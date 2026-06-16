# VenuePilot (`venuepilot`)

## Why this provider is in the pack
This provider/platform appeared in the Music Roadtrip master export through ticket-link or website domains. It was not part of the first provider ZIP, or it needed more specific export-driven notes.

## Export domain evidence
- Grouped provider key: `venuepilot`
- Domains/patterns: `venuepilot.com`, `tickets.venuepilot.com`
- Ticket-link mentions in Concert rows: 329
- Website mentions in Concert rows: 6
- Total URL mentions in Concert rows: 335
- Sample URL: https://tickets.venuepilot.com/e/christian-royce-ton-johnson-2026-07-16-cactus-club-milwaukee-635265

## API / docs status
No public API documentation found in this pass; product/support pages found.

## Official or relevant documentation links
- https://www.venuepilot.com/
- https://support.venuepilot.co/knowledge/from-hold-to-tickets-sold

## Music Roadtrip usage recommendation
- Source role: `venue_ticketing_platform`
- Recommended use now: provenance/ticket-link classification and QA.
- Do not add live API calls unless credentials, rate limits, and terms are explicitly reviewed.
- Do not hardcode credentials.
- Do not treat this as a primary event source unless a direct, permitted integration is approved.

## Mapping / cleanup notes
Treat as ticketing provider and venue-management system. No direct connector until partner docs.

## Suggested Codex actions
- Add/extend provider taxonomy entry for `venuepilot`.
- Add domain detection patterns above.
- Add this provider to ticketing_provider detection.
- If API docs are official and useful, add mapper placeholders only; do not make live calls.
- Route unknown/incomplete direct integrations through the API Feed Review Workbench as manual JSON or provenance-only candidates.
