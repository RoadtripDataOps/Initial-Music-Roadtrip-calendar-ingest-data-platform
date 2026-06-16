# Afton Tickets / Afton Shows (`afton-tickets`)

## Why this provider is in the pack
This provider/platform appeared in the Music Roadtrip master export through ticket-link or website domains. It was not part of the first provider ZIP, or it needed more specific export-driven notes.

## Export domain evidence
- Grouped provider key: `afton-tickets`
- Domains/patterns: `aftontickets.com`, `aftonshows.com`
- Ticket-link mentions in Concert rows: 55
- Website mentions in Concert rows: 0
- Total URL mentions in Concert rows: 55
- Sample URL: https://aftontickets.com/chicagotribute

## API / docs status
Official site found; no public API docs found in this pass.

## Official or relevant documentation links
- https://aftonshows.com/

## Music Roadtrip usage recommendation
- Source role: `promoter_ticketing_platform`
- Recommended use now: provenance/ticket-link classification and QA.
- Do not add live API calls unless credentials, rate limits, and terms are explicitly reviewed.
- Do not hardcode credentials.
- Do not treat this as a primary event source unless a direct, permitted integration is approved.

## Mapping / cleanup notes
Treat as ticketing provider based on URL only.

## Suggested Codex actions
- Add/extend provider taxonomy entry for `afton-tickets`.
- Add domain detection patterns above.
- Add this provider to ticketing_provider detection.
- If API docs are official and useful, add mapper placeholders only; do not make live calls.
- Route unknown/incomplete direct integrations through the API Feed Review Workbench as manual JSON or provenance-only candidates.
