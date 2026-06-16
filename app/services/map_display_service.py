from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    AppDiscoverySlot,
    AppSearchEntityType,
    AppSearchIndex,
    DiscoverySlotType,
    Event,
    EventVenue,
    Itinerary,
    PoiLocation,
    Region,
    utc_now,
)
from app.services.app_feed_service import (
    DUPLICATE_EXCLUDE_STATUSES,
    PUBLISHABLE_STATUSES,
    event_publish_readiness,
    poi_publish_readiness,
)


@dataclass(frozen=True)
class MapMarkerFilters:
    entity_type: str | None = None
    category: str | None = None
    subcategory: str | None = None
    region_id: int | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    has_upcoming_events: bool | None = None
    certified: bool | None = None
    limit: int = 250
    offset: int = 0


def _safe_float(value: float | None) -> float | None:
    return float(value) if value is not None else None


def _as_aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _futureish(value: datetime | None) -> bool:
    aware = _as_aware_utc(value)
    return aware is not None and aware >= utc_now() - timedelta(hours=12)


def _quality_from_flags(
    score: float | None,
    flags: list[str],
) -> dict[str, object]:
    return {
        "score": score,
        "flags": list(dict.fromkeys(flag for flag in flags if flag)),
    }


def _int_value(value: object, default: int = 0) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _category_marker_style(
    category: str | None,
    subcategory: str | None,
) -> dict[str, object]:
    category_key = (category or "").strip()
    subcategory_key = (subcategory or "").strip()
    if category_key == "Music Site" and subcategory_key == "Venues":
        return {
            "icon_key": "venue_pin",
            "icon_label": "Venue",
            "marker_color": "#38d978",
            "marker_shape": "pin",
            "marker_size": "large",
            "marker_weight": 82,
            "cluster_priority": 74,
            "z_index": 220,
        }
    if category_key == "Music Site":
        return {
            "icon_key": "music_site",
            "icon_label": "Music Site",
            "marker_color": "#46b3ff",
            "marker_shape": "pin",
            "marker_size": "medium",
            "marker_weight": 70,
            "cluster_priority": 62,
            "z_index": 190,
        }
    if category_key == "Cultural":
        return {
            "icon_key": "cultural_place",
            "icon_label": "Cultural",
            "marker_color": "#ff784e",
            "marker_shape": "pin",
            "marker_size": "small",
            "marker_weight": 48,
            "cluster_priority": 42,
            "z_index": 140,
        }
    if category_key == "Lodging":
        return {
            "icon_key": "lodging",
            "icon_label": "Lodging",
            "marker_color": "#ff4b5c",
            "marker_shape": "pin",
            "marker_size": "small",
            "marker_weight": 44,
            "cluster_priority": 38,
            "z_index": 120,
        }
    if category_key == "Bars & Lounges":
        return {
            "icon_key": "bar_lounge",
            "icon_label": "Bars & Lounges",
            "marker_color": "#23d4d7",
            "marker_shape": "pin",
            "marker_size": "small",
            "marker_weight": 50,
            "cluster_priority": 45,
            "z_index": 150,
        }
    return {
        "icon_key": "place_pin",
        "icon_label": category_key or "Place",
        "marker_color": "#9ca3af",
        "marker_shape": "pin",
        "marker_size": "small",
        "marker_weight": 40,
        "cluster_priority": 30,
        "z_index": 100,
    }


def _base_marker(
    style: dict[str, object],
    *,
    certified: bool = False,
) -> dict[str, object]:
    marker = dict(style)
    marker["marker_opacity"] = 1.0
    marker["glow"] = certified
    marker["certified"] = certified
    if certified:
        marker["marker_weight"] = _int_value(marker.get("marker_weight")) + 18
        marker["cluster_priority"] = _int_value(marker.get("cluster_priority")) + 14
        marker["z_index"] = _int_value(marker.get("z_index")) + 40
    return marker


def _marker_from_event(event: Event) -> dict[str, Any]:
    venue = event.venue
    score, blockers, flags = event_publish_readiness(event)
    location_flags: list[str] = []
    if venue is None or (venue.latitude is None or venue.longitude is None):
        location_flags.append("missing_location")
    if not (event.recommended_ticket_link or event.tickets_link):
        location_flags.append("missing_ticket")
    if not (event.selected_main_image_url or event.main_image_url):
        location_flags.append("missing_image")
    upcoming_ready = (
        event.publish_status in PUBLISHABLE_STATUSES
        and event.duplicate_status not in DUPLICATE_EXCLUDE_STATUSES
        and _futureish(event.start_datetime)
    )
    return {
        "id": f"event_{event.id}",
        "entity_type": AppSearchEntityType.event.value,
        "title": event.title,
        "category": event.category or "Concert",
        "subcategory": (
            event.normalized_genres[0]
            if event.normalized_genres
            else event.normalized_genre or event.genre or event.music_category or ""
        ),
        "latitude": _safe_float(venue.latitude) if venue else None,
        "longitude": _safe_float(venue.longitude) if venue else None,
        "marker": {
            "icon_key": "event_ticket",
            "icon_label": "Event",
            "marker_color": "#ffc233",
            "marker_shape": "pin",
            "marker_size": "medium",
            "marker_weight": 78 if upcoming_ready else 58,
            "marker_opacity": 1.0,
            "glow": False,
            "certified": False,
            "cluster_priority": 86 if upcoming_ready else 64,
            "z_index": 260 if upcoming_ready else 210,
        },
        "quality": _quality_from_flags(float(score), blockers + flags + location_flags),
    }


def _marker_from_poi(poi: PoiLocation) -> dict[str, Any]:
    score, blockers, flags = poi_publish_readiness(poi)
    certified = bool(poi.certified)
    style = _category_marker_style(poi.category, poi.subcategory)
    return {
        "id": f"poi_{poi.id}",
        "entity_type": AppSearchEntityType.poi.value,
        "title": poi.display_name,
        "category": poi.category,
        "subcategory": poi.subcategory or "",
        "latitude": _safe_float(poi.latitude),
        "longitude": _safe_float(poi.longitude),
        "marker": _base_marker(style, certified=certified),
        "quality": _quality_from_flags(float(score), blockers + flags),
    }


def _marker_from_venue(venue: EventVenue) -> dict[str, Any]:
    style = _category_marker_style(venue.category, venue.subcategory)
    flags = venue.image_quality_flags
    if venue.latitude is None or venue.longitude is None:
        flags = list(dict.fromkeys(flags + ["missing_location"]))
    return {
        "id": f"venue_{venue.id}",
        "entity_type": AppSearchEntityType.venue.value,
        "title": venue.display_name,
        "category": venue.category,
        "subcategory": venue.subcategory,
        "latitude": _safe_float(venue.latitude),
        "longitude": _safe_float(venue.longitude),
        "marker": _base_marker(style),
        "quality": _quality_from_flags(venue.image_quality_score, flags),
    }


def _marker_from_region(region: Region) -> dict[str, Any]:
    certified = region.certified
    return {
        "id": f"region_{region.id}",
        "entity_type": AppSearchEntityType.region.value,
        "title": region.name,
        "category": region.region_type,
        "subcategory": "",
        "latitude": _safe_float(region.latitude),
        "longitude": _safe_float(region.longitude),
        "marker": {
            "icon_key": "region_marker",
            "icon_label": "Region",
            "marker_color": "#8b5cf6" if certified else "#60a5fa",
            "marker_shape": "circle",
            "marker_size": "xlarge",
            "marker_weight": 95 if certified else 80,
            "marker_opacity": 0.92,
            "glow": certified,
            "certified": certified,
            "cluster_priority": 96,
            "z_index": 80,
        },
        "quality": _quality_from_flags(None, []),
    }


def _marker_from_index(entry: AppSearchIndex) -> dict[str, Any]:
    marker: dict[str, object]
    if entry.entity_type == AppSearchEntityType.event.value:
        marker = {
            "icon_key": "event_ticket",
            "icon_label": "Event",
            "marker_color": "#ffc233",
            "marker_shape": "pin",
            "marker_size": "medium",
            "marker_weight": 78 if entry.app_feed_ready else 58,
            "marker_opacity": 1.0,
            "glow": False,
            "certified": False,
            "cluster_priority": 84 if entry.has_upcoming_events else 62,
            "z_index": 250,
        }
    elif entry.entity_type == AppSearchEntityType.itinerary.value:
        marker = {
            "icon_key": "route_card",
            "icon_label": "Itinerary",
            "marker_color": "#9f7bff",
            "marker_shape": "diamond",
            "marker_size": "large",
            "marker_weight": 72 if entry.app_feed_ready else 55,
            "marker_opacity": 1.0,
            "glow": entry.certified,
            "certified": entry.certified,
            "cluster_priority": 70,
            "z_index": 205,
        }
    elif entry.entity_type == AppSearchEntityType.region.value:
        marker = _marker_from_region(
            Region(
                id=int(entry.entity_id),
                region_key=f"index:{entry.entity_id}",
                slug=f"index-{entry.entity_id}",
                name=entry.display_name,
                region_type=entry.category or "custom",
                city=entry.city,
                state=entry.state,
                country=entry.country,
                latitude=entry.latitude,
                longitude=entry.longitude,
                certified=entry.certified,
            ),
        )["marker"]
    else:
        marker = _base_marker(
            _category_marker_style(entry.category, entry.subcategory),
            certified=entry.certified,
        )
    return {
        "id": f"{entry.entity_type}_{entry.entity_id}",
        "entity_type": entry.entity_type,
        "title": entry.display_name,
        "category": entry.category or "",
        "subcategory": entry.subcategory or "",
        "latitude": _safe_float(entry.latitude),
        "longitude": _safe_float(entry.longitude),
        "marker": marker,
        "quality": _quality_from_flags(entry.quality_score, entry.quality_flags),
    }


def build_map_marker(
    record: Event | PoiLocation | EventVenue | Region | AppSearchIndex,
) -> dict[str, Any]:
    """Build app-safe marker display metadata without returning image/icon assets."""

    if isinstance(record, Event):
        return _marker_from_event(record)
    if isinstance(record, PoiLocation):
        return _marker_from_poi(record)
    if isinstance(record, EventVenue):
        return _marker_from_venue(record)
    if isinstance(record, Region):
        return _marker_from_region(record)
    return _marker_from_index(record)


def _bounded_limit(limit: int) -> int:
    return max(1, min(limit, 1000))


def _bounded_offset(offset: int) -> int:
    return max(0, offset)


def list_map_markers(
    db: Session,
    filters: MapMarkerFilters | None = None,
) -> dict[str, Any]:
    """Return event, POI, venue, and region marker metadata for private app feeds."""

    filters = filters or MapMarkerFilters()
    entity_type = filters.entity_type
    markers: list[dict[str, Any]] = []

    if entity_type in (None, AppSearchEntityType.event.value):
        event_stmt = select(Event).options(selectinload(Event.venue)).where(
            Event.publish_status.in_(PUBLISHABLE_STATUSES),
            Event.duplicate_status.not_in(DUPLICATE_EXCLUDE_STATUSES),
            Event.record_type == "event",
            Event.category == "Concert",
        )
        if filters.region_id:
            event_stmt = event_stmt.where(Event.region_id == filters.region_id)
        if filters.date_from:
            event_stmt = event_stmt.where(
                Event.start_datetime >= datetime.combine(filters.date_from, time.min),
            )
        if filters.date_to:
            event_stmt = event_stmt.where(
                Event.start_datetime <= datetime.combine(filters.date_to, time.max),
            )
        if filters.city or filters.state or filters.country:
            event_stmt = event_stmt.join(Event.venue)
            if filters.city:
                event_stmt = event_stmt.where(EventVenue.city == filters.city)
            if filters.state:
                event_stmt = event_stmt.where(EventVenue.state == filters.state)
            if filters.country:
                event_stmt = event_stmt.where(EventVenue.country == filters.country)
        if filters.has_upcoming_events is True:
            event_stmt = event_stmt.where(Event.start_datetime >= utc_now())
        elif filters.has_upcoming_events is False:
            event_stmt = event_stmt.where(Event.start_datetime < utc_now())
        markers.extend(
            build_map_marker(event) for event in db.scalars(event_stmt).all()
        )

    if entity_type in (None, AppSearchEntityType.poi.value):
        poi_stmt = select(PoiLocation).where(
            PoiLocation.publish_status.in_(PUBLISHABLE_STATUSES),
            PoiLocation.category != "Concert",
        )
        if filters.category:
            poi_stmt = poi_stmt.where(PoiLocation.category == filters.category)
        if filters.subcategory:
            poi_stmt = poi_stmt.where(PoiLocation.subcategory == filters.subcategory)
        if filters.region_id:
            poi_stmt = poi_stmt.where(PoiLocation.region_id == filters.region_id)
        if filters.city:
            poi_stmt = poi_stmt.where(PoiLocation.city == filters.city)
        if filters.state:
            poi_stmt = poi_stmt.where(PoiLocation.state == filters.state)
        if filters.country:
            poi_stmt = poi_stmt.where(PoiLocation.country == filters.country)
        if filters.certified is not None:
            poi_stmt = poi_stmt.where(PoiLocation.certified.is_(filters.certified))
        markers.extend(build_map_marker(poi) for poi in db.scalars(poi_stmt).all())

    if entity_type == AppSearchEntityType.venue.value:
        venue_stmt = select(EventVenue)
        if filters.city:
            venue_stmt = venue_stmt.where(EventVenue.city == filters.city)
        if filters.state:
            venue_stmt = venue_stmt.where(EventVenue.state == filters.state)
        if filters.country:
            venue_stmt = venue_stmt.where(EventVenue.country == filters.country)
        if filters.category:
            venue_stmt = venue_stmt.where(EventVenue.category == filters.category)
        if filters.subcategory:
            venue_stmt = venue_stmt.where(EventVenue.subcategory == filters.subcategory)
        markers.extend(
            build_map_marker(venue) for venue in db.scalars(venue_stmt).all()
        )

    if entity_type == AppSearchEntityType.region.value:
        region_stmt = select(Region)
        if filters.region_id:
            region_stmt = region_stmt.where(Region.id == filters.region_id)
        if filters.city:
            region_stmt = region_stmt.where(Region.city == filters.city)
        if filters.state:
            region_stmt = region_stmt.where(Region.state == filters.state)
        if filters.country:
            region_stmt = region_stmt.where(Region.country == filters.country)
        if filters.certified is not None:
            region_stmt = region_stmt.where(Region.certified.is_(filters.certified))
        markers.extend(
            build_map_marker(region) for region in db.scalars(region_stmt).all()
        )

    offset = _bounded_offset(filters.offset)
    limit = _bounded_limit(filters.limit)
    paged = markers[offset : offset + limit]
    return {
        "export_type": "map_markers",
        "count": len(paged),
        "total": len(markers),
        "limit": limit,
        "offset": offset,
        "records": paged,
    }


def _count_event_range(events: list[Event], days: int) -> int:
    now = utc_now()
    end = now + timedelta(days=days)
    count = 0
    for event in events:
        event_start = _as_aware_utc(event.start_datetime)
        if event_start is not None and now <= event_start <= end:
            count += 1
    return count


def build_filter_options(
    db: Session,
    region_id: int | None = None,
) -> dict[str, Any]:
    """Build event and POI filter options without mixing Concert into POI filters."""

    event_stmt = select(Event).options(selectinload(Event.venue)).where(
        Event.publish_status.in_(PUBLISHABLE_STATUSES),
        Event.duplicate_status.not_in(DUPLICATE_EXCLUDE_STATUSES),
        Event.record_type == "event",
        Event.category == "Concert",
    )
    poi_stmt = select(PoiLocation).where(
        PoiLocation.publish_status.in_(PUBLISHABLE_STATUSES),
        PoiLocation.category != "Concert",
    )
    if region_id is not None:
        event_stmt = event_stmt.where(Event.region_id == region_id)
        poi_stmt = poi_stmt.where(PoiLocation.region_id == region_id)
    events = list(db.scalars(event_stmt).all())
    pois = list(db.scalars(poi_stmt).all())
    itinerary_stmt = select(Itinerary).where(
        Itinerary.status.in_(("approved", "published")),
    )
    if region_id is not None:
        itinerary_stmt = itinerary_stmt.where(Itinerary.region_id == region_id)
    itineraries = list(db.scalars(itinerary_stmt).all())

    genre_counts: dict[str, int] = {}
    city_counts: dict[str, int] = {}
    state_counts: dict[str, int] = {}
    quality_counts: dict[str, int] = {}
    for event in events:
        event_genres = event.normalized_genres or [
            genre
            for genre in [event.normalized_genre, event.genre, event.music_category]
            if genre
        ]
        for genre in event_genres:
            if genre:
                genre_counts[genre] = genre_counts.get(genre, 0) + 1
        if event.venue and event.venue.city:
            city_counts[event.venue.city] = city_counts.get(event.venue.city, 0) + 1
        if event.venue and event.venue.state:
            state_counts[event.venue.state] = state_counts.get(event.venue.state, 0) + 1
        _, blockers, flags = event_publish_readiness(event)
        for flag in blockers + flags:
            quality_counts[flag] = quality_counts.get(flag, 0) + 1

    category_counts: dict[str, dict[str, int]] = {}
    certified_counts = {True: 0, False: 0}
    for poi in pois:
        category = poi.category or "Unknown"
        if category == "Concert":
            continue
        category_counts.setdefault(category, {})
        if poi.subcategory:
            subcounts = category_counts[category]
            subcounts[poi.subcategory] = subcounts.get(poi.subcategory, 0) + 1
        certified_counts[bool(poi.certified)] += 1

    return {
        "event_filters": {
            "date_ranges": [
                {
                    "key": "next_7_days",
                    "label": "Next 7 days",
                    "count": _count_event_range(events, 7),
                },
                {
                    "key": "next_30_days",
                    "label": "Next 30 days",
                    "count": _count_event_range(events, 30),
                },
                {
                    "key": "next_90_days",
                    "label": "Next 90 days",
                    "count": _count_event_range(events, 90),
                },
            ],
            "genres": [
                {"name": key, "count": genre_counts[key]}
                for key in sorted(genre_counts)
            ],
            "cities": [
                {"name": key, "count": city_counts[key]} for key in sorted(city_counts)
            ],
            "states": [
                {"name": key, "count": state_counts[key]}
                for key in sorted(state_counts)
            ],
            "quality_flags": [
                {"name": key, "count": quality_counts[key]}
                for key in sorted(quality_counts)
            ],
        },
        "poi_filters": {
            "categories": [
                {
                    "name": category,
                    "count": sum(subcounts.values())
                    or sum(1 for poi in pois if poi.category == category),
                    "subcategories": [
                        {"name": subcategory, "count": subcounts[subcategory]}
                        for subcategory in sorted(subcounts)
                    ],
                }
                for category, subcounts in sorted(category_counts.items())
            ],
            "certified": [
                {"value": True, "count": certified_counts[True]},
                {"value": False, "count": certified_counts[False]},
            ],
        },
        "itinerary_filters": {
            "types": [
                {"name": key, "count": count}
                for key, count in sorted(
                    {
                        itinerary_type: sum(
                            1
                            for itinerary in itineraries
                            if itinerary.itinerary_type == itinerary_type
                        )
                        for itinerary_type in {
                            itinerary.itinerary_type
                            for itinerary in itineraries
                        }
                    }.items()
                )
            ],
            "regions": [
                {"region_id": key, "count": count}
                for key, count in sorted(
                    {
                        region_key: sum(
                            1
                            for itinerary in itineraries
                            if itinerary.region_id == region_key
                        )
                        for region_key in {
                            itinerary.region_id
                            for itinerary in itineraries
                            if itinerary.region_id is not None
                        }
                    }.items()
                )
            ],
        },
        "active_filter_display_rules": {
            "show_badge": True,
            "show_count": True,
            "recommended_active_indicator": "solid_button_or_dot",
        },
    }


DEFAULT_DISCOVERY_SLOTS = (
    {
        "slot_key": "upcoming_concerts",
        "slot_type": DiscoverySlotType.event_carousel.value,
        "title": "Upcoming Concerts",
        "description": "App-ready Concert event carousel placeholder.",
        "sort_order": 10,
        "payload": {"entity_type": "event", "contract_only": True},
    },
    {
        "slot_key": "road_trips_and_tours",
        "slot_type": DiscoverySlotType.itinerary_carousel.value,
        "title": "Road Trips & Tours",
        "description": "Itinerary-style Road Trip, Tour, Setlist, and Route cards.",
        "sort_order": 15,
        "payload": {"entity_type": "itinerary", "contract_only": True},
    },
    {
        "slot_key": "music_sites",
        "slot_type": DiscoverySlotType.poi_carousel.value,
        "title": "Music Sites",
        "description": "POI-style places for regional discovery.",
        "sort_order": 20,
        "payload": {"entity_type": "poi", "category": "Music Site"},
    },
    {
        "slot_key": "certified_regions",
        "slot_type": DiscoverySlotType.region_carousel.value,
        "title": "Certified Music Regions",
        "description": "Region-level discovery placeholder.",
        "sort_order": 30,
        "payload": {"entity_type": "region", "certified": True},
    },
)


def ensure_default_discovery_slots(db: Session) -> None:
    """Seed global discovery slots for local contract demos."""

    existing = set(db.scalars(select(AppDiscoverySlot.slot_key)).all())
    for slot in DEFAULT_DISCOVERY_SLOTS:
        if str(slot["slot_key"]) in existing:
            continue
        db.add(
            AppDiscoverySlot(
                slot_key=str(slot["slot_key"]),
                slot_type=str(slot["slot_type"]),
                title=str(slot["title"]),
                description=str(slot["description"]),
                enabled=True,
                sort_order=_int_value(slot["sort_order"], default=100),
                payload_json=json.dumps(slot["payload"]),
            ),
        )
    db.commit()


def list_discovery_slots(
    db: Session,
    region_id: int | None = None,
) -> dict[str, Any]:
    """Return enabled discovery slots for global or region-specific app feeds."""

    ensure_default_discovery_slots(db)
    stmt = select(AppDiscoverySlot).where(AppDiscoverySlot.enabled.is_(True))
    if region_id is None:
        stmt = stmt.where(AppDiscoverySlot.region_id.is_(None))
    else:
        stmt = stmt.where(AppDiscoverySlot.region_id == region_id)
    slots = list(
        db.scalars(
            stmt.order_by(AppDiscoverySlot.sort_order.asc(), AppDiscoverySlot.id.asc()),
        ).all(),
    )
    records = [
        {
            "id": f"discovery_slot_{slot.id}",
            "slot_key": slot.slot_key,
            "slot_type": slot.slot_type,
            "title": slot.title,
            "description": slot.description or "",
            "region_id": slot.region_id,
            "enabled": slot.enabled,
            "sort_order": slot.sort_order,
            "payload": slot.payload,
        }
        for slot in slots
    ]
    return {
        "export_type": "discovery",
        "region_id": region_id,
        "count": len(records),
        "records": records,
    }
