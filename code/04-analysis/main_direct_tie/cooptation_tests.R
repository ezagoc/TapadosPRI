# MAIN_SPEC section 15: does the new president co-opt the most threatening losers? Exact within-succession permutation test
# (P1, the gate), secondary measures, and the descriptive check by opposition-entry regime (P2).
#   Rscript code/04-analysis/main_direct_tie/cooptation_tests.R   (after aspirants_table.R)
suppressPackageStartupMessages({library(data.table); library(survival)})
db_root <- Sys.getenv("TAPADOSPRI_DB_ROOT", file.path(path.expand("~"), "Dropbox", "TapadosPRI"))
out_dir <- Sys.getenv("TAPADOS_MAIN_OUTPUT_DIR", file.path(db_root, "output", "main_direct_tie"))
asp <- fread(file.path(db_root, "data", "structural", "aspirants.csv"))
L <- asp[slate == "main"]
L[, `:=`(kept = as.integer(treatment == "kept a top chair"), threat = as.numeric(scale(log1p(camp_any))),
         gov = log1p(governors_in_camp), cabinet = as.integer(rung_e2 >= 9L))]
inf <- L[, .(k = sum(kept), n = .N), by = election][k > 0 & k < n, election]

exact_p <- function(z) {
  stat <- L[election %in% inf & kept == 1L, sum(get(z))]
  sums <- 0
  for (e in inf) {
    x <- L[election == e, get(z)]; k <- L[election == e, sum(kept)]
    s <- combn(x, k, sum)
    sums <- as.vector(outer(sums, s, "+"))
  }
  data.table(measure = z, statistic = stat, permutations = length(sums), p_one_sided = mean(sums >= stat - 1e-12),
             mean_under_null = mean(sums))
}
p1 <- rbindlist(lapply(c("threat", "general", "gov"), exact_p))
p1[, role := c("P1 (gate): standardized log(1 + camp)", "secondary: general's rank", "secondary: log(1 + governors in camp)")]
cl <- clogit(kept ~ threat + cabinet + age + runner_up + strata(election), data = L[election %in% inf])
p2 <- merge(L[, .(any_coopted = as.integer(any(kept == 1L)), kept = sum(kept), losers = .N), by = .(election, exit_regime)],
            asp[, .(breaks = sum(broke)), by = election], by = "election")
fwrite(p1, file.path(out_dir, "cooptation_p1.csv")); fwrite(p2, file.path(out_dir, "cooptation_p2.csv"))
cat("Informative successions:", inf, "\n"); print(p1[, .(role, statistic = round(statistic, 2), mean_under_null = round(mean_under_null, 2), permutations, p_one_sided = round(p_one_sided, 3))])
cat("\nConditional logit (secondary):\n"); print(round(summary(cl)$coefficients, 3))
cat("\nP2 (descriptive):\n"); print(p2[order(election)])
print(L[election %in% inf][order(election, -threat), .(election, name = substr(name, 1, 28), camp_any, threat = round(threat, 2), general, governors_in_camp, cabinet, kept, treatment)])
