from __future__ import annotations

import json
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.db.models import ApiFeedRecord, Event, ImageCandidate
from app.services.crawl_service import Fetcher, FetchResult, fetch_calendar_url
from app.services.image_qa_service import (
    ImageCandidateInput,
    blocking_reasons,
    create_image_candidate,
    is_auto_selectable,
    is_human_selectable,
    is_likely_direct_image_asset,
    normalize_image_url,
)
from app.services.security_service import url_safety_flags
from app.services.source_taxonomy_service import detect_source_key, normalized_domain
from app.services.ticket_link_service import TicketLinkAssessment, classify_ticket_link

ALLOWED_TICKET_FALLBACK_CATEGORIES = {
    "direct",
    "platform_event",
    "redirect_or_handoff",
}
DIRECT_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif")
IMAGE_ASSET_HOST_TERMS = ("cdn", "cloudfront", "images", "image", "media", "uploads")
SENSITIVE_QUERY_TOKENS = (
    "token",
    "session",
    "sid",
    "queueittoken",
    "auth",
    "password",
    "secret",
    "key",
)
_FETCH_CACHE: dict[str, FetchResult] = {}


@dataclass(frozen=True)
class ExtractedTicketImage:
    image_url: str
    source_payload_path: str


@dataclass(frozen=True)
class TicketPageMetadata:
    canonical_url: str | None
    page_title: str | None
    images: list[ExtractedTicketImage]


@dataclass(frozen=True)
class TicketPageFallbackDecision:
    should_run: bool
    reason: str
    ticket_url: str | None
    assessment: TicketLinkAssessment


@dataclass
class TicketPageImageResult:
    event_id: int
    ticket_url: str | None
    fallback_triggered: bool
    trigger_reason: str
    fetch_status: str
    error_message: str | None = None
    http_status_code: int | None = None
    content_type: str | None = None
    final_url: str | None = None
    canonical_url: str | None = None
    page_title: str | None = None
    extracted_image_count: int = 0
    created_candidate_count: int = 0
    candidate_ids: list[int] = field(default_factory=list)
    selected_candidate_id: int | None = None
    selected_url: str | None = None
    selected_reason: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "ticket_url": redact_url(self.ticket_url),
            "fallback_triggered": self.fallback_triggered,
            "trigger_reason": self.trigger_reason,
            "fetch_status": self.fetch_status,
            "error_message": self.error_message,
            "http_status_code": self.http_status_code,
            "content_type": self.content_type,
            "final_url": redact_url(self.final_url),
            "canonical_url": redact_url(self.canonical_url),
            "page_title": self.page_title,
            "extracted_image_count": self.extracted_image_count,
            "created_candidate_count": self.created_candidate_count,
            "candidate_ids": self.candidate_ids,
            "selected_candidate_id": self.selected_candidate_id,
            "selected_url": self.selected_url,
            "selected_reason": self.selected_reason,
        }


class TicketPageMetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta_images: list[ExtractedTicketImage] = []
        self.canonical_url: str | None = None
        self.page_title: str | None = None
        self._in_title = False
        self._title_chunks: list[str] = []
        self._in_jsonld = False
        self._jsonld_chunks: list[str] = []
        self.jsonld_payloads: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attr_map = {key.lower(): value or "" for key, value in attrs}
        lowered_tag = tag.lower()
        if lowered_tag == "meta":
            key = (
                attr_map.get("property")
                or attr_map.get("name")
                or attr_map.get("itemprop")
                or ""
            ).lower()
            value = attr_map.get("content") or ""
            if key in {"og:image", "twitter:image"} and value:
                self.meta_images.append(
                    ExtractedTicketImage(
                        image_url=value.strip(),
                        source_payload_path=f"meta.{key}",
                    )
                )
        elif lowered_tag == "link":
            rel = attr_map.get("rel", "").lower()
            href = attr_map.get("href") or ""
            if rel == "canonical" and href:
                self.canonical_url = href.strip()
        elif lowered_tag == "title":
            self._in_title = True
        elif lowered_tag == "script":
            script_type = attr_map.get("type", "").lower()
            if script_type == "application/ld+json":
                self._in_jsonld = True
                self._jsonld_chunks = []

    def handle_endtag(self, tag: str) -> None:
        lowered_tag = tag.lower()
        if lowered_tag == "title":
            self._in_title = False
            title = " ".join("".join(self._title_chunks).split())
            self.page_title = title or self.page_title
        elif lowered_tag == "script" and self._in_jsonld:
            self._in_jsonld = False
            payload = "".join(self._jsonld_chunks).strip()
            if payload:
                self.jsonld_payloads.append(payload)

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_chunks.append(data)
        if self._in_jsonld:
            self._jsonld_chunks.append(data)


def redact_url(url: str | None) -> str | None:
    if not url:
        return url
    parsed = urlparse(url)
    query = []
    redacted = False
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if any(token in key.lower() for token in SENSITIVE_QUERY_TOKENS):
            query.append((key, "REDACTED"))
            redacted = True
        else:
            query.append((key, value))
    if not redacted:
        return url
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            urlencode(query, doseq=True),
            parsed.fragment,
        )
    )


def _jsonld_images_from_value(value: object, path: str) -> list[ExtractedTicketImage]:
    images: list[ExtractedTicketImage] = []
    if isinstance(value, str):
        images.append(ExtractedTicketImage(value.strip(), path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            images.extend(_jsonld_images_from_value(item, f"{path}[{index}]"))
    elif isinstance(value, dict):
        direct_value = value.get("url") or value.get("@id")
        if isinstance(direct_value, str):
            images.append(ExtractedTicketImage(direct_value.strip(), path))
        for key, item in value.items():
            if key == "image":
                images.extend(_jsonld_images_from_value(item, f"{path}.image"))
            elif isinstance(item, (dict, list)):
                images.extend(_jsonld_images_from_value(item, f"{path}.{key}"))
    return images


def _jsonld_images(payload: str) -> list[ExtractedTicketImage]:
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return []
    candidates = parsed if isinstance(parsed, list) else [parsed]
    images: list[ExtractedTicketImage] = []
    for index, item in enumerate(candidates):
        images.extend(_jsonld_images_from_value(item, f"jsonld[{index}]"))
    return images


def _is_ticket_page_direct_image_url(url: str) -> bool:
    if not is_likely_direct_image_asset(url):
        return False
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    path = parsed.path.lower()
    return path.endswith(DIRECT_IMAGE_EXTENSIONS) or any(
        term in host for term in IMAGE_ASSET_HOST_TERMS
    )


def extract_ticket_page_metadata(html: str) -> TicketPageMetadata:
    parser = TicketPageMetadataParser()
    parser.feed(html)
    extracted = list(parser.meta_images)
    for payload in parser.jsonld_payloads:
        extracted.extend(_jsonld_images(payload))

    seen: set[str] = set()
    images: list[ExtractedTicketImage] = []
    for image in extracted:
        if not _is_ticket_page_direct_image_url(image.image_url):
            continue
        normalized = normalize_image_url(image.image_url)
        if normalized in seen:
            continue
        seen.add(normalized)
        images.append(image)

    return TicketPageMetadata(
        canonical_url=parser.canonical_url,
        page_title=parser.page_title,
        images=images,
    )


def _ticket_url_for_event(event: Event) -> str | None:
    return event.recommended_ticket_link or event.tickets_link


def _selected_candidate(event: Event) -> ImageCandidate | None:
    return next(
        (
            candidate
            for candidate in event.image_candidates
            if candidate.id == event.selected_image_candidate_id
        ),
        None,
    )


def _has_manual_accepted_image(event: Event) -> bool:
    selected = _selected_candidate(event)
    if selected is None:
        return False
    return (
        selected.candidate_status == "accepted"
        and selected.source_type in {"manual", "upload", "partner_supplied"}
    )


def _has_accepted_artist_image(event: Event) -> bool:
    return any(
        candidate.candidate_status == "accepted"
        and is_human_selectable(candidate)
        and (
            candidate.image_role in {"artist_live", "artist_press"}
            or candidate.rescue_source == "provider_artist_image"
        )
        for candidate in event.image_candidates
    )


def _event_is_stale_or_rejected(event: Event) -> bool:
    status_values = {
        (event.publish_status or "").lower(),
        (event.event_lifecycle_status or "").lower(),
        (event.event_status or "").lower(),
    }
    return bool(status_values & {"rejected", "expired", "stale", "cancelled"})


def _only_evidence_images(event: Event) -> bool:
    if not event.image_candidates:
        return False
    return all(
        candidate.source_evidence_only or not is_auto_selectable(candidate)
        for candidate in event.image_candidates
    )


def ticket_page_fallback_decision(
    event: Event,
    settings: Settings,
) -> TicketPageFallbackDecision:
    ticket_url = _ticket_url_for_event(event)
    assessment = classify_ticket_link(ticket_url)
    if _event_is_stale_or_rejected(event):
        return TicketPageFallbackDecision(
            False,
            "event_rejected_expired_or_stale",
            ticket_url,
            assessment,
        )
    if _has_manual_accepted_image(event):
        return TicketPageFallbackDecision(
            False,
            "manual_accepted_image_exists",
            ticket_url,
            assessment,
        )
    if _has_accepted_artist_image(event):
        return TicketPageFallbackDecision(
            False,
            "accepted_artist_image_exists",
            ticket_url,
            assessment,
        )
    if not ticket_url:
        return TicketPageFallbackDecision(False, "missing_ticket_url", None, assessment)
    if (
        not assessment.usable
        or assessment.category not in ALLOWED_TICKET_FALLBACK_CATEGORIES
    ):
        return TicketPageFallbackDecision(
            False,
            f"ticket_link_not_usable:{assessment.category}",
            ticket_url,
            assessment,
        )
    safety_flags = url_safety_flags(ticket_url, settings)
    if safety_flags:
        return TicketPageFallbackDecision(
            False,
            "ticket_url_safety_blocked",
            ticket_url,
            assessment,
        )

    selected = _selected_candidate(event)
    if not event.selected_main_image_url:
        return TicketPageFallbackDecision(
            True,
            "missing_selected_image",
            ticket_url,
            assessment,
        )
    if event.image_status in {"missing", "needs_review"}:
        return TicketPageFallbackDecision(
            True,
            f"selected_image_status:{event.image_status}",
            ticket_url,
            assessment,
        )
    if selected is not None:
        reasons = blocking_reasons(selected, manual_override=False)
        if reasons:
            return TicketPageFallbackDecision(
                True,
                f"selected_image_blocked:{','.join(reasons[:3])}",
                ticket_url,
                assessment,
            )
        if (
            selected.appears_stock_or_placeholder
            or selected.appears_poster_or_flyer
            or selected.generic_detection_score >= 70
            or selected.rescue_source == "social_graphic_reference"
            or selected.source_evidence_only
        ):
            return TicketPageFallbackDecision(
                True,
                "selected_provider_image_weak",
                ticket_url,
                assessment,
            )
    if _only_evidence_images(event):
        return TicketPageFallbackDecision(
            True,
            "only_evidence_or_blocked_images",
            ticket_url,
            assessment,
        )
    return TicketPageFallbackDecision(
        False,
        "usable_image_exists",
        ticket_url,
        assessment,
    )


def _load_event(session: Session, event_id: int) -> Event | None:
    return session.scalars(
        select(Event)
        .options(selectinload(Event.image_candidates))
        .where(Event.id == event_id)
    ).first()


def fetch_ticket_page_html(
    ticket_url: str,
    settings: Settings,
    *,
    fetcher: Fetcher | None = None,
    use_cache: bool = True,
) -> FetchResult:
    if use_cache and ticket_url in _FETCH_CACHE:
        return _FETCH_CACHE[ticket_url]
    active_fetcher = fetcher or (lambda url: fetch_calendar_url(url, settings))
    result = active_fetcher(ticket_url)
    if use_cache:
        _FETCH_CACHE[ticket_url] = result
    return result


def create_ticket_page_image_candidates(
    session: Session,
    event: Event,
    metadata: TicketPageMetadata,
    *,
    ticket_url: str,
    final_url: str | None,
    assessment: TicketLinkAssessment,
) -> list[ImageCandidate]:
    provider_key = assessment.provider_key or detect_source_key(ticket_url)
    provider_domain = assessment.provider_domain or normalized_domain(ticket_url)
    created: list[ImageCandidate] = []
    for extracted in metadata.images:
        normalized = normalize_image_url(extracted.image_url)
        existing = session.scalars(
            select(ImageCandidate).where(
                ImageCandidate.event_id == event.id,
                ImageCandidate.normalized_image_url == normalized,
                ImageCandidate.source_payload_path == extracted.source_payload_path,
            )
        ).first()
        if existing is not None:
            continue
        candidate = create_image_candidate(
            session,
            ImageCandidateInput(
                event_id=event.id,
                source_type="ticket_page",
                source_provider=provider_key or provider_domain,
                source_url=final_url or ticket_url,
                image_url=extracted.image_url,
                image_role="event_provider",
                clearance_status="needs_approval",
                rescue_source="ticketing_page_image",
                rescue_priority=52,
                source_payload_path=extracted.source_payload_path,
                music_signal_score=72.0,
                selected_reason="ticket_page_fallback_candidate",
                selection_explanation_json=json.dumps(
                    {
                        "ticket_url": redact_url(ticket_url),
                        "ticketing_provider": provider_key,
                        "ticketing_provider_domain": provider_domain,
                        "source_payload_path": extracted.source_payload_path,
                        "page_title": metadata.page_title,
                        "canonical_url": redact_url(metadata.canonical_url),
                    },
                    ensure_ascii=True,
                    sort_keys=True,
                ),
            ),
            commit=False,
        )
        created.append(candidate)
    return created


def run_ticket_page_image_fallback(
    session: Session,
    event_id: int,
    *,
    settings: Settings,
    fetcher: Fetcher | None = None,
    commit: bool = True,
) -> TicketPageImageResult | None:
    event = _load_event(session, event_id)
    if event is None:
        return None

    decision = ticket_page_fallback_decision(event, settings)
    result = TicketPageImageResult(
        event_id=event.id,
        ticket_url=decision.ticket_url,
        fallback_triggered=decision.should_run,
        trigger_reason=decision.reason,
        fetch_status="not_run",
    )
    if not decision.should_run or not decision.ticket_url:
        if commit:
            session.commit()
        return result

    fetch_result = fetch_ticket_page_html(
        decision.ticket_url,
        settings,
        fetcher=fetcher,
    )
    result.http_status_code = fetch_result.http_status_code
    result.content_type = fetch_result.content_type
    result.final_url = fetch_result.final_url or decision.ticket_url
    if fetch_result.error_message:
        result.fetch_status = "failure"
        result.error_message = fetch_result.error_message
        if commit:
            session.commit()
        return result
    if fetch_result.http_status_code is None or fetch_result.http_status_code >= 400:
        result.fetch_status = "failure"
        result.error_message = (
            f"Ticket page returned HTTP {fetch_result.http_status_code}."
        )
        if commit:
            session.commit()
        return result
    content_type = (fetch_result.content_type or "").split(";", maxsplit=1)[0].lower()
    if content_type != "text/html":
        result.fetch_status = "blocked"
        result.error_message = "Ticket page response was not text/html."
        if commit:
            session.commit()
        return result
    raw_body = fetch_result.raw_response_body or ""
    if len(raw_body.encode("utf-8")) > settings.crawler_max_response_bytes:
        result.fetch_status = "blocked"
        result.error_message = "Ticket page response size limit exceeded."
        if commit:
            session.commit()
        return result

    metadata = extract_ticket_page_metadata(raw_body)
    result.canonical_url = metadata.canonical_url
    result.page_title = metadata.page_title
    result.extracted_image_count = len(metadata.images)
    created = create_ticket_page_image_candidates(
        session,
        event,
        metadata,
        ticket_url=decision.ticket_url,
        final_url=result.final_url,
        assessment=decision.assessment,
    )
    result.created_candidate_count = len(created)
    result.candidate_ids = [candidate.id for candidate in created]
    result.fetch_status = "success" if metadata.images else "no_usable_images"
    session.flush()
    session.refresh(event, attribute_names=["image_candidates"])

    from app.services.event_photo_rescue_service import run_event_photo_rescue

    rescue_result = run_event_photo_rescue(session, event.id, commit=False)
    if rescue_result is not None:
        result.selected_candidate_id = rescue_result.selected_candidate_id
        result.selected_url = rescue_result.selected_url
        result.selected_reason = rescue_result.reason
    if commit:
        session.commit()
    return result


def events_needing_ticket_page_fallback(
    session: Session,
    *,
    settings: Settings,
    limit: int = 100,
    api_feed_run_id: int | None = None,
) -> list[Event]:
    statement = (
        select(Event)
        .options(selectinload(Event.image_candidates))
        .where(Event.category == "Concert", Event.record_type == "event")
        .order_by(Event.updated_at.desc(), Event.id.desc())
        .limit(limit)
    )
    if api_feed_run_id is not None:
        statement = statement.where(Event.api_feed_run_id == api_feed_run_id)
    events = list(session.scalars(statement).all())
    return [
        event
        for event in events
        if ticket_page_fallback_decision(event, settings).should_run
    ]


def ticket_page_fallback_counts_for_api_feed_run(
    session: Session,
    run_id: int,
    *,
    settings: Settings,
) -> dict[str, int]:
    event_ids = set(
        session.scalars(select(Event.id).where(Event.api_feed_run_id == run_id)).all()
    )
    event_ids.update(
        event_id
        for event_id in session.scalars(
            select(ApiFeedRecord.created_event_id).where(
                ApiFeedRecord.api_feed_run_id == run_id,
                ApiFeedRecord.created_event_id.is_not(None),
            )
        ).all()
        if event_id is not None
    )
    events = (
        list(
            session.scalars(
                select(Event)
                .options(selectinload(Event.image_candidates))
                .where(Event.id.in_(event_ids))
            ).all()
        )
        if event_ids
        else []
    )
    return {
        "events_needing_ticket_image_fallback": sum(
            ticket_page_fallback_decision(event, settings).should_run
            for event in events
        ),
        "ticket_page_candidates_found": sum(
            1
            for event in events
            for candidate in event.image_candidates
            if candidate.source_type == "ticket_page"
        ),
        "fallback_selected": sum(
            event.image_source_type == "ticket_page" for event in events
        ),
        "no_usable_ticket_image_found": sum(
            any(
                candidate.source_type == "ticket_page"
                for candidate in event.image_candidates
            )
            is False
            and not event.selected_main_image_url
            for event in events
        ),
    }


def run_ticket_page_image_fallback_for_api_feed_run(
    session: Session,
    run_id: int,
    *,
    settings: Settings,
    fetcher: Fetcher | None = None,
) -> dict[str, object]:
    event_ids = set(
        session.scalars(select(Event.id).where(Event.api_feed_run_id == run_id)).all()
    )
    event_ids.update(
        event_id
        for event_id in session.scalars(
            select(ApiFeedRecord.created_event_id).where(
                ApiFeedRecord.api_feed_run_id == run_id,
                ApiFeedRecord.created_event_id.is_not(None),
            )
        ).all()
        if event_id is not None
    )
    results = [
        result
        for event_id in sorted(event_ids)
        if (
            result := run_ticket_page_image_fallback(
                session,
                event_id,
                settings=settings,
                fetcher=fetcher,
                commit=False,
            )
        )
        is not None
    ]
    session.commit()
    return {
        "api_feed_run_id": run_id,
        "event_count": len(event_ids),
        "attempted_count": sum(result.fallback_triggered for result in results),
        "created_candidate_count": sum(
            result.created_candidate_count for result in results
        ),
        "selected_count": sum(
            result.selected_candidate_id is not None for result in results
        ),
        "results": [result.as_dict() for result in results],
    }


def run_recent_events_ticket_page_image_fallback(
    session: Session,
    *,
    settings: Settings,
    fetcher: Fetcher | None = None,
    limit: int = 100,
) -> dict[str, object]:
    events = events_needing_ticket_page_fallback(
        session,
        settings=settings,
        limit=limit,
    )
    results = [
        result
        for event in events
        if (
            result := run_ticket_page_image_fallback(
                session,
                event.id,
                settings=settings,
                fetcher=fetcher,
                commit=False,
            )
        )
        is not None
    ]
    session.commit()
    return {
        "event_count": len(events),
        "attempted_count": sum(result.fallback_triggered for result in results),
        "created_candidate_count": sum(
            result.created_candidate_count for result in results
        ),
        "selected_count": sum(
            result.selected_candidate_id is not None for result in results
        ),
        "results": [result.as_dict() for result in results],
    }
