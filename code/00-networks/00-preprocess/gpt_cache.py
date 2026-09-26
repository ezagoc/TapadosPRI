"""
gpt_cache.py

Cache for the GPT fallback of 05_govt_positions.py, 05_labor_positions.py and
05_party_positions.py (fill `organization` / `position_title` when the regex
extraction finds none).

Answers are reused from the previous run's output CSV, keyed by the exact
`role_text_raw` sent to GPT, so re-running a 05 script only queries texts it has
never seen. If no API key is configured or the call fails (e.g. no credit), the
new texts are left blank and reported; they are filled on a later run.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from config import openai_api_key


def fill_with_cache(texts: pd.Series, prev_csv: Path, gpt_fill_missing) -> pd.DataFrame:
    """Return a frame indexed like `texts` with columns organization, position_title."""
    out = pd.DataFrame(index=texts.index, columns=["organization", "position_title"], dtype=object)
    if Path(prev_csv).exists():
        prev = pd.read_csv(prev_csv, usecols=lambda c: c in ("role_text_raw", "org_gpt", "position_title_gpt"))
        prev = prev.dropna(subset=["role_text_raw"])
        prev = prev[prev[["org_gpt", "position_title_gpt"]].notna().any(axis=1)] \
            .drop_duplicates("role_text_raw").set_index("role_text_raw")
        hit = texts.isin(prev.index)
        out.loc[hit, "organization"] = texts[hit].map(prev["org_gpt"]).values
        out.loc[hit, "position_title"] = texts[hit].map(prev["position_title_gpt"]).values
    else:
        hit = pd.Series(False, index=texts.index)
    todo = texts[~hit]
    print(f"  GPT cache: {hit.sum()} texts reused, {len(todo)} new")
    if len(todo):
        key = openai_api_key()
        if not key:
            print(f"  no OpenAI key configured: {len(todo)} new texts left blank")
            return out
        try:
            res = gpt_fill_missing(todo, key)
            out.loc[res.index, "organization"] = res["organization"]
            out.loc[res.index, "position_title"] = res["position_title"]
        except Exception as e:                       # e.g. no API credit
            print(f"  GPT call failed ({str(e)[:100]}): {len(todo)} new texts left blank")
    return out
