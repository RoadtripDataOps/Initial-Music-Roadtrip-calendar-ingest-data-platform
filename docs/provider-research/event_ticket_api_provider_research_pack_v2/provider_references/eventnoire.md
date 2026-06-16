# Eventnoire provider reference

## Status

no_public_api_reference_found

## Why added

Observed 190 times in ticket/website fields.

## Official / reviewed source links

https://www.eventnoire.com/learn-more | https://info.eventnoire.com/faqs/ | https://info.eventnoire.com/terms-and-conditions/

## Integration stance

Eventnoire is an event discovery/ticketing/registration platform. No public API reference was found. Treat Eventnoire URLs as platform_event ticket links if event-specific; no connector without docs.

## Codex implementation guidance

- Add provider/domain recognition for provenance and ticket-link QA.
- Do not make live API calls unless credentials and terms are explicitly supplied.
- Do not hardcode credentials.
- Treat event-specific URLs as candidate ticket/event links when classifier rules allow.
- Treat generic homepages, account pages, app links, checkout/session URLs, and affiliate-only redirects as suspicious until resolved.
- Preserve raw source/provider/domain information for future dedupe and cleanup.
