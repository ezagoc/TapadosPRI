# Does the premium reach the followers' followers? (20 October 2026.)
# Population: eligible politicians with no direct tie to any slate contender by e-2 (n_direct == 0). Second-degree
# exposure = a dated tie of the four types, formed by e-2, to an exclusive direct follower (the main sample) of
# exactly one contender's camp: D2 (the designee's followers only), P2 (one losing contender's followers only), M2 (two
# or more camps; excluded, as the multi-tied are in the main design), N2 (no second-degree tie). Two versions: all dated
# ties, and strong ties (focus_size <= 10) at both steps (the follower's own tie to the contender must be strong too).
# Estimates: the section-4 window contrast D2 vs P2 (section-5 bootstrap), its section-7 event study, and D2 and P2 each
# against N2 (reward and penalty at two steps; approximate inference in the style of section 11).
# Caveat found on the first run: in 1940 the designee's side at two steps is one politician (Gutierrez Cazares, rung 8 in
# 1937 only), who carries a whole succession weight; the windows table adds the contrast without 1940 and with person weights.
# Run after estimate_main.R, from the repo root: Rscript code/04-analysis/main_direct_tie/indirect_ties.R
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
invisible(capture.output(source(file.path(script_dir, "estimate_main.R"))))
source(file.path(script_dir, "design_tools.R"))
seed_ind <- 20102026L
set.seed(seed_ind)
B_ind <- 20000L
ks <- -7:8; ref <- -2L
main_sample <- copy(sample)          # the exclusive direct followers (intermediaries)
direct_levels <- levels(main_sample$prior_status)

# ------------------------------------------------------------------ 1. second-degree groups
lt <- dated[edge_type %in% tie_types]
lt_long <- rbindlist(list(lt[, .(pid = person_a, other = person_b, year_start, focus_size)],
                          lt[, .(pid = person_b, other = person_a, year_start, focus_size)]))
is_strong <- function(z) !is.na(z$focus_size) & z$focus_size <= 10

prior_status_of <- function(d, e) {
  prior <- eligible[[as.character(e - 6L)]]
  if (is.null(prior)) return(rep("absent", nrow(d)))
  p <- prior[match(d$pid, pid)]
  z <- fifelse(is.na(p$pid), "absent", fifelse(p$prior_winner_tie == 1L, "prev_winner",
                                               fifelse(p$n_direct > 0L, "prev_loser", "no_direct")))
  z[is.na(z)] <- "no_direct"
  z
}

build_groups <- function(strong) {
  rbindlist(lapply(elections, function(e) {
    t0 <- e - 2L; sl <- slates[[as.character(e)]]
    pool <- eligible[[as.character(e)]]
    fol <- main_sample[election == e, .(pid, patron)]
    if (strong) {   # first step: the follower's tie to his contender formed in a cohort of at most 10
      ok <- lt_long[other %in% sl$candidates & year_start <= t0]
      ok <- unique(ok[is_strong(ok), .(pid, patron = other)])
      fol <- fol[ok, on = .(pid, patron), nomatch = 0L]
    }
    una <- copy(pool[n_direct == 0L])
    step <- lt_long[year_start <= t0 & pid %in% una$pid & other %in% fol$pid]
    if (strong) step <- step[is_strong(step)]
    step <- unique(step[, .(pid, follower = other)])
    step[, patron := fol$patron[match(follower, fol$pid)]]
    camps <- unique(step[, .(pid, patron)])[, .(n_camps = .N, patron2 = patron[1]), by = pid]
    nfol <- step[, .(n_followers = uniqueN(follower)), by = pid]
    una[, n_camps := camps$n_camps[match(pid, camps$pid)]]; una[is.na(n_camps), n_camps := 0L]
    una[, patron2 := camps$patron2[match(pid, camps$pid)]]
    una[, n_followers := nfol$n_followers[match(pid, nfol$pid)]]; una[is.na(n_followers), n_followers := 0L]
    una[, group := fifelse(n_camps == 0L, "N2", fifelse(n_camps >= 2L, "M2", fifelse(patron2 == sl$winner, "D2", "P2")))]
    una[, prior_status := prior_status_of(una, e)]
    una[, intermediaries := nrow(fol)]
    una[, .(pid, election, group, patron = patron2, n_followers, intermediaries, age, pre, earlier, post, delta, ldeg, lrec,
            prior_status)]
  }))
}
groups <- list(all = build_groups(FALSE), strong = build_groups(TRUE))

# Analysis table with the main sample's columns and factor levels.
prepare <- function(G) {
  S <- copy(G)
  S[, treated := as.integer(group == "D2")]
  S[, pre_band := factor(fifelse(pre <= 4L, "low", fifelse(pre <= 7L, "middle", "high")), levels = c("low", "middle", "high"))]
  S[, earlier_band := factor(fifelse(earlier == 0L, "none", fifelse(earlier <= 4L, "low", fifelse(earlier <= 7L, "middle", "high"))),
                             levels = c("none", "low", "middle", "high"))]
  S[, prior_status := factor(prior_status, levels = direct_levels)]
  S[, election_factor := factor(election, levels = elections)]
  S[, network := fifelse(group == "N2", paste(election, "N", sep = "_"), paste(election, patron, sep = "_"))]
  setorder(S, election, group, network, pid)
  S
}

sizes <- rbindlist(lapply(names(groups), function(v) {
  g <- groups[[v]]
  g[, .(version = v, unaligned_pool = .N, intermediaries = intermediaries[1], D2 = sum(group == "D2"), P2 = sum(group == "P2"),
        M2 = sum(group == "M2"), N2 = sum(group == "N2"), D2_camps = 1L, P2_camps = uniqueN(patron[group == "P2"])), by = election]
}))
sizes[, share_two_steps := (D2 + P2 + M2) / unaligned_pool]
setorder(sizes, version, election)

# ------------------------------------------------------------------ 2. estimator helpers
# Try covariate sets in order; the first whose control model has full rank is used (MAIN_SPEC section 4: combine
# adjacent rank bands rather than drop a succession). Returns the design and the label of the covariates used.
try_designs <- function(formulas, ...) {
  for (f in formulas) {
    d <- tryCatch(build_design(formula = f$formula, ...), error = function(e) NULL)
    if (!is.null(d)) return(list(d = d, covariates = f$label))
  }
  stop("No covariate set gives a full-rank control model.")
}
window_formulas <- list(
  list(label = "section 4 covariates", formula = formula_x),
  list(label = "earlier band collapsed to none / low / middle-or-high",
       formula = ~ election_factor + pre_band + earlier_band2 + age + ldeg + lrec + prior_status),
  list(label = "without the earlier band", formula = ~ election_factor + pre_band + age + ldeg + lrec + prior_status),
  list(label = "without the rank bands", formula = formula_es))
es_formulas <- list(
  list(label = "section 7 covariates", formula = formula_es),
  list(label = "prior status collapsed to absent / no direct tie / any prior tie",
       formula = ~ election_factor + age + ldeg + lrec + prior_status3),
  list(label = "without prior status", formula = ~ election_factor + age + ldeg + lrec))
add_collapsed <- function(S) {
  S[, earlier_band2 := factor(fifelse(earlier_band == "none", "none", fifelse(earlier_band == "low", "low", "middle_high")),
                              levels = c("none", "low", "middle_high"))]
  S[, prior_status3 := factor(fifelse(prior_status == "absent", "absent", fifelse(prior_status == "no_direct", "no_direct", "any_tie")),
                              levels = c("absent", "no_direct", "any_tie"))]
  S
}
succ_string <- function(es) paste(es, collapse = " ")
dropped_string <- function(es) { z <- setdiff(elections, es); if (length(z)) paste(z, collapse = " ") else "" }

# Group G against N2: the section-4 estimator with N2 as the control pool (weights 1/n_N2e, equal weight per succession
# in which G is present). Linear weights, residuals under the N2 model, and the successions used.
vs_n2_fit <- function(tab, y, formula, G) {
  X <- model.matrix(formula, data = tab)
  N <- which(tab$group == "N2")
  n0 <- table(tab$election[N]); w <- 1 / as.numeric(n0[as.character(tab$election[N])])
  X0 <- X[N, , drop = FALSE]; keepc <- colSums(abs(X0)) > 0; X0 <- X0[, keepc, drop = FALSE]; X <- X[, keepc, drop = FALSE]
  if (qr(X0 * sqrt(w))$rank != ncol(X0)) stop("N2 control model is rank-deficient.")
  M <- solve(crossprod(X0, X0 * w)); beta <- M %*% crossprod(X0, w * y[N])
  res <- y - as.vector(X %*% beta)
  es <- elections[sapply(elections, function(e) any(tab$group == G & tab$election == e))]
  # succession weights: the main estimand's rule with the D2 group's shares in both contrasts (D2 - P2 keeps that weighting)
  nD2 <- sapply(es, function(e) sum(tab$group == "D2" & tab$election == e)); if (sum(nD2) == 0) nD2 <- rep(1, length(es))
  om <- omega_for(es, nD2)
  a <- numeric(nrow(tab)); b <- 0
  for (e in es) {
    ix <- which(tab$group == G & tab$election == e)
    a[ix] <- om[[as.character(e)]] / length(ix); b <- b + om[[as.character(e)]] * colMeans(X[ix, , drop = FALSE])
  }
  a[N] <- -w * as.vector(X0 %*% (M %*% b))
  list(est = sum(a * y), a = a, res = res, successions = es, G = G)
}
# Approximate inference for G vs N2 (MAIN_SPEC section 11 logic). Network shocks: the P2 camps' mean residuals under
# the N2 model, centred within succession, variance A + B/n fitted on those camps (no leverage correction), resampled
# for every treated network and rescaled by its size; N2 side: normal with politician-clustered variance of sum a_i r_i.
vs_n2_inference <- function(tab, fit, B = B_ind, seed = seed_ind) {
  set.seed(seed)
  dg <- data.table(net = tab$network, e = tab$election, g = tab$group, r = fit$res)[g == "P2", .(r = mean(r), n = .N), by = .(net, e)]
  dg[, rc := r - weighted.mean(r, n), by = e]
  ab <- pmax(0, coef(lm(I(rc^2) ~ I(1 / n), data = dg))); if (sum(ab) <= 0) ab <- c(0, mean(dg$rc^2 * dg$n))
  z <- dg$rc / sqrt(pmax(ab[1] + ab[2] / dg$n, 1e-12)); z <- (z - mean(z)) / sd(z)
  tn <- data.table(net = tab$network, g = tab$group, a = fit$a)[g == fit$G, .(gw = sum(a), n = .N), by = net]
  draws <- colSums(matrix(base::sample(z, nrow(tn) * B, replace = TRUE), nrow = nrow(tn)) * tn$gw * sqrt(ab[1] + ab[2] / tn$n))
  ni <- tab$group == "N2"
  s <- tapply((fit$a * fit$res)[ni], tab$pid[ni], sum); Gc <- length(s)
  draws <- draws + rnorm(B, 0, sqrt(Gc / (Gc - 1) * sum(s^2)))
  q <- quantile(draws, c(.025, .975), names = FALSE, type = 1); q90 <- quantile(draws, c(.05, .95), names = FALSE, type = 1)
  data.table(estimate = fit$est, ci_lower = fit$est - q[2], ci_upper = fit$est - q[1], ci90_lower = fit$est - q90[2],
             ci90_upper = fit$est - q90[1], p_bootstrap = mean(abs(draws) >= abs(fit$est)),
             n = sum(tab$group %in% c(fit$G, "N2") & tab$election %in% fit$successions),
             n_treated = sum(tab$group == fit$G), A = ab[1], B = ab[2], treated_networks = nrow(tn))
}
# As build_design, only the successions in which G is present enter the control model (and the donor shocks).
vs_n2_run <- function(tab, y, formulas, G, B = B_ind, seed = seed_ind) {
  es <- elections[sapply(elections, function(e) any(tab$group == G & tab$election == e))]
  keep <- tab$election %in% es
  tab <- tab[keep]; y <- y[keep]
  for (f in formulas) {
    fit <- tryCatch(vs_n2_fit(tab, y, f$formula, G), error = function(e) NULL)
    if (!is.null(fit)) return(vs_n2_inference(tab, fit, B, seed)[, `:=`(covariates = f$label,
                              successions_used = succ_string(fit$successions), dropped = dropped_string(fit$successions))])
  }
  stop("No covariate set gives a full-rank N2 model.")
}
yr_of <- function(tab, k) { z <- annual[data.table(pid = tab$pid, year = tab$election + k), on = .(pid, year), rank]; z[is.na(z)] <- 0L; z }

# ------------------------------------------------------------------ 3. estimates, both versions
windows <- list(); es_all <- list(); designs <- list()
for (v in names(groups)) {
  S_all <- add_collapsed(prepare(groups[[v]]))
  # --- D2 vs P2: the section-4 estimator and section-5 bootstrap on the followers' followers of one camp
  sample <- S_all[group %in% c("D2", "P2")]
  td <- try_designs(window_formulas)
  d <- td$d
  w_dp <- estimate_columns(d, cbind(y = sample$delta[d$rows]), B = B_ind, seed = seed_ind)$table
  w_dp[, `:=`(version = v, contrast = "D2-P2", n_treated = n_designee, successions_used = succ_string(d$elections),
              dropped = dropped_string(d$elections), covariates = td$covariates,
              inference = "Ferman-Pinto bootstrap, P2 camps as donors")]
  te <- try_designs(es_formulas); d_es <- te$d
  Y <- sapply(ks, function(k) year_value(annual, k)); colnames(Y) <- ks
  Ym <- (Y[, colnames(Y) != as.character(ref)] - Y[, as.character(ref)])[d_es$rows, , drop = FALSE]
  e_dp <- estimate_columns(d_es, Ym, B = B_ind, seed = seed_ind + 1L)$table
  e_dp <- rbind(e_dp[, .(k = as.integer(column), estimate, ci_lower, ci_upper, ci90_lower, ci90_upper, p_bootstrap)],
                data.table(k = ref, estimate = 0, ci_lower = 0, ci_upper = 0, ci90_lower = 0, ci90_upper = 0, p_bootstrap = NA_real_))
  e_dp[, `:=`(version = v, contrast = "D2-P2", covariates = te$covariates, successions_used = succ_string(d_es$elections))]
  designs[[v]] <- list(window = d, es = d_es, S = copy(sample))
  # Robustness of D2 vs P2 (not prespecified; added after seeing that the 1940 designee's side at two steps is one
  # politician, who carries a whole succession weight): without 1940, and successions weighted by the designee's side.
  rob <- list()
  if (any(sample$election == 1940L & sample$treated == 1L)) {
    S_dp <- copy(sample)
    sample <- S_dp[election != 1940L][, election_factor := droplevels(election_factor)]   # 1940 is the base level
    td40 <- try_designs(window_formulas)
    rob$no1940 <- estimate_columns(td40$d, cbind(y = sample$delta[td40$d$rows]), B = B_ind, seed = seed_ind + 2L)$table[
      , `:=`(spec = "without 1940 (single D2 politician)", covariates = td40$covariates, successions_used = succ_string(td40$d$elections),
             dropped = dropped_string(td40$d$elections))]
    sample <- S_dp
  }
  tdp <- try_designs(window_formulas, weights = "person")
  rob$person <- estimate_columns(tdp$d, cbind(y = sample$delta[tdp$d$rows]), B = B_ind, seed = seed_ind + 3L)$table[
    , `:=`(spec = "successions weighted by the designee's side", covariates = tdp$covariates, successions_used = succ_string(tdp$d$elections),
           dropped = dropped_string(tdp$d$elections))]
  rob <- rbindlist(rob)[, `:=`(version = v, contrast = "D2-P2", n_treated = n_designee,
                               inference = "Ferman-Pinto bootstrap, P2 camps as donors")]
  windows[[paste(v, "rob")]] <- rob
  # --- D2 vs N2 and P2 vs N2 on the stacked table (D2, P2, N2); the P2 rows only supply the donor shocks for D2
  T3 <- S_all[group %in% c("D2", "P2", "N2")]
  YT <- sapply(ks, function(k) yr_of(T3, k)); colnames(YT) <- ks
  for (G in c("D2", "P2")) {
    wn <- vs_n2_run(T3, T3$delta, window_formulas, G, seed = seed_ind + 10L)
    wn[, `:=`(version = v, contrast = paste0(G, "-N2"), spec = "main",
              inference = "approximate: P2-camp shocks + politician-clustered N2 noise")]
    windows[[paste(v, G)]] <- wn
    en <- rbindlist(lapply(setdiff(ks, ref), function(k) {
      y <- YT[, as.character(k)] - YT[, as.character(ref)]
      vs_n2_run(T3, y, es_formulas, G, seed = seed_ind + 100L + k)[, k := k]
    }))
    en <- rbind(en[, .(k, estimate, ci_lower, ci_upper, ci90_lower, ci90_upper, p_bootstrap, covariates, successions_used)],
                data.table(k = ref, estimate = 0, ci_lower = 0, ci_upper = 0, ci90_lower = 0, ci90_upper = 0, p_bootstrap = NA_real_,
                           covariates = en$covariates[1], successions_used = en$successions_used[1]))
    en[, `:=`(version = v, contrast = paste0(G, "-N2"))]
    es_all[[paste(v, G)]] <- en
  }
  # sanity: the D2-N2 point estimate equals build_design's with the N2 rows as the control pool (network election_N)
  sample <- T3[group %in% c("D2", "N2")]
  chk <- tryCatch(build_design(formula = as.formula(window_formulas[[match(windows[[paste(v, "D2")]]$covariates,
                                                                          sapply(window_formulas, `[[`, "label"))]]$formula)),
                  error = function(e) NULL)
  if (!is.null(chk)) stopifnot(abs(sum(chk$a * sample$delta[chk$rows]) - windows[[paste(v, "D2")]]$estimate) < 1e-8)
  windows[[paste(v, "DP")]] <- w_dp[, spec := "main"]
  es_all[[paste(v, "DP")]] <- e_dp
}
sample <- main_sample

windows <- rbindlist(windows, fill = TRUE)[, .(version, contrast, spec, estimate, ci_lower, ci_upper, ci90_lower, ci90_upper, p_bootstrap,
                                               n, n_treated, successions_used, dropped, covariates, inference, A, B, treated_networks)]
windows[, spec := factor(spec, levels = c("main", "without 1940 (single D2 politician)", "successions weighted by the designee's side"))]
setorder(windows, version, contrast, spec); windows[, spec := as.character(spec)]
es_tab <- rbindlist(es_all, use.names = TRUE)[, .(version, contrast, k, estimate, ci_lower, ci_upper, ci90_lower, ci90_upper, p_bootstrap,
                                                  covariates, successions_used)]
setorder(es_tab, version, contrast, k)
es_tab[, window_average_1_4 := mean(estimate[k %in% 1:4]), by = .(version, contrast)]
es_tab[, lead_average := mean(estimate[k %in% -7:-3]), by = .(version, contrast)]

fwrite(sizes, file.path(out_dir, "indirect_ties_sizes.csv"))
fwrite(windows, file.path(out_dir, "indirect_ties_windows.csv"))
fwrite(es_tab, file.path(out_dir, "indirect_ties_event_study.csv"))

# ------------------------------------------------------------------ 4. figure: strong-ties D2 vs P2 event study
es_figure(es_tab[version == "strong" & contrast == "D2-P2"], "Effect on rank position,\ntwo steps from the contender", "es_indirect")

# ------------------------------------------------------------------ 5. table and macros
tab_dir <- file.path(out_dir, "tables"); dir.create(tab_dir, showWarnings = FALSE)
f2 <- function(x, d = 2) { v <- round(x, d); s <- formatC(abs(v), format = "f", digits = d); ifelse(v < 0, paste0("$-$", s), s) }
ci_txt <- function(lo, hi, d = 2) paste0("[", f2(lo, d), ", ", f2(hi, d), "]")
pv <- function(p) if (p < 0.001) "$<$0.001" else f2(p, 3)
mac <- function(n, v) sprintf("\\newcommand{\\%s}{%s}", n, v)
direct <- fread(file.path(out_dir, "robustness.csv"))[1]
w_all <- windows[version == "all" & contrast == "D2-P2" & spec == "main"]; w_str <- windows[version == "strong" & contrast == "D2-P2" & spec == "main"]
r_all <- windows[version == "all" & contrast == "D2-P2" & spec != "main"]; r_str <- windows[version == "strong" & contrast == "D2-P2" & spec != "main"]
tl <- c("% indirect_ties.tex (indirect_ties.R)", "\\begin{tabular}{lrrrr}", "\\toprule",
        " & Estimate & 95\\% interval & Politicians & Designee's side \\\\", "\\midrule",
        sprintf("Direct followers & %s & %s & %s & %s \\\\", f2(direct$estimate), ci_txt(direct$ci_lower, direct$ci_upper),
                format(direct$n, big.mark = ","), format(direct$n_designee, big.mark = ",")),
        sprintf("Followers' followers, all ties & %s & %s & %s & %s \\\\", f2(w_all$estimate), ci_txt(w_all$ci_lower, w_all$ci_upper),
                format(w_all$n, big.mark = ","), format(w_all$n_treated, big.mark = ",")),
        sprintf("Followers' followers, strong ties & %s & %s & %s & %s \\\\", f2(w_str$estimate), ci_txt(w_str$ci_lower, w_str$ci_upper),
                format(w_str$n, big.mark = ","), format(w_str$n_treated, big.mark = ",")),
        "\\bottomrule", "\\end{tabular}")
writeLines(tl, file.path(tab_dir, "indirect_ties.tex"))
share_all <- sizes[version == "all", sum(D2 + P2 + M2) / sum(unaligned_pool)]
share_str <- sizes[version == "strong", sum(D2 + P2 + M2) / sum(unaligned_pool)]
writeLines(c("% indirect_macros.tex (indirect_ties.R). Do not edit by hand.",
  mac("INDstrongEst", f2(w_str$estimate)), mac("INDstrongLo", f2(w_str$ci_lower)), mac("INDstrongHi", f2(w_str$ci_upper)),
  mac("INDstrongP", pv(w_str$p_bootstrap)),
  mac("INDallEst", f2(w_all$estimate)), mac("INDallLo", f2(w_all$ci_lower)), mac("INDallHi", f2(w_all$ci_upper)),
  mac("INDallP", pv(w_all$p_bootstrap)),
  mac("INDnStrongD", format(w_str$n_treated, big.mark = ",")), mac("INDnStrongP", format(w_str$n - w_str$n_treated, big.mark = ",")),
  mac("INDnAllD", format(w_all$n_treated, big.mark = ",")), mac("INDnAllP", format(w_all$n - w_all$n_treated, big.mark = ",")),
  mac("INDshareTwoStepsAll", round(100 * share_all)), mac("INDshareTwoStepsStrong", round(100 * share_str)),
  mac("INDstrongDropped", if (nzchar(w_str$dropped)) w_str$dropped else "none"),
  mac("INDstrongNoFortyEst", f2(r_str[grepl("^without 1940", spec), estimate])),
  mac("INDstrongNoFortyLo", f2(r_str[grepl("^without 1940", spec), ci_lower])),
  mac("INDstrongNoFortyHi", f2(r_str[grepl("^without 1940", spec), ci_upper])),
  mac("INDallNoFortyEst", f2(r_all[grepl("^without 1940", spec), estimate])),
  mac("INDallNoFortyLo", f2(r_all[grepl("^without 1940", spec), ci_lower])),
  mac("INDallNoFortyHi", f2(r_all[grepl("^without 1940", spec), ci_upper])),
  mac("INDstrongPersonEst", f2(r_str[grepl("^successions weighted", spec), estimate])),
  mac("INDallPersonEst", f2(r_all[grepl("^successions weighted", spec), estimate])),
  mac("INDstrongWindowEs", f2(es_tab[version == "strong" & contrast == "D2-P2", window_average_1_4][1])),
  mac("INDstrongRewardEst", f2(windows[version == "strong" & contrast == "D2-N2" & spec == "main", estimate])),
  mac("INDstrongRewardLo", f2(windows[version == "strong" & contrast == "D2-N2" & spec == "main", ci_lower])),
  mac("INDstrongRewardHi", f2(windows[version == "strong" & contrast == "D2-N2" & spec == "main", ci_upper])),
  mac("INDstrongPenaltyEst", f2(windows[version == "strong" & contrast == "P2-N2" & spec == "main", estimate])),
  mac("INDstrongPenaltyLo", f2(windows[version == "strong" & contrast == "P2-N2" & spec == "main", ci_lower])),
  mac("INDstrongPenaltyHi", f2(windows[version == "strong" & contrast == "P2-N2" & spec == "main", ci_upper]))),
  file.path(tab_dir, "indirect_macros.tex"))

# ------------------------------------------------------------------ 6. console
r3 <- function(d) d[, lapply(.SD, function(x) if (is.numeric(x)) round(x, 3) else x)]
cat("Second-degree groups (unaligned pool, n_direct == 0):\n"); print(sizes)
cat(sprintf("Share of the unaligned pool within two steps of some camp: all ties %.1f%%, strong ties %.1f%%\n",
            100 * share_all, 100 * share_str))
cat("\nWindow contrasts (rungs):\n")
print(r3(windows[, .(version, contrast, spec, estimate, ci_lower, ci_upper, p_bootstrap, n, n_treated, dropped, covariates)]))
cat(sprintf("\nDirect followers (robustness.csv row 1): %.2f [%.2f, %.2f]\n", direct$estimate, direct$ci_lower, direct$ci_upper))
cat("\nEvent studies (rungs):\n")
print(r3(dcast(es_tab, version + contrast ~ k, value.var = "estimate")))
print(r3(unique(es_tab[, .(version, contrast, lead_average, window_average_1_4, covariates)])))
cat("Wrote:", file.path(out_dir, "indirect_ties_{sizes,windows,event_study}.csv"), "es_indirect.{pdf,png}, tables/indirect_ties.tex, tables/indirect_macros.tex\n")
