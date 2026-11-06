# The aspirants of every succession for the co-optation block (MAIN_SPEC section 15): camp, seniority, military command,
# regional base, the new president's treatment (kept a top chair / demoted / no post) and whether the aspirant broke with
# the party around the succession; plus the opposition-entry regime of each succession. Descriptive table only.
#   Rscript code/04-analysis/main_direct_tie/aspirants_table.R
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
invisible(capture.output(source(file.path(script_dir, "estimate_main.R"))))
invisible(capture.output(source(file.path(script_dir, "rp_setup.R"))))
struct_dir <- file.path(data_dir, "structural")

# Opposition-entry regime at each election (Orozco Henriquez and Vargas Baca 2006, "Regulacion juridica de los partidos
# politicos en Mexico", in Zovatto ed., IDEA/UNAM, pp. 581-583): 1918 law, a party needs a founding assembly of 100
# members and independent candidacies are allowed; 7 Jan 1946 law, national parties registered by Gobernacion only, no
# independent candidacies; 4 Dec 1951 law, 30,000 members; 7 Jan 1954 reform, 75,000 members; 1973 law; 30 Dec 1977
# LFOPPE, conditional registration without a membership check; 12 Feb 1987 Federal Electoral Code.
exit_rules <- data.table(election = elections,
  law = c("1918 law", "1946 law", "1951 law (30,000 members)", "1954 reform (75,000)", "1954 reform (75,000)", "1954 reform (75,000)",
          "1973 law", "1977 LFOPPE (conditional registration)", "1977 LFOPPE / 1987 code"),
  exit_regime = c("easy", "intermediate", "intermediate", "hard", "hard", "hard", "hard", "easy", "easy"))
fwrite(exit_rules, file.path(struct_dir, "exit_rules.csv"))

mil <- fread(file.path(data_dir, "military_positions_wide.csv"))
gov_years <- positions[grepl("^governor", rule), .(pid = person_id, y0, y1)]
asp <- rbind(
  contenders[election_year <= 1988 & role != "winner", .(election = election_year, pid = person_id, name = corcholata_name,
             slate = fifelse(in_main_slate == 1L, "main", "full list"), runner_up = as.integer(role == "runner_up"), broke_year = broke_with_pri_year)],
  data.table(election = 1940L, pid = 158L, name = "Juan Andreu Almazán", slate = "outside the list", runner_up = 0L, broke_year = 1939L))
asp <- merge(asp, exit_rules[, .(election, exit_regime)], by = "election")
asp[, `:=`(age = election - as.numeric(birth[as.character(pid)]),
           rung_e2 = mapply(function(p, e) highest_rank(p, e - 2L, e - 2L), pid, election),
           rung_post2 = mapply(function(p, e) highest_rank(p, e + 1L, e + 2L), pid, election))]
asp[, treatment := fifelse(rung_post2 >= 8L, "kept a top chair", fifelse(rung_post2 >= 1L, "demoted", "no post"))]
asp[, broke := as.integer(!is.na(broke_year) & broke_year > 0 & broke_year >= election - 2L & broke_year <= election + 1L)]
asp[, `:=`(general = as.integer(mil$highest_rank[match(pid, mil$person_id)] %in% c("division_general", "brigade_general", "brigadier_general", "general")),
           commands = fcoalesce(as.integer(mil$n_commands[match(pid, mil$person_id)]), 0L))]
# camp: exclusive followers in the design (slate losers) and every pool member directly tied by e-2 (all aspirants)
asp[, camp_exclusive := fcoalesce(patrons$followers[match(paste(election, pid), paste(patrons$election, patrons$patron))], NA_integer_)]
asp[, camp_any := mapply(function(p, e) length(unique(long_ties[candidate == p & year_start <= e - 2L & pid %in% eligible[[as.character(e)]]$pid, pid])), pid, election)]
asp[, governors_in_camp := mapply(function(p, e) {
  f <- unique(long_ties[candidate == p & year_start <= e - 2L, pid])
  length(unique(gov_years[pid %in% f & y0 <= e - 2L & y1 >= e - 2L, pid]))
}, pid, election)]
asp[, governor_self := as.integer(pid %in% gov_years[y0 <= election - 2L & y1 >= election - 2L, pid]), by = election]
setorder(asp, election, -camp_any)
fwrite(asp, file.path(struct_dir, "aspirants.csv")); fwrite(asp, file.path(out_dir, "aspirants.csv"))
print(asp[, .N, by = .(slate)])
print(asp[, .(aspirants = .N, slate_losers = sum(slate == "main"), general = sum(general), governors_in_camp = sum(governors_in_camp)), by = .(election, exit_regime)])
