from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    CrawlRun,
    Event,
    ImageCandidate,
    MasterCalendarSource,
    SourceExtractedEventCandidate,
)
from app.services.event_dedupe_service import (
    NormalizedEventCandidate,
    SourceClaimInput,
    upsert_event_from_candidate,
)
from app.services.event_photo_rescue_service import run_event_photo_rescue
from app.services.extraction_types import EventCandidate, ExtractionResult
from app.services.image_qa_service import (
    ImageCandidateInput,
    create_image_candidate,
    normalize_image_url,
)
from app.services.poi_candidate_service import (
    create_poi_candidate_from_extraction,
    create_poi_candidate_from_extraction_payload,
)
from app.services.source_extraction_utils import clean_text
from app.services.ticket_link_service import classify_ticket_link
from app.services.venue_service import ensure_venue_from_location_text


def json_dumps(value: object) -> str:
    return json.dumps(value, default=json_default, ensure_ascii=True, sort_keys=True)


def json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def list_extracted_event_candidates(
    session: Session,
    review_status: str | None = None,
) -> list[SourceExtractedEventCandidate]:
    statement = (
        select(SourceExtractedEventCandidate)
        .options(
            selectinload(SourceExtractedEventCandidate.crawl_run).selectinload(
                CrawlRun.source,
            )
        )
        .order_by(
            SourceExtractedEventCandidate.created_at.desc(),
            SourceExtractedEventCandidate.id.desc(),
        )
    )
    if review_status:
        statement = statement.where(
            SourceExtractedEventCandidate.review_status == review_status
        )
    return list(session.scalars(statement).all())


def get_extracted_event_candidate(
    session: Session,
    candidate_id: int,
) -> SourceExtractedEventCandidate | None:
    return session.scalars(
        select(SourceExtractedEventCandidate)
        .options(
            selectinload(SourceExtractedEventCandidate.crawl_run).selectinload(
                CrawlRun.source,
            )
        )
        .where(SourceExtractedEventCandidate.id == candidate_id)
    ).first()


def extracted_candidates_for_crawl_run(
    session: Session,
    crawl_run_id: int,
) -> list[SourceExtractedEventCandidate]:
    return list(
        session.scalars(
            select(SourceExtractedEventCandidate)
            .where(SourceExtractedEventCandidate.crawl_run_id == crawl_run_id)
            .order_by(SourceExtractedEventCandidate.id.asc())
        ).all()
    )


def persist_extraction_result(
    session: Session,
    crawl_run: CrawlRun,
    result: ExtractionResult,
) -> list[SourceExtractedEventCandidate]:
    """Store extractor metadata and staged event candidates for review."""

    summary = {
        **result.extraction_summary,
        "discovered_links": [
            {
                "discovered_url": link.discovered_url,
                "anchor_text": link.anchor_text,
                "confidence": link.confidence,
                "reason": link.reason,
                "source_url": link.source_url,
            }
            for link in result.discovered_links
        ],
    }
    crawl_run.extractor_type = result.extractor_type
    crawl_run.extraction_status = result.status
    crawl_run.event_candidates_count = len(result.event_candidates)
    crawl_run.unsupported_reason = result.unsupported_reason
    crawl_run.extraction_warnings_json = json_dumps(result.warnings)
    crawl_run.extraction_errors_json = json_dumps(result.errors)
    crawl_run.discovered_links_count = len(result.discovered_links)
    crawl_run.extraction_summary_json = json_dumps(summary)
    staged: list[SourceExtractedEventCandidate] = []
    poi_candidate_count = 0
    for candidate in result.event_candidates:
        existing = matching_staged_candidate(session, crawl_run.id, candidate)
        if existing is not None:
            staged.append(existing)
            if create_poi_candidate_from_extraction(
                session,
                staged_event=existing,
                event_candidate=candidate,
                extractor_type=result.extractor_type,
            ):
                poi_candidate_count += 1
            continue
        staged_candidate = staged_candidate_from_event_candidate(
            crawl_run,
            result.extractor_type,
            candidate,
        )
        session.add(staged_candidate)
        session.flush()
        if create_poi_candidate_from_extraction(
            session,
            staged_event=staged_candidate,
            event_candidate=candidate,
            extractor_type=result.extractor_type,
        ):
            poi_candidate_count += 1
        staged.append(staged_candidate)
    for poi_payload in result.poi_candidates:
        if create_poi_candidate_from_extraction_payload(
            session,
            crawl_run_id=crawl_run.id,
            master_calendar_source_id=None,
            payload=poi_payload,
            extractor_type=result.extractor_type,
        ):
            poi_candidate_count += 1
    if poi_candidate_count:
        summary["poi_candidate_count"] = poi_candidate_count
    update_master_source_quality(session, crawl_run, result)
    session.add(crawl_run)
    session.commit()
    for item in staged:
        session.refresh(item)
    return staged


def matching_staged_candidate(
    session: Session,
    crawl_run_id: int,
    candidate: EventCandidate,
) -> SourceExtractedEventCandidate | None:
    return session.scalars(
        select(SourceExtractedEventCandidate).where(
            SourceExtractedEventCandidate.crawl_run_id == crawl_run_id,
            SourceExtractedEventCandidate.event_name == candidate.event_name,
            SourceExtractedEventCandidate.start_datetime == candidate.start_datetime,
            SourceExtractedEventCandidate.event_url == candidate.event_url,
        )
    ).first()


def staged_candidate_from_event_candidate(
    crawl_run: CrawlRun,
    extractor_type: str,
    candidate: EventCandidate,
) -> SourceExtractedEventCandidate:
    normalized = normalized_payload(candidate, crawl_run, extractor_type)
    source_claim_preview = {
        "source_type": "source_extracted",
        "ingestion_provider": extractor_type,
        "source_url": candidate.event_url or crawl_run.source_url,
        "calendar_source_id": crawl_run.source_id,
        "crawl_run_id": crawl_run.id,
    }
    master_id = crawl_run.source.claimed_source_id if crawl_run.source else None
    return SourceExtractedEventCandidate(
        crawl_run_id=crawl_run.id,
        master_calendar_source_id=master_id,
        source_url=crawl_run.source_url,
        extractor_type=extractor_type,
        event_name=candidate.event_name,
        start_datetime=candidate.start_datetime,
        venue_name=candidate.venue_name,
        event_url=candidate.event_url,
        raw_fragment_json=json_dumps(candidate.raw_fragment),
        normalized_payload_json=json_dumps(normalized),
        review_status=candidate.review_status,
        validation_status=candidate.validation_status,
        validation_errors_json=json_dumps(candidate.validation_errors),
        quality_flags_json=json_dumps(candidate.quality_flags),
        source_claim_preview_json=json_dumps(source_claim_preview),
    )


def normalized_payload(
    candidate: EventCandidate,
    crawl_run: CrawlRun,
    extractor_type: str,
) -> dict[str, object]:
    ticket = classify_ticket_link(candidate.tickets_link)
    location_text = candidate.venue_name or candidate.venue_address
    image_payloads = [
        {
            "image_url": item.image_url,
            "source_url": item.source_url,
            "image_role": item.image_role,
            "source_payload_path": item.source_payload_path,
        }
        for item in candidate.image_candidates
    ]
    source_chain = [
        {
            "role": "approved_source_page",
            "source": extractor_type,
            "url": crawl_run.source_url,
        }
    ]
    if candidate.event_url:
        source_chain.append(
            {
                "role": "event_detail",
                "source": extractor_type,
                "url": candidate.event_url,
            }
        )
    return {
        "category": "Concert",
        "record_type": "event",
        "source_type": "source_extracted",
        "ingestion_provider": extractor_type,
        "upstream_event_source": extractor_type,
        "title": candidate.event_name,
        "headliner": candidate.headliner or candidate.event_name,
        "supporting_artists": candidate.supporting_artists,
        "description": candidate.description,
        "start_datetime": candidate.start_datetime.isoformat()
        if candidate.start_datetime
        else None,
        "end_datetime": candidate.end_datetime.isoformat()
        if candidate.end_datetime
        else None,
        "timezone": candidate.timezone,
        "location_text": location_text,
        "venue_name": candidate.venue_name,
        "venue_address": candidate.venue_address,
        "city": candidate.city,
        "state": candidate.state,
        "zip_code": candidate.zip_code,
        "country": candidate.country,
        "latitude": candidate.latitude,
        "longitude": candidate.longitude,
        "source_url": candidate.event_url or crawl_run.source_url,
        "source_event_id": candidate.source_event_id,
        "event_status": candidate.event_status,
        "tickets_link": candidate.tickets_link,
        "price": candidate.price,
        "ticket_link_classification": ticket.category,
        "ticketing_provider": ticket.provider_key,
        "ticketing_provider_domain": ticket.provider_domain,
        "ticket_link_repair_strategy": ticket.repair_strategy,
        "ticket_link_repair_source": ticket.repair_source,
        "ticket_link_repair_suggestion": ticket.repair_suggestion,
        "recommended_ticket_link": ticket.recommended_url,
        "ticket_link_quality_score": ticket.quality_score,
        "ticket_offers_json": json_dumps(
            [
                {
                    "url": candidate.tickets_link,
                    "classification": ticket.category,
                    "usable": ticket.usable,
                    "recommended_url": ticket.recommended_url,
                    "flags": list(ticket.flags),
                }
            ]
            if candidate.tickets_link
            else []
        ),
        "source_chain_json": json_dumps(source_chain),
        "external_identifiers_json": json_dumps(
            [
                {
                    "scope": "event",
                    "source": extractor_type,
                    "identifier": candidate.source_event_id,
                }
            ]
            if candidate.source_event_id
            else []
        ),
        "provenance_flags_json": json_dumps(candidate.quality_flags),
        "image_candidates": image_payloads,
    }


def update_master_source_quality(
    session: Session,
    crawl_run: CrawlRun,
    result: ExtractionResult,
) -> None:
    master_id = crawl_run.source.claimed_source_id if crawl_run.source else None
    if not master_id:
        return
    master = session.get(MasterCalendarSource, master_id)
    if master is None:
        return
    master.last_extractor_type = result.extractor_type
    master.last_extraction_status = result.status
    master.last_event_candidate_count = len(result.event_candidates)
    flags = set(master.source_quality_flags)
    if result.status in {"success", "partial"}:
        master.extraction_success_count += 1
        flags.discard("unsupported_extractor")
    elif result.status == "unsupported":
        master.unsupported_count += 1
        flags.add("unsupported_extractor")
    else:
        master.extraction_failure_count += 1
        flags.add("extraction_failure")
    if result.warnings:
        flags.add("extraction_warnings")
    master.source_quality_flags_json = json_dumps(sorted(flags))
    session.add(master)


def approve_extracted_event_candidate(
    session: Session,
    candidate_id: int,
    *,
    approved_by: str | None = None,
) -> Event:
    candidate = get_extracted_event_candidate(session, candidate_id)
    if candidate is None:
        raise ValueError("Extracted event candidate not found.")
    if candidate.created_event_id:
        event = session.get(Event, candidate.created_event_id)
        if event is not None:
            return event
    if candidate.validation_status != "valid" or candidate.validation_errors:
        raise ValueError("Invalid extracted event candidates cannot be approved.")
    payload = candidate.normalized_payload
    normalized = normalized_candidate_from_payload(session, candidate, payload)
    claim = source_claim_from_payload(candidate, payload)
    result = upsert_event_from_candidate(session, normalized, claim)
    candidate.created_event_id = result.event.id
    candidate.review_status = (
        "duplicate_candidate"
        if result.action == "duplicate_candidate"
        else "approved"
    )
    create_image_candidates_for_extracted_event(session, candidate, result.event.id)
    run_event_photo_rescue(session, result.event.id, commit=False)
    if approved_by:
        payload["approved_by"] = approved_by
        candidate.normalized_payload_json = json_dumps(payload)
    session.add(candidate)
    session.commit()
    session.refresh(result.event)
    return result.event


def reject_extracted_event_candidate(
    session: Session,
    candidate_id: int,
) -> SourceExtractedEventCandidate:
    candidate = get_extracted_event_candidate(session, candidate_id)
    if candidate is None:
        raise ValueError("Extracted event candidate not found.")
    candidate.review_status = "rejected"
    session.add(candidate)
    session.commit()
    session.refresh(candidate)
    return candidate


def send_extracted_event_to_duplicate_review(
    session: Session,
    candidate_id: int,
) -> SourceExtractedEventCandidate:
    candidate = get_extracted_event_candidate(session, candidate_id)
    if candidate is None:
        raise ValueError("Extracted event candidate not found.")
    candidate.review_status = "duplicate_candidate"
    session.add(candidate)
    session.commit()
    session.refresh(candidate)
    return candidate


def normalized_candidate_from_payload(
    session: Session,
    candidate: SourceExtractedEventCandidate,
    payload: dict[str, object],
) -> NormalizedEventCandidate:
    start = parse_required_datetime(payload.get("start_datetime"), "start_datetime")
    end = parse_optional_datetime(payload.get("end_datetime"))
    location_text = clean_text(payload.get("location_text"))
    venue = ensure_venue_from_location_text(session, location_text)
    ingestion_provider = str(
        payload.get("ingestion_provider") or candidate.extractor_type
    )
    return NormalizedEventCandidate(
        source_id=candidate.crawl_run.source_id,
        crawl_run_id=candidate.crawl_run_id,
        event_venue_id=venue.id if venue else None,
        category="Concert",
        record_type="event",
        source_type="source_extracted",
        ingestion_provider=ingestion_provider,
        upstream_event_source=str(
            payload.get("upstream_event_source") or candidate.extractor_type
        ),
        upstream_event_id=clean_text(payload.get("source_event_id")),
        source_chain_json=str(payload.get("source_chain_json") or "[]"),
        external_identifiers_json=str(payload.get("external_identifiers_json") or "[]"),
        ticket_offers_json=str(payload.get("ticket_offers_json") or "[]"),
        provenance_flags_json=str(payload.get("provenance_flags_json") or "[]"),
        title=str(payload.get("title") or candidate.event_name or "Untitled event"),
        headliner=clean_text(payload.get("headliner")),
        supporting_artists=clean_text(payload.get("supporting_artists")),
        description=clean_text(payload.get("description")),
        start_datetime=start,
        end_datetime=end,
        timezone=clean_text(payload.get("timezone")),
        location_text=location_text,
        source_url=clean_text(payload.get("source_url")) or candidate.source_url,
        tickets_link=clean_text(payload.get("tickets_link")),
        price=clean_text(payload.get("price")),
        source_event_id=clean_text(payload.get("source_event_id")),
        event_status=clean_text(payload.get("event_status")),
        ticket_link_classification=clean_text(
            payload.get("ticket_link_classification")
        ),
        ticketing_provider=clean_text(payload.get("ticketing_provider")),
        ticketing_provider_domain=clean_text(payload.get("ticketing_provider_domain")),
        ticket_link_repair_strategy=clean_text(
            payload.get("ticket_link_repair_strategy")
        ),
        ticket_link_repair_source=clean_text(payload.get("ticket_link_repair_source")),
        ticket_link_repair_suggestion=clean_text(
            payload.get("ticket_link_repair_suggestion")
        ),
        recommended_ticket_link=clean_text(payload.get("recommended_ticket_link")),
        ticket_link_quality_score=parse_optional_float(
            payload.get("ticket_link_quality_score")
        ),
        raw_event_json=candidate.raw_fragment_json,
    )


def source_claim_from_payload(
    candidate: SourceExtractedEventCandidate,
    payload: dict[str, object],
) -> SourceClaimInput:
    ingestion_provider = str(
        payload.get("ingestion_provider") or candidate.extractor_type
    )
    return SourceClaimInput(
        source_type="source_extracted",
        ingestion_provider=ingestion_provider,
        upstream_event_source=str(
            payload.get("upstream_event_source") or candidate.extractor_type
        ),
        upstream_event_id=clean_text(payload.get("source_event_id")),
        provider_event_id=clean_text(payload.get("source_event_id")),
        source_record_id=clean_text(payload.get("source_event_id"))
        or f"crawl-{candidate.crawl_run_id}-candidate-{candidate.id}",
        source_url=clean_text(payload.get("source_url")) or candidate.source_url,
        source_name=candidate.crawl_run.source.organization_name
        if candidate.crawl_run and candidate.crawl_run.source
        else None,
        master_calendar_source_id=candidate.master_calendar_source_id,
        calendar_source_id=candidate.crawl_run.source_id,
        crawl_run_id=candidate.crawl_run_id,
        raw_payload_json=candidate.raw_fragment_json,
        normalized_payload_json=candidate.normalized_payload_json,
        field_values={
            "title": payload.get("title"),
            "start_datetime": payload.get("start_datetime"),
            "source_url": payload.get("source_url"),
        },
        source_chain_json=str(payload.get("source_chain_json") or "[]"),
        ticket_offers_json=str(payload.get("ticket_offers_json") or "[]"),
        external_identifiers_json=str(payload.get("external_identifiers_json") or "[]"),
    )


def create_image_candidates_for_extracted_event(
    session: Session,
    candidate: SourceExtractedEventCandidate,
    event_id: int,
) -> int:
    payload = candidate.normalized_payload
    image_items = payload.get("image_candidates")
    if not isinstance(image_items, list):
        return 0
    created = 0
    for item in image_items:
        if not isinstance(item, dict):
            continue
        image_url = clean_text(item.get("image_url"))
        if not image_url:
            continue
        normalized_url = normalize_image_url(image_url)
        existing = session.scalars(
            select(ImageCandidate).where(
                ImageCandidate.event_id == event_id,
                ImageCandidate.normalized_image_url == normalized_url,
            )
        ).first()
        if existing is not None:
            continue
        create_image_candidate(
            session,
            ImageCandidateInput(
                event_id=event_id,
                image_url=image_url,
                source_type="source_extracted",
                source_provider=candidate.extractor_type,
                source_url=clean_text(item.get("source_url")) or candidate.source_url,
                source_chain_json=str(payload.get("source_chain_json") or "[]"),
                image_role=clean_text(item.get("image_role")) or "event_provider",
                clearance_status="needs_approval",
                candidate_status="pending_review",
                rescue_source="provider_event_image",
                source_payload_path=clean_text(item.get("source_payload_path")),
            ),
            commit=False,
        )
        created += 1
    return created


def parse_required_datetime(value: object, field_name: str) -> datetime:
    parsed = parse_optional_datetime(value)
    if parsed is None:
        raise ValueError(f"{field_name} is required.")
    return parsed


def parse_optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def parse_optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value))
    except ValueError:
        return None
