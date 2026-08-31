"""
Generate the editable rank lookup tables for manual curation.

For each domain (govt, party, labor) this emits two CSVs into data/rank/:

  <domain>_institution_rank.csv   — one row per distinct institution
  <domain>_title_rank.csv         — one row per distinct job title

Each table has:
  - the raw value + n_records + helpful context columns (so you can judge)
  - a `suggested_*_tier` column (a heuristic first guess, READ-ONLY reference)
  - a BLANK fill column you complete by hand (`domain_tier`, `global_tier`,
    or `title_tier`)
  - a blank `notes` column

Tier conventions (HIGHER = MORE SENIOR), so a promotion is a score increase:
  domain_tier   1..N   rank of the institution *within its own domain*
  global_tier   1..10  common cross-domain ladder:
      10  Presidency / national party presidency
       9  core cabinet (Hacienda, Gobernacion, Presidencia, Prog.& Budget,
           Foreign Relations) + Supreme Court
       8  other federal secretariats; Bank of Mexico, PEMEX, IMSS, ISSSTE
       7  federal sub-agencies, CEN bodies, national unions (CTM, CNC)
       6  national party, DDF
       5  governorship / Ministerio Publico
       4  state secretariats & courts, state party committees
       3  local / district party, minor state bodies
       1-2 municipal / marginal
  title_tier    1..N   seniority of the title *within a domain* (institution-
                       independent: secretary > director general > director > ...)

Downstream (02-rank/02_*.py, to be written) joins your completed tiers onto each
position record and builds the person x year rank panel. Editing the suggested
values is optional — the BLANK fill columns are what the downstream script reads.

Input:  data/clean_positions/{govt,party,labor}_positions.csv
Output: data/rank/<domain>_{institution,title}_rank.csv
"""

from pathlib import Path
import sys

import pandas as pd

CODE_DIR = Path(__file__).resolve().parents[1]
if str(CODE_DIR) not in sys.path:
    sys.path.append(str(CODE_DIR))

from config import (
    CLEAN_GOVT_POSITIONS_CSV,
    CLEAN_PARTY_POSITIONS_CSV,
    CLEAN_LABOR_POSITIONS_CSV,
    RANK_DIR,
)

# ---------------------------------------------------------------------------
# Existing title vocabularies (copied from the 05_* scripts) — used only to
# pre-seed a suggested title tier. Higher suggested tier = more senior.
# ---------------------------------------------------------------------------

_GOVT_RANK_ORDER = {  # lower = more senior (as in 05_govt_positions.py)
    "secretary": 1, "attorney_general": 2, "governor": 3, "acting_governor": 4,
    "ambassador": 5, "consul_general": 6, "justice": 7, "magistrate": 8,
    "circuit_judge": 9, "district_judge": 10, "judge": 11, "subsecretary": 12,
    "assistant_attorney_general": 13, "assistant_secretary": 14,
    "director_general": 13, "oficial_mayor": 14, "secretary_general": 15,
    "general_manager": 16, "coordinator_general": 17, "inspector_general": 18,
    "assistant_director_general": 19, "director": 20, "assistant_director": 21,
    "coordinator": 22, "head": 23, "manager": 24, "assistant_manager": 25,
    "inspector": 26, "delegate": 27, "administrator": 28, "treasurer": 29,
    "comptroller": 30, "technical_secretary": 31, "adviser": 32, "assistant": 33,
    "analyst": 34, "member": 35, "consul": 36, "other": 99,
}

_PARTY_RANK_ORDER = {
    "national_president": 1, "secretary_general_nat": 2, "cen_president": 3,
    "cen_secretary": 4, "iepes_director": 5, "national_delegate": 6,
    "state_president": 7, "state_secretary_general": 8, "campaign_leader": 9,
    "state_secretary": 10, "cen_member": 11, "adviser_member": 12,
    "campaign_participant": 13, "joined": 14, "other": 99,
}

_LABOR_RANK_ORDER = {  # order of _RANK_PATTERNS in 05_labor_positions.py
    "secretary_general": 0, "president": 1, "director_general": 2,
    "secretary": 3, "director": 4, "delegate": 5, "coordinator": 6,
    "treasurer": 7, "adviser": 8, "representative": 9, "member": 10, "other": 11,
}


def _invert_to_suggested(order_map: dict) -> dict:
    """lower-is-senior order -> higher-is-senior suggested tier (1..N), excl. 'other'."""
    ranked = sorted((k for k in order_map if k != "other"), key=lambda k: order_map[k])
    n = len(ranked)
    out = {k: n - i for i, k in enumerate(ranked)}  # most senior gets n
    out["other"] = 1
    return out


# ---------------------------------------------------------------------------
# Institution -> suggested global tier heuristics (per domain)
# ---------------------------------------------------------------------------

def _govt_global_tier(inst: str, federal_majority) -> int:
    s = (inst or "").lower()
    if "presidency" in s or "office of the president" in s:
        return 9
    if any(k in s for k in ("treasury", "hacienda", "government", "gobernacion",
                            "programming and budget", "foreign relations")):
        return 9
    if "supreme court" in s:
        return 9
    if any(k in s for k in ("bank of mexico", "pemex", "petroleos", "imss",
                            "issste", "nacional financiera", "nafinsa", "cfe",
                            "federal electric", "conasupo", "banobras", "banrural")):
        return 8
    if "secretariat of" in s:
        return 8
    if "department of the federal district" in s:
        return 6
    if "ministerio publico" in s:
        return 5
    if "tribunal" in s or "court" in s:
        return 4
    if federal_majority is True:
        return 7
    if federal_majority is False:
        return 4
    return 3


def _party_global_tier(inst: str, level: str) -> int:
    s = (inst or "").lower()
    if "cen of pri" in s:
        return 8
    if "iepes" in s:
        return 7
    if "cen of pan" in s or "cen of prd" in s or s == "cen":
        return 7
    if s in ("pri", "pan", "prd", "pnr", "prm"):
        return 6
    if level == "national":
        return 6
    if level == "state":
        return 4
    if level == "local":
        return 3
    return 3


_LABOR_NATIONAL = {"CTM", "CNC", "CNOP", "FSTSE", "SNTE", "CROC", "CROM",
                   "STPRM", "STFRM", "SUTERM", "COPARMEX"}


def _labor_global_tier(inst: str, national_majority) -> int:
    if (inst or "").upper() in _LABOR_NATIONAL:
        return 7
    if national_majority is True:
        return 6
    return 3


# ---------------------------------------------------------------------------
# Per-domain spec
# ---------------------------------------------------------------------------

DOMAINS = {
    "govt": {
        "path": CLEAN_GOVT_POSITIONS_CSV,
        "inst_col": "secretariat_norm",
        "title_col": "rank",
        "hint_col": "is_federal",          # bool-ish
        "order_map": _GOVT_RANK_ORDER,
        "global_fn": _govt_global_tier,
    },
    "party": {
        "path": CLEAN_PARTY_POSITIONS_CSV,
        "inst_col": "organization",
        "title_col": "party_rank",
        "hint_col": "party_level",         # national/state/local
        "order_map": _PARTY_RANK_ORDER,
        "global_fn": _party_global_tier,
    },
    "labor": {
        "path": CLEAN_LABOR_POSITIONS_CSV,
        "inst_col": "org_clean",
        "title_col": "rank",
        "hint_col": "is_national",         # bool-ish
        "order_map": _LABOR_RANK_ORDER,
        "global_fn": _labor_global_tier,
    },
}


def _majority_hint(series: pd.Series):
    """Most common non-null hint value for an institution (bool or str)."""
    vals = series.dropna()
    if vals.empty:
        return None
    mode = vals.mode()
    return mode.iloc[0] if len(mode) else None


def _top_values(series: pd.Series, n: int = 3) -> str:
    counts = series.dropna().astype(str)
    counts = counts[counts != "nan"].value_counts()
    return " | ".join(counts.index[:n])


def build_institution_table(df: pd.DataFrame, spec: dict, domain: str) -> pd.DataFrame:
    inst_col, title_col, hint_col = spec["inst_col"], spec["title_col"], spec["hint_col"]
    work = df[df[inst_col].notna() & (df[inst_col].astype(str) != "nan")].copy()
    work[inst_col] = work[inst_col].astype(str).str.strip()

    rows = []
    for inst, sub in work.groupby(inst_col, sort=False):
        hint = _majority_hint(sub[hint_col]) if hint_col in sub else None
        rows.append({
            "domain": domain,
            "institution": inst,
            "n_records": len(sub),
            "hint": hint,
            "example_titles": _top_values(sub[title_col]),
            "suggested_global_tier": spec["global_fn"](inst, hint),
        })

    out = pd.DataFrame(rows).sort_values("n_records", ascending=False).reset_index(drop=True)
    # domain_tier suggestion = dense rank of the suggested global tier within the domain
    out["suggested_domain_tier"] = out["suggested_global_tier"].rank(method="dense").astype(int)
    # Blank columns for manual curation
    out["domain_tier"] = ""
    out["global_tier"] = ""
    out["notes"] = ""
    return out[[
        "domain", "institution", "n_records", "hint", "example_titles",
        "suggested_domain_tier", "suggested_global_tier",
        "domain_tier", "global_tier", "notes",
    ]]


def build_title_table(df: pd.DataFrame, spec: dict, domain: str) -> pd.DataFrame:
    inst_col, title_col = spec["inst_col"], spec["title_col"]
    suggested = _invert_to_suggested(spec["order_map"])
    work = df[df[title_col].notna() & (df[title_col].astype(str) != "nan")].copy()
    work[title_col] = work[title_col].astype(str).str.strip()

    rows = []
    for title, sub in work.groupby(title_col, sort=False):
        rows.append({
            "domain": domain,
            "title": title,
            "n_records": len(sub),
            "example_institutions": _top_values(sub[inst_col]),
            "suggested_title_tier": suggested.get(title, 1),
        })

    out = pd.DataFrame(rows).sort_values("n_records", ascending=False).reset_index(drop=True)
    out["title_tier"] = ""
    out["notes"] = ""
    return out[[
        "domain", "title", "n_records", "example_institutions",
        "suggested_title_tier", "title_tier", "notes",
    ]]


def main() -> None:
    RANK_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Writing rank lookup tables to: {RANK_DIR}\n")

    for domain, spec in DOMAINS.items():
        if not spec["path"].exists():
            print(f"  [skip] {domain}: missing {spec['path']}")
            continue
        df = pd.read_csv(spec["path"])

        inst_tbl = build_institution_table(df, spec, domain)
        inst_path = RANK_DIR / f"{domain}_institution_rank.csv"
        inst_tbl.to_csv(inst_path, index=False)

        title_tbl = build_title_table(df, spec, domain)
        title_path = RANK_DIR / f"{domain}_title_rank.csv"
        title_tbl.to_csv(title_path, index=False)

        print(f"  {domain:6s}  {len(inst_tbl):4d} institutions -> {inst_path.name}")
        print(f"          {len(title_tbl):4d} titles       -> {title_path.name}")

    print("\nNext: fill the blank `domain_tier` / `global_tier` / `title_tier` "
          "columns by hand, then run 02-rank/02_build_rank_panel.py (to be written).")


if __name__ == "__main__":
    main()
