# Federal investment commanded (MAIN_SPEC section 9, 17 October 2026): percent of the year's federal public
# investment realized by the agency a politician heads (0 if none); window contrast and event study with the
# main design. The crosswalk from posts to agencies is the 13 October one (archived budget_outcome.py),
# ported unchanged. Run from the repo root: Rscript code/04-analysis/main_direct_tie/budget_outcome.R
args <- commandArgs(FALSE)
script_dir <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
invisible(capture.output(source(file.path(script_dir, "estimate_main.R"))))
source(file.path(script_dir, "design_tools.R"))
inv_dir <- file.path(data_dir, "investment")

# ------------------------------------------------------------------ 1. agency series (share of the year's total)
panel <- fread(file.path(inv_dir, "agency_investment_panel.csv"))
V <- "value_mn_new_pesos"
dep <- panel[block == "dependencias", .(v = sum(get(V), na.rm = TRUE)), by = .(agency_key, year)]
para <- panel[block == "paraestatal", .(v = sum(get(V), na.rm = TRUE)), by = .(agency_key, year)]
ramo <- panel[block == "ramo_sector", .(v = sum(get(V), na.rm = TRUE)), by = .(agency_key, year)]
dep_years <- unique(dep$year)
total <- rbind(dep[, .(t = sum(v)), by = year], para[year %in% dep_years, .(t = sum(v)), by = year])[, .(total = sum(t)), by = year]
total <- rbind(total, ramo[!(year %in% dep_years), .(total = sum(v)), by = year])
sector_parastatals <- list(sepafin = c("pemex", "cfe", "lyfc"), energia_sector = c("pemex", "cfe", "lyfc"),
                           sct = c("fnm", "fc_pacifico", "fc_chihuahua_pacifico", "fc_sureste", "fc_sonora_bc",
                                   "asa", "capufe", "aeromexico"))
ramo_own <- ramo[!(year %in% dep_years)]
ramo_own[, v := mapply(function(k, y, v) {
  sub <- para[year == y & agency_key %in% sector_parastatals[[k]], sum(v)]
  if (is.null(sector_parastatals[[k]])) sub <- 0
  max(v - sub, 0)
}, agency_key, year, v)]
series <- rbind(dep, ramo_own, para)[, .(nominal = sum(v)), by = .(agency_key, year)]
series <- merge(series, total, by = "year")[, share := 100 * nominal / total]
fwrite(series[order(agency_key, year)], file.path(out_dir, "budget_agency_series.csv"))

# ------------------------------------------------------------------ 2. who heads what
pos <- fread(file.path(data_dir, "rank", "position_tiers.csv"), na.strings = c("", "NA"))
heads <- pos[rule %in% c("cabinet_secretary", "df_regent", "big_parastatal_head", "parastatal_head",
                         "director_general", "autonomous_dept_head") & !is.na(year_start)]
heads[, `:=`(text = tolower(role_text), y0 = as.integer(year_start),
             y1 = as.integer(pmax(fifelse(is.na(year_end), year_start, year_end), year_start)))]
heads <- heads[y1 - y0 <= 12L]
secretary_re <- list(
  list("communications and public works", function(y) if (y <= 1958) "sop" else "sct"),
  list("communications and transport|secretary of communications\\b", function(y) "sct"),
  list("public works and human|human settlements", function(y) c("sahop", "sedue")),
  list("public works", function(y) c("sop", "sahop")),
  list("urban development|ecology", function(y) c("sedue", "sedesol")),
  list("agriculture and hydraulic", function(y) c("sarh", "sagar")),
  list("hydraulic resources", function(y) c("srh", "sarh")),
  list("agriculture|livestock|agrarian development", function(y) c("sag", "sarh", "sagar", "sagarpa")),
  list("agrarian", function(y) "sra"),
  list("social development", function(y) "sedesol"),
  list("tourism", function(y) "sectur"),
  list("energy|mines|national properties|government properties|patrimon|government industries",
       function(y) c("sepafin", "energia_sector")),
  list("commerce|industr|economy", function(y) c("secofi", "se")),
  list("programming and budget", function(y) "spp"),
  list("fisheries", function(y) "sepesca"),
  list("environment|natural resources", function(y) "semarnap"),
  list("public security", function(y) "ssp"),
  list("presidency", function(y) c("secretaria de la presidencia de la republica", "presidencia de la republica")),
  list("comptroller|contralor", function(y) c("secretaria de la contraloria general de la federacion",
                                              "contraloria general de la federacion",
                                              "contraloria y desarrollo administrativo e")),
  list("\\bgovernment\\b|gobernacion|interior", function(y) "segob"),
  list("foreign (relations|affairs)", function(y) "sre"),
  list("education", function(y) "sep"),
  list("\\blabor\\b", function(y) "stps"),
  list("treasury|finance|hacienda", function(y) "shcp"),
  list("national defense|\\bwar\\b|defense", function(y) "sedena"),
  list("\\bnavy\\b|marina", function(y) "semar"),
  list("health|welfare|salubridad", function(y) "ssa"),
  list("attorney general", function(y) "pgr"))
parastatal_re <- c(
  cfe = "federal electric(ity)? commission|comision federal de electricidad|\\bcfe\\b",
  fnm = "national railroads|ferrocarriles nacionales|\\bferronales\\b",
  imss = "\\bimss\\b|mexican (institute of )?social security|instituto mexicano del seguro social",
  issste = "\\bissste\\b|institute of (security and )?social services (for|of) (federal |state )?(government )?(workers|employees)",
  pemex = "\\bpemex\\b|petroleos mexicanos|mexican petroleum",
  ahmsa = "altos hornos",
  lyfc = "light and power( company)? of the cent(er|re)|luz y fuerza",
  capufe = "\\bcapufe\\b|federal highways and bridges|caminos y puentes federales",
  sicartsa = "\\bsicartsa\\b|las truchas",
  conasupo = "\\bconasupo\\b|subsistencias populares|popular subsistence",
  fertimex = "\\bfertimex\\b|guanos y fertilizantes|fertilizantes mexicanos|mexican fertilizers|guano",
  asa = "aeropuertos y servicios|airports and auxiliary services",
  aeromexico = "aeronaves de mexico|aeromexico",
  banobras = "\\bbanobras\\b|urban mortgage|public works bank|banco nacional hipotecario",
  `banco de mexico s a` = "bank of mexico|banco de mexico",
  fc_pacifico = "pacific railroad|ferrocarril del pacifico",
  loteria = "national lottery|loteria nacional",
  nafin = "nacional financiera|\\bnafin\\b")
titular <- "director general|general manager|general director|^director\\b|^director,|administrator|^president|^head\\b|regent"
not_titular <- "adjunto|deputy|assistant|subdirector|sub-director|coordinator|^director of|director of [a-z]"
has_data <- paste(series$agency_key, series$year)
resolve <- function(text, rule, year) {
  if (rule == "cabinet_secretary") {
    for (p in secretary_re) if (grepl(p[[1]], text, perl = TRUE)) {
      keys <- p[[2]](year)
      hit <- keys[paste(keys, year) %in% has_data]
      return(if (length(hit)) hit[1] else keys[1])
    }
    return(NA_character_)
  }
  if (rule == "df_regent") return("ddf")
  if (grepl(titular, text, perl = TRUE) && !grepl(not_titular, text, perl = TRUE)) {
    for (k in names(parastatal_re)) if (grepl(parastatal_re[[k]], text, perl = TRUE)) return(k)
  }
  NA_character_
}
heads[, key := mapply(resolve, text, rule, y0)]
fwrite(heads[, .(record_id, person_id, person_name, rule, role_text, y0, y1, key = fifelse(is.na(key), "UNMATCHED", key))][
  rule %in% c("cabinet_secretary", "df_regent", "big_parastatal_head", "parastatal_head") | key != "UNMATCHED"][order(key, y0)],
  file.path(out_dir, "budget_crosswalk_audit.csv"))
hy <- heads[!is.na(key)]
reps <- hy$y1 - hy$y0 + 1L
ii <- rep(seq_len(nrow(hy)), reps)
person_years <- data.table(pid = hy$person_id[ii], year = hy$y0[ii] + sequence(reps) - 1L, agency_key = hy$key[ii])
person_years <- merge(person_years, series[, .(agency_key, year, share)], by = c("agency_key", "year"), all.x = TRUE)
person_years[is.na(share), share := 0]
budget_py <- person_years[, .(share = max(share), heads = 1L), by = .(pid, year)]

# ------------------------------------------------------------------ 3. outcomes and estimates
ks <- -7:8; ref <- -2L
Bt <- sapply(ks, function(k) year_value(budget_py, k, "share")); colnames(Bt) <- ks
Ht <- sapply(ks, function(k) year_value(budget_py, k, "heads")); colnames(Ht) <- ks
wmax <- function(from, to) apply(sapply(from:to, function(k) year_value(budget_py, k, "share")), 1L, max)
whead <- function(from, to) apply(sapply(from:to, function(k) year_value(budget_py, k, "heads")), 1L, max)
b_pre <- wmax(-5, -2); b_post <- wmax(1, 4)
h_pre <- whead(-5, -2); h_post <- whead(1, 4)
d_all <- build_design()
windows <- estimate_columns(d_all, cbind(budget_share = b_post - b_pre, heads_agency = h_post - h_pre))$table
windows[, label := c("Federal investment commanded (percentage points)", "Heads an investment agency")]
desc <- data.table(group = c("designee", "losers"),
                   heads_pre = c(mean(h_pre[sample$treated == 1]), mean(h_pre[sample$treated == 0])),
                   heads_post = c(mean(h_post[sample$treated == 1]), mean(h_post[sample$treated == 0])),
                   share_pre = c(mean(b_pre[sample$treated == 1]), mean(b_pre[sample$treated == 0])),
                   share_post = c(mean(b_post[sample$treated == 1]), mean(b_post[sample$treated == 0])),
                   n_heads_post = c(sum(h_post[sample$treated == 1]), sum(h_post[sample$treated == 0])))
fwrite(windows, file.path(out_dir, "budget_windows.csv"))
fwrite(desc, file.path(out_dir, "budget_descriptives.csv"))
d_es <- build_design(formula = formula_es)
es <- estimate_columns(d_es, Bt[, colnames(Bt) != as.character(ref)] - Bt[, as.character(ref)])$table
es <- rbind(es[, .(k = as.integer(column), estimate, ci_lower, ci_upper, p_bootstrap)],
            data.table(k = ref, estimate = 0, ci_lower = 0, ci_upper = 0, p_bootstrap = NA))
setorder(es, k)
fwrite(es, file.path(out_dir, "budget_event_study.csv"))
es_figure(es, "Difference in federal investment commanded\nsince e-2 (percentage points)", "es_budget")

cat("agency series:", uniqueN(series$agency_key), "agencies,", min(series$year), "-", max(series$year), "\n")
cat("head records resolved:", sum(!is.na(heads$key)), "of", nrow(heads), "\n")
print(windows[, .(label, estimate = round(estimate, 3), ci_lower = round(ci_lower, 3), ci_upper = round(ci_upper, 3), p_bootstrap)])
print(desc)
print(es[, .(k, estimate = round(estimate, 3), ci_lower = round(ci_lower, 3), ci_upper = round(ci_upper, 3))])
