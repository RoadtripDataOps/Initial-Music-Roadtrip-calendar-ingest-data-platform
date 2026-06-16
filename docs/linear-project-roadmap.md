# Music Roadtrip Calendar Ingest + API Data Platform — Linear Roadmap

## 1. Executive Summary

Music Roadtrip needs one internal place to collect event calendars, review
licensed API feeds, clean event listings, improve ticket links and photos, audit
music-related places, and hand clean data to the app team.

This project creates that internal data operating system. It helps Scott and the
team accept calendar and event submissions, safely review vendor feeds such as
CitySpark and JamBase, dedupe overlapping records, improve event quality, protect
the POI/place inventory, and prepare reliable event and place data for Music
Roadtrip.

The goal is not to build consumer app features. The goal is to make the data
that powers those experiences cleaner, safer, easier to review, and easier to
hand off.

## 2. Scope

### In Scope

- Public calendar and event intake.
- Calendar source collection.
- Calendar/source scraping for approved sources.
- API feed sandboxing for CitySpark, JamBase, and future providers.
- Event cleanup and normalization.
- Event dedupe.
- Source provenance and source claims.
- Event photo quality and photo rescue.
- Ticket-link quality.
- POI inventory and POI audit.
- App-feed handoff contracts for clean event and POI data.
- Source quality reporting.
- Admin dashboards and review workbenches.

### Out of Scope

- Mobile app UI.
- User accounts.
- Saved trips.
- Itineraries.
- Route builder.
- Turn-by-turn navigation.
- Social/community features.
- Consumer app implementation.
- Ad sales implementation.
- Final production tech stack section.

### Data Rule: Events vs POIs

Public and team-facing wording should generally say **Events**.

Internal systems may still store the backend event category as `Concert`.
That internal category is an event category only. Concert records must never be
treated as POIs.

Non-Concert categories are POIs/places. Venue and place profiles can show nested
events, but the events themselves remain events.

### Current Project Status

The local proof of concept is well advanced. Public intake, admin review,
calendar source management, crawl operations, API feed review, event cleanup,
photo rescue, ticket QA, app-feed contracts, region reporting, source quality,
and POI inventory snapshot foundations are in place.

The most important remaining local work is the incoming POI candidate audit gate
and real-data testing with live, licensed provider credentials and real city
source crawls.

## 3. Status Legend

- `[x] Done`
- `[ ] Todo`
- `[ ] Backlog`
- `[ ] Needs confirmation`

## 4. Milestone Summary Table

| Phase | Milestone | Plain-English outcome | Status |
| --- | --- | --- | --- |
| 1 | Public Intake + Admin Foundation | Partners and team members can submit calendars/events and admins can log in securely. | Mostly Done |
| 2 | Calendar Source Registry + Crawl Operations | Music Roadtrip can manage approved calendar sources and crawl them manually or in batches. | Mostly Done |
| 3 | API Feed Review + Provider Sandbox | CitySpark and JamBase records can be reviewed safely before they become app-ready events. | Mostly Done |
| 4 | Event Cleanup, Dedupe, Tickets, and Photos | Events are cleaned, deduped, QA'd, and given better photos/ticket links. | Mostly Done |
| 5 | POI Inventory + POI Audit | Current POIs are inventoried and new POI candidates are staged before entering the database. | Partially Done |
| 6 | Source Extraction Beyond ICS | Approved source pages can produce event candidates from ICS, JSON-LD, RSS, and static HTML. | Done |
| 7 | Background Jobs + Scheduler | Long-running tasks can run safely as jobs instead of blocking admin pages. | Mostly Done |
| 8 | App Feed + Search/Map Contracts | The app team gets clean event/POI/search/map JSON contracts. | Mostly Done |
| 9 | Region, Source Quality, and Reporting | Data can be grouped by region and source quality can be reported. | Mostly Done |
| 10 | Real Data Testing + Production Readiness | Real API/source testing and secure staging deployment remain. | Todo |

## 5. Detailed Milestones and Issues

## Phase 1 — Public Intake + Admin Foundation

Status: Mostly Done

Purpose: Let partners, venues, tourism boards, and the Music Roadtrip team submit
calendar links or event spreadsheets. Protect the internal review area with
login.

Why it matters: Music Roadtrip needs a simple, trusted front door for event and
calendar information. This gives partners an easy way to contribute while
keeping all submitted data behind review before it affects the app.

- [x] Create a local proof of concept for Music Roadtrip calendar/event intake
- [x] Create a public homepage for calendar and event submissions
- [x] Add Music Roadtrip branding and logo to public pages
- [x] Add public Submit Calendar page
- [x] Add public Submit Events page
- [x] Add simple guidance for non-technical users
- [x] Add Which option should I choose? help text
- [x] Add What happens next? help text
- [x] Add public form for one calendar link
- [x] Add public upload path for a spreadsheet of event details
- [x] Add public upload path for a list of calendar links
- [x] Add downloadable event spreadsheet templates
- [x] Add downloadable calendar-list templates
- [x] Add simple public success/thank-you page
- [x] Add Team Login link for internal users
- [x] Add admin login
- [x] Protect internal admin pages behind login
- [x] Add admin logout
- [x] Add form protection for internal admin actions
- [x] Keep public pages separate from admin pages
- [x] Add dark Music Roadtrip visual theme
- [x] Simplify public wording from Concerts to Events
- [x] Keep backend category rule unchanged: `category=Concert`
- [ ] Review final public copy with marketing team
- [ ] Add production-ready legal/privacy copy for public submissions

Internal note: Public wording can say Events even while the backend continues to
store event records with the internal Concert category.

## Phase 2 — Calendar Source Registry + Crawl Operations

Status: Mostly Done

Purpose: Create a trusted master list of calendar sources and make it possible
to crawl one source or many sources without manually clicking each one.

Why it matters: Music Roadtrip cannot scale calendar collection one manual page
at a time. A reviewed source registry makes it possible to collect from approved
venues, tourism boards, festivals, partners, and internal research sources while
still protecting the system from spam and unapproved submissions.

- [x] Store submitted calendar links for review
- [x] Create a master calendar source registry
- [x] Deduplicate calendar links so the same source is not added twice
- [x] Add source status values such as pending, approved, paused, and blocked
- [x] Add review status before a source can be crawled
- [x] Add crawl frequency choices such as manual, daily, weekly, biweekly, and monthly
- [x] Add manual crawl action for approved sources
- [x] Add crawl history
- [x] Add crawl detail page
- [x] Save crawl response metadata and raw response preview
- [x] Add bulk crawl actions
- [x] Add crawl queue page
- [x] Allow selected sources to be crawled together
- [x] Allow due sources to be crawled together
- [x] Allow approved sources from a batch upload to be crawled together
- [x] Add source risk/scam/spam protections
- [x] Add suspicious submission queue
- [x] Add blocked submitters/domains
- [x] Add trusted submitters/domains
- [x] Keep public submissions from becoming crawlable without review
- [x] Add background job support for crawl operations
- [x] Add scheduler foundation for future recurring crawls
- [ ] Run a real 25-50 source city test
- [ ] Calibrate crawl frequency rules using real source performance
- [ ] Create source research playbook for collecting city/tourism board calendars
- [ ] Add production scheduler/worker deployment

Internal note: Crawls remain gated by source approval and review approval.

## Phase 3 — API Feed Review + Provider Sandbox

Status: Mostly Done

Purpose: Let Scott safely review licensed API data from CitySpark, JamBase, and
future vendors before that data reaches the app.

Why it matters: Licensed vendor feeds can help Music Roadtrip move faster, but
they still need review, provenance, dedupe, image QA, ticket QA, and approval.
The provider workbench keeps vendor data visible for review without turning on
uncontrolled live calls or auto-publishing.

- [x] Create private API Feed Review Workbench
- [x] Add provider cards for JamBase, CitySpark, Spotify, SerpAPI, and Manual JSON
- [x] Treat JamBase as a paid licensed vendor feed
- [x] Treat CitySpark as a paid licensed vendor feed
- [x] Keep live provider calls off by default
- [x] Keep API credentials out of code and UI
- [x] Add manual JSON upload for provider-style testing
- [x] Add synthetic/demo provider records for testing
- [x] Show raw provider data next to normalized event data
- [x] Add approve, hold, reject, and send-to-enrichment review actions
- [x] Add provider source-chain/provenance tracking
- [x] Add provider pipeline/developer handoff pages
- [x] Add JamBase v3.1.0 docs and mapping notes
- [x] Update JamBase base URL and request examples
- [x] Update CitySpark provider model to match paid vendor status
- [x] Add live sandbox page for JamBase
- [x] Add live sandbox page for CitySpark
- [x] Redact API keys from all request previews
- [x] Make provider sandbox runs admin-only
- [x] Store sandbox results as pending API feed records
- [x] Ensure provider records do not auto-publish
- [x] Route approved provider records through dedupe/source-claim workflow
- [x] Add background job support for provider sandbox runs
- [ ] Add real JamBase credentials in private environment
- [ ] Run JamBase 100-event controlled test
- [ ] Run JamBase 1,000-event controlled test
- [ ] Add real CitySpark credentials in private environment
- [ ] Run CitySpark 100-event controlled test
- [ ] Run CitySpark 1,000-event controlled test
- [ ] Compare JamBase and CitySpark overlap, photos, tickets, and duplicates
- [ ] Create provider performance scorecards from real runs

Internal note: CitySpark is a licensed vendor feed, not a first-party source.
Live calls and permanent use remain controlled by configuration and agreement.

## Phase 4 — Event Cleanup, Dedupe, Tickets, and Photos

Status: Mostly Done

Purpose: Create the cleanest possible event listings before they reach Music
Roadtrip or the app team.

Why it matters: A good event feed is not just a date and title. The listing
needs a clear name, reliable time, venue, ticket link, good photo, source
history, dedupe status, and readiness signal. This phase gives Scott one place
to review those quality issues before app handoff.

- [x] Parse ICS/iCalendar feeds into events
- [x] Normalize all event records as Events for the team/public UI
- [x] Preserve backend `category=Concert` for event records
- [x] Add event table and event detail pages
- [x] Add event provenance/source fields
- [x] Add event dedupe service
- [x] Add event source claims
- [x] Prevent repeated crawls from creating duplicate events
- [x] Prevent repeated uploads from creating duplicate events
- [x] Prevent repeated provider approvals from creating duplicate events
- [x] Add duplicate event review pages
- [x] Add event lifecycle status such as active, cancelled, postponed, rescheduled, stale, expired
- [x] Preserve source claims when events update
- [x] Record created vs updated vs duplicate counts
- [x] Add ticket-link classification
- [x] Add ticket-link repair rules
- [x] Prefer JamBase offer URLs for JamBase ticket links
- [x] Prefer CitySpark ticketUrl for CitySpark ticket links
- [x] Flag generic/app ticket links
- [x] Add event image candidate system
- [x] Add event photo rescue service
- [x] Prefer artist/live/press photos over generic provider images
- [x] Suppress generic provider photos and stock placeholders
- [x] Treat posters/flyers/social graphics as evidence, not final event photos
- [x] Add selected image explanation
- [x] Allow best eligible image to display while marked needs approval
- [x] Add Image QA review board
- [x] Add admin event Photo Decision panel
- [x] Add preview badges for missing/bad/pending images
- [x] Add Event Quality Workbench
- [x] Add event quality buckets for missing photos, bad tickets, duplicates, missing venue, low music relevance, and app-feed readiness
- [x] Add bulk event-quality actions such as run photo rescue and recompute readiness
- [x] Add artist registry
- [x] Add event-to-artist links
- [x] Add genre normalization
- [x] Add music relevance scoring
- [x] Add artist image support for event photo rescue
- [ ] Calibrate photo rescue with real JamBase and CitySpark image samples
- [ ] Calibrate ticket-link rules with real provider runs
- [ ] Add a final ready-for-app review workflow for real events
- [ ] Create manual operating checklist for event quality review

Internal note: Event records stay event-only and must not enter the POI/place
inventory.

## Phase 5 — POI Inventory + POI Audit

Status: Partially Done

Purpose: Protect the quality of Music Roadtrip's map/place database. New POIs
discovered from scraping or API data should be reviewed before they enter the
main POI inventory.

Why it matters: Music Roadtrip's place database is a major product asset. Before
new places are added, they need to be matched against existing places, checked
for duplicates, assigned the right category/subcategory, and reviewed for image
and location quality.

- [x] Analyze current Mapotic export
- [x] Split export into Events vs POIs
- [x] Confirm Concert rows are events only
- [x] Create POI Master Registry foundation
- [x] Add POI location model
- [x] Generate current POI registry JSONL from Mapotic export
- [x] Identify POI duplicate candidates from current export
- [x] Add POI admin pages
- [x] Add POI duplicate review page
- [x] Add category/subcategory parsing rules
- [x] Preserve POI fields such as name, category, subcategory, address, city, state, zip, lat/lng, website, socials, image URL
- [x] Add search seeds from POIs and regions
- [x] Create current POI inventory monthly snapshot
- [x] Create current POI dedupe index JSON
- [x] Add admin page for POI inventory snapshots
- [x] Add monthly POI inventory snapshot job
- [ ] Add incoming POI candidate model
- [ ] Stage scraped/provider-discovered locations as POI candidates
- [ ] Match incoming POI candidates against existing POI database
- [ ] Match incoming POI candidates against latest dedupe index
- [ ] Add POI candidate review page
- [ ] Add decisions: link existing POI, create new POI, update existing POI, mark event-venue-only, needs research, reject
- [ ] Prevent unapproved POI candidates from entering app-feed POIs
- [ ] Add POI candidate quality scoring
- [ ] Add POI candidate image checks
- [ ] Add POI candidate category/subcategory validation
- [ ] Add POI candidate background jobs
- [ ] Add POI audit documentation and operating checklist

Internal note: The database remains the source of truth. JSON/JSONL POI
inventory files are portable review and dedupe snapshots, not the primary
database.

## Phase 6 — Source Extraction Beyond ICS

Status: Done

Purpose: Make approved source URLs useful even when they are not clean calendar
feeds.

Why it matters: Many useful calendars are not published as clean calendar files.
Safe extraction lets Scott stage possible event listings from approved sources
without crawling uncontrolled pages or publishing uncertain results.

- [x] Add safe extraction service for approved crawl results
- [x] Continue supporting ICS/iCalendar
- [x] Add JSON-LD Event and MusicEvent extraction
- [x] Add RSS/Atom feed extraction
- [x] Add simple static HTML event-card extraction
- [x] Add generic event-link discovery
- [x] Stage extracted event candidates for review
- [x] Add admin extracted-events pages
- [x] Add extraction metadata to crawl details
- [x] Add extraction warnings/errors to crawl details
- [x] Route approved extracted events through dedupe and source claims
- [x] Create image candidates from extracted images
- [x] Run photo rescue after extracted event approval
- [x] Keep extracted events from auto-publishing
- [x] Avoid browser automation, recursive crawling, and social scraping
- [x] Preserve no CitySpark page scraping rule
- [ ] Test extraction against 25-50 real tourism/venue calendar pages
- [ ] Improve static HTML patterns based on real-page failures
- [ ] Add source-specific extractor notes for common calendar platforms

## Phase 7 — Background Jobs + Scheduler

Status: Mostly Done

Purpose: Make long-running tasks safe by moving them out of web requests and
into a local job system.

Why it matters: Crawls, provider sandbox runs, exports, reports, and image
rescue work should not rely on a single page request. Jobs make the system safer
to operate and easier to retry when something fails.

- [x] Add database-backed job queue
- [x] Add background job model
- [x] Add scheduled task model
- [x] Add local worker command
- [x] Add scheduler command
- [x] Add admin Jobs page
- [x] Add admin Scheduled Tasks page
- [x] Add retry/cancel job actions
- [x] Add redaction for secrets in job payloads/results
- [x] Add app-feed export jobs
- [x] Add provider sandbox jobs
- [x] Add crawl jobs
- [x] Add photo rescue jobs
- [x] Add source-quality rollup jobs
- [x] Add partner-report jobs
- [x] Add search-index rebuild jobs
- [x] Add artist/genre jobs
- [x] Add POI inventory snapshot jobs
- [x] Add dashboard job counts
- [ ] Run jobs under a real long-lived worker process
- [ ] Add production scheduler/cron/service setup
- [ ] Add failed-job alerting
- [ ] Add worker health check

## Phase 8 — App Feed + Search/Map Contracts

Status: Mostly Done

Purpose: Give the app team clean event/POI/venue/search/map data without
exposing the messy internal ingest tables.

Why it matters: The app team needs stable, app-safe data contracts. They should
not have to understand raw vendor payloads, review queues, crawl errors, or
internal cleanup records to display useful Music Roadtrip data.

- [x] Add private app-feed layer
- [x] Add app-safe Events JSON
- [x] Add app-safe POIs JSON
- [x] Add app-safe Venues JSON
- [x] Keep app feed private by default
- [x] Hide raw provider data from app feeds
- [x] Add publish/app-readiness scoring
- [x] Add app feed dashboard
- [x] Add app-feed export jobs
- [x] Add region-filtered app feeds
- [x] Add internal app search index
- [x] Add app search admin page
- [x] Add private app search JSON route
- [x] Add search suggestion route
- [x] Add map marker metadata contract
- [x] Add map marker JSON routes
- [x] Add filter options JSON route
- [x] Keep Events separate from POI category filters
- [x] Add discovery feed placeholder
- [x] Add search/map/filter documentation
- [ ] Validate app-feed JSON with app developer
- [ ] Freeze v1 app-feed contract
- [ ] Add versioned app-feed endpoints or exports
- [ ] Add performance tests for app-feed/search endpoints
- [ ] Decide when/if public app-feed routes can be enabled

Internal note: The app-feed layer is private by default and should not expose
raw provider payloads or internal notes.

## Phase 9 — Region, Source Quality, and Reporting

Status: Mostly Done

Purpose: Group data by city/region and show which sources and regions are ready
for Music Roadtrip.

Why it matters: Tourism boards, partners, and internal teams need to understand
source coverage and data quality by region. This helps Music Roadtrip decide
where to launch, which sources are worth more attention, and what data still
needs cleanup.

- [x] Add region/destination layer
- [x] Add destination partner model
- [x] Add search seed registry
- [x] Seed search locations from POIs
- [x] Add region inference for POIs and events
- [x] Add admin regions pages
- [x] Add admin search seeds page
- [x] Add region quality snapshots
- [x] Add regional app-feed JSON
- [x] Add source trust scoring
- [x] Add source quality grades
- [x] Add source recommendations
- [x] Add partner reports
- [x] Add region report page
- [x] Add JSON and CSV report exports
- [x] Add source-quality jobs
- [x] Add partner-report jobs
- [ ] Generate reports for one real test city
- [ ] Create partner-facing report template
- [ ] Add region readiness checklist
- [ ] Add monthly source-quality report automation
- [ ] Define which metrics matter most to tourism/partner teams

## Phase 10 — Real Data Testing + Production Readiness

Status: Todo

Purpose: Move the system from local proof of concept to secure internal staging
and real data operations.

Why it matters: The platform already proves the workflow locally. The next step
is to test with real sources and licensed credentials, tune the rules from real
data, and prepare a secure internal environment that Scott can use reliably.

- [ ] Choose first real test region
- [ ] Load 25-50 real calendar sources for the test region
- [ ] Run controlled source crawl test
- [ ] Review extracted event candidates
- [ ] Approve a controlled batch of real events
- [ ] Review Event Quality Workbench results
- [ ] Review Image QA and photo rescue results
- [ ] Review ticket-link quality results
- [ ] Review POI candidates
- [ ] Review app-feed event/POI JSON output
- [ ] Run JamBase 100-event sandbox pull
- [ ] Run JamBase 1,000-event sandbox pull
- [ ] Run CitySpark 100-event sandbox pull
- [ ] Run CitySpark 1,000-event sandbox pull
- [ ] Compare provider overlap and duplicates
- [ ] Tune provider mapping rules from real data
- [ ] Tune photo rescue rules from real data
- [ ] Tune ticket-link rules from real data
- [ ] Tune POI candidate matching from real data
- [ ] Move from SQLite to production database
- [ ] Add proper database migrations
- [ ] Deploy secure staging environment
- [ ] Add stronger admin access control
- [ ] Add secrets management
- [ ] Add backups
- [ ] Add monitoring/error logging
- [ ] Add worker/scheduler hosting
- [ ] Add public URL for approved public intake pages
- [ ] Add internal staging URL for admin
- [ ] Create operating SOP for Scott's workflow
- [ ] Create handoff docs for app developer

## 6. Remaining Work Summary

Remaining before the local proof of concept is complete:

- Incoming POI candidate audit gate.
- Real JamBase and CitySpark shakedown runs.
- Real city/source crawl test.
- Event/photo/ticket rule calibration from real data.
- POI candidate matching and review tuning from real data.

Remaining before internal staging:

- Production database.
- Deployment.
- Secure admin access.
- Long-running worker.
- Scheduler.
- Backups.
- Monitoring.
- Real credentials.

## 7. Recommended Next 5 Issues

1. Build incoming POI candidate audit gate.
2. Add real JamBase credentials and run 100-event sandbox test.
3. Add real CitySpark credentials and run 100-event sandbox test.
4. Run a real city calendar-source crawl test.
5. Calibrate event photo, ticket-link, and POI matching rules from real data.

## 8. Linear Import Notes

- Create one Linear project under Scott Zone.
- Create each Phase as a Linear milestone.
- Create each checkbox as an issue.
- Mark `[x]` items as Done.
- Leave `[ ]` items as Todo or Backlog depending on priority.
- Do not include app-team travel-planning or mobile-app issues in this project.
- Do not include itinerary/mobile-app issues in this project.
- Add production platform details later as a separate section or issue after Scott reviews them.
