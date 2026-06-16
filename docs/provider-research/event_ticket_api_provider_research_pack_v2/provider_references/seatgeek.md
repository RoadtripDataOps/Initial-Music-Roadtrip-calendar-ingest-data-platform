# SeatGeek Provider Reference

Generated: 2026-06-04

## Status

`official_developer_portal_found_js_docs`

## Provider Type

`event_discovery_ticketing_api`

## Official / reference docs found

- https://seatgeek.com/build
- https://platform.seatgeek.com/
- https://seatgeek.com/api-terms

## Access / auth notes

API key / developer portal. Some detailed docs require JavaScript/login and are not easily snapshotable from browser text.

## Event / ticket data notes

Platform overview describes a canonical live-events dataset with venue latitude/longitude. API terms govern access and impose restrictions; terms warn against systematic download/storage/scraping outside authorized usage.

## Music Roadtrip mapping implications

Add provider as disabled until terms/credential review. If enabled, map events/performers/venues; preserve attribution and comply with storage/download restrictions.

## Additional notes

Strong compliance review needed before using as source of truth.

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
