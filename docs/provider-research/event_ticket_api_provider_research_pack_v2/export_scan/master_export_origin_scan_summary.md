# Master Export Origin Scan Summary
Generated from `m1Kj8nPj_export.csv`. The full CSV is intentionally not copied into this pack because it is large and contains operational data; this pack includes aggregate origin/domain scans only.
- Total rows scanned: **166,743**
- Concert rows scanned: **141,168**
## Category counts
- `Concert`: 141,168
- `Music Site`: 8,922
- `Cultural`: 5,602
- `Shopping`: 5,292
- `Bars & Lounges`: 4,275
- `Visitor & Travel`: 880
- `Food & Bev`: 604

## Explicit ingestion provider field
- `CitySpark`: 84,163
- `Jambase`: 56,876
- `<blank>`: 129

Observation: explicit `Data_source [developers]` values only exposed `CitySpark`, `Jambase`, and blanks. Additional upstream/ticketing origins are inferred from ticket/website domains, not from a clean source-of-source field.

## Nonblank provenance fields on Concert rows
- `Tickets link (en)`: 98,628
- `Website (en)`: 78,089
- `Music category`: 65,867
- `Spotify URL (en)`: 17,564

## Top ticket-link domains
- `ticketmaster.evyy.net`: 37,144 ticket-link mentions; sample source `CitySpark`
- `bandsintown.com`: 10,494 ticket-link mentions; sample source `CitySpark`
- `facebook.com`: 49 ticket-link mentions; sample source `CitySpark`
- `eventbrite.com`: 6,313 ticket-link mentions; sample source `CitySpark`
- `eventim.de`: 5,614 ticket-link mentions; sample source `Jambase`
- `link.dice.fm`: 5,588 ticket-link mentions; sample source `CitySpark`
- `axs.com`: 4,703 ticket-link mentions; sample source `CitySpark`
- `prod-nts-api.seeticketsusa.us`: 3,126 ticket-link mentions; sample source `CitySpark`
- `etix.prf.hn`: 2,185 ticket-link mentions; sample source `CitySpark`
- `tixr.com`: 1,922 ticket-link mentions; sample source `CitySpark`
- `eventvesta.com`: 901 ticket-link mentions; sample source `CitySpark`
- `etix.com`: 1,118 ticket-link mentions; sample source `CitySpark`
- `awin1.com`: 1,099 ticket-link mentions; sample source `Jambase`
- `app.opendate.io`: 966 ticket-link mentions; sample source `CitySpark`
- `events.outhousetickets.com`: 427 ticket-link mentions; sample source `CitySpark`
- `eventbrite.ca`: 306 ticket-link mentions; sample source `CitySpark`
- `universe.com`: 576 ticket-link mentions; sample source `CitySpark`
- `ticketnetwork.lusg.net`: 29 ticket-link mentions; sample source `CitySpark`
- `tickets.taogroup.com`: 288 ticket-link mentions; sample source `CitySpark`
- `tockify.com`: 2 ticket-link mentions; sample source `CitySpark`
- `skiddle.com`: 358 ticket-link mentions; sample source `Jambase`
- `tickets.venuepilot.com`: 328 ticket-link mentions; sample source `CitySpark`
- `ticketmaster.com`: 295 ticket-link mentions; sample source `CitySpark`
- `ticketweb.com`: 281 ticket-link mentions; sample source `CitySpark`
- `scfta.org`: 264 ticket-link mentions; sample source `CitySpark`
- `biletix.com`: 290 ticket-link mentions; sample source `Jambase`
- `speakeasygo.com`: 244 ticket-link mentions; sample source `Jambase`
- `dice.fm`: 213 ticket-link mentions; sample source `CitySpark`
- `portsmouthnhtickets.com`: 104 ticket-link mentions; sample source `CitySpark`
- `events.eventnoire.com`: 96 ticket-link mentions; sample source `CitySpark`
- `24tix.com`: 8 ticket-link mentions; sample source `CitySpark`
- `ci.ovationtix.com`: 140 ticket-link mentions; sample source `CitySpark`
- `ticketmaster.no`: 162 ticket-link mentions; sample source `Jambase`
- `my805tix.com`: 84 ticket-link mentions; sample source `CitySpark`
- `prekindle.com`: 28 ticket-link mentions; sample source `CitySpark`
- `sickening.events`: 64 ticket-link mentions; sample source `CitySpark`

## Provider candidates by grouped domain
- `ticketmaster`: 48,310 total URL mentions; ticket links 37,915; previous pack: True
- `unknown_or_venue_specific`: 37,671 total URL mentions; ticket links 11,936; previous pack: False
- `bandsintown`: 27,998 total URL mentions; ticket links 10,494; previous pack: True
- `spotify`: 17,662 total URL mentions; ticket links 0; previous pack: False
- `facebook`: 17,070 total URL mentions; ticket links 53; previous pack: False
- `eventbrite`: 11,014 total URL mentions; ticket links 6,653; previous pack: True
- `dice`: 5,832 total URL mentions; ticket links 5,801; previous pack: True
- `eventim`: 5,735 total URL mentions; ticket links 5,713; previous pack: True
- `axs`: 4,706 total URL mentions; ticket links 4,703; previous pack: True
- `etix`: 3,391 total URL mentions; ticket links 3,321; previous pack: True
- `see-tickets`: 3,158 total URL mentions; ticket links 3,157; previous pack: True
- `tixr`: 1,975 total URL mentions; ticket links 1,922; previous pack: True
- `eventvesta`: 1,728 total URL mentions; ticket links 901; previous pack: False
- `awin-affiliate`: 1,099 total URL mentions; ticket links 1,099; previous pack: False
- `opendate`: 986 total URL mentions; ticket links 966; previous pack: False
- `outhouse-tickets`: 775 total URL mentions; ticket links 429; previous pack: False
- `universe`: 577 total URL mentions; ticket links 576; previous pack: False
- `ticketnetwork`: 561 total URL mentions; ticket links 29; previous pack: False
- `tao-group`: 558 total URL mentions; ticket links 382; previous pack: False
- `skiddle`: 358 total URL mentions; ticket links 358; previous pack: False
- `venuepilot`: 335 total URL mentions; ticket links 329; previous pack: False
- `ticketweb`: 321 total URL mentions; ticket links 281; previous pack: True
- `biletix`: 290 total URL mentions; ticket links 290; previous pack: False
- `speakeasygo`: 244 total URL mentions; ticket links 244; previous pack: False
- `eventnoire`: 190 total URL mentions; ticket links 96; previous pack: False
- `twentyfour-tix`: 172 total URL mentions; ticket links 8; previous pack: False
- `ovationtix-audienceview`: 168 total URL mentions; ticket links 140; previous pack: False
- `my805tix`: 161 total URL mentions; ticket links 84; previous pack: False
- `holdmyticket`: 148 total URL mentions; ticket links 120; previous pack: False
- `seated`: 144 total URL mentions; ticket links 0; previous pack: True
- `prekindle`: 140 total URL mentions; ticket links 29; previous pack: False
- `humanitix`: 123 total URL mentions; ticket links 82; previous pack: False
- `showpass`: 91 total URL mentions; ticket links 52; previous pack: False
- `simpletix`: 87 total URL mentions; ticket links 69; previous pack: False
- `ticket-tailor`: 77 total URL mentions; ticket links 67; previous pack: False
- `tix-com`: 73 total URL mentions; ticket links 60; previous pack: False
- `mlb`: 63 total URL mentions; ticket links 57; previous pack: False
- `ticketleap`: 62 total URL mentions; ticket links 56; previous pack: False
- `afton-tickets`: 55 total URL mentions; ticket links 55; previous pack: False
- `vivid-seats`: 53 total URL mentions; ticket links 0; previous pack: False
- `instantseats`: 50 total URL mentions; ticket links 30; previous pack: False
- `zeffy`: 46 total URL mentions; ticket links 37; previous pack: False
- `tixtrack-nliven`: 39 total URL mentions; ticket links 39; previous pack: False
