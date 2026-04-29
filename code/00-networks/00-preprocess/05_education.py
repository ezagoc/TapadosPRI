"""
Build the education dataset from parsed_positions.csv.

Step 1 — classify each record into one of four types:
  - degree        : a credential or studies received
  - academic_role : employment at an academic institution
  - pre_university: elementary, secondary, or preparatory schooling
  - unknown       : no degree, self-educated, or uninformative text

Step 2 — for 'degree' records, extract:
  - degree_level  : phd / masters / specialization / diploma / certificate / undergraduate
  - degree_field  : law / economics / engineering / medicine / business / military /
                    education / political_sci / agronomy / architecture / science /
                    sociology / humanities / other
  - foreign_degree: True / False / None

Step 3 — NER fallback: for records still missing an organization after regex
  extraction, run spaCy NER on the raw text and take the best ORG entity.

Step 4 — collapse to wide format (one row per person) with dummy variables.
  All columns are 0/1 dummies except `institution` (string).

Outputs:
  data/education.csv       — long format (one row per record)
  data/education_wide.csv  — wide format (one row per person)
"""

import re
from typing import Optional
import pandas as pd
import spacy
from config import PARSED_POSITIONS_CSV, EDUCATION_CSV, EDUCATION_WIDE_CSV

# ---------------------------------------------------------------------------
# Step 1: record-type classification
# ---------------------------------------------------------------------------

_UNKNOWN_RE = re.compile(
    r"no degree|no formal education|early education\s*unknown|education unknown"
    r"|never taught|primarily self.?educated|self.?educated|no further education"
    r"|left school|career educator|did not learn",
    re.IGNORECASE,
)

_ACADEMIC_ROLE_RE = re.compile(
    r"\b(professor|director|dean|rector|instructor|teacher|coordinator|researcher"
    r"|aide|adviser|founding|chair|chairperson|administrator|founder|cofounder"
    r"|associate|lecturer|inspector|technician|hygienist|analyst|consultant"
    r"|head|pilot|anesthesiologist|ophthalmologist|attorney|counsel|representative"
    r"|investigator|schoolteacher|official)\b"
    r"|secretary[\s,]|secretarygeneral|secretary-general"
    r"|\bmember\s*[,of]"
    r"|\bpresident\s*,",
    re.IGNORECASE,
)

_PRE_UNIVERSITY_RE = re.compile(
    r"\b(elementary|primary|secondary|preparatory|kindergarten)\b"
    r"|\b\d(st|nd|rd|th).*(grade|year of school)\b"
    r"|\b(grade|grades)\s+at\b",
    re.IGNORECASE,
)

_DEGREE_RE = re.compile(
    r"\b(degree|phd|ph\.d|doctoral|doctorate|master|postgraduate|post-graduate"
    r"|graduate|studies|study|enrolled|student|courses?|diploma|diplomas"
    r"|specialization|specialist|licenciatura|fellow|fellowship|graduated|graduating"
    r"|studied|attended|credential|certificate|certification|specialty"
    r"|cadet|normal|bachelor|semesters?|training|residency|resident|intern"
    r"|scholarship|scholar|seminar|program|vocational|staff and command)\b"
    r"|\b(ba|bs|md|lld|llb|mpa|mba|llm|scd|cpa)\b"
    r"|\bm\.?[as]\.?\b",
    re.IGNORECASE,
)


def classify_record(text: str) -> str:
    if not isinstance(text, str) or not text.strip():
        return "unknown"
    if _UNKNOWN_RE.search(text):
        return "unknown"
    if _ACADEMIC_ROLE_RE.search(text):
        return "academic_role"
    if _PRE_UNIVERSITY_RE.search(text):
        return "pre_university"
    if _DEGREE_RE.search(text):
        return "degree"
    return "other"


# ---------------------------------------------------------------------------
# Step 2a: degree level
# Priority: phd > masters > specialization > diploma > certificate > undergraduate
# ---------------------------------------------------------------------------

_LEVEL_PATTERNS = [
    ("phd", re.compile(
        r"\b(phd|ph\.d|doctoral|doctorate|doctor of|scd|lld|postdoctoral|postdoc)\b",
        re.IGNORECASE,
    )),
    ("masters", re.compile(
        r"\b(master|postgraduate|post-graduate|graduate work|graduate studi|mba|mpa|llm)\b"
        r"|\bm[.\s]?[as][.\s]?\b",
        re.IGNORECASE,
    )),
    ("specialization", re.compile(
        r"\b(specialization|specialist|specialty|residency|resident|fellow|fellowship)\b",
        re.IGNORECASE,
    )),
    ("diploma", re.compile(
        r"\b(diploma|diplomas|staff and command|command studi|command train)\b",
        re.IGNORECASE,
    )),
    ("certificate", re.compile(
        r"\b(certificate|certification|credential|cpa|licensed|normal school|normal cert"
        r"|teaching cert|teaching certificate|normal)\b",
        re.IGNORECASE,
    )),
]


def extract_degree_level(text: str) -> Optional[str]:
    if not isinstance(text, str):
        return None
    for level, pat in _LEVEL_PATTERNS:
        if pat.search(text):
            return level
    return "undergraduate"


# ---------------------------------------------------------------------------
# Step 2b: degree field
# ---------------------------------------------------------------------------

_FIELD_PATTERNS = [
    ("law", re.compile(
        r"\b(law|legal|jurisprudence|llb|lld|jd\b|criminolog|notary|judicial|amparo)\b",
        re.IGNORECASE,
    )),
    ("economics", re.compile(
        r"\b(economics?|economic|econometrics?|finance|financial|actuari"
        r"|political economy|fiscal)\b",
        re.IGNORECASE,
    )),
    ("medicine", re.compile(
        r"\b(medicine|medical|surgery|surgical|pediatric|cardiology|urology|pathology"
        r"|dental|dentist|nursing|public health|ophthalmol|anesthesi|orthoped"
        r"|radiol|neurology|psychiatr|gynecol|obstet|biochem|epidemiol)\b",
        re.IGNORECASE,
    )),
    ("engineering", re.compile(
        r"\b(engineering|mechanical|electrical|civil eng|construction|systems eng"
        r"|industrial eng|operations research|aeronautical eng|chemical eng|computer)\b",
        re.IGNORECASE,
    )),
    ("business", re.compile(
        r"\b(business|administration|accounting|accountant|commerce|management"
        r"|mba\b|cpa\b|banking|industrial relations|higher management)\b",
        re.IGNORECASE,
    )),
    ("military", re.compile(
        r"\b(military|war college|staff and command|aeronautic|naval|aviation"
        r"|artillery|infantry|cadet|national security|defense|army|marines)\b",
        re.IGNORECASE,
    )),
    ("education", re.compile(
        r"\b(education|pedagog|teaching|normal school|normal cert|didactic)\b",
        re.IGNORECASE,
    )),
    ("political_sci", re.compile(
        r"\b(political science|political and social|public admin|governance"
        r"|public policy|international relations|diplomacy|social sciences)\b",
        re.IGNORECASE,
    )),
    ("agronomy", re.compile(
        r"\b(agronomy|agriculture|agricultural|veterinar|zootechn|forestry|rural)\b",
        re.IGNORECASE,
    )),
    ("architecture", re.compile(
        r"\b(architecture|architect|urban planning|urban design)\b",
        re.IGNORECASE,
    )),
    ("science", re.compile(
        r"\b(physics|chemistry|biology|mathematics|math\b|zoology|botany"
        r"|biochemistry|sciences?\b|natural science|exact science)\b",
        re.IGNORECASE,
    )),
    ("sociology", re.compile(
        r"\b(sociology|social science|anthropolog|demograph|social work"
        r"|latin american studies|area studies|psychology)\b",
        re.IGNORECASE,
    )),
    ("humanities", re.compile(
        r"\b(philosophy|history|literature|language|linguistics|journalism"
        r"|communications?|arts\b|music|theology|religion|letters)\b",
        re.IGNORECASE,
    )),
]


def extract_degree_field(text: str) -> Optional[str]:
    if not isinstance(text, str):
        return None
    for field, pat in _FIELD_PATTERNS:
        if pat.search(text):
            return field
    return "other"


# ---------------------------------------------------------------------------
# Step 2c: foreign degree
# Built from the same university list in 04_parse_positions.py + additions.
# Checks both role_text_raw and organization.
# ---------------------------------------------------------------------------

_FOREIGN_UNIV_RE = re.compile(
    r"\b("
    # United States — from 04_parse_positions.py
    r"Harvard|Yale|MIT\b|Stanford|Columbia University|Princeton|Georgetown"
    r"|Victoria University|American University"
    # United States — additions
    r"|New York University|NYU\b|University of Chicago|UCLA\b"
    r"|University of California|University of Michigan|Johns Hopkins"
    r"|Northwestern University|University of Pennsylvania|Wharton"
    r"|University of Texas|LBJ School|University of Pittsburgh"
    r"|Notre Dame|Iowa State|Duke University|Vanderbilt|Tulane"
    r"|George Washington University|Woodrow Wilson|Kennedy School"
    r"|Mason Program|Cornell University|Rockefeller|Fulbright"
    r"|University of Southern California|University of Arizona"
    r"|University of Florida|Indiana University|University of Virginia"
    r"|University of Wisconsin|University of Minnesota|Ohio State"
    # United Kingdom — from 04_parse_positions.py
    r"|Oxford|Cambridge University|London School"
    # United Kingdom — additions
    r"|University of Essex|King.s College|Imperial College|Edinburgh"
    # France
    r"|University of Paris|Sorbonne|Sciences Po|Colegio de Francia"
    # Germany
    r"|University of Berlin|University of Turingia|University of Frankfurt"
    r"|University of Cologne|University of Hamburg"
    # Italy
    r"|University of Rome|Gregorian Pontifical|Salesian Pontifical"
    r"|University of Bologna|University of Naples"
    # Spain
    r"|Polytechnic of Madrid|Ortega y Gasset University|University of Madrid"
    r"|Complutense|Autonomous University of Madrid"
    # Other Europe & Latin America
    r"|University of Vienna|University of Geneva|University of Brussels"
    r"|University of Cuyo|University of Buenos Aires|University of Chile"
    r"|University of Argentina|University of Rosario|Canal Zone"
    r")\b",
    re.IGNORECASE,
)

# Known Mexican institutions — presence means NOT a foreign degree
_MEXICAN_UNIV_RE = re.compile(
    r"\b(UNAM|IPN\b|ITAM\b|ITESM\b|CIDE\b|IPADE\b|CEMLA\b"
    r"|Colegio de Mexico|Ibero-American University"
    r"|National Polytechnic|National School|Free Law School"
    r"|Heroic Military College|Higher War College|Military Medical School"
    r"|University of Guadalajara|University of Michoacan|University of Puebla"
    r"|University of Guanajuato|University of Veracruz|University of Yucatan"
    r"|University of Sinaloa|University of Sonora|University of Colima"
    r"|University of Chihuahua|University of Coahuila|University of Tamaulipas"
    r"|University of Tabasco|University of Oaxaca|University of Guerrero"
    r"|University of Hidalgo|University of Zacatecas|University of Nayarit"
    r"|University of Durango|University of Aguascalientes"
    r"|University of Queretaro|University of San Luis Potosi"
    r"|University of Baja California|University of the Valley of Mexico"
    r"|Autonomous University|Autonomous Metropolitan|Benito Juarez University"
    r"|Juarez University|Juarez Institute|Pan American University"
    r"|La Salle University|Anahuac University|Intercontinental University"
    r"|Popular Autonomous University|Colegio de San Nicolas"
    r"|Technological Institute|Applied Military School|Naval College"
    r"|Center for Higher Naval|National Defense College)\b",
    re.IGNORECASE,
)


def is_foreign_degree(text: str, org: str) -> Optional[bool]:
    combined = " ".join(x for x in [str(text), str(org)] if x and x != "nan")
    if _FOREIGN_UNIV_RE.search(combined) and not _MEXICAN_UNIV_RE.search(combined):
        return True
    if _MEXICAN_UNIV_RE.search(combined):
        return False
    return None


# ---------------------------------------------------------------------------
# Step 3: NER fallback for null organizations
# ---------------------------------------------------------------------------

_NER_STOP = {
    "ma", "ms", "ba", "bs", "phd", "un", "lld", "llb", "mba", "mpa", "llm",
    "magna cum laude", "summa cum laude", "cum laude",
}

_INST_KW_RE = re.compile(
    r"\b(university|school|college|institute|academy|polytechnic|seminary"
    r"|center|centre|authority|foundation|colegio|escuela)\b",
    re.IGNORECASE,
)


def ner_extract_org(texts: pd.Series, nlp) -> pd.Series:
    """
    Run spaCy NER on each text and return the best ORG entity.
    Prefers entities that contain institution keywords; also catches
    known universities mis-tagged as GPE (e.g. Sorbonne).
    Only processes non-null texts.
    """
    results = pd.Series([None] * len(texts), index=texts.index)

    valid_mask = texts.notna() & (texts.str.strip() != "")
    valid_texts = texts[valid_mask].tolist()
    valid_idx   = texts[valid_mask].index.tolist()

    for idx, doc in zip(valid_idx, nlp.pipe(valid_texts, batch_size=64)):
        orgs = []
        gpe_unis = []
        for ent in doc.ents:
            text = ent.text.strip()
            if len(text) < 4 or text.lower() in _NER_STOP:
                continue
            if ent.label_ == "ORG":
                orgs.append(text)
            elif ent.label_ == "GPE" and _FOREIGN_UNIV_RE.search(text):
                # Universities mis-tagged as locations (e.g. Sorbonne)
                gpe_unis.append(text)

        # Prefer ORGs that look like institutions; then any ORG; then GPE-unis
        inst_orgs = [o for o in orgs if _INST_KW_RE.search(o)]
        if inst_orgs:
            results[idx] = inst_orgs[0]
        elif orgs:
            results[idx] = orgs[0]
        elif gpe_unis:
            results[idx] = gpe_unis[0]

    return results


# ---------------------------------------------------------------------------
# Step 4: collapse to wide format (one row per person)
# ---------------------------------------------------------------------------

_DEGREE_LEVELS = ["undergraduate", "masters", "phd", "specialization", "diploma", "certificate"]
_DEGREE_FIELDS = [
    "law", "economics", "engineering", "medicine", "business",
    "military", "education", "political_sci", "agronomy",
    "architecture", "science", "sociology", "humanities",
]


def pick_institution(deg: pd.DataFrame) -> Optional[str]:
    """Return the institution of the highest-level degree, preferring non-null orgs."""
    for level in ["phd", "masters", "specialization", "diploma", "undergraduate", "certificate"]:
        rows = deg[deg["degree_level"] == level]
        orgs = rows["organization"].dropna()
        if not orgs.empty:
            return orgs.iloc[0]
    orgs = deg["organization"].dropna()
    return orgs.iloc[0] if not orgs.empty else None


def make_wide(edu: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for pid, grp in edu.groupby("person_id", sort=False):
        r = {
            "person_id":            pid,
            "person_name":          grp["person_name"].iloc[0],
            "birth_date_clean":     grp["birth_date_clean"].iloc[0],
            "birth_date_precision": grp["birth_date_precision"].iloc[0],
        }

        # Record-type dummies
        types = grp["record_type"]
        r["pre_university"]   = int((types == "pre_university").any())
        r["academic_role_edu"] = int((types == "academic_role").any())

        # Degree records
        deg = grp[grp["record_type"] == "degree"]
        r["has_degree"] = int(len(deg) > 0)

        # Degree level dummies
        for lvl in _DEGREE_LEVELS:
            r[lvl] = int((deg["degree_level"] == lvl).any())

        # Degree field dummies
        for fld in _DEGREE_FIELDS:
            r[fld] = int((deg["degree_field"] == fld).any())

        # Foreign degree dummy
        r["foreign_degree"] = int(deg["foreign_degree"].eq(True).any())

        # Institution (string — highest-level degree institution)
        r["institution"] = pick_institution(deg)

        rows.append(r)

    col_order = (
        ["person_id", "person_name", "birth_date_clean", "birth_date_precision"]
        + ["pre_university", "academic_role_edu", "has_degree"]
        + _DEGREE_LEVELS
        + _DEGREE_FIELDS
        + ["foreign_degree", "institution"]
    )
    return pd.DataFrame(rows)[col_order]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

df = pd.read_csv(PARSED_POSITIONS_CSV)
edu = df[df["field_type"] == "education"].copy().reset_index(drop=True)

cols = [
    "record_id", "person_id", "person_name",
    "role_text_raw", "role_text",
    "organization", "state",
    "year_start", "year_end",
    "birth_date_clean", "birth_date_precision",
]
edu = edu[cols]

# Step 1
edu["record_type"] = edu["role_text_raw"].apply(classify_record)

# Step 2
is_degree = edu["record_type"] == "degree"
edu["degree_level"]   = None
edu["degree_field"]   = None
edu["foreign_degree"] = None

edu.loc[is_degree, "degree_level"] = (
    edu.loc[is_degree, "role_text_raw"].apply(extract_degree_level)
)
edu.loc[is_degree, "degree_field"] = (
    edu.loc[is_degree, "role_text_raw"].apply(extract_degree_field)
)
edu.loc[is_degree, "foreign_degree"] = edu.loc[is_degree].apply(
    lambda r: is_foreign_degree(r["role_text_raw"], r["organization"]), axis=1
)

# Step 3: NER fallback for null organizations
print("Running NER on null-organization records...")
nlp = spacy.load("en_core_web_sm", disable=["tagger", "parser", "lemmatizer"])
null_org_mask = edu["organization"].isna() & edu["role_text_raw"].notna()
ner_results = ner_extract_org(edu.loc[null_org_mask, "role_text_raw"], nlp)
edu.loc[null_org_mask, "organization"] = ner_results
filled = ner_results.notna().sum()
print(f"  NER filled {filled} / {null_org_mask.sum()} null organizations")

# Step 4
wide = make_wide(edu)

# ---------------------------------------------------------------------------
# Save both formats
# ---------------------------------------------------------------------------
edu.to_csv(EDUCATION_CSV, index=False)
wide.to_csv(EDUCATION_WIDE_CSV, index=False)

# --- Summary ---
print(f"Education records (long):  {len(edu)}")
print(f"Persons (wide):            {len(wide)}")

deg = edu[is_degree]
print(f"\nRecord type breakdown:")
for rt, cnt in edu["record_type"].value_counts().items():
    print(f"  {rt:15s}: {cnt:5d}  ({100*cnt/len(edu):.1f}%)")

print(f"\nDegree level  ({len(deg)} degree records):")
for lvl, cnt in deg["degree_level"].value_counts().items():
    print(f"  {lvl:15s}: {cnt:5d}  ({100*cnt/len(deg):.1f}%)")

print(f"\nDegree field:")
for fld, cnt in deg["degree_field"].value_counts().items():
    print(f"  {fld:15s}: {cnt:5d}  ({100*cnt/len(deg):.1f}%)")

foreign = deg["foreign_degree"]
print(f"\nForeign degree: True={foreign.sum()}, False={(foreign==False).sum()}, Unknown={foreign.isna().sum()}")

print(f"\nWide format dummy means (share of persons with each variable):")
dummy_cols = [c for c in wide.columns if c not in ("person_id", "person_name", "birth_date_clean", "birth_date_precision", "institution")]
for col in dummy_cols:
    print(f"  {col:20s}: {wide[col].mean():.3f}")

print(f"\nNull orgs remaining after NER: {edu['organization'].isna().sum()}")
print(f"\nSaved long  -> {EDUCATION_CSV}")
print(f"Saved wide  -> {EDUCATION_WIDE_CSV}")
