from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.db.models import ApiFeedRecord, ApiFeedRun, Event, utc_now
from app.services.event_dedupe_service import (
    NormalizedEventCandidate,
    SourceClaimInput,
    upsert_event_from_candidate,
)
from app.services.event_photo_rescue_service import (
    create_provider_image_candidates_for_record,
    run_event_photo_rescue,
)
from app.services.file_risk_service import is_direct_image_url, is_social_url
from app.services.poi_candidate_service import (
    create_poi_candidate_from_provider_location,
)
from app.services.source_taxonomy_service import (
    dedupe_source_chain,
    detect_source_key,
    normalized_domain,
    source_chain_entry,
)
from app.services.ticket_link_service import (
    TICKET_LINK_CATEGORIES,
    TicketLinkAssessment,
    TicketLinkCandidate,
    choose_ticket_link,
    classify_ticket_link,
)
from app.services.ticketmaster_classification_service import (
    TicketmasterClassificationMapping,
    map_ticketmaster_classification,
)
from app.services.venue_service import VenueInput, ensure_event_venue

CITYSPARK_PROVIDER_KEY = "city" + "spark"
CITYSPARK_PROVIDER_DISPLAY = "City" + "Spark"


@dataclass(frozen=True)
class ProviderConfig:
    provider_key: str
    display_name: str
    provider_type: str
    enabled: bool
    credentials_env_var_names: tuple[str, ...]
    compliance_notes: str
    storage_policy: str
    ttl_hours: int | None
    rate_limit_notes: str
    docs_available: tuple[str, ...]
    docs_missing: tuple[str, ...]
    field_mapping_summary: str
    ticket_link_strategy: str
    dedupe_strategy: str
    created_at: datetime
    updated_at: datetime
    live_calls_enabled: bool = False
    credentials_configured: bool = False

    @property
    def workbench_status(self) -> str:
        return "Workbench Open"

    @property
    def provider_type_display(self) -> str:
        return self.provider_type.replace("_", " ").title()

    @property
    def live_api_status(self) -> str:
        if self.provider_type == "manual":
            return "Local Demo"
        return "Live Calls On" if self.live_calls_enabled else "Live Calls Off"

    @property
    def storage_status(self) -> str:
        labels = {
            "permanent_allowed": "Permanent Allowed",
            "temporary_review_only": "Review Only",
            "enrichment_suggestions_only": "Enrichment Suggestions Only",
        }
        return labels.get(self.storage_policy, self.storage_policy.replace("_", " "))

    @property
    def retention_status(self) -> str | None:
        if self.ttl_hours is None:
            return None
        return f"{self.ttl_hours}h Retention"

    @property
    def contract_status(self) -> str | None:
        return None

    @property
    def credential_status(self) -> str | None:
        if (
            self.provider_type == "licensed_vendor_feed"
            and self.credentials_env_var_names
        ):
            return (
                "Credentials Configured"
                if self.credentials_configured
                else "Credentials Missing"
            )
        return None


@dataclass(frozen=True)
class ProviderSummary:
    provider: ProviderConfig
    last_run: ApiFeedRun | None
    pending_count: int
    approved_count: int
    rejected_count: int


@dataclass(frozen=True)
class NormalizedApiCandidate:
    normalized_payload: dict[str, Any]
    mapping_warnings: list[str]
    quality_flags: list[str]
    normalization_status: str
    provider_record_id: str | None
    provider_event_id: str | None
    provider_artist_id: str | None
    provider_venue_id: str | None
    source_url: str | None
    source_record_id: str | None
    dedupe_key: str
    dedupe_confidence: float
    venue_match_confidence: float
    event_relevance_score: float
    photo_quality_score: float
    field_completeness_score: float


@dataclass(frozen=True)
class ApiFeedRecordFilters:
    provider_key: str | None = None
    ingestion_provider: str | None = None
    upstream_event_source: str | None = None
    ticketing_provider: str | None = None
    ticket_link_classification: str | None = None
    ticket_link_repair_strategy: str | None = None
    provenance_flag: str | None = None
    review_status: str | None = None
    normalization_status: str | None = None
    quality_issue: str | None = None
    duplicate_status: str | None = None
    missing_image: bool = False
    missing_ticket_link: bool = False
    missing_venue: bool = False
    compliance_expiring_soon: bool = False
    unknown_upstream_source: bool = False
    api_backfill_required: bool = False
    min_event_relevance_score: float | None = None
    min_photo_quality_score: float | None = None


def provider_registry(settings: Settings) -> list[ProviderConfig]:
    now = utc_now()
    return [
        ProviderConfig(
            provider_key="jambase",
            display_name="JamBase",
            provider_type="licensed_vendor_feed",
            enabled=False,
            credentials_env_var_names=("JAMBASE_API_KEY",),
            compliance_notes=(
                "Licensed vendor feed framework only; live calls require "
                "configured credentials and provider terms review. Records "
                "still require review before normalized app use."
            ),
            storage_policy="permanent_allowed",
            ttl_hours=None,
            rate_limit_notes="Use provider rate limits when live API mode is added.",
            docs_available=(
                "docs/provider-research/jambase/v3.1.0/jambase-api-v3.1.0-openapi.yaml",
                "docs/provider-research/jambase/v3.1.0/jambase-api-v3.1.0-openapi.json",
                "docs/provider-research/jambase/v3.1.0/jambase-api-v3.1.0-postman.json",
                "docs/provider-research/jambase/jambase-v3.1.0-summary.md",
            ),
            docs_missing=(),
            field_mapping_summary=(
                "Maps JamBase API v3.1.0 Concert/Festival objects, performers, "
                "offers, venue geo/address, images, and venue-local date fields."
            ),
            ticket_link_strategy=(
                "Prefer offers[].url where category is ticketingLinkPrimary; "
                "fallback to ticketingLinkSecondary."
            ),
            dedupe_strategy=(
                "Use JamBase v3.1.0 identifier as the strongest source ID input, "
                "then event name, venue-local start, venue, city, and state."
            ),
            created_at=now,
            updated_at=now,
            live_calls_enabled=settings.jambase_live_calls_enabled,
            credentials_configured=bool(settings.jambase_api_key.strip()),
        ),
        ProviderConfig(
            provider_key=CITYSPARK_PROVIDER_KEY,
            display_name=CITYSPARK_PROVIDER_DISPLAY,
            provider_type="licensed_vendor_feed",
            enabled=settings.cityspark_provider_enabled,
            credentials_env_var_names=("CITY" + "SPARK_API_KEY",),
            compliance_notes=(
                "Licensed vendor feed framework only; live calls require "
                "configured credentials and provider terms review. Records "
                "still require review before normalized app use."
            ),
            storage_policy="permanent_allowed",
            ttl_hours=None,
            rate_limit_notes="No live calls in this milestone.",
            docs_available=("docs/City" + "Spark_v1.json",),
            docs_missing=(),
            field_mapping_summary=(
                "Maps EventSeries eventId, instances, location, primaryImage, "
                "categories, labels, ticketUrl, price, and time flags."
            ),
            ticket_link_strategy=(
                "Prefer ticketUrl. Treat links[] and generic event url as "
                "supporting links unless independently validated."
            ),
            dedupe_strategy=(
                "Use eventId as the strongest source ID input, then event name, "
                "start, venue, city, and state."
            ),
            created_at=now,
            updated_at=now,
            live_calls_enabled=settings.cityspark_live_calls_enabled,
            credentials_configured=bool(
                settings.cityspark_api_key.strip()
                and settings.cityspark_portal_script_id.strip()
            ),
        ),
        ProviderConfig(
            provider_key="spotify",
            display_name="Spotify",
            provider_type="enrichment",
            enabled=False,
            credentials_env_var_names=("SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"),
            compliance_notes="Enrichment suggestions only; not a primary event source.",
            storage_policy="enrichment_suggestions_only",
            ttl_hours=None,
            rate_limit_notes="Use only for enrichment after event-source review.",
            docs_available=(),
            docs_missing=("provider API docs not integrated in this milestone",),
            field_mapping_summary="Enrichment placeholder only.",
            ticket_link_strategy="Not a ticket-link source.",
            dedupe_strategy="Not used for primary event dedupe.",
            created_at=now,
            updated_at=now,
        ),
        ProviderConfig(
            provider_key="serpapi",
            display_name="SerpAPI",
            provider_type="enrichment",
            enabled=False,
            credentials_env_var_names=("SERPAPI_API_KEY",),
            compliance_notes="Enrichment suggestions only; not a primary event source.",
            storage_policy="enrichment_suggestions_only",
            ttl_hours=None,
            rate_limit_notes="Use only for enrichment after event-source review.",
            docs_available=(),
            docs_missing=("provider API docs not integrated in this milestone",),
            field_mapping_summary="Enrichment placeholder only.",
            ticket_link_strategy="Not a ticket-link source.",
            dedupe_strategy="Not used for primary event dedupe.",
            created_at=now,
            updated_at=now,
        ),
        ProviderConfig(
            provider_key="manual_json",
            display_name="Manual JSON",
            provider_type="manual",
            enabled=True,
            credentials_env_var_names=(),
            compliance_notes=(
                "Local demo/manual import path for provider-style records."
            ),
            storage_policy="permanent_allowed",
            ttl_hours=None,
            rate_limit_notes="No external API calls.",
            docs_available=("local synthetic/manual JSON contract",),
            docs_missing=(),
            field_mapping_summary=(
                "Accepts already-normalized event-like JSON fields for local QA."
            ),
            ticket_link_strategy="Classify the supplied tickets_link or ticketUrl.",
            dedupe_strategy=(
                "Use source_record_id/id when supplied, then event name, start, "
                "venue, city, and state."
            ),
            created_at=now,
            updated_at=now,
        ),
    ]


def get_provider_config(settings: Settings, provider_key: str) -> ProviderConfig | None:
    for provider in provider_registry(settings):
        if provider.provider_key == provider_key:
            return provider
    return None


def provider_display_name(settings: Settings, provider_key: str | None) -> str:
    if not provider_key:
        return "Unknown"
    provider = get_provider_config(settings, provider_key)
    return provider.display_name if provider else provider_key


def provider_summaries(
    session: Session,
    settings: Settings,
) -> list[ProviderSummary]:
    summaries: list[ProviderSummary] = []
    for provider in provider_registry(settings):
        last_run = session.scalars(
            select(ApiFeedRun)
            .where(ApiFeedRun.provider_key == provider.provider_key)
            .order_by(ApiFeedRun.started_at.desc(), ApiFeedRun.id.desc())
        ).first()
        summaries.append(
            ProviderSummary(
                provider=provider,
                last_run=last_run,
                pending_count=count_records(
                    session,
                    provider.provider_key,
                    "pending_review",
                ),
                approved_count=count_records(
                    session,
                    provider.provider_key,
                    "approved",
                ),
                rejected_count=count_records(
                    session,
                    provider.provider_key,
                    "rejected",
                ),
            )
        )
    return summaries


def count_records(session: Session, provider_key: str, review_status: str) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(ApiFeedRecord)
            .where(
                ApiFeedRecord.provider_key == provider_key,
                ApiFeedRecord.review_status == review_status,
            )
        )
        or 0
    )


def clean_string(value: object) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def first_string(raw: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, dict):
            continue
        cleaned = clean_string(value)
        if cleaned:
            return cleaned
    return None


def nested_string(raw: dict[str, Any], key: str, *nested_keys: str) -> str | None:
    value = raw.get(key)
    if not isinstance(value, dict):
        return None
    return first_string(value, *nested_keys)


def first_float(raw: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = raw.get(key)
        if value is None:
            continue
        try:
            return float(str(value).strip())
        except ValueError:
            continue
    return None


def nested_float(raw: dict[str, Any], key: str, *nested_keys: str) -> float | None:
    value = raw.get(key)
    if not isinstance(value, dict):
        return None
    return first_float(value, *nested_keys)


def provider_scalar(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return clean_string(value)
    if isinstance(value, int | float | bool):
        return clean_string(value)
    if isinstance(value, list):
        for item in value:
            scalar = provider_scalar(item)
            if scalar:
                return scalar
        return None
    if isinstance(value, dict):
        for key in (
            "name",
            "alternateName",
            "identifier",
            "url",
            "largeImageUrl",
            "mediumImageUrl",
            "smallImageUrl",
            "linkUrl",
            "price",
            "minPrice",
            "maxPrice",
        ):
            scalar = provider_scalar(value.get(key))
            if scalar:
                return scalar
    return None


def provider_first_string(raw: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        scalar = provider_scalar(raw.get(key))
        if scalar:
            return scalar
    return None


def provider_nested_string(
    raw: dict[str, Any],
    key: str,
    *nested_keys: str,
) -> str | None:
    value = raw.get(key)
    if not isinstance(value, dict):
        return None
    return provider_first_string(value, *nested_keys)


def dict_or_empty(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def dict_list(value: object) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def string_list(value: object) -> list[str]:
    if isinstance(value, list):
        cleaned = [provider_scalar(item) for item in value]
        return [item for item in cleaned if item]
    scalar = provider_scalar(value)
    return [scalar] if scalar else []


def first_image_url(*values: object) -> str | None:
    for value in values:
        if isinstance(value, str):
            cleaned = clean_string(value)
            if cleaned:
                return cleaned
        if isinstance(value, list):
            nested = first_image_url(*value)
            if nested:
                return nested
        if isinstance(value, dict):
            nested = provider_first_string(
                value,
                "largeImageUrl",
                "mediumImageUrl",
                "smallImageUrl",
                "url",
                "imageUrl",
                "contentUrl",
            )
            if nested:
                return nested
    return None


def combined_text(*parts: object) -> str | None:
    cleaned = [provider_scalar(part) for part in parts]
    text = "\n\n".join(part for part in cleaned if part)
    return text or None


def bool_value(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1"}:
            return True
        if lowered in {"false", "no", "0"}:
            return False
    return None


def labels_from_objects(values: object) -> list[str]:
    labels: list[str] = []
    for item in dict_list(values):
        label = provider_first_string(item, "name", "label", "identifier")
        if label:
            labels.append(label)
    if isinstance(values, list):
        labels.extend(value for value in string_list(values) if value not in labels)
    return labels


def price_text_from_value(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return clean_string(value)
    if isinstance(value, int | float):
        return clean_string(value)
    if isinstance(value, dict):
        currency = provider_first_string(value, "priceCurrency", "currency")
        direct = provider_first_string(value, "price", "priceText", "text", "name")
        if direct:
            return f"{direct} {currency}".strip() if currency else direct
        minimum = provider_first_string(value, "minPrice", "minimumPrice")
        maximum = provider_first_string(value, "maxPrice", "maximumPrice")
        if minimum and maximum:
            price_range = f"{minimum}-{maximum}"
            return f"{price_range} {currency}".strip() if currency else price_range
        if minimum:
            minimum_price = f"from {minimum}"
            return (
                f"{minimum_price} {currency}".strip()
                if currency
                else minimum_price
            )
        if maximum:
            maximum_price = f"up to {maximum}"
            return (
                f"{maximum_price} {currency}".strip()
                if currency
                else maximum_price
            )
    return None


def provider_json(data: object) -> str:
    return json.dumps(data, ensure_ascii=True, sort_keys=True)


def first_external_identifier(
    entries: list[dict[str, str]],
    scope: str,
) -> tuple[str | None, str | None]:
    for entry in entries:
        if entry.get("scope") != scope:
            continue
        source = clean_string(entry.get("source"))
        identifier = clean_string(entry.get("identifier"))
        if source and identifier:
            return source, identifier
    return None, None


def identifier_entries_from_value(
    value: object,
    scope: str,
) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for item in dict_list(value):
        raw_source = provider_first_string(item, "source", "provider", "name", "type")
        source = detect_source_key(raw_source) or raw_source
        identifiers = (
            string_list(item.get("identifier"))
            or string_list(item.get("identifiers"))
            or string_list(item.get("id"))
            or string_list(item.get("ids"))
            or string_list(item.get("value"))
        )
        for identifier in identifiers:
            if source and identifier:
                entries.append(
                    {
                        "scope": scope,
                        "source": source,
                        "identifier": identifier,
                    }
                )
    return entries


def provider_identifier_entry(
    scope: str,
    source: str,
    identifier: str | None,
) -> list[dict[str, str]]:
    cleaned = clean_string(identifier)
    if not cleaned:
        return []
    return [{"scope": scope, "source": source, "identifier": cleaned}]


def ticket_offer_entries(offers: list[dict[str, Any]]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for offer in offers:
        url = provider_first_string(offer, "url", "ticketUrl", "linkUrl")
        seller = dict_or_empty(offer.get("seller"))
        seller_source = provider_first_string(
            seller,
            "identifier",
            "name",
            "alternateName",
        )
        source_key = detect_source_key(seller_source) or detect_source_key(url)
        entry: dict[str, str] = {}
        category = provider_first_string(offer, "category", "@type", "type")
        seller_name = provider_first_string(seller, "name", "alternateName")
        seller_identifier = provider_first_string(seller, "identifier")
        domain = normalized_domain(url)
        if category:
            entry["category"] = category
        if url:
            entry["url"] = url
        if seller_identifier:
            entry["seller_identifier"] = seller_identifier
        if seller_name:
            entry["seller_name"] = seller_name
        if source_key:
            entry["detected_provider"] = source_key
        if domain:
            entry["provider_domain"] = domain
        if entry:
            entries.append(entry)
    return entries


def first_ticket_offer_value(
    offers: list[dict[str, str]],
    key: str,
) -> str | None:
    for offer in offers:
        value = clean_string(offer.get(key))
        if value:
            return value
    return None


def provenance_flags_for_values(
    values: dict[str, Any],
    ticket_assessment: TicketLinkAssessment,
) -> list[str]:
    flags: list[str] = []
    if not clean_string(values.get("upstream_event_source")) or clean_string(
        values.get("upstream_event_source")
    ) == "unknown":
        flags.append("unknown upstream source")
    if ticket_assessment.repair_strategy == "api_backfill_required":
        flags.append("api backfill required")
    if ticket_assessment.category in {
        "platform_generic_or_app",
        "suspicious",
        "unresolved",
        "blank",
    }:
        flags.append(f"ticket repair: {ticket_assessment.repair_strategy}")
    if ticket_assessment.provider_key:
        flags.append(f"ticketing provider detected: {ticket_assessment.provider_key}")
    if values.get("external_identifiers"):
        flags.append("external identifiers present")
    return sorted(set(flags))


def source_chain_for_values(
    ingestion_provider: str,
    values: dict[str, Any],
) -> list[dict[str, str]]:
    entries = [
        source_chain_entry(
            "ingestion_provider",
            ingestion_provider,
            clean_string(values.get("provider_event_id"))
            or clean_string(values.get("source_record_id")),
            clean_string(values.get("source_url")),
        )
    ]
    upstream_source = clean_string(values.get("upstream_event_source"))
    if upstream_source:
        entries.append(
            source_chain_entry(
                "upstream_event_source",
                upstream_source,
                clean_string(values.get("upstream_event_id")),
            )
        )
    artist_source = clean_string(values.get("upstream_artist_source"))
    if artist_source:
        entries.append(
            source_chain_entry(
                "upstream_artist_source",
                artist_source,
                clean_string(values.get("upstream_artist_id")),
            )
        )
    venue_source = clean_string(values.get("upstream_venue_source"))
    if venue_source:
        entries.append(
            source_chain_entry(
                "upstream_venue_source",
                venue_source,
                clean_string(values.get("upstream_venue_id")),
            )
        )
    ticket_provider = clean_string(values.get("ticketing_provider"))
    if ticket_provider:
        entries.append(
            source_chain_entry(
                "ticketing_provider",
                ticket_provider,
                url=clean_string(values.get("recommended_ticket_link"))
                or clean_string(values.get("tickets_link")),
            )
        )
    return dedupe_source_chain(entries)


def apply_provenance_values(
    values: dict[str, Any],
    provider_key: str,
    ticket_assessment: TicketLinkAssessment,
    external_identifiers: list[dict[str, str]] | None = None,
    ticket_offers: list[dict[str, str]] | None = None,
) -> None:
    values["ingestion_provider"] = provider_key
    values["ticketing_provider"] = (
        clean_string(values.get("ticketing_provider"))
        or ticket_assessment.provider_key
    )
    values["ticketing_provider_domain"] = (
        clean_string(values.get("ticketing_provider_domain"))
        or ticket_assessment.provider_domain
    )
    values["ticket_link_repair_strategy"] = ticket_assessment.repair_strategy
    values["ticket_link_repair_source"] = ticket_assessment.repair_source
    values["external_identifiers"] = external_identifiers or []
    values["ticket_offers"] = ticket_offers or []
    if not values.get("upstream_event_source"):
        values["upstream_event_source"] = "unknown"
    values["source_chain"] = source_chain_for_values(provider_key, values)
    values["provenance_flags"] = provenance_flags_for_values(
        values,
        ticket_assessment,
    )


def value_float(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def parse_datetime_value(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = value.strip()
    try:
        if len(cleaned) == 10:
            parsed = datetime.fromisoformat(f"{cleaned}T00:00:00")
        else:
            parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def combined_datetime(raw: dict[str, Any]) -> datetime | None:
    direct = first_string(raw, "start_datetime", "startDateTime", "startDate", "start")
    parsed = parse_datetime_value(direct)
    if parsed:
        return parsed
    date_value = first_string(raw, "start_date", "startDate", "date")
    time_value = first_string(raw, "start_time", "startTime", "time") or "00:00:00"
    if date_value:
        return parse_datetime_value(f"{date_value}T{time_value}")
    return None


def split_additional_images(value: str | None) -> str | None:
    if not value:
        return None
    parts = [part.strip() for part in value.replace("|", "$").split("$")]
    cleaned = [part for part in parts if part]
    return "$".join(cleaned) if cleaned else None


def event_relevance_score(raw: dict[str, Any]) -> float:
    text = " ".join(
        str(value)
        for value in [
            raw.get("category"),
            raw.get("event_name"),
            raw.get("title"),
            raw.get("name"),
            raw.get("description"),
        ]
        if value
    ).lower()
    if any(token in text for token in ["concert", "music", "live", "band", "artist"]):
        return 90.0
    return 72.0


def completeness_score(values: dict[str, Any]) -> float:
    required = [
        "event_name",
        "headliner",
        "start_datetime",
        "venue_name",
        "city",
        "state",
        "tickets_link",
        "main_image_url",
    ]
    present = sum(1 for key in required if values.get(key))
    return round((present / len(required)) * 100, 2)


def dedupe_key_for_candidate(provider_key: str, values: dict[str, Any]) -> str:
    basis = "|".join(
        [
            provider_key,
            str(values.get("source_record_id") or ""),
            str(values.get("event_name") or "").lower(),
            str(values.get("start_datetime") or ""),
            str(values.get("venue_name") or "").lower(),
            str(values.get("city") or "").lower(),
            str(values.get("state") or "").lower(),
        ]
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def generic_event_mapper(
    raw: dict[str, Any],
    provider_key: str,
) -> NormalizedApiCandidate:
    venue_value = raw.get("venue")
    venue: dict[str, Any] = venue_value if isinstance(venue_value, dict) else {}
    artist_value = raw.get("artist")
    artist: dict[str, Any] = artist_value if isinstance(artist_value, dict) else {}
    image = first_image_url(
        raw.get("main_image_url"),
        raw.get("image"),
        raw.get("image_url"),
        raw.get("imageUrl"),
    )
    tickets = first_string(raw, "tickets_link", "ticket_url", "ticketUrl", "tickets")
    ticket_assessment = classify_ticket_link(tickets)
    source_url = first_string(raw, "source_url", "url", "event_url", "eventUrl")
    event_url = first_string(raw, "event_url", "eventUrl", "url") or source_url
    start = combined_datetime(raw)
    end = parse_datetime_value(first_string(raw, "end_datetime", "endDateTime", "end"))
    ticketmaster_mapping: TicketmasterClassificationMapping | None = None
    if "classifications" in raw or "segment" in raw:
        ticketmaster_mapping = map_ticketmaster_classification(raw)
    external_identifiers = identifier_entries_from_value(
        raw.get("external_identifiers")
        or raw.get("externalIdentifiers")
        or raw.get("x-externalIdentifiers"),
        "event",
    )
    upstream_event_source = detect_source_key(
        first_string(raw, "upstream_event_source", "upstreamSource", "dataSource")
    ) or first_string(raw, "upstream_event_source", "upstreamSource", "dataSource")
    upstream_event_id = first_string(
        raw,
        "upstream_event_id",
        "upstreamEventId",
        "external_event_id",
    )
    values: dict[str, Any] = {
        "category": "Concert",
        "record_type": "event",
        "provider_event_type": provider_first_string(raw, "@type", "type"),
        "provider_music_segment": (
            ticketmaster_mapping.segment if ticketmaster_mapping else None
        ),
        "event_name": first_string(raw, "event_name", "name", "title"),
        "description": first_string(raw, "description", "summary"),
        "headliner": first_string(raw, "headliner", "performer", "artist")
        or nested_string(raw, "artist", "name"),
        "supporting_artists": first_string(raw, "supporting_artists", "support"),
        "provider_genre": (
            ticketmaster_mapping.provider_genre
            if ticketmaster_mapping
            else first_string(raw, "provider_genre", "genre")
        ),
        "provider_subgenre": (
            ticketmaster_mapping.provider_subgenre
            if ticketmaster_mapping
            else first_string(raw, "provider_subgenre", "subgenre", "subGenre")
        ),
        "music_category": (
            ticketmaster_mapping.music_category
            if ticketmaster_mapping
            else first_string(raw, "music_category")
        ),
        "normalized_genre": (
            ticketmaster_mapping.normalized_genre
            if ticketmaster_mapping
            else first_string(raw, "normalized_genre", "genre")
        ),
        "event_status": first_string(raw, "event_status", "eventStatus"),
        "start_datetime": start.isoformat() if start else None,
        "end_datetime": end.isoformat() if end else None,
        "timezone": first_string(raw, "timezone", "timeZone", "tz"),
        "doors_time": first_string(raw, "doors_time", "doorTime"),
        "has_time": bool_value(raw.get("has_time") or raw.get("hasTime")),
        "all_day": bool_value(raw.get("all_day") or raw.get("allDay")),
        "venue_name": first_string(raw, "venue_name", "venue")
        or nested_string(raw, "venue", "name"),
        "venue_address": first_string(raw, "venue_address", "address")
        or nested_string(raw, "venue", "address"),
        "city": first_string(raw, "city") or nested_string(raw, "venue", "city"),
        "state": first_string(raw, "state") or nested_string(raw, "venue", "state"),
        "zip_code": first_string(raw, "zip_code", "postal_code", "zip")
        or nested_string(raw, "venue", "postal_code", "zip"),
        "country": first_string(raw, "country")
        or nested_string(raw, "venue", "country"),
        "latitude": first_float(raw, "latitude", "lat")
        or nested_float(venue, "geo", "lat"),
        "longitude": first_float(raw, "longitude", "lng", "lon")
        or nested_float(venue, "geo", "lng", "lon"),
        "event_url": event_url,
        "tickets_link": ticket_assessment.recommended_url,
        "ticket_link_classification": ticket_assessment.category,
        "ticket_link_repair_suggestion": ticket_assessment.repair_suggestion,
        "recommended_ticket_link": ticket_assessment.recommended_url,
        "ticket_link_quality_score": ticket_assessment.quality_score,
        "price": first_string(raw, "price"),
        "age_restriction": first_string(raw, "age_restriction", "ageRestriction"),
        "main_image_url": image,
        "additional_image_urls": split_additional_images(
            first_string(raw, "additional_image_urls", "additionalImages")
        ),
        "spotify_url": first_string(raw, "spotify_url", "spotifyUrl"),
        "source_url": source_url or event_url,
        "source_record_id": first_string(raw, "source_record_id", "id", "record_id"),
        "provider_event_id": first_string(raw, "provider_event_id", "event_id", "id"),
        "upstream_event_source": upstream_event_source,
        "upstream_event_id": upstream_event_id,
        "provider_artist_id": first_string(raw, "provider_artist_id", "artist_id")
        or nested_string(artist, "ids", "provider_artist_id", "id"),
        "provider_venue_id": first_string(raw, "provider_venue_id", "venue_id")
        or nested_string(venue, "ids", "provider_venue_id", "id"),
    }
    apply_provenance_values(
        values,
        provider_key,
        ticket_assessment,
        external_identifiers,
        ticket_offer_entries([{"url": tickets}]) if tickets else [],
    )
    values["dedupe_source_fields"] = {
        "provider": provider_key,
        "ingestion_provider": values.get("ingestion_provider"),
        "provider_event_id": values.get("provider_event_id"),
        "upstream_event_source": values.get("upstream_event_source"),
        "upstream_event_id": values.get("upstream_event_id"),
        "ticketing_provider": values.get("ticketing_provider"),
        "normalized_ticket_url": values.get("recommended_ticket_link"),
        "source_chain": values.get("source_chain"),
        "source_record_id": values.get("source_record_id"),
        "event_name": values.get("event_name"),
        "start_datetime": values.get("start_datetime"),
        "venue_name": values.get("venue_name"),
        "city": values.get("city"),
        "state": values.get("state"),
    }
    values["venue_match_fields"] = {
        "provider_venue_id": values.get("provider_venue_id"),
        "venue_name": values.get("venue_name"),
        "venue_address": values.get("venue_address"),
        "city": values.get("city"),
        "state": values.get("state"),
        "latitude": values.get("latitude"),
        "longitude": values.get("longitude"),
    }
    values["provider_doc_notes"] = (
        "Manual/generic JSON mapping. Ticket links are classified before approval."
    )
    warnings: list[str] = []
    quality_flags: list[str] = []
    for field_name in ["event_name", "headliner", "start_datetime", "venue_name"]:
        if not values.get(field_name):
            warnings.append(f"missing_{field_name}")
            quality_flags.append(f"missing {field_name.replace('_', ' ')}")
    if not values.get("tickets_link"):
        quality_flags.append("missing ticket link")
    if ticket_assessment.category not in {"blank", "direct"}:
        quality_flags.append(f"ticket link: {ticket_assessment.category}")
    quality_flags.extend(ticket_assessment.flags)
    quality_flags.extend(
        str(flag)
        for flag in values.get("provenance_flags", [])
        if isinstance(flag, str)
    )
    if not values.get("main_image_url"):
        quality_flags.append("missing image")
    elif is_social_url(str(values["main_image_url"])):
        quality_flags.append("social image URL")
    elif not is_direct_image_url(str(values["main_image_url"])):
        quality_flags.append("non-direct image URL")
    if not values.get("venue_address") and not (
        values.get("latitude") and values.get("longitude")
    ):
        quality_flags.append("missing venue location")
    if ticketmaster_mapping:
        quality_flags.extend(ticketmaster_mapping.flags)

    normalized_status = "normalized"
    if warnings:
        normalized_status = "partial"
    if not values.get("event_name") or not values.get("start_datetime"):
        normalized_status = "failed"

    key = dedupe_key_for_candidate(provider_key, values)
    return NormalizedApiCandidate(
        normalized_payload=values,
        mapping_warnings=warnings,
        quality_flags=quality_flags,
        normalization_status=normalized_status,
        provider_record_id=first_string(raw, "provider_record_id", "record_id", "id"),
        provider_event_id=first_string(raw, "provider_event_id", "event_id", "id"),
        provider_artist_id=clean_string(values.get("provider_artist_id")),
        provider_venue_id=clean_string(values.get("provider_venue_id")),
        source_url=clean_string(values.get("source_url")),
        source_record_id=clean_string(values.get("source_record_id")),
        dedupe_key=key,
        dedupe_confidence=0.86 if values.get("source_record_id") else 0.68,
        venue_match_confidence=0.78 if values.get("venue_name") else 0.0,
        event_relevance_score=(
            ticketmaster_mapping.event_relevance_score
            if ticketmaster_mapping
            else event_relevance_score(raw)
        ),
        photo_quality_score=80.0 if image and is_direct_image_url(image) else 35.0,
        field_completeness_score=completeness_score(values),
    )


def finalize_provider_candidate(
    raw: dict[str, Any],
    provider_key: str,
    values: dict[str, Any],
    ticket_assessment: TicketLinkAssessment,
    provider_record_id: str | None,
    provider_event_id: str | None,
    provider_artist_id: str | None,
    provider_venue_id: str | None,
    relevance_score: float,
    extra_warnings: list[str] | None = None,
    extra_quality_flags: list[str] | None = None,
) -> NormalizedApiCandidate:
    warnings = list(extra_warnings or [])
    quality_flags = list(extra_quality_flags or [])
    for field_name in ["event_name", "headliner", "start_datetime", "venue_name"]:
        if not values.get(field_name):
            warnings.append(f"missing_{field_name}")
            quality_flags.append(f"missing {field_name.replace('_', ' ')}")
    if not values.get("tickets_link"):
        quality_flags.append("missing ticket link")
    if ticket_assessment.category not in {"blank", "direct"}:
        quality_flags.append(f"ticket link: {ticket_assessment.category}")
    quality_flags.extend(ticket_assessment.flags)

    image = clean_string(values.get("main_image_url"))
    if not image:
        quality_flags.append("missing image")
    elif is_social_url(image):
        quality_flags.append("social image URL")
    elif not is_direct_image_url(image):
        quality_flags.append("non-direct image URL")

    if not values.get("venue_address") and not (
        values.get("latitude") and values.get("longitude")
    ):
        quality_flags.append("missing venue location")

    normalized_status = "normalized"
    if warnings:
        normalized_status = "partial"
    if not values.get("event_name") or not values.get("start_datetime"):
        normalized_status = "failed"

    key = dedupe_key_for_candidate(provider_key, values)
    return NormalizedApiCandidate(
        normalized_payload=values,
        mapping_warnings=sorted(set(warnings)),
        quality_flags=sorted(set(quality_flags)),
        normalization_status=normalized_status,
        provider_record_id=provider_record_id,
        provider_event_id=provider_event_id,
        provider_artist_id=provider_artist_id,
        provider_venue_id=provider_venue_id,
        source_url=clean_string(values.get("source_url")),
        source_record_id=clean_string(values.get("source_record_id")),
        dedupe_key=key,
        dedupe_confidence=0.96 if values.get("source_record_id") else 0.7,
        venue_match_confidence=0.86 if provider_venue_id else 0.78
        if values.get("venue_name")
        else 0.0,
        event_relevance_score=relevance_score,
        photo_quality_score=80.0 if image and is_direct_image_url(image) else 35.0,
        field_completeness_score=completeness_score(values),
    )


def manual_json_mapper(raw: dict[str, Any]) -> NormalizedApiCandidate:
    return generic_event_mapper(raw, "manual_json")


def spotify_link_from_provider_values(*values: object) -> str | None:
    for value in values:
        for link in string_list(value):
            if "spotify.com" in link.lower():
                return link
        for item in dict_list(value):
            item_link = provider_first_string(item, "url", "identifier", "sameAs")
            if item_link and "spotify.com" in item_link.lower():
                return item_link
    return None


def jambase_performer_fields(
    performers: list[dict[str, Any]],
) -> tuple[str | None, str | None, str | None, str | None, str | None]:
    names: list[str] = []
    supporting: list[str] = []
    genres: list[str] = []
    headliner: str | None = None
    headliner_id: str | None = None
    spotify_url: str | None = None
    for performer in performers:
        name = provider_first_string(performer, "name")
        if name:
            names.append(name)
        genres.extend(string_list(performer.get("genre")))
        spotify_url = spotify_url or spotify_link_from_provider_values(
            performer.get("sameAs"),
            performer.get("x-externalIdentifiers"),
        )
        is_headliner = bool_value(performer.get("x-isHeadliner")) is True
        if is_headliner and name and not headliner:
            headliner = name
            headliner_id = provider_first_string(performer, "identifier")
    if not headliner and names:
        headliner = names[0]
        headliner_id = provider_first_string(performers[0], "identifier")
    for name in names:
        if name != headliner:
            supporting.append(name)
    genre = genres[0] if genres else None
    return (
        headliner,
        ", ".join(supporting) if supporting else None,
        genre,
        headliner_id,
        spotify_url,
    )


def jambase_ticket_assessment(offers: list[dict[str, Any]]) -> TicketLinkAssessment:
    candidates: list[TicketLinkCandidate] = []
    for index, offer in enumerate(offers):
        category = (provider_first_string(offer, "category") or "").strip()
        url = provider_first_string(offer, "url")
        priority = 10 + index
        if category == "ticketingLinkPrimary":
            priority = index
        elif category == "ticketingLinkSecondary":
            priority = 100 + index
        candidates.append(
            TicketLinkCandidate(
                url=url,
                source=category or "offer",
                priority=priority,
            )
        )
    return choose_ticket_link(candidates)


def jambase_price_text(offers: list[dict[str, Any]]) -> str | None:
    for offer in offers:
        price = price_text_from_value(offer.get("priceSpecification"))
        if price:
            return price
    return None


def jambase_mapper(raw: dict[str, Any]) -> NormalizedApiCandidate:
    event = dict_or_empty(raw.get("event")) or raw
    location = dict_or_empty(event.get("location"))
    address = dict_or_empty(location.get("address"))
    region = dict_or_empty(address.get("addressRegion"))
    country = dict_or_empty(address.get("addressCountry"))
    geo = dict_or_empty(location.get("geo"))
    performers = dict_list(event.get("performer"))
    offers = dict_list(event.get("offers"))
    (
        headliner,
        supporting_artists,
        provider_genre,
        provider_artist_id,
        performer_spotify_url,
    ) = jambase_performer_fields(performers)
    event_type = provider_first_string(event, "@type", "type")
    source_record_id = provider_first_string(event, "identifier")
    ticket_assessment = jambase_ticket_assessment(offers)
    ticket_offers = ticket_offer_entries(offers)
    external_identifiers: list[dict[str, str]] = []
    external_identifiers.extend(
        provider_identifier_entry("event", "jambase", source_record_id)
    )
    external_identifiers.extend(
        identifier_entries_from_value(event.get("x-externalIdentifiers"), "event")
    )
    for performer in performers:
        external_identifiers.extend(
            provider_identifier_entry(
                "artist",
                "jambase",
                provider_first_string(performer, "identifier"),
            )
        )
        external_identifiers.extend(
            identifier_entries_from_value(
                performer.get("x-externalIdentifiers"),
                "artist",
            )
        )
    external_identifiers.extend(
        provider_identifier_entry(
            "venue",
            "jambase",
            provider_first_string(location, "identifier"),
        )
    )
    external_identifiers.extend(
        identifier_entries_from_value(location.get("x-externalIdentifiers"), "venue")
    )
    upstream_event_source, upstream_event_id = first_external_identifier(
        [
            entry
            for entry in external_identifiers
            if entry.get("source") != "jambase"
        ],
        "event",
    )
    upstream_artist_source, upstream_artist_id = first_external_identifier(
        [
            entry
            for entry in external_identifiers
            if entry.get("source") != "jambase"
        ],
        "artist",
    )
    upstream_venue_source, upstream_venue_id = first_external_identifier(
        [
            entry
            for entry in external_identifiers
            if entry.get("source") != "jambase"
        ],
        "venue",
    )
    event_status = provider_first_string(event, "eventStatus")
    start_raw = provider_first_string(event, "startDate")
    end_raw = provider_first_string(event, "endDate")
    previous_start_raw = provider_first_string(event, "previousStartDate")
    image = first_image_url(event.get("image"), event.get("x-promoImage"))
    venue_image = first_image_url(location.get("image"))
    venue_source_url = provider_first_string(location, "url")
    values: dict[str, Any] = {
        "category": "Concert",
        "record_type": "event",
        "provider_event_type": event_type,
        "provider_music_segment": "Music",
        "event_name": provider_first_string(event, "name", "x-customTitle"),
        "description": combined_text(
            provider_first_string(event, "description"),
            provider_first_string(event, "x-subtitle"),
        ),
        "headliner": headliner,
        "supporting_artists": supporting_artists,
        "provider_genre": provider_genre,
        "provider_subgenre": None,
        "music_category": "Music",
        "normalized_genre": provider_genre,
        "event_status": event_status,
        "event_lifecycle_status": event_status,
        "start_datetime": start_raw,
        "end_datetime": end_raw,
        "previous_start_datetime": previous_start_raw,
        "timezone": provider_first_string(address, "x-timezone"),
        "doors_time": provider_first_string(event, "doorTime"),
        "attendance_mode": provider_first_string(event, "eventAttendanceMode"),
        "is_free": bool_value(event.get("isAccessibleForFree")),
        "deletion_status": provider_first_string(event, "deletionStatus"),
        "deleted_at": provider_first_string(event, "deletedAt"),
        "provider_merged_into": provider_first_string(event, "mergedInto"),
        "related_stream_ids": string_list(event.get("x-streamIds")),
        "lineup_display_option": provider_first_string(
            event,
            "x-lineupDisplayOption",
        ),
        "venue_name": provider_first_string(location, "name"),
        "venue_address": provider_first_string(address, "streetAddress"),
        "venue_address_2": provider_first_string(address, "x-streetAddress2"),
        "city": provider_first_string(address, "addressLocality"),
        "state": provider_first_string(region, "alternateName", "identifier", "name"),
        "zip_code": provider_first_string(address, "postalCode"),
        "country": provider_first_string(
            country,
            "identifier",
            "alternateName",
            "name",
        ),
        "country_iso3": provider_first_string(country, "alternateName"),
        "latitude": first_float(geo, "latitude", "lat"),
        "longitude": first_float(geo, "longitude", "lng", "lon"),
        "event_url": provider_first_string(event, "url"),
        "tickets_link": ticket_assessment.recommended_url,
        "ticket_link_classification": ticket_assessment.category,
        "ticket_link_repair_suggestion": ticket_assessment.repair_suggestion,
        "recommended_ticket_link": ticket_assessment.recommended_url,
        "ticket_link_quality_score": ticket_assessment.quality_score,
        "ticketing_provider": first_ticket_offer_value(
            ticket_offers,
            "detected_provider",
        ),
        "ticketing_provider_domain": first_ticket_offer_value(
            ticket_offers,
            "provider_domain",
        ),
        "price": jambase_price_text(offers),
        "main_image_url": image,
        "spotify_url": spotify_link_from_provider_values(
            event.get("sameAs"),
            performer_spotify_url,
        ),
        "source_url": provider_first_string(event, "url"),
        "source_record_id": source_record_id,
        "provider_event_id": source_record_id,
        "upstream_event_source": upstream_event_source,
        "upstream_event_id": upstream_event_id,
        "upstream_artist_source": upstream_artist_source,
        "upstream_artist_id": upstream_artist_id,
        "upstream_venue_source": upstream_venue_source,
        "upstream_venue_id": upstream_venue_id,
        "provider_artist_id": provider_artist_id,
        "provider_venue_id": provider_first_string(location, "identifier"),
        "venue_source_url": venue_source_url,
        "venue_image_url": venue_image,
        "venue_links": string_list(location.get("sameAs")),
        "venue_closed": bool_value(location.get("x-isPermanentlyClosed")),
        "venue_upcoming_count": provider_first_string(location, "x-numUpcomingEvents"),
        "performer_lineup_metadata": [
            {
                "identifier": provider_first_string(performer, "identifier"),
                "name": provider_first_string(performer, "name"),
                "performance_rank": provider_first_string(
                    performer,
                    "x-performanceRank",
                ),
                "performance_date": provider_first_string(
                    performer,
                    "x-performanceDate",
                ),
                "date_is_confirmed": bool_value(
                    performer.get("x-dateIsConfirmed")
                ),
                "artist_type": provider_first_string(
                    performer,
                    "x-bandOrMusician",
                ),
                "image_url": first_image_url(performer.get("image")),
                "genres": string_list(performer.get("genre")),
                "same_as": string_list(performer.get("sameAs")),
                "external_identifiers": dict_list(
                    performer.get("x-externalIdentifiers")
                ),
                "spotify_url": spotify_link_from_provider_values(
                    performer.get("sameAs"),
                    performer.get("x-externalIdentifiers"),
                ),
            }
            for performer in performers
        ],
    }
    apply_provenance_values(
        values,
        "jambase",
        ticket_assessment,
        external_identifiers,
        ticket_offers,
    )
    values.update(
        {
            "dedupe_source_fields": {
                "provider": "jambase",
                "ingestion_provider": values.get("ingestion_provider"),
                "identifier": source_record_id,
                "provider_event_id": source_record_id,
                "upstream_event_source": values.get("upstream_event_source"),
                "upstream_event_id": values.get("upstream_event_id"),
                "event_data_source": values.get("upstream_event_source")
                or "jambase",
                "venue_data_source": values.get("upstream_venue_source")
                or "jambase",
                "artist_data_source": values.get("upstream_artist_source")
                or "jambase",
                "ticketing_provider": values.get("ticketing_provider"),
                "normalized_ticket_url": values.get("recommended_ticket_link"),
                "source_chain": values.get("source_chain"),
                "provider_event_type": event_type,
                "event_name": provider_first_string(event, "name", "x-customTitle"),
                "start_datetime": start_raw,
                "previous_start_datetime": previous_start_raw,
                "event_lifecycle_status": event_status,
                "venue_identifier": provider_first_string(location, "identifier"),
            },
            "venue_match_fields": {
                "provider_venue_id": provider_first_string(location, "identifier"),
                "upstream_venue_source": values.get("upstream_venue_source"),
                "upstream_venue_id": values.get("upstream_venue_id"),
                "venue_name": provider_first_string(location, "name"),
                "venue_source_url": venue_source_url,
                "venue_image_url": venue_image,
                "venue_address": provider_first_string(address, "streetAddress"),
                "venue_address_2": provider_first_string(address, "x-streetAddress2"),
                "city": provider_first_string(address, "addressLocality"),
                "state": provider_first_string(
                    region,
                    "alternateName",
                    "identifier",
                    "name",
                ),
                "latitude": first_float(geo, "latitude", "lat"),
                "longitude": first_float(geo, "longitude", "lng", "lon"),
            },
            "provider_doc_notes": (
                "JamBase API v3.1.0 mapper follows the local OpenAPI/Postman docs. "
                "Concert and Festival records remain category Concert events with "
                "provider_event_type preserved. startDate, endDate, previousStartDate, "
                "and doorTime are venue-local values; use location.address.x-timezone "
                "for conversion when needed."
            ),
        }
    )
    return finalize_provider_candidate(
        event,
        "jambase",
        values,
        ticket_assessment,
        provider_record_id=source_record_id,
        provider_event_id=source_record_id,
        provider_artist_id=provider_artist_id,
        provider_venue_id=provider_first_string(location, "identifier"),
        relevance_score=96.0,
    )


def cityspark_ticket_assessment(raw: dict[str, Any]) -> TicketLinkAssessment:
    candidates = [
        TicketLinkCandidate(
            url=provider_first_string(raw, "ticketUrl"),
            source="ticketUrl",
            priority=0,
        )
    ]
    for index, link in enumerate(dict_list(raw.get("links"))):
        candidates.append(
            TicketLinkCandidate(
                url=provider_first_string(link, "linkUrl", "url"),
                source=provider_first_string(link, "linkType", "label", "title")
                or "supporting_link",
                priority=50 + index,
            )
        )
    return choose_ticket_link(candidates)


def cityspark_mapper(raw: dict[str, Any]) -> NormalizedApiCandidate:
    event = dict_or_empty(raw.get("event")) or raw
    location = dict_or_empty(event.get("location"))
    primary_image = dict_or_empty(event.get("primaryImage"))
    instances = dict_list(event.get("instances"))
    first_instance = instances[0] if instances else {}
    source_record_id = provider_first_string(event, "eventId", "id")
    ticket_assessment = cityspark_ticket_assessment(event)
    ticket_offer_inputs = [
        {"category": "ticketUrl", "url": provider_first_string(event, "ticketUrl")}
    ]
    for link in dict_list(event.get("links")):
        ticket_offer_inputs.append(
            {
                "category": provider_first_string(link, "linkType", "label", "title"),
                "url": provider_first_string(link, "linkUrl", "url"),
            }
        )
    ticket_offers = ticket_offer_entries(ticket_offer_inputs)
    external_identifiers = provider_identifier_entry(
        "event",
        CITYSPARK_PROVIDER_KEY,
        source_record_id,
    )
    external_identifiers.extend(
        identifier_entries_from_value(
            event.get("externalIdentifiers") or event.get("sourceIdentifiers"),
            "event",
        )
    )
    upstream_event_source = detect_source_key(
        provider_first_string(event, "source", "dataSource", "eventSource")
    ) or provider_first_string(event, "source", "dataSource", "eventSource")
    upstream_event_id = provider_first_string(
        event,
        "sourceEventId",
        "upstreamEventId",
        "externalEventId",
    )
    start_raw = provider_first_string(first_instance, "start") or provider_first_string(
        event,
        "start",
    )
    end_raw = provider_first_string(first_instance, "end") or provider_first_string(
        event,
        "end",
    )
    start = parse_datetime_value(start_raw)
    end = parse_datetime_value(end_raw)
    labels = string_list(event.get("labels"))
    categories = labels_from_objects(event.get("categories"))
    provider_genre = categories[0] if categories else None
    image = first_image_url(primary_image)
    values: dict[str, Any] = {
        "category": "Concert",
        "record_type": "event",
        "provider_event_type": "EventSeries",
        "event_name": provider_first_string(event, "name"),
        "description": combined_text(
            provider_first_string(event, "description"),
            provider_first_string(event, "summary"),
        ),
        "headliner": provider_first_string(event, "name"),
        "supporting_artists": None,
        "provider_genre": provider_genre,
        "provider_subgenre": None,
        "music_category": "Music" if provider_genre else None,
        "normalized_genre": provider_genre,
        "start_datetime": start.isoformat() if start else None,
        "end_datetime": end.isoformat() if end else None,
        "has_time": bool_value(event.get("hasTime")),
        "all_day": bool_value(event.get("allDay")),
        "venue_name": provider_first_string(location, "locationName"),
        "venue_address": provider_first_string(location, "address"),
        "city": provider_first_string(location, "city"),
        "state": provider_first_string(location, "state"),
        "country": provider_first_string(location, "country"),
        "latitude": first_float(location, "latitude"),
        "longitude": first_float(location, "longitude"),
        "event_url": provider_first_string(event, "url"),
        "tickets_link": ticket_assessment.recommended_url,
        "ticket_link_classification": ticket_assessment.category,
        "ticket_link_repair_suggestion": ticket_assessment.repair_suggestion,
        "recommended_ticket_link": ticket_assessment.recommended_url,
        "ticket_link_quality_score": ticket_assessment.quality_score,
        "price": price_text_from_value(event.get("price")),
        "main_image_url": image,
        "source_url": provider_first_string(event, "url"),
        "source_record_id": source_record_id,
        "provider_event_id": source_record_id,
        "upstream_event_source": upstream_event_source,
        "upstream_event_id": upstream_event_id,
        "ticketing_provider": first_ticket_offer_value(
            ticket_offers,
            "detected_provider",
        ),
        "ticketing_provider_domain": first_ticket_offer_value(
            ticket_offers,
            "provider_domain",
        ),
        "labels": labels,
        "provider_categories": categories,
        "supporting_links": dict_list(event.get("links")),
        "contact": dict_or_empty(event.get("contact")),
    }
    apply_provenance_values(
        values,
        CITYSPARK_PROVIDER_KEY,
        ticket_assessment,
        external_identifiers,
        ticket_offers,
    )
    values.update(
        {
            "dedupe_source_fields": {
                "provider": CITYSPARK_PROVIDER_KEY,
                "ingestion_provider": values.get("ingestion_provider"),
                "eventId": source_record_id,
                "provider_event_id": source_record_id,
                "upstream_event_source": values.get("upstream_event_source"),
                "upstream_event_id": values.get("upstream_event_id"),
                "ticketing_provider": values.get("ticketing_provider"),
                "normalized_ticket_url": values.get("recommended_ticket_link"),
                "source_chain": values.get("source_chain"),
                "event_name": provider_first_string(event, "name"),
                "start_datetime": start.isoformat() if start else None,
                "venue_name": provider_first_string(location, "locationName"),
            },
            "venue_match_fields": {
                "venue_name": provider_first_string(location, "locationName"),
                "venue_address": provider_first_string(location, "address"),
                "city": provider_first_string(location, "city"),
                "state": provider_first_string(location, "state"),
                "latitude": first_float(location, "latitude"),
                "longitude": first_float(location, "longitude"),
            },
            "provider_doc_notes": (
                "CitySpark paid licensed vendor API EventSeries mapper. Records "
                "still pass through API Feed Review, normalization, dedupe, source "
                "claims, ticket QA, image QA, and app-feed readiness before use."
            ),
        }
    )
    extra_flags: list[str] = []
    if not provider_first_string(event, "ticketUrl") and ticket_assessment.usable:
        extra_flags.append("ticket candidate came from supporting link")
    elif not provider_first_string(event, "ticketUrl"):
        extra_flags.append("ticketUrl missing")
    return finalize_provider_candidate(
        event,
        CITYSPARK_PROVIDER_KEY,
        values,
        ticket_assessment,
        provider_record_id=source_record_id,
        provider_event_id=source_record_id,
        provider_artist_id=None,
        provider_venue_id=None,
        relevance_score=event_relevance_score(event),
        extra_quality_flags=extra_flags,
    )


def map_record(provider_key: str, raw: dict[str, Any]) -> NormalizedApiCandidate:
    if provider_key == "manual_json":
        return manual_json_mapper(raw)
    if provider_key == "jambase":
        return jambase_mapper(raw)
    if provider_key == CITYSPARK_PROVIDER_KEY:
        return cityspark_mapper(raw)
    return generic_event_mapper(raw, provider_key)


def demo_records_for_provider(provider_key: str) -> list[dict[str, Any]]:
    if provider_key == "jambase":
        return [
            {
                "@type": "Concert",
                "identifier": "jambase:demo-100",
                "name": "Demo Roots Concert",
                "startDate": "2026-08-14T20:00:00-05:00",
                "location": {
                    "identifier": "jambase:venue-1",
                    "name": "Demo River Hall",
                    "geo": {"latitude": 35.1495, "longitude": -90.049},
                    "address": {
                        "streetAddress": "100 Music Ave",
                        "addressLocality": "Memphis",
                        "addressRegion": {"alternateName": "TN"},
                        "postalCode": "38103",
                        "addressCountry": {"identifier": "US"},
                        "x-timezone": "America/Chicago",
                    },
                },
                "performer": [
                    {
                        "identifier": "jambase:artist-1",
                        "name": "The Demo Travelers",
                        "genre": ["Roots"],
                        "x-isHeadliner": True,
                    }
                ],
                "offers": [
                    {
                        "category": "ticketingLinkPrimary",
                        "url": "https://tickets.example/demo-roots",
                    }
                ],
                "image": "https://images.example/demo-roots.jpg",
                "url": "https://events.example/demo-roots",
            },
            {
                "@type": "Concert",
                "identifier": "jambase:demo-101",
                "name": "Demo Late Set",
                "startDate": "2026-08-15T22:00:00-05:00",
                "location": {
                    "identifier": "jambase:venue-1",
                    "name": "Demo River Hall",
                    "address": {
                        "addressLocality": "Memphis",
                        "addressRegion": {"alternateName": "TN"},
                        "addressCountry": {"identifier": "US"},
                        "x-timezone": "America/Chicago",
                    },
                },
                "performer": [
                    {
                        "identifier": "jambase:artist-2",
                        "name": "Night Signal",
                        "genre": ["Soul"],
                        "x-isHeadliner": True,
                    }
                ],
                "offers": [
                    {
                        "category": "ticketingLinkPrimary",
                        "url": "https://tickets.example/demo-late?utm_source=demo",
                    }
                ],
            },
        ]
    if provider_key == CITYSPARK_PROVIDER_KEY:
        return [
            {
                "eventId": "cs-demo-200",
                "name": "Licensed Vendor Demo Concert",
                "description": "Synthetic CitySpark-style event for local review.",
                "location": {
                    "locationName": "Licensed Review Hall",
                    "address": "200 Licensed Ave",
                    "city": "Memphis",
                    "state": "TN",
                    "country": "US",
                },
                "instances": [
                    {
                        "start": "2026-09-01T19:30:00-05:00",
                        "end": "2026-09-01T22:00:00-05:00",
                    }
                ],
                "ticketUrl": "https://tickets.example/licensed-review",
                "primaryImage": {
                    "largeImageUrl": "https://images.example/licensed-review.jpg"
                },
                "url": "https://vendor-review.example/licensed-review",
            }
        ]
    return [
        {
            "id": "manual-demo-1",
            "event_name": "Manual Demo Concert",
            "headliner": "The Local Fixtures",
            "start_datetime": "2026-07-20T20:00:00-05:00",
            "venue_name": "Fixture Music Hall",
            "venue_address": "11 Test Street",
            "city": "Memphis",
            "state": "TN",
            "zip_code": "38103",
            "country": "US",
            "event_url": "https://events.example/manual-demo",
            "tickets_link": "https://tickets.example/manual-demo",
            "main_image_url": "https://images.example/manual-demo.jpg",
        },
        {
            "id": "manual-demo-2",
            "event_name": "Messy Demo Concert",
            "headliner": "Missing Image Trio",
            "start_datetime": "2026-07-21T20:00:00-05:00",
            "venue_name": "Fixture Music Hall",
            "city": "Memphis",
            "state": "TN",
            "tickets_link": "https://tickets.example/messy-demo?fbclid=demo",
        },
    ]


def extract_json_records(payload: object) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        event_value = payload.get("event")
        if isinstance(event_value, dict):
            return [event_value]
        for key in ["events", "data", "results"]:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload]
    return []


def load_json_records(content: bytes) -> list[dict[str, Any]]:
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Upload must be a valid JSON file.") from exc
    records = extract_json_records(payload)
    if not records:
        raise ValueError("JSON file did not contain event records.")
    return records


def compliance_expiration_for(provider: ProviderConfig) -> datetime | None:
    if provider.storage_policy != "temporary_review_only" or provider.ttl_hours is None:
        return None
    return utc_now() + timedelta(hours=provider.ttl_hours)


def create_api_feed_run(
    session: Session,
    settings: Settings,
    provider_key: str,
    records: list[dict[str, Any]],
    run_mode: str,
    requested_by: str | None,
    request_preview: dict[str, Any] | None = None,
    parameters: dict[str, Any] | None = None,
    notes: str | None = None,
) -> ApiFeedRun:
    provider = get_provider_config(settings, provider_key)
    if provider is None:
        raise ValueError("Unknown API feed provider.")
    if provider.provider_type == "enrichment":
        raise ValueError("Enrichment providers are not primary event feeds.")

    expires_at = compliance_expiration_for(provider)
    run = ApiFeedRun(
        provider_key=provider.provider_key,
        provider_type=provider.provider_type,
        run_mode=run_mode,
        status="pending",
        requested_by=requested_by,
        raw_record_count=len(records),
        compliance_expiration_at=expires_at,
        request_preview_json=provider_json(request_preview or {}),
        parameters_json=provider_json(parameters or {}),
        notes=notes or provider.compliance_notes,
    )
    session.add(run)
    session.flush()

    seen_dedupe_keys: set[str] = set()
    duplicate_count = 0
    normalized_count = 0
    for raw in records:
        candidate = map_record(provider.provider_key, raw)
        duplicate_status = "new"
        if candidate.dedupe_key in seen_dedupe_keys:
            duplicate_status = "duplicate_within_run"
        elif session.scalars(
            select(Event).where(Event.dedupe_key == candidate.dedupe_key)
        ).first():
            duplicate_status = "possible_existing_event"
        if duplicate_status != "new":
            duplicate_count += 1
        seen_dedupe_keys.add(candidate.dedupe_key)
        if candidate.normalization_status != "failed":
            normalized_count += 1
        values = candidate.normalized_payload
        record = ApiFeedRecord(
            api_feed_run_id=run.id,
            provider_key=provider.provider_key,
            provider_type=provider.provider_type,
            provider_record_id=candidate.provider_record_id,
            provider_event_id=candidate.provider_event_id,
            provider_artist_id=candidate.provider_artist_id,
            provider_venue_id=candidate.provider_venue_id,
            raw_payload_json=provider_json(raw),
            normalized_payload_json=provider_json(values),
            normalization_status=candidate.normalization_status,
            review_status="pending_review",
            category="Concert",
            record_type="event",
            event_name=clean_string(values.get("event_name")),
            description=clean_string(values.get("description")),
            headliner=clean_string(values.get("headliner")),
            supporting_artists=clean_string(values.get("supporting_artists")),
            provider_event_type=clean_string(values.get("provider_event_type")),
            provider_genre=clean_string(values.get("provider_genre")),
            provider_subgenre=clean_string(values.get("provider_subgenre")),
            music_category=clean_string(values.get("music_category")),
            normalized_genre=clean_string(values.get("normalized_genre")),
            event_status=clean_string(values.get("event_status")),
            ingestion_provider=clean_string(values.get("ingestion_provider")),
            upstream_event_source=clean_string(values.get("upstream_event_source")),
            upstream_event_id=clean_string(values.get("upstream_event_id")),
            upstream_artist_source=clean_string(values.get("upstream_artist_source")),
            upstream_artist_id=clean_string(values.get("upstream_artist_id")),
            upstream_venue_source=clean_string(values.get("upstream_venue_source")),
            upstream_venue_id=clean_string(values.get("upstream_venue_id")),
            provider_music_segment=clean_string(values.get("provider_music_segment")),
            start_datetime=parse_datetime_value(
                clean_string(values.get("start_datetime"))
            ),
            end_datetime=parse_datetime_value(clean_string(values.get("end_datetime"))),
            timezone=clean_string(values.get("timezone")),
            doors_time=clean_string(values.get("doors_time")),
            has_time=(
                values.get("has_time")
                if isinstance(values.get("has_time"), bool)
                else None
            ),
            all_day=(
                values.get("all_day")
                if isinstance(values.get("all_day"), bool)
                else None
            ),
            venue_name=clean_string(values.get("venue_name")),
            venue_address=clean_string(values.get("venue_address")),
            city=clean_string(values.get("city")),
            state=clean_string(values.get("state")),
            zip_code=clean_string(values.get("zip_code")),
            country=clean_string(values.get("country")),
            latitude=value_float(values.get("latitude")),
            longitude=value_float(values.get("longitude")),
            event_url=clean_string(values.get("event_url")),
            tickets_link=clean_string(values.get("tickets_link")),
            ticket_link_classification=clean_string(
                values.get("ticket_link_classification")
            ),
            ticketing_provider=clean_string(values.get("ticketing_provider")),
            ticketing_provider_domain=clean_string(
                values.get("ticketing_provider_domain")
            ),
            ticket_link_repair_strategy=clean_string(
                values.get("ticket_link_repair_strategy")
            ),
            ticket_link_repair_source=clean_string(
                values.get("ticket_link_repair_source")
            ),
            ticket_link_repair_suggestion=clean_string(
                values.get("ticket_link_repair_suggestion")
            ),
            recommended_ticket_link=clean_string(values.get("recommended_ticket_link")),
            ticket_link_quality_score=value_float(
                values.get("ticket_link_quality_score")
            ),
            price=clean_string(values.get("price")),
            age_restriction=clean_string(values.get("age_restriction")),
            main_image_url=clean_string(values.get("main_image_url")),
            additional_image_urls=clean_string(values.get("additional_image_urls")),
            spotify_url=clean_string(values.get("spotify_url")),
            source_url=candidate.source_url,
            source_record_id=candidate.source_record_id,
            dedupe_key=candidate.dedupe_key,
            dedupe_confidence=candidate.dedupe_confidence,
            duplicate_status=duplicate_status,
            venue_match_confidence=candidate.venue_match_confidence,
            event_relevance_score=candidate.event_relevance_score,
            photo_quality_score=candidate.photo_quality_score,
            field_completeness_score=candidate.field_completeness_score,
            quality_flags_json=json.dumps(candidate.quality_flags, ensure_ascii=True),
            mapping_warnings_json=json.dumps(
                candidate.mapping_warnings,
                ensure_ascii=True,
            ),
            dedupe_source_fields_json=provider_json(
                values.get("dedupe_source_fields") or {}
            ),
            venue_match_fields_json=provider_json(
                values.get("venue_match_fields") or {}
            ),
            provider_doc_notes=clean_string(values.get("provider_doc_notes")),
            source_chain_json=provider_json(values.get("source_chain") or []),
            external_identifiers_json=provider_json(
                values.get("external_identifiers") or []
            ),
            ticket_offers_json=provider_json(values.get("ticket_offers") or []),
            provenance_flags_json=provider_json(values.get("provenance_flags") or []),
            compliance_expires_at=expires_at,
        )
        session.add(record)

    run.status = "success"
    run.completed_at = utc_now()
    run.normalized_candidate_count = normalized_count
    run.duplicate_candidate_count = duplicate_count
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def create_failed_api_feed_run(
    session: Session,
    settings: Settings,
    provider_key: str,
    run_mode: str,
    requested_by: str | None,
    error_message: str,
    request_preview: dict[str, Any] | None = None,
    parameters: dict[str, Any] | None = None,
    notes: str | None = None,
) -> ApiFeedRun:
    provider = get_provider_config(settings, provider_key)
    if provider is None:
        raise ValueError("Unknown API feed provider.")
    if provider.provider_type == "enrichment":
        raise ValueError("Enrichment providers are not primary event feeds.")

    expires_at = compliance_expiration_for(provider)
    run = ApiFeedRun(
        provider_key=provider.provider_key,
        provider_type=provider.provider_type,
        run_mode=run_mode,
        status="failure",
        requested_by=requested_by,
        raw_record_count=0,
        normalized_candidate_count=0,
        error_message=clean_string(error_message),
        compliance_expiration_at=expires_at,
        request_preview_json=provider_json(request_preview or {}),
        parameters_json=provider_json(parameters or {}),
        notes=notes or provider.compliance_notes,
        completed_at=utc_now(),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def run_demo_import(
    session: Session,
    settings: Settings,
    provider_key: str,
    requested_by: str | None,
) -> ApiFeedRun:
    return create_api_feed_run(
        session,
        settings,
        provider_key,
        demo_records_for_provider(provider_key),
        run_mode="demo_fixture",
        requested_by=requested_by,
    )


def run_manual_json_import(
    session: Session,
    settings: Settings,
    provider_key: str,
    content: bytes,
    requested_by: str | None,
) -> ApiFeedRun:
    return create_api_feed_run(
        session,
        settings,
        provider_key,
        load_json_records(content),
        run_mode="manual_json_upload",
        requested_by=requested_by,
    )


def list_api_feed_runs(
    session: Session,
    provider_key: str | None = None,
) -> list[ApiFeedRun]:
    statement = (
        select(ApiFeedRun)
        .options(selectinload(ApiFeedRun.records))
        .order_by(ApiFeedRun.started_at.desc(), ApiFeedRun.id.desc())
    )
    if provider_key:
        statement = statement.where(ApiFeedRun.provider_key == provider_key)
    return list(session.scalars(statement).all())


def get_api_feed_run(session: Session, run_id: int) -> ApiFeedRun | None:
    return session.scalars(
        select(ApiFeedRun)
        .options(selectinload(ApiFeedRun.records))
        .where(ApiFeedRun.id == run_id)
    ).first()


def get_api_feed_record(session: Session, record_id: int) -> ApiFeedRecord | None:
    return session.scalars(
        select(ApiFeedRecord)
        .options(selectinload(ApiFeedRecord.run))
        .where(ApiFeedRecord.id == record_id)
    ).first()


def list_api_feed_records(
    session: Session,
    filters: ApiFeedRecordFilters | None = None,
    run_id: int | None = None,
) -> list[ApiFeedRecord]:
    filters = filters or ApiFeedRecordFilters()
    statement = (
        select(ApiFeedRecord)
        .options(selectinload(ApiFeedRecord.run))
        .order_by(ApiFeedRecord.created_at.desc(), ApiFeedRecord.id.desc())
    )
    if run_id is not None:
        statement = statement.where(ApiFeedRecord.api_feed_run_id == run_id)
    if filters.provider_key:
        statement = statement.where(ApiFeedRecord.provider_key == filters.provider_key)
    if filters.ingestion_provider:
        statement = statement.where(
            ApiFeedRecord.ingestion_provider == filters.ingestion_provider
        )
    if filters.upstream_event_source:
        statement = statement.where(
            ApiFeedRecord.upstream_event_source == filters.upstream_event_source
        )
    if filters.ticketing_provider:
        statement = statement.where(
            ApiFeedRecord.ticketing_provider == filters.ticketing_provider
        )
    if filters.ticket_link_classification:
        statement = statement.where(
            ApiFeedRecord.ticket_link_classification
            == filters.ticket_link_classification
        )
    if filters.ticket_link_repair_strategy:
        statement = statement.where(
            ApiFeedRecord.ticket_link_repair_strategy
            == filters.ticket_link_repair_strategy
        )
    if filters.review_status:
        statement = statement.where(
            ApiFeedRecord.review_status == filters.review_status
        )
    if filters.normalization_status:
        statement = statement.where(
            ApiFeedRecord.normalization_status == filters.normalization_status
        )
    if filters.duplicate_status:
        statement = statement.where(
            ApiFeedRecord.duplicate_status == filters.duplicate_status
        )
    records = list(session.scalars(statement).all())
    if filters.quality_issue:
        records = [
            record
            for record in records
            if filters.quality_issue in record.quality_flags
        ]
    if filters.provenance_flag:
        records = [
            record
            for record in records
            if filters.provenance_flag in record.provenance_flags
        ]
    if filters.missing_image:
        records = [
            record for record in records if "missing image" in record.quality_flags
        ]
    if filters.missing_ticket_link:
        records = [
            record
            for record in records
            if "missing ticket link" in record.quality_flags
        ]
    if filters.missing_venue:
        records = [
            record
            for record in records
            if any(flag.startswith("missing venue") for flag in record.quality_flags)
        ]
    if filters.compliance_expiring_soon:
        soon = utc_now() + timedelta(hours=24)
        records = [
            record
            for record in records
            if record.compliance_expires_at is not None
            and record.compliance_expires_at <= soon
        ]
    if filters.unknown_upstream_source:
        records = [
            record
            for record in records
            if record.upstream_event_source in {None, "unknown"}
            or "unknown upstream source" in record.provenance_flags
        ]
    if filters.api_backfill_required:
        records = [
            record
            for record in records
            if "api backfill required" in record.provenance_flags
            or record.ticket_link_repair_strategy == "api_backfill_required"
        ]
    if filters.min_event_relevance_score is not None:
        records = [
            record
            for record in records
            if (record.event_relevance_score or 0) >= filters.min_event_relevance_score
        ]
    if filters.min_photo_quality_score is not None:
        records = [
            record
            for record in records
            if (record.photo_quality_score or 0) >= filters.min_photo_quality_score
        ]
    return records


def refresh_run_counts(session: Session, run_id: int) -> None:
    run = session.get(ApiFeedRun, run_id)
    if run is None:
        return
    records = list(
        session.scalars(
            select(ApiFeedRecord).where(ApiFeedRecord.api_feed_run_id == run_id)
        ).all()
    )
    run.approved_count = sum(record.review_status == "approved" for record in records)
    run.held_count = sum(record.review_status == "held" for record in records)
    run.rejected_count = sum(record.review_status == "rejected" for record in records)
    run.duplicate_candidate_count = sum(
        record.duplicate_status != "new" for record in records
    )
    session.add(run)


def raw_event_payload(record: ApiFeedRecord, event_id: int | None = None) -> str:
    payload = {
        "api_feed_run_id": record.api_feed_run_id,
        "api_feed_record_id": record.id,
        "provider_key": record.provider_key,
        "provider_record_id": record.provider_record_id,
        "source_record_id": record.source_record_id,
        "provider_event_type": record.provider_event_type,
        "provider_genre": record.provider_genre,
        "provider_subgenre": record.provider_subgenre,
        "provider_music_segment": record.provider_music_segment,
        "ingestion_provider": record.ingestion_provider,
        "upstream_event_source": record.upstream_event_source,
        "upstream_event_id": record.upstream_event_id,
        "upstream_artist_source": record.upstream_artist_source,
        "upstream_artist_id": record.upstream_artist_id,
        "upstream_venue_source": record.upstream_venue_source,
        "upstream_venue_id": record.upstream_venue_id,
        "music_category": record.music_category,
        "normalized_genre": record.normalized_genre,
        "ticket_link_classification": record.ticket_link_classification,
        "ticketing_provider": record.ticketing_provider,
        "ticketing_provider_domain": record.ticketing_provider_domain,
        "ticket_link_repair_strategy": record.ticket_link_repair_strategy,
        "ticket_link_repair_source": record.ticket_link_repair_source,
        "ticket_link_repair_suggestion": record.ticket_link_repair_suggestion,
        "recommended_ticket_link": record.recommended_ticket_link,
        "source_chain": record.source_chain,
        "external_identifiers": record.external_identifiers,
        "ticket_offers": record.ticket_offers,
        "provenance_flags": record.provenance_flags,
        "dedupe_source_fields": record.dedupe_source_fields,
        "venue_match_fields": record.venue_match_fields,
        "provider_doc_notes": record.provider_doc_notes,
        "quality_flags": record.quality_flags,
        "mapping_warnings": record.mapping_warnings,
        "normalized_payload": json.loads(record.normalized_payload_json),
        "raw_payload": json.loads(record.raw_payload_json),
    }
    if event_id:
        payload["event_id"] = event_id
    return json.dumps(payload, ensure_ascii=True, sort_keys=True)


def approve_api_feed_record(
    session: Session,
    settings: Settings,
    record_id: int,
) -> ApiFeedRecord:
    record = get_api_feed_record(session, record_id)
    if record is None:
        raise ValueError("API feed record not found.")
    provider = get_provider_config(settings, record.provider_key)
    if provider is None:
        raise ValueError("Unknown API feed provider.")
    if record.normalization_status == "failed" or record.start_datetime is None:
        raise ValueError("Only normalized event candidates can be approved.")

    venue = ensure_event_venue(
        session,
        VenueInput(
            display_name=record.venue_name or "Unknown Venue",
            address=record.venue_address,
            city=record.city,
            state=record.state,
            zip_code=record.zip_code,
            country=record.country,
            latitude=record.latitude,
            longitude=record.longitude,
            website=record.event_url,
            main_image_url=record.main_image_url,
            additional_image_urls=record.additional_image_urls,
        ),
    )
    quality_scores_json = json.dumps(
        {
            "dedupe_confidence": record.dedupe_confidence,
            "venue_match_confidence": record.venue_match_confidence,
            "event_relevance_score": record.event_relevance_score,
            "photo_quality_score": record.photo_quality_score,
            "field_completeness_score": record.field_completeness_score,
            "ticket_link_quality_score": record.ticket_link_quality_score,
        },
        ensure_ascii=True,
        sort_keys=True,
    )
    raw_payload = raw_event_payload(record)
    normalized = NormalizedEventCandidate(
        event_venue_id=venue.id,
        api_feed_run_id=record.api_feed_run_id,
        api_feed_record_id=record.id,
        api_provider_key=record.provider_key,
        api_source_record_id=record.source_record_id or record.provider_record_id,
        api_mapping_warnings_json=record.mapping_warnings_json,
        api_quality_scores_json=quality_scores_json,
        category="Concert",
        record_type="event",
        source_type="api_feed",
        title=record.event_name or "Untitled Concert",
        description=record.description,
        headliner=record.headliner,
        supporting_artists=record.supporting_artists,
        provider_event_type=record.provider_event_type,
        provider_genre=record.provider_genre,
        provider_subgenre=record.provider_subgenre,
        provider_music_segment=record.provider_music_segment,
        music_category=record.music_category,
        normalized_genre=record.normalized_genre,
        genre=record.normalized_genre or record.provider_genre,
        event_status=record.event_status,
        start_datetime=record.start_datetime,
        end_datetime=record.end_datetime,
        timezone=record.timezone,
        location_text=record.venue_name or record.venue_address,
        source_url=record.event_url or record.source_url,
        tickets_link=record.tickets_link,
        ticket_link_classification=record.ticket_link_classification,
        ticketing_provider=record.ticketing_provider,
        ticketing_provider_domain=record.ticketing_provider_domain,
        ticket_link_repair_strategy=record.ticket_link_repair_strategy,
        ticket_link_repair_source=record.ticket_link_repair_source,
        ticket_link_repair_suggestion=record.ticket_link_repair_suggestion,
        recommended_ticket_link=record.recommended_ticket_link,
        ticket_link_quality_score=record.ticket_link_quality_score,
        price=record.price,
        age_restriction=record.age_restriction,
        doors_time=record.doors_time,
        has_time=record.has_time,
        all_day=record.all_day,
        main_image_url=record.main_image_url,
        additional_image_urls=record.additional_image_urls,
        spotify_url=record.spotify_url,
        source_event_id=record.source_record_id or record.provider_event_id,
        provider_doc_notes=record.provider_doc_notes,
        dedupe_source_fields_json=record.dedupe_source_fields_json,
        venue_match_fields_json=record.venue_match_fields_json,
        ingestion_provider=record.ingestion_provider,
        upstream_event_source=record.upstream_event_source,
        upstream_event_id=record.upstream_event_id,
        source_chain_json=record.source_chain_json,
        external_identifiers_json=record.external_identifiers_json,
        ticket_offers_json=record.ticket_offers_json,
        provenance_flags_json=record.provenance_flags_json,
        raw_event_json=raw_payload,
        dedupe_key=record.dedupe_key,
        dedupe_confidence=(
            "strong" if (record.dedupe_confidence or 0) >= 0.85 else "medium"
        ),
    )
    result = upsert_event_from_candidate(
        session,
        normalized,
        SourceClaimInput(
            source_type="api_feed",
            ingestion_provider=record.ingestion_provider or record.provider_key,
            upstream_event_source=record.upstream_event_source,
            upstream_event_id=record.upstream_event_id,
            provider_event_id=record.provider_event_id,
            provider_event_type=record.provider_event_type,
            provider_record_id=record.provider_record_id,
            source_record_id=record.source_record_id,
            source_url=record.event_url or record.source_url,
            source_name=provider.display_name,
            api_feed_run_id=record.api_feed_run_id,
            api_feed_record_id=record.id,
            raw_payload_json=record.raw_payload_json,
            normalized_payload_json=record.normalized_payload_json,
            field_values={
                "event_name": record.event_name,
                "start_datetime": record.start_datetime,
                "venue_name": record.venue_name,
                "provider_key": record.provider_key,
            },
            source_chain_json=record.source_chain_json,
            ticket_offers_json=record.ticket_offers_json,
            external_identifiers_json=record.external_identifiers_json,
        ),
    )
    event = result.event
    event.raw_event_json = raw_event_payload(record, event.id)
    from app.services.artist_service import link_event_to_artists
    from app.services.genre_service import normalize_event_music_fields

    normalize_event_music_fields(event)
    link_event_to_artists(session, event.id, commit=False)
    create_provider_image_candidates_for_record(
        session,
        record,
        event.id,
        commit=False,
    )
    create_poi_candidate_from_provider_location(session, record)
    run_event_photo_rescue(session, event.id, commit=False)
    record.review_status = "approved"
    record.created_event_id = event.id
    record.duplicate_status = (
        "duplicate_candidate"
        if result.action == "duplicate_candidate"
        else "none"
    )
    session.add(record)
    refresh_run_counts(session, record.api_feed_run_id)
    session.commit()
    session.refresh(record)
    return record


def update_api_feed_record_review_status(
    session: Session,
    record_id: int,
    review_status: str,
) -> ApiFeedRecord:
    record = get_api_feed_record(session, record_id)
    if record is None:
        raise ValueError("API feed record not found.")
    record.review_status = review_status
    session.add(record)
    refresh_run_counts(session, record.api_feed_run_id)
    session.commit()
    session.refresh(record)
    return record


def api_quality_counts(session: Session) -> dict[str, int]:
    soon = utc_now() + timedelta(hours=24)
    records = list(session.scalars(select(ApiFeedRecord)).all())
    counts = {
        "pending": sum(record.review_status == "pending_review" for record in records),
        "held": sum(record.review_status == "held" for record in records),
        "needs_enrichment": sum(
            record.review_status == "needs_enrichment" for record in records
        ),
        "expiring_soon": sum(
            record.compliance_expires_at is not None
            and record.compliance_expires_at <= soon
            for record in records
        ),
        "rejected": sum(record.review_status == "rejected" for record in records),
        "unknown_upstream_source": sum(
            record.upstream_event_source in {None, "unknown"}
            or "unknown upstream source" in record.provenance_flags
            for record in records
        ),
        "api_backfill_required": sum(
            "api backfill required" in record.provenance_flags
            or record.ticket_link_repair_strategy == "api_backfill_required"
            for record in records
        ),
        "suspicious_provenance": sum(
            any(
                flag.startswith("ticket repair:")
                or flag.startswith("ticketing provider detected:")
                for flag in record.provenance_flags
            )
            for record in records
        ),
    }
    for category in TICKET_LINK_CATEGORIES:
        counts[f"ticket_{category}"] = sum(
            record.ticket_link_classification == category for record in records
        )
    return counts


def ticket_link_classification_counts(session: Session) -> list[tuple[str, int]]:
    records = list(session.scalars(select(ApiFeedRecord)).all())
    return [
        (
            category,
            sum(record.ticket_link_classification == category for record in records),
        )
        for category in TICKET_LINK_CATEGORIES
    ]


def approved_events_by_provider(session: Session) -> list[tuple[str, int]]:
    rows = session.execute(
        select(Event.api_provider_key, func.count())
        .where(Event.source_type == "api_feed", Event.api_provider_key.is_not(None))
        .group_by(Event.api_provider_key)
        .order_by(Event.api_provider_key.asc())
    ).all()
    return [(str(provider), int(count)) for provider, count in rows]


def approved_events_by_ingestion_provider(session: Session) -> list[tuple[str, int]]:
    rows = session.execute(
        select(Event.ingestion_provider, func.count())
        .where(Event.source_type == "api_feed", Event.ingestion_provider.is_not(None))
        .group_by(Event.ingestion_provider)
        .order_by(Event.ingestion_provider.asc())
    ).all()
    return [(str(provider), int(count)) for provider, count in rows]


def approved_events_by_upstream_source(session: Session) -> list[tuple[str, int]]:
    rows = session.execute(
        select(Event.upstream_event_source, func.count())
        .where(
            Event.source_type == "api_feed",
            Event.upstream_event_source.is_not(None),
        )
        .group_by(Event.upstream_event_source)
        .order_by(Event.upstream_event_source.asc())
    ).all()
    return [(str(source), int(count)) for source, count in rows]


def approved_events_by_ticketing_provider(session: Session) -> list[tuple[str, int]]:
    rows = session.execute(
        select(Event.ticketing_provider, func.count())
        .where(Event.source_type == "api_feed", Event.ticketing_provider.is_not(None))
        .group_by(Event.ticketing_provider)
        .order_by(Event.ticketing_provider.asc())
    ).all()
    return [(str(provider), int(count)) for provider, count in rows]
