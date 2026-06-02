"""
05c_party_positions_clean.py

Post-processing fixes for party_positions.csv (output of 05_party_positions.py).
Reads  data/party_positions.csv
Writes data/clean_positions/party_positions.csv  (+  `modified` column = 1 if changed).

Fixes applied:
  ── text / years ────────────────────────────────────────────────────────────
  1.  Remove OCR book-title fragments from role_text_raw
      ("s, 1935–2009", "NNN mexican political biographie", "Iberomp", "sity of")
  2.  Re-extract year_start / year_end from cleaned raw text
      (removes 1935–2009 artifact years caused by the OCR fragments)
  3.  Clean OCR garbage from organization names

  ── party_rank ──────────────────────────────────────────────────────────────
  4.  Add new rank "candidate": records with record_type="candidate" and
      party_rank="other" → "candidate"  (386 records)
  5.  Fix "national adviser" → "adviser_member": the original regex was anchored
      at start-of-string (^), so "national adviser to PAN" was never caught
      (187 records)
  6.  State-level party director/head → "state_president": conservative pattern
      matching only "director of [party]" or "[party] director" at start of text
      (subset of 145 records)
  7.  Campaign coordinator → "campaign_leader": "coordinator/director of campaign"
      (3 records)

  ── party / party_level ─────────────────────────────────────────────────────
  8.  Recognize minor party acronyms not in original _PARTY_PATTERNS:
      PMS, PRT, PCD, PPM, PAS, PP  (fills null party column)
  9.  City in text → party_level="local": if text mentions a specific
      municipality (from CITY_TO_STATE in config.py), override "state"→"local"
 10.  Null party_level → infer from context:
      - "Chamber of Deputies" / "Senate" / national keywords → "national"
      - City name in text → "local"
      - State name in text → "state"
      - Fallback → "national" (party committee/delegation roles)

Note on "candidate" rank: if party_positions_wide.csv is regenerated from this
clean file, add "candidate": 15 to _RANK_ORDER in 05_party_positions.py so that
_best_rank() handles it correctly.
"""

import re
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

CODE_DIR = Path(__file__).resolve().parents[2]
if str(CODE_DIR) not in sys.path:
    sys.path.append(str(CODE_DIR))

from config import DATA_DIR

PARTY_POSITIONS_CSV       = DATA_DIR / "party_positions.csv"
CLEAN_DIR                 = DATA_DIR / "clean_positions"
PARTY_POSITIONS_CLEAN_CSV = CLEAN_DIR / "party_positions.csv"


# ---------------------------------------------------------------------------
# Fix 1: Remove OCR book-title fragments from role_text_raw
# ---------------------------------------------------------------------------

_OCR_RAW_RE = re.compile(
    r"\bs,\s*1935[–\-]2009\b"                      # "s, 1935–2009" (book subtitle)
    r"|\bBiograph\w*,?\s*1935[–\-]2009\b"           # "Biographies, 1935–2009"
    r"|\d{2,}\s+mexican\s+political\s+biograph\w*"  # "144 mexican political biographie"
    r"|\bIberomp\b"                                 # truncated "Ibero-American"
    r"|\bsity\s+of\b",                             # page-break cut of "University of"
    re.I,
)

def _clean_raw(text: str) -> str:
    cleaned = _OCR_RAW_RE.sub(" ", text)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


# ---------------------------------------------------------------------------
# Fix 2: Re-extract year_start / year_end from cleaned raw text
# ---------------------------------------------------------------------------

_YEAR_RANGE_RE  = re.compile(r"(\d{4})\s*[-–]\s*(\d{4})")
_SINGLE_YEAR_RE = re.compile(r"\b(1[89]\d{2}|20[0-2]\d)\b")


def _reextract_years(text: str):
    m = _YEAR_RANGE_RE.search(text)
    if m:
        return int(m.group(1)), int(m.group(2))
    singles = _SINGLE_YEAR_RE.findall(text)
    if singles:
        yr = int(singles[-1])
        return yr, yr
    return None, None

def _strip_years_from_text(text: str) -> str:
    out = re.sub(r",?\s*\d{4}\s*[-–]\s*\d{4}", "", text)
    out = re.sub(r",\s*\b(?:1[89]\d{2}|20[0-2]\d)\b\s*$", "", out)
    out = re.sub(r",\s*$", "", out).strip()
    return re.sub(r"\s{2,}", " ", out).strip()


# ---------------------------------------------------------------------------
# Fix 3: Clean OCR garbage from organization column
# ---------------------------------------------------------------------------

_OCR_ORG_RE = re.compile(
    r"\d{2,}\s+mexican\s+political\s+biograph\w*\s*", re.I,
)

def _clean_org(org) -> Optional[str]:
    if not isinstance(org, str):
        return org
    cleaned = _OCR_ORG_RE.sub("", org)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip().rstrip(".,; ")
    return cleaned if len(cleaned) >= 2 else None


# ---------------------------------------------------------------------------
# Fix 4: Add "candidate" rank for record_type="candidate" with party_rank="other"
# ---------------------------------------------------------------------------

def _fix_candidate_rank(rank: str, record_type: str) -> str:
    if rank == "other" and record_type == "candidate":
        return "candidate"
    return rank


# ---------------------------------------------------------------------------
# Fix 5: "national adviser / technical adviser" → "adviser_member"
# The original regex used ^ (start-of-string), missing "national adviser to PAN".
# ---------------------------------------------------------------------------

_ADVISER_RE = re.compile(r"\b(?:national\s+|technical\s+|general\s+)?(?:adviser|advisor)\b", re.I)

def _fix_adviser_rank(rank: str, text: str) -> str:
    if rank == "other" and _ADVISER_RE.search(text):
        return "adviser_member"
    return rank


# ---------------------------------------------------------------------------
# Fix 6: State-level party director/head → "state_president"
# Conservative: only matches "director of [party]" or "[party] director"
# at the start of the text, to avoid section directors (women's action, etc.)
# ---------------------------------------------------------------------------

_PARTY_NAMES = r"(?:PRI|PAN|PRD|PPS|PNR|PRM|PSUM|PST|PDM|PARM|PMT|PCM|PVEM|PT)"

# "director of PRI, [state]" or "[party] director, [location]" — both require comma
# immediately after the party/director keyword to exclude section directors.
_STATE_DIR_RE = re.compile(
    r"^director\s+of\s+(?:the\s+)?" + _PARTY_NAMES + r"(?=\s*,)"
    r"|^" + _PARTY_NAMES + r"\s+director\s*,",
    re.I,
)

def _fix_state_dir_rank(rank: str, text: str, level: str) -> str:
    if rank == "other" and level == "state" and _STATE_DIR_RE.search(text.strip()):
        return "state_president"
    return rank


# ---------------------------------------------------------------------------
# Fix 7: Campaign coordinator / organizer → "campaign_leader"
# ---------------------------------------------------------------------------

_CAMP_COORD_RE = re.compile(
    r"^(?:coordinator|organizer|director)\b.{0,80}\bcampaigns?\b", re.I
)

def _fix_camp_coord_rank(rank: str, text: str) -> str:
    if rank == "other" and _CAMP_COORD_RE.search(text):
        return "campaign_leader"
    return rank


# ---------------------------------------------------------------------------
# Fix 8: party_level="state" with null state → set to None
# (kept as fix 8, city/level fixes below are 9-10)
# Bug in 05_party_positions.py: float(NaN) is truthy in Python, so
# `if state and state not in ("Federal District",)` incorrectly returned
# "state" for records where state was NaN.
# ---------------------------------------------------------------------------

def _fix_party_level(level: str, state) -> Optional[str]:
    if level == "state" and pd.isna(state):
        return None
    return level


# ---------------------------------------------------------------------------
# Fix 9: Recognize minor party acronyms missing from original _PARTY_PATTERNS
# ---------------------------------------------------------------------------

# Maps acronym → canonical name stored in `party` column
_MINOR_PARTIES = {
    "PMS":  "PMS",   # Partido Mexicano Socialista (PRD precursor 1987–1989)
    "PRT":  "PRT",   # Partido Revolucionario de los Trabajadores (Trotskyist)
    "PCD":  "PCD",   # Partido Centro Democrático (Camacho Solís, 1999–2003)
    "PPM":  "PPM",   # Partido Popular Mexicano
    "PAS":  "PAS",   # Partido Alianza Social
}
# PP (Partido Popular) handled separately — acronym too short/ambiguous alone
_PP_RE = re.compile(r"\bParty\b.*\bPP\b|\bPP\b.*\bParty\b|candidate\s+of\s+PP\b"
                    r"|member\s+of\s+PP\b|founding\s+member.*\bPP\b", re.I)
_MINOR_PARTY_RE = re.compile(
    r"\b(" + "|".join(_MINOR_PARTIES.keys()) + r")\b", re.I
)

def _fix_minor_party(party, org: str, text: str):
    if pd.notna(party):
        return party
    for source in (org, text):
        if not isinstance(source, str):
            continue
        m = _MINOR_PARTY_RE.search(source)
        if m:
            return _MINOR_PARTIES[m.group(1).upper()]
    if isinstance(text, str) and _PP_RE.search(text):
        return "PP"
    return party


# ---------------------------------------------------------------------------
# Fix 9b: City in text → party_level="local"
# Uses CITY_TO_STATE from config.py (cities that are clearly municipalities,
# not state names). State-named cities (Puebla, Oaxaca) are excluded to avoid
# false positives.
# ---------------------------------------------------------------------------

from config import CITY_TO_STATE

# Only non-capital municipalities — state capitals excluded to avoid false positives.
# "president of PRI, Durango" = state-level (Durango is also the state capital).
# "president of PRI, Iguala" = local (Iguala is clearly a municipality).
# Excluded: state capitals AND cities that share names with states, politicians,
# or other ambiguous terms (e.g. "veracruz"=city+state, "leon" in "Nuevo Leon",
# "lazaro cardenas"=president+city, "obregon"=general+city).
_EXCLUDED_LOWER = {
    # State capitals
    "aguascalientes", "mexicali", "la paz", "campeche", "tuxtla gutierrez",
    "chihuahua", "saltillo", "colima", "toluca", "morelia", "cuernavaca",
    "tepic", "monterrey", "oaxaca", "puebla", "queretaro", "chetumal",
    "san luis potosi", "culiacan", "hermosillo", "villahermosa",
    "ciudad victoria", "tlaxcala", "jalapa", "xalapa", "merida",
    "zacatecas", "durango", "guadalajara", "chilpancingo",
    # Ambiguous: both city and state, or politician name
    "veracruz", "leon", "lazaro cardenas", "obregon",
}

# Safe non-capital municipalities from CITY_TO_STATE (no state/capital ambiguity)
_CITY_NAMES_LOCAL = sorted(
    [city for city in CITY_TO_STATE
     if city.lower() not in _EXCLUDED_LOWER],
    key=len, reverse=True,
)

# Additional non-capital municipalities unambiguously distinct from state names
_EXTRA_CITIES_LOCAL = [
    "iguala", "acapulco",
    "ciudad juarez", "parral", "delicias",
    "torreon", "monclova", "piedras negras",
    "tampico", "nuevo laredo", "matamoros", "reynosa",
    "mazatlan", "los mochis", "guasave",
    "irapuato", "celaya", "salamanca", "silao",
    "uruapan", "zamora",
    "valladolid", "progreso",
    "comalcalco",
    "san cristobal de las casas", "tapachula", "comitan",
    "cancun", "playa del carmen",
    "manzanillo",
    "apizaco", "huamantla",
    "tulancingo",
    "san juan del rio",
    "fresnillo",
    "gomez palacio", "lerdo",
    "jochitlan", "metepec",
    "juchitan", "tuxtepec",
    "coatzacoalcos", "poza rica", "tuxpan",
]

_ALL_CITIES = sorted(
    set(_CITY_NAMES_LOCAL + _EXTRA_CITIES_LOCAL),
    key=len, reverse=True,
)
_CITY_LOCAL_RE = re.compile(
    r"\b(" + "|".join(re.escape(c) for c in _ALL_CITIES) + r")\b", re.I
)

def _fix_city_to_local(level: Optional[str], text: str) -> Optional[str]:
    if level != "state":
        return level
    if _CITY_LOCAL_RE.search(text):
        return "local"
    return level


# ---------------------------------------------------------------------------
# Fix 10: Null party_level → infer from context
# ---------------------------------------------------------------------------

_NATIONAL_BODY_RE = re.compile(
    r"\b(Chamber\s+of\s+Deputies|Senate|Congress|federal\s+legislature|"
    r"CEN\b|IEPES\b|national\s+committee|central\s+committee|"
    r"national\s+council|national\s+assembly|national\s+convention|"
    r"national\s+PRI|national\s+PAN|national\s+PRD|plurinominal)\b",
    re.I,
)

_STATE_LEVEL_RANKS = {"state_president", "state_secretary", "state_secretary_general"}

def _fix_null_level(level: Optional[str], text: str, state, rank: str) -> Optional[str]:
    if pd.notna(level):
        return level
    # Rank explicitly indicates state level — trust it even without a state name.
    # 217 records have state_president/state_secretary rank but no state in text.
    if rank in _STATE_LEVEL_RANKS:
        return "state"
    if not isinstance(text, str):
        return None
    # Explicit national body keywords → national
    if _NATIONAL_BODY_RE.search(text):
        return "national"
    # Unambiguous municipality → local
    if _CITY_LOCAL_RE.search(text):
        return "local"
    # State column populated → state
    if pd.notna(state):
        return "state"
    # No geographic context: leave NULL rather than guessing.
    # "national" as fallback inflates national connections in network analysis
    # with records like "Joined PRI, 1975" or "Member of PAN".
    return None


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def _clean_row(row: pd.Series):
    raw        = row["role_text_raw"] if pd.notna(row["role_text_raw"]) else ""
    org        = row["organization"]
    yr_s       = row["year_start"]
    yr_e       = row["year_end"]
    rank       = row["party_rank"]  if pd.notna(row["party_rank"])  else "other"
    rec_type   = row["record_type"] if pd.notna(row["record_type"]) else ""
    level      = row["party_level"] if pd.notna(row["party_level"]) else None
    state      = row["state"]
    party      = row["party"]       if pd.notna(row["party"])       else None

    # Text / year fixes
    raw_clean = _clean_raw(raw)
    role_text = _strip_years_from_text(raw_clean) if raw_clean else None
    if raw_clean != raw:
        yr_s, yr_e = _reextract_years(raw_clean)

    org_clean = _clean_org(org)

    # party_rank fixes (applied in priority order)
    rank = _fix_candidate_rank(rank, rec_type)
    rank = _fix_adviser_rank(rank, raw_clean)
    rank = _fix_state_dir_rank(rank, raw_clean, level or "")
    rank = _fix_camp_coord_rank(rank, raw_clean)

    # party_level: NaN-state bug → null, then city→local, then fill nulls
    level = _fix_party_level(level, state)       # NaN-state bug (fix 8)
    level = _fix_city_to_local(level, raw_clean) # city in text → local (fix 9b)
    level = _fix_null_level(level, raw_clean, state, rank)  # fill remaining nulls (fix 10)

    # Minor party recognition
    party = _fix_minor_party(party, str(org) if pd.notna(org) else "", raw_clean)

    return raw_clean, role_text, yr_s, yr_e, org_clean, rank, level, party


def main():
    print("Loading party_positions.csv …")
    pp = pd.read_csv(PARTY_POSITIONS_CSV)
    print(f"  {len(pp):,} records")

    orig_raw   = pp["role_text_raw"].copy()
    orig_org   = pp["organization"].copy()
    orig_ys    = pp["year_start"].copy()
    orig_ye    = pp["year_end"].copy()
    orig_rank  = pp["party_rank"].copy()
    orig_level = pp["party_level"].copy()
    orig_party = pp["party"].copy()

    print("Applying fixes …")
    results = pp.apply(_clean_row, axis=1)

    pp["role_text_raw"] = [r[0] for r in results]
    pp["role_text"]     = [r[1] for r in results]
    pp["year_start"]    = [r[2] for r in results]
    pp["year_end"]      = [r[3] for r in results]
    pp["organization"]  = [r[4] for r in results]
    pp["party_rank"]    = [r[5] for r in results]
    pp["party_level"]   = [r[6] for r in results]
    pp["party"]         = [r[7] for r in results]

    def _n_chg(new, old):
        return (new.fillna("__N__").astype(str) != old.fillna("__N__").astype(str)).sum()

    pp["modified"] = (
        (pp["role_text_raw"].fillna("__N__") != orig_raw.fillna("__N__"))
        | (pp["organization"].fillna("__N__").astype(str) != orig_org.fillna("__N__").astype(str))
        | (pp["year_start"].fillna(-1)  != orig_ys.fillna(-1))
        | (pp["year_end"].fillna(-1)    != orig_ye.fillna(-1))
        | (pp["party_rank"].fillna("__N__")  != orig_rank.fillna("__N__"))
        | (pp["party_level"].fillna("__N__") != orig_level.fillna("__N__"))
        | (pp["party"].fillna("__N__")       != orig_party.fillna("__N__"))
    ).astype(int)

    n_mod = pp["modified"].sum()
    print(f"  Modified: {n_mod:,} / {len(pp):,} records ({100*n_mod/len(pp):.1f}%)")

    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    pp.to_csv(PARTY_POSITIONS_CLEAN_CSV, index=False)
    print(f"\nSaved → {PARTY_POSITIONS_CLEAN_CSV}")

    print(f"\n  role_text_raw : {_n_chg(pp['role_text_raw'], orig_raw):4d} changes")
    print(f"  organization  : {_n_chg(pp['organization'],  orig_org):4d} changes")
    print(f"  year_start    : {_n_chg(pp['year_start'],    orig_ys):4d} changes")
    print(f"  year_end      : {_n_chg(pp['year_end'],      orig_ye):4d} changes")
    print(f"  party_rank    : {_n_chg(pp['party_rank'],    orig_rank):4d} changes")
    print(f"  party_level   : {_n_chg(pp['party_level'],   orig_level):4d} changes")
    print(f"  party         : {_n_chg(pp['party'],         orig_party):4d} changes")

    # party_rank change breakdown
    rank_chg = pp[pp["party_rank"].fillna("__N__") != orig_rank.fillna("__N__")].copy()
    rank_chg["orig_rank"] = orig_rank[rank_chg.index]
    print(f"\nparty_rank change breakdown:")
    print(rank_chg.groupby(["orig_rank","party_rank"]).size().to_string())

    # party_level change breakdown
    lev_chg = pp[pp["party_level"].fillna("__N__") != orig_level.fillna("__N__")].copy()
    lev_chg["orig_level"] = orig_level[lev_chg.index]
    print(f"\nparty_level change breakdown:")
    print(lev_chg.groupby(["orig_level","party_level"], dropna=False).size().to_string())

    # Sample rank changes
    print("\n--- Sample party_rank changes ---")
    for new_rank in ["candidate", "adviser_member", "state_president", "campaign_leader"]:
        subset = rank_chg[rank_chg["party_rank"] == new_rank].head(4)
        if not subset.empty:
            print(f"\n  → {new_rank} ({len(rank_chg[rank_chg['party_rank']==new_rank])} total):")
            for _, row in subset.iterrows():
                print(f"    {row['role_text_raw'][:80]}")

    # party_level: show local changes and null→assigned breakdown
    lev_chg2 = pp[pp["party_level"].fillna("__N__") != orig_level.fillna("__N__")].copy()
    lev_chg2["orig"] = orig_level[lev_chg2.index]
    print(f"\n--- party_level change breakdown ---")
    print(lev_chg2.groupby(["orig","party_level"], dropna=False).size().to_string())

    local_chg = lev_chg2[lev_chg2["party_level"] == "local"]
    if not local_chg.empty:
        print(f"\n  state→local sample (city detected):")
        for _, row in local_chg.head(8).iterrows():
            print(f"    [{row['orig']}→local]  {row['role_text_raw'][:75]}")

    # party: minor party fills
    party_chg = pp[pp["party"].fillna("__N__") != orig_party.fillna("__N__")]
    if not party_chg.empty:
        print(f"\n--- party fills (minor parties) ---")
        print(party_chg[["role_text_raw","party"]].head(20).to_string())


if __name__ == "__main__":
    main()
