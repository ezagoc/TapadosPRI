"""Official salaries of the ladder's offices in 1927 and 1999, in 1999 pesos a month.

The appendix table "The ladder" shows, next to each rung, the official salary of its first office
in 1927 and 1999. To compare them, the 1927 salaries are converted to 1999 pesos.

Salaries (the same checkpoints as 02_position_tiers.validate()):
  1927  "cuota diaria" (pesos a day) in the Presupuesto de Egresos de la Federación para 1927
        (SHCP; Google Books aNtCZxaBDvUC). Monthly = daily x 365 / 12 (the budget's annual
        amounts are daily x 365, e.g. Supreme Court justice 60 x 365 = 21,900).
  1999  official monthly pay ranges of the federal command posts, exposición de motivos of the
        PEF 2000, Table VI.4 (new pesos); the midpoint of each range is shown.

Prices, chained (old pesos; 1 new peso = 1,000 old pesos since 1993):
  1927-1939  general wholesale price index, Mexico City (INEGI, Estadísticas históricas de
             México 2014, cuadro 18.4, base 1929=100) -- the only general index covering 1927
  1939-1960  workers' cost-of-living index, Mexico City (cuadro 18.20, base 1978=100)
  1960-1999  consumer price index (World Bank WDI FP.CPI.TOTL; price_deflator_mexico.csv, 02_build_deflator.py)
The chain is approximate: other splices give a 1927-1999 price ratio 22% lower (wholesale index to
1960) to 11% higher (cost of living to 1978); the table rounds to thousands of pesos.

Output: RANK_DIR/official_pay_real.csv
"""
import sys
from pathlib import Path

import pandas as pd

CODE_DIR = Path(__file__).resolve().parents[1]
if str(CODE_DIR) not in sys.path:
    sys.path.append(str(CODE_DIR))

from config import INVESTMENT_DIR, RANK_DIR  # noqa: E402

OUT = RANK_DIR / "official_pay_real.csv"

# INEGI, Estadísticas históricas de México 2014, cap. 18 "Precios" (EHM2014.zip, "18. Precios.pdf")
WPI_1929_BASE = {1927: 104.5, 1939: 118.5, 1942: 140.1}   # cuadro 18.4, general index
WPI_1978_BASE = {1942: 4.7, 1960: 23.0}                    # cuadro 18.5, general index (robustness)
COL_1978_BASE = {1939: 3.0, 1960: 22.2, 1978: 100.0}        # cuadro 18.20, índice general

# rung on the displayed ten-rung ladder (president = 1), 1927 daily pay, 1999 monthly range
OFFICES = [
    ("President of Mexico",                     1, 200.0, None),
    ("Cabinet secretary",                       2, 54.0,  (88278, 88278)),
    ("Undersecretary",                          4, 45.0,  (80085, 83768)),
    ("Director general",                        5, 43.25, (51193, 72061)),
    ("Deputy director general",                 6, None,  (39163, 63036)),
    ("Area director",                           7, None,  (24676, 41473)),
    ("Department head (1927: jefe de sección)", 8, 13.5,  (10013, 15218)),
    ("Subdirector",                             8, None,  (13435, 23285)),
]


def main():
    cpi = pd.read_csv(INVESTMENT_DIR / "price_deflator_mexico.csv").set_index("year").cpi_2010base
    cpi_60_99 = cpi[1999] / cpi[1960]
    ratio = WPI_1929_BASE[1939] / WPI_1929_BASE[1927] * COL_1978_BASE[1960] / COL_1978_BASE[1939] * cpi_60_99
    alt_wpi = WPI_1929_BASE[1942] / WPI_1929_BASE[1927] * WPI_1978_BASE[1960] / WPI_1978_BASE[1942] * cpi_60_99
    alt_col = (WPI_1929_BASE[1939] / WPI_1929_BASE[1927] * COL_1978_BASE[1978] / COL_1978_BASE[1939]
               * cpi[1999] / cpi[1978])
    rows = []
    for office, rung, daily, rng in OFFICES:
        m27 = daily * 365 / 12 if daily else None
        rows.append({"office": office, "rung": rung, "pay_1927_daily": daily,
                     "pay_1927_monthly_1927_pesos": m27,
                     "pay_1927_monthly_1999_pesos": m27 * ratio / 1000 if m27 else None,
                     "pay_1999_monthly_low": rng[0] if rng else None,
                     "pay_1999_monthly_high": rng[1] if rng else None,
                     "pay_1999_monthly_mid": sum(rng) / 2 if rng else None})
    out = pd.DataFrame(rows)
    out["price_ratio_1999_1927_old_pesos"] = ratio
    RANK_DIR.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)
    print(f"1999/1927 price ratio (old pesos): {ratio:,.0f}  [wholesale to 1960: {alt_wpi:,.0f} "
          f"({alt_wpi / ratio - 1:+.0%}); cost of living to 1978: {alt_col:,.0f} ({alt_col / ratio - 1:+.0%})]")
    show = out[["office", "rung", "pay_1927_monthly_1999_pesos", "pay_1999_monthly_mid"]].copy()
    show.iloc[:, 2:] = (show.iloc[:, 2:] / 1000).round(1)
    print("Thousands of 1999 pesos a month:\n" + show.to_string(index=False))
    for col in ("pay_1927_monthly_1999_pesos", "pay_1999_monthly_mid"):
        s = out.dropna(subset=[col]).groupby("rung")[col].min()
        assert s.is_monotonic_decreasing, col          # higher rung (smaller number) = higher pay
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
