"""Slide figure: the 1946 succession told on the real network, one picture per stage (click-through overlays).

Stages, drawn on ONE fixed layout so nodes do not move between clicks:
  1. political class   every politician eligible in the main design for 1946 (a ranked post in 1941-44, aged
                       25-75 in 1946, not a contender of 1946 or earlier) plus the six contenders of the audited
                       slate, and every position-based tie among them formed by 1944 (e-2, as in estimate_main.R).
                       All grey.
  2. contenders        the six contenders become black diamonds, labelled.
  3. designation       Aleman's diamond turns red; the politicians tied only to him become red circles with red
                       ties; those tied only to a losing contender become black circles with black ties to their
                       patron; politicians tied to several contenders stay grey.
  4. election          Aleman becomes a red star (election of 7 July 1946, inauguration 1 December 1946) and each
                       follower is redrawn by his career after the succession: an up-triangle, slightly larger, if
                       his highest post in 1947-50 was above his highest post in 1941-44, a down-triangle if below,
                       the circle if equal. Colours keep the camp.

Eligibility, annual ranks and the follower definition copy code/04-analysis/main_direct_tie/estimate_main.R
(tie types co_work / co_education / co_military / co_revolution, ties dated by e-2, rung = floor(hybrid_rank),
spells of at most 12 years). The counts are written as LaTeX macros for the slide captions.

Run it with the staging environment that produced the deck's numbers (research/eligibility_refresh_2026_10_27:
title-corrected ranks and verified deaths excluded), i.e. TAPADOSPRI_DB_ROOT and TAPADOSPRI_DATA_DIR pointing there.
Outputs: OUTPUT_DIR/slides/succession_1946_stage{1..4}.{pdf,png} (identical frame and layout, so the slide can switch them with \\only), OUTPUT_DIR/slides/succession_1946_macros.tex
Run:     python code/03-descriptive_stats/viz_succession_1946_network.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import networkx as nx
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code"))
from config import DATA_DIR, OUTPUT_DIR  # noqa: E402

E, TIE_LAG = 1946, 2
T0 = E - TIE_LAG
TIE_TYPES = ["co_work", "co_education", "co_military", "co_revolution"]
ACC, INK, Z3, Z4, Z5, Z6 = "#940034", "#111111", "#d4d4d8", "#a1a1aa", "#71717a", "#52525b"
OUT = OUTPUT_DIR / "slides"
OUT.mkdir(parents=True, exist_ok=True)
DISPLAY = {101: "Alemán", 2318: "Rojo Gómez", 2024: "Padilla", 1298: "Henríquez Guzmán",
           268: "Baz", 524: "Castillo Nájera"}

# ----------------------------------------------------------------------------------------------- data
nodes = pd.read_csv(DATA_DIR / "networks" / "network_nodes.csv")
edges = pd.read_csv(DATA_DIR / "networks" / "network_edges.csv", low_memory=False)
cont = pd.read_csv(DATA_DIR / "candidates" / "corcholatas_matched.csv")
pos_recs = pd.read_csv(DATA_DIR / "rank" / "position_tiers.csv", low_memory=False)

slate = cont[(cont.election_year == E) & (cont.in_main_slate == 1)]
winner = int(slate.loc[slate.role == "winner", "person_id"].iloc[0])
contenders = [int(p) for p in slate.person_id]
assert len(contenders) == 6 and winner in contenders

# annual highest rung of a dated ranked post (estimate_main.R)
p = pos_recs[pos_recs.hybrid_rank.notna() & pos_recs.year_start.notna()].copy()
p["y0"] = p.year_start.astype(int)
p["y1"] = np.maximum(p.year_end.fillna(p.year_start).astype(int), p.y0)
p["rung"] = np.floor(p.hybrid_rank + 1e-9).astype(int)
p = p[(p.y1 - p.y0 <= 12) & (p.rung >= 1) & (p.rung <= 11)]
annual = (pd.DataFrame({"pid": np.repeat(p.person_id.values, (p.y1 - p.y0 + 1).values),
                        "year": np.concatenate([np.arange(a, b + 1) for a, b in zip(p.y0, p.y1)]),
                        "rank": np.repeat(p.rung.values, (p.y1 - p.y0 + 1).values)})
          .groupby(["pid", "year"], as_index=False)["rank"].max())


def highest_rank(ids, from_year, through):
    tab = annual[(annual.year >= from_year) & (annual.year <= through)].groupby("pid")["rank"].max()
    return np.array([int(tab.get(i, 0)) for i in ids])


ids = set(annual[(annual.year >= E - 5) & (annual.year <= T0)].pid)
ids -= set(cont[cont.election_year <= E].person_id.dropna().astype(int))
birth = nodes.set_index("person_id").birth_year
age = pd.Series({i: E - birth.get(i, np.nan) for i in ids})
eligible = sorted(int(i) for i in age[(age >= 25) & (age <= 75)].index)
# the deck's eligibility refresh (research/eligibility_refresh_2026_10_27) drops politicians whose verified death
# precedes the designation year; apply the same rule when its file is in DATA_DIR
death_file = DATA_DIR / "verified_death_years.csv"
if death_file.exists():
    dy = pd.read_csv(death_file).set_index("person_id").death_year
    eligible = [i for i in eligible if not (i in dy.index and dy[i] < E - 1)]
print(f"eligible politicians for {E}: {len(eligible)} (the deck's sample table says 519)")

dated = edges[edges.year_start.notna() & edges.edge_type.isin(TIE_TYPES) & (edges.year_start <= T0)]
everyone = set(eligible) | set(contenders)
bg = dated[dated.person_a.isin(everyone) & dated.person_b.isin(everyone)][["person_a", "person_b"]].drop_duplicates()
G = nx.Graph()
G.add_nodes_from(everyone)
G.add_edges_from(bg.itertuples(index=False, name=None))

# direct ties to contenders, as in the design: patron = the single contender a politician is tied to
ct = dated[dated.person_a.isin(contenders) | dated.person_b.isin(contenders)]
long = pd.concat([ct[ct.person_a.isin(contenders)].rename(columns={"person_a": "candidate", "person_b": "pid"}),
                  ct[ct.person_b.isin(contenders)].rename(columns={"person_b": "candidate", "person_a": "pid"})])
long = long[long.pid.isin(eligible)][["pid", "candidate"]].drop_duplicates()
n_direct = long.groupby("pid").candidate.nunique()
patron = long[long.pid.map(n_direct) == 1].set_index("pid").candidate.to_dict()
shared = sorted(n_direct[n_direct >= 2].index)
win_followers = sorted(i for i, c in patron.items() if c == winner)
lose_followers = sorted(i for i, c in patron.items() if c != winner)
print(f"winner's exclusive followers {len(win_followers)}, losers' {len(lose_followers)}, tied to several {len(shared)}")

ids_sorted = sorted(everyone)
pre_rank = dict(zip(ids_sorted, highest_rank(ids_sorted, E - 5, T0)))
post_rank = dict(zip(ids_sorted, highest_rank(ids_sorted, E + 1, E + 4)))
trend = {i: int(np.sign(post_rank[i] - pre_rank[i])) for i in ids_sorted}      # +1 rose, 0 same, -1 fell
MARK = {1: ("^", 54), 0: ("o", 20), -1: ("v", 12)}                           # post-succession marker by trend

# ----------------------------------------------------------------------------------------------- layout
rng = np.random.default_rng(1946)
centres = {winner: np.array([0.9, 0.1]),
           2318: np.array([-4.6, 1.9]),    # Rojo Gomez
           2024: np.array([4.9, 1.9]),     # Padilla
           1298: np.array([-4.9, -1.7]),   # Henriquez Guzman
           268: np.array([4.6, -1.9]),     # Baz
           524: np.array([-1.6, -2.4])}    # Castillo Najera


def disk(centre, n, r_in, r_out):
    k = np.arange(n)
    phi = k * 2.399963 + rng.uniform(-0.15, 0.15, n)
    rad = r_in + (r_out - r_in) * np.sqrt((k + 0.5) / max(n, 1))
    return np.c_[centre[0] + rad * np.cos(phi), centre[1] + rad * np.sin(phi)]


fixed = dict(centres)
for c in contenders:
    alters = [i for i, pc in patron.items() if pc == c]
    pts = disk(centres[c], len(alters), 0.45, 0.45 + 0.2 * np.sqrt(len(alters)))
    fixed.update(dict(zip(alters, pts)))
giant = max(nx.connected_components(G), key=len)
init = {n: fixed.get(n, rng.uniform([-6.3, -3.1], [6.3, 3.1])) for n in giant}
pos = nx.spring_layout(G.subgraph(giant), pos=init, fixed=[n for n in fixed if n in giant], k=0.45, iterations=180, seed=11)
rest = [n for n in G.nodes if n not in giant]
ang = rng.uniform(0, 2 * np.pi, len(rest))
rad = rng.uniform(0.98, 1.08, len(rest))
for n, a, r in zip(rest, ang, rad):
    pos[n] = np.array([6.6 * r * np.cos(a), 3.0 * r * np.sin(a)])
for n in pos:
    pos[n] = np.array([np.clip(pos[n][0], -7.0, 7.0), np.clip(pos[n][1], -3.2, 3.3)])
for n in fixed:                       # contenders and their exclusive followers keep their star geometry
    pos[n] = fixed[n]

# ----------------------------------------------------------------------------------------------- drawing
segs_all = [(pos[a], pos[b]) for a, b in G.edges]
fol_edges = {c: [(pos[c], pos[i]) for i, pc in patron.items() if pc == c] for c in contenders}
plain = [n for n in G.nodes if n not in contenders and n not in patron]


def legend_handles(stage):
    """Handles and the number of legend columns for each stage (matplotlib fills legends column by column)."""
    grey = Line2D([], [], color=Z3, lw=1.0, marker="o", markerfacecolor=Z4, markeredgewidth=0, markersize=2.6,
                  label="politicians and their ties")
    if stage == 1:
        return [grey], 1
    if stage == 2:
        return [grey, Line2D([], [], marker="D", color="w", markerfacecolor=INK, markersize=5.5, label="contenders")], 2
    if stage == 3:                                   # row 1: the diamonds, row 2: their followers
        return [Line2D([], [], marker="D", color="w", markerfacecolor=INK, markersize=5.5, label="losing contender"),
                Line2D([], [], marker="o", color="w", markerfacecolor=INK, markersize=5, label="tied only to a loser"),
                Line2D([], [], marker="D", color="w", markerfacecolor=ACC, markersize=5.5, label="designee"),
                Line2D([], [], marker="o", color="w", markerfacecolor=ACC, markersize=5, label="tied only to the designee")], 2
    return [Line2D([], [], marker="*", color="w", markerfacecolor=ACC, markersize=9, label="new president"),
            Line2D([], [], marker="^", color="w", markerfacecolor=Z6, markersize=7.8, label=f"rose in rank after {E}"),
            Line2D([], [], marker="v", color="w", markerfacecolor=Z6, markersize=4.0, label="fell in rank"),
            Line2D([], [], marker="o", color="w", markerfacecolor=Z6, markersize=5, label="same rank")], 4


def draw(stage):
    fig = plt.figure(figsize=(5.3, 2.45), dpi=300)      # drawn at the size it takes on the slide
    fig.patch.set_facecolor("white")
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(-7.4, 7.4)
    ax.set_ylim(-4.6, 3.5)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.add_collection(LineCollection(segs_all, colors=Z3, linewidths=0.2, alpha=0.25, zorder=0))

    def size(i, base):
        return base

    pts = np.array([pos[n] for n in plain])
    ax.scatter(pts[:, 0], pts[:, 1], s=[size(n, 2.6) for n in plain], color=Z4, alpha=0.65, linewidths=0, zorder=1)
    # followers
    for c in contenders:
        alters = [i for i, pc in patron.items() if pc == c]
        if not alters:
            continue
        a = np.array([pos[i] for i in alters])
        if stage < 3:
            ax.scatter(a[:, 0], a[:, 1], s=[size(i, 2.6) for i in alters], color=Z4, alpha=0.65, linewidths=0, zorder=1)
        else:
            win = c == winner
            ax.add_collection(LineCollection(fol_edges[c], colors=ACC if win else INK, linewidths=0.7 if win else 0.5,
                                             alpha=0.95 if win else 0.8, zorder=3 if win else 2))
            col = ACC if win else INK
            if stage == 3:
                ax.scatter(a[:, 0], a[:, 1], s=20, marker="o", color=col, zorder=5 if win else 4, linewidths=0)
            else:
                for t, (mk, area) in MARK.items():
                    grp = np.array([pos[i] for i in alters if trend[i] == t])
                    if len(grp):
                        ax.scatter(grp[:, 0], grp[:, 1], s=area, marker=mk, color=col, zorder=5 if win else 4, linewidths=0)
    # contenders
    for c in contenders:
        win = c == winner
        if stage == 1:
            ax.scatter(*pos[c], s=2.6, color=Z4, alpha=0.65, linewidths=0, zorder=1)
            continue
        mk = "*" if (win and stage >= 4) else "D"
        col = ACC if (win and stage >= 3) else INK
        ax.scatter(*pos[c], s=240 if mk == "*" else 85, marker=mk, color=col, zorder=7, edgecolors="white", linewidths=0.6)
        n_f = sum(1 for pc in patron.values() if pc == c)
        dy = -(0.45 + 0.2 * np.sqrt(n_f) + 0.22)
        ax.text(pos[c][0], pos[c][1] + dy, DISPLAY[c], ha="center", va="top", fontsize=8 if win else 7,
                color=col, weight="bold" if win else "normal", zorder=8,
                bbox=dict(boxstyle="round,pad=0.12", facecolor="white", edgecolor="none", alpha=0.8))
    handles, ncol = legend_handles(stage)
    ax.legend(handles=handles, loc="lower center", ncol=ncol, frameon=False, fontsize=6,
              handlelength=1.3, columnspacing=1.6, handletextpad=0.4, bbox_to_anchor=(0.5, 0.0))
    for ext in ("pdf", "png"):                       # fixed frame: every stage has the same size and placement
        fig.savefig(OUT / f"succession_{E}_stage{stage}.{ext}", dpi=300, facecolor="white")
    plt.close(fig)


for st in range(1, 5):
    draw(st)

macros = {"SuccEligible": len(eligible), "SuccNodes": G.number_of_nodes(), "SuccTies": G.number_of_edges(),
          "SuccContenders": len(contenders), "SuccWinnerFollowers": len(win_followers),
          "SuccLoserFollowers": len(lose_followers), "SuccShared": len(shared)}
with open(OUT / f"succession_{E}_macros.tex", "w") as f:
    f.write(f"% Generated by code/03-descriptive_stats/viz_succession_{E}_network.py\n")
    for k, v in macros.items():
        f.write(f"\\newcommand{{\\{k}}}{{{v:,}}}\n")
print("saved stages 1-4 and macros:", macros)
