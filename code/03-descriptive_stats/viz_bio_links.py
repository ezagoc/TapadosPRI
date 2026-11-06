"""Slide figure: how a tie is read off two biographies.

Real crops of Camp (2011), Mexican Political Biographies 1935-2009, with the phrases that generate each
position-based tie highlighted: Echeverria (president 1970-76) and three politicians tied to him by a
school generation (Reyes Heroles), a shared office (Moya Palencia, Gobernacion) and a shared faculty
(Lopez Portillo, UNAM law school). A stated tie ("friend of Luis Echeverria") is shown in grey as an
example of what the design records but does not use. Page indices refer to the PDF in BIOGRAPHIES_DIR.
Output: OUTPUT_DIR/slides/bio_links_echeverria.{png,pdf}
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import BIOGRAPHIES_DIR, OUTPUT_DIR  # noqa: E402
import pymupdf, io
from PIL import Image, ImageDraw
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

PDF = next(BIOGRAPHIES_DIR.glob('Mexican_Political_Biographies_1935-2009*.pdf'))
OUT = OUTPUT_DIR / 'slides'; OUT.mkdir(parents=True, exist_ok=True)
doc = pymupdf.open(PDF)
YEL, BLU, GRN, GRY = (1.0, 0.86, 0.25), (0.50, 0.74, 1.0), (0.55, 0.86, 0.55), (0.80, 0.80, 0.80)
DPI = 300
COLW = 173  # points: width of a text column in the book

def mark(page_no, marks):
    page = doc[page_no]
    for phrase, col in marks:
        for r in page.search_for(phrase):
            a = page.add_highlight_annot(r); a.set_colors(stroke=col); a.update()

def snap(page_no, x0, y0, y1):
    """Expand (y0, y1) to whole text lines of the column whose centre lies inside the range."""
    tops, bots = [], []
    for block in doc[page_no].get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            bx0, by0, bx1, by1 = line["bbox"]
            if bx0 >= x0 - 6 and bx1 <= x0 + COLW + 6 and y0 <= (by0 + by1) / 2 <= y1:
                tops.append(by0); bots.append(by1)
    return (min(tops) - 1.2, max(bots) + 1.2) if tops else (y0, y1)

def piece(page_no, x0, y0, y1):
    y0, y1 = snap(page_no, x0, y0, y1)
    pix = doc[page_no].get_pixmap(clip=pymupdf.Rect(x0, y0, x0 + COLW, y1), dpi=DPI)
    return Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")

def stack(pieces, gap=10):
    w = max(p.width for p in pieces); h = sum(p.height for p in pieces) + gap * (len(pieces) - 1)
    out = Image.new("RGB", (w, h), "white"); d = ImageDraw.Draw(out); y = 0
    for i, p in enumerate(pieces):
        out.paste(p, (0, y)); y += p.height
        if i < len(pieces) - 1:
            for x in range(8, w - 8, 14): d.line([(x, y + gap // 2), (x + 6, y + gap // 2)], fill=(170, 170, 170), width=2)
            y += gap
    return out

# --- Echeverría (pdf page 314, right column x=234): heading / education lines / government line
mark(314, [('law studies at National School of Law, UNAM, 1940–1944', YEL),
           ('professor of legal theory, National School of Law, UNAM, 1947–1949', GRN),
           ('secretary of government, 1964–1970', BLU)])
LEA = stack([piece(314, 234, 130, 144), piece(314, 234, 236, 303), piece(314, 234, 512, 534)])
# --- Reyes Heroles (p. 826): heading through the law degree
mark(826, [('law degree with honorable mention from National School of Law, UNAM, 1944', YEL)])
JRH = stack([piece(826, 234, 306, 384)])
# --- Moya Palencia (p. 696): heading at the bottom of the left column, posts at the top of the right column
mark(696, [('general, Bureau of Cinematography, Secre', BLU), ('tariat of Government, 1964–1968', BLU),
           ('secretary of government, 1969–1970, under', BLU), ('Luis Echeverría; secretary of government', BLU)])
MOYA = stack([piece(696, 56, 581, 603), piece(696, 234, 213, 269)])
# --- López Portillo (p. 584 heading and faculty post; p. 585 the stated friendship)
mark(584, [('professor of law, National School of Law, UNAM, 1947–1958', GRN)])
mark(585, [('friend of Luis', GRY), ('Echeverría since grammar school', GRY)])
JLP = stack([piece(584, 234, 444, 453), piece(584, 234, 581, 602), piece(585, 56, 374, 396)])

ACC, INK, Z5, Z6 = '#940034', '#111111', '#71717a', '#52525b'
W, H = 13.33, 6.1
fig = plt.figure(figsize=(W, H), dpi=200); fig.patch.set_facecolor('white')
SCALE = 3.1 / COLW   # inches per point: every crop at the same magnification (~1.5x the printed size)

def place(img, x, y_top, border='#d4d4d8'):
    w = img.width / DPI * 72 * SCALE; h = img.height / DPI * 72 * SCALE
    ax = fig.add_axes([x / W, (y_top - h) / H, w / W, h / H]); ax.imshow(img); ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values(): s.set_color(border); s.set_linewidth(0.8)
    return h

for i, (col, lab) in enumerate([(YEL, 'same school, same cohort'), (BLU, 'same office, same years'),
                                (GRN, 'same faculty, same years'), (GRY, 'stated tie: recorded, not used')]):
    x = 0.03 + i * 0.235
    fig.patches.append(Rectangle((x, 0.935), 0.011, 0.03, transform=fig.transFigure, facecolor=col, edgecolor='none'))
    fig.text(x + 0.015, 0.95, lab, fontsize=10.5, color=INK, va='center')

# top: the president, centred
xw = (W - 3.1) / 2; top = 5.45
h = place(LEA, xw, top)
fig.text(xw / W, (top - h - 0.17) / H, 'Luis Echeverría Álvarez', fontsize=11.5, weight='bold', color=ACC, va='center')
fig.text(xw / W, (top - h - 0.40) / H, 'President 1970–1976', fontsize=9.5, color=Z6, va='center')

# bottom: three politicians at the same scale
row_top = 2.45
items = [(0.55, JRH, YEL, 'Jesús Reyes Heroles', 'Law degree, UNAM, 1944: Echeverría\'s generation (1940–44)'),
         (0.55 + 4.1, MOYA, BLU, 'Mario Moya Palencia', 'Gobernación, 1964–70, under Echeverría as secretary'),
         (0.55 + 8.2, JLP, GRN, 'José López Portillo', 'UNAM law faculty, 1947–58, when Echeverría taught (1947–49)')]
for x, img, col, name, desc in items:
    h = place(img, x, row_top)
    fig.patches.append(Rectangle((x / W, 0.44 / H), 0.009, 0.026, transform=fig.transFigure, facecolor=col, edgecolor='none'))
    fig.text((x + 0.17) / W, 0.52 / H, name, fontsize=11.5, weight='bold', color=INK, va='center')
fig.savefig(OUT / 'bio_links_echeverria.png', dpi=200, facecolor='white'); fig.savefig(OUT / 'bio_links_echeverria.pdf', facecolor='white')
print('saved; crop heights (in):', [round(i.height / DPI * 72 * SCALE, 2) for i in (LEA, JRH, MOYA, JLP)])
