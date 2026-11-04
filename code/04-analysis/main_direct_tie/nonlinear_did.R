# Does the linear treatment of an ordinal outcome drive the main result? (seminar comment, 3 November 2026)
# Three checks on the main sample (designee's vs losing contenders' followers, within succession, covariates of the
# main design, equal weight per succession):
#   1. Threshold DiDs: for each rung r = 1..9 the outcome is 1[rank >= r], the change post minus pre, estimated with
#      the main estimator (design_tools.R: regression adjustment, Ferman-Pinto contender-level bootstrap). Each is a
#      difference in probabilities, a binary DiD whose linear estimand is unambiguous; together they trace where on
#      the ladder the premium sits.
#   2. Exponential-mean (Poisson QMLE) DiD in the spirit of Wooldridge (2023, Econometrics Journal): the two-period
#      stacked panel (pre window, post window), E[Y | .] = exp(succession x period, covariates x period, treated,
#      treated x period); the ATT is the average over the treated in the post period of exp(.) with and without the
#      treatment term, i.e. an effect on the original scale under "ratio" parallel trends. Inference: cluster
#      bootstrap by contender group (first pass; the main design's Ferman-Pinto inference does not transfer).
#   3. Roth and Sant'Anna (2023) check: the pre and post rank distributions of the losers' followers against the
#      designee's followers' pre distribution; parallel trends are insensitive to the outcome's functional form when
#      the untreated distribution is stationary, when assignment is as good as random, or a mixture of the two.
# Run after estimate_main.R, inside the deck's staging environment (research/eligibility_refresh_2026_10_27):
#   Rscript code/04-analysis/main_direct_tie/nonlinear_did.R
# Writes nonlinear_threshold.csv, nonlinear_poisson.csv, nonlinear_distributions.csv and tables/nonlinear_macros.tex.
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
invisible(capture.output(source(file.path(script_dir, "estimate_main.R"))))
source(file.path(script_dir, "design_tools.R"))
tab_dir <- file.path(out_dir, "tables"); dir.create(tab_dir, showWarnings = FALSE)
B_boot <- 20000L; seed <- 3112026L

# ------------------------------------------------------------------ 1. threshold DiDs along the ladder
rungs <- 1:9
Ym <- sapply(rungs, function(r) as.numeric(sample$post >= r) - as.numeric(sample$pre >= r))
colnames(Ym) <- paste0("rung", rungs)
d <- build_design()
thr <- estimate_columns(d, cbind(Ym, delta = sample$delta), B = B_boot, seed = seed)$table
thr[, rung := c(rungs, NA)]
base <- sample[treated == 0L, .(share_pre_losers = sapply(rungs, function(r) mean(pre >= r)),
                                share_post_losers = sapply(rungs, function(r) mean(post >= r)))][, rung := rungs]
thr <- merge(thr, base, by = "rung", all.x = TRUE)[order(rung, na.last = TRUE)]
fwrite(thr, file.path(out_dir, "nonlinear_threshold.csv"))
cat("\nThreshold DiDs (pp of followers at rung >= r, designee's minus losers', regression adjusted):\n")
print(thr[, .(column, estimate = round(100 * estimate, 1), lo = round(100 * ci_lower, 1), hi = round(100 * ci_upper, 1),
              p = round(p_bootstrap, 2), losers_pre = round(100 * share_pre_losers, 0))])

# ------------------------------------------------------------------ 2. exponential-mean DiD (Poisson QMLE)
S <- copy(sample)
S[, grp_n := .N, by = .(election, treated)]
S[, w := 1 / grp_n]                                   # each succession-group gets the same total weight
long <- rbind(S[, .(pid, election, network, treated, y = pre, post = 0L, w, pre_band, earlier_band, age, ldeg, lrec, prior_status)],
              S[, .(pid, election, network, treated, y = post, post = 1L, w, pre_band, earlier_band, age, ldeg, lrec, prior_status)])
long[, election_factor := factor(election, levels = elections)]
f_pois <- y ~ election_factor * post + (pre_band + earlier_band + age + ldeg + lrec + prior_status) * post + treated + treated:post
fit_att <- function(dat) {
  m <- suppressWarnings(glm(f_pois, family = quasipoisson, data = dat, weights = w))
  tr <- dat[treated == 1L & post == 1L]
  m1 <- predict(m, newdata = tr, type = "response")
  # the counterfactual keeps the follower's treated-group level (the main effect) and removes only the treated x post term
  tau_name <- grep("^(treated:post|post:treated)$", names(coef(m)), value = TRUE)
  stopifnot(length(tau_name) == 1L)
  cf <- predict(m, newdata = tr, type = "link") - coef(m)[tau_name]
  m0 <- exp(cf)
  att <- weighted.mean(m1 - m0, tr$w)
  ratio <- weighted.mean(m1, tr$w) / weighted.mean(m0, tr$w)
  c(att = att, ratio = ratio, tau = unname(coef(m)[tau_name]))
}
obs <- fit_att(long)
set.seed(seed)
nets <- unique(long[, .(election, network)])
Bp <- 500L
boot <- t(replicate(Bp, {
  draw <- nets[, .SD[sample(.N, .N, replace = TRUE)], by = election]
  draw[, rep := seq_len(.N), by = .(election, network)]
  dd <- merge(long, draw, by = c("election", "network"), allow.cartesian = TRUE)
  tryCatch(fit_att(dd), error = function(e) c(att = NA, ratio = NA, tau = NA))
}))
pois <- data.table(statistic = names(obs), estimate = obs, se_boot = apply(boot, 2, sd, na.rm = TRUE),
                   ci_lower = apply(boot, 2, quantile, 0.025, na.rm = TRUE), ci_upper = apply(boot, 2, quantile, 0.975, na.rm = TRUE))
fwrite(pois, file.path(out_dir, "nonlinear_poisson.csv"))
cat("\nExponential-mean DiD (Poisson QMLE, cluster bootstrap by contender group, ", Bp, " draws):\n", sep = "")
print(pois[, .(statistic, estimate = round(estimate, 3), se_boot = round(se_boot, 3), ci_lower = round(ci_lower, 3), ci_upper = round(ci_upper, 3))])

# ------------------------------------------------------------------ 3. distributions for the Roth-Sant'Anna check
dist <- rbindlist(lapply(0:9, function(r) data.table(
  rank = r,
  designee_pre = mean(sample[treated == 1L, pre] == r), designee_post = mean(sample[treated == 1L, post] == r),
  losers_pre = mean(sample[treated == 0L, pre] == r), losers_post = mean(sample[treated == 0L, post] == r))))
fwrite(dist, file.path(out_dir, "nonlinear_distributions.csv"))
cat("\nRank distributions (shares): designee's followers pre/post, losers' followers pre/post\n")
print(dist[, lapply(.SD, function(x) if (is.numeric(x)) round(x, 3) else x)])

# ------------------------------------------------------------------ macros
mac <- c("% nonlinear_macros.tex (nonlinear_did.R). Do not edit by hand.",
         sprintf("\\newcommand{\\NLpoissonATT}{%s}", formatC(obs["att"], format = "f", digits = 2)),
         sprintf("\\newcommand{\\NLpoissonLo}{%s}", formatC(pois[statistic == "att", ci_lower], format = "f", digits = 2)),
         sprintf("\\newcommand{\\NLpoissonHi}{%s}", formatC(pois[statistic == "att", ci_upper], format = "f", digits = 2)),
         sprintf("\\newcommand{\\NLpoissonRatio}{%s}", formatC(obs["ratio"], format = "f", digits = 2)),
         sprintf("\\newcommand{\\NLlinearDelta}{%s}", formatC(thr[column == "delta", estimate], format = "f", digits = 2)))
writeLines(mac, file.path(tab_dir, "nonlinear_macros.tex"))
cat("\ndone\n")

# ------------------------------------------------------------------ figure: the premium along the ladder
tf <- thr[!is.na(rung)]
tf[, `:=`(est = 100 * estimate, lo = 100 * ci_lower, hi = 100 * ci_upper, lo90 = 100 * ci90_lower, hi90 = 100 * ci90_upper)]
labs_r <- c("1" = "any post", "2" = "mayor,\nadviser", "3" = "dept.\nhead", "4" = "area\ndirector", "5" = "deputy\nDG", "6" = "director\ngeneral",
            "7" = "under-\nsecretary", "8" = "major\ngovernor", "9" = "cabinet")
tf[, lab := paste0(rung, "\n", labs_r[as.character(rung)])]
p <- ggplot(tf, aes(x = rung, y = est)) +
  geom_hline(yintercept = 0, colour = "#a1a1aa", linewidth = 0.4) +
  geom_linerange(aes(ymin = lo, ymax = hi), colour = "#18181b", linewidth = 0.5) +
  geom_linerange(aes(ymin = lo90, ymax = hi90), colour = "#18181b", linewidth = 1.4) +
  geom_point(colour = "#940034", size = 2.6) +
  scale_x_continuous(breaks = tf$rung, labels = tf$lab) +
  labs(x = "Rung r of the office ladder (outcome: holds a post at rung r or above)",
       y = "Designee's minus losers' followers,\nchange in the share at rung r or above (pp)") +
  theme_classic(base_size = 13) +
  theme(axis.text.x = element_text(size = 9, lineheight = 0.9), axis.line = element_line(colour = "#a1a1aa", linewidth = 0.35),
        axis.ticks = element_line(colour = "#a1a1aa", linewidth = 0.35), plot.background = element_rect(fill = "white", colour = NA))
ggsave(file.path(out_dir, "nonlinear_threshold.pdf"), p, width = 9, height = 4.2)
ggsave(file.path(out_dir, "nonlinear_threshold.png"), p, width = 9, height = 4.2, dpi = 200)
cat("figure saved\n")
