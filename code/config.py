"""
Shared configuration for the TapadosPRI political network analysis pipeline.
"""

import os
import re
import unicodedata
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DB_ROOT = Path(os.environ.get("TAPADOSPRI_DB_ROOT", str(Path.home() / "Dropbox" / "TapadosPRI"))).expanduser()
DATA_DIR = Path(os.environ.get("TAPADOSPRI_DATA_DIR", str(DB_ROOT / "data"))).expanduser()
OUTPUT_DIR = Path(os.environ.get("TAPADOSPRI_OUTPUT_DIR", str(DB_ROOT / "output"))).expanduser()
LITERATURE_DIR = Path(os.environ.get("TAPADOSPRI_LITERATURE_DIR", str(DB_ROOT / "literature"))).expanduser()
BIOGRAPHIES_DIR = LITERATURE_DIR / "biographies"

BIOGRAPHIES_RAW_TXT = DATA_DIR / "biographies_full.txt"
BIOGRAPHIES_CSV = DATA_DIR / "biographies_corrected.csv"
BIOGRAPHIES_PARSED_CSV = DATA_DIR / "biographies.csv"
CORCHOLATAS_XLSX = DATA_DIR / "candidates" / "corcholatas historicas.xlsx"
PARSED_POSITIONS_CSV       = DATA_DIR / "parsed_positions.csv"
PARSED_CONNECTIONS_CSV     = DATA_DIR / "parsed_connections.csv"
EDUCATION_CSV              = DATA_DIR / "education.csv"
EDUCATION_WIDE_CSV         = DATA_DIR / "education_wide.csv"
BIRTHPLACE_CSV             = DATA_DIR / "birthplace.csv"
PARTY_POSITIONS_CSV        = DATA_DIR / "party_positions.csv"
PARTY_POSITIONS_WIDE_CSV   = DATA_DIR / "party_positions_wide.csv"
PUBLIC_POSITIONS_CSV       = DATA_DIR / "public_positions.csv"
GOVT_POSITIONS_CSV         = DATA_DIR / "govt_positions.csv"
GOVT_POSITIONS_WIDE_CSV    = DATA_DIR / "govt_positions_wide.csv"
LABOR_POSITIONS_CSV        = DATA_DIR / "labor_positions.csv"
LABOR_POSITIONS_WIDE_CSV   = DATA_DIR / "labor_positions_wide.csv"
MILITARY_POSITIONS_CSV     = DATA_DIR / "military_positions.csv"
MILITARY_POSITIONS_WIDE_CSV= DATA_DIR / "military_positions_wide.csv"
OTHER_POSITIONS_CSV        = DATA_DIR / "other_positions.csv"
SHAPEFILE_DIR = DATA_DIR / "shapefiles"
STATES_GEOJSON = SHAPEFILE_DIR / "mexico_states.json"
MAIN_BIOGRAPHIES_PDF = BIOGRAPHIES_DIR / "Mexican_Political_Biographies_1935-2009_Fourth_Edi....pdf"
EARLY_BIOGRAPHIES_PDF = BIOGRAPHIES_DIR / "mexican-political-biographies-1884-1934.pdf"

# ---------------------------------------------------------------------------
# Mexican states: canonical name -> (variants list, centroid lat, centroid lon)
# ---------------------------------------------------------------------------
MEXICAN_STATES = {
    "Aguascalientes":       (["Aguascalientes"], 21.88, -102.29),
    "Baja California":      (["Baja California", "Baja California del Norte", "Baja California Norte"], 30.84, -115.28),
    "Baja California Sur":  (["Baja California Sur", "Baja California del Sur"], 26.04, -111.66),
    "Campeche":             (["Campeche"], 19.83, -90.53),
    "Chiapas":              (["Chiapas"], 16.75, -93.12),
    "Chihuahua":            (["Chihuahua"], 28.63, -106.09),
    "Coahuila":             (["Coahuila", "Coahuila de Zaragoza"], 27.06, -101.71),
    "Colima":               (["Colima"], 19.24, -103.72),
    "Durango":              (["Durango"], 24.03, -104.65),
    "Federal District":     (["Federal District", "Distrito Federal", "Mexico City", "D.F."], 19.43, -99.13),
    "Guanajuato":           (["Guanajuato"], 21.02, -101.26),
    "Guerrero":             (["Guerrero"], 17.44, -99.55),
    "Hidalgo":              (["Hidalgo"], 20.09, -98.76),
    "Jalisco":              (["Jalisco"], 20.66, -103.35),
    "Mexico":               (["State of Mexico", "Mexico", "Estado de Mexico", "Edo. de Mexico"], 19.49, -99.69),
    "Michoacan":            (["Michoacan"], 19.57, -101.71),
    "Morelos":              (["Morelos"], 18.68, -99.23),
    "Nayarit":              (["Nayarit"], 21.75, -104.85),
    "Nuevo Leon":           (["Nuevo Leon"], 25.59, -99.99),
    "Oaxaca":               (["Oaxaca"], 17.07, -96.73),
    "Puebla":               (["Puebla"], 19.04, -98.20),
    "Queretaro":            (["Queretaro"], 20.59, -100.39),
    "Quintana Roo":         (["Quintana Roo"], 19.18, -88.48),
    "San Luis Potosi":      (["San Luis Potosi"], 22.15, -100.98),
    "Sinaloa":              (["Sinaloa"], 24.81, -107.39),
    "Sonora":               (["Sonora"], 29.07, -110.96),
    "Tabasco":              (["Tabasco"], 17.84, -92.62),
    "Tamaulipas":           (["Tamaulipas"], 24.27, -98.84),
    "Tlaxcala":             (["Tlaxcala"], 19.32, -98.16),
    "Veracruz":             (["Veracruz"], 19.17, -96.13),
    "Yucatan":              (["Yucatan"], 20.97, -89.62),
    "Zacatecas":            (["Zacatecas"], 22.77, -102.58),
}

# Build a reverse lookup: variant (lowered) -> canonical name
STATE_LOOKUP = {}
for canonical, (variants, _, _) in MEXICAN_STATES.items():
    for v in variants:
        STATE_LOOKUP[v.lower()] = canonical
    STATE_LOOKUP[canonical.lower()] = canonical

# ---------------------------------------------------------------------------
# Federal keywords — if present in a position entry, location = Federal District
# ---------------------------------------------------------------------------
FEDERAL_KEYWORDS = [
    "secretariat of",
    "secretaria de",
    "pemex",
    "bank of mexico",
    "banco de mexico",
    "supreme court",
    "chamber of deputies",
    "senate",
    "cen of pri",
    "cen of pan",
    "cen of prd",
    "office of the presidency",
    "office of the attorney general of mexico",
    "attorney general of mexico",
    "national securities commission",
    "national institute",
    "federal electric commission",
    "cfe",
    "infonavit",
    "conasupo",
    "nafinsa",
    "nacional financiera",
    "imss",
    "issste",
    "fondo de cultura economica",
    "economics cabinet",
    "plurinominal",
]

# ---------------------------------------------------------------------------
# Institution → state mapping (for education field)
# ---------------------------------------------------------------------------
INSTITUTION_LOCATIONS = {
    "unam": "Federal District",
    "national school of law": "Federal District",
    "national school of economics": "Federal District",
    "national preparatory school": "Federal District",
    "national school of political": "Federal District",
    "ipn": "Federal District",
    "higher school of economics, ipn": "Federal District",
    "national polytechnic": "Federal District",
    "colegio de mexico": "Federal District",
    "ibero-american university": "Federal District",
    "itam": "Federal District",
    "autonomous technological institute": "Federal District",
    "free law school": "Federal District",
    "heroic military college": "Federal District",
    "higher war college": "Federal District",
    "military medical school": "Federal District",
    "national normal school": "Federal District",
    "itesm": "Nuevo Leon",
    "technological institute of higher studies, monterrey": "Nuevo Leon",
    "technological institute of higher studies, monterr": "Nuevo Leon",
    "university of guadalajara": "Jalisco",
    "university of michoacan": "Michoacan",
    "university of sonora": "Sonora",
    "university of veracruz": "Veracruz",
    "juarez institute": "Tabasco",
    "university of yucatan": "Yucatan",
    "autonomous university of puebla": "Puebla",
    "autonomous university of nuevo leon": "Nuevo Leon",
    "autonomous university of the state of mexico": "Mexico",
    "autonomous university of chihuahua": "Chihuahua",
    "autonomous university of coahuila": "Coahuila",
    "autonomous university of sinaloa": "Sinaloa",
    "autonomous university of tamaulipas": "Tamaulipas",
    "autonomous university of guerrero": "Guerrero",
    "autonomous university of san luis potosi": "San Luis Potosi",
    "autonomous university of tabasco": "Tabasco",
    "autonomous university of zacatecas": "Zacatecas",
    "autonomous university of baja california": "Baja California",
    "autonomous university of queretaro": "Queretaro",
    "university of colima": "Colima",
    "university of guanajuato": "Guanajuato",
}

# ---------------------------------------------------------------------------
# City → state mapping (for position text)
# ---------------------------------------------------------------------------
CITY_TO_STATE = {
    "guadalajara": "Jalisco",
    "monterrey": "Nuevo Leon",
    "puebla": "Puebla",
    "merida": "Yucatan",
    "toluca": "Mexico",
    "morelia": "Michoacan",
    "hermosillo": "Sonora",
    "chihuahua": "Chihuahua",
    "saltillo": "Coahuila",
    "villahermosa": "Tabasco",
    "tuxtla gutierrez": "Chiapas",
    "oaxaca": "Oaxaca",
    "veracruz": "Veracruz",
    "jalapa": "Veracruz",
    "xalapa": "Veracruz",
    "aguascalientes": "Aguascalientes",
    "culiacan": "Sinaloa",
    "mazatlan": "Sinaloa",
    "durango": "Durango",
    "acapulco": "Guerrero",
    "chilpancingo": "Guerrero",
    "iguala": "Guerrero",
    "tijuana": "Baja California",
    "mexicali": "Baja California",
    "ensenada": "Baja California",
    "la paz": "Baja California Sur",
    "cancun": "Quintana Roo",
    "chetumal": "Quintana Roo",
    "campeche": "Campeche",
    "colima": "Colima",
    "cuernavaca": "Morelos",
    "pachuca": "Hidalgo",
    "queretaro": "Queretaro",
    "san luis potosi": "San Luis Potosi",
    "tampico": "Tamaulipas",
    "ciudad victoria": "Tamaulipas",
    "tepic": "Nayarit",
    "zacatecas": "Zacatecas",
    "tlaxcala": "Tlaxcala",
    "nogales": "Sonora",
    "tapachula": "Chiapas",
    "tenosique": "Tabasco",
    "cordoba": "Veracruz",
    "orizaba": "Veracruz",
    "leon": "Guanajuato",
    "irapuato": "Guanajuato",
    "celaya": "Guanajuato",
    "ciudad juarez": "Chihuahua",
    "nuevo laredo": "Tamaulipas",
    "matamoros": "Tamaulipas",
    "reynosa": "Tamaulipas",
    "torreon": "Coahuila",
    "badiraguato": "Sinaloa",
    "magdalena de kino": "Sonora",
}

# ---------------------------------------------------------------------------
# Election pairs: year -> (winner name in CSV, closest loser name in CSV)
# Names must match exactly as they appear in biographies.csv
# ---------------------------------------------------------------------------
ELECTION_PAIRS = {
    1988: (
        "salinas de gortari, carlos",
        "Bartlett (diaz), Manuel",
    ),
    1982: (
        "de la Madrid (hurtado), Miguel",
        # Diaz Serrano — need to confirm exact CSV name
        None,
    ),
    1994: (
        "colosio (Murrieta), luis donaldo",
        # Aspe Armella — need to confirm exact CSV name
        None,
    ),
}

# 1988 "seis distinguidos" and other tapados
TAPADOS_1988 = [
    "salinas de gortari, carlos",
    "Bartlett (diaz), Manuel",
    "del Mazo gonzalez, alfredo",
    "garcia raMirez, sergio",
    # Others to be matched from corcholatas xlsx
]

# ---------------------------------------------------------------------------
# Mapping from canonical state names to GeoJSON 'name' property
# ---------------------------------------------------------------------------
STATE_TO_GEOJSON = {
    "Aguascalientes": "Aguascalientes",
    "Baja California": "Baja California",
    "Baja California Sur": "Baja California Sur",
    "Campeche": "Campeche",
    "Chiapas": "Chiapas",
    "Chihuahua": "Chihuahua",
    "Coahuila": "Coahuila",
    "Colima": "Colima",
    "Durango": "Durango",
    "Federal District": "Ciudad de México",
    "Guanajuato": "Guanajuato",
    "Guerrero": "Guerrero",
    "Hidalgo": "Hidalgo",
    "Jalisco": "Jalisco",
    "Mexico": "México",
    "Michoacan": "Michoacán",
    "Morelos": "Morelos",
    "Nayarit": "Nayarit",
    "Nuevo Leon": "Nuevo León",
    "Oaxaca": "Oaxaca",
    "Puebla": "Puebla",
    "Queretaro": "Querétaro",
    "Quintana Roo": "Quintana Roo",
    "San Luis Potosi": "San Luis Potosí",
    "Sinaloa": "Sinaloa",
    "Sonora": "Sonora",
    "Tabasco": "Tabasco",
    "Tamaulipas": "Tamaulipas",
    "Tlaxcala": "Tlaxcala",
    "Veracruz": "Veracruz",
    "Yucatan": "Yucatán",
    "Zacatecas": "Zacatecas",
}

# Reverse: GeoJSON name -> canonical
GEOJSON_TO_STATE = {v: k for k, v in STATE_TO_GEOJSON.items()}

# ---------------------------------------------------------------------------
# PDF artifact patterns to clean from extracted text
# ---------------------------------------------------------------------------
PDF_ARTIFACTS = [
    r"sity of Texas Press,?\s*2011\.?\s*ProQuest Ebook\s*cID=\d+\.?",
    r"\bmp,\s*(?:es,\s*1935–2009|)",
    r"\bmp,\b",
]

# ---------------------------------------------------------------------------
# Name normalization
# ---------------------------------------------------------------------------
def strip_accents(text: str) -> str:
    """Remove accent marks from text."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.category(c).startswith("M"))


def normalize_name(name: str) -> str:
    """
    Normalize a name for fuzzy matching.
    Handles the CSV's odd capitalization and parenthetical maternal surnames.
    e.g. 'salinas de gortari, carlos' -> 'salinas de gortari carlos'
    e.g. 'Bartlett (diaz), Manuel' -> 'bartlett diaz manuel'
    """
    name = name.lower()
    name = strip_accents(name)
    # Remove content markers like (Deceased ...)
    name = re.sub(r"\(deceased[^)]*\)", "", name)
    # Convert parenthetical surnames: (diaz) -> diaz
    name = re.sub(r"\(([^)]+)\)", r"\1", name)
    # Remove punctuation except spaces
    name = re.sub(r"[^a-z\s]", "", name)
    # Collapse whitespace
    name = re.sub(r"\s+", " ", name).strip()
    return name


def extract_last_name(name: str) -> str:
    """Extract the primary last name (before comma or first word)."""
    normalized = normalize_name(name)
    # CSV format is "lastname, firstname" — take part before first space
    # after normalization commas are gone, so split and take first token
    parts = normalized.split()
    return parts[0] if parts else ""


def clean_text(text: str) -> str:
    """Remove PDF artifacts from extracted text."""
    if not isinstance(text, str):
        return ""
    for pattern in PDF_ARTIFACTS:
        text = re.sub(pattern, "", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Accent-normalized lookup tables
# Built automatically from the tables above — do not edit directly.
# Use these together with strip_accents(text.lower()) for robust OCR matching
# where source text may have dropped or mangled accent marks.
# ---------------------------------------------------------------------------
STATE_LOOKUP_NORM         = {strip_accents(k): v for k, v in STATE_LOOKUP.items()}
FEDERAL_KEYWORDS_NORM     = [strip_accents(kw) for kw in FEDERAL_KEYWORDS]
CITY_TO_STATE_NORM        = {strip_accents(k): v for k, v in CITY_TO_STATE.items()}
INSTITUTION_LOCATIONS_NORM = {strip_accents(k): v for k, v in INSTITUTION_LOCATIONS.items()}


# Month abbreviations that Python's %b strptime cannot handle natively.
# "Sept" (4 letters) and locale-variant spellings are the main offenders.
MONTH_ABBREV_MAP = {
    "Sept": "Sep",
    "June": "Jun",
    "July": "Jul",
}

# ---------------------------------------------------------------------------
# Person name corrections
#
# Corrupted person names (death-date fragments and name bleed) are now repaired
# reproducibly at the source by 00-preprocess/03_fix_person_names.py, which
# rewrites biographies_corrected.csv before 04_parse_positions.py runs.
# The old person_id → name override map lived here, but it was made obsolete by
# that fix (and unsafe, since re-running 04 re-assigns person_ids). Removed.
# ---------------------------------------------------------------------------
