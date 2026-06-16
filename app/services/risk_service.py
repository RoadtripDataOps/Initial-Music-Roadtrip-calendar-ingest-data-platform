import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from ipaddress import ip_address
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import (
    BlockedSubmitter,
    CalendarSource,
    SubmissionAttempt,
    TrustedSubmitter,
)

SOCIAL_PROFILE_DOMAINS = {
    "facebook.com",
    "instagram.com",
    "tiktok.com",
    "twitter.com",
    "x.com",
    "threads.net",
    "youtube.com",
}
ACCEPTED_CALENDAR_EXTENSIONS = {".ics", ".ical", ".html", ".htm", ""}


@dataclass(frozen=True)
class RiskAssessment:
    """Reusable submission risk score result."""

    risk_score: int
    risk_level: str
    risk_flags: list[str]

    @property
    def risk_flags_json(self) -> str:
        return json.dumps(self.risk_flags, ensure_ascii=True, sort_keys=True)


@dataclass(frozen=True)
class SubmissionRiskInput:
    """Input signals for public calendar URL submission scoring."""

    organization_name: str
    contact_email: str
    calendar_url: str
    permission_confirmed: bool
    honeypot_value: str | None
    form_rendered_at: datetime | None
    submitted_at: datetime
    submitted_ip_hash: str | None
    submitted_user_agent_hash: str | None
    settings: Settings
    submission_type: str = "submit-calendar"


def risk_level_for_score(score: int) -> str:
    """Map an integer score to the public risk-level buckets."""

    if score >= 80:
        return "blocked"
    if score >= 50:
        return "high"
    if score >= 20:
        return "medium"
    return "low"


def build_assessment(score: int, flags: list[str]) -> RiskAssessment:
    """Normalize score/flag output."""

    clamped = max(0, score)
    unique_flags = sorted(set(flags))
    return RiskAssessment(
        risk_score=clamped,
        risk_level=risk_level_for_score(clamped),
        risk_flags=unique_flags,
    )


def hash_signal(value: str | None, salt: str) -> str | None:
    """Hash submission metadata for lightweight local rate-limit tracking."""

    if not value:
        return None
    payload = f"{salt}:{value.strip().lower()}".encode()
    return hashlib.sha256(payload).hexdigest()


def email_domain(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    return email.rsplit("@", maxsplit=1)[-1].strip().lower() or None


def url_domain(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    return parsed.hostname.lower() if parsed.hostname else None


def canonicalize_url(url: str) -> str:
    """Canonicalize a source URL for duplicate detection."""

    parsed = urlparse(url)
    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith(("utm_", "fbclid", "gclid"))
    ]
    return urlunparse(
        (
            parsed.scheme.lower(),
            (parsed.hostname or "").lower(),
            parsed.path.rstrip("/") or "/",
            "",
            urlencode(sorted(query_pairs)),
            "",
        )
    )


def is_development(settings: Settings) -> bool:
    return settings.environment.strip().lower() in {
        "dev",
        "development",
        "local",
        "test",
    }


def private_or_local_url_flags(url: str, settings: Settings) -> list[str]:
    """Return dangerous URL flags without doing DNS/network lookups."""

    parsed = urlparse(url)
    flags: list[str] = []
    hostname = parsed.hostname
    if parsed.scheme not in {"http", "https"}:
        return ["invalid_url_scheme"]
    if hostname is None:
        return ["missing_url_hostname"]

    lowered = hostname.lower()
    if lowered == "169.254.169.254":
        return ["aws_metadata_ip_blocked", "dangerous_url"]
    is_local_demo = is_development(settings)
    if lowered == "localhost":
        if not is_local_demo:
            flags.extend(["localhost_url_blocked_in_production", "dangerous_url"])
        return flags

    try:
        parsed_ip = ip_address(lowered)
    except ValueError:
        return flags

    if (
        parsed_ip.is_private
        or parsed_ip.is_loopback
        or parsed_ip.is_link_local
        or parsed_ip.is_reserved
    ):
        if not is_local_demo:
            flags.extend(["private_network_url_blocked_in_production", "dangerous_url"])
    return flags


def social_profile_url_flag(url: str) -> bool:
    domain = url_domain(url)
    if domain is None:
        return False
    return any(
        domain == item or domain.endswith(f".{item}")
        for item in SOCIAL_PROFILE_DOMAINS
    )


def has_accepted_source_extension(url: str) -> bool:
    path = urlparse(url).path.lower()
    if not path or "/" == path:
        return True
    extension = "." + path.rsplit(".", maxsplit=1)[-1] if "." in path else ""
    return extension in ACCEPTED_CALENDAR_EXTENSIONS


def find_duplicate_source(
    session: Session,
    calendar_url: str,
) -> CalendarSource | None:
    """Return an existing source/claim with the same canonical URL."""

    canonical = canonicalize_url(calendar_url)
    sources = session.scalars(select(CalendarSource)).all()
    for source in sources:
        if canonicalize_url(source.calendar_url) == canonical:
            return source
    return None


def is_blocked_submission(
    session: Session,
    contact_email: str,
    calendar_url: str,
) -> bool:
    """Return whether email, email domain, or URL domain is blocked."""

    contact_domain = email_domain(contact_email)
    submitted_domain = url_domain(calendar_url)
    statement = select(BlockedSubmitter)
    for blocked in session.scalars(statement):
        if blocked.email and blocked.email.lower() == contact_email.lower():
            return True
        if blocked.email_domain and blocked.email_domain.lower() == contact_domain:
            return True
        if blocked.url_domain and blocked.url_domain.lower() == submitted_domain:
            return True
    return False


def is_trusted_submission(
    session: Session,
    contact_email: str,
    calendar_url: str,
) -> bool:
    """Return whether email, email domain, or URL domain is trusted."""

    contact_domain = email_domain(contact_email)
    submitted_domain = url_domain(calendar_url)
    statement = select(TrustedSubmitter)
    for trusted in session.scalars(statement):
        if trusted.email and trusted.email.lower() == contact_email.lower():
            return True
        if trusted.email_domain and trusted.email_domain.lower() == contact_domain:
            return True
        if trusted.url_domain and trusted.url_domain.lower() == submitted_domain:
            return True
    return False


def rate_limit_flags(
    session: Session,
    risk_input: SubmissionRiskInput,
) -> list[str]:
    """Return lightweight local rate-limit flags for recent attempts."""

    since_hour = risk_input.submitted_at - timedelta(hours=1)
    since_day = risk_input.submitted_at - timedelta(days=1)
    attempts_hour = list(
        session.scalars(
            select(SubmissionAttempt).where(SubmissionAttempt.created_at >= since_hour)
        ).all()
    )
    attempts_day = list(
        session.scalars(
            select(SubmissionAttempt).where(SubmissionAttempt.created_at >= since_day)
        ).all()
    )
    flags: list[str] = []

    matching_email = [
        attempt
        for attempt in attempts_day
        if attempt.contact_email
        and attempt.contact_email.lower() == risk_input.contact_email.lower()
    ]
    matching_ip = [
        attempt
        for attempt in attempts_hour
        if risk_input.submitted_ip_hash
        and attempt.ip_hash == risk_input.submitted_ip_hash
    ]
    matching_domain = [
        attempt
        for attempt in attempts_day
        if attempt.submitted_domain == url_domain(risk_input.calendar_url)
    ]
    matching_user_agent = [
        attempt
        for attempt in attempts_hour
        if risk_input.submitted_user_agent_hash
        and attempt.user_agent_hash == risk_input.submitted_user_agent_hash
    ]
    matching_route = [
        attempt
        for attempt in attempts_hour
        if attempt.submission_type == risk_input.submission_type
    ]

    if (
        len(matching_email)
        >= risk_input.settings.public_submit_rate_limit_per_email_per_day
    ):
        flags.append("rate_limit_email_day_exceeded")
    if len(matching_ip) >= risk_input.settings.public_submit_rate_limit_per_ip_per_hour:
        flags.append("rate_limit_ip_hour_exceeded")
    if (
        len(matching_domain)
        >= risk_input.settings.public_submit_rate_limit_per_domain_per_day
    ):
        flags.append("rate_limit_domain_day_exceeded")
    if (
        len(matching_route)
        >= risk_input.settings.public_submit_rate_limit_per_route_per_hour
    ):
        flags.append("rate_limit_route_hour_exceeded")
    if (
        len(matching_user_agent)
        >= risk_input.settings.public_submit_rate_limit_per_ip_per_hour * 2
    ):
        flags.append("rate_limit_user_agent_hour_exceeded")
    if (
        len(attempts_hour)
        >= risk_input.settings.public_submit_global_rate_limit_per_hour
    ):
        flags.append("rate_limit_global_hour_exceeded")

    if len(matching_email) >= 5 or len(matching_ip) >= 8 or len(matching_domain) >= 10:
        flags.append("too_many_recent_submissions")

    unrelated_domains = {
        attempt.submitted_domain
        for attempt in matching_email
        if attempt.submitted_domain
        and attempt.submitted_domain != url_domain(risk_input.calendar_url)
    }
    if len(unrelated_domains) >= 3:
        flags.append("same_email_many_unrelated_domains")

    invalid_from_ip = [
        attempt
        for attempt in matching_ip
        if attempt.was_invalid or "failed" in attempt.risk_flags_json
    ]
    if len(invalid_from_ip) >= 3:
        flags.append("repeated_failed_or_invalid_submissions")

    return flags


def score_calendar_submission(
    session: Session,
    risk_input: SubmissionRiskInput,
) -> tuple[RiskAssessment, CalendarSource | None]:
    """Score a public calendar URL submission."""

    score = 0
    flags: list[str] = []

    if risk_input.honeypot_value and risk_input.honeypot_value.strip():
        score += 85
        flags.append("honeypot_filled")

    if risk_input.form_rendered_at is not None:
        elapsed = (
            risk_input.submitted_at - risk_input.form_rendered_at
        ).total_seconds()
        if elapsed < risk_input.settings.minimum_form_seconds:
            score += 50
            flags.append("submitted_too_fast")

    if not risk_input.permission_confirmed:
        score += 80
        flags.append("authorization_missing")

    url_flags = private_or_local_url_flags(risk_input.calendar_url, risk_input.settings)
    if "invalid_url_scheme" in url_flags or "missing_url_hostname" in url_flags:
        score += 80
    if "dangerous_url" in url_flags:
        score += 80
    flags.extend(url_flags)

    parsed = urlparse(risk_input.calendar_url)
    query_keys = [
        key for key, _value in parse_qsl(parsed.query, keep_blank_values=True)
    ]
    if len(query_keys) >= 6:
        score += 10
        flags.append("many_tracking_or_query_parameters")

    if social_profile_url_flag(risk_input.calendar_url):
        score += 35
        flags.append("social_media_profile_url")

    if not has_accepted_source_extension(risk_input.calendar_url):
        score += 20
        flags.append("unaccepted_calendar_source_file_type")

    if not risk_input.calendar_url.lower().endswith((".ics", ".ical")):
        score += 5
        flags.append("source_type_unknown")

    duplicate_source = find_duplicate_source(session, risk_input.calendar_url)
    if duplicate_source is not None:
        score += 15
        flags.append("duplicate_calendar_url")

    if is_blocked_submission(
        session,
        risk_input.contact_email,
        risk_input.calendar_url,
    ):
        score += 80
        flags.append("blocked_submitter_or_domain")

    if is_trusted_submission(
        session,
        risk_input.contact_email,
        risk_input.calendar_url,
    ):
        score -= 20
        flags.append("trusted_submitter_or_domain")

    rate_flags = rate_limit_flags(session, risk_input)
    if any(flag.startswith("rate_limit_") for flag in rate_flags):
        score += 80
    if "too_many_recent_submissions" in rate_flags:
        score += 35
    if "same_email_many_unrelated_domains" in rate_flags:
        score += 25
    if "repeated_failed_or_invalid_submissions" in rate_flags:
        score += 25
    flags.extend(rate_flags)

    return build_assessment(score, flags), duplicate_source


def review_status_for_assessment(assessment: RiskAssessment) -> str:
    """Map risk level into the initial admin review state."""

    if assessment.risk_level == "blocked":
        return "blocked"
    if assessment.risk_level == "high":
        return "quarantined"
    return "pending_review"


def record_submission_attempt(
    session: Session,
    submission_type: str,
    risk_input: SubmissionRiskInput,
    assessment: RiskAssessment,
    was_invalid: bool = False,
) -> SubmissionAttempt:
    """Persist a lightweight local attempt record for rate-limit signals."""

    attempt = SubmissionAttempt(
        submission_type=submission_type,
        contact_email=risk_input.contact_email,
        submitted_domain=url_domain(risk_input.calendar_url),
        ip_hash=risk_input.submitted_ip_hash,
        user_agent_hash=risk_input.submitted_user_agent_hash,
        risk_score=assessment.risk_score,
        risk_level=assessment.risk_level,
        risk_flags_json=assessment.risk_flags_json,
        was_invalid=was_invalid,
    )
    session.add(attempt)
    session.commit()
    return attempt
