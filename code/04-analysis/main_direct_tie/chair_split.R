# The patron's chair (MAIN_SPEC section 12, 19 October 2026): the losing contenders' followers split by whether
# their patron kept a top chair in the new president's first two years, each against the reweighted unaligned
# politicians of section 11. Run after reward_punishment.R:
#   Rscript code/04-analysis/main_direct_tie/chair_split.R
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
invisible(capture.output(source(file.path(script_dir, "estimate_main.R"))))
source(file.path(script_dir, "design_tools.R"))
source(file.path(script_dir, "rp_setup.R"))
set.seed(19102026L)

# Sections 1-2 (the patron's chair, split_groups, lin_fit) live in rp_setup.R.
webb <- c(-sqrt(1.5), -1, -sqrt(.5), sqrt(.5), 1, sqrt(1.5))
lin_inference <- function(S, f, label, B = 20000L) {
  keep <- f$a != 0
  s <- tapply((f$a * f$u)[keep], S$cluster[keep], sum); G <- length(s)
  se <- sqrt(G / (G - 1) * sum(s^2))
  draws <- as.vector(matrix(sample(webb, B * G, replace = TRUE), B) %*% s) * sqrt(G / (G - 1))
  q <- quantile(draws, c(.025, .975, .05, .95), names = FALSE, type = 1)
  data.table(estimate = label, value = f$est, se = se, ci_lower = f$est - 1.96 * se, ci_upper = f$est + 1.96 * se,
             ci90_lower = f$est - 1.645 * se, ci90_upper = f$est + 1.645 * se,
             wild_lower = f$est - q[2], wild_upper = f$est - q[1], wild90_lower = f$est - q[4], wild90_upper = f$est - q[3],
             p_wild = mean(abs(draws) >= abs(f$est)), groups_treated = length(unique(S$cluster[keep & S$g != "N"])),
             successions = paste(f$successions, collapse = " "))
}
estimate_all <- function(S, y, formula, B = 20000L) {
  rbind(lin_inference(S, lin_fit(S, y, formula, "Pk"), "Pk: patron kept a top chair", B),
        lin_inference(S, lin_fit(S, y, formula, "Pl"), "Pl: patron lost it", B),
        lin_inference(S, lin_fit(S, y, formula, c("Pk", "Pl"), c(1, -1)), "Pk - Pl, within succession", B))
}
f_window <- ~ election_factor + pre_band + earlier_band + age + ldeg + lrec + prior_status + fed_exec
f_es <- ~ election_factor + age + ldeg + lrec + prior_status + fed_exec
S_main <- split_groups(make_weights(A[support == TRUE], bal_formula_window))
win <- estimate_all(S_main, S_main$delta, f_window)[, spec := "Main"]

# ------------------------------------------------------------------ 3. robustness (a)-(c)
S_a <- split_groups(S_main[, g := NULL], cut = 9L)
S_b <- split_groups(S_main[, g := NULL], rung_col = "rung_post3")
S_main <- split_groups(S_main)
rob <- rbind(estimate_all(S_a, S_a$delta, f_window)[, spec := "(a) Top chair = rung 9"],
             estimate_all(S_b, S_b$delta, f_window)[, spec := "(b) Patron's chair over e+1..e+3"])
E2 <- as.integer(strsplit(win[estimate == "Pk - Pl, within succession", successions], " ")[[1]])
for (e in E2) {
  Se <- copy(S_main[election != e]); Se[, election_factor := droplevels(election_factor)]
  rob <- rbind(rob, estimate_all(Se, Se$delta, f_window)[, spec := sprintf("(c) Without %d", e)])
}
windows <- rbind(win, rob)

# ------------------------------------------------------------------ 4. event study (section-7 covariates)
S_es <- split_groups(make_weights(A[support == TRUE], bal_formula_es))
YS <- YA[A$support == TRUE, , drop = FALSE]
es <- rbindlist(lapply(setdiff(ks, ref), function(k) {
  y <- YS[, as.character(k)] - YS[, as.character(ref)]
  estimate_all(S_es, y, f_es, B = 5000L)[, k := k]
}))
es <- rbind(es, data.table(estimate = unique(es$estimate), value = 0, se = 0, ci_lower = 0, ci_upper = 0, ci90_lower = 0, ci90_upper = 0,
                           wild_lower = 0, wild_upper = 0, wild90_lower = 0, wild90_upper = 0, k = ref), fill = TRUE)
setorder(es, estimate, k)

# ------------------------------------------------------------------ 5. selection checks (ii) and (iii)
bal_X <- model.matrix(bal_formula_window, data = S_main)[, -1]
fol <- S_main$g %in% c("Pk", "Pl")
bal <- rbindlist(lapply(colnames(bal_X), function(v) {
  x <- bal_X[fol, v]; gk <- S_main$g[fol] == "Pk"
  data.table(variable = v, kept = mean(x[gk]), lost = mean(x[!gk]),
             std_diff = (mean(x[gk]) - mean(x[!gk])) / sqrt((var(x[gk]) + var(x[!gk])) / 2))
}))
patrons[, kept := as.integer(rung_post2 >= 8L)]
pat_tab <- patrons[, .(patrons = .N, with_followers = sum(followers > 0), followers = sum(followers), rung_at_e_minus_2 = mean(rung_pre),
                       cabinet_at_e_minus_2 = mean(rung_pre >= 9L), age = mean(age, na.rm = TRUE), runner_up = mean(runner_up),
                       mean_followers = mean(followers)), by = kept]

fwrite(windows, file.path(out_dir, "chair_split_windows.csv")); fwrite(es, file.path(out_dir, "chair_split_event_study.csv"))
fwrite(bal, file.path(out_dir, "chair_split_balance.csv")); fwrite(patrons, file.path(out_dir, "chair_split_patrons.csv"))
r3 <- function(d) d[, lapply(.SD, function(x) if (is.numeric(x)) round(x, 3) else x)]
print(r3(windows[, .(spec, estimate, value, ci_lower, ci_upper, wild_lower, wild_upper, p_wild, groups_treated, successions)]))
print(r3(pat_tab)); print(r3(bal))
print(r3(es[, .(estimate, k, value, ci_lower, ci_upper)]))
print(patrons[kept == 1L, .(election, patron, name = nodes$name[match(patron, nodes$person_id)], rung_post2, followers)])
