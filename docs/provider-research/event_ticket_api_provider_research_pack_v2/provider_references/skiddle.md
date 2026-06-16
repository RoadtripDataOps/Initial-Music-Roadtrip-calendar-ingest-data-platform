# Skiddle provider reference

## Status

official_public_api_docs_found

## Why added

Observed 358 times in the master export, all in Tickets link (en), from JamBase rows.

## Official / reviewed source links

https://www.skiddle.com/api/ | https://github.com/Skiddle/web-api | https://www.skiddle.com/api/join.php

## Integration stance

Skiddle has public events API material and API key application flow. API terms mention source credit/brand logo requirements. Add disabled-by-default provider mapper and URL QA classification for skiddle.com event-specific pages.

## Codex implementation guidance

- Add provider/domain recognition for provenance and ticket-link QA.
- Do not make live API calls unless credentials and terms are explicitly supplied.
- Do not hardcode credentials.
- Treat event-specific URLs as candidate ticket/event links when classifier rules allow.
- Treat generic homepages, account pages, app links, checkout/session URLs, and affiliate-only redirects as suspicious until resolved.
- Preserve raw source/provider/domain information for future dedupe and cleanup.
