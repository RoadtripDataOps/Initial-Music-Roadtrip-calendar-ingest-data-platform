# VenuePilot provider reference

## Status

no_public_api_reference_found

## Why added

Observed 335 times in the export, primarily tickets.venuepilot.com links.

## Official / reviewed source links

https://www.venuepilot.com/ | https://support.venuepilot.co/knowledge/from-hold-to-tickets-sold

## Integration stance

VenuePilot is an event management/ticketing system with public calendar/widgets and ticketing URLs, but no public API reference was found. Treat as ticketing provider and calendar/source platform; connector disabled until docs/payloads are supplied.

## Codex implementation guidance

- Add provider/domain recognition for provenance and ticket-link QA.
- Do not make live API calls unless credentials and terms are explicitly supplied.
- Do not hardcode credentials.
- Treat event-specific URLs as candidate ticket/event links when classifier rules allow.
- Treat generic homepages, account pages, app links, checkout/session URLs, and affiliate-only redirects as suspicious until resolved.
- Preserve raw source/provider/domain information for future dedupe and cleanup.
