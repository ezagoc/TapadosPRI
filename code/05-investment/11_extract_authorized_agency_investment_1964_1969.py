"""
11_extract_authorized_agency_investment_1964_1969.py

Extract federal public investment AUTHORIZED / PROGRAMMED by agency (secretaría or
departamento, organismo descentralizado, empresa de participación estatal) for
1964–1970 from the two Secretaría de la Presidencia books that cover the gap of the
agency panel (no realized-by-agency figures exist for 1964–1969; see README_1964_1969.md):

  Book A  "Inversión Pública Federal 1964–1966" (literature/federal_investment_1964.pdf,
          199 pp., one book page per PDF page, right half; Azure OCR JSON of all pages)
          Cuadro 1  (pp. 5–7)     authorized by dependencia, 1964
          Cuadro 6  (pp. 53–55)   authorized by dependencia, 1965
          Cuadro 12 (pp. 124–126) authorized by entidad, 1966
          Cuadros 2, 7, 13 (pp. 8, 56, 127) authorized by destino (purpose), 1964–1966
  Book B  "Inversión Pública Federal 1965–1970" (literature/federal_investment_1965_1970.pdf,
          128 PDF pages = two-page spreads with the tables printed sideways; Azure OCR JSON
          covers PDF pp. 73–128)
          Cuadro 9       (book pp. 145–148) programmed by entity, sum 1965–1970
          Cuadros 10–15  (pp. 149–170)      programmed by entity, one per year 1965–1970
                                            (1965 and 1966: "cifras autorizadas")
          Cuadro 1       (pp. 136–137)      programmed by objeto del gasto, 1965–1970
          Cuadro 16      (pp. 172–173)      REALIZED by objeto del gasto, 1965–1969 (+1970 programmed)
          Annex Cuadro I (pp. 207–208)      authorized by dependencia, 1964 (second printing)

Units: millions of pesos of the day (old pesos) → `value_mn_new_pesos` = printed / 1 000,
as 08_extract_agency_investment.py does for the 1925–1963 book.

Reading protocol. Reader 1 = Azure Document Intelligence layout OCR (the JSON files).
Reader 2 = vision LLM (llm_tables.READERS[0]) on page crops; where the two disagree a third
read (READERS[1]) breaks the tie by majority. Every LLM answer is cached in
INVESTMENT_DIR/agency_raw/ (prefix auth_) and logged in the spending ledger (llm_tables).
The 1965–1970 sum table (Cuadro 9), the 1964 annex and the purpose tables are read by
Azure only: they are validation tables, each checked against an independent printing or
identity (see below). Run with --no-llm to rebuild from Azure and the cache only.

Validation (→ *_validation.csv): per table-year, sector subtotals = sum of agencies and
TOTAL = sum of sectors; in Book B the printed SUMA of every row = sum of its financing
columns (Azure read); the 1965–1970 sum of every entity (Cuadro 9) = sum of its six yearly
figures; 1964 Book A Cuadro 1 vs Book B annex; 1965 and 1966 Book A vs Book B (documented
revisions between the two printings); purpose tables: groups = sum of items, SUMA = sum of
years, and the realized totals vs INEGI Estadísticas Históricas 2014 (Cuadro 16.27).
Printed cells that contradict the table are corrected only with the printed evidence
listed in MANUAL_CORRECTIONS.

Outputs (INVESTMENT_DIR):
  agency_investment_authorized_1964_1969_long.csv        (also holds the 1970 and 1965–70 sum rows)
  agency_investment_authorized_1964_1969_validation.csv
  investment_purpose_programmed_realized_1964_1970.csv   (objeto del gasto / destino tables)
"""

from __future__ import annotations

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd
from PIL import Image

CODE_DIR = Path(__file__).resolve().parents[1]
for p in (CODE_DIR, Path(__file__).resolve().parent):
    if str(p) not in sys.path:
        sys.path.append(str(p))

from config import (INVERSION_PUBLICA_1965_1970_JSON, INVESTMENT_DIR, LITERATURE_DIR,  # noqa: E402
                    openai_api_key, strip_accents)
from llm_tables import READERS, page_image, parse_value, read_crop  # noqa: E402

BOOKS = {
    "b64": {"pdf": LITERATURE_DIR / "federal_investment_1964.pdf",
            "json": LITERATURE_DIR / "federal_investment_1964.pdf.json", "page_offset": 0,
            "title": "Inversión Pública Federal 1964–1966 (Secretaría de la Presidencia, 1967)"},
    "b70": {"pdf": LITERATURE_DIR / "federal_investment_1965_1970.pdf",
            "json": INVERSION_PUBLICA_1965_1970_JSON, "page_offset": 72,
            "title": "Inversión Pública Federal 1965–1970 (Secretaría de la Presidencia, 1970)"},
}
RAW_DIR = INVESTMENT_DIR / "agency_raw"
OUT_LONG = INVESTMENT_DIR / "agency_investment_authorized_1964_1969_long.csv"
OUT_VAL = INVESTMENT_DIR / "agency_investment_authorized_1964_1969_validation.csv"
OUT_PURPOSE = INVESTMENT_DIR / "investment_purpose_programmed_realized_1964_1970.csv"
LLM_READER, LLM_TIEBREAK = READERS[0], READERS[1]

# Agency tables: id, book, caption number (as printed), year, concept, value column name,
# half-pages read by the LLM [(pdf_page, half)] (empty = Azure only)
AGENCY_TABLES = [
    ("b64_c1", "b64", "1", 1964, "authorized", "Total", [(5, "R"), (6, "R"), (7, "R")]),
    ("b64_c6", "b64", "6", 1965, "authorized", "Total", [(53, "R"), (54, "R"), (55, "R")]),
    ("b64_c12", "b64", "12", 1966, "authorized", "Total", [(124, "R"), (125, "R"), (126, "R")]),
    ("b70_cI", "b70", "I", 1964, "authorized", "Millones de pesos", []),
    ("b70_c9", "b70", "9", None, "programmed_sum_1965_1970", "SUMA", []),
    ("b70_c10", "b70", "10", 1965, "authorized", "SUMA", [(81, "R"), (82, "L"), (82, "R"), (83, "L")]),
    ("b70_c11", "b70", "11", 1966, "authorized", "SUMA", [(83, "R"), (84, "L"), (84, "R"), (85, "L")]),
    ("b70_c12", "b70", "12", 1967, "programmed", "SUMA", [(85, "L"), (85, "R"), (86, "L"), (86, "R")]),
    ("b70_c13", "b70", "13", 1968, "programmed", "SUMA", [(87, "L"), (87, "R"), (88, "L")]),
    ("b70_c14", "b70", "14", 1969, "programmed", "SUMA", [(88, "R"), (89, "L"), (89, "R"), (90, "L")]),
    ("b70_c15", "b70", "15", 1970, "programmed", "SUMA", [(90, "R"), (91, "L"), (91, "R"), (92, "L")]),
]
# Purpose (objeto del gasto / destino) tables, Azure only: id, book, caption, concept, year columns
PURPOSE_TABLES = [
    ("b70_c1", "b70", "1", "programmed", [None, 1965, 1966, 1967, 1968, 1969, 1970]),
    ("b70_c16", "b70", "16", "realized", [None, 1965, 1966, 1967, 1968, 1969, 1970]),
    ("b64_c2", "b64", "2", "authorized", [1964]),
    ("b64_c7", "b64", "7", "authorized", [1965]),
    ("b64_c13", "b64", "13", "authorized", [1966]),
]
# Book B Cuadro 16: 1970 is programmed ("* Inversión autorizada"); SUMA column = 1965–1970
PURPOSE_1970_IS_PROGRAMMED = {"b70_c16"}
# cross-printings of the same year (reference table, second table)
CROSS = [("b64_c1", "b70_cI", 1964), ("b64_c6", "b70_c10", 1965), ("b64_c12", "b70_c11", 1966)]
# the 1965–1970 sum table must equal the six yearly tables
SUM_TABLE, YEAR_TABLES = "b70_c9", ["b70_c10", "b70_c11", "b70_c12", "b70_c13", "b70_c14", "b70_c15"]
# INEGI, Estadísticas Históricas de México 2014, Cuadro 16.27 "Destino de la inversión
# pública federal realizada" (source for 1925–1970: Secretaría de la Presidencia): totals
EHM_REALIZED_TOTAL = {1965: 13049, 1966: 15475, 1967: 21057, 1968: 23314, 1969: 26339, 1970: 29205}

SECTORS = [("gobierno federal", "gobierno_federal"),
           ("organismos descentralizados", "organismos_descentralizados"),
           ("empresas de participacion estatal", "empresas_participacion_estatal")]

PROMPT = """This image is part of a page of a Mexican government statistical table from the
book "{book}": "{title}" (investment by government agency, decentralized agency and
state-owned company; millions of pesos).

Transcribe every row IN READING ORDER, top to bottom:
- row_type "total" for the grand TOTAL row;
- row_type "sector" for the three section headings GOBIERNO FEDERAL, ORGANISMOS
  DESCENTRALIZADOS and EMPRESAS DE PARTICIPACION ESTATAL (they carry subtotals);
- row_type "agency" for every other line (Secretaría ..., Departamento ..., Comisión ...,
  Instituto ..., Banco ..., Petróleos Mexicanos, ... S. A., Subsidios, Territorio ...).
For each row give "value" = the amount printed in the column "{col}" — the FIRST numeric
column, immediately to the right of the label — exactly as printed ('' if blank or a
dash). Ignore every other column (%, Recursos, Crédito, Cooperaciones, etc.). Join
wrapped labels into one row; drop footnote marks such as 1/, a/, *.
Return JSON: {{"records": [{{"row_label": "<label as printed>", "row_type":
"total|sector|agency", "value": "<as printed>"}}]}}. Do not compute, round or correct
anything. If the image shows only part of the table, transcribe the rows visible."""


# ── labels ───────────────────────────────────────────────────────────────────
def norm_label(s) -> str:
    s = strip_accents(str(s).lower())
    s = re.sub(r":(?:un)?selected:", " ", s)
    s = re.sub(r"(?<=[a-z])-\s+(?=[a-z])", "", s)                      # hyphenated line breaks
    s = re.sub(r"\bma[lľi]z\b", "maiz", s)
    s = re.sub(r"\b\d{1,2}\s*/|\b[a-z]\s*/|\*|\b\d\b(?=\s*$)", " ", s)      # footnote marks 1/, a/, *
    s = re.sub(r"[^a-z ]+", " ", s)
    s = re.sub(r"\b(s a|s a de c v|s de r l|a c|s c l?|y filiales?|y filial)\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def row_type_of(label_norm: str) -> str | None:
    """'total' / 'sector' / 'agency' / None (header or junk)."""
    if not label_norm:
        return None
    if re.fullmatch(r"(it |ii |i )?total( autorizado)?", label_norm) or label_norm == "total":
        return "total"
    for key, _ in SECTORS:
        if similar(label_norm.replace("it ", ""), key) >= 0.85 or key in label_norm:
            return "sector"
    if re.fullmatch(r"(concepto|millones de pesos|total|porciento.*|cuadro.*|dependencias gubernamentales.*)", label_norm):
        return None
    if re.search(r"\b(continuacion|conclusion)\b|^cuadro\b", label_norm):
        return None
    return "agency"


def sector_key(label_norm: str) -> str | None:
    for key, val in SECTORS:
        if similar(label_norm.replace("it ", ""), key) >= 0.85 or key in label_norm:
            return val
    return None


# ── Azure JSON ───────────────────────────────────────────────────────────────
_JSON_CACHE: dict = {}


def analyze(book: str) -> dict:
    if book not in _JSON_CACHE:
        d = json.loads(BOOKS[book]["json"].read_text())
        _JSON_CACHE[book] = d.get("analyzeResult", d)
    return _JSON_CACHE[book]


CAPTION_RE = re.compile(r"^\s*cuad\w*[\s,.]*(?:no\.?\s*)?([ivx]+|\d+)\b(?!\s*\.\s*\d)", re.I)


def tables_of(book: str, caption: str) -> list[dict]:
    """Azure tables printed under caption 'CUADRO <caption>' (and its continuations),
    assigned by document offset: a table belongs to the last caption printed before it."""
    ar = analyze(book)
    caps = []
    for p in ar["paragraphs"]:
        m = CAPTION_RE.match(p["content"])
        if m and p.get("spans"):
            caps.append((p["spans"][0]["offset"], m.group(1).upper()))
    caps.sort()
    out = []
    for t in ar["tables"]:
        off = t["spans"][0]["offset"]
        before = [c for c in caps if c[0] < off]
        if before and before[-1][1] == caption.upper():
            out.append(t)
    return sorted(out, key=lambda t: t["spans"][0]["offset"])


def grid(t: dict) -> list[list[str]]:
    g = [[""] * t["columnCount"] for _ in range(t["rowCount"])]
    for c in t["cells"]:
        txt = re.sub(r":(?:un)?selected:", " ", c.get("content") or "")
        g[c["rowIndex"]][c["columnIndex"]] = " ".join(txt.split())
    return g


NUM_RE = re.compile(r"(?<![\d.])\d{1,3}(?: \d{3})*(?:\s?\.\s?\d)?(?![\d])")


def cell_number(s: str) -> tuple[float | None, str]:
    """Printed cell → (value, flag). A cell with several numbers (pencil annotations in the
    library copy, or two rows merged by the OCR) takes the LAST printed number and is
    flagged 'multi'; a dash/blank → None."""
    s = s.strip().replace(":", ".")
    if not s or re.fullmatch(r"[-–—.,]+", s):
        return None, ""
    if re.fullmatch(r"(?:\d{1,3}(?:[ .]\d{3})*|\d+)(?:\.\s?\d+)?", s):   # one number; dots/spaces as thousands marks
        return parse_value(s), ""
    toks = [m.group(0) for m in NUM_RE.finditer(s)]
    if not toks:
        return None, "nonnumeric"
    v = parse_value(toks[-1].replace(" .", ".").replace(". ", "."))
    return v, ("multi" if len(toks) > 1 else "")


def is_numeric_cell(c: str) -> bool:
    """A printed amount (or a dash), once footnote marks such as 'a/' are removed —
    not a label that merely ends in a footnote digit ('... Transportes 1/')."""
    c = re.sub(r"\b\d{1,2}\s*/|\b[a-zA-Z]\s*/", " ", c).strip()
    return bool(c) and re.fullmatch(r"[\d .,:$()\-–—]+", c) is not None and \
        (re.search(r"\d", c) is not None or re.fullmatch(r"[-–—.]+", c) is not None)


def azure_agency_rows(book: str, caption: str, value_col: str) -> list[dict]:
    """[(row_type, label, value, flag, parts_sum)] in reading order for one cuadro."""
    rows = []
    for t in tables_of(book, caption):
        g = grid(t)
        ncol = t["columnCount"]
        # label = first column(s) before the first numeric column; value = that column
        for r in g:
            cells = list(r)
            # the first column holding a number (or a dash) after a non-empty label
            label_parts, vi = [], None
            for j, c in enumerate(cells):
                if j > 0 and is_numeric_cell(c):
                    vi = j
                    break
                label_parts.append(c)
            label = " ".join(x for x in label_parts if x).strip()
            ln = norm_label(label)
            rt = row_type_of(ln)
            if rt is None:
                continue
            if vi is None:                               # column headers repeated on each page
                continue
            v, flag = cell_number(cells[vi])
            parts = None
            if ncol >= 6 and vi == 1:                         # Book B: SUMA = Σ financing columns
                ps = [cell_number(c)[0] for c in cells[2:]]
                if any(x is not None for x in ps):
                    parts = sum(x for x in ps if x is not None)
            rows.append({"row_type": rt, "label": label, "value": v, "flag": flag, "parts_sum": parts})
    return rows


# ── LLM reads ────────────────────────────────────────────────────────────────
def half_page(book: str, page: int, half: str) -> Image.Image:
    im = page_image(BOOKS[book]["pdf"], page)
    W, H = im.size
    x0, x1 = (0, W // 2) if half == "L" else (W // 2, W)
    im = im.crop((x0, 0, x1, H))
    if book == "b70":                       # tables printed sideways on the spread
        im = im.rotate(-90, expand=True)
    return im


def bands(im: Image.Image, book: str, n: int = 3, ov: float = 0.07) -> list[Image.Image]:
    W, H = im.size
    if book == "b70":
        im = im.crop((0, 0, int(0.64 * W), H))          # labels + SUMA column
    else:
        im = im.crop((int(0.04 * W), int(0.03 * H), int(0.97 * W), int(0.97 * H)))
    W, H = im.size
    step = H / n
    o = int(ov * H)
    return [im.crop((0, max(0, int(k * step) - o), W, min(H, int((k + 1) * step) + o))) for k in range(n)]


def llm_rows(client, model, tid, book, halves, title, col) -> list[dict]:
    """Rows read by `model` over the table's half-pages, in reading order; overlapping
    bands deduplicated (same label and value as the previous band's rows)."""
    prompt = PROMPT.format(book=BOOKS[book]["title"], title=title, col=col)
    jobs = []
    for page, half in halves:
        for k, crop in enumerate(bands(half_page(book, page, half), book)):
            jobs.append(((page, half, k), crop))
    with ThreadPoolExecutor(6) as pool:
        futs = {key: pool.submit(read_crop, client, model, crop, prompt,
                                 RAW_DIR / f"auth_{tid}_p{key[0]}{key[1]}_b{key[2]}_{model}.json")
                for key, crop in jobs}
        recs = {key: futs[key].result() for key, _ in jobs}
    out, prev = [], []
    for key, _ in jobs:
        block = []
        for r in recs[key]:
            lab = str(r.get("row_label", "")).strip()
            ln = norm_label(lab)
            if not ln:
                continue
            rt = r.get("row_type") if r.get("row_type") in ("total", "sector", "agency") else row_type_of(ln)
            if rt is None:
                continue
            if rt == "agency" and row_type_of(ln) in ("total", "sector"):
                rt = row_type_of(ln)
            block.append({"row_type": rt, "label": lab, "label_norm": ln,
                          "value": parse_value(r.get("value", ""))})
        raw = list(block)
        if key[2] > 0:                      # drop the overlap with the previous band (same label)
            tail = prev[-10:]
            block = [b for b in block if not any(similar(b["label_norm"], p["label_norm"]) >= 0.9 and
                                                 b["row_type"] == p["row_type"] for p in tail)]
        out.extend(block)
        prev = raw
    # a half-page can hold the tail of the previous cuadro above this one's TOTAL row and
    # the next cuadro's TOTAL below: keep the rows from this table's TOTAL to the next TOTAL
    tot = [i for i, r in enumerate(out) if r["row_type"] == "total"]
    if tot:
        out = out[tot[0]:(tot[1] if len(tot) > 1 else len(out))]
    return out


# ── assembling one table ─────────────────────────────────────────────────────
def with_sectors(rows: list[dict]) -> list[dict]:
    sec = None
    for r in rows:
        ln = norm_label(r["label"])
        r["label_norm"] = ln
        if r["row_type"] == "sector":
            sec = sector_key(ln)
            r["sector"] = sec
        elif r["row_type"] == "agency":
            r["sector"] = sec
        else:
            r["sector"] = None
    return rows


def align(az: list[dict], llm: list[dict]) -> list[tuple[dict, dict | None]]:
    """Pair each Azure row with the most similar unused LLM row of the same row_type
    (label similarity ≥ 0.82, searched near the running position); unmatched LLM agency
    rows with a value are appended as LLM-only rows."""
    used, pairs, pos = set(), [], 0
    for a in az:
        best, bi = 0.0, None
        for j, l in enumerate(llm):
            if j in used or l["row_type"] != a["row_type"]:
                continue
            s = similar(a["label_norm"], l["label_norm"]) - 0.002 * abs(j - pos)
            if s > best:
                best, bi = s, j
        if bi is not None and best >= 0.82:
            used.add(bi)
            pos = bi + 1
            pairs.append((a, llm[bi]))
        else:
            pairs.append((a, None))
    extra = [(None, l) for j, l in enumerate(llm) if j not in used and l["row_type"] == "agency"
             and l["value"] is not None]
    return pairs + extra


def build_table(client, spec, use_llm: bool) -> pd.DataFrame:
    tid, book, caption, year, concept, col, halves = spec
    title = {"b64": f"CUADRO No. {caption} INVERSION PUBLICA FEDERAL AUTORIZADA POR DEPENDENCIAS {year}",
             "b70": f"CUADRO {caption} INVERSION PUBLICA FEDERAL PROGRAMADA POR ENTIDADES DEL SECTOR "
                    f"PUBLICO, SEGUN FUENTES DE FINANCIAMIENTO {year or '1965-1970'}"}[book]
    az = with_sectors(azure_agency_rows(book, caption, col))
    if not az:
        raise RuntimeError(f"{tid}: no Azure table found under caption {caption}")
    recs = []
    if use_llm and halves:
        l1 = with_sectors(llm_rows(client, LLM_READER, tid, book, halves, title, col))
        pairs = align(az, l1)
        disagree = any((a is None) or (l is None) or (a["value"] != l["value"]) for a, l in pairs)
        l2 = {}
        if disagree:
            rows2 = with_sectors(llm_rows(client, LLM_TIEBREAK, tid, book, halves, title, col))
            # index tie-break rows by normalised label (fuzzy lookup below)
            l2 = {r["label_norm"]: r for r in rows2}
        for pos, (a, l) in enumerate(pairs):
            lab = (a or l)["label"]
            ln = (a or l)["label_norm"]
            va = a["value"] if a else None
            vl = l["value"] if l else None
            vc = None
            if l2:
                k = max(l2, key=lambda k: similar(k, ln), default=None)
                if k is not None and similar(k, ln) >= 0.82 and l2[k]["row_type"] == (a or l)["row_type"]:
                    vc = l2[k]["value"]
            if a is not None and l is not None and va == vl:
                final, flag = va, "agree"
            elif a is None:                 # a row Azure missed: kept only if the third read confirms it
                final, flag = (vl, "llm_only_confirmed") if vc == vl else (None, "llm_only_unconfirmed")
            elif l is None:
                final, flag = (va if vc == va else va), ("azure_only_confirmed" if vc == va else "azure_only")
            elif vc is not None and vc in (va, vl):
                final, flag = vc, "majority"
            else:
                final, flag = va, "unresolved"
            recs.append({"table": tid, "book": book, "caption": caption, "year": year, "concept": concept,
                         "row_order": pos, "row_type": (a or l)["row_type"], "sector": (a or l)["sector"],
                         "label": lab, "label_norm": ln, "read_azure": va, "read_llm": vl, "read_tiebreak": vc,
                         "azure_flag": a["flag"] if a else None, "parts_sum_azure": a["parts_sum"] if a else None,
                         "agreement": flag, "value_printed": final})
    else:
        for pos, a in enumerate(az):
            recs.append({"table": tid, "book": book, "caption": caption, "year": year, "concept": concept,
                         "row_order": pos, "row_type": a["row_type"], "sector": a["sector"], "label": a["label"],
                         "label_norm": a["label_norm"], "read_azure": a["value"], "read_llm": None,
                         "read_tiebreak": None, "azure_flag": a["flag"], "parts_sum_azure": a["parts_sum"],
                         "agreement": "azure_only", "value_printed": a["value"]})
    return pd.DataFrame(recs)


# ── manual corrections (printed evidence) ────────────────────────────────────
# (table, label prefix) → (value, why). Applied after the reads, flagged in `agreement`.
MANUAL_CORRECTIONS: dict[tuple[str, str], tuple[float, str]] = {}
# Rows to drop: OCR artefacts that are not rows of the table (table, label prefix) → why
DROP_ROWS: dict[tuple[str, str], str] = {}
# Two printed rows merged into one by the OCR: (table, merged label prefix) → [(label, value), ...], why
MANUAL_SPLITS: dict[tuple[str, str], tuple[list[tuple[str, float]], str]] = {
    ("b70_c9", "instituto mexicano de investigaciones tecnologicas instituto mexicano del cafe"): (
        [("Instituto Mexicano de Investigaciones Tecnológicas", 3.2), ("Instituto Mexicano del Café y Filial", 49.3)],
        "two consecutive rows read as one cell '3.2 49.3' (book p. 146); split as printed — with 3.2 "
        "the Organismos subtotal 74 184.1 closes"),
}


def apply_manual(long: pd.DataFrame) -> pd.DataFrame:
    long = long.copy()
    for (t, pref), (parts, why) in MANUAL_SPLITS.items():
        m = (long.table == t) & long.label_norm.str.startswith(pref)
        assert m.sum() == 1, (t, pref, int(m.sum()))
        base = long[m].iloc[0]
        new = []
        for k, (lab, v) in enumerate(parts):
            r = base.copy()
            r["label"], r["label_norm"], r["value_printed"] = lab, norm_label(lab), v
            r["row_order"] = base.row_order + k / 10
            r["agreement"] = "manual split: " + why
            new.append(r)
        long = pd.concat([long[~m], pd.DataFrame(new)], ignore_index=True)
    for (t, pref), (v, why) in MANUAL_CORRECTIONS.items():
        m = (long.table == t) & long.label_norm.str.startswith(pref)
        assert m.sum() == 1, (t, pref, m.sum())
        long.loc[m, ["value_printed", "agreement"]] = [v, "manual: " + why]
    for (t, pref), why in DROP_ROWS.items():
        m = (long.table == t) & long.label_norm.str.startswith(pref)
        assert m.sum() >= 1, (t, pref)
        long = long[~m]
    return long


# ── validation ───────────────────────────────────────────────────────────────
def checks(g: pd.DataFrame) -> dict:
    ag = g[g.row_type == "agency"].groupby("sector").value_printed.sum(min_count=1)
    sec = g[g.row_type == "sector"].drop_duplicates("sector").set_index("sector").value_printed
    tot = g[g.row_type == "total"].value_printed
    tot = tot.iloc[0] if len(tot) else None
    gaps = {s: round((ag.get(s, 0) or 0) - sec[s], 2) for s in sec.index if pd.notna(sec[s])}
    sum_sec = sec.sum(min_count=1)
    tol = lambda x, ref: x is not None and pd.notna(x) and abs(x) <= max(0.15, 1e-4 * abs(ref or 0))
    out = {"total_printed": tot, "sum_sectors": sum_sec,
           "total_gap": None if tot is None or pd.isna(tot) else round(sum_sec - tot, 2),
           "max_sector_gap": max((abs(v) for v in gaps.values()), default=None),
           "sector_gaps": "; ".join(f"{k}:{v:+.1f}" for k, v in gaps.items())}
    out["balanced"] = bool(all(tol(v, tot) for v in gaps.values()) and tol(out["total_gap"], tot))
    rs = g[(g.row_type == "agency") & g.parts_sum_azure.notna() & g.value_printed.notna()]
    rg = (rs.value_printed - rs.parts_sum_azure).abs()
    out["rows_with_parts"] = int(len(rs))
    out["rows_parts_mismatch"] = int((rg > 0.15).sum())
    return out


def reconcile(long: pd.DataFrame) -> pd.DataFrame:
    """A single cell whose alternative read (or the Azure sum of its financing columns)
    restores the table's identities is taken from that alternative."""
    long = long.copy()
    for t, g in long.groupby("table"):
        if checks(g)["balanced"]:
            continue
        fixes = []
        for i in g.index:
            alts = {long.at[i, c] for c in ("read_azure", "read_llm", "read_tiebreak", "parts_sum_azure")}
            alts = {a for a in alts if a is not None and pd.notna(a)} - {long.at[i, "value_printed"]}
            for alt in alts:
                trial = long.loc[g.index].copy()
                trial.at[i, "value_printed"] = alt
                if checks(trial)["balanced"]:
                    fixes.append((i, alt))
        if len(fixes) == 1:
            i, alt = fixes[0]
            long.loc[i, ["value_printed", "agreement"]] = [alt, "reconciled"]
    return long


# Entities renamed between tables (normalised label → canonical label used for matching)
ALIASES = {
    "secretaria de agricultura": "secretaria de agricultura y ganaderia",
    "banco nacional hipotecario urbano y de obras publicas": "banco nacional de obras y servicios publicos",
    "patronato para las obras del instituto politecnico nacional": "patronato de obras e instalaciones del instituto politecnico nacional",
    "patronato de obras e instalaciones del instituto politecni co nacional": "patronato de obras e instalaciones del instituto politecnico nacional",
    "nueva compania electrica de chapala": "nueva compania electrica chapala",
    "cooperativa de ejidatarios y obreros del ingenio del mante": "sociedad cooperativa de ejidatarios y obreros del ingenio del mante",
    "cooperativa de obreros de vestuario y equipo": "sociedad cooperativa de obreros de vestuario y equipo",
    "nacional financiera ingenios": "ingenios en fideicomiso de nacional financiera",
    "compania nacional de subsistencias populares y empresas filiates": "compania nacional de subsistencias populares y empresas filiales",
    "malz industrializado": "maiz industrializado",
    "comision nacional de estudios del territorio nacional y planeacion": "comision de estudios del territorio nacional y planeacion",
    "fondo de garantia y fomento a la industria": "fondo de garantia y fomento a la industria mediana y pequena",
    "hospital de enfermedades de la nutricion": "instituto nacional de la nutricion",
    "ingenio emiliano zapata": "sociedad cooperativa de ejidatarios y obreros del ingenio emiliano zapata",
    "fabricas de papel de tuxtepec": "fabricas de papel tuxtepec",
    "centro materno infantil gral maximimo avila camacho": "centro materno infantil gral maximino avila camacho",
}
# Year-specific aliases for the 1965–1970 sum check: (table, label) → canonical
SUM_ALIASES = {("b70_c10", "nacional financiera"): "ingenios en fideicomiso de nacional financiera",
               ("b64_c6", "nacional financiera"): "ingenios en fideicomiso de nacional financiera"}
# Rows that one printing lists separately and the other consolidates: canonical label of the
# consolidated row → labels it absorbs (verified: the parts add up exactly, see validation)
CONSOLIDATIONS_SUM = {
    # Book B Cuadro 9 (1965–70 sum) folds the electric companies absorbed by CFE in 1967–68
    # into its CFE row (the yearly tables list them under Empresas in 1965–67)
    "comision federal de electricidad": ["industrial electrica mexicana", "nueva compania electrica chapala",
                                         "compania electrica guzman", "compania electrica manzanillo",
                                         "compania electrica morelia", "compania hidroelectrica occidental"],
}
CONSOLIDATIONS = {
    # Book B lists the national agricultural banks 'y filiales' (Book A lists the subsidiaries)
    "banco nacional agropecuario": ["banco agropecuario del noreste", "banco agropecuario del noroeste",
                                    "banco agropecuario del sureste", "banco provincial de sinaloa",
                                    "banco agropecuario de occidente", "banco agropecuario del norte",
                                    "banco agropecuario del sur"],
    "banco nacional de credito agricola": ["banco de zamora"],
    "banco nacional de credito ejidal": ["banco agrario de yucatan", "banco agrario de michoacan", "empacadora ejidal"],
    "banco nacional de fomento cooperativo": ["refrigeradora del noroeste"],
    "compania nacional de subsistencias populares y empresas filiales": ["maiz industrializado"],
    "instituto mexicano del cafe": ["beneficios mexicanos del cafe"],
}


def canon(label_norm: str, table: str | None = None) -> str:
    if table is not None and (table, label_norm) in SUM_ALIASES:
        return SUM_ALIASES[(table, label_norm)]
    return ALIASES.get(label_norm, label_norm)


def reconcile_with_sum(long: pd.DataFrame) -> pd.DataFrame:
    """Yearly cells whose Azure SUMA disagrees with the sum of its financing columns (or
    with another read): take the alternative when it closes that entity's 1965–1970 sum
    identity exactly (Cuadro 9) — e.g. three cells of the 1969 table that Azure read as
    '0.0'/'1.0' (IMSS 460.0, INAH 15.0, Patronato del Ahorro 4.1; book p. 165)."""
    long = long.copy()
    s = long[(long.table == SUM_TABLE) & (long.row_type == "agency")]
    sums = {canon(l): v for l, v in zip(s.label_norm, s.value_printed)}
    yr = long.table.isin(YEAR_TABLES) & (long.row_type == "agency")
    keys = pd.Series([canon(l, t) for l, t in zip(long.label_norm, long.table)], index=long.index)
    for k, target in sums.items():
        idx = long.index[yr & (keys == k)]
        if not len(idx) or pd.isna(target):
            continue
        gap = target - long.loc[idx, "value_printed"].sum()
        if abs(gap) <= 0.15:
            continue
        fixes = []
        for i in idx:
            alts = {long.at[i, c] for c in ("read_llm", "read_tiebreak", "parts_sum_azure", "read_azure")}
            for alt in {a for a in alts if a is not None and pd.notna(a)} - {long.at[i, "value_printed"]}:
                if abs(alt - long.at[i, "value_printed"] - gap) <= 0.15:
                    fixes.append((i, alt))
        if len(fixes) == 1:
            i, alt = fixes[0]
            long.loc[i, ["value_printed", "agreement"]] = [alt, "reconciled_sum1965_70"]
    return long


def fold(rows: list[tuple[str, float]], groups: dict) -> list[tuple[str, float]]:
    """Fold the subsidiaries listed in `groups` into their consolidated row (created if the
    table lists only the parts); the label records what was folded."""
    rows = list(rows)
    for canon_lab, parts in groups.items():
        hit = [(l, v) for l, v in rows if l in parts]
        if not hit:
            continue
        base = [(l, v) for l, v in rows if l == canon_lab]
        rows = [(l, v) for l, v in rows if l not in parts and l != canon_lab]
        v = sum(x[1] or 0 for x in base) + sum(x[1] or 0 for x in hit)
        rows.append((canon_lab + " (+ " + ", ".join(l for l, _ in hit) + ")", v))
    return rows


def match_rows(a: pd.DataFrame, b: pd.DataFrame, cutoff=0.9, fold_a=None, fold_b=None) -> list[tuple]:
    """Pair agency rows of two tables by canonical label (exact first, then the most similar
    pairs ≥ cutoff) → [(label_a, label_b, va, vb)]; unmatched rows carry None."""
    A = [(canon(r.label_norm, r.table), r.value_printed) for _, r in a[a.row_type == "agency"].iterrows()]
    B = [(canon(r.label_norm, r.table), r.value_printed) for _, r in b[b.row_type == "agency"].iterrows()]
    if fold_a:
        A = fold(A, fold_a)
    if fold_b:
        B = fold(B, fold_b)
    base = lambda l: l.split(" (+")[0]
    cand = sorted(((similar(base(la), base(lb)), i, j) for i, (la, _) in enumerate(A) for j, (lb, _) in enumerate(B)
                   if similar(base(la), base(lb)) >= cutoff), reverse=True)
    ua, ub, pairs = set(), set(), {}
    for s_, i, j in cand:
        if i in ua or j in ub:
            continue
        ua.add(i); ub.add(j); pairs[i] = j
    out = [(A[i][0], B[pairs[i]][0], A[i][1], B[pairs[i]][1]) if i in pairs else (A[i][0], None, A[i][1], None)
           for i in range(len(A))]
    out += [(None, B[j][0], None, B[j][1]) for j in range(len(B)) if j not in ub]
    return out




def cross_checks(long: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for ta, tb, y in CROSS:
        a, b = long[long.table == ta], long[long.table == tb]
        for la, lb, va, vb in match_rows(a, b, fold_a=CONSOLIDATIONS, fold_b=CONSOLIDATIONS):
            d = None if va is None or vb is None or pd.isna(va) or pd.isna(vb) else round(va - vb, 2)
            rows.append({"check": "cross_printing", "year": y, "table_a": ta, "table_b": tb,
                         "label_a": la, "label_b": lb, "value_a": va, "value_b": vb, "diff": d})
    # 1965–1970 sum table vs the six yearly tables (yearly rows pooled by canonical label)
    s = long[long.table == SUM_TABLE]
    yr = long[long.table.isin(YEAR_TABLES) & (long.row_type == "agency")].copy()
    yr["key"] = [canon(l, t) for l, t in zip(yr.label_norm, yr.table)]
    pooled = yr.groupby("key").agg(value_printed=("value_printed", "sum"), n=("value_printed", "count"),
                                   labels=("label_norm", lambda x: ", ".join(sorted(set(x)))[:120])).reset_index()
    pooled["row_type"], pooled["table"], pooled["label_norm"] = "agency", "pooled", pooled.key
    for la, lb, va, vb in match_rows(s, pooled, fold_b={**CONSOLIDATIONS, **CONSOLIDATIONS_SUM}):
        n = int(pooled[pooled.key == lb.split(" (+")[0]].n.sum()) if lb else 0
        rows.append({"check": "sum_1965_1970", "year": None, "table_a": SUM_TABLE, "table_b": "c10..c15",
                     "label_a": la, "label_b": lb, "value_a": va, "value_b": vb,
                     "diff": None if va is None or vb is None or pd.isna(va) or pd.isna(vb) else round(va - vb, 2),
                     "n_years_found": n})
    for t in [SUM_TABLE] + YEAR_TABLES:
        g = long[long.table == t]
        for rt in ("total", "sector"):
            for _, r in g[g.row_type == rt].iterrows():
                m = s[(s.row_type == rt) & (s.sector == r.sector)] if rt == "sector" else s[s.row_type == "total"]
                rows.append({"check": "sum_1965_1970_" + rt, "year": r.year, "table_a": t, "table_b": SUM_TABLE,
                             "label_a": r.label_norm, "label_b": None, "value_a": r.value_printed,
                             "value_b": m.value_printed.iloc[0] if len(m) else None, "diff": None})
    return pd.DataFrame(rows)


# ── purpose tables (Azure only) ──────────────────────────────────────────────
def purpose_rows(spec) -> pd.DataFrame:
    tid, book, caption, concept, years = spec
    recs = []
    for t in tables_of(book, caption):
        g = grid(t)
        ncol = t["columnCount"]
        for r in g:
            if ncol >= 15:                               # Book B: label col 1, (mn, %) pairs
                label = r[1]
                vals = [r[2 + 2 * k] for k in range(len(years))]
            else:                                        # Book A destino tables: label cols, Total, %
                nums = [j for j, c in enumerate(r) if cell_number(c)[0] is not None]
                if not nums:
                    continue
                vi = nums[0]
                label = " ".join(x for x in r[:vi] if x).strip()
                vals = [r[vi]]
            ln = norm_label(re.sub(r"^\s*([ivx]+|[a-h]|\d)\s*[.)]\s*-?\s*", "", label, flags=re.I))
            if not ln or re.fullmatch(r"concepto|millones de pesos|porciento", ln):
                continue
            for y, cell in zip(years, vals):
                v, flag = cell_number(cell)
                con = "programmed" if (tid in PURPOSE_1970_IS_PROGRAMMED and y == 1970) else concept
                if cell.strip().lower().startswith("inap"):
                    v, flag = None, "inap"
                recs.append({"table": tid, "book": book, "caption": caption, "concept": con,
                             "year": y if y else "sum_1965_1970", "label": label.strip(), "label_norm": ln,
                             "cell_printed": cell, "azure_flag": flag, "value_printed": v})
    d = pd.DataFrame(recs)
    # the wrapped group label 'EQUIPOS E INSTALACIONES PARA ADMINISTRACION Y / DEFENSA' is
    # read as two rows: the values are on the 'DEFENSA' line
    drop = []
    for i in d.index:
        if d.at[i, "label_norm"] == "defensa" and i > 0:
            j = d.index[(d.table == d.at[i, "table"]) & (d.year == d.at[i, "year"]) &
                        d.label_norm.str.startswith("equipos e instalaciones")]
            if len(j):
                d.loc[j[0], ["value_printed", "cell_printed", "azure_flag"]] = [d.at[i, "value_printed"], d.at[i, "cell_printed"], "wrapped"]
                drop.append(i)
    d = d.drop(index=drop)
    d["row_order"] = d.groupby(["table", "year"]).cumcount()
    return d


# levels of the objeto del gasto classification (Book B Cuadros 1 and 16)
PURPOSE_GROUPS = {"industrial": ["petroleo y petroquimica", "electricidad", "siderurgia", "otras inversiones"],
                  "bienestar social": ["obras de servicio urbano y rural", "escuelas",
                                       "hospitales y centros asistenciales", "vivienda", "otras inversiones"],
                  "transportes y comunicaciones": ["carreteras", "ferrocarriles", "comunicaciones aereas",
                                                   "telecomunicaciones", "obras maritimas", "otras inversiones"],
                  "fomento agropecuario y pesquero": ["agricultura", "ganaderia", "forestal", "pesca",
                                                      "otras inversiones"],
                  "equipos e instalaciones para administracion y defensa": []}
# (table, year, label prefix) → (value, why). The 1966 column of Cuadro 16 and parts of
# Cuadro 1 lie in the gutter of the scan (book pp. 137 and 173): their first digit is cut off.
# Each value below is pinned by two identities (items = group, groups = total) and, for the
# totals, by INEGI EHM 2014 Cuadro 16.27 / the book's own p. 5 table.
PURPOSE_MANUAL: dict[tuple[str, object, str], tuple[float, str]] = {
    ("b70_c16", 1966, "total"): (15475.0, "scan shows '5 475.0' (first digit in the gutter); groups sum to 15 475.0 = EHM 16.27"),
    ("b70_c16", 1966, "industrial"): (7718.9, "scan shows '1 718.9'; items 4 623.2+2 395.0+317.0+383.7 = 7 718.9"),
    ("b70_c16", 1966, "bienestar social"): (3424.5, "scan shows '$ 424.5'; items 1 865.2+588.9+804.0+142.3+24.1 = 3 424.5"),
    ("b70_c16", 1966, "transportes y comunicaciones"): (2901.7, "scan shows ': 901.7'; items 1 965.7+692.3+109.7+134.0 = 2 901.7"),
    ("b70_c1", 1966, "total"): (20668.9, "scan shows '9 668.9'; groups sum to 20 668.9 = Book A Cuadro 12 total"),
    ("b70_c1", 1966, "bienestar social"): (4569.3, "scan shows '1569.3'; items 1 957.9+891.6+826.5+833.8+59.5 = 4 569.3"),
    ("b70_c1", 1966, "obras de servicio urbano y rural"): (1957.9, "scan shows '957.9'; Book A Cuadro 13 prints 'Servicios municipales 1 957.9'; "
                                                                   "the group 4 569.3 then closes"),
    ("b70_c16", 1966, "obras de servicio urbano y rural"): (1865.2, "scan shows '865.2'; group 3 424.5 − (588.9+804.0+142.3+24.1) = 1 865.2, "
                                                                    "and the printed share 12.1% of 15 475 = 1 872"),
    ("b70_c1", 1968, "bienestar social"): (6035.0, "OCR read '6 085.0'; items 3 530.0+1 030.0+1 025.0+425.0+25.0 = 6 035.0 and the "
                                                    "groups then add to the printed total 24 500.0 (24.6% of 24 500 = 6 027)"),
}


def purpose_structure(d: pd.DataFrame) -> pd.DataFrame:
    """Attach group / level to the objeto del gasto rows (in reading order)."""
    d = d.copy()
    d["group"], d["level"] = None, None
    for (t, y), g in d.groupby(["table", "year"]):
        if not t.startswith("b70"):
            continue
        grp = None
        for i in g.sort_values("row_order").index:
            ln = d.at[i, "label_norm"]
            if ln.startswith("total"):
                d.at[i, "level"], d.at[i, "group"] = 0, None
                continue
            gk = next((k for k in PURPOSE_GROUPS if similar(ln, k) >= 0.8 or ln.startswith(k[:20])), None)
            if gk and not ln.startswith("otras"):
                grp, d.at[i, "level"], d.at[i, "group"] = gk, 1, gk
            else:
                d.at[i, "level"], d.at[i, "group"] = 2, grp
    return d


def purpose_validation(d: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (t, y), g in d.groupby(["table", "year"]):
        if not t.startswith("b70"):                      # Book A destino: top-level groups are upper-case
            tot = g[g.label_norm.str.startswith("total")].value_printed
            tot = tot.iloc[0] if len(tot) else None
            top = g[g.label.str.replace(r"[^A-Za-zÁÉÍÓÚÑ]", "", regex=True).str.isupper() &
                    ~g.label_norm.str.startswith("total") & ~g.label_norm.str.startswith("sector ")]
            top = pd.concat([top, g[g.label_norm.str.startswith("sector ")]])
            sg = top.value_printed.sum()
            rows.append({"table": t, "year": y, "check": "destino_total_vs_groups", "total_printed": tot,
                         "sum_groups": sg, "gap": None if tot is None else round(sg - tot, 2),
                         "balanced": tot is not None and abs(sg - tot) <= 0.15,
                         "group_gaps": "; ".join(f"{l}:{v}" for l, v in zip(top.label_norm, top.value_printed))})
            continue
        tot = g[g.level == 0].value_printed.iloc[0]
        grp = g[g.level == 1].set_index("group").value_printed
        items = g[g.level == 2].groupby("group").value_printed.sum(min_count=1)
        gaps = {k: round(items.get(k, 0) - grp[k], 2) for k in grp.index if pd.notna(grp[k]) and k in items.index}
        tg = round(grp.sum() - tot, 2) if pd.notna(tot) else None
        ok = all(abs(v) <= 0.15 for v in gaps.values()) and tg is not None and abs(tg) <= 0.15
        rows.append({"table": t, "year": y, "check": "groups_and_total", "total_printed": tot, "sum_groups": grp.sum(),
                     "gap": tg, "balanced": ok, "group_gaps": "; ".join(f"{k}:{v:+.1f}" for k, v in gaps.items())})
    # SUMA 1965–1970 = Σ years, per row (Book B)
    for t in ("b70_c1", "b70_c16"):
        g = d[d.table == t]
        s = g[g.year == "sum_1965_1970"].set_index("row_order").value_printed
        yrs = g[g.year != "sum_1965_1970"].groupby("row_order").value_printed.sum(min_count=1)
        bad = [(int(i), round(s[i] - yrs.get(i, 0), 1)) for i in s.index if pd.notna(s[i]) and abs(s[i] - (yrs.get(i, 0) or 0)) > 0.15]
        rows.append({"table": t, "year": "sum_1965_1970", "check": "suma_equals_sum_of_years", "total_printed": None,
                     "sum_groups": None, "gap": None, "balanced": not bad,
                     "group_gaps": "; ".join(f"row{i}:{v:+.1f}" for i, v in bad)})
    # realized totals vs INEGI EHM 2014 Cuadro 16.27
    g = d[(d.table == "b70_c16") & (d.level == 0)]
    for _, r in g.iterrows():
        if r.year in EHM_REALIZED_TOTAL and r.year != 1970:      # the 1970 column is programmed
            rows.append({"table": "b70_c16", "year": r.year, "check": "total_vs_EHM_16.27", "total_printed": r.value_printed,
                         "sum_groups": EHM_REALIZED_TOTAL[r.year], "gap": round(r.value_printed - EHM_REALIZED_TOTAL[r.year], 1),
                         "balanced": abs(r.value_printed - EHM_REALIZED_TOTAL[r.year]) < 1})
    return pd.DataFrame(rows)


def main():
    use_llm = "--no-llm" not in sys.argv
    client = None
    if use_llm:
        import openai
        client = openai.OpenAI(api_key=openai_api_key())
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    only = {a for a in sys.argv[1:] if not a.startswith("--")}

    parts = []
    for spec in AGENCY_TABLES:
        if only and spec[0] not in only:
            continue
        d = build_table(client, spec, use_llm)
        n_dis = int((~d.agreement.isin(["agree", "azure_only"])).sum())
        print(f"  {spec[0]:8s} rows={len(d):4d} agencies={(d.row_type == 'agency').sum():3d} "
              f"not-agreeing={n_dis}")
        parts.append(d)
    long = pd.concat(parts, ignore_index=True)
    long = apply_manual(long)
    long = reconcile(long)
    long = reconcile_with_sum(long)
    long = reconcile(long)
    long["units"] = "millions_old_pesos"
    long["value_mn_new_pesos"] = long.value_printed / 1000
    long["block"] = long.sector.map({"gobierno_federal": "dependencias", "organismos_descentralizados": "paraestatal",
                                     "empresas_participacion_estatal": "paraestatal"})
    long.to_csv(OUT_LONG, index=False)

    val = pd.DataFrame([{"table": t, "year": g.year.iloc[0], "concept": g.concept.iloc[0], **checks(g),
                         "n_agencies": int((g.row_type == "agency").sum()),
                         "agreement": ", ".join(f"{k}={v}" for k, v in g.agreement.str.split(":").str[0].value_counts().items())}
                        for t, g in long.groupby("table")])
    xc = cross_checks(long)
    val = pd.concat([val, xc], ignore_index=True, sort=False)
    val.to_csv(OUT_VAL, index=False)

    purpose = pd.concat([purpose_rows(s) for s in PURPOSE_TABLES], ignore_index=True)
    for (t, y, pref), (v, why) in PURPOSE_MANUAL.items():
        m = (purpose.table == t) & (purpose.year.astype(str) == str(y)) & purpose.label_norm.str.startswith(pref)
        assert m.sum() == 1, (t, y, pref, int(m.sum()))
        purpose.loc[m, ["value_printed", "azure_flag"]] = [v, "manual: " + why]
    purpose = purpose_structure(purpose)
    pv = purpose_validation(purpose)
    purpose["units"] = "millions_old_pesos"
    purpose.to_csv(OUT_PURPOSE, index=False)
    pv.to_csv(OUT_VAL.with_name("investment_purpose_programmed_realized_1964_1970_validation.csv"), index=False)

    print("\nagreement:", long.agreement.str.split(":").str[0].value_counts().to_dict())
    print(val[val.check.isna()][["table", "year", "n_agencies", "total_printed", "sum_sectors", "total_gap",
                                 "max_sector_gap", "rows_parts_mismatch", "balanced"]].to_string(index=False))
    x = xc[(xc.check == "cross_printing") & (xc["diff"].fillna(0) != 0)]
    print(f"\ncross-printing differences: {len(x)} rows (see validation file)")
    x = xc[(xc.check == "cross_printing") & (xc.label_a.isna() | xc.label_b.isna())]
    print(f"cross-printing unmatched rows: {len(x)}")
    s = xc[xc.check == "sum_1965_1970"]
    print(f"1965–70 sum check: {int((s['diff'].abs() <= 0.15).sum())} of {len(s)} entities add up to Cuadro 9")
    print(pv.to_string(index=False))
    print(f"→ {OUT_LONG}\n→ {OUT_VAL}\n→ {OUT_PURPOSE}")


if __name__ == "__main__":
    main()
