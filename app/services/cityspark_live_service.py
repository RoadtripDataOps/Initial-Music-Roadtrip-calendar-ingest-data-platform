from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import ApiFeedRun
from app.services.api_feed_service import (
    CITYSPARK_PROVIDER_KEY,
    create_api_feed_run,
    create_failed_api_feed_run,
    extract_json_records,
)
from app.services.jambase_live_service import (
    LIVE_SANDBOX_RUN_MODE,
    clean_parameter,
    positive_int,
    provider_error_message,
)
from app.services.provider_http_client import (
    REDACTED,
    ProviderHttpClient,
    ProviderJsonClient,
    redact_json_value,
)


@dataclass(frozen=True)
class CitysparkSandboxContext:
    provider_key: str
    live_calls_enabled: bool
    credential_status: str
    portal_status: str
    max_events: int
    request_preview: dict[str, Any]
    default_values: dict[str, Any]
    disabled_reason: str | None


def normalized_cityspark_limit(settings: Settings, value: object | None) -> int:
    requested = positive_int(value, settings.cityspark_sandbox_max_events)
    return min(max(1, requested), max(1, settings.cityspark_sandbox_max_events))


def normalized_cityspark_page_size(settings: Settings, value: object | None) -> int:
    requested = positive_int(value, settings.cityspark_default_page_size)
    return min(max(1, requested), 200)


def bool_parameter(value: object | None, default: bool) -> bool:
    if value is None:
        return default
    lowered = str(value).strip().lower()
    if lowered in {"true", "1", "yes", "on"}:
        return True
    if lowered in {"false", "0", "no", "off"}:
        return False
    return default


def list_parameter(value: object | None) -> list[str] | None:
    cleaned = clean_parameter(value)
    if cleaned is None:
        return None
    parts = [part.strip() for part in cleaned.split(",")]
    values = [part for part in parts if part]
    return values or None


def cityspark_sandbox_body(
    settings: Settings,
    values: dict[str, object] | None = None,
) -> dict[str, object]:
    raw = values or {}
    body: dict[str, object] = {
        "portalScriptId": settings.cityspark_portal_script_id.strip(),
        "page": positive_int(raw.get("page"), 1),
        "pageSize": normalized_cityspark_page_size(settings, raw.get("pageSize")),
        "includeLabels": bool_parameter(raw.get("includeLabels"), True),
        "includeInstances": bool_parameter(raw.get("includeInstances"), True),
    }
    limit = normalized_cityspark_limit(settings, raw.get("limit"))
    body["limit"] = limit
    for key in ["searchTerm", "latitude", "longitude", "radius"]:
        value = clean_parameter(raw.get(key))
        if value is not None:
            body[key] = value
    for key in ["categories", "interest", "labels"]:
        values_list = list_parameter(raw.get(key))
        if values_list is not None:
            body[key] = values_list
    for key in ["blockVirtual", "handPicked"]:
        if key in raw:
            body[key] = bool_parameter(raw.get(key), False)
    return body


def redacted_cityspark_body(body: dict[str, object]) -> dict[str, object]:
    redacted = dict(body)
    redacted["portalScriptId"] = REDACTED
    value = redact_json_value(redacted)
    return value if isinstance(value, dict) else {}


def cityspark_request_preview(
    settings: Settings,
    values: dict[str, object] | None = None,
) -> dict[str, Any]:
    endpoint = f"{settings.cityspark_base_url.rstrip('/')}/v2/event/search"
    body = cityspark_sandbox_body(settings, values)
    return {
        "method": "POST",
        "url": endpoint,
        "headers": {"X-API-Key": REDACTED, "Content-Type": "application/json"},
        "body": redacted_cityspark_body(body),
    }


def cityspark_sandbox_context(settings: Settings) -> CitysparkSandboxContext:
    api_key_configured = bool(settings.cityspark_api_key.strip())
    portal_configured = bool(settings.cityspark_portal_script_id.strip())
    disabled_reason = None
    if not settings.cityspark_live_calls_enabled:
        disabled_reason = (
            "Set CITYSPARK_LIVE_CALLS_ENABLED=true to enable sandbox requests."
        )
    elif not api_key_configured:
        disabled_reason = "Set CITYSPARK_API_KEY to enable sandbox requests."
    elif not portal_configured:
        disabled_reason = "Set CITYSPARK_PORTAL_SCRIPT_ID to enable sandbox requests."
    return CitysparkSandboxContext(
        provider_key=CITYSPARK_PROVIDER_KEY,
        live_calls_enabled=settings.cityspark_live_calls_enabled,
        credential_status=(
            "Credentials Configured" if api_key_configured else "Credentials Missing"
        ),
        portal_status="Configured" if portal_configured else "Missing",
        max_events=max(1, settings.cityspark_sandbox_max_events),
        request_preview=cityspark_request_preview(settings),
        default_values=redacted_cityspark_body(cityspark_sandbox_body(settings)),
        disabled_reason=disabled_reason,
    )


def cityspark_records_from_payload(payload: object) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        for key in [
            "EventSeries",
            "eventSeries",
            "eventSeriesList",
            "events",
            "data",
            "results",
            "items",
            "records",
        ]:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return extract_json_records(payload)


def has_next_page(
    payload: object,
    page: int,
    page_size: int,
    record_count: int,
) -> bool:
    if record_count < page_size:
        return False
    if not isinstance(payload, dict):
        return False
    for key in ["hasMore", "has_more"]:
        value = payload.get(key)
        if isinstance(value, bool):
            return value
    pagination = payload.get("pagination")
    if isinstance(pagination, dict):
        total_pages = pagination.get("totalPages") or pagination.get("total_pages")
        if total_pages is not None:
            try:
                return page < int(str(total_pages))
            except ValueError:
                return False
    total_pages = payload.get("totalPages") or payload.get("total_pages")
    if total_pages is not None:
        try:
            return page < int(str(total_pages))
        except ValueError:
            return False
    return True


def run_cityspark_live_sandbox(
    session: Session,
    settings: Settings,
    values: dict[str, object] | None,
    requested_by: str | None,
    http_client: ProviderJsonClient | None = None,
) -> ApiFeedRun:
    if not settings.cityspark_live_calls_enabled:
        raise ValueError("CitySpark live calls are off. Enable the sandbox flag first.")
    api_key = settings.cityspark_api_key.strip()
    if not api_key:
        raise ValueError("CitySpark credentials are missing.")
    if not settings.cityspark_portal_script_id.strip():
        raise ValueError("CitySpark portalScriptId is missing.")

    client = http_client or ProviderHttpClient()
    body = cityspark_sandbox_body(settings, values)
    limit = normalized_cityspark_limit(settings, body.pop("limit"))
    page_size = normalized_cityspark_page_size(settings, body["pageSize"])
    page = positive_int(body["page"], 1)
    endpoint = f"{settings.cityspark_base_url.rstrip('/')}/v2/event/search"
    records: list[dict[str, Any]] = []
    preview = cityspark_request_preview(settings, values)

    while len(records) < limit:
        request_body = dict(body)
        request_body["page"] = page
        result = client.post_json(
            endpoint,
            json_body=request_body,
            headers={"X-API-Key": api_key, "Content-Type": "application/json"},
            secrets=(api_key, settings.cityspark_portal_script_id.strip()),
        )
        if not result.ok:
            return create_failed_api_feed_run(
                session,
                settings,
                CITYSPARK_PROVIDER_KEY,
                LIVE_SANDBOX_RUN_MODE,
                requested_by,
                provider_error_message(result),
                request_preview=preview,
                parameters={"body": redacted_cityspark_body(request_body)},
                notes=(
                    "CitySpark live sandbox request failed before records were "
                    "staged."
                ),
            )
        page_records = cityspark_records_from_payload(result.json_data)
        if not page_records:
            break
        remaining = limit - len(records)
        records.extend(page_records[:remaining])
        if not has_next_page(result.json_data, page, page_size, len(page_records)):
            break
        page += 1

    safe_body = cityspark_sandbox_body(settings, values)
    return create_api_feed_run(
        session,
        settings,
        CITYSPARK_PROVIDER_KEY,
        records,
        run_mode=LIVE_SANDBOX_RUN_MODE,
        requested_by=requested_by,
        request_preview=preview,
        parameters={"body": redacted_cityspark_body(safe_body)},
        notes=(
            "CitySpark live sandbox records are staged for API Feed Review only; "
            "nothing is auto-approved or published."
        ),
    )
