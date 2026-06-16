# SimpleTix (`simpletix`)

## Why this provider is in the pack
This provider/platform appeared in the Music Roadtrip master export through ticket-link or website domains. It was not part of the first provider ZIP, or it needed more specific export-driven notes.

## Export domain evidence
- Grouped provider key: `simpletix`
- Domains/patterns: `simpletix.com`
- Ticket-link mentions in Concert rows: 69
- Website mentions in Concert rows: 18
- Total URL mentions in Concert rows: 87
- Sample URL: https://www.simpletix.com/e/latin-night-tickets-222128

## API / docs status
Official platform/help pages found; complete public API reference not found in this pass.

## Official or relevant documentation links
- https://www.simpletix.com/
- https://help.simpletix.com/docs/integrations/connect-simpletix-to-zapier

## Music Roadtrip usage recommendation
- Source role: `event_ticketing_platform`
- Recommended use now: provenance/ticket-link classification and QA.
- Do not add live API calls unless credentials, rate limits, and terms are explicitly reviewed.
- Do not hardcode credentials.
- Do not treat this as a primary event source unless a direct, permitted integration is approved.

## Mapping / cleanup notes
Treat as ticketing provider. If API docs are supplied later, add direct mapper.

## Suggested Codex actions
- Add/extend provider taxonomy entry for `simpletix`.
- Add domain detection patterns above.
- Add this provider to ticketing_provider detection.
- If API docs are official and useful, add mapper placeholders only; do not make live calls.
- Route unknown/incomplete direct integrations through the API Feed Review Workbench as manual JSON or provenance-only candidates.
