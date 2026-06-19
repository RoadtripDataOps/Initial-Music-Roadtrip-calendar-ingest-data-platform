# Calendar Source Research And City Crawl Shakedown

Milestone 5.5B adds an admin workflow for real city-by-city calendar collection
and controlled crawl testing. The goal is to let Scott gather calendar URLs,
dedupe them, safely preflight them, approve good sources into the master source
registry, and run a measured crawl without auto-publishing events or
auto-creating POIs.

## Purpose

This workflow supports Music Roadtrip source development for cities, tourism
boards, venues, festivals, chambers, publications, and internal research. It is
for source onboarding and QA, not live provider API testing.

It does not:

- make live JamBase or CitySpark API calls
- add API keys
- auto-publish events
- auto-create POIs
- bypass admin approval, CSRF, crawler safety, dedupe, ticket QA, image QA,
  source intelligence, event quality review, or POI candidate review
- add itinerary, route-builder, saved-trip, mobile app, or consumer navigation
  features

## Recommended First City Workflow

1. Open `/admin/source-research`.
2. Create a new research batch for a city or region.
3. Paste researched calendar URLs or upload the CSV/XLSX template.
4. Review dedupe status against the master source registry and the current
   batch.
5. Run preflight to safely check each URL.
6. Approve good research items into the master calendar source registry.
7. Run crawl for approved sources in the batch.
8. Review the shakedown report for crawl results, extraction outcomes, event
   quality issues, source intelligence, and POI candidates.

## Research Batches

`calendar_source_research_batches` stores each city or region collection effort.
Each batch tracks:

- batch name
- optional region
- city, state, and country
- research owner
- source goal count
- workflow status
- notes

Batch statuses move from draft to preflight, approval, crawl, report review, and
archive states. These statuses are operational signals only. They do not publish
data.

## Research Items

`calendar_source_research_items` stores each submitted URL in a batch. Items can
come from pasted URLs, CSV/XLSX uploads, tourism-board research, partner
submissions, venue lists, festival pages, chambers, publications, or internal
research.

Each item tracks:

- submitted URL and canonical URL
- suggested source name and organization
- source type
- city, state, and country
- contact email if available
- authorization status
- preflight status and response metadata
- dedupe status
- risk level and risk flags
- review status
- linked or created master calendar source

## Templates

Download templates from:

- `/templates/calendar-source-research-template.csv`
- `/templates/calendar-source-research-template.xlsx`

Template fields:

- Calendar URL
- Source Name
- Organization Name
- Source Type
- City
- State
- Country
- Contact Email
- Authorization Status
- Notes

## Dedupe Behavior

Every research URL is canonicalized before review. Canonicalization removes
common tracking parameters, lowercases scheme and domain, and removes safe
trailing slashes while preserving meaningful path and query values.

The dedupe pass checks:

1. exact canonical URL match against `master_calendar_sources`
2. duplicates already present in the same research batch
3. possible duplicates by domain and path similarity

Exact existing sources are linked to the master source. Duplicates do not create
new master rows.

## Preflight Behavior

Preflight uses the existing crawler safety controls before any crawl approval.
It records:

- HTTP status
- content type
- final URL after redirects
- success, warning, failure, or blocked status
- error message when available

Preflight blocks unsupported schemes, unsafe private or localhost URLs in
production, and URLs flagged by existing SSRF/crawler safety checks.

Preflight is not a crawl approval. It only helps Scott decide whether a source
is worth approving.

## Approval Behavior

Approving a research item creates or links a master calendar source. The new
master source keeps:

- source name and organization
- original and canonical URL
- source type
- city, state, and country
- research owner and notes
- risk metadata
- source scrape profile

Approval does not run a crawl automatically. Scott must explicitly click the
batch crawl action.

## Batch Crawl Behavior

The batch crawl action only crawls approved master sources linked to approved
research items. Existing crawl gates still apply:

- source status must be approved
- review status must be approved
- blocked, paused, quarantined, or pending sources are skipped
- crawler safety protections run on every fetch

Successful crawls update source intelligence, stage extracted event candidates
when review is needed, save normalized events only through the existing safe
flows, and create POI candidates for discovered venues or locations. They do
not auto-publish events or auto-create POIs.

## Shakedown Report

Each batch has a report page at:

`/admin/source-research/{id}/report`

The report summarizes:

- total researched URLs
- new sources
- existing sources
- possible duplicates
- rejected or blocked sources
- approved master registry sources
- approved sources crawled
- successful and failed crawls
- unsupported sources
- source health warnings
- events found, created, updated, and duplicated
- extracted event candidates pending review
- missing image and ticket issues
- missing venue and low music relevance issues
- not app-feed-ready events
- POI candidates created
- matched existing POIs
- possible POI duplicates
- event-venue-only candidates
- sources needing review
- extractor types and platforms detected
- zero-event drops and repeated failures

## Source Intelligence Connection

Every approved source can have a scrape profile. Batch crawls update the scrape
profile with content type, final URL, response hash, extractor type, platform
type, event yield, failures, and health status. This lets future crawls start
from remembered source intelligence instead of starting from scratch.

## Event Quality Connection

Events and event candidates from a city shakedown still pass through the event
quality workflow. Scott can review missing images, weak ticket links, duplicate
risk, source claims, music relevance, and app-feed readiness before anything is
used downstream.

## POI Candidate Connection

Venue and location data discovered during extraction is staged as
`poi_candidates`. It is matched against the existing POI registry and must be
approved, linked, marked event-venue-only, sent to research, or rejected by an
admin. Unapproved POI candidates are not exposed in app-feed POIs.

## Safety

This workflow is designed for controlled city crawl shakedowns:

- no live provider API calls by default
- no API keys in the repo
- no CitySpark scraping
- no ticketing or social-platform scraping
- no automatic event publishing
- no automatic POI creation
- no bypass of admin approval, CSRF, crawler safety, event dedupe, ticket QA,
  image QA, source intelligence, event quality review, POI candidate review, or
  app-feed privacy
