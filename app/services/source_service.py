import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    BlockedSubmitter,
    CalendarSource,
    SourceReviewStatus,
    SourceStatus,
    TrustedSubmitter,
    utc_now,
)
from app.models.source import CalendarSourceCreate
from app.services.risk_service import RiskAssessment, email_domain, url_domain


def create_calendar_source(
    session: Session,
    submission: CalendarSourceCreate,
    risk_assessment: RiskAssessment | None = None,
    review_status: SourceReviewStatus = SourceReviewStatus.pending_review,
    submitted_ip_hash: str | None = None,
    submitted_user_agent_hash: str | None = None,
    submitted_domain: str | None = None,
    claimed_source_id: int | None = None,
    form_rendered_at: datetime | None = None,
    submitted_via: str = "submit-calendar",
) -> CalendarSource:
    """Persist a submitted calendar source as pending review."""

    assessment = risk_assessment or RiskAssessment(
        risk_score=0,
        risk_level="low",
        risk_flags=[],
    )
    source = CalendarSource(
        organization_name=submission.organization_name,
        calendar_url=submission.calendar_url,
        contact_email=submission.contact_email,
        permission_confirmed=submission.permission_confirmed,
        status=SourceStatus.pending.value,
        risk_score=assessment.risk_score,
        risk_level=assessment.risk_level,
        risk_flags_json=assessment.risk_flags_json,
        review_status=review_status.value,
        submitted_ip_hash=submitted_ip_hash,
        submitted_user_agent_hash=submitted_user_agent_hash,
        submitted_domain=submitted_domain,
        claimed_source_id=claimed_source_id,
        form_rendered_at=form_rendered_at,
        submitted_via=submitted_via,
    )
    session.add(source)
    session.commit()
    session.refresh(source)
    return source


def list_calendar_sources(session: Session) -> list[CalendarSource]:
    """Return submitted sources newest first."""

    statement = select(CalendarSource).order_by(CalendarSource.created_at.desc())
    return list(session.scalars(statement).all())


def update_source_status(
    session: Session,
    source_id: int,
    status: SourceStatus,
) -> CalendarSource | None:
    """Set the admin status for one submitted source."""

    source = session.get(CalendarSource, source_id)
    if source is None:
        return None
    if status == SourceStatus.approved:
        if source.risk_level in {"high", "blocked"} or source.review_status in {
            SourceReviewStatus.quarantined.value,
            SourceReviewStatus.blocked.value,
            SourceReviewStatus.rejected.value,
        }:
            source.status = SourceStatus.pending.value
            source.review_notes = (
                "Suspicious submissions require review action approval."
            )
        else:
            source.status = SourceStatus.approved.value
            source.review_status = SourceReviewStatus.approved.value
            source.reviewed_at = utc_now()
            source.reviewed_by = "admin"
    else:
        source.status = status.value
    session.add(source)
    session.commit()
    session.refresh(source)
    return source


def get_calendar_source(session: Session, source_id: int) -> CalendarSource | None:
    """Return a calendar source by ID."""

    return session.get(CalendarSource, source_id)


def list_suspicious_calendar_sources(session: Session) -> list[CalendarSource]:
    """Return public submissions that need suspicious-submission review."""

    statement = (
        select(CalendarSource)
        .where(
            (CalendarSource.risk_level.in_(["high", "blocked"]))
            | (
                CalendarSource.review_status.in_(
                    [
                        SourceReviewStatus.quarantined.value,
                        SourceReviewStatus.blocked.value,
                        SourceReviewStatus.rejected.value,
                    ]
                )
            )
        )
        .order_by(CalendarSource.created_at.desc())
    )
    return list(session.scalars(statement).all())


def review_calendar_source(
    session: Session,
    source_id: int,
    action: str,
    notes: str | None = None,
    reviewed_by: str = "admin",
) -> CalendarSource | None:
    """Apply a POC admin review action to a public submission."""

    source = session.get(CalendarSource, source_id)
    if source is None:
        return None

    if action == "approve":
        source.review_status = SourceReviewStatus.approved.value
        source.status = SourceStatus.approved.value
    elif action == "reject":
        source.review_status = SourceReviewStatus.rejected.value
        source.status = SourceStatus.pending.value
    elif action == "quarantine":
        source.review_status = SourceReviewStatus.quarantined.value
        source.status = SourceStatus.pending.value
    elif action == "block_email":
        session.add(
            BlockedSubmitter(
                email=source.contact_email.lower(),
                email_domain=email_domain(source.contact_email),
                reason=notes or "Blocked from suspicious submission review.",
            )
        )
        source.review_status = SourceReviewStatus.blocked.value
        source.status = SourceStatus.pending.value
    elif action == "block_domain":
        session.add(
            BlockedSubmitter(
                url_domain=url_domain(source.calendar_url),
                reason=notes or "Blocked from suspicious submission review.",
            )
        )
        source.review_status = SourceReviewStatus.blocked.value
        source.status = SourceStatus.pending.value
    elif action == "trust_submitter":
        session.add(
            TrustedSubmitter(
                organization_name=source.organization_name,
                email=source.contact_email.lower(),
                email_domain=email_domain(source.contact_email),
                notes=notes or "Trusted from suspicious submission review.",
            )
        )
        source.review_status = SourceReviewStatus.pending_review.value
    elif action == "trust_domain":
        session.add(
            TrustedSubmitter(
                organization_name=source.organization_name,
                url_domain=url_domain(source.calendar_url),
                notes=notes or "Trusted from suspicious submission review.",
            )
        )
        source.review_status = SourceReviewStatus.pending_review.value
    else:
        return None

    source.reviewed_at = utc_now()
    source.reviewed_by = reviewed_by
    if notes:
        source.review_notes = notes
    session.add(source)
    session.commit()
    session.refresh(source)
    return source


def risk_flags_for_display(source: CalendarSource) -> str:
    """Return comma-separated risk flags for simple admin display."""

    try:
        flags = json.loads(source.risk_flags_json)
    except json.JSONDecodeError:
        return ""
    if not isinstance(flags, list):
        return ""
    return ", ".join(str(flag) for flag in flags)
