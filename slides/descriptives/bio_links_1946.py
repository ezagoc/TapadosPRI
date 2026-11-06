"""Slide figure: the 1946 succession read off the biographies.

Real crops of Camp (2011), Mexican Political Biographies 1935-2009: two 1946 contenders, Miguel Aleman and
Ezequiel Padilla, one pyramid each: portrait, his biography, and below it the two politicians tied to him (the
men Aleman appointed in December 1946, which the slide does not say: it comes before the outcome is revealed). The phrases that generate each
position-based tie are highlighted: same school and cohort (yellow), same office and years (blue). Pages are located
by the entry heading, phrases by text search; the crops are whole text lines of the book's column.
Output: OUTPUT_DIR/slides/descriptives/bio_links_1946.{png,pdf} (the deck's figure of the same name). The two portraits are read
from the deck's static images (research/slides/3rdYearPresentation/figures/1946_portrait_*.png).
Run: python3 slides/descriptives/bio_links_1946.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'code'))   # the repository's code/ (config.py)
from config import BIOGRAPHIES_DIR, OUTPUT_DIR  # noqa: E402
import pymupdf, io
from PIL import Image, ImageDraw
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

PDF = next(BIOGRAPHIES_DIR.glob('Mexican_Political_Biographies_1935-2009*.pdf'))
OUT = OUTPUT_DIR / 'slides' / 'descriptives'; OUT.mkdir(parents=True, exist_ok=True)
PORTRAITS = Path(__file__).resolve().parents[2] / 'research' / 'slides' / '3rdYearPresentation' / 'figures'
doc = pymupdf.open(PDF)
YEL, BLU = (1.0, 0.86, 0.25), (0.50, 0.74, 1.0)
DPI = 300
COLW = 173  # points: width of a text column in the book
COLS = (56, 234)  # x of the two columns


def column(rect):
    return COLS[0] if rect.x0 < 200 else COLS[1]


def find(pages, text):
    """First page (in order) where the text occurs, with its rectangles."""
    for p in pages:
        rs = doc[p].search_for(text)
        if rs:
            return p, rs
    raise ValueError(f'{text!r} not found on pages {pages}')


def mark(pages, marks):
    for phrase, col in marks:
        p, rs = find(pages, phrase)
        page = doc[p]  # keep the page object alive while its annotations are updated
        for r in rs:
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


def piece_for(pages, texts):
    """Crop covering the lines that hold the given phrases (all on one page and column)."""
    p, rs = find(pages, texts[0])
    x0 = column(rs[0])
    rects = [r for t in texts for r in doc[p].search_for(t) if column(r) == x0]
    return piece(p, x0, min(r.y0 for r in rects), max(r.y1 for r in rects))


def stack(pieces, gap=10):
    w = max(p.width for p in pieces); h = sum(p.height for p in pieces) + gap * (len(pieces) - 1)
    out = Image.new("RGB", (w, h), "white"); d = ImageDraw.Draw(out); y = 0
    for i, p in enumerate(pieces):
        out.paste(p, (0, y)); y += p.height
        if i < len(pieces) - 1:
            for x in range(8, w - 8, 14): d.line([(x, y + gap // 2), (x + 6, y + gap // 2)], fill=(170, 170, 170), width=2)
            y += gap
    return out


# --- Aleman (pdf p. 65): heading, the law-school cohort, the Interior post
P = [65, 66]
mark(P, [('law degree from National School of Law, 1925–1928', YEL), ('secretary of government, 1940–1945', BLU)])
ALE = stack([piece_for(P, ['Alemán (Valdés), Miguel']),
             piece_for(P, ['law degree from National School of Law, 1925–1928']),
             piece_for(P, ['secretary of government, 1940–1945'])])
# --- Perez Martinez (p. 783-784): oficial mayor under Aleman
P = [783, 784]
mark(P, [('oficial mayor, Secretariat of Government, 1945', BLU)])
HPM = stack([piece_for(P, ['Pérez Martínez, Héctor']),
             piece_for(P, ['oficial mayor, Secretariat of Government, 1945'])])
# --- Beteta (p. 136): the same law-school cohort as Aleman
P = [136, 137]
mark(P, [('law degree from National School of Law, 1925–1926', YEL)])
BET = stack([piece_for(P, ['Beteta (Quintana), Ramón']),
             piece_for(P, ['law degree from National School of Law, 1925–1926'])])
# --- Padilla (p. 758): heading and the Foreign Relations post
P = [758, 759]
mark(P, [('secretary of foreign relations, 1940–1945', BLU)])
PAD = stack([piece_for(P, ['Padilla (Peñalosa), Ezequiel']), piece_for(P, ['secretary of foreign relations, 1940–1945'])])
# --- Torres Bodet (p. 983): assistant secretary under Padilla
P = [983, 984]
mark(P, [('assistant secretary of foreign relations, 1940–1943', BLU)])
JTB = stack([piece_for(P, ['Torres Bodet, Jaime']), piece_for(P, ['assistant secretary of foreign relations, 1940–1943'])])
# --- Tello (p. 975): Foreign Relations posts under Padilla, 1942-45
P = [975, 976]
mark(P, [('director general, Diplomatic Service and Political', BLU), ('Affairs, Secretariat of Foreign Relations, 1942–1943', BLU)])
TEL = stack([piece_for(P, ['Tello (Baurraud), Manuel']),
             piece_for(P, ['director general, Diplomatic Service and Political', 'Affairs, Secretariat of Foreign Relations, 1942–1943'])])

ACC, INK, Z5, Z6 = '#940034', '#111111', '#71717a', '#52525b'
W, H = 12.6, 5.6
CW = 3.0                 # inches: width of every crop (the same magnification for all)
SCALE = CW / COLW        # inches per point
GAP = 0.15               # between the two crops at the base of each pyramid
fig = plt.figure(figsize=(W, H), dpi=200); fig.patch.set_facecolor('white')


def place(img, x, y_top, border='#d4d4d8'):
    w = img.width / DPI * 72 * SCALE; h = img.height / DPI * 72 * SCALE
    ax = fig.add_axes([x / W, (y_top - h) / H, w / W, h / H]); ax.imshow(img); ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values(): s.set_color(border); s.set_linewidth(0.8)
    return h


def portrait(name, cx, y_top, width=1.3):
    img = Image.open(PORTRAITS / f'1946_portrait_{name}.png').convert('RGB')
    h = width * img.height / img.width
    ax = fig.add_axes([(cx - width / 2) / W, (y_top - h) / H, width / W, h / H]); ax.imshow(img); ax.axis('off')
    return h


def connector(x0, y0, x1, y1):
    fig.add_artist(plt.Line2D([x0 / W, x1 / W], [y0 / H, y1 / H], transform=fig.transFigure, color='#a1a1aa', linewidth=0.9))


for i, (col, lab) in enumerate([(YEL, 'school tie'), (BLU, 'work tie')]):
    x = 0.25 + i * 3.0
    fig.patches.append(Rectangle((x / W, (H - 0.33) / H), 0.14 / W, 0.17 / H, transform=fig.transFigure, facecolor=col, edgecolor='none'))
    fig.text((x + 0.2) / W, (H - 0.245) / H, lab, fontsize=12, color=INK, va='center')

TOP = H - 0.6
# one pyramid per contender: portrait, his biography, then the two politicians tied to him
for cx, pic, crop, people in [(W / 4, 'aleman', ALE, [HPM, BET]), (3 * W / 4, 'padilla', PAD, [JTB, TEL])]:
    y = TOP - portrait(pic, cx, TOP) - 0.18
    y_base = y - place(crop, cx - CW / 2, y)
    y_people = y_base - 0.45
    for k, img in enumerate(people):
        x = cx - CW - GAP / 2 if k == 0 else cx + GAP / 2
        connector(cx, y_base, x + CW / 2, y_people)
        place(img, x, y_people)

fig.savefig(OUT / 'bio_links_1946.png', dpi=200, facecolor='white'); fig.savefig(OUT / 'bio_links_1946.pdf', facecolor='white')
print('saved; crop heights (in):', {k: round(v.height / DPI * 72 * SCALE, 2) for k, v in
                                    dict(ALE=ALE, HPM=HPM, BET=BET, PAD=PAD, JTB=JTB, TEL=TEL).items()})
