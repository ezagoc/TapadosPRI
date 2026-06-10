"""
06_build_networks.py

Build an ego-network for every "tapado" (PRI/PRM presidential pre-candidate) listed
in candidates/corcholatas_historicas.xlsx, using the cleaned position datasets.

An edge links a tapado T to another person P when there is a high-precision signal that
the two plausibly knew each other:

  1. explicit  — a family / mentorship / personal tie stated in the biography
                 (parsed from `personal_info`); no year requirement.
  2. co_education — same educational focus with overlapping years. The focus is the
                 institution, refined to faculty level for large institutions: an
                 institution with more than TAU_INST distinct people (e.g. UNAM, 1280)
                 only links people who also share the same `degree_field` (faculty
                 grain: law, economics, engineering, ...). Small/specific schools
                 (primary, secondary, preparatory, regional or military colleges) link
                 on the institution alone. Both studying and teaching roles count, so
                 professor–student ties are captured.
  3. co_work   — same organization with overlapping years. Large ministries are allowed
                 because the mandatory year overlap is the control (they only link people
                 who served there in the same years).

Birthplace ties are intentionally excluded from this first network. A separate, lower
-precision "family by surname" stage (GPT-confirmed) is added afterwards.

Every edge records where the two coincided (`focus`), how big that focus is
(`focus_size`), and what each person was doing there (`ego_role`, `alter_role`).

Inputs : corcholatas_historicas.xlsx, parsed_positions.csv, biographies_corrected.csv,
         clean_positions/{education,govt,party,labor,public,other}_positions.csv
Outputs: data/networks/tapado_edges.csv, data/networks/tapado_nodes.csv
"""

from __future__ import annotations

import re
import sys
import unicodedata
from collections import defaultdict
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
    clean_text,
    clean_person_name,
)

CLEAN_DIR    = DATA_DIR / "clean_positions"
NETWORK_DIR  = DATA_DIR / "networks"
EDGES_CSV    = NETWORK_DIR / "tapado_edges.csv"
NODES_CSV    = NETWORK_DIR / "tapado_nodes.csv"

WORK_DATASETS = ["govt_positions", "party_positions", "labor_positions",
                 "public_positions", "other_positions"]

# ── tunable parameters ───────────────────────────────────────────────────────
TAU_INST = 60   # an institution with more distinct people than this is "large"
                # and is refined to (institution, faculty) before linking.
TAU_WORK = 60   # a work focus (after sub-unit refinement) with more distinct people
                # than this is too diffuse to imply a tie and is dropped.
WIN      = 1    # year-overlap tolerance: intervals within this many years overlap.

# ── name normalisation / matching ────────────────────────────────────────────
_STOPWORDS = {"de", "la", "del", "los", "las", "y", "e", "van", "von", "jr", "sr"}


def _norm(s: str) -> str:
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.category(c).startswith("M"))
    return re.sub(r"[^a-z ]+", " ", s.lower()).strip()


def _tokens(s: str) -> set:
    return {t for t in _norm(s).split() if len(t) >= 3 and t not in _STOPWORDS}


def _role_of(row) -> str:
    """Readable role for a position record (what the person did at the focus)."""
    rt = row.get("role_text")
    if isinstance(rt, str) and rt.strip():
        return rt.strip()
    raw = row.get("role_text_raw")
    return raw.strip() if isinstance(raw, str) else ""


def _overlaps(a0: int, a1: int, b0: int, b1: int, w: int = WIN) -> bool:
    return a0 <= b1 + w and b0 <= a1 + w


class PersonMatcher:
    """Fuzzy-match a free-text name to a person_id via normalised token overlap."""

    def __init__(self, people: pd.DataFrame):
        self.pid_name = dict(zip(people["person_id"], people["person_name"]))
        self.pid_tokens = {pid: _tokens(name) for pid, name in self.pid_name.items()}
        self.token_to_pids: dict[str, set] = defaultdict(set)
        for pid, toks in self.pid_tokens.items():
            for t in toks:
                self.token_to_pids[t].add(pid)

    def match(self, query: str, *, require_cover: bool = True) -> int | None:
        q = _tokens(query)
        if not q:
            return None
        score: dict[int, int] = defaultdict(int)
        for t in q:
            for pid in self.token_to_pids.get(t, ()):
                score[pid] += 1
        if not score:
            return None
        pid, ov = max(score.items(), key=lambda kv: (kv[1], -len(self.pid_tokens[kv[0]])))
        if ov < 2:
            return None
        if require_cover and ov < len(q) - 1:  # most query tokens must be present
            return None
        return pid


# ── explicit relationship patterns (from biographies personal_info) ───────────
FAMILY_PATTERNS = [
    r"(?:son|daughter)\s+of\s+([^,;]+)",
    r"(?:brother|sister)\s+(?:of\s+)?([^,;]+)",
    r"married\s+([^,;]+)",
    r"(?:nephew|niece)\s+of\s+([^,;]+)",
    r"(?:uncle|aunt)\s+(?:of\s+)?([^,;]+)",
    r"(?:cousin)\s+(?:of\s+)?([^,;]+)",
    r"(?:father|mother)-in-law\s+(?:of\s+)?([^,;]+)",
    r"(?:son-in-law|daughter-in-law)\s+(?:of\s+)?([^,;]+)",
    r"(?:grandson|granddaughter)\s+(?:of\s+)?([^,;]+)",
]
MENTORSHIP_PATTERNS = [
    r"student\s+of\s+([^,;]+)",
    r"studied\s+(?:under|with)\s+([^,;]+)",
    r"(?:prot[eé]g[eé])\s+of\s+([^,;]+)",
    r"(?:political\s+)?(?:patron|mentor)\s+(?:was\s+)?([^,;]+)",
    r"disciple\s+of\s+([^,;]+)",
]
PERSONAL_PATTERNS = [
    r"(?:close\s+)?friends?\s+(?:of|with|included)\s+([^,;]+)",
    r"came\s+in\s+contact\s+with\s+([^,;]+)",
]
EXPLICIT_PATTERNS = (
    [(p, "family") for p in FAMILY_PATTERNS]
    + [(p, "mentorship") for p in MENTORSHIP_PATTERNS]
    + [(p, "personal") for p in PERSONAL_PATTERNS]
)
# trailing role words that should be trimmed from a mentioned name
_MENTION_TAIL = re.compile(
    r"\s+(?:who|whose|was|is|a|an|the|secretary|director|governor|president|senator|"
    r"federal|head|mayor|former|general|leader|chief|deputy|ambassador)\b.*$",
    re.IGNORECASE,
)


# ── focus-key derivation ──────────────────────────────────────────────────────
_TRUNCATED_SCHOOL = re.compile(r"\bNo\.?\s*$", re.I)  # "Secondary School No" (number lost)


def edu_focus_key(org, field, level, record_type, inst_size: dict):
    """Education focus: (institution, faculty, degree_level, role).

    - degree_level: an undergraduate and a master's/PhD student in the same faculty
      are NOT linked — they did not share classes.
    - role: students link to students (classmates) and staff link to staff
      (colleagues), but a student is NOT linked to a teacher/professor (co-presence
      at a school as student vs teacher does not imply they knew each other).
    Records with no degree level (prep, teaching roles) share a 'pre/other' level
    bucket so prep classmates still link.
    """
    if not isinstance(org, str) or len(org) < 3:
        return None
    if _TRUNCATED_SCHOOL.search(org):
        return None  # generic "... School No" (number dropped) links different schools
    lvl = level if isinstance(level, str) and level.strip() and level != "nan" else "pre/other"
    role = "staff" if record_type == "academic_role" else "student"
    if inst_size.get(org, 0) > TAU_INST:
        if not isinstance(field, str) or not field.strip() or field == "nan":
            return None  # large institution with no faculty info → too coarse to link
        return ("edu", org, field, lvl, role)
    return ("edu", org, None, lvl, role)


def _s(v):
    """Return a clean non-empty string or None."""
    return v.strip() if isinstance(v, str) and v.strip() and v != "nan" else None


def work_focus_key(d: dict):
    """
    Work focus, refined to a sub-unit small enough to imply acquaintance.

    - party: a specific party body (CEN, IEPES, a regional committee) and/or a
      geographic unit (party of a given state). Generic national membership
      ("PRI" with no body and no state) is dropped — being co-members is not co-work.
    - govt: refined by sub_department or a secretariat finer than the organization,
      else the organization itself (large ones are then dropped by the size cap).
    - labor / public / other: the organization.
    """
    src = d.get("source")
    org = _s(d.get("organization"))
    if src == "party_positions":
        party = _s(d.get("party")) or org or "party"
        body, st = _s(d.get("party_body")), _s(d.get("state"))
        if body and st:
            return ("work", f"{party} – {body} ({st})")
        if body:
            return ("work", f"{party} – {body}")
        if st:
            return ("work", f"{party} – {st}")
        return None  # generic national membership → drop
    if src == "govt_positions":
        if not org:
            return None
        sub, sec = _s(d.get("sub_department")), _s(d.get("secretariat_norm"))
        if sub:
            return ("work", f"{org} – {sub}")
        if sec and sec != org:
            return ("work", sec)
        return ("work", org)
    if org:
        return ("work", org)
    return None


def focus_label(key) -> str:
    if key[0] == "edu":
        _, org, field, lvl, role = key
        base = f"{org} | {field}" if field else org
        return f"{base} [{lvl}/{role}]"
    return key[1]  # work / military focus is already a readable label


# Military co-service focus: a specific unit or the commander served under.
# Factions ("Zapatistas") and bare "Division" (the rank) are intentionally ignored.
_MIL_UNIT = re.compile(
    r"\b(\d{1,3})(?:st|nd|rd|th)?\s+"
    r"(Battalion|Regiment|Division|Brigade|Cavalry|Infantry|Corps|Military Zone)\b", re.I)
_MIL_GEN = re.compile(
    r"under (?:General|Gen\.?|Col\.?|Colonel|Brigadier(?: General)?|Brig\.?) "
    r"([A-ZÁÉÍÓÚ][\wÁÉÍÓÚáéíóúñ.]+(?:\s+[A-ZÁÉÍÓÚ][\wÁÉÍÓÚáéíóúñ.]+){1,3})")


def military_foci(text) -> set:
    """Specific units / shared commander extracted from a military role text."""
    if not isinstance(text, str):
        return set()
    foci = set()
    for m in _MIL_UNIT.finditer(text):
        foci.add(f"{int(m.group(1))} {m.group(2).title()}")
    for m in _MIL_GEN.finditer(text):
        foci.add("under Gen. " + m.group(1).strip())
    return foci


def _build_focus_index(df: pd.DataFrame, key_fn) -> tuple[dict, dict]:
    """focus_key -> [(person_id, year_start, year_end, role)]; and focus_size."""
    index: dict = defaultdict(list)
    for row in df.itertuples(index=False):
        d = row._asdict()
        key = key_fn(d)
        if key is None:
            continue
        ys, ye = d.get("year_start"), d.get("year_end")
        if pd.isna(ys):
            continue  # co-location requires a year
        ys = int(ys)
        ye = int(ye) if pd.notna(ye) else ys
        index[key].append((d["person_id"], ys, ye, _role_of(d)))
    size = {k: len({r[0] for r in recs}) for k, recs in index.items()}
    return index, size


# ── main ─────────────────────────────────────────────────────────────────────
def load_tapados(matcher: PersonMatcher) -> pd.DataFrame:
    """Return DataFrame: person_id, name, election_year, is_winner (one row per election)."""
    corch = pd.read_excel(CORCHOLATAS_XLSX, header=1).dropna(subset=["Nombre"])
    rows, unmatched = [], []
    for _, r in corch.iterrows():
        raw = str(r["Nombre"])
        is_winner = "✓" in raw
        name = raw.replace("✓", "").strip()
        pid = matcher.match(name, require_cover=True)
        if pid is None:
            unmatched.append(name)
            continue
        rows.append({
            "person_id": pid,
            "corcholata_name": name,
            "election_year": int(r["Elección"]),
            "is_winner": int(is_winner),
        })
    if unmatched:
        print(f"  ⚠ {len(unmatched)} corcholatas without a clear match:")
        for n in unmatched:
            print(f"      {n}")
    return pd.DataFrame(rows)


def main():
    print("Loading people and corcholatas …")
    pp = pd.read_csv(PARSED_POSITIONS_CSV)
    people = pp[["person_id", "person_name"]].drop_duplicates()
    pid_name = dict(zip(people["person_id"], people["person_name"]))
    matcher = PersonMatcher(people)

    tap = load_tapados(matcher)
    tapado_ids = set(tap["person_id"])
    print(f"  {len(tapado_ids)} unique tapados matched ({len(tap)} tapado-elections)")

    # ── education focus index ────────────────────────────────────────────────
    edu = pd.read_csv(CLEAN_DIR / "education.csv")
    inst_size = (edu.dropna(subset=["organization"])
                    .groupby("organization")["person_id"].nunique().to_dict())
    edu_key_fn = lambda d: edu_focus_key(d.get("organization"), d.get("degree_field"),
                                         d.get("degree_level"), d.get("record_type"), inst_size)
    edu_index, edu_size = _build_focus_index(edu, edu_key_fn)
    print(f"  education foci (with years): {len(edu_index)}")

    # ── work focus index (all work datasets combined), refined + size-capped ──
    work = pd.concat([pd.read_csv(CLEAN_DIR / f"{name}.csv").assign(source=name)
                      for name in WORK_DATASETS], ignore_index=True)
    work_index, work_size = _build_focus_index(work, work_focus_key)
    dropped_big = {k for k, n in work_size.items() if n > TAU_WORK}
    for k in dropped_big:
        del work_index[k]
    print(f"  work foci (with years): {len(work_index)} kept "
          f"(dropped {len(dropped_big)} foci larger than {TAU_WORK} people)")

    # ── military co-service index (unit / commander extracted from role text) ─
    mil = pd.read_csv(CLEAN_DIR / "military_positions.csv")
    mil_rows = []
    for row in mil.itertuples(index=False):
        d = row._asdict()
        text = d.get("role_text") if isinstance(d.get("role_text"), str) else d.get("role_text_raw")
        for fk in military_foci(text):
            d2 = dict(d); d2["mil_focus"] = fk; mil_rows.append(d2)
    mil_exp = pd.DataFrame(mil_rows)
    mil_key_fn = lambda d: ("mil", d["mil_focus"]) if d.get("mil_focus") else None
    mil_index, mil_size = _build_focus_index(mil_exp, mil_key_fn)
    for k in [k for k, n in mil_size.items() if n > TAU_WORK]:
        del mil_index[k]
    print(f"  military foci (with years): {len(mil_index)}")

    # ── biographies personal_info, mapped to person_id ───────────────────────
    bio = pd.read_csv(BIOGRAPHIES_CSV)
    name_to_pid = {v: k for k, v in pid_name.items()}
    bio["person_id"] = bio["name"].map(lambda n: name_to_pid.get(clean_person_name(n)))

    edges = []

    def add_edge(ego, alter, etype, key, size, ego_role, alter_role, ys, ye, conf="rule"):
        if alter == ego:
            return
        edges.append({
            "ego_id": ego, "alter_id": alter,
            "edge_type": etype,
            "focus": focus_label(key) if isinstance(key, tuple) else key,
            "focus_size": size,
            "ego_role": ego_role, "alter_role": alter_role,
            "year_start": ys, "year_end": ye,
            "confirmed_by": conf,
        })

    # ── co-location edges (education + work) ─────────────────────────────────
    def colocation(df, index, size_map, key_fn, etype):
        tdf = df[df["person_id"].isin(tapado_ids)]
        for row in tdf.itertuples(index=False):
            d = row._asdict()
            key = key_fn(d)
            if key is None or key not in index or pd.isna(d.get("year_start")):
                continue
            tys = int(d["year_start"])
            tye = int(d["year_end"]) if pd.notna(d.get("year_end")) else tys
            ego_role = _role_of(d)
            for (pid, oys, oye, orole) in index.get(key, ()):
                if pid == d["person_id"]:
                    continue
                if _overlaps(tys, tye, oys, oye):
                    add_edge(d["person_id"], pid, etype, key, size_map.get(key),
                             ego_role, orole,
                             max(tys, oys), min(tye, oye))

    print("Building co-education edges …")
    colocation(edu, edu_index, edu_size, edu_key_fn, "co_education")
    print("Building co-work edges …")
    colocation(work, work_index, work_size, work_focus_key, "co_work")
    print("Building co-military edges …")
    colocation(mil_exp, mil_index, mil_size, mil_key_fn, "co_military")

    # ── explicit edges (family / mentorship / personal) ──────────────────────
    print("Building explicit edges …")
    for row in bio[bio["person_id"].isin(tapado_ids)].itertuples(index=False):
        d = row._asdict()
        ego = d["person_id"]
        info = d.get("personal_info")
        if not isinstance(info, str) or not info.strip():
            continue
        info = clean_text(info)
        for pat, etype in EXPLICIT_PATTERNS:
            for m in re.finditer(pat, info, re.IGNORECASE):
                mention = _MENTION_TAIL.sub("", m.group(1).strip()).strip()
                if len(mention) < 4:
                    continue
                alter = matcher.match(mention, require_cover=False)
                if alter is not None and alter != ego:
                    add_edge(ego, alter, etype, etype, None,
                             etype, mention[:80], None, None)

    # ── assemble, dedupe, attach metadata ────────────────────────────────────
    edf = pd.DataFrame(edges).drop_duplicates(
        subset=["ego_id", "alter_id", "edge_type", "focus"])
    # winner / election info per ego (joined across elections)
    ego_elec = (tap.groupby("person_id")
                   .agg(election_year=("election_year",
                                       lambda s: ";".join(map(str, sorted(set(s))))),
                        is_winner=("is_winner", "max")).to_dict("index"))
    edf["ego_name"]      = edf["ego_id"].map(pid_name)
    edf["alter_name"]    = edf["alter_id"].map(pid_name)
    edf["election_year"] = edf["ego_id"].map(lambda p: ego_elec[p]["election_year"])
    edf["is_winner"]     = edf["ego_id"].map(lambda p: ego_elec[p]["is_winner"])
    edf = edf[["ego_id", "ego_name", "election_year", "is_winner",
               "alter_id", "alter_name", "edge_type", "focus", "focus_size",
               "ego_role", "alter_role", "year_start", "year_end", "confirmed_by"]]

    NETWORK_DIR.mkdir(parents=True, exist_ok=True)
    edf.to_csv(EDGES_CSV, index=False)

    # ── nodes file ───────────────────────────────────────────────────────────
    node_ids = set(edf["ego_id"]) | set(edf["alter_id"])
    nodes = []
    for pid in sorted(node_ids):
        meta = ego_elec.get(pid)
        nodes.append({
            "person_id": pid, "name": pid_name.get(pid),
            "is_tapado": int(pid in tapado_ids),
            "election_year": meta["election_year"] if meta else "",
            "is_winner": meta["is_winner"] if meta else "",
        })
    pd.DataFrame(nodes).to_csv(NODES_CSV, index=False)

    # ── report ───────────────────────────────────────────────────────────────
    print(f"\nSaved {len(edf):,} edges → {EDGES_CSV}")
    print(f"Saved {len(nodes):,} nodes → {NODES_CSV}")
    print("\nEdge types:")
    print(edf["edge_type"].value_counts().to_string())
    deg = edf.groupby("ego_id").size()
    no_edges = tapado_ids - set(edf["ego_id"])
    print(f"\nTapados with 0 edges: {len(no_edges)}")
    for pid in no_edges:
        print(f"   {pid_name.get(pid)}")
    print("\nEdges per tapado (top / bottom):")
    deg_named = deg.rename(index=pid_name).sort_values(ascending=False)
    print(deg_named.head(8).to_string())
    print("   …")
    print(deg_named.tail(5).to_string())


if __name__ == "__main__":
    main()
