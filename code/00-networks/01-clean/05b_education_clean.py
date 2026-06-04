"""
05b_education_clean.py

Post-processing fixes for education.csv (output of 05_education.py).
Reads  data/education.csv
Writes data/clean_positions/education.csv  (+  `modified` column = 1 if any field changed).

Fields touched: organization, state, role_text_raw, role_text,
                year_start, year_end, degree_field, foreign_degree.

Fixes applied:
  ── organization / state ────────────────────────────────────────────────────
   1.  Strip OCR garbage from org  ("NNN mexican political biographie …")
   2.  Strip context pollution from org  ("seminary when Archbishop … was director")
   3.  Strip trailing year / comma artifacts  ("School, 1952" → "School")
   4.  Fix "National Preparatory School No. 4" hallucination from NER
   5.  Restore truncated School No. numbers  ("Secondary School No" → "Secondary School No. 3")
   6.  Clear state / city names captured as institution
   7.  Prefer university over "School of X" when university appears in raw text
   8.  Re-extract truncated university names  ("University of Nuevo" → "University of Nuevo Leon")
   9.  Normalize UAM variants  ("Metropolitan University" → "Autonomous Metropolitan University")
  10.  Final trailing-artifact strip (after org reconstruction)
  11.  Restore numbered-school institution when org is null
  12.  Infer missing state from city names (skips foreign-country texts)

  ── role_text_raw / years ───────────────────────────────────────────────────
  13.  Remove OCR book-title fragments from raw text
       ("s, 1935–2009", "144 mexican political biographie", "Iberomp", "sity of")
  14.  Re-extract year_start / year_end from cleaned raw text,
       stripping thesis-title text and historical references before extraction

  ── degree_field ────────────────────────────────────────────────────────────
  15.  Fix business→political_sci when political context is unambiguous
       ("School of Political and Social Sciences", "political science and public admin", …)
  16.  Fix other→architecture for urbanism records

  ── foreign_degree ──────────────────────────────────────────────────────────
  17.  Detect foreign degrees missed by 05_education.py:
       University of London, Salamanca, Toulouse, Navarra, Brookings,
       Ecole Pratique, Humboldt University, and others.
"""

import re
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

CODE_DIR = Path(__file__).resolve().parents[2]
if str(CODE_DIR) not in sys.path:
    sys.path.append(str(CODE_DIR))

from config import EDUCATION_CSV, DATA_DIR

CLEAN_DIR           = DATA_DIR / "clean_positions"
EDUCATION_CLEAN_CSV = CLEAN_DIR / "education.csv"


# ============================================================
# ── ORGANIZATION / STATE FIXES (original batch) ─────────────
# ============================================================

# Fix 1: OCR garbage in org  ("NNN mexican political biographie")
_OCR_GARBAGE_RE = re.compile(
    r"\s*\d{2,}\s+mexican\s+political\s+biograph\w*\s*", re.I,
)

def _fix_ocr(org: str) -> Optional[str]:
    cleaned = _OCR_GARBAGE_RE.sub("", org)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip().rstrip(".,; ")
    return cleaned if len(cleaned) >= 3 else None


# Fix 2: Context pollution  ("when … was director", "where … located")
_CONTEXT_POLLUTION_RE = re.compile(
    r"\s+when\s+.+$|\s+where\s+.+$|\s+whose\s+.+$", re.I | re.DOTALL,
)
_ORDINAL_START_RE = re.compile(r"^\d+(?:st|nd|rd|th)\b", re.I)

def _fix_context(org: str) -> Optional[str]:
    cleaned = _CONTEXT_POLLUTION_RE.sub("", org).strip().rstrip(".,; ")
    if _ORDINAL_START_RE.match(cleaned):
        return None
    return cleaned if len(cleaned) >= 3 else None


# Fix 3 / 10 (shared): trailing year / comma artifacts
_TRAIL_YEAR_RE = re.compile(r",?\s*\d{4}[\s\-–\d]*$")
_TRAIL_JUNK_RE = re.compile(r"[,\.;:\s]+$")

def _fix_trail(org: str) -> Optional[str]:
    org = _TRAIL_YEAR_RE.sub("", org).strip()
    org = _TRAIL_JUNK_RE.sub("", org).strip()
    return org if len(org) >= 3 else None


# Fix 4: "National Preparatory School No. 4" hallucination
def _fix_nps_hallucination(org: str, raw: str) -> str:
    if not re.match(r"National Preparatory School No\.", org, re.I):
        return org
    m = re.search(r"National Preparatory School\s+No\.?\s*(\d+)", raw, re.I)
    if m:
        return f"National Preparatory School No. {m.group(1)}"
    if re.search(r"National Preparatory School(?!\s+No)", raw, re.I):
        return "National Preparatory School"
    m2 = re.search(r"Preparatory School\s+No\.?\s*(\d+)", raw, re.I)
    if m2:
        return f"Preparatory School No. {m2.group(1)}"
    return "National Preparatory School"


# Fix 5: Restore truncated School No. numbers
_SCHOOL_NO_STEM_RE = re.compile(
    r"^(.+?(?:Secondary|Preparatory|Urban|Primary|Night\s+Secondary|"
    r"Public\s+Secondary)\s+(?:School\s+)?)"
    r"No\.?\s*$",
    re.I,
)

def _fix_school_no_trunc(org: str, raw: str) -> str:
    m = _SCHOOL_NO_STEM_RE.match(org.strip())
    if not m:
        return org
    stem = m.group(1).strip()
    m2 = re.search(re.escape(stem) + r"\s+No\.?\s*(\d+)", raw, re.I)
    return f"{stem} No. {m2.group(1)}" if m2 else org


# Fix 6: State / city names captured as institution → null
_STATE_NAMES_LOWER = {
    # Mexican state names
    "aguascalientes", "baja california", "baja california sur",
    "campeche", "chiapas", "chihuahua", "coahuila", "colima",
    "durango", "guanajuato", "guerrero", "hidalgo", "jalisco",
    "mexico", "michoacan", "morelos", "nayarit", "nuevo leon",
    "oaxaca", "puebla", "queretaro", "quintana roo",
    "san luis potosi", "sinaloa", "sonora", "tabasco",
    "tamaulipas", "tlaxcala", "veracruz", "yucatan", "zacatecas",
    "federal district", "mexico city",
    # Major Mexican cities commonly misidentified as institutions
    "salamanca", "orizaba", "jalapa", "xalapa", "guadalajara",
    "monterrey", "morelia", "hermosillo", "culiacan", "tampico",
    "tepic", "villahermosa", "campeche", "toluca", "cuernavaca",
    "pachuca", "queretaro", "oaxaca", "merida", "durango",
    "zacatecas", "saltillo", "acapulco", "chilpancingo", "tuxtla",
    "los mochis", "cananea", "colima",
}

def _fix_state_as_org(org: str) -> Optional[str]:
    return None if org.strip().lower() in _STATE_NAMES_LOWER else org


# University extraction helper (used by Fix 7 and 8)
_FULL_UNIV_RE = re.compile(
    r"\b("
    r"(?:(?:Autonomous|National|Free|Popular|Autonomous\s+Metropolitan|"
    r"Metropolitan\s+Autonomous|Benito\s+Juarez|Juarez|La\s+Salle|Anahuac|"
    r"Intercontinental|Pan\s+American|Ibero.?American|Superior|Higher|"
    r"Public|Technological|Military|Naval)\s+)*"
    r"University(?:\s+of(?:\s+the)?)?"
    r"(?:\s+[A-Za-z]+){1,6}"
    r")"
    r"(?=\s*,|\s+\d{4}|\s*$)",
    re.I,
)
_KNOWN_UNIV_ABBREV_RE = re.compile(
    r"\b(UNAM|IPN\b|ITAM\b|ITESM\b|CIDE\b|IPADE\b|Colegio\s+de\s+Mexico)\b",
    re.I,
)

def _extract_best_univ(raw: str) -> Optional[str]:
    m_full = _FULL_UNIV_RE.search(raw)
    if m_full:
        return m_full.group(1).strip().rstrip(".,; ")
    m_abbrev = _KNOWN_UNIV_ABBREV_RE.search(raw)
    return m_abbrev.group(1).strip() if m_abbrev else None


# Fix 7: "School of X" → prefer university when explicitly in raw text
_SCHOOL_OF_RE = re.compile(
    r"^(?:National\s+School\s+of|Free\s+Law\s+School|School\s+of)\b", re.I,
)

def _fix_school_prefer_univ(org: str, raw: str) -> str:
    if not _SCHOOL_OF_RE.match(org.strip()):
        return org
    univ = _extract_best_univ(raw)
    return univ if univ else org


# Fix 8: Re-extract truncated university names (word-boundary bug in 04)
_TRUNC_ENDINGS_RE = re.compile(
    r"\b(Nuevo|San|Los|La|Las|El|the)\s*$|University\s+of\s*$", re.I,
)

def _fix_truncated_univ(org: str, raw: str) -> str:
    if not re.search(r"\bUniversity\b", org, re.I):
        return org
    if not _TRUNC_ENDINGS_RE.search(org):
        return org
    univ = _extract_best_univ(raw)
    return univ if univ else org


# Fix 9: Normalize UAM variants
_UAM_MATCH_RE = re.compile(
    r"Metropolitan\s+Autonomous\s+University|Autonomous\s+Metropolitan\s+University"
    r"|^Metropolitan\s+University$",
    re.I,
)
_CAMPUS_RE = re.compile(r"\b(Xochimilco|Azcapotzalco|Iztapalapa)\s+Campus\b", re.I)

def _fix_uam(org: str, raw: str) -> str:
    if not _UAM_MATCH_RE.search(org):
        return org
    base = "Autonomous Metropolitan University"
    m = _CAMPUS_RE.search(raw)
    return f"{base}, {m.group(1)} Campus" if m else base


# Fix 11: Restore numbered-school institution when org is null
_NUMBERED_SCHOOL_RE = re.compile(
    r"\b("
    r"(?:(?:Night\s+)?(?:Public\s+)?Secondary(?:\s+Boarding\s+School\s+of\s+Secondary)?|"
    r"Preparatory|Night\s+Workers'?\s*Night?)\s+"
    r"(?:School\s+)?No\.?\s*\d+"
    r"(?:\s+for\s+(?:Boys|Girls))?"
    r")",
    re.I,
)
_SECONDARY_NO_RE = re.compile(r"\bSecondary\s+No\.?\s*\d+\b", re.I)

def _fix_restore_school(org, raw: str):
    if pd.notna(org):
        return org
    m = _NUMBERED_SCHOOL_RE.search(raw)
    if m:
        return m.group(1).strip().rstrip("., ")
    m2 = _SECONDARY_NO_RE.search(raw)
    return m2.group(0).strip() if m2 else org


# Fix 12: Infer missing state from city names (skips foreign-country texts)
_CITY_STATE = sorted(
    [
        ("san jose de gracia", "Sinaloa"), ("temazcalcingo", "Mexico"),
        ("ixmiquilpan", "Hidalgo"),        ("nacajuca", "Tabasco"),
        ("chilpancingo", "Guerrero"),       ("chapingo", "Mexico"),
        ("los mochis", "Sinaloa"),          ("agua prieta", "Sonora"),
        ("calkini", "Campeche"),            ("orizaba", "Veracruz"),
        ("jalapa", "Veracruz"),             ("xalapa", "Veracruz"),
        ("cananea", "Sonora"),              ("guadalajara", "Jalisco"),
        ("monterrey", "Nuevo Leon"),        ("morelia", "Michoacan"),
        ("hermosillo", "Sonora"),           ("culiacan", "Sinaloa"),
        ("tampico", "Tamaulipas"),          ("tepic", "Nayarit"),
        ("colima", "Colima"),               ("villahermosa", "Tabasco"),
        ("toluca", "Mexico"),               ("cuernavaca", "Morelos"),
        ("tlaxcala", "Tlaxcala"),           ("pachuca", "Hidalgo"),
        ("guanajuato", "Guanajuato"),       ("tuxtla", "Chiapas"),
        ("chilpancingo", "Guerrero"),       ("acapulco", "Guerrero"),
        ("nueva rosita", "Coahuila"),       ("magdalena de kino", "Sonora"),
        ("calvillo", "Aguascalientes"),     ("coapa", "Federal District"),
        ("leon", "Guanajuato"),
    ],
    key=lambda x: -len(x[0]),
)
_FOREIGN_CTX_RE = re.compile(
    r"\b(Spain|France|Germany|Italy|England|United\s+Kingdom|United\s+States|"
    r"USA\b|Argentina|Chile|Brazil|Cuba|Colombia|Switzerland|Belgium|"
    r"Canada|Japan|Soviet\s+Union|Russia|Austria|Netherlands|Sweden|"
    r"University\s+of\s+Salamanca|University\s+of\s+Madrid|University\s+of\s+Paris|"
    r"University\s+of\s+Rome|University\s+of\s+Berlin|University\s+of\s+Vienna|"
    r"University\s+of\s+Geneva|University\s+of\s+Brussels|Sorbonne|"
    r"Complutense|Sciences\s+Po)\b",
    re.I,
)

def _fix_infer_state(state, raw: str):
    if pd.notna(state):
        return state
    if not isinstance(raw, str) or _FOREIGN_CTX_RE.search(raw):
        return state
    raw_l = raw.lower()
    for city, st in _CITY_STATE:
        if city in raw_l:
            return st
    return state


# ============================================================
# ── RAW TEXT / YEAR FIXES ────────────────────────────────────
# ============================================================

# Fix 13: Remove OCR book-title fragments from role_text_raw
_OCR_BOOK_TITLE_RE = re.compile(
    r"\bs,\s*1935[–\-]2009\b"              # "s, 1935–2009" (book subtitle fragment)
    r"|\bBiograph\w*,?\s*1935[–\-]2009\b"  # "Biographies, 1935–2009"
    r"|\d{2,}\s+mexican\s+political\s+biograph\w*\s*"  # "144 mexican political biographie"
    r"|\bIberomp\b"                         # truncated "Ibero-American"
    r"|\bsity\s+of\b",                     # page-break truncation of "University of"
    re.I,
)

def _clean_raw(text: str) -> str:
    cleaned = _OCR_BOOK_TITLE_RE.sub(" ", text)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned


# Fix 14: Re-extract years after cleaning, ignoring thesis title years
_YEAR_RANGE_RE  = re.compile(r"(\d{4})\s*[-–]\s*(\d{4})")
_SINGLE_YEAR_RE = re.compile(r"\b(1[89]\d{2}|20[0-2]\d)\b")
_THESIS_STRIP_RE = re.compile(
    r",?\s*with\s+(?:a\s+)?(?:thesis|dissertation)\s+"
    r"(?:titled?|entitled|on|about|examining|dealing|addressing)\b.+$",
    re.I | re.DOTALL,
)
_HIST_REF_RE = re.compile(
    r"\bConstitution\s+of\s+\d{4}\b"          # "Constitution of 1857"
    r"|\b(?:since|until|after|before)\s+\d{4}\b",  # "since 1910"
    re.I,
)

def _reextract_years(raw_clean: str):
    """Re-extract year_start/year_end from cleaned text, stripping thesis titles."""
    t = _THESIS_STRIP_RE.sub("", raw_clean)
    t = _HIST_REF_RE.sub("", t)
    m = _YEAR_RANGE_RE.search(t)
    if m:
        return int(m.group(1)), int(m.group(2))
    singles = _SINGLE_YEAR_RE.findall(t)
    if singles:
        yr = int(singles[-1])
        return yr, yr
    return None, None

def _strip_years_from_text(text: str) -> str:
    """Remove year information from text (for role_text column)."""
    out = re.sub(r",?\s*\d{4}\s*[-–]\s*\d{4}", "", text)
    out = re.sub(r",\s*\b(?:1[89]\d{2}|20[0-2]\d)\b\s*$", "", out)
    out = re.sub(r",\s*$", "", out).strip()
    return re.sub(r"\s{2,}", " ", out).strip()


# ============================================================
# ── DEGREE FIELD FIXES ───────────────────────────────────────
# ============================================================

# Fix 15: business → political_sci when political context is unambiguous
_POLSCI_STRONG_RE = re.compile(
    r"\b(political\s+science|school\s+of\s+political|ciencias\s+politicas|"
    r"political\s+and\s+social\s+sciences?|social\s+and\s+political\s+sciences?|"
    r"public\s+admin\w*\s+and\s+political|political\s+\w+\s+and\s+public\s+admin|"
    r"governance|public\s+policy|international\s+relations|diplomacy)\b",
    re.I,
)

# Fix 16: other → architecture for urbanism
_URBANISM_RE = re.compile(r"\b(urbanism|urban\s+plan(?:ning)?|urban\s+design)\b", re.I)

def _fix_degree_field(field, text: str):
    if pd.isna(field) or not isinstance(text, str):
        return field
    if field == "business" and _POLSCI_STRONG_RE.search(text):
        return "political_sci"
    if field == "other" and _URBANISM_RE.search(text):
        return "architecture"
    return field


# ============================================================
# ── FOREIGN DEGREE FIXES ─────────────────────────────────────
# ============================================================

# Fix 17: Detect missed foreign degrees (expanded university list)
_EXTENDED_FOREIGN_RE = re.compile(
    r"\b("
    # UK
    r"University\s+of\s+(?:London|Essex|Edinburgh|Glasgow|Birmingham|Manchester|Leeds)"
    r"|London\s+School\s+of\s+Economics|LSE\b|King.s\s+College\s+London"
    r"|Imperial\s+College\s+London"
    # France
    r"|University\s+of\s+(?:Paris|Toulouse|Bordeaux|Lyon|Strasbourg|Montpellier)"
    r"|Sciences\s+Po|Ecole\s+Nationale\s+d.Administration|ENA\b"
    r"|Ecole\s+Pratique\s+des\s+Hautes\s+Etudes|IEDES\b"
    # Germany
    r"|Alexander\s+Humboldt\s+University|Humboldt\s+University,\s*Berlin"
    r"|University\s+of\s+(?:Turingia|Frankfurt|Hamburg|Cologne|Heidelberg|Munich)"
    r"|Free\s+University\s+of\s+(?:Berlin|Cataluna)"
    r"|Max\s+Planck\s+Institute"
    # Spain
    r"|University\s+of\s+(?:Salamanca|Navarra|Oviedo|Granada|Deusto|Valladolid)"
    r"|Complutense\s+University|Autonomous\s+University\s+of\s+Madrid"
    r"|Ortega\s+y\s+Gasset\s+University"
    # Italy
    r"|Gregorian\s+Pontifical\s+University|Salesian\s+Pontifical\s+University"
    r"|University\s+of\s+(?:Rome|Bologna|Naples|Florence)"
    # Belgium / Switzerland / Netherlands / Austria
    r"|University\s+of\s+(?:Geneva|Brussels|Ghent|Louvain|Vienna|Zurich)"
    # US (additions beyond existing list)
    r"|University\s+of\s+(?:Ohio|Florida|Wisconsin|Minnesota|Arizona|Virginia|"
    r"Indiana|Southern\s+California|North\s+Carolina|Denver|Utah|Kansas)"
    r"|Woodrow\s+Wilson\s+School|Kennedy\s+School\s+of\s+Government"
    r"|LBJ\s+School|Mason\s+Program|Brookings\s+Institution"
    r"|Central\s+School\s+of\s+Planning\s+and\s+Statistics"
    # Latin America (non-Mexican)
    r"|University\s+of\s+(?:Buenos\s+Aires|Chile|Cuyo|Rosario|Colombia|Havana)"
    r"|Central\s+American\s+University|Latin\s+American\s+Military\s+University"
    r"|Canal\s+Zone"
    r")\b",
    re.I,
)

# Known Mexican institutions — presence means NOT a foreign degree
_MEXICAN_UNIV_RE = re.compile(
    r"\b(UNAM|IPN\b|ITAM\b|ITESM\b|CIDE\b|IPADE\b|Colegio\s+de\s+Mexico"
    r"|National\s+Polytechnic|National\s+School|Free\s+Law\s+School"
    r"|Heroic\s+Military\s+College|Higher\s+War\s+College|Military\s+Medical\s+School"
    r"|University\s+of\s+Guadalajara|University\s+of\s+Michoacan"
    r"|University\s+of\s+Veracruz|University\s+of\s+Yucatan"
    r"|University\s+of\s+Sinaloa|University\s+of\s+Sonora|University\s+of\s+Colima"
    r"|University\s+of\s+Nuevo\s+Leon|University\s+of\s+Durango"
    r"|University\s+of\s+Guanajuato|University\s+of\s+San\s+Luis\s+Potosi"
    r"|University\s+of\s+Puebla|University\s+of\s+Oaxaca|University\s+of\s+Guerrero"
    r"|University\s+of\s+Hidalgo|University\s+of\s+Zacatecas|University\s+of\s+Nayarit"
    r"|University\s+of\s+Aguascalientes|University\s+of\s+Queretaro"
    r"|University\s+of\s+Baja\s+California|University\s+of\s+the\s+Valley\s+of\s+Mexico"
    r"|University\s+of\s+Coahuila|University\s+of\s+Tamaulipas|University\s+of\s+Tabasco"
    r"|Autonomous\s+University|Autonomous\s+Metropolitan|Benito\s+Juarez\s+University"
    r"|Juarez\s+University|Juarez\s+Institute|Pan\s+American\s+University"
    r"|La\s+Salle\s+University|Anahuac\s+University|Intercontinental\s+University"
    r"|Popular\s+Autonomous\s+University|Colegio\s+de\s+San\s+Nicolas"
    r"|Technological\s+Institute|Applied\s+Military\s+School|Naval\s+College"
    r"|Center\s+for\s+Higher\s+Naval|National\s+Defense\s+College)\b",
    re.I,
)

def _fix_foreign_degree(foreign_degree, text: str, org: str):
    """Extend foreign_degree detection with a broader university list."""
    if foreign_degree is True:
        return True
    combined = " ".join(x for x in [str(text), str(org)] if x and x != "nan")
    if _EXTENDED_FOREIGN_RE.search(combined):
        # Don't override False if a Mexican institution is also clearly present
        # (mixed case — person studied at both; leave the existing value)
        if foreign_degree is False and _MEXICAN_UNIV_RE.search(combined):
            return foreign_degree
        return True
    return foreign_degree


# ============================================================
# ── MAIN PIPELINE ────────────────────────────────────────────
# ============================================================

def _clean_row(row: pd.Series):
    org    = row["organization"] if pd.notna(row["organization"]) else None
    state  = row["state"]        if pd.notna(row["state"])        else None
    raw    = row["role_text_raw"] if pd.notna(row["role_text_raw"]) else ""
    field  = row["degree_field"] if pd.notna(row["degree_field"]) else None
    fgn    = row["foreign_degree"]
    yr_s   = row["year_start"]
    yr_e   = row["year_end"]

    # ── org / state fixes ──────────────────────────────────────────────
    if org is not None:
        org = _fix_ocr(org)
    if org is not None:
        org = _fix_context(org)
    if org is not None:
        org = _fix_trail(org)
    if org is not None:
        org = _fix_nps_hallucination(org, raw)
    if org is not None:
        org = _fix_school_no_trunc(org, raw)
    if org is not None:
        org = _fix_state_as_org(org)
    if org is not None:
        org = _fix_school_prefer_univ(org, raw)
    if org is not None:
        org = _fix_truncated_univ(org, raw)
    if org is not None:
        org = _fix_uam(org, raw)
    if org is not None:
        org = _fix_trail(org)

    org   = _fix_restore_school(org, raw)
    state = _fix_infer_state(state, raw)

    # ── raw text / year fixes ──────────────────────────────────────────
    raw_clean = _clean_raw(raw)
    role_text = _strip_years_from_text(raw_clean) if raw_clean else None

    # Re-extract years only if raw text changed (OCR garbage present)
    if raw_clean != raw:
        new_yr_s, new_yr_e = _reextract_years(raw_clean)
        # Also re-extract when original years look like "1935–2009" book artifact
        if (yr_s == 1935 and yr_e == 2009) or (pd.notna(yr_s) and pd.notna(yr_e) and yr_e < yr_s):
            yr_s, yr_e = new_yr_s, new_yr_e
        elif raw_clean != raw:
            yr_s, yr_e = new_yr_s, new_yr_e
    else:
        # Even if raw text is clean, fix year_end < year_start (inverted)
        # and thesis-title year contamination
        if pd.notna(yr_s) and pd.notna(yr_e) and yr_e < yr_s:
            new_yr_s, new_yr_e = _reextract_years(raw_clean)
            yr_s, yr_e = new_yr_s, new_yr_e
        elif pd.notna(yr_s) and yr_s < 1880:
            # Year is too early — likely captured from a historical reference in text
            new_yr_s, new_yr_e = _reextract_years(raw_clean)
            yr_s, yr_e = new_yr_s, new_yr_e

    # ── degree field / foreign degree fixes ───────────────────────────
    field = _fix_degree_field(field, raw_clean if raw_clean else raw)
    fgn   = _fix_foreign_degree(fgn, raw_clean if raw_clean else raw, str(org) if org else "")

    return org, state, raw_clean, role_text, yr_s, yr_e, field, fgn


def main():
    print("Loading education.csv …")
    edu = pd.read_csv(EDUCATION_CSV)
    print(f"  {len(edu):,} records")

    orig = edu[["organization", "state", "role_text_raw", "role_text",
                "year_start", "year_end", "degree_field", "foreign_degree"]].copy()

    print("Applying fixes …")
    results = edu.apply(_clean_row, axis=1)

    edu["organization"]  = [r[0] for r in results]
    edu["state"]         = [r[1] for r in results]
    edu["role_text_raw"] = [r[2] for r in results]
    edu["role_text"]     = [r[3] for r in results]
    edu["year_start"]    = [r[4] for r in results]
    edu["year_end"]      = [r[5] for r in results]
    edu["degree_field"]  = [r[6] for r in results]
    edu["foreign_degree"]= [r[7] for r in results]
    # work_state = state for education: institution location IS where the person
    # studied or taught. Foreign degrees (foreign_degree=True) have state=NULL
    # since no Mexican state was extracted — work_state stays NULL too.
    edu["work_state"] = edu["state"]

    def _changed(new, old):
        return new.fillna("__NULL__") != old.fillna("__NULL__")

    edu["modified"] = (
        _changed(edu["organization"],   orig["organization"])
        | _changed(edu["state"],        orig["state"])
        | _changed(edu["role_text_raw"],orig["role_text_raw"])
        | _changed(edu["year_start"].astype(str), orig["year_start"].astype(str))
        | _changed(edu["year_end"].astype(str),   orig["year_end"].astype(str))
        | _changed(edu["degree_field"], orig["degree_field"])
        | _changed(edu["foreign_degree"].astype(str), orig["foreign_degree"].astype(str))
    ).astype(int)

    n_mod = edu["modified"].sum()
    print(f"  Modified: {n_mod:,} / {len(edu):,} records ({100*n_mod/len(edu):.1f}%)")

    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    edu.to_csv(EDUCATION_CLEAN_CSV, index=False)
    print(f"\nSaved → {EDUCATION_CLEAN_CSV}")

    # ── Change summary (use sentinel to handle None/NaN consistently) ──
    def _n_changed(col):
        return (edu[col].fillna("__N__").astype(str) !=
                orig[col].fillna("__N__").astype(str)).sum()

    for col in ["organization", "state", "year_start", "year_end",
                "degree_field", "foreign_degree", "role_text_raw"]:
        print(f"  {col:18s}: {_n_changed(col):4d} changes")

    print("\n--- Sample org changes ---")
    mask = (
        edu["organization"].fillna("__N__") != orig["organization"].fillna("__N__")
    ) & ~(edu["organization"].isna() & orig["organization"].isna())
    for i, row in edu[mask].head(15).iterrows():
        print(f"  {orig['organization'][i]!r:45s} → {row['organization']!r}")

    print("\n--- Sample year changes ---")
    mask_y = (
        _changed(edu["year_start"].astype(str), orig["year_start"].astype(str))
        | _changed(edu["year_end"].astype(str),  orig["year_end"].astype(str))
    )
    for i, row in edu[mask_y].head(15).iterrows():
        print(f"  [{orig['year_start'][i]}–{orig['year_end'][i]}] → "
              f"[{row['year_start']}–{row['year_end']}]  |  {row['role_text_raw'][:75]}")

    print("\n--- Sample degree_field changes ---")
    mask_f = _changed(edu["degree_field"], orig["degree_field"])
    for i, row in edu[mask_f].head(15).iterrows():
        print(f"  {orig['degree_field'][i]!r:15s} → {row['degree_field']!r:15s}  |  "
              f"{row['role_text_raw'][:65]}")

    print("\n--- foreign_degree changes ---")
    mask_fg = _changed(edu["foreign_degree"].astype(str), orig["foreign_degree"].astype(str))
    for i, row in edu[mask_fg].head(15).iterrows():
        print(f"  {str(orig['foreign_degree'][i]):6s} → {str(row['foreign_degree']):6s}  |  "
              f"{row['role_text_raw'][:70]}")


if __name__ == "__main__":
    main()
