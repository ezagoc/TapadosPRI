# 07-structural: Chairs and Clocks (Block A)

Specification: `research/structural_2026-10-19/MODEL_SPEC.md` (frozen, `FREEZE.txt`; four referee rounds in the same folder).

## Run order

```bash
python code/07-structural/01_death_years.py                       # death years, presidential timeline -> data/structural/
Rscript code/04-analysis/main_direct_tie/export_structural_inputs.R  # pool, ties, chairs, seats, estimator weights (unit test)
TAPADOS_INCLUSION=predetermined TAPADOS_MAIN_OUTPUT_DIR=<output>/main_direct_tie/robust_predetermined_inclusion \
  Rscript code/04-analysis/main_direct_tie/export_structural_inputs.R
bash code/07-structural/run_parallel.sh all 6 40                  # 20 starts, 6 processes, 40 GB watchdog
bash code/07-structural/run_parallel.sh predetermined 6 40
python code/07-structural/summarize.py --rule all                 # best start, fit, preliminary SEs, J, AGS
```

## Files

- `chairs_model.py`: data loader and forward-equation simulator (JAX); capacity prices by Newton with implicit derivatives.
- `moments.py`: targeted moments (families 1–3, 5–8), the same formulas for the model and the observed data.
- `objective.py`: indirect-inference criterion with analytic gradients.
- `weights.py`: preliminary diagonal weighting (until `joint_draws.R` exists).
- `estimate_ii.py`: multi-start L-BFGS-B; `summarize.py`: results.
- `stochastic.py`: exact-capacity stochastic simulator (mean-field check, recovery experiment).

## Memory

One gradient peaks at about 4.4 GB per process and takes about 10 s (measured 19 October 2026). Gradients are pulled back
one succession cycle at a time and each simulated year is rematerialized in the backward pass. Before these two changes a
process peaked at 31 GB, and 17 processes in parallel exhausted a 69 GB machine and crashed it. Keep the number of processes
times 4.4 GB well below the machine's memory; `run_parallel.sh` stops all estimation processes if their total passes its
limit.
