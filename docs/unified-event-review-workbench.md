# Unified Event Review Workbench

Milestone 5.6A adds `/admin/event-review`, an admin-only review workbench that
puts calendar-ingested events, licensed API feed records, extracted event
candidates, and staged event uploads into one scrollable table.

The page is a visibility and handoff layer. It does not make live provider
calls, call external geocoding/search APIs, expose API keys, auto-publish
events, auto-create POIs, or bypass existing review gates.

## Purpose

The workbench gives Scott one daily place to review the fields that usually
decide whether an event is ready for the next step:

- title, date, time, description, genre, and location
- event image status and image approval state
- ticket URL and ticket-link classification
- website or event URL
- source/provider provenance and source claim count
- duplicate status, POI candidate status, and app-feed readiness

It follows a CitySpark-style functional pattern without copying CitySpark
branding, protected UI, proprietary API design, or vendor materials.

## Record Types Included

The workbench currently includes:

- Normalized `Event` rows where `category=Concert` and `record_type=event`.
- API feed records from JamBase, CitySpark, manual JSON uploads, and future
  provider feeds.
- Extracted event candidates from approved crawls, including JSON-LD, RSS/Atom,
  static HTML event cards, generic HTML event-link discovery, and ICS-derived
  source context when present.
- Staged event-upload rows from import batches, read-only, linking back to the
  import batch review page.

Rejected, blocked, quarantined, archived, and expired records are hidden by
default unless the review-status filter explicitly asks for them.

## Filters

Top filters:

- Search text
- Date from and date to
- Location text
- Radius miles, latitude, and longitude
- City and state
- Genre
- Source type
- Provider/source
- Review status
- Image status
- Ticket status
- Venue/POI status
- Duplicate status
- App-feed readiness
- Quality issue

Radius filtering uses stored latitude/longitude when available. If a record has
no coordinates, the workbench falls back to the city/state filters already
entered by the admin. It does not call external geocoding services.

## Table Columns

The table shows:

- Actions
- Status
- Image thumbnail
- Event Title
- Start date/time
- Venue / Location
- Address
- Description
- Genre
- Ticket URL
- Website / Event URL
- Source
- Quality Flags

Rows show selected event images when available. If no safe event image exists,
the page shows `Missing Image`. If a selected image still needs review, it shows
`Selected · Needs Approval`. If a generic/provider image has been blocked, it
shows `Generic Image Blocked`. Music Roadtrip logo assets are never presented as
event images.

## Review Actions

The Actions column links into existing review routes:

- View detail
- View preview when a normalized event exists
- View app-feed JSON when a normalized event exists
- Run photo rescue through existing CSRF-protected event/API-feed routes
- View image candidates
- View source claims or provider lineage
- View duplicate group
- View POI candidates or venue match searches
- Approve, hold, or reject API feed records where the existing API feed review
  routes support those decisions
- Approve or reject extracted event candidates where the existing extracted
  candidate review routes support those decisions

All mutation actions require the existing admin CSRF token. The workbench does
not create new bypass routes.

## Admin Simplification

The sidebar now includes a `Daily Workbench` group with the common daily paths:

- Event Review
- Source Research
- POI Candidates
- API Feeds
- Jobs

Existing pages remain available in their original sections. This makes the
common review path visible without removing operational, source, feed, quality,
inventory, or handoff pages.

The dashboard also has an `Event Review Workbench` card with counts for:

- events needing images
- events needing ticket links
- pending API feed records
- pending extracted candidates
- events ready for app feed
- POI candidates from events

## Relation To Existing Workbenches

`/admin/event-review` is the broad daily review table. It combines visibility
across record types and links into the specific tools below.

`/admin/event-quality` remains the normalized-event QA workbench for deeper
event quality scoring, bulk photo rescue, duplicate-risk review, and app-feed
readiness calculations.

`/admin/api-feeds` remains the provider-specific review area for demo imports,
manual JSON upload, provider pipeline documentation, live sandbox controls, API
record details, and raw-to-normalized mapping review.

`/admin/extracted-events` remains the focused queue for extracted crawl
candidates before they become normalized events.

`/admin/image-candidates` remains the image QA board for candidate clearance,
selection, preflight metadata, and photo rescue.

`/admin/poi-candidates` remains the POI audit queue. Event review links there
for venue/POI match follow-up but does not auto-create POIs.

`/admin/app-feed` remains the app-safe export area. Event review can link to
app-feed JSON previews for normalized events but does not publish records.
