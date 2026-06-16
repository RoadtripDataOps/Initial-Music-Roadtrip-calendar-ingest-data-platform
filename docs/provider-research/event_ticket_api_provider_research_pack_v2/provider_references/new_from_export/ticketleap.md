# TicketLeap (`ticketleap`)

## Why this provider is in the pack
This provider/platform appeared in the Music Roadtrip master export through ticket-link or website domains. It was not part of the first provider ZIP, or it needed more specific export-driven notes.

## Export domain evidence
- Grouped provider key: `ticketleap`
- Domains/patterns: `ticketleap.com`, `events.ticketleap.com`
- Ticket-link mentions in Concert rows: 56
- Website mentions in Concert rows: 6
- Total URL mentions in Concert rows: 62
- Sample URL: https://events.ticketleap.com/tickets/smellslikenirvanatribute/SMELLSLIKENIRVANATRIBUTEJUNE6DEADORIGINAL?fbclid=IwY2xjawQC7QhleHRuA2FlbQIxMABicmlkETJwWXNDemZCYU5jN1JHVDZIc3J0YwZhcHBfaWQQMjIyMDM5MTc4ODIwMDg5MgABHiXhfQSLA771F3MIHJ-AAveyVYHMAADpdxUGe120GF7p3qi4hCHmERTj9R1a_aem_PKmv6dHoykAjUE7lztZXTQ

## API / docs status
No official complete public API docs found in this pass; third-party references suggest limited/readonly API.

## Official or relevant documentation links
- https://apitracker.io/a/ticketleap
- https://github.com/connorskees/ticketleap

## Music Roadtrip usage recommendation
- Source role: `event_ticketing_platform`
- Recommended use now: provenance/ticket-link classification and QA.
- Do not add live API calls unless credentials, rate limits, and terms are explicitly reviewed.
- Do not hardcode credentials.
- Do not treat this as a primary event source unless a direct, permitted integration is approved.

## Mapping / cleanup notes
Treat as ticketing provider; no direct connector until official docs are supplied.

## Suggested Codex actions
- Add/extend provider taxonomy entry for `ticketleap`.
- Add domain detection patterns above.
- Add this provider to ticketing_provider detection.
- If API docs are official and useful, add mapper placeholders only; do not make live calls.
- Route unknown/incomplete direct integrations through the API Feed Review Workbench as manual JSON or provenance-only candidates.
