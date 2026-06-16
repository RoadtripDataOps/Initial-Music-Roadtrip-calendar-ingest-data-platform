# Music Roadtrip UI Reference

Internal POC mapping for the private preview sandbox and admin QA screens.

These notes use local screenshot references and the public Music Roadtrip site
for visual/product inspiration only. They are not data sources.

## Category Model

| Label | Record type | Color | Icon placeholder | Preview use |
| --- | --- | --- | --- | --- |
| Concert | Event | Yellow | Microphone | Music Events list and event profiles only |
| Music Site | POI / venue-style place | Blue | Music note | Venue/profile category filter |
| Bars & Lounges | POI / venue-style place | Teal | Martini | Venue/profile category filter |
| Cultural | POI / venue-style place | Orange | Theatre masks | Venue/profile category filter |
| Food & Bev | POI / venue-style place | Purple | Fork and knife | Venue/profile category filter |
| Shopping | POI / venue-style place | Green | Shopping cart | Venue/profile category filter |
| Visitor & Travel | POI / venue-style place | Brown | Info pin | Venue/profile category filter |
| Itineraries | Curated guide surface | Orange | Folded map | Reference only for this milestone |
| Lodging | POI / venue-style place | Red | Bed | Venue/profile category filter |

Rule: `Concert` is an event category. It must not appear in venue/POI category
drawers and must not convert an event into a POI.

## Venue Subcategories

`Music Site`: Festivals, Recording Studios, Radio Stations, Music Education,
Dance Clubs, Venues.

`Cultural`: Museums, Art, Memorials, Birthplaces, Theatres, Album Covers,
Performing Arts Centers.

`Food & Bev`: Restaurants, Coffee Shops.

`Shopping`: Record Stores, Music Stores, Apparel & Merch Shops.

`Visitor & Travel`: Travel & Tourism, Chamber.

`Lodging`: Music Hotels, Music Camping.

`Bars & Lounges`: no subcategories yet.

## Field And Icon Mapping

| Reference label | Internal field or panel |
| --- | --- |
| Website | `source_url`, venue `website` |
| Address | venue address fields |
| Tickets link | event `tickets_link` |
| Spotify URL | event `spotify_url` |
| Instagram, Facebook, X, TikTok | staged upload social fields |
| Certified | trusted/certified placeholder badge |
| Performers | event headliner/supporting artists |
| Hours of operation | future venue enrichment field |
| Data source | event/source provenance |
| Source Record ID | event `source_event_id` |
| Venue Match Confidence | future venue matching QA |
| Link Last HTTP Status | crawl-run HTTP status |
| Carousel selection | future venue `carousel_tag` QA filter |
| Music category | event `genre` or venue music taxonomy |
| Photo Quality Score | image QA panel |
| Event Relevance Score | future event relevance QA |
| Quality Control | preview quality dashboard |

## Preview Surface Mapping

Music Events list:
- Dark app-style background.
- Large page title.
- Search area, genre, date, radius, and quality filters.
- Yellow Concert marker.
- Event thumbnail, date/time pill, venue, distance, and QA chips.

Event profile:
- Image-led hero.
- Concert category label.
- Map/Nav/Street/Web/Tickets/Reminder actions.
- Venue card and admin provenance link.
- Spotify and enrichment placeholders.

Venue profile:
- Image-led hero.
- Blue Music Site marker or category-specific marker.
- Subcategory badge and Certified placeholder.
- Map/Nav/Street/Web actions.
- Nested events ordered by date.

Venue filter drawer:
- Dark bottom-sheet inspired panel.
- Colored outline category chips.
- Subcategory chips after selecting a main category.
- Advanced filters for carousel tag, certified, city, state, and quality issue.
- `Show X places` button and `Reset filters` link.
