"""
13_plot_agency_series.py

Two figures from the agency panel (10_*), for the appendix slide on the 1964–69 imputation:

  investment_series        shares of federal public investment commanded by the largest
                           agencies, 1925–2003 (PEMEX, CFE, National Railways,
                           SCOP/SOP/SAHOP, Recursos Hidráulicos/SARH, IMSS), the imputed
                           1964–69 stretch shaded. Share of the year's total: dependencias +
                           paraestatal; 1984–97 the sector view (ramo_sector), where the
                           secretarías are not comparable and their lines stop in 1983.
  investment_series_total  total federal public investment in real 1960 pesos, 1959–2003
                           (the CPI deflator starts in 1959), imputed stretch in dark red,
                           sexenio boundaries as faint lines — a sanity figure.

House style: 10 x 5.2 in, white, no box or grid, grey mass + dark red accent, direct
labels, plain axis words, source note, key number on the plot; PDF + PNG to
OUTPUT_DIR/slides/; investment_series.pdf is also copied to the deck's figures folder.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

CODE_DIR = Path(__file__).resolve().parents[1]
if str(CODE_DIR) not in sys.path:
    sys.path.append(str(CODE_DIR))

from config import INVESTMENT_DIR, OUTPUT_DIR, ROOT  # noqa: E402

PANEL = INVESTMENT_DIR / "agency_investment_panel.csv"
RATES = INVESTMENT_DIR / "execution_rates.csv"
OUT_DIR = OUTPUT_DIR / "slides"
DECK_FIG = ROOT / "research" / "slides" / "pri_succession_slides" / "figures" / "investment_series.pdf"

RED, GREY, DARK, LIGHT = "#940034", "#9a9a9a", "#333333", "#e6e6e6"
SEXENIO_STARTS = [1934, 1940, 1946, 1952, 1958, 1964, 1970, 1976, 1982, 1988, 1994, 2000]
GAP = (1964, 1969)
# label → (keys, colour, last year shown, end label, peak label)
AGENCIES = {
    "National Railways": (["fnm"], "#4a4a4a", None, "National Railways", "National Railways"),
    # SCOP 1925–58 → SOP 1959–76 → SAHOP 1977–82 (INEGI's 1986 edition prints 1980–82 under the later name SEDUE)
    "Public works ministry (SCOP / SOP)": (["scop", "sop", "sahop", "sedue"], "#8c8c8c", 1982, "Public works ministry",
                                           "Public works ministry (SCOP / SOP)"),
    "PEMEX": (["pemex"], RED, None, "PEMEX", None),
    "CFE": (["cfe"], "#d9707f", None, "CFE", None),
    "IMSS": (["imss"], "#c4c4c4", None, "IMSS", None),
}
PEAK_LABEL_AT = {"National Railways": (1927.0, 48.0),            # above its 1925–27 segment (55→44%)
                 "Public works ministry (SCOP / SOP)": (1938.5, 44.3)}   # above its 1936 peak (43%)
KEY_LINE = "Federal investment moved from the railways and the\npublic-works ministry to PEMEX and CFE."

plt.rcParams.update({"font.family": "sans-serif", "font.size": 10, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.edgecolor": "#777777", "axes.linewidth": 0.6,
                     "xtick.color": "#555555", "ytick.color": "#555555", "axes.labelcolor": "#444444"})


def totals(panel: pd.DataFrame, col: str) -> pd.Series:
    dep = panel[panel.block == "dependencias"].groupby("year")[col].sum()
    para = panel[panel.block == "paraestatal"].groupby("year")[col].sum()
    ramo = panel[panel.block == "ramo_sector"].groupby("year")[col].sum()
    years = sorted(panel.year.unique())
    return pd.Series({y: dep.get(y, 0) + para.get(y, 0) if y in dep.index else ramo.get(y, np.nan) for y in years})


def sexenio_lines(ax, ymax):
    for s in SEXENIO_STARTS:
        ax.axvline(s, color=LIGHT, lw=0.6, zorder=0)


def _overlaps(fig, texts) -> list[tuple[str, str]]:
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    boxes = [(t.get_text().replace("\n", " ")[:30], t.get_window_extent(r)) for t in texts]
    return [(a, b) for i, (a, ba) in enumerate(boxes) for b, bb in boxes[i + 1:] if ba.overlaps(bb)]


def fig_shares(panel: pd.DataFrame, rates: pd.DataFrame):
    tot = totals(panel, "value_mn_new_pesos")
    fig, ax = plt.subplots(figsize=(10, 5.2))
    ax.axvspan(GAP[0] - 0.5, GAP[1] + 0.5, color="#f3e4e7", zorder=0)
    texts = []
    end_pos = []                                          # (y, text, colour, bold)
    for name, (keys, colour, last, end_label, peak_label) in AGENCIES.items():
        s = panel[panel.agency_key.isin(keys)].groupby("year").value_mn_new_pesos.sum()
        s = (100 * s / tot.reindex(s.index)).dropna().sort_index()
        if last:
            s = s[s.index <= last]
        ax.plot(s.index, s.values, color=colour, lw=1.6, zorder=3 if colour == RED else 2)
        if last:                                          # series that stops: label at its end
            texts.append(ax.annotate(end_label, (s.index[-1], s.values[-1]), xytext=(4, 0),
                                     textcoords="offset points", fontsize=8.5, color=colour, va="center"))
        else:
            end_pos.append([s.values[-1], end_label, colour, colour == RED, s.index[-1]])
        if peak_label:                                    # also near the 1930s–40s peak
            xp, yp = PEAK_LABEL_AT[name]
            texts.append(ax.text(xp, yp, peak_label, fontsize=8.5, color=colour, va="bottom"))
    # right-end labels, pushed apart so they never overlap (min gap 2.2 pp)
    end_pos.sort(key=lambda t: t[0])
    y_prev = -10
    for item in end_pos:
        item[0] = max(item[0], y_prev + 2.2)
        y_prev = item[0]
    for y, lab, colour, bold, x in end_pos:
        texts.append(ax.annotate(lab, (x, y), xytext=(5, 0), textcoords="offset points", fontsize=9,
                                 color=colour, va="center", fontweight="bold" if bold else "normal"))
    texts.append(ax.text(GAP[0] + 0.3, 40.5, "1964–69 imputed", fontsize=8, color=RED, va="top"))
    ax.set_xlim(1925, 2010)
    ax.set_ylim(0, 58)                                    # railways: 55% in 1925
    ax.set_ylabel("share of federal public investment, percent")
    ax.set_xlabel("")
    ax.set_xticks(range(1930, 2010, 10))
    ax.set_yticks(range(0, 51, 10))
    fig.text(0.01, 0.01, "Source: Secretaría de la Presidencia (1925–70), SPP (1970–80), INEGI (1980–2003); real 1960 pesos. 1964–69: no realized figures by agency were\n"
                         "published; each agency's authorized budget is multiplied by the execution rate of its purpose (realized over authorized, by purpose, from the same\n"
                         "books: 0.80 in 1965, 0.75 in 1966, 0.95–0.96 in 1967–69) and scaled to the printed realized total.",
             fontsize=7.5, color=GREY, ha="left", va="bottom", linespacing=1.3)
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    for a, b in _overlaps(fig, texts):
        print(f"  WARNING: labels overlap: '{a}' / '{b}'")
    return fig


def fig_total(panel: pd.DataFrame, rates: pd.DataFrame):
    tot = totals(panel, "real_mn_1960_pesos").dropna()
    tot = tot[tot.index >= 1959] / 1000      # thousand million 1960 pesos
    fig, ax = plt.subplots(figsize=(10, 5.2))
    sexenio_lines(ax, tot.max())
    ax.plot(tot.index, tot.values, color=GREY, lw=1.4, zorder=2)
    g = tot[(tot.index >= GAP[0] - 1) & (tot.index <= GAP[1] + 1)]
    ax.plot(g.index, g.values, color=RED, lw=2.0, zorder=3)
    ax.scatter(g.index[1:-1], g.values[1:-1], color=RED, s=14, zorder=4)
    nat = rates[(rates.level == 0) & (rates.year.between(1965, 1969))].set_index("year").rate
    ax.annotate("1964–69 imputed: authorized × execution rate\n"
                f"(national rate {nat.min():.2f}–{nat.max():.2f}; 1964 = authorized level)",
                (1966.5, g.max() + 2.5), fontsize=8.5, color=RED, ha="center", va="bottom")
    for s in [1964, 1970, 1976, 1982, 1988, 1994, 2000]:
        if s in tot.index:
            ax.annotate(str(s), (s, tot[s]), xytext=(0, 5), textcoords="offset points", fontsize=7.5,
                        color="#777777", ha="center")
    ax.set_xlim(1958, 2004)
    ax.set_ylim(0, tot.max() * 1.15)
    ax.set_ylabel("thousand million pesos of 1960")
    ax.set_xticks(range(1960, 2005, 5))
    fig.text(0.01, 0.01, "Source: agency panel (dependencias + paraestatal; 1984–97 sector view), CPI deflator "
                         "1960 = 100. Election years labelled; faint lines mark the start of each sexenio.",
             fontsize=7.5, color="#777777")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    return fig


def main():
    panel = pd.read_csv(PANEL)
    rates = pd.read_csv(RATES)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, fn in (("investment_series", fig_shares), ("investment_series_total", fig_total)):
        fig = fn(panel, rates)
        for ext in ("pdf", "png"):
            fig.savefig(OUT_DIR / f"{name}.{ext}", dpi=200 if ext == "png" else None, facecolor="white")
        plt.close(fig)
        print(f"→ {OUT_DIR / name}.pdf/.png")
    if DECK_FIG.parent.exists():
        shutil.copy(OUT_DIR / "investment_series.pdf", DECK_FIG)
        print(f"→ {DECK_FIG}")


if __name__ == "__main__":
    main()
