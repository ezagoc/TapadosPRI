"""
animate_network.py

Animated GIF of the full network of Mexican politicians through history. The whole
network grows in the background (grey): each politician appears the year they are
born, each tie the year the two met (`year_start`). On top, the CIRCLE OF THE
PRESIDENT IN OFFICE lights up — everyone with a direct tie to him, coloured by tie
kind — so each sexenio the highlighted circle jumps to a new group: elite turnover
made visible. A bar strip at the bottom shows new ties per year; they pulse with
the sexenio (≈30% of co-work ties form in the inauguration year).

Layout: a force-directed layout of the final network whose x-axis is anchored to
birth year, so generations flow left → right and the network visibly grows,
renews and ages. Only DATED ties are drawn (undated stated ties are omitted).

The president's circle includes his stated ties that have no known date (a
biography's family / mentor / friend) — they are shown once he is in office.

Output: OUTPUT_DIR/network_history.gif and network_history_final.png
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
from matplotlib.collections import LineCollection
from PIL import Image

CODE_DIR = Path(__file__).resolve().parents[1]
if str(CODE_DIR) not in sys.path:
    sys.path.append(str(CODE_DIR))

from config import OUTPUT_DIR
from network_utils import load_network

YEARS = range(1880, 2011)
FPS = 8
HOLD_LAST = 24                      # extra frames on the final year
SEED = 7

# dark surface + text tokens + the first three categorical slots (dark mode) of the
# validated reference palette (dataviz skill: all-pairs safe for three series)
SURFACE, INK, INK_2, INK_3 = "#1a1a19", "#ffffff", "#c3c2b7", "#6f6e69"
KINDS = {  # tie kind → (label, colour)
    "work":   ("Worked together (same unit)",   "#3987e5"),
    "school": ("Same school and cohort",        "#d95926"),
    "stated": ("Family · mentor · friend",      "#199e70"),
}
KIND_OF = {"co_work": "work", "co_military": "work", "co_revolution": "work",
           "co_education": "school", "family": "stated", "mentorship": "stated",
           "personal": "stated", "family_surname": "stated"}
HIGHLIGHT = INK                     # president in office: white, bold, larger (not a
                                    # hue — it would clash with the tie colours)

# (person_name in the dataset, short label, took office, left office)
PRESIDENTS = [
    ("Portes Gil, Emilio",               "Portes Gil",      1928, 1930),
    ("Rodriguez Lujan, Abelardo L",      "A. L. Rodríguez", 1932, 1934),
    ("Cardenas del Rio, Lazaro",         "Cárdenas",        1934, 1940),
    ("Avila Camacho, Manuel",            "Ávila Camacho",   1940, 1946),
    ("Aleman Valdes, Miguel",            "Alemán",          1946, 1952),
    ("Ruiz Cortines, Adolfo",            "Ruiz Cortines",   1952, 1958),
    ("Lopez Mateos, Adolfo",             "López Mateos",    1958, 1964),
    ("Diaz Ordaz, Gustavo",              "Díaz Ordaz",      1964, 1970),
    ("Echeverria Alvarez, Luis",         "Echeverría",      1970, 1976),
    ("Lopez Portillo Pacheco, Jose",     "López Portillo",  1976, 1982),
    ("de la Madrid Hurtado, Miguel",     "De la Madrid",    1982, 1988),
    ("Salinas de Gortari, Carlos",       "Salinas",         1988, 1994),
    ("Zedillo Ponce de Leon, Ernesto",   "Zedillo",         1994, 2000),
    ("Fox Quesada, Vicente",             "Fox",             2000, 2006),
    ("Calderon Hinojosa, Felipe de Jesus", "Calderón",      2006, 2012),
]


def build_layout(nodes: pd.DataFrame, edges: pd.DataFrame) -> dict:
    """Force layout of the final weighted network, x anchored to birth year."""
    g = nx.Graph()
    g.add_nodes_from(nodes.person_id)
    w = edges.groupby(["person_a", "person_b"])["tie_weight"].max()
    g.add_weighted_edges_from((a, b, float(x)) for (a, b), x in w.items())
    rng = np.random.default_rng(SEED)
    by = nodes.set_index("person_id")["birth_year"]
    bx = ((by - 1860) / (1990 - 1860) * 2 - 1).to_dict()
    init = {p: (bx[p], rng.uniform(-1, 1)) for p in g.nodes}
    pos = nx.spring_layout(g, pos=init, weight="weight", iterations=60,
                           k=1.2 / np.sqrt(len(g)), seed=SEED)
    # anchor x to the generation (85%); keep the force layout's vertical ORDER
    # (community structure) but spread it evenly over the height (rank transform)
    ys = pd.Series({p: pos[p][1] for p in g.nodes})
    ys = (ys.rank(pct=True) * 2 - 1).to_dict()
    return {p: (0.85 * bx[p] + 0.15 * pos[p][0], 0.9 * ys[p]) for p in g.nodes}


def main():
    edges, nodes = load_network()
    nodes = nodes.dropna(subset=["birth_year"]).copy()
    nodes["birth_year"] = nodes["birth_year"].astype(int)
    keep = set(nodes.person_id)
    all_edges = edges[edges.person_a.isin(keep) & edges.person_b.isin(keep)].copy()
    edges = all_edges.dropna(subset=["year_start"]).copy()
    edges["kind"] = edges.edge_type.map(KIND_OF)
    edges = edges.sort_values("tie_weight").drop_duplicates(["person_a", "person_b"], keep="last")

    print("Computing layout …")
    pos = build_layout(nodes, edges)
    xy = np.array([pos[p] for p in nodes.person_id])
    idx = {p: i for i, p in enumerate(nodes.person_id)}
    birth = nodes.birth_year.to_numpy()
    first_tie = pd.concat([edges[["person_a", "year_start"]].rename(columns={"person_a": "p"}),
                           edges[["person_b", "year_start"]].rename(columns={"person_b": "p"})]
                          ).groupby("p").year_start.min()
    active = nodes.person_id.map(first_tie).to_numpy(dtype=float)     # NaN = never tied
    seg = np.stack([xy[edges.person_a.map(idx)], xy[edges.person_b.map(idx)]], axis=1)
    e_year = edges.year_start.to_numpy()
    e_w = edges.tie_weight.to_numpy()
    e_col = np.array([matplotlib.colors.to_rgb(KINDS[k][1]) for k in edges.kind])
    e_kind = edges.kind.to_numpy()
    pres = [(idx.get(nodes.set_index("name").person_id.get(nm)), lab, a, b)
            for nm, lab, a, b in PRESIDENTS]
    pres = [p for p in pres if p[0] is not None]
    pid_of = nodes.person_id.to_numpy()
    deg_all = np.bincount(np.concatenate([edges.person_a.map(idx), edges.person_b.map(idx)]),
                          minlength=len(xy))
    # each president's ties: (alter index, kind, weight, year formed or NaN if undated)
    all_edges["kind"] = all_edges.edge_type.map(KIND_OF)
    circle_ties = {}
    for i, *_ in pres:
        p = pid_of[i]
        sub = all_edges[(all_edges.person_a == p) | (all_edges.person_b == p)]
        other = np.where(sub.person_a == p, sub.person_b, sub.person_a)
        circle_ties[i] = pd.DataFrame({"j": pd.Series(other).map(idx).to_numpy(),
                                       "kind": sub.kind.to_numpy(),
                                       "w": sub.tie_weight.to_numpy(),
                                       "year": sub.year_start.to_numpy()})
    new_per_year = edges.groupby("year_start").size().reindex(YEARS, fill_value=0)

    fig = plt.figure(figsize=(12, 7.2), dpi=100, facecolor=SURFACE)
    frames = []
    xlim = (xy[:, 0].min() - 0.05, xy[:, 0].max() + 0.05)
    ylim = (-1.08, 1.45)                         # headroom above for president labels
    # president labels above the network in two rows, shifted sideways just enough
    # not to overlap (greedy, left → right), each joined to its node by a leader line
    char_w = (xlim[1] - xlim[0]) / (12 * 0.98) * 0.085      # data units per char (~9pt)
    rows_right = [-np.inf, -np.inf]
    label_pos = {}
    for i, lab, a, b in sorted(pres, key=lambda t: xy[t[0], 0]):
        half = len(lab) * char_w / 2 + 0.01
        cands = [max(xy[i, 0], r + half) for r in rows_right]
        r = int(np.argmin([c - xy[i, 0] for c in cands]))
        label_pos[i] = (cands[r], 1.12 + 0.13 * r)
        rows_right[r] = cands[r] + half

    for year in YEARS:
        fig.clf()
        ax = fig.add_axes([0.01, 0.14, 0.98, 0.75], facecolor=SURFACE)
        ax.set_xlim(*xlim); ax.set_ylim(*ylim); ax.axis("off")

        # ties formed so far: old ones recede by weight, this year's are bright
        on = e_year <= year
        new = e_year == year
        old = on & ~new
        # background: the whole network so far, in grey (this year's ties a bit brighter)
        grey = matplotlib.colors.to_rgb(INK_2)
        if old.any():
            rgba = np.column_stack([np.tile(grey, (old.sum(), 1)), 0.02 + 0.05 * e_w[old]])
            ax.add_collection(LineCollection(seg[old], colors=rgba, linewidths=0.3))
        if new.any():
            glow = min(1.0, 20 / np.sqrt(new.sum()))
            rgba = np.column_stack([np.tile(grey, (new.sum(), 1)), glow * (0.1 + 0.25 * e_w[new])])
            ax.add_collection(LineCollection(seg[new], colors=rgba, linewidths=0.5))

        # generation guide: where people born in each decade sit on the x-axis
        for d in range(1880, 1991, 20):
            gx = 0.85 * ((d - 1860) / (1990 - 1860) * 2 - 1)
            ax.plot([gx, gx], [-0.97, -0.94], color=INK_3, lw=0.8)
            ax.text(gx, -1.0, f"born {d}", color=INK_3, fontsize=7.5, ha="center", va="top")

        # politicians born so far: faint until their first tie
        born = birth <= year
        lit = born & (active <= year)
        dim = born & ~lit
        ax.scatter(xy[dim, 0], xy[dim, 1], s=2.5, c=INK_3, alpha=0.5, linewidths=0)
        if lit.any():
            deg = np.bincount(np.concatenate([edges.person_a.map(idx)[on], edges.person_b.map(idx)[on]]),
                              minlength=len(xy))[lit]
            ax.scatter(xy[lit, 0], xy[lit, 1], s=3 + 2.2 * np.sqrt(deg), c=INK_2,
                       alpha=0.85, linewidths=0)

        # the circle of the president in office: his direct ties, coloured by kind
        cur = next((p for p in pres if p[2] <= year < p[3] or (year == p[3] == YEARS[-1])), None)
        n_circle = 0
        if cur is not None:
            ci = cur[0]
            ct = circle_ties[ci]
            ct = ct[ct.year.isna() | (ct.year <= year)]
            ct = ct[birth[ct.j.to_numpy()] <= year]
            n_circle = ct.j.nunique()
            for k in ("work", "school", "stated"):
                ck = ct[ct.kind == k]
                if len(ck):
                    segs = np.stack([np.tile(xy[ci], (len(ck), 1)), xy[ck.j.to_numpy()]], axis=1)
                    rgba = np.column_stack([np.tile(matplotlib.colors.to_rgb(KINDS[k][1]),
                                                    (len(ck), 1)), 0.35 + 0.5 * ck.w.to_numpy()])
                    ax.add_collection(LineCollection(segs, colors=rgba, linewidths=1.0, zorder=3))
            js = ct.j.unique()
            ax.scatter(xy[js, 0], xy[js, 1], s=10 + 2.5 * np.sqrt(deg_all[js]), c=INK,
                       edgecolors=SURFACE, linewidths=0.5, zorder=4)
            # name the circle's three best-connected members
            for j in sorted(js, key=lambda j: -deg_all[j])[:3]:
                if j in {p[0] for p in pres}:
                    continue
                ax.text(xy[j, 0], xy[j, 1] - 0.035, nodes.name.iloc[j].split(",")[0],
                        color=INK, fontsize=7.5, ha="center", va="top", zorder=6)

        # presidents: named from taking office; highlighted during the sexenio
        in_office = None
        for i, lab, a, b in pres:
            if year < a:
                continue
            now = a <= year < b or (year == b == YEARS[-1])
            if now:
                in_office = lab
            x, y = xy[i]
            lx, ly = label_pos[i]
            ax.plot([x, x, lx], [y, ly - 0.08, ly - 0.02], color=INK if now else INK_3,
                    lw=1.1 if now else 0.5, alpha=0.9, zorder=4)
            ax.scatter([x], [y], s=110 if now else 22, facecolors=INK if now else INK_2,
                       edgecolors=SURFACE, linewidths=1.5, zorder=5)
            ax.text(lx, ly, lab, ha="center", va="bottom",
                    fontsize=11 if now else 8, color=INK if now else INK_3,
                    fontweight="bold" if now else "normal", zorder=6)

        # header: year, president, counters
        fig.text(0.02, 0.945, f"{year}", fontsize=30, fontweight="bold", color=INK, va="center")
        fig.text(0.13, 0.955, "The network of Mexico's political elite",
                 fontsize=15, fontweight="bold", color=INK, va="center")
        fig.text(0.13, 0.920, f"President: {in_office}" if in_office else " ",
                 fontsize=11, color=INK_2, va="center")
        fig.text(0.98, 0.955, f"{int(born.sum()):,} politicians born", fontsize=11,
                 color=INK_2, ha="right", va="center")
        fig.text(0.98, 0.920, f"{int(on.sum()):,} ties", fontsize=11,
                 color=INK_2, ha="right", va="center")
        fig.text(0.98, 0.885, f"president's circle: {n_circle}" if cur else " ", fontsize=11,
                 color=INK, fontweight="bold", ha="right", va="center")

        # footer: legend, node note, timeline, source
        fig.text(0.02, 0.118, "Ties of the president in office:", color=INK, fontsize=9,
                 fontweight="bold", va="center")
        for j, (lab, col) in enumerate(KINDS.values()):
            fig.text(0.215 + j * 0.19, 0.118, "━", color=col, fontsize=14, va="center")
            fig.text(0.24 + j * 0.19, 0.118, lab, color=INK_2, fontsize=9, va="center")
        fig.text(0.98, 0.118, "grey: all other ties", color=INK_2, fontsize=9,
                 ha="right", va="center")
        # new ties per year (bars) with sexenio ticks: the network is rebuilt every 6 years
        tl = fig.add_axes([0.02, 0.03, 0.96, 0.065], facecolor=SURFACE)
        tl.set_xlim(YEARS[0] - 0.5, YEARS[-1] + 0.5); tl.axis("off")
        nv = new_per_year.to_numpy()
        tl.bar(list(YEARS), nv, width=0.8,
               color=[INK_2 if y < year else (INK if y == year else "#2e2e2c") for y in YEARS])
        for _, lab, a, b in pres:
            tl.plot([a, a], [0, nv.max() * 1.05], color=INK_3, lw=0.6, ls=":")
        for d in range(1880, 2011, 20):
            tl.text(d, -nv.max() * 0.12, str(d), color=INK_3, fontsize=7.5, ha="center", va="top")
        tl.text(YEARS[0], nv.max() * 0.95, "new ties per year  ·  dotted = new president",
                color=INK_3, fontsize=7.5, va="top")
        fig.text(0.13, 0.888, "Source: Camp, Mexican Political Biographies 1935–2009 · "
                 "grey = all dated ties · horizontal axis ≈ birth year",
                 color=INK_3, fontsize=7.5, va="center")

        fig.canvas.draw()
        frames.append(Image.fromarray(np.asarray(fig.canvas.buffer_rgba())[..., :3]))
        if year % 20 == 0:
            print(f"  {year}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    frames[-1].save(OUTPUT_DIR / "network_history_final.png")
    frames += [frames[-1]] * HOLD_LAST
    # one global palette for every frame (per-frame palettes shift the tie colours);
    # seeded with the key colours so the legend is exact in every frame
    keys = [SURFACE, INK, INK_2, INK_3] + [c for _, c in KINDS.values()]
    swatch = Image.new("RGB", (len(keys) * 40, 40))
    for k, c in enumerate(keys):
        swatch.paste(matplotlib.colors.to_hex(c), (k * 40, 0, k * 40 + 40, 40))
    sample = frames[::10] + [frames[-1]]
    w, h = sample[0].size
    board = Image.new("RGB", (w, h * len(sample) + 40))
    for k, f in enumerate(sample):
        board.paste(f, (0, k * h))
    for rep_ in range(w // swatch.width + 1):
        board.paste(swatch, (rep_ * swatch.width, h * len(sample)))
    palette = board.quantize(colors=255, method=Image.Quantize.MEDIANCUT)
    pal = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in frames]
    out = OUTPUT_DIR / "network_history.gif"
    pal[0].save(out, save_all=True, append_images=pal[1:], duration=int(1000 / FPS),
                loop=0, optimize=True)
    print(f"→ {out}  ({out.stat().st_size / 1e6:.1f} MB, {len(frames)} frames)")


if __name__ == "__main__":
    main()
