# Source Extraction Policy

Milestone 4.9 adds safe extraction from approved crawl results beyond
ICS/iCalendar. The extractors convert fetched source content into staged event
candidates for admin review. They do not publish events and they do not create
normalized events directly.

## Architecture

`app/services/source_extraction_service.py` selects an extractor from the crawl
URL, content type, response body hints, source type, and any future explicit
admin override.

Supported extractor types:

- `ics`
- `json_ld_event`
- `rss_atom`
- `html_event_list`
- `generic_html_links`
- `unsupported`

All extractors return an `ExtractionResult` with status, event candidates,
warnings, errors, discovered links, and summary metadata. Successful crawls
store extraction metadata on `crawl_runs`:

- extractor type
- extraction status
- staged candidate count
- unsupported reason
- warnings/errors
- discovered link count

Non-ICS event candidates are stored in `source_extracted_event_candidates` with
raw fragment JSON, normalized payload preview, validation status, quality flags,
and source-claim preview. Admin approval later sends valid candidates through
the existing event dedupe/upsert, source-claim, ticket QA, image QA, and photo
rescue services.

## JSON-LD Event Rules

The JSON-LD extractor reads `<script type="application/ld+json">` blocks from
the fetched page. It supports single objects, arrays, and `@graph` objects.

Accepted event types:

- `Event`
- `MusicEvent`
- `Festival`
- `Concert`

Non-event JSON-LD objects are ignored. Extracted fields include name,
start/end date, status, description, URL, image URLs, location/address/geo,
offers, performers, and organizer details.

Rules:

- Candidates normalize to `category=Concert` and `record_type=event`.
- Images become image candidates only; they are never final images at
  extraction time.
- Ticket URLs pass through the shared ticket-link classifier.
- Source URL, crawl run, and source-chain provenance are preserved.
- Partial candidates are staged for review instead of silently discarded.

## RSS/Atom Rules

The RSS/Atom extractor parses RSS and Atom feeds when the content type or body
looks like a feed. It maps items to candidate events only when title,
description, or summary text provides event-like date evidence.

Rules:

- Item links are preserved as event URLs.
- Description/summary text is preserved as candidate description.
- Published dates are evidence only, not event dates, unless the item clearly
  presents them as the event date.
- Items without a reliable event date are staged as invalid or needs review.
- RSS extraction is intentionally conservative.

## Static HTML Rules

The HTML extractor parses static HTML only. It does not execute JavaScript and
does not use browser automation.

It looks for repeated event-like cards and common event vocabulary in tags,
classes, IDs, links, and visible text. It can extract:

- title
- date/time
- event URL
- venue text when visible
- ticket URL when visible
- direct image asset URLs

Rules:

- Do not hallucinate missing dates or venues.
- Do not create event candidates without an event date.
- A title/date candidate with missing venue can be staged for review.
- Social page, post, profile, or generic web URLs are not accepted as image
  assets.
- No recursive crawling is performed in this milestone.

## Discovered Links

If a static page does not contain extractable dated event cards, the system may
record likely event detail links as discovered links:

- discovered URL
- anchor text
- confidence
- reason
- source URL

Discovered links are shown on crawl-run detail pages as possible future work.
They are not crawled automatically and do not create events.

## Review And Approval

Admins review extracted candidates at:

- `/admin/crawl-runs/{id}`
- `/admin/extracted-events`
- `/admin/extracted-events/{id}`

Approval requirements:

- Admin authentication.
- CSRF token for every mutation.
- Candidate must be valid.
- Candidate approval uses the shared normalized event upsert path.
- Source claims preserve crawl run, source URL, source chain, raw payload, and
  normalized payload.
- Ticket-link QA runs before normalized event fields are saved.
- Extracted images become image candidates and then pass through image QA/photo
  rescue.
- Repeated approval of the same candidate does not create duplicate events.

Rejected or duplicate-review candidates remain staged and are not published.

## Safety Limits

Milestone 4.9 does not:

- scrape CitySpark pages
- make live provider API calls
- add or require API keys
- bypass public submission risk scoring
- bypass master-source or crawl approval gates
- bypass event dedupe/source claims
- bypass ticket-link QA
- bypass image QA/photo rescue
- execute JavaScript
- run browser automation
- recursively crawl discovered links
- auto-publish extracted events
- use Music Roadtrip logo assets as event, venue, POI, fallback, or QA images

CitySpark remains a licensed vendor/API feed handled through the private API
Feed Review Workbench when credentials and contract configuration allow it.
Public users must not submit CitySpark-exported data manually, and this
source-extraction layer must not scrape CitySpark pages.

Concert records remain backend `category=Concert`, `record_type=event`, and
must never be treated as POIs. Venue and POI records remain separate containers
that may display nested Concert events through venue linkage.

## Future Browser-Rendered Extraction

Some approved sources may require browser-rendered extraction in the future.
That should be added as a separate, explicit milestone with:

- per-source policy review
- robots and terms checks
- strict domain scope limits
- rate limits and backoff
- browser automation feature flag
- fixture-first tests
- no CAPTCHA, login-wall, paywall, or access-control bypass

Until that milestone exists, extraction is static-content only.
