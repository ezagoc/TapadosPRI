"""Download locality-level census results (INEGI ITER: 2000, 2005, 2010, 2020) and the missing FRUS volume
(1969-76 vol. E-11 part 1, Mexico 1973-76). Files are stored exactly as received, with a manifest (URL, date, bytes,
SHA-256) and a check that each file is what it claims to be (zip or XML).
Output: DATA_DIR/census_iter/raw/*.zip, DATA_DIR/_web_discovery_2026-10-13/frus_mexico_tei_xml/frus1969-76ve11p1.xml,
        DATA_DIR/census_iter/raw/MANIFEST.csv
Run: python code/08-census/01_download_sources.py
"""
import csv
import datetime as dt
import hashlib
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import DATA_DIR  # noqa: E402

# 1990 and 1995 have no open-data file (checked 19 October 2026: every URL pattern returns a 2 KB error page); they are
# only in INEGI's interactive SCITEL tool, by state. Each file is checked to be a real zip before it is kept.
ITER = {
    2000: "https://www.inegi.org.mx/contenidos/programas/ccpv/2000/datosabiertos/cgpv2000_iter_00_csv.zip",
    2005: "https://www.inegi.org.mx/contenidos/programas/ccpv/2005/datosabiertos/cpv2005_iter_00_csv.zip",
    2010: "https://www.inegi.org.mx/contenidos/programas/ccpv/2010/datosabiertos/iter_nal_2010_csv.zip",
    2020: "https://www.inegi.org.mx/contenidos/programas/ccpv/2020/datosabiertos/iter/iter_00_cpv2020_csv.zip",
}
FRUS = "https://raw.githubusercontent.com/HistoryAtState/frus/master/volumes/frus1969-76ve11p1.xml"
RAW = DATA_DIR / "census_iter" / "raw"; RAW.mkdir(parents=True, exist_ok=True)
FRUS_DIR = DATA_DIR / "_web_discovery_2026-10-13" / "frus_mexico_tei_xml"


def fetch(url, dest):
    if dest.exists() and dest.stat().st_size > 0:
        return "kept"
    req = urllib.request.Request(url, headers={"User-Agent": "TapadosPRI research (academic)"})
    with urllib.request.urlopen(req, timeout=600) as r, open(dest, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    time.sleep(2)
    return "downloaded"


rows = []
for year, url in ITER.items():
    dest = RAW / f"iter_{year}_{url.rsplit('/', 1)[1]}"
    status = fetch(url, dest)
    ok = zipfile.is_zipfile(dest)
    if not ok:
        dest.unlink()
        raise SystemExit(f"{year}: not a zip file ({url}); removed")
    members = zipfile.ZipFile(dest).namelist() if ok else []
    rows.append(dict(file=dest.name, url=url, status=status, bytes=dest.stat().st_size, is_zip=ok,
                     members=";".join(members[:6]), sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),
                     date=dt.date.today().isoformat()))
    print(f"{year}: {status}, {dest.stat().st_size / 1e6:.1f} MB, zip={ok}, members={members[:3]}", flush=True)
dest = FRUS_DIR / "frus1969-76ve11p1.xml"
status = fetch(FRUS, dest)
head = dest.read_bytes()[:200]
rows.append(dict(file=dest.name, url=FRUS, status=status, bytes=dest.stat().st_size, is_zip=False, members="",
                 sha256=hashlib.sha256(dest.read_bytes()).hexdigest(), date=dt.date.today().isoformat()))
print(f"FRUS E-11: {status}, {dest.stat().st_size / 1e6:.1f} MB, xml={head.lstrip().startswith(b'<')}")
with open(RAW / "MANIFEST.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
