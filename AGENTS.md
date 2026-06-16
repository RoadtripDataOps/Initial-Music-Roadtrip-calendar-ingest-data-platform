# AGENTS.md — Internal Event Calendar Harvester

## Mission

Build a compliant internal event calendar ingestion system for client-authorized calendar URLs. The system should let clients or internal staff submit calendar sources, crawl those sources on a configured cadence, extract event data, normalize it into a canonical schema, deduplicate it, and store it in a database with full provenance.

This project supports a two-track ingestion strategy: direct/owned calendar sources submitted by authorized clients and staff, plus licensed vendor/API feeds such as CitySpark and JamBase. Live provider calls remain off until credentials and configuration are added. It must **not** copy CitySpark's proprietary UI, documentation, API design, data, branding, or protected materials. Build around open standards, client-provided authorization, licensed provider review controls, and your own event model.

## Non-negotiable constraints

1. CitySpark is a paid licensed vendor API feed for Music Roadtrip, not a first-party source. Treat it like JamBase as a licensed provider feed: records still pass through API Feed Review, normalization, dedupe, source claims, ticket QA, image QA, and app-feed readiness before use. Live API calls remain off until credentials and configuration are added.
2. Do not scrape CitySpark, ticketing vendors, publishers, social platforms, or any third-party site in a way that violates their terms, authentication gates, robots.txt, rate limits, or access controls.
3. Do not bypass CAPTCHAs, bot defenses, paywalls, login walls, or hidden APIs.
4. Every event record must store source provenance: source URL, fetched URL, canonical event URL if known, crawl run ID, extractor version, raw hash, and timestamps.
5. Crawler tests must use local fixtures by default. Do not run uncontrolled live crawls in automated tests.
6. No secrets in the repository. Use `.env` locally and secret managers in production.
7. Keep the POC narrow: ingestion, normalization, dedupe, source admin, and a basic export/API. Monetization, ticketing, newsletters, and public event discovery are out of scope for the first build.
8. Do not propose or implement route-builder, itinerary, user-trip, saved-trip,
   consumer navigation, or mobile-app UI features unless explicitly requested.
   Prioritize calendar ingest, source scraping, API sandbox review, event photo
   quality, event normalization, dedupe, ticket QA, and POI audit.

## Target architecture for the first POC

Use a Python monorepo:

```text
app/
  main.py                  # FastAPI app
  api/                     # JSON API routes
  web/                     # Jinja/HTMX pages
  core/                    # config, logging, security
  db/                      # SQLAlchemy models, sessions, migrations hooks
  models/                  # Pydantic schemas
  services/                # business services
  extractors/              # source fetch + parse + normalize modules
  jobs/                    # scheduler and crawl jobs
tests/
  fixtures/                # saved HTML, JSON-LD, ICS, RSS, malformed examples
  unit/
  integration/
docs/
```

Recommended dependencies when implementation starts:

- `fastapi`, `uvicorn`, `jinja2`, `python-multipart`
- `sqlalchemy`, `alembic`, `psycopg`, `pydantic-settings`
- `httpx`, `beautifulsoup4`, `selectolax`, `extruct`, `w3lib`, `feedparser`, `icalendar`, `python-dateutil`, `dateparser`
- `apscheduler` for POC scheduling
- `playwright` behind an optional feature flag for dynamic pages
- `pytest`, `respx`, `pytest-asyncio`, `ruff`, `mypy`

## Initial commands Codex should create

After scaffolding, the repository should support:

```bash
make setup          # install dependencies and initialize local environment
make dev            # run FastAPI locally
make test           # run pytest
make lint           # run ruff and mypy
make db-up          # start local Postgres/Redis if Docker Compose is used
make db-migrate     # apply Alembic migrations
make seed-fixtures  # import sample calendar sources and test events
```

If using `uv`, prefer:

```bash
uv sync
uv run pytest
uv run ruff check .
uv run mypy app
uv run uvicorn app.main:app --reload
```

## Product requirements Codex must preserve

### User-facing source submission

Build a shareable route such as `/submit-calendar` with:

- Organization/venue/promoter name.
- Contact name and email.
- Calendar URL.
- Optional event category, geography, notes, and preferred crawl cadence.
- Explicit authorization checkbox: submitter confirms they control the calendar or are authorized to submit it for indexing.
- Confirmation screen and admin notification placeholder.

### Internal source admin

Build `/admin/sources` with:

- Pending/approved/paused/blocked statuses.
- Source details and crawl cadence.
- Last crawl status, last successful extraction count, error count.
- Manual “run crawl” action.
- Parser strategy selection: auto, JSON-LD, ICS, RSS/Atom, static HTML, Playwright, custom mapping.
- Notes and audit trail.

### Crawl and extraction pipeline

Implement stages as separate testable services:

1. Source validation.
2. robots.txt and policy check.
3. Fetch.
4. Document classification.
5. Structured extraction.
6. HTML fallback extraction.
7. Normalization into canonical events.
8. Dedupe/upsert.
9. Review queue for uncertain results.
10. Export/API.

### Data policy

Store raw documents only when source authorization allows it. Store hashes and extracted fields even when raw retention is disabled. Raw retention should be configurable per source.

## Extraction priority order

1. ICS/iCalendar feed when available.
2. JSON-LD `schema.org/Event` objects on event detail pages.
3. RSS/Atom feeds with event metadata.
4. Microdata/RDFa event markup.
5. HTML list/detail extraction using configurable selectors.
6. Playwright-rendered HTML only when static fetch cannot access event content and source policy allows it.
7. Manual CSV upload as fallback for clients who cannot provide scrapeable calendars.

## Canonical event model principles

- Separate `event_series` from `event_instance`.
- Keep recurrence rules if present, but expand a bounded future window for search/display.
- Store local and UTC timestamps, timezone, `all_day`, and `has_time` flags.
- Keep source text and normalized text separately.
- Keep venue and organizer normalized but source-linked.
- Preserve multiple source links per event.
- Do not collapse duplicates destructively; use dedupe clusters and survivorship rules.

## Crawler safety rules

Default per-domain behavior:

- Respect robots.txt.
- Use a truthful user-agent string with contact email configured by environment variable.
- Max 1 concurrent request per hostname during POC.
- Default delay between requests: 2 seconds plus jitter.
- Honor `Retry-After`.
- Back off on 429/403/5xx.
- Never follow infinite calendars indefinitely; cap crawl depth and URL count per run.
- Only crawl submitted/approved source domains and discovered event detail URLs under allowed scope.

## Testing expectations

Each extractor must have fixtures for:

- Valid JSON-LD Event.
- JSON-LD array and `@graph`.
- Multi-date event.
- Missing timezone.
- All-day event.
- ICS feed with UID/RRULE.
- RSS item with event-like title/date.
- Malformed HTML.
- Duplicate events from two sources.

Do not mark a milestone complete until tests pass and a short demo path is documented.

## Definition of done for the local POC

A boss demo is ready when:

1. A user can submit a source URL through a public form.
2. An admin can approve the source.
3. An admin can run a crawl locally.
4. The system extracts at least one fixture-based ICS source and one JSON-LD Event source.
5. Extracted events are stored in Postgres.
6. The admin can view normalized events, source provenance, crawl errors, and dedupe status.
7. A simple JSON export endpoint returns upcoming events.
8. Tests pass with no network dependency.

## Implementation style

- Prefer small, explicit functions.
- Do not introduce a heavy frontend framework unless specifically requested.
- Use typed Pydantic models at system boundaries.
- Use SQLAlchemy models for persistence.
- Keep extractor modules pure where possible: raw input in, structured candidate out.
- Add docstrings to public services and extractor interfaces.
- Log structured events for crawl runs and extraction failures.
- Fail closed on source-policy ambiguity.
