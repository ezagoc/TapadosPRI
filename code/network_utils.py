"""
Shared helpers for the full political network (00-networks/00-preprocess/06–07)
and its consumers (03-descriptive_stats, 04-analysis).

- StrictNameMatcher: free-text name -> person_id, requiring the paternal surname
  and a given name to match (used for corcholatas and for names mentioned in
  biographies).
- load_network / ego_view: read the full undirected edge list and orient it
  around a set of egos (e.g. the tapados).
- load_corcholatas: the per-election candidate crosswalk (winner flag per election).
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

import pandas as pd

from config import (
    CORCHOLATAS_MATCHED_CSV,
    NETWORK_EDGES_CSV,
    NETWORK_NODES_CSV,
    strip_accents,
)

_CONNECTORS = {"de", "la", "del", "los", "las", "y", "e", "jr", "sr"}


def name_tokens(s) -> list[str]:
    s = strip_accents(str(s).lower()).replace("-", " ")
    return [t for t in re.sub(r"[^a-z ]+", " ", s).split() if t not in _CONNECTORS]


class StrictNameMatcher:
    """Match a free-text name in Spanish order ('Given Paternal Maternal') to a person_id.

    For a person 'Paternal Maternal, Given names' to match, the query must contain
    the PATERNAL surname at some position i such that
      - every token before i (ignoring initials) is one of the person's given
        names, and there is at least one;
      - the token right after i, if any, matches the person's second surname
        (edit-similarity ≥ 0.8, tolerating spellings like Manatou/Manautou).
    E.g. 'David Rubalcaba Jiménez' does NOT match 'Jimenez Gonzalez, David'.
    Candidates are ranked by (most shared tokens, fewest person tokens absent from
    the query); a remaining tie is ambiguous and returns None. Optional `year` +
    age bounds drop people implausibly young/old at that date.
    """

    def __init__(self, pid_name: dict, byear: dict | None = None):
        self.byear = byear or {}
        self.keys = {}
        self.by_paternal: dict[str, list] = {}
        for pid, name in pid_name.items():
            sur, _, giv = str(name).partition(",")
            sur_t, giv_t = name_tokens(sur), name_tokens(giv)
            if not sur_t or not giv_t:
                continue
            self.keys[pid] = (sur_t, set(giv_t), set(sur_t) | set(giv_t))
            self.by_paternal.setdefault(sur_t[0], []).append(pid)

    @staticmethod
    def _fits(q: list[str], sur_t: list[str], giv: set) -> bool:
        for i, tok in enumerate(q):
            if tok != sur_t[0]:
                continue
            before = [t for t in q[:i] if len(t) > 1]
            if not before or not set(before) <= giv:
                continue
            after = [t for t in q[i + 1:] if len(t) > 1]
            if after and len(sur_t) > 1 and \
                    SequenceMatcher(None, after[0], sur_t[1]).ratio() < 0.8:
                continue
            return True
        return False

    def match(self, query: str, year: int | None = None,
              min_age: int = 0, max_age: int = 200) -> tuple[int | None, str]:
        q = name_tokens(query)
        qs = set(q)
        hits = []
        for tok in qs:
            for pid in self.by_paternal.get(tok, ()):
                sur_t, giv, toks = self.keys[pid]
                if not self._fits(q, sur_t, giv):
                    continue
                by = self.byear.get(pid)
                if year is not None and by and not (min_age <= year - by <= max_age):
                    continue
                hits.append((len(qs & toks), -len(toks - qs), pid))
        if not hits:
            return None, "no_match"
        hits = sorted(set(hits), reverse=True)
        if len(hits) > 1 and hits[0][:2] == hits[1][:2]:
            return None, "ambiguous"
        return hits[0][2], "auto"


def load_network() -> tuple[pd.DataFrame, pd.DataFrame]:
    return pd.read_csv(NETWORK_EDGES_CSV), pd.read_csv(NETWORK_NODES_CSV)


# Main specification: NO size cutoff — co-location ties are weighted by the
# data-calibrated `tie_weight` = (n − 1)^b (00-preprocess/08_tie_weights.py). The
# robustness curve re-runs results unweighted, with `weight_newman` = 1/(n − 1),
# and with these caps on people at the focus at the same time:
ROBUSTNESS_CAPS = (10, 20, 30, 60)


def ego_view(edges: pd.DataFrame, ego_ids, as_of: int | None = None,
             max_focus_size: int | None = None,
             undated: str = "keep") -> pd.DataFrame:
    """Orient the undirected edge list around `ego_ids`.

    Returns one row per (ego, alter, edge) with columns ego_id, ego_name, alter_id,
    alter_name, ego_role, alter_role plus the edge attributes.
      as_of          keep only ties formed by that year (year_start <= as_of).
      max_focus_size drop co-location ties at foci with more people at the same
                     time (None = keep all, the main spec; see ROBUSTNESS_CAPS);
                     stated ties have no size and are always kept.
      undated        stated ties with no known start year: "keep" or "drop".
    """
    ego_ids = set(ego_ids)
    parts = []
    for side, other in (("a", "b"), ("b", "a")):
        sub = edges[edges[f"person_{side}"].isin(ego_ids)]
        parts.append(sub.rename(columns={
            f"person_{side}": "ego_id", f"name_{side}": "ego_name", f"role_{side}": "ego_role",
            f"person_{other}": "alter_id", f"name_{other}": "alter_name", f"role_{other}": "alter_role",
        }))
    out = pd.concat(parts, ignore_index=True)
    if max_focus_size is not None:
        out = out[out["focus_size"].isna() | (out["focus_size"] <= max_focus_size)]
    if undated == "drop":
        out = out[out["year_start"].notna()]
    if as_of is not None:
        out = out[out["year_start"].isna() | (out["year_start"] <= as_of)]
    return out


def load_corcholatas(matched_only: bool = True) -> pd.DataFrame:
    """One row per (election_year, pre-candidate) with its per-election is_winner."""
    c = pd.read_csv(CORCHOLATAS_MATCHED_CSV)
    if matched_only:
        c = c.dropna(subset=["person_id"])
        c["person_id"] = c["person_id"].astype(int)
    return c
