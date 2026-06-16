# App Feed Contract

The app feed is the boundary between internal ingestion/review tables and the
Music Roadtrip app. Internal records may contain raw provider payloads,
source-claim details, duplicate candidates, image candidates, admin notes,
crawl logs, and import batches. The app feed exposes only sanitized,
publishable, app-ready records.

Feeds are private by default. Keep `APP_FEED_PUBLIC=false` unless the deployment
is intentionally exposing app JSON.

## Routes

- `GET /admin/app-feed` shows counts, export controls, and preview links.
- `GET /admin/app-feed/events.json` returns sanitized event JSON.
- `GET /admin/app-feed/pois.json` returns sanitized POI JSON.
- `GET /admin/app-feed/venues.json` returns sanitized venue JSON.
- `GET /admin/app-feed/regions/{region_id}/events.json` returns sanitized
  event JSON for one internal region.
- `GET /admin/app-feed/regions/{region_id}/pois.json` returns sanitized POI
  JSON for one internal region.
- `GET /admin/app-feed/regions/{region_id}/venues.json` returns sanitized
  venue JSON for one internal region.
- `POST /admin/app-feed/export` creates an `app_feed_exports` row and stores a
  local JSON snapshot.
- `GET /api/app/events`, `GET /api/app/pois`, and `GET /api/app/venues` are
  private unless `APP_FEED_PUBLIC=true`.

Admin routes require login. Export POSTs require CSRF.

## Event Contract

```json
{
  "event_id": "event-123",
  "record_type": "event",
  "category": "Concert",
  "title": "Example Show",
  "headliner": "Example Artist",
  "supporting_artists": [],
  "genre": "Americana",
  "provider_genre": "",
  "music_category": "",
  "start_datetime": "2026-08-01T20:00:00+00:00",
  "end_datetime": "",
  "timezone": "America/Chicago",
  "doors_time": "19:00",
  "lifecycle_status": "active",
  "venue": {
    "venue_id": "45",
    "poi_id": "venue-example",
    "name": "Example Venue",
    "address": "1 Music Way",
    "city": "Memphis",
    "state": "TN",
    "zip_code": "38103",
    "country": "US",
    "latitude": 35.14,
    "longitude": -90.05
  },
  "image": {
    "url": "https://example.com/show.jpg",
    "role": "event_provider",
    "status": "selected_pending_approval",
    "clearance_status": "needs_approval",
    "needs_approval": true,
    "quality_score": 82.0,
    "flags": ["image_needs_approval"]
  },
  "tickets": {
    "url": "https://tickets.example.com/show",
    "provider": "venue",
    "classification": "primary",
    "quality_flags": []
  },
  "links": {
    "event_url": "https://venue.example.com/show",
    "spotify_url": "",
    "website": "https://venue.example.com"
  },
  "source": {
    "primary_provider": "jambase",
    "ingestion_providers": ["jambase"],
    "source_claim_count": 1,
    "source_chain_summary": "JamBase"
  },
  "quality": {
    "publish_ready_score": 92,
    "dedupe_confidence": "strong",
    "venue_match_confidence": null,
    "flags": []
  },
  "updated_at": "2026-08-01T12:00:00+00:00"
}
```

Event filters: `date_from`, `date_to`, `city`, `state`, `country`, `genre`,
`venue_id`, `poi_id`, `region_id`, `include_cancelled`,
`include_needs_approval`, `limit`, and `offset`.

Default exclusions:

- events outside `approved` or `published` publish status
- rejected, merged, or duplicate-candidate events
- cancelled events unless `include_cancelled=true`
- raw provider JSON, admin notes, API keys, secrets, and compliance-only fields

Selected images pending approval may appear in the private app feed, but
`image.needs_approval` is set to `true`.

## POI Contract

```json
{
  "poi_id": "poi-example",
  "record_type": "poi",
  "name": "Example Record Shop",
  "category": "Shopping",
  "subcategory": "Record Stores",
  "description": "Independent record shop.",
  "address": "10 Vinyl Ave",
  "city": "Memphis",
  "state": "TN",
  "zip_code": "38103",
  "country": "US",
  "latitude": 35.14,
  "longitude": -90.05,
  "links": {
    "website": "https://records.example.com",
    "instagram": "",
    "facebook": "",
    "x": "",
    "tiktok": "",
    "youtube": "",
    "spotify": ""
  },
  "image": {
    "url": "https://records.example.com/photo.jpg",
    "status": "available",
    "clearance_status": "unknown",
    "needs_approval": false,
    "quality_score": 76.0,
    "flags": []
  },
  "place": {
    "certified": false,
    "carousel_selection": "",
    "business_status": "OPERATIONAL",
    "hours_of_operation": ""
  },
  "events": {
    "upcoming_event_count": 0,
    "next_event_datetime": ""
  },
  "quality": {
    "publish_ready_score": 88,
    "flags": []
  },
  "updated_at": "2026-08-01T12:00:00+00:00"
}
```

POI filters: `category`, `subcategory`, `city`, `state`, `country`,
`region_id`, `has_upcoming_events`, `limit`, and `offset`.

Rules:

- Concert rows are excluded from the POI feed.
- ZIP code is serialized as text.
- Latitude and longitude keep their source orientation.
- Music Roadtrip logo assets are never used as event, venue, POI, or fallback
  images.

Regional POI routes use the same exclusions and still omit Concert records.

## Venue Contract

Venues are derived from `EventVenue` records attached to publishable events and
include venue identity, address/coordinates, app-safe image metadata, and
upcoming event counts. They intentionally omit raw event source claims and
provider payloads.

## Readiness Scoring

Readiness is computed at feed time and returned in `quality.publish_ready_score`.
Blockers and flags are also stored in the publish-layer columns when future
approval workflows choose to persist them.

Event scoring considers event title, start time, venue identity and location,
ticket link, selected image, image hard blocks, duplicate status, lifecycle
status, source claims, and source trust signals.

POI scoring considers name, category, subcategory, address or coordinates,
website/source identifiers, image presence, duplicate signals, and stable IDs.

## Internal Fields Intentionally Omitted

The app feed never exposes:

- raw provider JSON
- raw source-claim payloads
- API keys, secrets, auth headers, or credential names with values
- admin review notes
- crawl logs
- import-batch row payloads
- compliance-only retention fields
- duplicate-candidate review internals
- image candidate raw review data beyond app-safe status/flags

## Versioning Strategy

The current POC contract is unversioned but should be treated as `v1`. Future
breaking changes should add `/api/app/v2/...` routes while keeping the current
shape available until the app developer migrates.
