from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any

from icalendar import Calendar
from icalendar import Event as ICalendarEvent


@dataclass(frozen=True)
class IcsEventCandidate:
    """Normalized event fields parsed from one ICS VEVENT."""

    title: str
    description: str | None
    start_datetime: datetime
    end_datetime: datetime | None
    timezone: str | None
    location_text: str | None
    source_url: str | None
    source_event_id: str | None
    all_day: bool
    raw_event: dict[str, Any]


def clean_text(value: object | None) -> str | None:
    """Return trimmed text, using None for blank optional values."""

    if value is None:
        return None
    text = str(value).strip()
    return text or None


def component_text(component: ICalendarEvent, field_name: str) -> str | None:
    """Return a trimmed text value from an ICS component."""

    return clean_text(component.get(field_name))


def decoded_datetime(value: object) -> date | datetime | None:
    """Decode an icalendar date/datetime property."""

    decoded = getattr(value, "dt", value)
    if isinstance(decoded, datetime | date):
        return decoded
    return None


def datetime_from_ics(value: date | datetime) -> tuple[datetime, bool]:
    """Convert an ICS date or datetime into a stored datetime plus all-day flag."""

    if isinstance(value, datetime):
        return value, False
    return datetime.combine(value, time.min), True


def timezone_name(component: ICalendarEvent) -> str | None:
    """Extract timezone from DTSTART params or timezone-aware datetime values."""

    dtstart = component.get("dtstart")
    if dtstart is None:
        return None

    params = getattr(dtstart, "params", {})
    tzid = clean_text(params.get("TZID")) if params else None
    if tzid:
        return tzid

    decoded = decoded_datetime(dtstart)
    if isinstance(decoded, datetime) and decoded.tzinfo is not None:
        zone_key = getattr(decoded.tzinfo, "key", None)
        if zone_key:
            return str(zone_key)
        tz_name = decoded.tzname()
        return clean_text(tz_name)
    return None


def raw_component_json(component: ICalendarEvent, all_day: bool) -> dict[str, Any]:
    """Build a JSON-serializable preview of an ICS VEVENT."""

    properties: dict[str, str] = {}
    for key, value in component.property_items():
        if key not in {"BEGIN", "END"}:
            properties[str(key)] = str(value)
    return {
        "all_day": all_day,
        "properties": properties,
    }


def parse_ics_events(raw_body: str) -> list[IcsEventCandidate]:
    """Parse VEVENT records from raw ICS text into normalized candidates."""

    calendar = Calendar.from_ical(raw_body)
    candidates: list[IcsEventCandidate] = []

    for component in calendar.walk():
        if component.name != "VEVENT":
            continue

        title = component_text(component, "summary")
        dtstart_value = component.get("dtstart")
        decoded_start = decoded_datetime(dtstart_value) if dtstart_value else None
        if title is None or decoded_start is None:
            continue

        start_datetime, all_day = datetime_from_ics(decoded_start)
        dtend_value = component.get("dtend")
        decoded_end = decoded_datetime(dtend_value) if dtend_value else None
        end_datetime = datetime_from_ics(decoded_end)[0] if decoded_end else None

        candidates.append(
            IcsEventCandidate(
                title=title,
                description=component_text(component, "description"),
                start_datetime=start_datetime,
                end_datetime=end_datetime,
                timezone=timezone_name(component),
                location_text=component_text(component, "location"),
                source_url=component_text(component, "url"),
                source_event_id=component_text(component, "uid"),
                all_day=all_day,
                raw_event=raw_component_json(component, all_day),
            )
        )

    return candidates
