# Turnover of the political elite around each succession (29 October 2026). Raw levels over every politician in
# the biographies: those in a ranked post two years before the election (the eligible pool, aligned or not) and
# where they stand in years e+1..e+4; and, among those in a ranked post or a top post (score >= 7) in e+2, the
# share who held no ranked post at e-2 (entrants). Context for the raw DiD: every group falls after the
# succession because the baseline conditions on being in office; the gains go to entrants. Writes
# turnover_by_succession.csv and tables/turnover_macros.tex. Run after estimate_main.R:
#   Rscript code/04-analysis/main_direct_tie/turnover.R
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
invisible(capture.output(source(file.path(script_dir, "estimate_main.R"))))
suppressPackageStartupMessages(library(data.table))

TOP <- 7L
rk <- function(ids, yr) { z <- annual[data.table(pid = ids, year = yr), on = .(pid, year), rank]; z[is.na(z)] <- 0L; z }
all_ids <- unique(annual$pid)
res <- rbindlist(lapply(elections, function(e) {
  pre <- rk(all_ids, e - 2L)
  post <- rowMeans(sapply(1:4, function(k) rk(all_ids, e + k)))
  post_off <- rowMeans(sapply(1:4, function(k) rk(all_ids, e + k) > 0))
  inpre <- pre > 0
  age <- e - as.numeric(birth[as.character(all_ids)])
  top2 <- rk(all_ids, e + 2L) >= TOP; off2 <- rk(all_ids, e + 2L) > 0
  data.table(election = e,
             n_in_office_pre = sum(inpre), mean_rank_pre = mean(pre[inpre]), mean_rank_post = mean(post[inpre]),
             share_still_in_office = mean(post_off[inpre]), share_rank_fell = mean(post[inpre] < pre[inpre]),
             share_rank_rose = mean(post[inpre] > pre[inpre]),
             n_in_office_e2 = sum(off2), entrants_share_office_e2 = mean(!inpre[off2]),
             n_top_e2 = sum(top2), entrants_share_top_e2 = mean(!inpre[top2]),
             top_e2_held_top_pre = mean(pre[top2] >= TOP), top_e2_mean_age = mean(age[top2], na.rm = TRUE))
}))
fwrite(res, file.path(out_dir, "turnover_by_succession.csv"))
avg <- res[, lapply(.SD[, -1], mean)]
print(res[, lapply(.SD, function(x) if (is.numeric(x)) round(x, 2) else x)])
cat("\naverages over the nine successions:\n"); print(avg[, lapply(.SD, round, 2)])

tab_dir <- file.path(out_dir, "tables"); dir.create(tab_dir, showWarnings = FALSE)
mac <- function(n, v) sprintf("\\newcommand{\\%s}{%s}", n, v)
pct <- function(x) round(100 * x)
writeLines(c("% turnover_macros.tex (turnover.R): elite turnover around the succession, averages over the nine successions. Do not edit by hand.",
             mac("TURNinOfficePre", round(avg$n_in_office_pre)), mac("TURNrankPre", formatC(avg$mean_rank_pre, format = "f", digits = 1)),
             mac("TURNrankPost", formatC(avg$mean_rank_post, format = "f", digits = 1)),
             mac("TURNstillInOffice", pct(avg$share_still_in_office)), mac("TURNfell", pct(avg$share_rank_fell)), mac("TURNrose", pct(avg$share_rank_rose)),
             mac("TURNinOfficeAfter", round(avg$n_in_office_e2)), mac("TURNentrantsOffice", pct(avg$entrants_share_office_e2)),
             mac("TURNtopAfter", round(avg$n_top_e2)), mac("TURNentrantsTop", pct(avg$entrants_share_top_e2)),
             mac("TURNtopHeldTopPre", pct(avg$top_e2_held_top_pre))),
           file.path(tab_dir, "turnover_macros.tex"))
