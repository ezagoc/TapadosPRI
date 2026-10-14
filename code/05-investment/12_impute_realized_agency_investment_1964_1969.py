"""
12_impute_realized_agency_investment_1964_1969.py

Fill the 1964–1969 gap of the agency panel: realized investment by agency does not exist
for those years (the Secretaría de la Presidencia books give agencies only as AUTHORIZED /
PROGRAMMED investment), so realized is IMPUTED as

    realized(agency, year) = authorized(agency, year) × execution rate(purpose of the agency, year)

Execution rates (realized / programmed) come from the same book, which prints both the
programmed (Cuadro 1) and the realized (Cuadro 16) investment by OBJETO DEL GASTO
(purpose: petróleo, electricidad, siderurgia, carreteras, ferrocarriles, escuelas,
hospitales, vivienda, agricultura, …) for every year 1965–1969. Each agency is mapped to
the purpose it serves (PURPOSE_MAP; e.g. PEMEX → petróleo, CFE → electricidad, SOP →
carreteras, CAPFCE → escuelas, IMSS → hospitales); agencies without a clear purpose get
the national rate of the year. No realized figure of any kind exists for 1964: the level
follows the official series (INEGI, Estadísticas Históricas 2014, Cuadros 16.25 and
16.27, carry the authorized 17 436 as the 1964 value of the realized series, i.e. a
national rate of 1) and the composition uses the average 1965–69 relative execution of
each purpose (chosen because the leave-one-year-out check below shows it predicts the
realized purpose mix better than the authorized mix; see execution_rates_checks.csv).
IMSS 1964 is printed as realized in the book itself (footnote 4) and keeps rate 1.

Checks (→ execution_rates_checks.csv): stability of the purpose rates across years; a
leave-one-year-out test of three rules on the realized purpose totals of 1965–69
(authorized mix with the year's national rate; cross-year purpose rates; cross-year
relative purpose pattern × the year's national rate); and the 1970 agency-level
comparison of the programmed (Cuadro 15) and the SPP 1970 realized secretarías (not used:
the SPP 1970 figures of the three largest secretarías equal the programmed ones to 0.1%).

Inputs (INVESTMENT_DIR): agency_investment_authorized_1964_1969_long.csv,
investment_purpose_programmed_realized_1964_1970.csv (11_*), agency_investment_inegi_long.csv (09_*).
Outputs (INVESTMENT_DIR): execution_rates.csv, execution_rates_checks.csv,
agency_investment_imputed_1964_1969_long.csv (consumed by 10_build_agency_investment_panel.py).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

CODE_DIR = Path(__file__).resolve().parents[1]
if str(CODE_DIR) not in sys.path:
    sys.path.append(str(CODE_DIR))

from config import INVESTMENT_DIR, strip_accents  # noqa: E402

AUTH = INVESTMENT_DIR / "agency_investment_authorized_1964_1969_long.csv"
PURPOSE = INVESTMENT_DIR / "investment_purpose_programmed_realized_1964_1970.csv"
INEGI = INVESTMENT_DIR / "agency_investment_inegi_long.csv"
OUT_RATES = INVESTMENT_DIR / "execution_rates.csv"
OUT_CHECKS = INVESTMENT_DIR / "execution_rates_checks.csv"
OUT_IMPUTED = INVESTMENT_DIR / "agency_investment_imputed_1964_1969_long.csv"

GAP_YEARS = [1964, 1965, 1966, 1967, 1968, 1969]
# source table per gap year: Book B (1970 edition) throughout — same concept, cross-checked
# against Book A for 1964–66 (identical after documented consolidations, see 11_*)
SOURCE_TABLE = {1964: "b70_cI", 1965: "b70_c10", 1966: "b70_c11", 1967: "b70_c12", 1968: "b70_c13", 1969: "b70_c14"}
# National execution rate applied to 1964 (no realized figure exists; official-series convention)
RATE_1964_NATIONAL = 1.0
# INEGI, Estadísticas Históricas de México 2014, Cuadro 16.27: realized 1970 by destination
# (source Secretaría de la Presidencia), used only for the 1970 group-level check
EHM_1970 = {"fomento agropecuario y pesquero": 3921, "industrial": 11097, "transportes y comunicaciones": 5525,
            "bienestar social": 8196, "equipos e instalaciones para administracion y defensa": 466, "total": 29205}

GROUPS = {"industrial": ["petroleo y petroquimica", "electricidad", "siderurgia", "otras inversiones"],
          "bienestar social": ["obras de servicio urbano y rural", "escuelas", "hospitales y centros asistenciales",
                               "vivienda", "otras inversiones"],
          "transportes y comunicaciones": ["carreteras", "ferrocarriles", "comunicaciones aereas", "telecomunicaciones",
                                           "obras maritimas", "otras inversiones"],
          "fomento agropecuario y pesquero": ["agricultura", "ganaderia", "forestal", "pesca", "otras inversiones"],
          "equipos e instalaciones para administracion y defensa": []}

# agency (regex on the normalised label) → (group, item); item None = the group's rate.
# Order matters: the first match wins. Anything unmatched → national rate of the year.
PURPOSE_MAP = [
    (r"petroleos mexicanos", "industrial", "petroleo y petroquimica"),
    (r"industria petroquimica nacional|tetraetilo", "industrial", "petroleo y petroquimica"),
    (r"comision federal de electricidad|luz y fuerza|electrica|hidroelectrica", "industrial", "electricidad"),
    (r"altos hornos|siderurgica nacional|siderurgica", "industrial", "siderurgia"),
    (r"ferrocarril", "transportes y comunicaciones", "ferrocarriles"),
    (r"secretaria de obras publicas|caminos y puentes", "transportes y comunicaciones", "carreteras"),
    (r"aeropuertos|aeronaves|radio aeronautica", "transportes y comunicaciones", "comunicaciones aereas"),
    (r"secretaria de marina|puertos libres|astilleros", "transportes y comunicaciones", "obras maritimas"),
    (r"secretaria de comunicaciones y transportes", "transportes y comunicaciones", None),
    (r"recursos hidraulicos|secretaria de agricultura|almacenes nacionales|subsistencias populares|"
     r"banco nacional de credito|banco nacional agropecuario|banco agr|aseguradora nacional agricola|"
     r"impulsora de la cuenca|patronato del maguey|instituto mexicano del cafe|azucar|ingenio|empacadora",
     "fomento agropecuario y pesquero", "agricultura"),
    (r"pesca|pesqueros", "fomento agropecuario y pesquero", "pesca"),
    (r"productos forestales|servicios forestales|union forestal", "fomento agropecuario y pesquero", "forestal"),
    (r"construccion de escuelas|educacion publica|ciudad universitaria|politecnico|ensenanza tecnica|"
     r"antropologia|bellas artes|libros de texto|investigaciones tecnologicas|juventud",
     "bienestar social", "escuelas"),
    (r"seguro social|seguridad y servicios sociales|salubridad|hospital|cardiologia|nutricion|materno infantil|"
     r"asistencia a la ninez|proteccion a la infancia|indigenista|indigena", "bienestar social",
     "hospitales y centros asistenciales"),
    (r"instituto nacional de la vivienda|desarrollo de la comunidad rural y de la vivienda", "bienestar social", "vivienda"),
    (r"distrito federal|transporte colectivo|juntas federales|hipotecario urbano|obras y servicios publicos|"
     r"programa nacional fronterizo|territorio de", "bienestar social", "obras de servicio urbano y rural"),
    (r"defensa nacional|industria militar|gobernacion|hacienda|relaciones exteriores|patrimonio nacional|"
     r"trabajo y prevision|presidencia|asuntos agrarios|turismo|procuraduria|banco de mexico|loteria|"
     r"talleres graficos|talleres tipograficos|comision nacional bancaria|comision nacional de valores|"
     r"pensiones militares|subsidios|industria y comercio|banco nacional del ejercito|ahorro nacional|"
     r"comercio exterior|nacional financiera|aseguradora|hipotecaria|monte de piedad|banco nacional de fomento|"
     r"banco del pequeno comercio|cinematografico|financiera nacional azucarera|fondo de garantia|"
     r"estudios del territorio nacional|comision de operacion y fomento",
     "equipos e instalaciones para administracion y defensa", None),
    (r"fertilizantes|guanos|fomento minero|minera|real del monte|zincamex|azufr|fosforitas|atenquique|papel|"
     r"diesel|hules|cordemex|maderas|chapas|carros de ferrocarril|textil|telas|envases|vestuario|sales y alcalis|"
     r"energia nuclear|recursos naturales|laboratorios nacionales|instalaciones inmobiliarias|bienes raices|"
     r"inmobiliaria|abastos|quimico|refrigeradora|operadora de teatros|gas de queretaro|derivados|"
     r"industrial", "industrial", "otras inversiones"),
]


def norm(s) -> str:
    s = strip_accents(str(s).lower())
    s = re.sub(r"(?<=[a-z])-\s+(?=[a-z])", "", s)
    s = re.sub(r"[^a-z ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def purpose_of(label_norm: str) -> tuple[str | None, str | None]:
    for pat, grp, item in PURPOSE_MAP:
        if re.search(pat, label_norm):
            return grp, item
    return None, None


# ── execution rates by purpose ───────────────────────────────────────────────
def purpose_rates(purpose: pd.DataFrame) -> pd.DataFrame:
    """rate = realized / programmed by (level, group, item, year), 1965–1969; 1970 at the
    national and group level from EHM 16.27; relative rate = rate / national rate."""
    p = purpose[purpose.table.isin(["b70_c1", "b70_c16"]) & (purpose.year != "sum_1965_1970")].copy()
    p["year"] = p.year.astype(int)
    p["item"] = np.where(p.level == 2, p.label_norm, "")
    p["group"] = np.where(p.level == 0, "total", p.group)
    w = p.pivot_table(index=["level", "group", "item"], columns=["concept", "year"], values="value_printed",
                      aggfunc="first")
    rows = []
    for (lvl, grp, item), r in w.iterrows():
        item = item or None
        for y in range(1965, 1971):
            prog = r.get(("programmed", y), np.nan)
            real = r.get(("realized", y), np.nan)
            if y == 1970:                                   # Cuadro 16's 1970 column is programmed
                real = EHM_1970.get(grp if lvl <= 1 else None, np.nan) if lvl <= 1 else np.nan
            rows.append({"level": int(lvl), "group": grp, "item": item, "year": y,
                         "programmed_mn_old_pesos": prog, "realized_mn_old_pesos": real,
                         "rate": real / prog if prog and pd.notna(real) and pd.notna(prog) and prog > 0 else np.nan,
                         "realized_source": "EHM 2014 Cuadro 16.27" if y == 1970 else "Book B Cuadro 16"})
    d = pd.DataFrame(rows)
    nat = d[d.level == 0].set_index("year").rate
    d["national_rate"] = d.year.map(nat)
    d["relative_rate"] = d.rate / d.national_rate
    return d


def stability(rates: pd.DataFrame) -> pd.DataFrame:
    r = rates[(rates.year <= 1969) & rates.rate.notna()]
    g = r.groupby(["level", "group", "item"], dropna=False).agg(
        n_years=("rate", "size"), mean_rate=("rate", "mean"), sd_rate=("rate", "std"),
        min_rate=("rate", "min"), max_rate=("rate", "max"), mean_relative=("relative_rate", "mean"),
        sd_relative=("relative_rate", "std"), mean_programmed=("programmed_mn_old_pesos", "mean")).reset_index()
    g["cv_rate"] = g.sd_rate / g.mean_rate
    return g.sort_values(["level", "mean_programmed"], ascending=[True, False])


def loyo(rates: pd.DataFrame) -> pd.DataFrame:
    """Leave-one-year-out: predict the realized value of every purpose item in year t from
    its programmed value with (A) the national rate of t (= authorized mix), (B) the
    item's mean rate in the other years, (C) the national rate of t × the item's mean
    RELATIVE rate in the other years. Errors weighted by realized value; also the error in
    the realized mix (sum of |pp| over items)."""
    it = rates[(rates.level == 2) & (rates.year <= 1969) & rates.rate.notna()].copy()
    out = []
    for t in range(1965, 1970):
        cur = it[it.year == t].set_index(["group", "item"])
        oth = it[it.year != t].groupby(["group", "item"]).agg(r=("rate", "mean"), rel=("relative_rate", "mean"))
        nat = rates[(rates.level == 0) & (rates.year == t)].rate.iloc[0]
        for method in ("A_authorized_mix", "B_item_rate_other_years", "C_relative_pattern_other_years"):
            pred = {}
            for k, r in cur.iterrows():
                prog = r.programmed_mn_old_pesos
                if method.startswith("A"):
                    pred[k] = prog * nat
                elif method.startswith("B"):
                    pred[k] = prog * (oth.r.get(k, nat) if k in oth.index else nat)
                else:
                    pred[k] = prog * nat * (oth.rel.get(k, 1.0) if k in oth.index else 1.0)
            P = pd.Series(pred); R = cur.realized_mn_old_pesos
            wape = (P - R).abs().sum() / R.sum()
            mix = ((P / P.sum()) - (R / R.sum())).abs().sum() * 100 / 2    # pp of the total reallocated
            out.append({"year": t, "method": method, "n_items": len(R), "wape": round(wape, 4),
                        "mix_error_pp": round(mix, 2), "total_pred": round(P.sum(), 1), "total_real": round(R.sum(), 1)})
    d = pd.DataFrame(out)
    summ = d.groupby("method").agg(wape=("wape", "mean"), mix_error_pp=("mix_error_pp", "mean")).reset_index()
    summ["year"] = "mean 1965-69"
    return pd.concat([d, summ], ignore_index=True)


# ── 1970 agency-level comparison (programmed Cuadro 15 vs SPP 1970 realized) ─
SPP_1970_MAP = {   # SPP Cuadro II.7 label (normalised prefix) → Cuadro 15 labels (normalised prefixes)
    "secretaria de agricultura y recursos hidraulicos": ["secretaria de agricultura y ganaderia", "secretaria de recursos hidraulicos"],
    "secretaria de asentamientos humanos y obras publicas": ["secretaria de obras publicas"],
    "secretaria de comunicaciones y transportes": ["secretaria de comunicaciones y transportes"],
    "secretaria de educacion publica": ["secretaria de educacion publica"],
    "secretaria de gobernacion": ["secretaria de gobernacion"],
    "secretaria de hacienda": ["secretaria de hacienda"],
    "secretaria de comercio": ["secretaria de industria y comercio"],
    "secretaria de marina": ["secretaria de marina"],
    "secretaria de salubridad": ["secretaria de salubridad"],
    "secretaria de patrimonio y fomento industrial": ["secretaria del patrimonio nacional"],
    "secretaria de trabajo": ["secretaria del trabajo"],
    "secretaria de la defensa nacional": ["secretaria de la defensa nacional"],
    "secretaria de la reforma agraria": ["departamento de asuntos agrarios"],
    "secretaria de turismo": ["departamento de turismo"],
    "procuraduria general": ["procuraduria general"],
    "departamento de la industria militar": ["departamento de la industria militar"],
    "otros": ["departamento del distrito federal", "territorio de baja california", "territorio de quintana roo"],
}
GROUP_OF_SPP = {"secretaria de agricultura y recursos hidraulicos": "fomento agropecuario y pesquero",
                "secretaria de asentamientos humanos y obras publicas": "transportes y comunicaciones",
                "secretaria de comunicaciones y transportes": "transportes y comunicaciones",
                "secretaria de educacion publica": "bienestar social", "secretaria de marina": "transportes y comunicaciones",
                "secretaria de salubridad": "bienestar social", "otros": "bienestar social"}


def check_1970(auth: pd.DataFrame, rates: pd.DataFrame) -> pd.DataFrame:
    spp = pd.read_csv(INEGI)
    spp = spp[(spp.table == "spp_II7y") & (spp.year == 1970) & (spp.level == 2)]
    c15 = auth[(auth.table == "b70_c15") & (auth.row_type == "agency")]
    nat = rates[(rates.level == 0) & (rates.year == 1970)].rate.iloc[0]
    grp = rates[(rates.level == 1) & (rates.year == 1970)].set_index("group").rate
    rows = []
    for spp_lab, parts in SPP_1970_MAP.items():
        real = spp[spp.label_norm.str.startswith(spp_lab)].value_printed.sum(min_count=1)
        prog = sum(c15[c15.label_norm.str.startswith(p)].value_printed.sum(min_count=1) or 0 for p in parts)
        g = GROUP_OF_SPP.get(spp_lab, "equipos e instalaciones para administracion y defensa")
        rows.append({"spp_label": spp_lab, "programmed_c15": prog, "realized_spp_1970": real,
                     "rate": real / prog if prog else np.nan, "group": g, "pred_national": prog * nat,
                     "pred_group": prog * grp.get(g, np.nan)})
    d = pd.DataFrame(rows)
    d["abs_err_national"] = (d.pred_national - d.realized_spp_1970).abs()
    d["abs_err_group"] = (d.pred_group - d.realized_spp_1970).abs()
    return d


# ── imputation ───────────────────────────────────────────────────────────────
def impute(auth: pd.DataFrame, rates: pd.DataFrame, use_1964_pattern: bool) -> pd.DataFrame:
    item_rate = rates[(rates.level == 2)].set_index(["group", "item", "year"]).rate
    grp_rate = rates[(rates.level == 1)].set_index(["group", "year"]).rate
    nat_rate = rates[(rates.level == 0)].set_index("year").rate
    rel = rates[(rates.year <= 1969) & (rates.level >= 1)].groupby(["level", "group", "item"], dropna=False).relative_rate.mean()
    out = []
    for y in GAP_YEARS:
        g = auth[(auth.table == SOURCE_TABLE[y]) & (auth.row_type == "agency") & auth.value_printed.notna()]
        for _, r in g.iterrows():
            ln = norm(r.label)
            grp, item = purpose_of(ln)
            if y == 1964 and ln.startswith("instituto mexicano del seguro social"):
                # Book A Cuadro 1 footnote 4: the IMSS figure is the investment REALIZED as reported
                # by the institute (oficio 36/77, 18 May 1965): 'hospitales, centros asistenciales y
                # unidades de habitación' (Cuadro 3), financed by domestic credit (Book B annex IV).
                # It is 2.4× IMSS's 1963 realized and 7.6× its 1965 authorization; INEGI's 1964
                # 'hospitales' total (2 528) carries it. Kept as printed, flagged.
                rate, basis = 1.0, ("printed as realized, IMSS-reported (Book A Cuadro 1 note 4: hospitals, care "
                                    "centres and housing units; 2.4x its 1963 realized) — use with caution")
            elif y == 1964:
                k = (2, grp, item) if item else (1, grp, None)
                rr = rel.get(k, np.nan) if (grp and use_1964_pattern) else np.nan
                rate = RATE_1964_NATIONAL * (rr if pd.notna(rr) else 1.0)
                basis = ("national 1964 (official-series convention) × mean 1965-69 relative rate of "
                         + (f"item {item}" if item else f"group {grp}")) if pd.notna(rr) else "national 1964 (official-series convention)"
            else:
                rate, basis = np.nan, None
                if item is not None and item != "otras inversiones":
                    rate = item_rate.get((grp, item, y), np.nan)
                    basis = f"item: {item} ({y})"
                if pd.isna(rate) and grp is not None:
                    rate = grp_rate.get((grp, y), np.nan)
                    basis = f"group: {grp} ({y})" + (" (residual item)" if item == "otras inversiones" else "")
                if pd.isna(rate):
                    rate, basis = nat_rate[y], f"national ({y})"
            out.append({"source": r.table, "book": r.book, "year": y, "block": r.block, "sector": r.sector,
                        "label": re.sub(r"(?<=\w)-\s+(?=\w)", "", str(r.label)).strip(" ."), "label_printed": r.label,
                        "label_norm": ln, "purpose_group": grp, "purpose_item": item,
                        "authorized_mn_old_pesos": r.value_printed, "execution_rate": rate, "rate_basis": basis,
                        "concept_printed": r.concept, "agreement": r.agreement, "measure": "imputed_from_authorized"})
    d = pd.DataFrame(out)
    # calibration: the agency → purpose map is approximate, so Σ authorized × rate differs
    # from the printed realized total by a few percent; scale every agency of the year so
    # the imputed total equals the printed realized total (Cuadro 16 = EHM 16.27). 1964: none.
    real_tot = rates[rates.level == 0].set_index("year").realized_mn_old_pesos
    d["calibration_factor"] = 1.0
    for y in GAP_YEARS:
        if y in real_tot.index and pd.notna(real_tot[y]):
            m = d.year == y
            d.loc[m, "calibration_factor"] = real_tot[y] / (d.loc[m, "authorized_mn_old_pesos"] * d.loc[m, "execution_rate"]).sum()
    d["execution_rate_applied"] = d.execution_rate * d.calibration_factor
    d["realized_imputed_mn_old_pesos"] = d.authorized_mn_old_pesos * d.execution_rate_applied
    d["authorized_mn_new_pesos"] = d.authorized_mn_old_pesos / 1000
    d["value_mn_new_pesos"] = d.realized_imputed_mn_old_pesos / 1000
    return d


def mapping_coverage(imp: pd.DataFrame, rates: pd.DataFrame) -> pd.DataFrame:
    """Σ authorized of the agencies mapped to each purpose vs the purpose's programmed
    amount in Cuadro 1 (a ratio near 1 means the map reproduces the book's own
    classification)."""
    rows = []
    for y in range(1965, 1970):
        g = imp[imp.year == y]
        for lvl, key in ((1, "purpose_group"), (2, "purpose_item")):
            agg = g.groupby(key).authorized_mn_old_pesos.sum()
            ref = rates[(rates.level == lvl) & (rates.year == y)]
            for _, r in ref.iterrows():
                k = r["group"] if lvl == 1 else r["item"]
                if lvl == 2 and r["group"] not in ("industrial", "bienestar social", "transportes y comunicaciones",
                                                "fomento agropecuario y pesquero"):
                    continue
                mapped = agg.get(k, 0.0) if not (lvl == 2 and k == "otras inversiones") else np.nan
                rows.append({"year": y, "level": lvl, "group": r["group"], "item": r["item"] if lvl == 2 else None,
                             "programmed_cuadro1": r.programmed_mn_old_pesos, "authorized_mapped_agencies": mapped,
                             "ratio": mapped / r.programmed_mn_old_pesos if r.programmed_mn_old_pesos else np.nan})
    return pd.DataFrame(rows)


def main():
    auth = pd.read_csv(AUTH)
    purpose = pd.read_csv(PURPOSE)
    rates = purpose_rates(purpose)
    stab = stability(rates)
    lo = loyo(rates)
    c70 = check_1970(auth, rates)

    summ = lo[lo.year == "mean 1965-69"].set_index("method")
    use_pattern = summ.loc["C_relative_pattern_other_years", "mix_error_pp"] < summ.loc["A_authorized_mix", "mix_error_pp"]
    imp = impute(auth, rates, use_1964_pattern=bool(use_pattern))
    cov = mapping_coverage(imp, rates)

    rates.to_csv(OUT_RATES, index=False)
    checks = pd.concat([stab.assign(check="stability"), lo.assign(check="leave_one_year_out"),
                        c70.assign(check="agency_level_1970"), cov.assign(check="mapping_coverage")],
                       ignore_index=True, sort=False)
    checks.to_csv(OUT_CHECKS, index=False)
    imp.to_csv(OUT_IMPUTED, index=False)

    pd.set_option("display.width", 200)
    print("national execution rates (realized / programmed):")
    print(rates[rates.level == 0][["year", "programmed_mn_old_pesos", "realized_mn_old_pesos", "rate"]].round(3).to_string(index=False))
    print("\ngroup rates by year:")
    print(rates[rates.level == 1].pivot(index="group", columns="year", values="rate").round(3).to_string())
    print("\nitem rates 1965-69 (mean, sd, cv):")
    print(stab[stab.level == 2][["group", "item", "mean_rate", "sd_rate", "cv_rate", "mean_relative", "mean_programmed"]].round(3).to_string(index=False))
    print("\nleave-one-year-out (purpose level):")
    print(lo.to_string(index=False))
    print(f"\n1964 composition uses the relative pattern: {bool(use_pattern)}")
    print("\n1970 agency-level check (programmed Cuadro 15 vs SPP 1970 realized):")
    print(c70.round(3).to_string(index=False))
    print(f"  mean |error| national rule {c70.abs_err_national.sum():.0f} vs group rule {c70.abs_err_group.sum():.0f} "
          f"(sum over secretarías, mn pesos); realized/programmed overall {c70.realized_spp_1970.sum() / c70.programmed_c15.sum():.3f}")
    print("\nmapping coverage (Σ authorized of mapped agencies / programmed of the purpose), groups:")
    print(cov[cov.level == 1].pivot(index="group", columns="year", values="ratio").round(2).to_string())
    print("items:")
    print(cov[cov.level == 2].pivot_table(index=["group", "item"], columns="year", values="ratio").round(2).to_string())
    cov = imp.groupby("year").apply(lambda g: pd.Series({
        "n_agencies": len(g), "authorized": g.authorized_mn_old_pesos.sum(), "imputed": g.realized_imputed_mn_old_pesos.sum(),
        "calibration": g.calibration_factor.iloc[0],
        "share_item_rule": g[g.rate_basis.str.startswith("item")].authorized_mn_old_pesos.sum() / g.authorized_mn_old_pesos.sum(),
        "share_group_rule": g[g.rate_basis.str.startswith("group")].authorized_mn_old_pesos.sum() / g.authorized_mn_old_pesos.sum(),
        "share_national": g[g.rate_basis.str.startswith("national")].authorized_mn_old_pesos.sum() / g.authorized_mn_old_pesos.sum()}))
    print("\nimputed rows by year:")
    print(cov.round(3).to_string())
    unm = imp[imp.purpose_group.isna()].groupby("label_norm").authorized_mn_old_pesos.sum().sort_values(ascending=False)
    print(f"\nagencies on the national rate ({len(unm)}), largest:")
    print(unm.head(15).round(1).to_string())
    print(f"→ {OUT_RATES}\n→ {OUT_CHECKS}\n→ {OUT_IMPUTED}")


if __name__ == "__main__":
    main()
