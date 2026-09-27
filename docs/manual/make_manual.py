"""Builds the Danish user manual, build/Label-Printer-Vejledning.pdf.

    python docs/manual/make_manual.py            # new screenshots + PDF
    python docs/manual/make_manual.py --no-shots # reuse existing screenshots

The screenshots come from screenshots.py, which drives the real app, and the
price/name examples are computed with the program's own parsing functions,
so the manual always matches the program it ships with. The installer
(packaging/installer.iss) includes the PDF, and the "? Hjælp" button opens it.
"""

import argparse
import sys
from pathlib import Path

from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import PageBreak, Spacer, Table, TableStyle

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src"))

import demo_sheet  # noqa: E402
from manual_style import (  # noqa: E402
    BODY,
    CONTENT_W,
    GAP,
    H2,
    KICKER,
    LEAD,
    RULE,
    SMALL,
    Num,
    build_document,
    callouts,
    colour_table,
    framed,
    front_title,
    link,
    note,
    p,
    picture,
    section,
    toc_table,
    two_col,
    use_screenshots,
)  # fmt: skip

from label_printer import __version__  # noqa: E402
from label_printer.gui import MANUAL_NAME  # noqa: E402
from label_printer.parsing import format_dkk, parse_vejl, split_name  # noqa: E402

OUT = ROOT / "build" / MANUAL_NAME
SHOTS = ROOT / "build" / "manual-screenshots"
ICON = ROOT / "src" / "label_printer" / "assets" / "label_printer.ico"
W = CONTENT_W

SECTIONS = [
    ("oversigt", "Programmet på én side"),
    ("kort", "Sådan gør du – kort fortalt"),
    ("trin1", "Trin 1: Kopiér rækkerne i Google Sheets"),
    ("trin2", "Trin 2: Sæt rækkerne ind og tjek dem"),
    ("farver", "Røde og gule rækker"),
    ("ret", "Ret og slet i tabellen"),
    ("layout", "Layout og valg"),
    ("trin3", "Trin 3: Lav PDF, udskriv og klip"),
    ("regler", "Sådan læses priser og navne"),
    ("fejl", "Hvis noget går galt"),
    ("installation", "Installation og opdatering"),
]
TITLE = dict(SECTIONS)


def build_story():
    s = []
    W = CONTENT_W

    # ---- Front page ---------------------------------------------------------
    left = [
        Spacer(1, 20),
        p("VEJLEDNING", KICKER),
        front_title("Label Printer", ICON),
        Spacer(1, 6),
        p(
            "Laver prisskilte til butikken ud fra rækkerne i Google Sheets. Du kopierer "
            "rækkerne, sætter dem ind i Label Printer og får en PDF med to etiketter på "
            "hvert A4-ark, som klippes over på midten.",
            LEAD,
        ),
        p(
            f"Version {__version__}. Klik på et emne for at springe dertil. Vejledningen "
            "åbnes også med knappen <b>?&nbsp;Hjælp</b> i programmet.",
            SMALL,
        ),
        Spacer(1, 8),
        toc_table(SECTIONS, CONTENT_W - 330 - GAP - 20),
    ]
    s.append(
        two_col(
            left,
            [
                Spacer(1, 70),
                framed("09_etiket", 330),
                Spacer(1, 6),
                p("Sådan ser en færdig etiket ud (layout Klassisk).", SMALL),
            ],
            CONTENT_W - 330 - GAP,
        )
    )
    s.append(PageBreak())

    # ---- Overview -------------------------------------------------------------
    s += section(
        TITLE["oversigt"],
        "oversigt",
        "Overblik",
        "Hele programmet er ét vindue: en tabel til venstre og et panel til højre.",
    )
    img_w = 540
    s.append(
        two_col(
            framed("01_oversigt", img_w),
            callouts(
                [
                    (
                        1,
                        "<b>Tabellen.</b> Her sætter du rækkerne fra Google Sheets ind. Den ser ud og "
                        "virker som et regneark.",
                    ),
                    (2, "<b>? Hjælp</b> åbner denne vejledning."),
                    (
                        3,
                        "<b>Indsæt fra udklipsholder</b> sætter det, du har kopieret, ind i tabellen "
                        "(erstatter det, der står der).",
                    ),
                    (4, "<b>Ryd tabel</b> tømmer tabellen, så du kan starte forfra."),
                    (5, "<b>Tællere:</b> hvor mange rækker, etiketter og A4-sider der bliver lavet."),
                    (6, "<b>Forhåndsvisning</b> af etiketten for den række, du har klikket på."),
                    (7, "<b>Layout og valg</b> – udseende, antal etiketter og skærelinje."),
                    (8, "<b>Generér PDF</b> laver filen, der skal udskrives."),
                ],
                W - img_w - GAP,
            ),
            img_w,
        )
    )
    s.append(PageBreak())

    # ---- Short version --------------------------------------------------------
    s += section(
        TITLE["kort"],
        "kort",
        "Kort fortalt",
        "Det er alt, du skal gøre til hverdag. Detaljerne står på de næste sider.",
    )
    steps = [
        (
            "Kopiér",
            f"Markér varerækkerne i Google Sheets <b>fra kolonne A</b> (uden "
            f"overskriften) og tryk <b>Ctrl+C</b>. {link('trin1', 'Se trin 1')}",
        ),
        (
            "Indsæt",
            f"Åbn Label Printer, klik i den første celle og tryk <b>Ctrl+V</b>. {link('trin2', 'Se trin 2')}",
        ),
        (
            "Tjek",
            f"Står der <b>✓ Klar</b>? Røde rækker bliver ikke udskrevet, gule får ingen "
            f"vejl. pris. Klik på en række for at se etiketten. {link('farver', 'Om farverne')}",
        ),
        (
            "Lav PDF",
            f"Klik <b>Generér PDF</b> og vælg, hvor filen skal gemmes. Den åbner af sig "
            f"selv. {link('trin3', 'Se trin 3')}",
        ),
        (
            "Udskriv og klip",
            "Tryk <b>Ctrl+P</b> og udskriv. Klip hvert ark over på midten – så har du to etiketter.",
        ),
    ]
    rows = [
        [
            Num(i + 1, 26),
            p(f"<b>{t}</b>", ParagraphStyle("st", parent=BODY, fontSize=13.5, leading=17)),
            p(txt, BODY),
        ]
        for i, (t, txt) in enumerate(steps)
    ]
    t = Table(rows, colWidths=[40, 130, W - 170])
    t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -2), 0.5, RULE),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 12),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )
    s.append(t)
    s.append(Spacer(1, 14))
    s.append(
        note(
            "<b>Tip:</b> Du kan altid prøve dig frem. Label Printer ændrer aldrig noget i "
            "Google Sheets, og Ctrl+Z fortryder ændringer i tabellen."
        )
    )
    s.append(PageBreak())

    # ---- Step 1 ---------------------------------------------------------------
    s += section(
        TITLE["trin1"],
        "trin1",
        "Trin 1",
        "Label Printer skal have rækkerne i samme kolonne-rækkefølge som arket, så "
        "markeringen skal starte i kolonne A.",
    )
    img_w = 470
    s.append(
        two_col(
            framed("07_google_sheet", img_w),
            [
                callouts(
                    [
                        (
                            1,
                            "Klik på kolonne A i den <b>første vare</b> (her række 3) og træk ned til den "
                            "sidste vare og mod højre til mindst kolonne I (<i>Pris pr stk</i>). Flere "
                            "kolonner gør ikke noget.",
                        ),
                        (
                            2,
                            "Feltet øverst til venstre viser markeringen. Den skal <b>starte med A</b>, "
                            f"fx <i>A3:J{2 + len(demo_sheet.DEMO_ROWS)}</i>.",
                        ),
                        (
                            3,
                            "Overskriften (række 1) og dato-rækken (række 2) skal <b>ikke</b> med. Kommer "
                            "overskriften med, springes den over; dato-rækken bliver rød og udskrives ikke.",
                        ),
                    ],
                    W - img_w - GAP,
                ),
                Spacer(1, 4),
                p("Tryk derefter <b>Ctrl+C</b> for at kopiere."),
                note(
                    "Rækker uden <i>Pris pr stk</i> (fx de røde »delvis vare« i arket) må gerne komme "
                    "med – de bliver bare ikke udskrevet."
                ),
            ],
            img_w,
        )
    )
    s.append(Spacer(1, 10))
    s.append(
        p(
            "Label Printer bruger disse kolonner: <b>A</b> Varenummer (står nederst på "
            "etiketten), <b>B</b> Varenavn, <b>F</b> STK, <b>H</b> Vejledende "
            "priser og <b>I</b> Pris pr stk. Flyttes kolonnerne rundt i arket, virker det ikke "
            "længere.",
            SMALL,
        )
    )
    s.append(PageBreak())

    # ---- Step 2 ---------------------------------------------------------------
    s += section(
        TITLE["trin2"],
        "trin2",
        "Trin 2",
        "Klik i den første celle i tabellen (række 1, Varenummer) og tryk <b>Ctrl+V</b> "
        "– eller klik <b>Indsæt fra udklipsholder</b>.",
    )
    img_w = 505
    s.append(
        two_col(
            framed("02_indsat", img_w),
            [
                callouts(
                    [
                        (
                            1,
                            "<b>Blå overskrifter</b> er de kolonner, der kommer på etiketten. Grå kolonner "
                            "bruges ikke.",
                        ),
                        (2, "<b>✓ Klar til udskrift</b> betyder, at alle rækker er i orden."),
                        (
                            3,
                            "<b>Forhåndsvisningen</b> viser etiketten for den række, du har klikket på. Kig "
                            "især på <i>Vejl. salgspris</i> og <i>Vores pris</i>.",
                        ),
                    ],
                    W - img_w - GAP,
                ),
                note(
                    "Tællerne øverst viser, hvor meget der bliver udskrevet: her 15 etiketter på 8 "
                    "sider (to etiketter pr. ark)."
                ),
            ],
            img_w,
        )
    )
    s.append(PageBreak())

    # ---- Colours ---------------------------------------------------------------
    s += section(
        TITLE["farver"],
        "farver",
        "Trin 2 – tjek",
        "Farverne i tabellen viser, hvad der skal kigges på. Du kan altid udskrive – "
        "røde rækker springes bare over.",
    )
    img_w = 505
    s.append(
        two_col(
            framed("03_roed_gul", img_w),
            [
                callouts(
                    [
                        (
                            1,
                            "<b>Rød række:</b> rækken mangler varenummer, varenavn eller pris pr stk og "
                            "bliver <b>ikke</b> udskrevet. Feltet, der mangler, er mørkere rødt.",
                        ),
                        (
                            2,
                            "<b>Gul celle:</b> der er ingen vejledende pris. Etiketten udskrives, men uden "
                            "tal efter »Vejl. salgspris«.",
                        ),
                        (
                            3,
                            "<b>Forklaringen</b> viser, hvor mange rækker det gælder. Den forsvinder, når "
                            "der ikke er noget at vise.",
                        ),
                    ],
                    W - img_w - GAP,
                ),
                p("<b>Hvad gør jeg?</b>", H2),
                p(
                    "Ret prisen i Google Sheets og kopiér igen – eller skriv den direkte i cellen i "
                    "Label Printer. Skal varen ikke have en etiket, kan du bare lade den være eller "
                    f"{link('ret', 'slette rækken')}."
                ),
            ],
            img_w,
        )
    )
    s.append(PageBreak())

    # ---- Editing ---------------------------------------------------------------
    s += section(
        TITLE["ret"],
        "ret",
        "Tabellen",
        "Ændringer her gælder kun etiketterne – Google Sheets bliver ikke ændret.",
    )
    img_w = 505
    s.append(
        two_col(
            framed("04_slet_raekker", img_w),
            [
                callouts(
                    [
                        (
                            1,
                            "<b>Slet rækker:</b> klik på rækkenummeret. Træk, eller hold Shift og "
                            "klik, for at vælge flere. Tryk derefter <b>Delete</b> eller "
                            "<b>Backspace</b>.",
                        )
                    ],
                    W - img_w - GAP,
                ),
                colour_table(
                    ["Det vil jeg", "Sådan"],
                    [
                        ["Rette en celle", "Dobbeltklik på cellen (eller begynd at skrive) og tryk Enter."],
                        ["Tømme celler", "Markér cellerne og tryk Delete."],
                        ["Fortryde", "Ctrl+Z."],
                        ["Flere muligheder", "Højreklik i tabellen (fx Indsæt rækker, Slet rækker)."],
                        ["Starte forfra", "Klik Ryd tabel."],
                    ],
                    [95, W - img_w - GAP - 95],
                    ("neutral", "good"),
                ),
            ],
            img_w,
        )
    )
    s.append(PageBreak())

    # ---- Layout and options ------------------------------------------------------
    s += section(
        TITLE["layout"],
        "layout",
        "Valg",
        "Valgene står under forhåndsvisningen. Hvis du ikke rører dem, får du "
        "standard-udseendet og én etiket pr. række.",
    )
    panel_w = 400
    s.append(
        two_col(
            [framed("06_indstillinger", panel_w)],
            [
                callouts(
                    [
                        (
                            1,
                            "<b>Layout:</b> vælg etikettens udseende (se herunder). <i>Klassisk</i> er "
                            "standard.",
                        ),
                        (
                            2,
                            "<b>Gør til standard</b> gemmer det valgte layout, så programmet starter med "
                            "det næste gang. Gælder kun denne computer.",
                        ),
                        (
                            3,
                            "<b>Én etiket pr. stk:</b> slået fra laves der én etiket pr. række. Slået til "
                            "laves der én pr. stk – STK = 2 giver to etiketter.",
                        ),
                        (4, "<b>Skærelinje i midten:</b> tegner en tynd stiplet linje at klippe efter."),
                        (5, "<b>Generér PDF:</b> se trin 3."),
                    ],
                    W - panel_w - GAP,
                ),
            ],
            panel_w,
        )
    )
    s.append(PageBreak())
    s += section(
        "De fire layouts",
        "layouts",
        "Layout",
        "Samme vare i hvert layout. De tre nederste deler navnet, så varen står med fed "
        f"og detaljerne under ({link('regler', 'sådan deles navnet')}).",
    )
    s.append(picture("08_layouts", 490))
    s.append(PageBreak())

    # ---- Step 3 ------------------------------------------------------------------
    s += section(TITLE["trin3"], "trin3", "Trin 3")
    sheet_w = 300
    s.append(
        two_col(
            [
                callouts(
                    [
                        (
                            1,
                            "Klik <b>Generér PDF</b>. Vælg hvor filen skal gemmes – navnet foreslås "
                            "automatisk (fx <i>etiketter_2026-09-24.pdf</i>).",
                        ),
                        (2, "PDF'en åbner i browseren. Tryk <b>Ctrl+P</b> og udskriv."),
                        (
                            3,
                            "Klip hvert ark over på midten. Den øverste og den nederste halvdel er hver "
                            "sin etiket.",
                        ),
                    ],
                    W - sheet_w - GAP,
                ),
                Spacer(1, 8),
                note(
                    "<b>Er etiketterne for små, eller sidder midten forkert?</b> Så er arket blevet "
                    "skaleret. Tryk Ctrl+P igen, åbn <i>Flere indstillinger</i> og vælg "
                    "<b>Faktisk størrelse</b> (eller skala 100&nbsp;%) i stedet for »Tilpas til side«."
                ),
                Spacer(1, 8),
                p(
                    "Rækker, der er røde i tabellen, kommer ikke med i PDF'en. Er der et ulige antal "
                    "etiketter, er den nederste halvdel af sidste ark tom.",
                    SMALL,
                ),
            ],
            [framed("10_ark", sheet_w - 10)],
            W - sheet_w - GAP,
        )
    )
    s.append(PageBreak())

    # ---- Rules ---------------------------------------------------------------------
    s += section(
        TITLE["regler"],
        "regler",
        "Regler",
        "Programmet læser priserne selv. Tabellerne herunder er lavet med programmets "
        "egne regler, så de passer præcist.",
    )
    vejl_examples = [
        "4.999 kr",
        "4.999 kr (6.999 kr)",
        "1234 4321",
        "~2.199 kr (vejledende, ukendt variant)",
        "1,000",
        "OBS: delvis vare (del 1/3)",
        "",
    ]
    vejl_rows = [
        [f"<i>{e}</i>" if e else "<i>(tom)</i>", format_dkk(parse_vejl(e)) or "– (tom på etiketten)"]
        for e in vejl_examples
    ]
    name_examples = [
        "Marmoris spisebord, keramik | 200x100 Pandora/Hvid",
        "Sevilla U-sofa, venstrevendt Loop Mørk Beige",
        "Madrid XL chaiselong sofa højrevendt Modesto",
    ]
    name_rows = []
    for n in name_examples:
        title, details = split_name(n)
        name_rows.append([n, f"<b>{title}</b>" + (f"<br/>{details}" if details else "")])
    half = (W - GAP) / 2
    s.append(
        two_col(
            [
                p("Vejledende pris (kolonne H)", H2),
                p(
                    "Står der flere tal, bruges det <b>højeste</b>. »kr«, »~«, tekst og brøker "
                    "som »del 1/3« ignoreres.",
                    SMALL,
                ),
                colour_table(
                    ["Kommentar", "Vejl. salgspris"],
                    vejl_rows,
                    [half * 0.6, half * 0.4],
                    ("neutral", "accent"),
                ),
                Spacer(1, 8),
                p(
                    "<b>Pris pr stk</b> (kolonne I) skal indeholde ét tal, fx <i>2500</i>, <i>2.500</i> "
                    "eller <i>2.500 kr</i>.",
                    SMALL,
                ),
            ],
            [
                p("Varenavnet (kolonne B)", H2),
                p(
                    "<i>Klassisk</i> skriver navnet præcis som i arket. De andre layouts deler det ved "
                    "første »|« – eller ved første komma, hvis der ikke er noget »|«.",
                    SMALL,
                ),
                colour_table(
                    ["I arket", "På etiketten"], name_rows, [half * 0.5, half * 0.5], ("neutral", "accent")
                ),
                Spacer(1, 8),
                p("Vil du bestemme, hvor navnet deles, så sæt et »|« ind i navnet i arket.", SMALL),
            ],
            half,
        )
    )
    s.append(PageBreak())

    # ---- Troubleshooting -------------------------------------------------------------
    s += section(TITLE["fejl"], "fejl", "Fejlfinding")
    trouble = [
        [
            "Alle rækker er røde, og der står »Ingen komplette rækker«",
            "Markeringen i Google Sheets startede ikke i kolonne A.",
            f"Kopiér igen fra kolonne A. {link('eksempel', 'Se eksemplet')}",
        ],
        [
            "Priserne står i de forkerte kolonner",
            "Kolonnerne i Google Sheets er blevet flyttet.",
            "Kolonnerne skal stå i samme rækkefølge som fra Label Miner.",
        ],
        [
            "Vejl. salgspris ser forkert ud",
            "Kommentaren indeholder et andet tal, der er større end prisen (fx et mål).",
            "Tjek forhåndsvisningen og ret kommentaren, så den kun indeholder prisen.",
        ],
        [
            "Etiketterne er for små, eller midten sidder forkert",
            "Arket er udskrevet med »Tilpas til side«.",
            f"Vælg »Faktisk størrelse«, når du udskriver. {link('trin3', 'Se trin 3')}",
        ],
        [
            "»Kunne ikke gemme filen«",
            "En PDF med samme navn er åben.",
            "Luk den gamle PDF, eller gem under et andet navn.",
        ],
        [
            "Ctrl+V gør ingenting",
            "Der er ikke valgt en celle.",
            "Klik i den første celle, eller brug Indsæt fra udklipsholder.",
        ],
        [
            "Generér PDF er grå",
            "Der er ingen komplette rækker.",
            f"Se {link('farver', 'røde og gule rækker')}.",
        ],
        [
            "For mange eller for få etiketter",
            "Valget »Én etiket pr. stk«.",
            f"Slå det til eller fra. {link('layout', 'Se valg')}",
        ],
        [
            "Navnet deles et mærkeligt sted",
            "Navnet har et komma, der ikke skal dele det.",
            "Sæt »|« der, hvor det skal deles, eller brug layout Klassisk.",
        ],
    ]
    s.append(
        colour_table(
            ["Det sker", "Hvorfor", "Gør sådan"],
            trouble,
            [W * 0.3, W * 0.33, W * 0.37],
            ("bad", "neutral", "good"),
        )
    )
    s.append(PageBreak())

    s += section(
        "Eksempel: markeringen startede i kolonne B",
        "eksempel",
        "Fejlfinding",
        "Sådan ser det ud, hvis kolonne A ikke kom med, da rækkerne blev kopieret.",
    )
    img_w = 540
    s.append(
        two_col(
            framed("05_forkert_kolonne", img_w),
            [
                callouts(
                    [
                        (
                            1,
                            "Varenavnet står under <i>Varenummer</i>, og alle andre kolonner er rykket én "
                            "plads. Derfor mangler <i>Pris pr stk</i>, og alle rækker bliver røde.",
                        ),
                        (2, "Der står »Ingen komplette rækker«, og <b>Generér PDF</b> er grå."),
                    ],
                    W - img_w - GAP,
                ),
                p(
                    "<b>Løsning:</b> klik <b>Ryd tabel</b>, gå tilbage til Google Sheets og markér igen "
                    f"fra kolonne A. {link('trin1', 'Se trin 1')}"
                ),
            ],
            img_w,
        )
    )
    s.append(PageBreak())

    # ---- Installation ------------------------------------------------------------------
    s += section(
        TITLE["installation"],
        "installation",
        "Til nye computere",
        "Programmet installeres med én fil: <b>Label-Printer-Setup.exe</b>. Der skal ikke installeres andet.",
    )
    half = (W - GAP) / 2
    s.append(
        two_col(
            [
                p("Første gang", H2),
                callouts(
                    [
                        (1, "Dobbeltklik på <b>Label-Printer-Setup.exe</b>."),
                        (
                            2,
                            "Siger Windows »Windows beskyttede din pc«, så klik <b>Flere oplysninger</b> og "
                            "derefter <b>Kør alligevel</b>. Advarslen kommer, fordi programmet er lavet til "
                            "butikken og ikke købt i en butik – det er normalt.",
                        ),
                        (3, "Klik dig gennem installationen. Der kræves ikke administrator-adgangskode."),
                        (
                            4,
                            "Start programmet med ikonet <b>Label Printer</b> på skrivebordet eller i "
                            "Start-menuen.",
                        ),
                    ],
                    half,
                ),
            ],
            [
                p("Opdatering", H2),
                p(
                    "Kør den nye <b>Label-Printer-Setup.exe</b> på samme måde. Den erstatter den gamle "
                    "version – du skal ikke afinstallere først, og det valgte standard-layout bliver husket."
                ),
                Spacer(1, 8),
                p("Det bliver installeret", H2),
                colour_table(
                    ["Hvad", "Hvor"],
                    [
                        ["Programmet", "Ikon på skrivebordet og i Start-menuen"],
                        [
                            "Denne vejledning",
                            "<b>?&nbsp;Hjælp</b> i programmet, eller Start-menuen "
                            "(<i>Label Printer – Vejledning</i>)",
                        ],
                        ["Afinstallering", "Start-menuen (<i>Afinstaller Label Printer</i>)"],
                    ],
                    [half * 0.35, half * 0.65],
                    ("neutral", "accent"),
                ),
            ],
            half,
        )
    )
    return s


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-shots", action="store_true", help="reuse existing screenshots")
    args = parser.parse_args()
    if not args.no_shots:
        import screenshots

        screenshots.take_all()
    use_screenshots(SHOTS)
    OUT.parent.mkdir(exist_ok=True)
    build_document(
        OUT,
        build_story,
        title="Label Printer – Vejledning",
        subject=f"Brugervejledning til Label Printer {__version__}",
        footer=f"Label Printer {__version__}  ·  Vejledning",
    )
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
