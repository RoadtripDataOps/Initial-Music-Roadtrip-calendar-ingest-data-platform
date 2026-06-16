import csv
import gzip
import json
import re
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import DEV_ADMIN_PASSWORD_HASH, Settings
from app.db.models import (
    BackgroundJob,
    PoiInventoryExport,
    PoiLocation,
    ScheduledTask,
    utc_now,
)
from app.main import create_app
from app.services.background_job_service import (
    enqueue_due_scheduled_tasks,
    enqueue_job,
    process_next_job,
)
from app.services.poi_candidate_matching_service import (
    PoiCandidateInput,
    match_poi_candidate,
)
from app.services.poi_inventory_export_service import (
    build_poi_dedupe_index,
    export_current_poi_dedupe_index,
    export_current_poi_inventory,
    export_poi_inventory_manifest,
    poi_dedupe_index_keys_for_location,
)
from app.services.poi_registry_service import (
    analyze_mapotic_export,
    duplicate_candidates_for_pois,
    import_poi_registry_jsonl,
    minimal_poi_from_record,
    normalize_poi_name,
    parse_mapotic_category,
    poi_dedupe_key_for_values,
    poi_registry_record_from_row,
)

HEADERS = [
    "MapoticID",
    "Longitude",
    "Latitude",
    "Name (en)",
    "Category",
    "Music Site",
    "Cultural",
    "Food & Bev",
    "Shopping",
    "Visitor & Travel",
    "Lodging",
    "Import ID",
    "PlacesID (en)",
    "Canonical Venue ID (en)",
    "Address (en)",
    "City (en)",
    "State (en)",
    "Zip Code (en)",
    "Country (en)",
    "Website (en)",
    "Phone",
    "E-mail",
    "Instagram (en)",
    "Facebook (en)",
    "X (en)",
    "TikTok (en)",
    "Video Tour",
    "Spotify URL (en)",
    "Main image URL",
    "Image URL",
    "Description (en)",
    "Hours of operation (en)",
    "Rating",
    "Review Count (Google) (en)",
    "Review Count (Yelp) (en)",
    "Certified",
    "Carousel selection",
    "Business Status",
    "Last Veriified At",
    "Venue Match Confidence",
    "Photo Quality Score",
    "Quality Control",
    "Date",
    "Tickets link (en)",
    "Data_source [developers]",
    "Source Record ID",
]


def mapotic_row(**overrides: str) -> dict[str, str]:
    row = {header: "" for header in HEADERS}
    row.update(
        {
            "MapoticID": "1001",
            "Longitude": "-90.04900",
            "Latitude": "35.14950",
            "Name (en)": "River Music Hall LLC",
            "Category": "Music Site",
            "Music Site": "Venues",
            "Import ID": "mapotic:1001",
            "PlacesID (en)": "place-1001",
            "Address (en)": "1 Music Way",
            "City (en)": "Memphis",
            "State (en)": "TN",
            "Zip Code (en)": "03810",
            "Country (en)": "US",
            "Website (en)": "https://venue.example",
            "Phone": "+1 901 555 0101",
            "Main image URL": "https://images.example/venue.jpg",
            "Image URL": "https://images.example/venue-2.jpg",
        }
    )
    row.update(overrides)
    return row


def write_mapotic_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADERS, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def make_client(tmp_path: Path) -> TestClient:
    app = create_app(
        Settings(
            database_url=f"sqlite:///{tmp_path / 'test.db'}",
            admin_password_hash=DEV_ADMIN_PASSWORD_HASH,
            session_secret_key="test-session-secret",
        )
    )
    return TestClient(app)


def login_admin(client: TestClient) -> None:
    response = client.post(
        "/admin/login",
        data={"username": "admin", "password": "admin"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def csrf_token(client: TestClient) -> str:
    response = client.get("/admin/poi-inventory")
    assert response.status_code == 200
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
    assert match is not None
    return match.group(1)


def poi_location(
    *,
    canonical_poi_id: str = "poi-river-music-hall",
    poi_dedupe_key: str = "poi:river-music-hall",
    display_name: str = "River Music Hall",
    normalized_name: str = "river music hall",
    category: str = "Music Site",
    subcategory: str | None = "Venues",
    latitude: float | None = 35.1495,
    longitude: float | None = -90.049,
    city: str | None = "Memphis",
    state: str | None = "TN",
    places_id: str | None = "place-river",
    mapotic_id: str | None = "mapotic-river",
    website: str | None = "https://venue.example/events",
    phone: str | None = "+1 901 555 0101",
    main_image_url: str | None = "https://images.example/venue.jpg",
) -> PoiLocation:
    return PoiLocation(
        canonical_poi_id=canonical_poi_id,
        poi_dedupe_key=poi_dedupe_key,
        source_type="mapotic_export",
        source_record_id=mapotic_id,
        mapotic_id=mapotic_id,
        places_id=places_id,
        display_name=display_name,
        normalized_name=normalized_name,
        category=category,
        subcategory=subcategory,
        latitude=latitude,
        longitude=longitude,
        address="1 Music Way",
        city=city,
        state=state,
        zip_code="03810",
        country="US",
        website=website,
        phone=phone,
        email="info@venue.example",
        main_image_url=main_image_url,
        description="A music place used in POI inventory tests.",
        certified=True,
        carousel_selection="regional",
        business_status="open",
        rating=4.7,
        review_count_google=12,
        review_count_yelp=3,
        photo_quality_score=88.0,
        quality_control="ready",
        publish_status="approved",
        publish_ready_score=91.0,
        raw_source_json=json.dumps({"raw_row_hash": f"hash-{canonical_poi_id}"}),
    )


@pytest.mark.parametrize(
    ("category", "subcategory_column", "subcategory", "kind"),
    [
        ("Concert", "", None, "event"),
        ("Music Site", "Music Site", "Venues", "poi"),
        ("Cultural", "Cultural", "Museums", "poi"),
        ("Food & Bev", "Food & Bev", "Restaurants", "poi"),
        ("Shopping", "Shopping", "Record Stores", "poi"),
        ("Visitor & Travel", "Visitor & Travel", "Travel & Tourism", "poi"),
        ("Lodging", "Lodging", "Music Hotels", "poi"),
        ("Bars & Lounges", "", None, "poi"),
    ],
)
def test_mapotic_category_and_subcategory_parsing(
    category: str,
    subcategory_column: str,
    subcategory: str | None,
    kind: str,
) -> None:
    row = mapotic_row(Category=category)
    if subcategory_column and subcategory:
        row[subcategory_column] = subcategory

    parsed = parse_mapotic_category(row)

    assert parsed.kind == kind
    assert parsed.category == category
    assert parsed.subcategory == subcategory


def test_poi_dedupe_key_uses_normalized_name_and_rounded_coordinates() -> None:
    key, confidence = poi_dedupe_key_for_values(
        normalize_poi_name("The Fillmore LLC"),
        37.784004,
        -122.433106,
    )

    assert confidence == "strong"
    assert key == "name_geo:the fillmore|lat:37.78400|lng:-122.43311"


def test_same_poi_name_and_same_rounded_coordinates_dedupes() -> None:
    first = poi_registry_record_from_row(
        mapotic_row(**{"Latitude": "35.149501", "Longitude": "-90.049001"})
    )
    second = poi_registry_record_from_row(
        mapotic_row(
            **{
                "MapoticID": "1002",
                "PlacesID (en)": "place-1002",
                "Latitude": "35.149504",
                "Longitude": "-90.049004",
            }
        )
    )

    assert first is not None
    assert second is not None
    assert first["poi_dedupe_key"] == second["poi_dedupe_key"]


def test_same_poi_name_nearby_coordinates_becomes_duplicate_candidate() -> None:
    first = poi_registry_record_from_row(mapotic_row())
    second = poi_registry_record_from_row(
        mapotic_row(
            **{
                "MapoticID": "1002",
                "PlacesID (en)": "place-1002",
                "Latitude": "35.14960",
                "Longitude": "-90.04910",
            }
        )
    )
    assert first is not None
    assert second is not None

    candidates = duplicate_candidates_for_pois(
        [minimal_poi_from_record(first), minimal_poi_from_record(second)]
    )

    assert candidates
    assert candidates[0]["confidence"] == "medium"


def test_analyze_mapotic_export_writes_poi_registry_without_concert_rows(
    tmp_path: Path,
) -> None:
    export_path = tmp_path / "mapotic.csv"
    write_mapotic_csv(
        export_path,
        [
            mapotic_row(),
            mapotic_row(
                **{
                    "MapoticID": "2001",
                    "Category": "Concert",
                    "Date": "2026-08-01",
                    "Tickets link (en)": "https://tickets.example/show",
                }
            ),
        ],
    )

    outputs = analyze_mapotic_export(
        export_path,
        docs_dir=tmp_path / "docs",
        generated_dir=tmp_path / "generated",
    )
    registry_lines = outputs["registry"].read_text(encoding="utf-8").splitlines()
    profile = json.loads(outputs["profile"].read_text(encoding="utf-8"))

    assert len(registry_lines) == 1
    assert json.loads(registry_lines[0])["category"] != "Concert"
    assert profile["event_count"] == 1
    assert profile["poi_count"] == 1
    assert outputs["duplicates"].exists()
    assert outputs["event_profile"].exists()


def test_poi_registry_record_preserves_zip_and_coordinate_order() -> None:
    record = poi_registry_record_from_row(
        mapotic_row(
            **{
                "Latitude": "35.14950",
                "Longitude": "-90.04900",
                "Zip Code (en)": "03810",
            }
        )
    )

    assert record is not None
    assert record["zip_code"] == "03810"
    assert record["latitude"] == 35.1495
    assert record["longitude"] == -90.049


def test_social_and_logo_urls_are_not_stored_as_poi_images() -> None:
    record = poi_registry_record_from_row(
        mapotic_row(
            **{
                "Main image URL": "/static/images/music-roadtrip-logo-square.png",
                "Image URL": (
                    "https://instagram.com/p/not-image$"
                    "https://images.example/usable.jpg"
                ),
            }
        )
    )

    assert record is not None
    assert record["main_image_url"] is None
    assert record["additional_image_urls"] == "https://images.example/usable.jpg"


def test_poi_import_command_logic_creates_and_dedupes_locations(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "registry.jsonl"
    record = poi_registry_record_from_row(mapotic_row())
    assert record is not None
    registry_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    with make_client(tmp_path) as client:
        with client.app.state.SessionLocal() as session:
            first_summary = import_poi_registry_jsonl(session, registry_path)
            second_summary = import_poi_registry_jsonl(session, registry_path)
            locations = list(session.scalars(select(PoiLocation)).all())

    assert first_summary.created == 1
    assert second_summary.created == 0
    assert second_summary.updated == 1
    assert len(locations) == 1
    assert locations[0].category == "Music Site"
    assert locations[0].zip_code == "03810"


def test_poi_import_counts_duplicate_keys_within_same_jsonl(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.jsonl"
    first = poi_registry_record_from_row(mapotic_row())
    second = poi_registry_record_from_row(
        mapotic_row(**{"MapoticID": "1002", "PlacesID (en)": "place-1002"})
    )
    assert first is not None
    assert second is not None
    assert first["poi_dedupe_key"] == second["poi_dedupe_key"]
    registry_path.write_text(
        json.dumps(first) + "\n" + json.dumps(second) + "\n",
        encoding="utf-8",
    )

    with make_client(tmp_path) as client:
        with client.app.state.SessionLocal() as session:
            summary = import_poi_registry_jsonl(session, registry_path)
            locations = list(session.scalars(select(PoiLocation)).all())

    assert summary.created == 1
    assert summary.duplicate == 1
    assert len(locations) == 1


def test_poi_admin_pages_load_after_import(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry.jsonl"
    record = poi_registry_record_from_row(mapotic_row())
    assert record is not None
    registry_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    with make_client(tmp_path) as client:
        with client.app.state.SessionLocal() as session:
            import_poi_registry_jsonl(session, registry_path)
        login_admin(client)
        list_response = client.get("/admin/poi-locations")
        detail_response = client.get("/admin/poi-locations/1")
        duplicates_response = client.get("/admin/poi-duplicates")

    assert list_response.status_code == 200
    assert "POI Master Registry" in list_response.text
    assert "River Music Hall" in list_response.text
    assert detail_response.status_code == 200
    assert "Raw Source JSON Preview" in detail_response.text
    assert duplicates_response.status_code == 200


def test_poi_inventory_export_writes_jsonl_manifest_and_sanitizes_records(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "poi_inventory"
    with make_client(tmp_path) as client:
        with client.app.state.SessionLocal() as session:
            session.add_all(
                [
                    poi_location(),
                    poi_location(
                        canonical_poi_id="poi-social-image",
                        poi_dedupe_key="poi:social-image",
                        display_name="Social Image Club",
                        normalized_name="social image club",
                        places_id="place-social",
                        mapotic_id="mapotic-social",
                        main_image_url="https://instagram.com/p/not-a-direct-image",
                    ),
                    poi_location(
                        canonical_poi_id="poi-logo-image",
                        poi_dedupe_key="poi:logo-image",
                        display_name="Logo Image Museum",
                        normalized_name="logo image museum",
                        places_id="place-logo",
                        mapotic_id="mapotic-logo",
                        main_image_url=(
                            "/static/images/music-roadtrip-logo-square.png"
                        ),
                    ),
                    poi_location(
                        canonical_poi_id="poi-concert-row",
                        poi_dedupe_key="poi:concert-row",
                        display_name="Concert Row",
                        normalized_name="concert row",
                        category="Concert",
                        subcategory=None,
                        places_id="place-concert",
                        mapotic_id="mapotic-concert",
                    ),
                ]
            )
            session.commit()

            inventory_export = export_current_poi_inventory(
                session,
                output_dir,
                archive=False,
                generated_by="pytest",
            )
            dedupe_export = export_current_poi_dedupe_index(
                session,
                output_dir,
                archive=False,
                generated_by="pytest",
            )
            manifest_export = export_poi_inventory_manifest(
                session,
                output_dir,
                archive=False,
                generated_by="pytest",
            )

            export_rows = list(session.scalars(select(PoiInventoryExport)).all())

    inventory_path = output_dir / "current_poi_inventory.jsonl.gz"
    dedupe_path = output_dir / "current_poi_dedupe_index.json"
    manifest_path = output_dir / "current_poi_inventory_manifest.json"
    assert inventory_export.status == "success"
    assert inventory_export.record_count == 3
    assert inventory_export.output_size_bytes is not None
    assert inventory_export.sha256_hash
    assert dedupe_export.status == "success"
    assert manifest_export.status == "success"
    assert len(export_rows) == 3
    assert inventory_path.exists()
    assert dedupe_path.exists()
    assert manifest_path.exists()

    with gzip.open(inventory_path, "rt", encoding="utf-8") as handle:
        records = [json.loads(line) for line in handle if line.strip()]
    names = {record["display_name"] for record in records}
    assert names == {"River Music Hall", "Social Image Club", "Logo Image Museum"}
    river = next(
        record for record in records if record["display_name"] == "River Music Hall"
    )
    assert river["zip_code"] == "03810"
    assert river["latitude"] == 35.1495
    assert river["longitude"] == -90.049
    assert river["website_domain"] == "venue.example"
    assert river["raw_row_hash"] == "hash-poi-river-music-hall"

    social = next(
        record for record in records if record["display_name"] == "Social Image Club"
    )
    logo = next(
        record for record in records if record["display_name"] == "Logo Image Museum"
    )
    assert social["main_image_url"] is None
    assert "main_image_url_social_or_video_suppressed" in social["image_warnings"]
    assert logo["main_image_url"] is None
    assert "main_image_url_logo_asset_suppressed" in logo["image_warnings"]
    serialized_records = json.dumps(records)
    assert "instagram.com/p/not-a-direct-image" not in serialized_records
    assert "music-roadtrip-logo-square.png" not in serialized_records

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["database_is_source_of_truth"] is True
    assert manifest["concert_rows_excluded"] is True
    assert manifest["inventory_export"]["record_count"] == 3
    assert manifest["inventory_export"]["sha256_hash"] == inventory_export.sha256_hash
    assert manifest["generated_at"]


def test_poi_dedupe_index_records_duplicate_key_collisions() -> None:
    first = poi_location(
        canonical_poi_id="poi-collision-one",
        poi_dedupe_key="poi:collision-one",
        places_id="place-collision-one",
        mapotic_id="mapotic-collision-one",
    )
    first.id = 1
    second = poi_location(
        canonical_poi_id="poi-collision-two",
        poi_dedupe_key="poi:collision-two",
        places_id="place-collision-two",
        mapotic_id="mapotic-collision-two",
        website="https://venue.example/",
        phone="+1 (901) 555-0101",
    )
    second.id = 2

    first_keys = poi_dedupe_index_keys_for_location(first)
    index = build_poi_dedupe_index([first, second])

    assert first_keys["name_geo_5"] == "river music hall|lat:35.14950|lng:-90.04900"
    assert index["record_count"] == 2
    keys = index["keys"]
    assert keys["places_id"]["place-collision-one"][0]["poi_id"] == 1
    assert "venue.example|city:memphis|state:tn" in keys["website_city_state"]
    duplicate_strategies = {
        duplicate["strategy"] for duplicate in index["duplicates"]
    }
    assert "name_geo_5" in duplicate_strategies
    assert "website_city_state" in duplicate_strategies
    assert index["stats"]["duplicate_key_count"] >= 2


def test_poi_candidate_matching_prefers_database_then_latest_snapshot(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "poi_inventory"
    with make_client(tmp_path) as client:
        with client.app.state.SessionLocal() as session:
            poi = poi_location()
            session.add(poi)
            session.commit()

            candidate = PoiCandidateInput(
                display_name="River Music Hall",
                latitude=35.1495,
                longitude=-90.049,
                city="Memphis",
                state="TN",
            )
            db_match = match_poi_candidate(session, candidate)
            assert db_match.match_source == "database"
            assert db_match.match_strategy == "name_geo_5"
            assert db_match.poi_id == poi.id

            export_current_poi_dedupe_index(
                session,
                output_dir,
                archive=False,
                generated_by="pytest",
            )
            session.delete(poi)
            session.commit()

            snapshot_match = match_poi_candidate(session, candidate)

    assert snapshot_match.match_source == "dedupe_snapshot"
    assert snapshot_match.match_strategy == "name_geo_5"
    assert snapshot_match.snapshot_records


def test_poi_inventory_background_job_and_scheduler(tmp_path: Path) -> None:
    output_dir = tmp_path / "job-poi-inventory"
    with make_client(tmp_path) as client:
        with client.app.state.SessionLocal() as session:
            session.add(poi_location())
            session.commit()
            enqueue_job(
                session,
                "poi_inventory_snapshot_export",
                {
                    "output_dir": str(output_dir),
                    "archive": False,
                    "api_key": "SHOULD_NOT_LEAK",
                },
            )

            processed = process_next_job(
                session,
                client.app.state.settings,
                worker_id="poi-inventory-worker",
            )
            assert processed is not None
            assert processed.status == "success"
            assert "SHOULD_NOT_LEAK" not in processed.payload_json
            assert "SHOULD_NOT_LEAK" not in (processed.result_json or "")
            exports = list(session.scalars(select(PoiInventoryExport)).all())
            assert len(exports) == 3

            task = ScheduledTask(
                task_key="test_monthly_poi_inventory_snapshot",
                task_type="monthly_poi_inventory_snapshot",
                enabled=True,
                schedule_type="monthly",
                next_run_at=utc_now() - timedelta(days=1),
                payload_json=json.dumps(
                    {
                        "output_dir": str(output_dir),
                        "archive": False,
                    }
                ),
            )
            session.add(task)
            session.commit()

            result = enqueue_due_scheduled_tasks(session)
            job = session.get(BackgroundJob, result.enqueued_job_ids[0])

    assert result.due_task_count == 1
    assert job is not None
    assert job.job_type == "poi_inventory_snapshot_export"
    assert job.payload["scheduled_task_key"] == "test_monthly_poi_inventory_snapshot"


def test_poi_inventory_admin_pages_require_login_and_csrf(tmp_path: Path) -> None:
    with make_client(tmp_path) as client:
        client.app.state.poi_inventory_output_dir = tmp_path / "admin-poi-inventory"
        with client.app.state.SessionLocal() as session:
            session.add(poi_location())
            session.commit()

        unauthenticated = client.get("/admin/poi-inventory", follow_redirects=False)
        assert unauthenticated.status_code == 303
        assert unauthenticated.headers["location"].startswith("/admin/login")

        login_admin(client)
        overview = client.get("/admin/poi-inventory")
        assert overview.status_code == 200
        assert "POI Inventory Snapshots" in overview.text

        missing_csrf = client.post(
            "/admin/poi-inventory/generate-dedupe-index",
            follow_redirects=False,
        )
        assert missing_csrf.status_code == 403

        generated = client.post(
            "/admin/poi-inventory/generate-dedupe-index",
            data={"csrf_token": csrf_token(client)},
            follow_redirects=False,
        )
        assert generated.status_code == 303

        with client.app.state.SessionLocal() as session:
            export = session.scalars(
                select(PoiInventoryExport)
                .where(PoiInventoryExport.export_type == "dedupe_index_json")
                .order_by(PoiInventoryExport.id.asc())
            ).one()

        history = client.get("/admin/poi-inventory/exports")
        detail = client.get(f"/admin/poi-inventory/exports/{export.id}")
        download = client.get(f"/admin/poi-inventory/exports/{export.id}/download")
        assert history.status_code == 200
        assert detail.status_code == 200
        assert download.status_code == 200
        assert "current_poi_dedupe_index.json" in download.headers.get(
            "content-disposition",
            "",
        )
