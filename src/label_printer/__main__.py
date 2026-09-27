"""Entry point: ``python -m label_printer`` opens the GUI.

A headless mode turns a tab-separated file into a PDF without the GUI:

    python -m label_printer --paste rows.tsv --out labels.pdf
"""

import argparse
import sys
from pathlib import Path

from .layouts import LAYOUTS
from .parsing import expand, parse_paste
from .pdf import build_pdf
from .settings import default_layout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="label_printer",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--paste", help="tab-separated file with pasted rows (skips the GUI)")
    parser.add_argument("--out", default="etiketter.pdf")
    parser.add_argument("--layout", default=None, choices=list(LAYOUTS))
    parser.add_argument("--cut-line", action="store_true", help="draw a dashed cut line across each page")
    parser.add_argument(
        "--per-stk", action="store_true", help="one label per piece (STK) instead of one per row"
    )
    args = parser.parse_args(argv)

    if not args.paste:
        from .gui import run_gui

        run_gui()
        return 0

    labels = parse_paste(Path(args.paste).read_text(encoding="utf-8"), args.per_stk)
    for label in labels:
        if label.problems:
            print(f"linje {label.line} springes over: {', '.join(label.problems)}", file=sys.stderr)
        elif label.warnings:
            print(f"linje {label.line}: {', '.join(label.warnings)}", file=sys.stderr)
    printable = expand(labels, args.per_stk)
    if not printable:
        print("ingen komplette rækker -- intet at udskrive", file=sys.stderr)
        return 1
    pages = build_pdf(labels, args.out, args.layout or default_layout(), args.per_stk, args.cut_line)
    print(f"{len(printable)} etiketter, {pages} sider -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
