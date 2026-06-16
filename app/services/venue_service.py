from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Event, EventVenue


@dataclass(frozen=True)
class VenueInput:
    """Venue fields collected from an event source."""

    display_name: str
    address: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    country: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    website: str | None = None
    phone: str | None = None
    description: str | None = None
    main_image_url: str | None = None
    additional_image_urls: str | None = None
    category: str = "Music Site"
    subcategory: str = "Venues"


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def parse_optional_float(value: str | None) -> float | None:
    if not value or not value.strip():
        return None
    try:
        return float(value)
    except ValueError:
        return None


def normalized_part(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def deterministic_venue_key(input_data: VenueInput) -> str:
    """Build a stable key from normalized venue identity fields."""

    parts = [
        normalized_part(input_data.display_name),
        normalized_part(input_data.address),
        normalized_part(input_data.city),
        normalized_part(input_data.state),
        normalized_part(input_data.zip_code),
        normalized_part(input_data.country),
    ]
    if input_data.latitude is not None and input_data.longitude is not None:
        parts.append(f"{input_data.latitude:.5f},{input_data.longitude:.5f}")
    basis = "|".join(parts)
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def ensure_event_venue(session: Session, input_data: VenueInput) -> EventVenue:
    """Create or update one POI-style venue container for event previews."""

    venue_key = deterministic_venue_key(input_data)
    venue = session.scalars(
        select(EventVenue).where(EventVenue.venue_key == venue_key)
    ).first()
    if venue is None:
        venue = EventVenue(
            venue_key=venue_key,
            display_name=input_data.display_name.strip(),
        )

    updates = {
        "address": clean_text(input_data.address),
        "city": clean_text(input_data.city),
        "state": clean_text(input_data.state),
        "zip_code": clean_text(input_data.zip_code),
        "country": clean_text(input_data.country),
        "latitude": input_data.latitude,
        "longitude": input_data.longitude,
        "website": clean_text(input_data.website),
        "phone": clean_text(input_data.phone),
        "description": clean_text(input_data.description),
        "main_image_url": clean_text(input_data.main_image_url),
        "additional_image_urls": clean_text(input_data.additional_image_urls),
        "category": input_data.category,
        "subcategory": input_data.subcategory,
    }
    for field_name, value in updates.items():
        if value not in {None, ""}:
            setattr(venue, field_name, value)

    session.add(venue)
    session.flush()
    return venue


def ensure_venue_from_location_text(
    session: Session,
    location_text: str | None,
) -> EventVenue | None:
    if not location_text or not location_text.strip():
        return None
    return ensure_event_venue(
        session,
        VenueInput(display_name=location_text.strip()),
    )


def list_venues(session: Session) -> list[EventVenue]:
    statement = (
        select(EventVenue)
        .options(selectinload(EventVenue.events))
        .order_by(EventVenue.display_name.asc(), EventVenue.id.asc())
    )
    return list(session.scalars(statement).all())


def get_venue(session: Session, venue_id: int) -> EventVenue | None:
    statement = (
        select(EventVenue)
        .options(selectinload(EventVenue.events))
        .where(EventVenue.id == venue_id)
    )
    return session.scalars(statement).first()


def upcoming_events_for_venue(session: Session, venue_id: int) -> list[Event]:
    statement = (
        select(Event)
        .where(
            Event.event_venue_id == venue_id,
            Event.category == "Concert",
            Event.record_type == "event",
        )
        .order_by(Event.start_datetime.asc(), Event.id.asc())
    )
    return list(session.scalars(statement).all())
