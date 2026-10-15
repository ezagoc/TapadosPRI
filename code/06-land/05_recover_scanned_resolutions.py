"""
Recover hectares, beneficiaries, signing date / president, land classes and file-history dates of the Diario Oficial
land-grant resolutions that SIDOF holds only as a scan (no HTML text), from the scanned edition PDFs.

Targets: the DOF land-grant resolutions of the ledger (config.AGRARIAN_LEDGER_CSV) without a SIDOF full text: action_id
"DOF<codNota>", is_land_grant_action == 1, a resolucion, has_fulltext == 0 (429 notes, Nov 1976 - 1991, in 189
editions). The selection uses only columns 04 copies from 03 unchanged, so it is the same before and after 04 merges this
script's table into the ledger (04_build_agrarian_ledger.py reads config.DOF_SCANNED_RESOLUTIONS_CSV).

Modes (each resumable; re-run in this order)
  harvest  For each edition (codDiario), sequentially and politely (>= 1 s between requests, 5 tries with back-off,
           done-list): fetch each target's note record (.../notas/nota/<codNota>: codSeccion, pagina, codEdicion),
           download the whole edition (.../documentos/pdf/<codDiario>) to the LOCAL work folder
           config.DOF_SCANNED_LOCAL_DIR (never Dropbox; sha256 while downloading), write its whole text layer
           (pdftotext -layout, one JSON line per PDF page) to config.DOF_SCANNED_EDITIONS_DIR and one MANIFEST row (in
           place, under the file lock that 06_reparse_dof_texts.py also takes), keep a column-ordered text of every page
           (word boxes split at the column gutters, band by band: Paper Capture lines run across both columns) and
           single-page PDFs around each target, then delete the PDF.
  parse    Locate each resolution and parse it, in the text layer and in the second OCR:
             - location: expected page = section cover (or calibrated section offset) + printed page - 1; best fuzzy
               alignment of the index title with village / municipality checks, "Al margen" / "VISTO" bonuses and
               penalties for the closing "Publiquese ... la presente resolucion" and the resolutive points; table-of-
               contents pages excluded; a second pass with the section offsets learned from confident matches; end =
               the closing formula, never past the next resolution ("Al margen un sello" / "VISTO" / "RESULTANDO
               PRIMERO.-" after a heading);
             - OCR repairs that change no content (soft hyphens, "()"/O/l for 0/1, separators in amounts, four-group
               ha-a-ca-dm2 amounts, garbled units and concession verbs, amounts in words re-segmented, fuzzy number and
               month words in the closing formula, "se resuelve" restored), then 03's parse_body / parse_signing /
               parse_stages;
             - an amount counts only when the village is named next to it and no amount in words precedes it;
             - combination: digits = words in the text layer (and in the second OCR when both read it) -> text_layer;
               only in the second OCR -> local_ocr; digits re-read to match the words -> text_layer_words /
               local_ocr_words; conflicts and the rest -> page images.
           One .txt per codNota (both OCRs, header: edition file, PDF pages) in config.DOF_SCANNED_TEXTS_DIR.
  ocr      tesseract 5 (300 dpi, eng) on every kept page of each resolution: the second, independent OCR (and the only
           one for the editions without a text layer).
  refetch  Re-download editions whose located resolutions span pages not kept at harvest (sha256 must match).
  vision   Crops of the resolutive points (+ closing formula) read by two pinned vision models, a third on
           disagreement (05-investment/llm_tables.py: cache, budget guard LLM_BUDGET_USD on the cumulative ledger).
  sheets   The same crops, labelled, for reading by hand when the vision step cannot run (no OpenAI credit on
           2026-10-14); readings go to DOF_SCANNED_TEXTS_DIR/image_reads.csv (method image_read).
  handcheck  Draw 40 recovered resolutions (seed 2026) and render their pages; the truth read by hand goes to
             handcheck_truth.csv and is scored against handcheck_extracted_at_sampling.csv.
  build    Final table config.DOF_SCANNED_RESOLUTIONS_CSV, config.DOF_SCANNED_VALIDATION_CSV (digits vs words per OCR,
           OCR vs OCR, image reads vs OCR, hand check), 100 dpi grayscale PNGs of the pages read by hand, MANIFEST pages.

Downloads are untrusted data: they are only read with poppler (pdftotext, pdfinfo, pdfseparate, pdftoppm) and
tesseract and parsed as text; run this script with `python -I` from outside the download folder.

Run:
  export DOF_SCANNED_LOCAL_DIR=/private/tmp/claude-501/dof_editions
  python -I code/06-land/05_recover_scanned_resolutions.py harvest
  python -I code/06-land/05_recover_scanned_resolutions.py parse
  python -I code/06-land/05_recover_scanned_resolutions.py ocr
  python -I code/06-land/05_recover_scanned_resolutions.py refetch
  python -I code/06-land/05_recover_scanned_resolutions.py parse
  LLM_BUDGET_USD=45 python -I code/06-land/05_recover_scanned_resolutions.py vision    # or: sheets (read by hand)
  python -I code/06-land/05_recover_scanned_resolutions.py build
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import gzip
import hashlib
import html as html_lib
import importlib.util
import io
import json
import re
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz, process
from rapidfuzz.distance import Levenshtein

CODE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import (  # noqa: E402
    AGRARIAN_LEDGER_CSV, DOF_SIDOF_INDEX_DIR, DOF_SCANNED_EDITIONS_DIR, DOF_SCANNED_TEXTS_DIR, DOF_SCANNED_LOCAL_DIR,
    DOF_SCANNED_RESOLUTIONS_CSV, DOF_SCANNED_VALIDATION_CSV, openai_api_key,
)
from dof_agrarian_utils import iter_jsonl, index_files, norm  # noqa: E402


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


P03 = _load("dof03_parse", Path(__file__).resolve().parent / "03_parse_dof_agrarian.py")

NOTE_URL = "https://sidof.segob.gob.mx/dof/sidof/notas/nota/{}"
PDF_URL = "https://sidof.segob.gob.mx/dof/sidof/documentos/pdf/{}"
UA = "Mozilla/5.0 (academic research; TapadosPRI land-reform project)"
MIN_INTERVAL = 1.5          # seconds between the start of two requests (>= 1 s asked)

LOCAL = DOF_SCANNED_LOCAL_DIR
NOTES_DIR = LOCAL / "notes"           # cached note records (JSON)
PDF_DIR = LOCAL / "pdf"               # edition PDFs while being read (deleted after)
COLTEXT_DIR = LOCAL / "coltext"       # column-ordered page text + line boxes per edition
PAGES_DIR = LOCAL / "pages"           # single-page PDFs around each target
RENDER_DIR = LOCAL / "render"         # page renders for vision crops and the hand check
PARSED_JSONL = LOCAL / "parsed.jsonl"
DONE_FILE = LOCAL / "done_editions.txt"
MANIFEST = DOF_SCANNED_EDITIONS_DIR / "MANIFEST.csv"
MANIFEST_COLS = ["source_url", "codDiario", "date", "codEdicion", "http_status", "content_type", "bytes", "sha256",
                 "n_pages", "pdf_producer", "downloaded_at", "extracted_with", "edition_text_file", "codNotas_pdf_pages"]
VISION_CACHE = DOF_SCANNED_TEXTS_DIR / "vision_cache"
HANDCHECK_TRUTH = DOF_SCANNED_TEXTS_DIR / "handcheck_truth.csv"
HANDCHECK_EXTRACTED = DOF_SCANNED_TEXTS_DIR / "handcheck_extracted_at_sampling.csv"

SECTION_ORD = {"UNICA": 1, "PRIMERA": 1, "SEGUNDA": 2, "TERCERA": 3, "CUARTA": 4, "QUINTA": 5, "SEXTA": 6,
               "SEPTIMA": 7, "OCTAVA": 8, "NOVENA": 9, "DECIMA": 10, "DECIMA PRIMERA": 11, "DECIMA SEGUNDA": 12,
               "DECIMA TERCERA": 13, "DECIMA CUARTA": 14, "DECIMA QUINTA": 15, "DECIMA SEXTA": 16,
               "DECIMA SEPTIMA": 17, "DECIMA OCTAVA": 18, "DECIMA NOVENA": 19, "VIGESIMA": 20}


# ============================================================================================== HTTP
_LAST = [0.0]


def polite_get(url: str, dest: Path | None = None, tries: int = 5):
    """GET with >= MIN_INTERVAL s between requests and exponential back-off. Returns (status, content_type, body)
    where body = bytes, or (bytes_written, sha256) when `dest` is given (streamed to dest)."""
    last_err = None
    for k in range(tries):
        wait = MIN_INTERVAL - (time.monotonic() - _LAST[0])
        if wait > 0:
            time.sleep(wait)
        _LAST[0] = time.monotonic()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=300) as r:
                status, ctype = r.status, r.headers.get("Content-Type")
                clen = r.headers.get("Content-Length")
                if dest is None:
                    body = r.read()
                    _LAST[0] = time.monotonic()
                    return status, ctype, body
                h, n = hashlib.sha256(), 0
                tmp = dest.with_suffix(".part")
                with open(tmp, "wb") as fh:
                    while True:
                        chunk = r.read(1 << 20)
                        if not chunk:
                            break
                        fh.write(chunk)
                        h.update(chunk)
                        n += len(chunk)
                _LAST[0] = time.monotonic()
                if clen is not None and int(clen) != n:
                    raise OSError(f"truncated download: {n} of {clen} bytes")
                tmp.rename(dest)
                return status, ctype, (n, h.hexdigest())
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            last_err = e
            if getattr(e, "code", None) == 404:
                return 404, None, None
            print(f"  request error ({k + 1}/{tries}) {url}: {e!r}", flush=True)
            time.sleep(min(160, 5 * 2 ** k))
    print(f"  giving up on {url}: {last_err!r}", flush=True)
    return None, None, None


def note_record(cod: int) -> dict | None:
    """The SIDOF note record (cached)."""
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    fn = NOTES_DIR / f"{cod}.json"
    if fn.exists():
        return json.loads(fn.read_text())
    status, _, body = polite_get(NOTE_URL.format(cod))
    if status != 200 or not body:
        return None
    j = json.loads(body.decode("utf-8"))
    if not isinstance(j, dict) or j.get("messageCode") not in (200, "200") or not isinstance(j.get("Nota"), dict):
        return None
    rec = {k: v for k, v in j["Nota"].items() if k != "cadenaContenido"}
    fn.write_text(json.dumps(rec, ensure_ascii=False))
    return rec


# ============================================================================================ targets
def load_targets() -> pd.DataFrame:
    """The 429 land-grant DOF resolutions without full text, with their daily-index metadata. Selected on columns 04
    takes from 03 unchanged (not on is_land_grant / hectares_total, which 04 fills from this script's table)."""
    led = pd.read_csv(AGRARIAN_LEDGER_CSV, low_memory=False,
                      usecols=["action_id", "is_land_grant_action", "action_detail", "has_fulltext", "dof_date",
                               "dof_codNota", "dof_title", "action_type", "poblado", "poblado_alias", "ncpe_name",
                               "municipality_dof", "state_code", "president_signing", "president_in_office_at_dof"])
    t = led[(led.is_land_grant_action == 1) & led.action_id.astype(str).str.startswith("DOF")
            & led.action_detail.astype(str).str.startswith("resolucion") & (led.has_fulltext == 0)].copy()
    t["codNota"] = t["dof_codNota"].astype(int)
    meta = edition_index(set(t["codNota"]))
    t = t.merge(meta["targets"], on="codNota", how="left")
    return t.sort_values(["codDiario", "orden"]).reset_index(drop=True)


def edition_index(cods: set[int]) -> dict:
    """Daily-index metadata of the targets, and every note (any subject) of the editions that hold them, so the
    next note after a resolution bounds its end."""
    rows, by_diario = [], collections.defaultdict(list)
    files = [f for f in index_files(DOF_SIDOF_INDEX_DIR) if re.search(r"sidof_notes_19(7[6-9]|[89]\d)", f.name)]
    for fn in files:
        for rec in iter_jsonl(fn):
            for ed, ns in (rec.get("response") or {}).items():
                if not isinstance(ns, list):
                    continue
                for n in ns:
                    try:
                        cod, diario = int(n["codNota"]), int(n["codDiario"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    by_diario[diario].append({"codNota": cod, "codSeccion": n.get("codSeccion"),
                                              "pagina": n.get("pagina"), "orden": n.get("orden"),
                                              "titulo": re.sub(r"\s+", " ", n.get("titulo") or "").strip()})
                    if cod in cods:
                        rows.append({"codNota": cod, "codDiario": diario, "codSeccion": n.get("codSeccion"),
                                     "pagina": n.get("pagina"), "orden": n.get("orden"), "edition_index": ed,
                                     "existeImagen": n.get("existeImagen"), "existePdf": n.get("existePdf")})
    keep = {r["codDiario"] for r in rows}
    return {"targets": pd.DataFrame(rows).drop_duplicates("codNota"),
            "editions": {d: sorted({n["codNota"]: n for n in v}.values(), key=lambda n: (n["orden"] or 0))
                         for d, v in by_diario.items() if d in keep}}


# ========================================================================================= PDF text
WORD_RE = re.compile(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</word>', re.S)
PAGE_SPLIT_RE = re.compile(r'(<page width="[\d.]+" height="[\d.]+">)')
HEADER_RE = re.compile(r"(lunes|martes|mi.rcoles|jueves|viernes|s.bado|domingo)\b|d\s?i\s?a\s?r\s?i\s?o|o\s?f\s?i\s?c\s?i\s?a",
                       re.I)


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, check=True, **kw)


def bbox_pages(pdf: Path, first: int | None = None, last: int | None = None) -> list[tuple[float, float, list]]:
    """Word boxes of every page: [(width, height, [(x0, y0, x1, y1, text), ...]), ...]."""
    cmd = ["pdftotext", "-bbox", "-enc", "UTF-8"]
    if first:
        cmd += ["-f", str(first), "-l", str(last or first)]
    raw = run(cmd + [str(pdf), "-"]).stdout.decode("utf-8", errors="replace")
    parts = PAGE_SPLIT_RE.split(raw)
    pages = []
    for i in range(1, len(parts), 2):
        w, h = map(float, re.findall(r'[\d.]+', parts[i]))
        words = [(float(a), float(b), float(c), float(d), html_lib.unescape(t).strip())
                 for a, b, c, d, t in WORD_RE.findall(parts[i + 1])]
        pages.append((w, h, [x for x in words if x[4]]))
    return pages


def _coverage(w: float, words: list) -> list[int]:
    cov = [0] * (int(w) + 2)
    for x0, _y0, x1, _y1, _t in words:
        for b in range(max(0, int(x0) + 1), min(len(cov), int(x1))):      # boxes shrunk by 1 pt
            cov[b] += 1
    return cov


def _runs(cov: list[int], lo: int, hi: int, thr: float, minw: int) -> list[tuple[int, int]]:
    runs, start = [], None
    for b in range(lo, hi):
        if cov[b] <= thr:
            start = b if start is None else start
        else:
            if start is not None and b - start >= minw:
                runs.append((start, b))
            start = None
    if start is not None and hi - start >= minw:
        runs.append((start, hi))
    return runs


N_BANDS = 4


def gutters(w: float, h: float, words: list) -> list[list[float]]:
    """Column gutters of a page, per horizontal band (scans are often slightly skewed): a list of N_BANDS lists
    of x cut positions. A gutter is a run of (almost) no word coverage between 18% and 82% of the width, found
    on the whole page or in at least 3 of the 4 bands; each band then takes its own local minimum near it."""
    body = [x for x in words if x[1] > 0.1 * h and (x[2] - x[0]) < 0.45 * w]
    if len(body) < 40:
        return [[] for _ in range(N_BANDS)]
    lo, hi = int(0.18 * w), int(0.82 * w)
    cov = _coverage(w, body)
    cuts = []
    for ra, rb in sorted(_runs(cov, lo, hi, max(2, 0.01 * len(body)), 2), key=lambda r: r[0] - r[1]):   # widest first
        c = (ra + rb) / 2
        if all(abs(c - x) > 0.2 * w for x in cuts):
            cuts.append(c)
    ytop = 0.1 * h
    bh = (h - ytop) / N_BANDS
    band_words = [[x for x in body if ytop + k * bh <= (x[1] + x[3]) / 2 < ytop + (k + 1) * bh] for k in range(N_BANDS)]
    band_cov = [_coverage(w, bw) for bw in band_words]
    if not cuts:   # skewed page: look band by band for a central gutter
        centers = []
        for bw, bc in zip(band_words, band_cov):
            if len(bw) < 25:
                continue
            rr = _runs(bc, int(0.35 * w), int(0.65 * w), 0, 3)
            if rr:
                ra, rb = max(rr, key=lambda r: r[1] - r[0])
                centers.append((ra + rb) / 2)
        if len(centers) >= 3:
            cuts = [sorted(centers)[len(centers) // 2]]
    out = []
    for bc in band_cov:
        local = []
        for c in sorted(cuts):
            win = range(max(lo, int(c) - 20), min(hi, int(c) + 21))
            m = min(bc[b] for b in win)
            zs = [b for b in win if bc[b] == m]
            # centre of the minimum run closest to the global cut
            best = min(zs, key=lambda b: abs(b - c))
            r0 = r1 = best
            while r0 - 1 in win and bc[r0 - 1] == m:
                r0 -= 1
            while r1 + 1 in win and bc[r1 + 1] == m:
                r1 += 1
            local.append((r0 + r1) / 2)
        out.append(local)
    return out


def column_lines(w: float, h: float, words: list) -> tuple[list[list[float]], list[list]]:
    """Lines in reading order (column by column, top to bottom): [[col, x0, y0, x1, y1, text], ...]. The running
    page header (date, DIARIO OFICIAL, page number) and rule lines are dropped."""
    bands = gutters(w, h, words)
    ytop = 0.1 * h
    bh = (h - ytop) / N_BANDS
    # running header: the top-most line cluster when it looks like a header
    srt = sorted(words, key=lambda x: (x[1] + x[3]) / 2)
    drop = set()
    if srt:
        top = [x for x in srt if (x[1] + x[3]) / 2 < (srt[0][1] + srt[0][3]) / 2 + 9]
        txt = " ".join(x[4] for x in top)
        if (top and (top[0][1] + top[0][3]) / 2 < 0.16 * h and HEADER_RE.search(txt)
                and not re.search(r"organo|gobierno", txt, re.I)):
            drop = {id(x) for x in top}
    ncol = max(len(b) for b in bands) + 1
    cols = [[] for _ in range(ncol)]
    for wd in words:
        if id(wd) in drop:
            continue
        xc, yc = (wd[0] + wd[2]) / 2, (wd[1] + wd[3]) / 2
        k = min(N_BANDS - 1, max(0, int((yc - ytop) // bh)))
        cols[sum(xc > c for c in bands[k])].append(wd)
    out = []
    for k, col in enumerate(cols):
        col.sort(key=lambda x: (x[1] + x[3]) / 2)
        lines, cur, cy = [], [], None
        for wd in col:
            yc = (wd[1] + wd[3]) / 2
            hgt = max(4.0, wd[3] - wd[1])
            if cur and abs(yc - cy) > 0.45 * hgt:
                lines.append(cur)
                cur = []
            if not cur:
                cy = yc
            cur.append(wd)
        if cur:
            lines.append(cur)
        for ln in lines:
            ln.sort(key=lambda x: x[0])
            text = " ".join(x[4] for x in ln)
            if re.fullmatch(r"[\W_~]*", text):
                continue
            out.append([k, round(min(x[0] for x in ln), 1), round(min(x[1] for x in ln), 1),
                        round(max(x[2] for x in ln), 1), round(max(x[3] for x in ln), 1), text])
    return bands, out


COVER_CUES = [r"organo\s+del\s+go", r"registrad[oa]\s+como\s+art", r"director\s*:", r"\btomo\s+[cdlxvi]{2,}",
              r"gobierno\s+c[o0]\S{0,3}n\S{0,3}st", r"\bdel\s+gobierno\s+c"]
SECTION_WORD_RE = re.compile(r"\b((?:decima\s+)?(?:primera|segunda|tercera|cuarta|quinta|sexta|septima|octava|novena)"
                             r"|decima|unica)\s+secc", re.I)
SECTION_WORD_LOOSE_RE = re.compile(r"(?:director|mariano|maltiano)\W{0,3}\s*\S{0,12}?\s*((?:decima\s+)?(?:primera|segunda|tercera|"
                                   r"cuarta|quinta|sexta|septima|octava|novena)|decima)\b", re.I)


def detect_cover(text: str) -> str | None:
    """Section header of a cover page (masthead + 'SEGUNDA SECCION'); 'cover (no section ordinal)' when only the
    masthead is found; None for other pages."""
    head = norm(text[:1600])
    m = SECTION_WORD_RE.search(head) or SECTION_WORD_LOOSE_RE.search(head[:400])
    if sum(bool(re.search(c, head)) for c in COVER_CUES) + bool(m) < 2:
        return None
    return (m.group(1).upper() + " SECCION") if m else "cover (no section ordinal)"


def is_sumario(text: str) -> bool:
    return bool(re.search(r"\bs\s?u\s?m\s?a\s?r\s?i\s?o\b|\bindice\b", norm(text[:900])))


# ============================================================================================ harvest
def edition_archive_path(date_iso: str, edicion: str, diario: int) -> Path:
    return DOF_SCANNED_EDITIONS_DIR / f"{date_iso}_{edicion}_{diario}.jsonl.gz"


def pdftotext_version() -> str:
    r = subprocess.run(["pdftotext", "-v"], capture_output=True)
    m = re.search(r"version\s+([\d.]+)", (r.stderr or r.stdout).decode())
    return m.group(1) if m else "unknown"


def read_manifest() -> list[dict]:
    if not MANIFEST.exists():
        return []
    with open(MANIFEST, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def update_manifest(fn):
    """Read-modify-write MANIFEST.csv in place under an exclusive lock on the file itself: 06_reparse_dof_texts.py
    appends to the same manifest under the same lock, so the file is never replaced (no rename)."""
    import fcntl
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST, "a+", newline="", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            fh.seek(0)
            text = fh.read()
            rows = list(csv.DictReader(io.StringIO(text))) if text.strip() else []
            cols = next(csv.reader([text.splitlines()[0]])) if text.strip() else MANIFEST_COLS
            cols = cols + [c for c in MANIFEST_COLS if c not in cols]
            rows = fn(rows)
            fh.seek(0)
            fh.truncate()
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow({c: r.get(c) for c in cols})
            fh.flush()
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def save_coltext(diario: int, pages: list[dict]):
    COLTEXT_DIR.mkdir(parents=True, exist_ok=True)
    with gzip.open(COLTEXT_DIR / f"{diario}.json.gz", "wt", encoding="utf-8") as f:
        json.dump(pages, f, ensure_ascii=False)


def load_coltext(diario: int) -> list[dict] | None:
    """Column-ordered pages of an edition; cover and summary flags are recomputed with the current rules."""
    fn = COLTEXT_DIR / f"{diario}.json.gz"
    if not fn.exists():
        return None
    with gzip.open(fn, "rt", encoding="utf-8") as f:
        pages = json.load(f)
    for p in pages:
        text = "\n".join(ln[5] for ln in p["lines"])
        p["cover"], p["sumario"] = detect_cover(text), is_sumario(text)
    return pages


def harvest(limit: int | None = None, only: set[int] | None = None):
    for d in (NOTES_DIR, PDF_DIR, COLTEXT_DIR, PAGES_DIR, DOF_SCANNED_EDITIONS_DIR):
        d.mkdir(parents=True, exist_ok=True)
    tg = load_targets()
    ed_index = edition_index(set(tg["codNota"]))["editions"]
    done = set(int(x) for x in DONE_FILE.read_text().split()) if DONE_FILE.exists() else set()
    editions = [d for d in tg["codDiario"].dropna().astype(int).unique() if d not in done and (not only or d in only)]
    print(f"{len(tg)} target notes in {tg.codDiario.nunique()} editions; {len(done)} done, {len(editions)} to go", flush=True)
    version = pdftotext_version()
    for i, diario in enumerate(editions[:limit] if limit else editions):
        sub = tg[tg.codDiario == diario]
        recs = {}
        for cod in sub.codNota:
            r = note_record(int(cod))
            if r is None:
                print(f"  note record {cod} unavailable", flush=True)
            else:
                recs[int(cod)] = r
        anyrec = next(iter(recs.values()), None)
        date_iso = (dt.datetime.strptime(anyrec["fecha"], "%d-%m-%Y").date().isoformat() if anyrec
                    else str(sub.dof_date.iloc[0]))
        edicion = (anyrec or {}).get("codEdicion") or "MAT"
        pdf = PDF_DIR / f"{diario}.pdf"
        t0 = time.time()
        if not pdf.exists():
            status, ctype, res = polite_get(PDF_URL.format(diario), dest=pdf)
            downloaded_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            if status != 200 or res is None:
                print(f"[{i + 1}/{len(editions)}] {diario}: download failed (status {status})", flush=True)
                continue
            nbytes, sha = res
        else:   # a previous run downloaded it but stopped before finishing
            ctype, status = "application/pdf", 200
            nbytes, sha = pdf.stat().st_size, hashlib.sha256(pdf.read_bytes()).hexdigest()
            downloaded_at = dt.datetime.fromtimestamp(pdf.stat().st_mtime, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(pdf, "rb") as fh:
            if fh.read(5) != b"%PDF-":
                print(f"[{i + 1}/{len(editions)}] {diario}: not a PDF ({ctype}); skipped", flush=True)
                pdf.unlink()
                continue
        info = run(["pdfinfo", str(pdf)]).stdout.decode("utf-8", errors="replace")
        n_pages = int(re.search(r"Pages:\s+(\d+)", info).group(1))
        producer = (re.search(r"Producer:\s+(.*)", info) or [None, ""])[1].strip()
        # whole text layer, layout mode, one JSON line per page (the archive)
        layout = run(["pdftotext", "-layout", "-enc", "UTF-8", str(pdf), "-"]).stdout.decode("utf-8", errors="replace")
        layout_pages = layout.split("\f")[:n_pages]
        # column-ordered text (local, for parsing)
        pages = []
        for k, (w, h, words) in enumerate(bbox_pages(pdf), start=1):
            cuts, lines = column_lines(w, h, words)
            text = "\n".join(ln[5] for ln in lines)
            pages.append({"pdf_page": k, "w": w, "h": h, "cuts": cuts, "lines": lines,
                          "cover": detect_cover(text), "sumario": is_sumario(text)})
        save_coltext(diario, pages)
        arch = edition_archive_path(date_iso, edicion, diario)
        with gzip.open(arch, "wt", encoding="utf-8") as f:
            for k in range(n_pages):
                f.write(json.dumps({"codDiario": int(diario), "date": date_iso, "codEdicion": edicion, "pdf_page": k + 1,
                                    "section_header_detected": pages[k]["cover"] if k < len(pages) else None,
                                    "text": layout_pages[k] if k < len(layout_pages) else ""}, ensure_ascii=False) + "\n")
        # locate the targets to decide which pages to keep as single-page PDFs
        notes = [dict(r, **(recs.get(int(r["codNota"])) or {})) for r in sub.to_dict("records")]
        locs = locate_edition(pages, notes, ed_index.get(int(diario), []))
        keep = set()
        for cod, loc in locs.items():
            if loc.get("start_page"):
                keep |= set(range(loc["start_page"] - 1, (loc.get("end_page") or loc["start_page"]) + 2))
            if loc.get("expected_page"):
                keep |= set(range(loc["expected_page"] - 3, loc["expected_page"] + 6))
        keep = sorted(p for p in keep if 1 <= p <= n_pages)
        for p in keep:
            out = PAGES_DIR / f"{diario}_{p:03d}.pdf"
            if not out.exists():
                run(["pdfseparate", "-f", str(p), "-l", str(p), str(pdf), str(out)])
        row = {"source_url": PDF_URL.format(diario), "codDiario": int(diario), "date": date_iso,
                     "codEdicion": edicion, "http_status": status, "content_type": ctype, "bytes": nbytes,
                     "sha256": sha, "n_pages": n_pages, "pdf_producer": producer, "downloaded_at": downloaded_at,
                     "extracted_with": f"pdftotext {version} (poppler) -layout -enc UTF-8, one line per page",
                     "edition_text_file": arch.name,
                     "codNotas_pdf_pages": ";".join(f"{c}:{l.get('start_page') or '?'}-{l.get('end_page') or '?'}"
                                                    for c, l in locs.items())}
        update_manifest(lambda rows: [r for r in rows if str(r.get("codDiario")) != str(diario)] + [row])
        pdf.unlink()
        with open(DONE_FILE, "a") as f:
            f.write(f"{diario}\n")
        found = sum(1 for l in locs.values() if l.get("start_page"))
        print(f"[{i + 1}/{len(editions)}] {date_iso} {edicion} {diario}: {n_pages} pages, {nbytes / 1e6:.1f} MB, "
              f"{found}/{len(locs)} located, kept {len(keep)} pages, {time.time() - t0:.0f}s", flush=True)


# =========================================================================================== location
def cnorm(s: str) -> str:
    """Length-preserving normalisation: lower case, accents stripped, every non-alphanumeric char -> space."""
    out = []
    for ch in s:
        base = unicodedata.normalize("NFKD", ch)
        base = "".join(c for c in base if not unicodedata.combining(c)) or " "
        c = base[0].lower()
        out.append(c if c.isalnum() and c.isascii() else " ")
    return "".join(out)


def clean_title(t: str) -> str:
    t = re.sub(r"\(\s*reg[^)]*\)?\s*\.?\s*$", "", t or "", flags=re.I)
    return re.sub(r"\s+", " ", cnorm(t)).strip()


class EditionStream:
    """All column-ordered page texts of an edition joined into one string, with page offsets."""

    def __init__(self, pages: list[dict]):
        self.pages = pages
        parts, self.starts = [], []
        pos = 0
        for p in pages:
            txt = "\n".join(ln[5] for ln in p["lines"])
            self.starts.append(pos)
            parts.append(txt)
            pos += len(txt) + 2
        self.text = "\n\n".join(parts)
        self.ntext = cnorm(self.text)

    def page_of(self, pos: int) -> int:
        k = 0
        for i, s in enumerate(self.starts):
            if s <= pos:
                k = i
        return k + 1

    def page_span(self, page: int) -> tuple[int, int]:
        i = page - 1
        a = self.starts[i]
        b = self.starts[i + 1] - 2 if i + 1 < len(self.starts) else len(self.text)
        return a, b

    def line_at(self, pos: int):
        """(page, line) holding character `pos`."""
        page = self.page_of(pos)
        off = pos - self.starts[page - 1]
        acc = 0
        for ln in self.pages[page - 1]["lines"]:
            if acc + len(ln[5]) >= off:
                return page, ln
            acc += len(ln[5]) + 1
        lines = self.pages[page - 1]["lines"]
        return page, (lines[-1] if lines else None)


def section_covers(pages: list[dict]) -> dict[int, int]:
    """Section ordinal -> PDF page of its cover. Named covers win; unnamed ones are numbered in order."""
    covers = [(p["pdf_page"], p["cover"]) for p in pages if p.get("cover")]
    if pages and (not covers or covers[0][0] != 1):      # the edition opens with the first section's cover
        covers.insert(0, (1, "cover (assumed: first page)"))
    out = {}
    for k, (pg, lab) in enumerate(covers, start=1):
        name = lab.replace(" SECCION", "") if lab and lab.endswith("SECCION") else None
        o = SECTION_ORD.get(name) if name else None
        if o and o not in out:
            out[o] = pg
    for k, (pg, lab) in enumerate(covers, start=1):    # fill unnamed covers by order
        if pg not in out.values() and k not in out:
            out[k] = pg
    if 1 not in out:
        out[1] = 1
    return out


SIGN_START_RE = re.compile(r"\bd\s?a\s?d\s?[oa0]\s+e\s?n\s+(?:el\s+)?(?:p\s?a\s?\w{2,5}\s?o\s+d\s?e\s?l\s+p\s?o\s?d|"
                           r"la\s+ciudad\s+de\s+m|m\s?e\s?x\s?i\s?c\s?o\s*,?\s+d)")
# other anchors of the closing formula, in case the OCR garbled "Dado en el Palacio ..."
CLOSING_RES = [SIGN_START_RE,
               re.compile(r"n\s?o\s?t\s?[il1]\s?f\s?[il1]\s?q\s?u\s?e\s?s\s?e\s+y\s+e\s?j\s?e\s?c\s?u\s?t\s?e\s?s\s?e"),
               re.compile(r"p\s?r\s?e\s?\w{1,3}\s?d\s?e\s?n\s?t\s?e\s+c\s?o\s?n\s?s\s?t\s?[il1]\s?t\w{0,9}\s+d\s?e\s+l\s?[oa]\s?s"
                          r"|c\s?o\s?n\s?s\s?t\s?[il1]\s?t\s?u\s?c\s?[il1]\s?o\s?n\s?a\s?l\s+d\s?e\s+l\s?[oa]\s?s\s+e\s?s\s?t"),
               re.compile(r"\bc\s?[uv]\s?m\s*p\s?[l1i]\s?a\s?s\s?e\b")]
PUBLIQUESE_RE = re.compile(r"\bp\s?u\s?b\s?l\s?[il1]\s?q\s?u\s?e\s?s\s?e\s+(?:e\s?n|e\s?s\s?t\s?a)")
EN_USO_RE = re.compile(r"e\s?n\s+u\s?s\s?o\s+d\s?e\s+l\s?a\s?s\s+f\s?a\s?c")    # "Presidente ..., en uso de las facultades" opens a decree
# every resolution opens with "Al margen un sello", "VISTO para resolver" and "RESULTANDO PRIMERO": a second one
# after a resolution's start means the next resolution began (its own closing formula was garbled by the OCR)
VISTO_RE = re.compile(r"\bv\s?[il1]\s?s\s?t\s?[o0]\s+p\s?a\s?r\s?a\s+r\s?e\s?s\s?[o0]\s?l\s?v\s?e\s?r")
RES1_RE = re.compile(r"r\s?e\s?s\s?u\s?l\s?t\s?a\s?n\s?d\s?o\s+p\s?r\s?[il1]\s?m\s?e\s?r\s?o")
CONSID_RE = re.compile(r"c\s?o\s?n\s?s\s?[il1]\s?d\s?e\s?r\s?a\s?n\s?d\s?o")
RUBRICA_RE = re.compile(r"r\s?[uv]\s?b\s?r\s?[il1]\s?c\s?a")
# a printed heading (original case): "RESOLUCION sobre", "Resolución sobre", "DECRETO por", "ACUERDO que", ...
HEADING_RE = re.compile(r"(?:RE\W?S\W?O\W?L\W?U\W?C\W?[I1l]\W?[OÓ0]\W?N|Re\W?s\W?o\W?l\W?u\W?c\W?i\W?[oó]\W?n|DECRETO|Decreto|"
                        r"ACUERDO|Acuerdo|SOLICITUD|Solicitud|AVISO|EDICTO)\s+(?:sobre|soble|s\S{2,3}re|por\s+(?:el|la)|que\s+(?:concede|declara|se)|"
                        r"relativ)")
MARGEN_RE = re.compile(r"\ba\s?[l1i]?\s+m\s?a\s?r\s?g\s?e\s?n\s+u\s?n\b|\bs\s?e\s?l\s?l\s?o\s+c\s?o\s?n\s+e\s?l\s+e\s?s\s?c")


def name_score(name: str | None, window: str) -> float | None:
    if not isinstance(name, str) or len(name.strip()) < 3:
        return None
    return fuzz.partial_ratio(clean_title(name), window)


def find_title(es: EditionStream, title: str, pages: list[int], names: list[str | None],
               exp: int | None = None) -> dict | None:
    """Best alignment of the title on the given pages. Score = 60% title alignment + 40% names (poblado,
    municipality) found within the heading and the next 600 characters, + 8 when "Al margen un sello" follows
    (every resolution heading is followed by it), - 2 per page away from the expected page."""
    tn = clean_title(title)
    if len(tn) < 15:
        return None
    best = None
    for pg in pages:
        a, b = es.page_span(pg)
        hay = es.ntext[a:b]
        if not hay.strip():
            continue
        al = fuzz.partial_ratio_alignment(tn, hay, score_cutoff=50)
        if al is None:
            continue
        pos = a + al.dest_start
        end = a + al.dest_end
        win = re.sub(r"\s+", " ", es.ntext[max(0, pos - 50): pos + len(tn) + 600])
        ns = [s for s in (name_score(n, win) for n in names) if s is not None]
        margen = bool(MARGEN_RE.search(es.ntext[max(pos, end - 40): end + 250]))
        # the closing "Publiquese ... la presente resolucion que concede ... al poblado X, Municipio Y" repeats the
        # title: a match right after it is not the heading
        # (and so do the resolutive points: "SEGUNDO.- Es procedente la accion de ... promovida por ...")
        closing = bool(re.search(r"presente\s+r\w{0,3}s\w{0,3}l|p\w{0,2}bl\w{0,2}quese|inscr\w{0,2}base|r\s?e\s?s\s?u\s?e\s?l\s?v\s?e"
                                 r"|es\s+proced\w*|se\s+conced\w*|promovid", es.ntext[max(0, pos - 220): pos + 10]))
        visto = bool(VISTO_RE.search(es.ntext[max(0, pos - 130): pos + 20]))
        score = (0.6 * al.score + 0.4 * (sum(ns) / len(ns) if ns else al.score) + 8 * margen + 6 * visto
                 - 15 * closing - (2 * abs(pg - exp) if exp else 0))
        if best is None or score > best["score"]:
            best = {"pos": pos, "page": pg, "score": round(score, 1), "title_score": round(al.score, 1),
                    "name_scores": [round(s) for s in ns], "margen": margen}
    if best:   # move back to the printed heading word ("RESOLUCION sobre ...") if it sits just before
        lo = max(0, best["pos"] - 80)
        hm = list(HEADING_RE.finditer(es.text[lo: best["pos"] + 25]))
        if hm:
            best["pos"] = lo + hm[-1].start()
            best["page"] = es.page_of(best["pos"])
    return best


def summary_pages(es: EditionStream) -> set[int]:
    """Pages of the table of contents: the run of pages right after a masthead with many printed headings or
    dot-leader entries ("....... 25") and (almost) no "Al margen un sello"."""
    def looks(p):
        a, b = es.page_span(p["pdf_page"])
        nh = len(HEADING_RE.findall(es.text[a:b]))
        nm = len(MARGEN_RE.findall(es.ntext[a:b]))
        leaders = len(re.findall(r"(?:\.\s?){4,}\s*\d{1,3}\b", es.text[a:b]))
        return p.get("sumario") or ((nh >= 5 or leaders >= 3) and nm <= 1)
    out = set()
    covers = sorted({p["pdf_page"] for p in es.pages if p.get("cover")} | {1})
    for c in covers:
        k, misses = c, 0
        while k <= len(es.pages) and k - c <= 20 and misses <= 1:
            p = es.pages[k - 1]
            if p.get("lines") and looks(p):
                out.add(k)
                misses = 0
            elif k > c:
                misses += 1
            k += 1
    out |= {k for k in range(2, len(es.pages)) if k - 1 in out and k + 1 in out}     # one-page gaps
    return out


def calibrate_sections(es: EditionStream, all_notes: list[dict], skip: set[int]) -> dict[int, int]:
    """Section -> (PDF page - printed page) offset, from up to 5 notes of each section (any subject, longest titles)
    found anywhere in the edition. Used when the edition has several sections: the covers of some sections are
    not detected in the OCR, which would shift the page arithmetic of every later section."""
    by_sec = collections.defaultdict(list)
    for x in all_notes:
        o = SECTION_ORD.get(str(x.get("codSeccion") or "").upper())
        if o and x.get("pagina") and len(clean_title(x.get("titulo") or "")) >= 70:
            by_sec[o].append(x)
    pages = [p["pdf_page"] for p in es.pages if p.get("lines") and p["pdf_page"] not in skip]
    out = {}
    for o, xs in by_sec.items():
        offs = []
        for x in sorted(xs, key=lambda x: -len(x.get("titulo") or ""))[:5]:
            pt = P03.parse_title(x["titulo"])
            names = [n for n in (pt.get("ncpe_name") or pt.get("poblado"), pt.get("municipality")) if n]
            if not names:
                continue
            f = find_title(es, x["titulo"], pages, names, None)
            if f and f["score"] >= 92 and min(f["name_scores"] or [0]) >= 90:
                offs.append(f["page"] - int(x["pagina"]))
        if offs:
            c = collections.Counter(offs).most_common(1)[0]
            if c[1] >= 2 or len(offs) == 1:
                out[o] = c[0]
    return out


def find_by_name(es: EditionStream, names: list, pages: list[int], exp: int | None) -> dict | None:
    """The village name (exact, accents and punctuation ignored) within 260 characters after "VISTO para
    resolver" on the candidate pages; the resolution starts at the heading before it."""
    nm = [clean_title(n) for n in names[:1] if isinstance(n, str) and len(clean_title(n)) >= 5]
    if not nm:
        return None
    rx = re.compile(r"\s+".join(map(re.escape, nm[0].split())))
    hits = []
    for pg in pages:
        a, b = es.page_span(pg)
        for v in VISTO_RE.finditer(es.ntext, a, b):
            if rx.search(re.sub(r"\s+", " ", es.ntext[v.end(): v.end() + 260]).replace(" ", " ")) or \
                    rx.search(es.ntext[v.end(): v.end() + 300]):
                hits.append((abs(pg - exp) if exp else 0, v.start(), pg))
    if not hits:
        return None
    _, vpos, pg = min(hits)
    lo = max(0, vpos - 450)
    hm = list(HEADING_RE.finditer(es.text[lo: vpos]))
    pos = lo + hm[-1].start() if hm else max(0, vpos - 300)
    return {"pos": pos, "page": es.page_of(pos), "score": 80.0, "title_score": None, "name_scores": [100],
            "margen": None, "by_name": True}


def locate_edition(pages: list[dict], notes: list[dict], all_notes: list[dict],
                   covers: dict[int, int] | None = None, offsets: dict[int, int] | None = None) -> dict[int, dict]:
    """Two passes: the second uses the section offsets implied by the targets located with confidence in the
    first (title + village + municipality found), for the targets of those sections that were not found."""
    out = _locate_pass(pages, notes, all_notes, covers, offsets)
    learned = collections.defaultdict(list)
    for nt in notes:
        loc = out.get(int(nt["codNota"]), {})
        o = SECTION_ORD.get(str(nt.get("codSeccion") or "").upper())
        if loc.get("status") == "found" and loc.get("score", 0) >= 88 and min(loc.get("name_scores") or [0]) >= 85 \
                and o and pd.notna(nt.get("pagina")):
            learned[o].append(loc["start_page"] - int(nt["pagina"]))
    new = dict(offsets or {})
    changed = False
    for o, offs in learned.items():
        c, k = collections.Counter(offs).most_common(1)[0]
        if new.get(o) != c and (k >= 2 or o not in new):
            new[o], changed = c, True
    redo = [nt for nt in notes if out.get(int(nt["codNota"]), {}).get("status") != "found"
            and SECTION_ORD.get(str(nt.get("codSeccion") or "").upper()) in learned]
    if changed and redo:
        again = _locate_pass(pages, redo, all_notes, covers, new)
        taken = [(l["start"], l["end"]) for l in out.values() if l.get("status") == "found"]
        for c, l in again.items():
            if l.get("status") == "found" and not any(l["start"] < y and x < l["end"] for x, y in taken):
                out[c] = dict(l, second_pass=True)
                taken.append((l["start"], l["end"]))
    return out


def _locate_pass(pages: list[dict], notes: list[dict], all_notes: list[dict],
                 covers: dict[int, int] | None = None, offsets: dict[int, int] | None = None) -> dict[int, dict]:
    """Locate every target note of one edition: start (heading), end (after the signature) and PDF pages.
    `covers` (section -> cover page) can be passed in when `pages` is a partial OCR of the edition; `offsets`
    (section -> PDF page - printed page) likewise."""
    es = EditionStream(pages)
    n = len(pages)
    covers = covers or section_covers(pages)
    skip = summary_pages(es)
    nsec = len({str(x.get("codSeccion") or "").upper() for x in all_notes} - {""})
    if offsets is None and nsec > 1:
        offsets = calibrate_sections(es, all_notes, skip)
    offsets = offsets or {}
    order = sorted(all_notes, key=lambda x: (SECTION_ORD.get(str(x.get("codSeccion") or "").upper(), 99), x.get("orden") or 0))
    out = {}
    for nt in notes:
        cod = int(nt["codNota"])
        sec = str(nt.get("codSeccion") or "").upper()
        o = SECTION_ORD.get(sec)
        pag = int(nt["pagina"]) if pd.notna(nt.get("pagina")) else None
        exp = (pag + offsets[o] if o in offsets else covers[o] + pag - 1 if o in covers else None) if pag else None
        names = [nt.get("ncpe_name") if isinstance(nt.get("ncpe_name"), str) else nt.get("poblado"),
                 nt.get("municipality_dof")]
        title = nt.get("titulo") or nt.get("dof_title") or ""
        loc = {"expected_page": exp, "covers": covers, "start_page": None, "end_page": None}
        cands = list(range(max(1, exp - 3), min(n, exp + 3) + 1)) if exp else []
        best = find_title(es, title, cands, names, exp) if cands else None
        if best is None or best["score"] < 80:     # global search (not on summary or empty pages)
            allp = [p["pdf_page"] for p in pages if p["pdf_page"] not in skip and p.get("lines")]
            gb = find_title(es, title, allp, names, None)      # no page prior: the expected page may be wrong
            if (gb and (best is None or gb["score"] > best["score"] + 5) and gb["score"] >= 88
                    and gb["name_scores"] and min(gb["name_scores"]) >= 85):
                best = dict(gb, global_search=True)
        # a weak match must at least name the village or the municipality (else it is another resolution)
        if best is not None and best["score"] < 85 and best["name_scores"] and max(best["name_scores"]) < 75:
            # unless the village is named (exactly) further on, before the next resolution's "Al margen"
            nm0 = clean_title(names[0]) if isinstance(names[0], str) else ""
            nxt = MARGEN_RE.search(es.ntext, best["pos"] + 600)
            span = es.ntext[best["pos"]: (nxt.start() if nxt else best["pos"] + 20000)]
            if not (len(nm0) >= 5 and re.search(r"\s+".join(map(re.escape, nm0.split())), span)):
                loc["rejected"] = best
                best = None
        if best is None and cands:            # the heading is garbled: find the village named in a "VISTO" paragraph
            best = find_by_name(es, names, cands, exp)
        if best is None or best["score"] < 70:
            loc["status"] = "not_found"
            loc["best"] = best
            out[cod] = loc
            continue
        start = best["pos"]
        # bound: the heading of the next note of the edition (any subject), else 12 pages
        bound = es.page_span(min(n, es.page_of(start) + 12))[1]
        bound_is_next = False
        idx = next((i for i, x in enumerate(order) if int(x["codNota"]) == cod), None)
        if idx is not None and idx + 1 < len(order):
            nx = order[idx + 1]
            no = SECTION_ORD.get(str(nx.get("codSeccion") or "").upper())
            nexp = ((int(nx["pagina"]) + offsets[no] if no in offsets else covers[no] + int(nx["pagina"]) - 1 if no in covers
                     else None) if nx.get("pagina") else None)
            if nexp:
                nb = find_title(es, nx.get("titulo") or "", list(range(max(1, nexp - 2), min(n, nexp + 2) + 1)),
                                [None], nexp)
                if nb and nb["score"] >= 80 and nb["pos"] > start + 200:
                    bound = min(bound, nb["pos"])
                    bound_is_next = True
                    loc["next_note"] = int(nx["codNota"])
        # the next resolution's "Al margen un sello" / "VISTO para resolver" / "RESULTANDO PRIMERO.-" closes this one
        marks = []
        mg = MARGEN_RE.search(es.ntext, start + 600, bound)
        if mg:
            hm = list(HEADING_RE.finditer(es.text[max(start, mg.start() - 400): mg.start()]))
            marks.append(max(start, mg.start() - 400) + hm[-1].start() if hm else max(start + 600, mg.start() - 220))
        vm = VISTO_RE.search(es.ntext, start + 1200, bound)
        if vm:
            marks.append(max(start + 900, vm.start() - 380))
        for rm in RES1_RE.finditer(es.ntext, start + 1500, bound):
            # only with a heading or a decree's "Presidente Constitucional ..., en uso de las facultades" before it
            # (a second "RESULTANDO PRIMERO" inside one resolution is a printing slip)
            pre = es.ntext[max(start, rm.start() - 900): rm.start()]
            if (re.match(r"\s*[\.\-:,]", es.text[rm.end(): rm.end() + 4]) and es.text[rm.start()].isupper()
                    and (EN_USO_RE.search(pre) or HEADING_RE.search(es.text[max(start, rm.start() - 900): rm.start()]))):
                marks.append(max(start + 1200, rm.start() - 650))
                break
        if marks and min(marks) < bound:
            bound, bound_is_next = min(marks), True
        seg = es.ntext[start:bound]
        anchors = []
        for rx in CLOSING_RES:
            m = next((m for m in rx.finditer(seg) if m.start() > 800 and not EN_USO_RE.search(seg, m.end(), m.end() + 90)),
                     None)
            if m:
                anchors.append(m.start())
        pq = next((m for m in PUBLIQUESE_RE.finditer(seg) if m.start() > 800), None)
        if anchors or pq:
            a0 = min(anchors) if anchors else pq.start()
            tail = seg[a0: a0 + (1100 if anchors else 1700)]
            nh = HEADING_RE.search(es.text[start + a0: start + a0 + len(tail)], 30)
            if nh:
                tail = tail[:nh.start()]
            rub = [m.end() for m in RUBRICA_RE.finditer(tail)]
            if rub:
                end = start + a0 + (rub[1] if len(rub) >= 2 else rub[0])
            else:
                end = start + a0 + len(tail) if bound_is_next else start + a0 + min(len(tail), 900)
            loc["end_status"] = ("signature" if anchors else "publiquese") + ("" if rub else "_no_rubrica")
        else:   # no closing formula found: up to the next resolution, or the next printed heading
            nh = None if bound_is_next else HEADING_RE.search(es.text[start:bound], 2000)
            end = start + (nh.start() if nh else len(seg))
            loc["end_status"] = "no_signature_" + ("next_resolution" if bound_is_next else "heading" if nh else "cap")
        loc.update(status="found", start=start, end=end, start_page=es.page_of(start), end_page=es.page_of(max(start, end - 1)),
                   score=best["score"], title_score=best["title_score"], name_scores=best["name_scores"],
                   margen=best.get("margen"), global_search=bool(best.get("global_search")),
                   page_offset=(es.page_of(start) - exp) if exp else None)
        out[cod] = loc
    # two targets on overlapping text: only the best title match keeps it
    found = sorted((c for c in out if out[c].get("status") == "found"), key=lambda c: -out[c]["score"])
    taken = []
    for c in found:
        a, b = out[c]["start"], out[c]["end"]
        if any(a < y and x < b for x, y in taken):
            out[c].update(status="ambiguous", start_page=None, end_page=None)
        else:
            taken.append((a, b))
    return out


# ============================================================================================ OCR repair
_LET = "A-Za-zÁÉÍÓÚÜÑáéíóúüñ"
NUMBER_VOCAB = sorted(set(P03.NUM_WORDS) - {"mi"} | {"y", "hectareas", "hectarea", "areas", "area", "centiareas",
                                                     "centiarea", "con"}, key=len, reverse=True)
DATE_VOCAB = sorted({w for w in P03.NUM_WORDS if len(w) >= 4} | set(P03.MONTHS) | {"dias", "novecientos"})
PAREN_RE = re.compile(r"\(([^()]{4,260})\)")


def segment_number_words(letters: str, fuzzy: bool = False) -> list[str] | None:
    """Split a run of letters with lost or spurious spaces into Spanish number words ('treshectareas' ->
    ['tres', 'hectareas']). Exact: fewest words. Fuzzy: minimum edit cost, each word matched with at most a
    third of its letters wrong, stray letters skipped at cost 1; None when the cost exceeds 20% of the letters."""
    n = len(letters)
    if not fuzzy:
        best: list = [None] * (n + 1)
        best[0] = []
        for i in range(n):
            if best[i] is None:
                continue
            for w in NUMBER_VOCAB:
                if letters.startswith(w, i) and (best[i + len(w)] is None or len(best[i]) + 1 < len(best[i + len(w)])):
                    best[i + len(w)] = best[i] + [w]
        return best[n]
    INF = 1e9
    cost = [INF] * (n + 1)
    back: list = [None] * (n + 1)
    cost[0] = 0.0
    for i in range(n):
        if cost[i] >= INF:
            continue
        if cost[i] + 1 < cost[i + 1]:                       # skip a stray letter
            cost[i + 1], back[i + 1] = cost[i] + 1, (i, None)
        for w in NUMBER_VOCAB:
            lw = len(w)
            for j in range(max(i + 1, i + lw - 2), min(n, i + lw + 2) + 1):
                d = Levenshtein.distance(letters[i:j], w)
                if d <= max(0, lw // 3) and cost[i] + d + 0.01 < cost[j]:
                    cost[j], back[j] = cost[i] + d + 0.01, (i, w)
    if cost[n] >= INF or cost[n] > max(2.0, 0.2 * n):
        return None
    out, j = [], n
    while j > 0:
        i, w = back[j]
        if w:
            out.append(w)
        j = i
    return out[::-1]


def repair_number_words(inner: str) -> str | None:
    """Amount in words as OCR'd ('TRES MIL HEC TAREAS', 'CUATROCIEN TAS SETENTA Y DOS HECTARFAS, OCHENTA
    AREAS') -> clean number words, or None when it cannot be read. Exact segmentation first, then fuzzy."""
    t = norm(inner)
    t = re.sub(r"[^a-z, ]", " ", t)
    chunks = [c.strip() for c in t.split(",") if c.strip()]
    out = []
    for ch in chunks:
        letters = re.sub(r"[^a-z]", "", ch)
        if not letters:
            continue
        seg = segment_number_words(letters) or segment_number_words(letters, fuzzy=True)
        if seg is None:
            if out:      # trailing text after the amount ("de agostadero ...") ends it
                break
            return None
        out.append(" ".join(seg))
    res = ", ".join(out)
    return res if re.search(r"hectarea", res) else None


def repair_signing_words(t: str) -> str:
    """Fuzzy-correct number and month words in the closing formula ('noveclentos', 'setellta', 'octubrc')."""
    nt = cnorm(t)
    for rx in CLOSING_RES[:1]:
        m = None
        for m in rx.finditer(nt):
            pass
        if not m:
            continue
        a, b = m.start(), min(len(t), m.start() + 420)
        win = t[a:b]

        def fix(mm):
            tok = mm.group(0)
            low = norm(tok)
            if len(low) < 4 or low in DATE_VOCAB or not low.isalpha():
                return tok
            c = process.extractOne(low, DATE_VOCAB, scorer=fuzz.ratio, score_cutoff=80)
            return c[0] if c else tok
        t = t[:a] + re.sub(rf"[{_LET}]+", fix, win) + t[b:]
    return t


def clean_ocr(text: str) -> str:
    """OCR repairs that change no content: soft hyphens, separators in amounts, O/l for 0/1, unit misreads,
    amounts in words, the closing formula's number and month words."""
    t = text.replace("­", "")
    t = re.sub(r"(\d)\s*[-–—·•]\s*\n\s*(\d)", r"\1-\2", t)                     # amount split at a line end
    t = re.sub(rf"([{_LET}])\s*[•·¬\-]\s*\n\s*([{_LET}])", r"\1\2", t)          # hyphenated words
    t = re.sub(rf"([{_LET}])•\s*([{_LET}])", r"\1\2", t)
    t = re.sub(r"\s*\n\s*", " ", t)
    t = re.sub(r"(?<=[\d\-·])((?:\(\))+)", lambda m: "0" * (len(m.group(1)) // 2), t)   # "()" read for 0
    t = re.sub(r"(?<=-)[Oo]{2}(?=\W|$)|(?<=-\d)[Oo]|(?<=-)[Oo](?=\d)|(?<=\d)[Oo](?=[\d,\-])",
               lambda m: "0" * len(m.group(0)), t)
    t = re.sub(r"(?<=[\d\-])[lI](?=\d)|(?<=\d)[lI](?=[\d,\-])", "1", t)                # 1,l00 -> 1,100
    t = P03.repair_ocr_digits(t)
    t = re.sub(r"(?<=\d)\s?[-–—·•=_~][-–—·•=_~\s]{0,3}(?=\d)", "-", t)                  # 3,000--00·00, 3,000- 00
    # four groups ha-a-ca-dm2 (1980s: "1,945-47-47-18 Has." = 1,945 ha 47 a 47 ca 18 dm2) -> 03's decimal form "1,945-47-47.18"
    t = re.sub(r"(\d{1,3}(?:,\d{3})*-\d\d-\d\d)-(\d\d)(?=\s*(?:[HhRr][a-z&\$]{0,3}\b|\(|,?\s*\())", r"\1.\2", t)
    # "840-0000 Has.": hyphen lost between areas and centiareas
    t = re.sub(r"(?<![\d\-,\.])(\d{1,3}(?:,\d{3})*-)(\d\d)(\d\d)(?=\s*(?:[HhRr][a-z&\$]{0,3}\b|\())", r"\1\2-\3", t)
    # "718-00.00 Has", "18,375-00,00 Has": a dot / comma printed for the second hyphen
    t = re.sub(r"(?<![\d\-,\.])(\d{1,3}(?:,\d{3})*-\d\d)[\.,](\d\d)(?=\s*(?:[HhRr][a-z&\$]{0,3}\b|\())", r"\1-\2", t)
    # unit misread right after an ha-a-ca amount: "Hu.", "Hal", "H&s.", "Ras.", "Hels."
    t = re.sub(r"(\d{1,3}-\d{1,2}(?:[\.,]\d+)?)\s*[HhRr][a-z&\$]{1,3}[\.,;:]", r"\1 Has.", t)
    # amount in words inside parentheses
    def par(m):
        inner = m.group(1)
        if not re.search(r"h\W?e\W?c|t\W?[aá]\W?r\W?e\W?a|\b[aá]\W?r\W?e\W?a", inner, re.I):
            return m.group(0)
        rep = repair_number_words(inner)
        return f"({rep})" if rep else m.group(0)
    t = PAREN_RE.sub(par, t)
    # unit garbled beyond recognition ("1,916-00-00 1-1<1s. (un mil novecientas dieciseis hectareas)")
    t = re.sub(r"(\d{1,3}(?:,\d{3})*-\d\d-\d\d)\s*[^\s(]{1,8}\s*(?=\([a-z ,]*hectarea)", r"\1 Has. ", t)
    # concession verb garbled ("TERCERO.-Se roncedt\" al poblado ...")
    def verb(m):
        best = process.extractOne(norm(m.group(2)), ["concede", "conceden", "dota", "amplia", "restituye", "reconoce",
                                                       "confirma", "titula"], scorer=fuzz.ratio, score_cutoff=60)
        return f"{m.group(1)} {best[0]}" if best else m.group(0)
    t = re.sub(r"\b([Ss][eE])\s+([^\s]{4,9})(?=\s+(?:al\b|a\s+los\b|a\s+la\b|a\s+favor|por\s+concepto))", verb, t)
    t = re.sub(r"(?i)\bc\W?a\W?p\W?a\W?c\W?[il1]\W?t\S{0,7}", "capacitados ", t)   # "capacit¡¡do~"
    t = repair_signing_words(t)
    return re.sub(r"[ \t]{2,}", " ", t)


# ============================================================================================ parsing
# presidents who signed agrarian resolutions published 1976-1992 (older ones were reprinted only rarely)
PRES_FUZZY = [("echeverria", "Luis Echeverria Alvarez"), ("lopez portillo", "Jose Lopez Portillo"),
              ("de la madrid", "Miguel de la Madrid Hurtado"), ("salinas de gortari", "Carlos Salinas de Gortari"),
              ("diaz ordaz", "Gustavo Diaz Ordaz"), ("lopez mateos", "Adolfo Lopez Mateos")]
SKIP_WORDS = {"de", "del", "mes", "dias", "dia", "ano", "los", "a", "el"}


def _closing_window(clean: str) -> str:
    """The closing formula: from the first anchor ('Dado en el Palacio', 'notifiquese y ejecutese', 'Presidente
    Constitucional', 'Cumplase') in the last 1,500 characters."""
    tail = clean[-1500:]
    nt = cnorm(tail)
    starts = [m.start() for rx in CLOSING_RES for m in [rx.search(nt)] if m]
    if not starts:
        return clean[-700:]
    a = min(starts)
    if not SIGN_START_RE.match(nt, a):      # the date precedes "El Presidente ..." / "Cumplase"
        a = max(0, a - 450)
    return tail[a:]


def _fuzzy_word(tok: str, vocab, cutoff: float = 78) -> str | None:
    if tok in vocab:
        return tok
    if len(tok) < 4:
        return None
    m = process.extractOne(tok, vocab, scorer=fuzz.ratio, score_cutoff=cutoff)
    return m[0] if m else None


def parse_closing(clean: str, dof_date: dt.date) -> dict:
    """Signing date and president from the closing formula with OCR-tolerant word matching: 'a los cuatro
    diai del mes (fe Qctubte de mil novecientos setenta y seis.- El Presidente ..., Luis Echeverda Alvarez'."""
    win = _closing_window(clean)
    toks = [m.group(0) for m in re.finditer(r"[a-z]+|\d+", re.sub(r"\s+", " ", cnorm(win)))]
    numw = [w for w in P03.NUM_WORDS if w != "mi"]
    out = {"signing_date_fuzzy": None, "president_fuzzy": None, "president_fuzzy_score": None}
    def numtok(tk: str) -> str | None:
        if tk.isdigit():
            return tk
        if tk in ("y", "v"):                  # OCR reads "y" as "v"
            return "y"
        return _fuzzy_word(tk, numw, 78) if len(tk) >= 4 else (tk if tk in numw else None)

    for i, tok in enumerate(toks):
        mon = _fuzzy_word(tok, list(P03.MONTHS), 70) if len(tok) >= 4 else None
        if not mon or i < 2:
            continue
        # day: the last run of number words (or 1-2 digits) in the 8 tokens before the month
        run, j = [], i - 1
        while j >= max(0, i - 8):
            w = numtok(toks[j])
            if w is not None and not (w.isdigit() and (len(w) > 2 or run)):
                run.insert(0, w)
            elif run:
                break
            j -= 1
        while run and run[0] == "y":
            run.pop(0)
        # year: the first run of number words after the month (two junk tokens tolerated), or 4 digits
        yr_toks, k, junk = [], i + 1, 0
        while k < len(toks) and len(yr_toks) < 6:
            w = numtok(toks[k])
            if w is None or (w.isdigit() and len(w) != 4):
                if yr_toks:
                    break
                junk += toks[k] not in SKIP_WORDS
                if junk > 2:
                    break
            else:
                yr_toks.append(w)
                if w.isdigit():
                    break
            k += 1
        if yr_toks and yr_toks[0] == "novecientos":      # "mil" lost in the OCR
            yr_toks.insert(0, "mil")
        complete = bool(yr_toks) and (yr_toks[-1].isdigit() or yr_toks[-1] not in ("y", "mil", "novecientos"))
        day = P03.words_to_int(" ".join(run)) if run else None
        yr = P03.words_to_int(" ".join(yr_toks)) if yr_toks else None
        if day and yr and complete and 1 <= day <= 31 and 1915 <= yr <= dof_date.year:
            try:
                d = dt.date(yr, P03.MONTHS[mon], day)
            except ValueError:
                continue
            if d <= dof_date:
                out["signing_date_fuzzy"] = d
                break
    pm = re.search(r"p\s?r\s?e\s?\w{1,3}\s?d\s?e\s?n\s?t\s?e", cnorm(win))
    ptxt = re.sub(r"\s+", " ", cnorm(win[pm.start():] if pm else win))
    best = (None, 0.0)
    for key, name in PRES_FUZZY:
        sc = fuzz.partial_ratio(key, ptxt)
        if sc > best[1]:
            best = (name, sc)
    if best[1] >= 80:
        out["president_fuzzy"], out["president_fuzzy_score"] = best[0], round(best[1])
    return out


def operative_segment(t: str):
    """Mirror of 03.parse_body's operative section and concession segment (on normalised text)."""
    sig = list(P03.SIGN_RE.finditer(t))
    end = sig[-1].start() if sig else len(t)
    opers = list(P03.OPER_RE.finditer(t, 0, end))
    if opers:
        oper_start = opers[-1].end()
    else:
        firsts = [m for m in re.finditer(r"\bprimero\s*\.?\s*-", t[:end]) if m.start() > end * 0.4]
        oper_start = firsts[0].start() if firsts else int(end * 0.6)
    op = P03.fix_digits(t[oper_start:end])
    conc = P03.CONCESSION_RE.search(op)
    if not conc:
        return op, None, None
    seg_end = P03.NEXT_ITEM_RE.search(op, conc.end())
    seg = op[conc.start(): (seg_end.start() if seg_end else min(len(op), conc.start() + 3000))]
    if not P03.amounts_in(seg):
        seg = op[conc.start(): conc.start() + 3000]
    return op, conc, seg


def amount_check(clean: str) -> dict:
    """The granted amount as printed in digits and in words, and whether they agree."""
    t = P03.norm(clean)
    op, conc, seg = operative_segment(t)
    out = {"ha_check": "no_concession" if conc is None else "no_amount", "ha_digits_text": None,
           "ha_words_text": None, "hectares_words": None, "hectares_digits": None, "concession_window": None}
    if conc is None:
        return out
    k = op.find(seg[:60]) if seg else -1
    out["concession_window"] = op[max(0, k - 700): k + 400] if k >= 0 else seg[:400]
    am = P03.amounts_in(seg)
    flags = list(P03.AMOUNT_FLAGS)
    if not am:
        return out
    a, b, v = am[0]
    flag = flags[0]
    w = P03.word_amount(seg[a: b + 260])
    m = re.search(r"\(([^()]{3,240})\)", seg[b - 2: b + 260]) or re.search(r"\(([^()]{3,240})\)", seg[a: b + 260])
    out.update(ha_digits_text=seg[a:b].strip(), ha_words_text=m.group(1).strip() if m else None,
               hectares_words=round(w, 4) if w is not None else None, hectares_digits=round(v, 4))
    if P03.HECT_WORD_RE.search(seg[:max(0, a - 5)]):
        # an amount written in words comes before the first parsable digits: the granted amount was not read
        out["ha_check"] = "earlier_amount_unparsed"
        return out
    if flag.endswith("_corrected_by_words"):
        out["ha_check"] = "corrected_by_words"
    elif flag.endswith("_words_disagree"):
        out["ha_check"] = "disagree"
        # the printed digits are the words' digits with OCR damage to separators or a lost leading digit:
        # "1-172.28\"52" = 1,172-28-52 = "mil ciento setenta y dos hectareas veintiocho areas cincuenta y dos";
        # "~,344-00-00" with "cuatro mil trescientas cuarenta y cuatro" -> 4,344-00-00
        dseq = re.sub(r"\D", "", seg[a:b])
        wint = int(w + 1e-6)
        wa = int(round((w - wint) * 10000))
        wseq = f"{wint}{wa // 100:02d}{wa % 100:02d}"
        lead = seg[max(0, a - 2):a]
        if dseq and len(dseq) >= 5 and (dseq == wseq or (wseq.endswith(dseq) and re.search(r"[^\d\s]", lead + seg[a:a + 1]))):
            out["ha_check"] = "corrected_by_words"
            out["ha_words_rule"] = "digit_sequence" if dseq == wseq else "digit_suffix"
            out["hectares_corrected"] = round(w, 4)
    elif w is None:
        out["ha_check"] = "no_words"
    else:
        out["ha_check"] = "agree"
    return out


CLASSES_ALL = ["ha_riego", "ha_temporal", "ha_agostadero", "ha_monte", "ha_desertico", "ha_indefinido"]
PARSE_COLS = ["hectares_total", "ha_riego", "ha_temporal", "ha_agostadero", "ha_monte", "ha_desertico", "ha_indefinido",
              "beneficiaries", "beneficiaries_source", "grant", "concession_verb", "denial_phrase", "signing_date",
              "president_signing_text", "signer_body", "body_action_type", "ha_parse_flag", "water_volume_m3"]


def mark_operative(clean: str) -> tuple[str, bool]:
    """When the OCR garbled "se resuelve:", put the marker back where the resolutive points start (the first
    "PRIMERO" after "Por lo expuesto" / after the last CONSIDERANDO), so that 03's operative-section rule works."""
    nt = cnorm(clean)
    if list(P03.OPER_RE.finditer(nt)):
        return clean, False
    sig = [m.start() for rx in CLOSING_RES for m in [rx.search(nt, int(len(nt) * 0.3))] if m]
    end = min(sig) if sig else len(nt)
    cons = [m for m in CONSID_RE.finditer(nt, 0, end)]
    a = cons[-1].end() if cons else int(end * 0.5)
    pe = re.search(r"p\s?o\s?r\s+l\s?o\s+e\s?x\s?p\s?u\s?e\s?s\s?t\s?o|p\s?o\s?r\s+l\s?o\s+a\s?n\s?t\s?e\s?r\s?[il1]\s?o\s?r", nt[a:end])
    b = a + (pe.end() if pe else 0)
    pm = None
    for x in re.finditer(r"\bp\s?r\s?[il1t]\s?m\s?e\s?r\s?[o0]\b|\bu\s?n\s?[il1]\s?c\s?o\s*-", nt[b:end]):
        if not re.search(r"n\s?d\s?o\s*$", nt[max(0, b + x.start() - 12): b + x.start()]):   # not "CONSIDERANDO PRIMERO"
            pm = x
            break
    if not pm or (not pe and pm.start() > 1500):
        return clean, False
    k = b + pm.start()
    return clean[:k] + " se resuelve: " + clean[k:], True


def parse_resolution(raw: str, action: str, dof_date: dt.date, names: list | None = None) -> dict:
    """Parse one extracted resolution (column-ordered OCR text) with 03's functions after OCR repair.
    `names` (village / NCPE name, municipality from the index title): the resolutive points around the granted
    amount must name the village, else the amount may belong to another resolution (`name_in_resolutive`)."""
    clean, marked = mark_operative(clean_ocr(raw))
    body = P03.parse_body(clean, action)
    out = {c: body.get(c) for c in PARSE_COLS}
    out["operative_marker_inserted"] = int(marked)
    out.update(amount_check(clean))
    win = out.pop("concession_window", None)
    nm = [n for n in (names or []) if isinstance(n, str) and len(n) >= 3]
    def name_score_strict(n, w):
        n = clean_title(n)
        w = re.sub(r"\s+", " ", cnorm(w))
        if len(n) <= 8:      # short names ("marin", "baturi"): whole word only
            return 100.0 if re.search(r"\b" + r"\s+".join(map(re.escape, n.split())) + r"\b", w) else 0.0
        return fuzz.partial_ratio(n, w)
    out["name_in_resolutive"] = (max(name_score_strict(n, win) for n in nm) if (win and nm) else None)
    if out.get("hectares_corrected") is not None:          # digits re-read from the words (see amount_check)
        out["hectares_total"] = out["hectares_corrected"]
        for c in CLASSES_ALL:
            out[c] = None
        out["ha_indefinido"] = out["hectares_total"]
    heading = P03.parse_title(norm(clean[:400]))
    out["heading_action_type"] = heading["action_type"]
    # signing date: must precede publication
    sd = out["signing_date"]
    if sd is not None and not (dt.date(1915, 1, 6) <= sd <= dof_date):
        out["signing_date_rejected"] = sd.isoformat()
        out["signing_date"] = sd = None
    cl = parse_closing(clean, dof_date)
    out["signing_date_source"] = "03_signing_clause" if sd is not None else None
    name = out["president_signing_text"] or cl["president_fuzzy"]
    if sd is None and cl["signing_date_fuzzy"] is not None:
        if name is None or P03.president_on(cl["signing_date_fuzzy"]) == name:
            out["signing_date"] = sd = cl["signing_date_fuzzy"]
            out["signing_date_source"] = "fuzzy_closing_formula"
        else:
            out["signing_date_rejected"] = cl["signing_date_fuzzy"].isoformat()
    if sd is not None and name is not None and P03.president_on(sd) != name and out["signing_date_source"] == "03_signing_clause":
        # the name in the signature is more reliable than an OCR'd year ("ochenta [y siete]" read as 1980)
        out["signing_president_conflict"] = 1
        out["signing_date_rejected"] = sd.isoformat()
        out["signing_date"] = sd = None
        out["signing_date_source"] = None
    out["president_source"] = "03_signature_name" if out["president_signing_text"] else None
    if out["president_signing_text"] is None and cl["president_fuzzy"]:
        out["president_signing_text"] = cl["president_fuzzy"]
        out["president_source"] = f"fuzzy_name_{cl['president_fuzzy_score']}"
    if out["president_signing_text"] and out["signer_body"] is None:
        out["signer_body"] = "president"
    out["president_in_office_at_signing"] = P03.president_on(sd) if sd else None
    if action in P03.STAGE_ACTIONS:
        st = P03.parse_stages(clean, out.get("grant"), action)
        for c in P03.STAGE_COLS:
            out[c] = st[c]
    out["clean_text"] = clean
    return out


# ========================================================================================= parse step
PARSED_CSV = LOCAL / "parsed.csv"
TEXT_HEADER = """# Diario Oficial de la Federacion - presidential agrarian resolution recovered from the scanned edition
# codNota: {cod}   (SIDOF note record https://sidof.segob.gob.mx/dof/sidof/notas/nota/{cod}; no HTML text in SIDOF)
# title (SIDOF index): {title}
# DOF date: {date}, edition {edicion}, section {seccion}, printed page {pagina} (as indexed by SIDOF)
# source: {url}  (whole edition, codDiario {diario}; sha256 {sha})
# edition text file: dof_scanned_editions/{arch}  (pdftotext -layout, one JSON line per PDF page)
# this excerpt: PDF pages {p0}-{p1} of that edition; {ocrdesc}
# location: {locinfo}
"""
OCR_DESC = {"a": ("PDF text layer (Adobe Paper Capture, 2012) re-ordered column by column from pdftotext -bbox word\n"
                  "#   boxes, from the resolution heading to the signature; uncorrected OCR (noisy)"),
            "t": ("second OCR made here: tesseract 5 (300 dpi, English model) on the scanned page, lines re-ordered\n"
                  "#   column by column, from the resolution heading to the signature; uncorrected OCR (noisy)"),
            "h": ("PDF text layer (Adobe Paper Capture) of the pages where the resolution was found by reading the page\n"
                  "#   images (the automatic location failed); whole pages, re-ordered column by column; uncorrected OCR")}


def note_meta(row: dict) -> dict:
    rec = {}
    fn = NOTES_DIR / f"{int(row['codNota'])}.json"
    if fn.exists():
        rec = json.loads(fn.read_text())
    return dict(row, **{k: rec.get(k) for k in ("titulo", "codSeccion", "pagina", "codEdicion", "ordenSeccion",
                                                "fecha", "existeImagen", "existePdf") if rec.get(k) is not None})


def excerpt_with_pages(es: EditionStream, start: int, end: int) -> str:
    out = []
    for pg in range(es.page_of(start), es.page_of(max(start, end - 1)) + 1):
        a, b = es.page_span(pg)
        a, b = max(a, start), min(b, end)
        if b > a:
            out.append(f"=== pdf page {pg} ===\n{es.text[a:b].strip()}")
    return "\n".join(out) + "\n"


def parse_source(pages: list[dict], notes: list[dict], all_notes: list[dict], covers=None, offsets=None) -> dict[int, dict]:
    """Locate and parse every target note of one edition in one OCR source."""
    locs = locate_edition(pages, notes, all_notes, covers, offsets)
    es = EditionStream(pages)
    out = {}
    for nt in notes:
        cod = int(nt["codNota"])
        loc = locs.get(cod, {})
        rec = {"loc": loc, "es": es}
        if loc.get("status") == "found":
            raw = es.text[loc["start"]: loc["end"]]
            pt = P03.parse_title(nt.get("titulo") or nt.get("dof_title") or "")
            names = [nt.get("ncpe_name") if isinstance(nt.get("ncpe_name"), str) else nt.get("poblado"),
                     pt.get("ncpe_name") or pt.get("poblado")]
            res = parse_resolution(raw, nt["action_type"], dt.date.fromisoformat(nt["dof_date"]), names)
            res.pop("clean_text", None)
            rec.update(res=res, raw=raw)
        out[cod] = rec
    return out


SRC_COLS = ["status", "pdf_page_start", "pdf_page_end", "loc_score", "end_status", "text_chars", "hectares_total",
            "ha_check", "hectares_digits", "hectares_words", "ha_digits_text", "ha_words_text", "beneficiaries",
            "beneficiaries_source", "grant", "signing_date", "signing_date_source", "president_signing_text",
            "heading_action_type", "operative_marker_inserted", "name_in_resolutive"]


def src_summary(rec: dict) -> dict:
    loc, res = rec.get("loc", {}), rec.get("res", {})
    return {"status": loc.get("status", "not_found"), "pdf_page_start": loc.get("start_page"),
            "pdf_page_end": loc.get("end_page"), "loc_score": loc.get("score"), "end_status": loc.get("end_status"),
            "text_chars": len(rec.get("raw") or "") or None, **{k: res.get(k) for k in SRC_COLS[6:]}}


def same(a, b, tol=0.006) -> bool:
    return a is not None and b is not None and not pd.isna(a) and not pd.isna(b) and abs(float(a) - float(b)) <= tol


def combine_sources(a: dict, t: dict) -> dict:
    """Text-stage decision from the PDF text layer (a) and tesseract (t). Hectares accepted when one source's digits
    agree with its own amount in words; both sources must agree when both do."""
    out = {}
    named = lambda x: x.get("name_in_resolutive") is None or x.get("name_in_resolutive") >= 80
    ok = lambda x: x.get("ha_check") == "agree" and named(x)
    corr = lambda x: x.get("ha_check") == "corrected_by_words" and named(x)
    for x, nm in ((a, "text layer"), (t, "second OCR")):
        if x.get("ha_check") in ("agree", "corrected_by_words") and not named(x):
            out["ha_name_check"] = (out.get("ha_name_check", "") + f"{nm}: village not named near the amount; ").strip()
    if ok(a) and ok(t):
        if same(a["hectares_total"], t["hectares_total"]):
            out.update(hectares=a["hectares_total"], method="text_layer", confidence="high", ha_source="a",
                       ha_note="digits = words in the text layer and in the second OCR")
        elif same(a["hectares_total"], t.get("hectares_words")) or same(t["hectares_total"], a.get("hectares_words")):
            # same amount, one OCR misread a digit within the 2% words tolerance: keep the exact digits = words one
            gap = lambda x: abs(float(x["hectares_digits"]) - float(x["hectares_words"]))
            x, src = (a, "a") if gap(a) <= gap(t) else (t, "t")
            out.update(hectares=x["hectares_total"], method="text_layer" if src == "a" else "local_ocr", confidence="high",
                       ha_source=src, ha_note="both OCRs agree with the amount in words (one misread a digit)")
        else:
            out.update(ha_conflict=f"text layer {a['hectares_total']} vs second OCR {t['hectares_total']}")
    elif ok(a):
        out.update(hectares=a["hectares_total"], method="text_layer", confidence="high", ha_source="a",
                   ha_note="digits = words in the text layer")
    elif ok(t):
        out.update(hectares=t["hectares_total"], method="local_ocr", confidence="high", ha_source="t",
                   ha_note="digits = words in the second OCR (tesseract)")
    elif corr(a) or corr(t):
        x, src = (a, "a") if corr(a) else (t, "t")
        other = t if src == "a" else a
        conf = "high" if any(same(x["hectares_total"], other.get(k)) for k in ("hectares_digits", "hectares_words")) else "medium"
        out.update(hectares=x["hectares_total"], method="text_layer_words" if src == "a" else "local_ocr_words",
                   confidence=conf, ha_source=src, ha_note=f"digits re-read to match the words ({x.get('ha_digits_text')})")
    elif a.get("grant") == 0 or t.get("grant") == 0:
        out.update(denied_text=1)
    # beneficiaries: equal in both = high; one source = medium; conflict -> vision
    ba, bt = a.get("beneficiaries"), t.get("beneficiaries")
    ba = None if ba is None or pd.isna(ba) else int(ba)
    bt = None if bt is None or pd.isna(bt) else int(bt)
    if ba is not None and bt is not None:
        if ba == bt:
            out.update(beneficiaries=ba, beneficiaries_confidence="high")
        elif a.get("beneficiaries_source") == "operative" and t.get("beneficiaries_source") != "operative":
            out.update(beneficiaries=ba, beneficiaries_confidence="medium")
        elif t.get("beneficiaries_source") == "operative" and a.get("beneficiaries_source") != "operative":
            out.update(beneficiaries=bt, beneficiaries_confidence="medium")
        else:
            out.update(beneficiaries_conflict=f"{ba} vs {bt}")
    elif ba is not None or bt is not None:
        out.update(beneficiaries=ba if ba is not None else bt, beneficiaries_confidence="medium")
    out["beneficiaries_source"] = (a if ba is not None else t).get("beneficiaries_source") if out.get("beneficiaries") is not None else None
    # signing date and president
    sa, st = a.get("signing_date"), t.get("signing_date")
    if sa and st:
        if sa == st:
            out.update(signing_date=sa, signing_date_confidence="high")
        else:
            out.update(signing_date_conflict=f"{sa} vs {st}")
    elif sa or st:
        out.update(signing_date=sa or st, signing_date_confidence="medium")
    pa, pt = a.get("president_signing_text"), t.get("president_signing_text")
    out["signer"] = pa or pt
    out["signer_source"] = "text" if (pa or pt) else None
    out["grant"] = a.get("grant") if a.get("grant") is not None and not pd.isna(a.get("grant")) else t.get("grant")
    return out


def parse_all(only: set[int] | None = None):
    tg = load_targets()
    ed_index = edition_index(set(tg["codNota"]))["editions"]
    man = {int(r["codDiario"]): r for r in read_manifest()}
    DOF_SCANNED_TEXTS_DIR.mkdir(parents=True, exist_ok=True)
    if not only:                                 # full run: no text file from an earlier location survives
        for f in DOF_SCANNED_TEXTS_DIR.glob("*.txt"):
            f.unlink()
    rows = []
    for diario, sub in tg.groupby(tg["codDiario"].fillna(-1).astype(int)):
        if only and diario not in only:
            continue
        pages = load_coltext(diario) if diario in man else None
        notes = [note_meta(r) for r in sub.to_dict("records")]
        if pages is None:
            for nt in notes:
                rows.append({"codNota": int(nt["codNota"]), "codDiario": diario, "status": "edition_not_harvested"})
            continue
        m = man[diario]
        empty = text_layer_empty(pages)
        alln = ed_index.get(diario, [])
        offs = None
        if not empty and len({str(x.get("codSeccion") or "").upper() for x in alln} - {""}) > 1:
            esA = EditionStream(pages)
            offs = calibrate_sections(esA, alln, summary_pages(esA))
        A = parse_source(pages, notes, alln, None, offs)
        tp = load_tess(diario)
        T = parse_source(tp, notes, alln, None if empty else section_covers(pages), offs or {}) if tp else {}
        skipA = set() if empty else summary_pages(EditionStream(pages))
        for R in (A, T):                     # a start on a table-of-contents page is not the resolution
            for c, x in R.items():
                if x.get("loc", {}).get("status") == "found" and x["loc"]["start_page"] in skipA:
                    x["loc"] = dict(x["loc"], status="summary_page", start_page=None, end_page=None)
                    x.pop("res", None)
                    x.pop("raw", None)
        for nt in notes:
            cod = int(nt["codNota"])
            a, t = A.get(cod, {}), T.get(cod, {})
            sa, st = src_summary(a), src_summary(t) if t else {}
            found = [x for x in (a, t) if x.get("loc", {}).get("status") == "found"]
            base = {"codNota": cod, "codDiario": diario, "codSeccion": nt.get("codSeccion"), "pagina": nt.get("pagina"),
                    "codEdicion": nt.get("codEdicion") or m.get("codEdicion"), "ordenSeccion": nt.get("ordenSeccion"),
                    "pdf_pages_edition": m.get("n_pages"), "dof_date": nt["dof_date"],
                    "title": nt.get("titulo") or nt.get("dof_title"), "action_type": nt["action_type"],
                    "state_code": nt.get("state_code"), "president_in_office_at_dof": nt.get("president_in_office_at_dof"),
                    "text_layer": "none_or_watermark" if empty else "paper_capture",
                    "expected_page": (a.get("loc") or {}).get("expected_page"),
                    "status": "found" if found else "not_found", "edition_text_file": m.get("edition_text_file")}
            if not found and not empty:   # is the index page beyond the section's pages in the scan?
                cov = sorted(section_covers(pages).items())
                o = SECTION_ORD.get(str(nt.get("codSeccion") or "").upper())
                starts = dict(cov)
                if o in starts:
                    nxt = [pg for oo, pg in cov if pg > starts[o]]
                    seclen = (min(nxt) if nxt else len(pages) + 1) - starts[o]
                    base["section_pages_in_scan"] = seclen
            if not found:      # where does the village name occur at all in the edition?
                pt = P03.parse_title(nt.get("titulo") or nt.get("dof_title") or "")
                nm = clean_title(pt.get("ncpe_name") or pt.get("poblado") or "")
                if len(nm) >= 4:
                    esA = EditionStream(pages)
                    rx = re.compile(r"\b" + r"\s+".join(map(re.escape, nm.split())) + r"\b")
                    hits = sorted({esA.page_of(x.start()) for x in rx.finditer(esA.ntext)})
                    skip = summary_pages(esA)
                    base["village_pages"] = ",".join(map(str, hits))
                    base["village_only_in_summary"] = int(bool(hits) and all(h in skip for h in hits))
            base.update({f"a_{k}": v for k, v in sa.items()})
            base.update({f"t_{k}": v for k, v in st.items()})
            prim = a if a.get("loc", {}).get("status") == "found" else (t if t else a)
            ploc = prim.get("loc", {})
            base.update(pdf_page_start=ploc.get("start_page"), pdf_page_end=ploc.get("end_page"),
                        excerpt_source="a" if prim is a else "t", excerpt_start=ploc.get("start"),
                        excerpt_end=ploc.get("end"))
            for xs, x in (("a", a), ("t", t)):
                xl = (x or {}).get("loc") or {}
                if xl.get("status") == "found":
                    base[f"{xs}_start"], base[f"{xs}_end"] = xl["start"], xl["end"]
            if found:
                base.update(combine_sources(sa if a.get("res") else {}, st if t.get("res") else {}))
                res = prim.get("res", {})
                for c in ("ha_riego", "ha_temporal", "ha_agostadero", "ha_monte", "ha_desertico", "ha_indefinido"):
                    src = a if base.get("ha_source") == "a" else t if base.get("ha_source") == "t" else {}
                    base[c] = (src.get("res") or {}).get(c)
                stage = {}
                for x in (a, t):                    # stage dates: text layer first, then the second OCR
                    for c in P03.STAGE_COLS:
                        v = (x.get("res") or {}).get(c)
                        if stage.get(c) is None and v is not None and not (isinstance(v, float) and pd.isna(v)):
                            stage[c] = v
                base.update(stage)
                base["body_action_type"] = res.get("heading_action_type")
                write_text_file(cod, base, m, a, t)
            rows.append(base)
    df = pd.DataFrame(rows)
    if only and PARSED_CSV.exists():
        old = pd.read_csv(PARSED_CSV)
        df = pd.concat([old[~old.codNota.isin(df.codNota)], df], ignore_index=True)
    df.to_csv(PARSED_CSV, index=False)
    f = df[df.status == "found"]
    print(f"parsed {len(df)} notes: {len(f)} located (text layer {int((f.a_status == 'found').sum())}, "
          f"second OCR {int((f.get('t_status', pd.Series(dtype=str)) == 'found').sum())})")
    print("  text-stage hectares:", f.method.value_counts(dropna=False).to_dict())
    print(f"  beneficiaries {f.beneficiaries.notna().mean():.1%}, signing date {f.signing_date.notna().mean():.1%}, "
          f"signer {f.signer.notna().mean():.1%}")


def write_text_file(cod: int, base: dict, m: dict, a: dict, t: dict):
    parts = []
    for name, x, key in (("PDF text layer (Adobe Paper Capture)", a, "a"), ("second OCR (tesseract 300 dpi, eng)", t, "t")):
        loc = x.get("loc") or {}
        if loc.get("status") != "found":
            continue
        hdr = TEXT_HEADER.format(ocrdesc=OCR_DESC[key], 
            cod=cod, title=base["title"], date=base["dof_date"], edicion=base["codEdicion"], seccion=base["codSeccion"],
            pagina=base["pagina"], url=PDF_URL.format(base["codDiario"]), diario=base["codDiario"], sha=m.get("sha256"),
            arch=m.get("edition_text_file"), p0=loc["start_page"], p1=loc["end_page"],
            locinfo=(f"expected PDF page {loc.get('expected_page')} (section cover + page - 1), found on "
                     f"{loc['start_page']} (title match score {loc.get('score')}); end: {loc.get('end_status')}"))
        parts.append(f"{hdr}# OCR source: {name}\n" + excerpt_with_pages(x["es"], loc["start"], loc["end"]))
    if parts:
        (DOF_SCANNED_TEXTS_DIR / f"{cod}.txt").write_text("\n".join(parts), encoding="utf-8")


def refetch(only: set[int] | None = None):
    """Re-download editions whose located resolutions span pages that were not kept at harvest time (location
    rules were refined after the harvest), check the sha256 against the MANIFEST, keep the pages, delete the PDF."""
    df = pd.read_csv(PARSED_CSV)
    man = {int(r["codDiario"]): r for r in read_manifest()}
    kept = collections.defaultdict(set)
    for f in PAGES_DIR.glob("*.pdf"):
        d, pg = f.stem.split("_")
        kept[int(d)].add(int(pg))
    need = collections.defaultdict(set)
    for r in df[df.status == "found"].to_dict("records"):
        d = int(r["codDiario"])
        want = set(range(int(r["pdf_page_start"]), int(r["pdf_page_end"]) + 1))
        for x in ("a", "t"):
            if pd.notna(r.get(f"{x}_pdf_page_start")):
                want |= set(range(int(r[f"{x}_pdf_page_start"]), int(r[f"{x}_pdf_page_end"]) + 1))
        if want - kept[d]:
            need[d] |= want | {max(want) + 1}
    for d in sorted(need):
        if only and d not in only:
            continue
        pdf = PDF_DIR / f"{d}.pdf"
        PDF_DIR.mkdir(parents=True, exist_ok=True)
        status, _ctype, res = polite_get(PDF_URL.format(d), dest=pdf)
        if status != 200 or res is None:
            print(f"  {d}: re-download failed ({status})")
            continue
        if res[1] != man[d]["sha256"]:
            print(f"  {d}: sha256 differs from the first download ({res[1]} vs {man[d]['sha256']}); pages not kept")
            pdf.unlink()
            continue
        n = int(man[d]["n_pages"])
        add = sorted(p for p in need[d] - kept[d] if 1 <= p <= n)
        for pg in add:
            run(["pdfseparate", "-f", str(pg), "-l", str(pg), str(pdf), str(PAGES_DIR / f"{d}_{pg:03d}.pdf")])
        pdf.unlink()
        print(f"  {d}: re-downloaded (same sha256), kept {len(add)} more pages", flush=True)


# =========================================================================================== local OCR
# A second, independent OCR of every page that holds a target resolution (tesseract, English model: digits and the
# upper-case amounts in words read well; accents are dropped, as norm() does anyway). It also fills the editions
# whose PDF has no text layer (some scans carry only a "Copia DOF" watermark text, or nothing).
TESS_DIR = LOCAL / "coltext_tess"
OCR_DPI = 300


def tesseract_page(diario: int, page: int) -> dict | None:
    """Words of one page from tesseract (300 dpi, page segmentation 3), in points, column-ordered like the PDF
    text layer."""
    src = PAGES_DIR / f"{diario}_{page:03d}.pdf"
    if not src.exists():
        return None
    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    root = RENDER_DIR / f"ocr_{diario}_{page:03d}"
    run(["pdftoppm", "-r", str(OCR_DPI), "-gray", "-png", "-singlefile", str(src), str(root)])
    png = root.with_suffix(".png")
    try:
        from PIL import Image
        with Image.open(png) as im:
            wpx, hpx = im.size
        env = dict(__import__("os").environ, OMP_THREAD_LIMIT="1")
        tsv = run(["tesseract", str(png), "stdout", "-l", "eng", "--psm", "3", "tsv"], env=env).stdout.decode("utf-8", "replace")
    finally:
        png.unlink(missing_ok=True)
    k = 72.0 / OCR_DPI
    words, groups = [], collections.OrderedDict()
    for line in tsv.splitlines()[1:]:
        f = line.split("\t")
        if len(f) < 12 or f[0] != "5" or not f[11].strip():
            continue
        x, y, w, h = (int(v) for v in f[6:10])
        wd = (x * k, y * k, (x + w) * k, (y + h) * k, f[11].strip())
        words.append(wd)
        groups.setdefault((f[2], f[3], f[4]), []).append(wd)        # tesseract's own lines (block, par, line)
    W, H = wpx * k, hpx * k
    bands = gutters(W, H, words)
    bh = (H - 0.1 * H) / N_BANDS
    lines = []
    for ws in groups.values():
        x0, y0 = min(w[0] for w in ws), min(w[1] for w in ws)
        x1, y1 = max(w[2] for w in ws), max(w[3] for w in ws)
        band = min(N_BANDS - 1, max(0, int((((y0 + y1) / 2) - 0.1 * H) // bh)))
        col = sum((x0 + x1) / 2 > c for c in bands[band])
        text = " ".join(w[4] for w in sorted(ws, key=lambda w: w[0]))
        if re.fullmatch(r"[\W_~]*", text):
            continue
        lines.append([col, round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1), text])
    lines.sort(key=lambda ln: (ln[0], ln[2]))
    # running header: lines in the top band that are the page number, the date or "DIARIO OFICIAL"
    lines = [ln for ln in lines if not ((ln[2] + ln[4]) / 2 < 0.12 * H and (
        re.fullmatch(r"\W*\d{1,3}\W*", ln[5]) or (HEADER_RE.search(ln[5]) and not re.search(r"organo|gobierno", ln[5], re.I))))]
    text = "\n".join(ln[5] for ln in lines)
    return {"pdf_page": page, "w": W, "h": H, "cuts": bands, "lines": lines, "cover": detect_cover(text),
            "sumario": is_sumario(text), "ocr": "tesseract"}


def text_layer_empty(pages: list[dict]) -> bool:
    ch = sorted(len(" ".join(ln[5] for ln in p["lines"])) for p in pages)
    med = ch[len(ch) // 2] if ch else 0
    wm = sum("Copia DOF" in " ".join(ln[5] for ln in p["lines"])[:300] for p in pages)
    return med < 400 or wm > 0.5 * len(pages)


def ocr_all(workers: int = 8):
    """Tesseract every kept page around the target resolutions (pages of the located resolution + 1, or the whole
    kept window when the text layer did not locate it)."""
    from concurrent.futures import ThreadPoolExecutor
    df = pd.read_csv(PARSED_CSV)
    TESS_DIR.mkdir(parents=True, exist_ok=True)
    kept = collections.defaultdict(set)
    for f in PAGES_DIR.glob("*.pdf"):
        d, pg = f.stem.split("_")
        kept[int(d)].add(int(pg))
    jobs = collections.defaultdict(set)
    for r in df.to_dict("records"):
        d = int(r["codDiario"]) if pd.notna(r.get("codDiario")) else None
        if d is None:
            continue
        if r.get("status") == "found":
            want = set(range(int(r["pdf_page_start"]), int(r["pdf_page_end"]) + 2))
        else:
            want = set(kept[d])
        jobs[d] |= want & kept[d]
    for d in sorted(jobs):
        fn = TESS_DIR / f"{d}.json.gz"
        have = {}
        if fn.exists():
            with gzip.open(fn, "rt", encoding="utf-8") as f:
                have = {p["pdf_page"]: p for p in json.load(f) if p.get("ocr")}
        todo = sorted(jobs[d] - set(have))
        if not todo:
            continue
        with ThreadPoolExecutor(workers) as ex:
            for res in ex.map(lambda pg: tesseract_page(d, pg), todo):
                if res:
                    have[res["pdf_page"]] = res
        n = len(load_coltext(d) or []) or max(have)
        pages = [have.get(k) or {"pdf_page": k, "w": 0, "h": 0, "cuts": [], "lines": [], "cover": None, "sumario": False}
                 for k in range(1, n + 1)]
        with gzip.open(fn, "wt", encoding="utf-8") as f:
            json.dump(pages, f, ensure_ascii=False)
        print(f"  {d}: OCR {len(todo)} pages", flush=True)


def load_tess(diario: int) -> list[dict] | None:
    fn = TESS_DIR / f"{diario}.json.gz"
    if not fn.exists():
        return None
    with gzip.open(fn, "rt", encoding="utf-8") as f:
        return json.load(f)


# ======================================================================================== vision step
LLM = _load("llm_tables", CODE_DIR / "05-investment" / "llm_tables.py")
VISION_DPI = 250
PNG_DPI = 100
CONC_ANCHOR_RE = re.compile(r"\bse\s+(?:le\s+|les\s+)?(?:concede|conceden|dota|amplia|restituye|reconoce|reconocen|confirma|"
                            r"crea|titula|decreta|otorga|niega)\b|\bes\s+procedente\b|\bno\s+ha\s+lugar\b")
VISION_PROMPT = """You are reading a crop of a scanned page of Mexico's Diario Oficial de la Federacion (1976-1992). It shows
part of a presidential agrarian resolution whose index title is:
  {title}
The crop may join two pieces (separated by a white gap): the resolutive points and, if present, the closing formula.
Transcribe exactly what is printed; do not compute, convert or guess. Return JSON:
{{"records": [{{
  "poblado": "village name as printed in the resolutive points, or null",
  "concession_sentence": "the first resolutive sentence that grants, recognizes, creates or denies land, verbatim (max 60 words), or null",
  "hectares_digits": "the FIRST surface granted in that sentence exactly as printed in digits, e.g. 3,000-00-00, or null",
  "hectares_words": "the same surface written in words exactly as printed, e.g. TRES MIL HECTAREAS, or null",
  "land_quality": "the words describing that land right after the surface, e.g. de agostadero de mala calidad, or null",
  "beneficiaries": "integer number of capacitados / campesinos / comuneros benefited stated in the resolutive points, or null",
  "denied": "true if the resolution denies the request (se niega, no ha lugar), else false",
  "signing_date": "date of the closing formula 'Dado en el Palacio del Poder Ejecutivo ... a los X dias del mes de Y de Z' as YYYY-MM-DD, or null if not visible",
  "president": "surname(s) of the President who signs, or null if not visible",
  "legible": "true if the surface is clearly legible, else false"
}}]}}"""


def render_page(diario: int, page: int, dpi: int):
    from PIL import Image
    src = PAGES_DIR / f"{diario}_{page:03d}.pdf"
    if not src.exists():
        return None
    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    out = RENDER_DIR / f"{diario}_{page:03d}_{dpi}"
    png = out.with_suffix(".png")
    if not png.exists():
        run(["pdftoppm", "-r", str(dpi), "-gray", "-png", "-singlefile", str(src), str(out)])
    return Image.open(png).convert("L")


def crop_pieces(es: EditionStream, pos: int, height_pt: float) -> list[tuple[int, float, float, float, float]]:
    """Regions (pdf_page, x0, y0, x1, y1 in points) of the column text starting at character `pos`, `height_pt`
    tall, continued at the top of the next column (same page or next page) when the column ends."""
    page, line = es.line_at(pos)
    if line is None:
        return []
    p = es.pages[page - 1]
    col = line[0]
    cl = [ln for ln in p["lines"] if ln[0] == col]
    x0, x1 = min(ln[1] for ln in cl) - 6, max(ln[3] for ln in cl) + 6
    y0 = max(0, line[2] - 14)
    ybot = max(ln[4] for ln in cl) + 6
    y1 = min(ybot, y0 + height_pt)
    pieces = [(page, x0, y0, x1, y1)]
    rest = height_pt - (y1 - y0)
    if rest > 60:
        ncol = max(ln[0] for ln in p["lines"]) + 1
        npg, ncl = (page, col + 1) if col + 1 < ncol else (page + 1, 0)
        if npg <= len(es.pages):
            q = [ln for ln in es.pages[npg - 1]["lines"] if ln[0] == ncl]
            if q:
                top = min(ln[2] for ln in q) - 6
                pieces.append((npg, min(ln[1] for ln in q) - 6, top, max(ln[3] for ln in q) + 6, top + rest))
    return pieces


def merge_pieces(pieces: list) -> list:
    """Union of crop regions that overlap on the same page and column (keeps reading order)."""
    out = []
    for pc in pieces:
        for i, q in enumerate(out):
            if pc[0] == q[0] and min(pc[3], q[3]) - max(pc[1], q[1]) > 20 and pc[2] <= q[4] + 5 and q[2] <= pc[4] + 5:
                out[i] = (q[0], min(q[1], pc[1]), min(q[2], pc[2]), max(q[3], pc[3]), max(q[4], pc[4]))
                break
        else:
            out.append(pc)
    return out


def stack_crops(diario: int, pieces: list, dpi: int = VISION_DPI):
    from PIL import Image
    pieces = merge_pieces(pieces)
    ims = []
    for page, x0, y0, x1, y1 in pieces:
        im = render_page(diario, page, dpi)
        if im is None:
            continue
        k = dpi / 72.0
        ims.append(im.crop((max(0, int(x0 * k)), max(0, int(y0 * k)), min(im.width, int(x1 * k)), min(im.height, int(y1 * k)))))
    if not ims:
        return None
    gap = 24
    w = max(i.width for i in ims)
    out = Image.new("L", (w, sum(i.height for i in ims) + gap * (len(ims) - 1)), 255)
    y = 0
    for i in ims:
        out.paste(i, (0, y))
        y += i.height + gap
    return out


def digits_value(s) -> float | None:
    """'3,000-00-00' -> 3000.0; '1,542-00-00' -> 1542.0; '586-64-16.5' -> 586.64165; plain '3000' -> 3000."""
    if not isinstance(s, str) or not s.strip():
        return None
    t = s.strip().replace(" ", "").replace("O", "0").replace("o", "0")
    m = re.match(r"(\d{1,3}(?:[,\.]\d{3})*|\d+)-(\d{1,2})-(\d{1,2})(?:[\.,](\d+))?", t)
    if m:
        v = float(re.sub(r"[,\.]", "", m.group(1))) + int(m.group(2)) / 100 + int(m.group(3)) / 10000
        if m.group(4):
            v += float("0." + m.group(4)) / 10000
        return round(v, 6)
    m = re.match(r"(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?$", t)
    if m:
        return float(m.group(1).replace(",", "") + ("." + m.group(2) if m.group(2) else ""))
    return None


def words_value(s) -> float | None:
    if not isinstance(s, str) or not s.strip():
        return None
    rep = repair_number_words(s) or norm(s)
    if not re.search(r"hectarea", rep):
        rep += " hectareas"
    return P03.word_amount(" " + rep)


def _close(a, b, tol=0.006) -> bool:
    return a is not None and b is not None and abs(a - b) <= tol + 1e-4 * max(abs(a), abs(b))


def vision_reads(client, cod: int, img, title: str, models: list[str]) -> list[dict]:
    VISION_CACHE.mkdir(parents=True, exist_ok=True)
    out = []
    for mdl in models:
        recs = LLM.read_crop(client, mdl, img, VISION_PROMPT.format(title=title), VISION_CACHE / f"{cod}_{mdl}.json")
        r = recs[0] if recs else {}
        r = dict(r, model=mdl, digits_val=digits_value(r.get("hectares_digits")),
                 words_val=words_value(r.get("hectares_words")))
        r["value"] = r["digits_val"] if r["digits_val"] is not None else r["words_val"]
        r["self_consistent"] = _close(r["digits_val"], r["words_val"], 0.02)
        out.append(r)
    return out


def needs_vision(r: dict) -> list[str]:
    why = []
    if r.get("status") != "found":
        return why
    if pd.isna(r.get("hectares")) if "hectares" in r else True:
        why.append("hectares")
    if pd.isna(r.get("beneficiaries")) if "beneficiaries" in r else True:
        why.append("beneficiaries")
    if (pd.isna(r.get("signing_date")) if "signing_date" in r else True) or (pd.isna(r.get("signer")) if "signer" in r else True):
        why.append("signing")
    return why


def vision_all(limit: int | None = None, only_notes: set[int] | None = None):
    from openai import OpenAI
    df = pd.read_csv(PARSED_CSV)
    if only_notes:
        df = df[df.codNota.isin(only_notes)]
    key = openai_api_key()
    if not key:
        raise SystemExit("no OpenAI key (config.openai_api_key)")
    client = OpenAI(api_key=key)
    start_spent = LLM.spent_usd()
    print(f"LLM ledger before: ${start_spent:.2f}; budget LLM_BUDGET_USD={__import__('os').getenv('LLM_BUDGET_USD', '20')}")
    rows = []
    todo = [r for r in df.to_dict("records") if needs_vision(r)]
    # hectares first (the main quantity), then the rest
    todo.sort(key=lambda r: (0 if "hectares" in needs_vision(r) else 1, r["codNota"]))
    print(f"{len(todo)} notes need a vision read: " + str(collections.Counter(w for r in todo for w in needs_vision(r))))
    if limit:
        todo = todo[:limit]
    cache_es: dict[tuple, EditionStream] = {}
    for n, r in enumerate(todo, 1):
        cod, diario = int(r["codNota"]), int(r["codDiario"])
        key = (diario, r.get("excerpt_source"))
        if key not in cache_es:
            cache_es = {key: EditionStream(load_tess(diario) if r.get("excerpt_source") == "t" else load_coltext(diario))}
        es = cache_es[key]
        start, end = int(r["excerpt_start"]), int(r["excerpt_end"])
        nt = es.ntext[start:end]
        opers = [m for m in P03.OPER_RE.finditer(nt)]
        o0 = opers[-1].start() if opers else int(len(nt) * 0.55)
        ca = CONC_ANCHOR_RE.search(nt, o0)
        apos = start + (ca.start() if ca else o0)
        pieces = crop_pieces(es, apos, 400)
        why = needs_vision(r)
        if "signing" in why:
            cw = _closing_window(es.text[start:end])
            cpos = start + max(0, (end - start) - len(cw))
            pieces += crop_pieces(es, cpos, 190)
        pieces = merge_pieces(pieces)
        img = stack_crops(diario, pieces)
        rec = {"codNota": cod, "vision_why": ",".join(why),
               "vision_crops": ";".join(f"p{pg}:{x0:.0f},{y0:.0f},{x1:.0f},{y1:.0f}" for pg, x0, y0, x1, y1 in pieces)}
        if img is None:
            rows.append(dict(rec, vision_status="no_page_image"))
            continue
        try:
            reads = vision_reads(client, cod, img, r.get("title") or "", LLM.READERS)
            vals = [x["value"] for x in reads]
            if not _close(vals[0], vals[1]) and "hectares" in why:
                reads += vision_reads(client, cod, img, r.get("title") or "", [LLM.TIEBREAK])
        except LLM.BudgetExceeded as e:
            print(f"  budget stop: {e}", flush=True)
            break
        except Exception as e:                      # e.g. openai.RateLimitError "insufficient_quota"
            if "quota" in str(e) or "credit" in str(e):
                print(f"  OpenAI account without credit, vision stopped: {str(e)[:160]}", flush=True)
                break
            raise
        rec.update(summarize_vision(reads, r))
        rows.append(rec)
        if n % 10 == 0:
            print(f"  [{n}/{len(todo)}] spent ${LLM.spent_usd() - start_spent:.2f}", flush=True)
    out = pd.DataFrame(rows)
    out.to_csv(LOCAL / "vision.csv", index=False)
    print(f"vision: {len(out)} notes; spent this run ${LLM.spent_usd() - start_spent:.2f} (ledger ${LLM.spent_usd():.2f})")
    if len(out):
        print(out.vision_status.value_counts().to_string())


def summarize_vision(reads: list[dict], r: dict) -> dict:
    """Consensus of the vision reads: hectares when two readers agree; confidence high when the agreed value
    also matches its own amount in words or a text-layer reading (digits or words), else medium; low when it
    took the tie-break."""
    out = {f"vision_{i}_{k}": x.get(k) for i, x in enumerate(reads) for k in
           ("model", "hectares_digits", "hectares_words", "value", "beneficiaries", "signing_date", "president",
            "denied", "poblado", "land_quality")}
    vals = [x["value"] for x in reads]
    agreed = None
    for i in range(len(reads)):
        for j in range(i + 1, len(reads)):
            if _close(vals[i], vals[j]):
                agreed = (i, j)
                break
        if agreed:
            break
    text_vals = [v for v in (r.get("hectares_digits"), r.get("hectares_words")) if pd.notna(v)]
    if agreed:
        i, j = agreed
        v = vals[i]
        support = (reads[i]["self_consistent"] or reads[j]["self_consistent"] or any(_close(v, t) for t in text_vals))
        out["vision_hectares"] = v
        out["vision_confidence"] = "low" if 2 in agreed and not support else ("high" if support else "medium")
        out["vision_status"] = "agree" + ("_tiebreak" if 2 in agreed else "")
        out["vision_land_quality"] = reads[i].get("land_quality")
    else:
        denied = [bool(x.get("denied")) is True or str(x.get("denied")).lower() == "true" for x in reads]
        out["vision_status"] = "denied" if all(denied[:2]) else "disagree"
        out["vision_hectares"] = None
    def agree_field(k, conv=lambda z: z):
        vs = [conv(x.get(k)) for x in reads[:2]]
        return vs[0] if vs[0] is not None and vs[0] == vs[1] else None
    def as_int(z):
        try:
            return int(str(z).replace(",", "").strip())
        except (TypeError, ValueError):
            return None
    def as_date(z):
        try:
            return dt.date.fromisoformat(str(z)[:10])
        except (TypeError, ValueError):
            return None
    out["vision_beneficiaries"] = agree_field("beneficiaries", as_int)
    out["vision_signing_date"] = agree_field("signing_date", as_date)
    out["vision_president"] = agree_field("president", lambda z: norm(z) if isinstance(z, str) and z.strip() else None)
    return out


# ================================================================================ image reads (by hand)
# The OpenAI account behind config.openai_api_key() had no credit on 14 Oct 2026, so the notes that the two OCRs
# could not settle were read from the page images by the agent (Claude), one read per note, on the same crops the
# vision step would send (250 dpi), and checked against every OCR reading of the same amount (digits and words).
SHEETS_DIR = LOCAL / "sheets"
IMAGE_READS = DOF_SCANNED_TEXTS_DIR / "image_reads.csv"
IMAGE_READ_COLS = ["codNota", "hectares_digits", "hectares_words", "land_quality", "beneficiaries", "denied",
                   "signing_date", "president", "legible", "read_note"]


def crop_back(es: EditionStream, pos: int, height_pt: float) -> list:
    """Regions holding the `height_pt` of column text that END at character `pos` (going back into the previous
    column / page when the column starts): the resolutive points sit right before the closing formula."""
    page, line = es.line_at(pos)
    if line is None:
        return []
    p = es.pages[page - 1]
    col = line[0]
    cl = [ln for ln in p["lines"] if ln[0] == col]
    x0, x1 = min(ln[1] for ln in cl) - 6, max(ln[3] for ln in cl) + 6
    ytop = min(ln[2] for ln in cl) - 6
    y1 = line[2] + 4
    y0 = max(ytop, y1 - height_pt)
    pieces = [(page, x0, y0, x1, y1)]
    rest = height_pt - (y1 - y0)
    if rest > 60:
        ppg, pcl = (page, col - 1) if col > 0 else (page - 1, None)
        if ppg >= 1:
            q = es.pages[ppg - 1]["lines"]
            if q:
                pcl = max(ln[0] for ln in q) if pcl is None else pcl
                ql = [ln for ln in q if ln[0] == pcl]
                if ql:
                    bot = max(ln[4] for ln in ql) + 6
                    pieces.insert(0, (ppg, min(ln[1] for ln in ql) - 6, bot - rest, max(ln[3] for ln in ql) + 6, bot))
    return pieces


def note_crops(r: dict, es: EditionStream, why: list[str]) -> list:
    """Crops for reading a note by hand: from the first resolutive concession ("se concede / reconoce / es
    procedente", after "se resuelve") found in either OCR (both share the page coordinates), 340 pt; else the
    620 pt of text before the closing formula; and the closing formula itself."""
    start, end = int(r["excerpt_start"]), int(r["excerpt_end"])
    cw = _closing_window(es.text[start:end])
    cpos = start + max(0, (end - start) - len(cw))
    pieces = []
    if "hectares" in why or "beneficiaries" in why:
        diario = int(r["codDiario"])
        for xs in (r.get("excerpt_source"), "t" if r.get("excerpt_source") == "a" else "a"):
            if pd.isna(r.get(f"{xs}_start")):
                continue
            ex = es if xs == r.get("excerpt_source") else EditionStream(load_tess(diario) if xs == "t" else load_coltext(diario))
            s0, s1 = int(r[f"{xs}_start"]), int(r[f"{xs}_end"])
            nt = ex.ntext[s0:s1]
            opers = [m for m in P03.OPER_RE.finditer(nt)]
            if not opers:
                continue
            ca = CONC_ANCHOR_RE.search(nt, opers[-1].start())
            if ca:
                pieces += crop_pieces(ex, s0 + ca.start(), 340)
                break
        if not pieces:
            pieces += crop_back(es, cpos, 620)
    if "signing" in why or not pieces:
        pieces += crop_pieces(es, cpos, 190)
    return merge_pieces(pieces)


def labelled(img, label: str):
    """The crop with a label band on top (codNota), for reading by hand."""
    from PIL import Image, ImageDraw, ImageFont
    band = 44
    out = Image.new("L", (img.width, img.height + band), 255)
    out.paste(img, (0, band))
    d = ImageDraw.Draw(out)
    d.rectangle([0, 0, img.width, band - 4], fill=0)
    d.text((10, 6), label, fill=255, font=ImageFont.load_default(size=30))
    return out


def make_sheets(only_notes: set[int] | None = None, out_dir: Path = SHEETS_DIR):
    """Crops to be read by hand for every note the text stage left open: one image per note when the amount is
    open (sheet_<codNota>.png), signature-only crops tiled four per image (sig_<k>.png); writes a 100 dpi grayscale
    PNG of each page involved to DOF_SCANNED_TEXTS_DIR."""
    from PIL import Image
    df = pd.read_csv(PARSED_CSV)
    out_dir.mkdir(parents=True, exist_ok=True)
    reads = pd.read_csv(IMAGE_READS, dtype=str).set_index("codNota") if IMAGE_READS.exists() else pd.DataFrame()
    rows, sig_tiles = [], []
    for r in df.sort_values(["codDiario", "codNota"]).to_dict("records"):
        if only_notes and int(r["codNota"]) not in only_notes:
            continue
        why = needs_vision(r)
        if not only_notes and str(int(r["codNota"])) in reads.index:     # drop what was already read by hand
            ir = reads.loc[str(int(r["codNota"]))]
            has = lambda k: isinstance(ir.get(k), str) and ir.get(k).strip() != ""
            settled = has("read_note") and bool(re.search(r"not a land grant|no number|signing only|illegible", ir["read_note"]))
            why = [w for w in why if not (
                (w == "hectares" and (has("hectares_digits") or has("hectares_words") or "not a land grant" in str(ir.get("read_note"))))
                or (w == "beneficiaries" and (has("beneficiaries") or settled))
                or (w == "signing" and (has("signing_date") or has("president") or settled)))]
        if not why or r.get("status") != "found":
            continue
        cod, diario = int(r["codNota"]), int(r["codDiario"])
        es = EditionStream(load_tess(diario) if r.get("excerpt_source") == "t" else load_coltext(diario))
        pieces = note_crops(r, es, why)
        img = stack_crops(diario, pieces, 200)
        if img is None:
            continue
        pt = P03.parse_title(r.get("title") or "")
        img = labelled(img, f"{cod} {(pt.get('ncpe_name') or pt.get('poblado') or '?')[:26]} | {','.join(w[0] for w in why)} p{'/'.join(str(p[0]) for p in pieces)}")
        if why == ["signing"]:
            sig_tiles.append((cod, img))
            fname = None
        else:
            fname = f"sheet_{cod}.png"
            img.save(out_dir / fname, optimize=True)
        rows.append({"codNota": cod, "why": ",".join(why), "file": fname, "pieces": ";".join(
            f"p{pg}:{x0:.0f},{y0:.0f},{x1:.0f},{y1:.0f}" for pg, x0, y0, x1, y1 in pieces)})
    for k in range(0, len(sig_tiles), 4):
        group = sig_tiles[k:k + 4]
        w = max(i.width for _, i in group)
        tile = Image.new("L", (w, sum(i.height + 16 for _, i in group)), 255)
        y = 0
        for cod, i in group:
            tile.paste(i, (0, y))
            y += i.height + 16
            for rw in rows:
                if rw["codNota"] == cod:
                    rw["file"] = f"sig_{k // 4:03d}.png"
        tile.save(out_dir / f"sig_{k // 4:03d}.png", optimize=True)
    pd.DataFrame(rows).to_csv(out_dir / "sheets.csv", index=False)
    print(f"{len(rows)} notes to read: {sum(1 for r in rows if r['why'] != 'signing')} amount sheets, "
          f"{len(sig_tiles)} signature crops in {(len(sig_tiles) + 3) // 4} tiles -> {out_dir}")


# ========================================================================================= hand check
HANDCHECK_DIR = LOCAL / "handcheck"
HANDCHECK_N, HANDCHECK_SEED = 40, 2026
BENEF_WORDS = r"(?:capac|campes|benef|comuner|ejidat|jefes|individ|solicit)"


def handcheck_crops(r: dict, es: EditionStream) -> list:
    """Larger crops for reading by hand: the resolutive points from "se resuelve" (520 pt, continued into the next
    column), the closing formula, and the place where the extracted number of beneficiaries is printed."""
    start, end = int(r["excerpt_start"]), int(r["excerpt_end"])
    nt = es.ntext[start:end]
    opers = [m for m in P03.OPER_RE.finditer(nt)]
    o0 = opers[-1].start() if opers else int(len(nt) * 0.55)
    pieces = crop_pieces(es, start + o0, 520)
    cw = _closing_window(es.text[start:end])
    pieces += crop_pieces(es, start + max(0, (end - start) - len(cw)), 190)
    b = r.get("beneficiaries")
    if b is not None and not pd.isna(b):
        hits = [m.start() for m in re.finditer(rf"(?<!\d){int(b)}(?!\d)\W{{0,4}}(?:\w+\s+){{0,2}}{BENEF_WORDS}", nt)]
        after = [h for h in hits if h >= o0] or hits
        if after:
            pieces += crop_pieces(es, start + max(0, after[0] - 150), 120)
    return merge_pieces(pieces)


def handcheck_sample():
    """Draw the hand-check sample among recovered notes and render its crops (local) and pages (100 dpi, Dropbox)."""
    df = build(write=False)
    rec = df[df.hectares.notna()].sort_values("codNota")
    smp = rec.sample(n=min(HANDCHECK_N, len(rec)), random_state=HANDCHECK_SEED).sort_values("codNota")
    HANDCHECK_DIR.mkdir(parents=True, exist_ok=True)
    par = pd.read_csv(PARSED_CSV).set_index("codNota")
    rows = []
    for cod in smp.codNota:
        r = dict(par.loc[cod])
        r["codNota"] = cod
        r["beneficiaries"] = smp.set_index("codNota").loc[cod, "beneficiaries"]
        diario = int(r["codDiario"])
        es = EditionStream(load_tess(diario) if r.get("excerpt_source") == "t" else load_coltext(diario))
        pieces = handcheck_crops(r, es)
        img = stack_crops(diario, pieces, 220)
        if img is None:
            continue
        img.save(HANDCHECK_DIR / f"{cod}.png", optimize=True)
        rows.append({"codNota": cod, "pieces": ";".join(f"p{pg}:{x0:.0f},{y0:.0f},{x1:.0f},{y1:.0f}"
                                                        for pg, x0, y0, x1, y1 in pieces)})
    pd.DataFrame(rows).to_csv(HANDCHECK_DIR / "sample.csv", index=False)
    print(f"hand-check sample: {len(rows)} notes (seed {HANDCHECK_SEED}) -> {HANDCHECK_DIR}")


# ============================================================================================== build
FINAL_COLS = ["codNota", "codDiario", "dof_date", "codEdicion", "codSeccion", "pagina", "pdf_pages", "pdf_page_start",
              "pdf_page_end", "title", "action_type", "body_action_type", "is_land_grant_printed", "text_layer", "hectares", "hectares_words",
              "hectares_digits_text", "hectares_words_text", "ha_riego", "ha_temporal", "ha_agostadero", "ha_monte",
              "ha_desertico", "ha_indefinido", "beneficiaries", "beneficiaries_source", "grant", "signing_date", "signer",
              "signer_source", "petition_date", "petition_type", "petition_published_date", "cam_dictamen_date",
              "mandamiento_date", "mandamiento_outcome", "cca_approval_date", "method", "confidence",
              "beneficiaries_confidence", "signing_date_confidence", "note"]


def _nn(v):
    return v is not None and not (isinstance(v, float) and pd.isna(v)) and v != ""


def classify_quality(words: str | None) -> str | None:
    if not isinstance(words, str) or not words.strip():
        return None
    cl = P03.classify_window(norm(words))
    return cl[0] if cl else None


def quality_classes(words, total: float) -> dict:
    """Land classes of an image read: 'riego=340;indefinido=30' (parts read on the page) or the words after the
    amount ('de agostadero de mala calidad' -> agostadero; mixed or unknown -> indefinido)."""
    out = {c: None for c in CLASSES_ALL}
    if isinstance(words, str) and re.fullmatch(r"\s*\w+=[\d.]+(\s*;\s*\w+=[\d.]+)*\s*", words):
        parts = {k.strip(): float(v) for k, v in (x.split("=") for x in words.split(";"))}
        for k, v in parts.items():
            out[f"ha_{k}"] = round((out.get(f"ha_{k}") or 0) + v, 4)
        rest = total - sum(parts.values())
        if rest > 0.01:
            out["ha_indefinido"] = round((out["ha_indefinido"] or 0) + rest, 4)
        return out
    cl = classify_quality(words)
    out[f"ha_{cl}" if cl else "ha_indefinido"] = total
    return out


NOT_GRANT_RE = re.compile(r"not a land grant")
PAGES_IN_NOTE_RE = re.compile(r"PDF pages? (\d+)(?:\s*(?:-|and)\s*(\d+))?")


def write_pngs(df: pd.DataFrame, reads: pd.DataFrame, handchecked: set[int]):
    """100 dpi grayscale PNGs of the pages read by hand (image reads in place of the vision model, and the hand
    check): the last two pages of the resolution (resolutive points and signature), or the PDF pages named in the
    read note when the resolution was located by hand. Replaces any earlier PNG set."""
    for f in DOF_SCANNED_TEXTS_DIR.glob("*.png"):
        f.unlink()
    n = 0
    for r in df.to_dict("records"):
        cod = int(r["codNota"])
        if cod not in reads.index and cod not in handchecked:
            continue
        pages = set()
        rn = str(reads.loc[cod].get("read_note")) if cod in reads.index else ""
        for a, b in re.findall(r"PDF pages? (\d+)(?:\s*(?:-|and)\s*(\d+))?", rn):
            pages |= set(range(int(a), int(b or a) + 1))
        if not pages and _nn(r.get("pdf_page_end")):
            e, s0 = int(r["pdf_page_end"]), int(r["pdf_page_start"])
            pages = {p for p in (e - 1, e) if p >= s0}
        for pg in sorted(pages):
            im = render_page(int(r["codDiario"]), pg, PNG_DPI)
            if im is not None:
                im.save(DOF_SCANNED_TEXTS_DIR / f"{cod}_pdfpage{pg:03d}.png", optimize=True)
                n += 1
    print(f"{n} page images (100 dpi grayscale) -> {DOF_SCANNED_TEXTS_DIR}")
    # text files for the resolutions located by hand (whole pages named in the read note)
    man = {int(m["codDiario"]): m for m in read_manifest()}
    for r in df.to_dict("records"):
        cod = int(r["codNota"])
        fn = DOF_SCANNED_TEXTS_DIR / f"{cod}.txt"
        if fn.exists() or cod not in reads.index:
            continue
        rn = str(reads.loc[cod].get("read_note"))
        pp = re.findall(r"PDF pages? (\d+)(?:\s*(?:-|and)\s*(\d+))?", rn)
        if not pp:
            continue
        pages = sorted({k for a, b in pp for k in range(int(a), int(b or a) + 1)})
        es = EditionStream(load_coltext(int(r["codDiario"])))
        m = man[int(r["codDiario"])]
        hdr = TEXT_HEADER.format(ocrdesc=OCR_DESC["h"], cod=cod, title=r["title"], date=r["dof_date"], edicion=r["codEdicion"],
                                 seccion=r["codSeccion"], pagina=r["pagina"], url=PDF_URL.format(int(r["codDiario"])),
                                 diario=int(r["codDiario"]), sha=m.get("sha256"), arch=m.get("edition_text_file"),
                                 p0=pages[0], p1=pages[-1], locinfo="by hand on the page images (" + rn + ")")
        body = "\n".join(f"=== pdf page {pg} ===\n" + es.text[slice(*es.page_span(pg))].strip() for pg in pages)
        fn.write_text(hdr + "# OCR source: PDF text layer (Adobe Paper Capture)\n" + body + "\n", encoding="utf-8")


def build(write: bool = True) -> pd.DataFrame:
    par = pd.read_csv(PARSED_CSV)
    reads = pd.read_csv(IMAGE_READS, dtype=str) if IMAGE_READS.exists() else pd.DataFrame(columns=["codNota"])
    reads["codNota"] = reads["codNota"].astype(int)
    reads = reads.set_index("codNota")
    out, val = [], []
    for r in par.to_dict("records"):
        cod = int(r["codNota"])
        o = {k: r.get(k) for k in ("codNota", "codDiario", "dof_date", "codEdicion", "codSeccion", "pagina", "pdf_page_start",
                                   "pdf_page_end", "title", "action_type", "body_action_type", "text_layer")}
        o["pdf_pages"] = (f"{int(r['pdf_page_start'])}-{int(r['pdf_page_end'])}" if _nn(r.get("pdf_page_start")) else None)
        notes = []
        src = r.get("ha_source")
        x = "a" if src == "a" else "t" if src == "t" else None
        o["hectares"] = r.get("hectares")
        o["method"], o["confidence"] = r.get("method"), r.get("confidence")
        if x:
            o["hectares_words"] = r.get(f"{x}_hectares_words")
            o["hectares_digits_text"], o["hectares_words_text"] = r.get(f"{x}_ha_digits_text"), r.get(f"{x}_ha_words_text")
        for c in CLASSES_ALL:
            o[c] = r.get(c)
        o["beneficiaries"], o["beneficiaries_source"] = r.get("beneficiaries"), r.get("beneficiaries_source")
        o["beneficiaries_confidence"] = r.get("beneficiaries_confidence")
        o["signing_date"], o["signing_date_confidence"] = r.get("signing_date"), r.get("signing_date_confidence")
        o["signer"] = r.get("signer")
        o["signer_source"] = "text_name" if _nn(r.get("signer")) else None
        o["grant"] = r.get("grant")
        for c in ("petition_date", "petition_type", "petition_published_date", "cam_dictamen_date", "mandamiento_date",
                  "mandamiento_outcome", "cca_approval_date"):
            o[c] = r.get(c)
        # ---- image read by hand (replaces the vision LLM, see above)
        o["is_land_grant_printed"] = 1
        if cod in reads.index:
            ir = reads.loc[cod]
            rn = str(ir.get("read_note")) if _nn(ir.get("read_note")) else ""
            if NOT_GRANT_RE.search(rn):
                o["is_land_grant_printed"] = 0
                o["hectares"], o["method"], o["confidence"], o["grant"] = None, "image_read", None, None
                for c in CLASSES_ALL + ["petition_date", "petition_type", "petition_published_date", "cam_dictamen_date",
                                        "mandamiento_date", "mandamiento_outcome", "cca_approval_date", "signing_date",
                                        "signing_date_confidence", "signer", "signer_source"]:
                    o[c] = None
                o["beneficiaries"] = o["beneficiaries_source"] = o["beneficiaries_confidence"] = None
            dv, wv = digits_value(ir.get("hectares_digits")), words_value(ir.get("hectares_words"))
            denied = str(ir.get("denied")).strip().lower() in ("1", "true", "yes")
            ocr_vals = [r.get(k) for k in ("a_hectares_digits", "a_hectares_words", "t_hectares_digits", "t_hectares_words")]
            if o["is_land_grant_printed"] and (dv is not None or wv is not None):
                v = dv if dv is not None else wv
                img_consistent = dv is not None and wv is not None and same(dv, wv, 0.02)
                ocr_match = any(same(v, t) for t in ocr_vals if _nn(t))
                if _nn(o["hectares"]) and not same(o["hectares"], v):
                    notes.append(f"text stage had {o['hectares']} ha ({o['method']}); the page reads {v} ha (page kept)")
                if not _nn(o["hectares"]) or not same(o["hectares"], v):
                    o["hectares"], o["hectares_words"] = v, wv
                    o["hectares_digits_text"], o["hectares_words_text"] = ir.get("hectares_digits"), ir.get("hectares_words")
                    o["method"] = "image_read"
                    o["confidence"] = ("high" if (img_consistent and ocr_match) or (img_consistent and not ocr_vals)
                                       else "medium" if (img_consistent or ocr_match) else "low")
                    o.update(quality_classes(ir.get("land_quality"), v))
                    o["grant"] = 1 if v > 0 else o["grant"]
                    if dv is not None and wv is not None and not img_consistent:
                        notes.append("printed digits and words disagree (digits kept)")
                    elif wv is None:
                        notes.append("no amount in words printed or legible")
                    if _nn(r.get("ha_conflict")):
                        notes.append(f"OCR conflict resolved on the page ({r['ha_conflict']})")
            if denied and not _nn(o["hectares"]):
                o["grant"], o["hectares"], o["method"], o["confidence"] = 0, 0.0, "image_read", "high"
                notes.append("request denied (read on the page)")
            b = ir.get("beneficiaries")
            if o["is_land_grant_printed"] and _nn(b) and str(b).strip().isdigit():
                b = int(b)
                if not _nn(o["beneficiaries"]):
                    o["beneficiaries"], o["beneficiaries_source"], o["beneficiaries_confidence"] = b, "image_read", "medium"
                elif int(o["beneficiaries"]) != b:
                    notes.append(f"beneficiaries: text {int(o['beneficiaries'])}, page {b} (page kept)")
                    o["beneficiaries"], o["beneficiaries_source"], o["beneficiaries_confidence"] = b, "image_read", "medium"
                else:
                    o["beneficiaries_confidence"] = "high"
            sd = ir.get("signing_date")
            if _nn(sd):
                if not _nn(o["signing_date"]):
                    o["signing_date"], o["signing_date_confidence"] = str(sd), "medium"
                elif str(o["signing_date"]) != str(sd):
                    notes.append(f"signing date: text {o['signing_date']}, page {sd} (page kept)")
                    o["signing_date"], o["signing_date_confidence"] = str(sd), "medium"
                else:
                    o["signing_date_confidence"] = "high"
            pr = ir.get("president")
            if _nn(pr):
                name, sc = None, 0
                for key, nm in PRES_FUZZY:
                    k2 = fuzz.partial_ratio(key, norm(pr))
                    if k2 > sc:
                        name, sc = nm, k2
                if sc >= 80 and (not _nn(o["signer"]) or o["signer"] != name):
                    if _nn(o["signer"]):
                        notes.append(f"signer: text {o['signer']}, page {name} (page kept)")
                    o["signer"], o["signer_source"] = name, "image_read"
            if rn:
                notes.append(rn)
            if not _nn(o["pdf_pages"]):
                pm = PAGES_IN_NOTE_RE.search(rn)
                if pm:
                    o["pdf_pages"] = pm.group(1) + (f"-{pm.group(2)}" if pm.group(2) else "")
        if not _nn(o["signer"]) and _nn(o["signing_date"]):
            o["signer"] = P03.president_on(dt.date.fromisoformat(str(o["signing_date"])[:10]))
            o["signer_source"] = "signing_date"
        if _nn(o["signer"]) and _nn(o["signing_date"]) and P03.president_on(dt.date.fromisoformat(str(o["signing_date"])[:10])) != o["signer"]:
            notes.append("signer named differs from the president in office on the signing date")
        # ---- notes
        if r.get("status") != "found" and not (cod in reads.index):
            if _nn(r.get("section_pages_in_scan")) and _nn(r.get("pagina")) and int(r["pagina"]) > int(r["section_pages_in_scan"]):
                notes.append(f"not in the scanned PDF: section {r['codSeccion']} has {int(r['section_pages_in_scan'])} pages in the "
                             f"scan, the index places the note on page {int(r['pagina'])}")
            elif r.get("text_layer") == "none_or_watermark":
                notes.append("not located: the edition PDF has no text layer and the page was not read")
            elif r.get("village_only_in_summary") == 1 or (_nn(r.get("village_pages")) and not str(r.get("village_pages")).strip()) \
                    or not _nn(r.get("village_pages")):
                notes.append("not in the scanned PDF: the village is named only in the table of contents"
                             + (f" (PDF pages {r['village_pages']})" if _nn(r.get("village_pages")) else "")
                             + "; the scan has fewer pages in this section than the index page number")
            else:
                notes.append(f"not located: title not found (village named on PDF pages {r['village_pages']})")
        elif not _nn(o["hectares"]) and o.get("is_land_grant_printed", 1):
            notes.append("hectares not recovered" + (f" (OCR conflict {r['ha_conflict']})" if _nn(r.get("ha_conflict")) else ""))
        if _nn(r.get("body_action_type")) and r.get("body_action_type") not in ("other", r.get("action_type")):
            notes.append(f"printed heading reads as '{r['body_action_type']}', index title as '{r['action_type']}'")
        if _nn(r.get("ha_note")) and o["method"] in ("text_layer", "text_layer_words", "local_ocr", "local_ocr_words"):
            notes.append(str(r["ha_note"]))
        o["note"] = "; ".join(notes) if notes else None
        out.append(o)
        # ---- validation rows: digits vs words in each OCR, image read vs OCR
        for xs, name in (("a", "text_layer"), ("t", "second_ocr")):
            if _nn(r.get(f"{xs}_ha_check")):
                val.append({"codNota": cod, "check": f"digits_vs_words_{name}", "field": "hectares",
                            "value_a": r.get(f"{xs}_hectares_digits"), "source_a": f"{name} digits ({r.get(f'{xs}_ha_digits_text')})",
                            "value_b": r.get(f"{xs}_hectares_words"), "source_b": f"{name} words ({r.get(f'{xs}_ha_words_text')})",
                            "agree": int(r.get(f"{xs}_ha_check") == "agree"), "detail": r.get(f"{xs}_ha_check")})
        if _nn(r.get("a_hectares_total")) and _nn(r.get("t_hectares_total")):
            val.append({"codNota": cod, "check": "text_layer_vs_second_ocr", "field": "hectares",
                        "value_a": r.get("a_hectares_total"), "source_a": "text layer", "value_b": r.get("t_hectares_total"),
                        "source_b": "second OCR", "agree": int(same(r.get("a_hectares_total"), r.get("t_hectares_total")))})
        if o["method"] == "image_read" and o["hectares"]:
            for k in ("a_hectares_digits", "a_hectares_words", "t_hectares_digits", "t_hectares_words"):
                if _nn(r.get(k)):
                    val.append({"codNota": cod, "check": "image_read_vs_ocr", "field": "hectares", "value_a": o["hectares"],
                                "source_a": "image read", "value_b": r.get(k), "source_b": k,
                                "agree": int(same(o["hectares"], r.get(k)))})
    df = pd.DataFrame(out)
    for c in FINAL_COLS:
        if c not in df:
            df[c] = None
    df = df[FINAL_COLS].sort_values(["dof_date", "codNota"]).reset_index(drop=True)
    if not write:
        return df
    # ---- hand check: scored against the values extracted when the sample was drawn (frozen in
    # HANDCHECK_EXTRACTED), not against the output corrected afterwards with what the hand check found
    if HANDCHECK_TRUTH.exists():
        hc = pd.read_csv(HANDCHECK_TRUTH, dtype=str)
        fin = (pd.read_csv(HANDCHECK_EXTRACTED) if HANDCHECK_EXTRACTED.exists() else df).set_index("codNota")
        for h in hc.to_dict("records"):
            cod = int(h["codNota"])
            if cod not in fin.index:
                continue
            e = fin.loc[cod]
            for fld, tv, ev in (("hectares", h.get("hectares_truth"), e["hectares"]),
                                ("beneficiaries", h.get("beneficiaries_truth"), e["beneficiaries"]),
                                ("signing_date", h.get("signing_date_truth"), e["signing_date"]),
                                ("signer", h.get("signer_truth"), e["signer"])):
                if not _nn(tv):
                    continue
                if fld == "hectares":
                    ok = _nn(ev) and same(float(tv), float(ev))
                elif fld == "beneficiaries":
                    ok = _nn(ev) and int(float(tv)) == int(float(ev))
                elif fld == "signer":
                    ok = _nn(ev) and norm(str(tv)) in norm(str(ev))
                else:
                    ok = _nn(ev) and str(tv)[:10] == str(ev)[:10]
                val.append({"codNota": cod, "check": "hand_check", "field": fld, "value_a": tv, "source_a": "read by hand on the page image",
                            "value_b": ev if _nn(ev) else None, "source_b": f"extracted ({e['method']})",
                            "agree": int(ok) if _nn(ev) else None,
                            "independent": int(e["method"] != "image_read"),
                            "detail": "not extracted" if not _nn(ev) else h.get("truth_note")})
    df.to_csv(DOF_SCANNED_RESOLUTIONS_CSV, index=False)
    pd.DataFrame(val).to_csv(DOF_SCANNED_VALIDATION_CSV, index=False)
    write_pngs(df, reads, set(hc.codNota.astype(int)) if HANDCHECK_TRUTH.exists() else set())
    # MANIFEST: final note -> PDF pages for this script's editions (rows written by 06_reparse_dof_texts.py are kept)
    pages = df.groupby("codDiario").apply(lambda g: ";".join(f"{int(c)}:{p if isinstance(p, str) else '?'}"
                                                             for c, p in zip(g.codNota, g.pdf_pages)),
                                         include_groups=False).to_dict()

    def upd(rows):
        for m in rows:
            k = int(m["codDiario"])
            if k in pages:
                m["codNotas_pdf_pages"] = pages[k]
        return rows
    update_manifest(upd)
    rec = df[df.hectares.notna()]
    print(f"{len(df)} notes; hectares recovered for {len(rec)} ({rec.hectares.sum():,.0f} ha); methods "
          f"{rec.method.value_counts().to_dict()}; confidence {rec.confidence.value_counts().to_dict()}")
    print(f"beneficiaries {df.beneficiaries.notna().sum()}, signing date {df.signing_date.notna().sum()}, signer {df.signer.notna().sum()}")
    return df


# ================================================================================================ main
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("mode", choices=["harvest", "refetch", "ocr", "parse", "vision", "sheets", "handcheck", "build"])
    ap.add_argument("--limit", type=int, default=None, help="harvest: at most N editions this run")
    ap.add_argument("--editions", type=str, default=None, help="harvest/parse: comma-separated codDiario")
    ap.add_argument("--notes", type=str, default=None, help="vision: comma-separated codNota")
    args = ap.parse_args()
    only = {int(x) for x in args.editions.split(",")} if args.editions else None
    if args.mode == "harvest":
        harvest(args.limit, only)
    elif args.mode == "refetch":
        refetch(only)
    elif args.mode == "ocr":
        ocr_all()
    elif args.mode == "parse":
        parse_all(only)
    elif args.mode == "vision":
        vision_all(args.limit, {int(x) for x in args.notes.split(",")} if args.notes else None)
    elif args.mode == "sheets":
        make_sheets({int(x) for x in args.notes.split(",")} if args.notes else None)
    elif args.mode == "handcheck":
        handcheck_sample()
    elif args.mode == "build":
        build(write=True)


if __name__ == "__main__":
    main()
