from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    Event,
    EventVenue,
    MasterCalendarSource,
    PoiLocation,
    Region,
    RegionLaunchStatus,
    RegionPartnerStatus,
    RegionQualitySnapshot,
    RegionType,
    SearchSeedLocation,
    SearchSeedSourceType,
    SearchSeedType,
    SourceExtractedEventCandidate,
    SourceReviewStatus,
    utc_now,
)
from app.services.app_feed_service import (
    AppEventFilters,
    AppPoiFilters,
    list_app_events,
    list_app_pois,
)

PUBLISHABLE_STATUSES = {"approved", "published"}
BAD_TICKET_CLASSIFICATIONS = {
    "missing",
    "invalid",
    "generic_platform",
    "generic_app",
    "tracking_or_affiliate",
    "unresolved",
}


@dataclass(frozen=True)
class RegionMatch:
    region: Region
    confidence: float
    reason: str


@dataclass(frozen=True)
class RegionSummary:
    region: Region
    event_count: int
    poi_count: int
    source_count: int
    quality_score: int


@dataclass(frozen=True)
class SearchSeedFilters:
    q: str | None = None
    seed_type: str | None = None
    region_id: int | None = None


def normalize_region_key(*parts: object) -> str:
    """Build a stable lower-case key from human region fields."""

    text = "-".join(
        str(part).strip().lower()
        for part in parts
        if part is not None and str(part).strip()
    )
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "unknown"


def create_or_update_region(
    session: Session,
    *,
    name: str,
    region_type: str = RegionType.city.value,
    city: str | None = None,
    state: str | None = None,
    country: str | None = "US",
    latitude: float | None = None,
    longitude: float | None = None,
    radius_miles: float | None = None,
    timezone: str | None = None,
    description: str | None = None,
    partner_status: str = RegionPartnerStatus.internal.value,
    certified: bool = False,
    launch_status: str = RegionLaunchStatus.research.value,
    bbox_json: str | None = None,
    commit: bool = True,
) -> Region:
    """Create or update one destination region by deterministic key."""

    region_key = normalize_region_key(region_type, name, city, state, country)
    slug = normalize_region_key(name, city, state, country)
    region = session.scalar(
        select(Region).where(Region.region_key == region_key)
    )
    if region is None:
        region = Region(region_key=region_key, slug=slug, name=name)
        session.add(region)
    region.name = name.strip()
    region.slug = slug
    region.region_type = region_type
    region.city = clean(city)
    region.state = clean(state)
    region.country = clean(country)
    region.latitude = latitude
    region.longitude = longitude
    region.radius_miles = radius_miles
    region.timezone = clean(timezone)
    region.description = clean(description)
    region.partner_status = partner_status
    region.certified = certified
    region.launch_status = launch_status
    region.bbox_json = bbox_json
    if commit:
        session.commit()
        session.refresh(region)
    return region


def list_regions(session: Session) -> list[RegionSummary]:
    regions = list(
        session.scalars(
            select(Region).order_by(Region.name.asc(), Region.id.asc())
        ).all()
    )
    return [region_summary(session, region) for region in regions]


def get_region(session: Session, region_id: int) -> Region | None:
    return session.get(Region, region_id)


def region_summary(session: Session, region: Region) -> RegionSummary:
    event_count = scalar_count(
        session,
        select(func.count(Event.id)).where(Event.region_id == region.id),
    )
    poi_count = scalar_count(
        session,
        select(func.count(PoiLocation.id)).where(PoiLocation.region_id == region.id),
    )
    source_count = scalar_count(
        session,
        select(func.count(MasterCalendarSource.id)).where(
            MasterCalendarSource.region_id == region.id
        ),
    )
    latest = latest_region_quality_snapshot(session, region.id)
    quality_score = safe_int(latest.snapshot.get("quality_score")) if latest else 0
    return RegionSummary(region, event_count, poi_count, source_count, quality_score)


def infer_region_for_poi(session: Session, poi: PoiLocation) -> RegionMatch | None:
    match = match_region_by_place(
        session,
        city=poi.city,
        state=poi.state,
        country=poi.country,
    )
    if match:
        return match
    return nearest_region_match(session, poi.latitude, poi.longitude)


def infer_region_for_event(session: Session, event: Event) -> RegionMatch | None:
    if event.venue:
        match = match_region_by_place(
            session,
            city=event.venue.city,
            state=event.venue.state,
            country=event.venue.country,
        )
        if match:
            return match
        return nearest_region_match(
            session,
            event.venue.latitude,
            event.venue.longitude,
        )
    if event.event_venue_id:
        venue = session.get(EventVenue, event.event_venue_id)
        if venue:
            match = match_region_by_place(
                session,
                city=venue.city,
                state=venue.state,
                country=venue.country,
            )
            if match:
                return match
            return nearest_region_match(session, venue.latitude, venue.longitude)
    return None


def infer_region_for_master_source(
    session: Session,
    source: MasterCalendarSource,
) -> RegionMatch | None:
    match = match_region_by_place(
        session,
        city=source.city or source.region_or_market,
        state=source.state,
        country=source.country,
    )
    if match:
        return match
    return None


def assign_inferred_regions(session: Session, *, commit: bool = True) -> dict[str, int]:
    """Assign high-confidence region matches to unassigned records."""

    counts = {"pois": 0, "events": 0, "sources": 0}
    unassigned_pois = select(PoiLocation).where(PoiLocation.region_id.is_(None))
    for poi in session.scalars(unassigned_pois):
        match = infer_region_for_poi(session, poi)
        if match and match.confidence >= 0.75:
            poi.region_id = match.region.id
            poi.region_confidence = match.confidence
            session.add(poi)
            counts["pois"] += 1
    for event in session.scalars(
        select(Event)
        .options(selectinload(Event.venue))
        .where(Event.region_id.is_(None))
    ):
        match = infer_region_for_event(session, event)
        if match and match.confidence >= 0.75:
            event.region_id = match.region.id
            event.region_confidence = match.confidence
            session.add(event)
            counts["events"] += 1
    for source in session.scalars(
        select(MasterCalendarSource).where(MasterCalendarSource.region_id.is_(None))
    ):
        match = infer_region_for_master_source(session, source)
        if match and match.confidence >= 0.8:
            source.region_id = match.region.id
            source.region_confidence = match.confidence
            session.add(source)
            counts["sources"] += 1
    if commit:
        session.commit()
    return counts


def match_region_by_place(
    session: Session,
    *,
    city: str | None,
    state: str | None,
    country: str | None,
) -> RegionMatch | None:
    city_key = normalized_place(city)
    state_key = normalized_place(state)
    country_key = normalized_place(country)
    if not any((city_key, state_key, country_key)):
        return None
    candidates = list(session.scalars(select(Region)).all())
    for region in candidates:
        region_city = normalized_place(region.city)
        region_state = normalized_place(region.state)
        region_country = normalized_place(region.country)
        if city_key and region_city == city_key:
            if state_key and region_state and region_state != state_key:
                continue
            if country_key and region_country and region_country != country_key:
                continue
            return RegionMatch(region, 0.95, "city_state_country")
    for region in candidates:
        if state_key and normalized_place(region.state) == state_key:
            if country_key and normalized_place(region.country) not in {
                "",
                country_key,
            }:
                continue
            if region.region_type in {
                RegionType.state.value,
                RegionType.metro.value,
                RegionType.certified_music_region.value,
            }:
                return RegionMatch(region, 0.72, "state_match")
    return None


def nearest_region_match(
    session: Session,
    latitude: float | None,
    longitude: float | None,
) -> RegionMatch | None:
    if latitude is None or longitude is None:
        return None
    best: tuple[Region, float] | None = None
    for region in session.scalars(
        select(Region).where(
            Region.latitude.is_not(None),
            Region.longitude.is_not(None),
            Region.radius_miles.is_not(None),
        )
    ):
        if region.latitude is None or region.longitude is None:
            continue
        distance = haversine_miles(
            latitude,
            longitude,
            region.latitude,
            region.longitude,
        )
        radius = region.radius_miles or 0
        if distance <= radius and (best is None or distance < best[1]):
            best = (region, distance)
    if best is None:
        return None
    region, distance = best
    radius = region.radius_miles or 1
    confidence = max(0.5, min(0.9, 1 - (distance / max(radius, 1)) * 0.4))
    return RegionMatch(region, round(confidence, 3), "nearest_region_radius")


def seed_search_locations_from_pois(
    session: Session,
    *,
    commit: bool = True,
) -> dict[str, int]:
    created = 0
    updated = 0
    for poi in session.scalars(select(PoiLocation).order_by(PoiLocation.id.asc())):
        seed_key = f"poi:{poi.id}"
        seed = session.scalar(
            select(SearchSeedLocation).where(SearchSeedLocation.seed_key == seed_key)
        )
        if seed is None:
            seed = SearchSeedLocation(seed_key=seed_key)
            session.add(seed)
            created += 1
        else:
            updated += 1
        seed.display_name = poi.display_name
        seed.normalized_name = poi.normalized_name or normalized_place(poi.display_name)
        seed.seed_type = seed_type_for_poi(poi)
        seed.source_type = (
            SearchSeedSourceType.mapotic_export.value
            if poi.source_type == "mapotic_export"
            else SearchSeedSourceType.poi_registry.value
        )
        seed.source_record_id = poi.source_record_id or str(poi.id)
        seed.region_id = poi.region_id
        seed.poi_location_id = poi.id
        seed.latitude = poi.latitude
        seed.longitude = poi.longitude
        seed.city = poi.city
        seed.state = poi.state
        seed.country = poi.country
        seed.priority = 30 if seed.seed_type == SearchSeedType.venue.value else 60
        seed.search_weight = (
            1.5 if seed.seed_type == SearchSeedType.venue.value else 1.0
        )
        seed.popularity_score = float(poi.rating or 0)
        seed.use_for_internal_search = True
        if seed.use_for_app_search is None:
            seed.use_for_app_search = False
    if commit:
        session.commit()
    return {"created": created, "updated": updated}


def seed_search_locations_from_regions(
    session: Session,
    *,
    commit: bool = True,
) -> dict[str, int]:
    created = 0
    updated = 0
    for region in session.scalars(select(Region).order_by(Region.id.asc())):
        seed_key = f"region:{region.region_key}"
        seed = session.scalar(
            select(SearchSeedLocation).where(SearchSeedLocation.seed_key == seed_key)
        )
        if seed is None:
            seed = SearchSeedLocation(seed_key=seed_key)
            session.add(seed)
            created += 1
        else:
            updated += 1
        seed.display_name = region.name
        seed.normalized_name = normalized_place(region.name)
        seed.seed_type = seed_type_for_region(region)
        seed.source_type = SearchSeedSourceType.region.value
        seed.source_record_id = str(region.id)
        seed.region_id = region.id
        seed.latitude = region.latitude
        seed.longitude = region.longitude
        seed.city = region.city
        seed.state = region.state
        seed.country = region.country
        seed.timezone = region.timezone
        seed.priority = 10 if region.certified else 20
        seed.search_weight = 3.0 if region.certified else 2.0
        seed.popularity_score = 100.0 if region.certified else 50.0
        seed.use_for_internal_search = True
        seed.use_for_app_search = region.launch_status in {
            RegionLaunchStatus.ready.value,
            RegionLaunchStatus.launched.value,
        }
    if commit:
        session.commit()
    return {"created": created, "updated": updated}


def list_search_seed_locations(
    session: Session,
    filters: SearchSeedFilters | None = None,
) -> list[SearchSeedLocation]:
    filters = filters or SearchSeedFilters()
    stmt = select(SearchSeedLocation).options(selectinload(SearchSeedLocation.region))
    if filters.q:
        needle = f"%{filters.q.strip().lower()}%"
        stmt = stmt.where(func.lower(SearchSeedLocation.display_name).like(needle))
    if filters.seed_type:
        stmt = stmt.where(SearchSeedLocation.seed_type == filters.seed_type)
    if filters.region_id:
        stmt = stmt.where(SearchSeedLocation.region_id == filters.region_id)
    return list(
        session.scalars(
            stmt.order_by(
                SearchSeedLocation.priority.asc(),
                SearchSeedLocation.display_name.asc(),
            )
        ).all()
    )


def compute_region_quality_snapshot(
    session: Session,
    region_id: int,
    *,
    commit: bool = True,
) -> RegionQualitySnapshot:
    region = session.get(Region, region_id)
    if region is None:
        raise ValueError("Region not found.")
    events = list(
        session.scalars(
            select(Event)
            .options(selectinload(Event.venue))
            .where(Event.region_id == region.id)
        ).all()
    )
    pois = list(
        session.scalars(
            select(PoiLocation).where(PoiLocation.region_id == region.id)
        ).all()
    )
    sources = list(
        session.scalars(
            select(MasterCalendarSource).where(
                MasterCalendarSource.region_id == region.id
            )
        ).all()
    )
    app_event_count = len(
        list_app_events(session, AppEventFilters(region_id=region.id, limit=1000))
    )
    app_poi_count = len(
        list_app_pois(session, AppPoiFilters(region_id=region.id, limit=1000))
    )
    missing_image_count = sum(1 for event in events if not event_image_url(event))
    pending_image_approval_count = sum(
        1
        for event in events
        if (event.image_clearance_status or event.image_status or "").lower()
        in {"needs_approval", "pending_approval", "selected_pending_approval"}
    )
    bad_ticket_count = sum(1 for event in events if event_has_ticket_issue(event))
    duplicate_event_candidate_count = sum(
        1
        for event in events
        if (event.duplicate_status or "").lower() == "duplicate_candidate"
    )
    poi_duplicate_candidate_count = sum(
        1
        for poi in pois
        if (poi.poi_dedupe_confidence or "").lower() not in {"strong", "exact"}
    )
    extraction_failure_count = sum(
        1
        for source in sources
        if source.last_extraction_status in {"failure", "unsupported"}
        or source.extraction_failure_count > 0
        or source.unsupported_count > 0
    )
    quality_score = quality_score_for_counts(
        total_count=len(events) + len(pois) + len(sources),
        issue_count=(
            missing_image_count
            + pending_image_approval_count
            + bad_ticket_count
            + duplicate_event_candidate_count
            + poi_duplicate_candidate_count
            + extraction_failure_count
        ),
    )
    snapshot_payload: dict[str, object] = {
        "region_id": region.id,
        "region_key": region.region_key,
        "region_name": region.name,
        "quality_score": quality_score,
        "approved_source_count": sum(
            1
            for source in sources
            if source.status == "approved"
            and source.review_status == SourceReviewStatus.approved.value
        ),
        "pending_source_count": sum(
            1 for source in sources if source.status == "pending"
        ),
        "failed_crawl_source_count": sum(
            1 for source in sources if source.last_extraction_status == "failure"
        ),
        "unsupported_extraction_source_count": sum(
            1 for source in sources if source.last_extraction_status == "unsupported"
        ),
    }
    snapshot = RegionQualitySnapshot(
        region_id=region.id,
        snapshot_json=json.dumps(snapshot_payload, sort_keys=True),
        event_count=len(events),
        poi_count=len(pois),
        source_count=len(sources),
        app_feed_event_count=app_event_count,
        app_feed_poi_count=app_poi_count,
        missing_image_count=missing_image_count,
        pending_image_approval_count=pending_image_approval_count,
        bad_ticket_count=bad_ticket_count,
        duplicate_event_candidate_count=duplicate_event_candidate_count,
        poi_duplicate_candidate_count=poi_duplicate_candidate_count,
        extraction_failure_count=extraction_failure_count,
        generated_at=utc_now(),
    )
    session.add(snapshot)
    if commit:
        session.commit()
        session.refresh(snapshot)
    return snapshot


def latest_region_quality_snapshot(
    session: Session,
    region_id: int,
) -> RegionQualitySnapshot | None:
    return session.scalar(
        select(RegionQualitySnapshot)
        .where(RegionQualitySnapshot.region_id == region_id)
        .order_by(
            RegionQualitySnapshot.generated_at.desc(),
            RegionQualitySnapshot.id.desc(),
        )
    )


def region_events(session: Session, region_id: int) -> list[Event]:
    return list(
        session.scalars(
            select(Event)
            .options(selectinload(Event.venue))
            .where(Event.region_id == region_id)
            .order_by(Event.start_datetime.asc(), Event.id.asc())
        ).all()
    )


def region_pois(session: Session, region_id: int) -> list[PoiLocation]:
    return list(
        session.scalars(
            select(PoiLocation)
            .where(PoiLocation.region_id == region_id)
            .order_by(PoiLocation.display_name.asc())
        ).all()
    )


def region_sources(session: Session, region_id: int) -> list[MasterCalendarSource]:
    return list(
        session.scalars(
            select(MasterCalendarSource)
            .where(MasterCalendarSource.region_id == region_id)
            .order_by(MasterCalendarSource.source_name.asc())
        ).all()
    )


def region_extracted_candidate_count(session: Session, region_id: int) -> int:
    source_ids = [
        source.id for source in region_sources(session, region_id)
    ]
    if not source_ids:
        return 0
    return scalar_count(
        session,
        select(func.count(SourceExtractedEventCandidate.id)).where(
            SourceExtractedEventCandidate.master_calendar_source_id.in_(source_ids)
        ),
    )


def region_source_coverage(session: Session, region_id: int) -> dict[str, int]:
    sources = region_sources(session, region_id)
    source_ids = [source.id for source in sources]
    events_from_sources = 0
    if source_ids:
        events_from_sources = scalar_count(
            session,
            select(func.count(Event.id)).where(Event.region_id == region_id),
        )
    due_count = sum(
        1
        for source in sources
        if source.status == "approved"
        and source.review_status == SourceReviewStatus.approved.value
        and not source.last_crawled_at
    )
    return {
        "approved_calendar_sources": sum(
            1
            for source in sources
            if source.status == "approved"
            and source.review_status == SourceReviewStatus.approved.value
        ),
        "pending_calendar_sources": sum(
            1
            for source in sources
            if source.status == "pending"
            or source.review_status == SourceReviewStatus.pending_review.value
        ),
        "failed_crawl_sources": sum(
            1 for source in sources if source.last_extraction_status == "failure"
        ),
        "unsupported_extraction_sources": sum(
            1 for source in sources if source.last_extraction_status == "unsupported"
        ),
        "sources_due_for_crawl": due_count,
        "events_found_from_region_sources": events_from_sources,
    }


def seed_type_for_poi(poi: PoiLocation) -> str:
    category = (poi.category or "").strip().lower()
    subcategory = (poi.subcategory or "").strip().lower()
    if "festival" in subcategory:
        return SearchSeedType.festival.value
    if "airport" in subcategory or "airport" in category:
        return SearchSeedType.airport.value
    if "stadium" in subcategory:
        return SearchSeedType.stadium.value
    if category == "music site" and subcategory == "venues":
        return SearchSeedType.venue.value
    return SearchSeedType.poi.value


def seed_type_for_region(region: Region) -> str:
    if region.region_type in {
        RegionType.city.value,
        RegionType.metro.value,
        RegionType.state.value,
        RegionType.country.value,
    }:
        return region.region_type
    if region.region_type == RegionType.tourism_board.value:
        return SearchSeedType.tourism_board.value
    return SearchSeedType.unknown.value


def event_has_ticket_issue(event: Event) -> bool:
    if not (event.recommended_ticket_link or event.tickets_link):
        return True
    classification = (event.ticket_link_classification or "").strip().lower()
    return classification in BAD_TICKET_CLASSIFICATIONS


def event_image_url(event: Event) -> str:
    return event.selected_main_image_url or event.main_image_url or ""


def quality_score_for_counts(total_count: int, issue_count: int) -> int:
    if total_count <= 0:
        return 100
    score = 100 - round((issue_count / max(total_count, 1)) * 100)
    return max(0, min(100, score))


def scalar_count(session: Session, stmt: Any) -> int:
    return int(session.scalar(stmt) or 0)


def safe_int(value: object) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def normalized_place(value: str | None) -> str:
    return normalize_region_key(value)


def haversine_miles(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    earth_radius_miles = 3958.8
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1)
        * math.cos(phi2)
        * math.sin(delta_lambda / 2) ** 2
    )
    return earth_radius_miles * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
