# Eventbrite Provider Reference

Generated: 2026-06-04

## Status

`official_public_api_docs_found`

## Provider Type

`event_management_ticketing_api`

## Official / reference docs found

- https://www.eventbrite.com/platform/api
- https://www.eventbrite.com/platform/docs/introduction
- https://www.eventbrite.com/platform/docs/events
- https://www.eventbrite.com/platform/docs/api-basics
- https://www.eventbrite.com/platform/docs/changelog
- https://jsapi.apiary.io/apis/eventbriteapiv3public.source

## Access / auth notes

OAuth 2.0 / bearer token. API docs also expose API Explorer/Apiary-style reference. Some older Eventbrite endpoints were deprecated as Eventbrite moved to organization-based flows.

## Event / ticket data notes

Eventbrite API v3 supports event, organization, venue, ticket class, image upload, and related workflows. For ingestion, prefer organizer/organization event listing or event retrieve endpoints over deprecated public search assumptions.

## Music Roadtrip mapping implications

Add eventbrite provider. Use manual JSON first. Normalize event objects to Concert only when music relevance is confirmed. Reject /checkout-external as final ticket link per existing ticket-link audit.

## Additional notes

Keep OAuth tokens out of repo. Public search behavior has changed over time; use docs/changelog and organization event endpoints.

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
