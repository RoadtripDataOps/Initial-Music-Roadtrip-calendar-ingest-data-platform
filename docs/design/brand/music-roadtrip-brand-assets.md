# Music Roadtrip Brand Assets

These PNG files are UI brand assets for the local Calendar Ingest POC:

- `app/web/static/images/music-roadtrip-logo-square.png`
- `app/web/static/images/music-roadtrip-logo-circle.png`
- `app/web/static/images/music-roadtrip-logo-plate.png`

Documentation copies live in:

- `docs/design/brand/music-roadtrip-logo-square.png`
- `docs/design/brand/music-roadtrip-logo-circle.png`
- `docs/design/brand/music-roadtrip-logo-plate.png`

## Usage

- Square logo: public `/submit-events` hero and documentation.
- Circle logo: admin login, admin sidebar, public form headers, and compact
  preview/header UI.
- Plate logo: optional marketing-style hero only; avoid repeating it throughout
  admin or dense operational pages.

All logo images should use `alt="Music Roadtrip logo"` and should reinforce the
page brand without replacing visible text headings.

## Image QA Guardrail

These logos are UI assets only.

Do not:

- Create `image_candidates` from these logo files.
- Use these logos as event images.
- Use these logos as venue images.
- Use these logos as fallback event images.
- Allow these logos to enter image QA scoring.
- Store these logos as `selected_main_image_url` for events or venues.

The logo paths should remain under `/static/images/` or `docs/design/brand/` and
must not be used as source-provider image payloads.
