# DICE.fm Provider Reference

Generated: 2026-06-04

## Status

`official_partner_graphql_docs_found`

## Provider Type

`partner_ticketing_reporting`

## Official / reference docs found

- https://partners-endpoint.dice.fm/graphql/docs/index.html
- https://github.com/dicefm

## Access / auth notes

Partner access; GraphQL API. Public docs describe DICE Ticket Holders API for downstream systems tied to partner events.

## Event / ticket data notes

The official public partner docs focus on ticket holders, access management, finance/BI, events/venues/tickets as queryable objects. It is not an open broad event discovery feed.

## Music Roadtrip mapping implications

Add as disabled/private_by_default. Accept manual JSON/GraphQL fixture review. Treat generic link.dice.fm handoff links as suspicious/generic unless event-specific target is proven.

## Additional notes

Do not confuse DICE.fm with unrelated DiceTickets.com docs.

## Suggested normalized fields to inspect

- provider_key
- provider_record_id / source_record_id
- provider_event_id
- provider_venue_id
- provider_event_type
- category = Concert
- record_type = event
- event_name
- headliner
- supporting_artists
- start_datetime
- end_datetime
- timezone
- venue_name
- venue_address
- city
- state
- zip_code
- country
- latitude
- longitude
- event_url
- tickets_link
- main_image_url
- additional_image_urls
- provider_genre
- provider_subgenre
- ticket_link_classification
- dedupe_key
- dedupe_confidence
- raw_payload_json

## Default implementation stance

Unless this provider is already configured with credentials and contract approval, keep it disabled in live mode. Use manual JSON upload / synthetic fixtures first.
