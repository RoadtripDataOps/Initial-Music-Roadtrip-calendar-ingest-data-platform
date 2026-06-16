# Master export origin/domain scan summary

Source file analyzed locally: `m1Kj8nPj_export.csv`.

The full export is **not included** in this research pack. This pack only includes aggregate counts and provider/domain references for Codex.

## High-level findings

- Total rows: 166,743
- Concert rows: 141,168
- Explicit `Data_source [developers]` values on Concert rows:
  - CitySpark: 84,163
  - Jambase: 56,876
  - blank: 129

The explicit ingestion provider field only identifies CitySpark/JamBase. The richer upstream/provider clues appear mostly in:

- `Tickets link (en)`
- `Website (en)`
- occasional image/affiliate URLs

## New provider/domain candidates not in the original pack

See `data/master_export_provider_candidates.csv` and `data/master_export_concert_domain_summary.csv`.

Newly added references include:

- OpenDate
- Event Vesta
- Universe
- Outhouse Tickets
- Skiddle
- VenuePilot
- Biletix
- TicketNetwork / Mercury Web Services
- Tockify
- Humanitix
- SimpleTix
- TicketLeap
- Showpass
- HoldMyTicket
- Eventnoire
- My805Tix
- 24tix
- Prekindle
- SpeakeasyGo
- OvationTix / AudienceView Professional
- Timely / Time.ly
- Afton Tickets

## How to use these findings

Do not assume each provider is an API integration target. Most should first be used for:

1. provenance/source-chain display,
2. ticket-link classification,
3. ticket-link repair/backfill strategy,
4. event dedupe support,
5. provider-specific QA warnings.

Use direct API integration only after provider docs, credentials, and usage terms are confirmed.

## Special notes

- `ticketmaster.evyy.net`, `ticketnetwork.lusg.net`, `etix.prf.hn`, and similar domains are affiliate/redirect style domains. They should not be treated as final ticket providers; resolve/classify them carefully.
- `aff=cityspark` remains a vendor/tracking QA flag, not an accepted source-of-truth marker.
- `Concert` remains an event record and must not be converted into a POI.
