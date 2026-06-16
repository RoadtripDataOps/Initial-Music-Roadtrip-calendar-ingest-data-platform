# TicketWeb Provider Reference

Generated: 2026-06-04

## Status

`official_integration_pages_found_private_reference`

## Provider Type

`ticketing_platform`

## Official / reference docs found

- https://info.ticketweb.com/client-website-services/
- https://info.ticketweb.com/wordpress-plugin/
- https://info.ticketweb.com/checkout/
- https://www.ticketweb.ie/aboutus/ticket-your-events.html

## Access / auth notes

Direct API access appears available to clients; public docs for exact API endpoints are not public.

## Event / ticket data notes

WordPress plugin and widget sync event details at scheduled intervals; TicketWeb IE says websites can automatically update event-listing pages with standard API.

## Music Roadtrip mapping implications

Add disabled/private_by_default. Recognize TicketWeb event URLs as ticket links. Implement connector only after official API credentials/docs are provided.

## Additional notes

Ticketmaster Discovery API may surface TicketWeb-sourced events, so avoid duplicate provider handling without dedupe.

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
