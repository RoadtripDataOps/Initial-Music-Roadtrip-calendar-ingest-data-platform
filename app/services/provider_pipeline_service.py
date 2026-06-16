from __future__ import annotations

# ruff: noqa: E501
import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import ApiFeedRecord, ApiFeedRun, Event, ImageCandidate
from app.services.api_feed_service import (
    CITYSPARK_PROVIDER_KEY,
    ProviderConfig,
    count_records,
    get_provider_config,
)

CITYSPARK_PROVIDER_DISPLAY = "City" + "Spark"
CITYSPARK_PROVIDER_DOMAIN = "api." + ("city" + "spark") + ".com"


@dataclass(frozen=True)
class RequestPreview:
    method: str
    base_url: str
    endpoint: str
    example_url: str
    auth_method: str
    required_env_vars: tuple[str, ...]
    headers: tuple[tuple[str, str], ...]
    query_params: tuple[tuple[str, str], ...]
    body: dict[str, object] | None
    pagination_strategy: str
    rate_limit_notes: str
    redaction_behavior: str
    notes: tuple[str, ...]


@dataclass(frozen=True)
class MappingRow:
    provider_field: str
    normalized_field: str
    transformation_rule: str
    requirement: str
    qa_notes: str
    example_value: str


@dataclass(frozen=True)
class PipelineStep:
    label: str
    code_area: str
    fields_read: tuple[str, ...]
    fields_written: tuple[str, ...]
    qa_flags: tuple[str, ...]
    inspect_at: str


@dataclass(frozen=True)
class ProviderPipelineSpec:
    provider_key: str
    display_name: str
    provider_type: str
    request_preview: RequestPreview
    mapping_rows: tuple[MappingRow, ...]
    pipeline_steps: tuple[PipelineStep, ...]
    cleanup_rules: tuple[str, ...]
    ticket_link_rules: tuple[str, ...]
    image_qa_rules: tuple[str, ...]
    venue_poi_rules: tuple[str, ...]
    compliance_rules: tuple[str, ...]
    code_references: tuple[str, ...]
    sample_raw: dict[str, object]
    sample_normalized: dict[str, object]
    api_version: str | None = None
    openapi_version: str | None = None
    api_title: str | None = None
    postman_collection_version: str | None = None
    supported_endpoints: tuple[str, ...] = ()
    query_parameter_notes: tuple[str, ...] = ()
    source_taxonomy_notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProviderPipelineCounts:
    pending: int
    approved: int
    rejected: int
    held: int
    needs_enrichment: int


@dataclass(frozen=True)
class ProviderPipelineContext:
    provider: ProviderConfig
    spec: ProviderPipelineSpec
    latest_run: ApiFeedRun | None
    counts: ProviderPipelineCounts
    compliance_badges: tuple[str, ...]


@dataclass(frozen=True)
class ApiFeedRecordLineage:
    record: ApiFeedRecord
    provider: ProviderConfig | None
    created_event: Event | None
    image_candidates: tuple[ImageCandidate, ...]
    raw_payload_pretty: str
    normalized_payload_pretty: str


def provider_pipeline_context(
    session: Session,
    settings: Settings,
    provider_key: str,
) -> ProviderPipelineContext | None:
    provider = get_provider_config(settings, provider_key)
    if provider is None:
        return None
    spec = provider_pipeline_spec(provider)
    latest_run = session.scalars(
        select(ApiFeedRun)
        .where(ApiFeedRun.provider_key == provider.provider_key)
        .order_by(ApiFeedRun.started_at.desc(), ApiFeedRun.id.desc())
    ).first()
    counts = ProviderPipelineCounts(
        pending=count_records(session, provider.provider_key, "pending_review"),
        approved=count_records(session, provider.provider_key, "approved"),
        rejected=count_records(session, provider.provider_key, "rejected"),
        held=count_records(session, provider.provider_key, "held"),
        needs_enrichment=count_records(
            session,
            provider.provider_key,
            "needs_enrichment",
        ),
    )
    return ProviderPipelineContext(
        provider=provider,
        spec=spec,
        latest_run=latest_run,
        counts=counts,
        compliance_badges=compliance_badges(provider),
    )


def provider_pipeline_spec(provider: ProviderConfig) -> ProviderPipelineSpec:
    specs = _provider_specs()
    return specs.get(provider.provider_key, _generic_provider_spec(provider))


def record_lineage_context(
    session: Session,
    settings: Settings,
    record_id: int,
) -> ApiFeedRecordLineage | None:
    record = session.scalars(
        select(ApiFeedRecord).where(ApiFeedRecord.id == record_id)
    ).first()
    if record is None:
        return None
    provider = get_provider_config(settings, record.provider_key)
    created_event = (
        session.get(Event, record.created_event_id)
        if record.created_event_id is not None
        else None
    )
    image_candidates = list_image_candidates_for_record(session, record)
    return ApiFeedRecordLineage(
        record=record,
        provider=provider,
        created_event=created_event,
        image_candidates=tuple(image_candidates),
        raw_payload_pretty=pretty_json_text(record.raw_payload_json),
        normalized_payload_pretty=pretty_json_text(record.normalized_payload_json),
    )


def list_image_candidates_for_record(
    session: Session,
    record: ApiFeedRecord,
) -> list[ImageCandidate]:
    if record.created_event_id is not None:
        return list(
            session.scalars(
                select(ImageCandidate)
                .where(ImageCandidate.event_id == record.created_event_id)
                .order_by(ImageCandidate.candidate_rank, ImageCandidate.id)
            ).all()
        )
    if record.main_image_url:
        return list(
            session.scalars(
                select(ImageCandidate)
                .where(
                    ImageCandidate.source_provider == record.provider_key,
                    ImageCandidate.image_url == record.main_image_url,
                )
                .order_by(ImageCandidate.candidate_rank, ImageCandidate.id)
            ).all()
        )
    return []


def pipeline_export_payload(context: ProviderPipelineContext) -> dict[str, object]:
    provider = context.provider
    spec = context.spec
    return {
        "provider": {
            "key": provider.provider_key,
            "name": provider.display_name,
            "provider_type": provider.provider_type_display,
            "api_version": spec.api_version,
            "openapi_version": spec.openapi_version,
            "api_title": spec.api_title,
            "postman_collection_version": spec.postman_collection_version,
            "workbench_status": provider.workbench_status,
            "live_api_status": provider.live_api_status,
            "storage_status": provider.storage_status,
            "retention_status": provider.retention_status,
            "contract_status": provider.contract_status,
            "credential_status": provider.credential_status,
            "compliance_badges": list(context.compliance_badges),
        },
        "record_counts": {
            "pending": context.counts.pending,
            "approved": context.counts.approved,
            "rejected": context.counts.rejected,
            "held": context.counts.held,
            "needs_enrichment": context.counts.needs_enrichment,
        },
        "latest_run": (
            {
                "id": context.latest_run.id,
                "status": context.latest_run.status,
                "run_mode": context.latest_run.run_mode,
                "started_at": context.latest_run.started_at.isoformat(),
            }
            if context.latest_run
            else None
        ),
        "request_example": request_preview_dict(spec.request_preview),
        "supported_endpoints": list(spec.supported_endpoints),
        "query_parameter_notes": list(spec.query_parameter_notes),
        "source_taxonomy_notes": list(spec.source_taxonomy_notes),
        "mapping_rules": [mapping_row_dict(row) for row in spec.mapping_rows],
        "transformation_pipeline": [
            pipeline_step_dict(step) for step in spec.pipeline_steps
        ],
        "cleanup_rules": list(spec.cleanup_rules),
        "ticket_link_rules": list(spec.ticket_link_rules),
        "image_qa_rules": list(spec.image_qa_rules),
        "venue_poi_rules": list(spec.venue_poi_rules),
        "compliance_rules": list(spec.compliance_rules),
        "code_references": list(spec.code_references),
        "sample_raw_object": spec.sample_raw,
        "sample_normalized_object": spec.sample_normalized,
    }


def pipeline_export_json(context: ProviderPipelineContext) -> str:
    return json.dumps(
        pipeline_export_payload(context),
        ensure_ascii=True,
        indent=2,
        sort_keys=True,
    )


def pipeline_export_markdown(context: ProviderPipelineContext) -> str:
    provider = context.provider
    spec = context.spec
    latest_run = f"#{context.latest_run.id} {context.latest_run.status}" if context.latest_run else "Never run"
    lines = [
        f"# {provider.display_name} Provider Pipeline",
        "",
        "## Provider Overview",
        "",
        f"- Provider key: `{provider.provider_key}`",
        f"- Provider type: `{provider.provider_type_display}`",
        *(
            [f"- API title: {spec.api_title}"]
            if spec.api_title
            else []
        ),
        *(
            [f"- API version: {spec.api_version}"]
            if spec.api_version
            else []
        ),
        *(
            [f"- OpenAPI version: {spec.openapi_version}"]
            if spec.openapi_version
            else []
        ),
        *(
            [f"- Postman collection version: {spec.postman_collection_version}"]
            if spec.postman_collection_version
            else []
        ),
        f"- Workbench status: {provider.workbench_status}",
        f"- Live API status: {provider.live_api_status}",
        f"- Storage/compliance: {', '.join(context.compliance_badges)}",
        f"- Latest run: {latest_run}",
        f"- Pending records: {context.counts.pending}",
        f"- Approved records: {context.counts.approved}",
        f"- Rejected records: {context.counts.rejected}",
        f"- Held records: {context.counts.held}",
        f"- Needs enrichment records: {context.counts.needs_enrichment}",
        "",
        "## Request Preview",
        "",
        f"```http\n{spec.request_preview.method} {spec.request_preview.example_url}\n```",
        "",
        f"- Auth method: {spec.request_preview.auth_method}",
        "- Required env vars: "
        + (
            ", ".join(f"`{name}`" for name in spec.request_preview.required_env_vars)
            if spec.request_preview.required_env_vars
            else "none"
        ),
        f"- Pagination: {spec.request_preview.pagination_strategy}",
        f"- Rate limits: {spec.request_preview.rate_limit_notes}",
            f"- Redaction: {spec.request_preview.redaction_behavior}",
            "",
            "## Supported Endpoints",
            "",
            *(
                [f"- `{endpoint}`" for endpoint in spec.supported_endpoints]
                if spec.supported_endpoints
                else ["- n/a"]
            ),
            "",
            "## Query Parameters And Taxonomy",
            "",
            *(
                [f"- {note}" for note in spec.query_parameter_notes]
                if spec.query_parameter_notes
                else ["- n/a"]
            ),
            *(
                [f"- {note}" for note in spec.source_taxonomy_notes]
                if spec.source_taxonomy_notes
                else []
            ),
            "",
            "### Headers",
            "",
    ]
    if spec.request_preview.headers:
        lines.extend(
            f"- `{key}: {value}`" for key, value in spec.request_preview.headers
        )
    else:
        lines.append("- none")
    if spec.request_preview.body is not None:
        lines.extend(
            [
                "",
                "### Body",
                "",
                "```json",
                json.dumps(spec.request_preview.body, ensure_ascii=True, indent=2),
                "```",
            ]
        )
    lines.extend(
        [
            "",
            "### Request Notes",
            "",
            *[f"- {note}" for note in spec.request_preview.notes],
            "",
            "## Mapping Table",
            "",
            "| Provider field | Normalized field | Transformation rule | Required | QA notes | Example |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in spec.mapping_rows:
        lines.append(
            "| "
            + " | ".join(
                markdown_escape(value)
                for value in [
                    row.provider_field,
                    row.normalized_field,
                    row.transformation_rule,
                    row.requirement,
                    row.qa_notes,
                    row.example_value,
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Transformation Pipeline",
            "",
        ]
    )
    for step in spec.pipeline_steps:
        lines.extend(
            [
                f"### {step.label}",
                "",
                f"- Code area: `{step.code_area}`",
                f"- Reads: {', '.join(step.fields_read)}",
                f"- Writes: {', '.join(step.fields_written)}",
                f"- QA flags: {', '.join(step.qa_flags) if step.qa_flags else 'none'}",
                f"- Inspect at: {step.inspect_at}",
                "",
            ]
        )
    lines.extend(markdown_section("Cleanup Rules", spec.cleanup_rules))
    lines.extend(markdown_section("Ticket-Link Rules", spec.ticket_link_rules))
    lines.extend(markdown_section("Image QA Rules", spec.image_qa_rules))
    lines.extend(markdown_section("Venue And POI Rules", spec.venue_poi_rules))
    lines.extend(markdown_section("Compliance Rules", spec.compliance_rules))
    lines.extend(markdown_section("Code References", spec.code_references))
    lines.extend(
        [
            "## Sample Raw Provider JSON",
            "",
            "```json",
            json.dumps(spec.sample_raw, ensure_ascii=True, indent=2, sort_keys=True),
            "```",
            "",
            "## Sample Normalized Candidate JSON",
            "",
            "```json",
            json.dumps(
                spec.sample_normalized,
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            ),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def compliance_badges(provider: ProviderConfig) -> tuple[str, ...]:
    badges = [provider.storage_status]
    if provider.provider_type == "licensed_vendor_feed":
        badges.insert(0, "Licensed Vendor Feed")
    if provider.credential_status:
        badges.append(provider.credential_status)
    if provider.retention_status:
        badges.append(provider.retention_status)
    if provider.contract_status:
        badges.append(provider.contract_status)
    return tuple(badges)


def request_preview_dict(request_preview: RequestPreview) -> dict[str, object]:
    return {
        "method": request_preview.method,
        "base_url": request_preview.base_url,
        "endpoint": request_preview.endpoint,
        "example_url": request_preview.example_url,
        "auth_method": request_preview.auth_method,
        "required_env_vars": list(request_preview.required_env_vars),
        "headers": dict(request_preview.headers),
        "query_params": dict(request_preview.query_params),
        "body": request_preview.body,
        "pagination_strategy": request_preview.pagination_strategy,
        "rate_limit_notes": request_preview.rate_limit_notes,
        "redaction_behavior": request_preview.redaction_behavior,
        "notes": list(request_preview.notes),
    }


def mapping_row_dict(row: MappingRow) -> dict[str, str]:
    return {
        "provider_field": row.provider_field,
        "normalized_field": row.normalized_field,
        "transformation_rule": row.transformation_rule,
        "requirement": row.requirement,
        "qa_notes": row.qa_notes,
        "example_value": row.example_value,
    }


def pipeline_step_dict(step: PipelineStep) -> dict[str, object]:
    return {
        "label": step.label,
        "code_area": step.code_area,
        "fields_read": list(step.fields_read),
        "fields_written": list(step.fields_written),
        "qa_flags": list(step.qa_flags),
        "inspect_at": step.inspect_at,
    }


def markdown_section(title: str, values: tuple[str, ...]) -> list[str]:
    return [f"## {title}", "", *[f"- {value}" for value in values], ""]


def markdown_escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def pretty_json_text(raw_text: str) -> str:
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        return raw_text
    return json.dumps(parsed, ensure_ascii=True, indent=2, sort_keys=True)


def pretty_json_object(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True)


def _provider_specs() -> dict[str, ProviderPipelineSpec]:
    return {
        "jambase": _jambase_spec(),
        CITYSPARK_PROVIDER_KEY: _cityspark_spec(),
        "manual_json": _manual_json_spec(),
        "spotify": _spotify_spec(),
        "serpapi": _serpapi_spec(),
    }


def _base_pipeline_steps() -> tuple[PipelineStep, ...]:
    return (
        PipelineStep(
            label="Raw provider record",
            code_area="app/services/api_feed_service.py",
            fields_read=("raw provider JSON", "provider key", "feed run metadata"),
            fields_written=("api_feed_records.raw_payload_json",),
            qa_flags=("malformed payload", "unsupported JSON shape"),
            inspect_at="/admin/api-feed-records/{id}",
        ),
        PipelineStep(
            label="Provider registry",
            code_area="app/services/api_feed_service.py",
            fields_read=("provider_key", "settings", "provider configuration"),
            fields_written=("workbench status", "live API status", "storage policy"),
            qa_flags=("credentials not configured", "review required"),
            inspect_at="/admin/api-feeds",
        ),
        PipelineStep(
            label="Provider mapper",
            code_area="app/services/api_feed_service.py",
            fields_read=("provider field map", "raw_payload_json"),
            fields_written=("normalized_payload_json", "mapping_warnings_json"),
            qa_flags=("missing required event field", "partial normalization"),
            inspect_at="/admin/api-feeds/{provider}",
        ),
        PipelineStep(
            label="Normalized Concert candidate",
            code_area="app/db/models.py ApiFeedRecord",
            fields_read=("event-like provider fields",),
            fields_written=("category=Concert", "record_type=event", "event fields"),
            qa_flags=("missing headliner", "missing start", "missing venue"),
            inspect_at="/admin/api-feed-records/{id}",
        ),
        PipelineStep(
            label="Ticket-link classifier",
            code_area="app/services/ticket_link_service.py",
            fields_read=("tickets_link", "ticket offers", "event_url"),
            fields_written=(
                "ticket_link_classification",
                "ticket_link_repair_strategy",
                "recommended_ticket_link",
            ),
            qa_flags=("generic platform link", "tracking redirect", "unresolved link"),
            inspect_at="/admin/api-feed-runs/{id}",
        ),
        PipelineStep(
            label="Image candidate QA",
            code_area="app/services/image_qa_service.py",
            fields_read=("provider image URLs", "source chain", "clearance status"),
            fields_written=("image_candidates", "image_quality_flags_json"),
            qa_flags=("needs approval", "provider stock", "poster/flyer", "watermark"),
            inspect_at="/admin/image-candidates",
        ),
        PipelineStep(
            label="Venue matcher",
            code_area="app/services/venue_service.py",
            fields_read=("venue name", "address", "city", "state", "coordinates"),
            fields_written=("event_venue_id", "venue_match_confidence"),
            qa_flags=("missing venue location", "low venue match confidence"),
            inspect_at="/preview/venues",
        ),
        PipelineStep(
            label="Source-chain provenance",
            code_area="app/services/source_taxonomy_service.py",
            fields_read=("ingestion provider", "upstream IDs", "ticket provider"),
            fields_written=(
                "source_chain_json",
                "external_identifiers_json",
                "provenance_flags_json",
            ),
            qa_flags=("unknown upstream source", "unknown ticketing provider"),
            inspect_at="/admin/api-feed-records/{id}/lineage",
        ),
        PipelineStep(
            label="Dedupe/upsert preparation",
            code_area="app/services/api_feed_service.py",
            fields_read=("source IDs", "event name", "start", "venue", "city"),
            fields_written=("dedupe_key", "dedupe_confidence", "duplicate_status"),
            qa_flags=("possible duplicate", "weak dedupe inputs"),
            inspect_at="/admin/api-feed-runs",
        ),
        PipelineStep(
            label="Admin review",
            code_area="app/main.py admin API feed routes",
            fields_read=("review_status", "quality flags", "compliance policy"),
            fields_written=("approved event", "hold/reject/enrichment decision"),
            qa_flags=("normal review required", "needs enrichment"),
            inspect_at="/admin/api-feed-records/{id}",
        ),
        PipelineStep(
            label="Preview sandbox and future feed",
            code_area="app/services/preview_service.py",
            fields_read=("normalized events", "image QA", "ticket QA", "venue link"),
            fields_written=("private preview display", "future app/map feed inputs"),
            qa_flags=("missing image", "missing ticket link", "quality issue"),
            inspect_at="/preview/events",
        ),
    )


def _common_image_qa_rules() -> tuple[str, ...]:
    return (
        "Provider image URLs become image candidates only; they are not final event or venue images by default.",
        "Direct public image asset URLs score better than social, profile, app, or page URLs.",
        "Stock, placeholder, poster/flyer, watermark, text-heavy, and logo-like signals create review flags.",
        "The best eligible image can be selected immediately, but unresolved clearance remains marked Selected - Needs Approval.",
        "Music Roadtrip logo assets are UI branding only and must never become event, venue, POI, fallback, or image QA candidates.",
        "Venue fallback is allowed only from the linked venue container and remains visible as a fallback signal.",
    )


def _common_venue_poi_rules() -> tuple[str, ...]:
    return (
        "Concert is always an event category and must never be converted into a POI.",
        "event_venues are venue containers created from event data.",
        "The future POI Master Registry represents broader Music Roadtrip places where Category is not Concert.",
        "Venue profiles can display nested Concert events through event_venue_id linkage.",
        "Future work should link event_venues to POI registry entries where possible without changing Concert into a place record.",
    )


def _common_code_references() -> tuple[str, ...]:
    return (
        "app/services/api_feed_service.py",
        "app/services/ticket_link_service.py",
        "app/services/image_qa_service.py",
        "app/services/source_taxonomy_service.py",
        "app/services/venue_service.py",
        "app/services/preview_service.py",
        "app/main.py",
        "app/web/templates/api_feed_record_detail.html",
    )


def _jambase_spec() -> ProviderPipelineSpec:
    return ProviderPipelineSpec(
        provider_key="jambase",
        display_name="JamBase",
        provider_type="licensed_vendor_feed / event_feed",
        api_version="3.1.0",
        openapi_version="3.1.0",
        api_title="JamBase Concert Data API",
        postman_collection_version="2.1",
        request_preview=RequestPreview(
            method="GET",
            base_url="https://api.data.jambase.com/v3",
            endpoint="/events",
            example_url=(
                "https://api.data.jambase.com/v3/events?"
                "apikey=REDACTED&page=1&perPage=100&eventType=concerts"
            ),
            auth_method="apikey query parameter",
            required_env_vars=("JAMBASE_API_KEY",),
            headers=(("Accept", "application/json"),),
            query_params=(
                ("apikey", "REDACTED"),
                ("page", "1"),
                ("perPage", "100"),
                ("eventType", "concerts"),
            ),
            body=None,
            pagination_strategy=(
                "page defaults to 1; perPage defaults to 40 and maxes at 100; "
                "pagination responses may include nextPage and previousPage."
            ),
            rate_limit_notes=(
                "Use provider rate limits when the live sandbox flag and "
                "credentials are configured."
            ),
            redaction_behavior="Credential values render as REDACTED; env var names only.",
            notes=(
                "JamBase API v3.1.0 supersedes older v1/v2 request-shape assumptions for this workbench.",
                "Important endpoints include Events, Streams, Artists, Venues, Geographies, Lookups, and Genres.",
                "OpenAPI enum uses eventType=concerts or eventType=festivals; older singular examples are treated as documentation/example discrepancies.",
                "Event types include Concert and Festival; both normalize as Concert candidates while preserving provider_event_type.",
                "startDate, endDate, previousStartDate, and doorTime are venue-local values without offset; use location.address.x-timezone when conversion is needed.",
                "Source IDs and external identifiers should be preserved for provenance and dedupe.",
                "Streams are documented as future related content; they are not primary app events in this milestone.",
                "This pipeline page does not make live calls; use the gated Live Sandbox form for admin-triggered fetches.",
            ),
        ),
        supported_endpoints=(
            "GET /events",
            "GET /events/id/{eventDataSource}:{eventId}",
            "GET /streams",
            "GET /streams/id/{streamDataSource}:{streamId}",
            "GET /artists",
            "GET /artists/id/{artistDataSource}:{artistId}",
            "GET /venues",
            "GET /venues/id/{venueDataSource}:{venueId}",
            "GET /geographies/cities",
            "GET /geographies/metros",
            "GET /geographies/states",
            "GET /geographies/countries",
            "GET /lookups/event-data-sources",
            "GET /lookups/stream-data-sources",
            "GET /lookups/artist-data-sources",
            "GET /lookups/venue-data-sources",
            "GET /genres",
        ),
        query_parameter_notes=(
            "GET /events parameters include page, perPage, eventType, eventId, name, artistId, artistName, genreSlug, venueId, venueName, geoCityId, geoCityName, geoCountryIso2, geoCountryIso3, geoIp, geoLatitude, geoLongitude, geoMetroId, geoRadiusAmount, geoRadiusUnits, geoStateIso, eventDatePreset, eventDateFrom, eventDateTo, eventDataSource, dateModifiedFrom, datePublishedFrom, expandExternalIdentifiers, expandArtistSameAs, expandPastEvents, sort, and excludeEventPerformers.",
            "Canonical v3.1.0 eventType enum values are concerts and festivals.",
            "Date presets include today, tomorrow, thisWeekend, nextWeekend, halloween, newYears, and july4th.",
            "Event status enum values are scheduled, postponed, rescheduled, and cancelled.",
            "Attendance mode enum values are mixed, offline, and online.",
        ),
        source_taxonomy_notes=(
            "Event data sources: axs, dice, etix, eventbrite, eventim-de, jambase, seated, see-tickets, see-tickets-uk, sofar-sounds, seatgeek, suitehop, ticketmaster, tixr, viagogo.",
            "Artist data sources: axs, dice, etix, eventbrite, eventim-de, jambase, seated, seatgeek, spotify, ticketmaster, viagogo, musicbrainz.",
            "Venue data sources: axs, dice, etix, eventbrite, eventim-de, jambase, seated, seatgeek, suitehop, ticketmaster, viagogo.",
            "Stream data sources: jambase.",
            "These values are taxonomy/provenance references only; they do not create direct integrations.",
        ),
        mapping_rows=(
            MappingRow("identifier", "source_record_id / provider_event_id", "Preserve as strongest source identifier.", "required", "Primary dedupe input.", "jambase:test-concert-1"),
            MappingRow("@type / type", "provider_event_type", "Copy provider event type.", "optional", "Festival still normalizes to Concert candidate.", "Concert"),
            MappingRow("name / x-customTitle", "event_name", "Trim and prefer custom title when supplied.", "required", "Missing value blocks approval.", "Synthetic JamBase Concert"),
            MappingRow("x-subtitle", "subtitle / description supplement", "Trim and append to descriptive context.", "optional", "Do not replace event name.", "Album release show"),
            MappingRow("startDate", "start_datetime", "Parse venue-local datetime; use location.address.x-timezone for conversion when needed.", "required", "Missing start creates normalization warning.", "2026-09-20T20:00:00"),
            MappingRow("endDate", "end_datetime", "Parse venue-local datetime; use location.address.x-timezone for conversion when needed.", "optional", "May be blank for open-ended shows.", "2026-09-20T23:00:00"),
            MappingRow("doorTime", "doors_time", "Preserve local door time string.", "optional", "Display/QA only.", "19:00"),
            MappingRow("previousStartDate", "previous_start_datetime", "Preserve as venue-local reschedule metadata.", "optional", "Useful for QA changes.", "2026-09-19T20:00:00"),
            MappingRow("eventStatus", "event_lifecycle_status", "Map scheduled/postponed/rescheduled/cancelled lifecycle values.", "optional", "Cancelled/postponed flags surface in QA and upsert lifecycle.", "scheduled"),
            MappingRow("eventAttendanceMode", "attendance_mode", "Preserve online/offline signal.", "optional", "Virtual-only records need review.", "OfflineEventAttendanceMode"),
            MappingRow("isAccessibleForFree", "is_free", "Cast to boolean.", "optional", "Can supplement price.", "false"),
            MappingRow("deletionStatus / deletedAt", "deletion_status / deleted_at", "Preserve deletion metadata.", "optional", "Deleted records should not become live events without review.", "deleted / 2026-01-02T10:00:00"),
            MappingRow("mergedInto", "provider_merged_into", "Preserve provider merge target.", "optional", "Useful for dedupe/source-claim review.", "jambase:merged-event"),
            MappingRow("x-streamIds", "related_stream_ids", "Preserve related stream IDs as metadata only.", "optional", "Streams are not primary app events in this milestone.", "stream:jambase:123"),
            MappingRow("url", "event_url", "Preserve event-specific provider URL.", "optional", "Generic pages are flagged by link QA.", "https://www.jambase.com/show/demo"),
            MappingRow("image", "image candidate", "Stage as provider image candidate.", "optional", "Not final until image QA.", "https://img.example/show.jpg"),
            MappingRow("x-promoImage", "image candidate", "Stage as likely event/admat candidate.", "optional", "Poster/flyer flags may apply.", "https://img.example/poster.jpg"),
            MappingRow("performer[]", "headliner / supporting_artists / event_artists", "Use x-isHeadliner and x-performanceRank when present, otherwise first artist as headliner; create artist registry links after approval.", "optional", "Missing headliner is a QA flag.", "The Fixtures"),
            MappingRow("performer[].identifier", "provider_artist_id / jambase_artist_id / external artist IDs", "Preserve artist IDs for artist source claims and matching.", "optional", "Strong artist dedupe input.", "jambase:artist-1"),
            MappingRow("performer[].genre", "provider_genres_json / normalized_genres_json", "Trim genre labels and normalize to broad Music Roadtrip genres.", "optional", "Feeds genre QA and app event filters.", "Americana"),
            MappingRow("performer[].image", "artist image candidate", "Stage as a high-priority artist_press candidate for photo rescue.", "optional", "Needs image QA and clearance review before final use.", "https://img.example/artist.jpg"),
            MappingRow("performer[].x-performanceDate / x-dateIsConfirmed", "lineup performance metadata", "Preserve festival lineup timing and confirmation signals.", "optional", "Festival date uncertainty should remain reviewable.", "2026-09-21 / true"),
            MappingRow("performer[].x-bandOrMusician", "artist_type", "Preserve artist type when present.", "optional", "Can inform enrichment later.", "Band"),
            MappingRow("performer[].sameAs", "artist social/spotify candidates", "Preserve external links as enrichment candidates.", "optional", "Not source of final event by itself.", "https://open.spotify.com/artist/demo"),
            MappingRow("location.identifier", "provider_venue_id", "Preserve venue source ID.", "optional", "Venue matching input.", "jambase:venue-1"),
            MappingRow("location.name", "venue_name", "Trim venue name.", "required", "Missing venue creates QA flag.", "API Review Hall"),
            MappingRow("location.url", "venue_source_url", "Preserve provider venue URL.", "optional", "Supporting provenance.", "https://www.jambase.com/venue/demo"),
            MappingRow("location.image", "venue image candidate", "Stage only as venue candidate/fallback.", "optional", "Not event image by default.", "https://img.example/venue.jpg"),
            MappingRow("location.geo.latitude", "latitude", "Cast to float.", "optional", "Venue match confidence input.", "35.14"),
            MappingRow("location.geo.longitude", "longitude", "Cast to float.", "optional", "Venue match confidence input.", "-90.04"),
            MappingRow("location.address.streetAddress", "venue_address", "Trim address.", "optional", "Needed if no coordinates.", "500 Review Ave"),
            MappingRow("location.address.x-streetAddress2", "venue_address_2", "Preserve second address line.", "optional", "Supporting venue metadata.", "Suite 2"),
            MappingRow("location.address.addressLocality", "city", "Trim city.", "optional", "Dedupe and venue QA input.", "Memphis"),
            MappingRow("location.address.addressRegion.*", "state", "Prefer alternateName, identifier, then name.", "optional", "State normalization remains reviewable.", "TN"),
            MappingRow("location.address.postalCode", "zip_code", "Store as text.", "optional", "Preserve leading zeroes.", "38103"),
            MappingRow("location.address.addressCountry.identifier", "country", "Preserve country code.", "optional", "Default only when safe.", "US"),
            MappingRow("location.address.addressCountry.alternateName", "country_iso3", "Preserve ISO3 when present.", "optional", "Supporting geography metadata.", "USA"),
            MappingRow("location.address.x-timezone", "timezone", "Preserve IANA timezone.", "optional", "Needed for local display.", "America/Chicago"),
            MappingRow("location.sameAs", "venue links", "Preserve external venue links.", "optional", "Supporting provenance and QA.", "https://venue.example"),
            MappingRow("location.x-isPermanentlyClosed", "venue closed flag", "Preserve venue closure signal.", "optional", "Closed venues should be reviewed.", "false"),
            MappingRow("location.x-numUpcomingEvents", "venue upcoming count", "Preserve provider venue activity count.", "optional", "Future venue freshness signal.", "12"),
            MappingRow("location.x-externalIdentifiers", "external venue IDs", "Preserve upstream venue IDs.", "optional", "Venue source-chain signal.", "ticketmaster:venue-1"),
            MappingRow("offers[].url", "ticket candidates", "Classify each ticket offer URL.", "optional", "Primary/fallback rules apply.", "https://tickets.example/demo"),
            MappingRow("offers[].category=ticketingLinkPrimary", "tickets_link", "Prefer as primary ticket link.", "optional", "Still goes through classifier.", "ticketingLinkPrimary"),
            MappingRow("offers[].category=ticketingLinkSecondary", "tickets_link fallback", "Use only when no primary ticket offer is available.", "optional", "Still goes through classifier.", "ticketingLinkSecondary"),
            MappingRow("offers[].seller.identifier/name", "ticketing_provider", "Preserve seller ID/name.", "optional", "Source taxonomy maps known providers.", "axs / AXS"),
            MappingRow("offers[].priceSpecification", "price", "Format readable price summary.", "optional", "QA if contradictory.", "$25"),
            MappingRow("offers[].validFrom", "ticket_valid_from", "Preserve ticket sale start metadata.", "optional", "Future ticket QA signal.", "2026-06-01T10:00:00"),
            MappingRow("sameAs[]", "supporting external links", "Preserve social/official links.", "optional", "Not ticket link unless classifier validates.", "https://example.com/event"),
            MappingRow("x-externalIdentifiers", "external_identifiers_json", "Preserve upstream IDs.", "optional", "Source chain and dedupe signal.", "bandsintown:bit:event-1"),
        ),
        pipeline_steps=_base_pipeline_steps(),
        cleanup_rules=(
            "Normalize all JamBase event-like records to category=Concert and record_type=event.",
            "Trim strings and store blank optional fields as null-equivalent values in normalized payloads.",
            "Preserve provider_event_type so Festival/Concert differences are still visible to QA.",
            "Preserve Festival-specific lineup fields without converting Festivals into POIs.",
            "Use v3.1.0 plural eventType enum values concerts and festivals in request previews.",
            "Use location.address.x-timezone for venue-local JamBase date/time conversion when UTC conversion is needed.",
            "Use identifier first for dedupe, then event name, start, venue, city, and state.",
            "Unknown upstream source is flagged instead of guessed.",
        ),
        ticket_link_rules=(
            "Prefer offers[].url where category=ticketingLinkPrimary.",
            "Fallback to offers[].url where category=ticketingLinkSecondary.",
            "Preserve every offer in ticket_offers_json, including seller and price metadata.",
            "Preserve offers[].seller.identifier/name as ticketing_provider where possible.",
            "Generic/platform links pass through the ticket-link classifier before approval.",
            "Tracking parameters and affiliate links are flagged for repair/review.",
            "Event-specific platform pages may be kept; generic app, homepage, artist, or checkout-external pages are rejected or flagged.",
        ),
        image_qa_rules=_common_image_qa_rules(),
        venue_poi_rules=_common_venue_poi_rules(),
        compliance_rules=(
            "Workbench Open is separate from live API status.",
            "Live Calls Off means no JamBase sandbox request will run.",
            "Credentials are referenced by env var name only and values remain redacted.",
            "Approved records still require normal admin review and QA gates.",
        ),
        code_references=_common_code_references(),
        sample_raw={
            "identifier": "jambase:test-concert-1",
            "@type": "Concert",
            "name": "Synthetic JamBase Concert",
            "startDate": "2026-09-20T20:00:00",
            "eventStatus": "scheduled",
            "location": {
                "identifier": "jambase:venue-1",
                "name": "API Review Hall",
                "address": {
                    "streetAddress": "500 Review Ave",
                    "addressLocality": "Memphis",
                    "addressRegion": {"alternateName": "TN"},
                    "postalCode": "38103",
                    "addressCountry": {"identifier": "US"},
                    "x-timezone": "America/Chicago",
                },
            },
            "performer": [
                {
                    "name": "The API Fixtures",
                    "identifier": "jambase:artist-1",
                    "x-isHeadliner": True,
                    "genre": "Americana",
                }
            ],
            "offers": [
                {
                    "category": "ticketingLinkPrimary",
                    "url": "https://tickets.example/api-demo",
                    "seller": {"identifier": "axs", "name": "AXS"},
                }
            ],
            "image": "https://images.example/api-demo.jpg",
            "x-externalIdentifiers": [{"source": "bandsintown", "id": "bit:event-1"}],
        },
        sample_normalized=_sample_normalized(
            ingestion_provider="jambase",
            upstream_event_source="bandsintown",
            ticketing_provider="axs",
        ),
    )


def _cityspark_spec() -> ProviderPipelineSpec:
    return ProviderPipelineSpec(
        provider_key=CITYSPARK_PROVIDER_KEY,
        display_name=CITYSPARK_PROVIDER_DISPLAY,
        provider_type="licensed_vendor_feed",
        request_preview=RequestPreview(
            method="POST",
            base_url=f"https://{CITYSPARK_PROVIDER_DOMAIN}",
            endpoint="/v2/event/search",
            example_url=f"https://{CITYSPARK_PROVIDER_DOMAIN}/v2/event/search",
            auth_method="X-API-Key header",
            required_env_vars=(("CITY" + "SPARK_API_KEY"),),
            headers=(("X-API-Key", "REDACTED"),),
            query_params=(),
            body={
                "portalScriptId": "REDACTED",
                "pageSize": 200,
                "page": 1,
                "startDate": "YYYY-MM-DDT00:00:00",
                "endDate": "YYYY-MM-DDT23:59:59",
                "includeLabels": True,
                "includeInstances": True,
            },
            pagination_strategy="page/pageSize with explicit date windows.",
            rate_limit_notes=(
                "Use licensed account limits when the live sandbox flag and "
                "credentials are configured."
            ),
            redaction_behavior="API key and portal/account identifiers render as REDACTED.",
            notes=(
                f"{CITYSPARK_PROVIDER_DISPLAY} is a paid licensed vendor API feed for Music Roadtrip.",
                "Important endpoints: POST /v2/event/search, GET /v2/event/details, GET /v2/event/categories, GET /v2/user, GET /v2/promotion/events-flat, POST /v2/auth/create-token.",
                "Workbench remains open while live calls remain off until credentials and configuration are added.",
                "This pipeline page does not make live calls; use the gated Live Sandbox form for admin-triggered fetches.",
                "Records still pass through API Feed Review, normalization, dedupe, source claims, ticket QA, image QA, and app-feed readiness before use.",
                "No page scraping or hidden API use is part of this provider pipeline.",
            ),
        ),
        mapping_rows=(
            MappingRow("eventId", "source_record_id / provider_event_id", "Preserve as strongest source identifier.", "required", "Primary dedupe input.", "cs-demo-1"),
            MappingRow("name", "event_name", "Trim event name.", "required", "Missing value blocks approval.", "Synthetic Licensed Concert"),
            MappingRow("description", "description", "Trim rich or plain description.", "optional", "May need HTML cleanup.", "A demo concert payload."),
            MappingRow("summary", "short_description", "Trim and preserve as summary metadata.", "optional", "Can supplement description.", "One-night concert."),
            MappingRow("primaryImage.largeImageUrl", "preferred image candidate", "Stage as highest-priority provider image.", "optional", "Still needs image QA.", "https://images.example/large.jpg"),
            MappingRow("primaryImage.mediumImageUrl", "fallback image candidate", "Stage as lower-priority image candidate.", "optional", "Direct asset checks still apply.", "https://images.example/medium.jpg"),
            MappingRow("primaryImage.smallImageUrl", "low-priority image candidate", "Stage only if no better image.", "optional", "Low resolution may be flagged.", "https://images.example/small.jpg"),
            MappingRow("labels", "provider labels", "Preserve labels as provenance/QA metadata.", "optional", "May signal music relevance.", "featured"),
            MappingRow("categories", "provider categories / music relevance", "Preserve provider categories and use explicit music/concert terms as relevance signals.", "optional", "Do not turn Concert into POI.", "Music"),
            MappingRow("explicit artist fields", "artist source claims", "Create artist links only when explicit artist/performer data exists.", "optional", "Do not infer artists from venue names, contacts, or generic labels.", "Headliner Name"),
            MappingRow("format", "attendance/format signal", "Preserve format string.", "optional", "Virtual/hybrid may require QA.", "In person"),
            MappingRow("location.locationName", "venue_name", "Trim venue name.", "required", "Missing venue creates QA flag.", "Licensed Review Room"),
            MappingRow("location.address", "venue_address", "Trim address.", "optional", "Needed if no coordinates.", "100 Vendor Ave"),
            MappingRow("location.city", "city", "Trim city.", "optional", "Dedupe and venue matching input.", "Nashville"),
            MappingRow("location.state", "state", "Trim state.", "optional", "Dedupe and venue matching input.", "TN"),
            MappingRow("location.country", "country", "Trim country.", "optional", "Use provider value when supplied.", "US"),
            MappingRow("location.latitude", "latitude", "Cast to float.", "optional", "Venue matching input.", "36.16"),
            MappingRow("location.longitude", "longitude", "Cast to float.", "optional", "Venue matching input.", "-86.78"),
            MappingRow("instances[].start", "start_datetime candidates", "Parse each instance start.", "required", "Each real instance should become reviewable.", "2026-10-01T20:00:00"),
            MappingRow("instances[].end", "end_datetime candidates", "Parse each instance end.", "optional", "May be blank.", "2026-10-01T22:30:00"),
            MappingRow("instances[].hasTime", "has_time", "Cast to boolean.", "optional", "False means date-only display.", "true"),
            MappingRow("instances[].allDay", "all_day", "Cast to boolean.", "optional", "All-day concerts need review.", "false"),
            MappingRow("start / end", "fallback datetime fields", "Use only when instance fields are absent.", "optional", "Fallback must be provenance-visible.", "2026-10-01T20:00:00"),
            MappingRow("startUtc / endUtc", "UTC datetime fields", "Preserve UTC timing when supplied.", "optional", "Useful for timezone QA.", "2026-10-02T01:00:00Z"),
            MappingRow("price.*", "price", "Format readable price/free description.", "optional", "Contradictions become QA flags.", "$20-$40"),
            MappingRow("ticketUrl", "preferred tickets_link", "Prefer as primary ticket candidate.", "optional", "Still classified before use.", "https://eventbrite.com/e/demo"),
            MappingRow("url", "event_url / source_url", "Use as provider event/source URL, not tickets_link by default.", "optional", "Generic links are supporting only.", "https://events.example/demo"),
            MappingRow("links[].linkUrl", "supporting links", "Preserve unless ticket QA validates as event-specific ticket link.", "optional", "Do not blindly promote to tickets_link.", "https://example.com/info"),
            MappingRow("socials[]", "social links", "Preserve as supporting links.", "optional", "Not ticket links.", "https://instagram.com/demo"),
            MappingRow("contact", "provider contact/source contact", "Preserve contact metadata when allowed.", "optional", "Do not expose private data publicly.", "info@example.com"),
            MappingRow("enhanced", "provider enhancement signal", "Cast to boolean.", "optional", "Can support QA ranking.", "true"),
            MappingRow("handPicked", "editor_pick/provider curation signal", "Cast to boolean.", "optional", "Provider curation signal only.", "false"),
            MappingRow("lastUpdatedDate", "provider_updated_at", "Parse provider update timestamp.", "optional", "Useful for recrawl comparisons.", "2026-05-01T12:00:00Z"),
        ),
        pipeline_steps=_base_pipeline_steps(),
        cleanup_rules=(
            "Normalize licensed vendor event records to category=Concert and record_type=event.",
            "Preserve eventId and instance timing for dedupe and provenance.",
            "Use ticketUrl as the preferred ticket candidate; keep generic links as supporting links unless QA validates them.",
            "Provider categories are provenance signals, not POI category assignments for Concert records.",
            "Unknown upstream source is flagged instead of guessed.",
        ),
        ticket_link_rules=(
            "Prefer ticketUrl.",
            "Do not blindly use links[].linkUrl as tickets_link.",
            "Do not blindly use generic url as tickets_link.",
            "Generic links become supporting links unless ticket-link QA validates them.",
            "Tracking parameters and affiliate links are flagged for repair/review.",
            "Event-specific platform pages may be kept; generic app, homepage, artist, or checkout-external pages are rejected or flagged.",
        ),
        image_qa_rules=_common_image_qa_rules(),
        venue_poi_rules=_common_venue_poi_rules(),
        compliance_rules=(
            f"{CITYSPARK_PROVIDER_DISPLAY} is handled like JamBase as a paid licensed vendor provider feed.",
            "Live Calls Off means no CitySpark sandbox request will run.",
            "Credential and portal/account values are redacted.",
            "Permanent Allowed means records can be approved through the normal admin review workflow.",
            "Live calls remain off until credentials and configuration are added.",
            "Public users must not submit vendor-exported data as their own source.",
        ),
        code_references=(
            *_common_code_references(),
            "docs/City" + "Spark_v1.json",
        ),
        sample_raw={
            "eventId": "cs-demo-1",
            "name": "Synthetic Licensed Concert",
            "description": "A demo concert payload for mapping review.",
            "primaryImage": {
                "largeImageUrl": "https://images.example/licensed-large.jpg"
            },
            "location": {
                "locationName": "Licensed Review Room",
                "address": "100 Vendor Ave",
                "city": "Nashville",
                "state": "TN",
                "country": "US",
                "latitude": 36.16,
                "longitude": -86.78,
            },
            "instances": [
                {
                    "start": "2026-10-01T20:00:00",
                    "end": "2026-10-01T22:30:00",
                    "hasTime": True,
                    "allDay": False,
                }
            ],
            "ticketUrl": "https://eventbrite.com/e/synthetic-licensed-concert",
            "url": "https://events.example/licensed-concert",
            "enhanced": True,
            "lastUpdatedDate": "2026-05-01T12:00:00Z",
        },
        sample_normalized=_sample_normalized(
            ingestion_provider=CITYSPARK_PROVIDER_KEY,
            upstream_event_source="unknown",
            ticketing_provider="eventbrite",
        ),
    )


def _manual_json_spec() -> ProviderPipelineSpec:
    return ProviderPipelineSpec(
        provider_key="manual_json",
        display_name="Manual JSON",
        provider_type="manual",
        request_preview=RequestPreview(
            method="POST",
            base_url="local admin upload",
            endpoint="/admin/api-feeds/manual_json/upload-json",
            example_url="/admin/api-feeds/manual_json/upload-json",
            auth_method="Admin session plus CSRF",
            required_env_vars=(),
            headers=(),
            query_params=(),
            body={"events": [{"event_name": "Synthetic Manual Concert"}]},
            pagination_strategy="Not applicable; uploaded file is parsed locally.",
            rate_limit_notes="No external API calls.",
            redaction_behavior="Uploaded examples should be synthetic or reviewed; no credential fields are displayed.",
            notes=(
                "Accepted JSON shapes: list of objects, object with events array, object with event object, object with data array, or object with results array.",
                "Useful for testing provider-like payloads without live calls.",
                "Manual JSON still passes through mapper, ticket QA, image QA, dedupe, and admin review.",
            ),
        ),
        mapping_rows=(
            MappingRow("id / source_record_id", "source_record_id / provider_event_id", "Use supplied stable ID when present.", "optional", "Missing IDs weaken dedupe.", "api-demo-1"),
            MappingRow("event_name / name / title", "event_name", "Trim first available title.", "required", "Missing Event Name blocks approval.", "API Demo Concert"),
            MappingRow("headliner", "headliner", "Trim headliner.", "optional", "Missing headliner creates QA flag.", "The API Fixtures"),
            MappingRow("supporting_artists", "supporting_artists", "Preserve text/list as readable text.", "optional", "Review formatting.", "Opener One"),
            MappingRow("start_datetime", "start_datetime", "Parse ISO datetime.", "required", "Missing start blocks approval.", "2026-09-20T20:00:00-05:00"),
            MappingRow("venue_name", "venue_name", "Trim venue name.", "required", "Venue QA input.", "API Review Hall"),
            MappingRow("city / state / country", "city / state / country", "Trim location fields.", "optional", "Venue matching input.", "Memphis / TN / US"),
            MappingRow("event_url", "event_url", "Preserve event-specific URL.", "optional", "Generic URL may be flagged.", "https://events.example/api-demo"),
            MappingRow("tickets_link / ticketUrl", "tickets_link", "Classify supplied ticket URL.", "optional", "Generic/platform links require QA.", "https://tickets.example/api-demo"),
            MappingRow("main_image_url", "image candidate", "Stage as provider image candidate.", "optional", "Not final until image QA.", "https://images.example/api-demo.jpg"),
        ),
        pipeline_steps=_base_pipeline_steps(),
        cleanup_rules=(
            "Manual JSON rows normalize to category=Concert and record_type=event.",
            "Unsupported shapes are rejected before records are created.",
            "Blank optional fields remain empty/null in normalized payloads.",
            "Manual records still need admin approval before event creation.",
        ),
        ticket_link_rules=(
            "Classify tickets_link or ticketUrl when supplied.",
            "Generic platform links are flagged for review.",
            "Ticket links should prefer event-specific links over generic platform links.",
        ),
        image_qa_rules=_common_image_qa_rules(),
        venue_poi_rules=_common_venue_poi_rules(),
        compliance_rules=(
            "Manual JSON is a local/demo workbench path.",
            "No external provider calls are made.",
            "Uploaded data should be synthetic, licensed, or internally approved before use.",
        ),
        code_references=_common_code_references(),
        sample_raw={
            "events": [
                {
                    "id": "api-demo-1",
                    "event_name": "API Demo Concert",
                    "headliner": "The API Fixtures",
                    "start_datetime": "2026-09-20T20:00:00-05:00",
                    "venue_name": "API Review Hall",
                    "city": "Memphis",
                    "state": "TN",
                    "tickets_link": "https://tickets.example/api-demo",
                    "main_image_url": "https://images.example/api-demo.jpg",
                }
            ]
        },
        sample_normalized=_sample_normalized(
            ingestion_provider="manual_json",
            upstream_event_source="manual_json",
            ticketing_provider="unknown",
        ),
    )


def _spotify_spec() -> ProviderPipelineSpec:
    return _enrichment_spec(
        provider_key="spotify",
        display_name="Spotify",
        required_env_vars=("SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"),
        request_base="https://api.spotify.com/v1",
        sample_fields={
            "spotify_artist_id": "spotify:artist-demo",
            "spotify_url": "https://open.spotify.com/artist/demo",
            "spotify_artist_name": "The API Fixtures",
            "spotify_image_url": "https://images.example/artist.jpg",
            "match_confidence": 0.92,
        },
        mapping_rows=(
            MappingRow("spotify_artist_id", "spotify_artist_id", "Preserve as enrichment ID.", "optional", "Never primary event ID.", "spotify:artist-demo"),
            MappingRow("spotify_url", "spotify_url", "Preserve as artist enrichment URL.", "optional", "Not a ticket link.", "https://open.spotify.com/artist/demo"),
            MappingRow("spotify_artist_name", "spotify_artist_name", "Use for enrichment match display.", "optional", "Do not overwrite event title blindly.", "The API Fixtures"),
            MappingRow("spotify_image_url", "image candidate", "Stage as candidate only.", "optional", "Artist images are not automatic event images.", "https://images.example/artist.jpg"),
            MappingRow("match confidence", "spotify_match_confidence", "Preserve confidence score.", "optional", "Low confidence requires review.", "0.92"),
        ),
    )


def _serpapi_spec() -> ProviderPipelineSpec:
    return _enrichment_spec(
        provider_key="serpapi",
        display_name="SerpAPI",
        required_env_vars=("SERPAPI_API_KEY",),
        request_base="https://serpapi.com/search.json",
        sample_fields={
            "title": "Synthetic Concert - Tickets",
            "link": "https://tickets.example/api-demo",
            "snippet": "Official event ticket page.",
            "image_url": "https://images.example/search-result.jpg",
            "source_page_url": "https://events.example/api-demo",
            "confidence": 0.81,
            "flags": ["candidate only"],
        },
        mapping_rows=(
            MappingRow("result title/link/snippet", "enrichment suggestions", "Preserve search result context.", "optional", "Suggestions only, not final values.", "Synthetic Concert - Tickets"),
            MappingRow("image result direct URL", "image candidate", "Stage direct image URL only.", "optional", "Image QA still required.", "https://images.example/search-result.jpg"),
            MappingRow("source page URL", "source_url", "Preserve where the suggestion came from.", "optional", "Useful for provenance.", "https://events.example/api-demo"),
            MappingRow("confidence/flags", "enrichment_flags_json", "Preserve score and flags.", "optional", "Low confidence requires review.", "candidate only"),
        ),
    )


def _enrichment_spec(
    provider_key: str,
    display_name: str,
    required_env_vars: tuple[str, ...],
    request_base: str,
    sample_fields: dict[str, object],
    mapping_rows: tuple[MappingRow, ...],
) -> ProviderPipelineSpec:
    return ProviderPipelineSpec(
        provider_key=provider_key,
        display_name=display_name,
        provider_type="enrichment",
        request_preview=RequestPreview(
            method="GET",
            base_url=request_base,
            endpoint="future enrichment endpoint",
            example_url=f"{request_base}?api_key=REDACTED&q=synthetic+concert",
            auth_method="Provider credentials when future live enrichment is intentionally enabled",
            required_env_vars=required_env_vars,
            headers=(),
            query_params=(("api_key", "REDACTED"), ("q", "synthetic concert")),
            body=None,
            pagination_strategy="Provider-specific; enrichment candidates are bounded by reviewed records.",
            rate_limit_notes="No live calls in this milestone.",
            redaction_behavior="Credential values render as REDACTED; env var names only.",
            notes=(
                f"{display_name} is an enrichment provider only.",
                "It is not a primary event feed.",
                "Outputs are suggestions or candidates, not final event fields.",
                "No live calls are made by this workbench page.",
            ),
        ),
        mapping_rows=mapping_rows,
        pipeline_steps=_base_pipeline_steps(),
        cleanup_rules=(
            "Enrichment providers do not create primary Concert events by themselves.",
            "Suggestions attach only to already-reviewed event candidates or venue containers.",
            "Low confidence enrichment remains review-only.",
        ),
        ticket_link_rules=(
            "Enrichment ticket/link suggestions go through ticket-link QA.",
            "Generic app pages and tracking links are flagged instead of accepted blindly.",
            "Event-specific links are preferred over platform homepages or artist pages.",
        ),
        image_qa_rules=_common_image_qa_rules(),
        venue_poi_rules=_common_venue_poi_rules(),
        compliance_rules=(
            "Workbench Open is separate from live enrichment status.",
            "Live Calls Off means this page does not contact the provider.",
            "Credentials are referenced by env var name only and values remain redacted.",
            "Enrichment suggestions are not primary event-source records.",
        ),
        code_references=_common_code_references(),
        sample_raw=sample_fields,
        sample_normalized={
            **_sample_normalized(
                ingestion_provider=provider_key,
                upstream_event_source="reviewed_event_candidate",
                ticketing_provider="unknown",
            ),
            "source_type": "enrichment_suggestion",
            "quality_flags": ["enrichment provider only", "candidate only"],
        },
    )


def _generic_provider_spec(provider: ProviderConfig) -> ProviderPipelineSpec:
    return ProviderPipelineSpec(
        provider_key=provider.provider_key,
        display_name=provider.display_name,
        provider_type=provider.provider_type,
        request_preview=RequestPreview(
            method="N/A",
            base_url="not configured",
            endpoint="not configured",
            example_url="not configured",
            auth_method="not configured",
            required_env_vars=provider.credentials_env_var_names,
            headers=(),
            query_params=(),
            body=None,
            pagination_strategy="not configured",
            rate_limit_notes=provider.rate_limit_notes,
            redaction_behavior="Credential values are not displayed.",
            notes=("Provider pipeline metadata has not been specialized yet.",),
        ),
        mapping_rows=(
            MappingRow(
                "raw provider payload",
                "normalized candidate",
                provider.field_mapping_summary,
                "review required",
                "Specialized mapper needed before production use.",
                "n/a",
            ),
        ),
        pipeline_steps=_base_pipeline_steps(),
        cleanup_rules=("Review provider payloads before adding permanent mapping rules.",),
        ticket_link_rules=(provider.ticket_link_strategy,),
        image_qa_rules=_common_image_qa_rules(),
        venue_poi_rules=_common_venue_poi_rules(),
        compliance_rules=(provider.compliance_notes,),
        code_references=_common_code_references(),
        sample_raw={"provider": provider.provider_key, "demo": True},
        sample_normalized=_sample_normalized(
            ingestion_provider=provider.provider_key,
            upstream_event_source="unknown",
            ticketing_provider="unknown",
        ),
    )


def _sample_normalized(
    ingestion_provider: str,
    upstream_event_source: str,
    ticketing_provider: str,
) -> dict[str, object]:
    return {
        "category": "Concert",
        "record_type": "event",
        "event_name": "Synthetic Provider Concert",
        "headliner": "The API Fixtures",
        "supporting_artists": "Opening Data",
        "start_datetime": "2026-09-20T20:00:00-05:00",
        "end_datetime": "2026-09-20T23:00:00-05:00",
        "timezone": "America/Chicago",
        "venue_name": "API Review Hall",
        "venue_address": "500 Review Ave",
        "city": "Memphis",
        "state": "TN",
        "zip_code": "38103",
        "country": "US",
        "latitude": 35.14,
        "longitude": -90.04,
        "event_url": "https://events.example/api-demo",
        "tickets_link": "https://tickets.example/api-demo",
        "price": "$25",
        "provider_event_type": "Concert",
        "provider_genre": "Americana",
        "source_type": "api_feed",
        "ingestion_provider": ingestion_provider,
        "upstream_event_source": upstream_event_source,
        "ticketing_provider": ticketing_provider,
        "source_chain_json": [
            {"role": "ingestion_provider", "source": ingestion_provider},
            {"role": "upstream_event_source", "source": upstream_event_source},
            {"role": "ticketing_provider", "source": ticketing_provider},
        ],
        "image_candidate_status": "provider candidate - needs approval",
        "ticket_link_classification": "platform_event",
        "quality_flags": ["provider image needs approval"],
    }
