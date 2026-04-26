"""Regression: lönespec-import skapar TaxEvent + UpcomingTransaction
med skatte-meta i .notes så /tax/salary-summary visar månadens skatt.

Bakgrund: tidigare berikade _import_lonespec bara den befintliga
löne-tx:en med kategori. Skattefördelningen från lönespecen (kommunal,
statlig, grundavdrag) skrevs aldrig till någon strukturerad plats, så
/tax-vyns 'Lön & skatt'-kort var alltid tom efter batch-import.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def session():
    from hembudget.db.models import Base, Category

    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    s = S()
    s.add(Category(name="Lön", parent_id=None))
    s.commit()
    try:
        yield s
    finally:
        s.close()


def _make_parsed_lonespec(net: Decimal, pay_date: date):
    """Bygg ett minimalt EkonomilabbetParseResult för en lönespec."""
    from hembudget.parsers.base import RawTransaction
    from hembudget.parsers.ekonomilabbet import EkonomilabbetParseResult
    return EkonomilabbetParseResult(
        kind="lonespec",
        title=f"Lönespec {pay_date.isoformat()}",
        period=pay_date.strftime("%Y-%m"),
        transactions=[
            RawTransaction(
                date=pay_date, description="LÖN ELAJO", amount=net,
                row_index=0,
            ),
        ],
        total_amount=net,
    )


def _make_artifact(meta: dict, pdf_bytes: bytes = b"%PDF-1.4 stub"):
    """Bygg ett mock-objekt som ser ut som BatchArtifact för testet."""
    class MockArtifact:
        def __init__(self):
            self.id = 999
            self.kind = "lonespec"
            self.filename = "lonespec_2026-04.pdf"
            self.pdf_bytes = pdf_bytes
            self.meta = meta
            self.imported_at = None
    return MockArtifact()


def test_lonespec_creates_tax_event(session, tmp_path, monkeypatch):
    from hembudget.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)

    from hembudget.db.models import (
        Account, TaxEvent, Transaction, UpcomingTransaction,
    )
    from hembudget.teacher.batch import _import_lonespec

    pay_date = date(2026, 4, 25)
    net_amount = Decimal("24200")
    artifact = _make_artifact({
        "employer": "Elajo Eltjänst",
        "profession": "Elektriker",
        "gross": 33000.0,
        "grundavdrag": 1700.0,
        "kommunal_tax": 7500.0,
        "statlig_tax": 1300.0,
        "net": 24200.0,
        "pay_date": pay_date.isoformat(),
    })
    parsed = _make_parsed_lonespec(net_amount, pay_date)

    # Pre-existerande lönekonto + lön-tx att berika
    acc = Account(name="Lönekonto", bank="ekonomilabbet", type="checking")
    session.add(acc); session.flush()
    session.add(Transaction(
        account_id=acc.id, date=pay_date, amount=net_amount,
        currency="SEK", raw_description="LÖN ELAJO", hash="h_salary",
    ))
    session.commit()

    stats = {
        "imported_tx": 0, "skipped_tx": 0, "accounts_touched": [],
    }
    _import_lonespec(session, parsed, stats, artifact)
    session.commit()

    # 1. UpcomingTransaction skapad med skatt-info i .notes
    ups = (
        session.query(UpcomingTransaction)
        .filter(UpcomingTransaction.source == "salary_pdf")
        .all()
    )
    assert len(ups) == 1
    up = ups[0]
    assert up.source_image_path is not None
    assert up.notes is not None
    import json as _json
    notes = _json.loads(up.notes)
    assert notes["gross"] == 33000.0
    assert notes["tax"] == 8800.0  # 7500 + 1300
    assert notes["kommunal_tax"] == 7500.0
    assert notes["statlig_tax"] == 1300.0

    # 2. TaxEvent type=salary_tax skapad för månaden
    tax_events = (
        session.query(TaxEvent)
        .filter(TaxEvent.type == "salary_tax")
        .all()
    )
    assert len(tax_events) == 1
    ev = tax_events[0]
    assert ev.amount == Decimal("8800")
    assert ev.date == pay_date
    assert ev.meta["kommunal"] == 7500.0
    assert ev.meta["statlig"] == 1300.0


def test_lonespec_idempotent_on_re_import(session, tmp_path, monkeypatch):
    """Re-import av samma lönespec skapar inte fler UpcomingTransaction
    eller TaxEvent."""
    from hembudget.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)

    from hembudget.db.models import (
        Account, TaxEvent, Transaction, UpcomingTransaction,
    )
    from hembudget.teacher.batch import _import_lonespec

    pay_date = date(2026, 4, 25)
    net_amount = Decimal("24200")
    artifact = _make_artifact({
        "employer": "Elajo Eltjänst", "profession": "Elektriker",
        "gross": 33000.0, "grundavdrag": 1700.0,
        "kommunal_tax": 7500.0, "statlig_tax": 1300.0,
        "net": 24200.0,
    })
    parsed = _make_parsed_lonespec(net_amount, pay_date)

    acc = Account(name="Lönekonto", bank="ekonomilabbet", type="checking")
    session.add(acc); session.flush()
    session.add(Transaction(
        account_id=acc.id, date=pay_date, amount=net_amount,
        currency="SEK", raw_description="LÖN ELAJO", hash="h_salary",
    ))
    session.commit()

    for _ in range(3):
        stats = {
            "imported_tx": 0, "skipped_tx": 0, "accounts_touched": [],
        }
        _import_lonespec(session, parsed, stats, artifact)
        session.commit()

    assert (
        session.query(UpcomingTransaction)
        .filter(UpcomingTransaction.source == "salary_pdf")
        .count()
    ) == 1
    assert (
        session.query(TaxEvent)
        .filter(TaxEvent.type == "salary_tax")
        .count()
    ) == 1
