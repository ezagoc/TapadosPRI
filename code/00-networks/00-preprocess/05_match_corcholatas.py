"""
05_match_corcholatas.py

Link every row of candidates/corcholatas_historicas.xlsx (one row per
pre-candidate × election) to a `person_id` in parsed_positions.csv, and write the
result as an explicit, reviewable crosswalk. Every downstream script (06, 07,
04-analysis) reads this crosswalk instead of re-matching names on its own.

Matching rule (strict, to avoid false positives):
  - the person's PATERNAL surname (first surname token of `person_name`) must
    appear in the corcholata name, AND
  - at least one of the person's given names must appear in it, AND
  - the person must be 30–80 years old in the election year (when birth year known).
  Among the people passing these tests, rank by (most shared tokens, fewest
  person tokens absent from the corcholata name); a remaining tie is flagged
  `ambiguous` and left unmatched.
  The previous token-overlap matcher linked "Manuel Pérez Treviño" to
  "Avila Perez, Manuel" and "Ezequiel Padilla" (b. 1890) to his namesake
  "Padilla Couttolenc, Ezequiel" (b. 1942).

MANUAL_OVERRIDES pins cases the rule cannot resolve; each carries its reason.

Input:  candidates/corcholatas_historicas.xlsx, parsed_positions.csv
Output: candidates/corcholatas_matched.csv
        (election_year, corcholata_name, is_winner (✓ in the xlsx), is_runner_up,
         role, took_office, runner_up_source,
         person_id, person_name, match_status, position_at_time, status_source,
         broke_with_pri_year)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

CODE_DIR = Path(__file__).resolve().parents[2]
if str(CODE_DIR) not in sys.path:
    sys.path.append(str(CODE_DIR))

from config import CORCHOLATAS_XLSX, CORCHOLATAS_MATCHED_CSV, PARSED_POSITIONS_CSV
from network_utils import StrictNameMatcher

MIN_AGE, MAX_AGE = 30, 80   # plausible age of a pre-candidate in the election year

# corcholata name (without ✓ / parenthetical notes) -> (person_name or None, reason)
MANUAL_OVERRIDES = {
    "Manuel Pérez Treviño": (
        None,
        "no own entry in Camp 1935-2009 (biography is in the 1884-1934 volume); "
        "only mentioned in others' bios",
    ),
}


# Single "closest runner-up" per election — used only for ROBUSTNESS (the main
# control group is every documented losing pre-candidate). Sources: CR = "The
# Tapado System … (Claude Research)" in the Dropbox root; XLSX = the `Estatus`
# column of corcholatas_historicas.xlsx. "verify" = to confirm against Castañeda
# (1999) La herencia.
RUNNER_UP = {
    1940: ("Francisco J. Múgica", "CR: Cárdenas passed over Múgica"),
    1946: ("Javier Rojo Gómez", "XLSX: documented pre-candidate — verify"),
    1952: ("Fernando Casas Alemán", "CR: Alemán first favored Casas Alemán"),
    1958: ("Gilberto Flores Muñoz", "XLSX: main pre-candidate"),
    1964: ("Antonio Ortiz Mena", "XLSX: documented pre-candidate — verify"),
    1970: ("Emilio Martínez Manatou", "XLSX: main cabinet pre-candidate"),
    1976: ("Mario Moya Palencia", "CR: front-runner from Gobernación"),
    1982: ("Javier García Paniagua", "CR: final two De la Madrid vs García Paniagua"),
    1988: ("Manuel Bartlett Díaz", "CR: Gobernación front-runner among the six"),
    1994: ("Manuel Camacho Solís", "CR: Colosio picked over Camacho Solís"),
    2000: ("Roberto Madrazo Pintado", "CR: second in the 1999 open primary"),
}


# Special successions. `role` per corcholata-election:
#   winner              designated by the dedazo and took office (treated)
#   designated_removed  designated, then removed before taking office (1994 Colosio,
#                       assassinated 23 Mar 1994) — a control with the same selection
#   nominee_lost        won the PRI nomination but lost the general election (2000
#                       Labastida vs Fox): nomination, not the presidency
#   runner_up / loser   the documented runner-up / every other pre-candidate
# `took_office` = 1 only for the person who became president (1994: Zedillo, the
# substitute candidate; 2000: nobody from the PRI).
DESIGNATED_REMOVED = {1994: "Luis Donaldo Colosio"}
NOMINEE_LOST = {2000: "Francisco Labastida Ochoa"}


def _role(year: int, name: str, is_winner: int, is_runner_up: int) -> str:
    if DESIGNATED_REMOVED.get(year) == name:
        return "designated_removed"
    if NOMINEE_LOST.get(year) == name:
        return "nominee_lost"
    if is_winner:
        return "winner"
    return "runner_up" if is_runner_up else "loser"


def _clean_corcholata(raw: str) -> str:
    name = str(raw).replace("✓", "")
    name = re.sub(r"\([^)]*\)", "", name)          # "(asesinado)", "(sustituto)"
    return re.sub(r"\s+", " ", name).strip()


def main():
    pp = pd.read_csv(PARSED_POSITIONS_CSV,
                     usecols=["person_id", "person_name", "birth_date_clean"])
    pp = pp.dropna(subset=["person_id", "person_name"]).drop_duplicates("person_id")
    byear = {pid: int(str(b)[:4]) for pid, b in zip(pp.person_id, pp.birth_date_clean)
             if str(b)[:4].isdigit()}
    pid_name = dict(zip(pp.person_id, pp.person_name))
    name_pid = {v: k for k, v in pid_name.items()}
    matcher = StrictNameMatcher(pid_name, byear)

    corch = pd.read_excel(CORCHOLATAS_XLSX, header=1).dropna(subset=["Nombre"])
    rows = []
    for _, r in corch.iterrows():
        raw = str(r["Nombre"])
        name = _clean_corcholata(raw)
        if name in MANUAL_OVERRIDES:
            target, reason = MANUAL_OVERRIDES[name]
            pid = name_pid.get(target) if target else None
            status = f"manual: {reason}"
        else:
            pid, status = matcher.match(name, int(r["Elección"]), MIN_AGE, MAX_AGE)
        year = int(r["Elección"])
        ru_name, ru_src = RUNNER_UP.get(year, (None, None))
        role = _role(year, name, int("✓" in raw), int(name == ru_name))
        rows.append({
            "election_year": year,
            "corcholata_name": name,
            "is_winner": int("✓" in raw),
            "is_runner_up": int(name == ru_name),
            "role": role,
            "took_office": int(role == "winner"),
            "runner_up_source": ru_src if name == ru_name else None,
            "person_id": pid,
            "person_name": pid_name.get(pid, ""),
            "match_status": status,
            # source columns (values kept verbatim, in Spanish, as in the xlsx)
            "position_at_time": r.get("Cargo al momento"),
            "status_source": r.get("Estatus"),
            "broke_with_pri_year": r.get("Rompimiento PRI"),
        })
    out = pd.DataFrame(rows)
    out["person_id"] = out["person_id"].astype("Int64")
    CORCHOLATAS_MATCHED_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(CORCHOLATAS_MATCHED_CSV, index=False)

    print(f"{len(out)} corcholata-elections, {out.person_id.nunique()} unique people matched")
    print(out.match_status.str.split(":").str[0].value_counts().to_string())
    missing = set(RUNNER_UP) - set(out.loc[out.is_runner_up == 1, "election_year"])
    assert not missing, f"RUNNER_UP name not found in the xlsx for {sorted(missing)}"
    for special in (DESIGNATED_REMOVED, NOMINEE_LOST):
        for y, nm in special.items():
            assert ((out.election_year == y) & (out.corcholata_name == nm)).any(), nm
    assert (out.groupby("election_year").took_office.sum() <= 1).all()
    print(out.groupby("role").size().to_string())
    bad = out[out.person_id.isna()]
    if len(bad):
        print("\nUnmatched:")
        print(bad[["election_year", "corcholata_name", "match_status"]].to_string(index=False))
    print(f"\n→ {CORCHOLATAS_MATCHED_CSV}")


if __name__ == "__main__":
    main()
