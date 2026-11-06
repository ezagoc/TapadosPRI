"""Slide figure: the networks the main design actually uses, for the 1970 succession.

Exactly the analysis sample of research/main/main_estimate.py (imported, not re-derived): for each hopeful
of the main slate, the politicians tied to him and to NO other hopeful (his exclusive network) by a
position-based tie formed by e-2 (co-work, co-education, co-military, co-revolution; stated family /
mentorship / personal ties are not used). Politicians tied to two or more hopefuls are dropped from the
sample and are not drawn. Only hopeful-alter ties are drawn (alter-alter ties play no role in the design).
Edge colours follow bio_links_echeverria: same school & cohort (yellow), same office & years (blue), same
faculty & years (green). Designee = star, his exclusive network = small stars; losing contenders and their
networks = circles, faded.
Output: OUTPUT_DIR/slides/networks_1970.{png,pdf}
"""
import sys
from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code")); sys.path.insert(0, str(ROOT / "research" / "main"))
from config import OUTPUT_DIR                                        # noqa: E402
from main_estimate import S, SLATE, edges, cand, TIE_TYPES, LAG       # noqa: E402  (the frozen sample)
from network_utils import ego_view                                   # noqa: E402

E = 1970
ACC, INK, Z4, Z5, Z6 = "#940034", "#111111", "#a1a1aa", "#71717a", "#52525b"
YEL, BLU, GRN = (1.0, 0.86, 0.25), (0.50, 0.74, 1.0), (0.55, 0.86, 0.55)
OUT = OUTPUT_DIR / "slides"; OUT.mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(1970)

slate = SLATE[E]; winner = slate[0]
names = cand.drop_duplicates("person_id").set_index("person_id").corcholata_name.replace({"Emilio Martínez Manatou": "Emilio Martínez Manautou"})  # typo in the xlsx
s = S[S.election == E]
ev = ego_view(edges, slate, as_of=E - LAG)
ev = ev[ev.edge_type.isin(TIE_TYPES) & ev.year_start.notna() & ev.alter_id.isin(s.pid)]
ev = ev.merge(s[["pid", "patron"]], left_on="alter_id", right_on="pid")
ev = ev[ev.ego_id == ev.patron]                                      # by construction: the alter's only hopeful


def colour(r):
    if r.edge_type == "co_work": return BLU
    if r.edge_type == "co_education": return GRN if "/staff]" in str(r.focus) else YEL
    return Z5                                                        # co_military / co_revolution (none in 1970)


def disk(centre, n, r_in, r_out):
    """n points spread over an annulus around centre (sunflower spacing, jittered)."""
    k = np.arange(n); phi = k * 2.399963 + rng.uniform(-0.15, 0.15, n)
    rad = r_in + (r_out - r_in) * np.sqrt((k + 0.5) / n)
    return np.c_[centre[0] + rad * np.cos(phi), centre[1] + rad * np.sin(phi)]


fig, ax = plt.subplots(figsize=(13.33, 6.8), dpi=200); fig.patch.set_facecolor("white")
ax.set_xlim(-7.0, 7.0); ax.set_ylim(-3.6, 3.6); ax.set_aspect("equal"); ax.axis("off")

losers = sorted(slate[1:], key=lambda c: -(s.patron == c).sum())   # by network size
# fixed layout: the two big losing networks left and right, the two small ones top, the singleton bottom right
spots = [((-4.9, 0.3), "below"), ((4.9, 0.3), "below"), ((-3.0, 2.35), "left"), ((3.0, 2.35), "right"), ((2.6, -2.45), "right")]
centres = {winner: np.array([0.0, 0.0])}; side = {winner: "below"}
for c, (xy, sd) in zip(losers, spots):
    centres[c] = np.array(xy); side[c] = sd
for c in slate:
    alters = s[s.patron == c].pid.tolist(); n = len(alters)
    win = c == winner
    r_out = 0.4 + 0.17 * np.sqrt(n)
    pts = disk(centres[c], n, 0.4, r_out) if n else np.zeros((0, 2))
    pos = dict(zip(alters, pts))
    alpha = 1.0 if win else 0.38
    for r in ev[ev.ego_id == c].itertuples():
        p = pos[r.alter_id]
        ax.plot([centres[c][0], p[0]], [centres[c][1], p[1]], color=colour(r), lw=1.1 if win else 0.9, alpha=alpha, zorder=1 if win else 0, solid_capstyle="round")
    if n:
        ax.scatter(pts[:, 0], pts[:, 1], s=46 if win else 26, marker="*" if win else "o", color=INK if win else Z5, alpha=alpha, zorder=3 if win else 2, linewidths=0)
    ax.scatter(*centres[c], s=620 if win else 260, marker="*" if win else "o", color=ACC if win else Z6, alpha=1.0 if win else 0.75, zorder=5, edgecolors="white", linewidths=1.2)
    lab = f"{names[c]}  ({n})"
    kw = dict(fontsize=10.5 if win else 9.5, color=ACC if win else Z6, weight="bold" if win else "normal", zorder=6)
    cx, cy = centres[c]
    if side[c] == "below": ax.text(cx, cy - r_out - 0.2, lab, ha="center", va="top", **kw)
    elif side[c] == "left": ax.text(cx - r_out - 0.12, cy, lab, ha="right", va="center", **kw)
    else: ax.text(cx + r_out + 0.12, cy, lab, ha="left", va="center", **kw)

handles = [Line2D([], [], color=YEL, lw=2.2, label="same school, same cohort"),
           Line2D([], [], color=BLU, lw=2.2, label="same office, same years"),
           Line2D([], [], color=GRN, lw=2.2, label="same faculty, same years"),
           Line2D([], [], marker="*", color="w", markerfacecolor=ACC, markersize=15, label="designee"),
           Line2D([], [], marker="*", color="w", markerfacecolor=INK, markersize=9, label="tied only to the designee"),
           Line2D([], [], marker="o", color="w", markerfacecolor=Z6, markersize=10, label="losing contender"),
           Line2D([], [], marker="o", color="w", markerfacecolor=Z5, markersize=6, alpha=0.6, label="tied only to that contender")]
ax.legend(handles=handles, loc="lower center", ncol=7, frameon=False, fontsize=8.6, handlelength=1.6, columnspacing=1.3, bbox_to_anchor=(0.5, -0.02))
ax.text(6.85, 3.4, f"ties formed by {E - LAG}", ha="right", va="top", fontsize=8.5, color=Z5, style="italic")
fig.savefig(OUT / "networks_1970.png", dpi=200, facecolor="white", bbox_inches="tight"); fig.savefig(OUT / "networks_1970.pdf", facecolor="white", bbox_inches="tight")
print("saved;", {names[c]: int((s.patron == c).sum()) for c in slate}, "| ties drawn:", len(ev))
