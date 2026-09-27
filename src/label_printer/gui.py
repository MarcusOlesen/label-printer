"""The Label Printer window: a spreadsheet to paste rows into, a live
preview of the selected label, and the layout options.

The UI text is Danish, as the program is used in a Danish shop.
"""

import contextlib
import csv
import io
import os
import sys
from datetime import date
from pathlib import Path

from . import __version__
from .layouts import DEFAULT_LAYOUT, LAYOUTS
from .model import COL_NAVN, COL_PRIS, COL_STK, COL_VARENR, COL_VEJL, Label
from .parsing import expand, parse_rows
from .pdf import build_pdf, render_label_image
from .settings import default_layout, load_settings, save_settings

ASSETS = Path(__file__).resolve().parent / "assets"
MANUAL_NAME = "Label-Printer-Vejledning.pdf"

SHEET_HEADERS = [
    "Varenummer",
    "Varenavn",
    "MK Varenummer",
    "MK ordrenr",
    "STAND",
    "STK",
    "Modtaget",
    "Vejl. priser",
    "Pris pr stk",
    "Pris samlet",
    "URL",
    "Image name",
]
USED_COLS = [COL_VARENR, COL_NAVN, COL_STK, COL_VEJL, COL_PRIS]
COL_WIDTHS = {COL_VARENR: 100, COL_NAVN: 280, COL_STK: 45, COL_VEJL: 175, COL_PRIS: 90}
UNUSED_COL_WIDTH = 45  # pasted but not printed: keep narrow so the prices stay in view
EMPTY_ROWS = 40

UI_FONT = "Segoe UI"
C = {  # matches the sv-ttk dark theme used by Label Miner
    "bg": "#1c1c1c",
    "card": "#262626",
    "table": "#202020",
    "header": "#2d2d2d",
    "grid": "#3a3a3a",
    "fg": "#fafafa",
    "muted": "#8b8b8b",
    "faint": "#5f5f5f",
    "accent": "#57c8ff",
    "ok": "#6fcf97",
    "bad": "#ff8a8a",
    "bad_bg": "#8a3030",
    "bad_row": "#4a2323",
    "warn": "#f2c94c",
    "warn_bg": "#4d4220",
    "select": "#1f4a63",
}
# Danish right-click menu for the table.
SHEET_MENU_LABELS = dict(
    cut_label="Klip",
    copy_label="Kopiér",
    copy_plain_label="Kopiér som tekst",
    paste_label="Indsæt",
    delete_label="Slet indhold",
    clear_contents_label="Slet indhold",
    delete_rows_label="Slet rækker",
    insert_rows_above_label="Indsæt rækker over",
    insert_rows_below_label="Indsæt rækker under",
    insert_row_label="Indsæt række",
    select_all_label="Markér alt",
    undo_label="Fortryd",
    redo_label="Annullér fortryd",
    edit_cell_label="Redigér celle",
)


class LabelPrinterApp:
    def __init__(self, root):
        import tkinter as tk
        from tkinter import ttk

        from tksheet import Sheet

        self.tk, self.ttk = tk, ttk
        self.root = root
        self.labels: list[Label] = []
        self.preview_image = None
        self.save_dir = str(Path.home() / "Desktop")
        self._validate_job = self._preview_job = None
        self.per_stk_var = tk.BooleanVar(value=False)  # default: one label per row
        self.cut_line_var = tk.BooleanVar(value=False)  # default: no cut line

        root.title(f"Label Printer {__version__}")
        root.geometry("1360x800")
        root.minsize(1000, 620)
        with contextlib.suppress(tk.TclError):
            root.state("zoomed")  # the table benefits from all the room it can get
        root.configure(bg=C["bg"])
        ico = ASSETS / "label_printer.ico"
        if ico.exists():
            with contextlib.suppress(tk.TclError):
                root.iconbitmap(str(ico))
        self._apply_theme()

        # ---- header -------------------------------------------------------
        header = ttk.Frame(root, padding=(20, 16, 20, 8))
        header.pack(fill="x")
        # Buttons are packed before the titles so a narrow window squeezes the
        # text, never the buttons.
        buttons = ttk.Frame(header)
        buttons.pack(side="right", anchor="n")
        ttk.Button(buttons, text="?  Hjælp", command=self.open_manual).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Indsæt fra udklipsholder", command=self.paste_replace).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(buttons, text="Ryd tabel", command=self.clear).pack(side="left")
        titles = ttk.Frame(header)
        titles.pack(side="left", fill="x", expand=True)
        ttk.Label(titles, text="Label Printer", font=(UI_FONT, 18, "bold")).pack(anchor="w")
        ttk.Label(
            titles,
            foreground=C["muted"],
            text="Kopiér rækkerne i Google Sheets (fra kolonne A) og indsæt med Ctrl+V. "
            "Du kan rette direkte i cellerne.",
        ).pack(anchor="w")
        ttk.Label(
            titles,
            foreground=C["muted"],
            text="Slet rækker: klik på rækkenumrene (træk eller Shift-klik for flere) og "
            "tryk Delete.  Markerede celler tømmes med Delete.",
        ).pack(anchor="w")

        # ---- body: sheet + sidebar ---------------------------------------
        body = ttk.Frame(root, padding=(20, 8, 20, 20))
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        self.sheet = Sheet(
            body,
            headers=SHEET_HEADERS,
            data=self._blank_rows(EMPTY_ROWS),
            theme="dark",
            font=(UI_FONT, 10, "normal"),
            header_font=(UI_FONT, 10, "bold"),
            index_font=(UI_FONT, 9, "normal"),
            default_row_height=28,
            default_header_height=34,
            paste_can_expand_y=True,
            paste_can_expand_x=False,
            expand_sheet_if_paste_too_big=True,
            show_selected_cells_border=True,
        )
        self._style_sheet()
        self.sheet.enable_bindings("all")
        # Anything that adds, removes or reorders *columns* would shift the
        # pasted data out of the Label Miner column order, so switch it off.
        for binding in (
            "edit_header",
            "edit_index",
            "rename_columns",
            "rc_insert_column",
            "rc_delete_column",
            "column_drag_and_drop",
            "sort_cells",
            "sort_row",
            "sort_column",
            "sort_rows",
            "sort_columns",
        ):
            with contextlib.suppress(Exception):
                self.sheet.disable_bindings(binding)
        with contextlib.suppress(Exception):
            self.sheet.set_options(**SHEET_MENU_LABELS, redraw=False)
        self.sheet.grid(row=0, column=0, sticky="nsew")
        self.sheet.bind("<<SheetModified>>", lambda e: self._schedule_validate())
        self.sheet.bind("<<SheetSelect>>", lambda e: self._schedule_preview())
        root.bind_all("<Control-v>", self._global_paste, add="+")
        # Delete/Backspace: remove whole selected rows. Our tag is put in front
        # of tksheet's own bindings on its canvases so it gets the key first;
        # with only cells selected it falls through and tksheet empties them.
        for widget in (self.sheet.MT, self.sheet.RI, self.sheet.CH, self.sheet.TL):
            widget.bindtags(("LabelPrinterRows",) + widget.bindtags())
        root.bind_class("LabelPrinterRows", "<Delete>", self._on_delete_key)
        root.bind_class("LabelPrinterRows", "<BackSpace>", self._on_delete_key)

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
            frame_bg=C["bg"],
            table_bg=C["table"],
            table_fg=C["fg"],
            table_grid_fg=C["grid"],
            header_bg=C["header"],
            header_fg=C["muted"],
            header_grid_fg=C["grid"],
            header_border_fg=C["grid"],
            index_bg=C["header"],
            index_fg=C["muted"],
            index_grid_fg=C["grid"],
            index_border_fg=C["grid"],
            top_left_bg=C["header"],
            top_left_fg=C["header"],
            table_selected_cells_bg=C["select"],
            table_selected_cells_border_fg=C["accent"],
            header_selected_cells_bg=C["select"],
            header_selected_cells_fg=C["fg"],
            index_selected_cells_bg=C["select"],
            index_selected_cells_fg=C["fg"],
            table_editor_bg=C["card"],
            table_editor_fg=C["fg"],
        )
        for key, value in options.items():  # tolerate option names changing between versions
            with contextlib.suppress(Exception):
                self.sheet.set_options(**{key: value}, redraw=False)
        for col in range(len(SHEET_HEADERS)):
            self.sheet.column_width(col, COL_WIDTHS.get(col, UNUSED_COL_WIDTH), redraw=False)
        unused = [c for c in range(len(SHEET_HEADERS)) if c not in USED_COLS]
        self.sheet.highlight_columns(unused, fg=C["faint"], redraw=False)
        for col in USED_COLS:  # the columns that end up on the label stand out
            self.sheet.highlight_cells(column=col, canvas="header", fg=C["accent"], redraw=False)
        self._style_stk_column()

    def _style_stk_column(self):
        """STK only counts as a 'used' column while one label per piece is on."""
        if self.per_stk:
            # dehighlight_columns also clears the header, so it must come first
            self.sheet.dehighlight_columns([COL_STK], redraw=False)
            self.sheet.highlight_cells(column=COL_STK, canvas="header", fg=C["accent"], redraw=False)
        else:
            self.sheet.highlight_cells(column=COL_STK, canvas="header", fg=C["faint"], redraw=False)
            self.sheet.highlight_columns([COL_STK], fg=C["faint"], redraw=False)
        self.sheet.refresh()

    def _build_sidebar(self, parent):
        # Plain tk widgets here: sv-ttk draws ttk frames/labels with images and
        # ignores custom backgrounds, which leaves grey patches on the card.
        tk = self.tk
        side = tk.Frame(
            parent,
            bg=C["card"],
            width=370,
            padx=18,
            pady=14,
            highlightthickness=1,
            highlightbackground=C["grid"],
        )
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
        for i, (key, caption) in enumerate([("rows", "rækker"), ("labels", "etiketter"), ("pages", "sider")]):
            stats.columnconfigure(i, weight=1, uniform="stat")
            var = tk.StringVar(value="0")
            self.stat_vars[key] = var
            label(
                stats,
                textvariable=var,
                font=(UI_FONT, 20, "bold"),
                fg=C["accent"] if key == "labels" else C["fg"],
            ).grid(row=0, column=i, sticky="w")
            label(stats, text=caption, fg=C["muted"], font=(UI_FONT, 9)).grid(row=1, column=i, sticky="w")

        tk.Frame(side, bg=C["grid"], height=1).grid(row=1, column=0, sticky="ew", pady=8)

        self.status_label = label(side, font=(UI_FONT, 11, "bold"), wraplength=340)
        self.status_label.grid(row=2, column=0, sticky="ew")
        # Colour legend for the table highlights; only the entries that apply
        # to the current data are shown.
        legend = tk.Frame(side, bg=C["card"])
        legend.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        self.legend_rows = {}
        for i, key in enumerate(("bad_row", "warn_bg")):
            row = tk.Frame(legend, bg=C["card"])
            row.grid(row=i, column=0, sticky="w")
            tk.Frame(
                row, bg=C[key], width=13, height=13, highlightthickness=1, highlightbackground=C["grid"]
            ).pack(side="left", padx=(0, 8))
            text = label(row, fg=C["fg"], font=(UI_FONT, 9))
            text.pack(side="left")
            self.legend_rows[key] = (row, text)

        self.preview_title = label(side, fg=C["muted"], font=(UI_FONT, 9, "bold"))
        self.preview_title.grid(row=4, column=0, sticky="ew", pady=(8, 4))
        self.preview = tk.Label(
            side,
            bg=C["table"],
            fg=C["muted"],
            font=(UI_FONT, 10),
            height=11,
            text="Ingen gyldige rækker endnu.",
        )
        self.preview.grid(row=5, column=0, sticky="new")

        layout_row = tk.Frame(side, bg=C["card"])
        layout_row.grid(row=7, column=0, sticky="ew", pady=(8, 0))
        layout_row.columnconfigure(1, weight=1)
        label(layout_row, text="LAYOUT", fg=C["muted"], font=(UI_FONT, 9, "bold")).grid(
            row=0, column=0, sticky="w", padx=(0, 12)
        )
        self.layout_names = {name: key for key, (name, _) in LAYOUTS.items()}
        self.layout_var = tk.StringVar(value=LAYOUTS[default_layout()][0])
        combo = self.ttk.Combobox(
            layout_row, textvariable=self.layout_var, state="readonly", values=list(self.layout_names)
        )
        combo.grid(row=0, column=1, sticky="ew")
        combo.bind(
            "<<ComboboxSelected>>",
            lambda e: (combo.selection_clear(), self._update_default_button(), self._schedule_preview()),
        )
        self.default_btn = tk.Label(layout_row, bg=C["card"], font=(UI_FONT, 9), cursor="hand2")
        self.default_btn.grid(row=1, column=1, sticky="e", pady=(4, 0))
        self.default_btn.bind("<Button-1>", lambda e: self._make_default())
        self._update_default_button()

        def checkbox(text, variable, command, row):
            tk.Checkbutton(
                layout_row,
                variable=variable,
                command=command,
                text=text,
                anchor="w",
                bg=C["card"],
                fg=C["fg"],
                activebackground=C["card"],
                activeforeground=C["fg"],
                selectcolor=C["table"],
                highlightthickness=0,
                bd=0,
                font=(UI_FONT, 10),
                cursor="hand2",
            ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(4, 0))

        # The first shares its line with the "Standard-layout" link.
        checkbox("Én etiket pr. stk", self.per_stk_var, self._toggle_per_stk, 1)
        checkbox("Skærelinje i midten", self.cut_line_var, None, 2)
        self.default_btn.lift()
        side.rowconfigure(9, weight=1)

        self.generate_btn = self.ttk.Button(
            side, text="Generér PDF", style="Big.Accent.TButton", command=self.generate
        )
        self.generate_btn.grid(row=10, column=0, sticky="ew")

    @staticmethod
    def _blank_rows(n):
        return [[""] * len(SHEET_HEADERS) for _ in range(n)]

    # ---- pasting ---------------------------------------------------------
    def open_manual(self):
        """Open the PDF manual: installed next to the .exe, or built into the
        repository root when running from source (docs/manual/make_manual.py)."""
        for folder in (Path(sys.executable).parent, Path(__file__).resolve().parents[2]):
            manual = folder / MANUAL_NAME
            if manual.exists():
                os.startfile(manual)
                return
        from tkinter import messagebox

        messagebox.showinfo("Label Printer", f"Vejledningen ({MANUAL_NAME}) blev ikke fundet.")

    def paste_replace(self):
        """Replace the whole table with the clipboard contents."""
        try:
            text = self.root.clipboard_get()
        except self.tk.TclError:
            return
        rows = [
            (row + [""] * len(SHEET_HEADERS))[: len(SHEET_HEADERS)]
            for row in csv.reader(io.StringIO(text.strip("\r\n")), delimiter="\t")
        ]
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

    def _on_delete_key(self, event):
        """Delete/Backspace in the table. Whole rows selected (via the row
        numbers) -> remove those rows. Otherwise Delete falls through to
        tksheet, which empties the selected cells; Backspace does the same."""
        if self.sheet.get_selected_rows():
            self.delete_selected_rows()
            return "break"
        if event.keysym == "BackSpace" and self.sheet.get_selected_cells():
            self.sheet.MT.delete_key()
            return "break"
        return None

    def delete_selected_rows(self):
        """Remove the whole rows that are selected. Undo with Ctrl+Z."""
        rows = set(self.sheet.get_selected_rows())
        if not rows:
            return
        self.sheet.delete_rows(sorted(rows), undo=True, redraw=False)
        self.sheet.deselect("all")
        missing = EMPTY_ROWS - self.sheet.get_total_rows()
        if missing > 0:  # keep some empty rows to paste into
            # idx=None appends; tksheet reads idx="end" as something else
            # entirely and inserts thousands of rows.
            self.sheet.insert_rows(
                self._blank_rows(missing), idx=None, undo=False, create_selections=False, redraw=False
            )
        self.sheet.select_cell(min(min(rows), self.sheet.get_total_rows() - 1), 0)
        self.validate()

    # ---- validation ------------------------------------------------------
    def _schedule_validate(self):
        if self._validate_job:
            self.root.after_cancel(self._validate_job)
        self._validate_job = self.root.after(120, self.validate)

    def validate(self):
        self._validate_job = None
        self.labels = parse_rows(self.sheet.get_sheet_data(), self.per_stk)
        bad = [lab for lab in self.labels if lab.problems]
        warned = [lab for lab in self.labels if lab.warnings and not lab.problems]

        # Redraw all row/cell highlights from scratch (rows may have been
        # inserted or deleted since last time). Column styling is separate
        # and survives this.
        self.sheet.dehighlight_rows("all", redraw=False)
        self.sheet.dehighlight_cells(row="all", redraw=False)
        if bad:  # incomplete row: whole row red, the missing cells stronger
            self.sheet.highlight_rows([lab.line - 1 for lab in bad], bg=C["bad_row"], redraw=False)
            cells = [(lab.line - 1, col) for lab in bad for col in lab.bad_cols]
            if cells:
                self.sheet.highlight_cells(cells=cells, bg=C["bad_bg"], redraw=False)
        warn_cells = [(lab.line - 1, col) for lab in warned for col in lab.warn_cols]
        if warn_cells:
            self.sheet.highlight_cells(cells=warn_cells, bg=C["warn_bg"], redraw=False)
        self.sheet.refresh()

        n = len(expand(self.labels, self.per_stk))
        self.stat_vars["rows"].set(str(len(self.labels)))
        self.stat_vars["labels"].set(str(n))
        self.stat_vars["pages"].set(str((n + 1) // 2))

        legend = {
            "bad_row": (f"Ufuldstændig række – udskrives ikke ({len(bad)})", bool(bad)),
            "warn_bg": (f"Ingen vejl. pris – tom på etiketten ({len(warned)})", bool(warned)),
        }
        for key, (text, show) in legend.items():
            row, text_label = self.legend_rows[key]
            text_label.configure(text=text)
            if show:
                row.grid()
            else:
                row.grid_remove()

        if not self.labels:
            self._set_status("Indsæt rækker for at komme i gang.", C["muted"])
        elif n == 0:
            self._set_status("Ingen komplette rækker – der er intet at udskrive.", C["bad"])
        elif bad:
            self._set_status(
                f"✓  Klar – {len(bad)} række{'r' if len(bad) > 1 else ''} springes over", C["warn"]
            )
        else:
            self._set_status("✓  Klar til udskrift", C["ok"])
        self.generate_btn.state(["!disabled"] if n else ["disabled"])
        self._schedule_preview()

    def _set_status(self, text, color):
        self.status_label.configure(text=text, fg=color)

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
            self.preview.configure(image="", text="Ingen gyldige rækker endnu.", height=11)
            self.preview_title.configure(text="FORHÅNDSVISNING")
            return
        self.preview_title.configure(text=f"FORHÅNDSVISNING  ·  RÆKKE {label.line}")
        image = render_label_image(label, 290, self.layout)
        if image is None:
            self.preview.configure(image="", text="Installer pypdfium2 for forhåndsvisning.")
            return
        from PIL import ImageTk

        self.preview_image = ImageTk.PhotoImage(image)
        self.preview.configure(image=self.preview_image, text="", height=0)

    def _update_default_button(self):
        if self.layout == default_layout():
            self.default_btn.configure(text="✓ Standard-layout", fg=C["faint"], cursor="")
        else:
            self.default_btn.configure(text="Gør til standard", fg=C["accent"], cursor="hand2")

    def _make_default(self):
        if self.layout == default_layout():
            return
        settings = load_settings()
        settings["default_layout"] = self.layout
        try:
            save_settings(settings)
        except OSError as exc:
            from tkinter import messagebox

            messagebox.showerror("Label Printer", f"Kunne ikke gemme indstillingen:\n{exc}")
            return
        self._update_default_button()

    @property
    def per_stk(self):
        return bool(self.per_stk_var.get())

    def _toggle_per_stk(self):
        self._style_stk_column()
        self.validate()

    @property
    def layout(self):
        return self.layout_names.get(self.layout_var.get(), DEFAULT_LAYOUT)

    # ---- output ----------------------------------------------------------
    def generate(self):
        from tkinter import filedialog, messagebox

        path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")],
            initialdir=self.save_dir,
            initialfile=f"etiketter_{date.today():%Y-%m-%d}.pdf",
        )
        if not path:
            return
        try:
            pages = build_pdf(self.labels, path, self.layout, self.per_stk, bool(self.cut_line_var.get()))
        except PermissionError:
            messagebox.showerror("Label Printer", "Kunne ikke gemme filen – er den åben i en PDF-læser?")
            return
        self.save_dir = str(Path(path).parent)
        self._set_status(f"✓  Gemt {pages} sider: {Path(path).name}", C["ok"])
        os.startfile(path)


def run_gui() -> None:
    import tkinter as tk

    root = tk.Tk()
    LabelPrinterApp(root)
    root.mainloop()
