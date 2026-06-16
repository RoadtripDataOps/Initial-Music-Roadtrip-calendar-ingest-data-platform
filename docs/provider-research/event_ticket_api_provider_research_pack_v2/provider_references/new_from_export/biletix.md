# Biletix (`biletix`)

## Why this provider is in the pack
This provider/platform appeared in the Music Roadtrip master export through ticket-link or website domains. It was not part of the first provider ZIP, or it needed more specific export-driven notes.

## Export domain evidence
- Grouped provider key: `biletix`
- Domains/patterns: `biletix.com`
- Ticket-link mentions in Concert rows: 290
- Website mentions in Concert rows: 0
- Total URL mentions in Concert rows: 290
- Sample URL: https://www.biletix.com/performance/5OSM8/001/TURKIYE/tr?utm_source=jambase

## API / docs status
No official public API docs found in this pass.

## Official or relevant documentation links
- https://www.biletix.com/

## Music Roadtrip usage recommendation
- Source role: `event_ticketing_platform`
- Recommended use now: provenance/ticket-link classification and QA.
- Do not add live API calls unless credentials, rate limits, and terms are explicitly reviewed.
- Do not hardcode credentials.
- Do not treat this as a primary event source unless a direct, permitted integration is approved.

## Mapping / cleanup notes
Treat as ticketing provider based on URL only. Likely Turkish ticket platform; do not direct connect without docs.

## Suggested Codex actions
- Add/extend provider taxonomy entry for `biletix`.
- Add domain detection patterns above.
- Add this provider to ticketing_provider detection.
- If API docs are official and useful, add mapper placeholders only; do not make live calls.
- Route unknown/incomplete direct integrations through the API Feed Review Workbench as manual JSON or provenance-only candidates.
