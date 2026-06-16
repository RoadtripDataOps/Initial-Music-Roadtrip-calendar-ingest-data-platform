# Zeffy (`zeffy`)

## Why this provider is in the pack
This provider/platform appeared in the Music Roadtrip master export through ticket-link or website domains. It was not part of the first provider ZIP, or it needed more specific export-driven notes.

## Export domain evidence
- Grouped provider key: `zeffy`
- Domains/patterns: `zeffy.com`, `support.zeffy.com`
- Ticket-link mentions in Concert rows: 37
- Website mentions in Concert rows: 9
- Total URL mentions in Concert rows: 46
- Sample URL: https://www.zeffy.com/en-US/ticketing/2026-naacp-colorado-springs-juneteenth-prayer-breakfast

## API / docs status
Official API docs found, but resources are payments/contacts/campaigns rather than event discovery.

## Official or relevant documentation links
- https://support.zeffy.com/get-started-with-the-zeffy-api-yourg
- https://www.zeffy.com/integration/api

## Music Roadtrip usage recommendation
- Source role: `fundraising_event_ticketing_platform`
- Recommended use now: provenance/ticket-link classification and QA.
- Do not add live API calls unless credentials, rate limits, and terms are explicitly reviewed.
- Do not hardcode credentials.
- Do not treat this as a primary event source unless a direct, permitted integration is approved.

## Mapping / cleanup notes
Map zeffy.com. Useful for provenance and ticket-link classification; not a primary concert event API candidate unless campaign/event fields are explicitly available.

## Suggested Codex actions
- Add/extend provider taxonomy entry for `zeffy`.
- Add domain detection patterns above.
- Add this provider to ticketing_provider detection.
- If API docs are official and useful, add mapper placeholders only; do not make live calls.
- Route unknown/incomplete direct integrations through the API Feed Review Workbench as manual JSON or provenance-only candidates.
