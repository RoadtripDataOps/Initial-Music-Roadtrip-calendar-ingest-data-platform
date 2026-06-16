from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    ArtistSourceClaim,
    CanonicalArtist,
    Event,
    EventArtist,
    EventArtistRole,
    ImageCandidate,
    utc_now,
)
from app.services.genre_service import (
    genre_values_from_json,
    normalize_artist_genres,
    normalize_event_music_fields,
    normalize_genre_value,
)
from app.services.image_qa_service import (
    ImageCandidateInput,
    create_image_candidate,
    is_likely_direct_image_asset,
    normalize_image_url,
)


@dataclass(frozen=True)
class ArtistClaimInput:
    name: str
    source_type: str = "unknown"
    provider_artist_id: str | None = None
    provider_name: str | None = None
    source_url: str | None = None
    source_payload: dict[str, Any] | None = None
    external_identifiers: list[object] | None = None
    same_as: list[object] | None = None
    genres: list[str] | None = None
    image_url: str | None = None
    artist_type: str = "unknown"
    role: str = EventArtistRole.unknown.value
    performance_rank: int | None = None
    performance_date: datetime | None = None
    spotify_artist_id: str | None = None
    spotify_url: str | None = None
    jambase_artist_id: str | None = None
    cityspark_artist_id: str | None = None
    ticketmaster_artist_id: str | None = None
    musicbrainz_id: str | None = None
    match_confidence: float = 0.5
    match_reason: tuple[str, ...] = ("new_artist_claim",)


def normalize_artist_name(name: str | None) -> str:
    """Normalize artist names conservatively for matching."""

    value = (name or "").strip().casefold().replace("&", " and ")
    value = re.sub(r"['`´]", "", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    noise = {"the", "official", "live"}
    parts = [part for part in value.split() if part not in noise]
    return " ".join(parts)


def build_artist_key(name: str) -> str:
    normalized = normalize_artist_name(name)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return f"artist:{digest}"


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _safe_json_dict(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _as_list(value: object) -> list[object]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _dict_list(value: object) -> list[dict[str, Any]]:
    return [item for item in _as_list(value) if isinstance(item, dict)]


def _string_list(value: object) -> list[str]:
    items: list[str] = []
    for item in _as_list(value):
        if isinstance(item, str) and item.strip():
            items.append(item.strip())
        elif isinstance(item, dict):
            for key in ("name", "identifier", "url", "sameAs"):
                found = item.get(key)
                if isinstance(found, str) and found.strip():
                    items.append(found.strip())
                    break
    return items


def _first_string(value: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        found = value.get(key)
        if isinstance(found, str) and found.strip():
            return found.strip()
    return None


def _first_image(value: object) -> str | None:
    for item in _as_list(value):
        if isinstance(item, str) and is_likely_direct_image_asset(item):
            return item.strip()
        if isinstance(item, dict):
            for key in ("large", "medium", "small", "url", "image"):
                found = item.get(key)
                if isinstance(found, str) and is_likely_direct_image_asset(found):
                    return found.strip()
                nested = _first_image(found)
                if nested:
                    return nested
    return None


def _spotify_from_same_as(values: list[object]) -> tuple[str | None, str | None]:
    for item in values:
        text = ""
        if isinstance(item, str):
            text = item
        elif isinstance(item, dict):
            text = str(item.get("url") or item.get("identifier") or "")
        if "spotify.com/artist/" not in text:
            continue
        artist_id = text.rstrip("/").split("/")[-1].split("?")[0]
        return artist_id or None, text
    return None, None


def _same_as_url(values: list[object], marker: str) -> str | None:
    for item in values:
        text = ""
        if isinstance(item, str):
            text = item
        elif isinstance(item, dict):
            text = str(item.get("url") or item.get("identifier") or "")
        if marker in text.lower():
            return text
    return None


def _external_id(
    values: list[object],
    source_names: set[str],
) -> str | None:
    for item in values:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or item.get("provider") or "").lower()
        if source not in source_names:
            continue
        identifier = item.get("identifier") or item.get("id")
        if isinstance(identifier, str) and identifier.strip():
            return identifier.strip()
    return None


def _artist_type(value: str | None) -> str:
    lowered = (value or "").strip().lower()
    if lowered in {"band", "musician", "dj", "ensemble", "orchestra"}:
        return lowered
    if "dj" in lowered:
        return "dj"
    if "band" in lowered:
        return "band"
    if "musician" in lowered or "person" in lowered:
        return "musician"
    return "unknown"


def _role(value: str | None, *, is_headliner: bool = False) -> str:
    lowered = (value or "").strip().lower()
    if is_headliner:
        return EventArtistRole.headliner.value
    if lowered in {item.value for item in EventArtistRole}:
        return lowered
    if "dj" in lowered:
        return EventArtistRole.dj.value
    if "support" in lowered or "opener" in lowered:
        return EventArtistRole.supporting.value
    if lowered in {"performer", "artist"}:
        return EventArtistRole.performer.value
    return EventArtistRole.unknown.value


def _parse_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(str(value))
    except ValueError:
        return None


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def extract_artists_from_api_payload(
    provider: str | None,
    raw_payload: dict[str, Any],
) -> list[ArtistClaimInput]:
    """Extract artist claims from provider raw payloads without guessing."""

    provider_key = (provider or "unknown").strip().lower()
    event_payload = raw_payload.get("event")
    payload: dict[str, Any] = (
        event_payload if isinstance(event_payload, dict) else raw_payload
    )
    if provider_key == "jambase":
        claims: list[ArtistClaimInput] = []
        performers = payload.get("performer") or payload.get("performers") or []
        for index, performer in enumerate(_dict_list(performers)):
            name = _first_string(performer, "name")
            if not name:
                continue
            same_as = _as_list(performer.get("sameAs"))
            external_ids = _as_list(performer.get("x-externalIdentifiers"))
            spotify_id, spotify_url = _spotify_from_same_as(same_as + external_ids)
            provider_artist_id = _first_string(performer, "identifier")
            genres = _string_list(performer.get("genre"))
            is_headliner = bool(performer.get("x-isHeadliner"))
            role = (
                EventArtistRole.headliner.value
                if is_headliner
                else EventArtistRole.supporting.value
            )
            claims.append(
                ArtistClaimInput(
                    name=name,
                    source_type="jambase",
                    provider_artist_id=provider_artist_id,
                    provider_name="JamBase",
                    source_url=_first_string(performer, "url"),
                    source_payload=performer,
                    external_identifiers=external_ids,
                    same_as=same_as,
                    genres=genres,
                    image_url=_first_image(performer.get("image")),
                    artist_type=_artist_type(
                        _first_string(performer, "x-bandOrMusician"),
                    ),
                    role=role,
                    performance_rank=(
                        _parse_int(performer.get("x-performanceRank")) or index + 1
                    ),
                    performance_date=_parse_datetime(
                        performer.get("x-performanceDate"),
                    ),
                    spotify_artist_id=spotify_id,
                    spotify_url=spotify_url,
                    jambase_artist_id=provider_artist_id,
                    match_confidence=0.96 if provider_artist_id else 0.76,
                    match_reason=("jambase_performer",),
                )
            )
        return claims
    artist_value = raw_payload.get("artist")
    if isinstance(artist_value, dict):
        name = _first_string(artist_value, "name")
        if name:
            return [
                ArtistClaimInput(
                    name=name,
                    source_type=provider_key or "api_feed",
                    provider_artist_id=_first_string(artist_value, "id", "identifier"),
                    provider_name=provider_key,
                    source_payload=artist_value,
                    genres=_string_list(artist_value.get("genre")),
                    image_url=_first_image(artist_value.get("image")),
                    role=EventArtistRole.headliner.value,
                )
            ]
    return []


def _split_supporting(value: str | None) -> list[str]:
    if not value:
        return []
    parts = re.split(r"[,;\n]|\s+\+\s+|\s+with\s+", value)
    return [part.strip() for part in parts if part.strip()]


def extract_artists_from_event(event: Event) -> list[ArtistClaimInput]:
    """Extract conservative artist claims from a normalized event."""

    payload = _safe_json_dict(event.raw_event_json)
    raw_payload = payload.get("raw_payload")
    provider = event.api_provider_key or event.ingestion_provider or event.source_type
    if isinstance(raw_payload, dict):
        api_claims = extract_artists_from_api_payload(provider, raw_payload)
        if api_claims:
            return api_claims

    claims: list[ArtistClaimInput] = []
    if event.headliner:
        claims.append(
            ArtistClaimInput(
                name=event.headliner,
                source_type=event.source_type or "unknown",
                provider_artist_id=getattr(event, "upstream_artist_id", None),
                provider_name=event.ingestion_provider or event.api_provider_key,
                source_url=event.source_url,
                genres=[
                    item
                    for item in [
                        event.normalized_genre,
                        event.provider_genre,
                        event.genre,
                    ]
                    if item
                ],
                role=EventArtistRole.headliner.value,
                spotify_url=event.spotify_url,
                spotify_artist_id=event.spotify_artist_id,
                match_confidence=0.72,
                match_reason=("event_headliner",),
            )
        )
    for index, name in enumerate(_split_supporting(event.supporting_artists), start=2):
        claims.append(
            ArtistClaimInput(
                name=name,
                source_type=event.source_type or "unknown",
                provider_name=event.ingestion_provider or event.api_provider_key,
                source_url=event.source_url,
                genres=[event.normalized_genre] if event.normalized_genre else [],
                role=EventArtistRole.supporting.value,
                performance_rank=index,
                match_confidence=0.65,
                match_reason=("event_supporting_artist",),
            )
        )
    return claims


def match_existing_artist(
    session: Session,
    name: str,
    provider_ids: dict[str, str | None] | None = None,
    external_ids: dict[str, str | None] | None = None,
    genres: list[str] | None = None,
) -> tuple[CanonicalArtist | None, float, list[str]]:
    """Find an existing artist using strong IDs before medium name matching."""

    provider_ids = provider_ids or {}
    external_ids = external_ids or {}
    id_checks = [
        ("jambase_artist_id", provider_ids.get("jambase")),
        ("spotify_artist_id", provider_ids.get("spotify")),
        ("ticketmaster_artist_id", provider_ids.get("ticketmaster")),
        ("musicbrainz_id", external_ids.get("musicbrainz")),
    ]
    for field_name, identifier in id_checks:
        if not identifier:
            continue
        artist = session.scalars(
            select(CanonicalArtist).where(
                getattr(CanonicalArtist, field_name) == identifier,
            )
        ).first()
        if artist is not None:
            return artist, 0.98, [f"same_{field_name}"]
    normalized = normalize_artist_name(name)
    exact = session.scalars(
        select(CanonicalArtist).where(CanonicalArtist.normalized_name == normalized)
    ).first()
    if exact is None:
        return None, 0.0, ["no_match"]
    artist_genres = set(exact.normalized_genres)
    incoming_genres = {normalize_genre_value(genre) for genre in (genres or [])}
    if artist_genres & incoming_genres:
        return exact, 0.82, ["normalized_name_exact_genre_overlap"]
    if provider_ids and any(provider_ids.values()):
        return exact, 0.76, ["normalized_name_exact_provider_context"]
    return exact, 0.72, ["normalized_name_exact"]


def _merge_unique_json(existing_json: str | None, values: Sequence[object]) -> str:
    existing = genre_values_from_json(existing_json)
    merged = [str(item) for item in existing]
    for item in values:
        text = str(item).strip()
        if text and text not in merged:
            merged.append(text)
    return _json(merged)


def upsert_artist_from_claim(
    session: Session,
    claim: ArtistClaimInput,
) -> CanonicalArtist:
    jambase_artist_id = claim.jambase_artist_id
    if claim.source_type == "jambase" and not jambase_artist_id:
        jambase_artist_id = claim.provider_artist_id
    provider_ids = {
        "jambase": jambase_artist_id,
        "spotify": claim.spotify_artist_id,
        "ticketmaster": claim.ticketmaster_artist_id,
    }
    external_ids = {"musicbrainz": claim.musicbrainz_id}
    artist, confidence, reasons = match_existing_artist(
        session,
        claim.name,
        provider_ids,
        external_ids,
        claim.genres or [],
    )
    if artist is None:
        artist = CanonicalArtist(
            artist_key=build_artist_key(claim.name),
            display_name=claim.name.strip(),
            normalized_name=normalize_artist_name(claim.name),
            artist_type=claim.artist_type,
            first_seen_at=utc_now(),
            last_seen_at=utc_now(),
            raw_source_json=_json(claim.source_payload or {}),
        )
        session.add(artist)
        session.flush()
        confidence = claim.match_confidence
        reasons = list(claim.match_reason)
    artist.last_seen_at = utc_now()
    artist.artist_type = (
        artist.artist_type
        if artist.artist_type != "unknown"
        else claim.artist_type
    )
    artist.spotify_artist_id = artist.spotify_artist_id or claim.spotify_artist_id
    artist.spotify_url = artist.spotify_url or claim.spotify_url
    artist.instagram = artist.instagram or _same_as_url(
        claim.same_as or [],
        "instagram.com",
    )
    artist.facebook = artist.facebook or _same_as_url(
        claim.same_as or [],
        "facebook.com",
    )
    artist.x_url = (
        artist.x_url
        or _same_as_url(claim.same_as or [], "x.com")
        or _same_as_url(claim.same_as or [], "twitter.com")
    )
    artist.youtube = artist.youtube or _same_as_url(
        claim.same_as or [],
        "youtube.com",
    )
    artist.jambase_artist_id = artist.jambase_artist_id or jambase_artist_id
    artist.cityspark_artist_id = artist.cityspark_artist_id or claim.cityspark_artist_id
    artist.ticketmaster_artist_id = (
        artist.ticketmaster_artist_id or claim.ticketmaster_artist_id
    )
    artist.musicbrainz_id = artist.musicbrainz_id or claim.musicbrainz_id
    artist.image_url = artist.image_url or claim.image_url
    artist.image_status = artist.image_status or (
        "candidate" if claim.image_url else None
    )
    artist.image_clearance_status = artist.image_clearance_status or (
        "needs_approval" if claim.image_url else None
    )
    artist.provider_genres_json = _merge_unique_json(
        artist.provider_genres_json,
        claim.genres or [],
    )
    normalize_artist_genres(artist)

    existing_claim = session.scalars(
        select(ArtistSourceClaim).where(
            ArtistSourceClaim.artist_id == artist.id,
            ArtistSourceClaim.source_type == claim.source_type,
            ArtistSourceClaim.provider_artist_id == claim.provider_artist_id,
            ArtistSourceClaim.source_url == claim.source_url,
        )
    ).first()
    if existing_claim is None:
        source_claim = ArtistSourceClaim(
            artist_id=artist.id,
            source_type=claim.source_type,
            provider_artist_id=claim.provider_artist_id,
            provider_name=claim.provider_name or claim.source_type,
            source_url=claim.source_url,
            source_payload_json=_json(claim.source_payload or {}),
            external_identifiers_json=_json(claim.external_identifiers or []),
            same_as_json=_json(claim.same_as or []),
            genres_json=_json(claim.genres or []),
            image_url=claim.image_url,
            match_confidence=max(confidence, claim.match_confidence),
            match_reason_json=_json(
                list(dict.fromkeys([*reasons, *claim.match_reason])),
            ),
        )
        session.add(source_claim)
        session.flush()
    artist.source_claim_count = int(
        session.scalar(
            select(func.count(ArtistSourceClaim.id)).where(
                ArtistSourceClaim.artist_id == artist.id
            )
        )
        or 0
    )
    session.add(artist)
    return artist


def _upsert_event_artist(
    session: Session,
    event: Event,
    artist: CanonicalArtist,
    claim: ArtistClaimInput,
) -> EventArtist:
    role = _role(claim.role)
    link = session.scalars(
        select(EventArtist).where(
            EventArtist.event_id == event.id,
            EventArtist.artist_id == artist.id,
            EventArtist.role == role,
        )
    ).first()
    if link is None:
        link = EventArtist(
            event=event,
            artist=artist,
            role=role,
        )
        session.add(link)
    link.performance_rank = claim.performance_rank or link.performance_rank
    link.performance_date = claim.performance_date or link.performance_date
    link.provider_artist_id = claim.provider_artist_id or link.provider_artist_id
    link.source_claim_id = event.latest_source_claim_id or link.source_claim_id
    session.flush()
    return link


def _create_artist_image_candidate(
    session: Session,
    event: Event,
    artist: CanonicalArtist,
    claim: ArtistClaimInput,
) -> ImageCandidate | None:
    image_url = claim.image_url or artist.image_url
    if not image_url or not is_likely_direct_image_asset(image_url):
        return None
    normalized = normalize_image_url(image_url)
    existing = session.scalars(
        select(ImageCandidate).where(
            ImageCandidate.event_id == event.id,
            ImageCandidate.normalized_image_url == normalized,
            ImageCandidate.rescue_source == "provider_artist_image",
        )
    ).first()
    if existing is not None:
        artist.image_candidate_id = artist.image_candidate_id or existing.id
        return existing
    candidate = create_image_candidate(
        session,
        ImageCandidateInput(
            event_id=event.id,
            source_type="provider",
            source_provider=claim.source_type,
            source_url=claim.source_url or event.source_url,
            source_chain_json=event.source_chain_json,
            image_url=image_url,
            image_role="artist_press",
            clearance_status="needs_approval",
            rescue_source="provider_artist_image",
            rescue_priority=24 if claim.role == "headliner" else 40,
            artist_match_score=96.0 if claim.role == "headliner" else 76.0,
            music_signal_score=90.0,
            source_payload_path=f"artist_registry.artist[{artist.id}].image",
        ),
        commit=False,
    )
    artist.image_candidate_id = artist.image_candidate_id or candidate.id
    return candidate


def link_event_to_artists(
    session: Session,
    event_id: int,
    *,
    commit: bool = True,
) -> list[EventArtist]:
    """Create artist links for an event from reviewed normalized data."""

    event = session.scalars(
        select(Event)
        .options(selectinload(Event.venue), selectinload(Event.artist_links))
        .where(Event.id == event_id)
    ).first()
    if event is None or event.category != "Concert" or event.record_type != "event":
        return []
    links: list[EventArtist] = []
    for claim in extract_artists_from_event(event):
        if not normalize_artist_name(claim.name):
            continue
        artist = upsert_artist_from_claim(session, claim)
        link = _upsert_event_artist(session, event, artist, claim)
        _create_artist_image_candidate(session, event, artist, claim)
        links.append(link)
    normalize_event_music_fields(event)
    session.add(event)
    if commit:
        session.commit()
    return links


def rebuild_artist_registry(session: Session) -> dict[str, int]:
    """Rebuild artist links from existing normalized events only."""

    linked = 0
    events = list(session.scalars(select(Event).order_by(Event.id.asc())).all())
    for event in events:
        linked += len(link_event_to_artists(session, event.id, commit=False))
    session.commit()
    return {
        "events_processed": len(events),
        "event_artist_links": linked,
        "artists": int(session.scalar(select(func.count(CanonicalArtist.id))) or 0),
    }


def create_artist_image_candidates_for_event(
    session: Session,
    event_id: int,
) -> int:
    """Create local image candidates from linked canonical artist images."""

    event = session.scalars(
        select(Event)
        .options(selectinload(Event.artist_links).selectinload(EventArtist.artist))
        .where(Event.id == event_id)
    ).first()
    if event is None:
        return 0
    created = 0
    for link in event.artist_links:
        artist = link.artist
        claim = ArtistClaimInput(
            name=artist.display_name,
            source_type="artist_registry",
            image_url=artist.image_url,
            role=link.role,
        )
        if _create_artist_image_candidate(session, event, artist, claim) is not None:
            created += 1
    session.commit()
    return created


def _as_aware_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def list_artists(session: Session) -> list[CanonicalArtist]:
    return list(
        session.scalars(
            select(CanonicalArtist)
            .options(selectinload(CanonicalArtist.event_links))
            .order_by(CanonicalArtist.display_name.asc(), CanonicalArtist.id.asc())
        ).all()
    )


def get_artist(session: Session, artist_id: int) -> CanonicalArtist | None:
    return session.scalars(
        select(CanonicalArtist)
        .options(
            selectinload(CanonicalArtist.source_claims),
            selectinload(CanonicalArtist.event_links).selectinload(EventArtist.event),
        )
        .where(CanonicalArtist.id == artist_id)
    ).first()


def upcoming_event_count_for_artist(artist: CanonicalArtist) -> int:
    now = utc_now()
    count = 0
    for link in artist.event_links:
        if link.event is None:
            continue
        start = _as_aware_utc(link.event.start_datetime)
        if start is not None and start >= now:
            count += 1
    return count


def artist_duplicate_groups(session: Session) -> list[dict[str, object]]:
    rows = session.execute(
        select(
            CanonicalArtist.normalized_name,
            func.count(CanonicalArtist.id),
        )
        .group_by(CanonicalArtist.normalized_name)
        .having(func.count(CanonicalArtist.id) > 1)
    ).all()
    groups: list[dict[str, object]] = []
    for normalized_name, count in rows:
        artists = list(
            session.scalars(
                select(CanonicalArtist).where(
                    CanonicalArtist.normalized_name == normalized_name
                )
            ).all()
        )
        groups.append(
            {
                "normalized_name": normalized_name,
                "count": int(count),
                "artists": artists,
            }
        )
    return groups
