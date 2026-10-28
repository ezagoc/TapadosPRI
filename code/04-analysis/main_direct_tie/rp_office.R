# Reward and penalty on the extensive margin: holding a ranked post (29 October 2026).
# The section-11 decomposition of reward_punishment.R applied to the office indicator 1(rank > 0): the designee's
# followers (D) and the losing contenders' followers (P), each against one reweighted group of politicians tied to
# no contender (N), as an event study on E_k - E_ref with the section-7 covariates (same support, balancing,
# regression and inference as the rank version; rp_setup.R). Writes rp_event_study_office.csv, the figure
# es_reward_punishment_office.{pdf,png} (percentage points) and tables/rp_office_macros.tex (years 1-4 averages,
# shares). Run after estimate_main.R: Rscript code/04-analysis/main_direct_tie/rp_office.R
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
invisible(capture.output(source(file.path(script_dir, "estimate_main.R"))))
source(file.path(script_dir, "design_tools.R")); suppressPackageStartupMessages(library(ggplot2))
set.seed(18102026L)

source(file.path(script_dir, "rp_setup.R"))

f_es <- ~ election_factor + age + ldeg + lrec + prior_status + fed_exec
S_es <- make_weights(A[support == TRUE], bal_formula_es)
E <- (YA > 0) * 1                       # holds a ranked post in year e + k
ES <- E[A$support == TRUE, , drop = FALSE]
es <- rbindlist(lapply(setdiff(ks, ref), function(k) {
  y <- ES[, as.character(k)] - ES[, as.character(ref)]
  r <- rp_inference(S_es, rp_fit(S_es, y, f_es), B = 20000L); r[, k := k]
}))
es <- rbind(es, data.table(group = c("D", "P"), estimate = 0, ci_lower = 0, ci_upper = 0, ci90_lower = 0, ci90_upper = 0, k = ref), fill = TRUE)
setorder(es, group, k)
es[, outcome := "holds a ranked post"]
fwrite(es, file.path(out_dir, "rp_event_study_office.csv"))

# years 1-4 averages (the headline window of the deck), in percentage points, and the shares of the gap
m14 <- es[k %in% 1:4, .(estimate = mean(estimate)), by = group]
D14 <- m14[group == "D", estimate]; P14 <- m14[group == "P", estimate]; gap <- D14 - P14
share_D <- D14 / gap
last_P <- es[group == "P" & k >= 1 & estimate < 0 & ci90_upper < 0, k]   # years the penalty is below zero at 90%
ext <- fread(file.path(out_dir, "margins_event_study.csv"))[margin == "extensive" & k %in% 1:4, mean(estimate)]
cat(sprintf("years 1-4: designee's followers %+.1f pp, losers' followers %+.1f pp, gap %.1f pp (main extensive estimate %.1f pp)\n",
            100 * D14, 100 * P14, 100 * gap, 100 * ext))
cat(sprintf("shares of the gap: reward %.0f%%, penalty %.0f%%\n", 100 * share_D, 100 * (1 - share_D)))
print(es[, .(group, k, estimate = round(100 * estimate, 1), ci_lower = round(100 * ci_lower, 1), ci_upper = round(100 * ci_upper, 1))])

tab_dir <- file.path(out_dir, "tables"); dir.create(tab_dir, showWarnings = FALSE)
f1 <- function(x) { v <- round(x, 1); s <- formatC(abs(v), format = "f", digits = 1); ifelse(v < 0, paste0("$-$", s), s) }
mac <- function(n, v) sprintf("\\newcommand{\\%s}{%s}", n, v)
writeLines(c("% rp_office_macros.tex (rp_office.R): reward and penalty on holding a ranked post, years 1-4 averages in pp. Do not edit by hand.",
             mac("RPOreward", f1(100 * D14)), mac("RPOpenaltyAbs", f1(abs(100 * P14))), mac("RPOpenalty", f1(100 * P14)),
             mac("RPOgap", f1(100 * gap)), mac("RPOmainExtensive", f1(100 * ext)),
             mac("RPOrewardShare", round(100 * share_D)), mac("RPOpenaltyShare", round(100 * (1 - share_D)))),
           file.path(tab_dir, "rp_office_macros.tex"))

# figure, in the style of es_reward_punishment (figures.R), in percentage points
pd <- copy(es)[, `:=`(x = k + fifelse(group == "D", -0.12, 0.12), estimate = 100 * estimate, ci_lower = 100 * ci_lower,
                      ci_upper = 100 * ci_upper, ci90_lower = 100 * ci90_lower, ci90_upper = 100 * ci90_upper)]
top <- max(pd$ci_upper); bot <- min(pd$ci_lower); span <- top - bot
mk <- data.table(x = c(-1.5, 0.5, 6.5), lab = c("Designation", "New president", "Next president"),
                 col = c("#1a1a1a", RULE, RULE), lw = c(0.6, 0.35, 0.35), tcol = c("#1a1a1a", MUTED, MUTED))
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
  labs(x = x_label_k, y = "Effect on holding a post (pp),\neach group minus the unconnected") + theme_paper(17) +
  theme(axis.title.y = element_text(size = 14, lineheight = 0.95),
        legend.position = "inside", legend.position.inside = c(0.01, 0.80), legend.justification = c(0, 1),
        legend.text = element_text(size = 14, colour = INK), legend.key = element_blank(), legend.background = element_blank())
ggsave(file.path(out_dir, "es_reward_punishment_office.pdf"), g, width = 10, height = 4.1, bg = "white", device = "pdf")
ggsave(file.path(out_dir, "es_reward_punishment_office.png"), g, width = 10, height = 4.1, dpi = 250, bg = "white")
