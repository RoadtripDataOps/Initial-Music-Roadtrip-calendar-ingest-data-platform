from __future__ import annotations

import json
import re
import socket
from dataclasses import dataclass
from datetime import timedelta
from ipaddress import ip_address
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlsplit, urlunsplit

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import (
    AdminAuditLog,
    ApiFeedRun,
    CalendarSource,
    CrawlRun,
    SourceReviewStatus,
    SubmissionAttempt,
    utc_now,
)
from app.services.risk_service import (
    RiskAssessment,
    build_assessment,
    hash_signal,
    url_domain,
)

REDACTED = "[REDACTED]"
SENSITIVE_KEY_PARTS = (
    "api-key",
    "apikey",
    "api_key",
    "authorization",
    "cookie",
    "password",
    "secret",
    "session",
    "token",
    "x-api-key",
)
SENSITIVE_QUERY_KEYS = {
    "access_token",
    "apikey",
    "api_key",
    "authorization",
    "client_secret",
    "cookie",
    "password",
    "refresh_token",
    "secret",
    "session",
    "token",
    "x-api-key",
}
ALLOWED_UPLOAD_EXTENSIONS = {".csv", ".xlsx"}
MACRO_OR_LEGACY_EXTENSIONS = {".xlsm", ".xltm", ".xlam", ".xls", ".xlsb"}
ALLOWED_CRAWL_CONTENT_TYPES = (
    "application/atom+xml",
    "application/ics",
    "application/json",
    "application/ld+json",
    "application/rss+xml",
    "application/xml",
    "text/calendar",
    "text/html",
    "text/plain",
    "text/xml",
)
BLOCKED_HOST_SUFFIXES = (".internal", ".intranet", ".lan", ".local")
AWS_METADATA_IP = "169.254.169.254"


class PublicUploadSecurityError(ValueError):
    """Raised when a public upload fails security hardening checks."""


class CrawlerSafetyError(ValueError):
    """Raised when a crawl URL fails SSRF/safety checks."""


@dataclass(frozen=True)
class TurnstileVerificationResult:
    success: bool
    reason: str | None = None


def request_ip(request: object) -> str | None:
    client = getattr(request, "client", None)
    return str(client.host) if client and client.host else None


def request_user_agent(request: object) -> str | None:
    headers = getattr(request, "headers", {})
    return str(headers.get("user-agent") or "") or None


def request_ip_hash(request: object, settings: Settings) -> str | None:
    return hash_signal(request_ip(request), settings.risk_hash_salt)


def request_user_agent_hash(request: object, settings: Settings) -> str | None:
    return hash_signal(request_user_agent(request), settings.risk_hash_salt)


def _normalized_sensitive_key(key: object) -> str:
    return str(key).strip().lower().replace("_", "-")


def _is_sensitive_key(key: object) -> bool:
    normalized = _normalized_sensitive_key(key)
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)


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
    """Redact common secret-bearing key-value text and URL query values."""

    redacted = _redact_url(value)
    pattern = re.compile(
        r"(?i)\b(api[-_]?key|apikey|token|secret|password|authorization|cookie|session)"
        r"(\s*[=:]\s*)([^\s,;&}]+)",
    )
    return pattern.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{REDACTED}",
        redacted,
    )


def redact_sensitive_payload(value: object) -> object:
    """Return a JSON-safe copy with secrets redacted."""

    if isinstance(value, dict):
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


def safe_json(value: object) -> str:
    return json.dumps(redact_sensitive_payload(value), default=str, sort_keys=True)


def neutralize_csv_formula(value: object | None) -> str:
    """Neutralize spreadsheet formulas for import previews/exports."""

    if value is None:
        return ""
    text = str(value).strip()
    if text.startswith(("=", "+", "@")):
        return f"'{text}"
    return text


def verify_turnstile_token(
    token: str,
    *,
    request_ip_value: str | None,
    settings: Settings,
    verifier: object | None = None,
) -> TurnstileVerificationResult:
    """Verify a Cloudflare Turnstile token when bot protection is enabled."""

    if not settings.turnstile_enabled:
        return TurnstileVerificationResult(True)
    if not token.strip():
        return TurnstileVerificationResult(False, "turnstile_token_missing")
    if not settings.turnstile_secret_key:
        return TurnstileVerificationResult(False, "turnstile_secret_missing")
    if callable(verifier):
        try:
            verified = bool(verifier(token, request_ip_value))
        except Exception:
            return TurnstileVerificationResult(False, "turnstile_verifier_error")
        return TurnstileVerificationResult(
            verified,
            None if verified else "turnstile_token_invalid",
        )

    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.post(
                settings.turnstile_verify_url,
                data={
                    "secret": settings.turnstile_secret_key,
                    "response": token,
                    "remoteip": request_ip_value or "",
                },
            )
            payload = response.json()
    except (httpx.HTTPError, ValueError):
        return TurnstileVerificationResult(False, "turnstile_verify_failed")

    success = bool(payload.get("success"))
    return TurnstileVerificationResult(
        success,
        None if success else "turnstile_token_invalid",
    )


def public_rate_limit_assessment(
    session: Session,
    *,
    settings: Settings,
    route: str,
    contact_email: str | None,
    submitted_url: str | None,
    ip_hash: str | None,
    user_agent_hash: str | None,
) -> RiskAssessment:
    """Score public submission attempts against local rate-limit windows."""

    now = utc_now()
    since_hour = now - timedelta(hours=1)
    since_day = now - timedelta(days=1)
    attempts_hour = list(
        session.scalars(
            select(SubmissionAttempt).where(SubmissionAttempt.created_at >= since_hour),
        ).all(),
    )
    attempts_day = list(
        session.scalars(
            select(SubmissionAttempt).where(SubmissionAttempt.created_at >= since_day),
        ).all(),
    )
    domain = url_domain(submitted_url)
    normalized_email = (contact_email or "").strip().lower()
    flags: list[str] = []

    if (
        ip_hash
        and len([attempt for attempt in attempts_hour if attempt.ip_hash == ip_hash])
        >= settings.public_submit_rate_limit_per_ip_per_hour
    ):
        flags.append("rate_limit_ip_hour_exceeded")
    if (
        normalized_email
        and len(
            [
                attempt
                for attempt in attempts_day
                if (attempt.contact_email or "").lower() == normalized_email
            ],
        )
        >= settings.public_submit_rate_limit_per_email_per_day
    ):
        flags.append("rate_limit_email_day_exceeded")
    if (
        domain
        and len(
            [
                attempt
                for attempt in attempts_day
                if attempt.submitted_domain == domain
            ],
        )
        >= settings.public_submit_rate_limit_per_domain_per_day
    ):
        flags.append("rate_limit_domain_day_exceeded")
    if (
        route
        and len(
            [
                attempt
                for attempt in attempts_hour
                if attempt.submission_type == route
            ],
        )
        >= settings.public_submit_rate_limit_per_route_per_hour
    ):
        flags.append("rate_limit_route_hour_exceeded")
    if (
        user_agent_hash
        and len(
            [
                attempt
                for attempt in attempts_hour
                if attempt.user_agent_hash == user_agent_hash
            ],
        )
        >= settings.public_submit_rate_limit_per_ip_per_hour * 2
    ):
        flags.append("rate_limit_user_agent_hour_exceeded")
    if len(attempts_hour) >= settings.public_submit_global_rate_limit_per_hour:
        flags.append("rate_limit_global_hour_exceeded")

    return build_assessment(80 if flags else 0, flags)


def combine_security_assessments(*assessments: RiskAssessment | None) -> RiskAssessment:
    score = 0
    flags: list[str] = []
    for assessment in assessments:
        if assessment is None:
            continue
        score += assessment.risk_score
        flags.extend(assessment.risk_flags)
    return build_assessment(score, flags)


def record_public_submission_attempt(
    session: Session,
    *,
    submission_type: str,
    contact_email: str | None,
    submitted_url: str | None,
    ip_hash: str | None,
    user_agent_hash: str | None,
    assessment: RiskAssessment,
    was_invalid: bool,
) -> SubmissionAttempt:
    attempt = SubmissionAttempt(
        submission_type=submission_type,
        contact_email=contact_email,
        submitted_domain=url_domain(submitted_url),
        ip_hash=ip_hash,
        user_agent_hash=user_agent_hash,
        risk_score=assessment.risk_score,
        risk_level=assessment.risk_level,
        risk_flags_json=assessment.risk_flags_json,
        was_invalid=was_invalid,
    )
    session.add(attempt)
    session.commit()
    session.refresh(attempt)
    return attempt


def validate_public_upload_file(
    filename: str | None,
    content: bytes,
    settings: Settings,
) -> None:
    """Validate public upload size and extension before parsing."""

    if not content:
        raise PublicUploadSecurityError("Uploaded file is empty.")
    safe_name = (filename or "").lower()
    extension = f".{safe_name.rsplit('.', maxsplit=1)[-1]}" if "." in safe_name else ""
    if extension in MACRO_OR_LEGACY_EXTENSIONS:
        raise PublicUploadSecurityError(
            "Macro-enabled or legacy workbooks are not accepted.",
        )
    if extension not in ALLOWED_UPLOAD_EXTENSIONS:
        raise PublicUploadSecurityError("Unsupported file type. Upload CSV or XLSX.")
    max_bytes = settings.public_file_upload_max_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise PublicUploadSecurityError("Uploaded file exceeds the public size limit.")


def validate_public_upload_row_count(row_count: int, settings: Settings) -> None:
    if row_count > settings.public_file_upload_max_rows:
        raise PublicUploadSecurityError("Uploaded file has too many rows.")


def _is_development(settings: Settings) -> bool:
    return settings.environment.strip().lower() in {
        "dev",
        "development",
        "local",
        "test",
    }


def _is_internal_hostname(hostname: str) -> bool:
    lowered = hostname.lower()
    if lowered in {"localhost", "localhost.localdomain"}:
        return True
    if lowered.endswith(BLOCKED_HOST_SUFFIXES):
        return True
    return "." not in lowered


def _ip_safety_flags(host_value: str, settings: Settings) -> list[str]:
    flags: list[str] = []
    try:
        parsed_ip = ip_address(host_value)
    except ValueError:
        return flags

    if str(parsed_ip) == AWS_METADATA_IP:
        return ["aws_metadata_ip_blocked", "dangerous_url"]
    if parsed_ip.is_loopback:
        if not _is_development(settings):
            flags.extend(["localhost_url_blocked_in_production", "dangerous_url"])
        return flags
    if (
        parsed_ip.is_private
        or parsed_ip.is_link_local
        or parsed_ip.is_reserved
        or parsed_ip.is_multicast
    ):
        if not _is_development(settings):
            flags.extend(["private_network_url_blocked_in_production", "dangerous_url"])
        return flags
    return flags


def _resolved_addresses(hostname: str) -> set[str]:
    results = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    return {str(result[4][0]) for result in results}


def url_safety_flags(
    url: str,
    settings: Settings,
    *,
    resolve_dns: bool | None = None,
) -> list[str]:
    """Return SSRF/crawler safety flags for a candidate URL."""

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return ["non_http_url_scheme_blocked", "dangerous_url"]
    if not parsed.hostname:
        return ["missing_url_hostname", "dangerous_url"]

    hostname = parsed.hostname.strip().lower()
    flags = _ip_safety_flags(hostname, settings)
    if flags:
        return flags
    if _is_internal_hostname(hostname):
        if not (_is_development(settings) and hostname.startswith("localhost")):
            return ["internal_hostname_blocked", "dangerous_url"]
        return []

    should_resolve = (
        settings.crawler_dns_resolution_enabled
        if resolve_dns is None
        else resolve_dns
    )
    if should_resolve:
        try:
            addresses = _resolved_addresses(hostname)
        except OSError:
            return ["dns_resolution_failed", "dangerous_url"]
        for address in addresses:
            resolved_flags = _ip_safety_flags(address, settings)
            if resolved_flags:
                return ["dns_resolved_private_address", *resolved_flags]
    return []


def assert_safe_crawl_url(url: str, settings: Settings) -> None:
    flags = url_safety_flags(
        url,
        settings,
        resolve_dns=settings.is_production or settings.crawler_dns_resolution_enabled,
    )
    if flags:
        raise CrawlerSafetyError(f"Crawler safety blocked URL: {', '.join(flags)}")


def safe_redirect_target(
    base_url: str,
    location: str,
    settings: Settings,
) -> str:
    target = urljoin(base_url, location)
    assert_safe_crawl_url(target, settings)
    return target


def log_admin_action(
    session: Session,
    *,
    settings: Settings,
    request: object,
    actor_username: str | None,
    action: str,
    target_type: str | None = None,
    target_id: object | None = None,
    metadata: dict[str, object] | None = None,
) -> AdminAuditLog:
    entry = AdminAuditLog(
        actor_username=actor_username,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        ip_hash=request_ip_hash(request, settings),
        user_agent_hash=request_user_agent_hash(request, settings),
        metadata_json=safe_json(metadata or {}),
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


def admin_login_rate_limited(
    session: Session,
    *,
    settings: Settings,
    request: object,
) -> bool:
    ip_hash = request_ip_hash(request, settings)
    if not ip_hash:
        return False
    since = utc_now() - timedelta(hours=1)
    count = int(
        session.scalar(
            select(func.count(AdminAuditLog.id)).where(
                AdminAuditLog.action == "login_failure",
                AdminAuditLog.ip_hash == ip_hash,
                AdminAuditLog.created_at >= since,
            ),
        )
        or 0,
    )
    return count >= settings.admin_login_rate_limit_per_ip_per_hour


def list_recent_admin_audit_logs(
    session: Session,
    *,
    limit: int = 25,
) -> list[AdminAuditLog]:
    return list(
        session.scalars(
            select(AdminAuditLog)
            .order_by(AdminAuditLog.created_at.desc(), AdminAuditLog.id.desc())
            .limit(limit),
        ).all(),
    )


def _attempts_with_flag(session: Session, flag_text: str) -> int:
    return int(
        session.scalar(
            select(func.count(SubmissionAttempt.id)).where(
                SubmissionAttempt.risk_flags_json.contains(flag_text),
            ),
        )
        or 0,
    )


def security_dashboard_context(session: Session) -> dict[str, Any]:
    suspicious_count = int(
        session.scalar(
            select(func.count(CalendarSource.id)).where(
                (CalendarSource.risk_level.in_(["high", "blocked"]))
                | (
                    CalendarSource.review_status.in_(
                        [
                            SourceReviewStatus.quarantined.value,
                            SourceReviewStatus.blocked.value,
                            SourceReviewStatus.rejected.value,
                        ],
                    )
                ),
            ),
        )
        or 0,
    )
    blocked_attempts = int(
        session.scalar(
            select(func.count(SubmissionAttempt.id)).where(
                SubmissionAttempt.risk_level == "blocked",
            ),
        )
        or 0,
    )
    failed_logins = int(
        session.scalar(
            select(func.count(AdminAuditLog.id)).where(
                AdminAuditLog.action == "login_failure",
            ),
        )
        or 0,
    )
    crawler_safety_blocks = int(
        session.scalar(
            select(func.count(CrawlRun.id)).where(
                CrawlRun.error_message.contains("Crawler safety blocked"),
            ),
        )
        or 0,
    )
    provider_live_blocks = int(
        session.scalar(
            select(func.count(ApiFeedRun.id)).where(
                ApiFeedRun.error_message.contains("Live calls"),
            ),
        )
        or 0,
    )
    return {
        "suspicious_submissions": suspicious_count,
        "blocked_submissions": blocked_attempts,
        "failed_logins": failed_logins,
        "rate_limit_hits": _attempts_with_flag(session, "rate_limit_"),
        "turnstile_failures": _attempts_with_flag(session, "turnstile_"),
        "crawler_safety_blocks": crawler_safety_blocks,
        "provider_live_call_blocks": provider_live_blocks,
        "recent_admin_actions": list_recent_admin_audit_logs(session),
        "secrets_redaction_status": "active",
    }
