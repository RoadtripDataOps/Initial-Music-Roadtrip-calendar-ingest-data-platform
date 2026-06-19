from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    CalendarSource,
    CrawlRun,
    CrawlRunStatus,
    Event,
    EventSourceClaim,
    MasterCalendarSource,
    PoiCandidate,
    SourceHealthStatus,
    SourceReviewStatus,
    SourceScrapeExtractorConfidence,
    SourceScrapeExtractorType,
    SourceScrapePlatformType,
    SourceScrapeProfile,
    utc_now,
)
from app.services.event_service import count_events_for_crawl_run
from app.services.source_extraction_service import (
    looks_like_ics,
    looks_like_jsonld,
    looks_like_rss_atom,
)

DEFAULT_SOURCE_REGISTRY_OUTPUT_DIR = Path("data/generated/source_registry")
APPROVED_SOURCES_FILENAME = "current_approved_calendar_sources.json"
SCRAPE_PROFILES_FILENAME = "current_source_scrape_profiles.json"


@dataclass(frozen=True)
class SourceIntelligenceFilters:
    health_status: str | None = None
    extractor_type: str | None = None
    platform_type: str | None = None
    requires_javascript: bool | None = None
    no_successful_crawl: bool = False
    event_count_dropped: bool = False
    high_duplicate_rate: bool = False
    high_missing_ticket_rate: bool = False
    high_missing_image_rate: bool = False


@dataclass(frozen=True)
class SourceIntelligenceRow:
    source: MasterCalendarSource
    profile: SourceScrapeProfile
    last_crawl: CrawlRun | None
    event_count_dropped: bool


def get_or_create_scrape_profile(
    session: Session,
    master_source: MasterCalendarSource,
) -> SourceScrapeProfile:
    """Return the one scrape profile for a master source, creating it if needed."""

    profile = session.scalars(
        select(SourceScrapeProfile).where(
            SourceScrapeProfile.master_calendar_source_id == master_source.id
        )
    ).first()
    if profile is not None:
        return profile
    profile = SourceScrapeProfile(
        master_calendar_source_id=master_source.id,
        source_url=master_source.original_url,
        canonical_url=master_source.canonical_url,
        platform_type=SourceScrapePlatformType.unknown.value,
        extractor_type=SourceScrapeExtractorType.unsupported.value,
        extractor_confidence=SourceScrapeExtractorConfidence.unknown.value,
        source_health_status=SourceHealthStatus.watch.value,
    )
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile


def master_source_for_crawl_run(
    session: Session,
    crawl_run: CrawlRun,
) -> MasterCalendarSource | None:
    """Resolve the master source represented by a legacy crawl run."""

    if crawl_run.source and crawl_run.source.claimed_source_id:
        source = session.get(MasterCalendarSource, crawl_run.source.claimed_source_id)
        if source is not None:
            return source
    urls = {crawl_run.source_url}
    if crawl_run.source:
        urls.add(crawl_run.source.calendar_url)
    return session.scalars(
        select(MasterCalendarSource).where(
            or_(
                MasterCalendarSource.canonical_url.in_(urls),
                MasterCalendarSource.original_url.in_(urls),
            )
        )
    ).first()


def source_ids_for_master(
    session: Session,
    master_source: MasterCalendarSource,
) -> list[int]:
    urls = {master_source.canonical_url, master_source.original_url}
    return list(
        session.scalars(
            select(CalendarSource.id).where(
                or_(
                    CalendarSource.claimed_source_id == master_source.id,
                    CalendarSource.calendar_url.in_(urls),
                )
            )
        ).all()
    )


def crawl_runs_for_master(
    session: Session,
    master_source: MasterCalendarSource,
) -> list[CrawlRun]:
    urls = {master_source.canonical_url, master_source.original_url}
    source_ids = source_ids_for_master(session, master_source)
    conditions = [CrawlRun.source_url.in_(urls)]
    if source_ids:
        conditions.append(CrawlRun.source_id.in_(source_ids))
    return list(
        session.scalars(
            select(CrawlRun)
            .where(or_(*conditions))
            .order_by(CrawlRun.fetched_at.asc(), CrawlRun.id.asc())
        ).all()
    )


def latest_crawl_for_profile(
    session: Session,
    master_source: MasterCalendarSource,
) -> CrawlRun | None:
    crawls = crawl_runs_for_master(session, master_source)
    return crawls[-1] if crawls else None


def crawl_event_count(session: Session, crawl_run: CrawlRun) -> int:
    """Return the best available event yield for one crawl run."""

    saved_count = count_events_for_crawl_run(session, crawl_run.id)
    direct_count = (
        crawl_run.event_candidates_count
        + crawl_run.events_created_count
        + crawl_run.events_updated_count
        + crawl_run.duplicate_candidate_count
    )
    summary_count = 0
    raw_summary = crawl_run.extraction_summary
    ics_count = raw_summary.get("ics_event_count")
    if isinstance(ics_count, int):
        summary_count = ics_count
    return max(saved_count, direct_count, summary_count)


def update_profile_from_crawl_run(
    session: Session,
    crawl_run: CrawlRun,
) -> SourceScrapeProfile | None:
    """Update scrape intelligence after a crawl has completed extraction."""

    master_source = master_source_for_crawl_run(session, crawl_run)
    if master_source is None:
        return None
    profile = get_or_create_scrape_profile(session, master_source)
    previous_average = profile.average_event_count
    event_count = crawl_event_count(session, crawl_run)
    raw_body = crawl_run.raw_response_body or ""
    if not profile.recipe_locked_by_admin:
        profile.platform_type = infer_platform_type(crawl_run)
        profile.extractor_type = normalized_extractor_type(crawl_run.extractor_type)
        profile.extractor_confidence = infer_extractor_confidence(crawl_run)
        if (
            crawl_run.extraction_status in {"success", "partial"}
            and profile.extractor_type != SourceScrapeExtractorType.unsupported.value
        ):
            profile.last_working_extractor = profile.extractor_type
        profile.requires_javascript = source_requires_javascript(crawl_run)
        profile.supports_pagination = source_supports_pagination(crawl_run)
        profile.event_link_discovery_enabled = crawl_run.discovered_links_count > 0
        if crawl_run.discovered_links:
            profile.event_detail_link_pattern = "discovered_event_links"
        timezone = crawl_run.extraction_summary.get("timezone_assumption")
        if isinstance(timezone, str) and timezone.strip():
            profile.timezone_assumption = timezone.strip()

    profile.source_url = master_source.original_url
    profile.canonical_url = master_source.canonical_url
    profile.last_content_type = crawl_run.content_type
    profile.last_final_url = crawl_run.final_url or crawl_run.source_url
    profile.last_response_hash = response_hash(raw_body) if raw_body else None
    if crawl_run.status == CrawlRunStatus.success.value:
        profile.last_successful_crawl_run_id = crawl_run.id
        profile.last_verified_at = crawl_run.fetched_at
    else:
        profile.last_failed_crawl_run_id = crawl_run.id
    profile.last_event_count = event_count

    metrics = compute_source_performance_metrics(session, master_source)
    profile.total_crawl_count = int(metrics["total_crawl_count"])
    profile.successful_crawl_count = int(metrics["successful_crawl_count"])
    profile.failed_crawl_count = int(metrics["failed_crawl_count"])
    profile.average_event_count = float(metrics["average_event_count"])
    profile.duplicate_rate = float(metrics["duplicate_rate"])
    profile.missing_ticket_rate = float(metrics["missing_ticket_rate"])
    profile.missing_image_rate = float(metrics["missing_image_rate"])
    profile.poi_candidate_rate = float(metrics["poi_candidate_rate"])

    health_status = compute_source_health(master_source)
    if (
        crawl_run.status == CrawlRunStatus.success.value
        and event_count == 0
        and previous_average > 0
    ):
        health_status = SourceHealthStatus.watch.value
        mark_profile_needs_review(
            profile,
            "Latest successful crawl produced zero events after prior event yield.",
        )
    profile.source_health_status = health_status

    master_source.last_crawled_at = crawl_run.fetched_at
    master_source.last_extractor_type = profile.extractor_type
    master_source.last_extraction_status = crawl_run.extraction_status
    master_source.last_event_candidate_count = event_count
    session.add(master_source)
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile


def infer_platform_type(crawl_run: CrawlRun) -> str:
    body = crawl_run.raw_response_body or ""
    source_url = crawl_run.source_url
    content_type = crawl_run.content_type
    lowered_url = (crawl_run.final_url or source_url).lower()
    lowered_body = body[:50000].lower()
    if crawl_run.extraction_status == "unsupported" or (
        crawl_run.error_message
        and "unsupported response content type" in crawl_run.error_message.lower()
    ):
        return SourceScrapePlatformType.unsupported.value
    if looks_like_ics(source_url, content_type, body):
        return SourceScrapePlatformType.ics.value
    if looks_like_rss_atom(content_type, body):
        return SourceScrapePlatformType.rss_atom.value
    if "eventbrite." in lowered_url:
        return SourceScrapePlatformType.eventbrite_page.value
    if "the-events-calendar" in lowered_body or "tribe-events" in lowered_body:
        return SourceScrapePlatformType.the_events_calendar.value
    if "wp-content" in lowered_body or "wp-json" in lowered_body:
        return SourceScrapePlatformType.wordpress_events.value
    if looks_like_jsonld(body):
        return SourceScrapePlatformType.json_ld.value
    if "tourism" in lowered_url or "visit" in urlparse(lowered_url).netloc:
        return SourceScrapePlatformType.tourism_board_calendar.value
    if "calendar" in lowered_url or "events" in lowered_url:
        return SourceScrapePlatformType.venue_calendar.value
    if "<html" in lowered_body or "<article" in lowered_body or "<div" in lowered_body:
        return SourceScrapePlatformType.static_html.value
    return SourceScrapePlatformType.unknown.value


def infer_extractor_confidence(crawl_run: CrawlRun) -> str:
    if crawl_run.status != CrawlRunStatus.success.value:
        return SourceScrapeExtractorConfidence.unknown.value
    extractor = normalized_extractor_type(crawl_run.extractor_type)
    event_count = (
        crawl_run.event_candidates_count
        + crawl_run.events_created_count
        + crawl_run.events_updated_count
        + crawl_run.duplicate_candidate_count
    )
    if extractor in {
        SourceScrapeExtractorType.ics.value,
        SourceScrapeExtractorType.json_ld_event.value,
        SourceScrapeExtractorType.rss_atom.value,
    } and event_count > 0:
        return SourceScrapeExtractorConfidence.high.value
    if extractor in {
        SourceScrapeExtractorType.html_event_list.value,
        SourceScrapeExtractorType.generic_html_links.value,
    } and event_count > 0:
        return SourceScrapeExtractorConfidence.medium.value
    if extractor == SourceScrapeExtractorType.unsupported.value:
        return SourceScrapeExtractorConfidence.low.value
    return SourceScrapeExtractorConfidence.low.value


def compute_source_health(master_source: MasterCalendarSource) -> str:
    profile = master_source.scrape_profile
    if master_source.status == "paused":
        return SourceHealthStatus.paused.value
    if profile is None:
        return SourceHealthStatus.watch.value
    if (
        profile.platform_type == SourceScrapePlatformType.unsupported.value
        or master_source.unsupported_count > 0
    ):
        return SourceHealthStatus.unsupported.value
    if profile.failed_crawl_count >= 3 and profile.successful_crawl_count == 0:
        return SourceHealthStatus.failing.value
    if profile.last_failed_crawl_run_id and profile.failed_crawl_count >= 3:
        return SourceHealthStatus.failing.value
    if profile.last_failed_crawl_run_id and not profile.last_successful_crawl_run_id:
        return SourceHealthStatus.watch.value
    if profile.last_failed_crawl_run_id:
        return SourceHealthStatus.needs_review.value
    if profile.last_event_count == 0 and profile.average_event_count > 0:
        return SourceHealthStatus.watch.value
    if (
        profile.duplicate_rate >= 0.4
        or profile.missing_ticket_rate >= 0.6
        or profile.missing_image_rate >= 0.6
    ):
        return SourceHealthStatus.needs_review.value
    return SourceHealthStatus.healthy.value


def compute_source_performance_metrics(
    session: Session,
    master_source: MasterCalendarSource,
) -> dict[str, float | int]:
    crawls = crawl_runs_for_master(session, master_source)
    successful = [
        crawl for crawl in crawls if crawl.status == CrawlRunStatus.success.value
    ]
    failed = [crawl for crawl in crawls if crawl.status == CrawlRunStatus.failure.value]
    event_counts = [crawl_event_count(session, crawl) for crawl in successful]
    event_total = sum(event_counts)
    duplicate_count = sum(crawl.duplicate_candidate_count for crawl in crawls)
    events = events_for_master(session, master_source)
    missing_ticket_count = sum(
        1
        for event in events
        if not clean_value(event.tickets_link)
        and not clean_value(event.recommended_ticket_link)
    )
    missing_image_count = sum(
        1
        for event in events
        if not clean_value(event.selected_main_image_url)
        and not clean_value(event.main_image_url)
    )
    poi_candidate_count = poi_candidate_count_for_master(session, master_source, crawls)
    event_denominator = max(len(events), event_total, 1)
    return {
        "total_crawl_count": len(crawls),
        "successful_crawl_count": len(successful),
        "failed_crawl_count": len(failed),
        "average_event_count": (event_total / len(successful)) if successful else 0.0,
        "duplicate_rate": duplicate_count / max(event_total, 1),
        "missing_ticket_rate": missing_ticket_count / event_denominator,
        "missing_image_rate": missing_image_count / event_denominator,
        "poi_candidate_rate": poi_candidate_count / max(event_total, len(crawls), 1),
    }


def build_source_developer_summary(
    master_source: MasterCalendarSource,
) -> dict[str, object]:
    profile = master_source.scrape_profile
    if profile is None:
        return {
            "source_name": master_source.source_name,
            "canonical_url": master_source.canonical_url,
            "source_health_status": SourceHealthStatus.watch.value,
            "message": "No scrape profile has been created yet.",
        }
    return {
        "source_name": master_source.source_name,
        "canonical_url": master_source.canonical_url,
        "platform_type": profile.platform_type,
        "extractor_type": profile.extractor_type,
        "extractor_confidence": profile.extractor_confidence,
        "source_health_status": profile.source_health_status,
        "last_working_extractor": profile.last_working_extractor,
        "requires_javascript": profile.requires_javascript,
        "supports_pagination": profile.supports_pagination,
        "event_link_discovery_enabled": profile.event_link_discovery_enabled,
        "last_final_url": profile.last_final_url,
        "last_content_type": profile.last_content_type,
        "last_response_hash": profile.last_response_hash,
        "total_crawl_count": profile.total_crawl_count,
        "successful_crawl_count": profile.successful_crawl_count,
        "failed_crawl_count": profile.failed_crawl_count,
        "average_event_count": profile.average_event_count,
        "last_event_count": profile.last_event_count,
        "duplicate_rate": profile.duplicate_rate,
        "missing_ticket_rate": profile.missing_ticket_rate,
        "missing_image_rate": profile.missing_image_rate,
        "poi_candidate_rate": profile.poi_candidate_rate,
        "recipe_locked_by_admin": profile.recipe_locked_by_admin,
        "recipe_version": profile.recipe_version,
        "developer_notes": profile.developer_notes,
    }


def mark_profile_needs_review(
    profile: SourceScrapeProfile,
    reason: str,
) -> SourceScrapeProfile:
    profile.source_health_status = SourceHealthStatus.needs_review.value
    profile.developer_notes = append_note(profile.developer_notes, reason)
    return profile


def lock_profile_recipe(profile: SourceScrapeProfile) -> SourceScrapeProfile:
    profile.recipe_locked_by_admin = True
    return profile


def unlock_profile_recipe(profile: SourceScrapeProfile) -> SourceScrapeProfile:
    profile.recipe_locked_by_admin = False
    return profile


def list_source_intelligence(
    session: Session,
    filters: SourceIntelligenceFilters | None = None,
) -> list[SourceIntelligenceRow]:
    filters = filters or SourceIntelligenceFilters()
    sources = list(
        session.scalars(
            select(MasterCalendarSource).order_by(
                MasterCalendarSource.source_name.asc(),
                MasterCalendarSource.id.asc(),
            )
        ).all()
    )
    rows: list[SourceIntelligenceRow] = []
    for source in sources:
        profile = get_or_create_scrape_profile(session, source)
        latest = latest_crawl_for_profile(session, source)
        dropped = profile.last_event_count == 0 and profile.average_event_count > 0
        row = SourceIntelligenceRow(
            source=source,
            profile=profile,
            last_crawl=latest,
            event_count_dropped=dropped,
        )
        if not source_matches_filters(row, filters):
            continue
        rows.append(row)
    return rows


def source_matches_filters(
    row: SourceIntelligenceRow,
    filters: SourceIntelligenceFilters,
) -> bool:
    profile = row.profile
    if filters.health_status and profile.source_health_status != filters.health_status:
        return False
    if filters.extractor_type and profile.extractor_type != filters.extractor_type:
        return False
    if filters.platform_type and profile.platform_type != filters.platform_type:
        return False
    if (
        filters.requires_javascript is not None
        and profile.requires_javascript is not filters.requires_javascript
    ):
        return False
    if filters.no_successful_crawl and profile.successful_crawl_count > 0:
        return False
    if filters.event_count_dropped and not row.event_count_dropped:
        return False
    if filters.high_duplicate_rate and profile.duplicate_rate < 0.4:
        return False
    if filters.high_missing_ticket_rate and profile.missing_ticket_rate < 0.5:
        return False
    if filters.high_missing_image_rate and profile.missing_image_rate < 0.5:
        return False
    return True


def export_source_registry_snapshot(
    session: Session,
    output_dir: str | Path = DEFAULT_SOURCE_REGISTRY_OUTPUT_DIR,
) -> dict[str, object]:
    """Write current approved-source and scrape-profile JSON snapshots."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    sources = list(
        session.scalars(
            select(MasterCalendarSource).where(
                MasterCalendarSource.status == "approved",
                MasterCalendarSource.review_status == SourceReviewStatus.approved.value,
            )
        ).all()
    )
    approved_records = [approved_source_record(session, source) for source in sources]
    profile_records = [scrape_profile_record(session, source) for source in sources]
    approved_path = output_path / APPROVED_SOURCES_FILENAME
    profiles_path = output_path / SCRAPE_PROFILES_FILENAME
    approved_path.write_text(
        json.dumps(approved_records, default=str, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    profiles_path.write_text(
        json.dumps(profile_records, default=str, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    return {
        "approved_sources_path": str(approved_path),
        "scrape_profiles_path": str(profiles_path),
        "approved_source_count": len(approved_records),
        "scrape_profile_count": len(profile_records),
    }


def approved_source_record(
    session: Session,
    source: MasterCalendarSource,
) -> dict[str, object]:
    profile = get_or_create_scrape_profile(session, source)
    latest = latest_crawl_for_profile(session, source)
    next_due = next_crawl_due(source, latest)
    return {
        "canonical_url": source.canonical_url,
        "source_name": source.source_name,
        "approval_status": source.status,
        "review_status": source.review_status,
        "crawl_frequency": source.crawl_frequency,
        "source_health": profile.source_health_status,
        "extractor_type": profile.extractor_type,
        "platform_type": profile.platform_type,
        "last_crawl": latest.fetched_at.isoformat() if latest else None,
        "next_crawl": next_due.isoformat() if next_due else None,
        "total_crawls": profile.total_crawl_count,
        "event_yield": profile.last_event_count,
        "notes": source.notes,
    }


def scrape_profile_record(
    session: Session,
    source: MasterCalendarSource,
) -> dict[str, object]:
    profile = get_or_create_scrape_profile(session, source)
    return build_source_developer_summary(source) | {
        "master_calendar_source_id": source.id,
        "source_url": profile.source_url,
        "admin_notes": profile.admin_notes,
        "last_verified_at": (
            profile.last_verified_at.isoformat() if profile.last_verified_at else None
        ),
    }


def next_crawl_due(
    source: MasterCalendarSource,
    latest_crawl: CrawlRun | None,
) -> datetime | None:
    from app.services.bulk_crawl_service import next_crawl_due_at

    return next_crawl_due_at(source.crawl_frequency, latest_crawl)


def normalized_extractor_type(value: str | None) -> str:
    allowed = {item.value for item in SourceScrapeExtractorType}
    return value if value in allowed else SourceScrapeExtractorType.unsupported.value


def response_hash(raw_body: str) -> str:
    return hashlib.sha256(raw_body.encode("utf-8")).hexdigest()


def source_requires_javascript(crawl_run: CrawlRun) -> bool:
    text = " ".join(
        [
            crawl_run.unsupported_reason or "",
            " ".join(crawl_run.extraction_warnings),
            crawl_run.raw_response_body[:5000] if crawl_run.raw_response_body else "",
        ]
    ).lower()
    return "javascript" in text or "__next_data__" in text


def source_supports_pagination(crawl_run: CrawlRun) -> bool:
    body = (crawl_run.raw_response_body or "")[:20000].lower()
    return (
        'rel="next"' in body
        or "next page" in body
        or "pagination" in body
        or crawl_run.discovered_links_count > crawl_run.event_candidates_count
    )


def events_for_master(
    session: Session,
    master_source: MasterCalendarSource,
) -> list[Event]:
    source_ids = source_ids_for_master(session, master_source)
    claim_conditions = [EventSourceClaim.master_calendar_source_id == master_source.id]
    if source_ids:
        claim_conditions.append(EventSourceClaim.calendar_source_id.in_(source_ids))
    event_ids = [
        event_id
        for event_id in session.scalars(
            select(EventSourceClaim.event_id).where(
                or_(*claim_conditions),
                EventSourceClaim.event_id.is_not(None),
            )
        ).all()
        if event_id is not None
    ]
    if not event_ids:
        return []
    return list(
        session.scalars(select(Event).where(Event.id.in_(sorted(set(event_ids))))).all()
    )


def poi_candidate_count_for_master(
    session: Session,
    master_source: MasterCalendarSource,
    crawls: list[CrawlRun],
) -> int:
    crawl_ids = [crawl.id for crawl in crawls]
    conditions = [PoiCandidate.master_calendar_source_id == master_source.id]
    if crawl_ids:
        conditions.append(PoiCandidate.crawl_run_id.in_(crawl_ids))
    return int(
        session.scalar(
            select(func.count()).select_from(PoiCandidate).where(or_(*conditions))
        )
        or 0
    )


def clean_value(value: object) -> str:
    return str(value or "").strip()


def append_note(existing: str | None, note: str) -> str:
    timestamp = utc_now().strftime("%Y-%m-%d %H:%M")
    new_note = f"[{timestamp}] {note.strip()}"
    return f"{existing.rstrip()}\n{new_note}" if existing else new_note
