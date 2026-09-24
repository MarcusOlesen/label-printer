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
from dataclasses import dataclass
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
    labels = []
    rows = csv.reader(io.StringIO(text.strip("\r\n")), delimiter="\t")
    for line_no, row in enumerate(rows, start=1):
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
        try:
            stk = int(parse_price(row[COL_STK]) or 1)
        except ValueError:
            stk = 1

        if not varenr:
            problems.append("mangler varenummer")
        if not navn:
            problems.append("mangler varenavn")
        if vejl is None:
            problems.append("mangler vejl. pris")
        if pris is None:
            problems.append("mangler pris pr stk")
        if stk < 1:
            problems.append("STK < 1")
        labels.append(Label(varenr, navn, vejl, pris, stk, line_no, problems))
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


LAYOUTS = {"classic": draw_label_classic}


def build_pdf(labels: list[Label], path, layout: str = "classic") -> int:
    """Write the PDF; returns the number of pages."""
    register_fonts()
    draw = LAYOUTS[layout]
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
# GUI
# --------------------------------------------------------------------------

def run_gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title("Label Printer")
    root.geometry("1000x700")
    ico = Path(__file__).with_name("label_miner.ico")
    if ico.exists():
        try:
            root.iconbitmap(str(ico))
        except tk.TclError:
            pass

    state = {"labels": []}

    ttk.Label(root, text="Indsæt rækker fra Google Sheets (marker fra kolonne A, uden overskrift):"
              ).pack(anchor="w", padx=10, pady=(10, 2))
    text_frame = ttk.Frame(root)
    text_frame.pack(fill="both", expand=False, padx=10)
    text = tk.Text(text_frame, height=10, wrap="none", undo=True)
    text_scroll = ttk.Scrollbar(text_frame, command=text.yview)
    text.configure(yscrollcommand=text_scroll.set)
    text.pack(side="left", fill="both", expand=True)
    text_scroll.pack(side="right", fill="y")

    buttons = ttk.Frame(root)
    buttons.pack(fill="x", padx=10, pady=6)
    status = tk.StringVar(value="Indsæt rækker og tryk 'Indlæs'.")

    cols = ("linje", "varenr", "navn", "vejl", "pris", "antal", "fejl")
    headings = ("#", "Varenr", "Varenavn", "Vejl. pris", "Vores pris", "Antal", "Problemer")
    widths = (40, 80, 420, 90, 90, 50, 200)
    tree_frame = ttk.Frame(root)
    tree_frame.pack(fill="both", expand=True, padx=10)
    tree = ttk.Treeview(tree_frame, columns=cols, show="headings")
    for col, head, wid in zip(cols, headings, widths):
        tree.heading(col, text=head)
        tree.column(col, width=wid, anchor="w", stretch=(col == "navn"))
    tree.tag_configure("bad", background="#f8d0d0")
    tree_scroll = ttk.Scrollbar(tree_frame, command=tree.yview)
    tree.configure(yscrollcommand=tree_scroll.set)
    tree.pack(side="left", fill="both", expand=True)
    tree_scroll.pack(side="right", fill="y")

    ttk.Label(root, textvariable=status).pack(anchor="w", padx=10, pady=(4, 10))

    def load():
        labels = parse_paste(text.get("1.0", "end"))
        state["labels"] = labels
        tree.delete(*tree.get_children())
        for lab in labels:
            tree.insert("", "end", tags=("bad",) if lab.problems else (), values=(
                lab.line, lab.varenr, lab.navn,
                format_dkk(lab.vejl) if lab.vejl is not None else "",
                format_dkk(lab.pris) if lab.pris is not None else "",
                lab.stk, ", ".join(lab.problems)))
        bad = sum(1 for lab in labels if lab.problems)
        n = len(expand(labels))
        msg = f"{len(labels)} rækker → {n} etiketter → {(n + 1) // 2} sider"
        if bad:
            msg += f"   ⚠ {bad} rækker har problemer og skal rettes i arket først"
        status.set(msg)
        gen_btn.state(["!disabled"] if labels and not bad else ["disabled"])

    def generate():
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf", filetypes=[("PDF", "*.pdf")],
            initialfile=f"etiketter_{date.today():%Y-%m-%d}.pdf")
        if not path:
            return
        try:
            pages = build_pdf(state["labels"], path)
        except PermissionError:
            messagebox.showerror("Label Printer", "Kunne ikke gemme filen -- er den åben i en PDF-læser?")
            return
        status.set(f"Gemt {pages} sider: {path}")
        os.startfile(path)

    ttk.Button(buttons, text="Indlæs", command=load).pack(side="left")
    ttk.Button(buttons, text="Ryd", command=lambda: text.delete("1.0", "end")).pack(side="left", padx=6)
    gen_btn = ttk.Button(buttons, text="Generér PDF", command=generate, state="disabled")
    gen_btn.pack(side="right")

    text.focus_set()
    root.mainloop()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--paste", help="tab-separated file with pasted rows (skips the GUI)")
    parser.add_argument("--out", default="etiketter.pdf")
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
    pages = build_pdf(labels, args.out)
    print(f"{len(expand(labels))} etiketter, {pages} sider -> {args.out}")


if __name__ == "__main__":
    main()
