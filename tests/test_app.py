import csv
import json
import re
import sqlite3
from datetime import datetime, timedelta
from io import BytesIO, StringIO
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import select, text

from app.core.config import DEV_ADMIN_PASSWORD_HASH, Settings
from app.db.models import (
    AdminAuditLog,
    ApiFeedRecord,
    ApiFeedRun,
    AppDiscoverySlot,
    AppFeedExport,
    AppSearchIndex,
    ArtistSourceClaim,
    BackgroundJob,
    BlockedSubmitter,
    CalendarSource,
    CalendarSourceSubmission,
    CanonicalArtist,
    DestinationPartner,
    Event,
    EventArtist,
    EventDuplicateGroup,
    EventDuplicateGroupMember,
    EventSourceClaim,
    EventVenue,
    ImageCandidate,
    ImportBatch,
    Itinerary,
    MasterCalendarSource,
    PartnerReport,
    PoiCandidate,
    PoiLocation,
    RegionQualitySnapshot,
    ScheduledTask,
    SearchSeedLocation,
    SourceExtractedEventCandidate,
    SourceQualityScore,
    StagedCalendarSource,
    StagedEvent,
    SubmissionAttempt,
    TrustedSubmitter,
    utc_now,
)
from app.main import create_app
from app.services.api_feed_service import (
    cityspark_mapper,
    extract_json_records,
    jambase_mapper,
    provider_registry,
)
from app.services.app_search_service import (
    rebuild_search_index,
    search_app_index,
    suggest_app_search,
)
from app.services.artist_service import (
    ArtistClaimInput,
    build_artist_key,
    extract_artists_from_api_payload,
    link_event_to_artists,
    match_existing_artist,
    normalize_artist_name,
    upsert_artist_from_claim,
)
from app.services.background_job_service import (
    cancel_job,
    claim_next_job,
    enqueue_due_scheduled_tasks,
    enqueue_job,
    enqueue_scheduled_task_now,
    list_scheduled_tasks,
    mark_job_failure,
    mark_job_success,
    process_next_job,
    redact_sensitive_payload,
    retry_job,
)
from app.services.bulk_crawl_service import (
    CRAWL_FREQUENCIES,
    as_utc_datetime,
    is_due_for_crawl,
    next_crawl_due_at,
    normalize_crawl_frequency,
)
from app.services.crawl_service import FetchResult, get_crawl_run
from app.services.event_photo_rescue_service import (
    provider_image_inputs_from_raw,
    run_event_photo_rescue,
)
from app.services.event_quality_service import (
    compute_event_quality_score,
    event_quality_dashboard_counts,
    event_quality_workbench,
)
from app.services.event_service import (
    count_events_for_crawl_run,
    save_ics_events_for_crawl_run,
)
from app.services.file_risk_service import (
    score_calendar_source_rows,
    score_concert_event_rows,
)
from app.services.genre_service import (
    normalize_event_music_fields,
    normalize_genre_value,
)
from app.services.ics_service import parse_ics_events
from app.services.image_qa_service import (
    ImageCandidateInput,
    create_image_candidate,
    extract_text_from_image_candidate,
    is_likely_direct_image_asset,
    mark_candidate_preflight_result,
    select_best_event_image,
    select_candidate_for_event,
    set_candidate_clearance,
    update_candidate_review,
)
from app.services.import_service import CALENDAR_SOURCE_HEADERS, CONCERT_EVENT_HEADERS
from app.services.itinerary_service import (
    ItineraryCreate,
    ItineraryStopInput,
    add_stop,
    build_external_navigation_link,
    build_itinerary_app_feed,
    compute_itinerary_quality,
    create_itinerary,
    list_app_itineraries,
    move_stop,
    remove_stop,
)
from app.services.map_display_service import (
    build_filter_options,
    build_map_marker,
    list_discovery_slots,
    list_map_markers,
)
from app.services.master_calendar_service import canonicalize_calendar_url
from app.services.partner_report_service import (
    export_partner_report_csv,
    export_partner_report_json,
    generate_region_partner_report,
    generate_source_quality_report,
)
from app.services.poi_candidate_service import (
    approve_candidate_create_poi,
    approve_candidate_update_existing_poi,
    link_candidate_to_existing_poi,
    mark_candidate_event_venue_only,
    normalize_poi_candidate,
    reject_poi_candidate,
)
from app.services.provider_http_client import ProviderHttpResult
from app.services.region_service import (
    compute_region_quality_snapshot,
    create_or_update_region,
    infer_region_for_event,
    infer_region_for_poi,
    normalize_region_key,
    seed_search_locations_from_pois,
    seed_search_locations_from_regions,
)
from app.services.security_service import (
    neutralize_csv_formula,
    url_safety_flags,
)
from app.services.security_service import (
    redact_sensitive_payload as redact_security_payload,
)
from app.services.source_extraction_service import extract_source_content
from app.services.source_quality_service import (
    compute_source_quality_for_api_provider,
    compute_source_quality_for_master_source,
    compute_source_quality_for_partner,
    compute_source_quality_for_region,
    grade_score,
)
from app.services.source_taxonomy_service import (
    detect_source_key,
    provider_key_for_value,
)
from app.services.ticket_link_service import classify_ticket_link
from app.services.ticketmaster_classification_service import (
    map_ticketmaster_classification,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"
SAMPLE_ICS = (FIXTURE_DIR / "sample_calendar.ics").read_text(encoding="utf-8")
SAMPLE_JSONLD_HTML = (FIXTURE_DIR / "sample_event_jsonld.html").read_text(
    encoding="utf-8"
)
SAMPLE_RSS = (FIXTURE_DIR / "sample_events.rss").read_text(encoding="utf-8")
SAMPLE_HTML_EVENTS = (FIXTURE_DIR / "sample_event_cards.html").read_text(
    encoding="utf-8"
)
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def json_fixture(filename: str) -> object:
    return json.loads((FIXTURE_DIR / filename).read_text(encoding="utf-8"))


class FakeProviderHttpClient:
    def __init__(self, responses: list[ProviderHttpResult]) -> None:
        self.responses = responses
        self.get_calls: list[dict[str, object]] = []
        self.post_calls: list[dict[str, object]] = []

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
        secrets: tuple[str, ...] = (),
    ) -> ProviderHttpResult:
        self.get_calls.append(
            {"url": url, "params": params or {}, "headers": headers or {}}
        )
        return self.responses.pop(0)

    def post_json(
        self,
        url: str,
        *,
        json_body: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
        secrets: tuple[str, ...] = (),
    ) -> ProviderHttpResult:
        self.post_calls.append(
            {"url": url, "body": json_body or {}, "headers": headers or {}}
        )
        return self.responses.pop(0)


def make_client(tmp_path, environment: str = "development") -> TestClient:
    database_url = f"sqlite:///{tmp_path / 'test.db'}"
    app = create_app(
        Settings(
            database_url=database_url,
            environment=environment,
            admin_password_hash=DEV_ADMIN_PASSWORD_HASH,
            session_secret_key="test-session-secret",
        )
    )
    base_url = "https://testserver" if environment == "production" else "http://testserver"
    return TestClient(app, base_url=base_url)


def make_client_with_settings(tmp_path, **overrides: object) -> TestClient:
    database_url = f"sqlite:///{tmp_path / 'test.db'}"
    settings_values: dict[str, object] = {
        "database_url": database_url,
        "admin_password_hash": DEV_ADMIN_PASSWORD_HASH,
        "session_secret_key": "test-session-secret",
    }
    settings_values.update(overrides)
    return TestClient(create_app(Settings(**settings_values)))


def make_client_with_public_app_feed(tmp_path) -> TestClient:
    tmp_path.mkdir(parents=True, exist_ok=True)
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'test.db'}",
            admin_password_hash=DEV_ADMIN_PASSWORD_HASH,
            session_secret_key="test-session-secret",
            app_feed_public=True,
        )
    )
    return TestClient(app)


def submit_source(
    client: TestClient,
    organization_name: str = "Test Venue",
    calendar_url: str = "https://example.com/events",
) -> None:
    response = client.post(
        "/submit-calendar",
        data={
            "organization_name": organization_name,
            "calendar_url": calendar_url,
            "contact_email": "owner@example.com",
            "permission_confirmed": "true",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


def login_admin(
    client: TestClient,
    username: str = "admin",
    password: str = "admin",
) -> None:
    response = client.post(
        "/admin/login",
        data={
            "username": username,
            "password": password,
            "next": "/admin/sources",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


def csrf_token(client: TestClient) -> str:
    response = client.get("/admin/sources")
    assert response.status_code == 200
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
    assert match is not None
    return match.group(1)


def admin_get(client: TestClient, path: str) -> object:
    login_admin(client)
    return client.get(path)


def admin_post(
    client: TestClient,
    path: str,
    data: dict[str, str] | None = None,
    follow_redirects: bool = False,
) -> object:
    login_admin(client)
    payload = dict(data or {})
    payload["csrf_token"] = csrf_token(client)
    return client.post(path, data=payload, follow_redirects=follow_redirects)


def approve_source(client: TestClient, source_id: int = 1) -> None:
    response = admin_post(
        client,
        f"/admin/sources/{source_id}/status",
        data={"status": "approved"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def approve_master_source(client: TestClient, source_id: int = 1) -> None:
    response = admin_post(
        client,
        f"/admin/master-calendar-sources/{source_id}/status",
        data={"action": "approve"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def admin_post_with_source_ids(
    client: TestClient,
    path: str,
    source_ids: list[int],
    follow_redirects: bool = False,
) -> object:
    login_admin(client)
    token = csrf_token(client)
    data = {
        "csrf_token": token,
        "source_ids": [str(source_id) for source_id in source_ids],
    }
    return client.post(path, data=data, follow_redirects=follow_redirects)


def admin_post_upload_json(
    client: TestClient,
    path: str,
    content: bytes,
    filename: str = "events.json",
    follow_redirects: bool = False,
) -> object:
    login_admin(client)
    token = csrf_token(client)
    return client.post(
        path,
        data={"csrf_token": token},
        files={"upload_file": (filename, content, "application/json")},
        follow_redirects=follow_redirects,
    )


def get_source(client: TestClient, source_id: int = 1) -> CalendarSource:
    with client.app.state.SessionLocal() as session:
        source = session.get(CalendarSource, source_id)
        assert source is not None
        return source


def add_test_poi_location(
    session,
    *,
    name: str = "River Hall",
    category: str = "Music Site",
    subcategory: str | None = "Venues",
    latitude: float | None = 35.1495,
    longitude: float | None = -90.049,
    address: str | None = "1 Music Way",
    city: str | None = "Memphis",
    state: str | None = "TN",
    website: str | None = "https://venue.example",
    publish_status: str = "approved",
) -> PoiLocation:
    normalized = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
    dedupe_key = f"{normalized}|{latitude:.5f}|{longitude:.5f}" if latitude else name
    poi = PoiLocation(
        canonical_poi_id=f"poi-{abs(hash((name, city, state))) % 1000000}",
        poi_dedupe_key=dedupe_key,
        poi_dedupe_confidence="strong",
        source_type="test_fixture",
        source_record_id=f"test:{name}",
        display_name=name,
        normalized_name=normalized,
        category=category,
        subcategory=subcategory,
        latitude=latitude,
        longitude=longitude,
        address=address,
        city=city,
        state=state,
        zip_code="38103",
        country="US",
        website=website,
        publish_status=publish_status,
    )
    session.add(poi)
    session.commit()
    session.refresh(poi)
    return poi


def add_test_poi_candidate(session, **overrides: object) -> PoiCandidate:
    values: dict[str, object] = {
        "source_type": "manual_admin",
        "source_provider": "unknown",
        "source_url": "https://source.example/new-room",
        "candidate_name": "New Room",
        "city": "Memphis",
        "state": "TN",
        "country": "US",
        "latitude": 35.151,
        "longitude": -90.051,
        "website": "https://newroom.example",
        "main_image_url": "https://images.example/new-room.jpg",
        "description": "Music venue candidate for audit.",
    }
    values.update(overrides)
    candidate = PoiCandidate(**values)
    normalize_poi_candidate(candidate, session)
    session.add(candidate)
    session.commit()
    session.refresh(candidate)
    return candidate


def csv_upload(headers: list[str], rows: list[dict[str, str]]) -> bytes:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=headers)
    writer.writeheader()
    for row in rows:
        writer.writerow({header: row.get(header, "") for header in headers})
    return output.getvalue().encode("utf-8")


def xlsx_upload(headers: list[str], rows: list[dict[str, str]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers)
    for row in rows:
        sheet.append([row.get(header, "") for header in headers])
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def valid_concert_row(**overrides: str) -> dict[str, str]:
    row = {header: "" for header in CONCERT_EVENT_HEADERS}
    row.update(
        {
            "Category": "Concert",
            "Event Name": "River Stage Night",
            "Headliner": "The Test Band",
            "Start Date": "2026-08-01",
            "Start Time": "20:00",
            "Timezone": "America/Chicago",
            "Venue Name": "River Stage",
            "Venue Address": "1 Music Way",
            "City": "Memphis",
            "State": "TN",
            "Zip Code": "38103",
            "Country": "US",
            "Event URL": "https://venue.example/events/river-stage-night",
            "Main Image URL": "https://venue.example/images/show.jpg",
        }
    )
    row.update(overrides)
    return row


def valid_calendar_source_row(**overrides: str) -> dict[str, str]:
    row = {header: "" for header in CALENDAR_SOURCE_HEADERS}
    row.update(
        {
            "Organization Name": "Venue Calendar",
            "Calendar Name": "Venue Events",
            "Calendar URL": "https://venue.example/events/",
            "Source Type": "venue_calendar",
            "Expected Category": "Concert",
            "Venue Name": "Venue",
            "City": "Memphis",
            "State": "TN",
            "Country": "US",
            "Region / Market": "Memphis",
            "Contact Name": "Calendar Owner",
            "Contact Email": "owner@venue.example",
            "Crawl Frequency": "weekly",
            "Authorization Confirmed": "yes",
            "Notes": "Client submitted.",
        }
    )
    row.update(overrides)
    return row


def upload_concert_events(
    client: TestClient,
    content: bytes,
    filename: str = "concert-events.csv",
) -> TestClient:
    response = client.post(
        "/submit-events/file",
        data={
            "organization_name": "Upload Org",
            "contact_name": "Uploader",
            "contact_email": "upload@example.com",
        },
        files={
            "upload_file": (
                filename,
                content,
                (
                    "text/csv"
                    if filename.endswith(".csv")
                    else XLSX_MIME
                ),
            )
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    return client


def upload_calendar_sources(
    client: TestClient,
    content: bytes,
    filename: str = "calendar-sources.csv",
) -> TestClient:
    response = client.post(
        "/submit-calendar/sources-file",
        data={
            "organization_name": "Source Upload Org",
            "contact_name": "Uploader",
            "contact_email": "sources@example.com",
        },
        files={
            "upload_file": (
                filename,
                content,
                (
                    "text/csv"
                    if filename.endswith(".csv")
                    else XLSX_MIME
                ),
            )
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    return client


def approve_concert_upload(client: TestClient, rows: list[dict[str, str]]) -> None:
    upload_concert_events(client, csv_upload(CONCERT_EVENT_HEADERS, rows))
    response = admin_post(
        client,
        "/admin/import-batches/1/approve-valid-rows",
        follow_redirects=True,
    )
    assert response.status_code == 200


def create_preview_event(
    client: TestClient,
    *,
    title: str = "Direct Preview Event",
    main_image_url: str | None = None,
    tickets_link: str | None = "https://tickets.example/direct",
    source_url: str | None = "https://venue.example/direct",
    venue_key: str = "direct-preview-venue",
    venue_name: str = "Direct Preview Venue",
    venue_category: str = "Music Site",
    venue_subcategory: str = "Venues",
    latitude: float | None = 35.1495,
    longitude: float | None = -90.049,
) -> int:
    with client.app.state.SessionLocal() as session:
        venue = EventVenue(
            venue_key=venue_key,
            display_name=venue_name,
            address="10 Preview Ave",
            city="Memphis",
            state="TN",
            zip_code="38103",
            country="US",
            latitude=latitude,
            longitude=longitude,
            main_image_url="https://venue.example/images/venue.jpg",
            description="Local preview venue.",
            category=venue_category,
            subcategory=venue_subcategory,
        )
        session.add(venue)
        session.flush()
        event = Event(
            event_venue_id=venue.id,
            category="Concert",
            record_type="event",
            source_type="file_upload",
            title=title,
            headliner=title,
            start_datetime=datetime.fromisoformat("2026-08-01T20:00:00"),
            location_text=venue.display_name,
            source_url=source_url,
            tickets_link=tickets_link,
            main_image_url=main_image_url,
            dedupe_key=f"direct:{title}",
            raw_event_json="{}",
        )
        session.add(event)
        session.commit()
        return event.id


def seed_region_fixture(client: TestClient) -> int:
    with client.app.state.SessionLocal() as session:
        region = create_or_update_region(
            session,
            name="Memphis Music Region",
            region_type="certified_music_region",
            city="Memphis",
            state="TN",
            country="US",
            latitude=35.1495,
            longitude=-90.049,
            radius_miles=35,
            certified=True,
            launch_status="qa",
        )
        venue = EventVenue(
            venue_key="region-test-venue",
            display_name="Region Test Venue",
            city="Memphis",
            state="TN",
            country="US",
            latitude=35.1495,
            longitude=-90.049,
        )
        session.add(venue)
        session.flush()
        event = Event(
            event_venue_id=venue.id,
            region_id=region.id,
            region_confidence=0.95,
            category="Concert",
            record_type="event",
            source_type="file_upload",
            title="Region Fixture Concert",
            headliner="Region Fixture Artist",
            start_datetime=datetime.fromisoformat("2026-08-01T20:00:00"),
            source_url="https://events.example/region-fixture",
            tickets_link="https://tickets.example/region-fixture",
            ticket_link_classification="direct",
            publish_status="approved",
            dedupe_key="region-fixture-concert",
            raw_event_json="{}",
        )
        poi = PoiLocation(
            canonical_poi_id="poi-region-fixture",
            poi_dedupe_key="poi-region-fixture",
            source_type="mapotic_export",
            source_record_id="poi-region-fixture",
            display_name="Region Fixture Venue POI",
            normalized_name="region fixture venue poi",
            category="Music Site",
            subcategory="Venues",
            latitude=35.1495,
            longitude=-90.049,
            city="Memphis",
            state="TN",
            country="US",
            region_id=region.id,
            region_confidence=0.95,
            publish_status="approved",
        )
        source = MasterCalendarSource(
            canonical_url="https://region.example/events",
            canonical_url_hash="region-source-hash",
            original_url="https://region.example/events",
            domain="region.example",
            source_name="Region Fixture Source",
            city="Memphis",
            state="TN",
            country="US",
            status="approved",
            review_status="approved",
            region_id=region.id,
            region_confidence=0.95,
            last_extraction_status="failure",
            extraction_failure_count=1,
        )
        session.add_all([event, poi, source])
        session.commit()
        return region.id


def seed_app_search_contract_records(client: TestClient) -> dict[str, int]:
    region_id = seed_region_fixture(client)
    with client.app.state.SessionLocal() as session:
        certified_poi = PoiLocation(
            canonical_poi_id="certified-boost-studio",
            poi_dedupe_key="poi:certified-boost-studio",
            source_type="poi_registry",
            source_record_id="certified-boost-studio",
            display_name="Boost Studio Certified",
            normalized_name="boost studio certified",
            category="Music Site",
            subcategory="Recording Studios",
            latitude=35.16,
            longitude=-90.06,
            city="Memphis",
            state="TN",
            country="US",
            region_id=region_id,
            website="https://boost.example/certified",
            main_image_url="https://images.example/boost-certified.jpg",
            certified=True,
            publish_status="approved",
        )
        plain_poi = PoiLocation(
            canonical_poi_id="plain-boost-studio",
            poi_dedupe_key="poi:plain-boost-studio",
            source_type="poi_registry",
            source_record_id="plain-boost-studio",
            display_name="Boost Studio Plain",
            normalized_name="boost studio plain",
            category="Music Site",
            subcategory="Recording Studios",
            latitude=35.17,
            longitude=-90.07,
            city="Memphis",
            state="TN",
            country="US",
            region_id=region_id,
            website="https://boost.example/plain",
            main_image_url="https://images.example/boost-plain.jpg",
            certified=False,
            publish_status="approved",
        )
        seed = SearchSeedLocation(
            seed_key="manual:memphis-airport",
            display_name="Memphis International Airport",
            normalized_name="memphis international airport",
            seed_type="airport",
            source_type="manual",
            source_record_id="mem-airport",
            region_id=region_id,
            latitude=35.0424,
            longitude=-89.9767,
            city="Memphis",
            state="TN",
            country="US",
            priority=15,
            search_weight=3.5,
            popularity_score=20,
            use_for_internal_search=True,
            use_for_app_search=True,
        )
        venue = session.scalars(select(EventVenue)).first()
        assert venue is not None
        rejected_event = Event(
            event_venue_id=venue.id,
            region_id=region_id,
            category="Concert",
            record_type="event",
            source_type="file_upload",
            title="Rejected Search Secret",
            headliner="Rejected Artist",
            start_datetime=datetime.fromisoformat("2026-08-03T20:00:00"),
            tickets_link="https://tickets.example/rejected-search",
            publish_status="rejected",
            dedupe_key="rejected-search-secret",
            raw_event_json='{"secret":"SEARCH_SECRET_SHOULD_NOT_LEAK"}',
        )
        session.add_all([certified_poi, plain_poi, seed, rejected_event])
        session.commit()
        return {
            "region_id": region_id,
            "certified_poi_id": certified_poi.id,
            "plain_poi_id": plain_poi.id,
            "search_seed_id": seed.id,
            "rejected_event_id": rejected_event.id,
        }


def seed_itinerary_contract_records(client: TestClient) -> dict[str, int]:
    ids = seed_app_search_contract_records(client)
    with client.app.state.SessionLocal() as session:
        event = session.scalars(
            select(Event).where(Event.title == "Region Fixture Concert"),
        ).one()
        artist = CanonicalArtist(
            artist_key="fixture-roadtrip-artist",
            display_name="Fixture Roadtrip Artist",
            normalized_name="fixture roadtrip artist",
            artist_type="band",
            primary_genre="Blues",
            normalized_genres_json='["Blues"]',
            image_url="https://images.example/fixture-artist.jpg",
            image_status="accepted",
        )
        session.add(artist)
        session.flush()
        session.add(
            EventArtist(
                event_id=event.id,
                artist_id=artist.id,
                role="headliner",
                performance_rank=1,
            ),
        )
        session.commit()

        itinerary = create_itinerary(
            session,
            ItineraryCreate(
                title="Memphis Road Trip Contract",
                itinerary_type="road_trip",
                subtitle="Route through fixture music data",
                description="A sanitized app itinerary contract fixture.",
                status="approved",
                region_id=ids["region_id"],
                hero_image_url="https://images.example/route-hero.jpg",
                normalized_genres=["Blues"],
                tags=["qa", "road-trip"],
            ),
        )
        event_stop = add_stop(
            session,
            itinerary.id,
            ItineraryStopInput(stop_type="event", event_id=event.id),
        )
        poi_stop = add_stop(
            session,
            itinerary.id,
            ItineraryStopInput(
                stop_type="poi",
                poi_location_id=ids["certified_poi_id"],
            ),
        )
        artist_stop = add_stop(
            session,
            itinerary.id,
            ItineraryStopInput(stop_type="artist_context", artist_id=artist.id),
        )
        compute_itinerary_quality(session, itinerary.id)
        return {
            **ids,
            "itinerary_id": itinerary.id,
            "event_id": event.id,
            "artist_id": artist.id,
            "event_stop_id": event_stop.id,
            "poi_stop_id": poi_stop.id,
            "artist_stop_id": artist_stop.id,
        }


def seed_source_quality_fixture(client: TestClient) -> dict[str, int]:
    with client.app.state.SessionLocal() as session:
        region = create_or_update_region(
            session,
            name="Trust Score Region",
            region_type="certified_music_region",
            city="Memphis",
            state="TN",
            country="US",
            certified=True,
            launch_status="qa",
        )
        partner = DestinationPartner(
            name="Trust Tourism Board",
            partner_type="tourism_board",
            contact_email="partner@example.com",
            region_id=region.id,
            status="active",
        )
        venue = EventVenue(
            venue_key="trust-venue",
            display_name="Trust Venue",
            city="Memphis",
            state="TN",
            country="US",
            latitude=35.1495,
            longitude=-90.049,
        )
        good_source = MasterCalendarSource(
            canonical_url="https://trust.example/good",
            canonical_url_hash="trust-good",
            original_url="https://trust.example/good",
            domain="trust.example",
            source_name="Trusted Calendar",
            city="Memphis",
            state="TN",
            country="US",
            status="approved",
            review_status="approved",
            region_id=region.id,
            extraction_success_count=1,
            last_crawled_at=utc_now(),
        )
        weak_source = MasterCalendarSource(
            canonical_url="https://trust.example/weak",
            canonical_url_hash="trust-weak",
            original_url="https://trust.example/weak",
            domain="trust.example",
            source_name="Weak Calendar",
            city="Memphis",
            state="TN",
            country="US",
            status="approved",
            review_status="approved",
            region_id=region.id,
            extraction_failure_count=1,
            unsupported_count=1,
            last_extraction_status="failure",
            last_crawled_at=utc_now(),
        )
        session.add_all([partner, venue, good_source, weak_source])
        session.flush()
        good_event = Event(
            event_venue_id=venue.id,
            region_id=region.id,
            api_provider_key="jambase",
            ingestion_provider="jambase",
            category="Concert",
            record_type="event",
            source_type="api_feed",
            title="Trusted Concert",
            headliner="Trusted Concert",
            start_datetime=datetime.fromisoformat("2026-09-01T20:00:00"),
            source_url="https://trust.example/good/event",
            tickets_link="https://tickets.example/trusted",
            ticket_link_classification="direct",
            selected_main_image_url="https://images.example/trusted.jpg",
            image_status="accepted",
            image_clearance_status="approved",
            dedupe_key="trust-good-event",
            duplicate_status="none",
            publish_status="approved",
            source_claim_count=2,
            raw_event_json="{}",
        )
        weak_event = Event(
            region_id=region.id,
            category="Concert",
            record_type="event",
            source_type="file_upload",
            title="Weak Concert",
            start_datetime=datetime.fromisoformat("2026-09-02T20:00:00"),
            ticket_link_classification="platform_generic_or_app",
            dedupe_key="trust-weak-event",
            duplicate_status="duplicate_candidate",
            duplicate_candidate_group_id=44,
            publish_status="needs_review",
            publish_blockers_json='["missing_ticket", "missing_image"]',
            update_count=2,
            raw_event_json="{}",
        )
        session.add_all([good_event, weak_event])
        session.flush()
        claims = [
            EventSourceClaim(
                event_id=good_event.id,
                source_type="calendar",
                master_calendar_source_id=good_source.id,
                source_name=good_source.source_name,
                claim_dedupe_key="claim-good-1",
            ),
            EventSourceClaim(
                event_id=good_event.id,
                source_type="api_feed",
                ingestion_provider="jambase",
                provider_record_id="jambase-good",
                claim_dedupe_key="claim-good-2",
            ),
            EventSourceClaim(
                event_id=weak_event.id,
                source_type="calendar",
                master_calendar_source_id=weak_source.id,
                source_name=weak_source.source_name,
                claim_dedupe_key="claim-weak-1",
            ),
        ]
        image_candidate = ImageCandidate(
            event_id=weak_event.id,
            source_type="api_feed",
            source_provider="provider",
            image_url="https://images.example/generic.jpg",
            image_role="event_provider",
            is_direct_image_asset=True,
            is_social_media_url=False,
            appears_stock_or_placeholder=True,
            generic_detection_score=95,
            qa_flags_json='["generic_provider_image"]',
        )
        api_run = ApiFeedRun(
            provider_key="jambase",
            provider_type="licensed_vendor",
            run_mode="manual_json",
            status="success",
            raw_record_count=1,
            normalized_candidate_count=1,
            approved_count=1,
        )
        api_record = ApiFeedRecord(
            api_feed_run_id=0,
            provider_key="jambase",
            provider_type="licensed_vendor",
            provider_record_id="jambase-good",
            normalized_payload_json="{}",
            review_status="approved",
            event_name="Trusted Concert",
            start_datetime=datetime.fromisoformat("2026-09-01T20:00:00"),
            tickets_link="https://tickets.example/trusted",
            main_image_url="https://images.example/trusted.jpg",
            dedupe_key="jambase-good",
            created_event_id=good_event.id,
        )
        session.add_all(claims + [image_candidate, api_run])
        session.flush()
        api_record.api_feed_run_id = api_run.id
        session.add(api_record)
        session.commit()
        return {
            "region_id": region.id,
            "partner_id": partner.id,
            "good_source_id": good_source.id,
            "weak_source_id": weak_source.id,
            "good_event_id": good_event.id,
            "weak_event_id": weak_event.id,
        }


def seed_app_feed_records(client: TestClient) -> None:
    client.get("/health")
    with client.app.state.SessionLocal() as session:
        venue = EventVenue(
            venue_key="river-stage",
            display_name="River Stage",
            address="1 Music Way",
            city="Memphis",
            state="TN",
            zip_code="38103",
            country="US",
            latitude=35.1495,
            longitude=-90.049,
            website="https://venue.example",
            main_image_url="https://venue.example/images/venue.jpg",
        )
        session.add(venue)
        session.flush()
        approved_event = Event(
            event_venue_id=venue.id,
            api_provider_key="jambase",
            ingestion_provider="jambase",
            category="Concert",
            record_type="event",
            source_type="api_feed",
            title="River Stage Night",
            headliner="The Test Band",
            supporting_artists="Opener One, Opener Two",
            genre="Rock",
            provider_genre="rock",
            music_category="Rock",
            start_datetime=datetime.fromisoformat("2026-08-01T20:00:00"),
            end_datetime=datetime.fromisoformat("2026-08-01T23:00:00"),
            timezone="America/Chicago",
            location_text=venue.display_name,
            source_url="https://venue.example/events/river-stage-night",
            tickets_link="https://tickets.example/river-stage-night",
            ticket_link_classification="primary",
            ticketing_provider="venue",
            selected_main_image_url="https://images.example/river.jpg",
            image_status="selected_pending_approval",
            image_clearance_status="needs_approval",
            image_quality_score=82.0,
            image_quality_flags_json='["pending_clearance"]',
            dedupe_key="app-feed:river-stage-night",
            dedupe_confidence="strong",
            duplicate_status="none",
            source_claim_count=1,
            publish_status="approved",
            raw_event_json='{"raw_provider_json":"SECRET_API_KEY_SHOULD_NOT_LEAK"}',
        )
        rejected_event = Event(
            event_venue_id=venue.id,
            category="Concert",
            record_type="event",
            source_type="file_upload",
            title="Rejected Show",
            start_datetime=datetime.fromisoformat("2026-08-02T20:00:00"),
            dedupe_key="app-feed:rejected",
            publish_status="rejected",
            raw_event_json="{}",
        )
        duplicate_event = Event(
            event_venue_id=venue.id,
            category="Concert",
            record_type="event",
            source_type="file_upload",
            title="Duplicate Candidate Show",
            start_datetime=datetime.fromisoformat("2026-08-03T20:00:00"),
            dedupe_key="app-feed:duplicate",
            duplicate_status="duplicate_candidate",
            publish_status="approved",
            raw_event_json="{}",
        )
        cancelled_event = Event(
            event_venue_id=venue.id,
            category="Concert",
            record_type="event",
            source_type="file_upload",
            title="Cancelled Show",
            start_datetime=datetime.fromisoformat("2026-08-04T20:00:00"),
            dedupe_key="app-feed:cancelled",
            event_lifecycle_status="cancelled",
            publish_status="approved",
            raw_event_json="{}",
        )
        missing_venue_event = Event(
            category="Concert",
            record_type="event",
            source_type="file_upload",
            title="No Venue Yet",
            start_datetime=datetime.fromisoformat("2026-08-05T20:00:00"),
            tickets_link="https://tickets.example/no-venue",
            dedupe_key="app-feed:no-venue",
            publish_status="approved",
            raw_event_json="{}",
        )
        session.add_all(
            [
                approved_event,
                rejected_event,
                duplicate_event,
                cancelled_event,
                missing_venue_event,
            ],
        )
        session.flush()
        session.add(
            EventSourceClaim(
                event_id=approved_event.id,
                source_type="api_feed",
                ingestion_provider="jambase",
                source_url="https://provider.example/secret",
                raw_payload_json='{"token":"SECRET_SOURCE_CLAIM"}',
                normalized_payload_json="{}",
                claim_dedupe_key="claim:river-stage-night",
            ),
        )
        session.add_all(
            [
                PoiLocation(
                    canonical_poi_id="record-shop",
                    poi_dedupe_key="poi:record-shop",
                    display_name="River Records",
                    normalized_name="river records",
                    category="Shopping",
                    subcategory="Record Stores",
                    latitude=35.14,
                    longitude=-90.05,
                    address="10 Vinyl Ave",
                    city="Memphis",
                    state="TN",
                    zip_code="03810",
                    country="US",
                    website="https://records.example",
                    main_image_url="https://records.example/photo.jpg",
                    publish_status="approved",
                    raw_source_json='{"secret":"RAW_POI_SECRET"}',
                ),
                PoiLocation(
                    canonical_poi_id="concert-place",
                    poi_dedupe_key="poi:concert-place",
                    display_name="Concert Row",
                    normalized_name="concert row",
                    category="Concert",
                    latitude=35.1,
                    longitude=-90.1,
                    publish_status="approved",
                    raw_source_json="{}",
                ),
                PoiLocation(
                    canonical_poi_id="logo-place",
                    poi_dedupe_key="poi:logo-place",
                    display_name="Logo Museum",
                    normalized_name="logo museum",
                    category="Cultural",
                    subcategory="Museums",
                    latitude=35.2,
                    longitude=-90.2,
                    main_image_url="/static/images/music-roadtrip-logo-circle.png",
                    publish_status="approved",
                    raw_source_json="{}",
                ),
            ],
        )
        session.commit()


def create_image_candidate_for_test(
    client: TestClient,
    *,
    event_id: int | None = None,
    venue_id: int | None = None,
    image_url: str = "https://images.example/live-photo.jpg",
    source_type: str = "provider",
    source_provider: str | None = "test_provider",
    image_role: str = "event_provider",
    clearance_status: str = "unknown",
    candidate_status: str = "pending_review",
    width: int | None = 1600,
    height: int | None = 900,
    content_type: str | None = "image/jpeg",
    rescue_source: str = "unknown",
    source_payload_path: str | None = None,
    source_evidence_only: bool = False,
    can_be_final_image: bool = True,
) -> int:
    with client.app.state.SessionLocal() as session:
        candidate = create_image_candidate(
            session,
            ImageCandidateInput(
                event_id=event_id,
                venue_id=venue_id,
                image_url=image_url,
                source_type=source_type,
                source_provider=source_provider,
                image_role=image_role,
                clearance_status=clearance_status,
                candidate_status=candidate_status,
                width=width,
                height=height,
                content_type=content_type,
                rescue_source=rescue_source,
                source_payload_path=source_payload_path,
                source_evidence_only=source_evidence_only,
                can_be_final_image=can_be_final_image,
            ),
        )
        return candidate.id


def seed_event_quality_records(client: TestClient) -> dict[str, int]:
    with client.app.state.SessionLocal() as session:
        venue = EventVenue(
            venue_key="event-quality-venue",
            display_name="Event Quality Venue",
            address="100 Quality Ave",
            city="Memphis",
            state="TN",
            country="US",
            latitude=35.15,
            longitude=-90.04,
        )
        session.add(venue)
        session.flush()

        ready_event = Event(
            event_venue_id=venue.id,
            category="Concert",
            record_type="event",
            source_type="api_feed",
            ingestion_provider="jambase",
            title="Ready Quality Concert",
            headliner="Ready Quality Artist",
            genre="Rock",
            normalized_genre="Rock",
            music_relevance_score=92,
            start_datetime=datetime.fromisoformat("2026-09-01T20:00:00"),
            source_url="https://events.example/ready-quality",
            tickets_link="https://tickets.example/ready-quality",
            ticket_link_classification="direct",
            ticket_link_quality_score=96,
            selected_main_image_url="https://images.example/ready-quality.jpg",
            image_status="accepted",
            image_clearance_status="approved",
            image_role="artist_live",
            image_selection_reason="manual_approved",
            dedupe_key="event-quality-ready",
            dedupe_confidence="strong",
            duplicate_status="none",
            source_claim_count=2,
            publish_status="approved",
            raw_event_json="{}",
        )
        missing_event = Event(
            event_venue_id=venue.id,
            category="Concert",
            record_type="event",
            source_type="calendar",
            title="Missing Quality Assets",
            headliner="Missing Quality Artist",
            genre="Blues",
            normalized_genre="Blues",
            music_relevance_score=78,
            start_datetime=datetime.fromisoformat("2026-09-02T20:00:00"),
            dedupe_key="event-quality-missing",
            dedupe_confidence="strong",
            duplicate_status="none",
            source_claim_count=1,
            publish_status="needs_review",
            raw_event_json="{}",
        )
        duplicate_event = Event(
            category="Concert",
            record_type="event",
            source_type="api_feed",
            ingestion_provider="cityspark",
            title="Duplicate Risk Concert",
            start_datetime=datetime.fromisoformat("2026-09-03T20:00:00"),
            tickets_link="https://tickets.example",
            ticket_link_classification="platform_generic_or_app",
            ticket_link_quality_score=25,
            selected_main_image_url="https://images.example/generic-provider.jpg",
            image_status="blocked",
            image_clearance_status="rejected",
            image_role="stock_placeholder",
            music_relevance_score=20,
            dedupe_key="event-quality-duplicate",
            dedupe_confidence="weak",
            duplicate_status="duplicate_candidate",
            source_claim_count=1,
            publish_status="needs_review",
            raw_event_json="{}",
        )
        pending_image_event = Event(
            event_venue_id=venue.id,
            category="Concert",
            record_type="event",
            source_type="api_feed",
            ingestion_provider="jambase",
            title="Pending Image Concert",
            headliner="Pending Image Artist",
            genre="Soul",
            normalized_genre="Soul",
            music_relevance_score=84,
            start_datetime=datetime.fromisoformat("2026-09-04T20:00:00"),
            tickets_link="https://tickets.example/pending-image",
            ticket_link_classification="direct",
            selected_main_image_url="https://images.example/social-card.jpg",
            image_status="selected_pending_approval",
            image_clearance_status="needs_approval",
            dedupe_key="event-quality-pending-image",
            duplicate_status="none",
            source_claim_count=1,
            publish_status="approved",
            raw_event_json="{}",
        )
        non_concert_row = Event(
            event_venue_id=venue.id,
            category="Music Site",
            record_type="poi",
            source_type="file_upload",
            title="Not A Concert Row",
            start_datetime=datetime.fromisoformat("2026-09-05T20:00:00"),
            dedupe_key="event-quality-non-concert",
            raw_event_json="{}",
        )
        session.add_all(
            [
                ready_event,
                missing_event,
                duplicate_event,
                pending_image_event,
                non_concert_row,
            ]
        )
        session.flush()

        duplicate_group = EventDuplicateGroup(
            group_key="event-quality-duplicate-group",
            status="open",
            confidence="weak",
            reason_json='["event_quality_fixture"]',
        )
        session.add(duplicate_group)
        session.flush()
        duplicate_event.duplicate_candidate_group_id = duplicate_group.id
        session.add(
            EventDuplicateGroupMember(
                group_id=duplicate_group.id,
                event_id=duplicate_event.id,
                role="duplicate_candidate",
                match_score=0.42,
                reason_json='["event_quality_fixture"]',
            )
        )

        for index, event in enumerate([ready_event, missing_event, duplicate_event]):
            session.add(
                EventSourceClaim(
                    event_id=event.id,
                    source_type=event.source_type,
                    ingestion_provider=event.ingestion_provider,
                    provider_record_id=f"event-quality-{index}",
                    claim_dedupe_key=f"event-quality-claim-{index}",
                )
            )
        session.add(
            EventSourceClaim(
                event_id=ready_event.id,
                source_type="calendar",
                source_name="Partner Calendar",
                claim_dedupe_key="event-quality-claim-ready-calendar",
            )
        )

        duplicate_candidate = create_image_candidate(
            session,
            ImageCandidateInput(
                event_id=duplicate_event.id,
                image_url="https://images.example/generic-provider.jpg",
                image_role="stock_placeholder",
                clearance_status="rejected",
                candidate_status="rejected",
                generic_detection_score=95,
                rescue_source="provider_promo_image",
                can_be_final_image=False,
            ),
        )
        pending_candidate = create_image_candidate(
            session,
            ImageCandidateInput(
                event_id=pending_image_event.id,
                image_url="https://images.example/social-card.jpg",
                image_role="social_screenshot",
                clearance_status="needs_approval",
                candidate_status="needs_approval",
                rescue_source="social_graphic_reference",
                source_evidence_only=True,
                can_be_final_image=False,
            ),
        )
        duplicate_event.selected_image_candidate_id = duplicate_candidate.id
        pending_image_event.selected_image_candidate_id = pending_candidate.id
        session.commit()
        return {
            "ready": ready_event.id,
            "missing": missing_event.id,
            "duplicate": duplicate_event.id,
            "pending_image": pending_image_event.id,
            "non_concert": non_concert_row.id,
        }


def venue_id_for_event(client: TestClient, event_id: int) -> int:
    with client.app.state.SessionLocal() as session:
        event = session.get(Event, event_id)
        assert event is not None
        assert event.event_venue_id is not None
        return event.event_venue_id


def venue_filter_drawer_html(response_text: str) -> str:
    start = response_text.index('data-testid="venue-filter-drawer"')
    end = response_text.index("</section>", start)
    return response_text[start:end]


def test_homepage_and_health(tmp_path):
    with make_client(tmp_path) as client:
        assert client.get("/health").json() == {"status": "ok"}

        response = client.get("/")

    assert response.status_code == 200
    assert "Music Roadtrip Calendar Ingest" in response.text
    assert "Send authorized calendar links or event spreadsheets" in response.text
    assert "Submit Calendar" in response.text
    assert "/submit-calendar" in response.text
    assert "Submit Events" in response.text
    assert "/submit-events" in response.text
    assert "Team Login" in response.text
    assert 'href="/admin/login"' in response.text
    assert "Team members can log in to access the private review dashboard." in (
        response.text
    )
    assert "View admin sources" not in response.text
    assert "Submit Concerts" not in response.text


def test_static_logo_assets_are_served(tmp_path):
    with make_client(tmp_path) as client:
        square = client.get("/static/images/music-roadtrip-logo-square.png")
        circle = client.get("/static/images/music-roadtrip-logo-circle.png")

    assert square.status_code == 200
    assert circle.status_code == 200
    assert square.headers["content-type"] == "image/png"
    assert circle.headers["content-type"] == "image/png"


def test_admin_login_loads_publicly(tmp_path):
    with make_client(tmp_path) as client:
        response = client.get("/admin/login")

    assert response.status_code == 200
    assert "Admin Login" in response.text
    assert "Username" in response.text
    assert "Private internal tool" in response.text
    assert "color-scheme: dark" in response.text
    assert "login-card" in response.text
    assert "brand-logo--login" in response.text
    assert "/static/images/music-roadtrip-logo-circle.png" in response.text
    assert 'alt="Music Roadtrip logo"' in response.text
    assert '<aside class="admin-sidebar"' not in response.text


def test_admin_login_succeeds_with_valid_credentials(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post(
            "/admin/login",
            data={
                "username": "admin",
                "password": "admin",
                "next": "/admin/sources",
            },
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/sources"


def test_admin_login_defaults_to_dashboard_without_existing_csrf(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post(
            "/admin/login",
            data={"username": "admin", "password": "admin"},
            follow_redirects=False,
        )
        dashboard = client.get("/admin/dashboard")

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/dashboard"
    assert dashboard.status_code == 200
    assert "Admin Dashboard" in dashboard.text


def test_admin_login_fails_with_invalid_credentials(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post(
            "/admin/login",
            data={
                "username": "admin",
                "password": "wrong",
            },
        )

    assert response.status_code == 401
    assert "Invalid admin username or password." in response.text


def test_admin_pages_redirect_to_login_when_unauthenticated(tmp_path):
    protected_paths = [
        "/admin/dashboard",
        "/admin/sources",
        "/admin/master-calendar-sources",
        "/admin/import-batches",
        "/admin/suspicious-submissions",
    ]
    with make_client(tmp_path) as client:
        responses = [
            client.get(path, follow_redirects=False) for path in protected_paths
        ]

    assert all(response.status_code == 303 for response in responses)
    assert all(
        response.headers["location"].startswith("/admin/login")
        for response in responses
    )


def test_authenticated_admin_can_access_admin_pages(tmp_path):
    protected_paths = [
        "/admin/dashboard",
        "/admin/sources",
        "/admin/master-calendar-sources",
        "/admin/import-batches",
        "/admin/suspicious-submissions",
    ]
    with make_client(tmp_path) as client:
        login_admin(client)
        responses = [client.get(path) for path in protected_paths]

    assert all(response.status_code == 200 for response in responses)
    assert "Signed in as admin" in responses[0].text
    assert "admin-sidebar" in responses[0].text
    assert "brand-logo--sidebar" in responses[0].text
    assert "/static/images/music-roadtrip-logo-circle.png" in responses[0].text
    assert "color-scheme: dark" in responses[0].text
    assert "Intake" in responses[0].text
    assert "Future / App Team" in responses[0].text
    assert "Deferred Itineraries" in responses[0].text
    assert "Road Trips / Tours" not in responses[0].text


def test_event_quality_workbench_requires_login_and_renders_buckets(tmp_path):
    with make_client(tmp_path) as client:
        seed_event_quality_records(client)

        unauthenticated = client.get(
            "/admin/event-quality",
            follow_redirects=False,
        )
        assert unauthenticated.status_code == 303
        assert unauthenticated.headers["location"].startswith("/admin/login")

        login_admin(client)
        response = client.get("/admin/event-quality")

    assert response.status_code == 200
    assert "Event Quality Workbench" in response.text
    assert "Missing image" in response.text
    assert "Missing ticket link" in response.text
    assert "Duplicate candidate" in response.text
    assert "Low music relevance" in response.text
    assert "Ready Quality Concert" in response.text
    assert "Duplicate Risk Concert" in response.text
    assert "Not A Concert Row" not in response.text
    assert "/admin/app-feed/events.json?event_id=" in response.text


def test_event_quality_buckets_scores_and_dashboard_counts(tmp_path):
    with make_client(tmp_path) as client:
        ids = seed_event_quality_records(client)
        with client.app.state.SessionLocal() as session:
            workbench = event_quality_workbench(session)
            bucket_counts = {bucket.key: bucket.count for bucket in workbench.buckets}
            ready_event = session.get(Event, ids["ready"])
            duplicate_event = session.get(Event, ids["duplicate"])
            assert ready_event is not None
            assert duplicate_event is not None

            assert bucket_counts["missing_image"] == 1
            assert bucket_counts["missing_ticket_link"] == 1
            assert bucket_counts["duplicate_candidate"] == 1
            assert bucket_counts["low_music_relevance"] == 1
            assert bucket_counts["selected_image_pending_approval"] == 1
            assert bucket_counts["social_graphic_evidence_only"] == 1
            assert compute_event_quality_score(ready_event) > 90
            assert compute_event_quality_score(duplicate_event) < 55

            counts = event_quality_dashboard_counts(session)
            assert counts.missing_image_count == 1
            assert counts.missing_ticket_count == 1
            assert counts.duplicate_risk_count == 1
            assert counts.app_feed_ready_count == 1
            assert counts.not_app_feed_ready_count == 3
            assert all(row.event.category == "Concert" for row in workbench.rows)
            assert all(row.event.record_type == "event" for row in workbench.rows)


def test_event_quality_filters_and_bulk_actions_require_csrf(tmp_path):
    with make_client(tmp_path) as client:
        ids = seed_event_quality_records(client)
        login_admin(client)

        missing_bucket = client.get("/admin/event-quality?bucket=missing_image")
        assert missing_bucket.status_code == 200
        assert "Missing Quality Assets" in missing_bucket.text
        assert "Ready Quality Concert" not in missing_bucket.text

        no_csrf = client.post(
            "/admin/event-quality/bulk-action",
            data={"action": "photo_rescue", "event_ids": str(ids["missing"])},
            follow_redirects=False,
        )
        assert no_csrf.status_code == 403

        token = csrf_token(client)
        rescue = client.post(
            "/admin/event-quality/bulk-action",
            data={
                "csrf_token": token,
                "action": "photo_rescue",
                "event_ids": str(ids["missing"]),
            },
            follow_redirects=False,
        )
        assert rescue.status_code == 303
        assert rescue.headers["location"].startswith("/admin/event-quality")

        token = csrf_token(client)
        mark_review = client.post(
            "/admin/event-quality/bulk-action",
            data={
                "csrf_token": token,
                "action": "needs_image_review",
                "event_ids": str(ids["ready"]),
            },
            follow_redirects=False,
        )
        assert mark_review.status_code == 303
        with client.app.state.SessionLocal() as session:
            event = session.get(Event, ids["ready"])
            assert event is not None
            assert event.image_status == "needs_review"


def test_event_quality_dashboard_cards_render(tmp_path):
    with make_client(tmp_path) as client:
        seed_event_quality_records(client)
        response = admin_get(client, "/admin/dashboard")

    assert response.status_code == 200
    assert "Events needing photos" in response.text
    assert "Events needing tickets" in response.text
    assert "Events with duplicate risk" in response.text
    assert "Events not app-feed ready" in response.text
    assert "Events ready for app feed" in response.text
    assert "/admin/event-quality" in response.text


def test_event_quality_service_has_no_live_calls_or_keys() -> None:
    service_text = Path("app/services/event_quality_service.py").read_text()
    lowered = service_text.lower()
    assert "httpx" not in lowered
    assert "requests" not in lowered
    assert "urllib.request" not in lowered
    assert "api_key" not in lowered
    assert "client_secret" not in lowered


def test_unauthenticated_admin_post_action_is_rejected(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post(
            "/admin/sources/1/status",
            data={"status": "approved"},
            follow_redirects=False,
        )

    assert response.status_code == 401


def test_authenticated_admin_post_requires_valid_csrf_token(tmp_path):
    with make_client(tmp_path) as client:
        submit_source(client)
        login_admin(client)
        missing = client.post(
            "/admin/sources/1/status",
            data={"status": "approved"},
            follow_redirects=False,
        )
        invalid = client.post(
            "/admin/sources/1/status",
            data={"status": "approved", "csrf_token": "not-the-token"},
            follow_redirects=False,
        )

    assert missing.status_code == 403
    assert invalid.status_code == 403


def test_logout_clears_admin_session(tmp_path):
    with make_client(tmp_path) as client:
        login_admin(client)
        token = csrf_token(client)
        logout = client.post(
            "/admin/logout",
            data={"csrf_token": token},
            follow_redirects=False,
        )
        protected = client.get("/admin/sources", follow_redirects=False)

    assert logout.status_code == 303
    assert logout.headers["location"] == "/admin/login"
    assert protected.status_code == 303


def test_submit_events_and_templates_remain_public(tmp_path):
    with make_client(tmp_path) as client:
        submit_response = client.get("/submit-events")
        template_response = client.get("/templates/concert-events-template.csv")
        alias_template_response = client.get("/templates/events-template.csv")

    assert submit_response.status_code == 200
    assert "Submit Events" in submit_response.text
    assert "brand-logo--hero" in submit_response.text
    assert "/static/images/music-roadtrip-logo-square.png" in submit_response.text
    assert '<aside class="admin-sidebar"' not in submit_response.text
    assert "Signed in as" not in submit_response.text
    assert template_response.status_code == 200
    assert b"Category,Event Name,Headliner" in template_response.content
    assert alias_template_response.status_code == 200
    assert b"Category,Event Name,Headliner" in alias_template_response.content


def test_dev_sample_calendar_only_available_in_development(tmp_path):
    with make_client(tmp_path, environment="development") as client:
        development_response = client.get("/dev/sample-calendar.ics")
    with make_client(tmp_path, environment="production") as client:
        production_response = client.get("/dev/sample-calendar.ics")

    assert development_response.status_code == 200
    assert "BEGIN:VCALENDAR" in development_response.text
    assert production_response.status_code == 404


def test_submit_calendar_requires_permission(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post(
            "/submit-calendar",
            data={
                "organization_name": "Test Venue",
                "calendar_url": "https://example.com/events",
                "contact_email": "owner@example.com",
            },
        )

    assert response.status_code == 400
    assert "Authorization confirmation is required." in response.text


def test_submit_calendar_uses_public_shell_without_admin_sidebar(tmp_path):
    with make_client(tmp_path) as client:
        response = client.get("/submit-calendar")

    assert response.status_code == 200
    assert "Submit Calendar" in response.text
    assert "brand-logo--header" in response.text
    assert "/static/images/music-roadtrip-logo-circle.png" in response.text
    assert '<aside class="admin-sidebar"' not in response.text
    assert "Signed in as" not in response.text
    assert "Send one calendar link" in response.text
    assert "Upload a list of calendar links" in response.text
    assert "Which option should I choose?" in response.text
    assert "What happens next?" in response.text
    assert "/submit-calendar/url" in response.text
    assert "/submit-calendar/sources-file" in response.text
    assert 'name="calendar_url"' not in response.text


def test_submit_calendar_appears_in_admin(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post(
            "/submit-calendar",
            data={
                "organization_name": "Test Venue",
                "calendar_url": "https://example.com/events",
                "contact_email": "owner@example.com",
                "permission_confirmed": "true",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert "Thank you" in response.text
        assert "Music Roadtrip will review the calendar or file." in response.text

        admin_response = admin_get(client, "/admin/sources")

    assert admin_response.status_code == 200
    assert "Test Venue" in admin_response.text
    assert "https://example.com/events" in admin_response.text
    assert "Pending" in admin_response.text


def test_admin_can_approve_and_pause_source(tmp_path):
    with make_client(tmp_path) as client:
        client.post(
            "/submit-calendar",
            data={
                "organization_name": "Approval Test",
                "calendar_url": "https://venue.example/calendar",
                "contact_email": "calendar@venue.example",
                "permission_confirmed": "true",
            },
        )

        approved = admin_post(
            client,
            "/admin/sources/1/status",
            data={"status": "approved"},
            follow_redirects=True,
        )
        assert approved.status_code == 200
        assert 'value="approved" selected' in approved.text

        paused = admin_post(
            client,
            "/admin/sources/1/status",
            data={"status": "paused"},
            follow_redirects=True,
        )

    assert paused.status_code == 200
    assert 'value="paused" selected' in paused.text


def test_approved_source_can_be_crawled(tmp_path):
    with make_client(tmp_path) as client:
        submit_source(client, calendar_url="https://example.com/approved-calendar")
        approve_source(client)
        client.app.state.fetch_calendar_url = lambda url: FetchResult(
            http_status_code=200,
            content_type="text/calendar",
            raw_response_body="BEGIN:VCALENDAR\nEND:VCALENDAR",
        )

        sources_response = admin_get(client, "/admin/sources")
        assert "Run Crawl" in sources_response.text

        crawl_response = admin_post(
            client,
            "/admin/sources/1/crawl",
            follow_redirects=True,
        )

    assert crawl_response.status_code == 200
    assert "Crawl Run #1" in crawl_response.text
    assert "success" in crawl_response.text


def test_pending_source_cannot_be_crawled(tmp_path):
    called = False

    def fetcher(url: str) -> FetchResult:
        nonlocal called
        called = True
        return FetchResult(
            http_status_code=200,
            content_type="text/calendar",
            raw_response_body="BEGIN:VCALENDAR\nEND:VCALENDAR",
        )

    with make_client(tmp_path) as client:
        submit_source(client, calendar_url="https://example.com/pending-calendar")
        client.app.state.fetch_calendar_url = fetcher

        sources_response = admin_get(client, "/admin/sources")
        assert "Run Crawl" not in sources_response.text
        assert "Review and approve to crawl" in sources_response.text

        crawl_response = admin_post(client, "/admin/sources/1/crawl")
        history_response = admin_get(client, "/admin/crawl-runs")

    assert crawl_response.status_code == 400
    assert "Only approved sources can be crawled." in crawl_response.text
    assert called is False
    assert "No crawl runs yet." in history_response.text


def test_failed_fetch_creates_failed_crawl_run(tmp_path):
    def fetcher(url: str) -> FetchResult:
        return FetchResult(
            http_status_code=None,
            content_type=None,
            raw_response_body=None,
            error_message="Connection timed out.",
        )

    with make_client(tmp_path) as client:
        submit_source(client, calendar_url="https://example.com/failing-calendar")
        approve_source(client)
        client.app.state.fetch_calendar_url = fetcher

        detail_response = admin_post(
            client,
            "/admin/sources/1/crawl",
            follow_redirects=True,
        )
        history_response = admin_get(client, "/admin/crawl-runs")

    assert detail_response.status_code == 200
    assert "failure" in detail_response.text
    assert "Connection timed out." in detail_response.text
    assert "No raw response body was stored for this run." in detail_response.text
    assert "failing-calendar" in history_response.text


def test_successful_fetch_creates_successful_crawl_run(tmp_path):
    raw_body = "<html><title>Venue Events</title><p>One fetched page.</p></html>"

    def fetcher(url: str) -> FetchResult:
        return FetchResult(
            http_status_code=200,
            content_type="text/html; charset=utf-8",
            raw_response_body=raw_body,
        )

    with make_client(tmp_path) as client:
        submit_source(
            client,
            organization_name="Success Venue",
            calendar_url="https://example.com/success-calendar",
        )
        approve_source(client)
        client.app.state.fetch_calendar_url = fetcher

        detail_response = admin_post(
            client,
            "/admin/sources/1/crawl",
            follow_redirects=True,
        )
        history_response = admin_get(client, "/admin/crawl-runs")

    assert detail_response.status_code == 200
    assert "Success Venue" in detail_response.text
    assert "https://example.com/success-calendar" in detail_response.text
    assert "success" in detail_response.text
    assert "200" in detail_response.text
    assert "text/html; charset=utf-8" in detail_response.text
    assert "One fetched page." in detail_response.text
    assert "#1" in history_response.text
    assert "success-calendar" in history_response.text


def test_parse_normal_timed_ics_event():
    events = parse_ics_events(SAMPLE_ICS)
    event = next(
        item for item in events if item.source_event_id == "timed-001@example.test"
    )

    assert event.title == "Friday Night Showcase"
    assert event.description == "Local bands on the main stage."
    assert event.start_datetime.isoformat().startswith("2026-07-10T20:00:00")
    assert event.end_datetime is not None
    assert event.end_datetime.isoformat().startswith("2026-07-10T22:30:00")
    assert event.timezone == "America/Chicago"
    assert event.location_text == "Riverfront Music Hall"


def test_parse_all_day_ics_event():
    events = parse_ics_events(SAMPLE_ICS)
    event = next(
        item for item in events if item.source_event_id == "allday-001@example.test"
    )

    assert event.title == "Record Fair"
    assert event.all_day is True
    assert event.start_datetime.isoformat() == "2026-07-11T00:00:00"
    assert event.end_datetime is not None
    assert event.end_datetime.isoformat() == "2026-07-12T00:00:00"
    assert event.location_text == "Downtown Market"


def test_parse_ics_event_with_missing_optional_fields():
    events = parse_ics_events(SAMPLE_ICS)
    event = next(
        item for item in events if item.source_event_id == "minimal-001@example.test"
    )

    assert event.title == "Minimal Listing"
    assert event.description is None
    assert event.location_text is None
    assert event.source_url is None
    assert event.end_datetime is None


def test_parse_ics_uid_and_url():
    events = parse_ics_events(SAMPLE_ICS)
    event = next(item for item in events if item.title == "Friday Night Showcase")

    assert event.source_event_id == "timed-001@example.test"
    assert event.source_url == "https://example.test/events/friday-night-showcase"


def test_successful_ics_crawl_saves_events(tmp_path):
    def fetcher(url: str) -> FetchResult:
        return FetchResult(
            http_status_code=200,
            content_type="text/calendar; charset=utf-8",
            raw_response_body=SAMPLE_ICS,
        )

    with make_client(tmp_path) as client:
        submit_source(
            client,
            organization_name="ICS Venue",
            calendar_url="https://example.com/sample.ics",
        )
        approve_source(client)
        client.app.state.fetch_calendar_url = fetcher

        detail_response = admin_post(
            client,
            "/admin/sources/1/crawl",
            follow_redirects=True,
        )
        events_response = admin_get(client, "/admin/events")

    assert detail_response.status_code == 200
    assert "3 events extracted from this ICS crawl." in detail_response.text
    assert events_response.status_code == 200
    assert "Friday Night Showcase" in events_response.text
    assert "Record Fair" in events_response.text
    assert "Minimal Listing" in events_response.text


def test_non_ics_crawl_does_not_extract_events(tmp_path):
    def fetcher(url: str) -> FetchResult:
        return FetchResult(
            http_status_code=200,
            content_type="text/html; charset=utf-8",
            raw_response_body="<html><p>No calendar here.</p></html>",
        )

    with make_client(tmp_path) as client:
        submit_source(client, calendar_url="https://example.com/events")
        approve_source(client)
        client.app.state.fetch_calendar_url = fetcher

        detail_response = admin_post(
            client,
            "/admin/sources/1/crawl",
            follow_redirects=True,
        )
        events_response = admin_get(client, "/admin/events")

    assert "Event Extraction" in detail_response.text
    assert "html_event_list" in detail_response.text
    assert "No extractable static HTML event cards found." in detail_response.text
    assert "No extracted events yet." in events_response.text


def test_jsonld_extractor_extracts_musicevent_fields():
    result = extract_source_content(
        source_url="https://venue.example/events/jsonld-fixture-band",
        content_type="text/html",
        raw_body=SAMPLE_JSONLD_HTML,
    )

    assert result.extractor_type == "json_ld_event"
    assert result.status == "success"
    assert len(result.event_candidates) == 1
    candidate = result.event_candidates[0]
    assert candidate.event_name == "JSON-LD Fixture Band at River Hall"
    assert candidate.start_datetime is not None
    assert candidate.start_datetime.isoformat().startswith("2026-09-12T20:00:00")
    assert candidate.venue_name == "River Hall"
    assert candidate.city == "Memphis"
    assert candidate.state == "TN"
    assert candidate.latitude == 35.1495
    assert candidate.longitude == -90.049
    assert candidate.tickets_link == "https://tickets.example/jsonld-fixture-band"
    assert candidate.price == "25 USD"
    assert candidate.headliner == "JSON-LD Fixture Band"
    assert candidate.supporting_artists == "The Test Openers"
    assert candidate.source_event_id == "fixture-jsonld-001"
    assert [item.image_url for item in candidate.image_candidates] == [
        "https://images.example/jsonld-fixture-band.jpg"
    ]


def test_jsonld_extractor_extracts_graph_event_and_ignores_non_events():
    body = """
    <html><head>
      <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@graph": [
            {"@type": "BreadcrumbList", "name": "Not an event"},
            {
              "@type": "Event",
              "@id": "graph-event-001",
              "name": "Graph Fixture Concert",
              "startDate": "2026-10-01T19:00:00",
              "url": "https://venue.example/events/graph-fixture"
            }
          ]
        }
      </script>
    </head></html>
    """

    result = extract_source_content(
        source_url="https://venue.example/events/graph-fixture",
        content_type="text/html",
        raw_body=body,
    )

    assert result.extractor_type == "json_ld_event"
    assert result.status == "success"
    assert [item.event_name for item in result.event_candidates] == [
        "Graph Fixture Concert"
    ]


def test_rss_atom_extractor_conservatively_marks_weak_items():
    result = extract_source_content(
        source_url="https://venue.example/events.rss",
        content_type="application/rss+xml",
        raw_body=SAMPLE_RSS,
    )

    assert result.extractor_type == "rss_atom"
    assert result.status == "partial"
    assert len(result.event_candidates) == 2
    dated, undated = result.event_candidates
    assert dated.event_name == "RSS Fixture Trio - September 14, 2026 at 8:00 pm"
    assert dated.start_datetime is not None
    assert dated.event_url == "https://venue.example/events/rss-fixture-trio"
    assert dated.validation_status == "valid"
    assert undated.event_name == "Undated RSS Venue News"
    assert undated.start_datetime is None
    assert undated.review_status == "needs_review"
    assert undated.validation_status == "invalid"
    assert "Missing reliable event date." in undated.validation_errors
    assert "published_date_not_event_date" in undated.quality_flags


def test_html_extractor_extracts_static_event_cards_and_direct_images():
    result = extract_source_content(
        source_url="https://venue.example/events",
        content_type="text/html",
        raw_body=SAMPLE_HTML_EVENTS,
    )

    assert result.extractor_type == "html_event_list"
    assert result.status == "partial"
    assert len(result.event_candidates) == 1
    candidate = result.event_candidates[0]
    assert candidate.event_name == "HTML Fixture Quartet"
    assert candidate.start_datetime is not None
    assert candidate.venue_name == "Blue Note Room"
    assert candidate.event_url == "https://venue.example/events/html-fixture-quartet"
    assert candidate.tickets_link == "https://tickets.example/html-fixture-quartet"
    assert [item.image_url for item in candidate.image_candidates] == [
        "https://images.example/html-fixture-quartet.jpg"
    ]
    assert "https://instagram.com/p/not-a-direct-image" not in {
        item.image_url for item in candidate.image_candidates
    }
    assert any(
        link.discovered_url == "https://venue.example/events/html-fixture-quartet"
        for link in result.discovered_links
    )


def test_generic_html_link_discovery_stores_possible_event_links():
    body = """
    <html><body>
      <a href="/events/future-show">Future show details</a>
      <a href="/about">About the venue</a>
    </body></html>
    """

    result = extract_source_content(
        source_url="https://venue.example/calendar",
        content_type="text/html",
        raw_body=body,
    )

    assert result.extractor_type == "generic_html_links"
    assert result.status == "partial"
    assert result.event_candidates == []
    assert [link.discovered_url for link in result.discovered_links] == [
        "https://venue.example/events/future-show"
    ]


def test_jsonld_crawl_creates_staged_candidate_and_extraction_panel(tmp_path):
    def fetcher(url: str) -> FetchResult:
        return FetchResult(
            http_status_code=200,
            content_type="text/html; charset=utf-8",
            raw_response_body=SAMPLE_JSONLD_HTML,
        )

    with make_client(tmp_path) as client:
        submit_source(
            client,
            organization_name="JSON-LD Venue",
            calendar_url="https://venue.example/events/jsonld-fixture-band",
        )
        approve_source(client)
        client.app.state.fetch_calendar_url = fetcher

        detail_response = admin_post(
            client,
            "/admin/sources/1/crawl",
            follow_redirects=True,
        )
        extracted_response = admin_get(client, "/admin/extracted-events")
        with client.app.state.SessionLocal() as session:
            candidate = session.scalars(
                select(SourceExtractedEventCandidate)
            ).one()
            crawl_run = get_crawl_run(session, 1)
            events = list(session.scalars(select(Event)).all())
            images = list(session.scalars(select(ImageCandidate)).all())
            poi_candidates = list(session.scalars(select(PoiCandidate)).all())
            pois = list(session.scalars(select(PoiLocation)).all())

    assert detail_response.status_code == 200
    assert "Event Extraction" in detail_response.text
    assert "json_ld_event" in detail_response.text
    assert "JSON-LD Fixture Band at River Hall" in detail_response.text
    assert "JSON-LD Fixture Band at River Hall" in extracted_response.text
    assert crawl_run is not None
    assert crawl_run.extractor_type == "json_ld_event"
    assert crawl_run.extraction_status == "success"
    assert crawl_run.event_candidates_count == 1
    assert candidate.review_status == "pending_review"
    assert candidate.validation_status == "valid"
    assert candidate.normalized_payload["category"] == "Concert"
    assert candidate.normalized_payload["record_type"] == "event"
    assert candidate.normalized_payload["ticket_link_classification"] == "direct"
    assert candidate.normalized_payload["image_candidates"] != []
    assert len(poi_candidates) == 1
    assert poi_candidates[0].candidate_name == "River Hall"
    assert poi_candidates[0].suggested_category == "Music Site"
    assert poi_candidates[0].suggested_subcategory == "Venues"
    assert poi_candidates[0].review_status == "pending_review"
    assert poi_candidates[0].match_status == "new_candidate"
    assert events == []
    assert images == []
    assert pois == []


def test_jsonld_location_candidate_matches_existing_poi_strongly(tmp_path):
    def fetcher(url: str) -> FetchResult:
        return FetchResult(
            http_status_code=200,
            content_type="text/html; charset=utf-8",
            raw_response_body=SAMPLE_JSONLD_HTML,
        )

    with make_client(tmp_path) as client:
        with client.app.state.SessionLocal() as session:
            existing_poi = add_test_poi_location(session)
            existing_poi_id = existing_poi.id
        submit_source(
            client,
            organization_name="JSON-LD Venue",
            calendar_url="https://venue.example/events/jsonld-fixture-band",
        )
        approve_source(client)
        client.app.state.fetch_calendar_url = fetcher

        admin_post(client, "/admin/sources/1/crawl", follow_redirects=True)
        with client.app.state.SessionLocal() as session:
            candidate = session.scalars(select(PoiCandidate)).one()
            pois = list(session.scalars(select(PoiLocation)).all())

    assert len(pois) == 1
    assert candidate.candidate_name == "River Hall"
    assert candidate.match_status == "matched_existing"
    assert candidate.match_confidence == "strong"
    assert candidate.matched_poi_location_id == existing_poi_id


def test_weak_poi_candidate_match_requires_review_without_auto_link(tmp_path):
    with make_client(tmp_path) as client:
        with client.app.state.SessionLocal() as session:
            add_test_poi_location(
                session,
                name="Blue Room",
                latitude=None,
                longitude=None,
                address=None,
                city="Memphis",
                state="TN",
                website=None,
            )
            candidate = add_test_poi_candidate(
                session,
                candidate_name="Blue Room",
                latitude=None,
                longitude=None,
                address=None,
                city="Memphis",
                state="TN",
                website=None,
            )

    assert candidate.match_status == "possible_duplicate"
    assert candidate.match_confidence == "weak"
    assert candidate.matched_poi_location_id is None
    assert candidate.review_status == "pending_review"


def test_html_event_card_with_venue_creates_poi_candidate(tmp_path):
    with make_client(tmp_path) as client:
        submit_source(client, calendar_url="https://venue.example/events")
        approve_source(client)
        client.app.state.fetch_calendar_url = lambda url: FetchResult(
            http_status_code=200,
            content_type="text/html",
            raw_response_body=SAMPLE_HTML_EVENTS,
        )
        admin_post(client, "/admin/sources/1/crawl", follow_redirects=True)
        with client.app.state.SessionLocal() as session:
            event_candidates = list(
                session.scalars(select(SourceExtractedEventCandidate)).all()
            )
            poi_candidates = list(session.scalars(select(PoiCandidate)).all())
            pois = list(session.scalars(select(PoiLocation)).all())

    assert len(event_candidates) == 1
    assert len(poi_candidates) == 1
    assert poi_candidates[0].candidate_name == "Blue Note Room"
    assert "missing_geo" in poi_candidates[0].poi_quality_flags
    assert pois == []


def test_html_event_card_without_venue_does_not_create_poi_candidate(tmp_path):
    body = """
    <html><body>
      <article class="event-card">
        <h2>No Venue Fixture</h2>
        <time datetime="2026-09-20T20:00:00">September 20, 2026</time>
        <a href="/events/no-venue-fixture">Event details</a>
      </article>
    </body></html>
    """
    with make_client(tmp_path) as client:
        submit_source(client, calendar_url="https://venue.example/events")
        approve_source(client)
        client.app.state.fetch_calendar_url = lambda url: FetchResult(
            http_status_code=200,
            content_type="text/html",
            raw_response_body=body,
        )
        admin_post(client, "/admin/sources/1/crawl", follow_redirects=True)
        with client.app.state.SessionLocal() as session:
            event_candidates = list(
                session.scalars(select(SourceExtractedEventCandidate)).all()
            )
            poi_candidates = list(session.scalars(select(PoiCandidate)).all())
            pois = list(session.scalars(select(PoiLocation)).all())

    assert len(event_candidates) == 1
    assert poi_candidates == []
    assert pois == []


def test_poi_candidate_quality_flags_social_logo_and_missing_geo(tmp_path):
    with make_client(tmp_path) as client:
        with client.app.state.SessionLocal() as session:
            social_candidate = add_test_poi_candidate(
                session,
                candidate_name="Social Image Hall",
                latitude=None,
                longitude=None,
                main_image_url="https://instagram.com/p/not-a-direct-image",
            )
            logo_candidate = add_test_poi_candidate(
                session,
                candidate_name="Logo Image Hall",
                main_image_url="/static/images/music-roadtrip-logo-square.png",
            )

    assert "missing_geo" in social_candidate.poi_quality_flags
    assert "social_image_url" in social_candidate.poi_quality_flags
    assert "music_roadtrip_logo_image" in logo_candidate.poi_quality_flags


def test_approve_new_poi_candidate_creates_approved_poi_location(tmp_path):
    with make_client(tmp_path) as client:
        with client.app.state.SessionLocal() as session:
            candidate = add_test_poi_candidate(session, candidate_name="Approved Room")
            poi = approve_candidate_create_poi(session, candidate.id)
            refreshed = session.get(PoiCandidate, candidate.id)
            pois = list(session.scalars(select(PoiLocation)).all())

    assert poi.display_name == "Approved Room"
    assert poi.category == "Music Site"
    assert poi.subcategory == "Venues"
    assert poi.publish_status == "approved"
    assert len(pois) == 1
    assert refreshed is not None
    assert refreshed.review_status == "approved"
    assert refreshed.match_status == "approved_created"
    assert refreshed.created_poi_location_id == poi.id


def test_approve_update_existing_poi_updates_safe_non_blank_fields_only(tmp_path):
    with make_client(tmp_path) as client:
        with client.app.state.SessionLocal() as session:
            poi = add_test_poi_location(
                session,
                name="Trusted Hall",
                website="https://trusted.example",
            )
            candidate = add_test_poi_candidate(
                session,
                candidate_name="Trusted Hall",
                latitude=poi.latitude,
                longitude=poi.longitude,
                website=None,
                phone="901-555-0100",
                description="Better reviewed venue description.",
            )
            updated = approve_candidate_update_existing_poi(
                session,
                candidate.id,
                poi.id,
            )
            refreshed_candidate = session.get(PoiCandidate, candidate.id)

    assert updated.website == "https://trusted.example"
    assert updated.phone == "901-555-0100"
    assert updated.description == "Better reviewed venue description."
    assert refreshed_candidate is not None
    assert refreshed_candidate.match_status == "approved_updated"


def test_link_existing_poi_candidate_does_not_create_duplicate(tmp_path):
    with make_client(tmp_path) as client:
        with client.app.state.SessionLocal() as session:
            poi = add_test_poi_location(session, name="Existing Link Hall")
            candidate = add_test_poi_candidate(
                session,
                candidate_name="Existing Link Hall",
                latitude=poi.latitude,
                longitude=poi.longitude,
            )
            linked = link_candidate_to_existing_poi(session, candidate.id, poi.id)
            pois = list(session.scalars(select(PoiLocation)).all())

    assert len(pois) == 1
    assert linked.match_status == "matched_existing"
    assert linked.review_status == "approved"
    assert linked.matched_poi_location_id == poi.id


def test_event_venue_only_and_reject_do_not_create_poi_locations(tmp_path):
    with make_client(tmp_path) as client:
        with client.app.state.SessionLocal() as session:
            venue_only = add_test_poi_candidate(session, candidate_name="Private Room")
            rejected = add_test_poi_candidate(session, candidate_name="Bad Listing")
            venue_only = mark_candidate_event_venue_only(session, venue_only.id)
            rejected = reject_poi_candidate(session, rejected.id, "Not music relevant")
            pois = list(session.scalars(select(PoiLocation)).all())

    assert pois == []
    assert venue_only.match_status == "event_venue_only"
    assert venue_only.review_status == "approved"
    assert rejected.match_status == "rejected"
    assert rejected.review_status == "rejected"


def test_poi_candidates_admin_routes_and_csrf(tmp_path):
    with make_client(tmp_path) as client:
        unauth = client.get("/admin/poi-candidates", follow_redirects=False)
        with client.app.state.SessionLocal() as session:
            candidate = add_test_poi_candidate(session, candidate_name="Audit Hall")
            candidate_id = candidate.id
        list_response = admin_get(client, "/admin/poi-candidates")
        detail_response = admin_get(client, f"/admin/poi-candidates/{candidate_id}")
        login_admin(client)
        no_csrf = client.post(
            f"/admin/poi-candidates/{candidate_id}/approve-create",
            follow_redirects=False,
        )

    assert unauth.status_code == 303
    assert unauth.headers["location"].startswith("/admin/login")
    assert list_response.status_code == 200
    assert "Incoming POI Candidate Audit" in list_response.text
    assert "Audit Hall" in list_response.text
    assert detail_response.status_code == 200
    assert "Quality flags" in detail_response.text
    assert no_csrf.status_code == 403


def test_poi_candidate_app_feed_safety(tmp_path):
    with make_client(tmp_path) as client:
        with client.app.state.SessionLocal() as session:
            candidate = add_test_poi_candidate(session, candidate_name="Feed Safe Hall")
        hidden_response = admin_get(client, "/admin/app-feed/pois.json")
        with client.app.state.SessionLocal() as session:
            approve_candidate_create_poi(session, candidate.id)
        visible_response = admin_get(client, "/admin/app-feed/pois.json")

    hidden_payload = hidden_response.json()
    visible_payload = visible_response.json()
    assert hidden_payload["count"] == 0
    assert "Feed Safe Hall" not in hidden_response.text
    assert visible_payload["count"] == 1
    assert visible_payload["records"][0]["name"] == "Feed Safe Hall"


def test_html_crawl_stores_discovered_links_without_auto_crawling(tmp_path):
    def fetcher(url: str) -> FetchResult:
        return FetchResult(
            http_status_code=200,
            content_type="text/html; charset=utf-8",
            raw_response_body=(
                '<html><a href="/events/future-show">'
                "Future show details</a></html>"
            ),
        )

    with make_client(tmp_path) as client:
        submit_source(client, calendar_url="https://venue.example/calendar")
        approve_source(client)
        client.app.state.fetch_calendar_url = fetcher

        detail_response = admin_post(
            client,
            "/admin/sources/1/crawl",
            follow_redirects=True,
        )
        with client.app.state.SessionLocal() as session:
            crawl_run = get_crawl_run(session, 1)
            candidates = list(session.scalars(select(SourceExtractedEventCandidate)))

    assert detail_response.status_code == 200
    assert "generic_html_links" in detail_response.text
    assert "https://venue.example/events/future-show" in detail_response.text
    assert crawl_run is not None
    assert crawl_run.discovered_links_count == 1
    assert crawl_run.event_candidates_count == 0
    assert candidates == []


def test_extracted_events_requires_login_and_approval_requires_csrf(tmp_path):
    with make_client(tmp_path) as client:
        login_required = client.get("/admin/extracted-events", follow_redirects=False)
        submit_source(client, calendar_url="https://venue.example/events/jsonld")
        approve_source(client)
        client.app.state.fetch_calendar_url = lambda url: FetchResult(
            http_status_code=200,
            content_type="text/html",
            raw_response_body=SAMPLE_JSONLD_HTML,
        )
        admin_post(client, "/admin/sources/1/crawl", follow_redirects=True)
        login_admin(client)
        no_csrf = client.post(
            "/admin/extracted-events/1/approve",
            follow_redirects=False,
        )

    assert login_required.status_code == 303
    assert login_required.headers["location"].startswith("/admin/login")
    assert no_csrf.status_code == 403


def test_approving_extracted_candidate_uses_event_upsert_and_source_claims(
    tmp_path,
):
    with make_client(tmp_path) as client:
        submit_source(
            client,
            organization_name="Approval JSON-LD Venue",
            calendar_url="https://venue.example/events/jsonld-fixture-band",
        )
        approve_source(client)
        client.app.state.fetch_calendar_url = lambda url: FetchResult(
            http_status_code=200,
            content_type="text/html",
            raw_response_body=SAMPLE_JSONLD_HTML,
        )
        admin_post(client, "/admin/sources/1/crawl", follow_redirects=True)

        approve = admin_post(
            client,
            "/admin/extracted-events/1/approve",
            follow_redirects=True,
        )
        approve_again = admin_post(
            client,
            "/admin/extracted-events/1/approve",
            follow_redirects=True,
        )
        with client.app.state.SessionLocal() as session:
            events = list(session.scalars(select(Event)).all())
            claims = list(session.scalars(select(EventSourceClaim)).all())
            images = list(session.scalars(select(ImageCandidate)).all())
            pois = list(session.scalars(select(PoiLocation)).all())
            candidate = session.get(SourceExtractedEventCandidate, 1)

    assert approve.status_code == 200
    assert approve_again.status_code == 200
    assert len(events) == 1
    assert events[0].title == "JSON-LD Fixture Band at River Hall"
    assert events[0].category == "Concert"
    assert events[0].record_type == "event"
    assert events[0].source_type == "source_extracted"
    assert events[0].tickets_link == "https://tickets.example/jsonld-fixture-band"
    assert len(claims) == 1
    assert claims[0].source_type == "source_extracted"
    assert claims[0].source_url == "https://venue.example/events/jsonld-fixture-band"
    assert claims[0].crawl_run_id == 1
    assert len(images) == 1
    assert images[0].image_url == "https://images.example/jsonld-fixture-band.jpg"
    assert pois == []
    assert candidate is not None
    assert candidate.created_event_id == events[0].id
    assert candidate.review_status == "approved"


def test_approve_extracted_candidate_background_job_creates_event(tmp_path):
    with make_client(tmp_path) as client:
        submit_source(client, calendar_url="https://venue.example/events/jsonld")
        approve_source(client)
        client.app.state.fetch_calendar_url = lambda url: FetchResult(
            http_status_code=200,
            content_type="text/html",
            raw_response_body=SAMPLE_JSONLD_HTML,
        )
        admin_post(client, "/admin/sources/1/crawl", follow_redirects=True)
        with client.app.state.SessionLocal() as session:
            enqueue_job(
                session,
                "approve_extracted_event_candidate",
                {"candidate_id": 1},
            )
            processed = process_next_job(
                session,
                client.app.state.settings,
                worker_id="test-worker",
            )
            events = list(session.scalars(select(Event)).all())

    assert processed is not None
    assert processed.status == "success"
    assert processed.result["candidate_id"] == 1
    assert processed.result["event_id"] == events[0].id
    assert len(events) == 1


def test_extract_crawl_run_background_job_is_idempotent(tmp_path):
    with make_client(tmp_path) as client:
        submit_source(client, calendar_url="https://venue.example/events/jsonld")
        approve_source(client)
        client.app.state.fetch_calendar_url = lambda url: FetchResult(
            http_status_code=200,
            content_type="text/html",
            raw_response_body=SAMPLE_JSONLD_HTML,
        )
        admin_post(client, "/admin/sources/1/crawl", follow_redirects=True)
        with client.app.state.SessionLocal() as session:
            enqueue_job(session, "extract_crawl_run", {"crawl_run_id": 1})
            processed = process_next_job(
                session,
                client.app.state.settings,
                worker_id="test-worker",
            )
            candidates = list(
                session.scalars(select(SourceExtractedEventCandidate)).all()
            )

    assert processed is not None
    assert processed.status == "success"
    assert processed.result["extractor_type"] == "json_ld_event"
    assert processed.result["event_candidates_count"] == 1
    assert len(candidates) == 1


def test_process_extracted_event_batch_background_job_approves_valid_rows(
    tmp_path,
):
    with make_client(tmp_path) as client:
        submit_source(client, calendar_url="https://venue.example/events/jsonld")
        approve_source(client)
        client.app.state.fetch_calendar_url = lambda url: FetchResult(
            http_status_code=200,
            content_type="text/html",
            raw_response_body=SAMPLE_JSONLD_HTML,
        )
        admin_post(client, "/admin/sources/1/crawl", follow_redirects=True)
        with client.app.state.SessionLocal() as session:
            enqueue_job(session, "process_extracted_event_batch", {"crawl_run_id": 1})
            processed = process_next_job(
                session,
                client.app.state.settings,
                worker_id="test-worker",
            )
            events = list(session.scalars(select(Event)).all())

    assert processed is not None
    assert processed.status == "success"
    assert processed.result["selected_count"] == 1
    assert processed.result["approved_count"] == 1
    assert processed.result["failed_count"] == 0
    assert len(events) == 1


def test_same_crawl_run_does_not_create_duplicate_events(tmp_path):
    def fetcher(url: str) -> FetchResult:
        return FetchResult(
            http_status_code=200,
            content_type="text/calendar",
            raw_response_body=SAMPLE_ICS,
        )

    with make_client(tmp_path) as client:
        submit_source(client, calendar_url="https://example.com/sample.ics")
        approve_source(client)
        client.app.state.fetch_calendar_url = fetcher
        admin_post(client, "/admin/sources/1/crawl", follow_redirects=True)

        with client.app.state.SessionLocal() as session:
            crawl_run = get_crawl_run(session, 1)
            assert crawl_run is not None
            assert count_events_for_crawl_run(session, crawl_run.id) == 3
            assert save_ics_events_for_crawl_run(session, crawl_run) == 0
            assert count_events_for_crawl_run(session, crawl_run.id) == 3


def test_admin_events_page_loads(tmp_path):
    with make_client(tmp_path) as client:
        response = admin_get(client, "/admin/events")

    assert response.status_code == 200
    assert "Events" in response.text


def test_event_detail_page_loads(tmp_path):
    def fetcher(url: str) -> FetchResult:
        return FetchResult(
            http_status_code=200,
            content_type="text/calendar",
            raw_response_body=SAMPLE_ICS,
        )

    with make_client(tmp_path) as client:
        submit_source(client, calendar_url="https://example.com/sample.ics")
        approve_source(client)
        client.app.state.fetch_calendar_url = fetcher
        admin_post(client, "/admin/sources/1/crawl", follow_redirects=True)

        detail_response = admin_get(client, "/admin/events/1")

    assert detail_response.status_code == 200
    assert "Friday Night Showcase" in detail_response.text
    assert "timed-001@example.test" in detail_response.text
    assert "Crawl run" in detail_response.text


def test_honeypot_submission_is_flagged(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post(
            "/submit-concerts",
            data={
                "organization_name": "Bot Venue",
                "calendar_url": "https://bot.example/events.ics",
                "contact_email": "bot@example.com",
                "permission_confirmed": "true",
                "website": "filled by bot",
            },
            follow_redirects=False,
        )
        source = get_source(client)
        suspicious = admin_get(client, "/admin/suspicious-submissions")

    assert response.status_code == 303
    assert source.risk_level == "blocked"
    assert "honeypot_filled" in source.risk_flags
    assert source.review_status == "blocked"
    assert "Bot Venue" in suspicious.text


def test_too_fast_submission_is_flagged(tmp_path):
    with make_client(tmp_path) as client:
        rendered_at = utc_now().isoformat()
        response = client.post(
            "/submit-concerts",
            data={
                "organization_name": "Fast Venue",
                "calendar_url": "https://fast.example/events.ics",
                "contact_email": "fast@example.com",
                "permission_confirmed": "true",
                "form_rendered_at": rendered_at,
            },
            follow_redirects=False,
        )
        source = get_source(client)

    assert response.status_code == 303
    assert "submitted_too_fast" in source.risk_flags
    assert source.risk_level in {"high", "blocked"}


def test_invalid_url_scheme_is_rejected(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post(
            "/submit-calendar",
            data={
                "organization_name": "Bad URL Venue",
                "calendar_url": "ftp://example.com/events.ics",
                "contact_email": "owner@example.com",
                "permission_confirmed": "true",
            },
        )

    assert response.status_code == 400
    assert "Calendar URL must be a valid http or https URL." in response.text


def test_localhost_url_is_blocked_in_production(tmp_path):
    with make_client(tmp_path, environment="production") as client:
        response = client.post(
            "/submit-calendar",
            data={
                "organization_name": "Production Localhost",
                "calendar_url": "http://127.0.0.1:8000/dev/sample-calendar.ics",
                "contact_email": "owner@example.com",
                "permission_confirmed": "true",
            },
            follow_redirects=False,
        )
        source = get_source(client)
        approve_source(client)
        admin_response = admin_get(client, "/admin/sources")

    assert response.status_code == 303
    assert source.risk_level == "blocked"
    assert "private_network_url_blocked_in_production" in source.risk_flags
    assert "Run Crawl" not in admin_response.text


def test_localhost_demo_url_is_allowed_in_development(tmp_path):
    with make_client(tmp_path, environment="development") as client:
        response = client.post(
            "/submit-calendar",
            data={
                "organization_name": "Development Localhost",
                "calendar_url": "http://127.0.0.1:8000/dev/sample-calendar.ics",
                "contact_email": "owner@example.com",
                "permission_confirmed": "true",
            },
            follow_redirects=False,
        )
        source = get_source(client)

    assert response.status_code == 303
    assert "private_network_url_blocked_in_production" not in source.risk_flags
    assert source.risk_level == "low"


def test_duplicate_calendar_url_is_flagged_and_attached_as_claim(tmp_path):
    with make_client(tmp_path) as client:
        submit_source(client, calendar_url="https://example.com/events.ics")
        response = client.post(
            "/submit-calendar",
            data={
                "organization_name": "Duplicate Venue",
                "calendar_url": "https://example.com/events.ics?utm_source=test",
                "contact_email": "claimant@example.com",
                "permission_confirmed": "true",
            },
            follow_redirects=False,
        )
        duplicate = get_source(client, source_id=2)

    assert response.status_code == 303
    assert duplicate.claimed_source_id == 1
    assert "duplicate_calendar_url" in duplicate.risk_flags


def test_suspicious_concert_file_many_invalid_rows_is_quarantined():
    assessment = score_concert_event_rows(
        [
            {
                "Category": "Workshop",
                "Event Name": "",
                "Headliner": "",
                "Start Date": "",
                "Timezone": "",
                "Venue Name": "",
                "City": "",
                "State": "",
                "Main Image URL": "https://instagram.com/p/example",
            }
        ]
    )

    assert assessment.risk_level in {"high", "blocked"}
    assert "too_many_invalid_rows" in assessment.risk_flags
    assert "non_concert_category" in assessment.risk_flags
    assert "main_image_social_media_url" in assessment.risk_flags


def test_calendar_source_upload_flags_bad_rows():
    assessment = score_calendar_source_rows(
        [
            {
                "Organization Name": "asdf",
                "Calendar URL": "",
                "Contact Email": "",
                "Authorization Confirmed": "false",
                "Expected Category": "Sports",
            },
            {
                "Organization Name": "test test",
                "Calendar URL": "https://example.com/events.ics",
                "Contact Email": "owner@example.com",
                "Authorization Confirmed": "true",
                "Expected Category": "Concert",
            },
            {
                "Organization Name": "Another",
                "Calendar URL": "https://example.com/events.ics",
                "Contact Email": "owner@example.com",
                "Authorization Confirmed": "true",
                "Expected Category": "Concert",
            },
        ],
        existing_canonical_urls={"https://already.example/events.ics"},
    )

    assert "calendar_url_missing" in assessment.risk_flags
    assert "authorization_missing" in assessment.risk_flags
    assert "expected_category_not_concert" in assessment.risk_flags
    assert "duplicate_calendar_url_in_file" in assessment.risk_flags
    assert "junk_or_test_values" in assessment.risk_flags


def test_blocked_domain_cannot_submit_crawlable_source(tmp_path):
    with make_client(tmp_path) as client:
        with client.app.state.SessionLocal() as session:
            session.add(
                BlockedSubmitter(
                    url_domain="blocked.example",
                    reason="Known abuse.",
                )
            )
            session.commit()

        client.post(
            "/submit-calendar",
            data={
                "organization_name": "Blocked Domain",
                "calendar_url": "https://blocked.example/events.ics",
                "contact_email": "owner@example.com",
                "permission_confirmed": "true",
            },
        )
        source = get_source(client)
        approve_source(client)
        crawl_response = admin_post(client, "/admin/sources/1/crawl")

    assert source.risk_level == "blocked"
    assert "blocked_submitter_or_domain" in source.risk_flags
    assert crawl_response.status_code == 400


def test_trusted_submitter_gets_reduced_risk_but_still_validates(tmp_path):
    with make_client(tmp_path) as client:
        with client.app.state.SessionLocal() as session:
            session.add(
                TrustedSubmitter(
                    email="trusted@example.com",
                    notes="Known partner.",
                )
            )
            session.commit()

        client.post(
            "/submit-calendar",
            data={
                "organization_name": "Trusted Venue",
                "calendar_url": "https://example.com/events",
                "contact_email": "trusted@example.com",
                "permission_confirmed": "true",
            },
        )
        source = get_source(client)
        invalid_response = client.post(
            "/submit-calendar",
            data={
                "organization_name": "Trusted Venue",
                "calendar_url": "ftp://example.com/events",
                "contact_email": "trusted@example.com",
                "permission_confirmed": "true",
            },
        )

    assert "trusted_submitter_or_domain" in source.risk_flags
    assert source.risk_score == 0
    assert invalid_response.status_code == 400


def test_turnstile_disabled_locally_allows_normal_public_form(tmp_path):
    with make_client_with_settings(tmp_path, turnstile_enabled=False) as client:
        response = client.post(
            "/submit-calendar/url",
            data={
                "organization_name": "Local Venue",
                "calendar_url": "https://local.example/events.ics",
                "contact_email": "owner@local.example",
                "permission_confirmed": "true",
            },
            follow_redirects=False,
        )

    assert response.status_code == 303


def test_turnstile_enabled_requires_valid_token_and_blocks_invalid(tmp_path):
    with make_client_with_settings(
        tmp_path,
        turnstile_enabled=True,
        turnstile_site_key="site-key",
        turnstile_secret_key="turnstile-fixture-value",
    ) as client:
        client.app.state.turnstile_verifier = (
            lambda token, _ip: token == "valid-token"
        )
        valid = client.post(
            "/submit-calendar/url",
            data={
                "organization_name": "Verified Venue",
                "calendar_url": "https://verified.example/events.ics",
                "contact_email": "owner@verified.example",
                "permission_confirmed": "true",
                "cf-turnstile-response": "valid-token",
            },
            follow_redirects=False,
        )
        invalid = client.post(
            "/submit-calendar/url",
            data={
                "organization_name": "Blocked Bot Venue",
                "calendar_url": "https://blockedbot.example/events.ics",
                "contact_email": "bot@blockedbot.example",
                "permission_confirmed": "true",
                "cf-turnstile-response": "bad-token",
            },
            follow_redirects=False,
        )
        with client.app.state.SessionLocal() as session:
            blocked_source = session.get(CalendarSource, 2)
            master_count = len(session.scalars(select(MasterCalendarSource)).all())
            attempts = session.scalars(select(SubmissionAttempt)).all()

    assert valid.status_code == 303
    assert invalid.status_code == 400
    assert blocked_source is not None
    assert blocked_source.review_status == "blocked"
    assert "turnstile_token_invalid" in blocked_source.risk_flags
    assert master_count == 1
    assert any(
        "turnstile_token_invalid" in attempt.risk_flags_json
        for attempt in attempts
    )


def test_public_rate_limits_trigger_suspicious_state(tmp_path):
    with make_client_with_settings(
        tmp_path,
        public_submit_rate_limit_per_ip_per_hour=1,
    ) as client:
        first = client.post(
            "/submit-calendar",
            data={
                "organization_name": "First Venue",
                "calendar_url": "https://ratelimit.example/events-1.ics",
                "contact_email": "one@ratelimit.example",
                "permission_confirmed": "true",
            },
            follow_redirects=False,
        )
        second = client.post(
            "/submit-calendar",
            data={
                "organization_name": "Second Venue",
                "calendar_url": "https://ratelimit.example/events-2.ics",
                "contact_email": "two@ratelimit.example",
                "permission_confirmed": "true",
            },
            follow_redirects=False,
        )
        source = get_source(client, source_id=2)
        security = admin_get(client, "/admin/security")

    assert first.status_code == 303
    assert second.status_code == 303
    assert source.review_status == "blocked"
    assert "rate_limit_ip_hour_exceeded" in source.risk_flags
    assert "Rate-limit hits" in security.text


def test_admin_login_rate_limit_and_audit_log(tmp_path):
    with make_client_with_settings(
        tmp_path,
        admin_login_rate_limit_per_ip_per_hour=1,
    ) as client:
        first = client.post(
            "/admin/login",
            data={"username": "admin", "password": "wrong"},
        )
        second = client.post(
            "/admin/login",
            data={"username": "admin", "password": "wrong"},
        )
        with client.app.state.SessionLocal() as session:
            actions = [
                entry.action
                for entry in session.scalars(select(AdminAuditLog)).all()
            ]

    assert first.status_code == 401
    assert second.status_code == 429
    assert "login_failure" in actions
    assert "login_rate_limited" in actions


def test_audit_log_records_admin_source_actions(tmp_path):
    with make_client(tmp_path) as client:
        submit_source(client, calendar_url="https://audit.example/events.ics")
        approve_source(client)
        with client.app.state.SessionLocal() as session:
            actions = [
                entry.action
                for entry in session.scalars(select(AdminAuditLog)).all()
            ]

    assert "login_success" in actions
    assert "source_approved" in actions


def test_security_redaction_covers_sensitive_keys_and_text():
    redacted = redact_security_payload(
        {
            "api_key": "SECRET_VALUE",
            "headers": {"Authorization": "Bearer SECRET_TOKEN"},
            "url": "https://example.test/feed?token=SECRET_URL&safe=1",
            "note": "password=SECRET_PASSWORD",
        }
    )
    dumped = json.dumps(redacted)

    assert "SECRET_VALUE" not in dumped
    assert "SECRET_TOKEN" not in dumped
    assert "SECRET_URL" not in dumped
    assert "SECRET_PASSWORD" not in dumped
    assert "[REDACTED]" in dumped


def test_ssrf_url_safety_blocks_private_and_non_http_urls(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        environment="production",
        admin_password_hash=DEV_ADMIN_PASSWORD_HASH,
        session_secret_key="test-session-secret",
    )

    assert "dangerous_url" in url_safety_flags("http://127.0.0.1:8000", settings)
    assert "aws_metadata_ip_blocked" in url_safety_flags(
        "http://169.254.169.254/latest/meta-data",
        settings,
    )
    assert "non_http_url_scheme_blocked" in url_safety_flags(
        "file:///etc/passwd",
        settings,
    )


def test_development_fixture_localhost_exception_still_works(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        environment="development",
        admin_password_hash=DEV_ADMIN_PASSWORD_HASH,
        session_secret_key="test-session-secret",
    )

    assert (
        url_safety_flags(
            "http://127.0.0.1:8000/dev/sample-calendar.ics",
            settings,
        )
        == []
    )


def test_public_file_upload_hardening_limits_and_formula_neutralization(tmp_path):
    rows = [
        valid_concert_row(**{"Event Name": "One"}),
        valid_concert_row(**{"Event Name": "Two"}),
    ]
    with make_client_with_settings(
        tmp_path,
        public_file_upload_max_size_mb=0,
    ) as client:
        too_large = client.post(
            "/submit-events/file",
            data={
                "organization_name": "Upload Org",
                "contact_email": "upload@example.com",
            },
            files={"upload_file": ("events.csv", b"not empty", "text/csv")},
        )

    invalid_extension_dir = tmp_path / "invalid-extension"
    invalid_extension_dir.mkdir()
    with make_client_with_settings(invalid_extension_dir) as client:
        invalid_extension = client.post(
            "/submit-events/file",
            data={
                "organization_name": "Upload Org",
                "contact_email": "upload@example.com",
            },
            files={"upload_file": ("events.xlsm", b"macro", XLSX_MIME)},
        )

    too_many_rows_dir = tmp_path / "too-many-rows"
    too_many_rows_dir.mkdir()
    with make_client_with_settings(
        too_many_rows_dir,
        public_file_upload_max_rows=1,
    ) as client:
        too_many_rows = client.post(
            "/submit-events/file",
            data={
                "organization_name": "Upload Org",
                "contact_email": "upload@example.com",
            },
            files={
                "upload_file": (
                    "events.csv",
                    csv_upload(CONCERT_EVENT_HEADERS, rows),
                    "text/csv",
                )
            },
        )

    assert too_large.status_code == 400
    assert "size limit" in too_large.text
    assert invalid_extension.status_code == 400
    assert "Macro-enabled" in invalid_extension.text
    assert too_many_rows.status_code == 400
    assert "too many rows" in too_many_rows.text
    assert neutralize_csv_formula("=cmd|' /C calc'!A0").startswith("'=")


def test_admin_security_page_requires_login_and_loads(tmp_path):
    with make_client(tmp_path) as client:
        unauthenticated = client.get("/admin/security", follow_redirects=False)
        authenticated = admin_get(client, "/admin/security")

    assert unauthenticated.status_code == 303
    assert unauthenticated.headers["location"].startswith("/admin/login")
    assert authenticated.status_code == 200
    assert "Security" in authenticated.text
    assert "Secrets redaction status" in authenticated.text


def test_high_risk_submissions_appear_in_suspicious_queue(tmp_path):
    with make_client(tmp_path) as client:
        client.post(
            "/submit-concerts",
            data={
                "organization_name": "Suspicious Venue",
                "calendar_url": "https://suspicious.example/events.ics",
                "contact_email": "owner@example.com",
                "permission_confirmed": "true",
                "website": "spam",
            },
        )
        response = admin_get(client, "/admin/suspicious-submissions")

    assert response.status_code == 200
    assert "Suspicious Venue" in response.text
    assert "honeypot_filled" in response.text


def test_quarantined_submission_is_not_crawlable(tmp_path):
    with make_client(tmp_path) as client:
        client.post(
            "/submit-calendar",
            data={
                "organization_name": "Quarantined Venue",
                "calendar_url": "https://quarantine.example/events.ics",
                "contact_email": "owner@example.com",
                "permission_confirmed": "true",
                "form_rendered_at": utc_now().isoformat(),
            },
        )
        source = get_source(client)
        approve_source(client)
        crawl_response = admin_post(client, "/admin/sources/1/crawl")

    assert source.review_status == "quarantined"
    assert crawl_response.status_code == 400


def test_public_submission_is_not_auto_crawlable_or_scheduled(tmp_path):
    with make_client(tmp_path) as client:
        submit_source(client, calendar_url="https://example.com/not-auto.ics")
        admin_response = admin_get(client, "/admin/sources")
        crawl_response = admin_post(client, "/admin/sources/1/crawl")

    assert "Run Crawl" not in admin_response.text
    assert crawl_response.status_code == 400


def test_submit_calendar_page_shows_calendar_submission_options(tmp_path):
    with make_client(tmp_path) as client:
        response = client.get("/submit-calendar")

    assert response.status_code == 200
    assert "Submit Calendar" in response.text
    assert "Send one calendar link" in response.text
    assert "Upload a list of calendar links" in response.text
    assert "Start calendar submission" in response.text
    assert "Upload a calendar list" in response.text
    assert "A spreadsheet with actual event details" in response.text
    assert "Approved events may appear in Music Roadtrip after review." in response.text
    assert "color-scheme: dark" in response.text
    assert 'name="calendar_url"' not in response.text
    assert 'name="upload_file"' not in response.text
    assert "Upload event spreadsheet" in response.text
    assert "CSV/XLSX" not in response.text
    assert "dedupe" not in response.text.lower()
    assert "crawl" not in response.text.lower()
    assert "master registry" not in response.text.lower()


def test_submit_events_page_shows_event_upload_option_only(tmp_path):
    with make_client(tmp_path) as client:
        response = client.get("/submit-events")

    assert response.status_code == 200
    assert "Submit Events" in response.text
    assert "Upload event spreadsheet" in response.text
    assert "event name, date, venue, city, and ticket link" in response.text
    assert "Which option should I choose?" in response.text
    assert "One website calendar link" in response.text
    assert "Approved events may appear in Music Roadtrip after review." in response.text
    assert "brand-logo--hero" in response.text
    assert "/static/images/music-roadtrip-logo-square.png" in response.text
    assert "Do not upload vendor-exported API data" not in response.text
    assert "Licensed provider feeds such as CitySpark and JamBase" not in response.text
    assert "private API Feed Review Workbench" not in response.text
    assert "color-scheme: dark" in response.text
    assert "Start calendar submission" not in response.text
    assert "Upload a calendar list" in response.text
    assert "CSV/XLSX" not in response.text
    assert "event rows" not in response.text.lower()
    assert "staged" not in response.text.lower()
    assert 'name="calendar_url"' not in response.text
    assert 'name="upload_file"' not in response.text


def test_dedicated_submit_pages_load_minimal_forms(tmp_path):
    with make_client(tmp_path) as client:
        calendar = client.get("/submit-calendar/url")
        events_file = client.get("/submit-events/file")
        sources_file = client.get("/submit-calendar/sources-file")

    assert calendar.status_code == 200
    assert "Send one calendar link" in calendar.text
    assert "Calendar link" in calendar.text
    assert "Preferred review frequency" in calendar.text
    assert "Preferred crawl frequency" not in calendar.text
    assert "I confirm I am authorized to submit this calendar." in calendar.text
    assert "brand-logo--header" in calendar.text
    assert "/static/images/music-roadtrip-logo-circle.png" in calendar.text
    assert 'name="calendar_url"' in calendar.text
    assert 'name="authorization_checkbox"' in calendar.text
    assert "Advanced details" in calendar.text
    assert events_file.status_code == 200
    assert "Upload event spreadsheet" in events_file.text
    assert "Event spreadsheet" in events_file.text
    assert "Download event template CSV" in events_file.text
    assert "/templates/events-template.csv" in events_file.text
    assert "Concert events file" not in events_file.text
    assert "category=Concert" not in events_file.text
    assert "event rows" not in events_file.text.lower()
    assert "brand-logo--header" in events_file.text
    assert "/static/images/music-roadtrip-logo-circle.png" in events_file.text
    assert 'name="uploaded_file"' in events_file.text
    assert 'name="authorization_checkbox"' in events_file.text
    assert "Optional details" in events_file.text
    assert sources_file.status_code == 200
    assert "Upload a calendar list" in sources_file.text
    assert "Calendar list spreadsheet" in sources_file.text
    assert "Download calendar list template CSV" in sources_file.text
    assert "dedupe" not in sources_file.text.lower()
    assert "master registry" not in sources_file.text.lower()
    assert "crawl" not in sources_file.text.lower()
    assert "brand-logo--header" in sources_file.text
    assert "/static/images/music-roadtrip-logo-circle.png" in sources_file.text
    assert 'name="uploaded_file"' in sources_file.text
    assert 'name="authorization_checkbox"' in sources_file.text
    assert "Optional details" in sources_file.text


def test_legacy_submit_concert_routes_redirect_to_canonical_intake(tmp_path):
    with make_client(tmp_path) as client:
        landing = client.get("/submit-concerts", follow_redirects=False)
        calendar = client.get("/submit-concerts/calendar", follow_redirects=False)
        events_file = client.get(
            "/submit-concerts/events-file",
            follow_redirects=False,
        )
        sources_file = client.get(
            "/submit-concerts/calendar-sources-file",
            follow_redirects=False,
        )

    assert landing.status_code == 303
    assert landing.headers["location"] == "/submit-events"
    assert calendar.status_code == 303
    assert calendar.headers["location"] == "/submit-calendar/url"
    assert events_file.status_code == 303
    assert events_file.headers["location"] == "/submit-events/file"
    assert sources_file.status_code == 303
    assert sources_file.headers["location"] == "/submit-calendar/sources-file"


def test_minimal_concert_calendar_submission_succeeds_on_dedicated_page(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post(
            "/submit-calendar/url",
            data={
                "organization_name": "Dedicated Calendar Venue",
                "contact_email": "dedicated@example.com",
                "calendar_url": "https://dedicated.example/events",
                "authorization_checkbox": "true",
            },
            follow_redirects=False,
        )
        with client.app.state.SessionLocal() as session:
            master = session.scalars(select(MasterCalendarSource)).first()

    assert response.status_code == 303
    assert master is not None
    assert master.source_name == "Dedicated Calendar Venue"


def test_legacy_master_calendar_source_schema_accepts_public_submission(tmp_path):
    db_path = tmp_path / "test.db"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE calendar_sources (
                id INTEGER NOT NULL,
                organization_name VARCHAR(255) NOT NULL DEFAULT '',
                calendar_url TEXT NOT NULL DEFAULT '',
                contact_email VARCHAR(255) NOT NULL DEFAULT '',
                permission_confirmed BOOLEAN NOT NULL DEFAULT 0,
                status VARCHAR(32) NOT NULL DEFAULT 'pending',
                submitted_at DATETIME,
                created_at DATETIME,
                updated_at DATETIME,
                PRIMARY KEY (id)
            );
            CREATE TABLE master_calendar_sources (
                id INTEGER NOT NULL,
                canonical_url TEXT NOT NULL,
                canonical_url_hash VARCHAR(64) NOT NULL,
                original_url TEXT NOT NULL,
                domain VARCHAR(255),
                source_name VARCHAR(255) NOT NULL,
                organization_name VARCHAR(255) NOT NULL,
                source_type VARCHAR(64) NOT NULL DEFAULT 'unknown',
                expected_category VARCHAR(64) NOT NULL DEFAULT 'Concert',
                status VARCHAR(32) NOT NULL DEFAULT 'pending',
                review_status VARCHAR(32) NOT NULL DEFAULT 'pending_review',
                risk_score INTEGER NOT NULL DEFAULT 0,
                risk_level VARCHAR(32) NOT NULL DEFAULT 'low',
                risk_flags_json TEXT NOT NULL DEFAULT '[]',
                first_seen_at DATETIME,
                last_seen_at DATETIME,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                PRIMARY KEY (id)
            );
            CREATE UNIQUE INDEX ix_master_calendar_sources_canonical_url_hash
            ON master_calendar_sources (canonical_url_hash);
            """
        )

    app = create_app(
        Settings(
            database_url=f"sqlite:///{db_path}",
            admin_password_hash=DEV_ADMIN_PASSWORD_HASH,
            session_secret_key="test-session-secret",
        )
    )
    with TestClient(app, base_url="http://testserver") as client:
        response = client.post(
            "/submit-concerts/calendar",
            data={
                "organization_name": "Legacy Calendar Venue",
                "contact_email": "legacy@example.com",
                "calendar_url": "https://legacy.example/events",
                "authorization_checkbox": "true",
            },
            follow_redirects=False,
        )
        with client.app.state.SessionLocal() as session:
            master = session.scalars(select(MasterCalendarSource)).first()
            columns = [
                row[1]
                for row in session.execute(
                    text("PRAGMA table_info(master_calendar_sources)")
                )
            ]

    assert response.status_code == 303
    assert master is not None
    assert master.source_name == "Legacy Calendar Venue"
    assert "organization_name" not in columns


def test_advanced_concert_calendar_fields_are_accepted(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post(
            "/submit-calendar/url",
            data={
                "organization_name": "Advanced Calendar Venue",
                "contact_name": "Calendar Owner",
                "contact_email": "advanced@example.com",
                "calendar_name": "Advanced Shows",
                "calendar_url": "https://advanced.example/events",
                "city": "Memphis",
                "state": "TN",
                "country": "US",
                "region_or_market": "Memphis",
                "crawl_frequency": "weekly",
                "notes": "Advanced public page submission.",
                "permission_confirmed": "true",
            },
            follow_redirects=False,
        )
        with client.app.state.SessionLocal() as session:
            master = session.scalars(select(MasterCalendarSource)).first()

    assert response.status_code == 303
    assert master is not None
    assert master.source_name == "Advanced Shows"
    assert master.city == "Memphis"
    assert master.crawl_frequency == "weekly"


def test_single_calendar_url_submission_creates_master_source(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post(
            "/submit-calendar/url",
            data={
                "organization_name": "Master Venue",
                "contact_name": "Owner",
                "contact_email": "owner@master.example",
                "calendar_name": "Master Venue Calendar",
                "calendar_url": "https://master.example/events/",
                "city": "Memphis",
                "state": "TN",
                "country": "US",
                "region_or_market": "Memphis",
                "crawl_frequency": "weekly",
                "permission_confirmed": "true",
            },
            follow_redirects=False,
        )
        with client.app.state.SessionLocal() as session:
            masters = list(session.scalars(select(MasterCalendarSource)).all())
            claims = list(session.scalars(select(CalendarSourceSubmission)).all())

    assert response.status_code == 303
    assert len(masters) == 1
    assert masters[0].source_name == "Master Venue Calendar"
    assert masters[0].expected_category == "Concert"
    assert masters[0].status == "pending"
    assert masters[0].review_status == "pending_review"
    assert len(claims) == 1
    assert claims[0].master_calendar_source_id == masters[0].id


def test_duplicate_calendar_url_dedupes_master_and_adds_claim(tmp_path):
    with make_client(tmp_path) as client:
        for organization, url in [
            ("Venue One", "https://Venue.com/events/?utm_source=email"),
            ("Venue Two", "https://venue.com/events/"),
        ]:
            response = client.post(
                "/submit-calendar/url",
                data={
                    "organization_name": organization,
                    "contact_email": (
                        f"{organization.lower().replace(' ', '')}@example.com"
                    ),
                    "calendar_url": url,
                    "permission_confirmed": "true",
                },
                follow_redirects=False,
            )
            assert response.status_code == 303
        with client.app.state.SessionLocal() as session:
            masters = list(session.scalars(select(MasterCalendarSource)).all())
            claims = list(session.scalars(select(CalendarSourceSubmission)).all())

    assert len(masters) == 1
    assert len(claims) == 2
    assert masters[0].canonical_url == "https://venue.com/events"


def test_tracking_params_are_removed_during_canonicalization():
    canonical, canonical_hash = canonicalize_calendar_url(
        "https://Venue.com/events/?utm_source=email&gclid=123&view=month"
    )
    alternate, alternate_hash = canonicalize_calendar_url(
        "https://venue.com/events?view=month"
    )

    assert canonical == "https://venue.com/events?view=month"
    assert canonical == alternate
    assert canonical_hash == alternate_hash


def test_template_downloads(tmp_path):
    with make_client(tmp_path) as client:
        calendar_csv = client.get("/templates/calendar-sources-template.csv")
        calendar_xlsx = client.get("/templates/calendar-sources-template.xlsx")
        concert_csv = client.get("/templates/concert-events-template.csv")
        concert_xlsx = client.get("/templates/concert-events-template.xlsx")
        events_csv = client.get("/templates/events-template.csv")
        events_xlsx = client.get("/templates/events-template.xlsx")

    assert calendar_csv.status_code == 200
    assert b"Organization Name,Calendar Name,Calendar URL" in calendar_csv.content
    assert calendar_xlsx.status_code == 200
    assert calendar_xlsx.content.startswith(b"PK")
    assert concert_csv.status_code == 200
    assert b"Category,Event Name,Headliner" in concert_csv.content
    assert concert_xlsx.status_code == 200
    assert concert_xlsx.content.startswith(b"PK")
    assert events_csv.status_code == 200
    assert b"Category,Event Name,Headliner" in events_csv.content
    assert events_xlsx.status_code == 200
    assert events_xlsx.content.startswith(b"PK")


def test_valid_calendar_source_csv_upload_stages_rows(tmp_path):
    content = csv_upload(CALENDAR_SOURCE_HEADERS, [valid_calendar_source_row()])
    with make_client(tmp_path) as client:
        upload_calendar_sources(client, content)
        with client.app.state.SessionLocal() as session:
            batch = session.get(ImportBatch, 1)
            rows = list(session.scalars(select(StagedCalendarSource)).all())

    assert batch is not None
    assert batch.submission_type == "calendar_sources_file"
    assert batch.valid_row_count == 1
    assert len(rows) == 1
    assert rows[0].expected_category == "Concert"
    assert rows[0].dedupe_status == "new"


def test_valid_calendar_source_xlsx_upload_stages_rows(tmp_path):
    content = xlsx_upload(CALENDAR_SOURCE_HEADERS, [valid_calendar_source_row()])
    with make_client(tmp_path) as client:
        upload_calendar_sources(client, content, filename="calendar-sources.xlsx")
        with client.app.state.SessionLocal() as session:
            batch = session.get(ImportBatch, 1)
            row = session.scalars(select(StagedCalendarSource)).first()

    assert batch is not None
    assert batch.file_type == "xlsx"
    assert row is not None
    assert row.validation_status == "valid"


def test_calendar_source_upload_public_alias_accepts_uploaded_file(tmp_path):
    content = csv_upload(CALENDAR_SOURCE_HEADERS, [valid_calendar_source_row()])
    with make_client(tmp_path) as client:
        response = client.post(
            "/submit-concerts/calendar-sources-file",
            data={
                "organization_name": "Source Upload Org",
                "contact_email": "sources@example.com",
                "authorization_checkbox": "true",
            },
            files={"uploaded_file": ("calendar-sources.csv", content, "text/csv")},
            follow_redirects=False,
        )
        with client.app.state.SessionLocal() as session:
            batch = session.get(ImportBatch, 1)

    assert response.status_code == 303
    assert response.headers["location"] == (
        "/submit-calendar/thanks?batch_id=1&submission_kind=calendar-list"
    )
    assert batch is not None
    assert batch.submission_type == "calendar_sources_file"


def test_duplicate_calendar_source_upload_marks_duplicate_rows(tmp_path):
    rows = [
        valid_calendar_source_row(**{"Calendar URL": "https://dup.example/events/"}),
        valid_calendar_source_row(
            **{
                "Organization Name": "Duplicate Venue",
                "Calendar URL": "https://DUP.example/events/?utm_campaign=test",
                "Contact Email": "claim@example.com",
            }
        ),
    ]
    content = csv_upload(CALENDAR_SOURCE_HEADERS, rows)
    with make_client(tmp_path) as client:
        upload_calendar_sources(client, content)
        with client.app.state.SessionLocal() as session:
            staged = list(
                session.scalars(
                    select(StagedCalendarSource).order_by(
                        StagedCalendarSource.row_number
                    )
                ).all()
            )
            batch = session.get(ImportBatch, 1)

    assert batch is not None
    assert batch.duplicate_row_count == 1
    assert [row.dedupe_status for row in staged] == ["new", "duplicate_within_file"]
    assert staged[1].validation_status == "valid"


def test_valid_concert_event_csv_upload_stages_rows(tmp_path):
    content = csv_upload(CONCERT_EVENT_HEADERS, [valid_concert_row()])
    with make_client(tmp_path) as client:
        upload_concert_events(client, content)
        with client.app.state.SessionLocal() as session:
            batch = session.get(ImportBatch, 1)
            row = session.scalars(select(StagedEvent)).first()

    assert batch is not None
    assert batch.submission_type == "concert_events_file"
    assert batch.valid_row_count == 1
    assert row is not None
    assert row.validation_status == "valid"
    assert row.category == "Concert"
    assert row.zip_code == "38103"


def test_valid_concert_event_xlsx_upload_stages_rows(tmp_path):
    content = xlsx_upload(CONCERT_EVENT_HEADERS, [valid_concert_row()])
    with make_client(tmp_path) as client:
        upload_concert_events(client, content, filename="concert-events.xlsx")
        with client.app.state.SessionLocal() as session:
            batch = session.get(ImportBatch, 1)
            row = session.scalars(select(StagedEvent)).first()

    assert batch is not None
    assert batch.file_type == "xlsx"
    assert row is not None
    assert row.event_name == "River Stage Night"


def test_concert_event_upload_public_alias_accepts_uploaded_file(tmp_path):
    content = csv_upload(CONCERT_EVENT_HEADERS, [valid_concert_row()])
    with make_client(tmp_path) as client:
        response = client.post(
            "/submit-concerts/events-file",
            data={
                "organization_name": "Upload Org",
                "contact_email": "upload@example.com",
                "authorization_checkbox": "true",
            },
            files={"uploaded_file": ("concert-events.csv", content, "text/csv")},
            follow_redirects=False,
        )
        with client.app.state.SessionLocal() as session:
            batch = session.get(ImportBatch, 1)

    assert response.status_code == 303
    assert response.headers["location"] == (
        "/submit-events/thanks?batch_id=1&submission_kind=events"
    )
    assert batch is not None
    assert batch.submission_type == "concert_events_file"


def test_missing_required_headers_are_rejected(tmp_path):
    content = csv_upload(["Event Name"], [{"Event Name": "Missing Headers"}])
    with make_client(tmp_path) as client:
        response = client.post(
            "/submit-concerts/concert-events-file",
            data={
                "organization_name": "Upload Org",
                "contact_email": "upload@example.com",
            },
            files={"upload_file": ("bad.csv", content, "text/csv")},
        )

    assert response.status_code == 400
    assert "Missing required headers" in response.text


def test_blank_category_normalizes_to_concert(tmp_path):
    content = csv_upload(CONCERT_EVENT_HEADERS, [valid_concert_row(Category="")])
    with make_client(tmp_path) as client:
        upload_concert_events(client, content)
        with client.app.state.SessionLocal() as session:
            row = session.scalars(select(StagedEvent)).first()

    assert row is not None
    assert row.category == "Concert"
    assert row.validation_status == "valid"


def test_non_concert_category_is_invalid(tmp_path):
    content = csv_upload(
        CONCERT_EVENT_HEADERS,
        [valid_concert_row(Category="Workshop")],
    )
    with make_client(tmp_path) as client:
        upload_concert_events(client, content)
        with client.app.state.SessionLocal() as session:
            row = session.scalars(select(StagedEvent)).first()

    assert row is not None
    assert row.validation_status == "invalid"
    assert "non_concert_category" in row.validation_errors


def test_missing_event_name_is_invalid(tmp_path):
    content = csv_upload(
        CONCERT_EVENT_HEADERS,
        [valid_concert_row(**{"Event Name": ""})],
    )
    with make_client(tmp_path) as client:
        upload_concert_events(client, content)
        with client.app.state.SessionLocal() as session:
            row = session.scalars(select(StagedEvent)).first()

    assert row is not None
    assert row.validation_status == "invalid"
    assert "event_name_missing" in row.validation_errors


def test_missing_headliner_is_invalid(tmp_path):
    content = csv_upload(CONCERT_EVENT_HEADERS, [valid_concert_row(Headliner="")])
    with make_client(tmp_path) as client:
        upload_concert_events(client, content)
        with client.app.state.SessionLocal() as session:
            row = session.scalars(select(StagedEvent)).first()

    assert row is not None
    assert row.validation_status == "invalid"
    assert "headliner_missing" in row.validation_errors


def test_missing_address_and_coordinates_is_invalid(tmp_path):
    content = csv_upload(
        CONCERT_EVENT_HEADERS,
        [valid_concert_row(**{"Venue Address": "", "Latitude": "", "Longitude": ""})],
    )
    with make_client(tmp_path) as client:
        upload_concert_events(client, content)
        with client.app.state.SessionLocal() as session:
            row = session.scalars(select(StagedEvent)).first()

    assert row is not None
    assert row.validation_status == "invalid"
    assert "venue_address_or_coordinates_missing" in row.validation_errors


def test_social_media_main_image_url_is_invalid(tmp_path):
    content = csv_upload(
        CONCERT_EVENT_HEADERS,
        [valid_concert_row(**{"Main Image URL": "https://instagram.com/p/show"})],
    )
    with make_client(tmp_path) as client:
        upload_concert_events(client, content)
        with client.app.state.SessionLocal() as session:
            row = session.scalars(select(StagedEvent)).first()

    assert row is not None
    assert row.validation_status == "invalid"
    assert "main_image_social_media_url" in row.validation_errors


def test_approving_valid_staged_concert_rows_creates_concert_events(tmp_path):
    content = csv_upload(CONCERT_EVENT_HEADERS, [valid_concert_row()])
    with make_client(tmp_path) as client:
        upload_concert_events(client, content)
        response = admin_post(
            client,
            "/admin/import-batches/1/approve-valid-rows",
            follow_redirects=True,
        )
        events_response = admin_get(client, "/admin/events")
        with client.app.state.SessionLocal() as session:
            events = list(session.scalars(select(Event)).all())

    assert response.status_code == 200
    assert len(events) == 1
    assert events[0].category == "Concert"
    assert events[0].record_type == "event"
    assert events[0].source_type == "file_upload"
    assert events[0].import_batch_id == 1
    assert "River Stage Night" in events_response.text


def test_approving_valid_staged_calendar_source_rows_creates_master_sources(tmp_path):
    content = csv_upload(CALENDAR_SOURCE_HEADERS, [valid_calendar_source_row()])
    with make_client(tmp_path) as client:
        upload_calendar_sources(client, content)
        response = admin_post(
            client,
            "/admin/import-batches/1/approve-valid-rows",
            follow_redirects=True,
        )
        with client.app.state.SessionLocal() as session:
            masters = list(session.scalars(select(MasterCalendarSource)).all())
            claims = list(session.scalars(select(CalendarSourceSubmission)).all())

    assert response.status_code == 200
    assert len(masters) == 1
    assert masters[0].expected_category == "Concert"
    assert masters[0].status == "pending"
    assert masters[0].review_status == "pending_review"
    assert len(claims) == 1


def test_invalid_staged_rows_are_not_approved(tmp_path):
    content = csv_upload(
        CONCERT_EVENT_HEADERS,
        [valid_concert_row(**{"Event Name": ""})],
    )
    with make_client(tmp_path) as client:
        upload_concert_events(client, content)
        admin_post(client, "/admin/import-batches/1/approve-valid-rows")
        with client.app.state.SessionLocal() as session:
            events = list(session.scalars(select(Event)).all())

    assert events == []


def test_high_risk_staged_rows_are_not_crawlable_without_explicit_approval(tmp_path):
    content = csv_upload(
        CALENDAR_SOURCE_HEADERS,
        [
            valid_calendar_source_row(
                **{
                    "Calendar URL": "https://risk.example/events",
                    "Notes": "buy now crypto casino free money",
                }
            )
        ],
    )
    with make_client(tmp_path) as client:
        response = client.post(
            "/submit-concerts/calendar-sources-file",
            data={
                "organization_name": "Risk Upload",
                "contact_email": "risk@example.com",
                "website": "filled",
            },
            files={"upload_file": ("calendar-sources.csv", content, "text/csv")},
            follow_redirects=False,
        )
        with client.app.state.SessionLocal() as session:
            batch = session.get(ImportBatch, 1)
            masters_before = list(session.scalars(select(MasterCalendarSource)).all())
        approve = admin_post(
            client,
            "/admin/import-batches/1/approve-valid-rows",
            follow_redirects=False,
        )
        with client.app.state.SessionLocal() as session:
            masters_after = list(session.scalars(select(MasterCalendarSource)).all())

    assert response.status_code == 303
    assert batch is not None
    assert batch.review_status in {"quarantined", "blocked"}
    assert masters_before == []
    assert approve.status_code == 303
    assert masters_after == []


def test_existing_ics_events_normalize_as_concert(tmp_path):
    def fetcher(url: str) -> FetchResult:
        return FetchResult(
            http_status_code=200,
            content_type="text/calendar",
            raw_response_body=SAMPLE_ICS,
        )

    with make_client(tmp_path) as client:
        submit_source(client, calendar_url="https://example.com/sample.ics")
        approve_source(client)
        client.app.state.fetch_calendar_url = fetcher
        admin_post(client, "/admin/sources/1/crawl", follow_redirects=True)
        with client.app.state.SessionLocal() as session:
            events = list(session.scalars(select(Event)).all())

    assert events
    assert {event.category for event in events} == {"Concert"}
    assert {event.record_type for event in events} == {"event"}
    assert {event.source_type for event in events} == {"ics"}


def test_admin_master_and_import_pages_load(tmp_path):
    with make_client(tmp_path) as client:
        source_response = admin_get(client, "/admin/master-calendar-sources")
        imports_response = admin_get(client, "/admin/import-batches")

    assert source_response.status_code == 200
    assert "Master Calendar Sources" in source_response.text
    assert "Show filters" in source_response.text
    assert "<details class=\"filter-drawer\">" in source_response.text
    assert "Run all due" in source_response.text
    assert imports_response.status_code == 200
    assert "Import Batches" in imports_response.text


def test_preview_routes_require_admin_authentication(tmp_path):
    with make_client(tmp_path) as client:
        response = client.get("/preview", follow_redirects=False)
        public_response = client.get("/submit-concerts")

    assert response.status_code == 303
    assert response.headers["location"].startswith("/admin/login")
    assert public_response.status_code == 200


def test_authenticated_preview_pages_load(tmp_path):
    with make_client(tmp_path) as client:
        create_preview_event(client)
        login_admin(client)
        responses = [
            client.get("/preview"),
            client.get("/preview/events"),
            client.get("/preview/events/1"),
            client.get("/preview/venues"),
            client.get("/preview/venues/1"),
            client.get("/preview/quality"),
        ]

    assert all(response.status_code == 200 for response in responses)
    assert "preview-header" in responses[0].text
    assert "brand-logo--header" in responses[0].text
    assert "/static/images/music-roadtrip-logo-circle.png" in responses[0].text
    assert "Preview Home" in responses[1].text
    assert '<aside class="admin-sidebar"' not in responses[1].text
    assert "Visual QA Preview" in responses[0].text
    assert "Music Events Preview" in responses[1].text
    assert "Direct Preview Event" in responses[2].text
    assert "Direct Preview Venue" in responses[4].text


def test_emergency_accessibility_smoke_routes_load(tmp_path):
    public_paths = [
        "/submit-calendar",
        "/submit-calendar/url",
        "/submit-calendar/sources-file",
        "/submit-events",
        "/submit-events/file",
        "/submit-concerts",
        "/submit-concerts/calendar",
        "/submit-concerts/events-file",
        "/submit-concerts/calendar-sources-file",
        "/admin/login",
    ]
    authenticated_paths = [
        "/admin/dashboard",
        "/admin/master-calendar-sources",
        "/admin/api-feeds",
        "/admin/image-candidates",
        "/preview",
        "/preview/events",
        "/preview/quality",
    ]
    with make_client(tmp_path) as client:
        public_responses = [client.get(path) for path in public_paths]
        invalid_login = client.post(
            "/admin/login",
            data={"username": "admin", "password": "wrong"},
        )
        valid_login = client.post(
            "/admin/login",
            data={"username": "admin", "password": "admin"},
            follow_redirects=False,
        )
        authenticated_responses = [client.get(path) for path in authenticated_paths]

    assert [response.status_code for response in public_responses] == [200] * len(
        public_paths
    )
    assert invalid_login.status_code == 401
    assert "Invalid admin username or password." in invalid_login.text
    assert valid_login.status_code == 303
    assert valid_login.headers["location"] == "/admin/dashboard"
    assert [response.status_code for response in authenticated_responses] == [
        200
    ] * len(authenticated_paths)


def test_preview_venues_filter_drawer_renders_top_level_categories(tmp_path):
    with make_client(tmp_path) as client:
        response = admin_get(client, "/preview/venues")
        drawer = venue_filter_drawer_html(response.text)

    assert response.status_code == 200
    assert "Filters" in drawer
    for category in [
        "Music Site",
        "Bars &amp; Lounges",
        "Cultural",
        "Food &amp; Bev",
        "Shopping",
        "Visitor &amp; Travel",
        "Lodging",
    ]:
        assert category in drawer
    assert "Concert" not in drawer


def test_preview_venues_music_site_category_shows_subcategories(tmp_path):
    with make_client(tmp_path) as client:
        response = admin_get(client, "/preview/venues?category=Music%20Site")
        drawer = venue_filter_drawer_html(response.text)

    assert response.status_code == 200
    assert "Festivals" in drawer
    assert "Recording Studios" in drawer
    assert "Radio Stations" in drawer
    assert "Music Education" in drawer
    assert "Dance Clubs" in drawer
    assert "Venues" in drawer


def test_preview_venues_lodging_category_shows_subcategories(tmp_path):
    with make_client(tmp_path) as client:
        response = admin_get(client, "/preview/venues?category=Lodging")
        drawer = venue_filter_drawer_html(response.text)

    assert response.status_code == 200
    assert "Music Hotels" in drawer
    assert "Music Camping" in drawer


def test_preview_venues_bars_category_works_without_subcategories(tmp_path):
    with make_client(tmp_path) as client:
        response = admin_get(client, "/preview/venues?category=Bars%20%26%20Lounges")
        drawer = venue_filter_drawer_html(response.text)

    assert response.status_code == 200
    assert "Bars &amp; Lounges" in drawer
    assert "No subcategories yet." in drawer


def test_preview_venue_filtering_by_category_works(tmp_path):
    with make_client(tmp_path) as client:
        create_preview_event(
            client,
            title="Music Site Filter Event",
            venue_key="music-site-filter-venue",
            venue_name="Music Site Filter Venue",
            venue_category="Music Site",
            venue_subcategory="Venues",
        )
        create_preview_event(
            client,
            title="Lodging Filter Event",
            venue_key="lodging-filter-venue",
            venue_name="Lodging Filter Venue",
            venue_category="Lodging",
            venue_subcategory="Music Hotels",
        )
        response = admin_get(client, "/preview/venues?category=Lodging")

    assert response.status_code == 200
    assert "Lodging Filter Venue" in response.text
    assert "Music Site Filter Venue" not in response.text


def test_preview_venue_filtering_by_subcategory_works(tmp_path):
    with make_client(tmp_path) as client:
        create_preview_event(
            client,
            title="Hotel Subcategory Event",
            venue_key="hotel-subcategory-venue",
            venue_name="Hotel Subcategory Venue",
            venue_category="Lodging",
            venue_subcategory="Music Hotels",
        )
        create_preview_event(
            client,
            title="Camping Subcategory Event",
            venue_key="camping-subcategory-venue",
            venue_name="Camping Subcategory Venue",
            venue_category="Lodging",
            venue_subcategory="Music Camping",
        )
        response = admin_get(
            client,
            "/preview/venues?category=Lodging&subcategory=Music%20Hotels",
        )

    assert response.status_code == 200
    assert "Hotel Subcategory Venue" in response.text
    assert "Camping Subcategory Venue" not in response.text


def test_preview_venues_reset_filters_returns_full_venue_list(tmp_path):
    with make_client(tmp_path) as client:
        create_preview_event(
            client,
            title="Reset Music Event",
            venue_key="reset-music-venue",
            venue_name="Reset Music Venue",
            venue_category="Music Site",
            venue_subcategory="Venues",
        )
        create_preview_event(
            client,
            title="Reset Lodging Event",
            venue_key="reset-lodging-venue",
            venue_name="Reset Lodging Venue",
            venue_category="Lodging",
            venue_subcategory="Music Hotels",
        )
        filtered = admin_get(client, "/preview/venues?category=Lodging")
        reset = admin_get(client, "/preview/venues")

    assert "Reset filters" in filtered.text
    assert "Reset Lodging Venue" in filtered.text
    assert "Reset Music Venue" not in filtered.text
    assert "Reset Lodging Venue" in reset.text
    assert "Reset Music Venue" in reset.text


def test_preview_events_lists_approved_concert_events_only(tmp_path):
    rows = [
        valid_concert_row(**{"Event Name": "Approved Preview Concert"}),
        valid_concert_row(**{"Event Name": ""}),
    ]
    with make_client(tmp_path) as client:
        upload_concert_events(client, csv_upload(CONCERT_EVENT_HEADERS, rows))
        admin_post(client, "/admin/import-batches/1/approve-valid-rows")
        response = admin_get(client, "/preview/events")

    assert response.status_code == 200
    assert "Approved Preview Concert" in response.text
    assert "Untitled Concert" not in response.text
    assert '<span class="badge success">Event</span>' in response.text


def test_preview_event_detail_shows_ticket_link_when_present(tmp_path):
    row = valid_concert_row(
        **{"Tickets Link": "https://tickets.example/river-stage-night"}
    )
    with make_client(tmp_path) as client:
        approve_concert_upload(client, [row])
        response = admin_get(client, "/preview/events/1")

    assert response.status_code == 200
    assert "https://tickets.example/river-stage-night" in response.text
    assert "missing ticket link" not in response.text


def test_preview_event_detail_warns_when_ticket_is_missing(tmp_path):
    with make_client(tmp_path) as client:
        approve_concert_upload(client, [valid_concert_row()])
        response = admin_get(client, "/preview/events/1")

    assert response.status_code == 200
    assert "Tickets missing" in response.text
    assert "missing ticket link" in response.text


def test_preview_event_detail_warns_when_image_is_missing(tmp_path):
    row = valid_concert_row(**{"Main Image URL": ""})
    with make_client(tmp_path) as client:
        approve_concert_upload(client, [row])
        response = admin_get(client, "/preview/events/1")

    assert response.status_code == 200
    assert "Event Image QA" in response.text
    assert "missing image" in response.text


def test_preview_event_detail_flags_social_media_image_url(tmp_path):
    with make_client(tmp_path) as client:
        event_id = create_preview_event(
            client,
            title="Social Image Preview Event",
            main_image_url="https://instagram.com/p/show",
        )
        response = admin_get(client, f"/preview/events/{event_id}")

    assert response.status_code == 200
    assert "social image URL" in response.text
    assert "https://instagram.com/p/show" in response.text


def test_preview_event_detail_flags_vendor_tracking_parameter(tmp_path):
    vendor_ticket_url = "https://tickets.example/show?aff=" + "city" + "spark"
    with make_client(tmp_path) as client:
        event_id = create_preview_event(
            client,
            title="Tracking Preview Event",
            tickets_link=vendor_ticket_url,
        )
        response = admin_get(client, f"/preview/events/{event_id}")

    assert response.status_code == 200
    assert "suspicious/vendor tracking" in response.text
    assert vendor_ticket_url in response.text


def test_preview_reminder_ics_route_returns_calendar(tmp_path):
    with make_client(tmp_path) as client:
        event_id = create_preview_event(client, title="Reminder Preview Event")
        response = admin_get(client, f"/preview/events/{event_id}/reminder.ics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/calendar")
    assert "BEGIN:VCALENDAR" in response.text
    assert "SUMMARY:Reminder Preview Event" in response.text


def test_preview_venue_profiles_group_multiple_events(tmp_path):
    rows = [
        valid_concert_row(
            **{
                "Event Name": "First Venue Preview",
                "Start Date": "2026-08-01",
                "Start Time": "20:00",
                "Event URL": "https://venue.example/events/first",
            }
        ),
        valid_concert_row(
            **{
                "Event Name": "Second Venue Preview",
                "Start Date": "2026-09-01",
                "Start Time": "19:00",
                "Event URL": "https://venue.example/events/second",
            }
        ),
    ]
    with make_client(tmp_path) as client:
        approve_concert_upload(client, rows)
        list_response = admin_get(client, "/preview/venues")
        detail_response = admin_get(client, "/preview/venues/1")

    assert list_response.status_code == 200
    assert "2 upcoming events" in list_response.text
    assert detail_response.status_code == 200
    assert "Events at this venue" in detail_response.text
    first_index = detail_response.text.index("First Venue Preview")
    second_index = detail_response.text.index("Second Venue Preview")
    assert first_index < second_index


def test_preview_quality_dashboard_shows_counts(tmp_path):
    rows = [
        valid_concert_row(**{"Event Name": "Clean Quality Preview"}),
        valid_concert_row(
            **{
                "Event Name": "Missing Quality Preview Image",
                "Event URL": "https://venue.example/events/missing-image",
                "Main Image URL": "",
            }
        ),
    ]
    with make_client(tmp_path) as client:
        approve_concert_upload(client, rows)
        response = admin_get(client, "/preview/quality")

    assert response.status_code == 200
    assert "Data Quality Dashboard" in response.text
    assert "Total approved events" in response.text
    assert "Events missing images" in response.text
    assert "Events missing ticket links" in response.text


def test_preview_quality_dashboard_shows_zero_numeric_counts(tmp_path):
    with make_client(tmp_path) as client:
        response = admin_get(client, "/preview/quality")

    assert response.status_code == 200
    assert '<span class="quality-number">0</span>' in response.text


def test_preview_radius_filter_uses_venue_coordinates(tmp_path):
    with make_client(tmp_path) as client:
        near_id = create_preview_event(
            client,
            title="Nearby Preview Event",
            venue_key="near-preview-venue",
            latitude=35.1495,
            longitude=-90.049,
        )
        create_preview_event(
            client,
            title="Missing Coordinate Preview Event",
            venue_key="missing-coordinate-venue",
            latitude=None,
            longitude=None,
        )
        login_admin(client)
        response = client.get(
            "/preview/events",
            params={
                "latitude": "35.1495",
                "longitude": "-90.049",
                "radius_miles": "1",
            },
        )
        detail_response = client.get(f"/preview/events/{near_id}")

    assert response.status_code == 200
    assert "Nearby Preview Event" in response.text
    assert "Missing Coordinate Preview Event" not in response.text
    assert detail_response.status_code == 200


def test_image_direct_asset_detection_flags_pages_and_content_type():
    assert is_likely_direct_image_asset("https://images.example/show.jpg")
    assert is_likely_direct_image_asset(
        "https://assets.example/no-extension",
        "image/webp",
    )
    assert not is_likely_direct_image_asset("https://instagram.com/p/show")
    assert not is_likely_direct_image_asset("https://venue.example/events/show")
    assert not is_likely_direct_image_asset(
        "https://images.example/show.jpg",
        "text/html",
    )


def test_jambase_photo_rescue_discovers_provider_payload_images():
    inputs = provider_image_inputs_from_raw(
        "jambase",
        {
            "name": "Headliner Night",
            "image": "https://images.example/jambase-event.jpg",
            "x-promoImage": "https://images.example/jambase-admat.jpg",
            "performer": [
                {
                    "name": "Headliner Band",
                    "x-isHeadliner": True,
                    "image": "https://images.example/headliner-band.jpg",
                }
            ],
            "location": {
                "name": "Test Venue",
                "image": "https://images.example/venue-stage.jpg",
            },
        },
        event_id=123,
        source_url="https://jambase.example/events/123",
        source_chain_json="[]",
        headliner="Headliner Band",
    )
    paths = {item.source_payload_path: item for item in inputs}

    assert "jambase.image" in paths
    assert "jambase.x-promoImage" in paths
    assert "jambase.performer[0].image" in paths
    assert "jambase.location.image" in paths
    assert paths["jambase.performer[0].image"].rescue_source == (
        "provider_artist_image"
    )
    assert paths["jambase.x-promoImage"].source_evidence_only is True
    assert paths["jambase.x-promoImage"].can_be_final_image is False


def test_cityspark_photo_rescue_discovers_primary_media_and_logo_evidence():
    inputs = provider_image_inputs_from_raw(
        "cityspark",
        {
            "primaryImage": {
                "largeImageUrl": "https://images.example/cityspark-large.jpg",
                "mediumImageUrl": "https://images.example/cityspark-medium.jpg",
                "smallImageUrl": "https://images.example/cityspark-small.jpg",
            },
            "media": [{"url": "https://images.example/cityspark-media.jpg"}],
            "links": [{"logoUrl": "https://images.example/provider-logo.png"}],
        },
        event_id=456,
        source_url="https://vendor.example/events/456",
        source_chain_json="[]",
        headliner="CitySpark Demo Artist",
    )
    paths = {item.source_payload_path: item for item in inputs}

    assert paths["cityspark.primaryImage.largeImageUrl"].rescue_priority == 60
    assert paths["cityspark.primaryImage.smallImageUrl"].rescue_priority == 115
    assert paths["cityspark.media[0]"].rescue_source == "provider_event_image"
    assert paths["cityspark.links[0].logoUrl"].source_evidence_only is True
    assert paths["cityspark.links[0].logoUrl"].image_role == "logo"


def test_photo_rescue_prefers_artist_image_over_provider_admat(tmp_path):
    with make_client(tmp_path) as client:
        event_id = create_preview_event(client, title="Photo Rescue Artist Event")
        promo_id = create_image_candidate_for_test(
            client,
            event_id=event_id,
            image_url="https://images.example/provider-admat.jpg",
            image_role="admat",
            rescue_source="provider_promo_image",
            source_payload_path="jambase.x-promoImage",
            source_evidence_only=True,
            can_be_final_image=False,
        )
        artist_id = create_image_candidate_for_test(
            client,
            event_id=event_id,
            image_url="https://images.example/headliner-press.jpg",
            image_role="artist_press",
            rescue_source="provider_artist_image",
            source_payload_path="jambase.performer[0].image",
        )
        with client.app.state.SessionLocal() as session:
            result = run_event_photo_rescue(session, event_id)
            event = session.get(Event, event_id)
            promo = session.get(ImageCandidate, promo_id)

    assert result is not None
    assert event is not None
    assert event.selected_image_candidate_id == artist_id
    assert event.image_selection_reason.startswith("photo_rescue_selected_artist_image")
    assert promo is not None
    assert promo.can_be_final_image is False
    assert "source evidence only" in promo.rejection_reasons


def test_admin_can_run_photo_rescue_for_recently_approved_events(tmp_path):
    with make_client(tmp_path) as client:
        event_id = create_preview_event(client, title="Recent Rescue Event")
        create_image_candidate_for_test(
            client,
            event_id=event_id,
            image_url="https://images.example/recent-rescue-artist.jpg",
            image_role="artist_press",
            rescue_source="provider_artist_image",
        )
        response = admin_post(
            client,
            "/admin/image-candidates/photo-rescue/recent-approved",
        )
        with client.app.state.SessionLocal() as session:
            event = session.get(Event, event_id)

    assert response.status_code == 303
    assert event is not None
    assert event.selected_main_image_url == (
        "https://images.example/recent-rescue-artist.jpg"
    )
    assert event.image_selection_reason.startswith("photo_rescue_selected_artist_image")


def test_photo_rescue_blocks_social_graphic_evidence_only_candidate(tmp_path):
    with make_client(tmp_path) as client:
        event_id = create_preview_event(client, title="Social Evidence Event")
        create_image_candidate_for_test(
            client,
            event_id=event_id,
            image_url="https://images.example/social-flyer.jpg",
            image_role="social_screenshot",
            rescue_source="social_graphic_reference",
            source_payload_path="provider.socialGraphic",
            source_evidence_only=True,
            can_be_final_image=False,
        )
        with client.app.state.SessionLocal() as session:
            result = run_event_photo_rescue(session, event_id)
            event = session.get(Event, event_id)
            candidate = session.scalars(select(ImageCandidate)).first()

    assert result is not None
    assert event is not None
    assert event.selected_main_image_url is None
    assert event.image_status == "needs_review"
    assert candidate is not None
    assert candidate.source_evidence_only is True
    assert candidate.can_be_final_image is False


def test_photo_rescue_ocr_hook_is_not_configured_and_makes_no_external_call(tmp_path):
    with make_client(tmp_path) as client:
        event_id = create_preview_event(client, title="OCR Placeholder Event")
        candidate_id = create_image_candidate_for_test(client, event_id=event_id)
        with client.app.state.SessionLocal() as session:
            candidate = session.get(ImageCandidate, candidate_id)
            assert candidate is not None
            result = extract_text_from_image_candidate(candidate)

    assert result == {
        "ocr_status": "not_configured",
        "text_detected": "unknown",
        "extracted_text": None,
        "confidence": None,
    }


def test_admin_image_candidates_page_renders_review_board(tmp_path):
    with make_client(tmp_path) as client:
        event_id = create_preview_event(client, title="Review Board Image Event")
        create_image_candidate_for_test(
            client,
            event_id=event_id,
            image_url="https://images.example/review-board.jpg",
        )
        response = admin_get(client, "/admin/image-candidates")

    assert response.status_code == 200
    assert "Needs approval" in response.text
    assert "Selected pending approval" in response.text
    assert "Generic provider photos" in response.text
    assert "Photo Rescue" in response.text
    assert "review-board" in response.text
    assert "Accept visual" in response.text
    assert "Approve clearance" in response.text
    assert "Replace selected" in response.text


def test_brand_logos_are_ui_only_not_image_candidates_or_fallbacks(tmp_path):
    logo_paths = {
        "/static/images/music-roadtrip-logo-square.png",
        "/static/images/music-roadtrip-logo-circle.png",
        "/static/images/music-roadtrip-logo-plate.png",
    }
    with make_client(tmp_path) as client:
        client.get("/submit-events")
        client.get("/submit-calendar")
        admin_get(client, "/admin/image-candidates")
        with client.app.state.SessionLocal() as session:
            candidates = list(session.scalars(select(ImageCandidate)).all())
            events = list(session.scalars(select(Event)).all())
            venues = list(session.scalars(select(EventVenue)).all())

    assert candidates == []
    assert all(event.main_image_url not in logo_paths for event in events)
    assert all(event.selected_main_image_url not in logo_paths for event in events)
    assert all(venue.main_image_url not in logo_paths for venue in venues)
    assert all(venue.selected_main_image_url not in logo_paths for venue in venues)


def test_brand_asset_docs_preserve_image_qa_guardrails():
    docs = Path("docs/design/brand/music-roadtrip-brand-assets.md").read_text(
        encoding="utf-8",
    )

    assert "These logos are UI assets only." in docs
    assert "Create `image_candidates`" in docs
    assert "Store these logos as `selected_main_image_url`" in docs


def test_image_candidate_preflight_flags_broken_non_image_and_low_resolution(tmp_path):
    with make_client(tmp_path) as client:
        event_id = create_preview_event(client, title="Broken Image Metadata Event")
        candidate_id = create_image_candidate_for_test(
            client,
            event_id=event_id,
            image_url="https://images.example/broken.jpg",
            width=300,
            height=200,
        )
        with client.app.state.SessionLocal() as session:
            candidate = mark_candidate_preflight_result(
                session,
                candidate_id,
                is_accessible=False,
                content_type="text/html",
                width=300,
                height=200,
            )

    assert candidate is not None
    assert "broken or inaccessible image" in candidate.qa_flags
    assert "content-type mismatch" in candidate.qa_flags
    assert "low resolution image" in candidate.qa_flags
    assert "not direct image asset" in candidate.qa_flags


def test_repeated_provider_placeholder_image_is_flagged(tmp_path):
    with make_client(tmp_path) as client:
        first_event_id = create_preview_event(
            client,
            title="Placeholder Artist One",
            venue_key="placeholder-one",
        )
        second_event_id = create_preview_event(
            client,
            title="Placeholder Artist Two",
            venue_key="placeholder-two",
        )
        create_image_candidate_for_test(
            client,
            event_id=first_event_id,
            image_url="https://images.example/default/event-placeholder.jpg",
        )
        second_candidate_id = create_image_candidate_for_test(
            client,
            event_id=second_event_id,
            image_url="https://images.example/default/event-placeholder.jpg",
        )
        with client.app.state.SessionLocal() as session:
            candidate = session.get(ImageCandidate, second_candidate_id)

    assert candidate is not None
    assert candidate.appears_stock_or_placeholder is True
    assert "stock_placeholder_candidate" in candidate.qa_flags


def test_same_venue_fallback_image_reused_for_same_venue_is_allowed(tmp_path):
    with make_client(tmp_path) as client:
        event_id = create_preview_event(client, title="Venue Image Reuse Event")
        venue_id = venue_id_for_event(client, event_id)
        create_image_candidate_for_test(
            client,
            venue_id=venue_id,
            image_url="https://images.example/venue-action.jpg",
            source_type="venue",
            image_role="venue_live",
        )
        second_candidate_id = create_image_candidate_for_test(
            client,
            venue_id=venue_id,
            image_url="https://images.example/venue-action.jpg",
            source_type="venue",
            image_role="venue_live",
        )
        with client.app.state.SessionLocal() as session:
            candidate = session.get(ImageCandidate, second_candidate_id)

    assert candidate is not None
    assert candidate.appears_stock_or_placeholder is False


def test_same_image_reused_across_unrelated_artists_is_flagged(tmp_path):
    with make_client(tmp_path) as client:
        first_event_id = create_preview_event(
            client,
            title="Unrelated Artist One",
            venue_key="unrelated-one",
        )
        second_event_id = create_preview_event(
            client,
            title="Unrelated Artist Two",
            venue_key="unrelated-two",
        )
        create_image_candidate_for_test(
            client,
            event_id=first_event_id,
            image_url="https://images.example/shared-provider-photo.jpg",
        )
        second_candidate_id = create_image_candidate_for_test(
            client,
            event_id=second_event_id,
            image_url="https://images.example/shared-provider-photo.jpg",
        )
        with client.app.state.SessionLocal() as session:
            candidate = session.get(ImageCandidate, second_candidate_id)

    assert candidate is not None
    assert candidate.appears_stock_or_placeholder is True


def test_image_role_ranking_orders_artist_event_venue_and_stock(tmp_path):
    roles = [
        "artist_live",
        "artist_press",
        "event_provider",
        "venue_live",
        "venue_exterior",
        "stock_placeholder",
    ]
    with make_client(tmp_path) as client:
        event_id = create_preview_event(client, title="Image Ranking Event")
        candidate_ids = [
            create_image_candidate_for_test(
                client,
                event_id=event_id,
                image_url=f"https://images.example/{role}.jpg",
                source_type="manual",
                image_role=role,
                clearance_status="approved",
            )
            for role in roles
        ]
        with client.app.state.SessionLocal() as session:
            scores = [
                session.get(ImageCandidate, candidate_id).quality_score
                for candidate_id in candidate_ids
            ]

    assert scores == sorted(scores, reverse=True)


def test_poster_flyer_candidate_cannot_be_auto_selected(tmp_path):
    with make_client(tmp_path) as client:
        event_id = create_preview_event(client, title="Poster Image Event")
        create_image_candidate_for_test(
            client,
            event_id=event_id,
            image_url="https://images.example/show-poster.jpg",
            image_role="poster",
        )
        with client.app.state.SessionLocal() as session:
            event = select_best_event_image(session, event_id)

    assert event is not None
    assert event.selected_main_image_url is None
    assert event.image_status == "needs_review"


def test_needs_approval_artist_live_image_is_selected_immediately(tmp_path):
    with make_client(tmp_path) as client:
        event_id = create_preview_event(client, title="Pending Artist Live Event")
        candidate_id = create_image_candidate_for_test(
            client,
            event_id=event_id,
            image_url="https://images.example/pending-artist-live.jpg",
            image_role="artist_live",
        )
        with client.app.state.SessionLocal() as session:
            event = select_best_event_image(session, event_id)

    assert event is not None
    assert event.selected_image_candidate_id == candidate_id
    assert event.selected_main_image_url == "https://images.example/pending-artist-live.jpg"
    assert event.image_status == "selected_pending_approval"
    assert event.image_clearance_status == "needs_approval"
    assert event.image_selection_reason == "best_available_used_pending_approval"


def test_needs_approval_artist_press_image_is_selected_immediately(tmp_path):
    with make_client(tmp_path) as client:
        event_id = create_preview_event(client, title="Pending Artist Press Event")
        candidate_id = create_image_candidate_for_test(
            client,
            event_id=event_id,
            image_url="https://images.example/pending-artist-press.jpg",
            image_role="artist_press",
        )
        with client.app.state.SessionLocal() as session:
            event = select_best_event_image(session, event_id)

    assert event is not None
    assert event.selected_image_candidate_id == candidate_id
    assert event.image_status == "selected_pending_approval"
    assert event.image_clearance_status == "needs_approval"


def test_needs_approval_clean_provider_image_is_selected_immediately(tmp_path):
    with make_client(tmp_path) as client:
        event_id = create_preview_event(client, title="Pending Provider Image Event")
        candidate_id = create_image_candidate_for_test(
            client,
            event_id=event_id,
            image_url="https://images.example/pending-provider.jpg",
            image_role="event_provider",
            source_type="provider",
        )
        with client.app.state.SessionLocal() as session:
            event = select_best_event_image(session, event_id)

    assert event is not None
    assert event.selected_image_candidate_id == candidate_id
    assert event.image_status == "selected_pending_approval"
    assert event.image_role == "event_provider"


def test_clearance_rejected_blocks_selection(tmp_path):
    with make_client(tmp_path) as client:
        event_id = create_preview_event(client, title="Rejected Clearance Image Event")
        create_image_candidate_for_test(
            client,
            event_id=event_id,
            image_url="https://images.example/rejected-clearance.jpg",
            image_role="artist_live",
            clearance_status="rejected",
        )
        with client.app.state.SessionLocal() as session:
            event = select_best_event_image(session, event_id)

    assert event is not None
    assert event.selected_main_image_url is None
    assert event.image_status == "needs_review"


def test_social_media_image_url_blocks_selection(tmp_path):
    with make_client(tmp_path) as client:
        event_id = create_preview_event(client, title="Social Blocked Image Event")
        create_image_candidate_for_test(
            client,
            event_id=event_id,
            image_url="https://instagram.com/p/show",
            image_role="artist_live",
            content_type=None,
        )
        with client.app.state.SessionLocal() as session:
            event = select_best_event_image(session, event_id)

    assert event is not None
    assert event.selected_main_image_url is None
    assert event.image_status == "needs_review"


def test_text_heavy_and_logo_candidates_block_automatic_selection(tmp_path):
    with make_client(tmp_path) as client:
        text_event_id = create_preview_event(client, title="Text Heavy Image Event")
        text_candidate_id = create_image_candidate_for_test(
            client,
            event_id=text_event_id,
            image_url="https://images.example/text-heavy.jpg",
            image_role="event_provider",
        )
        logo_event_id = create_preview_event(
            client,
            title="Logo Only Image Event",
            venue_key="logo-only-venue",
        )
        create_image_candidate_for_test(
            client,
            event_id=logo_event_id,
            image_url="https://images.example/logo-only.jpg",
            image_role="logo",
        )
        with client.app.state.SessionLocal() as session:
            update_candidate_review(
                session,
                text_candidate_id,
                reviewed_by="tester",
                qa_updates={"has_text_detected": True},
            )
            text_event = select_best_event_image(session, text_event_id)
            logo_event = select_best_event_image(session, logo_event_id)

    assert text_event is not None
    assert text_event.selected_main_image_url is None
    assert logo_event is not None
    assert logo_event.selected_main_image_url is None


def test_watermark_candidate_requires_manual_acceptance(tmp_path):
    with make_client(tmp_path) as client:
        event_id = create_preview_event(client, title="Watermark Image Event")
        candidate_id = create_image_candidate_for_test(
            client,
            event_id=event_id,
            image_url="https://images.example/watermark-live.jpg",
            image_role="artist_live",
            clearance_status="approved",
        )
        with client.app.state.SessionLocal() as session:
            update_candidate_review(
                session,
                candidate_id,
                reviewed_by="tester",
                qa_updates={"has_watermark_detected": True},
            )
            blocked_event = select_best_event_image(session, event_id)
            assert blocked_event is not None
            blocked_selected_url = blocked_event.selected_main_image_url
            update_candidate_review(
                session,
                candidate_id,
                reviewed_by="tester",
                candidate_status="accepted",
                clearance_status="approved",
            )
            accepted_event = select_best_event_image(session, event_id)

    assert blocked_selected_url is None
    assert accepted_event is not None
    assert accepted_event.selected_image_candidate_id == candidate_id
    assert accepted_event.image_status == "accepted"


def test_accepted_manual_image_is_not_overwritten_by_lower_ranked_candidate(tmp_path):
    with make_client(tmp_path) as client:
        event_id = create_preview_event(client, title="Manual Image Lock Event")
        manual_candidate_id = create_image_candidate_for_test(
            client,
            event_id=event_id,
            image_url="https://images.example/manual-artist-live.jpg",
            source_type="manual",
            image_role="artist_live",
            clearance_status="approved",
            candidate_status="accepted",
        )
        with client.app.state.SessionLocal() as session:
            select_best_event_image(session, event_id)
        create_image_candidate_for_test(
            client,
            event_id=event_id,
            image_url="https://images.example/provider-image.jpg",
            source_type="provider",
            image_role="event_provider",
            clearance_status="approved",
        )
        with client.app.state.SessionLocal() as session:
            event = select_best_event_image(session, event_id)

    assert event is not None
    assert event.selected_image_candidate_id == manual_candidate_id
    assert event.selected_main_image_url == "https://images.example/manual-artist-live.jpg"


def test_venue_fallback_is_used_only_for_linked_venue(tmp_path):
    with make_client(tmp_path) as client:
        fallback_event_id = create_preview_event(
            client,
            title="Fallback Image Event",
            venue_key="fallback-venue",
        )
        no_fallback_event_id = create_preview_event(
            client,
            title="No Fallback Event",
            venue_key="no-fallback-venue",
        )
        venue_id = venue_id_for_event(client, fallback_event_id)
        venue_candidate_id = create_image_candidate_for_test(
            client,
            venue_id=venue_id,
            image_url="https://images.example/correct-venue-live.jpg",
            source_type="venue",
            image_role="venue_live",
            clearance_status="approved",
            candidate_status="accepted",
        )
        with client.app.state.SessionLocal() as session:
            fallback_event = select_best_event_image(session, fallback_event_id)
            no_fallback_event = select_best_event_image(session, no_fallback_event_id)

    assert fallback_event is not None
    assert fallback_event.image_status == "venue_fallback"
    assert fallback_event.selected_image_candidate_id == venue_candidate_id
    assert no_fallback_event is not None
    assert no_fallback_event.selected_main_image_url is None
    assert no_fallback_event.image_status == "missing"


def test_venue_fallback_can_be_selected_pending_approval(tmp_path):
    with make_client(tmp_path) as client:
        event_id = create_preview_event(
            client,
            title="Pending Venue Fallback Event",
            venue_key="pending-fallback-venue",
        )
        venue_id = venue_id_for_event(client, event_id)
        candidate_id = create_image_candidate_for_test(
            client,
            venue_id=venue_id,
            image_url="https://images.example/pending-venue-live.jpg",
            source_type="venue",
            image_role="venue_live",
        )
        with client.app.state.SessionLocal() as session:
            event = select_best_event_image(session, event_id)

    assert event is not None
    assert event.image_status == "venue_fallback"
    assert event.image_clearance_status == "needs_approval"
    assert event.selected_image_candidate_id == candidate_id
    assert "venue_fallback" in event.image_quality_flags
    assert "used_pending_approval" in event.image_quality_flags


def test_generic_provider_placeholder_is_not_selected_as_final_image(tmp_path):
    with make_client(tmp_path) as client:
        event_id = create_preview_event(client, title="Generic Provider Image Event")
        create_image_candidate_for_test(
            client,
            event_id=event_id,
            image_url="https://images.example/jambase-default.jpg",
            image_role="event_provider",
        )
        with client.app.state.SessionLocal() as session:
            event = select_best_event_image(session, event_id)

    assert event is not None
    assert event.selected_main_image_url is None
    assert event.image_status == "needs_review"


def test_ui_placeholder_is_not_stored_when_no_image_candidate(tmp_path):
    with make_client(tmp_path) as client:
        event_id = create_preview_event(
            client,
            title="Missing Candidate Image Event",
            main_image_url=None,
        )
        with client.app.state.SessionLocal() as session:
            event = select_best_event_image(session, event_id)

    assert event is not None
    assert event.selected_main_image_url is None
    assert event.image_status == "missing"


def test_unknown_clearance_keeps_candidate_reviewable_not_rejected(tmp_path):
    with make_client(tmp_path) as client:
        event_id = create_preview_event(client, title="Unknown Clearance Event")
        candidate_id = create_image_candidate_for_test(
            client,
            event_id=event_id,
            image_url="https://images.example/unknown-clearance.jpg",
            clearance_status="unknown",
        )
        with client.app.state.SessionLocal() as session:
            candidate = session.get(ImageCandidate, candidate_id)

    assert candidate is not None
    assert candidate.clearance_status == "needs_approval"
    assert candidate.candidate_status == "pending_review"
    assert "clearance rejected" not in candidate.rejection_reasons


def test_admin_can_mark_image_clearance_approved_and_rejected(tmp_path):
    with make_client(tmp_path) as client:
        event_id = create_preview_event(client, title="Clearance Workflow Event")
        candidate_id = create_image_candidate_for_test(client, event_id=event_id)
        with client.app.state.SessionLocal() as session:
            approved = set_candidate_clearance(
                session,
                candidate_id,
                "approved",
                "tester",
            )
            assert approved is not None
            rejected = set_candidate_clearance(
                session,
                candidate_id,
                "rejected",
                "tester",
            )

    assert rejected is not None
    assert rejected.clearance_status == "rejected"
    assert "clearance rejected" in rejected.rejection_reasons


def test_admin_can_mark_selected_pending_image_clearance_approved(tmp_path):
    with make_client(tmp_path) as client:
        event_id = create_preview_event(client, title="Selected Clearance Event")
        candidate_id = create_image_candidate_for_test(
            client,
            event_id=event_id,
            image_url="https://images.example/selected-clearance.jpg",
            image_role="artist_live",
        )
        with client.app.state.SessionLocal() as session:
            pending_event = select_best_event_image(session, event_id)
            assert pending_event is not None
            assert pending_event.image_status == "selected_pending_approval"
            set_candidate_clearance(session, candidate_id, "approved", "tester")
            event = session.get(Event, event_id)

    assert event is not None
    assert event.image_status == "accepted"
    assert event.image_clearance_status == "approved"
    assert event.selected_image_candidate_id == candidate_id


def test_admin_can_replace_selected_pending_approval_image(tmp_path):
    with make_client(tmp_path) as client:
        event_id = create_preview_event(client, title="Replace Selected Image Event")
        old_candidate_id = create_image_candidate_for_test(
            client,
            event_id=event_id,
            image_url="https://images.example/old-pending.jpg",
            image_role="event_provider",
        )
        new_candidate_id = create_image_candidate_for_test(
            client,
            event_id=event_id,
            image_url="https://images.example/new-pending.jpg",
            image_role="artist_press",
        )
        with client.app.state.SessionLocal() as session:
            selected = select_best_event_image(session, event_id)
            assert selected is not None
            assert selected.selected_image_candidate_id == new_candidate_id
            replaced = select_candidate_for_event(session, old_candidate_id)

    assert replaced is not None
    assert replaced.selected_image_candidate_id == old_candidate_id
    assert replaced.selected_main_image_url == "https://images.example/old-pending.jpg"
    assert replaced.image_status == "selected_pending_approval"


def test_image_candidate_review_requires_admin_auth_and_csrf(tmp_path):
    with make_client(tmp_path) as client:
        event_id = create_preview_event(client, title="Image Auth Event")
        candidate_id = create_image_candidate_for_test(client, event_id=event_id)
        unauth = client.post(
            f"/admin/image-candidates/{candidate_id}/accept",
            follow_redirects=False,
        )
        login_admin(client)
        no_csrf = client.post(
            f"/admin/image-candidates/{candidate_id}/accept",
            follow_redirects=False,
        )

    assert unauth.status_code == 401
    assert no_csrf.status_code == 403


def test_image_candidate_preflight_requires_admin_auth_and_csrf(tmp_path):
    with make_client(tmp_path) as client:
        event_id = create_preview_event(client, title="Image Preflight Auth Event")
        candidate_id = create_image_candidate_for_test(client, event_id=event_id)
        unauth = client.post(
            f"/admin/image-candidates/{candidate_id}/preflight",
            follow_redirects=False,
        )
        login_admin(client)
        no_csrf = client.post(
            f"/admin/image-candidates/{candidate_id}/preflight",
            follow_redirects=False,
        )

    assert unauth.status_code == 401
    assert no_csrf.status_code == 403


def test_preview_shows_image_quality_badges(tmp_path):
    with make_client(tmp_path) as client:
        event_id = create_preview_event(
            client,
            title="Preview Badge Missing Event",
            main_image_url=None,
        )
        response = admin_get(client, f"/preview/events/{event_id}")

    assert response.status_code == 200
    assert "Missing image" in response.text


def test_preview_shows_venue_fallback_and_needs_approval_badges(tmp_path):
    with make_client(tmp_path) as client:
        fallback_event_id = create_preview_event(
            client,
            title="Preview Venue Fallback Event",
            venue_key="preview-fallback-venue",
        )
        venue_id = venue_id_for_event(client, fallback_event_id)
        create_image_candidate_for_test(
            client,
            venue_id=venue_id,
            image_url="https://images.example/preview-venue-live.jpg",
            source_type="venue",
            image_role="venue_live",
            clearance_status="approved",
            candidate_status="accepted",
        )
        approval_event_id = create_preview_event(
            client,
            title="Preview Needs Approval Event",
            venue_key="preview-approval-venue",
        )
        create_image_candidate_for_test(
            client,
            event_id=approval_event_id,
            image_url="https://images.example/approval-artist.jpg",
            source_type="manual",
            image_role="artist_press",
            candidate_status="accepted",
        )
        with client.app.state.SessionLocal() as session:
            select_best_event_image(session, fallback_event_id)
            select_best_event_image(session, approval_event_id)
        fallback_response = admin_get(client, f"/preview/events/{fallback_event_id}")
        approval_response = admin_get(client, f"/preview/events/{approval_event_id}")

    assert "Venue fallback image" in fallback_response.text
    assert "Venue image accepted" in fallback_response.text
    assert "Needs approval" in approval_response.text
    assert "Selected · Needs Approval" in approval_response.text


def test_preview_shows_provider_stock_candidate_badge_and_quality_count(tmp_path):
    with make_client(tmp_path) as client:
        event_id = create_preview_event(client, title="Preview Stock Candidate Event")
        create_image_candidate_for_test(
            client,
            event_id=event_id,
            image_url="https://images.example/provider-stock-placeholder.jpg",
            image_role="event_provider",
        )
        detail_response = admin_get(client, f"/preview/events/{event_id}")
        quality_response = admin_get(client, "/preview/quality")

    assert "Provider stock candidate" in detail_response.text
    assert "Events with provider stock candidates" in quality_response.text
    assert "Events with poster/flyer candidates" in quality_response.text


def test_quality_dashboard_counts_selected_pending_approval_images(tmp_path):
    with make_client(tmp_path) as client:
        event_id = create_preview_event(client, title="Quality Pending Image Event")
        create_image_candidate_for_test(
            client,
            event_id=event_id,
            image_url="https://images.example/quality-pending.jpg",
            image_role="artist_live",
        )
        with client.app.state.SessionLocal() as session:
            select_best_event_image(session, event_id)
        response = admin_get(client, "/preview/quality")

    assert response.status_code == 200
    assert "Events with selected image pending approval" in response.text
    assert "Events with selected image" in response.text
    assert "Events missing usable image" in response.text


def test_api_feed_record_image_candidate_can_be_sent_to_image_qa(tmp_path):
    with make_client(tmp_path) as client:
        admin_post_upload_json(
            client,
            "/admin/api-feeds/manual_json/upload-json",
            api_upload_payload(),
        )
        detail_response = admin_get(client, "/admin/api-feed-records/1")
        create_response = admin_post(
            client,
            "/admin/api-feed-records/1/create-image-candidate",
        )
        with client.app.state.SessionLocal() as session:
            candidates = list(session.scalars(select(ImageCandidate)).all())

    assert detail_response.status_code == 200
    assert "Incoming Provider Image" in detail_response.text
    assert "Direct image asset" in detail_response.text
    assert create_response.status_code == 303
    assert len(candidates) == 1
    assert candidates[0].source_type == "provider"
    assert candidates[0].clearance_status == "needs_approval"


def test_api_feed_approval_creates_provider_image_candidate(tmp_path):
    with make_client(tmp_path) as client:
        admin_post_upload_json(
            client,
            "/admin/api-feeds/manual_json/upload-json",
            api_upload_payload(),
        )
        admin_post(client, "/admin/api-feed-records/1/approve")
        with client.app.state.SessionLocal() as session:
            event = session.get(Event, 1)
            candidates = list(session.scalars(select(ImageCandidate)).all())

    assert event is not None
    assert len(candidates) == 1
    assert candidates[0].event_id == event.id
    assert candidates[0].image_url == "https://images.example/api-demo.jpg"
    assert candidates[0].candidate_status == "pending_review"
    assert event.selected_image_candidate_id == candidates[0].id
    assert event.selected_main_image_url == "https://images.example/api-demo.jpg"
    assert event.image_status == "selected_pending_approval"
    assert event.image_clearance_status == "needs_approval"


def test_image_qa_service_does_not_make_live_spotify_or_serpapi_calls():
    service_source = Path("app/services/image_qa_service.py").read_text(
        encoding="utf-8",
    )

    assert "api.spotify.com" not in service_source
    assert "serpapi.com" not in service_source
    assert "httpx." not in service_source
    assert "requests." not in service_source


def test_event_photo_rescue_service_does_not_make_live_api_calls_or_use_keys():
    service_source = Path("app/services/event_photo_rescue_service.py").read_text(
        encoding="utf-8",
    )

    assert "httpx." not in service_source
    assert "requests." not in service_source
    assert "api_key" not in service_source.lower()
    assert "apikey" not in service_source.lower()


def test_preview_ics_events_create_venue_profiles(tmp_path):
    def fetcher(url: str) -> FetchResult:
        return FetchResult(
            http_status_code=200,
            content_type="text/calendar",
            raw_response_body=SAMPLE_ICS,
        )

    with make_client(tmp_path) as client:
        submit_source(client, calendar_url="https://example.com/sample.ics")
        approve_source(client)
        client.app.state.fetch_calendar_url = fetcher
        admin_post(client, "/admin/sources/1/crawl", follow_redirects=True)
        response = admin_get(client, "/preview/venues")
        with client.app.state.SessionLocal() as session:
            events = list(session.scalars(select(Event)).all())

    assert response.status_code == 200
    assert "Riverfront Music Hall" in response.text
    assert any(event.event_venue_id is not None for event in events)


def test_concert_events_are_not_treated_as_pois_in_preview(tmp_path):
    with make_client(tmp_path) as client:
        approve_concert_upload(client, [valid_concert_row()])
        with client.app.state.SessionLocal() as session:
            event = session.get(Event, 1)
            venue = session.get(EventVenue, 1)

    assert event is not None
    assert venue is not None
    assert event.category == "Concert"
    assert event.record_type == "event"
    assert venue.category == "Music Site"
    assert venue.subcategory == "Venues"


def test_crawl_queue_requires_login(tmp_path):
    with make_client(tmp_path) as client:
        response = client.get("/admin/crawl-queue", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].startswith("/admin/login")


def test_authenticated_admin_can_view_crawl_queue(tmp_path):
    with make_client(tmp_path) as client:
        response = admin_get(client, "/admin/crawl-queue")

    assert response.status_code == 200
    assert "Crawl Queue" in response.text


def test_crawl_queue_shows_approved_crawlable_sources(tmp_path):
    with make_client(tmp_path) as client:
        client.post(
            "/submit-concerts/calendar-url",
            data={
                "organization_name": "Queue Venue",
                "contact_email": "queue@example.com",
                "calendar_url": "https://queue.example/events.ics",
                "crawl_frequency": "weekly",
                "permission_confirmed": "true",
            },
        )
        approve_master_source(client)
        response = admin_get(client, "/admin/crawl-queue")

    assert response.status_code == 200
    assert "Queue Venue" in response.text
    assert "weekly" in response.text
    assert "Never crawled" in response.text


def test_blocked_or_quarantined_sources_do_not_appear_crawlable(tmp_path):
    with make_client(tmp_path) as client:
        client.post(
            "/submit-concerts/calendar-url",
            data={
                "organization_name": "Blocked Queue Venue",
                "contact_email": "blocked@example.com",
                "calendar_url": "https://blocked-queue.example/events.ics",
                "permission_confirmed": "true",
                "website": "bot-filled",
            },
        )
        response = admin_get(client, "/admin/crawl-queue")

    assert response.status_code == 200
    assert "Blocked Queue Venue" not in response.text


def test_bulk_crawl_selected_requires_admin_auth(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post(
            "/admin/master-calendar-sources/bulk-crawl",
            data={"source_ids": "1"},
            follow_redirects=False,
        )

    assert response.status_code == 401


def test_bulk_crawl_selected_requires_csrf(tmp_path):
    with make_client(tmp_path) as client:
        login_admin(client)
        response = client.post(
            "/admin/master-calendar-sources/bulk-crawl",
            data={"source_ids": "1"},
            follow_redirects=False,
        )

    assert response.status_code == 403


def test_bulk_crawl_skips_non_crawlable_sources(tmp_path):
    with make_client(tmp_path) as client:
        client.post(
            "/submit-concerts/calendar-url",
            data={
                "organization_name": "Approved Bulk Venue",
                "contact_email": "approved@example.com",
                "calendar_url": "https://approved-bulk.example/events.ics",
                "permission_confirmed": "true",
            },
        )
        client.post(
            "/submit-concerts/calendar-url",
            data={
                "organization_name": "Pending Bulk Venue",
                "contact_email": "pending@example.com",
                "calendar_url": "https://pending-bulk.example/events.ics",
                "permission_confirmed": "true",
            },
        )
        approve_master_source(client, 1)
        client.app.state.fetch_calendar_url = lambda url: FetchResult(
            http_status_code=200,
            content_type="text/calendar",
            raw_response_body="BEGIN:VCALENDAR\nEND:VCALENDAR",
        )
        response = admin_post_with_source_ids(
            client,
            "/admin/master-calendar-sources/bulk-crawl",
            [1, 2],
        )

    assert response.status_code == 200
    assert "2 selected" in response.text
    assert "1 attempted" in response.text
    assert "1 skipped" in response.text
    assert "Pending Bulk Venue" in response.text
    assert "status=pending" in response.text


def test_bulk_crawl_creates_crawl_runs_for_crawlable_selected_sources(tmp_path):
    with make_client(tmp_path) as client:
        client.post(
            "/submit-concerts/calendar-url",
            data={
                "organization_name": "Crawlable Bulk Venue",
                "contact_email": "crawlable@example.com",
                "calendar_url": "https://crawlable-bulk.example/events.ics",
                "permission_confirmed": "true",
            },
        )
        approve_master_source(client)
        client.app.state.fetch_calendar_url = lambda url: FetchResult(
            http_status_code=200,
            content_type="text/calendar",
            raw_response_body=SAMPLE_ICS,
        )
        response = admin_post_with_source_ids(
            client,
            "/admin/master-calendar-sources/bulk-crawl",
            [1],
        )
        with client.app.state.SessionLocal() as session:
            crawl_run = get_crawl_run(session, 1)
            master = session.get(MasterCalendarSource, 1)

    assert response.status_code == 200
    assert crawl_run is not None
    assert crawl_run.status == "success"
    assert master is not None
    assert master.last_crawled_at is not None
    assert "1 successful" in response.text
    assert "3 events extracted" in response.text


def test_bulk_crawl_summary_counts_success_and_failure(tmp_path):
    def fetcher(url: str) -> FetchResult:
        if "fail" in url:
            return FetchResult(
                http_status_code=500,
                content_type="text/html",
                raw_response_body="nope",
            )
        return FetchResult(
            http_status_code=200,
            content_type="text/calendar",
            raw_response_body="BEGIN:VCALENDAR\nEND:VCALENDAR",
        )

    with make_client(tmp_path) as client:
        for name, url in [
            ("Bulk Success", "https://bulk-success.example/events.ics"),
            ("Bulk Fail", "https://bulk-fail.example/events.ics"),
        ]:
            client.post(
                "/submit-concerts/calendar-url",
                data={
                    "organization_name": name,
                    "contact_email": f"{name.lower().replace(' ', '')}@example.com",
                    "calendar_url": url,
                    "permission_confirmed": "true",
                },
            )
        approve_master_source(client, 1)
        approve_master_source(client, 2)
        client.app.state.fetch_calendar_url = fetcher
        response = admin_post_with_source_ids(
            client,
            "/admin/master-calendar-sources/bulk-crawl",
            [1, 2],
        )

    assert response.status_code == 200
    assert "2 attempted" in response.text
    assert "1 successful" in response.text
    assert "1 failed" in response.text


def test_run_all_due_sources_only_includes_due_approved_sources(tmp_path):
    with make_client(tmp_path) as client:
        for name, url, frequency in [
            ("Due Daily", "https://due-daily.example/events.ics", "daily"),
            ("Manual Source", "https://manual-source.example/events.ics", "manual"),
            ("Pending Daily", "https://pending-daily.example/events.ics", "daily"),
        ]:
            client.post(
                "/submit-concerts/calendar-url",
                data={
                    "organization_name": name,
                    "contact_email": f"{name.lower().replace(' ', '')}@example.com",
                    "calendar_url": url,
                    "crawl_frequency": frequency,
                    "permission_confirmed": "true",
                },
            )
        approve_master_source(client, 1)
        approve_master_source(client, 2)
        client.app.state.fetch_calendar_url = lambda url: FetchResult(
            http_status_code=200,
            content_type="text/calendar",
            raw_response_body="BEGIN:VCALENDAR\nEND:VCALENDAR",
        )
        response = admin_post(
            client,
            "/admin/crawl-queue/run-due",
            follow_redirects=False,
        )

    assert response.status_code == 200
    assert "1 selected" in response.text
    assert "Due Daily" in response.text
    assert "Manual Source" not in response.text
    assert "Pending Daily" not in response.text


def test_import_batch_detail_can_crawl_approved_sources_in_batch(tmp_path):
    content = csv_upload(CALENDAR_SOURCE_HEADERS, [valid_calendar_source_row()])
    with make_client(tmp_path) as client:
        upload_calendar_sources(client, content)
        admin_post(client, "/admin/import-batches/1/approve-valid-rows")
        approve_master_source(client)
        client.app.state.fetch_calendar_url = lambda url: FetchResult(
            http_status_code=200,
            content_type="text/calendar",
            raw_response_body="BEGIN:VCALENDAR\nEND:VCALENDAR",
        )
        detail = admin_get(client, "/admin/import-batches/1")
        response = admin_post(
            client,
            "/admin/import-batches/1/crawl-approved-sources",
        )

    assert "Run crawl for approved sources in this batch" in detail.text
    assert response.status_code == 200
    assert "Import Batch #1 Crawl Summary" in response.text
    assert "1 attempted" in response.text


def test_crawl_frequency_values_and_next_due_computation(tmp_path):
    assert CRAWL_FREQUENCIES == ["manual", "daily", "weekly", "biweekly", "monthly"]
    assert normalize_crawl_frequency("Weekly") == "weekly"
    assert normalize_crawl_frequency("unknown") == "manual"

    with make_client(tmp_path) as client:
        submit_source(client, calendar_url="https://frequency.example/events.ics")
        approve_source(client)
        client.app.state.fetch_calendar_url = lambda url: FetchResult(
            http_status_code=200,
            content_type="text/calendar",
            raw_response_body="BEGIN:VCALENDAR\nEND:VCALENDAR",
        )
        admin_post(client, "/admin/sources/1/crawl")
        with client.app.state.SessionLocal() as session:
            crawl_run = get_crawl_run(session, 1)
            assert crawl_run is not None
            due_at = next_crawl_due_at("weekly", crawl_run)

    assert due_at == as_utc_datetime(crawl_run.fetched_at) + timedelta(days=7)
    assert is_due_for_crawl("manual", crawl_run) is False


def test_master_calendar_sources_page_shows_crawl_metadata(tmp_path):
    with make_client(tmp_path) as client:
        client.post(
            "/submit-concerts/calendar-url",
            data={
                "organization_name": "Metadata Venue",
                "contact_email": "metadata@example.com",
                "calendar_url": "https://metadata.example/events.ics",
                "crawl_frequency": "weekly",
                "permission_confirmed": "true",
            },
        )
        approve_master_source(client)
        client.app.state.fetch_calendar_url = lambda url: FetchResult(
            http_status_code=200,
            content_type="text/calendar",
            raw_response_body=SAMPLE_ICS,
        )
        admin_post_with_source_ids(
            client,
            "/admin/master-calendar-sources/bulk-crawl",
            [1],
        )
        response = admin_get(client, "/admin/master-calendar-sources?status=approved")

    assert response.status_code == 200
    assert "Metadata Venue" in response.text
    assert "weekly" in response.text
    assert "success" in response.text
    assert "3" in response.text
    assert "Run crawl for selected sources" in response.text


def test_trusted_submitter_badge_displays_on_master_sources(tmp_path):
    with make_client(tmp_path) as client:
        with client.app.state.SessionLocal() as session:
            session.add(
                TrustedSubmitter(
                    email="trusted-master@example.com",
                    notes="Known tourism board.",
                )
            )
            session.commit()
        client.post(
            "/submit-concerts/calendar-url",
            data={
                "organization_name": "Trusted Master Venue",
                "contact_email": "trusted-master@example.com",
                "calendar_url": "https://trusted-master.example/events.ics",
                "permission_confirmed": "true",
            },
        )
        approve_master_source(client)
        response = admin_get(client, "/admin/master-calendar-sources")

    assert response.status_code == 200
    assert "Trusted Master Venue" in response.text
    assert "Trusted" in response.text


def api_upload_payload() -> bytes:
    return json.dumps(
        [
            {
                "id": "api-demo-1",
                "event_name": "API Demo Concert",
                "headliner": "The API Fixtures",
                "start_datetime": "2026-09-20T20:00:00-05:00",
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
                "main_image_url": "https://images.example/api-demo.jpg",
            }
        ]
    ).encode("utf-8")


def test_api_feeds_requires_login(tmp_path):
    with make_client(tmp_path) as client:
        response = client.get("/admin/api-feeds", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].startswith("/admin/login")


def test_authenticated_admin_can_view_api_feed_provider_cards(tmp_path):
    with make_client(tmp_path) as client:
        response = admin_get(client, "/admin/api-feeds")

    assert response.status_code == 200
    assert "API Feed Review Workbench" in response.text
    assert "provider-card" in response.text
    assert "JamBase" in response.text
    assert "CitySpark" in response.text
    assert "Licensed Vendor Feed" in response.text
    assert "Workbench Open" in response.text
    assert "Live Calls Off" in response.text
    assert "Permanent Allowed" in response.text
    assert "Credentials Missing" in response.text
    assert "Temporary Review Only" not in response.text
    assert "48h Retention" not in response.text
    assert "Contract Required" not in response.text
    assert "permanent approval" not in response.text.lower()
    assert "Disabled" not in response.text
    assert "Spotify" in response.text
    assert "SerpAPI" in response.text
    assert "Manual JSON" in response.text
    assert "/admin/api-feeds/jambase/pipeline" in response.text


def test_provider_pipeline_pages_require_login(tmp_path):
    cityspark_key = "city" + "spark"
    paths = [
        "/admin/api-feeds/jambase/pipeline",
        f"/admin/api-feeds/{cityspark_key}/pipeline",
        "/admin/api-feed-records/1/lineage",
    ]
    with make_client(tmp_path) as client:
        responses = [
            client.get(path, follow_redirects=False)
            for path in paths
        ]

    assert [response.status_code for response in responses] == [303, 303, 303]
    assert all(
        response.headers["location"].startswith("/admin/login")
        for response in responses
    )


def test_authenticated_admin_can_open_provider_pipeline_pages(tmp_path):
    cityspark_key = "city" + "spark"
    providers = {
        "jambase": "JamBase",
        cityspark_key: "CitySpark",
        "manual_json": "Manual JSON",
        "spotify": "Spotify",
        "serpapi": "SerpAPI",
    }
    with make_client(tmp_path) as client:
        responses = {
            key: admin_get(client, f"/admin/api-feeds/{key}/pipeline")
            for key in providers
        }

    for key, label in providers.items():
        assert responses[key].status_code == 200
        assert "Provider Pipeline" in responses[key].text
        assert label in responses[key].text
        assert "Workbench Open" in responses[key].text
        assert "Credential values are redacted" in responses[key].text


def test_provider_pipeline_content_documents_mapping_and_qa(tmp_path):
    cityspark_key = "city" + "spark"
    with make_client(tmp_path) as client:
        jambase = admin_get(client, "/admin/api-feeds/jambase/pipeline")
        cityspark = admin_get(client, f"/admin/api-feeds/{cityspark_key}/pipeline")
        manual = admin_get(client, "/admin/api-feeds/manual_json/pipeline")
        spotify = admin_get(client, "/admin/api-feeds/spotify/pipeline")
        serpapi = admin_get(client, "/admin/api-feeds/serpapi/pipeline")

    assert "API 3.1.0" in jambase.text
    assert "GET https://api.data.jambase.com/v3/events" in jambase.text
    assert "https://www.jambase.com/jb-api/v1" not in jambase.text
    assert "apikey=REDACTED" in jambase.text
    assert "perPage=100" in jambase.text
    assert "eventType=concerts" in jambase.text
    assert "GET /streams" in jambase.text
    assert "GET /geographies/cities" in jambase.text
    assert "GET /lookups/event-data-sources" in jambase.text
    assert "GET /genres" in jambase.text
    assert "offers[].url" in jambase.text
    assert "identifier" in jambase.text
    assert "source_record_id" in jambase.text
    assert "event_lifecycle_status" in jambase.text
    assert "previous_start_datetime" in jambase.text
    assert "x-promoImage" in jambase.text
    assert "Mapping Table" in jambase.text
    assert "Image QA Rules" in jambase.text
    assert "Concert is always an event category" in jambase.text

    assert "POST https://api.cityspark.com/v2/event/search" in cityspark.text
    assert "ticketUrl" in cityspark.text
    assert "Licensed Vendor Feed" in cityspark.text
    assert "Permanent Allowed" in cityspark.text
    assert "Credentials Missing" in cityspark.text
    assert "Live Calls Off" in cityspark.text
    assert "No page scraping or hidden API use" in cityspark.text
    assert "paid licensed vendor API feed" in cityspark.text
    assert "Contract Required" not in cityspark.text
    assert "Temporary Review Only" not in cityspark.text
    assert "48h Retention" not in cityspark.text
    assert "permanent approval" not in cityspark.text.lower()

    assert "Accepted JSON shapes" in manual.text
    assert "object with events array" in manual.text
    assert "enrichment provider only" in spotify.text
    assert "not a primary event feed" in spotify.text
    assert "enrichment provider only" in serpapi.text
    assert "suggestions or candidates" in serpapi.text


def test_provider_mapping_page_renders_full_mapping_table(tmp_path):
    with make_client(tmp_path) as client:
        response = admin_get(client, "/admin/api-feeds/jambase/mapping")

    assert response.status_code == 200
    assert "Provider Mapping" in response.text
    assert "identifier" in response.text
    assert "source_record_id / provider_event_id" in response.text
    assert "Required/Optional" in response.text
    assert "Example Value" in response.text


def test_provider_pipeline_exports_are_redacted_and_structured(tmp_path):
    cityspark_key = "city" + "spark"
    with make_client(tmp_path) as client:
        jambase_md = admin_get(client, "/admin/api-feeds/jambase/pipeline.md")
        jambase_json = admin_get(client, "/admin/api-feeds/jambase/pipeline.json")
        cityspark_md = admin_get(
            client,
            f"/admin/api-feeds/{cityspark_key}/pipeline.md",
        )
        cityspark_json = admin_get(
            client,
            f"/admin/api-feeds/{cityspark_key}/pipeline.json",
        )

    assert jambase_md.status_code == 200
    assert "text/markdown" in jambase_md.headers["content-type"]
    assert "# JamBase Provider Pipeline" in jambase_md.text
    assert "## Mapping Table" in jambase_md.text
    assert "## Cleanup Rules" in jambase_md.text
    assert "REDACTED" in jambase_md.text

    assert jambase_json.status_code == 200
    assert "application/json" in jambase_json.headers["content-type"]
    data = json.loads(jambase_json.text)
    assert data["provider"]["key"] == "jambase"
    assert data["provider"]["api_version"] == "3.1.0"
    assert data["provider"]["api_title"] == "JamBase Concert Data API"
    assert data["request_example"]["base_url"] == "https://api.data.jambase.com/v3"
    assert data["request_example"]["query_params"]["apikey"] == "REDACTED"
    assert data["request_example"]["query_params"]["eventType"] == "concerts"
    assert "GET /venues" in data["supported_endpoints"]
    assert "GET /genres" in data["supported_endpoints"]
    assert data["mapping_rules"][0]["provider_field"] == "identifier"
    assert data["sample_normalized_object"]["category"] == "Concert"
    assert data["sample_normalized_object"]["record_type"] == "event"

    assert cityspark_md.status_code == 200
    assert "CitySpark Provider Pipeline" in cityspark_md.text
    assert "REDACTED" in cityspark_md.text
    assert cityspark_json.status_code == 200
    cityspark_data = json.loads(cityspark_json.text)
    assert cityspark_data["provider"]["name"] == "CitySpark"
    assert cityspark_data["request_example"]["headers"]["X-API-Key"] == "REDACTED"
    assert "Licensed Vendor Feed" in cityspark_data["provider"]["compliance_badges"]
    assert "Permanent Allowed" in cityspark_data["provider"]["compliance_badges"]
    assert (
        "Credentials Missing"
        in cityspark_data["provider"]["compliance_badges"]
    )
    assert "Contract Required" not in cityspark_data["provider"]["compliance_badges"]

    combined = "\n".join(
        [
            jambase_md.text,
            jambase_json.text,
            cityspark_md.text,
            cityspark_json.text,
        ]
    )
    assert ("s" + "k-") not in combined
    assert ("secret" + "-") not in combined.lower()


def test_api_feed_record_lineage_page_shows_record_path(tmp_path):
    with make_client(tmp_path) as client:
        admin_post_upload_json(
            client,
            "/admin/api-feeds/manual_json/upload-json",
            api_upload_payload(),
        )
        response = admin_get(client, "/admin/api-feed-records/1/lineage")

    assert response.status_code == 200
    assert "Record Lineage" in response.text
    assert "Raw Payload" in response.text
    assert "Mapper Output" in response.text
    assert "Ticket QA" in response.text
    assert "Image Candidate QA" in response.text
    assert "Source-Chain Provenance" in response.text
    assert "Venue And POI Boundary" in response.text
    assert "API Demo Concert" in response.text
    assert "Concert remains an event" in response.text


def test_api_feed_record_lineage_links_approved_event(tmp_path):
    with make_client(tmp_path) as client:
        admin_post_upload_json(
            client,
            "/admin/api-feeds/manual_json/upload-json",
            api_upload_payload(),
        )
        admin_post(client, "/admin/api-feed-records/1/approve")
        response = admin_get(client, "/admin/api-feed-records/1/lineage")

    assert response.status_code == 200
    assert "/admin/events/1" in response.text
    assert "/preview/events/1" in response.text
    assert "Created event" in response.text


def test_provider_pipeline_service_does_not_make_live_api_calls():
    service_text = Path("app/services/provider_pipeline_service.py").read_text()

    assert "httpx." not in service_text
    assert "requests." not in service_text
    assert "urllib.request" not in service_text
    assert "aiohttp" not in service_text


def test_live_provider_config_defaults_are_disabled_and_documented():
    settings = Settings()
    env_example = Path(".env.example").read_text()

    assert settings.jambase_live_calls_enabled is False
    assert settings.cityspark_live_calls_enabled is False
    assert settings.jambase_api_key == ""
    assert settings.cityspark_api_key == ""
    assert settings.cityspark_portal_script_id == ""
    assert "JAMBASE_LIVE_CALLS_ENABLED=false" in env_example
    assert "JAMBASE_API_KEY=" in env_example
    assert "CITYSPARK_LIVE_CALLS_ENABLED=false" in env_example
    assert "CITYSPARK_API_KEY=" in env_example
    assert "CITYSPARK_PORTAL_SCRIPT_ID=" in env_example


def test_live_sandbox_routes_require_login_and_csrf(tmp_path):
    cityspark_key = "city" + "spark"
    with make_client(tmp_path) as client:
        login_required = client.get(
            "/admin/api-feeds/jambase/live-sandbox",
            follow_redirects=False,
        )
        login_admin(client)
        no_csrf = client.post(
            f"/admin/api-feeds/{cityspark_key}/live-sandbox",
            data={"limit": "1"},
            follow_redirects=False,
        )

    assert login_required.status_code == 303
    assert login_required.headers["location"].startswith("/admin/login")
    assert no_csrf.status_code == 403


def test_live_sandbox_pages_show_disabled_missing_credential_states(tmp_path):
    cityspark_key = "city" + "spark"
    with make_client(tmp_path) as client:
        jambase = admin_get(client, "/admin/api-feeds/jambase/live-sandbox")
        cityspark = admin_get(client, f"/admin/api-feeds/{cityspark_key}/live-sandbox")

    assert jambase.status_code == 200
    assert "Live Calls Off" in jambase.text
    assert "Credentials Missing" in jambase.text
    assert "apikey=REDACTED" in jambase.text
    assert "Run Live Sandbox" in jambase.text
    assert "disabled" in jambase.text
    assert cityspark.status_code == 200
    assert "Live Calls Off" in cityspark.text
    assert "Credentials Missing" in cityspark.text
    assert "Portal Missing" in cityspark.text
    assert "X-API-Key" in cityspark.text
    assert "REDACTED" in cityspark.text


def test_missing_live_sandbox_credentials_block_without_network(tmp_path):
    fake = FakeProviderHttpClient([])
    with make_client_with_settings(
        tmp_path,
        jambase_live_calls_enabled=True,
        cityspark_live_calls_enabled=True,
    ) as client:
        client.app.state.provider_http_client = fake
        jambase = admin_post(
            client,
            "/admin/api-feeds/jambase/live-sandbox",
            data={"limit": "1"},
            follow_redirects=False,
        )
        cityspark_key = "city" + "spark"
        cityspark = admin_post(
            client,
            f"/admin/api-feeds/{cityspark_key}/live-sandbox",
            data={"limit": "1"},
            follow_redirects=False,
        )
        with client.app.state.SessionLocal() as session:
            run_count = len(list(session.scalars(select(ApiFeedRun)).all()))

    assert jambase.status_code == 303
    assert "credentials" in jambase.headers["location"].lower()
    assert cityspark.status_code == 303
    assert "credentials" in cityspark.headers["location"].lower()
    assert fake.get_calls == []
    assert fake.post_calls == []
    assert run_count == 0


def test_mocked_jambase_live_sandbox_creates_pending_records_and_caps(tmp_path):
    payload = {
        "events": [
            {
                "@type": "Concert",
                "identifier": "jambase:live-1",
                "name": "Live Sandbox JamBase Concert",
                "startDate": "2026-10-10T20:00:00",
                "location": {
                    "name": "Sandbox Hall",
                    "address": {
                        "addressLocality": "Memphis",
                        "addressRegion": {"alternateName": "TN"},
                        "addressCountry": {"identifier": "US"},
                    },
                },
                "performer": [{"name": "Sandbox Artist", "x-isHeadliner": True}],
                "offers": [
                    {
                        "category": "ticketingLinkPrimary",
                        "url": "https://tickets.example/jambase-live-1",
                    }
                ],
            }
        ],
    }
    fake = FakeProviderHttpClient(
        [
            ProviderHttpResult(
                ok=True,
                status_code=200,
                content_type="application/json",
                json_data=payload,
                text_preview="{}",
            )
        ]
    )
    with make_client_with_settings(
        tmp_path,
        jambase_live_calls_enabled=True,
        jambase_api_key="configured-jambase-value",
        jambase_sandbox_max_events=2,
    ) as client:
        client.app.state.provider_http_client = fake
        response = admin_post(
            client,
            "/admin/api-feeds/jambase/live-sandbox",
            data={"limit": "999", "perPage": "999", "eventType": "concerts"},
            follow_redirects=False,
        )
        with client.app.state.SessionLocal() as session:
            run = session.scalars(select(ApiFeedRun)).one()
            records = list(session.scalars(select(ApiFeedRecord)).all())
            event_count = len(list(session.scalars(select(Event)).all()))
            poi_count = len(list(session.scalars(select(PoiLocation)).all()))

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/api-feed-runs/1"
    assert len(fake.get_calls) == 1
    call = fake.get_calls[0]
    assert str(call["url"]).endswith("/events")
    assert "/events/id" not in str(call["url"])
    params = call["params"]
    assert isinstance(params, dict)
    assert params["perPage"] == 100
    assert params["apikey"] == "configured-jambase-value"
    assert run.run_mode == "live_api_sandbox"
    assert run.status == "success"
    assert run.raw_record_count == 1
    assert run.normalized_candidate_count == 1
    assert "REDACTED" in run.request_preview_json
    assert "configured-jambase-value" not in run.request_preview_json
    assert "configured-jambase-value" not in run.parameters_json
    assert len(records) == 1
    assert records[0].review_status == "pending_review"
    assert records[0].category == "Concert"
    assert records[0].record_type == "event"
    assert event_count == 0
    assert poi_count == 0


def test_mocked_cityspark_live_sandbox_creates_pending_records_and_caps(tmp_path):
    cityspark_key = "city" + "spark"
    payload = {
        "EventSeries": [
            {
                "eventId": "cs-live-1",
                "name": "Live Sandbox CitySpark Concert",
                "location": {
                    "locationName": "Licensed Sandbox Room",
                    "address": "100 Sandbox Ave",
                    "city": "Nashville",
                    "state": "TN",
                    "country": "US",
                },
                "instances": [{"start": "2026-11-01T20:00:00-05:00"}],
                "ticketUrl": "https://tickets.example/cityspark-live-1",
                "url": "https://events.example/cityspark-live-1",
            }
        ]
    }
    fake = FakeProviderHttpClient(
        [
            ProviderHttpResult(
                ok=True,
                status_code=200,
                content_type="application/json",
                json_data=payload,
                text_preview="{}",
            )
        ]
    )
    with make_client_with_settings(
        tmp_path,
        cityspark_live_calls_enabled=True,
        cityspark_api_key="configured-cityspark-value",
        cityspark_portal_script_id="portal-123",
        cityspark_sandbox_max_events=3,
    ) as client:
        client.app.state.provider_http_client = fake
        response = admin_post(
            client,
            f"/admin/api-feeds/{cityspark_key}/live-sandbox",
            data={"limit": "999", "pageSize": "999", "searchTerm": "concert"},
            follow_redirects=False,
        )
        with client.app.state.SessionLocal() as session:
            run = session.scalars(select(ApiFeedRun)).one()
            records = list(session.scalars(select(ApiFeedRecord)).all())
            event_count = len(list(session.scalars(select(Event)).all()))
            poi_count = len(list(session.scalars(select(PoiLocation)).all()))

    assert response.status_code == 303
    assert len(fake.post_calls) == 1
    call = fake.post_calls[0]
    assert str(call["url"]).endswith("/v2/event/search")
    assert "/v2/event/details" not in str(call["url"])
    body = call["body"]
    assert isinstance(body, dict)
    assert body["pageSize"] == 200
    assert body["portalScriptId"] == "portal-123"
    headers = call["headers"]
    assert isinstance(headers, dict)
    assert headers["X-API-Key"] == "configured-cityspark-value"
    assert run.provider_key == cityspark_key
    assert run.run_mode == "live_api_sandbox"
    assert "X-API-Key" in run.request_preview_json
    assert "REDACTED" in run.request_preview_json
    assert "configured-cityspark-value" not in run.request_preview_json
    assert "portal-123" not in run.parameters_json
    assert len(records) == 1
    assert records[0].review_status == "pending_review"
    assert records[0].category == "Concert"
    assert records[0].record_type == "event"
    assert event_count == 0
    assert poi_count == 0


def test_failed_live_sandbox_fetch_creates_failed_run(tmp_path):
    fake = FakeProviderHttpClient(
        [
            ProviderHttpResult(
                ok=False,
                status_code=503,
                content_type="application/json",
                json_data=None,
                text_preview="temporarily unavailable",
                error_message="Provider returned HTTP 503",
            )
        ]
    )
    with make_client_with_settings(
        tmp_path,
        jambase_live_calls_enabled=True,
        jambase_api_key="configured-jambase-value",
    ) as client:
        client.app.state.provider_http_client = fake
        response = admin_post(
            client,
            "/admin/api-feeds/jambase/live-sandbox",
            data={"limit": "1"},
            follow_redirects=False,
        )
        with client.app.state.SessionLocal() as session:
            run = session.scalars(select(ApiFeedRun)).one()
            records = list(session.scalars(select(ApiFeedRecord)).all())

    assert response.status_code == 303
    assert run.status == "failure"
    assert run.error_message == "Provider returned HTTP 503"
    assert run.raw_record_count == 0
    assert records == []


def test_live_sandbox_record_approval_uses_shared_event_path(tmp_path):
    payload = {
        "events": [
            {
                "@type": "Concert",
                "identifier": "jambase:approve-live-1",
                "name": "Approved Live Sandbox Concert",
                "startDate": "2026-12-10T20:00:00",
                "location": {
                    "name": "Approval Hall",
                    "address": {
                        "streetAddress": "20 Approval Ave",
                        "addressLocality": "Memphis",
                        "addressRegion": {"alternateName": "TN"},
                        "addressCountry": {"identifier": "US"},
                    },
                },
                "performer": [{"name": "Approval Artist", "x-isHeadliner": True}],
                "offers": [
                    {
                        "category": "ticketingLinkPrimary",
                        "url": "https://tickets.example/approval-live-1",
                    }
                ],
            }
        ]
    }
    fake = FakeProviderHttpClient(
        [
            ProviderHttpResult(
                ok=True,
                status_code=200,
                content_type="application/json",
                json_data=payload,
                text_preview="{}",
            )
        ]
    )
    with make_client_with_settings(
        tmp_path,
        jambase_live_calls_enabled=True,
        jambase_api_key="configured-jambase-value",
    ) as client:
        client.app.state.provider_http_client = fake
        admin_post(client, "/admin/api-feeds/jambase/live-sandbox")
        response = admin_post(client, "/admin/api-feed-records/1/approve")
        with client.app.state.SessionLocal() as session:
            events = list(session.scalars(select(Event)).all())
            claims = list(session.scalars(select(EventSourceClaim)).all())
            pois = list(session.scalars(select(PoiLocation)).all())
            poi_candidates = list(session.scalars(select(PoiCandidate)).all())
            record = session.get(ApiFeedRecord, 1)

    assert response.status_code == 303
    assert len(events) == 1
    assert events[0].category == "Concert"
    assert events[0].record_type == "event"
    assert events[0].source_type == "api_feed"
    assert events[0].source_claim_count == 1
    assert len(claims) == 1
    assert claims[0].source_type == "api_feed"
    assert pois == []
    assert len(poi_candidates) == 1
    assert poi_candidates[0].source_provider == "jambase"
    assert poi_candidates[0].candidate_name == "Approval Hall"
    assert record is not None
    assert record.review_status == "approved"
    assert record.created_event_id == events[0].id


def test_manual_json_upload_creates_api_feed_run_and_records(tmp_path):
    with make_client(tmp_path) as client:
        response = admin_post_upload_json(
            client,
            "/admin/api-feeds/manual_json/upload-json",
            api_upload_payload(),
        )
        with client.app.state.SessionLocal() as session:
            runs = list(session.scalars(select(ApiFeedRun)).all())
            records = list(session.scalars(select(ApiFeedRecord)).all())

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/api-feed-runs/1"
    assert len(runs) == 1
    assert runs[0].run_mode == "manual_json_upload"
    assert len(records) == 1
    assert records[0].event_name == "API Demo Concert"
    assert records[0].category == "Concert"
    assert records[0].record_type == "event"


def test_jambase_demo_fixture_normalizes_to_concert_candidate(tmp_path):
    with make_client(tmp_path) as client:
        response = admin_post(
            client,
            "/admin/api-feeds/jambase/run-demo-import",
        )
        with client.app.state.SessionLocal() as session:
            record = session.scalars(
                select(ApiFeedRecord).where(ApiFeedRecord.provider_key == "jambase")
            ).first()

    assert response.status_code == 303
    assert record is not None
    assert record.category == "Concert"
    assert record.record_type == "event"
    assert record.normalization_status in {"normalized", "partial"}


def test_cityspark_fixture_uses_standard_vendor_retention(tmp_path):
    cityspark_key = "city" + "spark"
    with make_client(tmp_path) as client:
        admin_post(
            client,
            f"/admin/api-feeds/{cityspark_key}/run-demo-import",
        )
        response = admin_get(client, f"/admin/api-feeds/{cityspark_key}")
        with client.app.state.SessionLocal() as session:
            run = session.scalars(select(ApiFeedRun)).first()
            record = session.scalars(select(ApiFeedRecord)).first()

    assert response.status_code == 200
    assert "Permanent Allowed" in response.text
    assert "Credentials Missing" in response.text
    assert "Temporary Review Only" not in response.text
    assert "48h Retention" not in response.text
    assert "Contract Required" not in response.text
    assert run is not None
    assert run.compliance_expiration_at is None
    assert record is not None
    assert record.compliance_expires_at is None


def test_cityspark_provider_record_can_be_approved_without_permanent_storage_flag(
    tmp_path,
):
    cityspark_key = "city" + "spark"
    with make_client(tmp_path) as client:
        admin_post(client, f"/admin/api-feeds/{cityspark_key}/run-demo-import")
        response = admin_post(
            client,
            "/admin/api-feed-records/1/approve",
        )
        with client.app.state.SessionLocal() as session:
            events = list(session.scalars(select(Event)).all())
            claims = list(session.scalars(select(EventSourceClaim)).all())
            pois = list(session.scalars(select(PoiLocation)).all())
            poi_candidates = list(session.scalars(select(PoiCandidate)).all())
            record = session.get(ApiFeedRecord, 1)

    assert response.status_code == 303
    assert len(events) == 1
    assert events[0].category == "Concert"
    assert events[0].record_type == "event"
    assert events[0].source_type == "api_feed"
    assert events[0].source_claim_count == 1
    assert len(claims) == 1
    assert claims[0].source_type == "api_feed"
    assert pois == []
    assert len(poi_candidates) == 1
    assert poi_candidates[0].source_provider == cityspark_key
    assert poi_candidates[0].candidate_name == "Licensed Review Hall"
    assert record is not None
    assert record.review_status == "approved"
    assert record.created_event_id == events[0].id


def jambase_fixture_records() -> list[dict[str, object]]:
    payload = json_fixture("api_jambase_events.json")
    records = extract_json_records(payload)
    return [dict(record) for record in records]


def cityspark_fixture_records() -> list[dict[str, object]]:
    payload = json_fixture("api_cityspark_events.json")
    records = extract_json_records(payload)
    return [dict(record) for record in records]


def test_artist_name_normalization_and_key_are_conservative():
    assert normalize_artist_name("The Fixture & Co. Live!") == "fixture and co"
    assert normalize_artist_name("Fixture Tribute") == "fixture tribute"
    assert build_artist_key("The Fixture Band") == build_artist_key("Fixture Band")


def test_artist_matching_uses_strong_ids_and_exact_name_context(tmp_path):
    with make_client(tmp_path) as client:
        with client.app.state.SessionLocal() as session:
            artist = upsert_artist_from_claim(
                session,
                ArtistClaimInput(
                    name="Fixture Headliner",
                    source_type="jambase",
                    provider_artist_id="jambase:artist-headliner",
                    jambase_artist_id="jambase:artist-headliner",
                    genres=["Rock"],
                ),
            )
            spotify_artist = upsert_artist_from_claim(
                session,
                ArtistClaimInput(
                    name="Spotify Fixture",
                    source_type="spotify",
                    spotify_artist_id="spotify:fixture",
                    genres=["Pop"],
                ),
            )
            session.commit()

            by_jambase, jambase_confidence, _ = match_existing_artist(
                session,
                "Unrelated Display",
                provider_ids={"jambase": "jambase:artist-headliner"},
            )
            by_spotify, spotify_confidence, _ = match_existing_artist(
                session,
                "Different Display",
                provider_ids={"spotify": "spotify:fixture"},
            )
            by_name, name_confidence, name_reasons = match_existing_artist(
                session,
                "The Fixture Headliner",
                genres=["Rock"],
            )
            weak, _, weak_reasons = match_existing_artist(
                session,
                "Fixture Headliner Tribute",
            )

    assert by_jambase is not None
    assert by_jambase.id == artist.id
    assert jambase_confidence >= 0.98
    assert by_spotify is not None
    assert by_spotify.id == spotify_artist.id
    assert spotify_confidence >= 0.98
    assert by_name is not None
    assert by_name.id == artist.id
    assert name_confidence >= 0.8
    assert "normalized_name_exact_genre_overlap" in name_reasons
    assert weak is None
    assert weak_reasons == ["no_match"]


def test_jambase_artist_extraction_reads_performer_metadata():
    record = jambase_fixture_records()[0]
    record["performer"][0]["image"] = {
        "url": "https://images.example/fixture-headliner.jpg"
    }
    claims = extract_artists_from_api_payload("jambase", record)

    assert len(claims) == 2
    headliner = claims[0]
    support = claims[1]
    assert headliner.name == "Fixture Headliner"
    assert headliner.role == "headliner"
    assert headliner.provider_artist_id == "jambase:artist-headliner"
    assert headliner.jambase_artist_id == "jambase:artist-headliner"
    assert headliner.spotify_url == "https://open.spotify.com/artist/fixture"
    assert headliner.image_url == "https://images.example/fixture-headliner.jpg"
    assert headliner.genres == ["Rock"]
    assert support.role == "supporting"
    assert support.genres == ["Indie Rock"]


def test_approved_jambase_record_creates_artist_registry_links_and_image(
    tmp_path,
):
    record = jambase_fixture_records()[0]
    record["performer"][0]["image"] = {
        "url": "https://images.example/fixture-headliner.jpg"
    }
    content = json.dumps({"events": [record]}).encode("utf-8")
    with make_client(tmp_path) as client:
        admin_post_upload_json(client, "/admin/api-feeds/jambase/upload-json", content)
        response = admin_post(client, "/admin/api-feed-records/1/approve")
        with client.app.state.SessionLocal() as session:
            event = session.get(Event, 1)
            artists = list(
                session.scalars(select(CanonicalArtist).order_by(CanonicalArtist.id))
            )
            links = list(session.scalars(select(EventArtist).order_by(EventArtist.id)))
            claims = list(
                session.scalars(
                    select(ArtistSourceClaim).order_by(ArtistSourceClaim.id)
                )
            )
            candidate = session.scalars(
                select(ImageCandidate).where(
                    ImageCandidate.rescue_source == "provider_artist_image"
                )
            ).first()

    assert response.status_code == 303
    assert event is not None
    assert event.category == "Concert"
    assert event.record_type == "event"
    assert event.normalized_genres == ["Rock", "Indie"]
    assert event.music_relevance_score is not None
    assert event.music_relevance_score >= 90
    assert len(artists) == 2
    assert {artist.display_name for artist in artists} == {
        "Fixture Headliner",
        "Fixture Support",
    }
    assert {link.role for link in links} == {"headliner", "supporting"}
    assert claims
    assert claims[0].source_type == "jambase"
    assert claims[0].genres == ["Rock"]
    assert candidate is not None
    assert candidate.image_role == "artist_press"
    assert candidate.rescue_priority < 30


def test_file_upload_headliner_creates_artist_link(tmp_path):
    with make_client(tmp_path) as client:
        with client.app.state.SessionLocal() as session:
            event = Event(
                category="Concert",
                record_type="event",
                source_type="file_upload",
                title="Uploaded Artist Night",
                headliner="Upload Headliner",
                supporting_artists="Upload Opener",
                start_datetime=datetime.fromisoformat("2026-08-05T20:00:00"),
                dedupe_key="artist-upload:1",
                raw_event_json="{}",
            )
            session.add(event)
            session.commit()
            event_id = event.id
            links = link_event_to_artists(session, event_id)
            artists = list(
                session.scalars(select(CanonicalArtist).order_by(CanonicalArtist.id))
            )

    assert len(links) == 2
    assert {artist.display_name for artist in artists} == {
        "Upload Headliner",
        "Upload Opener",
    }


def test_genre_normalization_and_music_relevance_signals(tmp_path):
    assert normalize_genre_value("Alternative Rock") == "Rock"
    assert normalize_genre_value("Made Up Genre") == "Other / Unknown"
    with make_client(tmp_path) as client:
        with client.app.state.SessionLocal() as session:
            music_event = Event(
                category="Concert",
                record_type="event",
                source_type="api_feed",
                api_provider_key="ticketmaster",
                title="Ticketmaster Music Night",
                headliner="Music Headliner",
                provider_music_segment="Music",
                provider_genre="Alternative",
                provider_subgenre="Alternative Rock",
                start_datetime=datetime.fromisoformat("2026-08-06T20:00:00"),
                dedupe_key="genre:music",
                raw_event_json="{}",
            )
            sports_event = Event(
                category="Concert",
                record_type="event",
                source_type="api_feed",
                api_provider_key="ticketmaster",
                title="Arena Sports Listing",
                provider_music_segment="Sports",
                provider_genre="Basketball",
                start_datetime=datetime.fromisoformat("2026-08-07T20:00:00"),
                dedupe_key="genre:sports",
                raw_event_json="{}",
            )
            session.add_all([music_event, sports_event])
            session.commit()
            normalize_event_music_fields(music_event)
            normalize_event_music_fields(sports_event)
            session.commit()

    assert music_event.normalized_genres == ["Indie", "Rock"]
    assert music_event.music_relevance_score is not None
    assert sports_event.music_relevance_score is not None
    assert music_event.music_relevance_score > sports_event.music_relevance_score
    assert "non_music_segment_sports" in sports_event.music_relevance_flags


def test_app_feed_includes_safe_artist_array_and_normalized_genre_filters(tmp_path):
    record = jambase_fixture_records()[0]
    record["performer"][0]["image"] = {
        "url": "https://images.example/fixture-headliner.jpg"
    }
    content = json.dumps({"events": [record]}).encode("utf-8")
    with make_client(tmp_path) as client:
        admin_post_upload_json(client, "/admin/api-feeds/jambase/upload-json", content)
        admin_post(client, "/admin/api-feed-records/1/approve")
        with client.app.state.SessionLocal() as session:
            event = session.get(Event, 1)
            assert event is not None
            event.publish_status = "approved"
            session.add(event)
            session.commit()
        feed_response = admin_get(client, "/admin/app-feed/events.json")
        filter_response = admin_get(client, "/admin/app-feed/filter-options.json")

    payload = feed_response.json()
    assert payload["count"] == 1
    feed_event = payload["records"][0]
    assert feed_event["headliner"] == "Fixture Headliner"
    assert feed_event["artists"][0]["name"] == "Fixture Headliner"
    assert feed_event["artists"][0]["role"] == "headliner"
    assert feed_event["artists"][0]["spotify_url"] == (
        "https://open.spotify.com/artist/fixture"
    )
    assert "raw_payload" not in json.dumps(feed_event)
    genre_names = {
        item["name"] for item in filter_response.json()["event_filters"]["genres"]
    }
    assert "Rock" in genre_names


def test_artist_admin_pages_and_jobs_work(tmp_path):
    with make_client(tmp_path) as client:
        with client.app.state.SessionLocal() as session:
            event = Event(
                category="Concert",
                record_type="event",
                source_type="file_upload",
                title="Admin Artist Night",
                headliner="Admin Headliner",
                provider_genre="Americana",
                start_datetime=datetime.fromisoformat("2026-08-08T20:00:00"),
                dedupe_key="artist-admin:1",
                raw_event_json="{}",
            )
            session.add(event)
            session.commit()
            event_id = event.id
            rebuild_job = enqueue_job(session, "rebuild_artist_registry", {})
            processed_rebuild = process_next_job(
                session,
                client.app.state.settings,
                "artist-test-worker",
            )
            genre_job = enqueue_job(session, "artist_genre_normalization", {})
            processed_genres = process_next_job(
                session,
                client.app.state.settings,
                "artist-test-worker",
            )
            artist = session.scalars(select(CanonicalArtist)).first()
            assert artist is not None
            artist_id = artist.id
            event = session.get(Event, event_id)
            assert event is not None
            event_id = event.id

        unauth_artists = client.get("/admin/artists", follow_redirects=False)
        artists_page = admin_get(client, "/admin/artists")
        detail_page = admin_get(client, f"/admin/artists/{artist_id}")
        duplicates_page = admin_get(client, "/admin/artist-duplicates")
        event_preview = admin_get(client, f"/preview/events/{event_id}")

    assert rebuild_job.job_type == "rebuild_artist_registry"
    assert genre_job.job_type == "artist_genre_normalization"
    assert processed_rebuild is not None
    assert processed_rebuild.status == "success"
    assert processed_genres is not None
    assert processed_genres.status == "success"
    assert unauth_artists.status_code == 303
    assert unauth_artists.headers["location"].startswith("/admin/login")
    assert artists_page.status_code == 200
    assert "Admin Headliner" in artists_page.text
    assert detail_page.status_code == 200
    assert "Source Claims" in detail_page.text
    assert "Linked Events" in detail_page.text
    assert duplicates_page.status_code == 200
    assert event_preview.status_code == 200
    assert "Artists" in event_preview.text


def test_artist_registry_safety_has_no_live_calls_or_social_scraping():
    artist_service = Path("app/services/artist_service.py").read_text(encoding="utf-8")
    genre_service = Path("app/services/genre_service.py").read_text(encoding="utf-8")
    combined = artist_service + genre_service

    assert "httpx" not in combined
    assert "requests" not in combined
    assert "api_key" not in combined.lower()
    assert "scrape" not in combined.lower()


def test_jambase_mapper_handles_object_with_events_array():
    payload = json_fixture("api_jambase_events.json")
    records = extract_json_records(payload)

    assert len(records) == 3
    assert records[0]["identifier"] == "jambase:test-concert-1"


def test_jambase_mapper_handles_single_event_object():
    record = jambase_fixture_records()[0]
    candidate = jambase_mapper(record)

    assert candidate.normalized_payload["event_name"] == "Synthetic JamBase Concert"
    assert candidate.normalized_payload["category"] == "Concert"
    assert candidate.normalized_payload["record_type"] == "event"


def test_jambase_mapper_handles_event_detail_object_with_event():
    record = jambase_fixture_records()[0]
    records = extract_json_records({"event": record})

    assert records == [record]
    assert jambase_mapper(records[0]).provider_event_id == "jambase:test-concert-1"


def test_jambase_mapper_extracts_identifier_as_source_record_id():
    candidate = jambase_mapper(jambase_fixture_records()[0])

    assert candidate.source_record_id == "jambase:test-concert-1"
    assert candidate.provider_event_id == "jambase:test-concert-1"
    assert candidate.dedupe_confidence >= 0.9


def test_jambase_mapper_extracts_headliner_and_supporting_artists():
    candidate = jambase_mapper(jambase_fixture_records()[0])
    payload = candidate.normalized_payload

    assert payload["headliner"] == "Fixture Headliner"
    assert payload["supporting_artists"] == "Fixture Support"


def test_jambase_mapper_prefers_primary_ticket_offer():
    candidate = jambase_mapper(jambase_fixture_records()[0])
    payload = candidate.normalized_payload

    assert payload["tickets_link"] == "https://www.axs.com/events/synthetic-jambase-concert"
    assert payload["ticket_link_classification"] == "platform_event"


def test_jambase_mapper_falls_back_to_secondary_ticket_offer():
    candidate = jambase_mapper(jambase_fixture_records()[1])
    payload = candidate.normalized_payload

    assert payload["tickets_link"] == "https://tickets.example/synthetic-jambase-festival"
    assert payload["ticket_link_classification"] == "direct"


def test_jambase_mapper_preserves_venue_geo_address_and_timezone():
    candidate = jambase_mapper(jambase_fixture_records()[0])
    payload = candidate.normalized_payload

    assert payload["provider_venue_id"] == "jambase:venue-1"
    assert payload["venue_address"] == "100 Fixture Ave"
    assert payload["city"] == "Memphis"
    assert payload["state"] == "TN"
    assert payload["zip_code"] == "38103"
    assert payload["country"] == "US"
    assert payload["latitude"] == 35.1495
    assert payload["longitude"] == -90.049
    assert payload["timezone"] == "America/Chicago"


def test_jambase_mapper_preserves_v310_lifecycle_and_related_metadata():
    record = jambase_fixture_records()[0]
    record["eventStatus"] = "rescheduled"
    record["previousStartDate"] = "2026-08-01T20:00:00"
    record["eventAttendanceMode"] = "offline"
    record["isAccessibleForFree"] = False
    record["deletionStatus"] = "active"
    record["mergedInto"] = "jambase:merged-target"
    record["x-streamIds"] = ["stream:jambase:1"]
    record["location"]["address"]["x-streetAddress2"] = "Suite 10"
    candidate = jambase_mapper(record)
    payload = candidate.normalized_payload

    assert payload["event_lifecycle_status"] == "rescheduled"
    assert payload["previous_start_datetime"] == "2026-08-01T20:00:00"
    assert payload["attendance_mode"] == "offline"
    assert payload["is_free"] is False
    assert payload["deletion_status"] == "active"
    assert payload["provider_merged_into"] == "jambase:merged-target"
    assert payload["related_stream_ids"] == ["stream:jambase:1"]
    assert payload["venue_address_2"] == "Suite 10"
    assert "v3.1.0" in payload["provider_doc_notes"]


def test_source_taxonomy_detects_ticketing_and_upstream_domains():
    assert detect_source_key("https://www.axs.com/events/fixture") == "axs"
    assert detect_source_key("https://bandsintown.com/e/fixture") == "bandsintown"
    assert detect_source_key("Ticketmaster") == "ticketmaster"
    assert detect_source_key("https://link.dice.fm/fixture") == "dice"
    assert provider_key_for_value("https://unknown.example/events/fixture") == "unknown"


def test_export_discovered_domains_map_to_provider_keys():
    cases = {
        "https://app.opendate.io/e/fixture": "opendate",
        "https://www.universe.com/events/fixture": "universe",
        "https://www.skiddle.com/whats-on/fixture": "skiddle",
        "https://events.humanitix.com/fixture": "humanitix",
        "https://www.tickettailor.com/events/fixture": "ticket-tailor",
        "https://buytickets.at/fixture": "ticket-tailor",
        "https://www.showpass.com/fixture": "showpass",
        "https://ci.ovationtix.com/36626": "ovationtix-audienceview",
        "https://holdmyticket.com/event/452084": "holdmyticket",
        "https://www.ticketnetwork.com/en/p/fixture": "ticketnetwork",
        "https://mercurywebservices.com/": "ticketnetwork",
        "https://www.vividseats.com/fixture": "vivid-seats",
        "https://skybox.vividseats.com/welcome.html": "vivid-seats",
        "https://www.prekindle.com/event/fixture": "prekindle",
        (
            "https://librarymusichall.tixtrack.com/tickets/series/fixture"
        ): "tixtrack-nliven",
        "https://api.nliven.co/apidocumentation/webhooks/": "tixtrack-nliven",
        "https://www.zeffy.com/en-US/ticketing/fixture": "zeffy",
        "https://eventvesta.com/events/127421/t/tickets": "eventvesta",
        "https://events.outhousetickets.com/e/fixture": "outhouse-tickets",
        "https://tickets.venuepilot.com/e/fixture": "venuepilot",
        "https://www.biletix.com/performance/fixture": "biletix",
        "https://speakeasygo.com/venue/event": "speakeasygo",
        "https://events.eventnoire.com/e/fixture/tickets": "eventnoire",
        "https://www.my805tix.com/e/fixture/tickets": "my805tix",
        "https://www.805tix.com/e/fixture": "my805tix",
        "https://www.24tix.com/events/fixture": "twentyfour-tix",
        "https://www.simpletix.com/e/fixture": "simpletix",
        "https://www.tix.com/ticket-sales/fixture": "tix-com",
        "https://events.ticketleap.com/tickets/fixture": "ticketleap",
        "https://aftontickets.com/fixture": "afton-tickets",
        "https://aftonshows.com/fixture": "afton-tickets",
        "https://www.instantseats.com/?fuseaction=home.artist": "instantseats",
    }

    for url, expected in cases.items():
        assert detect_source_key(url) == expected


def test_jambase_mapper_extracts_source_chain_and_external_identifiers():
    candidate = jambase_mapper(jambase_fixture_records()[0])
    payload = candidate.normalized_payload

    assert payload["ingestion_provider"] == "jambase"
    assert payload["upstream_event_source"] == "bandsintown"
    assert payload["upstream_event_id"] == "bit:event-1"
    assert payload["upstream_artist_source"] == "ticketmaster"
    assert payload["upstream_artist_id"] == "tm:artist-1"
    assert payload["upstream_venue_source"] == "axs"
    assert payload["upstream_venue_id"] == "axs:venue-1"
    assert payload["ticketing_provider"] == "axs"
    assert payload["ticket_link_repair_strategy"] == "keep_platform_event"
    assert payload["ticket_link_repair_source"] == "ticketingLinkPrimary"
    assert "external identifiers present" in payload["provenance_flags"]
    assert payload["source_chain"][1]["source"] == "bandsintown"
    assert payload["source_chain"][1]["source_id"] == "bit:event-1"
    assert any(
        item["scope"] == "artist" and item["source"] == "ticketmaster"
        for item in payload["external_identifiers"]
    )
    assert payload["ticket_offers"][0]["detected_provider"] == "axs"
    assert payload["dedupe_source_fields"]["upstream_event_source"] == "bandsintown"
    assert payload["dedupe_source_fields"]["ticketing_provider"] == "axs"


def test_jambase_festival_normalizes_as_concert_with_type_preserved():
    candidate = jambase_mapper(jambase_fixture_records()[1])
    payload = candidate.normalized_payload

    assert payload["category"] == "Concert"
    assert payload["record_type"] == "event"
    assert payload["provider_event_type"] == "Festival"
    assert payload["supporting_artists"] == "Festival Guest One, Festival Guest Two"


def test_cityspark_mapper_extracts_event_series_fields():
    candidate = cityspark_mapper(cityspark_fixture_records()[0])
    payload = candidate.normalized_payload

    assert candidate.source_record_id == "cs-test-event-1"
    assert payload["event_name"] == "Synthetic Licensed Vendor Concert"
    assert payload["venue_name"] == "Licensed Fixture Hall"
    assert payload["city"] == "Memphis"
    assert payload["main_image_url"] == "https://images.example/licensed-vendor-large.jpg"
    assert payload["tickets_link"] == "https://tickets.example/licensed-vendor-concert"
    assert payload["has_time"] is True
    assert payload["all_day"] is False


def test_cityspark_mapper_prefers_ticket_url_over_links():
    candidate = cityspark_mapper(cityspark_fixture_records()[0])
    payload = candidate.normalized_payload

    assert payload["tickets_link"] == "https://tickets.example/licensed-vendor-concert"
    assert payload["recommended_ticket_link"] == "https://tickets.example/licensed-vendor-concert"


def test_cityspark_mapper_does_not_prefer_generic_links_without_ticket_url():
    candidate = cityspark_mapper(cityspark_fixture_records()[1])
    payload = candidate.normalized_payload

    assert payload["tickets_link"] is None
    assert payload["ticket_link_classification"] == "platform_generic_or_app"
    assert "ticketUrl missing" in candidate.quality_flags


def test_ticket_link_classifier_rejects_eventbrite_checkout_external():
    assessment = classify_ticket_link(
        "https://www.eventbrite.com/checkout-external?eid=fixture"
    )

    assert assessment.category == "platform_generic_or_app"
    assert assessment.usable is False
    assert assessment.provider_key == "eventbrite"
    assert assessment.repair_strategy == "reject_checkout_external"


def test_ticket_link_classifier_flags_generic_dice_handoff_links():
    assessment = classify_ticket_link("https://link.dice.fm/fixture-handoff")

    assert assessment.category == "platform_generic_or_app"
    assert assessment.usable is False
    assert assessment.provider_key == "dice"
    assert assessment.repair_strategy == "reject_generic_app_handoff"


def test_ticket_link_classifier_flags_ticketmaster_generic_pages():
    homepage = classify_ticket_link("https://www.ticketmaster.com/")
    artist = classify_ticket_link("https://www.ticketmaster.com/artist/fixture/123")
    generic = classify_ticket_link("https://www.ticketmaster.com/music")

    assert homepage.category == "platform_generic_or_app"
    assert artist.category == "platform_generic_or_app"
    assert generic.category == "platform_generic_or_app"
    assert not homepage.usable
    assert not artist.usable
    assert not generic.usable
    assert homepage.provider_key == "ticketmaster"
    assert homepage.repair_strategy == "reject_generic_platform_page"


def test_ticket_link_classifier_accepts_event_specific_platform_pages():
    assessment = classify_ticket_link(
        "https://www.ticketmaster.com/event/fixture-event-id"
    )

    assert assessment.category == "platform_event"
    assert assessment.usable is True
    assert assessment.provider_key == "ticketmaster"
    assert assessment.repair_strategy == "keep_platform_event"


def test_ticket_link_classifier_flags_affiliate_tracking_domains():
    assessment = classify_ticket_link(
        "https://vivid-seats.pxf.io/c/258147/1017970/12730"
    )

    assert assessment.category == "redirect_or_handoff"
    assert assessment.usable is False
    assert assessment.provider_key == "affiliate-networks"
    assert assessment.repair_strategy == "resolve_affiliate_handoff"
    assert "affiliate/tracking domain" in assessment.flags


def test_ticketmaster_music_classification_is_positive_signal():
    payload = json_fixture("api_ticketmaster_classifications.json")
    assert isinstance(payload, dict)
    mapping = map_ticketmaster_classification(dict(payload["music"]))

    assert mapping.is_music_signal is True
    assert mapping.music_category == "Music"
    assert mapping.provider_genre == "Alternative"
    assert mapping.provider_subgenre == "Alternative Rock"
    assert mapping.normalized_genre == "Alternative Rock"
    assert mapping.event_relevance_score >= 90


def test_ticketmaster_non_music_classification_is_low_relevance():
    payload = json_fixture("api_ticketmaster_classifications.json")
    assert isinstance(payload, dict)
    mapping = map_ticketmaster_classification(dict(payload["non_music"]))

    assert mapping.is_music_signal is False
    assert "low_event_relevance" in mapping.flags
    assert mapping.event_relevance_score < 50


def test_api_feed_record_detail_shows_ticket_link_classification(tmp_path):
    content = (FIXTURE_DIR / "api_jambase_events.json").read_bytes()
    with make_client(tmp_path) as client:
        admin_post_upload_json(
            client,
            "/admin/api-feeds/jambase/upload-json",
            content,
        )
        response = admin_get(client, "/admin/api-feed-records/1")

    assert response.status_code == 200
    assert "Ticket classification" in response.text
    assert "platform_event" in response.text
    assert "Source Chain" in response.text
    assert "Bandsintown" in response.text
    assert "AXS" in response.text
    assert "Ticket provider docs status" in response.text
    assert "Source ID fields used for dedupe" in response.text
    assert "Provider documentation notes" in response.text


def test_api_provider_detail_shows_mapping_docs_summary(tmp_path):
    with make_client(tmp_path) as client:
        response = admin_get(client, "/admin/api-feeds/jambase")

    assert response.status_code == 200
    assert "Docs available" in response.text
    assert (
        "docs/provider-research/jambase/v3.1.0/"
        "jambase-api-v3.1.0-openapi.yaml"
        in response.text
    )
    assert "Ticket-link strategy" in response.text
    assert "Dedupe strategy" in response.text


def test_jambase_v310_docs_are_referenced() -> None:
    readme = Path("README.md").read_text()
    mapping_doc = Path("docs/provider-mapping-reference.md").read_text()
    summary_doc = Path(
        "docs/provider-research/jambase/jambase-v3.1.0-summary.md"
    ).read_text()

    assert "JamBase API v3.1.0" in readme
    assert "https://api.data.jambase.com/v3" in mapping_doc
    assert "eventType=concerts" in summary_doc
    assert "apikey=REDACTED" in summary_doc


def test_api_record_detail_shows_raw_and_normalized_candidate(tmp_path):
    with make_client(tmp_path) as client:
        admin_post_upload_json(
            client,
            "/admin/api-feeds/manual_json/upload-json",
            api_upload_payload(),
        )
        response = admin_get(client, "/admin/api-feed-records/1")

    assert response.status_code == 200
    assert "Raw Provider Record" in response.text
    assert "Normalized Music Roadtrip Candidate" in response.text
    assert "API Demo Concert" in response.text
    assert "api-demo-1" in response.text


def test_approve_api_feed_record_requires_admin_auth_and_csrf(tmp_path):
    with make_client(tmp_path) as client:
        unauth = client.post(
            "/admin/api-feed-records/1/approve",
            follow_redirects=False,
        )

    with make_client(tmp_path) as client:
        admin_post_upload_json(
            client,
            "/admin/api-feeds/manual_json/upload-json",
            api_upload_payload(),
        )
        login_admin(client)
        no_csrf = client.post(
            "/admin/api-feed-records/1/approve",
            follow_redirects=False,
        )

    assert unauth.status_code == 401
    assert no_csrf.status_code == 403


def test_approve_api_feed_record_creates_normalized_concert_event(tmp_path):
    with make_client(tmp_path) as client:
        admin_post_upload_json(
            client,
            "/admin/api-feeds/manual_json/upload-json",
            api_upload_payload(),
        )
        response = admin_post(
            client,
            "/admin/api-feed-records/1/approve",
        )
        with client.app.state.SessionLocal() as session:
            event = session.get(Event, 1)
            venue = session.get(EventVenue, 1)
            record = session.get(ApiFeedRecord, 1)

    assert response.status_code == 303
    assert event is not None
    assert event.title == "API Demo Concert"
    assert event.category == "Concert"
    assert event.record_type == "event"
    assert event.source_type == "api_feed"
    assert event.api_feed_record_id == 1
    assert venue is not None
    assert venue.category == "Music Site"
    assert record is not None
    assert record.review_status == "approved"
    assert record.created_event_id == event.id


def test_approved_jambase_record_preserves_provenance_on_preview(tmp_path):
    content = (FIXTURE_DIR / "api_jambase_events.json").read_bytes()
    with make_client(tmp_path) as client:
        admin_post_upload_json(
            client,
            "/admin/api-feeds/jambase/upload-json",
            content,
        )
        admin_post(client, "/admin/api-feed-records/1/approve")
        response = admin_get(client, "/preview/events/1")
        with client.app.state.SessionLocal() as session:
            event = session.get(Event, 1)

    assert response.status_code == 200
    assert event is not None
    assert event.category == "Concert"
    assert event.record_type == "event"
    assert event.ingestion_provider == "jambase"
    assert event.upstream_event_source == "bandsintown"
    assert event.ticketing_provider == "axs"
    assert "API Provenance" in response.text
    assert "bandsintown" in response.text
    assert "axs" in response.text
    assert "Source chain" in response.text


def test_hold_reject_and_enrichment_decisions_do_not_create_event(tmp_path):
    with make_client(tmp_path) as client:
        row = json.loads(api_upload_payload())[0]
        content = json.dumps({"events": [row, row, row]}).encode("utf-8")
        admin_post_upload_json(
            client,
            "/admin/api-feeds/manual_json/upload-json",
            content,
        )
        hold = admin_post(client, "/admin/api-feed-records/1/hold")
        reject = admin_post(client, "/admin/api-feed-records/2/reject")
        enrich = admin_post(client, "/admin/api-feed-records/3/send-to-enrichment")
        with client.app.state.SessionLocal() as session:
            records = list(
                session.scalars(select(ApiFeedRecord).order_by(ApiFeedRecord.id)).all()
            )
            events = list(session.scalars(select(Event)).all())

    assert hold.status_code == 303
    assert reject.status_code == 303
    assert enrich.status_code == 303
    assert [record.review_status for record in records] == [
        "held",
        "rejected",
        "needs_enrichment",
    ]
    assert events == []


def test_api_approval_uses_dedupe_upsert_path(tmp_path):
    with make_client(tmp_path) as client:
        payload = api_upload_payload()
        admin_post_upload_json(
            client,
            "/admin/api-feeds/manual_json/upload-json",
            payload,
        )
        admin_post_upload_json(
            client,
            "/admin/api-feeds/manual_json/upload-json",
            payload,
        )
        admin_post(client, "/admin/api-feed-records/1/approve")
        admin_post(client, "/admin/api-feed-records/2/approve")
        with client.app.state.SessionLocal() as session:
            events = list(session.scalars(select(Event)).all())
            claims = list(session.scalars(select(EventSourceClaim)).all())

    assert len(events) == 1
    assert events[0].title == "API Demo Concert"
    assert events[0].source_claim_count == 2
    assert len(claims) == 2


def test_repeated_ics_crawl_updates_events_and_adds_source_claims(tmp_path):
    def fetcher(url: str) -> FetchResult:
        return FetchResult(
            http_status_code=200,
            content_type="text/calendar",
            raw_response_body=SAMPLE_ICS,
        )

    with make_client(tmp_path) as client:
        submit_source(client, calendar_url="https://example.com/sample.ics")
        approve_source(client)
        client.app.state.fetch_calendar_url = fetcher
        admin_post(client, "/admin/sources/1/crawl", follow_redirects=True)
        admin_post(client, "/admin/sources/1/crawl", follow_redirects=True)
        with client.app.state.SessionLocal() as session:
            events = list(session.scalars(select(Event)).all())
            claims = list(session.scalars(select(EventSourceClaim)).all())
            second_run = get_crawl_run(session, 2)

    assert len(events) == 3
    assert len(claims) == 6
    assert second_run is not None
    assert second_run.events_created_count == 0
    assert second_run.events_updated_count == 3
    assert all(event.source_claim_count == 2 for event in events)


def test_duplicate_event_review_page_and_keep_both_action(tmp_path):
    rows = [
        {
            "id": "dup-a",
            "event_name": "Duplicate Candidate Show",
            "headliner": "Duplicate Candidate Show",
            "start_datetime": "2026-09-20T20:00:00",
            "venue_name": "First Venue",
            "venue_address": "1 First Ave",
            "city": "Memphis",
            "state": "TN",
            "event_url": "https://events.example/dup-a",
            "tickets_link": "https://tickets.example/dup-a",
        },
        {
            "id": "dup-b",
            "event_name": "Duplicate Candidate Show",
            "headliner": "Duplicate Candidate Show",
            "start_datetime": "2026-09-20T20:00:00",
            "venue_name": "Second Venue",
            "venue_address": "2 Second Ave",
            "city": "Memphis",
            "state": "TN",
            "event_url": "https://events.example/dup-b",
            "tickets_link": "https://tickets.example/dup-b",
        },
    ]
    with make_client(tmp_path) as client:
        admin_post_upload_json(
            client,
            "/admin/api-feeds/manual_json/upload-json",
            json.dumps(rows).encode("utf-8"),
        )
        admin_post(client, "/admin/api-feed-records/1/approve")
        admin_post(client, "/admin/api-feed-records/2/approve")
        page = admin_get(client, "/admin/duplicate-events")
        detail = admin_get(client, "/admin/duplicate-events/1")
        keep = admin_post(client, "/admin/duplicate-events/1/keep-both")
        with client.app.state.SessionLocal() as session:
            group = session.get(EventDuplicateGroup, 1)
            members = list(session.scalars(select(EventDuplicateGroupMember)).all())

    assert page.status_code == 200
    assert "Duplicate Candidate Show" in detail.text
    assert keep.status_code == 303
    assert group is not None
    assert group.status == "kept_separate"
    assert len(members) == 2


def test_preview_quality_shows_api_pending_review_counts(tmp_path):
    with make_client(tmp_path) as client:
        admin_post_upload_json(
            client,
            "/admin/api-feeds/manual_json/upload-json",
            api_upload_payload(),
        )
        response = admin_get(client, "/preview/quality")

    assert response.status_code == 200
    assert "API records pending review" in response.text
    assert "1" in response.text


def test_preview_quality_shows_source_claim_metrics(tmp_path):
    with make_client(tmp_path) as client:
        payload = api_upload_payload()
        admin_post_upload_json(
            client,
            "/admin/api-feeds/manual_json/upload-json",
            payload,
        )
        admin_post_upload_json(
            client,
            "/admin/api-feeds/manual_json/upload-json",
            payload,
        )
        admin_post(client, "/admin/api-feed-records/1/approve")
        admin_post(client, "/admin/api-feed-records/2/approve")
        response = admin_get(client, "/preview/quality")

    assert response.status_code == 200
    assert "Events with multiple source claims" in response.text
    assert "Events with one source claim" in response.text


def test_preview_quality_counts_unknown_upstream_and_unresolved_ticket_links(tmp_path):
    row = json.loads(api_upload_payload())[0]
    row["tickets_link"] = "https://unknown.example/events/not-final"
    with make_client(tmp_path) as client:
        admin_post_upload_json(
            client,
            "/admin/api-feeds/manual_json/upload-json",
            json.dumps([row]).encode("utf-8"),
        )
        response = admin_get(client, "/preview/quality")

    assert response.status_code == 200
    assert "API records with unknown upstream source" in response.text
    assert "API records requiring ticket backfill" in response.text
    assert "API ticket links classified as unresolved" in response.text


def test_no_api_key_values_appear_in_templates_or_tests():
    text = "\n".join(
        path.read_text()
        for base in [Path("app/web/templates"), Path("tests")]
        for path in base.rglob("*")
        if path.is_file() and path.suffix in {".html", ".py"}
    )
    assert ("s" + "k-") not in text
    assert ("secret" + "-") not in text.lower()


def test_export_discovered_providers_are_not_live_connectors():
    live_provider_keys = {
        provider.provider_key for provider in provider_registry(Settings())
    }
    export_only_keys = {
        "opendate",
        "universe",
        "skiddle",
        "humanitix",
        "ticket-tailor",
        "showpass",
        "ovationtix-audienceview",
        "holdmyticket",
        "ticketnetwork",
        "vivid-seats",
        "eventvesta",
        "venuepilot",
        "simpletix",
        "ticketleap",
    }

    assert live_provider_keys.isdisjoint(export_only_keys)


def test_cityspark_provider_detail_uses_paid_vendor_model(tmp_path):
    cityspark_key = "city" + "spark"
    with make_client(tmp_path) as client:
        response = admin_get(client, f"/admin/api-feeds/{cityspark_key}")

    assert response.status_code == 200
    assert "paid licensed vendor API feed" in response.text
    assert "Workbench Open" in response.text
    assert "Live Calls Off" in response.text
    assert "Permanent Allowed" in response.text
    assert "Credentials Missing" in response.text
    assert "Temporary Review Only" not in response.text
    assert "48h Retention" not in response.text
    assert "Contract Required" not in response.text
    assert "permanent approval" not in response.text.lower()


def test_cityspark_strategy_docs_describe_licensed_vendor_feed():
    docs_to_check = [
        Path("README.md").read_text(encoding="utf-8"),
        Path("docs/music-roadtrip-product-thesis.md").read_text(encoding="utf-8"),
        Path("docs/musicroadtrip_site_corpus.md").read_text(encoding="utf-8"),
        Path("docs/provider-mapping-reference.md").read_text(encoding="utf-8"),
        Path(
            "docs/provider-research/event_ticket_api_provider_research_pack_v2/"
            "provider_references/cityspark.md"
        ).read_text(encoding="utf-8"),
    ]
    combined_docs = "\n".join(docs_to_check)

    assert "CitySpark is a paid licensed vendor API feed" in combined_docs
    assert "licensed vendor feed" in combined_docs
    assert (
        "Live CitySpark calls remain off until credentials and configuration are added"
        in combined_docs
    )
    assert "not just a calendar scraper" in combined_docs
    assert "music-destination data platform" in combined_docs
    assert "Track A: Owned/direct source network" in combined_docs
    assert "Track B: Licensed/vendor provider feeds" in combined_docs
    assert "free travel app for music fans" in combined_docs
    assert "API usage requires an API key and CitySpark account" in combined_docs
    assert "JamBase and CitySpark Live Sandbox" in combined_docs
    assert "run_mode=live_api_sandbox" in combined_docs
    assert "Provider pipeline / developer handoff" in combined_docs
    assert "Ticketmaster classification references" in combined_docs

    cityspark = "City" + "Spark"
    data_source = "data" + " source"
    forbidden_phrases = [
        f"No {cityspark} data is ingested",
        f"{cityspark} is not a {data_source}",
        f"Do not ingest {cityspark} data",
        f"{cityspark} must not be used as a source",
        f"{cityspark} is only a reference",
        f"real {cityspark} event data is\n  not",
        "Temporary Review Only",
        "48h Retention",
        "Contract Required",
        "permanent approval blocked",
        "temporary-review-only",
        "permanent storage gated",
        "CITYSPARK_PERMANENT_STORAGE_ALLOWED",
    ]
    for phrase in forbidden_phrases:
        assert phrase not in combined_docs


def test_no_cityspark_live_connector_exists():
    app_text = "\n".join(path.read_text() for path in Path("app").rglob("*.py"))
    assert "httpx.post(\"https://api.cityspark.com" not in app_text
    assert "requests.post(\"https://api.cityspark.com" not in app_text
    assert "urllib.request.urlopen(\"https://api.cityspark.com" not in app_text


def test_create_region_and_normalize_region_key(tmp_path) -> None:
    with make_client(tmp_path) as client:
        with client.app.state.SessionLocal() as session:
            region = create_or_update_region(
                session,
                name="Memphis Music Region",
                region_type="certified_music_region",
                city="Memphis",
                state="TN",
                country="US",
            )
            same_region = create_or_update_region(
                session,
                name="Memphis Music Region",
                region_type="certified_music_region",
                city="Memphis",
                state="TN",
                country="US",
            )

    assert region.id == same_region.id
    assert (
        region.region_key
        == "certified-music-region-memphis-music-region-memphis-tn-us"
    )
    assert normalize_region_key("Memphis, TN", "US") == "memphis-tn-us"


def test_infer_poi_region_by_city_state_and_skip_low_confidence(tmp_path) -> None:
    with make_client(tmp_path) as client:
        with client.app.state.SessionLocal() as session:
            region = create_or_update_region(
                session,
                name="Memphis",
                region_type="city",
                city="Memphis",
                state="TN",
                country="US",
            )
            poi = PoiLocation(
                canonical_poi_id="infer-poi",
                poi_dedupe_key="infer-poi",
                display_name="Infer Venue",
                normalized_name="infer venue",
                category="Music Site",
                subcategory="Venues",
                city="Memphis",
                state="TN",
                country="US",
            )
            unmatched = PoiLocation(
                canonical_poi_id="unmatched-poi",
                poi_dedupe_key="unmatched-poi",
                display_name="Unmatched Venue",
                normalized_name="unmatched venue",
                category="Music Site",
                subcategory="Venues",
                city="Nowhere",
                state="ZZ",
                country="US",
            )
            session.add_all([poi, unmatched])
            session.flush()

            match = infer_region_for_poi(session, poi)
            no_match = infer_region_for_poi(session, unmatched)

    assert match is not None
    assert match.region.id == region.id
    assert match.confidence >= 0.9
    assert no_match is None


def test_infer_event_region_by_venue_city_state(tmp_path) -> None:
    with make_client(tmp_path) as client:
        with client.app.state.SessionLocal() as session:
            region = create_or_update_region(
                session,
                name="Memphis",
                region_type="city",
                city="Memphis",
                state="TN",
                country="US",
            )
            venue = EventVenue(
                venue_key="infer-event-venue",
                display_name="Infer Event Venue",
                city="Memphis",
                state="TN",
                country="US",
            )
            session.add(venue)
            session.flush()
            event = Event(
                event_venue_id=venue.id,
                category="Concert",
                record_type="event",
                source_type="file_upload",
                title="Infer Event",
                start_datetime=datetime.fromisoformat("2026-08-01T20:00:00"),
                dedupe_key="infer-event",
                raw_event_json="{}",
            )
            session.add(event)
            session.flush()
            match = infer_region_for_event(session, event)

    assert match is not None
    assert match.region.id == region.id
    assert match.reason == "city_state_country"


def test_seed_search_locations_from_pois_and_regions_is_idempotent(tmp_path) -> None:
    with make_client(tmp_path) as client:
        region_id = seed_region_fixture(client)
        with client.app.state.SessionLocal() as session:
            poi_counts = seed_search_locations_from_pois(session)
            region_counts = seed_search_locations_from_regions(session)
            poi_counts_again = seed_search_locations_from_pois(session)
            seeds = list(session.scalars(select(SearchSeedLocation)).all())
            poi_seed = session.scalar(
                select(SearchSeedLocation).where(
                    SearchSeedLocation.seed_key == "poi:1"
                )
            )
            assert poi_seed is not None
            poi_seed.use_for_app_search = True
            session.commit()
            marked_seed = session.get(SearchSeedLocation, poi_seed.id)

    assert region_id == 1
    assert poi_counts == {"created": 1, "updated": 0}
    assert region_counts == {"created": 1, "updated": 0}
    assert poi_counts_again == {"created": 0, "updated": 1}
    assert len(seeds) == 2
    assert poi_seed.display_name == "Region Fixture Venue POI"
    assert poi_seed.latitude == 35.1495
    assert poi_seed.longitude == -90.049
    assert marked_seed is not None
    assert marked_seed.use_for_internal_search is True
    assert marked_seed.use_for_app_search is True


def test_admin_region_pages_and_search_seed_filters(tmp_path) -> None:
    with make_client(tmp_path) as client:
        region_id = seed_region_fixture(client)
        with client.app.state.SessionLocal() as session:
            seed_search_locations_from_pois(session)

        regions_login = client.get("/admin/regions", follow_redirects=False)
        seeds_login = client.get("/admin/search-seeds", follow_redirects=False)
        regions = admin_get(client, "/admin/regions")
        detail = admin_get(client, f"/admin/regions/{region_id}")
        events = admin_get(client, f"/admin/regions/{region_id}/events")
        pois = admin_get(client, f"/admin/regions/{region_id}/pois")
        sources = admin_get(client, f"/admin/regions/{region_id}/sources")
        quality = admin_get(client, f"/admin/regions/{region_id}/quality")
        seeds = admin_get(client, "/admin/search-seeds?seed_type=venue")

    assert regions_login.status_code == 303
    assert seeds_login.status_code == 303
    assert "Memphis Music Region" in regions.text
    assert "Events" in detail.text
    assert "Region Fixture Concert" in events.text
    assert "Region Fixture Venue POI" in pois.text
    assert "Region Fixture Source" in sources.text
    assert "No quality snapshot yet" in quality.text
    assert "Region Fixture Venue POI" in seeds.text


def test_region_quality_snapshot_counts_issues(tmp_path) -> None:
    with make_client(tmp_path) as client:
        region_id = seed_region_fixture(client)
        with client.app.state.SessionLocal() as session:
            event = session.get(Event, 1)
            assert event is not None
            event.tickets_link = None
            event.ticket_link_classification = "missing"
            event.duplicate_status = "duplicate_candidate"
            snapshot = compute_region_quality_snapshot(session, region_id)
            stored = session.get(RegionQualitySnapshot, snapshot.id)

    assert stored is not None
    assert stored.event_count == 1
    assert stored.poi_count == 1
    assert stored.source_count == 1
    assert stored.missing_image_count == 1
    assert stored.bad_ticket_count == 1
    assert stored.duplicate_event_candidate_count == 1
    assert stored.extraction_failure_count == 1
    assert stored.snapshot["approved_source_count"] == 1


def test_region_quality_generate_requires_csrf(tmp_path) -> None:
    with make_client(tmp_path) as client:
        region_id = seed_region_fixture(client)
        login_admin(client)
        no_csrf = client.post(
            f"/admin/regions/{region_id}/quality/generate",
            follow_redirects=False,
        )
        generated = admin_post(
            client,
            f"/admin/regions/{region_id}/quality/generate",
            follow_redirects=False,
        )
        with client.app.state.SessionLocal() as session:
            snapshots = list(session.scalars(select(RegionQualitySnapshot)).all())

    assert no_csrf.status_code == 403
    assert generated.status_code == 303
    assert len(snapshots) == 1


def test_region_app_feed_json_filters_records_and_keeps_pois_non_concert(
    tmp_path,
) -> None:
    with make_client(tmp_path) as client:
        region_id = seed_region_fixture(client)
        with client.app.state.SessionLocal() as session:
            other_region = create_or_update_region(
                session,
                name="Nashville",
                region_type="city",
                city="Nashville",
                state="TN",
                country="US",
            )
            other_venue = EventVenue(
                venue_key="other-region-venue",
                display_name="Other Region Venue",
                city="Nashville",
                state="TN",
                country="US",
            )
            session.add(other_venue)
            session.flush()
            session.add(
                Event(
                    event_venue_id=other_venue.id,
                    region_id=other_region.id,
                    category="Concert",
                    record_type="event",
                    source_type="file_upload",
                    title="Other Region Concert",
                    start_datetime=datetime.fromisoformat("2026-08-02T20:00:00"),
                    tickets_link="https://tickets.example/other-region",
                    publish_status="approved",
                    dedupe_key="other-region-concert",
                    raw_event_json="{}",
                )
            )
            session.add(
                PoiLocation(
                    canonical_poi_id="concert-poi-should-not-export",
                    poi_dedupe_key="concert-poi-should-not-export",
                    display_name="Concert Row",
                    normalized_name="concert row",
                    category="Concert",
                    city="Memphis",
                    state="TN",
                    country="US",
                    region_id=region_id,
                    publish_status="approved",
                )
            )
            session.commit()
        login_admin(client)
        events = client.get(f"/admin/app-feed/regions/{region_id}/events.json")
        pois = client.get(f"/admin/app-feed/regions/{region_id}/pois.json")
        venues = client.get(f"/admin/app-feed/regions/{region_id}/venues.json")

    assert events.status_code == 200
    titles = {record["title"] for record in events.json()["records"]}
    assert "Region Fixture Concert" in titles
    assert "Other Region Concert" not in titles
    assert pois.status_code == 200
    names = {record["name"] for record in pois.json()["records"]}
    assert "Region Fixture Venue POI" in names
    assert "Concert Row" not in names
    assert venues.status_code == 200
    venue_names = {record["name"] for record in venues.json()["records"]}
    assert "Region Test Venue" in venue_names


def test_region_layer_adds_no_external_calls_or_cityspark_scraping() -> None:
    service_text = Path("app/services/region_service.py").read_text()
    cli_text = Path("app/tools/seed_search_locations.py").read_text()

    assert "httpx" not in service_text
    assert "requests" not in service_text
    assert "urllib" not in service_text
    assert "api_key" not in service_text.lower()
    assert "cityspark" not in service_text.lower()
    assert "httpx" not in cli_text
    assert "requests" not in cli_text


def test_source_quality_grade_thresholds() -> None:
    assert grade_score(100) == "excellent"
    assert grade_score(90) == "excellent"
    assert grade_score(89) == "good"
    assert grade_score(75) == "good"
    assert grade_score(74) == "fair"
    assert grade_score(60) == "fair"
    assert grade_score(59) == "poor"
    assert grade_score(40) == "poor"
    assert grade_score(39) == "blocked"
    assert grade_score(None) == "unknown"


def test_master_source_quality_scores_good_and_weak_sources(tmp_path) -> None:
    with make_client(tmp_path) as client:
        ids = seed_source_quality_fixture(client)
        with client.app.state.SessionLocal() as session:
            good_score = compute_source_quality_for_master_source(
                session,
                ids["good_source_id"],
            )
            weak_score = compute_source_quality_for_master_source(
                session,
                ids["weak_source_id"],
            )
            weak_source = session.get(MasterCalendarSource, ids["weak_source_id"])

    assert good_score.score == 100
    assert good_score.score_grade == "excellent"
    assert good_score.app_feed_ready_count == 1
    assert weak_score.score < good_score.score
    assert weak_score.extraction_failure_count == 1
    assert weak_score.duplicate_candidate_count == 1
    assert weak_score.missing_ticket_count == 1
    assert weak_score.missing_image_count == 1
    assert weak_score.generic_image_blocked_count == 1
    assert any("extraction failures" in item for item in weak_score.recommendations)
    assert weak_source is not None
    assert weak_source.source_trust_score == weak_score.score
    assert weak_source.last_quality_score_id == weak_score.id


def test_empty_source_quality_returns_fair_safely(tmp_path) -> None:
    with make_client(tmp_path) as client:
        with client.app.state.SessionLocal() as session:
            source = MasterCalendarSource(
                canonical_url="https://empty.example/events",
                canonical_url_hash="empty-source",
                original_url="https://empty.example/events",
                source_name="Empty Source",
            )
            session.add(source)
            session.commit()
            score = compute_source_quality_for_master_source(session, source.id)

    assert score.score == 60
    assert score.score_grade == "fair"
    assert score.event_count == 0


def test_source_quality_for_api_provider_region_and_partner(tmp_path) -> None:
    with make_client(tmp_path) as client:
        ids = seed_source_quality_fixture(client)
        with client.app.state.SessionLocal() as session:
            provider_score = compute_source_quality_for_api_provider(session, "jambase")
            region_score = compute_source_quality_for_region(
                session,
                ids["region_id"],
            )
            partner_score = compute_source_quality_for_partner(
                session,
                ids["partner_id"],
            )

    assert provider_score.provider_key == "jambase"
    assert provider_score.event_count >= 1
    assert region_score.region_id == ids["region_id"]
    assert region_score.event_count == 2
    assert region_score.missing_ticket_count == 1
    assert partner_score.partner_id == ids["partner_id"]
    assert partner_score.region_id == ids["region_id"]


def test_region_partner_report_includes_counts_and_exports(tmp_path) -> None:
    with make_client(tmp_path) as client:
        ids = seed_source_quality_fixture(client)
        with client.app.state.SessionLocal() as session:
            compute_source_quality_for_master_source(session, ids["good_source_id"])
            compute_source_quality_for_master_source(session, ids["weak_source_id"])
            report = generate_region_partner_report(
                session,
                ids["region_id"],
                generated_by="tester",
            )
            json_export = export_partner_report_json(report)
            csv_export = export_partner_report_csv(report)
            stored = session.get(PartnerReport, report.id)

    assert stored is not None
    assert report.status == "generated"
    assert report.metrics["event_count"] == 2
    assert report.metrics["poi_count"] == 0
    assert report.metrics["app_feed_ready_events"] == 1
    assert report.metrics["approved_calendar_sources"] == 2
    assert "source_quality_grades" in report.metrics
    assert json_export["metrics"]["event_count"] == 2
    assert "Region Quality" not in csv_export
    assert "event_count" in csv_export
    assert "missing ticket" in " ".join(str(item) for item in report.recommendations)


def test_source_quality_report_exports_rows(tmp_path) -> None:
    with make_client(tmp_path) as client:
        ids = seed_source_quality_fixture(client)
        with client.app.state.SessionLocal() as session:
            compute_source_quality_for_master_source(session, ids["good_source_id"])
            compute_source_quality_for_master_source(session, ids["weak_source_id"])
            report = generate_source_quality_report(
                session,
                region_id=ids["region_id"],
                generated_by="tester",
            )

    assert report.report_type == "source_quality"
    assert report.metrics["score_count"] >= 2
    assert report.metrics["ticket_issue_count"] >= 1
    assert report.metrics["image_issue_count"] >= 1


def test_source_quality_and_partner_report_admin_pages(tmp_path) -> None:
    with make_client(tmp_path) as client:
        ids = seed_source_quality_fixture(client)
        with client.app.state.SessionLocal() as session:
            score = compute_source_quality_for_master_source(
                session,
                ids["weak_source_id"],
            )
            report = generate_region_partner_report(session, ids["region_id"])

        source_quality_login = client.get(
            "/admin/source-quality",
            follow_redirects=False,
        )
        reports_login = client.get(
            "/admin/partner-reports",
            follow_redirects=False,
        )
        region_report_login = client.get(
            f"/admin/regions/{ids['region_id']}/report",
            follow_redirects=False,
        )
        source_quality = admin_get(client, "/admin/source-quality")
        source_detail = admin_get(client, f"/admin/source-quality/{score.id}")
        reports = admin_get(client, "/admin/partner-reports")
        report_detail = admin_get(client, f"/admin/partner-reports/{report.id}")
        region_report = admin_get(client, f"/admin/regions/{ids['region_id']}/report")
        report_json = admin_get(
            client,
            f"/admin/partner-reports/{report.id}/report.json",
        )
        report_csv = admin_get(
            client,
            f"/admin/partner-reports/{report.id}/report.csv",
        )

    assert source_quality_login.status_code == 303
    assert reports_login.status_code == 303
    assert region_report_login.status_code == 303
    assert "Weak Calendar" in source_quality.text
    assert "Score Inputs JSON" in source_detail.text
    assert "Partner Reports" in reports.text
    assert "Partner Report" in report_detail.text
    assert "Trust Score Region Partner Report" in region_report.text
    assert report_json.status_code == 200
    assert report_json.json()["metrics"]["event_count"] == 2
    assert report_csv.status_code == 200
    assert "event_count" in report_csv.text


def test_generate_region_report_action_requires_csrf(tmp_path) -> None:
    with make_client(tmp_path) as client:
        ids = seed_source_quality_fixture(client)
        login_admin(client)
        no_csrf = client.post(
            f"/admin/regions/{ids['region_id']}/report/generate",
            follow_redirects=False,
        )
        generated = admin_post(
            client,
            f"/admin/regions/{ids['region_id']}/report/generate",
            follow_redirects=False,
        )
        with client.app.state.SessionLocal() as session:
            reports = list(session.scalars(select(PartnerReport)).all())

    assert no_csrf.status_code == 403
    assert generated.status_code == 303
    assert len(reports) == 1


def test_source_quality_jobs_and_scheduled_task(tmp_path) -> None:
    with make_client(tmp_path) as client:
        ids = seed_source_quality_fixture(client)
        with client.app.state.SessionLocal() as session:
            source_job = enqueue_job(
                session,
                "source_quality_rollup",
                {
                    "source_kind": "master_calendar_source",
                    "source_id": ids["weak_source_id"],
                },
            )
            report_job = enqueue_job(
                session,
                "region_partner_report",
                {"region_id": ids["region_id"]},
            )
            processed_source = process_next_job(
                session,
                client.app.state.settings,
                worker_id="test-worker",
            )
            processed_report = process_next_job(
                session,
                client.app.state.settings,
                worker_id="test-worker",
            )
            task = next(
                task
                for task in list_scheduled_tasks(session)
                if task.task_key == "source_quality_rollup_all"
            )
            scheduled_job = enqueue_scheduled_task_now(session, task.id)
            assert scheduled_job is not None
            processed_scheduled = process_next_job(
                session,
                client.app.state.settings,
                worker_id="test-worker",
            )
            scores = list(session.scalars(select(SourceQualityScore)).all())
            reports = list(session.scalars(select(PartnerReport)).all())

    assert source_job.id == 1
    assert report_job.id == 2
    assert processed_source is not None
    assert processed_source.status == "success"
    assert processed_report is not None
    assert processed_report.status == "success"
    assert processed_scheduled is not None
    assert processed_scheduled.status == "success"
    assert scores
    assert reports


def test_source_trust_safety_boundaries() -> None:
    source_quality_text = Path("app/services/source_quality_service.py").read_text()
    partner_report_text = Path("app/services/partner_report_service.py").read_text()
    combined = source_quality_text + partner_report_text

    assert "httpx" not in combined
    assert "requests" not in combined
    assert "urllib" not in combined
    assert "api_key" not in combined.lower()
    assert "cityspark" not in combined.lower()
    assert "category=\"Concert\"" in Path("tests/test_app.py").read_text()
    assert (
        'category == "Concert"'
        in Path("app/services/source_quality_service.py").read_text()
    )


def test_app_feed_admin_page_and_private_api_gating(tmp_path) -> None:
    with make_client(tmp_path) as client:
        response = client.get("/admin/app-feed", follow_redirects=False)
        assert response.status_code == 303

        response = client.get("/api/app/events")
        assert response.status_code == 404

        login_admin(client)
        response = client.get("/admin/app-feed")
        assert response.status_code == 200
        assert "App Feed" in response.text

        response = client.get("/api/app/events")
        assert response.status_code == 200

    with make_client_with_public_app_feed(tmp_path / "public") as public_client:
        response = public_client.get("/api/app/events")
        assert response.status_code == 200


def test_app_search_index_rebuilds_internal_entities_without_duplicates(
    tmp_path,
) -> None:
    with make_client(tmp_path) as client:
        seed_app_search_contract_records(client)
        with client.app.state.SessionLocal() as session:
            counts = rebuild_search_index(session)
            first_entries = list(session.scalars(select(AppSearchIndex)).all())
            first_total = len(first_entries)

            assert counts["regions"] == 1
            assert counts["events"] == 1
            assert counts["search_seeds"] == 1
            assert counts["pois"] >= 3
            assert counts["venues"] == 1
            assert first_total == sum(counts.values())
            assert all(
                entry.entity_type == "event"
                for entry in first_entries
                if entry.category == "Concert"
            )
            assert not any(
                entry.display_name == "Rejected Search Secret"
                for entry in first_entries
            )

            second_counts = rebuild_search_index(session)
            second_total = len(list(session.scalars(select(AppSearchIndex)).all()))

            assert second_counts == counts
            assert second_total == first_total


def test_app_search_ranking_seeds_and_exclusions(tmp_path) -> None:
    with make_client(tmp_path) as client:
        seed_app_search_contract_records(client)
        with client.app.state.SessionLocal() as session:
            rebuild_search_index(session)

            region_results = search_app_index(session, "Memphis Music Region")
            assert region_results["results"][0]["entity_type"] == "region"

            boosted = search_app_index(session, "Boost Studio", limit=2)
            assert boosted["results"][0]["title"] == "Boost Studio Certified"
            assert "Certified" in boosted["results"][0]["badges"]

            seed_results = search_app_index(session, "airport")
            assert any(
                result["entity_type"] == "search_seed"
                for result in seed_results["results"]
            )

            suggestions = suggest_app_search(session, "memphis", limit=5)
            assert suggestions["suggestions"]
            assert "SEARCH_SECRET_SHOULD_NOT_LEAK" not in json.dumps(region_results)
            assert search_app_index(session, "Rejected Search Secret")["results"] == []


def test_app_search_admin_routes_and_private_api_gating(tmp_path) -> None:
    with make_client(tmp_path) as client:
        seed_app_feed_records(client)
        response = client.get("/admin/app-search", follow_redirects=False)
        assert response.status_code == 303
        assert client.get("/api/app/search?q=River").status_code == 404

        login_admin(client)
        with client.app.state.SessionLocal() as session:
            rebuild_search_index(session)

        page = client.get("/admin/app-search?q=River")
        assert page.status_code == 200
        assert "App Search" in page.text
        assert "River Stage Night" in page.text

        results = client.get("/admin/app-search/results.json?q=River")
        assert results.status_code == 200
        assert "River Stage Night" in results.text
        assert "SECRET_API_KEY_SHOULD_NOT_LEAK" not in results.text
        assert "raw_provider_json" not in results.text

        suggestions = client.get("/admin/app-search/suggest.json?q=River")
        assert suggestions.status_code == 200
        assert suggestions.json()["suggestions"]

        private_api = client.get("/api/app/search?q=River")
        assert private_api.status_code == 200
        assert "SECRET_API_KEY_SHOULD_NOT_LEAK" not in private_api.text

    with make_client_with_public_app_feed(tmp_path / "public-search") as public_client:
        public_response = public_client.get("/api/app/search?q=anything")
        assert public_response.status_code == 200


def test_app_search_rebuild_requires_csrf(tmp_path) -> None:
    with make_client(tmp_path) as client:
        seed_app_search_contract_records(client)
        login_admin(client)

        no_csrf = client.post("/admin/app-search/rebuild-index")
        assert no_csrf.status_code == 403

        response = admin_post(
            client,
            "/admin/app-search/rebuild-index",
            follow_redirects=False,
        )
        assert response.status_code == 303
        with client.app.state.SessionLocal() as session:
            assert list(session.scalars(select(AppSearchIndex)).all())


def test_map_marker_metadata_contract_keeps_events_and_pois_distinct(tmp_path) -> None:
    with make_client(tmp_path) as client:
        ids = seed_app_search_contract_records(client)
        with client.app.state.SessionLocal() as session:
            event = session.scalars(
                select(Event).where(Event.title == "Region Fixture Concert"),
            ).one()
            event_marker = build_map_marker(event)
            assert event_marker["entity_type"] == "event"
            assert event_marker["marker"]["icon_key"] == "event_ticket"
            assert event_marker["marker"]["icon_key"] != "music_note"
            assert event_marker["category"] == "Concert"

            certified_poi = session.get(PoiLocation, ids["certified_poi_id"])
            assert certified_poi is not None
            poi_marker = build_map_marker(certified_poi)
            assert poi_marker["entity_type"] == "poi"
            assert poi_marker["marker"]["glow"] is True
            assert poi_marker["category"] == "Music Site"

            marker_payload = list_map_markers(session)
            entity_types = {
                record["entity_type"] for record in marker_payload["records"]
            }
            assert {"event", "poi"}.issubset(entity_types)
            poi_titles = {
                record["title"]
                for record in marker_payload["records"]
                if record["entity_type"] == "poi"
            }
            assert "Region Fixture Concert" not in poi_titles
            assert "music-roadtrip-logo" not in json.dumps(marker_payload)


def test_map_marker_admin_and_api_routes(tmp_path) -> None:
    with make_client(tmp_path) as client:
        ids = seed_app_search_contract_records(client)
        login_admin(client)

        response = client.get("/admin/app-feed/map-markers.json")
        assert response.status_code == 200
        payload = response.json()
        assert any(record["entity_type"] == "event" for record in payload["records"])
        assert any(record["entity_type"] == "poi" for record in payload["records"])

        poi_response = client.get("/admin/app-feed/map-markers.json?entity_type=poi")
        assert poi_response.status_code == 200
        assert all(
            record["entity_type"] == "poi"
            for record in poi_response.json()["records"]
        )
        assert "Region Fixture Concert" not in poi_response.text

        region_response = client.get(
            f"/admin/app-feed/regions/{ids['region_id']}/map-markers.json",
        )
        assert region_response.status_code == 200
        assert region_response.json()["region"]["id"] == ids["region_id"]

        private_api = client.get("/api/app/map-markers?entity_type=event")
        assert private_api.status_code == 200
        assert all(
            record["entity_type"] == "event"
            for record in private_api.json()["records"]
        )


def test_filter_options_separate_event_and_poi_filters(tmp_path) -> None:
    with make_client(tmp_path) as client:
        ids = seed_app_search_contract_records(client)
        with client.app.state.SessionLocal() as session:
            options = build_filter_options(session, region_id=ids["region_id"])

        category_names = {
            category["name"]
            for category in options["poi_filters"]["categories"]
        }
        assert "Concert" not in category_names
        assert "Music Site" in category_names
        music_site = next(
            category
            for category in options["poi_filters"]["categories"]
            if category["name"] == "Music Site"
        )
        assert any(
            subcategory["name"] == "Recording Studios"
            for subcategory in music_site["subcategories"]
        )
        assert "event_filters" in options
        assert "poi_filters" in options
        assert options["active_filter_display_rules"]["show_badge"] is True

        login_admin(client)
        response = client.get("/admin/app-feed/filter-options.json")
        assert response.status_code == 200
        assert "Concert" not in {
            category["name"]
            for category in response.json()["poi_filters"]["categories"]
        }

        region_response = client.get(
            f"/admin/app-feed/regions/{ids['region_id']}/filter-options.json",
        )
        assert region_response.status_code == 200
        assert region_response.json()["region"]["id"] == ids["region_id"]


def test_discovery_slots_contract_and_region_filter(tmp_path) -> None:
    with make_client(tmp_path) as client:
        ids = seed_app_search_contract_records(client)
        with client.app.state.SessionLocal() as session:
            global_slots = list_discovery_slots(session)
            assert global_slots["records"]
            session.add(
                AppDiscoverySlot(
                    slot_key="region-memphis-highlights",
                    slot_type="poi_carousel",
                    title="Memphis Highlights",
                    description="Region-specific POI carousel.",
                    region_id=ids["region_id"],
                    enabled=True,
                    sort_order=5,
                    payload_json='{"category":"Music Site"}',
                ),
            )
            session.commit()
            region_slots = list_discovery_slots(session, ids["region_id"])
            assert [slot["title"] for slot in region_slots["records"]] == [
                "Memphis Highlights"
            ]

        login_admin(client)
        response = client.get("/admin/app-feed/discovery.json")
        assert response.status_code == 200
        assert response.json()["records"]

        region_response = client.get(
            f"/admin/app-feed/regions/{ids['region_id']}/discovery.json",
        )
        assert region_response.status_code == 200
        assert region_response.json()["records"][0]["title"] == "Memphis Highlights"


def test_itinerary_service_stops_quality_reorder_and_app_feed(tmp_path) -> None:
    with make_client(tmp_path) as client:
        ids = seed_itinerary_contract_records(client)
        with client.app.state.SessionLocal() as session:
            itinerary = session.get(Itinerary, ids["itinerary_id"])
            assert itinerary is not None
            score, flags = compute_itinerary_quality(session, itinerary.id)
            assert score >= 70
            assert "too_few_stops" not in flags

            feed = build_itinerary_app_feed(session, itinerary.id)
            assert feed["itinerary_id"] == f"itinerary-{itinerary.id}"
            assert feed["display_label"] == "Road Trip"
            assert len(feed["stops"]) == 3
            assert feed["stops"][0]["stop_type"] == "event"
            assert feed["stops"][1]["stop_type"] == "poi"
            assert feed["segments"]
            assert "raw_event_json" not in json.dumps(feed)
            assert "source_claim" not in json.dumps(feed)
            assert "SECRET" not in json.dumps(feed)

            first_segment = itinerary.segments[0]
            nav_url = build_external_navigation_link(first_segment)
            assert nav_url.startswith("https://www.google.com/maps/dir/")
            assert "api_key" not in nav_url

            moved = move_stop(
                session,
                itinerary.id,
                ids["poi_stop_id"],
                direction="up",
            )
            assert moved[0].id == ids["poi_stop_id"]
            remove_stop(session, itinerary.id, ids["artist_stop_id"])
            reloaded = session.get(Itinerary, itinerary.id)
            assert reloaded is not None
            assert len(reloaded.stops) == 2


def test_itinerary_quality_flags_rejected_event_and_concert_stays_event(
    tmp_path,
) -> None:
    with make_client(tmp_path) as client:
        ids = seed_itinerary_contract_records(client)
        with client.app.state.SessionLocal() as session:
            rejected_event = session.get(Event, ids["rejected_event_id"])
            assert rejected_event is not None
            rejected_event.publish_status = "approved"
            rejected_event.duplicate_status = "merged"
            session.add(rejected_event)
            session.commit()

            itinerary = create_itinerary(
                session,
                ItineraryCreate(
                    title="Merged Event Route",
                    status="approved",
                    region_id=ids["region_id"],
                    hero_image_url="https://images.example/merged-route.jpg",
                ),
            )
            add_stop(
                session,
                itinerary.id,
                ItineraryStopInput(stop_type="event", event_id=rejected_event.id),
            )
            add_stop(
                session,
                itinerary.id,
                ItineraryStopInput(
                    stop_type="poi",
                    poi_location_id=ids["plain_poi_id"],
                ),
            )
            _, flags = compute_itinerary_quality(session, itinerary.id)

            assert any("rejected_or_merged_event" in flag for flag in flags)
            concert_entries = [
                stop
                for stop in build_itinerary_app_feed(session, itinerary.id)["stops"]
                if stop["reference"]["event_id"]
            ]
            assert concert_entries
            assert concert_entries[0]["stop_type"] == "event"
            assert not any(stop["stop_type"] == "poi" for stop in concert_entries)


def test_itinerary_admin_preview_and_private_feed_routes(tmp_path) -> None:
    with make_client(tmp_path) as client:
        ids = seed_itinerary_contract_records(client)

        assert (
            client.get("/admin/itineraries", follow_redirects=False).status_code
            == 303
        )
        assert (
            client.get("/preview/itineraries", follow_redirects=False).status_code
            == 303
        )
        assert client.get("/api/app/itineraries").status_code == 404

        login_admin(client)
        itinerary_list = client.get("/admin/itineraries")
        assert itinerary_list.status_code == 200
        assert "Deferred / App team feature" in itinerary_list.text
        assert "Scott's current workflow is calendar ingest" in itinerary_list.text
        assert (
            client.get(f"/admin/itineraries/{ids['itinerary_id']}").status_code
            == 200
        )
        assert (
            client.get(
                f"/admin/itineraries/{ids['itinerary_id']}/stops"
            ).status_code
            == 200
        )
        assert (
            client.get(
                f"/admin/itineraries/{ids['itinerary_id']}/preview"
            ).status_code
            == 200
        )
        assert client.get("/preview/itineraries").status_code == 200
        assert (
            client.get(f"/preview/itineraries/{ids['itinerary_id']}").status_code
            == 200
        )

        no_csrf = client.post(
            f"/admin/itineraries/{ids['itinerary_id']}/stops",
            data={"stop_type": "custom", "title": "No CSRF"},
        )
        assert no_csrf.status_code == 403

        feed = client.get("/admin/app-feed/itineraries.json")
        assert feed.status_code == 200
        assert feed.json()["records"][0]["title"] == "Memphis Road Trip Contract"
        detail = client.get(f"/admin/app-feed/itineraries/{ids['itinerary_id']}.json")
        assert detail.status_code == 200
        region_feed = client.get(
            f"/admin/app-feed/regions/{ids['region_id']}/itineraries.json",
        )
        assert region_feed.status_code == 200
        artist_feed = client.get(
            f"/admin/app-feed/artists/{ids['artist_id']}/itineraries.json",
        )
        assert artist_feed.status_code == 200

        private_feed = client.get("/api/app/itineraries")
        assert private_feed.status_code == 200
        assert private_feed.json()["records"][0]["itinerary_id"] == (
            f"itinerary-{ids['itinerary_id']}"
        )

    with make_client_with_public_app_feed(
        tmp_path / "public-itineraries"
    ) as public_client:
        public_response = public_client.get("/api/app/itineraries")
        assert public_response.status_code == 200


def test_itineraries_index_discovery_filter_options_and_jobs(tmp_path) -> None:
    with make_client(tmp_path) as client:
        ids = seed_itinerary_contract_records(client)
        with client.app.state.SessionLocal() as session:
            counts = rebuild_search_index(session)
            assert counts["itineraries"] == 1
            search_payload = search_app_index(session, "Memphis Road Trip")
            assert search_payload["results"][0]["entity_type"] == "itinerary"

            options = build_filter_options(session, region_id=ids["region_id"])
            itinerary_types = {
                item["name"] for item in options["itinerary_filters"]["types"]
            }
            assert "road_trip" in itinerary_types
            category_names = {
                category["name"]
                for category in options["poi_filters"]["categories"]
            }
            assert "Concert" not in category_names

            discovery = list_discovery_slots(session)
            assert any(
                slot["slot_type"] == "itinerary_carousel"
                for slot in discovery["records"]
            )

            enqueue_job(
                session,
                "itinerary_quality_rollup",
                {"itinerary_id": ids["itinerary_id"]},
            )
            quality_job = process_next_job(
                session,
                client.app.state.settings,
                worker_id="itinerary-worker",
            )
            assert quality_job is not None
            assert quality_job.status == "success"
            assert quality_job.result["itinerary_count"] == 1

            enqueue_job(session, "itinerary_app_feed_export", {})
            feed_job = process_next_job(
                session,
                client.app.state.settings,
                worker_id="itinerary-worker",
            )
            assert feed_job is not None
            assert feed_job.status == "success"
            assert feed_job.result["export_type"] == "itineraries"

            enqueue_job(
                session,
                "build_region_itinerary_suggestions",
                {"region_id": ids["region_id"]},
            )
            region_job = process_next_job(
                session,
                client.app.state.settings,
                worker_id="itinerary-worker",
            )
            assert region_job is not None
            assert region_job.status == "success"

            enqueue_job(
                session,
                "build_artist_tour_itinerary",
                {"artist_id": ids["artist_id"]},
            )
            artist_job = process_next_job(
                session,
                client.app.state.settings,
                worker_id="itinerary-worker",
            )
            assert artist_job is not None
            assert artist_job.status == "success"

            records = list_app_itineraries(session)
            assert any(record["type"] == "road_trip" for record in records)


def test_itinerary_contract_safety_no_external_calls_or_logo_fallbacks() -> None:
    service_text = Path("app/services/itinerary_service.py").read_text()
    lowered = service_text.lower()
    assert "httpx" not in lowered
    assert "requests" not in lowered
    assert "urllib.request" not in lowered
    assert "api_key" not in lowered
    assert "client_secret" not in lowered


def test_scott_scope_docs_defer_itinerary_app_work() -> None:
    scope_doc = Path("docs/scott-data-pipeline-scope.md").read_text()
    readme = Path("README.md").read_text()
    agents = Path("AGENTS.md").read_text()
    itinerary_doc = Path("docs/itinerary-roadtrip-contract.md").read_text()

    assert "Scott Data Pipeline Scope" in scope_doc
    assert "calendar ingest" in scope_doc
    assert "API Feed Review Workbench" in scope_doc
    assert "event photo rescue" in scope_doc
    assert "POI registry and POI audit" in scope_doc
    assert "Out Of Scope" in scope_doc
    assert "User route builder" in scope_doc
    assert "Itineraries" in scope_doc
    assert "Deferred / App team feature" in readme
    assert "Do not propose or implement route-builder" in agents
    assert "Deferred Itinerary Road Trip Contract" in itinerary_doc
    assert "Do not expand Road Trip" in itinerary_doc


def test_app_search_and_map_jobs_and_scheduled_task(tmp_path) -> None:
    with make_client(tmp_path) as client:
        seed_app_search_contract_records(client)
        with client.app.state.SessionLocal() as session:
            enqueue_job(session, "rebuild_app_search_index", {})
            processed = process_next_job(
                session,
                client.app.state.settings,
                worker_id="search-worker",
            )
            assert processed is not None
            assert processed.status == "success"
            assert list(session.scalars(select(AppSearchIndex)).all())

            enqueue_job(session, "app_map_feed_export", {"limit": 50})
            map_job = process_next_job(
                session,
                client.app.state.settings,
                worker_id="search-worker",
            )
            assert map_job is not None
            assert map_job.status == "success"
            assert map_job.result["export_type"] == "map_markers"

            enqueue_job(session, "app_filter_options_export", {})
            filter_job = process_next_job(
                session,
                client.app.state.settings,
                worker_id="search-worker",
            )
            assert filter_job is not None
            assert filter_job.status == "success"
            assert filter_job.result["export_type"] == "filter_options"

            task = next(
                item
                for item in list_scheduled_tasks(session)
                if item.task_key == "rebuild_app_search_index"
            )
            queued = enqueue_scheduled_task_now(session, task.id)
            assert queued is not None
            assert queued.job_type == "rebuild_app_search_index"


def test_app_search_and_map_contract_has_no_external_calls_or_logo_markers() -> None:
    service_text = (
        Path("app/services/app_search_service.py").read_text()
        + Path("app/services/map_display_service.py").read_text()
    )
    lowered = service_text.lower()
    assert "httpx" not in lowered
    assert "requests" not in lowered
    assert "urllib.request" not in lowered
    assert "api_key" not in lowered
    assert "music-roadtrip-logo" not in lowered


def test_app_event_feed_is_sanitized_and_excludes_blocked_records(tmp_path) -> None:
    with make_client(tmp_path) as client:
        seed_app_feed_records(client)
        login_admin(client)

        response = client.get("/admin/app-feed/events.json")
        assert response.status_code == 200
        payload = response.json()
        titles = {record["title"] for record in payload["records"]}

        assert "River Stage Night" in titles
        assert "No Venue Yet" in titles
        assert "Rejected Show" not in titles
        assert "Duplicate Candidate Show" not in titles
        assert "Cancelled Show" not in titles
        assert "SECRET_API_KEY_SHOULD_NOT_LEAK" not in response.text
        assert "SECRET_SOURCE_CLAIM" not in response.text
        assert "raw_provider_json" not in response.text
        assert "raw_payload_json" not in response.text

        event = next(
            record
            for record in payload["records"]
            if record["title"] == "River Stage Night"
        )
        assert event["record_type"] == "event"
        assert event["category"] == "Concert"
        assert event["image"]["needs_approval"] is True
        assert event["source"]["source_claim_count"] == 1
        assert event["tickets"]["classification"] == "primary"
        assert event["venue"]["name"] == "River Stage"

        missing_venue = next(
            record for record in payload["records"] if record["title"] == "No Venue Yet"
        )
        assert "missing_venue" in missing_venue["quality"]["flags"]

        response = client.get("/admin/app-feed/events.json?include_cancelled=true")
        assert response.status_code == 200
        titles = {record["title"] for record in response.json()["records"]}
        assert "Cancelled Show" in titles


def test_app_poi_feed_excludes_concert_and_preserves_safe_fields(tmp_path) -> None:
    with make_client(tmp_path) as client:
        seed_app_feed_records(client)
        login_admin(client)

        response = client.get("/admin/app-feed/pois.json")
        assert response.status_code == 200
        payload = response.json()
        names = {record["name"] for record in payload["records"]}

        assert "River Records" in names
        assert "Logo Museum" in names
        assert "Concert Row" not in names
        assert "RAW_POI_SECRET" not in response.text
        assert "raw_source_json" not in response.text

        record_shop = next(
            record for record in payload["records"] if record["name"] == "River Records"
        )
        assert record_shop["zip_code"] == "03810"
        assert record_shop["latitude"] == 35.14
        assert record_shop["longitude"] == -90.05

        logo_place = next(
            record for record in payload["records"] if record["name"] == "Logo Museum"
        )
        assert logo_place["image"]["url"] == ""
        assert "logo_asset_suppressed" in logo_place["image"]["flags"]


def test_app_feed_export_requires_csrf_and_creates_export_row(tmp_path) -> None:
    with make_client(tmp_path) as client:
        seed_app_feed_records(client)
        login_admin(client)

        response = client.post(
            "/admin/app-feed/export",
            data={"export_type": "events"},
            follow_redirects=False,
        )
        assert response.status_code == 403

        response = admin_post(
            client,
            "/admin/app-feed/export",
            data={"export_type": "events"},
            follow_redirects=False,
        )
        assert response.status_code == 303

        with client.app.state.SessionLocal() as session:
            export = session.scalars(select(AppFeedExport)).one()
            assert export.export_type == "events"
            assert export.status == "success"
            assert export.record_count == 2
            assert export.output_json is not None
            assert "River Stage Night" in export.output_json
            assert "SECRET_API_KEY_SHOULD_NOT_LEAK" not in export.output_json


def test_background_job_lifecycle_and_secret_redaction(tmp_path) -> None:
    with make_client(tmp_path) as client:
        with client.app.state.SessionLocal() as session:
            job = enqueue_job(
                session,
                "app_feed_export",
                {
                    "export_type": "events",
                    "url": "https://provider.test/events?apikey=SECRET123&city=Memphis",
                    "headers": {"Authorization": "Bearer SECRET123"},
                },
                created_by="admin",
            )
            assert "SECRET123" not in job.payload_json
            assert "[REDACTED]" in job.payload_json

            claimed = claim_next_job(session, "worker-1")
            assert claimed is not None
            assert claimed.id == job.id
            assert claimed.status == "running"
            assert claimed.attempts == 1

            succeeded = mark_job_success(
                session,
                claimed,
                {"token": "SECRET456", "status": "ok"},
            )
            assert succeeded.status == "success"
            assert "SECRET456" not in (succeeded.result_json or "")

            failed = enqueue_job(session, "unknown", {"safe": "value"})
            failed = claim_next_job(session, "worker-1")
            assert failed is not None
            failed = mark_job_failure(session, failed, "token=SECRET789 broke")
            assert failed.status == "failure"
            assert "SECRET789" not in (failed.error_message or "")

            retried = retry_job(session, failed.id)
            assert retried is not None
            assert retried.status == "pending"
            cancelled = cancel_job(session, retried.id)
            assert cancelled is not None
            assert cancelled.status == "cancelled"

    redacted = redact_sensitive_payload(
        {
            "X-API-Key": "TOPSECRET",
            "nested": {"api_key": "ALSOSECRET"},
            "url": "https://example.test/path?access_token=URLSECRET&safe=1",
        }
    )
    assert "TOPSECRET" not in json.dumps(redacted)
    assert "ALSOSECRET" not in json.dumps(redacted)
    assert "URLSECRET" not in json.dumps(redacted)


def test_background_worker_processes_app_feed_export_job(tmp_path) -> None:
    with make_client(tmp_path) as client:
        with client.app.state.SessionLocal() as session:
            enqueue_job(session, "app_feed_export", {"export_type": "full"})

            processed = process_next_job(
                session,
                client.app.state.settings,
                worker_id="test-worker",
            )

            assert processed is not None
            assert processed.status == "success"
            exports = session.scalars(select(AppFeedExport)).all()
            assert len(exports) == 1
            assert exports[0].status == "success"


def test_background_worker_processes_poi_candidate_match_jobs(tmp_path) -> None:
    with make_client(tmp_path) as client:
        with client.app.state.SessionLocal() as session:
            candidate = add_test_poi_candidate(
                session,
                candidate_name="Worker Match Hall",
            )
            enqueue_job(session, "poi_candidate_match", {"candidate_id": candidate.id})
            single = process_next_job(
                session,
                client.app.state.settings,
                worker_id="test-worker",
            )
            add_test_poi_candidate(session, candidate_name="Worker Rollup Hall")
            enqueue_job(session, "all_poi_candidate_match", {})
            rollup = process_next_job(
                session,
                client.app.state.settings,
                worker_id="test-worker",
            )

    assert single is not None
    assert single.status == "success"
    assert single.result["poi_candidate_id"] == candidate.id
    assert rollup is not None
    assert rollup.status == "success"
    assert rollup.result["candidate_count"] >= 1


def test_worker_cli_once_processes_one_pending_job(tmp_path, monkeypatch) -> None:
    from app.core.config import get_settings
    from app.db.database import create_all, make_engine, make_session_factory
    from app.tools.run_worker import main as worker_main

    database_url = f"sqlite:///{tmp_path / 'worker-cli.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    try:
        engine = make_engine(database_url)
        create_all(engine)
        session_factory = make_session_factory(engine)
        with session_factory() as session:
            enqueue_job(session, "app_feed_export", {"export_type": "events"})

        exit_code = worker_main(["--once", "--worker-id", "cli-test-worker"])

        with session_factory() as session:
            job = session.scalars(select(BackgroundJob)).one()
            exports = list(session.scalars(select(AppFeedExport)).all())
    finally:
        get_settings.cache_clear()

    assert exit_code == 0
    assert job.status == "success"
    assert len(exports) == 1


def test_background_worker_unknown_job_fails_safely(tmp_path) -> None:
    with make_client(tmp_path) as client:
        with client.app.state.SessionLocal() as session:
            enqueue_job(session, "unknown", {"note": "unsupported"})

            processed = process_next_job(
                session,
                client.app.state.settings,
                worker_id="test-worker",
            )

            assert processed is not None
            assert processed.status == "failure"
            assert "Unknown background job type" in (processed.error_message or "")


def test_provider_sandbox_background_job_blocks_when_live_calls_disabled(
    tmp_path,
) -> None:
    with make_client(tmp_path) as client:
        with client.app.state.SessionLocal() as session:
            enqueue_job(
                session,
                "provider_sandbox_jambase",
                {"parameters": {"apikey": "SHOULD_NOT_LEAK", "limit": "5"}},
            )

            processed = process_next_job(
                session,
                client.app.state.settings,
                worker_id="test-worker",
            )

            assert processed is not None
            assert processed.status == "failure"
            assert "live calls are off" in (processed.error_message or "")
            assert "SHOULD_NOT_LEAK" not in processed.payload_json


def test_cityspark_sandbox_background_job_blocks_when_live_calls_disabled(
    tmp_path,
) -> None:
    with make_client(tmp_path) as client:
        with client.app.state.SessionLocal() as session:
            enqueue_job(
                session,
                "provider_sandbox_cityspark",
                {"parameters": {"api_key": "SHOULD_NOT_LEAK", "limit": "5"}},
            )

            processed = process_next_job(
                session,
                client.app.state.settings,
                worker_id="test-worker",
            )

            assert processed is not None
            assert processed.status == "failure"
            assert "live calls are off" in (processed.error_message or "")
            assert "SHOULD_NOT_LEAK" not in processed.payload_json


def test_event_photo_rescue_background_job_selects_image(tmp_path) -> None:
    with make_client(tmp_path) as client:
        event_id = create_preview_event(
            client,
            title="Background Photo Rescue Event",
        )
        candidate_id = create_image_candidate_for_test(
            client,
            event_id=event_id,
            image_url="https://images.example/background-artist.jpg",
            image_role="artist_press",
            rescue_source="provider_artist_image",
        )
        with client.app.state.SessionLocal() as session:
            enqueue_job(session, "event_photo_rescue", {"event_id": event_id})

            processed = process_next_job(
                session,
                client.app.state.settings,
                worker_id="test-worker",
            )
            event = session.get(Event, event_id)

    assert processed is not None
    assert processed.status == "success"
    assert processed.result["event_id"] == event_id
    assert processed.result["selected_candidate_id"] == candidate_id
    assert processed.result["selected_reason"].startswith(
        "photo_rescue_selected_artist_image"
    )
    assert event is not None
    assert event.selected_main_image_url == "https://images.example/background-artist.jpg"


def test_api_feed_run_photo_rescue_background_job_summarizes_results(
    tmp_path,
) -> None:
    with make_client(tmp_path) as client:
        event_id = create_preview_event(
            client,
            title="API Run Rescue Event",
            venue_key="api-run-rescue-venue",
        )
        create_image_candidate_for_test(
            client,
            event_id=event_id,
            image_url="https://images.example/api-run-artist.jpg",
            image_role="artist_press",
            rescue_source="provider_artist_image",
        )
        create_image_candidate_for_test(
            client,
            event_id=event_id,
            image_url="https://images.example/api-run-stock.jpg",
            image_role="stock_placeholder",
            rescue_source="provider_event_image",
        )
        with client.app.state.SessionLocal() as session:
            run = ApiFeedRun(
                provider_key="jambase",
                provider_type="licensed_vendor",
                run_mode="manual_json",
                status="success",
            )
            session.add(run)
            session.flush()
            event = session.get(Event, event_id)
            assert event is not None
            event.api_feed_run_id = run.id
            record = ApiFeedRecord(
                api_feed_run_id=run.id,
                provider_key="jambase",
                provider_type="licensed_vendor",
                provider_record_id="record-1",
                raw_payload_json="{}",
                normalized_payload_json="{}",
                normalization_status="normalized",
                review_status="approved",
                category="Concert",
                record_type="event",
                event_name=event.title,
                dedupe_key="api-run-rescue-event",
                created_event_id=event.id,
            )
            session.add(record)
            session.commit()
            enqueue_job(
                session,
                "api_feed_run_photo_rescue",
                {"api_feed_run_id": run.id},
            )

            processed = process_next_job(
                session,
                client.app.state.settings,
                worker_id="test-worker",
            )

    assert processed is not None
    assert processed.status == "success"
    assert processed.result["api_feed_run_id"] == run.id
    assert processed.result["rescued_event_count"] == 1
    assert processed.result["selected_count"] == 1
    assert processed.result["missing_usable_image_count"] == 0
    assert processed.result["blocked_generic_count"] >= 1


def test_recent_events_photo_rescue_background_job_summarizes_results(
    tmp_path,
) -> None:
    with make_client(tmp_path) as client:
        event_id = create_preview_event(
            client,
            title="Recent Background Rescue Event",
            venue_key="recent-background-rescue-venue",
        )
        create_image_candidate_for_test(
            client,
            event_id=event_id,
            image_url="https://images.example/recent-background-artist.jpg",
            image_role="artist_press",
            rescue_source="provider_artist_image",
        )
        with client.app.state.SessionLocal() as session:
            enqueue_job(
                session,
                "recent_events_photo_rescue",
                {"since_hours": 24, "limit": 10},
            )

            processed = process_next_job(
                session,
                client.app.state.settings,
                worker_id="test-worker",
            )

    assert processed is not None
    assert processed.status == "success"
    assert processed.result["rescued_event_count"] >= 1
    assert processed.result["selected_count"] >= 1
    assert any(
        item["event_id"] == event_id for item in processed.result.get("results", [])
    )


def test_crawl_source_background_job_respects_approval_gate(tmp_path) -> None:
    def forbidden_fetcher(url: str) -> FetchResult:
        raise AssertionError(f"Fetch should not run for gated source: {url}")

    with make_client(tmp_path) as client:
        with client.app.state.SessionLocal() as session:
            source = CalendarSource(
                organization_name="Pending Venue",
                calendar_url="https://example.test/events.ics",
                contact_email="owner@example.test",
                permission_confirmed=True,
            )
            session.add(source)
            session.commit()
            session.refresh(source)
            enqueue_job(session, "crawl_source", {"source_id": source.id})

            processed = process_next_job(
                session,
                client.app.state.settings,
                worker_id="test-worker",
                fetcher=forbidden_fetcher,
            )

            assert processed is not None
            assert processed.status == "failure"
            assert "Only approved sources can be crawled" in (
                processed.error_message or ""
            )


def test_scheduler_enqueues_only_due_enabled_tasks_and_updates_next_run(
    tmp_path,
) -> None:
    with make_client(tmp_path) as client:
        with client.app.state.SessionLocal() as session:
            due_task = ScheduledTask(
                task_key="test_due_export",
                task_type="app_feed_export",
                enabled=True,
                schedule_type="interval",
                interval_minutes=30,
                next_run_at=utc_now() - timedelta(minutes=5),
                payload_json=json.dumps({"export_type": "events"}),
            )
            disabled_task = ScheduledTask(
                task_key="test_disabled_export",
                task_type="app_feed_export",
                enabled=False,
                schedule_type="interval",
                interval_minutes=30,
                next_run_at=utc_now() - timedelta(minutes=5),
                payload_json=json.dumps({"export_type": "events"}),
            )
            manual_task = ScheduledTask(
                task_key="test_manual_export",
                task_type="app_feed_export",
                enabled=True,
                schedule_type="manual",
                next_run_at=utc_now() - timedelta(minutes=5),
                payload_json=json.dumps({"export_type": "events"}),
            )
            session.add_all([due_task, disabled_task, manual_task])
            session.commit()

            dry_run = enqueue_due_scheduled_tasks(session, dry_run=True)
            assert dry_run.due_task_count == 1
            assert dry_run.enqueued_job_ids == []
            assert session.scalars(select(BackgroundJob)).all() == []

            result = enqueue_due_scheduled_tasks(session)
            assert result.due_task_count == 1
            assert len(result.enqueued_job_ids) == 1
            session.refresh(due_task)
            session.refresh(disabled_task)
            session.refresh(manual_task)
            assert due_task.last_job_id == result.enqueued_job_ids[0]
            assert due_task.next_run_at is not None
            assert disabled_task.last_job_id is None
            assert manual_task.last_job_id is None


def test_scheduler_can_enqueue_recent_photo_rescue_task(tmp_path) -> None:
    with make_client(tmp_path) as client:
        with client.app.state.SessionLocal() as session:
            task = ScheduledTask(
                task_key="test_recent_photo_rescue",
                task_type="event_photo_rescue",
                enabled=True,
                schedule_type="interval",
                interval_minutes=60,
                next_run_at=utc_now() - timedelta(minutes=5),
                payload_json=json.dumps(
                    {
                        "job_type": "recent_events_photo_rescue",
                        "since_hours": 24,
                        "limit": 25,
                    }
                ),
            )
            session.add(task)
            session.commit()

            result = enqueue_due_scheduled_tasks(session)
            job = session.get(BackgroundJob, result.enqueued_job_ids[0])

    assert result.due_task_count == 1
    assert job is not None
    assert job.job_type == "recent_events_photo_rescue"
    assert job.payload["scheduled_task_key"] == "test_recent_photo_rescue"


def test_admin_jobs_and_scheduled_task_pages_require_login_and_csrf(tmp_path) -> None:
    with make_client(tmp_path) as client:
        response = client.get("/admin/jobs", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"].startswith("/admin/login")

        login_admin(client)
        jobs_page = client.get("/admin/jobs")
        tasks_page = client.get("/admin/scheduled-tasks")
        assert jobs_page.status_code == 200
        assert "Background Jobs" in jobs_page.text
        assert tasks_page.status_code == 200
        assert "Scheduled Tasks" in tasks_page.text

        missing_csrf = client.post(
            "/admin/app-feed/export/background",
            data={"export_type": "events"},
            follow_redirects=False,
        )
        assert missing_csrf.status_code == 403

        queued = admin_post(
            client,
            "/admin/app-feed/export/background",
            data={"export_type": "events"},
            follow_redirects=False,
        )
        assert queued.status_code == 303
        assert queued.headers["location"].startswith("/admin/jobs/")

        with client.app.state.SessionLocal() as session:
            job = session.scalars(select(BackgroundJob)).one()
            assert job.job_type == "app_feed_export"
            assert job.status == "pending"


def test_admin_photo_rescue_background_actions_require_csrf_and_enqueue(
    tmp_path,
) -> None:
    with make_client(tmp_path) as client:
        event_id = create_preview_event(
            client,
            title="Admin Background Rescue Event",
            venue_key="admin-background-rescue-venue",
        )
        candidate_id = create_image_candidate_for_test(
            client,
            event_id=event_id,
            image_url="https://images.example/admin-background-artist.jpg",
            image_role="artist_press",
            rescue_source="provider_artist_image",
        )
        with client.app.state.SessionLocal() as session:
            run = ApiFeedRun(
                provider_key="jambase",
                provider_type="licensed_vendor",
                run_mode="manual_json",
                status="success",
            )
            session.add(run)
            session.commit()
            run_id = run.id

        login_admin(client)
        missing_csrf = client.post(
            f"/admin/events/{event_id}/photo-rescue/background",
            follow_redirects=False,
        )
        assert missing_csrf.status_code == 403

        event_job_response = admin_post(
            client,
            f"/admin/events/{event_id}/photo-rescue/background",
            follow_redirects=False,
        )
        candidate_job_response = admin_post(
            client,
            f"/admin/image-candidates/{candidate_id}/photo-rescue/background",
            follow_redirects=False,
        )
        run_job_response = admin_post(
            client,
            f"/admin/api-feed-runs/{run_id}/photo-rescue/background",
            follow_redirects=False,
        )
        recent_job_response = admin_post(
            client,
            "/admin/image-candidates/photo-rescue/recent-approved/background",
            follow_redirects=False,
        )
        with client.app.state.SessionLocal() as session:
            job_types = [
                job.job_type
                for job in session.scalars(
                    select(BackgroundJob).order_by(BackgroundJob.id.asc())
                ).all()
            ]

    assert event_job_response.status_code == 303
    assert candidate_job_response.status_code == 303
    assert run_job_response.status_code == 303
    assert recent_job_response.status_code == 303
    assert job_types == [
        "event_photo_rescue",
        "event_photo_rescue",
        "api_feed_run_photo_rescue",
        "recent_events_photo_rescue",
    ]


def test_admin_job_detail_shows_redacted_payload(tmp_path) -> None:
    with make_client(tmp_path) as client:
        with client.app.state.SessionLocal() as session:
            job = enqueue_job(
                session,
                "provider_sandbox_cityspark",
                {
                    "url": "https://vendor.test/search?X-API-Key=SECRET_TOKEN",
                    "headers": {"X-API-Key": "SECRET_TOKEN"},
                },
            )

        response = admin_get(client, f"/admin/jobs/{job.id}")
        assert response.status_code == 200
        assert "SECRET_TOKEN" not in response.text
        assert "[REDACTED]" in response.text
