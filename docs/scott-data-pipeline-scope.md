# Scott Data Pipeline Scope

This repository is focused on Scott's Music Roadtrip data pipeline work:
calendar ingest, source crawling, licensed API sandbox review, normalized event
quality, event photos, ticket-link QA, and POI auditing.

The project can produce app-facing data contracts, but it should not grow into
the consumer mobile app, route builder, or user-trip product.

## In Scope

- Public Submit Calendar and Submit Events intake.
- Master calendar source registry.
- Crawl queue and safe source crawling.
- Safe source extraction from approved calendar/source URLs.
- API Feed Review Workbench.
- JamBase and CitySpark sandbox connectors.
- Provider pipeline handoff pages.
- Event normalization.
- Event Quality Workbench.
- Event dedupe and source claims.
- event photo rescue.
- Image QA.
- Ticket-link QA.
- Artist and genre metadata only when it improves event quality.
- POI registry and POI audit.
- App-feed event and POI contracts.

## Out Of Scope

- User route builder.
- Itineraries.
- Road trips and tours.
- Mobile app UI.
- User saves, folders, or trip collections.
- Social or community features.
- Consumer navigation.
- Ad, discovery, or monetization products.

## Deferred / App Team Feature

Any existing itinerary, Road Trip, Tour, Setlist, or Route code is
compatibility-only and should be treated as deferred app-team-owned future work.
Keep it stable if tests depend on it, but do not expand it unless the user asks
for itinerary work explicitly.

Scott's default priority order is:

1. Calendar/source intake and approval.
2. Crawling and extraction safety.
3. API sandbox review for licensed providers.
4. Normalized Concert event quality.
5. Dedupe, source claims, and provenance.
6. event photo rescue and image QA.
7. Ticket-link QA.
8. POI registry and POI audit.
9. Event/POI app-feed contracts.

Concert remains `category=Concert` and `record_type=event`. Concert records are
events, never POIs. Non-Concert categories remain POI/place records.
