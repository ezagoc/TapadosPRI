"""Deck table (4 November 2026): the 1946 followers one by one, for the example slides.

One Econometrica-style tabular per contender with followers in the main sample (analysis_sample.csv of
estimate_main.R): follower, highest rank 1941-44 (pre), highest rank 1947-50 (post) and the change in rungs
(+2, +1, -- for none, -1 ...), with a mean row. Names with accents come from biographies_corrected.csv, matched on
the letters of Camp's cleaned name. Env vars as estimate_main.R (TAPADOSPRI_DB_ROOT, TAPADOSPRI_DATA_DIR,
TAPADOS_MAIN_OUTPUT_DIR). Writes tables/followers_1946_<key>.tex, tables/followers_1946_macros.tex and
followers_1946.csv in the output folder.
"""
from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path

import pandas as pd

ELECTION = 1946
db_root = Path(os.environ.get("TAPADOSPRI_DB_ROOT", Path.home() / "Dropbox" / "TapadosPRI"))
data_dir = Path(os.environ.get("TAPADOSPRI_DATA_DIR", db_root / "data"))
out_dir = Path(os.environ.get("TAPADOS_MAIN_OUTPUT_DIR", db_root / "output" / "main_direct_tie"))
tab_dir = out_dir / "tables"
tab_dir.mkdir(parents=True, exist_ok=True)

SHORT = {"Aleman Valdes, Miguel": ("aleman", "Alem\\'an"), "Padilla Penalosa, Ezequiel": ("padilla", "Padilla"),
         "Baz de Prada, Gustavo": ("baz", "Baz"), "Rojo Gomez, Javier": ("rojo_gomez", "Rojo G\\'omez")}
PARTICLES = {"de", "la", "las", "los", "del", "y", "e"}
# Names Camp's OCR text garbles (cleaned name in the nodes file -> display name).
NAME_FIXES = {"Bustamante, Vasconcelos, Miguel e": "Bustamante Vasconcelos, Miguel E."}
ACCENTS = {"á": "\\'a", "é": "\\'e", "í": "\\'i", "ó": "\\'o", "ú": "\\'u", "ñ": "\\~n", "ü": '\\"u',
           "Á": "\\'A", "É": "\\'E", "Í": "\\'I", "Ó": "\\'O", "Ú": "\\'U", "Ñ": "\\~N"}


def letters(x: str) -> str:
    x = re.sub(r"\(Deceased[^)]*\)", "", str(x), flags=re.I)
    x = unicodedata.normalize("NFKD", x).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", x.lower())


def pretty(raw: str) -> str:
    """'aleMán (valdés), Miguel (Deceased May 14, 1983)' -> 'Alemán Valdés, Miguel'."""
    x = re.sub(r"\(Deceased[^)]*\)", "", str(raw), flags=re.I)
    x = re.sub(r"[()]", "", x)
    x = re.sub(r"\s+", " ", x).strip().strip(",")
    words = []
    for w in x.split():
        core = w.strip(",.")
        if core.lower() in PARTICLES:
            words.append(w.lower())
        elif len(core) == 1:                      # an initial
            words.append(core.upper() + "." + ("," if w.endswith(",") else ""))
        elif core.lower() in {"jr", "jr."}:
            words.append("Jr." + ("," if w.endswith(",") else ""))
        else:
            words.append(w[0].upper() + w[1:].lower())
    return " ".join(words)


def initials(name: str) -> str:
    """'Aguirre Beltrán, Gonzalo' -> 'Aguirre Beltrán, G.'; 'Sánchez, J. Salvador' -> 'Sánchez, J. S.'."""
    if "," not in name:
        return name
    surname, given = name.split(",", 1)
    parts = []
    for w in given.replace(",", " ").split():
        if w.lower().startswith("jr"):
            continue                                   # no room for "Jr." on the slide
        parts.append(w[0].upper() + ".")
    return surname.strip() + ", " + " ".join(parts)


def tex(x: str) -> str:
    return "".join(ACCENTS.get(c, c) for c in x)


sample = pd.read_csv(out_dir / "analysis_sample.csv")
sample = sample[sample.election == ELECTION].copy()
nodes = pd.read_csv(data_dir / "networks" / "network_nodes.csv").set_index("person_id")["name"]
bio = pd.read_csv(data_dir / "biographies_corrected.csv", usecols=["name"])
by_letters: dict[str, str] = {}
for n in bio.name.dropna():
    by_letters.setdefault(letters(n), n)


def display(pid: int) -> str:
    raw = nodes[pid]
    if raw in NAME_FIXES:
        return NAME_FIXES[raw]
    hit = by_letters.get(letters(raw))
    if hit is None:
        print("no accented name for", raw)
        return raw
    return pretty(hit)


sample["follower"] = sample.pid.map(display)
sample["contender"] = sample.patron.map(lambda p: nodes[p])
sample["change"] = sample.post - sample.pre
sample["sort_key"] = sample.follower.map(letters)
sample = sample.sort_values(["treated", "contender", "pre", "sort_key"], ascending=[False, True, False, True])
sample[["pid", "follower", "patron", "contender", "treated", "pre", "post", "change"]].to_csv(
    out_dir / "followers_1946.csv", index=False)


def signed(v: float, digits: int = 0) -> str:
    if abs(v) < 0.5 * 10 ** (-digits):
        return "--"
    s = f"{abs(v):.{digits}f}"
    return ("$+$" if v > 0 else "$-$") + s


macros = ["% followers_1946_macros.tex (followers_table_1946.py). Do not edit by hand."]
groups = {c: g for c, g in sample.groupby("contender", sort=False)}
keys = {c: SHORT.get(c, (re.sub(r"[^a-z]", "_", c.lower()), c.split(",")[0])) for c in groups}


def rows(g: pd.DataFrame, mean: bool = True, max_rows: int | None = None) -> list[str]:
    """One row per follower; with max_rows, the followers below the cap (ranked by pre) collapse into one row."""
    shown, rest = (g, g.iloc[0:0]) if max_rows is None or len(g) <= max_rows else (g.iloc[:max_rows], g.iloc[max_rows:])
    out = ["%s & %d & %d & %s \\\\" % (tex(initials(r.follower)), r.pre, r.post, signed(r.change)) for r in shown.itertuples()]
    if len(rest):
        out.append("%d others, ranks %d--%d in 1941--44 & %.1f & %.1f & %s \\\\" % (
            len(rest), rest.pre.min(), rest.pre.max(), rest.pre.mean(), rest.post.mean(), signed(rest.change.mean(), 1)))
    if mean:
        out += ["\\midrule", "Mean & %.1f & %.1f & %s \\\\" % (g.pre.mean(), g.post.mean(), signed(g.change.mean(), 1))]
    return out


HEAD = ["\\begin{tabular}{lccc}", "\\toprule", " & Rank & Rank & \\\\", " & 1941--44 & 1947--50 & Change \\\\", "\\midrule"]


def write(name: str, panels: list[tuple[str, pd.DataFrame]], mean: bool = True, max_rows: int | None = None) -> None:
    lines = ["%% %s.tex (followers_table_1946.py). Do not edit by hand." % name] + HEAD
    for i, (title, g) in enumerate(panels):
        if len(panels) > 1:
            if i > 0:
                lines.append("\\addlinespace[3pt]")
            lines.append("\\multicolumn{4}{l}{\\textit{%s, $n = %d$}} \\\\" % (title, len(g)))
        lines += rows(g, mean, max_rows)
    lines += ["\\bottomrule", "\\end{tabular}"]
    (tab_dir / f"{name}.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")


for contender, g in groups.items():
    key, short = keys[contender]
    write(f"followers_1946_{key}", [(f"{short}'s followers", g)])
    mkey = "".join(w.capitalize() for w in key.split("_"))
    macros += ["\\newcommand{\\Fol%sN}{%d}" % (mkey, len(g)),
               "\\newcommand{\\Fol%sMean}{%s}" % (mkey, signed(g.change.mean(), 1)),
               "\\newcommand{\\Fol%sUp}{%d}" % (mkey, (g.change > 0).sum()),
               "\\newcommand{\\Fol%sDown}{%d}" % (mkey, (g.change < 0).sum()),
               "\\newcommand{\\Fol%sNone}{%d}" % (mkey, (g.post == 0).sum())]
    print(f"{short}: n={len(g)} mean change {g.change.mean():+.2f}, up {(g.change > 0).sum()}, down {(g.change < 0).sum()}, no post {(g.post == 0).sum()}")
# the largest losing camp capped at 14 rows, the rest in one row (the deck shows it next to the designee's 13)
for contender, (key, short) in keys.items():
    if len(groups[contender]) > 16:
        write(f"followers_1946_{key}_top14", [("", groups[contender])], max_rows=14)
# the largest losing camp in two halves, to sit side by side on a slide (no mean row; the mean is a macro)
for contender, (key, short) in keys.items():
    g = groups[contender]
    if len(g) > 16:
        h = (len(g) + 1) // 2
        write(f"followers_1946_{key}_a", [("", g.iloc[:h])], mean=False)
        write(f"followers_1946_{key}_b", [("", g.iloc[h:])], mean=False)
# the two smaller losing camps in one two-panel table
small = [c for c in groups if keys[c][0] in ("baz", "rojo_gomez")]
if len(small) == 2:
    write("followers_1946_baz_rojo_gomez", [(f"{keys[c][1]}'s followers", groups[c]) for c in small])
d = sample[sample.treated == 1].change.mean()
p = sample[sample.treated == 0].change.mean()
ru = sample[sample.contender == "Padilla Penalosa, Ezequiel"].change.mean()      # the runner-up's followers
macros += ["\\newcommand{\\FolDesigneeMean}{%s}" % signed(d, 1), "\\newcommand{\\FolLosersMean}{%s}" % signed(p, 1),
           "\\newcommand{\\FolRawDiD}{%s}" % signed(d - p, 1),
           "\\newcommand{\\FolDesigneeVsRunnerUp}{%s}" % signed(d - ru, 1)]
(tab_dir / "followers_1946_macros.tex").write_text("\n".join(macros) + "\n", encoding="utf-8")
print(f"designee's followers mean change {d:+.2f}, losers' {p:+.2f}, raw DiD {d - p:+.2f}")
