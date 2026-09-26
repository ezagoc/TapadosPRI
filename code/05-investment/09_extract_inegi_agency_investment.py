"""
09_extract_inegi_agency_investment.py

Extract REALIZED federal public investment BY AGENCY, 1970–2003, from the SPP / INEGI
scans downloaded by 05_download_inegi_investment.py (the 1925–1963 years come from
08_extract_agency_investment.py):

  SPP 1970–80     Cuadro II.7 (secretarías y departamentos de Estado) and Cuadro II.9
                  (organismos y empresas controlados presupuestalmente), millions of pesos
                  (the 1970 parastatal column is AUTHORIZED investment — footnote a)
  INEGI 1987 ed.  Cuadros II.2.7 / II.2.9, 1982–1987, millions of pesos
  INEGI 1993 ed.  Cuadro 3.1.2.4 (by dependencia, two parts; millions of new pesos —
                  its totals equal the state table's 3.1.2.6 thousands / 1,000) +
                  paraestatal controlado 1987–1992
  INEGI 1999 ed.  administrative classification 1993–1998 + paraestatal, millions of pesos
  INEGI 2001 ed.  administrative classification 1998–2000 + paraestatal 1995–2000
  (2000–2003 by dependency: TOTAL row of the 2004 edition's state × dependency tables — TODO)

Each table is read with the vision-LLM protocol of llm_tables.py (two independent reads,
third read on disagreement, cached, spending ledger capped by LLM_BUDGET_USD). Rows keep
their hierarchy LEVEL (0 total, 1 group, 2 item, 3 sub-item) so the validation can check
that every group equals the sum of its children and the total the sum of the groups;
a single cell whose alternative read restores the identities is taken from that read.

Units are harmonised to millions of NEW pesos (1 new peso = 1,000 old pesos).

Blocks: 'dependencias' (SPP 1970–80: the secretarías' own investment, additive with
'paraestatal'); 'ramo_sector' (1984+; 1982–83 of the 1987 table are still own investment and are
re-blocked in 10_*: after the 1977 sectorisation each parastatal's
investment is also counted under its coordinating secretaría — e.g. Energía, Minas e
Industria Paraestatal includes PEMEX/CFE — so this is a sector view that sums to total
federal investment and must NOT be added to 'paraestatal'); 'paraestatal' (entity level).

Outputs (INVESTMENT_DIR): agency_investment_inegi_long.csv, _validation.csv;
raw answers cached in INVESTMENT_DIR/agency_raw/.
"""

from __future__ import annotations

import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

CODE_DIR = Path(__file__).resolve().parents[1]
for p in (CODE_DIR, Path(__file__).resolve().parent):
    if str(p) not in sys.path:
        sys.path.append(str(p))

from config import INVESTMENT_DIR, LITERATURE_DIR, openai_api_key, strip_accents
from llm_tables import READERS, TIEBREAK, page_image, parse_value, read_crop

SRC = LITERATURE_DIR / "inegi_investment"
RAW_DIR = INVESTMENT_DIR / "agency_raw"
OUT_LONG = INVESTMENT_DIR / "agency_investment_inegi_long.csv"
OUT_VAL = INVESTMENT_DIR / "agency_investment_inegi_validation.csv"
TO_MN_NEW = {"millions_old_pesos": 1e-3, "thousands_new_pesos": 1e-3, "millions_new_pesos": 1.0}

# id, file, page, bbox (x0,y0,x1,y1 as page fractions), vertical splits, years, units,
# block ('dependencias' | 'paraestatal'), title printed on the table
TABLES = [
    ("spp_II7y", "spp_1970_1980_2.pdf", 2, (0.325, 0.59, 0.995, 0.95),
     ("years", 0.445, [(0.445, 0.765, range(1970, 1976)), (0.70, 0.995, range(1975, 1981))]), range(1970, 1981),
     "millions_old_pesos", "dependencias",
     "Inversión Pública Federal Realizada por Secretarías y Departamentos de Estado (Cuadro II.7)"),
    ("spp_II9y", "spp_1970_1980_2.pdf", 3, (0.225, 0.515, 0.995, 0.93),
     ("years", 0.335, [(0.335, 0.665, range(1970, 1976)), (0.60, 0.995, range(1975, 1981))]), range(1970, 1981),
     "millions_old_pesos", "paraestatal",
     "Inversión Pública Federal Realizada por Organismos y Empresas Controlados Presupuestalmente (Cuadro II.9)"),
    ("igp87_II27", "igp_1987_2.pdf", 5, (0.0, 0.02, 1.0, 0.62), 2, range(1982, 1988),
     "millions_old_pesos", "ramo_sector",
     "INVERSION PUBLICA REALIZADA POR SECRETARIAS Y DEPARTAMENTO DE ESTADO 1982-1987"),
    ("igp87_II29", "igp_1987_2.pdf", 6, (0.0, 0.02, 1.0, 0.75), 2, range(1982, 1988),
     "millions_old_pesos", "paraestatal",
     "INVERSION PUBLICA FEDERAL REALIZADA POR ORGANISMOS Y EMPRESAS 1982-1987"),
    ("igp93_a", "igp_1993_2.pdf", 21, (0.0, 0.02, 1.0, 0.52), 2, range(1987, 1990),
     "millions_new_pesos", "ramo_sector",
     "INVERSION PUBLICA FEDERAL EJERCIDA SEGUN DEPENDENCIAS Y SECTORES 1987-92, primera parte (CUADRO 3.1.2.4)"),
    ("igp93_b", "igp_1993_2.pdf", 21, (0.0, 0.48, 1.0, 0.98), 2, range(1990, 1993),
     "millions_new_pesos", "ramo_sector",
     "INVERSION PUBLICA FEDERAL EJERCIDA SEGUN DEPENDENCIAS Y SECTORES 1987-92, conclusión (CUADRO 3.1.2.4)"),
    ("igp93_para", "igp_1993_2.pdf", 62, (0.0, 0.02, 1.0, 0.55), 1, range(1987, 1993),
     "thousands_new_pesos", "paraestatal",
     "INVERSION FISICA DEL SECTOR PARAESTATAL CONTROLADO PRESUPUESTALMENTE SEGUN ORGANISMOS Y EMPRESAS 1987-92"),
    ("igp99_a", "igp_1999_6.pdf", 1, (0.0, 0.02, 1.0, 0.52), 2, range(1993, 1996),
     "millions_new_pesos", "ramo_sector",
     "CLASIFICACION ADMINISTRATIVA DE LA INVERSION PUBLICA FEDERAL REALIZADA SEGUN DEPENDENCIA 1993-98, 1a parte"),
    ("igp99_b", "igp_1999_6.pdf", 1, (0.0, 0.48, 1.0, 0.98), 2, range(1996, 1999),
     "millions_new_pesos", "ramo_sector",
     "CLASIFICACION ADMINISTRATIVA DE LA INVERSION PUBLICA FEDERAL REALIZADA SEGUN DEPENDENCIA 1993-98, conclusión"),
    ("igp99_para", "igp_1999_6.pdf", 29, (0.0, 0.02, 1.0, 0.55), 1, range(1993, 1999),
     "thousands_new_pesos", "paraestatal",
     "INVERSION FISICA DEL SECTOR PARAESTATAL CONTROLADO PRESUPUESTALMENTE SEGUN ORGANISMOS Y EMPRESAS 1993-98"),
    ("igp01_a", "igp_2001_2.pdf", 62, (0.0, 0.02, 1.0, 0.98), 3, range(1998, 2001),
     "millions_new_pesos", "ramo_sector",
     "INVERSION PUBLICA FEDERAL REALIZADA EN CLASIFICACION ADMINISTRATIVA SEGUN DEPENDENCIA 1998-2000, 1a parte"),
    ("igp01_b", "igp_2001_2.pdf", 63, (0.0, 0.02, 1.0, 0.98), 3, range(1998, 2001),
     "millions_new_pesos", "ramo_sector",
     "INVERSION PUBLICA FEDERAL REALIZADA EN CLASIFICACION ADMINISTRATIVA SEGUN DEPENDENCIA 1998-2000, conclusión"),
    ("igp01_para", "igp_2001_2.pdf", 72, (0.0, 0.02, 1.0, 0.55), 1, range(1995, 2001),
     "millions_new_pesos", "paraestatal",
     "INVERSION FISICA DEL SECTOR PARAESTATAL CONTROLADO PRESUPUESTALMENTE SEGUN ORGANISMOS Y EMPRESAS 1995-2000"),
]

# a table continued over two pages is validated as one (page b rows follow page a)
VALIDATE_TOGETHER = {"igp01_a": "igp01_admin", "igp01_b": "igp01_admin"}
ROW_OFFSET = {"igp01_b": 1000}

PROMPT = """This image is (part of) a Mexican government statistical table: "{title}".
Transcribe ONLY this table (ignore any other table on the page). Value columns are the
years {years}; take ONLY the amounts per year — skip columns of percent change
('variación', 'incremento'), structure or shares ('estructura', 'distribución',
'participación') and any cumulative/total-over-years column.

Transcribe every row IN READING ORDER, top to bottom, with its hierarchy level from the
indentation/typography: level 0 = the grand total row; level 1 = a group heading that
carries a subtotal (e.g. 'Poder Ejecutivo', 'Gobierno Federal', 'Organismos y empresas',
'Sector ...'); level 2 = an agency/company under a group (or directly under the total
when the table has no groups); level 3 = a detail line under an agency. Join wrapped labels.
Return JSON: {{"records": [{{"row_label": "<label as printed>", "level": <0-3>,
"year": <int>, "value": "<exactly as printed; '' if blank or a dash>"}}]}}
Do not compute, round or correct anything. If the image shows only part of the table,
transcribe the rows visible."""


def crops(file, page, bbox, splits):
    im = page_image(SRC / file, page)
    W, H = im.size
    x0, y0, x1, y1 = (int(bbox[0] * W), int(bbox[1] * H), int(bbox[2] * W), int(bbox[3] * H))
    if isinstance(splits, tuple) and splits[0] == "years":   # explicit column groups
        from PIL import Image
        _, lab_r, groups = splits
        lab = im.crop((x0, y0, int(lab_r * W), y1))
        out = []
        for gx0, gx1, _ in groups:
            piece = im.crop((int(gx0 * W), y0, int(gx1 * W), y1))
            c = Image.new("RGB", (lab.width + piece.width, lab.height), "white")
            c.paste(lab, (0, 0)); c.paste(piece, (lab.width, 0))
            out.append(c)
        return out
    if isinstance(splits, tuple):          # ("wide", label_right, [x splits]): landscape
        from PIL import Image                # tables → column groups, each with the labels
        _, lab_r, xs = splits
        lab = im.crop((x0, y0, int(lab_r * W), y1))
        edges = [int(lab_r * W)] + [int(x * W) for x in xs] + [x1]
        out = []
        for a, b in zip(edges[:-1], edges[1:]):
            piece = im.crop((a, y0, b, y1))
            c = Image.new("RGB", (lab.width + piece.width, lab.height), "white")
            c.paste(lab, (0, 0)); c.paste(piece, (lab.width, 0))
            out.append(c)
        return out
    if splits == 1:
        return [im.crop((x0, y0, x1, y1))]
    step = (y1 - y0) / splits
    ov = int(0.06 * (y1 - y0))
    return [im.crop((x0, max(y0, int(y0 + k * step) - ov), x1, min(y1, int(y0 + (k + 1) * step) + ov)))
            for k in range(splits)]


def norm_label(s) -> str:
    s = strip_accents(str(s).lower())
    s = re.sub(r"\s*[a-z]?/\s*$|[\d¹²³⁴⁵⁶⁷⁸⁹]+\s*$", "", s)
    s = re.sub(r"[^a-z ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def align(level, label, ref, cutoff=0.9):
    """Return the reference label (same level) most similar to `label` if ≥ cutoff."""
    from difflib import SequenceMatcher
    n = norm_label(label)
    best = max(((SequenceMatcher(None, n, r).ratio(), r) for l, r in ref if l == level),
               default=(0, None))
    return best[1] if best[0] >= cutoff and best[1] != n else label


def merged_rows(recs_by_crop, years, wide=False):
    """Merge crops in reading order → [(level, label, {year: printed})], overlaps dropped.
    For wide tables every crop holds all rows (different years): values are unioned."""
    if wide:
        rows, pos = [], {}
        for recs in recs_by_crop:
            for lvl, lab, vals in merged_rows([recs], years):
                k = next((k for k in pos if k[0] == lvl and _similar(k[1], norm_label(lab))), None)
                if k is None:
                    k = (lvl, norm_label(lab)); pos[k] = len(rows); rows.append((lvl, lab, {}))
                rows[pos[k]][2].update({y: v for y, v in vals.items() if y not in rows[pos[k]][2]})
        return rows
    rows, seen = [], set()
    for recs in recs_by_crop:
        block, order = {}, []
        for r in recs:
            try:
                lvl = int(r.get("level"))
            except (TypeError, ValueError):
                lvl = 2
            key = (lvl, norm_label(r.get("row_label")))
            if not key[1]:
                continue
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
            if key in seen or any(k[0] == key[0] and _similar(k[1], key[1]) for k in seen):
                continue
            seen.add(key)
            rows.append((key[0], raw, block[key]))
    return rows


def _similar(a: str, b: str) -> bool:
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b).ratio() >= 0.9


def drop_fragments(rows, years):
    """Drop a 1–2 word row that is the wrapped tail of an earlier label ('Público' of
    'Secretaría de Hacienda y Crédito Público') repeating that row's values."""
    out = []
    for lvl, lab, vals in rows:
        frag = len(norm_label(lab).split()) <= 2 and any(parse_value(v) for v in vals.values())
        if frag and any(all(parse_value(vals.get(y)) == parse_value(pv.get(y)) for y in years)
                        for _, _, pv in out):
            continue          # wrapped label tail repeating an earlier row's values
        out.append((lvl, lab, vals))
    return out


def drop_duplicate_rows(long: pd.DataFrame) -> pd.DataFrame:
    """Within a table, a row that agrees with an earlier row of the same level in every
    year where both have a value (≥3 such years, no conflict) is the same row read twice
    under a label variant (e.g. footnote letters glued to the name: 'PIDERj' / 'PIDERl');
    the later copy is dropped and its extra years fill the first."""
    keep, drop = long.copy(), []
    for t, g in long.groupby("table"):
        firsts = []
        for ro, h in g.groupby("row_order", sort=True):
            v = h.set_index("year").value_printed
            match = None
            for ro0, v0, lvl0 in firsts:
                both = v.notna() & v0.reindex(v.index).notna()
                if lvl0 == h.level.iloc[0] and both.sum() >= 3 and \
                        (v[both].round(3) == v0.reindex(v.index)[both].round(3)).all():
                    match = ro0
                    break
            if match is None:
                firsts.append((ro, v, h.level.iloc[0]))
                continue
            drop.extend(h.index)
            for y, val in v.items():                       # fill gaps of the first copy
                m = (keep.table == t) & (keep.row_order == match) & (keep.year == y)
                if pd.notna(val) and keep.loc[m, "value_printed"].isna().all():
                    keep.loc[m, "value_printed"] = val
    return keep.drop(index=drop)


def hierarchy_gaps(g: pd.DataFrame) -> list[float]:
    """For one table-year (rows in order): parent − sum(children) for every parent."""
    rows = g.sort_values("row_order")[["level", "value_printed"]].values.tolist()
    gaps = []
    for i, (lvl, val) in enumerate(rows):
        desc, j = [], i + 1
        while j < len(rows) and rows[j][0] > lvl:
            desc.append(rows[j])
            j += 1
        # direct children = the shallowest level among the descendants (a table may
        # skip a level, e.g. companies directly under the total)
        kids = [v for l, v in desc if l == min(l2 for l2, _ in desc)] if desc else []
        if kids and pd.notna(val):
            gaps.append(val - sum(v for v in kids if pd.notna(v)))
    return gaps


# Printed cells that contradict the table itself (verified on the scan). They are kept,
# flagged in `source_note`, and left out of the identity checks.
SOURCE_ISSUES = {
    ("igp87_II29", 1985, "instituto para el desarrollo de la comunidad rural"): (
        "printed 3 024 in 1985, but footnote b says the institute was liquidated in "
        "January 1983; the column total excludes it (companies sum to total + 3 024)"),
}


# Misprinted cells corrected with internal evidence from the same table (verified on
# the scan): the printed % change column and the printed column total.
MANUAL_CORRECTIONS = {
    ("spp_II9y", 1976, "compania de luz y fuerza del centro"): (
        2528.5, "printed '1 528.5' but its printed change is +39.4% over 1 813.2 (1975) = 2 527.6; "
                "with 2 528.5 the companies add up to the printed total 49 627.0"),
    ("spp_II9y", 1977, "compania de luz y fuerza del centro"): (
        3832.9, "printed '2 832.9' but its printed change is ~+51% over 2 528.5 (1976) = 3 818; "
                "with 3 832.9 the companies add up to the printed total 64 053.0"),
}


def apply_manual(long: pd.DataFrame) -> pd.DataFrame:
    long = long.copy()
    for (t, y, pref), (v, why) in MANUAL_CORRECTIONS.items():
        m = (long.table == t) & (long.year == y) & long.label_norm.str.startswith(pref)
        long.loc[m, ["value_printed", "agreement"]] = [v, "manual: " + why]
    return long


def issue(table, year, label_norm):
    for (t, y, pref), note in SOURCE_ISSUES.items():
        if t == table and y == year and label_norm.startswith(pref):
            return note
    return None


def balanced(g: pd.DataFrame) -> bool:
    if "source_note" in g:
        g = g[g.source_note.isna()]
    tot = g[g.level == 0].value_printed
    ref = abs(tot.iloc[0]) if len(tot) and pd.notna(tot.iloc[0]) else 1000
    return all(abs(x) <= max(1.0, 1e-4 * ref) for x in hierarchy_gaps(g))


def main():
    import openai
    client = openai.OpenAI(api_key=openai_api_key())
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    only = set(sys.argv[1:])
    long = []
    for tid, file, page, bbox, splits, years, units, block, title in TABLES:
        if only and tid not in only:
            continue
        years = list(years)
        cr = crops(file, page, bbox, splits)
        prompt = PROMPT.format(title=title, years=", ".join(map(str, years)))
        prompts = [PROMPT.format(title=title, years=", ".join(map(str, g[2]))) +
                   f"\nThis crop shows the row labels on the left and ONLY the columns for "
                   f"{g[2][0]}–{g[2][-1]}. Note: some years may have no 'Incremento' column."
                   for g in splits[2]] if isinstance(splits, tuple) and splits[0] == "years" \
            else [prompt] * len(cr)
        with ThreadPoolExecutor(6) as pool:
            futs = {(m, k): pool.submit(read_crop, client, m, c, prompts[k], RAW_DIR / f"inegi_{tid}_c{k}_{m}.json")
                    for m in READERS for k, c in enumerate(cr)}
            wide = isinstance(splits, tuple)
            reads = {m: drop_fragments(merged_rows([futs[(m, k)].result() for k in range(len(cr))],
                                                   years, wide), years)
                     for m in READERS}
        # align reader 2's labels to reader 1's when they differ only slightly
        ref = [(l, norm_label(lab)) for l, lab, _ in reads[READERS[0]]]
        reads[READERS[1]] = [(l, align(l, lab, ref), v) for l, lab, v in reads[READERS[1]]]
        idx = {m: {(l, norm_label(lab)): (lab, v) for l, lab, v in reads[m]} for m in READERS}
        a, b = idx[READERS[0]], idx[READERS[1]]
        disagree = any(parse_value(a[k][1].get(y)) != parse_value(b.get(k, ("", {}))[1].get(y))
                       for k in a for y in years) or set(a) != set(b)
        c = {}
        if disagree:
            with ThreadPoolExecutor(6) as pool:
                futs = [pool.submit(read_crop, client, TIEBREAK, x, prompts[k], RAW_DIR / f"inegi_{tid}_c{k}_{TIEBREAK}.json")
                        for k, x in enumerate(cr)]
                c = {(l, norm_label(lab)): (lab, v) for l, lab, v in
                     drop_fragments(merged_rows([f.result() for f in futs], years, wide), years)}
        order = [(l, norm_label(lab)) for l, lab, _ in reads[READERS[0]]] + [k for k in b if k not in a]
        for pos, k in enumerate(order):
            lab = (a.get(k) or b.get(k))[0]
            for y in years:
                va, vb = (parse_value(d.get(k, ("", {}))[1].get(y)) for d in (a, b))
                vc = parse_value(c.get(k, ("", {}))[1].get(y)) if c else None
                if va == vb:
                    final, flag = va, "agree"
                elif vc is not None and vc in (va, vb):
                    final, flag = vc, "majority"
                else:
                    final, flag = (va if va is not None else vb), "unresolved"
                long.append({"table": tid, "file": file, "page": page, "block": block, "units": units,
                             "row_order": pos, "level": k[0], "label": lab, "label_norm": k[1], "year": y,
                             "read_1": a.get(k, ("", {}))[1].get(y), "read_2": b.get(k, ("", {}))[1].get(y),
                             "read_3": c.get(k, ("", {}))[1].get(y) if c else None,
                             "agreement": flag, "value_printed": final})
        n = sum(r["table"] == tid for r in long)
        print(f"  {tid:12s} p{page:<3d} rows={n // len(years):3d} disagreements={'yes' if disagree else 'no'}")

    long = drop_duplicate_rows(pd.DataFrame(long))
    long["vtable"] = long.table.replace(VALIDATE_TOGETHER)
    long["row_order"] = long.row_order + long.table.map(ROW_OFFSET).fillna(0)
    long["source_note"] = [issue(t, y, n) for t, y, n in zip(long.table, long.year, long.label_norm)]
    long = apply_manual(long)
    long = reconcile(long)
    # focused re-reads of still-unbalanced table-years (all three models, higher zoom,
    # one year only); kept only if the majority then balances
    spec = {t[0]: t for t in TABLES}
    for (vt, y), g in long.groupby(["vtable", "year"]):
        if vt in EXCLUDED or balanced(g):
            continue
        for tid in g.table.unique():
            if tid in spec:
                long = reread_year(client, long, spec[tid], y)
    long["in_panel"] = ~long.vtable.isin(EXCLUDED)
    long["value_mn_new_pesos"] = long.value_printed * long.units.map(TO_MN_NEW)
    long.to_csv(OUT_LONG, index=False)
    val = pd.DataFrame([{"vtable": t, "year": y, "balanced": balanced(g),
                         "max_gap": max((abs(x) for x in hierarchy_gaps(g[g.source_note.isna()])), default=0),
                         "total_printed": g[g.level == 0].value_printed.max()}
                        for (t, y), g in long.groupby(["vtable", "year"])])
    val.to_csv(OUT_VAL, index=False)
    print(long.agreement.value_counts().to_string())
    print(val.groupby("vtable").agg(years=("year", "size"), balanced=("balanced", "sum"),
                                   worst_gap=("max_gap", "max")).to_string())
    print(f"→ {OUT_LONG}\n→ {OUT_VAL}")


# read but not used in the panel (4-level functional × administrative classification
# whose levels cannot be validated reliably; paraestatal 1995–2000 comes from igp01_para)
EXCLUDED = {"igp01_admin"}


def reread_year(client, long, spec, year):
    tid, file, page, bbox, splits, years, units, block, title = spec
    prompt = PROMPT.format(title=title, years=year) + \
        f"\n\nIMPORTANT: transcribe ONLY the column for {year}. Read every digit carefully."
    extra = {}
    for m in READERS + [TIEBREAK]:
        for k, cr in enumerate(crops(file, page, bbox, splits)):
            big = cr.resize((int(cr.width * 1.4), int(cr.height * 1.4)))
            recs = read_crop(client, m, big, prompt, RAW_DIR / f"inegi_{tid}_y{year}_c{k}_{m}.json")
            for lvl, lab, vals in merged_rows([recs], [year]):
                if year in vals:
                    extra.setdefault(norm_label(lab), []).append(parse_value(vals[year]))
    idx = long.index[(long.table == tid) & (long.year == year)]
    trial = long.loc[idx].copy()
    for i in idx:
        votes = [parse_value(trial.at[i, c]) for c in ("read_1", "read_2", "read_3")]
        key = next((k for k in extra if _similar(k, trial.at[i, "label_norm"])), None)
        votes = [v for v in votes + extra.get(key, []) if v is not None]
        if votes:
            best = max(set(votes), key=votes.count)
            if best != trial.at[i, "value_printed"]:
                trial.loc[i, ["value_printed", "agreement"]] = [best, "reread"]
    vt = long.loc[idx[0], "vtable"]
    whole = pd.concat([long[(long.vtable == vt) & (long.year == year) & ~long.index.isin(idx)], trial])
    ok = balanced(whole)
    print(f"    re-read {tid} {year}: {'balanced' if ok else 'still unbalanced'}")
    if ok:
        long.loc[idx, ["value_printed", "agreement"]] = trial[["value_printed", "agreement"]]
    return long


def reconcile(long: pd.DataFrame) -> pd.DataFrame:
    long = long.copy()
    for (t, y), g in long.groupby(["vtable", "year"]):
        if balanced(g):
            continue
        fixes = []
        for i in g.index:
            for alt in {parse_value(long.at[i, c]) for c in ("read_1", "read_2", "read_3")} - {long.at[i, "value_printed"], None}:
                trial = long.loc[g.index].copy()
                trial.at[i, "value_printed"] = alt
                if balanced(trial):
                    fixes.append((i, alt))
        if len(fixes) == 1:
            i, alt = fixes[0]
            long.loc[i, ["value_printed", "agreement"]] = [alt, "reconciled"]
    return long


if __name__ == "__main__":
    main()
