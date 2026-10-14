"""
Harvest the Diario Oficial de la Federación (DOF) through the public SIDOF API of the Secretaría de
Gobernación: the daily index of every DOF note, and the full text of every agrarian note.

Endpoints (public, undocumented JSON):
  daily index  https://sidof.segob.gob.mx/dof/sidof/notas/DD-MM-YYYY
               -> NotasMatutinas / NotasVespertinas / NotasExtraordinarias: codNota, titulo, fecha,
                  codOrgaDos (issuing body), pagina, existeHtml, ...
  full note    https://sidof.segob.gob.mx/dof/sidof/notas/nota/<codNota>
               -> Nota.cadenaContenido (HTML; available for ~88-100% of notes from 1975 on, ~none before 1972)

Modes
  index     --start YYYY-MM-DD --end YYYY-MM-DD
            One JSON line per day {"date": "DD-MM-YYYY", "response": <raw API response>}, written to
            config.DOF_SIDOF_INDEX_DIR/sidof_notes_<YYYY>.jsonl. Days already present in ANY
            sidof_notes_*.jsonl[.gz] of that folder are skipped (the 2026-10-13 pilot files cover 1938 and
            1977-1992 in multi-year files; this script continues them with one file per year).
  fulltext  --first-year 1975 --last-year 1992
            For every agrarian note in the index (issuing body = Departamento Agrario / DAAC / Secretaría de la
            Reforma Agraria / Tribunal Superior Agrario / Procuraduría Agraria, or an agrarian title under
            another body) with existeHtml = "S", fetch the full note. Stored one JSON line per note in
            config.DOF_SIDOF_FULLTEXT_DIR/sidof_fulltext_<YYYY>.jsonl: the index metadata plus `html` =
            cadenaContenido after dof_agrarian_utils.slim_html (MS-Word <head>, comments and tag attributes
            dropped; text and table structure intact). Downloads are ordered by priority class (1 land/water
            grants, 2 expropriations, 3 rights resolutions, 4 other acts, 5 notices), then by date, so an
            interrupted run has the most useful notes first. Notes already stored are skipped.
  compact   gzip every sidof_fulltext_<YYYY>.jsonl (line counts verified) -> .jsonl.gz. Readers accept both.
  status    coverage table by year (days indexed, notes, agrarian notes, with html, full texts stored).

Politeness: a global rate limit across workers (--rate requests/second, default 6), up to 5 retries
with exponential back-off per request, and an automatic pause when several consecutive requests fail.
Progress goes to stdout and to <out folder>/harvest_log.txt. Every mode is resumable: just re-run.

Run (Python with no site/cwd imports, since the content is untrusted):
  python -I code/06-land/02_harvest_dof_agrarian.py index --start 1975-01-01 --end 1976-12-31 --workers 4
  python -I code/06-land/02_harvest_dof_agrarian.py fulltext --first-year 1975 --last-year 1992 --workers 4
  python -I code/06-land/02_harvest_dof_agrarian.py status
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import gzip
import json
import queue
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import DOF_SIDOF_INDEX_DIR, DOF_SIDOF_FULLTEXT_DIR  # noqa: E402
from dof_agrarian_utils import (  # noqa: E402
    fulltext_files, index_files, is_agrarian, iter_index_notes, iter_jsonl, parse_ddmmyyyy,
    priority_class, slim_html,
)

BASE = "https://sidof.segob.gob.mx/dof/sidof/notas"
UA = "Mozilla/5.0 (academic research; TapadosPRI land-reform project)"
ERRORS: collections.Counter = collections.Counter()   # error type -> count, reported in the log


class RateLimiter:
    """Global minimum spacing between request starts, shared by all worker threads."""

    def __init__(self, rate: float):
        self.interval = 1.0 / rate
        self.lock = threading.Lock()
        self.next_t = time.monotonic()
        self.pause_until = 0.0

    def wait(self):
        with self.lock:
            now = time.monotonic()
            t = max(self.next_t, now, self.pause_until)
            self.next_t = t + self.interval
        delay = t - time.monotonic()
        if delay > 0:
            time.sleep(delay)

    def pause(self, seconds: float):
        with self.lock:
            self.pause_until = max(self.pause_until, time.monotonic() + seconds)


def open_append(path: Path):
    """Open a JSONL file for appending; if an interrupted run left a partial last line, start a new line."""
    if path.exists() and path.stat().st_size > 0:
        with open(path, "rb") as fh:
            fh.seek(-1, 2)
            last = fh.read(1)
        if last != b"\n":
            with open(path, "a", encoding="utf-8") as fh:
                fh.write("\n")
    return open(path, "a", encoding="utf-8")


class Log:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.fh = open(path, "a", encoding="utf-8")

    def __call__(self, msg: str):
        line = f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
        print(line, flush=True)
        self.fh.write(line + "\n")
        self.fh.flush()


def fetch_json(url: str, limiter: RateLimiter, fails: collections.deque, tries: int = 5) -> dict | None:
    """GET a JSON document with retries; returns None after `tries` failures."""
    for k in range(tries):
        limiter.wait()
        try:
            # NB: no Accept header -- with "Accept: application/json" the server answers 406
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=90) as r:
                raw = r.read().decode("utf-8")
            j = json.loads(raw)
            if not isinstance(j, dict) or j.get("messageCode") not in (200, "200"):
                raise ValueError(f"messageCode {j.get('messageCode') if isinstance(j, dict) else type(j)}")
            fails.append(0)
            return j
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError, ConnectionError, OSError) as e:
            fails.append(1)
            ERRORS[type(e).__name__ + str(getattr(e, "code", ""))] += 1
            if sum(ERRORS.values()) in (1, 10, 100, 1000):
                print(f"request error #{sum(ERRORS.values())}: {url} {e!r}", flush=True)
            if len(fails) >= 10 and sum(fails) >= 8:   # the server is struggling: everyone pauses
                limiter.pause(60)
            code = getattr(e, "code", None)
            if code in (404, 406):
                return None
            time.sleep(min(120, 5 * 2 ** k))
    return None


def run_pool(tasks: list, worker_fn, writer_fn, workers: int, log: Log, label: str, every: int = 200):
    """Fetch `tasks` with `workers` threads; results are written by the calling thread (single writer)."""
    q_in: queue.Queue = queue.Queue()
    q_out: queue.Queue = queue.Queue(maxsize=1000)
    for t in tasks:
        q_in.put(t)
    stop = object()

    def work():
        while True:
            try:
                t = q_in.get_nowait()
            except queue.Empty:
                q_out.put(stop)
                return
            q_out.put((t, worker_fn(t)))

    threads = [threading.Thread(target=work, daemon=True) for _ in range(workers)]
    for th in threads:
        th.start()
    done = ok = 0
    finished = 0
    t0 = time.time()
    while finished < workers:
        item = q_out.get()
        if item is stop:
            finished += 1
            continue
        t, res = item
        done += 1
        if res is not None:
            writer_fn(t, res)
            ok += 1
        if done % every == 0 or done == len(tasks):
            rate = done / max(1e-9, time.time() - t0)
            eta = (len(tasks) - done) / max(rate, 1e-9) / 60
            log(f"{label}: {done}/{len(tasks)} done, {ok} ok, {done - ok} failed, {rate:.1f}/s, ETA {eta:.0f} min")
    return ok, done - ok


# --------------------------------------------------------------------------------------------- index
def indexed_dates(index_dir: Path) -> set[str]:
    done = set()
    for fn in index_files(index_dir):
        for rec in iter_jsonl(fn):
            if rec.get("date"):
                done.add(rec["date"])
    return done


def mode_index(args, log: Log):
    d0, d1 = dt.date.fromisoformat(args.start), dt.date.fromisoformat(args.end)
    done = indexed_dates(DOF_SIDOF_INDEX_DIR)
    todo = []
    d = d0
    while d <= d1:
        key = d.strftime("%d-%m-%Y")
        if key not in done:
            todo.append(key)
        d += dt.timedelta(days=1)
    log(f"index {d0}..{d1}: {len(todo)} days to fetch ({len(done)} days already in {DOF_SIDOF_INDEX_DIR.name})")
    if not todo:
        return
    limiter = RateLimiter(args.rate)
    fails: collections.deque = collections.deque(maxlen=10)
    handles: dict[int, object] = {}

    def worker(key):
        return fetch_json(f"{BASE}/{key}", limiter, fails)

    def writer(key, resp):
        year = int(key[-4:])
        if year not in handles:
            handles[year] = open_append(DOF_SIDOF_INDEX_DIR / f"sidof_notes_{year}.jsonl")
        fh = handles[year]
        fh.write(json.dumps({"date": key, "response": resp}, ensure_ascii=False) + "\n")
        fh.flush()

    try:
        ok, bad = run_pool(todo, worker, writer, args.workers, log, "index", every=100)
    finally:
        for fh in handles.values():
            fh.close()
    log(f"index finished: {ok} days written, {bad} failed (re-run to retry); request errors {dict(ERRORS)}")


# ------------------------------------------------------------------------------------------ fulltext
def stored_notes(fulltext_dir: Path) -> set[int]:
    have = set()
    for fn in fulltext_files(fulltext_dir):
        for rec in iter_jsonl(fn):
            if rec.get("codNota") is not None and rec.get("html") is not None:
                have.add(int(rec["codNota"]))
    return have


def mode_fulltext(args, log: Log):
    DOF_SIDOF_FULLTEXT_DIR.mkdir(parents=True, exist_ok=True)
    have = stored_notes(DOF_SIDOF_FULLTEXT_DIR)
    cand = {}
    for d, ed, n in iter_index_notes(DOF_SIDOF_INDEX_DIR):
        if not (args.first_year <= d.year <= args.last_year):
            continue
        if n.get("existeHtml") != "S" or not is_agrarian(n):
            continue
        cod = int(n["codNota"])
        if cod in have or cod in cand:
            continue
        cand[cod] = {
            "codNota": cod, "date": d.isoformat(), "edition": ed, "titulo": n.get("titulo"),
            "codOrgaUno": n.get("codOrgaUno"), "codOrgaDos": n.get("codOrgaDos"), "pagina": n.get("pagina"),
            "codSeccion": n.get("codSeccion"), "priority_class": priority_class(n.get("titulo") or ""),
        }
    tasks = sorted(cand.values(), key=lambda r: (r["priority_class"], r["date"], r["codNota"]))
    if args.max_class:
        tasks = [t for t in tasks if t["priority_class"] <= args.max_class]
    by_class = collections.Counter(t["priority_class"] for t in tasks)
    log(f"fulltext {args.first_year}-{args.last_year}: {len(tasks)} notes to fetch by class {dict(sorted(by_class.items()))}; "
        f"{len(have)} already stored")
    if not tasks:
        return
    limiter = RateLimiter(args.rate)
    fails: collections.deque = collections.deque(maxlen=10)
    handles: dict[int, object] = {}

    def worker(t):
        return fetch_json(f"{BASE}/nota/{t['codNota']}", limiter, fails)

    def writer(t, resp):
        nota = resp.get("Nota") or {}
        rec = dict(t)
        rec["fetched_utc"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        rec["nota_fecha"] = nota.get("fecha")
        rec["nombOrganismo"] = nota.get("nombOrganismo")
        rec["codEdicion"] = nota.get("codEdicion")
        rec["html_raw_chars"] = len(nota.get("cadenaContenido") or "")
        rec["html"] = slim_html(nota.get("cadenaContenido")) if nota else None
        if rec["html"] is None:
            rec["html"] = ""   # fetched, no content: stored so it is not re-requested
        year = int(t["date"][:4])
        if year not in handles:
            handles[year] = open_append(DOF_SIDOF_FULLTEXT_DIR / f"sidof_fulltext_{year}.jsonl")
        fh = handles[year]
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()

    try:
        ok, bad = run_pool(tasks, worker, writer, args.workers, log, "fulltext", every=500)
    finally:
        for fh in handles.values():
            fh.close()
    log(f"fulltext finished: {ok} notes written, {bad} failed (re-run to retry); request errors {dict(ERRORS)}")


# ------------------------------------------------------------------------------------ compact/status
def mode_compact(args, log: Log):
    for fn in sorted(DOF_SIDOF_FULLTEXT_DIR.glob("sidof_fulltext_*.jsonl")):
        gz = fn.with_suffix(".jsonl.gz")
        lines = [ln for ln in open(fn, encoding="utf-8") if ln.strip()]
        valid = []
        for ln in lines:
            try:
                json.loads(ln)
                valid.append(ln if ln.endswith("\n") else ln + "\n")
            except json.JSONDecodeError:
                pass
        mode = "at" if gz.exists() else "wt"
        with gzip.open(gz, mode, encoding="utf-8", compresslevel=6) as out:
            out.writelines(valid)
        n_gz = sum(1 for _ in iter_jsonl(gz))
        log(f"compact {fn.name}: {len(valid)} lines -> {gz.name} ({n_gz} lines total, {gz.stat().st_size/1e6:.1f} MB)")
        fn.unlink()


def mode_status(args, log: Log):
    days = collections.Counter()
    notes = collections.Counter()
    agr = collections.Counter()
    agr_html = collections.Counter()
    seen_dates = set()
    for d, ed, n in iter_index_notes(DOF_SIDOF_INDEX_DIR):
        seen_dates.add(d)
        notes[d.year] += 1
        if is_agrarian(n):
            agr[d.year] += 1
            agr_html[d.year] += n.get("existeHtml") == "S"
    for d in seen_dates:
        days[d.year] += 1
    full = collections.Counter()
    full_nonempty = collections.Counter()
    for fn in fulltext_files(DOF_SIDOF_FULLTEXT_DIR):
        for rec in iter_jsonl(fn):
            y = int(rec["date"][:4])
            full[y] += 1
            full_nonempty[y] += bool(rec.get("html"))
    # days with an index record (weekend/holiday days come back with zero notes and still count)
    all_dates = indexed_dates(DOF_SIDOF_INDEX_DIR)
    days_all = collections.Counter(parse_ddmmyyyy(k).year for k in all_dates)
    print(f"{'year':>4} {'days':>5} {'notes':>6} {'agrarian':>8} {'agr_html':>8} {'fulltext':>8} {'nonempty':>8}")
    for y in sorted(set(days_all) | set(full)):
        print(f"{y:>4} {days_all[y]:>5} {notes[y]:>6} {agr[y]:>8} {agr_html[y]:>8} {full[y]:>8} {full_nonempty[y]:>8}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="mode", required=True)
    p = sub.add_parser("index")
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p = sub.add_parser("fulltext")
    p.add_argument("--first-year", type=int, default=1975)
    p.add_argument("--last-year", type=int, default=1992)
    p.add_argument("--max-class", type=int, default=0, help="only fetch priority classes <= this (0 = all)")
    sub.add_parser("compact")
    sub.add_parser("status")
    for p in sub.choices.values():
        p.add_argument("--workers", type=int, default=4)
        p.add_argument("--rate", type=float, default=6.0, help="max requests per second across all workers")
    args = ap.parse_args()
    out_dir = DOF_SIDOF_FULLTEXT_DIR if args.mode in ("fulltext", "compact") else DOF_SIDOF_INDEX_DIR
    log = Log(out_dir / "harvest_log.txt")
    {"index": mode_index, "fulltext": mode_fulltext, "compact": mode_compact, "status": mode_status}[args.mode](args, log)


if __name__ == "__main__":
    main()
