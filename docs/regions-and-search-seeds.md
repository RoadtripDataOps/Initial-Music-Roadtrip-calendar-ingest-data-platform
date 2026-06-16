# Regions And Search Seeds

Milestone 5.0 adds a destination/region layer for Music Roadtrip's internal
ingestion system. Regions make it possible to group events, POIs, venue-style
places, calendar sources, crawl coverage, quality issues, and private app-feed
exports by city, metro, tourism board, partner market, or Certified Music
Region.

This layer is internal by default. It does not publish records, call external
geocoding services, call provider APIs, scrape CitySpark, or weaken the
existing review gates.

## Region Model

`regions` stores the destination or market:

- `region_key`, `slug`, and `name` identify the region.
- `region_type` supports `city`, `metro`, `state`, `country`,
  `certified_music_region`, `tourism_board`, and `custom`.
- `city`, `state`, `country`, `latitude`, `longitude`, `radius_miles`,
  `bbox_json`, and `timezone` describe geography.
- `partner_status` tracks internal, prospect, active partner, certified, and
  inactive relationships.
- `certified` and `launch_status` support Certified Music Region planning.

Current POC associations use nullable `region_id` and `region_confidence`
fields on:

- `events`
- `poi_locations`
- `master_calendar_sources`

This keeps the milestone simple while still allowing future many-to-many
relationships when overlapping metros, states, routes, or tourism-board
markets need richer modeling.

## Destination Partners

`destination_partners` stores tourism boards, chambers, city partners, venue
groups, festivals, internal teams, and other destination organizations.

Fields include partner name, partner type, contact name, contact email, website,
optional linked region, notes, status, and timestamps.

Destination partners are not public users by default. Their submissions still
flow through the same validation, risk scoring, review, source approval, crawl,
dedupe, ticket QA, image QA, and app-feed readiness gates as other inbound
sources.

## Search Seed Registry

`search_seed_locations` stores internal search anchors that the app/search
layer can eventually check before calling paid external search or geocoding
services.

Supported seed types:

- city
- metro
- state
- country
- venue
- poi
- festival
- stadium
- airport
- landmark
- neighborhood
- tourism_board
- unknown

Supported source types:

- manual
- mapotic_export
- jambase_geography
- poi_registry
- region
- internal_research

Seeds can store name, normalized name, source record ID, linked region, linked
POI, latitude, longitude, city, state, country, timezone, priority, search
weight, popularity score, and booleans for internal search and app search.

The seed registry is a lookup aid only. It does not create events or POIs, and
it does not imply publication.

## Local Seed CLI

Seed from existing local POI and region data:

```bash
python -m app.tools.seed_search_locations
```

Optionally infer region assignments before seeding:

```bash
python -m app.tools.seed_search_locations --assign-regions
```

Useful flags:

- `--skip-pois` seeds regions only.
- `--skip-regions` seeds POIs only.
- `--assign-regions` runs conservative POI/event/source inference first.

The CLI is intentionally local and bounded. It does not call external APIs,
make live provider calls, scrape pages, create POIs, create events, or
auto-publish anything.

## Region Inference Rules

Inference is conservative and should leave records unassigned when confidence
is low.

POIs:

- Match by city, state, and country when available.
- Fall back to nearest region center only when POI coordinates are available
  and fall inside the region radius.
- Do not force an assignment when no clear match exists.

Events:

- Prefer the linked venue/POI region when available.
- Otherwise match by venue city, state, and country.
- Otherwise fall back to coordinates only when they match a region radius.
- Concert remains an event record, not a POI.

Master calendar sources:

- Match by submitted city, state, country, or region/market fields.
- Leave unassigned when the location is ambiguous.
- Assignment does not make a source crawlable. Crawl gates still require
  approval and review approval.

## Region Quality Snapshots

`region_quality_snapshots` stores a point-in-time quality summary for a region.

Tracked counts include:

- event count
- POI count
- master source count
- private app-feed event count
- private app-feed POI count
- missing image count
- pending image approval count
- bad ticket count
- duplicate event candidate count
- POI duplicate candidate count
- extraction failure count

Snapshots are generated from `/admin/regions/{id}/quality`. They help the team
see where a destination is ready, where source coverage is thin, where ticket
links need cleanup, and where image or duplicate review is blocking launch.

## Admin Routes

Region pages:

- `/admin/regions`
- `/admin/regions/{id}`
- `/admin/regions/{id}/events`
- `/admin/regions/{id}/pois`
- `/admin/regions/{id}/sources`
- `/admin/regions/{id}/quality`
- `/admin/regions/{id}/report`

Search seeds:

- `/admin/search-seeds`

Source trust and reports:

- `/admin/source-quality`
- `/admin/partner-reports`

All routes are admin-only. POST actions require CSRF protection.

## Regional App Feed Routes

Private admin feed routes:

- `/admin/app-feed/regions/{region_id}/events.json`
- `/admin/app-feed/regions/{region_id}/pois.json`
- `/admin/app-feed/regions/{region_id}/venues.json`

These routes reuse the app-feed service filters. They remain private admin
routes and do not change public app-feed behavior.

Regional POI feeds continue to exclude Concert records. Concert records remain
`category=Concert` and `record_type=event`.

## Certified Music Region Planning

Regions support the future Certified Music Region workflow by combining:

- direct/owned calendar source coverage
- licensed vendor/API review coverage
- tourism board and destination partner relationships
- POI and venue inventory
- source coverage by crawl status
- quality snapshots
- private regional app-feed previews

The long-term strategy is to reduce dependency on any single paid provider by
building an owned, reviewed, region-aware source network while continuing to
review licensed vendor feeds through the private API Feed Review Workbench.

## Safety Notes

- No external geocoding calls are made.
- No live provider API calls are made by the region/search seed layer.
- No API keys are stored or required.
- CitySpark remains a licensed vendor/API feed behind provider-specific
  configuration and review controls; this layer does not scrape CitySpark.
- Public submissions still require validation, risk scoring, and admin review.
- App-feed JSON remains private unless app-feed public settings are explicitly
  changed elsewhere.

Source trust scoring and partner/destination reporting are documented in
`docs/source-trust-and-partner-reporting.md`.
