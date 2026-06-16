# Mapotic Place Import Field Formatting Guide

Date: 2026-04-06

This guide consolidates the Mapotic Help Center, public API docs, sample import sheets, and the public Discover experience into a production-oriented reference for preparing place data before import into Mapotic.

Use this guide with one key distinction:

- `Documented rule`: explicitly stated in Mapotic Help/API docs.
- `Safe convention`: not strictly documented by Mapotic, but the most reliable structure for imports and downstream rendering.

## Quick Reference

| Field | Type | Format | Example |
| --- | --- | --- | --- |
| Name | String | Free-text place name; required | `The Fillmore` |
| Address | String | Single address string for geocoding: `Road/Town/Postal Code` | `1805 Geary Blvd, San Francisco, CA 94115` |
| Latitude / Longitude | Number / Number | WGS84 (EPSG:4326), decimal degrees, separate columns | `37.7840` / `-122.4331` |
| Description | String | Long text / multiline text | `Historic music venue...` |
| Hours of Operation | String | Human-readable text; multiline recommended | `Mon-Fri 10:00-18:00` |
| Instagram | URL | Absolute `https://` profile or post URL | `https://www.instagram.com/thefillmore/` |
| Facebook | URL | Absolute `https://` URL | `https://www.facebook.com/TheFillmoreSF` |
| X (Twitter) | URL | Absolute `https://` URL | `https://x.com/thefillmore` |
| Email | Email string | Valid email format | `info@example.com` |
| YouTube | URL or Video ID object | Safe import: full YouTube URL; API video value: YouTube ID object | `https://www.youtube.com/watch?v=wkcglk95OzM` |
| Phone | String | Clickable phone number; international format recommended | `+1 415 555 0123` |
| Website | URL | Absolute `https://` URL | `https://www.thefillmore.com/` |
| TikTok | URL | Absolute `https://` URL | `https://www.tiktok.com/@thefillmore` |
| PlacesID | String or integer | Stable unique ID; Mapotic update syntax supports `mapotic:<id>` | `venue-000123` or `mapotic:00001` |
| City | String | Plain city name | `San Francisco` |
| State | String | Plain state name or abbreviation; stay consistent | `CA` |
| Zip Code | String | Postal code as text; preserve leading zeros | `94115` |
| Tickets Link | URL | Absolute `https://` URL | `https://www.ticketmaster.com/event/1A005F01ABCD1234` |
| Spotify URL | URL | Absolute `https://open.spotify.com/...` URL | `https://open.spotify.com/artist/1dfeR4HaWDbWqFHLkxsg1d` |
| Main Image URL | URL | One direct, publicly accessible image asset URL; no social-media page/post/share URLs | `https://cdn.example.com/main.jpg` |
| Additional Image URL(s) | URL list | Direct public image asset URLs separated with `$`; no social-media page/post/share URLs | `https://cdn.example.com/1.jpg$https://cdn.example.com/2.jpg` |

## General Import Rules

- Supported import files are `XLS`, `CSV`, and `KML` per Mapotic Help.
- `Name` is mandatory.
- Location must be provided by either:
  - `Latitude` + `Longitude`, or
  - one full `Address` field.
- Custom fields only import cleanly if the matching attribute already exists on the target map.
- For clickable links in text fields, Mapotic documents that the value must include `http://`; in production, prefer `https://`.
- For images, the URL must be publicly accessible without login, cookies, or signed-session access.
- Image fields must contain direct image-asset URLs only. Do not use social-media profile, post, reel, video, story, or share links as image URLs.

> Warning: Mapotic does not publish hard character limits for most fields. Where no limit is documented below, treat the field as "no public Mapotic limit published" rather than assuming unlimited storage.

## Name

- Data type: `String`
- Required format / pattern: Free-text place name. This is a Mapotic mandatory field.
- Character limits or constraints: No public Mapotic max length published.
- Accepted values or examples: `The Fillmore`, `Amoeba Music Hollywood`
- Notes or warnings: Keep this to the place name only. Do not overload it with city, category, or address details unless that is the actual public-facing name.

## Address

- Data type: `String`
- Required format / pattern: For geolocation import, Mapotic documents one combined address field in the format `Road/Town/Postal Code`.
- Character limits or constraints: No public Mapotic max length published.
- Accepted values or examples: `1805 Geary Blvd, San Francisco, CA 94115`
- Notes or warnings: Mapotic states address-based geolocation is less accurate than GPS coordinates and is sensitive to misspellings.

> Warning: `City`, `State`, and `Zip Code` do not replace the geolocation `Address` field by themselves. If you want Mapotic to geocode from address text, pre-compose one full address string before import.

## Latitude / Longitude

- Data type: `Number` / `Number`
- Required format / pattern: WGS84 (`EPSG:4326`) in decimal degrees (`DD`), with latitude and longitude imported as separate fields.
- Character limits or constraints: Numeric values only.
- Accepted values or examples: `37.7840` and `-122.4331`
- Notes or warnings: Negative numbers indicate south/west. Do not use DMS (`37°47'02"N`) or projected coordinate systems.

> Warning: Mapotic import examples use separate `Latitude` and `Longitude` columns, but the public GeoJSON API returns coordinates in `[longitude, latitude]` order. Do not swap them during import preparation.

## Description

- Data type: `String`
- Required format / pattern: Long text / multiline text (`textarea`-style content).

### Content Standard (Required)

All descriptions must be written in the voice of a **Senior Rolling Stone Magazine Travel Section writer**.

This is not optional. The goal is to produce descriptions that feel editorial, immersive, and culturally grounded — not generic directory listings.

### Writing Requirements

- Must include exactly one mention of: `musicroadtrip.com`
- Must feel specific to the location (no generic filler text)
- Must include at least one experiential, sensory, or cultural detail
- Must read as human-written editorial, not templated or generated

### Structure & Style Rules

- Paragraph length: **60–120 words**
- Writing style must vary across entries:
  - Do not reuse opening phrases or sentence structures
  - Rotate narrative approach:
    - Scene-setting
    - Historical framing
    - Cultural significance
    - First-impression tone
- Avoid predictable openings such as:
  - "Nestled in the heart of"
  - "Located in"
  - "Known for"

### Prohibited Content Patterns

- Repetitive phrasing across records
- Generic tourism language
- SEO-style keyword stuffing
- Descriptions that could apply to multiple locations with minimal changes

### Quality Validation Rules (Enforced in Pipeline)

A description should be flagged if:

- It does NOT contain `musicroadtrip.com`
- It reuses a known banned phrase
- It is structurally similar to previously generated descriptions
- It lacks specificity (i.e., could describe another venue)

### Character Limits or Constraints

- No public Mapotic max length published
- Recommended operational range: **60–120 words**

### Accepted Example (Style Reference Only)

A dimly lit room where decades of feedback, distortion, and late-night sets seem baked into the walls, this venue carries the kind of lived-in authenticity you don’t manufacture—you inherit. Artists pass through, but the energy lingers, echoing in worn floors and patched-up amps. It’s the kind of place musicroadtrip.com exists to document, where the story matters as much as the sound, and every night feels like it could tip into something unforgettable.

### Notes or Warnings

- Mapotic renders this as long-form text; formatting such as line breaks is supported
- Embedded links must include full URLs (`https://`) to be clickable
- Treat this field as **editorial content**, not metadata

## Hours of Operation

- Data type: `String`
- Required format / pattern: Safe convention is human-readable text in a `Long text` attribute; Mapotic does not publish a dedicated opening-hours import schema.
- Character limits or constraints: No public Mapotic max length published.
- Accepted values or examples: `Mon-Thu 11:00-22:00\nFri-Sat 11:00-00:00\nSun 11:00-21:00`
- Notes or warnings: Use one consistent schedule style across the whole dataset.

> Warning: There is no documented Mapotic importer format for structured recurring business hours such as `RRULE`, `OpeningHoursSpecification`, or Google-style hours objects. Treat this as display text unless you have a custom downstream parser.

## Instagram

- Data type: `URL string`
- Required format / pattern: Full absolute URL, preferably `https://www.instagram.com/<handle>/`
- Character limits or constraints: No public Mapotic max length published.
- Accepted values or examples: `https://www.instagram.com/thefillmore/`
- Notes or warnings: Use a full URL, not just `@handle`. Mapotic only documents clickable links for text values that include a URL schema.

## Facebook

- Data type: `URL string`
- Required format / pattern: Full absolute URL, preferably `https://www.facebook.com/<page>`
- Character limits or constraints: No public Mapotic max length published.
- Accepted values or examples: `https://www.facebook.com/TheFillmoreSF`
- Notes or warnings: Use the canonical public page URL, not a share URL shortened by Facebook.

## X (Twitter)

- Data type: `URL string`
- Required format / pattern: Full absolute URL, preferably `https://x.com/<handle>`
- Character limits or constraints: No public Mapotic max length published.
- Accepted values or examples: `https://x.com/thefillmore`
- Notes or warnings: Do not import bare handles such as `@thefillmore`. If your source still uses `twitter.com`, normalize consistently.

## Email

- Data type: `Email string`
- Required format / pattern: Valid email format. Mapotic documents that this field accepts only valid emails.
- Character limits or constraints: Must pass email validation; no public Mapotic length limit published.
- Accepted values or examples: `info@example.com`
- Notes or warnings: Use one mailbox per field. If you need multiple contacts, use multiple attributes or a descriptive text field instead of comma-joining addresses.

## YouTube

- Data type: `URL string` for safest CSV import; API-native video value is an object containing a YouTube ID
- Required format / pattern: Safe convention for CSV import is a full YouTube URL such as `https://www.youtube.com/watch?v=<video_id>`. In the public API, Mapotic's `video` attribute value is documented as `{"youtube": "wkcglk95OzM"}`.
- Character limits or constraints: No public Mapotic max length published.
- Accepted values or examples: `https://www.youtube.com/watch?v=wkcglk95OzM`, API value `{"youtube": "wkcglk95OzM"}`
- Notes or warnings: Mapotic publishes the API storage format for `video` attributes, but does not publish CSV import syntax for that attribute type.

> Warning: Do not assume the CSV importer accepts raw JSON for `Video` attributes unless you have tested it against the exact target map. For unattended imports, a plain URL field is the safer documented choice.

## Phone

- Data type: `String`
- Required format / pattern: Clickable phone number. Mapotic does not publish a strict mask; safe convention is one normalized number in international form.
- Character limits or constraints: No public Mapotic max length published.
- Accepted values or examples: `+1 415 555 0123`, `+14155550123`
- Notes or warnings: Avoid labels such as `Box Office:` in the value itself. Keep extensions separate if possible.

## Website

- Data type: `URL string`
- Required format / pattern: Full absolute URL including protocol, preferably `https://`
- Character limits or constraints: No public Mapotic max length published.
- Accepted values or examples: `https://www.thefillmore.com/`
- Notes or warnings: Do not use bare domains like `thefillmore.com`. Use canonical destination URLs, not tracking redirects when possible.

## TikTok

- Data type: `URL string`
- Required format / pattern: Full absolute URL, preferably `https://www.tiktok.com/@<handle>`
- Character limits or constraints: No public Mapotic max length published.
- Accepted values or examples: `https://www.tiktok.com/@thefillmore`
- Notes or warnings: Use the public profile URL. Do not import only the handle.

## PlacesID

- Data type: `String` or `Integer`
- Required format / pattern: Stable unique identifier used for future updates. Mapotic explicitly documents numeric IDs such as `1` to `n`, and also supports `mapotic:<MapoticID>` for updating records that already exist in Mapotic.
- Character limits or constraints: Must be unique per place within the dataset used for updates; no public max length published.
- Accepted values or examples: `1`, `12345`, `venue-000123`, `mapotic:00001`
- Notes or warnings: The important rule is stability. Reuse the same ID on every future import if you want updates instead of duplicate place creation.

> Warning: If you change `PlacesID` values between imports, Mapotic will treat the row as a new place instead of an update target.

## City

- Data type: `String`
- Required format / pattern: Plain city name in a single-line text attribute.
- Character limits or constraints: No public Mapotic max length published.
- Accepted values or examples: `San Francisco`
- Notes or warnings: This is best treated as a custom text attribute. It is not a standalone documented geolocation field for import resolution.

## State

- Data type: `String`
- Required format / pattern: Plain state name or abbreviation in a single-line text attribute.
- Character limits or constraints: No public Mapotic max length published.
- Accepted values or examples: `CA`, `California`
- Notes or warnings: Pick one convention across the dataset and keep it consistent. For U.S. data, USPS two-letter abbreviations are the cleanest machine-readable option.

## Zip Code

- Data type: `String`
- Required format / pattern: Postal code stored as text.
- Character limits or constraints: Preserve leading zeros; no public Mapotic max length published.
- Accepted values or examples: `94115`, `02108`, `94115-3412`
- Notes or warnings: Treat zip codes as strings, not numbers, so spreadsheet tools do not strip leading zeros.

## Tickets Link

- Data type: `URL string`
- Required format / pattern: Full absolute URL including protocol, preferably `https://`
- Character limits or constraints: No public Mapotic max length published.
- Accepted values or examples: `https://www.ticketmaster.com/event/1A005F01ABCD1234`
- Notes or warnings: Use the final public purchase page, not a session-bound cart URL.

## Spotify URL

- Data type: `URL string`
- Required format / pattern: Full absolute Spotify URL, typically `https://open.spotify.com/...`
- Character limits or constraints: No public Mapotic max length published.
- Accepted values or examples: `https://open.spotify.com/artist/1dfeR4HaWDbWqFHLkxsg1d`
- Notes or warnings: Use canonical Spotify URLs. Do not import `spotify:` URIs unless you have separately verified that your target rendering supports them.

## Main Image URL

- Data type: `URL string`
- Required format / pattern: One publicly accessible **direct image asset URL** mapped to Mapotic's `Main image` special parameter.
- Character limits or constraints: Must resolve publicly to an image asset; no public Mapotic size/length limit published.
- Accepted values or examples: `https://cdn.example.com/images/fillmore-main.jpg`
- Notes or warnings: Use a direct asset URL, not a page URL that merely contains an image. Do **not** use TikTok, Facebook, Instagram, X/Twitter, YouTube, Threads, LinkedIn, Pinterest, Yelp page links, or other social/profile/post/share URLs as image-field values. Social links belong only in their dedicated social/link fields, never in `Main Image URL`.

### Photo Search and Selection Standard (Required)

The image fields should not be populated with arbitrary high-resolution photos. Choose images that clearly communicate the record's **music signal**, the reason it belongs in Music Roadtrip, and the visual context a traveler needs.

Use the row's `Category` first. For POIs, use the subcategory value from the corresponding category-specific column, such as `Music Site`, `Cultural`, `Food & Bev`, `Shopping`, `Visitor & Travel`, or `Lodging`.

#### Global Photo Selection Rules

- **Main Image / Photo 1** should show the most important music-related subject for that category or subcategory.
- **Additional Image / Photo 2** should complement the main image with context: exterior, entrance, marquee, room, artifact, marker, or environment.
- Prioritize **subject clarity, musical relevance, recognizability, and traveler usefulness** over raw resolution.
- Prefer landscape images where width is greater than height.
- Prefer source images at least **600 px wide** before processing.
- Final processed images should never be below **400 px on the shortest side**.
- Use direct public image assets, not webpages that merely contain an image.
- Do **not** use social-media URLs as photo URLs, including profile pages, posts, reels, stories, videos, short links, or share links from TikTok, Facebook, Instagram, X/Twitter, YouTube, Threads, LinkedIn, Pinterest, Yelp, or similar platforms.
- Prefer authentic, place-specific, artist-specific, or artifact-specific images over stock imagery.

#### Universal Hard Avoid

Do not use images where the primary subject is:

- Food, drinks, menus, cocktails, coffee cups, pastries, plates, table settings, or bar closeups
- Posters, flyers, ads, screenshots, social-media UI, social-media post/page URLs, ticketing pages, map pins, logos, or event graphics
- Generic performers, crowd shots, nightlife scenes, or instrument photos where the place, artist, or music connection is not identifiable
- Unrelated buildings, nearby businesses, street scenes, city skylines, tourist views, or decorative interiors with no music signal
- Bathrooms, empty tables, staff-only areas, checkout counters, POS systems, menus, merch price tags, or storage rooms
- Watermarked thumbnails, blurred images, tiny previews, extreme crops, or heavily vertical images unless there is no credible alternative

#### Category-Specific Photo Hunt Guidance

| Category | Subcategory | Main Image / Photo 1 Target | Additional Image / Photo 2 Target | Search Concepts / Visual Cues |
| --- | --- | --- | --- | --- |
| `Concert` | Event, no POI subcategory | The performing artist, band, DJ, or ensemble in a live-performance context. Prefer a real live shot with stage, lighting, crowd energy, or venue context visible. | Venue exterior, marquee, stage view, or a second live image that adds context without duplicating Photo 1. | Artist name + live concert; artist performing; band on stage; DJ booth; venue name + artist; tour stop live photo. |
| `Music Site` | `Festivals` | Active festival performance: stage, artist, crowd, lights, festival grounds, or recognizable festival branding in context. | Entrance, grounds, main stage wide shot, crowd field, landmark installation, or festival sign. | Festival name + stage crowd; festival grounds music; main stage; live performance; festival entrance. |
| `Music Site` | `Recording Studios` | The studio identity: exterior sign, building facade, live room, control room, console, tracking room, or artist-in-studio image tied to that studio. | Wider exterior, plaque/sign, control room, live room, or historically relevant studio artifact. | Studio name + control room; live room; studio exterior sign; artist recording at studio. |
| `Music Site` | `Radio Stations` | Station identity: branded studio, on-air booth, host/DJ at microphone, building sign, broadcast room, or transmitter/site signage. | Exterior with station branding, control room, lobby display, or radio tower only when clearly tied to the station. | Station call letters + studio; on air booth; radio host microphone; station sign; broadcast studio. |
| `Music Site` | `Music Education` | Students, instructors, rehearsal rooms, practice spaces, ensemble performance, music classroom, school sign, or campus music building. | Performance hall, rehearsal room, entrance sign, instrument lab, or student ensemble context. | Music school name + rehearsal; student performance; music classroom; conservatory building; ensemble. |
| `Music Site` | `Dance Clubs` | DJ booth, dance floor, lighting, crowd movement, or interior club atmosphere where the venue identity is still recognizable. | Exterior entrance, sign, marquee, sound/lighting rig, or room-wide dance floor view. | Club name + DJ booth; dance floor lighting; nightclub interior; exterior entrance; marquee. |
| `Music Site` | `Venues` | High-energy live interior action shot: stage, performers, crowd, lighting, and room atmosphere. | Exterior facade, entrance, marquee, sign, or architectural interior if Photo 1 is live action. | Venue name + live concert crowd interior lighting; exterior marquee; stage; empty venue interior. |
| `Bars & Lounges` | No current subcategories | Live music, DJ, small stage, singer, jazz group, house band, dance floor, or musician-focused room atmosphere. The music signal must outweigh the bar signal. | Exterior sign, entrance, small stage, piano, DJ booth, or performance corner. | Bar name + live music; lounge jazz; DJ night; small stage; singer songwriter; exterior sign. |
| `Cultural` | `Museums` | Museum identity tied to music: exterior/sign, music exhibit, artist exhibit, instrument collection, listening room, or recognizable cultural artifact. | Entrance, exhibit detail, plaque, marquee, or building facade. | Museum name + music exhibit; artist exhibit; instrument collection; museum exterior sign. |
| `Cultural` | `Art` | Music-related public art: mural, sculpture, installation, street art, portrait, or visual artwork clearly tied to an artist, genre, scene, song, or music history. | Wider context showing where the artwork sits, nearby plaque, wall, building, or streetscape only when the artwork remains visible. | Artist mural; musician sculpture; music mural; public art musician; album/genre mural. |
| `Cultural` | `Memorials` | The artist, musician, band member, or music figure being memorialized. Prefer a recognizable portrait, performance image, statue, plaque, gravesite marker, or memorial object with the artist's name visible. | Wider memorial setting, plaque close-up, marker, statue, street sign, or surrounding site context. | Artist name + memorial; artist portrait; gravesite; statue; plaque; tribute mural. |
| `Cultural` | `Birthplaces` | The artist or musician associated with the birthplace. If available, use a recognizable portrait, early-career image, or image that directly connects the artist to the birthplace. | Birthplace exterior, historic marker, plaque, house, neighborhood marker, or museum-style context. | Artist name + birthplace; childhood home; historic marker; artist portrait; birthplace plaque. |
| `Cultural` | `Theatres` | Theatre facade, marquee, stage, auditorium, performance space, or live performance where the theatre identity is visible. | Interior auditorium, balcony, proscenium, exterior sign, box office facade, or historic architectural detail. | Theatre name + marquee; auditorium; stage; live performance; exterior facade. |
| `Cultural` | `Album Covers` | The actual album cover artwork. The artist name and album identity should be visible when possible. | The real-world location, object, street, storefront, wall, or landscape shown on or associated with the album cover, if relevant and identifiable. | Artist + album cover; album title cover art; album cover location; record sleeve; original cover photo site. |
| `Cultural` | `Performing Arts Centers` | Main hall, stage, auditorium, orchestra shell, exterior sign, marquee, or live music/performance image tied to the center. | Exterior facade, lobby with music context, seating bowl, proscenium, or entrance signage. | Performing arts center + stage; concert hall; auditorium; exterior sign; orchestra. |
| `Food & Bev` | `Restaurants` | Music connection first: musician performing at the restaurant, artist-owned/artist-associated restaurant, stage/piano/performance corner, live-music room, or exterior signage if the music tie is not visually available. | Exterior, entrance, music room, small stage, piano, mural, plaque, or artist-related display. | Restaurant name + live music; musician-owned restaurant; dinner show stage; piano bar; acoustic performance. |
| `Food & Bev` | `Coffee Shops` | Musician-focused image: singer-songwriter, acoustic performer, open mic, small stage, songwriter circle, piano, or musician-associated coffeehouse. Expect smaller rooms and less crowd energy than venues. | Exterior sign, performance corner, open-mic setup, small stage, music bulletin board only if it is clearly place-specific and not just generic flyers. | Coffee shop name + open mic; singer songwriter; acoustic performance; coffeehouse music; small stage. |
| `Shopping` | `Record Stores` | Store identity with music inventory: storefront sign, vinyl bins, record walls, listening stations, in-store DJ/performance, or recognizable interior aisles. | Exterior, checkout wall with records, rare-record display, in-store stage/DJ area, or signage. | Record store name + vinyl bins; storefront; in-store performance; record wall; listening station. |
| `Shopping` | `Music Stores` | Instruments, gear, repair benches, lesson rooms, storefront sign, instrument wall, or musician/customer trying gear where the store is identifiable. | Exterior, branded signage, instrument wall, repair shop, lesson room, or performance demo area. | Music store name + instruments; guitar wall; repair shop; lesson room; storefront. |
| `Shopping` | `Apparel & Merch Shops` | Music-specific merch: band shirts, artist merch wall, tour merchandise, label/scene apparel, storefront, or music-culture retail identity. | Exterior sign, merch wall, display tied to artists/scenes, or in-store music culture context. | Merch shop name + band shirts; artist merch; music apparel; storefront; tour merchandise. |
| `Visitor & Travel` | `Travel & Tourism` | Music destination signal: music trail marker, district sign, landmark tied to a musician/scene/song, mural, venue row, historic marker, or tourism image with clear music context. | Wider location context, sign/plaque, walkable district view, landmark exterior, or interpretive marker. | Music trail; music landmark; historic music district; artist landmark; tourism music site. |
| `Visitor & Travel` | `Chamber` | Chamber/tourism office or civic visitor image only when it directly promotes a music trail, music district, festival, scene, artist, or venue network. | Visitor center exterior, chamber sign, music map display, district signage, or festival/tourism collateral only if not poster-like and clearly place-specific. | Chamber + music trail; visitor center music district; local music tourism; downtown music sign. |
| `Lodging` | `Music Hotels` | Hotel identity tied to music: exterior/sign, lobby/music memorabilia, live-music room, artist-themed rooms, recording/performance space, or venue-style stage connected to the property. | Exterior entrance, lobby display, performance space, music-themed room, plaque, marquee/signage, or nearby music landmark when directly tied to the hotel. | Music hotel; hotel live music; artist-themed hotel; music memorabilia lobby; hotel venue stage; hotel exterior sign. |
| `Lodging` | `Music Camping` | Music-oriented camping context: festival campground, campground stage, music-camp setting, campfire/acoustic performance, branded entrance, or music-retreat grounds where the lodging/camping role is clear. | Campground entrance, tents/RV area with festival/music context, communal performance area, grounds map/sign, or landscape context with music signal. | Music camping; festival campground; music camp; campground stage; acoustic campfire performance; music retreat grounds. |

#### Fallback Order by Record Type

- **Active venues, dance clubs, bars, lounges, festivals, theatres, and performing arts centers:** live action first; exterior/sign second; architectural interior third.
- **Artist/person-linked cultural records such as memorials and birthplaces:** artist/person image first; memorial/birthplace marker second; exterior/location context third.
- **Object/artifact-linked cultural records such as album covers and art:** artifact itself first; physical location/context second; related artist image third.
- **Food & Bev records:** musician/performance/open-mic context first; exterior/sign second; interior performance area third. Never use food or drink as the main subject.
- **Shopping records:** store identity plus music inventory first; exterior/sign second; interior aisle/display third.
- **Visitor & Travel records:** music landmark/trail/district signal first; visitor-center/chamber exterior second; broad tourism imagery last only if the music connection remains explicit.
- **Lodging records:** music lodging/camping identity first; exterior/grounds/signage second; guest-room/campsite context third only when the music connection remains explicit. Avoid unrelated hotel-room or generic campground imagery.

These phrases and targets are guidance for the kind of visual evidence to look for. They are not tied to any specific provider, service, or API.

#### Image URL Eligibility Rules

Only use URLs that resolve directly to an image file or image asset suitable for import. The image URL should return an image response, not an HTML page, embedded viewer, social-media post, profile, reel, story, video page, or share page.

Allowed pattern examples:

- `https://cdn.example.com/images/venue-photo.jpg`
- `https://images.example.org/path/photo.png`
- A stable public CDN/object-storage URL that resolves directly to an image asset

Disallowed pattern examples:

- TikTok profile, video, or share links
- Facebook page, post, photo-page, or share links
- Instagram profile, post, reel, story, or share links
- X/Twitter post/profile links
- YouTube video, Shorts, or thumbnail-page links
- Pinterest, Threads, LinkedIn, Yelp, Google Maps listing/photo pages, or any other webpage that displays an image but is not itself a direct image asset

> Warning: Mapotic explicitly requires a link to an image that is accessible to the public. Authenticated CDN URLs, expiring signed URLs, Google Drive share pages, and social-media page/post/share URLs are poor import targets.

## Additional Image URL(s)

- Data type: `URL list`
- Required format / pattern: One or more publicly accessible **direct image asset URLs** separated by a dollar sign (`$`).
- Character limits or constraints: No leading `$`, no trailing `$`, and no `$` separators when only one image is present.
- Accepted values or examples: `https://cdn.example.com/1.jpg$https://cdn.example.com/2.jpg$https://cdn.example.com/3.jpg`
- Notes or warnings: Mapotic documents that the first image in the list becomes the main image unless you separately map `Main image`. Do **not** use TikTok, Facebook, Instagram, X/Twitter, YouTube, Threads, LinkedIn, Pinterest, Yelp page links, or other social/profile/post/share URLs inside the `$`-separated image list.

### Additional Image / Photo 2 Target

The additional image should complement the main image rather than duplicate it. Use the category-specific guidance above to decide what “complementary” means.

- If Photo 1 is live action, Photo 2 should usually provide place context: exterior, entrance, marquee, sign, room-wide interior, or architectural identity.
- If Photo 1 is an artist/person image, Photo 2 should usually show the memorial, birthplace, plaque, marker, mural, or associated site.
- If Photo 1 is an album cover or artifact, Photo 2 should usually show the real-world location, record object, cover-location context, or artist-related setting.
- If Photo 1 is a storefront or exterior, Photo 2 should usually show a music-relevant interior, stage, inventory, display, or interpretive marker.
- If only one high-quality, music-relevant image exists, use a single image rather than padding the gallery with weak or unrelated imagery.

> Warning: To remove an image gallery via import, Mapotic documents the sentinel value `$DELETE`. Do not mix `$DELETE` with actual URLs in the same field.

## Implementation Notes for Import Pipelines

- Prefer GPS coordinates over address geocoding whenever exact placement matters.
- Create all required Mapotic custom attributes before import. Import mapping cannot target attributes that do not exist.
- Normalize all social, ticketing, and music links to full canonical `https://` URLs before writing the import file.
- Keep social-media URLs out of image fields. Social links are valid only in their dedicated fields, not in `Main Image URL` or `Additional Image URL(s)`.
- Preserve `Zip Code` as text in spreadsheet or CSV generation code.
- Keep `PlacesID` stable forever once assigned.
- For image imports, preflight URLs with an unauthenticated HTTP `200` check and a valid image content type.
- For image selection, validate the visual role before import using the category/subcategory photo matrix: the main image should show the strongest music signal for that record type, and additional images should add complementary context rather than duplicate or dilute it.
- Treat `YouTube` as a plain URL field unless you have positively validated Mapotic `video` attribute CSV behavior in the target environment.

## Sources Reviewed

- [Mapotic Help: How to bulk import places into your Mapotic map](https://help.mapotic.com/import-data-places-mapotic-map/)
- [Mapotic Help: Attribute Types](https://help.mapotic.com/attribute-types/)
- [Mapotic Help: Setting up categories and attributes](https://help.mapotic.com/setting-up-categories-attributes/)
- [Mapotic API: Attribute](https://mapotic.github.io/mapotic.com-api-docs/attribute/)
- [Mapotic API: POI](https://mapotic.github.io/mapotic.com-api-docs/poi/)
- [Mapotic Discover](https://www.mapotic.com/discover)

## Confidence Notes

- `High confidence`: `Name`, `Address`, `Latitude / Longitude`, `PlacesID`, image fields, email validation, API attribute value types.
- `Medium confidence`: social URLs, `Website`, `Tickets Link`, `Spotify URL`, `Hours of Operation`, `City`, `State`, `Zip Code`, because Mapotic does not publish stricter field-specific validation beyond generic text/link behavior.
- `Caution required`: `YouTube`, because Mapotic publishes the API storage shape for `video` attributes but not the CSV import syntax for that attribute type.
