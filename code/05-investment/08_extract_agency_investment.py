"""
08_extract_agency_investment.py

Extract federal public investment BY AGENCY (secretaría / departamento, organismo
descentralizado, empresa de participación estatal) and year from the scanned
Secretaría de la Presidencia book "Inversión Pública Federal 1925–1963":

  Cuadro 2   Inversión pública federal por dependencias, organismos y empresas,
             1925–1958 (realized, millions of current pesos; six 'partes')
  Cuadro 11  the same for 1959–1963 (agency rows only; the indented program /
             project sub-items are skipped)

Book pages are two-page spreads: PDF page p holds book pages 2p (left) and 2p+1
(right). Each half page is cut into overlapping top/bottom crops so the small
print is read at full resolution; rows are merged in reading order (duplicates in
the overlap dropped) and each agency inherits the sector heading above it.

Reading protocol (llm_tables.py): two independent model reads per crop, a third
read where they disagree, majority value kept. Validation per year: sector rows
must equal the sum of their agencies and the TOTAL the sum of the sectors; a single
cell whose alternative read restores both identities is taken from that read.

Outputs (INVESTMENT_DIR):
  agency_investment_1925_1963_long.csv   year × agency, value as printed + reads
  agency_investment_1925_1963_validation.csv
Raw model answers are cached in INVESTMENT_DIR/agency_raw/.
"""

from __future__ import annotations

import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
from PIL import Image

CODE_DIR = Path(__file__).resolve().parents[1]
for p in (CODE_DIR, Path(__file__).resolve().parent):
    if str(p) not in sys.path:
        sys.path.append(str(p))

from config import openai_api_key, INVESTMENT_DIR, LITERATURE_DIR, strip_accents
from llm_tables import READERS, TIEBREAK, page_image, parse_value, read_crop

BOOK = LITERATURE_DIR / "InversionPublicaFederal_1925-1963.pdf"
RAW_DIR = INVESTMENT_DIR / "agency_raw"
OUT_LONG = INVESTMENT_DIR / "agency_investment_1925_1963_long.csv"
OUT_VAL = INVESTMENT_DIR / "agency_investment_1925_1963_validation.csv"

# source id, pdf page, half, expected years, table
PAGES = [
    ("c2_1925_1929", 11, "R", range(1925, 1930), "cuadro2"),
    ("c2_1930_1934", 12, "L", range(1930, 1935), "cuadro2"),
    ("c2_1935_1940", 12, "R", range(1935, 1941), "cuadro2"),
    ("c2_1941_1946", 13, "L", range(1941, 1947), "cuadro2"),
    ("c2_1947_1952", 13, "R", range(1947, 1953), "cuadro2"),
    ("c2_1953_1958", 14, "L", range(1953, 1959), "cuadro2"),
] + [(f"c11_p{p}{h}", p, h, range(1959, 1964), "cuadro11")
     for p, h in [(55, "R"), (56, "L"), (56, "R"), (57, "L"), (57, "R"),
                  (58, "L"), (58, "R"), (59, "L")]]

SECTORS = {"gobierno federal": "gobierno_federal",
           "organismos descentralizados": "organismos_descentralizados",
           "empresas de participacion estatal": "empresas_participacion_estatal"}

PROMPT = """This image is part of a page of a Mexican government statistical table:
"INVERSION PUBLICA FEDERAL POR DEPENDENCIAS, ORGANISMOS Y EMPRESAS" (federal public
investment by government agency, decentralized agency and state-owned company),
millions of pesos. The value columns are the years {years} (left to right){extra}.

Transcribe every row IN READING ORDER, top to bottom:
- row_type "total" for the grand TOTAL row;
- row_type "sector" for the three sector headings: GOBIERNO FEDERAL, ORGANISMOS
  DESCENTRALIZADOS, EMPRESAS DE PARTICIPACION ESTATAL (they carry subtotals);
- row_type "agency" for each agency / company line (Secretaría ..., Departamento ...,
  Comisión ..., Petróleos Mexicanos, ... S. A., and "Otros");
{skip}
Return JSON: {{"records": [{{"row_label": "<full label as printed; join wrapped
lines>", "row_type": "total|sector|agency", "year": <int>, "value": "<exactly as
printed; '' if blank or a dash>"}}]}} — one record per row and year.
Do not compute, round or correct anything."""
SKIP = {
    "cuadro2": "",
    "cuadro11": "- An AGENCY row has its name in SMALL CAPITALS (e.g. 'SECRETARIA DE RECURSOS\n"
                "  HIDRAULICOS') and its numbers in ITALICS. SKIP every indented detail line in\n"
                "  normal type under an agency (programs, projects, commissions, e.g. 'Programa de\n"
                "  bordeo', 'Papaloapan', 'Obras del Valle de México', 'Estudios y servicios',\n"
                "  'Otros' under an agency) — including detail lines at the top of the page that\n"
                "  continue an agency from the previous page.\n",
}
EXTRA = {"cuadro2": "", "cuadro11": "; ignore the first 'TOTAL' column (1959–1963 sum)"}


def half_crops(page: int, half: str) -> list[Image.Image]:
    im = page_image(BOOK, page)
    W, H = im.size
    x0, x1 = (0, W // 2) if half == "L" else (W // 2, W)
    return [im.crop((x0, int(0.02 * H), x1, int(0.58 * H))),
            im.crop((x0, int(0.42 * H), x1, int(0.98 * H)))]


def norm_label(s) -> str:
    s = strip_accents(str(s).lower())
    s = re.sub(r"[\d¹²³⁴⁵⁶⁷⁸⁹]+\s*$|\s+[a-z]/\s*$", "", s)        # footnote marks
    s = re.sub(r"[^a-z ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def ordered_rows(recs_by_crop: list[list[dict]], years) -> list[tuple]:
    """Merge crops in reading order → [(row_type, label, {year: printed})]."""
    rows, seen = [], set()
    for recs in recs_by_crop:
        block: dict = {}
        order = []
        for r in recs:
            key = (r.get("row_type"), norm_label(r.get("row_label")))
            if key not in block:
                block[key] = {}
                order.append((key, r.get("row_label")))
            try:
                y = int(r.get("year"))
            except (TypeError, ValueError):
                continue
            if y in years:
                block[key][y] = str(r.get("value", "")).strip()
        for key, raw in order:
            if key in seen:                              # overlap between crops
                continue
            seen.add(key)
            rows.append((key[0], raw, block[key]))
    return rows


def with_sectors(rows) -> list[tuple]:
    """Attach to each agency the last sector heading above it."""
    out, sector = [], None
    for rtype, label, vals in rows:
        if rtype == "sector":
            sector = SECTORS.get(norm_label(label), norm_label(label))
        out.append((rtype, label, sector if rtype == "agency" else
                    (SECTORS.get(norm_label(label)) if rtype == "sector" else None), vals))
    return out


def main():
    import openai
    client = openai.OpenAI(api_key=openai_api_key())
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    long = []
    for sid, page, half, years, table in PAGES:
        years = list(years)
        crops = half_crops(page, half)
        prompt = PROMPT.format(years=", ".join(map(str, years)), extra=EXTRA[table],
                               skip=SKIP[table])
        reads = {}
        with ThreadPoolExecutor(6) as pool:
            futs = {(m, k): pool.submit(read_crop, client, m, c, prompt,
                                        RAW_DIR / f"{sid}_c{k}_{m}.json")
                    for m in READERS for k, c in enumerate(crops)}
            for m in READERS:
                reads[m] = with_sectors(ordered_rows([futs[(m, k)].result()
                                                      for k in range(len(crops))], years))
        # align the two readers on (row_type, normalised label)
        idx = {m: {(t, norm_label(lab)): (lab, sec, v) for t, lab, sec, v in reads[m]}
               for m in READERS}
        a, b = idx[READERS[0]], idx[READERS[1]]
        need_tb = any(parse_value(a[k][2].get(y)) != parse_value(b.get(k, (None, None, {}))[2].get(y))
                      for k in a for y in years)
        c = {}
        if need_tb:
            with ThreadPoolExecutor(6) as pool:
                futs = [pool.submit(read_crop, client, TIEBREAK, cr, prompt,
                                    RAW_DIR / f"{sid}_c{k}_{TIEBREAK}.json")
                        for k, cr in enumerate(crops)]
                rc = with_sectors(ordered_rows([f.result() for f in futs], years))
                c = {(t, norm_label(lab)): (lab, sec, v) for t, lab, sec, v in rc}
        order = [(t, norm_label(lab)) for t, lab, _, _ in reads[READERS[0]]]
        order += [k for k in b if k not in a]
        for pos, k in enumerate(order):
            lab, sec, _ = a.get(k) or b.get(k)
            for y in years:
                va = parse_value(a.get(k, (0, 0, {}))[2].get(y))
                vb = parse_value(b.get(k, (0, 0, {}))[2].get(y))
                vc = parse_value(c.get(k, (0, 0, {}))[2].get(y)) if c else None
                if va == vb:
                    final, flag = va, "agree"
                elif vc is not None and vc in (va, vb):
                    final, flag = vc, "majority"
                else:
                    final, flag = va if va is not None else vb, "unresolved"
                long.append({"source": sid, "table": table, "pdf_page": page, "half": half,
                             "row_order": pos, "row_type": k[0], "sector": sec,
                             "label": lab, "label_norm": k[1], "year": y,
                             "read_1": a.get(k, (0, 0, {}))[2].get(y),
                             "read_2": b.get(k, (0, 0, {}))[2].get(y),
                             "read_3": c.get(k, (0, 0, {}))[2].get(y) if c else None,
                             "agreement": flag, "value_printed": final})
        n = sum(r["source"] == sid for r in long)
        print(f"  {sid:14s} rows={n // len(years):3d} cells={n}")

    long = pd.DataFrame(long)
    # Cuadro 11 runs over several pages but prints each sector heading only once:
    # carry the sector forward across pages, in page order
    long["page_order"] = long.pdf_page * 2 + (long.half == "R")
    long = long.sort_values(["table", "page_order", "row_order", "year"])
    sec = long.sector.where(long.row_type != "agency")
    long.loc[long.row_type == "agency", "sector"] = None
    long["sector"] = long.groupby("table").sector.transform(
        lambda s: s.fillna(sec.loc[s.index]).ffill())
    long.loc[long.row_type == "total", "sector"] = None
    long = add_manual_rows(long)
    long = reconcile(long)
    long["units"] = "millions_old_pesos"
    long["concept"] = "investment_realized"
    long.to_csv(OUT_LONG, index=False)
    val = validation(long)
    val.to_csv(OUT_VAL, index=False)
    print(long.agreement.value_counts().to_string())
    print(val.to_string(index=False))
    print(f"→ {OUT_LONG}\n→ {OUT_VAL}")


# Rows both readers skipped, added after visual inspection of the scan (with evidence).
MANUAL_ROWS = [
    {"source": "c2_1953_1958", "sector": "empresas_participacion_estatal", "label": "Otras",
     "values": {1953: None, 1954: None, 1955: None, 1956: 6.0, 1957: None, 1958: None},
     "why": "last row of the Empresas block ('Otras', book p. 28) skipped by both reads; "
            "its 6 in 1956 closes the printed Empresas subtotal (586 + 6 = 592)"},
]


def add_manual_rows(long: pd.DataFrame) -> pd.DataFrame:
    add = []
    for m in MANUAL_ROWS:
        src = long[long.source == m["source"]].iloc[0]
        last = long[(long.source == m["source"]) & (long.sector == m["sector"])].row_order.max()
        for y, v in m["values"].items():
            add.append({**{c: src[c] for c in ("table", "pdf_page", "half", "page_order")},
                        "source": m["source"], "row_order": last + 0.5, "row_type": "agency",
                        "sector": m["sector"], "label": m["label"], "label_norm": norm_label(m["label"]),
                        "year": y, "read_1": None, "read_2": None, "read_3": None,
                        "agreement": "manual: " + m["why"], "value_printed": v})
    return pd.concat([long, pd.DataFrame(add)], ignore_index=True)


# ── validation: agencies → sector subtotals → TOTAL ──────────────────────────
def year_checks(g: pd.DataFrame) -> dict:
    """Identities for one year of the whole table (all pages of that period)."""
    v = g.copy()
    out = {}
    ag = v[v.row_type == "agency"].groupby("sector").value_printed.sum(min_count=1)
    sec = v[v.row_type == "sector"].set_index("sector").value_printed
    tot = v[v.row_type == "total"].value_printed
    tot = tot.iloc[0] if len(tot) else None
    diffs = {s: (ag.get(s, 0) or 0) - (sec.get(s) or 0) for s in sec.index if pd.notna(sec.get(s))}
    out["max_sector_gap"] = max((abs(d) for d in diffs.values()), default=None)
    out["total_printed"] = tot
    out["sum_sectors"] = sec.sum(min_count=1)
    out["total_gap"] = None if tot is None or pd.isna(tot) else round(sec.sum() - tot, 2)
    tol = lambda x, ref: x is not None and abs(x) <= max(1.0, 1e-4 * abs(ref or 0))
    out["balanced"] = bool(tol(out["max_sector_gap"], tot) and tol(out["total_gap"], tot))
    return out


def validation(long: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame([{"table": t, "year": y, **year_checks(g)}
                         for (t, y), g in long.groupby(["table", "year"])])


def reconcile(long: pd.DataFrame) -> pd.DataFrame:
    long = long.copy()
    for (t, y), g in long.groupby(["table", "year"]):
        if year_checks(g)["balanced"]:
            continue
        fixes = []
        for i in g.index:
            alts = {parse_value(long.at[i, c]) for c in ("read_1", "read_2", "read_3")}
            for alt in alts - {long.at[i, "value_printed"], None}:
                trial = long.loc[g.index].copy()
                trial.at[i, "value_printed"] = alt
                if year_checks(trial)["balanced"]:
                    fixes.append((i, alt))
        if len(fixes) == 1:
            i, alt = fixes[0]
            long.loc[i, ["value_printed", "agreement"]] = [alt, "reconciled"]
    return long


if __name__ == "__main__":
    main()
