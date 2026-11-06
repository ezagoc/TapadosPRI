# The agency-level money test as a reward/penalty decomposition against the agencies headed by unaligned politicians
# (6 November 2026, the user's request: with 17 agencies a side the designee-vs-losers contrast has no power; compare each
# camp with the unaligned, report confidence intervals, and check robustness). Unit: agency x succession from
# agency_budget.csv (agency_budget.R), restricted to the agencies whose head in e+1..e+4 is a designee's follower (D), a
# losing contender's follower (P) or an unaligned eligible politician (N). Outcomes: the change in the agency's share of
# federal investment e-5..e-2 to e+1..e+4 in pp, in logs, in asinh of the share in pp, and the relative change (winsorized
# at +-2). Regression on D and P with the pre share and succession indicators. Inference: (i) permutation of the head
# groups across the D/P/N agencies of the same succession, p-value and a confidence interval by inverting the permutation
# null (estimate minus the null quantiles, the shift convention); (ii) agency-clustered robust s.e. Robustness on the log
# outcome: without the successions whose windows rest on imputed shares (1964, 1970), without the block-change successions
# (1982, 1988), only agencies with a pre share of at least 0.1%, equal weights by succession, no pre-share control, any
# follower against the unaligned, and the placebo on the heads of e-5..e-2. Event study of the log share around the
# handover (k = -5..4, agency-year), for the D and P agencies against the N agencies. Figure: the agencies handed to a
# follower, share before and after (log scale), designee's and losers' side by side. Writes agency_budget_rp.csv,
# agency_budget_rp_robustness.csv, agency_budget_rp_event_study.csv, agency_budget_dumbbell.{pdf,png},
# agency_budget_rp_es.{pdf,png} and tables/agency_budget_rp_macros.tex. Run after agency_budget.R:
#   Rscript code/04-analysis/main_direct_tie/agency_budget_rp.R
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
invisible(capture.output(source(file.path(script_dir, "estimate_main.R"))))
source(file.path(script_dir, "design_tools.R")); suppressPackageStartupMessages({library(sandwich); library(ggplot2)})
invisible(capture.output(source(file.path(script_dir, "rp_setup.R"))))
source(file.path(script_dir, "budget_crosswalk.R"))
set.seed(6112026L); PERMS <- 5000L
tab_dir <- file.path(out_dir, "tables"); dir.create(tab_dir, showWarnings = FALSE)

AP <- fread(file.path(out_dir, "agency_budget.csv"))
AP[, election_factor := factor(election)]
S <- AP[group_post %in% c("D", "P", "N")]
S[, `:=`(D = as.numeric(group_post == "D"), P = as.numeric(group_post == "P"),
         d_asinh = asinh(share_post) - asinh(share_pre), d_rel = pmin(pmax(share_post / share_pre - 1, -2), 2))]
S[!is.finite(d_rel), d_rel := NA_real_]
cat(sprintf("agency-successions with a D, P or N head after the succession: %d (D %d, P %d, N %d)\n", nrow(S), sum(S$D), sum(S$P), sum(S$group_post == "N")))

# ------------------------------------------------------------------ 1. reward and penalty against the unaligned-headed agencies
fit_rp <- function(dat, y, control_pre = TRUE, weights = NULL, perms = PERMS, label = "") {
  dd <- dat[!is.na(get(y))]
  hasP <- any(dd$P == 1)                                          # the "any follower" spec has no P column to estimate
  f <- as.formula(sprintf("%s ~ D %s + %s election_factor", y, if (hasP) "+ P" else "", if (control_pre) "share_pre +" else ""))
  w <- if (is.null(weights)) rep(1, nrow(dd)) else weights(dd)
  m <- lm(f, data = dd, weights = w); V <- vcovCL(m, cluster = dd$agency_key); b <- coef(m); se <- sqrt(diag(V))
  if (!hasP) { b["P"] <- NA_real_; se["P"] <- NA_real_ }
  stat <- function(d2) { cf <- coef(lm(f, data = d2, weights = w)); c(cf["D"], if (hasP) cf["P"] else NA_real_) }
  obs <- stat(dd)
  null <- replicate(perms, { d2 <- copy(dd); d2[, c("D", "P") := { i <- sample(.N); .(D[i], P[i]) }, by = election]; stat(d2) })
  pv <- rowMeans(abs(null) >= abs(obs) - 1e-12, na.rm = TRUE); q <- apply(null, 1, quantile, c(.025, .975), na.rm = TRUE)
  data.table(spec = label, outcome = y, term = c("reward: designee's vs unaligned heads", "penalty: losers' vs unaligned heads"),
             estimate = obs, perm_p = pv, perm_ci_lower = obs - q[2, ], perm_ci_upper = obs - q[1, ],
             se_cluster = se[c("D", "P")], cl_ci_lower = obs - 1.96 * se[c("D", "P")], cl_ci_upper = obs + 1.96 * se[c("D", "P")],
             n = nrow(dd), n_D = sum(dd$D), n_P = sum(dd$P), n_N = sum(dd$group_post == "N"))
}
main <- rbindlist(list(fit_rp(S, "d_share", label = "share, pp"), fit_rp(S, "d_log", label = "log share"),
                       fit_rp(S, "d_asinh", label = "asinh share"), fit_rp(S, "d_rel", label = "relative change, winsorized")))
fwrite(main, file.path(out_dir, "agency_budget_rp.csv"))
print(main[, .(spec, term, estimate = round(estimate, 3), perm_p = round(perm_p, 3), perm_ci_lower = round(perm_ci_lower, 3), perm_ci_upper = round(perm_ci_upper, 3),
               cl_ci_lower = round(cl_ci_lower, 3), cl_ci_upper = round(cl_ci_upper, 3), n, n_D, n_P, n_N)])

# ------------------------------------------------------------------ 2. robustness of the log result
eq_w <- function(dd) { n_e <- table(dd$election); 1 / as.numeric(n_e[as.character(dd$election)]) }
SA <- copy(S)[, `:=`(D = as.numeric(group_post %in% c("D", "P")), P = 0)]   # any follower against the unaligned (P column void)
SP <- AP[group_pre %in% c("D", "P", "N")][, `:=`(D = as.numeric(group_pre == "D"), P = as.numeric(group_pre == "P"))]   # placebo, heads before
rob <- rbindlist(list(
  fit_rp(S, "d_log", label = "log share, main"),
  fit_rp(S[!election %in% c(1964L, 1970L)], "d_log", label = "without 1964 and 1970 (imputed windows)"),
  fit_rp(S[!election %in% c(1982L, 1988L)], "d_log", label = "without 1982 and 1988 (block change)"),
  fit_rp(S[share_pre >= 0.1], "d_log", label = "agencies with a pre share of 0.1% or more"),
  fit_rp(S, "d_log", weights = eq_w, label = "equal weights by succession"),
  fit_rp(S, "d_log", control_pre = FALSE, label = "without the pre-share control"),
  fit_rp(SA, "d_log", label = "any follower against the unaligned")[term == "reward: designee's vs unaligned heads"][, term := "any follower vs unaligned heads"],
  fit_rp(SP, "d_log", label = "placebo: heads of e-5..e-2")))
fwrite(rob, file.path(out_dir, "agency_budget_rp_robustness.csv"))
print(rob[, .(spec, term, estimate = round(estimate, 3), perm_p = round(perm_p, 3), perm_ci_lower = round(perm_ci_lower, 3), perm_ci_upper = round(perm_ci_upper, 3), n, n_D, n_P)])

# ------------------------------------------------------------------ 3. event study of the log share around the handover
panel <- fread(file.path(data_dir, "investment", "agency_investment_panel.csv"))
series <- build_agency_series(panel)   # agency_key, year, share (pp of the year's total)
ks <- -5:4
es_dat <- rbindlist(lapply(seq_len(nrow(S)), function(i) {
  a <- S$agency_key[i]; e <- S$election[i]
  z <- series[agency_key == a & year %in% (e + ks)]
  base <- mean(log(z[year %in% (e - 5):(e - 2) & share > 0, share]))
  z[share > 0, .(agency_key = a, election = e, k = year - e, y = log(share) - base, D = S$D[i], P = S$P[i])]
}))
es <- rbindlist(lapply(setdiff(ks, -5:-2), function(kk) {
  dd <- copy(es_dat)[k == kk][, election_factor := factor(election)]   # kk: data.table resolves a bare k to the column
  m <- lm(y ~ D + P + election_factor, data = dd); V <- vcovCL(m, cluster = dd$agency_key); b <- coef(m); se <- sqrt(diag(V))
  data.table(k = kk, term = c("D", "P"), estimate = b[c("D", "P")], se = se[c("D", "P")], n = nrow(dd))
}))
es[, `:=`(ci_lower = estimate - 1.96 * se, ci_upper = estimate + 1.96 * se)]
fwrite(es, file.path(out_dir, "agency_budget_rp_event_study.csv"))
print(es[, .(k, term, estimate = round(estimate, 2), ci_lower = round(ci_lower, 2), ci_upper = round(ci_upper, 2), n)])

# ------------------------------------------------------------------ 4. figures
names_map <- unique(panel[, .(agency_key, lineage)])[, .(name = gsub("_", " ", lineage[1])), by = agency_key]
DP <- S[group_post %in% c("D", "P")]
DP[, name := names_map$name[match(agency_key, names_map$agency_key)]]
DP[, lab := sprintf("%s %d", toupper(agency_key), election)]
DP[, panel_lab := fifelse(group_post == "D", "Handed to a designee's follower", "Handed to a loser's follower")]
setorder(DP, panel_lab, -share_pre); DP[, lab := factor(lab, levels = rev(lab))]
DPl <- melt(DP[, .(lab, panel_lab, share_pre, share_post)], id.vars = c("lab", "panel_lab"), variable.name = "when", value.name = "share")
DPl[, when := factor(fifelse(when == "share_pre", "e-5..e-2", "e+1..e+4"), levels = c("e-5..e-2", "e+1..e+4"))]
floor_s <- 0.01
g <- ggplot(DP, aes(y = lab)) +
  geom_vline(xintercept = 1, colour = RULE, linetype = "dashed", linewidth = 0.35) +
  geom_segment(aes(x = pmax(share_pre, floor_s), xend = pmax(share_post, floor_s), yend = lab), colour = INK, linewidth = 0.5) +
  geom_point(data = DPl, aes(x = pmax(share, floor_s), colour = when, shape = when), size = 2.3, fill = "white", stroke = 0.8) +
  scale_colour_manual(values = c("#7a7a7a", INK), name = NULL) + scale_shape_manual(values = c(21, 16), name = NULL) +
  scale_x_log10(breaks = c(0.01, 0.1, 1, 10, 30), labels = c("0.01", "0.1", "1", "10", "30")) +
  facet_wrap(~ panel_lab, scales = "free_y") +
  labs(x = "Share of federal investment, % (log scale)", y = NULL) + theme_paper(14) +
  theme(legend.position = "bottom", strip.text = element_text(hjust = 0, size = 13), panel.grid.major.y = element_line(colour = "#eeeeee"))
ggsave(file.path(out_dir, "agency_budget_dumbbell.pdf"), g, width = 10, height = 4.6, bg = "white", device = "pdf")
ggsave(file.path(out_dir, "agency_budget_dumbbell.png"), g, width = 10, height = 4.6, dpi = 250, bg = "white")
pd <- copy(es)[, x := k + fifelse(term == "D", -0.12, 0.12)]
lab_g <- c(D = "Designee's followers' agencies", P = "Losers' followers' agencies")
g2 <- ggplot(pd, aes(x, estimate)) + geom_hline(yintercept = 0, colour = RULE, linewidth = 0.35) +
  geom_vline(xintercept = -1.5, colour = INK, linewidth = 0.6, linetype = "dashed") +
  geom_linerange(aes(ymin = ci_lower, ymax = ci_upper, colour = term), linewidth = 0.5, show.legend = FALSE) +
  geom_point(aes(shape = term, colour = term), fill = "white", size = 2.6, stroke = 0.8) +
  scale_colour_manual(values = c(D = INK, P = "#7a7a7a"), labels = lab_g, name = NULL) + scale_shape_manual(values = c(D = 16, P = 21), labels = lab_g, name = NULL) +
  scale_x_continuous(breaks = ks) + labs(x = "Years relative to the election", y = "Log share of federal investment,\nminus the agency's e-5..e-2 mean, against unaligned-headed agencies") + theme_paper(16) +
  theme(axis.title.y = element_text(size = 12, lineheight = 0.95), legend.position = "inside", legend.position.inside = c(0.01, 0.98), legend.justification = c(0, 1))
ggsave(file.path(out_dir, "agency_budget_rp_es.pdf"), g2, width = 10, height = 4.1, bg = "white", device = "pdf")
ggsave(file.path(out_dir, "agency_budget_rp_es.png"), g2, width = 10, height = 4.1, dpi = 250, bg = "white")

# ------------------------------------------------------------------ 5. macros
f2 <- function(x) { v <- round(x, 2); s <- formatC(abs(v), format = "f", digits = 2); ifelse(v < 0, paste0("$-$", s), s) }
mac <- function(n, v) sprintf("\\newcommand{\\%s}{%s}", n, v)
g1 <- function(sp, tm, what) main[spec == sp & grepl(tm, term)][[what]]
writeLines(c("% agency_budget_rp_macros.tex (agency_budget_rp.R): reward and penalty on an agency's share of federal investment, each camp's agencies against the unaligned's; permutation intervals. Do not edit by hand.",
  mac("ABRPnD", main$n_D[1]), mac("ABRPnP", main$n_P[1]), mac("ABRPnN", main$n_N[1]),
  mac("ABRPrewardPp", f2(g1("share, pp", "reward", "estimate"))), mac("ABRPrewardPpLo", f2(g1("share, pp", "reward", "perm_ci_lower"))), mac("ABRPrewardPpHi", f2(g1("share, pp", "reward", "perm_ci_upper"))), mac("ABRPrewardPpP", formatC(g1("share, pp", "reward", "perm_p"), format = "f", digits = 2)),
  mac("ABRPpenaltyPp", f2(g1("share, pp", "penalty", "estimate"))), mac("ABRPpenaltyPpLo", f2(g1("share, pp", "penalty", "perm_ci_lower"))), mac("ABRPpenaltyPpHi", f2(g1("share, pp", "penalty", "perm_ci_upper"))), mac("ABRPpenaltyPpP", formatC(g1("share, pp", "penalty", "perm_p"), format = "f", digits = 2)),
  mac("ABRPrewardLog", f2(g1("log share", "reward", "estimate"))), mac("ABRPrewardLogLo", f2(g1("log share", "reward", "perm_ci_lower"))), mac("ABRPrewardLogHi", f2(g1("log share", "reward", "perm_ci_upper"))), mac("ABRPrewardLogP", formatC(g1("log share", "reward", "perm_p"), format = "f", digits = 2)),
  mac("ABRPrewardLogPct", formatC(100 * (exp(g1("log share", "reward", "estimate")) - 1), format = "f", digits = 0)),
  mac("ABRPpenaltyLog", f2(g1("log share", "penalty", "estimate"))), mac("ABRPpenaltyLogLo", f2(g1("log share", "penalty", "perm_ci_lower"))), mac("ABRPpenaltyLogHi", f2(g1("log share", "penalty", "perm_ci_upper"))), mac("ABRPpenaltyLogP", formatC(g1("log share", "penalty", "perm_p"), format = "f", digits = 2)),
  mac("ABRProbMin", f2(min(rob[grepl("reward|any", term) & !grepl("placebo", spec), estimate]))), mac("ABRProbMax", f2(max(rob[grepl("reward|any", term) & !grepl("placebo", spec), estimate]))),
  mac("ABRProbPmax", formatC(max(rob[grepl("reward|any", term) & !grepl("placebo", spec), perm_p]), format = "f", digits = 2)),
  mac("ABRPplaceboLog", f2(rob[grepl("placebo", spec) & grepl("reward", term), estimate])), mac("ABRPplaceboLogP", formatC(rob[grepl("placebo", spec) & grepl("reward", term), perm_p], format = "f", digits = 2))),
  file.path(tab_dir, "agency_budget_rp_macros.tex"))
cat("agency_budget_rp done\n")
