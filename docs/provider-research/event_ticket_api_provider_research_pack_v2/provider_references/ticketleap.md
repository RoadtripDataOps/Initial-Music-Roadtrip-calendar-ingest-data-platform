# TicketLeap provider reference

## Status

no_official_public_api_reference_found

## Why added

Observed 62 times, mainly events.ticketleap.com ticket URLs.

## Official / reviewed source links

https://www.ticketleap.com/ | https://support.ticketleap.com/glossary | https://github.com/connorskees/ticketleap

## Integration stance

No official public TicketLeap API reference was found. A third-party library exists and should not be considered official. Treat as ticket URL/provenance provider only.

## Codex implementation guidance

- Add provider/domain recognition for provenance and ticket-link QA.
- Do not make live API calls unless credentials and terms are explicitly supplied.
- Do not hardcode credentials.
- Treat event-specific URLs as candidate ticket/event links when classifier rules allow.
- Treat generic homepages, account pages, app links, checkout/session URLs, and affiliate-only redirects as suspicious until resolved.
- Preserve raw source/provider/domain information for future dedupe and cleanup.
