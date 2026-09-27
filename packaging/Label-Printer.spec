# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller recipe: src/label_printer -> dist\Label-Printer\Label-Printer.exe
#
# Built by packaging\build.ps1, or on its own from the repository root:
#   python -m PyInstaller packaging\Label-Printer.spec --noconfirm
#
# Every dependency (reportlab, pypdfium2, sv_ttk) already has a
# pyinstaller-hooks-contrib hook, and tksheet is plain Python. "onedir" rather
# than "onefile": the app starts instantly instead of unpacking itself on
# every launch, and antivirus programs flag it less often.

import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
SRC = os.path.join(ROOT, "src")

a = Analysis(
    [os.path.join(SPECPATH, "launcher.py")],
    pathex=[SRC],
    binaries=[],
    # The GUI loads its window icon from the package's assets folder.
    datas=[(os.path.join(SRC, "label_printer", "assets"), os.path.join("label_printer", "assets"))],
    hiddenimports=["label_printer.gui"],  # imported lazily by __main__
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # A development environment may also hold heavy packages that nothing
    # here imports; excluding them keeps an optional import somewhere from
    # dragging hundreds of MB into this small app.
    excludes=["torch", "torchvision", "transformers", "docling", "cv2", "numpy", "scipy",
              "pandas", "matplotlib", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Label-Printer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # set True temporarily to see tracebacks from the frozen app
    icon=os.path.join(SRC, "label_printer", "assets", "label_printer.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Label-Printer",
)
