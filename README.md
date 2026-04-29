# TapadosPRI

Code repository for the TapadosPRI project.

This repository now separates:

- `code` in GitHub: `C:\Users\Dell\Documents\GitHub\TapadosPRI`
- shared project data, literature, and outputs in Dropbox: `C:\Users\Dell\Dropbox\TapadosPRI`

The code is written so you and your coauthor can work from the GitHub repo while continuing to read and write the shared project data in Dropbox.

## Project Layout

`code/config.py`
: Central path and shared configuration file.

`code/00-networks/00-preprocess/`
: PDF extraction, biography parsing, structured position parsing, and dataset builders.

`code/03-descriptive_stats/`
: R descriptive-statistics scripts and Python visualization scripts.

`code/extra-03_clean_biographies.R`
: Extra R cleaning workflow for biographies.

`requirements.txt`
: Python dependencies for the repo.

`.env.example`
: Example environment variables for pointing the code to the shared Dropbox project root.

`setup_env.ps1`
: PowerShell helper that sets the Dropbox-backed environment variables and activates `.venv`.

## Shared Data Layout

The code expects the Dropbox project root to contain:

- `data/`
- `literature/`
- `output/`

Important files currently referenced by the pipeline include:

- `data/biographies_corrected.csv`
- `data/biographies.csv`
- `data/biographies_full.txt`
- `data/parsed_positions.csv`
- `data/parsed_connections.csv`
- `data/education.csv`
- `data/govt_positions.csv`
- `data/party_positions.csv`
- `data/labor_positions.csv`
- `data/birthplace.csv`
- `data/shapefiles/mexico_states.json`
- `literature/biographies/Mexican_Political_Biographies_1935-2009_Fourth_Edi....pdf`

## Path Configuration

The main configuration lives in `code/config.py`.

By default it uses:

- `TAPADOSPRI_DB_ROOT = C:\Users\Dell\Dropbox\TapadosPRI`
- `TAPADOSPRI_DATA_DIR = %TAPADOSPRI_DB_ROOT%\data`
- `TAPADOSPRI_OUTPUT_DIR = %TAPADOSPRI_DB_ROOT%\output`
- `TAPADOSPRI_LITERATURE_DIR = %TAPADOSPRI_DB_ROOT%\literature`

You can override any of these with environment variables if the shared folder moves.

## Python Setup

From the repo root:

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If you want to set the shared Dropbox path explicitly for the current PowerShell session:

```powershell
$env:TAPADOSPRI_DB_ROOT = "C:\Users\Dell\Dropbox\TapadosPRI"
```

Or simply run:

```powershell
.\setup_env.ps1
```

The preprocessing pipeline also uses the spaCy model `en_core_web_sm`.
If you recreate the environment from scratch, install it with:

```powershell
python -m spacy download en_core_web_sm
```

## R Setup

The R scripts assume the same Dropbox-backed environment variables.

Required R packages include:

- `tidyverse`
- `lubridate`
- `igraph`
- `ggraph`
- `tidygraph`
- `patchwork`
- `scales`
- `RColorBrewer`

In R:

```r
install.packages(c(
  "tidyverse", "lubridate", "igraph", "ggraph",
  "tidygraph", "patchwork", "scales", "RColorBrewer"
))
```

## Typical Workflow

1. Extract biography text from the source PDF.
2. Parse biographies into structured rows.
3. Parse positions into a unified long dataset.
4. Build domain-specific datasets:
   - education
   - government
   - party
   - labor
   - public
   - other
   - birthplace
5. Build connection datasets.
6. Run descriptive statistics and network visualizations.

## Notes

- Nested scripts were updated so they can import `code/config.py` when run directly.
- The repo stores code only; large data files remain in Dropbox.
- Outputs are written to the shared Dropbox `output/` folder by default.
