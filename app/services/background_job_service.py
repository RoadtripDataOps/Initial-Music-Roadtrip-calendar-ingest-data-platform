from __future__ import annotations

import json
import re
import socket
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Literal, cast
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import (
    BackgroundJob,
    BackgroundJobStatus,
    BackgroundJobType,
    ScheduledTask,
    ScheduledTaskScheduleType,
    ScheduledTaskType,
    utc_now,
)
from app.services.api_feed_service import CITYSPARK_PROVIDER_KEY
from app.services.crawl_service import Fetcher, fetch_calendar_url

REDACTED = "[REDACTED]"
DEFAULT_QUEUE_NAME = "default"
SENSITIVE_KEY_PARTS = (
    "apikey",
    "api_key",
    "token",
    "secret",
    "password",
    "authorization",
    "x-api-key",
)
SENSITIVE_QUERY_KEYS = {
    "apikey",
    "api_key",
    "token",
    "secret",
    "password",
    "authorization",
    "x-api-key",
    "access_token",
    "refresh_token",
    "client_secret",
}
DEFAULT_SCHEDULED_TASKS = (
    {
        "task_key": "crawl_due_sources",
        "task_type": ScheduledTaskType.crawl_due_sources.value,
        "schedule_type": ScheduledTaskScheduleType.manual.value,
        "enabled": False,
        "payload": {},
    },
    {
        "task_key": "app_feed_export_full",
        "task_type": ScheduledTaskType.app_feed_export.value,
        "schedule_type": ScheduledTaskScheduleType.manual.value,
        "enabled": False,
        "payload": {"export_type": "full"},
    },
    {
        "task_key": "rebuild_app_search_index",
        "task_type": ScheduledTaskType.rebuild_app_search_index.value,
        "schedule_type": ScheduledTaskScheduleType.manual.value,
        "enabled": False,
        "payload": {"job_type": BackgroundJobType.rebuild_app_search_index.value},
    },
    {
        "task_key": "monthly_poi_inventory_snapshot",
        "task_type": ScheduledTaskType.monthly_poi_inventory_snapshot.value,
        "schedule_type": ScheduledTaskScheduleType.monthly.value,
        "enabled": False,
        "payload": {
            "job_type": BackgroundJobType.poi_inventory_snapshot_export.value,
            "output_dir": "data/generated/poi_inventory",
            "archive": True,
        },
    },
    {
        "task_key": "poi_candidate_quality_rollup",
        "task_type": ScheduledTaskType.source_quality_rollup.value,
        "schedule_type": ScheduledTaskScheduleType.manual.value,
        "enabled": False,
        "payload": {"job_type": BackgroundJobType.all_poi_candidate_match.value},
    },
    {
        "task_key": "itinerary_app_feed_export",
        "task_type": ScheduledTaskType.itinerary_app_feed_export.value,
        "schedule_type": ScheduledTaskScheduleType.manual.value,
        "enabled": False,
        "payload": {"job_type": BackgroundJobType.itinerary_app_feed_export.value},
    },
    {
        "task_key": "recent_events_photo_rescue",
        "task_type": ScheduledTaskType.event_photo_rescue.value,
        "schedule_type": ScheduledTaskScheduleType.manual.value,
        "enabled": False,
        "payload": {
            "job_type": BackgroundJobType.recent_events_photo_rescue.value,
            "since_hours": 168,
            "limit": 100,
        },
    },
    {
        "task_key": "source_quality_rollup_all",
        "task_type": ScheduledTaskType.source_quality_rollup.value,
        "schedule_type": ScheduledTaskScheduleType.manual.value,
        "enabled": False,
        "payload": {"job_type": BackgroundJobType.all_source_quality_rollup.value},
    },
    {
        "task_key": "partner_report_export_due_regions",
        "task_type": ScheduledTaskType.partner_report_export.value,
        "schedule_type": ScheduledTaskScheduleType.manual.value,
        "enabled": False,
        "payload": {"job_type": BackgroundJobType.region_partner_report.value},
    },
)


class SkipJob(RuntimeError):
    """Raised by handlers when a job is valid but intentionally skipped."""


@dataclass(frozen=True)
class BackgroundJobFilters:
    status: str | None = None
    job_type: str | None = None
    queue_name: str | None = None


@dataclass(frozen=True)
class SchedulerRunResult:
    due_task_count: int
    enqueued_job_ids: list[int]
    dry_run: bool = False


def _safe_json(data: object) -> str:
    return json.dumps(data, default=str, sort_keys=True)


def _parse_json_object(value: str | None) -> dict[str, object]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _normalized_sensitive_key(key: object) -> str:
    return str(key).strip().lower().replace("_", "-")


def _is_sensitive_key(key: object) -> bool:
    normalized = _normalized_sensitive_key(key)
    return any(part.replace("_", "-") in normalized for part in SENSITIVE_KEY_PARTS)


def _redact_url(value: str) -> str:
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.netloc:
        return value
    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    if not query_pairs:
        return value
    redacted_pairs = [
        (key, REDACTED if key.lower() in SENSITIVE_QUERY_KEYS else item_value)
        for key, item_value in query_pairs
    ]
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urlencode(redacted_pairs, doseq=True),
            parsed.fragment,
        ),
    )


def redact_sensitive_text(value: str) -> str:
    """Redact common key-value secrets in plain strings and URLs."""

    redacted = _redact_url(value)
    pattern = re.compile(
        r"(?i)\b(apikey|api_key|token|secret|password|authorization|x-api-key)"
        r"(\s*[=:]\s*)([^\s,;&}]+)",
    )
    return pattern.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{REDACTED}",
        redacted,
    )


def redact_sensitive_payload(value: object) -> object:
    """Return a JSON-safe copy with provider credentials and tokens redacted."""

    if isinstance(value, Mapping):
        redacted: dict[str, object] = {}
        for key, item_value in value.items():
            string_key = str(key)
            redacted[string_key] = (
                REDACTED
                if _is_sensitive_key(string_key)
                else redact_sensitive_payload(item_value)
            )
        return redacted
    if isinstance(value, list | tuple):
        return [redact_sensitive_payload(item) for item in value]
    if isinstance(value, str):
        return redact_sensitive_text(value)
    if value is None or isinstance(value, bool | int | float):
        return value
    return str(value)


def redact_error_message(error: object) -> str:
    return redact_sensitive_text(str(error))


def _redacted_json(data: object) -> str:
    return _safe_json(redact_sensitive_payload(data))


def enqueue_job(
    session: Session,
    job_type: str,
    payload: Mapping[str, object] | None,
    scheduled_for: object | None = None,
    priority: int = 100,
    queue_name: str = DEFAULT_QUEUE_NAME,
    created_by: str | None = None,
    max_attempts: int = 3,
) -> BackgroundJob:
    """Create a pending local background job."""

    allowed_types = {item.value for item in BackgroundJobType}
    normalized_type = (
        job_type if job_type in allowed_types else BackgroundJobType.unknown.value
    )
    job = BackgroundJob(
        job_type=normalized_type,
        status=BackgroundJobStatus.pending.value,
        priority=priority,
        queue_name=queue_name or DEFAULT_QUEUE_NAME,
        payload_json=_redacted_json(dict(payload or {})),
        scheduled_for=cast("Any", scheduled_for),
        created_by=created_by,
        max_attempts=max(1, max_attempts),
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def list_jobs(
    session: Session,
    filters: BackgroundJobFilters | None = None,
) -> list[BackgroundJob]:
    statement = select(BackgroundJob).order_by(
        BackgroundJob.created_at.desc(),
        BackgroundJob.id.desc(),
    )
    if filters:
        if filters.status:
            statement = statement.where(BackgroundJob.status == filters.status)
        if filters.job_type:
            statement = statement.where(BackgroundJob.job_type == filters.job_type)
        if filters.queue_name:
            statement = statement.where(BackgroundJob.queue_name == filters.queue_name)
    return list(session.scalars(statement).all())


def get_job(session: Session, job_id: int) -> BackgroundJob | None:
    return session.get(BackgroundJob, job_id)


def job_status_counts(session: Session) -> dict[str, int]:
    rows = session.execute(
        select(BackgroundJob.status, func.count(BackgroundJob.id)).group_by(
            BackgroundJob.status,
        ),
    ).all()
    counts = {status: int(count) for status, count in rows}
    for status in BackgroundJobStatus:
        counts.setdefault(status.value, 0)
    return counts


def jobs_needing_attention_count(session: Session) -> int:
    return int(
        session.scalar(
            select(func.count(BackgroundJob.id)).where(
                BackgroundJob.status == BackgroundJobStatus.failure.value,
            ),
        )
        or 0,
    )


def photo_rescue_jobs_needing_attention_count(session: Session) -> int:
    photo_job_types = {
        BackgroundJobType.event_photo_rescue.value,
        BackgroundJobType.api_feed_run_photo_rescue.value,
        BackgroundJobType.recent_events_photo_rescue.value,
    }
    return int(
        session.scalar(
            select(func.count(BackgroundJob.id)).where(
                BackgroundJob.status == BackgroundJobStatus.failure.value,
                BackgroundJob.job_type.in_(photo_job_types),
            ),
        )
        or 0,
    )


def claim_next_job(
    session: Session,
    worker_id: str,
    queue_name: str = DEFAULT_QUEUE_NAME,
) -> BackgroundJob | None:
    now = utc_now()
    statement = (
        select(BackgroundJob)
        .where(
            BackgroundJob.status == BackgroundJobStatus.pending.value,
            BackgroundJob.queue_name == (queue_name or DEFAULT_QUEUE_NAME),
            or_(
                BackgroundJob.scheduled_for.is_(None),
                BackgroundJob.scheduled_for <= now,
            ),
        )
        .order_by(
            BackgroundJob.priority.asc(),
            BackgroundJob.scheduled_for.asc().nullsfirst(),
            BackgroundJob.created_at.asc(),
            BackgroundJob.id.asc(),
        )
        .limit(1)
    )
    job = session.scalars(statement).first()
    if job is None:
        return None
    return mark_job_running(session, job, worker_id)


def mark_job_running(
    session: Session,
    job: BackgroundJob,
    worker_id: str,
) -> BackgroundJob:
    now = utc_now()
    job.status = BackgroundJobStatus.running.value
    job.locked_at = now
    job.locked_by = worker_id
    job.started_at = job.started_at or now
    job.completed_at = None
    job.attempts += 1
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def mark_job_success(
    session: Session,
    job: BackgroundJob,
    result: Mapping[str, object] | None,
) -> BackgroundJob:
    job.status = BackgroundJobStatus.success.value
    job.result_json = _redacted_json(dict(result or {}))
    job.error_message = None
    job.completed_at = utc_now()
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def mark_job_failure(
    session: Session,
    job: BackgroundJob,
    error: object,
    result: Mapping[str, object] | None = None,
) -> BackgroundJob:
    job.status = BackgroundJobStatus.failure.value
    job.error_message = redact_error_message(error)
    if result is not None:
        job.result_json = _redacted_json(dict(result))
    job.completed_at = utc_now()
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def mark_job_cancelled(session: Session, job: BackgroundJob) -> BackgroundJob:
    job.status = BackgroundJobStatus.cancelled.value
    job.completed_at = utc_now()
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def mark_job_skipped(
    session: Session,
    job: BackgroundJob,
    result: Mapping[str, object] | None = None,
) -> BackgroundJob:
    job.status = BackgroundJobStatus.skipped.value
    job.result_json = _redacted_json(dict(result or {}))
    job.completed_at = utc_now()
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def retry_job(session: Session, job_id: int) -> BackgroundJob | None:
    job = session.get(BackgroundJob, job_id)
    if job is None:
        return None
    if job.status not in {
        BackgroundJobStatus.failure.value,
        BackgroundJobStatus.cancelled.value,
        BackgroundJobStatus.skipped.value,
    }:
        return job
    job.status = BackgroundJobStatus.pending.value
    job.locked_at = None
    job.locked_by = None
    job.started_at = None
    job.completed_at = None
    job.error_message = None
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def cancel_job(session: Session, job_id: int) -> BackgroundJob | None:
    job = session.get(BackgroundJob, job_id)
    if job is None:
        return None
    if job.status in {
        BackgroundJobStatus.success.value,
        BackgroundJobStatus.failure.value,
        BackgroundJobStatus.cancelled.value,
        BackgroundJobStatus.skipped.value,
    }:
        return job
    return mark_job_cancelled(session, job)


def _job_payload(job: BackgroundJob) -> dict[str, object]:
    return _parse_json_object(job.payload_json)


def _source_ids_from_payload(payload: Mapping[str, object]) -> list[int]:
    values = payload.get("source_ids") or payload.get("master_source_ids")
    if not isinstance(values, Sequence) or isinstance(values, str | bytes):
        return []
    source_ids: list[int] = []
    for value in values:
        try:
            source_ids.append(int(str(value)))
        except ValueError:
            continue
    return source_ids


def _int_payload_value(
    payload: Mapping[str, object],
    key: str,
    *,
    default: int | None = None,
) -> int:
    value = payload.get(key)
    if value in (None, ""):
        if default is not None:
            return default
        raise ValueError(f"{key} is required.")
    try:
        return int(str(value))
    except ValueError as exc:
        raise ValueError(f"{key} must be an integer.") from exc


def _handle_app_feed_export(session: Session, job: BackgroundJob) -> dict[str, object]:
    from app.services.app_feed_service import create_app_feed_export

    payload = _job_payload(job)
    export_type = str(payload.get("export_type") or "full")
    if export_type not in {"events", "pois", "venues", "full"}:
        raise ValueError("Unsupported app feed export type.")
    export = create_app_feed_export(
        session,
        cast(Literal["events", "pois", "venues", "full"], export_type),
        job.created_by or job.locked_by or "background-worker",
    )
    result = {
        "app_feed_export_id": export.id,
        "export_type": export.export_type,
        "status": export.status,
        "record_count": export.record_count,
    }
    if export.status == "failure":
        raise RuntimeError(export.error_message or "App feed export failed.")
    return result


def _handle_crawl_source(
    session: Session,
    job: BackgroundJob,
    fetcher: Fetcher | None,
) -> dict[str, object]:
    from app.services.crawl_service import run_manual_crawl

    payload = _job_payload(job)
    try:
        source_id = int(str(payload.get("source_id") or ""))
    except ValueError as exc:
        raise ValueError("source_id is required.") from exc
    crawl_run = run_manual_crawl(
        session,
        source_id,
        fetcher=fetcher or fetch_calendar_url,
    )
    return {
        "crawl_run_id": crawl_run.id,
        "source_id": crawl_run.source_id,
        "status": crawl_run.status,
        "events_created_count": crawl_run.events_created_count,
        "events_updated_count": crawl_run.events_updated_count,
    }


def _handle_bulk_crawl(
    session: Session,
    job: BackgroundJob,
    fetcher: Fetcher | None,
) -> dict[str, object]:
    from app.services.bulk_crawl_service import run_bulk_crawl_for_master_ids

    payload = _job_payload(job)
    source_ids = _source_ids_from_payload(payload)
    title = str(payload.get("title") or "Background Bulk Crawl")
    summary = run_bulk_crawl_for_master_ids(
        session,
        source_ids,
        fetcher=fetcher or fetch_calendar_url,
        title=title,
    )
    return {
        "selected_count": summary.selected_count,
        "attempted_count": summary.attempted_count,
        "skipped_count": summary.skipped_count,
        "successful_count": summary.successful_count,
        "failed_count": summary.failed_count,
        "events_extracted": summary.events_extracted,
        "crawl_run_ids": [attempt.crawl_run_id for attempt in summary.attempts],
    }


def _handle_scheduled_crawl_due_sources(
    session: Session,
    job: BackgroundJob,
    fetcher: Fetcher | None,
) -> dict[str, object]:
    from app.services.bulk_crawl_service import (
        due_crawl_rows,
        run_bulk_crawl_for_master_ids,
    )

    source_ids = [row.source.id for row in due_crawl_rows(session)]
    summary = run_bulk_crawl_for_master_ids(
        session,
        source_ids,
        fetcher=fetcher or fetch_calendar_url,
        title="Scheduled Crawl Due Sources",
    )
    return {
        "selected_count": summary.selected_count,
        "attempted_count": summary.attempted_count,
        "skipped_count": summary.skipped_count,
        "successful_count": summary.successful_count,
        "failed_count": summary.failed_count,
        "events_extracted": summary.events_extracted,
        "crawl_run_ids": [attempt.crawl_run_id for attempt in summary.attempts],
    }


def _handle_provider_sandbox(
    session: Session,
    settings: Settings,
    job: BackgroundJob,
) -> dict[str, object]:
    payload = _job_payload(job)
    parameters = cast(dict[str, object], payload.get("parameters") or payload)
    requested_by = job.created_by or job.locked_by
    if job.job_type == BackgroundJobType.provider_sandbox_jambase.value:
        from app.services.jambase_live_service import run_jambase_live_sandbox

        run = run_jambase_live_sandbox(
            session,
            settings,
            parameters,
            requested_by=requested_by,
        )
    else:
        from app.services.cityspark_live_service import run_cityspark_live_sandbox

        run = run_cityspark_live_sandbox(
            session,
            settings,
            parameters,
            requested_by=requested_by,
        )
    return {
        "api_feed_run_id": run.id,
        "provider_key": run.provider_key,
        "status": run.status,
        "raw_record_count": run.raw_record_count,
        "normalized_candidate_count": run.normalized_candidate_count,
    }


def _handle_image_preflight(session: Session, job: BackgroundJob) -> dict[str, object]:
    from app.services.image_qa_service import (
        get_image_candidate,
        mark_candidate_preflight_result,
    )

    payload = _job_payload(job)
    try:
        candidate_id = int(str(payload.get("candidate_id") or ""))
    except ValueError as exc:
        raise SkipJob("candidate_id is required.") from exc
    candidate = get_image_candidate(session, candidate_id)
    if candidate is None:
        raise SkipJob(f"Image candidate #{candidate_id} was not found.")
    is_accessible = (
        True if candidate.is_direct_image_asset else candidate.is_accessible
    )
    updated = mark_candidate_preflight_result(
        session,
        candidate.id,
        is_accessible=is_accessible,
    )
    return {
        "image_candidate_id": candidate.id,
        "is_accessible": updated.is_accessible if updated else None,
        "status": updated.candidate_status if updated else candidate.candidate_status,
    }


def _photo_rescue_result_dict(result: object) -> dict[str, object]:
    return {
        "event_id": getattr(result, "event_id", None),
        "selected_candidate_id": getattr(result, "selected_candidate_id", None),
        "selected_url": getattr(result, "selected_url", None),
        "selected_reason": getattr(result, "reason", None),
        "created_candidate_count": getattr(result, "created_candidate_count", 0),
        "blocked_candidate_count": getattr(result, "blocked_candidate_count", 0),
        "fallback_used": getattr(result, "fallback_used", False),
        "needs_approval": getattr(result, "needs_approval", False),
    }


def _photo_rescue_summary_for_events(
    session: Session,
    event_ids: Sequence[int],
    rescued_results: Sequence[object],
) -> dict[str, object]:
    from app.db.models import Event, ImageCandidate

    unique_event_ids = sorted(set(event_ids))
    if not unique_event_ids:
        return {
            "event_count": 0,
            "rescued_event_count": 0,
            "selected_count": 0,
            "blocked_generic_count": 0,
            "missing_usable_image_count": 0,
            "results": [],
        }

    session.flush()
    events = list(
        session.scalars(select(Event).where(Event.id.in_(unique_event_ids))).all()
    )
    candidates = list(
        session.scalars(
            select(ImageCandidate).where(ImageCandidate.event_id.in_(unique_event_ids))
        ).all()
    )
    blocked_generic_count = sum(
        1
        for candidate in candidates
        if candidate.generic_detection_score >= 70
        or candidate.appears_stock_or_placeholder
        or "generic_provider_image" in candidate.qa_flags
        or "stock_placeholder_candidate" in candidate.qa_flags
    )
    return {
        "event_count": len(unique_event_ids),
        "rescued_event_count": len(rescued_results),
        "selected_count": sum(1 for event in events if event.selected_main_image_url),
        "blocked_generic_count": blocked_generic_count,
        "missing_usable_image_count": sum(
            1 for event in events if not event.selected_main_image_url
        ),
        "results": [_photo_rescue_result_dict(result) for result in rescued_results],
    }


def _handle_event_photo_rescue(
    session: Session,
    job: BackgroundJob,
) -> dict[str, object]:
    from app.db.models import Event
    from app.services.event_photo_rescue_service import run_event_photo_rescue

    payload = _job_payload(job)
    event_id = _int_payload_value(payload, "event_id")
    result = run_event_photo_rescue(session, event_id, commit=False)
    if result is None:
        raise SkipJob(f"Event #{event_id} was not found.")
    event = session.get(Event, event_id)
    return {
        **_photo_rescue_result_dict(result),
        "image_status": event.image_status if event else None,
    }


def _event_ids_for_api_feed_run(session: Session, run_id: int) -> list[int]:
    from app.db.models import ApiFeedRecord, Event

    event_ids = set(
        session.scalars(
            select(Event.id).where(Event.api_feed_run_id == run_id),
        ).all(),
    )
    event_ids.update(
        event_id
        for event_id in session.scalars(
            select(ApiFeedRecord.created_event_id).where(
                ApiFeedRecord.api_feed_run_id == run_id,
                ApiFeedRecord.created_event_id.is_not(None),
            ),
        ).all()
        if event_id is not None
    )
    return sorted(event_ids)


def _handle_api_feed_run_photo_rescue(
    session: Session,
    job: BackgroundJob,
) -> dict[str, object]:
    from app.db.models import ApiFeedRun
    from app.services.event_photo_rescue_service import run_event_photo_rescue

    payload = _job_payload(job)
    run_id = _int_payload_value(payload, "api_feed_run_id")
    run = session.get(ApiFeedRun, run_id)
    if run is None:
        raise SkipJob(f"API feed run #{run_id} was not found.")
    event_ids = _event_ids_for_api_feed_run(session, run_id)
    results = [
        result
        for event_id in event_ids
        if (result := run_event_photo_rescue(session, event_id, commit=False))
        is not None
    ]
    summary = _photo_rescue_summary_for_events(session, event_ids, results)
    return {"api_feed_run_id": run_id, **summary}


def _handle_recent_events_photo_rescue(
    session: Session,
    job: BackgroundJob,
) -> dict[str, object]:
    from app.db.models import Event
    from app.services.event_photo_rescue_service import run_event_photo_rescue

    payload = _job_payload(job)
    since_hours = max(1, _int_payload_value(payload, "since_hours", default=168))
    limit = max(1, min(_int_payload_value(payload, "limit", default=100), 500))
    cutoff = utc_now() - timedelta(hours=since_hours)
    event_ids = list(
        session.scalars(
            select(Event.id)
            .where(
                Event.category == "Concert",
                Event.record_type == "event",
                or_(
                    Event.created_at >= cutoff,
                    Event.updated_at >= cutoff,
                    Event.last_seen_at >= cutoff,
                ),
            )
            .order_by(Event.updated_at.desc(), Event.id.desc())
            .limit(limit),
        ).all()
    )
    results = [
        result
        for event_id in event_ids
        if (result := run_event_photo_rescue(session, event_id, commit=False))
        is not None
    ]
    summary = _photo_rescue_summary_for_events(session, event_ids, results)
    return {"since_hours": since_hours, "limit": limit, **summary}


def _handle_extract_crawl_run(
    session: Session, job: BackgroundJob
) -> dict[str, object]:
    from app.db.models import CrawlRun
    from app.services.event_service import save_ics_events_for_crawl_run
    from app.services.extracted_event_service import persist_extraction_result
    from app.services.source_extraction_service import extract_source_content

    payload = _job_payload(job)
    crawl_run_id = _int_payload_value(payload, "crawl_run_id")
    crawl_run = session.get(CrawlRun, crawl_run_id)
    if crawl_run is None:
        raise SkipJob(f"Crawl run #{crawl_run_id} was not found.")
    extraction = extract_source_content(
        source_url=crawl_run.source_url,
        content_type=crawl_run.content_type,
        raw_body=crawl_run.raw_response_body,
    )
    staged = persist_extraction_result(session, crawl_run, extraction)
    events_saved = 0
    if extraction.extractor_type == "ics":
        events_saved = save_ics_events_for_crawl_run(session, crawl_run)
    return {
        "crawl_run_id": crawl_run.id,
        "extractor_type": extraction.extractor_type,
        "extraction_status": extraction.status,
        "event_candidates_count": len(staged),
        "discovered_links_count": len(extraction.discovered_links),
        "events_saved_count": events_saved,
    }


def _handle_approve_extracted_event_candidate(
    session: Session,
    job: BackgroundJob,
) -> dict[str, object]:
    from app.services.extracted_event_service import approve_extracted_event_candidate

    payload = _job_payload(job)
    candidate_id = _int_payload_value(payload, "candidate_id")
    event = approve_extracted_event_candidate(
        session,
        candidate_id,
        approved_by=job.created_by or job.locked_by,
    )
    return {"candidate_id": candidate_id, "event_id": event.id}


def _handle_process_extracted_event_batch(
    session: Session,
    job: BackgroundJob,
) -> dict[str, object]:
    from app.db.models import SourceExtractedEventCandidate
    from app.services.extracted_event_service import approve_extracted_event_candidate

    payload = _job_payload(job)
    raw_candidate_ids = payload.get("candidate_ids")
    if isinstance(raw_candidate_ids, Sequence) and not isinstance(
        raw_candidate_ids,
        str | bytes,
    ):
        candidate_ids = [int(str(item)) for item in raw_candidate_ids]
    else:
        crawl_run_id = _int_payload_value(payload, "crawl_run_id")
        candidate_ids = list(
            session.scalars(
                select(SourceExtractedEventCandidate.id).where(
                    SourceExtractedEventCandidate.crawl_run_id == crawl_run_id,
                    SourceExtractedEventCandidate.review_status.in_(
                        {"pending_review", "needs_review"}
                    ),
                    SourceExtractedEventCandidate.validation_status == "valid",
                )
            ).all()
        )
    approved_event_ids: list[int] = []
    failed_candidate_ids: list[int] = []
    for candidate_id in candidate_ids:
        try:
            event = approve_extracted_event_candidate(
                session,
                candidate_id,
                approved_by=job.created_by or job.locked_by,
            )
        except ValueError:
            failed_candidate_ids.append(candidate_id)
            continue
        approved_event_ids.append(event.id)
    return {
        "selected_count": len(candidate_ids),
        "approved_count": len(approved_event_ids),
        "failed_count": len(failed_candidate_ids),
        "approved_event_ids": approved_event_ids,
        "failed_candidate_ids": failed_candidate_ids,
    }


def _handle_source_quality_rollup(
    session: Session,
    job: BackgroundJob,
) -> dict[str, object]:
    from app.services.source_quality_service import (
        compute_source_quality_for_api_provider,
        compute_source_quality_for_master_source,
        compute_source_quality_for_partner,
        compute_source_quality_for_region,
    )

    payload = _job_payload(job)
    source_kind = str(payload.get("source_kind") or "")
    if source_kind == "master_calendar_source":
        source_id = _int_payload_value(payload, "source_id")
        score = compute_source_quality_for_master_source(session, source_id)
    elif source_kind == "api_provider":
        provider_key = str(payload.get("provider_key") or "")
        if not provider_key:
            raise ValueError("provider_key is required.")
        score = compute_source_quality_for_api_provider(session, provider_key)
    elif source_kind == "region":
        region_id = _int_payload_value(payload, "region_id")
        score = compute_source_quality_for_region(session, region_id)
    elif source_kind == "destination_partner":
        partner_id = _int_payload_value(payload, "partner_id")
        score = compute_source_quality_for_partner(session, partner_id)
    else:
        raise ValueError("Unsupported source_kind for source quality rollup.")
    return {
        "source_quality_score_id": score.id,
        "source_kind": score.source_kind,
        "score": score.score,
        "grade": score.score_grade,
    }


def _handle_all_source_quality_rollup(
    session: Session,
    _job: BackgroundJob,
) -> dict[str, object]:
    from app.services.source_quality_service import compute_all_source_quality

    return {key: value for key, value in compute_all_source_quality(session).items()}


def _handle_region_partner_report(
    session: Session,
    job: BackgroundJob,
) -> dict[str, object]:
    from app.db.models import Region
    from app.services.partner_report_service import generate_region_partner_report

    payload = _job_payload(job)
    raw_region_id = payload.get("region_id")
    if raw_region_id in (None, ""):
        region_id = session.scalar(select(Region.id).order_by(Region.id.asc()))
        if region_id is None:
            raise SkipJob("No regions exist for partner report generation.")
    else:
        region_id = _int_payload_value(payload, "region_id")
    report = generate_region_partner_report(
        session,
        region_id,
        generated_by=job.created_by or job.locked_by or "background-worker",
    )
    return {
        "partner_report_id": report.id,
        "region_id": report.region_id,
        "report_type": report.report_type,
        "status": report.status,
    }


def _handle_rebuild_app_search_index(
    session: Session,
    _job: BackgroundJob,
) -> dict[str, object]:
    from app.services.app_search_service import rebuild_search_index

    counts = rebuild_search_index(session)
    return {
        "index_counts": counts,
        "indexed_record_count": sum(counts.values()),
    }


def _handle_app_map_feed_export(
    session: Session,
    job: BackgroundJob,
) -> dict[str, object]:
    from app.services.map_display_service import MapMarkerFilters, list_map_markers

    payload = _job_payload(job)
    markers = list_map_markers(
        session,
        MapMarkerFilters(
            entity_type=str(payload.get("entity_type") or "") or None,
            category=str(payload.get("category") or "") or None,
            subcategory=str(payload.get("subcategory") or "") or None,
            region_id=(
                _int_payload_value(payload, "region_id")
                if payload.get("region_id") not in (None, "")
                else None
            ),
            limit=_int_payload_value(payload, "limit", default=250),
            offset=_int_payload_value(payload, "offset", default=0),
        ),
    )
    return {
        "export_type": "map_markers",
        "record_count": markers["count"],
        "total": markers["total"],
    }


def _handle_app_filter_options_export(
    session: Session,
    job: BackgroundJob,
) -> dict[str, object]:
    from app.services.map_display_service import build_filter_options

    payload = _job_payload(job)
    region_id = (
        _int_payload_value(payload, "region_id")
        if payload.get("region_id") not in (None, "")
        else None
    )
    options = build_filter_options(session, region_id=region_id)
    return {
        "export_type": "filter_options",
        "region_id": region_id,
        "event_filter_sections": len(options["event_filters"]),
        "poi_category_count": len(options["poi_filters"]["categories"]),
    }


def _handle_poi_inventory_snapshot_export(
    session: Session,
    job: BackgroundJob,
) -> dict[str, object]:
    from app.services.poi_inventory_export_service import (
        DEFAULT_POI_INVENTORY_OUTPUT_DIR,
        export_poi_inventory_bundle,
    )

    payload = _job_payload(job)
    output_dir = str(payload.get("output_dir") or DEFAULT_POI_INVENTORY_OUTPUT_DIR)
    archive_value = payload.get("archive")
    archive = not (archive_value is False or archive_value == "false")
    raw_mode = str(payload.get("mode") or "full")
    mode = (
        raw_mode
        if raw_mode in {"full", "dedupe_only", "inventory_only"}
        else "full"
    )
    exports = export_poi_inventory_bundle(
        session,
        output_dir,
        archive=archive,
        generated_by=job.created_by or job.locked_by or "background-worker",
        mode=cast(Literal["full", "dedupe_only", "inventory_only"], mode),
    )
    return {
        "export_count": len(exports),
        "mode": mode,
        "archive": archive,
        "exports": {
            name: {
                "poi_inventory_export_id": export.id,
                "export_type": export.export_type,
                "status": export.status,
                "record_count": export.record_count,
                "duplicate_key_count": export.duplicate_key_count,
                "output_path": export.output_path,
                "sha256_hash": export.sha256_hash,
            }
            for name, export in exports.items()
        },
    }


def _handle_poi_candidate_match(
    session: Session,
    job: BackgroundJob,
) -> dict[str, object]:
    from app.services.poi_candidate_service import recompute_candidate_match_quality

    payload = _job_payload(job)
    candidate_id = _int_payload_value(payload, "candidate_id")
    candidate = recompute_candidate_match_quality(session, candidate_id)
    return {
        "poi_candidate_id": candidate.id,
        "match_status": candidate.match_status,
        "match_confidence": candidate.match_confidence,
        "poi_quality_score": candidate.poi_quality_score,
    }


def _handle_all_poi_candidate_match(
    session: Session,
    _job: BackgroundJob,
) -> dict[str, object]:
    from app.services.poi_candidate_service import recompute_all_pending_candidates

    return {
        key: value
        for key, value in recompute_all_pending_candidates(session).items()
    }


def _handle_rebuild_artist_registry(
    session: Session,
    _job: BackgroundJob,
) -> dict[str, object]:
    from app.services.artist_service import rebuild_artist_registry

    return {key: value for key, value in rebuild_artist_registry(session).items()}


def _handle_artist_genre_normalization(
    session: Session,
    _job: BackgroundJob,
) -> dict[str, object]:
    from app.services.genre_service import normalize_all_genres

    return {key: value for key, value in normalize_all_genres(session).items()}


def _handle_artist_image_rescue(
    session: Session,
    job: BackgroundJob,
) -> dict[str, object]:
    from app.db.models import Event, EventArtist
    from app.services.artist_service import create_artist_image_candidates_for_event
    from app.services.event_photo_rescue_service import run_event_photo_rescue

    payload = _job_payload(job)
    raw_event_id = payload.get("event_id")
    if raw_event_id not in (None, ""):
        event_ids = [_int_payload_value(payload, "event_id")]
    else:
        limit = max(1, min(_int_payload_value(payload, "limit", default=100), 500))
        event_ids = list(
            session.scalars(
                select(Event.id)
                .join(EventArtist, EventArtist.event_id == Event.id)
                .where(Event.category == "Concert", Event.record_type == "event")
                .order_by(Event.updated_at.desc(), Event.id.desc())
                .distinct()
                .limit(limit),
            ).all()
        )
    created_candidates = 0
    results = []
    for event_id in event_ids:
        created_candidates += create_artist_image_candidates_for_event(
            session,
            event_id,
        )
        result = run_event_photo_rescue(session, event_id, commit=False)
        if result is not None:
            results.append(result)
    summary = _photo_rescue_summary_for_events(session, event_ids, results)
    return {
        "artist_image_candidate_count": created_candidates,
        **summary,
    }


def _handle_itinerary_quality_rollup(
    session: Session,
    job: BackgroundJob,
) -> dict[str, object]:
    from app.db.models import Itinerary
    from app.services.itinerary_service import compute_itinerary_quality

    payload = _job_payload(job)
    raw_itinerary_id = payload.get("itinerary_id")
    if raw_itinerary_id not in (None, ""):
        itinerary_id = _int_payload_value(payload, "itinerary_id")
        score, flags = compute_itinerary_quality(session, itinerary_id)
        return {
            "itinerary_id": itinerary_id,
            "quality_score": score,
            "quality_flags": flags,
            "itinerary_count": 1,
        }
    itineraries = list(session.scalars(select(Itinerary.id)).all())
    for itinerary_id in itineraries:
        compute_itinerary_quality(session, itinerary_id)
    return {"itinerary_count": len(itineraries)}


def _handle_itinerary_app_feed_export(
    session: Session,
    _job: BackgroundJob,
) -> dict[str, object]:
    from app.services.itinerary_service import list_app_itineraries

    records = list_app_itineraries(session)
    return {
        "export_type": "itineraries",
        "record_count": len(records),
    }


def _handle_build_artist_tour_itinerary(
    session: Session,
    job: BackgroundJob,
) -> dict[str, object]:
    from app.db.models import CanonicalArtist
    from app.services.itinerary_service import build_itinerary_from_artist_events

    payload = _job_payload(job)
    raw_artist_id = payload.get("artist_id")
    if raw_artist_id in (None, ""):
        artist_id = session.scalar(
            select(CanonicalArtist.id).order_by(CanonicalArtist.id.asc())
        )
        if artist_id is None:
            raise SkipJob("No artists exist for artist tour itinerary suggestions.")
    else:
        artist_id = _int_payload_value(payload, "artist_id")
    itinerary = build_itinerary_from_artist_events(session, artist_id)
    return {
        "itinerary_id": itinerary.id,
        "artist_id": artist_id,
        "status": itinerary.status,
        "stop_count": len(itinerary.stops),
    }


def _handle_build_region_itinerary_suggestions(
    session: Session,
    job: BackgroundJob,
) -> dict[str, object]:
    from app.db.models import Region
    from app.services.itinerary_service import build_itinerary_from_region

    payload = _job_payload(job)
    raw_region_id = payload.get("region_id")
    if raw_region_id in (None, ""):
        region_id = session.scalar(select(Region.id).order_by(Region.id.asc()))
        if region_id is None:
            raise SkipJob("No regions exist for itinerary suggestions.")
    else:
        region_id = _int_payload_value(payload, "region_id")
    itinerary = build_itinerary_from_region(session, region_id)
    return {
        "itinerary_id": itinerary.id,
        "region_id": region_id,
        "status": itinerary.status,
        "stop_count": len(itinerary.stops),
    }


def execute_job(
    session: Session,
    settings: Settings,
    job: BackgroundJob,
    *,
    fetcher: Fetcher | None = None,
) -> BackgroundJob:
    """Run a claimed job once and persist success, failure, or skipped state."""

    try:
        if job.job_type == BackgroundJobType.app_feed_export.value:
            result = _handle_app_feed_export(session, job)
        elif job.job_type == BackgroundJobType.crawl_source.value:
            result = _handle_crawl_source(session, job, fetcher)
        elif job.job_type == BackgroundJobType.bulk_crawl.value:
            result = _handle_bulk_crawl(session, job, fetcher)
        elif job.job_type == BackgroundJobType.scheduled_crawl_due_sources.value:
            result = _handle_scheduled_crawl_due_sources(session, job, fetcher)
        elif job.job_type in {
            BackgroundJobType.provider_sandbox_jambase.value,
            BackgroundJobType.provider_sandbox_cityspark.value,
        }:
            result = _handle_provider_sandbox(session, settings, job)
        elif job.job_type == BackgroundJobType.image_preflight.value:
            result = _handle_image_preflight(session, job)
        elif job.job_type == BackgroundJobType.event_photo_rescue.value:
            result = _handle_event_photo_rescue(session, job)
        elif job.job_type == BackgroundJobType.api_feed_run_photo_rescue.value:
            result = _handle_api_feed_run_photo_rescue(session, job)
        elif job.job_type == BackgroundJobType.recent_events_photo_rescue.value:
            result = _handle_recent_events_photo_rescue(session, job)
        elif job.job_type == BackgroundJobType.extract_crawl_run.value:
            result = _handle_extract_crawl_run(session, job)
        elif job.job_type == (
            BackgroundJobType.approve_extracted_event_candidate.value
        ):
            result = _handle_approve_extracted_event_candidate(session, job)
        elif job.job_type == BackgroundJobType.process_extracted_event_batch.value:
            result = _handle_process_extracted_event_batch(session, job)
        elif job.job_type == BackgroundJobType.source_quality_rollup.value:
            result = _handle_source_quality_rollup(session, job)
        elif job.job_type == BackgroundJobType.all_source_quality_rollup.value:
            result = _handle_all_source_quality_rollup(session, job)
        elif job.job_type == BackgroundJobType.region_partner_report.value:
            result = _handle_region_partner_report(session, job)
        elif job.job_type == BackgroundJobType.rebuild_app_search_index.value:
            result = _handle_rebuild_app_search_index(session, job)
        elif job.job_type == BackgroundJobType.app_map_feed_export.value:
            result = _handle_app_map_feed_export(session, job)
        elif job.job_type == BackgroundJobType.app_filter_options_export.value:
            result = _handle_app_filter_options_export(session, job)
        elif job.job_type == BackgroundJobType.poi_inventory_snapshot_export.value:
            result = _handle_poi_inventory_snapshot_export(session, job)
        elif job.job_type == BackgroundJobType.poi_candidate_match.value:
            result = _handle_poi_candidate_match(session, job)
        elif job.job_type in {
            BackgroundJobType.all_poi_candidate_match.value,
            BackgroundJobType.poi_candidate_quality_rollup.value,
        }:
            result = _handle_all_poi_candidate_match(session, job)
        elif job.job_type == BackgroundJobType.rebuild_artist_registry.value:
            result = _handle_rebuild_artist_registry(session, job)
        elif job.job_type == BackgroundJobType.artist_genre_normalization.value:
            result = _handle_artist_genre_normalization(session, job)
        elif job.job_type == BackgroundJobType.artist_image_rescue.value:
            result = _handle_artist_image_rescue(session, job)
        elif job.job_type == BackgroundJobType.itinerary_quality_rollup.value:
            result = _handle_itinerary_quality_rollup(session, job)
        elif job.job_type == BackgroundJobType.itinerary_app_feed_export.value:
            result = _handle_itinerary_app_feed_export(session, job)
        elif job.job_type == BackgroundJobType.build_artist_tour_itinerary.value:
            result = _handle_build_artist_tour_itinerary(session, job)
        elif job.job_type == (
            BackgroundJobType.build_region_itinerary_suggestions.value
        ):
            result = _handle_build_region_itinerary_suggestions(session, job)
        elif job.job_type == BackgroundJobType.poi_registry_import.value:
            raise SkipJob("POI registry import jobs require an explicit import file.")
        else:
            raise ValueError(f"Unknown background job type: {job.job_type}")
    except SkipJob as exc:
        return mark_job_skipped(session, job, {"message": str(exc)})
    except Exception as exc:
        return mark_job_failure(session, job, exc)
    return mark_job_success(session, job, result)


def process_next_job(
    session: Session,
    settings: Settings,
    worker_id: str,
    queue_name: str = DEFAULT_QUEUE_NAME,
    *,
    fetcher: Fetcher | None = None,
) -> BackgroundJob | None:
    """Claim and run the next pending job for a worker."""

    job = claim_next_job(session, worker_id, queue_name)
    if job is None:
        return None
    return execute_job(session, settings, job, fetcher=fetcher)


def ensure_default_scheduled_tasks(session: Session) -> None:
    existing_keys = set(session.scalars(select(ScheduledTask.task_key)).all())
    for task_data in DEFAULT_SCHEDULED_TASKS:
        task_key = str(task_data["task_key"])
        if task_key in existing_keys:
            continue
        task = ScheduledTask(
            task_key=task_key,
            task_type=str(task_data["task_type"]),
            enabled=bool(task_data["enabled"]),
            schedule_type=str(task_data["schedule_type"]),
            payload_json=_safe_json(task_data["payload"]),
        )
        session.add(task)
    session.commit()


def list_scheduled_tasks(session: Session) -> list[ScheduledTask]:
    ensure_default_scheduled_tasks(session)
    return list(
        session.scalars(
            select(ScheduledTask).order_by(ScheduledTask.task_key.asc()),
        ).all(),
    )


def get_scheduled_task(session: Session, task_id: int) -> ScheduledTask | None:
    ensure_default_scheduled_tasks(session)
    return session.get(ScheduledTask, task_id)


def next_scheduled_task(
    session: Session,
    task_type: str | None = None,
) -> ScheduledTask | None:
    ensure_default_scheduled_tasks(session)
    statement = (
        select(ScheduledTask)
        .where(
            ScheduledTask.enabled.is_(True),
            ScheduledTask.schedule_type != ScheduledTaskScheduleType.manual.value,
            ScheduledTask.next_run_at.is_not(None),
        )
        .order_by(ScheduledTask.next_run_at.asc())
    )
    if task_type:
        statement = statement.where(ScheduledTask.task_type == task_type)
    return session.scalars(statement).first()


def _next_run_for_task(task: ScheduledTask) -> object | None:
    now = utc_now()
    if task.schedule_type == ScheduledTaskScheduleType.manual.value:
        return None
    if task.schedule_type == ScheduledTaskScheduleType.interval.value:
        return now + timedelta(minutes=max(1, task.interval_minutes or 60))
    if task.schedule_type == ScheduledTaskScheduleType.daily.value:
        return now + timedelta(days=1)
    if task.schedule_type == ScheduledTaskScheduleType.weekly.value:
        return now + timedelta(days=7)
    if task.schedule_type == ScheduledTaskScheduleType.biweekly.value:
        return now + timedelta(days=14)
    if task.schedule_type == ScheduledTaskScheduleType.monthly.value:
        return now + timedelta(days=30)
    return None


def job_type_for_scheduled_task(task: ScheduledTask) -> str:
    payload = _parse_json_object(task.payload_json)
    if task.task_type == ScheduledTaskType.crawl_due_sources.value:
        return BackgroundJobType.scheduled_crawl_due_sources.value
    if task.task_type == ScheduledTaskType.app_feed_export.value:
        return BackgroundJobType.app_feed_export.value
    if task.task_type == ScheduledTaskType.image_preflight.value:
        return BackgroundJobType.image_preflight.value
    if task.task_type == ScheduledTaskType.event_photo_rescue.value:
        payload_job_type = str(payload.get("job_type") or "")
        if payload_job_type in {
            BackgroundJobType.event_photo_rescue.value,
            BackgroundJobType.api_feed_run_photo_rescue.value,
            BackgroundJobType.recent_events_photo_rescue.value,
        }:
            return payload_job_type
        return BackgroundJobType.recent_events_photo_rescue.value
    if task.task_type == ScheduledTaskType.source_quality_rollup.value:
        payload_job_type = str(payload.get("job_type") or "")
        if payload_job_type in {
            BackgroundJobType.source_quality_rollup.value,
            BackgroundJobType.all_poi_candidate_match.value,
            BackgroundJobType.poi_candidate_quality_rollup.value,
        }:
            return payload_job_type
        return BackgroundJobType.all_source_quality_rollup.value
    if task.task_type == ScheduledTaskType.partner_report_export.value:
        return BackgroundJobType.region_partner_report.value
    if task.task_type == ScheduledTaskType.rebuild_app_search_index.value:
        return BackgroundJobType.rebuild_app_search_index.value
    if task.task_type == ScheduledTaskType.monthly_poi_inventory_snapshot.value:
        return BackgroundJobType.poi_inventory_snapshot_export.value
    if task.task_type == ScheduledTaskType.provider_sandbox.value:
        provider_key = str(payload.get("provider_key") or "")
        if provider_key == "jambase":
            return BackgroundJobType.provider_sandbox_jambase.value
        if provider_key == CITYSPARK_PROVIDER_KEY:
            return BackgroundJobType.provider_sandbox_cityspark.value
    return BackgroundJobType.unknown.value


def payload_for_scheduled_task(task: ScheduledTask) -> dict[str, object]:
    payload = _parse_json_object(task.payload_json)
    payload["scheduled_task_id"] = task.id
    payload["scheduled_task_key"] = task.task_key
    return payload


def enqueue_scheduled_task_now(
    session: Session,
    task_id: int,
    created_by: str | None = None,
) -> BackgroundJob | None:
    task = get_scheduled_task(session, task_id)
    if task is None:
        return None
    job = enqueue_job(
        session,
        job_type_for_scheduled_task(task),
        payload_for_scheduled_task(task),
        priority=100,
        created_by=created_by,
    )
    task.last_run_at = utc_now()
    task.last_job_id = job.id
    session.add(task)
    session.commit()
    session.refresh(job)
    return job


def due_scheduled_tasks(session: Session) -> list[ScheduledTask]:
    ensure_default_scheduled_tasks(session)
    now = utc_now()
    statement = (
        select(ScheduledTask)
        .where(
            ScheduledTask.enabled.is_(True),
            ScheduledTask.schedule_type != ScheduledTaskScheduleType.manual.value,
            ScheduledTask.next_run_at.is_not(None),
            ScheduledTask.next_run_at <= now,
        )
        .order_by(ScheduledTask.next_run_at.asc(), ScheduledTask.id.asc())
    )
    return list(session.scalars(statement).all())


def enqueue_due_scheduled_tasks(
    session: Session,
    *,
    dry_run: bool = False,
) -> SchedulerRunResult:
    tasks = due_scheduled_tasks(session)
    job_ids: list[int] = []
    if dry_run:
        return SchedulerRunResult(
            due_task_count=len(tasks),
            enqueued_job_ids=[],
            dry_run=True,
        )
    for task in tasks:
        job = enqueue_job(
            session,
            job_type_for_scheduled_task(task),
            payload_for_scheduled_task(task),
            priority=100,
            created_by="scheduler",
        )
        task.last_run_at = utc_now()
        task.last_job_id = job.id
        task.next_run_at = cast("Any", _next_run_for_task(task))
        session.add(task)
        job_ids.append(job.id)
    session.commit()
    return SchedulerRunResult(due_task_count=len(tasks), enqueued_job_ids=job_ids)


def default_worker_id() -> str:
    return f"{socket.gethostname()}-worker"
