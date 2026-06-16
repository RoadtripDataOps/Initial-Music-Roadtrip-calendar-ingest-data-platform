# Universe provider reference

## Status

official_public_api_docs_found

## Why added

Observed 577 times in master export ticket/website URLs. Universe is also a source within Ticketmaster Discovery.

## Official / reviewed source links

https://developers.universe.com/ | https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/ | https://developer.ticketmaster.com/products-and-docs/apis/discovery-feed/

## Integration stance

Universe has public developer docs with OAuth, GraphQL, and REST references. Ticketmaster Discovery states it sources content from platforms including Universe. Treat Universe as both standalone provider reference and Ticketmaster-source provenance. Keep live connector disabled until credentials/terms are reviewed.

## Codex implementation guidance

- Add provider/domain recognition for provenance and ticket-link QA.
- Do not make live API calls unless credentials and terms are explicitly supplied.
- Do not hardcode credentials.
- Treat event-specific URLs as candidate ticket/event links when classifier rules allow.
- Treat generic homepages, account pages, app links, checkout/session URLs, and affiliate-only redirects as suspicious until resolved.
- Preserve raw source/provider/domain information for future dedupe and cleanup.
