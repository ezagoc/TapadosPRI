#!/bin/bash
# Run the 20 estimation starts of one pool in parallel, with a memory watchdog.
# Usage: bash code/07-structural/run_parallel.sh <rule: all|predetermined> [processes, default 6] [limit GB, default 40]
# Each process peaks at about 4.4 GB (measured 19 October 2026). Before the per-cycle pullback and the checkpointing it
# peaked at 31 GB, and 17 processes exhausted a 69 GB machine. The watchdog kills every estimation process if their
# total resident memory passes the limit.
RULE=${1:-all}; NPROC=${2:-6}; LIMIT_GB=${3:-40}
HERE="$(cd "$(dirname "$0")" && pwd)"; PY=${PYTHON:-python3}
OUT="${TAPADOSPRI_DB_ROOT:-$HOME/Dropbox/TapadosPRI}/output/structural/$RULE"; mkdir -p "$OUT/logs"
export XLA_FLAGS="--xla_cpu_multi_thread_eigen=false intra_op_parallelism_threads=1"
PIDS=()
for ((p = 0; p < NPROC; p++)); do
  a=$(( p * 20 / NPROC )); b=$(( (p + 1) * 20 / NPROC - 1 ))
  "$PY" "$HERE/estimate_ii.py" --rule "$RULE" --starts "$a-$b" --maxiter 300 > "$OUT/logs/starts_$a-$b.log" 2>&1 &
  PIDS+=($!)
done
while kill -0 "${PIDS[@]}" 2>/dev/null; do
  KB=$(ps -o rss= -p "$(IFS=,; echo "${PIDS[*]}")" 2>/dev/null | awk '{s+=$1} END {print s+0}')
  if [ "$KB" -gt $(( LIMIT_GB * 1024 * 1024 )) ]; then
    echo "watchdog: $((KB / 1024 / 1024)) GB > $LIMIT_GB GB, stopping all estimation processes" | tee "$OUT/logs/WATCHDOG_STOP.txt"
    kill "${PIDS[@]}" 2>/dev/null; exit 1
  fi
  sleep 20
done
wait; echo "$RULE: all starts finished"
