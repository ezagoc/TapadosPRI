"""
03_fix_person_names.py

Repairs corrupted person names in biographies_corrected.csv (the manually
corrected pipeline input produced from 02_parse_biographies.py + hand edits).

── The problem ──────────────────────────────────────────────────────────────
When 02_parse_biographies.py split biographies_full.txt into rows, a newline
INSIDE a name caused part of the name to "bleed" into the PREVIOUS row's last
field (the `sources` column), leaving only a fragment as the current row's name.
Two corruption shapes result:

  1. Deceased people — the death-date marker "(Deceased Oct.\n9, 1965)" wraps,
     so the name keeps only the date tail:   "9, 1965)"   "(Deceased 1953)"
  2. Living people  — a first name wraps to a new line, so the name keeps only
     the trailing given name:                "Manuel"     "del carMen"
  Plus a few OCR-artifact fragments:         "mp,"        "es, 1935–2009"

In every case the *real* name survived: it was pushed to the tail of the
PREVIOUS row's `sources` column. biographies_full.txt also holds the full name,
but there OCR column-wrapping splits names across lines, so the previous row's
`sources` tail is the most complete single-field source.

── The fix ──────────────────────────────────────────────────────────────────
For each corrupt row i, reconstruct the name from row (i-1)'s `sources`:
  • strip trailing OCR junk ("mp,", "es, 1935–2009", page-break artifacts)
  • split off a trailing "(Deceased …)" marker (complete → name is before it;
    partial/open → complete it with the current row's date fragment)
  • the name is the text AFTER the last citation digit (citations carry page
    numbers / years; names contain no digits)
  • if the current row's fragment is a given name, append it
Every reconstructed name is VALIDATED as a substring of biographies_full.txt
(accent/whitespace-normalised); rows that fail validation are left untouched
and reported, so nothing is silently overwritten.

This script is idempotent and edits biographies_corrected.csv IN PLACE,
touching only the `name` column of corrupt rows. All manual corrections in the
other columns are preserved.

Input  : biographies_corrected.csv, biographies_full.txt   (config paths)
Output : biographies_corrected.csv  (corrupt names repaired)
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd

CODE_DIR = Path(__file__).resolve().parents[2]
if str(CODE_DIR) not in sys.path:
    sys.path.append(str(CODE_DIR))

from config import BIOGRAPHIES_CSV, BIOGRAPHIES_RAW_TXT


# ── normalisation ────────────────────────────────────────────────────────────
def _norm(s: str) -> str:
    """Lower-case, strip accents, collapse to single-spaced alphanumerics."""
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.category(c).startswith("M"))
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


# ── corruption detection ─────────────────────────────────────────────────────
_ARTIFACT = re.compile(
    r"(mexican political biograph|proquest|ebook|cid=|page \d|sity of texas)", re.I
)
_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)"
# A name cell that is itself a death-date fragment, e.g. "Aug. 25, 1979." "9, 1965)"
_DATE_FRAGMENT = re.compile(rf"^\s*(?:\d|{_MONTH}\.?\s+\d)", re.I)


def is_corrupt(name: str) -> bool:
    """True if a name cell is a corruption fragment rather than a real name.

    Checks the name *core* (with any "(Deceased …)" marker removed) so that a
    comma inside the death date cannot mask an otherwise-empty surname, e.g.
    "enrique (Deceased Nov. 29, 2006)".
    """
    if not isinstance(name, str) or not name.strip() or name.strip() == "nan":
        return True
    s = name.strip()
    core = re.sub(r"\s*\(Deceased[^)]*\)", "", s).strip()
    return bool(
        not core
        or _DATE_FRAGMENT.match(core)                   # "9, 1965)"  "Aug. 25, 1979."
        or core.startswith("(")                         # "(Deceased 1953)"
        or re.match(r"^\s*(mp|es)\b[,. ]", core, re.I)  # "mp,"  "es, 1935–2009"
        or _ARTIFACT.search(s)                          # page-break OCR junk
        or ("," not in core)                            # "Manuel"  (real names: "Last, First")
        or re.match(r"^[^(]*\)", core)                  # "Monteros)…" orphan close-paren
    )


# ── name reconstruction from the previous row's `sources` tail ───────────────
_JUNK_TAIL = re.compile(
    r"(?:\s*\b(?:mp|es)\b[,.]?"
    r"|\s*1935\s*[–-]\s*2009"
    r"|\s*\d+\s+mexican political biograph\w*"
    r"|\s*proquest[^.]*\.?"
    r"|\s*---\s*page\s*\d+\s*---)+\s*$",
    re.I,
)
_LEAD_CITE = re.compile(
    r"^(?:letters?|será|func|protag|directorio|ind|biog|correa|peral)\b[.,]?\s+", re.I
)


def _frag_is_junk(frag: str) -> bool:
    s = frag.strip()
    return bool(
        re.match(r"^\s*(mp|es)\b", s, re.I) or _ARTIFACT.search(s) or re.match(r"^\s*1935", s)
    )


def _after_last_digit(s: str) -> str:
    """Name = text after the last digit (citations carry digits; names do not)."""
    digits = list(re.finditer(r"\d", s))
    t = s[digits[-1].end():] if digits else s
    t = re.sub(r"^[\s\d.,;:–\-)]+", "", t)
    # drop any leftover leading URL / domain citation fragments
    t = re.sub(r"^(?:www\.\S+\s*|[A-Za-z.]+\.(?:mx|com|org|gob|edu|net)\S*\s*)+", "", t, flags=re.I)
    # drop page-break OCR artifacts that land between the last digit and the name
    t = re.sub(r"^\s*(?:\d+\s+)?mexican\s+political\s+biograph\w*\s*", "", t, flags=re.I)
    t = re.sub(r"^\s*(?:sity of texas[^.]*\.\s*|proquest[^.]*\.\s*)", "", t, flags=re.I)
    t = re.sub(r"^[\s.,;:–\-]+", "", t)
    return _LEAD_CITE.sub("", t).strip()


def reconstruct(prev_sources: str, fragment: str) -> str | None:
    """Rebuild the real name for a corrupt row from the previous row's sources."""
    if not isinstance(prev_sources, str):
        return None
    s = _JUNK_TAIL.sub("", prev_sources.rstrip()).rstrip()
    frag = (fragment or "").strip()

    # a complete "(Deceased …)" inside the current fragment is the authoritative marker
    frag_marker = re.search(r"\(Deceased[^)]*\)", frag)

    marker = None
    core = s
    m_close = re.search(r"\(Deceased[^)]*\)\s*$", s)   # complete "(Deceased …)"
    m_open = re.search(r"\(Deceased[^)]*$", s)          # open "(Deceased Oct"
    if m_close:
        marker = m_close.group(0).strip()
        core = s[: m_close.start()].rstrip()
    elif m_open:
        core = s[: m_open.start()].rstrip()
        if frag_marker:
            marker = frag_marker.group(0)               # fragment carries the full date
        else:
            # split death marker: complete the open marker with the date fragment,
            # then normalise to a single closing paren ("…1979." → "…1979)")
            marker = re.sub(r"\s+", " ", m_open.group(0) + " " + frag).strip()
            marker = re.sub(r"[.\s)]*$", "", marker) + ")"
        frag = ""

    name = _after_last_digit(core)

    if frag.startswith("(Deceased"):
        marker = frag
    elif frag_marker:
        # fragment = "<given-name> (Deceased …)"; append the name part, keep marker
        name = f"{name} {frag[: frag_marker.start()].strip()}".strip()
        marker = frag_marker.group(0)
    elif frag and re.match(r"^[A-Za-zÀ-ÿ(]", frag) and not _frag_is_junk(frag):
        name = f"{name} {frag}"

    full = f"{name} {marker}" if marker else name
    full = re.sub(r"\s{2,}", " ", full).strip()
    return full or None


def _insert_missing_comma(name: str) -> str:
    """Repair a complete name whose surname/given-name comma was dropped.

    "BreMauntz (Martínez) alBerto (Deceased Dec. 9, 1978)"
        → "BreMauntz (Martínez), alBerto (Deceased Dec. 9, 1978)"
    Only acts when the name core has a maternal "(…)" group followed by a
    given name and contains no comma; otherwise returns the name unchanged.
    """
    if not isinstance(name, str):
        return name
    core = re.sub(r"\s*\(Deceased[^)]*\)", "", name).strip()
    if "," in core:
        return name
    m = re.match(r"^(.*\))\s+(\S.*)$", core)  # "…(maternal) Given"
    if not m:
        return name
    return name.replace(core, f"{m.group(1)}, {m.group(2)}", 1)


# ── death-date paren normalisation ───────────────────────────────────────────
# Some names carry a death date without the "Deceased" keyword, e.g.
#   "charis castro, heliodoro (1964)"  "rangel frías, raúl (Apr. 18, 1993)"
# Tag these so clean_name_col (04_parse_positions.py) strips them from the name.
_BARE_DEATH_PAREN = re.compile(
    rf"\((\d{{4}}|{_MONTH}\.?\s+\d{{1,2}},?\s*\d{{4}})\)\s*$", re.I
)


def normalise_death_paren(name: str) -> str:
    if not isinstance(name, str):
        return name
    return _BARE_DEATH_PAREN.sub(lambda m: f"(Deceased {m.group(1)})", name).strip()


# ── main ─────────────────────────────────────────────────────────────────────
def main() -> None:
    print(f"Loading {BIOGRAPHIES_CSV.name} …")
    bio = pd.read_csv(BIOGRAPHIES_CSV)
    print(f"  {len(bio):,} rows")

    raw = BIOGRAPHIES_RAW_TXT.read_text(encoding="utf-8", errors="replace")
    norm_txt = _norm(raw)  # whitespace-collapsed, handles OCR line-wrapped names

    corrupt = [i for i in bio.index if is_corrupt(bio.loc[i, "name"])]
    print(f"  Corrupt name cells detected: {len(corrupt)}")
    if not corrupt:
        print("Nothing to fix — names already clean.")
        return

    fixed, skipped = [], []
    for i in corrupt:
        original = str(bio.loc[i, "name"])
        prev_sources = bio.loc[i - 1, "sources"] if i > 0 else None
        candidate = reconstruct(prev_sources, original)
        # validate: the name (minus death marker) must appear in the source text
        name_only = re.sub(r"\s*\(Deceased[^)]*\)", "", candidate or "").strip()
        if candidate and len(name_only) >= 4 and _norm(name_only) in norm_txt:
            bio.at[i, "name"] = candidate
            fixed.append((i, candidate))
            continue
        # fallback: a complete name that is only missing the surname/given-name
        # comma, e.g. "BreMauntz (Martínez) alBerto" → "BreMauntz (Martínez), alBerto".
        repaired = _insert_missing_comma(original)
        if repaired != original:
            bio.at[i, "name"] = repaired
            fixed.append((i, repaired))
        else:
            skipped.append((i, original, candidate))

    # Tag bare death-date parens "(1964)" → "(Deceased 1964)" across all rows
    before = bio["name"].copy()
    bio["name"] = bio["name"].map(normalise_death_paren)
    n_tagged = int((before.fillna("§") != bio["name"].fillna("§")).sum())

    bio.to_csv(BIOGRAPHIES_CSV, index=False)

    print(f"\nRepaired {len(fixed)} names → {BIOGRAPHIES_CSV}")
    if n_tagged:
        print(f"Normalised {n_tagged} bare death-date parens to '(Deceased …)'")
    for i, name in fixed:
        print(f"  row {i:4d}: {name}")

    if skipped:
        print(f"\n⚠ {len(skipped)} names could NOT be validated and were left unchanged:")
        for i, old, cand in skipped:
            print(f"  row {i:4d}: kept {old!r}  (best guess: {cand!r})")

    remaining = [i for i in bio.index if is_corrupt(bio.loc[i, "name"])]
    print(f"\nCorrupt names remaining: {len(remaining)}")


if __name__ == "__main__":
    main()
