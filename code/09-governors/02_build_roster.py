"""Governor roster 1930-2000: every person who governed each state, with start and end dates, the kind of tenure
(constitutional, interim, substitute, provisional, acting) and how it ended, linked to Camp's biographies.

Source: the Spanish Wikipedia annex of each state's rulers (01_*; the Federal District's regents included and flagged).
Dates are parsed with their precision (day, month, year; a start without a year takes the end's year). Kind and exit
come from the annex's notes. Names are matched to Camp with the project's strict matcher (Spanish order, maternal
surname checked, age 25-85 at the start). Checks: (i) for every matched governor, a Camp governor record of the same
state overlapping the dates; (ii) from 1970, Magar's elected incumbents (state, year of inauguration, name);
(iii) for the four states with two annexes, agreement between them.
Output: DATA_DIR/governors/governors_roster.csv, governors_roster_checks.csv
Run: python code/09-governors/02_build_roster.py
"""
import io
import re
import sys
import unicodedata
import warnings
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import DATA_DIR, PARSED_POSITIONS_CSV  # noqa: E402
from network_utils import StrictNameMatcher  # noqa: E402

warnings.filterwarnings("ignore")
RAW = DATA_DIR / "governors" / "wikipedia_raw"
OUT = DATA_DIR / "governors"
MONTHS = {m: i + 1 for i, m in enumerate(["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                                          "septiembre", "octubre", "noviembre", "diciembre"])}
STATES = ["Aguascalientes", "Baja California", "Baja California Sur", "Campeche", "Coahuila", "Colima", "Chiapas",
          "Chihuahua", "Federal District", "Durango", "Guanajuato", "Guerrero", "Hidalgo", "Jalisco", "Mexico",
          "Michoacan", "Morelos", "Nayarit", "Nuevo Leon", "Oaxaca", "Puebla", "Queretaro", "Quintana Roo",
          "San Luis Potosi", "Sinaloa", "Sonora", "Tabasco", "Tamaulipas", "Tlaxcala", "Veracruz", "Yucatan", "Zacatecas"]
KIND = [("acting", r"encargad[oa] del despacho|encargad[oa] del poder"), ("provisional", r"provisional"),
        ("substitute", r"sustitut[oa]"), ("interim", r"interin[oa]")]
EXIT = {"leave": r"licencia", "resigned": r"renunci", "removed": r"desaparici[oó]n de poderes|destituid|depuest|derrocad",
        "died": r"falleci|muri[oó]|asesinad", "resumed": r"reasumi"}


def plain(s):
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()


def state_of(fname):
    t = plain(fname.split("__", 1)[1].rsplit(".html", 1)[0].replace("_", " "))
    t = re.sub(r"^Anexo:Gobern(antes|adores) (de |del )", "", t)
    t = {"la Ciudad de Mexico": "Federal District", "Estado de Mexico": "Mexico"}.get(t, t)
    assert t in STATES, t
    return t


def clean(x):
    x = re.sub(r"\[[^\]]*\]", "", str(x)).replace("​", " ")
    return re.sub(r"\s+", " ", x).strip()


def parse_date(s, year_hint=None):
    """'1 de marzo de 1939', 'marzo de 1939', '1939', '1 de octubre' (year from the hint) -> (date, precision)."""
    s = plain(clean(s)).lower()
    y = re.search(r"\b(1[89]\d\d|20\d\d)\b", s)
    m = re.search(r"(" + "|".join(MONTHS) + r")", s)
    d = re.search(r"\b(\d{1,2})\b(?! de (1[89]|20)\d\d)", s)
    year = int(y.group(1)) if y else year_hint
    if year is None:
        return None, None
    if m and d:
        try:
            return pd.Timestamp(year, MONTHS[m.group(1)], int(d.group(1))), "day"
        except ValueError:                           # a day the month does not have ("31 de septiembre")
            return pd.Timestamp(year, MONTHS[m.group(1)], 15), "month"
    if m:
        return pd.Timestamp(year, MONTHS[m.group(1)], 15), "month"
    return pd.Timestamp(year, 7, 1), "year"


def parse_period(text):
    parts = [p for p in re.split(r"\s+[-–]\s*|\s*[-–]\s+|(?<=\d{4})-(?=\D)", clean(text)) if p.strip()]
    if not parts:
        return (None, None, None, None)
    end, end_p = parse_date(parts[-1]) if len(parts) > 1 else (None, None)
    start, start_p = parse_date(parts[0], end.year if end is not None else None)
    return start, start_p, end, end_p


def column(t, rx):
    hit = [c for c in t.columns if re.match(rx, str(c))]
    if not hit:
        return None
    v = t.loc[:, hit[0]]
    return v.iloc[:, 0] if isinstance(v, pd.DataFrame) else v


rows = []
for f in sorted(RAW.glob("es__*.html")):
    state, annex = state_of(f.name), "gobernantes" if "Gobernantes" in f.name else "gobernadores"
    for t in pd.read_html(io.StringIO(f.read_text(encoding="utf-8"))):
        t.columns = [re.sub(r"\s+(?=\.\d$)", "", clean(c)) for c in t.columns]   # "Gobernador[1]\u200b.2" -> "Gobernador.2"
        name = column(t, r"(Gobernador|Regente|Jefe de Gobierno)\.2$")
        period, start_c, end_c = column(t, r"Per[ií]odo"), column(t, r"Inicio"), column(t, r"Fin")
        if name is None or (period is None and start_c is None):
            continue
        party, notes = column(t, r"Partido"), column(t, r"Notas")
        for i in range(len(t)):
            if period is not None:
                s, sp, e, ep = parse_period(period.iloc[i])
            else:
                e, ep = parse_date(end_c.iloc[i]) if end_c is not None else (None, None)
                s, sp = parse_date(start_c.iloc[i], e.year if e is not None else None)
            if s is None or not (1925 <= s.year <= 2001) and not (e is not None and 1930 <= e.year <= 2001):
                continue
            nm = clean(name.iloc[i])
            if nm.lower() in ("nan", "") or nm == clean(t.columns[0]):
                continue
            note = clean(notes.iloc[i]) if notes is not None and str(notes.iloc[i]) != "nan" else ""
            low = plain(note).lower()
            rows.append(dict(state=state, annex=annex, name_wiki=re.sub(r"\s*\(.*?\)\s*", " ", nm).strip(),
                             start=s, start_precision=sp, end=e, end_precision=ep,
                             party=clean(party.iloc[i]) if party is not None else "", notes=note,
                             kind="regent" if state == "Federal District" else
                             next((k for k, rx in KIND if re.search(rx, low)), "constitutional"),
                             **{f"exit_{k}": int(bool(re.search(rx, low))) for k, rx in EXIT.items()}))
R = pd.DataFrame(rows).drop_duplicates(["state", "annex", "name_wiki", "start"])
R["start_year"] = R.start.dt.year
R["end_year"] = R.end.dt.year

# One annex per state ("Gobernantes" when both exist); the other is a check.
two = R.groupby("state").annex.nunique().pipe(lambda s: s[s > 1].index)
alt = R[(R.state.isin(two)) & (R.annex == "gobernadores")]
R = R[~((R.state.isin(two)) & (R.annex == "gobernadores"))].copy()

# Link to Camp.
pp = pd.read_csv(PARSED_POSITIONS_CSV, usecols=["person_id", "person_name", "birth_date_clean"]).dropna(
    subset=["person_id", "person_name"]).drop_duplicates("person_id")
byear = {p: int(str(b)[:4]) for p, b in zip(pp.person_id, pp.birth_date_clean) if str(b)[:4].isdigit()}
matcher = StrictNameMatcher(dict(zip(pp.person_id, pp.person_name)), byear)
res = [matcher.match(plain(n), int(y), 25, 85) for n, y in zip(R.name_wiki, R.start_year)]
R["person_id"] = [p for p, _ in res]
R["match_status"] = [s for _, s in res]

# Check (i): a Camp governor record of the same state overlapping the dates (any written date range).
# Elected governors are public positions; territorial governors (appointed) are government positions.
gov = pd.concat([pd.read_csv(DATA_DIR / "clean_positions" / f"{f}.csv", low_memory=False) for f in
                 ("public_positions", "govt_positions")], ignore_index=True)
gov = gov[gov.role_text.str.contains(r"^(interim |substitute |provisional |acting |constitutional )?governor", case=False, na=False)
          & ~gov.role_text.str.contains("elect", case=False, na=False)]
gov = gov.assign(y1=gov.year_end.fillna(gov.year_start))
# Camp's state labels differ for the territories ("Baja California del Sur", "Distrito Norte"), so a record agrees
# when its dates overlap and its text or state names the roster's state.
def state_words(st):
    return {"Baja California": r"baja california(?! (del )?sur)|distrito norte", "Baja California Sur":
            r"baja california (del )?sur|distrito sur|southern", "Mexico": r"state of mexico|\bmexico\b"}.get(
            st, re.escape(plain(st).lower()))
def camp_agrees(r):
    if pd.isna(r.person_id):
        return None
    g = gov[gov.person_id == r.person_id]
    g = g[g.apply(lambda x: bool(re.search(state_words(r.state), plain(f"{x.role_text} {x.state}").lower())), axis=1)]
    if g.empty:
        return 0
    e = r.end_year if pd.notna(r.end_year) else r.start_year
    return int(((g.year_start <= e + 1) & (g.y1 >= r.start_year - 1)).any())
R["camp_governor_record"] = R.apply(camp_agrees, axis=1)

# Check (ii): Magar's elected incumbents from 1970 (state, year of inauguration, name tokens).
mg = pd.read_csv(DATA_DIR / "electoralData/raw/magar_elecRetrns/data/goed1970-on.incumbents.csv")
mg = mg[mg.incumbent.notna() & mg["date.in"].notna()]
mg["start_year"] = mg["date.in"].astype(str).str[:4].astype(int)
mg["state"] = mg.edon.astype(int).map(lambda e: STATES[e - 1])
def toks(s):
    return set(re.findall(r"[a-z]{3,}", plain(s).lower())) - {"del", "las", "los"}
def magar_agrees(r):
    m = mg[(mg.state == r.state) & (mg.start_year.between(r.start_year - 1, r.start_year + 1))]
    if m.empty:
        return None
    return int(any(len(toks(r.name_wiki) & toks(x)) >= 2 for x in m.incumbent))
R["magar_match"] = R.apply(lambda r: magar_agrees(r) if r.start_year >= 1970 and r.kind == "constitutional" else None, axis=1)
mg_missing = [(r.state, r.start_year, r.incumbent) for r in mg[mg.start_year <= 2000].itertuples()
              if not any(len(toks(r.incumbent) & toks(n)) >= 2 for n in
                         R[(R.state == r.state) & R.start_year.between(r.start_year - 1, r.start_year + 1)].name_wiki)]

# Check (iii): the second annex, same governors and start years.
a2 = set(zip(alt.state, alt.name_wiki.map(lambda s: plain(s).lower()), alt.start_year))
inter = R[R.state.isin(two)]
both = inter.apply(lambda r: (r.state, plain(r.name_wiki).lower(), r.start_year) in a2, axis=1).mean() if len(inter) else None

R = R.sort_values(["state", "start"]).reset_index(drop=True)

# Early exit of a constitutional governor: the next tenure in the state is interim, substitute, provisional or acting
# (Wikipedia writes the reason in the successor's note: "interino por licencia de ..."), unless he resumed the post.
# The reason is read from his note and his successor's.
R["early_exit"], R["exit_reason"] = 0, ""
for st, g in R.groupby("state"):
    idx = list(g.index)
    for j, i in enumerate(idx[:-1]):
        if R.at[i, "kind"] != "constitutional":
            continue
        nxt = R.loc[idx[j + 1]]
        back = any(plain(R.at[k, "name_wiki"]) == plain(R.at[i, "name_wiki"]) for k in idx[j + 1:j + 3])
        if nxt.kind in ("interim", "substitute", "provisional", "acting") and not back:
            R.at[i, "early_exit"] = 1
            text = plain(f"{R.at[i, 'notes']} {nxt.notes}").lower()
            R.at[i, "exit_reason"] = next((k for k in ("removed", "died", "resigned", "leave") if re.search(EXIT[k], text)),
                                          "not stated")
R.to_csv(OUT / "governors_roster.csv", index=False)
w = R[R.start_year.between(1934, 2000)]
checks = pd.DataFrame([
    ("tenures 1934-2000", len(w)), ("states", w.state.nunique()),
    ("constitutional", (w.kind == "constitutional").sum()), ("interim/substitute/provisional/acting", w.kind.isin(["interim", "substitute", "provisional", "acting"]).sum()),
    ("regents (Federal District)", (w.kind == "regent").sum()),
    ("dates to the day (start)", (w.start_precision == "day").mean()),
    ("matched to Camp", w.person_id.notna().mean()), ("matched, constitutional", w[w.kind == "constitutional"].person_id.notna().mean()),
    ("ambiguous names", (w.match_status == "ambiguous").sum()),
    ("matched with a Camp governor record of that state and time", w.camp_governor_record.mean()),
    ("Magar 1970-2000 incumbents found in the roster", 1 - len(mg_missing) / (mg.start_year <= 2000).sum()),
    ("roster constitutional 1970-2000 found in Magar", w.magar_match.mean()),
    ("states with two annexes: rows found in both", both)], columns=["check", "value"])
checks.to_csv(OUT / "governors_roster_checks.csv", index=False)
print(checks.to_string(index=False))
print("\nMagar incumbents not found:", mg_missing[:12])
print("\nmatched to Camp but no Camp governor record of that state:")
print(w[(w.camp_governor_record == 0)][["state", "name_wiki", "start_year", "kind"]].head(15).to_string(index=False))
