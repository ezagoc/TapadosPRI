"""Slide versions of the event studies: landscape panels, slide palette, no titles.

Reads the official R results in research/main_R/output_v2/:
  event_study.csv                 combined / extensive / intensive (main DR-DiD, recentred Conley-Taber + Ferman-Pinto bands)
  budget_agencies_event_study.csv V1: agency head at e-2 nearest to the designee (log investment share)
  budget_event_study.csv          extensive = heads an investment agency; intensive = share of federal investment commanded
Writes OUTPUT_DIR/slides/es_<name>.{png,pdf}; es_posts_pesos is the two-panel "Posts, not pesos" figure.
"""
import sys
from pathlib import Path
import pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code"))
from config import OUTPUT_DIR  # noqa: E402

ACC, INK, Z4, Z5, Z6 = "#940034", "#111111", "#a1a1aa", "#71717a", "#52525b"
OUT = OUTPUT_DIR / "slides"; OUT.mkdir(parents=True, exist_ok=True)
MAIN = ROOT / "research" / "main_R" / "output_v2"
es = pd.read_csv(MAIN / "event_study.csv")
ag = pd.read_csv(MAIN / "budget_agencies_event_study.csv")
bu = pd.read_csv(MAIN / "budget_event_study.csv")
NOTE = "Point estimates; thick bars 90% and thin bars 95% confidence intervals (Conley-Taber, size-corrected). Reference year: two years before the election."


def style(ax):
    ax.set_facecolor("white")
    for s in ["top", "right"]: ax.spines[s].set_visible(False)
    for s in ["left", "bottom"]: ax.spines[s].set_color(Z4)
    ax.tick_params(colors=Z6, labelsize=10)
    ax.axhline(0, color=Z5, lw=0.8)
    for x, lab in [(-1.5, "destape"), (0.5, "new president takes office")]:
        ax.axvline(x, color=Z5, lw=0.8, ls=(0, (3, 3)))
        ax.text(x + 0.08, 0.97, lab, transform=ax.get_xaxis_transform(), va="top", ha="left", fontsize=9, color=Z6)


def draw(ax, d, ycol, lo, hi, lo90=None, hi90=None, tmin=-6, tmax=6):
    d = d[(d.t >= tmin) & (d.t <= tmax)].sort_values("t")
    ax.errorbar(d.t, d[ycol], yerr=[d[ycol] - d[lo], d[hi] - d[ycol]], fmt="none", ecolor=ACC, elinewidth=1.0, capsize=3, zorder=2)
    if lo90 is not None:
        ax.errorbar(d.t, d[ycol], yerr=[d[ycol] - d[lo90], d[hi90] - d[ycol]], fmt="o", color=ACC, ms=6, elinewidth=3.2, capsize=0, zorder=3)
    else:
        ax.plot(d.t, d[ycol], "o", color=ACC, ms=6, zorder=3)
    ax.set_xticks(range(tmin, tmax + 1)); ax.set_xticklabels([f"{t:+d}" if t else "0" for t in range(tmin, tmax + 1)])
    ax.set_xlabel("Years relative to the election", fontsize=11, color=INK)


def panel(df, ycol, lo, hi, lo90, hi90, ylabel, name):
    fig, ax = plt.subplots(figsize=(11.5, 4.6), dpi=200); fig.patch.set_facecolor("white")
    style(ax); draw(ax, df, ycol, lo, hi, lo90, hi90)
    ax.set_ylabel(ylabel, fontsize=11, color=INK)
    ax.text(0.0, -0.22, NOTE, transform=ax.transAxes, fontsize=8.5, color=Z5, va="top")
    save(fig, name)


def save(fig, name):
    fig.savefig(OUT / f"es_{name}.png", facecolor="white", bbox_inches="tight"); fig.savefig(OUT / f"es_{name}.pdf", facecolor="white", bbox_inches="tight")
    plt.close(fig); print("saved", name)


def posts_pesos():
    """Two panels: heads an investment agency (pp) and share of federal investment commanded (pp of the federal total)."""
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.6), dpi=200); fig.patch.set_facecolor("white")
    for ax, (key, ylabel, key_number) in zip(axes, [
        ("extensive", "Gap in the share heading an investment agency\n(designee's vs. losers' followers)", "post-destape gap: +9 pp\n95% CI [+5, +13]"),
        ("intensive", "Gap in the share of federal investment commanded\n(pp of the federal total)", "post-destape gap: −0.1 pp\n95% CI [−0.4, +0.3]"),
    ]):
        style(ax); draw(ax, bu[bu.outcome == key], "est", "lo", "hi")
        ax.set_ylabel(ylabel, fontsize=10.5, color=INK)
        ax.text(0.02, 0.96, key_number, transform=ax.transAxes, fontsize=9.5, color=ACC, ha="left", va="top")
    fig.text(0.0, -0.04, "Point estimates with 95% Conley-Taber confidence intervals (size-corrected). Reference year: two years before the election. "
             "Pooled gaps: traditional DR-DiD, e+1..e+4 vs. e-6..e-2.", fontsize=8.5, color=Z5, va="top")
    fig.tight_layout(w_pad=2.5)
    save(fig, "posts_pesos")


panel(es[es.outcome == "combined"], "main", "main_lo", "main_hi", "main_lo90", "main_hi90", "Rank gap, rungs\n(designee's vs. losers' followers)", "combined")
panel(es[es.outcome == "extensive"], "main", "main_lo", "main_hi", "main_lo90", "main_hi90", "Gap in the share holding a post\n(designee's vs. losers' followers)", "extensive")
panel(es[es.outcome == "intensive"], "main", "main_lo", "main_hi", "main_lo90", "main_hi90", "Rank gap among those in office, rungs\n(designee's vs. losers' followers)", "intensive")
panel(ag[ag.version == "pre_nearest"], "est", "lo", "hi", "lo90", "hi90", "Change in log investment share\n(designee-linked vs. loser-linked agencies)", "agencies")
posts_pesos()

def story():
    """R2: the story figure. Left: the rank gap over two sexenios (expiry.R, full sample). Right: the nine ATT_e."""
    import re
    ex = pd.read_csv(MAIN / "expiry" / "expiry_event_study.csv")
    d = ex[(ex["sample"] == "full") & (ex.outcome == "combined") & (ex.t >= -6) & (ex.t <= 12)].sort_values("t")
    txt = (MAIN / "main_result.txt").read_text()
    comp = [(int(y), float(a)) for y, a in re.findall(r"(19\d\d): n_D =\s*\d+\s+ATT_e ([+-]\d\.\d+)", txt)]
    att = float(re.search(r"ATT, doubly robust DiD, person-weighted\s+([+-]\d\.\d+)", txt).group(1))
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(11.5, 4.6), dpi=200, gridspec_kw={"width_ratios": [2.1, 1]})
    fig.patch.set_facecolor("white")
    # left
    ax.set_facecolor("white")
    for sp in ["top", "right"]: ax.spines[sp].set_visible(False)
    for sp in ["left", "bottom"]: ax.spines[sp].set_color(Z4)
    ax.tick_params(colors=Z6, labelsize=10)
    ax.axhline(0, color=Z5, lw=0.8)
    ax.axvspan(6.5, 12.5, color="#f4f4f5", zorder=0)
    for x, lab, y in [(-1.5, "destape", 0.98), (0.5, "new president", 0.98), (4.5, "next destape", 0.92), (6.5, "next president", 0.98)]:
        ax.axvline(x, color=Z5, lw=0.8, ls=(0, (3, 3)))
        ax.text(x + 0.1, y, lab, transform=ax.get_xaxis_transform(), va="top", ha="left", fontsize=8.5, color=Z6)
    ax.fill_between(d.t, d.lo, d.hi, color=ACC, alpha=0.10, lw=0)
    ax.plot(d.t, d.est, "-o", color=ACC, ms=5, lw=2.0, zorder=3)
    ax.set_xticks(range(-6, 13, 2)); ax.set_xticklabels([f"{t:+d}" if t else "0" for t in range(-6, 13, 2)])
    ax.set_xlabel("Years relative to the election", fontsize=11, color=INK)
    ax.set_ylabel("Rank gap, rungs\n(designee's vs. losers' followers)", fontsize=11, color=INK)
    ax.text(2.5, 1.22, "+1.0 rung for the whole sexenio", color=ACC, fontsize=9.5, ha="center")
    ax.text(9.5, -0.42, "+0.4 under the next president", color=Z6, fontsize=9.5, ha="center")
    ax.text(-3.6, 0.55, "nothing before", color=Z6, fontsize=9.5, ha="center")
    # right
    bx.set_facecolor("white")
    for sp in ["top", "right"]: bx.spines[sp].set_visible(False)
    for sp in ["left", "bottom"]: bx.spines[sp].set_color(Z4)
    bx.tick_params(colors=Z6, labelsize=9)
    bx.axhline(0, color=Z5, lw=0.8)
    ys = [y for y, _ in comp]; vs = [a for _, a in comp]
    bx.scatter(ys, vs, color=Z5, s=36, zorder=3)
    bx.axhline(att, color=ACC, lw=1.6)
    bx.text(1939, att + 0.012, f"pooled +{att*100:.0f} pp (+48%)", color=ACC, fontsize=9.5, va="bottom")
    bx.text(1939, 0.40, "nine of nine positive", color=Z6, fontsize=9.5)
    bx.set_xticks(ys); bx.set_xticklabels([str(y)[2:] for y in ys], fontsize=8.5)
    bx.set_xlabel("Succession", fontsize=11, color=INK)
    bx.set_ylabel("Promotion gap by succession\n(share promoted within four years)", fontsize=10, color=INK)
    bx.set_ylim(-0.05, 0.45)
    fig.text(0.0, -0.04, "Left: doubly robust DiD of the rank gap relative to year e-2 (0 if no post), 95% Conley-Taber band with the Ferman-Pinto correction. "
             "Right: the effect of the patron's designation on promotion, by succession; line = pooled estimate (exact p = 0.008).",
             fontsize=8.5, color=Z5, va="top")
    fig.tight_layout(w_pad=2.0)
    save(fig, "story")


def margins():
    """R3: extensive and intensive margins side by side."""
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.6), dpi=200); fig.patch.set_facecolor("white")
    for ax, (key, ylabel, note) in zip(axes, [
        ("extensive", "Gap in the share holding a post\n(designee's vs. losers' followers)", "post-destape average +0.06 [−0.07, +0.17]"),
        ("intensive", "Rank gap among those in office, rungs\n(designee's vs. losers' followers)", "post-destape average +0.54 [+0.24, +0.88]"),
    ]):
        style(ax); draw(ax, es[es.outcome == key], "main", "main_lo", "main_hi", "main_lo90", "main_hi90")
        ax.set_ylabel(ylabel, fontsize=10.5, color=INK)
        ax.text(0.02, 0.04, note, transform=ax.transAxes, fontsize=9.5, color=ACC, ha="left", va="bottom")
    fig.text(0.0, -0.04, NOTE, fontsize=8.5, color=Z5, va="top")
    fig.tight_layout(w_pad=2.5)
    save(fig, "margins")


story()
margins()
