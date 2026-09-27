"""Reading prices, rows and product names from the pasted sheet data.

The sheet is filled in by hand and by Label Miner, so prices come in many
shapes: '1.699 kr', '1,699', '~1699', '8.999 kr (11.999 kr)', '1234 4321' or
'OBS: delvis vare (del 1/3)'. Everything here is pure and unit-tested.
"""

import csv
import io
import re
from collections.abc import Iterable

from .model import COL_NAVN, COL_PRIS, COL_STK, COL_VARENR, COL_VEJL, MIN_COLS, Label

# A number: thousands separated by '.' (Danish) or ',' (English sheet locale)
# followed by exactly three digits, optionally with ',' and 1-2 decimals.
_NUMBER_RE = re.compile(r"(?<!\d)(?:\d{1,3}(?:[.,]\d{3})+(?:,\d{1,2})?(?!\d)|\d+(?:,\d{1,2})?(?!\d))")

# A space is a thousands separator only after a 1-2 digit group followed by
# exactly three digits ('1 000', '10 499'); prices never reach 100.000. Any
# other space separates two numbers: '1234 4321', '899 999'.
_SPACE_THOUSANDS_RE = re.compile(r"(?<![\d.,])(\d{1,2})[  ](\d{3})(?![\d])")

# Small fractions like 'del 1/3' or '2/2' are never prices; they are removed
# before reading numbers, or 'OBS: delvis vare (del 1/3)' would give 3.
_FRACTION_RE = re.compile(r"(?<![\d.,])\d{1,2} ?/ ?\d{1,2}(?![\d.,])")


def _to_int(number: str) -> int:
    """'1.699' -> 1699, '1,699' -> 1699, '1.699,50' -> 1700 (rounded)."""
    match = re.fullmatch(r"(.*?)(?:,(\d{1,2}))?", number)
    whole, decimals = match.group(1), match.group(2)
    value = int(whole.replace(".", "").replace(",", ""))
    if decimals and int(decimals[0]) >= 5:
        value += 1
    return value


def _numbers(text: str) -> list[int]:
    text = _FRACTION_RE.sub(" ", text or "")
    text = _SPACE_THOUSANDS_RE.sub(r"\1\2", text)
    return [_to_int(n) for n in _NUMBER_RE.findall(text)]


def parse_price(text: str) -> int | None:
    """The first number in a cell like '1.000 kr', '~1000' or '1.000,00'."""
    numbers = _numbers(text)
    return numbers[0] if numbers else None


def parse_vejl(text: str) -> int | None:
    """The recommended price: the highest number in the comment cell.

    '8.999 kr (11.999 kr)' -> 11999 (sale price with the normal price in
    brackets), '1234 4321' -> 4321.
    """
    numbers = _numbers(text)
    return max(numbers) if numbers else None


def format_dkk(value: int | None) -> str:
    """1699 -> '1.699,-'. None gives '' so the label keeps its caption but
    shows no number."""
    if value is None:
        return ""
    return f"{value:,}".replace(",", ".") + ",-"


def parse_paste(text: str, per_stk: bool = False) -> list[Label]:
    """Parse tab-separated rows as copied from Google Sheets."""
    return parse_rows(csv.reader(io.StringIO(text.strip("\r\n")), delimiter="\t"), per_stk)


def parse_rows(rows: Iterable[list], per_stk: bool = False) -> list[Label]:
    """Parse rows into labels, recording what is missing in each.

    STK is only validated when ``per_stk`` is set (one label per piece);
    otherwise every complete row gives one label.
    """
    labels = []
    for line_no, row in enumerate(rows, start=1):
        row = ["" if cell is None else str(cell) for cell in row]
        if not any(cell.strip() for cell in row):
            continue
        if row[0].strip().lower() == "varenummer":
            continue  # the header row was copied too
        problems = []
        if len(row) < MIN_COLS:
            problems.append("for få kolonner (start markeringen i kolonne A)")
        row = [cell.strip() for cell in row] + [""] * max(0, MIN_COLS - len(row))

        varenr, navn = row[COL_VARENR], row[COL_NAVN]
        vejl, pris = parse_vejl(row[COL_VEJL]), parse_price(row[COL_PRIS])
        stk = parse_price(row[COL_STK])
        stk = 1 if stk is None else stk

        bad_cols = []
        checks = [
            (varenr, COL_VARENR, "mangler varenummer"),
            (navn, COL_NAVN, "mangler varenavn"),
            (pris is not None, COL_PRIS, "mangler pris pr stk"),
            (stk >= 1 or not per_stk, COL_STK, "STK skal være mindst 1"),
        ]
        for ok, col, message in checks:
            if not ok:
                problems.append(message)
                bad_cols.append(col)
        warnings, warn_cols = [], []
        if vejl is None:  # printed with an empty recommended price
            warnings.append("ingen vejl. pris")
            warn_cols.append(COL_VEJL)
        labels.append(Label(varenr, navn, vejl, pris, stk, line_no, problems, bad_cols, warnings, warn_cols))
    return labels


def expand(labels: list[Label], per_stk: bool = False) -> list[Label]:
    """One entry per physical label: incomplete rows are skipped, and with
    ``per_stk`` a row with STK = 2 gives two labels."""
    complete = [label for label in labels if not label.problems]
    if not per_stk:
        return complete
    return [label for label in complete for _ in range(label.stk)]


def split_name(navn: str) -> tuple[str, str]:
    """Split a product name into a title and its details.

    'Balo spisebord, egetræ | butterfly udtræk | 190/290x95 Eg'
        -> ('Balo spisebord, egetræ', 'butterfly udtræk · 190/290x95 Eg')
    Without ' | ' the first ', ' is used instead:
    'Palermo chaiselong sofa, venstrevendt Loop Mørk Beige'
        -> ('Palermo chaiselong sofa', 'venstrevendt Loop Mørk Beige')
    Names with neither stay whole.
    """
    parts = [part.strip() for part in navn.split("|") if part.strip()]
    if len(parts) >= 2:
        return parts[0], " · ".join(parts[1:])
    title, sep, details = navn.strip().partition(", ")
    if sep and title.strip() and details.strip():
        return title.strip(), details.strip()
    return navn.strip(), ""
