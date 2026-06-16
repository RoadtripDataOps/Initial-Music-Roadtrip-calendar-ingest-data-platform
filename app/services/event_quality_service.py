from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Event, EventArtist, EventSourceClaim, ImageCandidate, utc_now
from app.services.app_feed_service import event_publish_readiness
from app.services.event_photo_rescue_service import run_event_photo_rescue

EventQualityBulkAction = Literal[
    "photo_rescue",
    "needs_image_review",
    "recompute_quality",
    "duplicate_review",
]

GOOD_TICKET_CLASSIFICATIONS = {
    "direct",
    "event_specific",
    "provider_event",
    "ticketing_provider",
    "repaired_event_specific",
}
BAD_TICKET_CLASSIFICATIONS = {
    "bad",
    "broken",
    "generic",
    "generic_platform",
    "generic_venue",
    "generic_artist",
    "platform_generic_or_app",
    "tracking_or_affiliate_only",
    "session_or_cart",
    "homepage",
    "unknown",
}
IMAGE_PENDING_STATUSES = {
    "needs_approval",
    "pending_approval",
    "selected_pending_approval",
    "needs_review",
}
IMAGE_BLOCKED_STATUSES = {"blocked", "hard_blocked", "rejected"}
GENERIC_IMAGE_ROLES = {"generic_crowd", "stock_placeholder", "logo", "unknown"}
POSTER_IMAGE_ROLES = {"poster", "flyer", "admat"}
LOW_MUSIC_RELEVANCE_THRESHOLD = 55.0
RECENT_UPDATE_WINDOW_DAYS = 7


@dataclass(frozen=True)
class EventQualityBucket:
    key: str
    label: str
    count: int


@dataclass(frozen=True)
class EventQualityFilters:
    bucket: str | None = None
    search: str | None = None
    limit: int = 100
    offset: int = 0


@dataclass(frozen=True)
class EventQualityRow:
    event: Event
    event_quality_score: int
    app_feed_readiness_score: int
    app_feed_ready: bool
    flags: set[str]
    source_providers: list[str]
    selected_candidate: ImageCandidate | None
    image_status_label: str
    ticket_status_label: str
    dedupe_status_label: str
    source_claim_count: int


@dataclass(frozen=True)
class EventQualityWorkbench:
    rows: list[EventQualityRow]
    buckets: list[EventQualityBucket]
    filters: EventQualityFilters
    total_count: int


@dataclass(frozen=True)
class EventQualityDashboardCounts:
    missing_image_count: int
    missing_ticket_count: int
    duplicate_risk_count: int
    not_app_feed_ready_count: int
    app_feed_ready_count: int


BUCKET_LABELS: tuple[tuple[str, str], ...] = (
    ("missing_image", "Missing image"),
    ("selected_image_pending_approval", "Selected image pending approval"),
    ("generic_provider_image_blocked", "Generic/provider image blocked"),
    ("poster_flyer_admat_blocked", "Poster/flyer/admat blocked"),
    ("social_graphic_evidence_only", "Social graphic evidence only"),
    ("missing_ticket_link", "Missing ticket link"),
    ("bad_generic_ticket_link", "Bad/generic ticket link"),
    ("missing_venue", "Missing venue"),
    ("missing_coordinates", "Missing coordinates"),
    ("duplicate_candidate", "Duplicate candidate"),
    ("weak_dedupe_confidence", "Weak dedupe confidence"),
    ("low_music_relevance", "Low music relevance"),
    ("missing_artist_headliner", "Missing artist/headliner"),
    ("missing_genre", "Missing genre"),
    ("not_app_feed_ready", "Not app-feed ready"),
    ("recently_updated", "Recently updated"),
    ("multiple_source_claims", "Multiple source claims"),
)


def _clean(value: str | None) -> str:
    return (value or "").strip()


def _json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _bounded_limit(value: int) -> int:
    return max(1, min(value, 250))


def _bounded_offset(value: int) -> int:
    return max(0, value)


def _selected_candidate(event: Event) -> ImageCandidate | None:
    if event.selected_image_candidate_id is None:
        return None
    return next(
        (
            candidate
            for candidate in event.image_candidates
            if candidate.id == event.selected_image_candidate_id
        ),
        None,
    )


def _source_provider_label(claim: EventSourceClaim) -> str:
    return (
        _clean(claim.ingestion_provider)
        or _clean(claim.upstream_event_source)
        or _clean(claim.source_name)
        or _clean(claim.source_type)
        or "unknown"
    )


def _source_providers(event: Event) -> list[str]:
    labels = {
        _clean(event.ingestion_provider),
        _clean(event.api_provider_key),
        _clean(event.upstream_event_source),
        _clean(event.source_type),
    }
    labels.update(_source_provider_label(claim) for claim in event.source_claims)
    return sorted(label for label in labels if label)


def _source_claim_count(event: Event) -> int:
    return max(event.source_claim_count or 0, len(event.source_claims))


def _ticket_classification(event: Event) -> str:
    return _clean(event.ticket_link_classification).lower()


def _has_ticket_link(event: Event) -> bool:
    return bool(_clean(event.recommended_ticket_link) or _clean(event.tickets_link))


def _bad_ticket_link(event: Event) -> bool:
    classification = _ticket_classification(event)
    if not classification:
        return False
    if classification in GOOD_TICKET_CLASSIFICATIONS:
        return False
    if classification in BAD_TICKET_CLASSIFICATIONS:
        return True
    if event.ticket_link_quality_score is not None:
        return event.ticket_link_quality_score < 55
    return "generic" in classification or "bad" in classification


def _has_selected_image(event: Event) -> bool:
    return bool(_clean(event.selected_main_image_url))


def _has_any_image(event: Event) -> bool:
    return bool(_clean(event.selected_main_image_url) or _clean(event.main_image_url))


def _selected_image_pending(event: Event, candidate: ImageCandidate | None) -> bool:
    event_statuses = {
        _clean(event.image_status).lower(),
        _clean(event.image_clearance_status).lower(),
    }
    candidate_statuses = set()
    if candidate is not None:
        candidate_statuses = {
            _clean(candidate.candidate_status).lower(),
            _clean(candidate.clearance_status).lower(),
        }
    return bool((event_statuses | candidate_statuses) & IMAGE_PENDING_STATUSES)


def _selected_image_blocked(event: Event, candidate: ImageCandidate | None) -> bool:
    event_statuses = {
        _clean(event.image_status).lower(),
        _clean(event.image_clearance_status).lower(),
        _clean(event.image_role).lower(),
    }
    candidate_statuses = set()
    if candidate is not None:
        candidate_statuses = {
            _clean(candidate.candidate_status).lower(),
            _clean(candidate.clearance_status).lower(),
            _clean(candidate.image_role).lower(),
            _clean(candidate.rescue_source).lower(),
        }
    return bool((event_statuses | candidate_statuses) & IMAGE_BLOCKED_STATUSES)


def _generic_provider_image_blocked(
    event: Event,
    candidate: ImageCandidate | None,
) -> bool:
    if _selected_image_blocked(event, candidate):
        return True
    if _clean(event.image_role).lower() in GENERIC_IMAGE_ROLES:
        return True
    candidates = event.image_candidates
    return any(
        candidate_item.generic_detection_score >= 70
        or _clean(candidate_item.image_role).lower() in GENERIC_IMAGE_ROLES
        or _clean(candidate_item.rescue_source).lower()
        in {"provider_promo_image", "unknown"}
        and not candidate_item.can_be_final_image
        for candidate_item in candidates
    )


def _poster_flyer_admat_blocked(event: Event) -> bool:
    if _clean(event.image_role).lower() in POSTER_IMAGE_ROLES:
        return True
    return any(
        _clean(candidate.image_role).lower() in POSTER_IMAGE_ROLES
        or candidate.poster_flyer_score >= 65
        or candidate.admat_score >= 65
        or (
            _clean(candidate.rescue_source).lower() == "provider_promo_image"
            and not candidate.can_be_final_image
        )
        for candidate in event.image_candidates
    )


def _social_graphic_evidence_only(event: Event) -> bool:
    return any(
        candidate.source_evidence_only
        and (
            _clean(candidate.rescue_source).lower() == "social_graphic_reference"
            or _clean(candidate.image_role).lower() == "social_screenshot"
        )
        for candidate in event.image_candidates
    )


def _missing_venue(event: Event) -> bool:
    return event.venue is None


def _missing_coordinates(event: Event) -> bool:
    return (
        event.venue is None
        or event.venue.latitude is None
        or event.venue.longitude is None
    )


def _duplicate_candidate(event: Event) -> bool:
    status = _clean(event.duplicate_status).lower()
    return status not in {"", "none", "unique", "resolved", "kept_separate"}


def _weak_dedupe_confidence(event: Event) -> bool:
    confidence = _clean(event.dedupe_confidence).lower()
    return confidence in {"", "weak", "medium", "low"}


def _missing_artist_headliner(event: Event) -> bool:
    return not _clean(event.headliner) and not event.artist_links


def _missing_genre(event: Event) -> bool:
    return not (
        _clean(event.genre)
        or _clean(event.normalized_genre)
        or event.normalized_genres
        or _clean(event.music_category)
    )


def _low_music_relevance(event: Event) -> bool:
    if event.music_relevance_score is not None:
        return event.music_relevance_score < LOW_MUSIC_RELEVANCE_THRESHOLD
    return bool(event.music_relevance_flags) or _missing_genre(event)


def _recently_updated(event: Event) -> bool:
    comparison = _utc(event.last_significant_change_at) or _utc(event.updated_at)
    if comparison is None:
        return False
    return utc_now() - comparison <= timedelta(days=RECENT_UPDATE_WINDOW_DAYS)


def event_quality_flags(event: Event) -> set[str]:
    selected = _selected_candidate(event)
    readiness_score, blockers, readiness_flags = event_publish_readiness(event)
    flags: set[str] = set(blockers)
    flags.update(readiness_flags)

    if not _has_any_image(event):
        flags.add("missing_image")
    if _selected_image_pending(event, selected):
        flags.add("selected_image_pending_approval")
    if _generic_provider_image_blocked(event, selected):
        flags.add("generic_provider_image_blocked")
    if _poster_flyer_admat_blocked(event):
        flags.add("poster_flyer_admat_blocked")
    if _social_graphic_evidence_only(event):
        flags.add("social_graphic_evidence_only")
    if not _has_ticket_link(event):
        flags.add("missing_ticket_link")
    if _bad_ticket_link(event):
        flags.add("bad_generic_ticket_link")
    if _missing_venue(event):
        flags.add("missing_venue")
    if _missing_coordinates(event):
        flags.add("missing_coordinates")
    if _duplicate_candidate(event):
        flags.add("duplicate_candidate")
    if _weak_dedupe_confidence(event):
        flags.add("weak_dedupe_confidence")
    if _low_music_relevance(event):
        flags.add("low_music_relevance")
    if _missing_artist_headliner(event):
        flags.add("missing_artist_headliner")
    if _missing_genre(event):
        flags.add("missing_genre")
    if not app_feed_ready_from_readiness(event, readiness_score, blockers):
        flags.add("not_app_feed_ready")
    if _recently_updated(event):
        flags.add("recently_updated")
    if _source_claim_count(event) > 1:
        flags.add("multiple_source_claims")
    return flags


def app_feed_ready_from_readiness(
    event: Event,
    readiness_score: int,
    blockers: list[str],
) -> bool:
    return (
        event.publish_status in {"approved", "published"}
        and readiness_score >= 80
        and not blockers
        and not _selected_image_pending(event, _selected_candidate(event))
    )


def compute_event_quality_score(event: Event) -> int:
    selected = _selected_candidate(event)
    readiness_score, blockers, _ = event_publish_readiness(event)
    score = 0
    score += 8 if _clean(event.title) else 0
    score += 8 if event.start_datetime is not None else 0
    score += 8 if not _missing_venue(event) else 0
    score += 7 if not _missing_coordinates(event) or (
        event.venue is not None and _clean(event.venue.address)
    ) else 0
    score += 7 if _has_ticket_link(event) else 0
    score += 8 if _has_ticket_link(event) and not _bad_ticket_link(event) else 0
    score += 9 if _has_selected_image(event) else 0
    score += 8 if _has_any_image(event) and not (
        _generic_provider_image_blocked(event, selected)
        or _poster_flyer_admat_blocked(event)
        or _social_graphic_evidence_only(event)
    ) else 0
    score += 7 if _has_any_image(event) and not _selected_image_pending(
        event,
        selected,
    ) else 0
    score += 7 if not _missing_artist_headliner(event) else 0
    score += 7 if not _low_music_relevance(event) else 0
    score += 7 if not _duplicate_candidate(event) else 0
    score += 4 if _source_claim_count(event) > 0 else 0
    score += 5 if app_feed_ready_from_readiness(event, readiness_score, blockers) else 0
    return min(100, max(0, score))


def _ticket_status_label(event: Event) -> str:
    if not _has_ticket_link(event):
        return "Missing"
    if _bad_ticket_link(event):
        return event.ticket_link_classification or "Needs review"
    return event.ticket_link_classification or "Present"


def _image_status_label(event: Event, selected: ImageCandidate | None) -> str:
    if not _has_any_image(event):
        return "Missing"
    if _selected_image_pending(event, selected):
        return "Pending approval"
    if _generic_provider_image_blocked(event, selected):
        return "Blocked generic/provider"
    if _poster_flyer_admat_blocked(event):
        return "Poster/flyer/admat"
    if _social_graphic_evidence_only(event):
        return "Evidence only"
    return event.image_status or "Present"


def _dedupe_status_label(event: Event) -> str:
    status = _clean(event.duplicate_status) or "none"
    if event.duplicate_candidate_group_id:
        return f"{status} / group {event.duplicate_candidate_group_id}"
    return status


def event_quality_row(event: Event) -> EventQualityRow:
    selected = _selected_candidate(event)
    readiness_score, blockers, _ = event_publish_readiness(event)
    app_ready = app_feed_ready_from_readiness(event, readiness_score, blockers)
    return EventQualityRow(
        event=event,
        event_quality_score=compute_event_quality_score(event),
        app_feed_readiness_score=readiness_score,
        app_feed_ready=app_ready,
        flags=event_quality_flags(event),
        source_providers=_source_providers(event),
        selected_candidate=selected,
        image_status_label=_image_status_label(event, selected),
        ticket_status_label=_ticket_status_label(event),
        dedupe_status_label=_dedupe_status_label(event),
        source_claim_count=_source_claim_count(event),
    )


def _event_stmt() -> Select[tuple[Event]]:
    return (
        select(Event)
        .options(
            selectinload(Event.venue),
            selectinload(Event.source_claims),
            selectinload(Event.image_candidates),
            selectinload(Event.artist_links).selectinload(EventArtist.artist),
        )
        .where(Event.category == "Concert")
        .where(Event.record_type == "event")
        .order_by(Event.start_datetime.asc(), Event.id.asc())
    )


def _matches_search(row: EventQualityRow, search: str | None) -> bool:
    if not search:
        return True
    needle = search.strip().lower()
    if not needle:
        return True
    event = row.event
    haystack = " ".join(
        [
            event.title,
            event.headliner or "",
            event.venue.display_name if event.venue else "",
            event.venue.city if event.venue and event.venue.city else "",
            event.venue.state if event.venue and event.venue.state else "",
            " ".join(row.source_providers),
        ]
    ).lower()
    return needle in haystack


def list_event_quality_rows(
    session: Session,
    filters: EventQualityFilters | None = None,
) -> list[EventQualityRow]:
    filters = filters or EventQualityFilters()
    events = list(session.scalars(_event_stmt()).all())
    rows = [event_quality_row(event) for event in events]
    if filters.bucket:
        rows = [row for row in rows if filters.bucket in row.flags]
    rows = [row for row in rows if _matches_search(row, filters.search)]
    start = _bounded_offset(filters.offset)
    stop = start + _bounded_limit(filters.limit)
    return rows[start:stop]


def event_quality_buckets(session: Session) -> list[EventQualityBucket]:
    rows = [event_quality_row(event) for event in session.scalars(_event_stmt()).all()]
    return [
        EventQualityBucket(
            key=key,
            label=label,
            count=sum(1 for row in rows if key in row.flags),
        )
        for key, label in BUCKET_LABELS
    ]


def event_quality_workbench(
    session: Session,
    filters: EventQualityFilters | None = None,
) -> EventQualityWorkbench:
    filters = filters or EventQualityFilters()
    rows = list_event_quality_rows(session, filters)
    total_count = len(
        [
            event_quality_row(event)
            for event in session.scalars(_event_stmt()).all()
            if (not filters.bucket or filters.bucket in event_quality_flags(event))
        ]
    )
    return EventQualityWorkbench(
        rows=rows,
        buckets=event_quality_buckets(session),
        filters=filters,
        total_count=total_count,
    )


def event_quality_dashboard_counts(session: Session) -> EventQualityDashboardCounts:
    rows = [event_quality_row(event) for event in session.scalars(_event_stmt()).all()]
    return EventQualityDashboardCounts(
        missing_image_count=sum("missing_image" in row.flags for row in rows),
        missing_ticket_count=sum("missing_ticket_link" in row.flags for row in rows),
        duplicate_risk_count=sum("duplicate_candidate" in row.flags for row in rows),
        not_app_feed_ready_count=sum("not_app_feed_ready" in row.flags for row in rows),
        app_feed_ready_count=sum(row.app_feed_ready for row in rows),
    )


def recompute_event_quality(session: Session, event_ids: list[int]) -> int:
    count = 0
    for event_id in event_ids:
        event = session.get(Event, event_id)
        if event is None or event.category != "Concert" or event.record_type != "event":
            continue
        row = event_quality_row(event)
        event.publish_ready_score = float(row.app_feed_readiness_score)
        event.publish_blockers_json = json.dumps(sorted(row.flags))
        count += 1
    session.commit()
    return count


def mark_events_needs_image_review(session: Session, event_ids: list[int]) -> int:
    count = 0
    for event_id in event_ids:
        event = session.get(Event, event_id)
        if event is None or event.category != "Concert" or event.record_type != "event":
            continue
        event.image_status = "needs_review"
        if event.selected_image_candidate_id is not None:
            candidate = session.get(ImageCandidate, event.selected_image_candidate_id)
            if candidate is not None:
                candidate.candidate_status = "needs_review"
        count += 1
    session.commit()
    return count


def run_photo_rescue_for_events(session: Session, event_ids: list[int]) -> int:
    count = 0
    for event_id in event_ids:
        event = session.get(Event, event_id)
        if event is None or event.category != "Concert" or event.record_type != "event":
            continue
        run_event_photo_rescue(session, event_id, commit=False)
        count += 1
    session.commit()
    return count


def send_events_to_duplicate_review_if_suspicious(
    session: Session,
    event_ids: list[int],
) -> int:
    count = 0
    for event_id in event_ids:
        event = session.get(Event, event_id)
        if event is None or event.category != "Concert" or event.record_type != "event":
            continue
        row = event_quality_row(event)
        if not (
            "weak_dedupe_confidence" in row.flags
            or "duplicate_candidate" in row.flags
            or event.duplicate_candidate_group_id is not None
        ):
            continue
        event.duplicate_status = "duplicate_candidate"
        event.last_update_summary_json = json.dumps(
            [
                {
                    "at": utc_now().isoformat(),
                    "action": "sent_to_duplicate_review_from_event_quality",
                }
            ]
        )
        count += 1
    session.commit()
    return count


def apply_event_quality_bulk_action(
    session: Session,
    event_ids: list[int],
    action: EventQualityBulkAction,
) -> int:
    if action == "photo_rescue":
        return run_photo_rescue_for_events(session, event_ids)
    if action == "needs_image_review":
        return mark_events_needs_image_review(session, event_ids)
    if action == "recompute_quality":
        return recompute_event_quality(session, event_ids)
    if action == "duplicate_review":
        return send_events_to_duplicate_review_if_suspicious(session, event_ids)
    raise ValueError(f"Unsupported event quality action: {action}")
