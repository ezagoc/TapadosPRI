"""
05g_military_positions_clean.py

Post-processing fixes for military_positions.csv (output of 05_military_positions.py).
Reads  data/military_positions.csv
Writes data/clean_positions/military_positions.csv  (+  `modified` column = 1 if changed).

Fixes applied:
  1.  Remove OCR book-title / page-break fragments from role_text_raw
      ("s, 1935–2009", "NNN mexican political biographie", "sity of") and
      regenerate role_text from the cleaned raw text.
  2.  Re-extract year_start / year_end from cleaned raw text when the OCR fix
      changed it.
  3.  Fix year anomalies:
        a. year_end < year_start  → swap (e.g. source typo "1899–1812")
        b. implausibly early year_start (< 1880, before any subject was active)
           → fall back to year_end
        c. implausibly late year (> 2009) → drop the offending bound
  4.  Drop degenerate records whose role text is empty/"None" after cleaning
      (these carry no military information).
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

MILITARY_POSITIONS_CSV       = DATA_DIR / "military_positions.csv"
CLEAN_DIR                    = DATA_DIR / "clean_positions"
MILITARY_POSITIONS_CLEAN_CSV = CLEAN_DIR / "military_positions.csv"


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


def _clean_raw(text: str) -> str:
    if not isinstance(text, str):
        return ""
    cleaned = _OCR_RAW_RE.sub(" ", text)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


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
    """Repair inverted / implausibly early / implausibly late year bounds."""
    if pd.notna(yr_s) and pd.notna(yr_e):
        if yr_e < yr_s:                       # source typo "1899–1812"
            yr_s, yr_e = yr_e, yr_s
    # implausibly early start (no subject active before ~1880)
    if pd.notna(yr_s) and yr_s < 1880:
        yr_s = yr_e if (pd.notna(yr_e) and yr_e >= 1880) else None
    if pd.notna(yr_e) and yr_e < 1880:
        yr_e = yr_s
    # implausibly late
    if pd.notna(yr_s) and yr_s > 2009:
        yr_s = None
    if pd.notna(yr_e) and yr_e > 2009:
        yr_e = yr_s
    return yr_s, yr_e


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def _clean_row(row: pd.Series):
    raw  = row["role_text_raw"] if pd.notna(row["role_text_raw"]) else ""
    yr_s = row["year_start"]
    yr_e = row["year_end"]

    # Fix 1: OCR cleanup + regenerate role_text
    raw_clean = _clean_raw(raw)
    role_text = _strip_years(raw_clean) if raw_clean else None
    if role_text == "":
        role_text = None

    # Fix 2: re-extract years if the raw text changed
    if raw_clean != raw:
        yr_s, yr_e = _reextract_years(raw_clean)

    # Fix 3: anomaly repair
    yr_s, yr_e = _fix_years(yr_s, yr_e)

    return raw_clean, role_text, yr_s, yr_e


def _is_degenerate(raw_clean: str) -> bool:
    """Record carries no military info (empty or just 'None' punctuation)."""
    if not isinstance(raw_clean, str):
        return True
    stripped = re.sub(r"[^a-z]", "", raw_clean.lower())
    return stripped in ("", "none")


def main():
    print("Loading military_positions.csv …")
    mil = pd.read_csv(MILITARY_POSITIONS_CSV)
    print(f"  {len(mil):,} records")

    orig_raw = mil["role_text_raw"].copy()
    orig_ys  = mil["year_start"].copy()
    orig_ye  = mil["year_end"].copy()

    print("Applying fixes …")
    results = mil.apply(_clean_row, axis=1)
    mil["role_text_raw"] = [r[0] for r in results]
    mil["role_text"]     = [r[1] for r in results]
    mil["year_start"]    = [r[2] for r in results]
    mil["year_end"]      = [r[3] for r in results]

    # Fix 4: drop degenerate records
    before = len(mil)
    keep = ~mil["role_text_raw"].apply(_is_degenerate)
    dropped = int((~keep).sum())
    orig_raw, orig_ys, orig_ye = orig_raw[keep], orig_ys[keep], orig_ye[keep]
    mil = mil[keep].reset_index(drop=True)
    orig_raw = orig_raw.reset_index(drop=True)
    orig_ys  = orig_ys.reset_index(drop=True)
    orig_ye  = orig_ye.reset_index(drop=True)

    mil["modified"] = (
        (mil["role_text_raw"].fillna("__N__") != orig_raw.fillna("__N__"))
        | (mil["year_start"].fillna(-1)       != orig_ys.fillna(-1))
        | (mil["year_end"].fillna(-1)         != orig_ye.fillna(-1))
    ).astype(int)

    n_mod = mil["modified"].sum()
    print(f"  Dropped degenerate: {dropped}")
    print(f"  Modified: {n_mod:,} / {len(mil):,} records ({100*n_mod/len(mil):.1f}%)")

    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    mil.to_csv(MILITARY_POSITIONS_CLEAN_CSV, index=False)
    print(f"\nSaved → {MILITARY_POSITIONS_CLEAN_CSV}")

    def _n_chg(new, old):
        return (new.fillna("__N__").astype(str) != old.fillna("__N__").astype(str)).sum()

    print(f"\n  role_text_raw : {_n_chg(mil['role_text_raw'], orig_raw):4d} changes")
    print(f"  year_start    : {_n_chg(mil['year_start'],    orig_ys):4d} changes")
    print(f"  year_end      : {_n_chg(mil['year_end'],      orig_ye):4d} changes")

    yr_fixed = mil[
        (mil["year_start"].fillna(-1) != orig_ys.fillna(-1)) |
        (mil["year_end"].fillna(-1)   != orig_ye.fillna(-1))
    ]
    if not yr_fixed.empty:
        print(f"\n--- Year fixes ({len(yr_fixed)}) ---")
        for i, row in yr_fixed.iterrows():
            print(f"  [{orig_ys[i]}–{orig_ye[i]}] → [{row['year_start']}–{row['year_end']}]"
                  f"  |  {str(row['role_text_raw'])[:60]}")


if __name__ == "__main__":
    main()
