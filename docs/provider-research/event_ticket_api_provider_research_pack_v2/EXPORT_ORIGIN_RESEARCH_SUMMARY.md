# Export-Origin Provider Research Summary

Generated: 2026-06-04

## Purpose

This pack extends the original event ticket API provider research pack using the Music Roadtrip master export (`m1Kj8nPj_export.csv`). The export's explicit ingestion field only identifies CitySpark and JamBase, but ticket/website URLs expose downstream ticketing and event platforms that should be tracked as provenance, ticketing providers, affiliate/tracking domains, or future mapper candidates.

## Important interpretation

Most providers in `provider_references/new_from_export/` are **not recommended as direct integrations yet**. They should be added to the provider taxonomy and source-chain/ticket-link classifier first.

Use them for:

- upstream/source-of-source display
- ticketing provider detection
- ticket-link cleanup and repair strategy
- duplicate/dedupe confidence
- API feed review context
- future partner-doc placeholders

Do not use them for:

- live API calls without credentials and term review
- permanent ingestion from licensed providers
- bypassing existing admin review
- converting Concert records into POIs

## Export scan headline

- Total export rows scanned: 166,743
- Concert rows scanned: 141,168
- Explicit Concert `Data_source [developers]` values:
  - CitySpark: 84,163
  - Jambase: 56,876
  - blank: 129
- `Source Record ID`, `event_id (Jambase)`, and `venue_id (Jambase)` were blank across Concert rows in this export.
- Ticket and website URLs exposed additional provider origins/domains.

## New high-priority provider/domain groups

These had meaningful presence in the export and should be added to the taxonomy:

- OpenDate
- Universe
- Skiddle
- Humanitix
- Ticket Tailor
- Showpass
- AudienceView / OvationTix
- HoldMyTicket
- TicketNetwork / Mercury Web Services
- Vivid Seats / SkyBox
- Prekindle
- TixTrack / Nliven
- Zeffy
- EventVesta
- Outhouse Tickets
- VenuePilot
- Biletix
- SpeakeasyGo
- Eventnoire
- My805Tix / 805Tix
- 24tix
- SimpleTix
- Tix.com
- TicketLeap
- Afton Tickets
- InstantSeats
- Affiliate/tracking networks

## Files added

- `export_scan/master_export_origin_scan_summary.md`
- `export_scan/concert_domain_counts.csv`
- `export_scan/provider_candidate_counts.csv`
- `export_scan/provider_candidate_counts.json`
- `provider_references/new_from_export/*.md`
- `codex/add-export-origin-provenance-prompt.md`

## Relationship to existing docs

JamBase already exposes third-party event, artist, and venue data-source slugs. The exported downstream URLs confirm why the Music Roadtrip app needs source-chain fields such as:

- ingestion_provider
- upstream_event_source
- ticketing_provider
- affiliate/tracking provider
- source_chain_json
- ticket_link_classification
- ticket_link_repair_strategy

The existing ticket-link audit already recommends JamBase offer URL backfill, CitySpark ticketUrl preference, and rejection/flagging of generic platform/app links.
