# Tix.com (`tix-com`)

## Why this provider is in the pack
This provider/platform appeared in the Music Roadtrip master export through ticket-link or website domains. It was not part of the first provider ZIP, or it needed more specific export-driven notes.

## Export domain evidence
- Grouped provider key: `tix-com`
- Domains/patterns: `tix.com`
- Ticket-link mentions in Concert rows: 60
- Website mentions in Concert rows: 13
- Total URL mentions in Concert rows: 73
- Sample URL: https://www.tix.com/ticket-sales/empresstheatre/7268/event/1444117

## API / docs status
Official platform site found; public API reference not found in this pass.

## Official or relevant documentation links
- https://www.tix.com/

## Music Roadtrip usage recommendation
- Source role: `event_ticketing_platform`
- Recommended use now: provenance/ticket-link classification and QA.
- Do not add live API calls unless credentials, rate limits, and terms are explicitly reviewed.
- Do not hardcode credentials.
- Do not treat this as a primary event source unless a direct, permitted integration is approved.

## Mapping / cleanup notes
Treat as ticketing provider based on URL only.

## Suggested Codex actions
- Add/extend provider taxonomy entry for `tix-com`.
- Add domain detection patterns above.
- Add this provider to ticketing_provider detection.
- If API docs are official and useful, add mapper placeholders only; do not make live calls.
- Route unknown/incomplete direct integrations through the API Feed Review Workbench as manual JSON or provenance-only candidates.
