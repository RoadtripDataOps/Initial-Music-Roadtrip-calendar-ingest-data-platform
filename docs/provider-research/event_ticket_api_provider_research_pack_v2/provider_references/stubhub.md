# StubHub Provider Reference

Generated: 2026-06-04

## Status

`official_public_api_docs_found_related`

## Provider Type

`catalog_inventory_ticketing_api`

## Official / reference docs found

- https://developer.stubhub.com/api-reference/catalog/

## Access / auth notes

OAuth2.

## Event / ticket data notes

Catalog API exposes categories, list/search events, event by ID/external platform ID, venues, etc. Similar to viagogo catalog docs.

## Music Roadtrip mapping implications

Add as related optional provider if you plan to use StubHub directly. Otherwise keep as related viagogo-family docs for mapping comparison.

## Additional notes

Not explicitly in the JamBase enum list but relevant to viagogo/secondary ticketing.

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
