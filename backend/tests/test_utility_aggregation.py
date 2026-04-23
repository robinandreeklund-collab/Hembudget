"""Tester för _readings_summary: kWh ska inte dubbelräknas när
'energy' (Telinet) och 'grid' (Hjo Elnät) fakturerar samma månad.
Kostnaden ska däremot summeras eftersom det är olika delar av elnotan.
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
    from hembudget.db.models import Base
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as s:
        yield s


def _add_reading(session, *, supplier, role, period_start, kwh, cost):
    from hembudget.db.models import UtilityReading
    from datetime import date as date_cls
    y, m, _ = period_start.year, period_start.month, period_start.day
    from calendar import monthrange
    end_day = monthrange(y, m)[1]
    session.add(UtilityReading(
        supplier=supplier,
        meter_type="electricity",
        meter_role=role,
        period_start=period_start,
        period_end=date_cls(y, m, end_day),
        consumption=Decimal(str(kwh)),
        consumption_unit="kWh",
        cost_kr=Decimal(str(cost)),
        source="test",
    ))


def test_aggregation_does_not_double_count_kwh(session):
    """Telinet + Hjo för feb-26 → kWh tas från Telinet (energy), inte
    summerat. Kostnaden summeras (3665 energi + 1723 nät = 5388)."""
    from hembudget.api.utility import _readings_summary

    _add_reading(
        session, supplier="telinet", role="energy",
        period_start=date(2026, 2, 1), kwh=2285, cost=3665,
    )
    _add_reading(
        session, supplier="hjo_energi", role="grid",
        period_start=date(2026, 2, 1), kwh=2285, cost=1723.38,
    )
    session.commit()

    summary = _readings_summary(session, 2026)
    el = summary["electricity"]
    feb = el["2026-02"]
    # kWh ska INTE vara 4570 (dubbelräknat) — ska vara 2285
    assert feb["consumption"] == 2285.0
    # Kostnaden är summa av båda delarna
    assert abs(feb["cost_kr"] - 5388.38) < 0.01
    # Nedbrytning per roll exponerad för UI
    assert feb["cost_by_role"]["energy"] == 3665.0
    assert abs(feb["cost_by_role"]["grid"] - 1723.38) < 0.01
    # Båda suppliers listas
    assert set(feb["suppliers"]) == {"telinet", "hjo_energi"}
    # Rollerna också listas
    assert set(feb["roles"]) == {"energy", "grid"}


def test_aggregation_falls_back_to_grid_when_no_energy(session):
    """Om bara Hjo Energi har en reading för månaden (Telinet-fakturan
    inte kommit än), använd 'grid'-kWh som förbrukning."""
    from hembudget.api.utility import _readings_summary

    _add_reading(
        session, supplier="hjo_energi", role="grid",
        period_start=date(2026, 3, 1), kwh=1531, cost=1723.38,
    )
    session.commit()

    summary = _readings_summary(session, 2026)
    mar = summary["electricity"]["2026-03"]
    assert mar["consumption"] == 1531.0
    assert abs(mar["cost_kr"] - 1723.38) < 0.01
    assert set(mar["roles"]) == {"grid"}


def test_aggregation_handles_legacy_total_role(session):
    """Äldre readings utan meter_role satt (default='total') ska fortfarande
    aggregeras korrekt — fallback-prioriteten är energy → grid → total."""
    from hembudget.api.utility import _readings_summary

    _add_reading(
        session, supplier="manuell", role="total",
        period_start=date(2026, 1, 1), kwh=2000, cost=4000,
    )
    session.commit()

    summary = _readings_summary(session, 2026)
    jan = summary["electricity"]["2026-01"]
    assert jan["consumption"] == 2000.0
    assert jan["cost_kr"] == 4000.0


def test_aggregation_sums_cost_across_all_roles(session):
    """Sanity: total kostnad = sum oavsett antal roller."""
    from hembudget.api.utility import _readings_summary

    _add_reading(
        session, supplier="telinet", role="energy",
        period_start=date(2026, 4, 1), kwh=1800, cost=3000,
    )
    _add_reading(
        session, supplier="hjo_energi", role="grid",
        period_start=date(2026, 4, 1), kwh=1800, cost=1500,
    )
    session.commit()

    summary = _readings_summary(session, 2026)
    apr = summary["electricity"]["2026-04"]
    assert apr["cost_kr"] == 4500.0
    assert apr["consumption"] == 1800.0  # ej 3600
