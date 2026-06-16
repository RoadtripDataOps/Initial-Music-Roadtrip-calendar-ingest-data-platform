from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser

from app.services.extraction_types import (
    DiscoveredEventLink,
    EventCandidate,
    ExtractedImageCandidate,
    ExtractionResult,
)
from app.services.image_qa_service import is_likely_direct_image_asset
from app.services.source_extraction_utils import (
    absolute_url,
    clean_text,
    looks_like_event_link,
    parse_datetime_value,
)

EVENT_CARD_TOKENS = (
    "event",
    "events",
    "calendar",
    "concert",
    "show",
    "lineup",
    "artist",
)


@dataclass
class HtmlNode:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list[HtmlNode] = field(default_factory=list)
    text_parts: list[str] = field(default_factory=list)

    def text(self) -> str:
        parts = list(self.text_parts)
        for child in self.children:
            parts.append(child.text())
        return clean_text(" ".join(parts)) or ""


class EventHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.root = HtmlNode("document")
        self.stack: list[HtmlNode] = [self.root]

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        node = HtmlNode(
            tag=tag.lower(),
            attrs={key.lower(): value or "" for key, value in attrs},
        )
        self.stack[-1].children.append(node)
        if tag.lower() not in {"br", "img", "meta", "link", "input"}:
            self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        while len(self.stack) > 1:
            node = self.stack.pop()
            if node.tag == lowered:
                break

    def handle_data(self, data: str) -> None:
        text = clean_text(data)
        if text:
            self.stack[-1].text_parts.append(text)


def extract_html_events(html: str, source_url: str) -> ExtractionResult:
    parser = EventHtmlParser()
    parser.feed(html)
    candidates: list[EventCandidate] = []
    for node in event_card_nodes(parser.root):
        candidate = candidate_from_card(node, source_url)
        if candidate is not None:
            candidates.append(candidate)
    if not candidates:
        single = candidate_from_card(parser.root, source_url)
        if single is not None:
            candidates.append(single)

    links = discovered_event_links(parser.root, source_url)
    if candidates:
        return ExtractionResult(
            extractor_type="html_event_list",
            status="partial" if links else "success",
            event_candidates=candidates,
            discovered_links=links,
            warnings=["HTML extraction is conservative; review staged candidates."],
            extraction_summary={"event_card_count": len(candidates)},
        )
    if links:
        return ExtractionResult(
            extractor_type="generic_html_links",
            status="partial",
            discovered_links=links,
            warnings=["No dated events extracted; possible event links were found."],
            unsupported_reason="No event cards with reliable dates were found.",
            extraction_summary={"event_card_count": 0},
        )
    return ExtractionResult(
        extractor_type="html_event_list",
        status="unsupported",
        unsupported_reason="No extractable static HTML event cards found.",
        extraction_summary={"event_card_count": 0},
    )


def event_card_nodes(root: HtmlNode) -> list[HtmlNode]:
    nodes: list[HtmlNode] = []
    for node in walk(root):
        if node.tag not in {"article", "li", "div", "section"}:
            continue
        identity = f"{node.attrs.get('class', '')} {node.attrs.get('id', '')}".lower()
        if any(token in identity for token in EVENT_CARD_TOKENS):
            nodes.append(node)
    return nodes


def walk(node: HtmlNode) -> list[HtmlNode]:
    nodes = [node]
    for child in node.children:
        nodes.extend(walk(child))
    return nodes


def descendants(node: HtmlNode, *tags: str) -> list[HtmlNode]:
    wanted = set(tags)
    return [item for item in walk(node) if item.tag in wanted]


def first_text_for_tags(node: HtmlNode, *tags: str) -> str | None:
    for item in descendants(node, *tags):
        text = item.text()
        if text:
            return text
    return None


def first_attr_for_tag(node: HtmlNode, tag: str, attr: str) -> str | None:
    for item in descendants(node, tag):
        value = item.attrs.get(attr)
        if value:
            return value
    return None


def candidate_from_card(node: HtmlNode, source_url: str) -> EventCandidate | None:
    title = first_text_for_tags(node, "h1", "h2", "h3")
    if not title:
        title = first_non_ticket_link_text(node)
    time_value = first_attr_for_tag(node, "time", "datetime")
    start = parse_datetime_value(time_value) or parse_datetime_value(node.text())
    if start is None:
        return None
    venue_name = first_scoped_text(node, ("venue", "location"))
    event_url = first_event_url(node, source_url)
    ticket_url = first_ticket_url(node, source_url)
    images = image_candidates(node, source_url)
    quality_flags = ["html_event_card_candidate"]
    if images:
        quality_flags.append("image_candidate_from_html")
    return EventCandidate(
        event_name=title,
        start_datetime=start,
        venue_name=venue_name,
        description=node.text()[:2000],
        event_url=event_url,
        tickets_link=ticket_url,
        raw_fragment={"tag": node.tag, "attrs": node.attrs, "text": node.text()},
        image_candidates=images,
        quality_flags=quality_flags,
        validation_errors=[] if title else ["Missing event title."],
        review_status="pending_review" if title else "needs_review",
        validation_status="valid" if title else "invalid",
    )


def first_non_ticket_link_text(node: HtmlNode) -> str | None:
    for link in descendants(node, "a"):
        text = link.text()
        lowered = text.lower()
        if text and "ticket" not in lowered and "buy" not in lowered:
            return text
    return None


def first_scoped_text(node: HtmlNode, tokens: tuple[str, ...]) -> str | None:
    for item in walk(node):
        identity = f"{item.attrs.get('class', '')} {item.attrs.get('id', '')}".lower()
        if any(token in identity for token in tokens):
            text = item.text()
            if text:
                return text
    return None


def first_event_url(node: HtmlNode, source_url: str) -> str | None:
    for link in descendants(node, "a"):
        href = absolute_url(link.attrs.get("href"), source_url)
        if not href:
            continue
        looks_event, _reason = looks_like_event_link(href, link.text())
        if looks_event and "ticket" not in href.lower():
            return href
    return None


def first_ticket_url(node: HtmlNode, source_url: str) -> str | None:
    for link in descendants(node, "a"):
        href = absolute_url(link.attrs.get("href"), source_url)
        text = link.text().lower()
        if href and ("ticket" in href.lower() or "ticket" in text or "buy" in text):
            return href
    return None


def image_candidates(node: HtmlNode, source_url: str) -> list[ExtractedImageCandidate]:
    candidates: list[ExtractedImageCandidate] = []
    for index, image in enumerate(descendants(node, "img")):
        src = absolute_url(image.attrs.get("src"), source_url)
        if not src or not is_likely_direct_image_asset(src):
            continue
        candidates.append(
            ExtractedImageCandidate(
                image_url=src,
                source_url=source_url,
                image_role="event_provider",
                source_payload_path=f"html.img[{index}]",
            )
        )
    return candidates


def discovered_event_links(
    root: HtmlNode, source_url: str
) -> list[DiscoveredEventLink]:
    links: list[DiscoveredEventLink] = []
    seen: set[str] = set()
    for link in descendants(root, "a"):
        href = absolute_url(link.attrs.get("href"), source_url)
        if not href or href in seen:
            continue
        text = link.text()
        looks_event, reason = looks_like_event_link(href, text)
        if not looks_event:
            continue
        seen.add(href)
        confidence = 0.72 if "event" in reason or "concert" in reason else 0.55
        links.append(
            DiscoveredEventLink(
                discovered_url=href,
                anchor_text=text,
                confidence=confidence,
                reason=reason,
                source_url=source_url,
            )
        )
    return links[:50]
