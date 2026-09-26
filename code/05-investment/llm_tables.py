"""
Shared helpers for reading printed statistical tables from scanned PDFs with vision
LLMs (used by 06_extract_inegi_state_investment.py and 08_extract_agency_investment.py).

Protocol: each crop is read independently by two pinned models (READERS); cells where
they disagree get a third read (TIEBREAK). Every answer is cached as JSON so re-runs
are free and fully auditable.

Spending guard: every API call's token usage is appended to DATA_DIR/llm_usage_ledger.csv
with its cost at the official list prices (+20% safety margin); before each call the
ledger total is checked and the run stops once it would exceed LLM_BUDGET_USD
(environment variable, default 20).
"""

from __future__ import annotations

import base64
import csv
import io
import json
import os
import re
import sys
import time
from pathlib import Path

import pymupdf
from PIL import Image

sys.path.append(str(Path(__file__).resolve().parents[1]))
from config import DATA_DIR  # noqa: E402

READERS = ["gpt-5.5-2026-04-23", "gpt-5.4-2026-03-05"]   # pinned snapshots
TIEBREAK = "gpt-5.2-2025-12-11"
DPI = 300

# USD per 1M tokens (input, output), OpenAI standard list prices (checked 2026-09-25)
PRICES = {"gpt-5.5": (5.00, 30.00), "gpt-5.4": (2.50, 15.00), "gpt-5.2": (1.75, 14.00),
          "gpt-5.4-mini": (0.75, 4.50)}
SAFETY = 1.2
LEDGER = DATA_DIR / "llm_usage_ledger.csv"


class BudgetExceeded(RuntimeError):
    pass


def _price(model: str) -> tuple[float, float]:
    base = max((k for k in PRICES if model.startswith(k)), key=len, default=None)
    return PRICES.get(base, (5.00, 30.00))          # unknown model → most expensive


def spent_usd() -> float:
    if not LEDGER.exists():
        return 0.0
    with open(LEDGER) as f:
        return sum(float(r["cost_usd"]) for r in csv.DictReader(f))


def _log_usage(model: str, usage, tag: str) -> float:
    pin, pout = _price(model)
    cost = SAFETY * (usage.prompt_tokens * pin + usage.completion_tokens * pout) / 1e6
    new = not LEDGER.exists()
    with open(LEDGER, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["time", "model", "tag", "prompt_tokens", "completion_tokens", "cost_usd"])
        w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), model, tag, usage.prompt_tokens,
                    usage.completion_tokens, round(cost, 5)])
    return cost


def check_budget():
    budget = float(os.getenv("LLM_BUDGET_USD", "20"))
    spent = spent_usd()
    if spent >= budget:
        raise BudgetExceeded(f"LLM budget reached: ${spent:.2f} of ${budget:.2f} "
                             f"(ledger {LEDGER}); raise LLM_BUDGET_USD to continue")


def page_image(pdf: Path, page: int, dpi: int = DPI) -> Image.Image:
    """Render one PDF page (1-based) to an RGB image."""
    pg = pymupdf.open(pdf)[page - 1]
    pix = pg.get_pixmap(dpi=dpi)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def read_crop(client, model, img, prompt, cache: Path) -> list[dict]:
    """Ask `model` to transcribe `img`; returns the JSON 'records' list (cached)."""
    if cache.exists():
        return json.loads(cache.read_text())
    check_budget()
    buf = io.BytesIO(); img.save(buf, "PNG")
    url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    r = client.chat.completions.create(
        model=model, response_format={"type": "json_object"},
        messages=[{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": url, "detail": "high"}}]}])
    _log_usage(model, r.usage, cache.stem)
    recs = json.loads(r.choices[0].message.content).get("records", [])
    cache.write_text(json.dumps(recs, ensure_ascii=False))
    return recs


def parse_value(s):
    """Printed number → float ('1 234.5', '(12.3)' negative, '-'/blank → None)."""
    s = str(s).strip()
    if not s or re.fullmatch(r"[-–—.]+", s):
        return None
    neg = s.startswith("(") or s.startswith("-")
    s = re.sub(r"[^0-9.,]", "", s)
    if s.count(",") and s.count("."):          # 1,234.5 → thousands commas
        s = s.replace(",", "")
    elif s.count(",") == 1 and len(s.split(",")[1]) == 1:   # 12,3 decimal comma
        s = s.replace(",", ".")
    else:
        s = s.replace(",", "")
    s = s.strip(".")
    if s.count(".") > 1:                        # stray dots: keep the last as decimal
        head, _, tail = s.rpartition(".")
        s = head.replace(".", "") + "." + tail
    if not s:
        return None
    v = float(s)
    return -v if neg else v
