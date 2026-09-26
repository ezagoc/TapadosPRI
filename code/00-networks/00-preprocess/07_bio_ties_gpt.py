"""
07_bio_ties_gpt.py  —  network stage 2: relationships stated in the biographies (GPT-read)

06 finds family / mentorship / personal ties with regular expressions, which miss
most phrasings ("early political patrons included A, B and C", "thesis committee
included …", "organized group of friends, including …"). Here GPT reads the
`personal_info` section of EVERY biography and lists each person named there with
their relationship to the biographee and the verbatim quote. The extraction is
grounded in the source text:

  - a mention is kept only if its name AND its quote appear verbatim in the
    biography text (accent/case-insensitive) — anything else is discarded as a
    hallucination;
  - the name is resolved to a person_id with the strict matcher of 06; a bare given
    name of a close blood relative ("brother Raúl") is completed with the
    biographee's paternal surname and tagged `gpt_bio_given_name`;
  - each tie is dated: GPT gives the year the relationship began when the text
    states it (the year must be in the quote or within 200 characters of the
    name) or implies a life
    stage (`inferred`, from the birth year); blood relatives are dated by the
    younger one's birth (`birth`). Stored in `year_start` + `date_basis`;
  - a family match must be age-consistent with the kin term (a "father" 12–70 years
    older, a "brother" within 25 years, …) — this rejects namesakes, e.g. a son who
    shares his father's full name.

GPT answers are cached per biography in networks/bio_mentions_gpt.csv (full audit
trail: every mention, quote, validation and match result). Delete the cache to
re-query. Also re-appends the 30 human-curated `family_surname` ties
(networks/family_surname_review.csv, keep == 1).

Run AFTER 06 (06 rewrites network_edges.csv from scratch).

Inputs : biographies_corrected.csv, networks/network_edges.csv,
         networks/family_surname_review.csv
Outputs: networks/bio_mentions_gpt.csv (cache + audit),
         networks/network_edges.csv (+ gpt_bio and family_surname edges),
         networks/network_nodes.csv (degree refreshed)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

CODE_DIR = Path(__file__).resolve().parents[2]
if str(CODE_DIR) not in sys.path:
    sys.path.append(str(CODE_DIR))

from config import (
    openai_api_key,
    BIOGRAPHIES_CSV,
    DATA_DIR,
    NETWORK_DIR,
    NETWORK_EDGES_CSV,
    NETWORK_NODES_CSV,
    PARSED_POSITIONS_CSV,
    clean_person_name,
    clean_text,
    strip_accents,
)
from network_utils import StrictNameMatcher, name_tokens

MODEL      = "gpt-5.4-mini-2026-03-17"   # pinned snapshot for reproducibility
PROMPT_VERSION = 2   # v2 adds the year each relationship began; bump to re-query
CONTEXT_CHARS  = 200  # a stated year must be this close to the mentioned name
WORKERS    = 8
CACHE_CSV  = NETWORK_DIR / "bio_mentions_gpt.csv"
REVIEW_CSV = NETWORK_DIR / "family_surname_review.csv"

RELATION_TYPES = {"family", "mentorship", "personal"}
_NEGATED = re.compile(r"\bnot\b|\bno (?:stated |personal |explicit )?relation"
                      # a relative's relation, not the biographee's ("father's friend")
                      r"|\b(?:father|mother|brother|sister|wife|husband|son|daughter)['’]s\b",
                      re.I)

# Kin terms → allowed (alter birth year − biographee birth year) range. Guards against
# namesakes (father and son often share the full name). Unknown birth year → accepted.
_KIN_AGE_GAP = [
    (re.compile(r"grand(?:father|mother|parent)", re.I), (-100, -30)),
    (re.compile(r"grand(?:son|daughter|child)", re.I), (30, 100)),
    (re.compile(r"(?:father|mother|parent)(?!-in-law)", re.I), (-70, -12)),
    (re.compile(r"\b(?:son|daughter|child)(?!-in-law)", re.I), (12, 70)),
    (re.compile(r"brother|sister|sibling|spouse|wife|husband|married", re.I), (-25, 25)),
    (re.compile(r"cousin", re.I), (-35, 35)),
]


def kin_age_ok(detail, gap) -> bool:
    if gap is None or pd.isna(gap):
        return True
    for pat, (lo, hi) in _KIN_AGE_GAP:
        if pat.search(str(detail)):
            return lo <= gap <= hi
    return True
# Blood kin: the tie exists from the younger person's birth → dated by birth year.
# (Spouses, in-laws, godparents are dated only if the text states the year.)
_BLOOD_KIN = re.compile(r"\b(?:son|daughter|father|mother|parent|brother|sister|sibling|"
                        r"grand\w*|uncle|aunt|nephew|niece|cousin)\b(?!-in-law)", re.I)
_NOT_BLOOD = re.compile(r"in-law|step|god|compadre|married|spouse|wife|husband", re.I)


def is_blood_kin(detail) -> bool:
    d = str(detail)
    return bool(_BLOOD_KIN.search(d)) and not _NOT_BLOOD.search(d)


# relatives who share the biographee's paternal surname (for bare-given-name mentions)
_SAME_SURNAME_KIN = re.compile(r"\b(father|son|daughter|brother|sister)\b", re.I)

PROMPT = """Below is the "personal information" section of the biography of {name} \
(born {birth_year}), from Roderic Ai Camp's Mexican Political Biographies.

List EVERY specific, named person that the text relates personally to {name}:
- family: any relative by blood or marriage (parent, child, sibling, spouse, in-law,
  uncle/aunt, nephew/niece, cousin, grandparent, grandchild, godparent/compadre).
- mentorship: teacher, professor, thesis director or committee member, political
  patron or mentor, someone who influenced the career, protégé or student OF {name},
  a disciple, someone who brought {name} into a post.
- personal: friend, classmate, schoolmate, companion, co-founder, member of the same
  group, collaborator stated as close.
Do NOT include people mentioned only as holders of a position, people related to
someone other than {name} (e.g. a relative's boss), or anyone whose relationship to
{name} is not explicitly stated. Do not use any knowledge outside the text.

Return JSON: {{"mentions": [{{"name": "<name exactly as written>",
"relation_type": "family|mentorship|personal",
"relation_detail": "<short, e.g. uncle, political patron, thesis committee, friend, protégé of {name}>",
"quote": "<shortest verbatim span of the text containing the name and relationship>",
"since_year": <year the relationship BEGAN, integer, or null>,
"since_basis": "exact|decade|inferred|null"}}]}}
since_year rules: "exact" = the text states that year for this relationship ("met at
MIT in 1978", "married in 1950"); "decade" = the text gives a decade ("in the 1930s" →
1930); "inferred" = the text clearly implies the life stage, which you convert using
the birth year ("since childhood" → birth+8, "classmates at the National Preparatory
School" → birth+15, "law school classmates" → birth+19). Otherwise null. Do not date
blood relatives (parents, siblings, children…): use null.
If there are none, return {{"mentions": []}}.

TEXT:
{text}"""


def _n(s) -> str:
    s = strip_accents(str(s).lower())
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", s)).strip()


def ask_gpt(client, name: str, birth_year, text: str) -> list[dict]:
    prompt = PROMPT.format(name=name, text=text,
                           birth_year=birth_year if birth_year else "year unknown")
    resp = client.chat.completions.create(
        model=MODEL,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
    )
    return json.loads(resp.choices[0].message.content).get("mentions", [])


def text_hash(text: str) -> str:
    return hashlib.sha1(str(text).encode("utf-8")).hexdigest()[:12]


def query_missing(bios: pd.DataFrame, cache: pd.DataFrame, limit: int | None,
                  offline: bool = False) -> pd.DataFrame:
    """Query GPT for every biography not yet in the cache (at this PROMPT_VERSION)."""
    done = set(cache["person_id"]) if len(cache) else set()
    todo = bios[~bios["person_id"].isin(done)]
    if limit:
        todo = todo.head(limit)
    if todo.empty:
        print(f"  all {len(bios):,} biographies already in cache")
        return cache
    if offline:
        print(f"  --offline: {len(todo):,} biographies not in cache are skipped "
              f"(no GPT ties for them until a later online run)")
        return cache
    import openai
    client = openai.OpenAI(api_key=openai_api_key())
    print(f"  querying {MODEL} for {len(todo):,} biographies ({WORKERS} workers) …")

    rows, failed = [], []
    with ThreadPoolExecutor(WORKERS) as pool:
        futs = {pool.submit(ask_gpt, client, r.person_name, r.birth_year, r.text): r
                for r in todo.itertuples()}
        for i, fut in enumerate(as_completed(futs), 1):
            r = futs[fut]
            try:
                mentions = fut.result()
            except Exception as e:                       # keep going; retried next run
                failed.append((r.person_name, str(e)[:120]))
                continue
            base = {"person_id": r.person_id, "person_name": r.person_name,
                    "model": MODEL, "prompt_version": PROMPT_VERSION,
                    "text_hash": text_hash(r.text)}
            if not mentions:                             # remember "no mentions" too
                rows.append(base)
            for m in mentions:
                rows.append({**base,
                             "name_mentioned": m.get("name"),
                             "relation_type": str(m.get("relation_type", "")).lower(),
                             "relation_detail": m.get("relation_detail"),
                             "quote": m.get("quote"),
                             "since_year": m.get("since_year"),
                             "since_basis": m.get("since_basis")})
            if i % 200 == 0:
                print(f"    {i:,}/{len(todo):,}")
                pd.concat([cache, pd.DataFrame(rows)]).to_csv(CACHE_CSV, index=False)
    if failed:
        print(f"  ! {len(failed)} biographies failed (re-run to retry), e.g. {failed[0]}")
    cache = pd.concat([cache, pd.DataFrame(rows)], ignore_index=True)
    cache.to_csv(CACHE_CSV, index=False)
    return cache


def date_mention(r, text: str, birth_year=None):
    """(year, basis) the stated relationship began, validated against the text.

    stated_exact   the year appears in the quote itself;
    stated_context the year appears within CONTEXT_CHARS of the mentioned name;
    stated_decade  a decade ("1930s") in the quote or near the name;
    inferred       GPT's life-stage estimate (must be ≥ birth + 5, i.e. not a birth
                   year returned by mistake). Anything else → undated.
    """
    y = pd.to_numeric(getattr(r, "since_year", None), errors="coerce")
    basis = str(getattr(r, "since_basis", "")).lower()
    if pd.isna(y) or not 1850 <= y <= 2012 or basis not in ("exact", "decade", "inferred"):
        return None, None
    y = int(y)
    if basis == "inferred":
        if birth_year and y < birth_year + 5:
            return None, None
        return y, "inferred"
    quote, t = str(getattr(r, "quote", "")), _n(text)
    if str(y) in quote:
        return y, "stated_exact" if basis == "exact" else "stated_decade"
    pos = t.find(_n(r.name_mentioned))
    if pos >= 0 and str(y) in t[max(0, pos - CONTEXT_CHARS): pos + CONTEXT_CHARS]:
        return y, "stated_context" if basis == "exact" else "stated_decade"
    return None, None                       # year not tied to this mention → undated


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="query at most N new biographies (testing)")
    ap.add_argument("--offline", action="store_true",
                    help="use cached answers only; do not call the API")
    args = ap.parse_args()

    pp = pd.read_csv(PARSED_POSITIONS_CSV,
                     usecols=["person_id", "person_name", "birth_date_clean"])
    pp = pp.dropna(subset=["person_id", "person_name"]).drop_duplicates("person_id")
    pid_name = dict(zip(pp.person_id, pp.person_name))
    byear = {pid: int(str(b)[:4]) for pid, b in zip(pp.person_id, pp.birth_date_clean)
             if str(b)[:4].isdigit()}
    name_to_pid = {v: k for k, v in pid_name.items()}

    bio = pd.read_csv(BIOGRAPHIES_CSV, usecols=["name", "personal_info"])
    bio["person_id"] = bio["name"].map(lambda n: name_to_pid.get(clean_person_name(n)))
    bio["text"] = bio["personal_info"].map(clean_text)
    bio = bio.dropna(subset=["person_id"])
    bio = bio[bio["text"].str.len() > 0].drop_duplicates("person_id")
    bio["person_id"] = bio["person_id"].astype(int)
    bio["person_name"] = bio["person_id"].map(pid_name)
    bio["birth_year"] = bio["person_id"].map(byear)
    text_of = dict(zip(bio.person_id, bio.text))
    print(f"{len(bio):,} biographies with personal_info")

    cache = pd.read_csv(CACHE_CSV) if CACHE_CSV.exists() else pd.DataFrame(
        columns=["person_id", "person_name", "name_mentioned", "relation_type",
                 "relation_detail", "quote", "model"])
    # person_ids can shift if 04 is re-run: drop cached answers whose id no longer
    # carries the same name (they are re-queried below)
    stale = cache["person_id"].map(pid_name) != cache["person_name"]
    if stale.any():
        print(f"  dropping {stale.sum()} cached rows with stale person_ids")
        cache = cache[~stale]
    # answers from an older prompt are re-queried
    if "prompt_version" not in cache.columns:
        cache["prompt_version"] = 1
    old = pd.to_numeric(cache["prompt_version"], errors="coerce").fillna(1) != PROMPT_VERSION
    if old.any():
        print(f"  dropping {cache.loc[old, 'person_id'].nunique():,} biographies cached "
              f"with an older prompt (v{PROMPT_VERSION} re-query)")
        cache = cache[~old]
    # answers for a text that has since changed are stale: rows carry the hash of the
    # text sent to GPT; legacy rows (no hash) are dropped for the biographies whose
    # personal_info 03b_split_merged_biographies.py repaired
    if "text_hash" not in cache.columns:
        cache["text_hash"] = None
    has = cache["text_hash"].notna()
    changed = has & (cache["text_hash"] != cache["person_id"].map(lambda p: text_hash(text_of.get(p, ""))))
    repairs = DATA_DIR / "biography_repairs.csv"
    if repairs.exists():
        rep = pd.read_csv(repairs)
        hosts = rep.loc[rep.personal_info_changed.fillna(0) == 1, "host_name"].dropna()
        repaired_ids = {name_to_pid.get(clean_person_name(n)) for n in hosts} - {None}
        changed |= ~has & cache["person_id"].isin(repaired_ids)
    if changed.any():
        print(f"  dropping {cache.loc[changed, 'person_id'].nunique():,} biographies whose "
              f"personal_info changed since they were queried")
        cache = cache[~changed]
    cache = query_missing(bio, cache, args.limit, offline=args.offline)

    # ── validate against the source text and resolve names ──────────────────
    matcher = StrictNameMatcher(pid_name)
    for col in ("since_year", "since_basis"):
        if col not in cache.columns:
            cache[col] = None
    m = cache.dropna(subset=["name_mentioned"]).copy()
    m = m.drop(columns=[c for c in ("name_in_text", "quote_in_text", "alter_id",
                                    "match_status", "tie_year", "date_basis")
                        if c in m.columns])
    src = m["person_id"].map(lambda p: _n(text_of.get(p, "")))
    src_raw = text_of
    m["name_in_text"] = [_n(a) in s for a, s in zip(m["name_mentioned"], src)]
    m["quote_in_text"] = [_n(q) in s for q, s in zip(m["quote"].fillna(""), src)]
    alters, status = [], []
    for r in m.itertuples():
        if not (r.name_in_text and r.quote_in_text and r.relation_type in RELATION_TYPES):
            alters.append(None); status.append("rejected: not grounded in text")
            continue
        if _NEGATED.search(str(r.relation_detail)):
            alters.append(None); status.append("rejected: relation negated")
            continue
        pid, st = matcher.match(r.name_mentioned)
        if pid is None and r.relation_type == "family" and \
                len(name_tokens(r.name_mentioned)) <= 2 and \
                _SAME_SURNAME_KIN.search(str(r.relation_detail)):
            paternal = name_tokens(pid_name[r.person_id].split(",")[0])[0]
            pid, st = matcher.match(f"{r.name_mentioned} {paternal}")
            st = "given_name" if pid is not None else st
        if pid == r.person_id:
            pid, st = None, "self"
        elif pid is not None and r.relation_type == "family":
            b0, b1 = byear.get(r.person_id), byear.get(pid)
            if not kin_age_ok(r.relation_detail, (b1 - b0) if b0 and b1 else None):
                pid, st = None, "rejected: age inconsistent with kin term"
        alters.append(pid); status.append(st)
    m["alter_id"] = pd.array(alters, dtype="Int64")
    m["match_status"] = status
    m["tie_year"], m["date_basis"] = zip(*[
        date_mention(r, src_raw.get(r.person_id, ""), byear.get(r.person_id))
        for r in m.itertuples()])
    m["tie_year"] = m["tie_year"].astype("Int64")
    audit = pd.concat([cache[cache["name_mentioned"].isna()], m], ignore_index=True)
    audit.to_csv(CACHE_CSV, index=False)
    print(f"\nMentions: {len(m):,}  | grounded: {(m.name_in_text & m.quote_in_text).sum():,}"
          f"  | resolved to a person: {m.alter_id.notna().sum():,}")
    print(m["match_status"].value_counts().to_string())

    # ── merge into the network ───────────────────────────────────────────────
    edges = pd.read_csv(NETWORK_EDGES_CSV)
    edges = edges[~edges["confirmed_by"].str.contains("gpt", na=False)].copy()   # idempotent
    ekey = {(a, b, t): i for i, (a, b, t) in
            enumerate(zip(edges.person_a, edges.person_b, edges.edge_type))}
    new, seen = [], set()
    # earliest dated mention first, so each tie keeps its earliest stated year
    for r in m[m.alter_id.notna()].sort_values("tie_year", na_position="last").itertuples():
        ego, alt = int(r.person_id), int(r.alter_id)
        a, b = min(ego, alt), max(ego, alt)
        how = "gpt_bio_given_name" if r.match_status == "given_name" else "gpt_bio"
        k = (a, b, r.relation_type)
        if k in seen:                                   # same tie from another mention
            continue
        seen.add(k)
        if k in ekey:                                   # regex already found it
            i = edges.index[ekey[k]]
            if "gpt" not in str(edges.at[i, "confirmed_by"]):
                edges.at[i, "confirmed_by"] = f"{edges.at[i, 'confirmed_by']}+{how}"
            if pd.isna(edges.at[i, "year_start"]) and pd.notna(r.tie_year):
                edges.at[i, "year_start"], edges.at[i, "date_basis"] = r.tie_year, r.date_basis
            continue
        ego_role, alt_role = "stated in own bio", str(r.quote)[:200]
        new.append({"person_a": a, "person_b": b, "edge_type": r.relation_type,
                    "focus": r.relation_detail, "focus_size": None,
                    "role_a": ego_role if a == ego else alt_role,
                    "role_b": alt_role if a == ego else ego_role,
                    "year_start": r.tie_year if pd.notna(r.tie_year) else None,
                    "year_end": None, "date_basis": r.date_basis, "stated_by": ego,
                    "confirmed_by": how})

    # human-curated kinship by shared surname (see family_surname_review.csv)
    rev = pd.read_csv(REVIEW_CSV)
    rev = rev[rev["keep"].astype(str).str.strip().isin(["1", "1.0"])]
    for r in rev.itertuples():
        e_id, a_id = int(r.ego_id), int(r.alter_id)
        assert pid_name.get(e_id) == r.ego_name and pid_name.get(a_id) == r.alter_name, \
            f"family_surname_review ids out of sync with parsed_positions: {r.ego_name}"
        rel = r.corrected_relationship if isinstance(r.corrected_relationship, str) \
            and r.corrected_relationship.strip() else r.relationship_gpt
        a, b = min(e_id, a_id), max(e_id, a_id)
        new.append({"person_a": a, "person_b": b, "edge_type": "family_surname",
                    "focus": rel, "focus_size": None,
                    "role_a": f"shared surname: {r.shared_surname}",
                    "role_b": f"shared surname: {r.shared_surname}",
                    "year_start": None, "year_end": None, "date_basis": None,
                    "stated_by": None, "confirmed_by": "gpt+human"})

    new = pd.DataFrame(new)
    new["name_a"] = new["person_a"].map(pid_name)
    new["name_b"] = new["person_b"].map(pid_name)
    edges = pd.concat([edges, new[edges.columns]], ignore_index=True)

    # a stated year before the younger person was born is an error → undated
    young = [max(byear.get(a) or 0, byear.get(b) or 0)
             for a, b in zip(edges.person_a, edges.person_b)]
    early = edges["year_start"].notna() & (edges["year_start"] < pd.Series(young, index=edges.index)) \
        & edges["edge_type"].isin(["family", "mentorship", "personal"])
    edges.loc[early, ["year_start", "date_basis"]] = [pd.NA, None]

    # blood relatives with no stated year: the tie exists from the younger one's birth
    fam = edges["edge_type"].isin(["family", "family_surname"]) & edges["year_start"].isna()
    for i in edges.index[fam]:
        b0, b1 = byear.get(edges.at[i, "person_a"]), byear.get(edges.at[i, "person_b"])
        if b0 and b1 and is_blood_kin(edges.at[i, "focus"]):
            edges.at[i, "year_start"], edges.at[i, "date_basis"] = max(b0, b1), "birth"
    for c in ("year_start", "year_end", "focus_size", "stated_by"):
        edges[c] = edges[c].astype("Int64")
    edges.to_csv(NETWORK_EDGES_CSV, index=False)

    nodes = pd.read_csv(NETWORK_NODES_CSV)
    deg = pd.concat([edges.person_a, edges.person_b]).value_counts()
    nodes["degree"] = nodes["person_id"].map(deg).fillna(0).astype(int)
    nodes.to_csv(NETWORK_NODES_CSV, index=False)

    print(f"\nAdded {len(new):,} edges → {NETWORK_EDGES_CSV}")
    print(edges["edge_type"].value_counts().to_string())
    print("\ndate_basis (stated ties):")
    stated = edges["edge_type"].isin(["family", "mentorship", "personal", "family_surname"])
    print(edges.loc[stated, "date_basis"].fillna("undated").value_counts().to_string())
    print("\nconfirmed_by:")
    print(edges["confirmed_by"].value_counts().to_string())


if __name__ == "__main__":
    main()
