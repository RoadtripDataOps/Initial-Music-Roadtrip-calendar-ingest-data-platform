from __future__ import annotations

import json
from html.parser import HTMLParser
from typing import Any

from app.services.extraction_types import (
    EventCandidate,
    ExtractedImageCandidate,
    ExtractionResult,
)
from app.services.image_qa_service import is_likely_direct_image_asset
from app.services.source_extraction_utils import (
    absolute_url,
    as_list,
    clean_text,
    first_text,
    parse_datetime_value,
    parse_float,
)

EVENT_TYPES = {"event", "musicevent", "festival", "concert"}


class JsonLdScriptParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.scripts: list[str] = []
        self._inside_jsonld = False
        self._current: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.lower() != "script":
            return
        attr_map = {key.lower(): value or "" for key, value in attrs}
        if attr_map.get("type", "").lower().strip() == "application/ld+json":
            self._inside_jsonld = True
            self._current = []

    def handle_data(self, data: str) -> None:
        if self._inside_jsonld:
            self._current.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._inside_jsonld:
            self.scripts.append("".join(self._current).strip())
            self._inside_jsonld = False
            self._current = []


def extract_jsonld_events(html: str, source_url: str) -> ExtractionResult:
    parser = JsonLdScriptParser()
    parser.feed(html)
    warnings: list[str] = []
    errors: list[str] = []
    candidates: list[EventCandidate] = []
    for script in parser.scripts:
        if not script:
            continue
        try:
            payload = json.loads(script)
        except json.JSONDecodeError as exc:
            warnings.append(f"Invalid JSON-LD script ignored: {exc.msg}")
            continue
        for item in event_objects(payload):
            candidate = candidate_from_jsonld(item, source_url)
            if candidate is not None:
                candidates.append(candidate)
    if candidates:
        return ExtractionResult(
            extractor_type="json_ld_event",
            status="success",
            event_candidates=candidates,
            warnings=warnings,
            errors=errors,
            extraction_summary={"jsonld_script_count": len(parser.scripts)},
        )
    status = "unsupported" if parser.scripts else "unsupported"
    reason = "No JSON-LD Event objects found."
    return ExtractionResult(
        extractor_type="json_ld_event",
        status=status,
        warnings=warnings,
        errors=errors,
        unsupported_reason=reason,
        extraction_summary={"jsonld_script_count": len(parser.scripts)},
    )


def event_objects(value: object) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, list):
        for item in value:
            found.extend(event_objects(item))
        return found
    if not isinstance(value, dict):
        return found
    graph = value.get("@graph")
    if isinstance(graph, list):
        for item in graph:
            found.extend(event_objects(item))
    if is_event_object(value):
        found.append(value)
    return found


def is_event_object(value: dict[str, Any]) -> bool:
    raw_types = as_list(value.get("@type"))
    normalized_types = {
        str(item).split("/")[-1].split("#")[-1].lower() for item in raw_types
    }
    return bool(EVENT_TYPES & normalized_types)


def candidate_from_jsonld(
    item: dict[str, Any],
    source_url: str,
) -> EventCandidate | None:
    name = clean_text(item.get("name"))
    start = parse_datetime_value(item.get("startDate"))
    end = parse_datetime_value(item.get("endDate"))
    description = clean_text(item.get("description"))
    event_url = absolute_url(first_text(item.get("url") or item.get("@id")), source_url)
    location = item.get("location") if isinstance(item.get("location"), dict) else {}
    address_value = location.get("address") if isinstance(location, dict) else None
    address = address_value if isinstance(address_value, dict) else {}
    geo_value = location.get("geo") if isinstance(location, dict) else None
    geo = geo_value if isinstance(geo_value, dict) else {}
    venue_name = (
        clean_text(location.get("name")) if isinstance(location, dict) else None
    )
    ticket_url, price = offer_fields(item.get("offers"), source_url)
    headliner, supporting = performer_fields(item.get("performer"))
    organizer = item.get("organizer") if isinstance(item.get("organizer"), dict) else {}
    images = image_candidates(item.get("image"), source_url)
    validation_errors: list[str] = []
    quality_flags: list[str] = []
    if not name:
        validation_errors.append("Missing event name.")
    if start is None:
        validation_errors.append("Missing reliable event date.")
    if images:
        quality_flags.append("image_candidate_from_json_ld")
    review_status = "pending_review" if not validation_errors else "needs_review"
    validation_status = "valid" if not validation_errors else "invalid"
    if not name and start is None:
        return None
    return EventCandidate(
        event_name=name,
        start_datetime=start,
        end_datetime=end,
        timezone=None,
        venue_name=venue_name,
        venue_address=clean_text(address.get("streetAddress")),
        city=clean_text(address.get("addressLocality")),
        state=clean_text(address.get("addressRegion")),
        zip_code=clean_text(address.get("postalCode")),
        country=clean_text(address.get("addressCountry")),
        latitude=parse_float(geo.get("latitude")),
        longitude=parse_float(geo.get("longitude")),
        description=description,
        event_url=event_url,
        tickets_link=ticket_url,
        price=price,
        source_event_id=clean_text(item.get("@id") or item.get("identifier")),
        headliner=headliner,
        supporting_artists=supporting,
        organizer_name=clean_text(organizer.get("name"))
        if isinstance(organizer, dict)
        else None,
        organizer_url=absolute_url(first_text(organizer.get("url")), source_url)
        if isinstance(organizer, dict)
        else None,
        event_status=clean_text(item.get("eventStatus")),
        raw_fragment=item,
        image_candidates=images,
        quality_flags=quality_flags,
        validation_errors=validation_errors,
        review_status=review_status,
        validation_status=validation_status,
    )


def image_candidates(value: object, source_url: str) -> list[ExtractedImageCandidate]:
    images: list[ExtractedImageCandidate] = []
    for index, item in enumerate(as_list(value)):
        image_url = first_text(item)
        absolute = absolute_url(image_url, source_url)
        if not absolute or not is_likely_direct_image_asset(absolute):
            continue
        images.append(
            ExtractedImageCandidate(
                image_url=absolute,
                source_url=source_url,
                image_role="event_provider",
                source_payload_path=f"jsonld.image[{index}]",
            )
        )
    return images


def offer_fields(value: object, source_url: str) -> tuple[str | None, str | None]:
    for item in as_list(value):
        if not isinstance(item, dict):
            continue
        url = absolute_url(first_text(item.get("url")), source_url)
        price_parts = [
            clean_text(item.get("price")),
            clean_text(item.get("lowPrice")),
            clean_text(item.get("highPrice")),
            clean_text(item.get("priceCurrency")),
        ]
        price = " ".join(part for part in price_parts if part)
        return url, price or None
    return None, None


def performer_fields(value: object) -> tuple[str | None, str | None]:
    names = [first_text(item) for item in as_list(value)]
    cleaned = [name for name in names if name]
    if not cleaned:
        return None, None
    return cleaned[0], ", ".join(cleaned[1:]) if len(cleaned) > 1 else None
