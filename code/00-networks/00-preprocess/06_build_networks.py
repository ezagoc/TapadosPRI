"""
06_build_networks.py

Build the FULL network of Mexican politicians in the dataset: every pair of people
(person_a < person_b) with a high-precision signal that they plausibly knew each
other. Tapado ego-networks are just views of this network (network_utils.ego_view).

Edge types
  co_education  — same school, same level, same role (student–student or
                  staff–staff; never student–teacher). Years are normalised to an
                  ENROLLMENT WINDOW: a record with a single year is the degree year,
                  so the window is [degree_year − program_length + 1, degree_year].
                  • Small institutions (≤ TAU_INST people): windows overlap.
                  • Large institutions (> TAU_INST, e.g. UNAM): refined to faculty
                    (`degree_field`) AND students must be of the same GENERATION
                    (entry years within ±GEN_WIN) — classmates, not the whole milieu.
                  • Teaching staff link on overlapping years, faculty inferred from
                    the role text; a staff focus is a workplace, so it gets the
                    co_work size cap.
  co_work       — same organisation refined to a sub-unit (party body/state, govt
                  sub-department/secretariat), overlapping years (±WIN). A focus is
                  dropped only if it had more than TAU_WORK people AT THE SAME TIME
                  (size over its whole history would drop e.g. the Supreme Court:
                  160 justices over a century, ≤25 at once).
  co_military   — same military unit / commander extracted from role text + overlap.
  co_revolution — fought in the Revolution in the same state + overlapping years.
  family / mentorship / personal — stated in a biography's `personal_info`; the
                  mentioned name is resolved with StrictNameMatcher. Undated.
(GPT-read biography ties and curated family_surname edges are appended by
07_bio_ties_gpt.py.)

Every edge carries where the two coincided (`focus`), how many people were there in
the year the tie began (`focus_size`; use 1/focus_size to weight), what
each did there (`role_a`, `role_b`) and the years of coincidence (`year_start` =
first year the tie existed). Analyses must use ties formed BEFORE the event they
study (ego_view(..., as_of=year)).

Inputs : parsed_positions.csv, biographies_corrected.csv,
         clean_positions/*.csv, candidates/corcholatas_matched.csv
Outputs: networks/network_edges.csv, networks/network_nodes.csv
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import pandas as pd

CODE_DIR = Path(__file__).resolve().parents[2]
if str(CODE_DIR) not in sys.path:
    sys.path.append(str(CODE_DIR))

from config import (
    BIOGRAPHIES_CSV,
    BIRTHPLACE_CSV,
    CLEAN_POSITIONS_DIR,
    MEXICAN_STATES,
    NETWORK_DIR,
    NETWORK_EDGES_CSV,
    NETWORK_NODES_CSV,
    PARSED_POSITIONS_CSV,
    strip_accents,
    clean_text,
    clean_person_name,
)
from network_utils import StrictNameMatcher, load_corcholatas, name_tokens

WORK_DATASETS = ["govt_positions", "party_positions", "labor_positions",
                 "public_positions", "other_positions"]

# ── tunable parameters ───────────────────────────────────────────────────────
TAU_INST = 60   # an institution with more distinct people than this is "large":
                # refined to faculty and linked by generation only.
TAU_WORK = 60   # a work/military/teaching focus with more people AT THE SAME TIME
                # (max over years) is dropped; the per-tie size is kept in focus_size.
WIN      = 1    # year-overlap tolerance for work / military / revolution.
GEN_WIN  = 1    # same generation = entry years within this many years.
# program length (years) used to turn a single degree year into an enrollment window
PROGRAM_YEARS = {"undergraduate": 5, "masters": 2, "phd": 3, "specialization": 1,
                 "diploma": 1, "certificate": 1, "pre/other": 3}


def _role_of(d: dict) -> str:
    """Readable role for a position record (what the person did at the focus)."""
    for col in ("role_text", "role_text_raw"):
        v = d.get(col)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _s(v):
    """Return a clean non-empty string or None."""
    return v.strip() if isinstance(v, str) and v.strip() and v != "nan" else None


def _overlaps(a0: int, a1: int, b0: int, b1: int, w: int) -> bool:
    return a0 <= b1 + w and b0 <= a1 + w


# ── focus-key derivation ──────────────────────────────────────────────────────
_TRUNCATED_SCHOOL = re.compile(r"\bNo\.?\s*$", re.I)  # "Secondary School No" (number lost)


def edu_focus_key(d: dict, inst_size: dict):
    """Education focus: (institution, faculty or None, degree_level, role, is_large).

    Students link to students and staff to staff (no student–teacher ties), and an
    undergraduate is not linked to a graduate student. Records without a degree
    level (prep, teaching roles) share a 'pre/other' level bucket.
    """
    org = d.get("organization")
    if not isinstance(org, str) or len(org) < 3 or _TRUNCATED_SCHOOL.search(org):
        return None
    lvl = _s(d.get("degree_level")) or "pre/other"
    role = "staff" if d.get("record_type") == "academic_role" else "student"
    if inst_size.get(org, 0) > TAU_INST:
        field = _s(d.get("degree_field"))
        if not field and role == "staff":
            field = staff_faculty(_role_of(d))
        if not field:
            return None  # large institution with no faculty info → too coarse to link
        return ("edu", org, field, lvl, role, True)
    return ("edu", org, None, lvl, role, False)


# Faculty of a teaching/staff record (degree_field is only coded for degrees), from
# the school or subject named in the role text: "professor, National School of Law".
_STAFF_FACULTY = [
    ("law", r"\blaw\b|legal|jurisprudence"),
    ("economics", r"econom"),
    ("business", r"business|accounting|commerce|administration"),
    ("political_sci", r"political|social sciences"),
    ("engineering", r"engineer"),
    ("medicine", r"medic|dentist|nursing"),
    ("architecture", r"architect"),
    ("science", r"chemi|physics|mathemat|sciences?\b"),
    ("humanities", r"philosoph|letters|history"),
    ("military", r"military|war college"),
]


def staff_faculty(text: str):
    for field, pat in _STAFF_FACULTY:
        if re.search(pat, text or "", re.I):
            return field
    return None


def edu_window(d: dict, key) -> tuple[int, int] | None:
    """Enrollment (student) or service (staff) window of an education record."""
    ys, ye = d.get("year_start"), d.get("year_end")
    if pd.isna(ys):
        return None
    ys = int(ys)
    ye = int(ye) if pd.notna(ye) and int(ye) >= ys else ys
    if key[4] == "student" and ye == ys:     # single year = degree year
        ys = ye - PROGRAM_YEARS.get(key[3], 3) + 1
    return ys, ye


def work_focus_key(d: dict):
    """
    Work focus, refined to a sub-unit small enough to imply acquaintance.

    - party: a specific party body (CEN, IEPES, a regional committee) and/or a
      geographic unit (party of a given state). Generic national membership
      ("PRI" with no body and no state) is dropped — being co-members is not co-work.
    - govt: refined by sub_department or a secretariat finer than the organization,
      else the organization itself; a non-federal post carries its state
      ("Secretariat of Government (Quintana Roo)" ≠ federal Gobernación).
    - public (elected office): only state legislatures and the DF Assembly — small
      bodies whose members sat together. Legislative committees ("Gran Comision",
      "Department of the Federal District Committee") are not shared workplaces and
      the federal Congress is too large → dropped.
    - labor / other: the organization.
    Labels that are parsing fragments ("administration and", "government") are dropped.
    """
    key = _work_focus_key(d)
    if key is None or not key[1][:1].isupper():
        return None
    return key


_PUBLIC_BODY = re.compile(r"^(?:State Legislature|Assembly of the Federal District)")


def _work_focus_key(d: dict):
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
            label = f"{org} – {sub}"
        elif sec and sec != org:
            label = sec
        else:
            label = org
        st = _s(d.get("work_state"))
        if d.get("is_federal") != True and st and st != "Federal District":  # noqa: E712
            label = f"{label} ({st})"
        return ("work", label)
    if src == "public_positions":
        return ("work", org) if org and _PUBLIC_BODY.match(org) else None
    if org:
        return ("work", org)
    return None


def focus_label(key) -> str:
    if key[0] == "edu":
        _, org, field, lvl, role, large = key
        base = f"{org} | {field}" if field else org
        gen = "/generation" if large and role == "student" else ""
        return f"{base} [{lvl}/{role}{gen}]"
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


# Revolutionary co-service: fought in the Revolution in the same state and years.
# Faction is rarely tagged in the source, so the focus is the state (extracted from
# the text); the specific faction stays visible in each person's role text.
_REVOLUTION = re.compile(
    r"revolution|zapatist|villist|carrancist|maderist|constitutionalist|obregonist|"
    r"cristero|huertist|insurgent|rebel|joined|fought|forces|brigade|division|battalion",
    re.I)
_STATE_VARIANTS = sorted(
    [(strip_accents(v.lower()), canon)
     for canon, (variants, _, _) in MEXICAN_STATES.items() for v in variants],
    key=lambda x: -len(x[0]))


def revolution_foci(text) -> set:
    """States where a revolutionary military role was served (one focus per state)."""
    if not isinstance(text, str) or not _REVOLUTION.search(text):
        return set()
    norm = strip_accents(text.lower())
    foci = set()
    # a state name followed by a unit word ("Sonora Brigade") is a unit name, not a
    # battle location — exclude it.
    unit_after = r"(?!\s+(?:brigade|battalion|regiment|division|corps|cavalry|infantry|zone))"
    for variant, canon in _STATE_VARIANTS:
        if re.search(r"\b" + re.escape(variant) + r"\b" + unit_after, norm):
            foci.add(f"Revolution ({canon})")
    return foci


# ── explicit relationship patterns (from biographies personal_info) ───────────
# (pattern, edge_type, blood_kin) — for blood kin a bare given name ("brother of
# Rafael") is completed with the biographee's own surnames before matching.
FAMILY_PATTERNS = [
    (r"(?:son|daughter)\s+of\s+([^,;]+)", True),
    (r"(?:brother|sister)\s+(?:of\s+)?([^,;]+)", True),
    (r"married\s+([^,;]+)", False),
    (r"(?:nephew|niece)\s+of\s+([^,;]+)", False),
    (r"(?:uncle|aunt)\s+(?:of\s+)?([^,;]+)", False),
    (r"(?:cousin)\s+(?:of\s+)?([^,;]+)", False),
    (r"(?:father|mother)-in-law\s+(?:of\s+)?([^,;]+)", False),
    (r"(?:son-in-law|daughter-in-law)\s+(?:of\s+)?([^,;]+)", False),
    (r"(?:grandson|granddaughter)\s+(?:of\s+)?([^,;]+)", False),
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
    [(p, "family", blood) for p, blood in FAMILY_PATTERNS]
    + [(p, "mentorship", False) for p in MENTORSHIP_PATTERNS]
    + [(p, "personal", False) for p in PERSONAL_PATTERNS]
)
# trailing role words that should be trimmed from a mentioned name
_MENTION_TAIL = re.compile(
    r"\s+(?:who|whose|was|is|a|an|the|at|in|since|during|when|from|secretary|director|"
    r"governor|president|senator|federal|head|mayor|former|general|leader|chief|"
    r"deputy|ambassador)\b.*$",
    re.IGNORECASE,
)
_AND = re.compile(r"\s+and\s+|\s*&\s*", re.IGNORECASE)


# ── co-location machinery ─────────────────────────────────────────────────────
# Minimum plausible age at the start of a record. Younger = a mis-parsed year (e.g.
# "law student at UNAM, 1945" for someone born 1951): such records are not used to
# form ties. Primary/secondary school records (level 'pre/other') may start at 4.
MIN_AGE_WORK, MIN_AGE_STUDENT, MIN_AGE_STAFF, MIN_AGE_SCHOOL, MAX_AGE = 14, 14, 18, 4, 100


def min_age(key) -> int:
    if key[0] == "edu":
        if key[4] == "staff":
            return MIN_AGE_STAFF
        return MIN_AGE_SCHOOL if key[3] == "pre/other" else MIN_AGE_STUDENT
    return MIN_AGE_WORK


def build_focus_index(df: pd.DataFrame, key_fn, window_fn=None, byear=None) -> dict:
    """focus_key -> [(person_id, year_start, year_end, role)] for dated records
    whose start is at a plausible age (records failing min_age / MAX_AGE are skipped)."""
    index: dict = defaultdict(list)
    byear = byear or {}
    skipped = 0
    for d in df.to_dict("records"):
        key = key_fn(d)
        if key is None:
            continue
        if window_fn is not None:
            win = window_fn(d, key)
        elif pd.notna(d.get("year_start")):
            ys = int(d["year_start"])
            ye = int(d["year_end"]) if pd.notna(d.get("year_end")) else ys
            win = (ys, max(ys, ye))
        else:
            win = None
        if win is None:
            continue  # co-location requires a year
        by = byear.get(int(d["person_id"]))
        if by and not (min_age(key) <= win[0] - by <= MAX_AGE):
            skipped += 1
            continue
        index[key].append((int(d["person_id"]), win[0], win[1], _role_of(d)))
    if skipped:
        print(f"    skipped {skipped} records starting at an implausible age")
    return index


def concurrent_sizes(index: dict) -> dict:
    """focus_key -> {year: number of distinct people there that year}.

    Size is measured SIMULTANEOUSLY, not over the focus' whole history: the
    Secretariat of Programming and Budget had 105 people in the dataset over
    1973–92 but at most 44 at once — a small elite who plausibly all knew each other.
    """
    out = {}
    for k, recs in index.items():
        per_year: dict = defaultdict(set)
        for pid, ys, ye, _ in recs:
            for y in range(ys, ye + 1):
                per_year[y].add(pid)
        out[k] = {y: len(p) for y, p in per_year.items()}
    return out


def cap(index: dict, keep=lambda k: True) -> dict:
    """Drop foci with more than TAU_WORK people at the same time (unless keep(k))."""
    conc = concurrent_sizes(index)
    return {k: v for k, v in index.items()
            if keep(k) or max(conc[k].values()) <= TAU_WORK}


class EdgeSet:
    """Undirected edges keyed by (a, b, type, focus); keeps the earliest coincidence."""

    def __init__(self):
        self.e: dict = {}

    def add(self, p, q, etype, focus, size, role_p, role_q, ys, ye, stated_by=None,
            confirmed_by="rule"):
        if p == q:
            return
        if p > q:
            p, q, role_p, role_q = q, p, role_q, role_p
        k = (p, q, etype, focus)
        cur = self.e.get(k)
        if cur is None:
            self.e[k] = dict(person_a=p, person_b=q, edge_type=etype, focus=focus,
                             focus_size=size, role_a=role_p, role_b=role_q,
                             year_start=ys, year_end=ye, stated_by=stated_by,
                             confirmed_by=confirmed_by)
        elif ys is not None and (cur["year_start"] is None or ys < cur["year_start"]):
            cur.update(role_a=role_p, role_b=role_q, year_start=ys,
                       year_end=max(ye, cur["year_end"] or ye))

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame(list(self.e.values()))


def colocation_edges(edges: EdgeSet, index: dict, etype: str, linked):
    """Add an edge for every pair of records at the same focus satisfying `linked`."""
    conc = concurrent_sizes(index)
    for key, recs in index.items():
        label = focus_label(key)
        for r1, r2 in combinations(recs, 2):
            if r1[0] != r2[0] and linked(key, r1, r2):
                ys = max(r1[1], r2[1])                 # first year both were there
                # focus_size = people at the focus in the year the tie began
                size = conc[key].get(ys) or max(conc[key].values())
                edges.add(r1[0], r2[0], etype, label, size, r1[3], r2[3],
                          ys, max(ys, min(r1[2], r2[2])))


def edu_linked(key, r1, r2) -> bool:
    if key[5] and key[4] == "student":           # large institution: same generation
        return abs(r1[1] - r2[1]) <= GEN_WIN
    return _overlaps(r1[1], r1[2], r2[1], r2[2], 0)


def overlap_linked(key, r1, r2) -> bool:
    return _overlaps(r1[1], r1[2], r2[1], r2[2], WIN)


def expand_foci(mil: pd.DataFrame, foci_fn, col: str) -> pd.DataFrame:
    rows = []
    for d in mil.to_dict("records"):
        text = d.get("role_text") if isinstance(d.get("role_text"), str) else d.get("role_text_raw")
        for fk in foci_fn(text):
            rows.append({**d, col: fk})
    return pd.DataFrame(rows)


# ── main ─────────────────────────────────────────────────────────────────────
def main():
    print("Loading people …")
    pp = pd.read_csv(PARSED_POSITIONS_CSV, usecols=["person_id", "person_name", "birth_date_clean"])
    people = pp.dropna(subset=["person_id", "person_name"]).drop_duplicates("person_id")
    pid_name = dict(zip(people.person_id, people.person_name))
    byear = {pid: int(str(b)[:4]) for pid, b in zip(people.person_id, people.birth_date_clean)
             if str(b)[:4].isdigit()}
    print(f"  {len(pid_name):,} people")

    edges = EdgeSet()

    # ── education ────────────────────────────────────────────────────────────
    edu = pd.read_csv(CLEAN_POSITIONS_DIR / "education.csv")
    inst_size = (edu.dropna(subset=["organization"])
                    .groupby("organization")["person_id"].nunique().to_dict())
    edu_index = build_focus_index(edu, lambda d: edu_focus_key(d, inst_size), edu_window,
                                  byear)
    # teaching staff of a school is a workplace → same size cap as co_work
    edu_index = cap(edu_index, keep=lambda k: k[4] == "student")
    print(f"Building co-education edges ({len(edu_index):,} foci) …")
    colocation_edges(edges, edu_index, "co_education", edu_linked)

    # ── work (all work datasets combined), refined + size-capped ─────────────
    work = pd.concat([pd.read_csv(CLEAN_POSITIONS_DIR / f"{n}.csv").assign(source=n)
                      for n in WORK_DATASETS], ignore_index=True)
    work_all = build_focus_index(work, work_focus_key, byear=byear)
    work_index = cap(work_all)
    print(f"Building co-work edges ({len(work_index):,} foci; "
          f"{len(work_all) - len(work_index)} dropped as > {TAU_WORK} people at once) …")
    for k in sorted(set(work_all) - set(work_index), key=str):
        print(f"    dropped: {focus_label(k)}")
    colocation_edges(edges, work_index, "co_work", overlap_linked)

    # ── military unit / commander, and revolutionary state ───────────────────
    mil = pd.read_csv(CLEAN_POSITIONS_DIR / "military_positions.csv")
    mil_index = cap(build_focus_index(expand_foci(mil, military_foci, "f"),
                                      lambda d: ("mil", d["f"]), byear=byear))
    print(f"Building co-military edges ({len(mil_index):,} foci) …")
    colocation_edges(edges, mil_index, "co_military", overlap_linked)
    revo_index = cap(build_focus_index(expand_foci(mil, revolution_foci, "f"),
                                       lambda d: ("revo", d["f"]), byear=byear))
    print(f"Building co-revolution edges ({len(revo_index):,} foci) …")
    colocation_edges(edges, revo_index, "co_revolution", overlap_linked)

    # ── explicit ties stated in every biography ──────────────────────────────
    print("Building explicit edges (family / mentorship / personal) …")
    matcher = StrictNameMatcher(pid_name)
    name_to_pid = {v: k for k, v in pid_name.items()}
    bio = pd.read_csv(BIOGRAPHIES_CSV, usecols=["name", "personal_info"])
    n_mentions = n_matched = 0
    for d in bio.to_dict("records"):
        ego = name_to_pid.get(clean_person_name(d["name"]))
        info = d.get("personal_info")
        if ego is None or not isinstance(info, str) or not info.strip():
            continue
        info = clean_text(info)
        ego_paternal = name_tokens(pid_name[ego].split(",")[0])[0]
        for pat, etype, blood in EXPLICIT_PATTERNS:
            for m in re.finditer(pat, info, re.IGNORECASE):
                for part in _AND.split(m.group(1)):   # "X and Y" → two mentions
                    mention = _MENTION_TAIL.sub("", part.strip()).strip()
                    if len(mention) < 4:
                        continue
                    n_mentions += 1
                    alter, _ = matcher.match(mention)
                    how = "rule"
                    if alter is None and blood and len(name_tokens(mention)) <= 2:
                        # bare given name of a blood relative → add own paternal surname
                        # (lower precision: tagged so analyses can drop it)
                        alter, _ = matcher.match(f"{mention} {ego_paternal}")
                        how = "rule_given_name"
                    if alter is not None and alter != ego:
                        n_matched += 1
                        phrase = info[m.start():m.start(1)].strip().lower()  # "son of"
                        edges.add(ego, alter, etype, phrase, None, "stated in own bio",
                                  mention[:80], None, None, stated_by=ego, confirmed_by=how)
    print(f"  {n_matched:,} of {n_mentions:,} name mentions resolved to a person")

    # ── assemble ─────────────────────────────────────────────────────────────
    edf = edges.frame()
    # one row per (pair, explicit type): the focus holds the kin/relation phrase
    explicit = edf["edge_type"].isin(["family", "mentorship", "personal"])
    edf = pd.concat([edf[~explicit],
                     edf[explicit].drop_duplicates(["person_a", "person_b", "edge_type"])],
                    ignore_index=True)
    # where each tie's date comes from: co-location → years both were there;
    # stated ties are undated here (07 dates them: stated year or relatives' birth)
    edf["date_basis"] = edf["year_start"].map(lambda y: "overlap" if pd.notna(y) else None)
    edf["name_a"] = edf["person_a"].map(pid_name)
    edf["name_b"] = edf["person_b"].map(pid_name)
    edf = edf[["person_a", "name_a", "person_b", "name_b", "edge_type", "focus",
               "focus_size", "role_a", "role_b", "year_start", "year_end",
               "date_basis", "stated_by", "confirmed_by"]]
    for c in ("year_start", "year_end", "focus_size", "stated_by"):
        edf[c] = edf[c].astype("Int64")
    NETWORK_DIR.mkdir(parents=True, exist_ok=True)
    edf.to_csv(NETWORK_EDGES_CSV, index=False)

    # ── nodes: everyone, with tapado info from the per-election crosswalk ────
    corch = load_corcholatas()
    tap_years = corch.groupby("person_id")["election_year"].apply(
        lambda s: ";".join(map(str, sorted(set(s))))).to_dict()
    win_years = corch[corch.is_winner == 1].groupby("person_id")["election_year"].apply(
        lambda s: ";".join(map(str, sorted(set(s))))).to_dict()
    bp = (pd.read_csv(BIRTHPLACE_CSV)[["person_id", "state"]].dropna()
            .drop_duplicates("person_id").set_index("person_id")["state"].to_dict())
    deg = pd.concat([edf.person_a, edf.person_b]).value_counts().to_dict()
    # how much the biography says about each person: network size mechanically
    # grows with it, so analyses must control for / normalise by these
    recs = pd.read_csv(PARSED_POSITIONS_CSV, usecols=["person_id", "field_type", "year_start"])
    recs = recs[recs.field_type != "birthplace"]
    n_rec = recs.groupby("person_id").size().to_dict()
    n_dated = recs.dropna(subset=["year_start"]).groupby("person_id").size().to_dict()
    pinfo_len = {name_to_pid.get(clean_person_name(n)): len(str(t)) for n, t in
                 zip(bio["name"], bio["personal_info"]) if isinstance(t, str)}
    nodes = pd.DataFrame([{
        "person_id": pid, "name": name, "birth_year": byear.get(pid),
        "birth_state": bp.get(pid), "degree": deg.get(pid, 0),
        "n_records": n_rec.get(pid, 0), "n_dated_records": n_dated.get(pid, 0),
        "personal_info_chars": pinfo_len.get(pid, 0),
        "is_tapado": int(pid in tap_years),
        "tapado_elections": tap_years.get(pid, ""),
        "winner_elections": win_years.get(pid, ""),
    } for pid, name in sorted(pid_name.items())])
    nodes["birth_year"] = nodes["birth_year"].astype("Int64")
    nodes.to_csv(NETWORK_NODES_CSV, index=False)

    # ── report ───────────────────────────────────────────────────────────────
    print(f"\nSaved {len(edf):,} edges → {NETWORK_EDGES_CSV}")
    print(f"Saved {len(nodes):,} nodes → {NETWORK_NODES_CSV}")
    print("\nEdge types:")
    print(edf["edge_type"].value_counts().to_string())
    pairs = edf[["person_a", "person_b"]].drop_duplicates()
    print(f"\nDistinct connected pairs: {len(pairs):,}")
    print(f"People with ≥1 tie: {(nodes.degree > 0).sum():,} / {len(nodes):,}")
    print("\nLargest co_education foci (edges):")
    ce = edf[edf.edge_type == "co_education"].focus.value_counts().head(5)
    print(ce.to_string())


if __name__ == "__main__":
    main()
