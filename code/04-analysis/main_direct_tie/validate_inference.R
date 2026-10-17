# Finite-sample calibration of the prespecified network bootstrap on the
# observed candidate-network sizes and covariate design. Run from the repo root.
args <- commandArgs(FALSE)
script_arg <- sub("^--file=", "", args[grepl("^--file=", args)][1])
script_dir <- dirname(normalizePath(script_arg))
source(file.path(script_dir, "estimate_main.R"))
set.seed(20261017L)

draw_unit <- function(n, distribution) {
  if (distribution == "normal") return(rnorm(n))
  if (distribution == "t5") return(rt(n, df = 5) / sqrt(5 / 3))
  stop("Unknown distribution")
}

calibrate_one <- function(A_true, B_true, distribution, reps, boot_draws,
                          repeat_person_share = 0,
                          network_structure = "independent") {
  network_ix <- match(sample$network, network_info$network)
  person_ix <- match(sample$pid, unique(sample$pid))
  multipliers <- c(1, 1.05, 1.10, 1.15, 1.20)
  out <- matrix(NA_real_, nrow = reps, ncol = 4 + length(multipliers),
                dimnames = list(NULL, c(paste0("coverage_", gsub("\\.", "_", as.character(multipliers))),
                                        "width", "A_hat", "B_hat", "theta_error")))
  for (s in seq_len(reps)) {
    net_z <- draw_unit(nrow(network_info), distribution)
    if (network_structure == "zero_sum") {
      for (e in elections) {
        ix <- which(network_info$election == e)
        net_z[ix] <- (net_z[ix] - mean(net_z[ix])) * sqrt(length(ix) / (length(ix) - 1))
      }
    }
    net <- sqrt(A_true) * net_z
    person <- sqrt(B_true * repeat_person_share) * draw_unit(uniqueN(sample$pid), distribution)
    iid <- sqrt(B_true * (1 - repeat_person_share)) * draw_unit(nrow(sample), distribution)
    error <- net[network_ix] + person[person_ix] + iid
    theta_error <- sum(a * error)
    donor_r <- as.vector(Q %*% error[controls])
    nuisance <- fit_variance_components(donor_r)
    donor_var <- pmax(as.vector(moment_x %*% nuisance), .Machine$double.eps)
    z <- donor_r / sqrt(donor_var)
    z <- z - mean(z)
    if (sd(z) == 0) next
    z <- z / sd(z)
    net_sd <- sqrt(nuisance[1] + nuisance[2] / network_info$n_eff)
    draw_error <- bootstrap_error(boot_draws, z, net_sd, network_info$g)
    q <- as.numeric(quantile(draw_error, c(.025, .975), type = 1, names = FALSE))
    covered <- vapply(multipliers, function(k) {
      interval <- theta_error - k * rev(q)
      as.numeric(interval[1] <= 0 && interval[2] >= 0)
    }, 0)
    out[s, ] <- c(covered, diff(q), nuisance, theta_error)
  }
  valid <- out[complete.cases(out), , drop = FALSE]
  cv <- colMeans(valid[, seq_along(multipliers), drop = FALSE])
  data.table(A_true, B_true, distribution, repeat_person_share, network_structure,
             reps = nrow(valid), boot_draws,
             coverage_1 = cv[1], coverage_1_05 = cv[2], coverage_1_10 = cv[3],
             coverage_1_15 = cv[4], coverage_1_20 = cv[5],
             coverage_mc_se_1_20 = sqrt(cv[5] * (1 - cv[5]) / nrow(valid)),
             mean_width = mean(valid[, "width"]),
             mean_A_hat = mean(valid[, "A_hat"]),
             A_hat_zero_share = mean(valid[, "A_hat"] < 1e-10),
             mean_B_hat = mean(valid[, "B_hat"]))
}

scenarios <- rbindlist(list(
  calibrate_one(0, AB[2], "normal", 500L, 3000L),
  calibrate_one(1, AB[2], "normal", 400L, 2500L),
  calibrate_one(2, AB[2], "normal", 1500L, 2500L),
  calibrate_one(2, AB[2], "t5", 1500L, 2500L),
  calibrate_one(0, AB[2], "normal", 400L, 2500L, repeat_person_share = .5),
  calibrate_one(2, AB[2], "normal", 800L, 2500L, network_structure = "zero_sum")
))
fwrite(scenarios, file.path(out_dir, "inference_calibration.csv"))
print(scenarios)

# Observed-data sensitivity to network-shock variance. This does not estimate
# a confidence set for A: the grid is a transparent assumption check.
sensitivity <- rbindlist(lapply(c(0, .5, 1, 2, 4), function(A_assumed) {
  B_assumed <- AB[2]
  variance <- A_assumed * vA + B_assumed * vB
  z <- r / sqrt(pmax(variance, .Machine$double.eps))
  z <- (z - mean(z)) / sd(z)
  net_sd <- sqrt(A_assumed + B_assumed / network_info$n_eff)
  draws <- bootstrap_error(30000L, z, net_sd, network_info$g)
  q <- as.numeric(quantile(draws, c(.025, .975), type = 1, names = FALSE))
  data.table(A_assumed, B_assumed,
             ci_lower = theta - calibration_factor * q[2],
             ci_upper = theta - calibration_factor * q[1],
             p_value = mean(abs(calibration_factor * draws) >= abs(theta)))
}))
fwrite(sensitivity, file.path(out_dir, "network_variance_sensitivity.csv"))
print(sensitivity)
metadata_path <- file.path(out_dir, "run_metadata.csv")
metadata <- fread(metadata_path)
metadata[, validation_script_md5 := unname(tools::md5sum(file.path(script_dir, "validate_inference.R")))]
fwrite(metadata, metadata_path)
