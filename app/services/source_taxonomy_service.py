from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

CITYSPARK_SOURCE_KEY = "city" + "spark"
CITYSPARK_SOURCE_DISPLAY = "City" + "Spark"


@dataclass(frozen=True)
class SourceTaxonomyEntry:
    key: str
    display_name: str
    source_types: tuple[str, ...]
    domain_patterns: tuple[str, ...]
    trust_notes: str
    cleanup_notes: str
    docs_status: str = "Docs status not reviewed for direct integration."
    direct_connector_status: str = "disabled_by_default"


def taxonomy_entry(
    key: str,
    display_name: str,
    source_types: tuple[str, ...],
    domain_patterns: tuple[str, ...],
    docs_status: str,
    cleanup_notes: str = "Use for provenance and ticket-link QA only.",
) -> SourceTaxonomyEntry:
    return SourceTaxonomyEntry(
        key=key,
        display_name=display_name,
        source_types=source_types,
        domain_patterns=domain_patterns,
        trust_notes="Export-origin provider signal; not a live connector.",
        cleanup_notes=cleanup_notes,
        docs_status=docs_status,
    )


SOURCE_TAXONOMY: dict[str, SourceTaxonomyEntry] = {
    "jambase": SourceTaxonomyEntry(
        key="jambase",
        display_name="JamBase",
        source_types=("ingestion_provider", "event_data_source"),
        domain_patterns=("jambase.com",),
        trust_notes="Provider API record; live API calls remain disabled in this POC.",
        cleanup_notes="Preserve provider IDs and any exposed upstream identifiers.",
    ),
    CITYSPARK_SOURCE_KEY: SourceTaxonomyEntry(
        key=CITYSPARK_SOURCE_KEY,
        display_name=CITYSPARK_SOURCE_DISPLAY,
        source_types=("licensed_vendor_provider",),
        domain_patterns=(),
        trust_notes=(
            "Paid licensed vendor API feed; live API calls remain disabled in "
            "this POC."
        ),
        cleanup_notes="Review, normalize, dedupe, and QA records before app use.",
    ),
    "bandsintown": SourceTaxonomyEntry(
        key="bandsintown",
        display_name="Bandsintown",
        source_types=("upstream_event_source", "artist_data_source"),
        domain_patterns=("bandsintown.com",),
        trust_notes="External upstream/ticket discovery signal.",
        cleanup_notes="Use event-specific links and preserve external IDs.",
    ),
    "axs": SourceTaxonomyEntry(
        key="axs",
        display_name="AXS",
        source_types=("ticketing_provider", "venue_data_source"),
        domain_patterns=("axs.com",),
        trust_notes="Ticketing platform.",
        cleanup_notes="Prefer event-specific ticket pages.",
    ),
    "ticketmaster": SourceTaxonomyEntry(
        key="ticketmaster",
        display_name="Ticketmaster",
        source_types=("ticketing_provider", "classification_provider"),
        domain_patterns=("ticketmaster.com",),
        trust_notes="Ticketing/classification source.",
        cleanup_notes="Reject generic home, artist, browse, and music pages.",
    ),
    "ticketweb": SourceTaxonomyEntry(
        key="ticketweb",
        display_name="TicketWeb",
        source_types=("ticketing_provider",),
        domain_patterns=("ticketweb.com",),
        trust_notes="Ticketing platform.",
        cleanup_notes="Prefer event-specific ticket pages.",
    ),
    "eventbrite": SourceTaxonomyEntry(
        key="eventbrite",
        display_name="Eventbrite",
        source_types=("ticketing_provider",),
        domain_patterns=("eventbrite.com",),
        trust_notes="Ticketing platform.",
        cleanup_notes="Reject checkout-external handoff URLs.",
    ),
    "dice": SourceTaxonomyEntry(
        key="dice",
        display_name="DICE",
        source_types=("ticketing_provider",),
        domain_patterns=("dice.fm", "link.dice.fm"),
        trust_notes="Ticketing platform.",
        cleanup_notes="Reject generic app handoff URLs.",
    ),
    "etix": SourceTaxonomyEntry(
        key="etix",
        display_name="Etix",
        source_types=("ticketing_provider",),
        domain_patterns=("etix.com",),
        trust_notes="Ticketing platform.",
        cleanup_notes="Prefer event-specific ticket pages.",
    ),
    "eventim": SourceTaxonomyEntry(
        key="eventim",
        display_name="Eventim",
        source_types=("ticketing_provider",),
        domain_patterns=("eventim.com",),
        trust_notes="Ticketing platform.",
        cleanup_notes="Prefer event-specific ticket pages.",
    ),
    "seated": SourceTaxonomyEntry(
        key="seated",
        display_name="Seated",
        source_types=("ticketing_provider",),
        domain_patterns=("seated.com",),
        trust_notes="Ticketing/waitlist platform.",
        cleanup_notes="Prefer event-specific ticket pages.",
    ),
    "see-tickets": SourceTaxonomyEntry(
        key="see-tickets",
        display_name="See Tickets",
        source_types=("ticketing_provider",),
        domain_patterns=("seetickets.com", "seetickets.us"),
        trust_notes="Ticketing platform.",
        cleanup_notes="Prefer event-specific ticket pages.",
    ),
    "seatgeek": SourceTaxonomyEntry(
        key="seatgeek",
        display_name="SeatGeek",
        source_types=("ticketing_provider",),
        domain_patterns=("seatgeek.com",),
        trust_notes="Ticketing marketplace.",
        cleanup_notes="Prefer event-specific ticket pages.",
    ),
    "sofar-sounds": SourceTaxonomyEntry(
        key="sofar-sounds",
        display_name="Sofar Sounds",
        source_types=("event_data_source", "ticketing_provider"),
        domain_patterns=("sofarsounds.com",),
        trust_notes="Event/ticketing platform.",
        cleanup_notes="Prefer event-specific ticket pages.",
    ),
    "suitehop": SourceTaxonomyEntry(
        key="suitehop",
        display_name="SuiteHop",
        source_types=("ticketing_provider",),
        domain_patterns=("suitehop.com",),
        trust_notes="Ticketing marketplace.",
        cleanup_notes="Prefer event-specific ticket pages.",
    ),
    "tixr": SourceTaxonomyEntry(
        key="tixr",
        display_name="Tixr",
        source_types=("ticketing_provider",),
        domain_patterns=("tixr.com",),
        trust_notes="Ticketing platform.",
        cleanup_notes="Prefer event-specific ticket pages.",
    ),
    "viagogo": SourceTaxonomyEntry(
        key="viagogo",
        display_name="viagogo",
        source_types=("ticketing_provider",),
        domain_patterns=("viagogo.com",),
        trust_notes="Ticketing marketplace.",
        cleanup_notes="Prefer event-specific ticket pages.",
    ),
    "spotify": SourceTaxonomyEntry(
        key="spotify",
        display_name="Spotify",
        source_types=("artist_data_source", "enrichment_provider"),
        domain_patterns=("spotify.com",),
        trust_notes="Artist enrichment signal.",
        cleanup_notes="Do not treat artist profile links as tickets.",
    ),
    "serpapi": SourceTaxonomyEntry(
        key="serpapi",
        display_name="SerpAPI",
        source_types=("research_provider",),
        domain_patterns=(),
        trust_notes="Approved internal research helper when configured.",
        cleanup_notes="Preserve reviewed source URLs.",
    ),
    "manual_json": SourceTaxonomyEntry(
        key="manual_json",
        display_name="Manual JSON",
        source_types=("file_upload", "manual_review"),
        domain_patterns=(),
        trust_notes="Local admin-uploaded fixture or reviewed data.",
        cleanup_notes="Preserve raw JSON provenance.",
    ),
    "csv_upload": SourceTaxonomyEntry(
        key="csv_upload",
        display_name="CSV Upload",
        source_types=("file_upload",),
        domain_patterns=(),
        trust_notes="Reviewed client/internal file upload.",
        cleanup_notes="Preserve row-level provenance.",
    ),
    "ics": SourceTaxonomyEntry(
        key="ics",
        display_name="ICS",
        source_types=("calendar_feed",),
        domain_patterns=(),
        trust_notes="Approved calendar feed.",
        cleanup_notes="Preserve UID and calendar source URL.",
    ),
    "unknown": SourceTaxonomyEntry(
        key="unknown",
        display_name="Unknown",
        source_types=("unknown",),
        domain_patterns=(),
        trust_notes="Source was not exposed by provider payload.",
        cleanup_notes="Flag for API backfill or manual review.",
    ),
}

EXPORT_DISCOVERED_PROVIDERS = {
    "affiliate-networks": taxonomy_entry(
        "affiliate-networks",
        "Affiliate/tracking networks",
        ("affiliate_tracking",),
        (
            "awin1.com",
            "evyy.net",
            "prf.hn",
            "pxf.io",
            "lusg.net",
            "partnerize.com",
            "impact.com",
        ),
        "Tracking/affiliate domains; not event providers.",
        "Flag as affiliate/tracking handoff and look for a final destination URL.",
    ),
    "opendate": taxonomy_entry(
        "opendate",
        "OpenDate",
        ("ticketing_provider", "upstream_event_source"),
        ("opendate.io",),
        "Developer page found; access appears account/tier gated.",
    ),
    "universe": taxonomy_entry(
        "universe",
        "Universe",
        ("ticketing_provider", "upstream_event_source"),
        ("universe.com",),
        "Official developer portal found; no live connector enabled.",
    ),
    "skiddle": taxonomy_entry(
        "skiddle",
        "Skiddle",
        ("ticketing_provider", "upstream_event_source"),
        ("skiddle.com",),
        "Official API docs found; API key required.",
    ),
    "humanitix": taxonomy_entry(
        "humanitix",
        "Humanitix",
        ("ticketing_provider", "upstream_event_source"),
        ("humanitix.com",),
        "Official public API docs found; API key required.",
    ),
    "ticket-tailor": taxonomy_entry(
        "ticket-tailor",
        "Ticket Tailor",
        ("ticketing_provider",),
        ("tickettailor.com", "buytickets.at"),
        "Official API docs found; no live connector enabled.",
    ),
    "showpass": taxonomy_entry(
        "showpass",
        "Showpass",
        ("ticketing_provider", "upstream_event_source"),
        ("showpass.com",),
        "Official developer docs found; no live connector enabled.",
    ),
    "ovationtix-audienceview": taxonomy_entry(
        "ovationtix-audienceview",
        "AudienceView / OvationTix",
        ("ticketing_provider", "upstream_event_source"),
        ("ovationtix.com",),
        "Official public API reference found; auth may be required.",
    ),
    "holdmyticket": taxonomy_entry(
        "holdmyticket",
        "HoldMyTicket",
        ("ticketing_provider", "upstream_event_source"),
        ("holdmyticket.com",),
        "Official API docs found; API key required.",
    ),
    "ticketnetwork": taxonomy_entry(
        "ticketnetwork",
        "TicketNetwork / Mercury Web Services",
        ("ticketing_provider", "affiliate_tracking"),
        ("ticketnetwork.com", "mercurywebservices.com"),
        "Partner-gated API/product docs found.",
    ),
    "vivid-seats": taxonomy_entry(
        "vivid-seats",
        "Vivid Seats / SkyBox",
        ("ticketing_provider", "affiliate_tracking"),
        ("vividseats.com",),
        "Docs portal found; full access may require login.",
    ),
    "prekindle": taxonomy_entry(
        "prekindle",
        "Prekindle",
        ("ticketing_provider", "upstream_event_source"),
        ("prekindle.com",),
        "Official site mentions an Open API; public reference not found.",
    ),
    "tixtrack-nliven": taxonomy_entry(
        "tixtrack-nliven",
        "TixTrack / Nliven",
        ("ticketing_provider",),
        ("tixtrack.com", "nliven.co"),
        "Webhook docs found; public event discovery docs not found.",
    ),
    "zeffy": taxonomy_entry(
        "zeffy",
        "Zeffy",
        ("ticketing_provider", "event_marketing_platform"),
        ("zeffy.com",),
        "API docs found for payments/contacts/campaigns, not event discovery.",
    ),
    "eventvesta": taxonomy_entry(
        "eventvesta",
        "Event Vesta",
        ("event_marketing_platform", "upstream_event_source"),
        ("eventvesta.com",),
        "Product site found; no public API docs found.",
    ),
    "outhouse-tickets": taxonomy_entry(
        "outhouse-tickets",
        "Outhouse Tickets",
        ("ticketing_provider",),
        ("outhousetickets.com",),
        "No public API docs found.",
    ),
    "venuepilot": taxonomy_entry(
        "venuepilot",
        "VenuePilot",
        ("ticketing_provider",),
        ("venuepilot.com",),
        "Product/support pages found; no public API docs found.",
    ),
    "biletix": taxonomy_entry(
        "biletix",
        "Biletix",
        ("ticketing_provider",),
        ("biletix.com",),
        "No public API docs found.",
    ),
    "speakeasygo": taxonomy_entry(
        "speakeasygo",
        "SpeakeasyGo",
        ("ticketing_provider",),
        ("speakeasygo.com",),
        "Ticketing product page found; no public API docs found.",
    ),
    "eventnoire": taxonomy_entry(
        "eventnoire",
        "Eventnoire",
        ("ticketing_provider", "event_marketing_platform"),
        ("eventnoire.com",),
        "Product/help pages found; no public API docs found.",
    ),
    "my805tix": taxonomy_entry(
        "my805tix",
        "My805Tix / 805Tix",
        ("ticketing_provider",),
        ("my805tix.com", "805tix.com"),
        "Product/event site found; no public API docs found.",
    ),
    "twentyfour-tix": taxonomy_entry(
        "twentyfour-tix",
        "24tix",
        ("ticketing_provider",),
        ("24tix.com",),
        "Help/product pages found; no public API docs found.",
    ),
    "simpletix": taxonomy_entry(
        "simpletix",
        "SimpleTix",
        ("ticketing_provider",),
        ("simpletix.com",),
        "Platform/help pages found; complete public API reference not found.",
    ),
    "tix-com": taxonomy_entry(
        "tix-com",
        "Tix.com",
        ("ticketing_provider",),
        ("tix.com",),
        "Platform site found; public API reference not found.",
    ),
    "ticketleap": taxonomy_entry(
        "ticketleap",
        "TicketLeap",
        ("ticketing_provider",),
        ("ticketleap.com",),
        "No complete official public API docs found.",
    ),
    "afton-tickets": taxonomy_entry(
        "afton-tickets",
        "Afton Tickets / Afton Shows",
        ("ticketing_provider",),
        ("aftontickets.com", "aftonshows.com"),
        "Official site found; no public API docs found.",
    ),
    "instantseats": taxonomy_entry(
        "instantseats",
        "InstantSeats",
        ("ticketing_provider",),
        ("instantseats.com",),
        "Product pages found; no public API docs found.",
    ),
}

SOURCE_TAXONOMY.update(EXPORT_DISCOVERED_PROVIDERS)

AFFILIATE_TRACKING_DOMAINS = EXPORT_DISCOVERED_PROVIDERS[
    "affiliate-networks"
].domain_patterns

SOURCE_ALIASES = {
    "bit": "bandsintown",
    "bands in town": "bandsintown",
    "see tickets": "see-tickets",
    "see tickets us": "see-tickets",
    "see tickets uk": "see-tickets",
    "sofar": "sofar-sounds",
    "sofar sounds": "sofar-sounds",
    "manual": "manual_json",
    "audienceview": "ovationtix-audienceview",
    "ovationtix": "ovationtix-audienceview",
    "mercury web services": "ticketnetwork",
    "mercury": "ticketnetwork",
    "skybox": "vivid-seats",
    "vivid seats": "vivid-seats",
    "tixtrack": "tixtrack-nliven",
    "nliven": "tixtrack-nliven",
    "805tix": "my805tix",
    "24tix": "twentyfour-tix",
    "tix.com": "tix-com",
    "ticket tailor": "ticket-tailor",
    "ticket tailoring": "ticket-tailor",
    "afton tickets": "afton-tickets",
    CITYSPARK_SOURCE_DISPLAY.lower(): CITYSPARK_SOURCE_KEY,
    CITYSPARK_SOURCE_KEY: CITYSPARK_SOURCE_KEY,
}


def normalized_domain(value: str | None) -> str | None:
    cleaned = (value or "").strip().lower()
    if not cleaned:
        return None
    parsed = urlparse(cleaned if "://" in cleaned else f"https://{cleaned}")
    host = (parsed.hostname or "").removeprefix("www.")
    return host or None


def source_key_from_text(value: str | None) -> str | None:
    cleaned = (value or "").strip().lower()
    if not cleaned:
        return None
    normalized = cleaned.replace("_", "-")
    if normalized in SOURCE_TAXONOMY:
        return normalized
    if cleaned in SOURCE_ALIASES:
        return SOURCE_ALIASES[cleaned]
    compact = cleaned.replace(" ", "").replace("-", "")
    for key in SOURCE_TAXONOMY:
        if compact == key.replace("-", "").replace("_", ""):
            return key
    return None


def source_key_from_domain(value: str | None) -> str | None:
    host = normalized_domain(value)
    if not host:
        return None
    for pattern in AFFILIATE_TRACKING_DOMAINS:
        if host == pattern or host.endswith(f".{pattern}"):
            return "affiliate-networks"
    for key, entry in SOURCE_TAXONOMY.items():
        for pattern in entry.domain_patterns:
            if host == pattern or host.endswith(f".{pattern}"):
                return key
    return None


def detect_source_key(value: str | None) -> str | None:
    return source_key_from_text(value) or source_key_from_domain(value)


def provider_key_for_value(value: str | None) -> str:
    return detect_source_key(value) or "unknown"


def source_display_name(key: str | None) -> str:
    if not key:
        return "Unknown"
    entry = SOURCE_TAXONOMY.get(key)
    return entry.display_name if entry else key


def source_docs_status(key: str | None) -> str:
    entry = SOURCE_TAXONOMY.get(key or "")
    return entry.docs_status if entry else SOURCE_TAXONOMY["unknown"].docs_status


def is_affiliate_tracking_source(key: str | None) -> bool:
    entry = SOURCE_TAXONOMY.get(key or "")
    return bool(entry and "affiliate_tracking" in entry.source_types)


def source_chain_entry(
    role: str,
    source_key: str | None,
    source_id: str | None = None,
    url: str | None = None,
) -> dict[str, str]:
    key = source_key or "unknown"
    entry = {
        "role": role,
        "source": key,
        "display_name": source_display_name(key),
    }
    if source_id:
        entry["source_id"] = source_id
    if url:
        entry["url"] = url
    return entry


def dedupe_source_chain(entries: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str, str, str]] = set()
    deduped: list[dict[str, str]] = []
    for entry in entries:
        key = (
            entry.get("role", ""),
            entry.get("source", ""),
            entry.get("source_id", ""),
            entry.get("url", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    return deduped
