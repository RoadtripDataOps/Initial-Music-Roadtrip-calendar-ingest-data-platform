# My805Tix provider reference

## Status

no_public_api_reference_found

## Why added

Observed 161 times in ticket/website fields.

## Official / reviewed source links

https://www.my805tix.com/

## Integration stance

No public API docs were found. My805Tix appears as a regional ticketing/event link provider in the data. Use link-quality/provenance classification only.

## Codex implementation guidance

- Add provider/domain recognition for provenance and ticket-link QA.
- Do not make live API calls unless credentials and terms are explicitly supplied.
- Do not hardcode credentials.
- Treat event-specific URLs as candidate ticket/event links when classifier rules allow.
- Treat generic homepages, account pages, app links, checkout/session URLs, and affiliate-only redirects as suspicious until resolved.
- Preserve raw source/provider/domain information for future dedupe and cleanup.
