"""
13_plot_agency_series.py

Two figures from the agency panel (10_*), for the appendix slide on the 1964–69 imputation:

  investment_series        shares of federal public investment commanded by the largest
                           agencies, 1925–2003 (PEMEX, CFE, Ferrocarriles Nacionales,
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

RED, GREY, DARK, LIGHT = "#8b1a1a", "#9a9a9a", "#333333", "#e6e6e6"
SEXENIO_STARTS = [1934, 1940, 1946, 1952, 1958, 1964, 1970, 1976, 1982, 1988, 1994, 2000]
GAP = (1964, 1969)
AGENCIES = {   # label → (keys, colour)
    "PEMEX": (["pemex"], RED),
    "CFE": (["cfe"], "#c0504d"),
    "Ferrocarriles Nacionales": (["fnm"], GREY),
    "Public works (SCOP / SOP / SAHOP)": (["scop", "sop", "sahop"], GREY),
    "Water resources (SRH / SARH)": (["srh", "sarh"], GREY),
    "IMSS": (["imss"], GREY),
}
SECRETARIAS = {"Public works (SCOP / SOP / SAHOP)", "Water resources (SRH / SARH)"}

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


def fig_shares(panel: pd.DataFrame, rates: pd.DataFrame):
    tot = totals(panel, "value_mn_new_pesos")
    fig, ax = plt.subplots(figsize=(10, 5.2))
    ax.axvspan(GAP[0] - 0.5, GAP[1] + 0.5, color="#f4e3e3", zorder=0)
    sexenio_lines(ax, 50)
    for name, (keys, colour) in AGENCIES.items():
        s = panel[panel.agency_key.isin(keys)].groupby("year").value_mn_new_pesos.sum()
        s = (100 * s / tot.reindex(s.index)).dropna()
        if name in SECRETARIAS:
            s = s[s.index <= 1983]
        s = s.sort_index()
        lw = 1.6 if colour != GREY else 1.0
        ax.plot(s.index, s.values, color=colour, lw=lw, zorder=3 if colour != GREY else 2)
        x, y = s.index[-1], s.values[-1]
        if name in SECRETARIAS:                 # label both ends of the long grey lines
            short = "Public works" if name.startswith("Public") else "Water resources"
            ax.annotate(short, (s.index[0], s.iloc[0]), xytext=(3, 4 if short == "Public works" else -9),
                        textcoords="offset points", fontsize=8, color="#666666")
            ax.annotate(name, (x, y), xytext=(4, 0), textcoords="offset points", fontsize=8.5, color=DARK, va="center")
        elif name == "Ferrocarriles Nacionales":
            ax.annotate(name, (1933, s.loc[1933] + 1.5), fontsize=8.5, color=DARK)
        elif name == "IMSS":
            ax.annotate(name, (x, y), xytext=(4, 0), textcoords="offset points", fontsize=8.5, color=DARK, va="center")
        else:
            ax.annotate(name, (x, y), xytext=(4, 0), textcoords="offset points", fontsize=9, color=colour, va="center",
                        fontweight="bold")
    nat = rates[(rates.level == 0) & (rates.year.between(1965, 1969))].set_index("year").rate
    ax.text(GAP[0] + 0.4, 45.5, "1964–69 imputed from\nauthorized budgets", fontsize=8, color=RED, va="top")
    ax.text(GAP[0] + 0.4, 39.5, f"execution {nat.min():.2f}–{nat.max():.2f}", fontsize=8, color=RED, va="top")
    ax.set_xlim(1925, 2010)
    ax.set_ylim(0, 48)
    ax.set_ylabel("share of federal public investment, percent")
    ax.set_xlabel("")
    ax.set_xticks(range(1930, 2010, 10))
    fig.text(0.01, 0.01, "Source: Secretaría de la Presidencia (1925–63, 1964–66, 1965–70), SPP (1970–80), INEGI "
                         "(1980–2003). Secretarías shown to 1983 (sector view afterwards).", fontsize=7.5, color="#777777")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
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
