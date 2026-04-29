"""
Visualization 2: Pre/Post election geographic network map.

Shows where the political networks of the winner and closest loser were
located before and after the election, plotted on a Mexico state map.

Showcase: 1988 — Salinas vs Bartlett
"""

import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch
from collections import defaultdict, Counter
import sys
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parents[1]
if str(CODE_DIR) not in sys.path:
    sys.path.append(str(CODE_DIR))

from config import (
    PARSED_POSITIONS_CSV,
    PARSED_CONNECTIONS_CSV,
    STATES_GEOJSON,
    OUTPUT_DIR,
    DATA_DIR,
    MEXICAN_STATES,
    STATE_TO_GEOJSON,
    GEOJSON_TO_STATE,
)

# ---------------------------------------------------------------------------
# Configuration
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
PRE_WINDOW = 6   # years before election
POST_WINDOW = 6  # years after election


def short_name(full_name):
    """Convert CSV name to readable format."""
    import re
    if "," in full_name:
        parts = full_name.split(",", 1)
        last = re.sub(r"\s*\([^)]*\)", "", parts[0].strip()).title()
        first = parts[1].strip().title() if len(parts) > 1 else ""
        return f"{first[0]}. {last}" if first else last
    return full_name.title()


def get_state_centroid(state_canonical):
    """Get lat/lon centroid for a canonical state name."""
    info = MEXICAN_STATES.get(state_canonical)
    if info:
        return info[1], info[2]  # lat, lon
    return None, None


def main():
    print("Loading data...")
    pos_df = pd.read_csv(PARSED_POSITIONS_CSV)
    conn_df = pd.read_csv(CONN_FILE)
    mexico = gpd.read_file(STATES_GEOJSON)

    # Map GeoJSON state names to canonical
    mexico["canonical"] = mexico["name"].map(GEOJSON_TO_STATE)

    # Get network members for winner and loser
    winner_mask = (conn_df["person_a"] == WINNER) | (conn_df["person_b"] == WINNER)
    loser_mask = (conn_df["person_a"] == LOSER) | (conn_df["person_b"] == LOSER)

    winner_network = set()
    for _, r in conn_df[winner_mask].iterrows():
        other = r["person_b"] if r["person_a"] == WINNER else r["person_a"]
        winner_network.add(other)

    loser_network = set()
    for _, r in conn_df[loser_mask].iterrows():
        other = r["person_b"] if r["person_a"] == LOSER else r["person_a"]
        loser_network.add(other)

    # Limit to top connections for visual clarity
    TOP_N = 30

    def top_connected(candidate, mask):
        counts = Counter()
        for _, r in conn_df[mask].iterrows():
            other = r["person_b"] if r["person_a"] == candidate else r["person_a"]
            counts[other] += 1
        return {p for p, _ in counts.most_common(TOP_N)}

    winner_top = top_connected(WINNER, winner_mask)
    loser_top = top_connected(LOSER, loser_mask)

    # Filter positions to relevant time windows
    pos_with_years = pos_df.dropna(subset=["state", "year_start"]).copy()
    pos_with_years["year_start"] = pos_with_years["year_start"].astype(int)
    pos_with_years["year_end"] = pos_with_years["year_end"].fillna(
        pos_with_years["year_start"]
    ).astype(int)

    pre_start = ELECTION_YEAR - PRE_WINDOW
    pre_end = ELECTION_YEAR
    post_start = ELECTION_YEAR
    post_end = ELECTION_YEAR + POST_WINDOW

    def get_state_counts(people, period_start, period_end):
        """Count how many network members are in each state during a period."""
        mask = (
            pos_with_years["person_name"].isin(people) &
            (pos_with_years["year_start"] <= period_end) &
            (pos_with_years["year_end"] >= period_start) &
            (pos_with_years["field_type"] != "birthplace")
        )
        filtered = pos_with_years[mask]
        state_counts = filtered.groupby("state")["person_name"].nunique()
        return state_counts.to_dict()

    # Compute state distributions
    scenarios = {
        ("Winner", "Pre-Election"): (winner_top | {WINNER}, pre_start, pre_end),
        ("Winner", "Post-Election"): (winner_top | {WINNER}, post_start, post_end),
        ("Loser", "Pre-Election"): (loser_top | {LOSER}, pre_start, pre_end),
        ("Loser", "Post-Election"): (loser_top | {LOSER}, post_start, post_end),
    }

    state_data = {}
    for key, (people, ps, pe) in scenarios.items():
        state_data[key] = get_state_counts(people, ps, pe)

    # ---------------------------------------------------------------------------
    # Plot 2x2 grid
    # ---------------------------------------------------------------------------
    fig, axes = plt.subplots(2, 2, figsize=(24, 18))
    fig.patch.set_facecolor("white")

    titles = [
        (0, 0, "Winner", "Pre-Election", f"{short_name(WINNER)} — Pre-Election ({pre_start}-{pre_end})"),
        (0, 1, "Winner", "Post-Election", f"{short_name(WINNER)} — Post-Election ({post_start}-{post_end})"),
        (1, 0, "Loser", "Pre-Election", f"{short_name(LOSER)} — Pre-Election ({pre_start}-{pre_end})"),
        (1, 1, "Loser", "Post-Election", f"{short_name(LOSER)} — Post-Election ({post_start}-{post_end})"),
    ]

    for row, col, candidate_type, period, title in titles:
        ax = axes[row][col]

        counts = state_data[(candidate_type, period)]
        max_count = max(counts.values()) if counts else 1

        # Map canonical names to GeoJSON for coloring
        color_map = {}
        for state_canon, count in counts.items():
            geojson_name = STATE_TO_GEOJSON.get(state_canon)
            if geojson_name:
                color_map[geojson_name] = count

        # Color states
        def get_color(row_data):
            name = row_data["name"]
            if name in color_map:
                intensity = color_map[name] / max_count
                if candidate_type == "Winner":
                    # Blue gradient
                    return (0.27 - 0.2 * intensity, 0.48 - 0.3 * intensity, 0.62 + 0.3 * intensity, 0.3 + 0.7 * intensity)
                else:
                    # Red gradient
                    return (0.90, 0.22 + 0.1 * intensity, 0.27 + 0.1 * intensity, 0.3 + 0.7 * intensity)
            return (0.93, 0.93, 0.93, 1.0)

        colors = mexico.apply(get_color, axis=1)
        mexico.plot(ax=ax, color=colors, edgecolor="#666666", linewidth=0.5)

        # Add count labels on states with connections
        for state_canon, count in counts.items():
            lat, lon = get_state_centroid(state_canon)
            if lat and lon and count > 0:
                fontsize = min(7 + count, 14)
                ax.annotate(
                    str(count), (lon, lat),
                    fontsize=fontsize, fontweight="bold",
                    ha="center", va="center", color="white",
                    bbox=dict(boxstyle="round,pad=0.2", facecolor="black", alpha=0.6),
                )

        # Mark candidate's primary location with a star
        candidate_name = WINNER if candidate_type == "Winner" else LOSER
        cand_states = pos_with_years[
            (pos_with_years["person_name"] == candidate_name) &
            (pos_with_years["year_start"] <= (pre_end if period == "Pre-Election" else post_end)) &
            (pos_with_years["year_end"] >= (pre_start if period == "Pre-Election" else post_start)) &
            (pos_with_years["field_type"] != "birthplace")
        ]["state"].value_counts()

        if len(cand_states) > 0:
            primary_state = cand_states.index[0]
            lat, lon = get_state_centroid(primary_state)
            if lat and lon:
                star_color = "#1D3557" if candidate_type == "Winner" else "#E63946"
                ax.scatter(lon, lat, s=400, marker="*", c=star_color,
                           edgecolors="gold", linewidths=1.5, zorder=5)

        ax.set_title(title, fontsize=14, fontweight="bold", pad=10)
        ax.axis("off")

    # Legend
    legend_elements = [
        Line2D([0], [0], marker="*", color="w", markerfacecolor="#1D3557",
               markersize=15, label=f"Winner: {short_name(WINNER)}"),
        Line2D([0], [0], marker="*", color="w", markerfacecolor="#E63946",
               markersize=15, label=f"Closest Loser: {short_name(LOSER)}"),
        Line2D([0], [0], marker="s", color="w", markerfacecolor="#457B9D",
               markersize=12, label="Winner network density"),
        Line2D([0], [0], marker="s", color="w", markerfacecolor="#E63946",
               markersize=12, label="Loser network density"),
        Line2D([0], [0], marker="s", color="w", markerfacecolor="#EDEDED",
               markersize=12, markeredgecolor="#999", label="No connections"),
    ]
    fig.legend(
        handles=legend_elements, loc="lower center", ncol=5,
        fontsize=11, framealpha=0.9, edgecolor="#CCC",
    )

    fig.suptitle(
        f"Geographic Distribution of Political Networks — {ELECTION_YEAR} Election\n"
        f"Number of network members active in each state",
        fontsize=18, fontweight="bold", y=0.98,
    )

    plt.tight_layout(rect=[0, 0.05, 1, 0.95])
    outpath = OUTPUT_DIR / f"viz2_geo_network_{ELECTION_YEAR}.png"
    fig.savefig(outpath, dpi=200, bbox_inches="tight", facecolor="white")
    print(f"\nSaved to {outpath}")
    plt.close()


if __name__ == "__main__":
    main()
