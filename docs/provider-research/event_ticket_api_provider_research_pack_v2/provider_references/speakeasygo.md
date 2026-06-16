# SpeakeasyGo provider reference

## Status

no_public_api_reference_found

## Why added

Observed 244 times in ticket URLs.

## Official / reviewed source links

https://speakeasygo.com/partner/website-build | https://speakeasygo.com/partner/reservations

## Integration stance

SpeakeasyGo appears to provide website/reservation/ticketing links in the export. I did not find public API docs. Treat as ticket URL/provider domain only.

## Codex implementation guidance

- Add provider/domain recognition for provenance and ticket-link QA.
- Do not make live API calls unless credentials and terms are explicitly supplied.
- Do not hardcode credentials.
- Treat event-specific URLs as candidate ticket/event links when classifier rules allow.
- Treat generic homepages, account pages, app links, checkout/session URLs, and affiliate-only redirects as suspicious until resolved.
- Preserve raw source/provider/domain information for future dedupe and cleanup.
