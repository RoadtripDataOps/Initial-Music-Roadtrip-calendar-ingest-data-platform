# Provider Mapping Reference

Milestone 3.9A uses the local files in `docs/` as schema and QA references.
No live provider calls are made unless credentials and config explicitly enable
them. CitySpark is treated as a paid licensed vendor API feed for Music
Roadtrip, handled through provider-specific compliance, retention, provenance,
and review controls. Public users must not submit CitySpark-exported data
manually, and the app must not scrape CitySpark pages.

## JamBase Event Feed Mapping

Reference files:

- `docs/provider-research/jambase/v3.1.0/jambase-api-v3.1.0-openapi.yaml`
- `docs/provider-research/jambase/v3.1.0/jambase-api-v3.1.0-openapi.json`
- `docs/provider-research/jambase/v3.1.0/jambase-api-v3.1.0-postman.json`
- `docs/provider-research/jambase/jambase-v3.1.0-summary.md`

API shape:

- API version: v3.1.0.
- OpenAPI version: 3.1.0.
- API title: JamBase Concert Data API.
- Base URL: `https://api.data.jambase.com/v3`.
- Authentication uses the `apikey` query parameter.
- Request previews use `apikey=REDACTED`; no live calls are made by this POC.
- The older `https://www.jambase.com/jb-api/v1` reference is legacy only when
  v3.1.0 differs.
- Key endpoints include `/events`, `/events/id/{eventDataSource}:{eventId}`,
  `/streams`, `/streams/id/{streamDataSource}:{streamId}`, `/artists`,
  `/artists/id/{artistDataSource}:{artistId}`, `/venues`,
  `/venues/id/{venueDataSource}:{venueId}`, geographies, lookups, and
  `/genres`.
- Pagination supports `page` and `perPage`; `page` defaults to 1, `perPage`
  defaults to 40 and maxes at 100.
- The v3.1.0 `eventType` enum is plural: `concerts` and `festivals`. Older
  singular examples are treated as documentation/example discrepancies.

Supported payload shapes:

- Object with an `events` array.
- A single event object.
- Event detail object with an `event` object.
- A list of event objects.

Mapping rules:

| Provider field | Music Roadtrip field |
| --- | --- |
| `identifier` | `source_record_id`, `provider_event_id`, strong dedupe input |
| `@type` or `type` | `provider_event_type` |
| `name` or `x-customTitle` | `event_name` |
| `x-subtitle` | Description supplement |
| `startDate`, `endDate`, `previousStartDate`, `doorTime` | Venue-local start, end, previous start, doors time |
| `eventStatus` | `event_lifecycle_status` |
| `eventAttendanceMode` | Attendance mode |
| `isAccessibleForFree` | Free/price metadata |
| `deletionStatus`, `deletedAt`, `mergedInto` | Deletion/merge metadata |
| `x-streamIds` | Related stream IDs |
| `url` | Event URL and source URL |
| `image`, `x-promoImage` | Main image candidate |
| `location.identifier` | Provider venue ID |
| `location.name` | Venue name |
| `location.url`, `location.image` | Venue matching/source metadata |
| `location.geo.latitude`, `location.geo.longitude` | Venue coordinates |
| `location.address.*`, `location.address.x-timezone` | Venue address, city, state, zip, country, timezone |
| `location.sameAs`, `location.x-externalIdentifiers` | Venue links and upstream venue IDs |
| `location.x-isPermanentlyClosed`, `location.x-numUpcomingEvents` | Venue status/freshness metadata |
| `performer[]` | Headliner, supporting artists, genres, lineup order, Spotify/social candidates, artist registry claims |
| `performer[].x-performanceDate`, `performer[].x-dateIsConfirmed` | Festival lineup timing metadata |
| `performer[].x-bandOrMusician` | Artist type |
| `performer[].image` | High-priority artist image candidate for photo rescue |
| `performer[].sameAs`, `performer[].x-externalIdentifiers` | Artist source claims, Spotify candidates, external IDs |
| `sameAs`, external identifiers | Source-chain and external identifier provenance |
| `offers[]`, `offers[].seller`, `offers[].validFrom` | Ticket candidates, provider, price text, sale metadata |

JamBase records normalize to `category=Concert` and `record_type=event`.
Festival records also normalize as Concert events, while preserving
`provider_event_type=Festival`. Festival records must not become POIs.

Time rule:

- `startDate`, `endDate`, `previousStartDate`, and `doorTime` are venue-local
  values without offset in v3.1.0. Use `location.address.x-timezone` when UTC
  conversion is needed.

Ticket strategy:

1. Prefer `offers[].url` where `category=ticketingLinkPrimary`.
2. Fall back to `ticketingLinkSecondary`.
3. Classify the chosen URL with the shared ticket-link classifier.
4. Preserve all offers in `ticket_offers_json`.

Source taxonomy:

- Event data sources: `axs`, `dice`, `etix`, `eventbrite`, `eventim-de`,
  `jambase`, `seated`, `see-tickets`, `see-tickets-uk`, `sofar-sounds`,
  `seatgeek`, `suitehop`, `ticketmaster`, `tixr`, `viagogo`.
- Artist data sources: `axs`, `dice`, `etix`, `eventbrite`, `eventim-de`,
  `jambase`, `seated`, `seatgeek`, `spotify`, `ticketmaster`, `viagogo`,
  `musicbrainz`.
- Venue data sources: `axs`, `dice`, `etix`, `eventbrite`, `eventim-de`,
  `jambase`, `seated`, `seatgeek`, `suitehop`, `ticketmaster`, `viagogo`.
- Stream data sources: `jambase`.

These values are taxonomy/provenance references only; they do not create direct
integrations for every provider.

## CitySpark Licensed Vendor Mapping

Reference file:

- `docs/CitySpark_v1.json`

CitySpark is a paid licensed vendor API feed for Music Roadtrip. It is handled
like JamBase as a licensed provider feed. Live calls remain off until
credentials and configuration are added.

API shape:

- API usage requires an API key and CitySpark account.
- Key event paths include `/v2/event/search`, `/v2/event/details`, and
  `/v2/event/categories`.

EventSeries mapping:

| Provider field | Music Roadtrip field |
| --- | --- |
| `eventId` | `source_record_id`, `provider_event_id`, strong dedupe input |
| `name` | Event name and fallback headliner |
| `description`, `summary` | Description |
| `primaryImage.largeImageUrl`, then medium, then small | Main image candidate |
| `labels`, `categories` | Provider label/category metadata |
| `location.locationName` | Venue name |
| `location.address`, `city`, `state`, `country` | Venue address fields |
| `location.latitude`, `location.longitude` | Venue coordinates |
| `instances[0].start/end`, then `start/end` | Start/end datetime |
| `hasTime`, `allDay` | Date/time flags |
| `price` | Price text/range |
| `ticketUrl` | Preferred ticket URL |
| `url` | Event/source URL |
| `links[]` | Supporting links only unless independently validated |
| `contact` | Source/contact metadata |

Synthetic CitySpark-like fixtures may be used for mapper tests; licensed
CitySpark records should enter only through the private provider workbench with
provenance and normal admin approval controls.

## Ticket Link Repair And QA Rules

Reference file:

- `docs/ticket_link_summary.md`

Classifier categories:

- `direct`
- `redirect_or_handoff`
- `platform_event`
- `platform_generic_or_app`
- `non_ticket`
- `blank`
- `suspicious`
- `unresolved`

Accepted:

- Direct ticket pages.
- Redirect/handoff URLs only when they clearly point to a ticket destination.
- Event-specific platform pages.

Rejected or flagged:

- Eventbrite `/checkout-external`.
- Generic DICE app/handoff links such as `link.dice.fm`.
- Ticketmaster homepage, artist, browse, discover, or generic music pages.
- Generic/app platform pages.
- Session/cart-like URLs.
- Tracking parameters including `utm_*`, `fbclid`, `gclid`, and
  `aff=cityspark`.

Repair targets:

- JamBase: `offers[].url`, primary then secondary.
- CitySpark: `ticketUrl`.
- Generic app/handoff links should be flagged instead of accepted blindly.
- Platform event pages may be retained when event-specific.
- Eventbrite `checkout-external`, generic DICE deep links, Ticketmaster
  home/artist pages, and generic pages should be rejected or flagged.
- Do not treat CitySpark `links[].linkUrl` or generic event `url` as a ticket
  link unless the classifier validates it as event-specific.

## Ticketmaster Music Classification Mapping

Reference file:

- `docs/ticketmaster_classifications.md`

Ticketmaster classification data is event/music taxonomy metadata, not a
Music Roadtrip POI category source.

Rules:

- `segment=Music` is a positive music relevance signal.
- Music genres/subgenres may populate `music_category`, `provider_genre`,
  `provider_subgenre`, `normalized_genre`, and `normalized_genres_json`.
- Non-Music segments are flagged as low event relevance unless a future
  business rule explicitly allows them.
- Ticketmaster categories must not create venue/POI categories.

## Provider Compliance Notes

- Provider reference docs are schema references only.
- No live API calls are made in this milestone.
- Provider credentials must be loaded from environment variables only.
- API keys must not appear in templates, tests, logs, fixtures, or README
  examples.
- CitySpark is a paid licensed vendor API provider, not a first-party public
  source.
- Live CitySpark calls remain off until credentials and configuration are added.
- CitySpark records still pass through API Feed Review, normalization, dedupe,
  source claims, ticket QA, image QA, and app-feed readiness before use.

## Provider Pipeline / Developer Handoff Notes

Provider handoff docs should give a future implementer enough context to wire a
provider safely without exposing secrets:

- Intended endpoint and request shape.
- Authentication mechanism by name only; no keys or credential values.
- Provider fields mapped into Music Roadtrip fields.
- Cleanup and normalization rules.
- Ticket-link repair and rejection rules.
- Image QA and clearance rules.
- Provenance fields, source-chain fields, and external IDs to preserve.
- Expected normalized output.
- Review gates that must pass before live calls or app-feed use.

The API Feed Review Workbench is the private place to inspect raw provider
records, normalized candidates, source-chain provenance, manual JSON provider
records, and approve/hold/reject/send-to-enrichment decisions. It is not a
public intake page, and it is not necessarily where live provider calls happen.

## Fields Used For Dedupe

Strongest provider IDs:

- JamBase `identifier`.
- CitySpark `eventId`.

Fallback inputs:

- Provider key.
- Event name.
- Start datetime.
- Venue name.
- City.
- State.

These are saved on API feed records as `dedupe_source_fields_json` so reviewers
can see exactly which provider fields influenced the dedupe key.

## Fields Used For Venue Matching

Preferred provider IDs:

- JamBase `location.identifier`.

Fallback venue inputs:

- Venue name.
- Venue address.
- City.
- State.
- Zip/postal code.
- Country.
- Latitude.
- Longitude.
- Venue URL or source URL when supplied.

These are saved as `venue_match_fields_json` on API feed records and approved
events.

## Fields Used For Ticket-Link Quality Scoring

Inputs:

- Candidate URL.
- Host/domain.
- Path specificity.
- Platform-specific event-page patterns.
- Presence of tracking query parameters.
- Presence of session/cart/checkout handoff patterns.
- Provider repair source, such as JamBase offer category or CitySpark
  `ticketUrl`.

The classifier stores:

- `ticket_link_classification`
- `ticket_link_repair_suggestion`
- `recommended_ticket_link`
- `ticket_link_quality_score`
