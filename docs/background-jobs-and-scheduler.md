# Background Jobs And Scheduler

Milestone 4.8 adds a local, DB-backed operations layer for the Music Roadtrip
Calendar Ingest POC. It is intentionally simple: SQLAlchemy, SQLite, manual
CLI commands, and admin pages. It does not add Redis, Celery, cron, or a
production daemon.

## Admin Pages

- `/admin/jobs`
  - Lists queued jobs with status, type, queue, attempts, timestamps, and
    errors.
  - Supports filters by status, job type, and queue.
- `/admin/jobs/{id}`
  - Shows redacted payload JSON, result JSON, error text, timestamps, lock
    metadata, and related-record links.
  - Provides safe retry for failed/cancelled/skipped jobs.
  - Provides safe cancel for pending/running jobs.
- `/admin/scheduled-tasks`
  - Lists local scheduled task definitions.
  - Supports manual enqueue for each task.
  - Supports enqueueing all due tasks.
- `/admin/scheduled-tasks/{id}`
  - Shows task cadence, payload, next/last run timestamps, and last job.

All admin mutations use the existing admin session and CSRF protections.

## Tables

`background_jobs` stores operational job attempts:

- job type and status
- priority and queue name
- redacted payload/result/error fields
- attempt counts and lock metadata
- scheduled, started, completed, created, and updated timestamps

`scheduled_tasks` stores task definitions:

- task key and task type
- enabled state
- cadence type: manual, interval, daily, weekly, biweekly, monthly
- next/last run timestamps
- last job ID
- redacted payload JSON

## Commands

Run one job:

```bash
python -m app.tools.run_worker --once
```

Run up to five jobs:

```bash
python -m app.tools.run_worker --limit 5
```

Poll continuously only when explicitly requested:

```bash
python -m app.tools.run_worker --loop
```

Enqueue due scheduled tasks:

```bash
python -m app.tools.run_scheduler --once
```

Preview due scheduled tasks without enqueueing:

```bash
python -m app.tools.run_scheduler --dry-run
```

The scheduler only creates background jobs. It does not execute them. Run the
worker separately.

## Supported Job Types

- `app_feed_export`
  - Calls the existing app feed export service.
  - Stores the export ID and record count in the job result.
- `crawl_source`
  - Runs the existing single-source crawl service.
  - Respects the source approval and review gate.
- `bulk_crawl`
  - Runs the existing bulk crawl service for selected master source IDs.
  - Respects the master source crawl gate.
- `scheduled_crawl_due_sources`
  - Finds due approved master sources and runs the existing bulk crawl service.
- `provider_sandbox_jambase`
  - Calls the existing JamBase live sandbox service.
  - Live calls remain blocked unless the existing settings and credentials
    enable them.
- `provider_sandbox_cityspark`
  - Calls the existing CitySpark live sandbox service.
  - Live calls remain blocked unless the existing settings, credentials, and
    contract configuration enable them.
- `image_preflight`
  - Runs the existing safe image preflight metadata update.
  - Does not fetch pages, OCR images, call AI, or create image candidates.
- `event_photo_rescue`
  - Runs event photo rescue for one normalized Concert event.
  - Uses stored image candidates and stored provider payloads only.
  - Records selected image, selected candidate, blocked candidates, and
    approval-needed status in the job result.
- `api_feed_run_photo_rescue`
  - Runs photo rescue for events created from one API feed run.
  - Stores summary counts for rescued events, selected images, blocked generic
    candidates, and events still missing a usable image.
- `recent_events_photo_rescue`
  - Runs photo rescue for recently created or updated Concert events.
  - Uses payload controls such as `since_hours` and `limit`.
- `poi_registry_import`
  - Placeholder job type for a future explicit file import handler.
- `unknown`
  - Fails safely with a clear error.

Default manual scheduled tasks are created for due-source crawls, app feed
exports, and recent event photo rescue. Scheduler tasks only enqueue work; they
do not execute jobs.

## Redaction

Payloads, results, and error messages are redacted before storage and display.
The redactor handles common sensitive fields and URL query parameters:

- `apikey`
- `api_key`
- `token`
- `secret`
- `password`
- `authorization`
- `X-API-Key`
- `access_token`
- `refresh_token`
- `client_secret`

Do not put API keys or credentials in queued payloads. Use environment/config
settings for provider credentials.

## Guardrails

- Background jobs do not bypass auth, CSRF, anti-abuse, crawl gates, image QA,
  ticket QA, dedupe/source-claim rules, or app feed privacy.
- Provider jobs do not make live calls unless existing provider settings and
  credentials explicitly allow them.
- CitySpark remains a licensed vendor/API feed handled through the API Feed
  Review Workbench. The queue does not scrape CitySpark pages and does not
  enable permanent use outside Music Roadtrip's contract controls.
- Public submissions never become crawlable or scheduled without validation,
  risk scoring, and explicit admin approval.
- Concert records remain events. POI/place registry jobs must not create POIs
  from Concert rows.

## Local Smoke Path

1. Start the app with `make dev`.
2. Log in at `/admin/login`.
3. Open `/admin/app-feed`.
4. Choose an export type and click `Run in background`.
5. Open the redirected `/admin/jobs/{id}` page.
6. In another terminal, run `python -m app.tools.run_worker --once`.
7. Refresh the job detail page and confirm it shows `success`.
8. Open `/admin/scheduled-tasks`.
9. Click `Enqueue now` on a manual task, then run the worker again.
10. Open `/admin/image-candidates`, `/admin/events/{id}`, or an API feed run
    detail page to queue photo rescue in the background.

Use `make test` and `make lint` before treating the operations layer as ready.
