"""
validate_network.py

Construct validity of the co-location ties (co_work, co_education, co_military,
co_revolution): if co-presence measures acquaintance, pairs that coincided in a
SMALL focus should more often also have a relationship STATED in a biography
(family / mentorship / personal, from 06 + 07). For each tie type × size bin
(people at the focus the year the tie began) we report the share of pairs with a
stated tie and its lift over a random pair of politicians.

This benchmark is incomplete (biographies mention few relationships), so levels
are low; the gradient across sizes is what matters. The parametric version of this
gradient (logit on log(n − 1)) calibrates the tie weights in 00-preprocess/08_tie_weights.py.

Output: OUTPUT_DIR/network_validation.csv (+ printed table)
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

CODE_DIR = Path(__file__).resolve().parents[1]
if str(CODE_DIR) not in sys.path:
    sys.path.append(str(CODE_DIR))

from config import OUTPUT_DIR
from network_utils import load_network

STATED = ["family", "mentorship", "personal", "family_surname"]
BINS = [0, 3, 5, 10, 15, 20, 30, 45, 60, 10_000]


def main():
    edges, nodes = load_network()
    stated = set(map(tuple, edges.loc[edges.edge_type.isin(STATED),
                                      ["person_a", "person_b"]].values))
    n = len(nodes)
    base = len(stated) / (n * (n - 1) / 2)

    co = edges[~edges.edge_type.isin(STATED)].copy()
    co["kind"] = co["edge_type"]
    edu = co.edge_type == "co_education"
    co.loc[edu, "kind"] = np.where(co.loc[edu, "focus"].str.contains("/generation"),
                                   "co_education: generation (large school)",
                                   np.where(co.loc[edu, "focus"].str.contains("/staff"),
                                            "co_education: teaching staff",
                                            "co_education: small school"))
    co["has_stated_tie"] = [(a, b) in stated for a, b in zip(co.person_a, co.person_b)]
    co["size_bin"] = pd.cut(co["focus_size"], BINS)

    t = (co.groupby(["kind", "size_bin"], observed=True)["has_stated_tie"]
           .agg(pairs="size", stated="sum", rate="mean").reset_index())
    t["per_1000"] = (t["rate"] * 1000).round(2)
    t["lift_vs_random"] = (t["rate"] / base).round(1)
    t = t.drop(columns="rate")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / "network_validation.csv"
    t.to_csv(out, index=False)
    print(f"Random pair of politicians: {base * 1000:.2f} stated ties per 1,000 pairs\n")
    print(t.to_string(index=False))
    print(f"\n→ {out}")


if __name__ == "__main__":
    main()
