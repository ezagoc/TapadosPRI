"""
export_candidate_networks.py

For each PRI/PRM election, export one Excel per pre-candidate — the winner(s), the
documented runner-up and every other losing corcholata (the control group) —
listing every network connection (name, tie
type and all tie detail) together with the connected person's POSITION in each year
of the e−6..e+6 window. Only ties formed by the destape year (e−1) are listed, so
the network is pre-determined with respect to the succession. Every tie carries its
calibrated `tie_weight` (08_tie_weights.py) — no size cutoff. Each file
is named by the candidate's `role` in the crosswalk (winner, runner_up, loser,
designated_removed = 1994 Colosio, nominee_lost = 2000 Labastida).

Output: OUTPUT_DIR/candidate_networks/<year>/<year>_<role>_<surname>.xlsx
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pandas as pd

CODE_DIR = Path(__file__).resolve().parents[1]
if str(CODE_DIR) not in sys.path:
    sys.path.append(str(CODE_DIR))

from config import DATA_DIR, OUTPUT_DIR
from network_utils import ego_view, load_corcholatas, load_network

CLEAN = DATA_DIR / "clean_positions"
OUT = OUTPUT_DIR / "candidate_networks"


# Symmetric event-study window for DiD: the full previous sexenio (e-6..e-1),
# the election/transition year (e), and the candidate's sexenio (e+1..e+6).
PRE_YEARS, POST_YEARS = 6, 6

RANK_LVL = {  # to pick the most senior position a person holds in a given year
    "secretary": 6, "attorney_general": 6, "assistant_secretary": 5, "oficial_mayor": 5,
    "director_general": 4, "ambassador": 4, "justice": 4, "coordinator_general": 4,
    "assistant_attorney_general": 4, "director": 3, "head": 3, "secretary_general": 3,
    "inspector_general": 3, "comptroller": 3, "general_manager": 3, "administrator": 3,
    "coordinator": 2, "judge": 2, "magistrate": 2, "delegate": 2, "treasurer": 2,
}
PUB_LVL = {"Governor": 6, "Senator": 4, "Federal Deputy": 3, "Deputy": 3, "President": 3,
           "Mayor": 3, "Local Deputy": 2, "Representative": 2, "Delegate": 2,
           "Secretary": 3, "Member": 1}


def _title(rank) -> str:
    return str(rank).replace("_", " ").title() if isinstance(rank, str) else "Official"


def build_position_index():
    """person_id -> list of (year_start, year_end, seniority, label)."""
    idx: dict = {}
    g = pd.read_csv(CLEAN / "govt_positions.csv").dropna(subset=["year_start"])
    for r in g.itertuples(index=False):
        inst = r.secretariat_norm if isinstance(r.secretariat_norm, str) else r.organization
        if isinstance(inst, str):
            label = f"{_title(r.rank)}, {inst}"
        elif isinstance(r.role_text, str) and r.role_text.strip():
            # institution wasn't structured out — fall back to the raw description,
            # which still names the body (e.g. "director general, Guanos and
            # Fertilizers of Mexico"). Covers ~15% of dated govt records.
            label = r.role_text.strip()[0].upper() + r.role_text.strip()[1:]
        else:
            label = _title(r.rank)
        idx.setdefault(r.person_id, []).append(
            (int(r.year_start), int(r.year_end) if pd.notna(r.year_end) else int(r.year_start),
             RANK_LVL.get(r.rank, 1), label))
    p = pd.read_csv(CLEAN / "public_positions.csv").dropna(subset=["year_start"])
    for r in p.itertuples(index=False):
        title = str(r.position_title) if pd.notna(r.position_title) else "Elected office"
        loc = f" ({r.state})" if isinstance(r.state, str) and r.state else ""
        idx.setdefault(r.person_id, []).append(
            (int(r.year_start), int(r.year_end) if pd.notna(r.year_end) else int(r.year_start),
             PUB_LVL.get(title, 2), f"{title}{loc}"))
    return idx


def position_in_year(idx, pid, year):
    """Most senior position label held in `year`, or '' if none recorded."""
    best = (-1, "")
    for ys, ye, sen, label in idx.get(pid, ()):
        if ys <= year <= ye and sen > best[0]:
            best = (sen, label)
    return best[1]


def main():
    edges, nodes = load_network()
    posidx = build_position_index()
    corch = load_corcholatas()          # per-election winner flag (corcholatas ✓)
    bp = nodes.set_index("person_id")["birth_state"].to_dict()
    byear = nodes.set_index("person_id")["birth_year"].to_dict()

    if OUT.exists():                 # wipe stale files from previous runs
        shutil.rmtree(OUT)

    # one ego-network per (election, candidate), with ties formed by the destape (e−1)
    nets = {(r.election_year, r.person_id): ego_view(edges, [r.person_id],
                                                     as_of=r.election_year - 1)
            for r in corch.itertuples()}
    egos = pd.DataFrame([{"election": r.election_year, "role": r.role,
                          "ego_id": r.person_id, "ego_name": r.person_name,
                          "n": nets[(r.election_year, r.person_id)]["alter_id"].nunique()}
                         for r in corch.itertuples()])

    n_files = 0
    for year in sorted(egos["election"].unique()):
        sub = egos[egos.election == year]
        order = {"winner": 0, "nominee_lost": 0, "designated_removed": 1,
                 "runner_up": 2, "loser": 3}
        sub = sub.sort_values(["role", "n"], key=lambda c: c.map(order) if c.name == "role"
                              else -c)
        outdir = OUT / str(year)
        outdir.mkdir(parents=True, exist_ok=True)
        year_cols = list(range(year - PRE_YEARS, year + POST_YEARS + 1))

        for cand in sub.itertuples():
            role = cand.role.upper().replace("_", "-")   # WINNER, RUNNER-UP, LOSER, …
            ties = nets[(year, cand.ego_id)]
            rows = []
            for t in ties.itertuples(index=False):
                a = t.alter_id
                row = {
                    "connection_name": t.alter_name,
                    "birth_year": byear.get(a),
                    "birthplace_state": bp.get(a, ""),
                    "tie_type": t.edge_type,
                    "tie_detail (focus)": t.focus,
                    "focus_size (people at once)": t.focus_size,
                    "tie_weight": t.tie_weight,
                    "weight_newman": t.weight_newman,
                    "their_role_at_focus": t.alter_role,
                    "candidate_role_at_focus": t.ego_role,
                    "tie_year_start": t.year_start,
                    "tie_date_basis": t.date_basis,
                    "tie_year_end": t.year_end,
                    "confirmed_by": t.confirmed_by,
                }
                for y in year_cols:
                    phase = "pre" if y < year else ("election" if y == year else "post")
                    row[f"pos_{y} ({phase})"] = position_in_year(posidx, a, y)
                rows.append(row)
            if not rows:
                print(f"    ! {cand.ego_name}: no ties formed by {year - 1}; skipped")
                continue
            df = pd.DataFrame(rows).sort_values(["tie_type", "connection_name"])
            surname = str(cand.ego_name).split(",")[0].strip().replace("/", "-")
            path = outdir / f"{year}_{role}_{surname}.xlsx"
            df.to_excel(path, index=False)
            n_files += 1
        print(f"  {year}: " + ", ".join(f"{k}={v}" for k, v in sub.role.value_counts().items()))

    print(f"\nWrote {n_files} Excel files under {OUT}")


if __name__ == "__main__":
    main()
