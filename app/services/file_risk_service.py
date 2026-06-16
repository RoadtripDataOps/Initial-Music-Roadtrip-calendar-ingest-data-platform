import re
from collections.abc import Mapping, Sequence
from datetime import date
from urllib.parse import urlparse

from app.services.risk_service import RiskAssessment, build_assessment

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif")
SOCIAL_DOMAINS = ("facebook.com", "instagram.com", "tiktok.com", "x.com", "twitter.com")
JUNK_VALUES = {"asdf", "test test", "fake", "fake url", "example"}
SPAM_PATTERN = re.compile(r"\b(buy now|crypto|casino|viagra|free money)\b", re.I)


def cell(row: Mapping[str, str], name: str) -> str:
    return str(row.get(name, "") or "").strip()


def is_full_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def is_social_url(value: str) -> bool:
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    return any(
        host == domain or host.endswith(f".{domain}") for domain in SOCIAL_DOMAINS
    )


def is_direct_image_url(value: str) -> bool:
    parsed = urlparse(value)
    return is_full_url(value) and parsed.path.lower().endswith(IMAGE_EXTENSIONS)


def score_concert_event_rows(rows: Sequence[Mapping[str, str]]) -> RiskAssessment:
    """Score uploaded concert event rows for suspicious or invalid content."""

    score = 0
    flags: list[str] = []
    invalid_rows = 0
    today = date.today()

    for row in rows:
        row_invalid = False
        category = cell(row, "Category")
        if category and category != "Concert":
            flags.append("non_concert_category")
            score += 15
            row_invalid = True

        required_fields = [
            ("Event Name", "event_name_missing"),
            ("Headliner", "headliner_missing"),
            ("Start Date", "start_date_missing"),
            ("Timezone", "timezone_missing"),
            ("Venue Name", "venue_name_missing"),
            ("City", "city_missing"),
            ("State", "state_missing"),
        ]
        for field_name, flag in required_fields:
            if not cell(row, field_name):
                flags.append(flag)
                score += 5
                row_invalid = True

        if not cell(row, "Event URL") and not cell(row, "Tickets Link"):
            flags.append("event_or_ticket_url_missing")
            score += 5
            row_invalid = True

        if not cell(row, "Venue Address") and not (
            cell(row, "Latitude") and cell(row, "Longitude")
        ):
            flags.append("venue_address_or_coordinates_missing")
            score += 5
            row_invalid = True

        for field_name in ["Event URL", "Tickets Link"]:
            value = cell(row, field_name)
            if value and not is_full_url(value):
                flags.append("url_field_not_full_url")
                score += 5
                row_invalid = True

        main_image = cell(row, "Main Image URL")
        if main_image:
            if is_social_url(main_image):
                flags.append("main_image_social_media_url")
                score += 20
                row_invalid = True
            elif not is_direct_image_url(main_image):
                flags.append("main_image_not_direct_public_image")
                score += 10
                row_invalid = True

        additional_images = cell(row, "Additional Image URL(s)")
        if additional_images and any(
            is_social_url(part.strip())
            for part in re.split(r"[\n|,]+", additional_images)
        ):
            flags.append("additional_image_social_media_url")
            score += 10
            row_invalid = True

        start_date = cell(row, "Start Date")
        if start_date:
            try:
                parsed_date = date.fromisoformat(start_date)
            except ValueError:
                flags.append("event_date_invalid")
                score += 10
                row_invalid = True
            else:
                if (
                    parsed_date.year < today.year - 1
                    or parsed_date.year > today.year + 5
                ):
                    flags.append("event_date_implausible")
                    score += 10
                    row_invalid = True

        combined_text = f"{cell(row, 'Event Name')} {cell(row, 'Description')}"
        if SPAM_PATTERN.search(combined_text):
            flags.append("obvious_spam_text")
            score += 25
            row_invalid = True

        if row_invalid:
            invalid_rows += 1

    if rows and invalid_rows / len(rows) >= 0.5:
        flags.append("too_many_invalid_rows")
        score += 35

    return build_assessment(score, flags)


def score_calendar_source_rows(
    rows: Sequence[Mapping[str, str]],
    existing_canonical_urls: set[str] | None = None,
) -> RiskAssessment:
    """Score uploaded calendar source rows."""

    existing = existing_canonical_urls or set()
    seen_urls: set[str] = set()
    score = 0
    flags: list[str] = []

    for row in rows:
        organization = cell(row, "Organization Name")
        calendar_url = cell(row, "Calendar URL")
        contact_email = cell(row, "Contact Email")
        authorization = cell(row, "Authorization Confirmed").lower()
        category = cell(row, "Expected Category")

        if not organization:
            flags.append("organization_name_missing")
            score += 10
        if not calendar_url:
            flags.append("calendar_url_missing")
            score += 10
        if not contact_email:
            flags.append("contact_email_missing")
            score += 10
        if authorization not in {"true", "yes", "1"}:
            flags.append("authorization_missing")
            score += 20
        if category and category != "Concert":
            flags.append("expected_category_not_concert")
            score += 15
        if calendar_url:
            lowered_url = calendar_url.lower()
            if lowered_url in seen_urls:
                flags.append("duplicate_calendar_url_in_file")
                score += 10
            seen_urls.add(lowered_url)
            if lowered_url in existing:
                flags.append("calendar_url_already_exists")
                score += 10
        if any(cell(row, field).lower() in JUNK_VALUES for field in row):
            flags.append("junk_or_test_values")
            score += 15

    if rows and score >= len(rows) * 20:
        flags.append("too_many_invalid_rows")
        score += 25

    return build_assessment(score, flags)
