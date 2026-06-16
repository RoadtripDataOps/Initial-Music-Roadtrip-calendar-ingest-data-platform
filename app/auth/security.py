from __future__ import annotations

import hmac
import secrets
from typing import Annotated

from fastapi import Form, HTTPException, Request, status

from app.auth.passwords import verify_password
from app.core.config import Settings

ADMIN_AUTHENTICATED_KEY = "admin_authenticated"
ADMIN_USERNAME_KEY = "admin_username"
ADMIN_CSRF_KEY = "admin_csrf_token"


def safe_admin_next_path(value: str | None) -> str:
    """Return a safe admin-local redirect target."""

    if value and value.startswith("/admin/") and not value.startswith("/admin/login"):
        return value
    if value and value.startswith("/preview"):
        return value
    return "/admin/dashboard"


def is_admin_authenticated(request: Request) -> bool:
    return request.session.get(ADMIN_AUTHENTICATED_KEY) is True


def admin_username(request: Request) -> str | None:
    value = request.session.get(ADMIN_USERNAME_KEY)
    return str(value) if value else None


def login_admin_session(request: Request, username: str) -> None:
    request.session.clear()
    request.session[ADMIN_AUTHENTICATED_KEY] = True
    request.session[ADMIN_USERNAME_KEY] = username
    ensure_csrf_token(request)


def logout_admin_session(request: Request) -> None:
    request.session.clear()


def ensure_csrf_token(request: Request) -> str:
    token = request.session.get(ADMIN_CSRF_KEY)
    if not isinstance(token, str) or not token:
        token = secrets.token_urlsafe(32)
        request.session[ADMIN_CSRF_KEY] = token
    return token


def validate_csrf_token(request: Request, submitted_token: str | None) -> None:
    expected_token = request.session.get(ADMIN_CSRF_KEY)
    if (
        not isinstance(expected_token, str)
        or not submitted_token
        or not hmac.compare_digest(expected_token, submitted_token)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid admin CSRF token.",
        )


def admin_template_context(request: Request) -> dict[str, str | bool]:
    return {
        "admin_user": admin_username(request) or "",
        "csrf_token": ensure_csrf_token(request),
        "is_admin_page": True,
    }


def verify_admin_login(
    settings: Settings,
    username: str,
    password: str,
) -> bool:
    if not hmac.compare_digest(username, settings.admin_username):
        return False
    return verify_password(password, settings.effective_admin_password_hash)


def require_admin(request: Request) -> str:
    """Require an authenticated admin session for one route."""

    username = admin_username(request)
    if is_admin_authenticated(request) and username:
        return username

    if request.method in {"GET", "HEAD"}:
        next_path = request.url.path
        if request.url.query:
            next_path = f"{next_path}?{request.url.query}"
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            detail="Admin login required.",
            headers={"Location": f"/admin/login?next={next_path}"},
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Admin login required.",
    )


def require_admin_csrf(
    request: Request,
    csrf_token: Annotated[str, Form()] = "",
) -> str:
    """Require admin login and a valid session CSRF token for form POSTs."""

    username = require_admin(request)
    validate_csrf_token(request, csrf_token)
    return username
