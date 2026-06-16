# See Tickets Provider Reference

Generated: 2026-06-04

## Status

`partner_private_docs_limited`

## Provider Type

`ticketing_platform`

## Official / reference docs found

- https://group.seetickets.com/ticketing/
- https://clients.eventim.us/hc/en-us/articles/18890091910939-Affiliates-Network

## Access / auth notes

Partner/API integration access; public page confirms many API integrations, but endpoint reference is not public.

## Event / ticket data notes

Potentially overlaps with Eventim/See Tickets US Affiliate Network. Complete schema likely requires direct partner relationship.

## Music Roadtrip mapping implications

Add disabled/private_by_default. Treat See Tickets URLs as ticket links. Use manual JSON only if docs/payloads are supplied.

## Additional notes

Third-party “API” services exist but are not official docs.

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
