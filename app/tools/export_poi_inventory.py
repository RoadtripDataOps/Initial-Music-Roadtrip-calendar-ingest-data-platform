from __future__ import annotations

import argparse
from pathlib import Path
from typing import Literal

from app.core.config import get_settings
from app.db.database import create_all, make_engine, make_session_factory
from app.services.poi_inventory_export_service import (
    DEFAULT_POI_INVENTORY_OUTPUT_DIR,
    export_poi_inventory_bundle,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export current POI inventory snapshots and dedupe index.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_POI_INVENTORY_OUTPUT_DIR,
        help="Directory for current and archived POI inventory artifacts.",
    )
    archive_group = parser.add_mutually_exclusive_group()
    archive_group.add_argument(
        "--archive",
        action="store_true",
        default=True,
        help="Write monthly archive copies in addition to current files.",
    )
    archive_group.add_argument(
        "--no-archive",
        action="store_false",
        dest="archive",
        help="Only write current files.",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dedupe-only",
        action="store_true",
        help="Export only current_poi_dedupe_index.json plus manifest.",
    )
    mode_group.add_argument(
        "--inventory-only",
        action="store_true",
        help="Export only current_poi_inventory.jsonl.gz plus manifest.",
    )
    return parser.parse_args(argv)


def _mode(args: argparse.Namespace) -> Literal["full", "dedupe_only", "inventory_only"]:
    if args.dedupe_only:
        return "dedupe_only"
    if args.inventory_only:
        return "inventory_only"
    return "full"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = get_settings()
    engine = make_engine(settings.database_url)
    create_all(engine)
    session_factory = make_session_factory(engine)
    with session_factory() as session:
        exports = export_poi_inventory_bundle(
            session,
            args.output_dir,
            archive=bool(args.archive),
            generated_by="cli",
            mode=_mode(args),
        )
    for name, export in exports.items():
        print(
            f"{name}: status={export.status} records={export.record_count} "
            f"duplicates={export.duplicate_key_count} path={export.output_path}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
