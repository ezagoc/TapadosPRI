# Who holds the senior posts before and after each succession (4 November 2026). Shanker's question on the raw-means
# figure: the mean rank falls after the handover in every group of the pool, so who takes the posts? The pool is a
# cohort fixed at e-2 (a ranked post in e-5..e-2, aged 25-75, no contender), so the posts its members leave go to
# politicians who were not in it. For every year we take every politician in Camp's data holding a senior post (rung 7
# or above, the level Camp's inclusion criterion counts) or any ranked post, and classify him by his status at e-2:
# designee's follower, losers' follower, unaligned in the pool, a contender, or outside the pool (entrants, whose first
# ranked post comes after e-2, and others: a post before e-5 but none in e-5..e-2, or ineligible by age). Shares of
# person-years by status at e-2 and over years 1-4, averaged over the nine successions with equal weight, and the
# number of posts per year. Run inside the deck's staging environment:
#   Rscript slides/analysis/post_holders.R
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
            entrant = "Entrants, first ranked post after $e-2$", other = "Not eligible at $e-2$")
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

# Why are senior-post holders in e-5..e-1 outside the pool? Every case falls under one of the pool's rules: a contender of
# this or an earlier succession, age at e outside 25-75 or unknown, dead before e-1 (the death rule), or no ranked post
# in e-5..e-2 (only possible at e-1). Shares of those person-years by reason, pooled over successions and years.
all_contenders <- unique(contenders[, .(person_id, election_year)])
reasons <- rbindlist(lapply(elections, function(e) {
  pool <- A[election == e]; mt <- multi_tied(e)
  rbindlist(lapply((e - 5L):(e - 1L), function(y) {
    o <- annual[year == y & rank >= 7L, pid]; o <- o[!(o %in% pool$pid) & !(o %in% mt)]
    by <- birth[as.character(o)]; age <- e - as.numeric(by); dy <- death_lookup[as.character(o)]
    reason <- fifelse(o %in% all_contenders[election_year <= e, person_id], "contender",
              fifelse(is.na(by), "no_birth_year", fifelse(age < 25 | age > 75, "age",
              fifelse(!is.na(dy) & dy < e - 1L, "dead", fifelse(!(o %in% unique(annual[year >= e - 5L & year <= e - 2L, pid])), "no_post_in_window", "unexplained")))))
    data.table(election = e, k = y - e, reason = reason)
  }))
}))
stopifnot(!any(reasons$reason == "unexplained"))
rs <- reasons[, .N, by = reason][, share := N / sum(N)]
fwrite(rs, file.path(out_dir, "post_holders_outside_reasons.csv"))
mac <- readLines(file.path(tab_dir, "post_holders_macros.tex"))
for (r in c("contender", "no_birth_year", "age", "dead", "no_post_in_window")) {
  v <- rs[reason == r, share]; if (length(v) == 0L) v <- 0
  mac <- c(mac, sprintf("\\newcommand{\\PHoutside%s}{%s}", gsub("_", "", r), pct(v)))
}
mac <- c(mac, sprintf("\\newcommand{\\PHoutsideAgeOrUnknown}{%s}", pct(sum(rs[reason %in% c("age", "no_birth_year"), share]))))
writeLines(mac, file.path(tab_dir, "post_holders_macros.tex"))
print(rs[order(-N)])

# ------------------------------------------------------------------ figure: who holds the senior posts, year by year
# Stacked shares of the senior post-years (rung 7 and above) in years e-6..e+8, by the holder's status at e-2, with
# the pool in four slices (the unaligned; the other pool members: tied to two or more contenders, or a contender) and the
# outsiders split into newcomers (first ranked post after e-2) and others.
suppressPackageStartupMessages(library(ggplot2))
slice_of <- c(D = "Designee's followers", P = "Losers' followers", N = "Unaligned", multi = "Other pool members",
              contender = "Other pool members", entrant = "Newcomers, first ranked post after e-2", other = "Not eligible at e-2")
slice_levels <- c("Designee's followers", "Losers' followers", "Unaligned", "Other pool members", "Newcomers, first ranked post after e-2", "Not eligible at e-2")
yearly <- rbindlist(lapply(elections, function(e) {
  rbindlist(lapply(-6:8, function(k) {
    h <- annual[year == e + k & rank >= 7L]
    sl <- factor(slice_of[as.character(classify(e, h$pid))], levels = slice_levels)
    data.table(election = e, k = k, posts = nrow(h), slice = slice_levels, share = as.numeric(table(sl)[slice_levels]) / nrow(h))
  }))
}))
fig <- yearly[, .(share = mean(share), posts = mean(posts)), by = .(k, slice)]    # equal weight per succession
fig[, slice := factor(slice, levels = rev(slice_levels))]
fwrite(fig, file.path(out_dir, "post_holders_yearly.csv"))
fills <- c("Designee's followers" = INK, "Losers' followers" = MUTED, "Unaligned" = "#d9d9d9", "Other pool members" = "#a6a6a6",
           "Newcomers, first ranked post after e-2" = "#b2182b", "Not eligible at e-2" = "#f4a582")
mk <- data.table(x = c(-1.5, 0.5, 6.5), lab = c("Dedazo", "New president", "Next president"))
gph <- ggplot(fig, aes(k, 100 * share, fill = slice)) +
  geom_col(width = 0.82, colour = "white", linewidth = 0.3) +
  geom_vline(data = mk, aes(xintercept = x), colour = INK, linewidth = c(0.6, 0.35, 0.35), linetype = "dashed") +
  geom_text(data = mk, aes(x = x + 0.12, y = 104, label = lab), inherit.aes = FALSE, hjust = 0, vjust = 0, colour = INK, size = 4.2, family = FAM) +
  scale_fill_manual(values = fills, breaks = slice_levels, name = NULL) +
  scale_x_continuous(breaks = -6:8, labels = function(x) ifelse(x == 0, "e", sprintf("%+d", x))) +
  scale_y_continuous(breaks = seq(0, 100, 25), expand = expansion(mult = c(0, 0.12))) +
  labs(x = "Years relative to the election", y = "Share of the senior posts (%)") +
  guides(fill = guide_legend(nrow = 2, byrow = TRUE)) +
  theme_minimal(base_size = 16, base_family = FAM) +
  theme(panel.grid.minor = element_blank(), panel.grid.major.x = element_blank(), legend.position = "bottom",
        legend.text = element_text(size = 12, colour = INK), axis.title = element_text(size = 14, colour = INK),
        axis.text = element_text(colour = INK), plot.margin = margin(4, 8, 4, 4))
ggsave(file.path(out_dir, "post_holders.pdf"), gph, width = 10, height = 4.8, bg = "white", device = "pdf")
ggsave(file.path(out_dir, "post_holders.png"), gph, width = 10, height = 4.8, dpi = 250, bg = "white")
cat("post_holders figure written\n")
print(dcast(fig[k %in% c(-2, 0, 2, 4, 8)], slice ~ k, value.var = "share")[, lapply(.SD, function(x) if (is.numeric(x)) round(100 * x) else x)])

# ------------------------------------------------------------------ who the newcomers are (the user's question, 4 Nov)
# Newcomers with a senior post in years 1-4: ties of any type to the designee (the four design types by e-2, the stated
# family/mentorship/friendship ties from the biographies, any type at any date), ties to any contender, the designee's
# school, and the background Camp records before e-2 (military service, private or professional posts, union posts).
edu_tab <- read_data("education.csv"); oth_tab <- read_data("other_positions.csv")
lab_tab <- read_data("labor_positions.csv"); mil_tab <- read_data("military_positions.csv")
stated_types <- c("family", "mentorship", "personal", "family_surname")
edges_long <- rbindlist(list(edges[, .(pid = person_a, other = person_b, edge_type, year_start)],
                             edges[, .(pid = person_b, other = person_a, edge_type, year_start)]))
nc <- rbindlist(lapply(elections, function(e) {
  pool <- A[election == e]; cand <- slates[[as.character(e)]]$candidates; w <- slates[[as.character(e)]]$winner
  mt <- multi_tied(e)
  h <- unique(annual[year >= e + 1L & year <= e + 4L & rank >= 7L, pid])
  fr <- first_ranked$first[match(h, first_ranked$pid)]
  ids <- h[!(h %in% pool$pid) & !(h %in% mt) & !is.na(fr) & fr > e - 2L]
  ew <- edges_long[other == w & pid %in% ids]
  schools_w <- unique(edu_tab[person_id == w & !is.na(organization), organization])
  data.table(election = e, pid = ids,
             tie_designee_any = ids %in% ew$pid, tie_designee_stated = ids %in% ew[edge_type %in% stated_types, pid],
             tie_any_contender = ids %in% edges_long[other %in% cand, pid],
             same_school = ids %in% edu_tab[organization %in% schools_w, person_id],
             military = ids %in% mil_tab[!is.na(year_start) & year_start <= e - 2L, person_id],
             private = ids %in% oth_tab[!is.na(year_start) & year_start <= e - 2L, person_id],
             union = ids %in% lab_tab[!is.na(year_start) & year_start <= e - 2L, person_id])
}))
fol <- rbindlist(lapply(elections, function(e) {
  w <- slates[[as.character(e)]]$winner; d <- A[election == e & group == "D", pid]
  schools_w <- unique(edu_tab[person_id == w & !is.na(organization), organization])
  data.table(same_school = d %in% edu_tab[organization %in% schools_w, person_id])
}))
fwrite(nc, file.path(out_dir, "post_holders_newcomers.csv"))
mac <- readLines(file.path(tab_dir, "post_holders_macros.tex"))
mac <- c(mac, sprintf("\\newcommand{\\PHnewcomerN}{%d}", nrow(nc)),
         sprintf("\\newcommand{\\PHnewcomerTieDesignee}{%s}", pct(mean(nc$tie_designee_any))),
         sprintf("\\newcommand{\\PHnewcomerTieStated}{%s}", pct(mean(nc$tie_designee_stated))),
         sprintf("\\newcommand{\\PHnewcomerTieAnyContender}{%s}", pct(mean(nc$tie_any_contender))),
         sprintf("\\newcommand{\\PHnewcomerSameSchool}{%s}", pct(mean(nc$same_school))),
         sprintf("\\newcommand{\\PHfollowerSameSchool}{%s}", pct(mean(fol$same_school))),
         sprintf("\\newcommand{\\PHnewcomerMilitary}{%s}", pct(mean(nc$military))),
         sprintf("\\newcommand{\\PHnewcomerPrivate}{%s}", pct(mean(nc$private))),
         sprintf("\\newcommand{\\PHnewcomerUnion}{%s}", pct(mean(nc$union))))
writeLines(mac, file.path(tab_dir, "post_holders_macros.tex"))
cat(sprintf("newcomers %d: tie to designee any %s%%, stated %s%%, any contender %s%%, same school %s%% (followers %s%%), military %s%%, private %s%%, union %s%%\n",
            nrow(nc), pct(mean(nc$tie_designee_any)), pct(mean(nc$tie_designee_stated)), pct(mean(nc$tie_any_contender)),
            pct(mean(nc$same_school)), pct(mean(fol$same_school)), pct(mean(nc$military)), pct(mean(nc$private)), pct(mean(nc$union))))
