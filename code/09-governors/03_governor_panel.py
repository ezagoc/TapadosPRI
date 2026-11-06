"""One row per constitutional PRI governor (tenure begun 1934-1994): next post, votes delivered, tie to the president,
roots in the state (SPEC.md).

Inputs: governors_roster.csv (02_*), rank/position_tiers.csv (annual ladder, as in the main design),
clean_positions/* (location of earlier posts), networks/network_edges.csv (ties), output/maps/opposition_vote_by_state.csv
(presidential vote by state, 03-descriptive_stats/map_opposition_vote.py).
Output: DATA_DIR/governors/governor_panel.csv
Run: python code/09-governors/03_governor_panel.py
"""
import re
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import DATA_DIR, OUTPUT_DIR  # noqa: E402

# President in office in year y: elected in e, in office e+1..e+6.
PRESIDENTS = {1934: 441, 1940: 209, 1946: 101, 1952: 2373, 1958: 1540, 1964: 767, 1970: 802, 1976: 1549, 1982: 714,
              1988: 2426, 1994: 2867}
FEDERAL_LEGISLATOR = r"^(?:alternate |plurinominal |substitute )?(?:federal deputy|senator)"
STATE_LEVEL = r"local deputy|state deputy|mayor|municipal president|city council|presidente municipal|state legislature"


def plain(s):
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()


def president_in(year):
    e = 1934 + 6 * ((year - 1935) // 6)
    return PRESIDENTS.get(e)


R = pd.read_csv(DATA_DIR / "governors" / "governors_roster.csv")
pri = ~R.party.fillna("").str.contains(r"Acci[oó]n Nacional|Democr[aá]tica|PAN\b|PRD\b|del Trabajo|Verde", regex=True)
G = R[(R.kind == "constitutional") & R.start_year.between(1934, 1994) & pri & (R.state != "Federal District")].copy()
G["end_year"] = G.end_year.fillna(G.start_year + 6).astype(int)
G["linked"] = G.person_id.notna()

# Annual ladder (same rule as estimate_main.R).
pt = pd.read_csv(DATA_DIR / "rank" / "position_tiers.csv", low_memory=False).dropna(subset=["hybrid_rank", "year_start"])
pt["y0"] = pt.year_start.astype(int)
pt["y1"] = np.maximum(pt.year_end.fillna(pt.year_start), pt.year_start).astype(int)
pt["rung"] = np.floor(pt.hybrid_rank.astype(float) + 1e-9).astype(int)
pt = pt[(pt.y1 - pt.y0 <= 12) & pt.rung.between(1, 11)]
annual = pt.loc[pt.index.repeat(pt.y1 - pt.y0 + 1)].assign(year=lambda d: d.y0 + d.groupby(level=0).cumcount())
annual = annual.groupby(["person_id", "year"]).rung.max()
ann = annual.reset_index()


def best(pid, a, b):
    if pd.isna(pid):
        return np.nan
    x = ann[(ann.person_id == pid) & ann.year.between(a, b)].rung
    return int(x.max()) if len(x) else 0


G["rung_before"] = [best(p, s - 6, s - 1) for p, s in zip(G.person_id, G.start_year)]
G["rung_after"] = [best(p, e + 1, e + 6) for p, e in zip(G.person_id, G.end_year)]
G["top_post"] = (G.rung_after >= 8).astype(float).where(G.linked)
G["post7"] = (G.rung_after >= 7).astype(float).where(G.linked)
G["no_post"] = (G.rung_after == 0).astype(float).where(G.linked)
G["left_for_top_post"] = [float(best(p, e, e + 1) >= 8) if (x == 1 and pd.notna(p)) else np.nan
                          for p, e, x in zip(G.person_id, G.end_year, G.early_exit)]

# Roots: posts located in the governed state in the ten years before (governorships excluded).
pos = pd.concat([pd.read_csv(DATA_DIR / "clean_positions" / f"{f}.csv", low_memory=False).assign(src=f)
                 for f in ("govt_positions", "public_positions", "party_positions", "labor_positions")], ignore_index=True)
pos["st"] = pos.state.fillna(pos.get("work_state"))
pos["y1"] = pos.year_end.fillna(pos.year_start)
pos["low"] = pos.role_text.fillna("").str.lower()
pos_all = pd.concat([pos, pd.read_csv(DATA_DIR / "clean_positions" / "military_positions.csv", low_memory=False)
                     .assign(y1=lambda d: d.year_end.fillna(d.year_start))], ignore_index=True)
pos_all = pos_all[pos_all.year_start.notna()]
pos = pos[pos.year_start.notna() & pos.st.notna() & ~pos.low.str.contains(r"governor", regex=True)]


def roots(pid, st, s):
    if pd.isna(pid):
        return np.nan
    anywhere = pos_all[(pos_all.person_id == pid) & (pos_all.year_start <= s - 1) & (pos_all.y1 >= s - 10)]
    if anywhere.empty:
        return "no record"                       # no dated post at all in the ten years: unknown, not parachuted
    x = pos[(pos.person_id == pid) & (pos.st == st) & (pos.year_start <= s - 1) & (pos.y1 >= s - 10)]
    if x.empty:
        return "parachuted"
    fed = x.low.str.contains(FEDERAL_LEGISLATOR, regex=True) & (x.src == "public_positions")
    return "federal legislator only" if fed.all() else "rooted"


G["roots"] = [roots(p, st, s) for p, st, s in zip(G.person_id, G.state, G.start_year)]
nodes = pd.read_csv(DATA_DIR / "networks" / "network_nodes.csv")
G["born_in_state"] = G.person_id.map(dict(zip(nodes.person_id, nodes.birth_state))).eq(G.state).astype(float).where(G.linked)
G["age_end"] = G.end_year - G.person_id.map(dict(zip(nodes.person_id, nodes.birth_year)))

# Ties to the president who appoints the next post (in office the year after the tenure) and to the one at the start.
e = pd.read_csv(DATA_DIR / "networks" / "network_edges.csv", low_memory=False)
lt = pd.concat([e[["person_a", "person_b", "year_start"]].rename(columns={"person_a": "a", "person_b": "b"}),
                e[["person_b", "person_a", "year_start"]].rename(columns={"person_b": "a", "person_a": "b"})])


def tied(pid, pres, by):
    if pd.isna(pid) or pres is None:
        return np.nan
    x = lt[(lt.a == pid) & (lt.b == pres)]
    return float(((x.year_start.isna()) | (x.year_start <= by)).any())


G["president_next"] = [president_in(y + 1) for y in G.end_year]
G["president_start"] = [president_in(y) for y in G.start_year]
G["tie_president_next"] = [tied(p, pr, y) for p, pr, y in zip(G.person_id, G.president_next, G.end_year)]
G["tie_president_start"] = [tied(p, pr, y) for p, pr, y in zip(G.person_id, G.president_start, G.start_year)]
G["appointer_is_next"] = (G.president_next == G.president_start).astype(int)

# Votes delivered: the presidential election held during the tenure (last one if two).
v = pd.read_csv(OUTPUT_DIR / "maps" / "opposition_vote_by_state.csv")
v["state"] = v.state.replace({"Distrito Federal": "Federal District"})
v["pri"] = v.regime / v.total
nat = v.groupby("year").apply(lambda d: d.regime.sum() / d.total.sum(), include_groups=False)
share = v.set_index(["state", "year"]).pri


def delivered(st, s, e_):
    ys = [y for y in nat.index if s <= y <= e_]
    if not ys:
        return pd.Series({"election": np.nan, "votes_delivered": np.nan, "votes_level": np.nan})
    y = max(ys)
    if y == 1976 or (st, y) not in share.index or (st, y - 6) not in share.index:
        return pd.Series({"election": y, "votes_delivered": np.nan,
                          "votes_level": np.nan if y == 1976 or (st, y) not in share.index else share[(st, y)] - nat[y]})
    return pd.Series({"election": y, "votes_delivered": (share[(st, y)] - share[(st, y - 6)]) - (nat[y] - nat[y - 6]),
                      "votes_level": share[(st, y)] - nat[y]})


G = pd.concat([G.reset_index(drop=True),
               G.apply(lambda r: delivered(r.state, r.start_year, r.end_year), axis=1).reset_index(drop=True)], axis=1)
G["term_end"] = [1934 + 6 * ((y - 1935) // 6) for y in G.end_year]
cols = ["state", "name_wiki", "person_id", "linked", "start_year", "end_year", "early_exit", "exit_reason", "term_end",
        "rung_before", "rung_after", "top_post", "post7", "no_post", "left_for_top_post", "roots", "born_in_state",
        "age_end", "president_start", "president_next", "appointer_is_next", "tie_president_start", "tie_president_next",
        "election", "votes_delivered", "votes_level"]
G[cols].to_csv(DATA_DIR / "governors" / "governor_panel.csv", index=False)

L = G[G.linked]
print(f"constitutional PRI governors begun 1934-1994: {len(G)} | linked to Camp: {len(L)} ({len(L) / len(G):.0%})")
print(f"with votes delivered: {L.votes_delivered.notna().sum()} | top post after: {L.top_post.mean():.1%} | "
      f"rung >= 7: {L.post7.mean():.1%} | no post: {L.no_post.mean():.1%}")
print("roots:", L.roots.value_counts().to_dict(), "| born in state:", f"{L.born_in_state.mean():.0%}")
print(f"tied to the next appointing president: {L.tie_president_next.mean():.1%} | to the one at the start: "
      f"{L.tie_president_start.mean():.1%}")
print(L.groupby("term_end").agg(n=("name_wiki", "size"), top=("top_post", "mean"), tie=("tie_president_next", "mean"),
                                parachuted=("roots", lambda s: (s == "parachuted").mean())).round(2).T)
