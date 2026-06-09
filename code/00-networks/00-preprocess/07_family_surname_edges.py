"""
07_family_surname_edges.py  —  network stage 2: kinship by shared surname (GPT-confirmed)

For every tapado, find other people in the dataset who share a paternal or maternal
surname, then ask GPT (gpt-4o-mini) to confirm whether the pair are actual relatives
up to second cousins / great-uncles (closer kinship only — not third cousins, not a
mere shared surname). Only GPT-confirmed pairs become `family_surname` edges.

No common-surname pre-filter is applied on purpose: excluding common surnames (García,
López, …) would systematically shrink the family dimension of common-surnamed people's
networks (a bias correlated with surname rarity, not real kinship). GPT does the
filtering instead — two unrelated "García" simply get a "no".

These edges are heuristic: GPT can be wrong on obscure figures, so every confirmed edge
is tagged `confirmed_by=gpt` and the full candidate list (with verdicts) is written for
human review.

Inputs : networks/tapado_edges.csv (core v1 edges), parsed_positions.csv,
         biographies_corrected.csv, corcholatas_historicas.xlsx
Outputs: networks/family_surname_candidates.csv  (all candidates + GPT verdict)
         networks/tapado_edges.csv                (core v1 + confirmed family_surname)
"""

from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

CODE_DIR = Path(__file__).resolve().parents[2]
if str(CODE_DIR) not in sys.path:
    sys.path.append(str(CODE_DIR))

from config import (
    BIOGRAPHIES_CSV,
    PARSED_POSITIONS_CSV,
    CORCHOLATAS_XLSX,
    DATA_DIR,
    clean_person_name,
)

NETWORK_DIR    = DATA_DIR / "networks"
EDGES_CSV      = NETWORK_DIR / "tapado_edges.csv"
CANDIDATES_CSV = NETWORK_DIR / "family_surname_candidates.csv"
# Optional human review: if present, its `keep` (1/0) and `corrected_relationship`
# columns OVERRIDE the automatic scope filter (manual one-by-one curation).
REVIEW_CSV     = NETWORK_DIR / "family_surname_review.csv"

BATCH_SIZE = 15
MODEL      = "gpt-4o-mini"

_CONN = {"de", "la", "del", "los", "las", "y", "e", "van", "von"}


def _norm(s: str) -> str:
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.category(c).startswith("M"))
    return re.sub(r"[^a-z ]+", " ", s.lower()).strip()


def _surname_tokens(person_name: str) -> set:
    """Significant surname tokens (the part before the comma)."""
    sur = person_name.split(",")[0] if "," in person_name else person_name
    return {t.lower() for t in sur.split() if len(t) >= 3 and t.lower() not in _CONN}


def _display(person_name: str) -> str:
    """'Lopez Mateos, Adolfo' -> 'Adolfo Lopez Mateos' for the prompt."""
    if "," in person_name:
        sur, giv = person_name.split(",", 1)
        return f"{giv.strip()} {sur.strip()}".strip()
    return person_name


def _tokens(s: str) -> set:
    return {w for w in _norm(s).split() if len(w) > 2}


# Keep only concrete kinship within the requested scope (up to second cousins /
# great-uncles). Drop vague or out-of-scope verdicts: "distant relatives/cousins",
# "third cousins", "... once/twice removed", or empty — these are where GPT tends to
# over-claim on a shared common surname.
_OUT_OF_SCOPE = re.compile(r"distant|third|fourth|removed", re.I)


def in_scope(relationship) -> bool:
    rel = str(relationship).strip().lower()
    if rel in ("", "nan", "none", "unknown"):
        return False
    return _OUT_OF_SCOPE.search(rel) is None


def match_tapados(corch: pd.DataFrame, people: pd.DataFrame) -> pd.DataFrame:
    tok2pid = defaultdict(set)
    pid_tok = {}
    for pid, name in zip(people["person_id"], people["person_name"]):
        t = _tokens(name)
        pid_tok[pid] = t
        for w in t:
            tok2pid[w].add(pid)
    rows = []
    for _, r in corch.dropna(subset=["Nombre"]).iterrows():
        name = str(r["Nombre"]).replace("✓", "").strip()
        q = _tokens(name)
        score = Counter()
        for w in q:
            for pid in tok2pid.get(w, ()):
                score[pid] += 1
        if not score:
            continue
        pid, ov = max(score.items(), key=lambda kv: (kv[1], -len(pid_tok[kv[0]])))
        if ov >= 2 and ov >= len(q) - 1:
            rows.append({"person_id": pid, "election_year": int(r["Elección"]),
                         "is_winner": int("✓" in str(r["Nombre"]))})
    return pd.DataFrame(rows)


def gpt_confirm(client, batch: list[dict]) -> dict:
    """Ask GPT to confirm kinship for a batch of pairs. Returns {id: (related, relationship)}."""
    lines = []
    for it in batch:
        lines.append(
            f"id={it['id']}: A) {it['a']} — B) {it['b']}"
        )
    prompt = (
        "You are an expert on 20th-century Mexican political families. For each numbered "
        "pair of people (A and B), decide whether they are actual relatives — by blood or "
        "marriage — within second cousins / great-uncles-or-aunts (do NOT count third "
        "cousins or more distant; a shared surname alone is NOT kinship). Birth years and "
        "birthplaces are given to disambiguate. If you are not reasonably confident they "
        "are related, answer \"no\".\n"
        "Respond ONLY with a JSON array, one object per pair: "
        '{"id": <int>, "related": "yes"|"no", "relationship": "<short, e.g. brothers / '
        'uncle-nephew / first cousins / father-in-law; empty if no>"}.\n\n'
        + "\n".join(lines)
    )
    resp = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    txt = resp.choices[0].message.content.strip()
    txt = re.sub(r"^```(?:json)?|```$", "", txt, flags=re.MULTILINE).strip()
    out = {}
    try:
        for obj in json.loads(txt):
            out[int(obj["id"])] = (str(obj.get("related", "no")).lower().startswith("y"),
                                   str(obj.get("relationship", "")).strip())
    except Exception as e:
        print(f"    ! parse error on a batch ({e}); treating as 'no'")
    return out


def main():
    print("Loading people, tapados and context …")
    pp = pd.read_csv(PARSED_POSITIONS_CSV)
    people = pp[["person_id", "person_name"]].drop_duplicates()
    pid_name = dict(zip(people["person_id"], people["person_name"]))

    corch = pd.read_excel(CORCHOLATAS_XLSX, header=1)
    tap = match_tapados(corch, people)
    tapado_ids = set(tap["person_id"])
    print(f"  {len(tapado_ids)} tapados")

    # birth year + birthplace context (helps GPT disambiguate)
    bio = pd.read_csv(BIOGRAPHIES_CSV)
    name_to_pid = {v: k for k, v in pid_name.items()}
    ctx = {}
    for _, r in bio.iterrows():
        pid = name_to_pid.get(clean_person_name(r["name"]))
        if pid is None:
            continue
        yr = ""
        m = re.search(r"\b(1[89]\d{2}|20\d{2})\b", str(r.get("birth_date", "")))
        if m:
            yr = m.group(1)
        bp = str(r.get("birthplace", "")).strip() if pd.notna(r.get("birthplace")) else ""
        ctx[pid] = (yr, bp)

    def describe(pid):
        nm = _display(pid_name.get(pid, str(pid)))
        yr, bp = ctx.get(pid, ("", ""))
        extra = ", ".join(x for x in [f"born {yr}" if yr else "", bp] if x)
        return f"{nm} ({extra})" if extra else nm

    # ── candidate generation: tapado shares a surname with another person ────
    sur2pid = defaultdict(set)
    sur_by_pid = {}
    for pid, name in zip(people["person_id"], people["person_name"]):
        toks = _surname_tokens(name)
        sur_by_pid[pid] = toks
        for t in toks:
            sur2pid[t].add(pid)

    pairs = {}  # frozenset({a,b}) -> shared surname token
    for pid in tapado_ids:
        for t in sur_by_pid[pid]:
            for other in sur2pid.get(t, ()):
                if other == pid:
                    continue
                pairs.setdefault(frozenset((pid, other)), t)
    pair_list = []
    for k, t in pairs.items():
        a, b = tuple(k)
        ego, alter = (a, b) if a in tapado_ids else (b, a)
        pair_list.append({"ego": ego, "alter": alter, "surname": t})
    print(f"  candidate kin-pairs (no common-surname filter): {len(pair_list)}")

    # ── GPT confirmation (cached: reuse verdicts if the audit file exists) ───
    if CANDIDATES_CSV.exists():
        cand_df = pd.read_csv(CANDIDATES_CSV)
        print(f"  reusing cached GPT verdicts ({len(cand_df)} pairs) from "
              f"{CANDIDATES_CSV.name} — delete it to re-query GPT")
    else:
        try:
            import openai
        except ImportError:
            sys.exit("openai package not installed")
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            sys.exit("OPENAI_API_KEY not found in environment/.env")
        client = openai.OpenAI(api_key=api_key)

        results = {}
        total = len(pair_list)
        for start in range(0, total, BATCH_SIZE):
            chunk = pair_list[start:start + BATCH_SIZE]
            batch = [{"id": start + i, "a": describe(p["ego"]), "b": describe(p["alter"])}
                     for i, p in enumerate(chunk)]
            verdict = gpt_confirm(client, batch)
            for i in range(len(chunk)):
                results[start + i] = verdict.get(start + i, (False, ""))
            print(f"    {min(start + BATCH_SIZE, total)}/{total} pairs confirmed", end="\r")
        print()
        cand_df = pd.DataFrame([{
            "ego_id": p["ego"], "ego_name": pid_name.get(p["ego"]),
            "alter_id": p["alter"], "alter_name": pid_name.get(p["alter"]),
            "shared_surname": p["surname"],
            "related": "yes" if results.get(i, (False, ""))[0] else "no",
            "relationship": results.get(i, (False, ""))[1],
        } for i, p in enumerate(pair_list)])

    # scope filter + audit trail
    cand_df["in_scope"] = cand_df["relationship"].apply(in_scope)
    NETWORK_DIR.mkdir(parents=True, exist_ok=True)
    cand_df.to_csv(CANDIDATES_CSV, index=False)
    n_yes = int((cand_df["related"] == "yes").sum())
    n_kept = int(((cand_df["related"] == "yes") & cand_df["in_scope"]).sum())
    print(f"\nGPT confirmed {n_yes} pairs; {n_kept} kept within scope "
          f"(dropped {n_yes - n_kept} distant/vague — enforces 'no third cousins')")
    print(f"Audit (all candidates + verdict + in_scope) → {CANDIDATES_CSV}")

    # ── append confirmed family_surname edges to the core edge list ──────────
    ego_elec = (tap.groupby("person_id")
                   .agg(election_year=("election_year",
                                       lambda s: ";".join(map(str, sorted(set(s))))),
                        is_winner=("is_winner", "max")).to_dict("index"))
    # If a human review file exists, it is the source of truth (keep==1) and may
    # correct the relationship label; otherwise fall back to the scope heuristic.
    manual = None
    if REVIEW_CSV.exists():
        rev = pd.read_csv(REVIEW_CSV)
        keep = rev[rev["keep"].astype(str).str.strip().isin(["1", "1.0", "yes", "true", "True"])]
        manual = {(int(x.ego_id), int(x.alter_id)):
                  (str(x.corrected_relationship).strip()
                   if isinstance(x.corrected_relationship, str) and str(x.corrected_relationship).strip()
                   else str(x.relationship_gpt))
                  for x in keep.itertuples()}
        print(f"  manual review applied: {len(manual)} family edges kept "
              f"(from {REVIEW_CSV.name})")

    base = cand_df[(cand_df["related"] == "yes") & cand_df["in_scope"]]
    fam_edges = []
    for _, r in base.iterrows():
        pair = (int(r["ego_id"]), int(r["alter_id"]))
        if manual is not None:
            if pair not in manual:
                continue
            relationship = manual[pair]
            confirmed = "gpt+human"
        else:
            relationship = r["relationship"]
            confirmed = "gpt"
        meta = ego_elec.get(r["ego_id"], {"election_year": "", "is_winner": ""})
        fam_edges.append({
            "ego_id": r["ego_id"], "ego_name": r["ego_name"],
            "election_year": meta["election_year"], "is_winner": meta["is_winner"],
            "alter_id": r["alter_id"], "alter_name": r["alter_name"],
            "edge_type": "family_surname",
            "focus": relationship or f"shared surname: {r['shared_surname']}",
            "focus_size": "", "ego_role": relationship,
            "alter_role": f"shared surname: {r['shared_surname']}",
            "year_start": "", "year_end": "", "confirmed_by": confirmed,
        })

    core = pd.read_csv(EDGES_CSV)
    core = core[core["edge_type"] != "family_surname"]  # idempotent re-run
    combined = pd.concat([core, pd.DataFrame(fam_edges)], ignore_index=True)
    combined.to_csv(EDGES_CSV, index=False)
    print(f"Added {len(fam_edges)} family_surname edges → {EDGES_CSV}")
    print("\nEdge types now:")
    print(combined["edge_type"].value_counts().to_string())


if __name__ == "__main__":
    main()
