"""
07_build_state_investment_panel.py

Build the annual STATE × YEAR panel of realized federal public investment,
1959–2003 — the distributive outcome of the project.

Sources (all "inversión pública federal realizada", state totals):
  1959–1963  Inversión Pública Federal 1925–1963, institution × state grand totals
             (federal_investment_long.csv, 01_extract_investment_tables.py)
  1964       Inversión Pública Federal 1964, purpose × state totals
             (federal_investment_purpose_state_1964_long.csv)
  1965–1969  Inversión Pública Federal 1965–1970, purpose × state totals
             (federal_investment_purpose_state_long.csv, 04_*)
  1970–2003  SPP / INEGI "El ingreso y el gasto público en México" editions
             (inegi_state_investment_long.csv, 06_*)
No state-level source exists for 1940–1958 (the 1925–1963 book is national-only there).

For years reported by several INEGI editions, the MOST RECENT edition whose table adds
up to its printed total is used (later editions carry revised figures); the other
balanced editions are compared (max absolute difference in state shares) and reported.

Measures per state-year:
  nominal_mn_new_pesos   millions of new pesos (1 new peso = 1,000 old pesos)
  real_mn_1960_pesos     millions of 1960 pesos (CPI deflator, 1960 = 100)
  share_of_states        state / sum over the 32 states (robust to the
                         "no distribuible geográficamente" row, 20–24% in 1983–84)

Outputs: INVESTMENT_DIR/state_investment_panel.csv, state_investment_sources.csv
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

CODE_DIR = Path(__file__).resolve().parents[1]
if str(CODE_DIR) not in sys.path:
    sys.path.append(str(CODE_DIR))

from config import INVESTMENT_DIR, PRICE_DEFLATOR_CSV, STATE_LOOKUP_NORM, strip_accents

OUT_PANEL = INVESTMENT_DIR / "state_investment_panel.csv"
OUT_SOURCES = INVESTMENT_DIR / "state_investment_sources.csv"

# most recent edition first (later editions revise earlier figures)
INEGI_PRIORITY = ["igp_2004", "igp_2001", "igp_2000", "igp_1999", "igp_1993",
                  "igp_1987", "igp_1986", "spp_1970_1980"]


def canon(name) -> str | None:
    t = strip_accents(str(name).lower()).strip()
    return STATE_LOOKUP_NORM.get(t)


def old_books() -> pd.DataFrame:
    """1959–1969 state totals, in millions of OLD pesos."""
    a = pd.read_csv(INVESTMENT_DIR / "federal_investment_long.csv")
    a = a[a.row_type == "grand_total"].assign(source="ipf_1925_1963")
    b = pd.read_csv(INVESTMENT_DIR / "federal_investment_purpose_state_1964_long.csv")
    b = b[(b.row_type == "grand_total") & (b.geography_type == "state")].assign(source="ipf_1964")
    c = pd.read_csv(INVESTMENT_DIR / "federal_investment_purpose_state_long.csv")
    # cuadros 19–23 are ANNUAL (they sum to the 1965–69 aggregate, cuadro 18); their
    # period_start is mislabelled 1965 in 04_*, so select on cuadro, not on the period
    c = c[(c.row_type == "grand_total") & (c.geography_type == "state")
          & c.cuadro.isin([19, 20, 21, 22, 23])].assign(source="ipf_1965_1970")
    out = pd.concat([d[["source", "year", "state", "investment_mdp"]] for d in (a, b, c)])
    out["state"] = out["state"].map(canon)
    out["year"] = out["year"].astype(int)
    out["nominal_mn_new_pesos"] = out.pop("investment_mdp") / 1000
    return out


def inegi() -> tuple[pd.DataFrame, pd.DataFrame]:
    """1970–2003: pick, per year, the most recent balanced edition."""
    long = pd.read_csv(INVESTMENT_DIR / "inegi_state_investment_long.csv")
    val = pd.read_csv(INVESTMENT_DIR / "inegi_state_investment_validation.csv")
    long["edition"] = long.source.str.replace(r"(_p\d+|[ab])$", "", regex=True)
    val["edition"] = val.source.str.replace(r"(_p\d+|[ab])$", "", regex=True)
    ok = val[val.balanced]
    states = long[~long.entity.isin(["TOTAL", "NOT_DISTRIBUTABLE", "ABROAD"])]
    shares = (states.assign(share=lambda d: d.value_printed /
                            d.groupby(["source", "year"]).value_printed.transform("sum")))

    chosen, report = [], []
    for y, g in ok.groupby("year"):
        eds = sorted(g.edition.unique(), key=INEGI_PRIORITY.index)
        pick = eds[0]
        src = g[g.edition == pick].source.iloc[0]
        sh = shares[(shares.year == y)].pivot_table(index="entity", columns="edition",
                                                    values="share")
        others = [e for e in eds[1:] if e in sh]
        maxdiff = max((sh[pick] - sh[e]).abs().max() for e in others) if others else None
        tot = long[(long.source == src) & (long.year == y) & (long.entity == "TOTAL")]
        nd = long[(long.source == src) & (long.year == y) & (long.entity == "NOT_DISTRIBUTABLE")]
        report.append({"year": y, "source": src, "balanced_editions": ";".join(eds),
                       "max_share_diff_vs_other_editions": maxdiff,
                       "not_distributable_share": (nd.value_mn_new_pesos.sum() /
                                                   tot.value_mn_new_pesos.sum()) if len(tot) else None})
        chosen.append(states[(states.source == src) & (states.year == y)])
    ch = pd.concat(chosen).rename(columns={"entity": "state"})
    ch = ch[["source", "year", "state", "value_mn_new_pesos"]].rename(
        columns={"value_mn_new_pesos": "nominal_mn_new_pesos"})
    return ch, pd.DataFrame(report)


def main():
    old = old_books()
    new, report = inegi()
    panel = pd.concat([old, new[new.year >= 1970]], ignore_index=True)
    assert panel.state.notna().all(), "unmapped state name"
    assert not panel.duplicated(["state", "year"]).any()

    defl = pd.read_csv(PRICE_DEFLATOR_CSV).set_index("year")["deflator"]
    panel["real_mn_1960_pesos"] = (panel.nominal_mn_new_pesos * 1000 * 100 /
                                   panel.year.map(defl)).round(3)
    panel["share_of_states"] = (panel.nominal_mn_new_pesos /
                                panel.groupby("year").nominal_mn_new_pesos.transform("sum")).round(5)
    panel = panel.sort_values(["year", "state"])
    panel.to_csv(OUT_PANEL, index=False)

    old_rep = (old.groupby(["year", "source"]).size().reset_index(name="n_states")
               .drop(columns="n_states"))
    pd.concat([old_rep, report], ignore_index=True).to_csv(OUT_SOURCES, index=False)

    print(f"{panel.state.nunique()} states × {panel.year.nunique()} years "
          f"({panel.year.min()}–{panel.year.max()}) → {OUT_PANEL}")
    nat = panel.groupby("year").agg(source=("source", "first"),
                                    real_total_mn_1960=("real_mn_1960_pesos", "sum"),
                                    DF_share=("share_of_states",
                                              lambda s: s[panel.loc[s.index, "state"] == "Federal District"].sum()))
    print(nat.round(3).to_string())
    print("\nCross-edition agreement (max |share diff|) and not-distributable share:")
    print(report.round(4).to_string(index=False))


if __name__ == "__main__":
    main()
