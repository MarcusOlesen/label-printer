"""Label Printer -- turn rows pasted from the Google Sheet into price labels.

Paste rows (copied from column A, no header, same column order as the Label
Miner output) and get a PDF with two labels per A4 page. Each label occupies
exactly one half of the page (210 x 148.5 mm), so a printed sheet can be cut
straight across the middle.

Usage:
    python label_printer.py                              # GUI
    python label_printer.py --paste rows.tsv --out x.pdf # headless (testing)
"""
import argparse
import csv
import io
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

# Column positions in the pasted rows (0-based, Label Miner order).
COL_VARENR = 0      # A  Varenummer (our own internal number)
COL_NAVN = 1        # B  Varenavn
COL_STK = 5         # F  STK
COL_VEJL = 7        # H  Vejledende priser
COL_PRIS = 8        # I  Pris pr stk
MIN_COLS = COL_PRIS + 1

DRAW_CUT_LINE = True
DISCLAIMER = "KØBT SOM BESET, UDEN RETURRET!"


@dataclass
class Label:
    varenr: str
    navn: str
    vejl: int | None
    pris: int | None
    stk: int
    line: int               # 1-based row number in the pasted text
    problems: list[str]
    bad_cols: list[int] = field(default_factory=list)   # columns to highlight in the GUI


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------

_NUMBER_RE = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?")


def _to_int(num: str) -> int:
    """'1.699' -> 1699, '1.699,50' -> 1700, '1699' -> 1699."""
    whole, _, frac = num.partition(",")
    value = int(whole.replace(".", ""))
    if frac and int(frac[0]) >= 5:
        value += 1
    return value


def parse_price(text: str) -> int | None:
    """First number in a cell like '1.000 kr' / '~1000' / '1.000,00'."""
    m = _NUMBER_RE.search((text or "").replace(" ", ""))
    return _to_int(m.group(0)) if m else None


def parse_vejl(text: str) -> int | None:
    """Highest number in the recommended-price column: '8.999 kr (11.999 kr)' -> 11999."""
    nums = [_to_int(n) for n in _NUMBER_RE.findall((text or "").replace(" ", ""))]
    return max(nums) if nums else None


def format_dkk(value: int) -> str:
    return f"{value:,}".replace(",", ".") + ",-"


def parse_paste(text: str) -> list[Label]:
    return parse_rows(csv.reader(io.StringIO(text.strip("\r\n")), delimiter="\t"))


def parse_rows(rows) -> list[Label]:
    labels = []
    for line_no, row in enumerate(rows, start=1):
        row = ["" if cell is None else str(cell) for cell in row]
        if not any(cell.strip() for cell in row):
            continue
        if row[0].strip().lower() == "varenummer":
            continue  # a header row was pasted anyway
        problems = []
        if len(row) < MIN_COLS:
            problems.append("for få kolonner (start markeringen i kolonne A)")
        row = [cell.strip() for cell in row] + [""] * max(0, MIN_COLS - len(row))

        varenr, navn = row[COL_VARENR], row[COL_NAVN]
        vejl, pris = parse_vejl(row[COL_VEJL]), parse_price(row[COL_PRIS])
        stk = parse_price(row[COL_STK])
        stk = 1 if stk is None else stk

        bad_cols = []
        for ok, col, msg in [(varenr, COL_VARENR, "mangler varenummer"),
                             (navn, COL_NAVN, "mangler varenavn"),
                             (vejl is not None, COL_VEJL, "mangler vejl. pris"),
                             (pris is not None, COL_PRIS, "mangler pris pr stk"),
                             (stk >= 1, COL_STK, "STK skal være mindst 1")]:
            if not ok:
                problems.append(msg)
                bad_cols.append(col)
        labels.append(Label(varenr, navn, vejl, pris, stk, line_no, problems, bad_cols))
    return labels


def expand(labels: list[Label]) -> list[Label]:
    """One entry per physical label (STK = 2 -> two labels)."""
    return [lab for lab in labels for _ in range(lab.stk)]


# --------------------------------------------------------------------------
# Fonts
# --------------------------------------------------------------------------

_FONT_CANDIDATES = [("calibri.ttf", "calibrib.ttf"), ("arial.ttf", "arialbd.ttf")]
FONT, FONT_BOLD = "Helvetica", "Helvetica-Bold"


def register_fonts():
    global FONT, FONT_BOLD
    font_dir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    for regular, bold in _FONT_CANDIDATES:
        if (font_dir / regular).exists() and (font_dir / bold).exists():
            pdfmetrics.registerFont(TTFont("LabelFont", str(font_dir / regular)))
            pdfmetrics.registerFont(TTFont("LabelFont-Bold", str(font_dir / bold)))
            FONT, FONT_BOLD = "LabelFont", "LabelFont-Bold"
            return


# --------------------------------------------------------------------------
# Layouts -- each draws one label into the box (x, y) .. (x + w, y + h)
# --------------------------------------------------------------------------

def _fit_size(text, font, size, min_size, max_width):
    while size > min_size and pdfmetrics.stringWidth(text, font, size) > max_width:
        size -= 0.5
    return size


def _wrap(text, font, size, max_width):
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


def draw_label_classic(c, x, y, w, h, label: Label):
    """Same layout as Dokument1.docx."""
    MARGIN_X = 20 * mm
    PRICE_SIZE = 45
    NAME_SIZE, NAME_MIN, NAME_WRAP_SIZE = 24, 18, 20
    TEXT_SIZE = 24
    # Baselines measured from the top of the label box.
    Y_VEJL, Y_VORES = 34 * mm, 58 * mm
    Y_NAME, NAME_LEADING = 82 * mm, 9 * mm
    Y_DISCLAIMER = 104 * mm
    Y_VARENR = 128 * mm

    left, right = x + MARGIN_X, x + w - MARGIN_X
    width = right - left
    top = y + h

    def price_line(caption, value, font, baseline):
        price = format_dkk(value)
        # Shrink only if caption + price would collide.
        size = PRICE_SIZE
        while size > 20 and (pdfmetrics.stringWidth(caption, font, size)
                             + pdfmetrics.stringWidth(price, font, size) + 10 * mm) > width:
            size -= 1
        c.setFont(font, size)
        c.drawString(left, top - baseline, caption)
        c.drawRightString(right, top - baseline, price)

    price_line("Vejl. salgspris:", label.vejl, FONT, Y_VEJL)
    price_line("Vores pris:", label.pris, FONT_BOLD, Y_VORES)

    size = _fit_size(label.navn, FONT_BOLD, NAME_SIZE, NAME_MIN, width)
    if pdfmetrics.stringWidth(label.navn, FONT_BOLD, size) <= width:
        lines = [label.navn]
    else:
        size = NAME_WRAP_SIZE
        lines = _wrap(label.navn, FONT_BOLD, size, width)
        while len(lines) > 2 and size > 12:
            size -= 1
            lines = _wrap(label.navn, FONT_BOLD, size, width)
    # Centre one or two lines around the name baseline so the disclaimer never moves.
    first = Y_NAME - (len(lines) - 1) * NAME_LEADING / 2
    c.setFont(FONT_BOLD, size)
    for i, line in enumerate(lines):
        c.drawString(left, top - first - i * NAME_LEADING, line)

    c.setFont(FONT, TEXT_SIZE)
    c.drawString(left, top - Y_DISCLAIMER, DISCLAIMER)
    c.drawRightString(right, top - Y_VARENR, label.varenr)


def split_name(navn: str) -> tuple[str, str]:
    """'Balo spisebord, egetræ | butterfly udtræk | 190/290x95 Eg'
    -> ('Balo spisebord, egetræ', 'butterfly udtræk · 190/290x95 Eg').
    Names without ' | ' have no reliable split point and stay whole."""
    parts = [p.strip() for p in navn.split("|") if p.strip()]
    if len(parts) < 2:
        return navn.strip(), ""
    return parts[0], " · ".join(parts[1:])


def _fit_lines(text, font, size, min_size, width, max_lines=2):
    """Keep one line by shrinking down to min_size; beyond that wrap at
    min_size (and keep shrinking only if it still needs > max_lines)."""
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
    """Draw lines starting at baseline y_top (page coords), going down.
    Returns the baseline of the last line."""
    c.setFont(font, size)
    draw = {"left": c.drawString, "center": c.drawCentredString,
            "right": c.drawRightString}[align]
    y_line = y_top
    for i, line in enumerate(lines):
        y_line = y_top - i * leading
        draw(x, y_line, line)
    return y_line


def draw_label_classic_clean(c, x, y, w, h, label: Label):
    """Klassisk, but the name is split at ' | ': the product in bold on the
    first line, the variant details (size, colour, ...) smaller underneath.
    Every label gets the same name size unless a name really doesn't fit."""
    MARGIN_X = 20 * mm
    PRICE_SIZE = 45
    TITLE_SIZE, TITLE_MIN = 24, 20
    DETAIL_SIZE, DETAIL_MIN = 20, 15
    TEXT_SIZE = 24
    Y_VEJL, Y_VORES = 34 * mm, 58 * mm
    Y_NAME_TOP = 76 * mm          # first name baseline
    Y_DISCLAIMER = 106 * mm
    Y_VARENR = 128 * mm

    left, right = x + MARGIN_X, x + w - MARGIN_X
    width = right - left
    top = y + h

    for caption, value, font, baseline in [("Vejl. salgspris:", label.vejl, FONT, Y_VEJL),
                                           ("Vores pris:", label.pris, FONT_BOLD, Y_VORES)]:
        price = format_dkk(value)
        size = PRICE_SIZE
        while size > 20 and (pdfmetrics.stringWidth(caption, font, size)
                             + pdfmetrics.stringWidth(price, font, size) + 10 * mm) > width:
            size -= 1
        c.setFont(font, size)
        c.drawString(left, top - baseline, caption)
        c.drawRightString(right, top - baseline, price)

    title, details = split_name(label.navn)
    t_size, t_lines = _fit_lines(title, FONT_BOLD, TITLE_SIZE, TITLE_MIN, width)
    d_size, d_lines = (_fit_lines(details, FONT, DETAIL_SIZE, DETAIL_MIN, width)
                       if details else (DETAIL_SIZE, []))
    total = len(t_lines) + len(d_lines)
    # Lift the block a little when it runs to 3 lines so it clears the disclaimer.
    y_first = top - Y_NAME_TOP + max(0, total - 2) * 4 * mm
    last = _draw_lines(c, t_lines, FONT_BOLD, t_size, left, y_first, t_size * 1.15)
    if d_lines:
        _draw_lines(c, d_lines, FONT, d_size, left, last - d_size * 1.35, d_size * 1.15)

    c.setFont(FONT, TEXT_SIZE)
    c.drawString(left, top - Y_DISCLAIMER, DISCLAIMER)
    c.drawRightString(right, top - Y_VARENR, label.varenr)


def draw_label_modern(c, x, y, w, h, label: Label):
    """Product name as the headline, our price as the big number, the
    disclaimer in a ruled footer together with the varenummer."""
    MARGIN_X = 18 * mm
    TITLE_SIZE, TITLE_MIN = 34, 26
    DETAIL_SIZE, DETAIL_MIN = 19, 14
    Y_TITLE = 30 * mm
    Y_VEJL = 72 * mm
    Y_CAPTION, Y_PRICE = 84 * mm, 110 * mm
    PRICE_SIZE = 80
    Y_RULE, Y_FOOTER = 120 * mm, 130 * mm

    left, right = x + MARGIN_X, x + w - MARGIN_X
    width = right - left
    top = y + h

    title, details = split_name(label.navn)
    t_size, t_lines = _fit_lines(title, FONT_BOLD, TITLE_SIZE, TITLE_MIN, width)
    last = _draw_lines(c, t_lines, FONT_BOLD, t_size, left, top - Y_TITLE, t_size * 1.1)
    if details:
        d_size, d_lines = _fit_lines(details, FONT, DETAIL_SIZE, DETAIL_MIN, width)
        c.setFillGray(0.3)
        _draw_lines(c, d_lines, FONT, d_size, left, last - d_size * 1.5, d_size * 1.15)
        c.setFillGray(0)

    c.setFont(FONT, 22)
    c.drawString(left, top - Y_VEJL, "Vejl. salgspris")
    c.drawRightString(right, top - Y_VEJL, format_dkk(label.vejl))

    c.setFont(FONT_BOLD, 14)
    c.drawString(left, top - Y_CAPTION, "VORES PRIS")
    price = format_dkk(label.pris)
    size = _fit_size(price, FONT_BOLD, PRICE_SIZE, 40, width)
    c.setFont(FONT_BOLD, size)
    c.drawString(left, top - Y_PRICE, price)

    c.setLineWidth(1.2)
    c.line(left, top - Y_RULE, right, top - Y_RULE)
    c.setFont(FONT_BOLD, 17)
    c.drawString(left, top - Y_FOOTER, DISCLAIMER)
    c.setFont(FONT, 17)
    c.drawRightString(right, top - Y_FOOTER, f"Varenr. {label.varenr}")


def draw_label_big_price(c, x, y, w, h, label: Label):
    """Centred, price-first: readable from across the showroom."""
    MARGIN_X = 18 * mm
    Y_VEJL = 24 * mm
    Y_PRICE, PRICE_SIZE = 62 * mm, 100
    Y_SAVE = 76 * mm
    Y_TITLE = 94 * mm
    TITLE_SIZE, TITLE_MIN = 22, 18
    DETAIL_SIZE, DETAIL_MIN = 15, 12
    Y_DISCLAIMER, Y_VARENR = 126 * mm, 136 * mm

    left, right = x + MARGIN_X, x + w - MARGIN_X
    width = right - left
    cx = x + w / 2
    top = y + h

    c.setFont(FONT, 22)
    c.drawCentredString(cx, top - Y_VEJL, f"Vejl. salgspris {format_dkk(label.vejl)}")

    price = format_dkk(label.pris)
    size = _fit_size(price, FONT_BOLD, PRICE_SIZE, 50, width)
    c.setFont(FONT_BOLD, size)
    c.drawCentredString(cx, top - Y_PRICE, price)

    if label.vejl and label.pris and label.vejl > label.pris:
        c.setFont(FONT_BOLD, 18)
        c.drawCentredString(cx, top - Y_SAVE, f"Du sparer {format_dkk(label.vejl - label.pris)}")

    title, details = split_name(label.navn)
    t_size, t_lines = _fit_lines(title, FONT_BOLD, TITLE_SIZE, TITLE_MIN, width)
    last = _draw_lines(c, t_lines, FONT_BOLD, t_size, cx, top - Y_TITLE, t_size * 1.15, "center")
    if details:
        d_size, d_lines = _fit_lines(details, FONT, DETAIL_SIZE, DETAIL_MIN, width)
        c.setFillGray(0.3)
        _draw_lines(c, d_lines, FONT, d_size, cx, last - d_size * 1.4, d_size * 1.15, "center")
        c.setFillGray(0)

    c.setFont(FONT_BOLD, 16)
    c.drawCentredString(cx, top - Y_DISCLAIMER, DISCLAIMER)
    c.setFont(FONT, 12)
    c.drawRightString(right, top - Y_VARENR, label.varenr)


# key -> (name shown in the GUI, draw function). The first entry is the default.
LAYOUTS = {
    "classic": ("Klassisk", draw_label_classic),
    "classic_clean": ("Klassisk – pæne navne", draw_label_classic_clean),
    "modern": ("Moderne", draw_label_modern),
    "big_price": ("Stor pris", draw_label_big_price),
}
DEFAULT_LAYOUT = "classic"


def build_pdf(labels: list[Label], path, layout: str = DEFAULT_LAYOUT) -> int:
    """Write the PDF; returns the number of pages."""
    register_fonts()
    draw = LAYOUTS[layout][1]
    page_w, page_h = A4
    half = page_h / 2
    items = expand(labels)
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setTitle("Etiketter")
    pages = 0
    for i in range(0, len(items), 2):
        pair = items[i:i + 2]
        draw(c, 0, half, page_w, half, pair[0])            # top half
        if len(pair) > 1:
            draw(c, 0, 0, page_w, half, pair[1])           # bottom half
        if DRAW_CUT_LINE:
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


# --------------------------------------------------------------------------
# Preview rendering (optional: needs pypdfium2 + Pillow)
# --------------------------------------------------------------------------

def render_label_image(label: Label, width_px: int, layout: str = DEFAULT_LAYOUT):
    """One label as a PIL image, or None if pypdfium2 isn't installed."""
    try:
        import pypdfium2
    except ImportError:
        return None
    register_fonts()
    page_w, page_h = A4[0], A4[1] / 2
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_w, page_h))
    LAYOUTS[layout][1](c, 0, 0, page_w, page_h, label)
    c.showPage()
    c.save()
    pdf = pypdfium2.PdfDocument(buf.getvalue())
    return pdf[0].render(scale=width_px / page_w).to_pil()


# --------------------------------------------------------------------------
# GUI
# --------------------------------------------------------------------------

SHEET_HEADERS = ["Varenummer", "Varenavn", "MK Varenummer", "MK ordrenr", "STAND", "STK",
                 "Modtaget", "Vejl. priser", "Pris pr stk", "Pris samlet",
                 "URL", "Image name"]
USED_COLS = [COL_VARENR, COL_NAVN, COL_STK, COL_VEJL, COL_PRIS]
COL_WIDTHS = {COL_VARENR: 100, COL_NAVN: 280, COL_STK: 45, COL_VEJL: 175, COL_PRIS: 90}
UNUSED_COL_WIDTH = 45  # pasted but not printed: keep narrow so the prices stay in view
EMPTY_ROWS = 40

UI_FONT = "Segoe UI"
C = {  # matches the sv-ttk dark theme used by Label Miner
    "bg": "#1c1c1c", "card": "#262626", "table": "#202020", "header": "#2d2d2d",
    "grid": "#3a3a3a", "fg": "#fafafa", "muted": "#8b8b8b", "faint": "#5f5f5f",
    "accent": "#57c8ff", "ok": "#6fcf97", "bad": "#ff8a8a", "bad_bg": "#5a2828",
    "select": "#1f4a63",
}


class LabelPrinterApp:
    def __init__(self, root):
        import tkinter as tk
        from tkinter import ttk
        from tksheet import Sheet

        self.tk, self.ttk = tk, ttk
        self.root = root
        self.labels: list[Label] = []
        self.bad_cells: set[tuple[int, int]] = set()
        self.bad_rows: set[int] = set()
        self.preview_image = None
        self.save_dir = str(Path.home() / "Desktop")
        self._validate_job = self._preview_job = None
        self._problem_targets = []

        root.title("Label Printer")
        root.geometry("1360x800")
        root.minsize(1000, 620)
        try:
            root.state("zoomed")  # the table benefits from all the room it can get
        except tk.TclError:
            pass
        root.configure(bg=C["bg"])
        ico = Path(__file__).with_name("label_miner.ico")
        if ico.exists():
            try:
                root.iconbitmap(str(ico))
            except tk.TclError:
                pass
        self._apply_theme()

        # ---- header -------------------------------------------------------
        header = ttk.Frame(root, padding=(20, 16, 20, 8))
        header.pack(fill="x")
        titles = ttk.Frame(header)
        titles.pack(side="left")
        ttk.Label(titles, text="Label Printer", font=(UI_FONT, 18, "bold")).pack(anchor="w")
        ttk.Label(titles, foreground=C["muted"],
                  text="Kopiér rækkerne i Google Sheets (marker fra kolonne A) og indsæt dem i "
                       "tabellen med Ctrl+V. Du kan rette direkte i cellerne.").pack(anchor="w")
        ttk.Button(header, text="Ryd tabel", command=self.clear).pack(side="right")
        ttk.Button(header, text="Indsæt fra udklipsholder", command=self.paste_replace
                   ).pack(side="right", padx=8)

        # ---- body: sheet + sidebar ---------------------------------------
        body = ttk.Frame(root, padding=(20, 8, 20, 20))
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        self.sheet = Sheet(
            body, headers=SHEET_HEADERS, data=self._blank_rows(EMPTY_ROWS),
            theme="dark", font=(UI_FONT, 10, "normal"), header_font=(UI_FONT, 10, "bold"),
            index_font=(UI_FONT, 9, "normal"), default_row_height=28, default_header_height=34,
            paste_can_expand_y=True, paste_can_expand_x=False, expand_sheet_if_paste_too_big=True,
            show_selected_cells_border=True,
        )
        self._style_sheet()
        self.sheet.enable_bindings("all")
        self.sheet.disable_bindings("edit_header", "edit_index", "rename_columns")
        self.sheet.grid(row=0, column=0, sticky="nsew")
        self.sheet.bind("<<SheetModified>>", lambda e: self._schedule_validate())
        self.sheet.bind("<<SheetSelect>>", lambda e: self._schedule_preview())
        root.bind_all("<Control-v>", self._global_paste, add="+")

        self._build_sidebar(body)
        self.sheet.select_cell(0, 0)
        self.sheet.focus_set()
        self.validate()

    # ---- setup -----------------------------------------------------------
    def _apply_theme(self):
        ttk = self.ttk
        try:
            import sv_ttk
            sv_ttk.set_theme("dark")
        except ImportError:
            pass
        self.root.option_add("*Font", (UI_FONT, 10))
        style = ttk.Style(self.root)
        style.configure(".", font=(UI_FONT, 10))
        style.configure("Big.Accent.TButton", font=(UI_FONT, 12, "bold"), padding=(20, 12))

    def _style_sheet(self):
        options = dict(
            frame_bg=C["bg"], table_bg=C["table"], table_fg=C["fg"], table_grid_fg=C["grid"],
            header_bg=C["header"], header_fg=C["muted"], header_grid_fg=C["grid"],
            header_border_fg=C["grid"], index_bg=C["header"], index_fg=C["muted"],
            index_grid_fg=C["grid"], index_border_fg=C["grid"], top_left_bg=C["header"],
            top_left_fg=C["header"], table_selected_cells_bg=C["select"],
            table_selected_cells_border_fg=C["accent"], header_selected_cells_bg=C["select"],
            header_selected_cells_fg=C["fg"], index_selected_cells_bg=C["select"],
            index_selected_cells_fg=C["fg"], table_editor_bg=C["card"], table_editor_fg=C["fg"],
        )
        for key, value in options.items():  # tolerate option names changing between versions
            try:
                self.sheet.set_options(**{key: value}, redraw=False)
            except Exception:
                pass
        for col in range(len(SHEET_HEADERS)):
            self.sheet.column_width(col, COL_WIDTHS.get(col, UNUSED_COL_WIDTH), redraw=False)
        unused = [c for c in range(len(SHEET_HEADERS)) if c not in USED_COLS]
        self.sheet.highlight_columns(unused, fg=C["faint"], redraw=False)
        for col in USED_COLS:  # the columns that end up on the label stand out
            self.sheet.highlight_cells(column=col, canvas="header", fg=C["accent"], redraw=False)
        self.sheet.refresh()

    def _build_sidebar(self, parent):
        # Plain tk widgets here: sv-ttk draws ttk frames/labels with images and
        # ignores custom backgrounds, which leaves grey patches on the card.
        tk = self.tk
        side = tk.Frame(parent, bg=C["card"], width=370, padx=18, pady=14,
                        highlightthickness=1, highlightbackground=C["grid"])
        side.grid(row=0, column=1, sticky="nsew", padx=(16, 0))
        side.grid_propagate(False)
        side.columnconfigure(0, weight=1)

        def label(parent, **kw):
            kw.setdefault("bg", C["card"])
            kw.setdefault("fg", C["fg"])
            kw.setdefault("font", (UI_FONT, 10))
            return tk.Label(parent, anchor="w", justify="left", **kw)

        stats = tk.Frame(side, bg=C["card"])
        stats.grid(row=0, column=0, sticky="ew")
        self.stat_vars = {}
        for i, (key, caption) in enumerate([("rows", "rækker"), ("labels", "etiketter"),
                                            ("pages", "sider")]):
            stats.columnconfigure(i, weight=1, uniform="stat")
            var = tk.StringVar(value="0")
            self.stat_vars[key] = var
            label(stats, textvariable=var, font=(UI_FONT, 22, "bold"),
                  fg=C["accent"] if key == "labels" else C["fg"]).grid(row=0, column=i, sticky="w")
            label(stats, text=caption, fg=C["muted"], font=(UI_FONT, 9)
                  ).grid(row=1, column=i, sticky="w")

        tk.Frame(side, bg=C["grid"], height=1).grid(row=1, column=0, sticky="ew", pady=12)

        self.status_label = label(side, font=(UI_FONT, 11, "bold"), wraplength=340)
        self.status_label.grid(row=2, column=0, sticky="ew")
        self.problem_list = tk.Listbox(
            side, height=3, activestyle="none", borderwidth=0, highlightthickness=0,
            bg=C["card"], fg=C["bad"], selectbackground=C["select"], selectforeground=C["fg"],
            font=(UI_FONT, 10), cursor="hand2")
        self.problem_list.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        self.problem_list.bind("<<ListboxSelect>>", self._jump_to_problem)

        self.preview_title = label(side, fg=C["muted"], font=(UI_FONT, 9, "bold"))
        self.preview_title.grid(row=4, column=0, sticky="ew", pady=(10, 6))
        self.preview = tk.Label(side, bg=C["table"], fg=C["muted"], font=(UI_FONT, 10),
                                height=12, text="Ingen gyldige rækker endnu.")
        self.preview.grid(row=5, column=0, sticky="new")
        label(side, text="Klik på en række for at se dens etiket.", fg=C["faint"],
              font=(UI_FONT, 9)).grid(row=6, column=0, sticky="ew", pady=(6, 0))

        layout_row = tk.Frame(side, bg=C["card"])
        layout_row.grid(row=7, column=0, sticky="ew", pady=(14, 0))
        layout_row.columnconfigure(1, weight=1)
        label(layout_row, text="LAYOUT", fg=C["muted"], font=(UI_FONT, 9, "bold")
              ).grid(row=0, column=0, sticky="w", padx=(0, 12))
        self.layout_names = {name: key for key, (name, _) in LAYOUTS.items()}
        self.layout_var = tk.StringVar(value=LAYOUTS[DEFAULT_LAYOUT][0])
        combo = self.ttk.Combobox(layout_row, textvariable=self.layout_var, state="readonly",
                                  values=list(self.layout_names))
        combo.grid(row=0, column=1, sticky="ew")
        combo.bind("<<ComboboxSelected>>", lambda e: (combo.selection_clear(),
                                                      self._schedule_preview()))
        side.rowconfigure(8, weight=1)

        self.generate_btn = self.ttk.Button(side, text="Generér PDF", style="Big.Accent.TButton",
                                            command=self.generate)
        self.generate_btn.grid(row=9, column=0, sticky="ew")

    @staticmethod
    def _blank_rows(n):
        return [[""] * len(SHEET_HEADERS) for _ in range(n)]

    # ---- pasting ---------------------------------------------------------
    def paste_replace(self):
        """Replace the whole table with the clipboard contents."""
        try:
            text = self.root.clipboard_get()
        except self.tk.TclError:
            return
        rows = [(row + [""] * len(SHEET_HEADERS))[:len(SHEET_HEADERS)]
                for row in csv.reader(io.StringIO(text.strip("\r\n")), delimiter="\t")]
        rows += self._blank_rows(max(0, EMPTY_ROWS - len(rows)))
        self.sheet.set_sheet_data(rows, reset_col_positions=False)
        self.sheet.select_cell(0, 0)
        self.validate()

    def _global_paste(self, event):
        # tksheet handles Ctrl+V itself when a cell is selected; otherwise
        # (focus on a button, nothing selected) paste the whole clipboard.
        if not self.sheet.get_currently_selected():
            self.paste_replace()

    def clear(self):
        self.sheet.set_sheet_data(self._blank_rows(EMPTY_ROWS), reset_col_positions=False)
        self.sheet.select_cell(0, 0)
        self.validate()

    # ---- validation ------------------------------------------------------
    def _schedule_validate(self):
        if self._validate_job:
            self.root.after_cancel(self._validate_job)
        self._validate_job = self.root.after(120, self.validate)

    def validate(self):
        self._validate_job = None
        self.labels = parse_rows(self.sheet.get_sheet_data())
        bad = [lab for lab in self.labels if lab.problems]

        new_cells = {(lab.line - 1, col) for lab in bad for col in lab.bad_cols}
        new_rows = {lab.line - 1 for lab in bad}
        stale = self.bad_cells - new_cells
        if stale:
            self.sheet.dehighlight_cells(cells=list(stale), redraw=False)
        for row in self.bad_rows - new_rows:
            self.sheet.dehighlight_cells(row=row, canvas="index", redraw=False)
        if new_cells:
            self.sheet.highlight_cells(cells=list(new_cells), bg=C["bad_bg"], redraw=False)
        for row in new_rows:
            self.sheet.highlight_cells(row=row, canvas="index", bg=C["bad_bg"], fg=C["fg"],
                                       redraw=False)
        self.bad_cells, self.bad_rows = new_cells, new_rows
        self.sheet.refresh()

        n = len(expand(self.labels))
        self.stat_vars["rows"].set(str(len(self.labels)))
        self.stat_vars["labels"].set(str(n))
        self.stat_vars["pages"].set(str((n + 1) // 2))

        self.problem_list.delete(0, "end")
        self._problem_targets = []
        for lab in bad:
            self.problem_list.insert("end", f"Række {lab.line}:  {', '.join(lab.problems)}")
            self._problem_targets.append((lab.line - 1, lab.bad_cols[0] if lab.bad_cols else 0))

        if not self.labels:
            self._set_status("Indsæt rækker for at komme i gang.", C["muted"])
        elif bad:
            self._set_status(f"{len(bad)} række{'r' if len(bad) > 1 else ''} skal rettes:", C["bad"])
        else:
            self._set_status("✓  Klar til udskrift", C["ok"])
        self.generate_btn.state(["!disabled"] if self.labels and not bad else ["disabled"])
        self._schedule_preview()

    def _set_status(self, text, color):
        self.status_label.configure(text=text, fg=color)

    def _jump_to_problem(self, _event):
        sel = self.problem_list.curselection()
        if not sel:
            return
        row, col = self._problem_targets[sel[0]]
        self.sheet.see(row, col)
        self.sheet.select_cell(row, col)
        self.sheet.focus_set()

    # ---- preview ---------------------------------------------------------
    def _schedule_preview(self):
        if self._preview_job:
            self.root.after_cancel(self._preview_job)
        self._preview_job = self.root.after(80, self.update_preview)

    def update_preview(self):
        self._preview_job = None
        selected = self.sheet.get_currently_selected()
        row = selected.row if selected else None
        by_row = {lab.line - 1: lab for lab in self.labels}
        label = by_row.get(row)
        if label is None or label.problems:
            label = next((lab for lab in self.labels if not lab.problems), None)
        if label is None:
            self.preview.configure(image="", text="Ingen gyldige rækker endnu.", height=12)
            self.preview_title.configure(text="FORHÅNDSVISNING")
            return
        self.preview_title.configure(text=f"FORHÅNDSVISNING  ·  RÆKKE {label.line}")
        image = render_label_image(label, 330, self.layout)
        if image is None:
            self.preview.configure(image="", text="Installer pypdfium2 for forhåndsvisning.")
            return
        from PIL import ImageTk
        self.preview_image = ImageTk.PhotoImage(image)
        self.preview.configure(image=self.preview_image, text="", height=0)

    @property
    def layout(self):
        return self.layout_names.get(self.layout_var.get(), DEFAULT_LAYOUT)

    # ---- output ----------------------------------------------------------
    def generate(self):
        from tkinter import filedialog, messagebox
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf", filetypes=[("PDF", "*.pdf")], initialdir=self.save_dir,
            initialfile=f"etiketter_{date.today():%Y-%m-%d}.pdf")
        if not path:
            return
        try:
            pages = build_pdf(self.labels, path, self.layout)
        except PermissionError:
            messagebox.showerror("Label Printer",
                                 "Kunne ikke gemme filen – er den åben i en PDF-læser?")
            return
        self.save_dir = str(Path(path).parent)
        self._set_status(f"✓  Gemt {pages} sider: {Path(path).name}", C["ok"])
        os.startfile(path)


def run_gui():
    import tkinter as tk
    root = tk.Tk()
    LabelPrinterApp(root)
    root.mainloop()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--paste", help="tab-separated file with pasted rows (skips the GUI)")
    parser.add_argument("--out", default="etiketter.pdf")
    parser.add_argument("--layout", default=DEFAULT_LAYOUT, choices=list(LAYOUTS))
    args = parser.parse_args()
    if not args.paste:
        run_gui()
        return
    labels = parse_paste(Path(args.paste).read_text(encoding="utf-8"))
    bad = [lab for lab in labels if lab.problems]
    for lab in bad:
        print(f"linje {lab.line}: {', '.join(lab.problems)}", file=sys.stderr)
    if bad:
        sys.exit(1)
    pages = build_pdf(labels, args.out, args.layout)
    print(f"{len(expand(labels))} etiketter, {pages} sider -> {args.out}")


if __name__ == "__main__":
    main()
