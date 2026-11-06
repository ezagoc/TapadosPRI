# MAIN_SPEC section 16: whom the succession promotes. Test 1 (premium by credentials) and Test 2 (credentials of top-post
# holders). Run after estimate_main.R: Rscript code/04-analysis/main_direct_tie/credentials.R
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
invisible(capture.output(source(file.path(script_dir, "estimate_main.R"))))
source(file.path(script_dir, "design_tools.R"))
ed <- fread(file.path(data_dir, "clean_positions", "education.csv"), na.strings = c("", "NA"))
by_e2 <- function(ids, e, dt) {
  b <- birth[as.character(dt$person_id)]
  ids %in% dt[(year_end <= e - 2) | (is.na(year_end) & (e - 2 - b) >= 35), person_id]
}
gtab <- ed[degree_level %in% c("masters", "phd")]
ftab <- gtab[foreign_degree %in% TRUE]
ttab <- ed[degree_field %in% c("economics", "business", "engineering", "science")]
sample[, `:=`(graduate = by_e2(pid, election[1], gtab), foreign_graduate = by_e2(pid, election[1], ftab),
              technical = by_e2(pid, election[1], ttab)), by = election]
f_sub <- ~ factor(election) + pre_band + earlier_band + age + ldeg + lrec + prior_status

est_sub <- function(keep, label) {
  d <- tryCatch(build_design(keep = keep, formula = f_sub), error = function(e) NULL)
  if (is.null(d)) return(list(row = data.table(group = label, estimate = NA_real_), err = NULL))
  ec <- estimate_columns(d, cbind(rank = sample$delta[d$rows]), B = 20000L)
  list(row = ec$table[, .(group = label, estimate, ci_lower, ci_upper, successions = length(d$elections),
                          designee = sum(d$S$treated), losers = sum(d$S$treated == 0L))], err = ec$err[1, ])
}
test1 <- rbindlist(lapply(c("graduate", "foreign_graduate", "technical"), function(m) {
  w <- est_sub(sample[[m]], paste(m, "= yes")); wo <- est_sub(!sample[[m]], paste(m, "= no"))
  contrast <- wo$row$estimate - w$row$estimate
  ce <- if (!is.null(w$err) && !is.null(wo$err)) quantile(sample(wo$err, 20000, TRUE) - sample(w$err, 20000, TRUE), c(.025, .975), names = FALSE) else c(NA, NA)
  rbind(w$row, wo$row, data.table(group = paste(m, ": without - with"), estimate = contrast,
                                  ci_lower = contrast - ce[2], ci_upper = contrast - ce[1]), fill = TRUE)[, measure := m]
}))
# Test 2: credentials of top-post holders, designee's exclusive followers vs every other holder
top_holders <- function(e, from, to) unique(annual[year >= from & year <= to & rank >= 8L, pid])
test2 <- rbindlist(lapply(elections, function(e) {
  el <- eligible[[as.character(e)]]; w <- slates[[as.character(e)]]$winner
  D <- el[n_direct == 1L & patron == w, pid]
  post <- top_holders(e, e + 1L, e + 4L); pre <- top_holders(e, e - 5L, e - 2L)
  g <- function(ids) mean(by_e2(ids, e, gtab))
  data.table(election = e, post_designee_followers = g(intersect(post, D)), n_post_D = length(intersect(post, D)),
             post_other_holders = g(setdiff(post, D)), n_post_other = length(setdiff(post, D)), pre_all_holders = g(pre), n_pre = length(pre))
}))
fwrite(test1, file.path(out_dir, "credentials_test1.csv")); fwrite(test2, file.path(out_dir, "credentials_test2.csv"))
r3 <- function(d) d[, lapply(.SD, function(x) if (is.numeric(x)) round(x, 3) else x)]
cat("Test 1: rank premium (main design) by credential\n"); print(r3(test1[, .(measure, group, estimate, ci_lower, ci_upper, successions, designee, losers)]))
cat("\nTest 2: share with a graduate degree among top-post holders\n"); print(r3(test2))
print(r3(test2[, .(post_designee_followers = mean(post_designee_followers, na.rm = TRUE), post_other_holders = mean(post_other_holders), pre_all_holders = mean(pre_all_holders))]))
