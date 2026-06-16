from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any, Literal

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    AppFeedExport,
    AppFeedExportStatus,
    Event,
    EventArtist,
    EventVenue,
    PoiLocation,
    PublishedEventSnapshot,
    PublishedPoiSnapshot,
    PublishStatus,
    utc_now,
)

PUBLISHABLE_STATUSES = {
    PublishStatus.approved.value,
    PublishStatus.published.value,
}
CANCELLED_STATUSES = {"cancelled", "canceled"}
DUPLICATE_EXCLUDE_STATUSES = {
    "duplicate_candidate",
    "merged",
    "rejected",
}
IMAGE_NEEDS_APPROVAL_STATUSES = {
    "needs_approval",
    "pending_approval",
    "selected_pending_approval",
}
IMAGE_HARD_BLOCK_STATUSES = {
    "rejected",
    "hard_blocked",
    "blocked",
}
LOGO_ASSET_MARKERS = (
    "music-roadtrip-logo",
    "/static/images/music-roadtrip-logo",
)


@dataclass(frozen=True)
class AppEventFilters:
    event_id: int | None = None
    date_from: date | None = None
    date_to: date | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    genre: str | None = None
    venue_id: int | None = None
    poi_id: str | None = None
    region_id: int | None = None
    include_cancelled: bool = False
    include_needs_approval: bool = True
    limit: int = 100
    offset: int = 0


@dataclass(frozen=True)
class AppPoiFilters:
    category: str | None = None
    subcategory: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    region_id: int | None = None
    has_upcoming_events: bool = False
    limit: int = 100
    offset: int = 0


@dataclass(frozen=True)
class AppFeedSummary:
    event_feed_record_count: int
    poi_feed_record_count: int
    venues_with_upcoming_events: int
    last_export: AppFeedExport | None
    failed_export_count: int
    records_blocked_from_publishing: int
    events_needing_images: int
    events_pending_image_approval: int
    duplicate_candidates_excluded: int
    cancelled_or_stale_events_excluded: int
    publishable_pois: int
    pois_blocked_from_app_feed: int


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _iso_datetime(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def _safe_float(value: float | None) -> float | None:
    return float(value) if value is not None else None


def _json_list(value: str | None) -> list[Any]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _split_artists(value: str | None) -> list[str]:
    if not value:
        return []
    if value.strip().startswith("["):
        parsed = _json_list(value)
        if parsed:
            return [str(item) for item in parsed if str(item).strip()]
    return [
        part.strip()
        for part in value.replace("\n", ",").split(",")
        if part.strip()
    ]


def _artist_payloads(event: Event) -> list[dict[str, Any]]:
    role_order = {
        "headliner": 0,
        "performer": 1,
        "supporting": 2,
        "dj": 3,
        "unknown": 9,
    }
    links = sorted(
        event.artist_links,
        key=lambda link: (
            link.performance_rank or 999,
            role_order.get(link.role or "unknown", 9),
            link.id,
        ),
    )
    payloads: list[dict[str, Any]] = []
    for link in links:
        artist = link.artist
        if artist is None:
            continue
        payloads.append(
            {
                "artist_id": f"artist-{artist.id}",
                "name": artist.display_name,
                "role": link.role or "unknown",
                "spotify_url": artist.spotify_url or "",
                "image_url": artist.image_url or "",
                "genres": artist.normalized_genres,
            }
        )
    return payloads


def _is_logo_asset(value: str | None) -> bool:
    if not value:
        return False
    lowered = value.lower()
    return any(marker in lowered for marker in LOGO_ASSET_MARKERS)


def _image_needs_approval(status: str | None, clearance_status: str | None) -> bool:
    status_key = (status or "").strip().lower()
    clearance_key = (clearance_status or "").strip().lower()
    return (
        status_key in IMAGE_NEEDS_APPROVAL_STATUSES
        or clearance_key in IMAGE_NEEDS_APPROVAL_STATUSES
    )


def _image_hard_blocked(status: str | None, clearance_status: str | None) -> bool:
    status_key = (status or "").strip().lower()
    clearance_key = (clearance_status or "").strip().lower()
    return (
        status_key in IMAGE_HARD_BLOCK_STATUSES
        or clearance_key in {"rejected", "blocked"}
    )


def _event_lifecycle(event: Event) -> str:
    return (event.event_lifecycle_status or event.event_status or "active").lower()


def _event_is_cancelled(event: Event) -> bool:
    return _event_lifecycle(event) in CANCELLED_STATUSES or (
        (event.event_status or "").strip().lower() in CANCELLED_STATUSES
    )


def _event_is_duplicate_excluded(event: Event) -> bool:
    return (event.duplicate_status or "").strip().lower() in DUPLICATE_EXCLUDE_STATUSES


def _event_image_url(event: Event) -> str:
    selected = event.selected_main_image_url or event.main_image_url or ""
    return "" if _is_logo_asset(selected) else selected


def event_publish_readiness(event: Event) -> tuple[int, list[str], list[str]]:
    blockers: list[str] = []
    flags: list[str] = []
    earned = 0
    total = 12

    if event.title.strip():
        earned += 1
    else:
        blockers.append("missing_title")

    if event.start_datetime is not None:
        earned += 1
    else:
        blockers.append("missing_start_datetime")

    venue = event.venue
    if venue and venue.display_name.strip():
        earned += 1
    else:
        blockers.append("missing_venue")

    has_venue_location = bool(
        venue
        and (
            (venue.address and venue.address.strip())
            or (venue.latitude is not None and venue.longitude is not None)
        )
    )
    if has_venue_location:
        earned += 1
    else:
        blockers.append("missing_venue_location")

    ticket_url = event.recommended_ticket_link or event.tickets_link
    if ticket_url:
        earned += 1
    else:
        blockers.append("missing_ticket_link")

    image_url = _event_image_url(event)
    if image_url:
        earned += 1
    else:
        flags.append("missing_image")

    if _image_hard_blocked(event.image_status, event.image_clearance_status):
        blockers.append("image_hard_blocked")
    else:
        earned += 1

    if _image_needs_approval(event.image_status, event.image_clearance_status):
        flags.append("image_needs_approval")
    else:
        earned += 1

    if _event_is_duplicate_excluded(event):
        blockers.append(f"duplicate_status_{event.duplicate_status}")
    else:
        earned += 1

    lifecycle = _event_lifecycle(event)
    if lifecycle in {"active", "scheduled"}:
        earned += 1
    else:
        blockers.append(f"lifecycle_{lifecycle}")

    if event.source_claim_count > 0 or event.source_claims:
        earned += 1
    else:
        flags.append("missing_source_claim")

    if event.ingestion_provider or event.api_provider_key or event.source_type:
        earned += 1
    else:
        flags.append("missing_source_trust_signal")

    return round((earned / total) * 100), blockers, flags


def poi_publish_readiness(poi: PoiLocation) -> tuple[int, list[str], list[str]]:
    blockers: list[str] = []
    flags: list[str] = []
    earned = 0
    total = 8

    if poi.display_name.strip():
        earned += 1
    else:
        blockers.append("missing_name")
    if poi.category.strip():
        earned += 1
    else:
        blockers.append("missing_category")
    if poi.subcategory:
        earned += 1
    else:
        flags.append("missing_subcategory")
    if (poi.latitude is not None and poi.longitude is not None) or poi.address:
        earned += 1
    else:
        blockers.append("missing_location")
    if poi.website or poi.source_record_id or poi.places_id:
        earned += 1
    else:
        flags.append("missing_website_or_source_url")
    if poi.main_image_url and not _is_logo_asset(poi.main_image_url):
        earned += 1
    else:
        flags.append("missing_image")
    if "duplicate" in (poi.quality_control or "").lower():
        blockers.append("possible_duplicate")
    else:
        earned += 1
    if poi.canonical_poi_id:
        earned += 1
    else:
        blockers.append("missing_stable_id")

    return round((earned / total) * 100), blockers, flags


def app_event_id(event: Event) -> str:
    return f"event-{event.id}"


def app_poi_id(poi: PoiLocation) -> str:
    return poi.canonical_poi_id or f"poi-{poi.id}"


def event_to_app_json(event: Event) -> dict[str, Any]:
    score, blockers, flags = event_publish_readiness(event)
    venue = event.venue
    image_url = _event_image_url(event)
    if _is_logo_asset(event.selected_main_image_url or event.main_image_url):
        flags.append("logo_asset_suppressed")
    ticket_url = event.recommended_ticket_link or event.tickets_link or ""
    ingestion_providers = [
        str(item)
        for item in {
            event.ingestion_provider or "",
            event.api_provider_key or "",
            event.source_type or "",
        }
        if item
    ]
    source_chain_summary = " > ".join(
        str(item.get("source_name") or item.get("provider") or item)
        if isinstance(item, dict)
        else str(item)
        for item in event.source_chain[:5]
    )
    image_flags = list(dict.fromkeys(event.image_quality_flags + flags))
    return {
        "event_id": app_event_id(event),
        "record_type": "event",
        "category": event.category or "Concert",
        "title": event.title,
        "headliner": event.headliner or "",
        "supporting_artists": _split_artists(event.supporting_artists),
        "artists": _artist_payloads(event),
        "genre": (
            event.normalized_genres[0]
            if event.normalized_genres
            else event.genre or event.normalized_genre or ""
        ),
        "normalized_genres": event.normalized_genres,
        "provider_genre": event.provider_genre or "",
        "music_category": event.music_category or "",
        "start_datetime": _iso_datetime(event.start_datetime),
        "end_datetime": _iso_datetime(event.end_datetime),
        "timezone": event.timezone or "",
        "doors_time": event.doors_time or "",
        "lifecycle_status": (
            event.event_lifecycle_status or event.event_status or "active"
        ),
        "venue": {
            "venue_id": str(venue.id) if venue else "",
            "poi_id": venue.venue_key if venue else "",
            "name": venue.display_name if venue else event.location_text or "",
            "address": venue.address if venue and venue.address else "",
            "city": venue.city if venue and venue.city else "",
            "state": venue.state if venue and venue.state else "",
            "zip_code": venue.zip_code if venue and venue.zip_code else "",
            "country": venue.country if venue and venue.country else "",
            "latitude": _safe_float(venue.latitude) if venue else None,
            "longitude": _safe_float(venue.longitude) if venue else None,
        },
        "image": {
            "url": image_url,
            "role": event.image_role or "",
            "image_role": event.image_role or "",
            "source_type": event.image_source_type or "",
            "status": event.image_status or "",
            "clearance_status": event.image_clearance_status or "",
            "needs_approval": _image_needs_approval(
                event.image_status,
                event.image_clearance_status,
            ),
            "quality_score": _safe_float(event.image_quality_score),
            "selection_reason": event.image_selection_reason or "",
            "quality_flags": image_flags,
            "flags": image_flags,
        },
        "tickets": {
            "url": ticket_url,
            "provider": event.ticketing_provider or "",
            "classification": event.ticket_link_classification or "",
            "quality_flags": [
                flag
                for flag in [
                    event.ticket_link_repair_strategy,
                    event.ticket_link_repair_source,
                ]
                if flag
            ],
        },
        "links": {
            "event_url": event.source_url or "",
            "spotify_url": event.spotify_url or "",
            "website": venue.website if venue and venue.website else "",
        },
        "source": {
            "primary_provider": event.api_provider_key
            or event.ingestion_provider
            or event.source_type
            or "",
            "ingestion_providers": ingestion_providers,
            "source_claim_count": event.source_claim_count,
            "source_chain_summary": source_chain_summary,
        },
        "quality": {
            "publish_ready_score": score,
            "dedupe_confidence": event.dedupe_confidence,
            "venue_match_confidence": None,
            "flags": list(dict.fromkeys(flags + blockers)),
        },
        "updated_at": _iso_datetime(event.updated_at),
    }


def poi_to_app_json(
    poi: PoiLocation,
    upcoming_event_count: int = 0,
    next_event_datetime: datetime | None = None,
) -> dict[str, Any]:
    score, blockers, flags = poi_publish_readiness(poi)
    image_url = poi.main_image_url or ""
    if _is_logo_asset(image_url):
        image_url = ""
        flags.append("logo_asset_suppressed")
    return {
        "poi_id": app_poi_id(poi),
        "record_type": "poi",
        "name": poi.display_name,
        "category": poi.category,
        "subcategory": poi.subcategory or "",
        "description": poi.description or "",
        "address": poi.address or "",
        "city": poi.city or "",
        "state": poi.state or "",
        "zip_code": _clean_text(poi.zip_code),
        "country": poi.country or "",
        "latitude": _safe_float(poi.latitude),
        "longitude": _safe_float(poi.longitude),
        "links": {
            "website": poi.website or "",
            "instagram": poi.instagram or "",
            "facebook": poi.facebook or "",
            "x": poi.x_url or "",
            "tiktok": poi.tiktok or "",
            "youtube": "",
            "spotify": poi.spotify_url or "",
        },
        "image": {
            "url": image_url,
            "status": "available" if image_url else "missing",
            "clearance_status": "unknown",
            "needs_approval": False,
            "quality_score": _safe_float(poi.photo_quality_score),
            "flags": list(dict.fromkeys(flags)),
        },
        "place": {
            "certified": bool(poi.certified),
            "carousel_selection": poi.carousel_selection or "",
            "business_status": poi.business_status or "",
            "hours_of_operation": poi.hours_of_operation or "",
        },
        "events": {
            "upcoming_event_count": upcoming_event_count,
            "next_event_datetime": _iso_datetime(next_event_datetime),
        },
        "quality": {
            "publish_ready_score": score,
            "flags": list(dict.fromkeys(flags + blockers)),
        },
        "updated_at": _iso_datetime(poi.updated_at),
    }


def venue_to_app_json(venue: EventVenue, events: list[Event]) -> dict[str, Any]:
    next_event = min(events, key=lambda event: event.start_datetime) if events else None
    image_url = venue.selected_main_image_url or venue.main_image_url or ""
    flags = venue.image_quality_flags
    if _is_logo_asset(image_url):
        image_url = ""
        flags = list(dict.fromkeys(flags + ["logo_asset_suppressed"]))
    return {
        "venue_id": str(venue.id),
        "record_type": "venue",
        "poi_id": venue.venue_key,
        "name": venue.display_name,
        "category": venue.category,
        "subcategory": venue.subcategory,
        "address": venue.address or "",
        "city": venue.city or "",
        "state": venue.state or "",
        "zip_code": _clean_text(venue.zip_code),
        "country": venue.country or "",
        "latitude": _safe_float(venue.latitude),
        "longitude": _safe_float(venue.longitude),
        "website": venue.website or "",
        "image": {
            "url": image_url,
            "status": venue.image_status or ("available" if image_url else "missing"),
            "clearance_status": venue.image_clearance_status or "",
            "needs_approval": _image_needs_approval(
                venue.image_status,
                venue.image_clearance_status,
            ),
            "quality_score": _safe_float(venue.image_quality_score),
            "flags": flags,
        },
        "events": {
            "upcoming_event_count": len(events),
            "next_event_datetime": _iso_datetime(
                next_event.start_datetime if next_event else None,
            ),
        },
        "updated_at": _iso_datetime(venue.updated_at),
    }


def _bounded_limit(limit: int | None) -> int:
    if limit is None:
        return 100
    return max(1, min(limit, 500))


def _bounded_offset(offset: int | None) -> int:
    if offset is None:
        return 0
    return max(0, offset)


def _apply_event_filters(
    stmt: Select[tuple[Event]],
    filters: AppEventFilters,
) -> Select[tuple[Event]]:
    stmt = stmt.where(Event.publish_status.in_(PUBLISHABLE_STATUSES))
    if filters.event_id:
        stmt = stmt.where(Event.id == filters.event_id)
    if not filters.include_cancelled:
        stmt = stmt.where(Event.event_lifecycle_status.not_in(CANCELLED_STATUSES))
        stmt = stmt.where(
            (Event.event_status.is_(None))
            | Event.event_status.not_in(CANCELLED_STATUSES),
        )
    stmt = stmt.where(Event.duplicate_status.not_in(DUPLICATE_EXCLUDE_STATUSES))
    if filters.date_from:
        stmt = stmt.where(
            Event.start_datetime >= datetime.combine(filters.date_from, time.min),
        )
    if filters.date_to:
        stmt = stmt.where(
            Event.start_datetime <= datetime.combine(filters.date_to, time.max),
        )
    if filters.genre:
        stmt = stmt.where(
            (Event.genre == filters.genre)
            | (Event.normalized_genre == filters.genre)
            | Event.normalized_genres_json.contains(f'"{filters.genre}"')
            | (Event.music_category == filters.genre)
        )
    if filters.venue_id:
        stmt = stmt.where(Event.event_venue_id == filters.venue_id)
    if filters.region_id:
        stmt = stmt.where(Event.region_id == filters.region_id)
    if filters.city:
        stmt = stmt.join(Event.venue).where(EventVenue.city == filters.city)
    if filters.state:
        stmt = stmt.join(Event.venue).where(EventVenue.state == filters.state)
    if filters.country:
        stmt = stmt.join(Event.venue).where(EventVenue.country == filters.country)
    return stmt


def list_app_events(
    db: Session,
    filters: AppEventFilters | None = None,
) -> list[dict[str, Any]]:
    filters = filters or AppEventFilters()
    stmt = select(Event).options(
        selectinload(Event.venue),
        selectinload(Event.source_claims),
        selectinload(Event.artist_links).selectinload(EventArtist.artist),
    )
    stmt = _apply_event_filters(stmt, filters)
    stmt = (
        stmt.order_by(Event.start_datetime.asc())
        .offset(_bounded_offset(filters.offset))
        .limit(_bounded_limit(filters.limit))
    )
    records: list[dict[str, Any]] = []
    for event in db.scalars(stmt).all():
        payload = event_to_app_json(event)
        if not filters.include_needs_approval and payload["image"]["needs_approval"]:
            continue
        records.append(payload)
    return records


def _apply_poi_filters(
    stmt: Select[tuple[PoiLocation]],
    filters: AppPoiFilters,
) -> Select[tuple[PoiLocation]]:
    stmt = stmt.where(PoiLocation.publish_status.in_(PUBLISHABLE_STATUSES))
    stmt = stmt.where(PoiLocation.category != "Concert")
    if filters.category:
        stmt = stmt.where(PoiLocation.category == filters.category)
    if filters.subcategory:
        stmt = stmt.where(PoiLocation.subcategory == filters.subcategory)
    if filters.city:
        stmt = stmt.where(PoiLocation.city == filters.city)
    if filters.state:
        stmt = stmt.where(PoiLocation.state == filters.state)
    if filters.country:
        stmt = stmt.where(PoiLocation.country == filters.country)
    if filters.region_id:
        stmt = stmt.where(PoiLocation.region_id == filters.region_id)
    return stmt


def _upcoming_events_by_venue(db: Session) -> dict[str, tuple[int, datetime | None]]:
    now = utc_now()
    result: dict[str, tuple[int, datetime | None]] = {}
    rows = db.execute(
        select(
            EventVenue.venue_key,
            func.count(Event.id),
            func.min(Event.start_datetime),
        )
        .join(Event, Event.event_venue_id == EventVenue.id)
        .where(Event.publish_status.in_(PUBLISHABLE_STATUSES))
        .where(Event.start_datetime >= now)
        .where(Event.duplicate_status.not_in(DUPLICATE_EXCLUDE_STATUSES))
        .group_by(EventVenue.venue_key)
    )
    for venue_key, count, next_datetime in rows:
        if venue_key:
            result[str(venue_key)] = (int(count), next_datetime)
    return result


def list_app_pois(
    db: Session,
    filters: AppPoiFilters | None = None,
) -> list[dict[str, Any]]:
    filters = filters or AppPoiFilters()
    stmt = _apply_poi_filters(select(PoiLocation), filters)
    stmt = (
        stmt.order_by(PoiLocation.display_name.asc())
        .offset(_bounded_offset(filters.offset))
        .limit(_bounded_limit(filters.limit))
    )
    upcoming = _upcoming_events_by_venue(db)
    records: list[dict[str, Any]] = []
    for poi in db.scalars(stmt).all():
        count, next_datetime = upcoming.get(
            poi.canonical_venue_id or poi.canonical_poi_id,
            (0, None),
        )
        if filters.has_upcoming_events and count <= 0:
            continue
        records.append(poi_to_app_json(poi, count, next_datetime))
    return records


def list_app_venues(
    db: Session,
    filters: AppEventFilters | None = None,
) -> list[dict[str, Any]]:
    filters = filters or AppEventFilters()
    events_stmt = select(Event).options(selectinload(Event.venue))
    events_stmt = _apply_event_filters(events_stmt, filters)
    events = db.scalars(events_stmt.order_by(Event.start_datetime.asc())).all()
    by_venue: dict[int, list[Event]] = {}
    for event in events:
        if event.venue is None:
            continue
        by_venue.setdefault(event.venue.id, []).append(event)
    return [
        venue_to_app_json(events_for_venue[0].venue, events_for_venue)
        for events_for_venue in by_venue.values()
        if events_for_venue[0].venue is not None
    ]


def app_feed_payload(
    export_type: Literal["events", "pois", "venues", "full"],
    db: Session,
) -> dict[str, Any]:
    generated_at = _iso_datetime(utc_now())
    if export_type == "events":
        records = list_app_events(db)
        return {
            "export_type": "events",
            "generated_at": generated_at,
            "count": len(records),
            "records": records,
        }
    if export_type == "pois":
        records = list_app_pois(db)
        return {
            "export_type": "pois",
            "generated_at": generated_at,
            "count": len(records),
            "records": records,
        }
    if export_type == "venues":
        records = list_app_venues(db)
        return {
            "export_type": "venues",
            "generated_at": generated_at,
            "count": len(records),
            "records": records,
        }
    events = list_app_events(db)
    pois = list_app_pois(db)
    venues = list_app_venues(db)
    return {
        "export_type": "full",
        "generated_at": generated_at,
        "events": {"count": len(events), "records": events},
        "pois": {"count": len(pois), "records": pois},
        "venues": {"count": len(venues), "records": venues},
    }


def create_app_feed_export(
    db: Session,
    export_type: Literal["events", "pois", "venues", "full"],
    generated_by: str,
) -> AppFeedExport:
    export = AppFeedExport(
        export_type=export_type,
        status=AppFeedExportStatus.pending.value,
        generated_by=generated_by,
    )
    db.add(export)
    db.flush()
    try:
        payload = app_feed_payload(export_type, db)
        output_json = json.dumps(payload, sort_keys=True)
        if export_type == "events":
            record_count = int(payload["count"])
        elif export_type == "pois":
            record_count = int(payload["count"])
        elif export_type == "venues":
            record_count = int(payload["count"])
        else:
            record_count = int(payload["events"]["count"]) + int(
                payload["pois"]["count"],
            )
        export.status = AppFeedExportStatus.success.value
        export.record_count = record_count
        export.generated_at = utc_now()
        export.output_json = output_json
        _persist_snapshots(db, payload, export_type)
    except Exception as exc:
        export.status = AppFeedExportStatus.failure.value
        export.error_message = str(exc)
    db.commit()
    db.refresh(export)
    return export


def _persist_snapshots(
    db: Session,
    payload: dict[str, Any],
    export_type: str,
) -> None:
    published_at = utc_now()
    if export_type in {"events", "full"}:
        event_records = (
            payload["records"]
            if export_type == "events"
            else payload["events"]["records"]
        )
        for record in event_records:
            event_id = int(str(record["event_id"]).removeprefix("event-"))
            db.add(
                PublishedEventSnapshot(
                    event_id=event_id,
                    app_event_id=record["event_id"],
                    snapshot_json=json.dumps(record, sort_keys=True),
                    published_at=published_at,
                ),
            )
    if export_type in {"pois", "full"}:
        poi_records = (
            payload["records"]
            if export_type == "pois"
            else payload["pois"]["records"]
        )
        poi_by_app_id = {
            app_poi_id(poi): poi.id
            for poi in db.scalars(select(PoiLocation)).all()
        }
        for record in poi_records:
            poi_location_id = poi_by_app_id.get(record["poi_id"])
            if poi_location_id is None:
                continue
            db.add(
                PublishedPoiSnapshot(
                    poi_location_id=poi_location_id,
                    app_poi_id=record["poi_id"],
                    snapshot_json=json.dumps(record, sort_keys=True),
                    published_at=published_at,
                ),
            )


def latest_successful_export(
    db: Session,
    export_type: str | None = None,
) -> AppFeedExport | None:
    stmt = select(AppFeedExport).where(
        AppFeedExport.status == AppFeedExportStatus.success.value,
    )
    if export_type:
        stmt = stmt.where(AppFeedExport.export_type == export_type)
    stmt = stmt.order_by(AppFeedExport.generated_at.desc(), AppFeedExport.id.desc())
    return db.scalars(stmt).first()


def app_feed_summary(db: Session) -> AppFeedSummary:
    events = list_app_events(db, AppEventFilters(limit=500))
    pois = list_app_pois(db, AppPoiFilters(limit=500))
    venues = list_app_venues(db, AppEventFilters(limit=500))
    failed_exports = db.scalar(
        select(func.count(AppFeedExport.id)).where(
            AppFeedExport.status == AppFeedExportStatus.failure.value,
        ),
    ) or 0
    total_events = db.scalar(select(func.count(Event.id))) or 0
    total_pois = db.scalar(select(func.count(PoiLocation.id))) or 0
    duplicate_excluded = db.scalar(
        select(func.count(Event.id)).where(
            Event.duplicate_status.in_(DUPLICATE_EXCLUDE_STATUSES),
        ),
    ) or 0
    cancelled_excluded = db.scalar(
        select(func.count(Event.id)).where(
            Event.event_lifecycle_status.in_(CANCELLED_STATUSES),
        ),
    ) or 0
    events_missing_images = sum(
        1 for record in events if not record["image"]["url"]
    )
    events_pending_approval = sum(
        1 for record in events if record["image"]["needs_approval"]
    )
    return AppFeedSummary(
        event_feed_record_count=len(events),
        poi_feed_record_count=len(pois),
        venues_with_upcoming_events=len(venues),
        last_export=latest_successful_export(db),
        failed_export_count=int(failed_exports),
        records_blocked_from_publishing=max(
            0,
            int(total_events) + int(total_pois) - len(events) - len(pois),
        ),
        events_needing_images=events_missing_images,
        events_pending_image_approval=events_pending_approval,
        duplicate_candidates_excluded=int(duplicate_excluded),
        cancelled_or_stale_events_excluded=int(cancelled_excluded),
        publishable_pois=len(pois),
        pois_blocked_from_app_feed=max(0, int(total_pois) - len(pois)),
    )
