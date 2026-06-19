# Ticket Page Image Fallback

Milestone 5.6B adds a controlled fallback for event images when provider images
are missing, weak, generic, blocked, or only useful as source evidence.

## Purpose

Ticketing event pages often include app-safe event artwork in `og:image`,
`twitter:image`, or JSON-LD `image` fields. The fallback checks those fields
only when an event already has a usable event-specific ticket link and needs
image help.

This does not replace Image QA. Ticket-page images become `image_candidates`
with `source_type=ticket_page`, `rescue_source=ticketing_page_image`, and
`clearance_status=needs_approval`.

## When It Runs

The fallback is eligible when:

- The event is a Concert event.
- The event has a usable ticket URL.
- The ticket URL is classified as direct, platform event, or clear handoff.
- The current image is missing, weak, generic, blocked, or evidence-only.
- There is no manually accepted image.
- There is no accepted artist image.
- The event is not rejected, expired, stale, or cancelled.

The fallback does not run during normal page render. Admins can trigger it from:

- `/admin/events/{id}`
- `/admin/image-candidates`
- `/admin/event-quality`
- `/admin/api-feed-runs/{id}`
- background jobs

## Safe Fetch Rules

Ticket-page fetches reuse crawler safety controls:

- No unsupported schemes.
- No private network or localhost URLs in production.
- Redirect checks.
- Timeout and response-size limits.
- HTML-only extraction.

The service extracts only:

- `meta[property="og:image"]`
- `meta[name="twitter:image"]`
- JSON-LD `image`
- canonical URL
- page title

Raw ticket-page HTML is not exposed in app feeds.

## Provider Stock And Evidence Rules

The Image QA service blocks or downgrades weak provider images such as:

- Placeholder/default/no-image URLs.
- Generic stock images.
- Low-value thumbnails.
- Logos.
- Poster/flyer/admat images.
- Text-heavy or social-graphic evidence-only images.
- Reused provider images across unrelated events.
- JamBase `x-promoImage` promo/admat evidence.
- CitySpark `links[].logoUrl` logo/source evidence.
- Music Roadtrip logo assets.

Provider evidence can help provenance, but hard-blocked evidence does not become
the final app image.

## Candidate Ranking

Ticket-page image candidates rank:

- Below manually accepted or clean artist images.
- Above clean provider event images when the event needs rescue.
- Above venue fallback images and generic provider promos.

The selected event image still carries approval state and quality flags so the
app feed can show safe image provenance without exposing raw crawl/provider
payloads.

## Background Jobs

Supported job types:

- `ticket_page_image_enrichment`
- `api_feed_run_ticket_image_enrichment`
- `recent_events_ticket_image_enrichment`

These jobs create/reuse image candidates and run best-image selection. They do
not auto-approve images or publish events.

## Guardrails

- No live JamBase or CitySpark API calls are made by this workflow.
- No API keys are required.
- No social platforms are scraped.
- Ticket pages are fetched only through explicit admin actions or queued jobs.
- Music Roadtrip logos are UI assets only and must not become event images.
- App feeds receive app-safe image metadata, not raw ticket-page HTML.
