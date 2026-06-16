from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    AppSearchEntityType,
    AppSearchIndex,
    CanonicalArtist,
    Event,
    EventArtist,
    EventVenue,
    Itinerary,
    ItineraryStatus,
    PoiLocation,
    PublishStatus,
    Region,
    SearchSeedLocation,
    utc_now,
)
from app.services.app_feed_service import (
    DUPLICATE_EXCLUDE_STATUSES,
    PUBLISHABLE_STATUSES,
    event_publish_readiness,
    poi_publish_readiness,
)
from app.services.map_display_service import build_map_marker

EXCLUDED_EVENT_PUBLISH_STATUSES = {
    PublishStatus.rejected.value,
    PublishStatus.stale.value,
    PublishStatus.archived.value,
    PublishStatus.unpublished.value,
}
EXCLUDED_DUPLICATE_STATUSES = set(DUPLICATE_EXCLUDE_STATUSES)
INDEXABLE_ITINERARY_STATUSES = {
    ItineraryStatus.approved.value,
    ItineraryStatus.published.value,
}


@dataclass(frozen=True)
class AppSearchFilters:
    entity_type: str | None = None
    category: str | None = None
    subcategory: str | None = None
    region_id: int | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    app_feed_ready: bool | None = None
    certified: bool | None = None


def normalize_search_text(text: object) -> str:
    """Normalize app search text without relying on external search services."""

    value = "" if text is None else str(text)
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"[^a-zA-Z0-9]+", " ", value).lower()
    return re.sub(r"\s+", " ", value).strip()


def _json_list(values: list[object]) -> str:
    return json.dumps([str(item) for item in values if str(item).strip()])


def _quality_flags_json(flags: list[str]) -> str:
    return json.dumps(list(dict.fromkeys(flag for flag in flags if flag)))


def _iso_datetime(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def _next_event_for_venue(
    db: Session,
    venue_key: str | None,
) -> tuple[int, datetime | None]:
    if not venue_key:
        return 0, None
    now = utc_now()
    events = list(
        db.scalars(
            select(Event)
            .join(Event.venue)
            .where(
                EventVenue.venue_key == venue_key,
                Event.publish_status.in_(PUBLISHABLE_STATUSES),
                Event.duplicate_status.not_in(EXCLUDED_DUPLICATE_STATUSES),
                Event.start_datetime >= now,
            )
            .order_by(Event.start_datetime.asc()),
        ).all(),
    )
    return len(events), events[0].start_datetime if events else None


def _search_text(parts: list[object | None]) -> str:
    return normalize_search_text(" ".join(str(part) for part in parts if part))


def _upsert_index_entry(db: Session, entry: AppSearchIndex) -> AppSearchIndex:
    existing = db.scalar(
        select(AppSearchIndex).where(AppSearchIndex.search_key == entry.search_key),
    )
    if existing is None:
        db.add(entry)
        return entry
    for attr in (
        "entity_type",
        "entity_id",
        "display_name",
        "normalized_name",
        "alternate_names_json",
        "search_text",
        "category",
        "subcategory",
        "region_id",
        "city",
        "state",
        "country",
        "latitude",
        "longitude",
        "timezone",
        "source_type",
        "source_record_id",
        "priority",
        "search_weight",
        "popularity_score",
        "app_feed_ready",
        "certified",
        "has_upcoming_events",
        "upcoming_event_count",
        "next_event_datetime",
        "quality_score",
        "quality_flags_json",
    ):
        setattr(existing, attr, getattr(entry, attr))
    existing.updated_at = utc_now()
    db.add(existing)
    return existing


def index_region(db: Session, region: Region) -> AppSearchIndex:
    display_name = region.name.strip()
    search_text = _search_text(
        [
            display_name,
            region.region_type,
            region.city,
            region.state,
            region.country,
            region.description,
        ],
    )
    entry = AppSearchIndex(
        search_key=f"region:{region.id}",
        entity_type=AppSearchEntityType.region.value,
        entity_id=str(region.id),
        display_name=display_name,
        normalized_name=normalize_search_text(display_name),
        alternate_names_json=_json_list([region.slug, region.region_key]),
        search_text=search_text,
        category=region.region_type,
        subcategory=None,
        region_id=region.id,
        city=region.city,
        state=region.state,
        country=region.country,
        latitude=region.latitude,
        longitude=region.longitude,
        timezone=region.timezone,
        source_type="region",
        source_record_id=str(region.id),
        priority=20 if region.certified else 35,
        search_weight=3.0 if region.certified else 2.2,
        popularity_score=20.0 if region.certified else 10.0,
        app_feed_ready=True,
        certified=region.certified,
        has_upcoming_events=False,
        upcoming_event_count=0,
        next_event_datetime=None,
        quality_score=None,
        quality_flags_json="[]",
    )
    return _upsert_index_entry(db, entry)


def index_poi_location(db: Session, poi: PoiLocation) -> AppSearchIndex | None:
    if (poi.category or "").strip() == "Concert":
        return None
    score, blockers, flags = poi_publish_readiness(poi)
    upcoming_count, next_event = _next_event_for_venue(
        db,
        poi.canonical_venue_id or poi.canonical_poi_id,
    )
    display_name = poi.display_name.strip()
    search_text = _search_text(
        [
            display_name,
            poi.normalized_name,
            poi.category,
            poi.subcategory,
            poi.city,
            poi.state,
            poi.country,
            poi.description,
            poi.carousel_selection,
        ],
    )
    entry = AppSearchIndex(
        search_key=f"poi:{poi.id}",
        entity_type=AppSearchEntityType.poi.value,
        entity_id=str(poi.id),
        display_name=display_name,
        normalized_name=normalize_search_text(display_name),
        alternate_names_json=_json_list([poi.canonical_poi_id, poi.mapotic_id or ""]),
        search_text=search_text,
        category=poi.category,
        subcategory=poi.subcategory,
        region_id=poi.region_id,
        city=poi.city,
        state=poi.state,
        country=poi.country,
        latitude=poi.latitude,
        longitude=poi.longitude,
        timezone=None,
        source_type=poi.source_type,
        source_record_id=poi.source_record_id or poi.canonical_poi_id,
        priority=25 if poi.certified else 55,
        search_weight=2.5 if poi.certified else 1.5,
        popularity_score=float(poi.review_count_google or 0) / 10,
        app_feed_ready=(
            poi.publish_status in PUBLISHABLE_STATUSES and not blockers
        ),
        certified=bool(poi.certified),
        has_upcoming_events=upcoming_count > 0,
        upcoming_event_count=upcoming_count,
        next_event_datetime=next_event,
        quality_score=float(score),
        quality_flags_json=_quality_flags_json(blockers + flags),
    )
    return _upsert_index_entry(db, entry)


def index_event(db: Session, event: Event) -> AppSearchIndex | None:
    if (event.category or "Concert") != "Concert" or event.record_type != "event":
        return None
    if event.publish_status in EXCLUDED_EVENT_PUBLISH_STATUSES:
        return None
    if event.duplicate_status in EXCLUDED_DUPLICATE_STATUSES:
        return None
    score, blockers, flags = event_publish_readiness(event)
    venue = event.venue
    artist_names = [
        link.artist.display_name
        for link in event.artist_links
        if link.artist is not None
    ]
    display_name = event.title.strip()
    search_text = _search_text(
        [
            display_name,
            event.headliner,
            event.supporting_artists,
            event.genre,
            event.normalized_genre,
            " ".join(event.normalized_genres),
            event.music_category,
            " ".join(artist_names),
            venue.display_name if venue else event.location_text,
            venue.city if venue else None,
            venue.state if venue else None,
        ],
    )
    entry = AppSearchIndex(
        search_key=f"event:{event.id}",
        entity_type=AppSearchEntityType.event.value,
        entity_id=str(event.id),
        display_name=display_name,
        normalized_name=normalize_search_text(display_name),
        alternate_names_json=_json_list(
            [event.headliner or "", *artist_names, event.source_event_id or ""],
        ),
        search_text=search_text,
        category="Concert",
        subcategory=(
            event.normalized_genres[0]
            if event.normalized_genres
            else event.normalized_genre or event.genre or event.music_category
        ),
        region_id=event.region_id,
        city=venue.city if venue else None,
        state=venue.state if venue else None,
        country=venue.country if venue else None,
        latitude=venue.latitude if venue else None,
        longitude=venue.longitude if venue else None,
        timezone=event.timezone,
        source_type=event.source_type,
        source_record_id=event.source_event_id or event.api_source_record_id,
        priority=35,
        search_weight=2.0,
        popularity_score=float(event.source_claim_count or 0) * 5,
        app_feed_ready=(
            event.publish_status in PUBLISHABLE_STATUSES and not blockers
        ),
        certified=False,
        has_upcoming_events=True,
        upcoming_event_count=1,
        next_event_datetime=event.start_datetime,
        quality_score=float(score),
        quality_flags_json=_quality_flags_json(blockers + flags),
    )
    return _upsert_index_entry(db, entry)


def index_artist(db: Session, artist: CanonicalArtist) -> AppSearchIndex:
    event_links = [link for link in artist.event_links if link.event is not None]
    upcoming_links = [
        link
        for link in event_links
        if link.event
        and link.event.start_datetime is not None
        and (
            link.event.start_datetime.replace(tzinfo=UTC)
            if link.event.start_datetime.tzinfo is None
            else link.event.start_datetime.astimezone(UTC)
        )
        >= utc_now()
    ]
    next_event = min(
        (link.event.start_datetime for link in upcoming_links if link.event),
        default=None,
    )
    display_name = artist.display_name.strip()
    search_text = _search_text(
        [
            display_name,
            artist.normalized_name,
            artist.artist_type,
            artist.primary_genre,
            " ".join(artist.normalized_genres),
            artist.spotify_url,
            artist.jambase_artist_id,
        ],
    )
    entry = AppSearchIndex(
        search_key=f"artist:{artist.id}",
        entity_type=AppSearchEntityType.artist_future.value,
        entity_id=str(artist.id),
        display_name=display_name,
        normalized_name=normalize_search_text(display_name),
        alternate_names_json=artist.alternate_names_json,
        search_text=search_text,
        category="Artist",
        subcategory=artist.primary_genre,
        region_id=None,
        city=None,
        state=None,
        country=None,
        latitude=None,
        longitude=None,
        timezone=None,
        source_type="artist_registry",
        source_record_id=artist.artist_key,
        priority=45,
        search_weight=1.6 + min(float(artist.source_claim_count or 0) * 0.1, 1.0),
        popularity_score=float(len(event_links) * 8),
        app_feed_ready=False,
        certified=False,
        has_upcoming_events=bool(upcoming_links),
        upcoming_event_count=len(upcoming_links),
        next_event_datetime=next_event,
        quality_score=artist.quality_score,
        quality_flags_json=artist.quality_flags_json,
    )
    return _upsert_index_entry(db, entry)


def index_venue(db: Session, venue: EventVenue) -> AppSearchIndex:
    upcoming_count, next_event = _next_event_for_venue(db, venue.venue_key)
    display_name = venue.display_name.strip()
    search_text = _search_text(
        [
            display_name,
            venue.category,
            venue.subcategory,
            venue.city,
            venue.state,
            venue.country,
            venue.description,
        ],
    )
    entry = AppSearchIndex(
        search_key=f"venue:{venue.id}",
        entity_type=AppSearchEntityType.venue.value,
        entity_id=str(venue.id),
        display_name=display_name,
        normalized_name=normalize_search_text(display_name),
        alternate_names_json=_json_list([venue.venue_key]),
        search_text=search_text,
        category=venue.category,
        subcategory=venue.subcategory,
        region_id=None,
        city=venue.city,
        state=venue.state,
        country=venue.country,
        latitude=venue.latitude,
        longitude=venue.longitude,
        timezone=None,
        source_type="event_venue",
        source_record_id=venue.venue_key,
        priority=40,
        search_weight=1.8,
        popularity_score=float(upcoming_count * 10),
        app_feed_ready=upcoming_count > 0,
        certified=False,
        has_upcoming_events=upcoming_count > 0,
        upcoming_event_count=upcoming_count,
        next_event_datetime=next_event,
        quality_score=venue.image_quality_score,
        quality_flags_json=_quality_flags_json(venue.image_quality_flags),
    )
    return _upsert_index_entry(db, entry)


def index_search_seed(db: Session, seed: SearchSeedLocation) -> AppSearchIndex | None:
    if not seed.use_for_internal_search and not seed.use_for_app_search:
        return None
    display_name = seed.display_name.strip()
    search_text = _search_text(
        [
            display_name,
            seed.normalized_name,
            seed.seed_type,
            seed.city,
            seed.state,
            seed.country,
        ],
    )
    entry = AppSearchIndex(
        search_key=f"search_seed:{seed.id}",
        entity_type=AppSearchEntityType.search_seed.value,
        entity_id=str(seed.id),
        display_name=display_name,
        normalized_name=normalize_search_text(display_name),
        alternate_names_json="[]",
        search_text=search_text,
        category=seed.seed_type,
        subcategory=None,
        region_id=seed.region_id,
        city=seed.city,
        state=seed.state,
        country=seed.country,
        latitude=seed.latitude,
        longitude=seed.longitude,
        timezone=seed.timezone,
        source_type=seed.source_type,
        source_record_id=seed.source_record_id or str(seed.id),
        priority=seed.priority,
        search_weight=seed.search_weight,
        popularity_score=seed.popularity_score,
        app_feed_ready=seed.use_for_app_search,
        certified=False,
        has_upcoming_events=False,
        upcoming_event_count=0,
        next_event_datetime=None,
        quality_score=None,
        quality_flags_json="[]",
    )
    return _upsert_index_entry(db, entry)


def index_itinerary(db: Session, itinerary: Itinerary) -> AppSearchIndex | None:
    if itinerary.status not in INDEXABLE_ITINERARY_STATUSES:
        return None
    display_name = itinerary.title.strip()
    search_text = _search_text(
        [
            display_name,
            itinerary.subtitle,
            itinerary.description,
            itinerary.itinerary_type,
            itinerary.display_label,
            itinerary.music_theme,
            " ".join(itinerary.normalized_genres),
            " ".join(itinerary.tags),
            itinerary.region.name if itinerary.region else None,
            itinerary.artist.display_name if itinerary.artist else None,
            itinerary.start_city,
            itinerary.start_state,
            itinerary.end_city,
            itinerary.end_state,
        ],
    )
    entry = AppSearchIndex(
        search_key=f"itinerary:{itinerary.id}",
        entity_type=AppSearchEntityType.itinerary.value,
        entity_id=str(itinerary.id),
        display_name=display_name,
        normalized_name=normalize_search_text(display_name),
        alternate_names_json=_json_list([itinerary.slug, itinerary.itinerary_key]),
        search_text=search_text,
        category=itinerary.display_label,
        subcategory=itinerary.itinerary_type,
        region_id=itinerary.region_id,
        city=itinerary.start_city
        or (itinerary.region.city if itinerary.region else None),
        state=itinerary.start_state
        or (itinerary.region.state if itinerary.region else None),
        country=itinerary.start_country
        or (itinerary.region.country if itinerary.region else None),
        latitude=itinerary.region.latitude if itinerary.region else None,
        longitude=itinerary.region.longitude if itinerary.region else None,
        timezone=itinerary.region.timezone if itinerary.region else None,
        source_type="itinerary",
        source_record_id=itinerary.itinerary_key,
        priority=18 if itinerary.featured else 42,
        search_weight=2.8 if itinerary.featured else 1.9,
        popularity_score=float(len(itinerary.stops) * 6),
        app_feed_ready=itinerary.app_feed_ready,
        certified=bool(itinerary.region.certified if itinerary.region else False),
        has_upcoming_events=any(stop.event_id for stop in itinerary.stops),
        upcoming_event_count=sum(1 for stop in itinerary.stops if stop.event_id),
        next_event_datetime=min(
            (stop.start_datetime for stop in itinerary.stops if stop.start_datetime),
            default=None,
        ),
        quality_score=itinerary.quality_score,
        quality_flags_json=itinerary.quality_flags_json,
    )
    return _upsert_index_entry(db, entry)


def rebuild_search_index(db: Session) -> dict[str, int]:
    """Rebuild the app search index from internal normalized records only."""

    db.execute(delete(AppSearchIndex))
    counts = {
        "regions": 0,
        "pois": 0,
        "venues": 0,
        "events": 0,
        "artists": 0,
        "itineraries": 0,
        "search_seeds": 0,
    }
    for region in db.scalars(select(Region).order_by(Region.id.asc())).all():
        index_region(db, region)
        counts["regions"] += 1
    for poi in db.scalars(
        select(PoiLocation)
        .where(
            PoiLocation.publish_status.in_(PUBLISHABLE_STATUSES),
            PoiLocation.category != "Concert",
        )
        .order_by(PoiLocation.id.asc()),
    ).all():
        if index_poi_location(db, poi) is not None:
            counts["pois"] += 1
    for venue in db.scalars(select(EventVenue).order_by(EventVenue.id.asc())).all():
        index_venue(db, venue)
        counts["venues"] += 1
    for event in db.scalars(
        select(Event)
        .options(
            selectinload(Event.venue),
            selectinload(Event.source_claims),
            selectinload(Event.artist_links).selectinload(EventArtist.artist),
        )
        .where(
            Event.publish_status.not_in(EXCLUDED_EVENT_PUBLISH_STATUSES),
            Event.duplicate_status.not_in(EXCLUDED_DUPLICATE_STATUSES),
            Event.record_type == "event",
            Event.category == "Concert",
        )
        .order_by(Event.id.asc()),
    ).all():
        if index_event(db, event) is not None:
            counts["events"] += 1
    for artist in db.scalars(
        select(CanonicalArtist)
        .options(
            selectinload(CanonicalArtist.event_links).selectinload(EventArtist.event)
        )
        .order_by(CanonicalArtist.id.asc()),
    ).all():
        index_artist(db, artist)
        counts["artists"] += 1
    for seed in db.scalars(
        select(SearchSeedLocation).order_by(SearchSeedLocation.id.asc()),
    ).all():
        if index_search_seed(db, seed) is not None:
            counts["search_seeds"] += 1
    for itinerary in db.scalars(
        select(Itinerary)
        .options(
            selectinload(Itinerary.region),
            selectinload(Itinerary.artist),
            selectinload(Itinerary.stops),
        )
        .where(Itinerary.status.in_(INDEXABLE_ITINERARY_STATUSES))
        .order_by(Itinerary.id.asc()),
    ).all():
        if index_itinerary(db, itinerary) is not None:
            counts["itineraries"] += 1
    db.commit()
    return counts


def _app_url_for(entry: AppSearchIndex) -> str:
    prefixed_id = f"{entry.entity_type}_{entry.entity_id}"
    if entry.entity_type == AppSearchEntityType.region.value:
        return f"/regions/{entry.entity_id}"
    if entry.entity_type == AppSearchEntityType.itinerary.value:
        return f"/itineraries/{entry.entity_id}"
    if entry.entity_type == AppSearchEntityType.event.value:
        return f"/events/{prefixed_id}"
    if entry.entity_type in {
        AppSearchEntityType.poi.value,
        AppSearchEntityType.venue.value,
    }:
        return f"/pois/{prefixed_id}"
    return f"/search/{prefixed_id}"


def _subtitle_for(entry: AppSearchIndex) -> str:
    location = ", ".join(
        part for part in [entry.city, entry.state, entry.country] if part
    )
    category = " · ".join(
        part for part in [entry.category, entry.subcategory] if part
    )
    if category and location:
        return f"{category} · {location}"
    return category or location


def _badges_for(entry: AppSearchIndex) -> list[str]:
    label = {
        AppSearchEntityType.event.value: "Event",
        AppSearchEntityType.itinerary.value: "Itinerary",
        AppSearchEntityType.poi.value: "POI",
        AppSearchEntityType.venue.value: "Venue",
        AppSearchEntityType.region.value: "Region",
        AppSearchEntityType.search_seed.value: "Search Seed",
        AppSearchEntityType.artist_future.value: "Artist",
    }.get(entry.entity_type, "Unknown")
    badges = [label]
    if entry.category and entry.category not in badges:
        badges.append(entry.category)
    if entry.certified:
        badges.append("Certified")
    if entry.app_feed_ready:
        badges.append("App Ready")
    return badges


def _text_match_score(entry: AppSearchIndex, query: str) -> float:
    normalized_query = normalize_search_text(query)
    name = entry.normalized_name
    text = entry.search_text
    if not normalized_query:
        return 100.0
    if name == normalized_query:
        return 1000.0
    if name.startswith(normalized_query):
        return 800.0
    if normalized_query in name:
        return 650.0
    if normalized_query in text:
        return 500.0
    query_tokens = set(normalized_query.split())
    text_tokens = set(text.split())
    if query_tokens and query_tokens.issubset(text_tokens):
        return 420.0
    if normalized_query.replace(" ", "") in text.replace(" ", ""):
        return 300.0
    return 0.0


def _rank_score(entry: AppSearchIndex, query: str) -> float:
    score = _text_match_score(entry, query)
    if normalize_search_text(query) and score <= 0:
        return 0.0
    if entry.entity_type == AppSearchEntityType.region.value:
        score += 70.0
    if entry.entity_type == AppSearchEntityType.itinerary.value:
        score += 45.0
    if entry.entity_type == AppSearchEntityType.search_seed.value:
        score += 25.0
    if entry.app_feed_ready:
        score += 40.0
    if entry.certified:
        score += 55.0
    if entry.has_upcoming_events:
        score += 30.0
    score += max(0.0, 100.0 - float(entry.priority))
    score += float(entry.search_weight or 0) * 10
    score += float(entry.popularity_score or 0)
    return round(score, 2)


def _entry_matches_query(entry: AppSearchIndex, query: str) -> bool:
    if not query:
        return True
    return _rank_score(entry, query) > 0


def _apply_filters(
    entries: list[AppSearchIndex],
    filters: AppSearchFilters | None,
) -> list[AppSearchIndex]:
    if filters is None:
        return entries
    filtered: list[AppSearchIndex] = []
    for entry in entries:
        if filters.entity_type and entry.entity_type != filters.entity_type:
            continue
        if filters.category and entry.category != filters.category:
            continue
        if filters.subcategory and entry.subcategory != filters.subcategory:
            continue
        if filters.region_id and entry.region_id != filters.region_id:
            continue
        if filters.city and entry.city != filters.city:
            continue
        if filters.state and entry.state != filters.state:
            continue
        if filters.country and entry.country != filters.country:
            continue
        if filters.app_feed_ready is not None:
            if entry.app_feed_ready != filters.app_feed_ready:
                continue
        if filters.certified is not None and entry.certified != filters.certified:
            continue
        filtered.append(entry)
    return filtered


def _entry_to_result(
    entry: AppSearchIndex,
    score: float,
    *,
    include_marker: bool = False,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "entity_type": entry.entity_type,
        "id": f"{entry.entity_type}_{entry.entity_id}",
        "title": entry.display_name,
        "subtitle": _subtitle_for(entry),
        "category": entry.category or "",
        "subcategory": entry.subcategory or "",
        "latitude": entry.latitude,
        "longitude": entry.longitude,
        "score": score,
        "badges": _badges_for(entry),
        "app_url": _app_url_for(entry),
        "region_id": entry.region_id,
        "city": entry.city or "",
        "state": entry.state or "",
        "country": entry.country or "",
        "app_feed_ready": entry.app_feed_ready,
        "certified": entry.certified,
        "has_upcoming_events": entry.has_upcoming_events,
        "upcoming_event_count": entry.upcoming_event_count,
        "next_event_datetime": _iso_datetime(entry.next_event_datetime),
    }
    if include_marker:
        result["marker_preview"] = build_map_marker(entry)
    return result


def rank_search_results(
    results: list[tuple[AppSearchIndex, float]],
    context: dict[str, object] | None = None,
) -> list[tuple[AppSearchIndex, float]]:
    """Sort scored search entries by rank, then deterministic stable fields."""

    _ = context
    return sorted(
        results,
        key=lambda item: (
            -item[1],
            item[0].entity_type,
            item[0].display_name.lower(),
            item[0].entity_id,
        ),
    )


def search_app_index(
    db: Session,
    query: str,
    filters: AppSearchFilters | None = None,
    limit: int = 20,
    offset: int = 0,
    *,
    include_marker: bool = False,
) -> dict[str, Any]:
    """Search the local app index and return app-safe result payloads."""

    bounded_limit = max(1, min(limit, 100))
    bounded_offset = max(0, offset)
    entries = list(db.scalars(select(AppSearchIndex)).all())
    filtered = _apply_filters(entries, filters)
    scored = [
        (entry, _rank_score(entry, query))
        for entry in filtered
        if _entry_matches_query(entry, query)
    ]
    ranked = rank_search_results(scored)
    paged = ranked[bounded_offset : bounded_offset + bounded_limit]
    return {
        "query": query,
        "results": [
            _entry_to_result(entry, score, include_marker=include_marker)
            for entry, score in paged
        ],
        "count": len(scored),
        "limit": bounded_limit,
        "offset": bounded_offset,
    }


def suggest_app_search(
    db: Session,
    query: str,
    limit: int = 10,
) -> dict[str, Any]:
    """Return compact typeahead suggestions from the internal index."""

    payload = search_app_index(db, query, limit=limit)
    suggestions = [
        {
            "entity_type": item["entity_type"],
            "id": item["id"],
            "title": item["title"],
            "subtitle": item["subtitle"],
            "score": item["score"],
        }
        for item in payload["results"]
    ]
    return {
        "query": query,
        "suggestions": suggestions,
        "limit": payload["limit"],
    }
