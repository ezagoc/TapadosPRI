# Draw the deck's event-study figures from figures.R (es_rank, es_extensive, es_intensive, es_reward_punishment) by
# evaluating only the blocks of figures.R that the deck uses: figures.R also draws figures of the paper's appendix whose
# inputs (thresholds, budget, chair split, placebos, camp sizes) the slides pipeline does not produce. Run after
# event_study.R, margins.R and reward_punishment.R:  Rscript slides/analysis/figures_deck.R
args <- commandArgs(FALSE)
here <- dirname(normalizePath(sub("^--file=", "", args[grepl("^--file=", args)][1])))
script_dir <- here
expressions <- parse(file.path(script_dir, "figures.R"))
lhs <- function(x) if (is.call(x) && identical(x[[1]], as.name("<-")) && is.symbol(x[[2]])) as.character(x[[2]]) else ""
names <- vapply(expressions, lhs, "")
pos <- function(n) { i <- which(names == n); stopifnot(length(i) == 1); i }
# blocks: setup and es_rank (up to the thresholds block `rb`), the margins block (`mg` up to the budget block `bg`),
# the reward/penalty block (`es` up to the chair-split block `cs`)
indices <- c(seq_len(pos("rb") - 1L), seq.int(pos("mg"), pos("bg") - 1L), seq.int(pos("es"), pos("cs") - 1L))
indices <- indices[!(names[indices] %in% c("args", "script_dir"))]
for (i in indices) eval(expressions[[i]], .GlobalEnv)
cat("Wrote es_rank, es_extensive, es_intensive and es_reward_punishment (pdf, png) to", out_dir, "\n")
