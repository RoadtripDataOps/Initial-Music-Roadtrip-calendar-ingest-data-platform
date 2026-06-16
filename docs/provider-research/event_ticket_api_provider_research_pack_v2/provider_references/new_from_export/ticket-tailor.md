# Ticket Tailor (`ticket-tailor`)

## Why this provider is in the pack
This provider/platform appeared in the Music Roadtrip master export through ticket-link or website domains. It was not part of the first provider ZIP, or it needed more specific export-driven notes.

## Export domain evidence
- Grouped provider key: `ticket-tailor`
- Domains/patterns: `tickettailor.com`, `buytickets.at`, `api.tickettailor.com`
- Ticket-link mentions in Concert rows: 67
- Website mentions in Concert rows: 10
- Total URL mentions in Concert rows: 77
- Sample URL: https://www.tickettailor.com/events/barnatparadisestationcom/2099924

## API / docs status
Official API documentation found. API key via HTTP Basic Auth. Event and event-series endpoints documented.

## Official or relevant documentation links
- https://developers.tickettailor.com/docs/api/ticket-tailor-api/
- https://developers.tickettailor.com/docs/api/get-all-events/
- https://developers.tickettailor.com/docs/api/get-event-by-id/
- https://developers.tickettailor.com/docs/api/get-all-event-series/

## Music Roadtrip usage recommendation
- Source role: `event_ticketing_platform`
- Recommended use now: provenance/ticket-link classification and QA.
- Do not add live API calls unless credentials, rate limits, and terms are explicitly reviewed.
- Do not hardcode credentials.
- Do not treat this as a primary event source unless a direct, permitted integration is approved.

## Mapping / cleanup notes
Map tickettailor.com/buytickets.at as ticket-tailor. Event-specific links can be platform_event.

## Suggested Codex actions
- Add/extend provider taxonomy entry for `ticket-tailor`.
- Add domain detection patterns above.
- Add this provider to ticketing_provider detection.
- If API docs are official and useful, add mapper placeholders only; do not make live calls.
- Route unknown/incomplete direct integrations through the API Feed Review Workbench as manual JSON or provenance-only candidates.
