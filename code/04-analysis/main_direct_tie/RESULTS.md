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

**Status (18 October 2026): not used in the deck.** The investment-commanded estimate is driven by one politician: Enrique Estrada Reynoso (designee's follower, 1940), director of National Railways in 1941–42 when it executed 23% of federal investment, contributes 0.33 of the 0.34; without him 0.02; with person weights 0.09. Heading an investment agency (+7.7 points, positive in 7 of 9 successions) is the robust part, but the user dropped the investment results from the deck until a better use of the agency data is found. Descriptive checks (share of investment run by each camp; presence in state enterprises) are in `research/_explore_2026-10-18/` and show no money advantage for the winner's camp.

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

## The patron's chair (19 October 2026, MAIN_SPEC section 12)

Losers' followers split by their patron's highest rung in $e+1,\ldots,e+2$: kept a top chair (rung 8 or above; 9 patrons, 216 followers, in 1952, 1958, 1976 and 1988) or lost it (36 patrons with followers, 594 followers). Same reweighted unaligned as §11. Cluster-robust and wild score (Webb) intervals coincide.

| Specification | Patron kept a top chair | Patron lost it | Kept − lost, within succession |
|---|---:|---:|---:|
| Main | +0.33 [−0.04, +0.69] | −0.42 [−0.73, −0.11] | **+0.62 [+0.16, +1.08]**, wild p .005 |
| (b) Chair over $e+1,\ldots,e+3$ | +0.29 [−0.07, +0.65] | −0.42 [−0.76, −0.09] | +0.60 [+0.08, +1.11] |
| (c) Without 1952 / 1958 / 1976 / 1988 | +0.41 / +0.36 / +0.36 / +0.17 | −0.42 / −0.38 / −0.52 / −0.43 | +0.67 / +0.52 / +0.87 / +0.44 [−0.16, +1.04] |
| (a) Top chair = rung 9, as specified | −0.99 [−1.39, −0.58] | −0.38 [−0.68, −0.09] | −0.78 [−1.22, −0.33] |
| (a) without 1952 (diagnostic, not prespecified) | +0.43 [+0.03, +0.82] | −0.43 [−0.75, −0.11] | +0.72 [+0.24, +1.20] |
| (a) followers weighted equally (diagnostic, not prespecified) | +0.36 [−0.05, +0.76] | −0.35 [−0.64, −0.05] | +0.51 [+0.09, +0.92] |

Robustness (a) reverses because at the cabinet threshold the 1952 "kept" group is a single follower (of Bermúdez, −5.2 rungs against the unaligned), who carries a quarter of the equal-succession weight; without 1952 or with follower weights it agrees with the main estimate. By the patron's post in $e+1,\ldots,e+2$ (followers weighted, residuals against the unaligned): cabinet level +0.36 (6 patrons), rung 8 +0.18 (3), no ranked post −0.37 (27), demoted to rungs 1–7 −0.69 (9).

Event study (`chair_split_event_study.csv`, `es_chair_split.pdf`): followers of losers who lost the chair fall by about half a rung in $e+1,\ldots,e+4$ and recover by $e+7$; followers of losers who kept it stay at 0 to +0.27. The kept − lost contrast is +0.72 to +1.06 from $e+1$ on, with leads of +0.15, 0.00 and −0.23 in $e-5,\ldots,e-3$, but +0.56 [+0.10, +1.03] in $e-7$ and −0.22 in $e-1$: followers of losers who would lose the chair were rising in $e-7,\ldots,e-2$ (their patrons rising as contenders), so part of their later fall may be a reversal. Selection: the followers' traits are balanced between the two groups (largest standardized difference 0.20); the patrons who kept a chair were more often in the cabinet at $e-2$ (78% vs 68%), younger (50 vs 54) and had more followers (24 vs 16).

Reading: the losers' followers' penalty is concentrated where the patron lost his chair; where he kept one there is none. The new president chooses which losers keep a chair, so this is the moment the structural model must match conditional on that choice, not a causal effect of the chair.

## Predetermined inclusion in the dictionary (19 October 2026, MAIN_SPEC section 13)

Pool restricted to politicians with a dictionary-qualifying post started by $e-2$ (rung 7 or above, national opposition
leadership, UNAM/IPN rector or major school director). The sample halves: 121 designee's followers (of 287), 402 losers'
followers (of 810), 1,290 unaligned in support (of 2,954). Outputs in `output/main_direct_tie/robust_predetermined_inclusion/`.

| Estimate | Full pool | Predetermined inclusion |
|---|---:|---:|
| Main window premium (§4–5) | 1.15 [0.46, 1.82] | **0.84 [−0.18, 1.82]** |
| Event study $e+1$ / $e+2$ / $e+3$ / $e+4$ (§7) | 0.94 / 0.92 / 0.87 / 0.85 | 0.94 / 0.53 / 0.30 / 0.29 |
| Holds a ranked post (§8, extensive) | +0.10 [−0.02, 0.22] | +0.11 [−0.05, 0.27] |
| Rank among those in office (§8, intensive) | +0.58 [0.21, 0.95] | +0.01 [−0.83, 0.85] |
| Reward, designee's followers − unaligned (§11) | +0.80 [0.23, 1.34] | +0.76 [−0.06, 1.54] |
| Penalty, losers' followers − unaligned (§11) | −0.29 [−0.56, −0.01] | −0.04 [−0.44, 0.37] |
| Losers' followers, patron kept / lost a top chair (§12) | +0.33 / −0.42 | +0.32 / −0.17 |
| Kept − lost, within succession (§12) | +0.62 [0.16, 1.08] | +0.43 [−0.37, 1.22] |

The annual margins event study did not run on this pool (the control model is rank-deficient in some years); the window
margins did. Reading (fixed in §13 before computing): the reward to the designee's followers has the same size among
politicians already in the dictionary by $e-2$, and the first-year jump is identical (0.94); what shrinks is the penalty to
the losers' followers (to zero), the persistence after $e+1$ and the rank premium among those in office. The two explanations
fixed in advance cannot be separated: selection into the dictionary, or a smaller rank premium for politicians already at
rung 7 or above, who have little room left (the access margin is unchanged, the rank margin vanishes). The main premium is
27% smaller and no longer significant with half the sample. Both pools are reported with equal prominence.

## Co-optation and credentials (19 October 2026, MAIN_SPEC sections 15-16)

**§15, co-optation (gate passed, weakly).** Within the four successions in which some loser kept a top chair, the kept losers
had larger camps: exact one-sided p = 0.041 (21,000 within-succession permutations; threat = standardized log(1 + camp)).
Secondary: no loser who was a general kept a top chair (p = 1.0); governors in camp p = 0.15; with seniority, age and
runner-up controls the camp coefficient is 1.30 (s.e. 1.04, p = 0.21). Co-optation by opposition-entry regime shows no
pattern (easy 1 of 3 successions, intermediate 1 of 2, hard 2 of 4). Retention of large-camp losers is consistent with both
co-opting threats and keeping the most useful (senior) losers.

**§16, credentials (no selection cost).** The §4 premium is the same for followers with and without a graduate degree by
$e-2$ (1.16 [0.06, 2.30] vs 1.15 [0.40, 1.90]; contrast −0.01 [−1.39, 1.35]), with and without a technical field (contrast
+0.03 [−1.43, 1.50]); smaller but imprecise for foreign graduate degrees (0.47 vs 1.13; contrast +0.66 [−0.93, 2.15]). Among
top-post holders in $e+1..e+4$, 29% of the designee's followers and 24% of the other holders had a graduate degree (20% among
the holders of $e-5..e-2$). By the reading fixed in §16, the succession bargain had no selection cost in these measures.

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

## Additions of 20 October 2026 (after the coauthor meeting; numbers on the current data, main 1.03 [0.31, 1.75])

- **Balance** (`balance_table.R`, `balance_main.csv`): 19 predetermined traits, largest normalized difference 0.16 (military career), mean 0.07, smallest bootstrap p 0.23; pre-trend (change in highest rung from e−9..e−6 to e−5..e−2) −0.14 [−0.66, 0.37], p 0.59; joint test F 3.49, permutation p 0.29 (5,000 relabellings of the designee among the contenders' groups within succession).
- **Timing placebo** (`placebos.R`, `placebo_timing.csv`): the main contrast with the event moved to e+s, s = −8..+8 (event-study covariates): 0.17, 0.17, 0.03 at s = −8, −7, −6 (joint p 0.83); rising through the overlap to 1.19 at s = 0; 0.06 at +4; −0.63 [−1.27, 0.01] at +6 and −0.75 at +8 (the premium reverses as the patron leaves).
- **Designee placebo** (`placebo_designee.csv`): every losing contender relabelled as designee, one per succession; pooled estimate at or above 1.03 in 0.0006 of the 7.7 million combinations (one-sided; 20,000 sampled: 0.0004); the actual designee's camp ranks first in 5 of 9 slates; 7 of 54 contenders' camps exceed 1.03 individually (Beteta 1952, Miranda Fonseca 1964, Bracamontes 1976 among the losers).
- **Followers' followers** (`indirect_ties.R`): unaligned politicians tied by e−2 to followers of one camp only. D2 − P2: all ties −0.47 [−1.30, 0.35] (229 vs 607); strong ties (focus ≤ 10 at both steps) −0.62 [−1.78, 0.38] (151 vs 426); without the single 1940 politician on the designee's side +0.04 [−0.85, 0.88] and +0.09 [−0.59, 0.77]. Against the unaligned: designee's side −0.26 [−1.24, 0.54], losers' side +0.22 [−0.13, 0.55]. Event study flat. 51% of the unaligned pool is within two steps of some camp with any tie, 17% with strong ties.
- **Camps across successions** (`camp_persistence.R`): of the next designee's exclusive followers at e+4, 5% [1, 11] were the sitting president's followers at e−2 (next losers' benchmark 4%), 9% a loser's, 9% tied to several, 45% unaligned, 32% not yet in the pool; Jaccard 4%; 5 of 8 next designees were themselves tied to the sitting president by e−2 (Díaz Ordaz → Echeverría, 26%, the one camp that passed on).
- **Heterogeneity** (`heterogeneity.R`, 17 splits): no subgroup contrast distinguishable from zero. Period 1.33 / 0.64 / 0.52 (1940–58, 1964–76, 1982–88), trend −0.22 rungs a decade [−0.78, 0.34]; co-work tie within 8 years of e−2 1.49 [0.49, 2.47] vs 0.32 for older ties (contrast 1.18 [−1.00, 3.25], same sign 5 of 6); co-education-only ties −0.25 vs co-work 1.00 (fragile: −0.49 with the loser model held fixed); career, rung, age, UNAM, ties, posts, prior pool all within ±0.6. Composition drift: economists among the designee's followers 0% (1940) to 42% (1988).
- **What a rung pays** (`pay_envelope.R`, `pay_ladder.csv`): official pay rises 26% (1927) to 34% (1999) per rung on average from department head to cabinet secretary; cabinet/department head 4.0 (1927) vs 5.8 (1999); at the designee's followers' posts (median: deputy director general) one rung is +34% (median) or about 40 thousand 2025 pesos a month; 1.03 rungs ≈ +35% of pay, 41 thousand pesos a month (about 2,100 USD at 19 pesos per dollar); the undersecretary-to-cabinet step is +8% in pay.
- **Deck**: 18 main slides (motivation, survival, this paper, dedazo, 1946 × 2, data, sample, estimand, identification, balance, event study, thresholds, reward/penalty, heterogeneity, losers, posts not pesos, conclusion); appendix with placebos, two steps, persistence, heterogeneity table, pay ladder, slate formation and the earlier material.
- **Who ran the money** (`investment_heads.R`; crosswalk extended in `budget_outcome.R`, see its comments): share of federal investment by the agency head's group, average of the nine successions, e−5..e−2 → e+1..e+4: designee's followers 1.4 → 3.3%; losers' followers 9.4 → 6.9; tied to several 6.8 → 8.9; unaligned in the pool 33.6 → 34.5; contenders of this succession 20.2 → 5.0; contenders of other successions 5.7 → 12.2; outside the eligible pool 7.5 → 16.7; no head by construction 3.6 → 6.0; head not found 11.9 → 6.5. Section 9 with the extended crosswalk: share commanded +0.43 [0.14, 0.74] (+0.11 [−0.18, 0.42] without Estrada Reynoso), capped at 5 pp per agency +0.16 [0.06, 0.25]; heads an agency with at least 1% of investment +5.6 pp [2.3, 8.8], 8 of 9 successions positive; heads any investment agency +6.5 [1.2, 11.6].
