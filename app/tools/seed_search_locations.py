from __future__ import annotations

import argparse
from collections.abc import Sequence

from app.core.config import get_settings
from app.db.database import create_all, make_engine, make_session_factory
from app.services.region_service import (
    assign_inferred_regions,
    seed_search_locations_from_pois,
    seed_search_locations_from_regions,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed internal search locations from local regions and POIs.",
    )
    parser.add_argument(
        "--skip-pois",
        action="store_true",
        help="Do not seed POI-derived search locations.",
    )
    parser.add_argument(
        "--skip-regions",
        action="store_true",
        help="Do not seed region-derived search locations.",
    )
    parser.add_argument(
        "--assign-regions",
        action="store_true",
        help="Infer region links for unassigned POIs, events, and sources first.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    settings = get_settings()
    engine = make_engine(settings.database_url)
    create_all(engine)
    session_factory = make_session_factory(engine)
    with session_factory() as session:
        if args.assign_regions:
            assigned = assign_inferred_regions(session)
        else:
            assigned = {"pois": 0, "events": 0, "sources": 0}
        poi_counts = (
            {"created": 0, "updated": 0}
            if args.skip_pois
            else seed_search_locations_from_pois(session)
        )
        region_counts = (
            {"created": 0, "updated": 0}
            if args.skip_regions
            else seed_search_locations_from_regions(session)
        )
    print(
        "Assigned regions: "
        f"{assigned['pois']} POIs, {assigned['events']} events, "
        f"{assigned['sources']} sources"
    )
    print(
        "Seeded POI locations: "
        f"{poi_counts['created']} created, {poi_counts['updated']} updated"
    )
    print(
        "Seeded region locations: "
        f"{region_counts['created']} created, {region_counts['updated']} updated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
