"""Download every census volume listed in the INEGI historical catalog (02_*) that is not yet on disk.

Files go to DATA_DIR/<industrial|economic|agricultural|population>_census/<year>/, named as INEGI names them
(<upc>.pdf, <upc>_1.pdf, <upc>.xls), so volumes downloaded by hand are recognized and skipped. Each download is checked
by its file signature (PDF / XLS / XLSX / ZIP), since INEGI answers missing files with a small HTML page and status 200.
Output: the files + DATA_DIR/<folder>/MANIFEST.csv (upc, title, edition, file, bytes, sha256, status)
Run: python code/08-census/03_download_inegi_census.py [--dry-run] [--kinds industrial,agricultural,...]
"""
import csv
import hashlib
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import DATA_DIR  # noqa: E402

SIGNATURES = {b"%PDF": "pdf", b"\xd0\xcf\x11\xe0": "xls", b"PK\x03\x04": "zip"}
INDUSTRIAL_1930_40 = {1930: "primer_censo", 1935: "segundo_censo", 1940: "tercer_censo"}  # folders made by hand
TOP = {"industrial": "industrial_census", "commerce_services": "economic_census", "economic": "economic_census",
       "agricultural": "agricultural_census", "ejido": "agricultural_census", "population": "population_census"}


def folder_for(row):
    found = re.search(r"(1[89]\d\d|20\d\d)", row["year"] or "")
    year = int(found.group(1)) if found else None
    if row["kind"] == "industrial" and year in INDUSTRIAL_1930_40:
        sub = INDUSTRIAL_1930_40[year]
    elif row["kind"] == "ejido":
        sub = f"ejidal_{year or 'unknown'}"
    elif row["kind"] == "commerce_services":
        sub = f"commerce_services_{year or 'unknown'}"
    else:
        sub = str(year or "unknown")
    return DATA_DIR / TOP[row["kind"]] / sub


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "TapadosPRI research (academic)"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return r.read()
        except Exception as e:
            err = e
            time.sleep(10 * (attempt + 1))
    raise err


def main(dry_run):
    catalog = [r for r in csv.DictReader(open(DATA_DIR / "inegi_historical_catalog.csv")) if r["status"] == "ok"]
    kinds = sys.argv[sys.argv.index("--kinds") + 1].split(",") if "--kinds" in sys.argv else list(TOP)
    catalog = [r for r in catalog if r["kind"] in kinds]
    on_disk = {p.name for d in set(TOP.values()) if (DATA_DIR / d).exists() for p in (DATA_DIR / d).rglob("*")
               if p.is_file()}
    todo = []
    for row in catalog:
        for url in filter(None, (u.strip() for u in row["files"].split("|"))):
            name = url.rsplit("/", 1)[-1]
            if name not in on_disk:
                todo.append((row, url, name))
    print(f"{len(catalog)} catalog records; {len(todo)} files not on disk")
    known = {} if dry_run else {hashlib.sha256(p.read_bytes()).hexdigest(): p.name for d in set(TOP.values())
                                if (DATA_DIR / d).exists() for p in (DATA_DIR / d).rglob("*")
                                if p.is_file() and p.suffix.lower() in (".pdf", ".xls", ".xlsx", ".zip")}
    if dry_run:
        for row, url, name in todo:
            print(f"  {folder_for(row).relative_to(DATA_DIR)}/{name}  {row['title'][:90]}")
        return
    manifests = {}
    for i, (row, url, name) in enumerate(todo, 1):
        folder = folder_for(row)
        folder.mkdir(parents=True, exist_ok=True)
        try:
            blob = fetch(url)
            kind, sha = SIGNATURES.get(blob[:4]), hashlib.sha256(blob).hexdigest()
            status = "ok" if kind and sha not in known else f"duplicate_of:{known[sha]}" if kind else "not_a_file"
            if status == "ok":
                (folder / name).write_bytes(blob)
                known[sha] = name
        except Exception as e:
            blob, sha, status = b"", "", f"error: {e}"
        manifests.setdefault(folder, []).append(dict(
            upc=row["upc"], title=row["title"], edition=row["edition"], year=row["year"], file=name, url=url,
            bytes=len(blob), sha256=sha if blob else "", status=status))
        print(f"[{i}/{len(todo)}] {status:10s} {len(blob)/1e6:7.1f} MB  {folder.relative_to(DATA_DIR)}/{name}", flush=True)
        time.sleep(1.5)
    for folder, rows in manifests.items():
        path = folder / "MANIFEST.csv"
        new = not path.exists()
        with open(path, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            if new:
                w.writeheader()
            w.writerows(rows)
    bad = [r for rows in manifests.values() for r in rows if r["status"] not in ("ok",) and
           not r["status"].startswith("duplicate_of")]
    print(f"done: {sum(len(r) for r in manifests.values()) - len(bad)} downloaded, {len(bad)} failed")
    for r in bad:
        print(f"  FAILED {r['status']}: {r['url']}")


if __name__ == "__main__":
    main("--dry-run" in sys.argv)
