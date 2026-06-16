from __future__ import annotations

import argparse
from pathlib import Path

from app.core.config import get_settings
from app.db.database import create_all, make_engine, make_session_factory
from app.services.poi_registry_service import import_poi_registry_jsonl


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import generated POI registry JSONL into poi_locations.",
    )
    parser.add_argument(
        "registry_path",
        type=Path,
        help="Path to data/generated/current_poi_registry.jsonl.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = get_settings()
    engine = make_engine(settings.database_url)
    create_all(engine)
    session_factory = make_session_factory(engine)
    with session_factory() as session:
        summary = import_poi_registry_jsonl(session, args.registry_path)
    print(
        f"created={summary.created} updated={summary.updated} "
        f"duplicate={summary.duplicate} skipped={summary.skipped}"
    )


if __name__ == "__main__":
    main()
