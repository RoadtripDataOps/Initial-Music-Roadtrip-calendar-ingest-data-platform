# New Providers Discovered From Master Export

This file summarizes providers/domains that appeared in the master export beyond the first ticket API provider pack. The export's explicit `Data_source [developers]` field still only exposed CitySpark and Jambase; these providers are inferred mainly from ticket/website domains.

| Provider key | Name | Ticket links | Website mentions | Docs status | Recommendation |
|---|---|---:|---:|---|---|
| `opendate` | OpenDate | 966 | 20 | Official developer page found; API access appears tied to platform/account tier. | Provenance/ticket QA first |
| `universe` | Universe | 576 | 1 | Official Universe developer portal found; Ticketmaster Discovery API can also return Universe-sourced events via source filter. | Provenance/ticket QA first |
| `skiddle` | Skiddle | 358 | 0 | Official API landing page and GitHub API documentation found. Requires API key; rate limits are monitored. | Provenance/ticket QA first |
| `humanitix` | Humanitix | 82 | 41 | Official public read-only API docs found. API can fetch event, order, ticket, and tag information; x-api-key header required. | Provenance/ticket QA first |
| `ticket-tailor` | Ticket Tailor | 67 | 10 | Official API documentation found. API key via HTTP Basic Auth. Event and event-series endpoints documented. | Provenance/ticket QA first |
| `showpass` | Showpass | 52 | 39 | Official developer documentation found. Public discovery endpoint documented; domain allowlist may be required. | Provenance/ticket QA first |
| `ovationtix-audienceview` | AudienceView Professional / OvationTix | 140 | 28 | Official public API reference found. Events/calendar endpoints expose future event data; scanning API requires auth. | Provenance/ticket QA first |
| `holdmyticket` | HoldMyTicket | 120 | 28 | Official docs found. Event API described as read-only for account events by API key. | Provenance/ticket QA first |
| `ticketnetwork` | TicketNetwork / Mercury Web Services | 29 | 532 | Official API-driven product pages found; full API docs appear partner-gated. | Provenance/ticket QA first |
| `vivid-seats` | Vivid Seats / SkyBox | 0 | 53 | Public docs portal exists but full docs may require account/login. SkyBox is broker-focused. | Provenance/ticket QA first |
| `prekindle` | Prekindle | 29 | 111 | Official site says Open API exists; public endpoint reference was not located in this pass. | Provenance/ticket QA first |
| `tixtrack-nliven` | TixTrack / Nliven | 39 | 0 | Official webhooks documentation found; public event discovery API docs not found in this pass. | Provenance/ticket QA first |
| `zeffy` | Zeffy | 37 | 9 | Official API docs found, but resources are payments/contacts/campaigns rather than event discovery. | Provenance/ticket QA first |
| `eventvesta` | Event Vesta / Vesta | 901 | 827 | No public API documentation found in this pass; product site found. | Provenance/ticket QA first |
| `outhouse-tickets` | Outhouse Tickets | 429 | 346 | No public API documentation found in this pass. | Provenance/ticket QA first |
| `venuepilot` | VenuePilot | 329 | 6 | No public API documentation found in this pass; product/support pages found. | Provenance/ticket QA first |
| `biletix` | Biletix | 290 | 0 | No official public API docs found in this pass. | Provenance/ticket QA first |
| `speakeasygo` | SpeakeasyGo Ticketing | 244 | 0 | Ticketing product page found; no public API documentation found in this pass. | Provenance/ticket QA first |
| `eventnoire` | Eventnoire | 96 | 94 | Product/help pages found; no public API documentation found in this pass. | Provenance/ticket QA first |
| `my805tix` | My805Tix / 805Tix | 84 | 77 | Product/event site found; no public API documentation found in this pass. | Provenance/ticket QA first |
| `twentyfour-tix` | 24tix | 8 | 164 | Help/product pages found; no public API documentation found in this pass. | Provenance/ticket QA first |
| `simpletix` | SimpleTix | 69 | 18 | Official platform/help pages found; complete public API reference not found in this pass. | Provenance/ticket QA first |
| `tix-com` | Tix.com | 60 | 13 | Official platform site found; public API reference not found in this pass. | Provenance/ticket QA first |
| `ticketleap` | TicketLeap | 56 | 6 | No official complete public API docs found in this pass; third-party references suggest limited/readonly API. | Provenance/ticket QA first |
| `afton-tickets` | Afton Tickets / Afton Shows | 55 | 0 | Official site found; no public API docs found in this pass. | Provenance/ticket QA first |
| `instantseats` | InstantSeats | 30 | 20 | Official product pages found; no public API docs found in this pass. | Provenance/ticket QA first |
| `affiliate-networks` | Affiliate/tracking networks | 0 | 0 | These are generally not event providers; they are redirect/tracking domains. | Provenance/ticket QA first |
