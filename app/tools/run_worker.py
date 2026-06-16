from __future__ import annotations

import argparse
import time
from collections.abc import Sequence

from app.core.config import get_settings
from app.db.database import create_all, make_engine, make_session_factory
from app.services.background_job_service import (
    DEFAULT_QUEUE_NAME,
    default_worker_id,
    process_next_job,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local DB-backed background jobs.")
    parser.add_argument("--once", action="store_true", help="Process at most one job.")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process at most N jobs.",
    )
    parser.add_argument(
        "--queue",
        default=DEFAULT_QUEUE_NAME,
        help="Queue name to claim.",
    )
    parser.add_argument("--worker-id", default=default_worker_id(), help="Worker name.")
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Keep polling until interrupted. Not enabled by default.",
    )
    parser.add_argument("--sleep-seconds", type=float, default=2.0)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    settings = get_settings()
    engine = make_engine(settings.database_url)
    create_all(engine)
    session_factory = make_session_factory(engine)
    processed = 0
    effective_limit = args.limit
    if args.once or (not args.loop and effective_limit is None):
        effective_limit = 1

    while True:
        with session_factory() as session:
            job = process_next_job(
                session,
                settings,
                worker_id=str(args.worker_id),
                queue_name=str(args.queue),
            )
        if job is None:
            if args.loop:
                time.sleep(max(0.1, float(args.sleep_seconds)))
                continue
            break
        processed += 1
        print(f"Processed job #{job.id}: {job.status}")
        if effective_limit is not None and processed >= effective_limit:
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
