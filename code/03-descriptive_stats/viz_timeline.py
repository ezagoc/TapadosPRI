"""
Visualization 3: Gantt-style timeline showing year-by-year geographic location
of all presidential candidates for a given election.

Shows which state each candidate was active in over time, revealing
geographic convergence patterns before elections.

Showcase: 1988 — All 6 key tapados
"""

import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import Rectangle
from collections import defaultdict
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parents[1]
if str(CODE_DIR) not in sys.path:
    sys.path.append(str(CODE_DIR))

from config import (
    PARSED_POSITIONS_CSV,
    OUTPUT_DIR,
    MEXICAN_STATES,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PRESETS = {
    1988: {
        "candidates": [
            ("salinas de gortari, carlos", True),
            ("Bartlett (díaz), Manuel", False),
            ("del Mazo gonzález, alfredo", False),
            ("garcía raMírez, sergio", False),
            ("aguirre (velázquez), raMón", False),
            ("gonzález avelar, Miguel", False),
        ],
        "short": {
            "salinas de gortari, carlos": "C. Salinas de Gortari ★",
            "Bartlett (díaz), Manuel": "M. Bartlett Díaz",
            "del Mazo gonzález, alfredo": "A. Del Mazo González",
            "garcía raMírez, sergio": "S. García Ramírez",
            "aguirre (velázquez), raMón": "R. Aguirre Velázquez",
            "gonzález avelar, Miguel": "M. González Avelar",
        },
    },
    1994: {
        "candidates": [
            ("zedillo Ponce de léon, ernesto", True),
            ("caMacho solís, víctor Manuel", False),
            ("asPe (arMella), Pedro carlos", False),
            ("gutiérrez Barrios, fernando (Deceased Oct. 30, 2000)", False),
            ("ortiz arana, fernando", False),
        ],
        "short": {
            "zedillo Ponce de léon, ernesto": "E. Zedillo ★",
            "caMacho solís, víctor Manuel": "M. Camacho Solís",
            "asPe (arMella), Pedro carlos": "P. Aspe Armella",
            "gutiérrez Barrios, fernando (Deceased Oct. 30, 2000)": "F. Gutiérrez Barrios",
            "ortiz arana, fernando": "F. Ortiz Arana",
        },
    },
}

ELECTION_YEAR = int(sys.argv[1]) if len(sys.argv) > 1 else 1988
preset = PRESETS[ELECTION_YEAR]
CANDIDATES = preset["candidates"]
CANDIDATE_SHORT = preset["short"]

# Top states get distinct colors; rest grouped as "Other"
STATE_COLORS = {
    "Federal District": "#1D3557",
    "Puebla": "#E63946",
    "Mexico": "#457B9D",
    "Jalisco": "#2A9D8F",
    "Sonora": "#FF9F1C",
    "Nuevo Leon": "#9B5DE5",
    "Guerrero": "#00BBF9",
    "Tabasco": "#E76F51",
    "Coahuila": "#6D6875",
    "Guanajuato": "#B5838D",
    "Michoacan": "#8338EC",
    "Chihuahua": "#06D6A0",
}
OTHER_COLOR = "#ADB5BD"

YEAR_START = 1950
YEAR_END = 2000


def main():
    print("Loading positions data...")
    pos_df = pd.read_csv(PARSED_POSITIONS_CSV)

    # Filter to candidates and usable records
    cand_names = [c[0] for c in CANDIDATES]
    pos = pos_df[
        pos_df["person_name"].isin(cand_names) &
        pos_df["state"].notna() &
        pos_df["year_start"].notna() &
        (pos_df["field_type"] != "birthplace")
    ].copy()

    pos["year_start"] = pos["year_start"].astype(int)
    pos["year_end"] = pos["year_end"].fillna(pos["year_start"]).astype(int)

    # Clip to range
    pos = pos[(pos["year_end"] >= YEAR_START) & (pos["year_start"] <= YEAR_END)]
    pos["year_start"] = pos["year_start"].clip(YEAR_START, YEAR_END)
    pos["year_end"] = pos["year_end"].clip(YEAR_START, YEAR_END)

    # Build year-by-year state assignments per candidate
    candidate_years = {}
    for cand_name, _ in CANDIDATES:
        cand_pos = pos[pos["person_name"] == cand_name]
        year_states = defaultdict(list)

        for _, row in cand_pos.iterrows():
            for y in range(int(row["year_start"]), int(row["year_end"]) + 1):
                if YEAR_START <= y <= YEAR_END:
                    year_states[y].append(row["state"])

        # For each year, pick the most common state
        year_primary = {}
        for y, states in year_states.items():
            from collections import Counter
            c = Counter(states)
            year_primary[y] = c.most_common(1)[0][0]

        candidate_years[cand_name] = year_primary

    # ---------------------------------------------------------------------------
    # Plot Gantt chart
    # ---------------------------------------------------------------------------
    n_candidates = len(CANDIDATES)
    fig, ax = plt.subplots(figsize=(28, 10))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#FAFAFA")

    bar_height = 0.7
    years = list(range(YEAR_START, YEAR_END + 1))

    for idx, (cand_name, is_winner) in enumerate(CANDIDATES):
        y_pos = n_candidates - idx - 1
        year_primary = candidate_years.get(cand_name, {})

        # Draw continuous segments of same state
        if not year_primary:
            continue

        # Group consecutive years with same state
        segments = []
        sorted_years = sorted(year_primary.keys())
        if sorted_years:
            seg_start = sorted_years[0]
            seg_state = year_primary[seg_start]
            for y in sorted_years[1:]:
                if year_primary[y] == seg_state and y == sorted_years[sorted_years.index(y) - 1] + 1:
                    continue
                elif year_primary[y] == seg_state:
                    continue
                else:
                    seg_end = y - 1
                    segments.append((seg_start, seg_end, seg_state))
                    seg_start = y
                    seg_state = year_primary[y]
            segments.append((seg_start, sorted_years[-1], seg_state))

        # Actually, simpler: draw each year as a 1-year bar
        for y in sorted_years:
            state = year_primary[y]
            color = STATE_COLORS.get(state, OTHER_COLOR)
            rect = Rectangle(
                (y, y_pos - bar_height / 2), 1, bar_height,
                facecolor=color, edgecolor="white", linewidth=0.3,
            )
            ax.add_patch(rect)

        # Winner highlight — add a border
        if is_winner:
            rect = Rectangle(
                (YEAR_START, y_pos - bar_height / 2 - 0.05),
                YEAR_END - YEAR_START + 1, bar_height + 0.1,
                facecolor="none", edgecolor="gold", linewidth=2.5,
                linestyle="-", zorder=4,
            )
            ax.add_patch(rect)

    # Election year vertical line
    ax.axvline(x=ELECTION_YEAR, color="#E63946", linewidth=2.5,
               linestyle="--", zorder=5, alpha=0.8)
    ax.text(
        ELECTION_YEAR, n_candidates + 0.1, f"Election {ELECTION_YEAR}",
        fontsize=11, fontweight="bold", color="#E63946", ha="center",
    )

    # Y-axis labels
    y_labels = [CANDIDATE_SHORT.get(c[0], c[0]) for c in CANDIDATES]
    y_positions = [n_candidates - i - 1 for i in range(n_candidates)]
    ax.set_yticks(y_positions)
    ax.set_yticklabels(y_labels, fontsize=12, fontweight="bold")

    # X-axis
    ax.set_xlim(YEAR_START, YEAR_END + 1)
    ax.set_ylim(-0.5, n_candidates + 0.5)
    ax.set_xticks(range(YEAR_START, YEAR_END + 1, 2))
    ax.set_xticklabels([str(y) for y in range(YEAR_START, YEAR_END + 1, 2)],
                       fontsize=9, rotation=45)
    ax.set_xlabel("Year", fontsize=13)

    # Grid
    ax.grid(axis="x", alpha=0.2, linewidth=0.5)
    ax.set_axisbelow(True)

    # Legend for states
    legend_patches = []
    for state, color in STATE_COLORS.items():
        legend_patches.append(mpatches.Patch(color=color, label=state))
    legend_patches.append(mpatches.Patch(color=OTHER_COLOR, label="Other States"))

    ax.legend(
        handles=legend_patches, loc="upper right", fontsize=8,
        ncol=2, framealpha=0.9, edgecolor="#CCC", title="State",
        title_fontsize=10,
    )

    ax.set_title(
        f"Career Location Timeline — {ELECTION_YEAR} Presidential Candidates\n"
        f"Primary state of activity per year (★ = winner, gold border)",
        fontsize=16, fontweight="bold", pad=15,
    )

    plt.tight_layout()
    outpath = OUTPUT_DIR / f"viz3_timeline_{ELECTION_YEAR}.png"
    fig.savefig(outpath, dpi=200, bbox_inches="tight", facecolor="white")
    print(f"Saved to {outpath}")
    plt.close()


if __name__ == "__main__":
    main()
