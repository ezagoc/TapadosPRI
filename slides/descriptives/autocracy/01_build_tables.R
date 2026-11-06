# 01_build_tables.R -- cross-national benchmark for the PRI: regime duration and
# regular leader successions per autocratic regime spell.
#
# Inputs (downloaded 2026-10-13, saved as received; read only, never executed):
#   GWF (2014) Autocratic Regimes 1.2      gwf_2014/extracted/GWF Autocratic Regimes 1.2/GWFcases.dta
#   Archigos 4.1                           archigos_v4.1/Archigos_4.1_stata14.dta
#   Svolik (2012) leader data              svolik_2012/extracted/leader/leadership change in dictatorships, 1946-2008.dta
#   V-Dem RoW v16 via OWID                 vdem_row/political-regime.csv
# Outputs: <autocracies>/tables/*.csv
#
# Run: Rscript 01_build_tables.R

suppressMessages({
  library(data.table)
  library(haven)
  library(survival)
})

data_dir <- Sys.getenv("TAPADOSPRI_DATA_DIR", file.path(Sys.getenv("TAPADOSPRI_DB_ROOT", file.path(path.expand("~"), "Dropbox", "TapadosPRI")), "data"))
B   <- file.path(data_dir, "_web_discovery_2026-10-13", "autocracies")   # the downloaded sources (README.md there)
OUT <- file.path(B, "tables")
dir.create(OUT, showWarnings = FALSE)

GWF_END   <- as.Date("2010-12-31")   # GWF censoring date
GWF_BEGIN <- as.Date("1946-01-01")   # GWF observation window starts here (left truncation)
TOL       <- 30                      # days: a leader change within 30 days of a regime's start or end
                                     # is treated as part of the regime change, not a within-regime succession
yrs <- function(d) as.numeric(d) / 365.25

# Project definition of the Mexican regime: PNR founded 4 Mar 1929; GWF end event = 2 Jul 2000 election.
MEX_PROJECT_START <- as.Date("1929-03-04")
MEX_END           <- as.Date("2000-07-02")

# ---------------------------------------------------------------------------
# 1. GWF regime spells
# ---------------------------------------------------------------------------
g <- as.data.table(read_dta(file.path(B, "gwf_2014/extracted/GWF Autocratic Regimes 1.2/GWFcases.dta")))
g[, `:=`(start = as.Date(gwf_startdate), end = as.Date(gwf_enddate),
         event = as.integer(!is.na(gwf_endyr)))]
stopifnot(all(g[event == 0, end] == GWF_END))
g[, definition := "gwf"]

mex_gwf <- g[cowcode == 70]
stopifnot(nrow(mex_gwf) == 1, mex_gwf$end == MEX_END)
mex_proj <- copy(mex_gwf)
mex_proj[, `:=`(start = MEX_PROJECT_START, gwf_casename = "Mexico 29-00 (PNR/PRM/PRI, project definition)",
                definition = "project")]
g <- rbind(g, mex_proj)
# Main sample: every GWF spell, with Mexico's spell replaced by the project definition.
g[, in_main := as.integer(!(cowcode == 70 & definition == "gwf"))]

g[, party_any    := as.integer(grepl("party", gwf_regimetype))]      # party-based + party hybrids
g[, party_strict := as.integer(gwf_regimetype == "party-based")]
g[, duration_yrs := yrs(end - start)]
g[, entry_yrs    := pmax(0, yrs(GWF_BEGIN - start))]                 # delayed entry for pre-1946 regimes
g[, spell_id := .I]

# ---------------------------------------------------------------------------
# 2. Optional extension of right-censoring with V-Dem Regimes of the World (v16, to 2025)
#    Ongoing GWF spells are extended while the country stays autocratic (RoW 0/1); the spell
#    ends in the first year RoW codes it a democracy (2/3). Autocrat-to-autocrat regime changes
#    after 2010 (e.g. Egypt 2011/13, Thailand 2014) are NOT detected -> upper bound on survival.
# ---------------------------------------------------------------------------
row <- fread(file.path(B, "vdem_row/political-regime.csv"))
name_map <- c("Cen African Rep" = "Central African Republic", "Congo-Brz" = "Congo",
              "Congo/Zaire" = "Democratic Republic of Congo", "Ivory Coast" = "Cote d'Ivoire",
              "Korea North" = "North Korea", "Swaziland" = "Eswatini")
g[, owid_entity := fifelse(gwf_country %in% names(name_map), name_map[gwf_country], gwf_country)]
ROW_LAST <- max(row$year)
g[, `:=`(end_ext = end, event_ext = event)]
for (i in g[event == 0, which = TRUE]) {
  r <- row[entity == g$owid_entity[i] & year > 2010 & year <= ROW_LAST][order(year)]
  stopifnot(max(r$year) == ROW_LAST, nrow(r) >= ROW_LAST - 2011)  # CAR and Egypt lack 2014 in RoW
  dem <- r[regime_row_owid >= 2]
  if (nrow(dem)) {
    set(g, i, "end_ext", as.Date(sprintf("%d-07-01", dem$year[1])))  # mid-year of first democratic year
    set(g, i, "event_ext", 1L)
  } else {
    set(g, i, "end_ext", as.Date(sprintf("%d-12-31", ROW_LAST)))
  }
}
g[, duration_ext_yrs := yrs(end_ext - start)]

# ---------------------------------------------------------------------------
# 3. Archigos leaders -> within-spell leader transitions
# ---------------------------------------------------------------------------
a <- as.data.table(read_dta(file.path(B, "archigos_v4.1/Archigos_4.1_stata14.dta"), encoding = "latin1"))
a[, `:=`(ls = as.Date(startdate), le = as.Date(enddate))]
stopifnot(!anyNA(a$ls), !anyNA(a$le))
setorder(a, ccode, ls, le)
a[, `:=`(next_leader = shift(leader, -1), next_start = shift(ls, -1)), by = ccode]
pairs <- a[!is.na(next_leader),
           .(ccode, prev_leader = leader, prev_start = ls, prev_end = le, prev_exit = exit,
             prev_exitcode = exitcode, prev_fate = posttenurefate, next_leader, T = next_start)]

# A transition belongs to spell s if the predecessor governed inside s and the successor took
# office strictly inside s (more than TOL days after its start and before its end).
tr <- pairs[g[, .(spell_id, ccode = cowcode, S = start, E = end)], on = "ccode", allow.cartesian = TRUE, nomatch = 0]
tr <- tr[prev_end >= S + TOL & T > S + TOL & T < E - TOL]
tr[, regular       := as.integer(prev_exit == "Regular")]
tr[, alive_nonviol := as.integer(prev_exit %in% c("Regular", "Retired Due to Ill Health"))]
tr[, regular_ok    := as.integer(prev_exit == "Regular" & prev_fate == "OK")]
tr[, non_irregular := as.integer(prev_exit %in% c("Regular", "Retired Due to Ill Health", "Natural Death"))]
tr[, in_1946_2010  := as.integer(T >= GWF_BEGIN & T <= GWF_END)]

cnt <- tr[, .(n_transitions = .N, n_regular = sum(regular), n_alive_nonviolent = sum(alive_nonviol),
              n_regular_fate_ok = sum(regular_ok), n_non_irregular = sum(non_irregular),
              n_regular_1946_2010 = sum(regular * in_1946_2010),
              first_transition = min(T), last_transition = max(T)), by = spell_id]
g <- cnt[g, on = "spell_id"]
for (v in c("n_transitions", "n_regular", "n_alive_nonviolent", "n_regular_fate_ok", "n_non_irregular", "n_regular_1946_2010"))
  set(g, which(is.na(g[[v]])), v, 0L)

# Caretaker-robust variant ("substantive leaders"): drop leader spells shorter than 18 months
# (acting/interim heads, Yugoslavia's annual rotating chairs), merge consecutive spells of the same
# person (Archigos leadid), and count handovers between the remaining leaders whose predecessor's own
# exit was Regular.
SUBST_MIN_YRS <- 1.5
sub <- a[yrs(le - ls) >= SUBST_MIN_YRS]
setorder(sub, ccode, ls)
sub[, run := rleid(ccode, leadid)]
sub <- sub[, .(ccode = ccode[1], leadid = leadid[1], leader = leader[1], ls = min(ls), le = max(le),
               exit = exit[.N]), by = run]
sub[, `:=`(next_leader = shift(leader, -1), next_start = shift(ls, -1)), by = ccode]
tr_sub <- sub[!is.na(next_leader), .(ccode, prev_leader = leader, prev_end = le, prev_exit = exit, next_leader, T = next_start)
             ][g[, .(spell_id, ccode = cowcode, S = start, E = end)], on = "ccode", allow.cartesian = TRUE, nomatch = 0
             ][prev_end >= S + TOL & T > S + TOL & T < E - TOL]
g[tr_sub[, .(n = sum(prev_exit == "Regular")), by = spell_id], on = "spell_id", n_regular_substantive := i.n]
g[is.na(n_regular_substantive), n_regular_substantive := 0L]

# Number of Archigos leaders in office during each spell (coverage check)
lead_n <- a[g[, .(spell_id, ccode = cowcode, S = start, E = end)], on = "ccode", allow.cartesian = TRUE, nomatch = 0
           ][le > S & ls < E, .(n_leaders = .N), by = spell_id]
g <- lead_n[g, on = "spell_id"]
g[is.na(n_leaders), n_leaders := 0L]
g[, archigos_covers_start := as.integer(start >= as.Date("1875-01-01"))]

# Sensitivity of the main count to the tolerance window (0 and 180 days)
sens <- function(tol) {
  t2 <- pairs[g[, .(spell_id, ccode = cowcode, S = start, E = end)], on = "ccode", allow.cartesian = TRUE, nomatch = 0]
  t2[prev_end >= S + tol & T > S + tol & T < E - tol & prev_exit == "Regular", .(n = .N), by = spell_id]
}
for (tol in c(0, 180)) {
  s <- sens(tol); v <- paste0("n_regular_tol", tol)
  g[s, on = "spell_id", (v) := i.n]; set(g, which(is.na(g[[v]])), v, 0L)
}

# Mexico check: 1934-2000 handovers (the deck's "eleven")
mex_tr <- tr[spell_id == g[definition == "project", spell_id]]
n_mex_since_1934 <- mex_tr[T >= as.Date("1934-01-01"), sum(regular)]
stopifnot(n_mex_since_1934 == 11)

# ---------------------------------------------------------------------------
# 4. Kaplan-Meier with delayed entry (regimes born before 1946 enter the risk set in 1946)
# ---------------------------------------------------------------------------
m <- g[in_main == 1]
km <- function(d, ext = FALSE, trunc = TRUE) {
  dur <- if (ext) d$duration_ext_yrs else d$duration_yrs
  ev  <- if (ext) d$event_ext else d$event
  if (trunc) survfit(Surv(d$entry_yrs, dur, ev) ~ 1) else survfit(Surv(dur, ev) ~ 1)
}
S_at <- function(fit, t) summary(fit, times = t, extend = TRUE)$surv
# Survival just before t: share of regimes still in power when they reach t years, without counting
# the regime whose own breakdown happens at t (Mexico's failure would otherwise count against itself).
EPS <- 1e-6
S_before <- function(fit, t) summary(fit, times = t - EPS, extend = TRUE)$surv
km_tab <- function(fit, sample) data.table(sample = sample, time = c(0, fit$time), surv = c(1, fit$surv),
                                           n_risk = c(NA, fit$n.risk), n_event = c(0, fit$n.event), n_censor = c(0, fit$n.censor))

fit_all   <- km(m)
fit_party <- km(m[party_any == 1])
fit_pstr  <- km(m[party_strict == 1])
fwrite(rbind(km_tab(fit_all, "all"), km_tab(fit_party, "party_any"), km_tab(fit_pstr, "party_strict"),
             km_tab(km(m, ext = TRUE), "all_vdem_ext"), km_tab(km(m[party_any == 1], ext = TRUE), "party_any_vdem_ext")),
       file.path(OUT, "km_survival_curves.csv"))

mex_dur_proj <- g[definition == "project", duration_yrs]
mex_dur_gwf  <- g[cowcode == 70 & definition == "gwf", duration_yrs]
# GWF-as-coded sample (Mexico 1915-2000) for the robustness percentile
mg <- g[definition == "gwf"]

key <- rbindlist(list(
  list("mexico_duration_project_yrs", mex_dur_proj, "PNR/PRM/PRI 1929-03-04 to 2000-07-02"),
  list("mexico_duration_gwf_yrs", mex_dur_gwf, "GWF Mexico 15-00: 1915-08-02 to 2000-07-02"),
  list("n_spells_main", nrow(m), "GWF spells in power at some point 1946-2010"),
  list("n_spells_party_any", nrow(m[party_any == 1]), "party-based incl. hybrids"),
  list("n_spells_party_strict", nrow(m[party_strict == 1]), "party-based only"),
  list("km_all_share_failed_by_mex_project", 1 - S_before(fit_all, mex_dur_proj), "1 - S(71.3-): share broken down before 71.3 yrs, delayed entry"),
  list("km_party_share_failed_by_mex_project", 1 - S_before(fit_party, mex_dur_proj), "party incl. hybrids"),
  list("km_partystrict_share_failed_by_mex_project", 1 - S_before(fit_pstr, mex_dur_proj), "party-based only"),
  list("km_all_median_yrs", unname(summary(fit_all)$table["median"]), "median survival, all"),
  list("km_party_median_yrs", unname(summary(fit_party)$table["median"]), "median survival, party incl. hybrids"),
  list("km_all_share_failed_by_mex_gwf", 1 - S_before(km(mg), mex_dur_gwf), "GWF-coded Mexico (84.9 yrs)"),
  list("km_party_share_failed_by_mex_gwf", 1 - S_before(km(mg[party_any == 1]), mex_dur_gwf), "GWF-coded Mexico"),
  list("km_all_share_failed_by_mex_project_notrunc", 1 - S_before(km(m, trunc = FALSE), mex_dur_proj), "no delayed entry: ignores that pre-1946 regimes are observed only from 1946 (overstates long-run survival)"),
  list("km_all_share_failed_by_mex_project_vdemext", 1 - S_before(km(m, ext = TRUE), mex_dur_proj), "censoring extended to 2025 with V-Dem RoW"),
  list("km_party_share_failed_by_mex_project_vdemext", 1 - S_before(km(m[party_any == 1], ext = TRUE), mex_dur_proj), "same, party incl. hybrids"),
  list("n_spells_longer_than_mex_project_by2010", nrow(m[duration_yrs > mex_dur_proj & definition != "project"]), "observed duration (incl. censored) > 71.3"),
  list("n_spells_longer_than_mex_project_by2025_vdemext", nrow(m[duration_ext_yrs > mex_dur_proj & definition != "project"]), "with V-Dem extension"),
  list("km_all_S_at_mex_project_lower95", summary(fit_all, times = mex_dur_proj - EPS, extend = TRUE)$lower, "95% CI of S(71.3)"),
  list("km_all_S_at_mex_project_upper95", summary(fit_all, times = mex_dur_proj - EPS, extend = TRUE)$upper, "95% CI of S(71.3)"),
  list("km_all_nrisk_at_mex_project", summary(fit_all, times = mex_dur_proj - EPS, extend = TRUE)$n.risk, "regimes at risk at 71.3 yrs"),
  list("n_spells_longer_than_mex_project_names_2010", NA, paste(m[duration_yrs > mex_dur_proj & definition != "project"][order(-duration_yrs), gwf_casename], collapse = "; ")),
  list("n_spells_longer_than_mex_project_names_2025", NA, paste(m[duration_ext_yrs > mex_dur_proj & definition != "project"][order(-duration_ext_yrs), gwf_casename], collapse = "; ")),
  list("n_spells_longer_than_mex_gwf_by2010", nrow(mg[duration_yrs > mex_dur_gwf & cowcode != 70]),
       paste(mg[duration_yrs > mex_dur_gwf & cowcode != 70][order(-duration_yrs), gwf_casename], collapse = "; ")),
  list("n_party_spells_longer_than_mex_project_by2010", nrow(m[party_any == 1 & duration_yrs > mex_dur_proj & definition != "project"]),
       paste(m[party_any == 1 & duration_yrs > mex_dur_proj & definition != "project", gwf_casename], collapse = "; ")),
  list("mexico_regular_successions_project", g[definition == "project", n_regular], "1929-2000 spell"),
  list("mexico_regular_successions_since_1934", n_mex_since_1934, "1934-2000"),
  list("mexico_regular_successions_gwf", g[cowcode == 70 & definition == "gwf", n_regular], "1915-2000 spell"),
  list("mexico_regular_successions_1946_2010", g[definition == "project", n_regular_1946_2010], "transitions dated 1946-2010")
))
setnames(key, c("quantity", "value", "note"))

# ---------------------------------------------------------------------------
# 5. Successions distribution: spells lasting >= 5 years
# ---------------------------------------------------------------------------
m5 <- m[duration_yrs >= 5]
others <- m5[definition != "project"]
mex_n  <- g[definition == "project", n_regular]
key <- rbind(key, rbindlist(list(
  list("n_spells_ge5yrs", nrow(m5), "main sample, duration >= 5 years"),
  list("max_regular_other_spells", max(others$n_regular), paste(others[n_regular == max(n_regular), gwf_casename], collapse = "; ")),
  list("n_spells_ge5_regular", nrow(m5[n_regular >= 5]), "incl. Mexico"),
  list("n_spells_ge8_regular", nrow(m5[n_regular >= 8]), "incl. Mexico"),
  list("n_spells_ge11_regular", nrow(m5[n_regular >= 11]), "incl. Mexico"),
  list("share_spells_zero_regular", mean(m5$n_regular == 0), "spells >= 5 yrs with no regular succession"),
  list("median_regular", median(m5$n_regular), "spells >= 5 yrs"),
  list("mexico_rank_regular", sum(others$n_regular > mex_n) + 1, "1 = most"),
  list("share_spells_below_mexico_regular", mean(others$n_regular < mex_n), "spells >= 5 yrs, excluding Mexico"),
  list("max_regular_other_spells_1946_2010", max(others$n_regular_1946_2010), paste(others[n_regular_1946_2010 == max(n_regular_1946_2010), gwf_casename], collapse = "; ")),
  list("mexico_rank_regular_1946_2010", sum(others$n_regular_1946_2010 > g[definition == "project", n_regular_1946_2010]) + 1, "window 1946-2010 only"),
  list("max_alive_nonviolent_other", max(others$n_alive_nonviolent), paste(others[n_alive_nonviolent == max(n_alive_nonviolent), gwf_casename], collapse = "; ")),
  list("max_regular_fate_ok_other", max(others$n_regular_fate_ok), paste(others[n_regular_fate_ok == max(n_regular_fate_ok), gwf_casename], collapse = "; ")),
  list("mexico_regular_fate_ok", g[definition == "project", n_regular_fate_ok], "regular and no exile/prison/death within a year"),
  list("mexico_non_irregular", g[definition == "project", n_non_irregular], "regular + ill health + natural death"),
  list("max_non_irregular_other", max(others$n_non_irregular), paste(others[n_non_irregular == max(n_non_irregular), gwf_casename], collapse = "; ")),
  list("mexico_regular_substantive", g[definition == "project", n_regular_substantive], "caretakers (<18 months) skipped"),
  list("max_regular_substantive_other", max(others$n_regular_substantive), paste(others[n_regular_substantive == max(n_regular_substantive), gwf_casename], collapse = "; "))
)), use.names = FALSE)

# ---------------------------------------------------------------------------
# 6. Svolik (2012) cross-check: ruling coalitions 1946-2008 (his do-file logic), count
#    within-coalition handovers whose predecessor exited by written/customary rules (cex == 1)
# ---------------------------------------------------------------------------
sv <- as.data.table(read_dta(file.path(B, "svolik_2012/extracted/leader/leadership change in dictatorships, 1946-2008.dta")))
sv[, `:=`(sd = as.Date(startdate), ed = as.Date(enddate))]
# Sorting as in the do-file: data are ordered by country and start date
setorder(sv, ccode, sd)
sv[, aspell_start := as.integer(is.na(consecutive) | consecutive == 0 | ccode != shift(ccode))]
sv[is.na(aspell_start), aspell_start := 1L]
sv[, aspell_id := cumsum(aspell_start)]
sv[, rc_new := as.integer(pol_aff != "regime" | aspell_start == 1)]
sv[, rc_id := cumsum(rc_new)]
sv[, nxt_same_rc := shift(rc_id, -1) == rc_id]
sv[is.na(nxt_same_rc), nxt_same_rc := FALSE]
svc <- sv[, .(country = cabb[1], rc_start = min(sd), rc_end = max(ed), first_leader = leader[1], last_leader = leader[.N],
              n_leaders = .N,
              n_handovers = sum(nxt_same_rc),
              n_handovers_cex1 = sum(nxt_same_rc & cex %in% 1),
              n_handovers_regular_exit = sum(nxt_same_rc & exit %in% c("term limit", "consensus", "resignation", "no contest"))),
          by = .(ccode, rc_id)]
svc[, duration_yrs := yrs(rc_end - rc_start)]
fwrite(svc, file.path(OUT, "svolik_ruling_coalitions_handovers.csv"))
sv5 <- svc[duration_yrs >= 5]
mex_sv <- sv5[ccode == 70]
stopifnot(nrow(mex_sv) == 1)
key <- rbind(key, rbindlist(list(
  list("svolik_mexico_handovers_cex1", mex_sv$n_handovers_cex1, paste(format(mex_sv$rc_start), format(mex_sv$rc_end))),
  list("svolik_n_coalitions_ge5yrs", nrow(sv5), "ruling coalitions lasting >= 5 years"),
  list("svolik_max_other_cex1", max(sv5[ccode != 70, n_handovers_cex1]),
       paste(sv5[ccode != 70 & n_handovers_cex1 == max(sv5[ccode != 70, n_handovers_cex1]), paste(country, year(rc_start))], collapse = "; ")),
  list("svolik_mexico_rank_cex1", sum(sv5[ccode != 70, n_handovers_cex1] > mex_sv$n_handovers_cex1) + 1, "1 = most"),
  list("svolik_n_coalitions_ge5_handovers_cex1", nrow(sv5[n_handovers_cex1 >= 5]), "incl. Mexico")
)), use.names = FALSE)

# ---------------------------------------------------------------------------
# 7. Write tables
# ---------------------------------------------------------------------------
out_cols <- c("spell_id", "cowcode", "gwf_country", "gwf_casename", "definition", "in_main", "gwf_regimetype",
              "party_any", "party_strict", "start", "end", "event", "duration_yrs", "entry_yrs",
              "end_ext", "event_ext", "duration_ext_yrs", "n_leaders", "archigos_covers_start",
              "n_transitions", "n_regular", "n_alive_nonviolent", "n_regular_fate_ok", "n_non_irregular",
              "n_regular_substantive", "n_regular_1946_2010",
              "n_regular_tol0", "n_regular_tol180", "first_transition", "last_transition")
setorder(g, -n_regular, -duration_yrs)
fwrite(g[, ..out_cols], file.path(OUT, "gwf_spells_benchmark.csv"))
fwrite(tr[, .(spell_id, casename = g$gwf_casename[match(spell_id, g$spell_id)], prev_leader, prev_start, prev_end,
              prev_exit, prev_exitcode, prev_fate, next_leader, transition_date = T, regular, alive_nonviol,
              regular_ok, in_1946_2010)][order(spell_id, transition_date)],
       file.path(OUT, "gwf_spell_transitions.csv"))
key[, value := signif(as.numeric(value), 4)]
fwrite(key, file.path(OUT, "key_numbers.csv"))
print(key, nrows = 200)

cat("\nTop spells by regular successions (>= 5 yrs):\n")
print(m5[order(-n_regular)][1:25, .(gwf_casename, gwf_regimetype, dur = round(duration_yrs, 1), event,
                                    n_transitions, n_regular, n_alive_nonviolent, n_regular_fate_ok,
                                    n_regular_1946_2010, n_regular_tol0, n_regular_tol180)])
cat("\nLongest spells (main sample):\n")
print(m[order(-duration_yrs)][1:20, .(gwf_casename, gwf_regimetype, dur = round(duration_yrs, 1), event,
                                      dur_ext = round(duration_ext_yrs, 1), event_ext)])
cat("\nSvolik top coalitions:\n")
print(sv5[order(-n_handovers_cex1)][1:15])

# ---------------------------------------------------------------------------
# 8. Comparator table: named comparators + every spell with >= 4 regular successions
# ---------------------------------------------------------------------------
COMPARATORS <- c("China 49-NA", "Soviet Union 17-91", "Russia 93-NA", "Ethiopia 91-NA", "Ethiopia 74-91",
                 "Vietnam 54-NA", "Tanzania 64-NA", "Singapore 65-NA", "Malaysia 57-NA", "Taiwan 49-00",
                 "Cuba 59-NA", "Korea North 48-NA", "Saudi Arabia 27-NA")
stopifnot(all(COMPARATORS %in% g$gwf_casename))
cmp <- g[in_main == 1 & (definition == "project" | gwf_casename %in% COMPARATORS | (n_regular >= 4 & duration_yrs >= 5))]
# Svolik ruling coalition with the largest overlap with each spell (same country)
ov <- svc[cmp[, .(spell_id, ccode = cowcode, S = start, E = end)], on = "ccode", allow.cartesian = TRUE, nomatch = 0]
ov[, overlap := as.numeric(pmin(rc_end, E) - pmax(rc_start, S))]
ov <- ov[overlap > 0][order(spell_id, -overlap)][, .SD[1], by = spell_id]
cmp[ov, on = "spell_id", `:=`(svolik_rc = paste(i.country, format(i.rc_start, "%Y"), format(i.rc_end, "%Y")),
                              svolik_handovers_cex1 = i.n_handovers_cex1)]
cmp[, km_share_failed_before := 1 - S_before(fit_all, duration_yrs)]
setorder(cmp, -n_regular, -duration_yrs)
fwrite(cmp[, .(gwf_casename, gwf_regimetype, start, end, still_in_power_2010 = 1L - event,
               duration_yrs = round(duration_yrs, 1), duration_ext_2025 = round(duration_ext_yrs, 1),
               km_share_failed_before = round(km_share_failed_before, 3),
               n_regular, n_regular_substantive, n_alive_nonviolent, n_non_irregular, n_regular_fate_ok,
               n_regular_1946_2010, n_transitions, svolik_rc, svolik_handovers_cex1)],
       file.path(OUT, "comparators.csv"))
cat("\nComparators:\n")
print(fread(file.path(OUT, "comparators.csv"))[, -c("start", "end")])
