# The outcome's scale on one slide: the office ladder with the share of politicians at each score before the
# succession (highest score in e-5..e-2), for the eligible pool, the designee's followers and the losers' followers,
# pooled over the nine successions (politician-successions). Everything is read from the objects estimate_main.R
# builds (eligible, slates), nothing is re-estimated here. Writes tables/ladder_shares.{tex,csv} and
# tables/ladder_macros.tex to the output directory.
#   Rscript code/04-analysis/main_direct_tie/ladder_shares.R
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
invisible(capture.output(source(file.path(script_dir, "estimate_main.R"))))
tab_dir <- file.path(out_dir, "tables"); dir.create(tab_dir, showWarnings = FALSE)

offices <- c("10" = "President of the Republic",
             "9" = "Cabinet secretaries; heads of large state firms",
             "8" = "Major-state governors; PRI president; prestige ambassadors",
             "7" = "Undersecretaries; senators; Supreme Court justices",
             "6" = "Directors general; other governors; other ambassadors",
             "5" = "Deputy directors general; big-city mayors",
             "4" = "Area directors; federal deputies and judges",
             "3" = "Subdirectors; department heads; state legislators",
             "2" = "Mayors; advisers and staff; union officers",
             "1" = "Municipal councillors; local party officials")

pool <- rbindlist(lapply(names(eligible), function(e) {
  d <- copy(eligible[[e]])
  w <- slates[[e]]$winner
  d[, group := fifelse(n_direct == 1L & patron == w, "designee",
               fifelse(n_direct == 1L & !is.na(patron), "losers", "other"))]
  d[, .(election = as.integer(e), pid, pre, post, group)]
}))
# the president is the only post scored 11 in position_tiers (no post scores 10); the deck's ladder shows him as 10
pool[pre == 11L, pre := 10L]; pool[post == 11L, post := 10L]
stopifnot(all(pool$pre >= 1L), all(pool$pre <= 10L))
groups <- list(pool = pool, designee = pool[group == "designee"], losers = pool[group == "losers"])
shares <- rbindlist(lapply(names(groups), function(g) {
  d <- groups[[g]]
  data.table(group = g, score = 10:1,
             n = sapply(10:1, function(s) sum(d$pre == s)),
             share = sapply(10:1, function(s) 100 * mean(d$pre == s)),
             politicians = nrow(d), mean_pre = mean(d$pre), mean_post = mean(d$post))
}))
fwrite(shares, file.path(tab_dir, "ladder_shares.csv"))

cell <- function(g, s) { x <- shares[group == g & score == s, share]; if (x == 0) "--" else formatC(x, format = "f", digits = 1) }
lines <- c("% ladder_shares.tex -- the office ladder and where politicians sit on it before the succession (ladder_shares.R).",
           "% Shares of politician-successions whose highest score in e-5..e-2 is the row's score; pooled over the nine successions.",
           "\\begin{tabular}{c >{\\raggedright\\arraybackslash}p{6.4cm} rrr}", "\\toprule",
           " & & \\multicolumn{3}{c}{Highest score 2--5 years before the election (\\%)} \\\\", "\\cmidrule(lr){3-5}",
           "Score & Representative offices & All eligible & Designee's followers & Losers' followers \\\\", "\\midrule")
for (s in 10:1) lines <- c(lines, sprintf("%d & %s & %s & %s & %s \\\\", s, offices[[as.character(s)]], cell("pool", s), cell("designee", s), cell("losers", s)))
np <- function(g) format(shares[group == g, politicians][1], big.mark = ",")
mp <- function(g) formatC(shares[group == g, mean_pre][1], format = "f", digits = 1)
lines <- c(lines, "\\midrule",
           sprintf("\\multicolumn{2}{l}{Politician-successions} & %s & %s & %s \\\\", np("pool"), np("designee"), np("losers")),
           sprintf("\\multicolumn{2}{l}{Mean score} & %s & %s & %s \\\\", mp("pool"), mp("designee"), mp("losers")),
           "\\bottomrule", "\\end{tabular}")
writeLines(lines, file.path(tab_dir, "ladder_shares.tex"))
mac <- c("% ladder_macros.tex -- numbers of the office-ladder slide (ladder_shares.R). Do not edit by hand.",
         sprintf("\\newcommand{\\LadderPoolN}{%s}", np("pool")), sprintf("\\newcommand{\\LadderDesigneeN}{%s}", np("designee")),
         sprintf("\\newcommand{\\LadderLosersN}{%s}", np("losers")), sprintf("\\newcommand{\\LadderPoolMean}{%s}", mp("pool")),
         sprintf("\\newcommand{\\LadderDesigneeMean}{%s}", mp("designee")), sprintf("\\newcommand{\\LadderLosersMean}{%s}", mp("losers")))
writeLines(mac, file.path(tab_dir, "ladder_macros.tex"))
cat("ladder_shares: pool", np("pool"), "designee", np("designee"), "losers", np("losers"), "\n")
print(dcast(shares, score ~ group, value.var = "share")[order(-score)])
