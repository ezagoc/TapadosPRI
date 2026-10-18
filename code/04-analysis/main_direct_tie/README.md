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
TAPADOS_TIE_CUTOFF=4 TAPADOS_MAIN_OUTPUT_DIR="$HOME/Dropbox/TapadosPRI/output/main_direct_tie/robust_ties_e4" \
  Rscript code/04-analysis/main_direct_tie/estimate_main.R
Rscript code/04-analysis/main_direct_tie/appendix_diagnostics.R
```

The scripts read `TapadosPRI/data/{networks,candidates,rank}` and write CSV outputs to `TapadosPRI/output/main_direct_tie/`. Set `TAPADOSPRI_DB_ROOT` or `TAPADOSPRI_DATA_DIR` if the shared Dropbox root differs. Set `TAPADOS_MAIN_OUTPUT_DIR` to stage outputs elsewhere; for example, the private presentation workspace uses `research/main/output_primary/`.

`estimate_main.R` writes the analysis sample, cohort contrasts, candidate-network weights, sample flow, overlap and recording audits, control-model coefficients, the main estimate, and leave-one-succession-out contrasts. `validate_inference.R` adds coverage simulations and sensitivity to common network shocks. `event_study.R` (MAIN_SPEC section 7) applies the same estimator year by year, e−7 to e+8 relative to e−2, for rank and for holding any ranked post, with a joint network bootstrap; it writes `event_study*.csv` and `event_study_{rank,any_post}.{pdf,png}`. `design_tools.R` (sourced, not run) holds the estimator on any subsample, covariate set and succession weights, the joint contender-level bootstrap and the figure style. `margins.R` (MAIN_SPEC section 8) splits the premium into holding a ranked post and rank among those in office, with Lee bounds. `budget_outcome.R` (section 9) builds the share of federal investment commanded by the agency a politician heads and runs the same design. `reward_punishment.R` (section 11) compares the designee's and the losers' followers with one reweighted group of unaligned politicians (common support, entropy balancing, regression), with the decomposition of the premium into reward and penalty, its robustness and the deck's `rp_*` tables and macros. `appendix_diagnostics.R` (section 10) writes the balance, robustness, by-succession, coverage, anticipation and losing-team diagnostics, the deck's tables (`tables/*.tex`) and `tables/main_direct_tie_macros.tex`, which holds every number quoted on the empirical slides. All scripts use fixed seeds. No old result table is read.

The 95% interval is **approximate and conditional** on the network-shock assumptions spelled out in the specification. The estimate is a relative direct-tie premium for politicians tied exclusively to one contender, not an absolute ATT for making their own contender president.
