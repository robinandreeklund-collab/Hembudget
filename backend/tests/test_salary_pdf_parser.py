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


def test_attach_salary_pdf_to_existing_upcoming(tmp_path, monkeypatch):
    """POST /upcoming/{id}/attach-salary-pdf ska uppdatera en befintlig
    income-rad med source_image_path + metadata från PDF:en — utan att
    skapa en ny rad."""
    from decimal import Decimal
    from datetime import date
    import pytest
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    monkeypatch.setenv("HEMBUDGET_DEMO_MODE", "1")
    monkeypatch.setenv("HEMBUDGET_DATA_DIR", str(tmp_path))

    from hembudget.db.models import Account, Base, UpcomingTransaction
    engine = create_engine(
        "sqlite:///:memory:", future=True,
        connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SL = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    from hembudget import demo as demo_mod
    monkeypatch.setattr(demo_mod, "bootstrap_if_empty", lambda: {"skipped": True})
    from hembudget.api import deps as api_deps
    from hembudget.main import build_app
    app = build_app()

    def _db():
        s = SL()
        try:
            yield s; s.commit()
        except Exception:
            s.rollback(); raise
        finally:
            s.close()

    app.dependency_overrides[api_deps.db] = _db
    client = TestClient(app)
    with client:
        # Skapa en befintlig income-rad utan källfil
        with SL() as s:
            acc = Account(name="Mitt konto", bank="nordea", type="checking")
            s.add(acc); s.flush()
            u = UpcomingTransaction(
                kind="income", name="Inkab (manuellt tillagd)",
                amount=Decimal("6197"),
                expected_date=date(2026, 1, 23),
                owner="Robin",
                source="manual",
            )
            s.add(u); s.commit()
            up_id = u.id

        # Ladda upp INKAB-PDF:en och koppla den till ovanstående rad
        pdf = PDF_DIR / "20260123.pdf"
        if not pdf.exists():
            pytest.skip("INKAB test-PDF saknas")
        with pdf.open("rb") as fh:
            r = client.post(
                f"/upcoming/{up_id}/attach-salary-pdf",
                files={"file": (pdf.name, fh, "application/pdf")},
            )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["id"] == up_id
        assert body["source_image_path"] is not None
        assert body["source"] == "salary_pdf"

        # Verifiera att INGEN ny rad skapades
        with SL() as s:
            count = s.query(UpcomingTransaction).filter_by(
                kind="income",
            ).count()
            assert count == 1

        # Verifiera att metadata är lagrad i notes
        import json as _json
        meta = _json.loads(body["notes"])
        assert meta["detected_format"] == "inkab"
        assert meta["gross"] == 6764.60
        assert meta["tax"] == 568.00
        assert meta["vacation_days_paid"] == 25
