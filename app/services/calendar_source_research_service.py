from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from urllib.parse import urlparse

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.db.models import (
    CalendarSourceResearchAuthorizationStatus,
    CalendarSourceResearchBatch,
    CalendarSourceResearchBatchStatus,
    CalendarSourceResearchDedupeStatus,
    CalendarSourceResearchItem,
    CalendarSourceResearchPreflightStatus,
    CalendarSourceResearchReviewStatus,
    CalendarSourceResearchSourceType,
    CrawlRun,
    Event,
    MasterCalendarSource,
    PoiCandidate,
    SourceExtractedEventCandidate,
    SourceReviewStatus,
)
from app.services.bulk_crawl_service import (
    BulkCrawlSummary,
    crawl_gate_reason,
    run_bulk_crawl_for_master_ids,
)
from app.services.crawl_service import Fetcher, FetchResult, fetch_calendar_url
from app.services.import_service import (
    ImportValidationError,
    clean_cell,
    parse_upload_rows,
    require_headers,
    row_json,
)
from app.services.master_calendar_service import (
    CalendarSourcePayload,
    canonicalize_calendar_url,
    create_or_attach_master_calendar_source,
    get_master_by_hash,
)
from app.services.risk_service import RiskAssessment, build_assessment
from app.services.security_service import url_safety_flags
from app.services.source_intelligence_service import get_or_create_scrape_profile

RESEARCH_SOURCE_TYPES = [item.value for item in CalendarSourceResearchSourceType]
RESEARCH_AUTHORIZATION_STATUSES = [
    item.value for item in CalendarSourceResearchAuthorizationStatus
]
RESEARCH_TEMPLATE_HEADERS = [
    "Calendar URL",
    "Source Name",
    "Organization Name",
    "Source Type",
    "City",
    "State",
    "Country",
    "Contact Email",
    "Authorization Status",
    "Notes",
]


@dataclass(frozen=True)
class ResearchBatchSummary:
    total_items: int
    new_sources: int
    existing_sources: int
    possible_duplicates: int
    invalid_or_blocked: int
    approved: int
    rejected: int
    needs_research: int
    pending_review: int
    preflight_success: int
    preflight_warnings: int
    preflight_failures: int


def _json_list(values: list[str]) -> str:
    return json.dumps(sorted(set(values)), ensure_ascii=True)


def _clean_optional(value: object | None) -> str | None:
    cleaned = clean_cell(value)
    return cleaned or None


def _normalized_source_type(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    return normalized if normalized in RESEARCH_SOURCE_TYPES else "unknown"


def _normalized_authorization_status(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    return (
        normalized
        if normalized in RESEARCH_AUTHORIZATION_STATUSES
        else CalendarSourceResearchAuthorizationStatus.internal_research.value
    )


def _is_valid_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname)


def _possible_duplicate_existing(
    session: Session,
    canonical_url: str,
    exact_match_id: int | None,
) -> int | None:
    parsed = urlparse(canonical_url)
    domain = parsed.hostname or ""
    path = parsed.path.rstrip("/") or "/"
    if not domain:
        return None
    candidates = list(
        session.scalars(
            select(MasterCalendarSource).where(MasterCalendarSource.domain == domain)
        ).all()
    )
    for source in candidates:
        if exact_match_id and source.id == exact_match_id:
            continue
        existing_path = urlparse(source.canonical_url).path.rstrip("/") or "/"
        if existing_path == path or existing_path.startswith(path) or path.startswith(
            existing_path
        ):
            return source.id
    return None


def _dedupe_status_for_item(
    session: Session,
    item: CalendarSourceResearchItem,
    seen_hashes: set[str],
    settings: Settings,
) -> None:
    flags: list[str] = []
    submitted_url = item.submitted_url.strip()
    if not _is_valid_http_url(submitted_url):
        item.canonical_url = None
        item.dedupe_status = CalendarSourceResearchDedupeStatus.invalid_url.value
        item.risk_level = "blocked"
        item.risk_flags_json = _json_list(["invalid_url"])
        return

    safety_flags = url_safety_flags(submitted_url, settings)
    if safety_flags:
        item.canonical_url = None
        item.dedupe_status = CalendarSourceResearchDedupeStatus.blocked_url.value
        item.risk_level = "blocked"
        item.risk_flags_json = _json_list(safety_flags)
        return

    canonical_url, url_hash = canonicalize_calendar_url(submitted_url)
    item.canonical_url = canonical_url
    exact_master = get_master_by_hash(session, url_hash)
    possible_id = _possible_duplicate_existing(
        session,
        canonical_url,
        exact_master.id if exact_master else None,
    )
    if exact_master is not None:
        item.dedupe_status = (
            CalendarSourceResearchDedupeStatus.existing_master_source.value
        )
        item.matched_master_calendar_source_id = exact_master.id
        flags.append("existing_master_source")
    elif url_hash in seen_hashes:
        item.dedupe_status = CalendarSourceResearchDedupeStatus.possible_duplicate.value
        flags.append("duplicate_within_batch")
    elif possible_id is not None:
        item.dedupe_status = CalendarSourceResearchDedupeStatus.possible_duplicate.value
        item.matched_master_calendar_source_id = possible_id
        flags.append("possible_duplicate_domain_path")
    else:
        item.dedupe_status = CalendarSourceResearchDedupeStatus.new_source.value
        item.matched_master_calendar_source_id = None
    seen_hashes.add(url_hash)
    assessment = build_assessment(20 if flags else 0, flags)
    item.risk_level = assessment.risk_level
    item.risk_flags_json = assessment.risk_flags_json


def create_research_batch(
    session: Session,
    *,
    batch_name: str,
    region_id: int | None = None,
    city: str | None = None,
    state: str | None = None,
    country: str | None = None,
    research_owner: str | None = None,
    source_goal_count: int = 0,
    notes: str | None = None,
) -> CalendarSourceResearchBatch:
    batch = CalendarSourceResearchBatch(
        batch_name=batch_name.strip(),
        region_id=region_id,
        city=_clean_optional(city),
        state=_clean_optional(state),
        country=_clean_optional(country) or "US",
        research_owner=_clean_optional(research_owner),
        source_goal_count=max(source_goal_count, 0),
        status=CalendarSourceResearchBatchStatus.draft.value,
        notes=_clean_optional(notes),
    )
    session.add(batch)
    session.commit()
    session.refresh(batch)
    return batch


def get_research_batch(
    session: Session,
    batch_id: int,
) -> CalendarSourceResearchBatch | None:
    return session.scalars(
        select(CalendarSourceResearchBatch)
        .options(selectinload(CalendarSourceResearchBatch.items))
        .where(CalendarSourceResearchBatch.id == batch_id)
    ).first()


def list_research_batches(session: Session) -> list[CalendarSourceResearchBatch]:
    return list(
        session.scalars(
            select(CalendarSourceResearchBatch)
            .options(selectinload(CalendarSourceResearchBatch.items))
            .order_by(
                CalendarSourceResearchBatch.updated_at.desc(),
                CalendarSourceResearchBatch.id.desc(),
            )
        ).all()
    )


def items_for_batch(
    session: Session,
    batch_id: int,
) -> list[CalendarSourceResearchItem]:
    return list(
        session.scalars(
            select(CalendarSourceResearchItem)
            .where(CalendarSourceResearchItem.batch_id == batch_id)
            .order_by(CalendarSourceResearchItem.id.asc())
        ).all()
    )


def add_research_item(
    session: Session,
    *,
    batch_id: int,
    submitted_url: str,
    suggested_source_name: str | None = None,
    organization_name: str | None = None,
    source_type: str | None = None,
    city: str | None = None,
    state: str | None = None,
    country: str | None = None,
    contact_email: str | None = None,
    authorization_status: str | None = None,
    notes: str | None = None,
    settings: Settings,
) -> CalendarSourceResearchItem:
    batch = session.get(CalendarSourceResearchBatch, batch_id)
    if batch is None:
        raise ValueError("Research batch not found.")
    item = CalendarSourceResearchItem(
        batch_id=batch.id,
        submitted_url=submitted_url.strip(),
        suggested_source_name=_clean_optional(suggested_source_name),
        organization_name=_clean_optional(organization_name),
        source_type=_normalized_source_type(source_type),
        city=_clean_optional(city) or batch.city,
        state=_clean_optional(state) or batch.state,
        country=_clean_optional(country) or batch.country or "US",
        contact_email=_clean_optional(contact_email),
        authorization_status=_normalized_authorization_status(authorization_status),
        notes=_clean_optional(notes),
    )
    session.add(item)
    session.flush()
    canonicalize_and_dedupe_items(session, batch.id, settings)
    batch.status = CalendarSourceResearchBatchStatus.preflight_ready.value
    session.add(batch)
    session.commit()
    session.refresh(item)
    return item


def add_items_from_pasted_urls(
    session: Session,
    *,
    batch_id: int,
    pasted_urls: str,
    settings: Settings,
) -> int:
    urls = [
        line.strip()
        for line in pasted_urls.replace(",", "\n").splitlines()
        if line.strip()
    ]
    for url in urls:
        add_research_item(
            session,
            batch_id=batch_id,
            submitted_url=url,
            authorization_status=(
                CalendarSourceResearchAuthorizationStatus.internal_research.value
            ),
            settings=settings,
        )
    return len(urls)


def add_items_from_csv(
    session: Session,
    *,
    batch_id: int,
    filename: str,
    content: bytes,
    settings: Settings,
    max_rows: int | None = None,
) -> int:
    _file_type, rows = parse_upload_rows(filename, content, max_rows=max_rows)
    require_headers(rows, RESEARCH_TEMPLATE_HEADERS)
    created = 0
    for row in rows:
        url = clean_cell(row.get("Calendar URL"))
        if not url:
            continue
        add_research_item(
            session,
            batch_id=batch_id,
            submitted_url=url,
            suggested_source_name=row.get("Source Name"),
            organization_name=row.get("Organization Name"),
            source_type=row.get("Source Type"),
            city=row.get("City"),
            state=row.get("State"),
            country=row.get("Country"),
            contact_email=row.get("Contact Email"),
            authorization_status=row.get("Authorization Status"),
            notes=row.get("Notes") or row_json(row),
            settings=settings,
        )
        created += 1
    if created == 0:
        raise ImportValidationError("Uploaded file contains no calendar URLs.")
    return created


def canonicalize_and_dedupe_items(
    session: Session,
    batch_id: int,
    settings: Settings,
) -> list[CalendarSourceResearchItem]:
    items = items_for_batch(session, batch_id)
    seen_hashes: set[str] = set()
    for item in items:
        _dedupe_status_for_item(session, item, seen_hashes, settings)
        session.add(item)
    session.commit()
    return items_for_batch(session, batch_id)


def preflight_research_item(
    session: Session,
    item_id: int,
    *,
    settings: Settings,
    fetcher: Fetcher | None = None,
) -> CalendarSourceResearchItem:
    item = session.get(CalendarSourceResearchItem, item_id)
    if item is None:
        raise ValueError("Research item not found.")
    safety_flags = url_safety_flags(item.submitted_url, settings)
    if safety_flags:
        item.preflight_status = CalendarSourceResearchPreflightStatus.blocked.value
        item.preflight_error = f"Crawler safety blocked URL: {', '.join(safety_flags)}"
        item.dedupe_status = CalendarSourceResearchDedupeStatus.blocked_url.value
        item.risk_level = "blocked"
        item.risk_flags_json = _json_list(safety_flags)
        session.add(item)
        session.commit()
        session.refresh(item)
        return item

    active_fetcher = fetcher or (lambda url: fetch_calendar_url(url, settings))
    result: FetchResult = active_fetcher(item.submitted_url)
    item.preflight_http_status = result.http_status_code
    item.preflight_content_type = (
        result.content_type[:255] if result.content_type else None
    )
    item.preflight_final_url = result.final_url or item.submitted_url
    item.preflight_error = result.error_message
    if result.error_message:
        lowered = result.error_message.lower()
        if "crawler safety blocked" in lowered:
            item.preflight_status = CalendarSourceResearchPreflightStatus.blocked.value
        elif "unsupported response content type" in lowered:
            item.preflight_status = CalendarSourceResearchPreflightStatus.warning.value
        else:
            item.preflight_status = CalendarSourceResearchPreflightStatus.failure.value
    elif result.http_status_code is not None and result.http_status_code >= 400:
        item.preflight_status = CalendarSourceResearchPreflightStatus.failure.value
        item.preflight_error = f"Source returned HTTP {result.http_status_code}."
    elif result.http_status_code is not None:
        item.preflight_status = CalendarSourceResearchPreflightStatus.success.value
    else:
        item.preflight_status = CalendarSourceResearchPreflightStatus.failure.value
        item.preflight_error = "Preflight did not return a response."
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def preflight_batch(
    session: Session,
    batch_id: int,
    *,
    settings: Settings,
    fetcher: Fetcher | None = None,
) -> list[CalendarSourceResearchItem]:
    canonicalize_and_dedupe_items(session, batch_id, settings)
    items = items_for_batch(session, batch_id)
    for item in items:
        if item.dedupe_status in {
            CalendarSourceResearchDedupeStatus.invalid_url.value,
            CalendarSourceResearchDedupeStatus.blocked_url.value,
        }:
            item.preflight_status = CalendarSourceResearchPreflightStatus.blocked.value
            item.preflight_error = item.preflight_error or item.dedupe_status
            session.add(item)
            session.commit()
            continue
        preflight_research_item(
            session,
            item.id,
            settings=settings,
            fetcher=fetcher,
        )
    batch = session.get(CalendarSourceResearchBatch, batch_id)
    if batch is not None:
        batch.status = CalendarSourceResearchBatchStatus.preflighted.value
        session.add(batch)
        session.commit()
    return items_for_batch(session, batch_id)


def _item_assessment(item: CalendarSourceResearchItem) -> RiskAssessment:
    score = 0
    flags = list(item.risk_flags)
    if item.preflight_status == CalendarSourceResearchPreflightStatus.warning.value:
        score += 10
        flags.append("preflight_warning")
    if item.preflight_status == CalendarSourceResearchPreflightStatus.failure.value:
        score += 25
        flags.append("preflight_failure")
    if item.preflight_status == CalendarSourceResearchPreflightStatus.blocked.value:
        score += 80
        flags.append("preflight_blocked")
    return build_assessment(score, flags)


def approve_item_to_master_registry(
    session: Session,
    item_id: int,
    *,
    master_status: str = "approved",
) -> CalendarSourceResearchItem:
    item = session.get(CalendarSourceResearchItem, item_id)
    if item is None:
        raise ValueError("Research item not found.")
    if item.dedupe_status in {
        CalendarSourceResearchDedupeStatus.invalid_url.value,
        CalendarSourceResearchDedupeStatus.blocked_url.value,
    }:
        item.review_status = CalendarSourceResearchReviewStatus.needs_research.value
        session.add(item)
        session.commit()
        session.refresh(item)
        return item
    organization = (
        item.organization_name or item.suggested_source_name or "Internal Research"
    )
    contact_email = item.contact_email or "research@musicroadtrip.local"
    payload = CalendarSourcePayload(
        organization_name=organization,
        contact_name=item.batch.research_owner if item.batch else None,
        contact_email=contact_email,
        calendar_name=item.suggested_source_name or organization,
        calendar_url=item.submitted_url,
        source_type=item.source_type,
        expected_category="Concert",
        city=item.city,
        state=item.state,
        country=item.country,
        region_or_market=item.batch.city if item.batch else item.city,
        authorization_confirmed=True,
        notes=item.notes,
        raw_row_json=json.dumps(
            {
                "research_batch_id": item.batch_id,
                "research_item_id": item.id,
                "authorization_status": item.authorization_status,
                "submitted_url": item.submitted_url,
            },
            ensure_ascii=True,
            sort_keys=True,
        ),
    )
    master, _submission, _created = create_or_attach_master_calendar_source(
        session,
        payload,
        _item_assessment(item),
        SourceReviewStatus.approved.value,
    )
    if master_status == "approved":
        master.status = "approved"
        master.review_status = SourceReviewStatus.approved.value
    else:
        master.status = "pending"
        master.review_status = SourceReviewStatus.pending_review.value
    session.add(master)
    session.commit()
    get_or_create_scrape_profile(session, master)
    item.review_status = CalendarSourceResearchReviewStatus.approved.value
    item.created_master_calendar_source_id = master.id
    item.matched_master_calendar_source_id = master.id
    item.dedupe_status = (
        CalendarSourceResearchDedupeStatus.existing_master_source.value
        if item.dedupe_status
        == CalendarSourceResearchDedupeStatus.existing_master_source.value
        else item.dedupe_status
    )
    session.add(item)
    batch = item.batch
    if batch is not None:
        batch.status = CalendarSourceResearchBatchStatus.approved_for_crawl.value
        session.add(batch)
    session.commit()
    session.refresh(item)
    return item


def approve_valid_batch_items(
    session: Session,
    batch_id: int,
    *,
    item_ids: list[int] | None = None,
    master_status: str = "approved",
) -> int:
    items = items_for_batch(session, batch_id)
    selected = set(item_ids or [item.id for item in items])
    approved = 0
    for item in items:
        if item.id not in selected:
            continue
        if (
            item.review_status
            != CalendarSourceResearchReviewStatus.pending_review.value
        ):
            continue
        if item.dedupe_status in {
            CalendarSourceResearchDedupeStatus.invalid_url.value,
            CalendarSourceResearchDedupeStatus.blocked_url.value,
        }:
            continue
        approve_item_to_master_registry(
            session,
            item.id,
            master_status=master_status,
        )
        approved += 1
    return approved


def reject_item(
    session: Session,
    item_id: int,
    notes: str | None = None,
) -> CalendarSourceResearchItem:
    item = session.get(CalendarSourceResearchItem, item_id)
    if item is None:
        raise ValueError("Research item not found.")
    item.review_status = CalendarSourceResearchReviewStatus.rejected.value
    if notes:
        item.notes = f"{item.notes}\n{notes}" if item.notes else notes
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def mark_needs_research(
    session: Session,
    item_id: int,
    notes: str | None = None,
) -> CalendarSourceResearchItem:
    item = session.get(CalendarSourceResearchItem, item_id)
    if item is None:
        raise ValueError("Research item not found.")
    item.review_status = CalendarSourceResearchReviewStatus.needs_research.value
    if notes:
        item.notes = f"{item.notes}\n{notes}" if item.notes else notes
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def master_source_ids_for_research_batch(session: Session, batch_id: int) -> list[int]:
    items = items_for_batch(session, batch_id)
    ids = [
        item.created_master_calendar_source_id or item.matched_master_calendar_source_id
        for item in items
        if item.review_status == CalendarSourceResearchReviewStatus.approved.value
        and (
            item.created_master_calendar_source_id
            or item.matched_master_calendar_source_id
        )
    ]
    return sorted({int(source_id) for source_id in ids if source_id is not None})


def run_crawl_for_approved_research_batch_sources(
    session: Session,
    batch_id: int,
    *,
    fetcher: Fetcher,
) -> BulkCrawlSummary:
    batch = session.get(CalendarSourceResearchBatch, batch_id)
    if batch is not None:
        batch.status = CalendarSourceResearchBatchStatus.crawl_running.value
        session.add(batch)
        session.commit()
    summary = run_bulk_crawl_for_master_ids(
        session,
        master_source_ids_for_research_batch(session, batch_id),
        fetcher=fetcher,
        title=f"Research Batch #{batch_id} Crawl Summary",
    )
    if batch is not None:
        batch.status = CalendarSourceResearchBatchStatus.crawl_complete.value
        session.add(batch)
        session.commit()
    return summary


def batch_summary(
    session: Session,
    batch_id: int,
) -> ResearchBatchSummary:
    items = items_for_batch(session, batch_id)
    return ResearchBatchSummary(
        total_items=len(items),
        new_sources=sum(
            item.dedupe_status == CalendarSourceResearchDedupeStatus.new_source.value
            for item in items
        ),
        existing_sources=sum(
            item.dedupe_status
            == CalendarSourceResearchDedupeStatus.existing_master_source.value
            for item in items
        ),
        possible_duplicates=sum(
            item.dedupe_status
            == CalendarSourceResearchDedupeStatus.possible_duplicate.value
            for item in items
        ),
        invalid_or_blocked=sum(
            item.dedupe_status
            in {
                CalendarSourceResearchDedupeStatus.invalid_url.value,
                CalendarSourceResearchDedupeStatus.blocked_url.value,
            }
            for item in items
        ),
        approved=sum(
            item.review_status == CalendarSourceResearchReviewStatus.approved.value
            for item in items
        ),
        rejected=sum(
            item.review_status == CalendarSourceResearchReviewStatus.rejected.value
            for item in items
        ),
        needs_research=sum(
            item.review_status
            == CalendarSourceResearchReviewStatus.needs_research.value
            for item in items
        ),
        pending_review=sum(
            item.review_status
            == CalendarSourceResearchReviewStatus.pending_review.value
            for item in items
        ),
        preflight_success=sum(
            item.preflight_status
            == CalendarSourceResearchPreflightStatus.success.value
            for item in items
        ),
        preflight_warnings=sum(
            item.preflight_status
            == CalendarSourceResearchPreflightStatus.warning.value
            for item in items
        ),
        preflight_failures=sum(
            item.preflight_status
            in {
                CalendarSourceResearchPreflightStatus.failure.value,
                CalendarSourceResearchPreflightStatus.blocked.value,
            }
            for item in items
        ),
    )


def source_research_dashboard_counts(session: Session) -> dict[str, int]:
    batches = list(session.scalars(select(CalendarSourceResearchBatch)).all())
    items = list(session.scalars(select(CalendarSourceResearchItem)).all())
    return {
        "batch_count": len(batches),
        "pending_items": sum(
            item.review_status
            == CalendarSourceResearchReviewStatus.pending_review.value
            for item in items
        ),
        "ready_for_preflight": sum(
            batch.status == CalendarSourceResearchBatchStatus.preflight_ready.value
            for batch in batches
        ),
        "ready_for_crawl": sum(
            batch.status == CalendarSourceResearchBatchStatus.approved_for_crawl.value
            for batch in batches
        ),
        "needs_research_after_crawl": sum(
            item.review_status
            == CalendarSourceResearchReviewStatus.needs_research.value
            for item in items
        ),
    }


def build_batch_shakedown_report(
    session: Session,
    batch_id: int,
) -> dict[str, object]:
    master_ids = master_source_ids_for_research_batch(session, batch_id)
    masters = [
        source
        for source in (
            session.get(MasterCalendarSource, source_id) for source_id in master_ids
        )
        if source is not None
    ]
    source_urls = {source.canonical_url for source in masters}
    source_ids = {source.id for source in masters}
    crawl_runs = (
        list(
            session.scalars(
                select(CrawlRun).where(CrawlRun.source_url.in_(source_urls))
            ).all()
        )
        if source_urls
        else []
    )
    crawl_ids = [run.id for run in crawl_runs]
    events = (
        list(session.scalars(select(Event).where(Event.crawl_run_id.in_(crawl_ids))).all())
        if crawl_ids
        else []
    )
    extracted_candidates = (
        list(
            session.scalars(
                select(SourceExtractedEventCandidate).where(
                    SourceExtractedEventCandidate.crawl_run_id.in_(crawl_ids)
                )
            ).all()
        )
        if crawl_ids
        else []
    )
    poi_candidates: list[PoiCandidate] = []
    poi_conditions = []
    if source_ids:
        poi_conditions.append(PoiCandidate.master_calendar_source_id.in_(source_ids))
    if crawl_ids:
        poi_conditions.append(PoiCandidate.crawl_run_id.in_(crawl_ids))
    if poi_conditions:
        poi_candidates = list(
            session.scalars(select(PoiCandidate).where(or_(*poi_conditions))).all()
        )
    profile_rows = [
        get_or_create_scrape_profile(session, source)
        for source in masters
    ]
    summary = batch_summary(session, batch_id)
    extractor_counts = Counter(profile.extractor_type for profile in profile_rows)
    platform_counts = Counter(profile.platform_type for profile in profile_rows)
    report = {
        "source_counts": {
            "total_researched_urls": summary.total_items,
            "new_sources": summary.new_sources,
            "existing_sources": summary.existing_sources,
            "possible_duplicates": summary.possible_duplicates,
            "rejected_or_blocked": summary.rejected + summary.invalid_or_blocked,
            "approved_to_master_registry": summary.approved,
        },
        "crawl_counts": {
            "approved_sources_crawled": len(
                {run.source_url for run in crawl_runs if run.status == "success"}
            ),
            "successful_crawls": sum(run.status == "success" for run in crawl_runs),
            "failed_crawls": sum(run.status == "failure" for run in crawl_runs),
            "unsupported_sources": sum(
                run.extraction_status == "unsupported" for run in crawl_runs
            ),
            "source_health_warnings": sum(
                profile.source_health_status in {"watch", "needs_review", "failing"}
                for profile in profile_rows
            ),
        },
        "event_counts": {
            "events_found": sum(run.event_candidates_count for run in crawl_runs)
            + len(events),
            "events_created": sum(run.events_created_count for run in crawl_runs),
            "events_updated": sum(run.events_updated_count for run in crawl_runs),
            "duplicate_events": sum(
                run.duplicate_candidate_count for run in crawl_runs
            ),
            "extracted_event_candidates_pending_review": sum(
                candidate.review_status == "pending_review"
                for candidate in extracted_candidates
            ),
        },
        "quality_counts": {
            "missing_image": sum(
                not event.selected_main_image_url and not event.main_image_url
                for event in events
            ),
            "selected_image_pending_approval": sum(
                event.image_clearance_status == "needs_approval" for event in events
            ),
            "missing_ticket_link": sum(
                not event.tickets_link and not event.recommended_ticket_link
                for event in events
            ),
            "bad_generic_ticket_links": sum(
                (event.ticket_link_classification or "")
                in {"generic_platform", "bad", "unresolved"}
                for event in events
            ),
            "missing_venue": sum(not event.location_text for event in events),
            "low_music_relevance": sum(
                (event.music_relevance_score or 100) < 50 for event in events
            ),
            "not_app_feed_ready": sum(
                event.publish_status not in {"approved", "published"}
                for event in events
            ),
        },
        "poi_counts": {
            "poi_candidates_created": len(poi_candidates),
            "matched_existing_pois": sum(
                candidate.match_status == "matched_existing"
                for candidate in poi_candidates
            ),
            "possible_poi_duplicates": sum(
                candidate.match_status == "possible_duplicate"
                for candidate in poi_candidates
            ),
            "event_venue_only_candidates": sum(
                candidate.match_status == "event_venue_only"
                for candidate in poi_candidates
            ),
            "needs_research": sum(
                candidate.review_status == "needs_research"
                for candidate in poi_candidates
            ),
        },
        "source_intelligence": {
            "extractor_types_used": dict(extractor_counts),
            "platforms_detected": dict(platform_counts),
            "sources_needing_review": sum(
                profile.source_health_status in {"watch", "needs_review"}
                for profile in profile_rows
            ),
            "sources_with_zero_event_drop": sum(
                profile.last_event_count == 0 and profile.average_event_count > 0
                for profile in profile_rows
            ),
            "sources_with_repeated_failures": sum(
                profile.failed_crawl_count >= 3 for profile in profile_rows
            ),
        },
    }
    return report


def crawl_block_reasons_for_batch(
    session: Session,
    batch_id: int,
) -> dict[int, str | None]:
    reasons: dict[int, str | None] = {}
    for source_id in master_source_ids_for_research_batch(session, batch_id):
        source = session.get(MasterCalendarSource, source_id)
        if source is not None:
            reasons[source_id] = crawl_gate_reason(source)
    return reasons
