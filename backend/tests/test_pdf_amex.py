"""Test av Amex PDF-fakturaparser.

Testdata är verbatim-textlayouten från en verklig SAS Amex Premium
Faktura (Sida 1 + Sida 2). Verifierar att alla nyckelfält extraheras."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from hembudget.parsers.pdf_statements.amex import (
    looks_like_amex,
    parse_amex,
    _parse_amount,
    _parse_date_amex,
    _split_merchant_city,
)


SAMPLE_TEXT = """\
SAS Amex Premium
Faktura

Sida 1 av 3

Fakturadatum: 02.02.26
Kortnummer som slutar på: 31009
Fakturans period: 03.01.26 till 02.02.26
www.americanexpress.se

Kortmedlem
Karl Robin Ludvig Fröjd

Sammanfattning

Fakturans saldo     13.445,08      SEK

Lägsta belopp att betala     403,35      SEK

Förfallodag                 27.02.26

Kontoöversikt
                               SEK
Föregående faktura       39.683,78
Nya inbetalningar       -42.656,78
Nya köp                  16.418,08
Fakturans saldo          13.445,08

Bankgiro: 5127-5477
OCR: 37939513843100975

Kreditgräns:     150.000,00
Saldo:            13.445,08
Kvar att utnyttja: 136.554,92

SAS EuroBonus Extrapoäng
EuroBonus-nummer: 631970910
Poäng överförda den 31.01.26

4.332

Sida 2 av 3

Inbetalningar
Transaktions-Process-
datum      datum    Transaktionsuppgifter           Belopp i SEK
09.01.26  09.01.26  Betalning Mottagen, Tack        -16.400,00 CR
28.01.26  28.01.26  Betalning Mottagen, Tack        -23.283,78 CR

Summa nya inbetalningar                             -39.683,78 CR

Nya köp

Nya köp för Karl Robin Ludvig Fröjd
Transaktions-Process-
datum      datum    Transaktionsuppgifter           Belopp i SEK
06.01.26  06.01.26  Max Burgers        Luleå            412,00
06.01.26  06.01.26  Ikea Orebro 70231 Ikea              30,00
06.01.26  06.01.26  Ikea Orebro 70231 Ikea           1.053,00
06.01.26  06.01.26  Åhlens Outlet Ab   Stockholm        208,00
06.01.26  07.01.26  Eko Örebro         Örebro            74,90
06.01.26  07.01.26  St1 Hjo Falköpingsvägen Hjo         809,60
07.01.26  07.01.26  Hbomax             Stockholm        149,00
07.01.26  07.01.26  Coop Hjo           Hjo            1.094,20
13.01.26  13.01.26  Coop Hjo           Hjo              532,40
15.01.26  16.01.26  Kjell & Co 74      Skövde           219,00
18.01.26  18.01.26  Coop Hjo           Hjo              291,65
18.01.26  18.01.26  Coop Hjo           Hjo              185,95
18.01.26  19.01.26  Okq8               Hjo            1.015,01
20.01.26  20.01.26  Coop Hjo           Hjo              132,46
21.01.26  21.01.26  Amazon Prime
                    Www.Amazon.Se                        69,00
21.01.26  22.01.26  Klm                Stockholm       -495,00 CR
21.01.26  22.01.26  Klm                Stockholm       -661,00 CR
21.01.26  22.01.26  Klm                Stockholm       -495,00 CR
21.01.26  22.01.26  Klm                Stockholm       -661,00 CR
21.01.26  22.01.26  Klm                Stockholm       -661,00 CR
22.01.26  22.01.26  Strava             San Francisco     99,00
23.01.26  23.01.26  Rusta - 28 Ska.Vde Skovde        1.016,00
23.01.26  23.01.26  Willys E Handel    Goteborg         352,48
23.01.26  23.01.26  Willys E Handel    Goteborg       1.219,67
23.01.26  24.01.26  Stadium Outlet     Skövde            70,00
24.01.26  24.01.26  Amazon Prime
                    Www.Amazon.Se                        69,00
24.01.26  24.01.26  Coop Hjo           Hjo               85,14
25.01.26  25.01.26  Spotifyse          Stockholm        129,00
27.01.26  27.01.26  Coop Hjo           Hjo               72,95
30.01.26  30.01.26  Willys E Handel    Goteborg       1.058,11
30.01.26  30.01.26  Willys Skovde Stalls 19 Skovde    1.823,71
30.01.26  30.01.26  Willys Skovde Stalls 19 Skovde       36,90
02.02.26  02.02.26  Periodens Del Av Årsavgift För
                    Kontot                             135,00

Summa nya köp för Karl Robin Ludvig Fröjd         9.470,13

Nya köp för Rut Elin Evelina Fröjd Extrakort som slutar på 31017
Transaktions-Process-
datum      datum    Transaktionsuppgifter           Belopp i SEK
02.01.26  02.01.26  Coop Hjo           Hjo              640,78
02.01.26  02.01.26  Coop Hjo           Hjo              142,80
06.01.26  06.01.26  Ikea Orebro 70231 Ikea              109,00
09.01.26  09.01.26  Apple.Com/Bill     Hollyhill         39,00
11.01.26  11.01.26  Willys Skovde Stalls 19 Skovde    1.285,76
15.01.26  15.01.26  Willys E Handel    Goteborg       1.050,86
15.01.26  15.01.26  Willys E Handel    Goteborg         706,75

Summa nya köp för Rut Elin Evelina Fröjd          3.974,95

Summan av alla nya köp                           13.445,08
"""


def test_detection():
    assert looks_like_amex(SAMPLE_TEXT)
    assert not looks_like_amex("SAS EuroBonus MC Premium KONTOUTDRAG")
    assert not looks_like_amex("")


def test_parse_amount():
    assert _parse_amount("13.445,08") == Decimal("13445.08")
    assert _parse_amount("1 053,00") == Decimal("1053.00")
    assert _parse_amount("412,00") == Decimal("412.00")
    assert _parse_amount("-16.400,00") == Decimal("-16400.00")


def test_parse_date_amex():
    assert _parse_date_amex("27.02.26") == date(2026, 2, 27)
    assert _parse_date_amex("06.01.26") == date(2026, 1, 6)
    assert _parse_date_amex("bad") is None


def test_header_fields():
    s = parse_amex(SAMPLE_TEXT)
    assert s.issuer == "amex"
    assert s.total_amount == Decimal("13445.08")
    assert s.minimum_amount == Decimal("403.35")
    assert s.due_date == date(2026, 2, 27)
    assert s.bankgiro == "5127-5477"
    assert s.ocr_reference == "37939513843100975"
    assert s.card_last_digits == "1009"
    assert s.statement_period_start == date(2026, 1, 3)
    assert s.statement_period_end == date(2026, 2, 2)
    assert s.opening_balance == Decimal("39683.78")
    assert s.new_purchases_total == Decimal("16418.08")
    assert s.payments_total == Decimal("-42656.78")


def test_transactions_extracted():
    s = parse_amex(SAMPLE_TEXT)
    # Minst 20+ transaktioner (faktiskt ~40 inklusive inbetalningar)
    assert len(s.transactions) > 20


def test_purchase_is_negative():
    s = parse_amex(SAMPLE_TEXT)
    max_burgers = next(
        t for t in s.transactions if "Max Burgers" in t.description
    )
    assert max_burgers.amount == Decimal("-412.00")
    assert max_burgers.date == date(2026, 1, 6)


def test_cr_marker_is_positive():
    """'CR' = credit = pengar in på kortet (inbetalning eller retur)."""
    s = parse_amex(SAMPLE_TEXT)
    paid_first = next(
        t for t in s.transactions if "Betalning Mottagen" in t.description
    )
    # Det var -16.400,00 CR i källan — ska bli positivt (inbetalning)
    assert paid_first.amount == Decimal("16400.00")

    klm_refund = next(
        t for t in s.transactions
        if "Klm" in t.description and t.amount > 0
    )
    assert klm_refund.amount > 0


def test_cardholder_detection():
    s = parse_amex(SAMPLE_TEXT)
    holders = {t.cardholder for t in s.transactions if t.cardholder}
    # Två kortinnehavare syns
    assert any("Karl Robin" in h for h in holders)
    assert any("Rut Elin Evelina" in h for h in holders)


def test_split_merchant_city():
    m, c = _split_merchant_city("Max Burgers        Luleå")
    assert m == "Max Burgers"
    assert c == "Luleå"

    m, c = _split_merchant_city("Coop Hjo           Hjo")
    assert m == "Coop Hjo"
    assert c == "Hjo"

    # Utan stad
    m, c = _split_merchant_city("Amazon Prime Www.Amazon.Se")
    assert c is None


def test_transactions_sorted_by_date():
    s = parse_amex(SAMPLE_TEXT)
    dates = [t.date for t in s.transactions]
    assert dates == sorted(dates)
