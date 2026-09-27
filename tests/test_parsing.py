import pytest

from label_printer.model import COL_PRIS, COL_VEJL
from label_printer.parsing import (
    expand,
    format_dkk,
    parse_paste,
    parse_price,
    parse_rows,
    parse_vejl,
    split_name,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2500", 2500),
        ("2.500", 2500),
        ("2.500 kr", 2500),
        ("2,500", 2500),  # English sheet locale
        ("~1000", 1000),
        ("1.699,50", 1700),  # decimals are rounded
        ("1.699,49", 1699),
        ("", None),
        ("ingen pris", None),
    ],
)
def test_parse_price(text, expected):
    assert parse_price(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("4.999 kr", 4999),
        ("4.999 kr (6.999 kr)", 6999),  # the highest number is the normal price
        ("~2.199 kr (vejledende, ukendt variant)", 2199),
        ("1234 4321", 4321),  # a space between two numbers separates them...
        ("10 499", 10499),  # ...unless it is a thousands separator
        ("1 000", 1000),
        ("OBS: delvis vare (del 1/3)", None),  # fractions are never prices
        ("2/2 7.999 kr", 7999),
        ("", None),
    ],
)
def test_parse_vejl(text, expected):
    assert parse_vejl(text) == expected


@pytest.mark.parametrize(
    ("value", "expected"), [(1699, "1.699,-"), (999, "999,-"), (21999, "21.999,-"), (None, "")]
)
def test_format_dkk(value, expected):
    assert format_dkk(value) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (
            "Balo spisebord, egetræ | butterfly udtræk | 190/290x95 Eg",
            ("Balo spisebord, egetræ", "butterfly udtræk · 190/290x95 Eg"),
        ),
        (
            "Palermo chaiselong sofa, venstrevendt Loop Mørk Beige",
            ("Palermo chaiselong sofa", "venstrevendt Loop Mørk Beige"),
        ),
        ("Madrid XL chaiselong sofa højrevendt", ("Madrid XL chaiselong sofa højrevendt", "")),
    ],
)
def test_split_name(name, expected):
    assert split_name(name) == expected


def row(varenr="1234", navn="Vika spisebordsstol", stk="1", vejl="999 kr", pris="450"):
    """A pasted row in the sheet's column order (A..I)."""
    return [varenr, navn, "106753", "143975", "B", stk, "X", vejl, pris]


def test_complete_row_parses():
    (label,) = parse_rows([row()])
    assert (label.varenr, label.navn, label.vejl, label.pris, label.stk) == (
        "1234",
        "Vika spisebordsstol",
        999,
        450,
        1,
    )
    assert label.problems == [] and label.warnings == []


def test_missing_price_makes_row_incomplete():
    (label,) = parse_rows([row(pris="")])
    assert label.problems == ["mangler pris pr stk"]
    assert label.bad_cols == [COL_PRIS]


def test_missing_recommended_price_is_only_a_warning():
    (label,) = parse_rows([row(vejl="")])
    assert label.problems == []
    assert label.warn_cols == [COL_VEJL]


def test_too_few_columns_is_reported():
    """The classic mistake: the selection in the sheet didn't start at column A."""
    (label,) = parse_rows([row()[1:]])
    assert any("kolonne A" in problem for problem in label.problems)


def test_header_and_empty_rows_are_skipped():
    labels = parse_rows([["Varenummer", "Varenavn"], ["", "", ""], row()])
    assert len(labels) == 1
    assert labels[0].line == 3


def test_parse_paste_reads_tab_separated_text():
    text = "\t".join(row()) + "\r\n" + "\t".join(row(varenr="1235")) + "\r\n"
    assert [label.varenr for label in parse_paste(text)] == ["1234", "1235"]


def test_expand_one_label_per_row_by_default():
    labels = parse_rows([row(stk="2"), row(pris="")])
    assert len(expand(labels)) == 1  # the incomplete row is skipped


def test_expand_one_label_per_piece():
    labels = parse_rows([row(stk="2"), row(stk="3")], per_stk=True)
    assert len(expand(labels, per_stk=True)) == 5


def test_stk_only_validated_per_piece():
    assert parse_rows([row(stk="0")])[0].problems == []
    assert parse_rows([row(stk="0")], per_stk=True)[0].problems == ["STK skal være mindst 1"]
