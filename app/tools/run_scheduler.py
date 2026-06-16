from __future__ import annotations

import argparse
from collections.abc import Sequence

from app.core.config import get_settings
from app.db.database import create_all, make_engine, make_session_factory
from app.services.background_job_service import enqueue_due_scheduled_tasks


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enqueue due local scheduled tasks.")
    parser.add_argument("--once", action="store_true", help="Run one scheduler pass.")
    parser.add_argument("--dry-run", action="store_true", help="Do not enqueue jobs.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    settings = get_settings()
    engine = make_engine(settings.database_url)
    create_all(engine)
    session_factory = make_session_factory(engine)
    with session_factory() as session:
        result = enqueue_due_scheduled_tasks(session, dry_run=bool(args.dry_run))
    action = "Would enqueue" if result.dry_run else "Enqueued"
    print(
        f"{action} {len(result.enqueued_job_ids)} "
        f"of {result.due_task_count} due tasks",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
