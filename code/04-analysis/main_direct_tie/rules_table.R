# Alternative allocation rules as a table (4 November 2026, coauthors' request: replace the simulation figure). Each rule
# reallocates the SAME observed posts of every year e+1..e+6 (rank counts preserved) and the main design is re-estimated
# on the synthetic careers (research/succession_benchmarks: assignments.py, inference.R):
#   purge            winner-takes-all: the losing contenders' followers get no post; the designee's followers take the
#                    best posts first (predetermined priority: prior rank, experience, credential), then the unaligned
#   promotions_only  the designee's followers are moved up into the best of the observed posts; the losers' followers
#                    keep their observed careers; nobody enters or leaves office
#   sharing          every year's posts split across camps in proportion to their population shares (capped quotas),
#                    within camp by predetermined priority
#   career           every post goes by predetermined priority alone (prior rank, experience, credential), camp ignored
# Columns: premium D - P, reward D - N, penalty P - N (years 1-4 average, rank positions, 95% intervals from the same
# Ferman-Pinto machinery as the observed row: benchmarks' inference.R), the premium in official pay (US$ a month, one
# rung = PAYgainOneUSD of pay_envelope.R, 1999 scale in 2025 prices) and the observed premium as a share of each rule's.
# Writes tables/rules_table.tex and tables/rules_macros.tex. Reads the benchmarks under TAPADOSPRI_DB_ROOT/research/
# succession_benchmarks (the staging environment). Run: Rscript code/04-analysis/main_direct_tie/rules_table.R
suppressPackageStartupMessages(library(data.table))
db_root <- Sys.getenv("TAPADOSPRI_DB_ROOT", file.path(path.expand("~"), "Dropbox", "TapadosPRI"))
out_dir <- Sys.getenv("TAPADOS_MAIN_OUTPUT_DIR", file.path(db_root, "output", "main_direct_tie"))
bench <- file.path(db_root, "research", "succession_benchmarks", "data", "inference")
tab_dir <- file.path(out_dir, "tables"); dir.create(tab_dir, showWarnings = FALSE)
rules <- fread(file.path(bench, "did_summary.csv"))[scope == "all_observed" & outcome == "annual_1_4"]
obs <- fread(file.path(bench, "observed_annual_summary.csv"))[outcome == "annual_1_4"][, rule := "observed"]
es_obs <- fread(file.path(out_dir, "event_study_summary.csv"))[outcome == "rank" & contrast == "main_window_average"]
stopifnot(abs(obs[contrast == "DP", estimate] - es_obs$estimate) < 1e-6)   # same point estimate as the deck's headline
pay <- readLines(file.path(tab_dir, "pay_macros.tex"))
usd_rung <- as.numeric(gsub(",", "", sub(".*\\{\\\\PAYgainOneUSD\\}\\{([^}]*)\\}.*", "\\1", pay[grepl("PAYgainOneUSD}", pay)])))
stopifnot(is.finite(usd_rung))
all <- rbind(obs[, .(rule, contrast, estimate, ci_lower, ci_upper)], rules[, .(rule, contrast, estimate, ci_lower, ci_upper)])
labels <- c(observed = "Observed", purge = "Winner-takes-all purge, losers' followers excluded",
            promotions_only = "Winner promotions, losers' followers unchanged", sharing = "Proportional sharing across camps",
            career = "Promotion by prior career alone")
order_rules <- names(labels)
W <- dcast(all, rule ~ contrast, value.var = c("estimate", "ci_lower", "ci_upper"))[match(order_rules, rule)]
W[, `:=`(usd = estimate_DP * usd_rung, share_of_purge = 100 * estimate_DP / W[rule == "purge", estimate_DP],
         observed_share = 100 * W[rule == "observed", estimate_DP] / estimate_DP)]
fwrite(W, file.path(out_dir, "rules_table.csv"))
f2 <- function(x) sub("^-", "$-$", formatC(x, format = "f", digits = 2))
fu <- function(x) { s <- formatC(abs(round(x, -1)), format = "d", big.mark = ","); if (x < 0) paste0("$-$", s) else s }
ci <- function(lo, hi) sprintf("{\\scriptsize[%s, %s]}", f2(lo), f2(hi))
lines <- c("% rules_table.tex (rules_table.R). Years 1-4 average, rank positions; 95% intervals; pay at one rung = US$ PAYgainOneUSD a month.",
  "\\begin{tabular}{lcccc}", "\\toprule",
  " & Premium & Reward & Penalty & Premium in pay \\\\",
  "Allocation of the same posts & designee's $-$ losers' & designee's $-$ unaligned & losers' $-$ unaligned & US\\$ a month \\\\", "\\midrule")
for (r in order_rules) {
  x <- W[rule == r]
  lines <- c(lines, sprintf("%s & %s & %s & %s & %s \\\\", labels[[r]], f2(x$estimate_DP), f2(x$estimate_DN), f2(x$estimate_PN), fu(x$usd)),
             sprintf(" & %s & %s & %s & \\\\", ci(x$ci_lower_DP, x$ci_upper_DP), ci(x$ci_lower_DN, x$ci_upper_DN), ci(x$ci_lower_PN, x$ci_upper_PN)))
  if (r == "observed") lines <- c(lines, "\\addlinespace[3pt]")
}
lines <- c(lines, "\\bottomrule", "\\end{tabular}")
writeLines(lines, file.path(tab_dir, "rules_table.tex"))
mac <- function(n, v) sprintf("\\newcommand{\\%s}{%s}", n, v)
g <- function(r, col) W[rule == r][[col]]
writeLines(c("% rules_macros.tex (rules_table.R). Do not edit by hand.",
  mac("RULobs", f2(g("observed", "estimate_DP"))), mac("RULpurge", f2(g("purge", "estimate_DP"))), mac("RULpromo", f2(g("promotions_only", "estimate_DP"))),
  mac("RULshare", f2(g("sharing", "estimate_DP"))), mac("RULcareer", f2(g("career", "estimate_DP"))),
  mac("RULpurgeReward", f2(g("purge", "estimate_DN"))), mac("RULpurgePenaltyAbs", f2(abs(g("purge", "estimate_PN")))),
  mac("RULshareReward", f2(g("sharing", "estimate_DN"))), mac("RULsharePenaltyAbs", f2(abs(g("sharing", "estimate_PN")))),
  mac("RULobsPctPurge", formatC(g("observed", "share_of_purge"), format = "f", digits = 0)),
  mac("RULobsPctPromo", formatC(100 * g("observed", "estimate_DP") / g("promotions_only", "estimate_DP"), format = "f", digits = 0)),
  mac("RULpurgeUSD", fu(g("purge", "usd"))), mac("RULpromoUSD", fu(g("promotions_only", "usd"))), mac("RULobsUSD", fu(g("observed", "usd"))),
  mac("RULusdRung", formatC(usd_rung, format = "d", big.mark = ","))),
  file.path(tab_dir, "rules_macros.tex"))
print(W[, .(rule, DP = round(estimate_DP, 2), DN = round(estimate_DN, 2), PN = round(estimate_PN, 2), usd = round(usd), pct_of_purge = round(share_of_purge))])
cat("rules_table done\n")
