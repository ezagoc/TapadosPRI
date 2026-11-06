"""Slide figure: the 1970 exclusive networks of the three largest contenders against the whole active elite.

Background (grey): every politician eligible in the design for 1970 (a ranked post in 1964-68, aged 25-75 in
1970, not a hopeful of 1970 or earlier) plus the six hopefuls, and every position-based tie among them formed
by 1968. Foreground (colour): the exclusive networks of Echeverría, Corona del Rosal and Ortiz Mena exactly as
main_estimate.py builds them (politicians tied to that hopeful and to no other hopeful of the slate). The other
three hopefuls are marked in grey. Edge colours as in bio_links_echeverria. Spring layout with the hopefuls pinned.
Output: OUTPUT_DIR/slides/networks_1970_full.{png,pdf}
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import networkx as nx
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code")); sys.path.insert(0, str(ROOT / "research" / "main"))
from config import OUTPUT_DIR                                            # noqa: E402
from main_estimate import S, U, SLATE, edges, cand, TIE_TYPES, LAG        # noqa: E402
from network_utils import ego_view                                       # noqa: E402

E = 1970; T0 = E - LAG
ACC, INK, Z3, Z4, Z5, Z6, Z8 = "#940034", "#111111", "#d4d4d8", "#a1a1aa", "#71717a", "#52525b", "#27272a"
YEL, BLU, GRN = (1.0, 0.86, 0.25), (0.50, 0.74, 1.0), (0.55, 0.86, 0.55)
OUT = OUTPUT_DIR / "slides"; OUT.mkdir(parents=True, exist_ok=True)

slate = SLATE[E]; winner = slate[0]
names = cand.drop_duplicates("person_id").set_index("person_id").corcholata_name.replace({"Emilio Martínez Manatou": "Emilio Martínez Manautou"})
s = S[S.election == E]
sizes = s.patron.value_counts()
HIGH = [winner] + [c for c in sizes.index if c != winner][:2]            # designee + the two largest losing networks

# background graph
others = [c for c in slate if c not in HIGH]
ids = (set(U[E].pid) | set(slate)) - set(others)                       # the three highlighted contenders only
bg = edges[edges.edge_type.isin(TIE_TYPES) & (edges.year_start <= T0) & edges.person_a.isin(ids) & edges.person_b.isin(ids)]
pairs = bg[["person_a", "person_b"]].drop_duplicates()
G = nx.Graph(); G.add_nodes_from(ids); G.add_edges_from(pairs.itertuples(index=False))

# foreground ties: hopeful -> exclusive alter
ev = ego_view(edges, slate, as_of=T0)
ev = ev[ev.edge_type.isin(TIE_TYPES) & ev.year_start.notna() & ev.alter_id.isin(s.pid)]
ev = ev.merge(s[["pid", "patron"]], left_on="alter_id", right_on="pid"); ev = ev[ev.ego_id == ev.patron]

# layout: the three highlighted exclusive networks keep a readable star geometry (hopeful at the centre of a disk
# of his alters); every other politician is placed by a spring layout that treats those positions as fixed, so the
# rest of the elite settles next to the people it is tied to. Politicians outside the giant component are scattered
# faintly on the outside.
rng = np.random.default_rng(1970)


def disk(centre, n, r_in, r_out):
    k = np.arange(n); phi = k * 2.399963 + rng.uniform(-0.15, 0.15, n)
    rad = r_in + (r_out - r_in) * np.sqrt((k + 0.5) / n)
    return np.c_[centre[0] + rad * np.cos(phi), centre[1] + rad * np.sin(phi)]


centres = {winner: np.array([0.0, 0.0]), HIGH[1]: np.array([-4.9, 0.3]), HIGH[2]: np.array([4.9, 0.3])}
fixed = dict(centres)
for c in HIGH:
    alters = s[s.patron == c].pid.tolist(); n = len(alters)
    pts = disk(centres[c], n, 0.4, 0.4 + 0.17 * np.sqrt(n))
    fixed.update(dict(zip(alters, pts)))
giant = max(nx.connected_components(G), key=len)
init = {n: fixed.get(n, rng.uniform([-6.5, -3.3], [6.5, 3.3])) for n in giant}
pos = nx.spring_layout(G.subgraph(giant), pos=init, fixed=[n for n in fixed if n in giant], k=0.5, iterations=150, seed=11)
rest = [n for n in G.nodes if n not in giant]
ang = rng.uniform(0, 2 * np.pi, len(rest)); rad = rng.uniform(0.97, 1.08, len(rest))
for n, a, r in zip(rest, ang, rad): pos[n] = np.array([6.9 * r * np.cos(a), 3.2 * r * np.sin(a)])
for n in pos: pos[n] = np.array([np.clip(pos[n][0], -7.3, 7.3), np.clip(pos[n][1], -3.2, 3.6)])

fig, ax = plt.subplots(figsize=(13.33, 6.8), dpi=200); fig.patch.set_facecolor("white")
ax.set_xlim(-7.5, 7.5); ax.set_ylim(-4.25, 3.75); ax.set_aspect("equal"); ax.axis("off")
# background
segs = [(pos[a], pos[b]) for a, b in G.edges]
ax.add_collection(LineCollection(segs, colors=Z3, linewidths=0.25, alpha=0.16, zorder=0))
fg_nodes = set(s[s.patron.isin(HIGH)].pid) | set(HIGH)
bgn = np.array([pos[n] for n in G.nodes if n not in fg_nodes])
ax.scatter(bgn[:, 0], bgn[:, 1], s=5, color=Z4, alpha=0.35, linewidths=0, zorder=1)


def colour(r):
    if r.edge_type == "co_work": return BLU
    if r.edge_type == "co_education": return GRN if "/staff]" in str(r.focus) else YEL
    return Z5


for c in HIGH:
    win = c == winner
    for r in ev[ev.ego_id == c].itertuples():
        a, b = pos[c], pos[r.alter_id]
        ax.plot([a[0], b[0]], [a[1], b[1]], color=colour(r), lw=1.3 if win else 1.0, alpha=1.0 if win else 0.9, zorder=3 if win else 2, solid_capstyle="round")
    pts = np.array([pos[p] for p in s[s.patron == c].pid])
    ax.scatter(pts[:, 0], pts[:, 1], s=48 if win else 22, marker="*" if win else "o", color=INK if win else Z8, zorder=5 if win else 4, linewidths=0)
for c in HIGH:
    win = c == winner
    ax.scatter(*pos[c], s=640 if win else 240, marker="*" if win else "o", color=ACC if win else Z8, zorder=7, edgecolors="white", linewidths=1.2)
    n = int(sizes.get(c, 0)); lab = f"{names[c]}  ({n})"
    dy = -(0.4 + 0.17 * np.sqrt(n) + 0.2)
    ax.text(pos[c][0], pos[c][1] + dy, lab, ha="center", va="top", fontsize=10.5 if win else 9.5, color=ACC if win else Z8,
            weight="bold" if win else "normal", zorder=8, bbox=dict(boxstyle="round,pad=0.15", facecolor="white", edgecolor="none", alpha=0.75))

handles = [Line2D([], [], color=YEL, lw=2.2, label="same school, same cohort"),
           Line2D([], [], color=BLU, lw=2.2, label="same office, same years"),
           Line2D([], [], color=GRN, lw=2.2, label="same faculty, same years"),
           Line2D([], [], marker="*", color="w", markerfacecolor=ACC, markersize=15, label="designee"),
           Line2D([], [], marker="*", color="w", markerfacecolor=INK, markersize=9, label="tied only to the designee"),
           Line2D([], [], marker="o", color="w", markerfacecolor=Z8, markersize=10, label="losing contender"),
           Line2D([], [], marker="o", color="w", markerfacecolor=Z8, markersize=5.5, label="tied only to that contender"),
           Line2D([], [], color=Z3, lw=1.5, marker="o", markerfacecolor=Z4, markeredgewidth=0, markersize=4, label=f"other politicians active in {E}")]
ax.legend(handles=handles, loc="lower center", ncol=4, frameon=False, fontsize=8.6, handlelength=1.6, columnspacing=1.6, bbox_to_anchor=(0.5, 0.0))
ax.text(7.45, 3.7, f"ties formed by {T0}", ha="right", va="top", fontsize=8.5, color=Z5, style="italic")
fig.savefig(OUT / "networks_1970_full.png", dpi=200, facecolor="white", bbox_inches="tight"); fig.savefig(OUT / "networks_1970_full.pdf", facecolor="white", bbox_inches="tight")
print("saved; background:", G.number_of_nodes(), "politicians,", G.number_of_edges(), "ties; highlighted:", {names[c]: int(sizes.get(c, 0)) for c in HIGH})
