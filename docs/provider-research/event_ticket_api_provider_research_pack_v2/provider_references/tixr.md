# Tixr Provider Reference

Generated: 2026-06-04

## Status

`official_public_apiary_docs_found`

## Provider Type

`ticketing_platform_api`

## Official / reference docs found

- https://tixrapi.docs.apiary.io/
- https://creators.tixr.com/products/integrations
- https://creators.tixr.com/products/studio

## Access / auth notes

Partner/API credentials likely required. Public Apiary documentation exists, but fetchable text is limited; third-party PolyAPI notes mention operations/webhooks.

## Event / ticket data notes

Likely supports clients/groups/events/orders/fans/transfers/forms/webhooks. Use as ticketing/partner operations provider rather than broad public discovery until docs are reviewed in browser.

## Music Roadtrip mapping implications

Add as disabled/private_by_default with manual JSON fixture support. Recognize tixr.com event-specific URLs as platform_event ticket links per audit logic.

## Additional notes

Codex should not assume all Tixr endpoints from third-party posts; use official Apiary docs if accessible locally.

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
