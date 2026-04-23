"""End-to-end-tester mot riktiga energi-PDF:er i data_for_test/el/.

Skippas med pytest.mark.skipif om PDF:erna inte finns (t.ex. i CI utan
hela repo:t). För lokal körning validerar de att parsern extraherar
supplier, period, kWh och kostnad korrekt från båda exempelfakturorna.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from hembudget.parsers.utility_pdfs import (
    HistoryPoint,
    parse_utility_pdf,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
EL_DIR = REPO_ROOT / "data_for_test" / "el"

TELINET_PDF = EL_DIR / "202604231449701.pdf"
HJO_PDF = EL_DIR / "efa_1776848739460.pdf"

has_telinet = TELINET_PDF.exists()
has_hjo = HJO_PDF.exists()


@pytest.mark.skipif(not has_telinet, reason="Telinet-PDF saknas")
def test_parse_telinet_invoice():
    res = parse_utility_pdf(TELINET_PDF.read_bytes())
    assert res.supplier == "telinet"
    assert res.meter_type == "electricity"
    # "Faktura 1 februari - 28 februari 2026"
    assert res.period_start == date(2026, 2, 1)
    assert res.period_end == date(2026, 2, 28)
    # "Under perioden har du förbrukat: 2 285 kWh"
    assert res.consumption == Decimal("2285")
    assert res.consumption_unit == "kWh"
    # "Totalbelopp att betala: 3 665 kr"
    assert res.cost_kr == Decimal("3665")
    assert res.parse_errors == []


@pytest.mark.skipif(not has_hjo, reason="Hjo Energi-PDF saknas")
def test_parse_hjo_energi_invoice():
    res = parse_utility_pdf(HJO_PDF.read_bytes())
    # Hjo Energi är kombinerad el + vatten + internet-faktura. Vi
    # extraherar el-delen primärt eftersom det är den meter_type
    # användaren främst spårar.
    assert res.supplier == "hjo_energi"
    assert res.meter_type == "electricity"
    # "Elöverföring (avläst) 260301-260331"
    assert res.period_start == date(2026, 3, 1)
    assert res.period_end == date(2026, 3, 31)
    # "1 531 kWh" på Elöverföring-raden
    assert res.consumption == Decimal("1531")
    assert res.consumption_unit == "kWh"
    # El-delsumma 1 723,38 (inte totalbeloppet 3 387 som inkluderar
    # vatten + internet)
    assert res.cost_kr == Decimal("1723.38")
    assert res.parse_errors == []


@pytest.mark.skipif(not has_hjo, reason="Hjo Energi-PDF saknas")
def test_parse_hjo_energi_history_has_13_months():
    """Hjo Energi-fakturan innehåller en 'Förbrukningsstatistik'-tabell
    med kWh per månad för 12+ senaste månader — vi extraherar allt."""
    res = parse_utility_pdf(HJO_PDF.read_bytes())
    assert len(res.history) == 13
    # Första månaden ska vara mars 2025
    first = res.history[0]
    assert first.year == 2025
    assert first.month == 3
    assert first.kwh == Decimal("1587")
    # Sista månaden ska matcha fakturans egen period
    last = res.history[-1]
    assert last.year == 2026
    assert last.month == 3
    assert last.kwh == Decimal("1531")
    # Feb-26 från historiken ska matcha Telinet-fakturans värde för
    # samma månad (2 285 kWh) — sanity check på data-konsistens.
    feb26 = next(h for h in res.history if h.year == 2026 and h.month == 2)
    assert feb26.kwh == Decimal("2285")


@pytest.mark.skipif(not has_telinet, reason="Telinet-PDF saknas")
def test_telinet_is_not_misdetected_as_hjo_energi():
    """Telinet-fakturan säger 'Nätleverantör: Hjo Elnät AB' i anläggnings-
    uppgifterna. Parsern får INTE klassa den som hjo_energi — då skulle
    vi köra fel parser och få noll output."""
    res = parse_utility_pdf(TELINET_PDF.read_bytes())
    assert res.supplier == "telinet"
    assert res.supplier != "hjo_energi"


def test_history_point_dataclass():
    hp = HistoryPoint(year=2026, month=1, kwh=Decimal("1234"))
    assert hp.year == 2026
    assert hp.month == 1
    assert hp.kwh == Decimal("1234")
