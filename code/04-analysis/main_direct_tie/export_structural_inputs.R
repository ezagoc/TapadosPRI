# Inputs of the structural model (research/structural_2026-10-19/MODEL_SPEC.md sections 2-4 and 8): the observed state of
# every succession cycle, ties, observed chairs, seat capacities, and the linear weights a of every design estimator that is
# a targeted moment, with a unit test that a'y_obs reproduces each published estimate to 1e-10.
# Run after the reduced form and code/07-structural/01_death_years.py, once per pool:
#   Rscript code/04-analysis/main_direct_tie/export_structural_inputs.R
#   TAPADOS_INCLUSION=predetermined TAPADOS_MAIN_OUTPUT_DIR=<...>/robust_predetermined_inclusion Rscript ...
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
invisible(capture.output(source(file.path(script_dir, "estimate_main.R"))))
source(file.path(script_dir, "design_tools.R"))
invisible(capture.output(source(file.path(script_dir, "rp_setup.R"))))
rule <- inclusion_rule
struct_dir <- file.path(data_dir, "structural"); dir.create(struct_dir, showWarnings = FALSE)
deaths <- fread(file.path(struct_dir, "death_years.csv")); presidents <- fread(file.path(struct_dir, "presidents.csv"))
death_of <- function(ids) deaths$death_year[match(ids, deaths$person_id)]
rank_at <- function(ids, years) { z <- annual[data.table(pid = ids, year = years), on = .(pid, year), rank]; z[is.na(z)] <- 0L; as.integer(z) }
K_ALL <- -8:8; T_SIM <- -1:8
tol <- 1e-10

# ------------------------------------------------------------------ 1. state, ties, chairs, capacities (full pool only)
if (rule == "all") {
  pool <- rbindlist(lapply(elections, function(e) {
    d <- copy(eligible[[as.character(e)]]); w <- slates[[as.character(e)]]$winner
    d[, group := fifelse(n_direct == 0L, "N", fifelse(n_direct == 1L & patron == w, "D", fifelse(n_direct == 1L, "P", "M")))]
    d[, patron_kept := fifelse(group == "P", as.integer(patrons$rung_post2[match(paste(e, patron), paste(patrons$election, patrons$patron))] >= 8L), NA_integer_)]
    later <- contenders[election_year > e & election_year <= e + 12L, .(obs_from = min(election_year) - 2L), by = .(pid = person_id)]
    d[, obs_from := later$obs_from[match(pid, later$pid)]]
    d[, `:=`(birth_year = as.integer(birth[as.character(pid)]), death_year = death_of(pid),
             qual_by_e2 = as.integer(pid %in% first_qualifying[first_year <= e - 2L, pid]))]
    for (k in K_ALL) set(d, j = sprintf("R_%s%d", ifelse(k < 0, "m", "p"), abs(k)), value = rank_at(d$pid, e + k))
    d[, .SD, .SDcols = c("election", "pid", "group", "patron", "patron_kept", "n_direct", "age", "birth_year", "death_year",
                         "obs_from", "qual_by_e2", "pre", "earlier", "ldeg", "lrec", grep("^R_", names(d), value = TRUE))]
  }))
  fwrite(pool, file.path(struct_dir, "pool.csv"))

  tw <- edges[edge_type %in% tie_types & !is.na(year_start), .(a = person_a, b = person_b, year_start, w = tie_weight)]
  tw <- rbind(tw, tw[, .(a = b, b = a, year_start, w)])
  ties <- rbindlist(lapply(elections, function(e) {
    ids <- pool[election == e, pid]
    tw[a %in% ids & year_start <= e - 2L & a != b, .(c = min(1, sum(w))), by = .(i = a, j = b)][, election := e]
  }))
  setcolorder(ties, c("election", "i", "j", "c")); fwrite(ties, file.path(struct_dir, "ties.csv"))

  chairs <- rbindlist(lapply(elections, function(e) {
    P <- pool[election == e]
    js <- unique(c(ties[election == e, j], presidents$person_id))
    g <- CJ(j = js, t = e + T_SIM)
    g <- g[!(j %in% P[is.na(obs_from), pid])]                           # simulated pool members are not observed
    g <- g[!(j %in% P[!is.na(obs_from), pid]) | t >= P$obs_from[match(j, P$pid)]]
    g[, rung := rank_at(j, t)]
    pr <- presidents[match(g$j, presidents$person_id)]
    alive <- is.na(death_of(g$j)) | g$t < death_of(g$j)
    g[, cat := fifelse(!is.na(pr$term_start) & t >= pr$term_start & t <= pr$term_end, "P",
               fifelse(!is.na(pr$term_end) & t > pr$term_end & alive, fifelse(rung >= 8L, "XT", "X"),
               fifelse(alive & rung >= 8L, "T", "R")))]
    g[cat != "R", .(election = e, j, t, cat)]
  }))
  fwrite(chairs, file.path(struct_dir, "chairs.csv"))

  caps <- rbindlist(lapply(elections, function(e) {
    P <- pool[election == e]
    rbindlist(lapply(T_SIM, function(k) {
      t <- e + k; sim <- is.na(P$obs_from) | t < P$obs_from
      r <- rank_at(P$pid[sim], rep(t, sum(sim)))
      data.table(election = e, t = t, r = 1:9, M = tabulate(r, nbins = 9))
    }))
  }))
  fwrite(caps, file.path(struct_dir, "capacities.csv"))
  losers <- rbindlist(lapply(elections, function(e) {
    l <- data.table(election = e, pid = setdiff(slates[[as.character(e)]]$candidates, slates[[as.character(e)]]$winner))
    for (k in T_SIM) set(l, j = sprintf("R_%s%d", ifelse(k < 0, "m", "p"), abs(k)), value = rank_at(l$pid, rep(e + k, nrow(l))))
    l
  }))
  fwrite(losers, file.path(struct_dir, "losers.csv"))
  cat("pool:", nrow(pool), "person-cycles; ties:", nrow(ties), "; observed chair-years:", nrow(chairs), "\n")
}

# ------------------------------------------------------------------ 2. linear weights of the design estimators (this pool)
S_es <- make_weights(A[support == TRUE], bal_formula_es)
YS <- YA[A$support == TRUE, , drop = FALSE]
fD <- rp_fit(S_es, rep(0, nrow(S_es)), f_es <- ~ election_factor + age + ldeg + lrec + prior_status + fed_exec)
S_sp <- split_groups(S_es)
fPk <- lin_fit(S_sp, rep(0, nrow(S_sp)), f_es, "Pk"); fPl <- lin_fit(S_sp, rep(0, nrow(S_sp)), f_es, "Pl")
S_win <- make_weights(A[support == TRUE], bal_formula_window)
d_all <- build_design()
aux <- merge(S_es[, .(election, pid, group, in_es = 1L, w_es = fifelse(group == "N", w, 0), a_D_es = fD$D$a, a_P_es = fD$P$a)],
             S_sp[, .(election, pid, g_split = g, a_Pk_es = fPk$a, a_Pl_es = fPl$a)], by = c("election", "pid"), all = TRUE)
aux <- merge(aux, S_win[, .(election, pid, in_win = 1L, w_win = fifelse(group == "N", w, 0))], by = c("election", "pid"), all = TRUE)
aux <- merge(aux, d_all$S[, .(election, pid, in_main = 1L, treated_main = treated, a_ext = d_all$a)], by = c("election", "pid"), all = TRUE)
for (v in c("in_es", "in_win", "in_main", "w_es", "w_win", "a_D_es", "a_P_es", "a_Pk_es", "a_Pl_es", "a_ext")) set(aux, which(is.na(aux[[v]])), v, 0)
fwrite(aux, file.path(struct_dir, sprintf("aux_%s.csv", rule)))
Xm <- model.matrix(formula_x, data = d_all$S)
fwrite(cbind(d_all$S[, .(election, pid, treated, pre)], as.data.table(Xm)), file.path(struct_dir, sprintf("aux_X_%s.csv", rule)))

# ------------------------------------------------------------------ 3. targets and the unit test a'y_obs = published
es_rp <- fread(file.path(out_dir, "rp_event_study.csv"))[group == "D"]
es_rpP <- fread(file.path(out_dir, "rp_event_study.csv"))[group == "P"]
es_cs <- fread(file.path(out_dir, "chair_split_event_study.csv"))
mg <- fread(file.path(out_dir, "margins_windows.csv"))
chk <- rbindlist(lapply(setdiff(ks, ref), function(kk) {
  y <- YS[, as.character(kk)] - YS[, as.character(ref)]
  data.table(moment = c("D", "P", "Pk", "Pl"), k = kk, a_y = c(sum(fD$D$a * y), sum(fD$P$a * y), sum(fPk$a * y), sum(fPl$a * y)),
             published = c(es_rp[k == kk, estimate], es_rpP[k == kk, estimate], es_cs[k == kk & grepl("^Pk:", estimate), value],
                           es_cs[k == kk & grepl("^Pl:", estimate), value]))
}))
ext_y <- as.numeric(sample$post[d_all$rows] > 0) - as.numeric(sample$pre[d_all$rows] > 0)
chk <- rbind(chk, data.table(moment = "extensive", k = NA_integer_, a_y = sum(d_all$a * ext_y), published = mg[column == "extensive", estimate]))
chk[, diff := abs(a_y - published)]
print(chk[, .(max_abs_diff = max(diff)), by = moment])
stopifnot(all(chk$diff < tol))
targets <- rbind(
  es_rp[k >= -1, .(family = "D_es", k, value = estimate, se = (ci_upper - ci_lower) / (2 * 1.96))],
  es_cs[!grepl("within", estimate) & k >= -1, .(family = fifelse(grepl("^Pk:", estimate), "Pk_es", "Pl_es"), k, value, se)],
  mg[column %in% c("extensive", "intensive"), .(family = column, k = NA_integer_, value = estimate, se = (ci_upper - ci_lower) / (2 * 1.96))])
fwrite(targets, file.path(struct_dir, sprintf("targets_%s.csv", rule)))
cat("export done for pool:", rule, "| unit test passed (max diff", signif(max(chk$diff), 2), ")\n")
