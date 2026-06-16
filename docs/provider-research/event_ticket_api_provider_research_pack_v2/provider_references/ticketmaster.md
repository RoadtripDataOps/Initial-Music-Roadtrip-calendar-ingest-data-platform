# Ticketmaster Provider Reference

Generated: 2026-06-04

## Status

`existing_docs_plus_official_public_docs`

## Provider Type

`event_discovery_and_partner_ticketing_api`

## Official / reference docs found

- https://developer.ticketmaster.com/products-and-docs/apis/getting-started/
- https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/
- https://developer.ticketmaster.com/products-and-docs/apis/discovery-feed/
- https://developer.ticketmaster.com/products-and-docs/apis/partner/

## Access / auth notes

API key for Discovery; Partner API is restricted to official distribution relationships.

## Event / ticket data notes

Discovery API provides global event discovery and sources including Ticketmaster, Universe, FrontGate, Ticketmaster Resale, and others. Partner API supports reserve/purchase/retrieve for approved partners.

## Music Roadtrip mapping implications

You already have Ticketmaster classification docs. Use Discovery as event source if configured, Partner API only if contractually allowed. Music segment positive signal; non-music low relevance.

## Additional notes

Ticketmaster Discovery Feed can provide file-based event content sourced from Discovery API.

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
