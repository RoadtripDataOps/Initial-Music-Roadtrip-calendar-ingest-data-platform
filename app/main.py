from collections.abc import AsyncIterator, Generator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal, cast

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy.orm import Session
from starlette.datastructures import FormData
from starlette.middleware.sessions import SessionMiddleware

from app.auth.security import (
    admin_template_context,
    is_admin_authenticated,
    login_admin_session,
    logout_admin_session,
    require_admin,
    require_admin_csrf,
    safe_admin_next_path,
    verify_admin_login,
)
from app.core.config import Settings, get_settings
from app.db.database import create_all, make_engine, make_session_factory
from app.db.models import (
    ApiFeedRun,
    BackgroundJobType,
    SourceReviewStatus,
    SourceStatus,
    utc_now,
)
from app.models.source import CalendarSourceCreate, SourceStatusUpdate
from app.services.api_feed_service import (
    CITYSPARK_PROVIDER_KEY,
    ApiFeedRecordFilters,
    approve_api_feed_record,
    get_api_feed_record,
    get_api_feed_run,
    get_provider_config,
    list_api_feed_records,
    list_api_feed_runs,
    provider_display_name,
    provider_registry,
    provider_summaries,
    run_demo_import,
    run_manual_json_import,
    update_api_feed_record_review_status,
)
from app.services.app_feed_service import (
    AppEventFilters,
    AppPoiFilters,
    app_feed_summary,
    create_app_feed_export,
    latest_successful_export,
    list_app_events,
    list_app_pois,
    list_app_venues,
)
from app.services.app_search_service import (
    AppSearchFilters,
    rebuild_search_index,
    search_app_index,
    suggest_app_search,
)
from app.services.artist_service import (
    artist_duplicate_groups,
    get_artist,
    list_artists,
    rebuild_artist_registry,
    upcoming_event_count_for_artist,
)
from app.services.background_job_service import (
    BackgroundJobFilters,
    cancel_job,
    enqueue_due_scheduled_tasks,
    enqueue_job,
    enqueue_scheduled_task_now,
    get_job,
    get_scheduled_task,
    job_status_counts,
    jobs_needing_attention_count,
    list_jobs,
    list_scheduled_tasks,
    next_scheduled_task,
    photo_rescue_jobs_needing_attention_count,
    retry_job,
)
from app.services.bulk_crawl_service import (
    CRAWL_FREQUENCIES,
    MasterSourceFilters,
    crawl_queue_rows,
    due_crawl_rows,
    list_master_source_metadata,
    master_source_ids_for_import_batch,
    metadata_for_master_source,
    pause_selected_sources,
    run_bulk_crawl_for_master_ids,
    update_selected_crawl_frequency,
)
from app.services.cityspark_live_service import (
    CitysparkSandboxContext,
    cityspark_sandbox_context,
    run_cityspark_live_sandbox,
)
from app.services.crawl_service import (
    SourceNotApprovedError,
    SourceNotFoundError,
    fetch_calendar_url,
    get_crawl_run,
    list_crawl_runs,
    run_manual_crawl,
)
from app.services.event_dedupe_service import (
    duplicate_group_view,
    keep_duplicate_group_separate,
    list_duplicate_group_views,
    merge_duplicate_group,
    reject_duplicate_group,
    source_claims_for_event,
)
from app.services.event_photo_rescue_service import (
    create_provider_image_candidates_for_record,
    provider_image_inputs_for_record,
    run_event_photo_rescue,
    run_photo_rescue_for_api_feed_run,
    run_photo_rescue_for_recently_approved_events,
)
from app.services.event_quality_service import (
    EventQualityBulkAction,
    EventQualityFilters,
    apply_event_quality_bulk_action,
    event_quality_dashboard_counts,
    event_quality_workbench,
)
from app.services.event_service import (
    appears_to_be_ics,
    count_events_for_crawl_run,
    get_event,
    list_events,
)
from app.services.extracted_event_service import (
    approve_extracted_event_candidate,
    extracted_candidates_for_crawl_run,
    get_extracted_event_candidate,
    list_extracted_event_candidates,
    reject_extracted_event_candidate,
    send_extracted_event_to_duplicate_review,
)
from app.services.image_qa_service import (
    IMAGE_ROLES,
    ImageCandidateFilters,
    create_image_candidate,
    event_image_badges,
    get_image_candidate,
    is_likely_direct_image_asset,
    list_image_candidates,
    mark_candidate_preflight_result,
    select_best_event_image,
    select_candidate_for_event,
    select_candidate_for_venue,
    set_candidate_clearance,
    update_candidate_review,
    venue_image_badges,
)
from app.services.import_service import (
    CALENDAR_SOURCE_HEADERS,
    CONCERT_EVENT_HEADERS,
    ImportValidationError,
    approve_valid_staged_calendar_sources,
    approve_valid_staged_events,
    csv_template,
    get_import_batch,
    list_import_batches,
    reject_or_quarantine_batch,
    stage_calendar_sources_upload,
    stage_concert_events_upload,
    staged_events_for_batch,
    staged_sources_for_batch,
    xlsx_template,
)
from app.services.itinerary_service import (
    ItineraryCreate,
    ItineraryStopInput,
    ItineraryUpdate,
    add_stop,
    build_itinerary_app_feed,
    build_itinerary_from_artist_events,
    build_itinerary_from_region,
    compute_itinerary_quality,
    create_itinerary,
    get_itinerary,
    itinerary_admin_reference_options,
    itinerary_preview_marker,
    list_app_itineraries,
    list_itineraries,
    move_stop,
    remove_stop,
    update_itinerary,
)
from app.services.jambase_live_service import (
    LIVE_SANDBOX_RUN_MODE,
    JambaseSandboxContext,
    jambase_sandbox_context,
    run_jambase_live_sandbox,
)
from app.services.map_display_service import (
    MapMarkerFilters,
    build_filter_options,
    list_discovery_slots,
    list_map_markers,
)
from app.services.master_calendar_service import (
    CalendarSourcePayload,
    count_master_submissions,
    create_or_attach_master_calendar_source,
    get_master_calendar_source,
    list_master_submissions,
    master_submission_counts,
    update_master_status,
)
from app.services.partner_report_service import (
    export_partner_report_csv,
    export_partner_report_json,
    generate_region_partner_report,
    generate_source_quality_report,
    get_partner_report,
    latest_region_partner_report,
    list_partner_reports,
    region_report_context,
)
from app.services.poi_candidate_service import (
    PoiCandidateFilters,
    approve_candidate_create_poi,
    approve_candidate_update_existing_poi,
    get_poi_candidate,
    link_candidate_to_existing_poi,
    list_candidate_buckets,
    list_poi_candidates,
    mark_candidate_event_venue_only,
    mark_candidate_needs_research,
    poi_candidate_dashboard_counts,
    recompute_candidate_match_quality,
    reject_poi_candidate,
)
from app.services.poi_inventory_export_service import (
    DEFAULT_POI_INVENTORY_OUTPUT_DIR,
    export_current_poi_dedupe_index,
    export_current_poi_inventory,
    export_poi_inventory_manifest,
    get_latest_poi_dedupe_index,
    get_latest_poi_inventory_export,
    get_latest_poi_inventory_manifest,
    get_poi_inventory_export,
    list_poi_inventory_exports,
)
from app.services.poi_registry_service import (
    get_poi_location,
    list_poi_locations,
    poi_duplicate_groups,
)
from app.services.preview_service import (
    VENUE_CATEGORY_OPTIONS,
    VENUE_QUALITY_ISSUES,
    PreviewFilters,
    VenuePreviewFilters,
    event_quality_flags,
    get_preview_event,
    get_preview_venue,
    list_preview_events,
    list_preview_venues,
    maps_url_for_event,
    maps_url_for_venue,
    parse_bool_filter,
    parse_date_filter,
    parse_float_filter,
    preview_events_for_venue,
    previewable_image_url,
    quality_summary,
    reminder_ics_for_event,
    selected_category_option,
    street_url_for_event,
    street_url_for_venue,
    venue_quality_flags,
)
from app.services.provider_http_client import ProviderJsonClient
from app.services.provider_pipeline_service import (
    pipeline_export_json,
    pipeline_export_markdown,
    pretty_json_object,
    provider_pipeline_context,
    record_lineage_context,
)
from app.services.region_service import (
    SearchSeedFilters,
    assign_inferred_regions,
    compute_region_quality_snapshot,
    create_or_update_region,
    get_region,
    latest_region_quality_snapshot,
    list_regions,
    list_search_seed_locations,
    region_events,
    region_extracted_candidate_count,
    region_pois,
    region_source_coverage,
    region_sources,
    seed_search_locations_from_pois,
    seed_search_locations_from_regions,
)
from app.services.risk_service import (
    RiskAssessment,
    SubmissionRiskInput,
    build_assessment,
    hash_signal,
    is_blocked_submission,
    is_trusted_submission,
    record_submission_attempt,
    review_status_for_assessment,
    score_calendar_submission,
    url_domain,
)
from app.services.security_service import (
    PublicUploadSecurityError,
    admin_login_rate_limited,
    combine_security_assessments,
    log_admin_action,
    public_rate_limit_assessment,
    record_public_submission_attempt,
    request_ip,
    request_ip_hash,
    request_user_agent_hash,
    security_dashboard_context,
    validate_public_upload_file,
    verify_turnstile_token,
)
from app.services.source_quality_service import (
    SourceQualityFilters,
    compute_all_source_quality,
    compute_source_quality_for_api_provider,
    compute_source_quality_for_master_source,
    compute_source_quality_for_partner,
    compute_source_quality_for_region,
    get_source_quality_score,
    list_source_quality_scores,
    source_quality_dashboard_summary,
)
from app.services.source_service import (
    create_calendar_source,
    list_calendar_sources,
    list_suspicious_calendar_sources,
    review_calendar_source,
    update_source_status,
)
from app.services.source_taxonomy_service import source_display_name, source_docs_status

templates = Jinja2Templates(directory="app/web/templates")
DEMO_ICS_PATH = Path("tests/fixtures/sample_calendar.ics")
DEMO_JSONLD_PATH = Path("tests/fixtures/sample_event_jsonld.html")
DEMO_RSS_PATH = Path("tests/fixtures/sample_events.rss")
DEMO_HTML_PATH = Path("tests/fixtures/sample_event_cards.html")


def get_db(request: Request) -> Generator[Session]:
    """Yield one database session for a request."""

    session_factory = request.app.state.SessionLocal
    with session_factory() as session:
        yield session


def validation_error_map(error: ValidationError) -> dict[str, str]:
    """Convert Pydantic errors into template-friendly field messages."""

    messages: dict[str, str] = {}
    for item in error.errors():
        field = str(item["loc"][0])
        messages[field] = str(item["msg"]).removeprefix("Value error, ")
    return messages


def parse_form_rendered_at(value: str | None) -> datetime | None:
    """Parse hidden form-render timestamp, ignoring malformed values."""

    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def score_upload_trust_gate(
    db: Session,
    request: Request,
    contact_email: str,
    honeypot_value: str,
    form_rendered_at_value: str,
) -> RiskAssessment:
    """Score public upload anti-abuse signals before admin review."""

    settings = request.app.state.settings
    submitted_at = utc_now()
    flags: list[str] = []
    score = 0

    if honeypot_value.strip():
        score += 85
        flags.append("honeypot_filled")

    form_rendered_at = parse_form_rendered_at(form_rendered_at_value)
    if form_rendered_at is not None:
        elapsed = (submitted_at - form_rendered_at).total_seconds()
        if elapsed < settings.minimum_form_seconds:
            score += 50
            flags.append("submitted_too_fast")

    upload_signal_url = "https://file-upload.local/submission"
    if is_blocked_submission(db, contact_email, upload_signal_url):
        score += 80
        flags.append("blocked_submitter_or_domain")
    if is_trusted_submission(db, contact_email, upload_signal_url):
        score -= 20
        flags.append("trusted_submitter_or_domain")

    rate_assessment = public_rate_limit_assessment(
        db,
        settings=settings,
        route=request.url.path,
        contact_email=contact_email,
        submitted_url=upload_signal_url,
        ip_hash=request_ip_hash(request, settings),
        user_agent_hash=request_user_agent_hash(request, settings),
    )
    return combine_security_assessments(build_assessment(score, flags), rate_assessment)


def turnstile_public_assessment(
    request: Request,
    turnstile_token: str,
) -> RiskAssessment:
    """Return a blocking assessment when Turnstile is enabled and invalid."""

    settings = request.app.state.settings
    verifier = getattr(request.app.state, "turnstile_verifier", None)
    result = verify_turnstile_token(
        turnstile_token,
        request_ip_value=request_ip(request),
        settings=settings,
        verifier=verifier,
    )
    if result.success:
        return build_assessment(0, [])
    return build_assessment(90, [result.reason or "turnstile_token_invalid"])


def public_form_context(
    request: Request,
    context: dict[str, object],
) -> dict[str, object]:
    settings = request.app.state.settings
    return {
        **context,
        "turnstile_enabled": settings.turnstile_enabled,
        "turnstile_site_key": settings.turnstile_site_key,
    }


def template_download(
    content: str | bytes,
    filename: str,
    media_type: str,
) -> Response:
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def parse_bool_query(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def parse_optional_bool_query(value: str | None) -> bool | None:
    if value is None or not value.strip():
        return None
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    return None


def parse_int_query(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def parse_datetime_query(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def app_event_filters_from_values(
    event_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    city: str | None = None,
    state_value: str | None = None,
    country: str | None = None,
    genre: str | None = None,
    venue_id: str | None = None,
    poi_id: str | None = None,
    include_cancelled: str | None = None,
    include_needs_approval: str | None = "true",
    limit: str | None = None,
    offset: str | None = None,
) -> AppEventFilters:
    return AppEventFilters(
        event_id=parse_int_query(event_id),
        date_from=parse_date_filter(date_from),
        date_to=parse_date_filter(date_to),
        city=city or None,
        state=state_value or None,
        country=country or None,
        genre=genre or None,
        venue_id=parse_int_query(venue_id),
        poi_id=poi_id or None,
        include_cancelled=parse_bool_query(include_cancelled),
        include_needs_approval=not (
            include_needs_approval
            and include_needs_approval.strip().lower() in {"0", "false", "no", "off"}
        ),
        limit=parse_int_query(limit) or 100,
        offset=parse_int_query(offset) or 0,
    )


def app_poi_filters_from_values(
    category: str | None = None,
    subcategory: str | None = None,
    city: str | None = None,
    state_value: str | None = None,
    country: str | None = None,
    has_upcoming_events: str | None = None,
    limit: str | None = None,
    offset: str | None = None,
) -> AppPoiFilters:
    return AppPoiFilters(
        category=category or None,
        subcategory=subcategory or None,
        city=city or None,
        state=state_value or None,
        country=country or None,
        has_upcoming_events=parse_bool_query(has_upcoming_events),
        limit=parse_int_query(limit) or 100,
        offset=parse_int_query(offset) or 0,
    )


def app_search_filters_from_values(
    entity_type: str | None = None,
    category: str | None = None,
    subcategory: str | None = None,
    region_id: str | None = None,
    city: str | None = None,
    state_value: str | None = None,
    country: str | None = None,
    app_feed_ready: str | None = None,
    certified: str | None = None,
) -> AppSearchFilters:
    return AppSearchFilters(
        entity_type=entity_type or None,
        category=category or None,
        subcategory=subcategory or None,
        region_id=parse_int_query(region_id),
        city=city or None,
        state=state_value or None,
        country=country or None,
        app_feed_ready=parse_optional_bool_query(app_feed_ready),
        certified=parse_optional_bool_query(certified),
    )


def map_marker_filters_from_values(
    entity_type: str | None = None,
    category: str | None = None,
    subcategory: str | None = None,
    region_id: str | None = None,
    city: str | None = None,
    state_value: str | None = None,
    country: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    has_upcoming_events: str | None = None,
    certified: str | None = None,
    limit: str | None = None,
    offset: str | None = None,
) -> MapMarkerFilters:
    return MapMarkerFilters(
        entity_type=entity_type or None,
        category=category or None,
        subcategory=subcategory or None,
        region_id=parse_int_query(region_id),
        city=city or None,
        state=state_value or None,
        country=country or None,
        date_from=parse_date_filter(date_from),
        date_to=parse_date_filter(date_to),
        has_upcoming_events=parse_optional_bool_query(has_upcoming_events),
        certified=parse_optional_bool_query(certified),
        limit=parse_int_query(limit) or 250,
        offset=parse_int_query(offset) or 0,
    )


def master_source_filters_from_values(
    status_value: str | None = None,
    review_status: str | None = None,
    crawl_frequency: str | None = None,
    city: str | None = None,
    state_value: str | None = None,
    region_or_market: str | None = None,
    source_type: str | None = None,
    organization: str | None = None,
    last_crawl_status: str | None = None,
    due_for_crawl: str | None = None,
    risk_level: str | None = None,
) -> MasterSourceFilters:
    return MasterSourceFilters(
        status=status_value or None,
        review_status=review_status or None,
        crawl_frequency=crawl_frequency or None,
        city=city or None,
        state=state_value or None,
        region_or_market=region_or_market or None,
        source_type=source_type or None,
        organization=organization or None,
        last_crawl_status=last_crawl_status or None,
        due_for_crawl=parse_bool_query(due_for_crawl),
        risk_level=risk_level or None,
    )


def selected_source_ids_from_form(form: FormData) -> list[int]:
    values = form.getlist("source_ids")
    parsed: list[int] = []
    for value in values:
        try:
            parsed.append(int(str(value)))
        except ValueError:
            continue
    return parsed


def selected_event_ids_from_form(form: FormData) -> list[int]:
    values = form.getlist("event_ids")
    parsed: list[int] = []
    for value in values:
        try:
            parsed.append(int(str(value)))
        except ValueError:
            continue
    return parsed


def job_filters_from_values(
    status_value: str | None = None,
    job_type: str | None = None,
    queue_name: str | None = None,
) -> BackgroundJobFilters:
    return BackgroundJobFilters(
        status=status_value or None,
        job_type=job_type or None,
        queue_name=queue_name or None,
    )


def scalar_form_values(form: FormData) -> dict[str, object]:
    values: dict[str, object] = {}
    for key, value in form.multi_items():
        if key == "csrf_token":
            continue
        values[key] = str(value)
    return values


LiveSandboxContext = JambaseSandboxContext | CitysparkSandboxContext


def live_sandbox_context_for_provider(
    settings: Settings,
    provider_key: str,
) -> LiveSandboxContext:
    if provider_key == "jambase":
        return jambase_sandbox_context(settings)
    if provider_key == CITYSPARK_PROVIDER_KEY:
        return cityspark_sandbox_context(settings)
    raise ValueError("Live sandbox is only available for licensed event feeds.")


def live_sandbox_recent_runs(
    db: Session,
    provider_key: str,
) -> list[ApiFeedRun]:
    return [
        run
        for run in list_api_feed_runs(db, provider_key)
        if run.run_mode == LIVE_SANDBOX_RUN_MODE
    ][:10]


def api_record_filters_from_values(
    provider_key: str | None = None,
    ingestion_provider: str | None = None,
    upstream_event_source: str | None = None,
    ticketing_provider: str | None = None,
    ticket_link_classification: str | None = None,
    ticket_link_repair_strategy: str | None = None,
    provenance_flag: str | None = None,
    review_status: str | None = None,
    normalization_status: str | None = None,
    quality_issue: str | None = None,
    duplicate_status: str | None = None,
    missing_image: str | None = None,
    missing_ticket_link: str | None = None,
    missing_venue: str | None = None,
    compliance_expiring_soon: str | None = None,
    unknown_upstream_source: str | None = None,
    api_backfill_required: str | None = None,
    min_event_relevance_score: str | None = None,
    min_photo_quality_score: str | None = None,
) -> ApiFeedRecordFilters:
    def parse_score(value: str | None) -> float | None:
        if not value:
            return None
        try:
            return float(value)
        except ValueError:
            return None

    return ApiFeedRecordFilters(
        provider_key=provider_key or None,
        ingestion_provider=ingestion_provider or None,
        upstream_event_source=upstream_event_source or None,
        ticketing_provider=ticketing_provider or None,
        ticket_link_classification=ticket_link_classification or None,
        ticket_link_repair_strategy=ticket_link_repair_strategy or None,
        provenance_flag=provenance_flag or None,
        review_status=review_status or None,
        normalization_status=normalization_status or None,
        quality_issue=quality_issue or None,
        duplicate_status=duplicate_status or None,
        missing_image=parse_bool_query(missing_image),
        missing_ticket_link=parse_bool_query(missing_ticket_link),
        missing_venue=parse_bool_query(missing_venue),
        compliance_expiring_soon=parse_bool_query(compliance_expiring_soon),
        unknown_upstream_source=parse_bool_query(unknown_upstream_source),
        api_backfill_required=parse_bool_query(api_backfill_required),
        min_event_relevance_score=parse_score(min_event_relevance_score),
        min_photo_quality_score=parse_score(min_photo_quality_score),
    )


def image_candidate_filters_from_values(
    event_id: str | None = None,
    venue_id: str | None = None,
    source_type: str | None = None,
    source_provider: str | None = None,
    candidate_status: str | None = None,
    clearance_status: str | None = None,
    image_role: str | None = None,
    quality_flag: str | None = None,
    stock_placeholder_candidate: str | None = None,
    text_detected: str | None = None,
    watermark_detected: str | None = None,
    poster_or_flyer: str | None = None,
    missing_dimensions: str | None = None,
    low_resolution: str | None = None,
    needs_approval: str | None = None,
    selected: str | None = None,
    selected_pending_approval: str | None = None,
    selected_and_cleared: str | None = None,
    selected_but_needs_approval: str | None = None,
    hard_blocked: str | None = None,
    missing_image: str | None = None,
    rescue_source: str | None = None,
    source_evidence_only: str | None = None,
    can_be_final_image: str | None = None,
    selected_by_rescue: str | None = None,
    missing_artist_image: str | None = None,
) -> ImageCandidateFilters:
    def parse_int(value: str | None) -> int | None:
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    selected_filter: bool | None = None
    if selected == "1":
        selected_filter = True
    if selected == "0":
        selected_filter = False
    final_filter: bool | None = None
    if can_be_final_image == "1":
        final_filter = True
    if can_be_final_image == "0":
        final_filter = False

    return ImageCandidateFilters(
        event_id=parse_int(event_id),
        venue_id=parse_int(venue_id),
        source_type=source_type or None,
        source_provider=source_provider or None,
        candidate_status=candidate_status or None,
        clearance_status=clearance_status or None,
        image_role=image_role or None,
        quality_flag=quality_flag or None,
        stock_placeholder_candidate=parse_bool_query(stock_placeholder_candidate),
        text_detected=parse_bool_query(text_detected),
        watermark_detected=parse_bool_query(watermark_detected),
        poster_or_flyer=parse_bool_query(poster_or_flyer),
        missing_dimensions=parse_bool_query(missing_dimensions),
        low_resolution=parse_bool_query(low_resolution),
        needs_approval=parse_bool_query(needs_approval),
        selected=selected_filter,
        selected_pending_approval=parse_bool_query(selected_pending_approval),
        selected_and_cleared=parse_bool_query(selected_and_cleared),
        selected_but_needs_approval=parse_bool_query(selected_but_needs_approval),
        hard_blocked=parse_bool_query(hard_blocked),
        missing_image=parse_bool_query(missing_image),
        rescue_source=rescue_source or None,
        source_evidence_only=parse_bool_query(source_evidence_only),
        can_be_final_image=final_filter,
        selected_by_rescue=parse_bool_query(selected_by_rescue),
        missing_artist_image=parse_bool_query(missing_artist_image),
    )


def admin_template_response(
    request: Request,
    template_name: str,
    context: dict[str, object],
    status_code: int = status.HTTP_200_OK,
) -> Response:
    return templates.TemplateResponse(
        request,
        template_name,
        {**context, **admin_template_context(request)},
        status_code=status_code,
    )


def require_private_app_feed_access(request: Request) -> None:
    settings = request.app.state.settings
    if settings.app_feed_public:
        return
    if is_admin_authenticated(request):
        return
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="App feed API is private.",
    )


def poi_inventory_output_dir(request: Request) -> Path:
    configured = getattr(
        request.app.state,
        "poi_inventory_output_dir",
        DEFAULT_POI_INVENTORY_OUTPUT_DIR,
    )
    return Path(configured)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI app."""

    settings = settings or get_settings()
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        create_all(engine)
        yield

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.mount(
        "/static",
        StaticFiles(directory="app/web/static"),
        name="static",
    )
    configured_same_site = settings.admin_cookie_samesite.strip().lower()
    if configured_same_site not in {"lax", "strict", "none"}:
        configured_same_site = "lax"
    session_same_site = cast(Literal["lax", "strict", "none"], configured_same_site)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.effective_session_secret_key,
        session_cookie="calendar_ingest_admin",
        same_site=session_same_site,
        https_only=settings.is_production,
        max_age=60 * settings.admin_session_timeout_minutes,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.SessionLocal = session_factory
    app.state.fetch_calendar_url = lambda url: fetch_calendar_url(url, settings)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/dev/sample-calendar.ics")
    def dev_sample_calendar() -> Response:
        """Development-only demo ICS feed for local POC testing."""

        if settings.is_production:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Development demo calendar is not available.",
            )
        if not DEMO_ICS_PATH.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Sample ICS fixture not found.",
            )
        return Response(
            content=DEMO_ICS_PATH.read_text(encoding="utf-8"),
            media_type="text/calendar",
        )

    @app.get("/dev/sample-jsonld-event.html")
    def dev_sample_jsonld_event() -> Response:
        """Development-only static JSON-LD Event page for local extraction demos."""

        if settings.is_production:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Development demo page is not available.",
            )
        if not DEMO_JSONLD_PATH.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Sample JSON-LD fixture not found.",
            )
        return Response(
            content=DEMO_JSONLD_PATH.read_text(encoding="utf-8"),
            media_type="text/html",
        )

    @app.get("/dev/sample-events.rss")
    def dev_sample_events_rss() -> Response:
        """Development-only RSS feed for local extraction demos."""

        if settings.is_production:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Development demo feed is not available.",
            )
        if not DEMO_RSS_PATH.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Sample RSS fixture not found.",
            )
        return Response(
            content=DEMO_RSS_PATH.read_text(encoding="utf-8"),
            media_type="application/rss+xml",
        )

    @app.get("/dev/sample-event-cards.html")
    def dev_sample_event_cards() -> Response:
        """Development-only static HTML event-card page for local demos."""

        if settings.is_production:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Development demo page is not available.",
            )
        if not DEMO_HTML_PATH.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Sample HTML fixture not found.",
            )
        return Response(
            content=DEMO_HTML_PATH.read_text(encoding="utf-8"),
            media_type="text/html",
        )

    @app.get("/admin/login", response_class=HTMLResponse)
    def admin_login_form(
        request: Request,
        next_path: str = "/admin/dashboard",
    ) -> Response:
        return templates.TemplateResponse(
            request,
            "admin_login.html",
            {
                "page_title": "Admin Login",
                "next_path": safe_admin_next_path(next_path),
                "error": "",
            },
        )

    @app.post("/admin/login", response_class=HTMLResponse)
    def admin_login(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        username: Annotated[str, Form(...)],
        password: Annotated[str, Form(...)],
        next_path: Annotated[str, Form(alias="next")] = "/admin/dashboard",
    ) -> Response:
        if admin_login_rate_limited(db, settings=settings, request=request):
            log_admin_action(
                db,
                settings=settings,
                request=request,
                actor_username=username,
                action="login_rate_limited",
                target_type="admin_session",
                metadata={"username": username},
            )
            return templates.TemplateResponse(
                request,
                "admin_login.html",
                {
                    "page_title": "Admin Login",
                    "next_path": safe_admin_next_path(next_path),
                    "error": "Too many failed login attempts. Try again later.",
                },
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        if verify_admin_login(settings, username, password):
            login_admin_session(request, username)
            log_admin_action(
                db,
                settings=settings,
                request=request,
                actor_username=username,
                action="login_success",
                target_type="admin_session",
                metadata={"next": safe_admin_next_path(next_path)},
            )
            return RedirectResponse(
                url=safe_admin_next_path(next_path),
                status_code=status.HTTP_303_SEE_OTHER,
            )
        log_admin_action(
            db,
            settings=settings,
            request=request,
            actor_username=username,
            action="login_failure",
            target_type="admin_session",
            metadata={"username": username},
        )
        return templates.TemplateResponse(
            request,
            "admin_login.html",
            {
                "page_title": "Admin Login",
                "next_path": safe_admin_next_path(next_path),
                "error": "Invalid admin username or password.",
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    @app.post("/admin/logout")
    def admin_logout(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        log_admin_action(
            db,
            settings=settings,
            request=request,
            actor_username=admin_user,
            action="logout",
            target_type="admin_session",
        )
        logout_admin_session(request)
        return RedirectResponse(
            url="/admin/login",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request) -> Response:
        return templates.TemplateResponse(
            request,
            "home.html",
            {"page_title": "Home"},
        )

    @app.get("/submit-calendar", response_class=HTMLResponse)
    def submit_calendar_form(request: Request) -> Response:
        return templates.TemplateResponse(
            request,
            "submit_calendar.html",
            public_form_context(request, {
                "page_title": "Submit Calendar",
                "form_rendered_at": utc_now().isoformat(),
                "errors": {},
                "values": {},
            }),
        )

    @app.get("/submit-concerts", response_class=HTMLResponse)
    def submit_concerts_form(request: Request) -> Response:
        return RedirectResponse(
            url="/submit-events",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.get("/submit-events", response_class=HTMLResponse)
    def submit_events_form(request: Request) -> Response:
        return templates.TemplateResponse(
            request,
            "submit_concerts.html",
            public_form_context(request, {
                "page_title": "Submit Events",
                "form_rendered_at": utc_now().isoformat(),
                "errors": {},
                "values": {},
            }),
        )

    @app.get("/submit-concerts/calendar", response_class=HTMLResponse)
    @app.get("/submit-concerts/calendar-url", response_class=HTMLResponse)
    def submit_concerts_calendar_form(request: Request) -> Response:
        return RedirectResponse(
            url="/submit-calendar/url",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.get("/submit-calendar/url", response_class=HTMLResponse)
    def submit_calendar_url_form(request: Request) -> Response:
        return templates.TemplateResponse(
            request,
            "submit_concerts_calendar.html",
            public_form_context(request, {
                "page_title": "Submit Calendar URL",
                "form_action": "/submit-calendar/url",
                "form_rendered_at": utc_now().isoformat(),
                "errors": {},
                "values": {},
            }),
        )

    @app.get("/submit-concerts/events-file", response_class=HTMLResponse)
    def submit_concert_events_file_form(request: Request) -> Response:
        return RedirectResponse(
            url="/submit-events/file",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.get("/submit-events/file", response_class=HTMLResponse)
    def submit_events_file_form(request: Request) -> Response:
        return templates.TemplateResponse(
            request,
            "submit_concerts_events_file.html",
            public_form_context(request, {
                "page_title": "Upload Events",
                "form_action": "/submit-events/file",
                "form_rendered_at": utc_now().isoformat(),
                "errors": {},
                "values": {},
            }),
        )

    @app.get("/submit-concerts/calendar-sources-file", response_class=HTMLResponse)
    def submit_calendar_sources_file_form(request: Request) -> Response:
        return RedirectResponse(
            url="/submit-calendar/sources-file",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.get("/submit-calendar/sources-file", response_class=HTMLResponse)
    def submit_calendar_sources_file_landing(request: Request) -> Response:
        return templates.TemplateResponse(
            request,
            "submit_concerts_calendar_sources_file.html",
            public_form_context(request, {
                "page_title": "Upload Calendar Sources",
                "form_action": "/submit-calendar/sources-file",
                "form_rendered_at": utc_now().isoformat(),
                "errors": {},
                "values": {},
            }),
        )

    @app.post("/submit-calendar/url", response_class=HTMLResponse)
    @app.post("/submit-concerts/calendar", response_class=HTMLResponse)
    @app.post("/submit-concerts/calendar-url", response_class=HTMLResponse)
    @app.post("/submit-concerts", response_class=HTMLResponse)
    @app.post("/submit-calendar", response_class=HTMLResponse)
    def submit_calendar(
        request: Request,
        organization_name: Annotated[str, Form(...)],
        calendar_url: Annotated[str, Form(...)],
        contact_email: Annotated[str, Form(...)],
        db: Annotated[Session, Depends(get_db)],
        contact_name: Annotated[str, Form()] = "",
        calendar_name: Annotated[str, Form()] = "",
        city: Annotated[str, Form()] = "",
        state_value: Annotated[str, Form(alias="state")] = "",
        country: Annotated[str, Form()] = "",
        region_or_market: Annotated[str, Form()] = "",
        crawl_frequency: Annotated[str, Form()] = "",
        notes: Annotated[str, Form()] = "",
        permission_confirmed: Annotated[bool, Form()] = False,
        authorization_checkbox: Annotated[bool, Form()] = False,
        honeypot_value: Annotated[str, Form(alias="website")] = "",
        form_rendered_at_value: Annotated[str, Form(alias="form_rendered_at")] = "",
        cf_turnstile_response: Annotated[
            str,
            Form(alias="cf-turnstile-response"),
        ] = "",
    ) -> Response:
        authorization_confirmed = permission_confirmed or authorization_checkbox
        submitted_via = request.url.path.strip("/") or "submit-calendar"
        values = {
            "organization_name": organization_name,
            "calendar_url": calendar_url,
            "contact_email": contact_email,
            "contact_name": contact_name,
            "calendar_name": calendar_name,
            "city": city,
            "state": state_value,
            "country": country,
            "region_or_market": region_or_market,
            "crawl_frequency": crawl_frequency,
            "notes": notes,
            "permission_confirmed": authorization_confirmed,
            "website": honeypot_value,
            "form_rendered_at": form_rendered_at_value,
        }
        try:
            submission = CalendarSourceCreate(**values)
        except ValidationError as exc:
            return templates.TemplateResponse(
                request,
                "submit_concerts_calendar.html",
                public_form_context(request, {
                    "page_title": "Submit Calendar",
                    "form_action": request.url.path,
                    "form_rendered_at": utc_now().isoformat(),
                    "errors": validation_error_map(exc),
                    "values": values,
                }),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        submitted_at = utc_now()
        settings_for_risk = request.app.state.settings
        client_host = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")
        submitted_ip_hash = hash_signal(client_host, settings_for_risk.risk_hash_salt)
        submitted_user_agent_hash = hash_signal(
            user_agent,
            settings_for_risk.risk_hash_salt,
        )
        risk_input = SubmissionRiskInput(
            organization_name=submission.organization_name,
            contact_email=submission.contact_email,
            calendar_url=submission.calendar_url,
            permission_confirmed=submission.permission_confirmed,
            honeypot_value=honeypot_value,
            form_rendered_at=parse_form_rendered_at(form_rendered_at_value),
            submitted_at=submitted_at,
            submitted_ip_hash=submitted_ip_hash,
            submitted_user_agent_hash=submitted_user_agent_hash,
            settings=settings_for_risk,
            submission_type=submitted_via,
        )
        assessment, duplicate_source = score_calendar_submission(db, risk_input)
        turnstile_assessment = turnstile_public_assessment(
            request,
            cf_turnstile_response,
        )
        assessment = combine_security_assessments(assessment, turnstile_assessment)
        review_status = SourceReviewStatus(
            review_status_for_assessment(assessment)
        )
        source = create_calendar_source(
            db,
            submission,
            risk_assessment=assessment,
            review_status=review_status,
            submitted_ip_hash=submitted_ip_hash,
            submitted_user_agent_hash=submitted_user_agent_hash,
            submitted_domain=url_domain(submission.calendar_url),
            claimed_source_id=duplicate_source.id if duplicate_source else None,
            form_rendered_at=risk_input.form_rendered_at,
            submitted_via=submitted_via,
        )
        if turnstile_assessment.risk_level == "blocked":
            record_submission_attempt(
                db,
                submission_type=submitted_via,
                risk_input=risk_input,
                assessment=assessment,
                was_invalid=True,
            )
            return templates.TemplateResponse(
                request,
                "submit_concerts_calendar.html",
                public_form_context(request, {
                    "page_title": "Submit Calendar",
                    "form_action": request.url.path,
                    "form_rendered_at": utc_now().isoformat(),
                    "errors": {
                        "turnstile": (
                            "Submission could not be accepted. Please try again."
                        ),
                    },
                    "values": values,
                }),
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        master, _claim, _created = create_or_attach_master_calendar_source(
            db,
            CalendarSourcePayload(
                organization_name=submission.organization_name,
                contact_name=contact_name or None,
                contact_email=submission.contact_email,
                calendar_name=calendar_name or None,
                calendar_url=submission.calendar_url,
                source_type="single_calendar_url",
                expected_category="Concert",
                city=city or None,
                state=state_value or None,
                country=country or None,
                region_or_market=region_or_market or None,
                crawl_frequency=crawl_frequency or None,
                authorization_confirmed=submission.permission_confirmed,
                notes=notes or None,
            ),
            assessment,
            review_status.value,
        )
        record_submission_attempt(
            db,
            submission_type=submitted_via,
            risk_input=risk_input,
            assessment=assessment,
        )
        return RedirectResponse(
            url=(
                f"/submit-calendar/thanks?source_id={source.id}"
                f"&master_source_id={master.id}"
            ),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.get("/submit-calendar/thanks", response_class=HTMLResponse)
    @app.get("/submit-events/thanks", response_class=HTMLResponse)
    def submit_calendar_thanks(
        request: Request,
        source_id: int | None = None,
        master_source_id: int | None = None,
        batch_id: int | None = None,
        submission_kind: str = "calendar",
    ) -> Response:
        return templates.TemplateResponse(
            request,
            "submit_success.html",
            {
                "page_title": "Submission Received",
                "source_id": source_id,
                "master_source_id": master_source_id,
                "batch_id": batch_id,
                "submission_kind": submission_kind,
            },
        )

    @app.get("/templates/calendar-sources-template.csv")
    def calendar_sources_template_csv() -> Response:
        return template_download(
            csv_template(CALENDAR_SOURCE_HEADERS),
            "calendar-sources-template.csv",
            "text/csv",
        )

    @app.get("/templates/calendar-sources-template.xlsx")
    def calendar_sources_template_xlsx() -> Response:
        return template_download(
            xlsx_template(CALENDAR_SOURCE_HEADERS),
            "calendar-sources-template.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    @app.get("/templates/concert-events-template.csv")
    def concert_events_template_csv() -> Response:
        return template_download(
            csv_template(CONCERT_EVENT_HEADERS),
            "concert-events-template.csv",
            "text/csv",
        )

    @app.get("/templates/events-template.csv")
    def events_template_csv() -> Response:
        return template_download(
            csv_template(CONCERT_EVENT_HEADERS),
            "events-template.csv",
            "text/csv",
        )

    @app.get("/templates/concert-events-template.xlsx")
    def concert_events_template_xlsx() -> Response:
        return template_download(
            xlsx_template(CONCERT_EVENT_HEADERS),
            "concert-events-template.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    @app.get("/templates/events-template.xlsx")
    def events_template_xlsx() -> Response:
        return template_download(
            xlsx_template(CONCERT_EVENT_HEADERS),
            "events-template.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    @app.post("/submit-events/file")
    @app.post("/submit-concerts/events-file")
    @app.post("/submit-concerts/concert-events-file")
    async def submit_concert_events_file(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        organization_name: Annotated[str, Form(...)],
        contact_email: Annotated[str, Form(...)],
        upload_file: Annotated[UploadFile | None, File()] = None,
        uploaded_file: Annotated[UploadFile | None, File()] = None,
        contact_name: Annotated[str, Form()] = "",
        notes: Annotated[str, Form()] = "",
        authorization_checkbox: Annotated[bool, Form()] = False,
        permission_confirmed: Annotated[bool, Form()] = False,
        honeypot_value: Annotated[str, Form(alias="website")] = "",
        form_rendered_at_value: Annotated[str, Form(alias="form_rendered_at")] = "",
        cf_turnstile_response: Annotated[
            str,
            Form(alias="cf-turnstile-response"),
        ] = "",
    ) -> Response:
        selected_file = uploaded_file or upload_file
        if selected_file is None:
            return templates.TemplateResponse(
                request,
                "submit_concerts_events_file.html",
                public_form_context(request, {
                    "page_title": "Upload Events",
                    "form_action": request.url.path,
                    "form_rendered_at": utc_now().isoformat(),
                    "errors": {"concert_events_file": "File upload is required."},
                    "values": {
                        "organization_name": organization_name,
                        "contact_name": contact_name,
                        "contact_email": contact_email,
                        "notes": notes,
                    },
                }),
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        content = await selected_file.read()
        gate_assessment = score_upload_trust_gate(
            db,
            request,
            contact_email,
            honeypot_value,
            form_rendered_at_value,
        )
        turnstile_assessment = turnstile_public_assessment(
            request,
            cf_turnstile_response,
        )
        gate_assessment = combine_security_assessments(
            gate_assessment,
            turnstile_assessment,
        )
        upload_signal_url = "https://file-upload.local/submission"
        ip_hash = request_ip_hash(request, request.app.state.settings)
        user_agent_hash = request_user_agent_hash(request, request.app.state.settings)
        try:
            validate_public_upload_file(
                selected_file.filename,
                content,
                request.app.state.settings,
            )
        except PublicUploadSecurityError as exc:
            file_assessment = combine_security_assessments(
                gate_assessment,
                build_assessment(80, ["file_upload_rejected"]),
            )
            record_public_submission_attempt(
                db,
                submission_type=request.url.path,
                contact_email=contact_email,
                submitted_url=upload_signal_url,
                ip_hash=ip_hash,
                user_agent_hash=user_agent_hash,
                assessment=file_assessment,
                was_invalid=True,
            )
            return templates.TemplateResponse(
                request,
                "submit_concerts_events_file.html",
                public_form_context(request, {
                    "page_title": "Upload Events",
                    "form_action": request.url.path,
                    "form_rendered_at": utc_now().isoformat(),
                    "errors": {"concert_events_file": str(exc)},
                    "values": {
                        "organization_name": organization_name,
                        "contact_name": contact_name,
                        "contact_email": contact_email,
                        "notes": notes,
                    },
                }),
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        if turnstile_assessment.risk_level == "blocked":
            record_public_submission_attempt(
                db,
                submission_type=request.url.path,
                contact_email=contact_email,
                submitted_url=upload_signal_url,
                ip_hash=ip_hash,
                user_agent_hash=user_agent_hash,
                assessment=gate_assessment,
                was_invalid=True,
            )
            return templates.TemplateResponse(
                request,
                "submit_concerts_events_file.html",
                public_form_context(request, {
                    "page_title": "Upload Events",
                    "form_action": request.url.path,
                    "form_rendered_at": utc_now().isoformat(),
                    "errors": {
                        "concert_events_file": (
                            "Submission could not be accepted. Please try again."
                        ),
                    },
                    "values": {
                        "organization_name": organization_name,
                        "contact_name": contact_name,
                        "contact_email": contact_email,
                        "notes": notes,
                    },
                }),
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        try:
            batch = stage_concert_events_upload(
                db,
                organization_name=organization_name,
                contact_name=contact_name,
                contact_email=contact_email,
                filename=selected_file.filename or "events-upload",
                content=content,
                notes=notes or None,
                gate_assessment=gate_assessment,
                max_rows=request.app.state.settings.public_file_upload_max_rows,
            )
        except ImportValidationError as exc:
            record_public_submission_attempt(
                db,
                submission_type=request.url.path,
                contact_email=contact_email,
                submitted_url=upload_signal_url,
                ip_hash=ip_hash,
                user_agent_hash=user_agent_hash,
                assessment=combine_security_assessments(
                    gate_assessment,
                    build_assessment(50, ["file_upload_parse_rejected"]),
                ),
                was_invalid=True,
            )
            return templates.TemplateResponse(
                request,
                "submit_concerts_events_file.html",
                public_form_context(request, {
                    "page_title": "Upload Events",
                    "form_action": request.url.path,
                    "form_rendered_at": utc_now().isoformat(),
                    "errors": {"concert_events_file": str(exc)},
                    "values": {
                        "organization_name": organization_name,
                        "contact_name": contact_name,
                        "contact_email": contact_email,
                        "notes": notes,
                    },
                }),
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        record_public_submission_attempt(
            db,
            submission_type=request.url.path,
            contact_email=contact_email,
            submitted_url=upload_signal_url,
            ip_hash=ip_hash,
            user_agent_hash=user_agent_hash,
            assessment=gate_assessment,
            was_invalid=False,
        )
        return RedirectResponse(
            url=f"/submit-events/thanks?batch_id={batch.id}&submission_kind=events",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/submit-calendar/sources-file")
    @app.post("/submit-concerts/calendar-sources-file")
    async def submit_calendar_sources_file(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        organization_name: Annotated[str, Form(...)],
        contact_email: Annotated[str, Form(...)],
        upload_file: Annotated[UploadFile | None, File()] = None,
        uploaded_file: Annotated[UploadFile | None, File()] = None,
        contact_name: Annotated[str, Form()] = "",
        notes: Annotated[str, Form()] = "",
        authorization_checkbox: Annotated[bool, Form()] = False,
        permission_confirmed: Annotated[bool, Form()] = False,
        honeypot_value: Annotated[str, Form(alias="website")] = "",
        form_rendered_at_value: Annotated[str, Form(alias="form_rendered_at")] = "",
        cf_turnstile_response: Annotated[
            str,
            Form(alias="cf-turnstile-response"),
        ] = "",
    ) -> Response:
        selected_file = uploaded_file or upload_file
        if selected_file is None:
            return templates.TemplateResponse(
                request,
                "submit_concerts_calendar_sources_file.html",
                public_form_context(request, {
                    "page_title": "Upload Calendar Sources",
                    "form_action": request.url.path,
                    "form_rendered_at": utc_now().isoformat(),
                    "errors": {
                        "calendar_sources_file": "File upload is required."
                    },
                    "values": {
                        "organization_name": organization_name,
                        "contact_name": contact_name,
                        "contact_email": contact_email,
                        "notes": notes,
                    },
                }),
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        content = await selected_file.read()
        gate_assessment = score_upload_trust_gate(
            db,
            request,
            contact_email,
            honeypot_value,
            form_rendered_at_value,
        )
        turnstile_assessment = turnstile_public_assessment(
            request,
            cf_turnstile_response,
        )
        gate_assessment = combine_security_assessments(
            gate_assessment,
            turnstile_assessment,
        )
        upload_signal_url = "https://file-upload.local/submission"
        ip_hash = request_ip_hash(request, request.app.state.settings)
        user_agent_hash = request_user_agent_hash(request, request.app.state.settings)
        try:
            validate_public_upload_file(
                selected_file.filename,
                content,
                request.app.state.settings,
            )
        except PublicUploadSecurityError as exc:
            file_assessment = combine_security_assessments(
                gate_assessment,
                build_assessment(80, ["file_upload_rejected"]),
            )
            record_public_submission_attempt(
                db,
                submission_type=request.url.path,
                contact_email=contact_email,
                submitted_url=upload_signal_url,
                ip_hash=ip_hash,
                user_agent_hash=user_agent_hash,
                assessment=file_assessment,
                was_invalid=True,
            )
            return templates.TemplateResponse(
                request,
                "submit_concerts_calendar_sources_file.html",
                public_form_context(request, {
                    "page_title": "Upload Calendar Sources",
                    "form_action": request.url.path,
                    "form_rendered_at": utc_now().isoformat(),
                    "errors": {"calendar_sources_file": str(exc)},
                    "values": {
                        "organization_name": organization_name,
                        "contact_name": contact_name,
                        "contact_email": contact_email,
                        "notes": notes,
                    },
                }),
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        if turnstile_assessment.risk_level == "blocked":
            record_public_submission_attempt(
                db,
                submission_type=request.url.path,
                contact_email=contact_email,
                submitted_url=upload_signal_url,
                ip_hash=ip_hash,
                user_agent_hash=user_agent_hash,
                assessment=gate_assessment,
                was_invalid=True,
            )
            return templates.TemplateResponse(
                request,
                "submit_concerts_calendar_sources_file.html",
                public_form_context(request, {
                    "page_title": "Upload Calendar Sources",
                    "form_action": request.url.path,
                    "form_rendered_at": utc_now().isoformat(),
                    "errors": {
                        "calendar_sources_file": (
                            "Submission could not be accepted. Please try again."
                        ),
                    },
                    "values": {
                        "organization_name": organization_name,
                        "contact_name": contact_name,
                        "contact_email": contact_email,
                        "notes": notes,
                    },
                }),
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        try:
            batch = stage_calendar_sources_upload(
                db,
                organization_name=organization_name,
                contact_name=contact_name,
                contact_email=contact_email,
                filename=selected_file.filename or "calendar-sources-upload",
                content=content,
                notes=notes or None,
                gate_assessment=gate_assessment,
                max_rows=request.app.state.settings.public_file_upload_max_rows,
            )
        except ImportValidationError as exc:
            record_public_submission_attempt(
                db,
                submission_type=request.url.path,
                contact_email=contact_email,
                submitted_url=upload_signal_url,
                ip_hash=ip_hash,
                user_agent_hash=user_agent_hash,
                assessment=combine_security_assessments(
                    gate_assessment,
                    build_assessment(50, ["file_upload_parse_rejected"]),
                ),
                was_invalid=True,
            )
            return templates.TemplateResponse(
                request,
                "submit_concerts_calendar_sources_file.html",
                public_form_context(request, {
                    "page_title": "Upload Calendar Sources",
                    "form_action": request.url.path,
                    "form_rendered_at": utc_now().isoformat(),
                    "errors": {"calendar_sources_file": str(exc)},
                    "values": {
                        "organization_name": organization_name,
                        "contact_name": contact_name,
                        "contact_email": contact_email,
                        "notes": notes,
                    },
                }),
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        record_public_submission_attempt(
            db,
            submission_type=request.url.path,
            contact_email=contact_email,
            submitted_url=upload_signal_url,
            ip_hash=ip_hash,
            user_agent_hash=user_agent_hash,
            assessment=gate_assessment,
            was_invalid=False,
        )
        return RedirectResponse(
            url=(
                f"/submit-calendar/thanks?batch_id={batch.id}"
                "&submission_kind=calendar-list"
            ),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.get("/preview", response_class=HTMLResponse)
    def preview_home(
        request: Request,
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        return admin_template_response(
            request,
            "preview_home.html",
            {"page_title": "Visual Sandbox"},
        )

    @app.get("/preview/events", response_class=HTMLResponse)
    def preview_events(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
        search_area: str | None = None,
        latitude: str | None = None,
        longitude: str | None = None,
        radius_miles: str | None = None,
        genre: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        selected_event_id: int | None = None,
        selected_venue_id: int | None = None,
    ) -> Response:
        filters = PreviewFilters(
            search_area=search_area or None,
            latitude=parse_float_filter(latitude),
            longitude=parse_float_filter(longitude),
            radius_miles=parse_float_filter(radius_miles),
            genre=genre or None,
            date_from=parse_date_filter(date_from),
            date_to=parse_date_filter(date_to),
        )
        rows = list_preview_events(db, filters)
        selected_event = (
            get_preview_event(db, selected_event_id) if selected_event_id else None
        )
        selected_venue = (
            get_preview_venue(db, selected_venue_id) if selected_venue_id else None
        )
        if selected_event is None and selected_venue is None and rows:
            selected_event = rows[0].event
        selected_venue_event_rows = (
            preview_events_for_venue(db, selected_venue.id)
            if selected_venue is not None
            else []
        )
        return admin_template_response(
            request,
            "preview_events.html",
            {
                "page_title": "Music Events Preview",
                "rows": rows,
                "filters": {
                    "search_area": search_area or "",
                    "latitude": latitude or "",
                    "longitude": longitude or "",
                    "radius_miles": radius_miles or "",
                    "genre": genre or "",
                    "date_from": date_from or "",
                    "date_to": date_to or "",
                },
                "selected_event": selected_event,
                "selected_event_flags": (
                    event_quality_flags(selected_event) if selected_event else []
                ),
                "selected_event_image_badges": (
                    event_image_badges(selected_event) if selected_event else []
                ),
                "selected_venue": selected_venue,
                "selected_venue_flags": (
                    venue_quality_flags(selected_venue) if selected_venue else []
                ),
                "selected_venue_image_badges": (
                    venue_image_badges(selected_venue) if selected_venue else []
                ),
                "selected_venue_event_rows": selected_venue_event_rows,
                "maps_url_for_event": maps_url_for_event,
                "street_url_for_event": street_url_for_event,
                "maps_url_for_venue": maps_url_for_venue,
                "street_url_for_venue": street_url_for_venue,
                "previewable_image_url": previewable_image_url,
            },
        )

    @app.get("/preview/events/{event_id}", response_class=HTMLResponse)
    def preview_event_detail(
        request: Request,
        event_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        event = get_preview_event(db, event_id)
        if event is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Preview event not found.",
            )
        return admin_template_response(
            request,
            "preview_event_detail.html",
            {
                "page_title": event.title,
                "event": event,
                "quality_flags": event_quality_flags(event),
                "image_badges": event_image_badges(event),
                "source_claims": source_claims_for_event(db, event.id),
                "maps_url": maps_url_for_event(event),
                "street_url": street_url_for_event(event),
                "previewable_image_url": previewable_image_url,
            },
        )

    @app.get("/preview/events/{event_id}/reminder.ics")
    def preview_event_reminder_ics(
        event_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        event = get_preview_event(db, event_id)
        if event is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Preview event not found.",
            )
        return Response(
            content=reminder_ics_for_event(event),
            media_type="text/calendar",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="event-{event.id}-reminder.ics"'
                )
            },
        )

    @app.get("/preview/venues", response_class=HTMLResponse)
    def preview_venues(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
        category: str | None = None,
        subcategory: str | None = None,
        certified: str | None = None,
        carousel_tag: str | None = None,
        city: str | None = None,
        state: str | None = None,
        quality_issue: str | None = None,
    ) -> Response:
        filters = VenuePreviewFilters(
            category=category or None,
            subcategory=subcategory or None,
            certified=parse_bool_filter(certified),
            carousel_tag=carousel_tag or None,
            city=city or None,
            state=state or None,
            quality_issue=quality_issue or None,
        )
        rows = list_preview_venues(db, filters)
        return admin_template_response(
            request,
            "preview_venues.html",
            {
                "page_title": "Venue Preview",
                "rows": rows,
                "previewable_image_url": previewable_image_url,
                "venue_categories": VENUE_CATEGORY_OPTIONS,
                "selected_category": selected_category_option(filters.category),
                "quality_issues": VENUE_QUALITY_ISSUES,
                "filters": {
                    "category": category or "",
                    "subcategory": subcategory or "",
                    "certified": "1" if filters.certified else "",
                    "carousel_tag": carousel_tag or "",
                    "city": city or "",
                    "state": state or "",
                    "quality_issue": quality_issue or "",
                },
                "place_count": len(rows),
            },
        )

    @app.get("/preview/venues/{venue_id}", response_class=HTMLResponse)
    def preview_venue_detail(
        request: Request,
        venue_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        venue = get_preview_venue(db, venue_id)
        if venue is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Preview venue not found.",
            )
        return admin_template_response(
            request,
            "preview_venue_detail.html",
            {
                "page_title": venue.display_name,
                "venue": venue,
                "quality_flags": venue_quality_flags(venue),
                "image_badges": venue_image_badges(venue),
                "event_rows": preview_events_for_venue(db, venue.id),
                "maps_url": maps_url_for_venue(venue),
                "street_url": street_url_for_venue(venue),
                "previewable_image_url": previewable_image_url,
            },
        )

    @app.get("/preview/itineraries", response_class=HTMLResponse)
    def preview_itineraries(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        return admin_template_response(
            request,
            "preview_itineraries.html",
            {
                "page_title": "Road Trips & Tours Preview",
                "itineraries": list_itineraries(db),
            },
        )

    @app.get("/preview/itineraries/{itinerary_id}", response_class=HTMLResponse)
    def preview_itinerary_detail(
        request: Request,
        itinerary_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        itinerary = get_itinerary(db, itinerary_id)
        if itinerary is None:
            raise HTTPException(status_code=404, detail="Itinerary not found.")
        return admin_template_response(
            request,
            "itinerary_preview.html",
            {
                "page_title": f"{itinerary.title} Preview",
                "itinerary": itinerary,
                "feed": build_itinerary_app_feed(db, itinerary),
                "stop_markers": [
                    itinerary_preview_marker(stop) for stop in itinerary.stops
                ],
            },
        )

    @app.get("/preview/quality", response_class=HTMLResponse)
    def preview_quality(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        return admin_template_response(
            request,
            "preview_quality.html",
            {
                "page_title": "Data Quality",
                "summary": quality_summary(db),
                "app_summary": app_feed_summary(db),
                "source_quality_summary": source_quality_dashboard_summary(db),
                "poi_candidate_counts": poi_candidate_dashboard_counts(db),
            },
        )

    @app.get("/admin/dashboard", response_class=HTMLResponse)
    def admin_dashboard(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        master_rows = list_master_source_metadata(db)
        queue_rows = crawl_queue_rows(db)
        background_job_counts = job_status_counts(db)
        source_quality_summary = source_quality_dashboard_summary(db)
        event_quality_counts = event_quality_dashboard_counts(db)
        poi_candidate_counts = poi_candidate_dashboard_counts(db)
        security_summary = security_dashboard_context(db)
        return admin_template_response(
            request,
            "admin_dashboard.html",
            {
                "page_title": "Admin Dashboard",
                "master_count": len(master_rows),
                "crawlable_count": sum(row.is_crawlable for row in master_rows),
                "due_count": len(due_crawl_rows(db)),
                "queue_count": len(queue_rows),
                "trusted_count": sum(row.is_trusted for row in master_rows),
                "app_summary": app_feed_summary(db),
                "job_counts": background_job_counts,
                "jobs_needing_attention": jobs_needing_attention_count(db),
                "photo_rescue_jobs_needing_attention": (
                    photo_rescue_jobs_needing_attention_count(db)
                ),
                "source_quality_summary": source_quality_summary,
                "event_quality_counts": event_quality_counts,
                "poi_candidate_counts": poi_candidate_counts,
                "security_summary": security_summary,
                "next_scheduled_crawl_task": next_scheduled_task(
                    db,
                    "crawl_due_sources",
                ),
            },
        )

    @app.get("/admin/security", response_class=HTMLResponse)
    def admin_security(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        return admin_template_response(
            request,
            "security.html",
            {
                "page_title": "Security",
                "security": security_dashboard_context(db),
            },
        )

    @app.get("/admin/event-quality", response_class=HTMLResponse)
    def admin_event_quality(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
        bucket: str | None = None,
        search: str | None = None,
        limit: str | None = None,
        offset: str | None = None,
    ) -> Response:
        filters = EventQualityFilters(
            bucket=bucket or None,
            search=search or None,
            limit=parse_int_query(limit) or 100,
            offset=parse_int_query(offset) or 0,
        )
        return admin_template_response(
            request,
            "event_quality.html",
            {
                "page_title": "Event Quality Workbench",
                "workbench": event_quality_workbench(db, filters),
                "selected_bucket": bucket or "",
                "search": search or "",
            },
        )

    @app.post("/admin/event-quality/bulk-action")
    async def admin_event_quality_bulk_action(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        form = await request.form()
        action = str(form.get("action") or "")
        event_ids = selected_event_ids_from_form(form)
        if not event_ids:
            return RedirectResponse(
                url="/admin/event-quality?error=Select at least one event.",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        if action not in {
            "photo_rescue",
            "needs_image_review",
            "recompute_quality",
            "duplicate_review",
        }:
            return RedirectResponse(
                url="/admin/event-quality?error=Unsupported bulk action.",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        updated_count = apply_event_quality_bulk_action(
            db,
            event_ids,
            cast(EventQualityBulkAction, action),
        )
        return RedirectResponse(
            url=f"/admin/event-quality?success=Updated {updated_count} event(s).",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.get("/admin/regions", response_class=HTMLResponse)
    def admin_regions(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        return admin_template_response(
            request,
            "regions.html",
            {
                "page_title": "Regions",
                "summaries": list_regions(db),
                "region_types": [
                    "city",
                    "metro",
                    "state",
                    "country",
                    "certified_music_region",
                    "tourism_board",
                    "custom",
                ],
                "partner_statuses": [
                    "internal",
                    "prospect",
                    "active_partner",
                    "certified",
                    "inactive",
                ],
                "launch_statuses": [
                    "research",
                    "building",
                    "qa",
                    "ready",
                    "launched",
                ],
            },
        )

    @app.post("/admin/regions")
    def admin_create_region(
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin_csrf)],
        name: Annotated[str, Form()],
        region_type: Annotated[str, Form()] = "city",
        city: Annotated[str | None, Form()] = None,
        state_value: Annotated[str | None, Form(alias="state")] = None,
        country: Annotated[str | None, Form()] = "US",
        latitude: Annotated[str | None, Form()] = None,
        longitude: Annotated[str | None, Form()] = None,
        radius_miles: Annotated[str | None, Form()] = None,
        timezone: Annotated[str | None, Form()] = None,
        partner_status: Annotated[str, Form()] = "internal",
        launch_status: Annotated[str, Form()] = "research",
        certified: Annotated[str | None, Form()] = None,
    ) -> Response:
        region = create_or_update_region(
            db,
            name=name,
            region_type=region_type,
            city=city,
            state=state_value,
            country=country,
            latitude=parse_float_filter(latitude),
            longitude=parse_float_filter(longitude),
            radius_miles=parse_float_filter(radius_miles),
            timezone=timezone,
            partner_status=partner_status,
            certified=parse_bool_query(certified),
            launch_status=launch_status,
        )
        return RedirectResponse(
            url=f"/admin/regions/{region.id}?success=Region saved",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/regions/infer")
    def admin_infer_regions(
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        counts = assign_inferred_regions(db)
        return RedirectResponse(
            url=(
                "/admin/regions?success="
                f"Assigned {counts['pois']} POIs, {counts['events']} events, "
                f"and {counts['sources']} sources"
            ),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/search-seeds/seed")
    def admin_seed_search_locations(
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        poi_counts = seed_search_locations_from_pois(db)
        region_counts = seed_search_locations_from_regions(db)
        return RedirectResponse(
            url=(
                "/admin/search-seeds?success="
                f"Seeded {poi_counts['created'] + region_counts['created']} "
                "new search locations"
            ),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.get("/admin/regions/{region_id}", response_class=HTMLResponse)
    def admin_region_detail(
        request: Request,
        region_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        region = get_region(db, region_id)
        if region is None:
            raise HTTPException(status_code=404, detail="Region not found.")
        events = region_events(db, region.id)
        pois = region_pois(db, region.id)
        sources = region_sources(db, region.id)
        latest_snapshot = latest_region_quality_snapshot(db, region.id)
        return admin_template_response(
            request,
            "region_detail.html",
            {
                "page_title": region.name,
                "region": region,
                "event_count": len(events),
                "poi_count": len(pois),
                "source_count": len(sources),
                "approved_source_count": sum(
                    1
                    for source in sources
                    if source.status == "approved"
                    and source.review_status == SourceReviewStatus.approved.value
                ),
                "extracted_candidate_count": region_extracted_candidate_count(
                    db,
                    region.id,
                ),
                "app_event_count": len(
                    list_app_events(
                        db,
                        AppEventFilters(region_id=region.id, limit=1000),
                    )
                ),
                "app_poi_count": len(
                    list_app_pois(
                        db,
                        AppPoiFilters(region_id=region.id, limit=1000),
                    )
                ),
                "source_coverage": region_source_coverage(db, region.id),
                "latest_snapshot": latest_snapshot,
            },
        )

    @app.get("/admin/regions/{region_id}/events", response_class=HTMLResponse)
    def admin_region_events(
        request: Request,
        region_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        region = get_region(db, region_id)
        if region is None:
            raise HTTPException(status_code=404, detail="Region not found.")
        return admin_template_response(
            request,
            "region_events.html",
            {
                "page_title": f"{region.name} Events",
                "region": region,
                "events": region_events(db, region.id),
            },
        )

    @app.get("/admin/regions/{region_id}/pois", response_class=HTMLResponse)
    def admin_region_pois(
        request: Request,
        region_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        region = get_region(db, region_id)
        if region is None:
            raise HTTPException(status_code=404, detail="Region not found.")
        return admin_template_response(
            request,
            "region_pois.html",
            {
                "page_title": f"{region.name} POIs",
                "region": region,
                "pois": region_pois(db, region.id),
            },
        )

    @app.get("/admin/regions/{region_id}/sources", response_class=HTMLResponse)
    def admin_region_sources(
        request: Request,
        region_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        region = get_region(db, region_id)
        if region is None:
            raise HTTPException(status_code=404, detail="Region not found.")
        return admin_template_response(
            request,
            "region_sources.html",
            {
                "page_title": f"{region.name} Sources",
                "region": region,
                "sources": region_sources(db, region.id),
                "coverage": region_source_coverage(db, region.id),
            },
        )

    @app.get("/admin/regions/{region_id}/quality", response_class=HTMLResponse)
    def admin_region_quality(
        request: Request,
        region_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        region = get_region(db, region_id)
        if region is None:
            raise HTTPException(status_code=404, detail="Region not found.")
        snapshot = latest_region_quality_snapshot(db, region.id)
        return admin_template_response(
            request,
            "region_quality.html",
            {
                "page_title": f"{region.name} Quality",
                "region": region,
                "snapshot": snapshot,
                "snapshot_json": pretty_json_object(snapshot.snapshot)
                if snapshot
                else "{}",
                "source_scores": list_source_quality_scores(
                    db,
                    SourceQualityFilters(region_id=region.id),
                ),
                "latest_report": latest_region_partner_report(db, region.id),
            },
        )

    @app.post("/admin/regions/{region_id}/quality/generate")
    def admin_region_quality_generate(
        region_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        compute_region_quality_snapshot(db, region_id)
        return RedirectResponse(
            url=f"/admin/regions/{region_id}/quality?success=Snapshot generated",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.get("/admin/search-seeds", response_class=HTMLResponse)
    def admin_search_seeds(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
        q: str | None = None,
        seed_type: str | None = None,
        region_id: str | None = None,
    ) -> Response:
        parsed_region_id = parse_int_query(region_id)
        filters = SearchSeedFilters(
            q=q or None,
            seed_type=seed_type or None,
            region_id=parsed_region_id,
        )
        return admin_template_response(
            request,
            "search_seeds.html",
            {
                "page_title": "Search Seeds",
                "seeds": list_search_seed_locations(db, filters),
                "regions": [summary.region for summary in list_regions(db)],
                "filters": {
                    "q": q or "",
                    "seed_type": seed_type or "",
                    "region_id": str(parsed_region_id or ""),
                },
                "seed_types": [
                    "city",
                    "metro",
                    "state",
                    "country",
                    "venue",
                    "poi",
                    "festival",
                    "stadium",
                    "airport",
                    "landmark",
                    "neighborhood",
                    "tourism_board",
                    "unknown",
                ],
            },
        )

    @app.get("/admin/source-quality", response_class=HTMLResponse)
    def admin_source_quality(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
        source_kind: str | None = None,
        grade: str | None = None,
        region_id: str | None = None,
        provider_key: str | None = None,
    ) -> Response:
        parsed_region_id = parse_int_query(region_id)
        filters = SourceQualityFilters(
            source_kind=source_kind or None,
            grade=grade or None,
            region_id=parsed_region_id,
            provider_key=provider_key or None,
        )
        return admin_template_response(
            request,
            "source_quality.html",
            {
                "page_title": "Source Quality",
                "scores": list_source_quality_scores(db, filters),
                "filters": {
                    "source_kind": source_kind or "",
                    "grade": grade or "",
                    "region_id": str(parsed_region_id or ""),
                    "provider_key": provider_key or "",
                },
                "regions": [summary.region for summary in list_regions(db)],
                "summary": source_quality_dashboard_summary(db),
                "source_kinds": [
                    "master_calendar_source",
                    "api_provider",
                    "api_feed_run",
                    "crawl_run",
                    "import_batch",
                    "destination_partner",
                    "region",
                    "unknown",
                ],
                "grades": ["excellent", "good", "fair", "poor", "blocked", "unknown"],
            },
        )

    @app.post("/admin/source-quality/compute")
    def admin_source_quality_compute(
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin_csrf)],
        source_kind: Annotated[str, Form()] = "all",
        source_id: Annotated[str | None, Form()] = None,
        provider_key: Annotated[str | None, Form()] = None,
        region_id: Annotated[str | None, Form()] = None,
        partner_id: Annotated[str | None, Form()] = None,
    ) -> Response:
        if source_kind == "all":
            counts = compute_all_source_quality(db)
            message = "Computed source quality for " + ", ".join(
                f"{count} {kind}" for kind, count in counts.items()
            )
        elif source_kind == "master_calendar_source":
            score = compute_source_quality_for_master_source(
                db,
                parse_int_query(source_id) or 0,
            )
            message = f"Computed score {score.score} for {score.display_name}"
        elif source_kind == "api_provider":
            score = compute_source_quality_for_api_provider(db, provider_key or "")
            message = f"Computed score {score.score} for {score.display_name}"
        elif source_kind == "region":
            score = compute_source_quality_for_region(
                db,
                parse_int_query(region_id) or 0,
            )
            message = f"Computed score {score.score} for {score.display_name}"
        elif source_kind == "destination_partner":
            score = compute_source_quality_for_partner(
                db,
                parse_int_query(partner_id) or 0,
            )
            message = f"Computed score {score.score} for {score.display_name}"
        else:
            raise HTTPException(status_code=400, detail="Unsupported source kind.")
        return RedirectResponse(
            url=f"/admin/source-quality?success={message}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/source-quality/queue")
    def admin_source_quality_queue(
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        job = enqueue_job(
            db,
            BackgroundJobType.all_source_quality_rollup.value,
            {},
            created_by=admin_user,
        )
        return RedirectResponse(
            url=f"/admin/jobs/{job.id}?success=Queued source quality rollup",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.get("/admin/source-quality/{score_id}", response_class=HTMLResponse)
    def admin_source_quality_detail(
        request: Request,
        score_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        score = get_source_quality_score(db, score_id)
        if score is None:
            raise HTTPException(
                status_code=404,
                detail="Source quality score not found.",
            )
        return admin_template_response(
            request,
            "source_quality_detail.html",
            {
                "page_title": f"Source Quality #{score.id}",
                "score": score,
                "score_inputs_json": pretty_json_object(score.score_inputs),
                "recommendations_json": pretty_json_object(score.recommendations),
            },
        )

    @app.get("/admin/partner-reports", response_class=HTMLResponse)
    def admin_partner_reports(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        return admin_template_response(
            request,
            "partner_reports.html",
            {
                "page_title": "Partner Reports",
                "reports": list_partner_reports(db),
                "regions": [summary.region for summary in list_regions(db)],
            },
        )

    @app.post("/admin/partner-reports/source-quality")
    def admin_generate_source_quality_report(
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
        region_id: Annotated[str | None, Form()] = None,
        partner_id: Annotated[str | None, Form()] = None,
    ) -> Response:
        report = generate_source_quality_report(
            db,
            region_id=parse_int_query(region_id),
            partner_id=parse_int_query(partner_id),
            generated_by=admin_user,
        )
        return RedirectResponse(
            url=f"/admin/partner-reports/{report.id}?success=Report generated",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.get("/admin/partner-reports/{report_id}", response_class=HTMLResponse)
    def admin_partner_report_detail(
        request: Request,
        report_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        report = get_partner_report(db, report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Partner report not found.")
        return admin_template_response(
            request,
            "partner_report_detail.html",
            {
                "page_title": f"Partner Report #{report.id}",
                "report": report,
                "summary_json": pretty_json_object(report.summary),
                "metrics_json": pretty_json_object(report.metrics),
                "recommendations_json": pretty_json_object(report.recommendations),
            },
        )

    @app.get("/admin/partner-reports/{report_id}/report.json")
    def admin_partner_report_json(
        report_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> JSONResponse:
        report = get_partner_report(db, report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Partner report not found.")
        return JSONResponse(export_partner_report_json(report))

    @app.get("/admin/partner-reports/{report_id}/report.csv")
    def admin_partner_report_csv(
        report_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        report = get_partner_report(db, report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Partner report not found.")
        return Response(
            export_partner_report_csv(report),
            media_type="text/csv",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="partner-report-{report.id}.csv"'
                )
            },
        )

    @app.get("/admin/regions/{region_id}/report", response_class=HTMLResponse)
    def admin_region_report(
        request: Request,
        region_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        try:
            context = region_report_context(db, region_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        region_name = getattr(context["region"], "name", "Region")
        return admin_template_response(
            request,
            "region_report.html",
            {
                "page_title": f"{region_name} Report",
                **context,
            },
        )

    @app.post("/admin/regions/{region_id}/report/generate")
    def admin_region_report_generate(
        region_id: int,
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        report = generate_region_partner_report(
            db,
            region_id,
            generated_by=admin_user,
        )
        return RedirectResponse(
            url=f"/admin/regions/{region_id}/report?success=Report generated"
            f"&report_id={report.id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/regions/{region_id}/report/queue")
    def admin_region_report_queue(
        region_id: int,
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        if get_region(db, region_id) is None:
            raise HTTPException(status_code=404, detail="Region not found.")
        job = enqueue_job(
            db,
            BackgroundJobType.region_partner_report.value,
            {"region_id": region_id},
            created_by=admin_user,
        )
        return RedirectResponse(
            url=f"/admin/jobs/{job.id}?success=Queued region partner report",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.get("/admin/jobs", response_class=HTMLResponse)
    def admin_jobs(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
        status_value: Annotated[str, Query(alias="status")] = "",
        job_type: str | None = None,
        queue_name: str | None = None,
    ) -> Response:
        filters = job_filters_from_values(
            status_value=status_value,
            job_type=job_type,
            queue_name=queue_name,
        )
        return admin_template_response(
            request,
            "jobs.html",
            {
                "page_title": "Background Jobs",
                "jobs": list_jobs(db, filters),
                "counts": job_status_counts(db),
                "filters": {
                    "status": status_value or "",
                    "job_type": job_type or "",
                    "queue_name": queue_name or "",
                },
            },
        )

    @app.get("/admin/jobs/{job_id}", response_class=HTMLResponse)
    def admin_job_detail(
        request: Request,
        job_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        job = get_job(db, job_id)
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Background job not found.",
            )
        return admin_template_response(
            request,
            "job_detail.html",
            {
                "page_title": f"Background Job #{job.id}",
                "job": job,
                "payload": pretty_json_object(job.payload),
                "result": pretty_json_object(job.result),
            },
        )

    @app.post("/admin/jobs/{job_id}/retry")
    def admin_job_retry(
        job_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        job = retry_job(db, job_id)
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Background job not found.",
            )
        return RedirectResponse(
            url=f"/admin/jobs/{job.id}?success=Queued job retry",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/jobs/{job_id}/cancel")
    def admin_job_cancel(
        job_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        job = cancel_job(db, job_id)
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Background job not found.",
            )
        return RedirectResponse(
            url=f"/admin/jobs/{job.id}?success=Cancelled job",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.get("/admin/scheduled-tasks", response_class=HTMLResponse)
    def admin_scheduled_tasks(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        return admin_template_response(
            request,
            "scheduled_tasks.html",
            {
                "page_title": "Scheduled Tasks",
                "tasks": list_scheduled_tasks(db),
            },
        )

    @app.get("/admin/scheduled-tasks/{task_id}", response_class=HTMLResponse)
    def admin_scheduled_task_detail(
        request: Request,
        task_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        task = get_scheduled_task(db, task_id)
        if task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Scheduled task not found.",
            )
        return admin_template_response(
            request,
            "scheduled_task_detail.html",
            {
                "page_title": task.task_key,
                "task": task,
                "payload": pretty_json_object(task.payload),
                "last_job": get_job(db, task.last_job_id) if task.last_job_id else None,
            },
        )

    @app.post("/admin/scheduled-tasks/{task_id}/enqueue")
    def admin_scheduled_task_enqueue(
        task_id: int,
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        job = enqueue_scheduled_task_now(db, task_id, created_by=admin_user)
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Scheduled task not found.",
            )
        return RedirectResponse(
            url=f"/admin/jobs/{job.id}?success=Scheduled task queued",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/scheduled-tasks/run-due")
    def admin_scheduled_tasks_run_due(
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        result = enqueue_due_scheduled_tasks(db)
        return RedirectResponse(
            url=(
                "/admin/scheduled-tasks?success="
                f"Queued {len(result.enqueued_job_ids)} due scheduled tasks"
            ),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.get("/admin/itineraries", response_class=HTMLResponse)
    def admin_itineraries(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        return admin_template_response(
            request,
            "itineraries.html",
            {
                "page_title": "Road Trips & Tours",
                "itineraries": list_itineraries(db),
                "references": itinerary_admin_reference_options(db),
            },
        )

    @app.get("/admin/itineraries/new", response_class=HTMLResponse)
    def admin_itinerary_new(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        return admin_template_response(
            request,
            "itinerary_form.html",
            {
                "page_title": "New Itinerary",
                "references": itinerary_admin_reference_options(db),
                "itinerary": None,
            },
        )

    @app.post("/admin/itineraries")
    def admin_itinerary_create(
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
        title: Annotated[str, Form()],
        itinerary_type: Annotated[str, Form()] = "road_trip",
        display_label: Annotated[str | None, Form()] = None,
        subtitle: Annotated[str | None, Form()] = None,
        description: Annotated[str | None, Form()] = None,
        region_id: Annotated[str | None, Form()] = None,
        destination_partner_id: Annotated[str | None, Form()] = None,
        artist_id: Annotated[str | None, Form()] = None,
        start_city: Annotated[str | None, Form()] = None,
        start_state: Annotated[str | None, Form()] = None,
        start_country: Annotated[str | None, Form()] = None,
        end_city: Annotated[str | None, Form()] = None,
        end_state: Annotated[str | None, Form()] = None,
        end_country: Annotated[str | None, Form()] = None,
        estimated_duration_text: Annotated[str | None, Form()] = None,
        estimated_distance_text: Annotated[str | None, Form()] = None,
        hero_image_url: Annotated[str | None, Form()] = None,
        music_theme: Annotated[str | None, Form()] = None,
        normalized_genres: Annotated[str | None, Form()] = None,
        tags: Annotated[str | None, Form()] = None,
        featured: Annotated[str | None, Form()] = None,
    ) -> Response:
        itinerary = create_itinerary(
            db,
            ItineraryCreate(
                title=title,
                itinerary_type=itinerary_type,
                display_label=display_label,
                subtitle=subtitle,
                description=description,
                region_id=parse_int_query(region_id),
                destination_partner_id=parse_int_query(destination_partner_id),
                artist_id=parse_int_query(artist_id),
                start_city=start_city,
                start_state=start_state,
                start_country=start_country,
                end_city=end_city,
                end_state=end_state,
                end_country=end_country,
                estimated_duration_text=estimated_duration_text,
                estimated_distance_text=estimated_distance_text,
                hero_image_url=hero_image_url,
                music_theme=music_theme,
                normalized_genres=[
                    item.strip()
                    for item in (normalized_genres or "").split(",")
                    if item.strip()
                ],
                tags=[
                    item.strip() for item in (tags or "").split(",") if item.strip()
                ],
                featured=parse_bool_query(featured),
                created_by=admin_user,
            ),
        )
        return RedirectResponse(
            url=f"/admin/itineraries/{itinerary.id}?success=Itinerary created",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.get("/admin/itineraries/{itinerary_id}", response_class=HTMLResponse)
    def admin_itinerary_detail(
        request: Request,
        itinerary_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        itinerary = get_itinerary(db, itinerary_id)
        if itinerary is None:
            raise HTTPException(status_code=404, detail="Itinerary not found.")
        return admin_template_response(
            request,
            "itinerary_detail.html",
            {
                "page_title": itinerary.title,
                "itinerary": itinerary,
                "references": itinerary_admin_reference_options(db),
                "feed_json": pretty_json_object(
                    build_itinerary_app_feed(db, itinerary),
                ),
                "stop_markers": [
                    itinerary_preview_marker(stop) for stop in itinerary.stops
                ],
            },
        )

    @app.post("/admin/itineraries/{itinerary_id}")
    def admin_itinerary_update(
        itinerary_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin_csrf)],
        title: Annotated[str, Form()],
        itinerary_type: Annotated[str, Form()] = "road_trip",
        display_label: Annotated[str | None, Form()] = None,
        subtitle: Annotated[str | None, Form()] = None,
        description: Annotated[str | None, Form()] = None,
        status_value: Annotated[str | None, Form(alias="status")] = None,
        region_id: Annotated[str | None, Form()] = None,
        destination_partner_id: Annotated[str | None, Form()] = None,
        artist_id: Annotated[str | None, Form()] = None,
        hero_image_url: Annotated[str | None, Form()] = None,
        music_theme: Annotated[str | None, Form()] = None,
        normalized_genres: Annotated[str | None, Form()] = None,
        tags: Annotated[str | None, Form()] = None,
        featured: Annotated[str | None, Form()] = None,
    ) -> Response:
        itinerary = update_itinerary(
            db,
            itinerary_id,
            ItineraryUpdate(
                title=title,
                itinerary_type=itinerary_type,
                display_label=display_label,
                subtitle=subtitle,
                description=description,
                status=status_value,
                region_id=parse_int_query(region_id),
                destination_partner_id=parse_int_query(destination_partner_id),
                artist_id=parse_int_query(artist_id),
                hero_image_url=hero_image_url,
                music_theme=music_theme,
                normalized_genres=[
                    item.strip()
                    for item in (normalized_genres or "").split(",")
                    if item.strip()
                ],
                tags=[
                    item.strip() for item in (tags or "").split(",") if item.strip()
                ],
                featured=parse_bool_query(featured),
            ),
        )
        return RedirectResponse(
            url=f"/admin/itineraries/{itinerary.id}?success=Itinerary updated",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.get("/admin/itineraries/{itinerary_id}/stops", response_class=HTMLResponse)
    def admin_itinerary_stops(
        itinerary_id: int,
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        return admin_itinerary_detail(request, itinerary_id, db, _admin)

    @app.post("/admin/itineraries/{itinerary_id}/stops")
    def admin_itinerary_add_stop(
        itinerary_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin_csrf)],
        stop_type: Annotated[str, Form()] = "custom",
        event_id: Annotated[str | None, Form()] = None,
        poi_location_id: Annotated[str | None, Form()] = None,
        event_venue_id: Annotated[str | None, Form()] = None,
        region_id: Annotated[str | None, Form()] = None,
        artist_id: Annotated[str | None, Form()] = None,
        title: Annotated[str | None, Form()] = None,
        subtitle: Annotated[str | None, Form()] = None,
        description: Annotated[str | None, Form()] = None,
        address: Annotated[str | None, Form()] = None,
        city: Annotated[str | None, Form()] = None,
        state_value: Annotated[str | None, Form(alias="state")] = None,
        country: Annotated[str | None, Form()] = None,
        latitude: Annotated[str | None, Form()] = None,
        longitude: Annotated[str | None, Form()] = None,
        start_datetime: Annotated[str | None, Form()] = None,
        end_datetime: Annotated[str | None, Form()] = None,
        stop_duration_text: Annotated[str | None, Form()] = None,
        ticket_url: Annotated[str | None, Form()] = None,
        website_url: Annotated[str | None, Form()] = None,
        image_url: Annotated[str | None, Form()] = None,
        notes: Annotated[str | None, Form()] = None,
    ) -> Response:
        try:
            add_stop(
                db,
                itinerary_id,
                ItineraryStopInput(
                    stop_type=stop_type,
                    event_id=parse_int_query(event_id),
                    poi_location_id=parse_int_query(poi_location_id),
                    event_venue_id=parse_int_query(event_venue_id),
                    region_id=parse_int_query(region_id),
                    artist_id=parse_int_query(artist_id),
                    title=title,
                    subtitle=subtitle,
                    description=description,
                    address=address,
                    city=city,
                    state=state_value,
                    country=country,
                    latitude=parse_float_filter(latitude),
                    longitude=parse_float_filter(longitude),
                    start_datetime=parse_datetime_query(start_datetime),
                    end_datetime=parse_datetime_query(end_datetime),
                    stop_duration_text=stop_duration_text,
                    ticket_url=ticket_url,
                    website_url=website_url,
                    image_url=image_url,
                    notes=notes,
                ),
            )
        except ValueError:
            return RedirectResponse(
                url=f"/admin/itineraries/{itinerary_id}?error=Could not add stop",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        return RedirectResponse(
            url=f"/admin/itineraries/{itinerary_id}?success=Stop added",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/itineraries/{itinerary_id}/stops/{stop_id}/move")
    def admin_itinerary_move_stop(
        itinerary_id: int,
        stop_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin_csrf)],
        direction: Annotated[str, Form()] = "down",
    ) -> Response:
        move_stop(db, itinerary_id, stop_id, direction)
        return RedirectResponse(
            url=f"/admin/itineraries/{itinerary_id}?success=Stops reordered",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/itineraries/{itinerary_id}/stops/{stop_id}/remove")
    def admin_itinerary_remove_stop(
        itinerary_id: int,
        stop_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        remove_stop(db, itinerary_id, stop_id)
        return RedirectResponse(
            url=f"/admin/itineraries/{itinerary_id}?success=Stop removed",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/itineraries/{itinerary_id}/quality")
    def admin_itinerary_quality_rollup(
        itinerary_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        compute_itinerary_quality(db, itinerary_id)
        return RedirectResponse(
            url=f"/admin/itineraries/{itinerary_id}?success=Quality refreshed",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/itineraries/actions/build-region")
    def admin_itinerary_build_region(
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin_csrf)],
        region_id: Annotated[str, Form()],
    ) -> Response:
        itinerary = build_itinerary_from_region(db, parse_int_query(region_id) or 0)
        return RedirectResponse(
            url=f"/admin/itineraries/{itinerary.id}?success=Draft route built",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/itineraries/actions/build-artist")
    def admin_itinerary_build_artist(
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin_csrf)],
        artist_id: Annotated[str, Form()],
    ) -> Response:
        itinerary = build_itinerary_from_artist_events(
            db,
            parse_int_query(artist_id) or 0,
        )
        return RedirectResponse(
            url=f"/admin/itineraries/{itinerary.id}?success=Draft tour built",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.get("/admin/itineraries/{itinerary_id}/preview", response_class=HTMLResponse)
    def admin_itinerary_preview(
        request: Request,
        itinerary_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        itinerary = get_itinerary(db, itinerary_id)
        if itinerary is None:
            raise HTTPException(status_code=404, detail="Itinerary not found.")
        return admin_template_response(
            request,
            "itinerary_preview.html",
            {
                "page_title": f"{itinerary.title} Preview",
                "itinerary": itinerary,
                "feed": build_itinerary_app_feed(db, itinerary),
                "stop_markers": [
                    itinerary_preview_marker(stop) for stop in itinerary.stops
                ],
            },
        )

    @app.get("/admin/itineraries/{itinerary_id}/app-feed.json")
    def admin_itinerary_app_feed_json(
        itinerary_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> JSONResponse:
        itinerary = get_itinerary(db, itinerary_id)
        if itinerary is None:
            raise HTTPException(status_code=404, detail="Itinerary not found.")
        return JSONResponse(build_itinerary_app_feed(db, itinerary))

    @app.get("/admin/app-search", response_class=HTMLResponse)
    def admin_app_search(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
        q: str | None = None,
        entity_type: str | None = None,
        category: str | None = None,
        subcategory: str | None = None,
        region_id: str | None = None,
        city: str | None = None,
        state_value: Annotated[str | None, Query(alias="state")] = None,
        country: str | None = None,
        app_feed_ready: str | None = None,
        certified: str | None = None,
        limit: str | None = None,
        offset: str | None = None,
    ) -> Response:
        filters = app_search_filters_from_values(
            entity_type=entity_type,
            category=category,
            subcategory=subcategory,
            region_id=region_id,
            city=city,
            state_value=state_value,
            country=country,
            app_feed_ready=app_feed_ready,
            certified=certified,
        )
        payload = search_app_index(
            db,
            q or "",
            filters,
            limit=parse_int_query(limit) or 20,
            offset=parse_int_query(offset) or 0,
            include_marker=True,
        )
        return admin_template_response(
            request,
            "app_search.html",
            {
                "page_title": "App Search",
                "query": q or "",
                "filters": filters,
                "results": payload["results"],
                "result_count": payload["count"],
                "regions": [summary.region for summary in list_regions(db)],
            },
        )

    @app.post("/admin/app-search/rebuild-index")
    def admin_app_search_rebuild_index(
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        counts = rebuild_search_index(db)
        total = sum(counts.values())
        return RedirectResponse(
            url=f"/admin/app-search?success=Rebuilt app search index with {total} rows",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.get("/admin/app-search/results.json")
    def admin_app_search_results_json(
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
        q: str | None = None,
        entity_type: str | None = None,
        category: str | None = None,
        subcategory: str | None = None,
        region_id: str | None = None,
        city: str | None = None,
        state_value: Annotated[str | None, Query(alias="state")] = None,
        country: str | None = None,
        app_feed_ready: str | None = None,
        certified: str | None = None,
        limit: str | None = None,
        offset: str | None = None,
    ) -> JSONResponse:
        filters = app_search_filters_from_values(
            entity_type=entity_type,
            category=category,
            subcategory=subcategory,
            region_id=region_id,
            city=city,
            state_value=state_value,
            country=country,
            app_feed_ready=app_feed_ready,
            certified=certified,
        )
        payload = search_app_index(
            db,
            q or "",
            filters,
            limit=parse_int_query(limit) or 20,
            offset=parse_int_query(offset) or 0,
        )
        return JSONResponse(payload)

    @app.get("/admin/app-search/suggest.json")
    def admin_app_search_suggest_json(
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
        q: str | None = None,
        limit: str | None = None,
    ) -> JSONResponse:
        return JSONResponse(
            suggest_app_search(db, q or "", limit=parse_int_query(limit) or 10),
        )

    @app.get("/admin/app-feed", response_class=HTMLResponse)
    def admin_app_feed(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        return admin_template_response(
            request,
            "app_feed.html",
            {
                "page_title": "App Feed",
                "summary": app_feed_summary(db),
                "latest_events_export": latest_successful_export(db, "events"),
                "latest_pois_export": latest_successful_export(db, "pois"),
            },
        )

    @app.get("/admin/app-feed/itineraries.json")
    def admin_app_feed_itineraries_json(
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> JSONResponse:
        records = list_app_itineraries(db)
        return JSONResponse(
            {
                "export_type": "itineraries",
                "count": len(records),
                "records": records,
            },
        )

    @app.get("/admin/app-feed/itineraries/{itinerary_id}.json")
    def admin_app_feed_itinerary_json(
        itinerary_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> JSONResponse:
        itinerary = get_itinerary(db, itinerary_id)
        if itinerary is None:
            raise HTTPException(status_code=404, detail="Itinerary not found.")
        return JSONResponse(build_itinerary_app_feed(db, itinerary))

    @app.get("/admin/app-feed/regions/{region_id}/events.json")
    def admin_region_app_feed_events_json(
        region_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
        limit: str | None = None,
        offset: str | None = None,
    ) -> JSONResponse:
        region = get_region(db, region_id)
        if region is None:
            raise HTTPException(status_code=404, detail="Region not found.")
        records = list_app_events(
            db,
            AppEventFilters(
                region_id=region.id,
                limit=parse_int_query(limit) or 100,
                offset=parse_int_query(offset) or 0,
            ),
        )
        return JSONResponse(
            {
                "export_type": "region_events",
                "region": {"id": region.id, "name": region.name},
                "count": len(records),
                "records": records,
            },
        )

    @app.get("/admin/app-feed/regions/{region_id}/itineraries.json")
    def admin_region_app_feed_itineraries_json(
        region_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> JSONResponse:
        region = get_region(db, region_id)
        if region is None:
            raise HTTPException(status_code=404, detail="Region not found.")
        records = list_app_itineraries(db, region_id=region.id)
        return JSONResponse(
            {
                "export_type": "region_itineraries",
                "region": {"id": region.id, "name": region.name},
                "count": len(records),
                "records": records,
            },
        )

    @app.get("/admin/app-feed/artists/{artist_id}/itineraries.json")
    def admin_artist_app_feed_itineraries_json(
        artist_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> JSONResponse:
        artist = get_artist(db, artist_id)
        if artist is None:
            raise HTTPException(status_code=404, detail="Artist not found.")
        records = list_app_itineraries(db, artist_id=artist.id)
        return JSONResponse(
            {
                "export_type": "artist_itineraries",
                "artist": {"id": artist.id, "name": artist.display_name},
                "count": len(records),
                "records": records,
            },
        )

    @app.get("/admin/app-feed/regions/{region_id}/pois.json")
    def admin_region_app_feed_pois_json(
        region_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
        limit: str | None = None,
        offset: str | None = None,
    ) -> JSONResponse:
        region = get_region(db, region_id)
        if region is None:
            raise HTTPException(status_code=404, detail="Region not found.")
        records = list_app_pois(
            db,
            AppPoiFilters(
                region_id=region.id,
                limit=parse_int_query(limit) or 100,
                offset=parse_int_query(offset) or 0,
            ),
        )
        return JSONResponse(
            {
                "export_type": "region_pois",
                "region": {"id": region.id, "name": region.name},
                "count": len(records),
                "records": records,
            },
        )

    @app.get("/admin/app-feed/regions/{region_id}/venues.json")
    def admin_region_app_feed_venues_json(
        region_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
        limit: str | None = None,
        offset: str | None = None,
    ) -> JSONResponse:
        region = get_region(db, region_id)
        if region is None:
            raise HTTPException(status_code=404, detail="Region not found.")
        records = list_app_venues(
            db,
            AppEventFilters(
                region_id=region.id,
                limit=parse_int_query(limit) or 100,
                offset=parse_int_query(offset) or 0,
            ),
        )
        return JSONResponse(
            {
                "export_type": "region_venues",
                "region": {"id": region.id, "name": region.name},
                "count": len(records),
                "records": records,
            },
        )

    @app.get("/admin/app-feed/regions/{region_id}/map-markers.json")
    def admin_region_map_markers_json(
        region_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
        entity_type: str | None = None,
        category: str | None = None,
        subcategory: str | None = None,
        city: str | None = None,
        state_value: Annotated[str | None, Query(alias="state")] = None,
        country: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        has_upcoming_events: str | None = None,
        certified: str | None = None,
        limit: str | None = None,
        offset: str | None = None,
    ) -> JSONResponse:
        region = get_region(db, region_id)
        if region is None:
            raise HTTPException(status_code=404, detail="Region not found.")
        filters = map_marker_filters_from_values(
            entity_type=entity_type,
            category=category,
            subcategory=subcategory,
            region_id=str(region.id),
            city=city,
            state_value=state_value,
            country=country,
            date_from=date_from,
            date_to=date_to,
            has_upcoming_events=has_upcoming_events,
            certified=certified,
            limit=limit,
            offset=offset,
        )
        payload = list_map_markers(db, filters)
        payload["region"] = {"id": region.id, "name": region.name}
        return JSONResponse(payload)

    @app.get("/admin/app-feed/regions/{region_id}/filter-options.json")
    def admin_region_filter_options_json(
        region_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> JSONResponse:
        region = get_region(db, region_id)
        if region is None:
            raise HTTPException(status_code=404, detail="Region not found.")
        payload = build_filter_options(db, region_id=region.id)
        payload["region"] = {"id": region.id, "name": region.name}
        return JSONResponse(payload)

    @app.get("/admin/app-feed/regions/{region_id}/discovery.json")
    def admin_region_discovery_json(
        region_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> JSONResponse:
        region = get_region(db, region_id)
        if region is None:
            raise HTTPException(status_code=404, detail="Region not found.")
        payload = list_discovery_slots(db, region_id=region.id)
        payload["region"] = {"id": region.id, "name": region.name}
        return JSONResponse(payload)

    @app.get("/admin/app-feed/events.json")
    def admin_app_feed_events_json(
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
        date_from: str | None = None,
        date_to: str | None = None,
        event_id: str | None = None,
        city: str | None = None,
        state_value: Annotated[str | None, Query(alias="state")] = None,
        country: str | None = None,
        genre: str | None = None,
        venue_id: str | None = None,
        poi_id: str | None = None,
        include_cancelled: str | None = None,
        include_needs_approval: str | None = "true",
        limit: str | None = None,
        offset: str | None = None,
    ) -> JSONResponse:
        filters = app_event_filters_from_values(
            event_id=event_id,
            date_from=date_from,
            date_to=date_to,
            city=city,
            state_value=state_value,
            country=country,
            genre=genre,
            venue_id=venue_id,
            poi_id=poi_id,
            include_cancelled=include_cancelled,
            include_needs_approval=include_needs_approval,
            limit=limit,
            offset=offset,
        )
        records = list_app_events(db, filters)
        return JSONResponse(
            {
                "export_type": "events",
                "count": len(records),
                "records": records,
            },
        )

    @app.get("/admin/app-feed/pois.json")
    def admin_app_feed_pois_json(
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
        category: str | None = None,
        subcategory: str | None = None,
        city: str | None = None,
        state_value: Annotated[str | None, Query(alias="state")] = None,
        country: str | None = None,
        has_upcoming_events: str | None = None,
        limit: str | None = None,
        offset: str | None = None,
    ) -> JSONResponse:
        filters = app_poi_filters_from_values(
            category=category,
            subcategory=subcategory,
            city=city,
            state_value=state_value,
            country=country,
            has_upcoming_events=has_upcoming_events,
            limit=limit,
            offset=offset,
        )
        records = list_app_pois(db, filters)
        return JSONResponse(
            {
                "export_type": "pois",
                "count": len(records),
                "records": records,
            },
        )

    @app.get("/admin/app-feed/venues.json")
    def admin_app_feed_venues_json(
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
        city: str | None = None,
        state_value: Annotated[str | None, Query(alias="state")] = None,
        country: str | None = None,
        limit: str | None = None,
        offset: str | None = None,
    ) -> JSONResponse:
        filters = app_event_filters_from_values(
            city=city,
            state_value=state_value,
            country=country,
            limit=limit,
            offset=offset,
        )
        records = list_app_venues(db, filters)
        return JSONResponse(
            {
                "export_type": "venues",
                "count": len(records),
                "records": records,
            },
        )

    @app.get("/admin/app-feed/map-markers.json")
    def admin_map_markers_json(
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
        entity_type: str | None = None,
        category: str | None = None,
        subcategory: str | None = None,
        region_id: str | None = None,
        city: str | None = None,
        state_value: Annotated[str | None, Query(alias="state")] = None,
        country: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        has_upcoming_events: str | None = None,
        certified: str | None = None,
        limit: str | None = None,
        offset: str | None = None,
    ) -> JSONResponse:
        filters = map_marker_filters_from_values(
            entity_type=entity_type,
            category=category,
            subcategory=subcategory,
            region_id=region_id,
            city=city,
            state_value=state_value,
            country=country,
            date_from=date_from,
            date_to=date_to,
            has_upcoming_events=has_upcoming_events,
            certified=certified,
            limit=limit,
            offset=offset,
        )
        return JSONResponse(list_map_markers(db, filters))

    @app.get("/admin/app-feed/filter-options.json")
    def admin_filter_options_json(
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
        region_id: str | None = None,
    ) -> JSONResponse:
        return JSONResponse(
            build_filter_options(db, region_id=parse_int_query(region_id)),
        )

    @app.get("/admin/app-feed/discovery.json")
    def admin_discovery_json(
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> JSONResponse:
        return JSONResponse(list_discovery_slots(db))

    @app.get("/admin/app-feed/latest/{export_type}.json")
    def admin_app_feed_latest_json(
        export_type: str,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        export = latest_successful_export(db, export_type)
        if export is None or not export.output_json:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No successful export found.",
            )
        return Response(
            content=export.output_json,
            media_type="application/json",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="app-feed-{export_type}.json"'
                ),
            },
        )

    @app.post("/admin/app-feed/export")
    def admin_app_feed_export(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        admin: Annotated[str, Depends(require_admin_csrf)],
        export_type: Annotated[str, Form()] = "full",
    ) -> Response:
        if export_type not in {"events", "pois", "venues", "full"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported export type.",
            )
        export_kind = cast(
            Literal["events", "pois", "venues", "full"],
            export_type,
        )
        export = create_app_feed_export(db, export_kind, admin)
        log_admin_action(
            db,
            settings=settings,
            request=request,
            actor_username=admin,
            action="app_feed_export",
            target_type="app_feed_export",
            target_id=export.id,
            metadata={"export_type": export.export_type, "status": export.status},
        )
        if export.status == "failure":
            return RedirectResponse(
                url=f"/admin/app-feed?error={export.error_message or 'Export failed'}",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        return RedirectResponse(
            url=f"/admin/app-feed?success=Generated {export.export_type} export",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/app-feed/export/background")
    def admin_app_feed_export_background(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        admin: Annotated[str, Depends(require_admin_csrf)],
        export_type: Annotated[str, Form()] = "full",
    ) -> Response:
        if export_type not in {"events", "pois", "venues", "full"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported export type.",
            )
        job = enqueue_job(
            db,
            "app_feed_export",
            {"export_type": export_type},
            created_by=admin,
        )
        log_admin_action(
            db,
            settings=settings,
            request=request,
            actor_username=admin,
            action="app_feed_export_queued",
            target_type="background_job",
            target_id=job.id,
            metadata={"export_type": export_type},
        )
        return RedirectResponse(
            url=f"/admin/jobs/{job.id}?success=Queued app feed export",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.get("/api/app/itineraries")
    def api_app_itineraries(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        region_id: str | None = None,
        artist_id: str | None = None,
    ) -> JSONResponse:
        require_private_app_feed_access(request)
        records = list_app_itineraries(
            db,
            region_id=parse_int_query(region_id),
            artist_id=parse_int_query(artist_id),
        )
        return JSONResponse({"count": len(records), "records": records})

    @app.get("/api/app/itineraries/{itinerary_id}")
    def api_app_itinerary_detail(
        itinerary_id: int,
        request: Request,
        db: Annotated[Session, Depends(get_db)],
    ) -> JSONResponse:
        require_private_app_feed_access(request)
        itinerary = get_itinerary(db, itinerary_id)
        if (
            itinerary is None
            or not itinerary.app_feed_ready
            or itinerary.status not in {"approved", "published"}
        ):
            raise HTTPException(status_code=404, detail="Itinerary not found.")
        return JSONResponse(build_itinerary_app_feed(db, itinerary))

    @app.get("/api/app/regions/{region_id}/itineraries")
    def api_app_region_itineraries(
        region_id: int,
        request: Request,
        db: Annotated[Session, Depends(get_db)],
    ) -> JSONResponse:
        require_private_app_feed_access(request)
        records = list_app_itineraries(db, region_id=region_id)
        return JSONResponse({"count": len(records), "records": records})

    @app.get("/api/app/artists/{artist_id}/itineraries")
    def api_app_artist_itineraries(
        artist_id: int,
        request: Request,
        db: Annotated[Session, Depends(get_db)],
    ) -> JSONResponse:
        require_private_app_feed_access(request)
        records = list_app_itineraries(db, artist_id=artist_id)
        return JSONResponse({"count": len(records), "records": records})

    @app.get("/api/app/events")
    def api_app_events(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        date_from: str | None = None,
        date_to: str | None = None,
        city: str | None = None,
        state_value: Annotated[str | None, Query(alias="state")] = None,
        country: str | None = None,
        genre: str | None = None,
        venue_id: str | None = None,
        poi_id: str | None = None,
        include_cancelled: str | None = None,
        include_needs_approval: str | None = "true",
        limit: str | None = None,
        offset: str | None = None,
    ) -> JSONResponse:
        require_private_app_feed_access(request)
        filters = app_event_filters_from_values(
            date_from=date_from,
            date_to=date_to,
            city=city,
            state_value=state_value,
            country=country,
            genre=genre,
            venue_id=venue_id,
            poi_id=poi_id,
            include_cancelled=include_cancelled,
            include_needs_approval=include_needs_approval,
            limit=limit,
            offset=offset,
        )
        records = list_app_events(db, filters)
        return JSONResponse({"count": len(records), "records": records})

    @app.get("/api/app/pois")
    def api_app_pois(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        category: str | None = None,
        subcategory: str | None = None,
        city: str | None = None,
        state_value: Annotated[str | None, Query(alias="state")] = None,
        country: str | None = None,
        has_upcoming_events: str | None = None,
        limit: str | None = None,
        offset: str | None = None,
    ) -> JSONResponse:
        require_private_app_feed_access(request)
        filters = app_poi_filters_from_values(
            category=category,
            subcategory=subcategory,
            city=city,
            state_value=state_value,
            country=country,
            has_upcoming_events=has_upcoming_events,
            limit=limit,
            offset=offset,
        )
        records = list_app_pois(db, filters)
        return JSONResponse({"count": len(records), "records": records})

    @app.get("/api/app/venues")
    def api_app_venues(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        city: str | None = None,
        state_value: Annotated[str | None, Query(alias="state")] = None,
        country: str | None = None,
        limit: str | None = None,
        offset: str | None = None,
    ) -> JSONResponse:
        require_private_app_feed_access(request)
        filters = app_event_filters_from_values(
            city=city,
            state_value=state_value,
            country=country,
            limit=limit,
            offset=offset,
        )
        records = list_app_venues(db, filters)
        return JSONResponse({"count": len(records), "records": records})

    @app.get("/api/app/search")
    def api_app_search(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        q: str | None = None,
        entity_type: str | None = None,
        category: str | None = None,
        subcategory: str | None = None,
        region_id: str | None = None,
        city: str | None = None,
        state_value: Annotated[str | None, Query(alias="state")] = None,
        country: str | None = None,
        app_feed_ready: str | None = None,
        certified: str | None = None,
        limit: str | None = None,
        offset: str | None = None,
    ) -> JSONResponse:
        require_private_app_feed_access(request)
        filters = app_search_filters_from_values(
            entity_type=entity_type,
            category=category,
            subcategory=subcategory,
            region_id=region_id,
            city=city,
            state_value=state_value,
            country=country,
            app_feed_ready=app_feed_ready,
            certified=certified,
        )
        payload = search_app_index(
            db,
            q or "",
            filters,
            limit=parse_int_query(limit) or 20,
            offset=parse_int_query(offset) or 0,
        )
        return JSONResponse(payload)

    @app.get("/api/app/search/suggest")
    def api_app_search_suggest(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        q: str | None = None,
        limit: str | None = None,
    ) -> JSONResponse:
        require_private_app_feed_access(request)
        return JSONResponse(
            suggest_app_search(db, q or "", limit=parse_int_query(limit) or 10),
        )

    @app.get("/api/app/map-markers")
    def api_app_map_markers(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        entity_type: str | None = None,
        category: str | None = None,
        subcategory: str | None = None,
        region_id: str | None = None,
        city: str | None = None,
        state_value: Annotated[str | None, Query(alias="state")] = None,
        country: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        has_upcoming_events: str | None = None,
        certified: str | None = None,
        limit: str | None = None,
        offset: str | None = None,
    ) -> JSONResponse:
        require_private_app_feed_access(request)
        filters = map_marker_filters_from_values(
            entity_type=entity_type,
            category=category,
            subcategory=subcategory,
            region_id=region_id,
            city=city,
            state_value=state_value,
            country=country,
            date_from=date_from,
            date_to=date_to,
            has_upcoming_events=has_upcoming_events,
            certified=certified,
            limit=limit,
            offset=offset,
        )
        return JSONResponse(list_map_markers(db, filters))

    @app.get("/api/app/regions/{region_id}/map-markers")
    def api_app_region_map_markers(
        region_id: int,
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        entity_type: str | None = None,
        category: str | None = None,
        subcategory: str | None = None,
        city: str | None = None,
        state_value: Annotated[str | None, Query(alias="state")] = None,
        country: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        has_upcoming_events: str | None = None,
        certified: str | None = None,
        limit: str | None = None,
        offset: str | None = None,
    ) -> JSONResponse:
        require_private_app_feed_access(request)
        filters = map_marker_filters_from_values(
            entity_type=entity_type,
            category=category,
            subcategory=subcategory,
            region_id=str(region_id),
            city=city,
            state_value=state_value,
            country=country,
            date_from=date_from,
            date_to=date_to,
            has_upcoming_events=has_upcoming_events,
            certified=certified,
            limit=limit,
            offset=offset,
        )
        return JSONResponse(list_map_markers(db, filters))

    @app.get("/api/app/filter-options")
    def api_app_filter_options(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        region_id: str | None = None,
    ) -> JSONResponse:
        require_private_app_feed_access(request)
        return JSONResponse(
            build_filter_options(db, region_id=parse_int_query(region_id)),
        )

    @app.get("/admin/api-feeds", response_class=HTMLResponse)
    def admin_api_feeds(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        app_settings = request.app.state.settings
        return admin_template_response(
            request,
            "api_feeds.html",
            {
                "page_title": "API Feed Review Workbench",
                "provider_summaries": provider_summaries(db, app_settings),
            },
        )

    @app.get("/admin/api-feeds/{provider_key}/pipeline", response_class=HTMLResponse)
    def admin_api_feed_provider_pipeline(
        request: Request,
        provider_key: str,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        context = provider_pipeline_context(
            db,
            request.app.state.settings,
            provider_key,
        )
        if context is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API feed provider not found.",
            )
        return admin_template_response(
            request,
            "provider_pipeline.html",
            {
                "page_title": f"{context.provider.display_name} Pipeline",
                "pipeline": context,
                "request_body_json": (
                    pretty_json_object(context.spec.request_preview.body)
                    if context.spec.request_preview.body is not None
                    else ""
                ),
                "sample_raw_json": pretty_json_object(context.spec.sample_raw),
                "sample_normalized_json": pretty_json_object(
                    context.spec.sample_normalized,
                ),
            },
        )

    @app.get("/admin/api-feeds/{provider_key}/mapping", response_class=HTMLResponse)
    def admin_api_feed_provider_mapping(
        request: Request,
        provider_key: str,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        context = provider_pipeline_context(
            db,
            request.app.state.settings,
            provider_key,
        )
        if context is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API feed provider not found.",
            )
        return admin_template_response(
            request,
            "provider_mapping.html",
            {
                "page_title": f"{context.provider.display_name} Mapping",
                "pipeline": context,
            },
        )

    @app.get("/admin/api-feeds/{provider_key}/pipeline.md")
    def admin_api_feed_provider_pipeline_markdown(
        provider_key: str,
        db: Annotated[Session, Depends(get_db)],
        request: Request,
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        context = provider_pipeline_context(
            db,
            request.app.state.settings,
            provider_key,
        )
        if context is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API feed provider not found.",
            )
        return Response(
            content=pipeline_export_markdown(context),
            media_type="text/markdown; charset=utf-8",
        )

    @app.get("/admin/api-feeds/{provider_key}/pipeline.json")
    def admin_api_feed_provider_pipeline_json(
        provider_key: str,
        db: Annotated[Session, Depends(get_db)],
        request: Request,
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        context = provider_pipeline_context(
            db,
            request.app.state.settings,
            provider_key,
        )
        if context is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API feed provider not found.",
            )
        return Response(
            content=pipeline_export_json(context),
            media_type="application/json",
        )

    @app.get(
        "/admin/api-feeds/{provider_key}/live-sandbox",
        response_class=HTMLResponse,
    )
    def admin_api_feed_live_sandbox(
        request: Request,
        provider_key: str,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
        error: str = "",
    ) -> Response:
        app_settings = request.app.state.settings
        provider = get_provider_config(app_settings, provider_key)
        if provider is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API feed provider not found.",
            )
        try:
            sandbox = live_sandbox_context_for_provider(app_settings, provider_key)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        return admin_template_response(
            request,
            "api_feed_live_sandbox.html",
            {
                "page_title": f"{provider.display_name} Live Sandbox",
                "provider": provider,
                "sandbox": sandbox,
                "request_preview_json": pretty_json_object(sandbox.request_preview),
                "recent_runs": live_sandbox_recent_runs(db, provider.provider_key),
                "error": error,
            },
        )

    @app.post("/admin/api-feeds/{provider_key}/live-sandbox")
    async def admin_api_feed_live_sandbox_run(
        request: Request,
        provider_key: str,
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        app_settings = request.app.state.settings
        provider = get_provider_config(app_settings, provider_key)
        if provider is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API feed provider not found.",
            )
        form_values = scalar_form_values(await request.form())
        http_client = cast(
            ProviderJsonClient | None,
            getattr(request.app.state, "provider_http_client", None),
        )
        try:
            if provider.provider_key == "jambase":
                run = run_jambase_live_sandbox(
                    db,
                    app_settings,
                    form_values,
                    requested_by=admin_user,
                    http_client=http_client,
                )
            elif provider.provider_key == CITYSPARK_PROVIDER_KEY:
                run = run_cityspark_live_sandbox(
                    db,
                    app_settings,
                    form_values,
                    requested_by=admin_user,
                    http_client=http_client,
                )
            else:
                raise ValueError(
                    "Live sandbox is only available for licensed event feeds."
                )
        except ValueError as exc:
            return RedirectResponse(
                url=(
                    f"/admin/api-feeds/{provider.provider_key}/live-sandbox"
                    f"?error={str(exc)}"
                ),
                status_code=status.HTTP_303_SEE_OTHER,
            )
        log_admin_action(
            db,
            settings=settings,
            request=request,
            actor_username=admin_user,
            action="provider_sandbox_run",
            target_type="api_feed_run",
            target_id=run.id,
            metadata={"provider_key": provider.provider_key, "run_mode": run.run_mode},
        )
        return RedirectResponse(
            url=f"/admin/api-feed-runs/{run.id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/api-feeds/{provider_key}/live-sandbox/background")
    async def admin_api_feed_live_sandbox_background(
        request: Request,
        provider_key: str,
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        provider = get_provider_config(request.app.state.settings, provider_key)
        if provider is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API feed provider not found.",
            )
        if provider.provider_key == "jambase":
            job_type = "provider_sandbox_jambase"
        elif provider.provider_key == CITYSPARK_PROVIDER_KEY:
            job_type = "provider_sandbox_cityspark"
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Live sandbox is only available for licensed event feeds.",
            )
        form_values = scalar_form_values(await request.form())
        job = enqueue_job(
            db,
            job_type,
            {"provider_key": provider.provider_key, "parameters": form_values},
            created_by=admin_user,
        )
        log_admin_action(
            db,
            settings=settings,
            request=request,
            actor_username=admin_user,
            action="provider_sandbox_queued",
            target_type="background_job",
            target_id=job.id,
            metadata={"provider_key": provider.provider_key},
        )
        return RedirectResponse(
            url=f"/admin/jobs/{job.id}?success=Queued provider sandbox job",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.get("/admin/api-feeds/{provider_key}", response_class=HTMLResponse)
    def admin_api_feed_provider(
        request: Request,
        provider_key: str,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
        error: str = "",
    ) -> Response:
        app_settings = request.app.state.settings
        provider = get_provider_config(app_settings, provider_key)
        if provider is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API feed provider not found.",
            )
        return admin_template_response(
            request,
            "api_feed_provider.html",
            {
                "page_title": provider.display_name,
                "provider": provider,
                "runs": list_api_feed_runs(db, provider.provider_key),
                "pending_records": list_api_feed_records(
                    db,
                    ApiFeedRecordFilters(
                        provider_key=provider.provider_key,
                        review_status="pending_review",
                    ),
                ),
                "error": error,
            },
        )

    @app.get("/admin/api-feed-records/{record_id}/lineage", response_class=HTMLResponse)
    def admin_api_feed_record_lineage(
        request: Request,
        record_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        lineage = record_lineage_context(
            db,
            request.app.state.settings,
            record_id,
        )
        if lineage is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API feed record not found.",
            )
        provider_display = (
            lineage.provider.display_name
            if lineage.provider
            else lineage.record.provider_key
        )
        return admin_template_response(
            request,
            "api_feed_record_lineage.html",
            {
                "page_title": f"API Feed Record #{lineage.record.id} Lineage",
                "lineage": lineage,
                "record": lineage.record,
                "provider_display": provider_display,
                "source_display_name": source_display_name,
                "source_docs_status": source_docs_status,
            },
        )

    @app.post("/admin/api-feeds/{provider_key}/run-demo-import")
    def admin_api_feed_run_demo_import(
        request: Request,
        provider_key: str,
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        try:
            run = run_demo_import(
                db,
                request.app.state.settings,
                provider_key,
                requested_by=admin_user,
            )
        except ValueError as exc:
            return RedirectResponse(
                url=f"/admin/api-feeds/{provider_key}?error={str(exc)}",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        log_admin_action(
            db,
            settings=settings,
            request=request,
            actor_username=admin_user,
            action="provider_demo_import",
            target_type="api_feed_run",
            target_id=run.id,
            metadata={"provider_key": provider_key},
        )
        return RedirectResponse(
            url=f"/admin/api-feed-runs/{run.id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/api-feeds/{provider_key}/upload-json")
    async def admin_api_feed_upload_json(
        request: Request,
        provider_key: str,
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
        upload_file: Annotated[UploadFile, File(...)],
    ) -> Response:
        filename = upload_file.filename or ""
        if not filename.lower().endswith(".json"):
            return RedirectResponse(
                url=f"/admin/api-feeds/{provider_key}?error=Upload must be .json",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        try:
            run = run_manual_json_import(
                db,
                request.app.state.settings,
                provider_key,
                await upload_file.read(),
                requested_by=admin_user,
            )
        except ValueError as exc:
            return RedirectResponse(
                url=f"/admin/api-feeds/{provider_key}?error={str(exc)}",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        log_admin_action(
            db,
            settings=settings,
            request=request,
            actor_username=admin_user,
            action="provider_json_upload",
            target_type="api_feed_run",
            target_id=run.id,
            metadata={"provider_key": provider_key, "filename": filename},
        )
        return RedirectResponse(
            url=f"/admin/api-feed-runs/{run.id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.get("/admin/api-feed-runs", response_class=HTMLResponse)
    def admin_api_feed_runs(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
        provider_key: str | None = None,
    ) -> Response:
        app_settings = request.app.state.settings
        return admin_template_response(
            request,
            "api_feed_runs.html",
            {
                "page_title": "API Feed Runs",
                "runs": list_api_feed_runs(db, provider_key),
                "providers": provider_registry(app_settings),
                "provider_display_name": lambda key: provider_display_name(
                    app_settings,
                    key,
                ),
            },
        )

    @app.get("/admin/api-feed-runs/{run_id}", response_class=HTMLResponse)
    def admin_api_feed_run_detail(
        request: Request,
        run_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
        ingestion_provider: str | None = None,
        upstream_event_source: str | None = None,
        ticketing_provider: str | None = None,
        ticket_link_classification: str | None = None,
        ticket_link_repair_strategy: str | None = None,
        provenance_flag: str | None = None,
        review_status: str | None = None,
        normalization_status: str | None = None,
        quality_issue: str | None = None,
        duplicate_status: str | None = None,
        missing_image: str | None = None,
        missing_ticket_link: str | None = None,
        missing_venue: str | None = None,
        compliance_expiring_soon: str | None = None,
        unknown_upstream_source: str | None = None,
        api_backfill_required: str | None = None,
        min_event_relevance_score: str | None = None,
        min_photo_quality_score: str | None = None,
    ) -> Response:
        run = get_api_feed_run(db, run_id)
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API feed run not found.",
            )
        app_settings = request.app.state.settings
        filters = api_record_filters_from_values(
            provider_key=run.provider_key,
            ingestion_provider=ingestion_provider,
            upstream_event_source=upstream_event_source,
            ticketing_provider=ticketing_provider,
            ticket_link_classification=ticket_link_classification,
            ticket_link_repair_strategy=ticket_link_repair_strategy,
            provenance_flag=provenance_flag,
            review_status=review_status,
            normalization_status=normalization_status,
            quality_issue=quality_issue,
            duplicate_status=duplicate_status,
            missing_image=missing_image,
            missing_ticket_link=missing_ticket_link,
            missing_venue=missing_venue,
            compliance_expiring_soon=compliance_expiring_soon,
            unknown_upstream_source=unknown_upstream_source,
            api_backfill_required=api_backfill_required,
            min_event_relevance_score=min_event_relevance_score,
            min_photo_quality_score=min_photo_quality_score,
        )
        return admin_template_response(
            request,
            "api_feed_run_detail.html",
            {
                "page_title": f"API Feed Run #{run.id}",
                "run": run,
                "provider": get_provider_config(app_settings, run.provider_key),
                "records": list_api_feed_records(db, filters, run_id=run.id),
                "filters": {
                    "ingestion_provider": ingestion_provider or "",
                    "upstream_event_source": upstream_event_source or "",
                    "ticketing_provider": ticketing_provider or "",
                    "ticket_link_classification": ticket_link_classification or "",
                    "ticket_link_repair_strategy": ticket_link_repair_strategy or "",
                    "provenance_flag": provenance_flag or "",
                    "review_status": review_status or "",
                    "normalization_status": normalization_status or "",
                    "quality_issue": quality_issue or "",
                    "duplicate_status": duplicate_status or "",
                    "missing_image": missing_image or "",
                    "missing_ticket_link": missing_ticket_link or "",
                    "missing_venue": missing_venue or "",
                    "compliance_expiring_soon": compliance_expiring_soon or "",
                    "unknown_upstream_source": unknown_upstream_source or "",
                    "api_backfill_required": api_backfill_required or "",
                    "min_event_relevance_score": min_event_relevance_score or "",
                    "min_photo_quality_score": min_photo_quality_score or "",
                },
                "provider_display_name": lambda key: provider_display_name(
                    app_settings,
                    key,
                ),
            },
        )

    @app.post("/admin/api-feed-runs/{run_id}/photo-rescue")
    def admin_api_feed_run_photo_rescue(
        run_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        run = get_api_feed_run(db, run_id)
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API feed run not found.",
            )
        run_photo_rescue_for_api_feed_run(db, run_id)
        return RedirectResponse(
            url=f"/admin/api-feed-runs/{run_id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/api-feed-runs/{run_id}/photo-rescue/background")
    def admin_api_feed_run_photo_rescue_background(
        run_id: int,
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        run = get_api_feed_run(db, run_id)
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API feed run not found.",
            )
        job = enqueue_job(
            db,
            "api_feed_run_photo_rescue",
            {"api_feed_run_id": run_id},
            created_by=admin_user,
        )
        return RedirectResponse(
            url=f"/admin/jobs/{job.id}?success=Queued API feed photo rescue job",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.get("/admin/api-feed-records/{record_id}", response_class=HTMLResponse)
    def admin_api_feed_record_detail(
        request: Request,
        record_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
        error: str = "",
    ) -> Response:
        record = get_api_feed_record(db, record_id)
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API feed record not found.",
            )
        app_settings = request.app.state.settings
        provider = get_provider_config(app_settings, record.provider_key)
        provider_image_candidates_preview = provider_image_inputs_for_record(
            record,
            event_id=record.created_event_id,
        )
        return admin_template_response(
            request,
            "api_feed_record_detail.html",
            {
                "page_title": f"API Feed Record #{record.id}",
                "record": record,
                "provider": provider,
                "provider_display": (
                    provider.display_name if provider else record.provider_key
                ),
                "raw_preview": record.raw_payload_json[:5000],
                "normalized_preview": record.normalized_payload_json[:5000],
                "source_display_name": source_display_name,
                "source_docs_status": source_docs_status,
                "incoming_image_is_direct": (
                    is_likely_direct_image_asset(record.main_image_url)
                    if record.main_image_url
                    else False
                ),
                "provider_image_candidates_preview": (
                    provider_image_candidates_preview
                ),
                "error": error,
            },
        )

    @app.post("/admin/api-feed-records/{record_id}/create-image-candidate")
    def admin_api_feed_record_create_image_candidate(
        record_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        record = get_api_feed_record(db, record_id)
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API feed record not found.",
            )
        provider_image_candidates = provider_image_inputs_for_record(
            record,
            event_id=record.created_event_id,
        )
        if not provider_image_candidates:
            return RedirectResponse(
                url=(
                    f"/admin/api-feed-records/{record.id}"
                    "?error=No provider image URLs found."
                ),
                status_code=status.HTTP_303_SEE_OTHER,
            )
        if record.created_event_id:
            create_provider_image_candidates_for_record(
                db,
                record,
                record.created_event_id,
                commit=False,
            )
            run_event_photo_rescue(db, record.created_event_id, commit=False)
            db.commit()
            return RedirectResponse(
                url=f"/admin/events/{record.created_event_id}",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        for payload in provider_image_candidates:
            create_image_candidate(db, payload, commit=False)
        db.commit()
        return RedirectResponse(
            url="/admin/image-candidates?source_type=provider&needs_approval=1",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/api-feed-records/{record_id}/photo-rescue")
    def admin_api_feed_record_photo_rescue(
        record_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        record = get_api_feed_record(db, record_id)
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API feed record not found.",
            )
        if not record.created_event_id:
            return RedirectResponse(
                url=(
                    f"/admin/api-feed-records/{record.id}"
                    "?error=Approve the record before running photo rescue."
                ),
                status_code=status.HTTP_303_SEE_OTHER,
            )
        run_event_photo_rescue(db, record.created_event_id)
        return RedirectResponse(
            url=f"/admin/events/{record.created_event_id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/api-feed-records/{record_id}/approve")
    def admin_api_feed_record_approve(
        request: Request,
        record_id: int,
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        try:
            record = approve_api_feed_record(
                db,
                request.app.state.settings,
                record_id,
            )
        except PermissionError as exc:
            return RedirectResponse(
                url=f"/admin/api-feed-records/{record_id}?error={str(exc)}",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        log_admin_action(
            db,
            settings=settings,
            request=request,
            actor_username=admin_user,
            action="api_feed_record_approve",
            target_type="api_feed_record",
            target_id=record.id,
            metadata={"created_event_id": record.created_event_id},
        )
        return RedirectResponse(
            url=f"/admin/api-feed-records/{record.id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/api-feed-records/{record_id}/hold")
    def admin_api_feed_record_hold(
        request: Request,
        record_id: int,
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        record = update_api_feed_record_review_status(db, record_id, "held")
        log_admin_action(
            db,
            settings=settings,
            request=request,
            actor_username=admin_user,
            action="api_feed_record_hold",
            target_type="api_feed_record",
            target_id=record.id,
        )
        return RedirectResponse(
            url=f"/admin/api-feed-records/{record.id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/api-feed-records/{record_id}/reject")
    def admin_api_feed_record_reject(
        request: Request,
        record_id: int,
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        record = update_api_feed_record_review_status(db, record_id, "rejected")
        log_admin_action(
            db,
            settings=settings,
            request=request,
            actor_username=admin_user,
            action="api_feed_record_reject",
            target_type="api_feed_record",
            target_id=record.id,
        )
        return RedirectResponse(
            url=f"/admin/api-feed-records/{record.id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/api-feed-records/{record_id}/send-to-enrichment")
    def admin_api_feed_record_send_to_enrichment(
        record_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        record = update_api_feed_record_review_status(
            db,
            record_id,
            "needs_enrichment",
        )
        return RedirectResponse(
            url=f"/admin/api-feed-records/{record.id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.get("/admin/crawl-queue", response_class=HTMLResponse)
    def admin_crawl_queue(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        rows = crawl_queue_rows(db)
        return admin_template_response(
            request,
            "crawl_queue.html",
            {
                "page_title": "Crawl Queue",
                "rows": rows,
                "frequencies": CRAWL_FREQUENCIES,
                "due_count": sum(row.is_due_for_crawl for row in rows),
                "never_crawled_count": sum(row.last_crawl is None for row in rows),
                "failed_count": sum(
                    row.last_crawl_status == "failure" for row in rows
                ),
            },
        )

    @app.post("/admin/crawl-queue/run-due", response_class=HTMLResponse)
    def admin_crawl_queue_run_due(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        source_ids = [row.source.id for row in due_crawl_rows(db)]
        summary = run_bulk_crawl_for_master_ids(
            db,
            source_ids,
            fetcher=request.app.state.fetch_calendar_url,
            title="Run All Due Sources",
        )
        return admin_template_response(
            request,
            "bulk_crawl_summary.html",
            {"page_title": summary.title, "summary": summary},
        )

    @app.post("/admin/crawl-queue/run-due/background")
    def admin_crawl_queue_run_due_background(
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        job = enqueue_job(
            db,
            "scheduled_crawl_due_sources",
            {"title": "Background Run All Due Sources"},
            created_by=admin_user,
        )
        return RedirectResponse(
            url=f"/admin/jobs/{job.id}?success=Queued due-source crawl job",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/crawl-queue/bulk-action")
    async def admin_crawl_queue_bulk_action(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        form = await request.form()
        source_ids = selected_source_ids_from_form(form)
        action = str(form.get("action") or "")
        if action == "run-selected":
            summary = run_bulk_crawl_for_master_ids(
                db,
                source_ids,
                fetcher=request.app.state.fetch_calendar_url,
                title="Run Selected Queue Sources",
            )
            return admin_template_response(
                request,
                "bulk_crawl_summary.html",
                {"page_title": summary.title, "summary": summary},
            )
        if action == "run-selected-background":
            job = enqueue_job(
                db,
                "bulk_crawl",
                {
                    "source_ids": source_ids,
                    "title": "Background Crawl Queue Selection",
                },
                created_by=admin_user,
            )
            return RedirectResponse(
                url=f"/admin/jobs/{job.id}?success=Queued selected crawl job",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        if action == "pause-selected":
            pause_selected_sources(db, source_ids)
        elif action == "change-frequency":
            update_selected_crawl_frequency(
                db,
                source_ids,
                str(form.get("crawl_frequency") or "manual"),
            )
        return RedirectResponse(
            url="/admin/crawl-queue",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.get("/admin/master-calendar-sources", response_class=HTMLResponse)
    def admin_master_calendar_sources(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
        status_value: Annotated[str, Query(alias="status")] = "",
        review_status: str | None = None,
        crawl_frequency: str | None = None,
        city: str | None = None,
        state_value: Annotated[str, Query(alias="state")] = "",
        region_or_market: str | None = None,
        source_type: str | None = None,
        organization: str | None = None,
        last_crawl_status: str | None = None,
        due_for_crawl: str | None = None,
        risk_level: str | None = None,
    ) -> Response:
        filters = master_source_filters_from_values(
            status_value=status_value,
            review_status=review_status,
            crawl_frequency=crawl_frequency,
            city=city,
            state_value=state_value,
            region_or_market=region_or_market,
            source_type=source_type,
            organization=organization,
            last_crawl_status=last_crawl_status,
            due_for_crawl=due_for_crawl,
            risk_level=risk_level,
        )
        all_rows = list_master_source_metadata(db)
        rows = list_master_source_metadata(db, filters)
        return admin_template_response(
            request,
            "master_calendar_sources.html",
            {
                "page_title": "Master Calendar Sources",
                "rows": rows,
                "sources": [row.source for row in rows],
                "submission_counts": master_submission_counts(db),
                "summary": {
                    "total": len(all_rows),
                    "approved": sum(
                        1 for row in all_rows if row.source.status == "approved"
                    ),
                    "due_now": sum(1 for row in all_rows if row.is_due_for_crawl),
                    "failed_last_crawl": sum(
                        1 for row in all_rows if row.last_crawl_status == "failure"
                    ),
                    "pending_review": sum(
                        1
                        for row in all_rows
                        if row.source.review_status == "pending_review"
                    ),
                    "never_crawled": sum(
                        1 for row in all_rows if row.last_crawl is None
                    ),
                },
                "filters": {
                    "status": status_value or "",
                    "review_status": review_status or "",
                    "crawl_frequency": crawl_frequency or "",
                    "city": city or "",
                    "state": state_value or "",
                    "region_or_market": region_or_market or "",
                    "source_type": source_type or "",
                    "organization": organization or "",
                    "last_crawl_status": last_crawl_status or "",
                    "due_for_crawl": "1" if filters.due_for_crawl else "",
                    "risk_level": risk_level or "",
                },
                "filter_query": filters.as_query_string(),
                "frequencies": CRAWL_FREQUENCIES,
            },
        )

    @app.post("/admin/master-calendar-sources/bulk-crawl")
    async def admin_bulk_crawl_master_sources(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        form = await request.form()
        source_ids = selected_source_ids_from_form(form)
        summary = run_bulk_crawl_for_master_ids(
            db,
            source_ids,
            fetcher=request.app.state.fetch_calendar_url,
            title="Bulk Crawl Selected Sources",
        )
        return admin_template_response(
            request,
            "bulk_crawl_summary.html",
            {"page_title": summary.title, "summary": summary},
        )

    @app.post("/admin/master-calendar-sources/bulk-crawl/background")
    async def admin_bulk_crawl_master_sources_background(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        form = await request.form()
        source_ids = selected_source_ids_from_form(form)
        job = enqueue_job(
            db,
            "bulk_crawl",
            {
                "source_ids": source_ids,
                "title": "Background Bulk Crawl Selected Sources",
            },
            created_by=admin_user,
        )
        return RedirectResponse(
            url=f"/admin/jobs/{job.id}?success=Queued bulk crawl job",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/master-calendar-sources/bulk-crawl-filter")
    def admin_bulk_crawl_master_sources_by_filter(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin_csrf)],
        status_value: Annotated[str, Form(alias="status")] = "",
        review_status: Annotated[str, Form()] = "",
        crawl_frequency: Annotated[str, Form()] = "",
        city: Annotated[str, Form()] = "",
        state_value: Annotated[str, Form(alias="state")] = "",
        region_or_market: Annotated[str, Form()] = "",
        source_type: Annotated[str, Form()] = "",
        organization: Annotated[str, Form()] = "",
        last_crawl_status: Annotated[str, Form()] = "",
        due_for_crawl: Annotated[str, Form()] = "",
        risk_level: Annotated[str, Form()] = "",
    ) -> Response:
        filters = master_source_filters_from_values(
            status_value=status_value,
            review_status=review_status,
            crawl_frequency=crawl_frequency,
            city=city,
            state_value=state_value,
            region_or_market=region_or_market,
            source_type=source_type,
            organization=organization,
            last_crawl_status=last_crawl_status,
            due_for_crawl=due_for_crawl,
            risk_level=risk_level,
        )
        rows = list_master_source_metadata(db, filters)
        summary = run_bulk_crawl_for_master_ids(
            db,
            [row.source.id for row in rows],
            fetcher=request.app.state.fetch_calendar_url,
            title="Bulk Crawl Filtered Sources",
        )
        return admin_template_response(
            request,
            "bulk_crawl_summary.html",
            {"page_title": summary.title, "summary": summary},
        )

    @app.get("/admin/master-calendar-sources/{source_id}", response_class=HTMLResponse)
    def admin_master_calendar_source_detail(
        request: Request,
        source_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        source = get_master_calendar_source(db, source_id)
        if source is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Master calendar source not found.",
            )
        return admin_template_response(
            request,
            "master_calendar_source_detail.html",
            {
                "page_title": source.source_name,
                "source": source,
                "crawl_metadata": metadata_for_master_source(db, source),
                "submissions": list_master_submissions(db, source.id),
                "submission_count": count_master_submissions(db, source.id),
            },
        )

    @app.post("/admin/master-calendar-sources/{source_id}/status")
    def admin_update_master_calendar_source_status(
        request: Request,
        source_id: int,
        action: Annotated[str, Form(...)],
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        source = update_master_status(db, source_id, action)
        if source is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Master calendar source not found.",
            )
        log_admin_action(
            db,
            settings=settings,
            request=request,
            actor_username=admin_user,
            action=f"master_source_{action}",
            target_type="master_calendar_source",
            target_id=source.id,
            metadata={"status": source.status, "review_status": source.review_status},
        )
        return RedirectResponse(
            url="/admin/master-calendar-sources",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.get("/admin/import-batches", response_class=HTMLResponse)
    def admin_import_batches(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        return admin_template_response(
            request,
            "import_batches.html",
            {
                "page_title": "Import Batches",
                "batches": list_import_batches(db),
            },
        )

    @app.get("/admin/import-batches/{batch_id}", response_class=HTMLResponse)
    def admin_import_batch_detail(
        request: Request,
        batch_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        batch = get_import_batch(db, batch_id)
        if batch is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Import batch not found.",
            )
        event_rows = []
        source_rows = []
        if batch.submission_type == "concert_events_file":
            event_rows = staged_events_for_batch(db, batch.id)
        elif batch.submission_type == "calendar_sources_file":
            source_rows = staged_sources_for_batch(db, batch.id)
        return admin_template_response(
            request,
            "import_batch_detail.html",
            {
                "page_title": f"Import Batch #{batch.id}",
                "batch": batch,
                "event_rows": event_rows,
                "source_rows": source_rows,
            },
        )

    @app.post("/admin/import-batches/{batch_id}/approve-valid-rows")
    def admin_approve_import_batch_valid_rows(
        batch_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        batch = get_import_batch(db, batch_id)
        if batch is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Import batch not found.",
            )
        if batch.submission_type == "concert_events_file":
            approve_valid_staged_events(db, batch.id)
        elif batch.submission_type == "calendar_sources_file":
            approve_valid_staged_calendar_sources(db, batch.id)
        return RedirectResponse(
            url=f"/admin/import-batches/{batch_id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/import-batches/{batch_id}/crawl-approved-sources")
    def admin_crawl_import_batch_sources(
        request: Request,
        batch_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        batch = get_import_batch(db, batch_id)
        if batch is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Import batch not found.",
            )
        source_ids = master_source_ids_for_import_batch(db, batch_id)
        summary = run_bulk_crawl_for_master_ids(
            db,
            source_ids,
            fetcher=request.app.state.fetch_calendar_url,
            title=f"Import Batch #{batch_id} Crawl Summary",
        )
        return admin_template_response(
            request,
            "bulk_crawl_summary.html",
            {"page_title": summary.title, "summary": summary, "batch": batch},
        )

    @app.post("/admin/import-batches/{batch_id}/crawl-approved-sources/background")
    def admin_crawl_import_batch_sources_background(
        batch_id: int,
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        batch = get_import_batch(db, batch_id)
        if batch is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Import batch not found.",
            )
        source_ids = master_source_ids_for_import_batch(db, batch_id)
        job = enqueue_job(
            db,
            "bulk_crawl",
            {
                "source_ids": source_ids,
                "title": f"Import Batch #{batch_id} Background Crawl",
                "import_batch_id": batch_id,
            },
            created_by=admin_user,
        )
        return RedirectResponse(
            url=f"/admin/jobs/{job.id}?success=Queued import batch crawl job",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/import-batches/{batch_id}/review")
    def admin_review_import_batch(
        batch_id: int,
        action: Annotated[str, Form(...)],
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        batch = reject_or_quarantine_batch(db, batch_id, action)
        if batch is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Import batch not found.",
            )
        return RedirectResponse(
            url=f"/admin/import-batches/{batch_id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.get("/admin/sources", response_class=HTMLResponse)
    def admin_sources(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        sources = list_calendar_sources(db)
        return admin_template_response(
            request,
            "admin_sources.html",
            {
                "page_title": "Admin Sources",
                "sources": sources,
                "statuses": list(SourceStatus),
            },
        )

    @app.get("/admin/suspicious-submissions", response_class=HTMLResponse)
    def admin_suspicious_submissions(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        suspicious_sources = list_suspicious_calendar_sources(db)
        return admin_template_response(
            request,
            "suspicious_submissions.html",
            {
                "page_title": "Suspicious Submissions",
                "sources": suspicious_sources,
            },
        )

    @app.post("/admin/suspicious-submissions/{source_id}/review")
    def admin_review_suspicious_submission(
        request: Request,
        source_id: int,
        action: Annotated[str, Form(...)],
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
        review_notes: Annotated[str, Form()] = "",
    ) -> Response:
        source = review_calendar_source(
            db,
            source_id=source_id,
            action=action,
            notes=review_notes or None,
            reviewed_by=admin_user,
        )
        if source is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Suspicious submission not found.",
            )
        log_admin_action(
            db,
            settings=settings,
            request=request,
            actor_username=admin_user,
            action=f"suspicious_submission_{action}",
            target_type="calendar_source",
            target_id=source.id,
            metadata={"review_status": source.review_status},
        )
        return RedirectResponse(
            url="/admin/suspicious-submissions",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/sources/{source_id}/status")
    def admin_update_source_status(
        request: Request,
        source_id: int,
        status_value: Annotated[str, Form(alias="status")],
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        try:
            status_update = SourceStatusUpdate(status=status_value)
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=validation_error_map(exc),
            ) from exc

        source = update_source_status(
            db,
            source_id=source_id,
            status=SourceStatus(status_update.status),
        )
        if source is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Calendar source not found.",
            )
        log_admin_action(
            db,
            settings=settings,
            request=request,
            actor_username=admin_user,
            action=f"source_{status_update.status}",
            target_type="calendar_source",
            target_id=source.id,
            metadata={"status": source.status, "review_status": source.review_status},
        )
        return RedirectResponse(
            url="/admin/sources",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/sources/{source_id}/crawl")
    def admin_run_crawl(
        request: Request,
        source_id: int,
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        try:
            crawl_run = run_manual_crawl(
                db,
                source_id=source_id,
                fetcher=request.app.state.fetch_calendar_url,
            )
        except SourceNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Calendar source not found.",
            ) from exc
        except SourceNotApprovedError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only approved sources can be crawled.",
            ) from exc
        log_admin_action(
            db,
            settings=settings,
            request=request,
            actor_username=admin_user,
            action="run_crawl",
            target_type="crawl_run",
            target_id=crawl_run.id,
            metadata={"source_id": source_id, "status": crawl_run.status},
        )

        return RedirectResponse(
            url=f"/admin/crawl-runs/{crawl_run.id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.get("/admin/crawl-runs", response_class=HTMLResponse)
    def admin_crawl_runs(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        crawl_runs = list_crawl_runs(db)
        return admin_template_response(
            request,
            "crawl_runs.html",
            {
                "page_title": "Crawl Runs",
                "crawl_runs": crawl_runs,
            },
        )

    @app.get("/admin/crawl-runs/{crawl_run_id}", response_class=HTMLResponse)
    def admin_crawl_run_detail(
        request: Request,
        crawl_run_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        crawl_run = get_crawl_run(db, crawl_run_id)
        if crawl_run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Crawl run not found.",
            )
        raw_body = crawl_run.raw_response_body or ""
        return admin_template_response(
            request,
            "crawl_run_detail.html",
            {
                "page_title": f"Crawl Run #{crawl_run.id}",
                "crawl_run": crawl_run,
                "extracted_event_count": count_events_for_crawl_run(
                    db,
                    crawl_run.id,
                ),
                "extracted_candidates": extracted_candidates_for_crawl_run(
                    db,
                    crawl_run.id,
                ),
                "discovered_links": crawl_run.discovered_links,
                "is_ics_crawl": appears_to_be_ics(crawl_run),
                "raw_preview": raw_body[:5000],
                "raw_was_truncated": len(raw_body) > 5000,
            },
        )

    @app.post("/admin/crawl-runs/{crawl_run_id}/extracted-events/approve-selected")
    async def admin_crawl_run_approve_extracted_events(
        request: Request,
        crawl_run_id: int,
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        form = await request.form()
        approved_count = 0
        for raw_id in form.getlist("candidate_ids"):
            try:
                approve_extracted_event_candidate(
                    db,
                    int(str(raw_id)),
                    approved_by=admin_user,
                )
            except (ValueError, TypeError):
                continue
            approved_count += 1
        log_admin_action(
            db,
            settings=settings,
            request=request,
            actor_username=admin_user,
            action="extracted_event_approve_selected",
            target_type="crawl_run",
            target_id=crawl_run_id,
            metadata={"approved_count": approved_count},
        )
        return RedirectResponse(
            url=(
                f"/admin/crawl-runs/{crawl_run_id}"
                f"?success=Approved {approved_count} extracted events"
            ),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/crawl-runs/{crawl_run_id}/extracted-events/reject-selected")
    async def admin_crawl_run_reject_extracted_events(
        request: Request,
        crawl_run_id: int,
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        form = await request.form()
        rejected_count = 0
        for raw_id in form.getlist("candidate_ids"):
            try:
                reject_extracted_event_candidate(db, int(str(raw_id)))
            except (ValueError, TypeError):
                continue
            rejected_count += 1
        log_admin_action(
            db,
            settings=settings,
            request=request,
            actor_username=admin_user,
            action="extracted_event_reject_selected",
            target_type="crawl_run",
            target_id=crawl_run_id,
            metadata={"rejected_count": rejected_count},
        )
        return RedirectResponse(
            url=(
                f"/admin/crawl-runs/{crawl_run_id}"
                f"?success=Rejected {rejected_count} extracted events"
            ),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.get("/admin/extracted-events", response_class=HTMLResponse)
    def admin_extracted_events(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
        review_status: str | None = None,
    ) -> Response:
        return admin_template_response(
            request,
            "extracted_events.html",
            {
                "page_title": "Extracted Event Candidates",
                "candidates": list_extracted_event_candidates(db, review_status),
                "filters": {"review_status": review_status or ""},
            },
        )

    @app.get("/admin/extracted-events/{candidate_id}", response_class=HTMLResponse)
    def admin_extracted_event_detail(
        request: Request,
        candidate_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        candidate = get_extracted_event_candidate(db, candidate_id)
        if candidate is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Extracted event candidate not found.",
            )
        return admin_template_response(
            request,
            "extracted_event_detail.html",
            {
                "page_title": f"Extracted Candidate #{candidate.id}",
                "candidate": candidate,
                "raw_preview": pretty_json_object(candidate.raw_fragment),
                "normalized_preview": pretty_json_object(
                    candidate.normalized_payload,
                ),
                "source_claim_preview": pretty_json_object(
                    candidate.source_claim_preview,
                ),
            },
        )

    @app.post("/admin/extracted-events/{candidate_id}/approve")
    def admin_extracted_event_approve(
        request: Request,
        candidate_id: int,
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        try:
            event = approve_extracted_event_candidate(
                db,
                candidate_id,
                approved_by=admin_user,
            )
        except ValueError as exc:
            return RedirectResponse(
                url=f"/admin/extracted-events/{candidate_id}?error={exc}",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        log_admin_action(
            db,
            settings=settings,
            request=request,
            actor_username=admin_user,
            action="extracted_event_approve",
            target_type="extracted_event_candidate",
            target_id=candidate_id,
            metadata={"event_id": event.id},
        )
        return RedirectResponse(
            url=f"/admin/events/{event.id}?success=Approved extracted event",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/extracted-events/{candidate_id}/approve/background")
    def admin_extracted_event_approve_background(
        candidate_id: int,
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        if get_extracted_event_candidate(db, candidate_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Extracted event candidate not found.",
            )
        job = enqueue_job(
            db,
            "approve_extracted_event_candidate",
            {"candidate_id": candidate_id},
            created_by=admin_user,
        )
        return RedirectResponse(
            url=f"/admin/jobs/{job.id}?success=Queued extracted event approval",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/extracted-events/{candidate_id}/reject")
    def admin_extracted_event_reject(
        request: Request,
        candidate_id: int,
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        reject_extracted_event_candidate(db, candidate_id)
        log_admin_action(
            db,
            settings=settings,
            request=request,
            actor_username=admin_user,
            action="extracted_event_reject",
            target_type="extracted_event_candidate",
            target_id=candidate_id,
        )
        return RedirectResponse(
            url="/admin/extracted-events?success=Rejected extracted event",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/extracted-events/{candidate_id}/duplicate-review")
    def admin_extracted_event_duplicate_review(
        candidate_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        send_extracted_event_to_duplicate_review(db, candidate_id)
        return RedirectResponse(
            url=(
                f"/admin/extracted-events/{candidate_id}"
                "?success=Sent to duplicate review"
            ),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.get("/admin/image-candidates", response_class=HTMLResponse)
    def admin_image_candidates(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
        event_id: str | None = None,
        venue_id: str | None = None,
        source_type: str | None = None,
        source_provider: str | None = None,
        candidate_status: str | None = None,
        clearance_status: str | None = None,
        image_role: str | None = None,
        quality_flag: str | None = None,
        stock_placeholder_candidate: str | None = None,
        text_detected: str | None = None,
        watermark_detected: str | None = None,
        poster_or_flyer: str | None = None,
        missing_dimensions: str | None = None,
        low_resolution: str | None = None,
        needs_approval: str | None = None,
        selected: str | None = None,
        selected_pending_approval: str | None = None,
        selected_and_cleared: str | None = None,
        selected_but_needs_approval: str | None = None,
        hard_blocked: str | None = None,
        missing_image: str | None = None,
        rescue_source: str | None = None,
        source_evidence_only: str | None = None,
        can_be_final_image: str | None = None,
        selected_by_rescue: str | None = None,
        missing_artist_image: str | None = None,
    ) -> Response:
        filters = image_candidate_filters_from_values(
            event_id=event_id,
            venue_id=venue_id,
            source_type=source_type,
            source_provider=source_provider,
            candidate_status=candidate_status,
            clearance_status=clearance_status,
            image_role=image_role,
            quality_flag=quality_flag,
            stock_placeholder_candidate=stock_placeholder_candidate,
            text_detected=text_detected,
            watermark_detected=watermark_detected,
            poster_or_flyer=poster_or_flyer,
            missing_dimensions=missing_dimensions,
            low_resolution=low_resolution,
            needs_approval=needs_approval,
            selected=selected,
            selected_pending_approval=selected_pending_approval,
            selected_and_cleared=selected_and_cleared,
            selected_but_needs_approval=selected_but_needs_approval,
            hard_blocked=hard_blocked,
            missing_image=missing_image,
            rescue_source=rescue_source,
            source_evidence_only=source_evidence_only,
            can_be_final_image=can_be_final_image,
            selected_by_rescue=selected_by_rescue,
            missing_artist_image=missing_artist_image,
        )
        return admin_template_response(
            request,
            "image_candidates.html",
            {
                "page_title": "Image Candidates",
                "candidates": list_image_candidates(db, filters),
                "filters": {
                    "event_id": event_id or "",
                    "venue_id": venue_id or "",
                    "source_type": source_type or "",
                    "source_provider": source_provider or "",
                    "candidate_status": candidate_status or "",
                    "clearance_status": clearance_status or "",
                    "image_role": image_role or "",
                    "quality_flag": quality_flag or "",
                    "stock_placeholder_candidate": stock_placeholder_candidate or "",
                    "text_detected": text_detected or "",
                    "watermark_detected": watermark_detected or "",
                    "poster_or_flyer": poster_or_flyer or "",
                    "missing_dimensions": missing_dimensions or "",
                    "low_resolution": low_resolution or "",
                    "needs_approval": needs_approval or "",
                    "selected": selected or "",
                    "selected_pending_approval": selected_pending_approval or "",
                    "selected_and_cleared": selected_and_cleared or "",
                    "selected_but_needs_approval": (
                        selected_but_needs_approval or ""
                    ),
                    "hard_blocked": hard_blocked or "",
                    "missing_image": missing_image or "",
                    "rescue_source": rescue_source or "",
                    "source_evidence_only": source_evidence_only or "",
                    "can_be_final_image": can_be_final_image or "",
                    "selected_by_rescue": selected_by_rescue or "",
                    "missing_artist_image": missing_artist_image or "",
                },
                "image_roles": IMAGE_ROLES,
            },
        )

    @app.post("/admin/image-candidates/photo-rescue/recent-approved")
    def admin_image_candidates_photo_rescue_recent_approved(
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        run_photo_rescue_for_recently_approved_events(db)
        return RedirectResponse(
            url="/admin/image-candidates?selected_by_rescue=1",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/image-candidates/photo-rescue/recent-approved/background")
    def admin_image_candidates_photo_rescue_recent_approved_background(
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        job = enqueue_job(
            db,
            "recent_events_photo_rescue",
            {"since_hours": 168, "limit": 100},
            created_by=admin_user,
        )
        return RedirectResponse(
            url=f"/admin/jobs/{job.id}?success=Queued recent event photo rescue job",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/image-candidates/{candidate_id}/accept")
    def admin_image_candidate_accept(
        request: Request,
        candidate_id: int,
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        update_candidate_review(
            db,
            candidate_id,
            reviewed_by=admin_user,
            candidate_status="accepted",
        )
        log_admin_action(
            db,
            settings=settings,
            request=request,
            actor_username=admin_user,
            action="image_candidate_accept",
            target_type="image_candidate",
            target_id=candidate_id,
        )
        return RedirectResponse(
            url=request.headers.get("referer") or "/admin/image-candidates",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/image-candidates/{candidate_id}/reject")
    def admin_image_candidate_reject(
        request: Request,
        candidate_id: int,
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        update_candidate_review(
            db,
            candidate_id,
            reviewed_by=admin_user,
            candidate_status="rejected",
        )
        log_admin_action(
            db,
            settings=settings,
            request=request,
            actor_username=admin_user,
            action="image_candidate_reject",
            target_type="image_candidate",
            target_id=candidate_id,
        )
        return RedirectResponse(
            url=request.headers.get("referer") or "/admin/image-candidates",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/image-candidates/{candidate_id}/needs-review")
    def admin_image_candidate_needs_review(
        request: Request,
        candidate_id: int,
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        update_candidate_review(
            db,
            candidate_id,
            reviewed_by=admin_user,
            candidate_status="needs_review",
        )
        return RedirectResponse(
            url=request.headers.get("referer") or "/admin/image-candidates",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/image-candidates/{candidate_id}/needs-approval")
    def admin_image_candidate_needs_approval(
        request: Request,
        candidate_id: int,
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        update_candidate_review(
            db,
            candidate_id,
            reviewed_by=admin_user,
            candidate_status="needs_approval",
            clearance_status="needs_approval",
        )
        return RedirectResponse(
            url=request.headers.get("referer") or "/admin/image-candidates",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/image-candidates/{candidate_id}/clearance-approved")
    def admin_image_candidate_clearance_approved(
        request: Request,
        candidate_id: int,
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        set_candidate_clearance(db, candidate_id, "approved", admin_user)
        return RedirectResponse(
            url=request.headers.get("referer") or "/admin/image-candidates",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/image-candidates/{candidate_id}/clearance-rejected")
    def admin_image_candidate_clearance_rejected(
        request: Request,
        candidate_id: int,
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        set_candidate_clearance(db, candidate_id, "rejected", admin_user)
        return RedirectResponse(
            url=request.headers.get("referer") or "/admin/image-candidates",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/image-candidates/{candidate_id}/update")
    async def admin_image_candidate_update(
        request: Request,
        candidate_id: int,
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        form = await request.form()
        qa_updates = {
            "has_text_detected": "has_text_detected" in form,
            "has_watermark_detected": "has_watermark_detected" in form,
            "has_logo_detected": "has_logo_detected" in form,
            "appears_poster_or_flyer": "appears_poster_or_flyer" in form,
            "appears_stock_or_placeholder": "appears_stock_or_placeholder" in form,
            "appears_live_performance": "appears_live_performance" in form,
            "appears_artist_subject": "appears_artist_subject" in form,
            "appears_venue_in_action": "appears_venue_in_action" in form,
            "appears_food_or_drink": "appears_food_or_drink" in form,
            "appears_unrelated_place": "appears_unrelated_place" in form,
            "appears_generic_crowd": "appears_generic_crowd" in form,
        }
        update_candidate_review(
            db,
            candidate_id,
            reviewed_by=admin_user,
            candidate_status=str(form.get("candidate_status") or ""),
            clearance_status=str(form.get("clearance_status") or ""),
            image_role=str(form.get("image_role") or ""),
            clearance_notes=str(form.get("clearance_notes") or ""),
            qa_updates=qa_updates,
        )
        return RedirectResponse(
            url=request.headers.get("referer") or "/admin/image-candidates",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/image-candidates/{candidate_id}/preflight")
    def admin_image_candidate_preflight(
        request: Request,
        candidate_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        candidate = get_image_candidate(db, candidate_id)
        if candidate is not None:
            mark_candidate_preflight_result(
                db,
                candidate_id,
                is_accessible=(
                    True if candidate.is_direct_image_asset else candidate.is_accessible
                ),
            )
        return RedirectResponse(
            url=request.headers.get("referer") or "/admin/image-candidates",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/image-candidates/{candidate_id}/preflight/background")
    def admin_image_candidate_preflight_background(
        candidate_id: int,
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        job = enqueue_job(
            db,
            "image_preflight",
            {"candidate_id": candidate_id},
            created_by=admin_user,
        )
        return RedirectResponse(
            url=f"/admin/jobs/{job.id}?success=Queued image preflight job",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/image-candidates/{candidate_id}/select-event")
    def admin_image_candidate_select_event(
        request: Request,
        candidate_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        candidate = get_image_candidate(db, candidate_id)
        if candidate and candidate.event_id:
            update_candidate_review(
                db,
                candidate_id,
                reviewed_by=None,
                candidate_status="accepted",
            )
            select_candidate_for_event(db, candidate_id)
        return RedirectResponse(
            url=request.headers.get("referer") or "/admin/image-candidates",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/image-candidates/{candidate_id}/select-venue")
    def admin_image_candidate_select_venue(
        request: Request,
        candidate_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        candidate = get_image_candidate(db, candidate_id)
        if candidate and candidate.venue_id:
            update_candidate_review(
                db,
                candidate_id,
                reviewed_by=None,
                candidate_status="accepted",
            )
            select_candidate_for_venue(db, candidate_id)
        return RedirectResponse(
            url=request.headers.get("referer") or "/admin/image-candidates",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/image-candidates/{candidate_id}/photo-rescue")
    def admin_image_candidate_photo_rescue(
        request: Request,
        candidate_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        candidate = get_image_candidate(db, candidate_id)
        if candidate and candidate.event_id:
            run_event_photo_rescue(db, candidate.event_id)
        return RedirectResponse(
            url=request.headers.get("referer") or "/admin/image-candidates",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/image-candidates/{candidate_id}/photo-rescue/background")
    def admin_image_candidate_photo_rescue_background(
        candidate_id: int,
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        candidate = get_image_candidate(db, candidate_id)
        if candidate is None or candidate.event_id is None:
            return RedirectResponse(
                url="/admin/image-candidates?error=Candidate has no linked event.",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        job = enqueue_job(
            db,
            "event_photo_rescue",
            {"event_id": candidate.event_id, "image_candidate_id": candidate.id},
            created_by=admin_user,
        )
        return RedirectResponse(
            url=f"/admin/jobs/{job.id}?success=Queued event photo rescue job",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/events/{event_id}/select-best-image")
    def admin_event_select_best_image(
        request: Request,
        event_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        select_best_event_image(db, event_id)
        return RedirectResponse(
            url=f"/admin/events/{event_id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/events/{event_id}/photo-rescue")
    def admin_event_photo_rescue(
        event_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        run_event_photo_rescue(db, event_id)
        return RedirectResponse(
            url=f"/admin/events/{event_id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/events/{event_id}/photo-rescue/background")
    def admin_event_photo_rescue_background(
        event_id: int,
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        event = get_event(db, event_id)
        if event is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event not found.",
            )
        job = enqueue_job(
            db,
            "event_photo_rescue",
            {"event_id": event_id},
            created_by=admin_user,
        )
        return RedirectResponse(
            url=f"/admin/jobs/{job.id}?success=Queued event photo rescue job",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.get("/admin/events", response_class=HTMLResponse)
    def admin_events(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        events = list_events(db)
        return admin_template_response(
            request,
            "events.html",
            {
                "page_title": "Events",
                "events": events,
            },
        )

    @app.get("/admin/artists", response_class=HTMLResponse)
    def admin_artists(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        return admin_template_response(
            request,
            "artists.html",
            {
                "page_title": "Artists",
                "artists": list_artists(db),
                "upcoming_event_count_for_artist": upcoming_event_count_for_artist,
            },
        )

    @app.post("/admin/artists/rebuild")
    def admin_artists_rebuild(
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        result = rebuild_artist_registry(db)
        return RedirectResponse(
            url=(
                "/admin/artists?success="
                f"Rebuilt {result['artists']} artists and "
                f"{result['event_artist_links']} event links"
            ),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.get("/admin/artist-duplicates", response_class=HTMLResponse)
    def admin_artist_duplicates(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        return admin_template_response(
            request,
            "artist_duplicates.html",
            {
                "page_title": "Artist Duplicate Review",
                "duplicate_groups": artist_duplicate_groups(db),
            },
        )

    @app.get("/admin/artists/{artist_id}", response_class=HTMLResponse)
    def admin_artist_detail(
        request: Request,
        artist_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        artist = get_artist(db, artist_id)
        if artist is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Artist not found.",
            )
        image_candidates = list_image_candidates(
            db,
            ImageCandidateFilters(rescue_source="provider_artist_image")
            if artist.image_url
            else ImageCandidateFilters(rescue_source="__no_artist_image__"),
        )
        if artist.image_url:
            image_candidates = [
                candidate
                for candidate in image_candidates
                if candidate.image_url == artist.image_url
            ]
        else:
            image_candidates = []
        return admin_template_response(
            request,
            "artist_detail.html",
            {
                "page_title": artist.display_name,
                "artist": artist,
                "image_candidates": image_candidates,
                "upcoming_event_count": upcoming_event_count_for_artist(artist),
            },
        )

    @app.get("/admin/poi-audit")
    def admin_poi_audit_alias(
        _admin: Annotated[str, Depends(require_admin)],
    ) -> RedirectResponse:
        return RedirectResponse(
            url="/admin/poi-candidates",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.get("/admin/poi-candidates", response_class=HTMLResponse)
    def admin_poi_candidates(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
        bucket: str | None = None,
        review_status: str | None = None,
        match_status: str | None = None,
        source_provider: str | None = None,
        search: str | None = None,
        limit: str | None = None,
        offset: str | None = None,
    ) -> Response:
        filters = PoiCandidateFilters(
            bucket=bucket or None,
            review_status=review_status or None,
            match_status=match_status or None,
            source_provider=source_provider or None,
            search=search or None,
            limit=parse_int_query(limit) or 100,
            offset=parse_int_query(offset) or 0,
        )
        return admin_template_response(
            request,
            "poi_candidates.html",
            {
                "page_title": "Incoming POI Candidate Audit",
                "candidates": list_poi_candidates(db, filters),
                "buckets": list_candidate_buckets(db),
                "selected_bucket": bucket or "",
                "filters": filters,
            },
        )

    @app.get("/admin/poi-candidates/{candidate_id}", response_class=HTMLResponse)
    def admin_poi_candidate_detail(
        request: Request,
        candidate_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        candidate = get_poi_candidate(db, candidate_id)
        if candidate is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="POI candidate not found.",
            )
        matched_poi = (
            get_poi_location(db, candidate.matched_poi_location_id)
            if candidate.matched_poi_location_id
            else None
        )
        created_poi = (
            get_poi_location(db, candidate.created_poi_location_id)
            if candidate.created_poi_location_id
            else None
        )
        return admin_template_response(
            request,
            "poi_candidate_detail.html",
            {
                "page_title": candidate.candidate_name,
                "candidate": candidate,
                "matched_poi": matched_poi,
                "created_poi": created_poi,
                "poi_locations": list_poi_locations(db, limit=500),
                "raw_preview": candidate.raw_fragment_json[:6000],
                "normalized_preview": candidate.normalized_payload_json[:6000],
                "raw_was_truncated": len(candidate.raw_fragment_json) > 6000,
                "normalized_was_truncated": (
                    len(candidate.normalized_payload_json) > 6000
                ),
            },
        )

    @app.post("/admin/poi-candidates/{candidate_id}/approve-create")
    def admin_poi_candidate_approve_create(
        request: Request,
        candidate_id: int,
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        try:
            poi = approve_candidate_create_poi(db, candidate_id)
        except ValueError as exc:
            return RedirectResponse(
                url=f"/admin/poi-candidates/{candidate_id}?error={exc}",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        log_admin_action(
            db,
            settings=settings,
            request=request,
            actor_username=admin_user,
            action="poi_candidate_approve_create",
            target_type="poi_candidate",
            target_id=candidate_id,
            metadata={"created_poi_location_id": poi.id},
        )
        return RedirectResponse(
            url=f"/admin/poi-candidates/{candidate_id}?success=Created POI #{poi.id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/poi-candidates/{candidate_id}/link-existing")
    async def admin_poi_candidate_link_existing(
        request: Request,
        candidate_id: int,
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        form = await request.form()
        poi_location_id = parse_int_query(str(form.get("poi_location_id") or ""))
        try:
            link_candidate_to_existing_poi(db, candidate_id, poi_location_id)
        except ValueError as exc:
            return RedirectResponse(
                url=f"/admin/poi-candidates/{candidate_id}?error={exc}",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        log_admin_action(
            db,
            settings=settings,
            request=request,
            actor_username=admin_user,
            action="poi_candidate_link_existing",
            target_type="poi_candidate",
            target_id=candidate_id,
            metadata={"poi_location_id": poi_location_id},
        )
        return RedirectResponse(
            url=f"/admin/poi-candidates/{candidate_id}?success=Linked existing POI",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/poi-candidates/{candidate_id}/approve-update")
    async def admin_poi_candidate_approve_update(
        request: Request,
        candidate_id: int,
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        form = await request.form()
        poi_location_id = parse_int_query(str(form.get("poi_location_id") or ""))
        try:
            poi = approve_candidate_update_existing_poi(
                db,
                candidate_id,
                poi_location_id,
            )
        except ValueError as exc:
            return RedirectResponse(
                url=f"/admin/poi-candidates/{candidate_id}?error={exc}",
                status_code=status.HTTP_303_SEE_OTHER,
            )
        log_admin_action(
            db,
            settings=settings,
            request=request,
            actor_username=admin_user,
            action="poi_candidate_approve_update",
            target_type="poi_candidate",
            target_id=candidate_id,
            metadata={"poi_location_id": poi.id},
        )
        return RedirectResponse(
            url=f"/admin/poi-candidates/{candidate_id}?success=Updated POI #{poi.id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/poi-candidates/{candidate_id}/event-venue-only")
    def admin_poi_candidate_event_venue_only(
        request: Request,
        candidate_id: int,
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        mark_candidate_event_venue_only(db, candidate_id)
        log_admin_action(
            db,
            settings=settings,
            request=request,
            actor_username=admin_user,
            action="poi_candidate_event_venue_only",
            target_type="poi_candidate",
            target_id=candidate_id,
        )
        return RedirectResponse(
            url=(
                f"/admin/poi-candidates/{candidate_id}"
                "?success=Marked event venue only"
            ),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/poi-candidates/{candidate_id}/needs-research")
    def admin_poi_candidate_needs_research(
        request: Request,
        candidate_id: int,
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        mark_candidate_needs_research(db, candidate_id)
        log_admin_action(
            db,
            settings=settings,
            request=request,
            actor_username=admin_user,
            action="poi_candidate_needs_research",
            target_type="poi_candidate",
            target_id=candidate_id,
        )
        return RedirectResponse(
            url=f"/admin/poi-candidates/{candidate_id}?success=Marked needs research",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/poi-candidates/{candidate_id}/reject")
    async def admin_poi_candidate_reject(
        request: Request,
        candidate_id: int,
        db: Annotated[Session, Depends(get_db)],
        admin_user: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        form = await request.form()
        reason = str(form.get("rejection_reason") or "")
        reject_poi_candidate(db, candidate_id, reason)
        log_admin_action(
            db,
            settings=settings,
            request=request,
            actor_username=admin_user,
            action="poi_candidate_reject",
            target_type="poi_candidate",
            target_id=candidate_id,
            metadata={"reason": reason},
        )
        return RedirectResponse(
            url=f"/admin/poi-candidates/{candidate_id}?success=Rejected candidate",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/poi-candidates/{candidate_id}/recompute")
    def admin_poi_candidate_recompute(
        candidate_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        recompute_candidate_match_quality(db, candidate_id)
        return RedirectResponse(
            url=f"/admin/poi-candidates/{candidate_id}?success=Recomputed match",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.get("/admin/poi-locations", response_class=HTMLResponse)
    def admin_poi_locations(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        locations = list_poi_locations(db)
        return admin_template_response(
            request,
            "poi_locations.html",
            {
                "page_title": "POI Master Registry",
                "locations": locations,
            },
        )

    @app.get("/admin/poi-locations/{poi_id}", response_class=HTMLResponse)
    def admin_poi_location_detail(
        request: Request,
        poi_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        location = get_poi_location(db, poi_id)
        if location is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="POI location not found.",
            )
        return admin_template_response(
            request,
            "poi_location_detail.html",
            {
                "page_title": location.display_name,
                "location": location,
                "raw_source_preview": location.raw_source_json[:5000],
                "raw_source_was_truncated": len(location.raw_source_json) > 5000,
            },
        )

    @app.get("/admin/poi-duplicates", response_class=HTMLResponse)
    def admin_poi_duplicates(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        return admin_template_response(
            request,
            "poi_duplicates.html",
            {
                "page_title": "POI Duplicate Review",
                "duplicate_groups": poi_duplicate_groups(db),
            },
        )

    @app.get("/admin/poi-inventory", response_class=HTMLResponse)
    def admin_poi_inventory(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        output_dir = poi_inventory_output_dir(request)
        return admin_template_response(
            request,
            "poi_inventory.html",
            {
                "page_title": "POI Inventory Snapshots",
                "latest_inventory": get_latest_poi_inventory_export(db),
                "latest_dedupe": get_latest_poi_dedupe_index(db),
                "latest_manifest": get_latest_poi_inventory_manifest(db),
                "recent_exports": list_poi_inventory_exports(db, limit=8),
                "output_dir": str(output_dir),
            },
        )

    @app.post("/admin/poi-inventory/generate")
    def admin_poi_inventory_generate(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        admin: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        output_dir = poi_inventory_output_dir(request)
        export_current_poi_inventory(
            db,
            output_dir,
            archive=True,
            generated_by=admin,
        )
        export_current_poi_dedupe_index(
            db,
            output_dir,
            archive=True,
            generated_by=admin,
        )
        export_poi_inventory_manifest(
            db,
            output_dir,
            archive=True,
            generated_by=admin,
        )
        return RedirectResponse(
            url="/admin/poi-inventory?success=Generated POI inventory snapshot",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/poi-inventory/generate-dedupe-index")
    def admin_poi_inventory_generate_dedupe_index(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        admin: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        output_dir = poi_inventory_output_dir(request)
        export_current_poi_dedupe_index(
            db,
            output_dir,
            archive=True,
            generated_by=admin,
        )
        export_poi_inventory_manifest(
            db,
            output_dir,
            archive=True,
            generated_by=admin,
        )
        return RedirectResponse(
            url="/admin/poi-inventory?success=Generated POI dedupe index",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.get("/admin/poi-inventory/exports", response_class=HTMLResponse)
    def admin_poi_inventory_exports(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        return admin_template_response(
            request,
            "poi_inventory_exports.html",
            {
                "page_title": "POI Inventory Export History",
                "exports": list_poi_inventory_exports(db),
            },
        )

    @app.get("/admin/poi-inventory/exports/{export_id}", response_class=HTMLResponse)
    def admin_poi_inventory_export_detail(
        request: Request,
        export_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        export = get_poi_inventory_export(db, export_id)
        if export is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="POI inventory export not found.",
            )
        return admin_template_response(
            request,
            "poi_inventory_export_detail.html",
            {
                "page_title": f"POI Inventory Export #{export.id}",
                "export": export,
                "metadata": pretty_json_object(export.metadata_payload),
                "output_exists": (
                    Path(export.output_path).exists()
                    if export.output_path
                    else False
                ),
            },
        )

    @app.get("/admin/poi-inventory/exports/{export_id}/download")
    def admin_poi_inventory_export_download(
        export_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        export = get_poi_inventory_export(db, export_id)
        if export is None or not export.output_path:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="POI inventory export file not found.",
            )
        output_path = Path(export.output_path)
        if not output_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="POI inventory export file not found.",
            )
        media_type = (
            "application/gzip"
            if output_path.suffix == ".gz"
            else "application/json"
        )
        return FileResponse(
            output_path,
            media_type=media_type,
            filename=output_path.name,
        )

    @app.get("/admin/duplicate-events", response_class=HTMLResponse)
    def admin_duplicate_events(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        return admin_template_response(
            request,
            "duplicate_events.html",
            {
                "page_title": "Duplicate Event Review",
                "groups": list_duplicate_group_views(db),
            },
        )

    @app.get("/admin/duplicate-events/{group_id}", response_class=HTMLResponse)
    def admin_duplicate_event_detail(
        request: Request,
        group_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        try:
            view = duplicate_group_view(db, group_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Duplicate group not found.",
            ) from exc
        return admin_template_response(
            request,
            "duplicate_event_detail.html",
            {
                "page_title": f"Duplicate Group #{view.group.id}",
                "view": view,
            },
        )

    @app.post("/admin/duplicate-events/{group_id}/merge")
    def admin_duplicate_event_merge(
        group_id: int,
        primary_event_id: Annotated[int, Form()],
        db: Annotated[Session, Depends(get_db)],
        admin: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        try:
            merge_duplicate_group(db, group_id, primary_event_id, admin)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        return RedirectResponse(
            url=f"/admin/duplicate-events/{group_id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/duplicate-events/{group_id}/keep-both")
    def admin_duplicate_event_keep_both(
        group_id: int,
        db: Annotated[Session, Depends(get_db)],
        admin: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        keep_duplicate_group_separate(db, group_id, admin)
        return RedirectResponse(
            url=f"/admin/duplicate-events/{group_id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.post("/admin/duplicate-events/{group_id}/reject")
    def admin_duplicate_event_reject(
        group_id: int,
        db: Annotated[Session, Depends(get_db)],
        admin: Annotated[str, Depends(require_admin_csrf)],
    ) -> Response:
        reject_duplicate_group(db, group_id, admin)
        return RedirectResponse(
            url=f"/admin/duplicate-events/{group_id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    @app.get("/admin/events/{event_id}", response_class=HTMLResponse)
    def admin_event_detail(
        request: Request,
        event_id: int,
        db: Annotated[Session, Depends(get_db)],
        _admin: Annotated[str, Depends(require_admin)],
    ) -> Response:
        event = get_event(db, event_id)
        if event is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event not found.",
            )
        raw_json = event.raw_event_json or ""
        image_candidates = list_image_candidates(
            db,
            ImageCandidateFilters(event_id=event.id),
        )
        selected_image_candidate = next(
            (
                candidate
                for candidate in image_candidates
                if candidate.id == event.selected_image_candidate_id
            ),
            None,
        )
        blocked_image_candidate_count = sum(
            bool(candidate.rejection_reasons) for candidate in image_candidates
        )
        return admin_template_response(
            request,
            "event_detail.html",
            {
                "page_title": event.title,
                "event": event,
                "image_candidates": image_candidates,
                "selected_image_candidate": selected_image_candidate,
                "photo_decision": (
                    selected_image_candidate.selection_explanation
                    if selected_image_candidate
                    else {}
                ),
                "blocked_image_candidate_count": blocked_image_candidate_count,
                "image_badges": event_image_badges(event),
                "image_roles": IMAGE_ROLES,
                "source_claims": source_claims_for_event(db, event.id),
                "raw_event_preview": raw_json[:5000],
                "raw_event_was_truncated": len(raw_json) > 5000,
            },
        )

    return app


app = create_app()
