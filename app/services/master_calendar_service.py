import hashlib
import json
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    CalendarSourceSubmission,
    MasterCalendarSource,
    SourceReviewStatus,
    utc_now,
)
from app.services.risk_service import RiskAssessment, canonicalize_url, url_domain


@dataclass(frozen=True)
class CalendarSourcePayload:
    """Normalized public/batch calendar source submission fields."""

    organization_name: str
    contact_name: str | None
    contact_email: str
    calendar_name: str | None
    calendar_url: str
    source_type: str | None = None
    expected_category: str | None = None
    venue_name: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    region_or_market: str | None = None
    crawl_frequency: str | None = None
    authorization_confirmed: bool = False
    notes: str | None = None
    import_batch_id: int | None = None
    raw_row_json: str | None = None


def canonical_url_hash(canonical_url: str) -> str:
    """Return deterministic hash for a canonical calendar URL."""

    return hashlib.sha256(canonical_url.encode()).hexdigest()


def canonicalize_calendar_url(url: str) -> tuple[str, str]:
    """Return canonical URL plus deterministic hash."""

    canonical = canonicalize_url(url)
    return canonical, canonical_url_hash(canonical)


def normalize_expected_category(value: str | None) -> str:
    return "Concert" if not value or not value.strip() else value.strip()


def get_master_by_hash(
    session: Session,
    url_hash: str,
) -> MasterCalendarSource | None:
    return session.scalars(
        select(MasterCalendarSource).where(
            MasterCalendarSource.canonical_url_hash == url_hash
        )
    ).first()


def create_or_attach_master_calendar_source(
    session: Session,
    payload: CalendarSourcePayload,
    assessment: RiskAssessment,
    review_status: str,
) -> tuple[MasterCalendarSource, CalendarSourceSubmission, bool]:
    """Create a canonical master source or attach a new submitter claim."""

    canonical_url, url_hash = canonicalize_calendar_url(payload.calendar_url)
    master = get_master_by_hash(session, url_hash)
    created = False
    now = utc_now()

    if master is None:
        master = MasterCalendarSource(
            canonical_url=canonical_url,
            canonical_url_hash=url_hash,
            original_url=payload.calendar_url,
            domain=url_domain(payload.calendar_url),
            source_name=payload.calendar_name
            or payload.organization_name
            or payload.calendar_url,
            source_type=(payload.source_type or "unknown").strip() or "unknown",
            expected_category=normalize_expected_category(payload.expected_category),
            venue_name=payload.venue_name,
            city=payload.city,
            state=payload.state,
            country=payload.country,
            region_or_market=payload.region_or_market,
            status="pending",
            review_status=review_status,
            risk_score=assessment.risk_score,
            risk_level=assessment.risk_level,
            risk_flags_json=assessment.risk_flags_json,
            crawl_frequency=payload.crawl_frequency,
            first_seen_at=now,
            last_seen_at=now,
            notes=payload.notes,
        )
        session.add(master)
        session.flush()
        created = True
    else:
        master.last_seen_at = now
        if assessment.risk_score > master.risk_score:
            master.risk_score = assessment.risk_score
            master.risk_level = assessment.risk_level
            master.risk_flags_json = assessment.risk_flags_json
        session.add(master)
        session.flush()

    submission = CalendarSourceSubmission(
        master_calendar_source_id=master.id,
        organization_name=payload.organization_name,
        contact_name=payload.contact_name,
        contact_email=payload.contact_email,
        original_url=payload.calendar_url,
        submitted_canonical_url=canonical_url,
        submitted_at=now,
        authorization_confirmed=payload.authorization_confirmed,
        risk_score=assessment.risk_score,
        risk_level=assessment.risk_level,
        risk_flags_json=assessment.risk_flags_json,
        review_status=review_status,
        notes=payload.notes,
        import_batch_id=payload.import_batch_id,
        raw_row_json=payload.raw_row_json,
    )
    session.add(submission)
    session.commit()
    session.refresh(master)
    session.refresh(submission)
    return master, submission, created


def list_master_calendar_sources(session: Session) -> list[MasterCalendarSource]:
    statement = select(MasterCalendarSource).order_by(
        MasterCalendarSource.created_at.desc(),
        MasterCalendarSource.id.desc(),
    )
    return list(session.scalars(statement).all())


def get_master_calendar_source(
    session: Session,
    source_id: int,
) -> MasterCalendarSource | None:
    return session.get(MasterCalendarSource, source_id)


def list_master_submissions(
    session: Session,
    source_id: int,
) -> list[CalendarSourceSubmission]:
    statement = (
        select(CalendarSourceSubmission)
        .where(CalendarSourceSubmission.master_calendar_source_id == source_id)
        .order_by(CalendarSourceSubmission.created_at.desc())
    )
    return list(session.scalars(statement).all())


def count_master_submissions(session: Session, source_id: int) -> int:
    statement = select(func.count()).select_from(CalendarSourceSubmission).where(
        CalendarSourceSubmission.master_calendar_source_id == source_id
    )
    return int(session.scalar(statement) or 0)


def master_submission_counts(session: Session) -> dict[int, int]:
    rows = session.execute(
        select(
            CalendarSourceSubmission.master_calendar_source_id,
            func.count(CalendarSourceSubmission.id),
        ).group_by(CalendarSourceSubmission.master_calendar_source_id)
    )
    return {int(source_id): int(count) for source_id, count in rows}


def update_master_status(
    session: Session,
    source_id: int,
    action: str,
) -> MasterCalendarSource | None:
    master = session.get(MasterCalendarSource, source_id)
    if master is None:
        return None

    if action == "approve":
        master.status = "approved"
        master.review_status = SourceReviewStatus.approved.value
    elif action == "pause":
        master.status = "paused"
    elif action == "block":
        master.status = "blocked"
        master.review_status = SourceReviewStatus.blocked.value
    else:
        return None
    session.add(master)
    session.commit()
    session.refresh(master)
    return master


def risk_flags_for_json(flags: list[str]) -> str:
    return json.dumps(sorted(set(flags)), ensure_ascii=True)
