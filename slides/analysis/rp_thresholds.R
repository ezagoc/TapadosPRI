# Where on the ladder the reward and the penalty happen (4 November 2026). The reward / penalty design of MAIN_SPEC
# section 11 (rp_setup.R: designee's followers D and losing contenders' followers P, each against the same
# entropy-reweighted unaligned N, window covariates, the estimator's succession weights) applied to the threshold
# outcomes 1[post rank >= r] - 1[pre rank >= r], r = 1..9: reward_r = D minus N, penalty_r = P minus N (signed), in
# percentage points. The penalty is the exact one (rp_fit_exact, 5 November 2026): measured for the same politicians as the
# threshold DiD of nonlinear_did.R (the main design, formula_x), so reward - penalty equals that DiD rung by rung. The DiD
# itself is in the table as group "G" (the same draws as nonlinear_did.R), with the reward's and the penalty's shares of it.
# Writes rp_thresholds.csv, the figures rp_thresholds.{pdf,png} (reward and penalty) and rp_thresholds_gap.{pdf,png} (the
# DiD alone, same style) and tables/rp_thresholds_macros.tex. Run after estimate_main.R:
#   Rscript slides/analysis/rp_thresholds.R
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
invisible(capture.output(source(file.path(script_dir, "estimate_main.R"))))
source(file.path(script_dir, "design_tools.R"))
invisible(capture.output(source(file.path(script_dir, "rp_setup.R"))))
set.seed(4112026L)
tab_dir <- file.path(out_dir, "tables"); dir.create(tab_dir, showWarnings = FALSE)
f_window <- ~ election_factor + pre_band + earlier_band + age + ldeg + lrec + prior_status + fed_exec
S_main <- make_weights(A[support == TRUE], bal_formula_window)
stopifnot(all(c("pre", "post") %in% names(S_main)))
rungs <- 1:9
d_main <- build_design()                                          # the threshold DiDs of nonlinear_did.R
Ym <- sapply(rungs, function(r) as.numeric(sample$post >= r) - as.numeric(sample$pre >= r)); colnames(Ym) <- paste0("rung", rungs)
res <- rbindlist(lapply(rungs, function(r) {
  y <- as.numeric(S_main$post >= r) - as.numeric(S_main$pre >= r)
  out <- rp_inference(S_main, rp_fit_exact(S_main, y, f_window, d_main, Ym[d_main$rows, r]), B = 20000L)
  out[, `:=`(rung = r, share_pre_D = mean(S_main[group == "D", pre] >= r), share_pre_P = mean(S_main[group == "P", pre] >= r),
             share_post_P = mean(S_main[group == "P", post] >= r))]   # the losers' followers' rate after the succession, the base of the relative gap
  out
}))
gap <- estimate_columns(d_main, Ym[d_main$rows, , drop = FALSE], B = 20000L, seed = 3112026L)$table[, rung := rungs]
stopifnot(max(abs(res[group == "D", estimate][order(res[group == "D", rung])] - res[group == "P", estimate][order(res[group == "P", rung])] - gap$estimate)) < 1e-8)
res <- rbind(res, gap[, .(group = "G", estimate, ci_lower, ci_upper, ci90_lower, ci90_upper, p_value = p_bootstrap,
                          inference = "main design (designee's minus losers' followers), Ferman-Pinto bootstrap", rung)], fill = TRUE)
res[, `:=`(gap = gap$estimate[match(rung, gap$rung)])][, share_of_gap := estimate / gap]
fwrite(res, file.path(out_dir, "rp_thresholds.csv"))
cat("Gap (D - P, main design) and its split, pp and shares:\n")
print(res[group != "G", .(rung, group, pp = round(100 * estimate, 1), gap_pp = round(100 * gap, 1), share = round(100 * share_of_gap))])
cat("Reward (D - N) and penalty (P - N) on 1[rank >= r], window change, pp:\n")
print(dcast(res[, .(rung, group, pp = round(100 * estimate, 1), lo = round(100 * ci_lower, 1), hi = round(100 * ci_upper, 1))], rung ~ group, value.var = c("pp", "lo", "hi")))

# ------------------------------------------------------------------ figure
labs_r <- c("1" = "any post", "2" = "mayor,\nadviser", "3" = "dept.\nhead", "4" = "area\ndirector", "5" = "deputy\nDG", "6" = "director\ngeneral",
            "7" = "under-\nsecretary", "8" = "major\ngovernor", "9" = "cabinet")
pd <- copy(res[group != "G"])[, `:=`(est = 100 * estimate, lo = 100 * ci_lower, hi = 100 * ci_upper, lo90 = 100 * ci90_lower, hi90 = 100 * ci90_upper)]
pd[, grp := factor(fifelse(group == "D", "Reward: designee's followers minus unaligned", "Penalty: a tie to a loser, same politicians"),
                   levels = c("Reward: designee's followers minus unaligned", "Penalty: a tie to a loser, same politicians"))]
pd[, x := rung + fifelse(group == "D", -0.15, 0.15)]
# the gap alone, same style, for the slide that precedes the split
pg <- copy(res[group == "G"])[, `:=`(est = 100 * estimate, lo = 100 * ci_lower, hi = 100 * ci_upper, lo90 = 100 * ci90_lower, hi90 = 100 * ci90_upper, x = rung)]
gg <- ggplot(pg, aes(x = x, y = est)) +
  geom_hline(yintercept = 0, colour = "#a1a1aa", linewidth = 0.4) +
  geom_linerange(aes(ymin = lo, ymax = hi), linewidth = 0.5, colour = "#18181b") + geom_linerange(aes(ymin = lo90, ymax = hi90), linewidth = 1.3, colour = "#18181b") +
  geom_point(size = 2.4, colour = "#18181b") +
  scale_x_continuous(breaks = rungs, labels = paste0(rungs, "\n", labs_r[as.character(rungs)])) +
  labs(x = "Rung r of the office ladder (outcome: holds a post at rung r or above)", y = "Designee's minus losers' followers,\nchange in the share at rung r or above (pp)") +
  theme_classic(base_size = 13) +
  theme(axis.text.x = element_text(size = 9, lineheight = 0.9), axis.line = element_line(colour = "#a1a1aa", linewidth = 0.35),
        plot.background = element_rect(fill = "white", colour = NA))
ggsave(file.path(out_dir, "rp_thresholds_gap.pdf"), gg, width = 9, height = 4.2); ggsave(file.path(out_dir, "rp_thresholds_gap.png"), gg, width = 9, height = 4.2, dpi = 200)
g <- ggplot(pd, aes(x = x, y = est, colour = grp, shape = grp)) +
  geom_hline(yintercept = 0, colour = "#a1a1aa", linewidth = 0.4) +
  geom_linerange(aes(ymin = lo, ymax = hi), linewidth = 0.5) + geom_linerange(aes(ymin = lo90, ymax = hi90), linewidth = 1.3) +
  geom_point(size = 2.4, fill = "white") +
  scale_colour_manual(values = c("#18181b", "#7a7a7a")) + scale_shape_manual(values = c(16, 21)) +
  scale_x_continuous(breaks = rungs, labels = paste0(rungs, "\n", labs_r[as.character(rungs)])) +
  labs(x = "Rung r of the office ladder (outcome: holds a post at rung r or above)", y = "Change in the share at rung r or above (pp)", colour = NULL, shape = NULL) +
  theme_classic(base_size = 13) +
  theme(legend.position = c(0.22, 0.92), axis.text.x = element_text(size = 9, lineheight = 0.9),
        axis.line = element_line(colour = "#a1a1aa", linewidth = 0.35), plot.background = element_rect(fill = "white", colour = NA))
ggsave(file.path(out_dir, "rp_thresholds.pdf"), g, width = 9, height = 4.2); ggsave(file.path(out_dir, "rp_thresholds.png"), g, width = 9, height = 4.2, dpi = 200)

# ------------------------------------------------------------------ macros
f1 <- function(x) { v <- round(x, 1); s <- formatC(abs(v), format = "f", digits = 1); ifelse(v < 0, paste0("$-$", s), s) }   # typeset minus
v <- function(G, r, what = "estimate") 100 * res[group == G & rung == r][[what]]
peakD <- res[group == "D"][which.max(estimate), rung]; peakP <- res[group == "P"][which.min(estimate), rung]
mac <- function(n, x) sprintf("\\newcommand{\\%s}{%s}", n, x)
lab_m <- c("Any", "Mayor", "Dept", "Area", "DepDG", "DG", "Under", "Gov", "Cab")
f0 <- function(x) formatC(round(x), format = "d")
by_rung <- unlist(lapply(rungs, function(r) {
  G <- res[group == "G" & rung == r]; D <- res[group == "D" & rung == r]; P <- res[group == "P" & rung == r]
  c(mac(paste0("RPTHgap", lab_m[r]), f1(100 * G$estimate)), mac(paste0("RPTHgap", lab_m[r], "Lo"), f1(100 * G$ci_lower)), mac(paste0("RPTHgap", lab_m[r], "Hi"), f1(100 * G$ci_upper)),
    mac(paste0("RPTHreward", lab_m[r], "Pp"), f1(100 * D$estimate)), mac(paste0("RPTHpenalty", lab_m[r], "Pp"), f1(100 * P$estimate)),
    mac(paste0("RPTHrewardShare", lab_m[r]), f0(100 * D$share_of_gap)), mac(paste0("RPTHpenaltyShare", lab_m[r]), f0(-100 * P$share_of_gap)),
    mac(paste0("RPTHrateP", lab_m[r]), f0(100 * D$share_post_P)), mac(paste0("RPTHrel", lab_m[r]), f0(100 * G$estimate / D$share_post_P)),
    mac(paste0("RPTHpenalty", lab_m[r], "Abs"), f1(abs(100 * P$estimate))), mac(paste0("RPTHpenalty", lab_m[r], "Lo"), f1(100 * P$ci_lower)), mac(paste0("RPTHpenalty", lab_m[r], "Hi"), f1(100 * P$ci_upper)),
    mac(paste0("RPTHreward", lab_m[r], "Lo"), f1(100 * D$ci_lower)), mac(paste0("RPTHreward", lab_m[r], "Hi"), f1(100 * D$ci_upper)))
}))
writeLines(c("% rp_thresholds_macros.tex (rp_thresholds.R): reward and exact penalty by rung, pp; the gap (main design) and the shares of it. Do not edit by hand.",
  by_rung,
  mac("RPTHrewardPeakRung", peakD), mac("RPTHrewardPeak", f1(v("D", peakD))), mac("RPTHrewardPeakLo", f1(v("D", peakD, "ci_lower"))), mac("RPTHrewardPeakHi", f1(v("D", peakD, "ci_upper"))),
  mac("RPTHpenaltyPeakRung", peakP), mac("RPTHpenaltyPeak", f1(abs(v("P", peakP)))), mac("RPTHpenaltyPeakLo", f1(abs(v("P", peakP, "ci_upper")))), mac("RPTHpenaltyPeakHi", f1(abs(v("P", peakP, "ci_lower")))),
  mac("RPTHrewardAny", f1(v("D", 1))), mac("RPTHpenaltyAny", f1(v("P", 1))), mac("RPTHrewardCab", f1(v("D", 9))), mac("RPTHpenaltyCab", f1(v("P", 9))),
  mac("RPTHrewardDG", f1(v("D", 6))), mac("RPTHpenaltyDG", f1(v("P", 6))), mac("RPTHrewardUnder", f1(v("D", 7))), mac("RPTHpenaltyUnder", f1(v("P", 7)))),
  file.path(tab_dir, "rp_thresholds_macros.tex"))
cat("rp_thresholds done\n")
