# viagogo Provider Reference

Generated: 2026-06-04

## Status

`official_public_api_docs_found`

## Provider Type

`catalog_inventory_ticketing_api`

## Official / reference docs found

- https://developer.viagogo.net/
- https://developer.viagogo.net/api-reference/catalog/
- https://developer.viagogo.net/api-reference/sales/
- https://developer.viagogo.net/api-reference/webhooks/

## Access / auth notes

OAuth2. Catalog API uses production and sandbox base URLs.

## Event / ticket data notes

Catalog API exposes categories, events and venues; list/search events, get events, list venues, and sync via updated_since/resource_version. Sales and Webhooks APIs exist for authenticated user operations.

## Music Roadtrip mapping implications

Add provider as partner_catalog_feed disabled until terms/credentials. Strong event_id/provider ID can support dedupe. Separate catalog from inventory/sales APIs.

## Additional notes

Related StubHub docs are very similar and should be considered a sibling/related provider.

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
