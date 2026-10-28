# Randomization inference for the headline estimate, the event-study average of years 1-4 (MAIN_SPEC section 7),
# 27 October 2026. The designation is reassigned at random and the estimate recomputed, in two ways, after the
# randomization-based tests of Lin, Liu, Xu and Zhang (2023):
#
#  (a) Designee within the contender set. In each succession every contender with exclusive followers is
#      relabelled designee in turn: his followers become the treated group and every other exclusive follower
#      of the slate (the actual designee's included) the comparison group. The estimator is linear and the
#      pooled estimate is the equal average of the nine succession contrasts, so one build_design call per
#      (succession, pseudo-designee) gives every contrast, and the estimate of a combination of one
#      pseudo-designee per succession is the mean of the nine chosen contrasts. Same approximation as
#      placebos.R: the common slopes of the outcome model are fitted with the relabelled succession together
#      with the other eight under their actual labels. For the actual labels the statistic is exactly the
#      headline estimate. The distribution is enumerated over every combination (the product of the slate
#      sizes); it is the reference distribution that respects that a designation moves whole contender groups.
#
#  (b) Followers within the succession. The designee's label is given at random to as many followers as he
#      actually has, among all exclusive followers of the succession, and the estimator is refitted. This is the
#      usual permutation of individual labels; it ignores the contender groups, so its distribution is narrower.
#
# Test statistic: the years 1-4 average of the event study, i.e. the estimate on the outcome
# (Y_{e+1} + ... + Y_{e+4}) / 4 - Y_{e-2} with the event-study covariates (formula_es) and equal succession
# weights; the average of the four yearly estimates equals this because the estimator is linear in the outcome.
# Run from the repo root: Rscript code/04-analysis/main_direct_tie/randomization_inference.R
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
invisible(capture.output(source(file.path(script_dir, "estimate_main.R"))))
source(file.path(script_dir, "design_tools.R"))
tab_dir <- file.path(out_dir, "tables"); dir.create(tab_dir, showWarnings = FALSE)
seed_ri <- 27102026L
B_followers <- 5000L
max_enumerate <- 1e7

# ------------------------------------------------------------------ statistic
Yk <- sapply(c(-2L, 1:4), function(k) year_value(annual, k)); colnames(Yk) <- c(-2L, 1:4)
y_avg <- rowMeans(Yk[, as.character(1:4), drop = FALSE]) - Yk[, "-2"]
d_es <- build_design(formula = formula_es, weights = "equal")
stopifnot(identical(d_es$rows, seq_len(nrow(sample))), identical(d_es$elections, elections))
actual <- sum(d_es$a * y_avg)
headline <- fread(file.path(out_dir, "event_study_summary.csv"))[outcome == "rank" & contrast == "main_window_average", estimate]
cat(sprintf("Headline (event_study_summary.csv): %.6f; recomputed on the averaged outcome: %.6f\n", headline, actual))
stopifnot(abs(actual - headline) < 1e-6)
actual_by_e <- by_succession_d(d_es, y_avg)

# ------------------------------------------------------------------ (a) designee within the contender set
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

actual_treated <- copy(sample$treated)
contrast_for <- function(e, c) {
  sample[, treated := actual_treated]
  sample[election == e, treated := as.integer(patron == c)]
  on.exit(sample[, treated := actual_treated], add = TRUE)
  d <- build_design(formula = formula_es, weights = "equal")
  stopifnot(identical(d$elections, elections))
  by_succession_d(d, y_avg[d$rows])[election == e, estimate]
}
slate_tab[, contrast := NA_real_]
for (i in seq_len(nrow(slate_tab))) {
  if (slate_tab$n_followers[i] == 0L) next   # no treated group: cannot be labelled designee
  slate_tab[i, contrast := contrast_for(slate_tab$election[i], slate_tab$person_id[i])]
}
stopifnot(identical(sample$treated, actual_treated))
chk <- merge(slate_tab[is_designee == 1L], actual_by_e, by = "election")
stopifnot(max(abs(chk$contrast - chk$estimate)) < 1e-8, abs(mean(chk$contrast) - actual) < 1e-8)
slate_tab[!is.na(contrast), rank_in_slate := frank(-contrast, ties.method = "min"), by = election]
n_rank_first <- sum(slate_tab[is_designee == 1L, rank_in_slate] == 1L)   # slates where the actual designee's contrast is the largest
fwrite(slate_tab[, .(election, person_id, person_name, is_designee, n_followers, contrast, rank_in_slate)],
       file.path(out_dir, "randomization_designee_contrasts.csv"))

by_e <- split(slate_tab[n_followers > 0L], by = "election", keep.by = TRUE)
slate_sizes <- sapply(by_e, nrow)
n_total <- prod(slate_sizes)
enumerated <- n_total <= max_enumerate
set.seed(seed_ri)
if (enumerated) {
  sums <- 0
  for (j in seq_along(by_e)) sums <- as.vector(outer(sums, by_e[[j]]$contrast, "+"))
  pooled_a <- sums / length(by_e); rm(sums)
  stopifnot(length(pooled_a) == n_total)
} else {
  grid <- sapply(slate_sizes, function(m) sample.int(m, 20000L, replace = TRUE))
  pooled_a <- rowMeans(sapply(seq_along(by_e), function(j) by_e[[j]]$contrast[grid[, j]]))
}
tol <- 1e-9
p_a_one <- mean(pooled_a >= actual - tol)
p_a_two <- mean(abs(pooled_a) >= abs(actual) - tol)

# ------------------------------------------------------------------ (b) followers within the succession
n_treated <- sample[, .(nT = sum(treated)), by = election]
set.seed(seed_ri + 1L)
pooled_b <- numeric(B_followers)
for (b in seq_len(B_followers)) {
  sample[, treated := 0L]
  for (e in elections) {
    ix <- which(sample$election == e)
    nT_e <- n_treated$nT[n_treated$election == e]
    sample[ix[sample.int(length(ix), nT_e)], treated := 1L]
  }
  d <- build_design(formula = formula_es, weights = "equal")
  stopifnot(identical(d$elections, elections))
  pooled_b[b] <- sum(d$a * y_avg[d$rows])
}
sample[, treated := actual_treated]
stopifnot(identical(sample$treated, actual_treated))
p_b_one <- mean(pooled_b >= actual - tol)
p_b_two <- mean(abs(pooled_b) >= abs(actual) - tol)
fwrite(data.table(draw = seq_len(B_followers), estimate = pooled_b), file.path(out_dir, "randomization_followers.csv"))

ri_summary <- data.table(
  scheme = c("designee_within_slate", "followers_within_succession"),
  n_draws = c(length(pooled_a), B_followers), enumerated = c(enumerated, FALSE),
  n_combinations_total = c(n_total, NA), actual_estimate = actual,
  mean = c(mean(pooled_a), mean(pooled_b)), sd = c(sd(pooled_a), sd(pooled_b)),
  p_one_sided = c(p_a_one, p_b_one), p_two_sided = c(p_a_two, p_b_two),
  n_at_or_above = c(sum(pooled_a >= actual - tol), sum(pooled_b >= actual - tol)),
  n_designees_ranked_first = c(n_rank_first, NA), seed = seed_ri)
fwrite(ri_summary, file.path(out_dir, "randomization_inference_summary.csv"))

# ------------------------------------------------------------------ figure (house style)
fmt_n <- function(n) format(n, big.mark = ",")
schemes <- c("(a) Random designee per contender set", "(b) Random followers per succession")
binned <- function(x, scheme, bins = 50L) {
  br <- seq(min(x), max(x), length.out = bins + 1L)
  h <- hist(x, breaks = br, plot = FALSE, right = FALSE, include.lowest = TRUE)
  data.table(scheme = scheme, mid = h$mids, share = h$counts / sum(h$counts), width = diff(br)[1])
}
hd <- rbind(binned(pooled_a, schemes[1]), binned(pooled_b, schemes[2]))
hd[, scheme := factor(scheme, levels = schemes)]
ann <- data.table(scheme = factor(schemes, levels = schemes),
                  label = c(sprintf("Mean = %.2f\nStd. dev. = %.2f\nShare at or above: %.4f", mean(pooled_a), sd(pooled_a), p_a_one),
                            sprintf("Mean = %.2f\nStd. dev. = %.2f\nShare at or above: %.4f", mean(pooled_b), sd(pooled_b), p_b_one)))
base <- 17
g <- ggplot(hd, aes(mid, share)) +
  geom_col(aes(width = width), fill = "grey78", colour = "white", linewidth = 0.2) +
  geom_vline(xintercept = actual, colour = INK, linewidth = 0.6, linetype = "dashed") +
  geom_text(data = ann, aes(x = -Inf, y = Inf, label = label), hjust = -0.08, vjust = 1.25, colour = INK, family = FAM,
            size = base * 0.24, lineheight = 0.95) +
  annotate("text", x = actual, y = Inf, vjust = 1.4, hjust = 1.08, colour = INK, family = FAM, size = base * 0.24,
           label = sprintf("Actual designees: %.2f", actual)) +
  facet_wrap(~ scheme, scales = "free") +
  scale_y_continuous(expand = expansion(mult = c(0, 0.08))) +
  labs(x = "Estimate under the reassigned designation (rank positions)", y = "Share of reassignments") +
  theme_paper(base) + theme(strip.text = element_text(size = base - 3, hjust = 0), panel.spacing.x = unit(16, "pt"))
ggsave(file.path(out_dir, "randomization_inference.pdf"), g, width = 10, height = 3.5, bg = "white", device = "pdf")
ggsave(file.path(out_dir, "randomization_inference.png"), g, width = 10, height = 3.5, dpi = 250, bg = "white")

# ------------------------------------------------------------------ macros
f2 <- function(x, d = 2) { s <- formatC(round(x, d), format = "f", digits = d); sub("^-", "$-$", s) }
pv <- function(p, d = 3) if (p < 10^-d) paste0("$<$", formatC(10^-d, format = "f", digits = d)) else f2(p, d)
mac <- function(name, value) sprintf("\\newcommand{\\%s}{%s}", name, value)
writeLines(c("% randomization_macros.tex (randomization_inference.R): randomization inference for the years 1-4 average. Do not edit by hand.",
             mac("RIactual", f2(actual)), mac("RIaN", fmt_n(n_total)), mac("RIaMean", f2(mean(pooled_a))), mac("RIaSd", f2(sd(pooled_a))),
             mac("RIaPone", pv(p_a_one)), mac("RIaPtwo", pv(p_a_two)), mac("RIaAbove", fmt_n(sum(pooled_a >= actual - tol))),
             mac("RIaFirst", n_rank_first),
             mac("RIbN", fmt_n(B_followers)), mac("RIbMean", f2(mean(pooled_b))), mac("RIbSd", f2(sd(pooled_b))),
             mac("RIbPone", pv(p_b_one)), mac("RIbPtwo", pv(p_b_two))),
           file.path(tab_dir, "randomization_macros.tex"))

# ------------------------------------------------------------------ console
cat("\n(a) Contrast of each contender if labelled designee (years 1-4 average):\n")
print(slate_tab[, .(election, person_name, is_designee, n_followers, contrast = round(contrast, 3), rank_in_slate)])
cat(sprintf("\n(a) %s combinations (%s): mean %.3f, sd %.3f; one-sided p %.4f, two-sided %.4f; at or above: %d\n",
            fmt_n(length(pooled_a)), if (enumerated) "all" else "sampled", mean(pooled_a), sd(pooled_a), p_a_one, p_a_two,
            sum(pooled_a >= actual - tol)))
cat(sprintf("    actual designees with the largest contrast of their slate: %d of %d\n", n_rank_first, length(elections)))
cat(sprintf("(b) %s draws: mean %.3f, sd %.3f; one-sided p %.4f, two-sided %.4f; at or above: %d\n",
            fmt_n(B_followers), mean(pooled_b), sd(pooled_b), p_b_one, p_b_two, sum(pooled_b >= actual - tol)))
cat("Wrote randomization_designee_contrasts.csv, randomization_followers.csv, randomization_inference_summary.csv,",
    "randomization_inference.{pdf,png}, tables/randomization_macros.tex to", out_dir, "\n")
