# Codex Prompt: Import Event Ticket Provider Research Pack

You are working in the Music Roadtrip Calendar Ingest POC.

Import this research pack under:

`docs/provider-research/`

Then update the API feed review/provider registry to include provider metadata from:

`docs/provider-research/data/provider_index.json`

## Important rules

- Do not add live API calls yet unless the provider already has credentials/config.
- Do not hardcode API keys.
- Do not expose API keys in templates, README examples, logs, or tests.
- Keep live provider calls off by default unless credentials and contractual
  permission exist.
- Use manual JSON upload and synthetic fixtures first.
- Normalize event feed records as `category = Concert` and `record_type = event`.
- Do not convert Concert events into POIs.
- Keep venue profiles as POI-style containers that display nested Concert events.
- CitySpark is a paid licensed vendor API feed; keep live calls off until
  credentials and configuration are added, and keep provider records behind
  API Feed Review before app use.
- Spotify and SerpAPI remain enrichment providers only.

## Add provider registry entries

Add or update provider cards for:

- AXS
- Bandsintown
- DICE.fm
- Etix
- Eventbrite
- Eventim / See Tickets US Affiliate Network
- Seated / CM.com Ticketing
- See Tickets
- TicketWeb
- SeatGeek
- Sofar Sounds
- SuiteHop
- Tixr
- viagogo
- StubHub
- Ticketmaster
- JamBase
- CitySpark

## Provider status behavior

Use these statuses:

- `official_public_api_docs_found`
- `official_public_reference_found`
- `official_affiliate_feed_article_found`
- `partner_private_docs_limited`
- `partner_private_public_docs_limited`
- `no_public_api_docs_found`
- `existing_docs_present`
- `existing_docs_present_review_only`

Only providers with public docs and permitted credentials should be eligible for future live connector work.

## UI additions

In `/admin/api-feeds`, add a docs/reference section for each provider showing:

- official docs links
- status
- auth model
- storage policy
- provider type
- mapping notes
- ticket-link notes
- dedupe fields
- venue matching fields

## Tests

Add tests that:

- provider registry renders all providers
- disabled/private providers cannot run live API calls
- CitySpark is handled like JamBase as a paid licensed vendor feed
- providers with no public docs are marked no_connector/private
- no API keys appear in code/templates/tests
- provider docs links render in admin API feed cards
