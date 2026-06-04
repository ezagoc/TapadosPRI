"""
Build the military positions dataset from biographies_corrected.csv (field j).

Ai Camp category j — Military experience: career information, with the exception
of high-level appointive positions in the Secretariat of National Defense or the
Navy (those appear in govt_positions). Includes the highest rank achieved, date
of promotion, revolutionary activity, and unit/zone commands.

Variables extracted:
  - branch:           army / navy / air_force / unknown
  - rank:             controlled vocabulary (division_general, brigade_general,
                      brigadier_general, colonel, lieutenant_colonel, major,
                      captain, lieutenant, sergeant, corporal, private, unknown)
  - is_promotion:     True if this entry records a rank promotion
  - is_commander:     True if the entry records commanding a unit or zone
  - is_revolutionary: True if the entry mentions Revolutionary activity
  - is_career_officer: True for the whole biography (career officer marker)
  - year_start, year_end
  - state:            geographic state of the assignment

Wide format (one row per person):
  - branch_army, branch_navy, branch_air_force (dummies)
  - is_career_officer, is_revolutionary
  - ever_division_general, ever_brigade_general, ever_brigadier_general,
    ever_colonel, ever_officer (captain or above)
  - highest_rank, first_military_year, last_military_year
  - n_military_entries, n_commands

Input:  data/biographies_corrected.csv        (field_j column = Ai Camp category j)
Output: data/military_positions.csv
        data/military_positions_wide.csv
"""

import re
from typing import Optional
from pathlib import Path
import sys

import pandas as pd

CODE_DIR = Path(__file__).resolve().parents[2]
if str(CODE_DIR) not in sys.path:
    sys.path.append(str(CODE_DIR))

from config import (
    BIOGRAPHIES_CSV,
    MILITARY_POSITIONS_CSV,
    MILITARY_POSITIONS_WIDE_CSV,
    MEXICAN_STATES,
    STATE_LOOKUP_NORM,
    CITY_TO_STATE_NORM,
    FEDERAL_KEYWORDS_NORM,
    strip_accents,
    clean_text,
    MONTH_ABBREV_MAP,
)

# ---------------------------------------------------------------------------
# OCR cleanup
# ---------------------------------------------------------------------------

_OCR_RE = re.compile(
    r"\bs,\s*1935[–\-]2009\b"
    r"|\bBiograph\w*,?\s*1935[–\-]2009\b"
    r"|\d{2,}\s+mexican\s+political\s+biograph\w*"
    r"|\bsity\s+of\b"
    r"|\bmp,?\s+s,\s*1935[–\-]2009\b",
    re.I,
)

def _clean_raw(text: str) -> str:
    cleaned = _OCR_RE.sub(" ", text)
    return re.sub(r"\s{2,}", " ", cleaned).strip()

# ---------------------------------------------------------------------------
# Year extraction
# ---------------------------------------------------------------------------

_YEAR_RANGE_RE  = re.compile(r"(\d{4})\s*[-–]\s*(\d{4})")
_SINGLE_YEAR_RE = re.compile(r"\b(1[89]\d{2}|20[0-2]\d)\b")

def _extract_years(text: str):
    m = _YEAR_RANGE_RE.search(text)
    if m:
        return int(m.group(1)), int(m.group(2))
    singles = _SINGLE_YEAR_RE.findall(text)
    if singles:
        yr = int(singles[-1])
        return yr, yr
    return None, None

def _strip_years(text: str) -> str:
    out = re.sub(r",?\s*\d{4}\s*[-–]\s*\d{4}", "", text)
    out = re.sub(r",\s*\b(?:1[89]\d{2}|20[0-2]\d)\b\s*$", "", out)
    out = re.sub(r",\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.\s*\d+,?\s*$", "", out, flags=re.I)
    return re.sub(r"[,\s]+$", "", out).strip()

# ---------------------------------------------------------------------------
# Branch classification
# ---------------------------------------------------------------------------

_BRANCH_PATTERNS = [
    ("air_force", re.compile(
        r"\bair\s+force\b|\bair\s+squadron\b|\bair\s+base\b|\bair\s+group\b"
        r"|\bair\s+wing\b|\bair\s+college\b|\bflight\b|\bpilot\b|\bcadet.*air\b"
        r"|\bsquadron\s+\d+\b",
        re.I,
    )),
    ("navy", re.compile(
        r"\bnavy\b|\bnaval\b|\bfleet\b|\bvice\s+admiral\b|\badmiral\b"
        r"|\bmarine\s+corps\b|\bcoast\s+guard\b",
        re.I,
    )),
    ("army", re.compile(
        r"\barmy\b|\binfantry\b|\bartillery\b|\bcavalry\b|\bbattalion\b"
        r"|\bbrigade\b|\bdivision\b|\bregiment\b|\bmilitary\s+zone\b"
        r"|\bmilitary\s+region\b|\bmilitary\s+camp\b|\bsoldier\b"
        r"|\bconstitutional\s+army\b|\brevolutionary\s+army\b"
        r"|\bfederal\s+army\b|\bnational\s+defense\b"
        r"|\bjoined\s+(the\s+)?(army|revolution|forces)\b",
        re.I,
    )),
]


def classify_branch(text: str) -> str:
    for branch, pat in _BRANCH_PATTERNS:
        if pat.search(text):
            return branch
    return "unknown"

# ---------------------------------------------------------------------------
# Rank classification  — ordered from highest to lowest
# ---------------------------------------------------------------------------

_RANK_PATTERNS = [
    ("division_general",    re.compile(r"\bdivision\s+general\b", re.I)),
    ("brigade_general",     re.compile(r"\bbrigade\s+general\b", re.I)),
    ("brigadier_general",   re.compile(r"\bbrigadier\s+general\b", re.I)),
    ("general",             re.compile(r"\brank\s+of\s+general\b|\bgeneral\b(?!\s+(?:staff|headquarters|directorate|administration|manager|delegate|delegate|coordinator|secretary|inspector|director|command))", re.I)),
    ("vice_admiral",        re.compile(r"\bvice\s+admiral\b", re.I)),
    ("colonel",             re.compile(r"\bcolonel\b", re.I)),
    ("lieutenant_colonel",  re.compile(r"\blieutenant\s+colonel\b", re.I)),
    ("major",               re.compile(r"\bmajor\b(?!\s+general)", re.I)),
    ("captain",             re.compile(r"\b(?:1st\s+|2nd\s+)?captain\b", re.I)),
    ("lieutenant",          re.compile(r"\b(?:1st\s+|2nd\s+)?lieutenant\b", re.I)),
    ("sergeant",            re.compile(r"\bsergeant\b", re.I)),
    ("corporal",            re.compile(r"\bcorporal\b", re.I)),
    ("private",             re.compile(r"\bprivate\b|\bsoldier\b", re.I)),
]

_RANK_ORDER = {
    "division_general": 1, "brigade_general": 2, "brigadier_general": 3,
    "general": 4, "vice_admiral": 5, "colonel": 6, "lieutenant_colonel": 7,
    "major": 8, "captain": 9, "lieutenant": 10, "sergeant": 11,
    "corporal": 12, "private": 13, "unknown": 99,
}


def classify_rank(text: str) -> str:
    for rank, pat in _RANK_PATTERNS:
        if pat.search(text):
            return rank
    return "unknown"

# ---------------------------------------------------------------------------
# Entry-level flags
# ---------------------------------------------------------------------------

_PROMOTION_RE = re.compile(
    r"\brank\s+of\b|\bpromoted\s+to\b|\breached\s+rank\b|\brank\s+of\s+(?:general|colonel|major|captain|lieutenant)\b",
    re.I,
)
_COMMANDER_RE = re.compile(
    r"\bcommander\b|\bcommanding\s+(?:general|officer)\b"
    r"|\bchief\s+of\s+(?:staff|military\s+operations|operations)\b"
    r"|\bcommander,\s+(?:\d+(?:st|nd|rd|th)?\s+)?(?:military\s+zone|military\s+region|air\s+base|air\s+group|battalion|regiment|brigade|division)\b",
    re.I,
)
_REVOLUTIONARY_RE = re.compile(
    r"\bRevolution\b|\bMadero\b|\bZapata\b|\bCarranza\b|\bObregon\b|\bVilla\b"
    r"|\bConstitutionalist\b|\bPlan\s+of\b|\bjoined\s+(?:the\s+)?Revolution\b"
    r"|\bjoined\s+(?:the\s+)?(?:Federal|Constitutional|Revolutionary)\s+Army\b"
    r"|\bfought\s+(?:against|with|under)\b|\bParticipant,\s+Revolution\b",
    re.I,
)
_CAREER_RE = re.compile(r"\bcareer\s+(?:army|naval|navy|air\s+force)\s+officer\b", re.I)

# ---------------------------------------------------------------------------
# State extraction (reusing config lookups)
# ---------------------------------------------------------------------------

_STATE_VARIANTS_NORM = sorted(
    [(strip_accents(v.lower()), canonical)
     for canonical, (variants, _, _) in MEXICAN_STATES.items()
     for v in variants],
    key=lambda x: len(x[0]), reverse=True,
)


def extract_state(text: str) -> Optional[str]:
    t = strip_accents(text.lower())
    for variant, canonical in _STATE_VARIANTS_NORM:
        if variant in t:
            return canonical
    for kw in FEDERAL_KEYWORDS_NORM:
        if kw in t:
            return "Federal District"
    for city, state in sorted(CITY_TO_STATE_NORM.items(), key=lambda x: -len(x[0])):
        if city in t:
            return state
    return None

# ---------------------------------------------------------------------------
# Parse one biography's field_j into individual entries
# ---------------------------------------------------------------------------

def parse_military_entry(entry: str, is_career: bool, person_name: str) -> Optional[dict]:
    entry = _clean_raw(clean_text(entry.strip()))
    if not entry or len(entry) < 5:
        return None

    role_text_raw = entry
    year_start, year_end = _extract_years(entry)
    role_text = _strip_years(entry)

    branch      = classify_branch(entry)
    rank        = classify_rank(entry)
    is_promo    = bool(_PROMOTION_RE.search(entry))
    is_cmd      = bool(_COMMANDER_RE.search(entry))
    is_rev      = bool(_REVOLUTIONARY_RE.search(entry))
    state       = extract_state(entry)

    return {
        "role_text_raw":    role_text_raw,
        "role_text":        role_text,
        "branch":           branch,
        "rank":             rank,
        "is_promotion":     is_promo,
        "is_commander":     is_cmd,
        "is_revolutionary": is_rev,
        "is_career_officer":is_career,
        "state":            state,
        "year_start":       year_start,
        "year_end":         year_end,
    }


def parse_person_military(name: str, field_j: str,
                           birth_date_clean: Optional[str],
                           birth_date_precision: Optional[str],
                           person_id: int) -> list[dict]:
    if not isinstance(field_j, str) or not field_j.strip():
        return []
    if field_j.strip().lower() == "none.":
        return []

    text = _clean_raw(clean_text(field_j))
    is_career = bool(_CAREER_RE.search(text))
    entries = [e.strip() for e in text.split(";") if len(e.strip()) >= 5]

    records = []
    for entry in entries:
        rec = parse_military_entry(entry, is_career, name)
        if rec:
            rec["person_id"]            = person_id
            rec["person_name"]          = name
            rec["birth_date_clean"]     = birth_date_clean
            rec["birth_date_precision"] = birth_date_precision
            records.append(rec)
    return records

# ---------------------------------------------------------------------------
# Main — parse all biographies
# ---------------------------------------------------------------------------

print("Loading biographies_corrected.csv …")
bio = pd.read_csv(BIOGRAPHIES_CSV)
print(f"  {len(bio)} biographies loaded")

# Assign person_id consistent with parsed_positions.csv approach
# (sequential integer by order of appearance, 1-based)
bio = bio.reset_index(drop=True)
bio["person_id"] = bio.index + 1

# Parse birth dates (reuse logic from 04_parse_positions)
from config import strip_accents as _sa
bio_mil = bio[bio["field_j"].notna() & (bio["field_j"].str.strip() != "")].copy()
print(f"  {len(bio_mil)} biographies with military data")

# Build birth date columns from existing parsed_positions if available
# Fall back to None (we'll join from parsed_positions after)
all_records = []
for _, row in bio_mil.iterrows():
    recs = parse_person_military(
        name=str(row["name"]),
        field_j=str(row["field_j"]),
        birth_date_clean=None,
        birth_date_precision=None,
        person_id=int(row["person_id"]),
    )
    all_records.extend(recs)

print(f"  {len(all_records)} military position entries extracted")

mil = pd.DataFrame(all_records)

# Assign record_id
mil.insert(0, "record_id", range(1, len(mil) + 1))

# Join birth dates from parsed_positions.csv for consistency
from config import PARSED_POSITIONS_CSV
pp = pd.read_csv(PARSED_POSITIONS_CSV, usecols=["person_id","birth_date_clean","birth_date_precision"])
pp_bd = pp.drop_duplicates("person_id").set_index("person_id")[["birth_date_clean","birth_date_precision"]]
mil["birth_date_clean"]     = mil["person_id"].map(pp_bd["birth_date_clean"])
mil["birth_date_precision"] = mil["person_id"].map(pp_bd["birth_date_precision"])

# Reorder columns
cols = [
    "record_id", "person_id", "person_name",
    "role_text_raw", "role_text",
    "branch", "rank",
    "is_promotion", "is_commander", "is_revolutionary", "is_career_officer",
    "state", "year_start", "year_end",
    "birth_date_clean", "birth_date_precision",
]
mil = mil[cols]

# work_state = state for military: assignment location IS physical work location.
mil["work_state"] = mil["state"]

# ---------------------------------------------------------------------------
# Save long format
# ---------------------------------------------------------------------------

mil.to_csv(MILITARY_POSITIONS_CSV, index=False)

print(f"\nMilitary records (long): {len(mil)}")
print(f"\nBranch distribution:")
print(mil["branch"].value_counts().to_string())
print(f"\nRank distribution:")
print(mil["rank"].value_counts().to_string())
print(f"\nFlags:")
print(f"  is_career_officer: {mil['is_career_officer'].sum()}")
print(f"  is_revolutionary:  {mil['is_revolutionary'].sum()}")
print(f"  is_commander:      {mil['is_commander'].sum()}")
print(f"  is_promotion:      {mil['is_promotion'].sum()}")

# ---------------------------------------------------------------------------
# Wide format — one row per person
# ---------------------------------------------------------------------------

_OFFICER_RANKS = {"division_general","brigade_general","brigadier_general",
                  "general","vice_admiral","colonel","lieutenant_colonel",
                  "major","captain"}


def _best_rank(ranks: pd.Series) -> Optional[str]:
    valid = [r for r in ranks if isinstance(r, str) and r != "unknown"]
    if not valid:
        return None
    return min(valid, key=lambda r: _RANK_ORDER.get(r, 99))


def make_wide(mil: pd.DataFrame) -> pd.DataFrame:
    def agg(sub):
        ranks   = sub["rank"]
        return pd.Series({
            "birth_date_clean":       sub["birth_date_clean"].iloc[0],
            "birth_date_precision":   sub["birth_date_precision"].iloc[0],
            "n_military_entries":     len(sub),
            "first_military_year":    sub["year_start"].min(),
            "last_military_year":     sub["year_end"].max(),
            "branch_army":            int((sub["branch"] == "army").any()),
            "branch_navy":            int((sub["branch"] == "navy").any()),
            "branch_air_force":       int((sub["branch"] == "air_force").any()),
            "is_career_officer":      int(sub["is_career_officer"].any()),
            "is_revolutionary":       int(sub["is_revolutionary"].any()),
            "ever_division_general":  int((ranks == "division_general").any()),
            "ever_brigade_general":   int((ranks == "brigade_general").any()),
            "ever_brigadier_general": int((ranks == "brigadier_general").any()),
            "ever_colonel":           int((ranks == "colonel").any()),
            "ever_officer":           int(ranks.isin(_OFFICER_RANKS).any()),
            "highest_rank":           _best_rank(ranks),
            "n_commands":             int(sub["is_commander"].sum()),
        })

    wide = (
        mil.groupby(["person_id", "person_name"], sort=False)
        .apply(agg, include_groups=False)
        .reset_index()
    )
    return wide


wide = make_wide(mil)
wide.to_csv(MILITARY_POSITIONS_WIDE_CSV, index=False)

print(f"\nWide format: {len(wide)} persons")
print(f"  Career officers:    {wide['is_career_officer'].sum()}")
print(f"  Revolutionary:      {wide['is_revolutionary'].sum()}")
print(f"  Branch army:        {wide['branch_army'].sum()}")
print(f"  Branch navy:        {wide['branch_navy'].sum()}")
print(f"  Branch air force:   {wide['branch_air_force'].sum()}")
print(f"  Ever div. general:  {wide['ever_division_general'].sum()}")
print(f"  Ever brig. general: {wide['ever_brigade_general'].sum()}")
print(f"  Ever colonel:       {wide['ever_colonel'].sum()}")
print(f"\nHighest rank distribution:")
print(wide["highest_rank"].value_counts().to_string())
print(f"\nSaved long: {MILITARY_POSITIONS_CSV}")
print(f"Saved wide: {MILITARY_POSITIONS_WIDE_CSV}")
