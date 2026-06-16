# App Search And Map Contract

Milestone 5.2 adds a private backend contract for Music Roadtrip app search,
map markers, category filters, and lightweight discovery slots. It does not add
mobile app code, external search/geocoding calls, live provider calls, or
scraping.

## Why This Exists

The app should be able to search known Music Roadtrip data first before any
future paid search/geocoding fallback. Users may search for a city, region,
venue, POI, festival, landmark, or event. The internal app search layer indexes
approved normalized records and search seeds into a safe, app-shaped response
instead of exposing raw ingestion tables.

## Search Index

Table: `app_search_index`

Indexed entity types:

- `event`
- `itinerary`
- `poi`
- `venue`
- `region`
- `search_seed`
- `artist_future`
- `unknown`

The index stores display text, normalized search text, category/subcategory,
region and location metadata, priority/search weights, app-feed readiness,
certification flags, upcoming-event signals, and quality flags.

Rebuild locally:

```bash
python -m pytest tests/test_app.py -k app_search
```

Admin UI and JSON:

- `/admin/app-search`
- `/admin/app-search/results.json?q=memphis`
- `/admin/app-search/suggest.json?q=memphis`
- `POST /admin/app-search/rebuild-index`

Optional app routes are private by default and follow `APP_FEED_PUBLIC`:

- `/api/app/search`
- `/api/app/search/suggest`

## Ranking Rules

The service ranks actual text matches only. Boosts cannot make unrelated rows
match.

Order of matching:

- exact normalized name match
- prefix match
- contains match
- token/normalized fallback

Ranking boosts:

- app-feed-ready records
- certified POIs/regions
- upcoming events
- region/search-seed priority
- search seed priority/search weight/popularity score

Rejected, merged, stale, archived, unpublished, and duplicate-candidate events
are excluded by default. Concert records index as `entity_type=event`, not POI.
Approved/published Road Trip/Tour records can index as `entity_type=itinerary`
only for deferred app-team compatibility.

## Search Result Shape

Responses are app-safe and omit raw provider JSON, source-claim payloads, admin
notes, credentials, and internal review blobs.

Example:

```json
{
  "query": "memphis",
  "results": [
    {
      "entity_type": "region",
      "id": "region_1",
      "title": "Memphis Music Region",
      "subtitle": "certified_music_region - Memphis, TN, US",
      "category": "certified_music_region",
      "latitude": 35.1495,
      "longitude": -90.049,
      "score": 1195,
      "badges": ["Region", "certified_music_region", "Certified", "App Ready"],
      "app_url": "/regions/1"
    }
  ],
  "limit": 20,
  "offset": 0
}
```

## Map Marker Metadata

Service: `app/services/map_display_service.py`

Function: `build_map_marker(record)`

Marker payloads are metadata only. They do not use copyrighted app icons, paid
assets, or Music Roadtrip logo assets as marker images.

Shape:

```json
{
  "id": "event_123",
  "entity_type": "event",
  "title": "Example Concert",
  "category": "Concert",
  "subcategory": "Rock",
  "latitude": 35.14,
  "longitude": -90.05,
  "marker": {
    "icon_key": "event_ticket",
    "icon_label": "Event",
    "marker_color": "#ffc233",
    "marker_shape": "pin",
    "marker_size": "medium",
    "marker_weight": 78,
    "marker_opacity": 1.0,
    "glow": false,
    "certified": false,
    "cluster_priority": 86,
    "z_index": 260
  },
  "quality": {
    "score": 92,
    "flags": []
  }
}
```

## Marker Rules

Events:

- `icon_key=event_ticket`
- visible label is `Event`
- backend category remains `Concert`
- event markers never use a music-note default icon key
- upcoming/app-feed-ready events receive higher cluster priority

POIs:

- `Music Site / Venues` receive higher marker weight
- certified POIs set `glow=true`
- cultural, lodging, and generic place markers are lower weight unless
  certified
- `Concert` is never returned as a POI category

Regions:

- region markers are intended for overview/search views
- they are not mixed into dense event/POI marker feeds unless explicitly
  requested with `entity_type=region`

Quality flags can include missing image, missing ticket, or missing location.
Records are not hidden solely because an image is pending approval.

## Map Feed Routes

Admin/private:

- `/admin/app-feed/map-markers.json`
- `/admin/app-feed/regions/{region_id}/map-markers.json`

Optional app routes:

- `/api/app/map-markers`
- `/api/app/regions/{region_id}/map-markers`

Filters:

- `entity_type`
- `category`
- `subcategory`
- `region_id`
- `city`
- `state`
- `date_from`
- `date_to`
- `has_upcoming_events`
- `certified`
- `limit`
- `offset`

Mixed event and POI feeds are allowed, but each marker includes explicit
`entity_type`.

## Filter Contract

Admin/private:

- `/admin/app-feed/filter-options.json`
- `/admin/app-feed/regions/{region_id}/filter-options.json`

Optional app route:

- `/api/app/filter-options`

The filter output separates event filters from POI filters:

- event filters: date ranges, genres, cities, states, quality flags
- POI filters: categories, subcategories, certified counts
- deferred itinerary filters: itinerary types and region counts, retained only
  for compatibility with app-team-owned future work
- active display rules: badge/count/solid-button-or-dot guidance

`Concert` is intentionally absent from POI category filters because Concert is
an event category.

Discovery slots can include `itinerary_carousel` only as a deferred app-team
placeholder for Road Trip, Tour, Setlist, and Route cards. Scott's active scope
remains event/POI data quality, search seeds, map marker metadata, and app-feed
contracts. See `docs/itinerary-roadtrip-contract.md`.

## Discovery Slots

Table: `app_discovery_slots`

Slot types:

- `event_carousel`
- `poi_carousel`
- `region_carousel`
- `editorial`
- `sponsored_future`

Routes:

- `/admin/app-feed/discovery.json`
- `/admin/app-feed/regions/{region_id}/discovery.json`

This is a placeholder contract for future event/POI/region carousels and
editorial blocks. It is not an ad system and does not implement monetization.

## Jobs

Background job types:

- `rebuild_app_search_index`
- `app_map_feed_export`
- `app_filter_options_export`

Scheduled task type:

- `rebuild_app_search_index`

The jobs use local database records only.

## Safety Boundaries

- No external search/geocoding calls.
- No live provider calls.
- No API keys.
- No CitySpark scraping.
- App feed routes remain private unless `APP_FEED_PUBLIC=true`.
- Music Roadtrip logo assets are UI branding only and are not marker images.
- Concert records remain `category=Concert`, `record_type=event`, and
  `entity_type=event`.
