"""FR-13 — derive a ShippingZone from a Philippine province / region name.

The authoritative mapping lives here (not in client JS). Web Places autocomplete
and the mobile zone-resolve endpoint both call `resolve_zone_name` so a Cebu
address always lands on VisMin with the same fee, regardless of client.

The zone dropdown remains the graceful-degradation fallback: if Places is down,
the key is missing, or the province is unknown, the customer still picks a zone
manually. Unknown input returns None — never a guessed fee.
"""

from __future__ import annotations

import re
import unicodedata

from .models import ShippingZone

# Canonical zone names — must match seed_demo ZONE_SEEDS and admin labels.
ZONE_NCR = "NCR"
ZONE_LUZON = "Luzon"
ZONE_VISMIN = "VisMin"

# Normalized (lowercase, stripped diacritics) province/region tokens → zone.
# Sources: PSA region names, common Places administrative_area_level_1 strings,
# and major cities that Places sometimes returns as the primary region.
_NCR_TOKENS = frozenset(
    {
        "ncr",
        "national capital region",
        "metro manila",
        "metropolitan manila",
        "manila",
        "quezon city",
        "caloocan",
        "las pinas",
        "las piñas",
        "makati",
        "malabon",
        "mandaluyong",
        "marikina",
        "muntinlupa",
        "navotas",
        "paranaque",
        "parañaque",
        "pasay",
        "pasig",
        "pateros",
        "san juan",
        "taguig",
        "valenzuela",
    }
)

_VISMIN_TOKENS = frozenset(
    {
        # Visayas regions / provinces
        "region vi",
        "region vii",
        "region viii",
        "western visayas",
        "central visayas",
        "eastern visayas",
        "visayas",
        "iloilo",
        "iloilo city",
        "capiz",
        "aklan",
        "antique",
        "guimaras",
        "negros occidental",
        "negros oriental",
        "cebu",
        "cebu city",
        "bohol",
        "siquijor",
        "leyte",
        "southern leyte",
        "biliran",
        "samar",
        "eastern samar",
        "northern samar",
        "western samar",
        "bacolod",
        "tacloban",
        "dumaguete",
        "tagbilaran",
        "kalibo",
        "roxas city",
        # Mindanao regions / provinces
        "region ix",
        "region x",
        "region xi",
        "region xii",
        "region xiii",
        "caraga",
        "barmm",
        "bangsamoro",
        "mindanao",
        "zamboanga peninsula",
        "zamboanga del norte",
        "zamboanga del sur",
        "zamboanga sibugay",
        "zamboanga city",
        "zamboanga",
        "northern mindanao",
        "bukidnon",
        "camiguin",
        "lanao del norte",
        "misamis occidental",
        "misamis oriental",
        "cagayan de oro",
        "davao region",
        "davao",
        "davao city",
        "davao del norte",
        "davao del sur",
        "davao occidental",
        "davao oriental",
        "davao de oro",
        "compostela valley",
        "soccsksargen",
        "south cotabato",
        "north cotabato",
        "cotabato",
        "cotabato city",
        "sultan kudarat",
        "sarangani",
        "general santos",
        "agusan del norte",
        "agusan del sur",
        "surigao del norte",
        "surigao del sur",
        "dinagat islands",
        "basilan",
        "lanao del sur",
        "maguindanao",
        "maguindanao del norte",
        "maguindanao del sur",
        "sulu",
        "tawi-tawi",
        "tawi tawi",
        "butuan",
        "iligan",
        "pagadian",
        "dipolog",
        "surigao city",
    }
)

# Luzon is the residual PH default when a province is recognized as Philippine
# but not NCR/VisMin. Explicit Luzon tokens avoid false "unknown" for common
# Places strings (e.g. "Calabarzon", "Central Luzon").
_LUZON_TOKENS = frozenset(
    {
        "luzon",
        "region i",
        "region ii",
        "region iii",
        "region iv-a",
        "region iv-b",
        "region v",
        "ilocos region",
        "ilocos",
        "ilocos norte",
        "ilocos sur",
        "la union",
        "pangasinan",
        "cagayan valley",
        "batanes",
        "cagayan",
        "isabela",
        "nueva vizcaya",
        "quirino",
        "central luzon",
        "aurora",
        "bataan",
        "bulacan",
        "nueva ecija",
        "pampanga",
        "tarlac",
        "zambales",
        "calabarzon",
        "cavite",
        "laguna",
        "batangas",
        "rizal",
        "quezon",
        "mimaropa",
        "marinduque",
        "occidental mindoro",
        "oriental mindoro",
        "palawan",
        "romblon",
        "bicol region",
        "bicol",
        "albay",
        "camarines norte",
        "camarines sur",
        "catanduanes",
        "masbate",
        "sorsogon",
        "cordillera administrative region",
        "cordillera",
        "car",
        "abra",
        "apayao",
        "benguet",
        "ifugao",
        "kalinga",
        "mountain province",
        "baguio",
        "olongapo",
        "angeles",
        "dagupan",
        "naga",
        "legazpi",
        "lucena",
        "puerto princesa",
        "santiago city",
        "tuguegarao",
    }
)


def _normalize(value: str) -> str:
    """Lowercase, strip diacritics, collapse whitespace/punctuation noise."""
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(value))
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^a-z0-9]+", " ", ascii_only.lower()).strip()
    return cleaned


def _match_zone(normalized: str) -> str | None:
    """Exact then substring match against the three zone token sets."""
    if not normalized:
        return None
    if normalized in _NCR_TOKENS:
        return ZONE_NCR
    if normalized in _VISMIN_TOKENS:
        return ZONE_VISMIN
    if normalized in _LUZON_TOKENS:
        return ZONE_LUZON
    for token in _NCR_TOKENS:
        if token in normalized or normalized in token:
            return ZONE_NCR
    for token in _VISMIN_TOKENS:
        if token in normalized or normalized in token:
            return ZONE_VISMIN
    for token in _LUZON_TOKENS:
        if token in normalized or normalized in token:
            return ZONE_LUZON
    return None


def resolve_zone_name(province_or_region: str, *, city: str = "") -> str | None:
    """Map a Places/admin province (and optional city) to a canonical zone name.

    Returns one of NCR / Luzon / VisMin, or None when the input is empty.
    City is checked first so a Makati locality beats a vague region string.
    Unrecognised non-empty input defaults to Luzon (prior client behaviour).
    """
    province = _normalize(province_or_region)
    city_norm = _normalize(city)
    if not province and not city_norm:
        return None
    for candidate in (city_norm, province):
        matched = _match_zone(candidate)
        if matched:
            return matched
    return ZONE_LUZON


def resolve_zone(province_or_region: str, *, city: str = "") -> ShippingZone | None:
    """Return the active ShippingZone row for a province/city, or None."""
    name = resolve_zone_name(province_or_region, city=city)
    if not name:
        return None
    return ShippingZone.objects.filter(name=name, is_active=True).first()
