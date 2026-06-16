# Provider Compliance and Access Notes

Generated: 2026-06-04

## Default stance

All external providers should be `disabled` by default in live mode unless the company has credentials and a reviewed agreement.

## CitySpark

CitySpark is a paid licensed vendor API feed for Music Roadtrip and is handled like JamBase as a licensed provider feed. Live calls remain off until credentials and configuration are added. Do not hardcode keys.

## SeatGeek

SeatGeek API terms require careful compliance review. The public terms define API usage rights, documentation, materials, and restrictions; they also warn against systematic download/storage/scraping outside authorized usage. Treat SeatGeek as disabled until terms and credentials are reviewed.

## Ticketmaster

Discovery API is available with API key. Partner API is restricted to official distribution partners. Use Discovery for event metadata only if configured. Do not assume purchase/reserve access.

## DICE, Etix, Eventim, See Tickets, TicketWeb, AXS, Tixr

These appear primarily partner/client integration APIs. Do not implement live connectors without partner docs and credentials.

## Eventbrite

Use OAuth and current organization/event endpoints. Be cautious with older/deprecated public search examples.

## Bandsintown

Artist-centric API for artist info/events. Not a broad city/date discovery feed. Good for artist-specific event backfill and ticket-link confirmation.

## Viagogo / StubHub

OAuth2 catalog APIs exist. Treat catalog vs sales/inventory operations separately. Secondary market usage requires legal/commercial review.
