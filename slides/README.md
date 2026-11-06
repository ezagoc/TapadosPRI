# slides: the code behind the seminar deck

Everything that `research/slides/3rdYearPresentation/main.tex` shows (every figure, table and number) is produced by the
scripts in this folder from the shared data in `TapadosPRI/data`, and written under `TapadosPRI/output/slides`. One
command rebuilds all of it:

```sh
bash slides/run_all.sh              # every step, about two hours; one log per step in TapadosPRI/output/slides/logs
bash slides/run_all.sh --list       # the steps, in order
bash slides/run_all.sh rp_thresholds collect     # only the named steps
```

Paths come from `.env` at the repository root (`TAPADOSPRI_DB_ROOT=/Users/<you>/Dropbox/TapadosPRI`, see the root
README). Python runs in the repository's environment (pandas, numpy, matplotlib); R needs data.table, ggplot2, sandwich,
haven, survival, readxl, patchwork and ragg. Figures of the deck keep fixed axes (`reference/`), so refreshed numbers
never move a frame on a slide.

## Where things are

| Folder | What it holds |
|---|---|
| `data/` | The three steps that write into `TapadosPRI/data`: `death_years.py` (death years from Camp's headers and Wikidata), `verified_deaths.py` (the deaths verified in the biography headers, used by the eligibility rule) and, from `code/02-rank/`, the office scale `position_tiers.csv` (`02_position_tiers.py`, title-corrected version of 26 October 2026). |
| `analysis/` | The main design and every result slide. `estimate_main.R` builds the sample, the ties and the weights and is sourced by every other script; `design_tools.R` holds the estimator, the Ferman-Pinto bootstrap and the house style; `rp_setup.R` the reward/penalty design against the unaligned. `MAIN_SPEC.md` is the written specification. |
| `benchmarks/` | The alternative allocation rules (purge, promotions only, proportional sharing, career merit): `prepare.R` reuses the design, `prepare_calendar.R` and `assignments.py` build the synthetic careers, `inference.R` re-estimates the design on them, `figures.py` draws the figure. |
| `deck/` | Tables built for the deck from saved estimates (`build_rank_description.py`, `build_by_succession_table.py`), the headline macros (`headline_macros.py`) and `collect_deck_files.py`, which copies every deck file to `output/slides/deck` and into the Overleaf repository. |
| `descriptives/` | The motivation and data slides: the PRI's presidential vote and land reform by president (`viz_appendix_descriptives.py`), federal investment by agency (`plot_agency_series.py`), and the cross-national autocracy benchmark (`autocracy/`, with its two hand-coded extension files), and the 1946 biographies figure (`bio_links_1946.py`). |
| `reference/figure_geometry/` | The axis ranges of the deck's event-study figures, frozen on the estimates of 27 October 2026 (copies of that run's CSVs; `design_tools.R`, `figures.R`). |

Outputs under `TapadosPRI/output/slides`:

| Folder | Written by |
|---|---|
| `analysis/` | the scripts of `analysis/` and `deck/`: estimates (CSV), figures (pdf/png) and `tables/` (every `.tex` table and macro file) |
| `analysis/robust_ties_e4/`, `analysis/robust_predetermined_inclusion/` | the two sample variants of the robustness table (`variant_annual.R`) |
| `benchmarks/` | `benchmarks/`: `data/` (design, calendar, synthetic paths, inference) and `final/` (the figure) |
| `descriptives/` | the scripts of `descriptives/` |
| `deck/figures/`, `deck/tables/` | `collect_deck_files.py`: the deck's files under their deck names |
| `logs/` | one log per step of `run_all.sh` |

## From a slide to its script

Deck file (in `3rdYearPresentation/figures` or `tables`) ← file under `TapadosPRI/output/slides` ← script. The same
list drives `deck/collect_deck_files.py`.

| Slides | Deck file | Output | Script |
|---|---|---|---|
| Motivation: how unusual was the PRI | `autocracy_survival_successions.pdf` | `descriptives/` | `descriptives/autocracy/06_successions_survival.R` (tables from `01_build_tables.R`, `03_extend_to_2025.R`) |
| The 1946 succession: ties read off the biographies | `bio_links_1946.pdf` | `descriptives/` | `descriptives/bio_links_1946.py` (crops of Camp 2011, phrases highlighted) |
| The 1946 succession | `followers_1946_aleman.tex`, `followers_1946_padilla_top12.tex`, `followers_1946_macros.tex` | `analysis/tables/` | `analysis/followers_table_1946.py` |
| Data: sample, ladder, balance | `sample.tex`, `ladder_shares.tex`, `balance_combined.tex` | `analysis/tables/` | `deck/build_rank_description.py`, `analysis/ladder_shares.R`, `analysis/balance_combined.R` |
| Data appendix: vote, investment, land | `pri_vote.pdf`, `investment_series.pdf`, `land_by_president.pdf` | `descriptives/` | `descriptives/viz_appendix_descriptives.py`, `descriptives/plot_agency_series.py` |
| Who holds the posts | `md_post_holders.pdf`, `post_holders_macros.tex` | `analysis/` | `analysis/post_holders.R` |
| The raw trajectories | `md_rp_raw.pdf` | `analysis/` | `analysis/rp_raw_trajectories.R` |
| First stage: new appointments | `md_first_stage_fed.pdf`, `first_stage_macros.tex` | `analysis/` | `analysis/first_stage.R` |
| First stage, reward and penalty | `md_first_stage_rp.pdf`, `first_stage_rp_macros.tex` | `analysis/` | `analysis/first_stage_rp.R` |
| No purge (holding a post) | `md_es_reward_punishment_office.pdf`, `rp_office_macros.tex`; appendix `md_es_extensive.pdf` | `analysis/` | `analysis/rp_office.R`; `analysis/margins.R` + `figures_deck.R` |
| The career premium (headline) | `md_es_rank.pdf`, `title_correction_macros.tex`, `main_direct_tie_macros.tex`, `pay_macros.tex` | `analysis/` | `analysis/event_study.R` + `figures_deck.R`; `deck/headline_macros.py`; `analysis/appendix_diagnostics.R`; `analysis/pay_envelope.R` |
| Half reward, half penalty | `md_es_reward_punishment.pdf`, `rp_macros.tex` | `analysis/` | `analysis/reward_punishment.R` + `figures_deck.R` |
| Where on the ladder | `md_rp_thresholds_gap.pdf`, `md_rp_thresholds.pdf`, `rp_thresholds_macros.tex` | `analysis/` | `analysis/rp_thresholds.R` |
| Two steps away | `md_es_indirect.pdf`, `indirect_macros.tex` | `analysis/` | `analysis/indirect_ties.R` |
| Succession by succession | `md_by_succession_forest.pdf`, `by_succession_forest_macros.tex`, `het_ties_macros.tex` | `analysis/` | `analysis/by_succession_forest.R`; `analysis/heterogeneity.R` + `het_ties_figure.R` (the number of splits) |
| Allocation rules | `rules_table.tex`, `rules_macros.tex`, `benchmarks_all_comparisons.pdf` | `analysis/tables/`, `benchmarks/final/` | `analysis/rules_table.R`; `benchmarks/figures.py` |
| The losers themselves | `loser_careers.tex`, `loser_macros.tex` | `analysis/tables/` | `analysis/loser_careers.py` (after `analysis/aspirants_table.R`) |
| Appendix: randomization, robustness, leave one out, runner-up | `md_randomization.pdf`, `randomization_macros.tex`; `md_robustness.tex`; `md_by_succession.tex`, `by_succession_macros.tex`; `runner_up.tex`, `runner_up_macros.tex` | `analysis/` | `analysis/randomization_inference.R`; `analysis/appendix_diagnostics.R` (+ `variant_annual.R`); `deck/build_by_succession_table.py`; `analysis/runner_up.R` |

Static images (not generated): `1942_mexican_cabinet_chart_poster.png` and the four `1946_portrait_*.png`, kept only
in the Overleaf repository.

## Checking a rebuild against the deck

`python3 slides/deck/collect_deck_files.py --check` compares every pipeline output with the file the deck currently
reads (text files exactly, comment lines aside; PDFs by page size and text) and copies nothing. `collect` (the last step
of `run_all.sh`) does the copy.

## Conventions

- Every path goes through the environment: `TAPADOSPRI_DB_ROOT`, `TAPADOSPRI_DATA_DIR`, `TAPADOSPRI_OUTPUT_DIR`,
  `TAPADOS_MAIN_OUTPUT_DIR` (the analysis folder) and `TAPADOS_BENCH_DIR` (the benchmarks folder); `run_all.sh` sets them.
- The main design is fixed by `TAPADOS_TIE_CUTOFF=2` (ties formed by e−2), `TAPADOS_INCLUSION=all` and
  `TAPADOS_SUCCESSION_WEIGHTS=person` (successions weighted by the designee's followers' shares). `variant_annual.R`
  reruns the headline estimand under the switches of the robustness table.
- Seeds are fixed inside the scripts; a rebuild reproduces every number of the deck.
