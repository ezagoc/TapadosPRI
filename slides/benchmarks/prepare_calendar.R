# Observed calendar inputs for independent, one-term conditional benchmarks.
# Original evaluation samples remain fixed.
cli <- commandArgs(FALSE)
this_file <- normalizePath(sub("^--file=", "", cli[grepl("^--file=", cli)][1]))
source(file.path(dirname(this_file), "prepare.R"))   # defines work (TAPADOS_BENCH_DIR) and the design objects
chained_out <- file.path(work, "data", "calendar")
dir.create(chained_out, recursive = TRUE, showWarnings = FALSE)
ids <- sort(unique(A$pid))
years <- 1931:1994
people <- nodes[match(ids, person_id), .(pid = person_id, name, birth_year)]
people[, death_year := dead$death_year[match(pid, dead$pid)]]
first_seen <- positions[, .(entry_year = min(y0)), by = .(pid = person_id)]
people[, entry_year := first_seen$entry_year[match(pid, first_seen$pid)]]
stopifnot(!anyNA(people$birth_year), !anyNA(people$entry_year))
fwrite(people, file.path(chained_out, "people.csv"))

calendar_matrix <- function(pp) {
  rr <- pp$y1 - pp$y0 + 1L; ii <- rep(seq_len(nrow(pp)), rr)
  tab <- data.table(pid = pp$person_id[ii], year = pp$y0[ii] + sequence(rr) - 1L, rank = pp$rung[ii])[
    , .(rank = max(rank)), by = .(pid, year)]
  setkey(tab, pid, year)
  y <- sapply(years, function(t) {
    z <- tab[data.table(pid = ids, year = t), on = .(pid, year), rank]
    z[is.na(z)] <- 0L; z
  })
  colnames(y) <- years
  data.table(pid = ids, y)
}
for (kind in c("all", "fed", "other", "top", "below_top")) {
  pp <- switch(kind, all = positions, fed = positions[movable == TRUE], other = positions[movable == FALSE],
               top = positions[rung >= 8L & rung < 11L], below_top = positions[rung < 8L | rung == 11L])
  fwrite(calendar_matrix(pp), file.path(chained_out, paste0("calendar_", kind, ".csv")))
}

# Dated connections for each independent succession experiment.
members <- rbindlist(lapply(elections, function(e) {
  sl <- slates[[as.character(e)]]
  ct <- unique(long_ties[candidate %in% sl$candidates & year_start <= e - 2L, .(pid, candidate)])
  ct <- ct[pid %in% ids]
  z <- data.table(election = e, pid = ids)
  z[, winner_tie := as.integer(pid %in% ct[candidate == sl$winner, pid])]
  z[, loser_tie := as.integer(pid %in% ct[candidate != sl$winner, pid])]
  counts <- ct[, .(n_direct = .N), by = pid]
  z[, n_direct := counts$n_direct[match(pid, counts$pid)]]
  z[is.na(n_direct), n_direct := 0L]
  single <- ct[, .(candidate = if (.N == 1L) candidate else NA_integer_), by = pid]
  z[, patron := single$candidate[match(pid, single$pid)]]
  z[, camp := fifelse(winner_tie == 1L, paste0("camp_", sl$winner),
                      fifelse(n_direct == 0L, "N", fifelse(n_direct == 1L, paste0("camp_", patron), "multiple_losers")))]
  eg <- ed[!is.na(year_end) & year_end <= e - 2L & credential_level > 0L,
           .(credential = max(credential_level)), by = .(pid = person_id)]
  z[, credential := eg$credential[match(pid, eg$pid)]]
  z[is.na(credential), credential := 0L]
  z[, winner := sl$winner]
  z
}))
fwrite(members, file.path(chained_out, "memberships.csv"))

cat(sprintf("Observed inputs: %d people, %d years, %d independent succession experiments.\n", length(ids), length(years), length(elections)))
