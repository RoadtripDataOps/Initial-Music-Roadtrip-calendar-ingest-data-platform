# SpeakeasyGo Ticketing (`speakeasygo`)

## Why this provider is in the pack
This provider/platform appeared in the Music Roadtrip master export through ticket-link or website domains. It was not part of the first provider ZIP, or it needed more specific export-driven notes.

## Export domain evidence
- Grouped provider key: `speakeasygo`
- Domains/patterns: `speakeasygo.com`
- Ticket-link mentions in Concert rows: 244
- Website mentions in Concert rows: 0
- Total URL mentions in Concert rows: 244
- Sample URL: https://speakeasygo.com/LIV%20Nightclub%20-%20Las%20Vegas/Matroda?eid=EVE-QYM0SH&utm_source=jambase

## API / docs status
Ticketing product page found; no public API documentation found in this pass.

## Official or relevant documentation links
- https://speakeasygo.com/partner/ticketing
- https://speakeasygo.com/partner/terms

## Music Roadtrip usage recommendation
- Source role: `event_ticketing_platform`
- Recommended use now: provenance/ticket-link classification and QA.
- Do not add live API calls unless credentials, rate limits, and terms are explicitly reviewed.
- Do not hardcode credentials.
- Do not treat this as a primary event source unless a direct, permitted integration is approved.

## Mapping / cleanup notes
Map as ticketing_provider=speakeasygo; provenance only unless docs are supplied.

## Suggested Codex actions
- Add/extend provider taxonomy entry for `speakeasygo`.
- Add domain detection patterns above.
- Add this provider to ticketing_provider detection.
- If API docs are official and useful, add mapper placeholders only; do not make live calls.
- Route unknown/incomplete direct integrations through the API Feed Review Workbench as manual JSON or provenance-only candidates.
