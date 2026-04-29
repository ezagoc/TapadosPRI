# ============================================================
# clean_biographies.R
# Systematic cleaning of the TapadosPRI biographies dataset
#
# Input:  data/biographies.csv          (2,886 x 13)
# Output: data/biographies_r_cleaned.csv
#
# Columns added by this script:
#   name       → name_clean, deceased, death_year, death_date
#   birth_date → birth_date_clean, birth_date_precision, birth_decade
#   education  → edu_1 / edu_start_1 / edu_end_1  … (up to 18 groups)
#   public_positions  → pub_pos_1 / pub_pos_start_1 / pub_pos_end_1 … (up to 9)
#   party_positions   → party_pos_* (up to 18)
#   govt_positions    → govt_pos_*  (up to 23)
#   labor_positions   → labor_pos_* (up to 14)
#   other_positions   → other_pos_* (up to 13)
#   field_j           → mil_*       (up to 36)
# ============================================================

library(tidyverse)
library(lubridate)

DB_ROOT <- Sys.getenv("TAPADOSPRI_DB_ROOT", unset = "C:/Users/Dell/Dropbox/TapadosPRI")
DATA_DIR <- Sys.getenv("TAPADOSPRI_DATA_DIR", unset = file.path(DB_ROOT, "data"))

# ---- 0. LOAD DATA ------------------------------------------
df <- read_csv(
  file.path(DATA_DIR, "biographies.csv"),
  locale        = locale(encoding = "UTF-8"),
  show_col_types = FALSE
)

cat("Loaded:", nrow(df), "rows x", ncol(df), "columns\n\n")


# ============================================================
# SECTION 1  Helper functions
# ============================================================

# ------------------------------------------------------------------
# parse_bio_date()
#
# Converts a messy date character vector to as.Date.
# Handles:
#   "Mar. 4, 1906"        → full date (abbreviated month)
#   "June 14, 1949"       → full date (full month name)
#   "1910"                → year only (day set to Jan 1)
#   "Nov., 1917"          → month-year only (day set to 1st)
#   "July, 1959"          → month-year only (no period variant)
#   "Jan. 31. 1951"       → period used as day/year separator
#   "1900s"               → decade approximation (date = NA)
#   "Feb. 8, 1946; City"  → birthplace contamination (stripped)
#   "June 14, 1936. City" → location after period (stripped)
#   OCR garbage           → set to NA
#
# Returns a list: $date (Date), $precision (chr), $decade (int)
# ------------------------------------------------------------------
parse_bio_date <- function(x) {

  n             <- length(x)
  date_out      <- as.Date(rep(NA, n))
  precision_out <- rep("unknown", n)
  decade_out    <- rep(NA_integer_, n)

  is_na <- is.na(x)

  # --- Decade approximations: "1900s", "1950s" etc. ---
  is_decade <- !is_na & str_detect(x, "^\\d{4}s$")
  decade_out[is_decade]    <- as.integer(str_extract(x[is_decade], "\\d{4}"))
  precision_out[is_decade] <- "decade"

  # --- Garbled / unparseable entries ---
  #   · contains "mp" word (OCR artefact)
  #   · contains "sity of Texas" (source citation leaked in)
  #   · pure place name with no digits
  is_garbled <- !is_na & !is_decade & (
    str_detect(x, "\\bmp\\b")             |
    str_detect(x, fixed("sity of Texas")) |
    (!str_detect(x, "\\d"))                # no digits at all
  )
  precision_out[is_garbled] <- "unparseable"

  # --- Work only on parseable entries ---
  x_work <- x
  x_work[is_na | is_decade | is_garbled] <- NA_character_

  # Strip location info appended after the date:
  #   "Feb. 8, 1946; City, State"   → keep "Feb. 8, 1946"
  #   "June 14, 1936. Emiliano …"   → keep "June 14, 1936"
  x_work <- x_work %>%
    str_replace(";.*$",                              "") %>%   # after semicolon
    str_trim() %>%
    str_replace("(?<=\\d{4})[.,]?\\s+[A-Z][a-z].*$", "") %>% # ". City, State" after year
    str_trim()

  # Normalise all punctuation to spaces (handles commas, periods, mixed separators)
  # "Mar. 4, 1906" → "Mar 4 1906"
  # "Jan. 31. 1951" → "Jan 31 1951"   (period as day/year separator)
  # "Sept, 10, 1926" → "Sept  10  1926" → squished to "Sept 10 1926"
  x_norm <- x_work %>%
    str_replace_all("[.,]", " ") %>%
    str_squish()

  # --- Classify remaining entries ---
  is_year_only  <- !is.na(x_norm) & str_detect(x_norm, "^\\d{4}$")
  is_month_year <- !is.na(x_norm) & !is_year_only &
                   str_detect(x_norm, "^[A-Za-z]+ \\d{4}$")
  is_full       <- !is.na(x_norm) & !is_year_only & !is_month_year

  precision_out[is_year_only  & precision_out == "unknown"] <- "year_only"
  precision_out[is_month_year & precision_out == "unknown"] <- "month_year"
  precision_out[is_full       & precision_out == "unknown"] <- "full"

  # --- Pad incomplete dates so lubridate can parse them ---
  # Year-only  → "Jan 1 1910"
  # Month-year → "Mar 1 1932"
  x_norm[is_year_only]  <- paste0("Jan 1 ", str_extract(x_work[is_year_only], "\\d{4}"))
  x_norm[is_month_year] <- str_replace(
    x_norm[is_month_year], "^([A-Za-z]+) (\\d{4})$", "\\1 1 \\2"
  )

  # --- Parse ---
  parsed      <- suppressWarnings(
    parse_date_time(x_norm, orders = c("b d Y", "B d Y"), quiet = TRUE)
  )
  date_out <- as.Date(parsed)

  list(date = date_out, precision = precision_out, decade = decade_out)
}


# ------------------------------------------------------------------
# clean_name_col()
#
# Extracts deceased status and death date from the name field, then
# returns a clean title-cased name.
#
# Input patterns:
#   "aBarca alarcón, raiMundo (Deceased)"
#   "aBascal infante, salvador (Deceased 2000)"
#   "aBitia arzóPalo, José (Deceased Apr. 19, 1989)"
#   "aceves saucedo, ángel (Deceased June 26, 2003)"
#
# Returns a tibble: name_clean, deceased, death_year, death_date
# ------------------------------------------------------------------
clean_name_col <- function(name_vec) {

  # Extract the raw content inside (Deceased ...)
  death_raw <- str_match(name_vec, "\\(Deceased\\s*([^)]*)\\)")[, 2] %>%
    str_trim()

  # Bare year: "2000", "1958", "1979", etc.
  death_year <- if_else(
    !is.na(death_raw) & str_detect(death_raw, "^\\d{4}$"),
    as.integer(death_raw),
    NA_integer_
  )

  # Full date string: contains letters → pass through parse_bio_date
  death_date_str <- if_else(
    !is.na(death_raw) & str_detect(death_raw, "[A-Za-z]"),
    death_raw,
    NA_character_
  )
  death_bd <- parse_bio_date(death_date_str)

  # Clean name: strip deceased marker, normalise spaces, apply title case
  name_clean <- name_vec %>%
    str_remove("\\s*\\(Deceased[^)]*\\)") %>%
    str_squish() %>%
    str_to_title()

  tibble(
    name_clean = name_clean,
    deceased   = str_detect(coalesce(name_vec, ""), fixed("(Deceased")),
    death_year = death_year,
    death_date = death_bd$date
  )
}


# ------------------------------------------------------------------
# extract_yr_range()
#
# Given a character vector of position/education text items,
# extracts start_year and end_year and returns a cleaned text.
#
# Handles:
#   "governor, Guerrero, 1963–1969"  → start=1963, end=1969
#   "Medical degree …, 1934"         → start=1934, end=NA
#   "Director, Hospital of Iguala"   → start=NA,   end=NA
#
# Returns a list: $text (chr), $start (int), $end (int)
# ------------------------------------------------------------------
extract_yr_range <- function(text) {
  endash    <- "\u2013"
  range_pat <- sprintf("(\\d{4})[%s-](\\d{4})", endash)

  m     <- str_match(text, range_pat)
  start <- as.integer(m[, 2])
  end   <- as.integer(m[, 3])

  # Single year fallback (no range present)
  single <- if_else(is.na(start),
                    as.integer(str_extract(text, "\\b\\d{4}\\b")),
                    NA_integer_)
  start  <- coalesce(start, single)

  # Remove extracted year info from text
  rm_range <- sprintf(",?\\s*\\d{4}[%s-]\\d{4}", endash)
  text_out <- text %>%
    str_remove(rm_range)          %>%   # year range
    str_remove(",\\s*\\d{4}\\s*$") %>%  # trailing single year
    str_remove(",\\s*$")          %>%   # trailing comma
    str_squish()

  # Return NA text for entries that were entirely a year (edge case)
  text_out <- if_else(text_out == "" | text_out == "NA", NA_character_, text_out)

  list(text = text_out, start = start, end = end)
}


# ------------------------------------------------------------------
# split_to_wide()
#
# Splits a semicolon-delimited column into wide format.
# For each split item i, adds three columns:
#   {prefix}_i       — cleaned text (year removed)
#   {prefix}_start_i — start year (integer)
#   {prefix}_end_i   — end year   (integer, NA if single year)
#
# NOTE: field_j has up to 36 items → adds 108 columns. Consider
# whether you need all items or just the first few.
# ------------------------------------------------------------------
split_to_wide <- function(df, col, prefix) {
  items_list <- df[[col]] %>% str_split(";\\s*")
  max_n      <- max(lengths(items_list), na.rm = TRUE)

  cat("  ", col, "→", max_n, "items max →", max_n * 3, "new columns\n")

  for (i in seq_len(max_n)) {
    item_i <- map_chr(items_list, function(items) {
      if (all(is.na(items)))   return(NA_character_)
      if (length(items) < i)   return(NA_character_)
      v <- str_trim(items[[i]])
      if (is.na(v) || v == "") NA_character_ else v
    })

    yr <- extract_yr_range(item_i)

    df[[paste0(prefix, "_",       i)]] <- yr$text
    df[[paste0(prefix, "_start_", i)]] <- yr$start
    df[[paste0(prefix, "_end_",   i)]] <- yr$end
  }

  df
}


# ============================================================
# SECTION 2  Apply cleaning
# ============================================================

# ---- 2.1  Name ------------------------------------------------
cat("── Cleaning: name\n")
name_cols <- clean_name_col(df$name)
df <- bind_cols(df, name_cols)

cat("  deceased = TRUE:", sum(df$deceased), "rows\n")
cat("  death_year non-NA:", sum(!is.na(df$death_year)), "\n")
cat("  death_date non-NA:", sum(!is.na(df$death_date)), "\n\n")


# ---- 2.2  Birth date ------------------------------------------
cat("── Cleaning: birth_date\n")
bd <- parse_bio_date(df$birth_date)

df <- df %>%
  mutate(
    birth_date_clean     = bd$date,
    birth_date_precision = bd$precision,
    birth_decade         = bd$decade
  )

cat("  Precision breakdown:\n")
print(table(df$birth_date_precision, useNA = "always"))

# Spot-check: unparseable entries
up <- df %>% filter(birth_date_precision == "unparseable") %>%
  select(name_clean, birth_date)
if (nrow(up) > 0) {
  cat("\n  Unparseable birth_dates (birth_date_clean set to NA):\n")
  print(up, n = Inf)
}
cat("\n")


# ---- 2.3  Education -------------------------------------------
cat("── Cleaning: education\n")
df <- split_to_wide(df, "education", "edu")
cat("\n")


# ---- 2.4  Position columns ------------------------------------
cat("── Cleaning: position columns\n")
position_info <- list(
  list("public_positions", "pub_pos"),
  list("party_positions",  "party_pos"),
  list("govt_positions",   "govt_pos"),
  list("labor_positions",  "labor_pos"),
  list("other_positions",  "other_pos"),
  list("field_j",          "mil")
)

for (info in position_info) {
  df <- split_to_wide(df, info[[1]], info[[2]])
}
cat("\n")


# ============================================================
# SECTION 3  Save output
# ============================================================
out_path <- file.path(DATA_DIR, "biographies_r_cleaned.csv")
write_csv(df, out_path, na = "")

cat("── Saved:", out_path, "\n")
cat("   Final dimensions:", nrow(df), "rows x", ncol(df), "columns\n\n")


# ============================================================
# SECTION 4  Quick verification
# ============================================================
cat("── Verification\n")

cat("  birth_date_clean range (full dates only):\n")
full_dates <- df %>% filter(birth_date_precision == "full") %>% pull(birth_date_clean)
cat("    min:", format(min(full_dates, na.rm = TRUE)),
    " max:", format(max(full_dates, na.rm = TRUE)), "\n")

cat("  edu_1 non-NA:", sum(!is.na(df$edu_1)), "(expect ~2876)\n")

cat("  pub_pos_start_1 non-NA:", sum(!is.na(df$pub_pos_start_1)), "\n")

cat("  Sample cleaned row:\n")
df %>%
  filter(!is.na(birth_date_clean)) %>%
  select(name_clean, deceased, birth_date_clean, birth_date_precision,
         edu_1, edu_start_1, edu_end_1) %>%
  slice(1) %>%
  print()
