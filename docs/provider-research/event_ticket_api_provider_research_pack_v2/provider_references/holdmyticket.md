# HoldMyTicket provider reference

## Status

official_public_event_api_docs_found

## Why added

Observed 148 times in ticket/website URLs.

## Official / reviewed source links

https://docs.holdmyticket.com/doc/434/events | https://docs.holdmyticket.com/doc/725/getting-started | https://sell.holdmyticket.com/web-design-services-event-ticketing

## Integration stance

HoldMyTicket has public docs for a read-only event API that returns published events by API key. Treat as potential authorized feed provider; no live calls until credentials/permissions are available.

## Codex implementation guidance

- Add provider/domain recognition for provenance and ticket-link QA.
- Do not make live API calls unless credentials and terms are explicitly supplied.
- Do not hardcode credentials.
- Treat event-specific URLs as candidate ticket/event links when classifier rules allow.
- Treat generic homepages, account pages, app links, checkout/session URLs, and affiliate-only redirects as suspicious until resolved.
- Preserve raw source/provider/domain information for future dedupe and cleanup.
