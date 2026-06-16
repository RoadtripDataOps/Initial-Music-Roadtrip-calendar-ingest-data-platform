# SuiteHop Provider Reference

Generated: 2026-06-04

## Status

`no_public_api_docs_found`

## Provider Type

`premium_seating_marketplace`

## Official / reference docs found

- https://suitehop.com/
- https://suitehop.com/policy/seller-services-agreement
- https://suitehop.com/how-it-works

## Access / auth notes

No official public API docs found.

## Event / ticket data notes

Public pages describe premium seating/suite marketplace, but not a documented event API.

## Music Roadtrip mapping implications

Add as no_connector / link-only provider unless partner docs are supplied.

## Additional notes

Given focus on premium seating, treat as ticket link provider rather than event discovery source.

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
