# AXS Provider Reference

Generated: 2026-06-04

## Status

`partner_private_public_docs_limited`

## Provider Type

`ticketing_platform`

## Official / reference docs found

- https://solutions.axs.com/us/venue-experience/
- https://solutions.axs.com/us/2026/02/25/axs-expands-tickets-for-good-partnership/

## Access / auth notes

Partner/API access only; no public event discovery docs found. Public AXS material mentions AXS APIs and integrations for ticket redemption / distribution partner workflows.

## Event / ticket data notes

No complete public event-discovery API reference found. Treat AXS links as ticket URLs or partner-supplied payloads until official partner docs are obtained.

## Music Roadtrip mapping implications

Add provider registry entry as disabled/private_by_default. Support manual JSON fixture mapping only after contract docs are added. Do not scrape AXS or use third-party scraper APIs by default.

## Additional notes

Third-party scraper APIs exist, but they are not official AXS docs and should not be treated as approved providers.

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
