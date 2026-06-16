# Sofar Sounds Provider Reference

Generated: 2026-06-04

## Status

`no_official_event_api_docs_found`

## Provider Type

`music_event_platform`

## Official / reference docs found

- https://www.sofarsounds.com/
- https://www.sofarsounds.com/terms_and_conditions
- https://github.com/sofarsounds/API-Documentation

## Access / auth notes

No current official public event API docs found. GitHub API-Documentation repo appears to be a generic Slate template, not Sofar event API reference.

## Event / ticket data notes

Sofar public site and terms confirm platform lists live music events/tickets, but no public event feed API was found.

## Music Roadtrip mapping implications

Add as no_connector. Support only client-submitted Sofar calendar URLs or manual JSON if partner docs/payloads are supplied.

## Additional notes

Do not scrape by default; treat as partner/source URL candidate only.

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
