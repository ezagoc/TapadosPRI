"""Slide figure: how a succession slate is built, with the 1970 race as the example (minimal version).

Rows: the names in contention for 1970 (the audited pool). Columns: five source groups, the same for every
succession: Camp's biographies; historians (Smith 1979 and the monographs on each succession); insiders
(Castañeda's 1999 interviews, memoirs, letters); intelligence files (DFS secret-police reports; U.S. State
Department cables and FRUS); and the press and polls before the destape (Mexican weeklies and IMOP polls read in
the audit; U.S. dailies via ProQuest TDM: at least PRESS_MIN articles in the 24 months before the destape naming
the person together with another contender).
A filled dot = a source in that group names the person as a contender. Two or more groups: in the slate; one: marginal.
The slate rule proper counts independent source families (two monographs are two families); the script prints
every name whose group count and family count would disagree (only 1946-1964 names carried by two historians).
Below: the nine slates 1940-1988 under the audited rule plus the press family (1940: PRM pre-candidates; 1988: the
party's official six), one square per name.
Output: OUTPUT_DIR/slides/slate_1970.{png,pdf}
"""
import sys
from pathlib import Path
import pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import DATA_DIR, OUTPUT_DIR  # noqa: E402

ACC, INK, Z3, Z4, Z5, Z6, Z8 = "#940034", "#111111", "#d4d4d8", "#a1a1aa", "#71717a", "#52525b", "#27272a"
OUT = OUTPUT_DIR / "slides"; OUT.mkdir(parents=True, exist_ok=True)
PRESS_MIN = 2
GOV = {"MXGOV", "USGOV"}                                                      # DFS reports; State Dept cables, FRUS
INSIDERS = {"castaneda", "santos", "ortega", "hernandez campos", "scherer", "marte r. gomez"}   # memoirs, interviews, letters
PRESSPOLL = lambda f: f.startswith("press:") or f == "IMOP"                    # outlets and polls read in the audit

verd = pd.read_csv(DATA_DIR / "candidates" / "slate_verdicts.csv")
cand = pd.read_csv(DATA_DIR / "candidates" / "corcholatas_matched.csv")
press = pd.read_csv(DATA_DIR / "ProQuest" / "hopeful_mentions_articles.csv")
press["date"] = pd.to_datetime(press.date, errors="coerce"); press["destape"] = pd.to_datetime(press.destape)
m = (press.destape - press.date).dt.days / 30.44
race = press[(m > 0) & (m <= 24) & (press.n_hopefuls_in_article >= 2)].groupby(["election_year", "hopeful"]).goid.nunique()


def families(e, name):
    """Set of the five uniform families naming `name` as a contender for succession e."""
    row = verd[(verd.election_year == e) & (verd.name == name)]
    fams = set(f.strip() for fs in row.families.dropna() for f in str(fs).split(";"))
    out = set()
    if "camp" in fams: out.add("camp")
    if fams & INSIDERS: out.add("insiders")
    if fams & GOV: out.add("gov")
    if any(PRESSPOLL(f) for f in fams) or race.get((e, name), 0) >= PRESS_MIN: out.add("press")
    if fams - {"camp"} - INSIDERS - GOV - {f for f in fams if PRESSPOLL(f)}: out.add("hist")   # smith and the monographs
    return out


FAM = [("camp", "Camp\nbiographies"), ("hist", "Historians\nSmith (1979),\nmonographs"),
       ("insiders", "Insiders\nCastañeda (1999),\nmemoirs"), ("gov", "Intelligence files\nDFS, U.S.\nState Dept."),
       ("press", "Press and polls\nbefore the\ndestape")]
# consistency: where would 'two or more groups' differ from the rule's 'two or more families' (+ the ProQuest press family)?
for r in verd[verd.verdict != "EXCLUDE"].itertuples():
    n_fam = int(r.n_families) + (1 if race.get((r.election_year, r.name), 0) >= PRESS_MIN else 0)
    n_grp = len(families(r.election_year, r.name))
    if (n_fam >= 2) != (n_grp >= 2):
        print(f"  groups vs families disagree: {r.election_year} {r.name}: families={n_fam} groups={n_grp} ({r.families})")
v70 = verd[(verd.election_year == 1970) & (verd.verdict != "EXCLUDE")]
rows = []
for name in v70.name:
    f = families(1970, name)
    rows.append((name, f, len(f) >= 2))
rows.sort(key=lambda r: (-r[2], r[0] != "Luis Echeverría Álvarez", -len(r[1]), r[0]))

W, H = 13.33, 6.8
fig = plt.figure(figsize=(W, H), dpi=200); fig.patch.set_facecolor("white")
ax = fig.add_axes([0, 0.33, 1, 0.67]); ax.set_xlim(0, W); ax.set_ylim(0.3, 4.86); ax.axis("off")   # 1 unit = 1 in
x_name, x0, dx = 1.0, 6.9, 1.25
y_top, dy = 3.95, 0.34
for j, (_, lab) in enumerate(FAM):
    ax.text(x0 + j * dx, y_top + 0.36, lab, ha="center", va="bottom", fontsize=8.2, color=Z6, linespacing=1.15)
n_in = sum(r[2] for r in rows)
for i, (name, fams, admitted) in enumerate(rows):
    y = y_top - i * dy - (0 if admitted else 0.42)
    win = name == "Luis Echeverría Álvarez"
    col = ACC if win else (INK if admitted else Z5)
    ax.text(x_name, y, name, ha="left", va="center", fontsize=10, color=col, weight="bold" if win else "normal")
    if win:
        ax.text(x_name + 2.75, y, "designated 21 Oct 1969", ha="left", va="center", fontsize=8, color=ACC, style="italic")
    for j, (key, _) in enumerate(FAM):
        if key in fams:
            ax.add_patch(Circle((x0 + j * dx, y), 0.085, color=ACC if win else (Z8 if admitted else Z4), lw=0))
        else:
            ax.add_patch(Circle((x0 + j * dx, y), 0.085, facecolor="white", edgecolor=Z3, lw=0.8))
y_sep = y_top - (n_in - 0.5) * dy - 0.21
ax.plot([x_name, x0 + 4 * dx + 0.4], [y_sep, y_sep], color=ACC, lw=1.0, ls=(0, (4, 3)))
ax.text(x0 + 4 * dx + 0.45, y_sep + 0.05, "named by two or more independent sources: in the slate", ha="right", va="bottom", fontsize=8.5, color=ACC, style="italic")
ax.text(x0 + 4 * dx + 0.45, y_sep - 0.05, "named by one: marginal (robustness only)", ha="right", va="top", fontsize=8.5, color=Z5, style="italic")

# bottom: the nine slates under the same rule
bx = fig.add_axes([0, 0, 1, 0.33]); bx.set_xlim(0, W); bx.set_ylim(0, 2.24); bx.axis("off")
s, gap = 0.17, 0.045
strip = [(range(1940, 1965, 6), 1.55), (range(1970, 1989, 6), 0.72)]
for years, yb in strip:
    xs = 1.0
    for e in years:
        winners = set(cand[(cand.election_year == e) & (cand.role == "winner")].corcholata_name)
        names = []
        if e in (1940, 1988):                       # given slates: the PRM pre-candidates; the party's official six
            for r in cand[(cand.election_year == e) & (cand.in_main_slate == 1)].itertuples():
                names.append(("in", r.corcholata_name in winners))
        else:                                        # audited rule (all qualifying families found) + the press family
            for r in verd[(verd.election_year == e) & (verd.verdict != "EXCLUDE")].itertuples():
                n_fam = int(r.n_families) + (1 if race.get((e, r.name), 0) >= PRESS_MIN else 0)
                names.append(("in" if n_fam >= 2 else "marginal", r.name in winners))
        names.sort(key=lambda t: (t[0] != "in", not t[1]))
        x = xs
        for status, win in names:
            if status == "in":
                bx.add_patch(Rectangle((x, yb), s, s, color=ACC if win else Z8, lw=0))
            else:
                bx.add_patch(Rectangle((x, yb), s, s, facecolor="white", edgecolor=Z4, lw=0.9))
            x += s + gap
        n_in_e = sum(st == "in" for st, _ in names); n_m = len(names) - n_in_e
        bx.text(xs, yb - 0.08, f"{e}   {n_in_e} in" + (f" · {n_m} marginal" if n_m else ""), fontsize=8, color=Z6, va="top")
        xs = x + 0.5
lx, ly = 1.0, 0.12
for off, col, edge, lab in [(0, ACC, None, "designee"), (1.4, Z8, None, "in the slate"), (3.1, "white", Z4, "marginal")]:
    bx.add_patch(Rectangle((lx + off, ly), 0.16, 0.16, facecolor=col, edgecolor=edge or col, lw=0.9))
    bx.text(lx + off + 0.24, ly + 0.08, lab, fontsize=8, color=INK, va="center")
fig.savefig(OUT / "slate_1970.png", dpi=200, facecolor="white"); fig.savefig(OUT / "slate_1970.pdf", facecolor="white")
print("saved;", "1970 in the slate:", n_in, "of", len(rows))
