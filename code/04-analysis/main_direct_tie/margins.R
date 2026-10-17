# Margins of the rank premium (MAIN_SPEC section 8, 17 October 2026): extensive (holds a ranked post) and
# intensive (rank among politicians in office before and after), window contrasts with Lee (2009) bounds and
# event studies. Run from the repo root: Rscript code/04-analysis/main_direct_tie/margins.R
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
invisible(capture.output(source(file.path(script_dir, "estimate_main.R"))))
source(file.path(script_dir, "design_tools.R"))

ks <- -7:8; ref <- -2L
Y <- sapply(ks, function(k) year_value(annual, k)); colnames(Y) <- ks
E_ <- (Y > 0) * 1

# ------------------------------------------------------------------ window contrasts (section-4 covariates)
d_all <- build_design()
ext_window <- as.numeric(sample$post > 0) - as.numeric(sample$pre > 0)
w_all <- estimate_columns(d_all, cbind(rank = sample$delta, extensive = ext_window))$table
stay <- sample$post > 0
d_stay <- build_design(keep = stay)
w_int <- estimate_columns(d_stay, cbind(intensive = sample$delta[d_stay$rows]))$table

# Lee bounds: trim the group with the higher post-window office rate by its excess share.
res_stay <- residuals_d(d_stay, sample$delta[d_stay$rows])
rate <- sample[, .(rate = mean(post > 0)), by = .(election, treated)]
lee <- rbindlist(lapply(d_stay$elections, function(e) {
  p1 <- rate[election == e & treated == 1L, rate]; p0 <- rate[election == e & treated == 0L, rate]
  rt <- sort(res_stay[d_stay$S$election == e & d_stay$S$treated == 1L])
  rc <- sort(res_stay[d_stay$S$election == e & d_stay$S$treated == 0L])
  trim <- function(x, q, from) { m <- floor(q * length(x) + 1e-9); if (m == 0) return(x)
    if (from == "top") head(x, length(x) - m) else tail(x, length(x) - m) }
  if (p1 >= p0) {
    q <- (p1 - p0) / p1
    lo <- mean(trim(rt, q, "top")) - mean(rc); hi <- mean(trim(rt, q, "bottom")) - mean(rc)
  } else {
    q <- (p0 - p1) / p0
    lo <- mean(rt) - mean(trim(rc, q, "bottom")); hi <- mean(rt) - mean(trim(rc, q, "top"))
  }
  data.table(election = e, office_rate_designee = p1, office_rate_losers = p0, trimmed_share = q,
             trimmed_group = fifelse(p1 >= p0, "designee", "losers"), lower = lo, upper = hi)
}))
lee_bounds <- c(lower = mean(lee$lower), upper = mean(lee$upper))

windows <- rbind(w_all, w_int)
windows[, label := c("Rank (0 if no recorded post)", "Holds a ranked post", "Rank among those in office before and after")]
windows[, `:=`(lee_lower = c(NA, NA, lee_bounds[["lower"]]), lee_upper = c(NA, NA, lee_bounds[["upper"]]))]
fwrite(windows, file.path(out_dir, "margins_windows.csv"))
fwrite(lee, file.path(out_dir, "margins_lee_by_succession.csv"))

# ------------------------------------------------------------------ event studies (section-7 covariates)
d_es <- build_design(formula = formula_es)
ext_cols <- E_[, colnames(E_) != as.character(ref)] - E_[, as.character(ref)]
ext_es <- estimate_columns(d_es, ext_cols)$table
ext_es <- rbind(ext_es[, .(k = as.integer(column), estimate, ci_lower, ci_upper, p_bootstrap, n)],
                data.table(k = ref, estimate = 0, ci_lower = 0, ci_upper = 0, p_bootstrap = NA, n = nrow(sample)))
int_es <- rbindlist(lapply(setdiff(ks, ref), function(k) {
  keep <- Y[, as.character(ref)] > 0 & Y[, as.character(k)] > 0
  d <- build_design(keep = keep, formula = formula_es)
  y <- (Y[, as.character(k)] - Y[, as.character(ref)])[d$rows]
  t <- estimate_columns(d, cbind(y), B = 20000L, seed = 17102026L + k)$table
  data.table(k = k, estimate = t$estimate, ci_lower = t$ci_lower, ci_upper = t$ci_upper,
             p_bootstrap = t$p_bootstrap, n = t$n, n_designee = t$n_designee)
}))
int_es <- rbind(int_es, data.table(k = ref, estimate = 0, ci_lower = 0, ci_upper = 0, p_bootstrap = NA,
                                   n = sum(Y[, as.character(ref)] > 0), n_designee = NA), fill = TRUE)
setorder(ext_es, k); setorder(int_es, k)
fwrite(rbind(ext_es[, margin := "extensive"], int_es[, margin := "intensive"], fill = TRUE),
       file.path(out_dir, "margins_event_study.csv"))

es_figure(ext_es, "Difference in holding a ranked post\nsince e-2 (percentage points)", "es_extensive", scale = 100)
es_figure(int_es, "Difference in rank since e-2,\nthose in office both years (rungs)", "es_intensive")

print(windows[, .(label, estimate = round(estimate, 3), ci_lower = round(ci_lower, 3), ci_upper = round(ci_upper, 3),
                  p_bootstrap, n, lee_lower = round(lee_lower, 3), lee_upper = round(lee_upper, 3))])
print(lee)
print(ext_es[, .(k, estimate = round(estimate, 3), ci_lower = round(ci_lower, 3), ci_upper = round(ci_upper, 3))])
print(int_es[, .(k, estimate = round(estimate, 3), ci_lower = round(ci_lower, 3), ci_upper = round(ci_upper, 3), n)])
