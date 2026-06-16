from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, field_validator


class CalendarSourceCreate(BaseModel):
    """Validated form data for a submitted calendar source."""

    organization_name: str
    calendar_url: str
    contact_email: str
    permission_confirmed: bool

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("organization_name")
    @classmethod
    def organization_required(cls, value: str) -> str:
        if not value:
            raise ValueError("Organization name is required.")
        return value

    @field_validator("calendar_url")
    @classmethod
    def calendar_url_must_be_http(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Calendar URL must be a valid http or https URL.")
        return value

    @field_validator("contact_email")
    @classmethod
    def contact_email_required(cls, value: str) -> str:
        if "@" not in value or "." not in value.rsplit("@", maxsplit=1)[-1]:
            raise ValueError("Contact email must be a valid email address.")
        return value

    @field_validator("permission_confirmed")
    @classmethod
    def permission_must_be_confirmed(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Authorization confirmation is required.")
        return value


class SourceStatusUpdate(BaseModel):
    """Validated admin status update."""

    status: Literal["pending", "approved", "paused"]
