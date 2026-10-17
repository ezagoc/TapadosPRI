# New main result — 16 October 2026

**Estimand.** Adjusted difference in the four-year change in highest recorded career rung between politicians directly and exclusively tied to the observed designee and politicians directly and exclusively tied to an unsuccessful contender in the same succession. Each of the nine successions has equal weight. The specification was written before this outcome was calculated.

**Estimate.** **+1.147 career rungs**; simulation-calibrated approximate network-bootstrap 95% interval **[+0.323, +1.954]**; approximate bootstrap $p=0.0051$. The uncalibrated interval is [0.460, 1.819]. This is an adjusted **relative premium**. It does not distinguish a reward to the winner's followers from a penalty to the losers' followers, and it is not an ATT over alternative presidents.

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

## What supports the interval, and what does not

There are nine winning networks and 45 nonempty losing networks. Within a succession, the person-weighted controls correspond to roughly 1.9–4.9 equally weighted losing networks. The primary bootstrap resamples **both winner and loser network contributions**, correcting donor residual moments for regression leverage and allowing network variance to depend on effective network size. The fitted variance components are $\widehat A=0$ for common network shocks and $\widehat B=15.226$ for individual noise. A fixed 1.20 widening of bootstrap error quantiles was chosen from simulations on the observed network layout: in the six simulated scenarios (normal/heavy-tailed errors, larger common shocks, repeated-person correlation, and negatively related networks within a slate), empirical coverage of the widened interval ranged from 95.9% to 99.3%, with Monte Carlo standard errors of roughly 0.4–0.9 percentage points. These simulations validate the algorithm **under their assumed error structures**; they cannot establish exchangeability of winner and loser shocks in the historical setting.

The signal is sensitive to stronger unobserved common network shocks. Holding $B=15.226$, an imposed $A=0.5$ gives interval [0.090, 2.170], while $A=1$ gives [−0.064, 2.371]. The latter contains zero. These are assumption checks, not estimates of $A$. The control-network data yield $\widehat A=0$, but they cannot rule out every historically relevant shock structure. A mechanical succession-clustered interval is not used.

## Substantive limits to put in the talk

- **Exclusive followers.** The main sample omits politicians directly tied to multiple contenders. This becomes substantial late in the sample: in 1988, 131 eligible politicians have exactly one direct contender tie and 320 have multiple. The result applies to exclusive direct ties, not to all connected politicians. A separate multi-tie/spillover analysis is the next priority.
- **Recorded office.** The post outcome is zero if no ranked office is recorded in the four-year post window. This occurs for 82/287 winner followers and 276/810 loser followers. A difference in recording or exit can contribute to the rank result. Do not describe the estimate as a pure promotion effect.
- **Selection and interference.** The dedazo was endogenous. Conditional parallel trends requires that, after predetermined career and network covariates and succession effects, the designee's followers had no distinct future career momentum that would have occurred even if their patron lost. Direct loser followers may benefit indirectly from the winner or be penalized for backing a loser. Neither the regression nor the interval settles these issues.

The next design check is a pre-designation trend graph on the frozen cohort, followed by an explicit study of multi-ties and meaningful indirect paths. Do not replace this estimate with a menu of post-hoc specifications.

## Reproduction

Run `estimate_main.R` and `validate_inference.R` as described in [README.md](README.md). Machine-readable source outputs are `main_result.csv`, `succession_contrasts.csv`, `network_contributions.csv`, `sample_flow.csv`, `post_recording.csv`, `inference_calibration.csv`, and `network_variance_sensitivity.csv` in `TapadosPRI/output/main_direct_tie/` (or the directory set by `TAPADOS_MAIN_OUTPUT_DIR`).
