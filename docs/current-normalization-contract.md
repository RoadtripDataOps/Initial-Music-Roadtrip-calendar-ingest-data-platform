# Current Normalization Contract

This contract describes how the current Music Roadtrip Mapotic export is used as
the baseline normalization and dedupe seed for this local ingestion POC.

## Event vs POI Split

- `Category = Concert` means the row is a Concert event.
- Concert records are events and must never be treated as POIs.
- `Category != Concert` means the row is a POI/place already represented on the
  Music Roadtrip map.
- Existing non-Concert Mapotic export rows are treated as the current source of
  truth for existing POIs.

## Category And Subcategory Logic

The `Category` column stores the main category. POI subcategories are stored in
the category-specific column named for that category:

| Category | Subcategory column |
| --- | --- |
| Music Site | `Music Site` |
| Cultural | `Cultural` |
| Food & Bev | `Food & Bev` |
| Shopping | `Shopping` |
| Visitor & Travel | `Visitor & Travel` |
| Lodging | `Lodging` |
| Bars & Lounges | none yet |

Concert rows are excluded from `current_poi_registry.jsonl` and
`poi_locations`.

## Core POI Fields

The POI registry preserves:

- Mapotic provenance: `MapoticID`, `Import ID`, `PlacesID`, raw row hash, and
  raw row JSON.
- Display identity: name, normalized name, category, subcategory, city, state,
  country, zip code, address, latitude, longitude.
- Contact and links: website, phone, email, Instagram, Facebook, X, TikTok,
  Spotify, and video/YouTube.
- Media: main image URL and additional image URLs.
- QA fields: certified, carousel selection, business status, quality control,
  last verified timestamp, venue match confidence, photo quality score, Google
  review count, Yelp review count, and rating.

Zip code is stored as text. Latitude and longitude come from their explicit
Mapotic columns and must not be swapped.

## Core Event Fields

Concert rows remain in the event pipeline. The current export exposes event-like
fields such as:

- `Name (en)` for event title.
- `Date` for event timing.
- `Tickets link (en)` / `Tickets link (es)` for ticket URLs.
- `Performers (en)` / `Performers (es)` for artist text.
- `Location (en)` / `Location (es)` and venue/source IDs for venue matching.
- `Data_source [developers]`, `event_id (Jambase)`, and `venue_id (Jambase)`
  for provider provenance.

CitySpark and JamBase rows are handled as licensed/vendor API records in the API
Feed Review Workbench, not as first-party POIs.

## IDs And Provenance

POI registry records use these identifiers:

- `canonical_poi_id`: deterministic internal ID derived from the POI dedupe key.
- `poi_dedupe_key`: normalized name plus rounded coordinates when available.
- `mapotic_id`: source Mapotic record ID.
- `places_id`: stable Mapotic custom PlacesID value when present.
- `canonical_venue_id`: venue matching identifier from the current export.
- `source_type`: `mapotic_export` for the current seed.
- `source_record_id`: source Mapotic ID.

All records preserve raw source JSON for auditability.

## Dedupe Rules

Strong POI duplicate signal:

- Same normalized name and latitude/longitude rounded to five decimal places.
- Or same stable PlacesID, MapoticID, or canonical venue ID.

Medium duplicate signal:

- Same normalized name.
- Coordinates within approximately 50 meters.
- Same city/state.

Weak duplicate signal:

- Same normalized name.
- Coordinates within approximately 100 meters.
- Matching website, phone, or address fragment.

Weak candidates must not be auto-merged. They belong in duplicate review.

## Image And Ticket Rules

- POI image fields must be direct public image asset URLs.
- Social-media pages, posts, videos, profiles, and Music Roadtrip logo UI assets
  must not be stored as POI/event/venue/fallback images.
- Concert ticket URLs remain event fields and are not used for POI identity.
- Ticket links should prefer event-specific links over generic platform links.

## Future Source Candidate Types

Future extraction work may produce:

- `event_candidate`
- `poi_candidate`
- `mixed_source_candidate`

Rules:

- Concert/event candidates go to the event pipeline.
- Non-Concert/place candidates go to the POI Master Registry.
- A submitted source can produce both event and POI candidates.
- All POI candidates dedupe against `current_poi_registry.jsonl` and
  `poi_locations` before any new place record is created.

This milestone does not add scraping, scheduled crawling, or live API calls.
