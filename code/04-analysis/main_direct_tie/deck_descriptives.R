# Deck tables and macros for the descriptive and secondary results (the losing contenders' destinations and
# co-optation, the patron's chair, the transitions to the next succession). Every number is read from the CSVs of
# loser_destinations.R, aspirants_table.R, cooptation_tests.R, chair_split.R, transitions.R and event_study.R (run
# those first); nothing is estimated here. Writes tables/{losers,chair_split,transitions}.tex and tables/desc_macros.tex.
#   Rscript code/04-analysis/main_direct_tie/deck_descriptives.R
suppressPackageStartupMessages(library(data.table))
db_root <- Sys.getenv("TAPADOSPRI_DB_ROOT", file.path(path.expand("~"), "Dropbox", "TapadosPRI"))
out_dir <- Sys.getenv("TAPADOS_MAIN_OUTPUT_DIR", file.path(db_root, "output", "main_direct_tie"))
tab_dir <- file.path(out_dir, "tables"); dir.create(tab_dir, showWarnings = FALSE)
f2 <- function(x, d = 2) { r <- round(x, d); s <- formatC(r, format = "f", digits = d); s[r == 0] <- formatC(0, format = "f", digits = d); sub("^-", "$-$", s) }
ci_txt <- function(lo, hi, d = 2) paste0("[", f2(lo, d), ", ", f2(hi, d), "]")
pct <- function(x, d = 0) f2(100 * x, d)
mac <- function(name, value) sprintf("\\newcommand{\\%s}{%s}", name, value)
write_tab <- function(lines, file) writeLines(lines, file.path(tab_dir, file))
designee_names <- c("1940" = "\\'Avila Camacho", "1946" = "Alem\\'an", "1952" = "Ruiz Cortines", "1958" = "L\\'opez Mateos",
                    "1964" = "D\\'iaz Ordaz", "1970" = "Echeverr\\'ia", "1976" = "L\\'opez Portillo", "1982" = "de la Madrid",
                    "1988" = "Salinas")
macros <- c("% desc_macros.tex -- numbers of the descriptive slides (deck_descriptives.R). Do not edit by hand.")

# ------------------------------------------------------------------ 1. where the new president sent the 47 losers
ld <- fread(file.path(out_dir, "loser_destinations.csv"))
stopifnot(nrow(ld) == 47L)
cats <- c("top domestic post", "abroad", "other domestic post", "no post", "broke with the party", "died", "prosecuted")
stopifnot(all(ld$destination %in% cats))
ld[, destination := factor(destination, cats)]
cnt <- dcast(ld[, .N, by = .(election, destination)], election ~ destination, value.var = "N", fill = 0L, drop = FALSE)
cnt[, losers := rowSums(.SD), .SDcols = cats]
tot <- cnt[, lapply(.SD, sum), .SDcols = c("losers", cats)]
ll <- c("% losers.tex -- destination of each losing contender in the new president's first three years (deck_descriptives.R from loser_destinations.csv)",
        "\\begin{tabular}{llrrrrrrr}", "\\toprule",
        " & & & \\multicolumn{6}{c}{Destination in $e+1,\\dots,e+3$} \\\\", "\\cmidrule(lr){4-9}",
        "Succession & Designee & Losers & Top post & Abroad & Lower post & No post & Broke & Died or \\\\",
        " & & & at home & & & & & prosecuted \\\\", "\\midrule")
for (i in seq_len(nrow(cnt))) ll <- c(ll, sprintf("%d & %s & %d & %d & %d & %d & %d & %d & %d \\\\", cnt$election[i],
  designee_names[as.character(cnt$election[i])], cnt$losers[i], cnt$`top domestic post`[i], cnt$abroad[i],
  cnt$`other domestic post`[i], cnt$`no post`[i], cnt$`broke with the party`[i], cnt$died[i] + cnt$prosecuted[i]))
ll <- c(ll, "\\midrule", sprintf("Total & & %d & %d & %d & %d & %d & %d & %d \\\\", tot$losers, tot$`top domestic post`, tot$abroad,
  tot$`other domestic post`, tot$`no post`, tot$`broke with the party`, tot$died + tot$prosecuted), "\\bottomrule", "\\end{tabular}")
write_tab(ll, "losers.tex")
macros <- c(macros, mac("LDn", tot$losers), mac("LDtop", tot$`top domestic post`), mac("LDabroad", tot$abroad),
            mac("LDkeptEither", tot$`top domestic post` + tot$abroad), mac("LDother", tot$`other domestic post`),
            mac("LDnone", tot$`no post`), mac("LDbroke", tot$`broke with the party`), mac("LDdied", tot$died),
            mac("LDprosecuted", tot$prosecuted),
            mac("LDkeptEitherPct", pct((tot$`top domestic post` + tot$abroad) / tot$losers)),
            mac("LDnonePct", pct(tot$`no post` / tot$losers)))

# ------------------------------------------------------------------ 2. co-optation: who kept a top chair (MAIN_SPEC 15)
asp <- fread(file.path(db_root, "data", "structural", "aspirants.csv"))
cm <- fread(file.path(db_root, "data", "candidates", "corcholatas_matched.csv"))
L <- asp[slate == "main"][!cm[role == "winner", .(election = election_year, pid = person_id)], on = .(election, pid)]
stopifnot(nrow(L) == 47L)
L[, kept := as.integer(treatment == "kept a top chair")]
inf <- L[, .(k = sum(kept), n = .N), by = election][k > 0 & k < n, election]
p1 <- fread(file.path(out_dir, "cooptation_p1.csv"))
macros <- c(macros, mac("CPnKept", sum(L$kept)), mac("CPnKeptSucc", L[kept == 1L, uniqueN(election)]),
            mac("CPnInf", length(inf)), mac("CPinfYears", paste(inf, collapse = ", ")),
            mac("CPpThreat", f2(p1[grepl("gate", role), p_one_sided], 3)), mac("CPpGov", f2(p1[grepl("governors", role), p_one_sided], 3)),
            mac("CPnGenerals", sum(L$general)), mac("CPgeneralsKept", L[general == 1L, sum(kept)]),
            mac("CPperms", format(p1[grepl("gate", role), permutations], big.mark = ",")),
            mac("CPcampKeptMedian", L[kept == 1L, median(camp_any)]), mac("CPcampLostMedian", L[kept == 0L, median(camp_any)]),
            mac("CPcabinetKept", pct(L[kept == 1L, mean(rung_e2 >= 9L)])), mac("CPcabinetLost", pct(L[kept == 0L, mean(rung_e2 >= 9L)])))

# ------------------------------------------------------------------ 3. the patron's chair (MAIN_SPEC 12)
cw <- fread(file.path(out_dir, "chair_split_windows.csv"))
pat <- fread(file.path(out_dir, "chair_split_patrons.csv"))
main <- cw[spec == "Main"]
pk <- main[grepl("^Pk:", estimate)]; pl <- main[grepl("^Pl:", estimate)]; df <- main[grepl("^Pk - Pl", estimate)]
ces <- fread(file.path(out_dir, "chair_split_event_study.csv"))
lead7 <- ces[grepl("^Pk - Pl", estimate) & k == -7]
macros <- c(macros,
  mac("CSkept", f2(pk$value)), mac("CSkeptLo", f2(pk$ci_lower)), mac("CSkeptHi", f2(pk$ci_upper)),
  mac("CSlost", f2(pl$value)), mac("CSlostLo", f2(pl$ci_lower)), mac("CSlostHi", f2(pl$ci_upper)),
  mac("CSdiff", f2(df$value)), mac("CSdiffLo", f2(df$ci_lower)), mac("CSdiffHi", f2(df$ci_upper)), mac("CSdiffP", f2(df$p_wild, 3)),
  mac("CSnKeptPatrons", pat[kept == 1L, .N]), mac("CSnLostPatrons", pat[kept == 0L, .N]),
  mac("CSnKeptFollowers", pat[kept == 1L, sum(followers)]), mac("CSnLostFollowers", pat[kept == 0L, sum(followers)]),
  mac("CSkeptSucc", paste(sort(unique(pat[kept == 1L, election])), collapse = ", ")),
  mac("CSleadSeven", f2(lead7$value)), mac("CSleadSevenLo", f2(lead7$ci_lower)), mac("CSleadSevenHi", f2(lead7$ci_upper)))
# Appendix table: every specification of chair_split.R.
spec_lab <- function(s) fifelse(s == "Main", "Main (top chair = rung 8 or above in $e+1$, $e+2$)",
                        fifelse(s == "(a) Top chair = rung 9", "(a) Top chair = rung 9 only (cabinet level)",
                        fifelse(s == "(b) Patron's chair over e+1..e+3", "(b) Patron's chair over $e+1,\\dots,e+3$", sub("^\\(c\\) ", "(c) ", s))))
cl <- c("% chair_split.tex -- the patron's chair across specifications (deck_descriptives.R from chair_split_windows.csv)",
        "\\begin{tabular}{lrrr}", "\\toprule",
        " & Patron kept & Patron lost & Kept $-$ lost, \\\\", " & a top chair & it & within succession \\\\", "\\midrule")
for (s in unique(cw$spec)) {
  r <- cw[spec == s]
  cl <- c(cl, sprintf("%s & %s & %s & %s \\\\", spec_lab(s), f2(r[grepl("^Pk:", estimate), value]), f2(r[grepl("^Pl:", estimate), value]),
                      f2(r[grepl("^Pk - Pl", estimate), value])),
          sprintf(" & {\\scriptsize %s} & {\\scriptsize %s} & {\\scriptsize %s} \\\\",
                  ci_txt(r[grepl("^Pk:", estimate), ci_lower], r[grepl("^Pk:", estimate), ci_upper]),
                  ci_txt(r[grepl("^Pl:", estimate), ci_lower], r[grepl("^Pl:", estimate), ci_upper]),
                  ci_txt(r[grepl("^Pk - Pl", estimate), ci_lower], r[grepl("^Pk - Pl", estimate), ci_upper])))
}
cl <- c(cl, "\\bottomrule", "\\end{tabular}")
write_tab(cl, "chair_split.tex")

# ------------------------------------------------------------------ 4. transitions to the next succession (transitions.R)
tc <- fread(file.path(out_dir, "transitions_contrasts.csv"))
tl <- melt(tc, id.vars = c("outcome", "stat"), measure.vars = c("D", "P", "M", "N", "D_minus_P", "P_minus_N"), variable.name = "group")
tl[, stat := fifelse(grepl("estimate", stat), "est", gsub("\\.", "_", stat))]
tw <- dcast(tl, outcome + group ~ stat, value.var = "value")
g <- function(o, gr, s = "est") tw[outcome == o & group == gr, get(s)]
sg <- fread(file.path(out_dir, "transitions_sign_tests.csv"))
cv <- fread(file.path(out_dir, "transitions_continuation_value.csv"))
ex <- fread(file.path(out_dir, "transitions_exit.csv"))
rh <- fread(file.path(out_dir, "transitions_random_heir.csv"))
bs <- fread(file.path(out_dir, "transitions_by_succession_tied_next_designee.csv"))
for (gr in c("D", "P", "M", "N")) macros <- c(macros,
  mac(paste0("TRheir", gr), pct(g("tied_next_designee", gr))),
  mac(paste0("TRheir", gr, "Lo"), pct(g("tied_next_designee", gr, "ci_2_5"))), mac(paste0("TRheir", gr, "Hi"), pct(g("tied_next_designee", gr, "ci_97_5"))),
  mac(paste0("TRany", gr), pct(g("tied_next_aspirant", gr))),
  mac(paste0("TRany", gr, "Lo"), pct(g("tied_next_aspirant", gr, "ci_2_5"))), mac(paste0("TRany", gr, "Hi"), pct(g("tied_next_aspirant", gr, "ci_97_5"))),
  mac(paste0("TRrungTen", gr), f2(cv[horizon == "e+10" & group == gr, mean_rung], 1)),
  mac(paste0("TRrungSixteen", gr), f2(cv[horizon == "e+16" & group == gr, mean_rung], 1)),
  mac(paste0("TRtopTen", gr), pct(cv[horizon == "e+10" & group == gr, top_7plus])),
  mac(paste0("TRinPool", gr), pct(ex[group == gr, in_pool_e6])))
macros <- c(macros,
  mac("TRnTransitions", sg$n[1]),
  mac("TRheirPNk", sg[outcome == "tied_next_designee" & contrast == "P > N", k]), mac("TRheirPNp", f2(sg[outcome == "tied_next_designee" & contrast == "P > N", p_one_sided], 3)),
  mac("TRanyPNk", sg[outcome == "tied_next_aspirant" & contrast == "P > N", k]), mac("TRanyPNp", f2(sg[outcome == "tied_next_aspirant" & contrast == "P > N", p_one_sided], 3)),
  mac("TRheirDPk", sg[outcome == "tied_next_designee" & contrast == "D > P", k]), mac("TRheirDPp", f2(sg[outcome == "tied_next_designee" & contrast == "D > P", p_one_sided], 3)),
  mac("TRheirPminusN", pct(g("tied_next_designee", "P_minus_N"))), mac("TRheirPminusNLo", pct(g("tied_next_designee", "P_minus_N", "ci_2_5"))),
  mac("TRheirPminusNHi", pct(g("tied_next_designee", "P_minus_N", "ci_97_5"))),
  mac("TRheirDminusP", pct(g("tied_next_designee", "D_minus_P"))), mac("TRheirDminusPLo", pct(g("tied_next_designee", "D_minus_P", "ci_2_5"))),
  mac("TRheirDminusPHi", pct(g("tied_next_designee", "D_minus_P", "ci_97_5"))),
  mac("TRbenchRatioD", f2(rh[group == "D", ratio], 1)), mac("TRbenchRatioP", f2(rh[group == "P", ratio], 1)), mac("TRbenchRatioN", f2(rh[group == "N", ratio], 1)))
# Appendix table: by group.
lab_g <- c(D = "Designee's followers", P = "Losers' followers", M = "Tied to several contenders", N = "Tied to no contender")
tr_l <- c("% transitions.tex -- group at e and standing at the next succession (deck_descriptives.R from transitions.R outputs)",
          "\\begin{tabular}{lrrrrr}", "\\toprule",
          " & Still eligible & \\multicolumn{2}{c}{Tied by $e+4$ to} & \\multicolumn{2}{c}{Rung held} \\\\",
          "\\cmidrule(lr){3-4}\\cmidrule(lr){5-6}",
          "Group at $e$ & at $e+6$ (\\%) & next designee (\\%) & any next contender (\\%) & $e+10$ & $e+16$ \\\\", "\\midrule")
for (gr in c("D", "P", "M", "N")) tr_l <- c(tr_l,
  sprintf("%s & %s & %s & %s & %s & %s \\\\", lab_g[gr], pct(ex[group == gr, in_pool_e6]), pct(g("tied_next_designee", gr)),
          pct(g("tied_next_aspirant", gr)), f2(cv[horizon == "e+10" & group == gr, mean_rung], 1), f2(cv[horizon == "e+16" & group == gr, mean_rung], 1)),
  sprintf(" & & {\\scriptsize [%s, %s]} & {\\scriptsize [%s, %s]} & & \\\\", pct(g("tied_next_designee", gr, "ci_2_5")), pct(g("tied_next_designee", gr, "ci_97_5")),
          pct(g("tied_next_aspirant", gr, "ci_2_5")), pct(g("tied_next_aspirant", gr, "ci_97_5"))))
tr_l <- c(tr_l, "\\midrule",
  sprintf("\\multicolumn{6}{l}{Losers' $>$ unaligned in %d of %d transitions (next designee, $p$ = %s) and %d of %d (any contender, $p$ = %s)} \\\\",
          sg[outcome == "tied_next_designee" & contrast == "P > N", k], sg$n[1], f2(sg[outcome == "tied_next_designee" & contrast == "P > N", p_one_sided], 3),
          sg[outcome == "tied_next_aspirant" & contrast == "P > N", k], sg$n[1], f2(sg[outcome == "tied_next_aspirant" & contrast == "P > N", p_one_sided], 3)),
  "\\bottomrule", "\\end{tabular}")
write_tab(tr_l, "transitions.tex")

# ------------------------------------------------------------------ 5. event-study intervals quoted on the main slides
ess <- fread(file.path(out_dir, "event_study_summary.csv"))[outcome == "rank"]
nx <- ess[contrast == "next_president_average"]; dr <- ess[contrast == "change_7_minus_6"]; av <- ess[contrast == "main_window_average"]
macros <- c(macros, mac("ESavgEst", f2(av$estimate)), mac("ESavgLo", f2(av$ci_lower)), mac("ESavgHi", f2(av$ci_upper)), mac("ESavgP", f2(av$p_bootstrap, 2)),
            mac("ESnextEst", f2(nx$estimate)), mac("ESnextLo", f2(nx$ci_lower)), mac("ESnextHi", f2(nx$ci_upper)), mac("ESnextP", f2(nx$p_bootstrap, 2)),
            mac("ESdropEst", f2(dr$estimate)), mac("ESdropLo", f2(dr$ci_lower)), mac("ESdropHi", f2(dr$ci_upper)), mac("ESdropP", f2(dr$p_bootstrap, 2)))
writeLines(macros, file.path(tab_dir, "desc_macros.tex"))
cat("written:", file.path(tab_dir, c("losers.tex", "chair_split.tex", "transitions.tex", "desc_macros.tex")), sep = "\n")
