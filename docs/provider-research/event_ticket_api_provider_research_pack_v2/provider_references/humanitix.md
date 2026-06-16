# Humanitix provider reference

## Status

official_public_api_docs_found

## Why added

Observed 123 times, mainly events.humanitix.com event/ticket URLs.

## Official / reviewed source links

https://help.humanitix.com/en/articles/8888275-public-api-documentation | https://api.humanitix.com/v1/documentation | https://humanitix.stoplight.io/

## Integration stance

Humanitix has a public read-only API for event/order/ticket/tag information. Requires x-api-key header and docs mention a 200 requests/minute rate limit. Good candidate for partner-authorized event feed review; do not hardcode keys.

## Codex implementation guidance

- Add provider/domain recognition for provenance and ticket-link QA.
- Do not make live API calls unless credentials and terms are explicitly supplied.
- Do not hardcode credentials.
- Treat event-specific URLs as candidate ticket/event links when classifier rules allow.
- Treat generic homepages, account pages, app links, checkout/session URLs, and affiliate-only redirects as suspicious until resolved.
- Preserve raw source/provider/domain information for future dedupe and cleanup.
