# All slide figures of the main direct-tie design, drawn from the CSVs the estimation scripts write (no estimation
# here). Run last: Rscript code/04-analysis/main_direct_tie/figures.R
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
suppressPackageStartupMessages(library(data.table))
db_root <- Sys.getenv("TAPADOSPRI_DB_ROOT", file.path(path.expand("~"), "Dropbox", "TapadosPRI"))
out_dir <- Sys.getenv("TAPADOS_MAIN_OUTPUT_DIR", file.path(db_root, "output", "main_direct_tie"))
source(file.path(script_dir, "design_tools.R"))
es_rank <- fread(file.path(out_dir, "event_study.csv"))[outcome == "rank"]
es_figure(es_rank, expression("Effect on rank, " * hat(theta)[k] * " (rungs)"), "es_rank")

mg <- fread(file.path(out_dir, "margins_event_study.csv"))
es_figure(mg[margin == "extensive"], expression("Effect on holding a post, " * hat(theta)[k] * " (pp)"), "es_extensive", scale = 100)
es_figure(mg[margin == "intensive"], expression("Effect on rank in office, " * hat(theta)[k] * " (rungs)"), "es_intensive")

bg <- fread(file.path(out_dir, "budget_event_study.csv"))
es_figure(bg[outcome == "investment_commanded_pp"], expression("Effect on investment commanded, " * hat(theta)[k] * " (pp)"), "es_budget")
es_figure(bg[outcome == "heads_investment_agency"], expression("Effect on heading an agency, " * hat(theta)[k] * " (pp)"),
          "es_budget_heads", scale = 100)

# Reward and penalty: two groups against the reweighted unaligned, symbol legend.
es <- fread(file.path(out_dir, "rp_event_study.csv")); ks <- -7:8
pd <- copy(es)[, x := k + fifelse(group == "D", -0.12, 0.12)]
top <- max(pd$ci_upper); bot <- min(pd$ci_lower); span <- top - bot
mk <- data.table(x = c(-1.5, 0.5, 6.5), lab = c("Designation", "New president", "Next president"))
lab_g <- c(D = expression(hat(theta)^D * ": designee's followers"), P = expression(hat(theta)^P * ": losers' followers"))
g <- ggplot(pd, aes(x, estimate)) +
  geom_hline(yintercept = 0, colour = RULE, linewidth = 0.35) +
  geom_vline(data = mk, aes(xintercept = x), colour = RULE, linewidth = 0.35, linetype = "dashed") +
  geom_text(data = mk, aes(x = x + 0.12, y = top + 0.10 * span, label = lab), hjust = 0, vjust = 0, colour = MUTED, size = 4.2, family = FAM) +
  geom_linerange(aes(ymin = ci_lower, ymax = ci_upper, colour = group), linewidth = 0.45, show.legend = FALSE) +
  geom_linerange(aes(ymin = ci90_lower, ymax = ci90_upper, colour = group), linewidth = 1.5, show.legend = FALSE) +
  geom_point(aes(shape = group, colour = group), fill = "white", size = 2.6, stroke = 0.8) +
  scale_colour_manual(values = c(D = INK, P = "#7a7a7a"), labels = lab_g, name = NULL) +
  scale_shape_manual(values = c(D = 16, P = 21), labels = lab_g, name = NULL) +
  scale_x_continuous(breaks = ks, labels = k_numbers) +
  coord_cartesian(ylim = c(bot - 0.03 * span, top + 0.20 * span), clip = "off") +
  labs(x = x_label_k, y = expression(hat(theta)[k]^D * " and " * hat(theta)[k]^P * " (rungs)")) + theme_paper(17) +
  theme(axis.title.y = element_text(size = 14, lineheight = 0.95),
        legend.position = "inside", legend.position.inside = c(0.01, 0.80), legend.justification = c(0, 1),
        legend.text = element_text(size = 14, colour = INK), legend.key = element_blank(), legend.background = element_blank())
ggsave(file.path(out_dir, "es_reward_punishment.pdf"), g, width = 10, height = 4.1, bg = "white", device = "pdf")
ggsave(file.path(out_dir, "es_reward_punishment.png"), g, width = 10, height = 4.1, dpi = 250, bg = "white")

# Anticipation: new direct ties with each contender by year.
ant <- fread(file.path(out_dir, "anticipation_ties.csv"))[k <= -2]
ant[, who := factor(fifelse(designee, "Designee", "Average losing contender"), levels = c("Designee", "Average losing contender"))]
ga <- ggplot(ant, aes(k, ties, linetype = who, shape = who)) +
  geom_line(colour = INK, linewidth = 0.45) + geom_point(colour = INK, size = 2.2, fill = "white") +
  scale_shape_manual(values = c(16, 21), name = NULL) + scale_linetype_manual(values = c("solid", "dashed"), name = NULL) +
  annotate("text", x = -3.3, y = max(ant[designee == TRUE, ties]) * 0.98, hjust = 1, vjust = 1, colour = MUTED, size = 3.9,
           family = FAM, lineheight = 0.9, label = "1976 and 1982 designees appointed\nto Finance and to Programming\nand Budget") +
  scale_x_continuous(breaks = -10:-2, labels = k_numbers) +
  labs(x = x_label_k, y = "New direct ties formed in the year\n(average per contender)") +
  theme_paper(17) + theme(axis.title.y = element_text(size = 14, lineheight = 0.95),
                          legend.position = "inside", legend.position.inside = c(0.01, 0.99), legend.justification = c(0, 1),
                          legend.text = element_text(size = 14, colour = INK), legend.key = element_blank(),
                          legend.background = element_blank(), legend.key.width = unit(1.6, "lines"))
ggsave(file.path(out_dir, "anticipation_ties.pdf"), ga, width = 10, height = 4.1, bg = "white", device = "pdf")
ggsave(file.path(out_dir, "anticipation_ties.png"), ga, width = 10, height = 4.1, dpi = 250, bg = "white")
cat("figures written to", out_dir, "\n")
