from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ExtractedImageCandidate:
    """Image URL found by a safe extractor; never a final selected image."""

    image_url: str
    source_url: str | None = None
    image_role: str = "event_provider"
    source_payload_path: str | None = None


@dataclass(frozen=True)
class EventCandidate:
    """Provider-neutral event candidate staged for admin review."""

    event_name: str | None
    start_datetime: datetime | None
    end_datetime: datetime | None = None
    timezone: str | None = None
    venue_name: str | None = None
    venue_address: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    country: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    description: str | None = None
    event_url: str | None = None
    tickets_link: str | None = None
    price: str | None = None
    source_event_id: str | None = None
    headliner: str | None = None
    supporting_artists: str | None = None
    organizer_name: str | None = None
    organizer_url: str | None = None
    event_status: str | None = None
    raw_fragment: dict[str, Any] = field(default_factory=dict)
    image_candidates: list[ExtractedImageCandidate] = field(default_factory=list)
    quality_flags: list[str] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)
    review_status: str = "pending_review"
    validation_status: str = "valid"


@dataclass(frozen=True)
class DiscoveredEventLink:
    """Likely event-detail link found on an approved source page."""

    discovered_url: str
    anchor_text: str
    confidence: float
    reason: str
    source_url: str


@dataclass(frozen=True)
class ExtractionResult:
    """Output from a safe source extractor."""

    extractor_type: str
    status: str
    event_candidates: list[EventCandidate] = field(default_factory=list)
    poi_candidates: list[object] = field(default_factory=list)
    discovered_links: list[DiscoveredEventLink] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    unsupported_reason: str | None = None
    extraction_summary: dict[str, object] = field(default_factory=dict)
