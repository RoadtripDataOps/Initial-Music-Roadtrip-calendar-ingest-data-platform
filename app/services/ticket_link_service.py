from __future__ import annotations

from dataclasses import dataclass, replace
from urllib.parse import parse_qsl, urlparse

from app.services.file_risk_service import is_full_url
from app.services.source_taxonomy_service import (
    detect_source_key,
    is_affiliate_tracking_source,
    normalized_domain,
)

VENDOR_AFFILIATE_TOKEN = "city" + "spark"

TICKET_LINK_CATEGORIES = (
    "direct",
    "redirect_or_handoff",
    "platform_event",
    "platform_generic_or_app",
    "non_ticket",
    "blank",
    "suspicious",
    "unresolved",
)


@dataclass(frozen=True)
class TicketLinkAssessment:
    category: str
    usable: bool
    recommended_url: str | None
    repair_suggestion: str
    quality_score: float
    flags: tuple[str, ...] = ()
    repair_strategy: str = "manual_review"
    repair_source: str | None = None
    provider_key: str | None = None
    provider_domain: str | None = None


@dataclass(frozen=True)
class TicketLinkCandidate:
    url: str | None
    source: str
    priority: int


def normalized_host(hostname: str | None) -> str:
    host = (hostname or "").lower().removeprefix("www.")
    return host


def assessment_provider_fields(url: str | None) -> tuple[str | None, str | None]:
    return detect_source_key(url), normalized_domain(url)


def path_has_any(path: str, tokens: tuple[str, ...]) -> bool:
    return any(token in path for token in tokens)


def query_flags(url: str) -> list[str]:
    parsed = urlparse(url)
    flags: list[str] = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lowered_key = key.lower()
        lowered_value = value.lower()
        if lowered_key.startswith("utm_"):
            flags.append("tracking parameter")
        if lowered_key in {"fbclid", "gclid"}:
            flags.append("click tracking parameter")
        if lowered_key in {"aff", "affid", "affiliate", "intsrc", "cid"}:
            flags.append("affiliate/tracking parameter")
        if lowered_key == "aff" and lowered_value == VENDOR_AFFILIATE_TOKEN:
            flags.append("vendor affiliate parameter")
        if VENDOR_AFFILIATE_TOKEN in f"{lowered_key}={lowered_value}":
            flags.append("vendor tracking token")
    return sorted(set(flags))


def session_or_cart_flags(url: str) -> list[str]:
    lowered = url.lower()
    flags: list[str] = []
    for token in ("cart", "session", "queueittoken", "checkout-external"):
        if token in lowered:
            flags.append("session/cart-like ticket URL")
            break
    return flags


def domain_flags(provider_key: str | None) -> list[str]:
    if is_affiliate_tracking_source(provider_key):
        return ["affiliate/tracking domain"]
    return []


def with_nonblocking_flags(
    category: str,
    usable: bool,
    url: str,
    suggestion: str,
    score: float,
    repair_strategy: str,
) -> TicketLinkAssessment:
    provider_key, provider_domain = assessment_provider_fields(url)
    flags = tuple(sorted(set(query_flags(url) + domain_flags(provider_key))))
    if flags:
        suggestion = f"{suggestion} Remove tracking parameters before publish."
        score = max(score - 12, 0)
    return TicketLinkAssessment(
        category=category,
        usable=usable,
        recommended_url=url if usable else None,
        repair_suggestion=suggestion,
        quality_score=score,
        flags=flags,
        repair_strategy=repair_strategy,
        provider_key=provider_key,
        provider_domain=provider_domain,
    )


def classify_ticket_link(url: str | None) -> TicketLinkAssessment:
    """Classify one ticket URL candidate for review and repair."""

    cleaned = (url or "").strip()
    if not cleaned:
        return TicketLinkAssessment(
            category="blank",
            usable=False,
            recommended_url=None,
            repair_suggestion="No ticket URL supplied.",
            quality_score=0.0,
            repair_strategy="api_backfill_required",
        )

    if not is_full_url(cleaned):
        return TicketLinkAssessment(
            category="suspicious",
            usable=False,
            recommended_url=None,
            repair_suggestion="Ticket URL must be a full http or https URL.",
            quality_score=5.0,
            flags=("malformed ticket URL",),
            repair_strategy="reject_malformed",
        )

    parsed = urlparse(cleaned)
    host = normalized_host(parsed.hostname)
    path = parsed.path.lower()
    lowered = cleaned.lower()
    cart_flags = session_or_cart_flags(cleaned)
    provider_key, provider_domain = assessment_provider_fields(cleaned)

    if is_affiliate_tracking_source(provider_key):
        return TicketLinkAssessment(
            category="redirect_or_handoff",
            usable=False,
            recommended_url=None,
            repair_suggestion=(
                "Affiliate or tracking handoff detected; use the final "
                "event-specific ticket URL when available."
            ),
            quality_score=32.0,
            flags=tuple(
                sorted(
                    set(
                        cart_flags
                        + query_flags(cleaned)
                        + domain_flags(provider_key)
                    )
                )
            ),
            repair_strategy="resolve_affiliate_handoff",
            provider_key=provider_key,
            provider_domain=provider_domain,
        )

    if "eventbrite." in host and "/checkout-external" in path:
        return TicketLinkAssessment(
            category="platform_generic_or_app",
            usable=False,
            recommended_url=None,
            repair_suggestion=(
                "Eventbrite checkout-external links are app handoffs; use the "
                "event page or provider ticket field instead."
            ),
            quality_score=18.0,
            flags=tuple(cart_flags),
            repair_strategy="reject_checkout_external",
            provider_key=provider_key,
            provider_domain=provider_domain,
        )

    if host == "link.dice.fm" or host.endswith(".link.dice.fm"):
        return TicketLinkAssessment(
            category="platform_generic_or_app",
            usable=False,
            recommended_url=None,
            repair_suggestion=(
                "Generic DICE handoff links are not final ticket destinations."
            ),
            quality_score=18.0,
            flags=tuple(cart_flags),
            repair_strategy="reject_generic_app_handoff",
            provider_key=provider_key,
            provider_domain=provider_domain,
        )

    if "ticketmaster." in host:
        if path in {"", "/"} or path_has_any(
            path,
            ("/artist/", "/discover", "/browse", "/music"),
        ):
            return TicketLinkAssessment(
                category="platform_generic_or_app",
                usable=False,
                recommended_url=None,
                repair_suggestion=(
                    "Ticketmaster home, artist, and generic pages need an "
                    "event-specific ticket URL."
                ),
                quality_score=20.0,
                flags=tuple(cart_flags),
                repair_strategy="reject_generic_platform_page",
                provider_key=provider_key,
                provider_domain=provider_domain,
            )
        if "/event/" in path:
            return with_nonblocking_flags(
                "platform_event",
                True,
                cleaned,
                "Event-specific Ticketmaster page accepted.",
                84.0,
                "keep_platform_event",
            )

    if "eventbrite." in host and "/e/" in path:
        return with_nonblocking_flags(
            "platform_event",
            True,
            cleaned,
            "Event-specific Eventbrite page accepted.",
            84.0,
            "keep_platform_event",
        )

    if host.endswith("dice.fm"):
        if path_has_any(path, ("/event/", "/events/")):
            return with_nonblocking_flags(
                "platform_event",
                True,
                cleaned,
                "Event-specific DICE page accepted.",
                78.0,
                "keep_platform_event",
            )
        return TicketLinkAssessment(
            category="platform_generic_or_app",
            usable=False,
            recommended_url=None,
            repair_suggestion="DICE URL is not event-specific.",
            quality_score=20.0,
            flags=tuple(cart_flags),
            repair_strategy="reject_generic_platform_page",
            provider_key=provider_key,
            provider_domain=provider_domain,
        )

    platform_hosts = (
        "bandsintown.com",
        "axs.com",
        "ticketweb.com",
        "tixr.com",
        "etix.com",
        "eventim.com",
        "seated.com",
        "seetickets.com",
        "seatgeek.com",
        "sofarsounds.com",
        "suitehop.com",
        "viagogo.com",
        "opendate.io",
        "universe.com",
        "skiddle.com",
        "humanitix.com",
        "tickettailor.com",
        "buytickets.at",
        "showpass.com",
        "ovationtix.com",
        "holdmyticket.com",
        "ticketnetwork.com",
        "mercurywebservices.com",
        "vividseats.com",
        "prekindle.com",
        "tixtrack.com",
        "nliven.co",
        "zeffy.com",
        "eventvesta.com",
        "outhousetickets.com",
        "venuepilot.com",
        "biletix.com",
        "speakeasygo.com",
        "eventnoire.com",
        "my805tix.com",
        "805tix.com",
        "24tix.com",
        "simpletix.com",
        "tix.com",
        "ticketleap.com",
        "aftontickets.com",
        "aftonshows.com",
        "instantseats.com",
    )
    if any(host == domain or host.endswith(f".{domain}") for domain in platform_hosts):
        if path_has_any(
            path,
            (
                "/e/",
                "/event",
                "/events",
                "/ticket",
                "/tickets",
                "/show",
                "/series",
                "/performance",
                "/whats-on",
            ),
        ):
            return with_nonblocking_flags(
                "platform_event",
                True,
                cleaned,
                "Event-specific platform ticket page accepted.",
                82.0,
                "keep_platform_event",
            )
        return TicketLinkAssessment(
            category="platform_generic_or_app",
            usable=False,
            recommended_url=None,
            repair_suggestion="Platform URL needs an event-specific path.",
            quality_score=24.0,
            flags=tuple(cart_flags),
            repair_strategy="reject_generic_platform_page",
            provider_key=provider_key,
            provider_domain=provider_domain,
        )

    redirect_hosts = (
        "bit.ly",
        "tinyurl.com",
        "linktr.ee",
        "lnk.to",
        "seetickets.us",
    )
    if host in redirect_hosts or "redirect" in host:
        if "ticket" in lowered or "tix" in lowered:
            return with_nonblocking_flags(
                "redirect_or_handoff",
                True,
                cleaned,
                "Redirect appears to point at a ticket destination.",
                68.0,
                "keep_redirect_or_handoff",
            )
        return TicketLinkAssessment(
            category="unresolved",
            usable=False,
            recommended_url=None,
            repair_suggestion=(
                "Redirect/handoff URL does not clearly point to tickets."
            ),
            quality_score=28.0,
            flags=tuple(cart_flags),
            repair_strategy="api_backfill_required",
            provider_key=provider_key,
            provider_domain=provider_domain,
        )

    if cart_flags:
        return TicketLinkAssessment(
            category="suspicious",
            usable=False,
            recommended_url=None,
            repair_suggestion="Use a stable event ticket page, not a cart/session URL.",
            quality_score=12.0,
            flags=tuple(cart_flags + query_flags(cleaned)),
            repair_strategy="reject_session_or_cart_url",
            provider_key=provider_key,
            provider_domain=provider_domain,
        )

    if any(token in host for token in ("ticket", "tix", "boxoffice")) or any(
        token in path for token in ("ticket", "tix", "buy")
    ):
        return with_nonblocking_flags(
            "direct",
            True,
            cleaned,
            "Direct ticket page accepted.",
            92.0,
            "keep_direct",
        )

    if any(token in lowered for token in ("calendar", "homepage", "about", "venue")):
        return TicketLinkAssessment(
            category="non_ticket",
            usable=False,
            recommended_url=None,
            repair_suggestion="URL looks informational rather than ticketable.",
            quality_score=30.0,
            flags=tuple(query_flags(cleaned)),
            repair_strategy="reject_non_ticket",
            provider_key=provider_key,
            provider_domain=provider_domain,
        )

    return with_nonblocking_flags(
        "unresolved",
        False,
        cleaned,
        "Review manually; no clear ticket pattern was detected.",
        42.0,
        "api_backfill_required",
    )


def choose_ticket_link(
    candidates: list[TicketLinkCandidate],
) -> TicketLinkAssessment:
    """Return the best usable ticket URL assessment from ordered candidates."""

    ordered = sorted(candidates, key=lambda candidate: candidate.priority)
    first_nonblank: TicketLinkAssessment | None = None
    for candidate in ordered:
        assessment = classify_ticket_link(candidate.url)
        if assessment.category != "blank":
            assessment = replace(assessment, repair_source=candidate.source)
        if assessment.category != "blank" and first_nonblank is None:
            first_nonblank = assessment
        if assessment.usable:
            return assessment
    if first_nonblank:
        return first_nonblank
    return classify_ticket_link(None)
