"""
05d_labor_positions_clean.py

Post-processing fixes for labor_positions.csv (output of 05_labor_positions.py).
Reads  data/labor_positions.csv
Writes data/clean_positions/labor_positions.csv  (+  `modified` column = 1 if changed).

Fixes applied:
  1.  Remove OCR book-title fragments from role_text_raw
      ("s, 1935–2009", "NNN mexican political biographie")
  2.  Re-extract year_start / year_end from cleaned raw text
  3.  Clean OCR garbage from org_clean / organization columns
  4.  Drop cross-dataset duplicate: "Secretary, National School of Economics,
      1936–1938" for Rangel Couto, Hugo (person_id=2177, record_id=34724).
      This entry appears in education.csv as an academic_role — labor_positions
      captured it incorrectly as a union/labor position.
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

LABOR_POSITIONS_CSV       = DATA_DIR / "labor_positions.csv"
CLEAN_DIR                 = DATA_DIR / "clean_positions"
LABOR_POSITIONS_CLEAN_CSV = CLEAN_DIR / "labor_positions.csv"


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
# Fix 3: Clean OCR garbage from organization columns
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
# Fix 4: Drop cross-dataset duplicate
# Rangel Couto, Hugo — "Secretary, National School of Economics, 1936–1938"
# This is an academic role already present in education.csv (record_id 34732).
# Identified by person_id + text pattern (robust to pipeline re-runs).
# ---------------------------------------------------------------------------

_DUPLICATE_PERSON_ID = 2177
_DUPLICATE_TEXT_RE   = re.compile(
    r"^secretary,?\s+national\s+school\s+of\s+economics", re.I
)


def _is_duplicate(row: pd.Series) -> bool:
    return bool(
        row["person_id"] == _DUPLICATE_PERSON_ID
        and isinstance(row["role_text_raw"], str)
        and _DUPLICATE_TEXT_RE.match(row["role_text_raw"].strip())
    )


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def _clean_row(row: pd.Series):
    raw  = row["role_text_raw"] if pd.notna(row["role_text_raw"]) else ""
    org  = row["organization"]
    org_clean = row["org_clean"]
    yr_s = row["year_start"]
    yr_e = row["year_end"]

    raw_clean = _clean_raw(raw)
    role_text = _strip_years_from_text(raw_clean) if raw_clean else None

    if raw_clean != raw:
        yr_s, yr_e = _reextract_years(raw_clean)

    org_out      = _clean_org(org)
    org_clean_out = _clean_org(org_clean)

    return raw_clean, role_text, yr_s, yr_e, org_out, org_clean_out


def main():
    print("Loading labor_positions.csv …")
    lp = pd.read_csv(LABOR_POSITIONS_CSV)
    print(f"  {len(lp):,} records")

    # Fix 4: drop the education duplicate before any other processing
    dup_mask = lp.apply(_is_duplicate, axis=1)
    n_dropped = dup_mask.sum()
    if n_dropped:
        print(f"\nDropping {n_dropped} cross-dataset duplicate(s):")
        print(lp[dup_mask][["person_name","role_text_raw","year_start","year_end"]].to_string())
    lp = lp[~dup_mask].reset_index(drop=True)

    orig_raw      = lp["role_text_raw"].copy()
    orig_org      = lp["organization"].copy()
    orig_org_clean= lp["org_clean"].copy()
    orig_ys       = lp["year_start"].copy()
    orig_ye       = lp["year_end"].copy()

    print("\nApplying text / year / org fixes …")
    results = lp.apply(_clean_row, axis=1)

    lp["role_text_raw"] = [r[0] for r in results]
    lp["role_text"]     = [r[1] for r in results]
    lp["year_start"]    = [r[2] for r in results]
    lp["year_end"]      = [r[3] for r in results]
    lp["organization"]  = [r[4] for r in results]
    lp["org_clean"]     = [r[5] for r in results]

    def _n_chg(new, old):
        return (new.fillna("__N__").astype(str) != old.fillna("__N__").astype(str)).sum()

    lp["modified"] = (
        (lp["role_text_raw"].fillna("__N__") != orig_raw.fillna("__N__"))
        | (lp["organization"].fillna("__N__").astype(str) != orig_org.fillna("__N__").astype(str))
        | (lp["org_clean"].fillna("__N__").astype(str)   != orig_org_clean.fillna("__N__").astype(str))
        | (lp["year_start"].fillna(-1) != orig_ys.fillna(-1))
        | (lp["year_end"].fillna(-1)   != orig_ye.fillna(-1))
    ).astype(int)

    n_mod = lp["modified"].sum()
    print(f"  Modified: {n_mod:,} / {len(lp):,} records ({100*n_mod/len(lp):.1f}%)")

    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    lp.to_csv(LABOR_POSITIONS_CLEAN_CSV, index=False)
    print(f"\nSaved → {LABOR_POSITIONS_CLEAN_CSV}")
    print(f"  Records before: {len(lp) + n_dropped:,}")
    print(f"  Dropped (cross-dataset dupes): {n_dropped}")
    print(f"  Records after:  {len(lp):,}")
    print(f"\n  role_text_raw : {_n_chg(lp['role_text_raw'], orig_raw):3d} changes")
    print(f"  organization  : {_n_chg(lp['organization'],  orig_org):3d} changes")
    print(f"  org_clean     : {_n_chg(lp['org_clean'],     orig_org_clean):3d} changes")
    print(f"  year_start    : {_n_chg(lp['year_start'],    orig_ys):3d} changes")
    print(f"  year_end      : {_n_chg(lp['year_end'],      orig_ye):3d} changes")

    print("\n--- Sample year corrections ---")
    y_mask = (
        lp["year_start"].fillna(-1).astype(str) != orig_ys.fillna(-1).astype(str)
    ) | (lp["year_end"].fillna(-1).astype(str) != orig_ye.fillna(-1).astype(str))
    for i, row in lp[y_mask].head(10).iterrows():
        print(f"  [{orig_ys[i]}–{orig_ye[i]}] → [{row['year_start']}–{row['year_end']}]"
              f"  |  {row['role_text_raw'][:65]}")


if __name__ == "__main__":
    main()
