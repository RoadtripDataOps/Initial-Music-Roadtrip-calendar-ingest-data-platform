# EVENTIM / See Tickets US Affiliate Network Provider Reference

Generated: 2026-06-04

## Status

`official_affiliate_feed_article_found`

## Provider Type

`affiliate_event_feed`

## Official / reference docs found

- https://clients.eventim.us/hc/en-us/articles/18890091910939-Affiliates-Network
- https://group.seetickets.com/ticketing/

## Access / auth notes

Affiliate/partner access; article describes API-based feed for marketplaces to ingest event information.

## Event / ticket data notes

Affiliate Network appears intended for marketplace event ingestion and affiliate tracking; full schema likely requires partner access.

## Music Roadtrip mapping implications

Add eventim_affiliate provider disabled until credentials/docs. Support feed/manual fixture review. Preserve affiliate tracking separately from clean canonical ticket URL.

## Additional notes

Eventim US article links to API Feed details and web application. Treat as partner feed, not open public API.

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
