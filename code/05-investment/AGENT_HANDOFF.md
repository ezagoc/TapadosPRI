# Agent Handoff — `05-investment` stage

Context for whoever (human or agent) picks this up next. Read alongside the root
`CLAUDE.md`. Everything here runs from the repo-local `.venv` (Python 3.14).

## Why this stage exists

The bigger goal is the **manual institution/title ranking** in `02-rank/`: rank
institutions first, then job titles within them, to build time-varying career-rank
variables (did a person rise or not?). While seeding those rank tables we found the
biography-derived institution names are noisy (`secretariat_norm` has an 843-row
long tail full of fragments like `"State 882 mexican political biographie"`,
`"government"`, `"police"`). This stage brings in an **objective, external signal of
institutional importance**: the federal public-investment tables, which give a clean
sector-grouped list of real federal institutions and how much each one spent.

So: `05-investment` feeds `02-rank`. The payoff is
`data/rank/govt_institution_rank_budget.csv` — the govt rank table with a budget
signal attached.

## Data provenance & scope

- Source: `literature/InversionPublicaFederal_1925-1963-66-129.pdf.json` — Azure
  Document Intelligence (`prebuilt-layout`, apiVersion 2024-11-30) output. 167
  tables over 64 pages.
- This excerpt covers **fiscal years 1959–1963 only** (original pp. 66–129). The
  full printed volume is 1925–1963, but only these years are in the JSON.
- **All five years are one presidency: Adolfo López Mateos (PRI, Dec 1958 – Nov
  1964).** "By presidency" cuts therefore collapse to one sexenio right now.
- Two interleaved table families per year:
  - **Institution × state** ("INVERSIÓN DE LAS DEPENDENCIAS…") — cuadros 15,17,19,21,23 → **extracted**.
  - **Destination × state** ("DESTINO DE LA INVERSIÓN…") — cuadros 16,18,20,22,24 → **NOT extracted** (different schema; see open threads).

## Scripts (run order)

```bash
.venv/bin/python code/05-investment/01_extract_investment_tables.py
.venv/bin/python code/05-investment/02_build_deflator.py
.venv/bin/python code/05-investment/03_link_investment_to_ranks.py
# then, in RStudio or with pandoc installed:
Rscript -e 'rmarkdown::render("code/05-investment/plan/investment_descriptives.Rmd")'
```

1. **`01_extract_investment_tables.py`** — parses the JSON into a clean long table.
   Tags each table object with (cuadro, year, parte, type) via document character
   offsets against caption paragraphs; keeps only institution matrices; stitches the
   split section sub-tables of each parte while tracking the current sector down the
   rows; melts to long; cleans OCR values and state names; canonicalizes institution
   spelling (de-hyphenation + accent merge, 101→86). Writes a validation report.
2. **`02_build_deflator.py`** — reads the three World Bank `API_FP.*.xls` files,
   extracts Mexico, rebases CPI so **1960 = 100**, assigns **1959 the 1960 value**.
3. **`03_link_investment_to_ranks.py`** — deflates to real 1960 pesos, ranks
   institutions by budget (`budget_tier` 1–5), and joins the budget onto the govt
   rank table using the curated `CROSSWALK` dict (Spanish → English).

## Outputs

`data/investment/`: `federal_investment_long.csv`, `_institutions.csv`,
`_budget_reference.csv`, `_wide_<year>.csv`, `_validation.csv`,
`price_deflator_mexico.csv`.
`data/rank/`: `govt_institution_rank_budget.csv` (govt rank table + budget columns).

Config constants added: `INVERSION_PUBLICA_JSON`, `INVESTMENT_DIR`, `CPI_LEVEL_XLS`,
`INFLATION_XLS`, `WPI_XLS`, `PRICE_DEFLATOR_CSV`, `DEFLATOR_BASE_YEAR`,
`CLEAN_*_POSITIONS_CSV`, `RANK_DIR`.

## Key decisions & caveats (don't re-litigate blindly)

- **Extraction quality is good:** 0 unparsed values; ~97.5% of (year, state) sector
  subtotals reconcile to the grand total. The 4 small gaps are OCR errors in
  *printed subtotals*, not in the line items (the line items sum correctly).
- **`:unselected:` = empty cell** (Azure checkbox artifact); `-` = nil (→ 0). Value
  fixes handle `0:4`→`0.4`, `1 419.6`→`1419.6`, trailing `:selected:`.
- **Budget ≠ prestige.** The budget signal is *capital spending*, not political
  power. Hacienda and Gobernación (the most powerful ministries) have tiny direct
  investment (budget tiers 3), while DDF/PEMEX/CFE/SOP/SRH dominate spending. Pair
  `invest_budget_tier` with human `global_tier` judgment; do not substitute.
- **Two `approx` crosswalk matches:** SOP (Obras Públicas) and SRH (Recursos
  Hidráulicos) have no clean bucket in the biography table — `secretariat_norm`
  conflates them with the SCOP/SARH-era names. Flagged `match_confidence=approx`.
- **Deflation is modest** (~3.4% cumulative 1960→63, a low-inflation window), but
  keeps years comparable and sets up the eventual full panel. WPI is empty pre-1970.

## Open threads / next steps

### Added: realized investment by purpose and state, 1965–1969

`04_extract_purpose_state_1965_1969.py` parses
`literature/federal_investment_1965_1970-73-128.pdf.json`, cuadros 18–23.
Cuadro 18 is the 1965–1969 aggregate and cuadros 19–23 are the annual realized
matrices for 1965–1969. The source has no realized 1970-by-state matrix; 1970
appears only in programmed national tables. Cuadro 17 is a redundant transposed
summary and is skipped.

Outputs in `data/investment/`:

- `federal_investment_purpose_state_long.csv`
- `federal_investment_purpose_state_wide_1965_1969.csv`
- `federal_investment_purpose_state_wide_<year>.csv` for 1965–1969
- `federal_investment_purpose_state_validation.csv`

The long file has 4,950 rows: 25 concepts × 33 geographies (32 states plus the
national total) × 6 matrices. It retains raw OCR strings and parse flags. Six
unambiguous OCR errors are corrected only where independent grand/category,
state, and annual-period sums establish the value; they are marked
`corrected_reconciled_ocr`. Remaining small printed/OCR discrepancies stay in
the validation file rather than being silently changed.

- **`02-rank/` manual tiering is still pending** — the human fills the blank
  `domain_tier`/`global_tier`/`title_tier` columns in `data/rank/*_rank.csv`.
- **`02-rank/02_build_rank_panel.py` is NOT written yet** — the script that joins the
  completed tiers onto position records and builds the person×year promotion panel
  (Δscore > 0). This is the actual analytical payoff of the ranking work.
- **Only govt gets a budget signal.** Party and labor institutions have no
  investment counterpart. Fine — note it.
- **Extend to 1925–1958** if those cuadros are digitized → turns the single-sexenio
  report into a real cross-president comparison (the president lookup already
  generalizes).
- **DESTINO tables (cuadros 16–24) are unextracted** — purpose × state investment;
  a second, useful matrix family if wanted.
- **Rmd rendering** needs `install.packages(c("sf","kableExtra"))` + pandoc (or knit
  in RStudio). Core data logic is validated; only the map/table/render deps are missing.

## Gotchas

- Python here is **3.14** (very new). `spacy` needed a manual `click` install; some
  heavy wheels may lag. `.xls` reading needs `xlrd` (installed).
- Top-level stage folders (`02-rank/`, `05-investment/`) locate `config.py` via
  `parents[1]`; the deeper `00-networks/*/` scripts use `parents[2]`.
- Data lives only in Dropbox (`TAPADOSPRI_DB_ROOT`), never in git.
