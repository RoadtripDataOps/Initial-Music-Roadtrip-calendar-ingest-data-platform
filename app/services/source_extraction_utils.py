from __future__ import annotations

import re
from datetime import datetime
from html import unescape
from urllib.parse import urljoin, urlparse

MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

EVENT_LINK_TOKENS = (
    "event",
    "events",
    "calendar",
    "concert",
    "show",
    "shows",
    "music",
    "festival",
    "tickets",
)


def clean_text(value: object) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", unescape(str(value))).strip()
    return cleaned or None


def strip_tags(value: str) -> str:
    return clean_text(re.sub(r"<[^>]+>", " ", value)) or ""


def as_list(value: object) -> list[object]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def first_text(value: object) -> str | None:
    if isinstance(value, list):
        for item in value:
            found = first_text(item)
            if found:
                return found
        return None
    if isinstance(value, dict):
        for key in ("name", "url", "@id", "text"):
            found = clean_text(value.get(key))
            if found:
                return found
        return None
    return clean_text(value)


def absolute_url(url: str | None, base_url: str) -> str | None:
    cleaned = clean_text(url)
    if not cleaned:
        return None
    return urljoin(base_url, cleaned)


def is_full_url(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def parse_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def parse_datetime_value(value: object) -> datetime | None:
    text = clean_text(value)
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized):
        normalized = f"{normalized}T00:00:00"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        pass

    numeric = re.search(
        r"\b(?P<month>\d{1,2})/(?P<day>\d{1,2})/(?P<year>\d{4})"
        r"(?:\s+(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>am|pm)?)?",
        text,
        flags=re.IGNORECASE,
    )
    if numeric:
        return _datetime_from_parts(numeric.groupdict())

    named = re.search(
        r"\b(?P<month_name>"
        + "|".join(MONTHS)
        + r")\.?\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?[,]?\s+(?P<year>\d{4})"
        r"(?:\s+(?:at\s+)?(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?"
        r"\s*(?P<ampm>am|pm)?)?",
        text,
        flags=re.IGNORECASE,
    )
    if not named:
        named = re.search(
            r"\b(?P<day>\d{1,2})(?:st|nd|rd|th)?\s+(?P<month_name>"
            + "|".join(MONTHS)
            + r")\.?\s+(?P<year>\d{4})"
            r"(?:\s+(?:at\s+)?(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?"
            r"\s*(?P<ampm>am|pm)?)?",
            text,
            flags=re.IGNORECASE,
        )
    if named:
        return _datetime_from_parts(named.groupdict())
    return None


def _datetime_from_parts(parts: dict[str, str | None]) -> datetime | None:
    month_value = parts.get("month")
    month_name = parts.get("month_name")
    month = int(month_value) if month_value else MONTHS.get((month_name or "").lower())
    day = int(parts["day"] or "0")
    year = int(parts["year"] or "0")
    hour = int(parts.get("hour") or "0")
    minute = int(parts.get("minute") or "0")
    ampm = (parts.get("ampm") or "").lower()
    if ampm == "pm" and hour < 12:
        hour += 12
    if ampm == "am" and hour == 12:
        hour = 0
    if not month:
        return None
    try:
        return datetime(year, month, day, hour, minute)
    except ValueError:
        return None


def looks_like_event_link(url: str, text: str) -> tuple[bool, str]:
    haystack = f"{url} {text}".lower()
    for token in EVENT_LINK_TOKENS:
        if token in haystack:
            return True, f"contains {token}"
    return False, "no event-like token"
