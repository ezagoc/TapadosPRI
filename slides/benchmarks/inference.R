# Re-estimate the original DiD on each synthetic outcome panel. The intervals
# inherit the original working model of network/person sampling disturbances;
# they are NOT uncertainty about which political allocation rule is correct.
cli <- commandArgs(FALSE)
this_file <- normalizePath(sub("^--file=", "", cli[grepl("^--file=", cli)][1]))
source(file.path(dirname(this_file), "prepare.R"))   # defines work (TAPADOS_BENCH_DIR) and the design objects
reward_out <- file.path(work, "data", "inference")
dir.create(reward_out, recursive = TRUE, showWarnings = FALSE)
paths <- fread(file.path(work, "data", "paths.csv.gz"))
setkey(paths, scope, rule, election, pid, k)
expected <- fread(file.path(work, "data", "assignment_estimates.csv"))
results <- list(); averages <- list(); components <- list(); checks <- list(); obs_averages <- list(); gaps <- list()
set.seed(20261023L)

refit_dp <- function(d, yy) {
  f <- lm.wfit(d$X0, yy[d$ctrl], w = d$w0)
  residual <- yy - as.vector(d$X %*% f$coefficients)
  sum(d$omega[as.character(d$elections)] * vapply(d$elections, function(e) mean(residual[d$S$election == e & d$S$treated == 1L]), 0.0))   # the design's succession weights
}
extract_ci <- function(fit, contrast, outcome) {
  fit$table[, .(contrast = contrast, outcome = outcome, estimate, ci_lower, ci_upper)]
}
for (ne in 9L) {
  grid <- -7:6
  keep <- rep(TRUE, nrow(sample))
  de <- build_design(keep = keep, formula = formula_es)
  dw <- build_design(keep = keep)
  stopifnot(identical(id(de$S), id(dw$S)))
  sn <- S_event
  sw <- S_window
  actual_d <- YA[match(id(de$S), id(A)), as.character(grid), drop = FALSE]
  actual_n <- YA[match(id(sn), id(A)), as.character(grid), drop = FALSE]
  obs_d <- rowMeans(actual_d[, as.character(1:4)]) - actual_d[, as.character(ref)]
  obs_n <- rowMeans(actual_n[, as.character(1:4)]) - actual_n[, as.character(ref)]
  od <- estimate_columns(de, cbind(annual_1_4 = obs_d), B = 50000L, seed = 20261023L)
  on <- rp_inference(sn, rp_fit(sn, obs_n, f_es), B = 50000L)
  obs_averages[[length(obs_averages) + 1L]] <- rbind(
    extract_ci(od, "DP", "annual_1_4"),
    on[, .(contrast = paste0(group, "N"), outcome = "annual_1_4", estimate, ci_lower, ci_upper)])[, n_successions := ne]
  for (scope_value in unique(paths$scope)) for (rule_value in unique(paths$rule)) {
    tab <- paths[.(scope_value, rule_value)]
    setkey(tab, election, pid, k)
    rank_for <- function(S) {
      z <- sapply(grid, function(relative_period) {
        query <- data.table(election = S$election, pid = S$pid, k = rep(relative_period, nrow(S)))
        tab[query, on = .(election, pid, k), rank]
      })
      stopifnot(!anyNA(z)); colnames(z) <- grid; z
    }
    yd <- rank_for(de$S); yn <- rank_for(sn)
    stopifnot(all(yd[, grid <= 0] == actual_d[, grid <= 0]),
              all(yn[, grid <= 0] == actual_n[, grid <= 0]))
    delta_d <- yd - yd[, as.character(ref)]
    dd <- estimate_columns(de, delta_d, B = 50000L, seed = 20261023L)
    dp <- dd$table[, .(contrast = "DP", k = as.integer(column), estimate, ci_lower, ci_upper)]
    components[[length(components) + 1L]] <- dd$components[, `:=`(scope = scope_value, rule = rule_value, n_successions = ne)]
    # A fresh loser-only WLS fit must match the exact linear implementation.
    for (k in grid) {
      value <- refit_dp(de, delta_d[, as.character(k)])
      # Compare by explicit vector index to avoid data.table scope ambiguity.
      check_error <- abs(value - dp$estimate[match(k, dp$k)])
      stopifnot(check_error < 1e-10)
      checks[[length(checks) + 1L]] <- data.table(scope = scope_value, rule = rule_value, ne, k, check = "Fresh WLS vs exact estimator", error = check_error)
    }
    rp <- rbindlist(lapply(grid, function(k) {
      if (k == ref) return(data.table(contrast = c("DN", "PN"), k = k, estimate = 0, ci_lower = 0, ci_upper = 0))
      z <- rp_inference(sn, rp_fit(sn, yn[, as.character(k)] - yn[, as.character(ref)], f_es), B = 50000L)
      z[, .(contrast = paste0(group, "N"), k = k, estimate, ci_lower, ci_upper)]
    }))
    z <- rbind(dp, rp)[, `:=`(scope = scope_value, rule = rule_value, n_successions = ne)]
    saved <- expected[scope == scope_value & rule == rule_value & n_successions == ne]
    z <- merge(z, saved[, .(contrast, k, saved_estimate = estimate)], by = c("contrast", "k"))
    stopifnot(max(abs(z$estimate - z$saved_estimate)) < 1e-10)
    z[, saved_estimate := NULL]
    obs_ci <- rbind(fread(file.path(work, "data", "design", "observed_dp_intervals.csv")),
                    fread(file.path(work, "data", "design", "observed_rp_intervals.csv")))
    for (ii in which(z$k <= 0L)) {
      rr <- obs_ci[contrast == z$contrast[ii] & k == z$k[ii]]
      stopifnot(nrow(rr) == 1L, abs(z$estimate[ii] - rr$estimate) < 1e-10)
      z$ci_lower[ii] <- rr$ci_lower; z$ci_upper[ii] <- rr$ci_upper
    }
    results[[length(results) + 1L]] <- z

    mean_d <- rowMeans(yd[, as.character(1:4)]) - yd[, as.character(ref)]
    mean_n <- rowMeans(yn[, as.character(1:4)]) - yn[, as.character(ref)]
    avg_dp <- estimate_columns(de, cbind(annual_1_4 = mean_d), B = 50000L, seed = 20261023L)
    avg_rp <- rp_inference(sn, rp_fit(sn, mean_n, f_es), B = 50000L)
    a <- rbind(extract_ci(avg_dp, "DP", "annual_1_4"),
               avg_rp[, .(contrast = paste0(group, "N"), outcome = "annual_1_4", estimate, ci_lower, ci_upper)])
    ydw <- apply(yd[, as.character(1:4)], 1, max) - apply(yd[, as.character(-5:-2)], 1, max)
    ynw <- rank_for(sw)
    delta_nw <- apply(ynw[, as.character(1:4)], 1, max) - apply(ynw[, as.character(-5:-2)], 1, max)
    win_dp <- estimate_columns(dw, cbind(window_max_1_4 = ydw), B = 50000L, seed = 20261023L)
    win_rp <- rp_inference(sw, rp_fit(sw, delta_nw, f_window), B = 50000L)
    a <- rbind(a, extract_ci(win_dp, "DP", "window_max_1_4"),
               win_rp[, .(contrast = paste0(group, "N"), outcome = "window_max_1_4", estimate, ci_lower, ci_upper)])
    a[, `:=`(scope = scope_value, rule = rule_value, n_successions = ne)]
    averages[[length(averages) + 1L]] <- a

    # The observed-to-benchmark gap is itself estimated on a paired outcome.
    # Do not compare two independently sampled confidence intervals.
    gap <- estimate_columns(de, cbind(gap_annual_1_4 = mean_d - obs_d), B = 50000L, seed = 20261023L)
    g <- extract_ci(gap, "DP", "benchmark_minus_observed")
    g[, `:=`(scope = scope_value, rule = rule_value, n_successions = ne)]
    gaps[[length(gaps) + 1L]] <- g
    message(ne, " successions / ", scope_value, " / ", rule_value, ": re-estimation and intervals verified")
  }
}
fwrite(rbindlist(results), file.path(reward_out, "did_intervals.csv"))
fwrite(rbindlist(averages), file.path(reward_out, "did_summary.csv"))
fwrite(rbindlist(obs_averages), file.path(reward_out, "observed_annual_summary.csv"))
fwrite(rbindlist(gaps), file.path(reward_out, "paired_gap_intervals.csv"))
fwrite(rbindlist(components), file.path(reward_out, "variance_components.csv"))
fwrite(rbindlist(checks), file.path(reward_out, "refit_checks.csv"))
fwrite(data.table(bootstrap_draws = 50000L, seed = 20261023L,
  target = "Precision of the DiD estimated on each synthetic outcome panel under the inherited inference working model",
  random_component = "Resampled standardized losing-network residuals; size-rescaled network/person shocks; RP-specific original inference",
  fixed_component = "Allocation rules, ties, capacities, networks, evaluation sample and X",
  excludes = "Uncertainty about rule validity, input measurement and allocation-model specification",
  coverage = "Nominal 95 percent pointwise intervals conditional on the original inference model; no allocation-DGP coverage claim"),
  file.path(reward_out, "inference_metadata.csv"))
