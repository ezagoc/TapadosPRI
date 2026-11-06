# Camp persistence across successions: does the next designee's camp come out of the sitting president's camp? For each
# consecutive pair of successions (e, e+6), e = 1940..1982, from the point of view of the NEXT designee's exclusive
# followers (direct ties by e+4, the main design's D group at e+6, read from the exported pool as transitions.R does):
#   (1) their status at e-2 in the previous succession: D the sitting president's (designee of e) exclusive follower,
#       P a loser's exclusive follower, M tied to several contenders, N unaligned in the pool, or not in the pool at e
#       (too young, no ranked post in e-5..e-2); benchmark: the same composition for every losing contender of the e+6
#       slate (equal weight per loser with at least one exclusive follower) and for its documented runner-up;
#   (2) whether the next designee (and every next loser) was himself directly tied to the sitting president by e-2 and by
#       e+4 (dated co-work, co-education, co-military, co-revolution edges, as in the main design);
#   (3) the overlap of the two camps: Jaccard index between the sitting president's exclusive followers at e-2 and the
#       next designee's at e+4 (and the next losers'), and the share of the sitting president's followers who are among
#       the next designee's exclusive followers at e+4 (transitions.R's 48% counts any tie among those still eligible;
#       this one counts exclusive ties, and is reported over all of them and over those still eligible);
#   (4) the fate of the sitting president's camp at e+6 is transitions.R's (tied to the next designee at all / to a
#       next loser only / to no next contender), copied from transitions_contrasts.csv, not recomputed.
# Equal weight per transition; percentile bootstrap over the 8 transitions (5,000 draws) for the 95% and 90% intervals.
#   Rscript code/04-analysis/main_direct_tie/camp_persistence.R   (after export_structural_inputs.R and transitions.R)
suppressPackageStartupMessages({ library(data.table); library(ggplot2) })
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
source(file.path(script_dir, "design_tools.R"))                       # house style only (theme_paper, INK, MUTED, RULE, FAM)
db_root <- Sys.getenv("TAPADOSPRI_DB_ROOT", file.path(path.expand("~"), "Dropbox", "TapadosPRI"))
out_dir <- Sys.getenv("TAPADOS_MAIN_OUTPUT_DIR", file.path(db_root, "output", "main_direct_tie"))
tab_dir <- file.path(out_dir, "tables"); dir.create(tab_dir, showWarnings = FALSE)
set.seed(20102026L)
B <- 5000L
pool <- fread(file.path(db_root, "data", "structural", "pool.csv"))
ties <- fread(file.path(db_root, "data", "structural", "ties.csv"))         # i in the pool at e, j anyone, ties by e-2
asp <- fread(file.path(db_root, "data", "candidates", "corcholatas_matched.csv"), na.strings = c("", "NA"))[
  in_main_slate == 1L & !is.na(person_id)]
edges <- fread(file.path(db_root, "data", "networks", "network_edges.csv"), na.strings = c("", "NA"))
tie_types <- c("co_work", "co_education", "co_military", "co_revolution")

# Direct ties between two people: year the first dated tie of the four types formed, and a short description.
dated <- edges[edge_type %in% tie_types & !is.na(year_start)]
long_e <- rbind(dated[, .(a = person_a, b = person_b, edge_type, focus, year_start)],
                dated[, .(a = person_b, b = person_a, edge_type, focus, year_start)])
setorder(long_e, a, b, year_start)
first_tie <- long_e[, .(first_year = year_start[1], detail = paste(unique(paste0(edge_type, ": ", focus, " (", year_start, ")")), collapse = "; ")),
                    by = .(a, b)]
tie_year <- function(i, j) first_tie[data.table(a = i, b = j), on = .(a, b), first_year]
tie_detail <- function(i, j) first_tie[data.table(a = i, b = j), on = .(a, b), detail]

statuses <- c("D", "P", "M", "N", "new")
status_labels <- c(D = "Sitting president's followers", P = "Losers' followers", M = "Tied to several",
                   N = "Unaligned", new = "Not in the pool at e")
short_names <- c("1940" = "Ávila Camacho", "1946" = "Alemán", "1952" = "Ruiz Cortines", "1958" = "López Mateos",
                 "1964" = "Díaz Ordaz", "1970" = "Echeverría", "1976" = "López Portillo", "1982" = "de la Madrid", "1988" = "Salinas")
latex_name <- function(x) { m <- c("á" = "\\'a", "é" = "\\'e", "í" = "\\'i", "ó" = "\\'o", "Á" = "\\'A")
  for (k in names(m)) x <- gsub(k, m[[k]], x, fixed = TRUE); x }

# ------------------------------------------------------------------ 1. one row per contender of the e+6 slate
es <- seq(1940L, 1982L, by = 6L)
designee <- asp[role == "winner", .(election = election_year, d = person_id, d_name = person_name)]
stopifnot(all(c(es, es + 6L) %in% designee$election))
contender_rows <- rbindlist(lapply(es, function(e) {
  e6 <- e + 6L
  sitting <- designee[election == e, d]
  prev <- pool[election == e, .(pid, status = group)]                  # status at e-2 (the pool at e)
  D_e <- prev[status == "D", pid]                                      # the sitting president's exclusive followers at e-2
  in_pool_e6 <- pool[election == e6, pid]
  slate <- asp[election_year == e6, .(pid = person_id, name = person_name, role, is_runner_up = as.integer(is_runner_up == 1L))]
  slate[, role := fifelse(role == "winner", "designee", fifelse(is_runner_up == 1L, "runner_up", "loser"))]
  slate[, `:=`(election = e, next_election = e6, sitting_president = sitting, sitting_name = designee[election == e, d_name])]
  ty <- tie_year(slate$pid, rep(sitting, nrow(slate)))
  slate[, `:=`(tied_sitting_by_e2 = as.integer(!is.na(ty) & ty <= e - 2L), tied_sitting_by_e4 = as.integer(!is.na(ty) & ty <= e + 4L),
               first_tie_sitting = ty, tie_sitting_detail = tie_detail(pid, rep(sitting, .N)))]
  compose <- function(F, prefix) {                                    # followers F by their status at e-2
    st <- prev$status[match(F, prev$pid)]; st[is.na(st)] <- "new"
    cnt <- as.list(table(factor(st, statuses))); names(cnt) <- paste0(prefix, "n_", statuses)
    c(setNames(list(length(F)), paste0(prefix, "n_followers")), cnt)
  }
  comp <- rbindlist(lapply(seq_len(nrow(slate)), function(k) {
    F <- pool[election == e6 & n_direct == 1L & patron == slate$pid[k], pid]   # exclusive followers at e+4 (the pool's D / P)
    FA <- unique(ties[election == e6 & j == slate$pid[k] & c > 0, i])          # tied at all by e+4, exclusive or not (robustness)
    inter <- length(intersect(D_e, F))
    c(compose(F, ""), compose(FA, "any_"),
      list(jaccard_sitting_D = if (length(union(D_e, F))) inter / length(union(D_e, F)) else NA_real_,
           inherited_share_of_sitting_D = if (length(D_e)) inter / length(D_e) else NA_real_,
           inherited_share_of_sitting_D_in_pool = if (length(intersect(D_e, in_pool_e6))) inter / length(intersect(D_e, in_pool_e6)) else NA_real_,
           n_sitting_D = length(D_e), n_sitting_D_in_pool_e6 = length(intersect(D_e, in_pool_e6))))
  }))
  cbind(slate, comp)
}))
for (s in statuses) contender_rows[, paste0("sh_", s) := get(paste0("n_", s)) / n_followers]
for (s in statuses) contender_rows[, paste0("any_sh_", s) := get(paste0("any_n_", s)) / any_n_followers]
setcolorder(contender_rows, c("election", "next_election", "pid", "name", "role", "is_runner_up", "sitting_president", "sitting_name"))
fwrite(contender_rows, file.path(out_dir, "camp_persistence_contenders.csv"))

# ------------------------------------------------------------------ 2. one row per transition
sh_cols <- paste0("sh_", statuses); any_sh_cols <- paste0("any_sh_", statuses)
by_tr <- rbindlist(lapply(es, function(e) {
  r <- contender_rows[election == e]; d <- r[role == "designee"]; l <- r[role != "designee"]; ru <- r[role == "runner_up"]
  lf <- l[n_followers > 0L]; la <- l[any_n_followers > 0L]            # losers with at least one (exclusive / any-tie) follower
  pooled <- l[, lapply(.SD, sum), .SDcols = paste0("n_", statuses)]
  out <- data.table(election = e, next_election = e + 6L, sitting_president = d$sitting_name, next_designee = d$name,
                    designee_tied_sitting_by_e2 = d$tied_sitting_by_e2, designee_tied_sitting_by_e4 = d$tied_sitting_by_e4,
                    designee_first_tie_sitting = d$first_tie_sitting, designee_tie_sitting_detail = d$tie_sitting_detail,
                    designee_n_followers = d$n_followers)
  out[, paste0("designee_", sh_cols) := d[, sh_cols, with = FALSE]]
  out[, `:=`(designee_jaccard_sitting_D = d$jaccard_sitting_D, inherited_share_of_sitting_D = d$inherited_share_of_sitting_D,
             inherited_share_of_sitting_D_in_pool = d$inherited_share_of_sitting_D_in_pool,
             n_sitting_D = d$n_sitting_D, n_sitting_D_in_pool_e6 = d$n_sitting_D_in_pool_e6,
             n_losers = nrow(l), n_losers_with_followers = nrow(lf),
             losers_tied_sitting_by_e2 = sum(l$tied_sitting_by_e2), losers_tied_sitting_by_e4 = sum(l$tied_sitting_by_e4),
             losers_mean_n_followers = mean(l$n_followers))]
  out[, paste0("losers_", sh_cols) := lf[, lapply(.SD, mean), .SDcols = sh_cols]]
  out[, paste0("losers_pooled_", sh_cols) := pooled / sum(unlist(pooled))]
  out[, `:=`(losers_jaccard_sitting_D = mean(lf$jaccard_sitting_D), losers_inherited_share_of_sitting_D = mean(lf$inherited_share_of_sitting_D),
             runner_up = ru$name, runner_up_tied_sitting_by_e2 = ru$tied_sitting_by_e2, runner_up_tied_sitting_by_e4 = ru$tied_sitting_by_e4,
             runner_up_n_followers = ru$n_followers)]
  out[, paste0("runner_up_", sh_cols) := if (ru$n_followers > 0L) ru[, sh_cols, with = FALSE] else as.list(rep(NA_real_, 5))]
  out[, runner_up_jaccard_sitting_D := ru$jaccard_sitting_D]
  out[, `:=`(designee_any_n_followers = d$any_n_followers, losers_any_mean_n_followers = mean(l$any_n_followers))]
  out[, paste0("designee_any_", sh_cols) := d[, any_sh_cols, with = FALSE]]
  out[, paste0("losers_any_", sh_cols) := la[, lapply(.SD, mean), .SDcols = any_sh_cols]]
  out
}))
fwrite(by_tr, file.path(out_dir, "camp_persistence_by_transition.csv"))

# ------------------------------------------------------------------ 3. equal-weight averages and the bootstrap over transitions
key <- c(paste0("designee_", sh_cols), paste0("losers_", sh_cols), paste0("losers_pooled_", sh_cols), paste0("runner_up_", sh_cols),
         paste0("designee_any_", sh_cols), paste0("losers_any_", sh_cols),
         "designee_jaccard_sitting_D", "losers_jaccard_sitting_D", "runner_up_jaccard_sitting_D",
         "inherited_share_of_sitting_D", "inherited_share_of_sitting_D_in_pool", "losers_inherited_share_of_sitting_D",
         "designee_tied_sitting_by_e2", "designee_tied_sitting_by_e4", "runner_up_tied_sitting_by_e2", "runner_up_tied_sitting_by_e4")
M <- as.matrix(by_tr[, key, with = FALSE]); n_tr <- nrow(M)
idx <- matrix(sample.int(n_tr, n_tr * B, replace = TRUE), nrow = B)
draws <- t(apply(idx, 1L, function(ix) colMeans(M[ix, , drop = FALSE], na.rm = TRUE)))   # B x key
summ <- data.table(statistic = key, estimate = colMeans(M, na.rm = TRUE),
                   ci_2.5 = apply(draws, 2L, quantile, 0.025, na.rm = TRUE), ci_97.5 = apply(draws, 2L, quantile, 0.975, na.rm = TRUE),
                   ci_5 = apply(draws, 2L, quantile, 0.05, na.rm = TRUE), ci_95 = apply(draws, 2L, quantile, 0.95, na.rm = TRUE),
                   n_transitions = colSums(!is.na(M)), source = "camp_persistence.R (equal weight per transition; bootstrap over transitions)")
# Losers tied to the sitting president, over all next-slate losers (counts, no interval).
lt <- contender_rows[role != "designee"]
summ <- rbind(summ, data.table(statistic = c("losers_tied_sitting_by_e2_share", "losers_tied_sitting_by_e4_share"),
                               estimate = c(mean(lt$tied_sitting_by_e2), mean(lt$tied_sitting_by_e4)), ci_2.5 = NA_real_, ci_97.5 = NA_real_,
                               ci_5 = NA_real_, ci_95 = NA_real_, n_transitions = n_tr,
                               source = sprintf("camp_persistence.R (share of the %d next-slate losers, person weighted)", nrow(lt))))
# (4) The sitting president's camp at e+6 (any tie, among those still eligible): transitions.R, not recomputed.
tc_path <- file.path(out_dir, "transitions_contrasts.csv")
if (file.exists(tc_path)) {
  tc <- fread(tc_path)
  g <- function(o, s) tc[outcome == o & grepl(s, stat), D]
  fate <- data.table(statistic = c("sitting_D_tied_next_designee_any", "sitting_D_tied_next_loser_only", "sitting_D_tied_no_next_contender",
                                   "sitting_D_exclusive_next_designee"),
                     estimate = c(g("tied_next_designee", "estimate"), g("tied_next_aspirant", "estimate") - g("tied_next_designee", "estimate"),
                                  1 - g("tied_next_aspirant", "estimate"), g("excl_next_designee", "estimate")),
                     ci_2.5 = c(g("tied_next_designee", "ci_2.5"), NA, NA, g("excl_next_designee", "ci_2.5")),
                     ci_97.5 = c(g("tied_next_designee", "ci_97.5"), NA, NA, g("excl_next_designee", "ci_97.5")),
                     ci_5 = c(g("tied_next_designee", "ci_5$"), NA, NA, g("excl_next_designee", "ci_5$")),
                     ci_95 = c(g("tied_next_designee", "ci_95"), NA, NA, g("excl_next_designee", "ci_95")),
                     n_transitions = n_tr, source = "transitions.R (transitions_contrasts.csv: D group at e still eligible at e+6, ties by e+4)")
  summ <- rbind(summ, fate)
}
fwrite(summ, file.path(out_dir, "camp_persistence_summary.csv"))

# ------------------------------------------------------------------ 4. console
cat("\n== next designee's exclusive followers at e+4 by status at e-2 (shares), tie to the sitting president\n")
print(by_tr[, .(election, next_election, next_designee, tied_e2 = designee_tied_sitting_by_e2, tied_e4 = designee_tied_sitting_by_e4,
                n = designee_n_followers, D = designee_sh_D, P = designee_sh_P, M = designee_sh_M, N = designee_sh_N, new = designee_sh_new,
                jaccard = designee_jaccard_sitting_D, n_losers, losers_e2 = losers_tied_sitting_by_e2, losers_e4 = losers_tied_sitting_by_e4,
                losers_n = losers_mean_n_followers, losers_D = losers_sh_D, losers_new = losers_sh_new,
                any_n = designee_any_n_followers, any_D = designee_any_sh_D, losers_any_D = losers_any_sh_D)], digits = 2)
cat("\n== equal-weight averages over", n_tr, "transitions, bootstrap over transitions (", B, "draws )\n")
print(summ[, .(statistic, estimate, ci_2.5, ci_97.5, ci_5, ci_95)], digits = 2)
cat("\nnext designees tied to the sitting president by e-2:", sum(by_tr$designee_tied_sitting_by_e2), "of", n_tr,
    "| by e+4:", sum(by_tr$designee_tied_sitting_by_e4), "of", n_tr, "\n")
cat("next losers tied by e-2:", sum(lt$tied_sitting_by_e2), "of", nrow(lt), "| by e+4:", sum(lt$tied_sitting_by_e4), "of", nrow(lt), "\n")
cat("transitions where the designee's share from D exceeds the losers' benchmark:", by_tr[, sum(designee_sh_D > losers_sh_D)], "of", n_tr, "\n")

# ------------------------------------------------------------------ 5. LaTeX table and macros
f2 <- function(x, d = 2) { r <- round(x, d); s <- formatC(r, format = "f", digits = d); s[r == 0] <- formatC(0, format = "f", digits = d); sub("^-", "$-$", s) }
pct <- function(x, d = 0) f2(100 * x, d)
mac <- function(name, value) sprintf("\\newcommand{\\%s}{%s}", name, value)
yn <- function(x) ifelse(x == 1L, "yes", "no")
S <- function(stat, col = "estimate") summ[statistic == stat, get(col)]
ci_row <- function(prefix) sprintf("{\\scriptsize [%s, %s]}", pct(S(prefix, "ci_2.5")), pct(S(prefix, "ci_97.5")))
tab <- c("% camp_persistence.tex -- the next designee's exclusive followers (ties by e+4) by their status at e-2 (camp_persistence.R)",
         "\\begin{tabular}{llccrrrrrr}", "\\toprule",
         " & & \\multicolumn{2}{c}{Tied to the sitting} & Followers & \\multicolumn{5}{c}{Status at $e-2$ (\\% of followers)} \\\\",
         " & & \\multicolumn{2}{c}{president by} & at $e+4$ & \\multicolumn{5}{c}{} \\\\",
         "\\cmidrule(lr){3-4}\\cmidrule(lr){6-10}",
         "Successions & Next designee & $e-2$ & $e+4$ & ($n$) & president's & losers' & several & unaligned & not in pool \\\\", "\\midrule")
for (k in seq_len(n_tr)) { r <- by_tr[k]
  tab <- c(tab, sprintf("%d--%d & %s & %s & %s & %d & %s & %s & %s & %s & %s \\\\", r$election, r$next_election,
                        latex_name(short_names[[as.character(r$next_election)]]), yn(r$designee_tied_sitting_by_e2), yn(r$designee_tied_sitting_by_e4),
                        r$designee_n_followers, pct(r$designee_sh_D), pct(r$designee_sh_P), pct(r$designee_sh_M), pct(r$designee_sh_N), pct(r$designee_sh_new)))
}
tab <- c(tab, "\\midrule",
         sprintf("Average & & %d of %d & %d of %d & %.0f & %s & %s & %s & %s & %s \\\\", sum(by_tr$designee_tied_sitting_by_e2), n_tr,
                 sum(by_tr$designee_tied_sitting_by_e4), n_tr, mean(by_tr$designee_n_followers),
                 pct(S("designee_sh_D")), pct(S("designee_sh_P")), pct(S("designee_sh_M")), pct(S("designee_sh_N")), pct(S("designee_sh_new"))),
         sprintf(" & & & & & %s & %s & %s & %s & %s \\\\", ci_row("designee_sh_D"), ci_row("designee_sh_P"), ci_row("designee_sh_M"),
                 ci_row("designee_sh_N"), ci_row("designee_sh_new")),
         sprintf("Next losers (benchmark) & & %d of %d & %d of %d & %.0f & %s & %s & %s & %s & %s \\\\", sum(lt$tied_sitting_by_e2), nrow(lt),
                 sum(lt$tied_sitting_by_e4), nrow(lt), mean(by_tr$losers_mean_n_followers),
                 pct(S("losers_sh_D")), pct(S("losers_sh_P")), pct(S("losers_sh_M")), pct(S("losers_sh_N")), pct(S("losers_sh_new"))),
         sprintf(" & & & & & %s & %s & %s & %s & %s \\\\", ci_row("losers_sh_D"), ci_row("losers_sh_P"), ci_row("losers_sh_M"),
                 ci_row("losers_sh_N"), ci_row("losers_sh_new")),
         "\\bottomrule", "\\end{tabular}")
writeLines(tab, file.path(tab_dir, "camp_persistence.tex"))

macros <- c("% persistence_macros.tex (camp_persistence.R). Shares in percent (Jaccard too); Lo/Hi = 95% bootstrap over transitions, LoNinety/HiNinety = 90%. Do not edit by hand.")
with_ci <- function(name, stat) c(mac(name, pct(S(stat))), mac(paste0(name, "Lo"), pct(S(stat, "ci_2.5"))), mac(paste0(name, "Hi"), pct(S(stat, "ci_97.5"))),
                                  mac(paste0(name, "LoNinety"), pct(S(stat, "ci_5"))), mac(paste0(name, "HiNinety"), pct(S(stat, "ci_95"))))
macros <- c(macros, with_ci("CPnextFromD", "designee_sh_D"), with_ci("CPnextFromDLosers", "losers_sh_D"), with_ci("CPnextFromP", "designee_sh_P"),
            with_ci("CPnextFromM", "designee_sh_M"), with_ci("CPnextFromN", "designee_sh_N"), with_ci("CPnextNew", "designee_sh_new"),
            with_ci("CPnextNewLosers", "losers_sh_new"), with_ci("CPjaccardD", "designee_jaccard_sitting_D"), with_ci("CPjaccardLosers", "losers_jaccard_sitting_D"),
            with_ci("CPinherited", "inherited_share_of_sitting_D"), with_ci("CPinheritedInPool", "inherited_share_of_sitting_D_in_pool"),
            with_ci("CPnextFromDAny", "designee_any_sh_D"), with_ci("CPnextFromDAnyLosers", "losers_any_sh_D"),
            mac("CPnextFollowersAnyMean", sprintf("%.0f", mean(by_tr$designee_any_n_followers))),
            mac("CPdesigneeTiedSitting", sum(by_tr$designee_tied_sitting_by_e2)), mac("CPdesigneeTiedSittingLate", sum(by_tr$designee_tied_sitting_by_e4)),
            mac("CPnTransitions", n_tr), mac("CPnNextLosers", nrow(lt)),
            mac("CPlosersTiedSitting", sum(lt$tied_sitting_by_e2)), mac("CPlosersTiedSittingLate", sum(lt$tied_sitting_by_e4)),
            mac("CPdesigneeAboveLosers", by_tr[, sum(designee_sh_D > losers_sh_D)]),
            mac("CPnextFollowersMean", sprintf("%.0f", mean(by_tr$designee_n_followers))), mac("CPlosersFollowersMean", sprintf("%.0f", mean(by_tr$losers_mean_n_followers))))
if (file.exists(tc_path)) macros <- c(macros, mac("CPsittingTiedNextAny", pct(S("sitting_D_tied_next_designee_any"))),
                                      mac("CPsittingTiedNextLoserOnly", pct(S("sitting_D_tied_next_loser_only"))),
                                      mac("CPsittingTiedNone", pct(S("sitting_D_tied_no_next_contender"))))
writeLines(macros, file.path(tab_dir, "persistence_macros.tex"))

# ------------------------------------------------------------------ 6. figure: stacked bars of the next designee's camp by status at e-2
rows <- rbind(by_tr[, .(row = sprintf("%d to %d: %s", election, next_election, short_names[as.character(next_election)]),
                        D = designee_sh_D, P = designee_sh_P, M = designee_sh_M, N = designee_sh_N, new = designee_sh_new)],
              data.table(row = "Average", D = S("designee_sh_D"), P = S("designee_sh_P"), M = S("designee_sh_M"), N = S("designee_sh_N"), new = S("designee_sh_new")),
              data.table(row = "Next losers (benchmark)", D = S("losers_sh_D"), P = S("losers_sh_P"), M = S("losers_sh_M"), N = S("losers_sh_N"), new = S("losers_sh_new")))
fl <- melt(rows, id.vars = "row", variable.name = "status", value.name = "share")
fl[, status := factor(status, statuses, labels = status_labels[statuses])]
fl[, row := factor(row, rev(rows$row))]
fl[, `:=`(label = fifelse(share >= 0.045, sprintf("%.0f", 100 * share), ""),
          ink = fifelse(status %in% status_labels[c("D", "P")], "white", INK))]
fills <- setNames(c(INK, "#6b6b6b", "#a3a3a3", "#cccccc", "#ececec"), status_labels[statuses])
gp <- ggplot(fl, aes(x = 100 * share, y = row, fill = status)) +
  geom_col(position = position_stack(reverse = TRUE), colour = "white", linewidth = 0.4, width = 0.74) +
  geom_text(aes(label = label, colour = ink, group = status), position = position_stack(vjust = 0.5, reverse = TRUE), size = 4, family = FAM,
            show.legend = FALSE) +
  geom_hline(yintercept = 2.5, colour = RULE, linewidth = 0.35, linetype = "dashed") +
  scale_fill_manual(values = fills) + scale_colour_identity() +
  scale_x_continuous(limits = c(0, 100.5), breaks = seq(0, 100, 25), expand = expansion(mult = c(0, 0.01))) +
  guides(fill = guide_legend(nrow = 1, byrow = TRUE)) +
  labs(x = "Share of the next designee's exclusive followers at e+4, by their status at e-2 (%)", y = NULL) + theme_paper(17) +
  theme(legend.position = "top", legend.location = "plot", legend.justification = "left", legend.title = element_blank(), legend.margin = margin(0, 0, 0, 0),
        legend.text = element_text(size = 12, colour = INK), legend.key.size = unit(0.42, "cm"), legend.spacing.x = unit(0.2, "cm"),
        axis.text.y = element_text(size = 13.5, colour = INK), axis.line.y = element_blank(), axis.ticks.y = element_blank(),
        axis.title.x = element_text(size = 14))
ggsave(file.path(out_dir, "camp_persistence.pdf"), gp, width = 10, height = 4.1, bg = "white", device = "pdf")
ggsave(file.path(out_dir, "camp_persistence.png"), gp, width = 10, height = 4.1, dpi = 250, bg = "white")
cat("written:", file.path(out_dir, c("camp_persistence_by_transition.csv", "camp_persistence_summary.csv", "camp_persistence_contenders.csv",
                                     "camp_persistence.pdf", "camp_persistence.png", "tables/camp_persistence.tex", "tables/persistence_macros.tex")), sep = "\n")
