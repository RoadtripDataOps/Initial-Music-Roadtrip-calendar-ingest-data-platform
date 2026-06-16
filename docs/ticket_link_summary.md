# Ticket Link Audit Summary

- Generated: 2026-04-16 11:04:40
- Workbook: `/Users/saugat/Documents/Audit Work/TIcket Links.xlsx`
- Scope: Jambase and CitySpark rows only; original `Sheet1` left unchanged.
- Eventbrite note: `/checkout-external` links were treated as generic/app handoff pages rather than final ticket links.

## Current Status

| Source | Rows | Direct | Redirect/handoff | Platform event | Platform generic/app | Non-ticket | Blank |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Jambase | 22,177 | 1,374 | 12,203 | 3,693 | 1,370 | 2,895 | 642 |
| CitySpark | 43,563 | 2,050 | 8,363 | 16,421 | 132 | 352 | 16,245 |

## Correction Actions Applied

| Source | Keep direct | Keep redirect | Keep platform event | Use website direct | Use website redirect | Use website platform event | API backfill required |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Jambase | 1,374 | 12,203 | 3,693 | 43 | 0 | 0 | 4,864 |
| CitySpark | 2,050 | 8,363 | 16,421 | 4,619 | 6 | 6,564 | 5,540 |

## Recommended Final Coverage

| Source | Resolved direct | Resolved redirect | Resolved platform event | Resolved total | Unresolved | Resolved from Website (en) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Jambase | 1,417 | 12,203 | 3,693 | 17,313 | 4,864 | 43 |
| CitySpark | 6,669 | 8,369 | 22,985 | 38,023 | 5,540 | 11,189 |

## Platform Domain Behavior

| Source | Domain | Platform event pages | Platform generic/app pages | Interpretation |
| --- | --- | ---: | ---: | --- |
| Jambase | eventbrite.com | 369 | 5 | Mixed usage; review this domain on the corrections tab. |
| Jambase | bandsintown.com | 1 | 0 | Event-specific platform pages; kept as working platform ticket destinations. |
| Jambase | axs.com | 1,718 | 5 | Mixed usage; review this domain on the corrections tab. |
| Jambase | ticketmaster.com | 16 | 18 | Mixed usage; review this domain on the corrections tab. |
| Jambase | ticketweb.com | 36 | 1 | Mixed usage; review this domain on the corrections tab. |
| Jambase | tixr.com | 872 | 2 | Mixed usage; review this domain on the corrections tab. |
| Jambase | etix.com | 98 | 2 | Mixed usage; review this domain on the corrections tab. |
| Jambase | link.dice.fm | 0 | 1,327 | Generic platform/app handoff only; not accepted as a final ticket link. |
| CitySpark | eventbrite.com | 2,813 | 2 | Mixed usage; review this domain on the corrections tab. |
| CitySpark | bandsintown.com | 12,242 | 0 | Event-specific platform pages; kept as working platform ticket destinations. |
| CitySpark | axs.com | 304 | 0 | Event-specific platform pages; kept as working platform ticket destinations. |
| CitySpark | ticketmaster.com | 37 | 40 | Mixed usage; review this domain on the corrections tab. |
| CitySpark | ticketweb.com | 54 | 1 | Mixed usage; review this domain on the corrections tab. |
| CitySpark | tixr.com | 31 | 16 | Mixed usage; review this domain on the corrections tab. |
| CitySpark | etix.com | 271 | 47 | Mixed usage; review this domain on the corrections tab. |
| CitySpark | link.dice.fm | 0 | 3 | Generic platform/app handoff only; not accepted as a final ticket link. |

## Repair Rules

1. Direct pages were kept.
2. Redirect/handoff links were kept only when the pattern clearly pointed at a ticket destination.
3. Platform event pages were kept when the URL looked event-specific.
4. Platform generic/app pages were rejected, including Eventbrite /checkout-external, DICE deep links, Ticketmaster homepages, and Ticketmaster artist pages.
5. Website (en) was used only when it looked more ticketable than Tickets link (en).
6. Unresolved rows require API backfill from JamBase offers[].url or CitySpark ticketUrl.

## Source API Notes

- JamBase repair target: offers[].url, preferring ticketingLinkPrimary then ticketingLinkSecondary.
- CitySpark repair target: ticketUrl; do not treat links[].linkUrl or the generic event url as the ticket field without validation.
- event_id (Jambase) (en), venue_id (Jambase) (en), Source Record ID, and Link Last HTTP Status are blank in the workbook, so unresolved rows cannot be deterministically rehydrated from this file alone.
