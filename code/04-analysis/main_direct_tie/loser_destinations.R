# Where the new president sends each losing aspirant (main slates 1940-1988, 47 losers), against the aspirant's public
# stature and the discontent of the moment. Two readings: a network theory of the threat predicts domestic posts for
# losers with large camps; a focal-point theory predicts posts abroad (embassies, international bodies) for visible ones.
# Destinations are read from every date range written in Camp's entry (role_text_raw), because parsed_positions keeps
# only the first range of a record ("head, Federal District, 1952-1958, 1958-1964, 1964-1966" -> 1952-1958).
#   Rscript code/04-analysis/main_direct_tie/loser_destinations.R
suppressPackageStartupMessages(library(data.table))
db_root <- Sys.getenv("TAPADOSPRI_DB_ROOT", file.path(path.expand("~"), "Dropbox", "TapadosPRI"))
data_dir <- file.path(db_root, "data")
out_dir <- Sys.getenv("TAPADOS_MAIN_OUTPUT_DIR", file.path(db_root, "output", "main_direct_tie"))
rd <- function(...) fread(file.path(data_dir, ...), na.strings = c("", "NA"))

cm <- rd("candidates", "corcholatas_matched.csv")
L <- rd("structural", "aspirants.csv")[slate == "main"][!cm[role == "winner", .(election = election_year, pid = person_id)],
                                                         on = .(election, pid)]
stopifnot(nrow(L) == 47L)

# Every date range of every record, expanded (two-digit ends completed: "1958-64").
pp <- rd("parsed_positions.csv")[!field_type %in% c("education", "birthplace") & person_id %in% L$pid]
spans <- pp[, {
  m <- regmatches(role_text_raw, gregexpr("1[89][0-9]{2}([[:space:]]*[–-][[:space:]]*[0-9]{2,4})?", role_text_raw))[[1]]
  if (!length(m)) list(y0 = as.integer(year_start), y1 = as.integer(fifelse(is.na(year_end), year_start, year_end))) else {
    y0 <- as.integer(substr(m, 1, 4))
    e <- sub("^.*[–-][[:space:]]*", "", m); e[!grepl("[–-]", m)] <- substr(m[!grepl("[–-]", m)], 1, 4)
    y1 <- as.integer(ifelse(nchar(e) == 2, paste0(substr(y0, 1, 2), e), e))
    list(y0 = y0, y1 = as.integer(pmax(y0, y1, na.rm = TRUE)))
  }
}, by = .(record_id, pid = person_id, ft = sub("_positions", "", field_type), role_text)][!is.na(y0)]

# Ex officio international seats of a cabinet secretary ("governor, IMF") are not postings abroad.
abroad_rx <- "ambassador|embassy|minister to |plenipotentiary|representative to|united nations|president, iadb|inter-american development bank|\\bconsul\\b|consul general|\\boas\\b|unesco|\\bfao\\b"
ex_officio_rx <- "^governor, (imf|world bank|iadb)"
top_rx <- paste0("^secretary of |^head, (department of the )?federal district|^head, department of |^attorney general of mexico|",
                 "^director general, (pemex|imss|issste|federal electric|conasupo)|^governor(?!-elect|, (imf|world bank|iadb))|justice, supreme court|president,? (of )?cen of pri")
bio <- rd("biographies_corrected.csv")
clean <- function(x) gsub("\\s+", " ", trimws(gsub("[^a-z, ]", "", tolower(iconv(gsub("[(][^)]*[)]", "", x), to = "ASCII//TRANSLIT")))))
nodes <- rd("networks", "network_nodes.csv")
L[nodes, key := clean(i.name), on = .(pid = person_id)]
bio[, key := clean(name)]
# Prosecutions are written in field k ("lost immunity ... tried for fraud ... convicted and imprisoned").
bio[, text := tolower(gsub("-\\s+", "", paste(personal_info, field_j, field_k)))]
L[bio, pinfo := i.text, on = "key"]
L[rd("structural", "death_years.csv"), death_year := i.death_year, on = .(pid = person_id)]

# Destination in the new president's first half (e+1..e+3): the first matching category in this order.
dest <- rbindlist(lapply(seq_len(nrow(L)), function(k) {
  e <- L$election[k]; p <- L$pid[k]
  s <- spans[pid == p & y0 <= e + 3L & y1 >= e + 1L & !(ft == "party" & grepl("candidate", tolower(role_text))) &
               !grepl(ex_officio_rx, tolower(role_text))]
  later <- spans[pid == p & y0 >= e + 1L & y0 <= e + 5L & grepl(abroad_rx, tolower(role_text), perl = TRUE) & !grepl(ex_officio_rx, tolower(role_text))]
  low <- tolower(s$role_text)
  ev <- function(i) paste(unique(sprintf("%s (%d-%d)", s$role_text[i], s$y0[i], s$y1[i])), collapse = "; ")
  jailed <- !is.na(L$pinfo[k]) && grepl("prison|jail|incarcerat|indicted|sentenced|convicted|tried for|lost immunity", L$pinfo[k])
  cat <- if (L$broke[k] == 1L && L$broke_year[k] <= e) "broke with the party" else
    if (!is.na(L$death_year[k]) && is.finite(L$death_year[k]) && L$death_year[k] <= e) "died" else
    if (jailed && grepl(as.character(e + 1L), L$pinfo[k])) "prosecuted" else
    if (any(grepl(top_rx, low, perl = TRUE) & !grepl("assistant|secretary-general|private secretary", low))) "top domestic post" else
    if (any(grepl(abroad_rx, low, perl = TRUE))) "abroad" else
    if (nrow(s) > 0) "other domestic post" else "no post"
  i <- if (cat == "abroad") grepl(abroad_rx, low, perl = TRUE) else if (cat == "top domestic post") grepl(top_rx, low, perl = TRUE) else rep(TRUE, nrow(s))
  data.table(election = e, pid = p, name = L$name[k], destination = cat, evidence = if (nrow(s)) ev(i) else "",
             jailed_ever = jailed, abroad_in_term = as.integer(nrow(later) > 0),
             abroad_later = paste(unique(sprintf("%s (%d)", later$role_text, later$y0)), collapse = "; "))
}))

# Stature before the race (e-5..e-3): U.S. press articles on any topic; public-exposure posts started by e-3; general.
press <- rd("ProQuest", "politician_mentions_yearly.csv")
L[, us_press := mapply(function(p, e) press[person_id == p & year %between% c(e - 5L, e - 3L), sum(articles_unambiguous)], pid, election)]
expo_rx <- "^governor|^head, (department of the )?federal district|director general, pemex|president,? (of )?cen of pri"
L[, exposure_post := mapply(function(p, e) as.integer(spans[pid == p & y0 <= e - 3L & grepl(expo_rx, tolower(role_text))][, .N] > 0), pid, election)]
opp <- fread(file.path(db_root, "output", "maps", "opposition_vote_by_state.csv"))
nat <- opp[, .(opp_prev = 1 - sum(regime) / sum(total)), by = .(election = year + 6L)]
L[nat, discontent_prev := i.opp_prev, on = "election"]

D <- merge(L[, .(election, pid, name, camp_any, general, us_press, exposure_post, discontent_prev, broke)], dest[, -"name"],
           by = c("election", "pid"))
D[, abroad := as.integer(destination == "abroad")]
D[, visible := as.integer(us_press > median(us_press)), by = election]
D[, big_camp := as.integer(camp_any > median(camp_any)), by = election]
setorder(D, election, -us_press)
fwrite(D, file.path(out_dir, "loser_destinations.csv"))

alive <- D[!destination %in% c("died", "broke with the party")]
cat("\n== destinations of the 47 losers (first half of the new term)\n"); print(D[, .N, by = destination][order(-N)])
cat("\n== by election\n"); print(dcast(D[, .N, by = .(election, destination)], election ~ destination, fill = 0))
cat("\n== abroad rate among those who stayed, by visibility (U.S. press above the slate median) and camp size\n")
print(alive[, .(n = .N, abroad = mean(abroad), abroad_in_term = mean(abroad_in_term), top_domestic = mean(destination == "top domestic post"),
                no_post = mean(destination == "no post")), by = .(visible)][order(visible)], digits = 2)
print(alive[, .(n = .N, abroad = mean(abroad), abroad_in_term = mean(abroad_in_term), top_domestic = mean(destination == "top domestic post"),
                no_post = mean(destination == "no post")), by = .(big_camp)][order(big_camp)], digits = 2)
cat("Fisher, abroad x visible: p =", signif(fisher.test(table(alive$abroad, alive$visible))$p.value, 3),
    "| abroad x big camp: p =", signif(fisher.test(table(alive$abroad, alive$big_camp))$p.value, 3), "\n")
f <- glm(abroad ~ scale(log1p(us_press)) + scale(log1p(camp_any)) + exposure_post, family = binomial, data = alive)
print(summary(f)$coefficients, digits = 3)
f2 <- glm(abroad ~ scale(log1p(us_press)) * scale(discontent_prev), family = binomial, data = alive)
cat("with discontent (opposition share in the previous presidential election):\n"); print(summary(f2)$coefficients, digits = 3)
cat("\n== the 47, for hand checking\n")
print(D[, .(election, name = substr(name, 1, 24), destination, in_term = abroad_in_term, press = us_press, camp = camp_any, evidence = substr(evidence, 1, 55))], nrows = 60)
