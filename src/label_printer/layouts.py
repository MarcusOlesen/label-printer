"""The label designs.

Every layout is a function ``draw(c, x, y, w, h, label)`` that draws one label
into the box (x, y)..(x + w, y + h) of a ReportLab canvas. Positions are
measured from the top of the box, so a layout looks the same in the top and
the bottom half of the page.
"""

import os
from collections.abc import Callable
from pathlib import Path

from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from .model import DISCLAIMER, Label
from .parsing import format_dkk, split_name

# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------

# Calibri matches the old Word labels; Arial and ReportLab's built-in
# Helvetica are fallbacks for machines without it.
_FONT_CANDIDATES = [("calibri.ttf", "calibrib.ttf"), ("arial.ttf", "arialbd.ttf")]
FONT, FONT_BOLD = "Helvetica", "Helvetica-Bold"


def register_fonts() -> None:
    """Use the first available Windows font pair instead of Helvetica."""
    global FONT, FONT_BOLD
    font_dir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    for regular, bold in _FONT_CANDIDATES:
        if (font_dir / regular).exists() and (font_dir / bold).exists():
            pdfmetrics.registerFont(TTFont("LabelFont", str(font_dir / regular)))
            pdfmetrics.registerFont(TTFont("LabelFont-Bold", str(font_dir / bold)))
            FONT, FONT_BOLD = "LabelFont", "LabelFont-Bold"
            return


# ---------------------------------------------------------------------------
# Text fitting helpers
# ---------------------------------------------------------------------------


def _fit_size(text: str, font: str, size: float, min_size: float, max_width: float) -> float:
    """Shrink the font size (not below min_size) until the text fits."""
    while size > min_size and pdfmetrics.stringWidth(text, font, size) > max_width:
        size -= 0.5
    return size


def _wrap(text: str, font: str, size: float, max_width: float) -> list[str]:
    """Greedy word wrap; words longer than a line are kept whole."""
    lines, current = [], ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if current and pdfmetrics.stringWidth(trial, font, size) > max_width:
            lines.append(current)
            current = word
        else:
            current = trial
    return lines + [current] if current else lines


def _fit_lines(text, font, size, min_size, width, max_lines=2):
    """Fit text on one line by shrinking down to min_size; beyond that wrap
    at min_size, and keep shrinking only if it still needs > max_lines."""
    fitted = _fit_size(text, font, size, min_size, width)
    if pdfmetrics.stringWidth(text, font, fitted) <= width:
        return fitted, [text]
    size = min_size
    lines = _wrap(text, font, size, width)
    while len(lines) > max_lines and size > 10:
        size -= 0.5
        lines = _wrap(text, font, size, width)
    return size, lines


def _draw_lines(c, lines, font, size, x, y_top, leading, align="left"):
    """Draw lines downwards from baseline y_top; returns the last baseline."""
    c.setFont(font, size)
    draw = {"left": c.drawString, "center": c.drawCentredString, "right": c.drawRightString}[align]
    y_line = y_top
    for i, line in enumerate(lines):
        y_line = y_top - i * leading
        draw(x, y_line, line)
    return y_line


def _price_line(c, caption, value, font, left, right, baseline, size=45):
    """Caption on the left, price on the right; shrinks only if they'd collide."""
    price = format_dkk(value)
    width = right - left
    while (
        size > 20
        and (
            pdfmetrics.stringWidth(caption, font, size) + pdfmetrics.stringWidth(price, font, size) + 10 * mm
        )
        > width
    ):
        size -= 1
    c.setFont(font, size)
    c.drawString(left, baseline, caption)
    c.drawRightString(right, baseline, price)


# ---------------------------------------------------------------------------
# Layouts
# ---------------------------------------------------------------------------


def draw_label_classic(c: Canvas, x, y, w, h, label: Label) -> None:
    """Reproduces the shop's old hand-made Word labels: prices on top, the
    full name in bold, the disclaimer and the item number underneath."""
    margin_x = 20 * mm
    name_size, name_min, name_wrap_size = 24, 18, 20
    # Baselines measured from the top of the label box.
    y_vejl, y_vores = 34 * mm, 58 * mm
    y_name, name_leading = 82 * mm, 9 * mm
    y_disclaimer, y_varenr = 104 * mm, 128 * mm

    left, right = x + margin_x, x + w - margin_x
    width = right - left
    top = y + h

    _price_line(c, "Vejl. salgspris:", label.vejl, FONT, left, right, top - y_vejl)
    _price_line(c, "Vores pris:", label.pris, FONT_BOLD, left, right, top - y_vores)

    size = _fit_size(label.navn, FONT_BOLD, name_size, name_min, width)
    if pdfmetrics.stringWidth(label.navn, FONT_BOLD, size) <= width:
        lines = [label.navn]
    else:
        size = name_wrap_size
        lines = _wrap(label.navn, FONT_BOLD, size, width)
        while len(lines) > 2 and size > 12:
            size -= 1
            lines = _wrap(label.navn, FONT_BOLD, size, width)
    # One or two lines are centred on the name baseline, so the disclaimer
    # below never moves.
    first = y_name - (len(lines) - 1) * name_leading / 2
    c.setFont(FONT_BOLD, size)
    for i, line in enumerate(lines):
        c.drawString(left, top - first - i * name_leading, line)

    c.setFont(FONT, 24)
    c.drawString(left, top - y_disclaimer, DISCLAIMER)
    c.drawRightString(right, top - y_varenr, label.varenr)


def draw_label_classic_clean(c: Canvas, x, y, w, h, label: Label) -> None:
    """Klassisk, but with the name split (see ``split_name``): the product in
    bold, the variant details (size, colour, ...) smaller underneath."""
    margin_x = 20 * mm
    title_size, title_min = 24, 20
    detail_size, detail_min = 20, 15
    y_vejl, y_vores = 34 * mm, 58 * mm
    y_name_top = 76 * mm
    y_disclaimer, y_varenr = 106 * mm, 128 * mm

    left, right = x + margin_x, x + w - margin_x
    width = right - left
    top = y + h

    _price_line(c, "Vejl. salgspris:", label.vejl, FONT, left, right, top - y_vejl)
    _price_line(c, "Vores pris:", label.pris, FONT_BOLD, left, right, top - y_vores)

    title, details = split_name(label.navn)
    t_size, t_lines = _fit_lines(title, FONT_BOLD, title_size, title_min, width)
    d_size, d_lines = (
        _fit_lines(details, FONT, detail_size, detail_min, width) if details else (detail_size, [])
    )
    total = len(t_lines) + len(d_lines)
    # A three-line name block is lifted a little so it clears the disclaimer.
    y_first = top - y_name_top + max(0, total - 2) * 4 * mm
    last = _draw_lines(c, t_lines, FONT_BOLD, t_size, left, y_first, t_size * 1.15)
    if d_lines:
        _draw_lines(c, d_lines, FONT, d_size, left, last - d_size * 1.35, d_size * 1.15)

    c.setFont(FONT, 24)
    c.drawString(left, top - y_disclaimer, DISCLAIMER)
    c.drawRightString(right, top - y_varenr, label.varenr)


def draw_label_modern(c: Canvas, x, y, w, h, label: Label) -> None:
    """Product name as the headline, our price as the big number, the
    disclaimer in a ruled footer together with the item number."""
    margin_x = 18 * mm
    title_size, title_min = 34, 26
    detail_size, detail_min = 19, 14
    y_title, y_vejl = 30 * mm, 72 * mm
    y_caption, y_price, price_size = 84 * mm, 110 * mm, 80
    y_rule, y_footer = 120 * mm, 130 * mm

    left, right = x + margin_x, x + w - margin_x
    width = right - left
    top = y + h

    title, details = split_name(label.navn)
    t_size, t_lines = _fit_lines(title, FONT_BOLD, title_size, title_min, width)
    last = _draw_lines(c, t_lines, FONT_BOLD, t_size, left, top - y_title, t_size * 1.1)
    if details:
        d_size, d_lines = _fit_lines(details, FONT, detail_size, detail_min, width)
        c.setFillGray(0.3)
        _draw_lines(c, d_lines, FONT, d_size, left, last - d_size * 1.5, d_size * 1.15)
        c.setFillGray(0)

    c.setFont(FONT, 22)
    c.drawString(left, top - y_vejl, "Vejl. salgspris")
    c.drawRightString(right, top - y_vejl, format_dkk(label.vejl))

    c.setFont(FONT_BOLD, 14)
    c.drawString(left, top - y_caption, "VORES PRIS")
    price = format_dkk(label.pris)
    c.setFont(FONT_BOLD, _fit_size(price, FONT_BOLD, price_size, 40, width))
    c.drawString(left, top - y_price, price)

    c.setLineWidth(1.2)
    c.line(left, top - y_rule, right, top - y_rule)
    c.setFont(FONT_BOLD, 17)
    c.drawString(left, top - y_footer, DISCLAIMER)
    c.setFont(FONT, 17)
    c.drawRightString(right, top - y_footer, f"Varenr. {label.varenr}")


def draw_label_big_price(c: Canvas, x, y, w, h, label: Label) -> None:
    """Centred and price-first, readable from across the showroom."""
    margin_x = 18 * mm
    y_vejl = 24 * mm
    y_price, price_size = 62 * mm, 100
    y_save, y_title = 76 * mm, 94 * mm
    title_size, title_min = 22, 18
    detail_size, detail_min = 15, 12
    y_disclaimer, y_varenr = 126 * mm, 136 * mm

    left, right = x + margin_x, x + w - margin_x
    width = right - left
    cx = x + w / 2
    top = y + h

    c.setFont(FONT, 22)
    c.drawCentredString(cx, top - y_vejl, f"Vejl. salgspris {format_dkk(label.vejl)}".strip())

    price = format_dkk(label.pris)
    c.setFont(FONT_BOLD, _fit_size(price, FONT_BOLD, price_size, 50, width))
    c.drawCentredString(cx, top - y_price, price)

    if label.vejl and label.pris and label.vejl > label.pris:
        c.setFont(FONT_BOLD, 18)
        c.drawCentredString(cx, top - y_save, f"Du sparer {format_dkk(label.vejl - label.pris)}")

    title, details = split_name(label.navn)
    t_size, t_lines = _fit_lines(title, FONT_BOLD, title_size, title_min, width)
    last = _draw_lines(c, t_lines, FONT_BOLD, t_size, cx, top - y_title, t_size * 1.15, "center")
    if details:
        d_size, d_lines = _fit_lines(details, FONT, detail_size, detail_min, width)
        c.setFillGray(0.3)
        _draw_lines(c, d_lines, FONT, d_size, cx, last - d_size * 1.4, d_size * 1.15, "center")
        c.setFillGray(0)

    c.setFont(FONT_BOLD, 16)
    c.drawCentredString(cx, top - y_disclaimer, DISCLAIMER)
    c.setFont(FONT, 12)
    c.drawRightString(right, top - y_varenr, label.varenr)


DrawFunction = Callable[[Canvas, float, float, float, float, Label], None]

# key -> (name shown in the GUI, draw function)
LAYOUTS: dict[str, tuple[str, DrawFunction]] = {
    "classic": ("Klassisk", draw_label_classic),
    "classic_clean": ("Klassisk – pæne navne", draw_label_classic_clean),
    "modern": ("Moderne", draw_label_modern),
    "big_price": ("Stor pris", draw_label_big_price),
}
# The factory default. Users can save another one from the GUI (settings.py).
DEFAULT_LAYOUT = "classic"
