"""
viz_ego_networks.py

For a set of elections, draw — in a single figure per election — the ego-network of
the designated winner next to the ego-network of the closest runner-up ("almost
president"), so the two can be compared side by side.

Reads the full network (data/networks/network_edges.csv, built by
06_build_networks.py + 07_bio_ties_gpt.py) and draws each candidate's
ego-network as of the destape year (e−1): only ties formed by then are shown.
Edges are coloured by tie type (co-education, co-work, family, mentorship, personal);
line width/opacity scale with the calibrated tie_weight (08_tie_weights.py).

Output: one PNG per election in OUTPUT_DIR, ego_network_<year>.png
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

CODE_DIR = Path(__file__).resolve().parents[1]
if str(CODE_DIR) not in sys.path:
    sys.path.append(str(CODE_DIR))

from config import OUTPUT_DIR
from network_utils import ego_view, load_corcholatas, load_network

# Tie type → colour
EDGE_COLORS = {
    "co_education":   "#1f77b4",   # blue
    "co_work":        "#2ca02c",   # green
    "co_military":    "#8c564b",   # brown
    "co_revolution":  "#17becf",   # cyan
    "family":         "#d62728",   # red
    "family_surname": "#d62728",   # red (same family family)
    "mentorship":     "#9467bd",   # purple
    "personal":       "#ff7f0e",   # orange
}
EDGE_LABELS = {
    "co_education":  "Co-education (same faculty, overlapping years)",
    "co_work":       "Co-work (same unit, overlapping years)",
    "co_military":   "Co-service (military unit, overlapping years)",
    "co_revolution": "Co-revolution (same state in the Revolution)",
    "family":        "Family / family (stated or surname)",
    "mentorship":    "Mentorship",
    "personal":      "Personal / friendship",
}


# Most-specific tie wins when a person is tied to the ego in several ways
_PRIORITY = {"family": 0, "family_surname": 0, "mentorship": 1, "personal": 2,
             "co_work": 3, "co_military": 4, "co_revolution": 5, "co_education": 6}


def hub_ties(edges: pd.DataFrame, ego_name: str, as_of: int) -> dict:
    """alter_id -> (alter_name, primary_edge_type, strongest tie_weight), ties by `as_of`."""
    ego_id = edges.loc[edges["name_a"] == ego_name, "person_a"]
    if ego_id.empty:
        ego_id = edges.loc[edges["name_b"] == ego_name, "person_b"]
    sub = ego_view(edges, set(ego_id), as_of=as_of)
    best: dict = {}
    for _, e in sub.iterrows():
        a, t, w = int(e["alter_id"]), e["edge_type"], float(e["tie_weight"])
        if a not in best or _PRIORITY[t] < _PRIORITY[best[a][1]]:
            best[a] = (e["alter_name"], t, max(w, best[a][2]) if a in best else w)
        else:
            best[a] = (*best[a][:2], max(w, best[a][2]))
    return best


def _stack(ids, x, height=11.0):
    """Vertical column of node positions at a given x."""
    n = len(ids)
    if n == 0:
        return {}
    ys = np.linspace(height / 2, -height / 2, n) if n > 1 else [0.0]
    return {a: (x, y) for a, y in zip(ids, ys)}


def draw_comparison(ax, edges, winner, loser, year, pop):
    """Two hubs (winner=star, runner-up=circle) with shared ties (squares) in the middle."""
    W, L = hub_ties(edges, winner, year - 1), hub_ties(edges, loser, year - 1)
    shared = set(W) & set(L)
    wonly = set(W) - shared
    lonly = set(L) - shared
    order = lambda ids, src: sorted(ids, key=lambda a: (_PRIORITY[src[a][1]], src[a][0]))
    wonly, lonly, shared = order(wonly, W), order(lonly, L), order(shared, W)

    posW, posL = (-3.0, 0.0), (3.0, 0.0)
    pos = {}
    pos.update(_stack(wonly, -6.5)); pos.update(_stack(lonly, 6.5))
    pos.update(_stack(shared, 0.0, height=11.0))

    def edge(a, hub, src):
        x, y = pos[a]
        w = src[a][2]                           # calibrated tie weight (0.25–1)
        ax.plot([hub[0], x], [hub[1], y], color=EDGE_COLORS[src[a][1]],
                lw=0.2 + 1.3 * w, alpha=0.1 + 0.6 * w, zorder=1)
    for a in wonly: edge(a, posW, W)
    for a in lonly: edge(a, posL, L)
    for a in shared: edge(a, posW, W); edge(a, posL, L)

    def nodes(ids, src, size, ring, marker="o"):
        if not ids: return
        ax.scatter([pos[a][0] for a in ids], [pos[a][1] for a in ids], s=size,
                   c=[EDGE_COLORS[src[a][1]] for a in ids], marker=marker,
                   edgecolors=ring, linewidths=0.8 if ring == "black" else 0.3, zorder=2)
    nodes(wonly, W, 45, "#555555")
    nodes(lonly, L, 45, "#555555")
    nodes(shared, W, 80, "black", marker="s")     # shared = square, highlighted

    # winner = star, runner-up = circle
    ax.scatter([posW[0]], [posW[1]], s=2900, marker="*", c="#ffd700",
               edgecolors="black", linewidths=1.4, zorder=4)
    ax.scatter([posL[0]], [posL[1]], s=1700, marker="o", c="#ffd700",
               edgecolors="black", linewidths=1.6, zorder=4)
    for hub, nm in ((posW, winner), (posL, loser)):
        ax.text(hub[0], hub[1] - 0.75, nm.split(",")[0], ha="center", va="top",
                fontsize=10, fontweight="bold", zorder=5)

    # labels: shared (if legible) + the most "popular" exclusive alters per side
    if len(shared) <= 30:
        for a in shared:
            x, y = pos[a]
            ax.text(x, y + 0.12, W[a][0].split(",")[0], fontsize=5.5,
                    ha="center", va="bottom", color="#222222", zorder=5)

    def label_top(ids, src, dx, ha, k=7):
        for a in sorted(ids, key=lambda a: -pop.get(a, 0))[:k]:
            if pop.get(a, 0) < 2:        # only label genuinely well-connected people
                continue
            x, y = pos[a]
            ax.text(x + dx, y, src[a][0].split(",")[0], fontsize=6.5,
                    ha=ha, va="center", color="#222222", zorder=5)
    label_top(wonly, W, -0.4, "right")
    label_top(lonly, L, 0.4, "left")

    ax.set_title(
        f"{year}: {winner.split(',')[0]} (winner) vs {loser.split(',')[0]} (runner-up)\n"
        f"{len(shared)} shared ties  |  {len(wonly)} only-winner  |  {len(lonly)} only-runner-up",
        fontsize=12)
    ax.set_xlim(-9, 9); ax.set_ylim(-6.5, 6.5); ax.axis("off")


def main():
    edges, _ = load_network()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # "popularity" = number of distinct tapados a person is tied to (used to pick
    # which exclusive alters are worth labelling)
    tapados = set(load_corcholatas()["person_id"])
    pop = ego_view(edges, tapados).groupby("alter_id")["ego_id"].nunique().to_dict()

    handles = [Line2D([0], [0], color=EDGE_COLORS[k], lw=2, label=v)
               for k, v in EDGE_LABELS.items()]
    handles += [
        Line2D([0], [0], marker="*", color="w", markerfacecolor="#ffd700",
               markeredgecolor="black", markersize=16, label="winner"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#ffd700",
               markeredgecolor="black", markersize=11, label="runner-up"),
        Line2D([0], [0], marker="s", color="w", markerfacecolor="#bbb",
               markeredgecolor="black", markersize=9, label="shared tie (both)"),
    ]

    # the chosen candidate (1994: Zedillo, who took office; 2000: nominee Labastida)
    # vs the documented runner-up, both from the crosswalk (05_match_corcholatas.py)
    corch = load_corcholatas()
    pairs = {y: (g.loc[g.role.isin(["winner", "nominee_lost"]), "person_name"].iloc[0],
                 g.loc[g.role == "runner_up", "person_name"].iloc[0])
             for y, g in corch.groupby("election_year")}
    for year, (winner, loser) in pairs.items():
        fig, ax = plt.subplots(figsize=(20, 11))
        draw_comparison(ax, edges, winner, loser, year, pop)
        ax.legend(handles=handles, loc="lower center", ncol=3, fontsize=8,
                  frameon=False, bbox_to_anchor=(0.5, -0.02))
        fig.suptitle(f"PRI presidential succession {year}: shared political network",
                     fontsize=14, fontweight="bold")
        fig.tight_layout()
        out = OUTPUT_DIR / f"ego_network_{year}.png"
        fig.savefig(out, dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"  saved {out}")


if __name__ == "__main__":
    main()
