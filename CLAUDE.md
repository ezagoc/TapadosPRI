# TapadosPRI — Project Context for Claude

## What this project is

Political network analysis of the "tapado" system in Mexico's PRI party (1921–2000): how presidential candidates were secretly selected. Compares the networks of the chosen successor vs. the losing pre-candidates across all successions 1940–2000.

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
    00-networks/00-preprocess/   ← ETL pipeline (scripts 01–07)
    00-networks/01-clean/        ← post-processing cleaners (05?_*_clean.py)
    02-rank/                     ← manual institution/title rank curation (generator + panel)
    03-descriptive_stats/        ← visualizations and stats
    04-analysis/                 ← analysis exports (export_candidate_networks.py)
    05-investment/               ← federal public-investment ETL (Azure JSON → real-peso DB)
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
| `01-clean/05?_*_clean.py` | Post-processing cleaners, one per position type. `05e_govt_positions_clean.py` Fix 9 recovers `organization` from `role_text` when it was never structured out (~15%→12% of dated govt records left without an institution) | specialized CSVs → `clean_positions/*.csv` |
| `00-preprocess/05_match_corcholatas.py` | Crosswalk each corcholata × election to a `person_id` (strict matcher), per-election winner, documented runner-up | `corcholatas_historicas.xlsx` → `candidates/corcholatas_matched.csv` |
| `00-preprocess/06_build_networks.py` | Build the FULL politician network: co-education (generation), co-work (sub-unit), co-military, co-revolution, regex-stated family/mentorship/personal | `clean_positions/*` → `networks/network_edges.csv`, `network_nodes.csv` |
| `00-preprocess/08_tie_weights.py` | Estimate how P(stated tie) decays with focus size; add `tie_weight` = (n−1)^b and `weight_newman`. Run after 07 | → `networks/network_edges.csv`, `tie_weight_params.csv` |
| `03-descriptive_stats/animate_network.py` | Animated history: the whole network grows in grey (nodes at birth, dated ties the year they formed; x ≈ birth year); the circle of the president in office is highlighted (direct ties coloured by kind) and jumps each sexenio; bottom strip = new ties per year with sexenio markers. All labels in English | → `output/network_history.gif`, `network_history_final.png` |
| `03-descriptive_stats/validate_network.py` | Stated-tie rate and lift by tie type × size bin (construct validity) | → `output/network_validation.csv` |
| `00-preprocess/07_bio_ties_gpt.py` | GPT reads every bio's `personal_info`; grounded, matched family/mentorship/personal ties + 30 curated `family_surname` ties. Run after 06 | → `networks/network_edges.csv`, `bio_mentions_gpt.csv` |
| `03-descriptive_stats/viz_ego_networks.py` | Per-election plot: winner vs. documented runner-up (ties as of e−1), shared ties in the middle | `networks/network_edges.csv` → `ego_network_<year>.png` |
| `04-analysis/export_candidate_networks.py` | Per election, one Excel per pre-candidate (winner, runner-up, every other loser): every tie formed by e−1 (name, type, focus detail) + each alter's position each year e−6..e+6 | `networks/network_edges.csv` + `clean_positions/*` → `output/candidate_networks/<year>/<year>_<role>_<surname>.xlsx` |
| `02-rank/02_position_tiers.py` | Rank every position record on three published scales — Smith (1979) Table A-3 `smith_tier` 0–8 (+ `smith_tier_ext`: his budget rules made time-varying with our investment panels), Brandenburg (1964) 12 rungs, official federal command ladder (`mando_level`, Manual de Sueldos 2000) — plus `hybrid_rank` = (13 − rung) + smith/10 + mando/100. Rules on role text (is_federal is unreliable), `rule` kept for audit; big parastatals time-varying from the agency panel (top-4 industrial by prior-6-year investment share; IMSS, ISSSTE, Smith's banks always big); ladder checked monotone vs 1999 official pay and the 1927 federal budget's daily pay | `clean_positions/*` → `rank/position_tiers.csv` |
| `02-rank/01_generate_rank_tables.py` | Emit editable rank lookup tables (institution + title) per domain, pre-seeded with heuristic `suggested_*_tier`. **Manual step**: fill the blank `domain_tier`/`global_tier`/`title_tier` columns by hand | `clean_positions/{govt,party,labor}_positions.csv` → `rank/<domain>_{institution,title}_rank.csv` |
| `05-investment/01_extract_investment_tables.py` | Extract the federal public-investment matrices (institution × state) from the Azure Document Intelligence JSON (cuadros 15–23, fiscal years 1959–63); stitch split section-tables, clean OCR values/states; validates subtotals vs. grand totals | `literature/InversionPublicaFederal_*.json` → `investment/federal_investment_long.csv`, `_institutions.csv`, `_wide_<year>.csv`, `_validation.csv` |
| `05-investment/02_build_deflator.py` | Build a Mexican CPI price deflator (World Bank WDI xls), rebased base=1960=100; 1959 takes the 1960 value | `investment/API_FP.*.xls` → `investment/price_deflator_mexico.csv` |
| `05-investment/03_link_investment_to_ranks.py` | Deflate investment to real 1960 pesos, rank institutions by budget, and join a budget signal onto the govt rank table via a curated Spanish→English crosswalk (`match_confidence` exact/approx) | investment + `rank/govt_institution_rank.csv` → `investment/federal_investment_budget_reference.csv`, `rank/govt_institution_rank_budget.csv` |
| `05-investment/05_download_inegi_investment.py` | Download INEGI digital-library scans with realized federal investment by state, 1970–2003 (SPP 1970–80; "El ingreso y el gasto público en México" 1986/87/93/99/2000/01/04 eds.) + manifest | → `literature/inegi_investment/*.pdf`, `manifest.csv` |
| `05-investment/06_extract_inegi_state_investment.py` | Read the state-total tables with vision LLMs (no Azure): two independent reads per crop (gpt-5.5 / gpt-5.4), 3rd read breaks ties; parts vs printed total, single-cell reconciliation, focused re-reads, 2 documented manual corrections (SLP 1974 misprint, Sonora 1976). Units → millions of new pesos | → `investment/inegi_state_investment_long.csv`, `_validation.csv`, `inegi_raw/` (cache) |
| `05-investment/07_build_state_investment_panel.py` | State × year panel 1959–2003: 1959–69 books + 1970–2003 INEGI (most recent balanced edition per year); nominal, real (1960 pesos), share of states | → `investment/state_investment_panel.csv`, `state_investment_sources.csv` |
| `05-investment/llm_tables.py` | Shared vision-LLM helpers for 06/09: page rendering, cached two-reader reads, value parsing, and a **budget guard** — every call logged to `data/llm_usage_ledger.csv` at list price +20%; stops at `LLM_BUDGET_USD` (default 20). Key: `OPENAI_ZAGO` (else `OPENAI_API_KEY`) via `config.openai_api_key()` | — |
| `05-investment/08_extract_agency_investment.py` | Realized investment by agency from *Inversión Pública Federal 1925–1963* (Cuadro 2: 1925–58; Cuadro 11: 1959–63), vision-LLM reads; one documented manual row (1956 "Otras" = 6). All 39 years add up to printed totals | → `investment/agency_investment_1925_1963_long.csv`, `_validation.csv` |
| `05-investment/09_extract_inegi_agency_investment.py` | Realized investment by secretaría and by parastatal, 1970–2003 (SPP 1970–80 II.7/II.9; INEGI 1986/1987/1993/1999/2001/2004 eds.); hierarchical checks, documented misprint corrections (`MANUAL_CORRECTIONS`), `SOURCE_ISSUES` for printed contradictions. The 1986 and 2004 tables are hand transcriptions (`investment/agency_transcribed/*.csv`, the OpenAI account ran out of credit) run through the same checks | → `investment/agency_investment_inegi_long.csv`, `_validation.csv` |
| `05-investment/10_build_agency_investment_panel.py` | Agency × year panel 1925–2003 (gap 1964–69: the 1964–66 / 1965–70 books give agencies only as authorized/programmed). One source table per year × block (most recent edition); `agency_key` + `lineage` crosswalk across renamings; blocks `dependencias` (secretarías' own investment: ≤1983 and 1998–2003), `paraestatal` (entity level) and `ramo_sector` (1984–98, sector view that already contains parastatals — never add to `paraestatal`); nominal, real 1960 pesos, share of block-year total | → `investment/agency_investment_panel.csv` |
| `05-investment/plan/investment_descriptives.Rmd` | Professor-facing descriptive report (real pesos): totals by year/president, top institutions/states, choropleths, heatmap, sector mix, growth, concentration (Gini/Lorenz). Needs R pkgs `sf`,`kableExtra` + pandoc | investment CSVs → knitted HTML |

## Code conventions

- All paths go through `config.py` — never `Path(__file__).parent / "data"` or hardcoded absolute paths
- Scripts in subdirectories prepend `CODE_DIR` to `sys.path` to locate `config.py`. Depth depends on nesting: `00-networks/*/` uses `parents[2]`, top-level stage folders (`02-rank/`, `05-investment/`) use `parents[1]`
- Outputs always to `OUTPUT_DIR`, data always from `DATA_DIR`
- The master dataset is `parsed_positions.csv` (15K+ records) — do not edit manually
- Python runs in a repo-local `.venv` (Python 3.14; `pandas`, `xlrd` for the investment xls, `openai`, `spacy`, etc.). R 4.6 is used for `.Rmd` reports

## Elections analyzed

- All 11 PRI/PRM successions 1940–2000 (83 corcholata-elections, 71 people matched).
- Candidates, winners (per election) and the documented runner-up live in
  `data/candidates/corcholatas_matched.csv` (built by `05_match_corcholatas.py`).
- 1994 has two ✓: Colosio (`designated_removed`) and Zedillo (`winner`, took office).
- 2000: Labastida (`nominee_lost`) — the PRI lost the presidency.

## Collaborators

- `ezagoc` (Eduardo Zago) — Windows, `C:\Users\Dell\Dropbox\TapadosPRI`
- `ezagoc` (Eduardo Zago) — Mac, `/Users/ezagoc/Dropbox/TapadosPRI`
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

### Full politician network (`data/networks/`) — current

Built by `05_match_corcholatas.py` → `06_build_networks.py` → `07_bio_ties_gpt.py`
from the cleaned position datasets, keyed on `person_id`. It is the **full network
of all ~2,900 politicians** (every pair that plausibly knew each other), not just the
tapados. A tapado's ego-network is a view of it: `network_utils.ego_view(edges,
[pid], as_of=year)`. **Always pass `as_of`** (e.g. `election_year − 1`, the destape
year) so treatment is defined by ties formed *before* the succession — ~9% of dated
ties (19% of co_work) form after the election.

- **co_education** — same school, level and role (student–student or staff–staff;
  never student–teacher). A single year is the degree year → enrollment window
  `[degree − program_length + 1, degree]` (lic 5, masters 2, PhD 3). Small schools:
  overlapping windows. Large institutions (>60 people, e.g. UNAM): refined to faculty
  **and same generation** (entry years ±1) — classmates, not the whole faculty.
  Teaching staff link on overlap (faculty inferred from role text) and are size-capped
  like a workplace.
- **co_work** — same organization + overlapping years (±1), refined to a sub-unit;
  party refined geographically (`PRI – Jalisco`, `PRI – Youth Organization`); non-federal
  govt posts carry their state (`Secretariat of Government (Quintana Roo)`); elected
  office only for state legislatures / DF Assembly (committees such as Gran Comisión
  and the federal Congress are not used); fragment labels ("administration and") dropped.
- **Age plausibility:** a record starting before age 14 (university, work), 18
  (teaching) or 4 (primary/secondary) is a mis-parsed year and forms no ties; a stated
  year before the younger person's birth is dropped. → no tie predates a birth.
- **Size = people at the focus AT THE SAME TIME** (not over its whole history: SPP had
  105 people over 1973–92 but ≤44 at once). `focus_size` = people there the year the
  tie began. The file keeps every focus with ≤60 at once (max observed: 57).
- **Tie weights, no cutoff** (`08_tie_weights.py`): P(stated tie | co-location) decays
  smoothly with size as a power law, logit slope on log(n−1) ≈ −0.3 (co_work −0.34,
  SE 0.09; co_education −0.30) — no natural threshold, and much flatter than Newman's
  1/(n−1). Main spec: `tie_weight = (n−1)^b` (b estimated per type; stated ties = 1).
  Robustness curve: unweighted, `weight_newman`, caps 10/20/30/60
  (`network_utils.ROBUSTNESS_CAPS`, `ego_view(max_focus_size=…)`). Caveat: the
  benchmark (stated ties) is incomplete and may over-represent small prominent groups,
  so results must hold across the whole curve.
- **family / mentorship / personal** — stated in a biography's `personal_info`, from
  two sources (`confirmed_by`): `rule` (regex in 06) and `gpt_bio` (07: GPT reads every
  bio and lists each named person + relationship + verbatim quote; kept only if name
  and quote appear in the text, resolved with the strict matcher, age-consistent with
  the kin term). `*_given_name` = a bare given name completed with the biographee's
  surname (lower precision).
- **Dating** (`date_basis`): `overlap` (co-location years); `birth` (blood kin: the
  younger one's birth year); `stated_exact` / `stated_decade` (year the relationship
  began, as written in the bio — verified to appear in the text); `inferred` (GPT from a
  stated life stage + birth year, e.g. "secondary school classmate"); empty = unknown
  (`ego_view(..., undated="drop")` for robustness).
- **family_surname** — only the 30 human-kept pairs of `family_surname_review.csv`
  (`gpt+human`). GPT confirming kinship from surnames alone had ~21% precision in that
  review (30/142), so it is **not** run on the full network.

**Name matching** (`network_utils.StrictNameMatcher`): Spanish order "Given Paternal
Maternal"; the paternal surname must be preceded only by the person's given names, a
stated maternal surname must match (fuzzy), optional age bounds. The old token-overlap
matcher had linked Manuel Pérez Treviño → Avila Pérez, Manuel and Ezequiel Padilla
(b. 1890) → Padilla Couttolenc (b. 1942).

| File | Description |
|---|---|
| `candidates/corcholatas_matched.csv` | Crosswalk corcholata × election → `person_id`, `is_winner` (per election), `is_runner_up` + `runner_up_source`, `match_status`. Single source of truth for candidates. Pérez Treviño (1940) has no own entry in the 1935–2009 volume. |
| `networks/network_edges.csv` | Undirected edges (`person_a < person_b`): `name_a/b, edge_type, focus, focus_size, role_a/b, year_start, year_end, date_basis, stated_by, confirmed_by, tie_weight, weight_newman` |
| `networks/tie_weight_params.csv` | Estimated decay slope per tie type (08) |
| `networks/network_nodes.csv` | Everyone: `birth_year, birth_state, degree, n_records, n_dated_records, personal_info_chars` (network size grows with biography length — control for these), `is_tapado, tapado_elections, winner_elections` |
| `output/network_validation.csv` | Stated-tie rate and lift by tie type × focus size (`validate_network.py`) |
| `networks/bio_mentions_gpt.csv` | 07 cache + audit: every GPT mention, quote, grounding checks, match result. Delete to re-query. |
| `networks/family_surname_review.csv` | Human curation of surname kinship (`keep`, `corrected_relationship`) |
| `networks/family_surname_candidates.csv` | Old GPT surname verdicts for tapado pairs (audit only) |
| `networks/legacy_ego_v1/` | Superseded per-tapado edge lists (`tapado_edges.csv`, …) |

**Treatment / control** (`role` in the crosswalk): `winner` (took office; 1994 =
Zedillo), `runner_up` (documented, with source; robustness), `loser` (main control =
all losers), `designated_removed` (1994 Colosio, assassinated — excluded from the
pooled design; special Zedillo-vs-Colosio comparison), `nominee_lost` (2000
Labastida won the primary but lost to Fox — nomination, not the presidency).
`took_office` = 1 only for the person who became president.

Viz: `03-descriptive_stats/viz_ego_networks.py` → `output/ego_network_<year>.png`
(winner = star, documented runner-up = circle, shared ties = squares; ties as of e−1).

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

### State investment panel (`data/investment/state_investment_panel.csv`) — main distributive outcome
32 states × 1959–2003 (45 years) of realized federal public investment (**1964 is AUTHORIZED** — the 1964 book has no realized figures; column `measure`): `nominal_mn_new_pesos`,
`real_mn_1960_pesos` (CPI, 1960=100; deflator now runs to 2010), `share_of_states`, `source`.
- **No state data exist for 1940–1958** (the 1925–1963 book is national-only before 1959) →
  investment outcomes cover the 1964–2000 successions only.
- 1970–2003 read from scans by LLMs, validated: every year used adds up to its printed total;
  overlapping editions give identical state shares except 1999 (revision, max diff 1.5 pp).
- "No distribuible geográficamente" is 20–24% in 1983–84 (≤12% otherwise) → prefer `share_of_states`.
- 1965–69 (`04_*`): cuadros 19–23 are annual (sum to cuadro 18); their `period_start` is mislabelled 1965.
- Visible political budget cycle: investment peaks in election years and drops in each sexenio's first year.

### Rank curation (`data/rank/`) — human-edited
| File | Description |
|---|---|
| `<domain>_institution_rank.csv` | One row per institution (govt/party/labor); pre-seeded `suggested_*_tier` + blank `domain_tier`/`global_tier` to fill by hand. Higher tier = more senior; combined score is institution-dominant lexicographic |
| `<domain>_title_rank.csv` | One row per job title; blank `title_tier` to fill |
| `govt_institution_rank_budget.csv` | Auto-generated copy of the govt table + investment budget columns (do not hand-edit; regenerated by `05-investment/03`) |

### Federal public investment (`data/investment/`)
Source: `literature/InversionPublicaFederal_1925-1963-66-129.pdf.json` (Azure
Document Intelligence layout output). This excerpt = cuadros 15–23, **fiscal years
1959–1963, all under one president (Adolfo López Mateos)**. Amounts are *millones
de pesos*; `03` deflates to real 1960 pesos.

| File | Description |
|---|---|
| `federal_investment_long.csv` | One row per (year, institution, state); `row_type` ∈ line_item / sector_subtotal / grand_total; `sector` ∈ gobierno_federal / organismos_descentralizados / empresas_participacion_estatal |
| `federal_investment_institutions.csv` | 86-institution catalog (Spanish names, by sector) |
| `federal_investment_budget_reference.csv` | Catalog + real total/annual investment, `budget_tier` (1–5), `govt_rank_name` crosswalk + `match_confidence` |
| `price_deflator_mexico.csv` | CPI deflator (1960=100), inflation %, WPI, 1959–2000 |
| `federal_investment_wide_<year>.csv`, `federal_investment_validation.csv` | Per-year pivots; subtotal-vs-total QA (~97.5% reconcile) |

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
05_match_corcholatas.py     # candidate crosswalk (person_id per corcholata × election)
06_build_networks.py        # full network (rule-based ties)
07_bio_ties_gpt.py          # + GPT-read biography ties (cached) + curated family_surname
08_tie_weights.py           # calibrated tie weights
```

Re-running `04` can re-assign person_ids: `07` drops cached GPT answers whose
person_id no longer carries the same name (re-queried), and asserts that
`family_surname_review.csv` ids still match their names.

`04_parse_positions.py` assigns `person_id` by order of first appearance of each
unique cleaned name, so the names **must** be correct before `04` runs (hence `03`).
`clean_name_col` in `04` also strips accents and maternal-surname parentheses and
lower-cases Spanish connectors, so every `person_name` is plain ASCII, e.g.
`Bartlett Diaz, Manuel`, `Sanchez Cordero Davila, Olga Maria del Carmen`.

> The earlier `config.py → PERSON_NAME_CORRECTIONS_MAP` (a `person_id → name`
> override) is gone: it was unsafe because re-running `04` re-assigns person_ids,
> and is superseded by the source-level fix in `03`.
