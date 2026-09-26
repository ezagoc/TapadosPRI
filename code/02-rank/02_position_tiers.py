"""
02_position_tiers.py

Rank every dated position record (govt, public/elected, party, labor, military) on
three EXTERNAL, published scales, plus a combined ordinal rank — the basis for
measuring promotions and demotions over careers.

  smith_tier       Peter H. Smith, Labyrinths of Power (1979), Appendix A, Table A-3,
                   HIGHEST OFFICE scale (0–8), applied exactly:
                     8 president and cabinet (secretaries, heads of autonomous
                       departments, governor/regent of the Federal District, attorney
                       general, ambassador to the United States)
                     7 president of the official party; heads of the big
                       decentralized agencies and state companies: CFE, Ferrocarriles
                       Nacionales, IMSS, ISSSTE, PEMEX, Altos Hornos de México, Banco
                       de México, Banco Nacional de Crédito Ejidal, Banobras, Nafinsa
                     6 governors of major states (Table A-2: the 10 largest state
                       budgets in 1910, 1930 or 1960, whichever year is closest to the
                       inauguration)
                     5 National Executive Committee (CEN) of the official party
                     4 subcabinet (subsecretaries, oficiales mayores, chief of the
                       presidential staff, head of Fábricas Militares)
                     3 senators   2 governors of other states/territories
                     1 federal deputies   0 ambassadors in major posts
                   Positions outside Smith's list are NaN.
  smith_tier_ext   the same scale with Smith's two budget rules made time-varying
                   with this project's data (his own method, extended past 1971):
                   "major state" = top-10 states by federal public investment in the
                   six years before the inauguration (state_investment_panel.csv,
                   1959+); before 1965 Smith's lists are kept. Big parastatals: Smith's
                   ten (agency panel extension pending — see TODO below).
  brandenburg_rung Frank Brandenburg, The Making of Modern Mexico (1964), pp. 158–159,
                   reproduced in Smith's Table A-1: 12 rungs, 1 = top. Covers state,
                   municipal and party offices below Smith's elite. Rungs are also
                   assigned to the federal middle ranks that Brandenburg does not
                   list, following the official command ladder (see mando_level):
                   director general 7, director general adjunto 8, director de área 9,
                   subdirector / jefe de departamento 10.
  mando_level      official federal command ladder (Manual de Sueldos y Prestaciones
                   de Mando, DOF 28-Jan-2000; grades G–O of the later Manual de
                   Percepciones): 9 Secretario (G), 8 Subsecretario / Oficial Mayor
                   (H/I, old code 36), 7 Jefe de Unidad / Coordinador General (J, 35),
                   6 Director General (K, 33E), 5 Director General Adjunto (L, 33A),
                   4 Director de Área (M, 30E), 3 Subdirector (N, 29), 2 Jefe de
                   Departamento (O, 28). Executive-branch posts only.
  hybrid_rank      (13 − brandenburg_rung) + smith_tier_ext/10 + mando_level/100:
                   Brandenburg orders everything; within a rung Smith and then the
                   command ladder break ties. Higher = more senior.

Classification is done on the ROLE TEXT (the `is_federal` flag is unreliable: e.g.
"secretary of programming and budget, Puebla" is a state post), with ordered regex
rules; each record keeps the `rule` that ranked it, for audit.

Validation (printed): distribution by rule; people's highest Smith tier vs Smith's
Table A-3 shares; the ladder vs the 1999 official monthly pay ranges (exposición de
motivos PEF 2000, Table VI.4). Salary checkpoints from the 1927/1940 budget books
are to be added as they are transcribed.

Output: RANK_DIR/position_tiers.csv
TODO: time-varying big parastatals from the agency investment panel (08/09 in
05-investment) once it covers the full period.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

CODE_DIR = Path(__file__).resolve().parents[1]
if str(CODE_DIR) not in sys.path:
    sys.path.append(str(CODE_DIR))

from config import (CLEAN_POSITIONS_DIR, INVESTMENT_DIR, MEXICAN_STATES, RANK_DIR,
                    strip_accents)

OUT = RANK_DIR / "position_tiers.csv"

# ── Smith Table A-2: states with the largest budgets ─────────────────────────
SMITH_BIG_STATES = {
    1910: {"Jalisco", "Yucatan", "Puebla", "Michoacan", "Oaxaca", "Mexico", "Veracruz",
           "Durango", "Guanajuato", "Chihuahua", "Hidalgo"},
    1930: {"Veracruz", "Baja California", "Jalisco", "Yucatan", "Puebla", "Sonora",
           "Mexico", "Hidalgo", "Tamaulipas", "Chihuahua"},
    1960: {"Chihuahua", "Sonora", "Veracruz", "Mexico", "Baja California", "Jalisco",
           "Yucatan", "Nuevo Leon", "Puebla"},
}
# Smith's "major" diplomatic posts (Table A-3, note c)
MAJOR_EMBASSIES = r"argentina|brazil|chile|china|france|germany|great britain|england|" \
                  r"united kingdom|guatemala|italy|japan|league of nations|russia|soviet|" \
                  r"spain|united nations|\bun\b"
# Smith's big decentralized agencies / state companies
BIG_PARASTATALS = (r"federal electric(ity)? commission|comision federal de electricidad|\bcfe\b|"
                   r"national railroads|ferrocarriles nacionales|\bimss\b|mexican (institute of )?"
                   r"social security|\bissste\b|\bpemex\b|petroleos mexicanos|mexican petroleum|"
                   r"altos hornos|bank of mexico|banco de mexico|ejido credit|ejidal|banobras|"
                   r"urban mortgage|nacional financiera|\bnafin")
# large cities (Brandenburg rung 8: municipal presidents of large cities)
BIG_CITIES = r"guadalajara|monterrey|puebla|merida|leon|ciudad juarez|juarez|tijuana|" \
             r"san luis potosi|chihuahua|toluca|aguascalientes|torreon|mexicali|acapulco|" \
             r"morelia|hermosillo|veracruz|culiacan|saltillo|queretaro|tampico|durango|oaxaca"

_STATE_WORDS = sorted({strip_accents(v.lower()) for c, (vs, _, _) in MEXICAN_STATES.items()
                       for v in vs + [c]} - {"mexico"}, key=len, reverse=True)
STATE_RE = re.compile(r"\b(state of|government of|under governor|estado de|state )|"
                      r"\b(" + "|".join(map(re.escape, _STATE_WORDS)) + r")\b")

MINISTRY = (r"(interior|government|foreign relations|treasury|finance|hacienda|"
            r"national defense|war and navy|war|navy|agriculture|communications|public works|"
            r"public education|education|health|labor|industry|commerce|economy|"
            r"national (patrimony|properties)|government properties|hydraulic resources|"
            r"agrarian reform|tourism|programming and budget|budget|energy|urban development|"
            r"human settlements|ecology|social development|fishing|fisheries|comptroller|"
            r"presidency|environment|public security|public administration|"
            r"parastatal|national (economy|assets)|welfare|transport)")


def norm(s) -> str:
    return re.sub(r"\s+", " ", strip_accents(str(s).lower())).strip() if isinstance(s, str) else ""


def is_state_level(t: str) -> bool:
    """A state/municipal post: names a state (not 'of Mexico') after the title."""
    t2 = re.sub(r"(bank|attorney general|republic|president|united states|mexican)[^,]* of mexico",
                "", t)
    return bool(STATE_RE.search(t2)) and "federal district" not in t2


# ── ordered rules per dataset: (name, regex on role text, output) ────────────
# output = (brandenburg_rung, smith_tier or None, mando_level or None); the special
# values 'GOV' (governor) and 'AMB' (ambassador) are resolved afterwards.
def govt_rule(t: str, rank: str):
    state = is_state_level(t)
    if re.match(r"(president of (mexico|the republic))", t):
        return "president", (2, 8, 10)
    if re.match(r"(ambassador|envoy)", t) or rank == "ambassador":
        return "ambassador", "AMB"
    if re.match(r"(governor|regent|head)[^,]*(of )?the federal district|"
                r"(head|chief)[, ]+(of )?(the )?department of the federal district", t):
        return "df_regent", (4, 8, 9)
    if re.match(r"attorney general of (mexico|the republic)|attorney general, (office of the )?"
                r"attorney general of mexico|attorney general of the nation", t):
        return "attorney_general_federal", (4, 8, 9)
    if re.match(r"(aide|auxiliary|private secretary|personal secretary|adviser|advisor|"
                r"assistant to|secretary to|technical secretary to)\b", t):
        return "staff", (11, None, None)
    if (re.match(r"(secretary|secretaria) of (the )?" + MINISTRY + r"\b", t) or
            re.match(r"secretary, secretariat of (the )?" + MINISTRY + r"\b", t)) and not state \
            and not re.search(r"secretary of (studies|agreements|accords)", t):
        return "cabinet_secretary", (4, 8, 9)
    if re.match(r"(assistant|deputy) attorney general of (mexico|the republic)|subprocurador", t):
        return "subcabinet_equivalent", (6, None, 8)
    if re.match(r"(head|chief|director)[, ]+(of )?(the )?(autonomous )?department of "
                r"(agrarian|health|tourism|labor|indigenous|forestry|fishing|press|physical|"
                r"military industry|national economy|public health|statistics)", t) and not state:
        return "autonomous_dept_head", (4, 8, 9)
    if re.match(r"private secretary (of|to) the president", t):
        return "president_private_secretary", (4, None, 7)
    if re.match(r"chief of (the )?(presidential )?staff|chief of staff of the president|"
                r"head of (the )?presidential (general )?staff|head of military factories", t):
        return "presidential_chief_of_staff", (4, 4, 8)
    if re.match(r"(assistant secretary|subsecretary|undersecretary|oficial mayor)", t) or \
            rank in ("assistant_secretary", "oficial_mayor"):
        return ("state_subcabinet", (10, None, None)) if state else ("subcabinet", (6, 4, 8))
    if re.match(r"(director general|general director|general manager|director|manager|"
                r"administrator|president)(,| of)? (the )?(" + BIG_PARASTATALS + r")", t):
        return "big_parastatal_head", (4, 7, 7)
    if re.search(r"(district|circuit)[^,]*(court )?judge|judge[^,]*(district|circuit)", t) and not state:
        return "federal_judge", (9, None, None)
    if re.search(r"superior tribunal|state supreme court|tribunal superior", t) or \
            (re.search(r"\b(judge|magistrate)\b", t) and state):
        return "state_judge", (10, None, None)
    if re.match(r"(agent|investigative agent)[^,]*ministerio publico|ministerio publico", t):
        return "staff", (11, None, None)
    if re.search(r"\bdelegate (to|in|of)\b|delegate, ", t) and "party" not in t and "pri" not in t:
        return "federal_official_in_states", (10, None, None)
    if re.search(r"city council|ayuntamiento|regidor", t):
        return "city_council", (12, None, None)
    if rank in ("justice",) or re.match(r"justice of the supreme court|supreme court justice", t):
        return ("state_supreme_court", (10, None, None)) if state else ("supreme_court_justice", (6, None, None))
    if rank in ("judge", "district_judge", "circuit_judge", "magistrate"):
        return ("state_judge", (10, None, None)) if state else ("federal_judge", (9, None, None))
    if rank == "attorney_general":
        return ("state_attorney_general", (9, None, None)) if state else ("attorney_general_other", (7, None, 6))
    if rank in ("secretary", "secretary_general", "treasurer", "comptroller") and state:
        return "state_cabinet", (9, None, None)
    if rank in ("comptroller",) or re.match(r"(controller|comptroller) general", t):
        return "director_general", (7, None, 6)
    if rank == "secretary_general":
        return "federal_secretary_general", (8, None, 5)
    if rank in ("coordinator_general",) or re.match(r"(head|chief) of (the )?unit", t):
        return ("state_director", (10, None, None)) if state else ("jefe_de_unidad", (7, None, 7))
    if rank in ("director_general", "general_manager") or re.match(r"director general", t):
        return ("state_director_general", (10, None, None)) if state else ("director_general", (7, None, 6))
    if rank == "assistant_director_general":
        return ("state_director", (10, None, None)) if state else ("director_general_adjunto", (8, None, 5))
    if rank in ("director", "manager", "administrator"):
        return ("state_director", (10, None, None)) if state else ("director_de_area", (9, None, 4))
    if rank in ("assistant_director", "assistant_manager"):
        return ("state_subdirector", (11, None, None)) if state else ("subdirector", (10, None, 3))
    if rank == "head":
        return ("state_department_head", (11, None, None)) if state else ("jefe_de_departamento", (10, None, 2))
    if rank in ("consul_general",):
        return "consul_general", (7, None, None)
    if rank in ("consul", "delegate"):
        return "federal_official_in_states", (10, None, None)
    if rank in ("secretary",):
        return ("state_cabinet", (9, None, None)) if state else ("secretary_other", (10, None, None))
    if rank in ("adviser", "assistant", "analyst", "technical_secretary", "coordinator",
                "inspector", "inspector_general", "member"):
        return "staff", (11, None, None)
    if rank in ("governor", "acting_governor"):
        return "governor", "GOV"
    return "unranked", None


def public_rule(t: str, title: str):
    if re.match(r"president of (mexico|the republic)", t):
        return "president", (2, 8, 10)
    if title in ("Governor",) or re.match(r"(interim |provisional |substitute )?governor", t):
        if "federal district" in t:
            return "df_regent", (4, 8, 9)
        return "governor", "GOV"
    if title == "Senator":
        return "senator", (6, 3, None)
    if title in ("Federal Deputy", "Deputy") and "local" not in t:
        return "federal_deputy", (9, 1, None)
    if title in ("President", "Vice President") and re.search(r"chamber|senate|congress", t):
        return "chamber_leader", (5, None, None)
    if title == "Local Deputy" or "local deputy" in t:
        return "local_deputy", (10, None, None)
    if title in ("Mayor",) or re.match(r"(municipal president|mayor)", t):
        return ("mayor_big_city", (8, None, None)) if re.search(BIG_CITIES, t) else ("mayor", (11, None, None))
    if title in ("Representative", "Delegate"):
        return "df_assembly_or_delegate", (10, None, None)
    if title in ("Member", "Alternate Mayor") and re.search(r"city council|ayuntamiento|regidor", t):
        return "city_council", (12, None, None)
    return "unranked", None


PRI = {"PRI", "PRM", "PNR"}


def party_rule(t: str, party: str, rank: str, level: str):
    official = party in PRI or not party
    if re.match(r"(aide|auxiliary|private secretary|personal secretary|adviser|advisor|"
                r"assistant to|secretary to)\b", t):
        return "party_staff", (11, None, None)
    if "iepes" in t or "cepes" in t:
        if "iepes" in t and re.match(r"(director|president|secretary)(,| of| general)", t) \
                and not re.match(r"(assistant|sub)", t):
            return "party_national_organ", (8, None, None)
        return "party_state_officer", (10, None, None)
    if rank in ("national_president", "cen_president") and official:
        return "pri_national_president", (5, 7, None)
    if rank in ("national_president", "cen_president"):
        return "opposition_party_leader", (6, None, None)
    if rank == "secretary_general_nat" and official:
        return "pri_secretary_general", (6, 5, None)
    if rank in ("cen_secretary", "cen_member") and official:
        return "pri_cen", (6, 5, None)
    if rank in ("cen_secretary", "cen_member", "secretary_general_nat"):
        return "opposition_national_leadership", (9, None, None)
    if rank == "state_president":
        return "party_state_president", (9, None, None)
    if rank in ("state_secretary_general", "state_secretary", "iepes_director", "national_delegate"):
        return "party_state_officer", (10, None, None)
    if rank in ("adviser_member", "campaign_leader"):
        return "party_other", (11, None, None)
    if level == "local":
        return "party_local", (12, None, None)
    return "unranked", None


BIG_UNIONS = r"\bctm\b|\bcnc\b|\bfstse\b|\bcrom\b|\bcnop\b|confederation of mexican workers|" \
             r"national peasant|congress of labor|congreso del trabajo"


def labor_rule(t: str, rank: str, national):
    top = rank in ("secretary_general", "president")
    if top and national is True and re.search(BIG_UNIONS, t):
        return "national_confederation_leader", (6, None, None)
    if top and national is True:
        return "national_union_leader", (7, None, None)
    if top:
        return "state_labor_leader", (9, None, None)
    if rank in ("secretary", "director", "delegate", "representative", "member", "adviser"):
        return "union_officer", (11, None, None)
    return "unranked", None


def military_rule(t: str):
    if re.search(r"command(er|ing)[^,]*military zone|zone commander|military zone commander", t):
        return "military_zone_commander", (5, None, None)
    return "unranked", None


# ── resolve governors and ambassadors ─────────────────────────────────────────
def governor_state(row) -> str | None:
    for col in ("work_state", "state"):
        v = row.get(col)
        if isinstance(v, str) and v and v != "Federal District":
            return v
    return None


def smith_big_state(state: str, year: int) -> bool:
    ref = min(SMITH_BIG_STATES, key=lambda r: abs(r - year))
    return state in SMITH_BIG_STATES[ref]


def investment_big_states() -> dict:
    """year → set of top-10 states by federal investment in the 6 prior years."""
    p = INVESTMENT_DIR / "state_investment_panel.csv"
    if not p.exists():
        return {}
    inv = pd.read_csv(p)
    out = {}
    for y in range(1965, 2011):
        w = inv[inv.year.between(y - 6, y - 1)]
        if w.year.nunique() < 3:
            continue
        top = w.groupby("state").share_of_states.mean().nlargest(10).index
        out[y] = set(top) - {"Federal District"}
    return out


def main():
    frames = []
    for name in ("govt_positions", "public_positions", "party_positions",
                 "labor_positions", "military_positions"):
        d = pd.read_csv(CLEAN_POSITIONS_DIR / f"{name}.csv")
        d["dataset"] = name
        frames.append(d)
    pos = pd.concat(frames, ignore_index=True)
    pos["t"] = pos.role_text.fillna(pos.role_text_raw).map(norm)
    inv_big = investment_big_states()

    rows = []
    for r in pos.to_dict("records"):
        t, ds = r["t"], r["dataset"]
        if ds == "govt_positions":
            rule, out = govt_rule(t, str(r.get("rank")))
        elif ds == "public_positions":
            rule, out = public_rule(t, str(r.get("position_title")))
        elif ds == "party_positions":
            rule, out = party_rule(t, str(r.get("party") or ""), str(r.get("party_rank")),
                                   str(r.get("party_level")))
        elif ds == "labor_positions":
            rule, out = labor_rule(t, str(r.get("rank")), r.get("is_national"))
        else:
            rule, out = military_rule(t)
        rung = smith = smith_ext = mando = None
        y = r.get("year_start")
        if out == "GOV":
            st = governor_state(r)
            if st and pd.notna(y):
                big = smith_big_state(st, int(y))
                big_ext = (st in inv_big[int(y)]) if int(y) in inv_big else big
                rung, smith, smith_ext = (5 if big else 7), (6 if big else 2), (6 if big_ext else 2)
                rule = "governor_major_state" if big else "governor_other_state"
            else:
                rung, smith, smith_ext, rule = 7, 2, 2, "governor_state_unknown"
        elif out == "AMB":
            if "united states" in t or "washington" in t:
                rung, smith, mando, rule = 4, 8, 9, "ambassador_united_states"
            elif re.search(MAJOR_EMBASSIES, t):
                rung, smith, rule = 5, 0, "ambassador_major_post"
            else:
                rung, rule = 7, "ambassador_other"
        elif out:
            rung, smith, mando = out
        if smith_ext is None:
            smith_ext = smith
        rows.append({"record_id": r.get("record_id"), "person_id": r["person_id"],
                     "person_name": r.get("person_name"), "dataset": ds,
                     "year_start": y, "year_end": r.get("year_end"),
                     "role_text": r.get("role_text"), "rule": rule,
                     "smith_tier": smith, "smith_tier_ext": smith_ext,
                     "brandenburg_rung": rung, "mando_level": mando})
    out = pd.DataFrame(rows)
    for c in ("smith_tier", "smith_tier_ext", "brandenburg_rung", "mando_level"):
        out[c] = out[c].astype("Int64")
    # Smith's tier 0 (major embassies) is ambiguous (promotion or exile): it is kept in
    # smith_tier but does not raise hybrid_rank above Brandenburg's ordering
    sm = out.smith_tier_ext.astype("Float64").fillna(0).clip(lower=0)
    out["hybrid_rank"] = ((13 - out.brandenburg_rung.astype("Float64")) + sm / 10 +
                          out.mando_level.astype("Float64").fillna(0) / 100).round(3)
    RANK_DIR.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)
    validate(out)
    print(f"\n→ {OUT}")


def validate(out: pd.DataFrame):
    n = len(out)
    ranked = out.brandenburg_rung.notna()
    print(f"{n:,} position records; ranked by Brandenburg/hybrid: {ranked.mean():.1%}; "
          f"on Smith's scale: {out.smith_tier.notna().mean():.1%}")
    print("\nRecords by rule (top 30):")
    print(out.rule.value_counts().head(30).to_string())
    # people's highest Smith tier vs Smith Table A-3 shares (his elite, 1900–1971)
    smith_share = {8: 7.5, 7: 1.0, 6: 4.9, 5: 1.5, 4: 5.0, 3: 9.7, 2: 6.8, 1: 62.8, 0: 0.8}
    hi = out.dropna(subset=["smith_tier"]).groupby("person_id").smith_tier.max()
    comp = pd.DataFrame({"this_dataset_%": (hi.value_counts(normalize=True) * 100).round(1),
                         "smith_1900_1971_%": pd.Series(smith_share)}).sort_index(ascending=False)
    print("\nHighest Smith tier per person (Camp's elite is more senior by design):")
    print(comp.to_string())
    # the command ladder vs the 1999 official monthly pay ranges (PEF 2000, Table VI.4)
    pay_1999 = {"jefe_de_departamento": (10013, 15218), "subdirector": (13435, 23285),
                "director_de_area": (24676, 41473), "director_general_adjunto": (39163, 63036),
                "director_general": (51193, 72061), "jefe_de_unidad": (66509, 76564),
                "subcabinet": (80085, 83768), "cabinet_secretary": (88278, 88278)}
    lad = out[out.rule.isin(pay_1999)].groupby("rule").hybrid_rank.median()
    mid = pd.Series({k: np.mean(v) for k, v in pay_1999.items()})
    chk = pd.DataFrame({"hybrid_rank": lad, "pay_1999_mid": mid}).sort_values("pay_1999_mid")
    print("\nCommand ladder vs 1999 official pay (must be monotone):")
    print(chk.to_string())
    print("monotone:", bool(chk.hybrid_rank.is_monotonic_increasing))


if __name__ == "__main__":
    main()
