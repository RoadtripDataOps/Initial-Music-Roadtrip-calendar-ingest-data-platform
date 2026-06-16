from __future__ import annotations

import json
import math
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    ApiFeedRecord,
    PoiCandidate,
    PoiCandidateMatchConfidence,
    PoiCandidateMatchStatus,
    PoiCandidateReviewStatus,
    PoiCandidateSourceProvider,
    PoiCandidateSourceType,
    PoiLocation,
    PublishStatus,
    SourceExtractedEventCandidate,
    utc_now,
)
from app.services.extraction_types import EventCandidate
from app.services.file_risk_service import (
    is_direct_image_url,
    is_full_url,
    is_social_url,
)
from app.services.poi_candidate_matching_service import (
    PoiCandidateInput,
    match_poi_candidate,
)
from app.services.poi_registry_service import (
    canonical_poi_id_for_key,
    meters_between,
    normalize_poi_name,
    poi_dedupe_key_for_values,
)

CONCERT_CATEGORY = "Concert"
DEFAULT_VENUE_CATEGORY = "Music Site"
DEFAULT_VENUE_SUBCATEGORY = "Venues"
LOGO_ASSET_MARKERS = (
    "music-roadtrip-logo",
    "/static/images/music-roadtrip-logo",
)
SOCIAL_IMAGE_FLAG = "social_image_url"
NON_DIRECT_IMAGE_FLAG = "non_direct_image_url"


@dataclass(frozen=True)
class PoiCandidateFilters:
    bucket: str | None = None
    review_status: str | None = None
    match_status: str | None = None
    source_provider: str | None = None
    search: str | None = None
    limit: int = 100
    offset: int = 0


@dataclass(frozen=True)
class PoiCandidateBucket:
    key: str
    label: str
    count: int


def json_dumps(value: object) -> str:
    return json.dumps(value, default=str, ensure_ascii=True, sort_keys=True)


def clean_text(value: object | None) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def value_float(value: object | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(str(value).strip())
    except ValueError:
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _json_dict(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_list(value: str | None) -> list[Any]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _domain(value: str | None) -> str | None:
    if not value:
        return None
    host = urlparse(value).hostname
    return host.lower().removeprefix("www.") if host else None


def _similar_name(left: str, right: str) -> bool:
    if left == right:
        return True
    if len(left) < 4 or len(right) < 4:
        return False
    return (
        left in right
        or right in left
        or SequenceMatcher(None, left, right).ratio() >= 0.82
    )


def _is_logo_asset(value: str | None) -> bool:
    if not value:
        return False
    lowered = value.lower()
    return any(marker in lowered for marker in LOGO_ASSET_MARKERS)


def _additional_images(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [
            part.strip()
            for part in value.replace("|", "$").replace("\n", "$").split("$")
            if part.strip()
        ]
    return []


def _payload_text(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        cleaned = clean_text(value)
        if cleaned:
            return cleaned
    return None


def _payload_float(payload: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        parsed = value_float(payload.get(key))
        if parsed is not None:
            return parsed
    return None


def category_suggestion_for_candidate(
    *,
    name: str | None,
    source_url: str | None = None,
    description: str | None = None,
) -> tuple[str, str | None, float]:
    """Suggest a conservative POI category from explicit place text."""

    text = " ".join(part for part in [name, source_url, description] if part).lower()
    if not text.strip():
        return "unknown", None, 0.0
    if any(token in text for token in ["festival", "fairgrounds"]):
        return "Music Site", "Festivals", 0.82
    if any(token in text for token in ["record store", "vinyl", "record shop"]):
        return "Shopping", "Record Stores", 0.82
    if "music store" in text or "guitar shop" in text or "instrument" in text:
        return "Shopping", "Music Stores", 0.78
    if "museum" in text:
        return "Cultural", "Museums", 0.76
    if "performing arts" in text:
        return "Cultural", "Performing Arts Centers", 0.78
    if "theatre" in text or "theater" in text:
        return "Cultural", "Theatres", 0.74
    if "hotel" in text:
        return "Lodging", "Music Hotels", 0.7
    if "camp" in text or "campground" in text:
        return "Lodging", "Music Camping", 0.68
    if "chamber" in text:
        return "Visitor & Travel", "Chamber", 0.7
    if "tourism" in text or "visitor" in text or "travel" in text:
        return "Visitor & Travel", "Travel & Tourism", 0.7
    if any(
        token in text
        for token in [
            "venue",
            "hall",
            "club",
            "stage",
            "amphitheater",
            "amphitheatre",
            "arena",
            "auditorium",
        ]
    ):
        return DEFAULT_VENUE_CATEGORY, DEFAULT_VENUE_SUBCATEGORY, 0.78
    return DEFAULT_VENUE_CATEGORY, DEFAULT_VENUE_SUBCATEGORY, 0.58


def music_signal_score_for_values(
    *,
    name: str | None,
    category: str | None,
    subcategory: str | None,
    description: str | None,
    source_type: str,
) -> float:
    text = " ".join(
        part for part in [name, category, subcategory, description] if part
    ).lower()
    score = 30.0
    if source_type in {
        PoiCandidateSourceType.crawl_extraction.value,
        PoiCandidateSourceType.api_provider.value,
    }:
        score += 20
    if category and category != "unknown":
        score += 12
    if subcategory:
        score += 10
    if any(
        token in text
        for token in [
            "music",
            "concert",
            "venue",
            "festival",
            "record",
            "theatre",
            "theater",
            "studio",
            "stage",
            "club",
            "performing arts",
        ]
    ):
        score += 25
    return min(score, 100.0)


def candidate_quality_flags(candidate: PoiCandidate) -> list[str]:
    flags: list[str] = []
    if not candidate.candidate_name.strip():
        flags.append("missing_name")
    if not (candidate.suggested_category or candidate.category):
        flags.append("missing_category")
    if not (candidate.suggested_subcategory or candidate.subcategory):
        flags.append("missing_subcategory")
    if candidate.category == CONCERT_CATEGORY:
        flags.append("concert_category_not_allowed_for_poi")
    if candidate.latitude is None or candidate.longitude is None:
        flags.append("missing_geo")
    elif abs(candidate.latitude) > 90 or abs(candidate.longitude) > 180:
        flags.append("invalid_geo")
    elif abs(candidate.latitude) > 90 and abs(candidate.longitude) <= 90:
        flags.append("possible_swapped_lat_lng")
    if not (candidate.city and candidate.state):
        flags.append("missing_city_state")
    if not (
        candidate.address
        or (candidate.latitude is not None and candidate.longitude is not None)
    ):
        flags.append("missing_address_or_geo")
    if not (candidate.website or candidate.source_url):
        flags.append("missing_website_or_source_url")

    image = candidate.main_image_url
    if not image:
        flags.append("missing_image")
    elif _is_logo_asset(image):
        flags.append("music_roadtrip_logo_image")
    elif is_social_url(image):
        flags.append(SOCIAL_IMAGE_FLAG)
    elif not is_direct_image_url(image):
        flags.append(NON_DIRECT_IMAGE_FLAG)
    if image and any(token in image.lower() for token in ["poster", "flyer", "admat"]):
        flags.append("poster_flyer_or_admat_image")
    if image and "thumbnail" in image.lower():
        flags.append("low_resolution_thumbnail")
    for extra in candidate.additional_image_urls:
        if _is_logo_asset(extra):
            flags.append("music_roadtrip_logo_image")
        elif is_social_url(extra):
            flags.append("additional_social_image_url")
        elif not is_direct_image_url(extra):
            flags.append("additional_non_direct_image_url")
    if candidate.music_signal_score < 55:
        flags.append("weak_music_signal")
    if candidate.match_confidence == PoiCandidateMatchConfidence.weak.value:
        flags.append("weak_match_requires_review")
    if candidate.match_status == PoiCandidateMatchStatus.possible_duplicate.value:
        flags.append("possible_duplicate")
    return sorted(set(flags))


def score_poi_candidate(candidate: PoiCandidate) -> tuple[float, list[str]]:
    flags = candidate_quality_flags(candidate)
    score = 100.0
    penalties = {
        "missing_name": 35,
        "missing_category": 15,
        "missing_subcategory": 5,
        "concert_category_not_allowed_for_poi": 60,
        "missing_geo": 12,
        "invalid_geo": 35,
        "possible_swapped_lat_lng": 30,
        "missing_city_state": 10,
        "missing_address_or_geo": 18,
        "missing_website_or_source_url": 8,
        "missing_image": 8,
        "music_roadtrip_logo_image": 40,
        SOCIAL_IMAGE_FLAG: 25,
        NON_DIRECT_IMAGE_FLAG: 15,
        "poster_flyer_or_admat_image": 12,
        "low_resolution_thumbnail": 8,
        "weak_music_signal": 12,
        "weak_match_requires_review": 6,
        "possible_duplicate": 8,
    }
    for flag in flags:
        score -= penalties.get(flag, 4)
    if candidate.main_image_url and not any(
        flag in flags
        for flag in {
            "missing_image",
            "music_roadtrip_logo_image",
            SOCIAL_IMAGE_FLAG,
            NON_DIRECT_IMAGE_FLAG,
        }
    ):
        score += 5
    if candidate.match_confidence == PoiCandidateMatchConfidence.strong.value:
        score += 5
    return max(0.0, min(100.0, round(score, 2))), flags


def _candidate_dedupe_key(candidate: PoiCandidate) -> str:
    key, _confidence = poi_dedupe_key_for_values(
        candidate.normalized_name,
        candidate.latitude,
        candidate.longitude,
        city=candidate.city,
        state=candidate.state,
        address=candidate.address,
    )
    return key


def _apply_match(candidate: PoiCandidate, session: Session) -> None:
    match = match_poi_candidate(
        session,
        PoiCandidateInput(
            display_name=candidate.candidate_name,
            latitude=candidate.latitude,
            longitude=candidate.longitude,
            website=candidate.website,
            phone=candidate.phone,
            city=candidate.city,
            state=candidate.state,
        ),
    )
    candidate.match_confidence = match.confidence
    candidate.matched_poi_location_id = None
    reason: dict[str, object] = {
        "match_source": match.match_source,
        "match_strategy": match.match_strategy,
        "canonical_poi_id": match.canonical_poi_id,
    }
    if match.poi_id is not None:
        reason["suggested_poi_location_id"] = match.poi_id
    if match.snapshot_records:
        reason["snapshot_records"] = list(match.snapshot_records[:5])

    if match.confidence == PoiCandidateMatchConfidence.strong.value:
        candidate.matched_poi_location_id = match.poi_id
        candidate.match_status = PoiCandidateMatchStatus.matched_existing.value
    elif match.confidence == PoiCandidateMatchConfidence.medium.value:
        candidate.matched_poi_location_id = match.poi_id
        candidate.match_status = PoiCandidateMatchStatus.possible_duplicate.value
    elif match.confidence == PoiCandidateMatchConfidence.weak.value:
        candidate.match_status = PoiCandidateMatchStatus.possible_duplicate.value
    else:
        fallback = _nearby_database_match(session, candidate)
        if fallback is not None:
            poi, confidence, fallback_reason = fallback
            if confidence != PoiCandidateMatchConfidence.weak.value:
                candidate.matched_poi_location_id = poi.id
            candidate.match_confidence = confidence
            candidate.match_status = PoiCandidateMatchStatus.possible_duplicate.value
            fallback_reason["suggested_poi_location_id"] = poi.id
            reason.update(fallback_reason)
        else:
            candidate.match_status = PoiCandidateMatchStatus.new_candidate.value
    candidate.match_reason_json = json_dumps(reason)


def _nearby_database_match(
    session: Session,
    candidate: PoiCandidate,
) -> tuple[PoiLocation, str, dict[str, object]] | None:
    if not candidate.normalized_name:
        return None
    pois = list(
        session.scalars(
            select(PoiLocation)
            .where(func.lower(PoiLocation.category) != CONCERT_CATEGORY.casefold())
            .order_by(PoiLocation.id.asc())
        ).all()
    )
    candidate_domain = _domain(candidate.website)
    for poi in pois:
        poi_normalized_name = normalize_poi_name(poi.display_name)
        similar_name = _similar_name(poi_normalized_name, candidate.normalized_name)
        same_city_state = (
            (poi.city or "").casefold() == (candidate.city or "").casefold()
            and (poi.state or "").casefold() == (candidate.state or "").casefold()
        )
        if (
            similar_name
            and candidate.latitude is not None
            and candidate.longitude is not None
            and poi.latitude is not None
            and poi.longitude is not None
        ):
            distance = meters_between(
                candidate.latitude,
                candidate.longitude,
                poi.latitude,
                poi.longitude,
            )
            if distance <= 50:
                return (
                    poi,
                    PoiCandidateMatchConfidence.medium.value,
                    {
                        "match_source": "database",
                        "match_strategy": "similar_name_nearby_geo",
                        "distance_meters": round(distance, 2),
                    },
                )
        if similar_name and same_city_state:
            poi_domain = _domain(poi.website)
            if candidate_domain and poi_domain and candidate_domain == poi_domain:
                return (
                    poi,
                    PoiCandidateMatchConfidence.weak.value,
                    {
                        "match_source": "database",
                        "match_strategy": "same_name_city_state_domain",
                        "domain": candidate_domain,
                    },
                )
            if candidate.phone and poi.phone and candidate.phone == poi.phone:
                return (
                    poi,
                    PoiCandidateMatchConfidence.weak.value,
                    {
                        "match_source": "database",
                        "match_strategy": "same_name_city_state_phone",
                    },
                )
    return None


def normalize_poi_candidate(
    candidate: PoiCandidate,
    session: Session | None = None,
) -> None:
    candidate.candidate_name = clean_text(candidate.candidate_name) or "Unknown POI"
    candidate.normalized_name = normalize_poi_name(candidate.candidate_name)
    candidate.category = clean_text(candidate.category)
    candidate.subcategory = clean_text(candidate.subcategory)
    candidate.suggested_category = clean_text(candidate.suggested_category)
    candidate.suggested_subcategory = clean_text(candidate.suggested_subcategory)
    if candidate.category == CONCERT_CATEGORY:
        candidate.category = None
    if not candidate.suggested_category:
        suggested_category, suggested_subcategory, confidence = (
            category_suggestion_for_candidate(
                name=candidate.candidate_name,
                source_url=candidate.source_url,
                description=candidate.description,
            )
        )
        candidate.suggested_category = suggested_category
        candidate.suggested_subcategory = suggested_subcategory
        if confidence < 0.55:
            candidate.review_status = PoiCandidateReviewStatus.needs_research.value
    if not candidate.category and candidate.suggested_category != "unknown":
        candidate.category = candidate.suggested_category
    if not candidate.subcategory and candidate.suggested_subcategory:
        candidate.subcategory = candidate.suggested_subcategory
    candidate.music_signal_score = music_signal_score_for_values(
        name=candidate.candidate_name,
        category=candidate.category or candidate.suggested_category,
        subcategory=candidate.subcategory or candidate.suggested_subcategory,
        description=candidate.description,
        source_type=candidate.source_type,
    )
    candidate.dedupe_key = _candidate_dedupe_key(candidate)
    if session is not None:
        _apply_match(candidate, session)
    score, flags = score_poi_candidate(candidate)
    candidate.poi_quality_score = score
    candidate.poi_quality_flags_json = json_dumps(flags)
    candidate.normalized_payload_json = json_dumps(candidate_payload(candidate))


def candidate_payload(candidate: PoiCandidate) -> dict[str, object]:
    return {
        "candidate_name": candidate.candidate_name,
        "normalized_name": candidate.normalized_name,
        "category": candidate.category,
        "subcategory": candidate.subcategory,
        "suggested_category": candidate.suggested_category,
        "suggested_subcategory": candidate.suggested_subcategory,
        "address": candidate.address,
        "city": candidate.city,
        "state": candidate.state,
        "zip_code": candidate.zip_code,
        "country": candidate.country,
        "latitude": candidate.latitude,
        "longitude": candidate.longitude,
        "website": candidate.website,
        "phone": candidate.phone,
        "email": candidate.email,
        "instagram": candidate.instagram,
        "facebook": candidate.facebook,
        "x_url": candidate.x_url,
        "tiktok": candidate.tiktok,
        "youtube": candidate.youtube,
        "spotify_url": candidate.spotify_url,
        "main_image_url": candidate.main_image_url,
        "additional_image_urls": candidate.additional_image_urls,
        "description": candidate.description,
        "music_signal_score": candidate.music_signal_score,
        "poi_quality_score": candidate.poi_quality_score,
        "quality_flags": candidate.poi_quality_flags,
        "dedupe_key": candidate.dedupe_key,
        "match_status": candidate.match_status,
        "match_confidence": candidate.match_confidence,
        "matched_poi_location_id": candidate.matched_poi_location_id,
        "source": {
            "source_type": candidate.source_type,
            "source_provider": candidate.source_provider,
            "source_url": candidate.source_url,
            "source_name": candidate.source_name,
        },
    }


def _existing_candidate(
    session: Session,
    *,
    source_type: str,
    source_provider: str | None,
    api_feed_record_id: int | None = None,
    crawl_run_id: int | None = None,
    candidate_name: str,
    city: str | None,
    state: str | None,
) -> PoiCandidate | None:
    normalized = normalize_poi_name(candidate_name)
    stmt = select(PoiCandidate).where(
        PoiCandidate.source_type == source_type,
        PoiCandidate.normalized_name == normalized,
    )
    if source_provider:
        stmt = stmt.where(PoiCandidate.source_provider == source_provider)
    if api_feed_record_id:
        stmt = stmt.where(PoiCandidate.api_feed_record_id == api_feed_record_id)
    if crawl_run_id:
        stmt = stmt.where(PoiCandidate.crawl_run_id == crawl_run_id)
    if city:
        stmt = stmt.where(PoiCandidate.city == city)
    if state:
        stmt = stmt.where(PoiCandidate.state == state)
    return session.scalars(stmt).first()


def create_poi_candidate_from_extraction(
    session: Session,
    *,
    staged_event: SourceExtractedEventCandidate,
    event_candidate: EventCandidate,
    extractor_type: str,
) -> PoiCandidate | None:
    """Stage a POI candidate from event-location extraction without promotion."""

    if not event_candidate.venue_name:
        return None
    existing = _existing_candidate(
        session,
        source_type=PoiCandidateSourceType.crawl_extraction.value,
        source_provider=PoiCandidateSourceProvider.source_crawl.value,
        crawl_run_id=staged_event.crawl_run_id,
        candidate_name=event_candidate.venue_name,
        city=event_candidate.city,
        state=event_candidate.state,
    )
    if existing is not None:
        return None
    candidate = PoiCandidate(
        source_type=PoiCandidateSourceType.crawl_extraction.value,
        source_provider=PoiCandidateSourceProvider.source_crawl.value,
        crawl_run_id=staged_event.crawl_run_id,
        master_calendar_source_id=staged_event.master_calendar_source_id,
        extracted_event_candidate_id=staged_event.id,
        source_url=event_candidate.event_url or staged_event.source_url,
        source_name=extractor_type,
        raw_fragment_json=json_dumps(event_candidate.raw_fragment),
        candidate_name=event_candidate.venue_name,
        address=event_candidate.venue_address,
        city=event_candidate.city,
        state=event_candidate.state,
        zip_code=event_candidate.zip_code,
        country=event_candidate.country,
        latitude=event_candidate.latitude,
        longitude=event_candidate.longitude,
        website=event_candidate.event_url,
        main_image_url=None,
        description=None,
        suggested_category=DEFAULT_VENUE_CATEGORY,
        suggested_subcategory=DEFAULT_VENUE_SUBCATEGORY,
    )
    normalize_poi_candidate(candidate, session)
    session.add(candidate)
    return candidate


def create_poi_candidate_from_extraction_payload(
    session: Session,
    *,
    crawl_run_id: int,
    master_calendar_source_id: int | None,
    payload: object,
    extractor_type: str,
) -> PoiCandidate | None:
    """Stage a standalone extractor POI payload without POI promotion."""

    data = payload if isinstance(payload, dict) else {"value": str(payload)}
    name = _payload_text(
        data,
        "candidate_name",
        "venue_name",
        "place_name",
        "display_name",
        "name",
    )
    if not name:
        return None
    city = _payload_text(data, "city", "addressLocality")
    state = _payload_text(data, "state", "addressRegion")
    existing = _existing_candidate(
        session,
        source_type=PoiCandidateSourceType.crawl_extraction.value,
        source_provider=PoiCandidateSourceProvider.source_crawl.value,
        crawl_run_id=crawl_run_id,
        candidate_name=name,
        city=city,
        state=state,
    )
    if existing is not None:
        return None

    suggested_category = _payload_text(data, "suggested_category", "category")
    suggested_subcategory = _payload_text(
        data,
        "suggested_subcategory",
        "subcategory",
    )
    candidate = PoiCandidate(
        source_type=PoiCandidateSourceType.crawl_extraction.value,
        source_provider=PoiCandidateSourceProvider.source_crawl.value,
        crawl_run_id=crawl_run_id,
        master_calendar_source_id=master_calendar_source_id,
        source_url=_payload_text(data, "source_url", "url", "website"),
        source_name=extractor_type,
        raw_fragment_json=json_dumps(data),
        candidate_name=name,
        address=_payload_text(data, "address", "streetAddress", "venue_address"),
        city=city,
        state=state,
        zip_code=_payload_text(data, "zip_code", "postalCode"),
        country=_payload_text(data, "country", "addressCountry"),
        latitude=_payload_float(data, "latitude", "lat"),
        longitude=_payload_float(data, "longitude", "lng", "lon"),
        website=_payload_text(data, "website", "url"),
        phone=_payload_text(data, "phone", "telephone"),
        email=_payload_text(data, "email"),
        instagram=_payload_text(data, "instagram"),
        facebook=_payload_text(data, "facebook"),
        x_url=_payload_text(data, "x_url", "twitter"),
        tiktok=_payload_text(data, "tiktok"),
        youtube=_payload_text(data, "youtube"),
        spotify_url=_payload_text(data, "spotify_url"),
        main_image_url=_payload_text(data, "main_image_url", "image"),
        additional_image_urls_json=json_dumps(
            _additional_images(data.get("additional_image_urls"))
        ),
        description=_payload_text(data, "description"),
        suggested_category=suggested_category,
        suggested_subcategory=suggested_subcategory,
    )
    normalize_poi_candidate(candidate, session)
    session.add(candidate)
    return candidate


def _provider_source(provider_key: str) -> str:
    if provider_key == "jambase":
        return PoiCandidateSourceProvider.jambase.value
    if provider_key == "cityspark":
        return PoiCandidateSourceProvider.cityspark.value
    if provider_key == "manual_json":
        return PoiCandidateSourceProvider.manual_json.value
    return PoiCandidateSourceProvider.unknown.value


def create_poi_candidate_from_provider_location(
    session: Session,
    record: ApiFeedRecord,
) -> PoiCandidate | None:
    """Stage provider venue/location data as a POI candidate for audit."""

    if not record.venue_name:
        return None
    provider_source = _provider_source(record.provider_key)
    existing = _existing_candidate(
        session,
        source_type=PoiCandidateSourceType.api_provider.value,
        source_provider=provider_source,
        api_feed_record_id=record.id,
        candidate_name=record.venue_name,
        city=record.city,
        state=record.state,
    )
    if existing is not None:
        return None
    raw_payload = _json_dict(record.raw_payload_json)
    venue_payload = _json_dict(record.venue_match_fields_json)
    candidate = PoiCandidate(
        source_type=PoiCandidateSourceType.api_provider.value,
        source_provider=provider_source,
        api_feed_run_id=record.api_feed_run_id,
        api_feed_record_id=record.id,
        source_url=record.event_url or record.source_url,
        source_name=record.provider_key,
        raw_fragment_json=json_dumps(
            {
                "venue_match_fields": venue_payload,
                "raw_payload": raw_payload,
            }
        ),
        candidate_name=record.venue_name,
        address=record.venue_address,
        city=record.city,
        state=record.state,
        zip_code=record.zip_code,
        country=record.country,
        latitude=record.latitude,
        longitude=record.longitude,
        website=clean_text(venue_payload.get("venue_source_url")) or record.event_url,
        main_image_url=clean_text(venue_payload.get("venue_image_url")),
        additional_image_urls_json=json_dumps([]),
        description=None,
        suggested_category=DEFAULT_VENUE_CATEGORY,
        suggested_subcategory=DEFAULT_VENUE_SUBCATEGORY,
    )
    normalize_poi_candidate(candidate, session)
    session.add(candidate)
    return candidate


def get_poi_candidate(session: Session, candidate_id: int) -> PoiCandidate | None:
    return session.get(PoiCandidate, candidate_id)


def list_poi_candidates(
    session: Session,
    filters: PoiCandidateFilters | None = None,
) -> list[PoiCandidate]:
    filters = filters or PoiCandidateFilters()
    stmt = select(PoiCandidate).order_by(
        PoiCandidate.updated_at.desc(),
        PoiCandidate.id.desc(),
    )
    if filters.review_status:
        stmt = stmt.where(PoiCandidate.review_status == filters.review_status)
    if filters.match_status:
        stmt = stmt.where(PoiCandidate.match_status == filters.match_status)
    if filters.source_provider:
        stmt = stmt.where(PoiCandidate.source_provider == filters.source_provider)
    if filters.search:
        search = f"%{filters.search.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(PoiCandidate.candidate_name).like(search),
                func.lower(PoiCandidate.city).like(search),
                func.lower(PoiCandidate.state).like(search),
            )
        )
    candidates = list(session.scalars(stmt).all())
    if filters.bucket:
        candidates = [
            candidate
            for candidate in candidates
            if _candidate_in_bucket(candidate, filters.bucket)
        ]
    return candidates[filters.offset : filters.offset + filters.limit]


def _candidate_in_bucket(candidate: PoiCandidate, bucket: str) -> bool:
    flags = set(candidate.poi_quality_flags)
    return {
        "pending_review": candidate.review_status == "pending_review",
        "matched_existing": candidate.match_status == "matched_existing",
        "possible_duplicate": candidate.match_status == "possible_duplicate",
        "new_candidate": candidate.match_status == "new_candidate",
        "needs_research": candidate.review_status == "needs_research",
        "missing_coordinates": "missing_geo" in flags,
        "missing_image": "missing_image" in flags,
        "bad_social_image": bool(
            flags
            & {
                SOCIAL_IMAGE_FLAG,
                NON_DIRECT_IMAGE_FLAG,
                "additional_social_image_url",
                "music_roadtrip_logo_image",
            }
        ),
        "missing_category": "missing_category" in flags,
        "weak_music_signal": "weak_music_signal" in flags,
        "event_venue_only": candidate.match_status == "event_venue_only",
        "approved_created": candidate.match_status == "approved_created",
        "rejected": candidate.review_status == "rejected",
    }.get(bucket, False)


def list_candidate_buckets(session: Session) -> list[PoiCandidateBucket]:
    candidates = list(session.scalars(select(PoiCandidate)).all())
    bucket_labels = [
        ("pending_review", "Pending review"),
        ("matched_existing", "Matched existing POI"),
        ("possible_duplicate", "Possible duplicate"),
        ("new_candidate", "New candidate"),
        ("needs_research", "Needs research"),
        ("missing_coordinates", "Missing coordinates"),
        ("missing_image", "Missing image"),
        ("bad_social_image", "Bad/social image URL"),
        ("missing_category", "Missing category"),
        ("weak_music_signal", "Weak music signal"),
        ("event_venue_only", "Event venue only"),
        ("approved_created", "Approved created"),
        ("rejected", "Rejected"),
    ]
    return [
        PoiCandidateBucket(
            key=key,
            label=label,
            count=sum(_candidate_in_bucket(candidate, key) for candidate in candidates),
        )
        for key, label in bucket_labels
    ]


def poi_candidate_dashboard_counts(session: Session) -> dict[str, int]:
    candidates = list(session.scalars(select(PoiCandidate)).all())
    return {
        "pending": sum(
            candidate.review_status == PoiCandidateReviewStatus.pending_review.value
            for candidate in candidates
        ),
        "possible_duplicates": sum(
            candidate.match_status == PoiCandidateMatchStatus.possible_duplicate.value
            for candidate in candidates
        ),
        "missing_images": sum(
            "missing_image" in candidate.poi_quality_flags for candidate in candidates
        ),
        "needs_research": sum(
            candidate.review_status == PoiCandidateReviewStatus.needs_research.value
            for candidate in candidates
        ),
        "approved_created": sum(
            candidate.match_status == PoiCandidateMatchStatus.approved_created.value
            for candidate in candidates
        ),
        "rejected": sum(
            candidate.review_status == PoiCandidateReviewStatus.rejected.value
            for candidate in candidates
        ),
        "event_venue_only": sum(
            candidate.match_status == PoiCandidateMatchStatus.event_venue_only.value
            for candidate in candidates
        ),
    }


def recompute_candidate_match_quality(
    session: Session,
    candidate_id: int,
) -> PoiCandidate:
    candidate = get_poi_candidate(session, candidate_id)
    if candidate is None:
        raise ValueError("POI candidate not found.")
    normalize_poi_candidate(candidate, session)
    candidate.updated_at = utc_now()
    session.add(candidate)
    session.commit()
    session.refresh(candidate)
    return candidate


def recompute_all_pending_candidates(session: Session) -> dict[str, int]:
    candidates = list(
        session.scalars(
            select(PoiCandidate).where(
                PoiCandidate.review_status.in_(
                    {
                        PoiCandidateReviewStatus.pending_review.value,
                        PoiCandidateReviewStatus.needs_research.value,
                    }
                )
            )
        ).all()
    )
    for candidate in candidates:
        normalize_poi_candidate(candidate, session)
        candidate.updated_at = utc_now()
        session.add(candidate)
    session.commit()
    return {"candidate_count": len(candidates)}


def _poi_values_from_candidate(candidate: PoiCandidate) -> dict[str, object]:
    category = (
        candidate.category or candidate.suggested_category or DEFAULT_VENUE_CATEGORY
    )
    subcategory = candidate.subcategory or candidate.suggested_subcategory
    dedupe_key = candidate.dedupe_key or _candidate_dedupe_key(candidate)
    canonical_id = canonical_poi_id_for_key(dedupe_key)
    raw = {
        "poi_candidate_id": candidate.id,
        "source_type": candidate.source_type,
        "source_provider": candidate.source_provider,
        "source_url": candidate.source_url,
        "raw_fragment": candidate.raw_fragment,
        "normalized_payload": candidate.normalized_payload,
        "quality_flags": candidate.poi_quality_flags,
        "match_reason": candidate.match_reason,
    }
    return {
        "canonical_poi_id": canonical_id,
        "poi_dedupe_key": dedupe_key,
        "poi_dedupe_confidence": candidate.match_confidence
        if candidate.match_confidence != "none"
        else "weak",
        "source_type": "poi_candidate",
        "source_record_id": f"poi-candidate-{candidate.id}",
        "display_name": candidate.candidate_name,
        "normalized_name": candidate.normalized_name,
        "category": category,
        "subcategory": subcategory,
        "latitude": candidate.latitude,
        "longitude": candidate.longitude,
        "address": candidate.address,
        "city": candidate.city,
        "state": candidate.state,
        "zip_code": candidate.zip_code,
        "country": candidate.country,
        "website": candidate.website or candidate.source_url,
        "phone": candidate.phone,
        "email": candidate.email,
        "instagram": candidate.instagram,
        "facebook": candidate.facebook,
        "x_url": candidate.x_url,
        "tiktok": candidate.tiktok,
        "spotify_url": candidate.spotify_url,
        "main_image_url": (
            candidate.main_image_url
            if candidate.main_image_url
            and not _is_logo_asset(candidate.main_image_url)
            and is_direct_image_url(candidate.main_image_url)
            else None
        ),
        "additional_image_urls": "$".join(
            image
            for image in candidate.additional_image_urls
            if is_direct_image_url(image) and not _is_logo_asset(image)
        )
        or None,
        "description": candidate.description,
        "photo_quality_score": candidate.poi_quality_score,
        "quality_control": ", ".join(candidate.poi_quality_flags) or None,
        "raw_source_json": json_dumps(raw),
        "publish_status": PublishStatus.approved.value,
    }


def _safe_update_fields(candidate: PoiCandidate) -> dict[str, object | None]:
    values = _poi_values_from_candidate(candidate)
    allowed = {
        "subcategory",
        "latitude",
        "longitude",
        "address",
        "city",
        "state",
        "zip_code",
        "country",
        "website",
        "phone",
        "email",
        "instagram",
        "facebook",
        "x_url",
        "tiktok",
        "spotify_url",
        "main_image_url",
        "additional_image_urls",
        "description",
        "photo_quality_score",
        "quality_control",
        "raw_source_json",
    }
    return {key: values.get(key) for key in allowed}


def approve_candidate_create_poi(
    session: Session,
    candidate_id: int,
) -> PoiLocation:
    candidate = get_poi_candidate(session, candidate_id)
    if candidate is None:
        raise ValueError("POI candidate not found.")
    if candidate.review_status == PoiCandidateReviewStatus.quarantined.value:
        raise ValueError("Quarantined POI candidates cannot be approved.")
    if candidate.category == CONCERT_CATEGORY:
        raise ValueError("Concert candidates cannot create POI records.")
    if candidate.match_confidence == PoiCandidateMatchConfidence.strong.value:
        raise ValueError("Strongly matched candidates should be linked or updated.")
    values = _poi_values_from_candidate(candidate)
    existing = session.scalars(
        select(PoiLocation).where(
            or_(
                PoiLocation.canonical_poi_id == values["canonical_poi_id"],
                PoiLocation.poi_dedupe_key == values["poi_dedupe_key"],
            )
        )
    ).first()
    if existing is not None:
        candidate.matched_poi_location_id = existing.id
        candidate.match_status = PoiCandidateMatchStatus.matched_existing.value
        candidate.match_confidence = PoiCandidateMatchConfidence.strong.value
        session.add(candidate)
        session.commit()
        raise ValueError("A matching POI already exists; link or update it instead.")
    poi = PoiLocation(**values)
    session.add(poi)
    session.flush()
    candidate.created_poi_location_id = poi.id
    candidate.review_status = PoiCandidateReviewStatus.approved.value
    candidate.match_status = PoiCandidateMatchStatus.approved_created.value
    candidate.updated_at = utc_now()
    session.add(candidate)
    session.commit()
    session.refresh(poi)
    return poi


def link_candidate_to_existing_poi(
    session: Session,
    candidate_id: int,
    poi_location_id: int | None = None,
) -> PoiCandidate:
    candidate = get_poi_candidate(session, candidate_id)
    if candidate is None:
        raise ValueError("POI candidate not found.")
    target_id = poi_location_id or candidate.matched_poi_location_id
    if target_id is None:
        raise ValueError("A POI location ID is required.")
    poi = session.get(PoiLocation, target_id)
    if poi is None:
        raise ValueError("POI location not found.")
    candidate.matched_poi_location_id = poi.id
    candidate.match_status = PoiCandidateMatchStatus.matched_existing.value
    candidate.match_confidence = (
        candidate.match_confidence
        if candidate.match_confidence != PoiCandidateMatchConfidence.none.value
        else PoiCandidateMatchConfidence.strong.value
    )
    candidate.review_status = PoiCandidateReviewStatus.approved.value
    candidate.updated_at = utc_now()
    session.add(candidate)
    session.commit()
    session.refresh(candidate)
    return candidate


def approve_candidate_update_existing_poi(
    session: Session,
    candidate_id: int,
    poi_location_id: int | None = None,
) -> PoiLocation:
    candidate = link_candidate_to_existing_poi(session, candidate_id, poi_location_id)
    poi = session.get(PoiLocation, candidate.matched_poi_location_id)
    if poi is None:
        raise ValueError("POI location not found.")
    updates = _safe_update_fields(candidate)
    changed: list[str] = []
    for field_name, value in updates.items():
        if value in {None, ""}:
            continue
        current = getattr(poi, field_name)
        if current in {None, ""} or field_name in {
            "photo_quality_score",
            "quality_control",
            "raw_source_json",
        }:
            setattr(poi, field_name, value)
            changed.append(field_name)
    candidate.match_status = PoiCandidateMatchStatus.approved_updated.value
    candidate.review_status = PoiCandidateReviewStatus.approved.value
    reason = dict(candidate.match_reason)
    reason["updated_fields"] = changed
    candidate.match_reason_json = json_dumps(reason)
    candidate.updated_at = utc_now()
    poi.updated_at = utc_now()
    session.add_all([candidate, poi])
    session.commit()
    session.refresh(poi)
    return poi


def mark_candidate_event_venue_only(
    session: Session,
    candidate_id: int,
) -> PoiCandidate:
    candidate = get_poi_candidate(session, candidate_id)
    if candidate is None:
        raise ValueError("POI candidate not found.")
    candidate.match_status = PoiCandidateMatchStatus.event_venue_only.value
    candidate.review_status = PoiCandidateReviewStatus.approved.value
    candidate.updated_at = utc_now()
    session.add(candidate)
    session.commit()
    session.refresh(candidate)
    return candidate


def mark_candidate_needs_research(
    session: Session,
    candidate_id: int,
) -> PoiCandidate:
    candidate = get_poi_candidate(session, candidate_id)
    if candidate is None:
        raise ValueError("POI candidate not found.")
    candidate.review_status = PoiCandidateReviewStatus.needs_research.value
    candidate.updated_at = utc_now()
    session.add(candidate)
    session.commit()
    session.refresh(candidate)
    return candidate


def reject_poi_candidate(
    session: Session,
    candidate_id: int,
    reason: str | None = None,
) -> PoiCandidate:
    candidate = get_poi_candidate(session, candidate_id)
    if candidate is None:
        raise ValueError("POI candidate not found.")
    candidate.review_status = PoiCandidateReviewStatus.rejected.value
    candidate.match_status = PoiCandidateMatchStatus.rejected.value
    candidate.rejection_reason = clean_text(reason)
    candidate.updated_at = utc_now()
    session.add(candidate)
    session.commit()
    session.refresh(candidate)
    return candidate


def create_manual_poi_candidate(
    session: Session,
    *,
    name: str,
    city: str | None = None,
    state: str | None = None,
    source_url: str | None = None,
) -> PoiCandidate:
    candidate = PoiCandidate(
        source_type=PoiCandidateSourceType.manual_admin.value,
        source_provider=PoiCandidateSourceProvider.unknown.value,
        source_url=source_url if source_url and is_full_url(source_url) else None,
        candidate_name=name,
        city=city,
        state=state,
    )
    normalize_poi_candidate(candidate, session)
    session.add(candidate)
    session.commit()
    session.refresh(candidate)
    return candidate
