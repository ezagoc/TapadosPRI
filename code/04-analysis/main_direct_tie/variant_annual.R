# The headline estimand for a variant run (4 November 2026): the years 1-4 average of the event study (mean rank in
# e+1..e+4 minus the rank in e-2, event-study covariates, Ferman-Pinto inference), estimated on the sample that the
# environment switches of estimate_main.R define (TAPADOS_TIE_CUTOFF, TAPADOS_INCLUSION, TAPADOS_SLATE, TAPADOS_PRE_MIN).
# The deck's robustness table reads annual_result.csv from each variant folder so that every row is the same estimand as
# the headline 0.74. Run inside the staging environment with the variant's environment and output folder, e.g.
#   TAPADOS_MAIN_OUTPUT_DIR=$B/output/main_direct_tie/robust_cabinet_slate TAPADOS_SLATE=cabinet Rscript variant_annual.R
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
invisible(capture.output(source(file.path(script_dir, "estimate_main.R"))))
source(file.path(script_dir, "design_tools.R"))
Yk <- sapply(c(-2L, 1:4), function(k) year_value(annual, k)); colnames(Yk) <- c(-2L, 1:4)
y_avg <- rowMeans(Yk[, as.character(1:4), drop = FALSE]) - Yk[, "-2"]
t <- estimate_columns(build_design(formula = formula_es), cbind(y = y_avg), B = 20000L, seed = 4112026L)$table
out <- data.table(outcome = "annual_1_4", tie_cutoff_years = tie_lag, inclusion = inclusion_rule, slate = slate_rule, pre_min = pre_min,
                  succession_weights = succession_weights, estimate = t$estimate, ci_lower = t$ci_lower, ci_upper = t$ci_upper,
                  p_bootstrap = t$p_bootstrap, n = nrow(sample), n_designee = sum(sample$treated == 1L))
fwrite(out, file.path(out_dir, "annual_result.csv"))
cat(sprintf("annual 1-4 average: %.2f [%.2f, %.2f], n = %d\n", out$estimate, out$ci_lower, out$ci_upper, out$n))
