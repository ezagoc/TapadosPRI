# One balance table for the deck (3 November 2026): the designee's followers against the losing contenders' followers
# (the main contrast) and both groups of followers against the reweighted unaligned politicians (the reward/penalty
# contrast), on one list of predetermined traits. Traits used as covariates in the estimation come first, the rest
# after a rule; no panel headings.
#   Followers block: raw means, the equal-weight mean over successions of the within-succession difference (designee's
#   minus losers'), that difference over sqrt((sd_D^2 + sd_P^2)/2) (Imbens and Rubin 2015), and the Ferman-Pinto
#   contender-level bootstrap p (design_tools.R, 20,000 draws), as in balance_table.R.
#   Unaligned block: the entropy-balancing weights of reward_punishment.R (rp_setup.R, within succession, common support),
#   the weighted mean aggregated with the followers' succession shares, and the standardized difference followers minus
#   weighted unaligned over sqrt((var_followers + var_unaligned)/2), as in reward_punishment.R section 5.
# Run after estimate_main.R, inside the deck's staging environment (research/eligibility_refresh_2026_10_27):
#   Rscript slides/analysis/balance_combined.R
# Writes balance_combined.csv, tables/balance_combined.tex and tables/balance_combined_macros.tex.
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
invisible(capture.output(source(file.path(script_dir, "estimate_main.R"))))
source(file.path(script_dir, "design_tools.R"))
invisible(capture.output(source(file.path(script_dir, "rp_setup.R"))))
tab_dir <- file.path(out_dir, "tables"); dir.create(tab_dir, showWarnings = FALSE)
B_boot <- 20000L; seed <- 20102026L
S_main <- make_weights(A[support == TRUE], bal_formula_window)

# ------------------------------------------------------------------ 1. traits for every eligible D, P and N politician
pos_all <- fread(file.path(data_dir, "rank", "position_tiers.csv"), na.strings = c("", "NA"))
edu <- fread(file.path(data_dir, "education_wide.csv"))
elected_rules <- c("federal_deputy", "senator", "local_deputy", "governor_major_state", "governor_other_state",
                   "governor_state_unknown", "mayor", "mayor_big_city", "city_council", "df_assembly_or_delegate")
first_year <- function(rows) rows[!is.na(year_start), .(y = min(year_start)), by = person_id]
fe <- first_year(pos_all[rule %in% elected_rules]); fp <- first_year(pos_all[dataset == "party_positions"])
fm <- unique(pos_all[dataset == "military_positions", person_id])
T <- copy(A)
ed_of <- function(col) as.numeric(edu[[col]][match(T$pid, edu$person_id)] %in% 1)
T[, `:=`(n_posts = expm1(lrec), n_ties = expm1(ldeg),
         prev_designee = as.numeric(prior_status == "prev_winner"), prev_loser = as.numeric(prior_status == "prev_loser"),
         pretrend = as.numeric(pre - earlier),
         born_df = as.numeric(nodes$birth_state[match(pid, nodes$person_id)] %in% "Federal District"),
         graduate = pmax(ed_of("masters"), ed_of("phd")), law = ed_of("law"), economics = ed_of("economics"),
         elected = as.numeric(fe$y[match(pid, fe$person_id)] <= election - 2L),
         party = as.numeric(fp$y[match(pid, fp$person_id)] <= election - 2L),
         military = as.numeric(pid %in% fm))]
T[is.na(elected), elected := 0]; T[is.na(party), party := 0]
rank_e2 <- annual[data.table(pid = T$pid, year = T$election - 2L), on = .(pid, year), rank]
T[, holds_e2 := as.numeric(!is.na(rank_e2) & rank_e2 > 0)]
T[, cabinet := 0]
for (e in elections) T[election == e, cabinet := as.numeric(highest_rank(pid, 0L, e - 2L) >= 8L)]
# ties with the own contender (followers only)
tie_pairs <- unique(rbind(dated[edge_type %in% tie_types, .(pid = person_a, candidate = person_b, edge_type, year_start)],
                          dated[edge_type %in% tie_types, .(pid = person_b, candidate = person_a, edge_type, year_start)]))
pt <- merge(T[group != "N", .(pid, candidate = patron, election)], tie_pairs, by = c("pid", "candidate"), allow.cartesian = TRUE)
pt <- pt[year_start <= election - tie_lag]
ts <- pt[, .(first_tie = min(year_start), cowork = as.numeric(any(edge_type == "co_work"))), by = .(pid, election)]
T[ts, on = .(pid, election), `:=`(tie_years = election - 2L - i.first_tie, tie_cowork = i.cowork)]

traits <- rbindlist(list(
  list("age",          "Age in the election year",                          "in",  1L),
  list("pre",          "Highest rank, $e-5$ to $e-2$",                      "in",  1L),
  list("earlier",      "Highest rank, $e-9$ to $e-6$ (0 if none)",          "in",  1L),
  list("n_posts",      "Ranked posts by $e-2$",                             "in",  1L),
  list("n_ties",       "Ties by $e-2$",                                     "in",  1L),
  list("prev_designee","Tied to the previous designee",                     "in",  2L),
  list("prev_loser",   "Tied to a losing contender of the previous succession", "in", 2L),
  list("fed_exec",     "Federal executive post, $e-5$ to $e-2$",            "in",  2L),
  list("holds_e2",     "Holds a ranked post in $e-2$",                      "out", 2L),
  list("cabinet",      "Cabinet-level post (rank $\\geq 8$) by $e-2$",      "out", 2L),
  list("elected",      "Elected office by $e-2$",                           "out", 2L),
  list("party",        "Party post by $e-2$",                               "out", 2L),
  list("born_df",      "Born in Mexico City",                               "out", 2L),
  list("law",          "Law degree",                                        "out", 2L),
  list("economics",    "Economics degree",                                  "out", 2L),
  list("graduate",     "Graduate degree",                                   "out", 2L),
  list("military",     "Military career",                                   "out", 2L),
  list("tie_years",    "Years since the tie to the contender formed",       "out", 1L),
  list("tie_cowork",   "Tie with the contender is co-work",                 "out", 2L)))
setnames(traits, c("column", "label", "block", "digits"))

# ------------------------------------------------------------------ 2. followers: designee's vs losers'
F <- T[group != "N"]
setkey(F, election, pid); setkey(sample, election, pid)
stopifnot(identical(F$pid, sample$pid), identical(F$election, sample$election))
F[, treated := as.integer(group == "D")]
Xb <- as.matrix(F[, traits$column, with = FALSE])
d_fe <- build_design(formula = ~ election_factor)
stopifnot(length(d_fe$rows) == nrow(F))
bt <- estimate_columns(d_fe, Xb, B = B_boot, seed = seed)$table
pcol <- grep("^p", names(bt), value = TRUE)[1]
fol <- rbindlist(lapply(traits$column, function(v) {
  x <- F[[v]]; tr <- F$treated; e <- F$election
  within <- mean(sapply(elections, function(el) mean(x[tr == 1 & e == el]) - mean(x[tr == 0 & e == el])))
  sdp <- sqrt((var(x[tr == 1]) + var(x[tr == 0])) / 2)
  data.table(column = v, mean_D = mean(x[tr == 1]), mean_P = mean(x[tr == 0]), diff_within = within,
             norm_diff = within / sdp, p = bt[[pcol]][match(v, bt$column)])
}))

# ------------------------------------------------------------------ 3. followers vs reweighted unaligned
un <- rbindlist(lapply(traits$column, function(v) {
  if (v %in% c("tie_years", "tie_cowork")) return(data.table(column = v, mean_N = NA_real_, mean_Nw = NA_real_, norm_diff_N = NA_real_))
  x <- T[[v]]; folr <- T$group != "N"; nn <- T$group == "N"
  sdp <- sqrt((var(x[folr]) + var(x[nn])) / 2)
  sn <- S_main$group == "N"
  xs <- x[match(paste(S_main$pid[sn], S_main$election[sn]), paste(T$pid, T$election))]   # trait values of the weighted unaligned
  nf <- S_main[follower == 1L, .N, by = election]; ws <- S_main$w[sn] * nf$N[match(S_main$election[sn], nf$election)]
  wm <- sum(ws * xs) / sum(ws)
  data.table(column = v, mean_N = mean(x[nn]), mean_Nw = wm, norm_diff_N = (mean(x[folr]) - wm) / sdp)
}))
out <- merge(merge(traits, fol, by = "column", sort = FALSE), un, by = "column", sort = FALSE)[match(traits$column, column)]
fwrite(out, file.path(out_dir, "balance_combined.csv"))

# ------------------------------------------------------------------ 4. table
fmt <- function(x, d) { if (is.na(x)) return("--"); if (abs(x) < 0.5 * 10^(-d)) x <- 0; s <- formatC(x, format = "f", digits = d); sub("^-", "$-$", s) }
row <- function(r) sprintf("%s & %s & %s & %s & %s & %s & %s \\\\", r$label, fmt(r$mean_D, r$digits), fmt(r$mean_P, r$digits),
                           fmt(r$norm_diff, 2), fmt(r$p, 2), fmt(r$mean_Nw, r$digits), fmt(r$norm_diff_N, 2))
nD <- sum(F$treated); nP <- sum(F$treated == 0); nN <- sum(S_main$group == "N")
lines <- c("% balance_combined.tex -- balance of predetermined traits (balance_combined.R). Followers: raw means, normalized",
           "% within-succession difference and bootstrap p. Unaligned: entropy-balanced within succession to the followers' means.",
           "\\begin{tabular}{lrrrrrr}", "\\toprule",
           " & \\multicolumn{4}{c}{Designee's vs losing contenders' followers} & \\multicolumn{2}{c}{Followers vs unaligned} \\\\",
           "\\cmidrule(lr){2-5}\\cmidrule(lr){6-7}",
           " & Designee's & Losers' & Norm. diff. & $p$ & Unaligned, & Norm. diff. \\\\",
           " & followers & followers & & & reweighted & \\\\", "\\midrule")
for (i in which(out$block == "in")) lines <- c(lines, row(out[i]))
lines <- c(lines, "\\addlinespace[2pt]")          # a slight gap, no rule, between the estimation's covariates and the rest
for (i in which(out$block == "out")) lines <- c(lines, row(out[i]))
lines <- c(lines, "\\midrule", sprintf("Politician-successions & %s & %s & & & %s & \\\\", format(nD, big.mark = ","), format(nP, big.mark = ","), format(nN, big.mark = ",")),
           "\\bottomrule", "\\end{tabular}")
writeLines(lines, file.path(tab_dir, "balance_combined.tex"))
mx <- function(v) max(abs(v), na.rm = TRUE)
mac <- c("% balance_combined_macros.tex (balance_combined.R). Do not edit by hand.",
         sprintf("\\newcommand{\\BalMaxNormDiff}{%s}", formatC(mx(out$norm_diff), format = "f", digits = 2)),
         sprintf("\\newcommand{\\BalMinP}{%s}", formatC(min(out$p, na.rm = TRUE), format = "f", digits = 2)),
         sprintf("\\newcommand{\\BalMaxNormDiffUnaligned}{%s}", formatC(mx(out$norm_diff_N), format = "f", digits = 2)),
         sprintf("\\newcommand{\\BalUnalignedN}{%s}", format(nN, big.mark = ",")))
writeLines(mac, file.path(tab_dir, "balance_combined_macros.tex"))
cat("balance_combined:", nD, "designee's,", nP, "losers',", nN, "reweighted unaligned; max |norm diff| followers",
    formatC(mx(out$norm_diff), digits = 2, format = "f"), "unaligned", formatC(mx(out$norm_diff_N), digits = 2, format = "f"), "\n")
print(out[, .(label, mean_D, mean_P, norm_diff, p, mean_Nw, norm_diff_N)], digits = 3)
