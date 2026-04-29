"""
extract_pdf.py
Extracts the biographies section (PDF pages 34-1067) from the Mexican Political
Biographies PDF using two-column layout detection and watermark removal.
Output: data/biographies_full.txt
"""

import pdfplumber
import re
from pathlib import Path
import sys

CODE_DIR = Path(__file__).resolve().parents[2]
if str(CODE_DIR) not in sys.path:
    sys.path.append(str(CODE_DIR))

from config import MAIN_BIOGRAPHIES_PDF, DATA_DIR

PDF_PATH = MAIN_BIOGRAPHIES_PDF
OUT_DIR = DATA_DIR
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Watermark strip: all watermark words sit at x0 = -4.8 (outside page boundary)
X_MIN = 10

# Patterns to strip from each page
FOOTER_RE = re.compile(
    r'(?:Camp,?\s+)?Roderic Ai\..*?(?:Created\s+)?from nyulibrary-ebooks on [^\n]+',
    re.DOTALL
)
URL_RE    = re.compile(r'Central,?\s+https?://ebookcentral[^\n]+\n?', re.MULTILINE)
HEADER_RE = re.compile(r'^[^\n]*recto runninghead[^\n]*\n?', re.MULTILINE)
# Running header at top of biography pages e.g. "the biographies 1028"
BIO_HDR_RE = re.compile(r'^.*?(?:the biographies|mexican political biographies)[^\n]*\n?',
                         re.MULTILINE | re.IGNORECASE)

# PDF page range (0-indexed)
BIO_START = 33    # PDF page 34  = book page 1  (first biography)
BIO_END   = 1067  # PDF page 1067 = book page 1034 (last biography)


def extract_col(page, x0, x1):
    px0, py0, px1, py1 = page.bbox
    col = page.crop((max(x0, px0), py0, min(x1, px1), py1))
    return col.extract_text() or ""


def clean_text(text):
    text = FOOTER_RE.sub("", text)
    text = URL_RE.sub("", text)
    text = HEADER_RE.sub("", text)
    text = BIO_HDR_RE.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_page(page):
    mid   = page.width / 2
    left  = extract_col(page, X_MIN, mid)
    right = extract_col(page, mid, page.width)
    text  = left + ("\n\n" if left and right else "") + right
    return clean_text(text)


# ── Main extraction ───────────────────────────────────────────────────────────

print(f"Extracting PDF pages {BIO_START + 1}–{BIO_END + 1}...")
pages_text = []

with pdfplumber.open(PDF_PATH) as pdf:
    total = len(pdf.pages)
    print(f"Total PDF pages: {total}")

    for i in range(BIO_START, min(BIO_END + 1, total)):
        text = clean_page(pdf.pages[i])
        if text:
            pages_text.append(f"--- PAGE {i + 1} ---\n{text}")

        done = i - BIO_START + 1
        if done % 100 == 0:
            print(f"  {done} / {BIO_END - BIO_START + 1} pages done...")

full_text = "\n\n".join(pages_text)

out_path = OUT_DIR / "biographies_full.txt"
out_path.write_text(full_text, encoding="utf-8")
print(f"\nDone. {len(pages_text)} pages saved to {out_path}")
