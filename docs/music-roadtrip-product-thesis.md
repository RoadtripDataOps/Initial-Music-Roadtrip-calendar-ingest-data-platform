# Music Roadtrip Product Thesis

Music Roadtrip Calendar Ingest is not merely a calendar scraper. It is the
foundation for Music Roadtrip's event and music-destination data platform.

Music Roadtrip is a free travel app for music fans and a music tourism platform.
Its job is to help people understand destinations through music: where to hear
it, where it happened, where to shop for it, where to stay near it, and how to
turn a concert or festival into a richer trip.

## Product Scope

The Music Roadtrip experience combines:

- Concerts, festivals, and music events.
- Venues, clubs, bars, lounges, and listening spaces.
- Music sites, landmarks, studios, music schools, and radio stations.
- Record stores, music stores, apparel, merchandise, and music shopping.
- Music museums, memorials, album-cover locations, murals, and music history.
- Restaurants, coffee shops, lodging, music hotels, and music camping.
- Travel planning, local guides, routes, directions, and curated itineraries.
- Visual storytelling, artist previews, ticket links, and QA-reviewed imagery.

This repository does not own every consumer-app feature in that product vision.
Scott's work here is the ingest/data-quality pipeline: calendar sources, API
sandbox review, normalized Concert events, event photos, ticket QA, POI audit,
and event/POI feed contracts. Route builders, user itineraries, saved trips,
consumer navigation, social/community features, monetization, and mobile app UI
belong to the app team unless explicitly requested for this repo.

This means the ingest system must preserve the difference between events and
places. `category=Concert` records are events. Non-Concert categories are
POI/venue-style place records that can host, contextualize, or help tell the
story around Concert events.

## Strategic Advantage

Music Roadtrip's advantage is human plus technology:

- Local curation from people who understand a destination's music identity.
- Licensed/vendor APIs such as CitySpark and JamBase, with live calls off until
  credentials and configuration are added.
- Submitted source calendars from clients, venues, promoters, artists,
  festivals, tourism boards, chambers, and partners.
- Internal source research that expands the owned/direct source network.
- Map-based storytelling and destination context.
- Travel utility for planning around concerts and music places.
- Visual QA for event and venue images.
- Ticket-link QA that prefers event-specific ticket pages over generic platform
  or handoff links.
- Editorial context that turns raw records into useful travel experiences.

## Two-Track Data Platform

Track A: Owned/direct source network

- Public calendar URL submissions.
- Concert event CSV/XLSX uploads.
- Calendar source CSV/XLSX uploads.
- Tourism board submissions.
- Chamber and partner submissions.
- Venue calendar submissions.
- Festival calendar submissions.
- Internal team source research.
- Approved master calendar source registry.
- Crawl queue and future scheduled crawling.

Track B: Licensed/vendor provider feeds

- CitySpark.
- JamBase.
- Ticketmaster classification references.
- Future approved ticketing/event APIs.
- Manual provider JSON review.
- Provider-specific mappers.
- Source-chain provenance.
- API Feed Review Workbench.
- Provider pipeline / developer handoff documentation.

Both tracks normalize into:

- `category=Concert`.
- `record_type=event`.
- Normalized events.
- Venue profile linkage.
- Ticket-link QA.
- Image QA.
- Source provenance.
- Dedupe/upsert.
- Admin review.
- Preview sandbox.
- Future app/map feed.

## CitySpark Strategy

CitySpark is a paid licensed vendor API feed for Music Roadtrip. The system may
support CitySpark as a licensed provider feed when credentials and contract
configuration allow it. CitySpark should be handled through the private API Feed
Review Workbench, with compliance, retention, source provenance, normalization,
dedupe, and approval controls.

CitySpark is not a first-party source. Public users should not submit
CitySpark-exported data manually, and the app should not scrape CitySpark
pages. Live CitySpark calls remain off unless credentials and configuration
explicitly enable them. Permanent CitySpark approval is governed by Music
Roadtrip's vendor agreement and explicit config.

## Certified Music Region And Destination Operations

The Certified Music Region / destination-facing layer matters because Music
Roadtrip is also useful to tourism boards, cities, chambers, and destination
partners. Those organizations need reliable data about concerts, venues, music
sites, hotels, retail, culture, and itineraries, but they also need trust:
provenance, dedupe status, QA flags, image quality, and source-chain clarity.

The backend ingest system supports both:

- B2C app experiences: discovery, maps, event pages, venue profiles, travel
  planning, and music-destination storytelling.
- B2B destination data operations: partner submissions, certified-region data,
  source review, QA cleanup, reporting, and future app/map feeds.

## Boss-Demo Narrative

The demo shows how Music Roadtrip can accept direct calendar submissions while
still reviewing licensed API feeds like CitySpark and JamBase. The system
normalizes everything into one Concert event pipeline, dedupes overlapping
records, improves images and ticket links, links events to venue profiles, and
previews how the data will look inside the app.
