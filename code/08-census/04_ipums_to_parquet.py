"""Convert the IPUMS International extract (Mexico 1960-2020, fixed-width .dat.gz + DDI codebook) to parquet.

Reads the column layout and implied decimals from the DDI, streams the gzip in blocks of fixed-width records (one
person per line), parses every column with numpy, and writes one parquet dataset partitioned by census year.
Also writes the codebook as two CSVs (variables; value labels) so later scripts need not parse the XML.
Output: DATA_DIR/ipums/parquet/YEAR=<year>/*.parquet, ipums/codebook_variables.csv, ipums/codebook_values.csv
Run: python code/08-census/04_ipums_to_parquet.py [extract name, default ipumsi_00001]
"""
import csv
import gzip
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import DATA_DIR  # noqa: E402

EXTRACT = sys.argv[1] if len(sys.argv) > 1 else "ipumsi_00001"
IPUMS = DATA_DIR / "ipums"
BLOCK = 1_000_000                                   # records per block (~0.5 GB of raw text)

root = ET.parse(IPUMS / f"{EXTRACT}.xml").getroot()
ns = {"d": root.tag.split("}")[0].strip("{")}
variables, values = [], []
for v in root.findall(".//d:dataDscr/d:var", ns):
    loc, lab = v.find("d:location", ns), v.find("d:labl", ns)
    variables.append(dict(name=v.get("name"), start=int(loc.get("StartPos")), width=int(loc.get("width")),
                          decimals=int(v.get("dcml") or 0), label=(lab.text or "").strip() if lab is not None else ""))
    for c in v.findall("d:catgry", ns):
        values.append(dict(name=v.get("name"), code=(c.findtext("d:catValu", "", ns) or "").strip(),
                           label=(c.findtext("d:labl", "", ns) or "").strip()))
for name, rows in (("codebook_variables.csv", variables), ("codebook_values.csv", values)):
    with open(IPUMS / name, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
LINE = max(v["start"] + v["width"] - 1 for v in variables) + 1    # record + newline
print(f"{len(variables)} variables, {len(values)} value labels, record length {LINE - 1}", flush=True)


def parse(block):
    """Fixed-width digits -> int64 per column (implied decimals -> float64). Non-digit fields fall back to text."""
    a = np.frombuffer(block, dtype=np.uint8).reshape(-1, LINE)
    assert (a[:, -1] == 10).all(), "record length does not match the DDI layout"
    cols = {}
    for v in variables:
        f = a[:, v["start"] - 1: v["start"] - 1 + v["width"]]
        d = f.astype(np.int64) - 48
        if ((d >= 0) & (d <= 9)).all():
            x = d @ (10 ** np.arange(v["width"] - 1, -1, -1, dtype=np.int64))
        else:                                       # blanks or signs: parse as text
            txt = np.char.strip(f.copy().view(f"S{v['width']}").ravel().astype(str))
            x = np.array([int(t) if t.lstrip("-").isdigit() else -1 for t in txt], dtype=np.int64)
        cols[v["name"]] = x / 10 ** v["decimals"] if v["decimals"] else x
    return pa.table({k: pa.array(x, type=TYPES[k]) for k, x in cols.items()})


TYPES = {v["name"]: pa.float64() if v["decimals"] else pa.int32() if v["width"] <= 9 else pa.int64() for v in variables}


out = IPUMS / "parquet"
writers, counts = {}, {}
with gzip.open(IPUMS / f"{EXTRACT}.dat.gz", "rb") as g:
    while block := g.read(BLOCK * LINE):
        t = parse(block)
        for year in np.unique(t["YEAR"].to_numpy()):
            sub = t.filter(pa.compute.equal(t["YEAR"], year))
            if year not in writers:
                (out / f"YEAR={year}").mkdir(parents=True, exist_ok=True)
                writers[year] = pq.ParquetWriter(out / f"YEAR={year}" / "part-0.parquet", sub.schema, compression="zstd")
            writers[year].write_table(sub.cast(writers[year].schema))
            counts[year] = counts.get(year, 0) + sub.num_rows
        print(f"{sum(counts.values()):,} records; years so far {sorted(counts)}", flush=True)
for w in writers.values():
    w.close()
for year, n in sorted(counts.items()):
    print(f"  {year}: {n:,} person records")
