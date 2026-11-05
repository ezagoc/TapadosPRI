# The size of the jump (4 November 2026, Shanker's framing: for most posts nothing changes, and where it does the move is
# one rung, not a leap). Outcome categories of the change in the highest rank from e-5..e-2 to e+1..e+4 (the main
# window): demoted or out, unchanged, up one rung, up two, up three or more (exhaustive, they add to 100). Each as an indicator in the
# main design (designee's minus losers' followers, event-study covariates, Ferman-Pinto draws), for all followers and
# for the followers whose baseline rung was 5-7 (deputy director general to undersecretary, where the threshold figure
# puts the reward). Raw shares by group alongside. Writes jump_sizes.csv, tables/jump_sizes.tex, tables/jump_sizes_macros.tex.
# Run inside the staging environment: Rscript code/04-analysis/main_direct_tie/jump_sizes.R
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
invisible(capture.output(source(file.path(script_dir, "estimate_main.R"))))
source(file.path(script_dir, "design_tools.R"))
tab_dir <- file.path(out_dir, "tables"); dir.create(tab_dir, showWarnings = FALSE)
jump <- sample$post - sample$pre
Y <- cbind(demoted = jump <= -1L, same = jump == 0L, up_one = jump == 1L, up_two = jump == 2L, up_three = jump >= 3L) * 1
stopifnot(all(rowSums(Y) == 1))
labels <- c(demoted = "Demoted or out of office", same = "Same rung", up_one = "Up one rung", up_two = "Up two rungs", up_three = "Up three rungs or more")
groups <- list(all = list(keep = rep(TRUE, nrow(sample)), label = "All followers"),
               mid = list(keep = sample$pre %in% 5:7, label = "Baseline rungs 5--7 (deputy director general to undersecretary)"),
               low = list(keep = sample$pre <= 4L, label = "Baseline rung 4 or below"),
               top = list(keep = sample$pre >= 8L, label = "Baseline rungs 8--9"))
res <- rbindlist(lapply(names(groups), function(g) {
  keep <- groups[[g]]$keep
  d <- build_design(keep = keep, formula = formula_es)
  t <- estimate_columns(d, Y[d$rows, , drop = FALSE], B = 20000L, seed = 4112026L)$table
  raw <- data.table(column = colnames(Y), D = 100 * colMeans(Y[keep & sample$treated == 1L, , drop = FALSE]),
                    P = 100 * colMeans(Y[keep & sample$treated == 0L, , drop = FALSE]))
  merge(raw, t[, .(column, estimate = 100 * estimate, ci_lower = 100 * ci_lower, ci_upper = 100 * ci_upper, p_bootstrap)], by = "column")[
    , `:=`(group = g, group_label = groups[[g]]$label, n_D = sum(keep & sample$treated == 1L), n_P = sum(keep & sample$treated == 0L))][match(colnames(Y), column)]
}))
# among the promoted, the share whose jump was exactly one rung (raw); total variation distance between the two outcome
# distributions = the smallest share of followers whose outcomes must differ (the rest can be matched one to one)
one_among <- sample[jump >= 1L, .(share_one = mean(jump == 1L)), by = treated]
tv <- res[group == "all", 0.5 * sum(abs(D - P))]; tv_adj <- res[group == "all", 0.5 * sum(abs(estimate))]
fwrite(res, file.path(out_dir, "jump_sizes.csv"))
f1 <- function(x) { v <- round(x, 1); s <- formatC(abs(v), format = "f", digits = 1); ifelse(v < 0, paste0("$-$", s), s) }
f0 <- function(x) { v <- round(x); s <- formatC(abs(v), format = "d"); ifelse(v < 0, paste0("$-$", s), s) }
ci <- function(lo, hi) sprintf("[%s, %s]", f1(lo), f1(hi))
lines <- c("% jump_sizes.tex (jump_sizes.R). Share of followers by the size of the move in highest rank, e-5..e-2 to e+1..e+4; DiD in pp. Do not edit by hand.",
           "\\begin{tabular}{lrrrc}", "\\toprule", " & \\multicolumn{2}{c}{Share of followers (\\%)} & \\multicolumn{2}{c}{Designee's $-$ losers' (pp)} \\\\",
           "\\cmidrule(lr){2-3}\\cmidrule(lr){4-5}", "Move in highest rank & designee's & losers' & estimate & 95\\% interval \\\\", "\\midrule")
for (g in c("all", "mid")) {
  r <- res[group == g]
  lines <- c(lines, sprintf("\\multicolumn{5}{l}{\\textit{%s, %d and %d followers}} \\\\", groups[[g]]$label, r$n_D[1], r$n_P[1]))
  for (i in seq_len(nrow(r))) lines <- c(lines, sprintf("%s & %s & %s & %s & %s \\\\", labels[r$column[i]], f0(r$D[i]), f0(r$P[i]), f1(r$estimate[i]), ci(r$ci_lower[i], r$ci_upper[i])))
  if (g == "all") lines <- c(lines, "\\addlinespace[3pt]")
}
lines <- c(lines, "\\bottomrule", "\\end{tabular}")
writeLines(lines, file.path(tab_dir, "jump_sizes.tex"))
mac <- function(n, v) sprintf("\\newcommand{\\%s}{%s}", n, v)
g <- function(grp, col, what) res[group == grp & column == col][[what]]
m <- c("% jump_sizes_macros.tex (jump_sizes.R). Do not edit by hand.")
for (grp in c("all", "mid")) for (col in colnames(Y)) {
  key <- paste0("JS", if (grp == "all") "" else "Mid", gsub("_", "", col))
  m <- c(m, mac(paste0(key, "D"), f0(g(grp, col, "D"))), mac(paste0(key, "P"), f0(g(grp, col, "P"))),
         mac(paste0(key, "DiD"), f1(g(grp, col, "estimate"))), mac(paste0(key, "Lo"), f1(g(grp, col, "ci_lower"))), mac(paste0(key, "Hi"), f1(g(grp, col, "ci_upper"))))
}
m <- c(m, mac("JSoneAmongPromotedD", f0(100 * one_among[treated == 1L, share_one])), mac("JSoneAmongPromotedP", f0(100 * one_among[treated == 0L, share_one])),
       mac("JSmidND", res[group == "mid", n_D][1]), mac("JSmidNP", res[group == "mid", n_P][1]),
       mac("JStvRaw", f0(tv)), mac("JStvAdj", f0(tv_adj)), mac("JSoneInRaw", round(100 / tv)), mac("JSoneInAdj", round(100 / tv_adj)),
       mac("JSmidUpDiD", f1(res[group == "mid" & column %in% c("up_one", "up_two", "up_three"), sum(estimate)])),
       mac("JSmidUpD", f0(res[group == "mid" & column %in% c("up_one", "up_two", "up_three"), sum(D)])), mac("JSmidUpP", f0(res[group == "mid" & column %in% c("up_one", "up_two", "up_three"), sum(P)])))
writeLines(m, file.path(tab_dir, "jump_sizes_macros.tex"))
print(res[, .(group, column, D = round(D), P = round(P), DiD = round(estimate, 1), lo = round(ci_lower, 1), hi = round(ci_upper, 1), n_D, n_P)])
print(one_among); cat("total variation raw", tv, " adjusted", tv_adj, "\n")
