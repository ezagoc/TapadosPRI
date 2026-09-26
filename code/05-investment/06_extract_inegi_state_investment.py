"""
06_extract_inegi_state_investment.py

Extract realized federal public investment BY STATE (total per entity and year),
1970–2003, from the INEGI/SPP scans downloaded by 05_download_inegi_investment.py.

The scans' own OCR layer is too noisy for numbers ("Agua5cal~8nte5", lost decimal
points) and Azure Document Intelligence is not available on this machine, so each
table is read from a 300-dpi image by vision LLMs with a strict protocol:

  1. Crop: tables whose years are COLUMNS ("wide") are cut into column pieces, each
     with the entity-name column pasted on its left; tables stacked in YEAR BLOCKS
     ("blocks", total + sectors as columns) are cropped to the name + TOTAL columns.
  2. Two independent reads per crop (READERS); a cell where they disagree gets a
     third read (TIEBREAK) and the majority value is kept (no majority → flagged).
  3. Validation: for every source × year, states (+ "no distribuible" + "extranjero")
     must add up to the printed national total (tolerance: 1 unit or 0.001%).
     Unbalanced tables are (a) reconciled when a single cell's alternative read makes
     them add up, else (b) re-read for that year by all three models at higher zoom,
     kept only if the majority then balances. Overlapping years across editions are
     compared in 07.

Raw model answers are cached per crop × model in INVESTMENT_DIR/inegi_raw/ (delete a
file to re-read it).

Units are harmonised to MILLIONS OF (NEW) PESOS: 1 nuevo peso (1993) = 1,000 old
pesos, so old-peso millions / 1,000; thousands of new pesos / 1,000.

Output: INVESTMENT_DIR/inegi_state_investment_long.csv (source, year, entity, value
as printed, both reads, final value in millions of new pesos, agreement flag) and
inegi_state_investment_validation.csv
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import pymupdf
from PIL import Image

CODE_DIR = Path(__file__).resolve().parents[1]
for p in (CODE_DIR, Path(__file__).resolve().parent):
    if str(p) not in sys.path:
        sys.path.append(str(p))

from config import openai_api_key, INVESTMENT_DIR, LITERATURE_DIR, STATE_LOOKUP_NORM, strip_accents
from llm_tables import READERS, TIEBREAK, page_image, parse_value, read_crop

SRC_DIR = LITERATURE_DIR / "inegi_investment"
RAW_DIR = INVESTMENT_DIR / "inegi_raw"
OUT_LONG = INVESTMENT_DIR / "inegi_state_investment_long.csv"
OUT_VAL = INVESTMENT_DIR / "inegi_state_investment_validation.csv"


# to millions of new pesos
TO_MILLIONS_NEW = {"millions_old_pesos": 1e-3, "thousands_new_pesos": 1e-3,
                   "millions_new_pesos": 1.0, "thousands_pesos": 1e-3}

# source id, file, page, mode, crops, expected years, units, table title
#   wide:   crops = (bbox, label_right_x, [column split xs])   fractions of the page
#   blocks: crops = [bbox, ...]                                  fractions of the page
TABLES = [
    ("spp_1970_1980", "spp_1970_1980_2.pdf", 5, "wide",
     ((0.015, 0.03, 0.995, 0.425), 0.105, [0.55]), list(range(1970, 1981)),
     "millions_old_pesos", "Inversión Pública Federal Realizada por Entidad Federativa (Cuadro II.13)"),
    ("igp_1986", "igp_1986_2.pdf", 17, "wide",
     ((0.0, 0.02, 1.0, 0.53), None, []), list(range(1980, 1986)),
     "millions_old_pesos", "INVERSION PUBLICA FEDERAL REALIZADA, SEGUN ENTIDAD FEDERATIVA 1980-1985 (Cuadro II.2.12)"),
    ("igp_1987", "igp_1987_2.pdf", 8, "wide",
     ((0.0, 0.02, 1.0, 0.53), None, []), list(range(1982, 1988)),
     "millions_old_pesos", "INVERSION PUBLICA FEDERAL REALIZADA, SEGUN ENTIDAD FEDERATIVA 1982-1987 (Cuadro II.2.12)"),
    ("igp_1993a", "igp_1993_2.pdf", 23, "wide",
     ((0.0, 0.02, 1.0, 0.5), None, []), [1987, 1988, 1989],
     "thousands_new_pesos", "INVERSION PUBLICA FEDERAL REALIZADA SEGUN ENTIDAD FEDERATIVA 1987-92, primera parte (Cuadro 3.1.2.6)"),
    ("igp_1993b", "igp_1993_2.pdf", 23, "wide",
     ((0.0, 0.47, 1.0, 0.97), None, []), [1990, 1991, 1992],
     "thousands_new_pesos", "INVERSION PUBLICA FEDERAL REALIZADA SEGUN ENTIDAD FEDERATIVA 1987-92, conclusión (Cuadro 3.1.2.6)"),
]
BLOCK_PAGES = [  # edition, file, units, [(page, expected years)]
    ("igp_1999", "igp_1999_6.pdf", "millions_new_pesos",
     [(3, [1993, 1994]), (5, [1995, 1996]), (7, [1997]), (9, [1998])]),
    ("igp_2000", "igp_2000_2.pdf", "millions_new_pesos",
     [(63, [1994, 1995]), (65, [1996, 1997]), (67, [1998]), (69, [1999])]),
    ("igp_2001", "igp_2001_2.pdf", "millions_new_pesos",
     [(64, [1995, 1996]), (66, [1997, 1998]), (68, [1999]), (70, [2000])]),
    ("igp_2004", "igp_2004_4.pdf", "thousands_pesos",
     [(5, [2000]), (9, [2001]), (13, [2002]), (17, [2003])]),
]
for ed, f, units, pages in BLOCK_PAGES:
    for p, yrs in pages:
        TABLES.append((f"{ed}_p{p}", f, p, "blocks", [(0.0, 0.03, 0.55, 0.99)], yrs, units,
                       "Clasificación sectorial de la inversión pública federal realizada "
                       "según entidad federativa — TOTAL column"))

PROMPT = """This image is (part of) a statistical table from a Mexican government
publication: "{title}". Values are {units_text}.

Transcribe the investment AMOUNTS for every row and every year visible:
{mode_text}
Rows to include: the national total row ("Total", "Total nacional"), every state
(entidad federativa), and if present "No distribuible geográficamente" and
"En el extranjero"/"Extranjero".

Return JSON: {{"records": [{{"row_label": "<as printed>", "year": <int or null>,
"value": "<exactly as printed, keep spaces/commas/decimals/parentheses>"}}]}}
Do not compute, round or correct anything. Use "" for a blank or dash cell."""
MODE_TEXT = {
    "wide": "Years are column headers. Take ONLY the amount columns (skip columns of "
            "percent change, 'incremento', 'estructura', 'distribución', 'participación').",
    "blocks": "Rows are grouped in blocks, each headed by a year label. Take ONLY the first "
              "numeric column, 'TOTAL'. Set year to the label of the block the row belongs "
              "to (if a block's year label is not visible in the image, use null). Expected "
              "years on this page: {years}.",
}
UNITS_TEXT = {"millions_old_pesos": "millions of pesos", "thousands_new_pesos":
              "thousands of new pesos", "millions_new_pesos": "millions of pesos",
              "thousands_pesos": "thousands of pesos"}


def crops_for(mode, spec, im):
    W, H = im.size
    box = lambda b: tuple(int(v * s) for v, s in zip(b, (W, H, W, H)))
    if mode == "blocks":
        return [im.crop(box(b)) for b in spec]
    bbox, label_right, splits = spec
    x0, y0, x1, y1 = box(bbox)
    if label_right is None or not splits:
        return [im.crop((x0, y0, x1, y1))]
    lab = im.crop((x0, y0, int(label_right * W), y1))
    edges = [int(label_right * W)] + [int(s * W) for s in splits] + [x1]
    out = []
    for a, b in zip(edges[:-1], edges[1:]):
        piece = im.crop((a, y0, b, y1))
        c = Image.new("RGB", (lab.width + piece.width, lab.height), "white")
        c.paste(lab, (0, 0)); c.paste(piece, (lab.width, 0))
        out.append(c)
    return out


# (page_image, read_crop and parse_value live in llm_tables.py)


_SPECIAL = [(r"total", "TOTAL"), (r"no\s*dist", "NOT_DISTRIBUTABLE"),
            (r"extranjero", "ABROAD")]


def canonical_entity(label: str):
    t = strip_accents(str(label).lower()).strip(" .:*")
    t = re.sub(r"\s*[a-z]?/\s*$|\s+\d+\s*$", "", t)            # footnote marks
    for pat, key in _SPECIAL:
        if re.search(pat, t):
            return key
    t = re.sub(r"\s+de\s+(zaragoza|ocampo|ignacio de la llave|la llave)$", "", t)
    t = re.sub(r"^(estado de\s+)", "", t)
    if t in STATE_LOOKUP_NORM:
        return STATE_LOOKUP_NORM[t]
    for k, v in sorted(STATE_LOOKUP_NORM.items(), key=lambda kv: -len(kv[0])):
        if k in t:
            return v
    return None


def to_cells(recs, expected_years):
    """records → {(entity, year): printed value}; null-year rows dropped."""
    out = {}
    for r in recs:
        ent = canonical_entity(r.get("row_label", ""))
        y = r.get("year")
        try:
            y = int(y)
        except (TypeError, ValueError):
            continue
        if ent is None or y not in expected_years:
            continue
        out.setdefault((ent, y), str(r.get("value", "")).strip())
    return out


def main():
    import openai
    client = openai.OpenAI(api_key=openai_api_key())
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    rows, val = [], []
    crops_of, prompt_of, years_of = {}, {}, {}

    for sid, file, page, mode, spec, years, units, title in TABLES:
        im = page_image(SRC_DIR / file, page)
        crops = crops_for(mode, spec, im)
        prompt = PROMPT.format(title=title, units_text=UNITS_TEXT[units],
                               mode_text=MODE_TEXT[mode].format(years=years))
        crops_of[sid], prompt_of[sid], years_of[sid] = crops, prompt, years
        reads = {}
        with ThreadPoolExecutor(6) as pool:
            futs = {(m, k): pool.submit(read_crop, client, m, c, prompt,
                                        RAW_DIR / f"{sid}_c{k}_{m}.json")
                    for m in READERS for k, c in enumerate(crops)}
            for (m, k), f in futs.items():
                reads.setdefault(m, {}).update(to_cells(f.result(), years))
        a, b = reads[READERS[0]], reads[READERS[1]]
        disagree = {k for k in set(a) | set(b) if parse_value(a.get(k)) != parse_value(b.get(k))}
        c = {}
        if disagree:
            with ThreadPoolExecutor(6) as pool:
                futs = [pool.submit(read_crop, client, TIEBREAK, cr, prompt,
                                    RAW_DIR / f"{sid}_c{k}_{TIEBREAK}.json")
                        for k, cr in enumerate(crops)]
                for f in futs:
                    c.update(to_cells(f.result(), years))
        for key in sorted(set(a) | set(b)):
            va, vb, vc = (parse_value(d.get(key)) for d in (a, b, c))
            if key not in disagree:
                final, flag = va, "agree"
            elif vc is not None and vc in (va, vb):
                final, flag = vc, "majority"
            else:
                final, flag = va, "unresolved"
            rows.append({"source": sid, "file": file, "page": page, "year": key[1],
                         "entity": key[0], "units_printed": units,
                         "read_1": a.get(key), "read_2": b.get(key), "read_3": c.get(key),
                         "agreement": flag, "value_printed": final})
        print(f"  {sid:16s} p{page:<3d} cells={sum(r['source'] == sid for r in rows):4d} "
              f"disagreements={len(disagree):3d} unresolved="
              f"{sum(r['source'] == sid and r['agreement'] == 'unresolved' for r in rows)}")

    long = pd.DataFrame(rows)

    # 1) reconcile: where parts ≠ printed total, a single cell whose alternative read
    #    makes the table add up is taken from that read
    long = reconcile(long)
    # 2) focused re-read of still-unbalanced source-years: all three models, asked
    #    for that one year only; majority over all reads, kept only if it balances
    for sid, y in unbalanced(long):
        long = reread_year(client, long, sid, y, crops_of[sid], prompt_of[sid])
    # 3) documented manual corrections (visual check + internal evidence)
    long = apply_manual(long)
    long["value_mn_new_pesos"] = long["value_printed"] * long["units_printed"].map(TO_MILLIONS_NEW)
    long.to_csv(OUT_LONG, index=False)

    val = pd.DataFrame([{"source": sid, "year": y, **balance(g)}
                        for (sid, y), g in long.groupby(["source", "year"])])
    val.to_csv(OUT_VAL, index=False)
    print(f"\n→ {OUT_LONG}\n→ {OUT_VAL}")
    print(long["agreement"].str.split(":").str[0].value_counts().to_string())
    print(val.to_string(index=False))


SPECIAL = ("TOTAL", "NOT_DISTRIBUTABLE", "ABROAD")

# Cells fixed by hand after visual inspection of the scan, each with internal evidence
# from the same printed table (its column total and its printed % change column).
MANUAL_CORRECTIONS = {
    ("spp_1970_1980", 1976, "Sonora"): (
        7322.2, "printed '7 322.2' (both models read 7 372.2); consistent with the printed "
                "+208.0% over 1975 (2 377.0) and with the column total 108 610.8"),
    ("spp_1970_1980", 1974, "San Luis Potosi"): (
        896.5, "printed '296.5' is a misprint: the printed +17.5% over 1973 (763.3 × 1.175 = "
               "896.9) and the column total 64 817.3 (states sum 600.0 short) both imply 896.5"),
}


def apply_manual(long: pd.DataFrame) -> pd.DataFrame:
    long = long.copy()
    for (sid, y, ent), (v, why) in MANUAL_CORRECTIONS.items():
        m = (long.source == sid) & (long.year == y) & (long.entity == ent)
        long.loc[m, ["value_printed", "agreement"]] = [v, "manual: " + why]
    return long


def balance(g: pd.DataFrame) -> dict:
    """Printed total vs states + not-distributable + abroad for one source × year."""
    v = g.set_index("entity")["value_printed"].astype(float)
    parts = v.drop([k for k in SPECIAL if k in v.index]).sum() + \
        sum(v.get(k, 0) if pd.notna(v.get(k, 0)) else 0 for k in ("NOT_DISTRIBUTABLE", "ABROAD"))
    tot = v.get("TOTAL")
    ok = tot is not None and pd.notna(tot) and abs(parts - tot) <= max(1.0, 1e-5 * abs(tot))
    return {"n_states": int(v.drop([k for k in SPECIAL if k in v.index]).notna().sum()),
            "printed_total": tot, "sum_of_parts": round(parts, 1),
            "diff": None if tot is None or pd.isna(tot) else round(parts - tot, 1),
            "balanced": bool(ok)}


def unbalanced(long: pd.DataFrame) -> list:
    return [(sid, y) for (sid, y), g in long.groupby(["source", "year"])
            if not balance(g)["balanced"]]


def _alternatives(r) -> set:
    vals = {parse_value(r[c]) for c in ("read_1", "read_2", "read_3") if c in r}
    return {v for v in vals if v is not None and v != r["value_printed"]}


def reconcile(long: pd.DataFrame) -> pd.DataFrame:
    long = long.copy()
    for sid, y in unbalanced(long):
        idx = long.index[(long.source == sid) & (long.year == y)]
        fixes = []
        for i in idx:
            for alt in _alternatives(long.loc[i]):
                trial = long.loc[idx].copy()
                trial.loc[i, "value_printed"] = alt
                if balance(trial)["balanced"]:
                    fixes.append((i, alt))
        if len(fixes) == 1:                      # a unique single-cell fix only
            i, alt = fixes[0]
            long.loc[i, ["value_printed", "agreement"]] = [alt, "reconciled"]
    return long


def reread_year(client, long, sid, year, crops, prompt) -> pd.DataFrame:
    focus = prompt + f"\n\nIMPORTANT: transcribe ONLY the year {year}. Read every digit carefully."
    extra: dict = {}
    for m in READERS + [TIEBREAK]:
        for k, cr in enumerate(crops):
            big = cr.resize((int(cr.width * 1.5), int(cr.height * 1.5)))
            recs = read_crop(client, m, big, focus, RAW_DIR / f"{sid}_y{year}_c{k}_{m}.json")
            for key, v in to_cells(recs, [year]).items():
                extra.setdefault(key, []).append(parse_value(v))
    idx = long.index[(long.source == sid) & (long.year == year)]
    trial = long.loc[idx].copy()
    for i in idx:
        r = trial.loc[i]
        votes = [parse_value(r[c]) for c in ("read_1", "read_2", "read_3")] + \
            extra.get((r.entity, year), [])
        votes = [v for v in votes if v is not None]
        if votes:
            best = max(set(votes), key=votes.count)
            if best != r.value_printed:
                trial.loc[i, ["value_printed", "agreement"]] = [best, "reread"]
    ok = balance(trial)["balanced"]
    print(f"    re-read {sid} {year}: {'balanced' if ok else 'still unbalanced'}")
    if ok:
        long = long.copy()
        long.loc[idx, ["value_printed", "agreement"]] = trial[["value_printed", "agreement"]]
    return long


if __name__ == "__main__":
    main()
