# Affiliate/tracking networks (`affiliate-networks`)

## Why this provider is in the pack
This provider/platform appeared in the Music Roadtrip master export through ticket-link or website domains. It was not part of the first provider ZIP, or it needed more specific export-driven notes.

## Export domain evidence
- Grouped provider key: `affiliate-networks`
- Domains/patterns: `ticketmaster.evyy.net`, `etix.prf.hn`, `awin1.com`, `ticketnetwork.lusg.net`, `vivid-seats.pxf.io`
- Ticket-link mentions in Concert rows: 0
- Website mentions in Concert rows: 0
- Total URL mentions in Concert rows: 0
- Sample URL: 

## API / docs status
These are generally not event providers; they are redirect/tracking domains.

## Official or relevant documentation links
- https://www.awin.com/us
- https://www.partnerize.com/
- https://impact.com/

## Music Roadtrip usage recommendation
- Source role: `affiliate_tracking`
- Recommended use now: provenance/ticket-link classification and QA.
- Do not add live API calls unless credentials, rate limits, and terms are explicitly reviewed.
- Do not hardcode credentials.
- Do not treat this as a primary event source unless a direct, permitted integration is approved.

## Mapping / cleanup notes
Preserve final destination provider when possible. Store redirect_chain/affiliate_chain flags. Do not treat affiliate domains as event source.

## Suggested Codex actions
- Add/extend provider taxonomy entry for `affiliate-networks`.
- Add domain detection patterns above.
- Add this provider to ticketing_provider detection.
- If API docs are official and useful, add mapper placeholders only; do not make live calls.
- Route unknown/incomplete direct integrations through the API Feed Review Workbench as manual JSON or provenance-only candidates.
