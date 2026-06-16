from __future__ import annotations

from urllib.parse import urlparse

from app.services.extraction_types import (
    DiscoveredEventLink,
    EventCandidate,
    ExtractedImageCandidate,
    ExtractionResult,
)
from app.services.html_event_extractor import extract_html_events
from app.services.ics_service import parse_ics_events
from app.services.jsonld_event_extractor import extract_jsonld_events
from app.services.rss_atom_extractor import extract_rss_atom_events

__all__ = [
    "DiscoveredEventLink",
    "EventCandidate",
    "ExtractedImageCandidate",
    "ExtractionResult",
    "extract_source_content",
    "looks_like_ics",
    "looks_like_jsonld",
    "looks_like_rss_atom",
]


def extract_source_content(
    *,
    source_url: str,
    content_type: str | None,
    raw_body: str | None,
    source_type: str | None = None,
    explicit_extractor: str | None = None,
) -> ExtractionResult:
    """Select and run a safe extractor for one approved crawl response."""

    body = raw_body or ""
    if not body:
        return ExtractionResult(
            extractor_type="unsupported",
            status="unsupported",
            unsupported_reason="No response body was available for extraction.",
        )

    preferred = explicit_extractor or extractor_hint(
        source_url, content_type, body, source_type
    )
    if preferred == "ics":
        return extract_ics_summary(body)
    if preferred == "rss_atom":
        return extract_rss_atom_events(body, source_url)
    if preferred == "json_ld_event":
        result = extract_jsonld_events(body, source_url)
        if result.event_candidates or explicit_extractor:
            return result
    if preferred in {"html_event_list", "generic_html_links"}:
        return extract_html_events(body, source_url)

    if looks_like_jsonld(body):
        result = extract_jsonld_events(body, source_url)
        if result.event_candidates:
            return result
    if looks_like_rss_atom(content_type, body):
        return extract_rss_atom_events(body, source_url)
    if looks_like_html(content_type, body):
        return extract_html_events(body, source_url)
    return ExtractionResult(
        extractor_type="unsupported",
        status="unsupported",
        unsupported_reason="No supported extractor matched this response.",
    )


def extractor_hint(
    source_url: str,
    content_type: str | None,
    body: str,
    source_type: str | None,
) -> str:
    lowered_source_type = (source_type or "").lower()
    if looks_like_ics(source_url, content_type, body):
        return "ics"
    if "rss" in lowered_source_type or "atom" in lowered_source_type:
        return "rss_atom"
    if looks_like_rss_atom(content_type, body):
        return "rss_atom"
    if looks_like_jsonld(body):
        return "json_ld_event"
    if looks_like_html(content_type, body):
        return "html_event_list"
    return "unsupported"


def looks_like_ics(source_url: str, content_type: str | None, body: str) -> bool:
    source_path = urlparse(source_url).path.lower()
    lowered_content_type = (content_type or "").lower()
    return (
        "text/calendar" in lowered_content_type
        or source_path.endswith((".ics", ".ical"))
        or "BEGIN:VCALENDAR" in body[:1000].upper()
    )


def looks_like_jsonld(body: str) -> bool:
    return "application/ld+json" in body[:20000].lower()


def looks_like_rss_atom(content_type: str | None, body: str) -> bool:
    lowered_content_type = (content_type or "").lower()
    stripped = body.lstrip()[:500].lower()
    return (
        "application/rss+xml" in lowered_content_type
        or "application/atom+xml" in lowered_content_type
        or "application/xml" in lowered_content_type
        or "text/xml" in lowered_content_type
        or stripped.startswith("<rss")
        or stripped.startswith("<feed")
    )


def looks_like_html(content_type: str | None, body: str) -> bool:
    lowered_content_type = (content_type or "").lower()
    lowered_body = body[:2000].lower()
    return (
        "text/html" in lowered_content_type
        or "<html" in lowered_body
        or "<article" in lowered_body
        or "<div" in lowered_body
    )


def extract_ics_summary(body: str) -> ExtractionResult:
    try:
        candidates = parse_ics_events(body)
    except ValueError as exc:
        return ExtractionResult(
            extractor_type="ics",
            status="failure",
            errors=[str(exc)],
        )
    return ExtractionResult(
        extractor_type="ics",
        status="success",
        extraction_summary={"ics_event_count": len(candidates)},
    )
