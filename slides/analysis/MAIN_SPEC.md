# Main empirical specification — frozen before estimating the new outcome

**Revision (17 October 2026, user decision).** The interval is the Ferman–Pinto network bootstrap as published, with the estimated variance components plugged in and no inflation factor (§5); the event study is §7.

**Status (16 October 2026).** This document supersedes the earlier `MAIN_SPEC` drafts and defines the single main result for the third-year-paper presentation. The old scripts and outputs are historical artifacts, not evidence used to choose this design. The canonical specification and estimator live in the shared code repository at `slides/analysis/`. Source data are read from `TapadosPRI/data`; canonical outputs are written to `TapadosPRI/output/main_direct_tie/` (a local `TAPADOS_MAIN_OUTPUT_DIR` override is available for private presentation work).

## 1. Question, unit, and exposure

The question is whether a politician's **documented direct tie** to the presidential designee is followed by a larger career gain than a direct tie to an unsuccessful aspirant in the same PRI succession. The comparison is among politicians already connected to one contender. A direct tie means a dated, documented co-work, co-education, co-military, or co-revolution edge to that contender, formed no later than two years before the election. It is not a claim of friendship or of no other indirect political connections.

The observation is a politician $i$ in succession $e\in\{1940,1946,1952,1958,1964,1970,1976,1982,1988\}$. Let $C_e$ be the observed slate, $s_e\in C_e$ the designee, and $c(i,e)\in C_e$ the politician's **single** directly tied contender. Let $D_{ie}=1\{c(i,e)=s_e\}$. The exclusive-tie restriction keeps treatment and control labels unambiguous; it limits the target population and does not rule out indirect exposure to the designee.

Eligibility is fixed from information available by $e-2$: a recorded ranked political position in the four years $e-5,\ldots,e-2$, age 25–75 in election year $e$, and no candidacy in the current or an earlier listed succession. Later candidates remain eligible until they themselves enter a slate. Drop observations without birth year. A politician may appear in several succession cohorts.

## 2. Main outcome and contrast

Let $R_{ie}^{pre}$ be the **highest whole-rung rank of a recorded post** in $e-5,\ldots,e-2$, and $R_{ie}^{post}$ the same in $e+1,\ldots,e+4$. Higher ranks mean higher political office; ties within a rung are discarded. Records without a start year or rank, and spells longer than 12 years, are excluded before constructing annual ranks. Set $R_{ie}^{post}=0$ if no retained ranked post is recorded in the post window. Then $\Delta R_{ie}=R_{ie}^{post}-R_{ie}^{pre}$. The two windows each contain four calendar years; $e-1$ and $e$ are excluded because designation and transition may begin there. The zero is *no recorded ranked office*, not a claim of unemployment. Missing coverage of office histories is therefore a measurement threat.

The main descriptive contrast in succession $e$ is the difference between the mean $\Delta R$ for direct followers of $s_e$ and a covariate-standardized mean for direct followers of losing contenders. We average the nine succession contrasts equally:

$$
\theta^{rel}=\frac{1}{9}\sum_e\theta_e^{rel},\qquad
\theta_e^{rel}=E[\Delta R\mid D=1,e]-E_{X\mid D=1,e}\{m_{0,e}(X)\},
$$

where $m_{0,e}(X)=E[\Delta R\mid D=0,e,X]$ is the change among loser followers at comparable predetermined $X$. Within a succession, losing followers contribute as people; a losing candidate with more eligible followers gets more weight. This targets a typical succession, not a typical politician across the whole 1940–1988 sample. Report all nine cohort estimates and the effective weights of the losing networks. Equal *candidate-network* weights are a sensitivity analysis, not an implicit probability that each rival would have won.

**Interpretation.** The estimate is the *relative career premium of a direct tie to the observed designee, compared with a direct tie to an observed loser*. It combines any reward to winner followers, any penalty to loser followers, and effects of indirect links. The design by itself cannot identify their separate absolute effects.

## 3. Potential outcomes and identification

The president chooses **one winner per slate**. For politician $i$, potential career outcomes are $R_{ie,t}(s)$ for each $s\in C_e$, allowing that the identities of all other contenders and their networks matter. The counterfactual career of a follower of $A$ when $A$ loses is not one outcome unless the alternative winner is specified or averaged using explicit weights over $B,C,\ldots$. The observed loser followers under the actual winner $s_e$ do not reveal what the $A$ followers would have experienced had another contender won. We therefore do **not** label the main estimate an ATT of making one's own patron president and do **not** assert no spillovers/SUTVA.

A causal reading of the relative contrast needs **conditional parallel trends for the relevant comparison**: absent the differential career consequences of having a direct tie to the designated rather than an unsuccessful contender, the expected change of their followers would be equal after conditioning on predetermined $X$ and succession. Equivalently, presidential choice may depend on stable contender quality and pre-existing network characteristics, but not on unobserved *future follower momentum* that would have occurred irrespective of who was designated. This is a substantive historical claim about dedazo; neither individual nor succession time fixed effects prove it. Pre-trends and balance can probe but cannot establish it. Indirect winner ties among loser followers and differential loser penalties can change the interpretation even when the trend comparison looks plausible.

The historical argument to investigate is concrete: the outgoing president chose among established insiders for coalition, loyalty, policy, and regime-management reasons, while the followers' prior careers and ties were already visible before the public destape. After controlling for that visible history, the choice would not track an *unobserved future trend* in their careers that would have occurred even if their patron lost. The choice itself was endogenous, and this argument is a hypothesis requiring evidence from succession histories and biographies; it is not established by naming the dedazo. Private expectations of designation may have formed before $e-2$, allowing strategic tie formation or early promotions. The strongest threats are this anticipation, selection on unobserved network momentum, concurrent patron-specific shocks, spillovers/interference, and selective recording of ties or offices. We should state these plainly in the talk.

## 4. Frozen main estimator

Compute the outcome once per eligible politician–succession. Estimate $m_0$ **using loser followers only** in one pooled linear regression with succession indicators and common slopes for pre-designation covariates. The controls are exactly: baseline whole-rung rank bands 1–4, 5–7, and 8–11 (ceiling adjustment); highest recorded rank in $e-9,\ldots,e-6$ as no record, 1–4, 5–7, or 8–11; age at $e$ as a linear term; log(1 + number of dated network-edge records formed by $e-2$); log(1 + number of retained ranked-position records started by $e-2$); and prior-succession connection status (direct tie to previous winner, tie to previous loser only, no tie, or absent from the prior eligible cohort). Each control observation receives weight $1/n_{0e}$, so each succession contributes equal total weight to fitting common slopes; within a succession the observed person shares of losing networks are retained. Predict $m_0$ for every winner follower, average their observed-minus-predicted changes by succession, and average those nine contrasts equally. This is an outcome-regression **conditional DiD**, not DRDiD/AIPW: double robustness would require a correctly implemented genuine two-period DRDiD and does not supply identification or solve interference.

Before accepting the estimate, report common support of the predetermined covariates, especially baseline rank, and the nine network sizes. Do not extrapolate silently across rank cells or pretend that empty networks are controls. If a categorical level is absent among all losing followers, combine adjacent pre-specified rank bands and disclose the change; do not decide from outcome estimates. A genuine two-period DRDiD could be a later nuisance-model sensitivity if overlap is adequate. Its propensity score would model a person's probability of being directly tied to the selected contender conditional on pre-destape observables **within this design**; it is not simply the president's probability of choosing that contender. Double robustness would not resolve one-of-$K$ counterfactuals, spillovers, or unmeasured network momentum.

## 5. Inference with nine designated networks

Treatment assignment and contender-specific shocks operate at the **candidate network within a succession**, not independently across followers. There are nine designated networks. Do not use a person-level robust standard error, and do not present a conventional succession-clustered normal interval as if nine clusters established precision. Individual and succession-by-period fixed effects absorb persistent person levels and common slate shocks; they do not absorb candidate-network post shocks.

The primary interval will be a **network-level residual bootstrap of the full estimator**, adapted to the Ferman–Pinto/Álvarez–Ferman few-treated logic. Recompute the winner–loser standardized contrast in each draw, perturbing *all* candidate-network post-change shocks, including those of losing networks. Estimate the shock distribution from residuals of losing networks after removing succession means and the main $X$ adjustment, with an explicit small-network variance model $\sigma^2_{ec}=A+B/M^{eff}_{ec}$. The donor mean has $M^{eff}=n$; for the estimator's target network contribution, $M^{eff}=(\sum_i a_i)^2/\sum_i a_i^2$, where $a_i$ is its exact linear weight. Correct the donor residual moments for the full control-regression hat matrix. Standardize donor residuals, draw shocks for every network, rescale by its fitted variance, and invert the empirical distribution of the full estimate centered on the observed estimate. The estimator is linear in outcomes with fixed $X$, so the exact linear weights propagate control-model refitting without re-running a regression in each draw. Record the interval algorithm, seed, draw count, leverage correction, fitted variance components, and network contributions in machine-readable output.

This is an **approximate** interval: the papers' clean many-control-groups theorem does not apply unchanged to slates with only a handful of losing networks, and exchangeability of standardized winner/loser network shocks after conditioning is untestable. Validate finite-sample coverage under simulated shocks on the *observed* nine-slate network-size layout, including heteroskedasticity, heavier tails, and repeated politicians. **The interval uses the estimated variance components as they are, with no inflation factor** (17 October 2026, user decision). The 16 October run widened the bootstrap error quantiles by a fixed 1.20, a size set by the largest simulated network shock ($A=2$) rather than by the data; it was dropped. The validation script reports the coverage of the plug-in interval in the simulations. Report leave-one-succession-out estimates and a variance-component sensitivity grid. This is **not** a conventional nine-cluster succession interval. If the bootstrap is unstable or undercovers materially, report that limitation rather than a spuriously tight 95% interval.

## 6. Research sequence

1. Build a new, transparent analysis dataset from the frozen source files; audit eligibility, edge dates, duplicates, and rank measurement. Do not read old result tables to choose specification.
2. Compute this one main estimate, its nine components, overlap diagnostics, and a network-aware interval. Inspect whether the interval is informative and calibrate coverage by simulation before using it in slides.
3. Only after the main result is credible: event study and pre-trend probes; sensitivity to rank definition and losing-network weights; explicit indirect exposure/distance analysis using meaningful typed paths rather than naive two-hop institutional projection.

## 7. Event study (written 17 October 2026, before it was computed on this design)

An exploratory event study on the previous design's sample (`research/_explore_2026-10-16/`) had been seen before this section was written; it is not an input here.

**Contrast.** The same analysis sample, treatment, loser-only outcome model, weights $1/n_{0e}$ and equal average of the nine succession contrasts as in §4, applied year by year. For $k\in\{-7,\ldots,8\}$ let $Y_{i,e+k}$ be the highest whole rung of a retained ranked post held in year $e+k$ (0 if none, as in §2), and $\Delta Y_{ik}=Y_{i,e+k}-Y_{i,e-2}$. The reference year is $k=-2$, the year at which ties and eligibility are measured; $\theta_k$ is the §2 contrast with $\Delta Y_{ik}$ as outcome. The sample is fixed across $k$.

**Covariates.** Succession indicators, age, log degree, log records and prior-succession status: the §4 controls **without the two rank bands**. The baseline band is a function of $Y$ in $e-5,\ldots,e-2$ and the earlier band of $Y$ in $e-9,\ldots,e-6$; conditioning on them would pull the leads toward zero mechanically and empty the pre-trend check. The main window contrast ($\Delta R$ of §2) under these covariates is reported next to the §4 estimate.

**Reading.** $k=-7,\ldots,-3$ are leads (pre-trend probes). $k=-1$ (the destape) and $k=0$ (election and handover; the new cabinet is named on 1 December of $e$ and is coded in year $e$) are transition years, outside the main windows. $k=1,\ldots,6$ is the patron's term, $k=7,8$ the next president's (the term ends on 1 December of $e+6$). Patronage predicts flat leads, a gap from the handover and a fall when the patron leaves office; a network rising for reasons of its own predicts neither a break at the handover nor one at $k=7$. Summary contrasts: lead average ($-7,\ldots,-3$), main-window average ($1,\ldots,4$), term average ($1,\ldots,6$), next-president average ($7,8$) and $\theta_7-\theta_6$.

**Secondary outcome.** The extensive margin with the same design: $1\{Y_{i,e+k}>0\}-1\{Y_{i,e-2}>0\}$, holding any recorded ranked post.

**Inference.** The §5 network bootstrap, run jointly over $k$: each draw assigns one pooled donor network to every network slot and uses that donor's standardized residuals at every $k$, which keeps the dependence across years within a network. The variance components $(A_k,B_k)$ are fitted year by year with the leverage correction of §5, with no inflation factor (§5). Report pointwise 95% and 90% intervals, a 95% sup-t band over $k\neq-2$, the joint lead test $\max_{k\le-3}|\hat\theta_k|/\hat s_k$, and intervals for the summary contrasts from the same draws. Code: `event_study.R`.

## 8. Margins of the rank premium (written 17 October 2026, before computing)

Rank with zeros mixes two things: whether a politician still holds a recorded ranked post and how high that post is. Same sample, treatment, estimators (§4 for windows, §7 for event studies), weights and inference.

- **Extensive margin.** $E_{i,t}=1\{\text{holds a retained ranked post in } t\}$. Window: $1\{R^{post}_{ie}>0\}-1\{R^{pre}_{ie}>0\}$ (every eligible politician has $R^{pre}>0$). Event study: $E_{i,e+k}-E_{i,e-2}$.
- **Intensive margin.** Rank among politicians in office before and after. Window: $\Delta R_{ie}$ on the subsample with $R^{post}_{ie}>0$, the loser-only outcome model refit on loser followers in that subsample. Event study: $Y_{i,e+k}-Y_{i,e-2}$ on politicians holding a ranked post in both $e-2$ and $e+k$, with the design recomputed year by year (pointwise intervals only).
- The designation can change who stays in office, so the intensive contrast compares selected groups. For the window contrast report Lee (2009) bounds: in each succession the group with the higher post-window office rate is trimmed by its excess share, from the top (lower bound) or the bottom (upper bound) of its residual changes from the loser-only model; succession bounds are averaged with the equal weights.

## 9. Federal investment commanded (written 17 October 2026, before computing)

**Outcome.** $B_{i,t}$ = percent of the year's federal public investment realized by the agency politician $i$ heads in year $t$; 0 if he heads none. Heads are cabinet secretaries, the regent of the Federal District and directors general (managers) of parastatals in the agency investment panel (`05-investment/10_*`), resolved from the role text with the crosswalk of the 13 October design (archived `budget_outcome.py`), ported unchanged to R. A person heading two agencies keeps the larger. Agency investment is a secretaría's own investment and each parastatal's; in 1984–1997, when only the sector view exists, a secretaría gets its sector minus its mapped parastatals. Shares are within year, so no deflator is needed; 1964–1969 use the panel's imputed realized series. Window: maximum over $e+1,\ldots,e+4$ minus maximum over $e-5,\ldots,e-2$, in percentage points; extensive: heads an investment agency. Event study as in §7. Event study also for heading an investment agency (added 18 October 2026, to read the timing of the investment event study: whether its end after $e+2$ comes from leaving the post or from the agency's budget).

**Reading.** The contrast combines being appointed to head an agency and the agency's budget. It does not hold the office fixed, so it is not a test that the same office receives more money.

## 10. Appendix diagnostics (written 17 October 2026)

(1) Balance of predetermined traits: raw means by group and within-succession standardized differences (descriptive; the design allows selection on levels). (2) Sample flow by succession. (3) Estimates by succession and leaving one succession out. (4) Robustness of the main contrast: person weights, no covariates, adjustment for the exact baseline rung (lagged level), scale-free thresholds $1\{R^{post}\ge r\}-1\{R^{pre}\ge r\}$. (5) Coverage of the §5 interval in the simulations. (6) Anticipation: new direct ties formed with each contender in $e-8,\ldots,e-2$, designee vs losing contenders. (7) Losing camps vs random regroupings: permutation test of the between-camp variation of residual changes among loser followers (10,000 reshuffles within succession). (8) Ties dated by $e-4$ instead of $e-2$ (added after diagnostic (6), before computing it: the 1976 and 1982 designees formed most of their ties in $e-4$ and $e-3$, when the outgoing president appointed them to Finance and to Programming and Budget, so late recruits could select into a rising team). Eligibility, covariates and windows are unchanged; only the tie cutoff moves (`TAPADOS_TIE_CUTOFF=4`). (9) Without 1976 and 1988 (added from the historical record, before computing it: in both the outgoing president leaned toward the designee years before the destape, López Portillo moved to Finance in 1973 and Salinas confirmed as economic chief in 1986; Castañeda 1999, pp. 76, 198, 365, 371). (10) Without Díaz Serrano's group in 1982 (forced out of Pemex in June 1981 and jailed under the next president, a shock to one losing group; Castañeda 1999, pp. 393, 411).

## 11. Reward and punishment against unaligned politicians (written 18 October 2026, before computing)

**Question.** How much of the relative premium is a reward to the designee's followers and how much a penalty to the losers' followers, both measured against politicians tied to no contender?

**Groups.** The eligible politicians of §1: designee's exclusive followers ($D$), losing contenders' exclusive followers ($P$), and politicians with no direct tie to any contender by $e-2$ ($N$). Politicians tied to several contenders are excluded, as in §1.

**Estimands.** $\theta^{D}_k=\frac19\sum_e\big(\overline{\Delta Y_{ik}}^{D}_e-\overline{\hat m^{N}_k(X_i)}^{D}_e\big)$ and $\theta^{P}_k$ likewise, with $\hat m^{N}_k$ the change of comparable unaligned politicians. One reweighted $N$ serves both, so $\theta^D-\theta^P$ approximates the §4 estimate. Reading: $\theta^P$ is the penalty aimed at a loser's followers beyond what any unaligned politician bears (displacement by the winner's camp falls on both); $\theta^D$ is the reward beyond the unaligned. Neither is an absolute effect.

**Comparability of $N$.** (i) Common support: a logit of being a follower ($D$ or $P$) on succession indicators and the §4 covariates plus a new one, *federal executive* (a ranked post in the federal executive branch in $e-5,\ldots,e-2$); within each succession, unaligned politicians below the lowest follower propensity are dropped; no follower is dropped. (ii) Entropy balancing (Hainmueller 2012) within each succession: weights on the remaining unaligned so that their weighted means of the covariates equal the followers' ($D$ and $P$ pooled), as close to equal weights as possible; each succession's unaligned weights sum to one. (iii) The §4 outcome regression (succession indicators, common slopes) fitted on the weighted unaligned, predicting for $D$ and for $P$; with exact balance this adds only the correction for the small differences between $D$ and $P$. Window contrast with the §4 covariates; event study ($k=-7,\ldots,8$) with the §7 covariates (no rank bands), plus federal executive in both.

**Inference.** $\theta^P$: cluster-robust variance of the linear estimator, clusters = losing contender groups (45) and each unaligned politician (all his successions). $\theta^D$: §5 bootstrap with the losing groups' mean residuals against the weighted unaligned as donors.

**Diagnostics and robustness (fixed now).** Balance before and after weighting; effective sample size of the weights; number of unaligned dropped. Robustness: (a) without the baseline-rank bands in the weights and the regression (regression to the mean when groups differ in levels; Daw and Hatfield 2018); (b) standard trimming of all groups at propensities in $[0.1, 0.9]$ (Crump et al. 2009); (c) without unaligned politicians who are two steps from the designee by $e-2$ (tied to someone directly tied to him). *Amended before seeing any estimate:* with every tie, nearly all comparable unaligned politicians are two steps away and the rest cannot be balanced, so both steps use strong ties only (formed in an office or school cohort of at most 10 people); (d) within politician: stacked $D$, $P$ and $N$ observations with politician and succession fixed effects and the §4 covariates, identified by politicians whose status changes across successions (as in Xu 2018).

## 12. The patron's chair (written 19 October 2026, before the formal estimate)

**Question.** Is the losers' followers' penalty (§11) the loss of their patron's chair, or a penalty aimed at them whatever their patron keeps? A first look in an exploration on 19 October (no weighting, no design inference) split the losers' followers by their patron's post after the succession and motivated this section; the definitions below are those of the first look and are fixed now, before the formal estimate.

**Patron's chair.** A losing contender *keeps a top chair* if his highest whole rung in $e+1,\ldots,e+2$ (the new president's first two years) is at least 8: cabinet secretary, head of a large parastatal, attorney general, Federal District regent, ambassador to the United States (rung 9); governor of a major state, PRI national president, leader of a chamber, major embassy, military zone (rung 8). Otherwise he *loses* it.

**Groups and estimands.** $D$ and $N$ as in §11; $P$ split into $P^{k}$ (patron kept a top chair) and $P^{l}$ (patron lost it). $\theta^{Pk}$ and $\theta^{Pl}$ as $\theta^P$ in §11, with the same reweighted $N$ (balanced to all followers pooled) and the same outcome regression, window and event-study covariates. The headline contrast is within succession, over the successions $E_2$ in which both groups exist: $\theta^{k-l}=\frac{1}{|E_2|}\sum_{e\in E_2}\big(\overline{\Delta Y-\hat m^{N}}^{Pk}_e-\overline{\Delta Y-\hat m^{N}}^{Pl}_e\big)$.

**Reading.** The new president decides which losers keep a chair, so $\theta^{k-l}$ is not the causal effect of a patron keeping his chair. It is the moment the structural model must match conditional on the observed chair assignment, and the reduced-form test of "the penalty is the chair": $\theta^{Pk}\approx 0$ or above, $\theta^{Pl}<0$. Selection checks, fixed now: (i) leads $k=-7,\ldots,-3$ of $P^k$ and $P^l$ in the event study; (ii) standardized differences of the followers' predetermined traits, $P^k$ vs $P^l$; (iii) the patrons' traits at $e-2$ (rung, exclusive followers, age, documented runner-up), kept vs lost.

**Inference.** Cluster-robust variance of each linear estimator, clusters = losing contender groups and each unaligned politician (§11), and a wild score bootstrap with Webb weights over the same clusters (few groups keep a chair). $\theta^D$ as in §11.

**Robustness (fixed now).** (a) Top chair = rung 9 only (cabinet level); (b) the patron's chair over $e+1,\ldots,e+3$; (c) each succession of $E_2$ left out in turn.

## 13. Predetermined inclusion in the dictionary (written 19 October 2026, before computing)

**Question.** Camp (2011) includes a politician who reached one of Brandenburg's top six prestige levels at some point up to
2009. For many pool members that post came after $e-2$, and more often for the designee's followers: 49.5% of them, against
39.9% of the losers' followers and 38.3% of the unaligned, first reached rung 7 or above after $e-2$ (measured 19 October).
Their presence in the data is then partly an outcome of the succession. Does the premium survive in the pool whose presence
does not depend on careers after $e-2$?

**Restriction.** Pool members (§1) who held a qualifying post that started by $e-2$: rung 7 or above (assistant secretary,
*oficial mayor*, senator, PRI national executive and every higher post); national leadership of an opposition party (rule
`opposition_national_leadership`); rector of UNAM or IPN, or director of UNAM's schools of law, economics or medicine (role
text). This follows Camp's stated inclusion rule (front matter of the 1935–2009 edition), which does not admit federal deputies
on their own. The restriction applies to every group alike; everything else in the design is unchanged (eligibility, ties,
covariates, weights, inference). Implementation: `TAPADOS_INCLUSION=predetermined`, outputs in
`output/main_direct_tie/robust_predetermined_inclusion/`.

**Estimates.** §4 with §5 inference; the §7 event study; the §8 margins; the §11 reward and penalty; the §12 chair split. These
are also the moments of the co-main structural estimate (`research/structural_2026-10-19/MODEL_SPEC.md` §2).

**Reading, fixed now.** The restricted pool is more senior by construction (everyone reached rung 7 by $e-2$), so a different
estimate can reflect selection into the dictionary or a different premium for senior politicians; the two cannot be fully
separated. A premium of similar size says selection into the dictionary does not drive it. A much smaller one says the
headline estimate partly reflects who is in the dictionary, and both are reported with equal prominence.

## 14. Generalized event study (reserved)

Specified in `research/structural_2026-10-19/MODEL_SPEC.md` §8, family 4; to be written here before it is computed.

## 15. Co-optation and the threat of a break (written 19 October 2026, before testing)

**Model behind it.** The new president decides which losing aspirants keep a top chair. A chair given to a rival is a chair
taken from his own camp (its price is the capacity price of rungs 8–9), but a co-opted aspirant has less reason to break with
the party and take his followers with him. The president should therefore co-opt the aspirants whose break would cost him
most, and less so when leaving the party is hard (opposition-entry rules, `structural/exit_rules.csv`, from Orozco Henríquez
and Vargas Baca 2006: easy 1940, 1982, 1988; intermediate 1946, 1952; hard 1958–1976).

**Data.** `aspirants_table.R` → `structural/aspirants.csv`: the 47 slate losers (main test) and every aspirant of the full
list plus Almazán (72; breaks). Threat measures dated by $e-2$: camp (politicians of the eligible pool directly tied to the
aspirant), general's rank, governors in office among those tied to him. Treatment: kept a top chair (rung 8–9 in $e+1..e+2$),
demoted, or no post.

**What was already known (not tests).** (a) In each of the four successions in which some loser kept a top chair (1952,
1958, 1976, 1988), the loser with the largest exclusive camp was among those kept (19 October, exploratory); in 1964, 1970 and
1982 nobody was kept, including the three largest camps of the sample. (b) The breaks (Almazán and Sánchez Tapia 1940, Padilla
1946, Henríquez 1952, Cárdenas and Muñoz Ledo 1988) all fall in easy or intermediate regimes. (c) The losers' followers'
penalty is the patron's chair, not an active penalty (§12).

**Pre-registered test (P1).** Within succession, slate losers with a larger threat are more likely to keep a top chair.
Threat index (one number, fixed now): the standardized log(1 + camp). Statistic: the sum of the threat index over the kept
losers, against its distribution when the kept labels are permuted within succession (number kept per succession fixed; all
permutations enumerated); one-sided exact p-value. Only the successions with at least one kept and one not kept loser are
informative (1952, 1958, 1976, 1988). Secondary, reported but not a gate: the same test with the general's rank and the
governors in camp; a conditional logit with seniority (cabinet at $e-2$), age and runner-up as controls.

**Pre-registered descriptive check (P2).** Successions with any co-optation by opposition-entry regime. With nine successions
it is reported, not tested.

**Gate.** The strategic block is built on Block A if P1's exact p-value is below 0.10. Otherwise the co-optation story is
reported as not supported by retention, and the block is not built on it.

## 16. Whom the succession promotes: credentials (written 19 October 2026, before computing)

**Question.** Does the premium to the designee's followers go to less qualified politicians, so that the succession bargain
lowers the qualifications of top officials (the cost side of peaceful rotation)?

**Measures, predetermined.** From `clean_positions/education.csv`: (i) a graduate degree (master's or doctorate) completed by
$e-2$ (degree year $\le e-2$; if the year is missing, counted when the politician was 35 or older at $e-2$); (ii) a foreign
graduate degree, same rule; (iii) a technical field (economics, business, engineering, science) at any level by $e-2$,
secondary.

**Already known (descriptive, 19 October).** Graduate degree: 29% of the designee's followers, 24% of the losers' followers;
foreign graduate degree 15% vs 9%; both rise over time (1976: 44% vs 22%).

**Test 1 (primary).** The §4 design estimated separately on followers with and without a graduate degree (the designee's and
the losers' followers split by the same measure; §4 covariates, with succession entered as a factor of the successions
present in each subsample; equal weights over successions in which both groups exist). Contrast: $\theta_{\text{without}}-
\theta_{\text{with}}$. A selection cost predicts a contrast of zero or above (the premium does not require credentials).
Inference: each estimate with the §5 bootstrap; the contrast interval from independent draws, which is conservative because
shared network shocks correlate the two estimates positively. Secondary: the same with the foreign graduate degree and the
technical field.

**Test 2 (descriptive).** Among politicians holding a top post (rung 8–9) at some point in $e+1..e+4$, the share with a graduate
degree by $e-2$: the designee's exclusive followers against every other holder, averaged over successions; and the same share
among top-post holders of $e-5..e-2$.

**Reading, fixed now.** A selection cost needs both: a premium not tilted toward credentialed followers (Test 1) and promoted
followers less credentialed than the other top officials (Test 2). If the premium favors the credentialed and the promoted
followers are at least as credentialed, the succession bargain had no selection cost in these measures, and the cost of
rotation must be looked for elsewhere (turnover of experience at each handover).

## 17. Where the dissident vote concentrated (written 20 October 2026; measures revised the same day, see note)

**Question.** Can a dissident's electoral damage by state be measured before the break? This is the first diagnostic of
the exit-threat model (damage $D_j$ by state); if it fails, the threat cannot be measured with these data.

**Elections and dissidents.** 1940 Juan Andreu Almazán (158), 1946 Ezequiel Padilla (2024), 1952 Miguel Henríquez Guzmán
(1298), 1988 Cuauhtémoc Cárdenas (452, FDN). Official state counts (`electoralData/`: 1940 DD, 1946-52 Ramírez Rancaño,
1988 Colegio Electoral dictamen). Outcome: the dissident's share of all candidates' votes, as a deviation from his mean
across states (his national level is not what is measured). Official counts: fraud heavier where he was stronger
compresses the association, so a positive result is conservative and a null is not decisive.

**Measures of an electoral base** (the question is about electoral machines, so the measures are not the §4 tie
definitions): (i) own base, his birth state and the states of his own posts before $e$; (ii) the share of the state's
political elite tied to him: people with elected, state or local party, state-government (outside the Federal District)
or military posts located in the state in $e-6..e-1$, tied to him by any tie type existing by $e-1$ (stated and undated
ties included); (iii) an allied governor, a governor of the state in $e-6..e-1$ tied to him.

**Evaluation.** Within election (fit by state); leave one dissident out (fit on three, predict the fourth's state pattern);
placebo aspirants (the $R^2$ of the dissident's own base and elite share against the same $R^2$ with every other aspirant
of the succession).

**Note on the revision.** The first measure (each dissident's network share by the location of his ties' posts, §4 tie
definition) located the networks in the federal bureaucracy (83% of Padilla's in the Federal District), which is not an
electoral base; its pooled placebo $p$ was 0.39. It was replaced by the measures above before they were computed.

**Result (20 October 2026).** The threat is not measurable with these data. Tied local elite: 3, 5, 3 and 21 people
(Camp records 7 and 6 ties for the two generals). The elite share does not predict (Spearman 0.13, 0.21, −0.38, 0.00).
Own base predicts only through the Federal District, where every dissident did well, and Cárdenas in Michoacán (63.9%);
the birth states of Almazán, Padilla and Henríquez are below their means. Allied governor +0.09 (se 0.04), mixed by state.
Out of sample, own base predicts 1940 and 1988 (r = 0.57, 0.53) but not 1946 or 1952 (0.13, 0.09). Placebos: another
aspirant's base and elite predict the dissident's vote as well as his own ($p$ = 0.4, 0.5, 0.5, 0.1). Reading: the
dissident vote follows a general opposition geography (Federal District, Morelos, Baja California, the Bajío), not the
dissident's own network; Cárdenas 1988 is the one case with a personal base.
Outputs: `dissident_geography_{states,within,loo,placebos}.csv`.

## Methodological anchors

- Sant’Anna and Zhao (2020), *Doubly Robust Difference-in-Differences Estimators* (genuine panel DRDiD and its identifying conditions).
- Ghanem, Sant’Anna, and Wüthrich, *Selection and Parallel Trends* (`SantAnna_Selection_on_PT.pdf`; historical selection can coexist with conditional parallel trends only under specific restrictions on untreated dynamics).
- Ferman and Pinto, *Inference in Differences-in-Differences with Few Treated Groups and Heteroskedasticity* (`Ferman_REst_Inference_in_DiD_Few_Treated_Groups.pdf`).
- Álvarez and Ferman, *Extensions for Inference in Difference-in-Differences with Few Treated Clusters* (`Alvarez_Ferman_Extensions_for_Inference_in_DiD.pdf`).

All four PDFs are in `TapadosPRI/literature/papers/11_methods_network_inference/`. Their inference results motivate, but do not prove the validity of, the adapted network bootstrap specified here.

## 4a. Succession weights of the pooled estimand (amended 3 November 2026)

§4 and §7 defined the pooled estimate as the equal average of the nine succession contrasts. From 3 November 2026 the main
estimand weights each succession by its share of the designee's followers (`TAPADOS_SUCCESSION_WEIGHTS=person`, the
default in `estimate_main.R`): $\hat\theta=\sum_e \omega_e\hat\tau_e$, $\omega_e=n^{D}_e/\sum_{e'}n^{D}_{e'}$, the premium of the
average follower of a designee. Reason: the equal average gave 1/9 of the weight to successions with 7 to 19 designee
followers (1940–1958), which set the width of the interval (person-level noise, `A_network` = 0; see
`inference_checks.R`), while the estimator's variance estimator was already at the independent-person floor. The equal
average is kept as the robustness row (`appendix_diagnostics.R`). The same $\omega_e$ (designee's followers' shares) are
used in both the reward and the penalty contrasts of §11, in the indirect-tie contrasts (§ indirect ties, D2 shares),
in the randomization and designee-placebo reference distributions (each combination weighted by its pseudo-designees'
followers) and in the raw trajectories figure. Linear weights, the Ferman–Pinto bootstrap and the coverage simulation
(§5) are recomputed under the new weights; the donor variance fit $A+B/n$ does not depend on $\omega$.
