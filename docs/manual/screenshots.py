"""Takes the screenshots for the Label Printer manual by driving the real app.

Starts LabelPrinterApp, pastes example rows, clicks through the scenarios the
manual describes and captures the window after each one. Numbered callouts
are positioned from the live widget geometry, so they stay correct when the
layout changes. Used by make_manual.py; can also be run on its own:

    python docs/manual/screenshots.py

Windows only (the window is captured with the Win32 PrintWindow API).
"""

import ctypes
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src"))

import demo_sheet  # noqa: E402

from label_printer import gui, settings  # noqa: E402
from label_printer.layouts import DEFAULT_LAYOUT, LAYOUTS  # noqa: E402
from label_printer.model import COL_NAVN, COL_PRIS, COL_VEJL, Label  # noqa: E402
from label_printer.pdf import build_pdf, render_label_image  # noqa: E402

SHOTS = ROOT / "build" / "manual-screenshots"
ORANGE = (217, 98, 43)
WHITE = (255, 255, 255)

# The demo rows (made-up order numbers and prices) in the sheet's 12 columns.
DEMO_ROWS = [
    [v, n, mk, order, stand, stk, "X", comment, price, "", "", ""]
    for v, n, mk, order, stand, stk, comment, price in demo_sheet.DEMO_ROWS
]
CLEAN_ROWS = [r for r in DEMO_ROWS if r[8] and r[7]]  # nothing to flag
FLAGGED_ROWS = DEMO_ROWS  # red + yellow rows


def tsv(rows):
    return "\n".join("\t".join(r) for r in rows)


# --------------------------------------------------------------------------
# Window capture (PrintWindow renders the window even if something covers it)
# --------------------------------------------------------------------------


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


def _setup_winapi():
    u, g = ctypes.windll.user32, ctypes.windll.gdi32
    u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    u.GetWindowDC.argtypes = [wintypes.HWND]
    u.GetWindowDC.restype = wintypes.HDC
    u.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    u.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
    g.CreateCompatibleDC.argtypes = [wintypes.HDC]
    g.CreateCompatibleDC.restype = wintypes.HDC
    g.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    g.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    g.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    g.SelectObject.restype = wintypes.HGDIOBJ
    g.GetDIBits.argtypes = [
        wintypes.HDC,
        wintypes.HBITMAP,
        wintypes.UINT,
        wintypes.UINT,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.UINT,
    ]
    g.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    g.DeleteDC.argtypes = [wintypes.HDC]
    ctypes.windll.dwmapi.DwmGetWindowAttribute.argtypes = [
        wintypes.HWND,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    return u, g


def grab_window(root):
    """Returns (image, (left, top)) of the visible window in screen pixels."""
    root.update()
    u, g = _setup_winapi()
    hwnd = int(root.wm_frame(), 16)
    rect, ext = wintypes.RECT(), wintypes.RECT()
    u.GetWindowRect(hwnd, ctypes.byref(rect))
    # The visible frame (GetWindowRect includes invisible resize borders).
    ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(ext), ctypes.sizeof(ext))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    hdc_win = u.GetWindowDC(hwnd)
    hdc = g.CreateCompatibleDC(hdc_win)
    bmp = g.CreateCompatibleBitmap(hdc_win, w, h)
    g.SelectObject(hdc, bmp)
    u.PrintWindow(hwnd, hdc, 2)  # PW_RENDERFULLCONTENT
    bmi = BITMAPINFOHEADER(40, w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * h * 4)
    g.GetDIBits(hdc, bmp, 0, h, buf, ctypes.byref(bmi), 0)
    g.DeleteObject(bmp)
    g.DeleteDC(hdc)
    u.ReleaseDC(hwnd, hdc_win)
    img = Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1)
    box = (ext.left - rect.left, ext.top - rect.top, ext.right - rect.left, ext.bottom - rect.top)
    return img.crop(box), (ext.left, ext.top)


# --------------------------------------------------------------------------
# Callouts
# --------------------------------------------------------------------------


def _font(size, bold=True):
    for name in ("segoeuib.ttf", "arialbd.ttf") if bold else ("segoeui.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def annotate(img, circles=(), boxes=(), arrows=(), scale=1.0):
    """circles: [(number, (x, y))]; boxes: [(x0, y0, x1, y1)];
    arrows: [((x0, y0), (x1, y1))] pointer lines from a circle to its target.
    All in image pixels."""
    img = img.convert("RGB")
    d = ImageDraw.Draw(img)
    width = max(3, round(3 * scale))
    for x0, y0, x1, y1 in boxes:
        d.rounded_rectangle((x0, y0, x1, y1), radius=round(6 * scale), outline=ORANGE, width=width)
    for (x0, y0), (x1, y1) in arrows:
        d.line((x0, y0, x1, y1), fill=ORANGE, width=width)
        dot = round(5 * scale)
        d.ellipse((x1 - dot, y1 - dot, x1 + dot, y1 + dot), fill=ORANGE)
    r = round(17 * scale)
    f = _font(round(20 * scale))
    for number, (x, y) in circles:
        d.ellipse((x - r - 2, y - r - 2, x + r + 2, y + r + 2), fill=WHITE)
        d.ellipse((x - r, y - r, x + r, y + r), fill=ORANGE)
        d.text((x, y + 1), str(number), font=f, fill=WHITE, anchor="mm")
    return img


# --------------------------------------------------------------------------
# Driving the app
# --------------------------------------------------------------------------


class Session:
    def __init__(self):
        import tkinter as tk

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        # Screenshots must show the factory defaults, not this PC's settings.
        settings.SETTINGS_PATH = Path(tempfile.gettempdir()) / "label_printer_manual_settings.json"
        settings.SETTINGS_PATH.unlink(missing_ok=True)
        self.root = tk.Tk()
        self.app = gui.LabelPrinterApp(self.root)
        self.scale = self.root.winfo_fpixels("1i") / 96
        self.root.state("normal")
        self.root.geometry(f"{round(1360 * self.scale)}x{round(820 * self.scale)}+30+30")
        self.settle(600)

    def settle(self, ms=400):
        end = time.time() + ms / 1000
        while time.time() < end:
            self.root.update()
            time.sleep(0.01)

    def paste(self, rows, select=(0, 1)):
        self.root.clipboard_clear()
        self.root.clipboard_append(tsv(rows))
        self.app.paste_replace()
        self.app.sheet.deselect("all")
        if select:
            self.app.sheet.select_cell(*select)
        self.app.sheet.see(0, 0)
        self.settle(500)

    def shot(self):
        img, self.origin = grab_window(self.root)
        return img

    # geometry helpers, in image pixels -----------------------------------
    def widget_box(self, w, pad=4):
        x = w.winfo_rootx() - self.origin[0]
        y = w.winfo_rooty() - self.origin[1]
        p = round(pad * self.scale)
        return (x - p, y - p, x + w.winfo_width() + p, y + w.winfo_height() + p)

    def cell_box(self, row, col, row2=None, col2=None):
        mt = self.app.sheet.MT
        row2, col2 = (row if row2 is None else row2), (col if col2 is None else col2)
        x0 = mt.col_positions[col] - mt.canvasx(0) + mt.winfo_rootx() - self.origin[0]
        x1 = mt.col_positions[col2 + 1] - mt.canvasx(0) + mt.winfo_rootx() - self.origin[0]
        y0 = mt.row_positions[row] - mt.canvasy(0) + mt.winfo_rooty() - self.origin[1]
        y1 = mt.row_positions[row2 + 1] - mt.canvasy(0) + mt.winfo_rooty() - self.origin[1]
        return (round(x0), round(y0), round(x1), round(y1))

    def row_index_box(self, row, row2=None):
        ri, mt = self.app.sheet.RI, self.app.sheet.MT
        row2 = row if row2 is None else row2
        y0 = mt.row_positions[row] - mt.canvasy(0) + ri.winfo_rooty() - self.origin[1]
        y1 = mt.row_positions[row2 + 1] - mt.canvasy(0) + ri.winfo_rooty() - self.origin[1]
        x0 = ri.winfo_rootx() - self.origin[0]
        return (x0, round(y0), x0 + ri.winfo_width(), round(y1))

    def find(self, text):
        """First widget whose text is `text`."""
        todo = [self.root]
        while todo:
            w = todo.pop(0)
            try:
                if w.cget("text") == text:
                    return w
            except Exception:
                pass
            todo.extend(w.winfo_children())
        raise LookupError(text)

    def close(self):
        self.root.destroy()


def left_mid(box, inset=0):
    return (box[0] + inset, (box[1] + box[3]) // 2)


def right_mid(box, inset=0):
    return (box[2] - inset, (box[1] + box[3]) // 2)


def top_left(box):
    return (box[0], box[1])


def take_all():
    """Captures every screenshot; returns {name: Path}."""
    SHOTS.mkdir(parents=True, exist_ok=True)
    out = {}
    s = Session()
    app, sc = s.app, s.scale
    side = app.generate_btn.master

    def save(name, img):
        path = SHOTS / f"{name}.png"
        img.save(path)
        out[name] = path

    # side_box is set after the first capture (widget boxes need the window origin)
    gutter = lambda box: (side_box[0] - round(22 * sc), (box[1] + box[3]) // 2)  # noqa: E731
    below = lambda box: ((box[0] + box[2]) // 2, box[3] + round(22 * sc))  # noqa: E731

    # 1. Overview: empty window --------------------------------------------
    app.clear()
    s.settle(400)
    img = s.shot()
    side_box = s.widget_box(side, pad=0)
    help_btn = s.widget_box(s.find("?  Hjælp"), pad=0)
    paste_btn = s.widget_box(s.find("Indsæt fra udklipsholder"), pad=0)
    clear_btn = s.widget_box(s.find("Ryd tabel"), pad=0)
    table = s.widget_box(app.sheet, pad=0)
    stats = s.widget_box(side.winfo_children()[0])
    preview = s.widget_box(app.preview)
    layout = s.widget_box(s.find("LAYOUT").master)
    gen = s.widget_box(app.generate_btn)
    save(
        "01_oversigt",
        annotate(
            img,
            scale=sc,
            circles=[
                (1, (table[0] + round(300 * sc), table[1] + round(260 * sc))),
                (2, below(help_btn)),
                (3, below(paste_btn)),
                (4, below(clear_btn)),
                (5, gutter(stats)),
                (6, gutter(preview)),
                (7, gutter(layout)),
                (8, gutter(gen)),
            ],
        ),
    )

    # 2. After a clean paste -------------------------------------------------
    s.paste(CLEAN_ROWS, select=(1, 1))
    img = s.shot()
    hdr = s.cell_box(0, COL_NAVN)
    header_row = (s.cell_box(0, 0)[0], hdr[1] - round(33 * sc), s.cell_box(0, COL_PRIS)[2], hdr[1])
    status = s.widget_box(app.status_label)
    empty_x = s.cell_box(0, len(gui.SHEET_HEADERS) - 1)[2] + round(70 * sc)
    save(
        "02_indsat",
        annotate(
            img,
            scale=sc,
            boxes=[header_row, status],
            arrows=[((empty_x, (header_row[1] + header_row[3]) // 2), right_mid(header_row))],
            circles=[
                (1, (empty_x, (header_row[1] + header_row[3]) // 2)),
                (2, gutter(status)),
                (3, gutter(preview)),
            ],
        ),
    )

    # 3. Red and yellow rows ------------------------------------------------
    s.paste(FLAGGED_ROWS, select=(0, 1))
    img = s.shot()
    red = [i for i, r in enumerate(FLAGGED_ROWS) if not r[8]]
    yellow = [i for i, r in enumerate(FLAGGED_ROWS) if not r[7]]
    red_box = s.cell_box(red[0], 0, red[-1], COL_PRIS)
    yellow_box = s.cell_box(yellow[0], COL_VEJL)
    legend = s.widget_box(app.legend_rows["bad_row"][0].master)
    red_mid = (red_box[1] + red_box[3]) // 2
    save(
        "03_roed_gul",
        annotate(
            img,
            scale=sc,
            boxes=[red_box, yellow_box, legend],
            arrows=[((empty_x, red_mid), (red_box[2], red_mid))],
            circles=[
                (1, (empty_x, red_mid)),
                (2, right_mid(yellow_box, -round(24 * sc))),
                (3, gutter(legend)),
            ],
        ),
    )

    # 4. Deleting rows via the row numbers ----------------------------------
    app.sheet.deselect("all")
    app.sheet.select_row(red[0])
    for r in red[1:]:
        app.sheet.add_row_selection(r)
    s.settle(300)
    img = s.shot()
    ri = s.row_index_box(red[0], red[-1])
    mid = (ri[1] + ri[3]) // 2
    save(
        "04_slet_raekker",
        annotate(
            img, scale=sc, boxes=[ri], arrows=[((empty_x, mid), (ri[2], mid))], circles=[(1, (empty_x, mid))]
        ),
    )

    # 5. Too few columns: copy started in column B --------------------------
    s.paste([r[1:] for r in CLEAN_ROWS], select=None)
    img = s.shot()
    first = s.cell_box(0, 0, 0, 1)
    mismatch = (first[0], first[1] - round(33 * sc), first[2], first[3])  # headers + row 1
    corner = s.widget_box(app.sheet.TL, pad=0)
    status = s.widget_box(app.status_label)
    save(
        "05_forkert_kolonne",
        annotate(
            img,
            scale=sc,
            boxes=[mismatch, status],
            circles=[(1, ((corner[0] + corner[2]) // 2, (corner[1] + corner[3]) // 2)), (2, gutter(status))],
        ),
    )

    # 6. Settings panel close-up (with margins for the callouts) ------------
    s.paste(CLEAN_ROWS, select=(1, 1))
    img = s.shot()
    lay = s.widget_box(s.find("LAYOUT"))
    top = lay[1] - round(16 * sc)
    crop = img.crop((side_box[0], top, side_box[2], side_box[3]))
    m = round(110 * sc)
    canvas_img = Image.new("RGB", (crop.width + 2 * m, crop.height), (28, 28, 28))
    canvas_img.paste(crop, (m, 0))

    def at(w, side="left"):
        b = s.widget_box(w, pad=0)
        return (
            b[0] - side_box[0] + m if side == "left" else b[2] - side_box[0] + m,
            (b[1] + b[3]) // 2 - top,
        )

    # Rows are closer together than a circle is wide, so stagger them and
    # point at their targets.
    near, far = round(m * 0.72), round(m * 0.28)
    targets = [
        (1, at(s.find("LAYOUT")), near),
        (3, at(s.find("Én etiket pr. stk")), far),
        (4, at(s.find("Skærelinje i midten")), near),
        (5, at(app.generate_btn), near),
    ]
    circles = [(n, (x, y)) for n, (_, y), x in targets]
    arrows = [((x, y), (tx - round(4 * sc), y)) for n, (tx, y), x in targets]
    tx, ty = at(app.default_btn, "right")
    circles.append((2, (crop.width + m + m // 2, ty)))
    arrows.append(((crop.width + m + m // 2, ty), (tx + round(4 * sc), ty)))
    save("06_indstillinger", annotate(canvas_img, scale=sc, circles=circles, arrows=arrows))
    s.close()

    # 7. The Google Sheet (drawn from the demo rows, see demo_sheet.py) ------
    sheet = demo_sheet.render()
    last_row = 2 + len(demo_sheet.DEMO_ROWS)
    selection = sheet.cell(0, 3, 9, last_row)
    header_rows = sheet.cell(0, 1, 9, 2)
    save(
        "07_google_sheet",
        annotate(
            sheet.image,
            scale=1.1,
            boxes=[selection, sheet.namebox, header_rows],
            circles=[
                (1, (selection[0] + 30, selection[1] + 12)),
                (2, (sheet.namebox[2] + 24, 18)),
                (3, (header_rows[2] - 24, (header_rows[1] + header_rows[3]) // 2)),
            ],
        ),
    )

    # 8. The four layouts, rendered from the real drawing code --------------
    item = Label("1235", "Marmoris spisebord, keramik | 200x100 Pandora/Hvid", 6999, 2500, 1, 1, [])
    tiles = []
    for key, (name, _) in LAYOUTS.items():
        tile = render_label_image(item, 760, key)
        cap = Image.new("RGB", (tile.width, 56), WHITE)
        ImageDraw.Draw(cap).text((6, 28), name, font=_font(30), fill=(40, 40, 40), anchor="lm")
        framed = Image.new("RGB", (tile.width + 2, tile.height + 58), (190, 190, 190))
        framed.paste(cap, (1, 1))
        framed.paste(tile, (1, 57))
        tiles.append(framed)
    tw, th = tiles[0].size
    grid = Image.new("RGB", (tw * 2 + 30, th * 2 + 30), WHITE)
    for i, t in enumerate(tiles):
        grid.paste(t, ((i % 2) * (tw + 30), (i // 2) * (th + 30)))
    save("08_layouts", grid)

    # 9. One finished label for the front page ------------------------------
    save("09_etiket", render_label_image(item, 900, DEFAULT_LAYOUT))

    # 10. A printed sheet: two labels and the cut line ------------------------
    import pypdfium2

    second = Label("1244", "Vega sofabord, hvid marmor | Ø90", 4499, 1800, 1, 2, [])
    pdf_path = Path(tempfile.gettempdir()) / "label_printer_manual_sheet.pdf"
    build_pdf([item, second], pdf_path, DEFAULT_LAYOUT, cut_line=True)
    page = pypdfium2.PdfDocument(str(pdf_path))[0].render(scale=1.4).to_pil().convert("RGB")
    d = ImageDraw.Draw(page)
    d.rectangle((0, 0, page.width - 1, page.height - 1), outline=(150, 150, 150), width=2)
    y = page.height // 2
    f = _font(26)
    d.text((page.width - 20, y - 8), "klip her", font=f, fill=ORANGE, anchor="rb")
    sheet_img = Image.new("RGB", (page.width + 24, page.height + 24), WHITE)
    ImageDraw.Draw(sheet_img).rectangle(
        (12, 12, page.width + 20, page.height + 20), fill=(215, 215, 215)
    )  # soft shadow
    sheet_img.paste(page, (4, 4))
    save("10_ark", sheet_img)
    return out


if __name__ == "__main__":
    for name, path in take_all().items():
        print(name, path)
