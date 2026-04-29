import pdfplumber
import re
from pathlib import Path
import sys

CODE_DIR = Path(__file__).resolve().parent
if str(CODE_DIR) not in sys.path:
    sys.path.append(str(CODE_DIR))

from config import MAIN_BIOGRAPHIES_PDF, DATA_DIR

PDF_PATH = MAIN_BIOGRAPHIES_PDF
OUT_PATH = DATA_DIR / "biographies_pages34_64.txt"

# Watermark words all sit at x0 = -4.8 (outside the page boundary).
# Main text starts at x0 >= ~48. Anything below this threshold is margin junk.
X_MIN = 10

# ProQuest citation footer — "Camp," and "Created" may be cut off by the x-filter
FOOTER_RE = re.compile(
    r'(?:Camp,?\s+)?Roderic Ai\..*?(?:Created\s+)?from nyulibrary-ebooks on [^\n]+',
    re.DOTALL
)
# ProQuest URL line that may survive on its own
URL_RE = re.compile(r'Central,?\s+https?://ebookcentral[^\n]+\n?', re.MULTILINE)
# Running headers — word order can vary, so match any line containing the phrase
HEADER_RE = re.compile(r'^[^\n]*recto runninghead[^\n]*\n?', re.MULTILINE)


def extract_col(page, x0, x1):
    """Extract clean text from a vertical slice of the page."""
    px0, py0, px1, py1 = page.bbox
    col = page.crop((max(x0, px0), py0, min(x1, px1), py1))
    return col.extract_text() or ""


def clean_text(text):
    text = FOOTER_RE.sub("", text)
    text = URL_RE.sub("", text)
    text = HEADER_RE.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_page(page):
    mid = page.width / 2
    # Left column (skip watermark strip at x < X_MIN)
    left  = extract_col(page, X_MIN, mid)
    # Right column
    right = extract_col(page, mid, page.width)
    # Join columns; blank separator so entries don't run together
    text = left + ("\n\n" if left and right else "") + right
    return clean_text(text)


output_lines = []

with pdfplumber.open(PDF_PATH) as pdf:
    for i, page in enumerate(pdf.pages[33:64], start=34):
        text = clean_page(page)
        header = f"\n--- PAGE {i} ---\n"
        print(header)
        print(text)
        output_lines.append(header + "\n" + text)

OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
with open(OUT_PATH, "w", encoding="utf-8") as f:
    f.write("\n".join(output_lines))

print(f"\nSaved to: {OUT_PATH}")
