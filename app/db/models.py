import json
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


def _json_list(value: str | None) -> list[object]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _json_dict(value: str | None) -> dict[str, object]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


class SourceStatus(StrEnum):
    """Allowed admin states for submitted calendar sources."""

    pending = "pending"
    approved = "approved"
    paused = "paused"


class CrawlRunStatus(StrEnum):
    """Allowed outcomes for manual crawl attempts."""

    success = "success"
    failure = "failure"


class SourceReviewStatus(StrEnum):
    """Allowed trust-review states for public submissions."""

    pending_review = "pending_review"
    approved = "approved"
    rejected = "rejected"
    quarantined = "quarantined"
    blocked = "blocked"


class RegionType(StrEnum):
    """Destination/region grouping types for operations and app feeds."""

    city = "city"
    metro = "metro"
    state = "state"
    country = "country"
    certified_music_region = "certified_music_region"
    tourism_board = "tourism_board"
    custom = "custom"


class DestinationPartnerType(StrEnum):
    """Partner organization types connected to destinations."""

    tourism_board = "tourism_board"
    chamber = "chamber"
    city = "city"
    region = "region"
    venue_group = "venue_group"
    festival = "festival"
    internal = "internal"


class RegionPartnerStatus(StrEnum):
    """Relationship state for a destination/region."""

    internal = "internal"
    prospect = "prospect"
    active_partner = "active_partner"
    certified = "certified"
    inactive = "inactive"


class RegionLaunchStatus(StrEnum):
    """Launch-readiness state for a destination/region."""

    research = "research"
    building = "building"
    qa = "qa"
    ready = "ready"
    launched = "launched"


class SearchSeedType(StrEnum):
    """Search seed entity types."""

    city = "city"
    metro = "metro"
    state = "state"
    country = "country"
    venue = "venue"
    poi = "poi"
    festival = "festival"
    stadium = "stadium"
    airport = "airport"
    landmark = "landmark"
    neighborhood = "neighborhood"
    tourism_board = "tourism_board"
    unknown = "unknown"


class SearchSeedSourceType(StrEnum):
    """Where a search seed originated."""

    manual = "manual"
    mapotic_export = "mapotic_export"
    jambase_geography = "jambase_geography"
    poi_registry = "poi_registry"
    region = "region"
    internal_research = "internal_research"


class ArtistType(StrEnum):
    """Canonical artist registry types."""

    band = "band"
    musician = "musician"
    dj = "dj"
    ensemble = "ensemble"
    orchestra = "orchestra"
    unknown = "unknown"


class ArtistSourceType(StrEnum):
    """Provider/source families that can claim artist identity."""

    jambase = "jambase"
    cityspark = "cityspark"
    spotify = "spotify"
    serpapi = "serpapi"
    ticketmaster = "ticketmaster"
    api_feed = "api_feed"
    file_upload = "file_upload"
    manual_admin = "manual_admin"
    unknown = "unknown"


class EventArtistRole(StrEnum):
    """Artist role on a normalized Concert event."""

    headliner = "headliner"
    supporting = "supporting"
    performer = "performer"
    dj = "dj"
    unknown = "unknown"


class PublishStatus(StrEnum):
    """Allowed app-feed publication states for normalized records."""

    draft = "draft"
    needs_review = "needs_review"
    approved = "approved"
    published = "published"
    unpublished = "unpublished"
    rejected = "rejected"
    stale = "stale"
    archived = "archived"


class AppFeedExportStatus(StrEnum):
    """Allowed outcomes for generated app feed export snapshots."""

    pending = "pending"
    success = "success"
    failure = "failure"


class PoiInventoryExportType(StrEnum):
    """Portable POI inventory snapshot artifact types."""

    full_inventory_jsonl = "full_inventory_jsonl"
    dedupe_index_json = "dedupe_index_json"
    manifest = "manifest"


class PoiInventoryExportStatus(StrEnum):
    """Allowed outcomes for generated POI inventory snapshots."""

    pending = "pending"
    success = "success"
    failure = "failure"


class PoiCandidateSourceType(StrEnum):
    """Where an incoming POI candidate was discovered."""

    crawl_extraction = "crawl_extraction"
    api_provider = "api_provider"
    file_upload = "file_upload"
    manual_admin = "manual_admin"
    mapotic_import = "mapotic_import"
    unknown = "unknown"


class PoiCandidateSourceProvider(StrEnum):
    """Provider/source labels for incoming POI candidates."""

    jambase = "jambase"
    cityspark = "cityspark"
    manual_json = "manual_json"
    source_crawl = "source_crawl"
    unknown = "unknown"


class PoiCandidateMatchStatus(StrEnum):
    """Admin/matching state for an incoming POI candidate."""

    unmatched = "unmatched"
    matched_existing = "matched_existing"
    possible_duplicate = "possible_duplicate"
    new_candidate = "new_candidate"
    rejected = "rejected"
    approved_created = "approved_created"
    approved_updated = "approved_updated"
    event_venue_only = "event_venue_only"


class PoiCandidateMatchConfidence(StrEnum):
    """Confidence bands for POI candidate matching."""

    strong = "strong"
    medium = "medium"
    weak = "weak"
    none = "none"


class PoiCandidateReviewStatus(StrEnum):
    """Admin review state for incoming POI candidates."""

    pending_review = "pending_review"
    approved = "approved"
    rejected = "rejected"
    needs_research = "needs_research"
    quarantined = "quarantined"


class AppSearchEntityType(StrEnum):
    """Entity families exposed by the internal app search index."""

    event = "event"
    itinerary = "itinerary"
    poi = "poi"
    venue = "venue"
    region = "region"
    search_seed = "search_seed"
    artist_future = "artist_future"
    unknown = "unknown"


class DiscoverySlotType(StrEnum):
    """Future-safe app discovery slot families."""

    event_carousel = "event_carousel"
    itinerary_carousel = "itinerary_carousel"
    poi_carousel = "poi_carousel"
    region_carousel = "region_carousel"
    editorial = "editorial"
    sponsored_future = "sponsored_future"


class BackgroundJobType(StrEnum):
    """Allowed local background job handler keys."""

    crawl_source = "crawl_source"
    bulk_crawl = "bulk_crawl"
    provider_sandbox_jambase = "provider_sandbox_jambase"
    provider_sandbox_cityspark = "provider_sandbox_cityspark"
    image_preflight = "image_preflight"
    event_photo_rescue = "event_photo_rescue"
    api_feed_run_photo_rescue = "api_feed_run_photo_rescue"
    recent_events_photo_rescue = "recent_events_photo_rescue"
    ticket_page_image_enrichment = "ticket_page_image_enrichment"
    api_feed_run_ticket_image_enrichment = "api_feed_run_ticket_image_enrichment"
    recent_events_ticket_image_enrichment = "recent_events_ticket_image_enrichment"
    extract_crawl_run = "extract_crawl_run"
    approve_extracted_event_candidate = "approve_extracted_event_candidate"
    process_extracted_event_batch = "process_extracted_event_batch"
    app_feed_export = "app_feed_export"
    poi_registry_import = "poi_registry_import"
    scheduled_crawl_due_sources = "scheduled_crawl_due_sources"
    source_quality_rollup = "source_quality_rollup"
    region_partner_report = "region_partner_report"
    all_source_quality_rollup = "all_source_quality_rollup"
    rebuild_app_search_index = "rebuild_app_search_index"
    app_map_feed_export = "app_map_feed_export"
    app_filter_options_export = "app_filter_options_export"
    poi_inventory_snapshot_export = "poi_inventory_snapshot_export"
    source_registry_snapshot_export = "source_registry_snapshot_export"
    poi_candidate_match = "poi_candidate_match"
    all_poi_candidate_match = "all_poi_candidate_match"
    poi_candidate_quality_rollup = "poi_candidate_quality_rollup"
    rebuild_artist_registry = "rebuild_artist_registry"
    artist_genre_normalization = "artist_genre_normalization"
    artist_image_rescue = "artist_image_rescue"
    itinerary_quality_rollup = "itinerary_quality_rollup"
    itinerary_app_feed_export = "itinerary_app_feed_export"
    build_artist_tour_itinerary = "build_artist_tour_itinerary"
    build_region_itinerary_suggestions = "build_region_itinerary_suggestions"
    unknown = "unknown"


class BackgroundJobStatus(StrEnum):
    """Allowed states for DB-backed background jobs."""

    pending = "pending"
    running = "running"
    success = "success"
    failure = "failure"
    cancelled = "cancelled"
    skipped = "skipped"


class ScheduledTaskType(StrEnum):
    """Allowed manual scheduler task families."""

    crawl_due_sources = "crawl_due_sources"
    app_feed_export = "app_feed_export"
    provider_sandbox = "provider_sandbox"
    image_preflight = "image_preflight"
    event_photo_rescue = "event_photo_rescue"
    source_quality_rollup = "source_quality_rollup"
    partner_report_export = "partner_report_export"
    rebuild_app_search_index = "rebuild_app_search_index"
    monthly_poi_inventory_snapshot = "monthly_poi_inventory_snapshot"
    monthly_source_registry_snapshot = "monthly_source_registry_snapshot"
    itinerary_app_feed_export = "itinerary_app_feed_export"


class ItineraryType(StrEnum):
    """Editorial collection types used for Road Trip/Tour app contracts."""

    road_trip = "road_trip"
    city_tour = "city_tour"
    artist_tour = "artist_tour"
    festival_weekend = "festival_weekend"
    venue_hop = "venue_hop"
    record_store_crawl = "record_store_crawl"
    certified_region = "certified_region"
    custom = "custom"


class ItineraryDisplayLabel(StrEnum):
    """App-facing labels for itinerary-style collections."""

    road_trip = "Road Trip"
    tour = "Tour"
    setlist = "Setlist"
    route = "Route"


class ItineraryStatus(StrEnum):
    """Review and app-feed readiness states for itineraries."""

    draft = "draft"
    review = "review"
    approved = "approved"
    published = "published"
    archived = "archived"


class ItineraryStopType(StrEnum):
    """Allowed itinerary stop reference families."""

    event = "event"
    poi = "poi"
    venue = "venue"
    region = "region"
    artist_context = "artist_context"
    note = "note"
    custom = "custom"


class ItineraryRouteProvider(StrEnum):
    """External handoff providers for manual navigation URLs."""

    none = "none"
    google_maps_external = "google_maps_external"
    apple_maps_external = "apple_maps_external"
    manual = "manual"


class ScheduledTaskScheduleType(StrEnum):
    """Supported scheduler cadence types."""

    manual = "manual"
    interval = "interval"
    daily = "daily"
    weekly = "weekly"
    biweekly = "biweekly"
    monthly = "monthly"


class SourceQualitySourceKind(StrEnum):
    """Entity families that can receive source trust scoring."""

    master_calendar_source = "master_calendar_source"
    api_provider = "api_provider"
    api_feed_run = "api_feed_run"
    crawl_run = "crawl_run"
    import_batch = "import_batch"
    destination_partner = "destination_partner"
    region = "region"
    unknown = "unknown"


class SourceQualityGrade(StrEnum):
    """Human-readable source trust bands."""

    excellent = "excellent"
    good = "good"
    fair = "fair"
    poor = "poor"
    blocked = "blocked"
    unknown = "unknown"


class SourceScrapePlatformType(StrEnum):
    """Detected source platform families for approved calendar sources."""

    ics = "ics"
    rss_atom = "rss_atom"
    json_ld = "json_ld"
    static_html = "static_html"
    wordpress_events = "wordpress_events"
    the_events_calendar = "the_events_calendar"
    eventbrite_page = "eventbrite_page"
    venue_calendar = "venue_calendar"
    tourism_board_calendar = "tourism_board_calendar"
    unknown = "unknown"
    unsupported = "unsupported"


class SourceScrapeExtractorType(StrEnum):
    """Extractor strategies stored for source scrape profiles."""

    ics = "ics"
    json_ld_event = "json_ld_event"
    rss_atom = "rss_atom"
    html_event_list = "html_event_list"
    generic_html_links = "generic_html_links"
    unsupported = "unsupported"


class SourceScrapeExtractorConfidence(StrEnum):
    """Confidence bands for remembered source scrape recipes."""

    high = "high"
    medium = "medium"
    low = "low"
    unknown = "unknown"


class SourceHealthStatus(StrEnum):
    """Operational health states for approved source scrape profiles."""

    healthy = "healthy"
    watch = "watch"
    needs_review = "needs_review"
    failing = "failing"
    paused = "paused"
    unsupported = "unsupported"


class CalendarSourceResearchBatchStatus(StrEnum):
    """Workflow states for city/region calendar source research batches."""

    draft = "draft"
    preflight_ready = "preflight_ready"
    preflighted = "preflighted"
    approved_for_crawl = "approved_for_crawl"
    crawl_running = "crawl_running"
    crawl_complete = "crawl_complete"
    review_complete = "review_complete"
    archived = "archived"


class CalendarSourceResearchSourceType(StrEnum):
    """Source families used during calendar research intake."""

    venue_calendar = "venue_calendar"
    tourism_board_calendar = "tourism_board_calendar"
    chamber_calendar = "chamber_calendar"
    festival_calendar = "festival_calendar"
    publication_calendar = "publication_calendar"
    artist_calendar = "artist_calendar"
    ticketing_calendar = "ticketing_calendar"
    unknown = "unknown"


class CalendarSourceResearchAuthorizationStatus(StrEnum):
    """How a researched calendar URL was obtained."""

    internal_research = "internal_research"
    partner_supplied = "partner_supplied"
    public_submission = "public_submission"
    unknown = "unknown"


class CalendarSourceResearchPreflightStatus(StrEnum):
    """Safe URL preflight states for researched calendar URLs."""

    pending = "pending"
    success = "success"
    warning = "warning"
    failure = "failure"
    blocked = "blocked"


class CalendarSourceResearchDedupeStatus(StrEnum):
    """Dedupe status for researched calendar URLs."""

    new_source = "new_source"
    existing_master_source = "existing_master_source"
    possible_duplicate = "possible_duplicate"
    invalid_url = "invalid_url"
    blocked_url = "blocked_url"


class CalendarSourceResearchReviewStatus(StrEnum):
    """Admin review status for researched calendar source items."""

    pending_review = "pending_review"
    approved = "approved"
    rejected = "rejected"
    needs_research = "needs_research"


class PartnerReportType(StrEnum):
    """Partner/destination report families."""

    destination_summary = "destination_summary"
    source_quality = "source_quality"
    app_feed_readiness = "app_feed_readiness"
    calendar_coverage = "calendar_coverage"


class PartnerReportStatus(StrEnum):
    """Generation state for partner/destination reports."""

    draft = "draft"
    generated = "generated"
    failed = "failed"


class CalendarSource(Base):
    """Submitted calendar URL and review status."""

    __tablename__ = "calendar_sources"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending', 'approved', 'paused')",
            name="ck_calendar_sources_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    organization_name: Mapped[str] = mapped_column(String(255), nullable=False)
    calendar_url: Mapped[str] = mapped_column(Text, nullable=False)
    contact_email: Mapped[str] = mapped_column(String(255), nullable=False)
    permission_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=SourceStatus.pending.value,
    )
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False, default="low")
    risk_flags_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    review_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=SourceReviewStatus.pending_review.value,
    )
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    submitted_user_agent_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    submitted_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    claimed_source_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    form_rendered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    submitted_via: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="submit-calendar",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    crawl_runs: Mapped[list["CrawlRun"]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
    )
    events: Mapped[list["Event"]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
    )

    @property
    def risk_flags(self) -> list[str]:
        try:
            parsed = json.loads(self.risk_flags_json)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
        return []


class CrawlRun(Base):
    """One manual fetch attempt for an approved calendar source."""

    __tablename__ = "crawl_runs"
    __table_args__ = (
        CheckConstraint(
            "status in ('success', 'failure')",
            name="ck_crawl_runs_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("calendar_sources.id"),
        nullable=False,
        index=True,
    )
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    final_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    http_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    extractor_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    extraction_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    event_candidates_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    unsupported_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_warnings_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )
    extraction_errors_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )
    discovered_links_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    extraction_summary_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
    )
    events_created_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    events_updated_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    duplicate_candidate_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    events_skipped_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    events_cancelled_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    source_claims_created_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    source: Mapped[CalendarSource] = relationship(back_populates="crawl_runs")
    extracted_event_candidates: Mapped[list["SourceExtractedEventCandidate"]] = (
        relationship(
            back_populates="crawl_run",
            cascade="all, delete-orphan",
        )
    )

    @property
    def extraction_warnings(self) -> list[str]:
        return [str(item) for item in _json_list(self.extraction_warnings_json)]

    @property
    def extraction_errors(self) -> list[str]:
        return [str(item) for item in _json_list(self.extraction_errors_json)]

    @property
    def extraction_summary(self) -> dict[str, object]:
        return _json_dict(self.extraction_summary_json)

    @property
    def discovered_links(self) -> list[object]:
        links = self.extraction_summary.get("discovered_links")
        return links if isinstance(links, list) else []
    events: Mapped[list["Event"]] = relationship(
        back_populates="crawl_run",
        cascade="all, delete-orphan",
    )


class SourceExtractedEventCandidate(Base):
    """Reviewable event candidate extracted from an approved source crawl."""

    __tablename__ = "source_extracted_event_candidates"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    crawl_run_id: Mapped[int] = mapped_column(
        ForeignKey("crawl_runs.id"),
        nullable=False,
        index=True,
    )
    master_calendar_source_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
    )
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    extractor_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    start_datetime: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    venue_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    event_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_fragment_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    normalized_payload_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
    )
    review_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending_review",
        index=True,
    )
    validation_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="valid",
    )
    validation_errors_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )
    quality_flags_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )
    source_claim_preview_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
    )
    created_event_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    crawl_run: Mapped[CrawlRun] = relationship(
        back_populates="extracted_event_candidates",
    )

    @property
    def raw_fragment(self) -> dict[str, object]:
        return _json_dict(self.raw_fragment_json)

    @property
    def normalized_payload(self) -> dict[str, object]:
        return _json_dict(self.normalized_payload_json)

    @property
    def validation_errors(self) -> list[str]:
        return [str(item) for item in _json_list(self.validation_errors_json)]

    @property
    def quality_flags(self) -> list[str]:
        return [str(item) for item in _json_list(self.quality_flags_json)]

    @property
    def source_claim_preview(self) -> dict[str, object]:
        return _json_dict(self.source_claim_preview_json)


class Region(Base):
    """Destination/region container for events, POIs, sources, and QA."""

    __tablename__ = "regions"
    __table_args__ = (
        UniqueConstraint("region_key", name="uq_regions_region_key"),
        UniqueConstraint("slug", name="uq_regions_slug"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    region_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    region_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=RegionType.city.value,
    )
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str | None] = mapped_column(String(255), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    radius_miles: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(128), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    partner_status: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=RegionPartnerStatus.internal.value,
    )
    certified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    launch_status: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=RegionLaunchStatus.research.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    destination_partners: Mapped[list["DestinationPartner"]] = relationship(
        back_populates="region",
    )
    search_seeds: Mapped[list["SearchSeedLocation"]] = relationship(
        back_populates="region",
    )
    quality_snapshots: Mapped[list["RegionQualitySnapshot"]] = relationship(
        back_populates="region",
        cascade="all, delete-orphan",
    )
    source_quality_scores: Mapped[list["SourceQualityScore"]] = relationship(
        back_populates="region",
    )
    partner_reports: Mapped[list["PartnerReport"]] = relationship(
        back_populates="region",
    )
    app_search_entries: Mapped[list["AppSearchIndex"]] = relationship(
        back_populates="region",
    )
    discovery_slots: Mapped[list["AppDiscoverySlot"]] = relationship(
        back_populates="region",
    )
    events: Mapped[list["Event"]] = relationship(back_populates="region")
    poi_locations: Mapped[list["PoiLocation"]] = relationship(back_populates="region")
    master_calendar_sources: Mapped[list["MasterCalendarSource"]] = relationship(
        back_populates="region",
    )

    @property
    def bbox(self) -> dict[str, object]:
        return _json_dict(self.bbox_json)


class DestinationPartner(Base):
    """Tourism board, chamber, venue group, or internal region partner."""

    __tablename__ = "destination_partners"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    partner_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=DestinationPartnerType.internal.value,
    )
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    region_id: Mapped[int | None] = mapped_column(
        ForeignKey("regions.id"),
        nullable=True,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="prospect")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    region: Mapped[Region | None] = relationship(back_populates="destination_partners")
    source_quality_scores: Mapped[list["SourceQualityScore"]] = relationship(
        back_populates="partner",
    )
    partner_reports: Mapped[list["PartnerReport"]] = relationship(
        back_populates="partner",
    )


class SearchSeedLocation(Base):
    """Internal location/name registry for search before external services."""

    __tablename__ = "search_seed_locations"
    __table_args__ = (
        UniqueConstraint("seed_key", name="uq_search_seed_locations_seed_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    seed_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(500), nullable=False)
    seed_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=SearchSeedType.unknown.value,
        index=True,
    )
    source_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=SearchSeedSourceType.manual.value,
        index=True,
    )
    source_record_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    region_id: Mapped[int | None] = mapped_column(
        ForeignKey("regions.id"),
        nullable=True,
        index=True,
    )
    poi_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("poi_locations.id"),
        nullable=True,
        index=True,
    )
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str | None] = mapped_column(String(255), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(128), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    search_weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    popularity_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    use_for_internal_search: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    use_for_app_search: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    region: Mapped[Region | None] = relationship(back_populates="search_seeds")
    poi_location: Mapped["PoiLocation | None"] = relationship(
        back_populates="search_seeds",
    )


class RegionQualitySnapshot(Base):
    """Point-in-time QA counts for a destination/region."""

    __tablename__ = "region_quality_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    region_id: Mapped[int] = mapped_column(
        ForeignKey("regions.id"),
        nullable=False,
        index=True,
    )
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    poi_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    app_feed_event_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    app_feed_poi_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    missing_image_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    pending_image_approval_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    bad_ticket_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_event_candidate_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    poi_duplicate_candidate_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    extraction_failure_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    region: Mapped[Region] = relationship(back_populates="quality_snapshots")

    @property
    def snapshot(self) -> dict[str, object]:
        return _json_dict(self.snapshot_json)


class SourceQualityScore(Base):
    """Point-in-time source trust score for a source, provider, partner, or region."""

    __tablename__ = "source_quality_scores"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    source_kind: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=SourceQualitySourceKind.unknown.value,
        index=True,
    )
    source_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    source_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str] = mapped_column(String(500), nullable=False)
    region_id: Mapped[int | None] = mapped_column(
        ForeignKey("regions.id"),
        nullable=True,
        index=True,
    )
    provider_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    partner_id: Mapped[int | None] = mapped_column(
        ForeignKey("destination_partners.id"),
        nullable=True,
        index=True,
    )
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    score_grade: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=SourceQualityGrade.unknown.value,
        index=True,
    )
    event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    event_created_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    event_updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_candidate_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    duplicate_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extraction_success_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    extraction_failure_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    unsupported_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missing_ticket_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    bad_ticket_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missing_image_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    generic_image_blocked_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    selected_pending_approval_image_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    missing_venue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missing_geo_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    app_feed_ready_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    app_feed_blocked_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    manual_correction_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_failure_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    scoring_window_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    scoring_window_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    score_inputs_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    recommendations_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    region: Mapped[Region | None] = relationship(back_populates="source_quality_scores")
    partner: Mapped[DestinationPartner | None] = relationship(
        back_populates="source_quality_scores",
    )

    @property
    def score_inputs(self) -> dict[str, object]:
        return _json_dict(self.score_inputs_json)

    @property
    def recommendations(self) -> list[object]:
        return _json_list(self.recommendations_json)


class PartnerReport(Base):
    """Generated destination/partner report snapshot."""

    __tablename__ = "partner_reports"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    partner_id: Mapped[int | None] = mapped_column(
        ForeignKey("destination_partners.id"),
        nullable=True,
        index=True,
    )
    region_id: Mapped[int | None] = mapped_column(
        ForeignKey("regions.id"),
        nullable=True,
        index=True,
    )
    report_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=PartnerReportType.destination_summary.value,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=PartnerReportStatus.draft.value,
        index=True,
    )
    report_period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    report_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    summary_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    metrics_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    recommendations_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )
    generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    generated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    partner: Mapped[DestinationPartner | None] = relationship(
        back_populates="partner_reports",
    )
    region: Mapped[Region | None] = relationship(back_populates="partner_reports")

    @property
    def summary(self) -> dict[str, object]:
        return _json_dict(self.summary_json)

    @property
    def metrics(self) -> dict[str, object]:
        return _json_dict(self.metrics_json)

    @property
    def recommendations(self) -> list[object]:
        return _json_list(self.recommendations_json)


class EventVenue(Base):
    """POI-style venue container for nested Concert event previews."""

    __tablename__ = "event_venues"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    venue_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(500), nullable=False)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state: Mapped[str | None] = mapped_column(String(255), nullable=True)
    zip_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    country: Mapped[str | None] = mapped_column(String(255), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    main_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    additional_image_urls: Mapped[str | None] = mapped_column(Text, nullable=True)
    selected_main_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    selected_image_candidate_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    image_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    image_quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    image_quality_flags_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )
    image_clearance_status: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    image_role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    image_selection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_selected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    category: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="Music Site",
    )
    subcategory: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="Venues",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    events: Mapped[list["Event"]] = relationship(back_populates="venue")
    image_candidates: Mapped[list["ImageCandidate"]] = relationship(
        back_populates="venue",
        cascade="all, delete-orphan",
    )

    @property
    def image_quality_flags(self) -> list[str]:
        return [str(item) for item in _json_list(self.image_quality_flags_json)]


class PoiLocation(Base):
    """Master Music Roadtrip place/location registry seeded from Mapotic POIs."""

    __tablename__ = "poi_locations"
    __table_args__ = (
        UniqueConstraint("canonical_poi_id", name="uq_poi_locations_canonical_poi_id"),
        UniqueConstraint("poi_dedupe_key", name="uq_poi_locations_dedupe_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    canonical_poi_id: Mapped[str] = mapped_column(String(64), nullable=False)
    poi_dedupe_key: Mapped[str] = mapped_column(Text, nullable=False)
    poi_dedupe_confidence: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="strong",
    )
    source_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="mapotic_export",
    )
    source_record_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mapotic_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    places_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    canonical_venue_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    subcategory: Mapped[str | None] = mapped_column(String(128), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state: Mapped[str | None] = mapped_column(String(255), nullable=True)
    zip_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    country: Mapped[str | None] = mapped_column(String(255), nullable=True)
    region_id: Mapped[int | None] = mapped_column(
        ForeignKey("regions.id"),
        nullable=True,
        index=True,
    )
    region_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    instagram: Mapped[str | None] = mapped_column(Text, nullable=True)
    facebook: Mapped[str | None] = mapped_column(Text, nullable=True)
    x_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    tiktok: Mapped[str | None] = mapped_column(Text, nullable=True)
    spotify_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    main_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    additional_image_urls: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    hours_of_operation: Mapped[str | None] = mapped_column(Text, nullable=True)
    certified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    carousel_selection: Mapped[str | None] = mapped_column(String(255), nullable=True)
    business_status: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_count_google: Mapped[int | None] = mapped_column(Integer, nullable=True)
    review_count_yelp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    photo_quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_control: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_verified_at: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_source_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    publish_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=PublishStatus.needs_review.value,
        index=True,
    )
    publish_ready_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    publish_blockers_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    unpublished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_published_snapshot_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    region: Mapped[Region | None] = relationship(back_populates="poi_locations")
    search_seeds: Mapped[list[SearchSeedLocation]] = relationship(
        back_populates="poi_location",
    )


class PoiCandidate(Base):
    """Incoming place/venue candidate staged before POI registry approval."""

    __tablename__ = "poi_candidates"
    __table_args__ = (
        CheckConstraint(
            "source_type in ("
            "'crawl_extraction', 'api_provider', 'file_upload', 'manual_admin', "
            "'mapotic_import', 'unknown'"
            ")",
            name="ck_poi_candidates_source_type",
        ),
        CheckConstraint(
            "source_provider in ("
            "'jambase', 'cityspark', 'manual_json', 'source_crawl', 'unknown'"
            ")",
            name="ck_poi_candidates_source_provider",
        ),
        CheckConstraint(
            "match_status in ("
            "'unmatched', 'matched_existing', 'possible_duplicate', "
            "'new_candidate', 'rejected', 'approved_created', 'approved_updated', "
            "'event_venue_only'"
            ")",
            name="ck_poi_candidates_match_status",
        ),
        CheckConstraint(
            "match_confidence in ('strong', 'medium', 'weak', 'none')",
            name="ck_poi_candidates_match_confidence",
        ),
        CheckConstraint(
            "review_status in ("
            "'pending_review', 'approved', 'rejected', 'needs_research', "
            "'quarantined'"
            ")",
            name="ck_poi_candidates_review_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    source_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=PoiCandidateSourceType.unknown.value,
        index=True,
    )
    source_provider: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )
    crawl_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    master_calendar_source_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
    )
    extracted_event_candidate_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
    )
    api_feed_run_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
    )
    api_feed_record_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
    )
    import_batch_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
    )
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_fragment_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    normalized_payload_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
    )
    candidate_name: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True,
    )
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    subcategory: Mapped[str | None] = mapped_column(String(128), nullable=True)
    suggested_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    suggested_subcategory: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    state: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    zip_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    country: Mapped[str | None] = mapped_column(String(255), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    instagram: Mapped[str | None] = mapped_column(Text, nullable=True)
    facebook: Mapped[str | None] = mapped_column(Text, nullable=True)
    x_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    tiktok: Mapped[str | None] = mapped_column(Text, nullable=True)
    youtube: Mapped[str | None] = mapped_column(Text, nullable=True)
    spotify_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    main_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    additional_image_urls_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    music_signal_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )
    poi_quality_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    poi_quality_flags_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )
    dedupe_key: Mapped[str] = mapped_column(Text, nullable=False, default="")
    match_status: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=PoiCandidateMatchStatus.unmatched.value,
        index=True,
    )
    matched_poi_location_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
    )
    match_confidence: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=PoiCandidateMatchConfidence.none.value,
        index=True,
    )
    match_reason_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    review_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=PoiCandidateReviewStatus.pending_review.value,
        index=True,
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_poi_location_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    @property
    def raw_fragment(self) -> dict[str, object]:
        return _json_dict(self.raw_fragment_json)

    @property
    def normalized_payload(self) -> dict[str, object]:
        return _json_dict(self.normalized_payload_json)

    @property
    def additional_image_urls(self) -> list[str]:
        return [str(item) for item in _json_list(self.additional_image_urls_json)]

    @property
    def poi_quality_flags(self) -> list[str]:
        return [str(item) for item in _json_list(self.poi_quality_flags_json)]

    @property
    def match_reason(self) -> dict[str, object]:
        return _json_dict(self.match_reason_json)


class Event(Base):
    """Normalized event extracted from a successful crawl run."""

    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint(
            "crawl_run_id",
            "dedupe_key",
            name="uq_events_crawl_run_dedupe_key",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("calendar_sources.id"),
        nullable=True,
        index=True,
    )
    crawl_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("crawl_runs.id"),
        nullable=True,
        index=True,
    )
    event_venue_id: Mapped[int | None] = mapped_column(
        ForeignKey("event_venues.id"),
        nullable=True,
        index=True,
    )
    region_id: Mapped[int | None] = mapped_column(
        ForeignKey("regions.id"),
        nullable=True,
        index=True,
    )
    region_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    import_batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    api_feed_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    api_feed_record_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    api_provider_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    api_source_record_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    api_mapping_warnings_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_quality_scores_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_event_type: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    provider_genre: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_subgenre: Mapped[str | None] = mapped_column(String(255), nullable=True)
    music_category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    normalized_genre: Mapped[str | None] = mapped_column(String(255), nullable=True)
    normalized_genres_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )
    genre_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    genre_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    music_relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    music_relevance_flags_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )
    ticket_link_classification: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    ticketing_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ticketing_provider_domain: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    ticket_link_repair_strategy: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    ticket_link_repair_source: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    ticket_link_repair_suggestion: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    recommended_ticket_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    ticket_link_quality_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    provider_doc_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    dedupe_source_fields_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    venue_match_fields_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    ingestion_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    upstream_event_source: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    upstream_event_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    provider_music_segment: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    source_chain_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_identifiers_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    ticket_offers_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    provenance_flags_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_status: Mapped[str | None] = mapped_column(String(128), nullable=True)
    has_time: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    all_day: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="Concert")
    record_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="event",
    )
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, default="ics")
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    headliner: Mapped[str | None] = mapped_column(String(500), nullable=True)
    supporting_artists: Mapped[str | None] = mapped_column(Text, nullable=True)
    genre: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_datetime: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    end_datetime: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    timezone: Mapped[str | None] = mapped_column(String(128), nullable=True)
    location_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    tickets_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[str | None] = mapped_column(String(255), nullable=True)
    age_restriction: Mapped[str | None] = mapped_column(String(255), nullable=True)
    doors_time: Mapped[str | None] = mapped_column(String(32), nullable=True)
    main_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    additional_image_urls: Mapped[str | None] = mapped_column(Text, nullable=True)
    selected_main_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    selected_image_candidate_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    image_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    image_quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    image_quality_flags_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )
    image_clearance_status: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    image_source_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    image_source_provider: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    image_role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    image_selection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_selected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    spotify_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    spotify_artist_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    spotify_artist_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    spotify_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    spotify_match_confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    spotify_preview_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    enrichment_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    enrichment_flags_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )
    enrichment_suggestions_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
    )
    source_event_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    dedupe_key: Mapped[str] = mapped_column(String(64), nullable=False)
    dedupe_confidence: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="strong",
    )
    duplicate_status: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="none",
        index=True,
    )
    duplicate_candidate_group_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
    )
    canonical_event_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latest_source_claim_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_claim_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    last_significant_change_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    event_lifecycle_status: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="active",
    )
    last_update_summary_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )
    changed_fields_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )
    update_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    raw_event_json: Mapped[str] = mapped_column(Text, nullable=False)
    publish_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=PublishStatus.needs_review.value,
        index=True,
    )
    publish_ready_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    publish_blockers_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    unpublished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_published_snapshot_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    source: Mapped[CalendarSource | None] = relationship(back_populates="events")
    crawl_run: Mapped[CrawlRun | None] = relationship(back_populates="events")
    venue: Mapped[EventVenue | None] = relationship(back_populates="events")
    region: Mapped[Region | None] = relationship(back_populates="events")
    image_candidates: Mapped[list["ImageCandidate"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
    )
    source_claims: Mapped[list["EventSourceClaim"]] = relationship(
        back_populates="event",
        foreign_keys="EventSourceClaim.event_id",
    )
    artist_links: Mapped[list["EventArtist"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
    )

    @property
    def enrichment_flags(self) -> list[str]:
        try:
            parsed = json.loads(self.enrichment_flags_json)
        except json.JSONDecodeError:
            return []
        return [str(item) for item in parsed] if isinstance(parsed, list) else []

    @property
    def source_chain(self) -> list[object]:
        return _json_list(self.source_chain_json)

    @property
    def external_identifiers(self) -> list[object]:
        return _json_list(self.external_identifiers_json)

    @property
    def ticket_offers(self) -> list[object]:
        return _json_list(self.ticket_offers_json)

    @property
    def provenance_flags(self) -> list[str]:
        return [str(item) for item in _json_list(self.provenance_flags_json)]

    @property
    def image_quality_flags(self) -> list[str]:
        return [str(item) for item in _json_list(self.image_quality_flags_json)]

    @property
    def normalized_genres(self) -> list[str]:
        return [str(item) for item in _json_list(self.normalized_genres_json)]

    @property
    def music_relevance_flags(self) -> list[str]:
        return [str(item) for item in _json_list(self.music_relevance_flags_json)]

    @property
    def changed_fields(self) -> list[object]:
        return _json_list(self.changed_fields_json)

    @property
    def last_update_summary(self) -> list[object]:
        return _json_list(self.last_update_summary_json)


class EventSourceClaim(Base):
    """One inbound source assertion about a normalized Concert event."""

    __tablename__ = "event_source_claims"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    event_id: Mapped[int | None] = mapped_column(
        ForeignKey("events.id"),
        nullable=True,
        index=True,
    )
    candidate_event_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="unknown",
        index=True,
    )
    ingestion_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    upstream_event_source: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    upstream_event_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    provider_event_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    provider_event_type: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    provider_record_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_record_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    master_calendar_source_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    calendar_source_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    crawl_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    import_batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    api_feed_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    api_feed_record_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    normalized_payload_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
    )
    field_values_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    source_chain_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    ticket_offers_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    external_identifiers_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )
    claim_dedupe_key: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    claim_dedupe_confidence: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="weak",
    )
    matched_event_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    match_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    match_reason_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    event: Mapped[Event | None] = relationship(
        back_populates="source_claims",
        foreign_keys=[event_id],
    )

    @property
    def match_reason(self) -> list[object]:
        return _json_list(self.match_reason_json)


class CanonicalArtist(Base):
    """Canonical Music Roadtrip artist identity used across event sources."""

    __tablename__ = "canonical_artists"
    __table_args__ = (
        UniqueConstraint("artist_key", name="uq_canonical_artists_artist_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    artist_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True,
    )
    alternate_names_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )
    artist_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=ArtistType.unknown.value,
    )
    primary_genre: Mapped[str | None] = mapped_column(String(255), nullable=True)
    normalized_genres_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )
    provider_genres_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )
    spotify_artist_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    spotify_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    jambase_artist_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cityspark_artist_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ticketmaster_artist_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    musicbrainz_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    official_website: Mapped[str | None] = mapped_column(Text, nullable=True)
    instagram: Mapped[str | None] = mapped_column(Text, nullable=True)
    facebook: Mapped[str | None] = mapped_column(Text, nullable=True)
    x_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    youtube: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_candidate_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    image_clearance_status: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    source_claim_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_flags_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )
    raw_source_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    source_claims: Mapped[list["ArtistSourceClaim"]] = relationship(
        back_populates="artist",
        cascade="all, delete-orphan",
    )
    event_links: Mapped[list["EventArtist"]] = relationship(
        back_populates="artist",
        cascade="all, delete-orphan",
    )

    @property
    def alternate_names(self) -> list[str]:
        return [str(item) for item in _json_list(self.alternate_names_json)]

    @property
    def normalized_genres(self) -> list[str]:
        return [str(item) for item in _json_list(self.normalized_genres_json)]

    @property
    def provider_genres(self) -> list[str]:
        return [str(item) for item in _json_list(self.provider_genres_json)]

    @property
    def quality_flags(self) -> list[str]:
        return [str(item) for item in _json_list(self.quality_flags_json)]


class ArtistSourceClaim(Base):
    """One source assertion about a canonical artist identity."""

    __tablename__ = "artist_source_claims"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    artist_id: Mapped[int | None] = mapped_column(
        ForeignKey("canonical_artists.id"),
        nullable=True,
        index=True,
    )
    source_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=ArtistSourceType.unknown.value,
        index=True,
    )
    provider_artist_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    provider_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    external_identifiers_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )
    same_as_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    genres_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    match_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    match_reason_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    artist: Mapped[CanonicalArtist | None] = relationship(
        back_populates="source_claims",
    )

    @property
    def external_identifiers(self) -> list[object]:
        return _json_list(self.external_identifiers_json)

    @property
    def same_as(self) -> list[object]:
        return _json_list(self.same_as_json)

    @property
    def genres(self) -> list[str]:
        return [str(item) for item in _json_list(self.genres_json)]

    @property
    def match_reason(self) -> list[object]:
        return _json_list(self.match_reason_json)


class EventArtist(Base):
    """Link table for performers attached to normalized Concert events."""

    __tablename__ = "event_artists"
    __table_args__ = (
        UniqueConstraint(
            "event_id",
            "artist_id",
            "role",
            name="uq_event_artists_event_artist_role",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id"),
        nullable=False,
        index=True,
    )
    artist_id: Mapped[int] = mapped_column(
        ForeignKey("canonical_artists.id"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=EventArtistRole.unknown.value,
    )
    performance_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    performance_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    provider_artist_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_claim_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    event: Mapped[Event] = relationship(back_populates="artist_links")
    artist: Mapped[CanonicalArtist] = relationship(back_populates="event_links")


class EventDuplicateGroup(Base):
    """Open duplicate review group for possible same-real-world concerts."""

    __tablename__ = "event_duplicate_groups"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    group_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    confidence: Mapped[str] = mapped_column(String(32), nullable=False, default="weak")
    reason_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    members: Mapped[list["EventDuplicateGroupMember"]] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
    )

    @property
    def reasons(self) -> list[object]:
        return _json_list(self.reason_json)


class EventDuplicateGroupMember(Base):
    """Membership row linking an event/source claim to a duplicate group."""

    __tablename__ = "event_duplicate_group_members"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("event_duplicate_groups.id"),
        nullable=False,
        index=True,
    )
    event_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    source_claim_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    role: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="duplicate_candidate",
    )
    match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    group: Mapped[EventDuplicateGroup] = relationship(back_populates="members")

    @property
    def reasons(self) -> list[object]:
        return _json_list(self.reason_json)


class ImageCandidate(Base):
    """Reviewable image option for a Concert event or venue profile."""

    __tablename__ = "image_candidates"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    event_id: Mapped[int | None] = mapped_column(
        ForeignKey("events.id"),
        nullable=True,
        index=True,
    )
    venue_id: Mapped[int | None] = mapped_column(
        ForeignKey("event_venues.id"),
        nullable=True,
        index=True,
    )
    source_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="unknown",
    )
    source_provider: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_chain_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    candidate_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    candidate_status: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="pending_review",
    )
    clearance_status: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="unknown",
    )
    clearance_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_role: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="unknown",
    )
    rescue_source: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="unknown",
    )
    rescue_priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=100,
    )
    generic_detection_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )
    generic_detection_reasons_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )
    text_graphic_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )
    poster_flyer_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )
    admat_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )
    artist_match_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )
    venue_context_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )
    music_signal_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )
    selected_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    selection_explanation_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
    )
    source_payload_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_evidence_only: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    can_be_final_image: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    aspect_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    pixel_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    orientation: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="unknown",
    )
    is_direct_image_asset: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_social_media_url: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_accessible: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    has_text_detected: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    has_watermark_detected: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    has_logo_detected: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    appears_stock_or_placeholder: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    appears_poster_or_flyer: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    appears_live_performance: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    appears_artist_subject: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    appears_venue_in_action: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    appears_food_or_drink: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    appears_unrelated_place: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    appears_generic_crowd: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    visual_quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    subject_relevance_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    technical_quality_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    provenance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    approval_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    rejection_reasons_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )
    qa_flags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    perceptual_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    average_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    duplicate_hash_group_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    reused_across_event_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    ocr_text_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text_area_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    text_location_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    event: Mapped[Event | None] = relationship(back_populates="image_candidates")
    venue: Mapped[EventVenue | None] = relationship(back_populates="image_candidates")

    @property
    def qa_flags(self) -> list[str]:
        return [str(item) for item in _json_list(self.qa_flags_json)]

    @property
    def rejection_reasons(self) -> list[str]:
        return [str(item) for item in _json_list(self.rejection_reasons_json)]

    @property
    def generic_detection_reasons(self) -> list[str]:
        return [
            str(item)
            for item in _json_list(self.generic_detection_reasons_json)
        ]

    @property
    def selection_explanation(self) -> dict[str, object]:
        if not self.selection_explanation_json:
            return {}
        try:
            parsed = json.loads(self.selection_explanation_json)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}


class SubmissionAttempt(Base):
    """Lightweight local rate-limit signal for public submissions."""

    __tablename__ = "submission_attempts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    submission_type: Mapped[str] = mapped_column(String(64), nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    submitted_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False, default="low")
    risk_flags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    was_invalid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )


class BlockedSubmitter(Base):
    """Local POC blocklist for emails and submitted URL domains."""

    __tablename__ = "blocked_submitters"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    email_domain: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    url_domain: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


class TrustedSubmitter(Base):
    """Local POC trusted submitter/domain list."""

    __tablename__ = "trusted_submitters"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    organization_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    email_domain: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    url_domain: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


class AdminAuditLog(Base):
    """Security-relevant admin action log."""

    __tablename__ = "admin_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    actor_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    target_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    user_agent_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    @property
    def metadata_payload(self) -> dict[str, object]:
        return _json_dict(self.metadata_json)


class ImportBatch(Base):
    """Risk-reviewed uploaded file batch."""

    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    submission_type: Mapped[str] = mapped_column(String(64), nullable=False)
    organization_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    review_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=SourceReviewStatus.pending_review.value,
    )
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False, default="low")
    risk_flags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    valid_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    invalid_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    events_created_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    events_updated_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    duplicate_candidate_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    source_claims_created_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    rows_rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_quarantined_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    @property
    def risk_flags(self) -> list[str]:
        try:
            parsed = json.loads(self.risk_flags_json)
        except json.JSONDecodeError:
            return []
        return [str(item) for item in parsed] if isinstance(parsed, list) else []


class StagedEvent(Base):
    """Risk-reviewed staged concert event row."""

    __tablename__ = "staged_events"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    import_batch_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    validation_status: Mapped[str] = mapped_column(String(32), nullable=False)
    validation_errors: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False, default="low")
    risk_flags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="Concert")
    event_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    headliner: Mapped[str | None] = mapped_column(String(500), nullable=True)
    supporting_artists: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    start_time: Mapped[str | None] = mapped_column(String(32), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(128), nullable=True)
    end_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    end_time: Mapped[str | None] = mapped_column(String(32), nullable=True)
    doors_time: Mapped[str | None] = mapped_column(String(32), nullable=True)
    venue_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    venue_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state: Mapped[str | None] = mapped_column(String(255), nullable=True)
    zip_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    country: Mapped[str | None] = mapped_column(String(255), nullable=True)
    latitude: Mapped[str | None] = mapped_column(String(64), nullable=True)
    longitude: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    tickets_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[str | None] = mapped_column(String(255), nullable=True)
    age_restriction: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    spotify_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    youtube_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    instagram: Mapped[str | None] = mapped_column(Text, nullable=True)
    facebook: Mapped[str | None] = mapped_column(Text, nullable=True)
    x_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    tiktok: Mapped[str | None] = mapped_column(Text, nullable=True)
    main_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    additional_image_urls: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_event_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_row_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    @property
    def risk_flags(self) -> list[str]:
        try:
            parsed = json.loads(self.risk_flags_json)
        except json.JSONDecodeError:
            return []
        return [str(item) for item in parsed] if isinstance(parsed, list) else []


class StagedCalendarSource(Base):
    """Risk-reviewed staged calendar source row."""

    __tablename__ = "staged_calendar_sources"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    import_batch_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    validation_status: Mapped[str] = mapped_column(String(32), nullable=False)
    validation_errors: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False, default="low")
    risk_flags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    organization_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    calendar_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    calendar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_url_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expected_category: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="Concert",
    )
    venue_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str | None] = mapped_column(String(255), nullable=True)
    region_or_market: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    crawl_frequency: Mapped[str | None] = mapped_column(String(64), nullable=True)
    authorization_confirmed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    dedupe_status: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="new",
    )
    existing_master_calendar_source_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_row_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    @property
    def risk_flags(self) -> list[str]:
        try:
            parsed = json.loads(self.risk_flags_json)
        except json.JSONDecodeError:
            return []
        return [str(item) for item in parsed] if isinstance(parsed, list) else []


class MasterCalendarSource(Base):
    """Canonical source registry row deduped by canonical URL hash."""

    __tablename__ = "master_calendar_sources"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
    )
    original_url: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="unknown",
    )
    expected_category: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="Concert",
    )
    venue_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str | None] = mapped_column(String(255), nullable=True)
    region_or_market: Mapped[str | None] = mapped_column(String(255), nullable=True)
    region_id: Mapped[int | None] = mapped_column(
        ForeignKey("regions.id"),
        nullable=True,
        index=True,
    )
    region_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    review_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=SourceReviewStatus.pending_review.value,
    )
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False, default="low")
    risk_flags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    crawl_frequency: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    last_crawled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_extractor_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_extraction_status: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )
    last_event_candidate_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    extraction_success_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    extraction_failure_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    unsupported_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    source_quality_flags_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )
    source_trust_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_trust_grade: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_quality_score_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    @property
    def risk_flags(self) -> list[str]:
        try:
            parsed = json.loads(self.risk_flags_json)
        except json.JSONDecodeError:
            return []
        return [str(item) for item in parsed] if isinstance(parsed, list) else []

    @property
    def source_quality_flags(self) -> list[str]:
        return [str(item) for item in _json_list(self.source_quality_flags_json)]

    region: Mapped[Region | None] = relationship(
        back_populates="master_calendar_sources",
    )
    scrape_profile: Mapped["SourceScrapeProfile | None"] = relationship(
        back_populates="master_calendar_source",
        cascade="all, delete-orphan",
        uselist=False,
    )


class SourceScrapeProfile(Base):
    """Remembered scrape recipe and health metrics for a master calendar source."""

    __tablename__ = "source_scrape_profiles"
    __table_args__ = (
        UniqueConstraint(
            "master_calendar_source_id",
            name="uq_source_scrape_profiles_master_calendar_source_id",
        ),
        CheckConstraint(
            "platform_type in ("
            "'ics', 'rss_atom', 'json_ld', 'static_html', 'wordpress_events', "
            "'the_events_calendar', 'eventbrite_page', 'venue_calendar', "
            "'tourism_board_calendar', 'unknown', 'unsupported'"
            ")",
            name="ck_source_scrape_profiles_platform_type",
        ),
        CheckConstraint(
            "extractor_type in ("
            "'ics', 'json_ld_event', 'rss_atom', 'html_event_list', "
            "'generic_html_links', 'unsupported'"
            ")",
            name="ck_source_scrape_profiles_extractor_type",
        ),
        CheckConstraint(
            "extractor_confidence in ('high', 'medium', 'low', 'unknown')",
            name="ck_source_scrape_profiles_extractor_confidence",
        ),
        CheckConstraint(
            "source_health_status in ("
            "'healthy', 'watch', 'needs_review', 'failing', 'paused', "
            "'unsupported'"
            ")",
            name="ck_source_scrape_profiles_source_health_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    master_calendar_source_id: Mapped[int] = mapped_column(
        ForeignKey("master_calendar_sources.id"),
        nullable=False,
        index=True,
    )
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    platform_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=SourceScrapePlatformType.unknown.value,
        index=True,
    )
    extractor_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=SourceScrapeExtractorType.unsupported.value,
        index=True,
    )
    extractor_confidence: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=SourceScrapeExtractorConfidence.unknown.value,
        index=True,
    )
    last_working_extractor: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    requires_javascript: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    supports_pagination: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    event_link_discovery_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    event_detail_link_pattern: Mapped[str | None] = mapped_column(Text, nullable=True)
    title_selector_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    date_selector_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    venue_selector_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    ticket_selector_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_selector_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    timezone_assumption: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_final_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_response_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_successful_crawl_run_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
    )
    last_failed_crawl_run_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
    )
    total_crawl_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    successful_crawl_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    failed_crawl_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    average_event_count: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )
    last_event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    missing_ticket_rate: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )
    missing_image_rate: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )
    poi_candidate_rate: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )
    source_health_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=SourceHealthStatus.watch.value,
        index=True,
    )
    developer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recipe_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1")
    recipe_locked_by_admin: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    master_calendar_source: Mapped[MasterCalendarSource] = relationship(
        back_populates="scrape_profile",
    )


class CalendarSourceSubmission(Base):
    """Claim/submission record for a master calendar source."""

    __tablename__ = "calendar_source_submissions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    master_calendar_source_id: Mapped[int] = mapped_column(
        ForeignKey("master_calendar_sources.id"),
        nullable=False,
        index=True,
    )
    organization_name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_email: Mapped[str] = mapped_column(String(255), nullable=False)
    original_url: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    authorization_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False, default="low")
    risk_flags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    review_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=SourceReviewStatus.pending_review.value,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    import_batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_row_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    @property
    def risk_flags(self) -> list[str]:
        try:
            parsed = json.loads(self.risk_flags_json)
        except json.JSONDecodeError:
            return []
        return [str(item) for item in parsed] if isinstance(parsed, list) else []


class CalendarSourceResearchBatch(Base):
    """City/region source-research batch before master source onboarding."""

    __tablename__ = "calendar_source_research_batches"
    __table_args__ = (
        CheckConstraint(
            "status in ("
            "'draft', 'preflight_ready', 'preflighted', 'approved_for_crawl', "
            "'crawl_running', 'crawl_complete', 'review_complete', 'archived'"
            ")",
            name="ck_calendar_source_research_batches_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    batch_name: Mapped[str] = mapped_column(String(255), nullable=False)
    region_id: Mapped[int | None] = mapped_column(
        ForeignKey("regions.id"),
        nullable=True,
        index=True,
    )
    city: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    state: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    country: Mapped[str | None] = mapped_column(String(255), nullable=True)
    research_owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_goal_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=CalendarSourceResearchBatchStatus.draft.value,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    items: Mapped[list["CalendarSourceResearchItem"]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
    )
    region: Mapped[Region | None] = relationship()


class CalendarSourceResearchItem(Base):
    """One researched calendar URL staged before master registry approval."""

    __tablename__ = "calendar_source_research_items"
    __table_args__ = (
        CheckConstraint(
            "source_type in ("
            "'venue_calendar', 'tourism_board_calendar', 'chamber_calendar', "
            "'festival_calendar', 'publication_calendar', 'artist_calendar', "
            "'ticketing_calendar', 'unknown'"
            ")",
            name="ck_calendar_source_research_items_source_type",
        ),
        CheckConstraint(
            "authorization_status in ("
            "'internal_research', 'partner_supplied', 'public_submission', "
            "'unknown'"
            ")",
            name="ck_calendar_source_research_items_authorization_status",
        ),
        CheckConstraint(
            "preflight_status in ("
            "'pending', 'success', 'warning', 'failure', 'blocked'"
            ")",
            name="ck_calendar_source_research_items_preflight_status",
        ),
        CheckConstraint(
            "dedupe_status in ("
            "'new_source', 'existing_master_source', 'possible_duplicate', "
            "'invalid_url', 'blocked_url'"
            ")",
            name="ck_calendar_source_research_items_dedupe_status",
        ),
        CheckConstraint(
            "review_status in ("
            "'pending_review', 'approved', 'rejected', 'needs_research'"
            ")",
            name="ck_calendar_source_research_items_review_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("calendar_source_research_batches.id"),
        nullable=False,
        index=True,
    )
    submitted_url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_source_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    organization_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=CalendarSourceResearchSourceType.unknown.value,
        index=True,
    )
    city: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    state: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    country: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    authorization_status: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=CalendarSourceResearchAuthorizationStatus.internal_research.value,
    )
    preflight_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=CalendarSourceResearchPreflightStatus.pending.value,
        index=True,
    )
    preflight_http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    preflight_content_type: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    preflight_final_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    preflight_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    dedupe_status: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=CalendarSourceResearchDedupeStatus.new_source.value,
        index=True,
    )
    matched_master_calendar_source_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
    )
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False, default="low")
    risk_flags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    review_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=CalendarSourceResearchReviewStatus.pending_review.value,
        index=True,
    )
    created_master_calendar_source_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    batch: Mapped[CalendarSourceResearchBatch] = relationship(back_populates="items")

    @property
    def risk_flags(self) -> list[str]:
        return [str(item) for item in _json_list(self.risk_flags_json)]


class ApiFeedRun(Base):
    """One private admin import/review run for provider-style API data."""

    __tablename__ = "api_feed_runs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    provider_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider_type: Mapped[str] = mapped_column(String(64), nullable=False)
    run_mode: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    requested_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    normalized_candidate_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    approved_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    held_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_candidate_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    compliance_expiration_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    request_preview_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
    )
    parameters_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    records: Mapped[list["ApiFeedRecord"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )


class AppFeedExport(Base):
    """One generated app-facing JSON feed export snapshot."""

    __tablename__ = "app_feed_exports"
    __table_args__ = (
        CheckConstraint(
            "export_type in ('events', 'pois', 'venues', 'full')",
            name="ck_app_feed_exports_export_type",
        ),
        CheckConstraint(
            "status in ('pending', 'success', 'failure')",
            name="ck_app_feed_exports_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    export_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=AppFeedExportStatus.pending.value,
        index=True,
    )
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    generated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    output_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


class PoiInventoryExport(Base):
    """One generated POI inventory or dedupe-index snapshot artifact."""

    __tablename__ = "poi_inventory_exports"
    __table_args__ = (
        CheckConstraint(
            "export_type in ('full_inventory_jsonl', 'dedupe_index_json', 'manifest')",
            name="ck_poi_inventory_exports_export_type",
        ),
        CheckConstraint(
            "status in ('pending', 'success', 'failure')",
            name="ck_poi_inventory_exports_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    export_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    export_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=PoiInventoryExportStatus.pending.value,
        index=True,
    )
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_key_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sha256_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    generated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    @property
    def metadata_payload(self) -> dict[str, object]:
        return _json_dict(self.metadata_json)


class AppSearchIndex(Base):
    """Local app-facing search index built from normalized internal data."""

    __tablename__ = "app_search_index"
    __table_args__ = (
        UniqueConstraint("search_key", name="uq_app_search_index_search_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    search_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=AppSearchEntityType.unknown.value,
        index=True,
    )
    entity_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(500), nullable=False)
    alternate_names_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )
    search_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    subcategory: Mapped[str | None] = mapped_column(String(128), nullable=True)
    region_id: Mapped[int | None] = mapped_column(
        ForeignKey("regions.id"),
        nullable=True,
        index=True,
    )
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str | None] = mapped_column(String(255), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_record_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    search_weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    popularity_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    app_feed_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    certified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_upcoming_events: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    upcoming_event_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    next_event_datetime: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_flags_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    region: Mapped[Region | None] = relationship(back_populates="app_search_entries")

    @property
    def alternate_names(self) -> list[str]:
        return [str(item) for item in _json_list(self.alternate_names_json)]

    @property
    def quality_flags(self) -> list[str]:
        return [str(item) for item in _json_list(self.quality_flags_json)]


class AppDiscoverySlot(Base):
    """Lightweight app discovery slot contract for future carousels/editorial."""

    __tablename__ = "app_discovery_slots"
    __table_args__ = (
        UniqueConstraint("slot_key", name="uq_app_discovery_slots_slot_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    slot_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    slot_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=DiscoverySlotType.event_carousel.value,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    region_id: Mapped[int | None] = mapped_column(
        ForeignKey("regions.id"),
        nullable=True,
        index=True,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    region: Mapped[Region | None] = relationship(back_populates="discovery_slots")

    @property
    def payload(self) -> dict[str, object]:
        return _json_dict(self.payload_json)


class Itinerary(Base):
    """App-safe Road Trip/Tour collection built from existing internal records."""

    __tablename__ = "itineraries"
    __table_args__ = (
        UniqueConstraint("itinerary_key", name="uq_itineraries_itinerary_key"),
        UniqueConstraint("slug", name="uq_itineraries_slug"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    itinerary_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    subtitle: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    itinerary_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=ItineraryType.road_trip.value,
        index=True,
    )
    display_label: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=ItineraryDisplayLabel.road_trip.value,
    )
    status: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=ItineraryStatus.draft.value,
        index=True,
    )
    region_id: Mapped[int | None] = mapped_column(
        ForeignKey("regions.id"),
        nullable=True,
        index=True,
    )
    destination_partner_id: Mapped[int | None] = mapped_column(
        ForeignKey("destination_partners.id"),
        nullable=True,
        index=True,
    )
    artist_id: Mapped[int | None] = mapped_column(
        ForeignKey("canonical_artists.id"),
        nullable=True,
        index=True,
    )
    start_city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    start_state: Mapped[str | None] = mapped_column(String(255), nullable=True)
    start_country: Mapped[str | None] = mapped_column(String(255), nullable=True)
    end_city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    end_state: Mapped[str | None] = mapped_column(String(255), nullable=True)
    end_country: Mapped[str | None] = mapped_column(String(255), nullable=True)
    estimated_duration_text: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    estimated_distance_text: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    hero_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    image_candidate_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    music_theme: Mapped[str | None] = mapped_column(String(255), nullable=True)
    normalized_genres_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )
    tags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    featured: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sponsored_future: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    app_feed_ready: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
    )
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_flags_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    region: Mapped[Region | None] = relationship()
    destination_partner: Mapped[DestinationPartner | None] = relationship()
    artist: Mapped[CanonicalArtist | None] = relationship()
    stops: Mapped[list["ItineraryStop"]] = relationship(
        back_populates="itinerary",
        cascade="all, delete-orphan",
        order_by="ItineraryStop.stop_order",
    )
    segments: Mapped[list["ItinerarySegment"]] = relationship(
        back_populates="itinerary",
        cascade="all, delete-orphan",
        order_by="ItinerarySegment.segment_order",
    )

    @property
    def normalized_genres(self) -> list[str]:
        return [str(item) for item in _json_list(self.normalized_genres_json)]

    @property
    def tags(self) -> list[str]:
        return [str(item) for item in _json_list(self.tags_json)]

    @property
    def quality_flags(self) -> list[str]:
        return [str(item) for item in _json_list(self.quality_flags_json)]


class ItineraryStop(Base):
    """One app-safe itinerary stop snapshot referencing an internal record."""

    __tablename__ = "itinerary_stops"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    itinerary_id: Mapped[int] = mapped_column(
        ForeignKey("itineraries.id"),
        nullable=False,
        index=True,
    )
    stop_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    stop_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=ItineraryStopType.custom.value,
        index=True,
    )
    event_id: Mapped[int | None] = mapped_column(
        ForeignKey("events.id"),
        nullable=True,
        index=True,
    )
    poi_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("poi_locations.id"),
        nullable=True,
        index=True,
    )
    event_venue_id: Mapped[int | None] = mapped_column(
        ForeignKey("event_venues.id"),
        nullable=True,
        index=True,
    )
    region_id: Mapped[int | None] = mapped_column(
        ForeignKey("regions.id"),
        nullable=True,
        index=True,
    )
    artist_id: Mapped[int | None] = mapped_column(
        ForeignKey("canonical_artists.id"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    subtitle: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str | None] = mapped_column(String(255), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    start_datetime: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    end_datetime: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    stop_duration_text: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    ticket_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    website_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    app_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    itinerary: Mapped[Itinerary] = relationship(back_populates="stops")
    event: Mapped[Event | None] = relationship()
    poi_location: Mapped[PoiLocation | None] = relationship()
    event_venue: Mapped[EventVenue | None] = relationship()
    region: Mapped[Region | None] = relationship()
    artist: Mapped[CanonicalArtist | None] = relationship()


class ItinerarySegment(Base):
    """Manual route segment metadata between two itinerary stops."""

    __tablename__ = "itinerary_segments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    itinerary_id: Mapped[int] = mapped_column(
        ForeignKey("itineraries.id"),
        nullable=False,
        index=True,
    )
    from_stop_id: Mapped[int | None] = mapped_column(
        ForeignKey("itinerary_stops.id"),
        nullable=True,
        index=True,
    )
    to_stop_id: Mapped[int | None] = mapped_column(
        ForeignKey("itinerary_stops.id"),
        nullable=True,
        index=True,
    )
    segment_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    distance_miles: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_drive_time_text: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    estimated_walk_time_text: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    navigation_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    route_provider: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=ItineraryRouteProvider.none.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    itinerary: Mapped[Itinerary] = relationship(back_populates="segments")
    from_stop: Mapped[ItineraryStop | None] = relationship(
        foreign_keys=[from_stop_id],
    )
    to_stop: Mapped[ItineraryStop | None] = relationship(foreign_keys=[to_stop_id])


class BackgroundJob(Base):
    """One DB-backed local background job queued by an admin or scheduler."""

    __tablename__ = "background_jobs"
    __table_args__ = (
        CheckConstraint(
            "job_type in ("
            "'crawl_source', 'bulk_crawl', 'provider_sandbox_jambase', "
            "'provider_sandbox_cityspark', 'image_preflight', 'app_feed_export', "
            "'event_photo_rescue', 'api_feed_run_photo_rescue', "
            "'recent_events_photo_rescue', "
            "'ticket_page_image_enrichment', "
            "'api_feed_run_ticket_image_enrichment', "
            "'recent_events_ticket_image_enrichment', "
            "'poi_registry_import', "
            "'extract_crawl_run', 'approve_extracted_event_candidate', "
            "'process_extracted_event_batch', 'scheduled_crawl_due_sources', "
            "'source_quality_rollup', 'region_partner_report', "
            "'all_source_quality_rollup', 'rebuild_app_search_index', "
            "'app_map_feed_export', 'app_filter_options_export', "
            "'poi_inventory_snapshot_export', 'source_registry_snapshot_export', "
            "'poi_candidate_match', 'all_poi_candidate_match', "
            "'poi_candidate_quality_rollup', "
            "'rebuild_artist_registry', 'artist_genre_normalization', "
            "'artist_image_rescue', "
            "'itinerary_quality_rollup', 'itinerary_app_feed_export', "
            "'build_artist_tour_itinerary', "
            "'build_region_itinerary_suggestions', "
            "'unknown'"
            ")",
            name="ck_background_jobs_job_type",
        ),
        CheckConstraint(
            "status in ("
            "'pending', 'running', 'success', 'failure', 'cancelled', 'skipped'"
            ")",
            name="ck_background_jobs_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=BackgroundJobStatus.pending.value,
        index=True,
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    queue_name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="default",
        index=True,
    )
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    locked_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    scheduled_for: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    @property
    def payload(self) -> dict[str, object]:
        try:
            parsed = json.loads(self.payload_json)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @property
    def result(self) -> dict[str, object]:
        if not self.result_json:
            return {}
        try:
            parsed = json.loads(self.result_json)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}


class ScheduledTask(Base):
    """Manual scheduler task definition that can enqueue background jobs."""

    __tablename__ = "scheduled_tasks"
    __table_args__ = (
        CheckConstraint(
            "task_type in ("
            "'crawl_due_sources', 'app_feed_export', 'provider_sandbox', "
            "'image_preflight', 'event_photo_rescue', "
            "'source_quality_rollup', 'partner_report_export', "
            "'rebuild_app_search_index', 'monthly_poi_inventory_snapshot', "
            "'monthly_source_registry_snapshot', 'itinerary_app_feed_export'"
            ")",
            name="ck_scheduled_tasks_task_type",
        ),
        CheckConstraint(
            "schedule_type in ("
            "'manual', 'interval', 'daily', 'weekly', 'biweekly', 'monthly'"
            ")",
            name="ck_scheduled_tasks_schedule_type",
        ),
        UniqueConstraint("task_key", name="uq_scheduled_tasks_task_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    task_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    schedule_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ScheduledTaskScheduleType.manual.value,
    )
    interval_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("background_jobs.id"),
        nullable=True,
    )
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    @property
    def payload(self) -> dict[str, object]:
        try:
            parsed = json.loads(self.payload_json)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}


class PublishedEventSnapshot(Base):
    """Historical app-facing event snapshot captured during export."""

    __tablename__ = "published_event_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    event_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    app_event_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )


class PublishedPoiSnapshot(Base):
    """Historical app-facing POI snapshot captured during export."""

    __tablename__ = "published_poi_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    poi_location_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    app_poi_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )


class ApiFeedRecord(Base):
    """One raw provider record plus its normalized Concert candidate."""

    __tablename__ = "api_feed_records"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    api_feed_run_id: Mapped[int] = mapped_column(
        ForeignKey("api_feed_runs.id"),
        nullable=False,
        index=True,
    )
    provider_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider_type: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_record_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    provider_event_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    provider_artist_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    provider_venue_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    normalized_payload_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
    )
    normalization_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="partial",
    )
    review_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=SourceReviewStatus.pending_review.value,
    )
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="Concert")
    record_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="event",
    )
    event_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    headliner: Mapped[str | None] = mapped_column(String(500), nullable=True)
    supporting_artists: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_event_type: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )
    provider_genre: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_subgenre: Mapped[str | None] = mapped_column(String(255), nullable=True)
    music_category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    normalized_genre: Mapped[str | None] = mapped_column(String(255), nullable=True)
    event_status: Mapped[str | None] = mapped_column(String(128), nullable=True)
    start_datetime: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    end_datetime: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    timezone: Mapped[str | None] = mapped_column(String(128), nullable=True)
    venue_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    venue_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state: Mapped[str | None] = mapped_column(String(255), nullable=True)
    zip_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    country: Mapped[str | None] = mapped_column(String(255), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    event_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    tickets_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    ticket_link_classification: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    ticketing_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ticketing_provider_domain: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    ticket_link_repair_strategy: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    ticket_link_repair_source: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    ticket_link_repair_suggestion: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    recommended_ticket_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    ticket_link_quality_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    price: Mapped[str | None] = mapped_column(String(255), nullable=True)
    age_restriction: Mapped[str | None] = mapped_column(String(255), nullable=True)
    doors_time: Mapped[str | None] = mapped_column(String(32), nullable=True)
    has_time: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    all_day: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    main_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    additional_image_urls: Mapped[str | None] = mapped_column(Text, nullable=True)
    spotify_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_record_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    dedupe_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    dedupe_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    duplicate_status: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="new",
    )
    venue_match_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    event_relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    photo_quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    field_completeness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_flags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    mapping_warnings_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )
    dedupe_source_fields_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
    )
    venue_match_fields_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
    )
    provider_doc_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    ingestion_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    upstream_event_source: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    upstream_event_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    upstream_artist_source: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    upstream_artist_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    upstream_venue_source: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    upstream_venue_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    provider_music_segment: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    source_chain_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )
    external_identifiers_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )
    ticket_offers_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    provenance_flags_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )
    compliance_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_event_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    run: Mapped[ApiFeedRun] = relationship(back_populates="records")

    @property
    def quality_flags(self) -> list[str]:
        try:
            parsed = json.loads(self.quality_flags_json)
        except json.JSONDecodeError:
            return []
        return [str(item) for item in parsed] if isinstance(parsed, list) else []

    @property
    def mapping_warnings(self) -> list[str]:
        try:
            parsed = json.loads(self.mapping_warnings_json)
        except json.JSONDecodeError:
            return []
        return [str(item) for item in parsed] if isinstance(parsed, list) else []

    @property
    def dedupe_source_fields(self) -> dict[str, object]:
        try:
            parsed = json.loads(self.dedupe_source_fields_json)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @property
    def venue_match_fields(self) -> dict[str, object]:
        try:
            parsed = json.loads(self.venue_match_fields_json)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @property
    def source_chain(self) -> list[object]:
        return _json_list(self.source_chain_json)

    @property
    def external_identifiers(self) -> list[object]:
        return _json_list(self.external_identifiers_json)

    @property
    def ticket_offers(self) -> list[object]:
        return _json_list(self.ticket_offers_json)

    @property
    def provenance_flags(self) -> list[str]:
        return [str(item) for item in _json_list(self.provenance_flags_json)]
