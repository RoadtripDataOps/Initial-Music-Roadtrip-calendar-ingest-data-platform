# Artist Registry And Genre Normalization

Milestone 5.3 adds a local artist, genre, and music relevance layer for the
Music Roadtrip ingestion POC. It uses already-reviewed normalized event data
and provider payloads stored in the private workbench. It does not call live
providers, add credentials, scrape social platforms, scrape CitySpark pages, or
auto-publish records.

## Artist Registry

`canonical_artists` stores one conservative canonical artist identity. It keeps
display and normalized names, broad artist type, normalized genres, provider
genres, provider IDs, Spotify URL, image metadata, quality flags, and source
claim counts.

`artist_source_claims` stores every provider or upload assertion about an
artist. JamBase performer records, file-upload headliners, JSON-LD performers,
and future enrichment suggestions can all add claims without destroying
provenance.

`event_artists` links normalized Concert events to canonical artists with a
role such as `headliner`, `supporting`, `performer`, `dj`, or `unknown`.
Concert records remain `category=Concert` and `record_type=event`; artists do
not create POIs.

## Matching Rules

Strong matches use provider IDs such as JamBase, Spotify, Ticketmaster, and
MusicBrainz. Medium matches use exact normalized name plus genre overlap or
provider context. Weak similar-name matches are not auto-merged, because false
artist merges are more damaging than a small duplicate review queue.

## JamBase Performer Extraction

JamBase `performer[]` data can populate:

- `provider_artist_id` / `jambase_artist_id` from `performer[].identifier`
- artist name from `performer[].name`
- source claim genres from `performer[].genre`
- role from `performer[].x-isHeadliner`
- lineup order from `performer[].x-performanceRank`
- festival timing from `performer[].x-performanceDate`
- artist type from `performer[].x-bandOrMusician`
- sameAs and external identifiers from provider metadata
- artist image candidates from `performer[].image`

JamBase performer images are treated as high-priority `artist_press` candidates
for photo rescue, but unresolved clearance still requires image approval.

## CitySpark Artist And Relevance Rules

CitySpark is a paid licensed vendor/API feed. CitySpark records may be reviewed
through the private API Feed Review Workbench when credentials and contract
configuration allow it. Live calls remain off unless explicitly configured.

For this milestone, CitySpark contributes music relevance from categories,
labels, and explicit music/concert signals. Artist inference stays
conservative: do not guess an artist from venue names, descriptions, contacts,
or broad labels.

## Genre Normalization

`app/services/genre_service.py` maps provider/upload genres into a broad Music
Roadtrip taxonomy:

- Rock
- Pop
- Country
- Folk
- Blues
- Jazz
- Hip-Hop/Rap
- R&B/Soul
- Electronic/Dance
- Punk
- Metal
- Reggae
- Latin
- Classical
- Americana
- Bluegrass
- Indie
- Jam Band
- World
- Tribute
- Other / Unknown

Events store `provider_genre`, `provider_subgenre`, `normalized_genre`,
`normalized_genres_json`, `genre_confidence`, and `genre_source`. Filter
contracts prefer normalized genres where available.

## Music Relevance

Events can store `music_relevance_score` and `music_relevance_flags_json`.
Positive signals include JamBase provider data, Ticketmaster `segment=Music`,
explicit music/concert categories, headliners, linked artists, music venues,
and ticket/event source signals. Lower-confidence signals include non-music
segments such as sports, comedy, family, misc, and theatre, plus missing
artist, venue, or date data.

Music relevance is a QA signal only. It does not publish, reject, or hide a
record by itself.

## App Feed Artist Contract

App event JSON keeps existing `headliner` and `supporting_artists` fields and
adds:

```json
{
  "artists": [
    {
      "artist_id": "artist-123",
      "name": "Example Band",
      "role": "headliner",
      "spotify_url": "",
      "image_url": "",
      "genres": ["Rock"]
    }
  ]
}
```

The app feed does not expose raw provider payloads, source-claim raw JSON,
credentials, or internal admin notes.

## Jobs

Local background job types:

- `rebuild_artist_registry`
- `artist_genre_normalization`
- `artist_image_rescue`

These jobs rebuild links from stored events, normalize existing genre fields,
and create artist image candidates for existing linked artists. They do not
make live provider calls.
