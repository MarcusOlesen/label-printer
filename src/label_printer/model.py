"""The label data model and the column layout of the pasted rows."""

from dataclasses import dataclass, field

# Column positions in a pasted row (0-based). This is the order of the shop's
# Google Sheet, which is also the order Label Miner exports.
COL_VARENR = 0  # A  Varenummer (the shop's own internal number)
COL_NAVN = 1  # B  Varenavn
COL_STK = 5  # F  STK (pieces)
COL_VEJL = 7  # H  comments / recommended price ("vejledende pris")
COL_PRIS = 8  # I  Pris pr stk (the outlet price)
MIN_COLS = COL_PRIS + 1

DISCLAIMER = "KØBT SOM BESET, UDEN RETURRET!"


@dataclass
class Label:
    """One pasted row, parsed.

    A row with ``problems`` is incomplete and is not printed; ``warnings``
    are printed anyway but flagged in the GUI. ``bad_cols`` / ``warn_cols``
    tell the GUI which cells to highlight.
    """

    varenr: str
    navn: str
    vejl: int | None  # recommended price; None prints an empty price
    pris: int | None  # our price
    stk: int
    line: int  # 1-based row number in the pasted text
    problems: list[str]
    bad_cols: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    warn_cols: list[int] = field(default_factory=list)
