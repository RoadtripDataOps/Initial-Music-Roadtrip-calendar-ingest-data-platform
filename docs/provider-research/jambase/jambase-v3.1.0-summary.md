# JamBase API v3.1.0 Summary

JamBase is a licensed vendor event feed in the Music Roadtrip API Feed Review
Workbench. This local POC documents the v3.1.0 request and mapping shape, but
does not make live JamBase API calls, add API keys, or hardcode credentials.

## Version Metadata

- Provider: JamBase
- API title: JamBase Concert Data API
- API version: v3.1.0
- OpenAPI version: 3.1.0
- Base URL: `https://api.data.jambase.com/v3`
- Auth: `apikey` query parameter
- Postman collection: v2.1
- Workbench status: Workbench Open
- Live calls: Live Calls Off unless future config explicitly enables them
- Provider type: Licensed Vendor Feed / Event Feed

## Supported Endpoints

- `GET /events`
- `GET /events/id/{eventDataSource}:{eventId}`
- `GET /streams`
- `GET /streams/id/{streamDataSource}:{streamId}`
- `GET /artists`
- `GET /artists/id/{artistDataSource}:{artistId}`
- `GET /venues`
- `GET /venues/id/{venueDataSource}:{venueId}`
- `GET /geographies/cities`
- `GET /geographies/metros`
- `GET /geographies/states`
- `GET /geographies/countries`
- `GET /lookups/event-data-sources`
- `GET /lookups/stream-data-sources`
- `GET /lookups/artist-data-sources`
- `GET /lookups/venue-data-sources`
- `GET /genres`

## Events Search

Example request preview:

```http
GET https://api.data.jambase.com/v3/events?apikey=REDACTED&page=1&perPage=100&eventType=concerts
Accept: application/json
```

`GET /events` supports `page`, `perPage`, `eventType`, `eventId`, `name`,
`artistId`, `artistName`, `genreSlug`, `venueId`, `venueName`, geography
filters, date presets/ranges, data-source filters, modified/published date
filters, expansion flags, sort, and `excludeEventPerformers`.

Pagination uses `page` and `perPage`; `page` defaults to 1, `perPage` defaults
to 40, and `perPage` is capped at 100. Responses may include `nextPage` and
`previousPage`.

The v3.1.0 OpenAPI enum uses plural `eventType` values: `concerts` and
`festivals`. Older singular examples such as `concert` or `festival` are
treated as documentation/example discrepancies; prefer the v3.1.0 enum.

## Schema Highlights

- `identifier` is the strongest JamBase event source ID and maps to
  `source_record_id` / `provider_event_id`.
- `@type` identifies provider event type. Concert and Festival records both
  normalize to `category=Concert` and `record_type=event`, while preserving
  `provider_event_type`.
- `startDate`, `endDate`, `previousStartDate`, and `doorTime` are venue-local
  values without offset. Use `location.address.x-timezone` when conversion is
  needed.
- `eventStatus` maps to event lifecycle review values: scheduled, postponed,
  rescheduled, or cancelled.
- `image` and `x-promoImage` become image candidates only. Promotional/admat
  imagery should be reviewed before use.
- `offers[].category=ticketingLinkPrimary` is the preferred ticket link;
  `ticketingLinkSecondary` is the fallback. Preserve all offers in
  `ticket_offers_json`.
- `offers[].seller` maps to ticketing provider/source-chain signals.
- `x-externalIdentifiers` and `sameAs` are preserved in provenance fields.

## Source Taxonomy

Event data sources include `axs`, `dice`, `etix`, `eventbrite`, `eventim-de`,
`jambase`, `seated`, `see-tickets`, `see-tickets-uk`, `sofar-sounds`,
`seatgeek`, `suitehop`, `ticketmaster`, `tixr`, and `viagogo`.

Artist data sources add `spotify` and `musicbrainz`. Venue data sources mirror
the venue/ticketing provider set. Stream data sources currently list
`jambase`.

These values are taxonomy, provenance, and QA references only; they do not
create direct integrations for every provider.

## Streams, Geographies, And Lookups

Streams are documented as future related content and should not be treated as
primary Music Roadtrip app events in this patch. Geographies, lookups, and
genres can later support region/market modeling, source taxonomy, and genre
normalization.
