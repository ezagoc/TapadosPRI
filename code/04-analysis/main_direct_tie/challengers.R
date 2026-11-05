# Successions with a break against the rest (4 November 2026, Shanker's test): does the treatment of the losers' followers
# differ in the successions where a contender left the party and ran against the designee (1940 Sánchez Tapia, 1946
# Padilla, 1952 Henríquez Guzmán, 1988 Cárdenas) from the uncontested ones? The reward (designee's followers minus the
# reweighted unaligned) and the penalty (losers' followers minus the unaligned) of the reward/penalty design (rp_setup.R:
# entropy balancing within succession, Ferman-Pinto inference), years 1-4 average of the rank change, fitted on the
# contested and the uncontested successions separately; then, within the three contested successions with a defector's
# camp in the sample, the penalty on the defector's followers against the loyal losers' followers. The penalty is measured
# after the break (years 1-4), so it reads as what followed a break, not what caused it. Writes challengers.csv,
# tables/challengers.tex and tables/challengers_macros.tex. Run inside the staging environment after estimate_main.R:
#   Rscript code/04-analysis/main_direct_tie/challengers.R
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
invisible(capture.output(source(file.path(script_dir, "estimate_main.R"))))
source(file.path(script_dir, "design_tools.R"))
invisible(capture.output(source(file.path(script_dir, "rp_setup.R"))))
tab_dir <- file.path(out_dir, "tables"); dir.create(tab_dir, showWarnings = FALSE)
set.seed(4112026L); B_ch <- 20000L
f_es <- ~ election_factor + age + ldeg + lrec + prior_status + fed_exec
S_es <- make_weights(A[support == TRUE], bal_formula_es)
ES <- YA[A$support == TRUE, , drop = FALSE]
y14 <- rowMeans(ES[, as.character(1:4), drop = FALSE]) - ES[, as.character(ref)]
contested <- c(1940L, 1946L, 1952L, 1988L)
defectors <- contenders[in_main_slate == 1L & broke_with_pri_year > 0 & broke_with_pri_year >= election_year - 1L & broke_with_pri_year <= election_year,
                        .(election = election_year, patron = person_id, name = person_name)]
cat("defector camps:\n"); print(defectors)
# On a subset of successions some covariates are collinear with the succession indicators (a prior-status level that
# exists in one succession only, fed_exec constant); the control model then drops terms until it is full rank.
fit_on <- function(rows, label) {
  S2 <- copy(S_es[rows]); y <- y14[rows]
  S2[, election_factor := factor(election)]
  tries <- list(f_es, ~ election_factor + age + ldeg + lrec + fed_exec, ~ election_factor + age + ldeg + lrec, ~ election_factor)
  fit <- NULL
  for (f in tries) { fit <- tryCatch(rp_fit(S2, y, f), error = function(e) NULL); if (!is.null(fit)) { f_used <- f; break } }
  stopifnot(!is.null(fit))
  # The Ferman-Pinto draws for the reward need several losing camps per succession as donors; where a succession keeps one
  # camp only (the defectors' and the loyal rows) the row reports the penalty alone, with its clustered interval.
  r <- tryCatch(rp_inference(S2, fit, B = B_ch), error = function(e) penalty_only(S2, fit))
  r[, control_model := paste(deparse(f_used), collapse = "")]
  r[, `:=`(set = label, n_D = sum(S2$group == "D"), n_P = sum(S2$group == "P"), n_N = sum(S2$group == "N"), successions = uniqueN(S2$election))]
}
penalty_only <- function(S2, fit) {
  P <- fit$P; seP <- sqrt(cr_var(P$a, P$u, S2$cluster, S2$group %in% c("P", "N")))
  data.table(group = "P", estimate = P$est, ci_lower = P$est - 1.96 * seP, ci_upper = P$est + 1.96 * seP,
             ci90_lower = P$est - 1.645 * seP, ci90_upper = P$est + 1.645 * seP, se = seP, p_value = 2 * pnorm(-abs(P$est / seP)),
             inference = "clustered by contender group / unaligned politician")
}
is_def <- paste(S_es$election, S_es$patron) %in% paste(defectors$election, defectors$patron)
res <- rbindlist(list(
  fit_on(S_es$election %in% contested, "Contested successions (1940, 1946, 1952, 1988)"),
  fit_on(!(S_es$election %in% contested), "Uncontested successions (1958--1982)"),
  fit_on(S_es$election %in% defectors$election, "1940, 1946 and 1952, all camps"),
  fit_on(S_es$election %in% defectors$election & (S_es$group != "P" | is_def), "1940, 1946 and 1952, the defectors' followers"),
  fit_on(S_es$election %in% defectors$election & (S_es$group != "P" | !is_def), "1940, 1946 and 1952, the loyal losers' followers")))
# Placebo over camps: in each of the three successions label one losing camp as the "defector" (every combination, the
# true one among them) and fit the penalty on those camps alone. The rank of the true penalty says how unusual it is.
camps3 <- unique(S_es[group == "P" & election %in% defectors$election, .(election, patron)])
combos <- as.data.table(expand.grid(lapply(split(camps3$patron, camps3$election), identity)))
setnames(combos, paste0("e", names(split(camps3$patron, camps3$election))))
placebo <- rbindlist(lapply(seq_len(nrow(combos)), function(i) {
  pick <- as.integer(unlist(combos[i])); els <- as.integer(sub("e", "", names(combos)))
  rows <- S_es$election %in% els & (S_es$group != "P" | paste(S_es$election, S_es$patron) %in% paste(els, pick))
  S2 <- copy(S_es[rows]); S2[, election_factor := factor(election)]
  fit <- NULL; for (f in list(f_es, ~ election_factor + age + ldeg + lrec + fed_exec, ~ election_factor + age + ldeg + lrec, ~ election_factor)) {
    fit <- tryCatch(rp_fit(S2, y14[rows], f), error = function(e) NULL); if (!is.null(fit)) break }
  data.table(combo = i, penalty = fit$P$est, n_P = sum(S2$group == "P"), is_true = all(pick %in% defectors$patron))
}))
placebo_rank <- placebo[, mean(penalty <= penalty[is_true])]
cat(sprintf("placebo over %d camp combinations: true penalty %.2f, share at least as negative %.3f\n", nrow(placebo), placebo[is_true == TRUE, penalty], placebo_rank))
fwrite(placebo, file.path(out_dir, "challengers_placebo.csv"))
fwrite(res, file.path(out_dir, "challengers.csv"))
f2 <- function(x) { v <- round(x, 2); s <- formatC(abs(v), format = "f", digits = 2); ifelse(v < 0, paste0("$-$", s), s) }
ci <- function(lo, hi) sprintf("[%s, %s]", f2(lo), f2(hi))
row_of <- function(set, grp) res[set == set & group == grp]
sets <- c(contested = "Contested successions (1940, 1946, 1952, 1988)", uncontested = "Uncontested successions (1958--1982)",
          three = "1940, 1946 and 1952, all camps",
          defector = "1940, 1946 and 1952, the defectors' followers", loyal = "1940, 1946 and 1952, the loyal losers' followers")
lines <- c("% challengers.tex (challengers.R). Reward and penalty, years 1-4 average of the rank change, by set of successions. Do not edit by hand.",
           "\\begin{tabular}{lrcccc}", "\\toprule",
           " & & \\multicolumn{2}{c}{Reward, designee's followers} & \\multicolumn{2}{c}{Penalty, losers' followers} \\\\", "\\cmidrule(lr){3-4}\\cmidrule(lr){5-6}",
           " & losers' followers & estimate & 95\\% interval & estimate & 95\\% interval \\\\", "\\midrule")
deck_rows <- c(sets[["contested"]], sets[["uncontested"]], sets[["defector"]], sets[["loyal"]])
deck_labels <- c("Contested successions (1940, 1946, 1952, 1988)", "Uncontested successions (1958--1982)", "1940, 1946 and 1952, the defectors' followers", "1940, 1946 and 1952, the loyal losers' followers")
for (i in seq_along(deck_rows)) {
  st <- deck_rows[i]; d <- res[set == st & group == "D"]; p <- res[set == st & group == "P"]
  show_d <- i <= 2
  lines <- c(lines, sprintf("%s & %d & %s & %s & %s & %s \\\\", deck_labels[i], p$n_P, if (show_d) f2(d$estimate) else "", if (show_d) ci(d$ci_lower, d$ci_upper) else "",
                            f2(p$estimate), ci(p$ci_lower, p$ci_upper)))
  if (i == 2) lines <- c(lines, "\\addlinespace[3pt]")
}
lines <- c(lines, "\\bottomrule", "\\end{tabular}")
writeLines(lines, file.path(tab_dir, "challengers.tex"))
mac <- function(n, v) sprintf("\\newcommand{\\%s}{%s}", n, v)
m <- c("% challengers_macros.tex (challengers.R). Do not edit by hand.")
for (k in names(sets)) for (grp in c("D", "P")) {
  r <- res[set == sets[[k]] & group == grp]; if (!nrow(r)) next
  key <- paste0("CH", k, if (grp == "D") "Reward" else "Penalty")
  m <- c(m, mac(key, f2(r$estimate)), mac(paste0(key, "Lo"), f2(r$ci_lower)), mac(paste0(key, "Hi"), f2(r$ci_upper)),
         mac(paste0("CH", k, "N", grp), r[[paste0("n_", grp)]]))
}
# the difference between the defectors' and the loyal losers' penalties, with a normal approximation on the two clustered SEs
dp <- res[set == sets[["defector"]] & group == "P"]; lp <- res[set == sets[["loyal"]] & group == "P"]
dd <- dp$estimate - lp$estimate; sd_dd <- sqrt(dp$se^2 + lp$se^2)
m <- c(m, mac("CHdefMinusLoyal", f2(dd)), mac("CHdefMinusLoyalLo", f2(dd - 1.96 * sd_dd)), mac("CHdefMinusLoyalHi", f2(dd + 1.96 * sd_dd)),
       mac("CHdefMinusLoyalP", formatC(2 * pnorm(-abs(dd / sd_dd)), format = "f", digits = 2)))
cp <- res[set == sets[["contested"]] & group == "P"]; up <- res[set == sets[["uncontested"]] & group == "P"]
dc <- cp$estimate - up$estimate; sd_dc <- sqrt(cp$se^2 + up$se^2)
m <- c(m, mac("CHcontMinusUncontPenalty", f2(dc)), mac("CHcontMinusUncontPenaltyLo", f2(dc - 1.96 * sd_dc)), mac("CHcontMinusUncontPenaltyHi", f2(dc + 1.96 * sd_dc)),
       mac("CHplaceboCombos", nrow(placebo)), mac("CHplaceboShare", formatC(placebo_rank, format = "f", digits = 2)), mac("CHplaceboRank", sum(placebo$penalty <= placebo[is_true == TRUE, penalty])),
       mac("CHdefectorNames", "S\\'anchez Tapia, Padilla and Henr\\'iquez Guzm\\'an"))
writeLines(m, file.path(tab_dir, "challengers_macros.tex"))
print(res[, .(set, group, estimate = round(estimate, 2), ci_lower = round(ci_lower, 2), ci_upper = round(ci_upper, 2), n_D, n_P, n_N, successions)])
