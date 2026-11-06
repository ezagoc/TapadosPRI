# Who runs the money (20 October 2026). For each succession, the share of federal public investment executed by
# agencies whose head belongs to each group of the main design (designee's followers, losing contenders'
# followers, tied to several contenders, in the eligible pool but tied to no contender, the contenders
# themselves, contenders of other successions, politicians outside the eligible pool), plus the agency-years
# with no head identified, split into lines that have no head by construction (programmes, residual lines,
# transfers) and heads the crosswalk did not find. Windows e-5..e-2 and e+1..e+4; shares within year, then
# averaged over the window's years, then over the nine successions (equal and person weights). Uses the exact
# decomposition of budget_crosswalk.R (every agency row of a year sums to 100) and the same head -> agency
# crosswalk as budget_outcome.R; a person heading two agencies keeps both, two heads of one agency in a year
# split its share. Run after budget_outcome.R, from the repo root:
#   Rscript code/04-analysis/main_direct_tie/investment_heads.R
# Outputs (output/main_direct_tie): investment_heads_by_group.csv, investment_heads_summary.csv,
# investment_heads_largest.csv, investment_heads_coverage.csv, investment_heads_unmatched.csv,
# investment_heads.pdf/.png, tables/investment_heads.tex, tables/invest_macros.tex.
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
invisible(capture.output(source(file.path(script_dir, "estimate_main.R"))))
source(file.path(script_dir, "design_tools.R"))
source(file.path(script_dir, "budget_crosswalk.R"))
inv_dir <- file.path(data_dir, "investment")
tab_dir <- file.path(out_dir, "tables")
dir.create(tab_dir, showWarnings = FALSE)

# ------------------------------------------------------------------ 1. agencies, shares and heads
panel <- fread(file.path(inv_dir, "agency_investment_panel.csv"))
ex <- build_agency_shares_exact(panel)
series <- build_agency_series(panel)                 # the budget_outcome.R series: same agency-years, used to resolve keys
stopifnot(abs(ex[, sum(share), by = year]$V1 - 100) < 1e-6)
labels <- unique(panel[, .(agency_key, label)])[, .(label = label[1]), by = agency_key]
agency_name <- c(pemex = "PEMEX", cfe = "CFE", sop = "SCOP / SOP (public works)", sct = "SCT", srh = "SRH (CNI before 1947)",
                 sarh = "SARH", sag = "SAG", fnm = "National Railways", imss = "IMSS", issste = "ISSSTE", ddf = "Federal District (DDF)",
                 sahop = "SAHOP", sedue = "SEDUE", sepafin = "SEPAFIN / SEMIP", energia_sector = "Energy sector", sep = "SEP",
                 spp = "SPP", lyfc = "Light and Power", capfce = "CAPFCE", stc_metro = "Metro (STC)", juntas_mejoras = "Juntas de Mejoras",
                 desarrollo_regional = "Desarrollo Regional", solidaridad_programs = "Solidaridad (ramo 26)", otrosl = "Other (residual line)",
                 ciudad_universitaria = "Ciudad Universitaria", fc_pacifico = "Ferrocarril del Pacifico", sicartsa = "SICARTSA",
                 ahmsa = "AHMSA", banobras = "BANOBRAS", semar = "Navy", sedena = "Defense", ssa = "Health", sedesol = "SEDESOL",
                 pider = "PIDER", provisiones_salariales = "Provisiones salariales", capufe = "CAPUFE", conasupo = "CONASUPO")
name_of <- function(k) ifelse(k %in% names(agency_name), agency_name[k], labels$label[match(k, labels$agency_key)])

pos <- fread(file.path(data_dir, "rank", "position_tiers.csv"), na.strings = c("", "NA"))
heads <- resolve_heads(head_records(pos), series)
hy <- heads[!is.na(key)]
ay <- unique(person_year_shares(hy, ex)[, .(agency_key, year, pid)])
ay[, w := 1 / .N, by = .(agency_key, year)]        # two heads of one agency in a year split its share
person_name <- pos[, .(name = person_name[1]), by = person_id]
budget_py <- person_year_shares(hy, series)[, .(share = max(share), heads = 1L), by = .(pid, year)]   # as budget_outcome.R

# ------------------------------------------------------------------ 2. coverage: who has a head, 1935-1992
cov <- merge(ex, ay[, .(n_heads = .N), by = .(agency_key, year)], by = c("agency_key", "year"), all.x = TRUE)
cov[is.na(n_heads), n_heads := 0L]
cov[, status := fifelse(no_head_by_construction, "no_head_by_construction", fifelse(n_heads > 0L, "head_found", "head_not_found"))]
coverage <- dcast(cov[, .(share = sum(share)), by = .(year, status)], year ~ status, value.var = "share", fill = 0)
coverage <- merge(coverage, cov[, .(n_agencies = .N, n_with_head = sum(n_heads > 0L)), by = year], by = "year")
setcolorder(coverage, c("year", "head_found", "head_not_found", "no_head_by_construction", "n_agencies", "n_with_head"))
fwrite(coverage[order(year)], file.path(out_dir, "investment_heads_coverage.csv"))
unmatched <- cov[status == "head_not_found" & year %in% 1935:1992][order(-share)][
  , .(agency_key, agency = name_of(agency_key), year, share = round(share, 2), lineage = labels$label[match(agency_key, labels$agency_key)])]
fwrite(unmatched[1:15], file.path(out_dir, "investment_heads_unmatched.csv"))

# ------------------------------------------------------------------ 3. groups of the main design
groups <- c(D = "Designee's followers", P = "Losing contenders' followers", M = "Tied to several contenders",
            N = "In the pool, tied to no contender", C = "Contenders of this succession",
            C_other = "Contenders of other successions", outside_pool = "Outside the eligible pool",
            no_head_by_construction = "No head by construction", head_not_found = "Head not found")
other_contenders <- function(e) unique(contenders[election_year != e, person_id])
group_of <- function(pids, e) {
  el <- eligible[[as.character(e)]]; sl <- slates[[as.character(e)]]
  g <- rep("outside_pool", length(pids))
  m <- match(pids, el$pid); inpool <- !is.na(m)
  nd <- el$n_direct[m]; pat <- el$patron[m]
  g[inpool & nd == 0L] <- "N"
  g[inpool & nd > 1L] <- "M"
  g[inpool & nd == 1L & !is.na(pat) & pat == sl$winner] <- "D"
  g[inpool & nd == 1L & !is.na(pat) & pat != sl$winner] <- "P"
  g[!inpool & pids %in% other_contenders(e)] <- "C_other"
  g[pids %in% sl$candidates] <- "C"
  g
}
windows <- list(before = -5:-2, after = 1:4)

by_group <- rbindlist(lapply(elections, function(e) rbindlist(lapply(names(windows), function(w) {
  yrs <- e + windows[[w]]
  rows <- cov[year %in% yrs]
  h <- ay[year %in% yrs][, group := group_of(pid, e)]
  h <- merge(h, rows[, .(agency_key, year, share)], by = c("agency_key", "year"))
  with_head <- h[, .(share = sum(share * w)), by = .(agency_key, year, group)]
  no_head <- rows[n_heads == 0L, .(agency_key, year, group = status, share)]
  all <- rbind(with_head, no_head)
  out <- all[, .(share = sum(share) / length(yrs), n_agency_years = uniqueN(paste(agency_key, year))), by = group]
  out <- merge(data.table(group = names(groups)), out, by = "group", all.x = TRUE)
  out[is.na(share), `:=`(share = 0, n_agency_years = 0L)]
  out[, `:=`(election = e, window = w)]
  out[, .(election, window, group, share, n_agency_years)]
}))))
by_group[, group := factor(group, levels = names(groups))]
setorder(by_group, election, window, group)
stopifnot(abs(by_group[, sum(share), by = .(election, window)]$V1 - 100) < 1e-6)
fwrite(by_group, file.path(out_dir, "investment_heads_by_group.csv"))

n_designee <- sample[treated == 1L, .N, by = election]
omega_person <- setNames(n_designee$N / sum(n_designee$N), n_designee$election)
summary <- by_group[, .(share_equal = mean(share),
                        share_person_weighted = sum(share * omega_person[as.character(election)]),
                        n_successions = .N, n_successions_positive = sum(share > 0),
                        share_min = min(share), share_max = max(share)), by = .(window, group)]
summary[, group_label := groups[as.character(group)]]
setcolorder(summary, c("window", "group", "group_label"))
setorder(summary, window, group)
fwrite(summary, file.path(out_dir, "investment_heads_summary.csv"))

# ------------------------------------------------------------------ 4. the largest agencies after each succession
named <- c("pemex", "cfe", "sop", "sct", "srh", "sarh", "fnm", "imss")
largest <- rbindlist(lapply(elections, function(e) {
  yrs <- e + windows$after
  a <- cov[year %in% yrs, .(share_post = sum(share) / length(yrs)), by = agency_key][order(-share_post)]
  a[, rank := seq_len(.N)]
  a <- a[rank <= 3L | agency_key %in% named]
  h <- ay[year %in% yrs & agency_key %in% a$agency_key][, group := group_of(pid, e)]
  h <- h[, .(y0 = min(year), y1 = max(year)), by = .(agency_key, pid, group)][order(agency_key, y0)]
  h[, name := person_name$name[match(pid, person_name$person_id)]]
  hh <- h[, .(heads = paste0(name, " (", y0, "-", y1, ", ", group, ")", collapse = "; "),
              groups = paste(unique(as.character(group)), collapse = "; ")), by = agency_key]
  a <- merge(a, hh, by = "agency_key", all.x = TRUE)
  a[is.na(heads), `:=`(heads = "", groups = fifelse(agency_key %in% ex[no_head_by_construction == TRUE, agency_key],
                                                     "no_head_by_construction", "head_not_found"))]
  a[, `:=`(election = e, agency = name_of(agency_key), in_top3 = as.integer(rank <= 3L))]
  a[order(rank), .(election, rank, in_top3, agency_key, agency, share_post, heads, groups)]
}))
fwrite(largest, file.path(out_dir, "investment_heads_largest.csv"))

# ------------------------------------------------------------------ 5. the section-9 estimates for the macros
bw <- fread(file.path(out_dir, "budget_windows.csv"))
needed <- c("budget_share", "heads_agency", "access_1pct", "budget_share_cap5")
stopifnot(all(needed %in% bw$column))
wmax <- function(from, to) apply(sapply(from:to, function(k) year_value(budget_py, k, "share")), 1L, max)
waccess <- function(from, to) apply(sapply(from:to, function(k) as.numeric(year_value(budget_py, k, "share") >= 1)), 1L, max)
y_share <- wmax(1, 4) - wmax(-5, -2)
y_access <- waccess(1, 4) - waccess(-5, -2)
d_all <- build_design()
access_check <- estimate_columns(d_all, cbind(access_1pct = y_access), B = 2000L)$table$estimate
stopifnot(abs(access_check - bw[column == "access_1pct", estimate]) < 1e-8)
access_by_e <- by_succession_d(d_all, y_access)
estrada <- pos[person_name == "Estrada Reynoso, Enrique", unique(person_id)]
stopifnot(length(estrada) == 1L)
d_ne <- build_design(keep = sample$pid != estrada)
no_estrada <- estimate_columns(d_ne, cbind(budget_share = y_share[d_ne$rows]))$table
fwrite(rbind(access_by_e[, .(outcome = "access_1pct", election, estimate, n_designee)],
             data.table(outcome = "budget_share_without_estrada", election = NA_integer_, estimate = no_estrada$estimate,
                        n_designee = no_estrada$n_designee)),
       file.path(out_dir, "investment_heads_estimates.csv"))

# ------------------------------------------------------------------ 6. figure: two stacked bars
fig <- copy(summary)[, .(window, group, share = share_equal)]
fig[, window := factor(window, levels = c("after", "before"),
                       labels = c("After the succession\n(e+1 to e+4)", "Before the succession\n(e-5 to e-2)"))]
fig[, group := factor(group, levels = names(groups))]       # designee's followers first, at the left of each bar
greys <- c(D = INK, P = "#4a4a4a", M = "#666666", N = "#808080", C = "#999999", C_other = "#b0b0b0",
           outside_pool = "#c6c6c6", no_head_by_construction = "#dadada", head_not_found = "#ececec")
fig[, lab := fifelse(share >= 5, sprintf("%.0f", share), "")]
fig[, lab_col := fifelse(group %in% c("D", "P", "M", "N"), "white", INK)]
setorder(fig, window, group)
g <- ggplot(fig, aes(x = share, y = window, fill = group)) +
  geom_col(width = 0.62, colour = "white", linewidth = 0.4, position = position_stack(reverse = TRUE)) +
  geom_text(aes(label = lab, colour = lab_col, group = group), position = position_stack(vjust = 0.5, reverse = TRUE),
            size = 4.2, family = FAM) +            # group = group: the labels stack in the bars' order, not by colour
  scale_colour_identity() +
  scale_fill_manual(values = greys, breaks = names(groups), labels = unname(groups), name = NULL) +
  scale_x_continuous(expand = c(0, 0), limits = c(0, 100.5), breaks = seq(0, 100, 20)) +
  labs(x = "Share of federal public investment (%), average of the nine successions 1940-1988", y = NULL) +
  theme_paper(15) +
  theme(legend.position = "right", legend.text = element_text(size = 11, colour = INK),
        legend.key.size = unit(0.42, "cm"), legend.spacing.y = unit(0.1, "cm"),
        axis.line.y = element_blank(), axis.ticks.y = element_blank(), axis.text.y = element_text(size = 12, lineheight = 0.9),
        axis.title.x = element_text(size = 12)) +
  guides(fill = guide_legend(ncol = 1, byrow = TRUE))
ggsave(file.path(out_dir, "investment_heads.pdf"), g, width = 10, height = 4.1, bg = "white", device = "pdf")
ggsave(file.path(out_dir, "investment_heads.png"), g, width = 10, height = 4.1, dpi = 250, bg = "white")

# ------------------------------------------------------------------ 7. LaTeX table and macros
num <- function(x, d = 1) sub("-", "$-$", sprintf(paste0("%.", d, "f"), x), fixed = TRUE)
tab <- dcast(summary[, .(group, window, share_equal)], group ~ window, value.var = "share_equal")
tab[, group := factor(group, levels = names(groups))]
setorder(tab, group)
tab[, change := after - before]
lines <- c("% investment_heads.tex (investment_heads.R from investment_heads_summary.csv): share of federal public investment",
           "% by the group of the agency's head, average of the nine successions 1940-1988, equal weights. Do not edit by hand.",
           "\\begin{tabular}{lrrr}", "\\toprule",
           " & \\multicolumn{3}{c}{Share of federal investment (\\%)} \\\\", "\\cmidrule(lr){2-4}",
           "Head of the agency & $e-5$ to $e-2$ & $e+1$ to $e+4$ & Change \\\\", "\\midrule",
           tab[, sprintf("%s & %s & %s & %s \\\\", groups[as.character(group)], num(before), num(after), num(change))],
           "\\bottomrule", "\\end{tabular}")
writeLines(lines, file.path(tab_dir, "investment_heads.tex"))

sh <- function(g, w) tab[group == g, get(w)]
est <- function(col, what) bw[column == col, get(what)]
macros <- c(
  "% invest_macros.tex -- numbers of the investment slides (investment_heads.R, budget_outcome.R). Do not edit by hand.",
  sprintf("\\newcommand{\\IHdBefore}{%s}", num(sh("D", "before"))), sprintf("\\newcommand{\\IHdAfter}{%s}", num(sh("D", "after"))),
  sprintf("\\newcommand{\\IHpBefore}{%s}", num(sh("P", "before"))), sprintf("\\newcommand{\\IHpAfter}{%s}", num(sh("P", "after"))),
  sprintf("\\newcommand{\\IHmBefore}{%s}", num(sh("M", "before"))), sprintf("\\newcommand{\\IHmAfter}{%s}", num(sh("M", "after"))),
  sprintf("\\newcommand{\\IHnBefore}{%s}", num(sh("N", "before"))), sprintf("\\newcommand{\\IHnAfter}{%s}", num(sh("N", "after"))),
  sprintf("\\newcommand{\\IHcBefore}{%s}", num(sh("C", "before"))), sprintf("\\newcommand{\\IHcAfter}{%s}", num(sh("C", "after"))),
  sprintf("\\newcommand{\\IHcOtherBefore}{%s}", num(sh("C_other", "before"))), sprintf("\\newcommand{\\IHcOtherAfter}{%s}", num(sh("C_other", "after"))),
  sprintf("\\newcommand{\\IHoutsideBefore}{%s}", num(sh("outside_pool", "before"))), sprintf("\\newcommand{\\IHoutsideAfter}{%s}", num(sh("outside_pool", "after"))),
  sprintf("\\newcommand{\\IHnoHeadBefore}{%s}", num(sh("no_head_by_construction", "before"))), sprintf("\\newcommand{\\IHnoHeadAfter}{%s}", num(sh("no_head_by_construction", "after"))),
  sprintf("\\newcommand{\\IHnotFoundBefore}{%s}", num(sh("head_not_found", "before"))), sprintf("\\newcommand{\\IHnotFoundAfter}{%s}", num(sh("head_not_found", "after"))),
  sprintf("\\newcommand{\\IHaccessEst}{%s}", num(100 * est("access_1pct", "estimate"))),
  sprintf("\\newcommand{\\IHaccessLo}{%s}", num(100 * est("access_1pct", "ci_lower"))),
  sprintf("\\newcommand{\\IHaccessHi}{%s}", num(100 * est("access_1pct", "ci_upper"))),
  sprintf("\\newcommand{\\IHaccessPositive}{%d}", sum(access_by_e$estimate > 0)),
  sprintf("\\newcommand{\\IHaccessP}{%s}", { pa <- est("access_1pct", "p_bootstrap"); if (pa < 0.01) "$<$0.01" else formatC(pa, format = "f", digits = 2) }),
  sprintf("\\newcommand{\\IHheadsEst}{%s}", num(100 * est("heads_agency", "estimate"))),
  sprintf("\\newcommand{\\IHheadsLo}{%s}", num(100 * est("heads_agency", "ci_lower"))),
  sprintf("\\newcommand{\\IHheadsHi}{%s}", num(100 * est("heads_agency", "ci_upper"))),
  sprintf("\\newcommand{\\IHshareEst}{%s}", num(est("budget_share", "estimate"), 2)),
  sprintf("\\newcommand{\\IHshareLo}{%s}", num(est("budget_share", "ci_lower"), 2)),
  sprintf("\\newcommand{\\IHshareHi}{%s}", num(est("budget_share", "ci_upper"), 2)),
  sprintf("\\newcommand{\\IHshareCapEst}{%s}", num(est("budget_share_cap5", "estimate"), 2)),
  sprintf("\\newcommand{\\IHshareCapLo}{%s}", num(est("budget_share_cap5", "ci_lower"), 2)),
  sprintf("\\newcommand{\\IHshareCapHi}{%s}", num(est("budget_share_cap5", "ci_upper"), 2)),
  sprintf("\\newcommand{\\IHshareNoEstrada}{%s}", num(no_estrada$estimate, 2)),
  sprintf("\\newcommand{\\IHshareNoEstradaLo}{%s}", num(no_estrada$ci_lower, 2)),
  sprintf("\\newcommand{\\IHshareNoEstradaHi}{%s}", num(no_estrada$ci_upper, 2)),
  sprintf("\\newcommand{\\IHnotFoundMean}{%s}", num(coverage[year %in% 1935:1992, mean(head_not_found)])),
  sprintf("\\newcommand{\\IHheadRecords}{%d}", nrow(hy)))
# the three largest agencies of each succession and who headed them (6 November 2026, the deck's money slide)
top3 <- largest[in_top3 == 1L]
top3_share <- top3[, .(s = sum(share_post)), by = election][, mean(s)]
macros <- c(macros,
  sprintf("\\newcommand{\\IHtopThreeShare}{%s}", formatC(top3_share, format = "f", digits = 0)),
  sprintf("\\newcommand{\\IHtopThreeN}{%d}", nrow(top3)),
  sprintf("\\newcommand{\\IHtopThreeD}{%d}", sum(grepl("\\bD\\b", top3$groups))),
  sprintf("\\newcommand{\\IHtopThreeP}{%d}", sum(grepl("\\bP\\b", top3$groups))),
  sprintf("\\newcommand{\\IHtopThreeFollowers}{%d}", sum(grepl("\\bD\\b|\\bP\\b", top3$groups))))
writeLines(macros, file.path(tab_dir, "invest_macros.tex"))

# ------------------------------------------------------------------ 8. console
cat("Head records resolved:", nrow(hy), "of", nrow(heads), "; agency-years with a head 1935-1992:",
    cov[year %in% 1935:1992, sum(n_heads > 0)], "of", cov[year %in% 1935:1992, .N], "\n")
cat("Share with no head found, mean 1935-1992:", round(coverage[year %in% 1935:1992, mean(head_not_found)], 1), "%\n")
coverage[, decade := 10 * (year %/% 10)]
print(coverage[year %in% 1935:1992, .(head_found = round(mean(head_found), 1), head_not_found = round(mean(head_not_found), 1),
                                      no_head_by_construction = round(mean(no_head_by_construction), 1)), by = decade])
cat("\n15 largest unmatched agency-years:\n"); print(unmatched[1:15])
cat("\nShares by group (equal weights over the nine successions):\n")
print(dcast(summary[, .(group_label, window, share = round(share_equal, 1))], group_label ~ window, value.var = "share"))
cat("\nLargest agencies after each succession:\n")
print(largest[in_top3 == 1L, .(election, rank, agency, share_post = round(share_post, 1), heads = substr(heads, 1, 70))], nrows = 40)
cat("\nAccess (>= 1%) positive in", sum(access_by_e$estimate > 0), "of", nrow(access_by_e), "successions;",
    "share without Estrada Reynoso:", round(no_estrada$estimate, 3), "[", round(no_estrada$ci_lower, 3), ",", round(no_estrada$ci_upper, 3), "]\n")
cat("Wrote:", out_dir, "\n")
