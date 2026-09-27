import pytest

from label_printer.__main__ import main
from label_printer.layouts import LAYOUTS
from label_printer.parsing import parse_rows
from label_printer.pdf import build_pdf, render_label_image


def row(varenr, navn, stk, vejl, pris):
    """A pasted row in the sheet's column order (A..I)."""
    return [varenr, navn, "", "", "", stk, "X", vejl, pris]


ROWS = [
    row("1235", "Marmoris spisebord, keramik | 200x100 Pandora/Hvid", "1", "4.999 kr (6.999 kr)", "2.500"),
    row("1240", "Eden spisebordsstol, Egetræ | Naturflet", "2", "", "1.000"),
    row(
        "1250",
        "Madrid XL chaiselong sofa højrevendt Modesto Brun med et langt navn",
        "1",
        "15.999 kr",
        "8.000",
    ),
]


@pytest.mark.parametrize("layout", list(LAYOUTS))
def test_build_pdf_two_labels_per_page(tmp_path, layout):
    labels = parse_rows(ROWS)
    path = tmp_path / "labels.pdf"
    pages = build_pdf(labels, path, layout)
    assert pages == 2  # three labels -> two A4 pages
    assert path.read_bytes().startswith(b"%PDF")


def test_build_pdf_one_label_per_piece(tmp_path):
    labels = parse_rows(ROWS, per_stk=True)
    assert build_pdf(labels, tmp_path / "labels.pdf", per_stk=True) == 2  # 1 + 2 + 1 labels


@pytest.mark.parametrize("layout", list(LAYOUTS))
def test_render_preview(layout):
    pytest.importorskip("pypdfium2")
    image = render_label_image(parse_rows(ROWS)[0], 300, layout)
    assert image.width == 300
    # Something was drawn: the label isn't a blank page
    assert image.convert("L").getextrema()[0] < 100


def test_cli_headless(tmp_path, capsys):
    paste = tmp_path / "rows.tsv"
    paste.write_text("\n".join("\t".join(r) for r in ROWS), encoding="utf-8")
    out = tmp_path / "labels.pdf"
    assert main(["--paste", str(paste), "--out", str(out), "--layout", "modern"]) == 0
    assert out.exists()
    assert "3 etiketter, 2 sider" in capsys.readouterr().out


def test_cli_nothing_to_print(tmp_path):
    paste = tmp_path / "rows.tsv"
    paste.write_text("1234\tNavn uden pris", encoding="utf-8")
    assert main(["--paste", str(paste), "--out", str(tmp_path / "x.pdf")]) == 1
