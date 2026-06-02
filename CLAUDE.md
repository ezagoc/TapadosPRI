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

## Git workflow

```bash
git pull origin master        # before starting
# ... edit code ...
git add <files>
git commit -m "description"
git push origin master
```

Never commit: `.env`, `settings.local.json`, `__pycache__/`, `*.pyc`, `.Rhistory`, `.DS_Store`.
