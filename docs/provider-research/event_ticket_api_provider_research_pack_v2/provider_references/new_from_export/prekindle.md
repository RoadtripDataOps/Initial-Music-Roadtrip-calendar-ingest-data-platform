# Prekindle (`prekindle`)

## Why this provider is in the pack
This provider/platform appeared in the Music Roadtrip master export through ticket-link or website domains. It was not part of the first provider ZIP, or it needed more specific export-driven notes.

## Export domain evidence
- Grouped provider key: `prekindle`
- Domains/patterns: `prekindle.com`
- Ticket-link mentions in Concert rows: 29
- Website mentions in Concert rows: 111
- Total URL mentions in Concert rows: 140
- Sample URL: https://www.prekindle.com/event/67781-troy-doherty-houston

## API / docs status
Official site says Open API exists; public endpoint reference was not located in this pass.

## Official or relevant documentation links
- https://www.prekindle.com/features
- https://www.prekindle.com/sell-tickets
- https://prekindlesupport.freshdesk.com/support/solutions/articles/12000060864-explore-the-prekindle-dashboard

## Music Roadtrip usage recommendation
- Source role: `event_ticketing_platform`
- Recommended use now: provenance/ticket-link classification and QA.
- Do not add live API calls unless credentials, rate limits, and terms are explicitly reviewed.
- Do not hardcode credentials.
- Do not treat this as a primary event source unless a direct, permitted integration is approved.

## Mapping / cleanup notes
Treat as ticketing provider; direct connector should wait for account docs/API key.

## Suggested Codex actions
- Add/extend provider taxonomy entry for `prekindle`.
- Add domain detection patterns above.
- Add this provider to ticketing_provider detection.
- If API docs are official and useful, add mapper placeholders only; do not make live calls.
- Route unknown/incomplete direct integrations through the API Feed Review Workbench as manual JSON or provenance-only candidates.
