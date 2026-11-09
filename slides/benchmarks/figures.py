"""Only the two one-term figures and one consolidated estimates table."""
from pathlib import Path
import hashlib
import json
import os
import numpy as np
import pandas as pd

# Data under TAPADOS_BENCH_DIR (prepare.R, assignments.py, inference.R); the figures go to its final/ folder.
ROOT = Path(os.environ.get("TAPADOS_BENCH_DIR", Path(os.environ.get("TAPADOSPRI_DB_ROOT", Path.home() / "Dropbox" / "TapadosPRI")) / "output" / "slides" / "benchmarks"))
DATA = ROOT / "data"
FINAL = ROOT / "final"
FINAL.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/tapados-benchmark-matplotlib")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator

plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "STIXGeneral", "DejaVu Serif"],
    "font.size": 10, "axes.linewidth": .6, "axes.spines.top": False, "axes.spines.right": False,
    "xtick.major.width": .6, "ytick.major.width": .6, "xtick.major.size": 3, "ytick.major.size": 3,
    "pdf.fonttype": 42, "ps.fonttype": 42})
RULES = ("purge", "promotions_only", "sharing", "career")
DECK_RULES = ("purge", "sharing")   # the deck's figure: the two extreme rules only (9 Nov 2026; all four stay in the table)
TITLES = {"purge": "Winner-takes-all purge", "promotions_only": "Winner promotions; losers unchanged",
          "sharing": "Proportional sharing", "career": "Merit proxy: prior career and education"}
DESCRIPTIONS = {"purge": "Losers excluded; winner’s followers take the top ranks",
                "promotions_only": "Existing jobholders only; no hiring or exits",
                "sharing": "Contenders’ camps share the top by size; the unaligned fill the rest",
                "career": "Prior rank, years in office, then completed education"}
CONTRASTS = {"DP": "Premium\ndesignee's − losers'", "DN": "Reward\ndesignee's − unaligned",
             "PN": "Penalty\nlosers' − unaligned"}


def observed_data(n=9):
    assert n == 9
    return pd.concat([pd.read_csv(DATA / "design/observed_dp_intervals.csv"),
                      pd.read_csv(DATA / "design/observed_rp_intervals.csv")]).query("k <= 6")


def panel(ax, observed, simulated, contrast, rule, n, *, small=False, marks=True):
    last = 6
    ax.axhline(0, color=".7", lw=.55, zorder=0)
    for x, label, align in ((-1.5, "After designation", "right"),
                             (.5, "New presidency", "left")):
        if x < last:
            ax.axvline(x, color=".75", lw=.55, ls=(0, (2, 3)), zorder=0)
            if marks:
                ax.text(x, 1.005, label, transform=ax.get_xaxis_transform(), ha=align,
                        va="bottom", fontsize=6 if small else 8, color=".4")
    for table, color, style, alpha in ((simulated.query("rule == @rule and contrast == @contrast"),
                                       "#333333", (0, (5, 2)), .10),
                                      (observed.query("contrast == @contrast"), "#940034", "-", .14)):
        z = table.sort_values("k")
        ax.fill_between(z.k, z.ci_lower, z.ci_upper, color=color, alpha=alpha, lw=0, zorder=1)
        ax.plot(z.k, z.estimate, color=color, ls=style, lw=1.5, zorder=4)
    ax.set_xlim(-7.2, last + .2)
    ax.set_xticks(np.arange(-6, last + 1, 2))
    ax.set_xlabel("Years relative to election", labelpad=5)
    ax.tick_params(labelsize=8 if small else 9)


def footer(fig, n, y, fontsize=9):
    fig.legend(handles=[Line2D([], [], color="#940034", lw=1.6, label="Observed"),
                        Line2D([], [], color="#333333", lw=1.5, ls="--", label="Assignment rule")],
               loc="lower center", bbox_to_anchor=(.53, y + .045), ncol=2, frameon=False,
               fontsize=fontsize, handlelength=3)
    note = ("9 PRI successions, 1940–88. Separate one-term exercises. Observed careers through year 0; rules apply in years 1–6.\n"
            "Shaded areas: pointwise 95% intervals using the paper’s DiD inference. Year −2 is the reference. Panel scales vary.\n"
            "Rules and annual rank counts are fixed; intervals assume the DiD error model applies to the constructed outcomes.")
    if os.environ.get("BENCH_FIGURE_NOTE", "0") == "1":   # the deck uses the figure without the note (6 Nov 2026)
        fig.text(.08, y, note, fontsize=7.7, color=".3", linespacing=1.45)


def save(fig, stem):
    for extension in ("png", "pdf"):
        fig.savefig(FINAL / f"{stem}.{extension}", dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def figures():
    intervals = pd.read_csv(DATA / "inference/did_intervals.csv")
    for n, stem in ((9, "01_winner_vs_losers"),):
        observed = observed_data(n)
        simulated = intervals.query("scope == 'all_observed' and n_successions == @n")
        fig, axes = plt.subplots(2, 2, figsize=(11.5, 8.5))
        for ax, rule in zip(axes.ravel(), RULES):
            panel(ax, observed, simulated, "DP", rule, n)
            ax.set_title(TITLES[rule] + "\n" + DESCRIPTIONS[rule], fontsize=10.5, loc="left", pad=24, linespacing=1.5)
            ax.set_ylabel("Adjusted DiD (rank units)")
        footer(fig, n, .012)
        fig.subplots_adjust(left=.08, right=.985, top=.89, bottom=.20, hspace=.69, wspace=.24)
        save(fig, stem)
    n = 9
    observed = observed_data(n)
    simulated = intervals.query("scope == 'all_observed' and n_successions == @n")
    # The deck's figure: the two extreme rules (columns) and the premium with its reward and penalty (rows)
    fig, axes = plt.subplots(3, 2, figsize=(11.5, 6.0))
    for row, contrast in enumerate(CONTRASTS):
        for col, rule in enumerate(DECK_RULES):
            ax = axes[row, col]
            panel(ax, observed, simulated, contrast, rule, n, marks=row == 0)
            ax.tick_params(labelsize=10)
            # three to five whole-number ticks a panel; a panel spanning less than that reaches out to the next integers
            lo, hi = ax.get_ylim()
            if np.floor(hi) - np.ceil(lo) < 2:
                pad = .06 * (np.ceil(hi) - np.floor(lo))
                ax.set_ylim(min(lo, np.floor(lo) - pad), max(hi, np.ceil(hi) + pad) if np.floor(hi) - np.floor(lo) < 2 else hi)
            ax.yaxis.set_major_locator(MaxNLocator(nbins=5, steps=[1, 2, 5, 10], min_n_ticks=3, integer=True))
            if row == 0:
                ax.set_title(TITLES[rule], fontsize=14, loc="left", pad=18, fontweight="bold")
            if row < 2:
                ax.set_xlabel("")
            else:
                ax.set_xlabel("Years relative to election", labelpad=5, fontsize=11)
        axes[row, 0].set_ylabel(CONTRASTS[contrast], labelpad=8, fontsize=11, linespacing=1.3)
    footer(fig, n, -.01, fontsize=11)
    fig.text(.12, .015, "Followers' rank positions. Shaded: 95% intervals", fontsize=9.5, color=".35")
    fig.subplots_adjust(left=.12, right=.985, top=.90, bottom=.16, wspace=.14, hspace=.36)
    save(fig, "02_all_comparisons")


def validate_and_export():
    intervals = pd.read_csv(DATA / "inference/did_intervals.csv")
    assert set(intervals.rule) == set(RULES)
    assert np.isfinite(intervals[["estimate", "ci_lower", "ci_upper"]]).all().all()
    assert intervals.ci_lower.le(intervals.estimate).all() and intervals.estimate.le(intervals.ci_upper).all()
    expected = pd.read_csv(DATA / "assignment_estimates.csv")
    matched = intervals.merge(expected, on=["scope", "rule", "contrast", "k", "n_successions"], suffixes=("", "_saved"))
    assert len(matched) == len(intervals) == len(expected)
    assert (matched.estimate - matched.estimate_saved).abs().max() < 1e-10
    paths = pd.read_csv(DATA / "paths.csv.gz")
    assert not paths.duplicated(["scope", "rule", "election", "pid", "k"]).any()
    assert set(paths.k) == set(range(-7, 7))
    assert set(paths.election) == set(range(1940, 1989, 6))
    actual = pd.read_csv(DATA / "calendar/calendar_all.csv").set_index("pid")
    actual.columns = actual.columns.astype(int)
    pre_rank_error = 0
    for (rule, election), episode in paths.query("scope == 'all_observed'").groupby(["rule", "election"]):
        z = episode.pivot(index="pid", columns="k", values="rank")
        ref = actual.loc[z.index, election + z.columns.to_numpy()].copy()
        ref.columns = z.columns
        for k in z.columns:
            assert np.array_equal(np.bincount(z[k], minlength=12), np.bincount(ref[k], minlength=12))
        pre_rank_error = max(pre_rank_error, int((z.loc[:, z.columns <= 0] - ref.loc[:, ref.columns <= 0]).abs().to_numpy().max()))
        if rule == "promotions_only":
            assert np.array_equal(z.to_numpy() > 0, ref.to_numpy() > 0)
    assert pre_rank_error == 0
    pre_intervals = intervals.query("k <= 0").merge(observed_data(), on=["contrast", "k"], suffixes=("", "_observed"))
    pre_point_error = float((pre_intervals.estimate - pre_intervals.estimate_observed).abs().max())
    assert pre_point_error < 1e-12
    assert np.array_equal(pre_intervals.ci_lower, pre_intervals.ci_lower_observed)
    assert np.array_equal(pre_intervals.ci_upper, pre_intervals.ci_upper_observed)
    checks = pd.read_csv(DATA / "allocation_checks.csv").query("rule == 'promotions_only'")
    assert checks.losers_changed.eq(0).all() and checks.winner_hires.eq(0).all() and checks.unaligned_exits.eq(0).all()
    refit = pd.read_csv(DATA / "inference/refit_checks.csv")
    assert refit.error.max() < 1e-10
    original = pd.read_csv(DATA / "design/reproduction_checks.csv")
    assert len(original) == 34 and original.max_abs_error.max() < 1e-7   # main window, DP and DN by year, D window (prepare.R)
    pointwise = intervals.assign(statistic="annual_coefficient").rename(columns={"k": "year_relative_to_election"})
    averages = pd.read_csv(DATA / "inference/did_summary.csv").rename(columns={"outcome": "statistic"})
    gaps = pd.read_csv(DATA / "inference/paired_gap_intervals.csv").rename(columns={"outcome": "statistic"})
    observed = pd.concat([observed_data(n).assign(n_successions=n) for n in (9,)])
    observed = observed.assign(rule="observed", scope="all_observed", statistic="annual_coefficient").rename(columns={"k": "year_relative_to_election"})
    obs_avg = pd.read_csv(DATA / "inference/observed_annual_summary.csv").rename(columns={"outcome": "statistic"}).assign(rule="observed", scope="all_observed")
    obs_win = pd.read_csv(DATA / "design/observed_summary.csv").query("outcome == 'window_max_1_4'")
    obs_win = obs_win.rename(columns={"outcome": "statistic"}).assign(n_successions=9, rule="observed", scope="all_observed")
    columns = ["scope", "rule", "contrast", "n_successions", "statistic", "year_relative_to_election", "estimate", "ci_lower", "ci_upper"]
    estimates = pd.concat([pointwise, averages, gaps, observed, obs_avg, obs_win], ignore_index=True)
    estimates[columns].sort_values(columns[:6]).to_csv(FINAL / "estimates.csv", index=False)
    audit = dict(design="Independent one-term conditional reassignment per succession", rules=list(RULES),
        person_succession_years=len(paths), post_horizon=[1, 6], n_successions=9,
        observed_histories_preserved_through_year_zero=True, maximum_pre_rank_error=pre_rank_error,
        maximum_pre_point_error=pre_point_error, identical_pre_confidence_limits=True, annual_rank_counts_preserved=True,
        promotion_only_preserves_employment=True, losing_followers_unchanged_under_promotions=True,
        maximum_refit_error=float(refit.error.max()), original_results_reproduced=len(original),
        bootstrap_draws=50000, intervals="Nominal pointwise, conditional on the original DiD error model",
        source_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(__file__).resolve().parent.iterdir()) if p.is_file()})   # the scripts of slides/benchmarks
    (DATA / "validation.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit, indent=2))
    print(estimates.query("statistic == 'annual_1_4' and scope == 'all_observed' and n_successions == 9 and contrast == 'DP'")
          [["rule", "estimate", "ci_lower", "ci_upper"]].round(3).to_string(index=False))


if __name__ == "__main__":
    FINAL.mkdir(exist_ok=True)
    validate_and_export()
    figures()
