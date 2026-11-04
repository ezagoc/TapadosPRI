# Winner against the number two (4 November 2026, coauthor's request). The main design compares the designee's followers
# with the followers of ALL losing contenders of the slate. Here the comparison group is one contender's followers:
#   (a) the documented runner-up (candidates/corcholatas_matched.csv, role runner_up, sources in the file);
#   (b) the largest losing camp of the slate (most exclusive followers);
#   (c) every losing contender in turn: one build_design per (succession, contender) gives the succession contrast; the
#       pooled estimate of a combination (one contender per succession) uses the estimator's succession weights; the
#       distribution over 5,000 random combinations (and the exact one when the product of slate sizes is small) shows
#       how far the choice of "number two" can move the estimate.
# Outcomes: the main window change (delta, main covariates) and the years 1-4 average of the event study (formula_es).
# Inference for (a) and (b): the Ferman-Pinto bootstrap of design_tools.R on the restricted design (its donors are the
# single comparison camps, so the variance fit rests on nine donors; stated on the slide). Successions whose documented
# runner-up has no exclusive follower drop out of (a) and are listed. Writes runner_up.csv, runner_up_combinations.csv,
# tables/runner_up.tex and tables/runner_up_macros.tex. Run after estimate_main.R:
#   Rscript code/04-analysis/main_direct_tie/runner_up.R
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
invisible(capture.output(source(file.path(script_dir, "estimate_main.R"))))
source(file.path(script_dir, "design_tools.R"))
set.seed(4112026L)
tab_dir <- file.path(out_dir, "tables"); dir.create(tab_dir, showWarnings = FALSE)
Yk <- sapply(c(-2L, 1:4), function(k) year_value(annual, k)); colnames(Yk) <- c(-2L, 1:4)
y_avg <- rowMeans(Yk[, as.character(1:4), drop = FALSE]) - Yk[, "-2"]
y_win <- sample$delta
outcomes <- list(window = list(y = y_win, formula = formula_x), annual = list(y = y_avg, formula = formula_es))

camps <- sample[treated == 0L, .(n = .N), by = .(election, patron)]
ru <- contenders[in_main_slate == 1L & role == "runner_up", .(election = election_year, patron = person_id)]
ru <- merge(ru, camps, by = c("election", "patron"), all.x = TRUE)
largest <- camps[camps[, .I[which.max(n)], by = election]$V1]
name_of <- unique(contenders[, .(person_id, person_name)])
nm <- function(id) name_of$person_name[match(id, name_of$person_id)]

# Inference. With ONE comparison camp per succession the Ferman-Pinto donor residuals are zero by construction (the
# succession indicators fit each camp's mean exactly), so the restricted designs take a person-level variance instead:
# sum a_i^2 e_i^2 with e_i the residuals of the FULL design's loser model, in line with the main fit's variance components
# (no common camp shock detected, A_network = 0). The main row keeps the Ferman-Pinto bootstrap.
fit_subset <- function(keep_patron, label, main = FALSE) {
  keep <- sample$treated == 1L | paste(sample$election, sample$patron) %in% paste(keep_patron$election, keep_patron$patron)
  rbindlist(lapply(names(outcomes), function(o) {
    y <- outcomes[[o]]$y
    d_full <- build_design(formula = outcomes[[o]]$formula); e_full <- residuals_d(d_full, y[d_full$rows])
    d <- build_design(keep = keep, formula = outcomes[[o]]$formula)
    est <- sum(d$a * y[d$rows])
    if (main) {
      t <- estimate_columns(d, cbind(y = y[d$rows]), B = 20000L, seed = 4112026L)$table
      lo <- t$ci_lower; hi <- t$ci_upper; p <- t$p_bootstrap; inf <- "Ferman-Pinto"
    } else {
      se <- sqrt(sum(d$a^2 * e_full[match(d$rows, d_full$rows)]^2))
      lo <- est - qnorm(.975) * se; hi <- est + qnorm(.975) * se; p <- 2 * pnorm(-abs(est / se)); inf <- "person-level"
    }
    data.table(spec = label, outcome = o, estimate = est, ci_lower = lo, ci_upper = hi, p = p, inference = inf,
               n_designee = sum(d$S$treated == 1L), n_comparison = sum(d$S$treated == 0L), successions = length(d$elections),
               dropped = paste(setdiff(elections, d$elections), collapse = " "))
  }))
}
res <- rbindlist(list(
  fit_subset(camps, "All losing contenders' followers (main)", main = TRUE),
  fit_subset(ru[!is.na(n)], "Documented runner-up's followers"),
  fit_subset(largest, "Largest losing camp's followers")))

# (c) every losing contender in turn
per <- rbindlist(lapply(names(outcomes), function(o) rbindlist(lapply(seq_len(nrow(camps)), function(i) {
  keep <- sample$treated == 1L | (sample$election == camps$election[i] & sample$patron == camps$patron[i]) |
    (sample$election != camps$election[i] & sample$treated == 0L)
  d <- build_design(keep = keep, formula = outcomes[[o]]$formula)
  data.table(outcome = o, election = camps$election[i], patron = camps$patron[i], n = camps$n[i],
             contrast = by_succession_d(d, outcomes[[o]]$y[d$rows])[election == camps$election[i], estimate])
}))))
per[, name := nm(patron)]
fwrite(per, file.path(out_dir, "runner_up_contrasts.csv"))
comb <- rbindlist(lapply(names(outcomes), function(o) {
  by_e <- split(per[outcome == o], by = "election")
  sizes <- sapply(by_e, nrow); n_total <- prod(sizes)
  draws <- if (n_total <= 2e5) as.matrix(do.call(expand.grid, lapply(sizes, seq_len))) else sapply(sizes, function(m) sample.int(m, 5000L, replace = TRUE))
  pooled <- rowSums(sapply(seq_along(by_e), function(j) omega[[as.character(by_e[[j]]$election[1])]] * by_e[[j]]$contrast[draws[, j]]))
  data.table(outcome = o, n_combinations = nrow(draws), exact = n_total <= 2e5, minimum = min(pooled), q10 = quantile(pooled, .1), median = median(pooled),
             q90 = quantile(pooled, .9), maximum = max(pooled), share_positive = mean(pooled > 0))
}))
fwrite(comb, file.path(out_dir, "runner_up_combinations.csv"))
fwrite(res, file.path(out_dir, "runner_up.csv"))
cat("Winner against one comparison camp:\n"); print(res[, .(spec, outcome, estimate = round(estimate, 2), ci_lower = round(ci_lower, 2), ci_upper = round(ci_upper, 2), n_comparison, successions, dropped)])
cat("\nEvery losing contender in turn (pooled with the estimator's weights):\n"); print(comb[, lapply(.SD, function(x) if (is.numeric(x)) round(x, 2) else x)])
cat("\nRunner-ups and their followers:\n"); print(ru[, .(election, name = nm(patron), followers = n)])

# ------------------------------------------------------------------ table and macros
f2 <- function(x) formatC(x, format = "f", digits = 2)
ci <- function(lo, hi) sprintf("[%s, %s]", f2(lo), f2(hi))
row <- function(sp) { a <- res[spec == sp & outcome == "annual"]; w <- res[spec == sp & outcome == "window"]
  sprintf("%s & %s & %s & %s & %s & %d & %d \\\\", sp, f2(a$estimate), ci(a$ci_lower, a$ci_upper), f2(w$estimate), ci(w$ci_lower, w$ci_upper), a$n_comparison, a$successions) }
ca <- comb[outcome == "annual"]; cw <- comb[outcome == "window"]
lines <- c("% runner_up.tex (runner_up.R). Designee's followers against one comparison camp. Do not edit by hand.",
  "\\begin{tabular}{lcccccc}", "\\toprule",
  " & \\multicolumn{2}{c}{Years 1--4 average} & \\multicolumn{2}{c}{Window $e+1$..$e+4$} & Comparison & \\\\",
  "\\cmidrule(lr){2-3}\\cmidrule(lr){4-5}",
  "Comparison group & Estimate & 95\\% interval & Estimate & 95\\% interval & followers & Successions \\\\", "\\midrule",
  row("All losing contenders' followers (main)"), row("Documented runner-up's followers"), row("Largest losing camp's followers"),
  sprintf("Each losing contender in turn, median & %s & %s & %s & %s & & 9 \\\\", f2(ca$median), sprintf("range [%s, %s]", f2(ca$minimum), f2(ca$maximum)), f2(cw$median), sprintf("range [%s, %s]", f2(cw$minimum), f2(cw$maximum))),
  "\\bottomrule", "\\end{tabular}")
writeLines(lines, file.path(tab_dir, "runner_up.tex"))
mac <- function(n, v) sprintf("\\newcommand{\\%s}{%s}", n, v)
a_ru <- res[spec == "Documented runner-up's followers" & outcome == "annual"]; a_lg <- res[spec == "Largest losing camp's followers" & outcome == "annual"]
writeLines(c("% runner_up_macros.tex (runner_up.R). Do not edit by hand.",
  mac("RUest", f2(a_ru$estimate)), mac("RUlo", f2(a_ru$ci_lower)), mac("RUhi", f2(a_ru$ci_upper)), mac("RUn", a_ru$n_comparison), mac("RUsucc", a_ru$successions),
  mac("RUdropped", ifelse(a_ru$dropped == "", "none", a_ru$dropped)),
  mac("RUlargestEst", f2(a_lg$estimate)), mac("RUlargestLo", f2(a_lg$ci_lower)), mac("RUlargestHi", f2(a_lg$ci_upper)),
  mac("RUeachMedian", f2(ca$median)), mac("RUeachMin", f2(ca$minimum)), mac("RUeachMax", f2(ca$maximum)), mac("RUeachPositive", formatC(100 * ca$share_positive, format = "f", digits = 0)),
  mac("RUeachN", format(ca$n_combinations, big.mark = ","))),
  file.path(tab_dir, "runner_up_macros.tex"))
cat("runner_up done\n")
