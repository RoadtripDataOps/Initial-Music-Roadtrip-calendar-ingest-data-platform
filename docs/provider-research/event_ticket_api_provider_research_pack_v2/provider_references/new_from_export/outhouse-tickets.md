# Outhouse Tickets (`outhouse-tickets`)

## Why this provider is in the pack
This provider/platform appeared in the Music Roadtrip master export through ticket-link or website domains. It was not part of the first provider ZIP, or it needed more specific export-driven notes.

## Export domain evidence
- Grouped provider key: `outhouse-tickets`
- Domains/patterns: `outhousetickets.com`, `events.outhousetickets.com`
- Ticket-link mentions in Concert rows: 429
- Website mentions in Concert rows: 346
- Total URL mentions in Concert rows: 775
- Sample URL: https://events.outhousetickets.com/e/furnas-county-fair-concert-2026?aff=cityspark

## API / docs status
No public API documentation found in this pass.

## Official or relevant documentation links
- https://events.outhousetickets.com/

## Music Roadtrip usage recommendation
- Source role: `event_ticketing_platform`
- Recommended use now: provenance/ticket-link classification and QA.
- Do not add live API calls unless credentials, rate limits, and terms are explicitly reviewed.
- Do not hardcode credentials.
- Do not treat this as a primary event source unless a direct, permitted integration is approved.

## Mapping / cleanup notes
Treat as ticketing provider based on domain. Event-specific links may be platform_event. No direct connector.

## Suggested Codex actions
- Add/extend provider taxonomy entry for `outhouse-tickets`.
- Add domain detection patterns above.
- Add this provider to ticketing_provider detection.
- If API docs are official and useful, add mapper placeholders only; do not make live calls.
- Route unknown/incomplete direct integrations through the API Feed Review Workbench as manual JSON or provenance-only candidates.
