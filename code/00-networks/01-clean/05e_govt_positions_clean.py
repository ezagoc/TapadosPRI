"""
05e_govt_positions_clean.py

Post-processing fixes for govt_positions.csv (output of 05_govt_positions.py).
Reads  data/govt_positions.csv
Writes data/clean_positions/govt_positions.csv  (+  `modified` column = 1 if changed).

Fixes applied:
  1.  Remove OCR book-title fragments from role_text_raw
      ("s, 1935–2009", "NNN mexican political biographie")
  2.  Re-extract year_start / year_end from cleaned raw text
  3.  Fix inverted years (year_end < year_start)
  4.  Remove OCR garbage from organization column
  5.  Fix role-word-as-org: when org is a function word ("planning", "training",
      "finance", …) the regex in 04 captured the sub-function instead of the
      real institution. Re-extract the org from the text after the role word.
  6.  Fix state-as-org where a real institution appears before the state name:
      "director, National Office of X of the Federal District" → org was set to
      "Federal District"; re-extract "National Office of X of the Federal District"
  7.  Clear GPT-hallucinated org: org_gpt assigned a state name that does not
      appear anywhere in the raw text (2 records: Taxpayer Services / Income Division
      incorrectly assigned org="Guerrero")
  9.  Recover organization from role_text when it was never structured out
      (~15% of dated records): take text after the title, strip years/state,
      keep it only if it carries an institution signal.
  8.  Add work_state column — physical work location:
        is_federal=True, not a foreign posting → work_state='Federal District'
        is_federal=True, foreign posting (ambassador/consul/attaché) → work_state=NULL
        state is not NULL → work_state=state (already reflects work location)
        is_federal=False, state=NULL → work_state=NULL
      state is kept as originally extracted from text (NOT filled with Federal
      District). A null state just means the text didn't mention a state.
"""

import re
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

CODE_DIR = Path(__file__).resolve().parents[2]
if str(CODE_DIR) not in sys.path:
    sys.path.append(str(CODE_DIR))

from config import DATA_DIR, MEXICAN_STATES, CITY_TO_STATE, strip_accents

GOVT_POSITIONS_CSV       = DATA_DIR / "govt_positions.csv"
CLEAN_DIR                = DATA_DIR / "clean_positions"
GOVT_POSITIONS_CLEAN_CSV = CLEAN_DIR / "govt_positions.csv"


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
# Fix 2 & 3: Year re-extraction + inverted year fix
# ---------------------------------------------------------------------------

_YEAR_RANGE_RE  = re.compile(r"(\d{4})\s*[-–]\s*(\d{4})")
_SINGLE_YEAR_RE = re.compile(r"\b(1[89]\d{2}|20[0-2]\d)\b")


def _reextract_years(text: str):
    m = _YEAR_RANGE_RE.search(text)
    if m:
        ys, ye = int(m.group(1)), int(m.group(2))
        if ys > ye:          # inverted → swap
            ys, ye = ye, ys
        return ys, ye
    singles = _SINGLE_YEAR_RE.findall(text)
    if singles:
        yr = int(singles[-1])
        return yr, yr
    return None, None

def _strip_years(text: str) -> str:
    out = re.sub(r",?\s*\d{4}\s*[-–]\s*\d{4}", "", text)
    out = re.sub(r",\s*\b(?:1[89]\d{2}|20[0-2]\d)\b\s*$", "", out)
    return re.sub(r"[,\s]+$", "", out).strip()


# ---------------------------------------------------------------------------
# Fix 4: Remove OCR garbage from organization column
# ---------------------------------------------------------------------------

_OCR_ORG_RE = re.compile(r"\d{2,}\s+mexican\s+political\s+biograph\w*\s*", re.I)

def _clean_org(org) -> Optional[str]:
    if not isinstance(org, str):
        return org
    cleaned = _OCR_ORG_RE.sub("", org).strip().rstrip(".,; ")
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned if len(cleaned) >= 3 else None


# ---------------------------------------------------------------------------
# Fix 5: Role-word-as-org → re-extract real org from text
# The extractor captured "planning", "training", "finance", etc. because
# _ROLE_ORG_RE in 04_parse_positions matched "[director] of [word]" and
# returned the word instead of the institution that follows.
# ---------------------------------------------------------------------------

_ROLE_WORDS = {
    "training", "planning", "planning and budget", "finance", "administration",
    "operations", "coordination", "inspection", "supervision", "evaluation",
    "studies", "research", "legal", "judicial", "procurement", "budget",
    "personnel", "affairs", "relations", "development", "promotion",
    "production", "services", "management", "control", "analysis",
    "programming", "budget and programming",
}

# Known named orgs / secretariats — if found in text after role word, prefer these
_KNOWN_ORG_RE = re.compile(
    r"(Secretariat\s+of\s+\w[\w\s]{3,50}?|"
    r"National\s+\w[\w\s]{3,50}?|"
    r"(?:Federal\s+)?(?:Electric\s+)?Commission\b[\w\s,]{0,30}?|"
    r"(?:National\s+)?(?:Railroads?|Railways?)\s+of\s+Mexico|"
    r"Telefonos?\s+de\s+Mexico|PEMEX|CFE|IMSS|ISSSTE|BANRURAL|CONASUPO|"
    r"Bank\s+of\s+\w[\w\s]{2,40}?|"
    r"[\w\s]{3,50}?\s+Institute\b|"
    r"[\w\s]{3,50}?\s+Commission\b|"
    r"[\w\s]{3,50}?\s+Center\b|"
    r"World\s+Bank|Inter-American[\w\s]{3,50}?|"
    r"DIF\b|IPN\b|UNAM\b)",
    re.I,
)

def _fix_role_word_org(org: str, raw: str) -> Optional[str]:
    if not isinstance(org, str) or org.strip().lower() not in _ROLE_WORDS:
        return org
    # Find the role word in the text and extract what follows the next comma
    pattern = re.compile(
        r"\bof\s+" + re.escape(org.strip()) + r"\s*,\s*(.+?)(?=,\s*\d{4}|\s*$)",
        re.I | re.DOTALL,
    )
    m = pattern.search(raw)
    if not m:
        return None     # no org found after the role word → null out
    candidate = _strip_years(m.group(1).strip().rstrip(".,; "))
    # Reject bare years, very short strings, or pure city/location names
    if len(candidate) < 4:
        return None
    if re.fullmatch(r"\d{4}", candidate.strip()):
        return None     # just a year ("director general of planning, 1979")
    if candidate.strip().lower() in _STATE_NAMES_LOWER:
        return None     # extracted a city/state, not an institution
    return candidate    # return the full institution name as-is


# ---------------------------------------------------------------------------
# Fix 6: State-as-org where real institution appears before state name
# Pattern: "[position], [REAL ORG], [state], [year]"
#          "[position], [REAL ORG of state], [year]"
# ---------------------------------------------------------------------------

_STATE_NAMES_NORM = sorted(
    {strip_accents(v.lower())
     for _, (variants, _, _) in MEXICAN_STATES.items()
     for v in variants}
    | {"federal district", "mexico city"},
    key=len, reverse=True,
)

_INSTITUTION_KW_RE = re.compile(
    r"\b(Office|Institute|Commission|Department|National|Bank|Council|"
    r"Center|Centre|Federation|Tribunal|Court|Authority|Agency|"
    r"Board|Committee|Bureau|Trust|Fund|Program|"
    r"District\s+Court|Penal\s+Court|Civil\s+Court|Judicial\s+District|"
    r"Correctional\s+District|Appellate|Appeals\s+Court|Supreme\s+Court)\b",
    re.I,
    # NOTE: "Administration" intentionally excluded — it matches "secretary of
    # administration" (a position title) and creates false positives.
)


def _has_inst_before_state(raw: str, org: str) -> bool:
    if not isinstance(raw, str) or not isinstance(org, str):
        return False
    org_l = org.strip().lower()
    raw_l = strip_accents(raw.lower())
    idx = raw_l.find(strip_accents(org_l))
    if idx < 0:
        return False
    return bool(_INSTITUTION_KW_RE.search(raw[:idx]))


def _reextract_org_before_state(raw: str, org: str) -> Optional[str]:
    """Extract the real institution that precedes the trailing state name."""
    org_l  = strip_accents(org.strip().lower())
    raw_l  = strip_accents(raw.lower())
    idx    = raw_l.find(org_l)
    if idx < 0:
        return org

    # Case A: state is preceded by a comma → trailing location, exclude from org
    # "[..., REAL ORG, State, year]"
    if idx > 0 and raw[idx - 2:idx].strip() == ",":
        text_before_state = raw[:idx].rstrip(", ")
        # Remove position title (first comma-element)
        comma_idx = text_before_state.find(",")
        if comma_idx > 0:
            org_part = _strip_years(text_before_state[comma_idx + 1:].strip().rstrip(".,; "))
            if len(org_part) >= 4:
                return org_part
        return None

    # Case B: state is part of the name ("of the Federal District")
    # "[..., REAL ORG of the State, year]" → include state in org name
    comma_idx = raw.find(",")
    if comma_idx > 0:
        after_title = raw[comma_idx + 1:].strip()
        org_part    = _strip_years(after_title.rstrip(".,; "))
        if len(org_part) >= 4:
            return org_part
    return org


def _fix_state_as_org(org: str, raw: str, state_names_lower: set) -> Optional[str]:
    if not isinstance(org, str):
        return org
    if org.strip().lower() not in state_names_lower:
        return org
    if _has_inst_before_state(raw, org):
        return _reextract_org_before_state(raw, org)
    return org     # state IS the org (attorney general of FD, treasurer of state, etc.)


_STATE_NAMES_LOWER = (
    set(_STATE_NAMES_NORM)
    | {"federal district", "mexico city"}
    | {strip_accents(c.lower()) for c in CITY_TO_STATE}  # also catch city names
)


# ---------------------------------------------------------------------------
# Fix 7: Clear GPT-hallucinated org
# org_gpt assigned a state name when the state name does not appear in the
# raw text. Detected when org == org_gpt == state_name and state ≠ in raw.
# ---------------------------------------------------------------------------

def _fix_gpt_hallucination(org: str, org_gpt: str, raw: str) -> Optional[str]:
    if not isinstance(org, str) or not isinstance(org_gpt, str):
        return org
    if org.strip().lower() not in _STATE_NAMES_LOWER:
        return org
    # If the state name assigned as org does NOT appear in the raw text → hallucination
    if strip_accents(org.lower()) not in strip_accents(str(raw).lower()):
        return None
    return org


# ---------------------------------------------------------------------------
# Fix 9: Recover organization from role_text when it was never structured out.
# ~15% of dated govt records have organization=NaN even though the institution
# is present in the raw text ("director general, Guanos and Fertilizers of
# Mexico"). Take the text after the leading title, strip trailing years/state,
# and accept it as the org only if it carries an institution signal (so generic
# entries like "private secretary to X during his campaign" stay NaN).
# ---------------------------------------------------------------------------

_INST_SIGNAL_RE = re.compile(
    r"\b(Secretariat|Ministry|Bank|Commission|Institute|Department|Office|"
    r"National|Federal|Company|Petroleos|PEMEX|CFE|IMSS|ISSSTE|CONASUPO|"
    r"BANRURAL|Police|Court|Tribunal|Council|Fund|Authority|Agency|"
    r"Railroads?|Railways?|University|Corporation|Committee|Board|Trust|"
    r"Telefonos|Comision|Fertilizers|Industries|of\s+Mexico|de\s+Mexico)\b"
    r"|\bS\.?A\.?(?:\s*de\s*C\.?V\.?| de CV| CV)?\b",
    re.I,
)

def _recover_org_from_text(raw: str) -> Optional[str]:
    if not isinstance(raw, str) or "," not in raw:
        return None
    after = _strip_years(raw.split(",", 1)[1]).strip().rstrip(".,; ")
    parts = [p.strip() for p in after.split(",") if p.strip()]
    while parts and strip_accents(parts[-1].lower()) in _STATE_NAMES_LOWER:
        parts.pop()                       # drop trailing pure-state segments
    cand = ", ".join(parts).strip().rstrip(".,; ")
    if len(cand) < 4 or strip_accents(cand.lower()) in _STATE_NAMES_LOWER:
        return None
    return cand if _INST_SIGNAL_RE.search(cand) else None


# ---------------------------------------------------------------------------
# Fix 8: work_state — physical work location
# state is kept unchanged (as extracted from text). work_state is inferred:
#   - is_federal=True, non-foreign posting → Federal District
#   - is_federal=True, foreign posting (ambassador/consul/attaché) → None
#   - state already has a value → work_state = state
#   - otherwise → None
# ---------------------------------------------------------------------------

_FOREIGN_POSTING_RE = re.compile(
    r"\b(ambassador|consul\s+general|consul|diplomatic\s+attach[ée]|"
    r"milit\w*\s+attach[ée]|charge\s+d.affaires|embassy|consulate)\b",
    re.I,
)

def _govt_work_state(state, is_federal, raw: str) -> Optional[str]:
    if pd.notna(state):
        return state          # state from text already reflects work location
    if is_federal is True:
        if _FOREIGN_POSTING_RE.search(raw):
            return None       # physically abroad, location unknown
        return "Federal District"
    return None


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def _clean_row(row: pd.Series):
    raw      = row["role_text_raw"] if pd.notna(row["role_text_raw"]) else ""
    org      = row["organization"]
    org_gpt  = row["org_gpt"]       if pd.notna(row.get("org_gpt", None)) else None
    yr_s     = row["year_start"]
    yr_e     = row["year_end"]
    state    = row["state"]
    is_fed   = row["is_federal"]

    # Fix 1: clean raw text
    raw_clean = _clean_raw(raw)
    role_text = re.sub(r"[,\s]+$", "", _strip_years(raw_clean)).strip() if raw_clean else None

    # Fix 2+3: re-extract / fix years
    if raw_clean != raw or (pd.notna(yr_s) and pd.notna(yr_e) and yr_e < yr_s):
        yr_s, yr_e = _reextract_years(raw_clean)

    # Fix 4: OCR in org
    org = _clean_org(org)

    # Fix 7: GPT hallucination (must run before fix 5/6 to null out bad orgs)
    if org is not None:
        org = _fix_gpt_hallucination(org, str(org_gpt) if org_gpt else "", raw_clean)

    # Fix 5: role-word-as-org
    if org is not None:
        org = _fix_role_word_org(org, raw_clean)

    # Fix 6: state-as-org with real institution before it
    if org is not None:
        org = _fix_state_as_org(org, raw_clean, _STATE_NAMES_LOWER)

    # Fix 9: recover org from text when still missing
    if org is None or (isinstance(org, float) and pd.isna(org)):
        org = _recover_org_from_text(raw_clean)

    # Fix 8: work_state (do NOT change state — keep as extracted from text)
    work_state = _govt_work_state(state, is_fed, raw_clean)

    return raw_clean, role_text, yr_s, yr_e, org, state, work_state


def main():
    print("Loading govt_positions.csv …")
    gp = pd.read_csv(GOVT_POSITIONS_CSV)
    print(f"  {len(gp):,} records")

    orig_raw   = gp["role_text_raw"].copy()
    orig_org   = gp["organization"].copy()
    orig_ys    = gp["year_start"].copy()
    orig_ye    = gp["year_end"].copy()
    orig_state = gp["state"].copy()
    # is_federal column needed for work_state but not modified
    gp["is_federal"] = gp["is_federal"].where(gp["is_federal"].notna(), None)

    print("Applying fixes …")
    results = gp.apply(_clean_row, axis=1)

    gp["role_text_raw"] = [r[0] for r in results]
    gp["role_text"]     = [r[1] for r in results]
    gp["year_start"]    = [r[2] for r in results]
    gp["year_end"]      = [r[3] for r in results]
    gp["organization"]  = [r[4] for r in results]
    gp["state"]         = [r[5] for r in results]
    gp["work_state"]    = [r[6] for r in results]

    def _n_chg(new, old):
        return (new.fillna("__N__").astype(str) != old.fillna("__N__").astype(str)).sum()

    gp["modified"] = (
        (gp["role_text_raw"].fillna("__N__") != orig_raw.fillna("__N__"))
        | (gp["organization"].fillna("__N__").astype(str) != orig_org.fillna("__N__").astype(str))
        | (gp["year_start"].fillna(-1) != orig_ys.fillna(-1))
        | (gp["year_end"].fillna(-1)   != orig_ye.fillna(-1))
        | (gp["state"].fillna("__N__") != orig_state.fillna("__N__"))
        # work_state is always new (not in original) — not counted in modified
    ).astype(int)

    n_mod = gp["modified"].sum()
    print(f"  Modified: {n_mod:,} / {len(gp):,} records ({100*n_mod/len(gp):.1f}%)")

    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    gp.to_csv(GOVT_POSITIONS_CLEAN_CSV, index=False)
    print(f"\nSaved → {GOVT_POSITIONS_CLEAN_CSV}")

    print(f"\n  role_text_raw : {_n_chg(gp['role_text_raw'], orig_raw):4d} changes")
    print(f"  organization  : {_n_chg(gp['organization'],  orig_org):4d} changes")
    print(f"  year_start    : {_n_chg(gp['year_start'],    orig_ys):4d} changes")
    print(f"  year_end      : {_n_chg(gp['year_end'],      orig_ye):4d} changes")
    print(f"  state         : {_n_chg(gp['state'],         orig_state):4d} changes (NOTE: state NOT filled for federal positions — use work_state)")
    n_ws_fed = (gp["work_state"] == "Federal District").sum()
    n_ws_tot = gp["work_state"].notna().sum()
    print(f"  work_state    : {n_ws_tot:4d} filled ({n_ws_fed} = Federal District, "
          f"{gp['work_state'].isna().sum()} = NULL [abroad or unknown])")

    # Org change sample
    org_chg = gp[
        (gp["organization"].fillna("__N__").astype(str) != orig_org.fillna("__N__").astype(str))
        & ~(gp["organization"].isna() & orig_org.isna())
    ]
    print(f"\n--- Sample org changes ({len(org_chg)} total) ---")
    for i, row in org_chg.head(20).iterrows():
        print(f"  BEFORE: {orig_org[i]!r}")
        print(f"   AFTER: {row['organization']!r}")
        print(f"   TEXT:  {row['role_text_raw'][:75]}")
        print()

    # work_state sample
    print(f"\n--- work_state sample ---")
    ws_fed = gp[gp["work_state"] == "Federal District"].head(3)
    for _, row in ws_fed.iterrows():
        print(f"  [FD]  state={row['state']!r}  |  {row['role_text_raw'][:65]}")
    ws_none = gp[gp["work_state"].isna() & (gp["is_federal"]==True)].head(3)
    for _, row in ws_none.iterrows():
        print(f"  [NULL/abroad]  |  {row['role_text_raw'][:65]}")


if __name__ == "__main__":
    main()
