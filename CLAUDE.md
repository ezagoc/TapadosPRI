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
| `00-preprocess/04_parse_positions.py` | Extracts state/org/dates/title from semi-structured text | `biographies.csv` → `parsed_positions.csv` (15K+ rows) |
| `00-preprocess/05_*.py` | One script per position type (education, govt, party, labor, public, birthplace, connections) | `parsed_positions.csv` → specialized CSVs |
| `03-descriptive_stats/viz_network.py` | Network graphs: top connections to winner vs. loser candidate | CSVs → PNGs |
| `03-descriptive_stats/viz_geo_network.py` | Geographic maps by state, pre/post election | CSVs + GeoJSON → PNGs |
| `03-descriptive_stats/viz_timeline.py` | Gantt-style timeline: tapado locations year by year | CSVs → PNGs |
| `03-descriptive_stats/viz_influence_map.py` | Influence map with temporal gradient | CSVs → PNGs |

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

### Network / connections
| File | Description |
|---|---|
| `parsed_connections.csv` | 6,656 dyads. Cols: person_a, person_b, connection_type (family/mentorship/personal/shared_government/shared_education/shared_party/shared_labor), detail, shared_state, year_start, year_end |
| `parsed_connections_1982.csv` | Connections filtered/weighted for the 1982 election |
| `parsed_connections_1994.csv` | Connections filtered/weighted for the 1994 election |

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
