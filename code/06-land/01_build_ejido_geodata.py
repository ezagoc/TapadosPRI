"""
Build the clean ejido geodata base from the RAN/PROCEDE shapefiles (cut 31 Dec 2006).

Source: RAN / PROCEDE, "Distribución de la propiedad social en México" (state layers 2001-2007). The raw
shapefiles were shared with us by Horacio Larreguy (ITAM); they are not in the project Dropbox.

Input (outside the project Dropbox, path in config.RAN_SHAPEFILES_DIR):
  nacional/nacional.shp      57,229 polygons of 32,053 nucleos agrarios (ejidos and comunidades),
                             several polygons per nucleo; PROCEDE certification attributes and dates
  <State>/p<state>.shp       INEGI 2000 census localities (points) that fall inside a nucleo,
                             with the nucleo keys attached (one file per state, 32 files)

Output (config.LAND_REFORM_DIR):
  ejidos_procede_2006.gpkg               layer "nucleos":    one multipolygon per nucleo agrario (EPSG:4326)
                                         layer "localities": census-2000 localities inside nucleos (points)
  ejidos_procede_2006_attributes.csv     nucleo attributes without geometry (includes the 1,556 nucleos without polygon)
  localities_2000_in_ejidos.csv          locality -> nucleo crosswalk (INEGI state/municipality/locality keys)
  README.md                              sources, variables, caveats

Run:  python3 code/06-land/01_build_ejido_geodata.py
"""
import sys
import warnings
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio
from shapely.validation import make_valid

CODE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CODE_DIR))
from config import RAN_SHAPEFILES_DIR, LAND_REFORM_DIR, EJIDOS_GPKG  # noqa: E402

warnings.filterwarnings("ignore")

STATE_NAMES = {
    "01": "Aguascalientes", "02": "Baja California", "03": "Baja California Sur", "04": "Campeche",
    "05": "Coahuila", "06": "Colima", "07": "Chiapas", "08": "Chihuahua", "09": "Distrito Federal",
    "10": "Durango", "11": "Guanajuato", "12": "Guerrero", "13": "Hidalgo", "14": "Jalisco",
    "15": "Mexico", "16": "Michoacan", "17": "Morelos", "18": "Nayarit", "19": "Nuevo Leon",
    "20": "Oaxaca", "21": "Puebla", "22": "Queretaro", "23": "Quintana Roo", "24": "San Luis Potosi",
    "25": "Sinaloa", "26": "Sonora", "27": "Tabasco", "28": "Tamaulipas", "29": "Tlaxcala",
    "30": "Veracruz", "31": "Yucatan", "32": "Zacatecas",
}

# raw column -> clean name (nucleo attributes; constant within a nucleo)
NUCLEO_COLS = {
    "CVEIN_CON": "nucleo_key",          # state + municipality + ejido codes (INEGI-style), unique per nucleo
    "CLAVEUNICA": "ran_claveunica",     # RAN unique key (16 chars)
    "CVE_EDO": "state_code",
    "CVE_MPIO": "mun_code",
    "CVE_EJIDO": "ejido_code",
    "NOM_NA": "nucleo_name",
    "NOM_MUN": "mun_name",
    "TPO_PO": "nucleo_type",            # E = ejido, C = comunidad agraria
    "TIPO_NA": "tipo_na",               # RAN internal type code (I/E/C/O), kept as is
    # The next fields come from PROCEDE's "General" and "Medición" tables; the source carries no labels.
    # GENERAL10 sums to the RAN national surface (101.59 M ha, = resumen.DBF), MEDICION13 to 93.7 M ha.
    "GENERAL10": "surface_registered_ha",   # surface on the RAN register (ha)
    "MEDICION13": "surface_measured_ha",    # surface measured by PROCEDE (ha)
    "GENERAL06": "n_general06",             # probably ejidatarios/comuneros with rights (= MEDICION5 in 93%)
    "GENERAL07": "n_general07",             # probably posesionarios (= MEDICION6 in 91%)
    "GENERAL01": "n_general01",             # probably avecindados
    "GENERAL08": "n_general08",             # small count (mean 1.6, max 70): probably annexes/polygons
    "DIAG": "date_diagnosis",           # PROCEDE diagnosis
    "MEDINI": "date_survey_start",
    "CERTI": "date_certified",          # certificates delivered
    "REGULA": "date_regularized",
    "MEDIDO": "measured",
    "ETAPA": "stage",
    "SEMAFORO": "semaforo",
}


def load_nucleos() -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    src = RAN_SHAPEFILES_DIR / "nacional" / "nacional.shp"
    print(f"reading {src}")
    g = gpd.read_file(src)
    g = g.rename(columns=NUCLEO_COLS)
    keep = list(NUCLEO_COLS.values())
    g["has_polygon"] = g.geometry.notna().astype(int)
    for c in ["date_diagnosis", "date_survey_start", "date_certified", "date_regularized"]:
        g[c] = pd.to_datetime(g[c], errors="coerce")
        g.loc[g[c] < "1990-01-01", c] = pd.NaT          # 1899-12-30 is the dBase null
    for c in ["surface_registered_ha", "surface_measured_ha", "n_general06", "n_general07", "n_general01", "n_general08"]:
        g[c] = pd.to_numeric(g[c], errors="coerce")
    g["state_name"] = g["state_code"].map(STATE_NAMES)

    # attributes: one row per nucleo (first non-null per column)
    attrs = (g[keep + ["state_name", "has_polygon"]]
             .groupby("nucleo_key", as_index=False).first())
    npoly = g[g.has_polygon == 1].groupby("nucleo_key").size().rename("n_polygons")
    attrs = attrs.merge(npoly, on="nucleo_key", how="left")
    attrs["n_polygons"] = attrs["n_polygons"].fillna(0).astype(int)

    # geometry: repair, then dissolve to one multipolygon per nucleo (area in the source LCC projection)
    gp = g[g.has_polygon == 1][["nucleo_key", "geometry"]].copy()
    bad = ~gp.geometry.is_valid
    print(f"  polygons {len(gp)}, invalid {int(bad.sum())} -> make_valid")
    gp.loc[bad, "geometry"] = gp.loc[bad, "geometry"].apply(make_valid)
    diss = gp.dissolve(by="nucleo_key", as_index=False)
    diss["area_ha"] = diss.geometry.area / 1e4
    attrs = attrs.merge(diss[["nucleo_key", "area_ha"]], on="nucleo_key", how="left")
    nuc = diss[["nucleo_key", "geometry"]].merge(attrs, on="nucleo_key", how="left")
    nuc = gpd.GeoDataFrame(nuc, geometry="geometry", crs=g.crs).to_crs(4326)
    print(f"  nucleos: {len(attrs)} ({int(attrs.has_polygon.sum())} with polygon)")
    return nuc, attrs


def load_localities(crs) -> gpd.GeoDataFrame:
    """Union of the 32 state locality files (INEGI 2000 census points inside nucleos). Column names differ
    slightly by state (Chiapas: CVE_MUN/CVE_LOC; Baja California Sur: no CLAVEUNICA), so each field is
    looked up from a list of candidates."""
    CANDS = {
        "state_code": ["ENT", "CVE_ESTADO"], "mun_code": ["MUN", "CVE_MUN"], "mun_name": ["NOMMUN", "NOM_MUN"],
        "loc_code": ["LOC", "CVE_LOC"], "loc_name": ["NOMLOC"], "pop_2000": ["POBTOT"],
        "nucleo_key": ["CVEIN_CON"], "ran_claveunica": ["CLAVEUNICA"],
    }
    files = sorted(RAN_SHAPEFILES_DIR.glob("*/p*.shp"))
    files = [f for f in files if f.stem.lower().startswith("p") and f.stem.lower() != "puebla"]
    parts = []
    for f in files:
        d = pyogrio.read_dataframe(f)
        up = {c.upper(): c for c in d.columns}
        out = {}
        for k, cands in CANDS.items():
            hit = next((up[c] for c in cands if c in up), None)
            out[k] = d[hit] if hit else pd.Series([None] * len(d))
        if out["nucleo_key"].isna().all():
            print(f"  skip {f.name}: no CVEIN_CON")
            continue
        dd = gpd.GeoDataFrame(pd.DataFrame(out), geometry=d.geometry, crs=d.crs or crs)
        parts.append(dd.to_crs(4326))
    loc = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), geometry="geometry", crs=4326)
    loc["state_code"] = loc["state_code"].astype(str).str.zfill(2)
    loc["mun_code"] = loc["mun_code"].astype(str).str.zfill(3)
    loc["loc_code"] = loc["loc_code"].astype(str).str.zfill(4)
    loc["inegi_locality_key"] = loc.state_code + loc.mun_code + loc.loc_code
    loc["pop_2000"] = pd.to_numeric(loc["pop_2000"], errors="coerce")   # '*' = confidential (<3 dwellings)
    loc["lon"] = loc.geometry.x
    loc["lat"] = loc.geometry.y
    print(f"  localities: {len(loc)} from {len(parts)} state files")
    return loc


README = """# Ejido geodata (RAN/PROCEDE, cut 31 December 2006)

Built by `code/06-land/01_build_ejido_geodata.py` from the RAN shapefiles "Distribución de la propiedad
social en México" (Registro Agrario Nacional / PROCEDE, data cut 31 Dec 2006; state layers dated 2001–2007),
shared with us by Horacio Larreguy (ITAM). The raw files are not in this Dropbox (path in
`config.RAN_SHAPEFILES_DIR`). Confirm with Larreguy the citation he wants before publishing anything built on this.

## Files
- `ejidos_procede_2006.gpkg` (EPSG:4326)
  - layer `nucleos`: one multipolygon per núcleo agrario (ejido or comunidad) with a polygon in the source
    (several source polygons per núcleo were dissolved; invalid rings repaired with `make_valid`).
  - layer `localities`: INEGI 2000 census localities located inside a núcleo (points), with the núcleo keys.
- `ejidos_procede_2006_attributes.csv`: all núcleos (including those without polygon, `has_polygon = 0`).
- `localities_2000_in_ejidos.csv`: the locality layer without geometry (lon/lat columns instead).

## Variables (nucleos)
`nucleo_key` (state + municipality + ejido code, unique), `ran_claveunica` (RAN 16-char key), `state_code`,
`state_name`, `mun_code`, `mun_name`, `ejido_code`, `nucleo_name`, `nucleo_type` (E ejido / C comunidad),
`tipo_na` (RAN internal code), `surface_registered_ha` (RAN register; sums to the national 101.59 M ha),
`surface_measured_ha` (PROCEDE measurement), `n_general06` / `n_general07` / `n_general01` / `n_general08`
(counts from PROCEDE's "General" table, unlabelled in the source; most likely ejidatarios-comuneros,
posesionarios, avecindados and annexes respectively, so treat the labels as provisional), `date_diagnosis`, `date_survey_start`, `date_certified`,
`date_regularized` (PROCEDE process dates, 1992–2006), `measured`, `stage`, `semaforo`, `has_polygon`,
`n_polygons` (source polygons dissolved), `area_ha` (computed from the geometry in the source Lambert
conformal conic projection).

## What it is and is not
- It is the map of social property as certified by PROCEDE (1993–2006): boundaries, names, keys, surfaces,
  beneficiaries. The Distrito Federal is absent from the source.
- It does NOT contain the original land-reform history (date of the presidential resolution of dotación /
  ampliación, hectares granted, signing president). Those come from Sanderson (1916–1976, village level, in
  `_web_discovery_2026-10-13/garfias_2018_apsr_state_capacity`), the Diario Oficial API (1977–1992) and, when
  accessible, RAN's PHINA. Link them to these polygons by `nucleo_name` + `mun_code` (and through the
  locality crosswalk, whose INEGI keys match Sanderson's `clave` within `municipio` where that coding was used).
- Census values `*` (confidential, fewer than 3 dwellings) are NaN in `pop_2000`.
"""


def main() -> None:
    LAND_REFORM_DIR.mkdir(parents=True, exist_ok=True)
    nuc, attrs = load_nucleos()
    loc = load_localities(crs=nuc.crs)
    if EJIDOS_GPKG.exists():
        EJIDOS_GPKG.unlink()
    nuc.to_file(EJIDOS_GPKG, layer="nucleos", driver="GPKG")
    loc.to_file(EJIDOS_GPKG, layer="localities", driver="GPKG")
    attrs.to_csv(LAND_REFORM_DIR / "ejidos_procede_2006_attributes.csv", index=False)
    loc.drop(columns="geometry").to_csv(LAND_REFORM_DIR / "localities_2000_in_ejidos.csv", index=False)
    (LAND_REFORM_DIR / "README.md").write_text(README)
    print("written", EJIDOS_GPKG)
    print(attrs.nucleo_type.value_counts(dropna=False).to_dict())
    print("surface_registered_ha total (M ha):", round(attrs.surface_registered_ha.sum() / 1e6, 2),
          "| area_ha from geometry (M ha):", round(attrs.area_ha.sum() / 1e6, 2),
          "| n_general06 (rightholders?):", int(attrs.n_general06.sum()))


if __name__ == "__main__":
    main()
