# TicketNetwork / Mercury Web Services (`ticketnetwork`)

## Why this provider is in the pack
This provider/platform appeared in the Music Roadtrip master export through ticket-link or website domains. It was not part of the first provider ZIP, or it needed more specific export-driven notes.

## Export domain evidence
- Grouped provider key: `ticketnetwork`
- Domains/patterns: `ticketnetwork.com`, `ticketnetwork.lusg.net`, `mercurywebservices.com`
- Ticket-link mentions in Concert rows: 29
- Website mentions in Concert rows: 532
- Total URL mentions in Concert rows: 561
- Sample URL: https://ticketnetwork.lusg.net/c/258147/132208/2322?prodsku=7260920&u=https%3A%2F%2Fwww.ticketnetwork.com%2Fen%2Fp%2F7260920&intsrc=CATF_896

## API / docs status
Official API-driven product pages found; full API docs appear partner-gated.

## Official or relevant documentation links
- https://mercurywebservices.com/
- https://corporate.ticketnetwork.com/products-services/
- https://www.ticketnetwork.com/en/affiliate-agreement

## Music Roadtrip usage recommendation
- Source role: `ticket_marketplace_or_affiliate`
- Recommended use now: provenance/ticket-link classification and QA.
- Do not add live API calls unless credentials, rate limits, and terms are explicitly reviewed.
- Do not hardcode credentials.
- Do not treat this as a primary event source unless a direct, permitted integration is approved.

## Mapping / cleanup notes
ticketnetwork.lusg.net is an affiliate/tracking domain. Treat as ticketing_provider=ticketnetwork plus affiliate_chain flag.

## Suggested Codex actions
- Add/extend provider taxonomy entry for `ticketnetwork`.
- Add domain detection patterns above.
- Add this provider to ticketing_provider detection.
- If API docs are official and useful, add mapper placeholders only; do not make live calls.
- Route unknown/incomplete direct integrations through the API Feed Review Workbench as manual JSON or provenance-only candidates.
