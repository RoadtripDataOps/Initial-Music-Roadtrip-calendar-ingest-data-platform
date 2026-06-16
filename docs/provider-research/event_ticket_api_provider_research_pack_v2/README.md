# Event Ticket API Provider Research Pack

Generated: 2026-06-04

This ZIP is a Codex-ready research pack for adding external event/ticket providers to the Music Roadtrip ingestion POC.

It does **not** contain API keys. It does **not** ingest event data. It does **not** include full copyrighted vendor documentation dumps. Instead, it contains:

- provider-by-provider API documentation links
- endpoint/schema notes where publicly available
- compliance/access notes
- mapping implications for normalized Music Roadtrip Concert events
- Codex implementation guidance
- copies of the reference docs the user already provided in this chat

## Scope assumption

The user asked for “all event ticket API providers listed below,” but no explicit list followed in the prompt. I treated the scope as:

1. Providers already in the project: JamBase, CitySpark, Ticketmaster.
2. Provider slugs from the JamBase OpenAPI/event-data-source enum: AXS, DICE, Etix, Eventbrite, Eventim, Seated, See Tickets, Sofar Sounds, SeatGeek, SuiteHop, Tixr, Viagogo.
3. Additional providers from the ticket-link audit: TicketWeb and Bandsintown.
4. Related secondary-market provider: StubHub, because its public catalog docs closely mirror viagogo.

## Recommended Codex order

1. Import this pack into `docs/provider-research/`.
2. Read `codex/add-provider-docs-prompt.md`.
3. Update the provider registry with the provider statuses in `data/provider_index.json`.
4. Keep live provider calls off by default unless credentials and contractual permission exist.
5. Use provider mappers with manual JSON fixtures before live API calls.

## Critical data rule

Every normalized event candidate should be `Category = Concert` and `record_type = event`. Do not convert Concert events into POIs. Venues are containers that can display nested Concert events.


## V2 addendum: Master export origin scan

This version adds `export_scan/` and `provider_references/new_from_export/`.

The scan of the master export found that `Category=Concert` rows are explicitly marked by the `Data_source [developers]` field as `CitySpark`, `Jambase`, or blank, but ticket and website URLs reveal additional upstream/ticketing systems. These providers should primarily be used for provenance, ticket-link cleanup, and API-feed review—not automatic direct API ingestion.

Key new provider/domain groups include OpenDate, Universe, Skiddle, Humanitix, Ticket Tailor, Showpass, AudienceView/OvationTix, HoldMyTicket, TicketNetwork, Vivid Seats, Prekindle, TixTrack/Nliven, Zeffy, EventVesta, VenuePilot, Outhouse Tickets, Eventnoire, 24tix, SimpleTix, Tix.com, TicketLeap, Afton Tickets, InstantSeats, and affiliate/tracking networks.

See:
- `export_scan/master_export_origin_scan_summary.md`
- `export_scan/provider_candidate_counts.csv`
- `export_scan/concert_domain_counts.csv`
- `provider_references/new_from_export/README_NEW_FROM_EXPORT.md`
- `codex/add-export-origin-provenance-prompt.md`


## v2 Additions: Master export origin scan

This v2 pack adds a scan of the Music Roadtrip master export for Concert-row ticket/provider domains. It adds provider references for sources and ticket destinations observed in `Tickets link (en)` and `Website (en)` that were not in the first research pack.

New files:

- `MASTER_EXPORT_ORIGIN_SCAN.md`
- `data/master_export_provider_candidates.csv`
- `data/master_export_provider_candidates.json`
- `data/master_export_concert_domain_summary.csv`
- additional `provider_references/*.md` files for newly observed providers
- `codex/add-master-export-origin-providers-prompt.md`

The master export itself is not bundled.
