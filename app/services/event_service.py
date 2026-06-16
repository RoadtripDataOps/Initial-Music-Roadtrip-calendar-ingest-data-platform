import json
from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import CrawlRun, CrawlRunStatus, Event, EventSourceClaim
from app.services.event_dedupe_service import (
    NormalizedEventCandidate,
    SourceClaimInput,
    candidate_dedupe_key,
    upsert_event_from_candidate,
)
from app.services.ics_service import IcsEventCandidate, parse_ics_events
from app.services.venue_service import ensure_venue_from_location_text


def appears_to_be_ics(crawl_run: CrawlRun) -> bool:
    """Return whether a crawl run looks like an ICS/iCalendar response."""

    content_type = (crawl_run.content_type or "").lower()
    source_path = urlparse(crawl_run.source_url).path.lower()
    raw_body = crawl_run.raw_response_body or ""
    return (
        "text/calendar" in content_type
        or source_path.endswith(".ics")
        or "BEGIN:VCALENDAR" in raw_body[:1000].upper()
    )


def event_dedupe_key(crawl_run: CrawlRun, candidate: IcsEventCandidate) -> str:
    """Create a stable cross-crawl dedupe key for an extracted ICS event."""

    normalized = NormalizedEventCandidate(
        source_id=crawl_run.source_id,
        crawl_run_id=crawl_run.id,
        category="Concert",
        record_type="event",
        source_type="ics",
        ingestion_provider="ics",
        upstream_event_source="ics",
        upstream_event_id=candidate.source_event_id,
        title=candidate.title,
        description=candidate.description,
        start_datetime=candidate.start_datetime,
        end_datetime=candidate.end_datetime,
        timezone=candidate.timezone,
        location_text=candidate.location_text,
        source_url=candidate.source_url or crawl_run.source_url,
        source_event_id=candidate.source_event_id,
        all_day=candidate.all_day,
        has_time=not candidate.all_day,
        raw_event_json=event_raw_json(candidate),
    )
    return candidate_dedupe_key(normalized)[0]


def event_raw_json(candidate: IcsEventCandidate) -> str:
    """Serialize normalized plus raw ICS event details for provenance."""

    payload = {
        "title": candidate.title,
        "description": candidate.description,
        "start_datetime": candidate.start_datetime.isoformat(),
        "end_datetime": (
            candidate.end_datetime.isoformat() if candidate.end_datetime else None
        ),
        "timezone": candidate.timezone,
        "location_text": candidate.location_text,
        "source_url": candidate.source_url,
        "source_event_id": candidate.source_event_id,
        "all_day": candidate.all_day,
        "raw_event": candidate.raw_event,
    }
    return json.dumps(payload, ensure_ascii=True, sort_keys=True)


def ics_event_status(candidate: IcsEventCandidate) -> str | None:
    properties = candidate.raw_event.get("properties")
    if isinstance(properties, dict):
        status = properties.get("STATUS")
        return str(status).strip() if status else None
    return None


def ics_source_chain_json(crawl_run: CrawlRun) -> str:
    return json.dumps(
        [
            {
                "role": "calendar_feed",
                "source": "ics",
                "display_name": "ICS",
                "url": crawl_run.source_url,
            }
        ],
        ensure_ascii=True,
        sort_keys=True,
    )


def ics_external_identifiers_json(candidate: IcsEventCandidate) -> str:
    if not candidate.source_event_id:
        return "[]"
    return json.dumps(
        [
            {
                "scope": "event",
                "source": "ics",
                "identifier": candidate.source_event_id,
            }
        ],
        ensure_ascii=True,
        sort_keys=True,
    )


def save_ics_events_for_crawl_run(session: Session, crawl_run: CrawlRun) -> int:
    """Parse and save ICS events for one successful crawl run."""

    if crawl_run.status != CrawlRunStatus.success.value or not appears_to_be_ics(
        crawl_run
    ):
        return 0
    if not crawl_run.raw_response_body:
        return 0

    try:
        candidates = parse_ics_events(crawl_run.raw_response_body)
    except ValueError:
        return 0
    seen_keys: set[str] = set()
    created_count = 0
    updated_count = 0
    duplicate_count = 0
    skipped_count = 0
    cancelled_count = 0
    claims_count = 0

    for candidate in candidates:
        raw_json = event_raw_json(candidate)
        source_chain_json = ics_source_chain_json(crawl_run)
        external_ids_json = ics_external_identifiers_json(candidate)
        venue = ensure_venue_from_location_text(session, candidate.location_text)
        normalized = NormalizedEventCandidate(
            source_id=crawl_run.source_id,
            crawl_run_id=crawl_run.id,
            event_venue_id=venue.id if venue else None,
            category="Concert",
            record_type="event",
            source_type="ics",
            ingestion_provider="ics",
            upstream_event_source="ics",
            upstream_event_id=candidate.source_event_id,
            source_chain_json=source_chain_json,
            external_identifiers_json=external_ids_json,
            provenance_flags_json="[]",
            title=candidate.title[:500],
            description=candidate.description,
            start_datetime=candidate.start_datetime,
            end_datetime=candidate.end_datetime,
            timezone=candidate.timezone[:128] if candidate.timezone else None,
            location_text=candidate.location_text,
            source_url=candidate.source_url or crawl_run.source_url,
            source_event_id=(
                candidate.source_event_id[:500]
                if candidate.source_event_id
                else None
            ),
            event_status=ics_event_status(candidate),
            all_day=candidate.all_day,
            has_time=not candidate.all_day,
            raw_event_json=raw_json,
        )
        dedupe_key, _confidence = candidate_dedupe_key(normalized)
        if dedupe_key in seen_keys:
            skipped_count += 1
            continue
        seen_keys.add(dedupe_key)
        result = upsert_event_from_candidate(
            session,
            normalized,
            SourceClaimInput(
                source_type="ics",
                ingestion_provider="ics",
                upstream_event_source="ics",
                upstream_event_id=candidate.source_event_id,
                provider_event_id=candidate.source_event_id,
                source_record_id=candidate.source_event_id,
                source_url=candidate.source_url or crawl_run.source_url,
                source_name=crawl_run.source.organization_name
                if crawl_run.source
                else None,
                calendar_source_id=crawl_run.source_id,
                crawl_run_id=crawl_run.id,
                raw_payload_json=raw_json,
                normalized_payload_json=raw_json,
                field_values={
                    "title": candidate.title,
                    "start_datetime": candidate.start_datetime,
                    "source_event_id": candidate.source_event_id,
                },
                source_chain_json=source_chain_json,
                external_identifiers_json=external_ids_json,
            ),
        )
        claims_count += 1
        if result.action == "created":
            created_count += 1
        elif result.action == "updated":
            updated_count += 1
        elif result.action == "duplicate_candidate":
            duplicate_count += 1
        elif result.action == "cancelled":
            cancelled_count += 1
        else:
            skipped_count += 1

    crawl_run.events_created_count = created_count
    crawl_run.events_updated_count = updated_count
    crawl_run.duplicate_candidate_count = duplicate_count
    crawl_run.events_skipped_count = skipped_count
    crawl_run.events_cancelled_count = cancelled_count
    crawl_run.source_claims_created_count = claims_count
    session.add(crawl_run)
    session.commit()
    return created_count


def count_events_for_crawl_run(session: Session, crawl_run_id: int) -> int:
    """Return how many events were extracted from a crawl run."""

    statement = select(func.count(func.distinct(EventSourceClaim.event_id))).where(
        EventSourceClaim.crawl_run_id == crawl_run_id,
        EventSourceClaim.event_id.is_not(None),
    )
    return int(session.scalar(statement) or 0)


def list_events(session: Session) -> list[Event]:
    """Return normalized events by start date."""

    statement = (
        select(Event)
        .options(
            selectinload(Event.source),
            selectinload(Event.crawl_run),
            selectinload(Event.venue),
            selectinload(Event.source_claims),
        )
        .order_by(Event.start_datetime.asc(), Event.id.asc())
    )
    return list(session.scalars(statement).all())


def get_event(session: Session, event_id: int) -> Event | None:
    """Return one normalized event with provenance relationships loaded."""

    statement = (
        select(Event)
        .options(
            selectinload(Event.source),
            selectinload(Event.crawl_run),
            selectinload(Event.venue),
            selectinload(Event.source_claims),
        )
        .where(Event.id == event_id)
    )
    return session.scalars(statement).first()
