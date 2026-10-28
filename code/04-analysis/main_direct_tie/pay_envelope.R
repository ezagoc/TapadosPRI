# Back-of-the-envelope: what a career rung is worth in official pay (written 20 October 2026, after a coauthor asked
# for a financial reading of the rung estimates: one rung at the bottom of the ladder is not one rung at the top).
# Inputs: data/rank/official_pay_real.csv (02-rank/03_official_pay_real.py: official monthly pay of the ladder's
# offices in 1927 and 1999, both in 2025 pesos) and output/main_direct_tie/analysis_sample.csv (the followers' rungs).
# The file's `rung` is the ten-rung display ladder (president = 1); the design's rung is 11 - that (cabinet = 9,
# undersecretary = 7, director general = 6, deputy director general = 5, area director = 4, department head = 3).
# Pay at rungs the sources do not price (8: governors of major states; 1-2: local posts and advisers) is interpolated
# or extrapolated log-linearly and used only for the followers' average step. Writes pay_ladder.csv, pay_ladder.{pdf,png}
# and tables/pay_macros.tex. Run from the repo root: Rscript code/04-analysis/main_direct_tie/pay_envelope.R
suppressPackageStartupMessages({library(data.table); library(ggplot2)})
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
db_root <- Sys.getenv("TAPADOSPRI_DB_ROOT", file.path(path.expand("~"), "Dropbox", "TapadosPRI"))
out_dir <- Sys.getenv("TAPADOS_MAIN_OUTPUT_DIR", file.path(db_root, "output", "main_direct_tie"))
tab_dir <- file.path(out_dir, "tables"); dir.create(tab_dir, showWarnings = FALSE)
source(file.path(script_dir, "design_tools.R"))   # house style only
USD <- 19   # pesos per dollar, 2025 average (rounded)

pay <- fread(file.path(db_root, "data", "rank", "official_pay_real.csv"))
pay[, rung := fifelse(rung == 1L, 10L, 11L - rung)]
# the department head and the subdirector share rung 3 in 1999: geometric mean
lad <- pay[, .(office = office[1], pay_1927 = exp(mean(log(pay_1927_monthly_2025_pesos), na.rm = TRUE)),
               pay_1999 = exp(mean(log(pay_1999_monthly_mid_2025_pesos), na.rm = TRUE))), by = rung][order(rung)]
lad[is.nan(pay_1927), pay_1927 := NA_real_][is.nan(pay_1999), pay_1999 := NA_real_]
lad[rung == 3L, office := "Department head"]
lad[, office := sub(" \\(1927.*", "", office)]
offices <- c(`9` = "Cabinet secretary", `8` = "Governor of a major state", `7` = "Undersecretary", `6` = "Director general",
             `5` = "Deputy director general", `4` = "Area director", `3` = "Department head", `2` = "Adviser, staff",
             `1` = "Local office")

# Pay per rung: the geometric average step from the department head (3) to the cabinet secretary (9).
step <- function(col) lad[rung == 9L, get(col)] / lad[rung == 3L, get(col)]
per_rung_1999 <- step("pay_1999")^(1 / 6) - 1
per_rung_1927 <- step("pay_1927")^(1 / 6) - 1
# Regression slopes of log pay on the rung (priced rungs 3-9) as a check.
slope <- function(col) { d <- lad[rung %in% 3:9 & !is.na(get(col))]; coef(lm(log(d[[col]]) ~ d$rung))[2] }
sl_1999 <- unname(slope("pay_1999")); sl_1927 <- unname(slope("pay_1927"))

# Full 1999 schedule on rungs 1-9: rung 8 interpolated between 7 and 9; rungs 1-2 extrapolated with the average step.
sched <- data.table(rung = 1:9)
sched[, pay := lad$pay_1999[match(rung, lad$rung)]]
sched[rung == 8L, pay := sqrt(lad[rung == 7L, pay_1999] * lad[rung == 9L, pay_1999])]
sched[rung == 2L, pay := lad[rung == 3L, pay_1999] / (1 + per_rung_1999)]
sched[rung == 1L, pay := lad[rung == 3L, pay_1999] / (1 + per_rung_1999)^2]
sched[, step_up := c(pay[-1] / pay[-.N] - 1, NA)]   # one rung up from this rung (none above the cabinet)

# Followers: the designee's exclusive followers' rung before the succession.
S <- fread(file.path(out_dir, "analysis_sample.csv"))
D <- S[treated == 1L]
D[, step := sched$step_up[match(pre, sched$rung)]]
D[pre == 9L, step := NA_real_]                   # a cabinet secretary cannot climb a rung within the ladder
D[, gain_1 := sched$pay[match(pmin(pre + 1L, 9L), sched$rung)] - sched$pay[match(pre, sched$rung)]]
med_rung <- as.integer(median(D$pre))
mean_step <- mean(D$step, na.rm = TRUE); med_step <- median(D$step, na.rm = TRUE)
mean_gain <- mean(D$gain_1)                       # 2025 pesos a month for one rung, at the followers' positions
# equal weight per succession, as the estimator
mean_gain_eq <- D[, .(g = mean(gain_1), s = mean(step, na.rm = TRUE)), by = election][, .(g = mean(g), s = mean(s))]

main_est <- fread(file.path(out_dir, "robustness.csv"))[1, estimate]
es <- fread(file.path(out_dir, "event_study_summary.csv"))
win_est <- es[outcome == "rank" & contrast == "main_window_average", estimate]
rp <- fread(file.path(out_dir, "rp_windows.csv"))
reward <- rp[grepl("^Main", spec) & group == "D", estimate][1]
penalty <- rp[grepl("^Main", spec) & group == "P", estimate][1]
if (length(reward) == 0 || is.na(reward)) { reward <- 0.60; penalty <- -0.35 }
pct <- function(rungs, r = per_rung_1999) 100 * ((1 + r)^rungs - 1)

ladder_out <- merge(lad, sched[, .(rung, pay_1999_filled = pay, step_up_1999 = step_up)], by = "rung", all = TRUE)
ladder_out[, office := offices[as.character(rung)]]
fwrite(ladder_out, file.path(out_dir, "pay_ladder.csv"))

# Figure: official monthly pay by rung, 1927 and 1999, log scale.
short <- c(`9` = "Cabinet\nsecretary", `8` = "Governor,\nmajor state", `7` = "Under-\nsecretary", `6` = "Director\ngeneral",
           `5` = "Deputy\ndirector general", `4` = "Area\ndirector", `3` = "Department\nhead")
pl <- melt(lad[rung <= 9L], id.vars = c("rung", "office"), measure.vars = c("pay_1927", "pay_1999"), variable.name = "year", value.name = "pay")
pl <- pl[!is.na(pay)][, year := factor(year, c("pay_1927", "pay_1999"), c("1927", "1999"))]
g <- ggplot(pl, aes(rung, pay / 1000, shape = year, linetype = year)) +
  geom_line(colour = INK, linewidth = 0.45) + geom_point(colour = INK, fill = "white", size = 2.6, stroke = 0.8) +
  scale_shape_manual(values = c(21, 16), name = NULL) + scale_linetype_manual(values = c("dashed", "solid"), name = NULL) +
  scale_x_continuous(breaks = 3:9, labels = function(x) paste0(x, "\n", short[as.character(x)])) +
  scale_y_log10(breaks = c(50, 100, 200, 300), labels = function(x) format(x, big.mark = ",")) +
  labs(x = "Rung", y = "Official monthly pay\n(thousand 2025 pesos, log scale)") + theme_paper(17) +
  theme(axis.text.x = element_text(size = 10.5, lineheight = 0.85), axis.title.y = element_text(size = 13, lineheight = 0.95),
        legend.position = "inside", legend.position.inside = c(0.02, 0.98), legend.justification = c(0, 1),
        legend.text = element_text(size = 14, colour = INK), legend.key = element_blank(), legend.background = element_blank(),
        legend.key.width = unit(1.6, "lines"))
ggsave(file.path(out_dir, "pay_ladder.pdf"), g, width = 10, height = 4.1, bg = "white", device = "pdf")
ggsave(file.path(out_dir, "pay_ladder.png"), g, width = 10, height = 4.1, dpi = 250, bg = "white")

# Figure for the deck: the ladder as two panels sharing the rows. Left, official monthly pay of each office (1999 scale in
# 2025 pesos; rungs 1, 2 and 8 have no published pay and are interpolated, drawn lighter). Right, where the designee's
# followers stood before the succession (share of followers at each rung at e-2, equal weight per succession).
# Complete the election x rung grid with zeros before averaging, so a rung absent from a succession counts as 0% there.
foll <- D[, .N, by = .(election, pre)][CJ(election = unique(D$election), pre = 1:9), on = .(election, pre)]
foll[is.na(N), N := 0L][, share := N / sum(N), by = election]
foll <- foll[, .(share = mean(share)), by = pre]
worth <- merge(sched[, .(rung, pay)], foll[, .(rung = pre, share)], by = "rung", all.x = TRUE)[is.na(share), share := 0]
worth[, office := offices[as.character(rung)]][, filled := rung %in% c(1L, 2L, 8L)]
worth[, office := factor(office, levels = offices[as.character(9:1)][9:1])]
wl <- rbind(worth[, .(rung, office, filled, panel = "Official pay of the office\n(thousand 2025 pesos a month)", value = pay / 1000,
                      lab = paste0(fifelse(filled, "~", ""), formatC(round(pay / 1000), format = "d")))],
            worth[, .(rung, office, filled = FALSE, panel = "Where the designee's followers stood\nbefore the succession (% of followers)",
                      value = 100 * share, lab = sprintf("%.0f%%", 100 * share))])
wl[, panel := factor(panel, levels = unique(panel))]
wl[, shade := fifelse(as.integer(panel) == 2L, "share", fifelse(filled, "filled", "pay"))]
g_w <- ggplot(wl, aes(x = value, y = office)) +
  geom_col(aes(fill = shade), width = 0.62) +
  geom_text(aes(x = value, label = lab), hjust = -0.18, colour = INK, size = 4.3, family = FAM) +
  scale_fill_manual(values = c(pay = INK, filled = "#bdbdbd", share = "#8c8c8c"), guide = "none") +
  scale_x_continuous(expand = expansion(mult = c(0, 0.22))) +
  facet_wrap(~panel, scales = "free_x") +
  labs(x = NULL, y = NULL) + theme_paper(15) +
  theme(strip.background = element_blank(), strip.text = element_text(size = 13.5, colour = INK, lineheight = 0.95, hjust = 0),
        axis.text.y = element_text(size = 13, colour = INK), axis.text.x = element_blank(), axis.ticks.x = element_blank(),
        axis.line.x = element_blank(), panel.spacing.x = unit(2.2, "lines"))
ggsave(file.path(out_dir, "pay_worth.pdf"), g_w, width = 10, height = 4.1, bg = "white", device = "pdf")
ggsave(file.path(out_dir, "pay_worth.png"), g_w, width = 10, height = 4.1, dpi = 250, bg = "white")

f0 <- function(x) formatC(round(x), format = "d", big.mark = ",")
f1 <- function(x) formatC(x, format = "f", digits = 1)
m <- c(
  PAYperRungNN = f0(100 * per_rung_1999), PAYperRungTS = f0(100 * per_rung_1927),
  PAYslopeNN = f0(100 * (exp(sl_1999) - 1)), PAYslopeTS = f0(100 * (exp(sl_1927) - 1)),
  PAYstepBottom = f0(100 * sched[rung == 3L, step_up]), PAYstepAreaDir = f0(100 * sched[rung == 4L, step_up]),
  PAYstepDeputyDG = f0(100 * sched[rung == 5L, step_up]), PAYstepDG = f0(100 * sched[rung == 6L, step_up]),
  PAYstepTop = f0(100 * (lad[rung == 9L, pay_1999] / lad[rung == 7L, pay_1999] - 1)),
  PAYratioCabDeptTS = f1(lad[rung == 9L, pay_1927] / lad[rung == 3L, pay_1927]),
  PAYratioCabDeptNN = f1(lad[rung == 9L, pay_1999] / lad[rung == 3L, pay_1999]),
  PAYratioCabDGTS = f1(lad[rung == 9L, pay_1927] / lad[rung == 6L, pay_1927]),
  PAYratioCabDGNN = f1(lad[rung == 9L, pay_1999] / lad[rung == 6L, pay_1999]),
  PAYpayDeptNN = f0(lad[rung == 3L, pay_1999] / 1000), PAYpayDGNN = f0(lad[rung == 6L, pay_1999] / 1000),
  PAYpayCabNN = f0(lad[rung == 9L, pay_1999] / 1000), PAYpayCabTS = f0(lad[rung == 9L, pay_1927] / 1000),
  PAYpayDeptTS = f0(lad[rung == 3L, pay_1927] / 1000),
  PAYmedianRung = as.character(med_rung), PAYmedianOffice = unname(tolower(offices[as.character(med_rung)])),
  PAYmeanStep = f0(100 * mean_step), PAYmedianStep = f0(100 * med_step),
  PAYgainOne = f0(mean_gain_eq$g / 1000), PAYgainOneUSD = f0(mean_gain_eq$g / USD),
  PAYgainOneUSDapprox = f0(round(mean_gain_eq$g / USD, -2)),
  PAYshareAreaDir = f0(100 * foll[pre == 4L, share]), PAYshareDG = f0(100 * foll[pre == 6L, share]),
  PAYshareUnder = f0(100 * foll[pre == 7L, share]), PAYshareTopThree = f0(100 * foll[pre >= 7L, sum(share)]),
  PAYshareBottomThree = f0(100 * foll[pre <= 3L, sum(share)]),
  PAYgainMain = f0(main_est * mean_gain_eq$g / 1000), PAYgainMainUSD = f0(main_est * mean_gain_eq$g / USD),
  PAYgainWindow = f0(win_est * mean_gain_eq$g / 1000), PAYgainWindowUSD = f0(win_est * mean_gain_eq$g / USD),
  PAYgainMainUSDapprox = f0(round(main_est * mean_gain_eq$g / USD, -2)), PAYgainWindowUSDapprox = f0(round(win_est * mean_gain_eq$g / USD, -2)),
  PAYgainMainFourYears = f1(4 * 12 * main_est * mean_gain_eq$g / 1e6),
  PAYgainWindowFourYears = f1(4 * 12 * win_est * mean_gain_eq$g / 1e6),
  PAYmainPct = f0(pct(main_est)), PAYwindowPct = f0(pct(win_est)), PAYrewardPct = f0(pct(reward)),
  PAYpenaltyPct = f0(-pct(penalty)), PAYusd = as.character(USD),
  PAYmainEst = formatC(main_est, format = "f", digits = 2), PAYwindowEst = formatC(win_est, format = "f", digits = 2)
)
names(m) <- sub("\\..*$", "", names(m))
writeLines(c("% pay_macros.tex -- official pay per rung (pay_envelope.R). Do not edit by hand.",
             sprintf("\\newcommand{\\%s}{%s}", names(m), m)), file.path(tab_dir, "pay_macros.tex"))
print(ladder_out[, .(rung, office, pay_1927 = round(pay_1927 / 1000), pay_1999 = round(pay_1999 / 1000),
                     filled_1999 = round(pay_1999_filled / 1000), step_up = round(100 * step_up_1999))])
cat(sprintf("\nPay per rung, geometric 3->9: 1927 %.0f%%, 1999 %.0f%%; regression slopes %.0f%%, %.0f%%\n",
            100 * per_rung_1927, 100 * per_rung_1999, 100 * (exp(sl_1927) - 1), 100 * (exp(sl_1999) - 1)))
cat(sprintf("Designee's followers: median rung %d (%s); one rung up = %.0f%% on average (median %.0f%%), %s thousand pesos a month (equal succession weights)\n",
            med_rung, offices[as.character(med_rung)], 100 * mean_step, 100 * med_step, f0(mean_gain_eq$g / 1000)))
cat(sprintf("Main %.2f rungs = %s%% of pay, %s thousand 2025 pesos a month (%s USD); window %.2f = %s%%, %s thousand\n",
            main_est, m["PAYmainPct"], m["PAYgainMain"], m["PAYgainMainUSD"], win_est, m["PAYwindowPct"], m["PAYgainWindow"]))
cat("written:", file.path(tab_dir, "pay_macros.tex"), "\n")
