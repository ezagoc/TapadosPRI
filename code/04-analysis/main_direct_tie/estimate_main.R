# The one prespecified main contrast in MAIN_SPEC.md (16 October 2026).
# Run: Rscript code/04-analysis/main_direct_tie/estimate_main.R
# Reads and writes the shared TapadosPRI Dropbox tree by default.
suppressPackageStartupMessages(library(data.table))

args <- commandArgs(FALSE)
script_arg <- sub("^--file=", "", args[grepl("^--file=", args)][1])
here <- if (is.na(script_arg)) normalizePath("research/main") else dirname(normalizePath(script_arg))
db_root <- Sys.getenv("TAPADOSPRI_DB_ROOT", file.path(path.expand("~"), "Dropbox", "TapadosPRI"))
data_dir <- Sys.getenv("TAPADOSPRI_DATA_DIR", file.path(db_root, "data"))
out_dir <- Sys.getenv("TAPADOS_MAIN_OUTPUT_DIR", file.path(db_root, "output", "main_direct_tie"))
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
seed <- 16102026L
set.seed(seed)

elections <- seq(1940L, 1988L, by = 6L)
tie_types <- c("co_work", "co_education", "co_military", "co_revolution")
read_data <- function(...) fread(file.path(data_dir, ...), na.strings = c("", "NA"))

nodes <- read_data("networks", "network_nodes.csv")
edges <- read_data("networks", "network_edges.csv")
contenders <- read_data("candidates", "corcholatas_matched.csv")
positions <- read_data("rank", "position_tiers.csv")

stopifnot(!anyNA(contenders[in_main_slate == 1L, person_id]))
slates <- lapply(elections, function(e) {
  d <- contenders[election_year == e & in_main_slate == 1L]
  winners <- d[role == "winner", person_id]
  stopifnot(length(winners) == 1L, !anyDuplicated(d$person_id), nrow(d) >= 2L)
  list(candidates = d$person_id, winner = winners)
})
names(slates) <- as.character(elections)

# Annual highest whole rung of a dated ranked post. Long spells over 12 years
# are excluded to avoid carrying undated administrative records for decades.
positions <- positions[!is.na(hybrid_rank) & !is.na(year_start)]
positions[, `:=`(y0 = as.integer(year_start),
                y1 = as.integer(pmax(fifelse(is.na(year_end), year_start, year_end), year_start)),
                rung = as.integer(floor(hybrid_rank + 1e-9)))]
positions <- positions[y1 - y0 <= 12L & rung >= 1L & rung <= 11L]
stopifnot(nrow(positions) > 0L)
reps <- positions$y1 - positions$y0 + 1L
ii <- rep(seq_len(nrow(positions)), reps)
annual <- data.table(pid = positions$person_id[ii],
                     year = positions$y0[ii] + sequence(reps) - 1L,
                     rank = positions$rung[ii])[, .(rank = max(rank)), by = .(pid, year)]
setkey(annual, pid, year)

highest_rank <- function(ids, from, through) {
  tab <- annual[year >= from & year <= through, .(rank = max(rank)), by = pid]
  z <- tab$rank[match(ids, tab$pid)]
  z[is.na(z)] <- 0L
  as.integer(z)
}

birth <- setNames(nodes$birth_year, nodes$person_id)
dated <- edges[!is.na(year_start)]
long_ties <- rbindlist(list(
  dated[, .(pid = person_a, candidate = person_b, edge_type, year_start)],
  dated[, .(pid = person_b, candidate = person_a, edge_type, year_start)]
))
long_ties <- unique(long_ties[edge_type %in% tie_types, .(pid, candidate, year_start)])

eligible <- vector("list", length(elections))
names(eligible) <- as.character(elections)
for (e in elections) {
  t0 <- e - 2L
  ids <- unique(annual[year >= e - 5L & year <= t0, pid])
  ids <- setdiff(ids, unique(contenders[election_year <= e, person_id]))
  d <- data.table(pid = sort(ids), election = e)
  d[, age := e - as.numeric(birth[as.character(pid)])]
  d <- d[!is.na(age) & age >= 25 & age <= 75]
  d[, pre := highest_rank(pid, e - 5L, t0)]
  stopifnot(all(d$pre > 0L))
  d[, earlier := highest_rank(pid, e - 9L, e - 6L)]
  d[, post := highest_rank(pid, e + 1L, e + 4L)]
  d[, delta := post - pre]

  pre_edges <- dated[year_start <= t0]
  deg <- data.table(pid = c(pre_edges$person_a, pre_edges$person_b))[, .N, by = pid]
  v <- deg$N[match(d$pid, deg$pid)]; v[is.na(v)] <- 0L
  d[, ldeg := log1p(v)]
  nrec <- positions[y0 <= t0, .N, by = person_id]
  v <- nrec$N[match(d$pid, nrec$person_id)]; v[is.na(v)] <- 0L
  d[, lrec := log1p(v)]

  slate <- slates[[as.character(e)]]
  ct <- unique(long_ties[candidate %in% slate$candidates & year_start <= t0,
                         .(pid, candidate)])
  ct <- ct[pid %in% d$pid]
  ct[, direct_ties := .N, by = pid]
  counts <- unique(ct[, .(pid, direct_ties)])
  d[, n_direct := counts$direct_ties[match(pid, counts$pid)]]
  d[is.na(n_direct), n_direct := 0L]
  d[, prior_winner_tie := as.integer(pid %in% ct[candidate == slate$winner, pid])]
  singles <- ct[direct_ties == 1L, .(pid, patron = candidate)]
  d[, patron := singles$patron[match(pid, singles$pid)]]
  eligible[[as.character(e)]] <- d
}

sample <- rbindlist(lapply(elections, function(e) {
  d <- copy(eligible[[as.character(e)]][n_direct == 1L])
  prior <- eligible[[as.character(e - 6L)]]
  if (is.null(prior)) {
    d[, prior_status := "absent"]
  } else {
    p <- prior[match(d$pid, pid)]
    d[, prior_status := fifelse(is.na(p$pid), "absent",
                         fifelse(p$prior_winner_tie == 1L, "prev_winner",
                         fifelse(p$n_direct > 0L, "prev_loser", "no_direct")))]
    d[is.na(prior_status), prior_status := "no_direct"]
  }
  d[, treated := as.integer(patron == slates[[as.character(e)]]$winner)]
  d
}), use.names = TRUE, fill = TRUE)

sample[, pre_band := factor(fifelse(pre <= 4L, "low", fifelse(pre <= 7L, "middle", "high")),
                            levels = c("low", "middle", "high"))]
sample[, earlier_band := factor(fifelse(earlier == 0L, "none", fifelse(earlier <= 4L, "low",
                                fifelse(earlier <= 7L, "middle", "high"))),
                                levels = c("none", "low", "middle", "high"))]
sample[, prior_status := factor(prior_status,
                                levels = c("absent", "no_direct", "prev_loser", "prev_winner"))]
sample[, election_factor := factor(election, levels = elections)]
sample[, network := paste(election, patron, sep = "_")]
setorder(sample, election, patron, pid)
stopifnot(!anyDuplicated(sample[, .(election, pid)]),
          all(sample$pre > 0L), all(sample$patron %in% contenders$person_id),
          all(table(sample$election, sample$treated) > 0L))

# Fit the control trend with equal total weight per succession. The target
# remains an equal mean of the nine treated-network average residuals.
controls <- which(sample$treated == 0L)
treated <- which(sample$treated == 1L)
control_n <- table(sample$election[controls])
formula_x <- ~ election_factor + pre_band + earlier_band + age + ldeg + lrec + prior_status
X <- model.matrix(formula_x, data = sample)
X0 <- X[controls, , drop = FALSE]
w0 <- 1 / as.numeric(control_n[as.character(sample$election[controls])])
y <- sample$delta
fit <- lm.wfit(X0, y[controls], w = w0)
if (fit$rank != ncol(X0)) stop("Main control model is rank-deficient; check predetermined factor levels.")
beta <- fit$coefficients
pred <- as.vector(X %*% beta)
sample[, predicted_loser_change := pred]
sample[, residual_change := delta - pred]

E <- length(elections)
components <- rbindlist(lapply(elections, function(e) {
  d <- sample[election == e]
  tw <- d[treated == 1L]
  co <- d[treated == 0L]
  data.table(election = e, winner = slates[[as.character(e)]]$winner,
             n_winner = nrow(tw), n_loser = nrow(co),
             winner_mean_pre = mean(tw$pre), loser_mean_pre = mean(co$pre),
             winner_mean_change = mean(tw$delta), loser_mean_change = mean(co$delta),
             adjusted_loser_change = mean(tw$predicted_loser_change),
             relative_premium = mean(tw$residual_change))
}))
theta <- mean(components$relative_premium)

# Exact linear weights of the full estimator, including estimation of the
# control-only outcome model.  Their sum in every succession is zero.
M <- solve(crossprod(X0, X0 * w0))
b <- Reduce(`+`, lapply(elections, function(e) colMeans(X[sample$election == e & sample$treated == 1L, , drop = FALSE]))) / E
a <- numeric(nrow(sample))
a[controls] <- -w0 * as.vector(X0 %*% (M %*% b))
for (e in elections) {
  ix <- which(sample$election == e & sample$treated == 1L)
  a[ix] <- 1 / (E * length(ix))
}
stopifnot(abs(sum(a * y) - theta) < 1e-8)
weights_by_e <- sample[, .(weight_sum = sum(a)), by = election]
stopifnot(max(abs(weights_by_e$weight_sum)) < 1e-8)

# Candidate network layout. All inference uses the network as the shock unit.
sample[, estimator_weight := a]
network_info <- sample[, .(n = .N, treated = unique(treated),
                           contribution = sum(estimator_weight * delta),
                           g = sum(estimator_weight),
                           weight_squares = sum(estimator_weight^2)),
                       by = .(election, patron, network)]
setorder(network_info, election, -treated, -n)
network_info[, n_eff := g^2 / weight_squares]
stopifnot(all(is.finite(network_info$n_eff)), all(network_info$n_eff > 0))
network_info[, control_share := fifelse(treated == 0L,
                             n / sum(n[treated == 0L]), NA_real_), by = election]
effective_controls <- network_info[treated == 0L,
  .(effective_losing_networks = 1 / sum(control_share^2)), by = election]
components <- merge(components, effective_controls, by = "election", sort = FALSE)

# Estimate Var(network mean shock) = A + B/n. We correct the squared donor
# residual moments for the *full control-regression hat matrix*. In particular,
# a network in a slate with few controls is not treated as an independent raw
# residual from an accurately known slate mean.
control_groups <- unique(sample[controls, .(network, election, patron)])
setorder(control_groups, election, patron)
K <- nrow(control_groups)
Z <- matrix(0, nrow = length(controls), ncol = K)
for (j in seq_len(K)) Z[sample$network[controls] == control_groups$network[j], j] <- 1
ns <- colSums(Z)
Cmat <- t(sweep(Z, 2L, ns, "/"))
Q <- Cmat - sweep((Cmat %*% X0) %*% M %*% t(X0), 2L, w0, "*")
L <- Q %*% Z
r <- as.vector(Cmat %*% (y[controls] - as.vector(X0 %*% beta)))
vA <- rowSums(L^2)
vB <- rowSums(Q^2)
moment_x <- cbind(vA, vB)
fit_variance_components <- function(residual_means, moment_design = moment_x) {
  target <- residual_means^2
  vA <- moment_design[, 1]
  vB <- moment_design[, 2]
  candidates <- rbind(
    pmax(0, as.vector(qr.solve(moment_design, target))),
    c(sum(vA * target) / sum(vA^2), 0),
    c(0, sum(vB * target) / sum(vB^2)),
    c(0, 0)
  )
  loss <- apply(candidates, 1L, function(ab) sum((target - as.vector(moment_design %*% ab))^2))
  candidates[which.min(loss), ]
}
AB <- fit_variance_components(r)
names(AB) <- c("A_network", "B_person")
if (sum(AB) <= 0) stop("Network variance fit collapsed to zero.")
donor_sd <- sqrt(pmax(as.vector(moment_x %*% AB), .Machine$double.eps))
donor_z <- r / donor_sd
donor_z <- donor_z - mean(donor_z)
donor_z <- donor_z / sd(donor_z)
network_info[, shock_sd := sqrt(AB[1] + AB[2] / n_eff)]
donors <- cbind(control_groups, data.table(n = ns, residual = r, leverage_var_A = vA,
                                           leverage_var_B = vB, standardized_residual = donor_z))

bootstrap_error <- function(B = 50000L, z = donor_z, sd_by_network = network_info$shock_sd,
                            g = network_info$g) {
  coefs <- g * sd_by_network
  draws <- matrix(base::sample(z, length(coefs) * B, replace = TRUE), nrow = length(coefs))
  as.vector(crossprod(coefs, draws))
}
B <- 50000L
err <- bootstrap_error(B)
quant <- as.numeric(quantile(err, c(.025, .975), names = FALSE, type = 1))
calibration_factor <- 1.20
ci_raw <- c(theta - quant[2], theta - quant[1])
ci <- c(theta - calibration_factor * quant[2], theta - calibration_factor * quant[1])
p <- mean(abs(calibration_factor * err) >= abs(theta))

loo <- rbindlist(lapply(elections, function(e) data.table(
  omitted_election = e,
  relative_premium = mean(components[election != e, relative_premium])
)))

# Covariate support audit. Counts, not outcome-based specification selection.
support <- sample[, .(n = .N), by = .(election, treated, pre_band)]
setorder(support, election, pre_band, treated)
repeats <- sample[, .N, by = pid]
sample_flow <- rbindlist(lapply(elections, function(e) {
  d <- eligible[[as.character(e)]]
  data.table(election = e, eligible = nrow(d), no_direct_tie = sum(d$n_direct == 0L),
             exclusive_direct_tie = sum(d$n_direct == 1L),
             multiple_direct_ties = sum(d$n_direct > 1L),
             winner_followers = components[election == e, n_winner],
             loser_followers = components[election == e, n_loser])
}))
post_recording <- sample[, .(n = .N, no_recorded_post = sum(post == 0L),
                             share_no_recorded_post = mean(post == 0L)),
                         by = .(election, treated)]

fwrite(sample[, .(pid, election, patron, network, treated, pre, earlier, post, delta,
                   age, pre_band, earlier_band, ldeg, lrec, prior_status,
                   predicted_loser_change, residual_change)],
       file.path(out_dir, "analysis_sample.csv"))
fwrite(components, file.path(out_dir, "succession_contrasts.csv"))
fwrite(network_info, file.path(out_dir, "network_contributions.csv"))
fwrite(donors, file.path(out_dir, "control_network_donors.csv"))
fwrite(loo, file.path(out_dir, "leave_one_succession_out.csv"))
fwrite(support, file.path(out_dir, "rank_support.csv"))
fwrite(sample_flow, file.path(out_dir, "sample_flow.csv"))
fwrite(post_recording, file.path(out_dir, "post_recording.csv"))
fwrite(data.table(term = names(beta), coefficient = as.vector(beta)),
       file.path(out_dir, "control_model.csv"))

summary <- data.table(
  design_version = "2026-10-16-primary-v1",
  estimate = theta, ci_lower = ci[1], ci_upper = ci[2], p_bootstrap = p,
  ci_uncalibrated_lower = ci_raw[1], ci_uncalibrated_upper = ci_raw[2],
  calibration_factor = calibration_factor, bootstrap_draws = B, seed = seed,
  A_network = AB[1], B_person = AB[2], control_donor_networks = K,
  treated_networks = sum(network_info$treated == 1L),
  total_person_successions = nrow(sample), unique_people = uniqueN(sample$pid),
  people_in_multiple_successions = sum(repeats$N > 1L)
)
fwrite(summary, file.path(out_dir, "main_result.csv"))
input_paths <- file.path(data_dir,
                         c("networks/network_nodes.csv", "networks/network_edges.csv",
                           "candidates/corcholatas_matched.csv", "rank/position_tiers.csv"))
fwrite(data.table(source = sub(paste0("^", data_dir, "/"), "", input_paths),
                  md5 = unname(tools::md5sum(input_paths))),
       file.path(out_dir, "input_hashes.csv"))
fwrite(data.table(design_version = summary$design_version,
                  R_version = R.version.string,
                  data_table_version = as.character(packageVersion("data.table")),
                  estimator_script_md5 = unname(tools::md5sum(file.path(here, "estimate_main.R"))),
                  specification_md5 = unname(tools::md5sum(file.path(here, "MAIN_SPEC.md")))),
       file.path(out_dir, "run_metadata.csv"))

cat("Main relative direct-tie premium, whole rungs:", round(theta, 3), "\n")
cat("Simulation-calibrated approximate network-bootstrap 95% CI:", paste(round(ci, 3), collapse = " to "), "\n")
cat("Bootstrap p-value:", round(p, 4), "\n")
cat("Network variance components A, B:", paste(round(AB, 4), collapse = ", "), "\n")
cat("Networks treated/control:", sum(network_info$treated == 1L), "/", K, "\n")
cat("Person-successions:", nrow(sample), "; unique people:", uniqueN(sample$pid), "\n")
cat("Wrote:", out_dir, "\n")
