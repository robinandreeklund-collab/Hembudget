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
