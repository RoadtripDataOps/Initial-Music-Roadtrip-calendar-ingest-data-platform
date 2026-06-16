# Event Ticket API Provider Research Summary

Generated: 2026-06-04

## Bottom line

There are three useful provider categories for Music Roadtrip:

1. **Public or semi-public event APIs**: JamBase, Ticketmaster Discovery, Eventbrite, Bandsintown, viagogo/StubHub catalog, SeatGeek.
2. **Partner/client APIs**: AXS, DICE, Etix, Eventim/See Tickets, Seated, TicketWeb, Tixr.
3. **No public API docs found / link-only until partner docs**: Sofar Sounds, SuiteHop, parts of AXS/Etix/See Tickets.

## Recommended implementation priority

1. JamBase mapper hardening
2. Ticketmaster Discovery/classification mapper
3. Eventbrite manual JSON mapper
4. Bandsintown artist-event mapper
5. viagogo/StubHub catalog mapper review
6. SeatGeek only after terms review
7. Partner-only providers only after credentials/docs

## Ticket-link strategy

Use your existing ticket-link audit as source of truth:

- JamBase: prefer `offers[].url`, primary then secondary.
- CitySpark: prefer `ticketUrl`.
- Eventbrite: reject `/checkout-external` as final link.
- DICE: treat generic `link.dice.fm` handoff as suspicious unless event-specific.
- Ticketmaster: reject homepages, artist pages, generic pages; keep event-specific pages.
- Tixr/AXS/Etix/TicketWeb/SeeTickets/Bandsintown: keep event-specific ticket pages; flag generic pages.

## Provider status matrix

| Provider | Status | Primary action |
|---|---|---|
| AXS | `partner_private_public_docs_limited` | Add provider registry entry as disabled/private_by_default. Support manual JSON fixture mapping only after contract docs are added. Do not scrape AXS or use third-party scraper APIs by default. |
| Bandsintown | `official_public_artist_api_docs_found` | Add as artist_event_feed provider. Useful for artist-specific backfill/enrichment and ticket link lookup. Normalize events to Concert candidates; preserve offers[] and Bandsintown event URL. |
| DICE.fm | `official_partner_graphql_docs_found` | Add as disabled/private_by_default. Accept manual JSON/GraphQL fixture review. Treat generic link.dice.fm handoff links as suspicious/generic unless event-specific target is proven. |
| Etix | `partner_private_docs_limited` | Add as disabled/private_by_default. Support URL QA classification and manual JSON fixture mapping only after partner docs are provided. |
| Eventbrite | `official_public_api_docs_found` | Add eventbrite provider. Use manual JSON first. Normalize event objects to Concert only when music relevance is confirmed. Reject /checkout-external as final ticket link per existing ticket-link audit. |
| EVENTIM / See Tickets US Affiliate Network | `official_affiliate_feed_article_found` | Add eventim_affiliate provider disabled until credentials/docs. Support feed/manual fixture review. Preserve affiliate tracking separately from clean canonical ticket URL. |
| Seated / CM.com Ticketing | `official_public_reference_found` | Add provider registry entry as partner_ticketing_reporting. Good for partner reporting, event metadata and ticket status. Use event/venue endpoints if credentialed. |
| See Tickets | `partner_private_docs_limited` | Add disabled/private_by_default. Treat See Tickets URLs as ticket links. Use manual JSON only if docs/payloads are supplied. |
| TicketWeb | `official_integration_pages_found_private_reference` | Add disabled/private_by_default. Recognize TicketWeb event URLs as ticket links. Implement connector only after official API credentials/docs are provided. |
| SeatGeek | `official_developer_portal_found_js_docs` | Add provider as disabled until terms/credential review. If enabled, map events/performers/venues; preserve attribution and comply with storage/download restrictions. |
| Sofar Sounds | `no_official_event_api_docs_found` | Add as no_connector. Support only client-submitted Sofar calendar URLs or manual JSON if partner docs/payloads are supplied. |
| SuiteHop | `no_public_api_docs_found` | Add as no_connector / link-only provider unless partner docs are supplied. |
| Tixr | `official_public_apiary_docs_found` | Add as disabled/private_by_default with manual JSON fixture support. Recognize tixr.com event-specific URLs as platform_event ticket links per audit logic. |
| viagogo | `official_public_api_docs_found` | Add provider as partner_catalog_feed disabled until terms/credentials. Strong event_id/provider ID can support dedupe. Separate catalog from inventory/sales APIs. |
| StubHub | `official_public_api_docs_found_related` | Add as related optional provider if you plan to use StubHub directly. Otherwise keep as related viagogo-family docs for mapping comparison. |
| Ticketmaster | `existing_docs_plus_official_public_docs` | You already have Ticketmaster classification docs. Use Discovery as event source if configured, Partner API only if contractually allowed. Music segment positive signal; non-music low relevance. |
| JamBase | `existing_docs_present` | Already implemented or staged. Use as primary provider mapper reference. |
| CitySpark | `licensed_vendor_feed_review` | Paid licensed vendor API feed for Music Roadtrip, handled like JamBase as a licensed provider feed. Live calls remain off until credentials and configuration are added. |
