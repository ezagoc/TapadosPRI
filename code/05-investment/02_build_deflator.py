"""
Build a tidy Mexican price-deflator table from the World Bank (WDI) xls files,
for converting the federal investment figures to real (constant-price) pesos.

Sources (data/investment/):
  API_FP.CPI.TOTL_DS2_*.xls      Consumer price index (2010 = 100)
  API_FP.CPI.TOTL.ZG_DS2_*.xls   Inflation, consumer prices (% annual)
  API_FP.WPI.TOTL_DS2_*.xls      Wholesale price index

The WDI series start in 1960. The investment volume includes fiscal year 1959,
so per the project rule 1959 is assigned the 1960 values (both CPI and inflation).

The deflator is rebased so the base year (config.DEFLATOR_BASE_YEAR = 1960) = 100.
Real pesos = nominal * 100 / deflator.

Output: data/investment/price_deflator_mexico.csv
  columns: year, cpi_2010base, inflation_pct, wpi, deflator (base=100)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

CODE_DIR = Path(__file__).resolve().parents[1]
if str(CODE_DIR) not in sys.path:
    sys.path.append(str(CODE_DIR))

from config import (
    CPI_LEVEL_XLS, INFLATION_XLS, WPI_XLS, PRICE_DEFLATOR_CSV, DEFLATOR_BASE_YEAR,
)


def _mexico_series(xls_path: Path, name: str) -> pd.Series:
    """Extract Mexico's yearly values from a WDI-formatted .xls (header on row 4)."""
    df = pd.read_excel(xls_path, sheet_name="Data", header=3)
    row = df[df["Country Code"] == "MEX"].iloc[0]
    out = {}
    for col in df.columns:
        stem = str(col).split(".")[0]
        if stem.isdigit():
            out[int(stem)] = row[col]
    return pd.Series(out, name=name).sort_index()


def main() -> None:
    cpi = _mexico_series(CPI_LEVEL_XLS, "cpi_2010base")
    inf = _mexico_series(INFLATION_XLS, "inflation_pct")
    wpi = _mexico_series(WPI_XLS, "wpi")

    df = pd.concat([cpi, inf, wpi], axis=1).reset_index(names="year")
    df = df[df["year"] <= 2010].copy()   # covers the 1959–2003 state investment panel

    # 1959 := 1960 (series begins in 1960; investment data starts in 1959)
    first = df.loc[df["year"] == 1960].iloc[0].copy()
    first["year"] = 1959
    df = pd.concat([pd.DataFrame([first]), df], ignore_index=True).sort_values("year")

    # Rebased deflator (base year = 100) from the CPI level
    base_cpi = df.loc[df["year"] == DEFLATOR_BASE_YEAR, "cpi_2010base"].iloc[0]
    df["deflator"] = (100 * df["cpi_2010base"] / base_cpi).round(4)

    df = df[["year", "cpi_2010base", "inflation_pct", "wpi", "deflator"]]
    df.to_csv(PRICE_DEFLATOR_CSV, index=False)

    print(f"Wrote {PRICE_DEFLATOR_CSV.name}: {len(df)} years "
          f"({int(df.year.min())}-{int(df.year.max())}), base {DEFLATOR_BASE_YEAR}=100")
    print(df[df.year.between(1959, 1964)].to_string(index=False))


if __name__ == "__main__":
    main()
