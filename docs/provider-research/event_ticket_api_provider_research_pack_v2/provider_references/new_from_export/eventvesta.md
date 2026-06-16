# Event Vesta / Vesta (`eventvesta`)

## Why this provider is in the pack
This provider/platform appeared in the Music Roadtrip master export through ticket-link or website domains. It was not part of the first provider ZIP, or it needed more specific export-driven notes.

## Export domain evidence
- Grouped provider key: `eventvesta`
- Domains/patterns: `eventvesta.com`
- Ticket-link mentions in Concert rows: 901
- Website mentions in Concert rows: 827
- Total URL mentions in Concert rows: 1728
- Sample URL: https://eventvesta.com/events/127421/t/tickets

## API / docs status
No public API documentation found in this pass; product site found.

## Official or relevant documentation links
- https://eventvesta.com/
- https://info.eventvesta.com/about/

## Music Roadtrip usage recommendation
- Source role: `event_marketing_platform`
- Recommended use now: provenance/ticket-link classification and QA.
- Do not add live API calls unless credentials, rate limits, and terms are explicitly reviewed.
- Do not hardcode credentials.
- Do not treat this as a primary event source unless a direct, permitted integration is approved.

## Mapping / cleanup notes
Treat as upstream/ticket platform discovered by URL. Use as provenance only until docs/partner access are supplied.

## Suggested Codex actions
- Add/extend provider taxonomy entry for `eventvesta`.
- Add domain detection patterns above.
- Add this provider to ticketing_provider detection.
- If API docs are official and useful, add mapper placeholders only; do not make live calls.
- Route unknown/incomplete direct integrations through the API Feed Review Workbench as manual JSON or provenance-only candidates.
