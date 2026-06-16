# Current POI Inventory Snapshots

The current POI inventory snapshot system creates portable review artifacts from
the `poi_locations` table. It exists so incoming POI candidates can be checked
against Music Roadtrip's known place inventory before any new POI is created or
updated.

The database remains the source of truth. The JSON and JSONL files are monthly
or manual exports for dedupe, review, handoff, and audit.

## Generated Files

Current files are written under `data/generated/poi_inventory/`:

- `current_poi_inventory.jsonl.gz`
- `current_poi_dedupe_index.json`
- `current_poi_inventory_manifest.json`

Monthly archive copies are written under `data/generated/poi_inventory/archive/`:

- `poi_inventory_YYYY_MM.jsonl.gz`
- `poi_dedupe_index_YYYY_MM.json`
- `poi_inventory_manifest_YYYY_MM.json`

Generated files are ignored from git. Commit code, docs, and tests, not large
snapshot artifacts.

## Full Inventory JSONL

Each line in `current_poi_inventory.jsonl.gz` is one app-safe POI record. It
includes stable IDs, display names, category/subcategory, coordinates, address,
city/state/country, website domain, contact fields, quality fields, publication
status, and a raw row hash when available.

Concert rows are excluded. `Category = Concert` remains event data and must not
enter the POI inventory.

Music Roadtrip logo assets and social/video URLs are not exported as valid POI
image URLs. If such a value is present in the database image slot, the export
suppresses it and records an `image_warnings` flag.

## Dedupe Index

`current_poi_dedupe_index.json` is a lightweight matching index. It includes:

- `places_id`
- `mapotic_id`
- `canonical_poi_id`
- `name_geo_5`
- `name_geo_4`
- `website_city_state`
- `phone`
- `name_city_state`

Duplicate key collisions are written to the `duplicates` array. Collisions are
not silently overwritten.

## Candidate Matching Order

Incoming POI candidate audit should prefer:

1. Live database matching against `poi_locations`.
2. Latest dedupe index snapshot as a secondary reference.
3. Archived snapshots only for audit or debugging.

Normal candidate matching must still work if no JSON snapshot exists.

## Manual Export

Run:

```bash
python -m app.tools.export_poi_inventory
python -m app.tools.export_poi_inventory --dedupe-only
python -m app.tools.export_poi_inventory --output-dir data/generated/poi_inventory --no-archive
```

## Admin Workflow

Admin routes:

- `/admin/poi-inventory`
- `/admin/poi-inventory/exports`
- `/admin/poi-inventory/exports/{id}`

The overview page can generate a full snapshot or dedupe index only. Mutation
actions require CSRF and all pages are admin-only.

## Background Jobs

Background job type:

- `poi_inventory_snapshot_export`

Scheduled task type:

- `monthly_poi_inventory_snapshot`

The default scheduled task is disabled in local development. It uses a monthly
schedule type when enabled.

## Safety Rules

- Do not auto-create POIs from scraped sources.
- Do not expose full POI inventory snapshots publicly.
- Do not scrape CitySpark, ticket vendors, publishers, or social platforms.
- Do not make live provider calls or add API keys.
- Do not use Music Roadtrip logos as POI images.
- Concert records remain events, never POIs.
