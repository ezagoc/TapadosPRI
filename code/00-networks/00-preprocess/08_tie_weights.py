"""
08_tie_weights.py  —  network stage 3: data-calibrated tie weights

How informative is co-presence about acquaintance, as a function of how many people
were at the focus at the same time (`focus_size` = n)? We use the relationships
STATED in the biographies (family / mentorship / personal / family_surname, from
06–07) as a benchmark and estimate, for co-location ties of each type,

    logit P(stated tie | co-location) = a + b · log(n − 1)

with standard errors clustered by focus. The fitted decay is a smooth power law
(b ≈ −0.3: a tie in a group of 60 is still ~1/3 as informative as one in a pair)
— there is no natural size cutoff, so instead of cutting we weight:

    tie_weight     = (n − 1) ** b      (1 for a pair; stated ties = 1)
    weight_newman  = 1 / (n − 1)       (Newman 2001; robustness, stated ties = 1)

b is estimated per tie type (co_work, co_education); types with too few benchmark
events (co_military, co_revolution) use the pooled co-location slope.

Caveat: the benchmark is incomplete, and if Camp records relationships more often
within small prominent groups, b is biased; results should hold across the
robustness curve (unweighted, Newman, caps 10/20/30/60 — network_utils.ROBUSTNESS_CAPS).

Run AFTER 07. Inputs/outputs: networks/network_edges.csv (+ tie_weight,
weight_newman), networks/tie_weight_params.csv
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

CODE_DIR = Path(__file__).resolve().parents[2]
if str(CODE_DIR) not in sys.path:
    sys.path.append(str(CODE_DIR))

from config import NETWORK_DIR, NETWORK_EDGES_CSV

PARAMS_CSV = NETWORK_DIR / "tie_weight_params.csv"
STATED = ["family", "mentorship", "personal", "family_surname"]
MIN_EVENTS = 50     # below this many benchmark events a type uses the pooled slope


def fit_decay(d: pd.DataFrame) -> dict:
    """Logit of 'has a stated tie' on log(n − 1), SEs clustered by focus."""
    x = sm.add_constant(np.log(d["focus_size"].clip(lower=2) - 1).rename("log_n_minus_1"))
    m = sm.GLM(d["y"].astype(float), x, family=sm.families.Binomial()).fit(
        cov_type="cluster", cov_kwds={"groups": pd.factorize(d["focus"])[0]})
    return {"slope": m.params["log_n_minus_1"], "se": m.bse["log_n_minus_1"],
            "intercept": m.params["const"], "pairs": len(d), "events": int(d["y"].sum())}


def main():
    edges = pd.read_csv(NETWORK_EDGES_CSV)
    stated = set(map(tuple, edges.loc[edges.edge_type.isin(STATED),
                                      ["person_a", "person_b"]].values))
    co = edges[~edges.edge_type.isin(STATED)].dropna(subset=["focus_size"]).copy()
    co["y"] = [(a, b) in stated for a, b in zip(co.person_a, co.person_b)]

    params = {"pooled": fit_decay(co)}
    for t, d in co.groupby("edge_type"):
        if d["y"].sum() >= MIN_EVENTS:
            params[t] = fit_decay(d)
    ptab = pd.DataFrame(params).T.rename_axis("edge_type").reset_index()
    ptab.to_csv(PARAMS_CSV, index=False)
    print("Decay of P(stated tie) with log(n − 1), by tie type:")
    print(ptab.round(3).to_string(index=False))

    slope = {t: params.get(t, params["pooled"])["slope"] for t in edges.edge_type.unique()}
    n1 = edges["focus_size"].clip(lower=2) - 1
    is_co = edges["focus_size"].notna() & ~edges.edge_type.isin(STATED)
    edges["tie_weight"] = np.where(is_co, n1 ** edges["edge_type"].map(slope), 1.0).round(4)
    edges["weight_newman"] = np.where(is_co, 1 / n1, 1.0).round(4)
    edges.to_csv(NETWORK_EDGES_CSV, index=False)

    print("\ntie_weight at n = 2, 5, 20, 60 (co_work):",
          [round((n - 1) ** slope["co_work"], 2) for n in (2, 5, 20, 60)])
    print(f"→ {NETWORK_EDGES_CSV} (+ tie_weight, weight_newman)\n→ {PARAMS_CSV}")


if __name__ == "__main__":
    main()
