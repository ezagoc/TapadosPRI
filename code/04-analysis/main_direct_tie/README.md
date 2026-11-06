# Main direct-tie analysis

This is the **only active main career estimate** for the third-year paper. The design is frozen in [MAIN_SPEC.md](MAIN_SPEC.md); [RESULTS.md](RESULTS.md) summarizes the current run. Scripts and result files under the older `research/main_R/` workflow are historical and are not inputs to this estimate.

From the code repository root, with R and `data.table` installed:

```bash
Rscript code/04-analysis/main_direct_tie/estimate_main.R
Rscript code/04-analysis/main_direct_tie/validate_inference.R
Rscript code/04-analysis/main_direct_tie/event_study.R
Rscript code/04-analysis/main_direct_tie/margins.R
Rscript code/04-analysis/main_direct_tie/budget_outcome.R
Rscript code/04-analysis/main_direct_tie/reward_punishment.R
Rscript code/04-analysis/main_direct_tie/chair_split.R
for s in estimate_main event_study margins reward_punishment chair_split; do
  TAPADOS_INCLUSION=predetermined TAPADOS_MAIN_OUTPUT_DIR="$HOME/Dropbox/TapadosPRI/output/main_direct_tie/robust_predetermined_inclusion" \
    Rscript code/04-analysis/main_direct_tie/$s.R; done
TAPADOS_TIE_CUTOFF=4 TAPADOS_MAIN_OUTPUT_DIR="$HOME/Dropbox/TapadosPRI/output/main_direct_tie/robust_ties_e4" \
  Rscript code/04-analysis/main_direct_tie/estimate_main.R
Rscript code/04-analysis/main_direct_tie/appendix_diagnostics.R
Rscript code/04-analysis/main_direct_tie/figures.R
```

The scripts read `TapadosPRI/data/{networks,candidates,rank}` and write CSV outputs to `TapadosPRI/output/main_direct_tie/`. Set `TAPADOSPRI_DB_ROOT` or `TAPADOSPRI_DATA_DIR` if the shared Dropbox root differs. Set `TAPADOS_MAIN_OUTPUT_DIR` to stage outputs elsewhere; for example, the private presentation workspace uses `research/main/output_primary/`.

`estimate_main.R` writes the analysis sample, cohort contrasts, candidate-network weights, sample flow, overlap and recording audits, control-model coefficients, the main estimate, and leave-one-succession-out contrasts. `validate_inference.R` adds coverage simulations and sensitivity to common network shocks. `event_study.R` (MAIN_SPEC section 7) applies the same estimator year by year, e−7 to e+8 relative to e−2, for rank and for holding any ranked post, with a joint network bootstrap; it writes `event_study*.csv` and `event_study_{rank,any_post}.{pdf,png}`. `design_tools.R` (sourced, not run) holds the estimator on any subsample, covariate set and succession weights, the joint contender-level bootstrap and the figure style. `margins.R` (MAIN_SPEC section 8) splits the premium into holding a ranked post and rank among those in office, with Lee bounds. `budget_outcome.R` (section 9) builds the share of federal investment commanded by the agency a politician heads and runs the same design. `reward_punishment.R` (section 11) compares the designee's and the losers' followers with one reweighted group of unaligned politicians (common support, entropy balancing, regression), with the decomposition of the premium into reward and penalty, its robustness and the deck's `rp_*` tables and macros. Its groups, entropy balancing and linear estimator live in `rp_setup.R` (sourced, not run). `chair_split.R` (section 12) splits the losers' followers by whether their patron kept a top chair after the succession. `appendix_diagnostics.R` (section 10) writes the balance, robustness, by-succession, coverage, anticipation and losing-team diagnostics, the deck's tables (`tables/*.tex`) and `tables/main_direct_tie_macros.tex`, which holds every number quoted on the empirical slides. `figures.R` draws every slide figure from those CSVs (no estimation), so labels and style can change without rerunning the estimates. All scripts use fixed seeds. No old result table is read.

Added 19--20 October 2026 (run after the scripts above; each sources `estimate_main.R` and `design_tools.R` unless noted and writes CSVs, a LaTeX table and a macros file under `output/main_direct_tie/` and its `tables/`):

```bash
Rscript code/04-analysis/main_direct_tie/balance_table.R      # balance of 19 predetermined traits with normalized differences and a joint permutation test (deck table md_balance_main)
Rscript code/04-analysis/main_direct_tie/placebos.R           # timing placebo (event moved to e+s) and designee placebo (randomization over the slates)
Rscript code/04-analysis/main_direct_tie/randomization_inference.R   # randomization inference for the years 1-4 average: designee reassigned within each slate (all combinations) and followers reassigned within each succession; figure + tables/randomization_macros.tex
Rscript code/04-analysis/main_direct_tie/indirect_ties.R      # followers' followers: two steps from the contender, all and strong ties
Rscript code/04-analysis/main_direct_tie/heterogeneity.R      # the main contrast by subgroup (period, tie age and type, career, rung, age, ...)
Rscript code/04-analysis/main_direct_tie/loser_destinations.R # the 47 losing contenders' posts in e+1..e+3
Rscript code/04-analysis/main_direct_tie/export_structural_inputs.R && Rscript code/04-analysis/main_direct_tie/transitions.R   # groups at e and ties to the next slate
Rscript code/04-analysis/main_direct_tie/camp_persistence.R   # the next designee's camp by its standing at e-2 (reads transitions.R inputs)
Rscript code/04-analysis/main_direct_tie/cooptation_tests.R   # which losers keep a top chair (MAIN_SPEC 15)
Rscript code/04-analysis/main_direct_tie/pay_envelope.R       # what a rung pays: official salaries 1927 and 1999 (reads data/rank/official_pay_real.csv)
Rscript code/04-analysis/main_direct_tie/investment_heads.R   # who runs the investment agencies by group, before and after each succession
Rscript code/04-analysis/main_direct_tie/deck_descriptives.R  # the deck's descriptive tables and desc_macros.tex (losers, chair split, transitions)
Rscript code/04-analysis/main_direct_tie/figures.R            # every slide figure, incl. thresholds, heterogeneity_deck, transitions
```

The deck (`research/slides/pri_succession_slides/main.tex`) inputs the macros files (`*_macros.tex`) and the `md_*` copies of the tables and figures; every number on a slide comes from one of them.

The 95% interval is **approximate and conditional** on the network-shock assumptions spelled out in the specification. The estimate is a relative direct-tie premium for politicians tied exclusively to one contender, not an absolute ATT for making their own contender president.
