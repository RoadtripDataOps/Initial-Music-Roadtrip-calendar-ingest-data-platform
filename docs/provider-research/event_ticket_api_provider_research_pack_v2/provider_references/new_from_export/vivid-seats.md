# Vivid Seats / SkyBox (`vivid-seats`)

## Why this provider is in the pack
This provider/platform appeared in the Music Roadtrip master export through ticket-link or website domains. It was not part of the first provider ZIP, or it needed more specific export-driven notes.

## Export domain evidence
- Grouped provider key: `vivid-seats`
- Domains/patterns: `vividseats.com`, `vivid-seats.pxf.io`, `vividseats.stoplight.io`, `skybox.vividseats.com`
- Ticket-link mentions in Concert rows: 0
- Website mentions in Concert rows: 53
- Total URL mentions in Concert rows: 53
- Sample URL: https://vivid-seats.pxf.io/c/258147/1017970/12730?prodsku=6488699&u=https%3A%2F%2Fwww.vividseats.com%2Fchoir-choir-choir-epic-80s-singalong-tickets-new-bedford-zeiterion-performing-arts-center-9-18-2026%2Fproduction%2F6488699%3Futm_term%3Dproduction-6488699&intsrc=CATF_7904

## API / docs status
Public docs portal exists but full docs may require account/login. SkyBox is broker-focused.

## Official or relevant documentation links
- https://vividseats.stoplight.io/
- https://skybox.vividseats.com/welcome.html
- https://brokersupport.vividseats.com/support/solutions/folders/1000219161

## Music Roadtrip usage recommendation
- Source role: `ticket_marketplace_or_affiliate`
- Recommended use now: provenance/ticket-link classification and QA.
- Do not add live API calls unless credentials, rate limits, and terms are explicitly reviewed.
- Do not hardcode credentials.
- Do not treat this as a primary event source unless a direct, permitted integration is approved.

## Mapping / cleanup notes
vivid-seats.pxf.io is an affiliate tracking domain. Treat as ticketing_provider=vivid-seats plus affiliate_chain flag.

## Suggested Codex actions
- Add/extend provider taxonomy entry for `vivid-seats`.
- Add domain detection patterns above.
- Add this provider to ticketing_provider detection.
- If API docs are official and useful, add mapper placeholders only; do not make live calls.
- Route unknown/incomplete direct integrations through the API Feed Review Workbench as manual JSON or provenance-only candidates.
