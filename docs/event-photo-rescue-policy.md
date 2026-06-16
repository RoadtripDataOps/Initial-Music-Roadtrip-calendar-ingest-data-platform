# Event Photo Rescue Policy

Milestone 4.8A adds a local event photo rescue layer for Concert event records.
It does not make live provider, search, social, or image-analysis calls. It only
uses image URLs and payloads already submitted, uploaded, staged, or stored in
the private API Feed Review Workbench.

## Core Rules

- Concert records are `category=Concert` and `record_type=event`; they are never
  POIs.
- Music Roadtrip logo assets are UI branding only and must not become event,
  venue, fallback, or image QA candidates.
- Public users cannot submit CitySpark-exported data as their own source.
- CitySpark and JamBase provider records stay behind private provider review,
  provenance, dedupe, ticket QA, image QA, and approval controls.
- Social-media page, post, or profile URLs are not valid final image URLs.
- Social graphics, flyers, posters, admats, and screenshots may support review
  as evidence, but default to `source_evidence_only=true` and
  `can_be_final_image=false`.

## Candidate Fields

Image candidates include rescue metadata:

- `rescue_source`
- `rescue_priority`
- `generic_detection_score`
- `generic_detection_reasons_json`
- `text_graphic_score`
- `poster_flyer_score`
- `admat_score`
- `artist_match_score`
- `venue_context_score`
- `music_signal_score`
- `selected_reason`
- `selection_explanation_json`
- `source_payload_path`
- `source_evidence_only`
- `can_be_final_image`

The selected candidate stores a transparent explanation with the selected
candidate, source path, reason, fallback status, blocked candidates, and approval
state.

## Provider Payload Paths

JamBase stored payload paths:

- `jambase.performer[0].image` and other performer image paths become
  `provider_artist_image` candidates. Headliner matches receive higher priority.
- `jambase.image` becomes a provider event image candidate.
- `jambase.x-promoImage` becomes a cautious provider promo/admat evidence
  candidate and is blocked from automatic final selection.
- `jambase.location.image` becomes a venue fallback candidate.

CitySpark stored payload paths:

- `cityspark.primaryImage.largeImageUrl` is preferred over medium and small.
- `cityspark.primaryImage.mediumImageUrl` and `smallImageUrl` may become lower
  priority provider event candidates.
- `cityspark.media[0]` and other direct media asset URLs may become provider
  event candidates.
- `cityspark.links[0].logoUrl` is logo/source evidence only and cannot be a
  final event photo.
- CitySpark link URLs and social URLs remain source URLs only unless they are
  direct public image assets and pass QA rules.

## Selection Ranking

Automatic rescue selection prefers:

1. Accepted admin-reviewed image candidates.
2. Artist live images.
3. Artist press images.
4. Headliner performer images from provider payloads.
5. Clean event-specific provider images.
6. Clean CitySpark large primary images.
7. Clean JamBase `image` values.
8. Venue live-performance or stage/interior music-signal images.
9. Venue exterior or marquee fallback images.
10. Missing or needs-review status when no candidate is eligible.

Unknown or unresolved clearance does not block provisional selection. The event
is marked `selected_pending_approval`, with `image.needs_approval=true` in the
app feed.

## Automatic Final-Image Blocks

These candidates are visible for QA but blocked from automatic final selection:

- Generic provider placeholders, default images, stock images, and reused images
  across unrelated artists or venues.
- Posters, flyers, admats, text-heavy images, screenshots, and logo-only images.
- Watermarked images unless an admin explicitly accepts them.
- Social-media page/post/profile URLs.
- Ticketing pages or generic platform pages used as image URLs.
- Non-direct image URLs and non-image content types.
- Severe low-resolution thumbnails.
- Food/drink/bar images with no music signal.
- Generic crowd shots without artist, venue, or music signal.

## Admin Surfaces

- `/admin/image-candidates` includes rescue filter chips for photo rescue,
  generic provider photos, poster/flyer/admat, social graphic evidence, artist
  candidates, venue fallback candidates, selected by rescue, and missing artist
  image.
- `/admin/events/{id}` shows a Photo Decision panel with selected preview,
  source path, selected reason, clearance, score, blocked count, fallback state,
  and a Run photo rescue action.
- `/admin/api-feed-records/{id}` previews provider payload image candidates and
  can send all provider images to Image QA.
- `/admin/api-feed-runs/{id}` can run photo rescue for approved events in the
  run.
- `/preview/events/{id}` and `/preview/quality` expose app-safe rescue badges
  and counts.

## App Feed

The app feed image object can include:

- `url`
- `source_type`
- `image_role`
- `selection_reason`
- `needs_approval`
- `quality_flags`

Raw provider payloads, social evidence, and internal review explanations are
not exposed in public app-feed records.
