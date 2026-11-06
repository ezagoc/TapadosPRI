"""Maps of the opposition vote by state in every presidential election 1929-2000 (official counts).

Opposition share = 1 - the regime candidate's votes / all registered candidates' votes in the state (1958-1982 the PPS
and PARM endorsed the PRI candidate, and their votes are in his total). Sources (electoralData/): Ramirez Rancano for
1929-1970 except 1940 (Chamber's table, DD), CEDE 1976, Diario de los Debates 1982, Colegio Electoral dictamen 1988,
INE polling-station files 1994 and 2000 summed by state. 1940 has 31 entities in the printed table (no separate Baja
California Sur). 1976: no registered opposition candidate.
Output: OUTPUT_DIR/maps/opposition_vote_by_state.{png,pdf,csv}
"""
import sys
import unicodedata
from pathlib import Path

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import BoundaryNorm, ListedColormap  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import DATA_DIR, OUTPUT_DIR  # noqa: E402

EL = DATA_DIR / "electoralData"
OUT = OUTPUT_DIR / "maps"
OUT.mkdir(parents=True, exist_ok=True)
STATES = ["Aguascalientes", "Baja California", "Baja California Sur", "Campeche", "Coahuila", "Colima", "Chiapas",
          "Chihuahua", "Distrito Federal", "Durango", "Guanajuato", "Guerrero", "Hidalgo", "Jalisco", "Mexico",
          "Michoacan", "Morelos", "Nayarit", "Nuevo Leon", "Oaxaca", "Puebla", "Queretaro", "Quintana Roo",
          "San Luis Potosi", "Sinaloa", "Sonora", "Tabasco", "Tamaulipas", "Tlaxcala", "Veracruz", "Yucatan", "Zacatecas"]
REGIME = {1929: "Pascual Ortiz Rubio", 1934: "Lazaro Cardenas", 1946: "Miguel Aleman", 1952: "Ruiz Cortines",
          1958: "Adolfo Lopez Mateos", 1964: "Gustavo Diaz Ordaz", 1970: "Luis Echeverria Alvarez"}
NOTE = {1940: "Almazán", 1946: "Padilla", 1952: "Henríquez", 1976: "no opposition candidate", 1988: "Cárdenas"}


def plain(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return {"Ciudad de Mexico": "Distrito Federal"}.get(s, s)


rows = []
rr = pd.read_csv(EL / "raw/ramirez_rancano/ramirez_rancano_presidential_by_state_1917_1970.csv")
rr = rr[rr.edon.between(1, 32) & ~rr.candidate.str.contains("TOTAL")]
for y, cand in REGIME.items():
    d = rr[rr.election_year == y].groupby("edon").apply(
        lambda g: pd.Series({"regime": g.loc[g.candidate == cand, "votes"].sum(), "total": g.votes.sum()}), include_groups=False)
    rows.append(d.assign(year=y).reset_index())
cc = pd.read_csv(EL / "crosscheck/presidential_by_state_crosscheck.csv")
for y, src, drop in [(1940, "DD", []), (1976, "CEDE", []), (1982, "DD", ["PRI line"]), (1988, "DICT", [])]:
    d = cc[(cc.year == y) & (cc.source == src) & ~cc.measure.isin(drop) & ~cc.measure.str.startswith("col labelled")]
    d = d.groupby("edon").apply(lambda g: pd.Series({"regime": g.loc[g.measure == "winner", "votes"].sum(),
                                                     "total": g.votes.sum()}), include_groups=False)
    rows.append(d.assign(year=y).reset_index())
p94 = pd.read_csv(EL / "raw/magar_elecRetrns/datosBrutos/result-casillas-fed/fed1994all/Presidente1994.csv", encoding="latin-1")
cand94 = ["PAN", "PRI", "PPS", "PRD", "PFCRN", "PARM", "UNO_PDM", "PT", "PVEM"]
s94 = p94.groupby("ID_ESTADO")[cand94].sum()
rows.append(pd.DataFrame({"edon": s94.index, "regime": s94.PRI.values, "total": s94.sum(axis=1).values, "year": 1994}))
p00 = pd.read_csv(EL / "raw/magar_elecRetrns/data/casillas/pre2000.csv")
cand00 = ["pan-pvem", "PRI", "prd-pt-conve-pas-psn", "pcd", "parm", "ds"]
s00 = p00.groupby("edon")[cand00].sum()
rows.append(pd.DataFrame({"edon": s00.index, "regime": s00.PRI.values, "total": s00.sum(axis=1).values, "year": 2000}))

v = pd.concat(rows, ignore_index=True)
v["state"] = v.edon.astype(int).map(lambda e: STATES[e - 1])
v["opposition"] = 1 - v.regime / v.total
nat = v.groupby("year").apply(lambda g: 1 - g.regime.sum() / g.total.sum(), include_groups=False)
v.sort_values(["year", "edon"]).to_csv(OUT / "opposition_vote_by_state.csv", index=False)
print("national opposition share:", (100 * nat).round(1).to_dict())

g = gpd.read_file(DATA_DIR / "shapefiles/mexico_states.json")
g["state"] = g["name"].map(plain)
assert set(g.state) == set(STATES), set(g.state) ^ set(STATES)
g = g.to_crs(6372)                                       # Mexico ITRF2008 / LCC

bins = [0, 2, 5, 10, 20, 30, 40, 50, 60, 100]
cmap = ListedColormap(plt.get_cmap("YlOrRd")(np.linspace(0.08, 0.95, len(bins) - 1)))
norm = BoundaryNorm(bins, cmap.N)
years = sorted(v.year.unique())
fig, axes = plt.subplots(3, 5, figsize=(16, 10.5))
for ax in axes.ravel():
    ax.set_axis_off()
for ax, y in zip(axes.ravel(), years):
    m = g.merge(v[v.year == y][["state", "opposition"]], on="state", how="left")
    m["pct"] = 100 * m.opposition
    m.plot(ax=ax, color="#d4d4d8", edgecolor="white", linewidth=0.3)
    m.dropna(subset=["pct"]).plot(ax=ax, column="pct", cmap=cmap, norm=norm, edgecolor="white", linewidth=0.3)
    sub = f"{100 * nat[y]:.0f}% national" + (f" · {NOTE[y]}" if y in NOTE else "")
    ax.set_title(f"{y}\n{sub}", fontsize=11, loc="left")
sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
cax = fig.add_axes([0.61, 0.17, 0.34, 0.025])
cb = fig.colorbar(sm, cax=cax, orientation="horizontal", ticks=bins)
cb.set_label("Opposition share of the presidential vote, %", fontsize=11)
fig.text(0.61, 0.09, "Official counts. Opposition = every registered candidate other than the\nregime's (PPS and PARM "
         "votes for the PRI candidate count as regime votes).\nGrey: no separate return for that territory.",
         fontsize=9, color="#52525b", va="top")
fig.suptitle("Votes against the regime's presidential candidate, by state, 1929–2000", fontsize=14, x=0.02,
             y=0.985, ha="left")
fig.subplots_adjust(left=0.01, right=0.99, top=0.90, bottom=0.02, wspace=0.03, hspace=0.22)
for ext in ("png", "pdf"):
    fig.savefig(OUT / f"opposition_vote_by_state.{ext}", dpi=200)
print("saved", OUT / "opposition_vote_by_state.png")
