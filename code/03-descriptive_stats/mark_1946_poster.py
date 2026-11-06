"""Mark the 1946 contenders and the outgoing president on the 1942 cabinet poster.

Each mark is an outline that hugs the oval portrait in the poster (no free-floating circles). The four contenders
with a portrait crop in the deck (Alemán, Padilla, Rojo Gómez, Baz) are located on the poster by normalized
cross-correlation of their crops; the president's portrait sits at the centre. Inside each located box the photo is
the largest dark connected component, and the outline is the ellipse inscribed in its bounding box plus a margin.

Writes, next to the deck's figures:
  1946_cabinet_contenders_circled.png  president outlined in ink, the four contenders in the deck's accent colour
  1946_cabinet_designee.png            the same, with Alemán's outline heavier and the other contenders' in grey

Run: python code/03-descriptive_stats/mark_1946_poster.py
"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from scipy.signal import fftconvolve

FIG_DIR = Path(__file__).resolve().parents[2] / "research" / "slides" / "pri_succession_slides" / "figures"
POSTER = FIG_DIR / "1942_mexican_cabinet_chart_poster.png"
PORTRAITS = {"aleman": "Miguel Alemán", "padilla": "Ezequiel Padilla", "rojo_gomez": "Javier Rojo Gómez", "baz": "Gustavo Baz"}
PRESIDENT_BOX = (540, 260, 880, 560)  # x0, y0, x1, y1: the centre of the poster
# The president's oval, measured on the poster: the title arcs ("PRESIDENTE CONSTITUCIONAL") sit on the frame and are too
# bold for the opening to separate them, so its vertical extent is fixed from the row profile (arcs end at y = 300,
# the name banner starts at y = 545); the columns come from the dark component.
PRESIDENT_ROWS = (300, 545)
INK, ACCENT, GREY = "#1a1a1a", "#940034", "#a1a1aa"
MARGIN, WIDTH = 7, 5


def locate(poster_gray: np.ndarray, crop_gray: np.ndarray) -> tuple[int, int, float]:
    """Top-left corner of the crop in the poster (normalized cross-correlation at half resolution, refined at full)."""
    def ncc(img, tpl):
        tpl = (tpl - tpl.mean()) / (tpl.std() + 1e-9)
        n = tpl.size
        s1 = fftconvolve(img, np.ones(tpl.shape), mode="valid")
        s2 = fftconvolve(img * img, np.ones(tpl.shape), mode="valid")
        num = fftconvolve(img, tpl[::-1, ::-1], mode="valid")
        var = np.maximum(s2 - s1 * s1 / n, 1e-9)
        return num / np.sqrt(var * n)
    half = ncc(poster_gray[::2, ::2], crop_gray[::2, ::2])
    y, x = np.unravel_index(np.argmax(half), half.shape)
    y, x = 2 * y, 2 * x
    h, w = crop_gray.shape
    pad = 6
    y0, x0 = max(y - pad, 0), max(x - pad, 0)
    window = poster_gray[y0:y + h + pad, x0:x + w + pad]
    full = ncc(window, crop_gray)
    dy, dx = np.unravel_index(np.argmax(full), full.shape)
    return x0 + dx, y0 + dy, float(full.max())


def oval_bbox(gray: np.ndarray, box: tuple[int, int, int, int], opening: int = 2) -> tuple[int, int, int, int]:
    """Bounding box of the photo inside the box: the largest dark connected component after an opening that removes
    the small lettering around the frames."""
    x0, y0, x1, y1 = box
    sub = gray[y0:y1, x0:x1] < 205
    sub = ndimage.binary_opening(sub, iterations=opening)
    labels, n = ndimage.label(sub)
    sizes = ndimage.sum(sub, labels, range(1, n + 1))
    photo = labels == (1 + int(np.argmax(sizes)))
    ys, xs = np.nonzero(photo)
    return x0 + xs.min(), y0 + ys.min(), x0 + xs.max(), y0 + ys.max()


def standard_oval(boxes: dict, ovals: dict, key: str, reference: list[str]) -> tuple[int, int, int, int]:
    """A portrait too light for the dark-pixel rule (Alemán's) gets the median oval size of the other secretaries,
    centred on its crop (the crops are centred on the ovals)."""
    w = int(np.median([ovals[k][2] - ovals[k][0] for k in reference]))
    h = int(np.median([ovals[k][3] - ovals[k][1] for k in reference]))
    x0, y0, x1, y1 = boxes[key]
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    return cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2


def main() -> None:
    poster = Image.open(POSTER).convert("RGB")
    gray = np.asarray(poster.convert("L")).astype(float)
    boxes = {"avila_camacho": PRESIDENT_BOX}
    for key in PORTRAITS:
        crop = np.asarray(Image.open(FIG_DIR / f"1946_portrait_{key}.png").convert("L")).astype(float)
        x, y, score = locate(gray, crop)
        h, w = crop.shape
        boxes[key] = (x, y, x + w, y + h)
        print(f"{key:14s} at x={x}, y={y} (ncc {score:.2f})")
    ovals = {k: oval_bbox(gray, b) for k, b in boxes.items()}
    px0, _, px1, _ = ovals["avila_camacho"]
    ovals["avila_camacho"] = (px0, PRESIDENT_ROWS[0], px1, PRESIDENT_ROWS[1])
    others = [k for k in PORTRAITS if k != "aleman"]
    ovals["aleman"] = standard_oval(boxes, ovals, "aleman", others)
    for k, (x0, y0, x1, y1) in ovals.items():
        print(f"{k:14s} oval {x1 - x0}x{y1 - y0} at ({x0}, {y0})")

    def draw(path: Path, style: dict[str, tuple[str, int]]) -> None:
        im = poster.copy()
        d = ImageDraw.Draw(im)
        for k, (colour, width) in style.items():
            x0, y0, x1, y1 = ovals[k]
            d.ellipse((x0 - MARGIN, y0 - MARGIN, x1 + MARGIN, y1 + MARGIN), outline=colour, width=width)
        im.save(path)
        print("written:", path)

    draw(FIG_DIR / "1946_cabinet_contenders_circled.png",
         {"avila_camacho": (INK, WIDTH), **{k: (ACCENT, WIDTH) for k in PORTRAITS}})
    draw(FIG_DIR / "1946_cabinet_designee.png",
         {"avila_camacho": (INK, WIDTH), "aleman": (ACCENT, WIDTH + 4), **{k: (GREY, WIDTH - 1) for k in PORTRAITS if k != "aleman"}})


if __name__ == "__main__":
    main()
