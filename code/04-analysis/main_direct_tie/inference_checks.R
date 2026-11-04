# Can the intervals of the main window contrast be narrower and still valid? (seminar comment, 3 November 2026,
# with Harrison and Jacho-Chavez 2026, "Rate-agnostic Wald inference for dyadic regressions", as the reference.)
# Each observation is a politician x contender dyad (a follower tied to one contender in one succession), so their
# dependence structure (observations dependent only when they share a unit) is two-way clustering by politician
# and by contender. Computed on the main sample, same estimator (design_tools.R build_design):
#   1. Ferman-Pinto (main): contender-level bootstrap with the fitted shock variance A + B/n (A = network, B = person).
#   2. Delete-one-unit jackknife over units = politicians U contenders (their eq. 2.4): deleting a unit removes every
#      observation touching it; deleting a designee removes his succession from the average (mean over the rest).
#   3. The same jackknife over contenders only (CV3 by contender) and over politicians only.
#   4. Person-level heteroskedasticity-robust SE of the linear estimator, sqrt(sum a_i^2 e_i^2) (HC0 on the
#      loser-model residuals): the floor when shocks are independent across people.
#   5. The nine succession premiums and the SE of their mean from their dispersion (9 clusters, t with 8 df).
# Everything for the main estimand (equal succession weights) and for person weights (average follower).
# Run after estimate_main.R, inside the deck's staging environment (research/eligibility_refresh_2026_10_27):
#   Rscript code/04-analysis/main_direct_tie/inference_checks.R
# Writes inference_checks.csv.
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
invisible(capture.output(source(file.path(script_dir, "estimate_main.R"))))
source(file.path(script_dir, "design_tools.R"))
y_full <- sample$delta

theta_of <- function(keep, weights) { d <- build_design(keep = keep, weights = weights); sum(d$a * y_full[d$rows]) }
jack <- function(units_of_row, weights) {
  # units_of_row: list, one character vector of unit ids per row of sample
  units <- sort(unique(unlist(units_of_row)))
  th <- sapply(units, function(g) {
    keep <- !vapply(units_of_row, function(u) g %in% u, logical(1))
    tryCatch(theta_of(keep, weights), error = function(e) NA_real_)
  })
  G <- sum(!is.na(th)); th <- th[!is.na(th)]
  list(se = sqrt((G - 1) / G * sum((th - mean(th))^2)), G = G, dropped = length(units) - G)
}
pol <- paste0("p", sample$pid); con <- paste0("c", sample$patron)
u_dyad <- Map(c, pol, con); u_con <- as.list(con); u_pol <- as.list(pol)

res <- list()
for (wts in c("equal", "person")) {
  d <- build_design(weights = wts)
  est <- sum(d$a * y_full[d$rows])
  fp <- estimate_columns(d, cbind(delta = y_full[d$rows]), B = 20000L, seed = 17102026L)$table
  e_hat <- residuals_d(d, y_full[d$rows])
  hc0 <- sqrt(sum(d$a^2 * e_hat^2))
  bys <- by_succession_d(d, y_full[d$rows])
  se9 <- sd(bys$estimate) / sqrt(nrow(bys))
  jd <- jack(u_dyad, wts); jc <- jack(u_con, wts); jp <- jack(u_pol, wts)
  res[[wts]] <- data.table(weights = wts, estimate = est,
    method = c("Ferman-Pinto bootstrap (main)", "Jackknife, politicians and contenders (dyadic)", "Jackknife, contenders only",
               "Jackknife, politicians only", "HC0 person level", "Dispersion of the nine premiums (t, 8 df)"),
    se = c(NA, jd$se, jc$se, jp$se, hc0, se9),
    ci_lower = c(fp$ci_lower, est - qnorm(.975) * c(jd$se, jc$se, jp$se, hc0), est - qt(.975, 8) * se9),
    ci_upper = c(fp$ci_upper, est + qnorm(.975) * c(jd$se, jc$se, jp$se, hc0), est + qt(.975, 8) * se9),
    units = c(d$K + length(d$elections), jd$G, jc$G, jp$G, nrow(d$S), nrow(bys)))
  res[[wts]][method == "Ferman-Pinto bootstrap (main)", se := (ci_upper - ci_lower) / (2 * qnorm(.975))]
  cat(sprintf("\n%s weights: estimate %.3f; A_network %.3f, B_person %.2f (main fit)\n", wts, est, AB[1], AB[2]))
  print(res[[wts]][, .(method, se = round(se, 3), ci_lower = round(ci_lower, 2), ci_upper = round(ci_upper, 2), units)])
  cat("nine premiums:", paste(sprintf("%d: %.2f", bys$election, bys$estimate), collapse = ", "), "\n")
}
out <- rbindlist(res)
fwrite(out, file.path(out_dir, "inference_checks.csv"))
cat("\nwritten inference_checks.csv\n")
