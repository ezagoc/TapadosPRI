# Does the linear treatment of an ordinal outcome drive the main result? (seminar comment, 3 November 2026)
# Three checks on the main sample (designee's vs losing contenders' followers, within succession, covariates of the
# main design, the main estimand's succession weights):
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
S[, w := if (succession_weights == "equal") 1 / grp_n else 1]   # equal: each succession-group the same total weight; person: each follower
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
# symmetric intervals around the estimate from the bootstrap s.e. (percentile bounds kept as q025/q975)
pois <- data.table(statistic = names(obs), estimate = obs, se_boot = apply(boot, 2, sd, na.rm = TRUE),
                   q025 = apply(boot, 2, quantile, 0.025, na.rm = TRUE), q975 = apply(boot, 2, quantile, 0.975, na.rm = TRUE))
pois[, `:=`(ci_lower = estimate - qnorm(.975) * se_boot, ci_upper = estimate + qnorm(.975) * se_boot)]
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

# ------------------------------------------------------------------ 4. Poisson event study (exponential-mean ETWFE)
# Yearly ranks k = -7..8 around the election (0 if no post), reference year e-2 as in event_study.R. Mean
# exp(succession x year + covariates x year + treated + treated x year); the yearly effect on the original scale is the
# average over the designee's followers of exp(.) with and without the treated x year term. Equal weight per
# succession-group; cluster bootstrap by contender group.
suppressPackageStartupMessages(library(fixest))
ks <- -7:8; ref_k <- -2L
yr <- function(k) { z <- annual[data.table(pid = sample$pid, year = sample$election + k), on = .(pid, year), rank]; z[is.na(z)] <- 0L; z }
Yk <- sapply(ks, yr); colnames(Yk) <- ks
S <- copy(sample); S[, grp_n := .N, by = .(election, treated)]; S[, w := if (succession_weights == "equal") 1 / grp_n else 1]
long_k <- rbindlist(lapply(seq_along(ks), function(j) S[, .(pid, election, network, treated, w, pre_band, earlier_band, age, ldeg, lrec, prior_status,
                                                            k = ks[j], y = Yk[, j])]))
long_k[, kf := relevel(factor(k), ref = as.character(ref_k))]
long_k[, election_factor := factor(election, levels = elections)]
f_es <- y ~ treated + treated:kf + (pre_band + earlier_band + age + ldeg + lrec + prior_status) * kf | election_factor^kf
es_att <- function(dat) {
  m <- fepois(f_es, data = dat, weights = ~w, notes = FALSE, warn = FALSE)
  cf <- coef(m); tau_names <- grep("^treated:kf", names(cf), value = TRUE)
  tr <- dat[treated == 1L]
  eta1 <- predict(m, newdata = tr, type = "link")
  tau_k <- setNames(rep(0, length(ks)), ks); for (nm in tau_names) tau_k[sub("^treated:kf", "", nm)] <- cf[nm]
  eta0 <- eta1 - tau_k[as.character(tr$k)]
  tr[, `:=`(m1 = exp(eta1), m0 = exp(eta0))]
  tr[, .(att = weighted.mean(m1 - m0, w)), by = k][order(k), att]
}
obs_es <- es_att(long_k)
set.seed(seed)
Bes <- 300L
nets <- unique(long_k[, .(election, network)])
boot_es <- t(replicate(Bes, {
  draw <- nets[, .SD[sample(.N, .N, replace = TRUE)], by = election]
  draw[, rep := seq_len(.N), by = .(election, network)]
  dd <- merge(long_k, draw, by = c("election", "network"), allow.cartesian = TRUE)
  tryCatch(es_att(dd), error = function(e) rep(NA_real_, length(ks)))
}))
pes <- data.table(k = ks, att = obs_es, se_boot = apply(boot_es, 2, sd, na.rm = TRUE),
                  q025 = apply(boot_es, 2, quantile, 0.025, na.rm = TRUE), q975 = apply(boot_es, 2, quantile, 0.975, na.rm = TRUE))
pes[, `:=`(ci_lower = att - qnorm(.975) * se_boot, ci_upper = att + qnorm(.975) * se_boot,
           ci90_lower = att - qnorm(.95) * se_boot, ci90_upper = att + qnorm(.95) * se_boot)]   # symmetric, bootstrap s.e.
pes[k == ref_k, `:=`(att = 0, se_boot = 0, ci_lower = 0, ci_upper = 0, ci90_lower = 0, ci90_upper = 0)]
fwrite(pes, file.path(out_dir, "nonlinear_poisson_es.csv"))
lin <- fread(file.path(out_dir, "event_study.csv"))[outcome == "rank"]
cmp <- merge(lin[, .(k, linear = estimate, lin_lo = ci_lower, lin_hi = ci_upper)], pes[, .(k, poisson = att, poi_lo = ci_lower, poi_hi = ci_upper)], by = "k")
cat("\nEvent study, linear (main) vs Poisson ATT by year:\n"); print(cmp[, lapply(.SD, round, 2)])
avg14 <- c(linear = mean(cmp[k %in% 1:4, linear]), poisson = mean(cmp[k %in% 1:4, poisson]))
cat("\nYears 1-4 average: linear", round(avg14["linear"], 3), " Poisson", round(avg14["poisson"], 3), "\n")
# figure: both series
plot_d <- rbind(cmp[, .(k, est = linear, lo = lin_lo, hi = lin_hi, series = "Linear DiD (main)")],
                cmp[, .(k, est = poisson, lo = poi_lo, hi = poi_hi, series = "Poisson QMLE")])
plot_d[, kx := k + ifelse(series == "Poisson QMLE", 0.18, -0.18)]
p2 <- ggplot(plot_d, aes(x = kx, y = est, colour = series, shape = series)) +
  geom_hline(yintercept = 0, colour = "#a1a1aa", linewidth = 0.4) +
  geom_vline(xintercept = c(-1.5, 0.5, 6.5), colour = "#d4d4d8", linetype = "dashed", linewidth = 0.4) +
  geom_linerange(aes(ymin = lo, ymax = hi), linewidth = 0.5) + geom_point(size = 2.2, fill = "white") +
  scale_colour_manual(values = c("Linear DiD (main)" = "#18181b", "Poisson QMLE" = "#940034")) +
  scale_shape_manual(values = c("Linear DiD (main)" = 16, "Poisson QMLE" = 21)) +
  scale_x_continuous(breaks = ks) +
  annotate("text", x = c(-1.6, 0.6, 6.6), y = max(plot_d$hi, na.rm = TRUE), label = c("Designation", "New president", "Next president"),
           hjust = 0, vjust = 1, size = 3, colour = "#71717a") +
  labs(x = "Years relative to the election", y = "Designee's minus losers' followers,\nrank positions (95% intervals)", colour = NULL, shape = NULL) +
  theme_classic(base_size = 13) + theme(legend.position = c(0.15, 0.9), axis.line = element_line(colour = "#a1a1aa", linewidth = 0.35),
                                        plot.background = element_rect(fill = "white", colour = NA))
ggsave(file.path(out_dir, "nonlinear_es.pdf"), p2, width = 9, height = 4.2)
ggsave(file.path(out_dir, "nonlinear_es.png"), p2, width = 9, height = 4.2, dpi = 200)
mac2 <- c(sprintf("\\newcommand{\\NLpoissonAnnual}{%s}", formatC(avg14["poisson"], format = "f", digits = 2)),
          sprintf("\\newcommand{\\NLlinearAnnual}{%s}", formatC(avg14["linear"], format = "f", digits = 2)))
cat(mac2, file = file.path(tab_dir, "nonlinear_macros.tex"), sep = "\n", append = TRUE)
cat("event-study figure saved\n")

# ------------------------------------------------------------------ 5. Poisson reward and penalty event study
# The section-11 decomposition with the exponential mean: designee's followers (D) and losing contenders' followers (P)
# against the same entropy-reweighted unaligned politicians (N; rp_setup.R, event-study balancing set), yearly ranks
# k = -7..8, reference e-2. Mean exp(succession x year + covariates x year + D + D x year + P + P x year); the unaligned
# carry their balancing weights, followers weight 1 (person weights). reward_k = average over D at year k of exp(eta) -
# exp(eta - tau^D_k); penalty_k likewise over P (signed). Cluster bootstrap over contender groups and unaligned
# politicians, resampled within succession; symmetric intervals from the bootstrap s.e.
invisible(capture.output(source(file.path(script_dir, "rp_setup.R"))))
S_es <- make_weights(A[support == TRUE], bal_formula_es)
YS <- YA[A$support == TRUE, , drop = FALSE]
S_es[, wgt := fifelse(group == "N", w, 1)]
if (succession_weights == "equal") { S_es[, grp_n := .N, by = .(election, group)]; S_es[group != "N", wgt := 1 / grp_n] }
S_es[, `:=`(isD = as.integer(group == "D"), isP = as.integer(group == "P"))]
long_rp <- rbindlist(lapply(seq_along(ks), function(j) S_es[, .(pid, election, cluster, group, isD, isP, wgt, age, ldeg, lrec, prior_status, fed_exec,
                                                                k = ks[j], y = YS[, j])]))
long_rp[, kf := relevel(factor(k), ref = as.character(ref_k))]
long_rp[, election_factor := factor(election, levels = elections)]
f_rp <- y ~ isD + isP + isD:kf + isP:kf + (age + ldeg + lrec + prior_status + fed_exec) * kf | election_factor^kf
rp_att <- function(dat) {
  m <- fepois(f_rp, data = dat, weights = ~wgt, notes = FALSE, warn = FALSE)
  cf <- coef(m); out <- list()
  for (G in c("D", "P")) {
    nm <- grep(paste0("^is", G, ":kf"), names(cf), value = TRUE)
    tau_k <- setNames(rep(0, length(ks)), ks); for (n in nm) tau_k[sub(paste0("^is", G, ":kf"), "", n)] <- cf[n]
    tr <- dat[group == G]
    eta1 <- predict(m, newdata = tr, type = "link"); eta0 <- eta1 - tau_k[as.character(tr$k)]
    tr[, `:=`(m1 = exp(eta1), m0 = exp(eta0))]
    out[[G]] <- tr[, .(att = weighted.mean(m1 - m0, wgt)), by = k][order(k), att]
  }
  c(out$D, out$P)
}
obs_rp <- rp_att(long_rp)
set.seed(seed)
cl_rp <- unique(long_rp[, .(election, cluster)])
Brp <- 300L
boot_rp <- t(replicate(Brp, {
  draw <- cl_rp[, .SD[sample(.N, .N, replace = TRUE)], by = election]
  draw[, rep := seq_len(.N), by = .(election, cluster)]
  dd <- merge(long_rp, draw, by = c("election", "cluster"), allow.cartesian = TRUE)
  tryCatch(rp_att(dd), error = function(e) rep(NA_real_, 2 * length(ks)))
}))
prp <- data.table(group = rep(c("D", "P"), each = length(ks)), k = rep(ks, 2), estimate = obs_rp, se_boot = apply(boot_rp, 2, sd, na.rm = TRUE))
prp[, `:=`(ci_lower = estimate - qnorm(.975) * se_boot, ci_upper = estimate + qnorm(.975) * se_boot,
           ci90_lower = estimate - qnorm(.95) * se_boot, ci90_upper = estimate + qnorm(.95) * se_boot)]
prp[k == ref_k, `:=`(estimate = 0, se_boot = 0, ci_lower = 0, ci_upper = 0, ci90_lower = 0, ci90_upper = 0)]
fwrite(prp, file.path(out_dir, "nonlinear_poisson_rp_es.csv"))
lin_rp <- fread(file.path(out_dir, "rp_event_study.csv"))
cmp_rp <- merge(prp[, .(group, k, poisson = estimate)], lin_rp[, .(group, k, linear = estimate)], by = c("group", "k"), all.x = TRUE)
cat("\nPoisson reward (D) and penalty (P) event study vs linear:\n")
print(dcast(cmp_rp, k ~ group, value.var = c("poisson", "linear"))[, lapply(.SD, round, 2)])
r14 <- prp[k %in% 1:4, .(att = mean(estimate)), by = group]; rew <- r14[group == "D", att]; pen <- r14[group == "P", att]
cat(sprintf("years 1-4: reward %.3f, penalty %.3f, difference %.3f, reward share %.0f%%\n", rew, pen, rew - pen, 100 * rew / (rew - pen)))
pd_rp <- copy(prp)
pd_rp[, grp := factor(fifelse(group == "D", "Designee's followers", "Losers' followers"), levels = c("Designee's followers", "Losers' followers"))]
pd_rp[, kx := k + fifelse(group == "D", -0.15, 0.15)]
p3 <- ggplot(pd_rp, aes(x = kx, y = estimate, colour = grp, shape = grp)) +
  geom_hline(yintercept = 0, colour = "#a1a1aa", linewidth = 0.4) +
  geom_vline(xintercept = c(-1.5, 0.5, 6.5), colour = "#d4d4d8", linetype = "dashed", linewidth = 0.4) +
  geom_linerange(aes(ymin = ci_lower, ymax = ci_upper), linewidth = 0.5) +
  geom_linerange(aes(ymin = ci90_lower, ymax = ci90_upper), linewidth = 1.3) +
  geom_point(size = 2.3, fill = "white") +
  scale_colour_manual(values = c("Designee's followers" = "#18181b", "Losers' followers" = "#7a7a7a")) +
  scale_shape_manual(values = c("Designee's followers" = 16, "Losers' followers" = 21)) +
  scale_x_continuous(breaks = ks) +
  annotate("text", x = c(-1.6, 0.6, 6.6), y = max(pd_rp$ci_upper), label = c("Designation", "New president", "Next president"),
           hjust = 0, vjust = 1, size = 3, colour = "#71717a") +
  labs(x = "Years relative to the election", y = "Effect on rank position,\neach group minus the reweighted unaligned", colour = NULL, shape = NULL) +
  theme_classic(base_size = 13) + theme(legend.position = c(0.15, 0.9), axis.line = element_line(colour = "#a1a1aa", linewidth = 0.35),
                                        plot.background = element_rect(fill = "white", colour = NA))
ggsave(file.path(out_dir, "nonlinear_rp_es.pdf"), p3, width = 9, height = 4.2)
ggsave(file.path(out_dir, "nonlinear_rp_es.png"), p3, width = 9, height = 4.2, dpi = 200)
mac3 <- c(sprintf("\\newcommand{\\NLrpReward}{%s}", formatC(rew, format = "f", digits = 2)),
          sprintf("\\newcommand{\\NLrpPenaltyAbs}{%s}", formatC(abs(pen), format = "f", digits = 2)),
          sprintf("\\newcommand{\\NLrpShare}{%s}", formatC(100 * rew / (rew - pen), format = "f", digits = 0)),
          sprintf("\\newcommand{\\NLrpDiff}{%s}", formatC(rew - pen, format = "f", digits = 2)))
cat(mac3, file = file.path(tab_dir, "nonlinear_macros.tex"), sep = "\n", append = TRUE)
cat("reward-penalty Poisson figure saved\n")

# ------------------------------------------------------------------ 6. the Poisson event study alone, house style
# Same figure function, geometry and labels as the main (linear) event-study figure, so the two can be compared one
# against the other: output/main_direct_tie/poisson_alone/es_rank.{pdf,png}.
dir.create(file.path(out_dir, "poisson_alone"), showWarnings = FALSE)
es_figure(pes[, .(k, estimate = att, ci_lower, ci_upper, ci90_lower, ci90_upper)],
          "Effect on rank position,\ndesignee's minus losers' followers", "es_rank", out = file.path(out_dir, "poisson_alone"))
cat("Poisson event study alone saved (poisson_alone/es_rank)\n")
