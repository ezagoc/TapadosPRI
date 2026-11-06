# Heterogeneity by the type of the tie to the contender, deck figure and macros (4 November 2026, the user's request:
# which tie matters most, the college friend or the work colleague?). Reads heterogeneity.csv (heterogeneity.R: the main
# window contrast estimated within each subgroup, every split defined by e-2) and draws the tie splits in the style of
# the deck's heterogeneity figure (figures.R): any co-work tie against school ties only; the type of the earliest tie;
# the age of co-work ties; the strength of the tie (smallest focus). Writes het_ties.{pdf,png} and
# tables/het_ties_macros.tex. Run inside the staging environment after heterogeneity.R:
#   Rscript code/04-analysis/main_direct_tie/het_ties_figure.R
suppressPackageStartupMessages({library(data.table); library(ggplot2)})
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
db_root <- Sys.getenv("TAPADOSPRI_DB_ROOT", file.path(path.expand("~"), "Dropbox", "TapadosPRI"))
out_dir <- Sys.getenv("TAPADOS_MAIN_OUTPUT_DIR", file.path(db_root, "output", "main_direct_tie"))
tab_dir <- file.path(out_dir, "tables"); dir.create(tab_dir, showWarnings = FALSE)
INK <- "#1a1a1a"; MUTED <- "#666666"; RULE <- "#b3b3b3"; FAM <- "Helvetica"
theme_paper <- function(base = 15) theme_minimal(base_size = base, base_family = FAM) +
  theme(panel.grid.minor = element_blank(), panel.grid.major.y = element_blank(), axis.text = element_text(colour = INK),
        strip.background = element_blank())

ht <- fread(file.path(out_dir, "heterogeneity.csv"))
sub <- ht[row_type == "subgroup" & !is.na(estimate)]
keep <- list(c("tie_mix", "Ties to the contender"), c("tie_stage", "When they first\nworked together"))   # 6 Nov 2026: two blocks
sub <- sub[split %in% sapply(keep, `[`, 1)]
sub <- sub[group != "Work and school ties"]   # 18 followers, interval wider than the axis; the bullet reports them
sub[, dimension := factor(sapply(keep, `[`, 2)[match(split, sapply(keep, `[`, 1))], levels = sapply(keep, `[`, 2))]
sub[, group := gsub("−", "-", gsub("e-2", "e-2", group))]
sub <- sub[order(dimension, -level)]
sub[, row := factor(paste(split, group), levels = rev(paste(split, group)))]
pooled <- fread(file.path(out_dir, "robustness.csv"))[1, estimate]
g <- ggplot(sub, aes(x = estimate, y = row)) +
  geom_vline(xintercept = 0, colour = RULE, linewidth = 0.35) +
  geom_vline(xintercept = pooled, colour = "#940034", linewidth = 0.5, linetype = "dashed") +
  geom_linerange(aes(xmin = ci_lower, xmax = ci_upper), colour = INK, linewidth = 0.45) +
  geom_linerange(aes(xmin = ci90_lower, xmax = ci90_upper), colour = INK, linewidth = 1.5) +
  geom_point(colour = INK, size = 2.4) +
  geom_text(aes(x = ci_upper + 0.12, label = sprintf("%.2f  (n = %s)", estimate, format(n, big.mark = ","))), hjust = 0,
            colour = MUTED, size = 3.8, family = FAM) +
  scale_y_discrete(labels = setNames(sub$group, sub$row)) +
  scale_x_continuous(limits = c(-1.6, 4.2), breaks = seq(-1, 3, 1)) +
  facet_grid(dimension ~ ., scales = "free_y", space = "free_y", switch = "y") +
  labs(x = "Premium of a tie to the designee, rank positions, by subgroup", y = NULL) + theme_paper(15) +
  theme(axis.text.y = element_text(size = 12, colour = INK), axis.line.y = element_blank(), axis.ticks.y = element_blank(),
        strip.placement = "outside", strip.text.y.left = element_text(size = 11.5, angle = 0, hjust = 1, colour = MUTED),
        panel.spacing.y = unit(0.35, "lines"), axis.title.x = element_text(size = 12.5))
ggsave(file.path(out_dir, "het_ties.pdf"), g, width = 10, height = 3.4, bg = "white", device = "pdf")
ggsave(file.path(out_dir, "het_ties.png"), g, width = 10, height = 3.4, dpi = 250, bg = "white")

f2 <- function(x) { s <- formatC(abs(x), format = "f", digits = 2); ifelse(x < 0, paste0("$-$", s), s) }
mac <- function(n, v) sprintf("\\newcommand{\\%s}{%s}", n, v)
row_of <- function(sp, grp) ht[row_type == "subgroup" & split == sp & group == grp]   # any split of heterogeneity.csv
con_of <- function(sp) ht[split == sp & row_type == "contrast"][1]
w <- row_of("tie_work_any", "Any co-work tie"); s_ <- row_of("tie_work_any", "School ties only"); cw <- con_of("tie_work_any")
cwk <- row_of("tie_type", "Co-work"); ced <- row_of("tie_type", "Co-education"); ct <- con_of("tie_type")
rec <- row_of("tie_age_cowork", "Co-work tie within 8 years of e-2"); old <- row_of("tie_age_cowork", "Co-work tie formed earlier")
sm <- row_of("tie_strength", "A tie in a focus of 10 or fewer"); lg <- row_of("tie_strength", "Only larger foci")
writeLines(c("% het_ties_macros.tex (het_ties_figure.R, from heterogeneity.csv). Do not edit by hand.",
  mac("HETworkEst", f2(w$estimate)), mac("HETworkLo", f2(w$ci_lower)), mac("HETworkHi", f2(w$ci_upper)), mac("HETworkN", format(w$n, big.mark = ",")),
  mac("HETschoolEst", f2(s_$estimate)), mac("HETschoolLo", f2(s_$ci_lower)), mac("HETschoolHi", f2(s_$ci_upper)), mac("HETschoolN", format(s_$n, big.mark = ",")),
  mac("HETworkSchoolDiff", f2(cw$estimate)), mac("HETworkSchoolDiffLo", f2(cw$ci_lower)), mac("HETworkSchoolDiffHi", f2(cw$ci_upper)),
  mac("HETearliestWorkEst", f2(cwk$estimate)), mac("HETearliestEduEst", f2(ced$estimate)), mac("HETearliestEduLo", f2(ced$ci_lower)), mac("HETearliestEduHi", f2(ced$ci_upper)),
  mac("HETrecentEst", f2(rec$estimate)), mac("HEToldEst", f2(old$estimate)), mac("HETsmallEst", f2(sm$estimate)), mac("HETlargeEst", f2(lg$estimate)),
  mac("HETsplits", uniqueN(ht$split)),
  mac("HETworkOnlyEst", f2(row_of("tie_mix", "Work ties only")$estimate)), mac("HETworkOnlyLo", f2(row_of("tie_mix", "Work ties only")$ci_lower)), mac("HETworkOnlyHi", f2(row_of("tie_mix", "Work ties only")$ci_upper)), mac("HETworkOnlyN", format(row_of("tie_mix", "Work ties only")$n, big.mark = ",")),
  mac("HETschoolOnlyEst", f2(row_of("tie_mix", "School ties only")$estimate)), mac("HETschoolOnlyLo", f2(row_of("tie_mix", "School ties only")$ci_lower)), mac("HETschoolOnlyHi", f2(row_of("tie_mix", "School ties only")$ci_upper)), mac("HETschoolOnlyN", format(row_of("tie_mix", "School ties only")$n, big.mark = ",")),
  mac("HETbothEst", f2(row_of("tie_mix", "Work and school ties")$estimate)), mac("HETbothLo", f2(row_of("tie_mix", "Work and school ties")$ci_lower)), mac("HETbothHi", f2(row_of("tie_mix", "Work and school ties")$ci_upper)), mac("HETbothN", format(row_of("tie_mix", "Work and school ties")$n, big.mark = ",")),
  mac("HETmixDiff", f2(con_of("tie_mix")$estimate)), mac("HETmixDiffLo", f2(con_of("tie_mix")$ci_lower)), mac("HETmixDiffHi", f2(con_of("tie_mix")$ci_upper)),
  mac("HETearlyEst", f2(row_of("tie_stage", "First worked together in the first five years of the career")$estimate)), mac("HETearlyLo", f2(row_of("tie_stage", "First worked together in the first five years of the career")$ci_lower)), mac("HETearlyHi", f2(row_of("tie_stage", "First worked together in the first five years of the career")$ci_upper)), mac("HETearlyN", format(row_of("tie_stage", "First worked together in the first five years of the career")$n, big.mark = ",")),
  mac("HETlaterEst", f2(row_of("tie_stage", "First worked together later")$estimate)), mac("HETlaterLo", f2(row_of("tie_stage", "First worked together later")$ci_lower)), mac("HETlaterHi", f2(row_of("tie_stage", "First worked together later")$ci_upper)), mac("HETlaterN", format(row_of("tie_stage", "First worked together later")$n, big.mark = ",")),
  mac("HETstageDiff", f2(con_of("tie_stage")$estimate)), mac("HETstageDiffLo", f2(con_of("tie_stage")$ci_lower)), mac("HETstageDiffHi", f2(con_of("tie_stage")$ci_upper)),
  mac("HETbelowSevenEst", f2(row_of("rung7", "Below rank 7")$estimate)), mac("HETbelowSevenLo", f2(row_of("rung7", "Below rank 7")$ci_lower)), mac("HETbelowSevenHi", f2(row_of("rung7", "Below rank 7")$ci_upper)),
  mac("HETsevenPlusEst", f2(row_of("rung7", "Rank 7 or above")$estimate)), mac("HETsevenPlusLo", f2(row_of("rung7", "Rank 7 or above")$ci_lower)), mac("HETsevenPlusHi", f2(row_of("rung7", "Rank 7 or above")$ci_upper)),
  mac("HETsevenDiff", f2(con_of("rung7")$estimate)), mac("HETsevenDiffLo", f2(con_of("rung7")$ci_lower)), mac("HETsevenDiffHi", f2(con_of("rung7")$ci_upper))),
  file.path(tab_dir, "het_ties_macros.tex"))
print(sub[, .(split, group, estimate = round(estimate, 2), ci_lower = round(ci_lower, 2), ci_upper = round(ci_upper, 2), n)])
cat("het_ties figure and macros written\n")
