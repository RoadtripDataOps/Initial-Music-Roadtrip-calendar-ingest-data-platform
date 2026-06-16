from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast
from urllib.parse import quote_plus

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    CanonicalArtist,
    DestinationPartner,
    Event,
    EventArtist,
    EventVenue,
    Itinerary,
    ItineraryDisplayLabel,
    ItineraryRouteProvider,
    ItinerarySegment,
    ItineraryStatus,
    ItineraryStop,
    ItineraryStopType,
    ItineraryType,
    PoiLocation,
    PublishStatus,
    Region,
    utc_now,
)
from app.services.app_feed_service import (
    DUPLICATE_EXCLUDE_STATUSES,
    LOGO_ASSET_MARKERS,
    PUBLISHABLE_STATUSES,
)

APP_FEED_STATUSES = {
    ItineraryStatus.approved.value,
    ItineraryStatus.published.value,
}
REGIONAL_ITINERARY_TYPES = {
    ItineraryType.city_tour.value,
    ItineraryType.festival_weekend.value,
    ItineraryType.certified_region.value,
}


@dataclass(frozen=True)
class ItineraryCreate:
    title: str
    itinerary_type: str = ItineraryType.road_trip.value
    display_label: str | None = None
    subtitle: str | None = None
    description: str | None = None
    status: str = ItineraryStatus.draft.value
    region_id: int | None = None
    destination_partner_id: int | None = None
    artist_id: int | None = None
    start_city: str | None = None
    start_state: str | None = None
    start_country: str | None = None
    end_city: str | None = None
    end_state: str | None = None
    end_country: str | None = None
    estimated_duration_text: str | None = None
    estimated_distance_text: str | None = None
    hero_image_url: str | None = None
    image_status: str | None = None
    image_candidate_id: int | None = None
    music_theme: str | None = None
    normalized_genres: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    featured: bool = False
    sponsored_future: bool = False
    sort_order: int = 100
    created_by: str | None = None


@dataclass(frozen=True)
class ItineraryUpdate:
    title: str | None = None
    itinerary_type: str | None = None
    display_label: str | None = None
    subtitle: str | None = None
    description: str | None = None
    status: str | None = None
    region_id: int | None = None
    destination_partner_id: int | None = None
    artist_id: int | None = None
    start_city: str | None = None
    start_state: str | None = None
    start_country: str | None = None
    end_city: str | None = None
    end_state: str | None = None
    end_country: str | None = None
    estimated_duration_text: str | None = None
    estimated_distance_text: str | None = None
    hero_image_url: str | None = None
    image_status: str | None = None
    image_candidate_id: int | None = None
    music_theme: str | None = None
    normalized_genres: list[str] | None = None
    tags: list[str] | None = None
    featured: bool | None = None
    sponsored_future: bool | None = None
    sort_order: int | None = None


@dataclass(frozen=True)
class ItineraryStopInput:
    stop_type: str = ItineraryStopType.custom.value
    event_id: int | None = None
    poi_location_id: int | None = None
    event_venue_id: int | None = None
    region_id: int | None = None
    artist_id: int | None = None
    title: str | None = None
    subtitle: str | None = None
    description: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    start_datetime: datetime | None = None
    end_datetime: datetime | None = None
    stop_duration_text: str | None = None
    ticket_url: str | None = None
    website_url: str | None = None
    image_url: str | None = None
    image_status: str | None = None
    app_url: str | None = None
    notes: str | None = None


def normalize_itinerary_key(text: str) -> str:
    value = unicodedata.normalize("NFKD", text or "")
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return re.sub(r"-+", "-", value) or "itinerary"


def _clean(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _json_list(values: list[str]) -> str:
    return json.dumps([item for item in values if item.strip()])


def _list_from_text(value: str | None) -> list[str]:
    if not value:
        return []
    if value.strip().startswith("["):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = []
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    return [part.strip() for part in value.split(",") if part.strip()]


def _iso_datetime(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def _is_logo_asset(value: str | None) -> bool:
    if not value:
        return False
    lowered = value.lower()
    return any(marker in lowered for marker in LOGO_ASSET_MARKERS)


def _safe_float(value: float | None) -> float | None:
    return float(value) if value is not None else None


def _optional_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(cast("Any", value))
    except (TypeError, ValueError):
        return None


def _display_label_for_type(itinerary_type: str, display_label: str | None) -> str:
    if display_label:
        return display_label
    if itinerary_type == ItineraryType.road_trip.value:
        return ItineraryDisplayLabel.road_trip.value
    if itinerary_type == ItineraryType.artist_tour.value:
        return ItineraryDisplayLabel.tour.value
    if itinerary_type in {
        ItineraryType.city_tour.value,
        ItineraryType.venue_hop.value,
        ItineraryType.record_store_crawl.value,
        ItineraryType.certified_region.value,
    }:
        return ItineraryDisplayLabel.tour.value
    return ItineraryDisplayLabel.route.value


def _unique_slug(session: Session, title: str, itinerary_id: int | None = None) -> str:
    base = normalize_itinerary_key(title)
    slug = base
    suffix = 2
    while True:
        stmt = select(Itinerary).where(Itinerary.slug == slug)
        if itinerary_id is not None:
            stmt = stmt.where(Itinerary.id != itinerary_id)
        existing = session.scalars(stmt).first()
        if existing is None:
            return slug
        slug = f"{base}-{suffix}"
        suffix += 1


def _itinerary_query() -> Any:
    return (
        select(Itinerary)
        .options(
            selectinload(Itinerary.region),
            selectinload(Itinerary.destination_partner),
            selectinload(Itinerary.artist),
            selectinload(Itinerary.stops).selectinload(ItineraryStop.event),
            selectinload(Itinerary.stops).selectinload(ItineraryStop.poi_location),
            selectinload(Itinerary.stops).selectinload(ItineraryStop.event_venue),
            selectinload(Itinerary.stops).selectinload(ItineraryStop.region),
            selectinload(Itinerary.stops).selectinload(ItineraryStop.artist),
            selectinload(Itinerary.segments).selectinload(ItinerarySegment.from_stop),
            selectinload(Itinerary.segments).selectinload(ItinerarySegment.to_stop),
        )
    )


def get_itinerary(session: Session, itinerary_id: int) -> Itinerary | None:
    return session.scalars(
        _itinerary_query().where(Itinerary.id == itinerary_id)
    ).first()


def list_itineraries(session: Session) -> list[Itinerary]:
    return list(
        session.scalars(
            _itinerary_query().order_by(
                Itinerary.sort_order.asc(),
                Itinerary.updated_at.desc(),
                Itinerary.id.desc(),
            )
        ).all()
    )


def create_itinerary(
    session: Session,
    data: ItineraryCreate | None = None,
    **values: object,
) -> Itinerary:
    payload = data or ItineraryCreate(**cast("Any", values))
    title = _clean(payload.title)
    if title is None:
        raise ValueError("Itinerary title is required.")
    itinerary_type = payload.itinerary_type or ItineraryType.road_trip.value
    slug = _unique_slug(session, title)
    itinerary = Itinerary(
        itinerary_key=f"{itinerary_type}:{slug}",
        slug=slug,
        title=title,
        subtitle=_clean(payload.subtitle),
        description=_clean(payload.description),
        itinerary_type=itinerary_type,
        display_label=_display_label_for_type(itinerary_type, payload.display_label),
        status=payload.status or ItineraryStatus.draft.value,
        region_id=payload.region_id,
        destination_partner_id=payload.destination_partner_id,
        artist_id=payload.artist_id,
        start_city=_clean(payload.start_city),
        start_state=_clean(payload.start_state),
        start_country=_clean(payload.start_country),
        end_city=_clean(payload.end_city),
        end_state=_clean(payload.end_state),
        end_country=_clean(payload.end_country),
        estimated_duration_text=_clean(payload.estimated_duration_text),
        estimated_distance_text=_clean(payload.estimated_distance_text),
        hero_image_url=_clean(payload.hero_image_url),
        image_status=_clean(payload.image_status),
        image_candidate_id=payload.image_candidate_id,
        music_theme=_clean(payload.music_theme),
        normalized_genres_json=_json_list(payload.normalized_genres),
        tags_json=_json_list(payload.tags),
        featured=payload.featured,
        sponsored_future=payload.sponsored_future,
        sort_order=payload.sort_order,
        created_by=_clean(payload.created_by),
    )
    if itinerary.status == ItineraryStatus.published.value:
        itinerary.published_at = utc_now()
    session.add(itinerary)
    session.commit()
    session.refresh(itinerary)
    compute_itinerary_quality(session, itinerary.id)
    refreshed = get_itinerary(session, itinerary.id)
    if refreshed is None:
        raise ValueError("Created itinerary could not be reloaded.")
    return refreshed


def update_itinerary(
    session: Session,
    itinerary_id: int,
    data: ItineraryUpdate | None = None,
    **updates: object,
) -> Itinerary:
    itinerary = session.get(Itinerary, itinerary_id)
    if itinerary is None:
        raise ValueError("Itinerary not found.")
    payload = data or ItineraryUpdate(**cast("Any", updates))
    scalar_fields = {
        "subtitle",
        "description",
        "status",
        "region_id",
        "destination_partner_id",
        "artist_id",
        "start_city",
        "start_state",
        "start_country",
        "end_city",
        "end_state",
        "end_country",
        "estimated_duration_text",
        "estimated_distance_text",
        "hero_image_url",
        "image_status",
        "image_candidate_id",
        "music_theme",
        "featured",
        "sponsored_future",
        "sort_order",
    }
    if payload.title is not None:
        title = _clean(payload.title)
        if title is None:
            raise ValueError("Itinerary title is required.")
        itinerary.title = title
        itinerary.slug = _unique_slug(session, title, itinerary_id=itinerary.id)
        itinerary.itinerary_key = f"{itinerary.itinerary_type}:{itinerary.slug}"
    if payload.itinerary_type is not None:
        itinerary.itinerary_type = payload.itinerary_type
        itinerary.itinerary_key = f"{itinerary.itinerary_type}:{itinerary.slug}"
        if payload.display_label is None:
            itinerary.display_label = _display_label_for_type(
                itinerary.itinerary_type,
                None,
            )
    if payload.display_label is not None:
        itinerary.display_label = payload.display_label
    for field_name in scalar_fields:
        value = getattr(payload, field_name)
        if value is None:
            continue
        setattr(
            itinerary,
            field_name,
            _clean(value) if isinstance(value, str) else value,
        )
    if payload.normalized_genres is not None:
        itinerary.normalized_genres_json = _json_list(payload.normalized_genres)
    if payload.tags is not None:
        itinerary.tags_json = _json_list(payload.tags)
    if (
        itinerary.status == ItineraryStatus.published.value
        and itinerary.published_at is None
    ):
        itinerary.published_at = utc_now()
    if itinerary.status != ItineraryStatus.published.value:
        itinerary.published_at = None
    itinerary.updated_at = utc_now()
    session.add(itinerary)
    session.commit()
    compute_itinerary_quality(session, itinerary.id)
    refreshed = get_itinerary(session, itinerary.id)
    if refreshed is None:
        raise ValueError("Updated itinerary could not be reloaded.")
    return refreshed


def _event_stop_snapshot(event: Event) -> dict[str, object]:
    venue = event.venue
    return {
        "title": event.title,
        "subtitle": event.headliner or "Concert event",
        "description": event.description,
        "address": venue.address if venue else None,
        "city": venue.city if venue else None,
        "state": venue.state if venue else None,
        "country": venue.country if venue else None,
        "latitude": venue.latitude if venue else None,
        "longitude": venue.longitude if venue else None,
        "start_datetime": event.start_datetime,
        "end_datetime": event.end_datetime,
        "ticket_url": event.recommended_ticket_link or event.tickets_link,
        "website_url": event.source_url,
        "image_url": event.selected_main_image_url or event.main_image_url,
        "image_status": event.image_status,
        "app_url": f"/events/event-{event.id}",
    }


def _poi_stop_snapshot(poi: PoiLocation) -> dict[str, object]:
    if (poi.category or "").strip() == "Concert":
        raise ValueError("Concert records cannot be used as POI itinerary stops.")
    return {
        "title": poi.display_name,
        "subtitle": " · ".join(
            part for part in [poi.category, poi.subcategory] if part
        ),
        "description": poi.description,
        "address": poi.address,
        "city": poi.city,
        "state": poi.state,
        "country": poi.country,
        "latitude": poi.latitude,
        "longitude": poi.longitude,
        "website_url": poi.website,
        "image_url": poi.main_image_url,
        "image_status": "available" if poi.main_image_url else "missing",
        "app_url": f"/pois/poi-{poi.id}",
    }


def _venue_stop_snapshot(venue: EventVenue) -> dict[str, object]:
    return {
        "title": venue.display_name,
        "subtitle": " · ".join(
            part for part in [venue.category, venue.subcategory] if part
        ),
        "description": venue.description,
        "address": venue.address,
        "city": venue.city,
        "state": venue.state,
        "country": venue.country,
        "latitude": venue.latitude,
        "longitude": venue.longitude,
        "website_url": venue.website,
        "image_url": venue.selected_main_image_url or venue.main_image_url,
        "image_status": venue.image_status,
        "app_url": f"/venues/venue-{venue.id}",
    }


def _region_stop_snapshot(region: Region) -> dict[str, object]:
    return {
        "title": region.name,
        "subtitle": region.region_type.replace("_", " ").title(),
        "description": region.description,
        "city": region.city,
        "state": region.state,
        "country": region.country,
        "latitude": region.latitude,
        "longitude": region.longitude,
        "app_url": f"/regions/{region.slug or region.id}",
    }


def _artist_stop_snapshot(artist: CanonicalArtist) -> dict[str, object]:
    return {
        "title": artist.display_name,
        "subtitle": artist.primary_genre or "Artist context",
        "description": None,
        "website_url": artist.official_website or artist.spotify_url,
        "image_url": artist.image_url,
        "image_status": artist.image_status,
        "app_url": f"/artists/artist-{artist.id}",
    }


def _apply_reference_snapshot(
    session: Session,
    stop_input: ItineraryStopInput,
) -> dict[str, object]:
    snapshot: dict[str, object] = {}
    if stop_input.stop_type == ItineraryStopType.event.value and stop_input.event_id:
        event = session.scalars(
            select(Event)
            .options(selectinload(Event.venue))
            .where(Event.id == stop_input.event_id)
        ).first()
        if event is None:
            raise ValueError("Referenced event was not found.")
        snapshot.update(_event_stop_snapshot(event))
    elif (
        stop_input.stop_type == ItineraryStopType.poi.value
        and stop_input.poi_location_id
    ):
        poi = session.get(PoiLocation, stop_input.poi_location_id)
        if poi is None:
            raise ValueError("Referenced POI was not found.")
        snapshot.update(_poi_stop_snapshot(poi))
    elif (
        stop_input.stop_type == ItineraryStopType.venue.value
        and stop_input.event_venue_id
    ):
        venue = session.get(EventVenue, stop_input.event_venue_id)
        if venue is None:
            raise ValueError("Referenced venue was not found.")
        snapshot.update(_venue_stop_snapshot(venue))
    elif (
        stop_input.stop_type == ItineraryStopType.region.value
        and stop_input.region_id
    ):
        region = session.get(Region, stop_input.region_id)
        if region is None:
            raise ValueError("Referenced region was not found.")
        snapshot.update(_region_stop_snapshot(region))
    elif (
        stop_input.stop_type == ItineraryStopType.artist_context.value
        and stop_input.artist_id
    ):
        artist = session.get(CanonicalArtist, stop_input.artist_id)
        if artist is None:
            raise ValueError("Referenced artist was not found.")
        snapshot.update(_artist_stop_snapshot(artist))
    overrides = {
        "title": stop_input.title,
        "subtitle": stop_input.subtitle,
        "description": stop_input.description,
        "address": stop_input.address,
        "city": stop_input.city,
        "state": stop_input.state,
        "country": stop_input.country,
        "latitude": stop_input.latitude,
        "longitude": stop_input.longitude,
        "start_datetime": stop_input.start_datetime,
        "end_datetime": stop_input.end_datetime,
        "stop_duration_text": stop_input.stop_duration_text,
        "ticket_url": stop_input.ticket_url,
        "website_url": stop_input.website_url,
        "image_url": stop_input.image_url,
        "image_status": stop_input.image_status,
        "app_url": stop_input.app_url,
        "notes": stop_input.notes,
    }
    for key, value in overrides.items():
        if value not in (None, ""):
            snapshot[key] = value
    return snapshot


def _next_stop_order(session: Session, itinerary_id: int) -> int:
    stops = list(
        session.scalars(
            select(ItineraryStop)
            .where(ItineraryStop.itinerary_id == itinerary_id)
            .order_by(ItineraryStop.stop_order.asc())
        ).all()
    )
    return len(stops) + 1


def add_stop(
    session: Session,
    itinerary_id: int,
    data: ItineraryStopInput | None = None,
    **values: object,
) -> ItineraryStop:
    itinerary = session.get(Itinerary, itinerary_id)
    if itinerary is None:
        raise ValueError("Itinerary not found.")
    stop_input = data or ItineraryStopInput(**cast("Any", values))
    snapshot = _apply_reference_snapshot(session, stop_input)
    title = _clean(snapshot.get("title"))
    if title is None:
        raise ValueError("Stop title is required.")
    stop = ItineraryStop(
        itinerary_id=itinerary.id,
        stop_order=_next_stop_order(session, itinerary.id),
        stop_type=stop_input.stop_type,
        event_id=stop_input.event_id,
        poi_location_id=stop_input.poi_location_id,
        event_venue_id=stop_input.event_venue_id,
        region_id=stop_input.region_id,
        artist_id=stop_input.artist_id,
        title=title,
        subtitle=_clean(snapshot.get("subtitle")),
        description=_clean(snapshot.get("description")),
        address=_clean(snapshot.get("address")),
        city=_clean(snapshot.get("city")),
        state=_clean(snapshot.get("state")),
        country=_clean(snapshot.get("country")),
        latitude=_optional_float(snapshot.get("latitude")),
        longitude=_optional_float(snapshot.get("longitude")),
        start_datetime=snapshot.get("start_datetime")
        if isinstance(snapshot.get("start_datetime"), datetime)
        else None,
        end_datetime=snapshot.get("end_datetime")
        if isinstance(snapshot.get("end_datetime"), datetime)
        else None,
        stop_duration_text=_clean(snapshot.get("stop_duration_text")),
        ticket_url=_clean(snapshot.get("ticket_url")),
        website_url=_clean(snapshot.get("website_url")),
        image_url=_clean(snapshot.get("image_url")),
        image_status=_clean(snapshot.get("image_status")),
        app_url=_clean(snapshot.get("app_url")),
        notes=_clean(snapshot.get("notes")),
    )
    session.add(stop)
    session.commit()
    session.refresh(stop)
    _renumber_stops(session, itinerary.id)
    _rebuild_segments(session, itinerary.id)
    compute_itinerary_quality(session, itinerary.id)
    session.refresh(stop)
    return stop


def _renumber_stops(session: Session, itinerary_id: int) -> None:
    stops = list(
        session.scalars(
            select(ItineraryStop)
            .where(ItineraryStop.itinerary_id == itinerary_id)
            .order_by(ItineraryStop.stop_order.asc(), ItineraryStop.id.asc())
        ).all()
    )
    for index, stop in enumerate(stops, start=1):
        stop.stop_order = index
        session.add(stop)
    session.commit()


def reorder_stops(
    session: Session,
    itinerary_id: int,
    stop_ids: list[int],
) -> list[ItineraryStop]:
    current = {
        stop.id: stop
        for stop in session.scalars(
            select(ItineraryStop).where(ItineraryStop.itinerary_id == itinerary_id)
        ).all()
    }
    if set(stop_ids) != set(current):
        raise ValueError("Stop order must include every stop exactly once.")
    for index, stop_id in enumerate(stop_ids, start=1):
        current[stop_id].stop_order = index
        session.add(current[stop_id])
    session.commit()
    _rebuild_segments(session, itinerary_id)
    compute_itinerary_quality(session, itinerary_id)
    return list(
        session.scalars(
            select(ItineraryStop)
            .where(ItineraryStop.itinerary_id == itinerary_id)
            .order_by(ItineraryStop.stop_order.asc())
        ).all()
    )


def move_stop(
    session: Session,
    itinerary_id: int,
    stop_id: int,
    direction: str,
) -> list[ItineraryStop]:
    stops = list(
        session.scalars(
            select(ItineraryStop)
            .where(ItineraryStop.itinerary_id == itinerary_id)
            .order_by(ItineraryStop.stop_order.asc(), ItineraryStop.id.asc())
        ).all()
    )
    ids = [stop.id for stop in stops]
    if stop_id not in ids:
        raise ValueError("Stop not found on itinerary.")
    index = ids.index(stop_id)
    target = index - 1 if direction == "up" else index + 1
    if target < 0 or target >= len(ids):
        return stops
    ids[index], ids[target] = ids[target], ids[index]
    return reorder_stops(session, itinerary_id, ids)


def remove_stop(session: Session, itinerary_id: int, stop_id: int) -> None:
    stop = session.get(ItineraryStop, stop_id)
    if stop is None or stop.itinerary_id != itinerary_id:
        raise ValueError("Stop not found on itinerary.")
    session.execute(
        delete(ItinerarySegment).where(ItinerarySegment.itinerary_id == itinerary_id)
    )
    session.flush()
    session.delete(stop)
    session.commit()
    _renumber_stops(session, itinerary_id)
    _rebuild_segments(session, itinerary_id)
    compute_itinerary_quality(session, itinerary_id)


def _location_query(stop: ItineraryStop) -> str:
    if stop.latitude is not None and stop.longitude is not None:
        return f"{stop.latitude},{stop.longitude}"
    return ", ".join(
        part
        for part in [stop.address, stop.city, stop.state, stop.country]
        if part
    )


def build_external_navigation_link(
    stop_or_segment: ItineraryStop | ItinerarySegment,
    provider: str = ItineraryRouteProvider.google_maps_external.value,
) -> str:
    if provider == ItineraryRouteProvider.none.value:
        return ""
    if isinstance(stop_or_segment, ItinerarySegment):
        from_query = (
            _location_query(stop_or_segment.from_stop)
            if stop_or_segment.from_stop
            else ""
        )
        to_query = (
            _location_query(stop_or_segment.to_stop) if stop_or_segment.to_stop else ""
        )
        if not from_query or not to_query:
            return ""
        if provider == ItineraryRouteProvider.apple_maps_external.value:
            return (
                "https://maps.apple.com/?saddr="
                f"{quote_plus(from_query)}&daddr={quote_plus(to_query)}"
            )
        return (
            "https://www.google.com/maps/dir/?api=1&origin="
            f"{quote_plus(from_query)}&destination={quote_plus(to_query)}"
        )
    query = _location_query(stop_or_segment)
    if not query:
        return ""
    if provider == ItineraryRouteProvider.apple_maps_external.value:
        return f"https://maps.apple.com/?q={quote_plus(query)}"
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(query)}"


def _distance_miles(from_stop: ItineraryStop, to_stop: ItineraryStop) -> float | None:
    if (
        from_stop.latitude is None
        or from_stop.longitude is None
        or to_stop.latitude is None
        or to_stop.longitude is None
    ):
        return None
    radius_miles = 3958.8
    lat1 = math.radians(from_stop.latitude)
    lat2 = math.radians(to_stop.latitude)
    delta_lat = math.radians(to_stop.latitude - from_stop.latitude)
    delta_lon = math.radians(to_stop.longitude - from_stop.longitude)
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    return round(2 * radius_miles * math.asin(math.sqrt(haversine)), 1)


def _drive_time_text(distance: float | None) -> str | None:
    if distance is None:
        return None
    minutes = max(1, round((distance / 28) * 60))
    if minutes < 60:
        return f"{minutes} min drive"
    hours = minutes // 60
    remainder = minutes % 60
    return f"{hours} hr {remainder} min drive" if remainder else f"{hours} hr drive"


def _walk_time_text(distance: float | None) -> str | None:
    if distance is None or distance > 3:
        return None
    minutes = max(1, round((distance / 3) * 60))
    return f"{minutes} min walk"


def _rebuild_segments(session: Session, itinerary_id: int) -> None:
    session.execute(
        delete(ItinerarySegment).where(ItinerarySegment.itinerary_id == itinerary_id)
    )
    session.flush()
    stops = list(
        session.scalars(
            select(ItineraryStop)
            .where(ItineraryStop.itinerary_id == itinerary_id)
            .order_by(ItineraryStop.stop_order.asc(), ItineraryStop.id.asc())
        ).all()
    )
    for index, (from_stop, to_stop) in enumerate(
        zip(stops, stops[1:], strict=False),
        start=1,
    ):
        distance = _distance_miles(from_stop, to_stop)
        segment = ItinerarySegment(
            itinerary_id=itinerary_id,
            from_stop_id=from_stop.id,
            to_stop_id=to_stop.id,
            segment_order=index,
            distance_miles=distance,
            estimated_drive_time_text=_drive_time_text(distance),
            estimated_walk_time_text=_walk_time_text(distance),
            route_provider=ItineraryRouteProvider.google_maps_external.value,
        )
        session.add(segment)
        session.flush()
        segment.from_stop = from_stop
        segment.to_stop = to_stop
        segment.navigation_url = build_external_navigation_link(segment)
        session.add(segment)
    session.commit()
    session.expire_all()


def compute_itinerary_quality(
    session: Session,
    itinerary_or_id: int | Itinerary,
) -> tuple[int, list[str]]:
    if isinstance(itinerary_or_id, int):
        session.expire_all()
    itinerary = (
        get_itinerary(session, itinerary_or_id)
        if isinstance(itinerary_or_id, int)
        else itinerary_or_id
    )
    if itinerary is None:
        raise ValueError("Itinerary not found.")
    flags: list[str] = []
    score = 100

    if not itinerary.title.strip():
        flags.append("missing_title")
        score -= 25
    if len(itinerary.stops) < 2:
        flags.append("too_few_stops")
        score -= 25
    if itinerary.status not in APP_FEED_STATUSES:
        flags.append("not_approved_or_published")
        score -= 10
    if not itinerary.hero_image_url:
        flags.append("missing_hero_image")
        score -= 8
    elif _is_logo_asset(itinerary.hero_image_url):
        flags.append("logo_asset_image")
        score -= 40

    duplicate_poi_ids: set[int] = set()
    seen_poi_ids: set[int] = set()
    for stop in itinerary.stops:
        if not _location_query(stop):
            flags.append(f"stop_{stop.stop_order}_missing_location")
            score -= 8
        if not stop.image_url:
            flags.append(f"stop_{stop.stop_order}_missing_image")
            score -= 3
        elif _is_logo_asset(stop.image_url):
            flags.append(f"stop_{stop.stop_order}_logo_asset_image")
            score -= 20
        if stop.event and (
            stop.event.publish_status in {
                PublishStatus.rejected.value,
                PublishStatus.archived.value,
                PublishStatus.stale.value,
            }
            or stop.event.duplicate_status in DUPLICATE_EXCLUDE_STATUSES
        ):
            flags.append(f"stop_{stop.stop_order}_rejected_or_merged_event")
            score -= 20
        if stop.poi_location_id:
            if stop.poi_location_id in seen_poi_ids:
                duplicate_poi_ids.add(stop.poi_location_id)
            seen_poi_ids.add(stop.poi_location_id)
    if duplicate_poi_ids:
        flags.append("duplicate_poi_stops")
        score -= 12
    if itinerary.itinerary_type in REGIONAL_ITINERARY_TYPES and not itinerary.region_id:
        flags.append("missing_region")
        score -= 12
    if (
        itinerary.itinerary_type == ItineraryType.artist_tour.value
        and not itinerary.artist_id
    ):
        flags.append("missing_artist")
        score -= 12

    score = max(0, min(100, score))
    itinerary.quality_score = float(score)
    itinerary.quality_flags_json = json.dumps(list(dict.fromkeys(flags)))
    itinerary.app_feed_ready = itinerary.status in APP_FEED_STATUSES and score >= 70
    if (
        itinerary.status == ItineraryStatus.published.value
        and itinerary.published_at is None
    ):
        itinerary.published_at = utc_now()
    session.add(itinerary)
    session.commit()
    return score, list(dict.fromkeys(flags))


def _region_payload(region: Region | None) -> dict[str, object]:
    if region is None:
        return {}
    return {
        "region_id": f"region-{region.id}",
        "slug": region.slug,
        "name": region.name,
        "type": region.region_type,
        "city": region.city or "",
        "state": region.state or "",
        "country": region.country or "",
    }


def _artist_payload(artist: CanonicalArtist | None) -> dict[str, object]:
    if artist is None:
        return {}
    return {
        "artist_id": f"artist-{artist.id}",
        "name": artist.display_name,
        "primary_genre": artist.primary_genre or "",
        "image_url": "" if _is_logo_asset(artist.image_url) else artist.image_url or "",
    }


def _stop_payload(stop: ItineraryStop) -> dict[str, object]:
    image_url = "" if _is_logo_asset(stop.image_url) else stop.image_url or ""
    return {
        "stop_id": f"itinerary_stop-{stop.id}",
        "stop_order": stop.stop_order,
        "stop_type": stop.stop_type,
        "reference": {
            "event_id": f"event-{stop.event_id}" if stop.event_id else "",
            "poi_id": f"poi-{stop.poi_location_id}" if stop.poi_location_id else "",
            "venue_id": f"venue-{stop.event_venue_id}" if stop.event_venue_id else "",
            "region_id": f"region-{stop.region_id}" if stop.region_id else "",
            "artist_id": f"artist-{stop.artist_id}" if stop.artist_id else "",
        },
        "title": stop.title,
        "subtitle": stop.subtitle or "",
        "description": stop.description or "",
        "location": {
            "address": stop.address or "",
            "city": stop.city or "",
            "state": stop.state or "",
            "country": stop.country or "",
            "latitude": _safe_float(stop.latitude),
            "longitude": _safe_float(stop.longitude),
        },
        "schedule": {
            "start_datetime": _iso_datetime(stop.start_datetime),
            "end_datetime": _iso_datetime(stop.end_datetime),
            "duration_text": stop.stop_duration_text or "",
        },
        "links": {
            "ticket_url": stop.ticket_url or "",
            "website_url": stop.website_url or "",
            "app_url": stop.app_url or "",
            "navigation_url": build_external_navigation_link(stop),
        },
        "image": {
            "url": image_url,
            "status": stop.image_status or ("available" if image_url else "missing"),
        },
    }


def _segment_payload(segment: ItinerarySegment) -> dict[str, object]:
    return {
        "segment_id": f"itinerary_segment-{segment.id}",
        "segment_order": segment.segment_order,
        "from_stop_id": (
            f"itinerary_stop-{segment.from_stop_id}" if segment.from_stop_id else ""
        ),
        "to_stop_id": f"itinerary_stop-{segment.to_stop_id}"
        if segment.to_stop_id
        else "",
        "distance_miles": _safe_float(segment.distance_miles),
        "estimated_drive_time_text": segment.estimated_drive_time_text or "",
        "estimated_walk_time_text": segment.estimated_walk_time_text or "",
        "navigation_url": segment.navigation_url or "",
        "route_provider": segment.route_provider,
    }


def build_itinerary_app_feed(
    session: Session,
    itinerary_or_id: int | Itinerary,
) -> dict[str, Any]:
    itinerary = (
        get_itinerary(session, itinerary_or_id)
        if isinstance(itinerary_or_id, int)
        else itinerary_or_id
    )
    if itinerary is None:
        raise ValueError("Itinerary not found.")
    hero_image_url = (
        ""
        if _is_logo_asset(itinerary.hero_image_url)
        else itinerary.hero_image_url or ""
    )
    return {
        "itinerary_id": f"itinerary-{itinerary.id}",
        "type": itinerary.itinerary_type,
        "display_label": itinerary.display_label,
        "title": itinerary.title,
        "subtitle": itinerary.subtitle or "",
        "description": itinerary.description or "",
        "region": _region_payload(itinerary.region),
        "artist": _artist_payload(itinerary.artist),
        "hero_image": {
            "url": hero_image_url,
            "status": itinerary.image_status
            or ("available" if hero_image_url else "missing"),
        },
        "tags": itinerary.tags,
        "genres": itinerary.normalized_genres,
        "estimates": {
            "duration_text": itinerary.estimated_duration_text or "",
            "distance_text": itinerary.estimated_distance_text or "",
            "start": {
                "city": itinerary.start_city or "",
                "state": itinerary.start_state or "",
                "country": itinerary.start_country or "",
            },
            "end": {
                "city": itinerary.end_city or "",
                "state": itinerary.end_state or "",
                "country": itinerary.end_country or "",
            },
        },
        "featured": itinerary.featured,
        "stops": [_stop_payload(stop) for stop in itinerary.stops],
        "segments": [_segment_payload(segment) for segment in itinerary.segments],
        "quality": {
            "score": _safe_float(itinerary.quality_score),
            "flags": itinerary.quality_flags,
            "app_feed_ready": itinerary.app_feed_ready,
        },
        "updated_at": _iso_datetime(itinerary.updated_at),
    }


def list_app_itineraries(
    session: Session,
    *,
    region_id: int | None = None,
    artist_id: int | None = None,
    include_unpublished: bool = False,
) -> list[dict[str, Any]]:
    stmt = _itinerary_query().order_by(Itinerary.sort_order.asc(), Itinerary.id.asc())
    if not include_unpublished:
        stmt = stmt.where(
            Itinerary.status.in_(APP_FEED_STATUSES),
            Itinerary.app_feed_ready.is_(True),
        )
    if region_id is not None:
        stmt = stmt.where(Itinerary.region_id == region_id)
    if artist_id is not None:
        stmt = stmt.where(Itinerary.artist_id == artist_id)
    return [
        build_itinerary_app_feed(session, itinerary)
        for itinerary in session.scalars(stmt).all()
    ]


def build_itinerary_from_region(session: Session, region_id: int) -> Itinerary:
    region = session.get(Region, region_id)
    if region is None:
        raise ValueError("Region not found.")
    itinerary = create_itinerary(
        session,
        ItineraryCreate(
            title=f"{region.name} Music Route",
            subtitle="Draft regional Road Trip suggestion",
            description=(
                "Draft-only itinerary suggestion from approved internal records."
            ),
            itinerary_type=ItineraryType.certified_region.value
            if region.certified
            else ItineraryType.city_tour.value,
            region_id=region.id,
            start_city=region.city,
            start_state=region.state,
            start_country=region.country,
            end_city=region.city,
            end_state=region.state,
            end_country=region.country,
            tags=["draft", "region"],
        ),
    )
    pois = list(
        session.scalars(
            select(PoiLocation)
            .where(
                PoiLocation.region_id == region.id,
                PoiLocation.publish_status.in_(PUBLISHABLE_STATUSES),
                PoiLocation.category != "Concert",
            )
            .order_by(PoiLocation.certified.desc(), PoiLocation.display_name.asc())
            .limit(4)
        ).all()
    )
    for poi in pois:
        add_stop(
            session,
            itinerary.id,
            ItineraryStopInput(
                stop_type=ItineraryStopType.poi.value,
                poi_location_id=poi.id,
            ),
        )
    return get_itinerary(session, itinerary.id) or itinerary


def build_itinerary_from_artist_events(
    session: Session,
    artist_id: int,
) -> Itinerary:
    artist = session.get(CanonicalArtist, artist_id)
    if artist is None:
        raise ValueError("Artist not found.")
    itinerary = create_itinerary(
        session,
        ItineraryCreate(
            title=f"{artist.display_name} Tour",
            subtitle="Draft artist tour route",
            itinerary_type=ItineraryType.artist_tour.value,
            display_label=ItineraryDisplayLabel.tour.value,
            artist_id=artist.id,
            normalized_genres=artist.normalized_genres,
            tags=["draft", "artist-tour"],
        ),
    )
    events = list(
        session.scalars(
            select(Event)
            .join(EventArtist, EventArtist.event_id == Event.id)
            .where(
                EventArtist.artist_id == artist.id,
                Event.publish_status.in_(PUBLISHABLE_STATUSES),
                Event.duplicate_status.not_in(DUPLICATE_EXCLUDE_STATUSES),
                Event.category == "Concert",
                Event.record_type == "event",
            )
            .order_by(Event.start_datetime.asc())
            .limit(8)
        ).all()
    )
    for event in events:
        add_stop(
            session,
            itinerary.id,
            ItineraryStopInput(
                stop_type=ItineraryStopType.event.value,
                event_id=event.id,
            ),
        )
    return get_itinerary(session, itinerary.id) or itinerary


def build_itinerary_from_search_results(
    session: Session,
    title: str,
    results: list[dict[str, object]],
) -> Itinerary:
    itinerary = create_itinerary(
        session,
        ItineraryCreate(
            title=title,
            itinerary_type=ItineraryType.custom.value,
            display_label=ItineraryDisplayLabel.route.value,
            tags=["draft", "search-results"],
        ),
    )
    for result in results:
        add_stop(
            session,
            itinerary.id,
            ItineraryStopInput(
                stop_type=ItineraryStopType.custom.value,
                title=str(result.get("title") or "Search result"),
                subtitle=_clean(result.get("entity_type")),
                city=_clean(result.get("city")),
                state=_clean(result.get("state")),
                country=_clean(result.get("country")),
                latitude=_optional_float(result.get("latitude")),
                longitude=_optional_float(result.get("longitude")),
            ),
        )
    return get_itinerary(session, itinerary.id) or itinerary


def itinerary_preview_marker(stop: ItineraryStop) -> dict[str, object]:
    return {
        "id": f"itinerary_stop_{stop.id}",
        "entity_type": "itinerary_stop",
        "title": stop.title,
        "category": stop.stop_type,
        "subcategory": "",
        "latitude": _safe_float(stop.latitude),
        "longitude": _safe_float(stop.longitude),
        "marker": {
            "icon_key": "route_stop",
            "icon_label": "Stop",
            "marker_color": "#9f7bff",
            "marker_shape": "pin",
            "marker_size": "medium",
            "marker_weight": 62,
            "marker_opacity": 1.0,
            "glow": False,
            "certified": False,
            "cluster_priority": 52,
            "z_index": 180,
        },
        "quality": {
            "score": None,
            "flags": [] if _location_query(stop) else ["missing_location"],
        },
    }


def itinerary_admin_reference_options(session: Session) -> dict[str, list[object]]:
    return {
        "events": list(
            session.scalars(
                select(Event)
                .where(Event.category == "Concert", Event.record_type == "event")
                .order_by(Event.start_datetime.desc())
                .limit(100)
            ).all()
        ),
        "pois": list(
            session.scalars(
                select(PoiLocation)
                .where(PoiLocation.category != "Concert")
                .order_by(PoiLocation.display_name.asc())
                .limit(100)
            ).all()
        ),
        "venues": list(
            session.scalars(
                select(EventVenue).order_by(EventVenue.display_name.asc()).limit(100)
            ).all()
        ),
        "regions": list(
            session.scalars(select(Region).order_by(Region.name.asc())).all()
        ),
        "artists": list(
            session.scalars(
                select(CanonicalArtist)
                .order_by(CanonicalArtist.display_name.asc())
                .limit(100)
            ).all()
        ),
        "partners": list(
            session.scalars(
                select(DestinationPartner).order_by(DestinationPartner.name.asc())
            ).all()
        ),
    }
