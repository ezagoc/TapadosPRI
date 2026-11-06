# Question 1 (SPEC.md): is a PRI governor's next post explained by the votes he delivered or by his tie to the
# president who appoints it? Linear probability with fixed effects for the presidential term in which the tenure ended
# and for the rung held before the governorship; standard errors clustered by state; a wild cluster bootstrap by
# presidential term (Webb weights, restricted under the null of each coefficient) as a check.
#   Rscript code/09-governors/04_q1_promotion.R   (after 03_governor_panel.py)
suppressPackageStartupMessages({library(data.table); library(fixest)})
db_root <- Sys.getenv("TAPADOSPRI_DB_ROOT", file.path(path.expand("~"), "Dropbox", "TapadosPRI"))
out_dir <- file.path(db_root, "output", "governors"); dir.create(out_dir, showWarnings = FALSE, recursive = TRUE)
G <- fread(file.path(db_root, "data", "governors", "governor_panel.csv"))[linked == TRUE]
G[, `:=`(votes_z = (votes_delivered - mean(votes_delivered, na.rm = TRUE)) / sd(votes_delivered, na.rm = TRUE),
         level_z = (votes_level - mean(votes_level, na.rm = TRUE)) / sd(votes_level, na.rm = TRUE),
         rung_before_bin = cut(rung_before, c(-1, 0, 5, 7, 11), labels = c("none", "1-5", "6-7", "8+")),
         roots = relevel(factor(roots), ref = "rooted"))]
set.seed(20102026L)

FE <- "term_end + rung_before_bin"
fml <- function(y, x) as.formula(paste(y, "~", paste(x, collapse = " + "), "|", FE))
wild_p <- function(y, x, data, coef, B = 9999) {      # restricted wild cluster bootstrap by presidential term
  d <- data[complete.cases(data[, c(y, setdiff(x, "roots"), "roots", "term_end", "rung_before_bin"), with = FALSE])]
  t0 <- tstat(feols(fml(y, x), d, cluster = ~term_end))[coef]
  r <- feols(fml(y, setdiff(x, coef)), d); yhat <- fitted(r); e <- resid(r)
  cl <- as.integer(factor(d$term_end)); G_ <- max(cl)
  webb <- c(-sqrt(1.5), -1, -sqrt(0.5), sqrt(0.5), 1, sqrt(1.5))
  tb <- replicate(B, {
    d$y_star <- yhat + e * sample(webb, G_, replace = TRUE)[cl]
    tstat(feols(fml("y_star", x), d, cluster = ~term_end))[coef]
  })
  mean(abs(tb) >= abs(t0))
}

X <- c("votes_z", "tie_president_next", "roots", "age_end")
specs <- list(main = fml("top_post", X), level = fml("top_post", replace(X, 1, "level_z")),
              tie_at_start = fml("top_post", replace(X, 2, "tie_president_start")),
              post7 = fml("post7", X), no_post = fml("no_post", X))
res <- rbindlist(lapply(names(specs), function(s) {
  m <- feols(specs[[s]], G, cluster = ~state)
  ct <- coeftable(m)
  data.table(spec = s, term = rownames(ct), estimate = ct[, 1], se_state = ct[, 2], p_state = ct[, 4], n = nobs(m),
             mean_y = mean(fitted(m) + resid(m)))
}))
for (k in c("votes_z", "tie_president_next")) res[spec == "main" & term == k, p_wild_term := wild_p("top_post", X, G, k, B = 1999)]
fwrite(res, file.path(out_dir, "q1_promotion.csv"))
print(res[term %in% c("votes_z", "level_z", "tie_president_next", "tie_president_start", "rootsparachuted",
                      "rootsfederal legislator only", "rootsno record")], digits = 3)

# Descriptive: top post by tie and by votes tercile within term.
G[, votes_tercile := cut(frank(votes_z, na.last = "keep") / sum(!is.na(votes_z)), c(0, 1/3, 2/3, 1), labels = c("low", "mid", "high"))]
cat("\nTop post after the governorship, by tie to the next president and by votes delivered (tercile):\n")
print(G[!is.na(votes_tercile), .(n = .N, top_post = mean(top_post)), by = .(tie = tie_president_next, votes_tercile)][order(tie, votes_tercile)], digits = 2)
cat("\nBy roots:\n"); print(G[, .(n = .N, top_post = mean(top_post), tie = mean(tie_president_next, na.rm = TRUE)), by = roots], digits = 2)
cat("\nEarly exits: left for a top post (called) vs not:\n"); print(G[early_exit == 1, .N, by = left_for_top_post])
