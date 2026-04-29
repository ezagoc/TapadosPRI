"""
Visualization 4: Geographic influence map with temporal gradient.

Shows a faceted map (one per candidate) coloring states where each person
was active, with darker shading for more recent activity (closer to election).
Star markers on birthplace.

Showcase: 1988 — Salinas + top 5 tapados
"""

import sys
import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
from collections import defaultdict
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parents[1]
if str(CODE_DIR) not in sys.path:
    sys.path.append(str(CODE_DIR))

from config import (
    PARSED_POSITIONS_CSV,
    BIOGRAPHIES_CSV,
    CORCHOLATAS_XLSX,
    STATES_GEOJSON,
    OUTPUT_DIR,
    MEXICAN_STATES,
    STATE_TO_GEOJSON,
    GEOJSON_TO_STATE,
    normalize_name,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PRESETS = {
    1988: {
        "candidates": [
            "salinas de gortari, carlos",
            "Bartlett (díaz), Manuel",
            "del Mazo gonzález, alfredo",
            "garcía raMírez, sergio",
            "aguirre (velázquez), raMón",
            "gonzález avelar, Miguel",
        ],
        "labels": {
            "salinas de gortari, carlos": "C. Salinas de Gortari ★ WINNER",
            "Bartlett (díaz), Manuel": "M. Bartlett Díaz",
            "del Mazo gonzález, alfredo": "A. Del Mazo González",
            "garcía raMírez, sergio": "S. García Ramírez",
            "aguirre (velázquez), raMón": "R. Aguirre Velázquez",
            "gonzález avelar, Miguel": "M. González Avelar",
        },
    },
    1994: {
        "candidates": [
            "zedillo Ponce de léon, ernesto",
            "caMacho solís, víctor Manuel",
            "asPe (arMella), Pedro carlos",
            "gutiérrez Barrios, fernando (Deceased Oct. 30, 2000)",
            "gaMBoa Patrón, eMilio",
            "ortiz arana, fernando",
        ],
        "labels": {
            "zedillo Ponce de léon, ernesto": "E. Zedillo ★ WINNER",
            "caMacho solís, víctor Manuel": "M. Camacho Solís",
            "asPe (arMella), Pedro carlos": "P. Aspe Armella",
            "gutiérrez Barrios, fernando (Deceased Oct. 30, 2000)": "F. Gutiérrez Barrios",
            "gaMBoa Patrón, eMilio": "E. Gamboa Patrón",
            "ortiz arana, fernando": "F. Ortiz Arana",
        },
    },
}

ELECTION_YEAR = int(sys.argv[1]) if len(sys.argv) > 1 else 1988
preset = PRESETS[ELECTION_YEAR]
CANDIDATES = preset["candidates"]
CANDIDATE_LABELS = preset["labels"]

# One hue per candidate (consistent across elections)
CANDIDATE_HUES = [
    (0.08, 0.32, 0.62),   # Dark blue - main candidate
    (0.90, 0.22, 0.27),   # Red
    (0.17, 0.63, 0.17),   # Green
    (0.58, 0.40, 0.74),   # Purple
    (1.0, 0.50, 0.05),    # Orange
    (0.09, 0.75, 0.81),   # Teal
]


def get_state_centroid(state_canonical):
    info = MEXICAN_STATES.get(state_canonical)
    if info:
        return info[1], info[2]
    return None, None


def main():
    print("Loading data...")
    pos_df = pd.read_csv(PARSED_POSITIONS_CSV)
    bio_df = pd.read_csv(BIOGRAPHIES_CSV)
    mexico = gpd.read_file(STATES_GEOJSON)
    mexico["canonical"] = mexico["name"].map(GEOJSON_TO_STATE)

    # Filter positions with years
    pos = pos_df.dropna(subset=["state", "year_start"]).copy()
    pos["year_start"] = pos["year_start"].astype(int)
    pos["year_end"] = pos["year_end"].fillna(pos["year_start"]).astype(int)

    # Get birthplace for each candidate
    birthplaces = {}
    bp_data = pos_df[pos_df["field_type"] == "birthplace"]
    for cand in CANDIDATES:
        bp_rows = bp_data[bp_data["person_name"] == cand]
        if len(bp_rows) > 0:
            birthplaces[cand] = bp_rows.iloc[0]["state"]

    # ---------------------------------------------------------------------------
    # Compute temporal weights per state per candidate
    # ---------------------------------------------------------------------------
    candidate_state_weights = {}

    for cand in CANDIDATES:
        cand_pos = pos[
            (pos["person_name"] == cand) &
            (pos["field_type"] != "birthplace") &
            (pos["year_end"] <= ELECTION_YEAR)
        ]

        state_weights = defaultdict(float)
        state_years = defaultdict(list)

        for _, row in cand_pos.iterrows():
            state = row["state"]
            # Weight: more recent = higher weight
            mid_year = (row["year_start"] + row["year_end"]) / 2
            recency = 1.0 / (ELECTION_YEAR - mid_year + 1)
            state_weights[state] += recency
            state_years[state].append((row["year_start"], row["year_end"]))

        # Normalize weights to [0, 1] using log scale to prevent
        # Federal District from dominating and making other states invisible
        if state_weights:
            max_w = max(state_weights.values())
            for s in state_weights:
                # Log-based normalization with a minimum floor
                raw = state_weights[s] / max_w
                # Apply sqrt to compress the range (boost low values)
                state_weights[s] = max(0.3, raw ** 0.4)

        candidate_state_weights[cand] = dict(state_weights)

    # ---------------------------------------------------------------------------
    # Plot: 2x3 faceted map
    # ---------------------------------------------------------------------------
    fig, axes = plt.subplots(2, 3, figsize=(30, 18))
    fig.patch.set_facecolor("white")

    for idx, cand in enumerate(CANDIDATES):
        row = idx // 3
        col = idx % 3
        ax = axes[row][col]

        base_rgb = CANDIDATE_HUES[idx]
        weights = candidate_state_weights.get(cand, {})

        # Color each state
        def get_color(geo_row):
            canonical = geo_row["canonical"]
            if canonical in weights:
                w = weights[canonical]
                # Interpolate from light (low weight) to dark (high weight)
                r = 1.0 - w * (1.0 - base_rgb[0])
                g = 1.0 - w * (1.0 - base_rgb[1])
                b = 1.0 - w * (1.0 - base_rgb[2])
                return (r, g, b, 0.7 + 0.3 * w)
            return (0.95, 0.95, 0.95, 1.0)

        colors = mexico.apply(get_color, axis=1)
        mexico.plot(ax=ax, color=colors, edgecolor="#888888", linewidth=0.5)

        # Star on birthplace
        bp_state = birthplaces.get(cand)
        if bp_state:
            lat, lon = get_state_centroid(bp_state)
            if lat and lon:
                ax.scatter(
                    lon, lat, s=500, marker="*", c="gold",
                    edgecolors="black", linewidths=1.5, zorder=5,
                )
                ax.annotate(
                    "Birthplace", (lon, lat), fontsize=8,
                    ha="center", va="top", xytext=(0, -12),
                    textcoords="offset points", fontweight="bold",
                    color="black",
                )

        label = CANDIDATE_LABELS.get(cand, cand)
        ax.set_title(label, fontsize=13, fontweight="bold", pad=10)
        ax.axis("off")

    # Colorbar legend
    fig.text(
        0.5, 0.02,
        "Darker shading = more recent activity (closer to election year). "
        "★ = Birthplace. Gray = no recorded activity.",
        ha="center", fontsize=12, style="italic", color="#555555",
    )

    fig.suptitle(
        f"Geographic Influence Map — {ELECTION_YEAR} Presidential Candidates\n"
        f"States colored by intensity of each candidate's presence (weighted by recency to {ELECTION_YEAR})",
        fontsize=18, fontweight="bold", y=0.98,
    )

    plt.tight_layout(rect=[0, 0.05, 1, 0.94])
    outpath = OUTPUT_DIR / f"viz4_influence_map_{ELECTION_YEAR}.png"
    fig.savefig(outpath, dpi=200, bbox_inches="tight", facecolor="white")
    print(f"Saved to {outpath}")
    plt.close()


if __name__ == "__main__":
    main()
