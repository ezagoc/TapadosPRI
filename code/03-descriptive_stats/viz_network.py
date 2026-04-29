"""
Visualization 1: Network graph showing connections between presidential candidates
(winner vs closest loser) and their political networks.

Showcase: 1988 election — Carlos Salinas de Gortari vs Manuel Bartlett Díaz
"""

import pandas as pd
import networkx as nx
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
from collections import Counter
import sys
from config import PARSED_CONNECTIONS_CSV, OUTPUT_DIR, normalize_name, DATA_DIR

# ---------------------------------------------------------------------------
# Configuration — can be overridden via command line
# ---------------------------------------------------------------------------
PRESETS = {
    1988: {
        "winner": "salinas de gortari, carlos",
        "loser": "Bartlett (díaz), Manuel",
        "conn_file": PARSED_CONNECTIONS_CSV,
    },
    1994: {
        "winner": "zedillo Ponce de léon, ernesto",
        "loser": "gutiérrez Barrios, fernando (Deceased Oct. 30, 2000)",
        "conn_file": DATA_DIR / "parsed_connections_1994.csv",
    },
}

ELECTION_YEAR = int(sys.argv[1]) if len(sys.argv) > 1 else 1988
preset = PRESETS[ELECTION_YEAR]
WINNER = preset["winner"]
LOSER = preset["loser"]
CONN_FILE = preset["conn_file"]

# Edge colors by connection type
CONN_COLORS = {
    "family": "#E63946",
    "mentorship": "#FF9F1C",
    "personal": "#FFD166",
    "shared_government": "#457B9D",
    "shared_education": "#2A9D8F",
    "shared_party": "#9B5DE5",
    "shared_public_office": "#00BBF9",
    "shared_labor": "#6C757D",
    "shared_other": "#ADB5BD",
    "birthplace_contemporary": "#BFBFBF",
}

CONN_LABELS = {
    "family": "Family",
    "mentorship": "Mentorship",
    "personal": "Personal",
    "shared_government": "Shared Government",
    "shared_education": "Shared Education",
    "shared_party": "Shared Party",
    "shared_public_office": "Shared Public Office",
    "shared_labor": "Shared Labor",
    "shared_other": "Shared Other",
    "birthplace_contemporary": "Birthplace Contemporary",
}


def short_name(full_name: str) -> str:
    """Convert CSV name format to readable short name."""
    # "salinas de gortari, carlos" -> "C. Salinas de Gortari"
    if "," in full_name:
        parts = full_name.split(",", 1)
        last = parts[0].strip()
        first = parts[1].strip() if len(parts) > 1 else ""
        # Clean parenthetical maternal surname
        import re
        last_clean = re.sub(r"\s*\([^)]*\)", "", last)
        # Fix odd capitalization
        last_clean = last_clean.title()
        first_clean = first.title()
        initial = first_clean[0] + "." if first_clean else ""
        return f"{initial} {last_clean}".strip()
    return full_name.title()


def build_network_graph():
    """Build and render the network visualization."""
    print("Loading connections...")
    conn_df = pd.read_csv(CONN_FILE)
    print(f"  {len(conn_df)} total connections")

    # Filter to connections involving winner or loser
    mask = (
        (conn_df["person_a"] == WINNER) | (conn_df["person_b"] == WINNER) |
        (conn_df["person_a"] == LOSER) | (conn_df["person_b"] == LOSER)
    )
    conn_df = conn_df[mask].copy()
    print(f"  {len(conn_df)} connections involving candidates")

    # Prioritize interesting connection types — drop birthplace_contemporary
    # if person has stronger connections
    strong_types = {"family", "mentorship", "personal", "shared_government",
                    "shared_education", "shared_party", "shared_public_office"}

    # Count connections per person (excluding birthplace)
    person_conns = Counter()
    person_strong = set()
    for _, row in conn_df.iterrows():
        other = row["person_b"] if row["person_a"] in (WINNER, LOSER) else row["person_a"]
        person_conns[other] += 1
        if row["connection_type"] in strong_types:
            person_strong.add(other)

    # Keep top N most connected people for readability
    TOP_N = 60
    top_people = {p for p, _ in person_conns.most_common(TOP_N)}
    top_people.add(WINNER)
    top_people.add(LOSER)

    # Filter connections to top people
    conn_filtered = conn_df[
        (conn_df["person_a"].isin(top_people)) & (conn_df["person_b"].isin(top_people))
    ].copy()

    # Build graph
    G = nx.Graph()
    G.add_node(WINNER)
    G.add_node(LOSER)

    edge_colors_list = []
    edge_types = []

    for _, row in conn_filtered.iterrows():
        a, b = row["person_a"], row["person_b"]
        ct = row["connection_type"]
        if not G.has_edge(a, b):
            G.add_edge(a, b, connection_types=[ct])
        else:
            G[a][b]["connection_types"].append(ct)

    # Determine node categories
    winner_neighbors = set(G.neighbors(WINNER)) - {LOSER}
    loser_neighbors = set(G.neighbors(LOSER)) - {WINNER}
    shared_neighbors = winner_neighbors & loser_neighbors
    winner_only = winner_neighbors - shared_neighbors
    loser_only = loser_neighbors - shared_neighbors

    print(f"\nNetwork stats:")
    print(f"  Total nodes: {G.number_of_nodes()}")
    print(f"  Total edges: {G.number_of_edges()}")
    print(f"  Winner-only connections: {len(winner_only)}")
    print(f"  Loser-only connections: {len(loser_only)}")
    print(f"  Shared connections: {len(shared_neighbors)}")

    # Layout — fix candidates at center, use spring for rest
    fixed_pos = {
        WINNER: (-0.6, 0),
        LOSER: (0.6, 0),
    }
    pos = nx.spring_layout(
        G, pos=fixed_pos, fixed=[WINNER, LOSER],
        k=0.3, iterations=100, seed=42,
    )

    # ---------------------------------------------------------------------------
    # Draw
    # ---------------------------------------------------------------------------
    fig, ax = plt.subplots(1, 1, figsize=(28, 20))
    fig.patch.set_facecolor("#FAFAFA")
    ax.set_facecolor("#FAFAFA")

    # Draw edges colored by primary connection type
    for u, v, data in G.edges(data=True):
        types = data.get("connection_types", [])
        # Pick the most "interesting" type as primary color
        priority = ["family", "mentorship", "personal", "shared_education",
                     "shared_government", "shared_party", "shared_public_office",
                     "shared_labor", "shared_other", "birthplace_contemporary"]
        primary = "birthplace_contemporary"
        for p in priority:
            if p in types:
                primary = p
                break

        color = CONN_COLORS.get(primary, "#CCCCCC")
        alpha = 0.8 if primary in ("family", "mentorship", "personal") else 0.3
        width = 2.5 if primary in ("family", "mentorship", "personal") else 0.8

        x = [pos[u][0], pos[v][0]]
        y = [pos[u][1], pos[v][1]]
        ax.plot(x, y, color=color, alpha=alpha, linewidth=width, zorder=1)

    # Draw nodes
    for node in G.nodes():
        x, y = pos[node]

        if node == WINNER:
            ax.scatter(x, y, s=1200, c="#1D3557", marker="*", zorder=5,
                       edgecolors="gold", linewidths=2)
            ax.annotate(short_name(node), (x, y), fontsize=12, fontweight="bold",
                        ha="center", va="bottom", xytext=(0, 18),
                        textcoords="offset points", color="#1D3557",
                        bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                                  edgecolor="#1D3557", alpha=0.9))
        elif node == LOSER:
            ax.scatter(x, y, s=1200, c="#E63946", marker="*", zorder=5,
                       edgecolors="gold", linewidths=2)
            ax.annotate(short_name(node), (x, y), fontsize=12, fontweight="bold",
                        ha="center", va="bottom", xytext=(0, 18),
                        textcoords="offset points", color="#E63946",
                        bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                                  edgecolor="#E63946", alpha=0.9))
        elif node in shared_neighbors:
            ax.scatter(x, y, s=300, c="#9B5DE5", marker="D", zorder=3,
                       edgecolors="white", linewidths=0.5)
        elif node in winner_only:
            ax.scatter(x, y, s=200, c="#457B9D", marker="o", zorder=3,
                       edgecolors="white", linewidths=0.5)
        elif node in loser_only:
            ax.scatter(x, y, s=200, c="#E76F51", marker="o", zorder=3,
                       edgecolors="white", linewidths=0.5)
        else:
            ax.scatter(x, y, s=100, c="#ADB5BD", marker="o", zorder=2)

    # Label top connected nodes
    LABEL_TOP = 25
    degree_sorted = sorted(
        [(n, G.degree(n)) for n in G.nodes() if n not in (WINNER, LOSER)],
        key=lambda x: x[1], reverse=True,
    )
    for node, deg in degree_sorted[:LABEL_TOP]:
        x, y = pos[node]
        ax.annotate(
            short_name(node), (x, y), fontsize=7, ha="center", va="bottom",
            xytext=(0, 8), textcoords="offset points", color="#333333",
            alpha=0.85,
        )

    # Legend
    legend_elements = [
        Line2D([0], [0], marker="*", color="w", markerfacecolor="#1D3557",
               markersize=18, label=f"Winner: {short_name(WINNER)}"),
        Line2D([0], [0], marker="*", color="w", markerfacecolor="#E63946",
               markersize=18, label=f"Closest Loser: {short_name(LOSER)}"),
        Line2D([0], [0], marker="D", color="w", markerfacecolor="#9B5DE5",
               markersize=10, label="Connected to Both"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#457B9D",
               markersize=10, label="Winner Network Only"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#E76F51",
               markersize=10, label="Loser Network Only"),
        Line2D([0], [0], color="white", markersize=0, label=""),  # spacer
    ]

    for ct, color in CONN_COLORS.items():
        if ct in ("shared_labor", "shared_other"):
            continue
        legend_elements.append(
            Line2D([0], [0], color=color, linewidth=2,
                   label=CONN_LABELS.get(ct, ct))
        )

    leg = ax.legend(
        handles=legend_elements, loc="upper left", fontsize=9,
        framealpha=0.9, edgecolor="#CCCCCC", title="Connection Types",
        title_fontsize=11,
    )

    ax.set_title(
        f"Political Network: {ELECTION_YEAR} Presidential Race\n"
        f"{short_name(WINNER)} (Winner) vs {short_name(LOSER)} (Closest Loser)",
        fontsize=18, fontweight="bold", pad=20,
    )
    ax.axis("off")

    plt.tight_layout()
    outpath = OUTPUT_DIR / f"viz1_network_{ELECTION_YEAR}.png"
    fig.savefig(outpath, dpi=200, bbox_inches="tight", facecolor="#FAFAFA")
    print(f"\nSaved to {outpath}")
    plt.close()


if __name__ == "__main__":
    build_network_graph()
