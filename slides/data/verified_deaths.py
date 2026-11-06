"""Verified death years for the eligibility rule of the main design.

estimate_main.R drops from every succession's pool the politicians whose verified death year is earlier than the
designation calendar year (death_year < election_year - 1): a politician who had died before the designation could
not be treated. Only deaths verified in two places are used: the year in data/structural/death_years.csv
(slides/data/death_years.py: Camp's "(Deceased <date>)" header, presidents from Wikidata) must also appear in the
"(deceased ...)" header of the biography matched by name in biographies_corrected.csv. Nothing is imputed; a death
year that cannot be verified leaves the politician in the pool.

Input:  TAPADOSPRI_DATA_DIR/structural/death_years.csv, TAPADOSPRI_DATA_DIR/biographies_corrected.csv
Output: TAPADOSPRI_DATA_DIR/verified_death_years.csv (person_id, name, death_year, biography_header,
        verified_by_name_and_header) and TAPADOSPRI_OUTPUT_DIR/slides/analysis/unresolved_death_header_matches.csv
        (the records whose header could not be matched; they are not used).
Run:    python3 slides/data/verified_deaths.py
"""
import os
import re
import unicodedata
from pathlib import Path

import pandas as pd

db_root = Path(os.environ.get("TAPADOSPRI_DB_ROOT", Path.home() / "Dropbox" / "TapadosPRI"))
data_dir = Path(os.environ.get("TAPADOSPRI_DATA_DIR", db_root / "data"))
out_dir = Path(os.environ.get("TAPADOS_MAIN_OUTPUT_DIR", Path(os.environ.get("TAPADOSPRI_OUTPUT_DIR", db_root / "output")) / "slides" / "analysis"))
out_dir.mkdir(parents=True, exist_ok=True)


def tokens(value):
    """Lower-case ASCII word set of a name, without the Spanish connectors."""
    value = unicodedata.normalize("NFKD", str(value))
    value = "".join(c for c in value if not unicodedata.combining(c)).lower()
    return set(re.findall("[a-z]+", value)) - {"y", "de", "del", "la"}


deaths = pd.read_csv(data_dir / "structural" / "death_years.csv")
biographies = pd.read_csv(data_dir / "biographies_corrected.csv", low_memory=False)
headers = biographies.name.fillna("").drop_duplicates()
header_names = headers.map(lambda h: tokens(re.split(r"\(deceased", h, flags=re.I)[0]))
verified, unresolved = [], []
for row in deaths.itertuples():
    name = tokens(row.name)
    matches = headers[header_names.map(lambda x: name <= x)]          # every header containing the name's words
    exact = matches[header_names.loc[matches.index].map(lambda x: x == name)]
    if len(exact) == 1:
        matches = exact
    if len(matches) == 1:
        header = matches.iloc[0]
        match = re.search(r"deceased[\s,]+([^)]*)", header, re.I)
        if match and str(int(row.death_year)) in match.group(1):      # the year must be printed in the header
            verified.append(dict(person_id=row.person_id, name=row.name, death_year=int(row.death_year),
                                 biography_header=header, verified_by_name_and_header=True))
            continue
    unresolved.append(dict(person_id=row.person_id, name=row.name, death_year=row.death_year))
out = pd.DataFrame(verified)
assert out.person_id.is_unique
out.to_csv(data_dir / "verified_death_years.csv", index=False)
pd.DataFrame(unresolved, columns=["person_id", "name", "death_year"]).to_csv(out_dir / "unresolved_death_header_matches.csv", index=False)
print(f"verified death years: {len(out)} of {len(deaths)} records ({len(unresolved)} unresolved, not used) -> {data_dir / 'verified_death_years.csv'}")
