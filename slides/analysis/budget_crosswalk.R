# Shared crosswalk between the agency investment panel (05-investment/10_*) and the heads of agencies in
# position_tiers.csv. Sourced by budget_outcome.R (MAIN_SPEC section 9) and investment_heads.R (the "who runs
# the money" descriptive). Needs data.table; `data_dir` is set by estimate_main.R.
#
# 1. build_agency_series(panel): one row per agency x year with the share of the year's federal investment,
#    as budget_outcome.R has computed it since 17 October 2026 (dependencias + paraestatal in the years with
#    the dependencias block; the ramo_sector view minus each sector's mapped parastatals in 1984-1997).
# 2. head_records(pos): the head-of-agency records of position_tiers.csv (rules and text filters).
# 3. resolve_head(text, rule, y0, y1, has_data): the agency key(s) a head record points to, NA if none. Keys
#    are chosen among those with data in the spell, so a spell that straddles a renaming (SAHOP -> SEDUE,
#    SRH -> SARH) keeps the key of each of its years (one row per key; years without a row of that key get 0).
# 4. resolve_heads(heads, series): adds `key`; a record naming two agencies gets one row per agency.
# 5. person_year_shares(hy, series): person x year x agency rows with the agency's share that year.
#
# Crosswalk history. The 13 October design (archived budget_outcome.py, ported to R on 17 October) resolved
# cabinet secretaries, the DF regent and directors general of parastatals from the role text. Extended on
# 20 October 2026 (each addition is marked "20 Oct" below with an example role text) so that the share of
# federal investment in agency-years with no identified head falls: DF heads filed as department chiefs,
# federal secretaries filed as secretary_other, the SCOP secretary before the 1959 split, founding heads
# filed as unranked, more parastatals of the panel, and a sub-unit guard so that "director general of
# construction, National Railroads of Mexico" no longer counts as the head of the railways.
suppressPackageStartupMessages(library(data.table))

sector_parastatals <- list(sepafin = c("pemex", "cfe", "lyfc"), energia_sector = c("pemex", "cfe", "lyfc"),
                           sct = c("fnm", "fc_pacifico", "fc_chihuahua_pacifico", "fc_sureste", "fc_sonora_bc",
                                   "asa", "capufe", "aeromexico"))

build_agency_series <- function(panel, V = "value_mn_new_pesos") {
  dep <- panel[block == "dependencias", .(v = sum(get(V), na.rm = TRUE)), by = .(agency_key, year)]
  para <- panel[block == "paraestatal", .(v = sum(get(V), na.rm = TRUE)), by = .(agency_key, year)]
  ramo <- panel[block == "ramo_sector", .(v = sum(get(V), na.rm = TRUE)), by = .(agency_key, year)]
  dep_years <- unique(dep$year)
  total <- rbind(dep[, .(t = sum(v)), by = year], para[year %in% dep_years, .(t = sum(v)), by = year])[, .(total = sum(t)), by = year]
  total <- rbind(total, ramo[!(year %in% dep_years), .(total = sum(v)), by = year])
  ramo_own <- ramo[!(year %in% dep_years)]
  ramo_own[, v := mapply(function(k, y, v) {
    sub <- para[year == y & agency_key %in% sector_parastatals[[k]], sum(v)]
    if (is.null(sector_parastatals[[k]])) sub <- 0
    max(v - sub, 0)
  }, agency_key, year, v)]
  series <- rbind(dep, ramo_own, para)[, .(nominal = sum(v)), by = .(agency_key, year)]
  merge(series, total, by = "year")[, share := 100 * nominal / total]
}

# ------------------------------------------------------------------ heads of agencies
head_rules <- c("cabinet_secretary", "df_regent", "big_parastatal_head", "parastatal_head",
                "director_general", "autonomous_dept_head")
# 20 Oct: heads of the Department of the Federal District that the rank rules filed as department chiefs:
# "head, Federal District" (Uruchurtu 1952-1966), "head, Federal District Department" (Rojo Gomez 1940-1946).
df_head_re <- "^head, (department of the )?federal district( department)?$"
# 20 Oct: federal secretaries filed as secretary_other, a bare title without a place or a court after a comma:
# "secretary of communication and transportation" (Buchanan 1958-1964), "secretary of programming and budgeting"
# (Aspe 1987-1988), "secretary of public health" (Gamboa Pascasio 1946-1952), "secretary of trade" (de la Vega
# 1977-1982). "secretary of studies and accounts, Supreme Court" has a comma; "secretary of agreements" matches
# no secretariat.
bare_secretary_re <- "^secretary of [a-z ]+$"
# 20 Oct: founding heads filed as unranked: "founder and first director general, Federal Electric Commission".
founder_re <- "^(founder and |founding )?(first )?(director general|general manager), "
# 20 Oct: the heads of the National Irrigation Commission (the panel's srh key before the secretariat of 1947),
# filed as unranked: "executive director, National Irrigation Commission" (Serrano 1939-1944, Orive Alba
# 1940-1946), "executive member, National Irrigation Commission" (Parres 1940-1946, the vocal ejecutivo).
cni_head_re <- "^(executive (director|member)|president), national irrigation commission$"

# 20 Oct: a date range inside the role text dates the spell; 04_parse_positions kept only the end year of
# "secretary of public works, June 18, 1935–Jan. 23" (Mugica: year_start 1939) and of "secretary of agriculture
# and livestock, Aug. 16, 1937–Nov. 30" (Parres: 1940). The year before the dash is the start of the spell when
# it precedes the parsed year_start.
text_start_year <- function(text) {
  m <- regmatches(text, regexpr("(19|20)[0-9]{2}(?=\\s*[\u2013\u2014-])", text, perl = TRUE))
  as.integer(if (length(m)) m else NA)
}
# 20 Oct: the panel keys the Secretaria de Comunicaciones y Obras Publicas (SCOP) as sop through 1958 and the
# two secretariats of the 1959 split as sop / sct from 1959. A communications or public-works secretary whose
# spell straddles 1958-1959 ("secretary of communication and transportation", Buchanan 1958-1964) is split
# there so that each piece resolves to the key of its own years.
split_1959_re <- "communications? and (public works|transport)|^secretary of communications?\\b|^secretary of public works"

head_records <- function(pos) {
  txt <- tolower(pos$role_text)
  heads <- pos[rule %in% head_rules |
               (rule == "jefe_de_departamento" & grepl(df_head_re, txt, perl = TRUE)) |
               (rule == "secretary_other" & grepl(bare_secretary_re, txt, perl = TRUE)) |
               (rule == "unranked" & (grepl(founder_re, txt, perl = TRUE) | grepl(cni_head_re, txt, perl = TRUE)))]
  heads <- heads[!is.na(year_start)]
  heads[, `:=`(text = tolower(role_text), y0 = as.integer(year_start),
               y1 = as.integer(pmax(fifelse(is.na(year_end), year_start, year_end), year_start)))]
  heads[, text_y0 := sapply(role_text, text_start_year)]
  heads[!is.na(text_y0) & text_y0 < y0 & y0 - text_y0 <= 12L, y0 := text_y0]
  heads[, text_y0 := NULL]
  heads <- heads[y1 - y0 <= 12L]
  straddle <- heads[rule %in% c("cabinet_secretary", "secretary_other") & grepl(split_1959_re, text, perl = TRUE) &
                    y0 <= 1958L & y1 >= 1959L]
  if (nrow(straddle)) {
    heads <- heads[!(rule %in% c("cabinet_secretary", "secretary_other") & grepl(split_1959_re, text, perl = TRUE) &
                     y0 <= 1958L & y1 >= 1959L)]
    heads <- rbind(heads, copy(straddle)[, y1 := 1958L], copy(straddle)[, y0 := 1959L])
  }
  heads
}

# Secretariats: first regex that matches wins; the key with data in that year is preferred.
secretary_re <- list(
  # 20 Oct: "communication" singular ("secretary of communication and public works", Serrano 1931-1932) and
  # SCOP before the 1959 split under the panel's key sop ("secretary of public works" is Camp's name for SCOP
  # in 1935-1958: Mugica, Maximino Avila Camacho, Garcia Lopez, Lazo, Buchanan).
  list("communications? and public works", function(y) if (y <= 1958) "sop" else "sct"),
  list("communications? and transport|^secretary of communications?\\b", function(y) if (y <= 1958) "sop" else "sct"),
  list("public works and human|human settlements", function(y) c("sahop", "sedue")),
  list("public works", function(y) c("sop", "sahop", "sedue")),
  list("urban development|ecology", function(y) c("sedue", "sedesol")),
  list("agriculture and hydraulic", function(y) c("sarh", "sagar")),
  list("hydraulic resources", function(y) c("srh", "sarh")),
  list("agriculture|livestock|agrarian development", function(y) c("sag", "sarh", "sagar", "sagarpa")),
  list("agrarian", function(y) "sra"),
  list("social development", function(y) "sedesol"),
  list("tourism", function(y) "sectur"),
  list("energy|mines|national properties|government properties|patrimon|government industries",
       function(y) c("sepafin", "energia_sector")),
  # 20 Oct: "secretary of trade" (de la Vega 1977-1982), "secretary of economic development" (Derbez 2000-2003).
  list("commerce|industr|economy|economic development|\\btrade\\b", function(y) c("secofi", "se")),
  # 20 Oct: "secretary of planning and programming" (Garcia Sainz 1977-1979).
  list("programming and budget|planning and programming", function(y) "spp"),
  list("fisheries", function(y) "sepesca"),
  list("environment|natural resources", function(y) "semarnap"),
  list("public security", function(y) "ssp"),
  list("presidency", function(y) c("secretaria de la presidencia de la republica", "presidencia de la republica",
                                   "secretaria de la presidencia")),
  # 20 Oct: "secretary of controller general" (Vazquez Nava 1988-1994).
  list("comptroller|contralor|controller", function(y) c("secretaria de la contraloria general de la federacion",
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
# 20 Oct: a secretary of a state, a city, the DF government or a parastatal is not a federal secretary:
# "secretary of social development, Department of the Federal District" (Bustani 1984-1986), "Secretary of
# social development, Leon", "secretary of labor relations, IMSS".
not_federal_secretary <- "federal district|department of the|\\bimss\\b|\\bpemex\\b|state of |, [a-z]+$"

# Parastatals: (regex, keys of the panel); first regex that matches wins, the key with data that year preferred.
parastatal_re <- list(
  list("federal electric(ity)? commission|comision federal de electricidad|\\bcfe\\b", "cfe"),
  list("national railroads|ferrocarriles nacionales|\\bferronales\\b|national railways", "fnm"),
  list("\\bimss\\b|mexican (institute of )?social security|instituto mexicano del seguro social", "imss"),
  list("\\bissste\\b|institute of (security and )?social services (for|of) (federal |state )?(government )?(workers|employees)", "issste"),
  list("\\bpemex\\b|petroleos mexicanos|mexican petroleum", "pemex"),
  list("altos hornos", "ahmsa"),
  list("light and power( company)? of the cent(er|re)|luz y fuerza|^light and power$", "lyfc"),
  list("\\bcapufe\\b|federal highways and bridges|caminos y puentes federales", "capufe"),
  list("\\bsicartsa\\b|las truchas", "sicartsa"),
  list("\\bconasupo\\b|subsistencias populares|popular subsistence", "conasupo"),
  list("\\bfertimex\\b|guanos y fertilizantes|fertilizantes mexicanos|mexican fertilizers|guano|fertilizers of mexico", "fertimex"),
  list("aeropuertos y servicios|airports and auxiliary services", "asa"),
  list("aeronaves de mexico|aeromexico", "aeromexico"),
  # 20 Oct: "director general, National Mortgage Bank" (de Dios Batiz 1940-1946), "Director general, National
  # Bank of Public Works and Services" (Robles Martinez 1965-1976).
  list("\\bbanobras\\b|urban mortgage|public works bank|banco nacional hipotecario|national mortgage|bank of public works", "banobras"),
  list("bank of mexico|banco de mexico", "banco de mexico s a"),
  list("pacific railroad|ferrocarril del pacifico|railroad of the pacific", "fc_pacifico"),
  list("national lottery|loteria nacional", "loteria"),
  # 20 Oct: the Mexican Institute of Foreign Trade before the foreign trade bank ("Foreign Trade Bank", Phillips
  # Olmedo 1982-1988), both in the panel.
  list("\\bimce\\b|mexican institute of foreign trade|instituto mexicano de comercio exterior", "imce"),
  list("\\bbancomext\\b|foreign trade bank|comercio exterior", "bancomext"),
  list("nacional financiera|\\bnafin\\b", "nafin"),
  # 20 Oct: parastatals of the panel the 13 October list did not name. Examples: "director general, CAPFCE"
  # (Ramirez Vazquez 1958-1964), "director general, Metro System, Department of the Federal District" (Cosio
  # Vidaurri 1982-1984), "director general, University City" (Lazo 1950), "director general, Diesel Nacional"
  # (Villasenor 1959-1970), "director general, Constructora Nacional de Carros de Ferrocarril" (Villasenor
  # 1952-1958), "director general of free ports" (Rolland 1946-1952), "director general, National Housing
  # Institute" (Quintanilla 1958-1964), "director general, National Border Program" (Vivanco 1966-1969),
  # "director general, National Bank of Cooperative Development" (Merino 1969), "director general, Cia.
  # Industrial de Atenquique" (Buenrostro 1964-1970), "director general, Military Industry" (Jimenez Segura
  # 1973-1982), "director general, Agricultural Credit Bank" (Castellanos 1965-1970).
  list("\\bcapfce\\b|federal school construction|school construction program", "capfce"),
  list("metro system|collective transport(ation)? system|sistema de transporte colectivo", "stc_metro"),
  list("university city|ciudad universitaria", "ciudad_universitaria"),
  list("diesel nacional", "diesel nacional s a"),
  list("constructora nacional de carros|railroad car construction|construction of railroad cars", "constructora nacional de carros de ferrocarril"),
  list("free ports|puertos libres", "puertos libres mexicanos"),
  list("national housing institute|instituto nacional de la vivienda", "instituto nacional de la vivienda"),
  list("national border program|\\bpronaf\\b|programa nacional fronterizo", "programa nacional fronterizo"),
  list("cooperative development bank|national bank of cooperative development|fomento cooperativo",
       c("banco nacional de fomento cooperativo", "banco nacional de fomento cooperativo s a de c v")),
  list("national bank of agricultural credit|agricultural credit bank|credito agricola", "banco nacional de credito agricola s a"),
  list("ejidal credit bank|national bank of ejidal credit|credito ejidal", "banco nacional de credito ejidal s a de c v"),
  list("atenquique", "compania industrial de atenquique"),
  list("military industry|industria militar", "dim"),
  list("\\bandsa\\b|almacenes nacionales|national (deposit )?warehouses", "andsa"),
  list("\\bpropemex\\b|productos pesqueros|mexican fish(ery)? products", "propemex"),
  list("chihuahua.{1,6}pacific", "fc_chihuahua_pacifico"),
  list("southeast(ern)? railroad|railroad of the southeast|unidos del sureste|ferrocarril del sureste", "fc_sureste"),
  list("sonora.{1,3}baja california", "fc_sonora_bc"),
  list("chapala", "chapala_electric"),
  list("patronato.*polytechnic|works of the national polytechnic", "patronato_obras_ipn"),
  list("electric transport(ation)? service", "ste_df"))
titular <- "director general|general manager|general director|^director\\b|^director,|administrator|^president|^head\\b|regent"
not_titular <- "adjunto|deputy|assistant|subdirector|sub-director|coordinator|^director of|director of [a-z]"
# 20 Oct: sub-unit guard. The record is split at its commas. The first segment must be a bare title ("director
# general", "general manager", "founder and first director general") followed by the agency in the next
# segment(s), or a title "of" the agency itself ("director general of IMSS", "director general of federal
# highways and bridges"). A title "of" a function ("director general of construction, National Railroads of
# Mexico"; "director general of refining, PEMEX"; "director general of supplies, Federal Electric Commission")
# is a sub-head, not the head. A segment naming a sub-unit ("IMSS Center", "Buenavista Project", "Eastern
# Division", "CONASUPO District", "Housing Trust Fund", "NAFIN Azucarera") rejects the record; segments with a
# date, a qualifier or the parent secretariat ("Oct.", "2006-", "under Rosendo Gomez", "SA", "Secretariat of
# Public Education", "Department of the Federal District") are skipped; any other segment (a place: "director
# general, ISSSTE, Chiapas") rejects the record. A record naming two agencies ("director general, Siderurgica
# Lazaro Cardenas-Las Truchas, Altos Hornos de Mexico, and Cia. Fundidora") keeps both.
title_words <- "director general|general manager|general director|managing director|executive president|director|administrator|president|head|regent|manager"
title_prefix <- paste0("^(founder and |founding |first |the )*(", title_words, ")")
sub_unit <- paste0("\\b(division|department of|center|centre|hospital|project|council|trust|fund|district|office|",
                   "section|branch|zone|plant|refinery|unit|committee for|azucarera|sugar|before it became|",
                   "workers|clinic|school|institute of (the )?[a-z]+ of|laboratory|laboratories)\\b")
date_or_qualifier <- paste0("^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|[0-9]|under |during |when |and |in charge|",
                            "before |after |which |until |from |since |s\\.? ?a\\.?( de c\\.? ?v\\.?)?$|secretariat of|",
                            "secretaria de|department of the federal district|federal district$|office of the|",
                            "mexico city|\\(|sa de cv|s\\.a\\. de c\\.v\\.)")

# Keys of the first parastatal regex that matches `seg`, those with data in the spell first (all of them joined
# by "|" when several have data: a spell that straddles a renaming keeps every key of its years); NA if none.
# A sub-unit word next to the agency name ("IMSS Center", "CONASUPO District") rejects the segment ("").
pick_parastatal <- function(seg, years, has_data) {
  for (p in parastatal_re) if (grepl(p[[1]], seg, perl = TRUE)) {
    rest <- sub(p[[1]], " ", seg, perl = TRUE)
    if (grepl(sub_unit, rest, perl = TRUE)) return("")
    return(keys_with_data(p[[2]], years, has_data))
  }
  NA_character_
}
keys_with_data <- function(keys, years, has_data) {
  hit <- keys[sapply(keys, function(k) any(paste(k, years) %in% has_data))]
  paste(if (length(hit)) hit else keys[1], collapse = "|")
}

parastatal_keys <- function(text, years, has_data) {
  if (grepl(not_titular, text, perl = TRUE) && !grepl(title_prefix, text, perl = TRUE)) return(character(0))
  segs <- trimws(strsplit(text, ",", fixed = TRUE)[[1]])
  segs <- segs[nchar(segs) > 0]
  if (!length(segs) || !grepl(title_prefix, segs[1], perl = TRUE)) return(character(0))
  if (grepl(not_titular, segs[1], perl = TRUE)) return(character(0))
  remainder <- trimws(sub(paste0(title_prefix, "( (of|for)( the)?)?"), "", segs[1], perl = TRUE))
  if (nchar(remainder)) {                       # "director general of <agency>"
    k <- pick_parastatal(remainder, years, has_data)
    return(if (is.na(k) || k == "") character(0) else k)
  }
  keys <- character(0)                          # "director general, <agency>[, <agency>][, date or qualifier]"
  for (seg in segs[-1]) {
    k <- pick_parastatal(seg, years, has_data)
    if (!is.na(k) && k == "") return(character(0))
    if (!is.na(k)) { keys <- c(keys, k); next }
    if (grepl(date_or_qualifier, seg, perl = TRUE)) next
    return(character(0))
  }
  unique(keys)
}

resolve_head <- function(text, rule, y0, y1, has_data) {
  years <- y0:y1
  if (rule %in% c("cabinet_secretary", "secretary_other")) {
    if (grepl(not_federal_secretary, text, perl = TRUE)) return(NA_character_)
    for (p in secretary_re) if (grepl(p[[1]], text, perl = TRUE)) return(keys_with_data(p[[2]](y0), years, has_data))
    return(NA_character_)
  }
  if (rule %in% c("df_regent", "jefe_de_departamento")) return("ddf")
  if (grepl(cni_head_re, text, perl = TRUE)) return("srh")
  keys <- parastatal_keys(text, years, has_data)
  if (!length(keys)) return(NA_character_)
  paste(keys, collapse = "|")
}

# Adds `key` (NA when the record points to no agency); a record naming two agencies becomes two rows.
resolve_heads <- function(heads, series) {
  has_data <- paste(series$agency_key, series$year)
  heads[, key := mapply(resolve_head, text, rule, y0, y1, MoreArgs = list(has_data = has_data))]
  multi <- heads[grepl("|", key, fixed = TRUE)]
  if (nrow(multi)) {
    heads <- heads[!grepl("|", key, fixed = TRUE)]
    ks <- strsplit(multi$key, "|", fixed = TRUE)
    multi <- multi[rep(seq_len(nrow(multi)), lengths(ks))][, key := unlist(ks)]
    heads <- rbind(heads, multi)
  }
  heads
}

# Person x year x agency rows (one per year of each resolved spell) with the agency's share that year (0 if the
# panel has no row for that agency-year).
person_year_shares <- function(hy, series) {
  reps <- hy$y1 - hy$y0 + 1L
  ii <- rep(seq_len(nrow(hy)), reps)
  person_years <- data.table(pid = hy$person_id[ii], year = hy$y0[ii] + sequence(reps) - 1L, agency_key = hy$key[ii])
  person_years <- merge(person_years, series[, .(agency_key, year, share)], by = c("agency_key", "year"), all.x = TRUE)
  person_years[is.na(share), share := 0]
  person_years
}

# ------------------------------------------------------------------ exact decomposition (investment_heads.R)
# Every agency row of a year sums to 100 here, unlike build_agency_series, whose 1984-1997 rows add parastatals
# outside the three mapped sectors on top of the sector totals (103-109%). In 1984-1997 every parastatal of the
# panel is subtracted from the sector that contains it (SEMIP / Energia for oil, electricity, steel, fertilizers
# and sugar; SCT for railways, airports, roads and the airline; social security contributions for IMSS and
# ISSSTE; SECOFI for CONASUPO and IMCE; Pesca for Propemex; Hacienda for the lottery; Gobernacion for PIPSA) and
# the shares are rescaled to 100 (`raw_sum` keeps the pre-rescaling sum: 100-101).
sector_of_parastatal <- function(key, lineage, year) {
  energy <- lineage %in% c("pemex", "electricity", "steel", "fertilizers") |
    key %in% c("fundidora monterrey", "azucar s a de c v", "azucar", "diesel nacional s a", "hules mexicanos", "sidermex")
  fifelse(energy, fifelse(year <= 1992, "sepafin", "energia_sector"),
  fifelse(lineage %in% c("transport", "railroads"), "sct",
  fifelse(lineage == "social_security", fifelse(year <= 1986, "poder legislativo y judicial y aportaciones a seguridad social",
                                                "aportaciones a seguridad social"),
  fifelse(lineage %in% c("food_distribution", "commerce"), "secofi",
  fifelse(lineage == "fisheries", fifelse(year <= 1992, "sepesca", "semarnap"),
  fifelse(key %in% c("loteria", "lotenal"), "shcp",
  fifelse(key %in% c("pipsa", "productora e importadora de papel s a"), "segob", NA_character_)))))))
}
# Lines of the panel that are not an agency with a head: programmes run through agreements with the states
# (Desarrollo Regional, Solidaridad / Superacion de la pobreza, PIDER), the local boards of material improvement,
# residual lines ("Otros", "Erogaciones no sectorizables", "Provisiones salariales", "Subsidios"), transfers
# (Aportaciones a seguridad social / educacion basica), the legislature, courts and electoral bodies, the
# federal territories and the bilateral foot-and-mouth campaign of 1947-1951.
no_head_by_construction_re <- paste0("^(desarrollo_regional|solidaridad_programs|pider|juntas_mejoras|provisiones_salariales|otras$|",
                                     "otrosl|otros |erogaciones|aportaciones|poder legislativo|organos electorales|tribunal|",
                                     "subsidios|reconstruccion|comision mexico americana|territorio)")

build_agency_shares_exact <- function(panel, V = "value_mn_new_pesos") {
  lin <- unique(panel[, .(agency_key, lineage = fifelse(is.na(lineage), "", lineage))])[, .(lineage = lineage[1]), by = agency_key]
  dep <- panel[block == "dependencias", .(v = sum(get(V), na.rm = TRUE)), by = .(agency_key, year)]
  para <- panel[block == "paraestatal", .(v = sum(get(V), na.rm = TRUE)), by = .(agency_key, year)]
  ramo <- panel[block == "ramo_sector", .(v = sum(get(V), na.rm = TRUE)), by = .(agency_key, year)]
  dep_years <- unique(dep$year)
  para[, lineage := lin$lineage[match(agency_key, lin$agency_key)]]
  para[, sector := sector_of_parastatal(agency_key, lineage, year)]
  mapped <- para[!(year %in% dep_years) & !is.na(sector), .(sub = sum(v)), by = .(agency_key = sector, year)]
  ramo_own <- merge(ramo[!(year %in% dep_years)], mapped, by = c("agency_key", "year"), all.x = TRUE)
  ramo_own[is.na(sub), sub := 0][, v := pmax(v - sub, 0)]
  total <- rbind(dep[, .(t = sum(v)), by = year], para[year %in% dep_years, .(t = sum(v)), by = year])[, .(total = sum(t)), by = year]
  total <- rbind(total, ramo[!(year %in% dep_years), .(total = sum(v)), by = year])
  rows <- rbind(dep[, .(agency_key, year, v)], ramo_own[, .(agency_key, year, v)], para[, .(agency_key, year, v)])[
    , .(nominal = sum(v)), by = .(agency_key, year)]
  rows <- merge(rows, total, by = "year")
  rows[, raw_sum := 100 * sum(nominal) / total[1], by = year]
  rows[, share := 100 * nominal / sum(nominal), by = year]
  rows[, no_head_by_construction := grepl(no_head_by_construction_re, agency_key, perl = TRUE)]
  rows[]
}
