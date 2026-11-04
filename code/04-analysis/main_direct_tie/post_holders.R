# Who holds the senior posts before and after each succession (4 November 2026). Shanker's question on the raw-means
# figure: the mean rank falls after the handover in every group of the pool, so who takes the posts? The pool is a
# cohort fixed at e-2 (a ranked post in e-5..e-2, aged 25-75, no contender), so the posts its members leave go to
# politicians who were not in it. For every year we take every politician in Camp's data holding a senior post (rung 7
# or above, the level Camp's inclusion criterion counts) or any ranked post, and classify him by his status at e-2:
# designee's follower, losers' follower, unaligned in the pool, a contender, or outside the pool (entrants, whose first
# ranked post comes after e-2, and others: a post before e-5 but none in e-5..e-2, or ineligible by age). Shares of
# person-years by status at e-2 and over years 1-4, averaged over the nine successions with equal weight, and the
# number of posts per year. Run inside the deck's staging environment:
#   Rscript code/04-analysis/main_direct_tie/post_holders.R
# Writes post_holders.csv, tables/post_holders.tex and tables/post_holders_macros.tex.
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
invisible(capture.output(source(file.path(script_dir, "estimate_main.R"))))
source(file.path(script_dir, "design_tools.R"))
invisible(capture.output(source(file.path(script_dir, "rp_setup.R"))))   # A: the pool with groups D, P, N
tab_dir <- file.path(out_dir, "tables"); dir.create(tab_dir, showWarnings = FALSE)

first_ranked <- annual[rank >= 1L, .(first = min(year)), by = pid]
status_levels <- c("D", "P", "N", "multi", "contender", "entrant", "other")
labels <- c(D = "Designee's followers", P = "Losers' followers", N = "Unaligned, in the pool",
            multi = "Tied to two or more contenders, excluded", contender = "The contenders",
            entrant = "Entrants, first ranked post after $e-2$", other = "Others outside the pool")
# politicians tied to two or more contenders of succession e by e-2 (the design keeps only those tied to exactly one)
multi_tied <- function(e) {
  cand <- slates[[as.character(e)]]$candidates
  ct <- unique(long_ties[candidate %in% cand & year_start <= e - tie_lag, .(pid, candidate)])
  ct[, .N, by = pid][N >= 2L, pid]
}

classify <- function(e, ids) {
  pool <- A[election == e]
  st <- pool$group[match(ids, pool$pid)]
  cand <- slates[[as.character(e)]]$candidates
  st[is.na(st) & ids %in% multi_tied(e)] <- "multi"
  st[is.na(st) & ids %in% cand] <- "contender"
  fr <- first_ranked$first[match(ids, first_ranked$pid)]
  st[is.na(st) & !is.na(fr) & fr > e - 2L] <- "entrant"
  st[is.na(st)] <- "other"
  factor(st, levels = status_levels)
}

shares <- rbindlist(lapply(elections, function(e) {
  rbindlist(lapply(c(7L, 1L), function(thr) {
    rbindlist(lapply(c(e - 2L, (e + 1L):(e + 4L)), function(y) {
      h <- annual[year == y & rank >= thr]
      st <- classify(e, h$pid)
      data.table(election = e, threshold = thr, year = y, k = y - e, posts = nrow(h),
                 status = status_levels, share = as.numeric(table(st)[status_levels]) / nrow(h))
    }))
  }))
}))
shares[, window := fifelse(k == -2L, "before", "after")]
win <- shares[, .(share = mean(share), posts = mean(posts)), by = .(election, threshold, window, status)]   # years 1-4 averaged
agg <- win[, .(share = mean(share), posts = mean(posts)), by = .(threshold, window, status)]              # equal weight per succession
wide <- dcast(agg, threshold + status ~ window, value.var = "share")
wide[, change_pp := 100 * (after - before)]
wide[, status := factor(status, levels = status_levels)]; setorder(wide, threshold, status)
posts <- dcast(agg[status == "D"], threshold ~ window, value.var = "posts")
fwrite(shares, file.path(out_dir, "post_holders.csv"))
fwrite(wide, file.path(out_dir, "post_holders_summary.csv"))

pct <- function(x) formatC(100 * x, format = "f", digits = 0)
pp <- function(x) { s <- formatC(x, format = "f", digits = 0); if (x > 0.5) paste0("$+$", s) else if (x < -0.5) paste0("$-$", sub("^-", "", s)) else "--" }
rows <- function(thr) {
  w <- wide[threshold == thr]
  c(sprintf("%s & %s & %s & %s \\\\", labels[as.character(w$status)], pct(w$before), pct(w$after), sapply(w$change_pp, pp)),
    sprintf("Posts per year & %s & %s & \\\\", formatC(posts[threshold == thr, before], format = "f", digits = 0, big.mark = ","),
            formatC(posts[threshold == thr, after], format = "f", digits = 0, big.mark = ",")))
}
lines <- c("% post_holders.tex (post_holders.R). Shares of posts held by each status at e-2, averaged over the nine successions.",
           "\\begin{tabular}{lrrr}", "\\toprule",
           " & \\multicolumn{3}{c}{Share of the posts (\\%)} \\\\", "\\cmidrule(lr){2-4}",
           "Status at $e-2$ & Year $e-2$ & Years 1--4 & Change (pp) \\\\", "\\midrule",
           "\\multicolumn{4}{l}{\\textit{Senior posts, rung 7 and above}} \\\\", rows(7L), "\\addlinespace[3pt]",
           "\\multicolumn{4}{l}{\\textit{Any ranked post}} \\\\", rows(1L), "\\bottomrule", "\\end{tabular}")
writeLines(lines, file.path(tab_dir, "post_holders.tex"))
mac <- c("% post_holders_macros.tex (post_holders.R). Do not edit by hand.")
for (thr in c(7L, 1L)) for (st in status_levels) {
  w <- wide[threshold == thr & status == st]; key <- paste0("PH", if (thr == 7L) "top" else "any", st)
  mac <- c(mac, sprintf("\\newcommand{\\%sBefore}{%s}", key, pct(w$before)), sprintf("\\newcommand{\\%sAfter}{%s}", key, pct(w$after)))
}
mac <- c(mac, sprintf("\\newcommand{\\PHtopPostsBefore}{%s}", formatC(posts[threshold == 7L, before], format = "f", digits = 0)),
         sprintf("\\newcommand{\\PHtopPostsAfter}{%s}", formatC(posts[threshold == 7L, after], format = "f", digits = 0)))
pool_share <- function(thr, w) sum(wide[threshold == thr & status %in% c("D", "P", "N", "multi"), get(w)])
mac <- c(mac, sprintf("\\newcommand{\\PHtopPoolBefore}{%s}", pct(pool_share(7L, "before"))),
         sprintf("\\newcommand{\\PHtopPoolAfter}{%s}", pct(pool_share(7L, "after"))),
         sprintf("\\newcommand{\\PHanyPoolBefore}{%s}", pct(pool_share(1L, "before"))),
         sprintf("\\newcommand{\\PHanyPoolAfter}{%s}", pct(pool_share(1L, "after"))),
         sprintf("\\newcommand{\\PHtopPostsGrowth}{%s}", formatC(100 * (posts[threshold == 7L, after] / posts[threshold == 7L, before] - 1), format = "f", digits = 0)))
writeLines(mac, file.path(tab_dir, "post_holders_macros.tex"))

# Why are senior-post holders at e-2 outside the pool? (diagnostic) ages from the nodes file, contenders of any succession
all_cand <- unique(unlist(lapply(slates, `[[`, "candidates")))
diag <- rbindlist(lapply(elections, function(e) {
  h <- annual[year == e - 2L & rank >= 7L]
  st <- classify(e, h$pid)
  o <- h[st == "other"]
  by <- nodes$birth_year[match(o$pid, nodes$person_id)]
  age <- e - by
  reason <- fifelse(is.na(by), "no birth year",
            fifelse(age < 25L | age > 75L, "age outside 25-75",
            fifelse(o$pid %in% all_cand, "contender in another succession", "other")))
  data.table(election = e, n_other = nrow(o), reason = reason)[, .N, by = .(election, n_other, reason)]
}))
fwrite(diag, file.path(out_dir, "post_holders_other_reasons.csv"))
print(diag[, .(N = sum(N)), by = reason][, share := round(100 * N / sum(N))][])
print(wide[, .(threshold, status, before = round(100 * before, 1), after = round(100 * after, 1), change_pp = round(change_pp, 1))])
print(posts)
