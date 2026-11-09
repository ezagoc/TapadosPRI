# How long careers last after a succession (8 November 2026): a survival analysis in the epidemiological style.
# Unit: a politician-succession of the main design (the designee's followers D and the losing contenders' followers P)
# and the entropy-reweighted unaligned (N, rp_setup.R). Time origin: the election year e. Event: leaving politics, the
# last year with a ranked post (position_tiers.csv through estimate_main.R's annual ranks). Follow-up ends in 2009, the
# last year of Camp's biographies: a politician with a ranked post in 2008 or 2009 is still active and is censored at
# 2009 - e. A politician who died while in office or within a year of his last post is censored at that post (death
# ended the career, he did not leave; data/structural/death_years.csv), so the hazards are cause-specific.
#   1. Kaplan-Meier curves of the share still in politics t years after the election, by group, standardized over
#      successions: each politician weighs omega_e / (group size in e) (the unaligned: their entropy weight, normalized
#      within the succession), so every group has the designee's followers' mix of successions, as in the estimator.
#   2. Cox model stratified by succession (a baseline hazard per succession, so comparisons stay within succession),
#      with age and age squared and the window covariates (rank bands, degree, records, prior status); robust standard
#      errors clustered by contender camp (the unaligned: by politician). Hazard ratio of leaving politics, losers'
#      followers against the designee's, and each group against the unaligned. Proportional hazards: cox.zph.
#   3. Restricted mean survival time: years in politics within 12 and 20 years after the election, the area under the
#      standardized curves, with 95% intervals from a bootstrap over contender camps within succession (B = 999).
# Figure: the standardized curves and, below, the number of politicians still in politics and covered by the data.
# Writes career_survival_km.csv, career_survival_cox.csv, career_survival_rmst.csv, career_survival.{pdf,png} and
# tables/career_survival_macros.tex. Run: Rscript slides/analysis/career_survival.R   (run_all.sh sets the environment)
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
invisible(capture.output(source(file.path(script_dir, "estimate_main.R"))))
source(file.path(script_dir, "design_tools.R"))
invisible(capture.output(source(file.path(script_dir, "rp_setup.R"))))
suppressPackageStartupMessages({ library(survival); library(patchwork) })
tab_dir <- file.path(out_dir, "tables"); dir.create(tab_dir, showWarnings = FALSE)
END <- 2009L; HORIZONS <- c(12L, 20L); B_boot <- 999L; set.seed(8112026L)

dead <- read_data("structural", "death_years.csv")[!is.na(death_year), .(death_year = min(death_year)), by = .(pid = person_id)]
last_post <- annual[year <= END & rank > 0L, .(L = max(year)), by = pid]
add_survival <- function(x) {
  x[, L := last_post$L[match(pid, last_post$pid)]]
  x[, dy := dead$death_year[match(pid, dead$pid)]]
  x[, active_end := L >= END - 1L]
  x[, died_in_office := !active_end & !is.na(dy) & dy <= L + 1L]
  x[, time := fifelse(active_end, as.numeric(END - election), pmax(as.numeric(L - election), 0))]
  x[, event := as.integer(!active_end & !died_in_office)]
  x
}

# ------------------------------------------------------------------ the data: followers and the reweighted unaligned
S <- make_weights(A[support == TRUE], bal_formula_window)
S[, wt := fifelse(group == "N", w, 1)]
S[, cl := fifelse(group == "N", paste0("N_", pid), paste(election, patron, sep = "_"))]
S <- add_survival(S)
S[, wk := omega[as.character(election)] * wt / sum(wt), by = .(election, group)]
stopifnot(!anyNA(S$time), all(S$time >= 0))
cat(sprintf("observations %d (D %d, P %d, N %d); events %d, censored at 2009 %d, died in office %d\n", nrow(S),
            sum(S$group == "D"), sum(S$group == "P"), sum(S$group == "N"), sum(S$event), sum(S$active_end), sum(S$died_in_office)))

# ------------------------------------------------------------------ 1. standardized Kaplan-Meier curves
km_curve <- function(d) {
  f <- survfit(Surv(time, event) ~ group, data = d, weights = wk)
  g <- sub("group=", "", rep(names(f$strata), f$strata))
  rbind(data.table(group = unique(g), time = 0, surv = 1), data.table(group = g, time = f$time, surv = f$surv))
}
rmst <- function(curve, h) curve[, {
  tt <- c(time[time < h], h); ss <- surv[time < h]
  .(rmst = sum(diff(tt) * ss))
}, by = group]
km <- km_curve(S)
fwrite(km, file.path(out_dir, "career_survival_km.csv"))

# ------------------------------------------------------------------ 2. Cox model stratified by succession
f_cov <- ~ age + I(age^2 / 100) + pre_band + earlier_band + ldeg + lrec + prior_status
FP <- S[group != "N"][, loser := as.integer(group == "P")]
cox_dp <- coxph(update(f_cov, Surv(time, event) ~ . + loser + strata(election)), data = FP, cluster = cl)
S[, `:=`(gD = as.integer(group == "D"), gP = as.integer(group == "P"))]
cox_all <- coxph(update(f_cov, Surv(time, event) ~ . + gD + gP + strata(election)), data = S, weights = wt, cluster = cl)
hr <- function(fit, term, label) {
  s <- summary(fit)$conf.int; co <- summary(fit)$coefficients
  data.table(contrast = label, hr = s[term, "exp(coef)"], lo = s[term, "lower .95"], hi = s[term, "upper .95"], p = co[term, ncol(co)])
}
cox <- rbind(hr(cox_dp, "loser", "losers' followers vs designee's followers"),
             hr(cox_all, "gD", "designee's followers vs unaligned"), hr(cox_all, "gP", "losers' followers vs unaligned"))
zph <- cox.zph(cox_dp)$table
cox[, ph_test_p := c(zph["loser", "p"], NA, NA)]
fwrite(cox, file.path(out_dir, "career_survival_cox.csv"))

# ------------------------------------------------------------------ 3. restricted mean survival time, camp bootstrap
point <- rbindlist(lapply(HORIZONS, function(h) rmst(km, h)[, horizon := h]))
boot_ids <- function() {
  # resample contender camps within succession for the followers and politicians within succession for the unaligned
  rbindlist(lapply(split(S, S$election), function(d) {
    cls <- unique(d$cl); pick <- sample(cls, length(cls), replace = TRUE)
    d[data.table(cl = pick), on = "cl", allow.cartesian = TRUE]
  }))
}
grid_at <- function(cu, ts = 0:30) cu[, .(time = ts, surv = sapply(ts, function(t) surv[max(which(time <= t))])), by = group]
band_draws <- list()
draws <- rbindlist(lapply(seq_len(B_boot), function(b) {
  d <- boot_ids(); d[, wk := omega[as.character(election)] * wt / sum(wt), by = .(election, group)]
  cu <- km_curve(d); band_draws[[b]] <<- grid_at(cu)[, draw := b]
  rbindlist(lapply(HORIZONS, function(h) rmst(cu, h)[, `:=`(horizon = h, draw = b)]))
}))
bands <- rbindlist(band_draws)[, .(lo = quantile(surv, .025), hi = quantile(surv, .975)), by = .(group, time)]
wide <- function(x) dcast(x, ... ~ group, value.var = "rmst")
pw <- wide(point); dw <- wide(draws)
rm_tab <- rbindlist(lapply(HORIZONS, function(h) {
  p <- pw[horizon == h]; d <- dw[horizon == h]
  rbindlist(list(
    data.table(horizon = h, contrast = "designee's minus losers' followers", estimate = p$D - p$P,
               lo = quantile(d$D - d$P, .025), hi = quantile(d$D - d$P, .975)),
    data.table(horizon = h, contrast = "losers' followers minus unaligned", estimate = p$P - p$N,
               lo = quantile(d$P - d$N, .025), hi = quantile(d$P - d$N, .975)),
    data.table(horizon = h, contrast = "designee's followers minus unaligned", estimate = p$D - p$N,
               lo = quantile(d$D - d$N, .025), hi = quantile(d$D - d$N, .975))))
}))
rm_tab <- merge(rm_tab, melt(pw, id.vars = "horizon", variable.name = "group", value.name = "years")[
  , dcast(.SD, horizon ~ paste0("years_", group), value.var = "years")], by = "horizon")
fwrite(rm_tab, file.path(out_dir, "career_survival_rmst.csv"))

# ------------------------------------------------------------------ figure: standardized curves with the numbers still at risk
at_risk <- rbindlist(lapply(seq(0, 30, 5), function(t) S[time >= t, .(n = .N), by = group][, time := t]))
lab <- c(D = "Designee's followers", P = "Losers' followers", N = "Unaligned, reweighted")
col <- c(D = INK, P = "#8a8a8a", N = "#b9b9b9"); lty <- c(D = "solid", P = "solid", N = "22")
kp <- km[time <= 30][, group := factor(group, levels = c("D", "P", "N"))]
g1 <- ggplot(kp, aes(time, 100 * surv, colour = group, linetype = group)) +
  geom_step(linewidth = 0.9) +
  scale_colour_manual(values = col, labels = lab, name = NULL) + scale_linetype_manual(values = lty, labels = lab, name = NULL) +
  scale_x_continuous(breaks = seq(0, 30, 5), expand = expansion(mult = c(0, 0))) +
  scale_y_continuous(breaks = seq(0, 100, 25), labels = function(x) paste0(x, "%")) +
  coord_cartesian(xlim = c(-1, 30), ylim = c(0, 100), clip = "off") +
  labs(x = NULL, y = "Still in politics") + theme_paper(20) +
  theme(plot.margin = margin(8, 12, 2, 8), axis.text.x = element_blank(), axis.ticks.x = element_blank(),
        legend.position = "inside", legend.position.inside = c(0.99, 0.99), legend.justification = c(1, 1),
        legend.text = element_text(size = 17, colour = INK), legend.key.width = unit(1.6, "cm"), legend.background = element_blank())
# the numbers below the curves: politicians whose career has not ended and who are still covered by the data (to 2009)
ar <- at_risk[group %in% c("D", "P")][, group := factor(group, levels = c("P", "D"))]
g2 <- ggplot(ar, aes(time, group, label = format(n, big.mark = ","))) + geom_text(size = 5.6, family = FAM, colour = MUTED) +
  scale_x_continuous(breaks = seq(0, 30, 5), expand = expansion(mult = c(0, 0))) +
  scale_y_discrete(labels = c(P = "Losers' followers", D = "Designee's followers")) + coord_cartesian(xlim = c(-1, 30), clip = "off") +
  labs(x = "Years after the election", y = NULL, subtitle = "Number still in politics") + theme_paper(19) +
  theme(axis.line.y = element_blank(), axis.ticks.y = element_blank(), plot.margin = margin(0, 12, 6, 8),
        plot.subtitle = element_text(size = 15, colour = MUTED))
g <- g1 / g2 + plot_layout(heights = c(3.4, 1))
ggsave(file.path(out_dir, "career_survival.pdf"), g, width = 10, height = 4.6, bg = "white", device = "pdf")
ggsave(file.path(out_dir, "career_survival.png"), g, width = 10, height = 4.6, dpi = 250, bg = "white")

# ------------------------------------------------------------------ macros and log
f2 <- function(x) { v <- round(x, 2); s <- formatC(abs(v), format = "f", digits = 2); ifelse(v < 0, paste0("$-$", s), s) }
f1 <- function(x) { v <- round(x, 1); s <- formatC(abs(v), format = "f", digits = 1); ifelse(v < 0, paste0("$-$", s), s) }
mac <- function(n, v) sprintf("\\newcommand{\\%s}{%s}", n, v)
r20 <- rm_tab[horizon == 20 & contrast == "designee's minus losers' followers"]
r20P <- rm_tab[horizon == 20 & contrast == "losers' followers minus unaligned"]
writeLines(c("% career_survival_macros.tex (career_survival.R): survival of careers after the succession. Do not edit by hand.",
  mac("CSVhrDP", f2(cox[1, hr])), mac("CSVhrDPLo", f2(cox[1, lo])), mac("CSVhrDPHi", f2(cox[1, hi])),
  mac("CSVhrPN", f2(cox[3, hr])), mac("CSVhrPNLo", f2(cox[3, lo])), mac("CSVhrPNHi", f2(cox[3, hi])),
  mac("CSVrmstD", f1(r20$years_D)), mac("CSVrmstP", f1(r20$years_P)), mac("CSVrmstN", f1(r20$years_N)),
  mac("CSVrmstDiff", f1(r20$estimate)), mac("CSVrmstDiffLo", f1(r20$lo)), mac("CSVrmstDiffHi", f1(r20$hi)),
  mac("CSVrmstPN", f1(r20P$estimate)), mac("CSVrmstPNLo", f1(r20P$lo)), mac("CSVrmstPNHi", f1(r20P$hi))),
  file.path(tab_dir, "career_survival_macros.tex"))
cat("\nHazard ratios of leaving politics (stratified Cox, age and window covariates, clustered by camp):\n"); print(cox[, lapply(.SD, function(x) if (is.numeric(x)) round(x, 3) else x)])
cat("\nYears in politics within h years of the election (restricted mean survival time), with camp-bootstrap 95% intervals:\n"); print(rm_tab[, lapply(.SD, function(x) if (is.numeric(x)) round(x, 2) else x)])
cat("\nShare still in politics at 6, 12 and 20 years:\n"); print(dcast(km[, .(surv = surv[max(which(time <= c(6)))]), by = group], . ~ group))
for (t in c(6, 12, 20)) print(km[, .(t = t, surv = round(100 * surv[max(which(time <= t))], 1)), by = group])
