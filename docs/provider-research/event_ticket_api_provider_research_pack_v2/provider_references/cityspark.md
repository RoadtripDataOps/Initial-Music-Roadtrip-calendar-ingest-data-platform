# CitySpark Provider Reference

Generated: 2026-06-04

## Status

`licensed_vendor_feed_review`

## Provider Type

`licensed_vendor_feed`

## Official / reference docs found

- docs/CitySpark_v1.json
- https://api.cityspark.com/terms

## Access / auth notes

X-API-Key or Bearer JWT per uploaded OpenAPI. Live calls remain off until credentials and configuration are added.

## Event / ticket data notes

EventSeries with eventId, name, description, primaryImage, location, instances, price, ticketUrl, url, categories, links.

## Music Roadtrip mapping implications

Treat CitySpark as a paid licensed vendor API feed for Music Roadtrip. It is handled like JamBase as a licensed provider feed. Live calls remain off until credentials and configuration are added. CitySpark records still pass through API Feed Review, normalization, dedupe, source claims, ticket QA, image QA, and app-feed readiness before use.

## Additional notes

Uploaded OpenAPI says version 2.0 despite filename CitySpark_v1.json.

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

Unless this provider is already configured with credentials and contract approval, keep live calls off. Use the private API Feed Review Workbench for manual JSON review and synthetic fixtures first; licensed records require provenance, retention, and approval controls.
