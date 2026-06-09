# TapadosPRI — Project Context for Claude

## What this project is

Political network analysis of the "tapado" system in Mexico's PRI party (1921–2000): how presidential candidates were secretly selected. Compares the 1988 and 1994 elections (winner vs. loser candidate networks).

Source data: ~1,200 biographies from *Mexican Political Biographies 1935–2009*.

## Folder architecture

This repo (`TapadosCode`) **contains code only**. Data, outputs, and literature live in a separate Dropbox folder:

```
~/Dropbox/TapadosPRI/     ← data + outputs (Dropbox only, NOT in git)
  data/                   ← CSVs, parsed_positions.csv, etc.
  output/                 ← PNGs, HTML, visualizations
  literature/             ← biography PDFs and papers

~/Dropbox/TapadosCode/    ← this repo (git + GitHub)
  code/
    config.py             ← central path configuration
    00-networks/00-preprocess/   ← ETL pipeline (scripts 01–05)
    03-descriptive_stats/        ← visualizations and stats (scripts 06–09)
```

## Path configuration

Paths to the data Dropbox are set via an environment variable, loaded automatically from `.env` (gitignored):

```
TAPADOSPRI_DB_ROOT=/Users/yourname/Dropbox/TapadosPRI
```

Never hardcode absolute paths — always use constants from `config.py`:
`DATA_DIR`, `OUTPUT_DIR`, `LITERATURE_DIR`, `BIOGRAPHIES_DIR`.

## Numbered pipeline

| File | What it does | Input → Output |
|---|---|---|
| `00-preprocess/01_extract_pdf.py` | Extracts text from biography PDF (pdfplumber, two-column layout) | PDF → `biographies_full.txt` |
| `00-preprocess/02_parse_biographies.py` | Parses raw text into structured CSV using field markers a–l | txt → `biographies.csv` |
| `00-preprocess/03_fix_person_names.py` | Repairs corrupted person names (death-date fragments / name bleed) in place, recovering them from `biographies_full.txt` | `biographies_corrected.csv` → `biographies_corrected.csv` |
| `00-preprocess/04_parse_positions.py` | Extracts state/org/dates/title; assigns `person_id`; cleans names (no accents, no parens) | `biographies_corrected.csv` → `parsed_positions.csv` (15K+ rows) |
| `00-preprocess/05_*.py` | One script per position type (education, govt, party, labor, public, birthplace) | `parsed_positions.csv` → specialized CSVs |
| `01-clean/05?_*_clean.py` | Post-processing cleaners, one per position type | specialized CSVs → `clean_positions/*.csv` |
| `00-preprocess/06_build_networks.py` | Build a per-tapado ego-network: explicit + co-education (faculty) + co-work (sub-unit) ties | `clean_positions/*` → `networks/tapado_edges.csv`, `tapado_nodes.csv` |
| `00-preprocess/07_family_surname_edges.py` | Add GPT-confirmed family-by-surname ties (human-curated via `family_surname_review.csv`) | → `networks/tapado_edges.csv` |
| `03-descriptive_stats/viz_ego_networks.py` | Per-election plot: winner vs. closest runner-up, shared ties in the middle | `networks/tapado_edges.csv` → `ego_network_<year>.png` |

## Code conventions

- All paths go through `config.py` — never `Path(__file__).parent / "data"` or hardcoded absolute paths
- Scripts in subdirectories prepend `CODE_DIR = Path(__file__).resolve().parents[2]` to `sys.path` to locate `config.py`
- Outputs always to `OUTPUT_DIR`, data always from `DATA_DIR`
- The master dataset is `parsed_positions.csv` (15K+ records) — do not edit manually

## Elections analyzed

- **1988**: Salinas de Gortari (winner) vs. Bartlett Díaz (loser)
- **1994**: Colosio Murrieta (winner) vs. Aspe Armella (loser)
- Candidates defined in `config.py` → `ELECTION_PAIRS` and `TAPADOS_1988`

## Collaborators

- `ezagoc` (Emilio Zagoc) — Windows, `C:\Users\Dell\Dropbox\TapadosPRI`
- `quinoba` (Joaquín Barrutia) — Mac, `/Users/joaquinbarrutia/Dropbox/TapadosPRI`

Each person maintains their own `.env` and `settings.local.json` (both gitignored).

## Data files (~/Dropbox/TapadosPRI/data/)

These files are never in git — they live only in Dropbox and are read/written by the scripts above.

### Raw / intermediate
| File | Description |
|---|---|
| `biographies_full.txt` | Full raw text extracted from the biography PDF (~1,034 pages) |
| `biographies.csv` | Initial parsed biographies (~2,886 rows, 13 cols): name, birth_date, birthplace, education, public_positions, party_positions, govt_positions, labor_positions, other_positions, personal_info |
| `biographies_corrected.csv` | Manually corrected version of the above — **this is the main input for the pipeline** |
| `biographies_pages34_64.txt`, `biographies_test_30pages.txt` | Partial extracts used for testing |

### Master positions dataset
| File | Description |
|---|---|
| `parsed_positions.csv` | **Central dataset.** 45,677 rows × 14 cols. One row per position record per person. Columns: record_id, person_id, person_name, field_type (education/govt/party/labor/public/other/birthplace), role_text_raw, role_text, position_title, organization, state, year_start, year_end, date_precision |

### Specialized position datasets (long format)
| File | Rows | Key columns |
|---|---|---|
| `education.csv` | 12,964 | degree_level, degree_field, foreign_degree, organization, state |
| `govt_positions.csv` | 12,664 | position_title, organization, rank, secretariat, federal, state |
| `party_positions.csv` | 6,006 | party, body, party_level, record_type, party_rank |
| `public_positions.csv` | — | Electoral/legislative positions (senators, deputies, governors, mayors) |
| `labor_positions.csv` | — | Union positions: org, sector, rank |
| `other_positions.csv` | — | Private sector, military, academic, religious |
| `birthplace.csv` | — | Birthplace records with state |

### Wide-format datasets (one row per person, dummies)
| File | Description |
|---|---|
| `education_wide.csv` | Dummies: phd, masters, diploma, undergraduate, law, economics, medicine, engineering, foreign_degree |
| `govt_positions_wide.csv` | Dummies: ever_secretary, ever_governor, ever_judge; n_govt_positions, highest_rank |
| `party_positions_wide.csv` | Dummies: pri_member, pan_member, ever_national_leader, ever_cen; highest_party_rank |
| `labor_positions_wide.csv` | Dummies by sector and rank |

### Tapado networks (`data/networks/`) — current

Built by `06_build_networks.py` + `07_family_surname_edges.py` from the cleaned
position datasets, keyed on `person_id`. One ego-network per tapado (the 73
pre-candidates in `corcholatas_historicas.xlsx`). An **edge** means the two people
plausibly knew each other:

- **co_education** — same educational focus + overlapping years. Large institutions
  (>60 people, e.g. UNAM) are refined to `(institution, faculty)` via `degree_field`;
  small/specific schools link on the institution alone. Both studying and teaching
  roles count (captures professor–student). *Note: big faculties like `UNAM | law`
  produce large same-generation cohorts — a real but broad "milieu" tie.*
- **co_work** — same organization + overlapping years, refined to a sub-unit and
  size-capped (≤60) so generic party membership / mega-ministries don't over-link;
  party is refined geographically (`PRI – Jalisco`, `PRI – Youth Organization`).
- **family / mentorship / personal** — stated in the biography `personal_info`.
- **family_surname** — shared paternal/maternal surname, GPT-confirmed (≤2nd cousins)
  and **human-curated** (see below).

| File | Description |
|---|---|
| `networks/tapado_edges.csv` | Edge list: `ego_id, ego_name, election_year, is_winner, alter_id, alter_name, edge_type, focus, focus_size, ego_role, alter_role, year_start, year_end, confirmed_by`. Ego-net = filter by `ego_id`. |
| `networks/tapado_nodes.csv` | `person_id, name, is_tapado, election_year, is_winner` |
| `networks/family_surname_candidates.csv` | All shared-surname pairs + GPT verdict + `in_scope` (audit trail for hallucination review) |
| `networks/family_surname_review.csv` | **Human curation** of the family ties: `keep` (1/0) + `corrected_relationship`; consumed by `07` to override GPT. Lives in Dropbox like other curated data. |

Viz: `03-descriptive_stats/viz_ego_networks.py` → `output/ego_network_<year>.png`
(winner = star, runner-up = circle, shared ties = squares in the middle).

### Legacy connections (superseded by the `networks/` pipeline above)
| File | Description |
|---|---|
| `parsed_connections.csv` | 6,656 dyads (older approach, name-keyed, pre name-fix). Kept for reference. |
| `parsed_connections_1982.csv` / `_1994.csv` | Older per-election connection files |

### Reference
| File | Description |
|---|---|
| `candidates/corcholatas_historicas.xlsx` | Historical list of tapado candidates per election |
| `shapefiles/mexico_states.json` | GeoJSON of Mexican states (used by geo visualization scripts) |

## Git workflow

```bash
git pull origin master        # before starting
# ... edit code ...
git add <files>
git commit -m "description"
git push origin master
```

Never commit: `.env`, `settings.local.json`, `__pycache__/`, `*.pyc`, `.Rhistory`, `.DS_Store`.

## Resolved data issue: malformed person names

### What happened

During the initial PDF parsing (`02_parse_biographies.py`), a newline **inside** a
name caused part of the name to "bleed" into the previous row's last field
(`sources`), leaving only a fragment as the current row's name. Two shapes:

```
"9, 1965)"  "Aug. 25, 1979."  "(Deceased 1953)"   ← deceased: only the death-date tail survived
"Manuel"    "del carmen"      "Monteros), eduardo" ← living: only a trailing given name / surname fragment
```

~110 of the ~2,886 biographies were affected, leaving those people unidentifiable
by name in `parsed_positions.csv` and every derived dataset.

### How it is fixed (reproducibly, in code)

`00-preprocess/03_fix_person_names.py` repairs every corrupt name **at the source**,
before `04` runs. For each corrupt row it rebuilds the real name from the previous
row's `sources` tail (where the bled name landed) and **validates it against
`biographies_full.txt`** before writing — names that fail validation are left
untouched and reported, so nothing is silently overwritten. The script is
idempotent and edits only the `name` column of `biographies_corrected.csv`,
preserving all manual corrections in the other columns.

### Pipeline order to regenerate everything

```
03_fix_person_names.py      # repair names in biographies_corrected.csv
04_parse_positions.py       # re-assign person_id, clean names (no accents, no parens)
05_*.py                     # education, govt, party, labor, public, military, other, birthplace, connections
01-clean/05?_*_clean.py     # post-processing cleaners
```

`04_parse_positions.py` assigns `person_id` by order of first appearance of each
unique cleaned name, so the names **must** be correct before `04` runs (hence `03`).
`clean_name_col` in `04` also strips accents and maternal-surname parentheses and
lower-cases Spanish connectors, so every `person_name` is plain ASCII, e.g.
`Bartlett Diaz, Manuel`, `Sanchez Cordero Davila, Olga Maria del Carmen`.

> The earlier `config.py → PERSON_NAME_CORRECTIONS_MAP` (a `person_id → name`
> override) is gone: it was unsafe because re-running `04` re-assigns person_ids,
> and is superseded by the source-level fix in `03`.
