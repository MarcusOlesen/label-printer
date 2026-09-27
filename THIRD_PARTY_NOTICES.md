# Third-party software

Label Printer's own code is MIT-licensed (see [LICENSE](LICENSE)). It depends on the packages below,
which users install themselves with pip. The Windows installer bundles them; their licences all allow
redistribution, including commercially, as long as their notices are kept.

| Package | Licence | Used for |
|---|---|---|
| [ReportLab](https://www.reportlab.com/) | BSD | drawing the labels and the PDF |
| [tksheet](https://github.com/ragardner/tksheet) | MIT | the spreadsheet grid |
| [pypdfium2](https://github.com/pypdfium2-team/pypdfium2) (PDFium) | Apache-2.0 / BSD-3-Clause | label preview |
| [Pillow](https://python-pillow.org/) | MIT-CMU | preview images |
| [sv-ttk](https://github.com/rdbende/Sun-Valley-ttk-theme) | MIT | dark theme |
| Python / Tkinter | PSF | runtime and GUI toolkit |

Build tools (not part of the source):

- **PyInstaller.** GPL-2.0 with a bootloader exception that allows distributing frozen apps under
  any licence.
- **Inno Setup.** Its licence allows distributing the installers it creates.

When distributing the built app, include these packages' licence texts. PyInstaller copies most of
them into `dist\Label-Printer\_internal\`.
