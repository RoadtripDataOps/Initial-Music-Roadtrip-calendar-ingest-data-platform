# Event Quality Workbench

Milestone 5.4A adds `/admin/event-quality`, an admin-only workbench for Scott's
highest-priority data-quality workflow: reviewing normalized Concert listings
before they reach the app feed.

This workbench is not an app feature. It does not build route builders,
itineraries, saved trips, mobile UI, consumer navigation, auto-publishing, live
provider calls, or external scraping.

## Review Focus

The workbench surfaces one row per normalized Concert event with:

- event name and headliner
- date/time
- venue and city/state
- source providers and source claim count
- dedupe status and duplicate group link
- image status and image selection reason
- ticket-link status
- music relevance score
- event quality score
- app-feed readiness score
- links to event detail, preview, image candidates, source claims, duplicate
  group, and app-feed JSON preview

Concert records remain `category=Concert` and `record_type=event`. They are not
POIs.

## Quality Buckets

The page provides count chips and filters for:

- Missing image
- Selected image pending approval
- Generic/provider image blocked
- Poster/flyer/admat blocked
- Social graphic evidence only
- Missing ticket link
- Bad/generic ticket link
- Missing venue
- Missing coordinates
- Duplicate candidate
- Weak dedupe confidence
- Low music relevance
- Missing artist/headliner
- Missing genre
- Not app-feed ready
- Recently updated
- Multiple source claims

## Event Quality Score

`event_quality_score` is computed from existing normalized event fields. It is
not a new persisted table in this milestone.

Scoring considers:

- clean title
- start date/time
- venue linkage
- venue address or coordinates
- ticket link presence
- ticket-link quality
- selected image presence
- selected image quality and role
- image approval state
- artist/headliner linkage
- genre and music relevance
- duplicate status
- source claim count
- app-feed readiness

The workbench also shows the existing app-feed readiness score so Scott can see
both the event-quality score and the feed-contract readiness signal.

## Safe Actions

All mutation actions require admin CSRF.

Supported actions:

- Run photo rescue for selected events.
- Mark selected events as needing image review.
- Recompute event quality/app-feed readiness signals for selected events.
- Send selected events to duplicate review when they are already suspicious.

The workbench never auto-approves, auto-publishes, makes live provider calls,
scrapes CitySpark, or bypasses image QA, ticket QA, source claims, or dedupe.

## Dashboard Integration

The admin dashboard shows:

- Events needing photos
- Events needing tickets
- Events with duplicate risk
- Events not app-feed ready
- Events ready for app feed

These counts use the same service as `/admin/event-quality`.
