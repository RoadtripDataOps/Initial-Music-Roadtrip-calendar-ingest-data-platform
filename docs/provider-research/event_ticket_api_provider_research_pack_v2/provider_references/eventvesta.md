# Event Vesta provider reference

## Status

no_public_api_reference_found

## Why added

Observed 1,728 times in the master export across Tickets link and Website fields.

## Official / reviewed source links

https://eventvesta.com/ | https://www.eventvesta.com/learn-more

## Integration stance

Event Vesta appears as an event marketing/discovery/ticketing destination. I did not find public event API endpoint docs. Treat as ticket/calendar URL provider and link QA target only until partner docs are supplied.

## Codex implementation guidance

- Add provider/domain recognition for provenance and ticket-link QA.
- Do not make live API calls unless credentials and terms are explicitly supplied.
- Do not hardcode credentials.
- Treat event-specific URLs as candidate ticket/event links when classifier rules allow.
- Treat generic homepages, account pages, app links, checkout/session URLs, and affiliate-only redirects as suspicious until resolved.
- Preserve raw source/provider/domain information for future dedupe and cleanup.
