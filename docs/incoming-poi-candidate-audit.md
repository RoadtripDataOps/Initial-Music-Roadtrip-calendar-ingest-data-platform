# Incoming POI Candidate Audit Gate

Milestone 5.4B adds a gate between source discovery and the POI Master
Registry. Any venue, place, or location discovered during extraction or API Feed
Review is staged as a `poi_candidate` first. It is not written to
`poi_locations` until an admin approves that action.

## Purpose

The POI registry powers Music Roadtrip place/map data, so scraped or
provider-discovered place data must not enter it blindly. The candidate gate
lets Scott review venue quality, music relevance, images, duplicate risk, and
source provenance before creating or updating a POI.

## Event Venue vs POI

Not every event location is a Music Roadtrip POI.

- Concert records remain `category = Concert` and `record_type = event`.
- Concert records are events, never POIs.
- Event venue containers can support event display without becoming POIs.
- A `poi_candidate` can be marked `event_venue_only` when it is useful for an
  event but not ready or appropriate for the map/place registry.

## Candidate Sources

POI candidates can be created from:

- JSON-LD `Event.location` objects.
- Static HTML event cards that include a venue/place field.
- JamBase location objects reviewed through API Feed Review.
- CitySpark licensed vendor location objects reviewed through API Feed Review.
- Future safe extraction, file upload, manual admin, or Mapotic-import flows.

The system does not make live provider calls, scrape CitySpark pages, scrape
social platforms, or bypass source gates as part of candidate creation.

## Matching Strategy

Candidates match against:

1. The live `poi_locations` database.
2. The latest `current_poi_dedupe_index.json` snapshot.
3. Archived snapshots only for audit/debug when available.

Strong match signals include PlacesID, Mapotic ID, source IDs, normalized name
plus rounded coordinates, website plus city/state, and exact address. Medium and
weak signals stay review-only. Weak candidates are not auto-linked or merged.

## Category Suggestions

Suggestions follow `docs/category-system.md`.

- Event venue default: `Music Site / Venues`.
- Festival grounds/page: `Music Site / Festivals`.
- Record store: `Shopping / Record Stores`.
- Music store: `Shopping / Music Stores`.
- Museum: `Cultural / Museums`.
- Theatre: `Cultural / Theatres`.
- Performing arts center: `Cultural / Performing Arts Centers`.
- Music hotel: `Lodging / Music Hotels`.
- Chamber/tourism board: `Visitor & Travel / Chamber` or
  `Visitor & Travel / Travel & Tourism`.

Low-confidence suggestions stay in review or needs-research status.

## Quality And Image Rules

Candidate scoring checks for:

- name
- category/subcategory suggestion
- address or latitude/longitude
- valid latitude/longitude
- city/state
- website or source URL
- direct image asset URL
- non-social image URL
- Music Roadtrip logo asset misuse
- description when available
- music signal
- dedupe/match confidence

Image URLs are not fetched during page render. Social URLs, logo assets,
posters/flyers/admat hints, thumbnails, and non-direct image URLs are flagged
for review.

## Admin Decisions

Admins can:

- Approve and create new POI.
- Link to existing POI.
- Approve safe update to an existing POI.
- Mark event venue only.
- Mark needs research.
- Reject.
- Recompute match/quality.

All mutation actions require admin authentication and CSRF.

## Promotion Rules

Approve new POI creates a `poi_locations` row with source/candidate provenance.
Approve update existing only fills safe non-empty fields and never overwrites a
trusted non-empty field with blank data. Link existing does not create a
duplicate. Event venue only and reject never create POIs.

## App Feed Safety

`poi_candidates` are private review records. They are not exposed in app-feed
POIs. The POI app feed still reads only approved/published `poi_locations` and
still excludes `Category = Concert`.

## Operations

Admin pages:

- `/admin/poi-candidates`
- `/admin/poi-candidates/{id}`
- `/admin/poi-audit` redirects to `/admin/poi-candidates`

Background job types:

- `poi_candidate_match`
- `all_poi_candidate_match`
- `poi_candidate_quality_rollup`

These jobs recompute candidate match and quality metadata. They do not promote
candidates into POIs.
