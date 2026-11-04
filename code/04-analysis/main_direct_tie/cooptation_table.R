# The losing contenders the new president kept, and the penalty on their followers (4 November 2026). Reads the
# pre-registered co-optation test (cooptation_tests.R, MAIN_SPEC section 15: within each succession with mixed
# retention, is the loser who kept a top chair the one with the larger camp? exact permutation test on the
# standardized log camp size) and the chair split (chair_split.R, section 12: losers' followers against the reweighted
# unaligned, split by whether their patron kept a top chair in the new president's first two years), plus the patron
# table (chair_split_patrons.csv) for the descriptive counts. Writes tables/cooptation.tex and
# tables/cooptation_macros.tex. Run after cooptation_tests.R and chair_split.R:
#   Rscript code/04-analysis/main_direct_tie/cooptation_table.R
suppressPackageStartupMessages(library(data.table))
db_root <- Sys.getenv("TAPADOSPRI_DB_ROOT", file.path(path.expand("~"), "Dropbox", "TapadosPRI"))
out_dir <- Sys.getenv("TAPADOS_MAIN_OUTPUT_DIR", file.path(db_root, "output", "main_direct_tie"))
data_dir <- Sys.getenv("TAPADOSPRI_DATA_DIR", file.path(db_root, "data"))
tab_dir <- file.path(out_dir, "tables"); dir.create(tab_dir, showWarnings = FALSE)
p1 <- fread(file.path(out_dir, "cooptation_p1.csv"))[measure == "threat"]
p2 <- fread(file.path(out_dir, "cooptation_p2.csv"))
cs <- fread(file.path(out_dir, "chair_split_windows.csv"))[spec == "Main"]
pat <- fread(file.path(out_dir, "chair_split_patrons.csv"))
asp <- fread(file.path(data_dir, "structural", "aspirants.csv"))[slate == "main"]
pat[, name := asp$name[match(paste(election, patron), paste(asp$election, asp$pid))]]
# descriptive: in successions where some losers kept a top chair and some did not, did the largest camp keep one?
mixed <- pat[, .(kept = sum(kept), losers = .N, largest_kept = kept[which.max(followers)], largest = name[which.max(followers)], largest_n = max(followers)), by = election][kept > 0 & kept < losers]
kept_all <- pat[kept == 1L][order(election)]
pk <- cs[grepl("^Pk", estimate)]; pl <- cs[grepl("^Pl", estimate)]
f2 <- function(x) sub("^-", "$-$", formatC(x, format = "f", digits = 2))
ci <- function(lo, hi) sprintf("[%s, %s]", f2(lo), f2(hi))
lines <- c("% cooptation.tex (cooptation_table.R). Do not edit by hand.",
  "\\begin{tabular}{lcc}", "\\toprule",
  " & Estimate & 95\\% interval \\\\", "\\midrule",
  "\\multicolumn{3}{l}{\\textit{A. Whom the new president kept (exact permutation test within succession)}} \\\\",
  sprintf("Camp size of the losers who kept a top chair, standardized & %s & $p = %s$ \\\\", f2(p1$statistic), formatC(p1$p_one_sided, format = "f", digits = 3)),
  sprintf("Expected under random retention & %s & \\\\", f2(p1$mean_under_null)),
  sprintf("Largest camp kept a chair & %d of %d successions & \\\\", sum(mixed$largest_kept), nrow(mixed)),
  "\\addlinespace[3pt]",
  "\\multicolumn{3}{l}{\\textit{B. Losers' followers against the reweighted unaligned, window $e+1$..$e+4$}} \\\\",
  sprintf("Patron kept a top chair (%d patrons) & %s & %s \\\\", pk$groups_treated, f2(pk$value), ci(pk$wild_lower, pk$wild_upper)),
  sprintf("Patron lost it (%d patrons) & %s & %s \\\\", pl$groups_treated, f2(pl$value), ci(pl$wild_lower, pl$wild_upper)),
  "\\bottomrule", "\\end{tabular}")
writeLines(lines, file.path(tab_dir, "cooptation.tex"))
mac <- function(n, v) sprintf("\\newcommand{\\%s}{%s}", n, v)
writeLines(c("% cooptation_macros.tex (cooptation_table.R). Do not edit by hand.",
  mac("COOPstat", f2(p1$statistic)), mac("COOPnull", f2(p1$mean_under_null)), mac("COOPp", formatC(p1$p_one_sided, format = "f", digits = 3)),
  mac("COOPperms", format(p1$permutations, big.mark = ",")), mac("COOPmixed", nrow(mixed)), mac("COOPlargestKept", sum(mixed$largest_kept)),
  mac("COOPkeptN", nrow(kept_all)), mac("COOPlosersN", nrow(pat)), mac("COOPkeptNames", paste(sprintf("%s (%d)", kept_all$name, kept_all$election), collapse = ", ")),
  mac("CSkept", f2(pk$value)), mac("CSkeptLo", f2(pk$wild_lower)), mac("CSkeptHi", f2(pk$wild_upper)), mac("CSkeptPatrons", pk$groups_treated),
  mac("CSlost", f2(pl$value)), mac("CSlostAbs", f2(abs(pl$value))), mac("CSlostLo", f2(pl$wild_lower)), mac("CSlostHi", f2(pl$wild_upper)), mac("CSlostPatrons", pl$groups_treated), mac("CSlostP", formatC(pl$p_wild, format = "f", digits = 3))),
  file.path(tab_dir, "cooptation_macros.tex"))
cat("mixed successions:\n"); print(mixed); cat("kept:", paste(sprintf("%s (%d)", kept_all$name, kept_all$election), collapse = "; "), "\n"); cat("cooptation_table done\n")
