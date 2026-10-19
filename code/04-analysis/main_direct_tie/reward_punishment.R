# Reward and punishment against unaligned politicians (MAIN_SPEC section 11, 18 October 2026).
# Designee's followers (D) and losing contenders' followers (P), each against one reweighted group of
# politicians tied to no contender (N). Run after estimate_main.R:
#   Rscript code/04-analysis/main_direct_tie/reward_punishment.R
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
invisible(capture.output(source(file.path(script_dir, "estimate_main.R"))))
source(file.path(script_dir, "design_tools.R"))
set.seed(18102026L)

# ------------------------------------------------------------------ 1. all eligible D, P, N with covariates
pt <- fread(file.path(data_dir, "rank", "position_tiers.csv"), na.strings = c("", "NA"))
fedx <- pt[dataset == "govt_positions" & !grepl("^state_|^governor|^mayor|city_council|^local", rule) & !is.na(year_start)]
fedx[, `:=`(y0 = as.integer(year_start), y1 = as.integer(pmax(fifelse(is.na(year_end), year_start, year_end), year_start)))]
fedx <- fedx[y1 - y0 <= 12L]
A <- rbindlist(lapply(elections, function(e) {
  d <- copy(eligible[[as.character(e)]][n_direct <= 1L])
  prior <- eligible[[as.character(e - 6L)]]
  if (is.null(prior)) d[, prior_status := "absent"] else {
    p <- prior[match(d$pid, pid)]
    d[, prior_status := fifelse(is.na(p$pid), "absent", fifelse(p$prior_winner_tie == 1L, "prev_winner",
                         fifelse(p$n_direct > 0L, "prev_loser", "no_direct")))]
    d[is.na(prior_status), prior_status := "no_direct"]
  }
  d[, fed_exec := as.integer(pid %in% fedx[y0 <= e - 2L & y1 >= e - 5L, person_id])]
  w <- slates[[as.character(e)]]$winner
  d[, group := fifelse(n_direct == 0L, "N", fifelse(patron == w, "D", "P"))]
  d
}), use.names = TRUE, fill = TRUE)
A[, pre_band := factor(fifelse(pre <= 4L, "low", fifelse(pre <= 7L, "middle", "high")), levels = c("low", "middle", "high"))]
A[, earlier_band := factor(fifelse(earlier == 0L, "none", fifelse(earlier <= 4L, "low", fifelse(earlier <= 7L, "middle", "high"))),
                           levels = c("none", "low", "middle", "high"))]
A[, prior_status := factor(prior_status, levels = c("absent", "no_direct", "prev_loser", "prev_winner"))]
A[, election_factor := factor(election, levels = elections)]
A[, follower := as.integer(group != "N")]
A[, cluster := fifelse(group == "N", paste0("N_", pid), paste(election, patron, sep = "_"))]
stopifnot(nrow(A[group != "N"]) == nrow(sample), nrow(A[group == "D"]) == sum(sample$treated))

# Annual ranks for the event study.
ks <- -7:8; ref <- -2L
yr_all <- function(k) { z <- annual[data.table(pid = A$pid, year = A$election + k), on = .(pid, year), rank]; z[is.na(z)] <- 0L; z }
YA <- sapply(ks, yr_all); colnames(YA) <- ks

# ------------------------------------------------------------------ 2. propensity of being a follower, common support
ps_formula <- follower ~ election_factor + pre_band + earlier_band + age + ldeg + lrec + prior_status + fed_exec
A[, ps := fitted(glm(ps_formula, family = binomial, data = A))]
A[, min_follower_ps := min(ps[follower == 1L]), by = election]
A[, support := follower == 1L | ps >= min_follower_ps]

# ------------------------------------------------------------------ 3. entropy balancing within succession
eb_weights <- function(Xc, target, tol = 1e-9, maxit = 200L) {
  keep <- apply(Xc, 2, function(v) sd(v) > 0)
  # A trait constant among the unaligned cannot be balanced; it is dropped (only happens in robustness samples).
  dropped <- colnames(Xc)[!keep & abs(colMeans(Xc) - target) > 1e-8]
  C <- sweep(Xc[, keep, drop = FALSE], 2, target[keep]); sc <- apply(C, 2, sd); C <- sweep(C, 2, sc, "/")
  lam <- rep(0, ncol(C))
  f <- function(l) { s <- as.vector(C %*% l); m <- max(s); m + log(mean(exp(s - m))) }
  for (it in seq_len(maxit)) {
    s <- as.vector(C %*% lam); w <- exp(s - max(s)); w <- w / sum(w)
    g <- colSums(w * C)
    if (max(abs(g)) < tol) break
    Cc <- sweep(C, 2, g); H <- crossprod(Cc, Cc * w)
    step <- -solve(H + diag(1e-10, ncol(C)), g); t <- 1
    while (f(lam + t * step) > f(lam) + 1e-4 * t * sum(g * step) && t > 1e-8) t <- t / 2
    lam <- lam + t * step
  }
  s <- as.vector(C %*% lam); w <- exp(s - max(s)); w <- w / sum(w)
  attr(w, "max_imbalance_sd") <- max(abs(colSums(w * C)))
  attr(w, "dropped") <- dropped
  w
}
bal_formula_window <- ~ pre_band + earlier_band + age + ldeg + lrec + prior_status + fed_exec
bal_formula_es <- ~ age + ldeg + lrec + prior_status + fed_exec
make_weights <- function(S, bal_formula) {
  S[, w := 0]
  for (e in elections) {
    ix <- which(S$election == e)
    Xb <- model.matrix(bal_formula, data = S[ix])[, -1, drop = FALSE]
    tgt <- colMeans(Xb[S$follower[ix] == 1L, , drop = FALSE])
    nn <- ix[S$group[ix] == "N"]
    wt <- eb_weights(Xb[S$group[ix] == "N", , drop = FALSE], tgt)
    if (attr(wt, "max_imbalance_sd") > 1e-6 || length(attr(wt, "dropped")))
      message(sprintf("  balancing in %d: max imbalance %.2g s.d.; not balanced: %s", e, attr(wt, "max_imbalance_sd"),
                      paste(attr(wt, "dropped"), collapse = ", ")))
    set(S, i = nn, j = "w", value = as.numeric(wt))
  }
  S
}

# ------------------------------------------------------------------ 4. estimator, linear weights and inference
rp_fit <- function(S, y, formula) {
  X <- model.matrix(formula, data = S)
  N <- which(S$group == "N"); w <- S$w[N]
  X0 <- X[N, , drop = FALSE]; keepc <- colSums(abs(X0)) > 0; X0 <- X0[, keepc, drop = FALSE]; X <- X[, keepc, drop = FALSE]
  M <- solve(crossprod(X0, X0 * w)); beta <- M %*% crossprod(X0, w * y[N])
  pred <- as.vector(X %*% beta); res <- y - pred
  out <- list()
  for (G in c("D", "P")) {
    a <- numeric(nrow(S)); b <- 0
    es <- elections[sapply(elections, function(e) any(S$group == G & S$election == e))]
    for (e in es) { ix <- which(S$group == G & S$election == e); a[ix] <- 1 / (length(es) * length(ix))
                    b <- b + colMeans(X[ix, , drop = FALSE]) / length(es) }
    a[N] <- -w * as.vector(X0 %*% (M %*% b))
    est <- sum(a * y)
    by_e <- data.table(election = S$election, g = S$group, r = res)[g == G, .(estimate = mean(r), n = .N), by = election]
    u <- res
    gi <- which(S$group == G); u[gi] <- res[gi] - ave(res[gi], S$election[gi])
    out[[G]] <- list(est = est, a = a, u = u, res = res, by_e = by_e)
  }
  out
}
cr_var <- function(a, u, cl, keep) {
  s <- tapply((a * u)[keep], cl[keep], sum); G <- length(s); G / (G - 1) * sum(s^2)
}
rp_inference <- function(S, fit, B = 50000L) {
  P <- fit$P; D <- fit$D
  inP <- S$group %in% c("P", "N")
  seP <- sqrt(cr_var(P$a, P$u, S$cluster, inP))
  # D: group shocks from the losing groups' mean residuals (centred within succession), Ferman-Pinto rescaling.
  dg <- data.table(cl = S$cluster, e = S$election, g = S$group, r = P$res)[g == "P", .(r = mean(r), n = .N), by = .(cl, e)]
  dg[, rc := r - weighted.mean(r, n), by = e]
  ab <- pmax(0, coef(lm(I(rc^2) ~ I(1 / n), data = dg)))
  if (sum(ab) <= 0) ab <- c(0, mean(dg$rc^2 * dg$n))
  z <- dg$rc / sqrt(pmax(ab[1] + ab[2] / dg$n, 1e-12)); z <- (z - mean(z)) / sd(z)
  nD <- D$by_e$n; E9 <- length(nD)
  draws <- colSums(matrix(base::sample(z, E9 * B, replace = TRUE), nrow = E9) * sqrt(ab[1] + ab[2] / nD)) / E9
  seN <- sqrt(cr_var(D$a, D$u, S$cluster, S$group == "N"))
  draws <- draws + rnorm(B, 0, seN)
  q <- quantile(draws, c(.025, .975), names = FALSE, type = 1)
  q90 <- quantile(draws, c(.05, .95), names = FALSE, type = 1)
  data.table(group = c("D", "P"), estimate = c(D$est, P$est),
             ci_lower = c(D$est - q[2], P$est - 1.96 * seP), ci_upper = c(D$est - q[1], P$est + 1.96 * seP),
             ci90_lower = c(D$est - q90[2], P$est - 1.645 * seP), ci90_upper = c(D$est - q90[1], P$est + 1.645 * seP),
             se = c(sd(draws), seP), p_value = c(mean(abs(draws) >= abs(D$est)), 2 * pnorm(-abs(P$est / seP))),
             inference = c("Ferman-Pinto bootstrap, losing groups as donors", "clustered by contender group / unaligned politician"))
}
run_window <- function(S, formula, label) {
  r <- rp_inference(S, rp_fit(S, S$delta, formula))
  r[, `:=`(spec = label, n_D = sum(S$group == "D"), n_P = sum(S$group == "P"), n_N = sum(S$group == "N"))]
}

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
lab <- c(pre_bandmiddle = "Baseline rung 5-7", pre_bandhigh = "Baseline rung 8-11", earlier_bandlow = "Rung 1-4 in e-9..e-6",
         earlier_bandmiddle = "Rung 5-7 in e-9..e-6", earlier_bandhigh = "Rung 8-11 in e-9..e-6", age = "Age",
         ldeg = "Log(1 + dated ties)", lrec = "Log(1 + ranked posts)", prior_statusno_direct = "Previous cohort, untied",
         prior_statusprev_loser = "Previous cohort, tied to a loser", prior_statusprev_winner = "Previous cohort, tied to the designee",
         fed_exec = "Federal executive post")
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

pd <- copy(es)[, x := k + fifelse(group == "D", -0.12, 0.12)]
pd[, lab := fifelse(group == "D", "Designee's followers", "Losing contenders' followers")]
top <- max(pd$ci_upper); bot <- min(pd$ci_lower); span <- top - bot
mk <- data.table(x = c(-1.5, 0.5, 6.5), lab = c("Designation", "New president", "Next president"))
g <- ggplot(pd, aes(x, estimate)) +
  geom_hline(yintercept = 0, colour = RULE, linewidth = 0.35) +
  geom_vline(data = mk, aes(xintercept = x), colour = RULE, linewidth = 0.35, linetype = "dashed") +
  geom_text(data = mk, aes(x = x + 0.12, y = top + 0.10 * span, label = lab), hjust = 0, vjust = 0, colour = MUTED, size = 4.2, family = FAM) +
  geom_linerange(aes(ymin = ci_lower, ymax = ci_upper, colour = group), linewidth = 0.45, show.legend = FALSE) +
  geom_linerange(aes(ymin = ci90_lower, ymax = ci90_upper, colour = group), linewidth = 1.5, show.legend = FALSE) +
  geom_point(aes(shape = group, colour = group), fill = "white", size = 2.6, stroke = 0.8) +
  scale_colour_manual(values = c(D = INK, P = "#7a7a7a"), labels = c(D = "Designee's followers", P = "Losers' followers"), name = NULL) +
  scale_shape_manual(values = c(D = 16, P = 21), labels = c(D = "Designee's followers", P = "Losers' followers"), name = NULL) +
  scale_x_continuous(breaks = ks, labels = k_labels_ascii) +
  coord_cartesian(ylim = c(bot - 0.03 * span, top + 0.20 * span), clip = "off") +
  labs(x = "Year relative to the presidential election (e)",
       y = "Gap with comparable unaligned,\nrank since e-2 (rungs)") + theme_paper(17) +
  theme(legend.position = "inside", legend.position.inside = c(0.01, 0.80), legend.justification = c(0, 1),
        legend.text = element_text(size = 14, colour = INK), legend.key = element_blank(), legend.background = element_blank())
ggsave(file.path(out_dir, "es_reward_punishment.pdf"), g, width = 10, height = 4.1, bg = "white", device = "pdf")
ggsave(file.path(out_dir, "es_reward_punishment.png"), g, width = 10, height = 4.1, dpi = 250, bg = "white")

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
bl <- c("% rp_balance.tex (reward_punishment.R)", "\\begin{tabular}{lrrrrr}", "\\toprule",
        " & & \\multicolumn{2}{c}{Unaligned} & \\multicolumn{2}{c}{Standardized difference} \\\\",
        "\\cmidrule(lr){3-4}\\cmidrule(lr){5-6}", " & Followers & Raw & Weighted & Raw & Weighted \\\\", "\\midrule")
for (i in seq_len(nrow(balance))) {
  d <- if (balance$variable[i] == "Age") 1 else 2
  bl <- c(bl, sprintf("%s & %s & %s & %s & %s & %s \\\\", gsub("e-9..e-6", "$e-9,\\dots,e-6$", balance$variable[i], fixed = TRUE),
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
  mac("RPdiff", f2(dm$difference)), mac("RPdiffLo", f2(dm$difference_lo)), mac("RPdiffHi", f2(dm$difference_hi)),
  mac("RPshare", round(100 * dm$reward_share)), mac("RPshareLo", round(100 * dm$reward_share_lo)), mac("RPshareHi", round(100 * dm$reward_share_hi)),
  mac("RPshareMin", round(100 * min(rows$share))), mac("RPshareMax", round(100 * max(rows$share))),
  mac("RPnKept", format(sum(S_main$group == "N"), big.mark = ",")), mac("RPnUnaligned", format(sum(A$group == "N"), big.mark = ",")),
  mac("RPessMin", round(min(ess$ess))), mac("RPessMax", round(max(ess$ess))),
  mac("RPpenaltyEnd", "5")), file.path(tab_dir, "rp_macros.tex"))
