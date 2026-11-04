# Did the agencies handed to the designee's followers get more money? (4 November 2026, coauthor's request.) Agency-level
# complement of budget_outcome.R (person-level investment commanded). Unit: agency x succession. For each succession e
# and each agency with investment data in both windows, the change in its share of federal public investment from
# e-5..e-2 to e+1..e+4 (percentage points of the year's total, window means), against who headed it in e+1..e+4:
# the group at e of the person with most head-years in the window (D designee's follower, P losing contender's
# follower, C a contender of the slate, N unaligned eligible, other = anyone else or no identified head).
# Regression of the change on D and P indicators, the pre-window share and succession indicators (base: all other heads);
# log version on agencies with positive shares in both windows. Inference: (i) agency-clustered robust s.e.; (ii) a
# permutation test that reassigns the head groups across the agencies of the same succession (5,000 draws), which is
# the question's natural null: the president chooses which agencies his followers get, the budget is what it is.
# Placebo: the same contrast for the heads of e-5..e-2 (future followers). Writes agency_budget.csv (agency panel),
# agency_budget_estimates.csv and tables/agency_budget_macros.tex. Run after estimate_main.R:
#   Rscript code/04-analysis/main_direct_tie/agency_budget.R
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
invisible(capture.output(source(file.path(script_dir, "estimate_main.R"))))
source(file.path(script_dir, "design_tools.R"))
invisible(capture.output(source(file.path(script_dir, "rp_setup.R"))))   # A: eligible D, P, N at each succession
source(file.path(script_dir, "budget_crosswalk.R"))
suppressPackageStartupMessages(library(sandwich))
set.seed(4112026L)
tab_dir <- file.path(out_dir, "tables"); dir.create(tab_dir, showWarnings = FALSE)
panel <- fread(file.path(data_dir, "investment", "agency_investment_panel.csv"))
series <- build_agency_series(panel)
pos <- fread(file.path(data_dir, "rank", "position_tiers.csv"), na.strings = c("", "NA"))
heads <- resolve_heads(head_records(pos), series)[!is.na(key)]
py <- person_year_shares(heads, series)            # pid, year, agency_key, share

group_at <- function(ids, e) {
  g <- A[election == e, .(pid, group)]; sl <- slates[[as.character(e)]]
  out <- g$group[match(ids, g$pid)]
  out[ids %in% sl$candidates] <- "C"
  out[is.na(out)] <- "other"; out
}
agency_window <- function(e, from, to, label) {
  yrs <- (e + from):(e + to)
  s <- series[year %in% yrs, .(share = mean(share), years = .N), by = agency_key]
  h <- py[year %in% yrs, .(head_years = .N), by = .(agency_key, pid)]
  if (nrow(h)) { h[, group := group_at(pid, e)]
    hg <- h[, .(head_years = sum(head_years)), by = .(agency_key, group)][order(agency_key, -head_years)]
    top <- hg[, .(group = group[1], head_years = head_years[1], total_head_years = sum(head_years)), by = agency_key]
  } else top <- data.table(agency_key = character(), group = character(), head_years = integer(), total_head_years = integer())
  s <- merge(s, top, by = "agency_key", all.x = TRUE)
  s[is.na(group), group := "other"]
  setnames(s, c("share", "years", "group", "head_years", "total_head_years"), paste0(c("share", "years", "group", "head_years", "total_head_years"), "_", label))
  s
}
AP <- rbindlist(lapply(elections, function(e) {
  pre <- agency_window(e, -5L, -2L, "pre"); post <- agency_window(e, 1L, 4L, "post")
  m <- merge(pre, post, by = "agency_key"); m[, election := e]; m
}))
AP[, `:=`(d_share = share_post - share_pre, d_log = fifelse(share_pre > 0 & share_post > 0, log(share_post) - log(share_pre), NA_real_),
          D_post = as.integer(group_post == "D"), P_post = as.integer(group_post == "P"),
          D_pre = as.integer(group_pre == "D"), P_pre = as.integer(group_pre == "P"), election_factor = factor(election))]
fwrite(AP, file.path(out_dir, "agency_budget.csv"))
cat("agency x succession rows:", nrow(AP), " heads after the succession:"); print(table(AP$group_post))

fit <- function(dat, y, dvar, pvar, perms = 5000L) {
  f <- as.formula(sprintf("%s ~ %s + %s + share_pre + election_factor", y, dvar, pvar))
  dd <- dat[!is.na(get(y))]
  m <- lm(f, data = dd); V <- vcovCL(m, cluster = dd$agency_key)
  b <- coef(m); se <- sqrt(diag(V))
  diff <- unname(b[dvar] - b[pvar]); se_diff <- sqrt(V[dvar, dvar] + V[pvar, pvar] - 2 * V[dvar, pvar])
  # permutation: shuffle the head-group labels across the agencies of each succession
  stat <- function(d2) { m2 <- lm(f, data = d2); cf <- coef(m2); c(cf[dvar], cf[pvar], cf[dvar] - cf[pvar]) }
  obs <- stat(dd); null <- replicate(perms, { d2 <- copy(dd); d2[, c(dvar, pvar) := { i <- sample(.N); .(get(dvar)[i], get(pvar)[i]) }, by = election]; stat(d2) })
  pv <- rowMeans(abs(null) >= abs(obs) - 1e-12)
  data.table(outcome = y, term = c("D vs other heads", "P vs other heads", "D vs P"), estimate = obs, se_cluster = c(se[dvar], se[pvar], se_diff),
             perm_p = pv, perm_q025 = apply(null, 1, quantile, .025), perm_q975 = apply(null, 1, quantile, .975), n = nrow(dd),
             n_D = sum(dd[[dvar]]), n_P = sum(dd[[pvar]]))
}
res <- rbind(fit(AP, "d_share", "D_post", "P_post")[, spec := "heads after the succession"],
             fit(AP, "d_log", "D_post", "P_post")[, spec := "heads after the succession, log share"],
             fit(AP, "d_share", "D_pre", "P_pre")[, spec := "placebo: heads before the succession"])
fwrite(res, file.path(out_dir, "agency_budget_estimates.csv"))
print(res[, .(spec, outcome, term, estimate = round(estimate, 3), se_cluster = round(se_cluster, 3), perm_p = round(perm_p, 3), n, n_D, n_P)])
# descriptive means
desc <- AP[, .(agencies = .N, share_pre = mean(share_pre), share_post = mean(share_post), d_share = mean(d_share)), by = group_post][order(-agencies)]
print(desc[, lapply(.SD, function(x) if (is.numeric(x)) round(x, 2) else x)])
# macros
f2 <- function(x) sub("^-", "$-$", formatC(x, format = "f", digits = 2)); f1 <- function(x) sub("^-", "$-$", formatC(x, format = "f", digits = 1))
r1 <- res[spec == "heads after the succession"]; r3 <- res[spec == "placebo: heads before the succession"]; r2 <- res[spec == "heads after the succession, log share"]
mac <- function(n, v) sprintf("\\newcommand{\\%s}{%s}", n, v)
writeLines(c("% agency_budget_macros.tex (agency_budget.R). Change in an agency's share of federal investment (pp), e-5..e-2 to e+1..e+4. Do not edit by hand.",
  mac("ABn", nrow(AP)), mac("ABnD", r1[term == "D vs P", n_D]), mac("ABnP", r1[term == "D vs P", n_P]), mac("ABagencies", uniqueN(AP$agency_key)),
  mac("ABdiff", f2(r1[term == "D vs P", estimate])), mac("ABdiffSE", f2(r1[term == "D vs P", se_cluster])), mac("ABdiffP", formatC(r1[term == "D vs P", perm_p], format = "f", digits = 2)),
  mac("ABdiffLo", f2(r1[term == "D vs P", estimate] - qnorm(.975) * r1[term == "D vs P", se_cluster])), mac("ABdiffHi", f2(r1[term == "D vs P", estimate] + qnorm(.975) * r1[term == "D vs P", se_cluster])),
  mac("ABd", f2(r1[term == "D vs other heads", estimate])), mac("ABdP", formatC(r1[term == "D vs other heads", perm_p], format = "f", digits = 2)),
  mac("ABp", f2(r1[term == "P vs other heads", estimate])), mac("ABpP", formatC(r1[term == "P vs other heads", perm_p], format = "f", digits = 2)),
  mac("ABlogDiff", f2(r2[term == "D vs P", estimate])), mac("ABlogDiffP", formatC(r2[term == "D vs P", perm_p], format = "f", digits = 2)),
  mac("ABplaceboDiff", f2(r3[term == "D vs P", estimate])), mac("ABplaceboP", formatC(r3[term == "D vs P", perm_p], format = "f", digits = 2)),
  mac("ABmeanShareD", f1(desc[group_post == "D", share_post])), mac("ABmeanShareP", f1(desc[group_post == "P", share_post]))),
  file.path(tab_dir, "agency_budget_macros.tex"))

# person-level numbers of budget_outcome.R for the same slide (heads an investment agency; investment commanded)
bw <- fread(file.path(out_dir, "budget_windows.csv"))
hb <- bw[column == "heads_agency"]; cb <- bw[column == "budget_share"]
cat(c(mac("ABheadsEst", f1(100 * hb$estimate)), mac("ABheadsLo", f1(100 * hb$ci_lower)), mac("ABheadsHi", f1(100 * hb$ci_upper)),
      mac("ABcommandEst", f2(cb$estimate)), mac("ABcommandLo", f2(cb$ci_lower)), mac("ABcommandHi", f2(cb$ci_upper))),
    file = file.path(tab_dir, "agency_budget_macros.tex"), sep = "\n", append = TRUE)
cat("agency_budget done\n")
