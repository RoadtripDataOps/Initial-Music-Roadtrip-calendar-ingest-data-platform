# Seated / CM.com Ticketing Provider Reference

Generated: 2026-06-04

## Status

`official_public_reference_found`

## Provider Type

`ticketing_reporting_api`

## Official / reference docs found

- https://developers.cm.com/ticketing/reference/seated-api

## Access / auth notes

X-CM-PRODUCTTOKEN header; token requested via Seated Ticketing team.

## Event / ticket data notes

Docs expose reporting/data endpoints including Event get, Ticket get, Venue get, Order get, Customer get, products, subscriptions, callback functionality, etc. Focus is insight/reporting rather than public event discovery.

## Music Roadtrip mapping implications

Add provider registry entry as partner_ticketing_reporting. Good for partner reporting, event metadata and ticket status. Use event/venue endpoints if credentialed.

## Additional notes

Filtering syntax uses subject[FILTER_NAME]: FILTER_VALUE; depth controls nested response detail.

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
