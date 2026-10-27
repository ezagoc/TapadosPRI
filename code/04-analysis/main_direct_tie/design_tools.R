# Shared tools for the section-4 estimator on any subsample, covariate set and succession weights, with the
# Ferman-Pinto contender-level bootstrap of section 5, and the house style for figures. Source after
# estimate_main.R (uses sample, formula_x, fit_variance_components).
suppressPackageStartupMessages(library(ggplot2))

formula_es <- ~ election_factor + age + ldeg + lrec + prior_status   # section 7: no rank bands

# Linear weights a_i of the estimator: mean residual of the designee's followers by succession (loser-only
# outcome model, weights 1/n0e), averaged with equal or person (designee's followers) succession weights.
build_design <- function(keep = rep(TRUE, nrow(sample)), formula = formula_x, weights = c("equal", "person")) {
  weights <- match.arg(weights)
  S <- sample[keep]
  tr <- S$treated == 1L
  el <- S$election
  es <- sort(unique(el))
  es <- es[sapply(es, function(e) any(tr & el == e) && any(!tr & el == e))]
  S <- S[election %in% es]
  tr <- S$treated == 1L; el <- S$election
  Xm <- model.matrix(formula, data = S)
  ctrl <- which(!tr)
  n0 <- table(el[ctrl])
  w0s <- 1 / as.numeric(n0[as.character(el[ctrl])])
  X0 <- Xm[ctrl, , drop = FALSE]
  keep_col <- colSums(abs(X0)) > 0
  X0 <- X0[, keep_col, drop = FALSE]
  Xm <- Xm[, keep_col, drop = FALSE]
  if (qr(X0 * sqrt(w0s))$rank != ncol(X0)) stop("Control model is rank-deficient on this subsample.")
  M <- solve(crossprod(X0, X0 * w0s))
  nT <- tapply(tr, el, sum)[as.character(es)]
  omega <- if (weights == "equal") rep(1 / length(es), length(es)) else as.numeric(nT) / sum(nT)
  names(omega) <- es
  b <- Reduce(`+`, lapply(es, function(e) omega[[as.character(e)]] * colMeans(Xm[tr & el == e, , drop = FALSE])))
  a <- numeric(nrow(S))
  a[ctrl] <- -w0s * as.vector(X0 %*% (M %*% b))
  for (e in es) { ix <- which(tr & el == e); a[ix] <- omega[[as.character(e)]] / length(ix) }
  cg <- unique(S$network[ctrl])
  Zc <- outer(S$network[ctrl], cg, "==") * 1
  Cc <- t(sweep(Zc, 2L, colSums(Zc), "/"))
  Q <- Cc - sweep((Cc %*% X0) %*% M %*% t(X0), 2L, w0s, "*")
  net <- data.table(network = S$network, a = a)[, .(g = sum(a), wsq = sum(a^2)), by = network]
  list(S = S, rows = which(keep)[sample$election[keep] %in% es], X = Xm, X0 = X0, M = M, a = a, ctrl = ctrl,
       w0 = w0s, Q = Q, moments = cbind(rowSums((Q %*% Zc)^2), rowSums(Q^2)), g = net$g,
       n_eff = net$g^2 / net$wsq, K = length(cg), omega = omega, elections = es)
}

# y must be aligned with d$S (use y_full[d$rows]).
residuals_d <- function(d, y) {
  beta_y <- as.vector(d$M %*% crossprod(d$X0, d$w0 * y[d$ctrl]))
  y - as.vector(d$X %*% beta_y)
}
by_succession_d <- function(d, y) {
  data.table(election = d$S$election, treated = d$S$treated, r = residuals_d(d, y))[
    treated == 1L, .(estimate = mean(r), n_designee = .N), by = election]
}

# Joint bootstrap errors for the columns of Ym (one donor contender group per slot and draw, shared
# across columns). Returns the error draws and the fitted variance components.
boot_errors <- function(d, Ym, B = 50000L, seed = 17102026L) {
  Ym <- as.matrix(Ym)
  set.seed(seed)
  idx <- matrix(base::sample.int(d$K, length(d$g) * B, replace = TRUE), nrow = length(d$g))
  err <- matrix(0, nrow = ncol(Ym), ncol = B, dimnames = list(colnames(Ym), NULL))
  comps <- vector("list", ncol(Ym))
  for (j in seq_len(ncol(Ym))) {
    r_y <- as.vector(d$Q %*% Ym[d$ctrl, j])
    if (all(abs(r_y) < 1e-12)) next
    ab <- fit_variance_components(r_y, d$moments)
    z <- r_y / sqrt(pmax(as.vector(d$moments %*% ab), .Machine$double.eps))
    z <- (z - mean(z)) / sd(z)
    err[j, ] <- colSums(d$g * sqrt(ab[1] + ab[2] / d$n_eff) * matrix(z[idx], nrow = nrow(idx)))
    comps[[j]] <- data.table(column = colnames(Ym)[j], A = ab[1], B = ab[2])
  }
  list(err = err, components = rbindlist(comps))
}

ci_from <- function(est, e, level = .95) {
  q <- as.numeric(quantile(e, c((1 - level) / 2, 1 - (1 - level) / 2), type = 1, names = FALSE))
  c(lower = est - q[2], upper = est - q[1])
}

# Estimates, 95% and 90% intervals and bootstrap p for every column of Ym on design d.
estimate_columns <- function(d, Ym, B = 50000L, seed = 17102026L) {
  Ym <- as.matrix(Ym)
  est <- as.vector(crossprod(d$a, Ym))
  be <- boot_errors(d, Ym, B, seed)
  out <- rbindlist(lapply(seq_len(ncol(Ym)), function(j) {
    ci <- ci_from(est[j], be$err[j, ], .95); ci90 <- ci_from(est[j], be$err[j, ], .90)
    data.table(column = colnames(Ym)[j], estimate = est[j], ci_lower = ci[[1]], ci_upper = ci[[2]],
               ci90_lower = ci90[[1]], ci90_upper = ci90[[2]], p_bootstrap = mean(abs(be$err[j, ]) >= abs(est[j])),
               n = nrow(d$S), n_designee = sum(d$S$treated))
  }))
  list(table = out, err = be$err, components = be$components)
}

# Annual outcome helpers on the full analysis sample.
year_value <- function(tab, k, value = "rank") {
  z <- tab[data.table(pid = sample$pid, year = sample$election + k), on = .(pid, year), get(value)]
  z[is.na(z)] <- 0
  z
}

# ------------------------------------------------------------------ house style (Econometrica-like)
INK <- "#1a1a1a"; MUTED <- "#666666"; RULE <- "#b3b3b3"; FAM <- "Helvetica"
theme_paper <- function(base = 15) theme_classic(base_size = base, base_family = FAM) +
  theme(axis.line = element_line(colour = INK, linewidth = 0.35), axis.ticks = element_line(colour = INK, linewidth = 0.35),
        axis.text = element_text(colour = INK, size = base - 2), axis.title = element_text(colour = INK, size = base - 1),
        strip.background = element_blank(), strip.text = element_text(colour = INK, size = base - 1, hjust = 0),
        plot.background = element_rect(fill = "white", colour = NA), legend.position = "none",
        plot.margin = margin(10, 14, 6, 6))
x_label_k <- "Years relative to the election"
k_labels <- function(x) ifelse(x == 0, "e", ifelse(x > 0, paste0("e+", x), paste0("e−", abs(x))))
k_labels_ascii <- function(x) ifelse(x == 0, "e", ifelse(x > 0, paste0("e+", x), paste0("e-", abs(x))))
k_numbers <- function(x) as.character(x)

# Event-study figure: points with 95% intervals, reference year hollow, vertical rules at designation
# (between e-2 and e-1), the new president's inauguration (1 Dec of e) and the next one (1 Dec of e+6).
es_figure <- function(d, ylab, file, scale = 1, out = out_dir, width = 10, height = 4.1, marks = TRUE,
                      facet = NULL, base = 17, ysize = 14, summary = NULL) {
  d <- copy(d)
  d[, `:=`(est = scale * estimate, lo = scale * ci_lower, hi = scale * ci_upper)]
  if (!"ci90_lower" %in% names(d)) d[, `:=`(ci90_lower = ci_lower, ci90_upper = ci_upper)]
  d[, `:=`(lo90 = scale * ci90_lower, hi90 = scale * ci90_upper)]
  ref_k <- d[estimate == 0 & ci_lower == 0 & ci_upper == 0, k]
  top <- max(d$hi, na.rm = TRUE); bot <- min(d$lo, na.rm = TRUE)
  span <- top - bot
  g <- ggplot(d, aes(k, est)) +
    geom_hline(yintercept = 0, colour = RULE, linewidth = 0.35)
  # Optional summary of a stretch of years, drawn under the estimates: a soft band for its interval and a dashed
  # line at the average over k0..k1 (the label is added last, below the points).
  if (!is.null(summary)) {
    if (!is.null(summary$lo))
      g <- g + annotate("rect", xmin = summary$k0 - 0.45, xmax = summary$k1 + 0.45, ymin = scale * summary$lo,
                        ymax = scale * summary$hi, fill = "#940034", alpha = 0.10)
    g <- g + annotate("segment", x = summary$k0 - 0.45, xend = summary$k1 + 0.45, y = scale * summary$est,
                      yend = scale * summary$est, colour = "#940034", linewidth = 1.1, linetype = "dashed")
  }
  if (marks) {
    mk <- data.table(x = c(-1.5, 0.5, 6.5), lab = c("Designation", "New president", "Next president"))
    g <- g + geom_vline(data = mk, aes(xintercept = x), colour = RULE, linewidth = 0.35, linetype = "dashed") +
      geom_text(data = mk, aes(x = x + 0.12, y = top + 0.10 * span, label = lab), hjust = 0, vjust = 0,
                colour = MUTED, size = base * 0.25, family = FAM)
  }
  g <- g + geom_linerange(aes(ymin = lo, ymax = hi), colour = INK, linewidth = 0.45) +
    geom_linerange(aes(ymin = lo90, ymax = hi90), colour = INK, linewidth = 1.5) +
    geom_point(data = d[!(k %in% ref_k)], colour = INK, size = 2.4) +
    geom_point(data = d[k %in% ref_k], shape = 21, fill = "white", colour = INK, size = 2.4, stroke = 0.7) +
    scale_x_continuous(breaks = sort(unique(d$k)), labels = k_numbers) +
    coord_cartesian(ylim = c(bot - 0.03 * span, top + 0.20 * span), clip = "off") +
    labs(x = x_label_k, y = ylab) + theme_paper(base) +
    theme(axis.title.y = element_text(size = ysize, lineheight = 0.95))
  # The summary's label, below the points.
  if (!is.null(summary)) {
    g <- g + annotate("text", x = (summary$k0 + summary$k1) / 2, y = bot + 0.04 * span, label = summary$label,
               colour = "#940034", size = base * 0.25, family = FAM, vjust = 0, lineheight = 0.9)
  }
  if (!is.null(facet)) g <- g + facet_wrap(as.formula(paste("~", facet)), nrow = 1, scales = "free_y")
  ggsave(file.path(out, paste0(file, ".pdf")), g, width = width, height = height, bg = "white", device = "pdf")
  ggsave(file.path(out, paste0(file, ".png")), g, width = width, height = height, dpi = 250, bg = "white")
  invisible(g)
}
