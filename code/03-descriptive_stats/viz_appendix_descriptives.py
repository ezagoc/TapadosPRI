"""Two appendix descriptives for the slide deck: the PRI's presidential vote 1929-2000 and land granted by president 1916-1992.

pri_vote
    The PRI's (PNR / PRM / PRI) national share of the valid vote in every presidential election 1929-2000, the range of
    that share across states, and the dissident candidates' shares. Data: the elections block's state panel 1934-1994
    (research/main_R/output_v2/elections/elections_votes_by_state.csv, built by elections.R from electoralData/),
    extended here with 1929 (Ramirez Rancano 1977, Colegio Electoral count) and 2000 (IFE via Magar 2012) from the
    same raw folder, with the panel's conventions: share of the valid vote = votes for the candidate / sum of the
    party lines; the PRI candidate includes the PPS and PARM lines where those parties ran him (1970-82).
land_by_president
    Hectares and beneficiaries of land grants (dotacion, ampliacion, restitucion, NCPE, bienes comunales) by signing
    president from the agrarian-actions ledger (land_reform/agrarian_actions_1916_1992.csv: Sanderson 1916 - 3 Nov
    1976, Diario Oficial 4 Nov 1976 - 1992), checked against INEGI EHM 2014 tables 9.50-9.51 by presidential term.

Writes OUTPUT_DIR/slides/<name>.{pdf,png} and the plotted numbers as <name>_data.csv, and copies the pdf/png to
research/slides/pri_succession_slides/figures/. Data are read only.
"""
import shutil
import sys
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "code"))
from config import DATA_DIR, OUTPUT_DIR  # noqa: E402

ACC, INK, Z4, Z5, Z6, Z7 = "#940034", "#111111", "#a1a1aa", "#71717a", "#52525b", "#f4f4f5"
OUT = OUTPUT_DIR / "slides"
FIG = ROOT / "research" / "slides" / "pri_succession_slides" / "figures"
ELEC = DATA_DIR / "electoralData" / "raw"
PANEL = ROOT / "research" / "main_R" / "output_v2" / "elections" / "elections_votes_by_state.csv"
LAND = DATA_DIR / "land_reform"
SIZE = (10, 5.2)


def style(ax):
    ax.set_facecolor("white")
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)
    for s in ["left", "bottom"]:
        ax.spines[s].set_color(Z4)
    ax.tick_params(colors=Z6, labelsize=9)
    ax.grid(False)


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)
    for ext in ["pdf", "png"]:
        p = OUT / f"{name}.{ext}"
        fig.savefig(p, facecolor="white", dpi=200)
        shutil.copy2(p, FIG / p.name)
    plt.close(fig)
    print("saved", OUT / f"{name}.pdf", "and", FIG / f"{name}.pdf")


def note(fig, lines, size=7.5, dy=0.028):
    """Source note at the bottom-left, one text per line; the font shrinks (to 6.5 pt) until each line fits the figure width."""
    r = fig.canvas.get_renderer()
    texts = []
    for i, line in enumerate(reversed(lines)):
        t = fig.text(0.0, 0.008 + i * dy, line, fontsize=size, color=Z5, va="bottom", ha="left")
        texts.append(t)
        while t.get_window_extent(renderer=r).width > 0.995 * fig.bbox.width and t.get_fontsize() > 6.5:
            t.set_fontsize(t.get_fontsize() - 0.25)
        if t.get_window_extent(renderer=r).width > 0.995 * fig.bbox.width:
            for t in texts:
                t.remove()
            return False
    print(f"note: {len(lines)} line(s) at {texts[0].get_fontsize():.2f} pt")
    return True


# ----------------------------------------------------------------------------------------------------------------------
# Figure 1: the PRI's presidential vote, 1929-2000
# ----------------------------------------------------------------------------------------------------------------------
# The leading opposition candidate of each election (the most votes after the PRI; none in 1976): surname and the column of the
# state panel that holds his votes (`rebel` = ex-PRI dissident, `pan` = PAN; 1934 Villarreal is pooled in `other`, read from
# Ramirez Rancano). Only five are labelled on the plot.
LEADING = {1929: ("Vasconcelos", "rebel"), 1934: ("Villarreal", "rr"), 1940: ("Almazán", "rebel"), 1946: ("Padilla", "rebel"),
           1952: ("Henríquez", "rebel"), 1958: ("Álvarez", "pan"), 1964: ("González Torres", "pan"), 1970: ("González Morfín", "pan"),
           1982: ("Madero", "pan"), 1988: ("Cárdenas", "rebel"), 1994: ("Fernández de Cevallos", "pan"), 2000: ("Fox", "pan")}
LABELLED = {1940, 1946, 1952, 1988, 2000}


def votes_by_state():
    """State panel 1929-2000: election, edon, state, pri, rebel, pan, other, valid (the panel's columns)."""
    W = pd.read_csv(PANEL)
    assert sorted(W.election.unique()) == [1934, 1940, 1946, 1952, 1958, 1964, 1970, 1976, 1982, 1988, 1994]
    states = W.drop_duplicates("edon").set_index("edon")["state"]
    # 1929: Ramirez Rancano's table 29 (Colegio Electoral count). The state cells add up to the printed national row.
    rr = pd.read_csv(ELEC / "ramirez_rancano" / "ramirez_rancano_presidential_by_state_1917_1970.csv")
    r = rr[(rr.election_year == 1929) & (rr.edon > 0) & (rr.candidate != "TOTAL (printed row total)")]
    r = r.pivot_table(index="edon", columns="candidate", values="votes", aggfunc="sum")
    nat = rr[(rr.election_year == 1929) & (rr.edon == 0)].set_index("candidate")["votes"]
    for c in ["Pascual Ortiz Rubio", "Jose Vasconcelos", "Triana"]:
        assert r[c].sum() == nat[c], (c, r[c].sum(), nat[c])
    d29 = pd.DataFrame({"election": 1929, "edon": r.index, "state": states.reindex(r.index).values,
                        "source": "Ramirez Rancano 1977 (Colegio Electoral count)", "pri": r["Pascual Ortiz Rubio"].values,
                        "rebel": r["Jose Vasconcelos"].values, "pan": 0, "other": r["Triana"].values})
    # 2000: IFE computo by state via Magar. Fox = Alianza por el Cambio (PAN + PVEM lines) -> `pan`; Cardenas = Alianza por
    # Mexico (PRD + PT-Convergencia-PSN-PAS lines) -> `rebel`; `efec` = valid votes = the sum of the party lines.
    mg = pd.read_csv(ELEC / "magar_elecRetrns" / "data" / "pred1964-on.csv")
    m = mg[mg.yr == 2000].set_index("edon")
    long = pd.concat([pd.DataFrame({"edon": m.index.values, "label": m[f"l{i:02d}"].values, "votes": m[f"v{i:02d}"].values}) for i in range(1, 13)]).dropna()
    grp = long.label.map(lambda l: "pri" if l == "pri" else "pan" if l in {"pan", "pvem", "pan-pvem"}
                         else "rebel" if l in {"prd", "pt-conve-psn-pas", "prd-pt-conve-psn-pas"} else "other")
    v = long.assign(grp=grp).pivot_table(index="edon", columns="grp", values="votes", aggfunc="sum")
    assert (v.sum(axis=1) == m.efec).all()
    assert v.pan.sum() == 15_989_636 and v.pri.sum() == 13_579_718 and v.rebel.sum() == 6_256_780, v.sum()  # IFE's official totals
    d00 = pd.DataFrame({"election": 2000, "edon": v.index, "state": states.reindex(v.index).values, "source": "IFE via Magar",
                        "pri": v.pri.values, "rebel": v.rebel.values, "pan": v.pan.values, "other": v.other.values})
    W = pd.concat([d29, W[d29.columns], d00], ignore_index=True)
    W["valid"] = W[["pri", "rebel", "pan", "other"]].sum(axis=1)
    for c in ["pri", "rebel", "pan"]:
        W[f"{c}_share"] = W[c] / W.valid
    return W


def minor_candidates_check(shown):
    """No candidate outside the panel's dissident and PAN columns reaches 5% of the valid vote: candidate rows of Ramirez Rancano 1929-52 (1958-70 print
    PRI and PAN only; the other 1970 lines ran Echeverria) and the party lines of Magar/IFE 1976-2000."""
    rr = pd.read_csv(ELEC / "ramirez_rancano" / "ramirez_rancano_presidential_by_state_1917_1970.csv")
    out = {}
    for e in [1929, 1934, 1940, 1946, 1952]:
        x = rr[(rr.election_year == e) & (rr.edon > 0) & (rr.candidate != "TOTAL (printed row total)")].groupby("candidate").votes.sum()
        out[e] = (x / x.sum()).sort_values(ascending=False).round(3).to_dict()
    mg = pd.read_csv(ELEC / "magar_elecRetrns" / "data" / "pred1964-on.csv")
    for e in [1976, 1982, 1994, 2000]:  # 1988 rows are mislabelled in Magar (README); the panel uses CEDE: PRI, FDN, PAN, PDM, PRT
        x = mg[mg.yr == e]
        out[e] = {x[f"l{i:02d}"].dropna().iloc[0]: round(x[f"v{i:02d}"].sum() / x.efec.sum(), 3) for i in range(1, 13) if x[f"l{i:02d}"].notna().any()}
    shown_lines = {1929: {"Ortiz Rubio", "Vasconcelos"}, 1934: {"Cardenas"}, 1940: {"Avila Camacho", "Almazan"},
                   1946: {"Aleman", "Padilla"}, 1952: {"Ruiz Cortines", "Henriquez", "Gonzalez Luna"},
                   1976: {"pri", "pps-parm"}, 1982: {"pri", "pps-parm", "pan"}, 1994: {"pri", "pan", "prd"},
                   2000: {"pri", "pan", "pvem", "pan-pvem", "prd", "pt-conve-psn-pas", "prd-pt-conve-psn-pas"}}
    for e, d in out.items():
        rest = {k: v for k, v in d.items() if not any(w in k for w in shown_lines[e])}
        print(f"  {e}: all lines {d}; not shown {rest}")
        assert max(rest.values(), default=0) < 0.05, (e, rest)
    print(f"  1988 (CEDE): PDM {shown.loc[1988, 'other'] / shown.loc[1988, 'valid']:.3f} incl. PRT; both below 5%")


def pri_vote():
    W = votes_by_state()
    nat = W.groupby("election")[["pri", "rebel", "pan", "other", "valid"]].sum()
    for c in ["pri", "rebel", "pan"]:
        nat[f"{c}_share"] = nat[c] / nat.valid
    rng = W.groupby("election").apply(lambda d: pd.Series({
        "n_states": len(d), "pri_share_min": d.pri_share.min(), "state_min": d.loc[d.pri_share.idxmin(), "state"],
        "pri_share_max": d.pri_share.max(), "state_max": d.loc[d.pri_share.idxmax(), "state"],
        "source": d.source.iloc[0]}), include_groups=False)
    nat = nat.join(rng)
    # leading opposition candidate per election
    rr = pd.read_csv(ELEC / "ramirez_rancano" / "ramirez_rancano_presidential_by_state_1917_1970.csv")
    r34 = rr[(rr.election_year == 1934) & (rr.edon > 0) & (rr.candidate != "TOTAL (printed row total)")].groupby("candidate").votes.sum()
    nat["opposition"] = [LEADING.get(e, ("", ""))[0] for e in nat.index]
    nat["opposition_share"] = [r34["Antonio Villarreal"] / r34.sum() if c == "rr" else nat.loc[e, f"{c}_share"] if c else float("nan")
                               for e, (_, c) in ((e, LEADING.get(e, ("", ""))) for e in nat.index)]
    for e, (_, c) in LEADING.items():  # the leading candidate is the larger of the dissident and PAN columns
        assert c == "rr" or nat.loc[e, f"{c}_share"] == max(nat.loc[e, "rebel_share"], nat.loc[e, "pan_share"]), e
    assert pd.isna(nat.loc[1976, "opposition_share"])
    print("leading opposition candidate per election (share of the valid vote):")
    print(nat[["opposition", "opposition_share"]].assign(opposition_share=lambda d: (100 * d.opposition_share).round(1)).to_string())
    print("minor lines check:")
    minor_candidates_check(nat)
    nat.to_csv(OUT / "pri_vote_data.csv")
    W.to_csv(OUT / "pri_vote_states.csv", index=False)
    print(nat[["pri_share", "pri_share_min", "state_min", "pri_share_max", "state_max", "n_states"]].round(3).to_string())

    yrs = nat.index.values
    fig, ax = plt.subplots(figsize=SIZE, dpi=200)
    fig.patch.set_facecolor("white")
    style(ax)
    # the nine successions studied, 1940-88
    ax.axvspan(1937, 1991, color=Z7, zorder=0, lw=0)
    ax.text(1964, 1.0, "1940–1988 successions", transform=ax.get_xaxis_transform(), ha="center", va="bottom", fontsize=9, color=Z6)
    # every state (small translucent dots, jittered), the PRI's national share (dark red line)
    jit = np.random.default_rng(0).uniform(-0.9, 0.9, len(W))
    ax.plot(W.election + jit, 100 * W.pri_share, "o", color=ACC, alpha=0.25, ms=2.8, mec="none", zorder=1.5)
    ax.plot(yrs, 100 * nat.pri_share, "-o", color=ACC, lw=1.8, ms=5.5, zorder=4)
    # the leading opposition candidate (hollow marker), five of them labelled
    opp = nat.dropna(subset=["opposition_share"])
    ax.plot(opp.index, 100 * opp.opposition_share, "o", mfc="white", mec=Z6, mew=1.1, ms=5.5, ls="none", zorder=3)
    for e in LABELLED:
        sh = 100 * nat.loc[e, "opposition_share"]
        ax.text(e + 1.3, sh, f"{nat.loc[e, 'opposition']} {sh:.0f}%", ha="left", va="center", fontsize=8.5, color=Z6)
    # key numbers
    ax.text(1976, 100 * nat.loc[1976, "pri_share"] + 2.2, "100%: no registered opponent", ha="center", va="bottom", fontsize=8.5, color=ACC)
    ax.text(1988 + 1.3, 100 * nat.loc[1988, "pri_share"] - 0.5, f"{100 * nat.loc[1988, 'pri_share']:.0f}%", ha="left", va="top", fontsize=8.5, color=ACC)
    ax.text(2000 + 1.3, 100 * nat.loc[2000, "pri_share"] - 0.5, f"{100 * nat.loc[2000, 'pri_share']:.0f}%", ha="left", va="top", fontsize=8.5, color=ACC)
    # key (upper right, the empty corner after 1991)
    handles = [Line2D([0], [0], color=ACC, marker="o", ms=5.5, lw=1.8),
               Line2D([0], [0], color=ACC, marker="o", ms=2.8, lw=0, alpha=0.25, mec="none"),
               Line2D([0], [0], color="white", marker="o", ms=5.5, lw=0, mec=Z6, mew=1.1)]
    leg = ax.legend(handles, ["PRI (PNR, PRM) candidate,\nnational share", "state shares", "leading opposition candidate"],
                    loc="upper right", bbox_to_anchor=(1.0, 0.985), frameon=False, fontsize=7.5, handlelength=1.6, labelspacing=0.5, borderaxespad=0)
    for t in leg.get_texts():
        t.set_color(Z6)
    ax.set_xticks(yrs)
    ax.set_xticklabels([str(y) for y in yrs], fontsize=9)
    ax.set_xlim(1925.5, 2013)
    ax.set_ylim(-3, 108)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_ylabel("Share of the valid vote, %", fontsize=10.5, color=INK)
    ax.set_xlabel("Presidential election", fontsize=10.5, color=INK)
    one = ("Source: official counts by state — Colegio Electoral 1929–70 (Ramírez Rancaño 1977); CFE 1976–88 (Magar 2012; CEDE 1988); "
           "IFE 1994–2000 (Magar 2012). PRI incl. the allied PPS–PARM lines, 1970–82.")
    assert note(fig, [one])
    fig.subplots_adjust(left=0.075, right=0.99, top=0.93, bottom=0.17)
    save(fig, "pri_vote")
    return nat


# ----------------------------------------------------------------------------------------------------------------------
# Figure 2: land granted by president, 1916-1992
# ----------------------------------------------------------------------------------------------------------------------
PRESIDENTS = [  # name in the ledger, label, term, INEGI term (None: 1915-34 is one INEGI period for seven presidents)
    ("Venustiano Carranza", "Carranza", "1916–20", None),
    ("Adolfo de la Huerta", "de la Huerta", "1920", None),
    ("Alvaro Obregon", "Obregón", "1920–24", None),
    ("Plutarco Elias Calles", "Calles", "1924–28", None),
    ("Emilio Portes Gil", "Portes Gil", "1928–30", None),
    ("Pascual Ortiz Rubio", "Ortiz Rubio", "1930–32", None),
    ("Abelardo L. Rodriguez", "Rodríguez", "1932–34", None),
    ("Lazaro Cardenas", "Cárdenas", "1934–40", "1935-1940"),
    ("Manuel Avila Camacho", "Ávila Camacho", "1940–46", "1941-1946"),
    ("Miguel Aleman Valdes", "Alemán", "1946–52", "1947-1952"),
    ("Adolfo Ruiz Cortines", "Ruiz Cortines", "1952–58", "1953-1958"),
    ("Adolfo Lopez Mateos", "López Mateos", "1958–64", "1959-1964"),
    ("Gustavo Diaz Ordaz", "Díaz Ordaz", "1964–70", "1965-1970"),
    ("Luis Echeverria Alvarez", "Echeverría", "1970–76", "1971-1976"),
    ("Jose Lopez Portillo", "López Portillo", "1976–82", "1977-1982"),
    ("Miguel de la Madrid Hurtado", "de la Madrid", "1982–88", "1983-1988"),
    ("Carlos Salinas de Gortari", "Salinas", "1988–92", "1989-1992"),
]


def land_by_president():
    cols = ["action_id", "president_signing", "president_source", "is_land_grant", "hectares_total", "ha_agostadero", "beneficiaries"]
    L = pd.read_csv(LAND / "agrarian_actions_1916_1992.csv", usecols=cols, low_memory=False)
    G = L[L.is_land_grant == 1]
    names = [p[0] for p in PRESIDENTS]
    assert set(G.president_signing.dropna()) == set(names), set(G.president_signing.dropna()) ^ set(names)
    g = G.groupby("president_signing").agg(hectares=("hectares_total", "sum"), ha_agostadero=("ha_agostadero", "sum"),
                                           beneficiaries=("beneficiaries", "sum"), resolutions=("action_id", "size"),
                                           hectares_missing=("hectares_total", lambda s: int(s.isna().sum()))).reindex(names)
    g.insert(0, "president", [p[1] for p in PRESIDENTS])
    g.insert(1, "term", [p[2] for p in PRESIDENTS])
    g["ehm_term"] = [p[3] for p in PRESIDENTS]
    una = G[G.president_signing.isna()]
    print(f"unattributed land-grant rows left out of the bars: {len(una)} rows, {una.hectares_total.sum() / 1e6:.2f} M ha, "
          f"{una.beneficiaries.sum() / 1e3:.0f} thousand beneficiaries ({una.president_source.fillna('no president').value_counts().to_dict()})")
    tot_ha, tot_ben = G.hectares_total.sum(), G.beneficiaries.sum()
    g["share_hectares"] = g.hectares / tot_ha
    g["share_beneficiaries"] = g.beneficiaries / tot_ben
    # INEGI EHM 2014 (national rows), by presidential term
    e = pd.read_csv(LAND / "ehm2014_land_by_state_term.csv")
    e = e[(e.state_code == 0) & (e.table.isin([9.50, 9.51])) & (e.measure.isin(["hectares", "beneficiaries"]))]
    e = e.pivot_table(index="ehm_term", columns="measure", values="value")
    g["inegi_hectares"] = g.ehm_term.map(e.hectares)
    g["inegi_beneficiaries"] = g.ehm_term.map(e.beneficiaries)
    g["ratio_hectares"] = g.hectares / g.inegi_hectares
    g["ratio_beneficiaries"] = g.beneficiaries / g.inegi_beneficiaries
    g.to_csv(OUT / "land_by_president_data.csv", index=False)
    early = g[g.ehm_term.isna()]
    print(f"1916-34 (seven presidents): ledger {early.hectares.sum() / 1e6:.2f} M ha vs INEGI 1915-34 {e.loc['1915-1934', 'hectares'] / 1e6:.2f}; "
          f"beneficiaries {early.beneficiaries.sum() / 1e3:.0f} vs {e.loc['1915-1934', 'beneficiaries'] / 1e3:.0f} thousand")
    print(f"1916-92 total: ledger {tot_ha / 1e6:.1f} M ha, {tot_ben / 1e6:.2f} M beneficiaries; INEGI 1915-Feb 1992 "
          f"{(e.hectares.sum() - e.loc['1900-1992', 'hectares'] - e.loc['1900-1914', 'hectares']) / 1e6:.1f} M ha, "
          f"{(e.beneficiaries.sum() - e.loc['1900-1992', 'beneficiaries'] - e.loc['1900-1914', 'beneficiaries']) / 1e6:.2f} M")
    show = g[["president", "term", "hectares", "inegi_hectares", "ratio_hectares", "beneficiaries", "inegi_beneficiaries", "ratio_beneficiaries", "share_hectares", "share_beneficiaries", "hectares_missing"]].copy()
    for c in ["hectares", "inegi_hectares"]:
        show[c] = show[c] / 1e6
    for c in ["beneficiaries", "inegi_beneficiaries"]:
        show[c] = show[c] / 1e3
    print(show.round(2).to_string(index=False))

    n = len(g)
    y = list(range(n))[::-1]  # Carranza at the top
    fig, (ax, bx) = plt.subplots(1, 2, figsize=SIZE, dpi=200, sharey=True, gridspec_kw={"width_ratios": [1.55, 1]})
    fig.patch.set_facecolor("white")
    ic, io = g.index.get_loc("Lazaro Cardenas"), g.index.get_loc("Gustavo Diaz Ordaz")
    colors = [ACC if i == ic else Z4 for i in range(n)]
    for a, col, scale, fmt, xlab, icol, inside in [  # icol: INEGI column, kept in the csv only
            (ax, "hectares", 1e6, "{:.1f}", "Hectares granted, millions", "inegi_hectares", f"{100 * g.share_hectares.iloc[ic]:.0f}% of all land granted 1916–92"),
            (bx, "beneficiaries", 1e3, "{:.0f}", "Beneficiaries, thousands", "inegi_beneficiaries", f"{100 * g.share_beneficiaries.iloc[ic]:.0f}% of all beneficiaries 1916–92")]:
        style(a)
        vals = g[col].values / scale
        xmax = vals.max() * 1.4
        a.barh(y, vals, height=0.66, color=colors, zorder=2)
        for i, (yi, v) in enumerate(zip(y, vals)):
            lab = fmt.format(v)
            if i == io and col == "hectares":
                lab += f" ({100 * g.ha_agostadero.iloc[io] / g.hectares.iloc[io]:.0f}% pasture)"
            a.text(v + 0.012 * xmax, yi, lab, va="center", ha="left", fontsize=8, color=ACC if i == ic else Z6, zorder=4)
        a.text(0.012 * xmax, y[ic], inside, va="center", ha="left", fontsize=8.5, color="white", zorder=4)
        a.set_xlabel(xlab, fontsize=10.5, color=INK)
        a.spines["left"].set_visible(False)
        a.tick_params(axis="y", length=0)
        a.set_xlim(0, xmax)
        a.set_xticks([t for t in a.get_xticks() if t <= 0.95 * xmax])
    ax.set_yticks(y)
    ax.set_yticklabels([f"{p}  {t}" for p, t in zip(g.president, g.term)], fontsize=8.5, color=INK)
    ax.set_ylim(-0.7, n - 0.3)
    # one measure only: the ledger, by signing president (INEGI's term totals are checked above, in the console and the csv, not drawn)
    note(fig, ["Source: Sanderson (1984), 1916–76; Diario Oficial resolutions, 1976–92; by signing president. 1977–92 incomplete: some resolutions lack published text."])
    fig.subplots_adjust(left=0.185, right=0.99, top=0.98, bottom=0.155, wspace=0.08)
    save(fig, "land_by_president")
    return g


if __name__ == "__main__":
    pri_vote()
    land_by_president()
