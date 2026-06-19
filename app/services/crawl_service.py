from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urljoin

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings, get_settings
from app.db.models import (
    CalendarSource,
    CrawlRun,
    CrawlRunStatus,
    SourceReviewStatus,
    SourceStatus,
)
from app.services.security_service import (
    ALLOWED_CRAWL_CONTENT_TYPES,
    CrawlerSafetyError,
    assert_safe_crawl_url,
)


class SourceNotFoundError(Exception):
    """Raised when a crawl is requested for an unknown source."""


class SourceNotApprovedError(Exception):
    """Raised when a crawl is requested before source approval."""


@dataclass(frozen=True)
class FetchResult:
    """Raw fetch result captured before persistence."""

    http_status_code: int | None
    content_type: str | None
    raw_response_body: str | None
    error_message: str | None = None
    final_url: str | None = None


class Fetcher(Protocol):
    def __call__(self, url: str) -> FetchResult:
        """Fetch a calendar URL and return raw response details."""


def fetch_calendar_url(
    url: str,
    settings: Settings | None = None,
) -> FetchResult:
    """Fetch a submitted calendar URL without extracting event data."""

    active_settings = settings or get_settings()
    try:
        assert_safe_crawl_url(url, active_settings)
        with httpx.Client(
            follow_redirects=False,
            timeout=active_settings.crawler_timeout_seconds,
            headers={"User-Agent": "MusicRoadtripCalendarIngestPOC/0.1"},
        ) as client:
            current_url = url
            response: httpx.Response | None = None
            for _redirect_index in range(active_settings.crawler_max_redirects + 1):
                response = client.get(current_url)
                if response.status_code not in {301, 302, 303, 307, 308}:
                    break
                location = response.headers.get("location")
                if not location:
                    break
                current_url = urljoin(current_url, location)
                assert_safe_crawl_url(current_url, active_settings)
            else:
                return FetchResult(
                    http_status_code=None,
                    content_type=None,
                    raw_response_body=None,
                    error_message="Crawler redirect limit exceeded.",
                    final_url=current_url,
                )
    except httpx.HTTPError as exc:
        return FetchResult(
            http_status_code=None,
            content_type=None,
            raw_response_body=None,
            error_message=str(exc),
        )
    except CrawlerSafetyError as exc:
        return FetchResult(
            http_status_code=None,
            content_type=None,
            raw_response_body=None,
            error_message=str(exc),
        )

    if response is None:
        return FetchResult(
            http_status_code=None,
            content_type=None,
            raw_response_body=None,
            error_message="Source fetch did not return a response.",
        )
    content_type = response.headers.get("content-type")
    if content_type:
        normalized_content_type = content_type.split(";", maxsplit=1)[0].lower()
        if normalized_content_type not in ALLOWED_CRAWL_CONTENT_TYPES:
            return FetchResult(
                http_status_code=response.status_code,
                content_type=content_type,
                raw_response_body=None,
                error_message=f"Unsupported response content type: {content_type}.",
                final_url=current_url,
            )
    if len(response.content) > active_settings.crawler_max_response_bytes:
        return FetchResult(
            http_status_code=response.status_code,
            content_type=content_type,
            raw_response_body=None,
            error_message="Crawler response size limit exceeded.",
            final_url=current_url,
        )
    return FetchResult(
        http_status_code=response.status_code,
        content_type=content_type,
        raw_response_body=response.text,
        error_message=None,
        final_url=current_url,
    )


def is_successful_fetch(result: FetchResult) -> bool:
    """Return whether a raw fetch result counts as a successful crawl."""

    return (
        result.error_message is None
        and result.http_status_code is not None
        and 200 <= result.http_status_code < 400
    )


def crawl_failure_message(result: FetchResult) -> str | None:
    """Return a stored failure message for exceptions or HTTP error statuses."""

    if result.error_message:
        return result.error_message
    if result.http_status_code is not None and result.http_status_code >= 400:
        return f"Source returned HTTP {result.http_status_code}."
    return None


def run_manual_crawl(
    session: Session,
    source_id: int,
    fetcher: Fetcher = fetch_calendar_url,
) -> CrawlRun:
    """Fetch an approved calendar source and persist the crawl attempt."""

    source = session.get(CalendarSource, source_id)
    if source is None:
        raise SourceNotFoundError(f"Calendar source {source_id} was not found.")
    if (
        source.status != SourceStatus.approved.value
        or source.review_status != SourceReviewStatus.approved.value
    ):
        raise SourceNotApprovedError("Only approved sources can be crawled.")

    result = fetcher(source.calendar_url)
    status = (
        CrawlRunStatus.success.value
        if is_successful_fetch(result)
        else CrawlRunStatus.failure.value
    )
    crawl_run = CrawlRun(
        source_id=source.id,
        source_url=source.calendar_url,
        final_url=result.final_url or source.calendar_url,
        http_status_code=result.http_status_code,
        content_type=result.content_type[:255] if result.content_type else None,
        raw_response_body=result.raw_response_body,
        status=status,
        error_message=crawl_failure_message(result),
    )
    session.add(crawl_run)
    session.commit()
    session.refresh(crawl_run)
    if crawl_run.status == CrawlRunStatus.success.value:
        from app.services.event_service import save_ics_events_for_crawl_run
        from app.services.extracted_event_service import persist_extraction_result
        from app.services.source_extraction_service import extract_source_content

        extraction = extract_source_content(
            source_url=crawl_run.source_url,
            content_type=crawl_run.content_type,
            raw_body=crawl_run.raw_response_body,
            source_type=source.submitted_via,
        )
        persist_extraction_result(session, crawl_run, extraction)
        if extraction.extractor_type == "ics":
            save_ics_events_for_crawl_run(session, crawl_run)
        session.refresh(crawl_run)
    from app.services.source_intelligence_service import update_profile_from_crawl_run

    update_profile_from_crawl_run(session, crawl_run)
    session.refresh(crawl_run)
    return crawl_run


def list_crawl_runs(session: Session) -> list[CrawlRun]:
    """Return crawl runs newest first."""

    statement = (
        select(CrawlRun)
        .options(selectinload(CrawlRun.source))
        .order_by(CrawlRun.fetched_at.desc(), CrawlRun.id.desc())
    )
    return list(session.scalars(statement).all())


def get_crawl_run(session: Session, crawl_run_id: int) -> CrawlRun | None:
    """Return one crawl run by ID."""

    statement = (
        select(CrawlRun)
        .options(selectinload(CrawlRun.source))
        .where(CrawlRun.id == crawl_run_id)
    )
    return session.scalars(statement).first()
