# Security Hardening

This milestone hardens the Music Roadtrip data-pipeline POC before any public
URL, public tunnel, staging deployment, or real provider credentials are used.

The repository remains focused on Scott's scope: public intake, calendar/source
scraping, API sandbox review, clean event listings, event photos, ticket QA,
POI inventory/audit, and private app-feed handoff. It does not add mobile app,
itinerary, route-builder, auto-publish, or monetization behavior.

## Threat Model

Primary risks:

- Bot or spam submissions through public forms.
- Oversized or malicious CSV/XLSX uploads.
- Spreadsheet formula injection in import previews or exported review data.
- SSRF through submitted calendar URLs or crawl redirects.
- Admin credential guessing.
- Missing audit trail for sensitive admin review actions.
- Provider credentials leaking into templates, logs, job payloads, previews, or
  error messages.
- Accidental live provider calls before credentials/configuration are intended.

## Public Intake Protections

Public submissions still pass through the existing trust gate:

- Honeypot field.
- Form render timestamp check.
- Authorization checkbox validation.
- Blocked/trusted submitter/domain checks.
- Risk scoring and review status mapping.
- Suspicious-submissions review queue.

Additional hardening:

- Optional Cloudflare Turnstile server-side verification.
- Rate-limit scoring by IP hash, contact email, submitted domain, route,
  user-agent hash, and global public-submit volume.
- Failed Turnstile submissions are blocked and recorded for admin/security
  review.
- Public responses stay generic and do not expose internal scoring details.

Turnstile config:

```bash
TURNSTILE_ENABLED=true
TURNSTILE_SITE_KEY=...
TURNSTILE_SECRET_KEY=...
TURNSTILE_VERIFY_URL=https://challenges.cloudflare.com/turnstile/v0/siteverify
```

`TURNSTILE_ENABLED=false` by default so local development and fixture tests keep
working.

## Rate Limits

Config:

```bash
PUBLIC_SUBMIT_RATE_LIMIT_PER_IP_PER_HOUR=8
PUBLIC_SUBMIT_RATE_LIMIT_PER_EMAIL_PER_DAY=20
PUBLIC_SUBMIT_RATE_LIMIT_PER_DOMAIN_PER_DAY=40
PUBLIC_FILE_UPLOAD_MAX_SIZE_MB=5
PUBLIC_FILE_UPLOAD_MAX_ROWS=1000
```

Rate-limit hits increase the public submission risk score and can push a
submission into blocked/quarantined review. The public user sees a generic
failure or normal receipt; detailed reasons appear only in admin review and
security dashboards.

## File Upload Protections

Supported uploads:

- `.csv`
- `.xlsx`

Rejected:

- Empty files.
- Unsupported extensions.
- Macro-enabled or legacy workbook extensions such as `.xlsm`, `.xltm`, `.xlam`,
  `.xls`, and `.xlsb`.
- Files above `PUBLIC_FILE_UPLOAD_MAX_SIZE_MB`.
- Files above `PUBLIC_FILE_UPLOAD_MAX_ROWS`.
- XLSX files that cannot be parsed, including password-protected workbooks when
  detectable.

CSV formula-injection values are neutralized for raw-row previews/exports. File
contents are treated as untrusted data and are never executed.

## Crawler SSRF Protections

Crawler safety blocks:

- `localhost`
- `127.0.0.1`, `0.0.0.0`, `::1`
- private IPv4 ranges
- private/link-local/reserved IPv6 ranges
- `169.254.169.254`
- internal hostnames
- `file://`, `ftp://`, `data:`, `javascript:`, and other non-http schemes

Crawler fetch rules:

- Validate before fetch.
- Re-check each redirect target.
- Limit redirects.
- Limit response size.
- Limit timeout.
- Restrict accepted content types to calendar, HTML, XML/RSS/Atom, JSON, and
  plain text.
- Send no cookies or auth headers.

Local development can use localhost fixture URLs. Production blocks localhost
and private-network targets.

## Admin Access Model

Admin protections:

- Signed HttpOnly session cookie.
- Secure cookie in production.
- SameSite cookie setting.
- Configurable session timeout.
- CSRF required for admin POST forms.
- Login failure tracking.
- Login rate limiting by IP hash.
- Password hash only for production.

Config:

```bash
ADMIN_SESSION_TIMEOUT_MINUTES=480
ADMIN_LOGIN_RATE_LIMIT_PER_IP_PER_HOUR=8
ADMIN_REQUIRE_SSO_GATE=false
```

`ADMIN_REQUIRE_SSO_GATE` is a deployment note/config seam for a future
front-door SSO gate. It does not weaken local admin auth.

## Audit Log

The `admin_audit_logs` table records security-relevant actions:

- Login success/failure/rate-limited.
- Logout.
- Source approval, pause, quarantine, block, trust, or reject.
- Manual crawl runs.
- Extracted event approval/rejection.
- Image candidate accept/reject.
- POI candidate approve/link/update/event-venue-only/needs-research/reject.
- Provider sandbox/demo/manual JSON actions.
- App-feed exports.

Audit metadata is redacted before storage.

## Secrets Redaction

Redaction covers common sensitive keys and text:

- `api_key`
- `apikey`
- `token`
- `secret`
- `password`
- `authorization`
- `X-API-Key`
- `cookie`
- `session`

This applies to security/audit metadata and complements the existing background
job redaction behavior.

## Monitoring

`/admin/security` is admin-only and shows:

- Suspicious submissions.
- Blocked submissions.
- Failed logins.
- Recent admin actions.
- Rate-limit hits.
- Turnstile failures.
- Crawler safety blocks.
- Provider live-call attempts blocked.
- Secrets redaction status.

## Provider Credential Handling

Do not hardcode credentials. Use environment variables or a secret manager.

Live JamBase and CitySpark calls remain off unless provider-specific credentials
and explicit live-call config are enabled. CitySpark is a licensed vendor feed
handled through the API Feed Review Workbench; do not scrape CitySpark pages.

## App-Feed Privacy

`APP_FEED_PUBLIC=false` by default. Private app-feed/admin JSON routes require
admin access unless intentionally configured otherwise.

No public submission, crawl, extraction, POI candidate, image candidate, or API
feed record auto-publishes.

## Pre-Launch Checklist

- Set `APP_ENV=production`.
- Set a strong `SESSION_SECRET_KEY`.
- Set `ADMIN_PASSWORD_HASH`; do not use the development fallback password.
- Configure `TURNSTILE_ENABLED=true`, `TURNSTILE_SITE_KEY`, and
  `TURNSTILE_SECRET_KEY` before exposing public forms.
- Review public rate-limit values for the expected traffic level.
- Keep `APP_FEED_PUBLIC=false` unless the app-feed contract is intentionally
  being exposed.
- Keep provider live calls off until credentials and run limits are reviewed.
- Confirm CitySpark/JamBase credentials are not committed.
- Confirm `/admin/security` loads and shows audit activity.
- Run `make test`.
- Run `make lint`.
