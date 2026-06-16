# Skiddle (`skiddle`)

## Why this provider is in the pack
This provider/platform appeared in the Music Roadtrip master export through ticket-link or website domains. It was not part of the first provider ZIP, or it needed more specific export-driven notes.

## Export domain evidence
- Grouped provider key: `skiddle`
- Domains/patterns: `skiddle.com`
- Ticket-link mentions in Concert rows: 358
- Website mentions in Concert rows: 0
- Total URL mentions in Concert rows: 358
- Sample URL: https://www.skiddle.com/whats-on/united-states/Middle-East-Club/The-Tartan-Specials-plus-special-guests/42376305/?utm_source=jambase

## API / docs status
Official API landing page and GitHub API documentation found. Requires API key; rate limits are monitored.

## Official or relevant documentation links
- https://www.skiddle.com/api/
- https://github.com/Skiddle/web-api
- https://github.com/Skiddle/skiddle-php-sdk

## Music Roadtrip usage recommendation
- Source role: `event_discovery_ticketing_platform`
- Recommended use now: provenance/ticket-link classification and QA.
- Do not add live API calls unless credentials, rate limits, and terms are explicitly reviewed.
- Do not hardcode credentials.
- Do not treat this as a primary event source unless a direct, permitted integration is approved.

## Mapping / cleanup notes
Export contained Skiddle links, often with utm_source=jambase. Treat as upstream/ticketing provider and classify event-specific URLs as platform_event.

## Suggested Codex actions
- Add/extend provider taxonomy entry for `skiddle`.
- Add domain detection patterns above.
- Add this provider to ticketing_provider detection.
- If API docs are official and useful, add mapper placeholders only; do not make live calls.
- Route unknown/incomplete direct integrations through the API Feed Review Workbench as manual JSON or provenance-only candidates.
