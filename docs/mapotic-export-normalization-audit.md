# Mapotic Export Normalization Audit

Source export: `/Users/augat/Downloads/Mapotic_Export_6_11_26.csv`
Generated at: `2026-06-12T00:05:50`

## Summary

- Row count: 177465
- Column count: 100
- Concert/event rows: 151042
- POI/place rows: 26423

## Category Counts

| Value | Count |
| --- | ---: |
| Concert | 151042 |
| Music Site | 9198 |
| Cultural | 5718 |
| Shopping | 5419 |
| Bars & Lounges | 4381 |
| Visitor & Travel | 877 |
| Food & Bev | 619 |
| Lodging | 211 |

## Subcategory Counts By Category

## Cultural

| Value | Count |
| --- | ---: |
| Theatres | 1755 |
| Memorials | 1529 |
| Performing Arts Centers | 1311 |
| Art | 863 |
| Museums | 143 |
| Album Covers | 113 |

## Food & Bev

| Value | Count |
| --- | ---: |
| Restaurants | 527 |
| Coffee Shops | 90 |

## Lodging

| Value | Count |
| --- | ---: |
| Music Hotels | 211 |

## Music Site

| Value | Count |
| --- | ---: |
| Venues | 7874 |
| Festivals | 1037 |
| Dance Clubs | 159 |
| Radio Stations | 51 |
| Recording Studios | 42 |
| Music Education | 25 |

## Shopping

| Value | Count |
| --- | ---: |
| Record Stores | 2987 |
| Music Stores | 2414 |
| Apparel & Merch Shops | 17 |

## Visitor & Travel

| Value | Count |
| --- | ---: |
| Travel & Tourism | 872 |
| Chamber | 4 |

## Data Source Counts

| Value | Count |
| --- | ---: |
| CitySpark | 90662 |
| Jambase | 60362 |
| blank | 26441 |

## Missing Required Field Counts

| Value | Count |
| --- | ---: |
| event_missing_ticket_link | 47773 |
| event_missing_date | 1961 |

## Field Completeness Counts

| Value | Count |
| --- | ---: |
| poi_main_image_present | 26417 |
| poi_additional_image_present | 18998 |
| poi_address_present | 26418 |
| poi_website_present | 22833 |
| poi_phone_present | 21604 |
| poi_email_missing | 26195 |
| poi_instagram_missing | 9928 |
| poi_facebook_present | 18709 |
| poi_x_url_present | 9351 |
| poi_tiktok_missing | 19990 |
| poi_ticket_link_missing | 20882 |
| poi_date_missing | 26423 |
| poi_geo_present | 26423 |
| poi_x_url_missing | 17072 |
| poi_additional_image_missing | 7425 |
| poi_instagram_present | 16495 |
| poi_tiktok_present | 6433 |
| poi_facebook_missing | 7714 |
| poi_phone_missing | 4819 |
| event_main_image_present | 149112 |
| event_additional_image_missing | 150581 |
| event_address_present | 90651 |
| event_website_present | 85533 |
| event_phone_missing | 151042 |
| event_email_missing | 151042 |

## Duplicate Candidate Summary

- Total duplicate candidates: 18
- Strong candidates: 4
- Medium candidates: 14
- Weak candidates: 0

## Normalization Observations

- `Category = Concert` is treated as event data and excluded from the POI registry.
- Non-Concert rows are normalized as POIs using the main `Category` column plus the matching category-specific subcategory column.
- `Longitude` and `Latitude` are exported as separate columns and must not be swapped.
- `Zip Code` is preserved as text.
- Image fields are kept only for direct/non-social assets; Music Roadtrip logo UI assets are excluded from POI image fields.

## Field Mapping Recommendations

- Use Mapotic IDs, PlacesID, and Canonical Venue ID as provenance and dedupe signals.
- Use normalized name plus latitude/longitude rounded to five decimals as the primary POI dedupe key.
- Keep source rows as raw JSON for auditability while storing cleaned display fields separately.

## Cleanup Priorities

1. Review strong and medium duplicate candidates before importing new POI candidates.
2. Fill missing location data on POIs that lack both coordinates and address.
3. Repair non-direct or social-media image values before image QA.
4. Normalize provider/source IDs for future cross-feed dedupe.
