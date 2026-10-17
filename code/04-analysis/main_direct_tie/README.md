# Main direct-tie analysis

This is the **only active main career estimate** for the third-year paper. The design is frozen in [MAIN_SPEC.md](MAIN_SPEC.md); [RESULTS.md](RESULTS.md) summarizes the current run. Scripts and result files under the older `research/main_R/` workflow are historical and are not inputs to this estimate.

From the code repository root, with R and `data.table` installed:

```bash
Rscript code/04-analysis/main_direct_tie/estimate_main.R
Rscript code/04-analysis/main_direct_tie/validate_inference.R
```

The scripts read `TapadosPRI/data/{networks,candidates,rank}` and write CSV outputs to `TapadosPRI/output/main_direct_tie/`. Set `TAPADOSPRI_DB_ROOT` or `TAPADOSPRI_DATA_DIR` if the shared Dropbox root differs. Set `TAPADOS_MAIN_OUTPUT_DIR` to stage outputs elsewhere; for example, the private presentation workspace uses `research/main/output_primary/`.

`estimate_main.R` writes the analysis sample, cohort contrasts, candidate-network weights, sample flow, overlap and recording audits, control-model coefficients, the main estimate, and leave-one-succession-out contrasts. `validate_inference.R` adds coverage simulations and sensitivity to common network shocks. Both scripts use fixed seeds. No old result table is read.

The 95% interval is **approximate and conditional** on the network-shock assumptions spelled out in the specification. The estimate is a relative direct-tie premium for politicians tied exclusively to one contender, not an absolute ATT for making their own contender president.
