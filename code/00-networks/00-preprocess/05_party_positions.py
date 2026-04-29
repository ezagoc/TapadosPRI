"""
Build the party positions dataset from parsed_positions.csv.

Variables extracted:
  - party:         canonical party acronym (PRI, PAN, PRD, ...)
  - pri_lineage:   True if PRI/PRM/PNR (ruling-party lineage)
  - party_body:    intra-party organizational unit (CEN, IEPES, State Committee, ...)
  - party_level:   national / state / local / None
  - record_type:   active_position / joined / campaign / candidate
  - party_rank:    hierarchical seniority tier within party structure

Wide format (one row per person):
  - primary_party, n_parties, pri_member, pan_member, prd_member,
    ever_national_leader, ever_cen, ever_state_president,
    highest_party_rank, n_active_positions,
    first_party_year, last_party_year

Input:  data/parsed_positions.csv
Output: data/party_positions.csv, data/party_positions_wide.csv
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

from config import PARSED_POSITIONS_CSV, PARTY_POSITIONS_CSV, PARTY_POSITIONS_WIDE_CSV

# ---------------------------------------------------------------------------
# Party identification
# ---------------------------------------------------------------------------

# Ordered: more specific patterns first to avoid "PT" swallowing "PST", etc.
_PARTY_PATTERNS = [
    (re.compile(r"\bPNR\b",                                              re.I), "PNR"),
    (re.compile(r"\bPRM\b",                                              re.I), "PRM"),
    (re.compile(r"\bPSUM\b",                                             re.I), "PSUM"),
    (re.compile(r"\bPST\b",                                              re.I), "PST"),
    (re.compile(r"\bPARM\b",                                             re.I), "PARM"),
    (re.compile(r"\bPFCRN\b",                                            re.I), "PFCRN"),
    (re.compile(r"\bPVEM\b",                                             re.I), "PVEM"),
    (re.compile(r"\bPDM\b",                                              re.I), "PDM"),
    (re.compile(r"\bPMT\b",                                              re.I), "PMT"),
    (re.compile(r"\bPCM\b|Mexican\s+Communist\s+Party\b",               re.I), "PCM"),
    (re.compile(r"\bPPS\b|Popular\s+Socialist\s+Party\b|Popular\s+Party\b", re.I), "PPS"),
    (re.compile(r"\bMORENA\b",                                           re.I), "MORENA"),
    (re.compile(r"\bPAN\b",                                              re.I), "PAN"),
    (re.compile(r"\bPRD\b",                                              re.I), "PRD"),
    (re.compile(r"\bPRI\b",                                              re.I), "PRI"),
    (re.compile(r"\bPT\b(?!\s*\d)",                                      re.I), "PT"),
    (re.compile(r"\bUNS\b|National\s+Sinarquista\s+Movement\b",         re.I), "UNS"),
    (re.compile(r"\bMexican\s+Liberal\s+Party\b",                       re.I), "PLM"),
]

_PRI_LINEAGE = {"PRI", "PRM", "PNR"}


def classify_party(org: str, text: str) -> Optional[str]:
    for source in (org, text):
        if not isinstance(source, str):
            continue
        for pattern, name in _PARTY_PATTERNS:
            if pattern.search(source):
                return name
    return None


# ---------------------------------------------------------------------------
# Intra-party body (organizational unit within the party)
# ---------------------------------------------------------------------------

_BODY_PATTERNS = [
    # Named acronym bodies — check before generic text patterns
    (re.compile(r"\bIEPES\b",                          re.I), "IEPES"),
    (re.compile(r"\bCEPES\b",                          re.I), "CEPES"),
    (re.compile(r"\bCNOP\b",                           re.I), "CNOP"),
    (re.compile(r"\bCNC\b",                            re.I), "CNC"),
    (re.compile(r"\bCTM\b",                            re.I), "CTM"),
    (re.compile(r"\bCEN\b",                            re.I), "CEN"),
    # Structural bodies from text
    (re.compile(r"\bNational\s+(?:Executive\s+)?Committee\b",  re.I), "National Committee"),
    (re.compile(r"\bCentral\s+Committee\b",            re.I), "Central Committee"),
    (re.compile(r"\bNational\s+(?:Political\s+)?Council\b",    re.I), "National Council"),
    (re.compile(r"\bNational\s+Assembly\b",            re.I), "National Assembly"),
    (re.compile(r"\bState\s+Committee\b",              re.I), "State Committee"),
    (re.compile(r"\bMunicipal\s+Committee\b",          re.I), "Municipal Committee"),
    (re.compile(r"\bDistrict\s+Committee\b",           re.I), "District Committee"),
    (re.compile(r"\bElectoral\s+Committee\b",          re.I), "Electoral Committee"),
    (re.compile(r"\bExecutive\s+Committee\b",          re.I), "Executive Committee"),
    (re.compile(r"\bAdvisory\s+Council\b",             re.I), "Advisory Council"),
    (re.compile(r"\bPolicy\s+Directorate\b",           re.I), "Policy Directorate"),
    (re.compile(r"\bRegional\s+Committee\b",           re.I), "Regional Committee"),
    (re.compile(r"\bYouth\b",                          re.I), "Youth Organization"),
]

_NATIONAL_BODIES = {
    "CEN", "IEPES", "National Committee", "Central Committee",
    "National Assembly", "National Council",
}
_STATE_BODIES    = {"CEPES", "State Committee", "Regional Committee"}
_LOCAL_BODIES    = {"Municipal Committee", "District Committee", "Electoral Committee"}


def classify_body(org: str, text: str) -> Optional[str]:
    for source in (org, text):
        if not isinstance(source, str):
            continue
        for pattern, body in _BODY_PATTERNS:
            if pattern.search(source):
                return body
    return None


# ---------------------------------------------------------------------------
# Party level: national / state / local
# ---------------------------------------------------------------------------

_NATIONAL_KW_RE = re.compile(
    r"\b(?:national|CEN\b|IEPES\b|central\s+committee|national\s+committee|"
    r"national\s+assembly|national\s+council|national\s+convention|"
    r"national\s+PRI|national\s+PAN|national\s+PRD)\b",
    re.I,
)
_LOCAL_KW_RE = re.compile(r"\bmunicipal\b|\bdistrict\b|\bparish\b", re.I)


def classify_party_level(
    body: Optional[str], state: Optional[str], text: str
) -> Optional[str]:
    if body in _NATIONAL_BODIES:
        return "national"
    if body in _STATE_BODIES:
        return "state"
    if body in _LOCAL_BODIES:
        return "local"
    if _NATIONAL_KW_RE.search(text or ""):
        return "national"
    if _LOCAL_KW_RE.search(text or ""):
        return "local"
    if state and state not in ("Federal District",):
        return "state"
    return None


# ---------------------------------------------------------------------------
# Record type: active_position / joined / campaign / candidate
# ---------------------------------------------------------------------------

_JOINED_RE    = re.compile(r"^(?:joined|became\s+(?:a\s+)?member|affiliated\s+with)\b", re.I)
_CAMPAIGN_RE  = re.compile(r"\bcampaign\b", re.I)
_CANDIDATE_RE = re.compile(r"\bprecandidate\b|\bcandidate\s+for\b|\bnomination\s+for\b", re.I)


def classify_record_type(text: str) -> str:
    if not isinstance(text, str):
        return "other"
    if _JOINED_RE.search(text):
        return "joined"
    if _CANDIDATE_RE.search(text):
        return "candidate"
    if _CAMPAIGN_RE.search(text):
        return "campaign"
    return "active_position"


# ---------------------------------------------------------------------------
# Party rank hierarchy — seniority within party structure
# Priority: check most specific first; uses both text and pre-computed fields
# ---------------------------------------------------------------------------

_RANK_ORDER = {
    "national_president":      1,
    "secretary_general_nat":   2,
    "cen_president":           3,
    "cen_secretary":           4,
    "iepes_director":          5,
    "national_delegate":       6,
    "state_president":         7,
    "state_secretary_general": 8,
    "campaign_leader":         9,
    "state_secretary":         10,
    "cen_member":              11,
    "adviser_member":          12,
    "campaign_participant":    13,
    "joined":                  14,
    "other":                   99,
}

_PRESIDENT_RE        = re.compile(r"^president\b", re.I)
_SEC_GENERAL_RE      = re.compile(r"^secretary[\s-]?general\b|^secretarygeneral\b", re.I)
_SECRETARY_OF_RE     = re.compile(r"^(?:assistant\s+)?secretary\b|secretary\s+of\b", re.I)
_IEPES_DIR_RE        = re.compile(r"^director.{0,20}\bIEPES\b", re.I)
_CEN_DELEGATE_RE     = re.compile(
    r"\bCEN\b.{0,30}\bdelegate\b|\bdelegate.{0,20}\bCEN\b"
    r"|general\s+delegate.{0,20}(?:PRI|PAN|PRD)",
    re.I,
)
_CAMPAIGN_LEADER_RE  = re.compile(
    r"(?:organizer|coordinator|director|chief|head|private\s+secretary).{0,50}"
    r"(?:presidential|gubernatorial)\s+campaign",
    re.I,
)
_ADVISER_MEMBER_RE   = re.compile(
    r"^(?:adviser|advisor|member|representative)\b|advisory\s+council|consultative",
    re.I,
)
_CAMPAIGN_RE2        = re.compile(r"\bcampaign\b", re.I)


def classify_party_rank(text: str, body: Optional[str], party_level: Optional[str]) -> str:
    if not isinstance(text, str):
        return "other"

    is_national = party_level == "national" or body in _NATIONAL_BODIES
    is_state    = party_level in ("state", "local") or body in _STATE_BODIES | _LOCAL_BODIES

    # President — level determines national vs. state
    if _PRESIDENT_RE.match(text):
        if body == "CEN":
            return "cen_president"
        return "national_president" if is_national else "state_president"

    # Secretary-general — level determines national vs. state
    if _SEC_GENERAL_RE.match(text):
        return "secretary_general_nat" if is_national else "state_secretary_general"

    # IEPES director
    if _IEPES_DIR_RE.search(text):
        return "iepes_director"

    # CEN-specific roles
    if re.search(r"\bCEN\b", text, re.I):
        if _CEN_DELEGATE_RE.search(text):
            return "national_delegate"
        if _SECRETARY_OF_RE.search(text):
            return "cen_secretary"
        return "cen_member"

    # National context — secretary of portfolio
    if is_national and _SECRETARY_OF_RE.search(text):
        return "cen_secretary"

    # Campaign leader (major campaigns — checked before generic campaign)
    if _CAMPAIGN_LEADER_RE.search(text):
        return "campaign_leader"

    # National delegate (non-CEN)
    if is_national and re.search(r"\bdelegate\b", text, re.I):
        return "national_delegate"

    # State-level secretary
    if is_state and _SECRETARY_OF_RE.search(text):
        return "state_secretary"

    # Adviser / member
    if _ADVISER_MEMBER_RE.search(text):
        return "adviser_member"

    # Campaign participant
    if _CAMPAIGN_RE2.search(text):
        return "campaign_participant"

    # Joined
    if _JOINED_RE.search(text):
        return "joined"

    return "other"


# ---------------------------------------------------------------------------
# Load and filter
# ---------------------------------------------------------------------------

df    = pd.read_csv(PARSED_POSITIONS_CSV)
party = df[df["field_type"] == "party_positions"].copy().reset_index(drop=True)

cols = [
    "record_id", "person_id", "person_name",
    "role_text_raw", "role_text",
    "position_title",
    "organization",
    "state",
    "year_start", "year_end",
    "birth_date_clean", "birth_date_precision",
]
party = party[cols]

# record_type doesn't depend on organization so compute it once here
party["record_type"] = party["role_text_raw"].map(classify_record_type)

# years_in_post doesn't depend on organization either
party["years_in_post"] = (
    (party["year_end"] - party["year_start"])
    .where(party["year_start"].notna() & party["year_end"].notna())
    .clip(lower=0)
)

# ---------------------------------------------------------------------------
# GPT fallback — fill missing organization via OpenAI API
# ---------------------------------------------------------------------------

_BATCH_SIZE = 20

_SYSTEM_PROMPT = (
    "You extract structured data from Mexican political party biography entries (1920-2000). "
    "Each entry describes one position held by a Mexican politician within a party or political organization. "
    "For each numbered entry return a JSON object inside a 'results' array with:\n"
    "  'organization': the party or intra-party body "
    "(e.g. 'PRI', 'CEN of PRI', 'IEPES of PRI', 'State Committee of PAN', 'PDM'). Return null if none is identifiable.\n"
    "  'position_title': the person's role or title (e.g. 'Secretary-General', 'President', 'Delegate'). "
    "Return null if unclear.\n"
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


missing_mask = party["organization"].isna()
print(f"\n{missing_mask.sum()} records have no organization after regex extraction.")

party["org_gpt"]            = None
party["position_title_gpt"] = None

if missing_mask.any():
    api_key = getpass.getpass("Enter your OpenAI API key: ")
    print(f"Running GPT (gpt-4o-mini) on {missing_mask.sum()} records...")
    gpt_results = gpt_fill_missing(party.loc[missing_mask, "role_text_raw"], api_key)

    party.loc[missing_mask, "org_gpt"]            = gpt_results["organization"]
    party.loc[missing_mask, "position_title_gpt"] = gpt_results["position_title"]

    party["organization"]  = party["organization"].fillna(party["org_gpt"])
    party["position_title"] = party["position_title"].fillna(party["position_title_gpt"])

    filled_org   = party.loc[missing_mask, "organization"].notna().sum()
    filled_title = party.loc[missing_mask, "position_title"].notna().sum()
    print(f"  GPT filled {filled_org} organizations and {filled_title} position titles")

# Recompute derived variables now that organization is more complete
party["party"]       = party.apply(
    lambda r: classify_party(r["organization"], r["role_text_raw"]), axis=1
)
party["pri_lineage"] = party["party"].isin(_PRI_LINEAGE)
party["party_body"]  = party.apply(
    lambda r: classify_body(r["organization"], r["role_text_raw"]), axis=1
)
party["party_level"] = party.apply(
    lambda r: classify_party_level(r["party_body"], r["state"], r["role_text_raw"] or ""), axis=1
)
party["party_rank"]  = party.apply(
    lambda r: classify_party_rank(r["role_text_raw"], r["party_body"], r["party_level"]), axis=1
)

# ---------------------------------------------------------------------------
# Save long format
# ---------------------------------------------------------------------------

party.to_csv(PARTY_POSITIONS_CSV, index=False)

print(f"Party position records: {len(party)}")
print(f"\nParty distribution:")
print(party["party"].value_counts().head(15).to_string())
print(f"\nParty body distribution:")
print(party["party_body"].value_counts().head(15).to_string())
print(f"\nParty level distribution:")
print(party["party_level"].value_counts().to_string())
print(f"\nRecord type distribution:")
print(party["record_type"].value_counts().to_string())
print(f"\nParty rank distribution:")
print(party["party_rank"].value_counts().head(15).to_string())

# ---------------------------------------------------------------------------
# Wide format — one row per person
# ---------------------------------------------------------------------------

_NATIONAL_LEADER_RANKS = {
    "national_president", "secretary_general_nat", "cen_president",
    "cen_secretary", "iepes_director",
}
_CEN_RANKS = {
    "cen_president", "cen_secretary", "cen_member", "national_delegate",
    "secretary_general_nat",
}
_STATE_PRESIDENT_RANKS = {"state_president"}


def _best_rank(ranks: pd.Series) -> Optional[str]:
    valid = [r for r in ranks if isinstance(r, str)]
    if not valid:
        return None
    return min(valid, key=lambda r: _RANK_ORDER.get(r, 99))


def make_wide(party: pd.DataFrame) -> pd.DataFrame:
    active = party[party["record_type"] == "active_position"]

    def agg(sub):
        ranks        = sub["party_rank"]
        parties      = sub["party"].dropna().unique().tolist()
        party_counts = sub["party"].value_counts()
        primary      = party_counts.index[0] if len(party_counts) else None
        active_sub   = sub[sub["record_type"] == "active_position"]

        return pd.Series({
            "birth_date_clean":       sub["birth_date_clean"].iloc[0],
            "birth_date_precision":   sub["birth_date_precision"].iloc[0],
            "primary_party":          primary,
            "n_parties":              sub["party"].nunique(),
            "parties_all":            "|".join(sorted(set(p for p in parties if p))),
            "pri_member":             int(sub["pri_lineage"].any()),
            "pan_member":             int((sub["party"] == "PAN").any()),
            "prd_member":             int((sub["party"] == "PRD").any()),
            "n_party_positions":      len(sub),
            "n_active_positions":     len(active_sub),
            "first_party_year":       sub["year_start"].min(),
            "last_party_year":        sub["year_end"].max(),
            "ever_national_leader":   int(ranks.isin(_NATIONAL_LEADER_RANKS).any()),
            "ever_cen":               int(ranks.isin(_CEN_RANKS).any()),
            "ever_state_president":   int(ranks.isin(_STATE_PRESIDENT_RANKS).any()),
            "highest_party_rank":     _best_rank(ranks),
        })

    wide = (
        party.groupby(["person_id", "person_name"], sort=False)
        .apply(agg)
        .reset_index()
    )
    return wide


wide = make_wide(party)
wide.to_csv(PARTY_POSITIONS_WIDE_CSV, index=False)

print(f"\nWide format: {len(wide)} persons")
print(f"  Primary party PRI/PNR/PRM: {(wide['pri_member'] == 1).sum()}")
print(f"  Primary party PAN:         {(wide['pan_member'] == 1).sum()}")
print(f"  Primary party PRD:         {(wide['prd_member'] == 1).sum()}")
print(f"  Ever national leader:      {wide['ever_national_leader'].sum()}")
print(f"  Ever CEN:                  {wide['ever_cen'].sum()}")
print(f"  Ever state president:      {wide['ever_state_president'].sum()}")
print(f"\nHighest party rank distribution:")
print(wide["highest_party_rank"].value_counts().head(15).to_string())
print(f"\nSaved long:  {PARTY_POSITIONS_CSV}")
print(f"Saved wide:  {PARTY_POSITIONS_WIDE_CSV}")
