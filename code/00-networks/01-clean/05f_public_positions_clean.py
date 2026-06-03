"""
05f_public_positions_clean.py

Post-processing fixes for public_positions.csv (output of 05_public_positions.py).
Reads  data/public_positions.csv
Writes data/clean_positions/public_positions.csv  (+  `modified` column = 1 if changed).

Fixes applied:
  1.  Remove OCR book-title fragments from role_text_raw
  2.  Fix year anomalies:
        a. year_end < year_start → swap (e.g. "1924–1916")
        b. OCR misread "2012" as "1912": when year_start ≥ 2000 and year_end < 1950
           → year_end += 100  (applies to plurinominal deputies/senators 2009–2012)
  3.  Fix double-space in position_title ("Federal  Deputy" → "Federal Deputy")
  4.  Fill null position_title for plurinominal deputies, senators, and similar
      records where a prefix word prevented regex matching:
        "plurinominal federal deputy" → "Federal Deputy"
        "plurinominal senator"        → "Senator"
        "Federal party deputy"        → "Federal Deputy"
        "deputy to Constitutional Convention" → "Deputy"
  5.  Extract municipality as organization for local positions with null org:
        "mayor, Hidalgo del Parral, Chihuahua, 1952" → org = "Hidalgo del Parral"
        "Member, City Council of Aguascalientes, 1954" → org = "Aguascalientes"
  6.  Infer null state from extracted municipality (via CITY_TO_STATE in config)
  7.  Add work_state column — physical work location, distinct from electoral
      constituency stored in state:
        Federal Deputy / Senator → work_state = "Federal District"
          (they represent a state but sit in the Chamber/Senate in Mexico City)
        Governor / Mayor / Local Deputy / Alternate Mayor → work_state = state
          (they worked physically in their constituency)
        All other federal-chamber positions (Member, President, Representative,
          Secretary, Delegate, Vice President, Coordinator) → "Federal District"
"""

import re
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

CODE_DIR = Path(__file__).resolve().parents[2]
if str(CODE_DIR) not in sys.path:
    sys.path.append(str(CODE_DIR))

from config import DATA_DIR, MEXICAN_STATES, CITY_TO_STATE, CITY_TO_STATE_NORM, strip_accents

PUBLIC_POSITIONS_CSV       = DATA_DIR / "public_positions.csv"
CLEAN_DIR                  = DATA_DIR / "clean_positions"
PUBLIC_POSITIONS_CLEAN_CSV = CLEAN_DIR / "public_positions.csv"


# ---------------------------------------------------------------------------
# Fix 1: Remove OCR book-title fragments from role_text_raw
# ---------------------------------------------------------------------------

_OCR_RAW_RE = re.compile(
    r"\bs,\s*1935[–\-]2009\b"
    r"|\bBiograph\w*,?\s*1935[–\-]2009\b"
    r"|\d{2,}\s+mexican\s+political\s+biograph\w*"
    r"|\bsity\s+of\b",
    re.I,
)

def _clean_raw(text: str) -> str:
    cleaned = _OCR_RAW_RE.sub(" ", text)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


# ---------------------------------------------------------------------------
# Fix 2: Year anomalies
# ---------------------------------------------------------------------------

_YEAR_RANGE_RE  = re.compile(r"(\d{4})\s*[-–]\s*(\d{4})")
_SINGLE_YEAR_RE = re.compile(r"\b(1[89]\d{2}|20[0-2]\d)\b")


def _fix_years(yr_s, yr_e, raw_clean: str):
    """Fix inverted and OCR-misread years."""
    # Re-extract if raw changed (OCR fix)
    if not isinstance(raw_clean, str):
        return yr_s, yr_e

    # Case: year_start >= 2000 and year_end < 1950 → OCR read "2012" as "1912"
    if pd.notna(yr_s) and pd.notna(yr_e):
        if yr_s >= 2000 and yr_e < 1950:
            yr_e = yr_e + 100   # 1912 → 2012
            return yr_s, yr_e
        # Case: simple inversion (e.g. "1924–1916")
        if yr_e < yr_s:
            yr_s, yr_e = yr_e, yr_s
            return yr_s, yr_e

    return yr_s, yr_e


def _reextract_years(text: str):
    m = _YEAR_RANGE_RE.search(text)
    if m:
        return int(m.group(1)), int(m.group(2))
    singles = _SINGLE_YEAR_RE.findall(text)
    if singles:
        yr = int(singles[-1])
        return yr, yr
    return None, None

def _strip_years(text: str) -> str:
    out = re.sub(r"[,\s]*\d{4}[\s\-–\d]*$", "", text)
    return re.sub(r"[,\s]+$", "", out).strip()


# ---------------------------------------------------------------------------
# Fix 3: Double-space in position_title
# ---------------------------------------------------------------------------

def _fix_double_space_title(title) -> Optional[str]:
    if not isinstance(title, str):
        return title
    return re.sub(r"\s{2,}", " ", title).strip()


# ---------------------------------------------------------------------------
# Fix 4: Fill null position_title for plurinominal and prefix variants
# ---------------------------------------------------------------------------

_TITLE_PATTERNS = [
    # Order matters: most specific first
    (re.compile(r"\b(?:plurinominal|alternate|party|constitutional|independent)\s+(?:federal\s+)?senator\b", re.I), "Senator"),
    (re.compile(r"\b(?:plurinominal|alternate|party|constitutional|independent|federal)\s+(?:federal\s+)?deputy\b", re.I), "Federal Deputy"),
    (re.compile(r"\bdeputy\s+to\s+(?:the\s+)?constitutional\s+convention\b", re.I), "Deputy"),
    (re.compile(r"\bdeputy,?\s+constitutional\s+convention\b", re.I), "Deputy"),
    (re.compile(r"\bconstitutional\s+deputy\b", re.I), "Deputy"),
    (re.compile(r"\bfederal\s+party\s+deputy\b", re.I), "Federal Deputy"),
    (re.compile(r"\balternate\s+(?:federal\s+)?deputy\b", re.I), "Federal Deputy"),
    (re.compile(r"\balternate\s+(?:local\s+)?deputy\b", re.I), "Local Deputy"),
    (re.compile(r"\blocal\s+deputy\s+to\s+(?:state\s+legislature|the\s+legislature)\b", re.I), "Local Deputy"),
    (re.compile(r"\bdeputy\s+to\s+(?:state\s+legislature|state\s+congress)\b", re.I), "Local Deputy"),
    (re.compile(r"\brepresentative\s+to\s+(?:the\s+)?assembly\b|\brepresentative\s+to\s+(?:the\s+)?federal\s+district\s+assembly\b", re.I), "Representative"),
    (re.compile(r"\bgovernor[\s-]elect\b", re.I), "Governor"),
    (re.compile(r"\bsubstitute\s+governor\b|\bprovisional\s+governor\b|\bacting\s+governor\b|\binterim\s+governor\b", re.I), "Governor"),
    (re.compile(r"\balternate\s+mayor\b|\bvice\s+mayor\b", re.I), "Alternate Mayor"),
    (re.compile(r"\balternate\s+senator\b", re.I), "Senator"),
    (re.compile(r"\bplurino\w*\s+local\s+deputy\b|\bplurino\w*\s+(?:state\s+)?deputy\b", re.I), "Local Deputy"),
]


def _fix_null_title(title, raw: str) -> Optional[str]:
    if pd.notna(title):
        return title
    if not isinstance(raw, str):
        return title
    for pat, label in _TITLE_PATTERNS:
        if pat.search(raw):
            return label
    return title


# ---------------------------------------------------------------------------
# Fix 5: Extract municipality as organization for local positions
# ---------------------------------------------------------------------------

_LOCAL_POSITION_RE = re.compile(
    r"\b(mayor|alternate\s+mayor|vice\s+mayor|municipal\s+president|"
    r"city\s+council|municipal\s+council|municipal\s+treasurer|"
    r"municipal\s+secretary|syndic|regidor|ayuntamiento)\b",
    re.I,
)

_STATE_NAMES_NORM = sorted(
    {strip_accents(v.lower()) for _, (variants,_,_) in MEXICAN_STATES.items() for v in variants}
    | {"federal district", "mexico city"},
    key=len, reverse=True,
)
_STATE_PAT = re.compile(
    r",?\s*(?:state\s+of\s+)?(" + "|".join(re.escape(s) for s in _STATE_NAMES_NORM) + r")\s*(?:,|\s*\d{4}|\s*$)",
    re.I,
)
# "City Council of X" or "City Council, X" patterns
_CITY_COUNCIL_PAT = re.compile(
    r"\bcity\s+council\s+(?:of\s+)?(.+?)(?:\s*,|\s*\d{4}|\s*$)",
    re.I,
)


def _extract_municipality(raw: str, position_title) -> Optional[str]:
    """Extract city/municipality name from local position text."""
    if not isinstance(raw, str):
        return None
    if not _LOCAL_POSITION_RE.search(raw):
        return None

    # Special case: "City Council of X" or "City Council, X"
    m_cc = _CITY_COUNCIL_PAT.search(raw)
    if m_cc:
        candidate = _strip_years(m_cc.group(1).strip().rstrip(" ,"))
        candidate_norm = strip_accents(candidate.lower())
        # Strip trailing state name from candidate
        m_st = _STATE_PAT.search(", " + candidate_norm)
        if m_st:
            candidate = candidate[:m_st.start()].strip().rstrip(" ,")
        if candidate and 2 <= len(candidate) <= 60:
            return candidate

    # General case: remove position title → strip year → strip state → remainder is city
    text = raw.strip()
    pt = str(position_title).strip() if pd.notna(position_title) else ""
    if pt and text.lower().startswith(pt.lower()):
        text = text[len(pt):].lstrip(" ,")
    else:
        # Try to remove known position words from start
        text = _LOCAL_POSITION_RE.sub("", text, count=1).lstrip(" ,")

    text = _strip_years(text).rstrip(" ,")

    # Strip trailing state name
    text_norm = strip_accents(text.lower())
    m = _STATE_PAT.search(text_norm)
    if m:
        text = text[:m.start()].strip().rstrip(" ,")

    text = text.strip().rstrip(" ,")

    # Validate: reasonable length, not a committee/council/convention name
    if not text or len(text) > 60 or len(text) < 2:
        return None
    if re.search(r"\bcommittee\b|\bconvention\b|\bcouncil\b|\bcommission\b", text, re.I):
        return None
    return text


# ---------------------------------------------------------------------------
# Fix 6: Infer null state from municipality (via CITY_TO_STATE)
# ---------------------------------------------------------------------------

def _infer_state_from_municipality(state, municipality: Optional[str]) -> Optional[str]:
    if pd.notna(state) or not municipality:
        return state
    mun_norm = strip_accents(municipality.lower())
    return CITY_TO_STATE_NORM.get(mun_norm, state)


# ---------------------------------------------------------------------------
# Fix 7: Add work_state — physical work location vs. electoral constituency
# ---------------------------------------------------------------------------

# Positions that are physically in the federal legislature (Mexico City)
_FEDERAL_CHAMBER_TITLES = {
    "Federal Deputy", "Senator", "Representative", "Vice President",
    "Member", "President", "Secretary", "Delegate", "Coordinator",
    "Head", "Oficial Mayor", "Director",
}
# Positions where work location = constituency state
_LOCAL_STATE_TITLES = {
    "Governor", "Mayor", "Local Deputy", "Alternate Mayor",
}


def _work_state(position_title, state) -> Optional[str]:
    """
    Physical work location. For senators and federal deputies the state column
    holds their electoral constituency (e.g. 'Morelos'), but they worked in
    the Chamber of Deputies / Senate in the Federal District.
    """
    title = str(position_title).strip() if pd.notna(position_title) else ""
    if title in _LOCAL_STATE_TITLES:
        return state if pd.notna(state) else None
    if title in _FEDERAL_CHAMBER_TITLES or not title:
        return "Federal District"
    return state if pd.notna(state) else None


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def _clean_row(row: pd.Series):
    raw    = row["role_text_raw"] if pd.notna(row["role_text_raw"]) else ""
    org    = row["organization"]
    state  = row["state"]
    yr_s   = row["year_start"]
    yr_e   = row["year_end"]
    title  = row["position_title"]

    # Fix 1: OCR
    raw_clean = _clean_raw(raw)
    role_text = re.sub(r"[,\s]+$", "", _strip_years(raw_clean)).strip() if raw_clean else None

    # Re-extract years when raw text changed
    if raw_clean != raw:
        yr_s, yr_e = _reextract_years(raw_clean)

    # Fix 2: year anomalies (OCR misread + inversions)
    yr_s, yr_e = _fix_years(yr_s, yr_e, raw_clean)

    # Fix 3: double-space in title
    title = _fix_double_space_title(title)

    # Fix 4: null position_title
    title = _fix_null_title(title, raw_clean)

    # Fix 5: extract municipality as org for local positions
    if pd.isna(org):
        org = _extract_municipality(raw_clean, title)

    # Fix 6: infer state from municipality
    state = _infer_state_from_municipality(state, org if pd.isna(row["state"]) else None)

    # Fix 7: work_state (physical location, not electoral constituency)
    wstate = _work_state(title, state)

    return raw_clean, role_text, yr_s, yr_e, title, org, state, wstate


def main():
    print("Loading public_positions.csv …")
    pp = pd.read_csv(PUBLIC_POSITIONS_CSV)
    print(f"  {len(pp):,} records")

    orig_raw   = pp["role_text_raw"].copy()
    orig_org   = pp["organization"].copy()
    orig_state = pp["state"].copy()
    orig_ys    = pp["year_start"].copy()
    orig_ye    = pp["year_end"].copy()
    orig_title = pp["position_title"].copy()

    print("Applying fixes …")
    results = pp.apply(_clean_row, axis=1)

    pp["role_text_raw"]  = [r[0] for r in results]
    pp["role_text"]      = [r[1] for r in results]
    pp["year_start"]     = [r[2] for r in results]
    pp["year_end"]       = [r[3] for r in results]
    pp["position_title"] = [r[4] for r in results]
    pp["organization"]   = [r[5] for r in results]
    pp["state"]          = [r[6] for r in results]
    pp["work_state"]     = [r[7] for r in results]

    def _n_chg(new, old):
        return (new.fillna("__N__").astype(str) != old.fillna("__N__").astype(str)).sum()

    pp["modified"] = (
        (pp["role_text_raw"].fillna("__N__")  != orig_raw.fillna("__N__"))
        | (pp["organization"].fillna("__N__").astype(str) != orig_org.fillna("__N__").astype(str))
        | (pp["state"].fillna("__N__")        != orig_state.fillna("__N__"))
        | (pp["year_start"].fillna(-1)        != orig_ys.fillna(-1))
        | (pp["year_end"].fillna(-1)          != orig_ye.fillna(-1))
        | (pp["position_title"].fillna("__N__") != orig_title.fillna("__N__"))
    ).astype(int)

    n_mod = pp["modified"].sum()
    print(f"  Modified: {n_mod:,} / {len(pp):,} records ({100*n_mod/len(pp):.1f}%)")

    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    pp.to_csv(PUBLIC_POSITIONS_CLEAN_CSV, index=False)
    print(f"\nSaved → {PUBLIC_POSITIONS_CLEAN_CSV}")

    print(f"\n  role_text_raw  : {_n_chg(pp['role_text_raw'],  orig_raw):4d} changes")
    print(f"  position_title : {_n_chg(pp['position_title'], orig_title):4d} changes")
    print(f"  organization   : {_n_chg(pp['organization'],   orig_org):4d} changes")
    print(f"  state          : {_n_chg(pp['state'],          orig_state):4d} changes")
    print(f"  year_start     : {_n_chg(pp['year_start'],     orig_ys):4d} changes")
    print(f"  year_end       : {_n_chg(pp['year_end'],       orig_ye):4d} changes")

    # Sample: position_title fills
    title_filled = pp[
        pp["position_title"].fillna("__N__") != orig_title.fillna("__N__")
    ]
    print(f"\n--- Sample position_title fills ({len(title_filled)} total) ---")
    for _, row in title_filled.head(15).iterrows():
        i = row.name
        print(f"  {orig_title[i]!r:6} → {row['position_title']!r:20}  |  {row['role_text_raw'][:60]}")

    # Sample: org fills (municipalities)
    org_filled = pp[
        pp["organization"].fillna("__N__").astype(str) != orig_org.fillna("__N__").astype(str)
    ]
    print(f"\n--- Sample organization fills ({len(org_filled)} total — municipalities) ---")
    for _, row in org_filled.head(15).iterrows():
        i = row.name
        print(f"  {orig_org[i]!r:6} → {row['organization']!r:25}  |  {row['role_text_raw'][:55]}")

    # Year fixes
    yr_fixed = pp[
        (pp["year_start"].fillna(-1) != orig_ys.fillna(-1)) |
        (pp["year_end"].fillna(-1)   != orig_ye.fillna(-1))
    ]
    if not yr_fixed.empty:
        print(f"\n--- Year fixes ({len(yr_fixed)}) ---")
        for i, row in yr_fixed.iterrows():
            print(f"  [{orig_ys[i]}–{orig_ye[i]}] → [{row['year_start']}–{row['year_end']}]"
                  f"  |  {row['role_text_raw'][:65]}")


if __name__ == "__main__":
    main()
