# Read-only reuse of the existing sample and estimators. All new files stay here.
suppressPackageStartupMessages(library(data.table))
cli <- commandArgs(FALSE)
this_file <- normalizePath(sub("^--file=", "", cli[grepl("^--file=", cli)][1]))
# Code: slides/benchmarks (this folder) and the estimators of slides/analysis. Data and results: TAPADOS_BENCH_DIR
# (default TapadosPRI/output/slides/benchmarks), with design/, calendar/, inference/ and the synthetic paths.
code_dir <- dirname(this_file)
canonical <- normalizePath(file.path(code_dir, "..", "analysis"))
default_root <- Sys.getenv("TAPADOSPRI_DB_ROOT", file.path(path.expand("~"), "Dropbox", "TapadosPRI"))
work <- Sys.getenv("TAPADOS_BENCH_DIR", file.path(default_root, "output", "slides", "benchmarks"))
refout <- Sys.getenv("TAPADOS_MAIN_OUTPUT_DIR", file.path(default_root, "output", "slides", "analysis"))   # the saved main results, read below
out <- file.path(work, "data", "design")
dir.create(out, recursive = TRUE, showWarnings = FALSE)
Sys.setenv(TAPADOS_MAIN_OUTPUT_DIR = out)
stopifnot(Sys.getenv("TAPADOS_INCLUSION", "all") == "all", Sys.getenv("TAPADOS_TIE_CUTOFF", "2") == "2")

# Evaluate the canonical loader through its last sample assertion, stopping
# BEFORE estimation/output. The marker is checked rather than copying its sample.
expressions <- parse(file.path(canonical, "estimate_main.R"))
lhs <- function(x) if (is.call(x) && identical(x[[1]], as.name("<-")) && is.symbol(x[[2]])) as.character(x[[2]]) else ""
marker <- which(vapply(expressions, lhs, "") == "controls")
stopifnot(length(marker) == 1L)
for (ex in expressions[seq_len(marker - 1L)]) eval(ex, .GlobalEnv)
for (nm in c("formula_x", "fit_variance_components")) {
  ix <- which(vapply(expressions, lhs, "") == nm)
  stopifnot(length(ix) == 1L)
  eval(expressions[[ix]], .GlobalEnv)
}
source(file.path(canonical, "design_tools.R"))
source(file.path(canonical, "rp_setup.R"))

f_window <- ~ election_factor + pre_band + earlier_band + age + ldeg + lrec + prior_status + fed_exec
f_es <- ~ election_factor + age + ldeg + lrec + prior_status + fed_exec
S_window <- make_weights(copy(A[support == TRUE]), bal_formula_window)
S_event <- make_weights(copy(A[support == TRUE]), bal_formula_es)
d_window <- build_design()
d_event <- build_design(formula = formula_es)
id <- function(d) paste(d$election, d$pid, sep = "_")
weights <- A[, .(election, pid)]
weights[, `:=`(DP_event = 0, DP_window = 0, DN_event = 0, PN_event = 0, DN_window = 0, PN_window = 0)]
weights$DP_event[match(id(d_event$S), id(A))] <- d_event$a
weights$DP_window[match(id(d_window$S), id(A))] <- d_window$a
fw <- rp_fit(S_window, S_window$delta, f_window)
fe <- rp_fit(S_event, rep(0, nrow(S_event)), f_es)
for (G in c("D", "P")) {
  set(weights, i = match(id(S_window), id(A)), j = paste0(G, "N_window"), value = fw[[G]]$a)
  set(weights, i = match(id(S_event), id(A)), j = paste0(G, "N_event"), value = fe[[G]]$a)
}
fwrite(weights, file.path(out, "weights.csv"))

# Explicitly dated educational credentials only. Unknown dates are not imputed.
ed <- read_data("clean_positions", "education.csv")
ed[, credential_level := fifelse(degree_level == "phd", 4L, fifelse(degree_level == "masters", 3L,
                            fifelse(degree_level == "undergraduate", 2L, 0L)))]
dead <- read_data("structural", "death_years.csv")[!is.na(death_year), .(death_year = min(death_year)), by = .(pid = person_id)]
A[, death_year := dead$death_year[match(pid, dead$pid)]]
A[, `:=`(credential = 0L, pre_years = 0L)]
for (e in elections) {
  eg <- ed[!is.na(year_end) & year_end <= e - 2L & credential_level > 0L,
           .(credential = max(credential_level)), by = .(pid = person_id)]
  ix <- which(A$election == e)
  cr <- eg$credential[match(A$pid[ix], eg$pid)]; cr[is.na(cr)] <- 0L
  set(A, i = ix, j = "credential", value = cr)
  pr <- annual[year >= e - 5L & year <= e - 2L, .(pre_years = uniqueN(year)), by = pid]
  set(A, i = ix, j = "pre_years", value = pr$pre_years[match(A$pid[ix], pr$pid)])
}
fwrite(A, file.path(out, "pool.csv"))

death_audit <- rbindlist(lapply(1:6, function(k) {
  z <- A[!is.na(death_year) & death_year < election + k, .(election, pid, group, death_year)]
  z[, k := k]
  z[, observed_rank := annual[data.table(pid = z$pid, year = z$election + k), on = .(pid, year), rank]]
  z[, name := nodes$name[match(pid, nodes$person_id)]]
  z[!is.na(observed_rank) & observed_rank > 0]
}))
fwrite(death_audit, file.path(out, "death_date_audit.csv"))

# Scope sensitivity: only unambiguously federal executive rules are movable.
# Other career posts remain available. The judicial, state and generic ambiguous
# titles are excluded; this is narrower than rp_setup.R's fed_exec covariate.
federal_rules <- c("ambassador_major_post", "ambassador_other", "ambassador_united_states", "consul_general",
  "attorney_general_federal", "autonomous_dept_head", "big_parastatal_head", "cabinet_secretary", "df_regent",
  "director_de_area", "director_general", "director_general_adjunto", "federal_official_in_states",
  "federal_secretary_general", "jefe_de_departamento", "jefe_de_unidad", "parastatal_head",
  "presidential_chief_of_staff", "staff", "subcabinet", "subcabinet_equivalent", "subdirector")
positions[, movable := dataset == "govt_positions" & rule %in% federal_rules]
# Exact reproduction against the current canonical tables; stop on stale inputs.
main_saved <- fread(file.path(refout, "main_result.csv"))
es_saved <- fread(file.path(refout, "event_study.csv"))
rp_saved <- fread(file.path(refout, "rp_event_study.csv"))
rp_window_saved <- fread(file.path(refout, "rp_windows.csv"))
checks <- list()
check <- function(label, got, expected) {
  err <- max(abs(got - expected))
  checks[[length(checks) + 1L]] <<- data.table(check = label, max_abs_error = err)
  if (!is.finite(err) || err > 1e-7) stop(label, " failed: ", err)
}
check("main window DP", sum(weights$DP_window * A$delta), main_saved$estimate)
obs <- list()
for (k in ks) {
  target_k <- k
  change <- YA[, as.character(k)] - YA[, as.character(ref)]
  for (contrast in c("DP", "DN", "PN")) {
    est <- sum(weights[[paste0(contrast, "_event")]] * change)
    # Since 5 November 2026 reward_punishment.R saves the EXACT penalty (P = D - the DP gap, measured for the designee's
    # followers' profile), not the own-profile P-N contrast formed here; the PN rows are therefore not compared with the
    # saved file. The deck's rules table forms the exact split from DN and DP itself (rules_table.R).
    if (contrast != "PN") {
      expected <- if (contrast == "DP") es_saved[outcome == "rank" & get("k") == target_k, estimate] else
        rp_saved[group == "D" & get("k") == target_k, estimate]
      check(paste(contrast, "event", k), est, expected)
    }
    obs[[length(obs) + 1L]] <- data.table(contrast, k, estimate = est)
  }
}
check("D window", fw[["D"]]$est, rp_window_saved[group == "D" & grepl("^Main:", spec), estimate])   # P: exact penalty saved, see above
fwrite(rbindlist(checks), file.path(out, "reproduction_checks.csv"))

# Actual statistical intervals for the observed estimates are kept separate from
# Monte Carlo variability in assignments. Joint outcomes for average annual rank.
YY <- YA[match(id(d_event$S), id(A)), , drop = FALSE]
DY <- cbind(annual_1_4 = rowMeans(YY[, as.character(1:4)]) - YY[, as.character(ref)],
            annual_1_6 = rowMeans(YY[, as.character(1:6)]) - YY[, as.character(ref)])
oe <- estimate_columns(d_event, DY, B = 50000L)
observed_summary <- oe$table[, .(contrast = "DP", outcome = column, estimate, ci_lower, ci_upper)]
for (w in list(1:4, 1:6)) {
  y <- rowMeans(YA[match(id(S_event), id(A)), as.character(w)]) - YA[match(id(S_event), id(A)), as.character(ref)]
  z <- rp_inference(S_event, rp_fit(S_event, y, f_es), B = 50000L)
  observed_summary <- rbind(observed_summary, z[, .(contrast = paste0(group, "N"),
    outcome = paste0("annual_1_", max(w)), estimate, ci_lower, ci_upper)])
}
observed_summary <- rbind(observed_summary, data.table(contrast = "DP", outcome = "window_max_1_4",
  estimate = main_saved$estimate, ci_lower = main_saved$ci_lower, ci_upper = main_saved$ci_upper),
  rp_window_saved[grepl("^Main:", spec), .(contrast = paste0(group, "N"), outcome = "window_max_1_4", estimate, ci_lower, ci_upper)])
fwrite(observed_summary, file.path(out, "observed_summary.csv"))
fwrite(es_saved[outcome == "rank", .(contrast = "DP", k, estimate, ci_lower, ci_upper)], file.path(out, "observed_dp_intervals.csv"))
# Observed D-N and P-N event-study contrasts of the benchmark design: each group of followers against the reweighted
# unaligned with its own profile (rp_fit), exactly as the rules' contrasts are formed in inference.R. Since 5 November 2026
# reward_punishment.R saves the EXACT penalty (the deck's slides), so the own-profile intervals are bootstrapped here
# with the same design and draws as inference.R (B = 50000). The D-N rows coincide with the saved reward.
obs_rp <- rbindlist(lapply(ks, function(k) {
  if (k == ref) return(data.table(contrast = c("DN", "PN"), k = k, estimate = 0, ci_lower = 0, ci_upper = 0))
  y <- YA[match(id(S_event), id(A)), as.character(k)] - YA[match(id(S_event), id(A)), as.character(ref)]
  z <- rp_inference(S_event, rp_fit(S_event, y, f_es), B = 50000L)
  z[, .(contrast = paste0(group, "N"), k = k, estimate, ci_lower, ci_upper)]
}))
stopifnot(max(abs(obs_rp[contrast == "DN" & k != ref, estimate] - rp_saved[group == "D" & k != ref][order(k), estimate])) < 1e-7)
fwrite(obs_rp, file.path(out, "observed_rp_intervals.csv"))

input_files <- c(file.path(canonical, c("estimate_main.R", "design_tools.R", "rp_setup.R")),
  file.path(data_dir, c("networks/network_nodes.csv", "networks/network_edges.csv", "candidates/corcholatas_matched.csv",
    "rank/position_tiers.csv", "clean_positions/education.csv", "structural/death_years.csv")))
fwrite(data.table(file = basename(input_files), md5 = unname(tools::md5sum(input_files))), file.path(out, "input_hashes.csv"))
cat(sprintf("Reproduced %d checks. Pool: %d person-successions; %d followers.\n", length(checks), nrow(A), nrow(sample)))
