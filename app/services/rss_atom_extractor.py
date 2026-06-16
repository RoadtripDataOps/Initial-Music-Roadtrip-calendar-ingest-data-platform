from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from app.services.extraction_types import EventCandidate, ExtractionResult
from app.services.source_extraction_utils import (
    absolute_url,
    clean_text,
    parse_datetime_value,
    strip_tags,
)


def extract_rss_atom_events(body: str, source_url: str) -> ExtractionResult:
    try:
        root = ET.fromstring(body.encode("utf-8"))
    except ET.ParseError as exc:
        return ExtractionResult(
            extractor_type="rss_atom",
            status="failure",
            errors=[f"RSS/Atom parse error: {exc}"],
        )
    items = feed_items(root)
    candidate_results = [candidate_from_item(item, source_url) for item in items]
    candidates: list[EventCandidate] = [
        candidate for candidate in candidate_results if candidate is not None
    ]
    if not candidates:
        return ExtractionResult(
            extractor_type="rss_atom",
            status="unsupported",
            unsupported_reason="No event-like feed items found.",
            extraction_summary={"feed_item_count": len(items)},
        )
    has_errors = any(candidate.validation_errors for candidate in candidates)
    status = "partial" if has_errors else "success"
    return ExtractionResult(
        extractor_type="rss_atom",
        status=status,
        event_candidates=candidates,
        warnings=["RSS extraction is conservative; review weak candidates."]
        if status == "partial"
        else [],
        extraction_summary={"feed_item_count": len(items)},
    )


def feed_items(root: ET.Element) -> list[ET.Element]:
    root_name = local_name(root.tag)
    if root_name == "rss":
        channel = root.find("channel")
        return list(channel.findall("item")) if channel is not None else []
    if root_name == "feed":
        return [item for item in list(root) if local_name(item.tag) == "entry"]
    return []


def local_name(tag: str) -> str:
    return tag.split("}", 1)[-1].lower()


def child_text(item: ET.Element, *names: str) -> str | None:
    wanted = {name.lower() for name in names}
    for child in list(item):
        if local_name(child.tag) in wanted:
            text = "".join(child.itertext())
            return clean_text(text)
    return None


def item_link(item: ET.Element, source_url: str) -> str | None:
    for child in list(item):
        if local_name(child.tag) != "link":
            continue
        href = child.attrib.get("href")
        if href:
            return absolute_url(href, source_url)
        if child.text:
            return absolute_url(child.text, source_url)
    guid = child_text(item, "guid", "id")
    return absolute_url(guid, source_url)


def candidate_from_item(item: ET.Element, source_url: str) -> EventCandidate | None:
    title = child_text(item, "title")
    description_html = child_text(item, "description", "summary", "content")
    description = strip_tags(description_html or "")
    link = item_link(item, source_url)
    date_source = " ".join(part for part in (title, description) if part)
    start = parse_datetime_value(date_source)
    quality_flags: list[str] = ["rss_atom_candidate"]
    validation_errors: list[str] = []
    if not title:
        validation_errors.append("Missing event title.")
    if start is None:
        validation_errors.append("Missing reliable event date.")
        if child_text(item, "pubDate", "published", "updated"):
            quality_flags.append("published_date_not_event_date")
    if not title and not link:
        return None
    return EventCandidate(
        event_name=title,
        start_datetime=start,
        description=description or None,
        event_url=link,
        raw_fragment=item_to_dict(item),
        quality_flags=quality_flags,
        validation_errors=validation_errors,
        review_status="pending_review" if not validation_errors else "needs_review",
        validation_status="valid" if not validation_errors else "invalid",
    )


def item_to_dict(item: ET.Element) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for child in list(item):
        name = local_name(child.tag)
        payload[name] = clean_text("".join(child.itertext()))
        if child.attrib:
            payload[f"{name}_attributes"] = dict(child.attrib)
    return payload
