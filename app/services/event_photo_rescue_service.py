from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import ApiFeedRecord, Event, ImageCandidate, utc_now
from app.services.image_qa_service import (
    ImageCandidateInput,
    apply_event_selection,
    blocking_reasons,
    candidate_sort_key,
    create_image_candidate,
    is_auto_selectable,
    is_human_selectable,
    is_likely_direct_image_asset,
    normalize_image_url,
    score_image_candidate,
    selected_reason_for_candidate,
    selected_status_for_candidate,
    venue_fallback_candidate,
)


@dataclass(frozen=True)
class PhotoRescueResult:
    event_id: int
    selected_candidate_id: int | None
    selected_url: str | None
    reason: str
    created_candidate_count: int
    blocked_candidate_count: int
    fallback_used: bool
    needs_approval: bool
    explanation: dict[str, object]


def safe_json_dict(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def direct_image_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    return cleaned if is_likely_direct_image_asset(cleaned) else None


def nested_direct_image_url(
    value: object,
    preferred_keys: tuple[str, ...],
) -> str | None:
    if isinstance(value, str):
        return direct_image_url(value)
    if not isinstance(value, dict):
        return None
    for key in preferred_keys:
        found = direct_image_url(value.get(key))
        if found:
            return found
    for nested in value.values():
        found = nested_direct_image_url(nested, preferred_keys)
        if found:
            return found
    return None


def image_input(
    *,
    event_id: int | None,
    provider_key: str,
    image_url: str,
    source_url: str | None,
    source_chain_json: str | None,
    source_payload_path: str,
    rescue_source: str,
    image_role: str,
    rescue_priority: int,
    source_evidence_only: bool = False,
    can_be_final_image: bool = True,
    artist_match_score: float = 0.0,
    venue_context_score: float = 0.0,
    music_signal_score: float = 0.0,
) -> ImageCandidateInput:
    return ImageCandidateInput(
        event_id=event_id,
        source_type="provider",
        source_provider=provider_key,
        source_url=source_url,
        source_chain_json=source_chain_json,
        image_url=image_url,
        image_role=image_role,
        clearance_status="needs_approval",
        rescue_source=rescue_source,
        rescue_priority=rescue_priority,
        source_payload_path=source_payload_path,
        source_evidence_only=source_evidence_only,
        can_be_final_image=can_be_final_image,
        artist_match_score=artist_match_score,
        venue_context_score=venue_context_score,
        music_signal_score=music_signal_score,
    )


def _jambase_payload(raw_payload: dict[str, Any]) -> dict[str, Any]:
    nested = raw_payload.get("event")
    return nested if isinstance(nested, dict) else raw_payload


def _cityspark_payload(raw_payload: dict[str, Any]) -> dict[str, Any]:
    nested = raw_payload.get("event")
    return nested if isinstance(nested, dict) else raw_payload


def provider_image_inputs_from_raw(
    provider_key: str,
    raw_payload: dict[str, Any],
    *,
    event_id: int | None,
    source_url: str | None,
    source_chain_json: str | None,
    headliner: str | None = None,
) -> list[ImageCandidateInput]:
    """Build QA candidates from stored provider JSON without external calls."""

    provider = provider_key.strip().lower()
    inputs: list[ImageCandidateInput] = []
    preferred_keys = (
        "largeImageUrl",
        "mediumImageUrl",
        "smallImageUrl",
        "large",
        "medium",
        "small",
        "url",
        "imageUrl",
    )

    if provider == "jambase":
        event = _jambase_payload(raw_payload)
        event_image = nested_direct_image_url(event.get("image"), preferred_keys)
        if event_image:
            inputs.append(
                image_input(
                    event_id=event_id,
                    provider_key=provider_key,
                    image_url=event_image,
                    source_url=source_url,
                    source_chain_json=source_chain_json,
                    source_payload_path="jambase.image",
                    rescue_source="provider_event_image",
                    image_role="event_provider",
                    rescue_priority=70,
                    music_signal_score=58.0,
                )
            )

        promo_image = nested_direct_image_url(event.get("x-promoImage"), preferred_keys)
        if promo_image:
            inputs.append(
                image_input(
                    event_id=event_id,
                    provider_key=provider_key,
                    image_url=promo_image,
                    source_url=source_url,
                    source_chain_json=source_chain_json,
                    source_payload_path="jambase.x-promoImage",
                    rescue_source="provider_promo_image",
                    image_role="admat",
                    rescue_priority=170,
                    source_evidence_only=True,
                    can_be_final_image=False,
                    music_signal_score=35.0,
                )
            )

        performers = event.get("performer") or event.get("performers") or []
        if isinstance(performers, dict):
            performers = [performers]
        headliner_key = (headliner or event.get("name") or "").strip().lower()
        if isinstance(performers, list):
            for index, performer in enumerate(performers):
                if not isinstance(performer, dict):
                    continue
                performer_image = nested_direct_image_url(
                    performer.get("image"),
                    preferred_keys,
                )
                if not performer_image:
                    continue
                performer_name = str(performer.get("name") or "").strip().lower()
                is_headliner = bool(
                    performer.get("x-isHeadliner")
                    or performer.get("headliner")
                    or (performer_name and performer_name in headliner_key)
                )
                inputs.append(
                    image_input(
                        event_id=event_id,
                        provider_key=provider_key,
                        image_url=performer_image,
                        source_url=source_url,
                        source_chain_json=source_chain_json,
                        source_payload_path=f"jambase.performer[{index}].image",
                        rescue_source="provider_artist_image",
                        image_role="artist_press",
                        rescue_priority=30 if is_headliner else 42,
                        artist_match_score=96.0 if is_headliner else 76.0,
                        music_signal_score=90.0,
                    )
                )

        location = event.get("location") or {}
        if isinstance(location, dict):
            venue_image = nested_direct_image_url(location.get("image"), preferred_keys)
            if venue_image:
                inputs.append(
                    image_input(
                        event_id=event_id,
                        provider_key=provider_key,
                        image_url=venue_image,
                        source_url=source_url,
                        source_chain_json=source_chain_json,
                        source_payload_path="jambase.location.image",
                        rescue_source="provider_venue_image",
                        image_role="venue_live",
                        rescue_priority=90,
                        venue_context_score=78.0,
                        music_signal_score=64.0,
                    )
                )

    elif provider == "cityspark":
        event = _cityspark_payload(raw_payload)
        primary = event.get("primaryImage") or {}
        if isinstance(primary, dict):
            for key, priority in (
                ("largeImageUrl", 60),
                ("mediumImageUrl", 68),
                ("smallImageUrl", 115),
            ):
                image_url = direct_image_url(primary.get(key))
                if not image_url:
                    continue
                inputs.append(
                    image_input(
                        event_id=event_id,
                        provider_key=provider_key,
                        image_url=image_url,
                        source_url=source_url,
                        source_chain_json=source_chain_json,
                        source_payload_path=f"cityspark.primaryImage.{key}",
                        rescue_source="provider_event_image",
                        image_role="event_provider",
                        rescue_priority=priority,
                        music_signal_score=55.0 if key != "smallImageUrl" else 35.0,
                    )
                )
        media = event.get("media") or []
        if isinstance(media, dict):
            media = [media]
        if isinstance(media, list):
            for index, item in enumerate(media):
                image_url = nested_direct_image_url(item, preferred_keys)
                if image_url:
                    inputs.append(
                        image_input(
                            event_id=event_id,
                            provider_key=provider_key,
                            image_url=image_url,
                            source_url=source_url,
                            source_chain_json=source_chain_json,
                            source_payload_path=f"cityspark.media[{index}]",
                            rescue_source="provider_event_image",
                            image_role="event_provider",
                            rescue_priority=75,
                            music_signal_score=50.0,
                        )
                    )
        links = event.get("links") or []
        if isinstance(links, dict):
            links = [links]
        if isinstance(links, list):
            for index, item in enumerate(links):
                if not isinstance(item, dict):
                    continue
                logo_url = direct_image_url(item.get("logoUrl"))
                if logo_url:
                    inputs.append(
                        image_input(
                            event_id=event_id,
                            provider_key=provider_key,
                            image_url=logo_url,
                            source_url=source_url,
                            source_chain_json=source_chain_json,
                            source_payload_path=f"cityspark.links[{index}].logoUrl",
                            rescue_source="social_graphic_reference",
                            image_role="logo",
                            rescue_priority=230,
                            source_evidence_only=True,
                            can_be_final_image=False,
                        )
                    )

    main_image_url = direct_image_url(raw_payload.get("main_image_url"))
    if main_image_url:
        inputs.append(
            image_input(
                event_id=event_id,
                provider_key=provider_key,
                image_url=main_image_url,
                source_url=source_url,
                source_chain_json=source_chain_json,
                source_payload_path="normalized.main_image_url",
                rescue_source="provider_event_image",
                image_role="event_provider",
                rescue_priority=65,
                music_signal_score=54.0,
            )
        )

    seen: set[tuple[str, str]] = set()
    unique_inputs: list[ImageCandidateInput] = []
    for item in inputs:
        dedupe_key = (
            normalize_image_url(item.image_url),
            item.source_payload_path or "",
        )
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        unique_inputs.append(item)
    return unique_inputs


def provider_image_inputs_for_record(
    record: ApiFeedRecord,
    *,
    event_id: int | None = None,
) -> list[ImageCandidateInput]:
    raw = safe_json_dict(record.raw_payload_json)
    if record.main_image_url and "main_image_url" not in raw:
        raw = {**raw, "main_image_url": record.main_image_url}
    return provider_image_inputs_from_raw(
        record.provider_key,
        raw,
        event_id=event_id,
        source_url=record.event_url or record.source_url,
        source_chain_json=record.source_chain_json,
        headliner=record.headliner,
    )


def create_provider_image_candidates_for_record(
    session: Session,
    record: ApiFeedRecord,
    event_id: int,
    *,
    commit: bool = True,
) -> list[ImageCandidate]:
    created: list[ImageCandidate] = []
    for payload in provider_image_inputs_for_record(record, event_id=event_id):
        normalized = normalize_image_url(payload.image_url)
        existing = session.scalars(
            select(ImageCandidate).where(
                ImageCandidate.event_id == event_id,
                ImageCandidate.normalized_image_url == normalized,
                ImageCandidate.source_payload_path == payload.source_payload_path,
            )
        ).first()
        if existing is not None:
            continue
        created.append(create_image_candidate(session, payload, commit=False))
    if commit:
        session.commit()
    return created


def _selected_explanation(
    event: Event,
    candidate: ImageCandidate | None,
    *,
    reason: str,
    blocked: list[dict[str, object]],
    fallback_used: bool,
    created_candidate_count: int,
) -> dict[str, object]:
    return {
        "event_id": event.id,
        "selected_candidate_id": candidate.id if candidate else None,
        "selected_image_url": candidate.image_url if candidate else None,
        "reason": reason,
        "source_payload_path": candidate.source_payload_path if candidate else None,
        "rescue_source": candidate.rescue_source if candidate else None,
        "rescue_priority": candidate.rescue_priority if candidate else None,
        "fallback_used": fallback_used,
        "needs_approval": (
            candidate.clearance_status == "needs_approval" if candidate else False
        ),
        "blocked_candidate_count": len(blocked),
        "blocked_candidates": blocked,
        "created_candidate_count": created_candidate_count,
    }


def run_event_photo_rescue(
    session: Session,
    event_id: int,
    *,
    commit: bool = True,
) -> PhotoRescueResult | None:
    event = session.scalars(
        select(Event)
        .options(
            selectinload(Event.image_candidates),
            selectinload(Event.venue),
        )
        .where(Event.id == event_id)
    ).first()
    if event is None:
        return None

    created_count = 0
    if event.api_feed_record_id is not None:
        record = session.get(ApiFeedRecord, event.api_feed_record_id)
        if record is not None:
            created_count = len(
                create_provider_image_candidates_for_record(
                    session,
                    record,
                    event.id,
                    commit=False,
                )
            )
            session.flush()
            session.refresh(event, attribute_names=["image_candidates"])

    candidates = list(event.image_candidates)
    for candidate in candidates:
        score_image_candidate(session, candidate)

    accepted = [
        candidate
        for candidate in candidates
        if candidate.candidate_status == "accepted" and is_human_selectable(candidate)
    ]
    auto_candidates = [
        candidate for candidate in candidates if is_auto_selectable(candidate)
    ]
    fallback_used = False
    reason = "photo_rescue_no_eligible_image"
    selected: ImageCandidate | None = None

    if accepted:
        selected = sorted(accepted, key=candidate_sort_key, reverse=True)[0]
        reason = "photo_rescue_manual_accept_preserved"
    elif auto_candidates:
        selected = sorted(auto_candidates, key=candidate_sort_key, reverse=True)[0]
        if selected.rescue_source == "provider_artist_image":
            reason = "photo_rescue_selected_artist_image"
        elif selected.rescue_source == "provider_venue_image":
            reason = "photo_rescue_selected_venue_candidate"
        elif selected.rescue_source == "ticketing_page_image":
            reason = "photo_rescue_selected_ticket_page_image"
        elif selected.rescue_source == "provider_event_image":
            reason = "photo_rescue_selected_provider_event_image"
        else:
            reason = "photo_rescue_selected_best_candidate"
    else:
        selected = venue_fallback_candidate(event, session)
        if selected is not None:
            fallback_used = True
            reason = "photo_rescue_selected_venue_fallback"

    blocked: list[dict[str, object]] = [
        {
            "candidate_id": candidate.id,
            "image_url": candidate.image_url,
            "source_payload_path": candidate.source_payload_path,
            "rescue_source": candidate.rescue_source,
            "reasons": blocking_reasons(candidate, manual_override=False),
        }
        for candidate in candidates
        if blocking_reasons(candidate, manual_override=False)
    ]

    if selected is None:
        status = "missing" if not candidates else "needs_review"
        apply_event_selection(event, None, status, reason=reason)
        explanation = _selected_explanation(
            event,
            None,
            reason=reason,
            blocked=blocked,
            fallback_used=fallback_used,
            created_candidate_count=created_count,
        )
    else:
        status_reason = selected_reason_for_candidate(
            selected,
            venue_fallback=fallback_used,
        )
        status = selected_status_for_candidate(selected, venue_fallback=fallback_used)
        if selected.clearance_status == "needs_approval":
            reason = f"{reason}_needs_approval"
        apply_event_selection(event, selected, status, reason=reason)
        explanation = _selected_explanation(
            event,
            selected,
            reason=reason,
            blocked=blocked,
            fallback_used=fallback_used,
            created_candidate_count=created_count,
        )
        flags = set(event.image_quality_flags)
        flags.add("photo_rescue_selected")
        if fallback_used:
            flags.add("venue_fallback")
        if any(item["reasons"] for item in blocked):
            flags.add("photo_rescue_blocked_candidates")
        event.image_quality_flags_json = json.dumps(sorted(flags), ensure_ascii=True)
        selected.selected_reason = reason
        selected.selection_explanation_json = json.dumps(
            {**explanation, "status_reason": status_reason},
            ensure_ascii=True,
            sort_keys=True,
        )
        session.add(selected)

    session.add(event)
    if commit:
        session.commit()
    return PhotoRescueResult(
        event_id=event.id,
        selected_candidate_id=selected.id if selected else None,
        selected_url=selected.image_url if selected else None,
        reason=reason,
        created_candidate_count=created_count,
        blocked_candidate_count=len(blocked),
        fallback_used=fallback_used,
        needs_approval=(
            selected.clearance_status == "needs_approval" if selected else False
        ),
        explanation=explanation,
    )


def run_photo_rescue_for_api_feed_run(session: Session, run_id: int) -> int:
    records = session.scalars(
        select(ApiFeedRecord).where(ApiFeedRecord.api_feed_run_id == run_id)
    ).all()
    count = 0
    for record in records:
        if record.created_event_id and run_event_photo_rescue(
            session,
            record.created_event_id,
            commit=False,
        ):
            count += 1
    session.commit()
    return count


def run_photo_rescue_for_candidate_ids(
    session: Session,
    candidate_ids: list[int],
) -> int:
    event_ids = {
        candidate.event_id
        for candidate in session.scalars(
            select(ImageCandidate).where(ImageCandidate.id.in_(candidate_ids))
        ).all()
        if candidate.event_id is not None
    }
    count = 0
    for event_id in sorted(event_ids):
        if run_event_photo_rescue(session, event_id, commit=False):
            count += 1
    session.commit()
    return count


def run_photo_rescue_for_recently_approved_events(
    session: Session,
    *,
    days: int = 7,
) -> int:
    cutoff = utc_now() - timedelta(days=days)
    event_ids = list(
        session.scalars(
            select(Event.id).where(
                Event.category == "Concert",
                Event.record_type == "event",
                Event.created_at >= cutoff,
            )
        ).all()
    )
    count = 0
    for event_id in event_ids:
        if run_event_photo_rescue(session, event_id, commit=False):
            count += 1
    session.commit()
    return count
