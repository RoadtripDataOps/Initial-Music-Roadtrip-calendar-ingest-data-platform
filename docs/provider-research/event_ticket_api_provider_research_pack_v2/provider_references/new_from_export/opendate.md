# OpenDate (`opendate`)

## Why this provider is in the pack
This provider/platform appeared in the Music Roadtrip master export through ticket-link or website domains. It was not part of the first provider ZIP, or it needed more specific export-driven notes.

## Export domain evidence
- Grouped provider key: `opendate`
- Domains/patterns: `app.opendate.io`, `opendate.io`
- Ticket-link mentions in Concert rows: 966
- Website mentions in Concert rows: 20
- Total URL mentions in Concert rows: 986
- Sample URL: https://app.opendate.io/e/the-timber-bridges-w-uncle-march-01-2026-668872

## API / docs status
Official developer page found; API access appears tied to platform/account tier.

## Official or relevant documentation links
- https://app.opendate.io/developers
- https://www.opendate.io/pricing

## Music Roadtrip usage recommendation
- Source role: `event_ticketing_platform`
- Recommended use now: provenance/ticket-link classification and QA.
- Do not add live API calls unless credentials, rate limits, and terms are explicitly reviewed.
- Do not hardcode credentials.
- Do not treat this as a primary event source unless a direct, permitted integration is approved.

## Mapping / cleanup notes
Export contained app.opendate.io ticket links. Treat as ticketing_provider/upstream_event_source; do not build live connector until credentials and terms are reviewed.

## Suggested Codex actions
- Add/extend provider taxonomy entry for `opendate`.
- Add domain detection patterns above.
- Add this provider to ticketing_provider detection.
- If API docs are official and useful, add mapper placeholders only; do not make live calls.
- Route unknown/incomplete direct integrations through the API Feed Review Workbench as manual JSON or provenance-only candidates.
