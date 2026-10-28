# Balance table of the main design (MAIN_SPEC section 10 (1); 20 October 2026). One row per predetermined trait of the
# politicians in the section-1 sample: raw means of the designee's and the losing contenders' followers, the
# within-succession difference (the section-4 estimator with succession indicators as the only covariates, i.e. the
# equal-weight mean over the nine successions of designee's minus losers' followers), the normalized difference of Imbens
# and Rubin (2015) (within-succession difference / sqrt((sd_D^2 + sd_P^2) / 2), group s.d. computed on the pooled sample)
# and the section-5 Ferman-Pinto contender-level bootstrap p with the trait as the outcome (20,000 draws).
# Joint test: the designee indicator is regressed on every trait and succession indicators within the sample; the
# statistic is the F statistic of the traits (primary) and the sum of squared normalized differences (secondary). The
# permutation p reassigns, within each succession, which contender's whole group of followers carries the designee label,
# uniformly among the contenders with at least one exclusive follower in the sample (5,000 draws from the product of
# group counts); the sample, the ties and the traits stay fixed.
# Pre-trend: change in the highest rung from e-9..e-6 to e-5..e-2 (earlier to pre), for every politician (earlier = 0 if no
# rung recorded) and restricted to those with a rung in e-9..e-6.
# Trait definitions follow appendix_diagnostics.R section 1 (education, birthplace, military, elected and party posts) and
# rp_setup.R section 1 (federal executive post in e-5..e-2); ties with the contender come from the dated edges that define
# the treatment (co_work, co_education, co_military, co_revolution formed by e-2).
# Run from the repo root (after estimate_main.R): Rscript code/04-analysis/main_direct_tie/balance_table.R
# Writes balance_main.csv, balance_joint_test.csv, tables/balance_main.tex and tables/balance_macros.tex.
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
invisible(capture.output(source(file.path(script_dir, "estimate_main.R"))))
source(file.path(script_dir, "design_tools.R"))
invisible(capture.output(source(file.path(script_dir, "rp_setup.R"))))   # A: fed_exec for every follower
tab_dir <- file.path(out_dir, "tables"); dir.create(tab_dir, showWarnings = FALSE)
B_boot <- 20000L; seed <- 20102026L; n_perm <- 5000L

# ------------------------------------------------------------------ 1. traits
pos_all <- fread(file.path(data_dir, "rank", "position_tiers.csv"), na.strings = c("", "NA"))
edu <- fread(file.path(data_dir, "education_wide.csv"))
elected_rules <- c("federal_deputy", "senator", "local_deputy", "governor_major_state", "governor_other_state",
                   "governor_state_unknown", "mayor", "mayor_big_city", "city_council", "df_assembly_or_delegate")
first_year <- function(rows) rows[!is.na(year_start), .(y = min(year_start)), by = person_id]
fe <- first_year(pos_all[rule %in% elected_rules]); fp <- first_year(pos_all[dataset == "party_positions"])
fm <- unique(pos_all[dataset == "military_positions", person_id])
bal <- copy(sample)
ed_of <- function(col) as.numeric(edu[[col]][match(bal$pid, edu$person_id)] %in% 1)
bal[, `:=`(n_posts = expm1(lrec), n_ties = expm1(ldeg), prev_designee = as.numeric(prior_status == "prev_winner"),
           pretrend = as.numeric(pre - earlier),
           born_df = as.numeric(nodes$birth_state[match(pid, nodes$person_id)] %in% "Federal District"),
           graduate = pmax(ed_of("masters"), ed_of("phd")), law = ed_of("law"), economics = ed_of("economics"),
           elected = as.numeric(fe$y[match(pid, fe$person_id)] <= election - 2L),
           party = as.numeric(fp$y[match(pid, fp$person_id)] <= election - 2L),
           military = as.numeric(pid %in% fm))]
bal[is.na(elected), elected := 0]; bal[is.na(party), party := 0]
# Career by e-2 from the annual ranks of the estimator (retained ranked posts only).
rank_e2 <- annual[data.table(pid = bal$pid, year = bal$election - 2L), on = .(pid, year), rank]
bal[, holds_e2 := as.numeric(!is.na(rank_e2) & rank_e2 > 0)]
bal[, cabinet := 0]
for (e in elections) bal[election == e, cabinet := as.numeric(highest_rank(pid, 0L, e - 2L) >= 8L)]
followers <- A[group != "N"]
bal[, fed_exec := as.numeric(followers$fed_exec[match(paste(pid, election), paste(followers$pid, followers$election))])]
# Ties with the contender: the dated edges of the treatment definition, formed by e - tie_lag.
tie_pairs <- unique(rbind(dated[edge_type %in% tie_types, .(pid = person_a, candidate = person_b, edge_type, year_start)],
                          dated[edge_type %in% tie_types, .(pid = person_b, candidate = person_a, edge_type, year_start)]))
pt_ties <- merge(bal[, .(pid, candidate = patron, election)], tie_pairs, by = c("pid", "candidate"), allow.cartesian = TRUE)
pt_ties <- pt_ties[year_start <= election - tie_lag]
tie_stats <- pt_ties[, .(first_tie = min(year_start), cowork = as.numeric(any(edge_type == "co_work"))), by = .(pid, election)]
bal[tie_stats, on = .(pid, election), `:=`(tie_years = election - 2L - i.first_tie, tie_cowork = i.cowork)]
stopifnot(identical(bal$pid, sample$pid), identical(bal$election, sample$election),
          !anyNA(bal$fed_exec), !anyNA(bal$tie_years), !anyNA(bal$tie_cowork), all(bal$tie_years >= 0))

traits <- rbindlist(list(
  list("pre", "Highest rank, $e-5$ to $e-2$", "A", 2L),
  list("earlier", "Highest rank, $e-9$ to $e-6$ (0 if none)", "A", 2L),
  list("pretrend", "Change between the two (pre-trend)", "A", 2L),
  list("pretrend_pos", "\\quad among those with a rank in $e-9$ to $e-6$", "A", 2L),
  list("holds_e2", "Holds a ranked post in $e-2$", "A", 2L),
  list("n_posts", "Ranked posts by $e-2$", "A", 1L),
  list("fed_exec", "Federal executive post, $e-5$ to $e-2$", "A", 2L),
  list("cabinet", "Cabinet-level post (rank $\\geq 8$) by $e-2$", "A", 2L),
  list("elected", "Elected office by $e-2$", "A", 2L),
  list("party", "Party post by $e-2$", "A", 2L),
  list("age", "Age in the election year", "B", 2L),
  list("born_df", "Born in Mexico City", "B", 2L),
  list("law", "Law degree", "B", 2L),
  list("economics", "Economics degree", "B", 2L),
  list("graduate", "Graduate degree", "B", 2L),
  list("military", "Military career", "B", 2L),
  list("n_ties", "Ties by $e-2$", "C", 1L),
  list("prev_designee", "Tied to the previous designee", "C", 2L),
  list("tie_years", "Years since the tie to the contender formed", "C", 2L),
  list("tie_cowork", "Tie with the contender is co-work", "C", 2L)))
setnames(traits, c("column", "label", "panel", "digits"))
panel_names <- c(A = "A. Career by $e-2$", B = "B. Background", C = "C. Ties")

# ------------------------------------------------------------------ 2. means, within-succession differences, bootstrap p
main_cols <- traits[column != "pretrend_pos", column]
Xb <- as.matrix(bal[, ..main_cols])
d_fe <- build_design(formula = ~ election_factor)
stopifnot(length(d_fe$rows) == nrow(bal), length(d_fe$elections) == length(elections))
bt <- estimate_columns(d_fe, Xb, B = B_boot, seed = seed)$table
keep_pos <- bal$earlier > 0
d_pos <- build_design(keep = keep_pos, formula = ~ election_factor)
bt_pos <- estimate_columns(d_pos, cbind(pretrend_pos = bal$pretrend[d_pos$rows]), B = B_boot, seed = seed)$table
bt[, `:=`(successions = length(d_fe$elections), n_designee = NULL)]
bt_pos[, `:=`(successions = length(d_pos$elections), n_designee = NULL)]
describe <- function(x, tr) data.table(
  mean_designee = mean(x[tr == 1]), mean_losers = mean(x[tr == 0]), sd_designee = sd(x[tr == 1]), sd_losers = sd(x[tr == 0]),
  n_designee = sum(tr == 1), n_losers = sum(tr == 0))
desc <- rbindlist(c(lapply(main_cols, function(v) describe(bal[[v]], bal$treated)[, column := v]),
                    list(describe(bal$pretrend[d_pos$rows], bal$treated[d_pos$rows])[, column := "pretrend_pos"])))
out <- merge(traits, merge(rbind(bt, bt_pos), desc, by = "column"), by = "column", sort = FALSE)
out <- out[match(traits$column, column)]
setnames(out, "estimate", "diff_within")
out[, `:=`(diff_raw = mean_designee - mean_losers, sd_pair = sqrt((sd_designee^2 + sd_losers^2) / 2))]
out[, `:=`(norm_diff = diff_within / sd_pair, norm_diff_raw = diff_raw / sd_pair)]

# ------------------------------------------------------------------ 3. joint test with a within-succession permutation p
# The pre-trend is pre minus earlier, so it is left out of the regression (exactly collinear); the restricted row is a
# subsample. Other exactly collinear traits, if any, are dropped with a message.
joint_cols <- setdiff(main_cols, "pretrend")
el <- bal$election; tr <- bal$treated; n <- nrow(bal); E <- length(elections)
Gm <- model.matrix(~ 0 + election_factor, data = bal); GtG_inv <- solve(crossprod(Gm))
within <- function(M) M - Gm %*% (GtG_inv %*% crossprod(Gm, M))
Xj <- as.matrix(bal[, ..joint_cols]); Xd <- within(Xj)
keep_j <- logical(0)
for (j in seq_len(ncol(Xd))) keep_j[j] <- qr(Xd[, c(which(keep_j), j), drop = FALSE])$rank == sum(keep_j) + 1L
if (!all(keep_j)) message("Dropped from the joint test (collinear within succession): ", paste(joint_cols[!keep_j], collapse = ", "))
joint_cols <- joint_cols[keep_j]; Xj <- Xj[, keep_j, drop = FALSE]; Xd <- Xd[, keep_j, drop = FALSE]
q <- ncol(Xd); Qm <- solve(crossprod(Xd))
f_stat <- function(Y) {   # Y: designee indicators, one column per assignment
  Yd <- within(Y); Bm <- crossprod(Xd, Yd)
  expl <- colSums(Bm * (Qm %*% Bm)); rss <- colSums(Yd^2)
  (expl / q) / ((rss - expl) / (n - q - E))
}
ssnd_stat <- function(Y) {   # sum over traits of squared normalized within-succession differences
  n1 <- colSums(Y); n0 <- n - n1
  m1 <- crossprod(Y, Xj) / n1; m0 <- crossprod(1 - Y, Xj) / n0
  v1 <- (crossprod(Y, Xj^2) / n1 - m1^2) * n1 / (n1 - 1); v0 <- (crossprod(1 - Y, Xj^2) / n0 - m0^2) * n0 / (n0 - 1)
  diff <- 0
  for (e in elections) {
    ix <- el == e; Ye <- Y[ix, , drop = FALSE]; Xe <- Xj[ix, , drop = FALSE]
    diff <- diff + (crossprod(Ye, Xe) / colSums(Ye) - crossprod(1 - Ye, Xe) / colSums(1 - Ye)) / E
  }
  rowSums((diff / sqrt((v1 + v0) / 2))^2)
}
Y_obs <- cbind(as.numeric(tr))
F_obs <- f_stat(Y_obs); S_obs <- ssnd_stat(Y_obs)
groups <- unique(bal[, .(election, network)])
set.seed(seed)
Yp <- matrix(0, n, n_perm)
for (e in elections) {
  ne <- groups[election == e, network]; ix <- which(el == e)
  Yp[ix, ] <- outer(bal$network[ix], ne[sample.int(length(ne), n_perm, replace = TRUE)], "==") * 1
}
stopifnot(all(colSums(Yp) > 0))
F_perm <- f_stat(Yp); S_perm <- ssnd_stat(Yp)
p_F <- mean(F_perm >= F_obs - 1e-12); p_S <- mean(S_perm >= S_obs - 1e-12)
slate_sizes <- contenders[in_main_slate == 1L & election_year %in% elections, .N, by = election_year]$N
joint <- data.table(statistic = c("F_traits", "sum_squared_normalized_differences"), observed = c(F_obs, S_obs),
                    permutation_mean = c(mean(F_perm), mean(S_perm)), p_permutation = c(p_F, p_S),
                    p_asymptotic = c(pf(F_obs, q, n - q - E, lower.tail = FALSE), NA_real_),
                    traits = q, permutations = n_perm, groups_product = prod(groups[, .N, by = election]$N),
                    slate_product = prod(slate_sizes), seed = seed)

# ------------------------------------------------------------------ 4. outputs
fwrite(out[, .(column, label, panel, mean_designee, mean_losers, sd_designee, sd_losers, diff_raw, diff_within, norm_diff,
               norm_diff_raw, ci_lower, ci_upper, ci90_lower, ci90_upper, p_bootstrap, n, n_designee, n_losers, successions,
               in_joint_test = column %in% joint_cols, bootstrap_draws = B_boot, seed = seed)],
       file.path(out_dir, "balance_main.csv"))
fwrite(joint, file.path(out_dir, "balance_joint_test.csv"))

f2 <- function(x, d = 2) { r <- round(x, d); s <- formatC(r, format = "f", digits = d); s[r == 0] <- formatC(0, format = "f", digits = d); sub("^-", "$-$", s) }
nD <- sum(bal$treated); nP <- sum(bal$treated == 0)
tl <- c("% balance_main.tex -- balance of predetermined traits in the main sample (balance_table.R). Means: raw, by group.",
        "% Difference: section-4 estimator with succession indicators only (equal-weight mean over the nine successions of",
        "% designee's minus losers' followers). Normalized difference: that difference / sqrt((sd_D^2 + sd_P^2)/2), group s.d. on",
        "% the pooled sample (Imbens and Rubin 2015). p: Ferman-Pinto bootstrap at the contender level, 20,000 draws. Joint test:",
        "% F statistic of the traits in a regression of the designee indicator on the traits and succession indicators; permutation",
        "% p from 5,000 reassignments of the designee label among the contender groups within each succession.",
        "\\begin{tabular}{lrrrrr}", "\\toprule",
        " & Designee's & Losing contenders' & Difference & Normalized & $p$ \\\\",
        " & followers & followers & & difference & \\\\", "\\midrule")
for (pn in c("A", "B", "C")) {
  tl <- c(tl, sprintf("\\multicolumn{6}{l}{\\textit{%s}} \\\\", panel_names[[pn]]))
  for (i in which(out$panel == pn)) {
    dd <- out$digits[i]
    tl <- c(tl, sprintf("%s & %s & %s & %s & %s & %s \\\\", out$label[i], f2(out$mean_designee[i], dd), f2(out$mean_losers[i], dd),
                        f2(out$diff_within[i], dd), f2(out$norm_diff[i], 2), f2(out$p_bootstrap[i], 2)))
  }
}
tl <- c(tl, "\\midrule",
        sprintf("Politicians & %s & %s & \\multicolumn{3}{r}{Joint test: $F$ = %s, $p$ = %s} \\\\",
                format(nD, big.mark = ","), format(nP, big.mark = ","), f2(F_obs, 2), f2(p_F, 2)),
        "\\bottomrule", "\\end{tabular}")
writeLines(tl, file.path(tab_dir, "balance_main.tex"))

mac <- function(name, value) sprintf("\\newcommand{\\%s}{%s}", name, value)
pv <- function(p) if (p < 0.001) "$<$0.001" else f2(p, 2)
uniq <- out[column != "pretrend_pos"]
i_max <- uniq[, which.max(abs(norm_diff))]
pre_all <- out[column == "pretrend"]; pre_pos <- out[column == "pretrend_pos"]
writeLines(c("% balance_macros.tex -- numbers of the balance slide (balance_table.R). Do not edit by hand.",
             mac("BALmaxNorm", f2(max(abs(uniq$norm_diff)), 2)), mac("BALmaxNormTrait", uniq$label[i_max]),
             mac("BALmeanNorm", f2(mean(abs(uniq$norm_diff)), 2)), mac("BALminP", f2(min(uniq$p_bootstrap), 2)),
             mac("BALjointP", pv(p_F)), mac("BALjointF", f2(F_obs, 2)), mac("BALjointPnorm", pv(p_S)),
             mac("BALnTraits", nrow(uniq)), mac("BALnJoint", q), mac("BALnPerm", format(n_perm, big.mark = ",")),
             mac("BALpretrendDiff", f2(pre_all$diff_within, 2)), mac("BALpretrendP", f2(pre_all$p_bootstrap, 2)),
             mac("BALpretrendLo", f2(pre_all$ci_lower, 2)), mac("BALpretrendHi", f2(pre_all$ci_upper, 2)),
             mac("BALpretrendPosDiff", f2(pre_pos$diff_within, 2)), mac("BALpretrendPosP", f2(pre_pos$p_bootstrap, 2)),
             mac("BALpretrendPosN", format(pre_pos$n, big.mark = ",")),
             mac("BALnDesignee", format(nD, big.mark = ",")), mac("BALnLosers", format(nP, big.mark = ","))),
           file.path(tab_dir, "balance_macros.tex"))

print(out[, .(panel, label = gsub("\\\\quad |\\$", "", label), designee = round(mean_designee, 2), losers = round(mean_losers, 2),
              diff = round(diff_within, 2), norm = round(norm_diff, 2), p = round(p_bootstrap, 2), n)])
print(joint[, .(statistic, observed = round(observed, 3), permutation_mean = round(permutation_mean, 3), p_permutation, p_asymptotic = round(p_asymptotic, 3), traits)])
cat(sprintf("Politicians: %d designee's followers, %d losers' followers; pre-trend restricted row: %d politicians in %d successions\n",
            nD, nP, pre_pos$n, pre_pos$successions))
cat("Wrote:", file.path(out_dir, "balance_main.csv"), file.path(tab_dir, "balance_main.tex"), file.path(tab_dir, "balance_macros.tex"), "\n")

# Deck version (23 lines fit one 16:9 slide at \scriptsize): the restricted pre-trend row (driven by 1940 alone), the
# party-post row and the co-work row are left out; the full table stays in balance_main.tex.
deck <- readLines(file.path(tab_dir, "balance_main.tex"))
drop <- grepl("among those with a rank|^Party post by|^Tie with the contender is co-work", deck)
writeLines(c("% balance_deck.tex -- balance_main.tex without three rows (balance_table.R)", deck[!drop]),
           file.path(tab_dir, "balance_deck.tex"))
