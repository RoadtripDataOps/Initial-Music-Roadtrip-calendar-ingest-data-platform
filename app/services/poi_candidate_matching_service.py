from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import PoiLocation
from app.services.poi_inventory_export_service import (
    CONCERT_CATEGORY,
    POI_DEDUPE_STRATEGIES,
    get_latest_poi_dedupe_index,
    poi_dedupe_index_keys_for_location,
    poi_dedupe_index_keys_for_values,
)
from app.services.poi_registry_service import normalize_poi_name


@dataclass(frozen=True)
class PoiCandidateInput:
    display_name: str
    latitude: float | None = None
    longitude: float | None = None
    places_id: str | None = None
    mapotic_id: str | None = None
    canonical_poi_id: str | None = None
    website: str | None = None
    phone: str | None = None
    city: str | None = None
    state: str | None = None


@dataclass(frozen=True)
class PoiCandidateMatch:
    match_source: Literal["database", "dedupe_snapshot", "none"]
    match_strategy: str | None
    confidence: Literal["strong", "medium", "weak", "none"]
    poi_id: int | None = None
    canonical_poi_id: str | None = None
    snapshot_records: tuple[dict[str, object], ...] = ()


def _candidate_keys(candidate: PoiCandidateInput) -> dict[str, str]:
    return poi_dedupe_index_keys_for_values(
        display_name=candidate.display_name,
        normalized_name=normalize_poi_name(candidate.display_name),
        latitude=candidate.latitude,
        longitude=candidate.longitude,
        places_id=candidate.places_id,
        mapotic_id=candidate.mapotic_id,
        canonical_poi_id=candidate.canonical_poi_id,
        website=candidate.website,
        phone=candidate.phone,
        city=candidate.city,
        state=candidate.state,
    )


def _strategy_confidence(strategy: str) -> Literal["strong", "medium", "weak"]:
    if strategy == "name_city_state":
        return "weak"
    if strategy in {"name_geo_4", "phone"}:
        return "medium"
    return "strong"


def _database_candidates(session: Session) -> list[PoiLocation]:
    return list(
        session.scalars(
            select(PoiLocation)
            .where(func.lower(PoiLocation.category) != CONCERT_CATEGORY.casefold())
            .order_by(PoiLocation.id.asc())
        ).all()
    )


def _match_database(
    session: Session,
    keys: dict[str, str],
) -> PoiCandidateMatch | None:
    for strategy in POI_DEDUPE_STRATEGIES:
        candidate_key = keys.get(strategy)
        if not candidate_key:
            continue
        for poi in _database_candidates(session):
            if poi_dedupe_index_keys_for_location(poi).get(strategy) == candidate_key:
                return PoiCandidateMatch(
                    match_source="database",
                    match_strategy=strategy,
                    confidence=_strategy_confidence(strategy),
                    poi_id=poi.id,
                    canonical_poi_id=poi.canonical_poi_id,
                )
    return None


def _load_latest_snapshot_index(session: Session) -> dict[str, object] | None:
    export = get_latest_poi_dedupe_index(session)
    if export is None or not export.output_path:
        return None
    path = Path(export.output_path)
    if not path.exists():
        return None
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _match_snapshot(
    index: dict[str, object] | None,
    keys: dict[str, str],
) -> PoiCandidateMatch | None:
    if not index:
        return None
    index_keys = index.get("keys")
    if not isinstance(index_keys, dict):
        return None
    for strategy in POI_DEDUPE_STRATEGIES:
        candidate_key = keys.get(strategy)
        if not candidate_key:
            continue
        strategy_keys = index_keys.get(strategy)
        if not isinstance(strategy_keys, dict):
            continue
        records = strategy_keys.get(candidate_key)
        if not isinstance(records, list) or not records:
            continue
        typed_records = tuple(
            record for record in records if isinstance(record, dict)
        )
        first = typed_records[0] if typed_records else {}
        poi_id = first.get("poi_id")
        canonical_poi_id = first.get("canonical_poi_id")
        return PoiCandidateMatch(
            match_source="dedupe_snapshot",
            match_strategy=strategy,
            confidence=_strategy_confidence(strategy),
            poi_id=int(poi_id) if isinstance(poi_id, int) else None,
            canonical_poi_id=(
                str(canonical_poi_id) if canonical_poi_id is not None else None
            ),
            snapshot_records=typed_records,
        )
    return None


def match_poi_candidate(
    session: Session,
    candidate: PoiCandidateInput,
) -> PoiCandidateMatch:
    """Match incoming POI candidates against DB first, then latest snapshot."""

    keys = _candidate_keys(candidate)
    database_match = _match_database(session, keys)
    if database_match is not None:
        return database_match
    snapshot_match = _match_snapshot(_load_latest_snapshot_index(session), keys)
    if snapshot_match is not None:
        return snapshot_match
    return PoiCandidateMatch(
        match_source="none",
        match_strategy=None,
        confidence="none",
    )
