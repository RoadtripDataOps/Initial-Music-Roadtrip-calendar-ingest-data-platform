# SimpleTix provider reference

## Status

no_complete_public_api_reference_found

## Why added

Observed 87 times in ticket/website fields.

## Official / reviewed source links

https://www.simpletix.com/ | https://help.simpletix.com/docs/integrations/connect-simpletix-to-zapier | https://apps.make.com/simpletix

## Integration stance

SimpleTix is an event ticketing/registration platform. Public integration docs exist for Zapier/Make-style workflows, but complete public API docs were not found. Treat as link/provenance provider only until partner docs are supplied.

## Codex implementation guidance

- Add provider/domain recognition for provenance and ticket-link QA.
- Do not make live API calls unless credentials and terms are explicitly supplied.
- Do not hardcode credentials.
- Treat event-specific URLs as candidate ticket/event links when classifier rules allow.
- Treat generic homepages, account pages, app links, checkout/session URLs, and affiliate-only redirects as suspicious until resolved.
- Preserve raw source/provider/domain information for future dedupe and cleanup.
