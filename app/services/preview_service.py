from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from urllib.parse import parse_qsl, quote, urlencode, urlparse

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Event, EventVenue
from app.services.api_feed_service import (
    api_quality_counts,
    approved_events_by_ingestion_provider,
    approved_events_by_provider,
    approved_events_by_ticketing_provider,
    approved_events_by_upstream_source,
    ticket_link_classification_counts,
)
from app.services.file_risk_service import (
    is_direct_image_url,
    is_full_url,
    is_social_url,
)
from app.services.image_qa_service import (
    SELECTED_PENDING_STATUS,
    event_image_badges,
    venue_image_badges,
)
from app.services.image_qa_service import (
    quality_counts as image_quality_counts,
)
from app.services.venue_service import get_venue, list_venues, upcoming_events_for_venue

VENDOR_TOKEN = "city" + "spark"


@dataclass(frozen=True)
class PreviewFilters:
    search_area: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    radius_miles: float | None = None
    genre: str | None = None
    date_from: date | None = None
    date_to: date | None = None

    @property
    def has_radius(self) -> bool:
        return (
            self.latitude is not None
            and self.longitude is not None
            and self.radius_miles is not None
        )


@dataclass(frozen=True)
class EventPreviewRow:
    event: Event
    distance_miles: float | None
    quality_flags: list[str]
    image_badges: list[str]


@dataclass(frozen=True)
class VenuePreviewRow:
    venue: EventVenue
    event_count: int
    next_event: Event | None
    quality_flags: list[str]
    image_badges: list[str]


@dataclass(frozen=True)
class VenueCategoryOption:
    name: str
    color: str
    icon: str
    subcategories: tuple[str, ...]


@dataclass(frozen=True)
class VenuePreviewFilters:
    category: str | None = None
    subcategory: str | None = None
    certified: bool = False
    carousel_tag: str | None = None
    city: str | None = None
    state: str | None = None
    quality_issue: str | None = None


@dataclass(frozen=True)
class QualitySummary:
    total_approved_events: int
    events_missing_images: int
    events_with_bad_image_urls: int
    events_missing_ticket_links: int
    events_missing_venue_address: int
    events_missing_coordinates: int
    events_missing_spotify_url: int
    events_with_suspicious_tracking: int
    events_without_venue_profile: int
    venues_missing_images: int
    venues_missing_descriptions: int
    duplicate_candidate_events: int
    weak_dedupe_events: int
    events_recently_updated: int
    events_with_multiple_source_claims: int
    events_with_single_source_claim: int
    events_with_source_conflicts: int
    api_records_pending_review: int
    api_records_held: int
    api_records_needing_enrichment: int
    api_records_expiring_soon: int
    api_records_rejected: int
    api_records_unknown_upstream_source: int
    api_records_api_backfill_required: int
    api_records_suspicious_provenance: int
    events_with_selected_image: int
    events_with_selected_image_pending_approval: int
    events_with_selected_cleared_image: int
    events_missing_usable_image: int
    events_using_venue_fallback: int
    events_using_provider_image_pending_approval: int
    events_with_hard_blocked_image_candidates: int
    events_with_provider_stock_candidate: int
    events_needing_image_approval: int
    events_with_text_heavy_image_candidates: int
    events_with_watermark_candidates: int
    events_with_poster_flyer_candidates: int
    events_with_accepted_artist_images: int
    events_with_accepted_venue_fallback_images: int
    events_selected_by_photo_rescue: int
    events_with_generic_provider_image_blocked: int
    events_with_poster_flyer_admat_blocked: int
    events_with_social_graphic_evidence: int
    events_with_artist_image_candidates: int
    venues_needing_image_approval: int
    api_approved_events_by_provider: list[tuple[str, int]]
    api_events_by_ingestion_provider: list[tuple[str, int]]
    api_events_by_upstream_source: list[tuple[str, int]]
    api_events_by_ticketing_provider: list[tuple[str, int]]
    api_ticket_link_classifications: list[tuple[str, int]]


VENUE_CATEGORY_OPTIONS = [
    VenueCategoryOption(
        name="Music Site",
        color="#3fa2ff",
        icon="M",
        subcategories=(
            "Festivals",
            "Recording Studios",
            "Radio Stations",
            "Music Education",
            "Dance Clubs",
            "Venues",
        ),
    ),
    VenueCategoryOption(
        name="Bars & Lounges",
        color="#4fd4e8",
        icon="B",
        subcategories=(),
    ),
    VenueCategoryOption(
        name="Cultural",
        color="#ff7d35",
        icon="C",
        subcategories=(
            "Museums",
            "Art",
            "Memorials",
            "Birthplaces",
            "Theatres",
            "Album Covers",
            "Performing Arts Centers",
        ),
    ),
    VenueCategoryOption(
        name="Food & Bev",
        color="#a36bff",
        icon="F",
        subcategories=("Restaurants", "Coffee Shops"),
    ),
    VenueCategoryOption(
        name="Shopping",
        color="#5bd85b",
        icon="S",
        subcategories=(
            "Record Stores",
            "Music Stores",
            "Apparel & Merch Shops",
        ),
    ),
    VenueCategoryOption(
        name="Visitor & Travel",
        color="#b87333",
        icon="V",
        subcategories=("Travel & Tourism", "Chamber"),
    ),
    VenueCategoryOption(
        name="Lodging",
        color="#ff4a3d",
        icon="L",
        subcategories=("Music Hotels", "Music Camping"),
    ),
]

VENUE_QUALITY_ISSUES = [
    "missing image",
    "bad image URL",
    "social image URL",
    "missing description",
    "missing address",
    "missing coordinates",
    "malformed website",
]


def venue_category_names() -> list[str]:
    return [option.name for option in VENUE_CATEGORY_OPTIONS]


def selected_category_option(category: str | None) -> VenueCategoryOption | None:
    if not category:
        return None
    for option in VENUE_CATEGORY_OPTIONS:
        if option.name == category:
            return option
    return None


def parse_date_filter(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def parse_float_filter(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_bool_filter(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def comparable_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def approved_event_statement() -> Select[tuple[Event]]:
    return (
        select(Event)
        .options(
            selectinload(Event.venue),
            selectinload(Event.source),
            selectinload(Event.source_claims),
        )
        .where(Event.category == "Concert", Event.record_type == "event")
        .order_by(Event.start_datetime.asc(), Event.id.asc())
    )


def approved_events(session: Session) -> list[Event]:
    return list(session.scalars(approved_event_statement()).all())


def haversine_miles(
    latitude: float,
    longitude: float,
    target_latitude: float,
    target_longitude: float,
) -> float:
    radius_miles = 3958.7613
    lat1 = math.radians(latitude)
    lat2 = math.radians(target_latitude)
    delta_lat = math.radians(target_latitude - latitude)
    delta_lng = math.radians(target_longitude - longitude)
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lng / 2) ** 2
    )
    return radius_miles * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def event_venue_name(event: Event) -> str | None:
    if event.venue:
        return event.venue.display_name
    return event.location_text


def event_address_text(event: Event) -> str | None:
    if not event.venue:
        return None
    parts = [
        event.venue.address,
        event.venue.city,
        event.venue.state,
        event.venue.zip_code,
        event.venue.country,
    ]
    return ", ".join(part for part in parts if part)


def event_coordinates(event: Event) -> tuple[float, float] | None:
    if not event.venue:
        return None
    if event.venue.latitude is None or event.venue.longitude is None:
        return None
    return event.venue.latitude, event.venue.longitude


def image_quality_flags(image_url: str | None, prefix: str = "") -> list[str]:
    if not image_url:
        return [f"{prefix}missing image".strip()]
    if is_social_url(image_url):
        return [f"{prefix}social image URL".strip()]
    if not is_direct_image_url(image_url):
        return [f"{prefix}bad image URL".strip()]
    return []


def event_display_image_url(event: Event) -> str | None:
    return event.selected_main_image_url or event.main_image_url


def venue_display_image_url(venue: EventVenue) -> str | None:
    return venue.selected_main_image_url or venue.main_image_url


def previewable_image_url(image_url: str | None) -> str | None:
    """Return an image URL only when it looks safe to render inline."""

    if image_url and is_direct_image_url(image_url):
        return image_url
    return None


def suspicious_tracking_url(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    lowered_url = url.lower()
    if VENDOR_TOKEN in lowered_url:
        return True
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        key_value = f"{key.lower()}={value.lower()}"
        if VENDOR_TOKEN in key_value:
            return True
        if key.lower() in {"utm_source", "utm_medium", "utm_campaign"}:
            return True
    return False


def suspicious_ticket_url(url: str | None) -> bool:
    if not url:
        return False
    lowered = url.lower()
    return any(token in lowered for token in ["cart", "checkout", "session"])


def event_quality_flags(event: Event) -> list[str]:
    flags: list[str] = []
    flags.extend(image_quality_flags(event_display_image_url(event)))
    flags.extend(event.image_quality_flags)
    if event.image_status == "needs_review":
        flags.append("needs image review")
    if (
        event.image_status == SELECTED_PENDING_STATUS
        or event.image_clearance_status == "needs_approval"
    ):
        flags.append("needs image approval")
    if event.image_status == "venue_fallback":
        flags.append("venue fallback image")
    if not event.tickets_link:
        flags.append("missing ticket link")
    elif not is_full_url(event.tickets_link):
        flags.append("malformed ticket link")
    elif suspicious_ticket_url(event.tickets_link):
        flags.append("session/cart ticket URL")
    if event.ticket_link_classification and event.ticket_link_classification not in {
        "direct",
        "platform_event",
        "redirect_or_handoff",
    }:
        flags.append(f"ticket link: {event.ticket_link_classification}")

    if event.source_url and not is_full_url(event.source_url):
        flags.append("malformed event URL")
    if not event_coordinates(event):
        flags.append("missing venue coordinates")
    if not event.venue:
        flags.append("missing venue profile")
    if suspicious_tracking_url(event.source_url) or suspicious_tracking_url(
        event.tickets_link
    ):
        flags.append("suspicious/vendor tracking")
    return sorted(set(flags))


def venue_quality_flags(venue: EventVenue) -> list[str]:
    flags: list[str] = []
    flags.extend(image_quality_flags(venue_display_image_url(venue)))
    flags.extend(venue.image_quality_flags)
    if venue.image_status == "needs_review":
        flags.append("needs image review")
    if venue.image_clearance_status == "needs_approval":
        flags.append("needs image approval")
    if not venue.description:
        flags.append("missing description")
    if not venue.address:
        flags.append("missing address")
    if venue.latitude is None or venue.longitude is None:
        flags.append("missing coordinates")
    if venue.website and not is_full_url(venue.website):
        flags.append("malformed website")
    return sorted(set(flags))


def venue_carousel_tags(venue: EventVenue) -> list[str]:
    raw_value = getattr(venue, "carousel_tags_json", None)
    if not isinstance(raw_value, str) or not raw_value:
        return []
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]


def venue_is_certified(venue: EventVenue) -> bool:
    return bool(getattr(venue, "certified", False))


def venue_matches_filters(
    venue: EventVenue,
    filters: VenuePreviewFilters,
    quality_flags: list[str],
) -> bool:
    if filters.category and venue.category != filters.category:
        return False
    if filters.subcategory and venue.subcategory != filters.subcategory:
        return False
    if filters.certified and not venue_is_certified(venue):
        return False
    if filters.carousel_tag:
        tags = {tag.lower() for tag in venue_carousel_tags(venue)}
        if filters.carousel_tag.lower() not in tags:
            return False
    if filters.city and (venue.city or "").lower() != filters.city.lower():
        return False
    if filters.state and (venue.state or "").lower() != filters.state.lower():
        return False
    if filters.quality_issue and filters.quality_issue not in quality_flags:
        return False
    return True


def event_matches_filters(event: Event, filters: PreviewFilters) -> bool:
    if filters.date_from and event.start_datetime.date() < filters.date_from:
        return False
    if filters.date_to and event.start_datetime.date() > filters.date_to:
        return False
    if filters.genre and (event.genre or "").lower() != filters.genre.lower():
        return False
    if filters.search_area:
        haystack = " ".join(
            [
                event.title,
                event.headliner or "",
                event_venue_name(event) or "",
                event.venue.city or "" if event.venue else "",
                event.venue.state or "" if event.venue else "",
            ]
        ).lower()
        if filters.search_area.lower() not in haystack:
            return False
    return True


def list_preview_events(
    session: Session,
    filters: PreviewFilters,
) -> list[EventPreviewRow]:
    rows: list[EventPreviewRow] = []
    for event in approved_events(session):
        if not event_matches_filters(event, filters):
            continue
        distance: float | None = None
        coordinates = event_coordinates(event)
        if filters.has_radius:
            if coordinates is None:
                continue
            distance = haversine_miles(
                filters.latitude or 0,
                filters.longitude or 0,
                coordinates[0],
                coordinates[1],
            )
            if distance > (filters.radius_miles or 0):
                continue
        rows.append(
            EventPreviewRow(
                event=event,
                distance_miles=distance,
                quality_flags=event_quality_flags(event),
                image_badges=event_image_badges(event),
            )
        )
    return rows


def get_preview_event(session: Session, event_id: int) -> Event | None:
    statement = (
        select(Event)
        .options(selectinload(Event.venue), selectinload(Event.source))
        .where(
            Event.id == event_id,
            Event.category == "Concert",
            Event.record_type == "event",
        )
    )
    return session.scalars(statement).first()


def list_preview_venues(
    session: Session,
    filters: VenuePreviewFilters | None = None,
) -> list[VenuePreviewRow]:
    filters = filters or VenuePreviewFilters()
    rows: list[VenuePreviewRow] = []
    for venue in list_venues(session):
        quality_flags = venue_quality_flags(venue)
        if not venue_matches_filters(venue, filters, quality_flags):
            continue
        events = sorted(
            [
                event
                for event in venue.events
                if event.category == "Concert" and event.record_type == "event"
            ],
            key=lambda event: (event.start_datetime, event.id),
        )
        rows.append(
            VenuePreviewRow(
                venue=venue,
                event_count=len(events),
                next_event=events[0] if events else None,
                quality_flags=quality_flags,
                image_badges=venue_image_badges(venue),
            )
        )
    return rows


def get_preview_venue(session: Session, venue_id: int) -> EventVenue | None:
    return get_venue(session, venue_id)


def preview_events_for_venue(session: Session, venue_id: int) -> list[EventPreviewRow]:
    return [
        EventPreviewRow(
            event=event,
            distance_miles=None,
            quality_flags=event_quality_flags(event),
            image_badges=event_image_badges(event),
        )
        for event in upcoming_events_for_venue(session, venue_id)
    ]


def quality_summary(session: Session) -> QualitySummary:
    events = approved_events(session)
    venues = list_venues(session)
    event_flags = {event.id: event_quality_flags(event) for event in events}
    venue_flags = {venue.id: venue_quality_flags(venue) for venue in venues}
    recently = datetime.now(UTC) - timedelta(days=7)
    duplicate_count = sum(
        event.duplicate_status == "duplicate_candidate" for event in events
    )
    api_counts = api_quality_counts(session)
    image_counts = image_quality_counts(session)
    return QualitySummary(
        total_approved_events=len(events),
        events_missing_images=sum(
            "missing image" in flags for flags in event_flags.values()
        ),
        events_with_bad_image_urls=sum(
            bool({"bad image URL", "social image URL"} & set(flags))
            for flags in event_flags.values()
        ),
        events_missing_ticket_links=sum(
            "missing ticket link" in flags for flags in event_flags.values()
        ),
        events_missing_venue_address=sum(
            event.venue is None or not event.venue.address for event in events
        ),
        events_missing_coordinates=sum(
            "missing venue coordinates" in flags for flags in event_flags.values()
        ),
        events_missing_spotify_url=sum(not event.spotify_url for event in events),
        events_with_suspicious_tracking=sum(
            "suspicious/vendor tracking" in flags for flags in event_flags.values()
        ),
        events_without_venue_profile=sum(
            "missing venue profile" in flags for flags in event_flags.values()
        ),
        venues_missing_images=sum(
            "missing image" in flags for flags in venue_flags.values()
        ),
        venues_missing_descriptions=sum(
            "missing description" in flags for flags in venue_flags.values()
        ),
        duplicate_candidate_events=duplicate_count,
        weak_dedupe_events=sum(event.dedupe_confidence == "weak" for event in events),
        events_recently_updated=sum(
            (
                comparable_utc(event.last_significant_change_at)
                or datetime.min.replace(tzinfo=UTC)
            )
            >= recently
            for event in events
        ),
        events_with_multiple_source_claims=sum(
            event.source_claim_count > 1 for event in events
        ),
        events_with_single_source_claim=sum(
            event.source_claim_count <= 1 for event in events
        ),
        events_with_source_conflicts=sum(
            event.duplicate_status == "duplicate_candidate" for event in events
        ),
        api_records_pending_review=api_counts["pending"],
        api_records_held=api_counts["held"],
        api_records_needing_enrichment=api_counts["needs_enrichment"],
        api_records_expiring_soon=api_counts["expiring_soon"],
        api_records_rejected=api_counts["rejected"],
        api_records_unknown_upstream_source=api_counts["unknown_upstream_source"],
        api_records_api_backfill_required=api_counts["api_backfill_required"],
        api_records_suspicious_provenance=api_counts["suspicious_provenance"],
        events_with_selected_image=image_counts["events_with_selected_image"],
        events_with_selected_image_pending_approval=image_counts[
            "events_with_selected_image_pending_approval"
        ],
        events_with_selected_cleared_image=image_counts[
            "events_with_selected_cleared_image"
        ],
        events_missing_usable_image=image_counts["events_missing_usable_image"],
        events_using_venue_fallback=image_counts["events_using_venue_fallback"],
        events_using_provider_image_pending_approval=image_counts[
            "events_using_provider_image_pending_approval"
        ],
        events_with_hard_blocked_image_candidates=image_counts[
            "events_with_hard_blocked_image_candidates"
        ],
        events_with_provider_stock_candidate=image_counts[
            "events_with_provider_stock_candidate"
        ],
        events_needing_image_approval=image_counts["events_needing_image_approval"],
        events_with_text_heavy_image_candidates=image_counts[
            "events_with_text_heavy_image_candidates"
        ],
        events_with_watermark_candidates=image_counts[
            "events_with_watermark_candidates"
        ],
        events_with_poster_flyer_candidates=image_counts[
            "events_with_poster_flyer_candidates"
        ],
        events_with_accepted_artist_images=image_counts[
            "events_with_accepted_artist_images"
        ],
        events_with_accepted_venue_fallback_images=image_counts[
            "events_with_accepted_venue_fallback_images"
        ],
        events_selected_by_photo_rescue=image_counts[
            "events_selected_by_photo_rescue"
        ],
        events_with_generic_provider_image_blocked=image_counts[
            "events_with_generic_provider_image_blocked"
        ],
        events_with_poster_flyer_admat_blocked=image_counts[
            "events_with_poster_flyer_admat_blocked"
        ],
        events_with_social_graphic_evidence=image_counts[
            "events_with_social_graphic_evidence"
        ],
        events_with_artist_image_candidates=image_counts[
            "events_with_artist_image_candidates"
        ],
        venues_needing_image_approval=image_counts["venues_needing_image_approval"],
        api_approved_events_by_provider=approved_events_by_provider(session),
        api_events_by_ingestion_provider=approved_events_by_ingestion_provider(
            session
        ),
        api_events_by_upstream_source=approved_events_by_upstream_source(session),
        api_events_by_ticketing_provider=approved_events_by_ticketing_provider(
            session
        ),
        api_ticket_link_classifications=ticket_link_classification_counts(session),
    )


def maps_url_for_event(event: Event) -> str:
    coordinates = event_coordinates(event)
    if coordinates:
        query = f"{coordinates[0]},{coordinates[1]}"
    else:
        query = event_address_text(event) or event_venue_name(event) or event.title
    return f"https://www.google.com/maps/search/?api=1&query={quote(query)}"


def street_url_for_event(event: Event) -> str:
    coordinates = event_coordinates(event)
    if coordinates:
        params = urlencode(
            {
                "api": "1",
                "map_action": "pano",
                "viewpoint": f"{coordinates[0]},{coordinates[1]}",
            }
        )
        return f"https://www.google.com/maps/@?{params}"
    return maps_url_for_event(event)


def maps_url_for_venue(venue: EventVenue) -> str:
    if venue.latitude is not None and venue.longitude is not None:
        query = f"{venue.latitude},{venue.longitude}"
    else:
        query = ", ".join(
            part
            for part in [
                venue.display_name,
                venue.address,
                venue.city,
                venue.state,
                venue.zip_code,
            ]
            if part
        )
    return f"https://www.google.com/maps/search/?api=1&query={quote(query)}"


def street_url_for_venue(venue: EventVenue) -> str:
    if venue.latitude is not None and venue.longitude is not None:
        params = urlencode(
            {
                "api": "1",
                "map_action": "pano",
                "viewpoint": f"{venue.latitude},{venue.longitude}",
            }
        )
        return f"https://www.google.com/maps/@?{params}"
    return maps_url_for_venue(venue)


def format_ics_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def escape_ics_text(value: str | None) -> str:
    if not value:
        return ""
    return (
        value.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace(",", "\\,")
        .replace(";", "\\;")
    )


def reminder_ics_for_event(event: Event) -> str:
    end_datetime = event.end_datetime or event.start_datetime
    url = event.tickets_link or event.source_url or ""
    description = event.description or ""
    location = event_address_text(event) or event.location_text
    if url:
        description = f"{description}\n{url}".strip()
    return "\r\n".join(
        [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Music Roadtrip//Calendar Ingest Preview//EN",
            "BEGIN:VEVENT",
            f"UID:preview-event-{event.id}@music-roadtrip.local",
            f"DTSTAMP:{format_ics_datetime(datetime.now(UTC))}",
            f"DTSTART:{format_ics_datetime(event.start_datetime)}",
            f"DTEND:{format_ics_datetime(end_datetime)}",
            f"SUMMARY:{escape_ics_text(event.title)}",
            f"LOCATION:{escape_ics_text(location)}",
            f"DESCRIPTION:{escape_ics_text(description)}",
            f"URL:{escape_ics_text(url)}",
            "END:VEVENT",
            "END:VCALENDAR",
            "",
        ]
    )
