# OvationTix / AudienceView Professional provider reference

## Status

no_public_api_reference_found

## Why added

Observed 168 times, mostly ci.ovationtix.com ticket links.

## Official / reviewed source links

https://ovationtix.com/ | https://audienceview.com/

## Integration stance

OvationTix is now AudienceView Professional. Public pages describe ticketing, CRM, events, and fundraising, but no public endpoint docs were found. Treat as ticketing provider and partner/private potential.

## Codex implementation guidance

- Add provider/domain recognition for provenance and ticket-link QA.
- Do not make live API calls unless credentials and terms are explicitly supplied.
- Do not hardcode credentials.
- Treat event-specific URLs as candidate ticket/event links when classifier rules allow.
- Treat generic homepages, account pages, app links, checkout/session URLs, and affiliate-only redirects as suspicious until resolved.
- Preserve raw source/provider/domain information for future dedupe and cleanup.
