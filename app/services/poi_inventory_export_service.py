from __future__ import annotations

import gzip
import hashlib
import json
import shutil
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    PoiInventoryExport,
    PoiInventoryExportStatus,
    PoiInventoryExportType,
    PoiLocation,
    utc_now,
)
from app.services.poi_registry_service import (
    clean_text,
    is_logo_asset_url,
    is_social_or_video_url,
    normalize_poi_name,
)

DEFAULT_POI_INVENTORY_OUTPUT_DIR = Path("data/generated/poi_inventory")
CURRENT_INVENTORY_FILENAME = "current_poi_inventory.jsonl.gz"
CURRENT_DEDUPE_INDEX_FILENAME = "current_poi_dedupe_index.json"
CURRENT_MANIFEST_FILENAME = "current_poi_inventory_manifest.json"
STRATEGY_VERSION = "poi-dedupe-v1"
CONCERT_CATEGORY = "Concert"

POI_DEDUPE_STRATEGIES = (
    "places_id",
    "mapotic_id",
    "canonical_poi_id",
    "name_geo_5",
    "name_geo_4",
    "website_city_state",
    "phone",
    "name_city_state",
)

LOWER_CONFIDENCE_STRATEGIES = {"name_city_state"}
MEDIUM_CONFIDENCE_STRATEGIES = {"website_city_state", "phone", "name_geo_4"}


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _safe_text(value: object | None) -> str | None:
    cleaned = clean_text(value)
    return cleaned if cleaned else None


def _website_domain(value: str | None) -> str | None:
    url = _safe_text(value)
    if not url:
        return None
    parsed = urlsplit(url if "://" in url else f"https://{url}")
    host = (parsed.netloc or parsed.path.split("/", 1)[0]).casefold()
    if host.startswith("www."):
        host = host[4:]
    return host or None


def _rounded_coordinate(value: float | None, digits: int) -> str | None:
    if value is None:
        return None
    return f"{value:.{digits}f}"


def _rounded_coordinate_value(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 5)


def _normalized_location_part(value: str | None) -> str:
    return (_safe_text(value) or "").casefold()


def _normalized_phone(value: str | None) -> str | None:
    phone = _safe_text(value)
    if not phone:
        return None
    digits = "".join(character for character in phone if character.isdigit())
    return digits or phone.casefold()


def _image_url_and_warnings(value: str | None) -> tuple[str | None, list[str]]:
    image_url = _safe_text(value)
    if not image_url:
        return None, []
    if is_logo_asset_url(image_url):
        return None, ["main_image_url_logo_asset_suppressed"]
    if is_social_or_video_url(image_url):
        return None, ["main_image_url_social_or_video_suppressed"]
    return image_url, []


def _raw_row_hash(poi_location: PoiLocation) -> str | None:
    if not poi_location.raw_source_json or poi_location.raw_source_json == "{}":
        return None
    try:
        parsed = json.loads(poi_location.raw_source_json)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        raw_hash = parsed.get("raw_row_hash")
        if isinstance(raw_hash, str) and raw_hash.strip():
            return raw_hash.strip()
    return hashlib.sha256(poi_location.raw_source_json.encode("utf-8")).hexdigest()


def _poi_ref(poi_location: PoiLocation) -> dict[str, object]:
    return {
        "poi_id": poi_location.id,
        "canonical_poi_id": poi_location.canonical_poi_id,
        "display_name": poi_location.display_name,
        "category": poi_location.category,
        "subcategory": poi_location.subcategory,
        "city": poi_location.city,
        "state": poi_location.state,
        "latitude": poi_location.latitude,
        "longitude": poi_location.longitude,
        "mapotic_id": poi_location.mapotic_id,
        "places_id": poi_location.places_id,
    }


def poi_dedupe_index_keys_for_values(
    *,
    display_name: str | None,
    normalized_name: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    places_id: str | None = None,
    mapotic_id: str | None = None,
    canonical_poi_id: str | None = None,
    website: str | None = None,
    phone: str | None = None,
    city: str | None = None,
    state: str | None = None,
) -> dict[str, str]:
    """Build deterministic POI dedupe keys for database or snapshot matching."""

    name = _safe_text(normalized_name) or normalize_poi_name(display_name)
    keys: dict[str, str] = {}
    if places_id := _safe_text(places_id):
        keys["places_id"] = places_id.casefold()
    if mapotic_id := _safe_text(mapotic_id):
        keys["mapotic_id"] = mapotic_id.casefold()
    if canonical_poi_id := _safe_text(canonical_poi_id):
        keys["canonical_poi_id"] = canonical_poi_id.casefold()
    if name and latitude is not None and longitude is not None:
        lat_5 = _rounded_coordinate(latitude, 5)
        lng_5 = _rounded_coordinate(longitude, 5)
        lat_4 = _rounded_coordinate(latitude, 4)
        lng_4 = _rounded_coordinate(longitude, 4)
        if lat_5 and lng_5:
            keys["name_geo_5"] = f"{name}|lat:{lat_5}|lng:{lng_5}"
        if lat_4 and lng_4:
            keys["name_geo_4"] = f"{name}|lat:{lat_4}|lng:{lng_4}"
    domain = _website_domain(website)
    normalized_city = _normalized_location_part(city)
    normalized_state = _normalized_location_part(state)
    if domain and normalized_city and normalized_state:
        keys["website_city_state"] = (
            f"{domain}|city:{normalized_city}|state:{normalized_state}"
        )
    if normalized_phone := _normalized_phone(phone):
        keys["phone"] = normalized_phone
    if name and normalized_city and normalized_state:
        keys["name_city_state"] = (
            f"{name}|city:{normalized_city}|state:{normalized_state}"
        )
    return keys


def poi_dedupe_index_keys_for_location(
    poi_location: PoiLocation,
) -> dict[str, str]:
    return poi_dedupe_index_keys_for_values(
        display_name=poi_location.display_name,
        normalized_name=poi_location.normalized_name,
        latitude=poi_location.latitude,
        longitude=poi_location.longitude,
        places_id=poi_location.places_id,
        mapotic_id=poi_location.mapotic_id,
        canonical_poi_id=poi_location.canonical_poi_id,
        website=poi_location.website,
        phone=poi_location.phone,
        city=poi_location.city,
        state=poi_location.state,
    )


def build_poi_inventory_record(poi_location: PoiLocation) -> dict[str, object]:
    """Return one app-safe POI inventory snapshot record."""

    main_image_url, image_warnings = _image_url_and_warnings(
        poi_location.main_image_url
    )
    return {
        "poi_id": poi_location.id,
        "canonical_poi_id": poi_location.canonical_poi_id,
        "poi_dedupe_key": poi_location.poi_dedupe_key,
        "source_type": poi_location.source_type,
        "source_record_id": poi_location.source_record_id,
        "mapotic_id": poi_location.mapotic_id,
        "places_id": poi_location.places_id,
        "canonical_venue_id": poi_location.canonical_venue_id,
        "display_name": poi_location.display_name,
        "normalized_name": poi_location.normalized_name,
        "category": poi_location.category,
        "subcategory": poi_location.subcategory,
        "latitude": poi_location.latitude,
        "longitude": poi_location.longitude,
        "rounded_latitude": _rounded_coordinate_value(poi_location.latitude),
        "rounded_longitude": _rounded_coordinate_value(poi_location.longitude),
        "address": poi_location.address,
        "city": poi_location.city,
        "state": poi_location.state,
        "zip_code": str(poi_location.zip_code) if poi_location.zip_code else None,
        "country": poi_location.country,
        "website": poi_location.website,
        "website_domain": _website_domain(poi_location.website),
        "phone": poi_location.phone,
        "email": poi_location.email,
        "instagram": poi_location.instagram,
        "facebook": poi_location.facebook,
        "x_url": poi_location.x_url,
        "tiktok": poi_location.tiktok,
        "spotify_url": poi_location.spotify_url,
        "main_image_url": main_image_url,
        "image_warnings": image_warnings,
        "description": poi_location.description,
        "certified": poi_location.certified,
        "carousel_selection": poi_location.carousel_selection,
        "business_status": poi_location.business_status,
        "rating": poi_location.rating,
        "review_count_google": poi_location.review_count_google,
        "review_count_yelp": poi_location.review_count_yelp,
        "photo_quality_score": poi_location.photo_quality_score,
        "quality_control": poi_location.quality_control,
        "publish_status": poi_location.publish_status,
        "publish_ready_score": poi_location.publish_ready_score,
        "updated_at": _isoformat(poi_location.updated_at),
        "raw_row_hash": _raw_row_hash(poi_location),
    }


def _list_inventory_locations(session: Session) -> list[PoiLocation]:
    statement = (
        select(PoiLocation)
        .where(func.lower(PoiLocation.category) != CONCERT_CATEGORY.casefold())
        .order_by(PoiLocation.display_name.asc(), PoiLocation.id.asc())
    )
    return list(session.scalars(statement).all())


def _strategy_confidence(strategy: str) -> str:
    if strategy in LOWER_CONFIDENCE_STRATEGIES:
        return "weak"
    if strategy in MEDIUM_CONFIDENCE_STRATEGIES:
        return "medium"
    return "strong"


def build_poi_dedupe_index(
    poi_locations: Iterable[PoiLocation],
) -> dict[str, object]:
    """Build a collision-preserving POI dedupe index from existing locations."""

    key_maps: dict[str, dict[str, list[dict[str, object]]]] = {
        strategy: {} for strategy in POI_DEDUPE_STRATEGIES
    }
    record_count = 0
    for location in poi_locations:
        if location.category.casefold() == CONCERT_CATEGORY.casefold():
            continue
        record_count += 1
        ref = _poi_ref(location)
        keys = poi_dedupe_index_keys_for_location(location)
        for strategy, key in keys.items():
            key_maps[strategy].setdefault(key, []).append(ref)

    duplicates: list[dict[str, object]] = []
    for strategy in POI_DEDUPE_STRATEGIES:
        for key, refs in sorted(key_maps[strategy].items()):
            if len(refs) < 2:
                continue
            duplicates.append(
                {
                    "strategy": strategy,
                    "confidence": _strategy_confidence(strategy),
                    "key": key,
                    "count": len(refs),
                    "poi_ids": [ref["poi_id"] for ref in refs],
                    "canonical_poi_ids": [
                        ref["canonical_poi_id"] for ref in refs
                    ],
                    "records": refs,
                }
            )

    populated_counts = {
        strategy: len(mapping) for strategy, mapping in key_maps.items()
    }
    duplicate_counts = {
        strategy: sum(1 for refs in key_maps[strategy].values() if len(refs) > 1)
        for strategy in POI_DEDUPE_STRATEGIES
    }
    return {
        "generated_at": utc_now().isoformat(),
        "record_count": record_count,
        "strategy_version": STRATEGY_VERSION,
        "keys": key_maps,
        "duplicates": duplicates,
        "stats": {
            "strategy_key_counts": populated_counts,
            "strategy_duplicate_key_counts": duplicate_counts,
            "duplicate_key_count": len(duplicates),
        },
    }


def _ensure_output_dirs(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_dir = output_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    return archive_dir


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_dumps(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def _image_warning_count(records: Iterable[Mapping[str, object]]) -> int:
    warning_count = 0
    for record in records:
        warnings = record.get("image_warnings")
        if isinstance(warnings, list):
            warning_count += len(warnings)
    return warning_count


def _index_stats(index: Mapping[str, object]) -> Mapping[str, object]:
    stats = index.get("stats")
    return stats if isinstance(stats, Mapping) else {}


def _int_value(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _create_pending_export(
    session: Session,
    export_type: str,
    *,
    generated_at: datetime,
    generated_by: str | None,
) -> PoiInventoryExport:
    export = PoiInventoryExport(
        export_key=f"{export_type}:{generated_at:%Y%m%d%H%M%S%f}",
        export_type=export_type,
        status=PoiInventoryExportStatus.pending.value,
        generated_at=generated_at,
        generated_by=generated_by,
    )
    session.add(export)
    session.commit()
    session.refresh(export)
    return export


def _complete_export(
    session: Session,
    export: PoiInventoryExport,
    *,
    output_path: Path,
    record_count: int,
    duplicate_key_count: int,
    metadata: Mapping[str, object],
) -> PoiInventoryExport:
    export.status = PoiInventoryExportStatus.success.value
    export.output_path = str(output_path)
    export.output_size_bytes = output_path.stat().st_size
    export.sha256_hash = _sha256_file(output_path)
    export.record_count = record_count
    export.duplicate_key_count = duplicate_key_count
    export.metadata_json = _json_dumps(dict(metadata))
    export.error_message = None
    session.add(export)
    session.commit()
    session.refresh(export)
    return export


def _fail_export(
    session: Session,
    export: PoiInventoryExport,
    error: Exception,
) -> PoiInventoryExport:
    export.status = PoiInventoryExportStatus.failure.value
    export.error_message = str(error)
    session.add(export)
    session.commit()
    session.refresh(export)
    return export


def export_current_poi_inventory(
    session: Session,
    output_dir: str | Path = DEFAULT_POI_INVENTORY_OUTPUT_DIR,
    *,
    archive: bool = True,
    generated_by: str | None = None,
) -> PoiInventoryExport:
    generated_at = utc_now()
    output_root = Path(output_dir)
    archive_dir = _ensure_output_dirs(output_root)
    export = _create_pending_export(
        session,
        PoiInventoryExportType.full_inventory_jsonl.value,
        generated_at=generated_at,
        generated_by=generated_by,
    )
    current_path = output_root / CURRENT_INVENTORY_FILENAME
    archive_file = archive_dir / f"poi_inventory_{generated_at:%Y_%m}.jsonl.gz"
    try:
        records = [
            build_poi_inventory_record(location)
            for location in _list_inventory_locations(session)
        ]
        with gzip.open(current_path, "wt", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        if archive:
            shutil.copyfile(current_path, archive_file)
        return _complete_export(
            session,
            export,
            output_path=current_path,
            record_count=len(records),
            duplicate_key_count=0,
            metadata={
                "archive_path": str(archive_file) if archive else None,
                "strategy_version": STRATEGY_VERSION,
                "image_warning_count": _image_warning_count(records),
            },
        )
    except Exception as exc:
        _fail_export(session, export, exc)
        raise


def export_current_poi_dedupe_index(
    session: Session,
    output_dir: str | Path = DEFAULT_POI_INVENTORY_OUTPUT_DIR,
    *,
    archive: bool = True,
    generated_by: str | None = None,
) -> PoiInventoryExport:
    generated_at = utc_now()
    output_root = Path(output_dir)
    archive_dir = _ensure_output_dirs(output_root)
    export = _create_pending_export(
        session,
        PoiInventoryExportType.dedupe_index_json.value,
        generated_at=generated_at,
        generated_by=generated_by,
    )
    current_path = output_root / CURRENT_DEDUPE_INDEX_FILENAME
    archive_file = archive_dir / f"poi_dedupe_index_{generated_at:%Y_%m}.json"
    try:
        index = build_poi_dedupe_index(_list_inventory_locations(session))
        current_path.write_text(
            json.dumps(index, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if archive:
            shutil.copyfile(current_path, archive_file)
        stats = _index_stats(index)
        duplicate_key_count = _int_value(stats.get("duplicate_key_count"))
        return _complete_export(
            session,
            export,
            output_path=current_path,
            record_count=_int_value(index.get("record_count")),
            duplicate_key_count=duplicate_key_count,
            metadata={
                "archive_path": str(archive_file) if archive else None,
                "strategy_version": STRATEGY_VERSION,
                "strategy_key_counts": stats.get("strategy_key_counts", {}),
            },
        )
    except Exception as exc:
        _fail_export(session, export, exc)
        raise


def _export_summary(export: PoiInventoryExport | None) -> dict[str, object] | None:
    if export is None:
        return None
    return {
        "id": export.id,
        "export_key": export.export_key,
        "export_type": export.export_type,
        "status": export.status,
        "record_count": export.record_count,
        "duplicate_key_count": export.duplicate_key_count,
        "output_path": export.output_path,
        "output_size_bytes": export.output_size_bytes,
        "sha256_hash": export.sha256_hash,
        "generated_at": _isoformat(export.generated_at),
        "generated_by": export.generated_by,
        "metadata": export.metadata_payload,
    }


def export_poi_inventory_manifest(
    session: Session,
    output_dir: str | Path = DEFAULT_POI_INVENTORY_OUTPUT_DIR,
    *,
    archive: bool = True,
    generated_by: str | None = None,
) -> PoiInventoryExport:
    generated_at = utc_now()
    output_root = Path(output_dir)
    archive_dir = _ensure_output_dirs(output_root)
    export = _create_pending_export(
        session,
        PoiInventoryExportType.manifest.value,
        generated_at=generated_at,
        generated_by=generated_by,
    )
    current_path = output_root / CURRENT_MANIFEST_FILENAME
    archive_file = archive_dir / f"poi_inventory_manifest_{generated_at:%Y_%m}.json"
    try:
        latest_inventory = get_latest_poi_inventory_export(session)
        latest_dedupe = get_latest_poi_dedupe_index(session)
        manifest = {
            "generated_at": generated_at.isoformat(),
            "strategy_version": STRATEGY_VERSION,
            "database_is_source_of_truth": True,
            "snapshot_files_are_export_artifacts": True,
            "concert_rows_excluded": True,
            "inventory_export": _export_summary(latest_inventory),
            "dedupe_index_export": _export_summary(latest_dedupe),
        }
        current_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if archive:
            shutil.copyfile(current_path, archive_file)
        return _complete_export(
            session,
            export,
            output_path=current_path,
            record_count=(
                latest_inventory.record_count if latest_inventory is not None else 0
            ),
            duplicate_key_count=(
                latest_dedupe.duplicate_key_count if latest_dedupe is not None else 0
            ),
            metadata={
                "archive_path": str(archive_file) if archive else None,
                "strategy_version": STRATEGY_VERSION,
            },
        )
    except Exception as exc:
        _fail_export(session, export, exc)
        raise


def export_poi_inventory_bundle(
    session: Session,
    output_dir: str | Path = DEFAULT_POI_INVENTORY_OUTPUT_DIR,
    *,
    archive: bool = True,
    generated_by: str | None = None,
    mode: Literal["full", "dedupe_only", "inventory_only"] = "full",
) -> dict[str, PoiInventoryExport]:
    exports: dict[str, PoiInventoryExport] = {}
    if mode in {"full", "inventory_only"}:
        exports["inventory"] = export_current_poi_inventory(
            session,
            output_dir,
            archive=archive,
            generated_by=generated_by,
        )
    if mode in {"full", "dedupe_only"}:
        exports["dedupe_index"] = export_current_poi_dedupe_index(
            session,
            output_dir,
            archive=archive,
            generated_by=generated_by,
        )
    exports["manifest"] = export_poi_inventory_manifest(
        session,
        output_dir,
        archive=archive,
        generated_by=generated_by,
    )
    return exports


def get_latest_poi_inventory_export(
    session: Session,
) -> PoiInventoryExport | None:
    return session.scalar(
        select(PoiInventoryExport)
        .where(
            PoiInventoryExport.export_type
            == PoiInventoryExportType.full_inventory_jsonl.value,
            PoiInventoryExport.status == PoiInventoryExportStatus.success.value,
        )
        .order_by(PoiInventoryExport.generated_at.desc(), PoiInventoryExport.id.desc())
    )


def get_latest_poi_dedupe_index(
    session: Session,
) -> PoiInventoryExport | None:
    return session.scalar(
        select(PoiInventoryExport)
        .where(
            PoiInventoryExport.export_type
            == PoiInventoryExportType.dedupe_index_json.value,
            PoiInventoryExport.status == PoiInventoryExportStatus.success.value,
        )
        .order_by(PoiInventoryExport.generated_at.desc(), PoiInventoryExport.id.desc())
    )


def get_latest_poi_inventory_manifest(
    session: Session,
) -> PoiInventoryExport | None:
    return session.scalar(
        select(PoiInventoryExport)
        .where(
            PoiInventoryExport.export_type == PoiInventoryExportType.manifest.value,
            PoiInventoryExport.status == PoiInventoryExportStatus.success.value,
        )
        .order_by(PoiInventoryExport.generated_at.desc(), PoiInventoryExport.id.desc())
    )


def get_poi_inventory_export(
    session: Session,
    export_id: int,
) -> PoiInventoryExport | None:
    return session.get(PoiInventoryExport, export_id)


def list_poi_inventory_exports(
    session: Session,
    *,
    limit: int = 100,
) -> list[PoiInventoryExport]:
    return list(
        session.scalars(
            select(PoiInventoryExport)
            .order_by(
                PoiInventoryExport.generated_at.desc(),
                PoiInventoryExport.id.desc(),
            )
            .limit(limit)
        ).all()
    )
