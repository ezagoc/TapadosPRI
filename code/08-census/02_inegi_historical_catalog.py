"""Catalog of the historical census volumes in INEGI's digital library (industrial, commercial/services/transport,
agricultural-livestock, ejido, and population censuses 1930-1950).

Uses the library's own services: the publications search (/app/api/productos/interna_v2/publicaciones/lista/resultados,
by title phrase and by project id) to list the volumes, then each record (/app/api/productos/interna_v2/ficha/datos) for
its edition, reference year, collection and the URL and size of every file (PDF, XLS, multi-part volumes).
Kept: titles naming one of the censuses with a reference year up to 1991 (agricultural/ejido) or 1989 (economic).
Output: DATA_DIR/inegi_historical_catalog.csv (one row per volume)
Run: python code/08-census/02_inegi_historical_catalog.py
"""
import csv
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import DATA_DIR  # noqa: E402

API = "https://www.inegi.org.mx/app/api/productos/interna_v2/"
BASE = "https://www.inegi.org.mx"
UA = {"User-Agent": "TapadosPRI research (academic)", "Content-Type": "application/json"}
PHRASES = ["Censo Industrial", "Censos Industriales", "Censo Agrícola", "Censos Agrícola", "Censo Ejidal",
           "Censo Agropecuario", "Censo Comercial", "Censo de Servicios", "Censo de Transportes", "Censos Económicos"]
POPULATION_PROJECTS = {"1677": 1930, "1672": 1940, "1671": 1950}   # library project ids (publicaciones/combos?opt=6)
KIND = [("agricultural", r"agr[ií]cola|ganader|agropecuari"), ("ejido", r"ejidal"), ("industrial", r"industrial"),
        ("commerce_services", r"comercial|servicios|transportes"), ("economic", r"econ[oó]mic")]
MAX_YEAR = {"agricultural": 1991, "ejido": 1991}                    # economic censuses: through 1989


def call(path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    for attempt in range(3):
        try:
            req = urllib.request.Request(API + path, data=data, headers=UA)
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            time.sleep(5 * (attempt + 1))
    return None


def search(phrase="", project=""):
    hits, page = [], 0
    while True:
        body = dict(tema="", enti="", titg="", edic="", form="", proy=project, busc=phrase, adv=False, tipob=1,
                    peri="", rango="", orden=1, pag=page, tam=100, desc=True)
        batch = (call("publicaciones/lista/resultados", body) or {}).get("list") or []
        hits += batch
        if len(batch) < 100:
            return hits
        page += 1


def classify(title):
    t = title.lower()
    if not re.search(r"\bcensos?\b", t):
        return None, None
    kind = next((k for k, p in KIND if re.search(r"censos?\s+(\w+\s+)?(" + p + ")", t)), None)
    years = [int(y) for y in re.findall(r"\b(19[2-9]\d|20[0-2]\d)\b", t)]
    return kind, (min(years) if years else None)


candidates = {}
for phrase in PHRASES:
    for h in search(phrase=phrase):
        kind, year = classify(h["titulo"] or "")
        if kind and (year is None or year <= MAX_YEAR.get(kind, 1989)):
            candidates[h["upc"]] = (kind, year)
for project, year in POPULATION_PROJECTS.items():
    for h in search(project=project):
        candidates[h["upc"]] = ("population", year)
print(f"{len(candidates)} candidate volumes; reading their records", flush=True)

rows = []
for i, (upc, (kind, year)) in enumerate(sorted(candidates.items()), 1):
    d = call(f"ficha/datos?upc={upc}&lang=false")
    time.sleep(0.5)
    if not d or not d.get("success"):
        rows.append(dict(upc=upc, kind=kind, year=year, title="", collection="", edition="", coverage="", state="",
                         mb=0, files="", status="record_unavailable"))
        continue
    g = d["info"]["generales"]
    files, mb = [], 0.0
    for f in g.get("formatos") or []:
        u = (f.get("url") or {}).get("valor")
        if u and (f.get("extension") or "").upper() in ("PDF", "XLS", "XLSX", "ZIP", "CSV"):
            files.append(u if u.startswith("http") else BASE + u)
            mb += (f.get("peso") or 0) / (1024 if (f.get("siglas") or "").upper() == "KB" else 1)
    for m in d["info"].get("multiarchivos") or []:
        u = m.get("url") or m.get("ruta") or m.get("archivo") or ""
        u = u.get("valor") if isinstance(u, dict) else u
        if u:
            files.append(u if u.startswith("http") else BASE + u)
    title = g.get("titulo") or ""
    k2, y2 = classify(title)
    rows.append(dict(upc=upc, kind=kind, year=year or y2 or g.get("temporalidad"), title=title,
                     collection=(g.get("desc_titgen") or "").strip(), edition=g.get("edicion"),
                     coverage=(g.get("desc_cobertura") or "").strip(), state=g.get("desc_entidad") or "",
                     mb=round(mb, 1), files=" | ".join(dict.fromkeys(files)), status="ok"))
    if i % 50 == 0:
        print(f"{i}/{len(candidates)}", flush=True)

out = DATA_DIR / "inegi_historical_catalog.csv"
with open(out, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
print(f"done: {len(rows)} volumes -> {out}")
