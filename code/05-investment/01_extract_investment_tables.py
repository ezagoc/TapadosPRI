"""
Extract the federal public-investment tables from the Azure Document
Intelligence JSON and build a clean, long-format database.

Source: literature/InversionPublicaFederal_1925-1963-66-129.pdf.json
  (prebuilt-layout output; this excerpt = cuadros for fiscal years 1959-1963)

The volume interleaves two table families, one pair per year:
  * "INVERSION DE LAS DEPENDENCIAS, ORGANISMOS Y EMPRESAS DEL SECTOR PUBLICO"
    -> institution x state matrix   (CUADROS 15, 17, 19, 21, 23)   <-- extracted here
  * "DESTINO DE LA INVERSION PUBLICA FEDERAL"
    -> purpose x state matrix       (CUADROS 16, 18, 20, 22, 24)   (skipped)

Each yearly institution cuadro is split into "partes" (groups of ~5 states as
columns) and, within a parte, into several table objects by section. Rows are
grouped under three sectors plus a grand total:
    TOTAL
    GOBIERNO FEDERAL                 (secretariats + DDF + subsidies)
    ORGANISMOS DESCENTRALIZADOS      (PEMEX, IMSS, CFE, FFNN, ...)
    EMPRESAS DE PARTICIPACION ESTATAL (Altos Hornos, Banco de Mexico, ...)

This script:
  1. tags every table object with (cuadro, year, parte, cuadro_type) using
     document character offsets against the caption paragraphs;
  2. keeps only the institution matrices;
  3. stitches the split section-tables of each parte, tracking the current
     sector down the rows;
  4. melts to long format and cleans state names (de-hyphenated + mapped to the
     canonical config states) and OCR'd numeric values;
  5. writes a long table, an institution catalog, and a validation report.

Outputs (data/investment/):
  federal_investment_long.csv          one row per (year, institution, state)
  federal_investment_institutions.csv  canonical institution catalog by sector
  federal_investment_wide_<year>.csv   institution x state pivot per year
  federal_investment_validation.csv    subtotal vs. summed-line-items check
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

CODE_DIR = Path(__file__).resolve().parents[1]
if str(CODE_DIR) not in sys.path:
    sys.path.append(str(CODE_DIR))

from config import (
    INVERSION_PUBLICA_JSON,
    INVESTMENT_DIR,
    STATE_LOOKUP_NORM,
    strip_accents,
)

# ---------------------------------------------------------------------------
# Section headers (row labels that are sector subtotals, not institutions)
# Matched on an accent-stripped, upper-cased, dot-trimmed label.
# ---------------------------------------------------------------------------
_SECTION_MAP = {
    "TOTAL": "__grand_total__",
    "GOBIERNO FEDERAL": "gobierno_federal",
    "ORGANISMOS DESCENTRALIZADOS": "organismos_descentralizados",
    "EMPRESAS DE PARTICIPACION ESTATAL": "empresas_participacion_estatal",
}

_PARTE_WORDS = ("primera", "segunda", "tercera", "cuarta", "quinta", "sexta",
                "septima", "octava", "novena", "decima")


def _norm_label_key(label: str) -> str:
    return re.sub(r"\s+", " ", strip_accents(label).upper()).strip().rstrip(".").strip()


def classify_section(label: str):
    """Return the sector key if this row label is a section header, else None."""
    return _SECTION_MAP.get(_norm_label_key(label))


# ---------------------------------------------------------------------------
# State-name normalization: de-hyphenate line wraps, map to canonical config
# ---------------------------------------------------------------------------
def normalize_state(raw: str):
    if not raw:
        return None
    s = raw.replace("\n", " ")
    s = re.sub(r"-\s+", "", s)                 # 'Aguas- calientes' -> 'Aguascalientes'
    s = re.sub(r"\s+", " ", s).strip()
    key = strip_accents(s.lower()).replace(",", " ")
    key = re.sub(r"\s+", " ", key).strip()
    return STATE_LOOKUP_NORM.get(key)          # None if not a recognized state


# ---------------------------------------------------------------------------
# Numeric value cleaning (millones de pesos)
# ---------------------------------------------------------------------------
def parse_value(raw: str):
    """Return (value_float_or_None, flag)."""
    if raw is None:
        return None, "empty"
    v = raw.strip()
    # Drop Azure checkbox artifacts that sometimes trail a real value ("2.2 :selected:")
    v = re.sub(r":(?:un)?selected:", " ", v).strip()
    if v == "":
        return None, "empty"
    if v in ("-", "—", "–"):
        return 0.0, "dash_nil"
    orig = raw.strip()
    v = v.replace(":", ".").replace(",", "")   # 0:4 -> 0.4 ; thousands comma
    v = re.sub(r"(?<=\d)\s+(?=\d)", "", v)      # '1 419.6' -> '1419.6'
    v = v.strip().rstrip(".")                   # '2.3.' -> '2.3'
    try:
        return float(v), ("ok" if v == orig else "cleaned")
    except ValueError:
        return None, f"unparsed:{orig!r}"


# ---------------------------------------------------------------------------
# Load JSON and tag each table with (cuadro, year, parte, type) via offsets
# ---------------------------------------------------------------------------
def _table_grid(t: dict):
    rows, cols = t["rowCount"], t["columnCount"]
    g = [["" for _ in range(cols)] for _ in range(rows)]
    for c in t["cells"]:
        r, ci = c["rowIndex"], c["columnIndex"]
        if r < rows and ci < cols:
            g[r][ci] = (c.get("content") or "").replace("\n", " ").strip()
    return g


def _offset(obj: dict) -> int:
    spans = obj.get("spans") or [{}]
    return spans[0].get("offset", 10**18)


def build_context_events(paragraphs: list) -> list:
    """Ordered (offset, partial-context) events parsed from caption paragraphs."""
    events = []
    for p in paragraphs:
        c = " ".join((p.get("content") or "").split())
        cu = re.search(r"CUADRO\s+NUMERO\s+(\d+)", c, re.I)
        yr = re.search(r"\b(19\d{2})\b", c)
        up = strip_accents(c).upper()
        typ = ("institution" if "DEPENDENCIAS" in up
               else "destino" if "DESTINO DE LA INVERSION" in up else None)
        parte = None
        pm = re.search(r"\b(" + "|".join(_PARTE_WORDS) + r")\s+PARTE", up)
        if pm:
            parte = pm.group(1).lower()
        if cu or yr or typ or parte:
            events.append((_offset(p), {
                "cuadro": cu.group(1) if cu else None,
                "year": int(yr.group(1)) if yr else None,
                "type": typ,
                "parte": parte,
            }))
    events.sort(key=lambda e: e[0])
    return events


def context_at(offset: int, events: list) -> dict:
    """Fold all events up to `offset`, carrying forward the last non-null field."""
    ctx = {"cuadro": None, "year": None, "type": None, "parte": None}
    for off, ev in events:
        if off > offset:
            break
        for k, v in ev.items():
            if v is not None:
                # A new cuadro title resets the parte counter
                if k == "cuadro" and v != ctx["cuadro"]:
                    ctx["parte"] = None
                ctx[k] = v
    return ctx


# ---------------------------------------------------------------------------
# Main extraction
# ---------------------------------------------------------------------------
def extract(json_path: Path) -> pd.DataFrame:
    doc = json.load(open(json_path))
    ar = doc["analyzeResult"]
    tables, paragraphs = ar["tables"], ar.get("paragraphs", [])
    events = build_context_events(paragraphs)

    # Attach context + grid to each institution-matrix table
    inst_tables = []
    for t in tables:
        ctx = context_at(_offset(t), events)
        if ctx["type"] != "institution" or ctx["year"] is None:
            continue
        inst_tables.append((ctx, _offset(t), t))
    inst_tables.sort(key=lambda x: x[1])

    # Group the split section-tables belonging to the same (year, parte, states)
    groups: dict = {}
    for ctx, off, t in inst_tables:
        g = _table_grid(t)
        state_headers = tuple(g[0][1:])                # columns 1..n are states
        key = (ctx["year"], ctx["parte"], state_headers)
        groups.setdefault(key, []).append((off, ctx, g))

    records = []
    for (year, parte, state_headers), members in groups.items():
        members.sort(key=lambda m: m[0])
        # Precompute normalized state for each column once per group
        norm_states = [normalize_state(h) for h in state_headers]
        current_sector = None
        cuadro = members[0][1]["cuadro"]
        for _off, ctx, g in members:
            for r in range(1, len(g)):
                label = g[r][0].strip()
                if not label:
                    continue
                sec = classify_section(label)
                if sec == "__grand_total__":
                    row_type, sector, institution = "grand_total", None, None
                elif sec is not None:
                    current_sector = sec
                    row_type, sector, institution = "sector_subtotal", sec, None
                else:
                    row_type, sector, institution = "line_item", current_sector, label
                for ci, (state_raw, state) in enumerate(zip(state_headers, norm_states), start=1):
                    if state is None:
                        continue
                    value, flag = parse_value(g[r][ci])
                    if value is None and flag == "empty":
                        continue  # no investment reported
                    records.append({
                        "year": year, "cuadro": cuadro, "parte": parte,
                        "row_type": row_type, "sector": sector,
                        "institution": institution if institution else label,
                        "state": state, "state_raw": state_raw,
                        "investment_mdp": value, "value_raw": g[r][ci], "parse_flag": flag,
                    })

    df = pd.DataFrame.from_records(records)

    # Tidy institution text: join OCR line-wraps ('Tra- bajadores' -> 'Trabajadores',
    # 'Pu- blicas' -> 'Publicas'), collapse whitespace, trim trailing punctuation.
    inst = (df["institution"].astype(str)
            .str.replace(r"-\s+", "", regex=True)
            .str.replace(r"\s+", " ", regex=True)
            .str.strip().str.rstrip(". "))
    df["institution"] = inst
    # Canonicalize spelling variants (accents / casing) to one display name per
    # accent-stripped key — merges 'Mexico'/'Mexico', etc.
    key = inst.map(lambda s: re.sub(r"[^a-z0-9]+", " ", strip_accents(s).lower()).strip())
    df["institution_key"] = key
    canon = (df[df["row_type"] == "line_item"]
             .groupby("institution_key")["institution"]
             .agg(lambda s: s.value_counts().idxmax()))
    df.loc[df["row_type"] == "line_item", "institution"] = key[df["row_type"] == "line_item"].map(canon)

    return df.sort_values(["year", "sector", "institution", "state"]).reset_index(drop=True)


def write_outputs(df: pd.DataFrame) -> None:
    INVESTMENT_DIR.mkdir(parents=True, exist_ok=True)

    long_path = INVESTMENT_DIR / "federal_investment_long.csv"
    df.to_csv(long_path, index=False)

    # Institution catalog: line items only (drop subtotal / grand-total rows)
    items = df[df["row_type"] == "line_item"].copy()
    catalog = (items.groupby(["sector", "institution"])
               .agg(n_records=("year", "size"),
                    years=("year", lambda s: "|".join(map(str, sorted(set(s))))),
                    n_years=("year", "nunique"),
                    total_mdp=("investment_mdp", "sum"))
               .reset_index()
               .sort_values(["sector", "total_mdp"], ascending=[True, False]))
    cat_path = INVESTMENT_DIR / "federal_investment_institutions.csv"
    catalog.to_csv(cat_path, index=False)

    # Per-year wide pivots (institution x state)
    for year, sub in items.groupby("year"):
        wide = sub.pivot_table(index=["sector", "institution"], columns="state",
                               values="investment_mdp", aggfunc="sum")
        wide.to_csv(INVESTMENT_DIR / f"federal_investment_wide_{year}.csv")

    # Validation: per (year, state) compare grand total vs sum of sector subtotals
    # vs sum of line items.
    def _tot(mask):
        return (df[mask].groupby(["year", "state"])["investment_mdp"].sum())
    grand = _tot(df["row_type"] == "grand_total").rename("grand_total")
    subs = _tot(df["row_type"] == "sector_subtotal").rename("sum_sector_subtotals")
    lines = _tot(df["row_type"] == "line_item").rename("sum_line_items")
    val = pd.concat([grand, subs, lines], axis=1).reset_index()
    val["diff_subtotals_vs_grand"] = (val["sum_sector_subtotals"] - val["grand_total"]).round(2)
    val["diff_lines_vs_subtotals"] = (val["sum_line_items"] - val["sum_sector_subtotals"]).round(2)
    val_path = INVESTMENT_DIR / "federal_investment_validation.csv"
    val.to_csv(val_path, index=False)

    # Console report
    print(f"Long table:      {len(df):5d} rows  -> {long_path.name}")
    print(f"  line items:    {(df['row_type']=='line_item').sum()}")
    print(f"  subtotals:     {(df['row_type']=='sector_subtotal').sum()}")
    print(f"  grand totals:  {(df['row_type']=='grand_total').sum()}")
    print(f"Years:           {sorted(df['year'].unique())}")
    print(f"Institutions:    {catalog['institution'].nunique()} distinct -> {cat_path.name}")
    print(f"  by sector:     {items.groupby('sector')['institution'].nunique().to_dict()}")
    bad = df[df["parse_flag"].str.startswith("unparsed")]
    print(f"Unparsed values: {len(bad)}"
          + (f"  e.g. {bad['value_raw'].head(5).tolist()}" if len(bad) else ""))
    within = (val["diff_subtotals_vs_grand"].abs() <= 0.2).mean()
    print(f"Validation:      {within:.0%} of (year,state) have sector subtotals "
          f"matching the grand total (±0.2 mdp) -> {val_path.name}")


def main() -> None:
    if not INVERSION_PUBLICA_JSON.exists():
        raise SystemExit(f"Missing source JSON: {INVERSION_PUBLICA_JSON}")
    df = extract(INVERSION_PUBLICA_JSON)
    write_outputs(df)


if __name__ == "__main__":
    main()
