# Strategy: Internal Event Calendar Harvester

Prepared for: Music Roadtrip / internal event ingestion proof of concept  
Date: 2026-06-03

## Executive recommendation

Build an internal **event-source ingestion and normalization platform**, not a direct CitySpark clone. CitySpark remains a paid licensed vendor feed while Music Roadtrip builds a stronger owned ingestion network. The valuable internal asset is a repeatable pipeline that turns authorized calendar URLs, ICS feeds, RSS feeds, JSON-LD event pages, manually submitted calendars, and licensed provider feeds into a canonical Concert event database.

The POC should prove four things:

1. A client or team member can submit a calendar source link.
2. Your team can approve/configure that source.
3. The crawler can run on a schedule and extract event candidates.
4. The system can normalize, dedupe, store, and export event data with provenance.

## Why not clone CitySpark directly

CitySpark publicly positions itself as an event platform for publishers with portals/widgets, auto-populated listings, editorial control, monetization, reverse publishing, private-label ticketing, and support. Music Roadtrip handles CitySpark as a paid licensed vendor/API provider behind credentials, provenance, QA, and private review workflows, the same way JamBase is handled as a licensed provider feed. Live API calls remain off until credentials and configuration are added. The owned-source system is being built alongside CitySpark to reduce dependency on any single vendor, not to pretend the licensed feed is irrelevant.

## Target POC scope

### In scope

- Calendar URL submission form.
- Internal source admin.
- Source authorization status.
- Daily/weekly scheduled crawl configuration.
- Fetch, parse, normalize, store.
- Extractors for ICS, JSON-LD Event, RSS/Atom, and simple HTML.
- Provenance and raw-document hash storage.
- Basic dedupe.
- Admin review queue.
- JSON export endpoint for your app or demos.

### Out of scope for POC

- Public discovery marketplace.
- Paid event promotion.
- Ticketing checkout.
- Newsletter production.
- Print/reverse publishing.
- Voice skills.
- Complex role-based enterprise permissions.
- Large-scale distributed crawling.

## Functional architecture

The platform has two input tracks.

Track A: Direct/owned source network

- Public calendar URL submissions.
- Calendar-source CSV/XLSX uploads.
- Concert-event CSV/XLSX uploads.
- Approved partner feeds.
- Tourism board submissions.
- Scheduled crawls of approved master calendar sources.

Track B: Licensed/vendor API feeds

- CitySpark.
- JamBase.
- Future approved APIs.
- Manual provider JSON review.
- Provider-specific mappers.
- Provider provenance.
- Compliance controls.
- API Feed Review Workbench.

Both tracks normalize into `category=Concert`, `record_type=event`, normalized
events, venue profile linkage, dedupe/upsert, image QA, ticket-link QA, preview
sandbox, and future app/map feed.

```text
Direct source submissions + licensed provider feeds
        ↓
Source/provider registry and approval
        ↓
Crawler scheduler / API Feed Review Workbench
        ↓
Fetch layer with robots/rate-limit policy
        ↓
Document classifier
        ↓
Extractors: ICS → JSON-LD → RSS/Atom → Microdata → HTML selectors → Playwright fallback
        ↓
Canonical normalization
        ↓
Dedupe and quality scoring
        ↓
Postgres event database
        ↓
Admin review + JSON API/export
```

## Recommended implementation sequence

### Phase 0 — Repository and guardrails

Create the repo with `AGENTS.md`, the docs in this pack, local config, linting, tests, Docker Compose, and a tiny FastAPI health check. Add fixtures before crawler code so Codex can validate extraction without live websites.

### Phase 1 — Source submission and admin registry

Build the client-facing source submission form and admin source table. Use statuses: `pending`, `approved`, `paused`, `blocked`, `needs_review`. Do not let scheduled jobs run on unapproved sources.

### Phase 2 — Extractor-first ingestion

Implement extraction in this order:

1. ICS feed parser.
2. JSON-LD `schema.org/Event` parser.
3. RSS/Atom parser.
4. HTML detail-page fallback.
5. HTML list-page discovery.
6. Playwright fallback.

### Phase 3 — Canonical model and upsert

Implement tables for organizations, source calendars, crawl runs, fetched documents, extraction candidates, event series, event instances, venues, organizers, source links, and dedupe clusters.

### Phase 4 — Admin review and demo export

Build admin pages for source status, crawl logs, raw/extracted comparison, normalized event list, and manual approve/reject/merge actions. Add `GET /api/events/upcoming` for demo integration.

### Phase 5 — Scale-up hardening

Move scheduling and workers out of the web process, add queues, per-domain concurrency, observability, alerting, audit logs, and production secret management.

## Data-source strategy

Prioritize sources with explicit permission and stable machine-readable formats.

| Priority | Source type | Reliability | Notes |
|---:|---|---:|---|
| 1 | Client-provided ICS feed | High | Best for recurrence, updates, UID tracking. |
| 2 | Client event pages with JSON-LD Event | High | Good semantic extraction; often SEO-supported. |
| 3 | Client RSS/Atom event feeds | Medium | Good for update discovery; date fields may be incomplete. |
| 4 | Static HTML calendars with detail pages | Medium | Requires source-specific selectors and regression tests. |
| 5 | Dynamic JS calendars | Low/Medium | Use Playwright only after approval; higher fragility/cost. |
| 6 | Manual CSV upload | High manual | Best fallback for valuable clients with poor websites. |

## Canonical event object

Minimum normalized event fields:

- `title`
- `description_text`
- `description_html`
- `start_at_local`
- `end_at_local`
- `timezone`
- `start_at_utc`
- `end_at_utc`
- `all_day`
- `has_time`
- `venue_name`
- `venue_address`
- `city`
- `region`
- `country`
- `latitude`
- `longitude`
- `organizer_name`
- `event_url`
- `ticket_url`
- `image_url`
- `price_min`
- `price_max`
- `is_free`
- `category`
- `source_id`
- `source_event_uid`
- `source_last_modified`
- `raw_hash`
- `normalization_version`
- `dedupe_cluster_id`

## Dedupe strategy

Use layered dedupe rather than one fuzzy guess.

1. **Source identity:** source ID + source UID, ICS UID, canonical event URL, or provider event ID.
2. **Strong event hash:** normalized title + normalized venue/address + start timestamp.
3. **Candidate similarity:** title similarity, venue match/geohash, start time window, performer names, and canonical URL domain.
4. **Manual review:** uncertain matches go to review queue.
5. **Non-destructive merge:** keep all source records and choose display fields via survivorship rules.

## Compliance posture

Use an authorization-first source policy:

- A client-submitted source must include an authorization checkbox.
- Admins must approve sources before crawling.
- The crawler must respect robots.txt and source terms.
- The crawler must identify itself with a configured contact email.
- Avoid scraping login-only/private areas unless a separate written data-access agreement exists.
- Preserve attribution and source links.
- Keep raw data retention configurable and limited.

## Boss-demo narrative

The demo should show:

The demo shows how Music Roadtrip can accept direct calendar submissions while
still reviewing licensed API feeds like CitySpark and JamBase. The goal is to
normalize everything into one clean Concert event pipeline, dedupe overlapping
records, improve images/ticket links, and preview how events will look in the
app.

1. “Here is a link we can send clients.”
2. “The client submits their calendar URL and authorizes indexing.”
3. “Our admin sees it as pending and approves it.”
4. “We run the crawler.”
5. “The API Feed Review Workbench can review licensed provider records.”
6. “The normalized event records are now in our DB with source traceability.”
7. “Our app can call `/api/events/upcoming` and consume clean data.”

## Success criteria

The POC is credible when it can ingest at least three source types — ICS, JSON-LD Event, and simple HTML — and can prove that every event has provenance, normalized date/time semantics, duplicate handling, and an export path.
