# Appendix diagnostics (MAIN_SPEC section 10, 17 October 2026) and the LaTeX tables of the deck. Every number
# is computed here or read from the outputs of estimate_main.R, validate_inference.R, event_study.R,
# margins.R and budget_outcome.R (run those first). Writes CSVs and tables/*.tex to the output directory.
# Run from the repo root: Rscript code/04-analysis/main_direct_tie/appendix_diagnostics.R
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
invisible(capture.output(source(file.path(script_dir, "estimate_main.R"))))
source(file.path(script_dir, "design_tools.R"))
tab_dir <- file.path(out_dir, "tables"); dir.create(tab_dir, showWarnings = FALSE)
f2 <- function(x, d = 2) { r <- round(x, d); s <- formatC(r, format = "f", digits = d); s[r == 0] <- formatC(0, format = "f", digits = d); sub("^-", "$-$", s) }
ci_txt <- function(lo, hi, d = 2) paste0("[", f2(lo, d), ", ", f2(hi, d), "]")
write_tab <- function(lines, file) writeLines(lines, file.path(tab_dir, file))
designee_names <- c("1940" = "\\'Avila Camacho", "1946" = "Alem\\'an", "1952" = "Ruiz Cortines", "1958" = "L\\'opez Mateos",
                    "1964" = "D\\'iaz Ordaz", "1970" = "Echeverr\\'ia", "1976" = "L\\'opez Portillo", "1982" = "de la Madrid",
                    "1988" = "Salinas")

# ------------------------------------------------------------------ 1. balance of predetermined traits
pos_all <- fread(file.path(data_dir, "rank", "position_tiers.csv"), na.strings = c("", "NA"))
edu <- fread(file.path(data_dir, "education_wide.csv"))
elected_rules <- c("federal_deputy", "senator", "local_deputy", "governor_major_state", "governor_other_state",
                   "governor_state_unknown", "mayor", "mayor_big_city", "city_council", "df_assembly_or_delegate")
first_year <- function(rows) rows[!is.na(year_start), .(y = min(year_start)), by = person_id]
fe <- first_year(pos_all[rule %in% elected_rules]); fp <- first_year(pos_all[dataset == "party_positions"])
fm <- unique(pos_all[dataset == "military_positions", person_id])
bal <- copy(sample)
bal[, `:=`(n_posts = expm1(lrec), n_ties = expm1(ldeg), prev_designee = as.numeric(prior_status == "prev_winner"),
           born_df = as.numeric(nodes$birth_state[match(pid, nodes$person_id)] %in% "Federal District"),
           degree = as.numeric(edu$has_degree[match(pid, edu$person_id)] %in% 1),
           graduate = as.numeric((edu$masters[match(pid, edu$person_id)] %in% 1) | (edu$phd[match(pid, edu$person_id)] %in% 1)),
           law = as.numeric(edu$law[match(pid, edu$person_id)] %in% 1),
           economics = as.numeric(edu$economics[match(pid, edu$person_id)] %in% 1),
           elected = as.numeric(fe$y[match(pid, fe$person_id)] <= election - 2L),
           party = as.numeric(fp$y[match(pid, fp$person_id)] <= election - 2L),
           military = as.numeric(pid %in% fm))]
bal[is.na(elected), elected := 0]; bal[is.na(party), party := 0]
bal_vars <- list(
  list("age", "Age in the election year", "A"), list("pre", "Highest rung, $e-5$ to $e-2$", "A"),
  list("earlier", "Highest rung, $e-9$ to $e-6$ (0 if none)", "A"), list("n_posts", "Ranked posts by $e-2$", "A"),
  list("n_ties", "Dated ties by $e-2$", "A"), list("prev_designee", "Tied to the previous designee", "A"),
  list("born_df", "Born in Mexico City", "B"), list("degree", "University degree", "B"),
  list("graduate", "Graduate degree", "B"), list("law", "Law degree", "B"), list("economics", "Economics degree", "B"),
  list("elected", "Elected office by $e-2$", "B"), list("party", "Party post by $e-2$", "B"),
  list("military", "Military career", "B"))
d_fe <- build_design(formula = ~ election_factor)
Xb <- sapply(bal_vars, function(v) bal[[v[[1]]]]); colnames(Xb) <- sapply(bal_vars, `[[`, 1)
bt <- estimate_columns(d_fe, Xb)$table
bt[, `:=`(label = sapply(bal_vars, `[[`, 2), panel = sapply(bal_vars, `[[`, 3),
          mean_designee = colMeans(Xb[bal$treated == 1, ]), mean_losers = colMeans(Xb[bal$treated == 0, ]),
          sd_pooled = apply(Xb, 2, sd))]
bt[, std_diff := estimate / sd_pooled]
fwrite(bt, file.path(out_dir, "balance.csv"))
bl <- c("% balance.tex -- predetermined traits (appendix_diagnostics.R). Within-succession difference: equal-weight mean of",
        "% succession differences; p: Ferman-Pinto bootstrap at the contender level.",
        "\\begin{tabular}{lrrrrr}", "\\toprule",
        " & \\multicolumn{2}{c}{Mean} & \\multicolumn{2}{c}{Within-succession difference} & \\\\",
        "\\cmidrule(lr){2-3}\\cmidrule(lr){4-5}",
        " & Designee's & Losers' & Difference & Standardized & $p$ \\\\", " & followers & followers & & & \\\\", "\\midrule",
        "\\multicolumn{6}{l}{\\textit{A. In the outcome model}} \\\\")
for (pn in c("A", "B")) {
  if (pn == "B") bl <- c(bl, "\\addlinespace", "\\multicolumn{6}{l}{\\textit{B. Not in the outcome model}} \\\\")
  for (i in which(bt$panel == pn)) {
    dd <- if (bt$column[i] %in% c("age", "n_posts", "n_ties", "pre", "earlier")) 1 else 2
    bl <- c(bl, sprintf("%s & %s & %s & %s & %s & %s \\\\", bt$label[i], f2(bt$mean_designee[i], dd), f2(bt$mean_losers[i], dd),
                        f2(bt$estimate[i], dd), f2(bt$std_diff[i], 2), f2(bt$p_bootstrap[i], 2)))
  }
}
bl <- c(bl, "\\midrule", sprintf("Politicians & %s & %s & & & \\\\", format(sum(bal$treated), big.mark = ","),
                                   format(sum(bal$treated == 0), big.mark = ",")), "\\bottomrule", "\\end{tabular}")
write_tab(bl, "balance.tex")

# ------------------------------------------------------------------ 2. sample by succession (slide 7)
slates <- contenders[in_main_slate == 1L, .(slate_size = .N), by = .(election = election_year)]
sf <- merge(sample_flow, slates, by = "election")
largest <- network_info[treated == 0L, .(largest_loser = max(n)), by = election]
sf <- merge(sf, largest, by = "election")
fwrite(sf, file.path(out_dir, "sample_by_succession.csv"))
sl <- c("% sample.tex -- the sample by succession (appendix_diagnostics.R, main design of 16-17 October 2026)",
        "\\begin{tabular}{llrrrrrr}", "\\toprule",
        " & & & & \\multicolumn{3}{c}{Tied to exactly one contender} &  \\\\", "\\cmidrule(lr){5-7}",
        "Succession & Designee & Slate & Eligible & Designee's & Largest & All losing & Two or \\\\",
        " & & size & politicians & followers & loser's & followers & more \\\\", "\\midrule")
for (i in seq_len(nrow(sf))) sl <- c(sl, sprintf("%d & %s & %d & %s & %d & %d & %d & %d \\\\", sf$election[i],
  designee_names[[as.character(sf$election[i])]], sf$slate_size[i], format(sf$eligible[i], big.mark = ","),
  sf$winner_followers[i], sf$largest_loser[i], sf$loser_followers[i], sf$multiple_direct_ties[i]))
sl <- c(sl, "\\midrule", sprintf("Total & & %d & %s & %d & & %d & %d \\\\", sum(sf$slate_size), format(sum(sf$eligible), big.mark = ","),
                                 sum(sf$winner_followers), sum(sf$loser_followers), sum(sf$multiple_direct_ties)),
        "\\bottomrule", "\\end{tabular}")
write_tab(sl, "sample.tex")

# ------------------------------------------------------------------ 3. estimates by succession and leaving one out
bs <- merge(components[, .(election, n_winner, n_loser, relative_premium)],
            loo[, .(election = omitted_election, leave_out = relative_premium)], by = "election")
bs_lines <- c("% by_succession.tex (appendix_diagnostics.R)", "\\begin{tabular}{llrrrr}", "\\toprule",
              " & & \\multicolumn{2}{c}{Followers} & & Average of the \\\\", "\\cmidrule(lr){3-4}",
              "Succession & Designee & Designee's & Losers' & Estimate & other eight \\\\", "\\midrule")
for (i in seq_len(nrow(bs))) bs_lines <- c(bs_lines, sprintf("%d & %s & %d & %d & %s & %s \\\\", bs$election[i],
  designee_names[[as.character(bs$election[i])]], bs$n_winner[i], bs$n_loser[i], f2(bs$relative_premium[i]), f2(bs$leave_out[i])))
bs_lines <- c(bs_lines, "\\midrule", sprintf("Pooled & & %d & %d & %s & \\\\", sum(bs$n_winner), sum(bs$n_loser), f2(theta)),
              "\\bottomrule", "\\end{tabular}")
write_tab(bs_lines, "by_succession.tex")

# ------------------------------------------------------------------ 4. robustness of the main contrast
thr <- list(list(1L, "Holds any ranked post (rung 10 or above)"), list(6L, "Federal deputy or area director or above (rung 7)"),
            list(8L, "Director general or above (rung 5)"), list(9L, "Undersecretary or above (rung 4)"))
rob <- rbindlist(list(
  estimate_columns(build_design(), cbind(y = sample$delta))$table[, spec := "Main: equal succession weights, all covariates"],
  estimate_columns(build_design(weights = "person"), cbind(y = sample$delta))$table[, spec := "Successions weighted by designee's followers"],
  estimate_columns(build_design(formula = ~ election_factor), cbind(y = sample$delta))$table[, spec := "Succession indicators only"],
  estimate_columns(build_design(formula = formula_es), cbind(y = sample$delta))$table[, spec := "Without the baseline-rank bands"],
  estimate_columns(build_design(formula = ~ election_factor + factor(pmax(pre, 2L)) + earlier_band + age + ldeg + lrec + prior_status),
                   cbind(y = sample$delta))$table[, spec := "Exact baseline rung instead of bands"]))
# (exact rung: the 2 politicians at the lowest rung, with no loser follower there, are pooled with the next rung)
e4_file <- file.path(out_dir, "robust_ties_e4", "main_result.csv")
if (file.exists(e4_file)) {
  e4 <- fread(e4_file)
  rob <- rbind(rob, data.table(column = "y", estimate = e4$estimate, ci_lower = e4$ci_lower, ci_upper = e4$ci_upper,
                               p_bootstrap = e4$p_bootstrap, n = e4$total_person_successions,
                               spec = "Ties formed by $e-4$ (late recruits excluded)"), fill = TRUE)
}
rob <- rbind(rob,
  estimate_columns(build_design(keep = !(sample$election %in% c(1976L, 1988L))), cbind(y = sample$delta[!(sample$election %in% c(1976L, 1988L))]))$table[
    , spec := "Without 1976 and 1988 (president leaned early)"],
  estimate_columns(build_design(keep = sample$network != "1982_771"), cbind(y = sample$delta[sample$network != "1982_771"]))$table[
    , spec := "Without D\\'iaz Serrano's group (1982)"], fill = TRUE)
rob[, unit := "rungs"]
thr_tab <- rbindlist(lapply(thr, function(t) {
  y <- as.numeric(sample$post >= t[[1]]) - as.numeric(sample$pre >= t[[1]])
  estimate_columns(build_design(), cbind(y = y))$table[, `:=`(spec = t[[2]], unit = "pp")]
}))
rob <- rbind(rob, thr_tab)
fwrite(rob, file.path(out_dir, "robustness.csv"))
rl <- c("% robustness.tex (appendix_diagnostics.R)", "\\begin{tabular}{lrr}", "\\toprule",
        " & Estimate & 95\\% interval \\\\", "\\midrule",
        "\\multicolumn{3}{l}{\\textit{A. Change in highest rung (rungs)}} \\\\")
for (i in which(rob$unit == "rungs")) rl <- c(rl, sprintf("%s & %s & %s \\\\", rob$spec[i], f2(rob$estimate[i]), ci_txt(rob$ci_lower[i], rob$ci_upper[i])))
rl <- c(rl, "\\addlinespace", "\\multicolumn{3}{l}{\\textit{B. Change in the share above a rung (percentage points)}} \\\\")
for (i in which(rob$unit == "pp")) rl <- c(rl, sprintf("%s & %s & %s \\\\", rob$spec[i], f2(100 * rob$estimate[i], 1),
                                                         ci_txt(100 * rob$ci_lower[i], 100 * rob$ci_upper[i], 1)))
rl <- c(rl, "\\bottomrule", "\\end{tabular}")
write_tab(rl, "robustness.tex")

# ------------------------------------------------------------------ 5. coverage of the interval in simulations
cov <- fread(file.path(out_dir, "inference_coverage.csv"))
cov[, scenario := c("No shock common to a contender's followers", "Common shock, variance 1", "Common shock, variance 2",
                    "Common shock, variance 2, heavy tails ($t_5$)", "Same politician in several successions",
                    "Common shock, variance 2, groups of a succession offsetting")]
cl <- c("% coverage.tex (appendix_diagnostics.R from inference_coverage.csv)", "\\begin{tabular}{lrrr}", "\\toprule",
        "Simulated errors & Coverage (\\%) & Monte Carlo s.e. & Samples \\\\", "\\midrule")
for (i in seq_len(nrow(cov))) cl <- c(cl, sprintf("%s & %s & %s & %s \\\\", cov$scenario[i], f2(100 * cov$coverage[i], 1),
                                                  f2(100 * cov$coverage_mc_se[i], 1), format(cov$reps[i], big.mark = ",")))
cl <- c(cl, "\\bottomrule", "\\end{tabular}")
write_tab(cl, "coverage.tex")

# ------------------------------------------------------------------ 6. anticipation: new ties with each contender by year
slate_long <- contenders[in_main_slate == 1L & election_year %in% elections, .(election = election_year, contender = person_id, role)]
tie_long <- unique(long_ties[, .(pid, candidate, year_start)])
ant <- rbindlist(lapply(seq_len(nrow(slate_long)), function(i) {
  e <- slate_long$election[i]; c0 <- slate_long$contender[i]
  t <- tie_long[candidate == c0 & year_start >= e - 10L & year_start <= e + 1L, .N, by = year_start]
  data.table(election = e, contender = c0, designee = slate_long$role[i] == "winner",
             k = -10:1, ties = t$N[match(e + (-10:1), t$year_start)])
}))
ant[is.na(ties), ties := 0]
ant[, share := ties / pmax(sum(ties[k <= -2]), 1), by = .(election, contender)]
ant_avg <- ant[, .(share = mean(share), ties = mean(ties), contenders = .N), by = .(designee, k)]
fwrite(ant_avg, file.path(out_dir, "anticipation_ties.csv"))
pa <- ant_avg[k <= -2]
ga <- ggplot(pa, aes(k, ties, linetype = designee, shape = designee)) +
  geom_line(colour = INK, linewidth = 0.45) + geom_point(colour = INK, size = 1.9, fill = "white") +
  scale_shape_manual(values = c(`TRUE` = 16, `FALSE` = 21)) + scale_linetype_manual(values = c(`TRUE` = "solid", `FALSE` = "dashed")) +
  annotate("text", x = -9.9, y = max(pa$ties) * 1.08, label = "Solid: designee.  Dashed: average losing contender.",
           hjust = 0, colour = INK, size = 4.2, family = FAM) +
  annotate("text", x = -3.3, y = max(pa[designee == TRUE, ties]) * 0.98, hjust = 1, vjust = 1, colour = MUTED, size = 3.9,
           family = FAM, lineheight = 0.9, label = "1976 and 1982 designees appointed\nto Finance and to Programming\nand Budget") +
  scale_x_continuous(breaks = -10:-2, labels = k_labels_ascii) +
  labs(x = "Year relative to the presidential election (e)", y = "New direct ties formed in the year\n(average per contender)") +
  theme_paper(17)
ggsave(file.path(out_dir, "anticipation_ties.pdf"), ga, width = 10, height = 4.1, bg = "white", device = "pdf")
ggsave(file.path(out_dir, "anticipation_ties.png"), ga, width = 10, height = 4.1, dpi = 250, bg = "white")

# ------------------------------------------------------------------ 7. losing camps vs random regroupings
L <- sample[treated == 0L]
between_ss <- function(lab) L[, .(n = .N, m = mean(residual_change)), by = .(election, lab)][, sum(n * m^2)]
S_real <- between_ss(L$network)
set.seed(17102026L)
S_perm <- replicate(10000L, between_ss(L[, .(lab = base::sample(network)), by = election]$lab))
p_camps <- mean(S_perm >= S_real)
donor <- merge(fread(file.path(out_dir, "control_network_donors.csv")),
               contenders[in_main_slate == 1L, .(election = election_year, patron = person_id, person_name, is_runner_up)],
               by = c("election", "patron"))
big <- donor[n >= 30 | grepl("^Padilla", person_name)][order(-n)]
big[, surname := sub(",.*$", "", person_name)]
big[, note := fifelse(grepl("^Padilla", person_name), " (ran against the PRI)", fifelse(is_runner_up == 1L, " (runner-up)", ""))]
camps_out <- list(p = p_camps, S_real = S_real, S_perm_mean = mean(S_perm), camps = big[, .(election, surname, n, residual, note)])
fwrite(data.table(statistic = "between_camp_sum_of_squares", real = S_real, permutation_mean = mean(S_perm),
                  permutations = 10000L, p_value = p_camps), file.path(out_dir, "camps_permutation.csv"))
latex_name <- function(x) { x <- gsub("Lopez", "L\\\\'opez", x); x <- gsub("Munoz", "Mu\\\\~noz", x); x }
ml <- c("% camps.tex (appendix_diagnostics.R)", "\\begin{tabular}{lrr}", "\\toprule",
        "Contender's followers & Followers & Rank change relative to \\\\", " & & comparable losers' followers \\\\", "\\midrule",
        sprintf("Designee's (average of nine successions) & %d & %s \\\\", sum(components$n_winner), f2(theta)), "\\addlinespace",
        "\\multicolumn{3}{l}{\\textit{Largest losing contenders}} \\\\")
for (i in seq_len(nrow(big))) ml <- c(ml, sprintf("%s %d%s & %d & %s \\\\", latex_name(big$surname[i]), big$election[i], big$note[i], big$n[i], f2(big$residual[i])))
ml <- c(ml, "\\midrule", sprintf("\\multicolumn{3}{l}{Losing camps vs random camps of the same sizes: permutation $p$ = %s} \\\\", f2(p_camps)),
        "\\bottomrule", "\\end{tabular}")
write_tab(ml, "camps.tex")

# ------------------------------------------------------------------ 8. margins and budget tables (main slides)
mw <- fread(file.path(out_dir, "margins_windows.csv"))
loser_mean <- c(mean(sample$delta[sample$treated == 0]), mean((sample$post > 0)[sample$treated == 0]) - 1,
                mean(sample$delta[sample$treated == 0 & sample$post > 0]))
mt <- c("% margins.tex (appendix_diagnostics.R from margins_windows.csv)", "\\begin{tabular}{lrrr}", "\\toprule",
        " & Estimate & 95\\% interval & Losers' followers \\\\", " & & & mean change \\\\", "\\midrule",
        sprintf("Rank, 0 if no recorded post (rungs) & %s & %s & %s \\\\", f2(mw$estimate[1]), ci_txt(mw$ci_lower[1], mw$ci_upper[1]), f2(loser_mean[1])),
        sprintf("Holds a ranked post (percentage points) & %s & %s & %s \\\\", f2(100 * mw$estimate[2], 1),
                ci_txt(100 * mw$ci_lower[2], 100 * mw$ci_upper[2], 1), f2(100 * loser_mean[2], 1)),
        sprintf("Rank if in office before and after (rungs) & %s & %s & %s \\\\", f2(mw$estimate[3]), ci_txt(mw$ci_lower[3], mw$ci_upper[3]), f2(loser_mean[3])),
        sprintf("\\quad Bounds for selection into office (Lee) & \\multicolumn{2}{c}{%s} & \\\\", ci_txt(mw$lee_lower[3], mw$lee_upper[3])),
        "\\midrule", sprintf("Politicians & \\multicolumn{3}{l}{%s; %s in office before and after} \\\\",
                             format(mw$n[1], big.mark = ","), format(mw$n[3], big.mark = ",")), "\\bottomrule", "\\end{tabular}")
write_tab(mt, "margins.tex")
bw <- fread(file.path(out_dir, "budget_windows.csv")); bd <- fread(file.path(out_dir, "budget_descriptives.csv"))
btab <- c("% budget.tex (appendix_diagnostics.R from budget_windows.csv)", "\\begin{tabular}{lrrrr}", "\\toprule",
          " & & & \\multicolumn{2}{c}{Mean after designation} \\\\", "\\cmidrule(lr){4-5}",
          " & Estimate & 95\\% interval & Designee's & Losers' \\\\", "\\midrule",
          sprintf("Heads an investment agency (percentage points) & %s & %s & %s & %s \\\\", f2(100 * bw$estimate[2], 1),
                  ci_txt(100 * bw$ci_lower[2], 100 * bw$ci_upper[2], 1), f2(100 * bd$heads_post[1], 1), f2(100 * bd$heads_post[2], 1)),
          sprintf("Federal investment commanded (percentage points) & %s & %s & %s & %s \\\\", f2(bw$estimate[1]),
                  ci_txt(bw$ci_lower[1], bw$ci_upper[1]), f2(bd$share_post[1]), f2(bd$share_post[2])),
          "\\bottomrule", "\\end{tabular}")
write_tab(btab, "budget.tex")

print(bt[, .(label, mean_designee = round(mean_designee, 2), mean_losers = round(mean_losers, 2), diff = round(estimate, 2),
             std = round(std_diff, 2), p = round(p_bootstrap, 2))])
print(rob[, .(spec, estimate = round(estimate, 3), ci_lower = round(ci_lower, 3), ci_upper = round(ci_upper, 3))])
cat("camps permutation p:", p_camps, "\n")
print(ant_avg[order(designee, k)])

# ------------------------------------------------------------------ 9. rank event-study figure and slide macros
esr <- fread(file.path(out_dir, "event_study.csv"))[outcome == "rank"]
es_figure(esr, "Difference in rank since e-2 (rungs)", "es_rank")
ess <- fread(file.path(out_dir, "event_study_summary.csv"))[outcome == "rank"]
mr <- fread(file.path(out_dir, "main_result.csv"))
pv <- function(p) if (p < 0.001) "$<$0.001" else f2(p, 3)
num <- function(x, d = 2) gsub("\\$", "", f2(x, d))
mac <- function(name, value) sprintf("\\newcommand{\\%s}{%s}", name, value)
neg <- function(x, d = 2) { v <- round(x, d); s <- formatC(abs(v), format = "f", digits = d); if (v < 0) paste0("$-$", s) else s }
row_of <- function(dt, key, col = "contrast") dt[get(col) == key]
lead <- row_of(ess, "lead_average"); drop <- row_of(ess, "change_7_minus_6"); nxt <- row_of(ess, "next_president_average")
k1 <- esr[k == 1]; jl <- row_of(ess, "joint_lead_test_max_t")
lines_mac <- c("% main_direct_tie_macros.tex -- every number on the empirical slides (appendix_diagnostics.R). Do not edit by hand.",
  mac("MDmainEst", neg(mr$estimate)), mac("MDmainLo", neg(mr$ci_lower)), mac("MDmainHi", neg(mr$ci_upper)), mac("MDmainP", pv(mr$p_bootstrap)),
  mac("MDnObs", format(mr$total_person_successions, big.mark = ",")), mac("MDnPeople", format(mr$unique_people, big.mark = ",")),
  mac("MDnDesignee", sum(sample$treated)), mac("MDnLosers", format(sum(sample$treated == 0), big.mark = ",")),
  mac("MDnLosingCamps", mr$control_donor_networks),
  mac("MDloserMean", neg(mean(sample$delta[sample$treated == 0]))),
  mac("MDleadEst", neg(lead$estimate)), mac("MDleadLo", neg(lead$ci_lower)), mac("MDleadHi", neg(lead$ci_upper)),
  mac("MDleadJointP", f2(jl$p_bootstrap)),
  mac("MDoneEst", neg(k1$estimate)), mac("MDoneLo", neg(k1$ci_lower)), mac("MDoneHi", neg(k1$ci_upper)),
  mac("MDdropEst", neg(drop$estimate)), mac("MDdropLo", neg(drop$ci_lower)), mac("MDdropHi", neg(drop$ci_upper)),
  mac("MDnextEst", neg(nxt$estimate)),
  mac("MDextEst", neg(100 * mw$estimate[2], 1)), mac("MDextLo", neg(100 * mw$ci_lower[2], 1)), mac("MDextHi", neg(100 * mw$ci_upper[2], 1)),
  mac("MDintEst", neg(mw$estimate[3])), mac("MDintLo", neg(mw$ci_lower[3])), mac("MDintHi", neg(mw$ci_upper[3])),
  mac("MDleeLo", neg(mw$lee_lower[3])), mac("MDleeHi", neg(mw$lee_upper[3])), mac("MDnStay", format(mw$n[3], big.mark = ",")),
  mac("MDheadsEst", neg(100 * bw$estimate[2], 1)), mac("MDheadsLo", neg(100 * bw$ci_lower[2], 1)), mac("MDheadsHi", neg(100 * bw$ci_upper[2], 1)),
  mac("MDheadsW", neg(100 * bd$heads_post[1], 1)), mac("MDheadsL", neg(100 * bd$heads_post[2], 1)),
  mac("MDbudgetEst", neg(bw$estimate[1])), mac("MDbudgetLo", neg(bw$ci_lower[1])), mac("MDbudgetHi", neg(bw$ci_upper[1])),
  mac("MDbudgetP", f2(bw$p_bootstrap[1], 2)),
  mac("MDbalMaxStd", f2(max(abs(bt$std_diff)))), mac("MDbalMinP", f2(min(bt$p_bootstrap))),
  mac("MDcampsP", f2(p_camps)),
  mac("MDpersonEst", neg(rob[spec == "Successions weighted by designee's followers", estimate])),
  mac("MDtiesFourEst", if (file.exists(e4_file)) neg(e4$estimate) else "--"),
  mac("MDtiesFourLo", if (file.exists(e4_file)) neg(e4$ci_lower) else "--"),
  mac("MDtiesFourHi", if (file.exists(e4_file)) neg(e4$ci_upper) else "--"),
  mac("MDcovMin", f2(100 * min(cov$coverage), 1)), mac("MDcovMax", f2(100 * max(cov$coverage), 1)),
  mac("MDrobMin", neg(min(rob[unit == "rungs", estimate]))), mac("MDrobMax", neg(max(rob[unit == "rungs", estimate]))),
  mac("MDpositiveCohorts", sum(components$relative_premium > 0)),
  mac("MDnoEarlyEst", neg(rob[grepl("^Without 1976", spec), estimate])),
  mac("MDnoEarlyLo", neg(rob[grepl("^Without 1976", spec), ci_lower])),
  mac("MDnoEarlyHi", neg(rob[grepl("^Without 1976", spec), ci_upper])))
writeLines(lines_mac, file.path(tab_dir, "main_direct_tie_macros.tex"))
