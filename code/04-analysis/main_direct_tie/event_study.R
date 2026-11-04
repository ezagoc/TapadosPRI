# Event study of the main direct-tie contrast (MAIN_SPEC.md section 7, 17 October 2026).
# Run from the repo root: Rscript code/04-analysis/main_direct_tie/event_study.R
# Sources estimate_main.R (same sample, weights and network layout) and writes the
# event-study tables and figures to the same output directory.
args <- commandArgs(FALSE)
script_arg <- sub("^--file=", "", args[grepl("^--file=", args)][1])
script_dir <- dirname(normalizePath(script_arg))

# estimate_main.R rewrites run_metadata.csv; keep the validation hash if nothing it
# certifies has changed.
db_root_pre <- Sys.getenv("TAPADOSPRI_DB_ROOT", file.path(path.expand("~"), "Dropbox", "TapadosPRI"))
metadata_pre_path <- file.path(Sys.getenv("TAPADOS_MAIN_OUTPUT_DIR", file.path(db_root_pre, "output", "main_direct_tie")),
                               "run_metadata.csv")
metadata_pre <- if (file.exists(metadata_pre_path)) data.table::fread(metadata_pre_path) else NULL

source(file.path(script_dir, "estimate_main.R"))
suppressPackageStartupMessages(library(ggplot2))
set.seed(17102026L)

ks <- -7:8
ref <- -2L
leads <- -7:-3
summaries <- list(lead_average = leads, main_window_average = 1:4, term_average = 1:6,
                  next_president_average = 7:8)

# Annual highest whole rung (0 if no retained ranked post), the same annual table as the main estimate.
year_rank <- function(k) {
  z <- annual[data.table(pid = sample$pid, year = sample$election + k), on = .(pid, year), rank]
  z[is.na(z)] <- 0L
  as.integer(z)
}
Y <- sapply(ks, year_rank)
colnames(Y) <- ks
outcomes <- list(
  rank = Y - Y[, as.character(ref)],
  any_post = (Y > 0) - (Y[, as.character(ref)] > 0)
)

# Linear weights of the section-4 estimator for a given covariate matrix: the loser-only
# outcome model with weights 1/n0e, the treated mean residual by succession, equal average.
design <- function(Xm) {
  X0m <- Xm[controls, , drop = FALSE]
  if (qr(X0m * sqrt(w0))$rank != ncol(X0m)) stop("Event-study control model is rank-deficient.")
  Mm <- solve(crossprod(X0m, X0m * w0))
  bm <- Reduce(`+`, lapply(elections, function(e)
    omega[[as.character(e)]] * colMeans(Xm[sample$election == e & sample$treated == 1L, , drop = FALSE])))
  am <- numeric(nrow(sample))
  am[controls] <- -w0 * as.vector(X0m %*% (Mm %*% bm))
  for (e in elections) {
    ix <- which(sample$election == e & sample$treated == 1L)
    am[ix] <- omega[[as.character(e)]] / length(ix)
  }
  Qm <- Cmat - sweep((Cmat %*% X0m) %*% Mm %*% t(X0m), 2L, w0, "*")
  net <- data.table(network = sample$network, a = am)[, .(g = sum(a), weight_squares = sum(a^2)), by = network]
  net <- net[match(network_info$network, network)]
  list(X = Xm, X0 = X0m, M = Mm, a = am, Q = Qm, moments = cbind(rowSums((Qm %*% Z)^2), rowSums(Qm^2)),
       g = net$g, n_eff = net$g^2 / net$weight_squares)
}
main_design <- design(X)
stopifnot(max(abs(main_design$a - a)) < 1e-10)
X_es <- model.matrix(~ election_factor + age + ldeg + lrec + prior_status, data = sample)
es_design <- design(X_es)

succession_contrast <- function(y, d) {
  beta_y <- as.vector(d$M %*% crossprod(d$X0, w0 * y[controls]))
  residual <- y - as.vector(d$X %*% beta_y)
  data.table(election = sample$election, treated = sample$treated, residual = residual)[
    treated == 1L, .(estimate = mean(residual)), by = election]
}

# Joint network bootstrap: one donor network per slot and draw, used at every year.
B_es <- 50000L
donor_index <- matrix(base::sample.int(K, length(network_info$network) * B_es, replace = TRUE),
                      nrow = length(network_info$network))
bootstrap_columns <- function(Ym, d) {
  err <- matrix(NA_real_, nrow = ncol(Ym), ncol = B_es, dimnames = list(colnames(Ym), NULL))
  components <- vector("list", ncol(Ym))
  for (j in seq_len(ncol(Ym))) {
    y <- Ym[, j]
    r_y <- as.vector(d$Q %*% y[controls])
    if (all(abs(r_y) < 1e-12)) { err[j, ] <- 0; next }
    ab <- fit_variance_components(r_y, d$moments)
    z <- r_y / sqrt(pmax(as.vector(d$moments %*% ab), .Machine$double.eps))
    z <- (z - mean(z)) / sd(z)
    coefs <- d$g * sqrt(ab[1] + ab[2] / d$n_eff)
    err[j, ] <- colSums(coefs * matrix(z[donor_index], nrow = nrow(donor_index)))
    components[[j]] <- data.table(column = colnames(Ym)[j], A = ab[1], B = ab[2])
  }
  list(err = err, components = rbindlist(components))
}

interval <- function(est, e, level) {
  q <- as.numeric(quantile(e, c((1 - level) / 2, 1 - (1 - level) / 2), type = 1, names = FALSE))
  c(est - q[2], est - q[1])
}

run_outcome <- function(name, dY) {
  window <- if (name == "rank") sample$delta else
    as.numeric(sample$post > 0) - as.numeric(sample$pre > 0)
  Ym <- cbind(dY[, colnames(dY) != as.character(ref), drop = FALSE], main_window = window)
  est <- as.vector(crossprod(es_design$a, Ym))
  names(est) <- colnames(Ym)
  boot <- bootstrap_columns(Ym, es_design)
  err <- boot$err
  yr <- setdiff(colnames(Ym), "main_window")
  s_k <- apply(err[yr, , drop = FALSE], 1L, sd)
  sup_t <- apply(abs(err[yr, , drop = FALSE]) / s_k, 2L, max)
  crit <- as.numeric(quantile(sup_t, .95, type = 1))
  yearly <- rbindlist(lapply(ks, function(k) {
    if (k == ref) return(data.table(outcome = name, k = k, estimate = 0, ci_lower = 0, ci_upper = 0,
                                    ci90_lower = 0, ci90_upper = 0, uniform_lower = 0, uniform_upper = 0,
                                    p_bootstrap = NA_real_,
                                    A = NA_real_, B = NA_real_))
    j <- as.character(k)
    ci <- interval(est[j], err[j, ], .95)
    ci90 <- interval(est[j], err[j, ], .90)
    vc <- boot$components[column == j]
    data.table(outcome = name, k = k, estimate = est[j], ci_lower = ci[1], ci_upper = ci[2],
               ci90_lower = ci90[1], ci90_upper = ci90[2],
               uniform_lower = est[j] - crit * s_k[j], uniform_upper = est[j] + crit * s_k[j],
               p_bootstrap = mean(abs(err[j, ]) >= abs(est[j])), A = vc$A, B = vc$B)
  }))
  combos <- c(lapply(summaries, function(kk) {
    w <- setNames(rep(1 / length(kk), length(kk)), as.character(kk)); w }),
    list(change_7_minus_6 = c("7" = 1, "6" = -1)))
  summary_rows <- rbindlist(lapply(names(combos), function(nm) {
    w <- combos[[nm]]
    e_c <- as.vector(crossprod(w, err[names(w), , drop = FALSE]))
    v <- sum(w * est[names(w)])
    ci <- interval(v, e_c, .95); ci90 <- interval(v, e_c, .90)
    data.table(outcome = name, contrast = nm, estimate = v, ci_lower = ci[1], ci_upper = ci[2],
               ci90_lower = ci90[1], ci90_upper = ci90[2],
               p_bootstrap = mean(abs(e_c) >= abs(v)))
  }))
  lead_names <- as.character(leads)
  lead_stat <- max(abs(est[lead_names]) / s_k[lead_names])
  lead_draws <- apply(abs(err[lead_names, , drop = FALSE]) / s_k[lead_names], 2L, max)
  ci_w <- interval(est["main_window"], err["main_window", ], .95)
  summary_rows <- rbind(summary_rows, data.table(
    outcome = name, contrast = c("joint_lead_test_max_t", "main_window_event_study_covariates"),
    estimate = c(lead_stat, est["main_window"]),
    ci_lower = c(NA, ci_w[1]), ci_upper = c(NA, ci_w[2]),
    ci90_lower = NA_real_, ci90_upper = NA_real_,
    p_bootstrap = c(mean(lead_draws >= lead_stat), mean(abs(err["main_window", ]) >= abs(est["main_window"])))),
    fill = TRUE)
  if (name == "rank") {
    summary_rows <- rbind(summary_rows, data.table(outcome = name, contrast = "main_estimate_section_4",
      estimate = theta, ci_lower = ci[1], ci_upper = ci[2], p_bootstrap = p), fill = TRUE)
  }
  by_succession <- rbindlist(lapply(colnames(Ym), function(j)
    succession_contrast(Ym[, j], es_design)[, `:=`(outcome = name, k = j)]))
  stopifnot(max(abs(by_succession[, .(m = sum(omega[as.character(election)] * estimate)), by = k][match(names(est), k), m] - est)) < 1e-8)
  list(yearly = yearly, summary = summary_rows, by_succession = by_succession,
       sup_t_critical = crit)
}

results <- lapply(names(outcomes), function(nm) run_outcome(nm, outcomes[[nm]]))
names(results) <- names(outcomes)
yearly <- rbindlist(lapply(results, `[[`, "yearly"))
summary_es <- rbindlist(lapply(results, `[[`, "summary"), fill = TRUE)
by_succession <- rbindlist(lapply(results, `[[`, "by_succession"))
raw_means <- rbindlist(lapply(ks, function(k) {
  data.table(election = sample$election, treated = sample$treated, rank = Y[, as.character(k)])[
    , .(n = .N, mean_rank = mean(rank), share_with_post = mean(rank > 0)), by = .(election, treated)][, k := k][]
}))
setorder(raw_means, election, treated, k)

fwrite(yearly, file.path(out_dir, "event_study.csv"))
fwrite(summary_es, file.path(out_dir, "event_study_summary.csv"))
fwrite(by_succession, file.path(out_dir, "event_study_by_succession.csv"))
fwrite(raw_means, file.path(out_dir, "event_study_raw_means.csv"))
fwrite(data.table(term = colnames(X_es), coefficient = as.vector(es_design$M %*% crossprod(es_design$X0, w0 * outcomes$rank[controls, "4"]))),
       file.path(out_dir, "event_study_control_model_k4.csv"))

# Figures in the deck's house style: white, no grid, the deck's dark red, direct labels.
RED <- "#940034"; G2 <- "#8c8c8c"; INK <- "#1a1a1a"; MUTED <- "#6b6b6b"; FAM <- "Helvetica"
theme_deck <- function(base = 18) theme_minimal(base_size = base, base_family = FAM) +
  theme(panel.grid = element_blank(), plot.background = element_rect(fill = "white", colour = NA),
        axis.line.x = element_line(colour = MUTED, linewidth = 0.4), axis.ticks.x = element_line(colour = MUTED, linewidth = 0.4),
        axis.text = element_text(colour = MUTED, size = base - 2), axis.title = element_text(colour = INK, size = base - 1),
        plot.caption = element_text(hjust = 0, colour = MUTED, size = base - 7), plot.caption.position = "plot",
        legend.position = "none", plot.margin = margin(8, 16, 6, 8))
event_figure <- function(name, ylab, scale, digits, unit, file) {
  d <- yearly[outcome == name]
  s <- summary_es[outcome == name]
  f <- function(x) { v <- round(scale * x, digits); ifelse(v == 0, "0", sprintf(paste0("%+.", digits, "f"), v)) }
  lab <- function(row) sprintf("%s%s [%s, %s]", f(row$estimate), unit, f(row$ci_lower), f(row$ci_upper))
  top <- scale * max(d$ci_upper) * 1.18
  bot <- scale * min(d$ci_lower, 0) - 0.25 * (top - scale * min(d$ci_lower, 0))
  marks <- data.table(x = c(-1.5, 0.5, 4.5, 6.5), lab = c("destape", "new president", "next destape", "next president"),
                      y = top * c(1, 0.9, 1, 0.9))
  label_y <- bot + 0.07 * (top - bot)
  g <- ggplot(d, aes(k, scale * estimate)) +
    annotate("rect", xmin = 6.5, xmax = 8.5, ymin = -Inf, ymax = Inf, fill = "#f2f2f2") +
    geom_hline(yintercept = 0, colour = G2, linewidth = 0.4) +
    geom_vline(data = marks, aes(xintercept = x), colour = G2, linewidth = 0.4, linetype = "22") +
    geom_text(data = marks, aes(x = x + 0.12, y = y, label = lab), hjust = 0, vjust = 1, colour = MUTED,
              size = 4.2, family = FAM) +
    geom_line(colour = RED, linewidth = 0.5, alpha = 0.5) +
    geom_linerange(aes(ymin = scale * ci_lower, ymax = scale * ci_upper), colour = RED, linewidth = 0.6) +
    geom_linerange(aes(ymin = scale * ci90_lower, ymax = scale * ci90_upper), colour = RED, linewidth = 1.8) +
    geom_point(colour = RED, size = 2.6) +
    annotate("label", fill = NA, border.colour = NA, x = -5, y = label_y, lineheight = 0.9, size = 4.8, family = FAM,
             colour = MUTED, label = paste0("e-7 to e-3\n", lab(s[contrast == "lead_average"]))) +
    annotate("label", fill = NA, border.colour = NA, x = 2.5, y = label_y, lineheight = 0.9, size = 4.8, family = FAM,
             colour = RED, label = paste0("e+1 to e+4\n", lab(s[contrast == "main_window_average"]))) +
    annotate("label", fill = NA, border.colour = NA, x = 7.5, y = label_y, lineheight = 0.9, size = 4.8, family = FAM,
             colour = MUTED, label = paste0("e+7 to e+8\n", lab(s[contrast == "next_president_average"]))) +
    scale_x_continuous(breaks = ks, labels = function(x) ifelse(x == 0, "e", sprintf("%+d", x))) +
    coord_cartesian(ylim = c(bot, top), clip = "off") +
    labs(x = "Years relative to the election", y = ylab,
         caption = paste("Designee's vs losing contenders' exclusive direct followers, change from e-2, adjusted for",
                         if (succession_weights == "equal") "predetermined traits; equal weight per succession.\nThick bars 90%, thin bars 95%," else
                         "predetermined traits; successions weighted by the designee's followers.\nThick bars 90%, thin bars 95%,",
                         "Ferman-Pinto bootstrap at the contender level.")) +
    theme_deck()
  ggsave(file.path(out_dir, paste0(file, ".pdf")), g, width = 10, height = 5.2, bg = "white", device = "pdf")
  ggsave(file.path(out_dir, paste0(file, ".png")), g, width = 10, height = 5.2, dpi = 250, bg = "white")
}
event_figure("rank", "Rank gap, rungs", 1, 2, "", "event_study_rank")
event_figure("any_post", "Holds a ranked post, pp", 100, 0, "", "event_study_any_post")

metadata <- fread(file.path(out_dir, "run_metadata.csv"))
if (!is.null(metadata_pre) && "validation_script_md5" %in% names(metadata_pre) &&
    identical(metadata_pre$estimator_script_md5, metadata$estimator_script_md5) &&
    identical(metadata_pre$specification_md5, metadata$specification_md5)) {
  metadata[, validation_script_md5 := metadata_pre$validation_script_md5]
}
metadata[, event_study_script_md5 := unname(tools::md5sum(file.path(script_dir, "event_study.R")))]
metadata[, event_study_seed := 17102026L]
fwrite(metadata, file.path(out_dir, "run_metadata.csv"))

cat("\nEvent study, rank (rungs):\n")
print(yearly[outcome == "rank", .(k, estimate = round(estimate, 3), ci_lower = round(ci_lower, 3),
                                  ci_upper = round(ci_upper, 3), p_bootstrap)])
cat("\nSummary contrasts:\n")
print(summary_es[, .(outcome, contrast, estimate = round(estimate, 3), ci_lower = round(ci_lower, 3),
                     ci_upper = round(ci_upper, 3), p_bootstrap)])
