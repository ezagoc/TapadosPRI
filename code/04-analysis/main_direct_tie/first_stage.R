# First stage (4 November 2026, after a seminar comment): does the new president appoint the designee's followers?
# Before the career premium (the reduced form) the deck must show that the treatment operated through its channel: the
# designee, once president, places his followers in the federal executive, and the losing contenders' followers do not get
# those appointments. Outcome by relative year k: an indicator that the politician STARTS a new ranked post in year e+k
# (position record with year_start = e+k), in the federal executive (govt_positions, not state or local; the channel
# of presidential appointment power) and at the top of the ladder (rung 7 or above). The new cabinet is named on
# 1 December of e, so the appointment years are e and e+1.
#   1. Event study of the yearly indicator, designee's minus losers' followers, event-study covariates (formula_es),
#      Ferman-Pinto inference with shared draws (design_tools.R). Levels, not changes: the pre-years are the placebo.
#   2. The appointment window e..e+1 with the main covariates (formula_x): federal executive, top post, cabinet level
#      (rung 8+), any ranked post; and the previous handover (e-6..e-5) as a placebo window.
#   3. Levels by group for e..e+1: designee's followers, losers' followers, the unaligned reweighted as in the reward /
#      penalty design (rp_setup.R), successions weighted as in the estimator.
# Writes first_stage_event_study.csv, first_stage_window.csv, first_stage_levels.csv, the figure first_stage_fed.{pdf,png}
# (house style) and tables/first_stage_macros.tex. Run after estimate_main.R, inside the staging environment:
#   Rscript code/04-analysis/main_direct_tie/first_stage.R
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
invisible(capture.output(source(file.path(script_dir, "estimate_main.R"))))
source(file.path(script_dir, "design_tools.R"))
invisible(capture.output(source(file.path(script_dir, "rp_setup.R"))))
tab_dir <- file.path(out_dir, "tables"); dir.create(tab_dir, showWarnings = FALSE)
B_fs <- 20000L; seed_fs <- 4112026L

pt <- fread(file.path(data_dir, "rank", "position_tiers.csv"), na.strings = c("", "NA"))
pt <- pt[!is.na(year_start) & !is.na(hybrid_rank)]
pt[, `:=`(y0 = as.integer(year_start), rung = pmin(as.integer(floor(hybrid_rank)), 11L))]
fed <- pt[dataset == "govt_positions" & !grepl("^state_|^governor|^mayor|city_council|^local", rule)]
top <- pt[rung >= 7L]; cab <- pt[rung >= 8L]
starts <- function(tab, ids, years) paste(ids, years) %in% paste(tab$person_id, tab$y0)
started_in <- function(tab, ids, e, k0, k1) Reduce(`|`, lapply(k0:k1, function(k) starts(tab, ids, e + k)))

# ------------------------------------------------------------------ 1. event study of new appointments, D - P
ks <- -7:8
Yfed <- sapply(ks, function(k) as.numeric(starts(fed, sample$pid, sample$election + k))); colnames(Yfed) <- paste0("fed_", ks)
Ytop <- sapply(ks, function(k) as.numeric(starts(top, sample$pid, sample$election + k))); colnames(Ytop) <- paste0("top_", ks)
d_es <- build_design(formula = formula_es)
stopifnot(identical(d_es$rows, seq_len(nrow(sample))))
es <- estimate_columns(d_es, cbind(Yfed, Ytop), B = B_fs, seed = seed_fs)$table
es[, `:=`(outcome = sub("_.*", "", column), k = as.integer(sub(".*_", "", column)))]
fwrite(es, file.path(out_dir, "first_stage_event_study.csv"))
cat("New appointment in year e+k, designee's minus losers' followers (pp):\n")
print(dcast(es[, .(outcome, k, pp = round(100 * estimate, 1))], k ~ outcome, value.var = "pp"))

# ------------------------------------------------------------------ 2. the appointment window e..e+1 and the previous handover
d_x <- build_design()
W <- cbind(any_01 = started_in(pt, sample$pid, sample$election, 0L, 1L), fed_01 = started_in(fed, sample$pid, sample$election, 0L, 1L),
           top_01 = started_in(top, sample$pid, sample$election, 0L, 1L), cab_01 = started_in(cab, sample$pid, sample$election, 0L, 1L),
           any_prev = started_in(pt, sample$pid, sample$election, -6L, -5L), fed_prev = started_in(fed, sample$pid, sample$election, -6L, -5L)) * 1
win <- estimate_columns(d_x, W, B = B_fs, seed = seed_fs)$table
fwrite(win, file.path(out_dir, "first_stage_window.csv"))
cat("\nAppointment window e..e+1 (and the previous handover e-6..e-5), designee's minus losers' followers (pp), main covariates:\n")
print(win[, .(column, pp = round(100 * estimate, 1), lo = round(100 * ci_lower, 1), hi = round(100 * ci_upper, 1), p = round(p_bootstrap, 3))])

# ------------------------------------------------------------------ 3. levels by group, the unaligned reweighted
S <- make_weights(A[support == TRUE], bal_formula_window)
S[, wt := fifelse(group == "N", w, 1)]
lv <- rbindlist(lapply(elections, function(e) {
  d <- S[election == e]
  d[, `:=`(any_01 = started_in(pt, pid, e, 0L, 1L), fed_01 = started_in(fed, pid, e, 0L, 1L), top_01 = started_in(top, pid, e, 0L, 1L),
           cab_01 = started_in(cab, pid, e, 0L, 1L), any_prev = started_in(pt, pid, e, -6L, -5L), fed_prev = started_in(fed, pid, e, -6L, -5L))]
  d[, .(any_01 = weighted.mean(any_01, wt), fed_01 = weighted.mean(fed_01, wt), top_01 = weighted.mean(top_01, wt), cab_01 = weighted.mean(cab_01, wt),
        any_prev = weighted.mean(any_prev, wt), fed_prev = weighted.mean(fed_prev, wt), n = .N), by = group][, election := e]
}))
levels <- lv[, .(any_01 = sum(omega[as.character(election)] * any_01), fed_01 = sum(omega[as.character(election)] * fed_01),
                 top_01 = sum(omega[as.character(election)] * top_01), cab_01 = sum(omega[as.character(election)] * cab_01),
                 any_prev = sum(omega[as.character(election)] * any_prev), fed_prev = sum(omega[as.character(election)] * fed_prev)), by = group][order(group)]
fwrite(levels, file.path(out_dir, "first_stage_levels.csv"))
cat("\nShare starting a new post in e..e+1 by group (successions weighted as in the estimator), %:\n")
print(levels[, lapply(.SD, function(x) if (is.numeric(x)) round(100 * x, 1) else x)])

# ------------------------------------------------------------------ figure: the federal-executive appointment event study
es_figure(es[outcome == "fed", .(k, estimate, ci_lower, ci_upper, ci90_lower, ci90_upper)],
          "New federal appointment that year (pp),\ndesignee's minus losers' followers", "first_stage_fed", scale = 100)
es_figure(es[outcome == "top", .(k, estimate, ci_lower, ci_upper, ci90_lower, ci90_upper)],
          "New top post that year (pp),\ndesignee's minus losers' followers", "first_stage_top", scale = 100)

# ------------------------------------------------------------------ macros
f1 <- function(x) formatC(x, format = "f", digits = 1); f0 <- function(x) formatC(x, format = "f", digits = 0)
g <- function(col, grp) 100 * levels[group == grp][[col]]
w <- function(col, what = "estimate") 100 * win[column == col][[what]]
mac <- function(n, v) sprintf("\\newcommand{\\%s}{%s}", n, v)
writeLines(c("% first_stage_macros.tex (first_stage.R). Shares and differences in percentage points. Do not edit by hand.",
  mac("FSfedD", f0(g("fed_01", "D"))), mac("FSfedP", f0(g("fed_01", "P"))), mac("FSfedN", f0(g("fed_01", "N"))),
  mac("FStopD", f0(g("top_01", "D"))), mac("FStopP", f0(g("top_01", "P"))), mac("FStopN", f0(g("top_01", "N"))),
  mac("FScabD", f0(g("cab_01", "D"))), mac("FScabP", f0(g("cab_01", "P"))), mac("FScabN", f0(g("cab_01", "N"))),
  mac("FSanyD", f0(g("any_01", "D"))), mac("FSanyP", f0(g("any_01", "P"))), mac("FSanyN", f0(g("any_01", "N"))),
  mac("FSprevD", f0(g("fed_prev", "D"))), mac("FSprevP", f0(g("fed_prev", "P"))),
  mac("FSfedEst", f1(w("fed_01"))), mac("FSfedLo", f1(w("fed_01", "ci_lower"))), mac("FSfedHi", f1(w("fed_01", "ci_upper"))), mac("FSfedPval", formatC(win[column == "fed_01", p_bootstrap], format = "f", digits = 3)),
  # the gap relative to the losers' followers' share (percent increase over the baseline), 5 Nov 2026
  mac("FSfedRel", f0(100 * w("fed_01") / g("fed_01", "P"))), mac("FStopRel", f0(100 * w("top_01") / g("top_01", "P"))), mac("FScabRel", f0(100 * w("cab_01") / g("cab_01", "P"))),
  mac("FStopEst", f1(w("top_01"))), mac("FStopLo", f1(w("top_01", "ci_lower"))), mac("FStopHi", f1(w("top_01", "ci_upper"))),
  mac("FScabEst", f1(w("cab_01"))), mac("FScabLo", f1(w("cab_01", "ci_lower"))), mac("FScabHi", f1(w("cab_01", "ci_upper"))),
  mac("FSanyEst", f1(w("any_01"))), mac("FSanyLo", f1(w("any_01", "ci_lower"))), mac("FSanyHi", f1(w("any_01", "ci_upper"))),
  mac("FSprevEst", f1(w("fed_prev"))), mac("FSprevLo", f1(w("fed_prev", "ci_lower"))), mac("FSprevHi", f1(w("fed_prev", "ci_upper"))),
  mac("FSfedPeak", f1(100 * max(es[outcome == "fed" & k %in% 0:1, estimate]))), mac("FSfedPeakYear", es[outcome == "fed" & k %in% 0:1][which.max(estimate), k])),
  file.path(tab_dir, "first_stage_macros.tex"))
cat("\nfirst stage done\n")
