from __future__ import annotations

import argparse
from pathlib import Path

from app.services.poi_registry_service import analyze_mapotic_export


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze a Mapotic export and generate POI registry artifacts.",
    )
    parser.add_argument(
        "export_path",
        type=Path,
        help="Path to the semicolon-delimited Mapotic export CSV.",
    )
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=Path("docs"),
        help="Directory for markdown audit output.",
    )
    parser.add_argument(
        "--generated-dir",
        type=Path,
        default=Path("data/generated"),
        help="Directory for generated JSON/CSV artifacts.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    outputs = analyze_mapotic_export(
        args.export_path,
        docs_dir=args.docs_dir,
        generated_dir=args.generated_dir,
    )
    for label, path in outputs.items():
        print(f"{label}: {path}")


if __name__ == "__main__":
    main()
