# 24tix (`twentyfour-tix`)

## Why this provider is in the pack
This provider/platform appeared in the Music Roadtrip master export through ticket-link or website domains. It was not part of the first provider ZIP, or it needed more specific export-driven notes.

## Export domain evidence
- Grouped provider key: `twentyfour-tix`
- Domains/patterns: `24tix.com`
- Ticket-link mentions in Concert rows: 8
- Website mentions in Concert rows: 164
- Total URL mentions in Concert rows: 172
- Sample URL: https://www.24tix.com/events/3k2u5jxlcjbb5ospgvrbcm42q4

## API / docs status
Help/product pages found; no public API documentation found in this pass.

## Official or relevant documentation links
- https://www.24tix.com/help

## Music Roadtrip usage recommendation
- Source role: `regional_ticketing_platform`
- Recommended use now: provenance/ticket-link classification and QA.
- Do not add live API calls unless credentials, rate limits, and terms are explicitly reviewed.
- Do not hardcode credentials.
- Do not treat this as a primary event source unless a direct, permitted integration is approved.

## Mapping / cleanup notes
Treat as ticketing provider based on URL; no direct connector.

## Suggested Codex actions
- Add/extend provider taxonomy entry for `twentyfour-tix`.
- Add domain detection patterns above.
- Add this provider to ticketing_provider detection.
- If API docs are official and useful, add mapper placeholders only; do not make live calls.
- Route unknown/incomplete direct integrations through the API Feed Review Workbench as manual JSON or provenance-only candidates.
