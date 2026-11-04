# Simple versions of the five result figures for the deck: one series (or two panels), one 90% band, the moments of the
# succession named in words, and the headline written on the plot. Drawn from the CSVs the estimation scripts write.
# Run: Rscript code/04-analysis/main_direct_tie/figures_simple.R
suppressPackageStartupMessages({library(data.table); library(ggplot2)})
db_root <- Sys.getenv("TAPADOSPRI_DB_ROOT", file.path(path.expand("~"), "Dropbox", "TapadosPRI"))
out <- Sys.getenv("TAPADOS_MAIN_OUTPUT_DIR", file.path(db_root, "output", "main_direct_tie"))
INK <- "#1a1a1a"; ACC <- "#940034"; MUT <- "#8a8a8a"; PALE <- "#f3f3f3"; FAM <- "Helvetica"
th <- function(base = 15) theme_classic(base_size = base, base_family = FAM) +
  theme(axis.line = element_line(colour = MUT), axis.ticks = element_line(colour = MUT), axis.title = element_text(size = 13),
        strip.background = element_blank(), strip.text = element_text(size = 14, colour = INK, hjust = 0))
save <- function(name, g, w = 10, h = 4.1) {
  ggsave(file.path(out, paste0(name, ".pdf")), g, width = w, height = h, bg = "white")
  ggsave(file.path(out, paste0(name, ".png")), g, width = w, height = h, dpi = 200, bg = "white")
}
pfmt <- function(p) if (p < 0.01) "p < 0.01" else sprintf("p = %.2f", p)

# 1. Main event study: the designee's followers' edge over the losers' followers, year by year.
es <- fread(file.path(out, "event_study.csv"))[outcome == "rank" & k >= -6 & k <= 8]
sm <- fread(file.path(out, "event_study_summary.csv"))[outcome == "rank" & contrast == "main_window_average"]
g1 <- ggplot(es, aes(k, estimate)) +
  annotate("rect", xmin = 0.5, xmax = 6.5, ymin = -Inf, ymax = Inf, fill = PALE) +
  geom_hline(yintercept = 0, colour = MUT, linewidth = 0.4) +
  geom_vline(xintercept = c(-1.5, 0.5, 6.5), colour = MUT, linetype = "dotted") +
  geom_ribbon(aes(ymin = ci90_lower, ymax = ci90_upper), fill = ACC, alpha = 0.15) +
  geom_line(colour = ACC, linewidth = 0.9) + geom_point(colour = ACC, size = 2.2) +
  annotate("text", x = -1.5, y = 1.9, label = "dedazo", hjust = 1.05, size = 4.2, colour = INK, family = FAM) +
  annotate("text", x = 0.5, y = 1.9, label = "takes office", hjust = -0.05, size = 4.2, colour = INK, family = FAM) +
  annotate("text", x = 6.5, y = 1.9, label = "leaves", hjust = -0.05, size = 4.2, colour = INK, family = FAM) +
  annotate("text", x = 2.5, y = -0.75, label = sprintf("+%.2f rungs over the first four years (%s)", sm$estimate, pfmt(sm$p_bootstrap)),
           size = 4.4, colour = ACC, family = FAM, fontface = "bold") +
  scale_x_continuous(breaks = seq(-6, 8, 2), labels = function(x) ifelse(x > 0, paste0("+", x), as.character(x))) +
  scale_y_continuous(limits = c(-1.1, 2.1), breaks = c(-1, 0, 1, 2)) +
  labs(x = "Years relative to the election", y = "Rungs above the losers' followers") + th()
save("es_rank_simple", g1)

# 2. Reward and penalty: each group of followers against politicians tied to no contender, two panels.
rp <- fread(file.path(out, "rp_event_study.csv"))[k >= -6 & k <= 8]
rw <- fread(file.path(out, "rp_windows.csv"))[grepl("^Main", spec)]
rp[, panel := factor(group, levels = c("D", "P"), labels = c("The designee's followers", "The losers' followers"))]
lab <- data.table(panel = levels(rp$panel), x = 2.5, y = -1.15,
                  txt = c(sprintf("+%.2f reward (%s)", rw[group == "D", estimate], pfmt(rw[group == "D", p_value])),
                          sprintf("%.2f penalty, over by +5 (%s)", rw[group == "P", estimate], pfmt(rw[group == "P", p_value]))))
lab[, panel := factor(panel, levels = levels(rp$panel))]
g2 <- ggplot(rp, aes(k, estimate)) +
  annotate("rect", xmin = 0.5, xmax = 6.5, ymin = -Inf, ymax = Inf, fill = PALE) +
  geom_hline(yintercept = 0, colour = MUT, linewidth = 0.4) +
  geom_vline(xintercept = c(-1.5, 0.5, 6.5), colour = MUT, linetype = "dotted") +
  geom_ribbon(aes(ymin = ci90_lower, ymax = ci90_upper), fill = ACC, alpha = 0.15) +
  geom_line(colour = ACC, linewidth = 0.9) + geom_point(colour = ACC, size = 2) +
  geom_text(data = lab, aes(x, y, label = txt), size = 4.2, colour = ACC, family = FAM, fontface = "bold", hjust = 0.5) +
  facet_wrap(~panel) +
  scale_x_continuous(breaks = seq(-6, 8, 2), labels = function(x) ifelse(x > 0, paste0("+", x), as.character(x))) +
  scale_y_continuous(limits = c(-1.4, 1.8), breaks = c(-1, 0, 1)) +
  labs(x = "Years relative to the election (designation at -1, takes office at +1, leaves at +6)",
       y = "Rungs above politicians\ntied to no contender") + th() + theme(panel.spacing.x = unit(2, "lines"))
save("rp_simple", g2)

# 3. Timing placebo: the same contrast with the event moved to e+s.
pl <- fread(file.path(out, "placebo_timing.csv"))
g3 <- ggplot(pl, aes(s, estimate)) +
  geom_hline(yintercept = 0, colour = MUT, linewidth = 0.4) +
  geom_vline(xintercept = 0, colour = MUT, linetype = "dotted") +
  geom_ribbon(aes(ymin = ci90_lower, ymax = ci90_upper), fill = ACC, alpha = 0.15) +
  geom_line(colour = ACC, linewidth = 0.9) + geom_point(colour = ACC, size = 2.2) +
  annotate("text", x = 0, y = 2.0, label = "the true dedazo", hjust = -0.05, size = 4.2, colour = INK, family = FAM) +
  annotate("text", x = -7, y = 1.5, label = "both windows before\nthe designation: nothing", hjust = 0, size = 4, colour = MUT, family = FAM, lineheight = 0.9) +
  annotate("text", x = 6, y = -1.15, label = "six years later: the fall-back", hjust = 0.5, size = 4, colour = MUT, family = FAM) +
  annotate("text", x = 0, y = pl[s == 0, estimate] + 0.35, label = sprintf("+%.2f", pl[s == 0, estimate]), size = 4.4, colour = ACC, family = FAM, fontface = "bold") +
  scale_x_continuous(breaks = seq(-8, 8, 2), labels = function(x) ifelse(x > 0, paste0("+", x), as.character(x))) +
  scale_y_continuous(limits = c(-1.5, 2.2), breaks = c(-1, 0, 1, 2)) +
  labs(x = "Years the event is moved from the real dedazo", y = "Estimated edge (rungs)") + th()
save("placebo_simple", g3)

# 4. The losers' followers come back: share tied to a contender of the next slate, by group at e.
tc <- fread(file.path(out, "transitions_contrasts.csv"))[outcome == "tied_next_aspirant"]
stat_of <- function(st, grp) 100 * as.numeric(tc[stat == st][[grp]])
groups <- data.table(grp = c("D", "P", "N"),
                     label = c("The designee's followers", "The losers' followers", "Politicians tied to no contender"))
groups[, `:=`(est = sapply(grp, function(g) stat_of("estimate (equal weight per transition)", g)),
              lo = sapply(grp, function(g) stat_of("ci_5", g)), hi = sapply(grp, function(g) stat_of("ci_95", g)))]
groups[, label := factor(label, levels = rev(label))]
g4 <- ggplot(groups, aes(x = est, y = label)) +
  geom_col(fill = c(MUT, ACC, INK)[match(groups$grp, c("D", "P", "N"))], width = 0.55) +
  geom_errorbarh(aes(xmin = lo, xmax = hi), height = 0.18, colour = "white", linewidth = 0.7) +
  geom_text(aes(x = hi + 2, label = sprintf("%.0f%%", est)), hjust = 0, size = 4.6, colour = INK, family = FAM) +
  scale_x_continuous(limits = c(0, 100), expand = c(0, 0)) +
  labs(x = "Tied to a contender of the next slate by e+4 (%, average of eight successions; 90% band)", y = NULL) +
  th() + theme(axis.text.y = element_text(size = 14, colour = INK), axis.line.y = element_blank(), axis.ticks.y = element_blank())
save("losers_simple", g4, h = 3.4)

# 5. Investment: who ran the money, three groups, before and after the succession.
ih <- fread(file.path(out, "investment_heads_summary.csv"))
ih[, g3 := fifelse(group == "D", "The designee's followers", fifelse(group == "P", "The losers' followers", "Everyone else"))]
inv <- ih[, .(share = sum(share_equal)), by = .(window, g3)]
inv[, g3 := factor(g3, levels = c("The designee's followers", "The losers' followers", "Everyone else"))]
inv[, window := factor(window, levels = c("after", "before"), labels = c("After the succession (+1 to +4)", "Before the succession (-5 to -2)"))]
setorder(inv, window, g3); inv[, xmax := cumsum(share), by = window][, xmin := xmax - share]
g5 <- ggplot(inv) +
  geom_rect(aes(xmin = xmin, xmax = xmax, ymin = as.numeric(window) - 0.3, ymax = as.numeric(window) + 0.3, fill = g3), colour = "white") +
  geom_text(data = inv[share >= 5], aes(x = (xmin + xmax) / 2, y = as.numeric(window), label = sprintf("%.0f%%", share),
                colour = g3), size = 4.4, family = FAM, show.legend = FALSE) +
  geom_text(data = inv[g3 == "The designee's followers"], aes(x = xmax + 1, y = as.numeric(window) + 0.42, label = sprintf("designee's followers: %.1f%%", share)),
            hjust = 0, size = 3.8, colour = ACC, family = FAM, fontface = "bold") +
  scale_fill_manual(values = c(ACC, "#c9a0b1", "#d9d9d9"), name = NULL) +
  scale_colour_manual(values = c("white", INK, INK)) +
  scale_y_continuous(breaks = 1:2, labels = levels(inv$window)) +
  scale_x_continuous(expand = c(0, 0)) +
  labs(x = "Share of federal public investment run by each group's agency heads (%)", y = NULL) +
  th() + theme(legend.position = "bottom", axis.text.y = element_text(size = 13, colour = INK), axis.line.y = element_blank(),
               axis.ticks.y = element_blank())
save("invest_simple", g5, h = 3.6)
cat("simple figures written to", out, "\n")
