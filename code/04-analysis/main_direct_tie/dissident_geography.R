# MAIN_SPEC section 17: can a dissident's electoral damage by state be measured before the break?
# Measures of an electoral base: own career (birth, own posts), the share of the state's political elite tied to him
# (elected, party, state-government and military posts located in the state in e-6..e-1; any tie existing by e-1,
# stated ties included), and an allied governor. Evaluated by fit within election, leave-one-dissident-out prediction,
# and placebo aspirants of the same succession.
#   Rscript code/04-analysis/main_direct_tie/dissident_geography.R
suppressPackageStartupMessages(library(data.table))
db_root <- Sys.getenv("TAPADOSPRI_DB_ROOT", file.path(path.expand("~"), "Dropbox", "TapadosPRI"))
data_dir <- Sys.getenv("TAPADOSPRI_DATA_DIR", file.path(db_root, "data"))
out_dir <- Sys.getenv("TAPADOS_MAIN_OUTPUT_DIR", file.path(db_root, "output", "main_direct_tie"))
read_data <- function(...) fread(file.path(data_dir, ...), na.strings = c("", "NA"))

dissidents <- data.table(election = c(1940L, 1946L, 1952L, 1988L), pid = c(158L, 2024L, 1298L, 452L),
                         name = c("Almazan", "Padilla", "Henriquez", "Cardenas"))

# Votes: dissident / sum of all candidates (1940: 31 entities in the printed table).
rr <- read_data("electoralData", "raw", "ramirez_rancano", "ramirez_rancano_presidential_by_state_1917_1970.csv")
cc <- read_data("electoralData", "crosscheck", "presidential_by_state_crosscheck.csv")
v40 <- cc[year == 1940 & source == "DD" & measure %in% c("winner", "Almazan", "Sanchez Tapia"),
          .(election = 1940L, total = sum(votes), dissident = sum(votes[measure == "Almazan"])), by = .(edon, state)]
v4652 <- rr[election_year %in% c(1946L, 1952L) & edon %between% c(1L, 32L) & !grepl("TOTAL", candidate),
            .(total = sum(votes, na.rm = TRUE), dissident = sum(votes[candidate %in% c("Padilla", "Henriquez")], na.rm = TRUE)),
            by = .(election = election_year, edon, state)]
v88 <- cc[year == 1988 & source == "DICT" & measure %in% c("winner", "PAN", "FDN (Cardenas)", "PDM", "PRT"),
          .(election = 1988L, total = sum(votes), dissident = sum(votes[measure == "FDN (Cardenas)"])), by = .(edon, state)]
votes <- rbind(v40, v4652, v88, use.names = TRUE)
votes[, state := fifelse(state == "Distrito Federal", "Federal District", state)]
votes[, `:=`(y = dissident / total)]
votes[, y_dev := y - mean(y), by = election]          # the national level of each dissident is not what we predict

# The state's political elite in e-6..e-1: elected office, state/local party posts, state-government posts outside the
# Federal District, military posts with a state.
rd <- function(f) read_data("clean_positions", paste0(f, ".csv"))
gp <- rd("govt_positions"); pp <- rd("public_positions"); qp <- rd("party_positions"); mp <- rd("military_positions")
loc <- function(d) d[, .(pid = person_id, st = fifelse(is.na(state), work_state, state), y0 = year_start,
                         y1 = fifelse(is.na(year_end), year_start, year_end), title = if ("position_title" %in% names(d)) position_title else NA_character_)]
elite <- rbind(loc(pp), loc(qp[party_level %in% c("state", "local")]), loc(gp[state != "Federal District"]), loc(mp), fill = TRUE)
elite <- elite[!is.na(st) & !is.na(y0) & st %in% votes$state]
own <- rbind(loc(pp), loc(qp), loc(gp), loc(mp), fill = TRUE)[!is.na(st) & !is.na(y0) & st %in% votes$state]
nodes <- read_data("networks", "network_nodes.csv")
edges <- read_data("networks", "network_edges.csv")
long <- rbind(edges[, .(ego = person_a, alter = person_b, year_start)], edges[, .(ego = person_b, alter = person_a, year_start)])

measures <- function(p, e) {
  tied <- long[ego == p & (is.na(year_start) | year_start <= e - 1), unique(alter)]
  w <- unique(elite[y0 <= e - 1 & y1 >= e - 6, .(pid, st, governor = title %in% "Governor")])
  s <- w[pid != p, .(elite_n = uniqueN(pid), tied_n = uniqueN(pid[pid %in% tied]),
                     ally_governor = as.integer(any(governor & pid %in% tied))), by = .(state = st)]
  base <- unique(c(nodes[person_id == p, birth_state], own[pid == p & y0 < e, st]))
  out <- data.table(state = unique(votes$state))
  out <- merge(out, s, by = "state", all.x = TRUE)
  for (v in c("elite_n", "tied_n", "ally_governor")) set(out, which(is.na(out[[v]])), v, 0)
  out[, `:=`(election = e, pid = p, L = fifelse(elite_n > 0, tied_n / elite_n, 0), B = as.integer(state %in% base))]
  out
}

D <- merge(votes, rbindlist(lapply(seq_len(nrow(dissidents)), function(i) measures(dissidents$pid[i], dissidents$election[i]))),
           by = c("election", "state"))
D[dissidents, dissident_name := i.name, on = "election"]

# (1) Within each election: does each measure line up with the vote?
within <- D[, .(states = .N, tied_elite = sum(tied_n), states_with_ties = sum(tied_n > 0), allied_governors = sum(ally_governor),
                base_states = sum(B), rho_L = cor(y, L, method = "spearman"),
                y_base = mean(y[B == 1]), y_nonbase = mean(y[B == 0]),
                y_tied = if (any(L > 0)) mean(y[L > 0]) else NA_real_, y_untied = mean(y[L == 0])),
            by = .(election, dissident_name)]

# (2) Pooled, within election: y deviation on the three measures.
fit_all <- lm(y_dev ~ B + L + ally_governor, data = D)
fit_fe <- lm(y ~ B + L + ally_governor + factor(election) + factor(state), data = D)

# (3) Leave one dissident out: fit on three, predict the fourth's state pattern.
loo <- rbindlist(lapply(dissidents$election, function(e) {
  tr <- D[election != e]; te <- D[election == e]
  m_base <- lm(y_dev ~ B, data = tr); m_full <- lm(y_dev ~ B + L + ally_governor, data = tr)
  data.table(held_out = e, cor_base = cor(te$y_dev, predict(m_base, te)), cor_full = cor(te$y_dev, predict(m_full, te)),
             rmse_none = sqrt(mean(te$y_dev^2)), rmse_base = sqrt(mean((te$y_dev - predict(m_base, te))^2)),
             rmse_full = sqrt(mean((te$y_dev - predict(m_full, te))^2)))
}))

# (4) Placebo aspirants: is the dissident's own base and elite share a better predictor of his vote than another
# aspirant's? Statistic: R2 of y_dev on (B, L) within the election.
asp <- read_data("candidates", "corcholatas_matched.csv")
r2 <- function(d) summary(lm(y_dev ~ B + L, data = d))$r.squared
plac <- rbindlist(lapply(seq_len(nrow(dissidents)), function(i) {
  e <- dissidents$election[i]; p <- dissidents$pid[i]
  others <- unique(asp[election_year == e & !is.na(person_id) & person_id != p, .(pid = as.integer(person_id), role)], by = "pid")
  own_r2 <- r2(D[election == e])
  pr <- others[, .(r2 = r2(merge(votes[election == e], measures(pid, e), by = c("election", "state")))), by = .(pid, role)]
  data.table(election = e, dissident = dissidents$name[i], r2_dissident = own_r2, n_placebo = nrow(pr),
             best_placebo = pr[which.max(r2), paste(pid, role)], max_placebo_r2 = max(pr$r2),
             p_placebo = (1 + sum(pr$r2 >= own_r2)) / (1 + nrow(pr)))
}))

fwrite(D, file.path(out_dir, "dissident_geography_states.csv"))
fwrite(within, file.path(out_dir, "dissident_geography_within.csv"))
fwrite(loo, file.path(out_dir, "dissident_geography_loo.csv"))
fwrite(plac, file.path(out_dir, "dissident_geography_placebos.csv"))
unlink(file.path(out_dir, c("dissident_geography_by_election.csv", "dissident_geography_pooled.csv")))
print(within, digits = 3); print(summary(fit_all)$coefficients, digits = 3)
print(summary(fit_fe)$coefficients[c("B", "L", "ally_governor"), ], digits = 3)
print(loo, digits = 3); print(plac, digits = 3)
