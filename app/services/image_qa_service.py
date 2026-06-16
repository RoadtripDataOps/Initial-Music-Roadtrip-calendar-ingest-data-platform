from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Event, EventVenue, ImageCandidate, utc_now
from app.services.file_risk_service import is_full_url, is_social_url

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif")
IMAGE_CONTENT_PREFIX = "image/"
TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
}
SOCIAL_OR_PAGE_DOMAINS = (
    "facebook.com",
    "instagram.com",
    "x.com",
    "twitter.com",
    "tiktok.com",
    "youtube.com",
    "pinterest.com",
    "threads.net",
    "linkedin.com",
    "yelp.com",
)
NON_IMAGE_PAGE_DOMAINS = (
    "eventbrite.com",
    "ticketmaster.com",
    "bandsintown.com",
    "axs.com",
    "dice.fm",
    "link.dice.fm",
)
STOCK_TOKENS = (
    "placeholder",
    "default",
    "generic",
    "stock",
    "no-image",
    "missing",
    "jambase-default",
    "event-placeholder",
)
POSTER_TOKENS = ("poster", "flyer", "admat", "logo")
IMAGE_ROLES = (
    "artist_live",
    "artist_press",
    "event_provider",
    "venue_live",
    "venue_exterior",
    "logo",
    "poster",
    "flyer",
    "admat",
    "album_art",
    "social_screenshot",
    "generic_crowd",
    "stock_placeholder",
    "unknown",
)
RESCUE_SOURCES = (
    "provider_event_image",
    "provider_promo_image",
    "provider_artist_image",
    "provider_venue_image",
    "official_artist_site",
    "official_venue_site",
    "event_page_og_image",
    "ticketing_page_image",
    "social_graphic_reference",
    "manual_upload",
    "unknown",
)
RESCUE_SOURCE_PRIORITIES = {
    "official_artist_site": 18,
    "provider_artist_image": 30,
    "provider_event_image": 58,
    "event_page_og_image": 62,
    "official_venue_site": 82,
    "provider_venue_image": 88,
    "provider_promo_image": 160,
    "ticketing_page_image": 170,
    "manual_upload": 72,
    "social_graphic_reference": 220,
    "unknown": 180,
}
CLEARED_CLEARANCE_STATUSES = {
    "approved",
    "licensed",
    "partner_supplied",
    "provider_allowed",
}
PENDING_CLEARANCE_STATUSES = {"unknown", "needs_approval", None}
SELECTED_PENDING_STATUS = "selected_pending_approval"


@dataclass(frozen=True)
class ImageCandidateInput:
    image_url: str
    event_id: int | None = None
    venue_id: int | None = None
    source_type: str = "unknown"
    source_provider: str | None = None
    source_url: str | None = None
    source_chain_json: str | None = None
    image_role: str = "unknown"
    clearance_status: str = "unknown"
    candidate_status: str = "pending_review"
    width: int | None = None
    height: int | None = None
    content_type: str | None = None
    file_size_bytes: int | None = None
    rescue_source: str = "unknown"
    rescue_priority: int = 100
    generic_detection_score: float = 0.0
    generic_detection_reasons_json: str = "[]"
    text_graphic_score: float = 0.0
    poster_flyer_score: float = 0.0
    admat_score: float = 0.0
    artist_match_score: float = 0.0
    venue_context_score: float = 0.0
    music_signal_score: float = 0.0
    selected_reason: str | None = None
    selection_explanation_json: str = "{}"
    source_payload_path: str | None = None
    source_evidence_only: bool = False
    can_be_final_image: bool = True


@dataclass(frozen=True)
class ImageAnalysisResult:
    text_detected: bool = False
    text_area_ratio: float | None = None
    watermark_detected: bool = False
    watermark_position: str | None = None
    logo_detected: bool = False
    logo_area_ratio: float | None = None
    poster_or_flyer_probability: float | None = None
    live_performance_probability: float | None = None
    artist_subject_probability: float | None = None
    venue_in_action_probability: float | None = None
    stock_placeholder_probability: float | None = None
    food_or_drink_probability: float | None = None
    generic_crowd_probability: float | None = None
    unrelated_place_probability: float | None = None
    image_aesthetic_score: float | None = None
    image_sharpness_score: float | None = None
    notes: str | None = None


@dataclass(frozen=True)
class ImageCandidateFilters:
    event_id: int | None = None
    venue_id: int | None = None
    source_type: str | None = None
    source_provider: str | None = None
    candidate_status: str | None = None
    clearance_status: str | None = None
    image_role: str | None = None
    quality_flag: str | None = None
    stock_placeholder_candidate: bool = False
    text_detected: bool = False
    watermark_detected: bool = False
    poster_or_flyer: bool = False
    missing_dimensions: bool = False
    low_resolution: bool = False
    needs_approval: bool = False
    selected: bool | None = None
    selected_pending_approval: bool = False
    selected_and_cleared: bool = False
    selected_but_needs_approval: bool = False
    hard_blocked: bool = False
    missing_image: bool = False
    rescue_source: str | None = None
    source_evidence_only: bool = False
    can_be_final_image: bool | None = None
    selected_by_rescue: bool = False
    missing_artist_image: bool = False


def normalize_image_url(url: str) -> str:
    cleaned = url.strip()
    if not is_full_url(cleaned):
        return cleaned
    parsed = urlparse(cleaned)
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMS
    ]
    return urlunparse(
        (
            parsed.scheme.lower(),
            (parsed.netloc or "").lower(),
            parsed.path,
            "",
            urlencode(query, doseq=True),
            "",
        )
    )


def host_matches(host: str, domains: tuple[str, ...]) -> bool:
    return any(host == domain or host.endswith(f".{domain}") for domain in domains)


def is_likely_direct_image_asset(
    url: str,
    content_type: str | None = None,
) -> bool:
    if content_type:
        normalized_content_type = content_type.lower().split(";")[0].strip()
        if normalized_content_type.startswith(IMAGE_CONTENT_PREFIX):
            return True
        return False
    if not is_full_url(url):
        return False
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    path = parsed.path.lower()
    if host_matches(host, SOCIAL_OR_PAGE_DOMAINS):
        return False
    if host == "google.com" and path.startswith("/imgres"):
        return False
    if "googleusercontent.com" in host and not path.endswith(IMAGE_EXTENSIONS):
        return False
    if host_matches(host, NON_IMAGE_PAGE_DOMAINS):
        return path.endswith(IMAGE_EXTENSIONS)
    if path.endswith(IMAGE_EXTENSIONS):
        return True
    cdn_terms = ("cdn", "cloudfront", "images", "image", "media", "uploads")
    if any(term in host for term in cdn_terms) or any(
        term in path for term in cdn_terms
    ):
        return True
    return False


def orientation_for(width: int | None, height: int | None) -> str:
    if not width or not height:
        return "unknown"
    ratio = width / height
    if ratio >= 2.2:
        return "panoramic"
    if 1.15 <= ratio < 2.2:
        return "landscape"
    if 0.85 <= ratio < 1.15:
        return "square"
    return "portrait"


def role_score(role: str) -> float:
    scores = {
        "artist_live": 100.0,
        "artist_press": 88.0,
        "event_provider": 72.0,
        "venue_live": 56.0,
        "venue_exterior": 42.0,
        "unknown": 24.0,
        "generic_crowd": 10.0,
        "poster": 0.0,
        "flyer": 0.0,
        "admat": 0.0,
        "logo": 0.0,
        "stock_placeholder": 0.0,
    }
    return scores.get(role, 20.0)


def provenance_score(source_type: str, clearance_status: str) -> float:
    scores = {
        "partner_supplied": 94.0,
        "official_artist_site": 88.0,
        "official_venue_site": 82.0,
        "press_kit": 84.0,
        "manual": 78.0,
        "upload": 72.0,
        "provider": 58.0,
        "spotify": 54.0,
        "serpapi": 45.0,
        "venue": 50.0,
        "unknown": 25.0,
    }
    value = scores.get(source_type, 35.0)
    if clearance_status in {"approved", "licensed", "partner_supplied"}:
        value += 8
    if clearance_status == "provider_allowed":
        value += 4
    if clearance_status == "rejected":
        value = 0
    return min(value, 100.0)


def approval_score(candidate_status: str, clearance_status: str) -> float:
    if candidate_status == "rejected" or clearance_status == "rejected":
        return 0.0
    if candidate_status == "accepted":
        return 96.0
    if clearance_status in CLEARED_CLEARANCE_STATUSES:
        return 86.0
    if clearance_status in {"needs_approval", "unknown"}:
        return 74.0
    return 50.0


def technical_score(candidate: ImageCandidate) -> tuple[float, list[str]]:
    flags: list[str] = []
    score = 100.0
    if not candidate.is_direct_image_asset:
        flags.append("not direct image asset")
        score -= 40
    if candidate.is_social_media_url:
        flags.append("social media image URL")
        score -= 45
    if candidate.is_accessible is False:
        flags.append("broken or inaccessible image")
        score -= 55
    if candidate.content_type and not candidate.content_type.lower().startswith(
        IMAGE_CONTENT_PREFIX
    ):
        flags.append("content-type mismatch")
        score -= 45
    if candidate.width is None or candidate.height is None:
        flags.append("missing dimensions")
        score -= 12
    else:
        shortest = min(candidate.width, candidate.height)
        if candidate.width < 720 or shortest < 400:
            flags.append("low resolution image")
            score -= 35
        elif candidate.width < 1200:
            flags.append("below preferred 1200px width")
            score -= 10
        if candidate.orientation in {"portrait", "panoramic"}:
            flags.append(f"{candidate.orientation} image")
            score -= 8
    return max(score, 0.0), flags


def subject_score(candidate: ImageCandidate) -> tuple[float, list[str]]:
    flags: list[str] = []
    score = 40.0
    if candidate.appears_live_performance:
        score += 30
    if candidate.appears_artist_subject:
        score += 26
    if candidate.appears_venue_in_action:
        score += 18
    if candidate.appears_food_or_drink:
        flags.append("food or drink image")
        score -= 24
    if candidate.appears_unrelated_place:
        flags.append("unrelated place image")
        score -= 36
    if candidate.appears_generic_crowd:
        flags.append("generic crowd image")
        score -= 22
    return max(min(score, 100.0), 0.0), flags


def stock_or_poster_flags(candidate: ImageCandidate) -> list[str]:
    lowered = f"{candidate.image_url} {candidate.image_role}".lower()
    flags: list[str] = []
    if any(token in lowered for token in STOCK_TOKENS):
        flags.append("stock_placeholder_candidate")
    if any(token in lowered for token in POSTER_TOKENS):
        flags.append("poster_or_flyer_candidate")
    return flags


def _json_string_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if str(item).strip()]


def rescue_source_for_candidate(candidate: ImageCandidate) -> str:
    if candidate.rescue_source in RESCUE_SOURCES and candidate.rescue_source:
        return candidate.rescue_source
    if candidate.image_role in {"artist_live", "artist_press"}:
        if candidate.source_type in {"spotify", "official_artist_site"}:
            return "official_artist_site"
        return "provider_artist_image"
    if candidate.image_role in {"venue_live", "venue_exterior"}:
        return "provider_venue_image"
    if candidate.image_role in {"poster", "flyer", "admat"}:
        return "provider_promo_image"
    if candidate.image_role in {"logo", "social_screenshot"}:
        return "social_graphic_reference"
    if candidate.source_type in {"manual", "upload", "partner_supplied"}:
        return "manual_upload"
    if candidate.source_type == "official_venue_site":
        return "official_venue_site"
    if candidate.source_type == "official_artist_site":
        return "official_artist_site"
    if candidate.source_type == "provider":
        return "provider_event_image"
    return "unknown"


def rescue_priority_for_candidate(candidate: ImageCandidate) -> int:
    source_priority = RESCUE_SOURCE_PRIORITIES.get(
        candidate.rescue_source or "unknown",
        RESCUE_SOURCE_PRIORITIES["unknown"],
    )
    role_priorities = {
        "artist_live": 10,
        "artist_press": 20,
        "event_provider": 55,
        "venue_live": 80,
        "venue_exterior": 100,
        "generic_crowd": 190,
        "poster": 200,
        "flyer": 200,
        "admat": 205,
        "logo": 220,
        "social_screenshot": 225,
        "stock_placeholder": 230,
        "unknown": 180,
    }
    path = (candidate.source_payload_path or "").lower()
    path_priority = 100
    if "performer" in path and "image" in path:
        path_priority = 30
    elif "spotify" in path:
        path_priority = 40
    elif "primaryimage.large" in path:
        path_priority = 60
    elif "jambase.image" in path:
        path_priority = 70
    elif "location.image" in path:
        path_priority = 90
    elif "primaryimage.small" in path:
        path_priority = 120
    elif "x-promoimage" in path or "promo" in path:
        path_priority = 170
    return min(
        int(candidate.rescue_priority or 100),
        source_priority,
        role_priorities.get(candidate.image_role, 180),
        path_priority,
    )


def generic_detection_reasons_for_candidate(candidate: ImageCandidate) -> list[str]:
    lowered = (
        f"{candidate.image_url} {candidate.normalized_image_url or ''} "
        f"{candidate.image_role} {candidate.source_payload_path or ''}"
    ).lower()
    reasons = set(_json_string_list(candidate.generic_detection_reasons_json))
    if any(token in lowered for token in STOCK_TOKENS):
        reasons.add("generic or placeholder filename")
    if candidate.image_role == "stock_placeholder":
        reasons.add("image role is stock placeholder")
    if candidate.appears_stock_or_placeholder:
        reasons.add("stock or placeholder detected")
    if (
        candidate.reused_across_event_count >= 3
        and candidate.image_role not in {"venue_live", "venue_exterior"}
    ):
        reasons.add("reused across unrelated events")
    if (
        candidate.image_role == "event_provider"
        and not candidate.appears_artist_subject
        and not candidate.appears_live_performance
        and not candidate.appears_venue_in_action
        and candidate.rescue_source == "provider_event_image"
    ):
        reasons.add("provider event image lacks artist, venue, or music signal")
    return sorted(reasons)


def update_rescue_scores(candidate: ImageCandidate) -> None:
    candidate.rescue_source = rescue_source_for_candidate(candidate)
    candidate.rescue_priority = rescue_priority_for_candidate(candidate)

    if candidate.has_text_detected or (candidate.text_area_ratio or 0) >= 0.18:
        candidate.text_graphic_score = max(candidate.text_graphic_score or 0.0, 90.0)
    elif candidate.image_role in {"poster", "flyer", "admat", "social_screenshot"}:
        candidate.text_graphic_score = max(candidate.text_graphic_score or 0.0, 55.0)

    if candidate.appears_poster_or_flyer or candidate.image_role in {
        "poster",
        "flyer",
        "admat",
    }:
        candidate.poster_flyer_score = max(candidate.poster_flyer_score or 0.0, 95.0)
    if candidate.image_role == "admat" or "x-promoimage" in (
        candidate.source_payload_path or ""
    ).lower():
        candidate.admat_score = max(candidate.admat_score or 0.0, 95.0)

    if candidate.appears_artist_subject or candidate.image_role in {
        "artist_live",
        "artist_press",
    }:
        candidate.artist_match_score = max(candidate.artist_match_score or 0.0, 88.0)
    if candidate.image_role in {"artist_live", "artist_press"}:
        candidate.music_signal_score = max(candidate.music_signal_score or 0.0, 85.0)
    if candidate.appears_live_performance:
        candidate.music_signal_score = max(candidate.music_signal_score or 0.0, 92.0)
    if candidate.appears_venue_in_action or candidate.image_role == "venue_live":
        candidate.venue_context_score = max(
            candidate.venue_context_score or 0.0,
            82.0,
        )
        candidate.music_signal_score = max(candidate.music_signal_score or 0.0, 70.0)
    if candidate.image_role == "venue_exterior":
        candidate.venue_context_score = max(
            candidate.venue_context_score or 0.0,
            56.0,
        )

    reasons = generic_detection_reasons_for_candidate(candidate)
    if reasons:
        candidate.generic_detection_score = max(
            candidate.generic_detection_score or 0.0,
            min(100.0, 35.0 + 18.0 * len(reasons)),
        )
    candidate.generic_detection_reasons_json = json.dumps(reasons, ensure_ascii=True)

    final_blocked_roles = {
        "admat",
        "flyer",
        "logo",
        "poster",
        "social_screenshot",
        "stock_placeholder",
    }
    if (
        candidate.source_evidence_only
        or candidate.source_evidence_only is True
        or candidate.rescue_source == "social_graphic_reference"
        or candidate.image_role in final_blocked_roles
        or not candidate.is_direct_image_asset
        or candidate.is_social_media_url
        or candidate.appears_stock_or_placeholder
        or candidate.appears_poster_or_flyer
        or candidate.has_text_detected
        or candidate.has_watermark_detected
        or candidate.has_logo_detected
        or candidate.generic_detection_score >= 70.0
        or candidate.poster_flyer_score >= 70.0
        or candidate.text_graphic_score >= 90.0
        or candidate.admat_score >= 70.0
    ):
        candidate.can_be_final_image = False
    elif candidate.can_be_final_image is None:
        candidate.can_be_final_image = True


def blocking_reasons(candidate: ImageCandidate, *, manual_override: bool) -> list[str]:
    reasons: list[str] = []
    if candidate.candidate_status == "rejected":
        reasons.append("candidate rejected")
    if candidate.clearance_status == "rejected":
        reasons.append("clearance rejected")
    if candidate.is_accessible is False:
        reasons.append("image inaccessible")
    if not candidate.is_direct_image_asset:
        reasons.append("not direct image asset")
    if candidate.is_social_media_url:
        reasons.append("social media URL")
    if manual_override:
        return reasons
    if candidate.source_evidence_only:
        reasons.append("source evidence only")
    if not candidate.can_be_final_image:
        reasons.append("not eligible as final image")
    if candidate.generic_detection_score >= 70.0:
        reasons.append("generic provider image")
    if candidate.text_graphic_score >= 90.0:
        reasons.append("text graphic")
    if candidate.poster_flyer_score >= 70.0:
        reasons.append("poster or flyer score")
    if candidate.admat_score >= 70.0:
        reasons.append("admat score")
    if candidate.image_role in {"logo", "social_screenshot"}:
        reasons.append("logo or social screenshot")
    if candidate.appears_poster_or_flyer:
        reasons.append("poster or flyer")
    if candidate.has_text_detected:
        reasons.append("text-heavy image")
    if candidate.has_watermark_detected:
        reasons.append("watermark suspected")
    if candidate.has_logo_detected:
        reasons.append("logo detected")
    if candidate.appears_stock_or_placeholder:
        reasons.append("stock placeholder")
    if candidate.appears_food_or_drink:
        reasons.append("unrelated food or drink image")
    if candidate.appears_unrelated_place:
        reasons.append("unrelated place image")
    if (
        candidate.appears_generic_crowd
        and not candidate.appears_artist_subject
        and not candidate.appears_live_performance
        and not candidate.appears_venue_in_action
    ):
        reasons.append("generic crowd without music signal")
    if candidate.width is not None and candidate.height is not None:
        if candidate.width < 720 or min(candidate.width, candidate.height) < 400:
            reasons.append("severe low resolution")
    return reasons


def analyze_image_candidate(_image_candidate: ImageCandidate) -> ImageAnalysisResult:
    """Placeholder for future OCR/computer-vision analysis."""

    return ImageAnalysisResult()


def extract_text_from_image_candidate(
    _candidate: ImageCandidate,
) -> dict[str, str | float | None]:
    """Return a stable OCR placeholder without making any external calls."""

    return {
        "ocr_status": "not_configured",
        "text_detected": "unknown",
        "extracted_text": None,
        "confidence": None,
    }


def apply_analysis_result(
    candidate: ImageCandidate,
    analysis: ImageAnalysisResult,
) -> None:
    candidate.has_text_detected = analysis.text_detected
    candidate.has_watermark_detected = analysis.watermark_detected
    candidate.has_logo_detected = analysis.logo_detected
    candidate.appears_poster_or_flyer = bool(
        analysis.poster_or_flyer_probability
        and analysis.poster_or_flyer_probability >= 0.7
    )
    candidate.appears_live_performance = bool(
        analysis.live_performance_probability
        and analysis.live_performance_probability >= 0.7
    )
    candidate.appears_artist_subject = bool(
        analysis.artist_subject_probability
        and analysis.artist_subject_probability >= 0.7
    )
    candidate.appears_venue_in_action = bool(
        analysis.venue_in_action_probability
        and analysis.venue_in_action_probability >= 0.7
    )
    candidate.appears_stock_or_placeholder = bool(
        analysis.stock_placeholder_probability
        and analysis.stock_placeholder_probability >= 0.7
    )
    candidate.appears_food_or_drink = bool(
        analysis.food_or_drink_probability and analysis.food_or_drink_probability >= 0.7
    )
    candidate.appears_generic_crowd = bool(
        analysis.generic_crowd_probability
        and analysis.generic_crowd_probability >= 0.7
    )
    candidate.appears_unrelated_place = bool(
        analysis.unrelated_place_probability
        and analysis.unrelated_place_probability >= 0.7
    )
    candidate.text_area_ratio = analysis.text_area_ratio
    candidate.ocr_text_json = json.dumps({"notes": analysis.notes}, ensure_ascii=True)


def seed_candidate_fields(candidate: ImageCandidate) -> None:
    candidate.normalized_image_url = normalize_image_url(candidate.image_url)
    candidate.is_social_media_url = is_social_url(candidate.image_url)
    candidate.is_direct_image_asset = is_likely_direct_image_asset(
        candidate.image_url,
        candidate.content_type,
    )
    candidate.orientation = orientation_for(candidate.width, candidate.height)
    candidate.aspect_ratio = (
        round(candidate.width / candidate.height, 4)
        if candidate.width and candidate.height
        else None
    )
    candidate.pixel_count = None
    if candidate.width and candidate.height:
        candidate.pixel_count = candidate.width * candidate.height
    candidate.average_hash = hashlib.sha256(
        (candidate.normalized_image_url or candidate.image_url).encode("utf-8")
    ).hexdigest()[:16]
    candidate.perceptual_hash = candidate.average_hash
    token_flags = stock_or_poster_flags(candidate)
    if "stock_placeholder_candidate" in token_flags:
        candidate.appears_stock_or_placeholder = True
    if "poster_or_flyer_candidate" in token_flags:
        candidate.appears_poster_or_flyer = True
    if candidate.image_role in {"poster", "flyer", "admat"}:
        candidate.appears_poster_or_flyer = True
    if candidate.image_role in {"logo", "stock_placeholder"}:
        candidate.appears_stock_or_placeholder = True
    if candidate.clearance_status == "unknown":
        candidate.clearance_status = "needs_approval"
    update_rescue_scores(candidate)


def update_reuse_flags(session: Session, candidate: ImageCandidate) -> None:
    normalized = candidate.normalized_image_url or normalize_image_url(
        candidate.image_url
    )
    matches = list(
        session.scalars(
            select(ImageCandidate)
            .options(selectinload(ImageCandidate.event))
            .where(ImageCandidate.normalized_image_url == normalized)
        ).all()
    )
    candidate.reused_across_event_count = len(
        {match.event_id for match in matches if match.event_id is not None}
    )
    event_headliners = {
        (match.event.headliner or match.event.title).strip().lower()
        for match in matches
        if match.event is not None
    }
    event_venue_ids = {
        match.event.event_venue_id
        for match in matches
        if match.event is not None and match.event.event_venue_id is not None
    }
    venue_ids = {
        match.venue_id for match in matches if match.venue_id is not None
    } | event_venue_ids
    venue_reuse_allowed = (
        candidate.image_role in {"venue_live", "venue_exterior"} and len(venue_ids) == 1
    )
    if len(event_headliners) > 1 and not venue_reuse_allowed:
        candidate.appears_stock_or_placeholder = True
        reasons = set(_json_string_list(candidate.generic_detection_reasons_json))
        reasons.add("reused across different headliners")
        candidate.generic_detection_reasons_json = json.dumps(
            sorted(reasons),
            ensure_ascii=True,
        )
    if candidate.reused_across_event_count >= 3 and not venue_reuse_allowed:
        candidate.appears_stock_or_placeholder = True
        reasons = set(_json_string_list(candidate.generic_detection_reasons_json))
        reasons.add("reused across three or more events")
        candidate.generic_detection_reasons_json = json.dumps(
            sorted(reasons),
            ensure_ascii=True,
        )
    if candidate.appears_stock_or_placeholder:
        candidate.duplicate_hash_group_id = candidate.average_hash
        candidate.generic_detection_score = max(
            candidate.generic_detection_score or 0.0,
            82.0,
        )
        candidate.can_be_final_image = False


def score_image_candidate(
    session: Session,
    candidate: ImageCandidate,
) -> ImageCandidate:
    seed_candidate_fields(candidate)
    session.flush()
    update_reuse_flags(session, candidate)
    update_rescue_scores(candidate)
    tech_score, tech_flags = technical_score(candidate)
    subj_score, subj_flags = subject_score(candidate)
    role = role_score(candidate.image_role)
    prov_score = provenance_score(candidate.source_type, candidate.clearance_status)
    appr_score = approval_score(candidate.candidate_status, candidate.clearance_status)
    qa_flags = tech_flags + subj_flags + stock_or_poster_flags(candidate)

    if candidate.has_text_detected:
        qa_flags.append("text-heavy image candidate")
    if candidate.has_watermark_detected:
        qa_flags.append("watermark suspected")
    if candidate.has_logo_detected:
        qa_flags.append("logo detected")
    if candidate.appears_poster_or_flyer:
        qa_flags.append("poster/flyer detected")
    if candidate.appears_stock_or_placeholder:
        qa_flags.append("stock_placeholder_candidate")
    if candidate.source_evidence_only:
        qa_flags.append("source_evidence_only")
    if not candidate.can_be_final_image:
        qa_flags.append("not_final_image_eligible")
    if candidate.generic_detection_score >= 70:
        qa_flags.append("generic_provider_image")
    if candidate.poster_flyer_score >= 70 or candidate.admat_score >= 70:
        qa_flags.append("poster_flyer_admat")
    if candidate.rescue_source == "provider_artist_image":
        qa_flags.append("artist_image_candidate")
    if candidate.rescue_source == "provider_venue_image":
        qa_flags.append("venue_fallback_candidate")
    if candidate.clearance_status == "needs_approval":
        qa_flags.append("needs image approval")
        qa_flags.append("used_pending_approval")

    final_score = (
        role * 0.28
        + tech_score * 0.24
        + subj_score * 0.2
        + prov_score * 0.16
        + appr_score * 0.12
    )
    if candidate.has_text_detected:
        final_score -= 14
    if candidate.has_watermark_detected:
        final_score -= 22
    if candidate.appears_poster_or_flyer:
        final_score -= 45
    if candidate.appears_stock_or_placeholder:
        final_score -= 50
    if candidate.generic_detection_score >= 70:
        final_score -= 45
    if not candidate.can_be_final_image:
        final_score -= 55
    if candidate.rescue_priority <= 40:
        final_score += 6
    elif candidate.rescue_priority >= 160:
        final_score -= 18
    if candidate.clearance_status == "rejected":
        final_score = 0

    candidate.technical_quality_score = round(tech_score, 2)
    candidate.subject_relevance_score = round(subj_score, 2)
    candidate.visual_quality_score = round((role + subj_score) / 2, 2)
    candidate.provenance_score = round(prov_score, 2)
    candidate.approval_score = round(appr_score, 2)
    candidate.quality_score = round(max(min(final_score, 100.0), 0.0), 2)
    candidate.qa_flags_json = json.dumps(sorted(set(qa_flags)), ensure_ascii=True)
    candidate.rejection_reasons_json = json.dumps(
        sorted(set(blocking_reasons(candidate, manual_override=False))),
        ensure_ascii=True,
    )
    return candidate


def create_image_candidate(
    session: Session,
    payload: ImageCandidateInput,
    *,
    commit: bool = True,
) -> ImageCandidate:
    role = payload.image_role if payload.image_role in IMAGE_ROLES else "unknown"
    candidate = ImageCandidate(
        event_id=payload.event_id,
        venue_id=payload.venue_id,
        source_type=payload.source_type,
        source_provider=payload.source_provider,
        source_url=payload.source_url,
        source_chain_json=payload.source_chain_json,
        image_url=payload.image_url.strip(),
        candidate_status=payload.candidate_status,
        clearance_status=payload.clearance_status,
        image_role=role,
        rescue_source=(
            payload.rescue_source
            if payload.rescue_source in RESCUE_SOURCES
            else "unknown"
        ),
        rescue_priority=payload.rescue_priority,
        generic_detection_score=payload.generic_detection_score,
        generic_detection_reasons_json=payload.generic_detection_reasons_json,
        text_graphic_score=payload.text_graphic_score,
        poster_flyer_score=payload.poster_flyer_score,
        admat_score=payload.admat_score,
        artist_match_score=payload.artist_match_score,
        venue_context_score=payload.venue_context_score,
        music_signal_score=payload.music_signal_score,
        selected_reason=payload.selected_reason,
        selection_explanation_json=payload.selection_explanation_json,
        source_payload_path=payload.source_payload_path,
        source_evidence_only=payload.source_evidence_only,
        can_be_final_image=payload.can_be_final_image,
        width=payload.width,
        height=payload.height,
        content_type=payload.content_type,
        file_size_bytes=payload.file_size_bytes,
        is_direct_image_asset=False,
        is_social_media_url=False,
    )
    session.add(candidate)
    session.flush()
    score_image_candidate(session, candidate)
    session.add(candidate)
    if commit:
        session.commit()
        session.refresh(candidate)
    return candidate


def list_image_candidates(
    session: Session,
    filters: ImageCandidateFilters | None = None,
) -> list[ImageCandidate]:
    filters = filters or ImageCandidateFilters()
    statement = (
        select(ImageCandidate)
        .options(
            selectinload(ImageCandidate.event),
            selectinload(ImageCandidate.venue),
        )
        .order_by(ImageCandidate.updated_at.desc(), ImageCandidate.id.desc())
    )
    if filters.event_id is not None:
        statement = statement.where(ImageCandidate.event_id == filters.event_id)
    if filters.venue_id is not None:
        statement = statement.where(ImageCandidate.venue_id == filters.venue_id)
    if filters.source_type:
        statement = statement.where(ImageCandidate.source_type == filters.source_type)
    if filters.source_provider:
        statement = statement.where(
            ImageCandidate.source_provider == filters.source_provider
        )
    if filters.candidate_status:
        statement = statement.where(
            ImageCandidate.candidate_status == filters.candidate_status
        )
    if filters.clearance_status:
        statement = statement.where(
            ImageCandidate.clearance_status == filters.clearance_status
        )
    if filters.image_role:
        statement = statement.where(ImageCandidate.image_role == filters.image_role)
    if filters.rescue_source:
        statement = statement.where(
            ImageCandidate.rescue_source == filters.rescue_source
        )
    candidates = list(session.scalars(statement).all())
    if filters.quality_flag:
        candidates = [
            candidate
            for candidate in candidates
            if filters.quality_flag in candidate.qa_flags
        ]
    if filters.stock_placeholder_candidate:
        candidates = [
            candidate
            for candidate in candidates
            if candidate.appears_stock_or_placeholder
        ]
    if filters.text_detected:
        candidates = [
            candidate for candidate in candidates if candidate.has_text_detected
        ]
    if filters.watermark_detected:
        candidates = [
            candidate for candidate in candidates if candidate.has_watermark_detected
        ]
    if filters.poster_or_flyer:
        candidates = [
            candidate for candidate in candidates if candidate.appears_poster_or_flyer
        ]
    if filters.missing_dimensions:
        candidates = [
            candidate
            for candidate in candidates
            if candidate.width is None or candidate.height is None
        ]
    if filters.low_resolution:
        candidates = [
            candidate
            for candidate in candidates
            if "low resolution image" in candidate.qa_flags
        ]
    if filters.needs_approval:
        candidates = [
            candidate
            for candidate in candidates
            if candidate.clearance_status == "needs_approval"
        ]
    if filters.selected is not None:
        selected_ids = {
            event.selected_image_candidate_id
            for event in session.scalars(select(Event)).all()
            if event.selected_image_candidate_id is not None
        } | {
            venue.selected_image_candidate_id
            for venue in session.scalars(select(EventVenue)).all()
            if venue.selected_image_candidate_id is not None
        }
        candidates = [
            candidate
            for candidate in candidates
            if (candidate.id in selected_ids) is filters.selected
        ]
    if filters.selected_pending_approval:
        candidates = [
            candidate
            for candidate in candidates
            if is_candidate_selected_with_status(
                session,
                candidate,
                {SELECTED_PENDING_STATUS, "venue_fallback"},
                needs_approval=True,
            )
        ]
    if filters.selected_and_cleared:
        candidates = [
            candidate
            for candidate in candidates
            if is_candidate_selected_with_status(
                session,
                candidate,
                {"accepted", "venue_fallback"},
                cleared=True,
            )
        ]
    if filters.selected_but_needs_approval:
        candidates = [
            candidate
            for candidate in candidates
            if is_candidate_selected_with_status(
                session,
                candidate,
                {SELECTED_PENDING_STATUS, "venue_fallback"},
                needs_approval=True,
            )
        ]
    if filters.hard_blocked:
        candidates = [
            candidate
            for candidate in candidates
            if blocking_reasons(candidate, manual_override=False)
        ]
    if filters.missing_image:
        candidates = [
            candidate
            for candidate in candidates
            if linked_record_missing_image(candidate)
        ]
    if filters.source_evidence_only:
        candidates = [
            candidate for candidate in candidates if candidate.source_evidence_only
        ]
    if filters.can_be_final_image is not None:
        candidates = [
            candidate
            for candidate in candidates
            if candidate.can_be_final_image is filters.can_be_final_image
        ]
    if filters.selected_by_rescue:
        candidates = [
            candidate
            for candidate in candidates
            if candidate.selected_reason
            and "photo_rescue" in candidate.selected_reason
        ]
    if filters.missing_artist_image:
        candidates = [
            candidate
            for candidate in candidates
            if candidate.event is not None
            and not any(
                linked.image_role in {"artist_live", "artist_press"}
                or linked.rescue_source == "provider_artist_image"
                for linked in candidate.event.image_candidates
            )
        ]
    return candidates


def get_image_candidate(session: Session, candidate_id: int) -> ImageCandidate | None:
    return session.get(ImageCandidate, candidate_id)


def candidate_sort_key(candidate: ImageCandidate) -> tuple[int, int, float, int]:
    accepted_bonus = 1 if candidate.candidate_status == "accepted" else 0
    return (
        accepted_bonus,
        -(candidate.rescue_priority or 100),
        candidate.quality_score or 0,
        -(candidate.candidate_rank or candidate.id),
    )


def linked_record_missing_image(candidate: ImageCandidate) -> bool:
    if candidate.event is not None:
        return not candidate.event.selected_main_image_url
    if candidate.venue is not None:
        return not candidate.venue.selected_main_image_url
    return False


def is_candidate_selected_with_status(
    session: Session,
    candidate: ImageCandidate,
    statuses: set[str],
    *,
    cleared: bool = False,
    needs_approval: bool = False,
) -> bool:
    event = session.get(Event, candidate.event_id) if candidate.event_id else None
    venue = session.get(EventVenue, candidate.venue_id) if candidate.venue_id else None
    selected_records = [record for record in [event, venue] if record is not None]
    for record in selected_records:
        if record.selected_image_candidate_id != candidate.id:
            continue
        if record.image_status not in statuses:
            continue
        if cleared and record.image_clearance_status not in CLEARED_CLEARANCE_STATUSES:
            continue
        if needs_approval and record.image_clearance_status != "needs_approval":
            continue
        return True
    return False


def is_auto_selectable(candidate: ImageCandidate) -> bool:
    return not blocking_reasons(candidate, manual_override=False)


def is_human_selectable(candidate: ImageCandidate) -> bool:
    return not blocking_reasons(candidate, manual_override=True)


def apply_event_selection(
    event: Event,
    candidate: ImageCandidate | None,
    status: str,
    *,
    reason: str,
) -> None:
    event.selected_image_candidate_id = candidate.id if candidate else None
    event.selected_main_image_url = candidate.image_url if candidate else None
    event.image_status = status
    event.image_quality_score = candidate.quality_score if candidate else None
    if candidate:
        flags = set(candidate.qa_flags)
        flags.add(reason)
        if candidate.clearance_status == "needs_approval":
            flags.add("used_pending_approval")
        if status == "venue_fallback":
            flags.add("venue_fallback")
        if status == SELECTED_PENDING_STATUS:
            flags.add(SELECTED_PENDING_STATUS)
        event.image_quality_flags_json = json.dumps(
            sorted(flags),
            ensure_ascii=True,
        )
    else:
        event.image_quality_flags_json = json.dumps([reason])
    event.image_clearance_status = (
        "needs_approval"
        if candidate and candidate.clearance_status in PENDING_CLEARANCE_STATUSES
        else candidate.clearance_status
        if candidate
        else None
    )
    event.image_source_type = candidate.source_type if candidate else None
    event.image_source_provider = candidate.source_provider if candidate else None
    event.image_role = candidate.image_role if candidate else None
    event.image_selection_reason = reason
    event.image_selected_at = utc_now() if candidate else None
    if candidate:
        candidate.selected_reason = reason


def apply_venue_selection(
    venue: EventVenue,
    candidate: ImageCandidate | None,
    status: str,
    *,
    reason: str,
) -> None:
    venue.selected_image_candidate_id = candidate.id if candidate else None
    venue.selected_main_image_url = candidate.image_url if candidate else None
    venue.image_status = status
    venue.image_quality_score = candidate.quality_score if candidate else None
    if candidate:
        flags = set(candidate.qa_flags)
        flags.add(reason)
        if candidate.clearance_status == "needs_approval":
            flags.add("used_pending_approval")
        if status == SELECTED_PENDING_STATUS:
            flags.add(SELECTED_PENDING_STATUS)
        venue.image_quality_flags_json = json.dumps(
            sorted(flags),
            ensure_ascii=True,
        )
    else:
        venue.image_quality_flags_json = json.dumps([reason])
    venue.image_clearance_status = (
        "needs_approval"
        if candidate and candidate.clearance_status in PENDING_CLEARANCE_STATUSES
        else candidate.clearance_status
        if candidate
        else None
    )
    venue.image_role = candidate.image_role if candidate else None
    venue.image_selection_reason = reason
    venue.image_selected_at = utc_now() if candidate else None
    if candidate:
        candidate.selected_reason = reason


def selected_candidate_is_accepted(event: Event, session: Session) -> bool:
    if event.selected_image_candidate_id is None:
        return False
    candidate = session.get(ImageCandidate, event.selected_image_candidate_id)
    return bool(candidate and candidate.candidate_status == "accepted")


def selected_status_for_candidate(
    candidate: ImageCandidate,
    *,
    venue_fallback: bool = False,
) -> str:
    if venue_fallback:
        return "venue_fallback"
    if candidate.clearance_status in CLEARED_CLEARANCE_STATUSES:
        return "accepted"
    return SELECTED_PENDING_STATUS


def selected_reason_for_candidate(
    candidate: ImageCandidate,
    *,
    venue_fallback: bool = False,
) -> str:
    if venue_fallback and candidate.clearance_status in PENDING_CLEARANCE_STATUSES:
        return "venue_fallback_used_pending_approval"
    if venue_fallback:
        return "venue_fallback_best_available"
    if candidate.clearance_status in CLEARED_CLEARANCE_STATUSES:
        return "best_available_cleared"
    return "best_available_used_pending_approval"


def sync_selected_candidate_state(
    session: Session,
    candidate: ImageCandidate,
) -> None:
    if candidate.event_id is not None:
        event = session.get(Event, candidate.event_id)
        if event and event.selected_image_candidate_id == candidate.id:
            if (
                candidate.candidate_status == "rejected"
                or candidate.clearance_status == "rejected"
            ):
                apply_event_selection(
                    event,
                    None,
                    "rejected",
                    reason="selected_candidate_rejected",
                )
            else:
                apply_event_selection(
                    event,
                    candidate,
                    selected_status_for_candidate(candidate),
                    reason=selected_reason_for_candidate(candidate),
                )
            session.add(event)
    if candidate.venue_id is not None:
        venue = session.get(EventVenue, candidate.venue_id)
        if venue and venue.selected_image_candidate_id == candidate.id:
            if (
                candidate.candidate_status == "rejected"
                or candidate.clearance_status == "rejected"
            ):
                apply_venue_selection(
                    venue,
                    None,
                    "rejected",
                    reason="selected_candidate_rejected",
                )
            else:
                apply_venue_selection(
                    venue,
                    candidate,
                    selected_status_for_candidate(candidate),
                    reason=selected_reason_for_candidate(candidate),
                )
            session.add(venue)


def select_candidate_for_event(
    session: Session,
    candidate_id: int,
    *,
    commit: bool = True,
) -> Event | None:
    candidate = session.get(ImageCandidate, candidate_id)
    if candidate is None or candidate.event_id is None:
        return None
    score_image_candidate(session, candidate)
    if not is_human_selectable(candidate):
        return None
    event = session.get(Event, candidate.event_id)
    if event is None:
        return None
    apply_event_selection(
        event,
        candidate,
        selected_status_for_candidate(candidate),
        reason="manual_replace_selected_image",
    )
    session.add(event)
    if commit:
        session.commit()
    return event


def select_candidate_for_venue(
    session: Session,
    candidate_id: int,
    *,
    commit: bool = True,
) -> EventVenue | None:
    candidate = session.get(ImageCandidate, candidate_id)
    if candidate is None or candidate.venue_id is None:
        return None
    score_image_candidate(session, candidate)
    if not is_human_selectable(candidate):
        return None
    venue = session.get(EventVenue, candidate.venue_id)
    if venue is None:
        return None
    apply_venue_selection(
        venue,
        candidate,
        selected_status_for_candidate(candidate),
        reason="manual_replace_selected_image",
    )
    session.add(venue)
    if commit:
        session.commit()
    return venue


def select_best_event_image(
    session: Session,
    event_id: int,
    *,
    auto_select: bool = True,
    commit: bool = True,
) -> Event | None:
    event = session.get(Event, event_id)
    if event is None:
        return None
    if selected_candidate_is_accepted(event, session):
        return event
    candidates = list(event.image_candidates)
    for candidate in candidates:
        score_image_candidate(session, candidate)

    accepted = [
        candidate
        for candidate in candidates
        if candidate.candidate_status == "accepted" and is_human_selectable(candidate)
    ]
    if accepted:
        winner = sorted(accepted, key=candidate_sort_key, reverse=True)[0]
        apply_event_selection(
            event,
            winner,
            selected_status_for_candidate(winner),
            reason=selected_reason_for_candidate(winner),
        )
        session.add(event)
        if commit:
            session.commit()
        return event

    if auto_select:
        clean = [candidate for candidate in candidates if is_auto_selectable(candidate)]
        if clean:
            winner = sorted(clean, key=candidate_sort_key, reverse=True)[0]
            apply_event_selection(
                event,
                winner,
                selected_status_for_candidate(winner),
                reason=selected_reason_for_candidate(winner),
            )
            session.add(event)
            if commit:
                session.commit()
            return event

    venue_fallback = venue_fallback_candidate(event, session)
    if venue_fallback:
        apply_event_selection(
            event,
            venue_fallback,
            selected_status_for_candidate(venue_fallback, venue_fallback=True),
            reason=selected_reason_for_candidate(
                venue_fallback,
                venue_fallback=True,
            ),
        )
        session.add(event)
        if commit:
            session.commit()
        return event

    status = "missing" if not candidates else "needs_review"
    reason = "missing_image" if status == "missing" else "no_eligible_image"
    apply_event_selection(event, None, status, reason=reason)
    session.add(event)
    if commit:
        session.commit()
    return event


def venue_fallback_candidate(event: Event, session: Session) -> ImageCandidate | None:
    if event.venue is None:
        return None
    candidates = [
        candidate
        for candidate in event.venue.image_candidates
        if candidate.image_role in {"venue_live", "venue_exterior"}
        and is_auto_selectable(candidate)
    ]
    if not candidates:
        return None
    return sorted(candidates, key=candidate_sort_key, reverse=True)[0]


def select_best_venue_image(
    session: Session,
    venue_id: int,
    *,
    commit: bool = True,
) -> EventVenue | None:
    venue = session.get(EventVenue, venue_id)
    if venue is None:
        return None
    candidates = list(venue.image_candidates)
    for candidate in candidates:
        score_image_candidate(session, candidate)
    accepted = [
        candidate
        for candidate in candidates
        if candidate.candidate_status == "accepted" and is_human_selectable(candidate)
    ]
    if accepted:
        winner = sorted(accepted, key=candidate_sort_key, reverse=True)[0]
        apply_venue_selection(
            venue,
            winner,
            selected_status_for_candidate(winner),
            reason=selected_reason_for_candidate(winner),
        )
    else:
        eligible = [
            candidate for candidate in candidates if is_auto_selectable(candidate)
        ]
        if eligible:
            winner = sorted(eligible, key=candidate_sort_key, reverse=True)[0]
            apply_venue_selection(
                venue,
                winner,
                selected_status_for_candidate(winner),
                reason=selected_reason_for_candidate(winner),
            )
        elif candidates:
            apply_venue_selection(
                venue,
                None,
                "needs_review",
                reason="no_eligible_image",
            )
        else:
            apply_venue_selection(venue, None, "missing", reason="missing_image")
    session.add(venue)
    if commit:
        session.commit()
    return venue


def update_candidate_review(
    session: Session,
    candidate_id: int,
    *,
    reviewed_by: str | None,
    candidate_status: str | None = None,
    clearance_status: str | None = None,
    image_role: str | None = None,
    clearance_notes: str | None = None,
    qa_updates: dict[str, bool] | None = None,
) -> ImageCandidate | None:
    candidate = session.get(ImageCandidate, candidate_id)
    if candidate is None:
        return None
    if candidate_status:
        candidate.candidate_status = candidate_status
    if clearance_status:
        candidate.clearance_status = clearance_status
    if image_role and image_role in IMAGE_ROLES:
        candidate.image_role = image_role
    if clearance_notes is not None:
        candidate.clearance_notes = clearance_notes
    for key, value in (qa_updates or {}).items():
        if hasattr(candidate, key):
            setattr(candidate, key, value)
    candidate.reviewed_by = reviewed_by
    candidate.reviewed_at = utc_now()
    score_image_candidate(session, candidate)
    sync_selected_candidate_state(session, candidate)
    session.add(candidate)
    session.commit()
    session.refresh(candidate)
    return candidate


def set_candidate_clearance(
    session: Session,
    candidate_id: int,
    clearance_status: str,
    reviewed_by: str | None,
) -> ImageCandidate | None:
    return update_candidate_review(
        session,
        candidate_id,
        reviewed_by=reviewed_by,
        clearance_status=clearance_status,
    )


def mark_candidate_preflight_result(
    session: Session,
    candidate_id: int,
    *,
    is_accessible: bool | None,
    content_type: str | None = None,
    width: int | None = None,
    height: int | None = None,
    file_size_bytes: int | None = None,
) -> ImageCandidate | None:
    candidate = session.get(ImageCandidate, candidate_id)
    if candidate is None:
        return None
    candidate.is_accessible = is_accessible
    if content_type is not None:
        candidate.content_type = content_type
    if width is not None:
        candidate.width = width
    if height is not None:
        candidate.height = height
    if file_size_bytes is not None:
        candidate.file_size_bytes = file_size_bytes
    score_image_candidate(session, candidate)
    session.add(candidate)
    session.commit()
    session.refresh(candidate)
    return candidate


def event_image_badges(event: Event) -> list[str]:
    candidate_flags = {
        flag
        for candidate in event.image_candidates
        for flag in candidate.qa_flags
    }
    flags = set(event.image_quality_flags) | candidate_flags
    candidate_source_types = {
        candidate.source_type for candidate in event.image_candidates
    }
    selected_candidate = next(
        (
            candidate
            for candidate in event.image_candidates
            if candidate.id == event.selected_image_candidate_id
        ),
        None,
    )
    badges: list[str] = []
    if event.image_status in {None, "missing"}:
        badges.append("Missing image")
    if event.image_status == "needs_review":
        badges.append("Needs image review")
    if event.selected_main_image_url:
        badges.append("Selected image")
    if event.image_status == SELECTED_PENDING_STATUS:
        badges.append("Selected · Needs Approval")
    if (
        event.image_status == SELECTED_PENDING_STATUS
        or event.image_clearance_status == "needs_approval"
    ):
        badges.append("Needs approval")
    if event.image_status == "venue_fallback":
        badges.append("Venue fallback image")
    if selected_candidate and selected_candidate.selected_reason:
        if "photo_rescue" in selected_candidate.selected_reason:
            badges.append("Selected by rescue")
        if selected_candidate.rescue_source == "provider_artist_image":
            badges.append("Artist source")
        if selected_candidate.rescue_source == "provider_venue_image":
            badges.append("Venue fallback source")
    if "stock_placeholder_candidate" in flags or any(
        candidate.appears_stock_or_placeholder for candidate in event.image_candidates
    ):
        badges.append("Provider stock candidate")
    if "generic_provider_image" in flags:
        badges.append("Generic provider image blocked")
    if "poster_flyer_admat" in flags:
        badges.append("Poster/flyer/admat blocked")
    if "source_evidence_only" in flags:
        badges.append("Source evidence only")
    if "poster/flyer detected" in flags:
        badges.append("Poster/flyer detected")
    if "text-heavy image candidate" in flags:
        badges.append("Text-heavy image")
    if "watermark suspected" in flags:
        badges.append("Watermark suspected")
    if event.image_role in {"artist_live", "artist_press"} and event.image_status in {
        "accepted",
        SELECTED_PENDING_STATUS,
    }:
        badges.append("Artist image")
        if event.image_status == "accepted":
            badges.append("Artist image accepted")
    if event.image_role == "event_provider" and event.selected_main_image_url:
        badges.append("Provider image")
    if event.image_role in {"venue_live", "venue_exterior"} and event.image_status in {
        "accepted",
        "venue_fallback",
        SELECTED_PENDING_STATUS,
    }:
        badges.append("Venue image")
        if event.image_status in {"accepted", "venue_fallback"}:
            badges.append("Venue image accepted")
    if event.image_source_type == "spotify" or "spotify" in candidate_source_types:
        badges.append("Spotify candidate")
    if event.image_source_type == "serpapi" or "serpapi" in candidate_source_types:
        badges.append("SerpAPI candidate")
    if (
        event.image_source_type in {"manual", "upload"}
        and event.image_status == "accepted"
    ):
        badges.append("Manual image accepted")
    elif any(
        candidate.source_type in {"manual", "upload"}
        and candidate.candidate_status == "accepted"
        for candidate in event.image_candidates
    ):
        badges.append("Manual image accepted")
    return badges


def venue_image_badges(venue: EventVenue) -> list[str]:
    candidate_flags = {
        flag
        for candidate in venue.image_candidates
        for flag in candidate.qa_flags
    }
    flags = set(venue.image_quality_flags) | candidate_flags
    badges: list[str] = []
    if venue.image_status in {None, "missing"}:
        badges.append("Missing image")
    if venue.image_status == "needs_review":
        badges.append("Needs image review")
    if venue.selected_main_image_url:
        badges.append("Selected image")
    if venue.image_status == SELECTED_PENDING_STATUS:
        badges.append("Selected · Needs Approval")
    if venue.image_clearance_status == "needs_approval":
        badges.append("Needs approval")
    if "stock_placeholder_candidate" in flags or any(
        candidate.appears_stock_or_placeholder for candidate in venue.image_candidates
    ):
        badges.append("Provider stock candidate")
    if "watermark suspected" in flags:
        badges.append("Watermark suspected")
    if venue.image_role in {"venue_live", "venue_exterior"} and venue.image_status in {
        "accepted",
        SELECTED_PENDING_STATUS,
    }:
        badges.append("Venue image")
        if venue.image_status == "accepted":
            badges.append("Venue image accepted")
    return badges


def quality_counts(session: Session) -> dict[str, int]:
    events = list(session.scalars(select(Event)).all())
    venues = list(session.scalars(select(EventVenue)).all())
    candidates = list(session.scalars(select(ImageCandidate)).all())
    return {
        "events_with_selected_image": sum(
            bool(event.selected_main_image_url) for event in events
        ),
        "events_with_selected_image_pending_approval": sum(
            bool(event.selected_main_image_url)
            and event.image_clearance_status == "needs_approval"
            for event in events
        ),
        "events_with_selected_cleared_image": sum(
            bool(event.selected_main_image_url)
            and event.image_clearance_status in CLEARED_CLEARANCE_STATUSES
            for event in events
        ),
        "events_missing_usable_image": sum(
            not event.selected_main_image_url for event in events
        ),
        "events_using_venue_fallback": sum(
            event.image_status == "venue_fallback" for event in events
        ),
        "events_using_provider_image_pending_approval": sum(
            bool(event.selected_main_image_url)
            and event.image_role == "event_provider"
            and event.image_clearance_status == "needs_approval"
            for event in events
        ),
        "events_with_hard_blocked_image_candidates": sum(
            any(
                candidate.event_id == event.id
                and blocking_reasons(candidate, manual_override=False)
                for candidate in candidates
            )
            for event in events
        ),
        "events_with_provider_stock_candidate": sum(
            any(
                candidate.event_id == event.id
                and candidate.appears_stock_or_placeholder
                for candidate in candidates
            )
            for event in events
        ),
        "events_needing_image_approval": sum(
            event.image_clearance_status == "needs_approval"
            or event.image_status == SELECTED_PENDING_STATUS
            for event in events
        ),
        "events_with_text_heavy_image_candidates": sum(
            any(
                candidate.event_id == event.id and candidate.has_text_detected
                for candidate in candidates
            )
            for event in events
        ),
        "events_with_watermark_candidates": sum(
            any(
                candidate.event_id == event.id and candidate.has_watermark_detected
                for candidate in candidates
            )
            for event in events
        ),
        "events_with_poster_flyer_candidates": sum(
            any(
                candidate.event_id == event.id and candidate.appears_poster_or_flyer
                for candidate in candidates
            )
            for event in events
        ),
        "events_with_accepted_artist_images": sum(
            event.image_status in {"accepted", SELECTED_PENDING_STATUS}
            and event.image_role in {"artist_live", "artist_press"}
            for event in events
        ),
        "events_with_accepted_venue_fallback_images": sum(
            event.image_status == "venue_fallback" for event in events
        ),
        "events_selected_by_photo_rescue": sum(
            any(
                candidate.event_id == event.id
                and candidate.id == event.selected_image_candidate_id
                and candidate.selected_reason
                and "photo_rescue" in candidate.selected_reason
                for candidate in candidates
            )
            for event in events
        ),
        "events_with_generic_provider_image_blocked": sum(
            any(
                candidate.event_id == event.id
                and (
                    candidate.generic_detection_score >= 70.0
                    or "generic_provider_image" in candidate.qa_flags
                )
                for candidate in candidates
            )
            for event in events
        ),
        "events_with_poster_flyer_admat_blocked": sum(
            any(
                candidate.event_id == event.id
                and (
                    candidate.poster_flyer_score >= 70.0
                    or candidate.admat_score >= 70.0
                    or "poster_flyer_admat" in candidate.qa_flags
                )
                for candidate in candidates
            )
            for event in events
        ),
        "events_with_social_graphic_evidence": sum(
            any(
                candidate.event_id == event.id
                and (
                    candidate.source_evidence_only
                    or candidate.rescue_source == "social_graphic_reference"
                )
                for candidate in candidates
            )
            for event in events
        ),
        "events_with_artist_image_candidates": sum(
            any(
                candidate.event_id == event.id
                and (
                    candidate.image_role in {"artist_live", "artist_press"}
                    or candidate.rescue_source == "provider_artist_image"
                )
                for candidate in candidates
            )
            for event in events
        ),
        "venues_needing_image_approval": sum(
            venue.image_clearance_status == "needs_approval" for venue in venues
        ),
    }
