from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import ApiFeedRun
from app.services.api_feed_service import (
    create_api_feed_run,
    create_failed_api_feed_run,
    extract_json_records,
)
from app.services.provider_http_client import (
    REDACTED,
    ProviderHttpClient,
    ProviderHttpResult,
    ProviderJsonClient,
    redact_url,
)

LIVE_SANDBOX_RUN_MODE = "live_api_sandbox"
JAMBASE_SUPPORTED_PARAMS = frozenset(
    {
        "eventType",
        "eventDateFrom",
        "eventDateTo",
        "geoCityName",
        "geoCityId",
        "geoStateIso",
        "geoCountryIso2",
        "geoLatitude",
        "geoLongitude",
        "geoRadiusAmount",
        "geoRadiusUnits",
        "genreSlug",
        "artistName",
        "artistId",
        "venueName",
        "venueId",
        "eventDataSource",
        "dateModifiedFrom",
        "datePublishedFrom",
        "expandExternalIdentifiers",
        "expandArtistSameAs",
        "excludeEventPerformers",
    }
)


@dataclass(frozen=True)
class JambaseSandboxContext:
    provider_key: str
    live_calls_enabled: bool
    credential_status: str
    max_events: int
    request_preview: dict[str, Any]
    default_values: dict[str, Any]
    disabled_reason: str | None


def normalized_jambase_limit(settings: Settings, value: object | None) -> int:
    requested = positive_int(value, settings.jambase_sandbox_max_events)
    return min(max(1, requested), max(1, settings.jambase_sandbox_max_events))


def normalized_jambase_per_page(settings: Settings, value: object | None) -> int:
    requested = positive_int(value, settings.jambase_default_per_page)
    return min(max(1, requested), 100)


def positive_int(value: object | None, default: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(str(value).strip())
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def clean_parameter(value: object | None) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def jambase_sandbox_parameters(
    settings: Settings,
    values: dict[str, object] | None = None,
) -> dict[str, object]:
    raw = values or {}
    params: dict[str, object] = {
        "eventType": clean_parameter(raw.get("eventType")) or "concerts",
        "perPage": normalized_jambase_per_page(settings, raw.get("perPage")),
        "page": positive_int(raw.get("page"), 1),
        "sort": "eventDate",
    }
    for key in JAMBASE_SUPPORTED_PARAMS:
        if key in {"eventType"}:
            continue
        value = clean_parameter(raw.get(key))
        if value is not None:
            params[key] = value
    params["limit"] = normalized_jambase_limit(settings, raw.get("limit"))
    return params


def jambase_request_preview(
    settings: Settings,
    values: dict[str, object] | None = None,
) -> dict[str, Any]:
    parameters = jambase_sandbox_parameters(settings, values)
    query_params = dict(parameters)
    query_params["apikey"] = REDACTED
    endpoint = f"{settings.jambase_base_url.rstrip('/')}/events"
    return {
        "method": "GET",
        "url": f"{endpoint}?{urlencode(query_params)}",
        "headers": {"Accept": "application/json"},
        "parameters": redacted_parameters(parameters),
    }


def redacted_parameters(parameters: dict[str, object]) -> dict[str, object]:
    redacted = dict(parameters)
    if "apikey" in redacted:
        redacted["apikey"] = REDACTED
    return redacted


def jambase_sandbox_context(settings: Settings) -> JambaseSandboxContext:
    credentials_configured = bool(settings.jambase_api_key.strip())
    disabled_reason = None
    if not settings.jambase_live_calls_enabled:
        disabled_reason = (
            "Set JAMBASE_LIVE_CALLS_ENABLED=true to enable sandbox requests."
        )
    elif not credentials_configured:
        disabled_reason = "Set JAMBASE_API_KEY to enable sandbox requests."
    return JambaseSandboxContext(
        provider_key="jambase",
        live_calls_enabled=settings.jambase_live_calls_enabled,
        credential_status=(
            "Credentials Configured"
            if credentials_configured
            else "Credentials Missing"
        ),
        max_events=max(1, settings.jambase_sandbox_max_events),
        request_preview=jambase_request_preview(settings),
        default_values=jambase_sandbox_parameters(settings),
        disabled_reason=disabled_reason,
    )


def jambase_records_from_payload(payload: object) -> list[dict[str, Any]]:
    return extract_json_records(payload)


def has_next_page(payload: object, page: int, per_page: int, record_count: int) -> bool:
    if record_count < per_page:
        return False
    if not isinstance(payload, dict):
        return False
    next_page = payload.get("nextPage") or payload.get("next_page")
    if next_page:
        return True
    pagination = payload.get("pagination")
    if isinstance(pagination, dict):
        has_more = pagination.get("hasMore") or pagination.get("has_more")
        if isinstance(has_more, bool):
            return has_more
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


def provider_error_message(result: ProviderHttpResult) -> str:
    if result.error_message:
        return result.error_message
    if result.status_code:
        return f"Provider returned HTTP {result.status_code}"
    return "Provider request failed."


def run_jambase_live_sandbox(
    session: Session,
    settings: Settings,
    values: dict[str, object] | None,
    requested_by: str | None,
    http_client: ProviderJsonClient | None = None,
) -> ApiFeedRun:
    if not settings.jambase_live_calls_enabled:
        raise ValueError("JamBase live calls are off. Enable the sandbox flag first.")
    api_key = settings.jambase_api_key.strip()
    if not api_key:
        raise ValueError("JamBase credentials are missing.")

    client = http_client or ProviderHttpClient()
    parameters = jambase_sandbox_parameters(settings, values)
    limit = positive_int(parameters.pop("limit"), settings.jambase_sandbox_max_events)
    per_page = positive_int(parameters["perPage"], settings.jambase_default_per_page)
    page = positive_int(parameters["page"], 1)
    endpoint = f"{settings.jambase_base_url.rstrip('/')}/events"
    records: list[dict[str, Any]] = []
    preview = jambase_request_preview(settings, values)

    while len(records) < limit:
        request_params = dict(parameters)
        request_params["page"] = page
        request_params["apikey"] = api_key
        result = client.get_json(
            endpoint,
            params=request_params,
            headers={"Accept": "application/json"},
            secrets=(api_key,),
        )
        if not result.ok:
            return create_failed_api_feed_run(
                session,
                settings,
                "jambase",
                LIVE_SANDBOX_RUN_MODE,
                requested_by,
                provider_error_message(result),
                request_preview=preview,
                parameters=redacted_parameters({**request_params, "apikey": REDACTED}),
                notes="JamBase live sandbox request failed before records were staged.",
            )
        page_records = jambase_records_from_payload(result.json_data)
        if not page_records:
            break
        remaining = limit - len(records)
        records.extend(page_records[:remaining])
        if not has_next_page(result.json_data, page, per_page, len(page_records)):
            break
        page += 1

    safe_parameters = jambase_sandbox_parameters(settings, values)
    safe_parameters["apikey"] = REDACTED
    return create_api_feed_run(
        session,
        settings,
        "jambase",
        records,
        run_mode=LIVE_SANDBOX_RUN_MODE,
        requested_by=requested_by,
        request_preview={
            **preview,
            "url": redact_url(preview["url"], (api_key,)),
        },
        parameters=redacted_parameters(safe_parameters),
        notes=(
            "JamBase live sandbox records are staged for API Feed Review only; "
            "nothing is auto-approved or published."
        ),
    )
