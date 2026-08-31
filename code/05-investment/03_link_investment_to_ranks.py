"""
Wire the federal-investment budget signal into the manual institution ranking.

Uses the extracted 1959-1963 investment (deflated to real 1960 pesos) as an
objective "how big was this institution" measure, and attaches it to the govt
rank lookup table so the manual tiering can lean on budget size.

Produces:
  data/investment/federal_investment_budget_reference.csv
      the 86-institution catalog with real total / annual-average investment,
      budget share, a suggested budget tier (1-5), and the English govt-rank
      name where a crosswalk exists.
  data/rank/govt_institution_rank_budget.csv
      a copy of govt_institution_rank.csv with the budget columns joined on
      (the hand-edited original is left untouched).

Inputs: data/investment/federal_investment_long.csv, price_deflator_mexico.csv,
        data/investment/federal_investment_institutions.csv,
        data/rank/govt_institution_rank.csv
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

CODE_DIR = Path(__file__).resolve().parents[1]
if str(CODE_DIR) not in sys.path:
    sys.path.append(str(CODE_DIR))

from config import INVESTMENT_DIR, RANK_DIR, PRICE_DEFLATOR_CSV, strip_accents

# ---------------------------------------------------------------------------
# Curated crosswalk: investment catalog (Spanish) -> candidate govt-rank names
# (English `secretariat_norm`). First candidate present in the govt table wins.
# Only institutions that plausibly appear in the biography govt careers are
# mapped; the many small state enterprises have no govt-career counterpart.
# ---------------------------------------------------------------------------
CROSSWALK: dict[str, list[str]] = {
    # --- Gobierno Federal (secretariats + DDF) ---
    "Secretaría de Hacienda y Crédito Público": ["Secretariat of the Treasury"],
    "Secretaría de Gobernación":               ["Secretariat of Government"],
    "Secretaría de Educación Pública":         ["Secretariat of Public Education"],
    "Secretaría de Salubridad y Asistencia":   ["Secretariat of Health"],
    "Secretaría de Agricultura y Ganadería":   ["Secretariat of Agriculture",
                                                "Secretariat of Agriculture and Livestock"],
    "Secretaría de Comunicaciones y Transportes": ["Secretariat of Communications and Transportation"],
    "Secretaría de la Defensa Nacional":       ["Secretariat of National Defense"],
    "Secretaría de Marina":                    ["Secretariat of the Navy"],
    "Secretaría del Patrimonio Nacional":      ["Secretariat of National Patrimony"],
    "Secretaría del Trabajo y Previsión Social": ["Secretariat of Labor"],
    "Departamento del Distrito Federal":       ["Department of the Federal District"],
    # --- Organismos descentralizados ---
    "Petróleos Mexicanos":                     ["PEMEX"],
    "Comisión Federal de Electricidad":        ["Federal Electric Commission", "CFE"],
    "Instituto Mexicano del Seguro Social":    ["IMSS"],
    "Instituto de Seguridad y Servicios Sociales de los Trabajadores del Estado": ["ISSSTE"],
    # --- Empresas de participación estatal (banks / industry) ---
    "Banco de México, S. A":                   ["Bank of Mexico"],
    "Nacional Financiera, S. A":               ["Nacional Financiera", "NAFINSA", "NAFIN"],
    "Banco Nacional de Comercio Exterior, S. A": ["National Bank of Foreign Commerce",
                                                  "Foreign Trade Bank"],
    "Banco Nacional de Crédito Ejidal, S. A. de C. V": ["National Bank of Ejido Credit"],
    "Banco Nacional de Crédito Agrícola, S. A": ["National Bank of Agricultural Credit"],
    "Compañía Nacional de Subsistencias Populares, S. A": ["CONASUPO"],
    "Altos Hornos de Mexico, S. A":            ["Altos Hornos de Mexico", "AHMSA"],
    # --- Approximate: the biography table lacks a clean bucket for these; its
    # nearest label conflates them with a neighbouring/later ministry (SCOP/SARH),
    # so the join is the best available but broader than the true 1959-63 body.
    "Secretaría de Obras Públicas":            ["Secretariat of Communications and Public Works"],
    "Secretaría de Recursos Hidráulicos":      ["Secretariat of Agriculture and Hydraulic Resources"],
}

# Investment institutions whose crosswalk target is a broader/adjacent govt bucket.
APPROX_MATCHES = {
    "Secretaría de Obras Públicas",
    "Secretaría de Recursos Hidráulicos",
}


def _norm(s: str) -> str:
    return " ".join(strip_accents(str(s)).lower().split())


def main() -> None:
    # --- real investment per institution -------------------------------------
    long = pd.read_csv(INVESTMENT_DIR / "federal_investment_long.csv")
    defl = pd.read_csv(PRICE_DEFLATOR_CSV)[["year", "deflator"]]
    items = long[(long["row_type"] == "line_item") & long["investment_mdp"].notna()].merge(
        defl, on="year", how="left")
    items["real"] = items["investment_mdp"] * 100 / items["deflator"]
    n_years = items["year"].nunique()

    cat = (items.groupby(["sector", "institution"])
           .agg(total_real=("real", "sum"),
                n_years=("year", "nunique"))
           .reset_index())
    cat["avg_annual_real"] = (cat["total_real"] / n_years).round(1)
    cat["total_real"] = cat["total_real"].round(1)
    cat["budget_share_pct"] = (100 * cat["total_real"] / cat["total_real"].sum()).round(2)
    # Budget tier 1..5 (5 = largest) by quantile of the real total
    cat["budget_tier"] = pd.qcut(cat["total_real"].rank(method="first"),
                                 5, labels=[1, 2, 3, 4, 5]).astype(int)

    # --- attach English govt-rank name via crosswalk ------------------------
    govt = pd.read_csv(RANK_DIR / "govt_institution_rank.csv")
    govt_norm = {_norm(x): x for x in govt["institution"].dropna()}

    def resolve(spanish: str):
        for cand in CROSSWALK.get(spanish, []):
            hit = govt_norm.get(_norm(cand))
            if hit:
                return hit
        return None

    cat["govt_rank_name"] = cat["institution"].map(resolve)
    cat["match_confidence"] = cat.apply(
        lambda r: (None if r["govt_rank_name"] is None
                   else "approx" if r["institution"] in APPROX_MATCHES else "exact"),
        axis=1)
    cat = cat.sort_values("total_real", ascending=False).reset_index(drop=True)
    ref_path = INVESTMENT_DIR / "federal_investment_budget_reference.csv"
    cat.to_csv(ref_path, index=False)

    # --- enrich the govt rank table -----------------------------------------
    budget_by_govt = (cat.dropna(subset=["govt_rank_name"])
                      .groupby("govt_rank_name")
                      .agg(invest_total_mdp_real=("total_real", "sum"),
                           invest_avg_mdp_real=("avg_annual_real", "sum"),
                           invest_budget_tier=("budget_tier", "max"),
                           invest_share_pct=("budget_share_pct", "sum"),
                           invest_match=("match_confidence", "min"))
                      .reset_index())
    enriched = govt.merge(budget_by_govt, left_on="institution",
                          right_on="govt_rank_name", how="left").drop(columns="govt_rank_name")
    out_path = RANK_DIR / "govt_institution_rank_budget.csv"
    enriched.to_csv(out_path, index=False)

    # --- report --------------------------------------------------------------
    matched = cat["govt_rank_name"].notna().sum()
    unresolved = [s for s in CROSSWALK if resolve(s) is None]
    print(f"Real investment years: {sorted(items['year'].unique())}")
    print(f"Budget reference:  {len(cat)} institutions -> {ref_path.name}")
    print(f"Crosswalk matched to govt rank names: {matched}")
    print(f"Govt rank rows enriched with a budget signal: "
          f"{enriched['invest_total_mdp_real'].notna().sum()} / {len(enriched)} -> {out_path.name}")
    if unresolved:
        print(f"Crosswalk targets NOT found in govt table ({len(unresolved)}): "
              + ", ".join(unresolved))
    print("\nTop 12 institutions by real total investment (mdp, 1960):")
    print(cat[["sector", "institution", "total_real", "budget_tier", "govt_rank_name"]]
          .head(12).to_string(index=False))


if __name__ == "__main__":
    main()
