# =============================================================================
# 07_networks.R
# Network analysis for Mexican political elite
#
# Design revision:
#   - Use the same eras as 06_descriptive_stats.R
#   - Avoid full hairball graphs
#   - Export one reduced, readable network per era / view
#
# Outputs:
#   output/network_education_<era>.png
#   output/network_government_<era>.png
#   output/network_biographical_<era>.png
#   output/network_hierarchy_<era>.png
# =============================================================================

library(tidyverse)
library(igraph)
library(ggraph)
library(tidygraph)
library(scales)
library(grid)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DB_ROOT <- Sys.getenv("TAPADOSPRI_DB_ROOT", unset = "C:/Users/Dell/Dropbox/TapadosPRI")
DATA_DIR <- Sys.getenv("TAPADOSPRI_DATA_DIR", unset = file.path(DB_ROOT, "data"))
OUTPUT_DIR <- Sys.getenv("TAPADOSPRI_OUTPUT_DIR", unset = file.path(DB_ROOT, "output"))
dir.create(OUTPUT_DIR, showWarnings = FALSE)

# ---------------------------------------------------------------------------
# Era definitions (aligned with 06_descriptive_stats.R)
# ---------------------------------------------------------------------------
ERAS <- list(
  corporatism = c(1929, 1945),
  pri_hege    = c(1946, 1999),
  democracy   = c(2000, 2012)
)

ERA_LABELS <- c(
  corporatism = "Corporatism (1929-45)",
  pri_hege    = "PRI Hegemony (1946-99)",
  democracy   = "Democracy (2000-12)"
)

PARTY_COLORS <- c(
  "PRI/PRM/PNR" = "#27AE60",
  "PAN" = "#2980B9",
  "PRD" = "#F39C12"
)

GOVT_RANK_ORDER <- c(
  secretary = 1, governor = 2, secretary_general = 3,
  director_general = 4, assistant_secretary = 5, oficial_mayor = 6,
  ambassador = 7, head = 8, director = 9, judge = 10, justice = 11,
  coordinator = 12, adviser = 13, assistant_director = 14,
  assistant = 15, other = 99
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
theme_net <- function() {
  theme_void(base_size = 12) +
    theme(
      plot.title = element_text(face = "bold", size = 14, hjust = 0.5),
      plot.subtitle = element_text(color = "grey35", size = 11, hjust = 0.5),
      plot.caption = element_text(color = "grey45", size = 9, hjust = 1),
      legend.position = "bottom",
      legend.title = element_text(size = 10),
      legend.text = element_text(size = 9)
    )
}

save_network_plot <- function(plot_obj, filename, width = 13, height = 9) {
  out_path <- file.path(OUTPUT_DIR, filename)
  ggsave(out_path, plot = plot_obj, width = width, height = height,
         units = "in", dpi = 300, bg = "white")
  cat("  Saved:", out_path, "\n")
}

save_placeholder_plot <- function(filename, title_text, body_text) {
  p <- ggplot() +
    annotate("text", x = 0.5, y = 0.58, label = title_text,
             size = 7, fontface = "bold", color = "#2C3E50") +
    annotate("text", x = 0.5, y = 0.42, label = body_text,
             size = 5, color = "grey40") +
    coord_cartesian(xlim = c(0, 1), ylim = c(0, 1), expand = FALSE) +
    theme_void()

  save_network_plot(p, filename, width = 10, height = 7)
}

slug <- function(x) {
  x |>
    str_replace_all("[^a-z0-9]+", "_") |>
    str_replace_all("^_|_$", "")
}

normalize_name <- function(x) {
  x <- tolower(x)
  x <- iconv(x, from = "UTF-8", to = "ASCII//TRANSLIT")
  x <- str_remove_all(x, "\\(deceased[^)]*\\)")
  x <- str_replace_all(x, "\\(([^)]+)\\)", "\\1")
  x <- str_remove_all(x, "[^a-z ]")
  str_squish(x)
}

make_era_panel <- function(df, year_col = "year_start", eras = ERAS) {
  map_dfr(names(eras), function(e) {
    lo <- eras[[e]][1]
    hi <- eras[[e]][2]
    df |>
      filter(!is.na(.data[[year_col]]), .data[[year_col]] >= lo, .data[[year_col]] <= hi) |>
      mutate(era = e)
  })
}

filter_graph_vertices <- function(vertices, require_known_era = FALSE) {
  out <- vertices |>
    filter(
      !is.na(person_id),
      !is.na(person_name),
      party_group %in% names(PARTY_COLORS)
    )

  if (require_known_era) {
    out <- out |> filter(!is.na(era))
  }

  out
}

filter_edges_to_vertices <- function(edges, vertices) {
  valid_ids <- as.character(vertices$person_id)
  edges |>
    filter(
      as.character(from) %in% valid_ids,
      as.character(to) %in% valid_ids
    )
}

build_cooccurrence_edges <- function(df,
                                     group_col = "organization",
                                     id_col = "person_id",
                                     start_col = "year_start",
                                     end_col = "year_end",
                                     min_size = 3,
                                     size_penalty_power = 0.35) {
  df_grp <- df |>
    filter(
      !is.na(.data[[group_col]]),
      str_trim(as.character(.data[[group_col]])) != ""
    ) |>
    group_by(.data[[group_col]]) |>
    filter(n_distinct(.data[[id_col]]) >= min_size) |>
    ungroup() |>
    group_by(.data[[id_col]], .data[[group_col]]) |>
    summarise(
      yr_start = suppressWarnings(min(.data[[start_col]], na.rm = TRUE)),
      yr_end   = suppressWarnings(max(.data[[end_col]], na.rm = TRUE)),
      .groups = "drop"
    ) |>
    mutate(
      yr_start = if_else(is.infinite(yr_start), NA_real_, yr_start),
      yr_end   = if_else(is.infinite(yr_end), NA_real_, yr_end)
    )

  group_sizes <- df_grp |>
    count(inst = .data[[group_col]], name = "group_size")

  left_tbl <- df_grp |> rename(pa = 1, inst = 2, sa = yr_start, ea = yr_end)
  right_tbl <- df_grp |> rename(pb = 1, inst = 2, sb = yr_start, eb = yr_end)

  edges_raw <- inner_join(left_tbl, right_tbl, by = "inst", relationship = "many-to-many") |>
    left_join(group_sizes, by = "inst") |>
    filter(pa < pb) |>
    mutate(
      both_have_years = !is.na(sa) & !is.na(sb),
      overlap = both_have_years &
        coalesce(sa, -Inf) <= coalesce(eb, Inf) &
        coalesce(sb, -Inf) <= coalesce(ea, Inf),
      base_weight = case_when(
        overlap ~ 1.0,
        !both_have_years ~ 0.5,
        TRUE ~ 0.0
      ),
      size_penalty = 1 / pmax(1, (group_size - min_size + 1)^size_penalty_power),
      weight = base_weight * size_penalty,
      institution = inst
    ) |>
    filter(weight > 0)

  edges_raw |>
    group_by(from = pa, to = pb) |>
    summarise(
      weight = pmin(sum(weight), 3.0),
      n_shared = n(),
      institutions = paste(head(sort(unique(institution)), 3), collapse = "; "),
      .groups = "drop"
    )
}

prepare_graph <- function(edges,
                          vertices,
                          directed = FALSE,
                          top_n_nodes = 50,
                          edge_quantile = 0.8,
                          min_component_size = 3) {
  if (nrow(edges) == 0 || nrow(vertices) < 2) {
    return(NULL)
  }

  edges <- filter_edges_to_vertices(edges, vertices)
  if (nrow(edges) == 0) {
    return(NULL)
  }

  edge_cutoff <- quantile(edges$weight, edge_quantile, na.rm = TRUE)
  edges_backbone <- edges |>
    filter(weight >= edge_cutoff)

  if (nrow(edges_backbone) == 0) {
    edges_backbone <- edges |>
      slice_max(order_by = weight, n = min(40, n()))
  }

  node_scores <- bind_rows(
    edges_backbone |> transmute(person_id = from, score = weight),
    edges_backbone |> transmute(person_id = to, score = weight)
  ) |>
    group_by(person_id) |>
    summarise(weighted_degree = sum(score), .groups = "drop") |>
    slice_max(weighted_degree, n = top_n_nodes, with_ties = FALSE)

  vertices_keep <- vertices |>
    filter(as.character(person_id) %in% as.character(node_scores$person_id))

  edges_keep <- filter_edges_to_vertices(edges_backbone, vertices_keep)
  if (nrow(edges_keep) == 0 || nrow(vertices_keep) < 2) {
    return(NULL)
  }

  graph_obj <- graph_from_data_frame(
    d = edges_keep,
    directed = directed,
    vertices = vertices_keep
  )

  graph_obj <- delete_vertices(graph_obj, V(graph_obj)[degree(graph_obj, mode = "all") == 0])
  if (vcount(graph_obj) < 2 || ecount(graph_obj) == 0) {
    return(NULL)
  }

  comps <- components(as.undirected(graph_obj, mode = "collapse"))
  keep_ids <- which(comps$csize >= min_component_size)
  if (length(keep_ids) == 0) {
    keep_ids <- which.max(comps$csize)
  }
  graph_obj <- induced_subgraph(graph_obj, vids = V(graph_obj)[comps$membership %in% keep_ids])

  if (vcount(graph_obj) < 2 || ecount(graph_obj) == 0) {
    return(NULL)
  }

  graph_obj <- set_vertex_attr(graph_obj, "degree", value = degree(graph_obj, mode = "all"))

  label_ids <- tibble(
    node_name = V(graph_obj)$name,
    degree = degree(graph_obj, mode = "all")
  ) |>
    arrange(desc(degree), node_name) |>
    slice_head(n = 15) |>
    pull(node_name)

  list(
    graph = graph_obj,
    tbl = as_tbl_graph(graph_obj),
    label_ids = label_ids
  )
}

plot_force_network <- function(prepped,
                               title_text,
                               subtitle_text,
                               node_color_var = "party_group",
                               node_color_values = PARTY_COLORS,
                               color_legend = "Party affiliation",
                               edge_color = "grey65",
                               width = 13,
                               height = 9) {
  if (is.null(prepped)) {
    return(NULL)
  }

  set.seed(42)
  p <- ggraph(prepped$tbl, layout = "fr") +
    geom_edge_link(aes(alpha = weight, width = weight),
                   color = edge_color, show.legend = FALSE) +
    geom_node_point(aes(color = .data[[node_color_var]], size = node_size), alpha = 0.9) +
    geom_node_text(
      aes(label = if_else(name %in% prepped$label_ids, person_name, NA_character_)),
      size = 2.7, repel = TRUE, max.overlaps = 25, fontface = "italic"
    ) +
    scale_color_manual(values = node_color_values, name = color_legend, drop = TRUE) +
    scale_size_continuous(range = c(2, 7), guide = "none") +
    scale_edge_width_continuous(range = c(0.3, 1.5)) +
    scale_edge_alpha_continuous(range = c(0.2, 0.75)) +
    labs(
      title = title_text,
      subtitle = subtitle_text,
      caption = "Backbone network: strongest edges, top nodes, and non-trivial components only"
    ) +
    guides(color = guide_legend(override.aes = list(size = 4), nrow = 1)) +
    theme_net()

  list(plot = p, width = width, height = height)
}

plot_hierarchy_network <- function(prepped, title_text, subtitle_text) {
  if (is.null(prepped)) {
    return(NULL)
  }

  set.seed(42)
  p <- ggraph(prepped$tbl, layout = "stress") +
    geom_edge_link(aes(width = n_inferences, alpha = n_inferences),
                   arrow = arrow(length = unit(3, "mm"), type = "closed"),
                   end_cap = circle(3, "mm"),
                   color = "#2C3E50", show.legend = FALSE) +
    geom_node_point(aes(color = party_group, size = node_size), alpha = 0.92) +
    geom_node_text(
      aes(label = if_else(name %in% prepped$label_ids, person_name, NA_character_)),
      size = 2.6, repel = TRUE, max.overlaps = 25, fontface = "italic"
    ) +
    scale_color_manual(values = PARTY_COLORS, name = "Party", drop = TRUE) +
    scale_size_continuous(range = c(2, 7), guide = "none") +
    scale_edge_width_continuous(range = c(0.35, 1.6)) +
    scale_edge_alpha_continuous(range = c(0.25, 0.85)) +
    labs(
      title = title_text,
      subtitle = subtitle_text,
      caption = "Directed backbone only; strongest inferred senior-junior ties retained"
    ) +
    guides(color = guide_legend(override.aes = list(size = 4), nrow = 1)) +
    theme_net()

  list(plot = p, width = 13, height = 9)
}

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
cat("Loading data...\n")

edu_long    <- read_csv(file.path(DATA_DIR, "education.csv"), show_col_types = FALSE)
govt_long   <- read_csv(file.path(DATA_DIR, "govt_positions.csv"), show_col_types = FALSE) |>
  mutate(is_federal = is_federal %in% c(TRUE, "True", "TRUE"))
party_wide  <- read_csv(file.path(DATA_DIR, "party_positions_wide.csv"), show_col_types = FALSE)
govt_wide   <- read_csv(file.path(DATA_DIR, "govt_positions_wide.csv"), show_col_types = FALSE) |>
  mutate(across(starts_with("ever_"), ~ .x %in% c(TRUE, "True", "TRUE")))
connections <- read_csv(file.path(DATA_DIR, "parsed_connections.csv"), show_col_types = FALSE)

# ---------------------------------------------------------------------------
# Shared nodes
# ---------------------------------------------------------------------------
nodes_base <- bind_rows(
  select(edu_long, person_id, person_name),
  select(govt_long, person_id, person_name)
) |>
  distinct(person_id, .keep_all = TRUE) |>
  left_join(
    select(
      party_wide, person_id, pri_member, pan_member, prd_member,
      primary_party, n_party_positions = n_party_positions
    ),
    by = "person_id"
  ) |>
  left_join(
    select(
      govt_wide, person_id, n_govt_positions, ever_secretary,
      ever_governor, highest_rank
    ),
    by = "person_id"
  ) |>
  mutate(
    party_group = case_when(
      coalesce(pri_member, 0) == 1 ~ "PRI/PRM/PNR",
      coalesce(pan_member, 0) == 1 ~ "PAN",
      coalesce(prd_member, 0) == 1 ~ "PRD",
      TRUE                         ~ "Other/Unknown"
    ),
    node_size = log1p(coalesce(n_govt_positions, 0)) + 1
  )

name_lookup <- nodes_base |>
  mutate(name_norm = normalize_name(person_name)) |>
  select(person_id, name_norm)

# ---------------------------------------------------------------------------
# Era panels
# ---------------------------------------------------------------------------
edu_era <- edu_long |>
  filter(record_type == "degree", !is.na(organization), str_trim(organization) != "") |>
  make_era_panel("year_end")

govt_era <- govt_long |>
  filter(is_federal == TRUE, !is.na(secretariat_norm), str_trim(secretariat_norm) != "") |>
  make_era_panel("year_start")

era_assign <- govt_era |>
  group_by(person_id, era) |>
  summarise(first_govt_yr = min(year_start), .groups = "drop") |>
  mutate(
    era_label = case_when(
      era == "corporatism" ~ "Corporatism",
      era == "pri_hege" ~ "PRI Hegemony",
      era == "democracy" ~ "Democracy",
      TRUE ~ NA_character_
    )
  )

conn_edges_matched <- connections |>
  mutate(
    a_norm = normalize_name(person_a),
    b_norm = normalize_name(person_b)
  ) |>
  left_join(name_lookup, by = c("a_norm" = "name_norm")) |>
  rename(id_a = person_id) |>
  left_join(name_lookup, by = c("b_norm" = "name_norm")) |>
  rename(id_b = person_id) |>
  filter(!is.na(id_a), !is.na(id_b), id_a != id_b)

persons_by_era <- bind_rows(
  edu_era |> select(person_id, era),
  govt_era |> select(person_id, era)
) |>
  distinct()

# ---------------------------------------------------------------------------
# Education networks by era
# ---------------------------------------------------------------------------
cat("Building education networks by era...\n")

for (era_name in names(ERAS)) {
  cat(" Era:", era_name, "\n")

  edu_df <- edu_era |> filter(era == era_name)
  edu_edges <- build_cooccurrence_edges(
    edu_df,
    group_col = "organization",
    id_col = "person_id",
    start_col = "year_start",
    end_col = "year_end",
    min_size = 4
  )

  edu_vertices <- nodes_base |>
    filter(person_id %in% c(edu_edges$from, edu_edges$to)) |>
    select(person_id, person_name, party_group, node_size) |>
    filter_graph_vertices()

  edu_prepped <- prepare_graph(
    edges = edu_edges,
    vertices = edu_vertices,
    directed = FALSE,
    top_n_nodes = 45,
    edge_quantile = 0.85,
    min_component_size = 4
  )

  if (is.null(edu_prepped)) {
    save_placeholder_plot(
      paste0("network_education_", era_name, ".png"),
      paste("Education Network -", ERA_LABELS[[era_name]]),
      "No readable education backbone for this era"
    )
  } else {
    edu_plot <- plot_force_network(
      edu_prepped,
      title_text = paste("Education Network -", ERA_LABELS[[era_name]]),
      subtitle_text = "Top nodes by weighted degree; strongest co-attendance edges only"
    )
    save_network_plot(edu_plot$plot, paste0("network_education_", era_name, ".png"),
                      width = edu_plot$width, height = edu_plot$height)
  }
}

# ---------------------------------------------------------------------------
# Government networks by era
# ---------------------------------------------------------------------------
cat("Building government networks by era...\n")

for (era_name in names(ERAS)) {
  cat(" Era:", era_name, "\n")

  govt_df <- govt_era |> filter(era == era_name)
  govt_edges <- build_cooccurrence_edges(
    govt_df,
    group_col = "secretariat_norm",
    id_col = "person_id",
    start_col = "year_start",
    end_col = "year_end",
    min_size = 4
  )

  govt_vertices <- nodes_base |>
    filter(person_id %in% c(govt_edges$from, govt_edges$to)) |>
    left_join(
      era_assign |>
        filter(era == era_name) |>
        select(person_id, era = era_label),
      by = "person_id"
    ) |>
    select(person_id, person_name, party_group, node_size, era) |>
    filter_graph_vertices(require_known_era = TRUE)

  govt_prepped <- prepare_graph(
    edges = govt_edges,
    vertices = govt_vertices,
    directed = FALSE,
    top_n_nodes = 50,
    edge_quantile = 0.88,
    min_component_size = 4
  )

  if (is.null(govt_prepped)) {
    save_placeholder_plot(
      paste0("network_government_", era_name, ".png"),
      paste("Government Network -", ERA_LABELS[[era_name]]),
      "No readable government backbone for this era"
    )
  } else {
    govt_plot <- plot_force_network(
      govt_prepped,
      title_text = paste("Government Network -", ERA_LABELS[[era_name]]),
      subtitle_text = "Top nodes by weighted co-service; strongest secretariat ties only",
      node_color_var = "era",
      node_color_values = c(
        "Corporatism" = "#C0392B",
        "PRI Hegemony" = "#27AE60",
        "Democracy" = "#2980B9"
      ),
      color_legend = "Era"
    )
    save_network_plot(govt_plot$plot, paste0("network_government_", era_name, ".png"),
                      width = govt_plot$width, height = govt_plot$height)
  }
}

# ---------------------------------------------------------------------------
# Biographical networks by era
# ---------------------------------------------------------------------------
cat("Building biographical networks by era...\n")

for (era_name in names(ERAS)) {
  cat(" Era:", era_name, "\n")

  era_persons <- persons_by_era |>
    filter(era == era_name) |>
    pull(person_id) |>
    as.character()

  conn_edges <- conn_edges_matched |>
    filter(
      as.character(id_a) %in% era_persons,
      as.character(id_b) %in% era_persons
    ) |>
    select(from = id_a, to = id_b, connection_type) |>
    filter(connection_type %in% c("family", "mentorship", "personal", "shared_government", "shared_education", "shared_party"))

  if (nrow(conn_edges) > 0) {
    conn_edges <- conn_edges |>
      mutate(weight = case_when(
        connection_type %in% c("family", "mentorship", "personal") ~ 1.5,
        TRUE ~ 1.0
      )) |>
      group_by(from, to) |>
      summarise(
        weight = sum(weight),
        connection_type = first(connection_type),
        .groups = "drop"
      )
  }

  conn_vertices <- nodes_base |>
    filter(person_id %in% c(conn_edges$from, conn_edges$to)) |>
    select(person_id, person_name, party_group, node_size) |>
    filter_graph_vertices()

  conn_prepped <- prepare_graph(
    edges = conn_edges,
    vertices = conn_vertices,
    directed = FALSE,
    top_n_nodes = 45,
    edge_quantile = 0.7,
    min_component_size = 3
  )

  if (is.null(conn_prepped)) {
    save_placeholder_plot(
      paste0("network_biographical_", era_name, ".png"),
      paste("Biographical Network -", ERA_LABELS[[era_name]]),
      "No readable biographical backbone for this era"
    )
  } else {
    conn_plot <- plot_force_network(
      conn_prepped,
      title_text = paste("Biographical Network -", ERA_LABELS[[era_name]]),
      subtitle_text = "Reduced to explicit and stronger relationship types within the era pool",
      edge_color = "grey55"
    )
    save_network_plot(conn_plot$plot, paste0("network_biographical_", era_name, ".png"),
                      width = conn_plot$width, height = conn_plot$height)
  }
}

# ---------------------------------------------------------------------------
# Hierarchy networks by era
# ---------------------------------------------------------------------------
cat("Building hierarchy networks by era...\n")

for (era_name in names(ERAS)) {
  cat(" Era:", era_name, "\n")

  govt_ranked <- govt_era |>
    filter(era == era_name) |>
    mutate(
      rank_order = {
        r <- GOVT_RANK_ORDER[rank]
        r[is.na(r)] <- 99L
        as.integer(r)
      }
    )

  hier_edges_raw <- govt_ranked |>
    select(pa = person_id, inst = secretariat_norm,
           ro_a = rank_order, sa = year_start, ea = year_end) |>
    inner_join(
      govt_ranked |>
        select(pb = person_id, inst = secretariat_norm,
               ro_b = rank_order, sb = year_start, eb = year_end),
      by = "inst"
    ) |>
    filter(
      pa != pb,
      ro_a < ro_b,
      (
        is.na(sa) | is.na(sb) | is.na(ea) | is.na(eb) |
          (coalesce(sa, -Inf) <= coalesce(eb, Inf) &
             coalesce(sb, -Inf) <= coalesce(ea, Inf))
      )
    )

  hier_edges <- hier_edges_raw |>
    count(from = pa, to = pb, wt = 1, name = "n_inferences") |>
    mutate(weight = n_inferences)

  hier_vertices <- nodes_base |>
    filter(person_id %in% c(hier_edges$from, hier_edges$to)) |>
    select(person_id, person_name, party_group, node_size) |>
    filter_graph_vertices()

  hier_prepped <- prepare_graph(
    edges = hier_edges,
    vertices = hier_vertices,
    directed = TRUE,
    top_n_nodes = 40,
    edge_quantile = 0.8,
    min_component_size = 3
  )

  if (is.null(hier_prepped)) {
    save_placeholder_plot(
      paste0("network_hierarchy_", era_name, ".png"),
      paste("Hierarchy Network -", ERA_LABELS[[era_name]]),
      "No readable hierarchy backbone for this era"
    )
  } else {
    hier_plot <- plot_hierarchy_network(
      hier_prepped,
      title_text = paste("Hierarchy Network -", ERA_LABELS[[era_name]]),
      subtitle_text = "Directed senior-to-junior ties within the era"
    )
    save_network_plot(hier_plot$plot, paste0("network_hierarchy_", era_name, ".png"),
                      width = hier_plot$width, height = hier_plot$height)
  }
}

cat("\nSaved era-based network files to:", OUTPUT_DIR, "\n")
