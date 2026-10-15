"""
Shared helpers for the Diario Oficial (DOF / SIDOF API) agrarian scripts of the 06-land stage
(02_harvest_dof_agrarian.py, 03_parse_dof_agrarian.py, 04_build_agrarian_ledger.py, 05_recover_scanned_resolutions.py,
06_reparse_dof_texts.py).

- reading the raw harvest files (daily index and full-text JSONL, plain or gzipped)
- deciding which DOF notes are agrarian (issuing body or title keywords)
- a priority class used to order the full-text downloads (land grants first)
- HTML -> plain text, and the light HTML slimming applied before storing full texts
- text normalisation (accents, case) shared by the parser and the name matcher
- the DOF land-grant notes that the ledger counts (dof_ledger_land_grant_notes), so that 04, 05 and 06 select the same
  notes from 03's output without reading the ledger they feed

Downloaded DOF content is untrusted data: it is only parsed as JSON / text here, never executed.
"""
from __future__ import annotations

import datetime as dt
import gzip
import html as html_lib
import json
import re
import unicodedata
from pathlib import Path
from typing import Iterator

EDITIONS = ("NotasMatutinas", "NotasVespertinas", "NotasExtraordinarias")

# Issuing bodies of agrarian acts over time: Comisión Nacional Agraria (1916-34; most 1917-34 resolutions were
# printed under the Secretaría de Agricultura y Fomento and are caught by the title keywords), Departamento Agrario
# (1934-58), Departamento de Asuntos Agrarios y Colonización (1959-74), Secretaría de la Reforma Agraria
# (1975-), Tribunal Superior Agrario / Procuraduría Agraria (1992-).
AGRARIAN_ORG_RE = re.compile(r"AGRARI", re.I)

# Title keywords that flag an agrarian note issued under another body (e.g. Presidencia, Agricultura).
AGRARIAN_TITLE_RE = re.compile(
    r"\b(dotacion|ampliacion|restitucion)\b.{0,60}\b(tierras?|ejidos?|ejidal|aguas)\b"
    r"|nuevo centro de poblacion|bienes comunales|derechos agrarios|unidad(es)? de dotacion"
    r"|terrenos? ejidal|\bejidos?\b|\bejidal(es)?\b|comunidad agraria|inafectabilidad|reforma agraria"
    r"|propiedad nacional|terrenos? nacional|colonia agricola|colonia ganadera"
)


def norm(text: str | None) -> str:
    """Lower-case, strip accents, collapse whitespace."""
    if not isinstance(text, str):
        return ""
    t = unicodedata.normalize("NFKD", text)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t.lower()).strip()


def open_text(path: Path):
    """Open a .jsonl or .jsonl.gz file for reading text."""
    if str(path).endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8")
    return open(path, encoding="utf-8")


def iter_jsonl(path: Path) -> Iterator[dict]:
    """Yield JSON records, skipping a truncated last line (interrupted harvest)."""
    with open_text(path) as fh:
        try:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
        except EOFError:  # truncated gzip member
            return


def index_files(index_dir: Path) -> list[Path]:
    return sorted(list(index_dir.glob("sidof_notes_*.jsonl")) + list(index_dir.glob("sidof_notes_*.jsonl.gz")))


def fulltext_files(fulltext_dir: Path) -> list[Path]:
    return sorted(list(fulltext_dir.glob("sidof_fulltext_*.jsonl")) + list(fulltext_dir.glob("sidof_fulltext_*.jsonl.gz")))


def parse_ddmmyyyy(s: str) -> dt.date:
    return dt.datetime.strptime(s, "%d-%m-%Y").date()


def iter_index_notes(index_dir: Path) -> Iterator[tuple[dt.date, str, dict]]:
    """Yield (DOF date, edition, note) for every note in every daily-index file.

    A date harvested twice (overlapping files) is yielded once.
    """
    seen: set[str] = set()
    for fn in index_files(index_dir):
        for rec in iter_jsonl(fn):
            key = rec.get("date")
            if not key or key in seen:
                continue
            seen.add(key)
            d = parse_ddmmyyyy(key)
            resp = rec.get("response") or {}
            for ed in EDITIONS:
                for n in resp.get(ed) or []:
                    yield d, ed, n


def is_agrarian(note: dict) -> bool:
    org = note.get("codOrgaDos") or ""
    if AGRARIAN_ORG_RE.search(org):
        return True
    return bool(AGRARIAN_TITLE_RE.search(norm(note.get("titulo"))))


GRANT_RE = re.compile(
    r"dotacion|ampliacion|restitucion|nuevo centro de poblacion|bienes comunales|incorporacion de tierras"
    r"|accesion de aguas|confirmacion"
)


def priority_class(title: str) -> int:
    """Order of full-text downloads: 1 land/water grant resolutions, 2 expropriation decrees,
    3 rights (privación / reconocimiento / adjudicación) resolutions, 4 other presidential acts
    (acuerdos de inafectabilidad, declaratorias, divisiones, ...), 5 notices (avisos, solicitudes,
    notificaciones, edictos, fe de erratas)."""
    t = norm(title)
    first = t.split(" ", 1)[0] if t else ""
    notice = first in {"aviso", "avisos", "solicitud", "solicitudes", "notificacion", "notificaciones", "edicto",
                       "edictos", "fe", "iniciacion", "convocatoria", "lista", "acta", "circular", "oficio"}
    if notice:
        return 5
    if re.search(r"expropia", t):
        return 2
    if re.search(r"privacion|reconocimiento de derechos|nueva adjudicacion|nuevas adjudicaciones", t):
        return 3
    if first in {"resolucion", "resoluciones", "decreto", "sentencia"} and GRANT_RE.search(t):
        return 1
    return 4


_TAG_RE = re.compile(r"<(/?)([A-Za-z][A-Za-z0-9:]*)\b[^>]*?(/?)>")


def slim_html(raw: str | None) -> str | None:
    """Drop the MS-Word boilerplate from SIDOF's `cadenaContenido` before storage: the <head> block,
    HTML comments (Word XML), <o:p>/<span> tags and every tag attribute (styles, classes). Text,
    paragraph and table structure are kept. Cuts storage by ~65% without losing content."""
    if not isinstance(raw, str):
        return raw
    h = re.sub(r"(?is)<head\b.*?</head>", "", raw)
    h = re.sub(r"(?s)<!--.*?-->", "", h)
    h = re.sub(r"(?is)</?o:p>", "", h)
    h = _TAG_RE.sub(lambda m: "<" + m.group(1) + m.group(2).lower() + m.group(3) + ">", h)
    h = re.sub(r"(?i)</?(span|font|b|i|u|strong|em)>", "", h)
    h = re.sub(r"[ \t\r\f\v]+", " ", h)
    h = re.sub(r"\n\s*\n+", "\n", h)
    return h.strip()


def html_to_text(h: str | None) -> str:
    """Plain text: paragraphs/rows -> newlines, table cells -> ' | ', entities decoded, spaces collapsed."""
    if not isinstance(h, str) or not h:
        return ""
    t = re.sub(r"[\r\n]+", " ", h)   # source newlines are MS-Word line wrapping, not paragraph breaks
    t = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", " ", t)
    t = re.sub(r"(?s)<!--.*?-->", " ", t)
    t = re.sub(r"(?i)</t[dh]>", " | ", t)
    t = re.sub(r"(?i)<br\s*/?>|</p>|</tr>|</div>|</h\d>|</li>", "\n", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html_lib.unescape(t).replace("\xa0", " ")
    t = re.sub(r"[ \t\r\f\v]+", " ", t)
    t = re.sub(r" *\n[ \n]*", "\n", t)
    return t.strip()


# ------------------------------------------------------------------------------------- ledger land-grant population
LAND_GRANT_ACTIONS = {"dotacion", "ampliacion", "restitucion", "ncpe", "bienes_comunales"}   # = INEGI "dotacion de tierras"


def sanderson_last_dof_date(sanderson_dta: Path) -> dt.date:
    """Last publication date in Sanderson's file (3 Nov 1976). The ledger's DOF rows start the next day
    (04_build_agrarian_ledger.py). Sanderson stores dates as yymmdd integers counted from 1900."""
    import pyreadstat
    s, _ = pyreadstat.read_dta(str(sanderson_dta), usecols=["fechadepublicacion"])
    best = None
    for x in s["fechadepublicacion"].dropna():
        x = int(x)
        try:
            d = dt.date(1900 + x // 10000, (x // 100) % 100, x % 100)
        except ValueError:
            continue
        best = d if best is None or d > best else best
    return best


def dof_ledger_land_grant_notes(notes, san_end: dt.date):
    """The rows of 03's notes table (dof_agrarian_notes_1975_1992.csv, read with pandas) that 04 turns into DOF
    land-grant rows of the ledger, as 03 parsed them: published after Sanderson's last date, in the ledger's scope, on a
    land-grant action (dotacion, ampliacion, restitucion, NCPE, bienes comunales), and either granted in 03's parse or a
    resolucion without a parsed outcome (04 counts those as grants, `grant_imputed`). Denials (grant == 0) and decrees /
    acuerdos without an outcome are left out, as in the ledger. With or without a full text."""
    import pandas as pd
    d = pd.to_datetime(notes["dof_date"]).dt.date
    g = pd.to_numeric(notes["grant"], errors="coerce")
    keep = ((d > san_end) & (notes["in_ledger_scope"] == 1) & notes["action_type"].isin(LAND_GRANT_ACTIONS)
            & ((g == 1) | (g.isna() & (notes["doc_type"] == "resolucion"))))
    return notes[keep].copy()
