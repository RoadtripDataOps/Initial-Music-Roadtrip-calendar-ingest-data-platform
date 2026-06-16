# Biletix provider reference

## Status

no_official_public_api_docs_found

## Why added

Observed 290 times in JamBase ticket links.

## Official / reviewed source links

https://www.biletix.com/ | https://www.biletix.com/wbtxapi/api/v1/siteMap/index | https://apify.com/bossula/biletix-crawler/api

## Integration stance

Biletix exposes sitemap-like endpoints, but I did not find official public API docs. Third-party crawler/API docs exist via Apify; do not treat those as approved official provider docs. Use as ticket URL/provider-domain classification only.

## Codex implementation guidance

- Add provider/domain recognition for provenance and ticket-link QA.
- Do not make live API calls unless credentials and terms are explicitly supplied.
- Do not hardcode credentials.
- Treat event-specific URLs as candidate ticket/event links when classifier rules allow.
- Treat generic homepages, account pages, app links, checkout/session URLs, and affiliate-only redirects as suspicious until resolved.
- Preserve raw source/provider/domain information for future dedupe and cleanup.
