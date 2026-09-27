"""Rendering labels: the printable PDF and single-label preview images."""

import io
from os import PathLike

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from . import layouts
from .layouts import DEFAULT_LAYOUT, LAYOUTS
from .model import Label
from .parsing import expand


def build_pdf(
    labels: list[Label],
    path: str | PathLike,
    layout: str = DEFAULT_LAYOUT,
    per_stk: bool = False,
    cut_line: bool = False,
) -> int:
    """Write the labels to a PDF, two per A4 page; returns the page count.

    Each label fills exactly one half of the page (210 x 148.5 mm), so a
    printed sheet is cut straight across the middle. Incomplete labels are
    skipped (see ``parsing.expand``).
    """
    layouts.register_fonts()
    draw = LAYOUTS[layout][1]
    page_w, page_h = A4
    half = page_h / 2
    items = expand(labels, per_stk)
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setTitle("Etiketter")
    # Default the print dialog to "Actual size": "Fit to page" would shrink
    # the labels and move the cut line.
    c.setViewerPreference("PrintScaling", "None")
    pages = 0
    for i in range(0, len(items), 2):
        pair = items[i : i + 2]
        draw(c, 0, half, page_w, half, pair[0])  # top half
        if len(pair) > 1:
            draw(c, 0, 0, page_w, half, pair[1])  # bottom half
        if cut_line:
            c.saveState()
            c.setStrokeGray(0.75)
            c.setLineWidth(0.5)
            c.setDash(4, 4)
            c.line(0, half, page_w, half)
            c.restoreState()
        c.showPage()
        pages += 1
    c.save()
    return pages


def render_label_image(label: Label, width_px: int, layout: str = DEFAULT_LAYOUT):
    """One label as a PIL image (for the GUI preview), or None when the
    optional pypdfium2 dependency isn't installed."""
    try:
        import pypdfium2
    except ImportError:
        return None
    layouts.register_fonts()
    page_w, page_h = A4[0], A4[1] / 2
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(page_w, page_h))
    LAYOUTS[layout][1](c, 0, 0, page_w, page_h, label)
    c.showPage()
    c.save()
    pdf = pypdfium2.PdfDocument(buffer.getvalue())
    return pdf[0].render(scale=width_px / page_w).to_pil()
