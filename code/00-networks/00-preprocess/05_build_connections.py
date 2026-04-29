"""
Build connections between presidential candidates (corcholatas) and other politicians.

Uses parsed_positions.csv for temporal co-location and biographies.csv personal_info
for explicit relationship mentions.

Output: data/parsed_connections.csv
"""

import re
from typing import Optional
from collections import defaultdict
from pathlib import Path
import sys
import pandas as pd

CODE_DIR = Path(__file__).resolve().parents[2]
if str(CODE_DIR) not in sys.path:
    sys.path.append(str(CODE_DIR))

from config import (
    BIOGRAPHIES_CSV,
    PARSED_POSITIONS_CSV,
    PARSED_CONNECTIONS_CSV,
    CORCHOLATAS_XLSX,
    normalize_name,
    clean_text,
)

# ---------------------------------------------------------------------------
# Relationship patterns for personal_info field
# ---------------------------------------------------------------------------
FAMILY_PATTERNS = [
    (r"(?:son|daughter)\s+of\s+([^,;]+)", "family"),
    (r"(?:brother|sister)\s+(?:of\s+)?([^,;]+)", "family"),
    (r"married\s+([^,;]+)", "family"),
    (r"(?:nephew|niece)\s+of\s+([^,;]+)", "family"),
    (r"(?:uncle|aunt)\s+([^,;]+)", "family"),
    (r"(?:cousin)\s+(?:of\s+)?([^,;]+)", "family"),
    (r"(?:father|mother)-in-law\s+(?:of\s+)?([^,;]+)", "family"),
    (r"(?:son-in-law|daughter-in-law)\s+(?:of\s+)?([^,;]+)", "family"),
    (r"(?:grandson|granddaughter)\s+(?:of\s+)?([^,;]+)", "family"),
    (r"(?:grandfather|grandmother)\s+([^,;]+)", "family"),
]

MENTORSHIP_PATTERNS = [
    (r"student\s+of\s+([^,;]+)", "mentorship"),
    (r"student\s+with\s+([^,;]+)", "mentorship"),
    (r"studied\s+(?:under|with)\s+([^,;]+)", "mentorship"),
    (r"(?:protégé|protege)\s+of\s+([^,;]+)", "mentorship"),
    (r"(?:political\s+)?(?:patron|mentor)\s+(?:was\s+)?([^,;]+)", "mentorship"),
    (r"(?:political\s+)?(?:patrons?\s+included)\s+([^,;]+)", "mentorship"),
    (r"disciple\s+of\s+([^,;]+)", "mentorship"),
    (r"adviser\s+to\s+([^,;]+)", "mentorship"),
]

PERSONAL_PATTERNS = [
    (r"(?:close\s+)?friend(?:s)?\s+(?:of|with|included)\s+([^,;]+)", "personal"),
    (r"close\s+friends?\s+with\s+([^,;]+)", "personal"),
    (r"came\s+in\s+contact\s+with\s+([^,;]+)", "personal"),
]

ALL_PATTERNS = FAMILY_PATTERNS + MENTORSHIP_PATTERNS + PERSONAL_PATTERNS


def build_name_index(bio_df: pd.DataFrame) -> dict:
    """Build a lookup from normalized name tokens to full CSV names."""
    index = defaultdict(list)
    # Common stop words that should not be used as index keys
    stop_words = {"de", "la", "del", "el", "los", "las", "y", "e"}
    for name in bio_df["name"]:
        normalized = normalize_name(name)
        parts = normalized.split()
        if parts:
            # Index by first token (primary last name)
            index[parts[0]].append(name)
            # Index by first two tokens for compound names
            if len(parts) > 1:
                index[f"{parts[0]} {parts[1]}"].append(name)
            # Index by ALL significant tokens (len >= 3, not stop words)
            # This ensures names like "de la Madrid" are findable via "madrid"
            for p in parts:
                if len(p) >= 3 and p not in stop_words:
                    if name not in index[p]:
                        index[p].append(name)
            # Index by consecutive pairs of significant tokens
            for i in range(len(parts) - 1):
                bigram = f"{parts[i]} {parts[i+1]}"
                if name not in index.get(bigram, []):
                    index[bigram].append(name)
    return dict(index)


def fuzzy_match_name(mentioned_name: str, name_index: dict) -> Optional[str]:
    """
    Try to match a mentioned name from personal_info to a person in biographies.csv.
    Returns the CSV name or None.
    """
    mentioned = normalize_name(mentioned_name)
    parts = mentioned.split()
    if not parts:
        return None

    # Try matching by last name (first word of mentioned name is often a first name,
    # but in the personal_info text, format varies)
    # Strategy: try each word as a potential last name and check the index
    candidates = []
    for i, word in enumerate(parts):
        if len(word) < 3:
            continue
        matches = name_index.get(word, [])
        for m in matches:
            # Check if other parts of the mentioned name appear in the match
            m_norm = normalize_name(m)
            overlap = sum(1 for p in parts if p in m_norm and len(p) > 2)
            if overlap >= 2 or (overlap >= 1 and len(parts) <= 2):
                candidates.append((m, overlap))

    if candidates:
        # Return best match
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]

    return None


def extract_personal_connections(bio_df: pd.DataFrame, target_names: set) -> list:
    """
    Extract explicit relationship mentions from personal_info for target persons.
    """
    name_index = build_name_index(bio_df)
    connections = []

    for _, row in bio_df.iterrows():
        name = row["name"]
        if name not in target_names:
            continue

        info = row.get("personal_info", "")
        if not isinstance(info, str) or not info.strip():
            continue

        info = clean_text(info)

        for pattern, conn_type in ALL_PATTERNS:
            for match in re.finditer(pattern, info, re.IGNORECASE):
                mentioned_raw = match.group(1).strip()
                # Clean up the mentioned name — take only the personal name part
                # Remove trailing role descriptions
                mentioned_clean = re.split(
                    r"\s+(?:who|was|is|secretary|director|governor|president|senator|federal|head|mayor|former)",
                    mentioned_raw,
                    flags=re.IGNORECASE,
                )[0].strip()

                if len(mentioned_clean) < 4:
                    continue

                matched = fuzzy_match_name(mentioned_clean, name_index)
                if matched and matched != name:
                    connections.append({
                        "person_a": name,
                        "person_b": matched,
                        "connection_type": conn_type,
                        "detail": mentioned_raw[:100],
                        "shared_state": None,
                        "year_start": None,
                        "year_end": None,
                    })

    return connections


def extract_colocation_connections(
    positions_df: pd.DataFrame,
    target_names: set,
) -> list:
    """
    Find people who shared the same organization at the same time as targets.
    Primary: match by (organization, field_type) + overlapping years.
    Fallback: match by (state, field_type) + overlapping years when org is None.
    """
    connections = []

    # Filter to records with years
    pos = positions_df.dropna(subset=["year_start"]).copy()
    pos["year_start"] = pos["year_start"].astype(int)
    pos["year_end"] = pos["year_end"].fillna(pos["year_start"]).astype(int)

    # Split into target and other positions
    target_pos = pos[pos["person_name"].isin(target_names)]
    other_pos = pos[~pos["person_name"].isin(target_names)]

    field_to_conn = {
        "govt_positions": "shared_government",
        "education": "shared_education",
        "party_positions": "shared_party",
        "public_positions": "shared_public_office",
        "labor_positions": "shared_labor",
        "other_positions": "shared_other",
    }

    seen = set()

    # --- Primary: organization-based matching ---
    # Group other positions by (organization, field_type)
    other_by_org = defaultdict(list)
    for _, r in other_pos.iterrows():
        if r["field_type"] == "birthplace":
            continue
        org = r.get("organization")
        if isinstance(org, str) and len(org) >= 3:
            key = (org, r["field_type"])
            other_by_org[key].append(r)

    for _, tp in target_pos.iterrows():
        if tp["field_type"] == "birthplace":
            continue
        org = tp.get("organization")
        if not isinstance(org, str) or len(org) < 3:
            continue

        key = (org, tp["field_type"])
        candidates = other_by_org.get(key, [])

        for op in candidates:
            overlap_start = max(tp["year_start"], op["year_start"])
            overlap_end = min(tp["year_end"], op["year_end"])

            if overlap_start <= overlap_end:
                pair_key = (tp["person_name"], op["person_name"], tp["field_type"], org)
                if pair_key in seen:
                    continue
                seen.add(pair_key)

                conn_type = field_to_conn.get(tp["field_type"], "shared_other")
                shared_state = tp.get("state") if tp.get("state") == op.get("state") else None

                connections.append({
                    "person_a": tp["person_name"],
                    "person_b": op["person_name"],
                    "connection_type": conn_type,
                    "detail": f"[{org}] {tp['role_text'][:50]} | {op['role_text'][:50]}",
                    "shared_state": shared_state,
                    "year_start": int(overlap_start),
                    "year_end": int(overlap_end),
                })

    # --- Fallback: state-based matching for records without organization ---
    other_by_state = defaultdict(list)
    for _, r in other_pos.iterrows():
        if r["field_type"] == "birthplace":
            continue
        org = r.get("organization")
        state = r.get("state")
        # Only use state fallback when org is missing AND state is present
        if (not isinstance(org, str) or len(org) < 3) and isinstance(state, str):
            key = (state, r["field_type"])
            other_by_state[key].append(r)

    for _, tp in target_pos.iterrows():
        if tp["field_type"] == "birthplace":
            continue
        org = tp.get("organization")
        state = tp.get("state")
        if isinstance(org, str) and len(org) >= 3:
            continue  # already handled by org-based matching
        if not isinstance(state, str):
            continue

        key = (state, tp["field_type"])
        candidates = other_by_state.get(key, [])

        for op in candidates:
            overlap_start = max(tp["year_start"], op["year_start"])
            overlap_end = min(tp["year_end"], op["year_end"])

            if overlap_start <= overlap_end:
                pair_key = (tp["person_name"], op["person_name"], tp["field_type"], state)
                if pair_key in seen:
                    continue
                seen.add(pair_key)

                conn_type = field_to_conn.get(tp["field_type"], "shared_other")

                connections.append({
                    "person_a": tp["person_name"],
                    "person_b": op["person_name"],
                    "connection_type": conn_type,
                    "detail": f"[state:{state}] {tp['role_text'][:50]} | {op['role_text'][:50]}",
                    "shared_state": state,
                    "year_start": int(overlap_start),
                    "year_end": int(overlap_end),
                })

    return connections


def extract_birthplace_connections(
    bio_df: pd.DataFrame,
    positions_df: pd.DataFrame,
    target_names: set,
) -> list:
    """Find contemporaries from the same birthplace state."""
    connections = []

    # Get birthplace data
    bp = positions_df[positions_df["field_type"] == "birthplace"].dropna(subset=["state"])
    bp_by_state = defaultdict(list)
    for _, r in bp.iterrows():
        bp_by_state[r["state"]].append(r["person_name"])

    # Get birth years from biographies
    birth_years = {}
    for _, row in bio_df.iterrows():
        bd = row.get("birth_date", "")
        if isinstance(bd, str):
            years = re.findall(r"\b(1[89]\d{2}|20\d{2})\b", bd)
            if years:
                birth_years[row["name"]] = int(years[-1])

    seen = set()
    for target in target_names:
        target_bp_state = None
        target_birth = birth_years.get(target)
        if not target_birth:
            continue

        for _, r in bp[bp["person_name"] == target].iterrows():
            target_bp_state = r["state"]

        if not target_bp_state:
            continue

        for other in bp_by_state.get(target_bp_state, []):
            if other == target or other in target_names:
                continue
            other_birth = birth_years.get(other)
            if not other_birth:
                continue
            if abs(target_birth - other_birth) <= 10:
                pair_key = (target, other)
                if pair_key in seen:
                    continue
                seen.add(pair_key)

                connections.append({
                    "person_a": target,
                    "person_b": other,
                    "connection_type": "birthplace_contemporary",
                    "detail": f"Same state: {target_bp_state}, born {target_birth} / {other_birth}",
                    "shared_state": target_bp_state,
                    "year_start": min(target_birth, other_birth),
                    "year_end": max(target_birth, other_birth),
                })

    return connections


def get_target_names(bio_df: pd.DataFrame, election_year: int = 1988) -> set:
    """Get the target candidate names for a given election year."""
    # Load corcholatas
    corch = pd.read_excel(CORCHOLATAS_XLSX, header=1)
    corch_names = corch[corch["Elección"] == election_year]["Nombre"].tolist()

    # Match corcholata names to biographies.csv names
    name_index = build_name_index(bio_df)
    matched = set()

    for cn in corch_names:
        # Clean checkmark
        cn_clean = cn.replace("✓", "").strip()
        result = fuzzy_match_name(cn_clean, name_index)
        if result:
            matched.add(result)
            print(f"  Matched: {cn_clean} -> {result}")
        else:
            print(f"  NO MATCH: {cn_clean}")

    return matched


def build_all_connections(election_year: int = 1988, output_path=None):
    """Build connections for a given election year."""
    print("Loading data...")
    bio_df = pd.read_csv(BIOGRAPHIES_CSV)
    pos_df = pd.read_csv(PARSED_POSITIONS_CSV)
    print(f"  {len(bio_df)} biographies, {len(pos_df)} position records")

    print(f"\nMatching {election_year} candidates to biographies...")
    targets = get_target_names(bio_df, election_year)
    print(f"  {len(targets)} candidates matched")

    print("\nExtracting personal connections from personal_info...")
    personal = extract_personal_connections(bio_df, targets)
    print(f"  {len(personal)} personal connections found")

    print("\nExtracting co-location connections from positions...")
    colocation = extract_colocation_connections(pos_df, targets)
    print(f"  {len(colocation)} co-location connections found")

    print("\nExtracting birthplace contemporary connections...")
    birthplace = extract_birthplace_connections(bio_df, pos_df, targets)
    print(f"  {len(birthplace)} birthplace connections found")

    # Combine all connections
    all_conns = personal + colocation + birthplace
    conn_df = pd.DataFrame(all_conns)

    # Deduplicate — keep the most specific connection per pair
    if len(conn_df) > 0:
        conn_df = conn_df.drop_duplicates(
            subset=["person_a", "person_b", "connection_type"],
            keep="first",
        )

    print(f"\nTotal unique connections: {len(conn_df)}")
    if len(conn_df) > 0:
        print("\nConnection type distribution:")
        print(conn_df["connection_type"].value_counts().to_string())

        print("\nConnections per candidate:")
        for t in targets:
            n = len(conn_df[(conn_df["person_a"] == t) | (conn_df["person_b"] == t)])
            print(f"  {t}: {n}")

    out = output_path or PARSED_CONNECTIONS_CSV
    conn_df.to_csv(out, index=False)
    print(f"\nSaved to {out}")
    return conn_df, targets


def main():
    import sys
    year = int(sys.argv[1]) if len(sys.argv) > 1 else 1988
    output = None
    if year != 1988:
        output = PARSED_CONNECTIONS_CSV.parent / f"parsed_connections_{year}.csv"
    build_all_connections(year, output)


if __name__ == "__main__":
    main()
