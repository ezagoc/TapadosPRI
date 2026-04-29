"""
Build the government (appointed) positions dataset from parsed_positions.csv.

Filters to field_type == 'govt_positions' and extracts:
  - rank: hierarchical seniority level
  - secretariat_norm: normalized ministry/agency name
  - is_federal: True if federal post, False if state/local, None if unknown
  - is_judicial: True if judge/magistrate/justice role
  - years_in_post: year_end - year_start

Also produces a wide-format summary (one row per person).

Input:  data/parsed_positions.csv
Output: data/govt_positions.csv, data/govt_positions_wide.csv
"""

import re
import json
import getpass
from typing import Optional
from pathlib import Path
import sys

import pandas as pd
import openai

CODE_DIR = Path(__file__).resolve().parents[2]
if str(CODE_DIR) not in sys.path:
    sys.path.append(str(CODE_DIR))

from config import PARSED_POSITIONS_CSV, GOVT_POSITIONS_CSV, GOVT_POSITIONS_WIDE_CSV

# ---------------------------------------------------------------------------
# Rank classification — matched against role_text_raw
# Priority: more specific patterns first
# ---------------------------------------------------------------------------

_RANK_PATTERNS = [
    # Judiciary (before generic judge)
    ("justice",                  re.compile(r"^(?:supernumerary\s+)?justice\b", re.I)),
    ("magistrate",               re.compile(r"^magistrate\b", re.I)),
    ("circuit_judge",            re.compile(r"^circuit\s+(?:court\s+)?judge\b", re.I)),
    ("district_judge",           re.compile(r"^district\s+judge\b", re.I)),
    ("judge",                    re.compile(r"^judge\b", re.I)),
    # Governors / executive branch
    ("acting_governor",          re.compile(r"^acting\s+governor\b", re.I)),
    ("governor",                 re.compile(r"^governor\b", re.I)),
    # Diplomatic
    ("ambassador",               re.compile(
        r"^(?:appointed|special|confidential|alternate|extraordinary|personal|first)\s+ambassador\b"
        r"|^rank\s+of\s+(?:special\s+)?ambassador\b"
        r"|^ambassador\b"
        r"|\brank\s+of\s+(?:special\s+)?ambassador\b"
        r"|\bjoined\s+diplomatic\s+corps\s+ambassador\b",
        re.I,
    )),
    ("consul_general",           re.compile(r"^consul\s+general\b", re.I)),
    ("consul",                   re.compile(r"^consul\b", re.I)),
    # Attorney General
    ("assistant_attorney_general", re.compile(r"^(?:\d+(?:st|nd|rd|th)\s+)?assistant\s+attorney\s+general\b", re.I)),
    ("attorney_general",         re.compile(r"^attorney\s+general\b", re.I)),
    # Cabinet
    ("secretary",                re.compile(r"^secretary\s+of\b", re.I)),
    # Sub-cabinet (compound before simple)
    ("subsecretary",             re.compile(r"^(?:sub|under)secretary\b", re.I)),
    ("assistant_secretary",      re.compile(r"^assistant\s+secretary\b", re.I)),
    ("secretary_general",        re.compile(r"^secretary[\s-]?general\b|^secretarygeneral\b", re.I)),
    ("director_general",         re.compile(r"^director\s+general\b", re.I)),
    ("oficial_mayor",            re.compile(r"^(?:oficial|official)\s+mayor\b", re.I)),
    # Senior management (compound before simple)
    ("general_manager",          re.compile(r"^general\s+manager\b", re.I)),
    ("coordinator_general",      re.compile(r"^(?:coordinator|general)\s+general\b|^general\s+coordinator\b", re.I)),
    ("inspector_general",        re.compile(r"^inspector\s+general\b", re.I)),
    ("assistant_director_general", re.compile(r"^assistant\s+director\s+general\b", re.I)),
    ("assistant_director",       re.compile(r"^assistant\s+director\b", re.I)),
    ("assistant_manager",        re.compile(r"^assistant\s+manager\b", re.I)),
    # Mid management
    ("director",                 re.compile(r"^director\b", re.I)),
    ("coordinator",              re.compile(r"^coordinator\b", re.I)),
    ("head",                     re.compile(r"^head\b|^chief\b", re.I)),
    ("manager",                  re.compile(r"^manager\b", re.I)),
    ("inspector",                re.compile(r"^inspector\b", re.I)),
    # Staff
    ("delegate",                 re.compile(r"^delegate\b|^fiduciary\s+delegate\b", re.I)),
    ("administrator",            re.compile(r"^administrator\b", re.I)),
    ("treasurer",                re.compile(r"^treasurer\b", re.I)),
    ("comptroller",              re.compile(r"^comptroller\b|^controller\s+general\b", re.I)),
    ("technical_secretary",      re.compile(r"^(?:auxiliary|technical)\s+secretary\b", re.I)),
    ("adviser",                  re.compile(r"^(?:general\s+)?(?:adviser|advisor)\b", re.I)),
    ("assistant",                re.compile(r"^assistant\b", re.I)),
    ("analyst",                  re.compile(r"^analyst\b", re.I)),
    ("member",                   re.compile(r"^member\b", re.I)),
    ("other",                    re.compile(r".", re.I)),
]

# Lower number = higher rank
_RANK_ORDER = {
    "secretary":                 1,
    "attorney_general":          2,
    "governor":                  3,
    "acting_governor":           4,
    "ambassador":                5,
    "consul_general":            6,
    "justice":                   7,
    "magistrate":                8,
    "circuit_judge":             9,
    "district_judge":            10,
    "judge":                     11,
    "subsecretary":              12,
    "assistant_attorney_general": 13,
    "assistant_secretary":       14,
    "director_general":          13,
    "oficial_mayor":             14,
    "secretary_general":         15,
    "general_manager":           16,
    "coordinator_general":       17,
    "inspector_general":         18,
    "assistant_director_general": 19,
    "director":                  20,
    "assistant_director":        21,
    "coordinator":               22,
    "head":                      23,
    "manager":                   24,
    "assistant_manager":         25,
    "inspector":                 26,
    "delegate":                  27,
    "administrator":             28,
    "treasurer":                 29,
    "comptroller":               30,
    "technical_secretary":       31,
    "adviser":                   32,
    "assistant":                 33,
    "analyst":                   34,
    "member":                    35,
    "consul":                    36,
    "other":                     99,
}


def classify_rank(text: str) -> Optional[str]:
    if not isinstance(text, str):
        return None
    for rank, pattern in _RANK_PATTERNS:
        if pattern.search(text):
            return rank
    return None


# ---------------------------------------------------------------------------
# Secretariat normalization — maps raw organization string to canonical name
# ---------------------------------------------------------------------------

_SECRETARIAT_NORM_MAP = [
    (re.compile(r"secretariat of the treasury|hacienda", re.I),
     "Secretariat of the Treasury"),
    (re.compile(r"secretariat of government|gobernacion", re.I),
     "Secretariat of Government"),
    (re.compile(r"secretariat of national defense", re.I),
     "Secretariat of National Defense"),
    (re.compile(r"secretariat of foreign relations", re.I),
     "Secretariat of Foreign Relations"),
    (re.compile(r"secretariat of public education", re.I),
     "Secretariat of Public Education"),
    (re.compile(r"secretariat of communications and public works", re.I),
     "Secretariat of Communications and Public Works"),
    (re.compile(r"secretariat of communications and transportation", re.I),
     "Secretariat of Communications and Transportation"),
    (re.compile(r"secretariat of public works", re.I),
     "Secretariat of Public Works"),
    (re.compile(r"secretariat of health", re.I),
     "Secretariat of Health"),
    (re.compile(r"secretariat of labor", re.I),
     "Secretariat of Labor"),
    (re.compile(r"secretariat of agriculture and hydraulic", re.I),
     "Secretariat of Agriculture and Hydraulic Resources"),
    (re.compile(r"secretariat of agriculture and livestock", re.I),
     "Secretariat of Agriculture and Livestock"),
    (re.compile(r"secretariat of agriculture", re.I),
     "Secretariat of Agriculture"),
    (re.compile(r"secretariat of agrarian reform", re.I),
     "Secretariat of Agrarian Reform"),
    (re.compile(r"secretariat of programming and budget", re.I),
     "Secretariat of Programming and Budget"),
    (re.compile(r"secretariat of industry and commerce", re.I),
     "Secretariat of Industry and Commerce"),
    (re.compile(r"secretariat of commerce", re.I),
     "Secretariat of Commerce"),
    (re.compile(r"secretariat of tourism", re.I),
     "Secretariat of Tourism"),
    (re.compile(r"secretariat of energy and mines", re.I),
     "Secretariat of Energy and Mines"),
    (re.compile(r"secretariat of energy", re.I),
     "Secretariat of Energy"),
    (re.compile(r"secretariat of social development", re.I),
     "Secretariat of Social Development"),
    (re.compile(r"secretariat of (?:the )?environment", re.I),
     "Secretariat of Environment"),
    (re.compile(r"secretariat of public security", re.I),
     "Secretariat of Public Security"),
    (re.compile(r"secretariat of public function", re.I),
     "Secretariat of Public Function"),
    (re.compile(r"secretariat of the controller|secretariat of the comptroller", re.I),
     "Secretariat of the Controller General"),
    (re.compile(r"secretariat of the navy", re.I),
     "Secretariat of the Navy"),
    (re.compile(r"secretariat of national patrimony", re.I),
     "Secretariat of National Patrimony"),
    (re.compile(r"secretariat of the presidency", re.I),
     "Secretariat of the Presidency"),
    (re.compile(r"secretariat of hydraulic resources", re.I),
     "Secretariat of Hydraulic Resources"),
    (re.compile(r"secretariat of human settlements", re.I),
     "Secretariat of Human Settlements"),
    (re.compile(r"secretariat of urban development", re.I),
     "Secretariat of Urban Development and Ecology"),
    (re.compile(r"secretariat of national patrimony", re.I),
     "Secretariat of National Patrimony"),
]


def normalize_secretariat(org: str) -> Optional[str]:
    if not isinstance(org, str):
        return None
    for pattern, canonical in _SECRETARIAT_NORM_MAP:
        if pattern.search(org):
            return canonical
    return org  # return as-is for non-secretariat orgs


# ---------------------------------------------------------------------------
# Federal vs. state classification
# ---------------------------------------------------------------------------

_FEDERAL_ORG_RE = re.compile(
    r"secretariat of|bank of mexico|nacional financiera|banrural|banobras|"
    r"pemex|petroleos mexicanos|cfe\b|federal electric|"
    r"imss|issste|infonavit|conasupo|"
    r"supreme court|chamber of deputies|senate\b|"
    r"national polytechnic|national finance bank|"
    r"foreign trade bank|economics cabinet|"
    r"national commission|national institute",
    re.I,
)

_DDF_RE = re.compile(r"department of the federal district", re.I)


# ---------------------------------------------------------------------------
# Sub-department extraction — captures "Department of X" within role text
# Excludes top-level orgs (DDF, Dept of Agrarian Affairs, etc.)
# ---------------------------------------------------------------------------

_DEPT_RE = re.compile(
    r"\b(Department\s+of\s+[A-Za-z][^,;]{2,60}?)"
    r"(?:\s*,|\s+\d{4}|\s*$)",
    re.IGNORECASE,
)

_TOP_LEVEL_DEPT_RE = re.compile(
    r"^Department of the Federal District$|"
    r"^Department of Agrarian Affairs|"
    r"^Department of Tourism$",
    re.IGNORECASE,
)


def extract_subdepartment(text: str) -> Optional[str]:
    if not isinstance(text, str):
        return None
    m = _DEPT_RE.search(text)
    if not m:
        return None
    dept = m.group(1).strip().rstrip(".,;")
    if _TOP_LEVEL_DEPT_RE.match(dept):
        return None
    return dept


def classify_federal(row: pd.Series) -> Optional[bool]:
    org = str(row.get("organization") or "")
    state = str(row.get("state") or "")
    text = str(row.get("role_text_raw") or "")

    if _DDF_RE.search(org):
        return False  # DDF is local government of Mexico City, not federal
    if _FEDERAL_ORG_RE.search(org):
        return True
    # State-level indicator in raw text or non-federal state
    if state and state != "Federal District" and state != "nan":
        # Could still be a federal delegate posted in a state — check text
        if re.search(r"\bsecretary\s+of\b|\bsecretary,\b", text, re.I):
            return True  # cabinet-level → always federal
        return False
    return None


# ---------------------------------------------------------------------------
# Load and filter
# ---------------------------------------------------------------------------

df = pd.read_csv(PARSED_POSITIONS_CSV)
govt = df[df["field_type"] == "govt_positions"].copy()
govt = govt.reset_index(drop=True)

cols = [
    "record_id", "person_id", "person_name",
    "role_text_raw", "role_text",
    "position_title",
    "organization",
    "state",
    "year_start", "year_end",
    "birth_date_clean", "birth_date_precision",
]
govt = govt[cols]

# ---------------------------------------------------------------------------
# Variable extraction
# ---------------------------------------------------------------------------

govt["rank"]             = govt["role_text_raw"].map(classify_rank)
govt["secretariat_norm"] = govt["organization"].map(normalize_secretariat)
govt["is_federal"]       = govt.apply(classify_federal, axis=1)
govt["sub_department"]   = govt["role_text_raw"].map(extract_subdepartment)
govt["is_judicial"]      = govt["rank"].isin(
    {"justice", "magistrate", "circuit_judge", "district_judge", "judge"}
)
govt["years_in_post"] = (
    (govt["year_end"] - govt["year_start"])
    .where(govt["year_start"].notna() & govt["year_end"].notna())
    .clip(lower=0)
)

# ---------------------------------------------------------------------------
# GPT fallback — fill missing organization and position_title via OpenAI API
# ---------------------------------------------------------------------------

_BATCH_SIZE = 20

_SYSTEM_PROMPT = (
    "You extract structured data from Mexican government biography entries (1920-2000). "
    "Each entry describes one position held by a Mexican politician. "
    "For each numbered entry return a JSON object inside a 'results' array with:\n"
    "  'organization': the top-level government institution or agency (e.g. 'Secretariat of Health', "
    "'PEMEX', 'Supreme Court', 'Department of the Federal District'). Return null if none is identifiable.\n"
    "  'position_title': the person's exact role or title (e.g. 'Director General', 'Ambassador', "
    "'Secretary'). Return null if unclear.\n"
    "Return ONLY valid JSON of the form {\"results\": [{...}, ...]}. No explanation."
)


def _gpt_extract_batch(texts: list[tuple[int, str]], client: openai.OpenAI) -> list[dict]:
    numbered = "\n".join(f"{i+1}. {text}" for i, (_, text) in enumerate(texts))
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": numbered},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        data = json.loads(response.choices[0].message.content)
        items = data.get("results", list(data.values())[0] if data else [])
        return [
            {"index": idx, "organization": r.get("organization"), "position_title": r.get("position_title")}
            for (idx, _), r in zip(texts, items)
        ]
    except Exception as e:
        print(f"    GPT error on batch: {e}")
        return [{"index": idx, "organization": None, "position_title": None} for idx, _ in texts]


def gpt_fill_missing(texts: pd.Series, api_key: str) -> pd.DataFrame:
    client = openai.OpenAI(api_key=api_key)
    items  = list(texts.items())
    all_results = []
    for i in range(0, len(items), _BATCH_SIZE):
        batch = items[i : i + _BATCH_SIZE]
        all_results.extend(_gpt_extract_batch(batch, client))
        done = min(i + _BATCH_SIZE, len(items))
        print(f"  {done}/{len(items)} processed...", end="\r")
    print()
    return pd.DataFrame(all_results).set_index("index")


missing_mask = govt["organization"].isna()
print(f"\n{missing_mask.sum()} records have no organization after regex extraction.")

govt["org_gpt"]            = None
govt["position_title_gpt"] = None

if missing_mask.any():
    api_key = getpass.getpass("Enter your OpenAI API key: ")
    print(f"Running GPT (gpt-4o-mini) on {missing_mask.sum()} records...")
    gpt_results = gpt_fill_missing(govt.loc[missing_mask, "role_text_raw"], api_key)

    govt.loc[missing_mask, "org_gpt"]            = gpt_results["organization"]
    govt.loc[missing_mask, "position_title_gpt"] = gpt_results["position_title"]

    govt["organization"]   = govt["organization"].fillna(govt["org_gpt"])
    govt["position_title"] = govt["position_title"].fillna(govt["position_title_gpt"])

    filled_org   = govt.loc[missing_mask, "organization"].notna().sum()
    filled_title = govt.loc[missing_mask, "position_title"].notna().sum()
    print(f"  GPT filled {filled_org} organizations and {filled_title} position titles")

# ---------------------------------------------------------------------------
# Save long format
# ---------------------------------------------------------------------------

govt.to_csv(GOVT_POSITIONS_CSV, index=False)
print(f"Government position records: {len(govt)}")
print(f"\nRank distribution (top 20):")
print(govt["rank"].value_counts().head(20).to_string())
print(f"\nJudicial records: {govt['is_judicial'].sum()}")
print(f"Federal (True): {(govt['is_federal'] == True).sum()}")
print(f"State (False): {(govt['is_federal'] == False).sum()}")
print(f"Unknown (None): {govt['is_federal'].isna().sum()}")

# ---------------------------------------------------------------------------
# Wide format — one row per person
# ---------------------------------------------------------------------------

_JUDICIAL_RANKS = {"justice", "magistrate", "circuit_judge", "district_judge", "judge"}
_SECRETARY_RANKS = {"secretary"}
_SUBSECRETARY_RANKS = {"subsecretary", "assistant_secretary"}
_DG_RANKS = {"director_general", "assistant_director_general"}


def _best_rank(ranks: pd.Series) -> Optional[str]:
    valid = [r for r in ranks if isinstance(r, str)]
    if not valid:
        return None
    return min(valid, key=lambda r: _RANK_ORDER.get(r, 99))


def _primary_secretariat(orgs: pd.Series) -> Optional[str]:
    counts = orgs.dropna().value_counts()
    return counts.index[0] if len(counts) > 0 else None


def make_wide(govt: pd.DataFrame) -> pd.DataFrame:
    def agg(sub):
        ranks = sub["rank"]
        return pd.Series({
            "birth_date_clean":      sub["birth_date_clean"].iloc[0],
            "birth_date_precision":  sub["birth_date_precision"].iloc[0],
            "n_govt_positions":      len(sub),
            "first_govt_year":       sub["year_start"].min(),
            "last_govt_year":        sub["year_end"].max(),
            "ever_secretary":        int(ranks.isin(_SECRETARY_RANKS).any()),
            "ever_subsecretary":     int(ranks.isin(_SUBSECRETARY_RANKS).any()),
            "ever_director_general": int(ranks.isin(_DG_RANKS).any()),
            "ever_governor":         int((ranks == "governor").any()),
            "ever_ambassador":       int((ranks == "ambassador").any()),
            "ever_judge":            int(ranks.isin(_JUDICIAL_RANKS).any()),
            "highest_rank":          _best_rank(ranks),
            "primary_secretariat":   _primary_secretariat(sub["secretariat_norm"]),
        })

    wide = (
        govt.groupby(["person_id", "person_name"], sort=False)
        .apply(agg)
        .reset_index()
    )
    return wide


wide = make_wide(govt)
wide.to_csv(GOVT_POSITIONS_WIDE_CSV, index=False)

print(f"\nWide format: {len(wide)} persons")
print(f"  Ever secretary:        {wide['ever_secretary'].sum()}")
print(f"  Ever subsecretary:     {wide['ever_subsecretary'].sum()}")
print(f"  Ever director general: {wide['ever_director_general'].sum()}")
print(f"  Ever governor:         {wide['ever_governor'].sum()}")
print(f"  Ever ambassador:       {wide['ever_ambassador'].sum()}")
print(f"  Ever judge:            {wide['ever_judge'].sum()}")
print(f"\nHighest rank distribution:")
print(wide["highest_rank"].value_counts().head(15).to_string())
print(f"\nSaved long:  {GOVT_POSITIONS_CSV}")
print(f"Saved wide:  {GOVT_POSITIONS_WIDE_CSV}")
