# Raw trajectories behind the reward-and-penalty decomposition (MAIN_SPEC section 11), shown before any contrast as
# Colonnelli-Prem-Teso (2020, Fig. 1a) and Akhtari-Moreira-Trucco (2022, Fig. A.9) do: mean rank position and share
# in office by year relative to the election for the designee's followers (D), the losers' followers (P), the unaligned
# reweighted as in the design (N), and, for reference, the unaligned within two steps of the designee and those three or
# more steps away (re-balanced on their own). Equal weight per succession. Run after estimate_main.R:
#   Rscript code/04-analysis/main_direct_tie/rp_raw_trajectories.R
# Writes rp_raw_trajectories.csv and rp_raw_trajectories.{pdf,png} to the output folder.
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
invisible(capture.output(source(file.path(script_dir, "estimate_main.R"))))
source(file.path(script_dir, "design_tools.R"))
set.seed(18102026L)
source(file.path(script_dir, "rp_setup.R"))
S <- make_weights(A[support == TRUE], bal_formula_es)
# distance to the designee: two steps = a dated tie formed by e-2 to one of his exclusive followers
lt <- dated[edge_type %in% tie_types]
lt_long <- rbindlist(list(lt[, .(pid = person_a, other = person_b, year_start)], lt[, .(pid = person_b, other = person_a, year_start)]))
S[, two_step := FALSE]
for (e in elections) {
  dmem <- S[election == e & group == "D", pid]
  near <- unique(lt_long[other %in% dmem & year_start <= e - 2L, pid])
  S[election == e & group == "N" & pid %in% near, two_step := TRUE]
}
S[, wt := 1 / .N, by = .(election, group)]; S[group == "N", wt := w]
S3 <- make_weights(A[support == TRUE & !(paste(pid, election) %in% S[group == "N" & two_step == TRUE, paste(pid, election)])], bal_formula_es)
S3[, wt := 1 / .N, by = .(election, group)]; S3[group == "N", wt := w]
ranks_of <- function(SS) YA[match(paste(SS$pid, SS$election), paste(A$pid, A$election)), ]
traj <- function(SS, keep, lab) {
  YY <- ranks_of(SS)
  rbindlist(lapply(seq_along(ks), function(j) {
    d <- data.table(e = SS$election[keep], w = SS$wt[keep], y = YY[keep, j])
    by_e <- d[, .(rank = sum(w * y) / sum(w), office = sum(w * (y > 0)) / sum(w), top = sum(w * (y >= 7)) / sum(w)), by = e]
    om <- omega[as.character(by_e$e)]; om <- om / sum(om)   # the main estimand's succession weights
    data.table(group = lab, k = ks[j], rank = sum(om * by_e$rank), office = sum(om * by_e$office), top = sum(om * by_e$top), n = sum(keep))
  }))
}
tr <- rbind(traj(S, S$group == "D", "Designee's followers"),
            traj(S, S$group == "P", "Losers' followers"),
            traj(S, S$group == "N", "Unaligned, reweighted"),
            traj(S, S$group == "N" & S$two_step, "Unaligned two steps from the designee"),
            traj(S3, S3$group == "N", "Unaligned three or more steps away, reweighted"))
fwrite(tr, file.path(out_dir, "rp_raw_trajectories.csv"))
cat(sprintf("unaligned in support: %d; within two steps of the designee: %.1f%%; three or more steps: %d\n",
            sum(S$group == "N"), 100 * mean(S[group == "N", two_step]), sum(S3$group == "N")))
# figure: levels by group; the designation (the treatment) in near-black, the handovers in grey
# the two distance groups stay in the CSV for reference; the figure shows the three groups of the design
pd <- tr[group %in% c("Designee's followers", "Losers' followers", "Unaligned, reweighted")]
lv <- c("Designee's followers", "Losers' followers", "Unaligned, reweighted")
pd[, group := factor(group, levels = lv)]
mk <- data.table(x = c(-1.5, 0.5, 6.5), lab = c("Designation", "New president", "Next president"), col = c(INK, RULE, RULE), lw = c(0.6, 0.35, 0.35))
top <- max(pd$rank); bot <- min(pd$rank); span <- top - bot
g <- ggplot(pd, aes(k, rank, colour = group, shape = group, linetype = group)) +
  geom_vline(data = mk, aes(xintercept = x), colour = mk$col, linewidth = mk$lw, linetype = "dashed") +
  geom_text(data = mk, aes(x = x + 0.12, y = top + 0.10 * span, label = lab), inherit.aes = FALSE, hjust = 0, vjust = 0,
            colour = mk$col, size = 4.2, family = FAM) +
  geom_line(linewidth = 0.6) + geom_point(size = 2.4, fill = "white", stroke = 0.8) +
  scale_colour_manual(values = c(INK, "#7a7a7a", "#940034"), name = NULL) +
  scale_shape_manual(values = c(16, 21, 17), name = NULL) +
  scale_linetype_manual(values = c("solid", "solid", "solid"), name = NULL) +
  scale_x_continuous(breaks = ks, labels = k_numbers) +
  coord_cartesian(ylim = c(bot - 0.05 * span, top + 0.22 * span), clip = "off") +
  labs(x = x_label_k, y = "Mean rank position\n(0 if no recorded post)") + theme_paper(17) +
  theme(legend.position = "inside", legend.position.inside = c(0.12, 0.02), legend.justification = c(0, 0),
        legend.text = element_text(size = 12, colour = INK), legend.key = element_blank(), legend.background = element_blank(),
        legend.key.width = unit(1.6, "lines"), axis.title.y = element_text(size = 14, lineheight = 0.95))
ggsave(file.path(out_dir, "rp_raw_trajectories.pdf"), g, width = 10, height = 4.6, bg = "white", device = "pdf")
ggsave(file.path(out_dir, "rp_raw_trajectories.png"), g, width = 10, height = 4.6, dpi = 250, bg = "white")
cat("Wrote:", file.path(out_dir, "rp_raw_trajectories.{csv,pdf,png}"), "\n")
