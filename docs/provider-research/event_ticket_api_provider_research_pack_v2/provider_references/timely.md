# Timely / Time.ly calendar provider reference

## Status

no_public_data_api_reference_found

## Why added

Observed 114 times, mostly events.timely.fun website URLs.

## Official / reviewed source links

https://time.ly/solutions/all-in-one-events-calendar-wordpress-plugin/ | https://es.wordpress.org/plugins/event-calendar-timely/

## Integration stance

Timely is a calendar/event plugin/platform. No public data API docs were found. Treat as calendar source/HTML/ICS candidate rather than ticket API provider.

## Codex implementation guidance

- Add provider/domain recognition for provenance and ticket-link QA.
- Do not make live API calls unless credentials and terms are explicitly supplied.
- Do not hardcode credentials.
- Treat event-specific URLs as candidate ticket/event links when classifier rules allow.
- Treat generic homepages, account pages, app links, checkout/session URLs, and affiliate-only redirects as suspicious until resolved.
- Preserve raw source/provider/domain information for future dedupe and cleanup.
