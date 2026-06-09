"""
05h_other_positions_clean.py

Post-processing fixes for other_positions.csv (output of 05_other_positions.py).
Reads  data/other_positions.csv
Writes data/clean_positions/other_positions.csv  (+  `modified` column = 1 if changed).

other_positions holds private-sector, academic, religious and miscellaneous
roles (AiCamp "other" category). Fixes applied:

  1.  Remove OCR book-title / page-break fragments from role_text_raw and
      organization ("s, 1935–2009", "NNN mexican political biographie",
      "sity of"). These land mid-text in this dataset, e.g.
      "director of government 108 mexican political biographie newspaper" →
      "director of government newspaper". role_text is regenerated from the
      cleaned raw text.
  2.  Re-extract year_start / year_end from cleaned raw text when the OCR fix
      changed it.
  3.  Fix year anomalies:
        a. year_end < year_start  → swap
        b. OCR misread "2012" as "1912" (year_start ≥ 2000, year_end < 1950)
           → year_end += 100
        c. implausibly early (< 1850) or late (> 2009) bound → drop it
  4.  Collapse double spaces in position_title / organization.

Missing years are left null: a position with no date in the source biography
has no recoverable year (04 already extracts every stated year), so no
imputation is performed.
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

OTHER_POSITIONS_CSV       = DATA_DIR / "other_positions.csv"
CLEAN_DIR                 = DATA_DIR / "clean_positions"
OTHER_POSITIONS_CLEAN_CSV = CLEAN_DIR / "other_positions.csv"


# ---------------------------------------------------------------------------
# Fix 1: Remove OCR book-title / page-break fragments
# ---------------------------------------------------------------------------

_OCR_RAW_RE = re.compile(
    r"\bs,\s*1935[–\-]2009\b"
    r"|\bBiograph\w*,?\s*1935[–\-]2009\b"
    r"|\d{2,}\s+mexican\s+political\s+biograph\w*"
    r"|\bIberomp\b"
    r"|\bsity\s+of\b",
    re.I,
)


def _clean_ocr(text):
    if not isinstance(text, str):
        return text
    cleaned = _OCR_RAW_RE.sub(" ", text)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    # tidy artifacts left by removing a mid-text fragment
    cleaned = re.sub(r"\s+,", ",", cleaned).strip(" ,")
    return cleaned


# ---------------------------------------------------------------------------
# Fix 2 / 3: Year re-extraction and anomaly repair
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


def _strip_years(text: str) -> str:
    out = re.sub(r"[,\s]*\d{4}[\s\-–\d]*$", "", text)
    return re.sub(r"[,\s]+$", "", out).strip()


def _fix_years(yr_s, yr_e):
    if pd.notna(yr_s) and pd.notna(yr_e):
        if yr_s >= 2000 and yr_e < 1950:      # OCR "2012" → "1912"
            return yr_s, yr_e + 100
        if yr_e < yr_s:                       # inverted
            yr_s, yr_e = yr_e, yr_s
    if pd.notna(yr_s) and (yr_s < 1850 or yr_s > 2009):
        yr_s = yr_e if (pd.notna(yr_e) and 1850 <= yr_e <= 2009) else None
    if pd.notna(yr_e) and (yr_e < 1850 or yr_e > 2009):
        yr_e = yr_s
    return yr_s, yr_e


# ---------------------------------------------------------------------------
# Fix 4: Collapse double spaces in text fields
# ---------------------------------------------------------------------------

def _collapse(text):
    if not isinstance(text, str):
        return text
    return re.sub(r"\s{2,}", " ", text).strip()


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def _clean_row(row: pd.Series):
    raw   = row["role_text_raw"] if pd.notna(row["role_text_raw"]) else ""
    org   = row["organization"]
    title = row["position_title"]
    yr_s  = row["year_start"]
    yr_e  = row["year_end"]

    # Fix 1: OCR cleanup + regenerate role_text
    raw_clean = _clean_ocr(raw)
    role_text = _strip_years(raw_clean) if raw_clean else None
    if role_text == "":
        role_text = None
    org   = _clean_ocr(org)

    # Fix 2: re-extract years when raw changed
    if raw_clean != raw:
        yr_s, yr_e = _reextract_years(raw_clean)

    # Fix 3: year anomalies
    yr_s, yr_e = _fix_years(yr_s, yr_e)

    # Fix 4: collapse double spaces
    title = _collapse(title)
    org   = _collapse(org)

    return raw_clean, role_text, title, org, yr_s, yr_e


def main():
    print("Loading other_positions.csv …")
    o = pd.read_csv(OTHER_POSITIONS_CSV)
    print(f"  {len(o):,} records")

    orig_raw   = o["role_text_raw"].copy()
    orig_org   = o["organization"].copy()
    orig_title = o["position_title"].copy()
    orig_ys    = o["year_start"].copy()
    orig_ye    = o["year_end"].copy()

    print("Applying fixes …")
    results = o.apply(_clean_row, axis=1)
    o["role_text_raw"]  = [r[0] for r in results]
    o["role_text"]      = [r[1] for r in results]
    o["position_title"] = [r[2] for r in results]
    o["organization"]   = [r[3] for r in results]
    o["year_start"]     = [r[4] for r in results]
    o["year_end"]       = [r[5] for r in results]

    o["modified"] = (
        (o["role_text_raw"].fillna("__N__")  != orig_raw.fillna("__N__"))
        | (o["organization"].fillna("__N__").astype(str)   != orig_org.fillna("__N__").astype(str))
        | (o["position_title"].fillna("__N__").astype(str) != orig_title.fillna("__N__").astype(str))
        | (o["year_start"].fillna(-1)        != orig_ys.fillna(-1))
        | (o["year_end"].fillna(-1)          != orig_ye.fillna(-1))
    ).astype(int)

    n_mod = o["modified"].sum()
    print(f"  Modified: {n_mod:,} / {len(o):,} records ({100*n_mod/len(o):.1f}%)")

    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    o.to_csv(OTHER_POSITIONS_CLEAN_CSV, index=False)
    print(f"\nSaved → {OTHER_POSITIONS_CLEAN_CSV}")

    def _n_chg(new, old):
        return (new.fillna("__N__").astype(str) != old.fillna("__N__").astype(str)).sum()

    print(f"\n  role_text_raw  : {_n_chg(o['role_text_raw'],  orig_raw):4d} changes")
    print(f"  organization   : {_n_chg(o['organization'],   orig_org):4d} changes")
    print(f"  position_title : {_n_chg(o['position_title'], orig_title):4d} changes")
    print(f"  year_start     : {_n_chg(o['year_start'],     orig_ys):4d} changes")
    print(f"  year_end       : {_n_chg(o['year_end'],       orig_ye):4d} changes")

    raw_fixed = o[o["role_text_raw"].fillna("__N__") != orig_raw.fillna("__N__")]
    print(f"\n--- Sample OCR cleanups ({len(raw_fixed)} total) ---")
    for _, row in raw_fixed.head(12).iterrows():
        i = row.name
        print(f"  {orig_raw[i][:55]!r}\n   → {row['role_text_raw'][:55]!r}")


if __name__ == "__main__":
    main()
