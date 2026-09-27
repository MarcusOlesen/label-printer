# Changelog

## 4.3 - 2026-09-25
- Fractions like "del 1/3" are ignored when reading prices, so "OBS: delvis vare (del 1/3)" no
  longer gives a price of 3.
- The code is split into a package (`src/label_printer`), with tests, CI and a documented build.

## 4.2 - 2026-09-25
- A Danish user manual, generated from screenshots of the real app, and a "? Hjælp" button that
  opens it. The installer includes it.

## 4.1 - 2026-09-25
- A space is only a thousands separator in "1 000" / "10 499" style; any other space separates two
  numbers, so "1234 4321" reads like "1234 (4321)".

## 4.0 - 2026-09-24
- Incomplete rows are skipped instead of blocking the whole PDF.
- An empty recommended price is allowed (printed empty).
- Delete/Backspace removes selected rows.
- A colour legend explains the row highlights.
- The cut line is off by default.

## 3.2 - 2026-09-24
- One label per row by default; optionally one label per piece (STK).

## 3.1 - 2026-09-24
- First version shipped with an installer.

## 3.0 - 2026-09-24
- Layout picker with four layouts. "Klassisk" reproduces the old Word labels and stays the default.
- Product names are split on " | " into a bold title and smaller details.

## 2.0 - 2026-09-24
- Spreadsheet-style GUI for pasting and editing rows.

## 1.0 - 2026-09-24
- First working version: prints labels to a PDF, two per A4 page.
