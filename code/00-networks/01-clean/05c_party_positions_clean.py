"""
05c_party_positions_clean.py

Post-processing fixes for party_positions.csv (output of 05_party_positions.py).
Reads  data/party_positions.csv
Writes data/clean_positions/party_positions.csv  (+  `modified` column = 1 if changed).

Fixes applied:
  1.  Remove OCR book-title fragments from role_text_raw
      ("s, 1935–2009", "NNN mexican political biographie", "Iberomp", "sity of")
  2.  Re-extract year_start / year_end from cleaned raw text
      (removes 1935–2009 artifact years caused by the OCR fragments)
  3.  Clean OCR garbage from organization names
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
# Main pipeline
# ---------------------------------------------------------------------------

def _clean_row(row: pd.Series):
    raw  = row["role_text_raw"] if pd.notna(row["role_text_raw"]) else ""
    org  = row["organization"]
    yr_s = row["year_start"]
    yr_e = row["year_end"]

    raw_clean = _clean_raw(raw)
    role_text = _strip_years_from_text(raw_clean) if raw_clean else None

    # Re-extract years only when the raw text actually changed
    if raw_clean != raw:
        yr_s, yr_e = _reextract_years(raw_clean)

    org_clean = _clean_org(org)

    return raw_clean, role_text, yr_s, yr_e, org_clean


def main():
    print("Loading party_positions.csv …")
    pp = pd.read_csv(PARTY_POSITIONS_CSV)
    print(f"  {len(pp):,} records")

    orig_raw = pp["role_text_raw"].copy()
    orig_org = pp["organization"].copy()
    orig_ys  = pp["year_start"].copy()
    orig_ye  = pp["year_end"].copy()

    print("Applying fixes …")
    results = pp.apply(_clean_row, axis=1)

    pp["role_text_raw"] = [r[0] for r in results]
    pp["role_text"]     = [r[1] for r in results]
    pp["year_start"]    = [r[2] for r in results]
    pp["year_end"]      = [r[3] for r in results]
    pp["organization"]  = [r[4] for r in results]

    def _n_changed(new, old):
        return (new.fillna("__N__").astype(str) != old.fillna("__N__").astype(str)).sum()

    pp["modified"] = (
        (pp["role_text_raw"].fillna("__N__") != orig_raw.fillna("__N__"))
        | (pp["organization"].fillna("__N__").astype(str) != orig_org.fillna("__N__").astype(str))
        | (pp["year_start"].fillna(-1) != orig_ys.fillna(-1))
        | (pp["year_end"].fillna(-1)   != orig_ye.fillna(-1))
    ).astype(int)

    n_mod = pp["modified"].sum()
    print(f"  Modified: {n_mod:,} / {len(pp):,} records ({100*n_mod/len(pp):.1f}%)")

    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    pp.to_csv(PARTY_POSITIONS_CLEAN_CSV, index=False)
    print(f"\nSaved → {PARTY_POSITIONS_CLEAN_CSV}")

    print(f"\n  role_text_raw : {_n_changed(pp['role_text_raw'], orig_raw):3d} changes")
    print(f"  organization  : {_n_changed(pp['organization'], orig_org):3d} changes")
    print(f"  year_start    : {_n_changed(pp['year_start'], orig_ys):3d} changes")
    print(f"  year_end      : {_n_changed(pp['year_end'],   orig_ye):3d} changes")

    print("\n--- Sample changes ---")
    changed = pp[pp["modified"] == 1]
    for _, row in changed.head(20).iterrows():
        i = row.name
        old_raw = orig_raw[i]
        new_raw = row["role_text_raw"]
        old_ys, old_ye = orig_ys[i], orig_ye[i]
        new_ys, new_ye = row["year_start"], row["year_end"]
        if old_raw != new_raw:
            print(f"  RAW:  {str(old_raw)[:80]}")
            print(f"    →   {str(new_raw)[:80]}")
        if str(old_ys) != str(new_ys) or str(old_ye) != str(new_ye):
            print(f"  YRS:  [{old_ys}–{old_ye}] → [{new_ys}–{new_ye}]")
        print()


if __name__ == "__main__":
    main()
