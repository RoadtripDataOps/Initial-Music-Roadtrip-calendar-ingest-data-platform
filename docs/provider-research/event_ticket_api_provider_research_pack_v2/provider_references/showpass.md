# Showpass provider reference

## Status

official_public_api_docs_found

## Why added

Observed 91 times in ticket/website URLs.

## Official / reviewed source links

https://dev.showpass.com/ | https://dev.showpass.com/api/01-public-api-introduction/ | https://dev.showpass.com/api/02-public-api-event-list-by-organization/

## Integration stance

Showpass has public developer docs. The Discovery API endpoint is https://www.showpass.com/api/public/discovery/ and supports programmatic access to experience/event data, with domain allowlisting noted for successful requests. Good candidate for provider mapper if authorized.

## Codex implementation guidance

- Add provider/domain recognition for provenance and ticket-link QA.
- Do not make live API calls unless credentials and terms are explicitly supplied.
- Do not hardcode credentials.
- Treat event-specific URLs as candidate ticket/event links when classifier rules allow.
- Treat generic homepages, account pages, app links, checkout/session URLs, and affiliate-only redirects as suspicious until resolved.
- Preserve raw source/provider/domain information for future dedupe and cleanup.
