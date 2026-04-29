"""
parse_biographies.py
Parses biographies_full.txt into a structured CSV with one row per entry.

Biography structure (from the book's key):
  a – birth date          b – state/city of birth
  c – education           d – principal public positions
  e – party positions     f – federal government positions
  g – labor/business      h – other positions
  i – personal/family     j – ?  k – ?
  l – sources
"""

import re
import pandas as pd
from pathlib import Path

TEXT_PATH = Path(__file__).parent.parent / "data" / "biographies_full.txt"
OUT_CSV   = Path(__file__).parent.parent / "data" / "biographies.csv"

FIELD_MAP = {
    'a': 'birth_date',
    'b': 'birthplace',
    'c': 'education',
    'd': 'public_positions',
    'e': 'party_positions',
    'f': 'govt_positions',
    'g': 'labor_positions',
    'h': 'other_positions',
    'i': 'personal_info',
    'j': 'field_j',
    'k': 'field_k',
    'l': 'sources',
}

# En-dash, em-dash, figure-dash, or plain hyphen used as field separator
DASH = r'[\u2013\u2014\u2012\-]'

# Matches a single field letter followed by a dash at a word boundary
FIELD_TOKEN = re.compile(rf'(?<!\w)([a-l])(?={DASH})')


def load_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    # Remove page-marker lines
    text = re.sub(r'^--- PAGE \d+ ---\n?', '', text, flags=re.MULTILINE)
    # Join words broken by end-of-line hyphens  e.g. "Guerr-\nero" → "Guerrero"
    text = re.sub(r'(\w)-\n(\w)', r'\1\2', text)
    return text


def extract_name(lines: list[str]) -> str | None:
    """
    Reconstruct a biography name from the last 1-2 non-field lines.
    Handles names that wrap across two lines, e.g.:
        aBascal carranza, carlos (Deceased
        Dec. 2, 2008)
    """
    if not lines:
        return None

    last = lines[-1]

    # Skip if the last line is a field value
    if re.match(rf'^[a-l]{DASH}', last):
        return None

    # Check if this line is a continuation of the previous name line:
    # e.g. "Dec. 2, 2008)" completing "aBascal carranza, carlos (Deceased"
    # Criteria: ends with ')', is short (date/parenthetical only), and the
    # previous line is not a field value and doesn't end with a period.
    if len(lines) >= 2:
        prev = lines[-2]
        if (last.endswith(')')
                and len(last) <= 30
                and not prev.endswith('.')
                and not re.match(rf'^[a-l]{DASH}', prev)):
            return prev + ' ' + last

    return last


def find_bio_starts(text: str):
    """
    Return a list of (a_pos, name) pairs where a_pos is the character position
    of a field-'a' marker and name is the name line immediately before it.
    """
    a_pattern = re.compile(rf'(?<!\w)a{DASH}')
    results = []

    for m in a_pattern.finditer(text):
        a_pos = m.start()
        preceding = text[:a_pos]
        lines = [ln.strip() for ln in preceding.split('\n') if ln.strip()]
        name = extract_name(lines)
        if name is None:
            continue
        results.append((a_pos, name))

    return results


def parse_fields(content: str) -> dict:
    """Split a biography body into fields a–l and return a dict."""
    # Normalise whitespace (collapse newlines / extra spaces within a field)
    content = re.sub(r'\s+', ' ', content).strip()

    splitter = re.compile(rf'(?<!\w)([a-l]){DASH}')
    parts = splitter.split(content)
    # parts layout: [pre_text, 'a', val_a, 'b', val_b, ...]

    fields = {}
    i = 1
    while i < len(parts) - 1:
        letter = parts[i]
        value  = parts[i + 1].strip().rstrip('. ')
        if letter in FIELD_MAP:
            fields[FIELD_MAP[letter]] = value
        i += 2

    return fields


def parse_biographies(text: str) -> list[dict]:
    bio_starts = find_bio_starts(text)
    print(f"  Found {len(bio_starts)} potential biography starts.")

    entries = []
    for idx, (a_pos, name) in enumerate(bio_starts):
        # Content ends just before the name of the NEXT biography
        if idx + 1 < len(bio_starts):
            next_a_pos = bio_starts[idx + 1][0]
            block = text[a_pos:next_a_pos]
            # Strip the last line (= next entry's name) from this block
            last_nl = block.rfind('\n')
            content = block[:last_nl] if last_nl > 0 else block
        else:
            content = text[a_pos:]

        fields = parse_fields(content)
        if not fields:
            continue

        entry = {'name': name, **fields}
        entries.append(entry)

    return entries


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"Loading {TEXT_PATH} ...")
    text = load_text(TEXT_PATH)
    print(f"  Text length: {len(text):,} characters")

    print("Parsing biographies...")
    entries = parse_biographies(text)
    print(f"  Parsed {len(entries)} biography entries.")

    df = pd.DataFrame(entries, columns=['name'] + list(FIELD_MAP.values()))
    df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    print(f"\nSaved: {OUT_CSV}")
    print(f"Shape: {df.shape}")
    print("\nSample (first 3 rows):")
    print(df[['name', 'birth_date', 'birthplace', 'education']].head(3).to_string())
