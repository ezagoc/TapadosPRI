# All slide figures of the main direct-tie design, drawn from the CSVs the estimation scripts write (no estimation
# here). Run last: Rscript code/04-analysis/main_direct_tie/figures.R
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
suppressPackageStartupMessages(library(data.table))
db_root <- Sys.getenv("TAPADOSPRI_DB_ROOT", file.path(path.expand("~"), "Dropbox", "TapadosPRI"))
out_dir <- Sys.getenv("TAPADOS_MAIN_OUTPUT_DIR", file.path(db_root, "output", "main_direct_tie"))
source(file.path(script_dir, "design_tools.R"))
es_rank <- fread(file.path(out_dir, "event_study.csv"))[outcome == "rank"]
es_sum <- fread(file.path(out_dir, "event_study_summary.csv"))[outcome == "rank" & contrast == "main_window_average"]
es_figure(es_rank, "Effect on rank (rungs),\ndesignee's minus losers' followers", "es_rank",
          summary = list(k0 = 1, k1 = 4, est = es_sum$estimate,
                         label = sprintf("Average of years 1 to 4: %.2f (p = %.2f)", es_sum$estimate, es_sum$p_bootstrap)))
es_figure(es_rank, "Effect on rank (rungs),\ndesignee's minus losers' followers", "es_rank_plain")

# Thresholds (robustness.csv, panel B): change in the share of followers whose best post is at or above an office.
rb <- fread(file.path(out_dir, "robustness.csv"))[unit == "pp"]
rb[, label := factor(spec, levels = rev(spec), labels = rev(c("Holds any ranked post", "Director general / other governor, or above",
                                                               "Major-state governor / PRI president, or above", "Cabinet rank, or above")))]
gth <- ggplot(rb, aes(x = 100 * estimate, y = label)) +
  geom_vline(xintercept = 0, colour = RULE, linewidth = 0.35) +
  geom_linerange(aes(xmin = 100 * ci_lower, xmax = 100 * ci_upper), colour = INK, linewidth = 0.45) +
  geom_linerange(aes(xmin = 100 * ci90_lower, xmax = 100 * ci90_upper), colour = INK, linewidth = 1.5) +
  geom_point(colour = INK, size = 2.8) +
  geom_text(aes(x = 100 * ci_upper + 1.2, label = sprintf("%+.0f pp", 100 * estimate)), hjust = 0, colour = MUTED, size = 4.4, family = FAM) +
  scale_x_continuous(limits = c(-6, 34), breaks = seq(0, 30, 10)) +
  labs(x = "Effect on the share of followers at or above the office (percentage points)", y = NULL) + theme_paper(17) +
  theme(axis.text.y = element_text(size = 14, colour = INK), axis.line.y = element_blank(), axis.ticks.y = element_blank(),
        axis.title.x = element_text(size = 13))
ggsave(file.path(out_dir, "thresholds.pdf"), gth, width = 10, height = 3.3, bg = "white", device = "pdf")
ggsave(file.path(out_dir, "thresholds.png"), gth, width = 10, height = 3.3, dpi = 250, bg = "white")

mg <- fread(file.path(out_dir, "margins_event_study.csv"))
es_figure(mg[margin == "extensive"], "Effect on holding a post (pp),\ndesignee's minus losers' followers", "es_extensive", scale = 100)
es_figure(mg[margin == "intensive"], "Effect on rank in office (rungs),\ndesignee's minus losers' followers", "es_intensive")

bg <- fread(file.path(out_dir, "budget_event_study.csv"))
es_figure(bg[outcome == "investment_commanded_pp"], expression("Effect on investment commanded, " * hat(theta)[k] * " (pp)"), "es_budget")
es_figure(bg[outcome == "heads_investment_agency"], expression("Effect on heading an agency, " * hat(theta)[k] * " (pp)"),
          "es_budget_heads", scale = 100)

# Reward and penalty: two groups against the reweighted unaligned, symbol legend.
es <- fread(file.path(out_dir, "rp_event_study.csv")); ks <- -7:8
pd <- copy(es)[, x := k + fifelse(group == "D", -0.12, 0.12)]
top <- max(pd$ci_upper); bot <- min(pd$ci_lower); span <- top - bot
mk <- data.table(x = c(-1.5, 0.5, 6.5), lab = c("Designation", "New president", "Next president"))
lab_g <- c(D = "Designee's followers", P = "Losers' followers")
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
  labs(x = x_label_k, y = "Effect on rank (rungs),\neach group minus the unconnected") + theme_paper(17) +
  theme(axis.title.y = element_text(size = 14, lineheight = 0.95),
        legend.position = "inside", legend.position.inside = c(0.01, 0.80), legend.justification = c(0, 1),
        legend.text = element_text(size = 14, colour = INK), legend.key = element_blank(), legend.background = element_blank())
ggsave(file.path(out_dir, "es_reward_punishment.pdf"), g, width = 10, height = 4.1, bg = "white", device = "pdf")
ggsave(file.path(out_dir, "es_reward_punishment.png"), g, width = 10, height = 4.1, dpi = 250, bg = "white")

# The patron's chair (MAIN_SPEC 12): designee's followers and losers' followers split by their patron's chair.
cs <- fread(file.path(out_dir, "chair_split_event_study.csv"))[estimate != "Pk - Pl, within succession"]
cs[, `:=`(group = fifelse(grepl("^Pk", estimate), "Pk", "Pl"), estimate = value)]
pc <- rbind(es[group == "D", .(group, k, estimate, ci_lower, ci_upper, ci90_lower, ci90_upper)],
            cs[, .(group, k, estimate, ci_lower, ci_upper, ci90_lower, ci90_upper)])
pc[, x := k + c(D = -0.2, Pk = 0, Pl = 0.2)[group]]
top <- max(pc$ci_upper); bot <- min(pc$ci_lower); span <- top - bot
lab_c <- c(D = expression(hat(theta)^D * ": designee's followers"),
           Pk = expression(hat(theta)^{Pk} * ": losers' followers, patron kept a top chair"),
           Pl = expression(hat(theta)^{Pl} * ": losers' followers, patron lost it"))
gc <- ggplot(pc, aes(x, estimate)) +
  geom_hline(yintercept = 0, colour = RULE, linewidth = 0.35) +
  geom_vline(data = mk, aes(xintercept = x), colour = RULE, linewidth = 0.35, linetype = "dashed") +
  geom_text(data = mk, aes(x = x + 0.12, y = top + 0.10 * span, label = lab), hjust = 0, vjust = 0, colour = MUTED, size = 4.2, family = FAM) +
  geom_linerange(aes(ymin = ci_lower, ymax = ci_upper, colour = group), linewidth = 0.45, show.legend = FALSE) +
  geom_linerange(aes(ymin = ci90_lower, ymax = ci90_upper, colour = group), linewidth = 1.5, show.legend = FALSE) +
  geom_point(aes(shape = group, colour = group), fill = "white", size = 2.6, stroke = 0.8) +
  scale_colour_manual(values = c(D = INK, Pk = "#7a7a7a", Pl = "#7a7a7a"), labels = lab_c, name = NULL) +
  scale_shape_manual(values = c(D = 16, Pk = 24, Pl = 21), labels = lab_c, name = NULL) +
  scale_x_continuous(breaks = ks, labels = k_numbers) +
  coord_cartesian(ylim = c(bot - 0.03 * span, top + 0.30 * span), clip = "off") +
  labs(x = x_label_k, y = expression(hat(theta)[k] * " against the unaligned (rungs)")) + theme_paper(17) +
  theme(axis.title.y = element_text(size = 14, lineheight = 0.95),
        legend.position = "inside", legend.position.inside = c(0.01, 0.84), legend.justification = c(0, 1),
        legend.text = element_text(size = 13, colour = INK), legend.key = element_blank(), legend.background = element_blank())
ggsave(file.path(out_dir, "es_chair_split.pdf"), gc, width = 10, height = 4.6, bg = "white", device = "pdf")
ggsave(file.path(out_dir, "es_chair_split.png"), gc, width = 10, height = 4.6, dpi = 250, bg = "white")

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
# Transitions to the next succession (transitions.R): share of each group at e, among those still eligible at e+6, tied
# by e+4 to the designee of e+6 and to any contender of its slate. Equal weight per transition; bootstrap over transitions.
tc <- fread(file.path(out_dir, "transitions_contrasts.csv"))[outcome %in% c("tied_next_designee", "tied_next_aspirant")]
tl <- melt(tc, id.vars = c("outcome", "stat"), measure.vars = c("D", "P", "M", "N"), variable.name = "group")
tl[, stat := fifelse(grepl("estimate", stat), "est", gsub("\\.", "_", stat))]
tw <- dcast(tl, outcome + group ~ stat, value.var = "value")
tw[, group := factor(group, rev(c("D", "P", "M", "N")),
                     labels = rev(c("Designee's followers", "Losers' followers", "Tied to several contenders", "Tied to no contender")))]
tw[, panel := factor(outcome, c("tied_next_designee", "tied_next_aspirant"),
                     labels = c("Tied to the next designee", "Tied to a contender of the next slate"))]
gt <- ggplot(tw, aes(x = 100 * est, y = group)) +
  geom_linerange(aes(xmin = 100 * ci_2_5, xmax = 100 * ci_97_5), colour = INK, linewidth = 0.45) +
  geom_linerange(aes(xmin = 100 * ci_5, xmax = 100 * ci_95), colour = INK, linewidth = 1.5) +
  geom_point(aes(shape = group), colour = INK, fill = "white", size = 2.8, stroke = 0.8, show.legend = FALSE) +
  geom_text(aes(x = 100 * ci_97_5 + 2.5, label = sprintf("%.0f%%", 100 * est)), hjust = 0, colour = MUTED, size = 4.2, family = FAM) +
  scale_shape_manual(values = c(16, 21, 24, 15)[c(4, 3, 2, 1)]) +
  facet_wrap(~ panel, nrow = 1, scales = "free_x") +
  scale_x_continuous(limits = c(0, 105), breaks = seq(0, 100, 25), expand = expansion(mult = c(0, 0.02))) +
  labs(x = "Share of the group at e, among those still eligible at e+6 (%)", y = NULL) + theme_paper(17) +
  theme(axis.text.y = element_text(size = 14, colour = INK), axis.line.y = element_blank(), axis.ticks.y = element_blank(),
        strip.text = element_text(size = 15), panel.spacing.x = unit(2.2, "lines"))
ggsave(file.path(out_dir, "transitions.pdf"), gt, width = 10, height = 3.3, bg = "white", device = "pdf")
ggsave(file.path(out_dir, "transitions.png"), gt, width = 10, height = 3.3, dpi = 250, bg = "white")
cat("figures written to", out_dir, "\n")

# Heterogeneity, deck version (heterogeneity.R): the main contrast by subgroup for the splits shown on the slide; the full set
# of splits is in heterogeneity.pdf and the table.
ht <- fread(file.path(out_dir, "heterogeneity.csv"))[row_type == "subgroup" & !is.na(estimate)]
keep_splits <- c("period", "tie_age_cowork", "tie_type", "career", "prev_designee", "rung", "age")
ht <- ht[split %in% keep_splits]
ht[, dimension := factor(dimension, levels = unique(dimension[order(match(split, keep_splits))]))]
ht[, group := gsub("e-2", "e−2", group)]
ht[, group := gsub("\u2212", "-", group)]   # ASCII hyphen: the pdf device has no U+2212
ht <- ht[order(dimension, level)]
ht[, row := factor(paste(split, group), levels = rev(paste(split, group)))]
ht[, lab := group]
pooled <- fread(file.path(out_dir, "robustness.csv"))[1, estimate]
gh <- ggplot(ht, aes(x = estimate, y = row)) +
  geom_vline(xintercept = 0, colour = RULE, linewidth = 0.35) +
  geom_vline(xintercept = pooled, colour = "#940034", linewidth = 0.5, linetype = "dashed") +
  geom_linerange(aes(xmin = ci_lower, xmax = ci_upper), colour = INK, linewidth = 0.45) +
  geom_linerange(aes(xmin = ci90_lower, xmax = ci90_upper), colour = INK, linewidth = 1.5) +
  geom_point(colour = INK, size = 2.4) +
  geom_text(aes(x = ci_upper + 0.15, label = sprintf("%.2f  (n = %s)", estimate, format(n, big.mark = ","))), hjust = 0,
            colour = MUTED, size = 3.6, family = FAM) +
  scale_y_discrete(labels = setNames(ht$lab, ht$row)) +
  scale_x_continuous(limits = c(-2.2, 5.6), breaks = seq(-2, 4, 1)) +
  facet_grid(dimension ~ ., scales = "free_y", space = "free_y", switch = "y") +
  labs(x = "Effect on the change in highest rung, by subgroup (rungs)", y = NULL) + theme_paper(15) +
  theme(axis.text.y = element_text(size = 11.5, colour = INK), axis.line.y = element_blank(), axis.ticks.y = element_blank(),
        strip.placement = "outside", strip.text.y.left = element_text(size = 11, angle = 0, hjust = 1, colour = MUTED),
        panel.spacing.y = unit(0.35, "lines"), axis.title.x = element_text(size = 12))
ggsave(file.path(out_dir, "heterogeneity_deck.pdf"), gh, width = 10, height = 4.6, bg = "white", device = "pdf")
ggsave(file.path(out_dir, "heterogeneity_deck.png"), gh, width = 10, height = 4.6, dpi = 250, bg = "white")

# Who ran the money, deck version (investment_heads.R): share of federal investment by the group of the agency head,
# before and after the succession, average of the nine successions; the designee's followers first and in ink.
ih <- fread(file.path(out_dir, "investment_heads_summary.csv"))
ih_order <- c("D", "P", "M", "C", "C_other", "outside_pool", "N", "no_head_by_construction", "head_not_found")
ih_labels <- c("Designee's followers", "Losing contenders' followers", "Tied to several contenders", "Contenders of this succession",
               "Contenders of other successions", "Outside the eligible pool", "In the pool, tied to no contender",
               "No head by construction", "Head not found")
ih[, group := factor(group, levels = ih_order, labels = ih_labels)]
ih[, window := factor(window, levels = c("after", "before"), labels = c("After the succession\n(e+1 to e+4)", "Before the succession\n(e−5 to e−2)"))]
ih[, window := factor(gsub("−", "-", as.character(window)), levels = gsub("−", "-", levels(window)))]
setorder(ih, window, group)
ih[, `:=`(xmax = cumsum(share_equal), xmin = cumsum(share_equal) - share_equal), by = window]
fills <- c("#1a1a1a", "#4d4d4d", "#737373", "#8c8c8c", "#a6a6a6", "#bfbfbf", "#d9d9d9", "#ededed", "#f7f7f7")
names(fills) <- ih_labels
gi <- ggplot(ih) +
  geom_rect(aes(xmin = xmin, xmax = xmax, ymin = as.numeric(window) - 0.36, ymax = as.numeric(window) + 0.36, fill = group),
            colour = "white", linewidth = 0.4) +
  geom_text(data = ih[share_equal >= 4], aes(x = (xmin + xmax) / 2, y = as.numeric(window), label = sprintf("%.0f", share_equal),
                                               colour = group), size = 3.8, family = FAM, show.legend = FALSE) +
  scale_fill_manual(values = fills, name = NULL, drop = FALSE) +
  scale_colour_manual(values = setNames(ifelse(seq_along(fills) <= 4, "white", INK), ih_labels), guide = "none") +
  scale_y_continuous(breaks = 1:2, labels = levels(ih$window), expand = expansion(add = 0.5)) +
  scale_x_continuous(breaks = seq(0, 100, 20), expand = expansion(mult = c(0, 0.01))) +
  labs(x = "Share of federal public investment (%), average of the nine successions", y = NULL) + theme_paper(15) +
  theme(axis.text.y = element_text(size = 12, colour = INK, lineheight = 0.9), axis.line.y = element_blank(), axis.ticks.y = element_blank(),
        legend.position = "bottom", legend.text = element_text(size = 10.5, colour = INK), legend.key.size = unit(0.75, "lines"),
        legend.margin = margin(0, 0, 0, 0), axis.title.x = element_text(size = 12)) +
  guides(fill = guide_legend(nrow = 3, byrow = TRUE))
ggsave(file.path(out_dir, "investment_heads_deck.pdf"), gi, width = 10, height = 3.4, bg = "white", device = "pdf")
ggsave(file.path(out_dir, "investment_heads_deck.png"), gi, width = 10, height = 3.4, dpi = 250, bg = "white")
