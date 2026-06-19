# Music Roadtrip Calendar Ingest POC

Music Roadtrip Calendar Ingest is an internal proof of concept for building
Music Roadtrip's event and music-destination data pipeline. It supports both
direct/owned calendar-source submissions and licensed/vendor API feeds such as
CitySpark and JamBase. The goal is to normalize events, venues, ticket links,
images, source provenance, and QA signals into one clean event pipeline for
admin review and future app/map use.

This POC is not just a calendar scraper. It is a foundation for Music
Roadtrip's broader music tourism platform: concerts, festivals, venues, music
sites, record stores, museums, music hotels, bars/lounges, restaurants, music
history, music shopping, and app-ready event/place data.

## Scope

This repository is focused on Music Roadtrip's ingest, API sandbox, event
quality, and POI audit workflows. App-level itinerary, route-builder, saved
trip, consumer navigation, social, and mobile-app UI features are handled
separately by the app team.

Scott's lane in this repo is calendar ingest, calendar/source scraping, API
data sandbox review for CitySpark, JamBase, and other feeds, clean normalized
event listings, proper event photos, ticket-link QA, dedupe/source claims, and
POI auditing.

Existing itinerary/Road Trip routes are compatibility-only and are marked
`Deferred / App team feature`. Do not expand them unless itinerary work is
explicitly requested.

CitySpark is a paid licensed vendor API feed for Music Roadtrip. This POC keeps
CitySpark behind provider-specific configuration, credential, compliance, and
review controls. Live CitySpark calls are off unless explicitly configured, and
CitySpark-derived records should only be permanently approved according to Music
Roadtrip's vendor agreement. The owned-source submission system is being built
alongside, not necessarily instead of, CitySpark.

Strategic docs:

- `docs/music-roadtrip-product-thesis.md`
- `docs/musicroadtrip_site_corpus.md`
- `docs/provider-pipeline-handoff.md`
- `docs/regions-and-search-seeds.md`
- `docs/source-trust-and-partner-reporting.md`
- `docs/event-quality-workbench.md`
- `docs/ticket-page-image-fallback.md`
- `docs/security-hardening.md`
- `docs/current-poi-inventory-snapshots.md`
- `docs/app-search-and-map-contract.md`
- `docs/scott-data-pipeline-scope.md`
- `docs/itinerary-roadtrip-contract.md`

## Two-Track Ingestion Strategy

Music Roadtrip is building a stronger owned ingestion network while continuing
to review licensed vendor/API feeds during the transition.

Track A: Direct/owned source network

- Public calendar URL submissions.
- Event CSV/XLSX uploads.
- Calendar-source CSV/XLSX uploads.
- Approved partner feeds.
- Tourism board submissions.
- Chamber/partner submissions.
- Venue calendar submissions.
- Festival calendar submissions.
- Internal team source research.
- Approved master calendar source registry.
- Scheduled crawls of approved master calendar sources.

Track B: Licensed/vendor API feeds

- CitySpark.
- JamBase.
- Ticketmaster classification references.
- Future approved APIs.
- Manual provider JSON review.
- Provider-specific mappers.
- Source-chain provenance.
- Compliance controls.
- API Feed Review Workbench.
- Provider pipeline / developer handoff pages.

Both tracks normalize into `category=Concert`, `record_type=event`, the
normalized events table, venue profile linkage, ticket-link QA, image QA,
source provenance, dedupe/upsert, admin review, the preview sandbox, and the
future app/map feed.

## What Works

- FastAPI app with a homepage and `/health` check.
- `/submit-calendar` choice-first public calendar intake page with single
  calendar URL and calendar-source CSV/XLSX upload paths.
- `/submit-events` public event intake page for event CSV/XLSX uploads.
- SQLite storage for submitted calendar sources.
- Master calendar source registry with canonical URL dedupe and submitter
  claim tracking.
- `/admin/sources` list with `pending`, `approved`, and `paused` status updates.
- `/admin/master-calendar-sources` registry and source detail pages with
  summary cards, primary crawl/import actions, and collapsed filters.
- `/admin/crawl-queue` for approved master sources, due-source review, and
  selected-source crawl operations.
- DB-backed local background job queue with `/admin/jobs`, retry/cancel
  controls, redacted payload/result/error display, and manual worker CLI.
- Manual scheduler foundation with `/admin/scheduled-tasks` and a scheduler CLI
  that enqueues due task definitions without running an always-on daemon.
- Downloadable calendar-source and event CSV/XLSX templates.
- Import batch review pages for staged event rows and staged calendar-source
  rows.
- Manual “Run Crawl” action for approved sources only.
- Bulk crawl operations for selected master sources, all filtered master
  sources, due sources, and approved calendar sources from an import batch.
- Optional `Run in background` buttons for crawl queue work, provider sandbox
  runs, app feed exports, import-batch crawls, and image preflight actions.
- Crawl frequencies for master sources: `manual`, `daily`, `weekly`,
  `biweekly`, and `monthly`.
- Private `/admin/api-feeds` API feed review workbench with provider cards,
  demo imports, manual JSON uploads, raw-to-normalized review, QA flags,
  dedupe status, and approve/hold/reject/enrichment decisions.
- Professional image QA review board at `/admin/image-candidates` with scored
  event and venue image candidates, clearance workflow, filter chips, manual QA
  toggles, and explicit preflight metadata actions.
- Ticket-page image fallback that can safely extract `og:image`,
  `twitter:image`, and JSON-LD image candidates from event-specific ticket
  pages when an event is missing a good image or has a blocked/generic provider
  image.
- Destination/region layer with `/admin/regions`, region detail tabs, regional
  source coverage, region quality snapshots, and private regional app-feed JSON.
- Search seed registry at `/admin/search-seeds` for internal city, region,
  POI, venue, tourism-board, and landmark search seeds without calling external
  search or geocoding services.
- Source trust scoring at `/admin/source-quality` for master calendar sources,
  API providers, destination partners, and regions.
- Partner and destination reports at `/admin/partner-reports` and
  `/admin/regions/{id}/report`, with JSON/CSV exports for regional reporting.
- `crawl_runs` storage with source URL, HTTP status, content type, fetched
  timestamp, success/failure status, error message, and raw response body.
- `/admin/crawl-runs` history and crawl-run detail pages.
- ICS/iCalendar extraction into an `events` table.
- Safe source extraction beyond ICS for approved crawl results: JSON-LD Event,
  RSS/Atom, static HTML event cards, and generic event-link discovery.
- `/admin/extracted-events` staged candidate review before non-ICS extraction
  output can become normalized Concert events.
- `/admin/events` event list and `/admin/events/{id}` detail/provenance pages.
- `/admin/event-quality` Event Quality Workbench for reviewing normalized
  Concert listings before app-feed use: titles, date/time, venue linkage,
  tickets, photos, photo rescue, dedupe, source claims, music relevance, and
  app-feed readiness.
- `/admin/poi-inventory` current POI inventory snapshot controls for exporting
  app-safe JSONL and dedupe-index JSON artifacts from `poi_locations`.
- Private `/preview` visual sandbox with Music Events list, event profile,
  venue profile, nested venue events, quality dashboard, and reminder `.ics`
  previews.
- Deferred / App team itinerary compatibility routes remain stable, but are not
  part of Scott's active ingest/data-quality workflow.
- Development-only fixture routes for manual POC demos:
  `/dev/sample-calendar.ics`, `/dev/sample-jsonld-event.html`,
  `/dev/sample-events.rss`, and `/dev/sample-event-cards.html`.
- Public submission trust gate with risk scoring, quarantine/block states,
  suspicious-submissions admin review, blocklist, and trusted submitters.
- Optional Cloudflare Turnstile protection for public POST forms, disabled by
  default for local development.
- Public intake rate-limit scoring by IP, email, submitted domain, route,
  user-agent hash, and global hourly volume.
- CSV/XLSX upload hardening with size limits, row-count limits, extension
  checks, macro/legacy workbook rejection, and formula-injection neutralization
  for previews.
- Crawler URL safety checks that block non-http schemes, localhost/private
  networks in production, AWS metadata addresses, internal hostnames, unsafe
  redirects, excessive redirects, oversized responses, and unsupported content
  types.
- `/admin/security` dashboard for suspicious submissions, blocked attempts,
  failed logins, rate-limit hits, Turnstile failures, crawler safety blocks,
  provider live-call blocks, recent audit actions, and redaction status.
- `admin_audit_logs` table for login/logout, source review, crawl, event
  review, image review, POI candidate decisions, provider sandbox actions, and
  app-feed exports.
- Secrets redaction helpers for audit metadata, job payloads, previews, and
  error strings.
- Admin login, signed session cookie, admin-only route protection, and CSRF
  protection for admin POST forms.
- Pytest coverage for source admin, manual crawl, ICS extraction, public trust
  checks, master source dedupe, file uploads, staged-row validation, and
  approval workflows, bulk crawl gates, crawl queue behavior, and private
  preview filtering.

## Local Setup

```bash
make setup
```

This creates `.venv/` and installs the app plus development dependencies.

Optional local environment file:

```bash
cp .env.example .env
```

The default database is `sqlite:///./calendar_ingest.db`.

For production, set real admin credentials and a strong session secret:

```bash
APP_ENV=production
ADMIN_USERNAME=your-admin-user
ADMIN_PASSWORD_HASH=generated-password-hash
SESSION_SECRET_KEY=long-random-secret
```

Generate `ADMIN_PASSWORD_HASH` with:

```bash
python -m app.auth.create_password_hash "your-password-here"
```

Development mode has a local fallback admin login for convenience:

- Username: `admin`
- Password: `admin`

Do not use the development fallback in production.

## Run The App

```bash
make dev
```

Open:

- `http://127.0.0.1:8000/`
- `http://127.0.0.1:8000/submit-calendar`
- `http://127.0.0.1:8000/submit-calendar/url`
- `http://127.0.0.1:8000/submit-calendar/sources-file`
- `http://127.0.0.1:8000/submit-events`
- `http://127.0.0.1:8000/submit-events/file`
- `http://127.0.0.1:8000/admin/login`
- `http://127.0.0.1:8000/admin/dashboard`
- `http://127.0.0.1:8000/admin/sources`
- `http://127.0.0.1:8000/admin/master-calendar-sources`
- `http://127.0.0.1:8000/admin/crawl-queue`
- `http://127.0.0.1:8000/admin/jobs`
- `http://127.0.0.1:8000/admin/scheduled-tasks`
- `http://127.0.0.1:8000/admin/regions`
- `http://127.0.0.1:8000/admin/search-seeds`
- `http://127.0.0.1:8000/admin/api-feeds`
- `http://127.0.0.1:8000/admin/api-feed-runs`
- `http://127.0.0.1:8000/admin/image-candidates`
- `http://127.0.0.1:8000/admin/import-batches`
- `http://127.0.0.1:8000/admin/crawl-runs`
- `http://127.0.0.1:8000/admin/extracted-events`
- `http://127.0.0.1:8000/admin/events`
- `http://127.0.0.1:8000/admin/event-quality`
- `http://127.0.0.1:8000/admin/security`
- `http://127.0.0.1:8000/admin/suspicious-submissions`
- `http://127.0.0.1:8000/preview`
- `http://127.0.0.1:8000/preview/events`
- `http://127.0.0.1:8000/preview/venues`
- `http://127.0.0.1:8000/preview/quality`
- `http://127.0.0.1:8000/dev/sample-calendar.ics`
- `http://127.0.0.1:8000/dev/sample-jsonld-event.html`
- `http://127.0.0.1:8000/dev/sample-events.rss`
- `http://127.0.0.1:8000/dev/sample-event-cards.html`

Public routes:

- `/`
- `/health`
- `/submit-calendar`
- `/submit-calendar/url`
- `/submit-calendar/sources-file`
- `/submit-events`
- `/submit-events/file`
- `/templates/calendar-sources-template.csv`
- `/templates/calendar-sources-template.xlsx`
- `/templates/events-template.csv`
- `/templates/events-template.xlsx`
- `/templates/concert-events-template.csv`
- `/templates/concert-events-template.xlsx`
- `/admin/login`
- `/dev/sample-calendar.ics` in development mode only
- `/dev/sample-jsonld-event.html` in development mode only
- `/dev/sample-events.rss` in development mode only
- `/dev/sample-event-cards.html` in development mode only

Admin-only routes:

- Every `/admin/*` route except `/admin/login`
- Every `/preview/*` route
- Admin approval, pause, block, trust, quarantine, crawl, import-review, and
  logout POST actions
- Regional app-feed JSON routes under `/admin/app-feed/regions/*`
- Deferred app-team itinerary JSON under `/admin/app-feed/itineraries*`

Admin sessions use a signed HttpOnly cookie with `SameSite=Lax`. The cookie is
`Secure` when `APP_ENV=production`; local development allows non-secure cookies
for `http://127.0.0.1:8000`.

Log out from the admin navigation bar after logging in, or POST to
`/admin/logout` from an authenticated admin form.

## Security Hardening

Public URLs, public tunnels, staging deployments, and real provider credentials
should not be used until the security checklist in
`docs/security-hardening.md` has been reviewed.

Important local defaults:

- `TURNSTILE_ENABLED=false`, so local public form testing still works.
- `TURNSTILE_SECRET_KEY` and provider API keys are read from environment only.
- Live provider calls remain off unless provider-specific config and
  credentials explicitly enable them.
- `APP_FEED_PUBLIC=false`, so app-feed style routes stay private by default.
- Development fixture URLs can use localhost; production crawler safety blocks
  localhost, private networks, metadata IPs, and unsafe redirects.

Production-facing controls:

- Enable Turnstile for public POST routes with `TURNSTILE_ENABLED=true`,
  `TURNSTILE_SITE_KEY`, and `TURNSTILE_SECRET_KEY`.
- Tune public limits with
  `PUBLIC_SUBMIT_RATE_LIMIT_PER_IP_PER_HOUR`,
  `PUBLIC_SUBMIT_RATE_LIMIT_PER_EMAIL_PER_DAY`,
  `PUBLIC_SUBMIT_RATE_LIMIT_PER_DOMAIN_PER_DAY`,
  `PUBLIC_FILE_UPLOAD_MAX_SIZE_MB`, and `PUBLIC_FILE_UPLOAD_MAX_ROWS`.
- Set `ADMIN_SESSION_TIMEOUT_MINUTES`, keep secure cookies enabled through
  `APP_ENV=production`, and use only `ADMIN_PASSWORD_HASH` for production admin
  access.
- Review `/admin/security` regularly for failed logins, blocked public
  submissions, Turnstile failures, crawler blocks, provider live-call blocks,
  and recent audit actions.

## UI Shells

The POC uses three separated UI shells:

- Public pages use a dark Music Roadtrip-branded shell with client-facing
  event and calendar intake cards, clear CTAs, dark form controls, and no admin
  navigation.
- Admin pages under `/admin/*` use a dark command-center shell with grouped
  sidebar navigation, breadcrumbs, signed-in admin state, logout, dark tables,
  status badges, clear flash messages, and mobile-friendly stacking.
- Preview pages under `/preview/*` remain private/authenticated and use the same
  dark visual system with brighter Concert and quality-review accents.

`/admin/login` is separate from those shells and renders as a centered login
card on a dark gradient background.

The visual system uses local CSS only. It takes general inspiration from
creative command-center tools: charcoal panels, thin borders, subtle glows,
green Music Roadtrip accents, yellow Concert accents, amber/red/cyan status
colors, and compact operational layouts. No paid Adobe assets, fonts, icons, or
copyrighted UI assets are required.

## Brand Assets

Music Roadtrip logo assets are served as static UI branding from
`app/web/static/images/` and documented in
`docs/design/brand/music-roadtrip-brand-assets.md`.

- Square logo: public `/submit-events` hero and docs.
- Circle logo: admin login, admin sidebar, compact public forms, and preview
  shell.
- Plate logo: optional marketing-style hero only.

These logos are UI assets only. They must not become event images, venue images,
fallback event images, image candidates, selected main images, or image QA
inputs.

## Mapotic Export Analysis And POI Registry

The current Mapotic export is the dedupe seed for existing Music Roadtrip
places. Raw exports can be large, so keep them local under `data/imports/` or
reference the Downloads path. `data/imports/*.csv` is ignored by git.

Copy the current export locally when needed:

```bash
cp /Users/augat/Downloads/Mapotic_Export_6_11_26.csv data/imports/Mapotic_Export_6_11_26.csv
```

Generate the deterministic audit artifacts:

```bash
python -m app.tools.analyze_mapotic_export data/imports/Mapotic_Export_6_11_26.csv
```

This writes:

- `docs/mapotic-export-normalization-audit.md`
- `data/generated/mapotic_export_profile.json`
- `data/generated/current_poi_registry.jsonl`
- `data/generated/current_poi_duplicate_candidates.csv`
- `data/generated/current_event_export_profile.json`

Import the generated POI seed into SQLite:

```bash
python -m app.tools.import_poi_registry data/generated/current_poi_registry.jsonl
```

Registry rules:

- `Category = Concert` rows are events and are excluded from the POI registry.
- `Category != Concert` rows are normalized as POIs/places.
- POI subcategories come from the category-specific Mapotic columns documented
  in `docs/category-system.md`.
- POI dedupe uses normalized name plus latitude/longitude rounded to five
  decimals when available, with PlacesID, MapoticID, and Canonical Venue ID as
  additional strong identity signals.
- Incoming `poi_candidates` from extraction and API Feed Review dedupe against
  the live `poi_locations` table first, then the latest
  `current_poi_dedupe_index.json` snapshot as a secondary reference. They must
  be approved, linked, rejected, or marked event-venue-only before any
  `poi_locations` row is created or updated.
- The database remains the source of truth. POI inventory JSON/JSONL files are
  generated snapshots for review, matching, and audit.
- Music Roadtrip logo assets and social/video URLs are not exported as valid
  POI image URLs.

The current contract is documented in `docs/current-normalization-contract.md`.
The admin registry pages are `/admin/poi-locations`,
`/admin/poi-locations/{id}`, and `/admin/poi-duplicates`.

Current POI inventory snapshots:

```bash
python -m app.tools.export_poi_inventory
python -m app.tools.export_poi_inventory --dedupe-only
```

This writes private generated artifacts under `data/generated/poi_inventory/`
and monthly archive copies under `data/generated/poi_inventory/archive/`.
Generated POI inventory files are ignored from git. More detail:
`docs/current-poi-inventory-snapshots.md`.

Incoming POI candidate audit:

- `/admin/poi-candidates` lists venues/places discovered during JSON-LD/HTML
  extraction, API Feed Review, file upload, manual admin, or future safe source
  flows.
- `/admin/poi-candidates/{id}` shows provenance, match evidence, quality flags,
  image warnings, suggested category/subcategory, and admin decisions.
- `/admin/poi-audit` redirects to the candidate review page.
- Candidates can be approved as new POIs, linked to existing POIs, used to
  safely update existing POIs, marked event-venue-only, marked needs-research,
  rejected, or recomputed.
- Weak matches remain review-only and are not auto-linked or auto-merged.
- `poi_candidates` never appear in app-feed POIs. App-feed POIs still come only
  from approved/published `poi_locations` and still exclude `Category =
  Concert`.

More detail: `docs/incoming-poi-candidate-audit.md`.

## Destination Region Layer And Search Seeds

Milestone 5.0 adds a region/destination layer for organizing Music Roadtrip
events, POIs, calendar sources, quality snapshots, and private app feeds by
city, metro, state, country, tourism board, custom region, and Certified Music
Region.

Admin pages:

- `/admin/regions` lists regions and creates basic region records.
- `/admin/regions/{id}` shows summary cards, source coverage, latest quality
  snapshot, and private regional app-feed links.
- `/admin/regions/{id}/events` lists Concert events assigned to the region.
- `/admin/regions/{id}/pois` lists POI/place records assigned to the region.
- `/admin/regions/{id}/sources` lists master calendar sources assigned to the
  region.
- `/admin/regions/{id}/quality` generates and displays quality snapshots.
- `/admin/regions/{id}/report` generates partner/destination reports.
- `/admin/search-seeds` lists internal search seed locations.
- `/admin/source-quality` lists source trust scores and recommendations.
- `/admin/partner-reports` lists generated destination/source-quality reports.

Private regional app-feed routes:

- `/admin/app-feed/regions/{region_id}/events.json`
- `/admin/app-feed/regions/{region_id}/pois.json`
- `/admin/app-feed/regions/{region_id}/venues.json`

Search seeds can be generated locally from approved POI/location data and
regions:

```bash
python -m app.tools.seed_search_locations
python -m app.tools.seed_search_locations --assign-regions
```

The CLI creates search seed records only. It does not create events, create
POIs, call external geocoding/search APIs, scrape CitySpark, or make live
provider API calls.

Region inference is conservative:

- POIs match by city/state/country first, then by nearest region center only
  when coordinates fall inside the region radius.
- Events inherit the linked venue/POI region when available, then match venue
  city/state/country, then coordinates.
- Master calendar sources match only from their submitted city/state/country or
  region/market fields; ambiguous sources remain unassigned.

This supports tourism board workflows, regional launch planning, Certified
Music Region reporting, partner dashboards, source coverage review, and an
internal search-first strategy that can reduce reliance on paid external search
and geocoding calls over time.

Concert remains `category=Concert` and `record_type=event`. Concert records are
not POIs. Regional POI feeds continue to exclude Concert rows.

More detail: `docs/regions-and-search-seeds.md`.

## Event Quality Workbench

Milestone 5.4A adds `/admin/event-quality`, Scott's main review page for
improving normalized Concert listings before they reach the app feed.

The workbench shows bucket counts and filters for missing images, pending image
approval, blocked generic/provider images, poster/flyer/admat images,
social-graphic evidence-only images, missing tickets, bad/generic ticket links,
missing venues, missing coordinates, duplicate candidates, weak dedupe
confidence, low music relevance, missing artist/headliner, missing genre,
not-app-feed-ready events, recently updated events, and events with multiple
source claims.

Each row shows event name, headliner, date/time, venue, city/state, providers,
source claim count, dedupe status, image status, image selection reason, ticket
status, music relevance score, event quality score, app-feed readiness score,
and actions for event detail, preview, image candidates, photo rescue, source
claims, duplicate group, and app-feed JSON preview.

Safe bulk actions:

- Run photo rescue for selected.
- Find ticket-page images for selected.
- Mark selected needs image review.
- Recompute event quality for selected.
- Send selected to duplicate review if suspicious.

All mutation actions require CSRF. The workbench does not auto-approve,
auto-publish, make live provider calls, scrape CitySpark, or bypass dedupe,
source claims, image QA, photo rescue, ticket QA, POI registry, or app-feed
safety.

Dashboard cards show Events needing photos, Events needing tickets, Events with
duplicate risk, Events not app-feed ready, and Events ready for app feed.

More detail: `docs/event-quality-workbench.md`.

## Ticket Page Image Fallback

Milestone 5.6B adds a controlled image fallback for events whose provider image
is missing, generic, blocked, evidence-only, or otherwise weak. When an admin
or background job explicitly runs the fallback, the system safely fetches the
event-specific ticket page, requires `text/html`, and extracts only public
image metadata from `og:image`, `twitter:image`, and JSON-LD `image` fields.

Created candidates use `source_type=ticket_page` and
`rescue_source=ticketing_page_image`. They remain Image QA candidates with
`needs_approval` clearance; the workflow does not auto-approve, auto-publish,
fetch during normal page render, make provider API calls, scrape social
platforms, or use Music Roadtrip logo assets as event images.

Image QA also hard-blocks or downgrades provider stock/evidence signals such as
JamBase `x-promoImage` promo/admat images, CitySpark `links[].logoUrl` logo
evidence, placeholder/default/no-image URLs, repeated generic provider images,
thumbnails, logos, posters, flyers, admats, and social-graphic evidence.

Admins can trigger ticket-page fallback from event detail, Image QA, Event
Quality, API feed run detail, or background jobs. More detail:
`docs/ticket-page-image-fallback.md`.

## App Search, Map Markers, And Filter Contract

Milestone 5.2 adds a private app contract for internal-first search, map marker
metadata, category filters, and lightweight discovery slots. It uses existing
normalized events, POIs, venues, regions, and search seeds. It does not build a
mobile app, call external search/geocoding APIs, make live provider calls, or
publish records automatically.

Admin routes:

- `/admin/app-search` searches the local app index and previews marker metadata.
- `/admin/app-search/results.json` returns app-safe search results.
- `/admin/app-search/suggest.json` returns compact typeahead suggestions.
- `POST /admin/app-search/rebuild-index` rebuilds `app_search_index` and
  requires CSRF.
- `/admin/app-feed/map-markers.json` returns event/POI marker metadata.
- `/admin/app-feed/filter-options.json` returns event and POI filter options.
- `/admin/app-feed/discovery.json` returns enabled discovery slot placeholders.
- `/admin/app-feed/regions/{region_id}/map-markers.json` returns regional map
  markers.
- `/admin/app-feed/regions/{region_id}/filter-options.json` returns regional
  filter options.
- `/admin/app-feed/regions/{region_id}/discovery.json` returns regional
  discovery slots.

Optional app routes follow the same private-by-default `APP_FEED_PUBLIC`
behavior as the existing app feed:

- `/api/app/search`
- `/api/app/search/suggest`
- `/api/app/map-markers`
- `/api/app/regions/{region_id}/map-markers`
- `/api/app/filter-options`

Search ranking uses exact, prefix, contains, and simple normalized matching.
Certified POIs, app-feed-ready records, upcoming events, regions, and weighted
search seeds receive ranking boosts, but boosts do not make unrelated rows
match. Rejected, stale, archived, unpublished, merged, and duplicate-candidate
events are excluded by default.

Marker payloads are metadata only. Event markers use an `event_ticket` icon key
and visible `Event` label while retaining backend `category=Concert`.
POI/place markers derive style from category/subcategory, and certified POIs can
set `glow=true`. Region markers are intended for overview/search layers.

Filter options intentionally separate Events from POIs. `Concert` is not a POI
category and does not appear in POI category filters. Music Roadtrip logo assets
remain UI branding only and must not be used as event, venue, POI, fallback, or
marker images.

Background job types:

- `rebuild_app_search_index`
- `app_map_feed_export`
- `app_filter_options_export`

Scheduled task type:

- `rebuild_app_search_index`

More detail: `docs/app-search-and-map-contract.md`.

## Deferred App-Team Itinerary Contract

Existing itinerary/Road Trip work is deferred and app-team-owned. Backend
records use `itinerary`, `itinerary_stop`, and `itinerary_segment`; app-facing
labels can be Road Trip, Tour, Setlist, or Route, but this repository should
not continue building route builders, saved trips, or consumer navigation
unless explicitly requested.

Compatibility routes:

- `/admin/itineraries`
- `/admin/itineraries/new`
- `/admin/itineraries/{id}`
- `/admin/itineraries/{id}/stops`
- `/admin/itineraries/{id}/preview`
- `/preview/itineraries`
- `/preview/itineraries/{id}`

Deferred private app-feed routes:

- `/admin/app-feed/itineraries.json`
- `/admin/app-feed/itineraries/{id}.json`
- `/admin/app-feed/regions/{region_id}/itineraries.json`
- `/admin/app-feed/artists/{artist_id}/itineraries.json`
- `/api/app/itineraries`
- `/api/app/itineraries/{id}`
- `/api/app/regions/{region_id}/itineraries`
- `/api/app/artists/{artist_id}/itineraries`

Itinerary stops reference existing normalized events, POIs, venues, regions, or
artists and store only app-safe snapshot fields. Concert records remain events
and can appear as event stops; they are never converted into POIs. Category
filters remain separate: `Concert` does not appear as a POI category.

Navigation links are external Google/Apple handoff URLs built from stored
addresses or coordinates. The service does not call routing, geocoding, search,
provider, CitySpark, ticketing, or social APIs and does not use API keys.

App search indexes approved/published itineraries as `entity_type=itinerary`.
Discovery slots can include `itinerary_carousel`, and filter options include
itinerary types/regions alongside the existing event and POI filters. Treat
that as compatibility support, not active Scott workflow scope.

Background job types:

- `itinerary_quality_rollup`
- `itinerary_app_feed_export`
- `build_artist_tour_itinerary`
- `build_region_itinerary_suggestions`

Suggestion jobs create draft-only itineraries. Nothing auto-publishes. Do not
expand this job family unless the user explicitly reopens itinerary work.

More detail: `docs/itinerary-roadtrip-contract.md`.

## Artist Registry, Genre Normalization, And Music Relevance

Milestone 5.3 adds a local artist registry and broad genre normalization layer.
It builds `canonical_artists`, `artist_source_claims`, and `event_artists` from
approved normalized Concert events, JamBase performer data, file-upload
headliners/supporting artists, and conservative JSON-LD performer data.

Admin routes:

- `/admin/artists`
- `/admin/artists/{id}`
- `/admin/artist-duplicates`

App event JSON keeps `headliner` and `supporting_artists` for compatibility and
adds an `artists` array with artist ID, name, role, Spotify URL, image URL, and
normalized genres. Raw provider payloads and source-claim JSON are not exposed
in app feed records.

Genre filters use normalized genres where available. Music relevance scoring is
a QA signal based on provider music segments, explicit music/concert labels,
linked artists/headliners, venue music context, ticket/event source signals, and
non-music category penalties. It does not auto-publish or auto-reject records.

Background job types:

- `rebuild_artist_registry`
- `artist_genre_normalization`
- `artist_image_rescue`

Photo rescue can use linked artist image candidates, including JamBase
performer images, while still respecting image QA and manual accepted-image
protection.

More detail: `docs/artist-registry-and-genre-normalization.md`.

## Source Trust Scoring And Partner Reports

Milestone 5.1 adds source quality rollups for deciding which calendar sources,
API providers, regions, and partner submissions are producing clean
app-ready data.

Source trust scoring starts from 100 and applies penalties for extraction
failures, unsupported crawls, duplicate candidates, rejected rows, missing or
bad ticket links, missing images, generic provider images, pending image
approval, missing venues, missing geo, manual correction rates, and stale/no
recent success. Positive signals include app-feed-ready records, successful
extraction history, good image and ticket coverage, trusted approval state, and
multiple source claims. Grades are:

- `excellent`: 90-100
- `good`: 75-89
- `fair`: 60-74
- `poor`: 40-59
- `blocked`: 0-39
- `unknown`: missing or intentionally unscored data

Admin routes:

- `/admin/source-quality`
- `/admin/source-quality/{id}`
- `/admin/partner-reports`
- `/admin/partner-reports/{id}`
- `/admin/regions/{id}/report`

Reports include event and POI counts, app-feed readiness, source coverage,
events created/updated, duplicate candidates, source claims, image issues,
ticket-link issues, extraction failures, source grades, top sources, weak
sources, and recommended next actions. JSON and CSV exports are available from
each partner report detail page.

Background job types:

- `source_quality_rollup`
- `all_source_quality_rollup`
- `region_partner_report`

Scheduled task families:

- `source_quality_rollup`
- `partner_report_export`

These scores and reports are review aids only. They do not auto-publish,
auto-crawl, bypass image/ticket QA, bypass dedupe/source claims, or make live
provider calls.

More detail: `docs/source-trust-and-partner-reporting.md`.

## Test

```bash
make test
```

## Lint

```bash
make lint
```

## Background Jobs And Scheduler

Milestone 4.8 adds a local SQLite-backed queue for operational jobs. It does
not add Redis, Celery, cron, or an always-on production scheduler.

Admin pages:

- `/admin/jobs` lists queued, running, successful, failed, cancelled, and
  skipped jobs.
- `/admin/jobs/{id}` shows redacted payload, result, error, attempts,
  timestamps, worker lock metadata, and links to related crawl/API/export
  records where available.
- `/admin/scheduled-tasks` lists manual scheduler task definitions.
- `/admin/scheduled-tasks/{id}` shows task payload and last-job provenance.

Manual commands:

```bash
python -m app.tools.run_worker --once
python -m app.tools.run_worker --limit 5
python -m app.tools.run_scheduler --once
python -m app.tools.run_scheduler --dry-run
```

The worker processes one job by default. It only polls continuously when
`--loop` is passed explicitly. The scheduler only enqueues due jobs; workers
must be run separately.

Supported job types include app feed export, single-source crawl, bulk crawl,
due-source crawl, crawl-run extraction, extracted-event candidate approval,
extracted-event batch processing, JamBase live sandbox, CitySpark live sandbox,
image preflight, event photo rescue, API-feed-run photo rescue, recent-event
photo rescue, source quality rollups, region partner reports, and placeholder
POI registry import. POI candidate jobs can recompute match/quality for one
candidate or all pending candidates, but they do not promote candidates into the
POI registry. Provider jobs still use the existing provider services, so live
API calls remain off unless credentials and explicit configuration enable them.
Crawl jobs still use the existing crawl gate: `status=approved` and
`review_status=approved`.

Photo rescue jobs use stored provider JSON, existing image candidates, and the
existing image QA rules. They do not scrape social platforms, call AI/OCR, or
fetch new provider data by default. Operators can queue photo rescue from event
details, API feed run details, and the Image QA board; worker results show
selected image counts, blocked generic candidate counts, and events still
missing a usable image.

All job payloads, results, and errors are redacted before storage/display for
common secret fields such as API keys, tokens, passwords, authorization
headers, `X-API-Key`, and sensitive URL query parameters.

More detail: `docs/background-jobs-and-scheduler.md`.

## Boss Demo Workflow

1. Open `/submit-calendar` to choose Submit One Calendar URL or Upload Calendar
   Sources.
2. Open `/submit-events` to upload event rows.
3. Log in at `/admin/login`.
4. Review submissions, import batches, master calendar sources, and the crawl
   queue from the admin sidebar.
5. Use `/admin/master-calendar-sources` to approve/pause/block sources or run
   selected/due crawls.
6. Use `/admin/api-feeds` for provider-record review and
   `/admin/image-candidates` for visual QA.
7. Open `/admin/regions` to review regional coverage and quality snapshots.
8. Open `/preview/events`, `/preview/venues`, and `/preview/quality` to inspect
   private preview output.

## Manual Source Extraction Demo Paths

1. Start the app with `make dev`.
2. Open `/submit-calendar`.
3. Submit the local demo calendar URL:
   `http://127.0.0.1:8000/dev/sample-calendar.ics`.
4. Open `/admin/sources`.
5. Change the submitted source status to `approved`.
6. Click `Run Crawl` beside the approved source.
7. Review the crawl result detail page and confirm extracted event count.
8. Open `/admin/events` to review normalized events.
9. Open an event detail page to review source and crawl provenance.

The same manual path can be used with these non-ICS fixture URLs:

- `http://127.0.0.1:8000/dev/sample-jsonld-event.html`
- `http://127.0.0.1:8000/dev/sample-events.rss`
- `http://127.0.0.1:8000/dev/sample-event-cards.html`

For non-ICS sources, the crawl detail page shows the extractor type, extraction
status, staged candidate count, warnings/errors, and discovered event links.
Open `/admin/extracted-events` to review staged candidates. Approving a valid
candidate sends it through the shared event dedupe/source-claim path, ticket
QA, image candidate creation, and photo rescue. It does not auto-publish the
event.

Development fixture routes return 404 when `APP_ENV=production`.

The source extraction milestone is intentionally conservative. It parses
approved crawl responses only; it does not scrape CitySpark pages, make live
provider API calls, run browser automation, execute JavaScript, follow links
recursively, bypass crawl gates, or publish extracted records automatically.
More detail: `docs/source-extraction-policy.md`.

## Event Intake And Category Rules

Public and admin UI generally refer to submitted records as Events. Internally,
event records are still normalized with `category=Concert` and
`record_type=event`. This preserves the category-system rule that Concert
records are events and never POIs, while using clearer language for users and
the Music Roadtrip team.

Every submitted event is treated internally as a `Concert`. Concert records are
always events and must never be treated as POIs.

Concert records may originate from approved client calendars, client event
uploads, tourism board calendar submissions, partner feeds, public venue
calendars, artist calendars, festival calendars, ticketing/event pages,
approved internal research, and licensed vendor/API feeds reviewed through the
private workbench. CitySpark is a licensed vendor feed, not a first-party public
submission source, and must not be scraped or manually submitted by public users.

Use these public submission paths:

1. `/submit-calendar` for calendar-source intake.
2. `/submit-calendar/url` to submit one calendar URL.
3. `/submit-calendar/sources-file` to upload calendar-source CSV/XLSX files.
4. `/submit-events` for event upload intake.
5. `/submit-events/file` to upload event CSV/XLSX rows.

Legacy `/submit-concerts` URLs are retained as compatibility redirects or POST
aliases for existing bookmarks, tests, and integrations:

- `/submit-concerts`
- `/submit-concerts/calendar`
- `/submit-concerts/calendar-url`
- `/submit-concerts/events-file`
- `/submit-concerts/calendar-sources-file`

All public submissions pass through risk scoring and admin review. Nothing
submitted publicly becomes crawlable, scheduled, published, or live without
validation, risk scoring, and explicit admin approval.

## Downloadable Templates

Calendar source templates:

- `/templates/calendar-sources-template.csv`
- `/templates/calendar-sources-template.xlsx`

Event upload templates:

- `/templates/events-template.csv`
- `/templates/events-template.xlsx`

Legacy event template aliases:

- `/templates/concert-events-template.csv`
- `/templates/concert-events-template.xlsx`

## Calendar Source Registry Workflow

Single calendar URL submissions and calendar-source file uploads write into the
master calendar source registry after canonical URL dedupe.

Canonicalization lowercases the scheme/domain, removes common tracking
parameters such as `utm_*`, `fbclid`, and `gclid`, removes safe trailing slashes,
and preserves meaningful path/query values. Duplicate calendar URLs attach a new
submission claim to the existing master source instead of creating duplicate
master rows.

Calendar-source upload rows require:

- `Organization Name`
- `Calendar URL`
- `Contact Email`
- `Authorization Confirmed` as `true`, `yes`, `1`, or `y`

`Expected Category` may be blank or `Concert`; blank values normalize to
`Concert`. Unsupported source types are accepted as `unknown`.

Admin review:

1. Upload a calendar-source CSV/XLSX from `/submit-calendar/sources-file`.
2. Open `/admin/import-batches/{id}`.
3. Review validation errors, dedupe status, and risk flags.
4. Click `Approve valid rows`.
5. Open `/admin/master-calendar-sources` to review pending master sources.
6. Approve, pause, or block master sources.

Approving staged calendar-source rows creates only pending master registry rows
or attaches duplicate claims. It does not auto-crawl or schedule anything.

## Calendar Source Intelligence

Each approved master calendar source can have a scrape profile that remembers
how the source was crawled and extracted. Open `/admin/source-intelligence` or a
master source detail page to review:

- platform type and extractor type
- extractor confidence and last working extractor
- final URL, content type, and response hash
- total, successful, and failed crawl counts
- average and latest event yield
- duplicate, missing-ticket, missing-image, and POI-candidate rates
- source health, recipe lock state, and developer notes

Source health states are `healthy`, `watch`, `needs_review`, `failing`,
`paused`, and `unsupported`. They are operational QA signals only. They do not
auto-publish data or bypass source approval, crawler safety, dedupe, image QA,
ticket QA, POI candidate review, or app-feed readiness.

The `source_registry_snapshot_export` background job writes local generated
JSON snapshots under `data/generated/source_registry/`:

- `current_approved_calendar_sources.json`
- `current_source_scrape_profiles.json`

These generated files are ignored from git. The scheduled task key is
`monthly_source_registry_snapshot`. See
`docs/calendar-source-intelligence.md` for the full operating model.

## Calendar Source Research And City Crawl Shakedown

Use `/admin/source-research` to organize real city-by-city calendar collection
before sources are approved into the master registry. Scott can create a
research batch for a city or region, paste researched URLs, upload a CSV/XLSX,
dedupe URLs, safely preflight them, approve good sources, run a controlled
batch crawl, and review the shakedown report.

Download source-research templates:

- `/templates/calendar-source-research-template.csv`
- `/templates/calendar-source-research-template.xlsx`

The workflow keeps public and researched sources gated:

1. Gather URLs from tourism boards, venues, festivals, chambers, publications,
   partners, and internal research.
2. Canonicalize and dedupe each URL against `master_calendar_sources` and other
   items in the same batch.
3. Run preflight with the existing URL safety, timeout, redirect, content-type,
   and private-network protections.
4. Approve good items into the master source registry.
5. Run crawl only for approved master sources in the batch.
6. Review source intelligence, event extraction, event quality, ticket/image
   issues, and POI candidates in the shakedown report.

Batch crawls do not auto-publish events and do not auto-create POIs. Discovered
venues or locations are staged as POI candidates for admin review. See
`docs/calendar-source-research-and-city-crawl-shakedown.md` for the full
operating checklist.

## Admin Review UI

The admin sidebar groups the POC into Overview, Intake, Sources, Data, Feeds,
Preview, and Settings / Help. The crowded horizontal admin navigation was
removed from private admin pages.

Master Calendar Sources shows summary cards and primary actions before the
table. Filters are collapsed by default behind `Show filters` and expand into a
compact grid with Apply and Reset actions.

API Feeds renders provider cards with provider type, workbench status, live API
status, storage/compliance policy, pending/approved/rejected counts, latest run,
compliance notes, and an Open action. Licensed vendor feeds such as CitySpark
and JamBase can be visible in the workbench while live calls remain off until
credentials and configuration are added.

Image QA renders as a visual review board with chips for Needs approval, Needs
review, Selected pending approval, Missing image, Provider stock, Poster/flyer,
Watermark/text, Venue fallback, Accepted, and Rejected. Candidate cards show
preview, event or venue name, role, provider, score, clearance state,
selected/current badges, QA badges, and review actions.

Preview pages keep the event/venue distinction: Concert records are events,
never POIs. Venue profiles are POI-style containers that can display nested
events through venue linkage.

## Master Source Crawl Queue And Bulk Crawls

Master calendar sources are crawlable only when all of these are true:

- `status=approved`
- `review_status=approved`
- not blocked
- not quarantined

Public submissions and uploaded rows never become crawlable automatically. An
admin must approve the master source first.

Open `/admin/master-calendar-sources` to filter the approved source list by
status, review status, crawl frequency, city, state, region/market, source type,
submitting organization, last crawl result, due-for-crawl state, and risk level.
The table shows canonical URL, domain, location, submitter claims, risk,
frequency, last/next crawl time, last result, total runs, extracted event count,
and trusted submitter badges.

Available crawl actions:

- Run crawl for selected master sources.
- Run crawl for all sources matching the current filters.
- Run crawl for all due sources.
- Run crawl for approved sources attached to one import batch from
  `/admin/import-batches/{id}`.
- Use `/admin/crawl-queue` to run selected queue sources, run all due sources,
  pause selected sources, or change selected crawl frequency.

`manual` sources never become due automatically. `daily`, `weekly`, `biweekly`,
and `monthly` sources compute the next due timestamp from the latest crawl run;
never-crawled non-manual sources are due immediately. The POC now has a manual
scheduler foundation that can enqueue due crawl jobs from the CLI or admin UI,
but it does not run an always-on production scheduler.

Trusted submitters/domains can be recorded through the suspicious-submissions
admin tools. A trusted badge helps admins recognize familiar partners, but it
does not bypass validation, risk scoring, or the approval gates.

Example tourism-board batch workflow:

1. Download `/templates/calendar-sources-template.csv` or `.xlsx`.
2. Add the tourism board’s approved calendar URLs, one row per source.
3. Upload the file from `/submit-calendar/sources-file`.
4. Review `/admin/import-batches/{id}`.
5. Click `Approve valid calendar sources`.
6. Approve the resulting master sources in `/admin/master-calendar-sources`.
7. Click `Run crawl for approved sources in this batch` from the import batch
   detail page, or use `/admin/crawl-queue` for due/selected crawl operations.

## API Feed Review Workbench

Open `/admin/api-feeds` after logging in as an admin. This private workbench is
for reviewing incoming provider-style records before they become normalized
events. It is not a public data intake page and does not imply live API
calls are enabled.

Initial provider cards:

- `JamBase`: `Workbench Open`; `Live Calls Off` unless credentials and provider
  terms are explicitly configured; `Credentials Missing` until `JAMBASE_API_KEY`
  is set; `Permanent Allowed` for reviewed provider records.
- `CitySpark`: `Workbench Open`; `Licensed Vendor Feed`; `Live Calls Off`
  until credentials and configuration are added; `Permanent Allowed`;
  `Credentials Missing` until `CITYSPARK_API_KEY` and
  `CITYSPARK_PORTAL_SCRIPT_ID` are set.
- `Spotify`: `Workbench Open`; `Live Calls Off`;
  `Enrichment Suggestions Only`.
- `SerpAPI`: `Workbench Open`; `Live Calls Off`;
  `Enrichment Suggestions Only`.
- `manual_json`: `Workbench Open`; `Local Demo`; `Permanent Allowed`.

Provider state terminology:

- `Workbench Open` means the private review/demo/manual JSON UI is visible.
- `Workbench Hidden` is reserved for providers intentionally removed from the
  review UI.
- `Live Calls Off` means no live provider requests are made.
- `Live Calls On` means an admin-only live sandbox request can run for a
  provider with explicit config and credentials.
- `Credentials Missing` means credentials or required provider account IDs are
  absent.
- `Credentials Configured` means the local environment has the required values;
  the values are never rendered.
- `Permanent Allowed` means the local review path can approve normalized records
  when existing gates pass.
- `Enrichment Suggestions Only` means the provider is not a primary event feed.

Live provider API calls remain off by default. When explicitly configured, the
JamBase and CitySpark Live Sandbox can make admin-triggered provider requests
and stage results as pending API Feed Review records. The workbench supports:

- Raw provider-record inspection.
- Normalized candidate review.
- Source-chain provenance review.
- Synthetic demo imports.
- Manual `.json` upload.
- Feature-flagged JamBase and CitySpark live sandbox runs that write to
  `api_feed_runs` and `api_feed_records` only.
- JSON shapes that are a list of event objects or an object containing
  `events`, `event`, `data`, or `results`.
- Provider-specific mappers that normalize toward the Music Roadtrip Concert
  event schema.
- A review page showing raw provider data, source-chain provenance, normalized
  candidate fields, and QA/decision controls.
- Approve, hold, reject, and send-to-enrichment decisions.
- Incoming provider image review. Provider images can be sent to the image QA
  queue as candidates, but they are not accepted blindly as final event images.

Provider reference docs are summarized in
`docs/provider-mapping-reference.md`. The local references used by Milestone
3.9A and 3.9B are:

- `docs/jambase_api_reference.md`
- `docs/JamBase-JamBaseAPI.yaml`
- `docs/CitySpark_v1.json`
- `docs/ticket_link_summary.md`
- `docs/ticketmaster_classifications.md`
- `docs/provider-research/event_ticket_api_provider_research_pack_v2/EXPORT_ORIGIN_RESEARCH_SUMMARY.md`
- `docs/provider-research/event_ticket_api_provider_research_pack_v2/web_research_sources_v2.md`
- `docs/provider-research/event_ticket_api_provider_research_pack_v2/export_scan/master_export_origin_scan_summary.md`
- `docs/provider-research/event_ticket_api_provider_research_pack_v2/export_scan/concert_domain_counts.csv`
- `docs/provider-research/event_ticket_api_provider_research_pack_v2/export_scan/provider_candidate_counts.csv`
- `docs/provider-research/event_ticket_api_provider_research_pack_v2/provider_references/new_from_export/`
- `docs/provider-research/event_ticket_api_provider_research_pack_v2/data/provider_index_v2_export_additions.csv`
- `docs/provider-research/event_ticket_api_provider_research_pack_v2/codex/add-export-origin-provenance-prompt.md`

These files are schema and QA references only. They are not provider data
feeds, and they do not enable live API calls by themselves.

### Live Provider Connector Sandbox

The controlled live sandbox is documented in
`docs/live-provider-sandbox.md`. Routes:

- `/admin/api-feeds/jambase/live-sandbox`
- `/admin/api-feeds/cityspark/live-sandbox`

Required env values:

- `JAMBASE_LIVE_CALLS_ENABLED=true`
- `JAMBASE_API_KEY`
- `JAMBASE_BASE_URL`
- `JAMBASE_DEFAULT_PER_PAGE`
- `JAMBASE_SANDBOX_MAX_EVENTS`
- `CITYSPARK_LIVE_CALLS_ENABLED=true`
- `CITYSPARK_API_KEY`
- `CITYSPARK_PORTAL_SCRIPT_ID`
- `CITYSPARK_BASE_URL`
- `CITYSPARK_DEFAULT_PAGE_SIZE`
- `CITYSPARK_SANDBOX_MAX_EVENTS`

No-key local behavior is intentional: the sandbox pages show `Live Calls Off`
and `Credentials Missing`, the run button is disabled, and POST attempts fail
safely without making network requests. Request previews and saved run metadata
show `REDACTED` for `apikey`, `X-API-Key`, and portal identifiers.

Successful sandbox fetches create `api_feed_runs` with
`run_mode=live_api_sandbox` and pending `api_feed_records`. They do not create
normalized events, app-feed records, POIs, image approvals, or published output
until an admin approves records through the existing API Feed Review path.
Approval still uses the shared dedupe/source-claim upsert service.

Provider pipeline / developer handoff docs should explain the intended endpoint
or request shape, provider-field mapping, cleanup rules, ticket-link rules,
image QA rules, provenance fields, normalized output, and compliance gates. They
must not show secrets or imply that live calls are enabled without explicit
credentials and config.

## Provider Pipeline Developer Handoff

The private Provider Pipeline pages sit beside API Feed Review. API Feed Review
is where admins inspect actual staged provider records and make approve, hold,
reject, or enrichment decisions. Provider Pipeline is the developer handoff
surface for understanding how provider data is expected to be called, mapped,
cleaned, QA-reviewed, and normalized.

After logging in as an admin, open:

- `/admin/api-feeds/jambase/pipeline`
- `/admin/api-feeds/cityspark/pipeline`
- `/admin/api-feeds/manual_json/pipeline`
- `/admin/api-feeds/spotify/pipeline`
- `/admin/api-feeds/serpapi/pipeline`

Each provider pipeline page includes:

- provider overview, workbench state, live API state, storage/compliance state,
  retention/contract badges, latest run, and review counts
- credential-redacted request preview with env var names only
- request notes, pagination/rate-limit notes, and provider constraints
- field mapping table and focused `/mapping` page
- raw provider JSON and normalized Music Roadtrip candidate JSON examples
- transformation pipeline from raw provider record to future app/map feed
- cleanup rules, ticket-link QA rules, image QA rules, venue/POI boundary rules,
  compliance rules, and code references

Downloadable handoff exports:

- `/admin/api-feeds/{provider}/pipeline.md`
- `/admin/api-feeds/{provider}/pipeline.json`

Exports include provider overview, request example, mapping rules, cleanup
rules, ticket-link strategy, image QA strategy, compliance policy, service/code
references, and synthetic raw/normalized examples. Credential values are
rendered as `REDACTED`; env var names may be shown for future configuration.

Per-record lineage:

- `/admin/api-feed-records/{id}/lineage`

The lineage page shows one real staged provider record's raw payload, mapper
output, normalization warnings, provider IDs, source-chain provenance,
ticket-link classification, repair strategy, image candidate section, venue
match result, dedupe key/confidence, review status, and approved event/preview
links when an event exists.

Provider Pipeline pages do not make live API calls, do not add credentials, and
do not enable direct integrations by themselves. The separate Live Sandbox forms
are feature-flagged and credential-gated. CitySpark remains a paid licensed
vendor feed: the workbench can be open for licensed review/demo/manual JSON
workflows while live calls stay off until credentials and configuration are
added. CitySpark records still pass through API Feed Review, normalization,
dedupe, source claims, ticket QA, image QA, and app-feed readiness before use.

Export-origin provenance:

- The v2 export scan found downstream ticketing/event domains in Concert rows.
  Those providers are taxonomy/provenance entries only, not direct integrations.
- Recognized export-discovered providers include OpenDate, Universe, Skiddle,
  Humanitix, Ticket Tailor, Showpass, AudienceView/OvationTix,
  HoldMyTicket, TicketNetwork/Mercury Web Services, Vivid Seats/SkyBox,
  Prekindle, TixTrack/Nliven, Zeffy, EventVesta, Outhouse Tickets,
  VenuePilot, Biletix, SpeakeasyGo, Eventnoire, My805Tix/805Tix, 24tix,
  SimpleTix, Tix.com, TicketLeap, Afton Tickets, InstantSeats, and
  affiliate/tracking networks.
- API feed records and approved events can store `ingestion_provider`,
  `upstream_event_source`, `upstream_event_id`, `ticketing_provider`,
  `ticketing_provider_domain`, `provider_music_segment`, `source_chain_json`,
  `external_identifiers_json`, `ticket_offers_json`, and
  `provenance_flags_json`.
- Unknown upstream sources are flagged for review instead of guessed.
- Example chains shown in review can look like `JamBase -> Bandsintown -> AXS
  ticket page`, `CitySpark licensed review -> ticketUrl -> Eventbrite event
  page`, or `JamBase -> OpenDate ticket page`.

JamBase mapping rules:

- Current API reference: JamBase API v3.1.0, OpenAPI 3.1.0, JamBase Concert
  Data API.
- Base URL: `https://api.data.jambase.com/v3`.
- Authentication uses an `apikey` query parameter. Request previews use
  `apikey=REDACTED`; the pipeline page does not call the provider.
- The old `https://www.jambase.com/jb-api/v1` shape is legacy reference only
  and should not be shown as the primary request preview.
- Key endpoints include `/events`, `/events/id/{eventDataSource}:{eventId}`,
  `/streams`, `/streams/id/{streamDataSource}:{streamId}`, `/artists`,
  `/artists/id/{artistDataSource}:{artistId}`, `/venues`,
  `/venues/id/{venueDataSource}:{venueId}`, geographies, lookups, and
  `/genres`.
- Pagination uses `page` and `perPage`; `page` defaults to 1, `perPage`
  defaults to 40 and maxes at 100.
- The v3.1.0 eventType enum is plural: `concerts` and `festivals`.
- Accept an object with `events`, a single event object, an event detail object
  with `event`, or a list of event objects.
- Use `identifier` as `source_record_id` / `provider_event_id` and the
  strongest dedupe input.
- Preserve `@type` / `type` as `provider_event_type`; Festival still becomes a
  `Concert` event candidate while retaining `provider_event_type=Festival`.
- Treat `startDate`, `endDate`, `previousStartDate`, and `doorTime` as
  venue-local values; use `location.address.x-timezone` when conversion is
  needed.
- Map `eventStatus` into event lifecycle review status and preserve
  reschedule/deletion/merge metadata for QA.
- Map performers into headliner, supporting artists, `event_artists`, artist
  source claims, genre, Spotify/social candidates, artist image candidates, and
  provider artist ID.
- JamBase performer images enter photo rescue as high-priority artist image
  candidates; unresolved clearance still requires image approval.
- JamBase performer genres feed `provider_genres_json`,
  `normalized_genres_json`, and app event genre filters.
- Map performer, location, offers, sameAs, external identifiers, venue IDs, geo,
  address, timezone, source URL, and image into mapping/provenance metadata.
- Prefer `offers[].url` with `ticketingLinkPrimary`, then
  `ticketingLinkSecondary`, and classify the resulting ticket candidate.

CitySpark licensed-provider rules:

- API usage requires an API key and CitySpark account.
- Key event paths include `/v2/event/search`, `/v2/event/details`, and
  `/v2/event/categories`.
- CitySpark is visible in the workbench for licensed vendor/API review,
  demo/manual JSON workflows, and provider-specific normalization QA.
- Live calls remain off until credentials and configuration are added.
- Public users must not upload or submit CitySpark-exported data as if it were
  their own source.
- Tests use synthetic CitySpark-like fixtures; licensed CitySpark records should
  enter only through the private provider workbench with provenance and normal
  admin approval controls.
- EventSeries fields such as `eventId`, `name`, `description`, `summary`,
  `primaryImage`, `categories`, `labels`, `location`, `instances`, `price`,
  `ticketUrl`, `links`, and start/end fields map into review candidates.
- `ticketUrl` is the preferred ticket repair target. `links[].linkUrl` and
  generic event `url` are supporting links only unless ticket-link QA validates
  them as event-specific.
- CitySpark uses normal licensed vendor retention and can be approved through
  the same admin review workflow as JamBase.
- CitySpark music relevance is based on explicit categories, labels, and
  concert/music fields. Artist inference remains conservative and should use
  only explicit artist/performer data when present.

Ticket-link QA categories:

- `direct`
- `redirect_or_handoff`
- `platform_event`
- `platform_generic_or_app`
- `non_ticket`
- `blank`
- `suspicious`
- `unresolved`

Ticket QA accepts direct pages, clear ticket handoffs, and event-specific
platform pages. It flags or rejects generic/app pages, Eventbrite
`/checkout-external`, generic DICE handoffs, Ticketmaster home/artist/generic
pages, tracking parameters such as `utm_*`, `fbclid`, and `gclid`, restricted
vendor affiliate markers, affiliate/tracking domains, and session/cart-like
URLs. Affiliate/tracking domains are treated as handoffs that need a final
event-specific ticket URL.

Ticketmaster classification usage:

- `segment=Music` is a positive music relevance signal.
- Music genre/subgenre values may populate `music_category`,
  `provider_genre`, `provider_subgenre`, and `normalized_genre`.
- Non-Music segments are flagged as low relevance.
- Ticketmaster taxonomy is event/music metadata only; it does not create
  venue/POI categories.

Approval rules:

- Every approved API event candidate becomes `category=Concert`,
  `record_type=event`, and `source_type=api_feed`.
- Approval creates or updates a normalized event using the candidate dedupe key
  and links or creates a venue profile.
- Concert records remain events and are not converted into POIs.
- Hold, reject, and send-to-enrichment decisions do not create events.
- CitySpark records can be approved into normalized events through the normal
  admin review workflow. Live API calls remain off unless future configuration
  such as `CITYSPARK_LIVE_CALLS_ENABLED=true` and credentials are added.
- API feed record detail, admin event detail, preview event detail, and the
  quality dashboard expose ticket-link classification, repair suggestion,
  repair strategy, recommended ticket link, provider mapping notes, source
  chain, external identifiers, ticket offers, provenance flags, dedupe source
  fields, and venue-match fields.

Provider credentials must come from environment variables. Do not hardcode or
paste API keys into templates, tests, logs, or README examples. Supported
environment variable names are listed in `.env.example`; leave values blank
unless you are configuring a local private environment.

## Professional Image QA Workflow

Concert event images are scored as candidates before they become selected event
images. The app stores reviewable `image_candidates` for events and venue
profiles, plus selected image fields on `events` and `event_venues`.

Preferred Concert image order:

1. Actual artist/band/DJ live performance photo.
2. Official artist press photo.
3. Clean event-specific provider image.
4. Venue-in-action photo from the linked venue.
5. Venue exterior or marquee photo from the linked venue.
6. If no candidate is acceptable, mark the event as missing or needing review.

Rejected or blocked automatic image types:

- Generic stock/provider placeholders.
- Posters, flyers, admats, logos, screenshots, and text-heavy graphics.
- Watermarked images unless an admin explicitly accepts them.
- Unrelated food/drink/interior photos, unrelated places, and generic crowd
  shots without artist, venue, or music signal.
- Social-media pages/posts/profiles used as image URLs.
- Generic web pages, ticket pages, or HTML article URLs used as image URLs.
- Broken, inaccessible, non-image content-type, or severe low-resolution URLs.

Unknown clearance is not a rejection reason. Unknown image clearance is kept in
the queue as `needs_approval` so the team can resolve permissions case by case.
`candidate_status` describes the visual/review decision (`pending_review`,
`accepted`, `rejected`, `needs_review`, `needs_approval`, `expired`).
`clearance_status` describes rights/permission state (`unknown`,
`needs_approval`, `approved`, `rejected`, `licensed`, `partner_supplied`,
`provider_allowed`). `image_status` describes whether an image is currently
selected for display (`accepted`, `selected_pending_approval`, `needs_review`,
`missing`, `rejected`, or `venue_fallback`).

The system uses the best eligible image immediately. If approval or clearance
is still needed, the image remains visible in the normalized selected image
field and internal preview, but it is marked `Selected · Needs Approval`. The
team can clear, reject, or replace it later.

Admin workflow:

1. Open `/admin/image-candidates`.
2. Filter by event, venue, source type/provider, image role, status, clearance,
   stock/text/watermark/poster flags, missing dimensions, low resolution, or
   selected state.
3. Review the direct asset flag, dimensions, content type, quality score,
   source URL, source chain, QA flags, and rejection reasons.
4. Use CSRF-protected actions to accept, reject, mark needs review, mark needs
   approval, approve/reject clearance, update manual QA toggles, run safe
   preflight metadata, select for an event/venue, rerun best-image selection,
   or run photo rescue.

Manual preflight is explicit. Normal page renders do not fetch arbitrary image
URLs. The current POC stores and scores provided metadata only; a future
background job may perform HEAD-first checks with safe timeouts and production
network protections.

Event selection behavior:

- Event candidates are considered before venue fallback candidates.
- Accepted admin-reviewed candidates win and are not overwritten by lower-ranked
  automatic candidates.
- Clean pending candidates are selected immediately as
  `selected_pending_approval` when clearance is still unknown or unresolved.
- Cleared candidates use `image_status=accepted` only when
  `clearance_status` is `approved`, `licensed`, `partner_supplied`, or
  `provider_allowed`.
- Venue fallback is used only from the linked venue, and preview badges call it
  out as `Venue fallback image`; pending venue fallback also shows
  `Needs Approval`.
- UI placeholders are display-only and are never stored as
  `selected_main_image_url`.

Provider/upload behavior:

- API feed records, API approvals, and event uploads create image
  candidates instead of blindly treating provider/upload image URLs as final.
- API Feed Review can send all discoverable provider payload images to Image QA,
  including source paths such as `jambase.image`,
  `jambase.performer[0].image`, `jambase.x-promoImage`,
  `jambase.location.image`, `cityspark.primaryImage.largeImageUrl`, and
  `cityspark.media[0]`.
- Photo rescue prefers artist imagery, then clean provider event imagery, then
  venue-in-action fallback. It records `rescue_source`, `rescue_priority`,
  `source_payload_path`, `selected_reason`, and a selection explanation JSON on
  the chosen candidate.
- Social graphics, provider logos, posters, flyers, admats, text-heavy images,
  and generic placeholders can be stored as review evidence, but are marked
  `source_evidence_only` or `can_be_final_image=false` so they are not selected
  automatically as final event images.
- If the provider/upload image is the best eligible candidate, it is selected
  provisionally and marked `Needs Approval` until cleared.
- Provider stock placeholders reused across unrelated events are flagged as
  `stock_placeholder_candidate`.
- Spotify and SerpAPI remain candidate-policy placeholders only. This milestone
  does not make live Spotify or SerpAPI image calls.

Preview visibility:

- `/preview/events`, `/preview/events/{id}`, `/preview/venues/{id}`, and
  `/preview/quality` show image QA badges such as `Missing image`, `Needs image
  review`, `Selected image`, `Selected · Needs Approval`, `Needs approval`,
  `Provider stock candidate`, `Poster/flyer detected`, `Text-heavy image`,
  `Watermark suspected`, `Venue fallback image`, `Artist image`,
  `Provider image`, `Venue image`, `Spotify candidate`, `SerpAPI candidate`,
  `Selected by rescue`, `Generic provider image blocked`,
  `Poster/flyer/admat blocked`, `Source evidence only`, and
  `Manual image accepted`.
- `/preview/quality` includes counts for missing images, venue fallbacks,
  selected images, selected images pending approval, selected cleared images,
  missing usable images, provider images pending approval, hard-blocked image
  candidates, provider stock candidates, approval queues, text-heavy candidates,
  watermark candidates, poster/flyer candidates, accepted artist images,
  accepted venue fallback images, photo-rescue selections, generic provider
  blocks, poster/flyer/admat blocks, social graphic evidence rows, artist image
  candidates, and venues needing image approval.

The future OCR/computer-vision hooks are `analyze_image_candidate()` and
`extract_text_from_image_candidate()`. They return structured placeholder
fields for text, watermark, logo, poster/flyer, live performance, artist
subject, venue-in-action, stock placeholder, food/drink, generic crowd,
unrelated place, aesthetic score, sharpness score, and OCR status. No external
AI image service is called in this milestone.

See `docs/event-photo-rescue-policy.md` for the full event photo rescue policy,
provider payload extraction paths, selection ranking, final-image blocks, and
app-feed image metadata rules.

## Event Upload Workflow

Event upload rows are staged in `staged_events` and reviewed through
`/admin/import-batches/{id}` before they become normalized events.

Required fields:

- `Category` blank or `Concert`
- `Event Name`
- `Headliner`
- `Start Date`
- `Timezone`
- `Venue Name`
- `City`
- `State`
- Either `Event URL` or `Tickets Link`
- Either `Venue Address` or both `Latitude` and `Longitude`

Validation notes:

- Blank `Category` normalizes to `Concert`.
- Non-Concert categories are invalid.
- `Zip Code` is stored as text.
- URL fields must be full `http` or `https` URLs when provided.
- `Main Image URL` must be a direct public image asset URL.
- Social-media page, post, or profile URLs are invalid for image fields.
- `Additional Image URL(s)` may contain multiple direct image URLs separated by
  `$`.

When an admin approves valid staged event rows, the app creates normalized
`events` rows with `category=Concert`, `record_type=event`, and
`source_type=file_upload`. Invalid, rejected, quarantined, high-risk, or blocked
rows are not approved.

## Private Visual Preview Sandbox

Log in at `/admin/login`, then open `/preview`.

The preview sandbox is private, admin-only, and read-only. It approximates app
surfaces for internal QA while the production Music Roadtrip app is still being
designed:

- `/preview` links to the preview surfaces.
- `/preview/events` shows a Music Events-style list with search area, latitude,
  longitude, radius, genre, and date filters.
- `/preview/events/{id}` shows an event profile preview.
- `/preview/events/{id}/reminder.ics` returns a local iCalendar reminder for the
  selected event.
- `/preview/venues` lists POI-style venue containers.
- `/preview/venues/{id}` shows a venue profile with nested events.
- `/preview/quality` summarizes missing images, ticket links, venue coordinates,
  Spotify URLs, suspicious tracking, venue profile gaps, and duplicate
  candidates.

Venue previews include a dark, mobile-style place filter panel inspired by the
provided filter drawer screenshot. It supports:

- Top-level place categories: `Music Site`, `Bars & Lounges`, `Cultural`,
  `Food & Bev`, `Shopping`, `Visitor & Travel`, and `Lodging`.
- Subcategory chips after a main category is selected.
- Category/subcategory filtering for venue profiles.
- Optional QA filters for certified placeholder, carousel tag, city, state, and
  quality issue.
- A `Show X places` button and `Reset filters` link.

Subcategories:

- `Music Site`: `Festivals`, `Recording Studios`, `Radio Stations`,
  `Music Education`, `Dance Clubs`, `Venues`
- `Cultural`: `Museums`, `Art`, `Memorials`, `Birthplaces`, `Theatres`,
  `Album Covers`, `Performing Arts Centers`
- `Food & Bev`: `Restaurants`, `Coffee Shops`
- `Shopping`: `Record Stores`, `Music Stores`, `Apparel & Merch Shops`
- `Visitor & Travel`: `Travel & Tourism`, `Chamber`
- `Lodging`: `Music Hotels`, `Music Camping`
- `Bars & Lounges`: no subcategories yet

The preview only lists normalized rows with `category=Concert` and
`record_type=event`. Venue profiles use `category=Music Site` and
`subcategory=Venues`, but the nested Concert records remain events and are not
converted into POIs.

`Concert` is intentionally not shown in the venue/place filter drawer because it
is an event category. The `/preview/events` page remains focused on event
filters such as search area, genre, date range, radius, and quality flags.

The visual treatment is inspired by the local mobile screenshots supplied for
this POC: dark app surfaces, large image-led profiles, compact date/time pills,
action tiles for Map/Nav/Street/Web/Tickets/Reminder, yellow Concert markers,
blue venue markers, and QA warning chips. These screenshots are design
references only; they are not data sources.

Image QA is intentionally passive. Normal page renders do not fetch arbitrary
image URLs for validation. The preview renders inline images only when the URL
looks like a direct image asset and otherwise shows the stored URL plus warning
chips for missing, social-media, or non-direct image URLs.

Ticket/link QA flags missing ticket links, malformed links, session/cart-like
ticket URLs, and legacy/vendor tracking parameters.
Links are not cleaned or rewritten in this milestone.

Spotify and SerpAPI integrations are placeholders only. The schema stores
Spotify preview fields and generic enrichment status/flags/suggestions, and the
event detail page displays those fields when present. No live Spotify or SerpAPI
requests are made by the preview sandbox.

## Submission Trust Gate

Public submissions never become live, crawlable, scheduled, or publishable by
themselves. New sources are stored as pending and must be approved by an admin.

Risk scoring returns:

- `low`: 0-19
- `medium`: 20-49
- `high`: 50-79
- `blocked`: 80+

The public form includes hidden anti-bot checks:

- Honeypot field filled by bots.
- Hidden form-render timestamp for unrealistically fast submissions.

The app also stores lightweight local rate-limit signals using hashed IP address
and hashed user agent when available, plus contact email and submitted domain.

Suspicious flags can include:

- Bot-like submission signals.
- Dangerous localhost/private-network URLs in production mode.
- Blocked submitter or domain.
- Duplicate calendar URL claims.
- Social-media profile URLs.
- Unknown or unsupported source type.
- Too many recent submissions or unrelated domains from the same submitter.

High-risk submissions are quarantined. Blocked submissions are blocked. Neither
state can be crawled from `/admin/sources`. Use `/admin/suspicious-submissions`
to approve, reject, quarantine, block email/domain, or trust submitter/domain.

Duplicate calendar URLs do not create a separate approved master source in this
POC. They are stored as additional claims and flagged for admin review.

Blocked submitters/domains are quarantined or blocked on later submissions.
Trusted submitters/domains receive a lower risk score, but they still must pass
URL validation, authorization checks, duplicate checks, and admin approval.

Development mode allows local demo URLs like:

```text
http://127.0.0.1:8000/dev/sample-calendar.ics
```

Production mode blocks localhost, `127.0.0.1`, private-network IP ranges, and
link-local IP ranges from public submissions. Public submitted URLs are never
crawled until an admin has approved them.

For a real deployment, put `/admin/*` behind SSO, VPN, or Cloudflare Access in
addition to this application-level login.

## App Feed Contract

The app feed is the read-only boundary between internal ingestion/review tables
and the Music Roadtrip app. Internal records may contain raw provider payloads,
source claims, duplicate candidates, image candidates, admin review state, crawl
logs, and import batches. App-feed routes expose only sanitized event, POI, and
venue records that have `publish_status` of `approved` or `published`.

Routes:

- `/admin/app-feed` is the private admin dashboard for app-feed counts, previews,
  exports, and latest JSON downloads.
- `/admin/app-feed/events.json`, `/admin/app-feed/pois.json`, and
  `/admin/app-feed/venues.json` return admin-only previews of the app contract.
- `/admin/app-feed/export` generates an `app_feed_exports` row and local JSON
  snapshot. The POST requires CSRF.
- `/api/app/events`, `/api/app/pois`, and `/api/app/venues` are private by
  default. Set `APP_FEED_PUBLIC=true` only when the deployment is intentionally
  exposing those JSON feeds.

Readiness scoring returns `publish_ready_score`, `publish_blockers_json`-style
flags in the JSON quality object, and app-safe image/ticket/source summaries.
Selected images pending approval may appear in the private feed, but they are
marked with `image.needs_approval=true`. Concert remains event-only and is
excluded from the POI feed. ZIP codes are serialized as text, latitude and
longitude are not swapped, and Music Roadtrip logo assets are suppressed as
event/venue/POI images.

See `docs/app-feed-contract.md` for full event, POI, and venue shapes, examples,
privacy notes, omitted internal fields, and the future versioning strategy.
