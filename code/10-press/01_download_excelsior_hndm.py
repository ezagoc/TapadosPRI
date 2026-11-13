"""Download the public issues of Excélsior from the Hemeroteca Nacional Digital de México (HNDM, UNAM).

What the HNDM serves (checked 13 November 2026)
    The HNDM lists Excélsior from 18 March 1917 to June 1969 (18,450 issues), but it serves the page images online only
    for issues more than a century old, by calendar year: on 13 Nov 2026 every issue up to 31 Dec 1926 opens (3,544
    issues) and every issue from 1 Jan 1927 on returns a one-page notice instead of the scan ("El fascículo ... es de
    acceso restringido y solo puede visualizarse dentro de las instalaciones de la Hemeroteca Nacional de México").
    This script downloads every page the server serves, records restricted or missing issues without downloading them,
    and never tries to get around the restriction. Each January one more year becomes public: rerun to add it.

How the site works
    The publication's viewer page carries the calendar of issues (JSON in the year selector). Posting a date (anio, mes,
    dia, pagina) to the viewer returns that page with its PDF id and the number of pages of the issue. The pages of an
    issue have consecutive ids (MongoDB ObjectIds), so one viewer request per issue gives every page's address,
    /consulta/publicacion/pdf/<id>.pdf. Each PDF is one scanned page with no text layer (OCR is a later step). The
    consecutive-id rule is checked on the first issue and every 25th issue by asking the viewer for the last page; if it
    fails, that issue's pages are looked up one by one.

Politeness
    One request at a time, about 1.2 s (jittered) between requests, exponential backoff on errors, stop after 20
    consecutive failures or when the disk has less than 20 GB free. Resumable: pages already on disk are skipped.

Output (config.EXCELSIOR_HNDM_DIR = TapadosPRI/data/press/excelsior_hndm)
    pdf/<year>/<YYYY-MM-DD>_p<NNN>.pdf   one scanned page
    manifest.csv    one row per page: date, page, n_pages, page_id, bytes, sha256, status (ok), downloaded_at;
                    one row per issue that is not served: date, page 0, status (restricted / unavailable)
    calendar.json   the issue calendar as served by the viewer
    download.log    progress log of the background run

Run
    python code/10-press/01_download_excelsior_hndm.py                 # every public issue (default: up to the year
                                                                        # that is 100 years old, e.g. 1926 in 2026)
    python code/10-press/01_download_excelsior_hndm.py --from 1925-01-01 --to 1925-01-31
    python code/10-press/01_download_excelsior_hndm.py --max-issues 2  # a test
"""
import argparse
import csv
import datetime as dt
import hashlib
import html
import json
import random
import re
import shutil
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import EXCELSIOR_HNDM_DIR  # noqa: E402

BASE = "https://hndm.iib.unam.mx"
PUB_ID = "558075be7d1e63c9fea1a244"                       # Excélsior, El
VIEWER = f"{BASE}/consulta/publicacion/visualizar/{PUB_ID}"
PDF_URL = BASE + "/consulta/publicacion/pdf/{}.pdf?coleccion=&palabras="
HEADERS = {"User-Agent": "Mozilla/5.0 (academic research; historical newspaper archive)", "Referer": VIEWER}
PAUSE = 1.2                 # seconds between requests (jittered +-30%)
MAX_FAILURES = 20           # consecutive failures before stopping
MIN_FREE_GB = 20            # stop when the disk has less free space than this
PLACEHOLDER_BYTES = 5000    # the restricted-issue notice is a ~1 KB one-page PDF; real scans are hundreds of KB
CHECK_EVERY = 25            # verify the consecutive-id rule on every n-th issue

OUT = EXCELSIOR_HNDM_DIR
PDF_DIR = OUT / "pdf"
MANIFEST = OUT / "manifest.csv"
FIELDS = ["date", "page", "n_pages", "page_id", "bytes", "sha256", "status", "downloaded_at"]


def log(msg):
    print(f"{dt.datetime.now():%Y-%m-%d %H:%M:%S}  {msg}", flush=True)


class Client:
    """A polite HTTP client: one request at a time, a jittered pause, retries with exponential backoff."""

    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update(HEADERS)
        self.last = 0.0
        self.failures = 0

    def _wait(self):
        gap = PAUSE * random.uniform(0.7, 1.3) - (time.time() - self.last)
        if gap > 0:
            time.sleep(gap)

    def request(self, method, url, **kw):
        for attempt in range(5):
            self._wait()
            try:
                r = self.s.request(method, url, timeout=90, **kw)
                self.last = time.time()
                if r.status_code == 200:
                    self.failures = 0
                    return r
                log(f"HTTP {r.status_code} on {url} (attempt {attempt + 1})")
            except requests.RequestException as e:
                self.last = time.time()
                log(f"{type(e).__name__} on {url} (attempt {attempt + 1})")
            time.sleep(min(300, 10 * 2 ** attempt))
        self.failures += 1
        if self.failures >= MAX_FAILURES:
            raise SystemExit(f"{MAX_FAILURES} consecutive failures: stopping (rerun later to resume)")
        return None


def page_text(r):
    t = re.sub(r"<script.*?</script>|<style.*?</style>|<[^>]+>", " ", r.text, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(t))


def fetch_calendar(c):
    """The issue calendar embedded in the viewer's year selector: [{aa, mes: [{mm, dia: [..]}]}]."""
    r = c.request("GET", VIEWER)
    if r is None:
        raise SystemExit("cannot open the viewer")
    m = re.search(r'<select id="anio" name="anio" onchange="Cambio\(\'(.*?)\'', r.text, re.S)
    cal = json.loads(html.unescape(m.group(1)))
    (OUT / "calendar.json").write_text(json.dumps(cal))
    return sorted(dt.date(int(y["aa"]), int(mm["mm"]), int(d)) for y in cal for mm in y["mes"] for d in mm["dia"])


def view(c, day, page):
    """Post a date and page number to the viewer: (date served, page, n_pages, pdf id), or None if not served."""
    data = {"coleccion": "", "pagina": str(page), "anio": f"{day.year}", "mes": f"{day.month:02d}", "dia": f"{day.day:02d}"}
    r = c.request("POST", VIEWER, data=data)
    if r is None:
        return None
    txt = page_text(r)
    m = re.search(r"Fecha: (\d{4}-\d\d-\d\d) Página: (\d+) de (\d+)", txt)
    pid = re.search(r"/consulta/publicacion/pdf/([0-9a-f]{24})\.pdf", r.text)
    if not m or not pid:
        return None
    return m.group(1), int(m.group(2)), int(m.group(3)), pid.group(1)


def nth_id(first, k):
    return f"{int(first, 16) + k:024x}"


def load_done():
    """Pages on disk, and issues to skip without asking the server: complete, restricted or not served."""
    done, closed, n_of = set(), set(), {}
    if MANIFEST.exists():
        with MANIFEST.open() as f:
            for row in csv.DictReader(f):
                if row["status"] == "ok":
                    done.add((row["date"], int(row["page"])))
                    n_of[row["date"]] = int(row["n_pages"])
                elif row["status"] in ("restricted", "unavailable"):
                    closed.add(row["date"])
    for day, n in n_of.items():
        if all((day, k) in done for k in range(1, n + 1)):
            closed.add(day)
    return done, closed


def append(row):
    new = not MANIFEST.exists()
    with MANIFEST.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)


def disk_ok():
    return shutil.disk_usage(OUT).free / 1e9 >= MIN_FREE_GB


def download_issue(c, day, n_check, done):
    """Download every page of one issue; returns the number of pages saved now, or None if the issue is not served."""
    first = view(c, day, 1)
    if first is None:
        append({"date": day.isoformat(), "page": 0, "status": "unavailable", "downloaded_at": dt.datetime.now().isoformat(timespec="seconds")})
        log(f"{day} not served by the viewer")
        return None
    served, _, n_pages, first_id = first
    if served != day.isoformat():
        log(f"asked {day}, viewer served {served}: skipped")
        return None
    ids = [nth_id(first_id, k) for k in range(n_pages)]
    if n_pages > 1 and n_check % CHECK_EVERY == 0:          # check the consecutive-id rule on the last page
        last = view(c, day, n_pages)
        if last is None or last[3] != ids[-1]:
            log(f"{day}: page ids are not consecutive, looking each page up")
            ids = [first_id] + [(view(c, day, k) or (None, None, None, None))[3] for k in range(2, n_pages + 1)]
    year_dir = PDF_DIR / f"{day.year}"
    year_dir.mkdir(parents=True, exist_ok=True)
    saved = 0
    for k, pid in enumerate(ids, start=1):
        if (day.isoformat(), k) in done or pid is None:
            continue
        if not disk_ok():
            raise SystemExit(f"less than {MIN_FREE_GB} GB free on disk: stopping")
        r = c.request("GET", PDF_URL.format(pid))
        if r is None:
            continue
        body = r.content
        if len(body) < PLACEHOLDER_BYTES:                     # the restricted-access notice, not a scan
            append({"date": day.isoformat(), "page": 0, "n_pages": n_pages, "page_id": pid, "bytes": len(body),
                    "status": "restricted", "downloaded_at": dt.datetime.now().isoformat(timespec="seconds")})
            log(f"{day}: restricted (only at the Hemeroteca Nacional)")
            return None
        path = year_dir / f"{day.isoformat()}_p{k:03d}.pdf"
        tmp = path.with_suffix(".part")
        tmp.write_bytes(body)
        tmp.replace(path)
        append({"date": day.isoformat(), "page": k, "n_pages": n_pages, "page_id": pid, "bytes": len(body),
                "sha256": hashlib.sha256(body).hexdigest(), "status": "ok",
                "downloaded_at": dt.datetime.now().isoformat(timespec="seconds")})
        done.add((day.isoformat(), k))
        saved += 1
    return saved


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--from", dest="start", default="1917-01-01")
    ap.add_argument("--to", dest="end", default=f"{dt.date.today().year - 100}-12-31",
                    help="last date to try (default: the latest year that is 100 years old)")
    ap.add_argument("--max-issues", type=int, default=None)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    start, end = dt.date.fromisoformat(a.start), dt.date.fromisoformat(a.end)
    c = Client()
    days = [d for d in fetch_calendar(c) if start <= d <= end]
    done, closed = load_done()
    log(f"{len(days)} issues in {start}..{end}; {len(done)} pages already on disk")
    n_issue = pages = 0
    for day in days:
        if day.isoformat() in closed:
            continue
        got = download_issue(c, day, n_issue, done)
        n_issue += 1
        pages += got or 0
        if n_issue % 10 == 0:
            log(f"{n_issue} issues visited, {pages} pages saved this run (last: {day})")
        if a.max_issues and n_issue >= a.max_issues:
            break
    log(f"finished: {n_issue} issues visited, {pages} pages saved this run")


if __name__ == "__main__":
    main()
