# Etix Provider Reference

Generated: 2026-06-04

## Status

`partner_private_docs_limited`

## Provider Type

`ticketing_platform`

## Official / reference docs found

- https://hello.etix.com/clients/integrations-partnerships/
- https://www.etix.com/ticket/online3/apiPartnerTerms.jsp

## Access / auth notes

Partner/API access; public API Partner Terms exist, but complete endpoint reference was not found publicly.

## Event / ticket data notes

Likely partner-specific event/ticket data access. Use Etix URLs as ticket links unless client supplies official API docs or payloads.

## Music Roadtrip mapping implications

Add as disabled/private_by_default. Support URL QA classification and manual JSON fixture mapping only after partner docs are provided.

## Additional notes

Public pages emphasize integrations and ticketing/marketing solutions; not sufficient for live connector implementation.

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
