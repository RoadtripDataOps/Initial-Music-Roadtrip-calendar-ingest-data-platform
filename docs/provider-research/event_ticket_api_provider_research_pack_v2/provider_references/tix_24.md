# 24tix provider reference

## Status

no_public_api_reference_found

## Why added

Observed 172 times, mostly Website URLs.

## Official / reviewed source links

https://www.24tix.com/ | https://www.24tix.com/help | https://www.24tix.com/terms

## Integration stance

No public API reference was found. 24tix help/terms confirm ticketing/resale workflows. Treat as ticketing provider/domain classification only.

## Codex implementation guidance

- Add provider/domain recognition for provenance and ticket-link QA.
- Do not make live API calls unless credentials and terms are explicitly supplied.
- Do not hardcode credentials.
- Treat event-specific URLs as candidate ticket/event links when classifier rules allow.
- Treat generic homepages, account pages, app links, checkout/session URLs, and affiliate-only redirects as suspicious until resolved.
- Preserve raw source/provider/domain information for future dedupe and cleanup.
