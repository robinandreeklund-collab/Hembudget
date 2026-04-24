"""Test av SEB Kort (SAS EuroBonus MC Premium) KONTOUTDRAG-parser."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from hembudget.parsers.pdf_statements.seb_kort import (
    looks_like_seb_kort,
    parse_seb_kort,
    _parse_amount,
    _parse_date_yymmdd,
)


SAMPLE_TEXT = """\
Sida
1/2

KONTOUTDRAG december 2025
SAS EuroBonus MC Premium

ROBIN FRÖJD
KLARABERGSGATAN 9
544 31  HJO

Kontonummer: 403538411614789

Datum     Specifikation              Ort           Valuta     Kurs      Bokföringsdag/  Belopp
                                                                        Utl.Belopp
          SKULD FRÅN 251201                                                      6032,91
251229    BETALT BG DATUM 251229                                                -6032,91
KORT NR **** **** **** 9506   EVELINA FRÖJD
251128    COOP HJO              HJO           SEK                 251201            70,90
251128    HIOGOTTEN AB          HJO           SEK                 251201           127,67
251129    HJO CAN HELP          HJO           SEK                 251201            20,00
251129    HEM OCH HOBBY         HJO           SEK                 251201           372,00
251129    HIO CAN HELP          HJO           SEK                 251201            70,00
251130    RUSTA - 28 SKA.VDE    SKOEVDE       SEK                 251201           174,30
251202    HEM OCH HOBBY         HJO           SEK                 251202           167,50
251203    PIZZERIA & REST       HJO           SEK                 251203           130,00
251203    CASTELLO SUSHI        HJO           SEK                 251204           139,00
251203    HAMMARKIOSKEN         HJO           SEK                 251204            45,00
251203    HEM OCH HOBBY         HJO           SEK                 251204           295,00
251208    HEM OCH HOBBY         HJO           SEK                 251209           467,00
251210    HEM OCH HOBBY         HJO           SEK                 251211           300,00
251212    SP SOMVIA WINE STORE  FREDERIKSBERG SEK                 251215          1499,00
251212    COOP HJO              HJO           SEK                 251215           657,92
251218    HJO CAN HELP          HJO           SEK                 251219           206,00
251219    AKADEMIBOKHANDE       SKÖVDE        SEK                 251222           199,00
251219    GINA TRICOT           SKOEVDE       SEK                 251222           149,95
251219    LINDEX SKOVDE 0       SKOEVDE       SEK                 251222           184,60
251219    COOP HJO              HJO           SEK                 251222            40,00
251219    NORMAL SKÖVDE         SKOEVDE       SEK                 251222           267,00
251220    HEM OCH HOBBY         HJO           SEK                 251222           318,00
251221    HEM OCH HOBBY         HJO           SEK                 251222           283,00
251222    ICA SUPERMARKET HJO   HJO           SEK                 251223           107,91
251222    HEM OCH HOBBY         HJO           SEK                 251223           333,00
251225    ICA SUPERMARKET HJO   HJO           SEK                 251229           788,53
251226    ICA SUPERMARKET HJO   HJO           SEK                 251229           427,61
251226    HIOGOTTEN AB          HJO           SEK                 251229            51,00
251226    HEM OCH HOBBY         HJO           SEK                 251229            34,37
251228    LAGER 157 SKOVD       SKOVDE        SEK                 251229           380,00
251228    ICA NARA NORRMALM     SKOEVDE       SEK                 251229            92,80
251228    KAPPAHL SKOEVDE ELINS SKOEVDE       SEK                 251229           299,30
251229    COOP HJO              HJO           SEK                 251230            53,45
251229    MOLLTORPS PIZZERIA    MOLLTORP      SEK                 251230           125,00
TOTALT DETTA KORT                                                                8875,81
KORT NR **** **** **** 7203   ROBIN FRÖJD
251129    MASSRESTAURANGE       ALVSJO        SEK                 251201           370,00
251129    NYX*TOALETT           STOCKHOLM     SEK                 251202            10,00
251201    BRODERNA BRANDT PERSON UDDEVALLA    SEK                 251202           614,00
251205    HIOGOTTEN AB          HJO           SEK                 251208           189,59
251207    NETFLIX.COM           AMSTERDAM     SEK                 251208           149,00
251212    ICA SUPERMARKET HJO   HJO           SEK                 251212           305,77
251212    HEM OCH HOBBY         HJO           SEK                 251216           262,00
251216    HEM OCH HOBBY         HJO           SEK                 251216            82,00
251219    HIOGOTTEN AB          HJO           SEK                 251222           235,85
251227    MACKEN I HJO AB       HJO           SEK                 251229           134,00
251229    MACKEN I HJO AB       HJO           SEK                 251230            81,00
TOTALT DETTA KORT                                                                2433,21
251231    Kostnad pappersfaktura                                                    35,00
          SKULD PER 251231                                                      11344,02

SEB Kort Bank AB, 106 40 Stockholm. Telefon 08-14 68 55. Bankgiro 595-4300. www.saseurobonusmastercard.se

Sida
2/2

KONTOUTDRAG december 2025
SAS EuroBonus MC Premium

Kontonummer: 403538411614789

Om inbetalning skett efter sista vardagen i förra månaden, men inte finns registrerad på ditt kontoutdrag, kan summan minskas med detta belopp.

Vid inbetalning på annat sätt än via inbetalningskort/autogiro ange OCR Nummer : 403538411614789

Köpgräns   Kvar att utnyttja per     Uttagen betalningsfri månad    Vill du betala hela månadens    Vill du debitera är det lägsta  Betalning oss tillhanda
           2025-12-31                                                skuld ska du betala              beloppet att betala             senast
20.000,00  8.655,98                  0,00                            11.344,02                        345,00                           2026-01-30

SEB Kort Bank AB, 106 40 Stockholm. Telefon 08-14 68 55. Bankgiro 595-4300. www.saseurobonusmastercard.se
"""


def test_detection():
    assert looks_like_seb_kort(SAMPLE_TEXT)
    assert not looks_like_seb_kort("SAS Amex Premium Faktura")


def test_parse_date_yymmdd():
    assert _parse_date_yymmdd("251201") == date(2025, 12, 1)
    assert _parse_date_yymmdd("260130") == date(2026, 1, 30)
    assert _parse_date_yymmdd("bad123") is None


def test_parse_amount_seb():
    assert _parse_amount("6032,91") == Decimal("6032.91")
    assert _parse_amount("11.344,02") == Decimal("11344.02")
    assert _parse_amount("-6032,91") == Decimal("-6032.91")


def test_header_fields():
    s = parse_seb_kort(SAMPLE_TEXT)
    assert s.issuer == "seb_kort"
    assert s.total_amount == Decimal("11344.02")
    assert s.minimum_amount == Decimal("345.00")
    assert s.due_date == date(2026, 1, 30)
    assert s.ocr_reference == "403538411614789"
    assert s.bankgiro == "595-4300"


def test_opening_closing_balance():
    s = parse_seb_kort(SAMPLE_TEXT)
    assert s.opening_balance == Decimal("6032.91")
    assert s.closing_balance == Decimal("11344.02")
    assert s.statement_period_start == date(2025, 12, 1)
    assert s.statement_period_end == date(2025, 12, 31)


def test_transactions_extracted_count():
    s = parse_seb_kort(SAMPLE_TEXT)
    # Evelinas kort: ~35 köp. Robin: 11 köp. Totalt ~46 + ev. kostnad
    # pappersfaktura + betalning. Kolla att det är många.
    assert len(s.transactions) > 40


def test_purchase_negative_payment_positive():
    s = parse_seb_kort(SAMPLE_TEXT)
    # Köp: COOP HJO 70.90 i källan → -70.90 hos oss (utgift på kortkonto)
    coop = next(
        (t for t in s.transactions if "COOP HJO" in t.description and abs(t.amount) == Decimal("70.90")),
        None,
    )
    assert coop is not None
    assert coop.amount == Decimal("-70.90")

    # Inbetalning: BETALT BG DATUM 251229 visas -6032,91 i källan → +6032.91
    payment = next(
        (t for t in s.transactions if "BETALT BG DATUM" in t.description),
        None,
    )
    if payment is not None:
        assert payment.amount == Decimal("6032.91")


def test_cardholder_detection():
    s = parse_seb_kort(SAMPLE_TEXT)
    holders = {t.cardholder for t in s.transactions if t.cardholder}
    assert any("EVELINA FRÖJD" in h for h in holders)
    assert any("ROBIN FRÖJD" in h for h in holders)

    # Varje transaktion (utom bankavgifter + SKULD-rader) ska ha en holder
    _no_holder_markers = ("BETALT BG", "SKULD", "pappersfaktura",
                          "valutatillägg", "årsavgift", "aviavgift")
    for t in s.transactions:
        if any(m.lower() in t.description.lower() for m in _no_holder_markers):
            continue
        assert t.cardholder is not None, f"Saknar holder på {t.description}"


def test_skipp_summary_rows():
    s = parse_seb_kort(SAMPLE_TEXT)
    for t in s.transactions:
        assert "TOTALT" not in t.description.upper()
        assert not t.description.upper().startswith("SKULD")


def test_transactions_sorted_by_date():
    s = parse_seb_kort(SAMPLE_TEXT)
    dates = [t.date for t in s.transactions]
    assert dates == sorted(dates)
