# Transition between successions: a politician's group at succession e (D designee's follower, P a loser's follower,
# M tied to several aspirants, N unaligned) against his group at the next succession e+6, from the exported pools.
# Leaving the pool: died before e+6, or alive without a ranked post in e+1..e+4 (the pool rule at e+6), over 75, or
# himself an aspirant. Ties to the next slate are dated by e+4, so they are predetermined with respect to the designation
# in e+5, as in the main design.
#   Rscript code/04-analysis/main_direct_tie/transitions.R   (after export_structural_inputs.R)
suppressPackageStartupMessages(library(data.table))
db_root <- Sys.getenv("TAPADOSPRI_DB_ROOT", file.path(path.expand("~"), "Dropbox", "TapadosPRI"))
out_dir <- Sys.getenv("TAPADOS_MAIN_OUTPUT_DIR", file.path(db_root, "output", "main_direct_tie"))
pool <- fread(file.path(db_root, "data", "structural", "pool.csv"))
set.seed(20102026L)

nxt <- pool[, .(election = election - 6L, pid, next_group = group, next_rung = R_m2)]
tr <- merge(pool[election <= 1982L, .(election, pid, group, patron_kept, age, death_year, R_m2, R_p4)], nxt,
            by = c("election", "pid"), all.x = TRUE)
tr[is.na(next_group), next_group := fifelse(!is.na(death_year) & death_year < election + 6L, "out: died", "out: alive")]
tr[, group := factor(group, c("D", "P", "M", "N"))]
tr[, next_group := factor(next_group, c("D", "P", "M", "N", "out: died", "out: alive"))]
# Tied to the next designee at all (exclusive or not: 56% of the designee's followers are tied to several aspirants at
# e+6, because the next slate comes from the sitting president's cabinet), and tied to any aspirant of the next slate.
ties <- fread(file.path(db_root, "data", "structural", "ties.csv"))
asp <- fread(file.path(db_root, "data", "candidates", "corcholatas_matched.csv"))[in_main_slate == 1L & !is.na(person_id)]
designee <- asp[role == "winner", .(election = election_year, d = person_id)]
nd <- merge(ties, designee, by = "election")[j == d, .(election = election - 6L, pid = i, tied_next_designee = 1L)]
na <- merge(ties, asp[, .(election = election_year, j = person_id)], by = c("election", "j"))[
  , .(tied_next_aspirant = 1L), by = .(election = election - 6L, pid = i)]
tr <- merge(merge(tr, unique(nd), by = c("election", "pid"), all.x = TRUE), na, by = c("election", "pid"), all.x = TRUE)
tr[is.na(tied_next_designee), tied_next_designee := 0L][is.na(tied_next_aspirant), tied_next_aspirant := 0L]

# (1) Pooled matrix: every row sums to one; and among those still in the pool at e+6.
m_all <- dcast(tr[, .N, by = .(group, next_group)][, share := N / sum(N), by = group], group ~ next_group, value.var = "share", fill = 0)
m_in <- dcast(tr[!grepl("out", next_group), .N, by = .(group, next_group)][, share := N / sum(N), by = group],
              group ~ next_group, value.var = "share", fill = 0)
n_rows <- tr[, .(n = .N, in_pool_next = sum(!grepl("out", next_group))), by = group]

# (2)-(5) for two outcomes among those in the pool at e+6: tied to the next designee at all (main), and his exclusive
# follower (the pool's D group at e+6).
inn <- tr[!grepl("out", next_group)]
inn[, excl_next_designee := as.integer(next_group == "D")]
signs_of <- function(d, y) d[, .(pD = mean(get(y)[group == "D"]), pP = mean(get(y)[group == "P"]),
                                 pM = mean(get(y)[group == "M"]), pN = mean(get(y)[group == "N"])), by = election]
contrast <- function(d, y) signs_of(d, y)[, .(D = mean(pD), P = mean(pP), M = mean(pM), N = mean(pN),
                                              D_minus_P = mean(pD - pP), P_minus_N = mean(pP - pN))]
es <- unique(inn$election)
out <- list()
for (y in c("tied_next_designee", "excl_next_designee", "tied_next_aspirant")) {
  est <- contrast(inn, y)
  boot <- rbindlist(lapply(1:2000, function(b) {
    s <- sample(es, replace = TRUE)
    contrast(rbindlist(lapply(seq_along(s), function(k) inn[election == s[k]][, election := k])), y)
  }))
  ci <- boot[, lapply(.SD, quantile, c(0.025, 0.975, 0.05, 0.95), na.rm = TRUE)]
  sg <- signs_of(inn, y)
  lpm <- lm(as.formula(paste(y, "~ group + factor(pmin(R_m2, 9L)) + age + factor(election)")), data = inn)
  cf <- summary(lpm)$coefficients
  out[[y]] <- rbind(cbind(outcome = y, stat = "estimate (equal weight per transition)", est),
                    cbind(outcome = y, stat = c("ci_2.5", "ci_97.5", "ci_5", "ci_95"), ci))
  cat("\n==", y, "\n"); print(sg, digits = 3); print(out[[y]], digits = 3)
  cat("transitions with D > P:", sg[, sum(pD > pP)], "of", nrow(sg), "| P > N:", sg[, sum(pP > pN)], "of", nrow(sg), "\n")
  cat("person-weighted LPM, transition FE, rung at e-2, age (reference D):\n"); print(cf[c("groupP", "groupM", "groupN"), ], digits = 3)
  fwrite(sg, file.path(out_dir, paste0("transitions_by_succession_", y, ".csv")))
}
fwrite(rbindlist(out), file.path(out_dir, "transitions_contrasts.csv"))
cat("\nLosers' followers by whether the patron kept a top chair after e:\n")
print(inn[group == "P", .(n = .N, tied_next_designee = mean(tied_next_designee), tied_next_aspirant = mean(tied_next_aspirant)),
          by = patron_kept], digits = 3)

fwrite(m_all, file.path(out_dir, "transitions_matrix_all.csv")); fwrite(m_in, file.path(out_dir, "transitions_matrix_in_pool.csv"))
print(n_rows); print(m_all, digits = 3); print(m_in, digits = 3)

# ---------------------------------------------------------------------------------------------------------------------
# (6) Sign tests across the 8 transitions (one-sided binomial), next to the bootstrap.
sign_p <- function(k, n) sum(dbinom(k:n, n, 0.5))
sg <- signs_of(inn, "tied_next_designee"); sa <- signs_of(inn, "tied_next_aspirant")
signs <- data.table(outcome = c("tied_next_designee", "tied_next_designee", "tied_next_aspirant", "tied_next_aspirant"),
                    contrast = c("P > N", "D > P", "P > N", "D > P"),
                    k = c(sg[, sum(pP > pN)], sg[, sum(pD > pP)], sa[, sum(pP > pN)], sa[, sum(pD > pP)]), n = nrow(sg))
signs[, p_one_sided := mapply(sign_p, k, n)]
cat("\n== sign tests\n"); print(signs, digits = 3)

# (7) Random-heir benchmark: for each transition and group, P(tied to contender c) averaged over every contender c of
# the next main slate, against P(tied to the actual next designee).
slate_next <- asp[, .(election = election_year - 6L, c = person_id, is_designee = role == "winner")]
tc <- merge(ties[, .(election = election - 6L, pid = i, c = j)], slate_next, by = c("election", "c"))
cand_tie <- CJ_by <- merge(inn[, .(election, pid, group)], slate_next, by = "election", allow.cartesian = TRUE)
cand_tie[unique(tc[, .(election, pid, c)]), tied := 1L, on = .(election, pid, c)][is.na(tied), tied := 0L]
bench <- cand_tie[, .(p = mean(tied)), by = .(election, group, c, is_designee)][
  , .(actual = p[is_designee], benchmark = mean(p), contenders = .N), by = .(election, group)]
bench_eq <- bench[, .(actual = mean(actual), benchmark = mean(benchmark), ratio = mean(actual) / mean(benchmark),
                      transitions_actual_above = sum(actual > benchmark), n = .N), by = group][order(group)]
bench_eq[, p_one_sided := mapply(sign_p, transitions_actual_above, n)]
cat("\n== random-heir benchmark (equal weight per transition)\n"); print(bench_eq, digits = 3)

# (8) Conditioning on the post held in e+2..e+4 (the premium): highest rung in those years.
pool_post <- pool[, .(election, pid, post_e24 = pmax(R_p2, R_p3, R_p4))]
inn[pool_post, post_e24 := i.post_e24, on = .(election, pid)]
inn[, post_bin := cut(post_e24, c(-1, 0, 4, 6, 8, 99), labels = c("none", "1-4", "5-6", "7-8", "9+"))]
cells <- dcast(inn[, .(p = mean(tied_next_designee), n = .N), by = .(post_bin, group)], post_bin ~ group, value.var = c("p", "n"))
f0 <- lm(tied_next_designee ~ group + factor(election), data = inn)
f1 <- lm(tied_next_designee ~ group + post_bin + factor(election), data = inn)
cond <- data.table(term = c("groupP", "groupM", "groupN"), without_post = coef(f0)[c("groupP", "groupM", "groupN")],
                   with_post = coef(f1)[c("groupP", "groupM", "groupN")])
cat("\n== tied to the next designee by post held in e+2..e+4 (person-weighted)\n"); print(cells, digits = 3)
cat("LPM with transition FE, reference D:\n"); print(cond, digits = 3)

# (9) What the tie to the next designee is made of: office or school; office in the heir's secretariat at the destape
# or elsewhere; formed during the sitting president's term (year >= e) or before.
edges <- fread(file.path(db_root, "data", "networks", "network_edges.csv"))
gov <- fread(file.path(db_root, "data", "clean_positions", "govt_positions.csv"), na.strings = c("", "NA"))
heir <- designee[, .(election = election - 6L, d)]
heir_org <- rbindlist(lapply(seq_len(nrow(heir)), function(k) {
  e6 <- heir$election[k] + 6L
  g <- gov[person_id == heir$d[k] & !is.na(year_start) & year_start <= e6 - 1 & fifelse(is.na(year_end), year_start, year_end) >= e6 - 2 &
             !is.na(organization) & organization != ""]
  data.table(election = heir$election[k], d = heir$d[k], heir_org = tolower(g[order(-year_start)][1, organization]))
}))
long_e <- rbind(edges[, .(pid = person_a, d = person_b, edge_type, focus, year_start)],
                edges[, .(pid = person_b, d = person_a, edge_type, focus, year_start)])
ch <- merge(merge(inn[tied_next_designee == 1L, .(election, pid, group)], heir_org, by = "election"),
            long_e[edge_type %in% c("co_work", "co_education", "co_military", "co_revolution") & !is.na(year_start)],
            by = c("pid", "d"))[year_start <= election + 4L]
ch[, `:=`(office = edge_type == "co_work", school = edge_type == "co_education",
          heir_secretariat = edge_type == "co_work" & !is.na(heir_org) & startsWith(tolower(focus), heir_org),
          during_term = year_start >= election)]
chan <- ch[, .(office = any(office), school = any(school), heir_secretariat = any(heir_secretariat),
               office_elsewhere = any(office & !heir_secretariat), during_term = any(during_term),
               only_before = !any(during_term)), by = .(election, pid, group)]
chan_rates <- merge(inn[, .(n = .N), by = .(election, group)],
                    chan[, lapply(.SD, sum), by = .(election, group), .SDcols = c("office", "school", "heir_secretariat",
                         "office_elsewhere", "during_term", "only_before")], by = c("election", "group"), all.x = TRUE)
for (v in c("office", "school", "heir_secretariat", "office_elsewhere", "during_term", "only_before"))
  set(chan_rates, which(is.na(chan_rates[[v]])), v, 0L)
chan_eq <- chan_rates[, lapply(.SD, function(x) mean(x / n)), by = group,
                      .SDcols = c("office", "school", "heir_secretariat", "office_elsewhere", "during_term", "only_before")][order(group)]
cat("\n== channel of the tie to the next designee (share of the group in the pool at e+6, equal weight per transition)\n")
print(heir_org); print(chan_eq, digits = 3)

# (10) Continuation value: rung held at e+10 and e+16 by group at e (everyone in the pool at e alive then; 0 = no post).
pt <- fread(file.path(db_root, "data", "rank", "position_tiers.csv"))[!is.na(hybrid_rank) & !is.na(year_start)]
pt[, `:=`(y0 = as.integer(year_start), y1 = as.integer(pmax(fifelse(is.na(year_end), year_start, year_end), year_start)),
          rung = as.integer(floor(hybrid_rank + 1e-9)))]
pt <- pt[y1 - y0 <= 12L & rung >= 1L & rung <= 11L]
reps <- pt$y1 - pt$y0 + 1L; ii <- rep(seq_len(nrow(pt)), reps)
annual <- data.table(pid = pt$person_id[ii], year = pt$y0[ii] + sequence(reps) - 1L, rank = pt$rung[ii])[
  , .(rank = max(rank)), by = .(pid, year)]
rank_at <- function(ids, years) { z <- annual[data.table(pid = ids, year = years), on = .(pid, year), rank]; z[is.na(z)] <- 0L; z }
cv <- pool[election <= 1982L, .(election, pid, group = factor(group, c("D", "P", "M", "N")), death_year)]
cv[, `:=`(r10 = rank_at(pid, election + 10L), r16 = rank_at(pid, election + 16L))]
cv10 <- cv[is.na(death_year) | death_year > election + 10L, .(mean_rung = mean(r10), top_7plus = mean(r10 >= 7), any_post = mean(r10 > 0)),
           by = .(election, group)][, lapply(.SD, mean), by = group, .SDcols = c("mean_rung", "top_7plus", "any_post")][order(group)]
cv16 <- cv[election <= 1976L & (is.na(death_year) | death_year > election + 16L), .(mean_rung = mean(r16), top_7plus = mean(r16 >= 7),
           any_post = mean(r16 > 0)), by = .(election, group)][, lapply(.SD, mean), by = group, .SDcols = c("mean_rung", "top_7plus", "any_post")][order(group)]
cat("\n== continuation value: rung at e+10 (alive), equal weight per transition 1940-1982\n"); print(cv10, digits = 3)
cat("rung at e+16 (alive), 1940-1976\n"); print(cv16, digits = 3)

# (11) Symmetry: at e+6, a loser's exclusive followers (P at e+6) by their group at e, against the unaligned at e+6.
# Change in rung around e+6 (mean of e+7..e+10 minus e+5), holding the rung at e+5 and the transition fixed (former
# winners start higher, so raw falls are mostly level).
pool[, dlt := (R_p1 + R_p2 + R_p3 + R_p4) / 4 - R_m1]
sy <- merge(pool[group %in% c("P", "N") & election >= 1946L, .(election, pid, g6 = group, dlt, R_m1)],
            pool[, .(election = election + 6L, pid, g0 = group)], by = c("election", "pid"), all.x = TRUE)
sy[is.na(g0), g0 := "new"]
sy[, cell := relevel(factor(fifelse(g6 == "N", "N_e6", paste0("P_e6_from_", g0))), ref = "N_e6")]
fs <- lm(dlt ~ cell + factor(pmin(R_m1, 9L)) + factor(election), data = sy)
sym_eq <- merge(sy[, .(n = .N, rung_e5 = mean(R_m1), raw_change = mean(dlt)), by = cell],
                data.table(cell = sub("^cell", "", grep("^cell", names(coef(fs)), value = TRUE)),
                           vs_unaligned_same_rung = coef(fs)[grep("^cell", names(coef(fs)))],
                           se = summary(fs)$coefficients[grep("^cell", names(coef(fs))), 2]), by = "cell", all.x = TRUE)
cat("\n== losers' followers at e+6 by group at e: rung change vs the unaligned at e+6 with the same rung at e+5\n")
print(sym_eq, digits = 3)

# (12) Exit by group, one line.
ex <- tr[, .(in_pool_e6 = mean(!grepl("out", next_group)), died = mean(next_group == "out: died"),
             no_post_or_over75_or_aspirant = mean(next_group == "out: alive")), by = group][order(group)]
cat("\n== exit by group\n"); print(ex, digits = 3)

fwrite(signs, file.path(out_dir, "transitions_sign_tests.csv")); fwrite(bench_eq, file.path(out_dir, "transitions_random_heir.csv"))
fwrite(cells, file.path(out_dir, "transitions_by_post.csv")); fwrite(cond, file.path(out_dir, "transitions_conditional_on_post.csv"))
fwrite(chan_eq, file.path(out_dir, "transitions_tie_channels.csv")); fwrite(rbind(cbind(horizon = "e+10", cv10), cbind(horizon = "e+16", cv16)),
       file.path(out_dir, "transitions_continuation_value.csv"))
fwrite(sym_eq, file.path(out_dir, "transitions_symmetry.csv")); fwrite(ex, file.path(out_dir, "transitions_exit.csv"))
