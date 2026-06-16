# Humanitix (`humanitix`)

## Why this provider is in the pack
This provider/platform appeared in the Music Roadtrip master export through ticket-link or website domains. It was not part of the first provider ZIP, or it needed more specific export-driven notes.

## Export domain evidence
- Grouped provider key: `humanitix`
- Domains/patterns: `humanitix.com`, `events.humanitix.com`, `api.humanitix.com`
- Ticket-link mentions in Concert rows: 82
- Website mentions in Concert rows: 41
- Total URL mentions in Concert rows: 123
- Sample URL: https://events.humanitix.com/musical-improv-drop-in-workshop2026

## API / docs status
Official public read-only API docs found. API can fetch event, order, ticket, and tag information; x-api-key header required.

## Official or relevant documentation links
- https://help.humanitix.com/en/articles/8888275-public-api-documentation
- https://api.humanitix.com/v1/documentation
- https://humanitix.stoplight.io/

## Music Roadtrip usage recommendation
- Source role: `event_ticketing_platform`
- Recommended use now: provenance/ticket-link classification and QA.
- Do not add live API calls unless credentials, rate limits, and terms are explicitly reviewed.
- Do not hardcode credentials.
- Do not treat this as a primary event source unless a direct, permitted integration is approved.

## Mapping / cleanup notes
Treat Humanitix URLs as ticketing_provider=humanitix. Consider mapper later if directly authorized.

## Suggested Codex actions
- Add/extend provider taxonomy entry for `humanitix`.
- Add domain detection patterns above.
- Add this provider to ticketing_provider detection.
- If API docs are official and useful, add mapper placeholders only; do not make live calls.
- Route unknown/incomplete direct integrations through the API Feed Review Workbench as manual JSON or provenance-only candidates.
