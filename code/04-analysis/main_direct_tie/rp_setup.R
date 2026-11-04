# Shared setup for reward_punishment.R and chair_split.R (MAIN_SPEC sections 11-12): the eligible designee's (D),
# losing contenders' (P) and unaligned (N) politicians, common support, entropy balancing and the linear estimator.
# Sourced after estimate_main.R and design_tools.R.
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
# Succession weights of the reward and penalty contrasts: the main estimand's rule (estimate_main.R succession_weights),
# with the designee's followers' shares in BOTH contrasts, so that reward - penalty keeps the main estimand's weighting.
rp_omega <- function(S, es) omega_for(es, sapply(es, function(e) sum(S$group == "D" & S$election == e)))
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
    om <- rp_omega(S, es)
    for (e in es) { ix <- which(S$group == G & S$election == e); a[ix] <- om[[as.character(e)]] / length(ix)
                    b <- b + om[[as.character(e)]] * colMeans(X[ix, , drop = FALSE]) }
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
  nD <- D$by_e$n; E9 <- length(nD); omD <- rp_omega(S, D$by_e$election)[as.character(D$by_e$election)]
  draws <- colSums(matrix(base::sample(z, E9 * B, replace = TRUE), nrow = E9) * (omD * sqrt(ab[1] + ab[2] / nD)))
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

# ------------------------------------------------------------------ the patron's chair after the succession (MAIN_SPEC 12)
patrons <- rbindlist(lapply(elections, function(e) {
  sl <- slates[[as.character(e)]]; los <- setdiff(sl$candidates, sl$winner)
  runner <- contenders[election_year == e & in_main_slate == 1L & role == "runner_up", person_id]
  data.table(election = e, patron = los, rung_post2 = highest_rank(los, e + 1L, e + 2L), rung_post3 = highest_rank(los, e + 1L, e + 3L),
             rung_pre = highest_rank(los, e - 2L, e - 2L), age = e - as.numeric(birth[as.character(los)]),
             runner_up = as.integer(los %in% runner))
}))
nf <- A[group == "P", .(followers = .N), by = .(election, patron)]
patrons <- merge(patrons, nf, by = c("election", "patron"), all.x = TRUE)[is.na(followers), followers := 0L]
split_groups <- function(S, rung_col = "rung_post2", cut = 8L) {
  S <- copy(S); pc <- patrons[[rung_col]][match(paste(S$election, S$patron), paste(patrons$election, patrons$patron))]
  S[, g := fifelse(group == "P", fifelse(pc >= cut, "Pk", "Pl"), group)]
  S
}

# ------------------------------------------------------------------ linear estimators against the reweighted unaligned (MAIN_SPEC 12)
# targets: list of (group, sign); `within` restricts to successions where every listed group exists (within-succession contrast).
lin_fit <- function(S, y, formula, groups, signs = rep(1, length(groups))) {
  X <- model.matrix(formula, data = S)
  N <- which(S$g == "N"); w <- S$w[N]
  X0 <- X[N, , drop = FALSE]; keepc <- colSums(abs(X0)) > 0; X0 <- X0[, keepc, drop = FALSE]; X <- X[, keepc, drop = FALSE]
  M <- solve(crossprod(X0, X0 * w)); beta <- M %*% crossprod(X0, w * y[N]); res <- y - as.vector(X %*% beta)
  es <- Reduce(intersect, lapply(groups, function(G) unique(S$election[S$g == G])))
  a <- numeric(nrow(S)); b <- 0; om <- rp_omega(S, es)
  for (j in seq_along(groups)) for (e in es) {
    ix <- which(S$g == groups[j] & S$election == e); a[ix] <- signs[j] * om[[as.character(e)]] / length(ix)
    b <- b + signs[j] * om[[as.character(e)]] * colMeans(X[ix, , drop = FALSE])
  }
  a[N] <- -w * as.vector(X0 %*% (M %*% b))
  u <- res; gi <- which(S$g %in% groups); u[gi] <- res[gi] - ave(res[gi], S$g[gi], S$election[gi])
  list(est = sum(a * y), a = a, u = u, successions = es)
}
