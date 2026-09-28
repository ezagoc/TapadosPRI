"""
05_slate_verdicts.py

Apply the slate rule to the source audits of the 1946-1982 successions and write one
verdict per (succession, name): MAIN (on the main slate), MARGINAL (robustness only) or
EXCLUDE. 05_match_corcholatas.py reads the verdicts to set `in_main_slate`.

The rule (research/main/MAIN_SPEC.md): a hopeful of succession e is on the main slate if
  1. at least two INDEPENDENT qualifying sources name them as a contender for the PRI/PRM
     nomination for the term starting in e;
  2. qualifying = contemporaneous pre-destape press / US government reporting / surveys,
     scholarly work, or participants' memoirs (blogs, Wikipedia, retrospective opinion
     columns and AI summaries are leads only and are not in the audit files);
  3. in the party at the end of e-2;
  4. constitutionally eligible (Art. 82: Mexican by birth, parents Mexican by birth, 35+;
     Art. 83: never president, even as substitute);
  5. alive at the destape (withdrawal does not remove a hopeful).
Sitting cabinet members are presumed party members unless a source shows otherwise.

Independence is counted by source FAMILY, the same way in every succession:
  all US government reporting (State Dept, embassy, consulates, FRUS) -> one family
  Mexican government intelligence (DFS)                               -> one family
  a survey -> its pollster; press -> its outlet; scholarly / memoir -> its author
  a source that relies on another -> the family of what it relies on

Input:  candidates/slate_audit/audit_*_sources.csv (one row per name x qualifying source)
Output: candidates/slate_verdicts.csv  (election_year, name, person_id, n_families,
        families, verdict, reason)
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd

CODE_DIR = Path(__file__).resolve().parents[2]
if str(CODE_DIR) not in sys.path:
    sys.path.append(str(CODE_DIR))

from config import PARSED_POSITIONS_CSV, SLATE_AUDIT_DIR, SLATE_VERDICTS_CSV
from network_utils import StrictNameMatcher

AUTHORS = ["camp", "smith", "castaneda", "medina", "serrano", "servin", "medin", "turrent", "loaeza",
           "langston", "espinoza", "mejia flores", "grijalva", "pellicer", "taylor", "perlo", "gonzalez franco",
           "gil; samuel schmidt", "perez castro", "gonzalez compean", "hernandez rodriguez", "pozas",
           "gutierrez marquez", "cosio villegas", "santos", "ortega", "hernandez campos", "scherer",
           "marte r. gomez", "moncada", "banco de mexico"]
OUTLETS = ["time", "politica", "revista de revistas", "siempre", "evening star", "por que", "united press"]

# Rules 3-5, or the counted rows do not name the person as a PRI contender for e (audit_*.md).
EXCLUDE = {
    (1946, "Maximino Ávila Camacho"): "rule 5: died 17 Feb 1945, before the destape",
    (1946, "Enrique Calderón Rodríguez"): "ran through an opposition party; party membership at e-2 unclear",
    (1946, "Jesús Agustín Castro"): "ran through an opposition party; party membership at e-2 unclear",
    (1952, "Abelardo L. Rodríguez"): "rule 4: Art. 83, substitute president 1932-34",
    (1952, "Cándido Aguilar Vargas"): "not named as a contender for the PRI nomination (own party)",
    (1958, "Ignacio García Téllez"): "not named as a contender in the counted rows",
    (1958, "Javier Rojo Gómez"): "not named as a contender in the counted rows",
    (1964, "Benito Coquet"): "rule 4: father a French national (Camp 2011, p. 217)",
    (1976, "Carlos Hank González"): "rule 4: German-born father (Smith 1979, p. 310)",
    (1982, "Carlos Hank González"): "rule 4: German-born father (Smith 1979, p. 310)",
    (1982, "Rosa Luz Alegría Escamilla"): "rule 4 pending: under 35 if born 1949 (Camp)",
    (1982, 'Mario Moreno "Cantinflas"'): "not a party politician",
}
# Kept on the slate, with the weakness recorded.
FLAGS = {
    (1946, "Francisco Castillo Nájera"): "publicly disavowed his candidacy, May 1945 (withdrawal does not remove)",
    (1958, "Antonio Ortiz Mena"): "provisional: both sources only partly seen",
    (1976, "Luis Enrique Bracamontes"): "all sources trace to Rovirosa Wade's April 1975 statement (seven-name version)",
    (1982, "Jorge Díaz Serrano"): "party membership presumed (sitting cabinet-level official)",
    (1982, "David Ibarra Muñoz"): "party membership presumed (sitting cabinet member)",
    (1982, "Porfirio Muñoz Ledo"): "weak: out of the cabinet in 1981",
}


def _norm(x) -> str:
    return unicodedata.normalize("NFKD", str(x)).encode("ascii", "ignore").decode().lower()


def _base_family(r) -> str:
    t, a, o = r.source_type, _norm(r.author), _norm(r.outlet_or_publisher)
    if t == "us_government":
        return "USGOV"
    if t == "mx_government":
        return "MXGOV"
    if t == "survey":
        return "IMOP" if "imop" in a else a[:20]
    if t == "press":
        return "press:" + next((k for k in OUTLETS if k in o), o[:20])
    return next((k for k in AUTHORS if k in a), a[:25])


def main():
    src = pd.concat([pd.read_csv(f) for f in sorted(SLATE_AUDIT_DIR.glob("audit_*_sources.csv"))],
                    ignore_index=True)
    fam = {r.source_id: _base_family(r) for _, r in src.iterrows()}
    for _ in range(3):                                    # follow chains of relies_on
        for _, r in src.iterrows():
            if isinstance(r.relies_on, str):
                n, ids = _norm(r.relies_on), re.findall(r"S\d{4}_\d{2}", r.relies_on)
                fam[r.source_id] = ("medina" if "medina" in n else "castaneda" if "castaneda" in n
                                    else "moncada" if "moncada" in n else fam.get(ids[0]) if ids
                                    else fam[r.source_id])
    src["family"] = src.source_id.map(fam)

    v = (src.groupby(["election_year", "name"])
            .agg(n_families=("family", "nunique"), families=("family", lambda s: "; ".join(sorted(set(s)))))
            .reset_index())
    v["verdict"] = v.n_families.map(lambda n: "MAIN" if n >= 2 else "MARGINAL")
    v["reason"] = ""
    for table, set_verdict in [(EXCLUDE, True), (FLAGS, False)]:
        for (e, n), why in table.items():
            m = (v.election_year == e) & (v.name == n)
            assert m.sum() == 1, f"{e} {n} not in the audit"
            v.loc[m, "reason"] = why
            if set_verdict:
                v.loc[m, "verdict"] = "EXCLUDE"

    pp = pd.read_csv(PARSED_POSITIONS_CSV, usecols=["person_id", "person_name", "birth_date_clean"])
    pp = pp.dropna(subset=["person_id", "person_name"]).drop_duplicates("person_id")
    byear = {p: int(str(b)[:4]) for p, b in zip(pp.person_id, pp.birth_date_clean) if str(b)[:4].isdigit()}
    matcher = StrictNameMatcher(dict(zip(pp.person_id, pp.person_name)), byear)
    v["person_id"] = [matcher.match(n, int(e), 30, 80)[0] for e, n in zip(v.election_year, v.name)]
    v["person_id"] = v.person_id.astype("Int64")
    miss = v[(v.verdict == "MAIN") & v.person_id.isna()]
    assert miss.empty, f"MAIN names without a person_id: {miss.name.tolist()}"

    v = v[["election_year", "name", "person_id", "n_families", "families", "verdict", "reason"]]
    v.to_csv(SLATE_VERDICTS_CSV, index=False)
    for e, g in v[v.verdict == "MAIN"].groupby("election_year"):
        print(f"{e} (k={len(g)}): " + ", ".join(g.name))
    print(v.verdict.value_counts().to_string())
    print(f"\n→ {SLATE_VERDICTS_CSV}")


if __name__ == "__main__":
    main()
