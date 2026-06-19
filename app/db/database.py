from typing import Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""


def sqlite_connect_args(database_url: str) -> dict[str, bool]:
    if database_url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


def make_engine(database_url: str) -> Engine:
    """Create the SQLAlchemy engine for the configured database URL."""

    return create_engine(
        database_url,
        connect_args=sqlite_connect_args(database_url),
        future=True,
    )


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a session factory bound to the app engine."""

    return sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        future=True,
    )


def create_all(engine: Engine) -> None:
    """Create local POC tables."""

    from app.db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    ensure_sqlite_schema(engine)


def ensure_sqlite_schema(engine: Engine) -> None:
    """Apply tiny SQLite-only column additions for the local POC database."""

    if engine.dialect.name != "sqlite":
        return

    with engine.begin() as connection:
        table_names = inspect(connection).get_table_names()
        if "calendar_sources" not in table_names:
            return

        add_missing_columns(
            connection,
            "calendar_sources",
            {
                "risk_score": "INTEGER NOT NULL DEFAULT 0",
                "risk_level": "VARCHAR(32) NOT NULL DEFAULT 'low'",
                "risk_flags_json": "TEXT NOT NULL DEFAULT '[]'",
                "reviewed_at": "DATETIME",
                "reviewed_by": "VARCHAR(255)",
                "review_status": "VARCHAR(32) NOT NULL DEFAULT 'pending_review'",
                "review_notes": "TEXT",
                "submitted_ip_hash": "VARCHAR(64)",
                "submitted_user_agent_hash": "VARCHAR(64)",
                "submitted_domain": "VARCHAR(255)",
                "claimed_source_id": "INTEGER",
                "form_rendered_at": "DATETIME",
                "submitted_via": "VARCHAR(64) NOT NULL DEFAULT 'submit-calendar'",
            },
        )

        add_missing_columns(
            connection,
            "events",
            {
                "event_venue_id": "INTEGER",
                "region_id": "INTEGER",
                "region_confidence": "FLOAT",
                "import_batch_id": "INTEGER",
                "api_feed_run_id": "INTEGER",
                "api_feed_record_id": "INTEGER",
                "api_provider_key": "VARCHAR(64)",
                "api_source_record_id": "VARCHAR(500)",
                "api_mapping_warnings_json": "TEXT",
                "api_quality_scores_json": "TEXT",
                "provider_event_type": "VARCHAR(128)",
                "provider_genre": "VARCHAR(255)",
                "provider_subgenre": "VARCHAR(255)",
                "music_category": "VARCHAR(255)",
                "normalized_genre": "VARCHAR(255)",
                "normalized_genres_json": "TEXT NOT NULL DEFAULT '[]'",
                "genre_confidence": "FLOAT",
                "genre_source": "VARCHAR(64)",
                "music_relevance_score": "FLOAT",
                "music_relevance_flags_json": "TEXT NOT NULL DEFAULT '[]'",
                "ticket_link_classification": "VARCHAR(64)",
                "ticketing_provider": "VARCHAR(64)",
                "ticketing_provider_domain": "VARCHAR(255)",
                "ticket_link_repair_strategy": "VARCHAR(64)",
                "ticket_link_repair_source": "VARCHAR(255)",
                "ticket_link_repair_suggestion": "TEXT",
                "recommended_ticket_link": "TEXT",
                "ticket_link_quality_score": "FLOAT",
                "provider_doc_notes": "TEXT",
                "dedupe_source_fields_json": "TEXT",
                "venue_match_fields_json": "TEXT",
                "ingestion_provider": "VARCHAR(64)",
                "upstream_event_source": "VARCHAR(64)",
                "upstream_event_id": "VARCHAR(500)",
                "provider_music_segment": "VARCHAR(255)",
                "source_chain_json": "TEXT",
                "external_identifiers_json": "TEXT",
                "ticket_offers_json": "TEXT",
                "provenance_flags_json": "TEXT",
                "event_status": "VARCHAR(128)",
                "has_time": "BOOLEAN",
                "all_day": "BOOLEAN",
                "category": "VARCHAR(64) NOT NULL DEFAULT 'Concert'",
                "record_type": "VARCHAR(64) NOT NULL DEFAULT 'event'",
                "source_type": "VARCHAR(64) NOT NULL DEFAULT 'ics'",
                "headliner": "VARCHAR(500)",
                "supporting_artists": "TEXT",
                "genre": "VARCHAR(255)",
                "tickets_link": "TEXT",
                "price": "VARCHAR(255)",
                "age_restriction": "VARCHAR(255)",
                "doors_time": "VARCHAR(32)",
                "main_image_url": "TEXT",
                "additional_image_urls": "TEXT",
                "selected_main_image_url": "TEXT",
                "selected_image_candidate_id": "INTEGER",
                "image_status": "VARCHAR(64)",
                "image_quality_score": "FLOAT",
                "image_quality_flags_json": "TEXT NOT NULL DEFAULT '[]'",
                "image_clearance_status": "VARCHAR(64)",
                "image_source_type": "VARCHAR(64)",
                "image_source_provider": "VARCHAR(255)",
                "image_role": "VARCHAR(64)",
                "image_selection_reason": "TEXT",
                "image_selected_at": "DATETIME",
                "spotify_url": "TEXT",
                "spotify_artist_id": "VARCHAR(255)",
                "spotify_artist_name": "VARCHAR(500)",
                "spotify_image_url": "TEXT",
                "spotify_match_confidence": "FLOAT",
                "spotify_preview_json": "TEXT",
                "enrichment_status": "VARCHAR(64)",
                "enrichment_flags_json": "TEXT NOT NULL DEFAULT '[]'",
                "enrichment_suggestions_json": "TEXT NOT NULL DEFAULT '{}'",
                "dedupe_confidence": "VARCHAR(32) NOT NULL DEFAULT 'strong'",
                "duplicate_status": "VARCHAR(64) NOT NULL DEFAULT 'none'",
                "duplicate_candidate_group_id": "INTEGER",
                "canonical_event_id": "INTEGER",
                "latest_source_claim_id": "INTEGER",
                "source_claim_count": "INTEGER NOT NULL DEFAULT 0",
                "first_seen_at": "DATETIME",
                "last_seen_at": "DATETIME",
                "last_significant_change_at": "DATETIME",
                "event_lifecycle_status": "VARCHAR(64) NOT NULL DEFAULT 'active'",
                "last_update_summary_json": "TEXT NOT NULL DEFAULT '[]'",
                "changed_fields_json": "TEXT NOT NULL DEFAULT '[]'",
                "update_count": "INTEGER NOT NULL DEFAULT 0",
                "publish_status": "VARCHAR(32) NOT NULL DEFAULT 'needs_review'",
                "publish_ready_score": "FLOAT",
                "publish_blockers_json": "TEXT NOT NULL DEFAULT '[]'",
                "published_at": "DATETIME",
                "unpublished_at": "DATETIME",
                "last_published_snapshot_json": "TEXT",
            },
        )
        connection.execute(
            text(
                "UPDATE events SET first_seen_at = COALESCE(first_seen_at, created_at, "
                "CURRENT_TIMESTAMP), last_seen_at = COALESCE(last_seen_at, updated_at, "
                "created_at, CURRENT_TIMESTAMP), dedupe_confidence = "
                "COALESCE(dedupe_confidence, 'strong'), duplicate_status = "
                "COALESCE(duplicate_status, 'none'), source_claim_count = "
                "COALESCE(source_claim_count, 0), event_lifecycle_status = "
                "COALESCE(event_lifecycle_status, 'active'), "
                "last_update_summary_json = COALESCE(last_update_summary_json, '[]'), "
                "changed_fields_json = COALESCE(changed_fields_json, '[]'), "
                "update_count = COALESCE(update_count, 0), "
                "publish_status = COALESCE(publish_status, 'needs_review'), "
                "publish_blockers_json = COALESCE(publish_blockers_json, '[]')"
            )
        )
        relax_events_nullable_provenance(connection)

        add_missing_columns(
            connection,
            "api_feed_runs",
            {
                "request_preview_json": "TEXT NOT NULL DEFAULT '{}'",
                "parameters_json": "TEXT NOT NULL DEFAULT '{}'",
            },
        )

        add_missing_columns(
            connection,
            "api_feed_records",
            {
                "description": "TEXT",
                "provider_event_type": "VARCHAR(128)",
                "provider_genre": "VARCHAR(255)",
                "provider_subgenre": "VARCHAR(255)",
                "music_category": "VARCHAR(255)",
                "normalized_genre": "VARCHAR(255)",
                "event_status": "VARCHAR(128)",
                "ticket_link_classification": "VARCHAR(64)",
                "ticketing_provider": "VARCHAR(64)",
                "ticketing_provider_domain": "VARCHAR(255)",
                "ticket_link_repair_strategy": "VARCHAR(64)",
                "ticket_link_repair_source": "VARCHAR(255)",
                "ticket_link_repair_suggestion": "TEXT",
                "recommended_ticket_link": "TEXT",
                "ticket_link_quality_score": "FLOAT",
                "doors_time": "VARCHAR(32)",
                "has_time": "BOOLEAN",
                "all_day": "BOOLEAN",
                "dedupe_source_fields_json": "TEXT NOT NULL DEFAULT '{}'",
                "venue_match_fields_json": "TEXT NOT NULL DEFAULT '{}'",
                "provider_doc_notes": "TEXT",
                "ingestion_provider": "VARCHAR(64)",
                "upstream_event_source": "VARCHAR(64)",
                "upstream_event_id": "VARCHAR(500)",
                "upstream_artist_source": "VARCHAR(64)",
                "upstream_artist_id": "VARCHAR(500)",
                "upstream_venue_source": "VARCHAR(64)",
                "upstream_venue_id": "VARCHAR(500)",
                "provider_music_segment": "VARCHAR(255)",
                "source_chain_json": "TEXT NOT NULL DEFAULT '[]'",
                "external_identifiers_json": "TEXT NOT NULL DEFAULT '[]'",
                "ticket_offers_json": "TEXT NOT NULL DEFAULT '[]'",
                "provenance_flags_json": "TEXT NOT NULL DEFAULT '[]'",
            },
        )

        add_missing_columns(
            connection,
            "image_candidates",
            {
                "rescue_source": "VARCHAR(64) NOT NULL DEFAULT 'unknown'",
                "rescue_priority": "INTEGER NOT NULL DEFAULT 100",
                "generic_detection_score": "FLOAT NOT NULL DEFAULT 0.0",
                "generic_detection_reasons_json": "TEXT NOT NULL DEFAULT '[]'",
                "text_graphic_score": "FLOAT NOT NULL DEFAULT 0.0",
                "poster_flyer_score": "FLOAT NOT NULL DEFAULT 0.0",
                "admat_score": "FLOAT NOT NULL DEFAULT 0.0",
                "artist_match_score": "FLOAT NOT NULL DEFAULT 0.0",
                "venue_context_score": "FLOAT NOT NULL DEFAULT 0.0",
                "music_signal_score": "FLOAT NOT NULL DEFAULT 0.0",
                "selected_reason": "TEXT",
                "selection_explanation_json": "TEXT NOT NULL DEFAULT '{}'",
                "source_payload_path": "TEXT",
                "source_evidence_only": "BOOLEAN NOT NULL DEFAULT 0",
                "can_be_final_image": "BOOLEAN NOT NULL DEFAULT 1",
            },
        )

        add_missing_columns(
            connection,
            "crawl_runs",
            {
                "final_url": "TEXT",
                "extractor_type": "VARCHAR(64)",
                "extraction_status": "VARCHAR(32)",
                "event_candidates_count": "INTEGER NOT NULL DEFAULT 0",
                "unsupported_reason": "TEXT",
                "extraction_warnings_json": "TEXT NOT NULL DEFAULT '[]'",
                "extraction_errors_json": "TEXT NOT NULL DEFAULT '[]'",
                "discovered_links_count": "INTEGER NOT NULL DEFAULT 0",
                "extraction_summary_json": "TEXT NOT NULL DEFAULT '{}'",
                "events_created_count": "INTEGER NOT NULL DEFAULT 0",
                "events_updated_count": "INTEGER NOT NULL DEFAULT 0",
                "duplicate_candidate_count": "INTEGER NOT NULL DEFAULT 0",
                "events_skipped_count": "INTEGER NOT NULL DEFAULT 0",
                "events_cancelled_count": "INTEGER NOT NULL DEFAULT 0",
                "source_claims_created_count": "INTEGER NOT NULL DEFAULT 0",
            },
        )

        add_missing_columns(
            connection,
            "event_venues",
            {
                "venue_key": "VARCHAR(64) NOT NULL DEFAULT ''",
                "display_name": "VARCHAR(500) NOT NULL DEFAULT ''",
                "address": "TEXT",
                "city": "VARCHAR(255)",
                "state": "VARCHAR(255)",
                "zip_code": "VARCHAR(32)",
                "country": "VARCHAR(255)",
                "latitude": "FLOAT",
                "longitude": "FLOAT",
                "website": "TEXT",
                "phone": "VARCHAR(255)",
                "description": "TEXT",
                "main_image_url": "TEXT",
                "additional_image_urls": "TEXT",
                "selected_main_image_url": "TEXT",
                "selected_image_candidate_id": "INTEGER",
                "image_status": "VARCHAR(64)",
                "image_quality_score": "FLOAT",
                "image_quality_flags_json": "TEXT NOT NULL DEFAULT '[]'",
                "image_clearance_status": "VARCHAR(64)",
                "image_role": "VARCHAR(64)",
                "image_selection_reason": "TEXT",
                "image_selected_at": "DATETIME",
                "category": "VARCHAR(64) NOT NULL DEFAULT 'Music Site'",
                "subcategory": "VARCHAR(64) NOT NULL DEFAULT 'Venues'",
                "created_at": "DATETIME",
                "updated_at": "DATETIME",
            },
        )

        add_missing_columns(
            connection,
            "poi_locations",
            {
                "canonical_poi_id": "VARCHAR(64) NOT NULL DEFAULT ''",
                "poi_dedupe_key": "TEXT NOT NULL DEFAULT ''",
                "poi_dedupe_confidence": (
                    "VARCHAR(32) NOT NULL DEFAULT 'strong'"
                ),
                "source_type": "VARCHAR(64) NOT NULL DEFAULT 'mapotic_export'",
                "source_record_id": "VARCHAR(255)",
                "mapotic_id": "VARCHAR(255)",
                "places_id": "VARCHAR(255)",
                "canonical_venue_id": "VARCHAR(255)",
                "display_name": "VARCHAR(500) NOT NULL DEFAULT ''",
                "normalized_name": "VARCHAR(500) NOT NULL DEFAULT ''",
                "category": "VARCHAR(64) NOT NULL DEFAULT 'Music Site'",
                "subcategory": "VARCHAR(128)",
                "latitude": "FLOAT",
                "longitude": "FLOAT",
                "address": "TEXT",
                "city": "VARCHAR(255)",
                "state": "VARCHAR(255)",
                "zip_code": "VARCHAR(32)",
                "country": "VARCHAR(255)",
                "region_id": "INTEGER",
                "region_confidence": "FLOAT",
                "website": "TEXT",
                "phone": "VARCHAR(255)",
                "email": "VARCHAR(255)",
                "instagram": "TEXT",
                "facebook": "TEXT",
                "x_url": "TEXT",
                "tiktok": "TEXT",
                "spotify_url": "TEXT",
                "main_image_url": "TEXT",
                "additional_image_urls": "TEXT",
                "description": "TEXT",
                "hours_of_operation": "TEXT",
                "certified": "BOOLEAN",
                "carousel_selection": "VARCHAR(255)",
                "business_status": "VARCHAR(255)",
                "rating": "FLOAT",
                "review_count_google": "INTEGER",
                "review_count_yelp": "INTEGER",
                "photo_quality_score": "FLOAT",
                "quality_control": "TEXT",
                "last_verified_at": "VARCHAR(255)",
                "raw_source_json": "TEXT NOT NULL DEFAULT '{}'",
                "publish_status": "VARCHAR(32) NOT NULL DEFAULT 'needs_review'",
                "publish_ready_score": "FLOAT",
                "publish_blockers_json": "TEXT NOT NULL DEFAULT '[]'",
                "published_at": "DATETIME",
                "unpublished_at": "DATETIME",
                "last_published_snapshot_json": "TEXT",
                "created_at": "DATETIME",
                "updated_at": "DATETIME",
            },
        )

        add_missing_columns(
            connection,
            "poi_candidates",
            {
                "source_type": "VARCHAR(64) NOT NULL DEFAULT 'unknown'",
                "source_provider": "VARCHAR(64)",
                "crawl_run_id": "INTEGER",
                "master_calendar_source_id": "INTEGER",
                "extracted_event_candidate_id": "INTEGER",
                "api_feed_run_id": "INTEGER",
                "api_feed_record_id": "INTEGER",
                "import_batch_id": "INTEGER",
                "source_url": "TEXT",
                "source_name": "VARCHAR(500)",
                "raw_fragment_json": "TEXT NOT NULL DEFAULT '{}'",
                "normalized_payload_json": "TEXT NOT NULL DEFAULT '{}'",
                "candidate_name": "VARCHAR(500) NOT NULL DEFAULT ''",
                "normalized_name": "VARCHAR(500) NOT NULL DEFAULT ''",
                "category": "VARCHAR(64)",
                "subcategory": "VARCHAR(128)",
                "suggested_category": "VARCHAR(64)",
                "suggested_subcategory": "VARCHAR(128)",
                "address": "TEXT",
                "city": "VARCHAR(255)",
                "state": "VARCHAR(255)",
                "zip_code": "VARCHAR(32)",
                "country": "VARCHAR(255)",
                "latitude": "FLOAT",
                "longitude": "FLOAT",
                "website": "TEXT",
                "phone": "VARCHAR(255)",
                "email": "VARCHAR(255)",
                "instagram": "TEXT",
                "facebook": "TEXT",
                "x_url": "TEXT",
                "tiktok": "TEXT",
                "youtube": "TEXT",
                "spotify_url": "TEXT",
                "main_image_url": "TEXT",
                "additional_image_urls_json": "TEXT NOT NULL DEFAULT '[]'",
                "description": "TEXT",
                "music_signal_score": "FLOAT NOT NULL DEFAULT 0.0",
                "poi_quality_score": "FLOAT NOT NULL DEFAULT 0.0",
                "poi_quality_flags_json": "TEXT NOT NULL DEFAULT '[]'",
                "dedupe_key": "TEXT NOT NULL DEFAULT ''",
                "match_status": "VARCHAR(64) NOT NULL DEFAULT 'unmatched'",
                "matched_poi_location_id": "INTEGER",
                "match_confidence": "VARCHAR(32) NOT NULL DEFAULT 'none'",
                "match_reason_json": "TEXT NOT NULL DEFAULT '{}'",
                "review_status": "VARCHAR(32) NOT NULL DEFAULT 'pending_review'",
                "rejection_reason": "TEXT",
                "created_poi_location_id": "INTEGER",
                "created_at": "DATETIME",
                "updated_at": "DATETIME",
            },
        )

        add_missing_columns(
            connection,
            "master_calendar_sources",
            {
                "canonical_url": "TEXT NOT NULL DEFAULT ''",
                "canonical_url_hash": "VARCHAR(64) NOT NULL DEFAULT ''",
                "original_url": "TEXT NOT NULL DEFAULT ''",
                "domain": "VARCHAR(255)",
                "source_name": "VARCHAR(255) NOT NULL DEFAULT ''",
                "source_type": "VARCHAR(64) NOT NULL DEFAULT 'unknown'",
                "expected_category": "VARCHAR(64) NOT NULL DEFAULT 'Concert'",
                "venue_name": "VARCHAR(255)",
                "city": "VARCHAR(255)",
                "state": "VARCHAR(255)",
                "country": "VARCHAR(255)",
                "region_or_market": "VARCHAR(255)",
                "region_id": "INTEGER",
                "region_confidence": "FLOAT",
                "status": "VARCHAR(32) NOT NULL DEFAULT 'pending'",
                "review_status": "VARCHAR(32) NOT NULL DEFAULT 'pending_review'",
                "risk_score": "INTEGER NOT NULL DEFAULT 0",
                "risk_level": "VARCHAR(32) NOT NULL DEFAULT 'low'",
                "risk_flags_json": "TEXT NOT NULL DEFAULT '[]'",
                "crawl_frequency": "VARCHAR(64)",
                "first_seen_at": "DATETIME",
                "last_seen_at": "DATETIME",
                "last_crawled_at": "DATETIME",
                "last_extractor_type": "VARCHAR(64)",
                "last_extraction_status": "VARCHAR(32)",
                "last_event_candidate_count": "INTEGER NOT NULL DEFAULT 0",
                "extraction_success_count": "INTEGER NOT NULL DEFAULT 0",
                "extraction_failure_count": "INTEGER NOT NULL DEFAULT 0",
                "unsupported_count": "INTEGER NOT NULL DEFAULT 0",
                "source_quality_flags_json": "TEXT NOT NULL DEFAULT '[]'",
                "source_trust_score": "FLOAT",
                "source_trust_grade": "VARCHAR(32)",
                "last_quality_score_id": "INTEGER",
                "notes": "TEXT",
                "created_at": "DATETIME",
                "updated_at": "DATETIME",
            },
        )
        relax_master_calendar_sources_legacy_columns(connection)

        add_missing_columns(
            connection,
            "import_batches",
            {
                "contact_name": "VARCHAR(255)",
                "original_filename": "VARCHAR(255)",
                "file_type": "VARCHAR(32)",
                "status": "VARCHAR(32) NOT NULL DEFAULT 'pending'",
                "review_status": "VARCHAR(32) NOT NULL DEFAULT 'pending_review'",
                "risk_score": "INTEGER NOT NULL DEFAULT 0",
                "risk_level": "VARCHAR(32) NOT NULL DEFAULT 'low'",
                "risk_flags_json": "TEXT NOT NULL DEFAULT '[]'",
                "submitted_at": "DATETIME",
                "notes": "TEXT",
                "error_summary": "TEXT",
                "valid_row_count": "INTEGER NOT NULL DEFAULT 0",
                "invalid_row_count": "INTEGER NOT NULL DEFAULT 0",
                "duplicate_row_count": "INTEGER NOT NULL DEFAULT 0",
                "events_created_count": "INTEGER NOT NULL DEFAULT 0",
                "events_updated_count": "INTEGER NOT NULL DEFAULT 0",
                "duplicate_candidate_count": "INTEGER NOT NULL DEFAULT 0",
                "source_claims_created_count": "INTEGER NOT NULL DEFAULT 0",
                "rows_rejected_count": "INTEGER NOT NULL DEFAULT 0",
                "rows_quarantined_count": "INTEGER NOT NULL DEFAULT 0",
                "reviewed_at": "DATETIME",
                "reviewed_by": "VARCHAR(255)",
                "review_notes": "TEXT",
            },
        )

        add_missing_columns(
            connection,
            "staged_events",
            {
                "row_number": "INTEGER NOT NULL DEFAULT 0",
                "validation_status": "VARCHAR(32) NOT NULL DEFAULT 'invalid'",
                "validation_errors": "TEXT NOT NULL DEFAULT '[]'",
                "risk_score": "INTEGER NOT NULL DEFAULT 0",
                "risk_level": "VARCHAR(32) NOT NULL DEFAULT 'low'",
                "risk_flags_json": "TEXT NOT NULL DEFAULT '[]'",
                "category": "VARCHAR(64) NOT NULL DEFAULT 'Concert'",
                "headliner": "VARCHAR(500)",
                "supporting_artists": "TEXT",
                "start_date": "VARCHAR(32)",
                "start_time": "VARCHAR(32)",
                "timezone": "VARCHAR(128)",
                "end_date": "VARCHAR(32)",
                "end_time": "VARCHAR(32)",
                "doors_time": "VARCHAR(32)",
                "venue_name": "VARCHAR(500)",
                "venue_address": "TEXT",
                "city": "VARCHAR(255)",
                "state": "VARCHAR(255)",
                "zip_code": "VARCHAR(32)",
                "country": "VARCHAR(255)",
                "latitude": "VARCHAR(64)",
                "longitude": "VARCHAR(64)",
                "event_url": "TEXT",
                "tickets_link": "TEXT",
                "description": "TEXT",
                "price": "VARCHAR(255)",
                "age_restriction": "VARCHAR(255)",
                "phone": "VARCHAR(255)",
                "email": "VARCHAR(255)",
                "website": "TEXT",
                "spotify_url": "TEXT",
                "youtube_url": "TEXT",
                "instagram": "TEXT",
                "facebook": "TEXT",
                "x_url": "TEXT",
                "tiktok": "TEXT",
                "main_image_url": "TEXT",
                "additional_image_urls": "TEXT",
                "source_event_id": "VARCHAR(500)",
                "notes": "TEXT",
                "updated_at": "DATETIME",
            },
        )

        add_missing_columns(
            connection,
            "staged_calendar_sources",
            {
                "row_number": "INTEGER NOT NULL DEFAULT 0",
                "validation_status": "VARCHAR(32) NOT NULL DEFAULT 'invalid'",
                "validation_errors": "TEXT NOT NULL DEFAULT '[]'",
                "risk_score": "INTEGER NOT NULL DEFAULT 0",
                "risk_level": "VARCHAR(32) NOT NULL DEFAULT 'low'",
                "risk_flags_json": "TEXT NOT NULL DEFAULT '[]'",
                "calendar_name": "VARCHAR(255)",
                "canonical_url": "TEXT",
                "canonical_url_hash": "VARCHAR(64)",
                "source_type": "VARCHAR(64)",
                "expected_category": "VARCHAR(64) NOT NULL DEFAULT 'Concert'",
                "venue_name": "VARCHAR(255)",
                "city": "VARCHAR(255)",
                "state": "VARCHAR(255)",
                "country": "VARCHAR(255)",
                "region_or_market": "VARCHAR(255)",
                "contact_name": "VARCHAR(255)",
                "crawl_frequency": "VARCHAR(64)",
                "authorization_confirmed": "BOOLEAN NOT NULL DEFAULT 0",
                "dedupe_status": "VARCHAR(64) NOT NULL DEFAULT 'new'",
                "existing_master_calendar_source_id": "INTEGER",
                "notes": "TEXT",
                "updated_at": "DATETIME",
            },
        )

        add_missing_columns(
            connection,
            "calendar_source_submissions",
            {
                "master_calendar_source_id": "INTEGER NOT NULL DEFAULT 0",
                "organization_name": "VARCHAR(255) NOT NULL DEFAULT ''",
                "contact_name": "VARCHAR(255)",
                "contact_email": "VARCHAR(255) NOT NULL DEFAULT ''",
                "original_url": "TEXT NOT NULL DEFAULT ''",
                "submitted_canonical_url": "TEXT NOT NULL DEFAULT ''",
                "submitted_at": "DATETIME",
                "authorization_confirmed": "BOOLEAN NOT NULL DEFAULT 0",
                "risk_score": "INTEGER NOT NULL DEFAULT 0",
                "risk_level": "VARCHAR(32) NOT NULL DEFAULT 'low'",
                "risk_flags_json": "TEXT NOT NULL DEFAULT '[]'",
                "review_status": "VARCHAR(32) NOT NULL DEFAULT 'pending_review'",
                "notes": "TEXT",
                "import_batch_id": "INTEGER",
                "raw_row_json": "TEXT",
                "created_at": "DATETIME",
                "updated_at": "DATETIME",
            },
        )

        connection.execute(
            text(
                "UPDATE calendar_sources "
                "SET review_status = 'approved' "
                "WHERE status = 'approved' "
                "AND review_status = 'pending_review' "
                "AND risk_score = 0"
            )
        )
        relax_background_jobs_job_type_constraint(connection)
        relax_scheduled_tasks_task_type_constraint(connection)


def relax_background_jobs_job_type_constraint(connection: Connection) -> None:
    """Allow newer local job types in older SQLite POC databases."""

    table_names = inspect(connection).get_table_names()
    if "background_jobs" not in table_names:
        return

    table_sql = connection.execute(
        text(
            "SELECT sql FROM sqlite_master "
            "WHERE type = 'table' AND name = 'background_jobs'"
        )
    ).scalar()
    if isinstance(table_sql, str) and "ticket_page_image_enrichment" in table_sql:
        return

    connection.execute(text("DROP TABLE IF EXISTS background_jobs_rebuilt"))
    connection.execute(
        text(
            """
            CREATE TABLE background_jobs_rebuilt (
                id INTEGER NOT NULL,
                job_type VARCHAR(64) NOT NULL,
                status VARCHAR(32) NOT NULL,
                priority INTEGER NOT NULL,
                queue_name VARCHAR(64) NOT NULL,
                payload_json TEXT NOT NULL,
                result_json TEXT,
                error_message TEXT,
                attempts INTEGER NOT NULL,
                max_attempts INTEGER NOT NULL,
                locked_at DATETIME,
                locked_by VARCHAR(255),
                started_at DATETIME,
                completed_at DATETIME,
                scheduled_for DATETIME,
                created_by VARCHAR(255),
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                PRIMARY KEY (id),
                CONSTRAINT ck_background_jobs_job_type CHECK (
                    job_type in (
                        'crawl_source',
                        'bulk_crawl',
                        'provider_sandbox_jambase',
                        'provider_sandbox_cityspark',
                        'image_preflight',
                        'event_photo_rescue',
                        'api_feed_run_photo_rescue',
                        'recent_events_photo_rescue',
                        'ticket_page_image_enrichment',
                        'api_feed_run_ticket_image_enrichment',
                        'recent_events_ticket_image_enrichment',
                        'extract_crawl_run',
                        'approve_extracted_event_candidate',
                        'process_extracted_event_batch',
                        'app_feed_export',
                        'poi_registry_import',
                        'scheduled_crawl_due_sources',
                        'source_quality_rollup',
                        'region_partner_report',
                        'all_source_quality_rollup',
                        'rebuild_app_search_index',
                        'app_map_feed_export',
                        'app_filter_options_export',
                        'poi_inventory_snapshot_export',
                        'source_registry_snapshot_export',
                        'poi_candidate_match',
                        'all_poi_candidate_match',
                        'poi_candidate_quality_rollup',
                        'rebuild_artist_registry',
                        'artist_genre_normalization',
                        'artist_image_rescue',
                        'itinerary_quality_rollup',
                        'itinerary_app_feed_export',
                        'build_artist_tour_itinerary',
                        'build_region_itinerary_suggestions',
                        'unknown'
                    )
                ),
                CONSTRAINT ck_background_jobs_status CHECK (
                    status in (
                        'pending',
                        'running',
                        'success',
                        'failure',
                        'cancelled',
                        'skipped'
                    )
                )
            )
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT INTO background_jobs_rebuilt (
                id,
                job_type,
                status,
                priority,
                queue_name,
                payload_json,
                result_json,
                error_message,
                attempts,
                max_attempts,
                locked_at,
                locked_by,
                started_at,
                completed_at,
                scheduled_for,
                created_by,
                created_at,
                updated_at
            )
            SELECT
                id,
                COALESCE(NULLIF(job_type, ''), 'unknown'),
                COALESCE(NULLIF(status, ''), 'pending'),
                COALESCE(priority, 100),
                COALESCE(NULLIF(queue_name, ''), 'default'),
                COALESCE(NULLIF(payload_json, ''), '{}'),
                result_json,
                error_message,
                COALESCE(attempts, 0),
                COALESCE(max_attempts, 3),
                locked_at,
                locked_by,
                started_at,
                completed_at,
                scheduled_for,
                created_by,
                COALESCE(created_at, CURRENT_TIMESTAMP),
                COALESCE(updated_at, CURRENT_TIMESTAMP)
            FROM background_jobs
            """
        )
    )
    connection.execute(text("DROP TABLE background_jobs"))
    connection.execute(
        text("ALTER TABLE background_jobs_rebuilt RENAME TO background_jobs")
    )
    for index_sql in (
        "CREATE INDEX IF NOT EXISTS ix_background_jobs_id "
        "ON background_jobs (id)",
        "CREATE INDEX IF NOT EXISTS ix_background_jobs_job_type "
        "ON background_jobs (job_type)",
        "CREATE INDEX IF NOT EXISTS ix_background_jobs_status "
        "ON background_jobs (status)",
        "CREATE INDEX IF NOT EXISTS ix_background_jobs_queue_name "
        "ON background_jobs (queue_name)",
        "CREATE INDEX IF NOT EXISTS ix_background_jobs_scheduled_for "
        "ON background_jobs (scheduled_for)",
    ):
        connection.execute(text(index_sql))


def relax_scheduled_tasks_task_type_constraint(connection: Connection) -> None:
    """Allow newer scheduler task families in older SQLite POC databases."""

    table_names = inspect(connection).get_table_names()
    if "scheduled_tasks" not in table_names:
        return

    table_sql = connection.execute(
        text(
            "SELECT sql FROM sqlite_master "
            "WHERE type = 'table' AND name = 'scheduled_tasks'"
        )
    ).scalar()
    if (
        isinstance(table_sql, str)
        and "monthly_source_registry_snapshot" in table_sql
    ):
        return

    connection.execute(text("DROP TABLE IF EXISTS scheduled_tasks_rebuilt"))
    connection.execute(
        text(
            """
            CREATE TABLE scheduled_tasks_rebuilt (
                id INTEGER NOT NULL,
                task_key VARCHAR(128) NOT NULL,
                task_type VARCHAR(64) NOT NULL,
                enabled BOOLEAN NOT NULL,
                schedule_type VARCHAR(32) NOT NULL,
                interval_minutes INTEGER,
                next_run_at DATETIME,
                last_run_at DATETIME,
                last_job_id INTEGER,
                payload_json TEXT NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                PRIMARY KEY (id),
                CONSTRAINT ck_scheduled_tasks_task_type CHECK (
                    task_type in (
                        'crawl_due_sources',
                        'app_feed_export',
                        'provider_sandbox',
                        'image_preflight',
                        'event_photo_rescue',
                        'source_quality_rollup',
                        'partner_report_export',
                        'rebuild_app_search_index',
                        'monthly_poi_inventory_snapshot',
                        'monthly_source_registry_snapshot',
                        'itinerary_app_feed_export'
                    )
                ),
                CONSTRAINT ck_scheduled_tasks_schedule_type CHECK (
                    schedule_type in (
                        'manual',
                        'interval',
                        'daily',
                        'weekly',
                        'biweekly',
                        'monthly'
                    )
                ),
                CONSTRAINT uq_scheduled_tasks_task_key UNIQUE (task_key),
                FOREIGN KEY(last_job_id) REFERENCES background_jobs (id)
            )
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT INTO scheduled_tasks_rebuilt (
                id,
                task_key,
                task_type,
                enabled,
                schedule_type,
                interval_minutes,
                next_run_at,
                last_run_at,
                last_job_id,
                payload_json,
                created_at,
                updated_at
            )
            SELECT
                id,
                COALESCE(NULLIF(task_key, ''), 'unknown_task_' || id),
                COALESCE(NULLIF(task_type, ''), 'app_feed_export'),
                COALESCE(enabled, 0),
                COALESCE(NULLIF(schedule_type, ''), 'manual'),
                interval_minutes,
                next_run_at,
                last_run_at,
                last_job_id,
                COALESCE(NULLIF(payload_json, ''), '{}'),
                COALESCE(created_at, CURRENT_TIMESTAMP),
                COALESCE(updated_at, CURRENT_TIMESTAMP)
            FROM scheduled_tasks
            """
        )
    )
    connection.execute(text("DROP TABLE scheduled_tasks"))
    connection.execute(
        text("ALTER TABLE scheduled_tasks_rebuilt RENAME TO scheduled_tasks")
    )
    for index_sql in (
        "CREATE INDEX IF NOT EXISTS ix_scheduled_tasks_id "
        "ON scheduled_tasks (id)",
        "CREATE INDEX IF NOT EXISTS ix_scheduled_tasks_task_key "
        "ON scheduled_tasks (task_key)",
        "CREATE INDEX IF NOT EXISTS ix_scheduled_tasks_task_type "
        "ON scheduled_tasks (task_type)",
        "CREATE INDEX IF NOT EXISTS ix_scheduled_tasks_next_run_at "
        "ON scheduled_tasks (next_run_at)",
    ):
        connection.execute(text(index_sql))


def relax_master_calendar_sources_legacy_columns(connection: Connection) -> None:
    """Remove stale local-only constraints from older master source tables."""

    table_names = inspect(connection).get_table_names()
    if "master_calendar_sources" not in table_names:
        return

    column_info = {
        str(row["name"]): row
        for row in connection.execute(
            text("PRAGMA table_info(master_calendar_sources)")
        ).mappings()
    }
    organization_column = column_info.get("organization_name")
    if organization_column is None or not organization_column.get("notnull"):
        return

    connection.execute(
        text("DROP TABLE IF EXISTS master_calendar_sources_rebuilt")
    )
    connection.execute(
        text(
            """
            CREATE TABLE master_calendar_sources_rebuilt (
                id INTEGER NOT NULL,
                canonical_url TEXT NOT NULL,
                canonical_url_hash VARCHAR(64) NOT NULL,
                original_url TEXT NOT NULL,
                domain VARCHAR(255),
                source_name VARCHAR(255) NOT NULL,
                source_type VARCHAR(64) NOT NULL DEFAULT 'unknown',
                expected_category VARCHAR(64) NOT NULL DEFAULT 'Concert',
                venue_name VARCHAR(255),
                city VARCHAR(255),
                state VARCHAR(255),
                country VARCHAR(255),
                region_or_market VARCHAR(255),
                region_id INTEGER,
                region_confidence FLOAT,
                status VARCHAR(32) NOT NULL DEFAULT 'pending',
                review_status VARCHAR(32) NOT NULL DEFAULT 'pending_review',
                risk_score INTEGER NOT NULL DEFAULT 0,
                risk_level VARCHAR(32) NOT NULL DEFAULT 'low',
                risk_flags_json TEXT NOT NULL DEFAULT '[]',
                crawl_frequency VARCHAR(64),
                first_seen_at DATETIME NOT NULL,
                last_seen_at DATETIME NOT NULL,
                last_crawled_at DATETIME,
                last_extractor_type VARCHAR(64),
                last_extraction_status VARCHAR(32),
                last_event_candidate_count INTEGER NOT NULL DEFAULT 0,
                extraction_success_count INTEGER NOT NULL DEFAULT 0,
                extraction_failure_count INTEGER NOT NULL DEFAULT 0,
                unsupported_count INTEGER NOT NULL DEFAULT 0,
                source_quality_flags_json TEXT NOT NULL DEFAULT '[]',
                source_trust_score FLOAT,
                source_trust_grade VARCHAR(32),
                last_quality_score_id INTEGER,
                notes TEXT,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                PRIMARY KEY (id)
            )
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT INTO master_calendar_sources_rebuilt (
                id,
                canonical_url,
                canonical_url_hash,
                original_url,
                domain,
                source_name,
                source_type,
                expected_category,
                venue_name,
                city,
                state,
                country,
                region_or_market,
                region_id,
                region_confidence,
                status,
                review_status,
                risk_score,
                risk_level,
                risk_flags_json,
                crawl_frequency,
                first_seen_at,
                last_seen_at,
                last_crawled_at,
                last_extractor_type,
                last_extraction_status,
                last_event_candidate_count,
                extraction_success_count,
                extraction_failure_count,
                unsupported_count,
                source_quality_flags_json,
                source_trust_score,
                source_trust_grade,
                last_quality_score_id,
                notes,
                created_at,
                updated_at
            )
            SELECT
                id,
                COALESCE(canonical_url, ''),
                COALESCE(canonical_url_hash, ''),
                COALESCE(original_url, canonical_url, ''),
                domain,
                COALESCE(
                    NULLIF(source_name, ''),
                    NULLIF(organization_name, ''),
                    NULLIF(original_url, ''),
                    NULLIF(canonical_url, ''),
                    'Unknown calendar'
                ),
                COALESCE(NULLIF(source_type, ''), 'unknown'),
                COALESCE(NULLIF(expected_category, ''), 'Concert'),
                venue_name,
                city,
                state,
                country,
                region_or_market,
                region_id,
                region_confidence,
                COALESCE(NULLIF(status, ''), 'pending'),
                COALESCE(NULLIF(review_status, ''), 'pending_review'),
                COALESCE(risk_score, 0),
                COALESCE(NULLIF(risk_level, ''), 'low'),
                COALESCE(NULLIF(risk_flags_json, ''), '[]'),
                crawl_frequency,
                COALESCE(first_seen_at, created_at, CURRENT_TIMESTAMP),
                COALESCE(last_seen_at, updated_at, created_at, CURRENT_TIMESTAMP),
                last_crawled_at,
                last_extractor_type,
                last_extraction_status,
                COALESCE(last_event_candidate_count, 0),
                COALESCE(extraction_success_count, 0),
                COALESCE(extraction_failure_count, 0),
                COALESCE(unsupported_count, 0),
                COALESCE(NULLIF(source_quality_flags_json, ''), '[]'),
                source_trust_score,
                source_trust_grade,
                last_quality_score_id,
                notes,
                COALESCE(created_at, first_seen_at, CURRENT_TIMESTAMP),
                COALESCE(updated_at, last_seen_at, created_at, CURRENT_TIMESTAMP)
            FROM master_calendar_sources
            """
        )
    )
    connection.execute(text("DROP TABLE master_calendar_sources"))
    connection.execute(
        text(
            "ALTER TABLE master_calendar_sources_rebuilt "
            "RENAME TO master_calendar_sources"
        )
    )
    connection.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS "
            "ix_master_calendar_sources_canonical_url_hash "
            "ON master_calendar_sources (canonical_url_hash)"
        )
    )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_master_calendar_sources_domain "
            "ON master_calendar_sources (domain)"
        )
    )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_master_calendar_sources_id "
            "ON master_calendar_sources (id)"
        )
    )


def add_missing_columns(
    connection: Connection,
    table_name: str,
    additions: dict[str, str],
) -> None:
    table_names = inspect(connection).get_table_names()
    if table_name not in table_names:
        return

    columns = {
        column["name"]
        for column in inspect(connection).get_columns(table_name)
    }
    for column_name, definition in additions.items():
        if column_name not in columns:
            connection.execute(
                text(
                    f"ALTER TABLE {table_name} "
                    f"ADD COLUMN {column_name} {definition}"
                )
            )


def relax_events_nullable_provenance(connection: Connection) -> None:
    """Allow file-upload events to omit crawl/source provenance in old SQLite DBs."""

    table_names = inspect(connection).get_table_names()
    if "events" not in table_names:
        return

    columns: dict[str, Any] = {}
    for column in inspect(connection).get_columns("events"):
        column_name = column.get("name")
        if isinstance(column_name, str):
            columns[column_name] = column

    source_nullable = columns.get("source_id", {}).get("nullable", True)
    crawl_nullable = columns.get("crawl_run_id", {}).get("nullable", True)
    if source_nullable is not True or crawl_nullable is not True:
        connection.execute(text("DROP INDEX IF EXISTS ix_events_source_id"))
        connection.execute(text("DROP INDEX IF EXISTS ix_events_id"))
        connection.execute(text("DROP INDEX IF EXISTS ix_events_crawl_run_id"))
        connection.execute(text("ALTER TABLE events RENAME TO events_old_nullable"))
        connection.execute(
            text(
                """
                CREATE TABLE events (
                    id INTEGER NOT NULL,
                    source_id INTEGER,
                    crawl_run_id INTEGER,
                    event_venue_id INTEGER,
                    region_id INTEGER,
                    region_confidence FLOAT,
                    import_batch_id INTEGER,
                    api_feed_run_id INTEGER,
                    api_feed_record_id INTEGER,
                    api_provider_key VARCHAR(64),
                    api_source_record_id VARCHAR(500),
                    api_mapping_warnings_json TEXT,
                    api_quality_scores_json TEXT,
                    provider_event_type VARCHAR(128),
                    provider_genre VARCHAR(255),
                    provider_subgenre VARCHAR(255),
                    music_category VARCHAR(255),
                    normalized_genre VARCHAR(255),
                    ticket_link_classification VARCHAR(64),
                    ticketing_provider VARCHAR(64),
                    ticketing_provider_domain VARCHAR(255),
                    ticket_link_repair_strategy VARCHAR(64),
                    ticket_link_repair_source VARCHAR(255),
                    ticket_link_repair_suggestion TEXT,
                    recommended_ticket_link TEXT,
                    ticket_link_quality_score FLOAT,
                    provider_doc_notes TEXT,
                    dedupe_source_fields_json TEXT,
                    venue_match_fields_json TEXT,
                    ingestion_provider VARCHAR(64),
                    upstream_event_source VARCHAR(64),
                    upstream_event_id VARCHAR(500),
                    provider_music_segment VARCHAR(255),
                    source_chain_json TEXT,
                    external_identifiers_json TEXT,
                    ticket_offers_json TEXT,
                    provenance_flags_json TEXT,
                    event_status VARCHAR(128),
                    has_time BOOLEAN,
                    all_day BOOLEAN,
                    category VARCHAR(64) NOT NULL DEFAULT 'Concert',
                    record_type VARCHAR(64) NOT NULL DEFAULT 'event',
                    source_type VARCHAR(64) NOT NULL DEFAULT 'ics',
                    title VARCHAR(500) NOT NULL,
                    headliner VARCHAR(500),
                    supporting_artists TEXT,
                    genre VARCHAR(255),
                    description TEXT,
                    start_datetime DATETIME NOT NULL,
                    end_datetime DATETIME,
                    timezone VARCHAR(128),
                    location_text TEXT,
                    source_url TEXT,
                    tickets_link TEXT,
                    price VARCHAR(255),
                    age_restriction VARCHAR(255),
                    doors_time VARCHAR(32),
                    main_image_url TEXT,
                    additional_image_urls TEXT,
                    selected_main_image_url TEXT,
                    selected_image_candidate_id INTEGER,
                    image_status VARCHAR(64),
                    image_quality_score FLOAT,
                    image_quality_flags_json TEXT NOT NULL DEFAULT '[]',
                    image_clearance_status VARCHAR(64),
                    image_source_type VARCHAR(64),
                    image_source_provider VARCHAR(255),
                    image_role VARCHAR(64),
                    image_selection_reason TEXT,
                    image_selected_at DATETIME,
                    spotify_url TEXT,
                    spotify_artist_id VARCHAR(255),
                    spotify_artist_name VARCHAR(500),
                    spotify_image_url TEXT,
                    spotify_match_confidence FLOAT,
                    spotify_preview_json TEXT,
                    enrichment_status VARCHAR(64),
                    enrichment_flags_json TEXT NOT NULL DEFAULT '[]',
                    enrichment_suggestions_json TEXT NOT NULL DEFAULT '{}',
                    source_event_id VARCHAR(500),
                    dedupe_confidence VARCHAR(32) NOT NULL DEFAULT 'strong',
                    duplicate_status VARCHAR(64) NOT NULL DEFAULT 'none',
                    duplicate_candidate_group_id INTEGER,
                    canonical_event_id INTEGER,
                    latest_source_claim_id INTEGER,
                    source_claim_count INTEGER NOT NULL DEFAULT 0,
                    first_seen_at DATETIME,
                    last_seen_at DATETIME,
                    last_significant_change_at DATETIME,
                    event_lifecycle_status VARCHAR(64) NOT NULL DEFAULT 'active',
                    last_update_summary_json TEXT NOT NULL DEFAULT '[]',
                    changed_fields_json TEXT NOT NULL DEFAULT '[]',
                    update_count INTEGER NOT NULL DEFAULT 0,
                    dedupe_key VARCHAR(64) NOT NULL,
                    raw_event_json TEXT NOT NULL,
                    publish_status VARCHAR(32) NOT NULL DEFAULT 'needs_review',
                    publish_ready_score FLOAT,
                    publish_blockers_json TEXT NOT NULL DEFAULT '[]',
                    published_at DATETIME,
                    unpublished_at DATETIME,
                    last_published_snapshot_json TEXT,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    PRIMARY KEY (id),
                    CONSTRAINT uq_events_crawl_run_dedupe_key
                    UNIQUE (crawl_run_id, dedupe_key),
                    FOREIGN KEY(source_id) REFERENCES calendar_sources (id),
                    FOREIGN KEY(crawl_run_id) REFERENCES crawl_runs (id),
                    FOREIGN KEY(event_venue_id) REFERENCES event_venues (id),
                    FOREIGN KEY(region_id) REFERENCES regions (id)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO events (
                    id,
                    source_id,
                    crawl_run_id,
                    event_venue_id,
                    region_id,
                    region_confidence,
                    import_batch_id,
                    api_feed_run_id,
                    api_feed_record_id,
                    api_provider_key,
                    api_source_record_id,
                    api_mapping_warnings_json,
                    api_quality_scores_json,
                    provider_event_type,
                    provider_genre,
                    provider_subgenre,
                    music_category,
                    normalized_genre,
                    ticket_link_classification,
                    ticketing_provider,
                    ticketing_provider_domain,
                    ticket_link_repair_strategy,
                    ticket_link_repair_source,
                    ticket_link_repair_suggestion,
                    recommended_ticket_link,
                    ticket_link_quality_score,
                    provider_doc_notes,
                    dedupe_source_fields_json,
                    venue_match_fields_json,
                    ingestion_provider,
                    upstream_event_source,
                    upstream_event_id,
                    provider_music_segment,
                    source_chain_json,
                    external_identifiers_json,
                    ticket_offers_json,
                    provenance_flags_json,
                    event_status,
                    has_time,
                    all_day,
                    category,
                    record_type,
                    source_type,
                    title,
                    headliner,
                    supporting_artists,
                    genre,
                    description,
                    start_datetime,
                    end_datetime,
                    timezone,
                    location_text,
                    source_url,
                    tickets_link,
                    price,
                    age_restriction,
                    doors_time,
                    main_image_url,
                    additional_image_urls,
                    selected_main_image_url,
                    selected_image_candidate_id,
                    image_status,
                    image_quality_score,
                    image_quality_flags_json,
                    image_clearance_status,
                    image_source_type,
                    image_source_provider,
                    image_role,
                    image_selection_reason,
                    image_selected_at,
                    spotify_url,
                    spotify_artist_id,
                    spotify_artist_name,
                    spotify_image_url,
                    spotify_match_confidence,
                    spotify_preview_json,
                    enrichment_status,
                    enrichment_flags_json,
                    enrichment_suggestions_json,
                    source_event_id,
                    dedupe_confidence,
                    duplicate_status,
                    duplicate_candidate_group_id,
                    canonical_event_id,
                    latest_source_claim_id,
                    source_claim_count,
                    first_seen_at,
                    last_seen_at,
                    last_significant_change_at,
                    event_lifecycle_status,
                    last_update_summary_json,
                    changed_fields_json,
                    update_count,
                    dedupe_key,
                    raw_event_json,
                    publish_status,
                    publish_ready_score,
                    publish_blockers_json,
                    published_at,
                    unpublished_at,
                    last_published_snapshot_json,
                    created_at,
                    updated_at
                )
                SELECT
                    id,
                    source_id,
                    crawl_run_id,
                    event_venue_id,
                    region_id,
                    region_confidence,
                    import_batch_id,
                    api_feed_run_id,
                    api_feed_record_id,
                    api_provider_key,
                    api_source_record_id,
                    api_mapping_warnings_json,
                    api_quality_scores_json,
                    provider_event_type,
                    provider_genre,
                    provider_subgenre,
                    music_category,
                    normalized_genre,
                    ticket_link_classification,
                    ticketing_provider,
                    ticketing_provider_domain,
                    ticket_link_repair_strategy,
                    ticket_link_repair_source,
                    ticket_link_repair_suggestion,
                    recommended_ticket_link,
                    ticket_link_quality_score,
                    provider_doc_notes,
                    dedupe_source_fields_json,
                    venue_match_fields_json,
                    ingestion_provider,
                    upstream_event_source,
                    upstream_event_id,
                    provider_music_segment,
                    source_chain_json,
                    external_identifiers_json,
                    ticket_offers_json,
                    provenance_flags_json,
                    event_status,
                    has_time,
                    all_day,
                    category,
                    record_type,
                    source_type,
                    title,
                    headliner,
                    supporting_artists,
                    genre,
                    description,
                    start_datetime,
                    end_datetime,
                    timezone,
                    location_text,
                    source_url,
                    tickets_link,
                    price,
                    age_restriction,
                    doors_time,
                    main_image_url,
                    additional_image_urls,
                    selected_main_image_url,
                    selected_image_candidate_id,
                    image_status,
                    image_quality_score,
                    image_quality_flags_json,
                    image_clearance_status,
                    image_source_type,
                    image_source_provider,
                    image_role,
                    image_selection_reason,
                    image_selected_at,
                    spotify_url,
                    spotify_artist_id,
                    spotify_artist_name,
                    spotify_image_url,
                    spotify_match_confidence,
                    spotify_preview_json,
                    enrichment_status,
                    enrichment_flags_json,
                    enrichment_suggestions_json,
                    source_event_id,
                    COALESCE(dedupe_confidence, 'strong'),
                    COALESCE(duplicate_status, 'none'),
                    duplicate_candidate_group_id,
                    canonical_event_id,
                    latest_source_claim_id,
                    COALESCE(source_claim_count, 0),
                    COALESCE(first_seen_at, created_at, CURRENT_TIMESTAMP),
                    COALESCE(last_seen_at, updated_at, created_at, CURRENT_TIMESTAMP),
                    last_significant_change_at,
                    COALESCE(event_lifecycle_status, 'active'),
                    COALESCE(last_update_summary_json, '[]'),
                    COALESCE(changed_fields_json, '[]'),
                    COALESCE(update_count, 0),
                    dedupe_key,
                    raw_event_json,
                    COALESCE(publish_status, 'needs_review'),
                    publish_ready_score,
                    COALESCE(publish_blockers_json, '[]'),
                    published_at,
                    unpublished_at,
                    last_published_snapshot_json,
                    created_at,
                    updated_at
                FROM events_old_nullable
                """
            )
        )
        connection.execute(text("DROP TABLE events_old_nullable"))
        connection.execute(
            text("CREATE INDEX ix_events_source_id ON events (source_id)")
        )
        connection.execute(text("CREATE INDEX ix_events_id ON events (id)"))
        connection.execute(
            text("CREATE INDEX ix_events_crawl_run_id ON events (crawl_run_id)")
        )
        connection.execute(
            text("CREATE INDEX ix_events_event_venue_id ON events (event_venue_id)")
        )
        connection.execute(
            text("CREATE INDEX ix_events_region_id ON events (region_id)")
        )
