"""
10_build_agency_investment_panel.py

Build the AGENCY × YEAR panel of realized federal public investment, 1925–2000:

  1925–1963  Inversión Pública Federal 1925–1963, Cuadros 2 and 11 (08_*)
  1970–2000  SPP 1970–80 Cuadros II.7 / II.9, INEGI "El ingreso y el gasto público en
             México" 1987, 1993, 1999, 2001 editions (09_*): secretarías/dependencias and
             organismos y empresas controlados presupuestalmente
  Gaps: 1964–1969 (only authorized/programmed investment by agency exists), 1981 (the
  1986 edition's 1980–85 agency tables are not extracted yet) and dependencias 1999–2000
  (the 2001 edition's 4-level functional table is excluded). Glued footnote letters in
  SPP labels ('Turismoi', 'PIDERj') are tolerated by substring matching in CROSSWALK.

For years reported by several editions the most recent edition is kept. Every row
carries the printed label, a stable `agency_key` and an institutional `lineage` that
follows mergers and renamings (e.g. SAG + SRH → SARH → SAGAR share lineage
'agriculture_water'), so an institution can be followed over time; unmatched labels
keep their normalised label as key.

Blocks (column `block`): 'dependencias' (secretarías' own investment, 1925–1983),
'paraestatal' (decentralized agencies and state companies, entity level, 1925–2000) and
'ramo_sector' (1984–1998: investment by coordinating secretaría INCLUDING its sectorised
parastatals — a different lens; never add it to 'paraestatal').

Measures: nominal millions of NEW pesos; real millions of 1960 pesos (1959+ only —
the CPI deflator starts in 1959); share of that year's block total — the scale-free
measure to use across the whole period.

Outputs (INVESTMENT_DIR): agency_investment_panel.csv
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

CODE_DIR = Path(__file__).resolve().parents[1]
if str(CODE_DIR) not in sys.path:
    sys.path.append(str(CODE_DIR))

from config import INVESTMENT_DIR, PRICE_DEFLATOR_CSV, strip_accents

OUT = INVESTMENT_DIR / "agency_investment_panel.csv"
EDITION_ORDER = ["igp01", "igp99", "igp93", "igp87", "spp"]      # most recent first

# (regex on the normalised label, agency_key, lineage)
CROSSWALK = [
    (r"petroleos mexicanos|^pemex", "pemex", "pemex"),
    (r"^cfe\b", "cfe", "electricity"),
    (r"^c?lyfc\b|^cl y fc", "lyfc", "electricity"),
    (r"^ferronales|^fnm\b", "fnm", "railroads"),
    (r"^imss\b", "imss", "social_security"),
    (r"^issste\b", "issste", "social_security"),
    (r"^capufe\b", "capufe", "transport"),
    (r"^asa\b", "asa", "transport"),
    (r"^fertimex\b", "fertimex", "fertilizers"),
    (r"^conasupo\b", "conasupo", "food_distribution"),
    (r"^sidermex\b", "sidermex", "steel"),
    (r"^banobras\b|hipotecario urbano y de obras publicas", "banobras", "development_banks"),
    (r"nacional financiera|^nafin", "nafin", "development_banks"),
    (r"juntas federales de mejoras materiales", "juntas_mejoras", "regional_programs"),
    (r"compania electrica chapala", "chapala_electric", "electricity"),
    (r"almacenes nacionales de deposito", "andsa", "food_distribution"),
    (r"ciudad universitaria", "ciudad_universitaria", "education"),
    (r"comision federal de electricidad", "cfe", "electricity"),
    (r"luz y fuerza del centro", "lyfc", "electricity"),
    (r"ferrocarriles nacionales", "fnm", "railroads"),
    (r"ferrocarril del pacifico", "fc_pacifico", "railroads"),
    (r"chihuahua al pacifico", "fc_chihuahua_pacifico", "railroads"),
    (r"unidos del sureste", "fc_sureste", "railroads"),
    (r"sonora baja california", "fc_sonora_bc", "railroads"),
    (r"instituto mexicano del seguro social", "imss", "social_security"),
    (r"seguridad y servicios sociales", "issste", "social_security"),
    (r"caminos y puentes federales", "capufe", "transport"),
    (r"aeropuertos y servicios auxiliares", "asa", "transport"),
    (r"aeronaves de mexico", "aeromexico", "transport"),
    (r"subsistencias populares", "conasupo", "food_distribution"),
    (r"altos hornos", "ahmsa", "steel"),
    (r"lazaro cardenas las truchas|sicartsa", "sicartsa", "steel"),
    (r"siderurgica nacional", "sidena", "steel"),
    (r"guanos y fertilizantes|fertilizantes mexicanos", "fertimex", "fertilizers"),
    (r"^secretaria de agricultura y ganaderia|^secretaria de agricultura y fomento", "sag", "agriculture_water"),
    (r"^secretaria de recursos hidraulicos", "srh", "agriculture_water"),
    (r"agricultura y recursos hidraulicos", "sarh", "agriculture_water"),
    (r"agricultura ganaderia y desarrollo rural", "sagar", "agriculture_water"),
    (r"comunicaciones y obras publicas", "scop", "communications_works"),
    (r"^secretaria de obras publicas", "sop", "communications_works"),
    (r"comunicaciones y transportes", "sct", "communications_works"),
    (r"asentamientos humanos y obras publicas", "sahop", "urban_development"),
    (r"desarrollo urbano y ecologia", "sedue", "urban_development"),
    (r"desarrollo social", "sedesol", "urban_development"),
    (r"educacion publica", "sep", "education"),
    (r"salubridad y asistencia|^secretaria de salud|^salud", "ssa", "health"),
    (r"defensa nacional|guerra y marina", "sedena", "defense"),
    (r"^secretaria de marina|^marina", "semar", "navy"),
    (r"hacienda y credito publico", "shcp", "finance"),
    (r"programacion y presupuesto", "spp", "planning"),
    (r"gobernacion", "segob", "interior"),
    (r"relaciones exteriores", "sre", "foreign_affairs"),
    (r"reforma agraria|asuntos agrarios", "sra", "agrarian"),
    (r"^secretaria de turismo|departamento de turismo|^turismo", "sectur", "tourism"),
    (r"trabajo y prevision social", "stps", "labor"),
    (r"patrimonio y fomento industrial|patrimonio nacional|energia minas", "sepafin", "energy_industry"),
    (r"comercio", "secofi", "commerce"),
    (r"pesca", "sepesca", "fisheries"),
    (r"distrito federal", "ddf", "federal_district"),
    (r"procuraduria general", "pgr", "justice"),
    (r"industria militar", "dim", "defense"),
    (r"^pider", "pider", "regional_programs"),
    (r"desarrollo regional", "desarrollo_regional", "regional_programs"),
    (r"loteria nacional", "loteria", "other"),
    (r"superacion de la pobreza|solidaridad", "solidaridad_programs", "regional_programs"),
    (r"^energia", "energia_sector", "energy_industry"),
]


def norm(s) -> str:
    s = strip_accents(str(s).lower())
    s = re.sub(r"[^a-z ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def key_lineage(label: str) -> tuple[str, str | None]:
    n = norm(label)
    for pat, key, lin in CROSSWALK:
        if re.search(pat, n):
            return key, lin
    return n, None


def early() -> pd.DataFrame:
    d = pd.read_csv(INVESTMENT_DIR / "agency_investment_1925_1963_long.csv")
    d = d[d.row_type == "agency"].copy()
    d["block"] = d.sector.map({"gobierno_federal": "dependencias",
                               "organismos_descentralizados": "paraestatal",
                               "empresas_participacion_estatal": "paraestatal"})
    d["source"] = d.source.str.replace(r"_p\d+[LR]$", "", regex=True)
    d["value_mn_new_pesos"] = d.value_printed / 1000
    return d[["source", "year", "block", "sector", "label", "value_mn_new_pesos"]]


def late() -> pd.DataFrame:
    d = pd.read_csv(INVESTMENT_DIR / "agency_investment_inegi_long.csv")
    d = d[d.in_panel & (d.level > 0)].copy()
    # keep the agency level: the deepest rows of each block (groups are subtotals)
    d = d[d["level"] == d.groupby("table")["level"].transform("max")]
    d["edition"] = d.table.str.extract(r"^(spp|igp\d+)")[0]
    d["rank"] = d.edition.map({e: i for i, e in enumerate(EDITION_ORDER)})
    # the 1987 edition's secretarías table switches concept in 1984: 1982–83 are the
    # secretarías' own investment (SEMIP 0.1–0.3), 1984+ the sectorised view (SEMIP
    # 881, i.e. including PEMEX/CFE) — so 1982–83 belong to 'dependencias'
    d.loc[(d.block == "ramo_sector") & (d.year <= 1983), "block"] = "dependencias"
    d["sector"] = d.block
    d = d.rename(columns={"table": "source"})
    return d[["source", "rank", "year", "block", "sector", "label", "value_mn_new_pesos",
              "source_note", "agreement"]]


def main():
    e, l = early(), late()
    for d in (e, l):
        kl = d.label.map(key_lineage)
        d["agency_key"], d["lineage"] = kl.str[0], kl.str[1]
    # one edition per (agency, year): the most recent
    l = l.sort_values("rank").drop_duplicates(["agency_key", "year", "block"])
    panel = pd.concat([e.assign(agreement=None, source_note=None), l.drop(columns="rank")],
                      ignore_index=True)
    panel = panel.dropna(subset=["value_mn_new_pesos"])
    panel = panel.groupby(["agency_key", "year", "block"], as_index=False).agg(
        label=("label", "first"), lineage=("lineage", "first"), sector=("sector", "first"),
        source=("source", "first"), value_mn_new_pesos=("value_mn_new_pesos", "sum"),
        source_note=("source_note", "first"))
    defl = pd.read_csv(PRICE_DEFLATOR_CSV).set_index("year")["deflator"]
    panel["real_mn_1960_pesos"] = panel.value_mn_new_pesos * 1000 * 100 / panel.year.map(defl)
    # shares within each block: 'ramo_sector' (1982+) is a sector view that already
    # includes parastatal investment, so blocks must not be summed together
    panel["share_of_year_total"] = panel.value_mn_new_pesos / \
        panel.groupby(["year", "block"]).value_mn_new_pesos.transform("sum")
    panel = panel.sort_values(["year", "block", "value_mn_new_pesos"], ascending=[True, True, False])
    panel.to_csv(OUT, index=False)

    print(f"{panel.agency_key.nunique()} agencies × {panel.year.nunique()} years "
          f"({panel.year.min()}–{panel.year.max()}) → {OUT}")
    print("years covered:", sorted(panel.year.unique()))
    print("\nlineage coverage (share of investment with a lineage):",
          round(panel.dropna(subset=["lineage"]).value_mn_new_pesos.sum() /
                panel.value_mn_new_pesos.sum(), 3))
    top = panel[panel.block == "paraestatal"].groupby("year").apply(
        lambda g: ", ".join(g.nlargest(3, "value_mn_new_pesos").agency_key))
    print("\nlargest 3 parastatals by year (every 5 years):")
    print(top[top.index % 5 == 0].to_string())


if __name__ == "__main__":
    main()
