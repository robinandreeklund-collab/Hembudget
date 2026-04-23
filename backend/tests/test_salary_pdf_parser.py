"""End-to-end test för PDF-löneparsern.

Verifierar att alla fyra test-PDF:er i data_for_test/loner parsas
korrekt (detected_format + netto + datum + skatt). Används som
smoke-test för parsern när nya formatet läggs till.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

PDF_DIR = Path(__file__).parent.parent.parent / "data_for_test" / "loner"


@pytest.mark.skipif(
    not PDF_DIR.exists() or not any(PDF_DIR.iterdir()),
    reason="Test-PDFerna saknas (data_for_test/loner/)",
)
def test_parse_inkab_pdf():
    from hembudget.parsers.salary_pdfs import parse_salary_pdf

    pdf = PDF_DIR / "20260123.pdf"
    assert pdf.exists()
    res = parse_salary_pdf(pdf.read_bytes())
    assert res.detected_format == "inkab"
    assert res.employer == "INKAB"
    assert res.paid_out_date == date(2026, 1, 23)
    assert res.gross == Decimal("6764.60")
    assert res.tax == Decimal("568.00")
    assert res.net == Decimal("6197.00")
    assert res.tax_table == "34"
    assert res.vacation_days_paid == 25
    assert res.vacation_days_unpaid == 0


def test_parse_vp_pdf_has_extra_tax():
    """VP-formatets signatur: 'Extra skatt'-rad som extraheras separat."""
    from hembudget.parsers.salary_pdfs import parse_salary_pdf

    pdf = PDF_DIR / "Lönebesked_2026-01-23.pdf"
    if not pdf.exists():
        pytest.skip("VP test-PDF saknas")
    res = parse_salary_pdf(pdf.read_bytes())
    assert res.detected_format == "vp"
    assert res.employer == "Vättaporten AB"
    assert res.employee == "Robin André"
    assert res.paid_out_date == date(2026, 1, 23)
    assert res.gross == Decimal("32257.00")
    assert res.tax == Decimal("9185.00")
    assert res.extra_tax == Decimal("2000.00")
    assert res.net == Decimal("23072.00")
    assert res.benefit == Decimal("2811.00")
    assert res.tax_table == "33"
    assert res.one_time_tax_percent == 26.0


def test_parse_fk_barnbidrag():
    from hembudget.parsers.salary_pdfs import parse_salary_pdf

    pdf = PDF_DIR / "utbetalning_2026-01-20.pdf"
    if not pdf.exists():
        pytest.skip("FK barnbidrag test-PDF saknas")
    res = parse_salary_pdf(pdf.read_bytes())
    assert res.detected_format == "fk_barnbidrag"
    assert res.employer == "Försäkringskassan"
    assert res.paid_out_date == date(2026, 1, 20)
    assert res.net == Decimal("2240")
    # Barnbidrag är skattefritt — tax=0 + gross=net
    assert res.tax == Decimal("0")
    assert res.gross == res.net


def test_parse_fk_foraldrapenning_uses_correct_date():
    """FK-föräldrapenning-PDF:en har 'Fastställd 2024-10-30' som form-
    version. Parsern ska plocka utbetalningsdagen, inte form-datumet."""
    from hembudget.parsers.salary_pdfs import parse_salary_pdf

    pdf = PDF_DIR / "utbetalning_2026-03-25.pdf"
    if not pdf.exists():
        pytest.skip("FK föräldrapenning test-PDF saknas")
    res = parse_salary_pdf(pdf.read_bytes())
    assert res.detected_format == "fk_foraldrapenning"
    assert res.paid_out_date == date(2026, 3, 25)
    assert res.net == Decimal("1719")
    assert res.gross == Decimal("2490")
    assert res.tax == Decimal("771")


def test_unknown_format_returns_error():
    from hembudget.parsers.salary_pdfs import parse_salary_pdf

    # Minimal fake PDF med text som inte matchar något format
    import pypdfium2 as pdfium
    # pypdfium2 kan inte skapa PDF:er — skapa bara en bytes-stream som
    # är OGILTIG och verifiera att parsern inte kraschar hårt.
    res = parse_salary_pdf(b"not a real pdf")
    assert res.detected_format == "unknown"
    assert len(res.parse_errors) >= 1
