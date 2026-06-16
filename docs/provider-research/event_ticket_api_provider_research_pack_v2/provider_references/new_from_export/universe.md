# Universe (`universe`)

## Why this provider is in the pack
This provider/platform appeared in the Music Roadtrip master export through ticket-link or website domains. It was not part of the first provider ZIP, or it needed more specific export-driven notes.

## Export domain evidence
- Grouped provider key: `universe`
- Domains/patterns: `universe.com`, `developers.universe.com`
- Ticket-link mentions in Concert rows: 576
- Website mentions in Concert rows: 1
- Total URL mentions in Concert rows: 577
- Sample URL: https://www.universe.com/events/collect-a-con-new-jersey-2-tickets-CK5907

## API / docs status
Official Universe developer portal found; Ticketmaster Discovery API can also return Universe-sourced events via source filter.

## Official or relevant documentation links
- https://developers.universe.com/
- https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/

## Music Roadtrip usage recommendation
- Source role: `event_ticketing_platform`
- Recommended use now: provenance/ticket-link classification and QA.
- Do not add live API calls unless credentials, rate limits, and terms are explicitly reviewed.
- Do not hardcode credentials.
- Do not treat this as a primary event source unless a direct, permitted integration is approved.

## Mapping / cleanup notes
Map universe.com as ticketing_provider=universe. It may also appear through Ticketmaster source=universe.

## Suggested Codex actions
- Add/extend provider taxonomy entry for `universe`.
- Add domain detection patterns above.
- Add this provider to ticketing_provider detection.
- If API docs are official and useful, add mapper placeholders only; do not make live calls.
- Route unknown/incomplete direct integrations through the API Feed Review Workbench as manual JSON or provenance-only candidates.
