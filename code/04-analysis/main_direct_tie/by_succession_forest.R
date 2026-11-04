# The premium succession by succession (4 November 2026; coauthor: "were some transitions more cronystic than others?").
# Per-succession contrast of the years 1-4 average outcome (event-study covariates, formula_es), designee's minus
# losers' followers, with Ferman-Pinto intervals from the POOLED shock model: the variance components A + B/n and the
# standardized donor residuals are fitted once on all 45 losing camps (design_tools.R boot_errors), and each
# succession's error is the same network-shock draw weighted by that succession's linear weights (a_i 1[e_i = e] /
# omega_e). A per-succession fit would rest on 2-7 donors. Joint draws also give a dispersion test: the standard
# deviation of the nine estimates against its distribution when every succession shares the pooled premium.
# Writes by_succession_forest.csv, by_succession_dispersion.csv, the figure by_succession_forest.{pdf,png} and
# tables/by_succession_forest_macros.tex. Run after estimate_main.R: Rscript code/04-analysis/main_direct_tie/by_succession_forest.R
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
invisible(capture.output(source(file.path(script_dir, "estimate_main.R"))))
source(file.path(script_dir, "design_tools.R"))
tab_dir <- file.path(out_dir, "tables"); dir.create(tab_dir, showWarnings = FALSE)
B_f <- 20000L; set.seed(4112026L)
Yk <- sapply(c(-2L, 1:4), function(k) year_value(annual, k)); colnames(Yk) <- c(-2L, 1:4)
y <- rowMeans(Yk[, as.character(1:4), drop = FALSE]) - Yk[, "-2"]
d <- build_design(formula = formula_es)
stopifnot(identical(d$rows, seq_len(nrow(sample))))
pooled <- sum(d$a * y)
headline <- fread(file.path(out_dir, "event_study_summary.csv"))[outcome == "rank" & contrast == "main_window_average", estimate]
stopifnot(abs(pooled - headline) < 1e-6)
# shock model from the pooled design
r_y <- as.vector(d$Q %*% y[d$ctrl]); ab <- fit_variance_components(r_y, d$moments)
z <- r_y / sqrt(pmax(as.vector(d$moments %*% ab), .Machine$double.eps)); z <- (z - mean(z)) / sd(z)
idx <- matrix(base::sample.int(d$K, length(d$g) * B_f, replace = TRUE), nrow = length(d$g))
shocks <- sqrt(ab[1] + ab[2] / d$n_eff) * matrix(z[idx], nrow = nrow(idx))      # network x draw
nets <- data.table(network = d$S$network)[, .(first = .I[1]), by = network]$network   # order of d$g
# linear weights of succession e's contrast: 1/n_e on its designee's followers and, on EVERY losing follower, the
# weight that the common loser model gives them for that succession's treated covariate mean (sum_e omega_e a_e = d$a)
a_for <- function(e) {
  tr <- d$S$treated == 1L; el <- d$S$election; a <- numeric(nrow(d$S))
  b_e <- colMeans(d$X[tr & el == e, , drop = FALSE])
  a[d$ctrl] <- -d$w0 * as.vector(d$X0 %*% (d$M %*% b_e)); ix <- which(tr & el == e); a[ix] <- 1 / length(ix); a
}
A_e <- sapply(elections, a_for); colnames(A_e) <- elections
stopifnot(max(abs(as.vector(A_e %*% omega[as.character(elections)]) - d$a)) < 1e-10)
G <- sapply(elections, function(e) data.table(network = d$S$network, a = A_e[, as.character(e)])[, .(g = sum(a)), by = network][match(nets, network), g])
colnames(G) <- elections
est <- as.vector(crossprod(A_e, y))
err <- t(G) %*% shocks                                                            # succession x draw
chk <- by_succession_d(d, y); stopifnot(max(abs(chk$estimate[match(elections, chk$election)] - est)) < 1e-8)
q <- function(v, p) as.numeric(quantile(v, p, type = 1, names = FALSE))
forest <- data.table(election = elections, estimate = est,
  ci_lower = est - apply(err, 1, q, .975), ci_upper = est - apply(err, 1, q, .025),
  ci90_lower = est - apply(err, 1, q, .95), ci90_upper = est - apply(err, 1, q, .05),
  n_designee = sample[treated == 1L, .N, by = election][match(elections, election), N],
  n_losers = sample[treated == 0L, .N, by = election][match(elections, election), N], weight = omega[as.character(elections)])
fwrite(forest, file.path(out_dir, "by_succession_forest.csv"))
# dispersion under a common premium
sd_obs <- sd(est); sd_null <- apply(pooled + err, 2, sd)
disp <- data.table(sd_observed = sd_obs, sd_expected = mean(sd_null), sd_null_q95 = q(sd_null, .95), p_value = mean(sd_null >= sd_obs),
                   range_observed = diff(range(est)), p_range = mean(apply(pooled + err, 2, function(v) diff(range(v))) >= diff(range(est))),
                   positive = sum(est > 0), pooled = pooled, A_network = ab[1], B_person = ab[2])
fwrite(disp, file.path(out_dir, "by_succession_dispersion.csv"))
cat("Premium by succession (years 1-4 average), pooled", round(pooled, 3), "\n"); print(forest[, lapply(.SD, function(x) if (is.numeric(x)) round(x, 2) else x)])
cat(sprintf("dispersion: SD of the nine %.2f, expected under a common premium %.2f (95th pct %.2f), p = %.2f; range p = %.2f\n",
            sd_obs, disp$sd_expected, disp$sd_null_q95, disp$p_value, disp$p_range))
# ------------------------------------------------------------------ figure
designees <- c("1940" = "Ávila Camacho", "1946" = "Alemán", "1952" = "Ruiz Cortines", "1958" = "López Mateos", "1964" = "Díaz Ordaz",
               "1970" = "Echeverría", "1976" = "López Portillo", "1982" = "de la Madrid", "1988" = "Salinas")
pf <- copy(forest)[, lab := paste0(election, "\n", designees[as.character(election)])]
pf[, x := seq_along(election)]
top <- max(pf$ci_upper); bot <- min(pf$ci_lower); span <- top - bot
g <- ggplot(pf, aes(x = x, y = estimate)) +
  geom_hline(yintercept = 0, colour = RULE, linewidth = 0.35) +
  annotate("segment", x = 0.5, xend = 9.5, y = pooled, yend = pooled, colour = "#940034", linewidth = 0.9, linetype = "dashed") +
  annotate("text", x = 9.5, y = pooled, label = sprintf("pooled %.2f", pooled), colour = "#940034", hjust = 1, vjust = -0.5, size = 4.2, family = FAM) +
  geom_linerange(aes(ymin = ci_lower, ymax = ci_upper), colour = INK, linewidth = 0.45) +
  geom_linerange(aes(ymin = ci90_lower, ymax = ci90_upper), colour = INK, linewidth = 1.5) +
  geom_point(aes(size = n_designee), colour = INK) + scale_size_area(max_size = 5, guide = "none") +
  scale_x_continuous(breaks = pf$x, labels = pf$lab) +
  coord_cartesian(ylim = c(bot - 0.03 * span, top + 0.08 * span), clip = "off") +
  labs(x = NULL, y = "Premium, years 1 to 4,\ndesignee's minus losers' followers") + theme_paper(17) +
  theme(axis.text.x = element_text(size = 10, lineheight = 0.85), axis.title.y = element_text(size = 14, lineheight = 0.95))
ggsave(file.path(out_dir, "by_succession_forest.pdf"), g, width = 10, height = 4.3, bg = "white", device = "pdf")
ggsave(file.path(out_dir, "by_succession_forest.png"), g, width = 10, height = 4.3, dpi = 250, bg = "white")
# ------------------------------------------------------------------ macros
f2 <- function(x) sub("^-", "$-$", formatC(x, format = "f", digits = 2)); f1 <- function(x) formatC(x, format = "f", digits = 1)
mac <- function(n, v) sprintf("\\newcommand{\\%s}{%s}", n, v)
o <- forest[order(-estimate)]
writeLines(c("% by_succession_forest_macros.tex (by_succession_forest.R). Do not edit by hand.",
  mac("BSFsdObs", f2(sd_obs)), mac("BSFsdExp", f2(disp$sd_expected)), mac("BSFp", formatC(disp$p_value, format = "f", digits = 2)),
  mac("BSFpositive", disp$positive), mac("BSFsignificant", sum(forest$ci_lower > 0)),
  mac("BSFtopYear", o$election[1]), mac("BSFtopEst", f2(o$estimate[1])), mac("BSFsecondYear", o$election[2]), mac("BSFsecondEst", f2(o$estimate[2])),
  mac("BSFlowYear", o$election[nrow(o)]), mac("BSFlowEst", f2(o$estimate[nrow(o)])), mac("BSFlowTwoYear", o$election[nrow(o) - 1]), mac("BSFlowTwoEst", f2(o$estimate[nrow(o) - 1])),
  mac("BSFpooled", f2(pooled))),
  file.path(tab_dir, "by_succession_forest_macros.tex"))
cat("by_succession_forest done\n")
