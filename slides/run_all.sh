#!/usr/bin/env bash
# Rebuild every figure, table and number of the deck (research/slides/3rdYearPresentation/main.tex) from the shared data.
#
#   bash slides/run_all.sh              run every step in order (about two hours; the log of each step goes to
#                                       TapadosPRI/output/slides/logs/<step>.log)
#   bash slides/run_all.sh STEP ...     run only the named steps, e.g. `bash slides/run_all.sh rp_thresholds collect`
#   bash slides/run_all.sh --list       print the steps
#
# Data are read from TapadosPRI/data (TAPADOSPRI_DB_ROOT in .env, see README.md) and every output is written under
# TapadosPRI/output/slides: analysis/ (estimates, figures, tables/), benchmarks/ (the allocation rules), descriptives/,
# deck/ (the files the deck reads, under their deck names) and logs/. The last step copies the deck files into the
# Overleaf repository. Nothing under TapadosPRI/data is rewritten except by the three data steps at the top.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"      # TapadosCode
SLIDES="$ROOT/slides"
if [ -f "$ROOT/.env" ]; then set -a; . "$ROOT/.env"; set +a; fi
export TAPADOSPRI_DB_ROOT="${TAPADOSPRI_DB_ROOT:-$HOME/Dropbox/TapadosPRI}"
export TAPADOSPRI_DATA_DIR="${TAPADOSPRI_DATA_DIR:-$TAPADOSPRI_DB_ROOT/data}"
export TAPADOSPRI_OUTPUT_DIR="${TAPADOSPRI_OUTPUT_DIR:-$TAPADOSPRI_DB_ROOT/output}"
OUT="$TAPADOSPRI_OUTPUT_DIR/slides"
export TAPADOS_MAIN_OUTPUT_DIR="$OUT/analysis"          # estimates, figures and tables/ of slides/analysis
export TAPADOS_BENCH_DIR="$OUT/benchmarks"              # the allocation-rule benchmarks (slides/benchmarks)
export TAPADOS_TIE_CUTOFF=2 TAPADOS_INCLUSION=all TAPADOS_SUCCESSION_WEIGHTS=person   # the main design (MAIN_SPEC.md)
export MPLCONFIGDIR="${MPLCONFIGDIR:-${TMPDIR:-/tmp}/tapados_mpl}"
PY="${PYTHON:-python3}"
mkdir -p "$OUT/analysis" "$OUT/benchmarks" "$OUT/descriptives" "$OUT/deck" "$OUT/logs"

# step name | command (run from the repository root)
STEPS=(
  # ---- data (TapadosPRI/data): death years, the eligibility rule's verified deaths, the office scale
  "death_years|$PY $SLIDES/data/death_years.py"
  "verified_deaths|$PY $SLIDES/data/verified_deaths.py"
  "position_tiers|$PY -B $ROOT/code/02-rank/02_position_tiers.py"
  # ---- the main design (slides/analysis); estimate_main.R is sourced by each script
  "event_study|Rscript $SLIDES/analysis/event_study.R"
  "margins|Rscript $SLIDES/analysis/margins.R"
  "reward_punishment|Rscript $SLIDES/analysis/reward_punishment.R"
  "variant_ties_e4|env TAPADOS_TIE_CUTOFF=4 TAPADOS_MAIN_OUTPUT_DIR=$OUT/analysis/robust_ties_e4 Rscript $SLIDES/analysis/variant_annual.R"
  "variant_inclusion|env TAPADOS_INCLUSION=predetermined TAPADOS_MAIN_OUTPUT_DIR=$OUT/analysis/robust_predetermined_inclusion Rscript $SLIDES/analysis/variant_annual.R"
  "budget_outcome|Rscript $SLIDES/analysis/budget_outcome.R"
  "validate_inference|Rscript $SLIDES/analysis/validate_inference.R"
  "appendix_diagnostics|Rscript $SLIDES/analysis/appendix_diagnostics.R"
  "indirect_ties|Rscript $SLIDES/analysis/indirect_ties.R"
  "rp_raw_trajectories|Rscript $SLIDES/analysis/rp_raw_trajectories.R"
  "figures_deck|Rscript $SLIDES/analysis/figures_deck.R"
  "rp_office|Rscript $SLIDES/analysis/rp_office.R"
  "pay_envelope|Rscript $SLIDES/analysis/pay_envelope.R"
  "ladder_shares|Rscript $SLIDES/analysis/ladder_shares.R"
  "balance_combined|Rscript $SLIDES/analysis/balance_combined.R"
  "randomization_inference|Rscript $SLIDES/analysis/randomization_inference.R"
  # ---- the allocation rules (slides/benchmarks)
  "benchmark_calendar|Rscript $SLIDES/benchmarks/prepare_calendar.R"
  "benchmark_assignments|$PY $SLIDES/benchmarks/assignments.py"
  "benchmark_inference|Rscript $SLIDES/benchmarks/inference.R"
  "benchmark_figures|$PY -c \"import sys; sys.path.insert(0, '$SLIDES/benchmarks'); import figures; figures.validate_and_export(); figures.figures()\""
  "rules_table|Rscript $SLIDES/analysis/rules_table.R"
  # ---- the rest of the results slides
  "first_stage|Rscript $SLIDES/analysis/first_stage.R"
  "first_stage_rp|Rscript $SLIDES/analysis/first_stage_rp.R"
  "rp_thresholds|Rscript $SLIDES/analysis/rp_thresholds.R"
  "runner_up|Rscript $SLIDES/analysis/runner_up.R"
  "by_succession_forest|Rscript $SLIDES/analysis/by_succession_forest.R"
  "post_holders|Rscript $SLIDES/analysis/post_holders.R"
  "aspirants_table|Rscript $SLIDES/analysis/aspirants_table.R"
  "loser_careers|$PY $SLIDES/analysis/loser_careers.py"
  "followers_1946|$PY $SLIDES/analysis/followers_table_1946.py"
  "heterogeneity|Rscript $SLIDES/analysis/heterogeneity.R"
  "het_ties|Rscript $SLIDES/analysis/het_ties_figure.R"
  # ---- deck tables and headline macros (slides/deck)
  "by_succession_table|$PY $SLIDES/deck/build_by_succession_table.py --analysis-dir $OUT/analysis"
  "sample_table|$PY $SLIDES/deck/build_rank_description.py --data-root $TAPADOSPRI_DB_ROOT --analysis-dir $OUT/analysis"
  "pay_table|$PY $SLIDES/deck/build_pay_table.py --data-root $TAPADOSPRI_DB_ROOT"
  "headline_macros|$PY $SLIDES/deck/headline_macros.py"
  # ---- descriptive figures (slides/descriptives)
  "descriptives|$PY -I $SLIDES/descriptives/viz_appendix_descriptives.py"
  "bio_links_1946|$PY $SLIDES/descriptives/bio_links_1946.py"
  "investment_series|$PY $SLIDES/descriptives/plot_agency_series.py"
  "autocracy_tables|Rscript $SLIDES/descriptives/autocracy/01_build_tables.R"
  "autocracy_extension|Rscript $SLIDES/descriptives/autocracy/03_extend_to_2025.R"
  "autocracy_figure|Rscript $SLIDES/descriptives/autocracy/06_successions_survival.R"
  # ---- copy the deck's files to output/slides/deck and to the Overleaf repository
  "collect|$PY $SLIDES/deck/collect_deck_files.py"
)
if [ "${1:-}" = "--list" ]; then for s in "${STEPS[@]}"; do echo "${s%%|*}"; done; exit 0; fi
only=("$@")
cd "$ROOT"
for s in "${STEPS[@]}"; do
  name="${s%%|*}"; cmd="${s#*|}"
  if [ ${#only[@]} -gt 0 ]; then keep=0; for o in "${only[@]}"; do [ "$o" = "$name" ] && keep=1; done; [ $keep -eq 1 ] || continue; fi
  printf '%s  START %s\n' "$(date +%H:%M:%S)" "$name"
  if ! bash -c "$cmd" > "$OUT/logs/$name.log" 2>&1; then
    printf '%s  FAILED %s (see %s)\n' "$(date +%H:%M:%S)" "$name" "$OUT/logs/$name.log"; tail -20 "$OUT/logs/$name.log"; exit 1
  fi
  printf '%s  DONE  %s\n' "$(date +%H:%M:%S)" "$name"
done
echo "all steps done"
