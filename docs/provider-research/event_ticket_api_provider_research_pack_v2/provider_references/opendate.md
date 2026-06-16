# OpenDate provider reference

## Status

official_public_api_docs_found

## Why added

Observed 986 times in the master export, mostly in Tickets link (en).

## Official / reviewed source links

https://app.opendate.io/developers | https://opendate.readme.io/reference/get_api-v2-eventbrite-events-id-find-confirm-1

## Integration stance

Opendate exposes developer docs for its API and event/ticketing/fan-engagement/financial features. Treat as ticketing/event management provider. Add disabled-by-default provider registry entry; use manual JSON fixtures first; no live calls without keys.

## Codex implementation guidance

- Add provider/domain recognition for provenance and ticket-link QA.
- Do not make live API calls unless credentials and terms are explicitly supplied.
- Do not hardcode credentials.
- Treat event-specific URLs as candidate ticket/event links when classifier rules allow.
- Treat generic homepages, account pages, app links, checkout/session URLs, and affiliate-only redirects as suspicious until resolved.
- Preserve raw source/provider/domain information for future dedupe and cleanup.
