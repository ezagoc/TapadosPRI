# Reward and punishment against unaligned politicians (MAIN_SPEC section 11, 18 October 2026).
# Designee's followers (D) and losing contenders' followers (P), each against one reweighted group of
# politicians tied to no contender (N). Run after estimate_main.R:
#   Rscript code/04-analysis/main_direct_tie/reward_punishment.R
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
invisible(capture.output(source(file.path(script_dir, "estimate_main.R"))))
source(file.path(script_dir, "design_tools.R"))
set.seed(18102026L)

source(file.path(script_dir, "rp_setup.R"))

f_window <- ~ election_factor + pre_band + earlier_band + age + ldeg + lrec + prior_status + fed_exec
f_es <- ~ election_factor + age + ldeg + lrec + prior_status + fed_exec
S_main <- make_weights(A[support == TRUE], bal_formula_window)
res_main <- run_window(S_main, f_window, "Main: support trimming, entropy balancing, regression")

# ------------------------------------------------------------------ 4b. decomposition: reward, penalty, their difference and shares
# Joint draws: designee groups (Ferman-Pinto, losing groups as donors), losing groups (cluster-robust normal) and
# the shared unaligned part (bivariate normal from the cluster sums of both linear weights).
decompose <- function(S, fit, label, B = 50000L) {
  D <- fit$D; P <- fit$P
  dg <- data.table(cl = S$cluster, e = S$election, g = S$group, r = P$res)[g == "P", .(r = mean(r), n = .N), by = .(cl, e)]
  dg[, rc := r - weighted.mean(r, n), by = e]
  ab <- pmax(0, coef(lm(I(rc^2) ~ I(1 / n), data = dg))); if (sum(ab) <= 0) ab <- c(0, mean(dg$rc^2 * dg$n))
  z <- dg$rc / sqrt(pmax(ab[1] + ab[2] / dg$n, 1e-12)); z <- (z - mean(z)) / sd(z)
  nD <- D$by_e$n; E9 <- length(nD)
  eD_groups <- colSums(matrix(base::sample(z, E9 * B, replace = TRUE), nrow = E9) * sqrt(ab[1] + ab[2] / nD)) / E9
  pi <- S$group == "P"; sP <- tapply((P$a * P$u)[pi], S$cluster[pi], sum)
  eP_groups <- rnorm(B, 0, sqrt(length(sP) / (length(sP) - 1) * sum(sP^2)))
  ni <- S$group == "N"
  sDn <- tapply((D$a * D$u)[ni], S$cluster[ni], sum); sPn <- tapply((P$a * P$u)[ni], S$cluster[ni], sum)
  G <- length(sDn); V <- G / (G - 1) * matrix(c(sum(sDn^2), sum(sDn * sPn), sum(sDn * sPn), sum(sPn^2)), 2)
  eN <- matrix(rnorm(2 * B), ncol = 2) %*% chol(V)
  eD <- eD_groups + eN[, 1]; eP <- eP_groups + eN[, 2]
  thD <- D$est - eD; thP <- P$est - eP        # draws of the estimates (symmetric errors)
  diff <- D$est - P$est; share <- D$est / diff
  q <- function(x) quantile(x, c(.025, .975), names = FALSE, type = 1)
  data.table(spec = label, reward = D$est, penalty = P$est, difference = diff,
             difference_lo = diff - q(eD - eP)[2], difference_hi = diff - q(eD - eP)[1],
             reward_share = share, reward_share_lo = q(thD / (thD - thP))[1], reward_share_hi = q(thD / (thD - thP))[2],
             main_section4 = theta)
}
# ------------------------------------------------------------------ 5. diagnostics
bal_vars <- model.matrix(bal_formula_window, data = S_main)[, -1]
lab <- c(pre_bandmiddle = "Highest rank 5--7, $e-5$ to $e-2$", pre_bandhigh = "Highest rank 8--11, $e-5$ to $e-2$",
         earlier_bandlow = "Highest rank 1--4, $e-9$ to $e-6$", earlier_bandmiddle = "Highest rank 5--7, $e-9$ to $e-6$",
         earlier_bandhigh = "Highest rank 8--11, $e-9$ to $e-6$", age = "Age in the election year",
         ldeg = "Log(1 + ties by $e-2$)", lrec = "Log(1 + ranked posts by $e-2$)",
         prior_statusno_direct = "Previous succession: tied to no contender",
         prior_statusprev_loser = "Previous succession: tied to a loser", prior_statusprev_winner = "Previous succession: tied to the designee",
         fed_exec = "Federal executive post, $e-5$ to $e-2$")
Xall <- model.matrix(bal_formula_window, data = A)[, -1]
balance <- rbindlist(lapply(colnames(bal_vars), function(v) {
  fol <- A$follower == 1L; nn <- A$group == "N"; sn <- S_main$group == "N"
  sdp <- sqrt((var(Xall[fol, v]) + var(Xall[nn, v])) / 2)
  # weighted unaligned mean, aggregated across successions with the followers' succession shares (as the followers' mean)
  nf <- S_main[follower == 1L, .N, by = election]; ws <- S_main$w[sn] * nf$N[match(S_main$election[sn], nf$election)]
  wm <- sum(ws * bal_vars[sn, v]) / sum(ws)
  data.table(variable = lab[[v]], followers = mean(Xall[fol, v]), unaligned_raw = mean(Xall[nn, v]),
             unaligned_weighted = wm, std_diff_raw = (mean(Xall[fol, v]) - mean(Xall[nn, v])) / sdp,
             std_diff_weighted = (mean(Xall[fol, v]) - wm) / sdp)
}))
support_tab <- A[, .(followers = sum(follower), unaligned = sum(group == "N"), unaligned_in_support = sum(group == "N" & support)), by = election]
ess <- S_main[group == "N", .(ess = sum(w)^2 / sum(w^2)), by = election]
support_tab <- merge(support_tab, ess, by = "election")
fwrite(balance, file.path(out_dir, "rp_balance.csv")); fwrite(support_tab, file.path(out_dir, "rp_support.csv"))

# ------------------------------------------------------------------ 6. robustness
f_window_nob <- ~ election_factor + age + ldeg + lrec + prior_status + fed_exec
S_a <- make_weights(A[support == TRUE], ~ age + ldeg + lrec + prior_status + fed_exec)
res_a <- run_window(S_a, f_window_nob, "(a) Without baseline-rank bands")
S_b <- make_weights(A[ps >= 0.1 & ps <= 0.9], bal_formula_window)
res_b <- run_window(S_b, f_window, "(b) Trimming all groups to propensity 0.1-0.9")
# Two strong steps: both ties formed in an office or school cohort of at most 10 people (MAIN_SPEC 11 (c), amended).
strong <- dated[edge_type %in% tie_types & !is.na(focus_size) & focus_size <= 10]
strong_long <- unique(rbind(strong[, .(pid = person_a, other = person_b, year_start)], strong[, .(pid = person_b, other = person_a, year_start)]))
two_step_all <- rbindlist(lapply(elections, function(e) {
  w <- slates[[as.character(e)]]$winner
  contacts <- unique(long_ties[candidate == w & year_start <= e - 2L, pid])
  data.table(election = e, pid = unique(long_ties[candidate %in% contacts & year_start <= e - 2L, pid]))
}))
two_step <- rbindlist(lapply(elections, function(e) {
  w <- slates[[as.character(e)]]$winner
  contacts <- unique(strong_long[other == w & year_start <= e - 2L, pid])
  data.table(election = e, pid = unique(strong_long[other %in% contacts & year_start <= e - 2L, pid]))
}))
A[, two_step_any := paste(election, pid) %in% paste(two_step_all$election, two_step_all$pid)]
A[, two_step_designee := paste(election, pid) %in% paste(two_step$election, two_step$pid)]
S_c <- make_weights(A[support == TRUE & !(group == "N" & two_step_designee)], bal_formula_window)
res_c <- run_window(S_c, f_window, "(c) Without unaligned two steps from the designee")
suppressPackageStartupMessages(library(fixest))
fe <- feols(delta ~ i(group, ref = "N") + pre_band + earlier_band + age + ldeg + lrec + prior_status + fed_exec | pid + election,
            data = A, cluster = ~cluster)
switchers <- A[, .(k = uniqueN(group)), by = pid][k > 1, .N]
ct <- coeftable(fe)
res_d <- data.table(group = c("D", "P"), estimate = ct[c("group::D", "group::P"), 1], se = ct[c("group::D", "group::P"), 2])
res_d[, `:=`(ci_lower = estimate - 1.96 * se, ci_upper = estimate + 1.96 * se, p_value = 2 * pnorm(-abs(estimate / se)),
             inference = "clustered by contender group / unaligned politician", spec = "(d) Within politician (politician and succession FE)",
             n_D = sum(A$group == "D"), n_P = sum(A$group == "P"), n_N = sum(A$group == "N"))]
windows <- rbindlist(list(res_main, res_a, res_b, res_c, res_d), fill = TRUE)
decomp <- rbindlist(list(decompose(S_main, rp_fit(S_main, S_main$delta, f_window), "Main"),
                         decompose(S_a, rp_fit(S_a, S_a$delta, f_window_nob), "(a) Without baseline-rank bands"),
                         decompose(S_b, rp_fit(S_b, S_b$delta, f_window), "(b) Trimming all groups to propensity 0.1-0.9"),
                         decompose(S_c, rp_fit(S_c, S_c$delta, f_window), "(c) Without unaligned two steps from the designee")))
fwrite(decomp, file.path(out_dir, "rp_decomposition.csv"))
windows[, `:=`(two_step_strong_share = mean(A[group == "N" & support == TRUE, two_step_designee]),
               two_step_any_share = mean(A[group == "N" & support == TRUE, two_step_any]))]
windows[, switchers := switchers]
fwrite(windows, file.path(out_dir, "rp_windows.csv"))

# ------------------------------------------------------------------ 7. event study (section-7 covariates)
S_es <- make_weights(A[support == TRUE], bal_formula_es)
YS <- YA[A$support == TRUE, , drop = FALSE]
es <- rbindlist(lapply(setdiff(ks, ref), function(k) {
  y <- YS[, as.character(k)] - YS[, as.character(ref)]
  r <- rp_inference(S_es, rp_fit(S_es, y, f_es), B = 20000L); r[, k := k]
}))
es <- rbind(es, data.table(group = c("D", "P"), estimate = 0, ci_lower = 0, ci_upper = 0, ci90_lower = 0, ci90_upper = 0, k = ref), fill = TRUE)
setorder(es, group, k)
fwrite(es, file.path(out_dir, "rp_event_study.csv"))

# figure: figures.R

print(support_tab); print(balance[, lapply(.SD, function(x) if (is.numeric(x)) round(x, 2) else x)])
print(decomp[, lapply(.SD, function(x) if (is.numeric(x)) round(x, 3) else x)])
print(windows[, .(spec, group, estimate = round(estimate, 3), ci_lower = round(ci_lower, 3), ci_upper = round(ci_upper, 3), p_value = round(p_value, 3), n_N)])
cat("two-step shares among unaligned in support: any ties", round(windows$two_step_any_share[1], 3), " strong ties", round(windows$two_step_strong_share[1], 3), " switchers:", switchers, "\n")
print(es[, .(group, k, estimate = round(estimate, 2), ci_lower = round(ci_lower, 2), ci_upper = round(ci_upper, 2))])

# ------------------------------------------------------------------ 8. deck tables and macros
tab_dir <- file.path(out_dir, "tables"); dir.create(tab_dir, showWarnings = FALSE)
f2 <- function(x, d = 2) { v <- round(x, d); s <- formatC(abs(v), format = "f", digits = d); ifelse(v < 0, paste0("$-$", s), s) }
ci <- function(lo, hi, d = 2) paste0("[", f2(lo, d), ", ", f2(hi, d), "]")
dm <- decomp[spec == "Main"]
w_d <- windows[spec == "(d) Within politician (politician and succession FE)"]
rows <- rbind(windows[group == "D", .(spec, reward = estimate, reward_lo = ci_lower, reward_hi = ci_upper)],
              fill = TRUE)[windows[group == "P", .(spec, penalty = estimate, penalty_lo = ci_lower, penalty_hi = ci_upper)], on = "spec"]
rows[, share := reward / (reward - penalty)]
labels <- c("Main" = "Main: support trimming, entropy balancing, regression")
lab_short <- c("Main: support trimming, entropy balancing, regression" = "Main specification",
               "(a) Without baseline-rank bands" = "Without the baseline-rank bands",
               "(b) Trimming all groups to propensity 0.1-0.9" = "All groups trimmed to propensity 0.1--0.9",
               "(c) Without unaligned two steps from the designee" = "Without unaligned two strong steps from the designee",
               "(d) Within politician (politician and succession FE)" = "Within politician (politician and succession effects)")
tl <- c("% rp_decomposition.tex (reward_punishment.R)", "\\begin{tabular}{lrrr}", "\\toprule",
        " & Reward & Penalty & Share of \\\\", " & (designee's $-$ unaligned) & (losers' $-$ unaligned) & reward \\\\", "\\midrule")
for (i in seq_len(nrow(rows))) tl <- c(tl, sprintf("%s & %s & %s & %s\\%% \\\\", lab_short[[rows$spec[i]]],
  f2(rows$reward[i]), f2(rows$penalty[i]), round(100 * rows$share[i])),
  sprintf(" & {\\scriptsize %s} & {\\scriptsize %s} & \\\\", ci(rows$reward_lo[i], rows$reward_hi[i]), ci(rows$penalty_lo[i], rows$penalty_hi[i])))
tl <- c(tl, "\\bottomrule", "\\end{tabular}")
writeLines(tl, file.path(tab_dir, "rp_decomposition.tex"))
bl <- c("% rp_balance.tex (reward_punishment.R). Standardized: difference over the average of the two groups' s.d.",
        "\begin{tabular}{lrrrrr}", "\toprule",
        " & \multicolumn{3}{c}{Mean} & \multicolumn{2}{c}{Standardized difference} \\",
        "\cmidrule(lr){2-4}\cmidrule(lr){5-6}", " & Followers & Unaligned & Unaligned, & Raw & Weighted \\",
        " & & & weighted & & \\", "\midrule")
for (i in seq_len(nrow(balance))) {
  d <- if (grepl("^Age", balance$variable[i])) 1 else 2
  bl <- c(bl, sprintf("%s & %s & %s & %s & %s & %s \\\\", balance$variable[i],
                      f2(balance$followers[i], d), f2(balance$unaligned_raw[i], d), f2(balance$unaligned_weighted[i], d),
                      f2(balance$std_diff_raw[i]), f2(balance$std_diff_weighted[i])))
}
bl <- c(bl, "\\midrule", sprintf("Politicians & %s & %s & %s & & \\\\", format(sum(A$follower), big.mark = ","),
                                  format(sum(A$group == "N"), big.mark = ","), format(sum(S_main$group == "N"), big.mark = ",")),
        "\\bottomrule", "\\end{tabular}")
writeLines(bl, file.path(tab_dir, "rp_balance.tex"))
mac <- function(n, v) sprintf("\\newcommand{\\%s}{%s}", n, v)
mm <- res_main
writeLines(c("% rp_macros.tex (reward_punishment.R). Do not edit by hand.",
  mac("RPreward", f2(mm[group == "D", estimate])), mac("RPrewardLo", f2(mm[group == "D", ci_lower])), mac("RPrewardHi", f2(mm[group == "D", ci_upper])),
  mac("RPpenalty", f2(mm[group == "P", estimate])), mac("RPpenaltyLo", f2(mm[group == "P", ci_lower])), mac("RPpenaltyHi", f2(mm[group == "P", ci_upper])),
  mac("RPpenaltyAbs", f2(abs(mm[group == "P", estimate]))),
  mac("RPrewardP", f2(mm[group == "D", p_value])), mac("RPpenaltyP", f2(mm[group == "P", p_value])),
  mac("RPdiff", f2(dm$difference)), mac("RPdiffLo", f2(dm$difference_lo)), mac("RPdiffHi", f2(dm$difference_hi)),
  mac("RPshare", round(100 * dm$reward_share)), mac("RPshareLo", round(100 * dm$reward_share_lo)), mac("RPshareHi", round(100 * dm$reward_share_hi)),
  mac("RPshareMin", round(100 * min(rows$share))), mac("RPshareMax", round(100 * max(rows$share))),
  mac("RPnKept", format(sum(S_main$group == "N"), big.mark = ",")), mac("RPnUnaligned", format(sum(A$group == "N"), big.mark = ",")),
  mac("RPessMin", round(min(ess$ess))), mac("RPessMax", round(max(ess$ess))),
  mac("RPpenaltyEnd", "5")), file.path(tab_dir, "rp_macros.tex"))
