# Placebo tests of the main window contrast (MAIN_SPEC section 4), 20 October 2026. The sample, the treatment
# (exclusive direct tie by e-2) and the covariates stay fixed; only the event year or the designee label moves.
#
# 1. Timing placebo. For every shift s in -8..8 the pseudo-event year is e' = e + s and the outcome is the
#    section-2 window change around e': max annual rung over e'+1..e'+4 minus max over e'-5..e'-2 (0 if no post
#    in a window, as estimate_main.R computes pre and post). The section-4 contrast is estimated for each s with
#    the event-study covariates (formula_es: succession, age, log degree, log records, prior status) and equal
#    succession weights. The baseline and earlier rank bands are NOT used: they are functions of the TRUE pre
#    window e-5..e-2 (and e-9..e-6), so for a shifted window they would be post-treatment or would absorb the
#    shifted outcome mechanically. One joint Ferman-Pinto bootstrap over all shifts (shared draws). Shifts with
#    |s| <= 3 have a post window overlapping the true one; s <= -6 are pure pre-designation placebos (both
#    windows end by e-2); s >= 6 have both windows after the election, the post window under the next president.
#
# 2. Designee placebo (randomization test of the slate). In each succession each losing contender with exclusive
#    followers is relabelled designee in turn; his followers become the treated group and every other exclusive
#    follower of the slate (the true designee's included) the comparison group; the section-4 contrast with the
#    main covariates (formula_x) is recomputed. The estimator is linear, so each (succession, pseudo-designee)
#    pair needs one build_design call; the pooled estimate of a combination of one pseudo-designee per succession
#    is the mean of the nine chosen contrasts. Approximation, stated here: in each call the common slopes of the
#    loser-only outcome model are fitted on the relabelled succession together with the other eight successions
#    under their actual labels, so the pooled estimate of a combination is the mean of nine such contrasts
#    rather than a joint refit on the nine relabelled control sets. For the actual labels it is exactly the
#    main estimate. The product of slate sizes exceeds 200,000, so 20,000 combinations are drawn at random
#    (seed 20102026) for the primary p-values; the exact distribution over every combination is cheap to
#    enumerate (iterated outer sums) and is reported as a cross-check.
#
# Run from the repo root: Rscript code/04-analysis/main_direct_tie/placebos.R
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
invisible(capture.output(source(file.path(script_dir, "estimate_main.R"))))
source(file.path(script_dir, "design_tools.R"))
tab_dir <- file.path(out_dir, "tables"); dir.create(tab_dir, showWarnings = FALSE)
seed_placebo <- 20102026L
B_placebo <- 20000L
main_estimate <- theta   # section-4 estimate with formula_x (1.03)

# ================================================================== 1. timing placebo
shifts <- -8:8
ks <- (min(shifts) - 5L):(max(shifts) + 4L)
Yk <- sapply(ks, function(k) year_value(annual, k)); colnames(Yk) <- ks
window_max <- function(k_from, k_to) do.call(pmax, as.data.frame(Yk[, as.character(k_from:k_to), drop = FALSE]))
Delta <- sapply(shifts, function(s) window_max(s + 1L, s + 4L) - window_max(s - 5L, s - 2L))
colnames(Delta) <- shifts
stopifnot(all(Delta[, "0"] == sample$delta))   # s = 0 reproduces the main outcome

d_es <- build_design(formula = formula_es)
stopifnot(identical(d_es$rows, seq_len(nrow(sample))))
tim <- estimate_columns(d_es, Delta[d_es$rows, , drop = FALSE], B = B_placebo, seed = seed_placebo)
timing <- tim$table[, .(s = as.integer(column), estimate, ci_lower, ci_upper, ci90_lower, ci90_upper, p_bootstrap, n,
                        n_designee)]
timing[, `:=`(overlap_post_window = abs(s) <= 3L, pre_designation_only = s <= -6L, next_president = s >= 6L,
              pre_window = sprintf("e%+d..e%+d", s - 5L, s - 2L), post_window = sprintf("e%+d..e%+d", s + 1L, s + 4L))]
setorder(timing, s)
stopifnot(abs(timing[s == 0L, estimate] - main_estimate) < 0.5)   # formula_es estimate (1.19) is near the main one

# Joint test that every pre-designation shift (s <= -6) is zero: max |t| against its bootstrap distribution, as
# event_study.R does for the leads.
pre_names <- as.character(shifts[shifts <= -6L])
s_sd <- apply(tim$err[pre_names, , drop = FALSE], 1L, sd)
pre_stat <- max(abs(timing[s <= -6L, estimate]) / s_sd)
pre_draws <- apply(abs(tim$err[pre_names, , drop = FALSE]) / s_sd, 2L, max)
pre_joint_p <- mean(pre_draws >= pre_stat)
pre_max_abs <- max(abs(timing[s <= -6L, estimate]))
timing_summary <- data.table(contrast = c("joint_pre_designation_test_max_t", "largest_abs_pre_designation_estimate",
                                          "main_window_event_study_covariates", "main_estimate_section_4"),
                             estimate = c(pre_stat, pre_max_abs, timing[s == 0L, estimate], main_estimate),
                             p_bootstrap = c(pre_joint_p, NA, timing[s == 0L, p_bootstrap], p),
                             shifts = c(paste(pre_names, collapse = " "), paste(pre_names, collapse = " "), "0", "0"))
fwrite(timing[, .(s, estimate, ci_lower, ci_upper, ci90_lower, ci90_upper, p_bootstrap, overlap_post_window,
                  pre_designation_only, n, next_president, n_designee, pre_window, post_window)],
       file.path(out_dir, "placebo_timing.csv"))
fwrite(timing_summary, file.path(out_dir, "placebo_timing_summary.csv"))

# Figure: house style of design_tools.R.
tp <- copy(timing)
top <- max(tp$ci_upper); bot <- min(tp$ci_lower); span <- top - bot
base <- 17
labs_dt <- data.table(x = c(-8, -3.4, 3.6), lab = c("Both windows end by e−2", "Post window overlaps e+1..e+4",
                                                   "Post window under the next president"),
                      hjust = c(0, 0, 0))
g_t <- ggplot(tp, aes(s, estimate)) +
  annotate("rect", xmin = -3.5, xmax = 3.5, ymin = -Inf, ymax = Inf, fill = "grey93") +
  geom_hline(yintercept = 0, colour = RULE, linewidth = 0.35) +
  geom_vline(xintercept = 0, colour = RULE, linewidth = 0.35, linetype = "dashed") +
  geom_text(data = labs_dt, aes(x = x, y = top + 0.10 * span, label = lab, hjust = hjust), vjust = 0,
            colour = MUTED, size = base * 0.25, family = FAM) +
  geom_linerange(aes(ymin = ci_lower, ymax = ci_upper), colour = INK, linewidth = 0.45) +
  geom_linerange(aes(ymin = ci90_lower, ymax = ci90_upper), colour = INK, linewidth = 1.5) +
  geom_point(data = tp[s != 0L], shape = 21, fill = "white", colour = INK, size = 2.4, stroke = 0.7) +
  geom_point(data = tp[s == 0L], colour = INK, size = 2.6) +
  scale_x_continuous(breaks = shifts, labels = k_numbers) +
  coord_cartesian(ylim = c(bot - 0.03 * span, top + 0.20 * span), clip = "off") +
  labs(x = expression("Pseudo-event year relative to the election, " * italic(s)),
       y = "Effect on the change\nin highest rank position") +
  theme_paper(base) + theme(axis.title.y = element_text(size = 14, lineheight = 0.95))
ggsave(file.path(out_dir, "placebo_timing.pdf"), g_t, width = 10, height = 4.1, bg = "white", device = "pdf")
ggsave(file.path(out_dir, "placebo_timing.png"), g_t, width = 10, height = 4.1, dpi = 250, bg = "white")

# ================================================================== 2. designee placebo
slate_tab <- rbindlist(lapply(names(slates), function(e) {
  sl <- slates[[e]]
  data.table(election = as.integer(e), person_id = sl$candidates, is_designee = as.integer(sl$candidates == sl$winner))
}))
name_of <- unique(contenders[, .(person_id, person_name)])
slate_tab[, person_name := name_of$person_name[match(person_id, name_of$person_id)]]
followers <- sample[, .(n_followers = .N), by = .(election, person_id = patron)]
slate_tab <- merge(slate_tab, followers, by = c("election", "person_id"), all.x = TRUE)
slate_tab[is.na(n_followers), n_followers := 0L]
setorder(slate_tab, election, -is_designee, -n_followers, person_id)

# One build_design per (succession, pseudo-designee): relabel the succession, take its contrast.
actual_treated <- copy(sample$treated)
contrast_for <- function(e, c) {
  sample[, treated := actual_treated]
  sample[election == e, treated := as.integer(patron == c)]
  on.exit(sample[, treated := actual_treated], add = TRUE)
  d <- build_design(formula = formula_x)
  stopifnot(identical(d$elections, elections))
  by_succession_d(d, sample$delta[d$rows])[election == e, estimate]
}
slate_tab[, contrast := NA_real_]
for (i in seq_len(nrow(slate_tab))) {
  if (slate_tab$n_followers[i] == 0L) next   # no treated group: cannot be labelled designee
  slate_tab[i, contrast := contrast_for(slate_tab$election[i], slate_tab$person_id[i])]
}
stopifnot(identical(sample$treated, actual_treated))
# The actual designees' contrasts reproduce the section-4 succession contrasts.
chk <- merge(slate_tab[is_designee == 1L], components[, .(election, relative_premium)], by = "election")
stopifnot(max(abs(chk$contrast - chk$relative_premium)) < 1e-8,
          abs(sum(omega[as.character(chk$election)] * chk$contrast) - main_estimate) < 1e-8)
slate_tab[!is.na(contrast), rank_in_slate := frank(-contrast, ties.method = "min"), by = election]
slate_tab[, above_main_estimate := !is.na(contrast) & contrast > main_estimate]
fwrite(slate_tab[, .(election, person_id, person_name, is_designee, n_followers, contrast, rank_in_slate,
                     above_main_estimate)], file.path(out_dir, "placebo_designee.csv"))

# Combinations of one pseudo-designee per succession (contenders with followers only).
by_e <- split(slate_tab[n_followers > 0L], by = "election", keep.by = TRUE)
slate_sizes <- sapply(by_e, nrow)
n_total <- prod(slate_sizes)
enumerate <- n_total <= 200000
set.seed(seed_placebo)
if (enumerate) {
  grid <- as.matrix(do.call(expand.grid, lapply(slate_sizes, seq_len)))
} else {
  grid <- sapply(slate_sizes, function(m) sample.int(m, B_placebo, replace = TRUE))
}
# Pooled statistic of a combination: the main estimand's succession weights applied to the relabelled groups (person: each
# pseudo-designee's followers' share of the combination's followers; equal: 1/9); for the actual labels, the main estimate.
cm <- sapply(seq_along(by_e), function(j) by_e[[j]]$contrast[grid[, j]])
nm <- sapply(seq_along(by_e), function(j) if (succession_weights == "equal") rep(1, nrow(grid)) else by_e[[j]]$n_followers[grid[, j]])
pooled <- rowSums(cm * nm) / rowSums(nm)
tol <- 1e-9
p_one <- mean(pooled >= main_estimate - tol)
p_two <- mean(abs(pooled) >= abs(main_estimate) - tol)
# Exact distribution over every combination: iterated outer sums of the nine contrast vectors.
num <- 0; den <- 0
for (j in seq_along(by_e)) {
  nj <- if (succession_weights == "equal") rep(1, nrow(by_e[[j]])) else by_e[[j]]$n_followers
  num <- as.vector(outer(num, nj * by_e[[j]]$contrast, "+")); den <- as.vector(outer(den, nj, "+"))
}
pooled_exact <- num / den; rm(num, den)
stopifnot(length(pooled_exact) == n_total)
p_one_exact <- mean(pooled_exact >= main_estimate - tol)
p_two_exact <- mean(abs(pooled_exact) >= abs(main_estimate) - tol)

n_above <- sum(slate_tab$above_main_estimate)
n_rank_first <- sum(slate_tab[is_designee == 1L, rank_in_slate] == 1L)
designee_summary <- data.table(
  p_one_sided = p_one, p_two_sided = p_two, n_combinations = nrow(grid), enumerated = enumerate,
  p_one_sided_exact = p_one_exact, p_two_sided_exact = p_two_exact, n_combinations_total = n_total,
  actual_estimate = main_estimate, mean_pooled = mean(pooled), sd_pooled = sd(pooled),
  n_contenders = nrow(slate_tab), n_contenders_evaluated = sum(!is.na(slate_tab$contrast)),
  n_contenders_above_main = n_above, n_designees_ranked_first = n_rank_first, seed = seed_placebo)
fwrite(designee_summary, file.path(out_dir, "placebo_designee_summary.csv"))

# Figure: histogram of the pooled estimates over the sampled combinations, the actual estimate as a rule.
hd <- data.table(estimate = pooled)
g_d <- ggplot(hd, aes(estimate)) +
  geom_histogram(bins = 60, fill = "grey78", colour = "white", linewidth = 0.2) +
  geom_vline(xintercept = main_estimate, colour = INK, linewidth = 0.6) +
  annotate("text", x = main_estimate - 0.04, y = Inf, vjust = 1.4, hjust = 1, colour = INK, family = FAM, size = base * 0.27,
           label = sprintf("Actual designees: %.2f\nshare of combinations at or above: %.4f", main_estimate, p_one)) +
  scale_y_continuous(expand = expansion(mult = c(0, 0.05)), labels = function(x) format(x, big.mark = ",")) +
  labs(x = "Pooled estimate with one pseudo-designee per succession (rank positions)",
       y = sprintf("Combinations (of %s)", format(nrow(grid), big.mark = ","))) +
  theme_paper(base) + theme(axis.title.y = element_text(size = 14, lineheight = 0.95))
ggsave(file.path(out_dir, "placebo_designee.pdf"), g_d, width = 10, height = 4.1, bg = "white", device = "pdf")
ggsave(file.path(out_dir, "placebo_designee.png"), g_d, width = 10, height = 4.1, dpi = 250, bg = "white")

# ================================================================== 3. macros
f2 <- function(x, d = 2) { r <- round(x, d); s <- formatC(r, format = "f", digits = d); s[r == 0] <- formatC(0, format = "f", digits = d); sub("^-", "$-$", s) }
pv <- function(p, d = 2) if (p < 10^-d) paste0("$<$", formatC(10^-d, format = "f", digits = d)) else f2(p, d)
mac <- function(name, value) sprintf("\\newcommand{\\%s}{%s}", name, value)
trio <- function(tag, s0) c(mac(paste0(tag, "Est"), f2(timing[s == s0, estimate])),
                            mac(paste0(tag, "Lo"), f2(timing[s == s0, ci_lower])),
                            mac(paste0(tag, "Hi"), f2(timing[s == s0, ci_upper])))
writeLines(c("% placebo_macros.tex (placebos.R): timing and designee placebos of the main contrast. Do not edit by hand.",
             trio("PLminusSix", -6L), trio("PLminusEight", -8L), trio("PLzero", 0L), trio("PLplusSix", 6L), trio("PLplusEight", 8L),
             mac("PLzeroP", pv(timing[s == 0L, p_bootstrap])), mac("PLplusSixP", pv(timing[s == 6L, p_bootstrap])),
             mac("PLplusEightP", pv(timing[s == 8L, p_bootstrap])),
             mac("PLpreMaxAbs", f2(pre_max_abs)), mac("PLpreJointP", pv(pre_joint_p)),
             mac("PDpOne", pv(p_one, 3)), mac("PDpTwo", pv(p_two, 3)),
             mac("PDnComb", format(nrow(grid), big.mark = ",")), mac("PDnAbove", n_above),
             mac("PDrankActual", n_rank_first)),
           file.path(tab_dir, "placebo_macros.tex"))

# ================================================================== console
cat("\nTiming placebo (event-study covariates, equal succession weights, B =", B_placebo, "):\n")
print(timing[, .(s, estimate = round(estimate, 3), ci_lower = round(ci_lower, 3), ci_upper = round(ci_upper, 3),
                 p = round(p_bootstrap, 3), overlap_post_window, pre_designation_only, next_president)])
cat(sprintf("Joint pre-designation test (s <= -6): max |t| = %.2f, bootstrap p = %.3f; largest |estimate| = %.3f\n",
            pre_stat, pre_joint_p, pre_max_abs))
cat("\nDesignee placebo: contrast of each slate contender if labelled designee\n")
print(slate_tab[, .(election, person_name, is_designee, n_followers, contrast = round(contrast, 3), rank_in_slate)])
cat(sprintf("\nCombinations: %s sampled of %s (enumerated: %s); one-sided p = %.4f, two-sided p = %.4f; exact over all: %.4f, %.4f\n",
            format(nrow(grid), big.mark = ","), format(n_total, big.mark = ","), enumerate, p_one, p_two, p_one_exact, p_two_exact))
cat(sprintf("Contenders with a contrast above %.2f if labelled designee: %d of %d evaluated (%d in the slates); designees ranked first: %d of %d\n",
            main_estimate, n_above, sum(!is.na(slate_tab$contrast)), nrow(slate_tab), n_rank_first, length(elections)))
cat("Wrote placebo_timing.{csv,pdf,png}, placebo_timing_summary.csv, placebo_designee.{csv,pdf,png}, placebo_designee_summary.csv, tables/placebo_macros.tex to", out_dir, "\n")
