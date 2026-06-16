# Event Dedupe And Source Claims

Milestone 4.5 adds a source-claim model around normalized Concert events. Every
inbound event assertion from ICS crawls, concert-event file uploads, and API feed
review can create an `event_source_claims` row before it updates or creates a
normalized event.

## Identity Strategy

- Strong match: same provider/source identifier, such as JamBase v3.1.0
  `identifier`, ICS `UID`, or a file upload `Source Event ID`.
- Medium match: normalized title or headliner, start datetime, venue, and ticket
  URL line up.
- Weak match: normalized title and start datetime line up but venue/source
  signals are incomplete or conflicting.

Weak or conflicting matches become duplicate review candidates instead of being
silently merged.

## Source Claims

Source claims preserve:

- source type and ingestion provider
- upstream provider/source IDs
- source URL and source name
- crawl, import batch, or API feed provenance
- raw payload, normalized payload, source-chain JSON, ticket offers, and
  external identifiers
- claim dedupe key, match confidence, and match reason

Approved events maintain `source_claim_count`, `latest_source_claim_id`,
`first_seen_at`, `last_seen_at`, and update summary fields.

## JamBase v3.1.0

JamBase API v3.1.0 `identifier` is the strongest event source-claim identifier.
JamBase Concert and Festival objects both normalize to `category=Concert` and
`record_type=event`, while preserving `provider_event_type`, source-chain data,
ticket offers, and external identifiers.

JamBase `startDate`, `endDate`, `previousStartDate`, and `doorTime` are
venue-local values without offset. Use `location.address.x-timezone` when UTC
conversion is needed.

No live JamBase calls are made in this POC. The provider pipeline and docs use
`apikey=REDACTED` request previews only.

## Admin Review

Duplicate candidates appear in `/admin/duplicate-events`. Admins can merge into
a canonical event, keep records separate, or mark candidates as not duplicates.

Concert records remain events and must never become POIs. Venue profiles are
separate POI-style containers that can display nested Concert events through
venue linkage.
