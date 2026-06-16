# JamBase Provider Reference

Generated: 2026-06-04

## Status

`existing_docs_present`

## Provider Type

`concert_event_data_api`

## Official / reference docs found

- docs/jambase_api_reference.md
- docs/JamBase-JamBaseAPI.yaml
- https://data.jambase.com/

## Access / auth notes

API key via apikey query parameter; User-Agent header required per your verified doc.

## Event / ticket data notes

Concert/Festival event feed with venues, artists, offers/ticket links, geographies, genres. Strong source_event_id via identifier.

## Music Roadtrip mapping implications

Already implemented or staged. Use as primary provider mapper reference.

## Additional notes

Your local docs are more precise than general web snippets.

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
