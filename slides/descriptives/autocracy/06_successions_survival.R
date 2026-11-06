# 06_successions_survival.R -- deck figure (15 Oct 2026): survival of autocracies by regular leader successions, in the
# style of autocracy_survival (03). Kaplan-Meier over the number of GWF regular successions in each regime's life
# (n_gwf_regular25, to 2025); a regime that broke down after k successions fails between k and k + 1; regimes still in
# power in 2025 are censored. Sample: the 280 GWF regimes in power in 1946-2010 (as 03). Counts cover each regime's whole
# life without delayed entry: regimes that ended before 1946 are not in the sample, which can only raise the curve.
# Writes output/slides/descriptives/autocracy_survival_successions.{pdf,png} (the deck's motivation figure). Needs the
# tables of 01_build_tables.R and 03_extend_to_2025.R. Run: Rscript slides/descriptives/autocracy/06_successions_survival.R
suppressPackageStartupMessages({ library(data.table); library(ggplot2); library(survival) })
db_root <- Sys.getenv("TAPADOSPRI_DB_ROOT", file.path(path.expand("~"), "Dropbox", "TapadosPRI"))
TB <- file.path(Sys.getenv("TAPADOSPRI_DATA_DIR", file.path(db_root, "data")), "_web_discovery_2026-10-13", "autocracies", "tables")
FIG <- file.path(Sys.getenv("TAPADOSPRI_OUTPUT_DIR", file.path(db_root, "output")), "slides", "descriptives")
dir.create(FIG, recursive = TRUE, showWarnings = FALSE)
ACC <- "#940034"; INK <- "#18181b"; Z3 <- "#d4d4d8"; Z4 <- "#a1a1aa"; Z5 <- "#71717a"; Z6 <- "#52525b"
FONT <- "Helvetica"; W <- 10; H <- 5.2; ANN <- 4.1
theme_slide <- function() theme_classic(base_size = 15, base_family = FONT) +
  theme(plot.background = element_rect(fill = "white", colour = NA), panel.background = element_rect(fill = "white", colour = NA),
        axis.line = element_line(colour = Z4, linewidth = 0.35), axis.ticks = element_line(colour = Z4, linewidth = 0.35),
        axis.ticks.length = unit(3, "pt"), axis.text = element_text(colour = Z6, size = 12.5), axis.title = element_text(colour = INK, size = 14),
        axis.title.x = element_text(margin = margin(t = 8)), axis.title.y = element_text(margin = margin(r = 8)),
        plot.caption = element_text(colour = Z5, size = 10, hjust = 0, margin = margin(t = 10)),
        plot.caption.position = "plot", legend.position = "none", plot.margin = margin(12, 16, 8, 10))
m <- fread(file.path(TB, "gwf_spells_benchmark_2025.csv"))[in_main == 1]
stopifnot(nrow(m) == 280)
mex <- m[grepl("^Mexico 29", gwf_casename)]
fit <- survfit(Surv(n_gwf_regular25 + 0.5, event25) ~ 1, data = m)
S <- function(k) { s <- summary(fit, times = k, extend = TRUE)$surv; if (length(s)) s else 1 }
KMAX <- 14
cv <- data.table(k = 0:KMAX)[, surv := sapply(k, S)]
y_mex <- S(mex$n_gwf_regular25)
# labelled regimes: name, GWF case; several at the same count share one label
lab <- data.table(case = c("South Africa 10-94", "Vietnam 54-NA", "Saudi Arabia 27-NA", "Soviet Union 17-91", "China 49-NA",
                           "Yugoslavia 45-90", "Singapore 65-NA", "Cuba 59-NA", "Korea North 48-NA", "Taiwan 49-00", "Spain 39-76"),
                  name = c("South Africa 1910-94", "Vietnam", "Saudi Arabia", "USSR", "China", "Yugoslavia", "Singapore", "Cuba",
                           "North Korea", "Taiwan (KMT)", "Franco's Spain"))
lab <- merge(lab, m[, .(case = gwf_casename, k = n_gwf_regular25, alive = event25 == 0)], by = "case")
stopifnot(nrow(lab) == 11)
lab[, nm := paste0(name, fifelse(alive, "+", ""))]
L <- lab[, .(txt = paste(nm, collapse = ", ")), by = k][, y := sapply(k, S)][order(k)]
# k = 1, 2 labelled next to their step; k >= 3 in a column to the right with leader lines (nested, non-crossing)
L[, `:=`(tx = k + 0.08, ty = y + 0.035, inline = k <= 2)]
col <- L[inline == FALSE][order(k)]; col[, ty := 0.38 - 0.05 * (seq_len(.N) - 1)]; col[, tx := 9.3]
L <- rbind(L[inline == TRUE], col)
p <- ggplot(cv, aes(k, surv)) +
  geom_step(colour = Z4, linewidth = 0.75, direction = "hv") +
  geom_segment(data = L[inline == FALSE], aes(x = k, xend = tx - 0.1, y = y + 0.008, yend = ty), colour = Z3, linewidth = 0.3) +
  geom_point(data = L, aes(k, y), colour = Z5, size = 1.6) +
  geom_text(data = L[inline == TRUE], aes(tx, ty, label = txt), hjust = 0, vjust = 0, family = FONT, size = ANN - 0.5, colour = Z5) +
  geom_text(data = L[inline == FALSE], aes(tx, ty, label = txt), hjust = 0, vjust = 0.5, family = FONT, size = ANN - 0.5, colour = Z5) +
  annotate("segment", x = mex$n_gwf_regular25, xend = mex$n_gwf_regular25, y = y_mex + 0.02, yend = 0.50, colour = ACC, linewidth = 0.45) +
  annotate("point", x = mex$n_gwf_regular25, y = y_mex, colour = ACC, size = 3) +
  annotate("text", x = mex$n_gwf_regular25 - 0.15, y = 0.50, hjust = 1, vjust = 1, family = FONT, size = ANN - 0.3, colour = ACC, fontface = "bold",
           label = sprintf("Mexico (PRI), 1929-2000: %d successions", mex$n_gwf_regular25)) +
  annotate("text", x = mex$n_gwf_regular25 - 0.15, y = 0.455, hjust = 1, vjust = 1, family = FONT, size = ANN - 0.6, colour = ACC, lineheight = 1.05,
           label = sprintf("no other autocracy got past %d", max(m[!grepl("^Mexico", gwf_casename), n_gwf_regular25]))) +
  scale_x_continuous("Regular leader successions", limits = c(0, KMAX), breaks = 0:KMAX, expand = expansion(mult = c(0, 0.01))) +
  scale_y_continuous("Share of regimes still in power", limits = c(0, 1), breaks = seq(0, 1, 0.25),
                     labels = function(b) paste0(round(100 * b), "%"), expand = expansion(mult = c(0, 0.02))) +
  labs(caption = "Source: Geddes, Wright & Frantz (2014), Archigos; extended to 2025. Kaplan-Meier; + = still in power in 2025 (censored).") +
  theme_slide()
pdf_dev <- function(filename, width, height, ...) grDevices::pdf(filename, width = width, height = height, family = FONT, encoding = "WinAnsi.enc", useDingbats = FALSE)
f <- file.path(FIG, "autocracy_survival_successions.pdf")
ggsave(f, p, width = W, height = H, device = pdf_dev); embedFonts(f, options = "-dPDFSETTINGS=/prepress")
ggsave(file.path(FIG, "autocracy_survival_successions.png"), p, width = W, height = H, dpi = 300, device = ragg::agg_png, bg = "white")
print(cv); print(L)
