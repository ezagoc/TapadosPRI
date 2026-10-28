# Holding a top post (score 7 or above: undersecretaries, senators, Supreme Court justices, the PRI's national
# executive and up) after the succession (29 October 2026). The main design on the indicator T_k = 1(rank_k >= 7):
# event study of T_k - T_{-2}, designee's minus losers' followers, section-7 covariates, equal weight per
# succession, Ferman-Pinto inference (design_tools.R), plus the years 1-4 average with its interval. Writes
# top_event_study.csv, top_summary.csv, the figure es_top.{pdf,png} (percentage points) and
# tables/top_macros.tex. Run after estimate_main.R: Rscript code/04-analysis/main_direct_tie/top_post.R
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
invisible(capture.output(source(file.path(script_dir, "estimate_main.R"))))
source(file.path(script_dir, "design_tools.R")); suppressPackageStartupMessages(library(ggplot2))

TOP <- as.integer(Sys.getenv("TAPADOS_TOP_THRESHOLD", "7"))
ks <- -7:8; ref <- -2L
Y <- sapply(ks, function(k) year_value(annual, k)); colnames(Y) <- ks
Tm <- (Y >= TOP) * 1

d_es <- build_design(formula = formula_es)
cols <- Tm[, colnames(Tm) != as.character(ref)] - Tm[, as.character(ref)]
es <- estimate_columns(d_es, cols)$table
es <- rbind(es[, .(k = as.integer(column), estimate, ci_lower, ci_upper, ci90_lower, ci90_upper, p_bootstrap, n)],
            data.table(k = ref, estimate = 0, ci_lower = 0, ci_upper = 0, ci90_lower = 0, ci90_upper = 0, p_bootstrap = NA, n = nrow(sample)))
setorder(es, k); es[, outcome := sprintf("holds a post of score %d or above", TOP)]
fwrite(es, file.path(out_dir, "top_event_study.csv"))

# years 1-4 average: the averaged outcome through the same estimator and bootstrap
avg14 <- rowMeans(Tm[, as.character(1:4)]) - Tm[, as.character(ref)]
s14 <- estimate_columns(d_es, cbind(years_1_4 = avg14))$table
s14[, outcome := es$outcome[1]]
fwrite(s14, file.path(out_dir, "top_summary.csv"))
cat(sprintf("threshold %d: years 1-4 average %+.1f pp [%.1f, %.1f], p = %.3f; pre-period mean of the indicator at e-2: designee's %.2f, losers' %.2f\n",
            TOP, 100 * s14$estimate, 100 * s14$ci_lower, 100 * s14$ci_upper, s14$p_bootstrap,
            mean(Tm[sample$treated == 1L, as.character(ref)]), mean(Tm[sample$treated == 0L, as.character(ref)])))
print(es[, .(k, estimate = round(100 * estimate, 1), ci_lower = round(100 * ci_lower, 1), ci_upper = round(100 * ci_upper, 1), p_bootstrap)])

tab_dir <- file.path(out_dir, "tables"); dir.create(tab_dir, showWarnings = FALSE)
f1 <- function(x) { v <- round(x, 1); s <- formatC(abs(v), format = "f", digits = 1); ifelse(v < 0, paste0("$-$", s), s) }
mac <- function(n, v) sprintf("\\newcommand{\\%s}{%s}", n, v)
writeLines(c(sprintf("%% top_macros.tex (top_post.R): holding a post of score %d or above, years 1-4 average in pp. Do not edit by hand.", TOP),
             mac("TOPthreshold", TOP), mac("TOPest", f1(100 * s14$estimate)), mac("TOPlo", f1(100 * s14$ci_lower)), mac("TOPhi", f1(100 * s14$ci_upper)),
             mac("TOPp", formatC(s14$p_bootstrap, format = "f", digits = 2)),
             mac("TOPpreDesignee", round(100 * mean(Tm[sample$treated == 1L, as.character(ref)]))),
             mac("TOPpreLosers", round(100 * mean(Tm[sample$treated == 0L, as.character(ref)])))),
           file.path(tab_dir, "top_macros.tex"))

es_figure(es, sprintf("Effect on holding a top post (pp),\ndesignee's minus losers' followers"), "es_top", scale = 100)
