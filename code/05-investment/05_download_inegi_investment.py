"""
05_download_inegi_investment.py

Download the INEGI digital-library scans that report realized federal public
investment ("Inversión Pública Federal Realizada") by state (entidad federativa),
extending the 1959–1969 books to 1970–2003:

  edition                                                      state tables for
  SPP, Información sobre gasto público 1970–1980               1970–1980 (Cuadros II.13–II.20)
  SPP, Estadísticas sobre gasto público 1979                   1970s (cross-check)
  INEGI, El ingreso y el gasto público en México, 1986 ed.     1980–1985
  INEGI, El ingreso y el gasto público en México, 1987 ed.     1982–1987
  INEGI, El ingreso y el gasto público en México, 1993 ed.     1987–1992
  INEGI, El ingreso y el gasto público en México, 1999 ed.     1993–1998
  INEGI, El ingreso y el gasto público en México, 2000 ed.     1994–1999
  INEGI, El ingreso y el gasto público en México, 2001 ed.     1995–2000
  INEGI, El ingreso y el gasto público en México, 2004 ed.     2000–2003

No state-level source exists for 1940–1958: the 1925–1963 book reports those years
only at the national level (state tables start in 1959).

The server answers HTTP 200 even for missing files, so each download is kept only if
it starts with the PDF magic bytes. Already-downloaded files are skipped.

Output: LITERATURE_DIR/inegi_investment/<edition>_<part>.pdf + manifest.csv
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

import pandas as pd

CODE_DIR = Path(__file__).resolve().parents[1]
if str(CODE_DIR) not in sys.path:
    sys.path.append(str(CODE_DIR))

from config import LITERATURE_DIR

OUT_DIR = LITERATURE_DIR / "inegi_investment"
BASE = ("https://www.inegi.org.mx/contenidos/productos/prod_serv/contenidos/espanol/"
        "bvinegi/productos/historicos/{folder}/{upc}/{upc}{part}.pdf")

# edition key, INEGI catalogue folder, UPC, parts, title
EDITIONS = [
    ("spp_1970_1980", "1329", "702825000749", ["_1", "_2", "_3"],
     "SPP, Informacion sobre gasto publico 1970-1980"),
    ("spp_1979", "1329", "702825003585", [""],
     "SPP, Estadisticas sobre gasto publico 1979"),
    ("igp_1986", "2104", "702825450236", ["_1", "_2"],
     "INEGI, El ingreso y el gasto publico en Mexico 1986"),
    ("igp_1987", "2104", "702825450243", ["_1", "_2"],
     "INEGI, El ingreso y el gasto publico en Mexico 1987"),
    ("igp_1993", "2104", "702825450274", ["_1", "_2"],
     "INEGI, El ingreso y el gasto publico en Mexico 1993"),
    ("igp_1999", "2104", "702825450953", [f"_{i}" for i in range(1, 9)],
     "INEGI, El ingreso y el gasto publico en Mexico 1999"),
    ("igp_2000", "2104", "702825451028", [f"_{i}" for i in range(1, 5)],
     "INEGI, El ingreso y el gasto publico en Mexico 2000"),
    ("igp_2001", "2104", "702825451073", [f"_{i}" for i in range(1, 5)],
     "INEGI, El ingreso y el gasto publico en Mexico 2001"),
    ("igp_2004", "181", "702825451165", [f"_{i}" for i in range(1, 8)],
     "INEGI, El ingreso y el gasto publico en Mexico 2004"),
]


def fetch(url: str, dest: Path) -> str:
    if dest.exists() and dest.read_bytes()[:4] == b"%PDF":
        return "cached"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    if data[:4] != b"%PDF":
        return "not a pdf"
    dest.write_bytes(data)
    return "downloaded"


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for key, folder, upc, parts, title in EDITIONS:
        for part in parts:
            url = BASE.format(folder=folder, upc=upc, part=part)
            dest = OUT_DIR / f"{key}{part or '_full'}.pdf"
            status = fetch(url, dest)
            size = dest.stat().st_size / 1e6 if dest.exists() else 0
            print(f"  {dest.name:28s} {status:10s} {size:6.1f} MB")
            rows.append({"edition": key, "title": title, "upc": upc, "part": part or "full",
                         "file": dest.name, "url": url, "status": status})
    pd.DataFrame(rows).to_csv(OUT_DIR / "manifest.csv", index=False)
    print(f"→ {OUT_DIR}")


if __name__ == "__main__":
    main()
