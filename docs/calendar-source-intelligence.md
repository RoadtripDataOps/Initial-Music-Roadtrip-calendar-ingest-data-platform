# Calendar Source Intelligence

Milestone 5.5A adds a scrape-profile layer for approved calendar sources.
The goal is to remember how each source was successfully crawled and extracted
so future runs do not start from zero.

## Scope

This layer supports Scott's ingest/data-quality workflow:

- approved master calendar sources
- crawl runs
- extractor selection
- event yield and source health
- developer notes for future scraper work
- monthly source registry snapshots

It does not enable live provider API calls, auto-publishing, mobile app work,
itinerary building, or any bypass of crawl gates and QA checks.

## Master Source Registry

`master_calendar_sources` remains the approved-source registry. Public
submissions and calendar-source uploads still dedupe into that registry and
must pass review before becoming crawlable.

Each master source can have one `source_scrape_profiles` record. The profile
stores the remembered scrape recipe and source health, including:

- platform type such as `ics`, `json_ld`, `rss_atom`, `static_html`,
  `the_events_calendar`, or `unsupported`
- extractor type such as `ics`, `json_ld_event`, `rss_atom`,
  `html_event_list`, or `generic_html_links`
- extractor confidence
- final URL, content type, and response hash from the latest crawl
- total, successful, and failed crawl counts
- average and latest event yield
- duplicate, missing-ticket, missing-image, and POI-candidate rates
- developer/admin notes
- recipe lock state

## Crawl Run Integration

After each crawl, the app updates the related source scrape profile. Successful
crawls update the last working extractor and metrics. Failed crawls update
failure counts and source health.

If a source previously produced events and then a successful crawl produces
zero events, the source is marked `watch` or `needs_review` and a developer
note is added. Repeated failures are marked `failing`. Unsupported formats are
marked `unsupported`.

## Source Health

Health states are operational, not publishing states:

- `healthy`: recent crawl/extraction behavior looks normal
- `watch`: the source may need attention
- `needs_review`: quality or scrape signals are risky
- `failing`: repeated crawl failures
- `paused`: source is paused by admin
- `unsupported`: no supported extractor currently matches the source

Source health does not publish data by itself. Events still pass through
normalization, dedupe, source claims, image QA, ticket QA, POI candidate review,
and app-feed readiness.

## Reusing Known Scrape Methods

The profile records the last working extractor and selector/link hints. Future
scraper work can use this as a starting point, especially for static HTML and
event-list pages. If an admin locks a recipe, automatic updates do not overwrite
extractor/platform hints, but crawl performance metrics still update.

## Developer Notes

Developer notes are stored on the scrape profile. Use them for concise scraper
handoff notes such as:

- why a source needs review
- whether JavaScript appears required
- whether pagination or detail-link discovery is supported
- selector hints for title/date/venue/ticket/image fields
- source-specific caveats

## Monthly Approved-Source Export

The `source_registry_snapshot_export` background job writes:

- `data/generated/source_registry/current_approved_calendar_sources.json`
- `data/generated/source_registry/current_source_scrape_profiles.json`

These files are local generated artifacts and are ignored by git through the
repo's `data/` ignore rule.

The monthly scheduled task key is:

`monthly_source_registry_snapshot`

The export is intended for internal review, source coverage planning, and
developer handoff. It is not a public app feed.

## Safety

Approved sources still require crawler safety on every run:

- no live provider calls by default
- no API keys in the repo
- no auto-publishing
- no bypass of approval, CSRF, dedupe, image QA, ticket QA, POI candidate review,
  or app-feed privacy
- no CitySpark scraping
- no social-platform scraping
