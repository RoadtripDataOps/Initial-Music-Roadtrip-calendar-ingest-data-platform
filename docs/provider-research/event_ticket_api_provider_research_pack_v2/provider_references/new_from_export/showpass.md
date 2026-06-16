# Showpass (`showpass`)

## Why this provider is in the pack
This provider/platform appeared in the Music Roadtrip master export through ticket-link or website domains. It was not part of the first provider ZIP, or it needed more specific export-driven notes.

## Export domain evidence
- Grouped provider key: `showpass`
- Domains/patterns: `showpass.com`
- Ticket-link mentions in Concert rows: 52
- Website mentions in Concert rows: 39
- Total URL mentions in Concert rows: 91
- Sample URL: https://www.showpass.com/soul-rebels-blue-nile-may-2026/

## API / docs status
Official developer documentation found. Public discovery endpoint documented; domain allowlist may be required.

## Official or relevant documentation links
- https://dev.showpass.com/
- https://dev.showpass.com/api/01-public-api-introduction/
- https://dev.showpass.com/api/02-public-api-event-list-by-organization/

## Music Roadtrip usage recommendation
- Source role: `event_ticketing_platform`
- Recommended use now: provenance/ticket-link classification and QA.
- Do not add live API calls unless credentials, rate limits, and terms are explicitly reviewed.
- Do not hardcode credentials.
- Do not treat this as a primary event source unless a direct, permitted integration is approved.

## Mapping / cleanup notes
Map showpass.com as ticketing_provider=showpass. Good candidate for direct provider mapper if credentials/allowlist are obtained.

## Suggested Codex actions
- Add/extend provider taxonomy entry for `showpass`.
- Add domain detection patterns above.
- Add this provider to ticketing_provider detection.
- If API docs are official and useful, add mapper placeholders only; do not make live calls.
- Route unknown/incomplete direct integrations through the API Feed Review Workbench as manual JSON or provenance-only candidates.
