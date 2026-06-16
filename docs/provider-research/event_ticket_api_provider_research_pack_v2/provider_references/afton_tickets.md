# Afton Tickets provider reference

## Status

no_public_api_reference_found

## Why added

Observed 55 times in ticket links.

## Official / reviewed source links

https://aftontickets.com/ | https://aftontickets.com/terms-and-conditions | https://help.aftontickets.com/knowledgebase/where-are-my-tickets/

## Integration stance

No public API docs were found. Treat Afton Tickets as a ticket-link/provenance provider until partner docs are supplied.

## Codex implementation guidance

- Add provider/domain recognition for provenance and ticket-link QA.
- Do not make live API calls unless credentials and terms are explicitly supplied.
- Do not hardcode credentials.
- Treat event-specific URLs as candidate ticket/event links when classifier rules allow.
- Treat generic homepages, account pages, app links, checkout/session URLs, and affiliate-only redirects as suspicious until resolved.
- Preserve raw source/provider/domain information for future dedupe and cleanup.
