# HoldMyTicket (`holdmyticket`)

## Why this provider is in the pack
This provider/platform appeared in the Music Roadtrip master export through ticket-link or website domains. It was not part of the first provider ZIP, or it needed more specific export-driven notes.

## Export domain evidence
- Grouped provider key: `holdmyticket`
- Domains/patterns: `holdmyticket.com`, `docs.holdmyticket.com`
- Ticket-link mentions in Concert rows: 120
- Website mentions in Concert rows: 28
- Total URL mentions in Concert rows: 148
- Sample URL: https://holdmyticket.com/event/452084

## API / docs status
Official docs found. Event API described as read-only for account events by API key.

## Official or relevant documentation links
- https://docs.holdmyticket.com/doc/434/events
- https://docs.holdmyticket.com/doc/441/orders
- https://sell.holdmyticket.com/web-design-services-event-ticketing

## Music Roadtrip usage recommendation
- Source role: `event_ticketing_platform`
- Recommended use now: provenance/ticket-link classification and QA.
- Do not add live API calls unless credentials, rate limits, and terms are explicitly reviewed.
- Do not hardcode credentials.
- Do not treat this as a primary event source unless a direct, permitted integration is approved.

## Mapping / cleanup notes
Map holdmyticket.com. Good provenance/ticket provider, possible direct mapper with account/API key.

## Suggested Codex actions
- Add/extend provider taxonomy entry for `holdmyticket`.
- Add domain detection patterns above.
- Add this provider to ticketing_provider detection.
- If API docs are official and useful, add mapper placeholders only; do not make live calls.
- Route unknown/incomplete direct integrations through the API Feed Review Workbench as manual JSON or provenance-only candidates.
