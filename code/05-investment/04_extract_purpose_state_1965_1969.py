"""Extract realized federal investment by purpose and state, 1965--1969.

Source: ``federal_investment_1965_1970-73-128.pdf.json`` (Azure Document
Intelligence layout output), cuadros 18--23:

* cuadro 18: realized investment for the full 1965--1969 period;
* cuadros 19--23: realized investment for each year 1965--1969.

Cuadro 17 contains the same period totals transposed and is intentionally not
used.  Programmed-investment cuadros 1--15 are national tables rather than the
requested realized state matrices.  The source has no realized 1970-by-state
matrix.
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

from config import (  # noqa: E402
    INVESTMENT_DIR,
    INVERSION_PUBLICA_1965_1970_JSON,
    STATE_LOOKUP_NORM,
    strip_accents,
)

TARGET_CUADROS = {
    18: None,  # aggregate, 1965--1969
    19: 1965,
    20: 1966,
    21: 1967,
    22: 1968,
    23: 1969,
}

LABEL_FIXES = {
    "EQUIPOS E INSTALACIONES PARA ADMINITSRACION Y DEFENSA":
        "EQUIPOS E INSTALACIONES PARA ADMINISTRACION Y DEFENSA",
    "TRSNAPORTES Y COMUNICACIONES": "TRANSPORTES Y COMUNICACIONES",
    "Comunicaciones aereas": "Comunicaciones aéreas",
    "Electricidad. %": "Electricidad",
    "Osras lúyerslónes": "Otras inversiones",
}

# These three category totals have an extra OCR'd 5 in the tens place.  In each
# case the printed grand total and the sum of the category's detail rows agree
# on the corrected value.  Preserve the source string in value_raw.
VALUE_FIXES = {
    (18, None, "Obras de servicio urbano y rural", "12 350.7"): 9350.7,
    (18, "Federal District", "Obras de servicio urbano y rural", "9 872.1"): 6872.1,
    (19, "Mexico", "TRANSPORTES Y COMUNICACIONES", "184.4"): 134.4,
    (20, "Nuevo Leon", "TRANSPORTES Y COMUNICACIONES", "81.6"): 31.6,
    (22, "Coahuila", "TRANSPORTES Y COMUNICACIONES", "180.1"): 130.1,
    (23, None, "Obras de servicio urbano y rural", "4 096.6"): 1096.6,
}


def _offset(obj: dict) -> int:
    return (obj.get("spans") or [{}])[0].get("offset", 10**18)


def _grid(table: dict) -> list[list[str]]:
    grid = [[""] * table["columnCount"] for _ in range(table["rowCount"])]
    for cell in table["cells"]:
        grid[cell["rowIndex"]][cell["columnIndex"]] = " ".join(
            (cell.get("content") or "").split()
        )
    return grid


def _clean_text(raw: str) -> str:
    text = re.sub(r":(?:un)?selected:", " ", raw, flags=re.I)
    text = re.sub(r"-\s+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.rstrip(". ")


def normalize_state(raw: str) -> tuple[str | None, str]:
    clean = _clean_text(raw)
    key = strip_accents(clean.lower()).replace(",", " ")
    key = re.sub(r"\s+", " ", key).strip()
    if key in {"total", "total nacional"}:
        return None, "national"
    return STATE_LOOKUP_NORM.get(key), "state"


def parse_value(raw: str) -> tuple[float | None, str]:
    """Parse OCR'd millions of pesos while retaining an audit flag."""
    original = raw.strip()
    value = re.sub(r":(?:un)?selected:", " ", original, flags=re.I).strip()
    if not value:
        # Azure uses both an empty cell and an unselected checkbox for printed nil.
        return 0.0, "blank_nil"
    if value in {"-", "—", "–"}:
        return 0.0, "dash_nil"
    value = re.sub(r"^[^0-9.,:-]+", "", value)
    # Duplicate leading decimal mark in two cells: .727.9 and .99:8.
    value = re.sub(r"^\.(?=\d+[.:]\d$)", "", value)
    value = value.rstrip(".")
    value = re.sub(r"(?<=\d)\s+(?=\d)", "", value)
    value = value.replace(":", ".")
    # A lone comma followed by one digit is an OCR'd decimal comma (e.g. 74,5).
    if re.fullmatch(r"-?\d+,\d", value):
        value = value.replace(",", ".")
    else:
        value = value.replace(",", "")
    try:
        parsed = float(value)
    except ValueError:
        return None, f"unparsed:{original!r}"
    return parsed, "ok" if value == original else "cleaned"


def caption_intervals(paragraphs: list[dict]) -> list[tuple[int, int, int | None]]:
    """Return intervals for every caption, including Roman-numbered 1964 tables."""
    captions: list[tuple[int, int | None]] = []
    for paragraph in paragraphs:
        content = " ".join((paragraph.get("content") or "").split())
        if not re.match(r"^CUADRO\b", content, flags=re.I):
            continue
        match = re.match(r"^CUADRO[\s,]+(\d+)\b", content, flags=re.I)
        captions.append((_offset(paragraph), int(match.group(1)) if match else None))
    captions.sort()
    return [
        (offset, captions[i + 1][0] if i + 1 < len(captions) else 10**18, cuadro)
        for i, (offset, cuadro) in enumerate(captions)
    ]


def extract(json_path: Path) -> pd.DataFrame:
    with json_path.open(encoding="utf-8") as source:
        result = json.load(source)["analyzeResult"]

    intervals = caption_intervals(result.get("paragraphs", []))
    records: list[dict] = []
    for table in result["tables"]:
        offset = _offset(table)
        cuadro = next(
            (number for start, end, number in intervals if start <= offset < end),
            None,
        )
        if cuadro not in TARGET_CUADROS:
            continue
        grid = _grid(table)
        if not grid or _clean_text(grid[0][0]).upper() != "CONCEPTO":
            continue

        headers = grid[0][1:]
        geographies = [normalize_state(header) for header in headers]
        if any(kind == "state" and state is None for state, kind in geographies):
            bad = [h for h, (s, k) in zip(headers, geographies) if k == "state" and s is None]
            raise ValueError(f"Unrecognized state headers in cuadro {cuadro}: {bad}")

        current_parent = None
        for row in grid[1:]:
            category = _clean_text(row[0])
            if not category:
                continue
            category = LABEL_FIXES.get(category, category)
            key = strip_accents(category).upper()
            if key == "TOTAL":
                row_type = "grand_total"
                parent = None
            elif category == category.upper():
                row_type = "category_total"
                current_parent = category.title()
                parent = current_parent
            else:
                row_type = "subcategory"
                parent = current_parent

            for raw_header, (state, geography_type), raw_value in zip(
                headers, geographies, row[1:]
            ):
                value, flag = parse_value(raw_value)
                fix_key = (cuadro, state, category, raw_value.strip())
                if fix_key in VALUE_FIXES:
                    value, flag = VALUE_FIXES[fix_key], "corrected_reconciled_ocr"
                records.append(
                    {
                        "year": TARGET_CUADROS[cuadro],
                        "period_start": 1965,
                        "period_end": 1969 if cuadro == 18 else TARGET_CUADROS[cuadro],
                        "cuadro": cuadro,
                        "geography_type": geography_type,
                        "state": state,
                        "state_raw": raw_header,
                        "row_type": row_type,
                        "parent_category": parent,
                        "category": category,
                        "investment_mdp": value,
                        "value_raw": raw_value,
                        "parse_flag": flag,
                    }
                )

    frame = pd.DataFrame.from_records(records)
    if frame.empty:
        raise ValueError("No purpose-by-state tables were extracted")
    return frame.sort_values(
        ["period_end", "cuadro", "row_type", "parent_category", "category", "geography_type", "state"],
        na_position="first",
    ).reset_index(drop=True)


def build_validation(frame: pd.DataFrame) -> pd.DataFrame:
    checks: list[dict] = []
    for (cuadro, year, category), group in frame.groupby(
        ["cuadro", "year", "category"], dropna=False
    ):
        national = group.loc[group["geography_type"] == "national", "investment_mdp"].sum()
        states = group.loc[group["geography_type"] == "state", "investment_mdp"].sum()
        checks.append(
            {
                "check": "states_vs_national",
                "cuadro": cuadro,
                "year": year,
                "geography": "All states",
                "category": category,
                "reported_total": national,
                "component_sum": states,
                "difference": round(states - national, 2),
            }
        )

    totals = frame[frame["row_type"] == "grand_total"].copy()
    majors = frame[frame["row_type"] == "category_total"].copy()
    # A sentinel makes the aggregate period's null year safe to merge/group.
    totals["year_key"] = totals["year"].fillna(0).astype(int)
    majors["year_key"] = majors["year"].fillna(0).astype(int)
    lookup_keys = ["cuadro", "year_key", "geography_type", "state"]
    major_sums = majors.groupby(lookup_keys, dropna=False)["investment_mdp"].sum()
    for row in totals.itertuples(index=False):
        key = (row.cuadro, row.year_key, row.geography_type, row.state)
        component_sum = major_sums.get(key, float("nan"))
        checks.append(
            {
                "check": "categories_vs_total",
                "cuadro": row.cuadro,
                "year": row.year,
                "geography": row.state if row.state else "National total",
                "category": "TOTAL",
                "reported_total": row.investment_mdp,
                "component_sum": component_sum,
                "difference": round(component_sum - row.investment_mdp, 2),
            }
        )

    # Cuadro 18 should equal the sum of annual cuadros 19--23.
    dimensions = ["geography_type", "state", "row_type", "parent_category", "category"]
    aggregate = (frame[frame["cuadro"] == 18]
                 .groupby(dimensions, dropna=False)["investment_mdp"].sum())
    annual = (frame[frame["cuadro"].isin([19, 20, 21, 22, 23])]
              .groupby(dimensions, dropna=False)["investment_mdp"].sum())
    comparison = pd.concat(
        [aggregate.rename("reported_total"), annual.rename("component_sum")], axis=1
    ).reset_index()
    comparison["difference"] = (
        comparison["component_sum"] - comparison["reported_total"]
    ).round(2)
    for row in comparison.itertuples(index=False):
        checks.append(
            {
                "check": "annual_sum_vs_1965_1969",
                "cuadro": 18,
                "year": None,
                "geography": row.state if row.state else "National total",
                "category": row.category,
                "reported_total": row.reported_total,
                "component_sum": row.component_sum,
                "difference": row.difference,
            }
        )
    return pd.DataFrame(checks)


def write_outputs(frame: pd.DataFrame) -> None:
    INVESTMENT_DIR.mkdir(parents=True, exist_ok=True)
    long_path = INVESTMENT_DIR / "federal_investment_purpose_state_long.csv"
    frame.to_csv(long_path, index=False)

    for cuadro, group in frame.groupby("cuadro"):
        label = "1965_1969" if cuadro == 18 else str(int(group["year"].iloc[0]))
        wide_source = group.copy()
        wide_source["parent_category"] = wide_source["parent_category"].fillna("")
        wide_source["geography"] = wide_source["state"].fillna("National total")
        wide = wide_source.pivot_table(
            index=["row_type", "parent_category", "category"],
            columns="geography",
            values="investment_mdp",
            aggfunc="first",
        )
        wide.to_csv(INVESTMENT_DIR / f"federal_investment_purpose_state_wide_{label}.csv")

    validation = build_validation(frame)
    validation_path = INVESTMENT_DIR / "federal_investment_purpose_state_validation.csv"
    validation.to_csv(validation_path, index=False)

    print(f"Long table: {len(frame):,} rows -> {long_path}")
    print(f"Cuadros: {sorted(frame['cuadro'].unique())}")
    print(f"Annual years: {sorted(frame['year'].dropna().astype(int).unique())}")
    print(f"States: {frame.loc[frame['geography_type'] == 'state', 'state'].nunique()}")
    print(f"Categories: {frame['category'].nunique()}")
    unparsed = frame[frame["parse_flag"].str.startswith("unparsed")]
    print(f"Unparsed values: {len(unparsed)}")
    category_checks = validation[validation["check"] == "categories_vs_total"]
    exact = category_checks["difference"].abs().le(0.2).mean()
    print(f"Category totals reconcile within 0.2 mdp: {exact:.1%}")
    print(f"Validation -> {validation_path}")


def main() -> None:
    if not INVERSION_PUBLICA_1965_1970_JSON.exists():
        raise SystemExit(f"Missing source JSON: {INVERSION_PUBLICA_1965_1970_JSON}")
    write_outputs(extract(INVERSION_PUBLICA_1965_1970_JSON))


if __name__ == "__main__":
    main()
