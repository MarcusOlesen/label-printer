"""Draws label_printer.ico (the Label Printer app icon).

Same visual family as label_miner.ico -- full-bleed coloured square, pale
rounded card with a diagonal highlight, a bold tag in the middle -- but in
a warm orange so the two apps are easy to tell apart on the desktop.

Run from the repository root:  python packaging/make_icon.py
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
S = 1024  # draw big, downscale for crisp small sizes
ORANGE = (217, 98, 43, 255)
CARD = (253, 234, 222, 255)
WHITE = (255, 255, 255, 255)
SIZES = [16, 24, 32, 48, 64, 128, 256]


def font(size):
    for name in ("segoeuib.ttf", "calibrib.ttf", "arialbd.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def draw_icon(text="kr"):
    img = Image.new("RGBA", (S, S), ORANGE)

    # Pale card with the same diagonal highlight as the Label Miner icon.
    card = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(card).rounded_rectangle((104, 104, S - 104, S - 104), radius=150, fill=CARD)
    shine = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shine)
    sd.polygon([(0, 330), (330, 0), (400, 0), (0, 400)], fill=WHITE)
    sd.polygon([(S, S - 330), (S - 330, S), (S - 400, S), (S, S - 400)], fill=WHITE)
    card.alpha_composite(Image.composite(shine, Image.new("RGBA", (S, S)), card))
    img.alpha_composite(card)

    # Price tag: pointed left end, rounded corners, punched hole, drawn flat
    # then rotated so it reads as a hanging tag.
    tag = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    td = ImageDraw.Draw(tag)
    pts = [(215, 512), (370, 335), (815, 335), (815, 689), (370, 689)]
    td.polygon(pts, fill=ORANGE)
    td.line(pts + [pts[0]], fill=ORANGE, width=70, joint="curve")
    for x, y in pts:  # round the corners the line join leaves square
        td.ellipse((x - 35, y - 35, x + 35, y + 35), fill=ORANGE)
    td.ellipse((278, 472, 358, 552), fill=CARD)
    f = font(300 if len(text) <= 2 else 220)
    td.text((610, 502), text, font=f, fill=WHITE, anchor="mm")
    tag = tag.rotate(20, resample=Image.BICUBIC, center=(512, 512))
    img.alpha_composite(tag)
    return img


def save_ico(img, path):
    img.save(path, format="ICO", sizes=[(s, s) for s in SIZES])


if __name__ == "__main__":
    text = sys.argv[1] if len(sys.argv) > 1 else "kr"
    default = ROOT / "src" / "label_printer" / "assets" / "label_printer.ico"
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else default
    icon = draw_icon(text)
    save_ico(icon, out)
    print(f"wrote {out}")
