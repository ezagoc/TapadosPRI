"""Deck macros (4 November 2026): selection into Camp's dictionary and the predetermined-inclusion check.

Camp (2011, pp. xv-xvii) includes a politician who reached Brandenburg's top six prestige levels (rung 7 or above on our
ladder), the national leadership of an opposition party, or the rectorship of UNAM/IPN or a UNAM school directorship,
at some point up to 2009 (estimate_main.R, `first_qualifying`). For the followers in the main sample
(analysis_sample.csv) this writes the share whose first qualifying post started after e-2 (their presence in the data
depends on the career after the succession) and the share with no qualifying post at all (in the book through the
weaker routes, two deputy terms and the like). It also reads the main window estimate of the predetermined-inclusion
run (TAPADOS_INCLUSION=predetermined, output/main_direct_tie/robust_predetermined_inclusion/main_result.csv, MAIN_SPEC
section 13) next to the main one. Env vars as estimate_main.R. Writes tables/dictionary_inclusion_macros.tex and
dictionary_inclusion.csv.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import numpy as np
import pandas as pd

db_root = Path(os.environ.get("TAPADOSPRI_DB_ROOT", Path.home() / "Dropbox" / "TapadosPRI"))
data_dir = Path(os.environ.get("TAPADOSPRI_DATA_DIR", db_root / "data"))
out_dir = Path(os.environ.get("TAPADOS_MAIN_OUTPUT_DIR", db_root / "output" / "main_direct_tie"))
tab_dir = out_dir / "tables"
tab_dir.mkdir(parents=True, exist_ok=True)

QUALIFYING_RX = re.compile(r"rector.*(?:unam|national autonomous|polytechnic|ipn)|"
                           r"director.*(?:school|faculty) of (?:law|economics|medicine).*(?:unam|national autonomous)", re.I)
pos = pd.read_csv(data_dir / "rank" / "position_tiers.csv", low_memory=False)
qual = pos[pos.year_start.notna() & ((np.floor(pos.hybrid_rank + 1e-9) >= 7)
                                      | (pos.rule == "opposition_national_leadership")
                                      | pos.role_text.astype(str).str.contains(QUALIFYING_RX))]
first_qualifying = qual.groupby("person_id").year_start.min()

s = pd.read_csv(out_dir / "analysis_sample.csv")
s["first_qualifying"] = s.pid.map(first_qualifying)
s["never"] = s.first_qualifying.isna()
s["after"] = s.never | (s.first_qualifying > s.election - 2)
rows = []
for treated, label in ((1, "designee"), (0, "losers")):
    g = s[s.treated == treated]
    rows.append({"group": label, "n": len(g), "share_after_e2": g.after.mean(), "share_never": g.never.mean()})
summary = pd.DataFrame(rows)
summary.to_csv(out_dir / "dictionary_inclusion.csv", index=False)
print(summary.to_string(index=False))

pct = lambda x: f"{100 * x:.0f}"
mac = ["% dictionary_inclusion_macros.tex (dictionary_inclusion.py). Do not edit by hand."]
for r in summary.itertuples():
    key = "D" if r.group == "designee" else "P"
    mac += [f"\\newcommand{{\\DictAfter{key}}}{{{pct(r.share_after_e2)}}}", f"\\newcommand{{\\DictNever{key}}}{{{pct(r.share_never)}}}"]


def window(path: Path) -> dict | None:
    if not path.exists():
        print("missing", path)
        return None
    r = pd.read_csv(path).iloc[0]
    return {"est": r.estimate, "lo": r.ci_lower, "hi": r.ci_upper, "n": int(r.total_person_successions), "people": int(r.unique_people)}


main = window(out_dir / "main_result.csv")
pred = window(out_dir / "robust_predetermined_inclusion" / "main_result.csv")
for key, w in (("Main", main), ("Pred", pred)):
    if w is None:
        continue
    mac += [f"\\newcommand{{\\Dict{key}Est}}{{{w['est']:.2f}}}", f"\\newcommand{{\\Dict{key}Lo}}{{{w['lo']:.2f}}}",
            f"\\newcommand{{\\Dict{key}Hi}}{{{w['hi']:.2f}}}", f"\\newcommand{{\\Dict{key}N}}{{{w['n']:,}}}"]
    print(key, f"{w['est']:.2f} [{w['lo']:.2f}, {w['hi']:.2f}], n = {w['n']}")
(tab_dir / "dictionary_inclusion_macros.tex").write_text("\n".join(mac) + "\n", encoding="utf-8")
