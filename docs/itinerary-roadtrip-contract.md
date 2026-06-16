# Deferred Itinerary Road Trip Contract

This contract is deferred and app-team-owned. It remains documented so existing
compatibility routes and tests stay understandable, but Scott's active scope is
calendar ingest, source scraping, API sandbox review, normalized event quality,
event photos, ticket-link QA, and POI audit.

Do not expand Road Trip, Tour, Setlist, Route, route-builder, saved-trip,
consumer navigation, social, ad/discovery monetization, or mobile-app UI
functionality in this repository unless the user explicitly asks for it.

The existing compatibility layer does not build a mobile app, turn-by-turn
navigation, routing engine, ad system, external geocoding/search calls, live
provider calls, or auto-publishing.

## Terminology

Backend terminology:

- `itinerary`
- `itinerary_stop`
- `itinerary_segment`

App-facing labels:

- Road Trip
- Tour
- Setlist
- Route

Concert records remain `category=Concert` and `record_type=event`. Concert
events can be itinerary stops, but they are never treated as POIs. Category
values other than Concert remain POI/place-style records.

## Tables

`itineraries` stores the editorial container:

- identity: `itinerary_key`, `slug`, `title`, `subtitle`, `description`
- type: `itinerary_type`, `display_label`, `status`
- context: `region_id`, `destination_partner_id`, `artist_id`
- route copy: start/end city, state, country, duration, distance
- display: hero image, image status, music theme, genres, tags
- QA/app state: `featured`, `app_feed_ready`, `quality_score`,
  `quality_flags_json`, timestamps, `published_at`

`itinerary_stops` stores app-safe stop snapshots:

- references: event, POI, venue, region, artist
- display: title, subtitle, description, image URL/status
- location: address, city, state, country, latitude, longitude
- timing: start/end datetime and duration text
- links: ticket, website, app URL

`itinerary_segments` stores manual route metadata between adjacent stops:

- from/to stop IDs
- distance miles, drive/walk estimates
- external navigation URL
- route provider: `none`, `google_maps_external`, `apple_maps_external`, or
  `manual`

Segments are derived from stored stop addresses/coordinates. They do not call
routing APIs.

## Admin Routes

- `/admin/itineraries`
- `/admin/itineraries/new`
- `/admin/itineraries/{id}`
- `/admin/itineraries/{id}/stops`
- `/admin/itineraries/{id}/preview`
- `/admin/itineraries/{id}/app-feed.json`

Mutating actions require admin authentication and CSRF. Admins can create a
draft, add referenced stops, reorder stops, remove stops, refresh quality, and
preview app-feed JSON.

Draft suggestion actions:

- `POST /admin/itineraries/actions/build-region`
- `POST /admin/itineraries/actions/build-artist`

These create draft-only suggestions. They do not publish.

## Preview Routes

- `/preview/itineraries`
- `/preview/itineraries/{id}`

The preview sandbox shows app-like itinerary cards, stop lists, segment
metadata, external navigation links, quality badges, and the app-feed JSON link.

## App Feed Routes

Admin/private:

- `/admin/app-feed/itineraries.json`
- `/admin/app-feed/itineraries/{id}.json`
- `/admin/app-feed/regions/{region_id}/itineraries.json`
- `/admin/app-feed/artists/{artist_id}/itineraries.json`

Optional app routes are private by default and respect `APP_FEED_PUBLIC`:

- `/api/app/itineraries`
- `/api/app/itineraries/{id}`
- `/api/app/regions/{region_id}/itineraries`
- `/api/app/artists/{artist_id}/itineraries`

Only approved/published, app-feed-ready itinerary records appear in list feeds.
The admin detail JSON can preview a single itinerary contract during review.

## App JSON Shape

The app-safe payload includes:

```json
{
  "itinerary_id": "itinerary-123",
  "type": "road_trip",
  "display_label": "Road Trip",
  "title": "Memphis Music Road Trip",
  "subtitle": "Two days of music landmarks",
  "description": "",
  "region": {},
  "artist": {},
  "hero_image": {
    "url": "",
    "status": "missing"
  },
  "tags": [],
  "genres": [],
  "estimates": {
    "duration_text": "",
    "distance_text": "",
    "start": {},
    "end": {}
  },
  "featured": false,
  "stops": [],
  "segments": [],
  "quality": {
    "score": 0,
    "flags": [],
    "app_feed_ready": false
  },
  "updated_at": ""
}
```

The payload does not include raw provider payloads, source-claim JSON, admin
notes, credentials, API keys, or private review blobs.

## Search, Discovery, And Filters

Approved/published itineraries index into `app_search_index` as
`entity_type=itinerary`. They are not POIs.

Discovery slots can retain `itinerary_carousel` for deferred app-team Road
Trip/Tour placeholders.

Compatibility filter options include:

- itinerary types
- itinerary regions

Event filters and POI category filters remain separate. `Concert` does not
appear as a POI filter category.

## Quality Rules

Quality scoring checks:

- title exists
- at least two stops
- stops have coordinates or address/city-state-country
- stop images are app-safe and are not Music Roadtrip logo assets
- status is approved or published for feed readiness
- event stops are not rejected, archived, stale, merged, or duplicate
  candidates
- duplicate POI stops are flagged
- regional itinerary types have a region
- artist tours have an artist
- hero image exists and is not a logo asset

Quality flags are review signals. They do not auto-publish or auto-reject.

## Navigation Links

Navigation URLs are external handoff links:

- Google Maps search/directions URLs
- Apple Maps search/directions URLs
- manual URL placeholders

The service builds these from stored coordinates or addresses only. It does not
make external routing, geocoding, search, ticketing, provider, CitySpark, or
social platform calls. It does not add or require API keys.

## Background Jobs

Job types:

- `itinerary_quality_rollup`
- `itinerary_app_feed_export`
- `build_artist_tour_itinerary`
- `build_region_itinerary_suggestions`

Suggestion jobs produce draft records only. They do not make external calls and
do not publish. Do not add new itinerary job behavior unless itinerary work is
explicitly reopened.
