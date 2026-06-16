# Bandsintown Provider Reference

Generated: 2026-06-04

## Status

`official_public_artist_api_docs_found`

## Provider Type

`artist_event_feed`

## Official / reference docs found

- https://help.artists.bandsintown.com/en/articles/9186477-api-documentation
- https://help.artists.bandsintown.com/en/articles/7053475-what-is-the-bandsintown-api

## Access / auth notes

app_id query parameter. Current docs position the API for artists/teams showing their own event data on sites/apps.

## Event / ticket data notes

Artist event endpoint returns date/time, venue name/location, ticket links/offers, lineup, description, title, and Bandsintown event page. It is artist-centric, not a broad global city/date feed.

## Music Roadtrip mapping implications

Add as artist_event_feed provider. Useful for artist-specific backfill/enrichment and ticket link lookup. Normalize events to Concert candidates; preserve offers[] and Bandsintown event URL.

## Additional notes

Offers array may be empty; docs show RSVP/Notify Me/Track CTA behaviors.

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
