"""Collect the deck's figures and tables from the pipeline's outputs under TapadosPRI/output/slides.

Every figure, table and macro file that 3rdYearPresentation/main.tex reads is listed in DECK_FILES with the pipeline
output it comes from (relative to TapadosPRI/output/slides). The script copies each one to output/slides/deck/figures
or output/slides/deck/tables under its deck name, and then into the Overleaf repository (research/slides, DECK_DIR) so
the deck compiles. Static images (the 1942 cabinet poster, the 1946 portraits) are not generated; they live only in the
Overleaf repository and are listed in STATIC for completeness.

  python3 slides/deck/collect_deck_files.py            copy to output/slides/deck and to the Overleaf repository
  python3 slides/deck/collect_deck_files.py --check    compare the pipeline's files with the deck's current copies
                                                       (text files exactly, PDFs by their text and page size) and copy nothing
  python3 slides/deck/collect_deck_files.py --no-deck  copy to output/slides/deck only
"""
import argparse
import os
import re
import shutil
import subprocess
from pathlib import Path

db_root = Path(os.environ.get("TAPADOSPRI_DB_ROOT", Path.home() / "Dropbox" / "TapadosPRI"))
OUT = Path(os.environ.get("TAPADOSPRI_OUTPUT_DIR", db_root / "output")) / "slides"
DECK_DIR = Path(os.environ.get("TAPADOS_DECK_DIR", Path(__file__).resolve().parents[2] / "research" / "slides" / "3rdYearPresentation"))

# deck file (under figures/ or tables/ of the Overleaf repository) -> pipeline output under TapadosPRI/output/slides
DECK_FILES = {
    # ---- figures of the main design (slides/analysis)
    "figures/md_es_rank.pdf": "analysis/es_rank.pdf",                                   # figures_deck.R (event_study.R)
    "figures/md_es_extensive.pdf": "analysis/es_extensive.pdf",                         # figures_deck.R (margins.R)
    "figures/md_es_reward_punishment.pdf": "analysis/es_reward_punishment.pdf",         # figures_deck.R (reward_punishment.R)
    "figures/md_es_reward_punishment_office.pdf": "analysis/es_reward_punishment_office.pdf",   # rp_office.R
    "figures/md_rp_raw.pdf": "analysis/rp_raw_trajectories.pdf",                        # rp_raw_trajectories.R
    "figures/md_post_holders.pdf": "analysis/post_holders.pdf",                         # post_holders.R
    "figures/md_first_stage_fed.pdf": "analysis/first_stage_fed.pdf",                   # first_stage.R
    "figures/md_first_stage_rp.pdf": "analysis/first_stage_rp.pdf",                     # first_stage_rp.R
    "figures/md_rp_thresholds_gap.pdf": "analysis/rp_thresholds_gap.pdf",               # rp_thresholds.R
    "figures/md_rp_thresholds.pdf": "analysis/rp_thresholds.pdf",                       # rp_thresholds.R
    "figures/md_es_indirect.pdf": "analysis/es_indirect.pdf",                           # indirect_ties.R
    "figures/md_by_succession_forest.pdf": "analysis/by_succession_forest.pdf",         # by_succession_forest.R
    "figures/md_randomization.pdf": "analysis/randomization_inference.pdf",             # randomization_inference.R
    "figures/benchmarks_all_comparisons.pdf": "benchmarks/final/02_all_comparisons.pdf",   # slides/benchmarks/figures.py
    # ---- descriptive figures (slides/descriptives)
    "figures/pri_vote.pdf": "descriptives/pri_vote.pdf",                                # viz_appendix_descriptives.py
    "figures/land_by_president.pdf": "descriptives/land_by_president.pdf",              # viz_appendix_descriptives.py
    "figures/investment_series.pdf": "descriptives/investment_series.pdf",              # plot_agency_series.py
    "figures/autocracy_survival_successions.pdf": "descriptives/autocracy_survival_successions.pdf",   # autocracy/06_successions_survival.R
    # ---- tables (slides/analysis, written to analysis/tables)
    "tables/sample.tex": "analysis/tables/sample.tex",                                  # deck/build_rank_description.py
    "tables/ladder_shares.tex": "analysis/tables/ladder_shares.tex",                    # ladder_shares.R
    "tables/balance_combined.tex": "analysis/tables/balance_combined.tex",              # balance_combined.R
    "tables/rules_table.tex": "analysis/tables/rules_table.tex",                        # rules_table.R
    "tables/loser_careers.tex": "analysis/tables/loser_careers.tex",                    # loser_careers.py
    "tables/md_robustness.tex": "analysis/tables/robustness_deck.tex",                  # appendix_diagnostics.R
    "tables/md_by_succession.tex": "analysis/tables/md_by_succession.tex",              # deck/build_by_succession_table.py
    "tables/runner_up.tex": "analysis/tables/runner_up.tex",                            # runner_up.R
    "tables/followers_1946_aleman.tex": "analysis/tables/followers_1946_aleman.tex",    # followers_table_1946.py
    "tables/followers_1946_padilla_top12.tex": "analysis/tables/followers_1946_padilla_top12.tex",   # followers_table_1946.py
    # ---- macro files (one \newcommand per number quoted on the slides)
    "tables/title_correction_macros.tex": "analysis/tables/title_correction_macros.tex",   # deck/headline_macros.py
    "tables/main_direct_tie_macros.tex": "analysis/tables/main_direct_tie_macros.tex",  # appendix_diagnostics.R
    "tables/rp_macros.tex": "analysis/tables/rp_macros.tex",                            # reward_punishment.R
    "tables/randomization_macros.tex": "analysis/tables/randomization_macros.tex",      # randomization_inference.R
    "tables/pay_macros.tex": "analysis/tables/pay_macros.tex",                          # pay_envelope.R
    "tables/rp_office_macros.tex": "analysis/tables/rp_office_macros.tex",              # rp_office.R
    "tables/first_stage_macros.tex": "analysis/tables/first_stage_macros.tex",          # first_stage.R
    "tables/first_stage_rp_macros.tex": "analysis/tables/first_stage_rp_macros.tex",    # first_stage_rp.R
    "tables/indirect_macros.tex": "analysis/tables/indirect_macros.tex",                # indirect_ties.R
    "tables/rp_thresholds_macros.tex": "analysis/tables/rp_thresholds_macros.tex",      # rp_thresholds.R
    "tables/runner_up_macros.tex": "analysis/tables/runner_up_macros.tex",              # runner_up.R
    "tables/rules_macros.tex": "analysis/tables/rules_macros.tex",                      # rules_table.R
    "tables/by_succession_macros.tex": "analysis/tables/by_succession_macros.tex",      # deck/build_by_succession_table.py
    "tables/by_succession_forest_macros.tex": "analysis/tables/by_succession_forest_macros.tex",   # by_succession_forest.R
    "tables/loser_macros.tex": "analysis/tables/loser_macros.tex",                      # loser_careers.py
    "tables/followers_1946_macros.tex": "analysis/tables/followers_1946_macros.tex",    # followers_table_1946.py
    "tables/post_holders_macros.tex": "analysis/tables/post_holders_macros.tex",        # post_holders.R
    "tables/het_ties_macros.tex": "analysis/tables/het_ties_macros.tex",                # het_ties_figure.R (heterogeneity.R)
}
STATIC = ["figures/1942_mexican_cabinet_chart_poster.png", "figures/1946_portrait_aleman.png", "figures/1946_portrait_baz.png",
          "figures/1946_portrait_padilla.png", "figures/1946_portrait_rojo_gomez.png"]


def pdf_signature(path):
    """Page size and text of a PDF, for comparing two renderings of the same figure."""
    info = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True).stdout
    size = re.search(r"Page size:\s*(.*)", info).group(1).strip()
    text = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True).stdout
    return size, " ".join(sorted(text.split()))   # the words, order-free: label order can change with sub-point moves


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="compare with the deck's current files, copy nothing")
    ap.add_argument("--no-deck", action="store_true", help="copy to output/slides/deck only")
    a = ap.parse_args()
    missing, same, differ, copied = [], [], [], []
    for deck_name, source in DECK_FILES.items():
        src = OUT / source
        if not src.exists():
            missing.append(f"{deck_name} <- {source}")
            continue
        current = DECK_DIR / deck_name
        if a.check:
            if not current.exists():
                differ.append(f"{deck_name}: not in the deck")
            elif src.suffix == ".pdf":
                s1, s2 = pdf_signature(src), pdf_signature(current)
                (same if s1 == s2 else differ).append(f"{deck_name}" + ("" if s1 == s2 else f": page size {s1[0]} vs {s2[0]}, text {'equal' if s1[1] == s2[1] else 'differs'}"))
            else:
                t1, t2 = src.read_text(), current.read_text()
                strip = lambda t: "\n".join(l for l in t.splitlines() if not l.startswith("%"))   # comment lines carry dates
                (same if strip(t1) == strip(t2) else differ).append(deck_name)
            continue
        dest = OUT / "deck" / deck_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        if not a.no_deck:
            (DECK_DIR / deck_name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, DECK_DIR / deck_name)
        copied.append(deck_name)
    for s in STATIC:
        if not (DECK_DIR / s).exists():
            missing.append(f"{s} (static image expected in the Overleaf repository)")
    if a.check:
        print(f"{len(same)} deck files reproduced, {len(differ)} differ, {len(missing)} missing")
        for d in differ: print("  DIFFERS", d)
    else:
        print(f"{len(copied)} files copied to {OUT / 'deck'}" + ("" if a.no_deck else f" and {DECK_DIR}"))
    for m in missing: print("  MISSING", m)
    raise SystemExit(1 if missing or (a.check and differ) else 0)


if __name__ == "__main__":
    main()
