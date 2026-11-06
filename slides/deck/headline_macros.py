"""The headline macros of the deck: tables/title_correction_macros.tex.

Every number is read from the saved estimates of the analysis folder; nothing is estimated here.
  MDannualEst, MDannualLo, MDannualHi, MDannualPreview   the years 1-4 average of the event study (event_study.R,
                                                         event_study_summary.csv, contrast main_window_average)
  MDannualReward, MDannualPenaltyAbs, MDannualRPdiff,    the years 1-4 averages of the reward (D) and the exact penalty (P)
  MDannualRewardShare, MDannualPenaltyShare              of reward_punishment.R (rp_event_study.csv); reward - penalty is
                                                         the gap by construction
  MDpurgePercent                                         the observed average as a share of the purge rule's average
                                                         (benchmarks, assignment_estimates.csv)
  MDnoiseVariance                                        the person-level variance component of the main window estimate
                                                         (estimate_main.R, main_result.csv, B_person)
Run after the analysis and benchmark steps:  python3 slides/deck/headline_macros.py
"""
import os
from pathlib import Path

import pandas as pd

db_root = Path(os.environ.get("TAPADOSPRI_DB_ROOT", Path.home() / "Dropbox" / "TapadosPRI"))
out_root = Path(os.environ.get("TAPADOSPRI_OUTPUT_DIR", db_root / "output")) / "slides"
analysis = Path(os.environ.get("TAPADOS_MAIN_OUTPUT_DIR", out_root / "analysis"))
bench = Path(os.environ.get("TAPADOS_BENCH_DIR", out_root / "benchmarks"))

es = pd.read_csv(analysis / "event_study_summary.csv")
annual = es.query("outcome == 'rank' and contrast == 'main_window_average'").iloc[0]
rp14 = pd.read_csv(analysis / "rp_event_study.csv").query("1 <= k <= 4").groupby("group").estimate.mean()
reward, penalty = float(rp14["D"]), float(rp14["P"])
gap = reward - penalty
assert abs(gap - annual.estimate) < 1e-6, (gap, annual.estimate)   # the exact decomposition adds up to the headline
main = pd.read_csv(analysis / "main_result.csv").iloc[0]
points = pd.read_csv(bench / "data" / "assignment_estimates.csv")
purge = points.query("scope == 'all_observed' and rule == 'purge' and contrast == 'DP' and 1 <= k <= 4").estimate.mean()
macros = {"MDannualEst": f"{annual.estimate:.2f}", "MDannualLo": f"{annual.ci_lower:.2f}", "MDannualHi": f"{annual.ci_upper:.2f}",
          "MDannualPreview": f"{annual.estimate:.1f}", "MDannualRewardShare": f"{100 * reward / gap:.0f}",
          "MDannualPenaltyShare": f"{-100 * penalty / gap:.0f}", "MDannualReward": f"{reward:.2f}",
          "MDannualPenaltyAbs": f"{abs(penalty):.2f}", "MDannualRPdiff": f"{gap:.2f}",
          "MDpurgePercent": f"{100 * annual.estimate / purge:.0f}", "MDnoiseVariance": f"{main.B_person:.2f}"}
lines = ["% title_correction_macros.tex (slides/deck/headline_macros.py): the headline numbers of the deck. Do not edit by hand."]
lines += [f"\\newcommand{{\\{k}}}{{{v}}}" for k, v in macros.items()]
(analysis / "tables").mkdir(exist_ok=True)
(analysis / "tables" / "title_correction_macros.tex").write_text("\n".join(lines) + "\n")
print("\n".join(lines[1:]))
