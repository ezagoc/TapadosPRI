# Main result — 16 October 2026 (inference revised 17 October 2026)

**Estimand.** Adjusted difference in the four-year change in highest recorded career rung between politicians directly and exclusively tied to the observed designee and politicians directly and exclusively tied to an unsuccessful contender in the same succession. Each of the nine successions has equal weight. The specification was written before this outcome was calculated.

**Estimate.** **+1.147 career rungs**; Ferman–Pinto network-bootstrap 95% interval **[+0.460, +1.819]**; bootstrap $p=0.0007$. This is an adjusted **relative premium**. It does not distinguish a reward to the winner's followers from a penalty to the losers' followers, and it is not an ATT over alternative presidents.

| Succession | Winner followers | Loser followers | Adjusted relative change |
|---:|---:|---:|---:|
| 1940 | 8 | 11 | +1.453 |
| 1946 | 12 | 43 | +2.803 |
| 1952 | 18 | 55 | −1.046 |
| 1958 | 15 | 82 | +2.966 |
| 1964 | 26 | 95 | +1.177 |
| 1970 | 58 | 128 | +1.352 |
| 1976 | 52 | 127 | +0.460 |
| 1982 | 75 | 161 | +0.621 |
| 1988 | 23 | 108 | +0.533 |

The analysis contains 1,097 politician-succession observations from 776 distinct politicians; 255 politicians appear in more than one succession. Eight of nine cohort contrasts are positive. With any one succession omitted, the average ranges from +0.919 to +1.421.

## Event study (17 October 2026, MAIN_SPEC section 7)

Same sample, estimator and weights, year by year relative to $e-2$; covariates without the two rank bands (they are functions of the lead-year outcome). Ferman–Pinto network-bootstrap intervals, joint over years (`event_study.csv`, `event_study_summary.csv`, figure `event_study_rank.pdf`).

| Contrast (rank, rungs) | Estimate | 95% interval | $p$ |
|---|---:|---:|---:|
| Leads, average of $e-7,\ldots,e-3$ | −0.15 | [−0.64, +0.33] | 0.55 |
| Joint lead test, max $|t|$ | 0.83 | | 0.79 |
| $e+1$ | +0.94 | [+0.18, +1.70] | 0.015 |
| Average of $e+1,\ldots,e+4$ (annual ranks) | +0.90 | [+0.08, +1.70] | 0.028 |
| Average of $e+7, e+8$ (next president) | 0.00 | [−0.77, +0.78] | 1.00 |
| $\theta_7-\theta_6$ (patron leaves office) | −0.49 | [−0.92, −0.04] | 0.029 |
| Main window $\Delta R$ with these covariates | +1.23 | [+0.46, +1.99] | 0.001 |

The leads are flat and jointly indistinguishable from zero. The gap appears at the handover (+0.41 in $e$, when the new cabinet is coded; +0.94 in $e+1$), holds at about +0.9 through $e+4$, shrinks in $e+5$ and $e+6$, and is gone under the next president; the fall when the patron leaves office is −0.49 [−0.92, −0.04]. Pointwise intervals exclude zero in $e+1$, $e+2$ and $e+4$; $e+3$ is [−0.07, +1.78]. The annual contrasts are about as noisy as the window contrast (plug-in person-level s.e. 0.32–0.35 in every version, event-study covariates) but smaller. Measured from the rank held in $e-2$ instead of the best rank in $e-5,\ldots,e-2$, the window contrast falls from +1.23 to +1.00: the designee's followers were slightly closer to their pre-window peak in $e-2$ (84% hold a recorded post in $e-2$, against 80% of the losers' followers), the same small difference the leads show. Averaging the annual ranks of $e+1,\ldots,e+4$ instead of taking their maximum lowers it by another 0.10.

Extensive margin (holds any ranked post): leads −5 pp [−14, +4]; $e+1,\ldots,e+4$ +7 pp [−5, +18]; main window +10 pp [−2, +21], $p=0.09$. A gap in office holding is not detected, but its point estimate is large enough that about half of the rung premium could come from the zero coding of no recorded post.

## Margins of the premium (17 October 2026, MAIN_SPEC section 8)

| Window contrast | Estimate | 95% interval | $p$ |
|---|---:|---:|---:|
| Rank, 0 if no recorded post (rungs) | +1.15 | [+0.46, +1.82] | 0.001 |
| Holds a ranked post (percentage points) | +10.2 | [−1.9, +22.0] | 0.10 |
| Rank if in office before and after (rungs; 739 politicians) | +0.58 | [+0.21, +0.95] | 0.002 |
| Lee bounds for selection into office | [−0.03, +1.23] | | |

About half of the rank premium is promotion among those who stay in office; the office margin is +10 points but imprecise. The year-by-year event study of rank among those in office is noisy because the group in office changes every year (`margins_event_study.csv`); the window contrast is the one to quote.

## Federal investment commanded (17 October 2026, MAIN_SPEC section 9)

After designation 11.1% of the designee's followers head an agency with federal investment, against 3.2% of the losers' followers (5.9% and 5.6% before). Heads an investment agency: +7.7 points [+2.6, +12.8], $p=0.003$. Percent of federal investment commanded: +0.34 points [+0.02, +0.69], $p=0.05$. Event study: flat before designation, +0.32 and +0.33 points in $e+1$ and $e+2$, about zero afterwards (`budget_event_study.csv`). Heading an investment agency, by year: +7 points in $e$, +8 to +9 in $e+1,\ldots,e+4$, +5 in $e+5$ and $e+6$, zero in $e+7$: the investment edge ends after $e+2$ while the posts are kept. The outcome moves with both the post and the agency's budget; it does not hold the office fixed. 572 of 1,577 head-of-agency records resolve to an agency of the investment panel (`budget_crosswalk_audit.csv`).

## Appendix diagnostics (17 October 2026, MAIN_SPEC section 10)

- **Balance.** Fourteen predetermined traits; largest standardized difference 0.18 (military career), smallest bootstrap $p$ 0.25 (`balance.csv`).
- **Robustness of the main estimate** (`robustness.csv`): successions weighted by the designee's followers 0.92 [0.37, 1.45]; succession indicators only 1.20 [0.13, 2.26]; without rank bands 1.23 [0.46, 1.99]; exact baseline rung 1.02 [0.35, 1.67]; ties dated by $e-4$ 1.10 [0.32, 1.86] (962 politician-successions). Without 1976 and 1988, when the outgoing president leaned toward the designee years ahead (Castañeda 1999), 1.33 [0.50, 2.14]; without Díaz Serrano's group in 1982, 1.15 [0.39, 1.89]. Share above a rung: rung 7 or above +20.5 points [12.3, 28.4], rung 5 or above +6.9 [3.0, 10.7], rung 4 or above +5.9 [0.7, 11.0].
- **Anticipation.** Designees formed more ties than losing contenders in $e-4$ and $e-3$, driven by 1976 (López Portillo, Finance 1973) and 1982 (de la Madrid, Programming and Budget 1979); the $e-4$ cutoff above removes those recruits (`anticipation_ties.csv`).
- **Losing teams vs random regroupings.** Between-team variation of residual changes among losers' followers equals that of random teams of the same sizes (permutation $p=0.42$, `camps_permutation.csv`).
- **Coverage** of the interval in simulations: 92.7% to 97.0% (`inference_coverage.csv`).

## Reward and punishment against unaligned politicians (18 October 2026, MAIN_SPEC section 11)

Designee's followers ($D$) and losers' followers ($P$) each against one group of politicians tied to no contender ($N$), trimmed to the followers' support (2,954 of 4,754 kept) and entropy-balanced within succession to the followers' means (exact balance on all twelve traits; effective sample 52–170 per succession), with the §4 regression on top.

| Specification | $D-N$ (reward) | $P-N$ (penalty) |
|---|---:|---:|
| Main | +0.80 [+0.23, +1.34] | −0.29 [−0.56, −0.01] |
| (a) Without baseline-rank bands | +0.73 [+0.10, +1.34] | −0.49 [−0.78, −0.21] |
| (b) All groups trimmed to propensity 0.1–0.9 | +1.00 [+0.47, +1.52] | −0.14 [−0.43, +0.14] |
| (c) Without unaligned two strong steps from the designee | +0.98 [+0.38, +1.54] | −0.11 [−0.43, +0.21] |
| (d) Within politician (politician and succession FE, 601 switchers) | +1.20 [+0.62, +1.77] | −0.15 [−0.46, +0.15] |

The reward is +0.7 to +1.2 rungs in every specification. The penalty is small (−0.1 to −0.5), significant only in the main and (a), and temporary: in the event study (`rp_event_study.csv`, `es_reward_punishment.pdf`) the losers' followers dip by 0.24–0.34 rungs from $e$ to $e+4$ and are back at zero by $e+5$; their leads are flat. The designee's followers' leads are slightly negative (−0.37 to +0.03), the source of the small pre-designation gap in the main event study. With every tie, 65% of the comparable unaligned are two steps from the designee; with strong ties, 17%. Reading: $P-N$ is the penalty aimed at a loser's followers beyond what any unaligned politician bears; neither contrast is an absolute effect. Decomposition (`rp_decomposition.csv`, joint draws): reward minus penalty 1.09 [0.54, 1.63] against the §4 estimate 1.15; reward share 74% [37%, 99%], 60% to 90% across specifications.

## What supports the interval, and what does not

There are nine winning networks and 45 nonempty losing networks. Within a succession, the person-weighted controls correspond to roughly 1.9–4.9 equally weighted losing networks. The primary bootstrap resamples **both winner and loser network contributions**, correcting donor residual moments for regression leverage and allowing network variance to depend on effective network size. The fitted variance components are $\widehat A=0$ for common network shocks and $\widehat B=15.226$ for individual noise, and the interval plugs them in as Ferman and Pinto (2019) do, with no inflation factor (the 1.20 widening of the 16 October run was dropped on 17 October). In six simulated scenarios on the observed network layout (`inference_coverage.csv`), its coverage is 96.8% without network shocks, 97.0% with repeated-person correlation, 94.3% with a common network shock $A=1$, and 92.7–93.5% with $A=2$ under normal, heavy-tailed and negatively related networks (Monte Carlo s.e. 0.6–1.2 percentage points). These simulations validate the algorithm **under their assumed error structures**; they cannot establish exchangeability of winner and loser shocks in the historical setting.

Holding $B=15.226$, an imposed $A=0.5$ gives interval [0.266, 1.999], $A=1$ gives [0.138, 2.167], and $A=2$ gives [−0.110, 2.407]. These are assumption checks, not estimates of $A$. The control-network data yield $\widehat A=0$, but they cannot rule out every historically relevant shock structure. A mechanical succession-clustered interval is not used.

## Substantive limits to put in the talk

- **Exclusive followers.** The main sample omits politicians directly tied to multiple contenders. This becomes substantial late in the sample: in 1988, 131 eligible politicians have exactly one direct contender tie and 320 have multiple. The result applies to exclusive direct ties, not to all connected politicians. A separate multi-tie/spillover analysis is the next priority.
- **Recorded office.** The post outcome is zero if no ranked office is recorded in the four-year post window. This occurs for 82/287 winner followers and 276/810 loser followers. A difference in recording or exit can contribute to the rank result. Do not describe the estimate as a pure promotion effect.
- **Selection and interference.** The dedazo was endogenous. Conditional parallel trends requires that, after predetermined career and network covariates and succession effects, the designee's followers had no distinct future career momentum that would have occurred even if their patron lost. Direct loser followers may benefit indirectly from the winner or be penalized for backing a loser. Neither the regression nor the interval settles these issues.

The pre-designation trend check is the event study above; the next design check is an explicit study of multi-ties and meaningful indirect paths. Do not replace this estimate with a menu of post-hoc specifications.

## Reproduction

Run the scripts in the order given in [README.md](README.md). Machine-readable source outputs are `main_result.csv`, `succession_contrasts.csv`, `network_contributions.csv`, `sample_flow.csv`, `post_recording.csv`, `inference_coverage.csv`, `network_variance_sensitivity.csv`, and the `event_study*.csv` tables in `TapadosPRI/output/main_direct_tie/` (or the directory set by `TAPADOS_MAIN_OUTPUT_DIR`).
