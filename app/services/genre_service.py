from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CanonicalArtist, Event

NORMALIZED_GENRES = (
    "Rock",
    "Pop",
    "Country",
    "Folk",
    "Blues",
    "Jazz",
    "Hip-Hop/Rap",
    "R&B/Soul",
    "Electronic/Dance",
    "Punk",
    "Metal",
    "Reggae",
    "Latin",
    "Classical",
    "Americana",
    "Bluegrass",
    "Indie",
    "Jam Band",
    "World",
    "Tribute",
    "Other / Unknown",
)

GENRE_ALIASES = {
    "alt country": "Americana",
    "alternative": "Indie",
    "alternative rock": "Rock",
    "americana": "Americana",
    "bluegrass": "Bluegrass",
    "blues": "Blues",
    "classical": "Classical",
    "country": "Country",
    "dance": "Electronic/Dance",
    "dj": "Electronic/Dance",
    "edm": "Electronic/Dance",
    "electronic": "Electronic/Dance",
    "folk": "Folk",
    "funk": "R&B/Soul",
    "hip hop": "Hip-Hop/Rap",
    "hip-hop": "Hip-Hop/Rap",
    "hip-hop/rap": "Hip-Hop/Rap",
    "indie": "Indie",
    "indie rock": "Indie",
    "jam": "Jam Band",
    "jam band": "Jam Band",
    "jamband": "Jam Band",
    "jazz": "Jazz",
    "latin": "Latin",
    "metal": "Metal",
    "music": "Other / Unknown",
    "pop": "Pop",
    "punk": "Punk",
    "rap": "Hip-Hop/Rap",
    "r&b": "R&B/Soul",
    "r&b/soul": "R&B/Soul",
    "reggae": "Reggae",
    "rock": "Rock",
    "soul": "R&B/Soul",
    "tribute": "Tribute",
    "world": "World",
}

NON_MUSIC_SEGMENTS = {"sports", "comedy", "family", "miscellaneous", "theatre"}


@dataclass(frozen=True)
class GenreNormalizationResult:
    normalized_genre: str
    normalized_genres: list[str]
    confidence: float
    source: str


def _clean(value: object) -> str:
    return str(value or "").strip()


def _json_list(values: list[str]) -> str:
    return json.dumps(list(dict.fromkeys(item for item in values if item)))


def genre_values_from_json(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if str(item).strip()]


def normalize_genre_value(value: object) -> str:
    """Map provider or uploaded genre strings into the broad MRT taxonomy."""

    cleaned = _clean(value)
    if not cleaned:
        return "Other / Unknown"
    lowered = cleaned.lower().replace("_", " ").replace("-", " ")
    lowered = " ".join(lowered.split())
    if lowered in GENRE_ALIASES:
        return GENRE_ALIASES[lowered]
    for token, mapped in GENRE_ALIASES.items():
        if token in lowered:
            return mapped
    return "Other / Unknown"


def normalize_genres(values: list[object]) -> GenreNormalizationResult:
    normalized: list[str] = []
    for value in values:
        if not _clean(value):
            continue
        mapped = normalize_genre_value(value)
        if mapped not in normalized:
            normalized.append(mapped)
    if not normalized:
        normalized = ["Other / Unknown"]
    known = [item for item in normalized if item != "Other / Unknown"]
    if known:
        normalized = known
    primary = known[0] if known else "Other / Unknown"
    confidence = 0.9 if known else 0.3
    source = "provider" if values and known else "unknown"
    return GenreNormalizationResult(
        normalized_genre=primary,
        normalized_genres=normalized,
        confidence=confidence,
        source=source,
    )


def compute_music_relevance(event: Event) -> tuple[float, list[str]]:
    """Score whether a normalized event looks musically relevant."""

    score = 50.0
    flags: list[str] = []
    segment = _clean(event.provider_music_segment).lower()
    category_text = " ".join(
        _clean(value).lower()
        for value in [
            event.music_category,
            event.provider_genre,
            event.provider_subgenre,
            event.normalized_genre,
            event.genre,
        ]
    )
    if segment == "music":
        score += 24
        flags.append("provider_music_segment")
    elif segment in NON_MUSIC_SEGMENTS:
        score -= 35
        flags.append(f"non_music_segment_{segment}")
    if event.api_provider_key == "jambase" or event.ingestion_provider == "jambase":
        score += 15
        flags.append("jambase_music_feed")
    if event.api_provider_key == "cityspark" and (
        "music" in category_text or "concert" in category_text
    ):
        score += 12
        flags.append("cityspark_music_category")
    if event.headliner:
        score += 10
        flags.append("headliner_present")
    if event.artist_links:
        score += 8
        flags.append("linked_artist")
    if event.venue and event.venue.category == "Music Site":
        score += 8
        flags.append("music_site_venue")
    if event.tickets_link or event.recommended_ticket_link:
        score += 4
        flags.append("ticket_link_present")
    if any(token in category_text for token in ["sports", "comedy", "family"]):
        score -= 20
        flags.append("non_music_category_signal")
    if not event.headliner:
        score -= 8
        flags.append("missing_artist")
    if event.venue is None:
        score -= 5
        flags.append("missing_venue")
    return max(0.0, min(100.0, round(score, 2))), list(dict.fromkeys(flags))


def normalize_event_music_fields(event: Event) -> Event:
    """Normalize genre and music relevance fields on an event in-place."""

    values: list[object] = []
    values.extend(genre_values_from_json(event.normalized_genres_json))
    values.extend(
        [
            event.normalized_genre,
            event.provider_genre,
            event.provider_subgenre,
            event.genre,
            event.music_category,
        ]
    )
    for link in event.artist_links:
        if link.artist is not None:
            values.extend(link.artist.normalized_genres)
    result = normalize_genres(values)
    event.normalized_genre = result.normalized_genre
    event.normalized_genres_json = _json_list(result.normalized_genres)
    event.genre_confidence = result.confidence
    event.genre_source = result.source
    relevance, flags = compute_music_relevance(event)
    event.music_relevance_score = relevance
    event.music_relevance_flags_json = _json_list(flags)
    return event


def normalize_artist_genres(artist: CanonicalArtist) -> CanonicalArtist:
    """Normalize artist genre collections in-place."""

    provider_genres = genre_values_from_json(artist.provider_genres_json)
    result = normalize_genres(provider_genres + [artist.primary_genre])
    artist.primary_genre = result.normalized_genre
    artist.normalized_genres_json = _json_list(result.normalized_genres)
    if artist.quality_score is None:
        artist.quality_score = 70.0 if result.confidence >= 0.8 else 45.0
    return artist


def normalize_all_genres(session: Session) -> dict[str, int]:
    """Normalize all existing event and artist genre fields locally."""

    event_count = 0
    artist_count = 0
    for event in session.scalars(select(Event)).all():
        normalize_event_music_fields(event)
        session.add(event)
        event_count += 1
    for artist in session.scalars(select(CanonicalArtist)).all():
        normalize_artist_genres(artist)
        session.add(artist)
        artist_count += 1
    session.commit()
    return {"events": event_count, "artists": artist_count}
