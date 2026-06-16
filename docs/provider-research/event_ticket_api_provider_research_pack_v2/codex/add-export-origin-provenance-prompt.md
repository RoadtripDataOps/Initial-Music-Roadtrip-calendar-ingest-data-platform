# Codex Prompt — Add Export-Discovered Providers to Provenance Layer

We scanned the Music Roadtrip master export and found that explicit `Data_source [developers]` values on Concert rows are only `CitySpark`, `Jambase`, or blank. However, ticket/website domains expose additional upstream ticketing/event systems.

Important:
- Do not make live API calls in this milestone.
- Do not add or hardcode API keys.
- Do not enable live CitySpark calls or public bypasses.
- CitySpark is a paid licensed vendor API feed; keep live calls off until
  credentials and configuration are added, and keep provider records behind
  API Feed Review before app use.
- Concert records are events and must never be converted into POIs.
- These providers are mostly for provenance, ticket-link cleanup, API feed review, and dedupe signals.

Use these files:
- `export_scan/master_export_origin_scan_summary.md`
- `export_scan/provider_candidate_counts.csv`
- `export_scan/concert_domain_counts.csv`
- `provider_references/new_from_export/README_NEW_FROM_EXPORT.md`
- `provider_references/new_from_export/*.md`

## Goal
Extend the API Feed Review Workbench and provenance/ticket-link classifier so it can recognize upstream/ticketing providers discovered in the master export.

## New provider/domain groups to add to source taxonomy

Add provider taxonomy entries for:

- `opendate`
- `universe`
- `skiddle`
- `humanitix`
- `ticket-tailor`
- `showpass`
- `ovationtix-audienceview`
- `holdmyticket`
- `ticketnetwork`
- `vivid-seats`
- `prekindle`
- `tixtrack-nliven`
- `zeffy`
- `eventvesta`
- `outhouse-tickets`
- `venuepilot`
- `biletix`
- `speakeasygo`
- `eventnoire`
- `my805tix`
- `twentyfour-tix`
- `simpletix`
- `tix-com`
- `ticketleap`
- `afton-tickets`
- `instantseats`
- `affiliate-networks`

For each provider, include:
- display name
- known domain patterns
- source role: ticketing_provider, upstream_event_source, affiliate_tracking, or event_marketing_platform
- docs status
- direct connector status: disabled by default
- cleanup notes

## Domain detection rules

Recognize these patterns at minimum:

- `app.opendate.io`, `opendate.io` → `opendate`
- `universe.com`, `developers.universe.com` → `universe`
- `skiddle.com` → `skiddle`
- `humanitix.com`, `events.humanitix.com`, `api.humanitix.com` → `humanitix`
- `tickettailor.com`, `buytickets.at`, `api.tickettailor.com` → `ticket-tailor`
- `showpass.com` → `showpass`
- `ovationtix.com`, `ci.ovationtix.com`, `api.ovationtix.com` → `ovationtix-audienceview`
- `holdmyticket.com` → `holdmyticket`
- `ticketnetwork.com`, `ticketnetwork.lusg.net`, `mercurywebservices.com` → `ticketnetwork`
- `vividseats.com`, `vivid-seats.pxf.io`, `vividseats.stoplight.io`, `skybox.vividseats.com` → `vivid-seats`
- `prekindle.com` → `prekindle`
- `tixtrack.com`, `api.nliven.co`, `librarymusichall.tixtrack.com` → `tixtrack-nliven`
- `zeffy.com`, `support.zeffy.com` → `zeffy`
- `eventvesta.com` → `eventvesta`
- `outhousetickets.com`, `events.outhousetickets.com` → `outhouse-tickets`
- `venuepilot.com`, `tickets.venuepilot.com` → `venuepilot`
- `biletix.com` → `biletix`
- `speakeasygo.com` → `speakeasygo`
- `eventnoire.com`, `events.eventnoire.com` → `eventnoire`
- `my805tix.com`, `805tix.com` → `my805tix`
- `24tix.com` → `twentyfour-tix`
- `simpletix.com` → `simpletix`
- `tix.com` → `tix-com`
- `ticketleap.com`, `events.ticketleap.com` → `ticketleap`
- `aftontickets.com`, `aftonshows.com` → `afton-tickets`
- `instantseats.com` → `instantseats`
- `ticketmaster.evyy.net`, `etix.prf.hn`, `awin1.com`, `ticketnetwork.lusg.net`, `vivid-seats.pxf.io` → affiliate/tracking chain flags as applicable

## API workbench behavior

Update API feed review record detail and event preview provenance panels to show:
- ingestion_provider
- upstream_event_source
- ticketing_provider
- ticketing_provider_domain
- source chain
- affiliate/tracking domain flag
- ticket-link classification
- ticket-link repair strategy
- docs status for detected provider

## Ticket-link cleanup behavior

Do not trust a provider domain blindly. A link can be:
- direct
- redirect_or_handoff
- platform_event
- platform_generic_or_app
- non_ticket
- suspicious
- unresolved

Continue to reject or flag:
- Eventbrite `/checkout-external`
- generic DICE/link.dice.fm app handoff links
- Ticketmaster homepages/artist pages/generic pages
- session/cart-like URLs
- vendor/affiliate tracking that hides the final destination
- `aff=cityspark` as a legacy vendor marker

## Provider docs integration

Add provider docs status into admin provider cards and mapping reference page. Providers with official public docs can have mapper placeholders, but no live connectors.

Providers with no public docs should be provenance-only and disabled as direct connectors.

## Tests

Add tests for:
- each new provider domain maps to the expected provider key
- affiliate domains set affiliate/tracking flags
- provider docs status renders in API feed review
- API feed record detail shows source chain for newly detected providers
- ticket link classifier preserves provider domain but does not auto-trust generic/app links
- no live API calls are added
- no API keys are hardcoded
- CitySpark is handled like JamBase as a paid licensed vendor feed
- Concert events remain events and are not converted into POIs

## Done when

- New export-discovered providers are recognized by domain.
- API feed review displays source chain/provenance for these providers.
- Preview/admin event detail surfaces ticketing provider and upstream provider.
- Provider cards/reference docs show docs status.
- Tests pass.
- Ruff passes.
- Mypy passes.
