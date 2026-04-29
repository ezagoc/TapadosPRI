"""
Parse semi-structured biography text fields into structured records.

Reads biographies.csv and extracts (person, field_type, role, state, year_start, year_end,
organization) tuples from all position, education, and birthplace fields.

Output: data/parsed_positions.csv
"""

import re
import datetime
from typing import Optional
from collections import defaultdict
import pandas as pd
from config import (
    BIOGRAPHIES_CSV,
    PARSED_POSITIONS_CSV,
    MEXICAN_STATES,
    STATE_LOOKUP,
    STATE_LOOKUP_NORM,
    FEDERAL_KEYWORDS,
    FEDERAL_KEYWORDS_NORM,
    INSTITUTION_LOCATIONS,
    INSTITUTION_LOCATIONS_NORM,
    CITY_TO_STATE,
    CITY_TO_STATE_NORM,
    clean_text,
    strip_accents,
    normalize_name,
    MONTH_ABBREV_MAP,
)

# Fields to parse for positions
POSITION_FIELDS = [
    "public_positions",
    "party_positions",
    "govt_positions",
    "labor_positions",
    "other_positions",
]

# Year range pattern: 1940-1946 or 1940–1946 or just 1940
YEAR_RANGE_RE = re.compile(r"(\d{4})\s*[-–]\s*(\d{4})")
SINGLE_YEAR_RE = re.compile(r"\b(1[89]\d{2}|20[0-2]\d)\b")

# Governor pattern
GOVERNOR_RE = re.compile(
    r"governor[,\s]+(?:of\s+)?(?:the\s+)?(?:state\s+of\s+)?([A-Za-z\s]+?)(?:\s*,|\s*\d{4})",
    re.IGNORECASE,
)

# Senator/deputy from state pattern
SENATOR_DEPUTY_RE = re.compile(
    r"(?:senator|federal deputy)\s+from\s+(?:the\s+)?(?:state\s+of\s+)?([A-Za-z\s]+?)(?:\s*,|\s*Dist)",
    re.IGNORECASE,
)

# State legislature pattern
STATE_LEGISLATURE_RE = re.compile(
    r"(?:state legislature|local deputy).+?(?:state\s+of\s+|Legislature\s+of\s+)([A-Za-z\s]+?)(?:\s*,|\s*\d)",
    re.IGNORECASE,
)

# Mayor pattern
MAYOR_RE = re.compile(
    r"mayor[,\s]+([A-Za-z\s]+?)(?:\s*,|\s*\d{4})",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Normalisation helper + pre-computed state variant list
# ---------------------------------------------------------------------------

def _norm(text: str) -> str:
    """Lowercase and strip accents — used for all dictionary/pattern lookups."""
    return strip_accents(text.lower())


# Sorted longest-first so "State of Mexico" is checked before "Mexico".
# Pre-computed once at import time (replaces the per-call build in the old code).
_STATE_VARIANTS_NORM = sorted(
    [(_norm(v), canonical)
     for canonical, (variants, _, _) in MEXICAN_STATES.items()
     for v in variants],
    key=lambda x: len(x[0]), reverse=True,
)


# ---------------------------------------------------------------------------
# Biography cleaning functions — ported from extra-03_clean_biographies.R
# ---------------------------------------------------------------------------

_MONTH_NORM = MONTH_ABBREV_MAP   # alias; defined in config.py

_DATE_PARSE_FORMATS = [
    "%b %d %Y",   # "Mar 4 1906"  (after punctuation normalisation)
    "%B %d %Y",   # "January 1 1910" or "June 14 1949" (padded / full name)
    "%b %Y",      # "Mar 1 1932"  (month-year padded to 1st)
    "%B %Y",      # "March 1 1932"
]


def parse_bio_date(date_str: str) -> dict:
    """
    Parse a messy biographical date string into a structured result.

    Handles:
      "Mar. 4, 1906"        -> full date
      "June 14, 1949"       -> full date
      "1910"                -> year only  (padded to Jan 1)
      "Nov., 1917"          -> month-year (padded to 1st)
      "Jan. 31. 1951"       -> period as day/year separator (normalised)
      "1900s"               -> decade approximation (date=None)
      "Feb. 8, 1946; City"  -> location stripped before parsing
      OCR garbage           -> precision="unparseable", date=None

    Returns:
      {"date": datetime.date | None,
       "precision": "full" | "year_only" | "month_year" | "decade" | "unparseable",
       "decade": int | None}
    """
    result = {"date": None, "precision": "unparseable", "decade": None}

    if not isinstance(date_str, str) or not date_str.strip():
        return result

    s = date_str.strip()

    # --- Decade: "1900s", "1950s" ---
    m = re.match(r"^(\d{4})s$", s)
    if m:
        result["precision"] = "decade"
        result["decade"] = int(m.group(1))
        return result

    # --- OCR garbage: "mp" word, source citation, or no digits at all ---
    if re.search(r"\bmp\b", s) or "sity of Texas" in s or not re.search(r"\d", s):
        return result  # precision stays "unparseable"

    # --- Strip location contamination ---
    # "Feb. 8, 1946; City, State"   -> "Feb. 8, 1946"
    s = re.sub(r";.*$", "", s).strip()
    # "June 14, 1936. Emiliano ..." -> "June 14, 1936"
    s = re.sub(r"(?<=\d{4})[.,]?\s+[A-Z][a-z].*$", "", s).strip()
    # Trailing OCR garbage digits after year
    s = re.sub(r"(?<=\d{4})[.,]?\s+\d+\s+\w.*$", "", s).strip()

    # --- Normalise month abbreviations (Sept -> Sep, etc.) ---
    for bad, good in _MONTH_NORM.items():
        s = re.sub(r"\b" + bad + r"\b", good, s)

    # --- Normalise all punctuation -> spaces, then squish ---
    # "Mar. 4, 1906" -> "Mar 4 1906"
    # "Jan. 31. 1951" -> "Jan 31 1951"
    s_norm = re.sub(r"[.,]", " ", s)
    s_norm = re.sub(r"\s{2,}", " ", s_norm).strip()

    # --- Classify ---
    if re.match(r"^\d{4}$", s_norm):
        result["precision"] = "year_only"
        year = int(s_norm)
        result["decade"] = (year // 10) * 10
        try:
            result["date"] = datetime.date(year, 1, 1)
        except ValueError:
            pass
        return result

    if re.match(r"^[A-Za-z]+ \d{4}$", s_norm):
        result["precision"] = "month_year"
        # Pad to first of month: "Nov 1917" -> "Nov 1 1917"
        s_norm = re.sub(r"^([A-Za-z]+) (\d{4})$", r"\1 1 \2", s_norm)

    # --- Attempt full date parse ---
    for fmt in _DATE_PARSE_FORMATS:
        try:
            d = datetime.datetime.strptime(s_norm, fmt).date()
            if result["precision"] == "unparseable":
                result["precision"] = "full"
            result["date"] = d
            result["decade"] = (d.year // 10) * 10
            return result
        except ValueError:
            continue

    return result


def clean_name_col(raw_name: str) -> dict:
    """
    Extract deceased status and death date from a raw name string,
    returning a clean title-cased name.

    Input:  "aBitia arzoPalo, Jose (Deceased Apr. 19, 1989)"
    Returns:
      {"name_clean": str,
       "deceased":   bool,
       "death_year": int | None,
       "death_date": datetime.date | None}
    """
    if not isinstance(raw_name, str):
        return {"name_clean": "", "deceased": False, "death_year": None, "death_date": None}

    deceased = bool(re.search(r"\(Deceased", raw_name, re.IGNORECASE))

    death_year = None
    death_date = None

    m = re.search(r"\(Deceased\s*([^)]*)\)", raw_name, re.IGNORECASE)
    if m:
        death_info = m.group(1).strip()
        if re.match(r"^\d{4}$", death_info):
            death_year = int(death_info)
        elif re.search(r"[A-Za-z]", death_info) and death_info:
            bd = parse_bio_date(death_info)
            death_date = bd["date"]
            if death_date:
                death_year = death_date.year

    # Strip deceased marker, collapse whitespace, title-case
    name_clean = re.sub(r"\s*\(Deceased[^)]*\)", "", raw_name, flags=re.IGNORECASE)
    name_clean = re.sub(r"\s{2,}", " ", name_clean).strip()
    name_clean = name_clean.title()

    return {
        "name_clean": name_clean,
        "deceased":   deceased,
        "death_year": death_year,
        "death_date": death_date,
    }


def extract_yr_range_py(entry: str) -> dict:
    """
    Extract year range from a position/education entry and return
    the entry text with year information removed.

    Improvement over extract_years(): also cleans years out of role_text,
    removes trailing commas left after year removal, and handles empty text.

    Returns:
      {"text": str | None, "year_start": int | None, "year_end": int | None}
    """
    result = {"text": entry, "year_start": None, "year_end": None}
    if not isinstance(entry, str) or not entry.strip():
        result["text"] = None
        return result

    m = YEAR_RANGE_RE.search(entry)
    if m:
        result["year_start"] = int(m.group(1))
        result["year_end"]   = int(m.group(2))
        # Remove the range (and optional leading comma/space)
        text_out = re.sub(r",?\s*\d{4}\s*[-\u2013]\s*\d{4}", "", entry)
    else:
        singles = SINGLE_YEAR_RE.findall(entry)
        if singles:
            result["year_start"] = int(singles[-1])
            result["year_end"]   = int(singles[-1])
        # Remove trailing single year with optional leading comma
        text_out = re.sub(r",\s*\b(?:1[89]\d{2}|20[0-2]\d)\b\s*$", "", entry)

    # Clean trailing comma/whitespace; collapse double spaces
    text_out = re.sub(r",\s*$", "", text_out).strip()
    text_out = re.sub(r"\s{2,}", " ", text_out).strip()
    result["text"] = text_out if text_out else None
    return result


# ---------------------------------------------------------------------------
# Organization extraction — regex-based structural parsing
# ---------------------------------------------------------------------------
# Strategy: The data follows patterns like:
#   "role, Department/Division, Secretariat of X, location, dates"
# The KEY org is the highest-level named entity (Secretariat, Bank, etc.)
# not the sub-department. We extract the top-level org first.

# Named top-level government organizations
# Use explicit secretariat names to avoid greedy matching across secretariats
_SECRETARIAT_NAMES = [
    "Secretariat of the Treasury",
    "Secretariat of Government",
    "Secretariat of National Defense",
    "Secretariat of Foreign Relations",
    "Secretariat of Public Education",
    "Secretariat of Public Works",
    "Secretariat of Communications and Public Works",
    "Secretariat of Communications and Transportation",
    "Secretariat of Health and Public Welfare",
    "Secretariat of Health",
    "Secretariat of Labor",
    "Secretariat of Labor and Social Welfare",
    "Secretariat of Agriculture",
    "Secretariat of Agriculture and Hydraulic Resources",
    "Secretariat of Agriculture and Livestock",
    "Secretariat of Agrarian Reform",
    "Secretariat of Programming and Budget",
    "Secretariat of Programming and Budgeting",
    "Secretariat of Commerce",
    "Secretariat of Industry and Commerce",
    "Secretariat of Tourism",
    "Secretariat of Energy",
    "Secretariat of Energy and Mines",
    "Secretariat of Social Development",
    "Secretariat of Environment",
    "Secretariat of Public Security",
    "Secretariat of Public Function",
    "Secretariat of the Controller General",
    "Secretariat of the Navy",
    "Secretariat of National Patrimony",
    "Secretariat of the Presidency",
    "Secretariat of Hydraulic Resources",
    "Secretariat of Human Settlements",
    "Secretariat of Urban Development and Ecology",
    # Presidency and Attorney General offices (treated as cabinet-level)
    "Office of the Presidency of Mexico",
    "Office of the Presidency of the Republic",
    "Office of the Presidency",
    "Office of the President of Mexico",
    "Office of the Attorney General of Mexico",
    "Office of the Attorney General of the Federal District",
    "Office of the Federal Attorney General",
    "Office of the Attorney General of the Republic",
    "Office of the Attorney General",
    "Office of the Assistant Attorney General",
    "Ministerio Publico",
]

# Build regex from the list — sorted longest first for correct matching
_SECRETARIAT_NAMES.sort(key=len, reverse=True)
_SECRETARIAT_RE = re.compile(
    r"(" + "|".join(re.escape(s) for s in _SECRETARIAT_NAMES) + r")",
    re.IGNORECASE,
)

# Other named orgs
_OTHER_NAMED_ORG_RE = re.compile(
    r"\b("
    r"Department of the Federal District"
    r"|Department of Agrarian Affairs(?: and Colonization)?"
    r"|Department of Tourism"
    r"|Department of (?:the )?[\w]+(?: [\w]+){0,3}"
    r"|PEMEX|Petroleos Mexicanos"
    r"|CFE|Comision Federal de Electricidad"
    r"|IMSS|ISSSTE|INFONAVIT|CONASUPO|BANRURAL|BANOBRAS"
    r"|National Bank of [\w\s]+?"
    r"|Bank of Mexico"
    r"|Supreme Court of Justice"
    r"|Federal Electoral Commission"
    r"|National Polytechnic Institute|IPN"
    r"|National Finance Bank|Nacional Financiera"
    r"|Altos Hornos de Mexico"
    r"|Foreign Trade Bank"
    r"|Economics Cabinet"
    r"|National Institute of [A-Za-z\s]+?"
    r"|General Hospital(?:\s+[A-Za-z\s]+?)?"
    r"|Hospital [A-Za-z][A-Za-z\s]+?"
    r"|Central Military Hospital|Military Hospital"
    r")"
    r"(?=\s*,|\s+\d{4}|\s*$|\s+and\b|\s+under\b|\))",
    re.IGNORECASE,
)

# "secretary of X" where X is the actual ministry name (when no "Secretariat" in text)
_SECRETARY_OF_RE = re.compile(
    r"\bsecretary of\s+(?:the\s+)?"
    r"(treasury|government|national defense|foreign relations|"
    r"public education|public works|communications[\w\s]*?|health[\w\s]*?|"
    r"labor[\w\s]*?|agriculture[\w\s]*?|agrarian reform|"
    r"programming and budget(?:ing)?|"
    r"commerce|industry[\w\s]*?|tourism|energy[\w\s]*?|"
    r"social development|environment[\w\s]*?|"
    r"public security|public function|navy|"
    r"national patrimony|the presidency|"
    r"hydraulic resources|human settlements|"
    r"urban development[\w\s]*?|controller general[\w\s]*?)"
    r"(?:\s*,|\s+\d{4}|\s*$)",
    re.IGNORECASE,
)

# Education: find institution names anywhere in text
_EDU_INST_PATTERNS = [
    # "at/from Institution" pattern
    re.compile(
        r"(?:from|at)\s+(?:the\s+)?"
        r"((?:University|School|Institute|Instituto|Colegio|Escuela|"
        r"College|Academy|Seminary|Center|Centre|"
        r"Autonomous Technological Institute|"
        r"Free Law School|Military Medical School|"
        r"National Preparatory School|Preparatory School|"
        r"National School of [\w\s]+?|"
        r"Graduate School[\w\s]*?|"
        r"UNAM|IPN|ITESM|ITAM|CEMLA|IPADE|CIDE|"
        r"Harvard|Yale|MIT|Stanford|Columbia|Princeton|Georgetown|"
        r"Oxford|Cambridge|London School|"
        r"Victoria University|American University)"
        r"[^,;]*?)"
        r"(?:\s*,|\s+\d{4}|\s*$)",
        re.IGNORECASE,
    ),
    # "degree, Institution, location" — org after first comma
    re.compile(
        r"(?:degree|diploma|studies)\s*,\s*(?:with [^,]+?,\s*)?"
        r"((?:National School|School|University|Free Law|Military|"
        r"Colegio|Escuela|Instituto|UNAM|IPN|ITESM|ITAM)"
        r"[^,;]*?)"
        r"(?:\s*,|\s+\d{4}|\s*$)",
        re.IGNORECASE,
    ),
    # "professor of X, Institution" — org after subject comma
    re.compile(
        r"professor\s+(?:of\s+)?[^,]+?,\s*"
        r"((?:National School|School|University|Free Law|"
        r"Colegio|Escuela|Instituto|UNAM|IPN|ITESM|ITAM|"
        r"Autonomous|Federal|Military)"
        r"[^,;]*?)"
        r"(?:\s*,|\s+\d{4}|\s*$)",
        re.IGNORECASE,
    ),
    # "National Institute of X" / "International Institute of X" — caught before standalone
    re.compile(
        r"\b((?:National|International)\s+Institute\s+of\s+[^,;]+?)"
        r"(?:\s*,|\s+\d{4}|\s*$)",
        re.IGNORECASE,
    ),
    # Standalone institution mentions (UNAM, Harvard, etc.)
    # Note: UNAM must not capture trailing "at" — use word boundary
    re.compile(
        r"\b(UNAM|IPN|ITESM|ITAM|CEMLA|IPADE|CIDE|"
        r"Harvard University|Yale University|MIT|"
        r"Stanford University|Columbia University|"
        r"Princeton University|Georgetown University|"
        r"Ibero.American University|IberoAmerican University|"
        r"University of [\w\s]+?|"
        r"Colegio de Mexico|Colegio de San Nicolas)"
        r"\b",
        re.IGNORECASE,
    ),
]

# Party organizations — extract the specific party body
_PARTY_PATTERNS = [
    # "IEPES of PRI", "CEN of PRI", "CNC", etc. — specific party bodies
    re.compile(
        r"\b(IEPES of PRI|CEN of PRI|CEN of PAN|CEN of PRD|"
        r"CNC|CTM|CNOP|SNTE|FSTSE|CROC|CROM|UNS|"
        r"IEPES|CEN)\b",
        re.IGNORECASE,
    ),
    # Just the party name as fallback
    re.compile(
        r"\b(PRI|PAN|PRD|PPS|PARM|PST|PSUM|PMT|PCM|PNR|PRM|"
        r"Popular Party|Popular Socialist Party|"
        r"Mexican Communist Party|National Sinarquista Movement)\b",
        re.IGNORECASE,
    ),
]

# Public positions — legislative bodies
_PUBLIC_PATTERNS = [
    re.compile(
        r"\b(Chamber of Deputies|Senate|"
        r"Assembly of the Federal District|"
        r"State Legislature of [\w\s]+?|"
        r"State Legislature|"
        r"Superior Tribunal of Justice|"
        r"Gran Comision)"
        r"(?:\s*,|\s+\d{4}|\s*$|\s+and\b)",
        re.IGNORECASE,
    ),
]

# Labor positions — union and labor federation organizations
_LABOR_ORG_PATTERNS = [
    # Named confederations and federations (acronym first, then full names)
    re.compile(
        r"\b(CTM|Confederacion de Trabajadores de Mexico|"
        r"CNC|Confederacion Nacional Campesina|"
        r"CNOP|Confederacion Nacional de Organizaciones Populares|"
        r"CROM|Confederacion Regional Obrera Mexicana|"
        r"CROC|Confederacion Revolucionaria de Obreros y Campesinos|"
        r"SNTE|Sindicato Nacional de Trabajadores de la Educacion|"
        r"FSTSE|Federacion de Sindicatos de Trabajadores al Servicio del Estado|"
        r"STPRM|Sindicato de Trabajadores Petroleros de la Republica Mexicana|"
        r"SUTERM|Sindicato Unico de Trabajadores Electricistas|"
        r"CTC|UOI|STIMAHCS|SUTGDF)\b"
        r"COPARMEX"
        r"Vertebra",
        re.IGNORECASE,
    ),
    # Generic "Sindicato/Union/Federation of X" — capture the full body name
    re.compile(
        r"\b((?:Sindicato|Union|Federation|Federacion|Confederacion)"
        r"(?:\s+\w+){1,6}?)"
        r"(?:\s*,|\s+\d{4}|\s*$)",
        re.IGNORECASE,
    ),
]

# ---------------------------------------------------------------------------
# Position title extraction
# ---------------------------------------------------------------------------

# Extracts the role/title at the START of a position entry.
# Examples:
#   "Secretary General, CTM, 1970–1976"  -> "Secretary General"
#   "Director General, IMSS"             -> "Director General"
#   "Federal Deputy from Jalisco, 1964"  -> "Federal Deputy"
_POSITION_TITLE_RE = re.compile(
    r"^("
    r"(?:supernumerary\s+)?justice"
    r"|magistrate"
    r"|circuit\s+court\s+judge|district\s+judge"
    r"|acting\s+governor|governor"
    r"|(?:appointed|special|confidential|alternate|extraordinary|personal|first)\s+ambassador"
    r"|rank\s+of\s+(?:special\s+)?ambassador"
    r"|ambassador"
    r"|consul\s+general|consul"
    r"|attorney\s+general"
    r"|subsecretary|undersecretary"
    r"|secretary[\s-]?general|secretarygeneral"
    r"|director\s+general"
    r"|(?:oficial|official)\s+mayor"
    r"|general\s+manager"
    r"|coordinator\s+general|general\s+coordinator"
    r"|inspector\s+general"
    r"|assistant\s+(?:secretary|director\s+general|director|manager|attorney\s+general)"
    r"|auxiliary\s+secretary|technical\s+secretary"
    r"|general\s+(?:adviser|advisor)"
    r"|director|president|vice\s+president"
    r"|coordinator|inspector"
    r"|secretary"
    r"|senator|federal\s+deputy|local\s+deputy|mayor"
    r"|delegate|representative|treasurer|adviser|advisor|assistant"
    r"|head|chief|manager|administrator|comptroller"
    r"|judge"
    r"|member\s+of\s+the\s+executive\s+committee|member"
    r")"
    r"(?=\s*,|\s+of\b|\s+for\b|\s+general\b|\s+from\b|\s+to\b|\s*$)",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Manual keywords — add your own terms here; they will be matched in
# position text and surfaced in the `manual_keyword` output column.
# ---------------------------------------------------------------------------
# Example:
#   _MANUAL_POSITION_KEYWORDS = ["tecnico", "asesor", "interventor"]
_MANUAL_POSITION_KEYWORDS: list[str] = [
    "ceo", 'cfo', 'cto', 
    # Add keywords here
]

_MANUAL_KEYWORDS_RE: Optional[re.Pattern] = (
    re.compile(
        r"\b(" + "|".join(re.escape(k) for k in _MANUAL_POSITION_KEYWORDS) + r")\b",
        re.IGNORECASE,
    )
    if _MANUAL_POSITION_KEYWORDS else None
)

# For govt_positions: role-based org extraction as fallback
# "director of X, Secretariat of Y" — we want Y, but if no named org found,
# capture X as the department/division
_ROLE_ORG_RE = re.compile(
    r"(?:director|head|chief|coordinator|inspector|judge|magistrate|"
    r"oficial mayor|comptroller|auditor|ambassador|attache|consul)\s*"
    r"(?:general\s+)?(?:of|for|in chief of)\s+(?:the\s+)?"
    r"([^,]+?)(?:\s*,|\s+\d{4}|\s*$)",
    re.IGNORECASE,
)

# Judicial org names — catches "Second Division, Third Circuit" etc.
_COURT_ORG_RE = re.compile(
    r"(?:"
    r"Supreme\s+Court(?:\s+of\s+Justice)?|"
    r"Superior\s+Tribunal(?:\s+of\s+Justice)?|"
    r"(?:First|Second|Third|Fourth|Fifth|Sixth|Seventh|Eighth|Ninth|Tenth)\s+"
    r"(?:Civil\s+)?(?:Division|Circuit(?:\s+Court)?|District(?:\s+Court)?)"
    r")",
    re.IGNORECASE,
)


def extract_organization(text: str, field_type: str) -> Optional[str]:
    """
    Extract the organization/institution name from a position entry using
    structural regex patterns. Returns raw extracted name or None.
    """
    if not text or len(text) < 5:
        return None

    if field_type == "birthplace":
        return None

    # Normalize whitespace (OCR sometimes produces double spaces like "Secretariat  of")
    text = re.sub(r"\s{2,}", " ", text)
    # Expand parenthetical acronyms so "Federal Electric Commission (CFE)" → "... CFE"
    text = re.sub(r"\(([A-Z]{2,8})\)", r" \1 ", text)

    # Role-modifier descriptors that look like orgs but aren't
    _SERVICE_DESCRIPTOR_RE = re.compile(
        r"^(?:medical|health|clinical|surgical|dental|coordinated\s+medical|"
        r"health\s+and\s+medical|public\s+health)\s+services?$",
        re.IGNORECASE,
    )

    def _clean_org(org):
        """Clean extracted org name."""
        org = org.strip().rstrip(".,;")
        # Remove year fragments
        org = re.sub(r"\s+\d{4}.*$", "", org)
        # Remove trailing prepositions and role words
        org = re.sub(
            r"\s+(?:at|in|to|from|under|as|during|until|delegate|adviser|"
            r"assistant|representative|coordinator|liaison|committees?)\b.*$",
            "", org, flags=re.IGNORECASE,
        )
        # Collapse multiple spaces
        org = re.sub(r"\s{2,}", " ", org)
        org = org.strip().rstrip(".,;")
        if len(org) < 3:
            return None
        # Reject role-modifier descriptors (e.g., "medical services")
        if _SERVICE_DESCRIPTOR_RE.match(org):
            return None
        return org

    if field_type == "education":
        for pattern in _EDU_INST_PATTERNS:
            m = pattern.search(text)
            if m:
                org = _clean_org(m.group(1))
                if org:
                    # Split on " and " to avoid merging two institutions
                    # e.g., "Free Law School and National School of Law" → "Free Law School"
                    if " and " in org:
                        org = org.split(" and ")[0].strip()
                    if len(org) >= 3:
                        # If a top-level parent university immediately follows the
                        # extracted constituent school (e.g. "National School of Law, UNAM"),
                        # return the parent instead.
                        org_pos = text.lower().find(org.lower())
                        after = text[org_pos + len(org):org_pos + len(org) + 30] if org_pos >= 0 else ""
                        parent = re.match(r"\s*,\s*(UNAM|IPN)\b", after, re.IGNORECASE)
                        if parent:
                            return parent.group(1).upper()
                        return org
        return None

    if field_type == "party_positions":
        for pattern in _PARTY_PATTERNS:
            m = pattern.search(text)
            if m:
                org = _clean_org(m.group(1))
                if org:
                    return org
        return None

    if field_type == "public_positions":
        for pattern in _PUBLIC_PATTERNS:
            m = pattern.search(text)
            if m:
                org = _clean_org(m.group(1))
                if org:
                    return org
        # Fall through to govt for public roles that mention agencies

    if field_type == "labor_positions":
        for pattern in _LABOR_ORG_PATTERNS:
            m = pattern.search(text)
            if m:
                org = _clean_org(m.group(1))
                if org:
                    return org
        # Fall through to general govt patterns as last resort

    # govt_positions, labor_positions, other_positions, public fallback
    # Try explicit Secretariat names first (most precise)
    m = _SECRETARIAT_RE.search(text)
    if m:
        org = _clean_org(m.group(1))
        if org:
            return org

    # Try other named orgs (PEMEX, Bank of Mexico, etc.)
    m = _OTHER_NAMED_ORG_RE.search(text)
    if m:
        org = _clean_org(m.group(1))
        if org:
            return org

    # Try "secretary of X" (the role implies the org)
    m = _SECRETARY_OF_RE.search(text)
    if m:
        org = _clean_org("Secretariat of " + m.group(1).strip())
        if org:
            return org

    # Fallback: role-based extraction for specific roles
    m = _ROLE_ORG_RE.search(text)
    if m:
        org = _clean_org(m.group(1))
        if org:
            return org

    # Judicial fallback: "Second Division, Third Circuit" etc.
    court_matches = _COURT_ORG_RE.findall(text)
    if court_matches:
        return _clean_org(", ".join(court_matches[:2]))

    return None


# ---------------------------------------------------------------------------
# Fuzzy organization normalization — Jaccard + Union-Find clustering
# ---------------------------------------------------------------------------

_ORG_STOP_WORDS = {"the", "of", "for", "and", "in", "to", "at", "a", "an", "de", "la", "del", "y"}

# Structural prefixes that differentiate orgs — two orgs with different
# prefixes should NOT be merged even if token overlap is high
_ORG_PREFIXES = [
    "secretariat of", "department of", "national bank of", "bank of",
    "school of", "national school of", "university of", "institute of",
    "college of", "colegio de",
    "chamber of", "assembly of", "state legislature of",
]


def _org_tokens(name: str) -> set:
    """Tokenize and normalize an organization name for comparison."""
    name = strip_accents(name.lower())
    name = re.sub(r"[^a-z0-9\s]", "", name)
    tokens = set(name.split()) - _ORG_STOP_WORDS
    return {t for t in tokens if len(t) >= 2}


def _org_prefix(name: str) -> Optional[str]:
    """Extract structural prefix to prevent merging different org types."""
    name_lower = name.lower()
    for prefix in _ORG_PREFIXES:
        if name_lower.startswith(prefix):
            return prefix
    return None


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class _UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        if x not in self.parent:
            self.parent[x] = x
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def normalize_organizations(org_series: pd.Series) -> dict:
    """
    Build a mapping from raw org names to canonical (clustered) names.
    Uses Jaccard similarity on token sets with Union-Find clustering.
    Returns dict: raw_name → canonical_name.
    """
    unique_orgs = [o for o in org_series.dropna().unique() if isinstance(o, str) and len(o) >= 3]
    if not unique_orgs:
        return {}

    # Pre-compute token sets and prefixes
    token_sets = {org: _org_tokens(org) for org in unique_orgs}
    prefixes = {org: _org_prefix(org) for org in unique_orgs}

    # Group by shared significant tokens for efficiency
    by_token = defaultdict(list)
    for org, tokens in token_sets.items():
        for t in tokens:
            if len(t) >= 3:  # only group by longer tokens
                by_token[t].append(org)

    # Union-Find clustering with stricter rules
    uf = _UnionFind()
    compared = set()
    for token, orgs in by_token.items():
        for i in range(len(orgs)):
            for j in range(i + 1, len(orgs)):
                pair = (orgs[i], orgs[j]) if orgs[i] < orgs[j] else (orgs[j], orgs[i])
                if pair in compared:
                    continue
                compared.add(pair)

                # Don't merge orgs with different structural prefixes
                # e.g., "Secretariat of the Treasury" vs "Secretariat of Health"
                p_i, p_j = prefixes[orgs[i]], prefixes[orgs[j]]
                if p_i and p_j and p_i == p_j:
                    # Same prefix type — need higher similarity since the prefix
                    # tokens inflate Jaccard. Use content tokens only.
                    content_i = token_sets[orgs[i]] - _org_tokens(p_i)
                    content_j = token_sets[orgs[j]] - _org_tokens(p_j)
                    if not content_i or not content_j:
                        continue
                    sim = _jaccard(content_i, content_j)
                    threshold = 0.6
                else:
                    sim = _jaccard(token_sets[orgs[i]], token_sets[orgs[j]])
                    threshold = 0.7

                if sim >= threshold:
                    uf.union(orgs[i], orgs[j])

    # Build clusters → pick longest name as canonical
    clusters = defaultdict(list)
    for org in unique_orgs:
        root = uf.find(org)
        clusters[root].append(org)

    mapping = {}
    for members in clusters.values():
        canonical = max(members, key=len)
        for m in members:
            mapping[m] = canonical

    return mapping


def extract_position_title(text: str) -> Optional[str]:
    """
    Extract the role/title at the beginning of a position entry.
    Returns the normalised title string or None.

    Uses _POSITION_TITLE_RE for known titles, then falls back to
    _MANUAL_KEYWORDS_RE for any user-defined keywords.
    """
    if not text:
        return None

    m = _POSITION_TITLE_RE.match(text)
    if m:
        return m.group(1).strip().title()

    # Manual keyword fallback
    if _MANUAL_KEYWORDS_RE:
        m = _MANUAL_KEYWORDS_RE.search(text)
        if m:
            return m.group(1).strip().title()

    return None


def extract_years(text: str) -> tuple:
    """Extract (year_start, year_end) from a position entry."""
    # Try range first
    match = YEAR_RANGE_RE.search(text)
    if match:
        return int(match.group(1)), int(match.group(2))
    # Try single years — take the last one as most likely the relevant date
    singles = SINGLE_YEAR_RE.findall(text)
    if singles:
        year = int(singles[-1])
        return year, year
    return None, None


def extract_state_from_text(text: str) -> Optional[str]:
    """
    Multi-tier state extraction from position text.
    Returns canonical state name or None.
    All matching is done on accent-stripped lowercase text for OCR robustness.
    """
    t = _norm(text)

    # Tier 1: Explicit state names — pre-computed list, longest-first
    for variant_norm, canonical in _STATE_VARIANTS_NORM:
        if variant_norm in t:
            return canonical

    # Tier 2: Federal keywords (accent-stripped)
    for kw in FEDERAL_KEYWORDS_NORM:
        if kw in t:
            return "Federal District"

    # Tier 3: City to state (accent-stripped keys, longest-first)
    for city, state in sorted(CITY_TO_STATE_NORM.items(), key=lambda x: len(x[0]), reverse=True):
        if city in t:
            return state

    return None


def extract_state_education(text: str) -> Optional[str]:
    """Extract state from education entry, checking institution names first."""
    t = _norm(text)

    # Check institution locations first (accent-stripped, longest-first)
    for inst, state in sorted(
        INSTITUTION_LOCATIONS_NORM.items(), key=lambda x: len(x[0]), reverse=True
    ):
        if inst in t:
            return state

    # Fall back to general extraction
    return extract_state_from_text(text)


def extract_state_political(text: str) -> Optional[str]:
    """Extract state from political position entries using specific patterns.
    Regex patterns applied to accent-stripped text; captured groups looked up
    in the accent-stripped STATE_LOOKUP_NORM.
    """
    t = _norm(text)

    # Governor pattern
    m = GOVERNOR_RE.search(t)
    if m:
        s = STATE_LOOKUP_NORM.get(m.group(1).strip())
        if s:
            return s

    # Senator/deputy from state
    m = SENATOR_DEPUTY_RE.search(t)
    if m:
        s = STATE_LOOKUP_NORM.get(m.group(1).strip())
        if s:
            return s

    # State legislature
    m = STATE_LEGISLATURE_RE.search(t)
    if m:
        s = STATE_LOOKUP_NORM.get(m.group(1).strip())
        if s:
            return s

    # Mayor — city lookup (accent-stripped)
    m = MAYOR_RE.search(t)
    if m:
        s = CITY_TO_STATE_NORM.get(m.group(1).strip())
        if s:
            return s

    # General extraction
    return extract_state_from_text(text)


def parse_position_entry(entry: str, field_type: str) -> dict:
    """Parse a single semicolon-delimited position entry."""
    entry = clean_text(entry.strip())
    if not entry:
        return None

    # Keep raw text BEFORE any date/year stripping
    role_text_raw = entry

    # Extract position title and manual keyword matches from raw text
    position_title = extract_position_title(entry)
    manual_keyword = (
        _MANUAL_KEYWORDS_RE.search(entry).group(1).strip().title()
        if _MANUAL_KEYWORDS_RE and _MANUAL_KEYWORDS_RE.search(entry)
        else None
    )

    # Use extract_yr_range_py: extracts years AND returns cleaned role_text
    yr          = extract_yr_range_py(entry)
    year_start  = yr["year_start"]
    year_end    = yr["year_end"]
    entry_clean = yr["text"] or entry   # fall back to original if text becomes None

    # State and org extractors receive the ORIGINAL entry (years present don't
    # break pattern matching for governors, secretariats, etc.)
    if field_type == "education":
        state = extract_state_education(entry)
    elif field_type in ("public_positions",):
        state = extract_state_political(entry)
    else:
        state = extract_state_from_text(entry)

    organization = extract_organization(entry, field_type)

    return {
        "field_type":    field_type,
        "role_text_raw": role_text_raw,
        "role_text":     entry_clean,
        "position_title": position_title,
        "manual_keyword": manual_keyword,
        "state":         state,
        "year_start":    year_start,
        "year_end":      year_end,
        "organization":  organization,
    }


def parse_birthplace(birthplace: str) -> Optional[dict]:
    """Parse birthplace field into a record."""
    if not isinstance(birthplace, str) or not birthplace.strip():
        return None

    birthplace = clean_text(birthplace.strip())
    state = extract_state_from_text(birthplace)

    return {
        "field_type":     "birthplace",
        "role_text_raw":  birthplace,
        "role_text":      birthplace,
        "position_title": None,
        "manual_keyword": None,
        "state":          state,
        "year_start":     None,
        "year_end":       None,
        "organization":   None,
    }


def parse_person(row: pd.Series) -> list[dict]:
    """Parse all position fields for one biography row."""
    # --- Clean name and parse birth date (ported from R cleaning step) ---
    name_info            = clean_name_col(row["name"])
    name_clean           = name_info["name_clean"]
    bd                   = parse_bio_date(row.get("birth_date", ""))
    birth_date_clean     = bd["date"].isoformat() if bd["date"] else None
    birth_date_precision = bd["precision"]

    records = []

    # Parse birthplace
    bp = parse_birthplace(row.get("birthplace", ""))
    if bp:
        bp["person_name"]          = name_clean
        bp["birth_date_clean"]     = birth_date_clean
        bp["birth_date_precision"] = birth_date_precision
        records.append(bp)

    # Parse each position field
    for field in POSITION_FIELDS:
        text = row.get(field, "")
        if not isinstance(text, str) or not text.strip():
            continue

        text = clean_text(text)
        entries = text.split(";")
        for entry in entries:
            entry = entry.strip()
            if len(entry) < 5:
                continue
            result = parse_position_entry(entry, field)
            if result:
                result["person_name"]          = name_clean
                result["birth_date_clean"]     = birth_date_clean
                result["birth_date_precision"] = birth_date_precision
                records.append(result)

    # Parse education
    edu = row.get("education", "")
    if isinstance(edu, str) and edu.strip():
        edu = clean_text(edu)
        entries = edu.split(";")
        for entry in entries:
            entry = entry.strip()
            if len(entry) < 5:
                continue
            result = parse_position_entry(entry, "education")
            if result:
                result["person_name"]          = name_clean
                result["birth_date_clean"]     = birth_date_clean
                result["birth_date_precision"] = birth_date_precision
                records.append(result)

    return records


def main():
    print("Loading biographies...")
    df = pd.read_csv(BIOGRAPHIES_CSV)
    print(f"  {len(df)} records loaded")

    # Strip accents from all text fields before any processing
    str_cols = df.select_dtypes(include=["object", "string"]).columns
    df[str_cols] = df[str_cols].apply(
        lambda col: col.map(lambda x: strip_accents(x) if isinstance(x, str) else x)
    )

    all_records = []
    for idx, row in df.iterrows():
        records = parse_person(row)
        all_records.extend(records)
        if (idx + 1) % 500 == 0:
            print(f"  Parsed {idx + 1} / {len(df)} biographies...")

    print(f"\nTotal position records extracted: {len(all_records)}")

    out = pd.DataFrame(all_records)

    # Assign person_id (stable integer per unique person_name)
    person_ids = {name: i + 1 for i, name in enumerate(out["person_name"].unique())}
    out.insert(0, "person_id", out["person_name"].map(person_ids))

    # Assign record_id (unique integer per row)
    out.insert(0, "record_id", range(1, len(out) + 1))

    # Reorder columns
    cols = [
        "record_id", "person_id", "person_name", "field_type",
        "role_text_raw", "role_text", "position_title", "manual_keyword",
        "state", "year_start", "year_end", "organization",
        "birth_date_clean", "birth_date_precision",
    ]
    out = out[cols]

    # Normalize organizations via fuzzy clustering
    print("\nNormalizing organizations via fuzzy clustering...")
    non_bp = out[out["field_type"] != "birthplace"]
    org_mapping = normalize_organizations(non_bp["organization"])
    out["organization"] = out["organization"].map(lambda x: org_mapping.get(x, x) if isinstance(x, str) else x)
    print(f"  {len(org_mapping)} raw org names clustered into {len(set(org_mapping.values()))} canonical names")

    # Stats
    with_state = out["state"].notna().sum()
    with_years = out["year_start"].notna().sum()
    with_org = out["organization"].notna().sum()
    non_bp_count = len(out[out["field_type"] != "birthplace"])
    print(f"\n  Records with state: {with_state} ({100*with_state/len(out):.1f}%)")
    print(f"  Records with years: {with_years} ({100*with_years/len(out):.1f}%)")
    print(f"  Records with org:   {with_org} ({100*with_org/non_bp_count:.1f}% of non-birthplace)")

    print(f"\n  Birth date precision breakdown (one row per person):")
    person_precision = out.drop_duplicates("person_name")["birth_date_precision"]
    for prec, cnt in person_precision.value_counts().items():
        print(f"    {prec}: {cnt}")

    print(f"\nTop 20 organizations per field type:")
    for ft in ["govt_positions", "education", "party_positions", "public_positions"]:
        ft_orgs = out[(out["field_type"] == ft) & out["organization"].notna()]["organization"]
        print(f"\n  {ft} ({len(ft_orgs)} with org):")
        for org, cnt in ft_orgs.value_counts().head(10).items():
            print(f"    {cnt:4d}  {org[:80]}")

    print(f"\nState distribution (top 15):")
    print(out["state"].value_counts().head(15).to_string())

    out.to_csv(PARSED_POSITIONS_CSV, index=False)
    print(f"\nSaved to {PARSED_POSITIONS_CSV}")


if __name__ == "__main__":
    main()
