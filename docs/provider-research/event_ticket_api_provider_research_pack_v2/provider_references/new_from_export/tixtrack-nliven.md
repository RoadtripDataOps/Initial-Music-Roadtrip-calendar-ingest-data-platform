# TixTrack / Nliven (`tixtrack-nliven`)

## Why this provider is in the pack
This provider/platform appeared in the Music Roadtrip master export through ticket-link or website domains. It was not part of the first provider ZIP, or it needed more specific export-driven notes.

## Export domain evidence
- Grouped provider key: `tixtrack-nliven`
- Domains/patterns: `tixtrack.com`, `api.nliven.co`
- Ticket-link mentions in Concert rows: 39
- Website mentions in Concert rows: 0
- Total URL mentions in Concert rows: 39
- Sample URL: https://librarymusichall.tixtrack.com/tickets/series/benfolds2026

## API / docs status
Official webhooks documentation found; public event discovery API docs not found in this pass.

## Official or relevant documentation links
- https://tixtrack.com/
- https://api.nliven.co/apidocumentation/webhooks/
- https://support.tixtrack.com/hc/en-us/articles/21085138746765-Getting-Started-with-Nliven

## Music Roadtrip usage recommendation
- Source role: `enterprise_ticketing_platform`
- Recommended use now: provenance/ticket-link classification and QA.
- Do not add live API calls unless credentials, rate limits, and terms are explicitly reviewed.
- Do not hardcode credentials.
- Do not treat this as a primary event source unless a direct, permitted integration is approved.

## Mapping / cleanup notes
Map tixtrack/Nliven domains. Treat current data as ticket link/provenance only, not direct feed.

## Suggested Codex actions
- Add/extend provider taxonomy entry for `tixtrack-nliven`.
- Add domain detection patterns above.
- Add this provider to ticketing_provider detection.
- If API docs are official and useful, add mapper placeholders only; do not make live calls.
- Route unknown/incomplete direct integrations through the API Feed Review Workbench as manual JSON or provenance-only candidates.
