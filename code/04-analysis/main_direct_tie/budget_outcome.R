# Federal investment commanded (MAIN_SPEC section 9, 17 October 2026): percent of the year's federal public
# investment realized by the agency a politician heads (0 if none); window contrast and event study with the
# main design. The crosswalk from posts to agencies is the 13 October one (archived budget_outcome.py), ported to
# R and extended on 20 October 2026 (budget_crosswalk.R). Run from the repo root:
# Rscript code/04-analysis/main_direct_tie/budget_outcome.R
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
invisible(capture.output(source(file.path(script_dir, "estimate_main.R"))))
source(file.path(script_dir, "design_tools.R"))
inv_dir <- file.path(data_dir, "investment")

# ------------------------------------------------------------------ 1. agency series (share of the year's total)
# The series builder and the head -> agency crosswalk live in budget_crosswalk.R (shared with investment_heads.R).
source(file.path(script_dir, "budget_crosswalk.R"))
panel <- fread(file.path(inv_dir, "agency_investment_panel.csv"))
series <- build_agency_series(panel)
fwrite(series[order(agency_key, year)], file.path(out_dir, "budget_agency_series.csv"))

# ------------------------------------------------------------------ 2. who heads what
pos <- fread(file.path(data_dir, "rank", "position_tiers.csv"), na.strings = c("", "NA"))
heads <- resolve_heads(head_records(pos), series)
fwrite(heads[, .(record_id, person_id, person_name, rule, role_text, y0, y1, key = fifelse(is.na(key), "UNMATCHED", key))][
  rule %in% c("cabinet_secretary", "df_regent", "big_parastatal_head", "parastatal_head") | key != "UNMATCHED"][order(key, y0)],
  file.path(out_dir, "budget_crosswalk_audit.csv"))
hy <- heads[!is.na(key)]
person_years <- person_year_shares(hy, series)
budget_py <- person_years[, .(share = max(share), heads = 1L), by = .(pid, year)]

# ------------------------------------------------------------------ 3. outcomes and estimates
ks <- -7:8; ref <- -2L
Bt <- sapply(ks, function(k) year_value(budget_py, k, "share")); colnames(Bt) <- ks
Ht <- sapply(ks, function(k) year_value(budget_py, k, "heads")); colnames(Ht) <- ks
wmax <- function(from, to) apply(sapply(from:to, function(k) year_value(budget_py, k, "share")), 1L, max)
whead <- function(from, to) apply(sapply(from:to, function(k) year_value(budget_py, k, "heads")), 1L, max)
b_pre <- wmax(-5, -2); b_post <- wmax(1, 4)
h_pre <- whead(-5, -2); h_post <- whead(1, 4)
# Robustness rows (20 October 2026): heads an agency with at least 1% of the year's investment (access, not the
# size of the budget), and the share with every agency capped at 5 points (one follower at National Railways in
# 1941-1942, 23% of federal investment, drives the uncapped share). Same estimator, same bootstrap draws.
wcap <- function(from, to) apply(sapply(from:to, function(k) pmin(year_value(budget_py, k, "share"), 5)), 1L, max)
waccess <- function(from, to) apply(sapply(from:to, function(k) as.numeric(year_value(budget_py, k, "share") >= 1)), 1L, max)
c_pre <- wcap(-5, -2); c_post <- wcap(1, 4)
a_pre <- waccess(-5, -2); a_post <- waccess(1, 4)
d_all <- build_design()
windows <- estimate_columns(d_all, cbind(budget_share = b_post - b_pre, heads_agency = h_post - h_pre,
                                         access_1pct = a_post - a_pre, budget_share_cap5 = c_post - c_pre))$table
windows[, label := c("Federal investment commanded (percentage points)", "Heads an investment agency",
                     "Heads an agency with at least 1% of the year's investment",
                     "Federal investment commanded, agencies capped at 5 points (percentage points)")]
desc <- data.table(group = c("designee", "losers"),
                   heads_pre = c(mean(h_pre[sample$treated == 1]), mean(h_pre[sample$treated == 0])),
                   heads_post = c(mean(h_post[sample$treated == 1]), mean(h_post[sample$treated == 0])),
                   share_pre = c(mean(b_pre[sample$treated == 1]), mean(b_pre[sample$treated == 0])),
                   share_post = c(mean(b_post[sample$treated == 1]), mean(b_post[sample$treated == 0])),
                   n_heads_post = c(sum(h_post[sample$treated == 1]), sum(h_post[sample$treated == 0])))
fwrite(windows, file.path(out_dir, "budget_windows.csv"))
fwrite(desc, file.path(out_dir, "budget_descriptives.csv"))
d_es <- build_design(formula = formula_es)
es <- estimate_columns(d_es, Bt[, colnames(Bt) != as.character(ref)] - Bt[, as.character(ref)])$table
es <- rbind(es[, .(k = as.integer(column), estimate, ci_lower, ci_upper, ci90_lower, ci90_upper, p_bootstrap)],
            data.table(k = ref, estimate = 0, ci_lower = 0, ci_upper = 0, ci90_lower = 0, ci90_upper = 0, p_bootstrap = NA))
setorder(es, k)
es_h <- estimate_columns(d_es, Ht[, colnames(Ht) != as.character(ref)] - Ht[, as.character(ref)])$table
es_h <- rbind(es_h[, .(k = as.integer(column), estimate, ci_lower, ci_upper, ci90_lower, ci90_upper, p_bootstrap)],
              data.table(k = ref, estimate = 0, ci_lower = 0, ci_upper = 0, ci90_lower = 0, ci90_upper = 0, p_bootstrap = NA))
setorder(es_h, k)
fwrite(rbind(es[, outcome := "investment_commanded_pp"], es_h[, outcome := "heads_investment_agency"]),
       file.path(out_dir, "budget_event_study.csv"))
es <- es[, outcome := NULL]

cat("agency series:", uniqueN(series$agency_key), "agencies,", min(series$year), "-", max(series$year), "\n")
cat("head records resolved:", sum(!is.na(heads$key)), "of", nrow(heads), "\n")
print(windows[, .(label, estimate = round(estimate, 3), ci_lower = round(ci_lower, 3), ci_upper = round(ci_upper, 3), p_bootstrap)])
print(desc)
print(es[, .(k, estimate = round(estimate, 3), ci_lower = round(ci_lower, 3), ci_upper = round(ci_upper, 3))])
print(es_h[, .(k, heads_pp = round(100 * estimate, 1), lo = round(100 * ci_lower, 1), hi = round(100 * ci_upper, 1))])
