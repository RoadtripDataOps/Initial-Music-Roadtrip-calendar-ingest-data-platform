# Prekindle provider reference

## Status

official_api_marketing_found_private_reference

## Why added

Observed 140 times in ticket/website fields.

## Official / reviewed source links

https://www.prekindle.com/features | https://www.prekindle.com/sell-tickets | https://prekindlesupport.freshdesk.com/support/solutions/articles/12000060864-explore-the-prekindle-dashboard

## Integration stance

Prekindle says it has a custom/open RESTful API, but full endpoint reference was not publicly retrievable. Treat as partner/private provider; connector disabled until docs are supplied.

## Codex implementation guidance

- Add provider/domain recognition for provenance and ticket-link QA.
- Do not make live API calls unless credentials and terms are explicitly supplied.
- Do not hardcode credentials.
- Treat event-specific URLs as candidate ticket/event links when classifier rules allow.
- Treat generic homepages, account pages, app links, checkout/session URLs, and affiliate-only redirects as suspicious until resolved.
- Preserve raw source/provider/domain information for future dedupe and cleanup.
