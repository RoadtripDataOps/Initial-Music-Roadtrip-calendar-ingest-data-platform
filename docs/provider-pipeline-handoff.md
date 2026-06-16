# Provider Pipeline Handoff

The Provider Pipeline pages are private developer handoff views for the Music
Roadtrip API Feed Review Workbench. They explain how provider-style records are
expected to move from a future or manual provider payload into normalized,
reviewable Concert event candidates.

These pages do not make live API calls, do not expose credential values, and do
not enable a provider integration by themselves. The separate Live Sandbox
forms for JamBase and CitySpark are admin-only, feature-flagged, and
credential-gated.

## Private Routes

All routes require an authenticated admin session:

- `/admin/api-feeds/{provider}/pipeline`
- `/admin/api-feeds/{provider}/mapping`
- `/admin/api-feeds/{provider}/live-sandbox` for JamBase and CitySpark only
- `/admin/api-feeds/{provider}/pipeline.md`
- `/admin/api-feeds/{provider}/pipeline.json`
- `/admin/api-feed-records/{id}/lineage`

Supported provider pages:

- `jambase`
- `cityspark`
- `manual_json`
- `spotify`
- `serpapi`

## API Feed Review vs Provider Pipeline

API Feed Review is where admins inspect actual staged provider records,
normalized candidates, source-chain provenance, ticket QA, image QA, and review
decisions.

Provider Pipeline is the developer handoff layer. It shows request previews,
mapping tables, cleanup rules, QA rules, code references, synthetic raw
examples, normalized examples, and Markdown/JSON exports for implementation
planning.

Workbench visibility and live API state are separate:

- `Workbench Open` means the private review/demo UI is available.
- `Live Calls Off` means no provider request is made.
- `Live Calls On` means an admin-only live sandbox request can run when
  credentials are configured.
- `Credentials Missing` means credentials or required provider account IDs are
  absent.
- `Credentials Configured` means the local environment has the required values;
  the values are never shown.
- `Licensed Vendor Feed`, `Permanent Allowed`, and `Enrichment Suggestions Only`
  describe provider role and storage policy.

## Provider Request Previews

Request previews show method, base URL, endpoint, required env var names,
example headers, query/body shape, pagination notes, rate-limit notes, and
redaction behavior.

Credential values are always shown as `REDACTED`. Env var names may be shown so
developers know what future configuration would require.

Live Sandbox request previews also store redacted metadata on `api_feed_runs`.
Fetched records remain pending API Feed Review records until an admin approves
them through the normal review, dedupe, source-claim, ticket QA, and image QA
workflow.

JamBase example:

```http
GET https://api.data.jambase.com/v3/events?apikey=REDACTED&page=1&perPage=100&eventType=concerts
Accept: application/json
```

JamBase API v3.1.0 is the current request-shape reference. It uses
`https://api.data.jambase.com/v3`, OpenAPI 3.1.0, and `apikey` query auth.
Older v1 examples are legacy references only. The v3.1.0 schema uses plural
`eventType` enum values `concerts` and `festivals`; singular examples in older
docs should be treated as documentation/example discrepancies.

CitySpark example:

```http
POST https://api.cityspark.com/v2/event/search
```

CitySpark is a paid licensed vendor API feed handled like JamBase. It belongs
behind provider-specific credentials, provenance, QA, and admin review. Public
users should not submit CitySpark-exported data as their own source, and the app
must not scrape CitySpark pages.

## Raw To Normalized Shape

Each pipeline page includes a synthetic raw provider JSON example and a
normalized Music Roadtrip candidate JSON example.

Normalized provider candidates should use:

- `category=Concert`
- `record_type=event`
- `source_type=api_feed`
- event name, headliner, timing, timezone, venue, city/state/country
- event URL and ticket candidate fields
- provider event type and genre signals
- `ingestion_provider`, `upstream_event_source`, `ticketing_provider`
- `source_chain_json`, `external_identifiers_json`, `ticket_offers_json`
- image candidate status
- ticket-link classification
- quality flags

Concert is always an event category. Concert records must never be converted
into POIs. Venue profiles are POI-style containers that can display nested
Concert events through venue linkage.

## Mapping And Cleanup Rules

Mapping tables list provider fields, normalized fields, transformation rules,
required/optional status, QA notes, and example values.

Current mapping coverage includes:

- JamBase event, artist, venue, offer, image, and external identifier fields.
- JamBase v3.1.0 Events, Streams, Artists, Venues, Geographies, Lookups, and
  Genres endpoint metadata.
- CitySpark event, instance, location, image, category, ticket URL, and
  provider update fields.
- Manual JSON accepted shapes: list, `events`, `event`, `data`, and `results`.
- Spotify enrichment-only artist/image/URL candidate fields.
- SerpAPI enrichment-only image/link/search suggestion fields.

Cleanup rules cover category normalization, blank optional fields, source ID
preservation, dedupe inputs, and unknown upstream-source flags.

## Ticket-Link QA

Provider ticket links are candidates until classified.

JamBase:

- Prefer `offers[].url` where `category=ticketingLinkPrimary`.
- Fall back to `ticketingLinkSecondary`.
- Preserve seller ID/name as `ticketing_provider`.
- Preserve all offers in `ticket_offers_json`.
- Flag tracking or generic platform links for review.

CitySpark:

- Prefer `ticketUrl`.
- Treat `links[].linkUrl` and generic `url` as supporting links unless ticket
  QA validates them as event-specific.
- Flag tracking and affiliate links for repair/review.

General:

- Keep direct event pages and clear ticket handoffs.
- Keep event-specific platform pages when the pattern is clear.
- Flag generic app pages, platform homepages, artist pages, checkout-external
  URLs, tracking URLs, and unresolved links.

## Image QA

Provider images become image candidates only.

Pipeline:

```text
provider image URL
-> image_candidate
-> direct asset checks
-> stock/placeholder checks
-> poster/flyer/text/watermark flags
-> ranking
-> selected if best eligible
-> Selected - Needs Approval when clearance is unresolved
```

Music Roadtrip logo assets are UI branding only. They must not be used as event
images, venue images, POI images, fallback images, selected main images, or
image QA candidates.

## Record Lineage

`/admin/api-feed-records/{id}/lineage` shows one real staged provider record's
path through the system:

- provider and feed run
- raw payload
- mapper output
- normalization warnings and QA flags
- provider/source IDs
- source-chain provenance
- ticket-link classification and repair strategy
- image candidates created
- venue match and dedupe inputs
- review status
- created normalized event and preview link when approved

Use lineage pages when debugging how a provider field became a normalized
Concert event field, why a ticket link was flagged, or why an image candidate
needs approval.

## Developer Workflow

1. Open `/admin/api-feeds`.
2. Choose a provider and click `Pipeline`.
3. Review the request preview, mapping table, cleanup rules, ticket QA, image
   QA, and synthetic raw-to-normalized examples.
4. Download `pipeline.md` or `pipeline.json` for implementation handoff.
5. Upload synthetic/manual JSON or run a local demo import.
6. Open an API feed record and then `Lineage`.
7. Compare raw payload, mapper output, QA flags, provenance, and approved event
   output before changing mapper logic.

No provider pipeline page should be treated as permission to make live API
calls. Live mode requires explicit credentials, configuration review, rate
limits, provenance, and approval gates.
