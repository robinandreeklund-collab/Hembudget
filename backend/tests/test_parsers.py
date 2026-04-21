from decimal import Decimal

from hembudget.parsers import AmexParser, NordeaParser, SebKortParser, detect_parser


AMEX_CSV = (
    "Datum;Beskrivning;Belopp;Utlandsbelopp;Kategori\n"
    "2026-03-15;ICA NARA STOCKHOLM;-542,50;;Dagligvaror\n"
    "2026-03-16;SPOTIFY SE;-129,00;;Streaming\n"
    "2026-03-20;AMEX ÅTERBETALNING;500,00;;\n"
).encode("utf-8")

NORDEA_CSV = (
    "Bokföringsdag;Belopp;Avsändare;Mottagare;Namn;Rubrik;Saldo;Valuta\n"
    "2026-03-25;-1200,00;Robin;Vattenfall;Vattenfall;Elräkning;15000,00;SEK\n"
    "2026-03-28;30000,00;Arbetsgivare AB;Robin;Lön mars;Lön;45000,00;SEK\n"
).encode("utf-8")

SEB_KORT_CSV = (
    "Datum;Specifikation;Ort;Valuta;Utl.belopp/moms;Belopp\n"
    "2026-03-10;OKQ8 STATION;STOCKHOLM;SEK;;-650,00\n"
    "2026-03-12;AMAZON UK;LONDON;GBP;12,34;-150,00\n"
).encode("utf-8")


def test_amex_parser():
    p = AmexParser()
    assert p.detect(AMEX_CSV)
    rows = p.parse(AMEX_CSV)
    assert len(rows) == 3
    assert rows[0].amount == Decimal("-542.50")
    assert "ICA" in rows[0].description.upper()


def test_nordea_parser():
    p = NordeaParser()
    assert p.detect(NORDEA_CSV)
    rows = p.parse(NORDEA_CSV)
    assert len(rows) == 2
    assert rows[1].amount == Decimal("30000.00")
    assert rows[1].balance == Decimal("45000.00")


def test_seb_kort_parser():
    p = SebKortParser()
    assert p.detect(SEB_KORT_CSV)
    rows = p.parse(SEB_KORT_CSV)
    assert len(rows) == 2
    assert rows[0].amount == Decimal("-650.00")


def test_detect_parser():
    assert detect_parser(AMEX_CSV).bank == "amex"
    assert detect_parser(NORDEA_CSV).bank == "nordea"
    assert detect_parser(SEB_KORT_CSV).bank == "seb_kort"


def test_stable_hash_dedup():
    rows = NordeaParser().parse(NORDEA_CSV)
    h1 = rows[0].stable_hash(42)
    h2 = rows[0].stable_hash(42)
    h3 = rows[1].stable_hash(42)
    assert h1 == h2
    assert h1 != h3


def test_identical_same_day_rows_not_deduped():
    """Nordea: two identical 'Avgift extra kort' rows on the same day get
    different balances, so they hash to different values."""
    csv = (
        "Bokföringsdag;Belopp;Avsändare;Mottagare;Namn;Rubrik;Saldo;Valuta\n"
        "2026-03-01;-24,00;1722 20 34439;;;Avgift extra kort;15532,06;SEK\n"
        "2026-03-01;-24,00;1722 20 34439;;;Avgift extra kort;15556,06;SEK\n"
    ).encode("utf-8")
    rows = NordeaParser().parse(csv)
    assert len(rows) == 2
    h1 = rows[0].stable_hash(1)
    h2 = rows[1].stable_hash(1)
    assert h1 != h2, "identical rows with different balances must hash differently"


def test_nordea_description_strips_own_account():
    """Own account number (Avsändare = 1722 20 34439) should not appear
    in the description — only real counterparties."""
    csv = (
        "Bokföringsdag;Belopp;Avsändare;Mottagare;Namn;Rubrik;Saldo;Valuta\n"
        "2026-03-15;-500,00;1722 20 34439;;;Betalning BG 5010-9198 VOLKSWAGEN F;1000,00;SEK\n"
        "2026-03-16;-149,00;1722 20 34439;;;Avgift extra kort;851,00;SEK\n"
    ).encode("utf-8")
    rows = NordeaParser().parse(csv)
    assert len(rows) == 2
    for r in rows:
        assert "1722" not in r.description, f"leaked own account: {r.description!r}"
    assert rows[0].description == "Betalning BG 5010-9198 VOLKSWAGEN F"
    assert rows[1].description == "Avgift extra kort"


def test_seb_kort_xlsx_parser_detects_and_parses():
    """Verify the SEB xlsx parser reads the binary format and inverts signs
    correctly (SEB reports +=purchase, -=payment; we want -=expense)."""
    from io import BytesIO
    from decimal import Decimal
    from datetime import datetime

    from openpyxl import Workbook

    from hembudget.parsers import SebKortXlsxParser

    wb = Workbook()
    ws = wb.active
    ws.title = "Transaktioner"
    ws.append(["Transaktionsexport", "", "", "", "", "", "2026-04-21"])
    ws.append([])
    ws.append(["Totalt övriga händelser"])
    ws.append(["Datum", "Bokfört", "Specifikation", "Ort", "Valuta", "Utl. belopp", "Belopp"])
    ws.append([datetime(2026, 1, 13), datetime(2026, 1, 13), "Inbetalning", "", "SEK", 0, -10000])
    ws.append([datetime(2026, 1, 31), datetime(2026, 1, 31), "Ränta", "", "SEK", 0, 204.42])
    ws.append([datetime(2026, 1, 5), datetime(2026, 1, 5), "ICA", "Stockholm", "SEK", 0, 542.50])

    buf = BytesIO()
    wb.save(buf)
    content = buf.getvalue()

    p = SebKortXlsxParser()
    assert p.detect(content)
    rows = p.parse(content)
    assert len(rows) == 3
    # Inbetalning: -10000 in SEB → +10000 in our convention (payment reduces debt)
    inbet = next(r for r in rows if "Inbetalning" in r.description)
    assert inbet.amount == Decimal("10000")
    # Ränta: +204.42 in SEB → -204.42 (expense)
    ranta = next(r for r in rows if "Ränta" in r.description)
    assert ranta.amount == Decimal("-204.42")
    # ICA: +542.50 → -542.50
    ica = next(r for r in rows if "ICA" in r.description)
    assert ica.amount == Decimal("-542.50")
    assert ica.description == "ICA [Stockholm]"
