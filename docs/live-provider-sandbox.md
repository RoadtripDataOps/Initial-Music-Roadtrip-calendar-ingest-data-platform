# Live Provider Connector Sandbox

Milestone 4.7 adds controlled live provider fetch capability for JamBase and
CitySpark. It is admin-only, feature-flagged, credential-gated, and routed into
the existing API Feed Review Workbench.

The sandbox does not publish events, approve records, create POIs, bypass
dedupe/source claims, bypass image QA, bypass ticket QA, or expose raw provider
records through the app feed.

## Configuration

Live calls are off by default.

```bash
JAMBASE_LIVE_CALLS_ENABLED=false
JAMBASE_API_KEY=
JAMBASE_BASE_URL=https://api.data.jambase.com/v3
JAMBASE_DEFAULT_PER_PAGE=100
JAMBASE_SANDBOX_MAX_EVENTS=1000

CITYSPARK_LIVE_CALLS_ENABLED=false
CITYSPARK_API_KEY=
CITYSPARK_PORTAL_SCRIPT_ID=
CITYSPARK_BASE_URL=https://api.cityspark.com
CITYSPARK_DEFAULT_PAGE_SIZE=200
CITYSPARK_SANDBOX_MAX_EVENTS=1000
```

No credential value should ever be committed, rendered in templates, written to
docs, logged, exported, or shown in browser-visible code. Request previews show
`REDACTED`.

## Admin Routes

- `/admin/api-feeds/jambase/live-sandbox`
- `/admin/api-feeds/cityspark/live-sandbox`

Both routes require admin auth. POST actions require CSRF.

## JamBase Example

1. Set `JAMBASE_LIVE_CALLS_ENABLED=true`.
2. Set `JAMBASE_API_KEY` in local environment only.
3. Open `/admin/api-feeds/jambase/live-sandbox`.
4. Run a small request such as `limit=10`, `perPage=10`, `eventType=concerts`.
5. Review the resulting API feed run and pending records.

The sandbox only supports `GET /events` in this milestone. It does not call the
event detail endpoint.

## CitySpark Example

1. Set `CITYSPARK_LIVE_CALLS_ENABLED=true`.
2. Set `CITYSPARK_API_KEY` and `CITYSPARK_PORTAL_SCRIPT_ID` in local
   environment only.
3. Open `/admin/api-feeds/cityspark/live-sandbox`.
4. Run a small request such as `limit=10`, `pageSize=10`, `includeLabels=true`,
   and `includeInstances=true`.
5. Review the resulting API feed run and pending records.

The sandbox only supports `POST /v2/event/search` in this milestone. It does
not scrape CitySpark pages and does not call a details endpoint.

## Safety Model

- Live calls are disabled unless the provider flag is true.
- Required credentials and provider account IDs must be present.
- API keys and portal identifiers are redacted from request previews, run
  metadata, logs, errors, docs, and templates.
- JamBase `perPage` is capped at 100.
- CitySpark `pageSize` is capped at 200.
- Provider fetches are capped by provider sandbox max settings.
- Fetched rows become `api_feed_records` with `review_status=pending_review`.
- Records normalize to `category=Concert` and `record_type=event`.
- Approval uses the existing API Feed Review approval path and shared
  dedupe/source-claim upsert service.
- No provider event record becomes a POI.
- App feed exports only use approved/publishable normalized records.

## Review Flow

1. Open `/admin/api-feed-runs/{id}`.
2. Review raw count, normalized count, duplicate count, and redacted request
   metadata.
3. Open each `/admin/api-feed-records/{id}`.
4. Review mapper warnings, ticket-link classification, source-chain provenance,
   image candidates, venue match signals, and duplicate status.
5. Approve, hold, reject, or send to enrichment.

Approving a sandbox-created API feed record creates or updates a normalized
Concert event through the same path as manual JSON provider records.

## Troubleshooting

- `Live Calls Off`: set the provider live flag to `true` in local environment.
- `Credentials Missing`: set the provider API key, and for CitySpark set
  `CITYSPARK_PORTAL_SCRIPT_ID`.
- Provider error run: open the failed `api_feed_run` and inspect the redacted
  error and request preview.
- Empty run: reduce filters, date window, or location constraints.
- Unexpected duplicate status: inspect source IDs, source chain, event name,
  start time, venue, city, and state in the record detail page.

Automated tests use mocked HTTP clients only and must not make live provider
requests.
