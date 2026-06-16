"""
export_candidate_networks.py

For each PRI/PRM election, export one Excel per candidate — the winner and the 3
runner-ups with the largest networks — listing every network connection (name, tie
type and all tie detail) together with the connected person's POSITION the year
before the election and each year of the sexenio after it.

Output: OUTPUT_DIR/candidate_networks/<year>/<year>_<role>_<surname>.xlsx
"""

from __future__ import annotations

import re
import shutil
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

CODE_DIR = Path(__file__).resolve().parents[1]
if str(CODE_DIR) not in sys.path:
    sys.path.append(str(CODE_DIR))

from config import DATA_DIR, OUTPUT_DIR, CORCHOLATAS_XLSX

CLEAN = DATA_DIR / "clean_positions"
EDGES = DATA_DIR / "networks" / "tapado_edges.csv"
OUT = OUTPUT_DIR / "candidate_networks"


def _toks(s):
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.category(c).startswith("M"))
    return {w for w in re.sub(r"[^a-z ]+", " ", s.lower()).split() if len(w) > 2}


def winner_by_election(people: pd.DataFrame) -> dict:
    """(election_year, person_id) -> 1 if that person is the ✓ winner of that election.

    Derived from the corcholatas ✓ per election row, not the per-person flag (which
    would mislabel a future winner who was a runner-up in an earlier election)."""
    tok2pid = defaultdict(set)
    pid_tok = {}
    for pid, name in zip(people.person_id, people.person_name):
        t = _toks(name); pid_tok[pid] = t
        for w in t:
            tok2pid[w].add(pid)

    def match(name):
        q = _toks(name)
        sc = Counter()
        for w in q:
            for pid in tok2pid.get(w, ()):
                sc[pid] += 1
        if not sc:
            return None
        pid, ov = max(sc.items(), key=lambda kv: (kv[1], -len(pid_tok[kv[0]])))
        return pid if (ov >= 2 and ov >= len(q) - 1) else None

    corch = pd.read_excel(CORCHOLATAS_XLSX, header=1).dropna(subset=["Nombre"])
    flag = {}
    for _, r in corch.iterrows():
        pid = match(str(r["Nombre"]).replace("✓", "").strip())
        if pid is not None:
            flag[(int(r["Elección"]), pid)] = int("✓" in str(r["Nombre"]))
    return flag

N_COMPETITORS = 3
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
    edges = pd.read_csv(EDGES)
    posidx = build_position_index()
    people = pd.read_csv(DATA_DIR / "parsed_positions.csv")[["person_id", "person_name"]] \
        .dropna().drop_duplicates("person_id")
    win_flag = winner_by_election(people)   # (election, person_id) -> ✓ winner of THAT election
    bp = pd.read_csv(DATA_DIR / "birthplace.csv")[["person_id", "state"]].dropna() \
        .drop_duplicates("person_id").set_index("person_id")["state"].to_dict()
    pp = pd.read_csv(DATA_DIR / "parsed_positions.csv")[["person_id", "birth_date_clean"]] \
        .dropna().drop_duplicates("person_id")
    byear = {r.person_id: str(r.birth_date_clean)[:4] for r in pp.itertuples(index=False)}

    if OUT.exists():                 # wipe stale files from previous runs
        shutil.rmtree(OUT)

    # ego -> election years; winner status is PER ELECTION (from the corcholatas ✓),
    # not the per-person flag, so a future president who was a runner-up earlier is
    # correctly listed as a competitor in that earlier election.
    egos = []
    for ego_id, grp in edges.groupby("ego_id"):
        name = grp["ego_name"].iloc[0]
        years = set()
        for s in grp["election_year"].astype(str):
            years.update(int(y) for y in s.split(";") if y.strip().isdigit())
        for y in years:
            winner = win_flag.get((y, ego_id), int(grp["is_winner"].iloc[0]))
            egos.append((y, winner, ego_id, name, grp["alter_id"].nunique()))
    egos = pd.DataFrame(egos, columns=["election", "winner", "ego_id", "ego_name", "n"])

    n_files = 0
    for year in sorted(egos["election"].unique()):
        sub = egos[egos.election == year]
        winners = sub[sub.winner == 1]
        comps = sub[sub.winner == 0].sort_values("n", ascending=False).head(N_COMPETITORS)
        outdir = OUT / str(year)
        outdir.mkdir(parents=True, exist_ok=True)
        year_cols = list(range(year - PRE_YEARS, year + POST_YEARS + 1))

        for role, cand in [("WINNER", r) for r in winners.itertuples()] + \
                          [("COMPETITOR", r) for r in comps.itertuples()]:
            ties = edges[edges.ego_id == cand.ego_id].copy()
            rows = []
            for t in ties.itertuples(index=False):
                a = t.alter_id
                row = {
                    "connection_name": t.alter_name,
                    "birth_year": byear.get(a, ""),
                    "birthplace_state": bp.get(a, ""),
                    "tie_type": t.edge_type,
                    "tie_detail (focus)": t.focus,
                    "focus_size": t.focus_size,
                    "their_role_at_focus": t.alter_role,
                    "candidate_role_at_focus": t.ego_role,
                    "tie_year_start": t.year_start,
                    "tie_year_end": t.year_end,
                    "confirmed_by": t.confirmed_by,
                }
                for y in year_cols:
                    phase = "pre" if y < year else ("election" if y == year else "post")
                    row[f"pos_{y} ({phase})"] = position_in_year(posidx, a, y)
                rows.append(row)
            df = pd.DataFrame(rows).sort_values(["tie_type", "connection_name"])
            surname = str(cand.ego_name).split(",")[0].strip().replace("/", "-")
            path = outdir / f"{year}_{role}_{surname}.xlsx"
            df.to_excel(path, index=False)
            n_files += 1
        print(f"  {year}: winner(s)={len(winners)} + {len(comps)} competitors")

    print(f"\nWrote {n_files} Excel files under {OUT}")


if __name__ == "__main__":
    main()
