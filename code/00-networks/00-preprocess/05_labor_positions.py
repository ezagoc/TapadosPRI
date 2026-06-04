"""
Build the labor / union positions dataset from parsed_positions.csv.

Variables extracted:
  - org_clean:  best available organization name (regex → acronym → text extraction)
  - rank:       controlled vocabulary (secretary_general, president, secretary, ...)
  - sector:     type of organization (industrial_union, peasant, education,
                public_employees, student, professional, business, religious, other)
  - is_national: True if a national-level body

Wide format (one row per person):
  - primary_org, n_labor_positions, ever_secretary_general, ever_president,
    highest_labor_rank, first_labor_year, last_labor_year

Input:  data/parsed_positions.csv
Output: data/labor_positions.csv, data/labor_positions_wide.csv
"""

import re
import json
import getpass
import os
from typing import Optional
from pathlib import Path
import sys

import pandas as pd
import openai

CODE_DIR = Path(__file__).resolve().parents[2]
if str(CODE_DIR) not in sys.path:
    sys.path.append(str(CODE_DIR))

from config import PARSED_POSITIONS_CSV, LABOR_POSITIONS_CSV, LABOR_POSITIONS_WIDE_CSV

# ---------------------------------------------------------------------------
# Organization extraction — fills gaps left by 04_parse_positions.py
# ---------------------------------------------------------------------------

# Well-known acronyms → canonical form
_ACRONYM_RE = re.compile(
    r"\b(CTM|SNTE|CNC|CNOP|FSTSE|CROC|CROM|STPRM|STFRM|SUTERM|COPARMEX|"
    r"UOI|CTC|STIMAHCS|SUTGDF|CONASUPO|IMSS|ISSSTE|CFE|IPN|UNAM)\b",
    re.I,
)

# Generic "body of X" — Union, Federation, Confederation, Association, etc.
_BODY_NAME_RE = re.compile(
    r"\b((?:Union|Federation|Confederation|Confederacion|Federacion|"
    r"Association|League|Liga|Chamber|College|Council|Alliance|Institute|"
    r"Society|Cooperative|Syndicate|Sindicato|Committee)\s+"
    r"(?:of\s+(?:the\s+)?)?[A-Za-z][A-Za-z\s\-]{2,60}?)"
    r"(?=\s*,|\s+\d{4}|\s*$|\s+of\s+(?:the\s+)?[A-Z])",
    re.I,
)

# "Local No. X, Union of Y"
_LOCAL_RE = re.compile(
    r"Local\s+No\.?\s*\d+\s*,\s*"
    r"((?:Union|Sindicato|Federation)[^,;]{3,60}?)"
    r"(?=\s*,|\s+\d{4}|\s*$)",
    re.I,
)


def extract_labor_org(text: str, existing_org: object) -> Optional[str]:
    if isinstance(existing_org, str) and len(existing_org) >= 3:
        return existing_org
    if not isinstance(text, str):
        return None
    # 1. Acronym
    m = _ACRONYM_RE.search(text)
    if m:
        return m.group(1).upper()
    # 2. "Local No. X, Union of Y"
    m = _LOCAL_RE.search(text)
    if m:
        return m.group(1).strip().rstrip(".,;")
    # 3. Generic body name
    m = _BODY_NAME_RE.search(text)
    if m:
        return m.group(1).strip().rstrip(".,;")
    return None


# ---------------------------------------------------------------------------
# Rank classification
# ---------------------------------------------------------------------------

_RANK_PATTERNS = [
    ("secretary_general", re.compile(r"^(?:assistant\s+)?secretary[\s-]?general\b|^secretarygeneral\b", re.I)),
    ("president",         re.compile(r"^(?:vice\s+)?president\b", re.I)),
    ("director_general",  re.compile(r"^director\s+general\b", re.I)),
    ("secretary",         re.compile(r"^secretary\b|^secretary\s+of\b", re.I)),
    ("director",          re.compile(r"^director\b", re.I)),
    ("delegate",          re.compile(r"^(?:general\s+)?delegate\b", re.I)),
    ("coordinator",       re.compile(r"^coordinator\b", re.I)),
    ("treasurer",         re.compile(r"^treasurer\b", re.I)),
    ("adviser",           re.compile(r"^(?:general\s+)?(?:adviser|advisor)\b", re.I)),
    ("representative",    re.compile(r"^representative\b", re.I)),
    ("member",            re.compile(r"^member\b", re.I)),
    ("other",             re.compile(r".", re.I)),
]

_RANK_ORDER = {label: i for i, (label, _) in enumerate(_RANK_PATTERNS)}


def classify_rank(text: str) -> str:
    if not isinstance(text, str):
        return "other"
    for label, pattern in _RANK_PATTERNS:
        if pattern.search(text):
            return label
    return "other"


# ---------------------------------------------------------------------------
# Sector classification — based on org name + role text
# ---------------------------------------------------------------------------

_SECTOR_RULES = [
    ("student",        re.compile(
        r"\bstudent\b|\buniversity\s+federation\b|\bfederation\s+of\s+(?:university\s+)?students\b"
        r"|\bstudent\s+(?:federation|union|association|league|movement|activist)\b",
        re.I,
    )),
    ("religious",      re.compile(
        r"\bcatholic\b|\breligious\b|\bchurch\b|\bjesuit\b|"
        r"\bchristian\b|\bevangelical\b|\bsinarquist\b",
        re.I,
    )),
    ("education",      re.compile(
        r"\bSNTE\b|\bteachers?\b|\beducation\s+workers?\b|\bprofessors?\b"
        r"|\bteaching\b|\bacademic\s+(?:union|workers?)\b",
        re.I,
    )),
    ("peasant",        re.compile(
        r"\bCNC\b|\bpeasant\b|\bagrar(?:ian|io)\b|\bfarmers?\b|\bcampesino\b"
        r"|\bsugar(?:cane)?\s+(?:producers?|workers?)\b"
        r"|\bleague\s+of\s+agrarian\b|\bagrarian\s+(?:league|community)\b",
        re.I,
    )),
    ("public_employees", re.compile(
        r"\bFSTSE\b|\bISSSSE\b|\bgovernment\s+(?:employees?|workers?)\b"
        r"|\bpublic\s+(?:employees?|servants?|workers?)\b"
        r"|\bfederal\s+(?:employees?|workers?)\b"
        r"|\bworkers?\s+of\s+(?:the\s+)?(?:Secretariat|ISSSTE|IMSS|CFE|PEMEX|IPN|UNAM)\b",
        re.I,
    )),
    ("business",       re.compile(
        r"\bCOPARMEX\b|\bchamber\s+of\s+(?:industry|commerce|construction)\b"
        r"|\bindustrialists?\b|\bemployers?\b|\bmanufactur\b"
        r"|\bnational\s+chamber\b|\bindustrial\s+(?:association|chamber)\b",
        re.I,
    )),
    ("professional",   re.compile(
        r"\blawyers?\b|\barchitects?\b|\beconomists?\b|\bphysicians?\b|\bdoctors?\b"
        r"|\bengineers?\b|\bjournalists?\b|\bwriters?\b|\baccountants?\b"
        r"|\bnational\s+college\s+of\b|\bbar\s+association\b|\bmedical\s+association\b",
        re.I,
    )),
    ("industrial_union", re.compile(
        r"\bCTM\b|\bCROC\b|\bCROM\b|\bSTPRM\b|\bSTFRM\b|\bSUTERM\b"
        r"|\bUOI\b|\bCTC\b|\bpetroleum\s+workers?\b|\brailroad\s+workers?\b"
        r"|\belectricity\s+workers?\b|\btextile\s+workers?\b|\bcement\s+workers?\b"
        r"|\bmineral\s+workers?\b|\bsteel\s+workers?\b|\bmine\s+workers?\b",
        re.I,
    )),
]


def classify_sector(org: Optional[str], text: str) -> str:
    combined = f"{org or ''} {text or ''}"
    for sector, pattern in _SECTOR_RULES:
        if pattern.search(combined):
            return sector
    return "other"


# ---------------------------------------------------------------------------
# National vs. state/local
# ---------------------------------------------------------------------------

_NATIONAL_ORG_RE = re.compile(
    r"\bCTM\b|\bSNTE\b|\bCNC\b|\bCNOP\b|\bFSTSE\b|\bCROC\b|\bCROM\b"
    r"|\bSTPRM\b|\bSTFRM\b|\bSUTERM\b|\bCOPARMEX\b"
    r"|\bnational\b|\bnacional\b",
    re.I,
)


def classify_national(org: Optional[str], text: str) -> Optional[bool]:
    combined = f"{org or ''} {text or ''}"
    if _NATIONAL_ORG_RE.search(combined):
        return True
    return None


# ---------------------------------------------------------------------------
# Load and filter
# ---------------------------------------------------------------------------

df    = pd.read_csv(PARSED_POSITIONS_CSV)
labor = df[df["field_type"] == "labor_positions"].copy().reset_index(drop=True)

cols = [
    "record_id", "person_id", "person_name",
    "role_text_raw", "role_text",
    "position_title",
    "organization",
    "state",
    "year_start", "year_end",
    "birth_date_clean", "birth_date_precision",
]
labor = labor[cols]

# ---------------------------------------------------------------------------
# Variable extraction
# ---------------------------------------------------------------------------

labor["org_clean"]   = labor.apply(
    lambda r: extract_labor_org(r["role_text_raw"], r["organization"]), axis=1
)
labor["rank"]        = labor["role_text_raw"].map(classify_rank)
labor["sector"]      = labor.apply(
    lambda r: classify_sector(r["org_clean"], r["role_text_raw"]), axis=1
)
labor["is_national"] = labor.apply(
    lambda r: classify_national(r["org_clean"], r["role_text_raw"]), axis=1
)
labor["years_in_post"] = (
    (labor["year_end"] - labor["year_start"])
    .where(labor["year_start"].notna() & labor["year_end"].notna())
    .clip(lower=0)
)

# ---------------------------------------------------------------------------
# GPT fallback — fill missing org_clean via OpenAI API
# ---------------------------------------------------------------------------

_BATCH_SIZE = 20

_SYSTEM_PROMPT = (
    "You extract structured data from Mexican labor/union biography entries (1900-2000). "
    "Each entry describes one position held by a Mexican politician in a union, federation, "
    "professional association, student organization, or similar body. "
    "For each numbered entry return a JSON object inside a 'results' array with:\n"
    "  'organization': the name of the union, federation, or association "
    "(e.g. 'CTM', 'SNTE', 'Federation of University Students of Guadalajara', "
    "'Chamber of Industry and Commerce'). Return null if none is identifiable.\n"
    "  'position_title': the person's role or title (e.g. 'Secretary-General', 'President', "
    "'Delegate'). Return null if unclear.\n"
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
        data  = json.loads(response.choices[0].message.content)
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


missing_mask = labor["org_clean"].isna()
print(f"\n{missing_mask.sum()} records have no organization after regex extraction.")

labor["org_gpt"]            = None
labor["position_title_gpt"] = None

if missing_mask.any():
    api_key = os.getenv("OPENAI_API_KEY") or getpass.getpass("Enter your OpenAI API key: ")
    print(f"Running GPT (gpt-4o-mini) on {missing_mask.sum()} records...")
    gpt_results = gpt_fill_missing(labor.loc[missing_mask, "role_text_raw"], api_key)

    labor.loc[missing_mask, "org_gpt"]            = gpt_results["organization"]
    labor.loc[missing_mask, "position_title_gpt"] = gpt_results["position_title"]

    labor["org_clean"]     = labor["org_clean"].fillna(labor["org_gpt"])
    labor["position_title"] = labor["position_title"].fillna(labor["position_title_gpt"])

    filled_org   = labor.loc[missing_mask, "org_clean"].notna().sum()
    filled_title = labor.loc[missing_mask, "position_title"].notna().sum()
    print(f"  GPT filled {filled_org} organizations and {filled_title} position titles")

# Re-run sector and is_national now that org_clean is more complete
labor["sector"]      = labor.apply(
    lambda r: classify_sector(r["org_clean"], r["role_text_raw"]), axis=1
)
labor["is_national"] = labor.apply(
    lambda r: classify_national(r["org_clean"], r["role_text_raw"]), axis=1
)

# ---------------------------------------------------------------------------
# Save long format
# ---------------------------------------------------------------------------

labor.to_csv(LABOR_POSITIONS_CSV, index=False)

print(f"Labor position records: {len(labor)}")
print(f"\nOrg extracted: {labor['org_clean'].notna().sum()} "
      f"({100*labor['org_clean'].notna().mean():.1f}%)")
print(f"\nRank distribution:")
print(labor["rank"].value_counts().head(12).to_string())
print(f"\nSector distribution:")
print(labor["sector"].value_counts().to_string())
print(f"\nNational body: {labor['is_national'].sum()}")

# ---------------------------------------------------------------------------
# Wide format — one row per person
# ---------------------------------------------------------------------------

_TOP_RANKS = {"secretary_general", "president", "director_general"}


def _best_rank(ranks: pd.Series) -> Optional[str]:
    valid = [r for r in ranks if isinstance(r, str)]
    if not valid:
        return None
    return min(valid, key=lambda r: _RANK_ORDER.get(r, 99))


def make_wide(labor: pd.DataFrame) -> pd.DataFrame:
    def agg(sub):
        ranks = sub["rank"]
        org_counts = sub["org_clean"].dropna().value_counts()
        return pd.Series({
            "birth_date_clean":        sub["birth_date_clean"].iloc[0],
            "birth_date_precision":    sub["birth_date_precision"].iloc[0],
            "n_labor_positions":       len(sub),
            "first_labor_year":        sub["year_start"].min(),
            "last_labor_year":         sub["year_end"].max(),
            "ever_secretary_general":  int((ranks == "secretary_general").any()),
            "ever_president":          int((ranks == "president").any()),
            "ever_top_rank":           int(ranks.isin(_TOP_RANKS).any()),
            "highest_labor_rank":      _best_rank(ranks),
            "primary_org":             org_counts.index[0] if len(org_counts) else None,
            "sectors":                 "|".join(sorted(sub["sector"].dropna().unique())),
        })

    wide = (
        labor.groupby(["person_id", "person_name"], sort=False)
        .apply(agg)
        .reset_index()
    )
    return wide


wide = make_wide(labor)
wide.to_csv(LABOR_POSITIONS_WIDE_CSV, index=False)

print(f"\nWide format: {len(wide)} persons")
print(f"  Ever secretary-general: {wide['ever_secretary_general'].sum()}")
print(f"  Ever president:         {wide['ever_president'].sum()}")
print(f"\nHighest labor rank distribution:")
print(wide["highest_labor_rank"].value_counts().to_string())
print(f"\nSaved long:  {LABOR_POSITIONS_CSV}")
print(f"Saved wide:  {LABOR_POSITIONS_WIDE_CSV}")
