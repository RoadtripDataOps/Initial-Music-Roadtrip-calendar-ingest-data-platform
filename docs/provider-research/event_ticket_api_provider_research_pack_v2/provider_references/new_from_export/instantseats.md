# InstantSeats (`instantseats`)

## Why this provider is in the pack
This provider/platform appeared in the Music Roadtrip master export through ticket-link or website domains. It was not part of the first provider ZIP, or it needed more specific export-driven notes.

## Export domain evidence
- Grouped provider key: `instantseats`
- Domains/patterns: `instantseats.com`
- Ticket-link mentions in Concert rows: 30
- Website mentions in Concert rows: 20
- Total URL mentions in Concert rows: 50
- Sample URL: https://www.instantseats.com/?fuseaction=home.artist&VenueID=514&artistid=37839&_gl=1*1lmvws8*_gcl_au*MTI0ODExNTk3LjE3NjU2NjU4OTA.*_ga*ODM4NTc1MzM1LjE3NDk1ODQ4NjE.*_ga_XFCVF897QY*czE3Njg5NDUwNTIkbzE3MyRnMSR0MTc2ODk0NTc0NSRqNjAkbDAkaDA.

## API / docs status
Official product pages found; no public API docs found in this pass.

## Official or relevant documentation links
- https://www.instantseats.com/selltix/news.cfm

## Music Roadtrip usage recommendation
- Source role: `event_ticketing_platform`
- Recommended use now: provenance/ticket-link classification and QA.
- Do not add live API calls unless credentials, rate limits, and terms are explicitly reviewed.
- Do not hardcode credentials.
- Do not treat this as a primary event source unless a direct, permitted integration is approved.

## Mapping / cleanup notes
Treat as ticketing provider based on URL only.

## Suggested Codex actions
- Add/extend provider taxonomy entry for `instantseats`.
- Add domain detection patterns above.
- Add this provider to ticketing_provider detection.
- If API docs are official and useful, add mapper placeholders only; do not make live calls.
- Route unknown/incomplete direct integrations through the API Feed Review Workbench as manual JSON or provenance-only candidates.
