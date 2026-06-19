from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    CalendarSource,
    CalendarSourceSubmission,
    CrawlRun,
    MasterCalendarSource,
    SourceReviewStatus,
    TrustedSubmitter,
    utc_now,
)
from app.services.crawl_service import Fetcher, run_manual_crawl
from app.services.event_service import count_events_for_crawl_run
from app.services.risk_service import url_domain

CRAWL_FREQUENCIES = ["manual", "daily", "weekly", "biweekly", "monthly"]
CRAWL_INTERVALS = {
    "daily": timedelta(days=1),
    "weekly": timedelta(days=7),
    "biweekly": timedelta(days=14),
    "monthly": timedelta(days=30),
}


@dataclass(frozen=True)
class MasterSourceFilters:
    status: str | None = None
    review_status: str | None = None
    crawl_frequency: str | None = None
    city: str | None = None
    state: str | None = None
    region_or_market: str | None = None
    source_type: str | None = None
    organization: str | None = None
    last_crawl_status: str | None = None
    due_for_crawl: bool = False
    risk_level: str | None = None

    def as_query_string(self) -> str:
        values: dict[str, str] = {}
        for key, value in self.__dict__.items():
            if key == "due_for_crawl":
                if value:
                    values[key] = "1"
            elif value:
                values[key] = str(value)
        return urlencode(values)


@dataclass(frozen=True)
class MasterSourceCrawlMetadata:
    source: MasterCalendarSource
    organizations: list[str]
    submission_count: int
    last_crawl: CrawlRun | None
    last_crawl_status: str | None
    total_crawl_runs: int
    latest_event_count: int
    next_crawl_due_at: datetime | None
    is_due_for_crawl: bool
    is_crawlable: bool
    crawl_block_reason: str | None
    is_trusted: bool


@dataclass(frozen=True)
class BulkCrawlSkippedSource:
    source_id: int
    source_name: str
    reason: str


@dataclass(frozen=True)
class BulkCrawlAttemptResult:
    source_id: int
    source_name: str
    crawl_run_id: int
    status: str
    events_extracted: int


@dataclass
class BulkCrawlSummary:
    title: str
    selected_count: int
    attempted_count: int = 0
    skipped: list[BulkCrawlSkippedSource] = field(default_factory=list)
    attempts: list[BulkCrawlAttemptResult] = field(default_factory=list)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)

    @property
    def successful_count(self) -> int:
        return sum(result.status == "success" for result in self.attempts)

    @property
    def failed_count(self) -> int:
        return sum(result.status == "failure" for result in self.attempts)

    @property
    def events_extracted(self) -> int:
        return sum(result.events_extracted for result in self.attempts)


def normalize_crawl_frequency(value: str | None) -> str:
    cleaned = (value or "").strip().lower()
    return cleaned if cleaned in CRAWL_FREQUENCIES else "manual"


def as_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def next_crawl_due_at(
    frequency: str | None,
    last_crawl: CrawlRun | None,
) -> datetime | None:
    frequency = normalize_crawl_frequency(frequency)
    if frequency == "manual":
        return None
    if last_crawl is None:
        return utc_now()
    return as_utc_datetime(last_crawl.fetched_at) + CRAWL_INTERVALS[frequency]


def is_due_for_crawl(
    frequency: str | None,
    last_crawl: CrawlRun | None,
) -> bool:
    due_at = next_crawl_due_at(frequency, last_crawl)
    return due_at is not None and due_at <= utc_now()


def crawl_gate_reason(source: MasterCalendarSource) -> str | None:
    if source.status == "blocked" or source.review_status == "blocked":
        return "blocked"
    if source.review_status == "quarantined":
        return "quarantined"
    if source.status != "approved":
        return f"status={source.status}"
    if source.review_status != SourceReviewStatus.approved.value:
        return f"review_status={source.review_status}"
    return None


def latest_crawl_for_master(
    session: Session,
    source: MasterCalendarSource,
) -> CrawlRun | None:
    statement = (
        select(CrawlRun)
        .where(CrawlRun.source_url == source.canonical_url)
        .order_by(CrawlRun.fetched_at.desc(), CrawlRun.id.desc())
    )
    return session.scalars(statement).first()


def total_crawl_runs_for_master(session: Session, source: MasterCalendarSource) -> int:
    statement = select(func.count()).select_from(CrawlRun).where(
        CrawlRun.source_url == source.canonical_url
    )
    return int(session.scalar(statement) or 0)


def organizations_for_master(
    session: Session,
    source_id: int,
) -> list[str]:
    rows = session.scalars(
        select(CalendarSourceSubmission.organization_name)
        .where(CalendarSourceSubmission.master_calendar_source_id == source_id)
        .order_by(CalendarSourceSubmission.created_at.asc())
    ).all()
    return sorted({row for row in rows if row})


def is_trusted_master_source(
    session: Session,
    source: MasterCalendarSource,
    organizations: list[str],
) -> bool:
    trusted = list(session.scalars(select(TrustedSubmitter)).all())
    if not trusted:
        return False
    submissions = list(
        session.scalars(
            select(CalendarSourceSubmission).where(
                CalendarSourceSubmission.master_calendar_source_id == source.id
            )
        ).all()
    )
    source_domain = source.domain or url_domain(source.canonical_url)
    emails = {submission.contact_email.lower() for submission in submissions}
    email_domains = {
        email.split("@", 1)[1]
        for email in emails
        if "@" in email and len(email.split("@", 1)) == 2
    }
    orgs = {organization.lower() for organization in organizations}
    orgs.add(source.source_name.lower())
    for row in trusted:
        if row.url_domain and row.url_domain.lower() == (source_domain or "").lower():
            return True
        if row.email and row.email.lower() in emails:
            return True
        if row.email_domain and row.email_domain.lower() in email_domains:
            return True
        if row.organization_name and row.organization_name.lower() in orgs:
            return True
    return False


def metadata_for_master_source(
    session: Session,
    source: MasterCalendarSource,
) -> MasterSourceCrawlMetadata:
    organizations = organizations_for_master(session, source.id)
    latest_crawl = latest_crawl_for_master(session, source)
    latest_count = (
        count_events_for_crawl_run(session, latest_crawl.id) if latest_crawl else 0
    )
    due_at = next_crawl_due_at(source.crawl_frequency, latest_crawl)
    gate_reason = crawl_gate_reason(source)
    return MasterSourceCrawlMetadata(
        source=source,
        organizations=organizations,
        submission_count=len(organizations),
        last_crawl=latest_crawl,
        last_crawl_status=latest_crawl.status if latest_crawl else None,
        total_crawl_runs=total_crawl_runs_for_master(session, source),
        latest_event_count=latest_count,
        next_crawl_due_at=due_at,
        is_due_for_crawl=is_due_for_crawl(source.crawl_frequency, latest_crawl),
        is_crawlable=gate_reason is None,
        crawl_block_reason=gate_reason,
        is_trusted=is_trusted_master_source(session, source, organizations),
    )


def list_master_source_metadata(
    session: Session,
    filters: MasterSourceFilters | None = None,
) -> list[MasterSourceCrawlMetadata]:
    filters = filters or MasterSourceFilters()
    sources = list(session.scalars(select(MasterCalendarSource)).all())
    rows = [metadata_for_master_source(session, source) for source in sources]
    filtered: list[MasterSourceCrawlMetadata] = []
    for row in rows:
        source = row.source
        if filters.status and source.status != filters.status:
            continue
        if filters.review_status and source.review_status != filters.review_status:
            continue
        if filters.crawl_frequency and (
            normalize_crawl_frequency(source.crawl_frequency)
            != filters.crawl_frequency
        ):
            continue
        if filters.city and (source.city or "").lower() != filters.city.lower():
            continue
        if filters.state and (source.state or "").lower() != filters.state.lower():
            continue
        if filters.region_or_market and (
            source.region_or_market or ""
        ).lower() != filters.region_or_market.lower():
            continue
        if filters.source_type and source.source_type != filters.source_type:
            continue
        if filters.organization:
            haystack = " ".join(row.organizations + [source.source_name]).lower()
            if filters.organization.lower() not in haystack:
                continue
        if filters.last_crawl_status and row.last_crawl_status != (
            filters.last_crawl_status
        ):
            continue
        if filters.due_for_crawl and not row.is_due_for_crawl:
            continue
        if filters.risk_level and source.risk_level != filters.risk_level:
            continue
        filtered.append(row)
    return sorted(
        filtered,
        key=lambda row: (row.source.created_at, row.source.id),
        reverse=True,
    )


def crawl_queue_rows(session: Session) -> list[MasterSourceCrawlMetadata]:
    rows = list_master_source_metadata(session)
    return [
        row
        for row in rows
        if row.source.status in {"approved", "paused"}
        and row.source.review_status == SourceReviewStatus.approved.value
    ]


def due_crawl_rows(session: Session) -> list[MasterSourceCrawlMetadata]:
    return [row for row in crawl_queue_rows(session) if row.is_due_for_crawl]


def master_source_ids_for_import_batch(session: Session, batch_id: int) -> list[int]:
    rows = session.scalars(
        select(CalendarSourceSubmission.master_calendar_source_id).where(
            CalendarSourceSubmission.import_batch_id == batch_id
        )
    ).all()
    return sorted({int(row) for row in rows})


def first_submission_for_master(
    session: Session,
    source_id: int,
) -> CalendarSourceSubmission | None:
    return session.scalars(
        select(CalendarSourceSubmission)
        .where(CalendarSourceSubmission.master_calendar_source_id == source_id)
        .order_by(CalendarSourceSubmission.created_at.asc())
    ).first()


def get_or_create_calendar_source_for_master(
    session: Session,
    source: MasterCalendarSource,
) -> CalendarSource:
    existing = session.scalars(
        select(CalendarSource).where(
            CalendarSource.calendar_url == source.canonical_url,
            CalendarSource.submitted_via == "master-calendar-source",
        )
    ).first()
    submission = first_submission_for_master(session, source.id)
    contact_email = submission.contact_email if submission else "admin@localhost"
    if existing is None:
        existing = CalendarSource(
            organization_name=source.source_name,
            calendar_url=source.canonical_url,
            contact_email=contact_email,
            permission_confirmed=True,
            status="approved",
            review_status=SourceReviewStatus.approved.value,
            risk_score=source.risk_score,
            risk_level=source.risk_level,
            risk_flags_json=source.risk_flags_json,
            submitted_domain=source.domain or url_domain(source.canonical_url),
            claimed_source_id=source.id,
            submitted_via="master-calendar-source",
        )
    else:
        existing.organization_name = source.source_name
        existing.contact_email = contact_email
        existing.status = "approved"
        existing.review_status = SourceReviewStatus.approved.value
        existing.risk_score = source.risk_score
        existing.risk_level = source.risk_level
        existing.risk_flags_json = source.risk_flags_json
        existing.claimed_source_id = source.id
    session.add(existing)
    session.commit()
    session.refresh(existing)
    return existing


def run_bulk_crawl_for_master_ids(
    session: Session,
    source_ids: list[int],
    fetcher: Fetcher,
    title: str = "Bulk Crawl Summary",
) -> BulkCrawlSummary:
    unique_ids = list(dict.fromkeys(source_ids))
    summary = BulkCrawlSummary(title=title, selected_count=len(unique_ids))
    for source_id in unique_ids:
        source = session.get(MasterCalendarSource, source_id)
        if source is None:
            summary.skipped.append(
                BulkCrawlSkippedSource(
                    source_id=source_id,
                    source_name=f"#{source_id}",
                    reason="not found",
                )
            )
            continue
        gate_reason = crawl_gate_reason(source)
        if gate_reason is not None:
            summary.skipped.append(
                BulkCrawlSkippedSource(
                    source_id=source.id,
                    source_name=source.source_name,
                    reason=gate_reason,
                )
            )
            continue
        calendar_source = get_or_create_calendar_source_for_master(session, source)
        crawl_run = run_manual_crawl(session, calendar_source.id, fetcher=fetcher)
        source.last_crawled_at = crawl_run.fetched_at
        session.add(source)
        session.commit()
        summary.attempted_count += 1
        summary.attempts.append(
            BulkCrawlAttemptResult(
                source_id=source.id,
                source_name=source.source_name,
                crawl_run_id=crawl_run.id,
                status=crawl_run.status,
                events_extracted=count_events_for_crawl_run(session, crawl_run.id),
            )
        )
    return summary


def update_selected_crawl_frequency(
    session: Session,
    source_ids: list[int],
    frequency: str,
) -> int:
    normalized = normalize_crawl_frequency(frequency)
    updated = 0
    for source_id in set(source_ids):
        source = session.get(MasterCalendarSource, source_id)
        if source is None:
            continue
        source.crawl_frequency = normalized
        session.add(source)
        updated += 1
    session.commit()
    return updated


def pause_selected_sources(session: Session, source_ids: list[int]) -> int:
    updated = 0
    for source_id in set(source_ids):
        source = session.get(MasterCalendarSource, source_id)
        if source is None or source.status == "blocked":
            continue
        source.status = "paused"
        session.add(source)
        updated += 1
    session.commit()
    return updated
