# Tockify provider reference

## Status

official_embedding_api_docs_found

## Why added

Observed 429 times, mostly Website URLs from CitySpark rows.

## Official / reviewed source links

https://tockify.com/i/docs | https://tockify.com/i/docs/api | https://tockify.com/i/docs/api/embed

## Integration stance

Tockify docs say the public API is primarily an embedding API, not a broad data extraction API. Tockify sources may expose embed pages or ICS-like subscription feeds; handle as calendar/source URL provider, not ticket API.

## Codex implementation guidance

- Add provider/domain recognition for provenance and ticket-link QA.
- Do not make live API calls unless credentials and terms are explicitly supplied.
- Do not hardcode credentials.
- Treat event-specific URLs as candidate ticket/event links when classifier rules allow.
- Treat generic homepages, account pages, app links, checkout/session URLs, and affiliate-only redirects as suspicious until resolved.
- Preserve raw source/provider/domain information for future dedupe and cleanup.
