from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    Event,
    EventDuplicateGroup,
    EventDuplicateGroupMember,
    EventSourceClaim,
    utc_now,
)

EventUpsertAction = Literal[
    "created",
    "updated",
    "duplicate_candidate",
    "skipped",
    "cancelled",
]


@dataclass(frozen=True)
class NormalizedEventCandidate:
    """Provider-neutral Concert event data ready for identity matching."""

    title: str
    start_datetime: datetime
    end_datetime: datetime | None = None
    timezone: str | None = None
    location_text: str | None = None
    event_venue_id: int | None = None
    source_id: int | None = None
    crawl_run_id: int | None = None
    import_batch_id: int | None = None
    api_feed_run_id: int | None = None
    api_feed_record_id: int | None = None
    api_provider_key: str | None = None
    api_source_record_id: str | None = None
    api_mapping_warnings_json: str | None = None
    api_quality_scores_json: str | None = None
    category: str = "Concert"
    record_type: str = "event"
    source_type: str = "unknown"
    headliner: str | None = None
    supporting_artists: str | None = None
    genre: str | None = None
    description: str | None = None
    source_url: str | None = None
    tickets_link: str | None = None
    price: str | None = None
    age_restriction: str | None = None
    doors_time: str | None = None
    main_image_url: str | None = None
    additional_image_urls: str | None = None
    spotify_url: str | None = None
    spotify_artist_id: str | None = None
    spotify_artist_name: str | None = None
    spotify_image_url: str | None = None
    spotify_match_confidence: float | None = None
    spotify_preview_json: str | None = None
    enrichment_status: str | None = None
    enrichment_flags_json: str = "[]"
    enrichment_suggestions_json: str = "{}"
    source_event_id: str | None = None
    provider_event_type: str | None = None
    provider_genre: str | None = None
    provider_subgenre: str | None = None
    music_category: str | None = None
    normalized_genre: str | None = None
    normalized_genres_json: str = "[]"
    genre_confidence: float | None = None
    genre_source: str | None = None
    music_relevance_score: float | None = None
    music_relevance_flags_json: str = "[]"
    ticket_link_classification: str | None = None
    ticketing_provider: str | None = None
    ticketing_provider_domain: str | None = None
    ticket_link_repair_strategy: str | None = None
    ticket_link_repair_source: str | None = None
    ticket_link_repair_suggestion: str | None = None
    recommended_ticket_link: str | None = None
    ticket_link_quality_score: float | None = None
    provider_doc_notes: str | None = None
    dedupe_source_fields_json: str | None = None
    venue_match_fields_json: str | None = None
    ingestion_provider: str | None = None
    upstream_event_source: str | None = None
    upstream_event_id: str | None = None
    provider_music_segment: str | None = None
    source_chain_json: str | None = None
    external_identifiers_json: str | None = None
    ticket_offers_json: str | None = None
    provenance_flags_json: str | None = None
    event_status: str | None = None
    has_time: bool | None = None
    all_day: bool | None = None
    raw_event_json: str = "{}"
    dedupe_key: str | None = None
    dedupe_confidence: str | None = None


@dataclass(frozen=True)
class SourceClaimInput:
    """Inbound source assertion preserved before and after event matching."""

    source_type: str
    ingestion_provider: str | None = None
    upstream_event_source: str | None = None
    upstream_event_id: str | None = None
    provider_event_id: str | None = None
    provider_event_type: str | None = None
    provider_record_id: str | None = None
    source_record_id: str | None = None
    source_url: str | None = None
    source_name: str | None = None
    master_calendar_source_id: int | None = None
    calendar_source_id: int | None = None
    crawl_run_id: int | None = None
    import_batch_id: int | None = None
    api_feed_run_id: int | None = None
    api_feed_record_id: int | None = None
    raw_payload_json: str = "{}"
    normalized_payload_json: str = "{}"
    field_values: dict[str, Any] = field(default_factory=dict)
    source_chain_json: str = "[]"
    ticket_offers_json: str = "[]"
    external_identifiers_json: str = "[]"
    claim_dedupe_key: str | None = None
    claim_dedupe_confidence: str | None = None


@dataclass(frozen=True)
class EventUpsertResult:
    event: Event
    source_claim: EventSourceClaim
    action: EventUpsertAction
    changed_fields: list[dict[str, Any]]
    duplicate_group: EventDuplicateGroup | None = None


@dataclass(frozen=True)
class DuplicateMemberView:
    member: EventDuplicateGroupMember
    event: Event | None
    source_claims: list[EventSourceClaim]


@dataclass(frozen=True)
class DuplicateGroupView:
    group: EventDuplicateGroup
    members: list[DuplicateMemberView]


TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
}

EVENT_FIELD_NAMES = [
    "source_id",
    "crawl_run_id",
    "event_venue_id",
    "import_batch_id",
    "api_feed_run_id",
    "api_feed_record_id",
    "api_provider_key",
    "api_source_record_id",
    "category",
    "record_type",
    "source_type",
    "provider_event_type",
    "provider_genre",
    "provider_subgenre",
    "music_category",
    "normalized_genre",
    "normalized_genres_json",
    "genre_confidence",
    "genre_source",
    "music_relevance_score",
    "music_relevance_flags_json",
    "ticket_link_classification",
    "ticketing_provider",
    "ticketing_provider_domain",
    "ticket_link_repair_strategy",
    "ticket_link_repair_source",
    "ticket_link_repair_suggestion",
    "recommended_ticket_link",
    "ticket_link_quality_score",
    "provider_doc_notes",
    "dedupe_source_fields_json",
    "venue_match_fields_json",
    "ingestion_provider",
    "upstream_event_source",
    "upstream_event_id",
    "provider_music_segment",
    "source_chain_json",
    "external_identifiers_json",
    "ticket_offers_json",
    "provenance_flags_json",
    "event_status",
    "has_time",
    "all_day",
    "title",
    "headliner",
    "supporting_artists",
    "genre",
    "description",
    "start_datetime",
    "end_datetime",
    "timezone",
    "location_text",
    "source_url",
    "tickets_link",
    "price",
    "age_restriction",
    "doors_time",
    "main_image_url",
    "additional_image_urls",
    "spotify_url",
    "spotify_artist_id",
    "spotify_artist_name",
    "spotify_image_url",
    "spotify_match_confidence",
    "spotify_preview_json",
    "enrichment_status",
    "enrichment_flags_json",
    "enrichment_suggestions_json",
    "source_event_id",
    "raw_event_json",
]

SIGNIFICANT_FIELDS = {
    "title",
    "start_datetime",
    "end_datetime",
    "event_venue_id",
    "location_text",
    "tickets_link",
    "source_url",
    "event_status",
    "event_lifecycle_status",
}


def normalize_dedupe_text(value: str | None) -> str:
    """Normalize title, venue, and artist text for conservative matching."""

    if not value:
        return ""
    cleaned = value.casefold().replace("&", " and ")
    cleaned = re.sub(r"['`´]", "", cleaned)
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    noise_words = {"the", "a", "an", "live", "concert", "show", "event"}
    parts = [part for part in cleaned.split() if part not in noise_words]
    return " ".join(parts)


def stable_hash(*parts: object) -> str:
    basis = "|".join("" if part is None else str(part) for part in parts)
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def canonical_url(value: str | None) -> str:
    if not value:
        return ""
    parsed = urlparse(value.strip())
    if not parsed.scheme or not parsed.netloc:
        return value.strip()
    query = [
        (key, item_value)
        for key, item_value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMS
    ]
    path = parsed.path
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            "",
            urlencode(query, doseq=True),
            "",
        )
    )


def _clean(value: str | None, limit: int | None = None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    return cleaned[:limit] if limit else cleaned


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _json(value: object) -> str:
    return json.dumps(value, default=_json_default, ensure_ascii=True, sort_keys=True)


def _json_or_default(value: str | None, default: str) -> str:
    if not value:
        return default
    try:
        json.loads(value)
    except json.JSONDecodeError:
        return default
    return value


def _parse_datetime(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def event_lifecycle_status(candidate: NormalizedEventCandidate) -> str:
    raw_status = " ".join(
        [
            candidate.event_status or "",
            candidate.raw_event_json or "",
        ]
    ).casefold()
    if "cancelled" in raw_status or "canceled" in raw_status:
        return "cancelled"
    if "postponed" in raw_status:
        return "postponed"
    if "rescheduled" in raw_status:
        return "rescheduled"
    return "active"


def _candidate_venue_text(candidate: NormalizedEventCandidate) -> str:
    return normalize_dedupe_text(candidate.location_text)


def _event_venue_text(event: Event) -> str:
    if event.venue:
        return normalize_dedupe_text(event.venue.display_name)
    return normalize_dedupe_text(event.location_text)


def _same_venue(candidate: NormalizedEventCandidate, event: Event) -> bool:
    if candidate.event_venue_id and event.event_venue_id:
        return candidate.event_venue_id == event.event_venue_id
    candidate_text = _candidate_venue_text(candidate)
    event_text = _event_venue_text(event)
    return bool(candidate_text and event_text and candidate_text == event_text)


def _venue_conflict(candidate: NormalizedEventCandidate, event: Event) -> bool:
    if candidate.event_venue_id and event.event_venue_id:
        return candidate.event_venue_id != event.event_venue_id
    candidate_text = _candidate_venue_text(candidate)
    event_text = _event_venue_text(event)
    return bool(candidate_text and event_text and candidate_text != event_text)


def medium_event_key(candidate: NormalizedEventCandidate) -> str:
    title = normalize_dedupe_text(candidate.headliner or candidate.title)
    venue = _candidate_venue_text(candidate)
    ticket_url = canonical_url(
        candidate.recommended_ticket_link or candidate.tickets_link
    )
    start = candidate.start_datetime.replace(second=0, microsecond=0).isoformat()
    return stable_hash("event-medium", title, start, venue, ticket_url)


def weak_event_key(candidate: NormalizedEventCandidate) -> str:
    title = normalize_dedupe_text(candidate.headliner or candidate.title)
    start = candidate.start_datetime.replace(second=0, microsecond=0).isoformat()
    city_state = ""
    return stable_hash("event-weak", title, start, city_state)


def _source_identifier_key(candidate: NormalizedEventCandidate) -> str | None:
    provider = candidate.ingestion_provider or candidate.api_provider_key
    provider_id = (
        candidate.api_source_record_id
        or candidate.source_event_id
        or candidate.upstream_event_id
    )
    if provider and provider_id:
        return stable_hash("provider", provider, provider_id)
    if candidate.source_type == "ics" and candidate.source_event_id:
        return stable_hash(
            "ics",
            candidate.source_id,
            canonical_url(candidate.source_url),
            candidate.source_event_id,
        )
    if candidate.source_type == "file_upload" and candidate.source_event_id:
        return stable_hash(
            "file-upload-source-event-id",
            candidate.source_event_id,
            normalize_dedupe_text(candidate.title),
            candidate.start_datetime.date().isoformat(),
        )
    return None


def candidate_dedupe_key(candidate: NormalizedEventCandidate) -> tuple[str, str]:
    if candidate.dedupe_key:
        return candidate.dedupe_key[:64], candidate.dedupe_confidence or "strong"
    source_key = _source_identifier_key(candidate)
    if source_key:
        return source_key, "strong"
    return medium_event_key(candidate), "medium"


def _claim_key(
    candidate: NormalizedEventCandidate,
    claim: SourceClaimInput,
) -> tuple[str, str]:
    if claim.claim_dedupe_key:
        return claim.claim_dedupe_key[:64], claim.claim_dedupe_confidence or "strong"
    if claim.provider_event_id and claim.ingestion_provider:
        return (
            stable_hash(
                "provider-event",
                claim.ingestion_provider,
                claim.provider_event_id,
            ),
            "strong",
        )
    if claim.source_record_id and claim.source_type:
        return (
            stable_hash("source-record", claim.source_type, claim.source_record_id),
            "strong",
        )
    if candidate.source_event_id and claim.source_type == "ics":
        return (
            stable_hash(
                "ics-claim",
                claim.calendar_source_id,
                canonical_url(claim.source_url or candidate.source_url),
                candidate.source_event_id,
            ),
            "strong",
        )
    event_key, confidence = candidate_dedupe_key(candidate)
    return stable_hash("claim", claim.source_type, event_key), confidence


def _events_on_start_day(
    session: Session,
    candidate: NormalizedEventCandidate,
) -> list[Event]:
    day_start = datetime.combine(candidate.start_datetime.date(), time.min)
    day_end = day_start + timedelta(days=1)
    return list(
        session.scalars(
            select(Event)
            .options(selectinload(Event.venue))
            .where(
                Event.category == "Concert",
                Event.record_type == "event",
                Event.start_datetime >= day_start,
                Event.start_datetime < day_end,
            )
        ).all()
    )


def _find_existing_event(
    session: Session,
    candidate: NormalizedEventCandidate,
    claim_key: str,
    event_key: str,
) -> tuple[Event | None, str, float]:
    existing_claim = session.scalars(
        select(EventSourceClaim).where(
            EventSourceClaim.claim_dedupe_key == claim_key,
            EventSourceClaim.event_id.is_not(None),
        )
    ).first()
    if existing_claim and existing_claim.event_id:
        event = session.get(Event, existing_claim.event_id)
        if event:
            return event, "matching source claim", 1.0

    existing_event = session.scalars(
        select(Event)
        .options(selectinload(Event.venue))
        .where(Event.dedupe_key == event_key)
        .order_by(Event.id.asc())
    ).first()
    if existing_event:
        return existing_event, "matching event dedupe key", 0.96

    candidate_title = normalize_dedupe_text(candidate.headliner or candidate.title)
    best_event: Event | None = None
    best_score = 0.0
    best_reason = "no match"
    for event in _events_on_start_day(session, candidate):
        event_title = normalize_dedupe_text(event.headliner or event.title)
        if not candidate_title or candidate_title != event_title:
            continue
        if _same_venue(candidate, event):
            return event, "same title, start, and venue", 0.86
        if _venue_conflict(candidate, event):
            if best_score < 0.58:
                best_event = event
                best_score = 0.58
                best_reason = "same title and start with venue conflict"
            continue
        if best_score < 0.74:
            best_event = event
            best_score = 0.74
            best_reason = "same title and start, venue incomplete"
    return best_event, best_reason, best_score


def _candidate_event_kwargs(
    candidate: NormalizedEventCandidate,
    event_key: str,
    confidence: str,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        field_name: getattr(candidate, field_name)
        for field_name in EVENT_FIELD_NAMES
        if hasattr(candidate, field_name)
    }
    kwargs["title"] = candidate.title[:500]
    kwargs["source_event_id"] = _clean(candidate.source_event_id, 500)
    kwargs["timezone"] = _clean(candidate.timezone, 128)
    kwargs["category"] = "Concert"
    kwargs["record_type"] = "event"
    kwargs["dedupe_key"] = event_key
    kwargs["dedupe_confidence"] = confidence
    kwargs["event_lifecycle_status"] = event_lifecycle_status(candidate)
    kwargs["raw_event_json"] = candidate.raw_event_json or "{}"
    kwargs["source_chain_json"] = _json_or_default(candidate.source_chain_json, "[]")
    kwargs["external_identifiers_json"] = _json_or_default(
        candidate.external_identifiers_json,
        "[]",
    )
    kwargs["ticket_offers_json"] = _json_or_default(candidate.ticket_offers_json, "[]")
    kwargs["provenance_flags_json"] = _json_or_default(
        candidate.provenance_flags_json,
        "[]",
    )
    kwargs["enrichment_flags_json"] = _json_or_default(
        candidate.enrichment_flags_json,
        "[]",
    )
    kwargs["enrichment_suggestions_json"] = _json_or_default(
        candidate.enrichment_suggestions_json,
        "{}",
    )
    return kwargs


def _incoming_event_values(candidate: NormalizedEventCandidate) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for field_name in EVENT_FIELD_NAMES:
        if not hasattr(candidate, field_name):
            continue
        value = getattr(candidate, field_name)
        if value is not None:
            values[field_name] = value
    values["event_lifecycle_status"] = event_lifecycle_status(candidate)
    return values


def _should_update_field(event: Event, field_name: str, incoming: Any) -> bool:
    if incoming is None:
        return False
    if isinstance(incoming, str) and not incoming.strip():
        return False
    if field_name in {"selected_main_image_url", "selected_image_candidate_id"}:
        return False
    current = getattr(event, field_name)
    if current in {None, ""}:
        return True
    if field_name == "ticket_link_quality_score":
        try:
            return float(incoming) > float(current)
        except (TypeError, ValueError):
            return False
    if field_name in {"tickets_link", "recommended_ticket_link"}:
        incoming_score = event.ticket_link_quality_score or 0
        if not current:
            return True
        return incoming_score > (event.ticket_link_quality_score or 0)
    if field_name in {
        "source_id",
        "crawl_run_id",
        "import_batch_id",
        "api_feed_run_id",
        "api_feed_record_id",
    }:
        return True
    if field_name in {
        "raw_event_json",
        "source_chain_json",
        "external_identifiers_json",
    }:
        return bool(current != incoming)
    if field_name in {
        "title",
        "start_datetime",
        "end_datetime",
        "timezone",
        "event_status",
        "event_lifecycle_status",
    }:
        return bool(current != incoming)
    return False


def _update_existing_event(
    event: Event,
    candidate: NormalizedEventCandidate,
) -> list[dict[str, Any]]:
    changed: list[dict[str, Any]] = []
    for field_name, incoming in _incoming_event_values(candidate).items():
        if not hasattr(event, field_name):
            continue
        if not _should_update_field(event, field_name, incoming):
            continue
        old_value = getattr(event, field_name)
        if old_value == incoming:
            continue
        setattr(event, field_name, incoming)
        changed.append(
            {
                "field": field_name,
                "old": _json_default(old_value) if old_value is not None else None,
                "new": _json_default(incoming),
            }
        )
    if changed:
        event.update_count += 1
        event.changed_fields_json = _json(changed)
        event.last_update_summary_json = _json(
            [
                {
                    "at": utc_now().isoformat(),
                    "changed_fields": [item["field"] for item in changed],
                }
            ]
        )
        if SIGNIFICANT_FIELDS & {str(item["field"]) for item in changed}:
            event.last_significant_change_at = utc_now()
    event.last_seen_at = utc_now()
    return changed


def _create_source_claim(
    session: Session,
    candidate: NormalizedEventCandidate,
    claim_input: SourceClaimInput,
    claim_key: str,
    claim_confidence: str,
    match_reason: str,
    match_score: float,
) -> EventSourceClaim:
    claim = EventSourceClaim(
        source_type=claim_input.source_type,
        ingestion_provider=claim_input.ingestion_provider,
        upstream_event_source=claim_input.upstream_event_source,
        upstream_event_id=_clean(claim_input.upstream_event_id, 500),
        provider_event_id=_clean(claim_input.provider_event_id, 500),
        provider_event_type=claim_input.provider_event_type,
        provider_record_id=_clean(claim_input.provider_record_id, 500),
        source_record_id=_clean(claim_input.source_record_id, 500),
        source_url=claim_input.source_url or candidate.source_url,
        source_name=claim_input.source_name,
        master_calendar_source_id=claim_input.master_calendar_source_id,
        calendar_source_id=claim_input.calendar_source_id,
        crawl_run_id=claim_input.crawl_run_id or candidate.crawl_run_id,
        import_batch_id=claim_input.import_batch_id or candidate.import_batch_id,
        api_feed_run_id=claim_input.api_feed_run_id or candidate.api_feed_run_id,
        api_feed_record_id=claim_input.api_feed_record_id
        or candidate.api_feed_record_id,
        raw_payload_json=claim_input.raw_payload_json or candidate.raw_event_json,
        normalized_payload_json=claim_input.normalized_payload_json,
        field_values_json=_json(claim_input.field_values),
        source_chain_json=claim_input.source_chain_json,
        ticket_offers_json=claim_input.ticket_offers_json,
        external_identifiers_json=claim_input.external_identifiers_json,
        claim_dedupe_key=claim_key,
        claim_dedupe_confidence=claim_confidence,
        match_confidence=match_score,
        match_reason_json=_json([match_reason]),
    )
    session.add(claim)
    session.flush()
    return claim


def _sync_event_claim_counts(
    session: Session,
    event: Event,
    latest_claim: EventSourceClaim,
) -> None:
    latest_claim.event_id = event.id
    latest_claim.matched_event_id = event.id
    event.latest_source_claim_id = latest_claim.id
    session.flush()
    event.source_claim_count = int(
        session.scalar(
            select(func.count())
            .select_from(EventSourceClaim)
            .where(EventSourceClaim.event_id == event.id)
        )
        or 0
    )
    if latest_claim.id and event.source_claim_count == 0:
        event.source_claim_count = 1


def _add_group_member(
    session: Session,
    group: EventDuplicateGroup,
    event_id: int,
    source_claim_id: int | None,
    role: str,
    match_score: float,
    reason: str,
) -> None:
    exists = session.scalars(
        select(EventDuplicateGroupMember).where(
            EventDuplicateGroupMember.group_id == group.id,
            EventDuplicateGroupMember.event_id == event_id,
        )
    ).first()
    if exists:
        if source_claim_id and not exists.source_claim_id:
            exists.source_claim_id = source_claim_id
        return
    session.add(
        EventDuplicateGroupMember(
            group_id=group.id,
            event_id=event_id,
            source_claim_id=source_claim_id,
            role=role,
            match_score=match_score,
            reason_json=_json([reason]),
        )
    )


def _create_duplicate_group(
    session: Session,
    existing_event: Event,
    new_event: Event,
    claim: EventSourceClaim,
    reason: str,
    match_score: float,
) -> EventDuplicateGroup:
    group_key = stable_hash(
        "duplicate-review",
        weak_event_key_from_event(existing_event),
    )
    group = session.scalars(
        select(EventDuplicateGroup).where(EventDuplicateGroup.group_key == group_key)
    ).first()
    if group is None:
        group = EventDuplicateGroup(
            group_key=group_key,
            status="open",
            confidence="weak" if match_score < 0.7 else "medium",
            reason_json=_json([reason]),
        )
        session.add(group)
        session.flush()
    _add_group_member(
        session,
        group,
        existing_event.id,
        None,
        "possible_primary",
        match_score,
        reason,
    )
    _add_group_member(
        session,
        group,
        new_event.id,
        claim.id,
        "duplicate_candidate",
        match_score,
        reason,
    )
    existing_event.duplicate_status = "duplicate_candidate"
    existing_event.duplicate_candidate_group_id = group.id
    new_event.duplicate_status = "duplicate_candidate"
    new_event.duplicate_candidate_group_id = group.id
    claim.candidate_event_id = new_event.id
    return group


def weak_event_key_from_event(event: Event) -> str:
    title = normalize_dedupe_text(event.headliner or event.title)
    start = event.start_datetime.replace(second=0, microsecond=0).isoformat()
    return stable_hash("event-weak", title, start, "")


def upsert_event_from_candidate(
    session: Session,
    candidate: NormalizedEventCandidate,
    claim_input: SourceClaimInput,
    *,
    commit: bool = False,
) -> EventUpsertResult:
    """Create or update a normalized Concert event and preserve a source claim."""

    event_key, event_confidence = candidate_dedupe_key(candidate)
    claim_key, claim_confidence = _claim_key(candidate, claim_input)
    existing, match_reason, match_score = _find_existing_event(
        session,
        candidate,
        claim_key,
        event_key,
    )
    claim = _create_source_claim(
        session,
        candidate,
        claim_input,
        claim_key,
        claim_confidence,
        match_reason,
        match_score,
    )

    duplicate_group: EventDuplicateGroup | None = None
    changed_fields: list[dict[str, Any]] = []
    action: EventUpsertAction

    if existing is None:
        event = Event(**_candidate_event_kwargs(candidate, event_key, event_confidence))
        event.first_seen_at = utc_now()
        event.last_seen_at = utc_now()
        session.add(event)
        session.flush()
        action = (
            "cancelled"
            if event.event_lifecycle_status == "cancelled"
            else "created"
        )
    elif match_score < 0.7:
        event = Event(
            **_candidate_event_kwargs(
                candidate,
                stable_hash(event_key, claim.id),
                "weak",
            )
        )
        event.first_seen_at = utc_now()
        event.last_seen_at = utc_now()
        session.add(event)
        session.flush()
        action = "duplicate_candidate"
        duplicate_group = _create_duplicate_group(
            session,
            existing,
            event,
            claim,
            match_reason,
            match_score,
        )
    else:
        event = existing
        changed_fields = _update_existing_event(event, candidate)
        action = (
            "cancelled"
            if event.event_lifecycle_status == "cancelled"
            else "updated"
            if changed_fields
            else "skipped"
        )

    _sync_event_claim_counts(session, event, claim)
    from app.services.artist_service import link_event_to_artists
    from app.services.genre_service import normalize_event_music_fields

    normalize_event_music_fields(event)
    link_event_to_artists(session, event.id, commit=False)
    session.add(event)
    session.add(claim)
    if commit:
        session.commit()
        session.refresh(event)
        session.refresh(claim)
    return EventUpsertResult(
        event=event,
        source_claim=claim,
        action=action,
        changed_fields=changed_fields,
        duplicate_group=duplicate_group,
    )


def source_claims_for_event(session: Session, event_id: int) -> list[EventSourceClaim]:
    return list(
        session.scalars(
            select(EventSourceClaim)
            .where(EventSourceClaim.event_id == event_id)
            .order_by(EventSourceClaim.seen_at.desc(), EventSourceClaim.id.desc())
        ).all()
    )


def list_duplicate_group_views(session: Session) -> list[DuplicateGroupView]:
    groups = list(
        session.scalars(
            select(EventDuplicateGroup)
            .options(selectinload(EventDuplicateGroup.members))
            .order_by(
                EventDuplicateGroup.updated_at.desc(),
                EventDuplicateGroup.id.desc(),
            )
        ).all()
    )
    return [duplicate_group_view(session, group.id) for group in groups]


def duplicate_group_view(
    session: Session,
    group_id: int,
) -> DuplicateGroupView:
    group = session.scalars(
        select(EventDuplicateGroup)
        .options(selectinload(EventDuplicateGroup.members))
        .where(EventDuplicateGroup.id == group_id)
    ).first()
    if group is None:
        raise ValueError("Duplicate group not found.")
    members: list[DuplicateMemberView] = []
    for member in sorted(group.members, key=lambda item: item.id):
        event = session.get(Event, member.event_id)
        claims = source_claims_for_event(session, member.event_id)
        members.append(
            DuplicateMemberView(
                member=member,
                event=event,
                source_claims=claims,
            )
        )
    return DuplicateGroupView(group=group, members=members)


def merge_duplicate_group(
    session: Session,
    group_id: int,
    primary_event_id: int,
    admin_user: str,
) -> DuplicateGroupView:
    view = duplicate_group_view(session, group_id)
    primary = session.get(Event, primary_event_id)
    if primary is None:
        raise ValueError("Primary event not found.")
    changed: list[dict[str, Any]] = []
    for member in view.members:
        duplicate = member.event
        if duplicate is None or duplicate.id == primary.id:
            continue
        for field_name in EVENT_FIELD_NAMES:
            if field_name in {"raw_event_json", "crawl_run_id"}:
                continue
            incoming = getattr(duplicate, field_name, None)
            if incoming is None or incoming == "":
                continue
            if getattr(primary, field_name, None) in {None, ""}:
                setattr(primary, field_name, incoming)
                changed.append({"field": field_name, "from_event_id": duplicate.id})
        for claim in member.source_claims:
            claim.event_id = primary.id
            claim.matched_event_id = primary.id
        duplicate.duplicate_status = "merged"
        duplicate.canonical_event_id = primary.id
        duplicate.event_lifecycle_status = "merged"
    primary.duplicate_status = "none"
    primary.canonical_event_id = None
    primary.changed_fields_json = _json(changed)
    primary.last_update_summary_json = _json(
        [{"at": utc_now().isoformat(), "action": "merge", "admin": admin_user}]
    )
    primary.update_count += 1
    primary.last_significant_change_at = utc_now()
    view.group.status = "merged"
    view.group.updated_at = utc_now()
    session.add(view.group)
    session.commit()
    return duplicate_group_view(session, group_id)


def keep_duplicate_group_separate(
    session: Session,
    group_id: int,
    admin_user: str,
) -> DuplicateGroupView:
    view = duplicate_group_view(session, group_id)
    for member in view.members:
        if member.event:
            member.event.duplicate_status = "kept_separate"
            member.event.duplicate_candidate_group_id = group_id
            member.event.last_update_summary_json = _json(
                [
                    {
                        "at": utc_now().isoformat(),
                        "action": "keep_separate",
                        "admin": admin_user,
                    }
                ]
            )
    view.group.status = "kept_separate"
    view.group.updated_at = utc_now()
    session.commit()
    return duplicate_group_view(session, group_id)


def reject_duplicate_group(
    session: Session,
    group_id: int,
    admin_user: str,
) -> DuplicateGroupView:
    view = duplicate_group_view(session, group_id)
    for member in view.members:
        if member.event:
            member.event.duplicate_status = "rejected_duplicate"
            member.event.duplicate_candidate_group_id = group_id
            member.event.last_update_summary_json = _json(
                [
                    {
                        "at": utc_now().isoformat(),
                        "action": "reject_duplicate_candidate",
                        "admin": admin_user,
                    }
                ]
            )
    view.group.status = "rejected"
    view.group.updated_at = utc_now()
    session.commit()
    return duplicate_group_view(session, group_id)
