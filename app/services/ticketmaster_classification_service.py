from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TicketmasterClassificationMapping:
    segment: str | None
    provider_genre: str | None
    provider_subgenre: str | None
    music_category: str | None
    normalized_genre: str | None
    event_relevance_score: float
    flags: tuple[str, ...]

    @property
    def is_music_signal(self) -> bool:
        return (self.segment or "").lower() == "music"


def node_name(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    for key in ("name", "segment", "genre", "subgenre", "subGenre"):
        raw = value.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def first_classification(payload: dict[str, Any]) -> dict[str, Any]:
    raw_classifications = payload.get("classifications")
    if isinstance(raw_classifications, list):
        for item in raw_classifications:
            if isinstance(item, dict):
                return item
    if isinstance(raw_classifications, dict):
        return raw_classifications
    return payload


def obvious_normalized_genre(genre: str | None, subgenre: str | None) -> str | None:
    for value in (subgenre, genre):
        if value and value.lower() not in {"undefined", "miscellaneous", "other"}:
            return value
    return None


def map_ticketmaster_classification(
    payload: dict[str, Any],
) -> TicketmasterClassificationMapping:
    """Map Ticketmaster classification data into event/music QA fields."""

    classification = first_classification(payload)
    segment = node_name(classification.get("segment"))
    genre = node_name(classification.get("genre"))
    subgenre = node_name(
        classification.get("subGenre") or classification.get("subgenre")
    )
    flags: list[str] = []
    music_category: str | None = None
    relevance = 40.0

    if segment and segment.lower() == "music":
        music_category = "Music"
        relevance = 94.0
        flags.append("ticketmaster_music_segment")
    elif segment:
        relevance = 25.0
        flags.extend(["ticketmaster_non_music_segment", "low_event_relevance"])
    else:
        relevance = 45.0
        flags.append("ticketmaster_segment_missing")

    return TicketmasterClassificationMapping(
        segment=segment,
        provider_genre=genre,
        provider_subgenre=subgenre,
        music_category=music_category,
        normalized_genre=obvious_normalized_genre(genre, subgenre),
        event_relevance_score=relevance,
        flags=tuple(flags),
    )
