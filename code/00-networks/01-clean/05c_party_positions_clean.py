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
# Bug in 05_party_positions.py: float(NaN) is truthy in Python, so
# `if state and state not in ("Federal District",)` incorrectly returned
# "state" for records where state was NaN.
# ---------------------------------------------------------------------------

def _fix_party_level(level: str, state) -> Optional[str]:
    if level == "state" and pd.isna(state):
        return None
    return level


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

    # party_level fix
    level = _fix_party_level(level, state)

    return raw_clean, role_text, yr_s, yr_e, org_clean, rank, level


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

    print("Applying fixes …")
    results = pp.apply(_clean_row, axis=1)

    pp["role_text_raw"] = [r[0] for r in results]
    pp["role_text"]     = [r[1] for r in results]
    pp["year_start"]    = [r[2] for r in results]
    pp["year_end"]      = [r[3] for r in results]
    pp["organization"]  = [r[4] for r in results]
    pp["party_rank"]    = [r[5] for r in results]
    pp["party_level"]   = [r[6] for r in results]

    def _n_chg(new, old):
        return (new.fillna("__N__").astype(str) != old.fillna("__N__").astype(str)).sum()

    pp["modified"] = (
        (pp["role_text_raw"].fillna("__N__") != orig_raw.fillna("__N__"))
        | (pp["organization"].fillna("__N__").astype(str) != orig_org.fillna("__N__").astype(str))
        | (pp["year_start"].fillna(-1)  != orig_ys.fillna(-1))
        | (pp["year_end"].fillna(-1)    != orig_ye.fillna(-1))
        | (pp["party_rank"].fillna("__N__")  != orig_rank.fillna("__N__"))
        | (pp["party_level"].fillna("__N__") != orig_level.fillna("__N__"))
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


if __name__ == "__main__":
    main()
