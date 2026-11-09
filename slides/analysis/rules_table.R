# Alternative allocation rules as a table (4 November 2026, coauthors' request: replace the simulation figure). Each rule
# reallocates the SAME observed posts of every year e+1..e+6 (rank counts preserved) and the main design is re-estimated
# on the synthetic careers (research/succession_benchmarks: assignments.py, inference.R):
#   purge            winner-takes-all: the losing contenders' followers get no post; the designee's followers take the
#                    best posts first (predetermined priority: prior rank, experience, credential), then the unaligned
#   promotions_only  the designee's followers are moved up into the best of the observed posts; the losers' followers
#                    keep their observed careers; nobody enters or leaves office
#   sharing          the contenders' camps (the winner's, each loser's, those tied to several losers) take the best posts
#                    first, split in proportion to their available members (capped quotas, within camp by predetermined
#                    priority); the unaligned fill the remaining posts (9 Nov 2026; before, the unaligned were one more camp)
#   career           every post goes by predetermined priority alone (prior rank, experience, credential), camp ignored
# Columns: premium D - P (years 1-4 average, rank positions, 95% intervals from the same Ferman-Pinto machinery as the
# observed row: benchmarks' inference.R), the reward D - N and the EXACT penalty (5 November 2026: reward minus premium,
# the penalty of a tie to a loser for the same politicians as the premium, rp_setup.R rp_fit_exact; the own-profile P - N
# of the benchmarks stays in estimate_PN_own) as shares of the premium,
# the convention of the deck's reward/penalty slide (shown only where the premium is positive: under sharing both groups
# gain on the unaligned and under career neither moves, so the split has no meaning), the premium in official pay (US$ a
# month, one rung = PAYgainOneUSD of pay_envelope.R, 1999 scale in 2025 prices) and the observed premium as a share of each
# rule's. The point estimates of reward and penalty stay in rules_table.csv and the RUL*Reward/PenaltyAbs macros.
# Writes tables/rules_table.tex and tables/rules_macros.tex. Reads the benchmarks under TAPADOS_BENCH_DIR
# (slides/benchmarks, default output/slides/benchmarks). Run: Rscript slides/analysis/rules_table.R
suppressPackageStartupMessages(library(data.table))
db_root <- Sys.getenv("TAPADOSPRI_DB_ROOT", file.path(path.expand("~"), "Dropbox", "TapadosPRI"))
out_dir <- Sys.getenv("TAPADOS_MAIN_OUTPUT_DIR", file.path(db_root, "output", "main_direct_tie"))
bench <- file.path(Sys.getenv("TAPADOS_BENCH_DIR", file.path(db_root, "output", "slides", "benchmarks")), "data", "inference")
tab_dir <- file.path(out_dir, "tables"); dir.create(tab_dir, showWarnings = FALSE)
rules <- fread(file.path(bench, "did_summary.csv"))[scope == "all_observed" & outcome == "annual_1_4"]
obs <- fread(file.path(bench, "observed_annual_summary.csv"))[outcome == "annual_1_4"][, rule := "observed"]
es_obs <- fread(file.path(out_dir, "event_study_summary.csv"))[outcome == "rank" & contrast == "main_window_average"]
stopifnot(abs(obs[contrast == "DP", estimate] - es_obs$estimate) < 1e-6)   # same point estimate as the deck's headline
pay <- readLines(file.path(tab_dir, "pay_macros.tex"))
usd_rung <- as.numeric(gsub(",", "", sub(".*\\{\\\\PAYgainOneUSD\\}\\{([^}]*)\\}.*", "\\1", pay[grepl("PAYgainOneUSD}", pay)])))
stopifnot(is.finite(usd_rung))
# the premium as a percentage change in official pay, the convention of pay_envelope.R (pct(): one rung = the 1999
# ladder's geometric step from department head to cabinet, compounded over the rungs of the premium; pay_ladder.csv)
lad <- fread(file.path(out_dir, "pay_ladder.csv"))
per_rung <- (lad[rung == 9L, pay_1999] / lad[rung == 3L, pay_1999])^(1 / 6) - 1
pay_pct <- function(rungs) 100 * ((1 + per_rung)^rungs - 1)
all <- rbind(obs[, .(rule, contrast, estimate, ci_lower, ci_upper)], rules[, .(rule, contrast, estimate, ci_lower, ci_upper)])
labels <- c(observed = "Observed", purge = "Winner-takes-all purge", promotions_only = "Winner promotions only",
            sharing = "Proportional sharing", career = "Promotion by prior career")
order_rules <- names(labels)
W <- dcast(all, rule ~ contrast, value.var = c("estimate", "ci_lower", "ci_upper"))[match(order_rules, rule)]
W[, `:=`(usd = estimate_DP * usd_rung, pay_pct = pay_pct(estimate_DP), share_of_purge = 100 * estimate_DP / W[rule == "purge", estimate_DP],
         observed_share = 100 * W[rule == "observed", estimate_DP] / estimate_DP)]
W[, estimate_PN_own := estimate_PN][, estimate_PN := estimate_DN - estimate_DP]   # exact penalty: reward - premium
W[, gap := estimate_DN - estimate_PN]
stopifnot(max(abs(W$gap - W$estimate_DP)) < 1e-10)
W[, `:=`(reward_pct = fifelse(estimate_DP > 0, 100 * estimate_DN / gap, NA_real_),
         penalty_pct = fifelse(estimate_DP > 0, -100 * estimate_PN / gap, NA_real_))]
fwrite(W, file.path(out_dir, "rules_table.csv"))
f2 <- function(x) { x <- round(x, 2); x[abs(x) < 0.005] <- 0; sub("^-", "$-$", formatC(x, format = "f", digits = 2)) }   # no signed zero
fu <- function(x) { s <- formatC(abs(round(x, -1)), format = "d", big.mark = ","); if (x < 0) paste0("$-$", s) else s }
ci <- function(lo, hi) sprintf("{\\scriptsize[%s, %s]}", f2(lo), f2(hi))
pct <- function(x) if (is.na(x)) "--" else paste0(formatC(x, format = "f", digits = 0), "\\%")
fp <- function(x) { s <- formatC(abs(round(x)), format = "d", big.mark = ","); paste0(if (x < 0) "$-$" else "$+$", s, "\\%") }
lines <- c("% rules_table.tex (rules_table.R). Years 1-4 average, rank positions; 95% intervals; reward and penalty as shares of their gap,",
  "% the reward D - N and the exact penalty (reward - premium: a tie to a loser for the same politicians) in rank positions, signed, adding to the premium; the premium as a percentage change in official pay (1999 ladder, 34% a rung, compounded).",
  "\\begin{tabular}{lccccc}", "\\toprule",
  " & \\multicolumn{2}{c}{Premium, designee's $-$ losers'} & \\multicolumn{2}{c}{Split, against the unaligned} & Premium \\\\", "\\cmidrule(lr){2-3}\\cmidrule(lr){4-5}",
  "Allocation of the same posts & rank positions & 95\\% interval & reward & penalty & in pay \\\\", "\\midrule")
for (r in order_rules) {
  x <- W[rule == r]
  # the two components with their sign, rank positions (the reward D - N and the penalty P - N of the deck's decomposition)
  split_cells <- sprintf("%s & %s", f2(x$estimate_DN), f2(x$estimate_PN))
  lines <- c(lines, sprintf("%s & %s & [%s, %s] & %s & %s \\\\", labels[[r]], f2(x$estimate_DP), f2(x$ci_lower_DP), f2(x$ci_upper_DP),
                            split_cells, fp(x$pay_pct)))
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
  mac("RULobsRewardPct", formatC(g("observed", "reward_pct"), format = "f", digits = 0)), mac("RULobsPenaltyPct", formatC(g("observed", "penalty_pct"), format = "f", digits = 0)),
  mac("RULpurgeRewardPct", formatC(g("purge", "reward_pct"), format = "f", digits = 0)), mac("RULpurgePenaltyPct", formatC(g("purge", "penalty_pct"), format = "f", digits = 0)),
  mac("RULpromoRewardPct", formatC(g("promotions_only", "reward_pct"), format = "f", digits = 0)), mac("RULpromoPenaltyPct", formatC(g("promotions_only", "penalty_pct"), format = "f", digits = 0)),
  mac("RULobsPctPurge", formatC(g("observed", "share_of_purge"), format = "f", digits = 0)),
  mac("RULobsPctPromo", formatC(100 * g("observed", "estimate_DP") / g("promotions_only", "estimate_DP"), format = "f", digits = 0)),
  mac("RULpurgeUSD", fu(g("purge", "usd"))), mac("RULpromoUSD", fu(g("promotions_only", "usd"))), mac("RULobsUSD", fu(g("observed", "usd"))),
  mac("RULusdRung", formatC(usd_rung, format = "d", big.mark = ",")),
  mac("RULobsPct", fp(g("observed", "pay_pct"))), mac("RULpurgePct", fp(g("purge", "pay_pct"))), mac("RULpromoPct", fp(g("promotions_only", "pay_pct"))),
  mac("RULsharePct", fp(g("sharing", "pay_pct"))), mac("RULcareerPct", fp(g("career", "pay_pct"))),
  mac("RULpurgeTimes", formatC(1 + g("purge", "pay_pct") / 100, format = "f", digits = 1)), mac("RULpayStep", formatC(100 * per_rung, format = "f", digits = 0))),
  file.path(tab_dir, "rules_macros.tex"))
print(W[, .(rule, DP = round(estimate_DP, 2), DN = round(estimate_DN, 2), PN = round(estimate_PN, 2), reward_pct = round(reward_pct), penalty_pct = round(penalty_pct), usd = round(usd), pay_pct = round(pay_pct), pct_of_purge = round(share_of_purge))])
cat("rules_table done\n")
