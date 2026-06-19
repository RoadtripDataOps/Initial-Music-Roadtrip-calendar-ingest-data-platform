from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time
from urllib.parse import quote_plus

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    ApiFeedRecord,
    Event,
    EventArtist,
    PoiCandidate,
    SourceExtractedEventCandidate,
    StagedEvent,
)
from app.services.event_quality_service import event_quality_row

LOGO_ASSET_MARKERS = (
    "music-roadtrip-logo",
    "/static/images/music-roadtrip-logo",
)
BLOCKED_STATUSES = {"rejected", "blocked", "quarantined", "expired", "archived"}
NEEDS_REVIEW_STATUSES = {
    "pending",
    "pending_review",
    "needs_review",
    "needs_enrichment",
    "held",
    "draft",
}
ALLOWED_PER_PAGE = (25, 50, 100)
DEFAULT_PER_PAGE = 25


@dataclass(frozen=True)
class EventReviewFilters:
    tab: str = "all"
    search: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    location_text: str | None = None
    radius_miles: float | None = None
    latitude: float | None = None
    longitude: float | None = None
    city: str | None = None
    state: str | None = None
    genre: str | None = None
    source_type: str | None = None
    provider: str | None = None
    review_status: str | None = None
    image_status: str | None = None
    ticket_status: str | None = None
    venue_status: str | None = None
    duplicate_status: str | None = None
    app_feed_readiness: str | None = None
    quality_issue: str | None = None
    sort: str = "start_datetime"
    sort_direction: str = "asc"
    page: int = 1
    per_page: int = DEFAULT_PER_PAGE
    show_full_descriptions: bool = False

    @property
    def has_radius(self) -> bool:
        return (
            self.radius_miles is not None
            and self.latitude is not None
            and self.longitude is not None
        )


@dataclass(frozen=True)
class EventReviewRow:
    row_key: str
    record_type: str
    record_label: str
    object_id: int
    status_label: str
    review_status: str
    title: str
    start_datetime: datetime | None
    venue_name: str
    address: str
    city: str
    state: str
    latitude: float | None
    longitude: float | None
    description: str
    genre: str
    ticket_url: str
    ticket_classification: str
    ticket_status: str
    website_url: str
    source_label: str
    source_type: str
    provider: str
    source_badges: tuple[str, ...]
    source_claim_count: int
    image_url: str
    image_status: str
    image_badges: tuple[str, ...]
    ticket_badges: tuple[str, ...]
    venue_badges: tuple[str, ...]
    quality_flags: tuple[str, ...]
    duplicate_status: str
    app_feed_ready: bool
    app_feed_readiness: str
    detail_url: str
    preview_url: str
    app_json_url: str
    photo_rescue_action_url: str
    image_candidates_url: str
    source_claims_url: str
    duplicate_group_url: str
    poi_candidates_url: str
    approve_action_url: str
    hold_action_url: str
    reject_action_url: str

    @property
    def needs_review(self) -> bool:
        status = self.review_status.lower()
        return (
            status in NEEDS_REVIEW_STATUSES
            or self.image_status in {"missing", "needs_approval", "generic_blocked"}
            or self.ticket_status in {"missing", "bad"}
            or "not_app_feed_ready" in self.quality_flags
            or bool(self.quality_flags)
        )


@dataclass(frozen=True)
class EventReviewTab:
    key: str
    label: str
    count: int


@dataclass(frozen=True)
class EventReviewPage:
    rows: list[EventReviewRow]
    tabs: list[EventReviewTab]
    filters: EventReviewFilters
    total_count: int
    page: int
    per_page: int
    page_count: int
    has_previous: bool
    has_next: bool


@dataclass(frozen=True)
class EventReviewDashboardCounts:
    events_needing_images: int
    events_needing_ticket_links: int
    pending_api_feed_records: int
    pending_extracted_candidates: int
    events_ready_for_app_feed: int
    poi_candidates_from_events: int


def event_review_dashboard_counts(session: Session) -> EventReviewDashboardCounts:
    rows = _normalized_event_rows(session)
    pending_api = int(
        session.scalar(
            select(func.count(ApiFeedRecord.id)).where(
                ApiFeedRecord.review_status == "pending_review",
            )
        )
        or 0
    )
    pending_extracted = int(
        session.scalar(
            select(func.count(SourceExtractedEventCandidate.id)).where(
                SourceExtractedEventCandidate.review_status == "pending_review",
            )
        )
        or 0
    )
    poi_candidates = int(
        session.scalar(
            select(func.count(PoiCandidate.id)).where(
                or_(
                    PoiCandidate.api_feed_record_id.is_not(None),
                    PoiCandidate.extracted_event_candidate_id.is_not(None),
                    PoiCandidate.crawl_run_id.is_not(None),
                )
            )
        )
        or 0
    )
    return EventReviewDashboardCounts(
        events_needing_images=sum(row.image_status == "missing" for row in rows),
        events_needing_ticket_links=sum(row.ticket_status == "missing" for row in rows),
        pending_api_feed_records=pending_api,
        pending_extracted_candidates=pending_extracted,
        events_ready_for_app_feed=sum(row.app_feed_ready for row in rows),
        poi_candidates_from_events=poi_candidates,
    )


def event_review_workbench(
    session: Session,
    filters: EventReviewFilters | None = None,
) -> EventReviewPage:
    filters = _normalize_filters(filters or EventReviewFilters())
    rows = _all_rows(session)
    rows = _hide_blocked_rows_by_default(rows, filters)
    tabs = _tabs(rows)
    rows = [row for row in rows if _matches_filters(row, filters)]
    _sort_rows(rows, filters)

    total_count = len(rows)
    per_page = _bounded_per_page(filters.per_page)
    page_count = max(1, math.ceil(total_count / per_page))
    page = min(max(1, filters.page), page_count)
    start = (page - 1) * per_page
    stop = start + per_page
    return EventReviewPage(
        rows=rows[start:stop],
        tabs=tabs,
        filters=filters,
        total_count=total_count,
        page=page,
        per_page=per_page,
        page_count=page_count,
        has_previous=page > 1,
        has_next=page < page_count,
    )


def _all_rows(session: Session) -> list[EventReviewRow]:
    poi_lookup = _poi_candidate_lookup(session)
    rows: list[EventReviewRow] = []
    rows.extend(_normalized_event_rows(session, poi_lookup))
    rows.extend(_api_feed_record_rows(session, poi_lookup))
    rows.extend(_extracted_candidate_rows(session, poi_lookup))
    rows.extend(_staged_event_rows(session))
    return rows


def _normalized_event_rows(
    session: Session,
    poi_lookup: dict[str, list[PoiCandidate]] | None = None,
) -> list[EventReviewRow]:
    poi_lookup = poi_lookup or {}
    statement = (
        select(Event)
        .options(
            selectinload(Event.source),
            selectinload(Event.crawl_run),
            selectinload(Event.venue),
            selectinload(Event.source_claims),
            selectinload(Event.image_candidates),
            selectinload(Event.artist_links).selectinload(EventArtist.artist),
        )
        .where(Event.category == "Concert")
        .where(Event.record_type == "event")
        .order_by(Event.start_datetime.asc(), Event.id.asc())
    )
    return [
        _event_row(event, poi_lookup)
        for event in session.scalars(statement).all()
    ]


def _api_feed_record_rows(
    session: Session,
    poi_lookup: dict[str, list[PoiCandidate]],
) -> list[EventReviewRow]:
    statement = (
        select(ApiFeedRecord)
        .options(selectinload(ApiFeedRecord.run))
        .where(ApiFeedRecord.category == "Concert")
        .where(ApiFeedRecord.record_type == "event")
        .order_by(ApiFeedRecord.created_at.desc(), ApiFeedRecord.id.desc())
    )
    return [
        _api_record_row(record, poi_lookup)
        for record in session.scalars(statement).all()
    ]


def _extracted_candidate_rows(
    session: Session,
    poi_lookup: dict[str, list[PoiCandidate]],
) -> list[EventReviewRow]:
    statement = (
        select(SourceExtractedEventCandidate)
        .options(selectinload(SourceExtractedEventCandidate.crawl_run))
        .order_by(
            SourceExtractedEventCandidate.created_at.desc(),
            SourceExtractedEventCandidate.id.desc(),
        )
    )
    return [
        _extracted_row(candidate, poi_lookup)
        for candidate in session.scalars(statement).all()
    ]


def _staged_event_rows(session: Session) -> list[EventReviewRow]:
    statement = (
        select(StagedEvent)
        .where(StagedEvent.category == "Concert")
        .order_by(StagedEvent.created_at.desc(), StagedEvent.id.desc())
    )
    return [_staged_row(row) for row in session.scalars(statement).all()]


def _event_row(
    event: Event,
    poi_lookup: dict[str, list[PoiCandidate]],
) -> EventReviewRow:
    quality = event_quality_row(event)
    flags = tuple(sorted(quality.flags))
    venue = event.venue
    image_url = _safe_image_url(event.selected_main_image_url or event.main_image_url)
    image_status, image_badges = _image_status_from_event(
        image_url,
        quality.image_status_label,
        flags,
    )
    ticket_url = _clean(event.recommended_ticket_link) or _clean(event.tickets_link)
    ticket_status, ticket_badges = _ticket_status(
        ticket_url,
        event.ticket_link_classification,
        flags,
    )
    source_badges = _source_badges(
        event.source_type,
        event.ingestion_provider or event.api_provider_key,
        event.upstream_event_source,
    )
    source_label = (
        event.source.organization_name
        if event.source
        else _provider_display(event.ingestion_provider or event.api_provider_key)
    )
    source_label = source_label or event.source_type or "Unknown"
    venue_badges = _venue_badges(
        venue_name=venue.display_name if venue else event.location_text,
        latitude=venue.latitude if venue else None,
        longitude=venue.longitude if venue else None,
        candidates=poi_lookup.get(f"api:{event.api_feed_record_id}", []),
    )
    return EventReviewRow(
        row_key=f"event-{event.id}",
        record_type="normalized_event",
        record_label="Normalized Event",
        object_id=event.id,
        status_label=event.publish_status.replace("_", " ").title(),
        review_status=event.publish_status,
        title=event.title,
        start_datetime=event.start_datetime,
        venue_name=venue.display_name if venue else _clean(event.location_text),
        address=_address(
            venue.address if venue else None,
            venue.city if venue else None,
            venue.state if venue else None,
        ),
        city=_clean(venue.city if venue else None),
        state=_clean(venue.state if venue else None),
        latitude=venue.latitude if venue else None,
        longitude=venue.longitude if venue else None,
        description=_clean(event.description),
        genre=_clean(event.normalized_genre)
        or _clean(event.genre)
        or _clean(event.music_category)
        or ", ".join(event.normalized_genres),
        ticket_url=ticket_url,
        ticket_classification=_clean(event.ticket_link_classification),
        ticket_status=ticket_status,
        website_url=_clean(event.source_url),
        source_label=source_label,
        source_type=event.source_type,
        provider=_clean(event.ingestion_provider)
        or _clean(event.api_provider_key)
        or _clean(event.source_type),
        source_badges=source_badges,
        source_claim_count=quality.source_claim_count,
        image_url=image_url,
        image_status=image_status,
        image_badges=image_badges,
        ticket_badges=ticket_badges,
        venue_badges=venue_badges,
        quality_flags=flags,
        duplicate_status=event.duplicate_status,
        app_feed_ready=quality.app_feed_ready,
        app_feed_readiness="ready" if quality.app_feed_ready else "not_ready",
        detail_url=f"/admin/events/{event.id}",
        preview_url=f"/preview/events/{event.id}",
        app_json_url=(
            f"/admin/app-feed/events.json?event_id={event.id}"
            "&include_needs_approval=true"
        ),
        photo_rescue_action_url=f"/admin/events/{event.id}/photo-rescue",
        image_candidates_url=f"/admin/image-candidates?event_id={event.id}",
        source_claims_url=f"/admin/events/{event.id}#source-claims",
        duplicate_group_url=(
            f"/admin/duplicate-events/{event.duplicate_candidate_group_id}"
            if event.duplicate_candidate_group_id
            else ""
        ),
        poi_candidates_url=_poi_candidates_url(venue.display_name if venue else ""),
        approve_action_url="",
        hold_action_url="",
        reject_action_url="",
    )


def _api_record_row(
    record: ApiFeedRecord,
    poi_lookup: dict[str, list[PoiCandidate]],
) -> EventReviewRow:
    image_url = _safe_image_url(record.main_image_url)
    image_status, image_badges = _image_status_from_simple_url(image_url)
    ticket_url = _clean(record.recommended_ticket_link) or _clean(record.tickets_link)
    flags = tuple(sorted(record.quality_flags + record.mapping_warnings))
    ticket_status, ticket_badges = _ticket_status(
        ticket_url,
        record.ticket_link_classification,
        flags,
    )
    provider = record.ingestion_provider or record.provider_key
    candidates = poi_lookup.get(f"api:{record.id}", [])
    return EventReviewRow(
        row_key=f"api-{record.id}",
        record_type="api_feed_record",
        record_label="API Feed Record",
        object_id=record.id,
        status_label=record.review_status.replace("_", " ").title(),
        review_status=record.review_status,
        title=record.event_name or "Untitled API record",
        start_datetime=record.start_datetime,
        venue_name=_clean(record.venue_name),
        address=_address(record.venue_address, record.city, record.state),
        city=_clean(record.city),
        state=_clean(record.state),
        latitude=record.latitude,
        longitude=record.longitude,
        description=_clean(record.description),
        genre=_clean(record.normalized_genre)
        or _clean(record.provider_genre)
        or _clean(record.music_category),
        ticket_url=ticket_url,
        ticket_classification=_clean(record.ticket_link_classification),
        ticket_status=ticket_status,
        website_url=_clean(record.event_url) or _clean(record.source_url),
        source_label=_provider_display(provider),
        source_type="api_feed",
        provider=provider,
        source_badges=_source_badges(
            "api_feed",
            provider,
            record.upstream_event_source,
        ),
        source_claim_count=1 if record.created_event_id else 0,
        image_url=image_url,
        image_status=image_status,
        image_badges=image_badges,
        ticket_badges=ticket_badges,
        venue_badges=_venue_badges(
            venue_name=record.venue_name,
            latitude=record.latitude,
            longitude=record.longitude,
            candidates=candidates,
        ),
        quality_flags=flags,
        duplicate_status=record.duplicate_status,
        app_feed_ready=False,
        app_feed_readiness="pending_review",
        detail_url=f"/admin/api-feed-records/{record.id}",
        preview_url=(
            f"/preview/events/{record.created_event_id}"
            if record.created_event_id
            else ""
        ),
        app_json_url=(
            f"/admin/app-feed/events.json?event_id={record.created_event_id}"
            "&include_needs_approval=true"
            if record.created_event_id
            else ""
        ),
        photo_rescue_action_url=f"/admin/api-feed-records/{record.id}/photo-rescue",
        image_candidates_url=(
            f"/admin/image-candidates?event_id={record.created_event_id}"
            if record.created_event_id
            else "/admin/image-candidates?source_type=provider"
        ),
        source_claims_url=f"/admin/api-feed-records/{record.id}/lineage",
        duplicate_group_url="",
        poi_candidates_url=_poi_candidates_url(record.venue_name),
        approve_action_url=(
            f"/admin/api-feed-records/{record.id}/approve"
            if record.review_status not in {"approved", "rejected"}
            else ""
        ),
        hold_action_url=(
            f"/admin/api-feed-records/{record.id}/hold"
            if record.review_status not in {"held", "approved", "rejected"}
            else ""
        ),
        reject_action_url=(
            f"/admin/api-feed-records/{record.id}/reject"
            if record.review_status != "rejected"
            else ""
        ),
    )


def _extracted_row(
    candidate: SourceExtractedEventCandidate,
    poi_lookup: dict[str, list[PoiCandidate]],
) -> EventReviewRow:
    payload = candidate.normalized_payload
    image_url = _safe_image_url(_payload_text(payload, "main_image_url"))
    image_status, image_badges = _image_status_from_simple_url(image_url)
    ticket_url = _payload_text(payload, "tickets_link")
    flags = tuple(sorted(candidate.quality_flags + candidate.validation_errors))
    ticket_status, ticket_badges = _ticket_status(
        ticket_url,
        _payload_text(payload, "ticket_link_classification"),
        flags,
    )
    provider = candidate.extractor_type
    candidates = poi_lookup.get(f"extracted:{candidate.id}", [])
    venue_name = candidate.venue_name or _payload_text(payload, "venue_name")
    return EventReviewRow(
        row_key=f"extracted-{candidate.id}",
        record_type="extracted_candidate",
        record_label="Extracted Candidate",
        object_id=candidate.id,
        status_label=candidate.review_status.replace("_", " ").title(),
        review_status=candidate.review_status,
        title=candidate.event_name or "Untitled extracted candidate",
        start_datetime=candidate.start_datetime,
        venue_name=_clean(venue_name),
        address=_address(
            _payload_text(payload, "venue_address"),
            _payload_text(payload, "city"),
            _payload_text(payload, "state"),
        ),
        city=_payload_text(payload, "city"),
        state=_payload_text(payload, "state"),
        latitude=_payload_float(payload, "latitude"),
        longitude=_payload_float(payload, "longitude"),
        description=_payload_text(payload, "description"),
        genre=_payload_text(payload, "normalized_genre")
        or _payload_text(payload, "genre"),
        ticket_url=ticket_url,
        ticket_classification=_payload_text(payload, "ticket_link_classification"),
        ticket_status=ticket_status,
        website_url=candidate.event_url or candidate.source_url,
        source_label=_extractor_label(candidate.extractor_type),
        source_type="extracted",
        provider=provider,
        source_badges=_source_badges("extracted", provider, provider),
        source_claim_count=1 if candidate.created_event_id else 0,
        image_url=image_url,
        image_status=image_status,
        image_badges=image_badges,
        ticket_badges=ticket_badges,
        venue_badges=_venue_badges(
            venue_name=venue_name,
            latitude=_payload_float(payload, "latitude"),
            longitude=_payload_float(payload, "longitude"),
            candidates=candidates,
        ),
        quality_flags=flags,
        duplicate_status="candidate",
        app_feed_ready=False,
        app_feed_readiness="pending_review",
        detail_url=f"/admin/extracted-events/{candidate.id}",
        preview_url=(
            f"/preview/events/{candidate.created_event_id}"
            if candidate.created_event_id
            else ""
        ),
        app_json_url=(
            f"/admin/app-feed/events.json?event_id={candidate.created_event_id}"
            "&include_needs_approval=true"
            if candidate.created_event_id
            else ""
        ),
        photo_rescue_action_url="",
        image_candidates_url=(
            f"/admin/image-candidates?event_id={candidate.created_event_id}"
            if candidate.created_event_id
            else ""
        ),
        source_claims_url=f"/admin/extracted-events/{candidate.id}",
        duplicate_group_url="",
        poi_candidates_url=_poi_candidates_url(venue_name),
        approve_action_url=(
            f"/admin/extracted-events/{candidate.id}/approve"
            if candidate.validation_status == "valid"
            and not candidate.created_event_id
            else ""
        ),
        hold_action_url="",
        reject_action_url=(
            f"/admin/extracted-events/{candidate.id}/reject"
            if candidate.review_status != "rejected"
            else ""
        ),
    )


def _staged_row(staged: StagedEvent) -> EventReviewRow:
    image_url = _safe_image_url(staged.main_image_url)
    image_status, image_badges = _image_status_from_simple_url(image_url)
    ticket_url = _clean(staged.tickets_link)
    flags = tuple(sorted(staged.risk_flags))
    ticket_status, ticket_badges = _ticket_status(ticket_url, "", flags)
    start = _staged_start(staged.start_date, staged.start_time)
    return EventReviewRow(
        row_key=f"staged-{staged.id}",
        record_type="staged_upload",
        record_label="Staged Upload",
        object_id=staged.id,
        status_label=staged.validation_status.replace("_", " ").title(),
        review_status=staged.validation_status,
        title=staged.event_name or "Untitled staged event",
        start_datetime=start,
        venue_name=_clean(staged.venue_name),
        address=_address(staged.venue_address, staged.city, staged.state),
        city=_clean(staged.city),
        state=_clean(staged.state),
        latitude=_float_or_none(staged.latitude),
        longitude=_float_or_none(staged.longitude),
        description=_clean(staged.description),
        genre="",
        ticket_url=ticket_url,
        ticket_classification="",
        ticket_status=ticket_status,
        website_url=_clean(staged.event_url) or _clean(staged.website),
        source_label="File Upload",
        source_type="file_upload",
        provider="file_upload",
        source_badges=("File Upload",),
        source_claim_count=0,
        image_url=image_url,
        image_status=image_status,
        image_badges=image_badges,
        ticket_badges=ticket_badges,
        venue_badges=_venue_badges(
            venue_name=staged.venue_name,
            latitude=_float_or_none(staged.latitude),
            longitude=_float_or_none(staged.longitude),
            candidates=[],
        ),
        quality_flags=flags,
        duplicate_status="staged",
        app_feed_ready=False,
        app_feed_readiness="pending_review",
        detail_url=f"/admin/import-batches/{staged.import_batch_id}",
        preview_url="",
        app_json_url="",
        photo_rescue_action_url="",
        image_candidates_url="",
        source_claims_url=f"/admin/import-batches/{staged.import_batch_id}",
        duplicate_group_url="",
        poi_candidates_url=_poi_candidates_url(staged.venue_name),
        approve_action_url="",
        hold_action_url="",
        reject_action_url="",
    )


def _poi_candidate_lookup(session: Session) -> dict[str, list[PoiCandidate]]:
    lookup: dict[str, list[PoiCandidate]] = {}
    statement = select(PoiCandidate).where(
        or_(
            PoiCandidate.api_feed_record_id.is_not(None),
            PoiCandidate.extracted_event_candidate_id.is_not(None),
        )
    )
    for candidate in session.scalars(statement).all():
        if candidate.api_feed_record_id is not None:
            lookup.setdefault(f"api:{candidate.api_feed_record_id}", []).append(
                candidate,
            )
        if candidate.extracted_event_candidate_id is not None:
            lookup.setdefault(
                f"extracted:{candidate.extracted_event_candidate_id}",
                [],
            ).append(candidate)
    return lookup


def _hide_blocked_rows_by_default(
    rows: list[EventReviewRow],
    filters: EventReviewFilters,
) -> list[EventReviewRow]:
    if filters.review_status:
        return rows
    return [
        row
        for row in rows
        if row.review_status.lower() not in BLOCKED_STATUSES
        and row.status_label.lower() not in BLOCKED_STATUSES
    ]


def _tabs(rows: list[EventReviewRow]) -> list[EventReviewTab]:
    return [
        EventReviewTab("all", "All", len(rows)),
        EventReviewTab(
            "normalized",
            "Normalized Events",
            sum(row.record_type == "normalized_event" for row in rows),
        ),
        EventReviewTab(
            "api",
            "API Feed Records",
            sum(row.record_type == "api_feed_record" for row in rows),
        ),
        EventReviewTab(
            "extracted",
            "Extracted Candidates",
            sum(row.record_type == "extracted_candidate" for row in rows),
        ),
        EventReviewTab(
            "needs_review",
            "Needs Review",
            sum(row.needs_review for row in rows),
        ),
        EventReviewTab(
            "ready_for_app",
            "Ready for App",
            sum(row.app_feed_ready for row in rows),
        ),
    ]


def _matches_filters(row: EventReviewRow, filters: EventReviewFilters) -> bool:
    return (
        _matches_tab(row, filters.tab)
        and _matches_text(row, filters.search)
        and _matches_date(row, filters.date_from, filters.date_to)
        and _matches_location_text(row, filters.location_text)
        and _matches_radius(row, filters)
        and _matches_contains(row.city, filters.city)
        and _matches_contains(row.state, filters.state)
        and _matches_contains(row.genre, filters.genre)
        and _matches_source_type(row, filters.source_type)
        and _matches_provider(row, filters.provider)
        and _matches_contains(row.review_status, filters.review_status)
        and _matches_contains(row.image_status, filters.image_status)
        and _matches_contains(row.ticket_status, filters.ticket_status)
        and _matches_venue_status(row, filters.venue_status)
        and _matches_contains(row.duplicate_status, filters.duplicate_status)
        and _matches_contains(row.app_feed_readiness, filters.app_feed_readiness)
        and _matches_quality_issue(row, filters.quality_issue)
    )


def _matches_tab(row: EventReviewRow, tab: str) -> bool:
    if tab == "normalized":
        return row.record_type == "normalized_event"
    if tab == "api":
        return row.record_type == "api_feed_record"
    if tab == "extracted":
        return row.record_type == "extracted_candidate"
    if tab == "needs_review":
        return row.needs_review
    if tab == "ready_for_app":
        return row.app_feed_ready
    return True


def _matches_text(row: EventReviewRow, value: str | None) -> bool:
    if not value:
        return True
    needle = value.strip().lower()
    if not needle:
        return True
    haystack = " ".join(
        [
            row.title,
            row.venue_name,
            row.address,
            row.city,
            row.state,
            row.description,
            row.genre,
            row.source_label,
            row.provider,
            row.record_label,
            " ".join(row.quality_flags),
        ]
    ).lower()
    return needle in haystack


def _matches_location_text(row: EventReviewRow, value: str | None) -> bool:
    if not value:
        return True
    needle = value.strip().lower()
    if not needle:
        return True
    return (
        needle
        in " ".join([row.venue_name, row.address, row.city, row.state]).lower()
    )


def _matches_date(
    row: EventReviewRow,
    date_from: date | None,
    date_to: date | None,
) -> bool:
    if date_from is None and date_to is None:
        return True
    if row.start_datetime is None:
        return False
    row_date = row.start_datetime.date()
    if date_from is not None and row_date < date_from:
        return False
    return not (date_to is not None and row_date > date_to)


def _matches_radius(row: EventReviewRow, filters: EventReviewFilters) -> bool:
    if not filters.has_radius:
        return True
    if row.latitude is not None and row.longitude is not None:
        distance = _distance_miles(
            filters.latitude or 0,
            filters.longitude or 0,
            row.latitude,
            row.longitude,
        )
        return distance <= (filters.radius_miles or 0)
    return bool(filters.city or filters.state)


def _matches_source_type(row: EventReviewRow, value: str | None) -> bool:
    if not value:
        return True
    needle = value.strip().lower()
    if not needle:
        return True
    badges = " ".join(row.source_badges).lower()
    return needle in row.source_type.lower() or needle in badges


def _matches_provider(row: EventReviewRow, value: str | None) -> bool:
    if not value:
        return True
    needle = value.strip().lower()
    if not needle:
        return True
    return needle in row.provider.lower() or needle in row.source_label.lower()


def _matches_venue_status(row: EventReviewRow, value: str | None) -> bool:
    if not value:
        return True
    needle = value.strip().lower().replace("_", " ")
    return any(needle in badge.lower() for badge in row.venue_badges)


def _matches_quality_issue(row: EventReviewRow, value: str | None) -> bool:
    if not value:
        return True
    needle = value.strip().lower()
    if not needle:
        return True
    return any(needle in flag.lower() for flag in row.quality_flags)


def _matches_contains(value: str, filter_value: str | None) -> bool:
    if not filter_value:
        return True
    needle = filter_value.strip().lower()
    if not needle:
        return True
    return needle in value.lower()


def _sort_rows(rows: list[EventReviewRow], filters: EventReviewFilters) -> None:
    reverse = filters.sort_direction == "desc"
    rows.sort(
        key=lambda row: (_sort_value(row, filters.sort), row.row_key),
        reverse=reverse,
    )


def _sort_value(row: EventReviewRow, sort_key: str) -> object:
    if sort_key == "event_title":
        return row.title.lower()
    if sort_key == "venue":
        return row.venue_name.lower()
    if sort_key == "source":
        return row.source_label.lower()
    if sort_key == "image_status":
        return row.image_status
    if sort_key == "ticket_status":
        return row.ticket_status
    if sort_key == "app_feed_readiness":
        return row.app_feed_readiness
    return row.start_datetime or datetime.max


def _normalize_filters(filters: EventReviewFilters) -> EventReviewFilters:
    sort = filters.sort
    if sort not in {
        "start_datetime",
        "event_title",
        "venue",
        "source",
        "image_status",
        "ticket_status",
        "app_feed_readiness",
    }:
        sort = "start_datetime"
    direction = "desc" if filters.sort_direction == "desc" else "asc"
    return EventReviewFilters(
        tab=filters.tab if filters.tab else "all",
        search=_none_if_blank(filters.search),
        date_from=filters.date_from,
        date_to=filters.date_to,
        location_text=_none_if_blank(filters.location_text),
        radius_miles=filters.radius_miles,
        latitude=filters.latitude,
        longitude=filters.longitude,
        city=_none_if_blank(filters.city),
        state=_none_if_blank(filters.state),
        genre=_none_if_blank(filters.genre),
        source_type=_none_if_blank(filters.source_type),
        provider=_none_if_blank(filters.provider),
        review_status=_none_if_blank(filters.review_status),
        image_status=_none_if_blank(filters.image_status),
        ticket_status=_none_if_blank(filters.ticket_status),
        venue_status=_none_if_blank(filters.venue_status),
        duplicate_status=_none_if_blank(filters.duplicate_status),
        app_feed_readiness=_none_if_blank(filters.app_feed_readiness),
        quality_issue=_none_if_blank(filters.quality_issue),
        sort=sort,
        sort_direction=direction,
        page=max(1, filters.page),
        per_page=_bounded_per_page(filters.per_page),
        show_full_descriptions=filters.show_full_descriptions,
    )


def _bounded_per_page(value: int) -> int:
    return value if value in ALLOWED_PER_PAGE else DEFAULT_PER_PAGE


def _image_status_from_event(
    image_url: str,
    label: str,
    flags: tuple[str, ...],
) -> tuple[str, tuple[str, ...]]:
    if not image_url or "missing_image" in flags:
        return "missing", ("Missing Image",)
    if "selected_image_pending_approval" in flags:
        return "needs_approval", ("Selected · Needs Approval",)
    if "generic_provider_image_blocked" in flags:
        return "generic_blocked", ("Generic Image Blocked",)
    return _status_key(label, fallback="present"), ("Image Present",)


def _image_status_from_simple_url(image_url: str) -> tuple[str, tuple[str, ...]]:
    if not image_url:
        return "missing", ("Missing Image",)
    return "present", ("Image Present",)


def _ticket_status(
    ticket_url: str,
    classification: str | None,
    flags: tuple[str, ...],
) -> tuple[str, tuple[str, ...]]:
    if not ticket_url or "missing_ticket_link" in flags:
        return "missing", ("Missing/bad ticket link",)
    lowered = _clean(classification).lower()
    if "bad_generic_ticket_link" in flags or "generic" in lowered or "bad" in lowered:
        return "bad", ("Missing/bad/generic ticket link",)
    return "present", (classification or "Ticket link",)


def _venue_badges(
    *,
    venue_name: str | None,
    latitude: float | None,
    longitude: float | None,
    candidates: list[PoiCandidate],
) -> tuple[str, ...]:
    badges: list[str] = []
    if not _clean(venue_name):
        badges.append("Missing Venue")
    elif any(
        candidate.match_status
        in {"matched_existing", "approved_created", "approved_updated"}
        for candidate in candidates
    ):
        badges.append("Linked POI")
    elif candidates:
        badges.append("POI Candidate")
    else:
        badges.append("Event Venue Only")
    if latitude is None or longitude is None:
        badges.append("Missing Coordinates")
    return tuple(badges)


def _source_badges(
    source_type: str | None,
    provider: str | None,
    upstream: str | None,
) -> tuple[str, ...]:
    values = {
        _clean(source_type).lower(),
        _clean(provider).lower(),
        _clean(upstream).lower(),
    }
    badges: list[str] = []
    if "api_feed" in values or "api" in values:
        badges.append("API Feed")
    if "file_upload" in values:
        badges.append("File Upload")
    if "source_extracted" in values or "extracted" in values:
        badges.append("Extracted")
    if "calendar" in values or "ics" in values:
        badges.append("Calendar")
    if "jambase" in values:
        badges.append("JamBase")
    if "cityspark" in values:
        badges.append("CitySpark")
    if "ics" in values:
        badges.append("ICS")
    if "json_ld_event" in values or "json-ld" in values:
        badges.append("JSON-LD")
    if "rss_atom" in values or "rss" in values:
        badges.append("RSS")
    if "html_event_list" in values or "generic_html_links" in values:
        badges.append("HTML")
    if not badges:
        badges.append((_clean(source_type) or "Unknown").replace("_", " ").title())
    return tuple(dict.fromkeys(badges))


def _provider_display(value: str | None) -> str:
    key = _clean(value).lower()
    labels = {
        "jambase": "JamBase",
        "cityspark": "CitySpark",
        "source_extracted": "Extracted Source",
        "api_feed": "API Feed",
        "file_upload": "File Upload",
        "ics": "ICS",
    }
    return labels.get(key, _clean(value).replace("_", " ").title())


def _extractor_label(value: str) -> str:
    labels = {
        "json_ld_event": "JSON-LD Extractor",
        "rss_atom": "RSS/Atom Extractor",
        "html_event_list": "HTML Extractor",
        "generic_html_links": "HTML Link Discovery",
        "ics": "ICS",
    }
    return labels.get(value, value.replace("_", " ").title())


def _safe_image_url(value: str | None) -> str:
    candidate = _clean(value)
    lowered = candidate.lower()
    if any(marker in lowered for marker in LOGO_ASSET_MARKERS):
        return ""
    return candidate


def _status_key(value: str, *, fallback: str) -> str:
    cleaned = _clean(value).lower().replace(" ", "_").replace("/", "_")
    return cleaned or fallback


def _address(address: str | None, city: str | None, state: str | None) -> str:
    return ", ".join(
        part for part in [_clean(address), _clean(city), _clean(state)] if part
    )


def _payload_text(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    return str(value).strip() if value is not None else ""


def _payload_float(payload: dict[str, object], key: str) -> float | None:
    value = payload.get(key)
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        return _float_or_none(value)
    return None


def _float_or_none(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _staged_start(start_date: str | None, start_time: str | None) -> datetime | None:
    if not start_date:
        return None
    try:
        day = date.fromisoformat(start_date)
    except ValueError:
        return None
    if start_time:
        try:
            clock = time.fromisoformat(start_time)
        except ValueError:
            clock = time()
    else:
        clock = time()
    return datetime.combine(day, clock)


def _distance_miles(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    radius = 3958.8
    lat1 = math.radians(latitude_a)
    lat2 = math.radians(latitude_b)
    delta_lat = math.radians(latitude_b - latitude_a)
    delta_lon = math.radians(longitude_b - longitude_a)
    hav = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(hav), math.sqrt(1 - hav))


def _poi_candidates_url(venue_name: str | None) -> str:
    if not _clean(venue_name):
        return "/admin/poi-candidates"
    return f"/admin/poi-candidates?search={quote_plus(_clean(venue_name))}"


def _clean(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _none_if_blank(value: str | None) -> str | None:
    cleaned = _clean(value)
    return cleaned or None
