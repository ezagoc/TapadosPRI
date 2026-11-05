# Heterogeneity of the main window contrast (MAIN_SPEC section 4 design, section 5 inference) by predetermined subgroups,
# in the style of the credentials test (section 16, credentials.R): the design is estimated separately on each subgroup
# (succession as a factor of the successions present; equal weights over the successions in which both the designee's and
# the losers' followers exist), and the between-subgroup contrast takes its interval from independent bootstrap draws,
# which is conservative because the subgroups share the losing groups' shocks. Nothing here is pre-specified: it is an
# exploration of which heterogeneities are robust and powered. Every split is defined from information available by e-2.
# Dimensions: (a) period and a linear trend of the by-succession estimates; (b) the follower's baseline rung; (c) age;
# (d) education (field, UNAM; the graduate-degree split is in credentials.R and is not repeated); (e) the tie to the
# contender (type, age, strength); (f) career type (federal executive post); (g) the designee's post at e-2 and the
# contender's camp size; (h) prior-succession status; (i) the follower's dated ties and ranked posts.
# Robustness to refitting the control model inside small subgroups: every split is also estimated with the full-sample
# loser model held fixed (section 4b; joint draws, so those contrast intervals are not conservative). Splits are ranked by
# |contrast|/se (refit), by the sign consistency of the contrast across successions and by |contrast|/se (fixed model);
# the table, figure and macros show the period split and the six best-ranked person-level splits.
# Run after estimate_main.R: Rscript code/04-analysis/main_direct_tie/heterogeneity.R
# Draws: TAPADOS_HET_B (default 20000; 10000 was used for exploration).
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
invisible(capture.output(source(file.path(script_dir, "estimate_main.R"))))
source(file.path(script_dir, "design_tools.R"))
B_het <- as.integer(Sys.getenv("TAPADOS_HET_B", "20000"))
tab_dir <- file.path(out_dir, "tables"); dir.create(tab_dir, showWarnings = FALSE)
seed_het <- 20102026L

# ------------------------------------------------------------------ 1. subgroup variables, all dated by e-2
# (a) period
sample[, period := fifelse(election <= 1958L, "1940-1958", fifelse(election <= 1976L, "1964-1976", "1982-1988"))]
# (b) baseline rung (the highest rung in e-5..e-2; 9 = cabinet secretary, 6 = director general, 4 = area director)
sample[, rung_group := fifelse(pre <= 4L, "Rung 4 or below", fifelse(pre <= 7L, "Rungs 5-7", "Rungs 8-9"))]
# (c) age in the election year
sample[, age_group := fifelse(age < 45, "Under 45", fifelse(age <= 55, "45-55", "Over 55"))]
# (d) education by e-2. Degree dated by its year; when the year is missing, counted if the politician was 35 or older at
# e-2 (the rule of credentials.R). A politician with both an economics and a law degree counts as economics.
ed <- fread(file.path(data_dir, "clean_positions", "education.csv"), na.strings = c("", "NA"))
deg <- ed[!is.na(degree_level)]
by_e2 <- function(ids, e, dt) {
  b <- birth[as.character(dt$person_id)]
  ids %in% dt[(year_end <= e - 2) | (is.na(year_end) & (e - 2 - b) >= 35), person_id]
}
sample[, `:=`(econ = by_e2(pid, election[1], deg[degree_field == "economics"]),
              law = by_e2(pid, election[1], deg[degree_field == "law"]),
              unam = by_e2(pid, election[1], deg[organization == "UNAM"]),
              any_degree = by_e2(pid, election[1], deg[degree_level %in% c("undergraduate", "masters", "phd")]),
              graduate = by_e2(pid, election[1], deg[degree_level %in% c("masters", "phd")])), by = election]
sample[, field_group := fifelse(econ, "Economics degree", fifelse(law, "Law degree", "Engineering, other field or none"))]
sample[, unam_group := fifelse(unam, "UNAM degree", fifelse(any_degree, "Degree elsewhere", "No recorded degree"))]
# (e) the tie to the contender: every dated co-work/co-education/co-military/co-revolution edge between the follower and
# his contender formed by e-2; the earliest one gives the type and the age of the tie (same year: revolution, military,
# education, work), and the smallest focus among them the strength.
tp <- rbindlist(list(dated[, .(pid = person_a, candidate = person_b, edge_type, focus_size, year_start)],
                     dated[, .(pid = person_b, candidate = person_a, edge_type, focus_size, year_start)]))[edge_type %in% tie_types]
st <- merge(sample[, .(pid, election, patron)], tp, by.x = c("pid", "patron"), by.y = c("pid", "candidate"), allow.cartesian = TRUE)
st <- st[year_start <= election - tie_lag]
st[, type_order := match(edge_type, c("co_revolution", "co_military", "co_education", "co_work"))]
setorder(st, pid, election, year_start, type_order)
tf <- st[, .(tie_type = edge_type[1], tie_year = year_start[1], min_focus = min(focus_size), n_ties_patron = .N,
             any_cowork = any(edge_type == "co_work")), by = .(pid, election)]
m <- match(paste(sample$pid, sample$election), paste(tf$pid, tf$election)); stopifnot(!anyNA(m))
sample[, `:=`(tie_type = tf$tie_type[m], tie_year = tf$tie_year[m], min_focus = tf$min_focus[m], any_cowork = tf$any_cowork[m])]
sample[, tie_type_group := fifelse(tie_type == "co_work", "Co-work", fifelse(tie_type == "co_education", "Co-education", "Co-military or revolution"))]
sample[, tie_age_group := fifelse(tie_year >= election - 2L - 8L, "Formed within 8 years of e-2", "Formed earlier")]
# School ties are old by construction, so type and age overlap: two splits separate them (any co-work tie vs school or
# military ties only; recency among followers whose earliest tie is co-work).
sample[, tie_work_group := fifelse(any_cowork, "Any co-work tie", fifelse(tie_type == "co_education", "School ties only", NA_character_))]
sample[, tie_age_cowork_group := fifelse(tie_type != "co_work", NA_character_,
                                 fifelse(tie_year >= election - 2L - 8L, "Co-work tie within 8 years of e-2", "Co-work tie formed earlier"))]
sample[, tie_strength_group := fifelse(min_focus <= 10L, "A tie in a focus of 10 or fewer", "Only larger foci")]
# (f) career type: a post in the federal executive branch active in e-5..e-2 (the fed_exec flag of rp_setup.R)
pt_all <- fread(file.path(data_dir, "rank", "position_tiers.csv"), na.strings = c("", "NA"))
fedx <- pt_all[dataset == "govt_positions" & !grepl("^state_|^governor|^mayor|city_council|^local", rule) & !is.na(year_start)]
fedx[, `:=`(y0 = as.integer(year_start), y1 = as.integer(pmax(fifelse(is.na(year_end), year_start, year_end), year_start)))]
fedx <- fedx[y1 - y0 <= 12L]
sample[, fed_exec := pid %in% fedx[y0 <= election[1] - 2L & y1 >= election[1] - 5L, person_id], by = election]
sample[, career_group := fifelse(fed_exec, "Federal executive post", "Elected, party, state or military only")]
# (g) the designee's post at e-2 and the contender's camp (exclusive followers in the sample, median over all 54 camps)
wpos <- contenders[in_main_slate == 1L & role == "winner" & election_year %in% elections, .(election = election_year, position_at_time)]
wpos[, designee_post := fifelse(grepl("Gobernaci", position_at_time), "Gobernacion",
                        fifelse(grepl("Hacienda|Programaci", position_at_time), "Hacienda or SPP", "Other (War 1940, Labor 1958)"))]
sample[, designee_post := wpos$designee_post[match(election, wpos$election)]]
camps <- network_info[, .(network, camp = n)]
sample[, camp := camps$camp[match(network, camps$network)]]
camp_median <- median(camps$camp)
sample[, camp_group := fifelse(camp > camp_median, "Contender's camp above the median", "Camp at or below the median")]
# (h) prior-succession status (prior_status of estimate_main.R)
sample[, prev_designee_group := fifelse(prior_status == "prev_winner", "Tied to the previous designee", "Not tied to him")]
sample[, prev_pool_group := fifelse(prior_status == "absent", "New to the pool", "In the previous pool")]
# (i) dated ties and ranked posts by e-2, above or below the succession's median (the network grows over time)
sample[, `:=`(ties_group = fifelse(ldeg > median(ldeg), "Ties above the median", "Ties at or below"),
              posts_group = fifelse(lrec > median(lrec), "Ranked posts above the median", "Ranked posts at or below")), by = election]

# ------------------------------------------------------------------ 2. the design on a subgroup, with the control model that is full rank
# Every factor is re-levelled within the subgroup (as credentials.R does with factor(election)): with the fixed levels of
# the full sample, a subgroup that lacks the reference level has dummies collinear with the intercept. A factor constant
# on the subgroup is dropped and the row says so; if the model is still rank-deficient, the event-study covariates
# (formula_es, no rank bands) are used, then succession indicators only. Groups with fewer than `min_side` followers on
# either side are not estimated.
x_factors <- c("pre_band", "earlier_band", "prior_status")
x_terms <- c("factor(election)", "factor(pre_band)", "factor(earlier_band)", "age", "ldeg", "lrec", "factor(prior_status)")
es_terms <- c("factor(election)", "age", "ldeg", "lrec", "factor(prior_status)")
min_side <- 10L
fit_group <- function(keep, seed) {
  keep <- keep & !is.na(keep)
  if (sum(keep & sample$treated == 1L) < min_side || sum(keep & sample$treated == 0L) < min_side) return(NULL)
  constant <- x_factors[sapply(x_factors, function(v) uniqueN(sample[keep][[v]]) <= 1L)]
  drop_constant <- function(terms) terms[!sapply(terms, function(t) any(sapply(constant, function(v) grepl(v, t, fixed = TRUE))))]
  tries <- list(list(f = reformulate(drop_constant(x_terms)),
                     label = if (length(constant)) paste("formula_x without", paste(constant, collapse = ", ")) else "formula_x"),
                list(f = reformulate(drop_constant(es_terms)), label = "formula_es"),
                list(f = ~ factor(election), label = "election indicators only"))
  for (t in tries) {
    d <- tryCatch(build_design(keep = keep, formula = t$f), error = function(e) NULL)
    if (is.null(d) || length(d$elections) < 2L) next
    y <- sample$delta[d$rows]
    ec <- estimate_columns(d, cbind(rank = y), B = B_het, seed = seed)
    return(list(table = ec$table, err = ec$err[1, ], by_e = by_succession_d(d, y), model = t$label,
                elections = d$elections, n_losers = sum(d$S$treated == 0L), designs = d))
  }
  NULL
}
contrast_rows <- function(fa, fb, label) {
  if (is.null(fa) || is.null(fb)) return(data.table(group = label, row_type = "contrast"))
  est <- fa$table$estimate - fb$table$estimate
  err <- fa$err - fb$err                   # independent draws (different seeds): conservative for a shared shock
  ci <- ci_from(est, err, .95); ci90 <- ci_from(est, err, .90)
  both <- merge(fa$by_e, fb$by_e, by = "election", suffixes = c("_a", "_b"))
  same <- sum(sign(both$estimate_a - both$estimate_b) == sign(est))
  data.table(group = label, row_type = "contrast", estimate = est, ci_lower = ci[[1]], ci_upper = ci[[2]],
             ci90_lower = ci90[[1]], ci90_upper = ci90[[2]], se = sd(err), p_bootstrap = mean(abs(err) >= abs(est)),
             successions_both = nrow(both), successions_same_sign = same,
             successions_list = paste(both$election, collapse = " "))
}
group_row <- function(f, label, keep) {
  keep <- keep & !is.na(keep)
  if (is.null(f)) return(data.table(group = label, row_type = "subgroup", n = sum(keep), n_designee = sum(keep & sample$treated == 1L),
                                    n_losers = sum(keep & sample$treated == 0L), control_model = "not estimated (too few)"))
  f$table[, .(group = label, row_type = "subgroup", estimate, ci_lower, ci_upper, ci90_lower, ci90_upper, se = sd(f$err), p_bootstrap,
              n, n_designee, n_losers = f$n_losers, successions = length(f$elections),
              successions_list = paste(f$elections, collapse = " "), control_model = f$model)]
}
# One split: ordered groups (first = reference), headline contrast = est[contrast[1]] - est[contrast[2]].
splits <- list(
  list(id = "period", short = "late minus early", dimension = "Period", var = "period", levels = c("1940-1958", "1964-1976", "1982-1988"),
       contrast = c("1982-1988", "1940-1958"), unit = "succession"),
  list(id = "rung", short = "8--9 minus 4 or below", dimension = "Baseline rung", var = "rung_group", levels = c("Rung 4 or below", "Rungs 5-7", "Rungs 8-9"),
       contrast = c("Rungs 8-9", "Rung 4 or below")),
  list(id = "age", short = "over 55 minus under 45", dimension = "Age at the election", var = "age_group", levels = c("Under 45", "45-55", "Over 55"),
       contrast = c("Over 55", "Under 45")),
  list(id = "field", short = "economics minus law", dimension = "Field of degree", var = "field_group",
       levels = c("Law degree", "Economics degree", "Engineering, other field or none"), contrast = c("Economics degree", "Law degree")),
  list(id = "unam", short = "UNAM minus elsewhere", dimension = "University", var = "unam_group", levels = c("UNAM degree", "Degree elsewhere", "No recorded degree"),
       contrast = c("UNAM degree", "Degree elsewhere")),
  list(id = "tie_type", short = "co-education minus co-work", dimension = "Type of the earliest tie", var = "tie_type_group",
       levels = c("Co-work", "Co-education", "Co-military or revolution"), contrast = c("Co-education", "Co-work")),
  list(id = "tie_age", short = "within 8 years minus earlier", dimension = "Age of the tie", var = "tie_age_group", levels = c("Formed earlier", "Formed within 8 years of e-2"),
       contrast = c("Formed within 8 years of e-2", "Formed earlier")),
  list(id = "tie_work_any", short = "co-work minus school only", dimension = "Any co-work tie", var = "tie_work_group", levels = c("School ties only", "Any co-work tie"),
       contrast = c("Any co-work tie", "School ties only")),
  list(id = "tie_age_cowork", short = "within 8 years minus earlier", dimension = "Age of the tie, co-work ties", var = "tie_age_cowork_group",
       levels = c("Co-work tie formed earlier", "Co-work tie within 8 years of e-2"),
       contrast = c("Co-work tie within 8 years of e-2", "Co-work tie formed earlier")),
  list(id = "tie_strength", short = "small focus minus larger only", dimension = "Strength of the tie", var = "tie_strength_group",
       levels = c("Only larger foci", "A tie in a focus of 10 or fewer"), contrast = c("A tie in a focus of 10 or fewer", "Only larger foci")),
  list(id = "career", short = "federal executive minus other", dimension = "Career by e-2", var = "career_group",
       levels = c("Elected, party, state or military only", "Federal executive post"),
       contrast = c("Federal executive post", "Elected, party, state or military only")),
  list(id = "designee_post", short = "Hacienda/SPP minus Gobernacion", dimension = "Designee's post at e-2", var = "designee_post",
       levels = c("Gobernacion", "Hacienda or SPP", "Other (War 1940, Labor 1958)"), contrast = c("Hacienda or SPP", "Gobernacion"),
       unit = "succession"),
  list(id = "camp", short = "above minus below the median", dimension = "Contender's camp", var = "camp_group",
       levels = c("Camp at or below the median", "Contender's camp above the median"),
       contrast = c("Contender's camp above the median", "Camp at or below the median"), unit = "succession"),   # one designee camp per succession
  list(id = "prev_designee", short = "tied minus not tied", dimension = "Previous designee", var = "prev_designee_group",
       levels = c("Not tied to him", "Tied to the previous designee"), contrast = c("Tied to the previous designee", "Not tied to him")),
  list(id = "prev_pool", short = "in the previous pool minus new", dimension = "Previous pool", var = "prev_pool_group", levels = c("New to the pool", "In the previous pool"),
       contrast = c("In the previous pool", "New to the pool")),
  list(id = "ties", short = "above minus below the median", dimension = "Ties by e-2", var = "ties_group", levels = c("Ties at or below", "Ties above the median"),
       contrast = c("Ties above the median", "Ties at or below")),
  list(id = "posts", short = "above minus below the median", dimension = "Ranked posts by e-2", var = "posts_group",
       levels = c("Ranked posts at or below", "Ranked posts above the median"), contrast = c("Ranked posts above the median", "Ranked posts at or below")))

fits <- list(); rows <- list(); k <- 0L
for (s in splits) {
  fs <- list()
  for (g in s$levels) { k <- k + 1L; fs[[g]] <- fit_group(sample[[s$var]] == g, seed = seed_het + k) }
  fits[[s$id]] <- fs
  sub <- rbindlist(lapply(s$levels, function(g) group_row(fs[[g]], g, sample[[s$var]] == g)), fill = TRUE)
  sub[, level := seq_len(.N)]
  head_c <- contrast_rows(fs[[s$contrast[1]]], fs[[s$contrast[2]]], paste(s$contrast[1], "minus", s$contrast[2]))[, headline := TRUE]
  other <- if (length(s$levels) == 3L) {
    pairs <- list(c(s$levels[2], s$levels[1]), c(s$levels[3], s$levels[2]), c(s$levels[3], s$levels[1]))
    pairs <- Filter(function(p) !identical(p, s$contrast), pairs)
    rbindlist(lapply(pairs, function(p) contrast_rows(fs[[p[1]]], fs[[p[2]]], paste(p[1], "minus", p[2]))), fill = TRUE)[, headline := FALSE]
  } else NULL
  r <- rbind(sub, head_c, other, fill = TRUE)
  r[is.na(level), level := 99L]
  r[, `:=`(split = s$id, dimension = s$dimension, split_unit = if (is.null(s$unit)) "person" else s$unit,
           split_order = length(rows) + 1L)]
  rows[[s$id]] <- r
}
het <- rbindlist(rows, fill = TRUE)
het[row_type == "contrast", z := abs(estimate) / se]
setcolorder(het, c("split", "split_order", "dimension", "split_unit", "row_type", "group", "level", "headline", "estimate", "ci_lower", "ci_upper",
                   "ci90_lower", "ci90_upper", "se", "z", "p_bootstrap", "n", "n_designee", "n_losers", "successions",
                   "successions_list", "control_model", "successions_both", "successions_same_sign"))
het[, bootstrap_draws := B_het]
fwrite(het, file.path(out_dir, "heterogeneity.csv"))

# ------------------------------------------------------------------ 3. ranking of the headline contrasts
ranked <- het[row_type == "contrast" & headline == TRUE & !is.na(estimate),
              .(split, dimension, split_unit, contrast = group, estimate, ci_lower, ci_upper, se, z, p_bootstrap,
                successions_both, successions_same_sign)]
ranked[, consistency := fifelse(successions_both > 0L, successions_same_sign / successions_both, NA_real_)]
n_min <- het[row_type == "subgroup" & !is.na(estimate), .(groups_estimated = .N, n_min_group = min(n), n_designee_min = min(n_designee)), by = split]
ranked <- merge(ranked, n_min, by = "split", sort = FALSE)
ranked[, rank_z := frank(-z, ties.method = "min")]
ranked[, rank_consistency := frank(-consistency, ties.method = "min", na.last = "keep")]
# The combined rank (filled in after the fixed-control-model estimates of 4b): mean of the ranks by |contrast|/se with
# the control model refit in the subgroup, by sign consistency across successions (succession-level splits have none)
# and by |contrast|/se with the control model held fixed.

# ------------------------------------------------------------------ 4. by-succession estimates and their linear trend, joint draws
# The by-succession contrast theta_e is linear in the outcomes on the full design (the control model is shared), so the OLS
# slope of the nine theta_e on the election year (per decade) is too; its draws come from the same donor draws as the
# nine estimates (one donor group per network slot and draw, as in design_tools.R).
d_full <- build_design()
y_full <- sample$delta[d_full$rows]
tr <- d_full$S$treated == 1L; el <- d_full$S$election
A_e <- sapply(d_full$elections, function(e) {
  a <- numeric(nrow(d_full$S)); ix <- which(tr & el == e); a[ix] <- 1 / length(ix)
  a[d_full$ctrl] <- -d_full$w0 * as.vector(d_full$X0 %*% (d_full$M %*% colMeans(d_full$X[ix, , drop = FALSE])))
  a
})
colnames(A_e) <- d_full$elections
# the pooled weights combine the by-succession contrasts with the design's succession weights (person weights since
# 3 November 2026; equal weights would make this the row mean)
w_e <- sapply(d_full$elections, function(e) omega[[as.character(e)]])
stopifnot(abs(sum(w_e) - 1) < 1e-8, max(abs(as.vector(A_e %*% w_e) - d_full$a)) < 1e-10)
x_dec <- (d_full$elections - mean(d_full$elections)) / 10
A_lin <- cbind(A_e, slope_per_decade = as.vector(A_e %*% (x_dec / sum(x_dec^2))))
boot_linear <- function(d, A, y, B, seed) {
  r_y <- as.vector(d$Q %*% y[d$ctrl]); ab <- fit_variance_components(r_y, d$moments)
  z <- r_y / sqrt(pmax(as.vector(d$moments %*% ab), .Machine$double.eps)); z <- (z - mean(z)) / sd(z)
  set.seed(seed); idx <- matrix(base::sample.int(d$K, length(d$g) * B, replace = TRUE), nrow = length(d$g))
  zz <- matrix(z[idx], nrow = nrow(idx))
  err <- t(apply(A, 2, function(a) {
    net <- data.table(network = d$S$network, a = a)[, .(g = sum(a), wsq = sum(a^2)), by = network]
    n_eff <- fifelse(net$wsq > 0, net$g^2 / net$wsq, 1)
    colSums(net$g * sqrt(ab[1] + ab[2] / n_eff) * zz)
  }))
  list(est = as.vector(crossprod(A, y)), err = err, components = ab)
}
bl <- boot_linear(d_full, A_lin, y_full, B_het, seed_het)
trend <- rbindlist(lapply(seq_len(ncol(A_lin)), function(j) {
  ci <- ci_from(bl$est[j], bl$err[j, ], .95); ci90 <- ci_from(bl$est[j], bl$err[j, ], .90)
  data.table(term = colnames(A_lin)[j], estimate = bl$est[j], ci_lower = ci[[1]], ci_upper = ci[[2]], ci90_lower = ci90[[1]],
             ci90_upper = ci90[[2]], se = sd(bl$err[j, ]), p_bootstrap = mean(abs(bl$err[j, ]) >= abs(bl$est[j])))
}))
stopifnot(max(abs(trend$estimate[1:9] - components$relative_premium)) < 1e-8)
trend[, bootstrap_draws := B_het]
fwrite(trend, file.path(out_dir, "heterogeneity_trend.csv"))
slope <- trend[term == "slope_per_decade"]

# ------------------------------------------------------------------ 4b. the same splits with the control model held fixed
# Robustness to refitting the loser model inside small subgroups: the full-sample model of section 4, and in each
# succession the subgroup's designee followers' mean residual minus its losers' followers' mean residual (equal weights
# over the successions with both). Linear in the outcomes, so the subgroup estimates and their contrasts share one set
# of joint draws (the contrast interval is then not conservative).
stopifnot(identical(d_full$rows, seq_len(nrow(sample))))
fixed_weights <- function(keep) {
  keep <- keep & !is.na(keep); tr <- sample$treated == 1L; el <- sample$election
  es <- elections[sapply(elections, function(e) any(keep & tr & el == e) && any(keep & !tr & el == e))]
  if (length(es) < 2L) return(NULL)
  a <- numeric(nrow(sample)); b <- 0
  for (e in es) {
    iT <- which(keep & tr & el == e); iC <- which(keep & !tr & el == e)
    a[iT] <- 1 / (length(es) * length(iT)); a[iC] <- -1 / (length(es) * length(iC))
    b <- b + (colMeans(d_full$X[iT, , drop = FALSE]) - colMeans(d_full$X[iC, , drop = FALSE])) / length(es)
  }
  a[d_full$ctrl] <- a[d_full$ctrl] - d_full$w0 * as.vector(d_full$X0 %*% (d_full$M %*% b))
  attr(a, "successions") <- es
  a
}
fw <- list(); fw_es <- list()
for (s in splits) for (g in s$levels) {
  a <- fixed_weights(sample[[s$var]] == g)
  if (!is.null(a)) { fw[[paste(s$id, g, sep = "|")]] <- a; fw_es[[paste(s$id, g, sep = "|")]] <- attr(a, "successions") }
}
A_fixed <- do.call(cbind, fw); colnames(A_fixed) <- names(fw)
bf <- boot_linear(d_full, A_fixed, y_full, B_het, seed_het + 1000L)
fixed_row <- function(est, err, es = NA) {
  ci <- ci_from(est, err, .95)
  data.table(estimate_fixed = est, ci_fixed_lower = ci[[1]], ci_fixed_upper = ci[[2]], se_fixed = sd(err),
             successions_fixed = if (length(es) == 1L && is.na(es)) NA_integer_ else length(es))
}
fixed <- rbindlist(lapply(seq_along(fw), function(j) cbind(data.table(grp_key = names(fw)[j]), fixed_row(bf$est[j], bf$err[j, ], fw_es[[j]]))))
het[row_type == "subgroup", grp_key := paste(split, group, sep = "|")]
het[row_type == "contrast", `:=`(grp_key_a = paste(split, sub(" minus .*$", "", group), sep = "|"),
                                 grp_key_b = paste(split, sub("^.* minus ", "", group), sep = "|"))]
het <- merge(het, fixed, by = "grp_key", all.x = TRUE, sort = FALSE)
for (i in which(het$row_type == "contrast")) {
  ja <- match(het$grp_key_a[i], names(fw)); jb <- match(het$grp_key_b[i], names(fw))
  if (is.na(ja) || is.na(jb)) next
  fr <- fixed_row(bf$est[ja] - bf$est[jb], bf$err[ja, ] - bf$err[jb, ],
                  intersect(fw_es[[ja]], fw_es[[jb]]))
  set(het, i, names(fr), fr)
}
het[row_type == "contrast", z_fixed := abs(estimate_fixed) / se_fixed]
het[, c("grp_key", "grp_key_a", "grp_key_b") := NULL]
setorder(het, split_order, level, -headline, na.last = TRUE)
fwrite(het, file.path(out_dir, "heterogeneity.csv"))
ranked <- merge(ranked, het[row_type == "contrast" & headline == TRUE, .(split, estimate_fixed, ci_fixed_lower, ci_fixed_upper, z_fixed)],
                by = "split", sort = FALSE)
ranked[, rank_z_fixed := frank(-z_fixed, ties.method = "min", na.last = "keep")]
ranked[, rank_combined := rowMeans(cbind(rank_z, rank_consistency, rank_z_fixed), na.rm = TRUE)]
setorder(ranked, rank_combined, rank_z)
fwrite(ranked, file.path(out_dir, "heterogeneity_ranked.csv"))

# ------------------------------------------------------------------ 5. composition of the designee's followers by succession
comp <- sample[, .(followers = .N, share_economics = mean(econ), share_law = mean(law), share_graduate = mean(graduate),
                   share_unam = mean(unam), share_federal_executive = mean(fed_exec), mean_baseline_rung = mean(pre),
                   mean_age = mean(age)), by = .(election, group = fifelse(treated == 1L, "designee", "losers"))]
setorder(comp, group, election)
fwrite(comp, file.path(out_dir, "heterogeneity_composition.csv"))

# ------------------------------------------------------------------ 6. table, figure and macros of the most informative splits
f2 <- function(x, d = 2) { r <- round(x, d); s <- formatC(r, format = "f", digits = d); s[r == 0] <- formatC(0, format = "f", digits = d); sub("^-", "$-$", s) }
ci_txt <- function(lo, hi, d = 2) paste0("[", f2(lo, d), ", ", f2(hi, d), "]")
neg <- function(x, d = 2) { if (length(x) == 0L || is.na(x)) return("--"); v <- round(x, d); s <- formatC(abs(v), format = "f", digits = d); if (v < 0) paste0("$-$", s) else s }
mac <- function(name, value) sprintf("\\newcommand{\\%s}{%s}", name, value)
tex <- function(x) { x <- gsub("e-2", "$e-2$", x, fixed = TRUE); x <- gsub("(\\d{4})-(\\d{4})", "\\1--\\2", x)
                     x <- gsub("(\\d)-(\\d)", "\\1--\\2", x); gsub("Gobernacion", "Gobernaci\\\\'on", x) }
# The period split first (the coauthor's question), then the best-ranked person-level splits with a full contrast.
person_level <- ranked[split_unit == "person" & !is.na(estimate), split]
chosen <- c("period", person_level[1:6])
tl <- c("% heterogeneity.tex -- the main contrast by subgroup (heterogeneity.R). Subgroup estimates: the section 4 design on",
        "% the subgroup; contrast: first minus second group, interval from independent contender-level bootstrap draws (conservative).",
        "\\begin{tabular}{lrrrr}", "\\toprule", " & Estimate & 95\\% interval & Politicians & Contrast \\\\", "\\midrule")
letters_up <- LETTERS
for (i in seq_along(chosen)) {
  s <- splits[[which(sapply(splits, `[[`, "id") == chosen[i])]]
  r <- het[split == s$id]
  hc <- r[row_type == "contrast" & headline == TRUE]
  if (i > 1) tl <- c(tl, "\\addlinespace")
  tl <- c(tl, sprintf("\\multicolumn{5}{l}{\\textit{%s. %s} (contrast: %s)} \\\\", letters_up[i], tex(s$dimension), tex(s$short)))
  sg <- r[row_type == "subgroup"]
  for (j in seq_len(nrow(sg))) {
    ctxt <- if (j == 1L && !is.na(hc$estimate)) sprintf("%s %s", f2(hc$estimate), ci_txt(hc$ci_lower, hc$ci_upper)) else ""
    if (is.na(sg$estimate[j])) tl <- c(tl, sprintf("%s & \\multicolumn{3}{l}{not estimated: %d politicians} & %s \\\\", tex(sg$group[j]), sg$n[j], ctxt))
    else tl <- c(tl, sprintf("%s & %s & %s & %s & %s \\\\", tex(sg$group[j]), f2(sg$estimate[j]), ci_txt(sg$ci_lower[j], sg$ci_upper[j]),
                             format(sg$n[j], big.mark = ","), ctxt))
  }
}
tl <- c(tl, "\\midrule", sprintf("Pooled (main estimate) & %s & %s & %s & \\\\", f2(theta), ci_txt(ci[1], ci[2]), format(nrow(sample), big.mark = ",")),
        "\\bottomrule", "\\end{tabular}")
writeLines(tl, file.path(tab_dir, "heterogeneity.tex"))

# Figure: horizontal coefficient plot of the same splits, grouped by dimension.
pd <- het[split %in% chosen & row_type == "subgroup" & !is.na(estimate)]
pd[, dimension := factor(dimension, levels = sapply(chosen, function(id) splits[[which(sapply(splits, `[[`, "id") == id)]]$dimension))]
pd[, label := gsub("Gobernacion", "Gobernaci\u00f3n", group, fixed = TRUE)]   # ASCII hyphens: the pdf device has no en dash
setorder(pd, dimension, -level)
pd[, label := factor(label, levels = unique(label))]
g <- ggplot(pd, aes(estimate, label)) +
  geom_vline(xintercept = 0, colour = RULE, linewidth = 0.35) +
  geom_vline(xintercept = theta, colour = MUTED, linewidth = 0.35, linetype = "dashed") +
  geom_linerange(aes(xmin = ci_lower, xmax = ci_upper), colour = INK, linewidth = 0.45) +
  geom_linerange(aes(xmin = ci90_lower, xmax = ci90_upper), colour = INK, linewidth = 1.5) +
  geom_point(colour = INK, size = 2.3) +
  facet_grid(dimension ~ ., scales = "free_y", space = "free_y", switch = "y") +
  labs(x = expression("Effect on rank, " * hat(theta) * " (rungs), by subgroup"), y = NULL) +
  theme_paper(14) +
  theme(strip.placement = "outside", strip.text.y.left = element_text(angle = 0, hjust = 1, vjust = 1, colour = MUTED, size = 11),
        panel.spacing.y = unit(4, "pt"), axis.line.y = element_blank(), axis.ticks.y = element_blank(),
        axis.text.y = element_text(size = 11))
ggsave(file.path(out_dir, "heterogeneity.pdf"), g, width = 10, height = 5.5, bg = "white", device = "pdf")
ggsave(file.path(out_dir, "heterogeneity.png"), g, width = 10, height = 5.5, dpi = 250, bg = "white")

# Macros: the period split, the trend, and the two best-ranked other splits.
per <- het[split == "period" & row_type == "subgroup"]; perc <- het[split == "period" & row_type == "contrast" & headline == TRUE]
mac_group <- function(prefix, row) c(mac(prefix, neg(row$estimate)), mac(paste0(prefix, "Lo"), neg(row$ci_lower)),
                                     mac(paste0(prefix, "Hi"), neg(row$ci_upper)), mac(paste0(prefix, "N"), format(row$n, big.mark = ",")))
mac_split <- function(prefix, id) {
  s <- splits[[which(sapply(splits, `[[`, "id") == id)]]; r <- het[split == id]
  hc <- r[row_type == "contrast" & headline == TRUE]
  ra <- r[row_type == "subgroup" & group == s$contrast[1]]; rb <- r[row_type == "subgroup" & group == s$contrast[2]]
  c(mac(paste0(prefix, "Name"), tex(s$dimension)), mac(paste0(prefix, "AName"), tex(s$contrast[1])), mac(paste0(prefix, "BName"), tex(s$contrast[2])),
    mac_group(paste0(prefix, "A"), ra), mac_group(paste0(prefix, "B"), rb),
    mac(paste0(prefix, "Contrast"), neg(hc$estimate)), mac(paste0(prefix, "ContrastLo"), neg(hc$ci_lower)), mac(paste0(prefix, "ContrastHi"), neg(hc$ci_upper)),
    mac(paste0(prefix, "ContrastP"), f2(hc$p_bootstrap, 2)),
    mac(paste0(prefix, "SameSign"), sprintf("%d of %d", hc$successions_same_sign, hc$successions_both)))
}
top_other <- person_level
lines_mac <- c("% het_macros.tex -- numbers of the heterogeneity slide (heterogeneity.R). Do not edit by hand.",
  mac_group("HETperiodEarly", per[group == "1940-1958"]), mac_group("HETperiodMid", per[group == "1964-1976"]),
  mac_group("HETperiodLate", per[group == "1982-1988"]),
  mac("HETperiodContrast", neg(perc$estimate)), mac("HETperiodContrastLo", neg(perc$ci_lower)), mac("HETperiodContrastHi", neg(perc$ci_upper)),
  mac("HETtrendSlope", neg(slope$estimate)), mac("HETtrendLo", neg(slope$ci_lower)), mac("HETtrendHi", neg(slope$ci_upper)),
  mac("HETtrendP", f2(slope$p_bootstrap, 2)),
  mac_split("HETtopTwo", top_other[1]), mac_split("HETtopThree", top_other[2]),
  mac("HETdraws", format(B_het, big.mark = ",")), mac("HETnSplits", nrow(ranked)))
writeLines(lines_mac, file.path(tab_dir, "het_macros.tex"))

# ------------------------------------------------------------------ 7. console
r3 <- function(d) d[, lapply(.SD, function(x) if (is.numeric(x)) round(x, 2) else x)]
cat("Main contrast:", round(theta, 3), " draws per estimate:", B_het, "\n\n")
print(r3(het[, .(split, group, row_type, estimate, ci_lower, ci_upper, n, n_designee, successions, control_model,
                 same = successions_same_sign, both = successions_both)]), nrows = 200)
cat("\nRanking of the headline contrasts\n")
print(r3(ranked[, .(split, contrast, estimate, ci_lower, ci_upper, z, consistency, n_min_group, estimate_fixed, ci_fixed_lower, ci_fixed_upper, z_fixed,
                    rank_z, rank_consistency, rank_z_fixed, rank_combined)]))
cat("\nBy succession and linear trend (per decade), joint draws\n"); print(r3(trend))
cat("\nComposition of the followers by succession\n"); print(r3(comp))
cat("\nWrote heterogeneity{,_ranked,_trend,_composition}.csv, heterogeneity.{pdf,png}, tables/heterogeneity.tex, tables/het_macros.tex to", out_dir, "\n")
