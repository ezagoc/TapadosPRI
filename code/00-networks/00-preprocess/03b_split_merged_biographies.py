"""
03b_split_merged_biographies.py

Recovers biographies that 02_parse_biographies.py merged into the PREVIOUS entry,
and repairs the host entries they overwrote, in biographies_corrected.csv.

── The problem ──────────────────────────────────────────────────────────────
02 starts a new biography only at an "a—" (birth date) marker. Entries whose
birth date is unknown start at "b—" or "c—", so their fields were appended to the
previous biography, and in 02's field dict the later values OVERWROTE the host's.
Example: "henríquez guzmán, Miguel" (the general, PRI pre-candidate 1946 and 1952)
lost his military career (j), his candidacies (k) and his sources (l). Instead he
carried the law degree and 1968 posts of the next entry, "heredia ferráez, Jorge",
who disappeared from the data.

── The fix ──────────────────────────────────────────────────────────────────
1. Re-read biographies_full.txt with 02's own functions and split every block
   wherever the fields restart after the sources field "l—" (l is always the last
   field; a restart at "b—"/"c—"/"d—" means a new entry). Only true em/en-dash
   markers count, so "www.e-local.gob.mx" in a source list is not a field.
2. The merged entry's name is the tail of the host's "l—" text, after the last
   citation and page-break junk. It must look like "surname(s), given name(s)"
   and appear verbatim in biographies_full.txt, otherwise the case is skipped
   and reported.
3. In biographies_corrected.csv, the host row is found by its birth date (never
   overwritten: merged entries have no a—) and its birthplace, which is either its
   own or the merged entry's one (entries starting at "b—" overwrote it).
   - A column is repaired only if its CSV value equals the merged entry's value
     (i.e. it still holds the overwrite). It then gets the host's own value, or
     is blanked if the host had none. Any other value is a manual correction and
     is kept (reported).
4. Each recovered entry is APPENDED at the end of the CSV. 04 assigns person_id by
   order of first appearance, so no existing person_id changes.

The script is idempotent: an entry whose name is already in the CSV is not
appended again, and repaired host columns no longer match the merged values.

It also writes biography_repairs.csv (one row per case). 07_bio_ties_gpt.py uses
it to drop cached GPT answers for hosts whose personal_info changed.

Input  : biographies_corrected.csv, biographies_full.txt   (config paths)
Output : biographies_corrected.csv (in place), DATA_DIR/biography_repairs.csv
Run after 03_fix_person_names.py and before 04_parse_positions.py.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd

CODE_DIR = Path(__file__).resolve().parents[2]
if str(CODE_DIR) not in sys.path:
    sys.path.append(str(CODE_DIR))

from config import BIOGRAPHIES_CSV, BIOGRAPHIES_RAW_TXT, DATA_DIR

REPAIRS_CSV = DATA_DIR / "biography_repairs.csv"

# reuse 02's text loading and entry detection (its __main__ block is not run)
_spec = importlib.util.spec_from_file_location(
    "parse02", Path(__file__).with_name("02_parse_biographies.py"))
parse02 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(parse02)
FIELD_MAP = parse02.FIELD_MAP

STRICT_TOKEN = re.compile(r"(?<!\w)([a-l])[–—]")        # em/en dash only
PAGE_JUNK = re.compile(
    r"sity of Texas Press,\s*2011\.\s*ProQuest Ebook\s*cID=\d+\.?"
    r"|\d+\s+mexican political biographie\w*"
    r"|(?<!\w)mp,\s*"
    r"|(?<!\w)es,\s*1935[–\-]2009",
    re.I)


def norm(s) -> str:
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", s)


def split_block(content: str) -> list[str]:
    """Split one 02 block into entries at every field restart after an "l—"."""
    content = re.sub(r"\s+", " ", content).strip()
    toks = [(m.group(1), m.start()) for m in STRICT_TOKEN.finditer(content)]
    cuts, seen_l = [], False
    for letter, pos in toks:
        if seen_l and letter in "bcd":
            cuts.append(pos)
            seen_l = False
        elif letter == "l":
            seen_l = True
    bounds = [0] + cuts + [len(content)]
    return [content[a:b] for a, b in zip(bounds[:-1], bounds[1:])]


def cut_name_tail(segment: str) -> tuple[str, str | None]:
    """Split a segment ending in "l—<sources> <next entry's name>" into
    (segment without the name, name, OCR-garbled birth date or None)."""
    m = list(STRICT_TOKEN.finditer(segment))
    last_l = [x for x in m if x.group(1) == "l"]
    if not last_l:
        return segment, None, None
    start = last_l[-1].end()
    sources = PAGE_JUNK.sub(" ", segment[start:])
    sources = re.sub(r"\s+", " ", sources).strip()
    # OCR sometimes reads the birth-date marker "a—" as "A-": "ventura valle, ángel A-July 27, 1939."
    ocr_a = re.search(r"\s+A-\s*((?:[A-Z][a-z]{2,4}\.?\s+\d{1,2},\s*)?\d{4})\.?\s*$", sources)
    birth = None
    if ocr_a:
        birth, sources = ocr_a.group(1), sources[:ocr_a.start()]
    dec = re.search(r"\(\s*Deceased[^)]*\)?\s*$", sources, re.I)
    head = sources[:dec.start()].rstrip() if dec else sources
    # the name follows the last citation: after the last ". " or "; " whose
    # remainder contains no digit
    pieces = re.split(r"(?<=[.;])\s+", head)
    name_bits = []
    for p in reversed(pieces):
        if re.search(r"\d|www|\.gob|\.com|\.org|letter", p, re.I):
            break
        name_bits.insert(0, p)
    name = " ".join(name_bits).strip()
    if dec:
        name = f"{name} {dec.group(0).strip()}".strip()
    if not re.match(r"^[^\W\d][^,]{1,60},\s*\S", name) or re.search(r"\d", name.split("(")[0]):
        return segment, None, None
    host_sources = sources[: len(sources) - len(name)].rstrip() if sources.endswith(name) \
        else sources[: sources.rfind(name_bits[0])].rstrip() if name_bits else sources
    return segment[:start] + " " + host_sources, name, birth


def none_like(v) -> bool:
    return not isinstance(v, str) or norm(v) in ("", "none")


def parse_blocks(text: str):
    """Yield, for every 02 block that holds merged entries, a list of
    (name, fields) with the host first (name None) and each field set cleaned of
    the next entry's name."""
    starts = parse02.find_bio_starts(text)
    for idx, (a_pos, _) in enumerate(starts):
        if idx + 1 < len(starts):
            block = text[a_pos:starts[idx + 1][0]]
            nl = block.rfind("\n")
            block = block[:nl] if nl > 0 else block
        else:
            block = text[a_pos:]
        parts = split_block(block)
        if len(parts) < 2:
            continue
        entries, name, birth = [], None, None
        for k, seg in enumerate(parts):
            nxt_name = nxt_birth = None
            if k + 1 < len(parts):
                seg, nxt_name, nxt_birth = cut_name_tail(seg)
            fields = parse02.parse_fields(seg)
            if birth:
                fields["birth_date"] = birth
            entries.append((name, fields))
            name, birth = nxt_name, nxt_birth
        yield entries


def main():
    text = parse02.load_text(BIOGRAPHIES_RAW_TXT)
    raw_norm = norm(BIOGRAPHIES_RAW_TXT.read_text(encoding="utf-8"))
    bio = pd.read_csv(BIOGRAPHIES_CSV)
    names_norm = set(bio["name"].map(norm))
    cols = [c for c in FIELD_MAP.values() if c in bio.columns and c != "birth_date"]

    log, new_rows = [], []
    for entries in parse_blocks(text):
        host = entries[0][1]
        merged = entries[1:]
        # host row: its birth date is never overwritten (merged entries have no a—);
        # its birthplace is its own or that of a merged entry starting at "b—"
        bd = bio["birth_date"].map(norm) == norm(host.get("birth_date"))
        places = {norm(host.get("birthplace"))} | {norm(f.get("birthplace")) for _, f in merged}
        cand = bio[bd & bio["birthplace"].map(norm).isin(places - {""} | ({""} if "" in places else set()))]
        rec_base = {"host_birth_date": host.get("birth_date"), "host_birthplace": host.get("birthplace")}
        if len(cand) == 1:
            i = cand.index[0]
            repaired, kept = [], []
            for c in cols:
                over = [f.get(c) for _, f in merged if c in f]
                if not over:
                    continue                                   # nothing overwrote c
                ov, hv, cv = over[-1], host.get(c), bio.at[i, c]
                still_overwritten = (norm(cv) == norm(ov)) or (none_like(ov) and none_like(cv)) or \
                    (c == "sources" and isinstance(cv, str) and norm(cv).startswith(norm(ov)))
                if still_overwritten:
                    if norm(cv) != norm(hv) or (none_like(cv) and not none_like(hv)):
                        bio.at[i, c] = pd.NA if none_like(hv) else hv
                        repaired.append(c)
                elif norm(cv) != norm(hv):
                    kept.append(c)
            host_status = "host repaired" if repaired else "host ok"
            rec_base.update({"host_name": bio.at[i, "name"], "host_columns_repaired": ";".join(repaired),
                             "host_columns_kept_manual": ";".join(kept),
                             "personal_info_changed": int("personal_info" in repaired)})
        else:
            host_status = f"host not found ({len(cand)} candidates)"
        for name, f in merged:
            rec = dict(rec_base, merged_name=name)
            if not name or norm(name.split("(")[0]) not in raw_norm:
                rec["status"] = host_status + "; name not recovered"
            elif norm(name) in names_norm:
                rec["status"] = host_status + "; entry already present"
            else:
                row = {c: (pd.NA if none_like(f.get(c)) else f.get(c)) for c in cols}
                row["birth_date"] = f.get("birth_date", pd.NA)
                row["name"] = name
                new_rows.append(row)
                names_norm.add(norm(name))
                rec["status"] = host_status + "; entry appended"
            log.append(rec)

    if new_rows:
        bio = pd.concat([bio, pd.DataFrame(new_rows)[bio.columns]], ignore_index=True)
    bio.to_csv(BIOGRAPHIES_CSV, index=False)
    rep = pd.DataFrame(log)
    if REPAIRS_CSV.exists():   # keep what earlier runs repaired (a re-run finds nothing left to do)
        old = pd.read_csv(REPAIRS_CSV)
        rep = pd.concat([old, rep], ignore_index=True)
        rep["personal_info_changed"] = rep.groupby(["merged_name", "host_birth_date"], dropna=False) \
            .personal_info_changed.transform("max")
        rep = rep.drop_duplicates(["merged_name", "host_birth_date"], keep="first")
    rep.to_csv(REPAIRS_CSV, index=False)

    print(rep.status.value_counts().to_string())
    print(f"appended {len(new_rows)} recovered biographies → {BIOGRAPHIES_CSV}")
    print(f"host rows with personal_info changed (all runs): "
          f"{int(rep.drop_duplicates('host_name').personal_info_changed.fillna(0).sum())}")
    print(f"→ {REPAIRS_CSV}")


if __name__ == "__main__":
    main()
