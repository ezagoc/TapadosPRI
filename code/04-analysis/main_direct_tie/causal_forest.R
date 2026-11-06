# Where does a tie to the designee pay most? A causal forest over every predetermined characteristic (6 November 2026,
# the user's request after the tie splits all came out alike). Same sample, outcome and treatment as the main design:
# the 1,120 followers, Y = mean rank in e+1..e+4 minus rank in e-2, W = tie to the designee (against a tie to a losing
# contender), succession weights omega_e / n_e (the main estimand's person weights spread over each succession's
# followers), clusters = contender camp. Athey and Wager's causal forest (grf), honest, tuned. Reports
#   1. the forest's ATT against the main estimate,
#   2. the omnibus heterogeneity test (test_calibration: differential forest prediction),
#   3. variable importance,
#   4. the best linear projection of the CATE on the tie variables (Semenova-Chernozhukov),
#   5. RATE (AUTOC and Qini) with sample splitting by camp: can a forest-ranked targeting beat random?
#   6. doubly robust effects by quartile of the held-out CATE ranking,
#   7. partial dependence of the CATE on the tie variables.
# Descriptive: the forest's variance clusters by camp only (no Ferman-Pinto shocks for the nine designee camps).
# Writes causal_forest_*.csv, the figure causal_forest.{pdf,png} and tables/causal_forest_macros.tex.
# Run inside the staging environment: Rscript code/04-analysis/main_direct_tie/causal_forest.R
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
invisible(capture.output(source(file.path(script_dir, "estimate_main.R"))))
source(file.path(script_dir, "design_tools.R")); suppressPackageStartupMessages({library(grf); library(ggplot2)})
invisible(capture.output(source(file.path(script_dir, "rp_setup.R"))))   # A: prior_status, fed_exec for the followers
tab_dir <- file.path(out_dir, "tables"); dir.create(tab_dir, showWarnings = FALSE)
seed_cf <- 6112026L; set.seed(seed_cf)

# ------------------------------------------------------------------ 1. features, all predetermined by e-2
S <- copy(sample)
# the ties to the contender (heterogeneity.R (e)): every dated edge formed by e-2
tp <- rbindlist(list(dated[, .(pid = person_a, candidate = person_b, edge_type, focus_size, year_start)],
                     dated[, .(pid = person_b, candidate = person_a, edge_type, focus_size, year_start)]))[edge_type %in% tie_types]
st <- merge(S[, .(pid, election, patron)], tp, by.x = c("pid", "patron"), by.y = c("pid", "candidate"), allow.cartesian = TRUE)
st <- st[year_start <= election - tie_lag]
tf <- st[, .(any_work = any(edge_type == "co_work"), any_school = any(edge_type == "co_education"),
             any_military = any(edge_type %in% c("co_military", "co_revolution")), n_foci = .N,
             min_focus = min(focus_size), tie_year = min(year_start),
             first_work_year = as.numeric(if (any(edge_type == "co_work")) min(year_start[edge_type == "co_work"]) else NA_real_)), by = .(pid, election)]
m <- match(paste(S$pid, S$election), paste(tf$pid, tf$election)); stopifnot(!anyNA(m))
S[, names(tf)[-(1:2)] := tf[m, -(1:2)]]
S[, birth_year := as.numeric(birth[as.character(pid)])]
S[, age_at_tie := tie_year - birth_year]                          # the follower's age when the earliest tie formed
S[, years_since_tie := election - 2L - tie_year]                  # how old the tie is at the dedazo
cs <- annual[rank >= 1L, .(career_start = min(year)), by = pid]
S[, career_start := cs$career_start[match(pid, cs$pid)]]
S[, years_in_career_at_work_tie := first_work_year - career_start]   # NA without a co-work tie
# education (heterogeneity.R (d))
ed <- fread(file.path(data_dir, "clean_positions", "education.csv"), na.strings = c("", "NA")); deg <- ed[!is.na(degree_level)]
by_e2 <- function(ids, e, dt) { b <- birth[as.character(dt$person_id)]; ids %in% dt[(year_end <= e - 2) | (is.na(year_end) & (e - 2 - b) >= 35), person_id] }
S[, `:=`(econ = by_e2(pid, election[1], deg[degree_field == "economics"]), law = by_e2(pid, election[1], deg[degree_field == "law"]),
         unam = by_e2(pid, election[1], deg[organization == "UNAM"]), any_degree = by_e2(pid, election[1], deg[degree_level %in% c("undergraduate", "masters", "phd")]),
         graduate = by_e2(pid, election[1], deg[degree_level %in% c("masters", "phd")])), by = election]
# prior status and the federal-executive flag (rp_setup.R)
ma <- match(paste(S$pid, S$election), paste(A$pid, A$election)); stopifnot(!anyNA(ma))
S[, `:=`(fed_exec = A$fed_exec[ma], prior_status = as.character(A$prior_status[ma]))]
S[, `:=`(prev_winner = as.integer(prior_status == "prev_winner"), prev_loser = as.integer(prior_status == "prev_loser"), prev_absent = as.integer(prior_status == "absent"))]
# outcome and treatment of the main design
Yfull <- sapply(1:4, function(k) year_value(annual, k)); y14 <- rowMeans(Yfull) - year_value(annual, ref)
S[, Y := y14]; S[, W := treated]
# succession weights: the main estimand gives succession e the share omega_e of the designee's followers; spread over its followers
nT <- S[, .(n_D = sum(W), n = .N), by = election]; nT[, omega := n_D / sum(n_D)]
S[, w := nT$omega[match(election, nT$election)] / nT$n[match(election, nT$election)]]
S[, camp := paste(election, patron)]
feat <- c("any_work", "any_school", "any_military", "n_foci", "min_focus", "age_at_tie", "years_since_tie", "years_in_career_at_work_tie",
          "pre", "earlier", "age", "ldeg", "lrec", "econ", "law", "unam", "any_degree", "graduate", "fed_exec", "prev_winner", "prev_loser", "prev_absent", "election")
labels <- c(any_work = "Any co-work tie", any_school = "Any school tie", any_military = "Military or revolution tie", n_foci = "Number of shared foci",
            min_focus = "Size of the smallest focus", age_at_tie = "Age when the tie formed", years_since_tie = "Years since the tie formed",
            years_in_career_at_work_tie = "Career years before the first co-work tie", pre = "Baseline rank", earlier = "Earlier rank",
            age = "Age at the election", ldeg = "Degrees", lrec = "Records", econ = "Economics degree", law = "Law degree", unam = "UNAM degree",
            any_degree = "Any degree", graduate = "Graduate degree", fed_exec = "Federal executive post", prev_winner = "Previous winner tie",
            prev_loser = "Previous loser tie", prev_absent = "Absent at the previous succession", election = "Succession")
X <- as.matrix(S[, lapply(.SD, as.numeric), .SDcols = feat])   # grf handles NA (years_in_career_at_work_tie without a work tie)
Y <- S$Y; W <- S$W; w <- S$w; cl <- as.integer(factor(S$camp))
cat(sprintf("followers %d, designee's %d, camps %d, features %d\n", nrow(X), sum(W), uniqueN(cl), ncol(X)))

# ------------------------------------------------------------------ 2. the forest
cf <- causal_forest(X, Y, W, sample.weights = w, clusters = cl, num.trees = 4000, seed = seed_cf, honesty = TRUE, tune.parameters = "all")
att <- average_treatment_effect(cf, target.sample = "treated")
ate <- average_treatment_effect(cf, target.sample = "all")
cal <- test_calibration(cf)
vi <- variable_importance(cf)
imp <- data.table(feature = feat, label = labels[feat], importance = as.numeric(vi))[order(-importance)]
tau <- predict(cf, estimate.variance = TRUE)
S[, `:=`(cate = tau$predictions, cate_se = sqrt(tau$variance.estimates))]
main_est <- fread(file.path(out_dir, "event_study_summary.csv"))[outcome == "rank" & contrast == "main_window_average", estimate]
cat(sprintf("forest ATT %.3f (se %.3f), ATE %.3f (se %.3f); main design %.3f\n", att[1], att[2], ate[1], ate[2], main_est))
print(cal)

# ------------------------------------------------------------------ 3. best linear projection on the tie variables
# any_work is the complement of any_school up to 18 followers with both and a handful with military ties only, so one
# tie-type indicator enters (school), with the continuous tie variables, the baseline rank and age
tie_vars <- c("any_school", "n_foci", "min_focus", "age_at_tie", "years_since_tie", "pre", "age")
blp <- best_linear_projection(cf, X[, tie_vars], target.sample = "all")
lab_lookup <- c("(Intercept)" = "Intercept", labels)
blp_tab <- data.table(term = rownames(blp), estimate = as.numeric(blp[, 1]), se = as.numeric(blp[, 2]), t = as.numeric(blp[, 3]), p = as.numeric(blp[, 4]))
blp_tab[, label := unname(lab_lookup[term])]
print(blp_tab[, .(label, estimate = round(estimate, 3), se = round(se, 3), p = round(p, 3))])

# ------------------------------------------------------------------ 4. RATE and quartiles with sample splitting by camp
camps <- unique(cl); half <- sample(camps, length(camps) %/% 2)
iA <- cl %in% half; iB <- !iA
cfA <- causal_forest(X[iA, ], Y[iA], W[iA], sample.weights = w[iA], clusters = cl[iA], num.trees = 2000, seed = seed_cf, honesty = TRUE)
cfB <- causal_forest(X[iB, ], Y[iB], W[iB], sample.weights = w[iB], clusters = cl[iB], num.trees = 2000, seed = seed_cf + 1L, honesty = TRUE)
prB <- predict(cfA, X[iB, ])$predictions; prA <- predict(cfB, X[iA, ])$predictions   # held-out priorities
rateB <- rank_average_treatment_effect(cfB, prB, target = "AUTOC"); qiniB <- rank_average_treatment_effect(cfB, prB, target = "QINI")
rateA <- rank_average_treatment_effect(cfA, prA, target = "AUTOC"); qiniA <- rank_average_treatment_effect(cfA, prA, target = "QINI")
rate <- data.table(half = c("B", "B", "A", "A"), target = c("AUTOC", "QINI", "AUTOC", "QINI"),
                   estimate = c(rateB$estimate, qiniB$estimate, rateA$estimate, qiniA$estimate), se = c(rateB$std.err, qiniB$std.err, rateA$std.err, qiniA$std.err))
rate[, `:=`(t = estimate / se, p = 2 * pnorm(-abs(estimate / se)))]
print(rate)
# doubly robust scores by quartile of the held-out priority
scores <- numeric(nrow(X)); scores[iB] <- get_scores(cfB); scores[iA] <- get_scores(cfA)
prio <- numeric(nrow(X)); prio[iB] <- prB; prio[iA] <- prA
S[, `:=`(score = scores, priority = prio)]
S[, quartile := cut(priority, quantile(priority, 0:4 / 4), include.lowest = TRUE, labels = c("Q1 lowest", "Q2", "Q3", "Q4 highest"))]
quart <- S[, .(effect = weighted.mean(score, w), se = sqrt(sum((w / sum(w))^2 * (score - weighted.mean(score, w))^2)), n = .N,
               any_work = mean(any_work), any_school = mean(any_school), min_focus = median(min_focus), age_at_tie = median(age_at_tie, na.rm = TRUE),
               years_since_tie = median(years_since_tie, na.rm = TRUE), pre = median(pre), age = median(age)), by = quartile][order(quartile)]
print(quart[, lapply(.SD, function(x) if (is.numeric(x)) round(x, 2) else x)])

# ------------------------------------------------------------------ 5. partial dependence of the CATE
pd_vars <- c("age_at_tie", "years_since_tie", "min_focus", "pre", "age")
pdp <- rbindlist(lapply(pd_vars, function(v) {
  grid <- quantile(X[, v], seq(0.05, 0.95, by = 0.1), na.rm = TRUE)
  rbindlist(lapply(grid, function(g) { Xg <- X; Xg[, v] <- g; p <- predict(cf, Xg, estimate.variance = FALSE)$predictions
    data.table(variable = v, label = labels[[v]], value = g, cate = weighted.mean(p, w)) }))
}))

# ------------------------------------------------------------------ 6. outputs
fwrite(data.table(quantity = c("forest_att", "forest_ate", "main_design", "calibration_mean", "calibration_differential"),
                  estimate = c(att[1], ate[1], main_est, cal[1, 1], cal[2, 1]), se = c(att[2], ate[2], NA, cal[1, 2], cal[2, 2]),
                  t = c(NA, NA, NA, cal[1, 3], cal[2, 3]), p = c(NA, NA, NA, cal[1, 4], cal[2, 4])), file.path(out_dir, "causal_forest_results.csv"))
fwrite(imp, file.path(out_dir, "causal_forest_importance.csv")); fwrite(blp_tab, file.path(out_dir, "causal_forest_blp.csv"))
fwrite(rate, file.path(out_dir, "causal_forest_rate.csv")); fwrite(quart, file.path(out_dir, "causal_forest_quartiles.csv"))
fwrite(pdp, file.path(out_dir, "causal_forest_pdp.csv")); fwrite(S[, .(pid, election, patron, treated, cate, cate_se, priority, quartile)], file.path(out_dir, "causal_forest_cate.csv"))
f2 <- function(x) { v <- round(x, 2); s <- formatC(abs(v), format = "f", digits = 2); ifelse(v < 0, paste0("$-$", s), s) }
mac <- function(n, v) sprintf("\\newcommand{\\%s}{%s}", n, v)
top <- imp[1:5]
writeLines(c("% causal_forest_macros.tex (causal_forest.R). Do not edit by hand.",
  mac("CFatt", f2(att[1])), mac("CFattSE", f2(att[2])), mac("CFn", nrow(X)), mac("CFfeatures", ncol(X)), mac("CFcamps", uniqueN(cl)),
  mac("CFcalMean", f2(cal[1, 1])), mac("CFcalMeanP", formatC(cal[1, 4], format = "f", digits = 2)),
  mac("CFcalDiff", f2(cal[2, 1])), mac("CFcalDiffP", formatC(cal[2, 4], format = "f", digits = 2)),
  mac("CFautoc", f2(rate[half == "B" & target == "AUTOC", estimate])), mac("CFautocSE", f2(rate[half == "B" & target == "AUTOC", se])), mac("CFautocP", formatC(rate[half == "B" & target == "AUTOC", p], format = "f", digits = 2)),
  mac("CFautocA", f2(rate[half == "A" & target == "AUTOC", estimate])), mac("CFautocAP", formatC(rate[half == "A" & target == "AUTOC", p], format = "f", digits = 2)),
  mac("CFqOne", f2(quart[1, effect])), mac("CFqOneSE", f2(quart[1, se])), mac("CFqFour", f2(quart[4, effect])), mac("CFqFourSE", f2(quart[4, se])),
  mac("CFtopOne", top$label[1]), mac("CFtopTwo", top$label[2]), mac("CFtopThree", top$label[3]),
  mac("CFtopOneShare", formatC(100 * top$importance[1], format = "f", digits = 0)), mac("CFtopTwoShare", formatC(100 * top$importance[2], format = "f", digits = 0)),
  mac("CFcateSD", f2(sd(S$cate))), mac("CFcateMin", f2(min(S$cate))), mac("CFcateMax", f2(max(S$cate)))),
  file.path(tab_dir, "causal_forest_macros.tex"))

# ------------------------------------------------------------------ 7. figure: importance and partial dependence
imp[, label := factor(label, levels = rev(label))]
g1 <- ggplot(imp[1:12], aes(x = importance, y = label)) + geom_col(fill = "#18181b", width = 0.6) +
  labs(x = "Variable importance in the causal forest", y = NULL) + theme_classic(base_size = 12) +
  theme(axis.line = element_line(colour = "#a1a1aa", linewidth = 0.35), plot.background = element_rect(fill = "white", colour = NA))
ggsave(file.path(out_dir, "causal_forest_importance.pdf"), g1, width = 6, height = 4); ggsave(file.path(out_dir, "causal_forest_importance.png"), g1, width = 6, height = 4, dpi = 200)
g2 <- ggplot(pdp, aes(x = value, y = cate)) + geom_hline(yintercept = main_est, colour = "#a1a1aa", linetype = "dashed") +
  geom_line(colour = "#18181b") + geom_point(colour = "#18181b", size = 1.4) + facet_wrap(~ label, scales = "free_x", nrow = 1) +
  labs(x = NULL, y = "Predicted premium, rank positions") + theme_classic(base_size = 11) +
  theme(strip.background = element_blank(), axis.line = element_line(colour = "#a1a1aa", linewidth = 0.35), plot.background = element_rect(fill = "white", colour = NA))
ggsave(file.path(out_dir, "causal_forest_pdp.pdf"), g2, width = 11, height = 2.8); ggsave(file.path(out_dir, "causal_forest_pdp.png"), g2, width = 11, height = 2.8, dpi = 200)
g3 <- ggplot(quart, aes(x = quartile, y = effect)) + geom_hline(yintercept = 0, colour = "#a1a1aa") +
  geom_pointrange(aes(ymin = effect - 1.96 * se, ymax = effect + 1.96 * se), colour = "#18181b") +
  labs(x = "Quartile of the held-out forest ranking", y = "Premium, rank positions (doubly robust)") + theme_classic(base_size = 12) +
  theme(axis.line = element_line(colour = "#a1a1aa", linewidth = 0.35), plot.background = element_rect(fill = "white", colour = NA))
ggsave(file.path(out_dir, "causal_forest_quartiles.pdf"), g3, width = 6, height = 4); ggsave(file.path(out_dir, "causal_forest_quartiles.png"), g3, width = 6, height = 4, dpi = 200)
cat("causal_forest done\n")
