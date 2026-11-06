# The first stage decomposed into reward and penalty (4 November 2026, the user's request after Shanker's comments).
# The outcome of first_stage.R, an indicator that the politician STARTS a new federal executive post in year e+k (and the
# window e..e+1, started in either year), decomposed as in rp_office.R: the designee's followers (D) and the losing
# contenders' followers (P), each against one reweighted group of politicians tied to no contender (N, rp_setup.R),
# the section-7 covariates, Ferman-Pinto inference. The penalty is the exact one (rp_fit_exact, 5 November 2026):
# measured for the same politicians as first_stage.R's gap, so reward - penalty equals that gap by construction (the
# event study against the formula_es design, the windows against the formula_x design, as in first_stage.R). Levels, as in first_stage.R (a start indicator has no baseline to
# difference; the pre-years are the placebo). The previous handover window e-6..e-5 is the placebo window.
# Writes first_stage_rp_event_study.csv, first_stage_rp_window.csv, the figure first_stage_rp.{pdf,png} and
# tables/first_stage_rp_macros.tex. Run inside the staging environment:
#   Rscript slides/analysis/first_stage_rp.R
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
invisible(capture.output(source(file.path(script_dir, "estimate_main.R"))))
source(file.path(script_dir, "design_tools.R")); suppressPackageStartupMessages(library(ggplot2))
invisible(capture.output(source(file.path(script_dir, "rp_setup.R"))))
tab_dir <- file.path(out_dir, "tables"); dir.create(tab_dir, showWarnings = FALSE)
set.seed(4112026L); B_rp <- 20000L

# the first stage's outcome tables (first_stage.R)
pt <- fread(file.path(data_dir, "rank", "position_tiers.csv"), na.strings = c("", "NA"))
pt <- pt[!is.na(year_start) & !is.na(hybrid_rank)]
pt[, `:=`(y0 = as.integer(year_start), rung = pmin(as.integer(floor(hybrid_rank)), 11L))]
fed <- pt[dataset == "govt_positions" & !grepl("^state_|^governor|^mayor|city_council|^local", rule)]
starts <- function(tab, ids, years) paste(ids, years) %in% paste(tab$person_id, tab$y0)
started_in <- function(tab, ids, e, k0, k1) Reduce(`|`, lapply(k0:k1, function(k) starts(tab, ids, e + k)))

f_es <- ~ election_factor + age + ldeg + lrec + prior_status + fed_exec
S_es <- make_weights(A[support == TRUE], bal_formula_es)

# event study: each group against the reweighted unaligned, year by year
d_es <- build_design(formula = formula_es); d_x <- build_design()
es <- rbindlist(lapply(ks, function(k) {
  y <- as.numeric(starts(fed, S_es$pid, S_es$election + k))
  ym <- as.numeric(starts(fed, sample$pid, sample$election + k))[d_es$rows]
  r <- rp_inference(S_es, rp_fit_exact(S_es, y, f_es, d_es, ym), B = B_rp); r[, k := k]
}))
setorder(es, group, k)
fwrite(es, file.path(out_dir, "first_stage_rp_event_study.csv"))

# windows: the appointment window e..e+1 and the previous handover e-6..e-5
win <- rbindlist(lapply(list(c("appointment", 0L, 1L), c("previous_handover", -6L, -5L)), function(wd) {
  y <- as.numeric(started_in(fed, S_es$pid, S_es$election, as.integer(wd[2]), as.integer(wd[3])))
  ym <- as.numeric(started_in(fed, sample$pid, sample$election, as.integer(wd[2]), as.integer(wd[3])))[d_x$rows]
  r <- rp_inference(S_es, rp_fit_exact(S_es, y, f_es, d_x, ym), B = B_rp); r[, window := wd[1]]
}))
fwrite(win, file.path(out_dir, "first_stage_rp_window.csv"))
D01 <- win[window == "appointment" & group == "D", estimate]; P01 <- win[window == "appointment" & group == "P", estimate]
gap <- D01 - P01
cat(sprintf("appointment window e..e+1, started a federal executive post, each group minus the reweighted unaligned:\n  designee's followers %+.1f pp [%.1f, %.1f], losers' followers %+.1f pp [%.1f, %.1f], gap %.1f pp\n",
            100 * D01, 100 * win[window == "appointment" & group == "D", ci_lower], 100 * win[window == "appointment" & group == "D", ci_upper],
            100 * P01, 100 * win[window == "appointment" & group == "P", ci_lower], 100 * win[window == "appointment" & group == "P", ci_upper], 100 * gap))
cat(sprintf("  shares of the gap: reward %.0f%%, penalty %.0f%%\n", 100 * D01 / gap, -100 * P01 / gap))
cat(sprintf("previous handover e-6..e-5: designee's followers %+.1f pp, losers' followers %+.1f pp\n",
            100 * win[window == "previous_handover" & group == "D", estimate], 100 * win[window == "previous_handover" & group == "P", estimate]))
print(es[, .(group, k, estimate = round(100 * estimate, 1), ci_lower = round(100 * ci_lower, 1), ci_upper = round(100 * ci_upper, 1))])

f1 <- function(x) { v <- round(x, 1); s <- formatC(abs(v), format = "f", digits = 1); ifelse(v < 0, paste0("$-$", s), s) }
f0 <- function(x) { v <- round(x); s <- formatC(abs(v), format = "d"); ifelse(v < 0, paste0("$-$", s), s) }
mac <- function(n, v) sprintf("\\newcommand{\\%s}{%s}", n, v)
wa <- win[window == "appointment"]; wp <- win[window == "previous_handover"]
writeLines(c("% first_stage_rp_macros.tex (first_stage_rp.R): the first stage (started a federal executive post in e..e+1) split into a reward and the exact penalty (same politicians; reward - penalty = first_stage.R's gap), pp. Do not edit by hand.",
             mac("FSRPreward", f1(100 * D01)), mac("FSRPrewardLo", f1(100 * wa[group == "D", ci_lower])), mac("FSRPrewardHi", f1(100 * wa[group == "D", ci_upper])),
             mac("FSRPpenalty", f1(100 * P01)), mac("FSRPpenaltyAbs", f1(abs(100 * P01))), mac("FSRPpenaltyLo", f1(100 * wa[group == "P", ci_lower])), mac("FSRPpenaltyHi", f1(100 * wa[group == "P", ci_upper])),
             mac("FSRPgap", f1(100 * gap)), mac("FSRPrewardShare", f0(100 * D01 / gap)), mac("FSRPpenaltyShare", f0(-100 * P01 / gap)),
             mac("FSRPprevReward", f1(100 * wp[group == "D", estimate])), mac("FSRPprevPenalty", f1(100 * wp[group == "P", estimate])),
             mac("FSRPpeakReward", f1(100 * max(es[group == "D" & k %in% 0:1, estimate]))), mac("FSRPpeakRewardYear", es[group == "D" & k %in% 0:1][which.max(estimate), k])),
           file.path(tab_dir, "first_stage_rp_macros.tex"))

# figure, the style of es_reward_punishment_office (rp_office.R), in percentage points
pd <- copy(es)[, `:=`(x = k + fifelse(group == "D", -0.12, 0.12), estimate = 100 * estimate, ci_lower = 100 * ci_lower,
                      ci_upper = 100 * ci_upper, ci90_lower = 100 * ci90_lower, ci90_upper = 100 * ci90_upper)]
top <- max(pd$ci_upper); bot <- min(pd$ci_lower); span <- top - bot
mk <- data.table(x = c(-1.5, 0.5, 6.5), lab = c("Dedazo", "New president", "Next president"),
                 col = c(INK, RULE, RULE), lw = c(0.6, 0.35, 0.35), tcol = c(INK, MUTED, MUTED))
lab_g <- c(D = "Designee's followers", P = "Losers' followers")
g <- ggplot(pd, aes(x, estimate)) +
  geom_hline(yintercept = 0, colour = RULE, linewidth = 0.35) +
  geom_vline(data = mk, aes(xintercept = x), colour = mk$col, linewidth = mk$lw, linetype = "dashed") +
  geom_text(data = mk, aes(x = x + 0.12, y = top + 0.10 * span, label = lab), hjust = 0, vjust = 0, colour = mk$tcol, size = 4.2, family = FAM) +
  geom_linerange(aes(ymin = ci_lower, ymax = ci_upper, colour = group), linewidth = 0.45, show.legend = FALSE) +
  geom_linerange(aes(ymin = ci90_lower, ymax = ci90_upper, colour = group), linewidth = 1.5, show.legend = FALSE) +
  geom_point(aes(shape = group, colour = group), fill = "white", size = 2.6, stroke = 0.8) +
  scale_colour_manual(values = c(D = INK, P = "#7a7a7a"), labels = lab_g, name = NULL) +
  scale_shape_manual(values = c(D = 16, P = 21), labels = lab_g, name = NULL) +
  scale_x_continuous(breaks = ks, labels = k_numbers) +
  coord_cartesian(ylim = c(bot - 0.03 * span, top + 0.20 * span), clip = "off") +
  labs(x = x_label_k, y = "Started a federal executive post (pp),\neach group minus the unconnected") + theme_paper(17) +
  theme(axis.title.y = element_text(size = 14, lineheight = 0.95),
        legend.position = "inside", legend.position.inside = c(0.01, 0.99), legend.justification = c(0, 1),
        legend.text = element_text(size = 14, colour = INK), legend.key = element_blank(), legend.background = element_blank())
ggsave(file.path(out_dir, "first_stage_rp.pdf"), g, width = 10, height = 4.1, bg = "white", device = "pdf")
ggsave(file.path(out_dir, "first_stage_rp.png"), g, width = 10, height = 4.1, dpi = 250, bg = "white")
cat("first_stage_rp: figure and macros written\n")
