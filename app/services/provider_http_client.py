from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

logger = logging.getLogger(__name__)
QueryParamValue = str | int | float | bool | None

REDACTED = "REDACTED"
SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "key",
        "token",
        "access_token",
        "authorization",
        "x-api-key",
        "portalScriptId",
    }
)


@dataclass(frozen=True)
class ProviderHttpResult:
    """Structured provider HTTP result with no credential values."""

    ok: bool
    status_code: int | None
    content_type: str | None
    json_data: object | None
    text_preview: str
    error_message: str | None = None


class ProviderJsonClient(Protocol):
    def get_json(
        self,
        url: str,
        *,
        params: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
        secrets: tuple[str, ...] = (),
    ) -> ProviderHttpResult: ...

    def post_json(
        self,
        url: str,
        *,
        json_body: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
        secrets: tuple[str, ...] = (),
    ) -> ProviderHttpResult: ...


def redact_secret_values(text: str, secrets: tuple[str, ...] = ()) -> str:
    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, REDACTED)
    return redacted


def redact_url(url: str, secrets: tuple[str, ...] = ()) -> str:
    parts = urlsplit(url)
    query_pairs = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key.lower() in SENSITIVE_KEYS:
            query_pairs.append((key, REDACTED))
        else:
            query_pairs.append((key, redact_secret_values(value, secrets)))
    redacted_query = urlencode(query_pairs, doseq=True)
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            redacted_query,
            parts.fragment,
        )
    )


def redact_headers(
    headers: dict[str, str] | None,
    secrets: tuple[str, ...] = (),
) -> dict[str, str]:
    redacted: dict[str, str] = {}
    for key, value in (headers or {}).items():
        if key.lower() in SENSITIVE_KEYS:
            redacted[key] = REDACTED
        else:
            redacted[key] = redact_secret_values(value, secrets)
    return redacted


def redact_json_value(value: object, secrets: tuple[str, ...] = ()) -> object:
    if isinstance(value, dict):
        return {
            str(key): (
                REDACTED
                if str(key) in SENSITIVE_KEYS or str(key).lower() in SENSITIVE_KEYS
                else redact_json_value(child, secrets)
            )
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [redact_json_value(item, secrets) for item in value]
    if isinstance(value, str):
        return redact_secret_values(value, secrets)
    return value


def query_params_for_httpx(
    params: dict[str, object] | None,
) -> dict[str, QueryParamValue] | None:
    if params is None:
        return None
    converted: dict[str, QueryParamValue] = {}
    for key, value in params.items():
        if value is None or isinstance(value, str | int | float | bool):
            converted[key] = value
        else:
            converted[key] = str(value)
    return converted


class ProviderHttpClient:
    """Small sync HTTP client for admin-triggered provider sandbox calls."""

    def __init__(self, timeout_seconds: float = 20.0, retries: int = 1) -> None:
        self.timeout_seconds = timeout_seconds
        self.retries = max(0, retries)

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
        secrets: tuple[str, ...] = (),
    ) -> ProviderHttpResult:
        return self._request_json(
            "GET",
            url,
            params=params,
            headers=headers,
            json_body=None,
            secrets=secrets,
        )

    def post_json(
        self,
        url: str,
        *,
        json_body: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
        secrets: tuple[str, ...] = (),
    ) -> ProviderHttpResult:
        return self._request_json(
            "POST",
            url,
            params=None,
            headers=headers,
            json_body=json_body,
            secrets=secrets,
        )

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, object] | None,
        headers: dict[str, str] | None,
        json_body: dict[str, object] | None,
        secrets: tuple[str, ...],
    ) -> ProviderHttpResult:
        redacted_url = redact_url(url, secrets)
        redacted_headers = redact_headers(headers, secrets)
        for attempt in range(self.retries + 1):
            logger.info(
                "provider_http_request method=%s url=%s headers=%s attempt=%s",
                method,
                redacted_url,
                redacted_headers,
                attempt + 1,
            )
            try:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.request(
                        method,
                        url,
                        params=query_params_for_httpx(params),
                        headers=headers,
                        json=json_body,
                    )
            except httpx.HTTPError as exc:
                message = f"{exc.__class__.__name__} while contacting provider"
                if attempt >= self.retries:
                    return ProviderHttpResult(
                        ok=False,
                        status_code=None,
                        content_type=None,
                        json_data=None,
                        text_preview="",
                        error_message=message,
                    )
                continue

            content_type = response.headers.get("content-type")
            text_preview = redact_secret_values(response.text[:2000], secrets)
            if response.status_code in {429} or 500 <= response.status_code < 600:
                if attempt < self.retries:
                    continue
            if response.status_code >= 400:
                return ProviderHttpResult(
                    ok=False,
                    status_code=response.status_code,
                    content_type=content_type,
                    json_data=None,
                    text_preview=text_preview,
                    error_message=f"Provider returned HTTP {response.status_code}",
                )
            try:
                json_data: object = response.json()
            except ValueError:
                return ProviderHttpResult(
                    ok=False,
                    status_code=response.status_code,
                    content_type=content_type,
                    json_data=None,
                    text_preview=text_preview,
                    error_message="Provider response was not valid JSON.",
                )
            return ProviderHttpResult(
                ok=True,
                status_code=response.status_code,
                content_type=content_type,
                json_data=json_data,
                text_preview=text_preview,
            )

        return ProviderHttpResult(
            ok=False,
            status_code=None,
            content_type=None,
            json_data=None,
            text_preview="",
            error_message="Provider request failed after retries.",
        )
