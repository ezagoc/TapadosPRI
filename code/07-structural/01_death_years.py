"""Death years and the presidential timeline for the structural model (MODEL_SPEC sections 2 and 4).

Camp's entries carry "(Deceased <date>)" in the name; 04_parse_positions.clean_name_col parses it but does not save it.
Presidents' death dates come from Wikidata (needed for the ex-president chair), checked against Camp where both exist.
The presidential timeline is written from the constitutional terms, not from position records: Alemán (1946-52) has no
"president" record in rank/position_tiers.csv.
Outputs: DATA_DIR/structural/death_years.csv (person_id, name, death_year, source) and presidents.csv (person_id, name,
term_start, term_end, death_year; the term runs from 1 December of term_start to 1 December of term_end).
Run: python code/07-structural/01_death_years.py
"""
import importlib.util
import sys
from pathlib import Path

import pandas as pd

CODE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE_DIR))
from config import DATA_DIR  # noqa: E402

OUT = DATA_DIR / "structural"
OUT.mkdir(exist_ok=True)

spec = importlib.util.spec_from_file_location("p04", CODE_DIR / "00-networks" / "00-preprocess" / "04_parse_positions.py")
p04 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p04)

bios = pd.read_csv(DATA_DIR / "biographies_corrected.csv")
info = bios["name"].map(p04.clean_name_col)
camp = pd.DataFrame({"name": info.map(lambda x: x["name_clean"]), "death_year": info.map(lambda x: x["death_year"])})
camp = camp.dropna(subset=["death_year"]).drop_duplicates("name")

nodes = pd.read_csv(DATA_DIR / "networks" / "network_nodes.csv")[["person_id", "name"]]
out = nodes.merge(camp, on="name", how="inner").assign(source="camp")

# Presidents 1928-2000: constitutional terms (1 December to 1 December) and death years from Wikidata (Calles and Ortiz
# Rubio have no entry in the 1935-2009 volume, so no ties; de la Madrid, Salinas and Zedillo were alive through 1996).
PRESIDENTS = [  # (Wikidata label, network name, term_start, term_end)
    ("Emilio Portes Gil", "Portes Gil, Emilio", 1928, 1930),
    ("Abelardo L. Rodríguez", "Rodriguez Lujan, Abelardo L", 1932, 1934),
    ("Lázaro Cárdenas", "Cardenas del Rio, Lazaro", 1934, 1940),
    ("Manuel Ávila Camacho", "Avila Camacho, Manuel", 1940, 1946),
    ("Miguel Alemán Valdés", "Aleman Valdes, Miguel", 1946, 1952),
    ("Adolfo Ruiz Cortines", "Ruiz Cortines, Adolfo", 1952, 1958),
    ("Adolfo López Mateos", "Lopez Mateos, Adolfo", 1958, 1964),
    ("Gustavo Díaz Ordaz", "Diaz Ordaz, Gustavo", 1964, 1970),
    ("Luis Echeverría", "Echeverria Alvarez, Luis", 1970, 1976),
    ("José López Portillo", "Lopez Portillo Pacheco, Jose", 1976, 1982),
    (None, "de la Madrid Hurtado, Miguel", 1982, 1988),
    (None, "Salinas de Gortari, Carlos", 1988, 1994),
    (None, "Zedillo Ponce de Leon, Ernesto", 1994, 2000),
]
wd = pd.read_csv(DATA_DIR / "_web_discovery_2026-10-13" / "wikidata_mexico_officeholders" / "wd_mexican_politicians_born_1860_1974.csv")
rows = []
for label, net_name, t0, t1 in PRESIDENTS:
    pid = nodes.loc[nodes.name == net_name, "person_id"]
    assert len(pid) == 1, f"{net_name} not found once in network_nodes"
    death = None
    if label is not None:
        r = wd[wd.personLabel == label]
        assert len(r) and pd.notna(r.death.iloc[0]), f"no Wikidata death date for {label}"
        death = int(str(r.death.iloc[0])[:4])
    rows.append({"person_id": int(pid.iloc[0]), "name": net_name, "term_start": t0, "term_end": t1, "death_year": death})
presidents = pd.DataFrame(rows)
presidents.to_csv(OUT / "presidents.csv", index=False)
pres = presidents.dropna(subset=["death_year"])[["person_id", "name", "death_year"]].assign(source="wikidata")
both = pres.merge(out, on="person_id", suffixes=("_wd", "_camp"))
bad = both[both.death_year_wd != both.death_year_camp]
assert bad.empty, f"Camp and Wikidata disagree for presidents:\n{bad}"
out = pd.concat([out[~out.person_id.isin(pres.person_id)], pres], ignore_index=True).sort_values("person_id")
out["death_year"] = out["death_year"].astype(int)
out.to_csv(OUT / "death_years.csv", index=False)
print(f"death years: {len(out)} politicians ({(out.source == 'camp').sum()} from Camp, {(out.source == 'wikidata').sum()} presidents from Wikidata)")
print(presidents.to_string(index=False))
