from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, TypedDict
from urllib.parse import urlparse

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import PoiLocation, utc_now

RowKind = Literal["event", "poi"]
DuplicateConfidence = Literal["strong", "medium", "weak"]

CONCERT_CATEGORY = "Concert"
SOURCE_EXPORT_DEFAULT = "Mapotic_Export_6_11_26.csv"

SUBCATEGORY_COLUMNS: dict[str, str | None] = {
    "Music Site": "Music Site",
    "Cultural": "Cultural",
    "Food & Bev": "Food & Bev",
    "Shopping": "Shopping",
    "Visitor & Travel": "Visitor & Travel",
    "Lodging": "Lodging",
    "Bars & Lounges": None,
}

POI_CATEGORIES = set(SUBCATEGORY_COLUMNS)

SOCIAL_OR_VIDEO_HOST_PARTS = (
    "facebook.com",
    "fb.com",
    "instagram.com",
    "tiktok.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "youtu.be",
)

LOGO_ASSET_PATH_PARTS = (
    "music-roadtrip-logo-square.png",
    "music-roadtrip-logo-circle.png",
    "music-roadtrip-logo-plate.png",
)

LEGAL_SUFFIX_PATTERN = re.compile(
    r"\b(incorporated|inc|llc|l\.l\.c|corp|corporation|co|company|ltd|limited)\b",
    re.IGNORECASE,
)
PUNCTUATION_PATTERN = re.compile(r"[^\w\s&]", re.UNICODE)
SPACE_PATTERN = re.compile(r"\s+")


class PoiRegistryRecord(TypedDict):
    source_export: str
    mapotic_id: str | None
    import_id: str | None
    places_id: str | None
    canonical_poi_id: str
    canonical_name: str
    display_name: str
    category: str
    subcategory: str | None
    latitude: float | None
    longitude: float | None
    geohash_or_geo_key: str | None
    address: str | None
    city: str | None
    state: str | None
    zip_code: str | None
    country: str | None
    website: str | None
    phone: str | None
    email: str | None
    instagram: str | None
    facebook: str | None
    x_url: str | None
    tiktok: str | None
    youtube_or_video: str | None
    spotify_url: str | None
    main_image_url: str | None
    additional_image_urls: str | None
    description: str | None
    hours_of_operation: str | None
    rating: float | None
    review_count_google: int | None
    review_count_yelp: int | None
    certified: bool | None
    carousel_selection: str | None
    business_status: str | None
    last_verified_at: str | None
    canonical_venue_id: str | None
    venue_match_confidence: float | None
    photo_quality_score: float | None
    quality_control: str | None
    raw_row_hash: str
    raw_row_json: dict[str, str]
    poi_dedupe_key: str
    poi_dedupe_confidence: str


@dataclass(frozen=True)
class ParsedMapoticCategory:
    kind: RowKind
    category: str
    subcategory: str | None


@dataclass(frozen=True)
class MinimalPoi:
    mapotic_id: str | None
    places_id: str | None
    canonical_venue_id: str | None
    display_name: str
    normalized_name: str
    category: str
    subcategory: str | None
    latitude: float | None
    longitude: float | None
    city: str | None
    state: str | None
    website: str | None
    phone: str | None
    address: str | None
    poi_dedupe_key: str


@dataclass(frozen=True)
class ImportPoiRegistrySummary:
    created: int = 0
    updated: int = 0
    duplicate: int = 0
    skipped: int = 0


def clean_text(value: object | None) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def row_value(row: Mapping[str, str], *headers: str) -> str | None:
    for header in headers:
        value = clean_text(row.get(header))
        if value is not None:
            return value
    return None


def parse_mapotic_category(row: Mapping[str, str]) -> ParsedMapoticCategory:
    category = row_value(row, "Category") or ""
    if category.casefold() == CONCERT_CATEGORY.casefold():
        return ParsedMapoticCategory(
            kind="event",
            category=CONCERT_CATEGORY,
            subcategory=None,
        )
    subcategory_header = SUBCATEGORY_COLUMNS.get(category)
    subcategory = row_value(row, subcategory_header) if subcategory_header else None
    return ParsedMapoticCategory(kind="poi", category=category, subcategory=subcategory)


def normalize_poi_name(name: str | None) -> str:
    if not name:
        return ""
    normalized = unicodedata.normalize("NFKD", name)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_name.casefold().replace("&", " and ")
    without_suffix = LEGAL_SUFFIX_PATTERN.sub(" ", lowered)
    without_punctuation = PUNCTUATION_PATTERN.sub(" ", without_suffix)
    return SPACE_PATTERN.sub(" ", without_punctuation).strip()


def parse_float(value: str | None) -> float | None:
    if not value:
        return None
    try:
        parsed = float(value.replace(",", ""))
    except ValueError:
        return None
    if math.isnan(parsed) or math.isinf(parsed):
        return None
    return parsed


def parse_int(value: str | None) -> int | None:
    parsed = parse_float(value)
    return int(parsed) if parsed is not None else None


def parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().casefold()
    if normalized in {"true", "yes", "y", "1"}:
        return True
    if normalized in {"false", "no", "n", "0"}:
        return False
    return None


def rounded_coordinate(value: float | None) -> str | None:
    if value is None:
        return None
    return f"{value:.5f}"


def geo_key(latitude: float | None, longitude: float | None) -> str | None:
    rounded_latitude = rounded_coordinate(latitude)
    rounded_longitude = rounded_coordinate(longitude)
    if rounded_latitude is None or rounded_longitude is None:
        return None
    return f"lat:{rounded_latitude}|lng:{rounded_longitude}"


def is_social_or_video_url(url: str) -> bool:
    host = urlparse(url).netloc.casefold()
    return any(part in host for part in SOCIAL_OR_VIDEO_HOST_PARTS)


def is_logo_asset_url(url: str) -> bool:
    lowered = url.casefold()
    return any(part in lowered for part in LOGO_ASSET_PATH_PARTS)


def direct_image_url_or_none(value: str | None) -> str | None:
    url = clean_text(value)
    if url is None:
        return None
    if is_social_or_video_url(url) or is_logo_asset_url(url):
        return None
    return url


def split_multi_url_field(value: str | None) -> list[str]:
    if value is None:
        return []
    pieces = re.split(r"[$|\n\r]+", value)
    return [piece.strip() for piece in pieces if piece.strip()]


def direct_image_url_list(value: str | None) -> str | None:
    urls = [
        url
        for url in split_multi_url_field(value)
        if not is_social_or_video_url(url) and not is_logo_asset_url(url)
    ]
    return "$".join(urls) if urls else None


def poi_dedupe_key_for_values(
    normalized_name: str,
    latitude: float | None,
    longitude: float | None,
    *,
    places_id: str | None = None,
    mapotic_id: str | None = None,
    canonical_venue_id: str | None = None,
    city: str | None = None,
    state: str | None = None,
    address: str | None = None,
) -> tuple[str, DuplicateConfidence]:
    geo = geo_key(latitude, longitude)
    if normalized_name and geo:
        return f"name_geo:{normalized_name}|{geo}", "strong"
    if places_id:
        return f"places_id:{places_id.casefold()}", "strong"
    if canonical_venue_id:
        return f"canonical_venue_id:{canonical_venue_id.casefold()}", "strong"
    if mapotic_id:
        return f"mapotic_id:{mapotic_id.casefold()}", "strong"
    location_parts = [
        normalized_name,
        (city or "").casefold(),
        (state or "").casefold(),
        normalize_poi_name(address),
    ]
    return "name_location:" + "|".join(location_parts), "weak"


def canonical_poi_id_for_key(poi_dedupe_key: str) -> str:
    digest = hashlib.sha256(poi_dedupe_key.encode("utf-8")).hexdigest()
    return f"poi_{digest[:16]}"


def stable_row_hash(row: Mapping[str, str]) -> str:
    payload = json.dumps(dict(row), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def poi_registry_record_from_row(
    row: Mapping[str, str],
    *,
    source_export: str = SOURCE_EXPORT_DEFAULT,
) -> PoiRegistryRecord | None:
    parsed_category = parse_mapotic_category(row)
    if parsed_category.kind == "event":
        return None

    display_name = row_value(row, "Name (en)", "Name (es)") or "Untitled POI"
    normalized_name = normalize_poi_name(display_name)
    latitude = parse_float(row_value(row, "Latitude"))
    longitude = parse_float(row_value(row, "Longitude"))
    mapotic_id = row_value(row, "MapoticID")
    places_id = row_value(row, "PlacesID (en)", "PlacesID (es)")
    canonical_venue_id = row_value(
        row,
        "Canonical Venue ID (en)",
        "Canonical Venue ID (es)",
    )
    city = row_value(row, "City (en)", "City (es)")
    state = row_value(row, "State (en)", "State (es)")
    address = row_value(row, "Address (en)", "Address (es)")
    poi_dedupe_key, confidence = poi_dedupe_key_for_values(
        normalized_name,
        latitude,
        longitude,
        places_id=places_id,
        mapotic_id=mapotic_id,
        canonical_venue_id=canonical_venue_id,
        city=city,
        state=state,
        address=address,
    )
    return {
        "source_export": source_export,
        "mapotic_id": mapotic_id,
        "import_id": row_value(row, "Import ID"),
        "places_id": places_id,
        "canonical_poi_id": canonical_poi_id_for_key(poi_dedupe_key),
        "canonical_name": normalized_name,
        "display_name": display_name,
        "category": parsed_category.category,
        "subcategory": parsed_category.subcategory,
        "latitude": latitude,
        "longitude": longitude,
        "geohash_or_geo_key": geo_key(latitude, longitude),
        "address": address,
        "city": city,
        "state": state,
        "zip_code": row_value(row, "Zip Code (en)", "Zip Code (es)"),
        "country": row_value(row, "Country (en)", "Country (es)"),
        "website": row_value(row, "Website (en)", "Website (es)"),
        "phone": row_value(row, "Phone"),
        "email": row_value(row, "E-mail"),
        "instagram": row_value(row, "Instagram (en)", "Instagram (es)"),
        "facebook": row_value(row, "Facebook (en)", "Facebook (es)"),
        "x_url": row_value(row, "X (en)", "X (es)"),
        "tiktok": row_value(row, "TikTok (en)", "TikTok (es)"),
        "youtube_or_video": row_value(row, "Video Tour"),
        "spotify_url": row_value(row, "Spotify URL (en)", "Spotify URL (es)"),
        "main_image_url": direct_image_url_or_none(row_value(row, "Main image URL")),
        "additional_image_urls": direct_image_url_list(row_value(row, "Image URL")),
        "description": row_value(row, "Description (en)", "Description (es)"),
        "hours_of_operation": row_value(
            row,
            "Hours of operation (en)",
            "Hours of operation (es)",
        ),
        "rating": parse_float(row_value(row, "Rating")),
        "review_count_google": parse_int(
            row_value(row, "Review Count (Google) (en)", "Review Count (Google) (es)")
        ),
        "review_count_yelp": parse_int(
            row_value(row, "Review Count (Yelp) (en)", "Review Count (Yelp) (es)")
        ),
        "certified": parse_bool(row_value(row, "Certified")),
        "carousel_selection": row_value(
            row,
            "Carousel selection",
            "Regional tips (map carousel)",
        ),
        "business_status": row_value(row, "Business Status"),
        "last_verified_at": row_value(row, "Last Veriified At", "Last Verified At"),
        "canonical_venue_id": canonical_venue_id,
        "venue_match_confidence": parse_float(row_value(row, "Venue Match Confidence")),
        "photo_quality_score": parse_float(row_value(row, "Photo Quality Score")),
        "quality_control": row_value(row, "Quality Control"),
        "raw_row_hash": stable_row_hash(row),
        "raw_row_json": dict(row),
        "poi_dedupe_key": poi_dedupe_key,
        "poi_dedupe_confidence": confidence,
    }


def minimal_poi_from_record(record: PoiRegistryRecord) -> MinimalPoi:
    return MinimalPoi(
        mapotic_id=record["mapotic_id"],
        places_id=record["places_id"],
        canonical_venue_id=record["canonical_venue_id"],
        display_name=record["display_name"],
        normalized_name=record["canonical_name"],
        category=record["category"],
        subcategory=record["subcategory"],
        latitude=record["latitude"],
        longitude=record["longitude"],
        city=record["city"],
        state=record["state"],
        website=record["website"],
        phone=record["phone"],
        address=record["address"],
        poi_dedupe_key=record["poi_dedupe_key"],
    )


def meters_between(
    first_latitude: float,
    first_longitude: float,
    second_latitude: float,
    second_longitude: float,
) -> float:
    radius_meters = 6_371_000
    lat_1 = math.radians(first_latitude)
    lat_2 = math.radians(second_latitude)
    delta_lat = math.radians(second_latitude - first_latitude)
    delta_lng = math.radians(second_longitude - first_longitude)
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat_1) * math.cos(lat_2) * math.sin(delta_lng / 2) ** 2
    )
    return radius_meters * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def address_fragment_matches(first: str | None, second: str | None) -> bool:
    first_normalized = normalize_poi_name(first)
    second_normalized = normalize_poi_name(second)
    if not first_normalized or not second_normalized:
        return False
    return (
        first_normalized in second_normalized
        or second_normalized in first_normalized
    )


def matching_contact_signal(first: MinimalPoi, second: MinimalPoi) -> bool:
    return bool(
        (first.website and second.website and first.website == second.website)
        or (first.phone and second.phone and first.phone == second.phone)
        or address_fragment_matches(first.address, second.address)
    )


def duplicate_candidates_for_pois(
    pois: Iterable[MinimalPoi],
) -> list[dict[str, object]]:
    poi_list = sorted(
        pois,
        key=lambda poi: (
            poi.normalized_name,
            poi.city or "",
            poi.state or "",
            poi.mapotic_id or "",
        ),
    )
    candidates: list[dict[str, object]] = []

    by_key: dict[str, list[MinimalPoi]] = defaultdict(list)
    by_name_city_state: dict[tuple[str, str, str], list[MinimalPoi]] = defaultdict(list)
    for poi in poi_list:
        by_key[poi.poi_dedupe_key].append(poi)
        if poi.normalized_name:
            by_name_city_state[
                (
                    poi.normalized_name,
                    (poi.city or "").casefold(),
                    (poi.state or "").casefold(),
                )
            ].append(poi)

    for key, group in sorted(by_key.items()):
        if len(group) < 2:
            continue
        candidates.append(
            duplicate_candidate_row(
                "strong",
                "same normalized name and rounded coordinates or stable ID",
                key,
                group[0],
                group[1],
                None,
            )
        )

    seen_pairs: set[tuple[str | None, str | None, str]] = set()
    for group in by_name_city_state.values():
        comparable = [
            poi
            for poi in group
            if poi.latitude is not None and poi.longitude is not None
        ]
        if len(comparable) < 2 or len(comparable) > 250:
            continue
        for index, first in enumerate(comparable):
            for second in comparable[index + 1 :]:
                first_id = first.mapotic_id or first.places_id or first.poi_dedupe_key
                second_id = (
                    second.mapotic_id or second.places_id or second.poi_dedupe_key
                )
                sorted_ids = sorted([first_id, second_id])
                pair_key = (sorted_ids[0], sorted_ids[1], "nearby")
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                distance = meters_between(
                    first.latitude or 0,
                    first.longitude or 0,
                    second.latitude or 0,
                    second.longitude or 0,
                )
                if distance <= 50:
                    candidates.append(
                        duplicate_candidate_row(
                            "medium",
                            "same normalized name within 50 meters in same city/state",
                            first.poi_dedupe_key,
                            first,
                            second,
                            distance,
                        )
                    )
                elif distance <= 100 and matching_contact_signal(first, second):
                    candidates.append(
                        duplicate_candidate_row(
                            "weak",
                            (
                                "same normalized name within 100 meters with "
                                "contact/address match"
                            ),
                            first.poi_dedupe_key,
                            first,
                            second,
                            distance,
                        )
                    )
    return candidates


def duplicate_candidate_row(
    confidence: str,
    reason: str,
    dedupe_key: str,
    first: MinimalPoi,
    second: MinimalPoi,
    distance_meters: float | None,
) -> dict[str, object]:
    return {
        "confidence": confidence,
        "reason": reason,
        "poi_dedupe_key": dedupe_key,
        "first_mapotic_id": first.mapotic_id,
        "second_mapotic_id": second.mapotic_id,
        "first_name": first.display_name,
        "second_name": second.display_name,
        "category": first.category,
        "subcategory": first.subcategory,
        "city": first.city,
        "state": first.state,
        "distance_meters": round(distance_meters, 2)
        if distance_meters is not None
        else None,
    }


def csv_rows(path: Path) -> Iterable[dict[str, str]]:
    csv.field_size_limit(sys.maxsize)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        for row in reader:
            yield {str(key): value or "" for key, value in row.items() if key}


def analyze_mapotic_export(
    export_path: Path,
    *,
    docs_dir: Path = Path("docs"),
    generated_dir: Path = Path("data/generated"),
) -> dict[str, Path]:
    generated_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)

    profile_path = generated_dir / "mapotic_export_profile.json"
    event_profile_path = generated_dir / "current_event_export_profile.json"
    registry_path = generated_dir / "current_poi_registry.jsonl"
    duplicate_path = generated_dir / "current_poi_duplicate_candidates.csv"
    report_path = docs_dir / "mapotic-export-normalization-audit.md"

    export_name = export_path.name
    counters: dict[str, Counter[str]] = {
        "category": Counter(),
        "data_source": Counter(),
        "source_record": Counter(),
    }
    subcategory_counts: dict[str, Counter[str]] = defaultdict(Counter)
    missing_required: Counter[str] = Counter()
    completeness: Counter[str] = Counter()
    pois: list[MinimalPoi] = []
    row_count = 0
    column_count = 0
    event_count = 0
    poi_count = 0

    with registry_path.open("w", encoding="utf-8") as registry_handle:
        for row in csv_rows(export_path):
            row_count += 1
            if row_count == 1:
                column_count = len(row)
            parsed_category = parse_mapotic_category(row)
            category = parsed_category.category or "Unknown"
            counters["category"][category] += 1
            if parsed_category.subcategory:
                subcategory_counts[category][parsed_category.subcategory] += 1
            data_source = row_value(row, "Data_source [developers]") or "blank"
            counters["data_source"][data_source] += 1
            source_record = row_value(row, "Source Record ID") or "blank"
            counters["source_record"][source_record] += 1
            update_completeness_counts(completeness, row, parsed_category.kind)
            update_missing_required_counts(missing_required, row, parsed_category.kind)

            if parsed_category.kind == "event":
                event_count += 1
                continue

            poi_count += 1
            record = poi_registry_record_from_row(row, source_export=export_name)
            if record is None:
                continue
            registry_handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            pois.append(minimal_poi_from_record(record))

    duplicate_rows = duplicate_candidates_for_pois(pois)
    write_duplicate_candidates(duplicate_path, duplicate_rows)

    profile = {
        "source_export": str(export_path),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "row_count": row_count,
        "column_count": column_count,
        "event_count": event_count,
        "poi_count": poi_count,
        "category_counts": dict(counters["category"].most_common()),
        "subcategory_counts_by_category": {
            category: dict(counter.most_common())
            for category, counter in sorted(subcategory_counts.items())
        },
        "data_source_counts": dict(counters["data_source"].most_common()),
        "source_record_counts": dict(counters["source_record"].most_common(25)),
        "missing_required_field_counts": dict(missing_required),
        "field_completeness_counts": dict(completeness),
        "duplicate_candidate_summary": duplicate_summary(duplicate_rows),
    }
    event_profile = {
        "source_export": str(export_path),
        "event_count": event_count,
        "ticket_link_present": completeness["event_ticket_link_present"],
        "ticket_link_missing": completeness["event_ticket_link_missing"],
        "main_image_present": completeness["event_main_image_present"],
        "main_image_missing": completeness["event_main_image_missing"],
        "date_present": completeness["event_date_present"],
        "date_missing": completeness["event_date_missing"],
        "data_source_counts": dict(counters["data_source"].most_common()),
    }
    profile_path.write_text(
        json.dumps(profile, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    event_profile_path.write_text(
        json.dumps(event_profile, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(render_audit_report(profile), encoding="utf-8")
    return {
        "report": report_path,
        "profile": profile_path,
        "registry": registry_path,
        "duplicates": duplicate_path,
        "event_profile": event_profile_path,
    }


def update_missing_required_counts(
    counter: Counter[str],
    row: Mapping[str, str],
    kind: RowKind,
) -> None:
    if row_value(row, "Name (en)", "Name (es)") is None:
        counter[f"{kind}_missing_name"] += 1
    if row_value(row, "Category") is None:
        counter[f"{kind}_missing_category"] += 1
    has_geo = row_value(row, "Latitude") is not None and row_value(row, "Longitude")
    has_address = row_value(row, "Address (en)", "Address (es)") is not None
    if kind == "poi" and not has_geo and not has_address:
        counter["poi_missing_address_or_lat_lng"] += 1
    if kind == "event":
        if row_value(row, "Date") is None:
            counter["event_missing_date"] += 1
        if row_value(row, "Tickets link (en)", "Tickets link (es)") is None:
            counter["event_missing_ticket_link"] += 1


def update_completeness_counts(
    counter: Counter[str],
    row: Mapping[str, str],
    kind: RowKind,
) -> None:
    prefix = "event" if kind == "event" else "poi"
    for field_name, headers in {
        "main_image": ("Main image URL",),
        "additional_image": ("Image URL",),
        "address": ("Address (en)", "Address (es)"),
        "website": ("Website (en)", "Website (es)"),
        "phone": ("Phone",),
        "email": ("E-mail",),
        "instagram": ("Instagram (en)", "Instagram (es)"),
        "facebook": ("Facebook (en)", "Facebook (es)"),
        "x_url": ("X (en)", "X (es)"),
        "tiktok": ("TikTok (en)", "TikTok (es)"),
        "ticket_link": ("Tickets link (en)", "Tickets link (es)"),
        "date": ("Date",),
    }.items():
        present = row_value(row, *headers) is not None
        counter[f"{prefix}_{field_name}_{'present' if present else 'missing'}"] += 1
    has_geo = row_value(row, "Latitude") is not None and row_value(row, "Longitude")
    counter[f"{prefix}_geo_{'present' if has_geo else 'missing'}"] += 1


def write_duplicate_candidates(
    path: Path,
    duplicate_rows: list[dict[str, object]],
) -> None:
    fieldnames = [
        "confidence",
        "reason",
        "poi_dedupe_key",
        "first_mapotic_id",
        "second_mapotic_id",
        "first_name",
        "second_name",
        "category",
        "subcategory",
        "city",
        "state",
        "distance_meters",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(duplicate_rows)


def duplicate_summary(duplicate_rows: list[dict[str, object]]) -> dict[str, int]:
    counter = Counter(str(row["confidence"]) for row in duplicate_rows)
    return {
        "total": len(duplicate_rows),
        "strong": counter["strong"],
        "medium": counter["medium"],
        "weak": counter["weak"],
    }


def markdown_counter_table(
    title: str,
    rows: Mapping[str, object],
    limit: int = 25,
) -> str:
    lines = [f"## {title}", "", "| Value | Count |", "| --- | ---: |"]
    for index, (value, count) in enumerate(rows.items()):
        if index >= limit:
            break
        lines.append(f"| {value or 'blank'} | {count} |")
    if not rows:
        lines.append("| none | 0 |")
    return "\n".join(lines)


def render_audit_report(profile: Mapping[str, object]) -> str:
    category_counts = profile["category_counts"]
    subcategory_counts = profile["subcategory_counts_by_category"]
    data_source_counts = profile["data_source_counts"]
    missing_counts = profile["missing_required_field_counts"]
    completeness = profile["field_completeness_counts"]
    duplicate_counts = profile["duplicate_candidate_summary"]
    assert isinstance(category_counts, Mapping)
    assert isinstance(subcategory_counts, Mapping)
    assert isinstance(data_source_counts, Mapping)
    assert isinstance(missing_counts, Mapping)
    assert isinstance(completeness, Mapping)
    assert isinstance(duplicate_counts, Mapping)

    lines = [
        "# Mapotic Export Normalization Audit",
        "",
        f"Source export: `{profile['source_export']}`",
        f"Generated at: `{profile['generated_at']}`",
        "",
        "## Summary",
        "",
        f"- Row count: {profile['row_count']}",
        f"- Column count: {profile['column_count']}",
        f"- Concert/event rows: {profile['event_count']}",
        f"- POI/place rows: {profile['poi_count']}",
        "",
        markdown_counter_table("Category Counts", category_counts),
        "",
        "## Subcategory Counts By Category",
        "",
    ]
    for category, counts in subcategory_counts.items():
        if isinstance(counts, Mapping):
            lines.append(markdown_counter_table(str(category), counts, limit=50))
            lines.append("")
    lines.extend(
        [
            markdown_counter_table("Data Source Counts", data_source_counts),
            "",
            markdown_counter_table("Missing Required Field Counts", missing_counts),
            "",
            markdown_counter_table("Field Completeness Counts", completeness),
            "",
            "## Duplicate Candidate Summary",
            "",
            f"- Total duplicate candidates: {duplicate_counts.get('total', 0)}",
            f"- Strong candidates: {duplicate_counts.get('strong', 0)}",
            f"- Medium candidates: {duplicate_counts.get('medium', 0)}",
            f"- Weak candidates: {duplicate_counts.get('weak', 0)}",
            "",
            "## Normalization Observations",
            "",
            "- `Category = Concert` is treated as event data and excluded from the "
            "POI registry.",
            "- Non-Concert rows are normalized as POIs using the main `Category` "
            "column plus the matching category-specific subcategory column.",
            "- `Longitude` and `Latitude` are exported as separate columns and must "
            "not be swapped.",
            "- `Zip Code` is preserved as text.",
            "- Image fields are kept only for direct/non-social assets; Music "
            "Roadtrip logo UI assets are excluded from POI image fields.",
            "",
            "## Field Mapping Recommendations",
            "",
            "- Use Mapotic IDs, PlacesID, and Canonical Venue ID as provenance and "
            "dedupe signals.",
            "- Use normalized name plus latitude/longitude rounded to five decimals "
            "as the primary POI dedupe key.",
            "- Keep source rows as raw JSON for auditability while storing cleaned "
            "display fields separately.",
            "",
            "## Cleanup Priorities",
            "",
            "1. Review strong and medium duplicate candidates before importing new "
            "POI candidates.",
            "2. Fill missing location data on POIs that lack both coordinates and "
            "address.",
            "3. Repair non-direct or social-media image values before image QA.",
            "4. Normalize provider/source IDs for future cross-feed dedupe.",
            "",
        ]
    )
    return "\n".join(lines)


def poi_location_values_from_record(
    record: Mapping[str, object],
) -> dict[str, object]:
    return {
        "canonical_poi_id": record["canonical_poi_id"],
        "poi_dedupe_key": record["poi_dedupe_key"],
        "poi_dedupe_confidence": record["poi_dedupe_confidence"],
        "source_type": "mapotic_export",
        "source_record_id": record.get("mapotic_id"),
        "mapotic_id": record.get("mapotic_id"),
        "places_id": record.get("places_id"),
        "canonical_venue_id": record.get("canonical_venue_id"),
        "display_name": record["display_name"],
        "normalized_name": record["canonical_name"],
        "category": record["category"],
        "subcategory": record.get("subcategory"),
        "latitude": record.get("latitude"),
        "longitude": record.get("longitude"),
        "address": record.get("address"),
        "city": record.get("city"),
        "state": record.get("state"),
        "zip_code": record.get("zip_code"),
        "country": record.get("country"),
        "website": record.get("website"),
        "phone": record.get("phone"),
        "email": record.get("email"),
        "instagram": record.get("instagram"),
        "facebook": record.get("facebook"),
        "x_url": record.get("x_url"),
        "tiktok": record.get("tiktok"),
        "spotify_url": record.get("spotify_url"),
        "main_image_url": record.get("main_image_url"),
        "additional_image_urls": record.get("additional_image_urls"),
        "description": record.get("description"),
        "hours_of_operation": record.get("hours_of_operation"),
        "certified": record.get("certified"),
        "carousel_selection": record.get("carousel_selection"),
        "business_status": record.get("business_status"),
        "rating": record.get("rating"),
        "review_count_google": record.get("review_count_google"),
        "review_count_yelp": record.get("review_count_yelp"),
        "photo_quality_score": record.get("photo_quality_score"),
        "quality_control": record.get("quality_control"),
        "last_verified_at": record.get("last_verified_at"),
        "raw_source_json": json.dumps(record, ensure_ascii=False, sort_keys=True),
    }


def apply_poi_values(location: PoiLocation, values: Mapping[str, object]) -> None:
    for key, value in values.items():
        setattr(location, key, value)


def find_existing_poi_location(
    session: Session,
    record: Mapping[str, object],
) -> PoiLocation | None:
    canonical_poi_id = str(record["canonical_poi_id"])
    poi_dedupe_key = str(record["poi_dedupe_key"])
    mapotic_id = record.get("mapotic_id")
    conditions = [
        PoiLocation.canonical_poi_id == canonical_poi_id,
        PoiLocation.poi_dedupe_key == poi_dedupe_key,
    ]
    if isinstance(mapotic_id, str) and mapotic_id:
        conditions.append(PoiLocation.mapotic_id == mapotic_id)
    return session.scalar(select(PoiLocation).where(or_(*conditions)))


def import_poi_registry_jsonl(
    session: Session,
    registry_path: Path,
) -> ImportPoiRegistrySummary:
    created = 0
    updated = 0
    duplicate = 0
    skipped = 0
    seen_keys: set[str] = set()
    with registry_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            if (
                not isinstance(record, dict)
                or record.get("category") == CONCERT_CATEGORY
            ):
                skipped += 1
                continue
            key = str(record.get("poi_dedupe_key") or "")
            if not key:
                skipped += 1
                continue
            if key in seen_keys:
                duplicate += 1
                continue
            values = poi_location_values_from_record(record)
            existing = find_existing_poi_location(session, record)
            if existing is None:
                location = PoiLocation(**values)
                session.add(location)
                created += 1
            else:
                apply_poi_values(existing, values)
                existing.updated_at = utc_now()
                updated += 1
            seen_keys.add(key)
    session.commit()
    return ImportPoiRegistrySummary(
        created=created,
        updated=updated,
        duplicate=duplicate,
        skipped=skipped,
    )


def list_poi_locations(session: Session, limit: int = 250) -> list[PoiLocation]:
    return list(
        session.scalars(
            select(PoiLocation).order_by(PoiLocation.display_name).limit(limit)
        )
    )


def get_poi_location(session: Session, poi_id: int) -> PoiLocation | None:
    return session.get(PoiLocation, poi_id)


def poi_duplicate_groups(session: Session) -> list[tuple[str, int]]:
    rows = session.execute(
        select(PoiLocation.poi_dedupe_key).order_by(PoiLocation.poi_dedupe_key)
    ).all()
    counts = Counter(str(row[0]) for row in rows)
    return sorted(
        [(key, count) for key, count in counts.items() if count > 1],
        key=lambda item: (-item[1], item[0]),
    )
