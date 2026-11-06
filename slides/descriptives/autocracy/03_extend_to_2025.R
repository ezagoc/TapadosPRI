# 03_extend_to_2025.R -- extend the GWF regime spells and the leader successions from 2010 to 2025.
#
# Inputs
#   tables/gwf_spells_benchmark.csv (from 01_build_tables.R)
#   handcoded/regime_extension_2010_2025_coding.csv  one row per GWF regime in power on 31 Dec 2010: survived to
#       31 Dec 2025 or broke down (date, event, confidence, alternative coding, source). GWF's unit is the ruling
#       group: a leader change inside the same group is not a breakdown.
#   handcoded/leaders_2016_2025_coding.csv  effective leaders 2016-2025 for every regime still in power after
#       2015 (Archigos 4.1 ends 31 Dec 2015), Archigos-style exits (Regular / Natural Death / Irregular / ...).
#   Archigos 4.1; GWF (2018) leader-year file GWF.dta (headline succession count, 1946-2010);
#   V-Dem RoW v16 via OWID (check), Bjornskov-Rode v7.1 (check: coups, DD regime type).
# Outputs (<autocracies>/tables/)
#   regime_extension_2010_2025.csv   coding + V-Dem and Bjornskov-Rode checks
#   gwf_spells_benchmark_2025.csv    every spell with extended end and whole-life succession counts
#   succession_transitions_2025.csv  every within-spell Archigos leader change, with the flags behind each variant
#   gwf_standard_successions_2025.csv  headline count: GWF (2018) regular autocratic successions, whole life to 2025
#   km_survival_curves_2025.csv      Kaplan-Meier step functions on the extended spells
#   key_numbers.csv                  rows prefixed "y2025_" are replaced
# Figure: research/slides/pri_succession_slides/figures/autocracy_survival.{pdf,png} (deck version, to 2025)
#
# Run after 01 and 02: Rscript 03_extend_to_2025.R

suppressMessages({
  library(data.table)
  library(haven)
  library(survival)
  library(ggplot2)
  library(readxl)
})

cli <- commandArgs(FALSE)
HERE <- dirname(normalizePath(sub("^--file=", "", cli[grepl("^--file=", cli)][1])))   # this folder (handcoded/)
db_root <- Sys.getenv("TAPADOSPRI_DB_ROOT", file.path(path.expand("~"), "Dropbox", "TapadosPRI"))
B    <- file.path(Sys.getenv("TAPADOSPRI_DATA_DIR", file.path(db_root, "data")), "_web_discovery_2026-10-13", "autocracies")
OUT  <- file.path(B, "tables")
FIG  <- file.path(Sys.getenv("TAPADOSPRI_OUTPUT_DIR", file.path(db_root, "output")), "slides", "descriptives")
dir.create(FIG, recursive = TRUE, showWarnings = FALSE)

END25     <- as.Date("2025-12-31")
GWF_END   <- as.Date("2010-12-31")
GWF_BEGIN <- as.Date("1946-01-01")
ARCH_END  <- as.Date("2015-12-31")
TOL       <- 30      # days, as in 01
MIN_TENURE_YRS <- 1.5  # variant only (footnote): completed tenures shorter than 18 months are skipped
EPS       <- 1e-6
yrs <- function(d) as.numeric(d) / 365.25

# ---------------------------------------------------------------------------
# 1. Spells and the hand-coded extension
# ---------------------------------------------------------------------------
g <- fread(file.path(OUT, "gwf_spells_benchmark.csv"))
g <- g[in_main == 1 | definition == "gwf"]          # keep GWF's own Mexico row too (robustness)
for (v in c("start", "end")) set(g, j = v, value = as.Date(g[[v]]))

cod <- fread(file.path(HERE, "handcoded/regime_extension_2010_2025_coding.csv"), encoding = "UTF-8")
cod[, breakdown_date := as.Date(breakdown_date)]
ongoing <- g[event == 0 & definition == "gwf", gwf_casename]
stopifnot(setequal(cod$gwf_casename, ongoing), !anyDuplicated(cod$gwf_casename),
          all(cod$status_2025 %in% c("survived", "broke_down")),
          all(cod[status_2025 == "broke_down", breakdown_date > GWF_END & breakdown_date <= END25]),
          all(is.na(cod[status_2025 == "survived", breakdown_date])),
          all(cod$confidence %in% c("high", "medium", "low")))

g[, `:=`(end25 = end, event25 = event)]
g[cod, on = "gwf_casename", `:=`(end25 = fifelse(i.status_2025 == "broke_down", i.breakdown_date, END25),
                                  event25 = as.integer(i.status_2025 == "broke_down"))]
g[, duration25 := yrs(end25 - start)]

# ---------------------------------------------------------------------------
# 2. Checks against V-Dem RoW (v16, to 2025) and Bjornskov-Rode v7.1 (coups, DD regime type)
# ---------------------------------------------------------------------------
row <- fread(file.path(B, "vdem_row/political-regime.csv"))
name_map <- c("Cen African Rep" = "Central African Republic", "Congo-Brz" = "Congo",
              "Congo/Zaire" = "Democratic Republic of Congo", "Ivory Coast" = "Cote d'Ivoire",
              "Korea North" = "North Korea", "Swaziland" = "Eswatini")
cod[, gwf_country := g$gwf_country[match(gwf_casename, g$gwf_casename)]]
cod[, owid_entity := fifelse(gwf_country %in% names(name_map), name_map[gwf_country], gwf_country)]
cod[, iso3 := row$code[match(owid_entity, row$entity)]]
stopifnot(!anyNA(cod$iso3))
rowlab <- c("closed autocracy", "electoral autocracy", "electoral democracy", "liberal democracy")
row_at <- function(e, y) { v <- row[entity == e & year == y, regime_row_owid]; if (length(v)) rowlab[1 + v] else NA_character_ }
cod[, vdem_row_2010 := sapply(owid_entity, row_at, y = 2010)]
cod[, vdem_row_2025 := sapply(owid_entity, row_at, y = 2025)]
cod[, vdem_first_democratic_year := sapply(owid_entity, function(e) {
  r <- row[entity == e & year > 2010 & regime_row_owid >= 2]; if (nrow(r)) min(r$year) else NA_integer_ })]

br_file <- file.path(B, "bjornskov_rode_v7.1/Bjornskov-Rode-integrated-dataset-v7.1.xlsx")
brc <- as.data.table(read_excel(br_file, sheet = "Coups", .name_repair = "minimal"))
setnames(brc, make.names(names(brc)))
brc <- brc[year >= 2011 & year <= 2025 & Successful.coups > 0]
coup_txt <- brc[, {
  x <- c(if (!is.na(First.coup.success) && First.coup.success == 1) sprintf("%d-%02d", as.integer(First.coup.year), as.integer(First.coup.month)),
         if (!is.na(Second.coup.success) && Second.coup.success == 1) sprintf("%d-%02d", as.integer(Second.coup.year), as.integer(Second.coup.month)),
         if (!is.na(Third.coup.success) && Third.coup.success == 1) sprintf("%d-%02d", as.integer(Third.coup.year), as.integer(Third.coup.month)))
  .(coups = paste(x, collapse = "; "))
}, by = .(iso3 = country.isocode, year)][, .(br_successful_coups_2011_2025 = paste(coups[coups != ""], collapse = "; ")), by = iso3]
cod[coup_txt, on = "iso3", br_successful_coups_2011_2025 := i.br_successful_coups_2011_2025]
brr <- as.data.table(read_excel(br_file, sheet = "Regime characteristics", .name_repair = "minimal"))[, .(iso3 = `country isocode`, year, `DD category`)]
cod[, br_dd_category_2025 := brr[year == 2025][match(cod$iso3, iso3), `DD category`]]
cod[, age_at_end_2025 := round(g$duration25[match(gwf_casename, g$gwf_casename)], 1)]
fwrite(cod[, .(gwf_casename, status_2025, breakdown_date, breakdown_event, confidence, alternative_date, alternative_coding, source,
               age_at_end_2025, vdem_row_2010, vdem_row_2025, vdem_first_democratic_year,
               br_successful_coups_2011_2025, br_dd_category_2025)],
       file.path(OUT, "regime_extension_2010_2025.csv"))

# ---------------------------------------------------------------------------
# 3. Leaders to 2025: Archigos 4.1 + hand-coded 2016-2025 for regimes still in power after 2015
# ---------------------------------------------------------------------------
a <- as.data.table(read_dta(file.path(B, "archigos_v4.1/Archigos_4.1_stata14.dta"), encoding = "latin1"))
a <- a[, .(ccode, leadid, leader, ls = as.Date(startdate), le = as.Date(enddate), exit, fate = posttenurefate,
           src = "Archigos 4.1")]
hl <- fread(file.path(HERE, "handcoded/leaders_2016_2025_coding.csv"), encoding = "UTF-8")
hl[, `:=`(ls = as.Date(start), le = as.Date(end))]
stopifnot(all(hl$exit %in% c("Regular", "Natural Death", "Irregular", "Retired Due to Ill Health", "Still in Office")),
          all(hl$ls <= hl$le))
after15 <- g[definition == "gwf" & end25 > ARCH_END, gwf_casename]
stopifnot(setequal(unique(hl$gwf_casename), after15))
hl[, ccode := g$cowcode[match(gwf_casename, g$gwf_casename)]]
# each regime's first hand-coded leader must be the leader Archigos has in office on 31 Dec 2015
first_hl <- hl[order(ls)][, .SD[1], by = ccode]
arch_last <- a[ccode %in% hl$ccode & le == ARCH_END]
chk <- first_hl[arch_last, on = "ccode"]
stopifnot(nrow(arch_last) == uniqueN(hl$ccode), all(chk$ls == chk$i.ls))
hl[, leadid := fifelse(seq_len(.N) == 1L & ls == arch_last$ls[match(ccode, arch_last$ccode)],
                       arch_last$leadid[match(ccode, arch_last$ccode)], paste0("hand-", ccode, "-", seq_len(.N))), by = ccode]
# a person who returns keeps one id (none in 2016-2025, checked)
stopifnot(!anyDuplicated(hl[, .(ccode, leader)]))
L <- rbind(a[!(ccode %in% hl$ccode & le == ARCH_END)],
           hl[, .(ccode, leadid, leader, ls, le, exit, fate = NA_character_, src = paste("hand-coded:", source))])
setorder(L, ccode, ls, le)

# ---------------------------------------------------------------------------
# 4. Within-spell transitions over each regime's whole life (start to breakdown or 31 Dec 2025)
# ---------------------------------------------------------------------------
sp <- g[, .(spell_id, definition, ccode = cowcode, S = start, E = end25)]
transitions <- function(Ld) {
  Ld <- copy(Ld)
  Ld[, `:=`(next_leader = shift(leader, -1), next_start = shift(ls, -1)), by = ccode]
  p <- Ld[!is.na(next_leader), .(ccode, prev_leader = leader, prev_start = ls, prev_end = le, prev_exit = exit,
                                 prev_fate = fate, next_leader, T = next_start)]
  p <- p[sp, on = "ccode", allow.cartesian = TRUE, nomatch = 0][prev_end >= S + TOL & T > S + TOL & T < E - TOL]
  p
}
tr <- transitions(L)
tr[, regular       := as.integer(prev_exit == "Regular")]
tr[, non_irregular := as.integer(prev_exit %in% c("Regular", "Retired Due to Ill Health", "Natural Death"))]
tr[, alive_nonviol := as.integer(prev_exit %in% c("Regular", "Retired Due to Ill Health"))]

# Variant: completed tenures under 18 months skipped (leaders still in office in 2025 are kept), same person merged
Ls <- L[yrs(le - ls) >= MIN_TENURE_YRS | (exit == "Still in Office" & le == END25)]
setorder(Ls, ccode, ls)
Ls[, run := rleid(ccode, leadid)]
Ls <- Ls[, .(ccode = ccode[1], leadid = leadid[1], leader = leader[1], ls = min(ls), le = max(le), exit = exit[.N],
             fate = fate[.N]), by = run][, run := NULL]
trs <- transitions(Ls)
trs[, regular_18m := as.integer(prev_exit == "Regular")]

cnt <- tr[, .(n_transitions25 = .N, n_regular25 = sum(regular), n_non_irregular25 = sum(non_irregular),
              n_alive25 = sum(alive_nonviol)), by = spell_id]
cnt <- merge(cnt, trs[, .(n_regular_18m25 = sum(regular_18m)), by = spell_id], by = "spell_id", all = TRUE)
g <- cnt[g, on = "spell_id"]
for (v in c("n_transitions25", "n_regular25", "n_non_irregular25", "n_alive25", "n_regular_18m25"))
  set(g, which(is.na(g[[v]])), v, 0L)
# sanity: spells that ended by 2010 keep their 01 counts
stopifnot(g[end <= GWF_END & event == 1, all(n_regular25 == n_regular & n_regular_18m25 == n_regular_substantive)])

fwrite(rbind(tr[, .(spell_id, rule = "all transitions", prev_leader, prev_start, prev_end, prev_exit, next_leader,
                    transition_date = T, counted_regular = regular, counted_non_irregular = non_irregular)],
             trs[, .(spell_id, rule = "18-month variant", prev_leader, prev_start, prev_end, prev_exit, next_leader,
                     transition_date = T, counted_regular = regular_18m, counted_non_irregular = NA_integer_)]
             )[, casename := g$gwf_casename[match(spell_id, g$spell_id)]][order(casename, rule, transition_date)],
       file.path(OUT, "succession_transitions_2025.csv"))

# ---------------------------------------------------------------------------
# 4b. HEADLINE count: "regular autocratic successions" as defined and measured by Geddes, Wright & Frantz
#     (2018, How Dictatorships Work; codebook v1.0, pp. 2 and 5-6):
#     - leader = the de facto regime leader on 1 January; leaders not in power on any 1 January are omitted
#       (GWF codebook n. 2). This drops caretakers such as South Africa's acting PMs, and GWF's own file codes
#       Yugoslavia's post-Tito federal prime ministers, not the annual rotating Presidency chairs.
#     - regular succession = "the retirement, illness, or death of the original leader and his replacement by
#       someone who previously occupied the formal position of successor, or was selected by the retiring leader,
#       or was chosen by a group of regime insiders", including leaders who leave because of term limits.
#       Operationally: a leader exit inside a regime spell that does not end the regime, where the outgoing leader
#       was not removed irregularly (Archigos exit Regular, Retired Due to Ill Health or Natural Death).
#     1946-2010: GWF's own leader-year file (GWF.dta, v1.0, 2018); manner of exit from Archigos 4.1 (the leader
#     Archigos has in office on 1 January of the exit year). Before 1946 and after 2010: Archigos 4.1 and the
#     2016-2025 hand coding with the same 1-January rule (a leader still in office on 31 Dec 2025 was in office
#     on 1 Jan 2026). Iran after 2010 keeps GWF's de facto leader (Khamenei, in office throughout).
# ---------------------------------------------------------------------------
NONIRR <- c("Regular", "Retired Due to Ill Health", "Natural Death")
gl <- as.data.table(read_dta(file.path(B, "gwf_2018_leaders/extracted/data/1.0/GWF.dta")))
gl <- gl[, .(cowcode, year, case18 = gwf_casename, leaderid = gwf_leaderid, leadername = gwf_leadername,
             leader_fail = gwf_leader_fail, case_fail = gwf_case_fail)]
case_map <- c("Domincan Rep 30-62" = "Dominican Rep 30-62", "Costa Rica 1948-49" = "Costa Rica 48-49",
              "Paraguay 40-48" = "Paraguay 39-48", "Germany, East 49-90" = "Germany East 49-90",
              "Yugoslavia 44-90" = "Yugoslavia 45-90", "Serbia/Yugoslavia  91-00" = "Serbia 91-00",
              "Congo-Brz  97-NA" = "Congo-Brz 97-NA", "Burundi 1962-1966" = "Burundi 62-66",
              "Ethiopia 1889-1974" = "Ethiopia 89-74", "Namibia 1990-NA" = "Namibia 90-NA",
              "Madagascar 09-" = "Madagascar 09-NA", "South Yemen 67-90" = "Yemen South 67-90",
              "UAE 71-NA" = "United Arab Emirates 71-NA", "Oman 1741-NA" = "Oman 41-NA", "Nepal 1846-1951" = "Nepal 46-51",
              "South Vietnam 54-63" = "Vietnam South 54-63", "South Vietnam 63-75" = "Vietnam South 63-75")
gl[, gwf_casename := fifelse(case18 %in% names(case_map), case_map[case18], case18)]
stopifnot(setequal(unique(gl$gwf_casename), g[definition == "gwf", gwf_casename]))
# within-regime leader exits 1946-2010: the leader leaves in year Y and the regime does not fail in Y
gx <- gl[leader_fail == 1 & case_fail == 0]
# manner of exit: the Archigos leader in office on 1 January of the exit year
a_on <- function(cc, y) { d0 <- as.Date(sprintf("%d-01-01", y)); r <- a[ccode == cc & ls <= d0 & le >= d0]; r[order(-ls)][1] }
man <- rbindlist(lapply(seq_len(nrow(gx)), function(i) {
  r <- a_on(gx$cowcode[i], gx$year[i])
  data.table(arch_leader = r$leader, arch_exit = r$exit, arch_end_year = as.integer(format(r$le, "%Y")))
}))
gx <- cbind(gx, man)
gx[, regular_gwf := as.integer(arch_exit %in% NONIRR)]
gx[, timing_flag := as.integer(is.na(arch_end_year) | arch_end_year != year)]
# map exits to every spell of that case (Mexico: the GWF 1915 row and the project 1929 row)
win <- gx[g[, .(spell_id, gwf_casename = fifelse(definition == "project", "Mexico 15-00", gwf_casename), S = start, E = end25)],
          on = "gwf_casename", nomatch = 0][year >= as.integer(format(S, "%Y"))]
# leaders outside 1946-2010: Archigos + hand coding, 1-January rule (Iran after 2010: Khamenei throughout)
has_jan1 <- function(ls, le) as.integer(format(le, "%Y")) > as.integer(format(ls, "%Y")) | format(ls, "%m-%d") == "01-01"
Lg <- copy(L)
Lg <- Lg[!(ccode == 630 & ls > as.Date("2013-01-01"))]                       # drop Iranian presidents after 2010 ...
Lg[ccode == 630 & leader == "Hassan Rouhani", `:=`(leader = "Khamenei (GWF de facto leader)", ls = as.Date("1989-06-04"),
                                                   le = END25, exit = "Still in Office", leadid = "gwf-khamenei")]
Lg <- Lg[has_jan1(ls, le) | (exit == "Still in Office" & le == END25)]
setorder(Lg, ccode, ls)
Lg[, run := rleid(ccode, leadid)]
Lg <- Lg[, .(ccode = ccode[1], leadid = leadid[1], leader = leader[1], ls = min(ls), le = max(le), exit = exit[.N],
             fate = fate[.N]), by = run][, run := NULL]
tro <- transitions(Lg)[T < GWF_BEGIN | T > GWF_END]
tro[, regular_gwf := as.integer(prev_exit %in% NONIRR)]
std <- rbind(win[, .(spell_id, source = "GWF 2018 leader file", prev_leader = leadername, next_leader = NA_character_,
                     year, exit = arch_exit, regular_gwf, timing_flag)],
             tro[, .(spell_id, source = "Archigos/hand-coded, 1-Jan rule", prev_leader, next_leader,
                     year = as.integer(format(T, "%Y")), exit = prev_exit, regular_gwf, timing_flag = 0L)])
g[std[, .(n = sum(regular_gwf)), by = spell_id], on = "spell_id", n_gwf_regular25 := i.n]
g[is.na(n_gwf_regular25), n_gwf_regular25 := 0L]
g[std[, .(n = .N), by = spell_id], on = "spell_id", n_gwf_exits25 := i.n]
g[is.na(n_gwf_exits25), n_gwf_exits25 := 0L]
std[, casename := g$gwf_casename[match(spell_id, g$spell_id)]]
fwrite(std[order(casename, year)], file.path(OUT, "gwf_standard_successions_2025.csv"))
mex_std <- std[spell_id == g[definition == "project", spell_id]]
stopifnot(mex_std[, sum(regular_gwf)] == mex_std[, .N])

# ---------------------------------------------------------------------------
# 5. Kaplan-Meier with delayed entry on the extended spells
# ---------------------------------------------------------------------------
m <- g[in_main == 1]
km <- function(d) survfit(Surv(d$entry_yrs, d$duration25, d$event25) ~ 1)
S_before <- function(fit, t) summary(fit, times = t - EPS, extend = TRUE)
fit_all <- km(m); fit_party <- km(m[party_any == 1]); fit_pstr <- km(m[party_strict == 1])
km_tab <- function(fit, sample) data.table(sample = sample, time = c(0, fit$time), surv = c(1, fit$surv),
                                           n_risk = c(NA, fit$n.risk), n_event = c(0, fit$n.event), n_censor = c(0, fit$n.censor))
fwrite(rbind(km_tab(fit_all, "all"), km_tab(fit_party, "party_any"), km_tab(fit_pstr, "party_strict")),
       file.path(OUT, "km_survival_curves_2025.csv"))

# Robustness: every judgement call takes its alternative coding (all alternatives are breakdown dates)
cod[, alternative_date := as.Date(alternative_date)]
m_alt <- copy(m)
m_alt[cod[!is.na(alternative_date)], on = "gwf_casename", `:=`(end25 = i.alternative_date, event25 = 1L)]
m_alt[, duration25 := yrs(end25 - start)]

mex <- g[definition == "project"]
mex_dur <- mex$duration25
sa <- S_before(fit_all, mex_dur); sp_ <- S_before(fit_party, mex_dur); ss <- S_before(fit_pstr, mex_dur)
mg <- g[definition == "gwf"]                                   # GWF-coded Mexico (1915-2000)
mex_gwf_dur <- mg[cowcode == 70, duration25]
older <- m[definition != "project" & duration25 > mex_dur][order(-duration25)]
older[, label := paste0(gwf_casename, " (", round(duration25, 1), fifelse(event25 == 0, "+", ""), ")")]
viet <- g[gwf_casename == "Vietnam 54-NA"]
viet_pass <- viet$start + round(mex_dur * 365.25)

# ---------------------------------------------------------------------------
# 6. Successions ranking: every regime lasting >= 5 years, whole life to 2025
# ---------------------------------------------------------------------------
m5 <- m[duration25 >= 5]
oth <- m5[definition != "project"]
rank_of <- function(v) sum(oth[[v]] > mex[[v]]) + 1
top_of <- function(v, k = 8) { o <- oth[order(-get(v), -duration25)][1:k]
  paste(sprintf("%s %d", o$gwf_casename, o[[v]]), collapse = "; ") }
mex_tr  <- tr[spell_id == mex$spell_id]
mex_trs <- trs[spell_id == mex$spell_id]
dropped_18m <- fsetdiff(mex_tr[regular == 1, .(next_leader, T)], mex_trs[regular_18m == 1, .(next_leader, T)])
gm <- g[cowcode == 70 & definition == "gwf"]

key25 <- rbindlist(list(
  list("y2025_n_spells", nrow(m), "GWF spells in power 1946-2010, followed to 2025 (Mexico = project dating)"),
  list("y2025_n_ongoing_2010", nrow(cod), "spells in power on 31 Dec 2010"),
  list("y2025_n_survived_2025", cod[status_2025 == "survived", .N], "of those, same regime still in power 31 Dec 2025"),
  list("y2025_n_broke_down_2011_2025", cod[status_2025 == "broke_down", .N], "of those, broke down 2011-2025"),
  list("y2025_n_low_or_medium_confidence", cod[confidence != "high", .N], paste(cod[confidence != "high", gwf_casename], collapse = "; ")),
  list("y2025_km_all_share_failed_before_mex", 1 - sa$surv, "1 - S(71.33-), delayed entry, to 2025"),
  list("y2025_km_all_ci_low", 1 - sa$upper, "95% CI"), list("y2025_km_all_ci_high", 1 - sa$lower, "95% CI"),
  list("y2025_km_all_nrisk_at_mex", sa$n.risk, "regimes at risk just before 71.33 years"),
  list("y2025_km_party_share_failed_before_mex", 1 - sp_$surv, "party regimes incl. hybrids"),
  list("y2025_km_party_ci_low", 1 - sp_$upper, "95% CI"), list("y2025_km_party_ci_high", 1 - sp_$lower, "95% CI"),
  list("y2025_km_party_nrisk_at_mex", sp_$n.risk, "party regimes at risk just before 71.33 years"),
  list("y2025_km_partystrict_share_failed_before_mex", 1 - ss$surv, "party-based only"),
  list("y2025_km_all_share_failed_before_mex_altcoding", 1 - S_before(km(m_alt), mex_dur)$surv, "all judgement calls at their alternative coding"),
  list("y2025_km_party_share_failed_before_mex_altcoding", 1 - S_before(km(m_alt[party_any == 1]), mex_dur)$surv, "same, party regimes"),
  list("y2025_km_all_median_yrs", unname(summary(fit_all)$table["median"]), "median survival, all"),
  list("y2025_km_party_median_yrs", unname(summary(fit_party)$table["median"]), "median survival, party incl. hybrids"),
  list("y2025_km_all_share_failed_before_mex_gwf", 1 - S_before(km(mg), mex_gwf_dur)$surv, "GWF dating of Mexico, 84.9 years"),
  list("y2025_km_party_share_failed_before_mex_gwf", 1 - S_before(km(mg[party_any == 1]), mex_gwf_dur)$surv, "GWF dating, party regimes"),
  list("y2025_n_older_than_pri", nrow(older), paste(older$label, collapse = "; ")),
  list("y2025_n_party_older_than_pri", nrow(older[party_any == 1]), paste(older[party_any == 1, label], collapse = "; ")),
  list("y2025_n_older_than_pri_gwf_dating", nrow(mg[cowcode != 70 & duration25 > mex_gwf_dur]),
       paste(mg[cowcode != 70 & duration25 > mex_gwf_dur][order(-duration25), gwf_casename], collapse = "; ")),
  list("y2025_vietnam_passes_pri", NA, format(viet_pass)),
  list("y2025_n_spells_ge5yrs", nrow(m5), "whole-life basis, duration to breakdown or 2025"),
  list("y2025_HEADLINE_mex_gwf_regular", mex$n_gwf_regular25, "GWF (2018) regular autocratic successions, 1929-2000"),
  list("y2025_HEADLINE_mex_rank_gwf_regular", rank_of("n_gwf_regular25"), top_of("n_gwf_regular25", 10)),
  list("y2025_HEADLINE_n_ties_or_above", sum(oth$n_gwf_regular25 >= mex$n_gwf_regular25), "other regimes with at least Mexico's count"),
  list("y2025_HEADLINE_mex_gwf_regular_since1934", mex_std[year >= 1934, sum(regular_gwf)], "same rule, handovers 1934-2000"),
  list("y2025_HEADLINE_mex_gwf_regular_gwf1915", gm$n_gwf_regular25, "same rule, GWF dating 1915-2000"),
  list("y2025_HEADLINE_n_ge5", nrow(m5[n_gwf_regular25 >= 5]), "incl. Mexico"),
  list("y2025_HEADLINE_n_ge8", nrow(m5[n_gwf_regular25 >= 8]), "incl. Mexico"),
  list("y2025_HEADLINE_n_ge11", nrow(m5[n_gwf_regular25 >= 11]), "incl. Mexico"),
  list("y2025_HEADLINE_share_zero", mean(m5$n_gwf_regular25 == 0), "regimes >= 5 yrs with none"),
  list("y2025_HEADLINE_max_ongoing", max(m5[event25 == 0, n_gwf_regular25]),
       paste(m5[event25 == 0][order(-n_gwf_regular25)][1:5, sprintf("%s %d", gwf_casename, n_gwf_regular25)], collapse = "; ")),
  list("y2025_HEADLINE_window_exits_timing_flags", std[source == "GWF 2018 leader file", sum(timing_flag)],
       "GWF exits whose Archigos 1-Jan leader left in another year (manner taken from that leader)"),
  list("y2025_mex_regular", mex$n_regular25, "Archigos Regular exits, 1929-2000"),
  list("y2025_mex_rank_regular", rank_of("n_regular25"), top_of("n_regular25")),
  list("y2025_mex_non_irregular", mex$n_non_irregular25, "Regular + natural death + ill health"),
  list("y2025_mex_rank_non_irregular", rank_of("n_non_irregular25"), top_of("n_non_irregular25")),
  list("y2025_mex_alive", mex$n_alive25, "Regular + ill health"),
  list("y2025_mex_rank_alive", rank_of("n_alive25"), top_of("n_alive25")),
  list("y2025_mex_regular_18m", mex$n_regular_18m25, "variant: completed tenures < 18 months skipped"),
  list("y2025_mex_rank_regular_18m", rank_of("n_regular_18m25"), top_of("n_regular_18m25")),
  list("y2025_mex_handover_dropped_18m", nrow(dropped_18m), paste(dropped_18m$next_leader, format(dropped_18m$T), collapse = "; ")),
  list("y2025_mex_regular_since1934", mex_tr[T >= as.Date("1934-01-01"), sum(regular)], "Archigos Regular"),
  list("y2025_mex_regular_18m_since1934", mex_trs[T >= as.Date("1934-01-01"), sum(regular_18m)], "18-month variant"),
  list("y2025_mex_gwf1915_regular", gm$n_regular25, "GWF dating 1915-2000"),
  list("y2025_mex_gwf1915_regular_18m", gm$n_regular_18m25, "GWF dating, 18-month variant"),
  list("y2025_mex_gwf1915_non_irregular", gm$n_non_irregular25, "GWF dating"),
  list("y2025_n_ge5_regular", nrow(m5[n_regular25 >= 5]), "incl. Mexico"),
  list("y2025_n_ge8_regular", nrow(m5[n_regular25 >= 8]), "incl. Mexico"),
  list("y2025_n_ge11_regular", nrow(m5[n_regular25 >= 11]), "incl. Mexico"),
  list("y2025_share_zero_regular", mean(m5$n_regular25 == 0), "regimes >= 5 yrs with no regular succession"),
  list("y2025_n_ge5_regular_18m", nrow(m5[n_regular_18m25 >= 5]), "incl. Mexico"),
  list("y2025_n_ge8_regular_18m", nrow(m5[n_regular_18m25 >= 8]), "incl. Mexico"),
  list("y2025_n_ge11_regular_18m", nrow(m5[n_regular_18m25 >= 11]), "incl. Mexico"),
  list("y2025_max_regular_ongoing", max(m5[event25 == 0, n_regular25]),
       paste(m5[event25 == 0 & n_regular25 == max(m5[event25 == 0, n_regular25]), gwf_casename], collapse = "; ")),
  list("y2025_max_regular_18m_ongoing", max(m5[event25 == 0, n_regular_18m25]),
       paste(m5[event25 == 0 & n_regular_18m25 == max(m5[event25 == 0, n_regular_18m25]), gwf_casename], collapse = "; "))
))
setnames(key25, c("quantity", "value", "note"))
key25[, value := signif(as.numeric(value), 4)]
key <- fread(file.path(OUT, "key_numbers.csv"))[!startsWith(quantity, "y2025_")]
fwrite(rbind(key, key25), file.path(OUT, "key_numbers.csv"))
print(key25, nrows = 200)

out_cols <- c("spell_id", "cowcode", "gwf_country", "gwf_casename", "definition", "in_main", "gwf_regimetype", "party_any",
              "start", "end", "event", "end25", "event25", "duration25", "entry_yrs",
              "n_gwf_exits25", "n_gwf_regular25", "n_transitions25", "n_regular25", "n_non_irregular25", "n_alive25", "n_regular_18m25",
              "n_regular", "n_regular_substantive")
setorder(g, -n_regular25, -duration25)
fwrite(g[, ..out_cols], file.path(OUT, "gwf_spells_benchmark_2025.csv"))
cat("\nTop regimes (>= 5 yrs), whole life to 2025:\n")
print(m5[order(-n_gwf_regular25, -n_regular25)][1:20, .(gwf_casename, dur = round(duration25, 1), event25, n_gwf_regular25, n_regular25,
                                                         n_regular_18m25, n_non_irregular25, n_alive25)])
cat("\nTop by non-irregular:\n")
print(m5[order(-n_non_irregular25)][1:12, .(gwf_casename, dur = round(duration25, 1), n_non_irregular25, n_regular25)])

# ---------------------------------------------------------------------------
# 7. Figure: survival to 2025 (same style as 02)
# ---------------------------------------------------------------------------
ACC <- "#940034"; INK <- "#18181b"; Z3 <- "#d4d4d8"; Z4 <- "#a1a1aa"; Z5 <- "#71717a"; Z6 <- "#52525b"
FONT <- "Helvetica"; W <- 10; H <- 5.2; ANN <- 4.1
theme_slide <- function() {
  theme_classic(base_size = 15, base_family = FONT) +
    theme(plot.background = element_rect(fill = "white", colour = NA),
          panel.background = element_rect(fill = "white", colour = NA),
          axis.line = element_line(colour = Z4, linewidth = 0.35), axis.ticks = element_line(colour = Z4, linewidth = 0.35),
          axis.ticks.length = unit(3, "pt"), axis.text = element_text(colour = Z6, size = 12.5),
          axis.title = element_text(colour = INK, size = 14),
          axis.title.x = element_text(margin = margin(t = 8)), axis.title.y = element_text(margin = margin(r = 8)),
          plot.caption = element_text(colour = Z5, size = 10, hjust = 0, margin = margin(t = 10)),
          plot.caption.position = "plot", legend.position = "none", plot.margin = margin(12, 16, 8, 10))
}
pdf_dev <- function(filename, width, height, ...)
  grDevices::pdf(filename, width = width, height = height, family = FONT, encoding = "WinAnsi.enc", useDingbats = FALSE)
save_both <- function(p, name) {
  f <- file.path(FIG, paste0(name, ".pdf"))
  ggsave(f, p, width = W, height = H, device = pdf_dev)
  embedFonts(f, options = "-dPDFSETTINGS=/prepress")
  ggsave(file.path(FIG, paste0(name, ".png")), p, width = W, height = H, dpi = 300, device = ragg::agg_png, bg = "white")
}

XMAX <- 100
curves <- rbind(km_tab(fit_all, "all"), km_tab(fit_pstr, "party_any"))  # figure: party-based regimes only (GWF typology), hybrids excluded
S_left <- function(s, t) { d <- curves[sample == s & time < t]; d[.N, surv] }
last_t <- curves[, .(tl = max(time)), by = sample]
ext <- curves[, {
  d <- .SD[time <= XMAX]
  tend <- min(XMAX, max(m[if (.BY$sample == "all") TRUE else party_strict == 1, duration25]))
  rbind(d, data.table(time = tend, surv = d$surv[nrow(d)]), fill = TRUE)
}, by = sample]
ext[, colour := fifelse(sample == "all", Z4, Z6)]
y_mex <- S_left("all", mex_dur)
pct_all <- round(100 * (1 - sa$surv)); pct_party <- round(100 * (1 - ss$surv))

lab <- data.table(case = c("Taiwan 49-00", "Cuba 59-NA", "Venezuela 05-NA", "Vietnam 54-NA", "Soviet Union 17-91", "China 49-NA",
                           "Korea North 48-NA", "Jordan 46-NA", "Saudi Arabia 27-NA"),
                  label = c("Taiwan (KMT)", "Cuba", "Venezuela", "Vietnam", "USSR", "China", "North Korea", "Jordan", "Saudi Arabia"))
lab[, `:=`(x = g$duration25[match(case, g$gwf_casename)], open = g$event25[match(case, g$gwf_casename)] == 0)]
lab[, y := sapply(x, function(t) S_left("all", t + 1e-9))]
lab[, txt := paste0(label, ", ", floor(x + 1e-9), fifelse(open, "+", ""))]
# label positions: Taiwan below the curve; Cuba above its point; the 74-80-year cluster in a column to the right
# of Mexico's marker with nested (non-crossing) leader lines; Saudi Arabia next to its point
lab[, `:=`(tx = x, ty = y - 0.035, hj = 0.5, vj = 1, lx = x, ly = y - 0.012, lyend = y - 0.03)]
lab[label == "Venezuela", `:=`(tx = x - 1, ty = y - 0.02, hj = 1, vj = 1, ly = NA, lyend = NA)]
col_y <- c(Vietnam = 0.32, USSR = 0.265, China = 0.21, "North Korea" = 0.155, Jordan = 0.10)
lab[label %in% names(col_y), `:=`(tx = 84, ty = col_y[label], hj = 0, vj = 0.5, lx = 83.6, ly = col_y[label], lyend = NA)]
lab[label == "Saudi Arabia", `:=`(tx = x + 0.6, ty = y + 0.03, hj = 1, vj = 0, lyend = NA, ly = NA)]
viet_note <- sprintf("Vietnam passed it in %s", format(viet_pass, "%B %Y"))

p <- ggplot() +
  geom_step(data = ext, aes(time, surv, group = sample, colour = colour), linewidth = 0.75, direction = "hv") +
  scale_colour_identity() +
  annotate("text", x = 7, y = 0.165, hjust = 0, vjust = 1, family = FONT, size = ANN, colour = Z5,
           label = sprintf("All autocracies (n = %d), median %d years", nrow(m), round(summary(fit_all)$table["median"]))) +
  annotate("text", x = 22, y = S_left("party_any", 22) + 0.05, hjust = 0, vjust = 0, family = FONT, size = ANN, colour = Z6,
           label = sprintf("Party regimes (n = %d), median %d years", nrow(m[party_strict == 1]), round(summary(fit_pstr)$table["median"]))) +
  geom_segment(data = lab[label %in% c("Taiwan (KMT)", "Cuba")], aes(x = x, xend = x, y = ly, yend = lyend),
               colour = Z3, linewidth = 0.3) +
  geom_segment(data = lab[label %in% names(col_y)], aes(x = lx, xend = x, y = ly, yend = y + 0.01),
               colour = Z3, linewidth = 0.3) +
  geom_point(data = lab, aes(x, y), colour = Z5, size = 1.6) +
  geom_text(data = lab, aes(tx, ty, label = txt, hjust = hj, vjust = vj), family = FONT, size = ANN - 0.5, colour = Z5) +
  annotate("segment", x = mex_dur, xend = mex_dur, y = y_mex + 0.02, yend = 0.50, colour = ACC, linewidth = 0.45) +
  annotate("point", x = mex_dur, y = y_mex, colour = ACC, size = 3) +
  annotate("text", x = mex_dur + 1.2, y = 0.50, hjust = 0, vjust = 1, family = FONT, size = ANN - 0.3, colour = ACC,
           fontface = "bold", label = sprintf("Mexico (PRI), 1929–2000: %d years", floor(mex_dur))) +
  annotate("text", x = mex_dur + 1.2, y = 0.455, hjust = 0, vjust = 1, family = FONT, size = ANN - 0.6, colour = ACC, lineheight = 1.05,
           label = sprintf("%d%% of autocracies broke down sooner\n(%d%% of party regimes)", pct_all, pct_party)) +
  scale_x_continuous("Years in power", limits = c(0, XMAX), breaks = seq(0, XMAX, 10), expand = expansion(mult = c(0, 0.01))) +
  scale_y_continuous("Share of regimes still in power", limits = c(0, 1), breaks = seq(0, 1, 0.25),
                     labels = function(b) paste0(round(100 * b), "%"), expand = expansion(mult = c(0, 0.02))) +
  labs(caption = "Source: Geddes, Wright & Frantz (2014), extended to 2025. + = still in power in 2025.") +
  theme_slide()
save_both(p, "autocracy_survival")
cat("Figure written:", file.path(FIG, "autocracy_survival.{pdf,png}"), "\n")
