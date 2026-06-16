# TicketNetwork / Mercury Web Services provider reference

## Status

official_marketing_for_api_found_private_reference

## Why added

Observed 561 times, including ticketnetwork.lusg.net affiliate/redirect links and ticketnetwork.com destinations.

## Official / reviewed source links

https://mercurywebservices.com/ | https://corporate.ticketnetwork.com/products-services/ | https://www.ticketnetwork.com/en/affiliate-agreement

## Integration stance

TicketNetwork Mercury is described as an API-driven feed for inventory/ticket locking/order creation. Full schema likely partner/private. Treat TicketNetwork as secondary/marketplace/ticketing provider; no live connector without signed access.

## Codex implementation guidance

- Add provider/domain recognition for provenance and ticket-link QA.
- Do not make live API calls unless credentials and terms are explicitly supplied.
- Do not hardcode credentials.
- Treat event-specific URLs as candidate ticket/event links when classifier rules allow.
- Treat generic homepages, account pages, app links, checkout/session URLs, and affiliate-only redirects as suspicious until resolved.
- Preserve raw source/provider/domain information for future dedupe and cleanup.
