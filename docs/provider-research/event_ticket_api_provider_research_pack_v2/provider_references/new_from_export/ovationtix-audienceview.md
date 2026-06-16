# AudienceView Professional / OvationTix (`ovationtix-audienceview`)

## Why this provider is in the pack
This provider/platform appeared in the Music Roadtrip master export through ticket-link or website domains. It was not part of the first provider ZIP, or it needed more specific export-driven notes.

## Export domain evidence
- Grouped provider key: `ovationtix-audienceview`
- Domains/patterns: `ovationtix.com`, `ci.ovationtix.com`, `api.ovationtix.com`
- Ticket-link mentions in Concert rows: 140
- Website mentions in Concert rows: 28
- Total URL mentions in Concert rows: 168
- Sample URL: https://ci.ovationtix.com/36626

## API / docs status
Official public API reference found. Events/calendar endpoints expose future event data; scanning API requires auth.

## Official or relevant documentation links
- https://api.ovationtix.com/public/
- https://api.ovationtix.com/public/events_api.jsp
- https://api.ovationtix.com/public/calendar_api.jsp

## Music Roadtrip usage recommendation
- Source role: `event_ticketing_platform`
- Recommended use now: provenance/ticket-link classification and QA.
- Do not add live API calls unless credentials, rate limits, and terms are explicitly reviewed.
- Do not hardcode credentials.
- Do not treat this as a primary event source unless a direct, permitted integration is approved.

## Mapping / cleanup notes
Map ci.ovationtix.com to audienceview/ovationtix. Event data fields include performance IDs, production IDs, dates, times, availability, etc.

## Suggested Codex actions
- Add/extend provider taxonomy entry for `ovationtix-audienceview`.
- Add domain detection patterns above.
- Add this provider to ticketing_provider detection.
- If API docs are official and useful, add mapper placeholders only; do not make live calls.
- Route unknown/incomplete direct integrations through the API Feed Review Workbench as manual JSON or provenance-only candidates.
