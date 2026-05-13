"""Tester för bil/pendling/försäkring-seeden (SKV-3-flödet)."""
from __future__ import annotations

import random
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from hembudget.db.base import Base
from hembudget.db.models import (
    Account, InsurancePolicy, Loan, MailItem,
)
from hembudget.game_engine.profile_generator.car_picker import (
    pick_car, _city_tier, _spend_profile_modifier, _market_value,
    _insurance_premium, BUDGET_CARS, MID_CARS, PREMIUM_CARS,
)


@pytest.fixture()
def session():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        yield s


# === Pick_car · grund ===


def test_pick_car_deterministic():
    """Samma seed → samma bil."""
    a = pick_car(
        random.Random(42),
        city_key="stockholm",
        age=35,
        spend_profile="balanserad",
        student_id=100,
    )
    b = pick_car(
        random.Random(42),
        city_key="stockholm",
        age=35,
        spend_profile="balanserad",
        student_id=100,
    )
    assert a == b


def test_pick_car_small_town_higher_chance():
    """Småorter har ~85 % bil-chans · över 30 körningar ska > 50 ha bil."""
    have = 0
    n = 30
    for i in range(n):
        c = pick_car(
            random.Random(i),
            city_key="hjo",  # ej i large/medium → small
            age=35,
            spend_profile="balanserad",
            student_id=i,
        )
        if c.has_car:
            have += 1
    assert have >= n // 2, f"förväntar ≥50% bil i småort, fick {have}/{n}"


def test_pick_car_sparsam_gets_cheaper_car():
    """Sparsam → BUDGET-tier · bilvärde < 200 000 i median.
    Använder småort där bil-chans är hög (85 %) så vi får data.
    """
    values = []
    for i in range(60):
        c = pick_car(
            random.Random(i),
            city_key="hjo",  # småort · hög bil-chans
            age=40,
            spend_profile="sparsam",
            student_id=i,
        )
        if c.has_car and c.market_value_sek:
            values.append(c.market_value_sek)
    assert len(values) > 5, f"för få bil-prover, fick {len(values)}"
    median = sorted(values)[len(values) // 2]
    assert median < 200_000, (
        f"sparsam ska ha < 200k median, fick {median}"
    )


def test_pick_car_extravagant_premium_cars():
    """Extravagant → premium/mid · bilvärde > 200k i median."""
    values = []
    for i in range(20):
        c = pick_car(
            random.Random(i + 1000),
            city_key="stockholm",
            age=35,
            spend_profile="extravagant",
            student_id=i,
        )
        if c.has_car and c.market_value_sek:
            values.append(c.market_value_sek)
    assert len(values) > 5
    median = sorted(values)[len(values) // 2]
    assert median > 200_000, (
        f"extravagant ska ha > 200k median, fick {median}"
    )


def test_pick_car_no_car_gets_public_transport():
    """Utan bil + storstad → kollektivt-kort."""
    found_public = False
    for i in range(40):
        c = pick_car(
            random.Random(i),
            city_key="stockholm",
            age=25,
            spend_profile="sparsam",
            student_id=i,
        )
        if not c.has_car and c.commute_transport == "public":
            assert c.monthly_public_transport > 0
            found_public = True
            break
    assert found_public, "minst en utan-bil-Stockholm ska få månadskort"


def test_pick_car_el_fuel_higher_electric_cost():
    """El-bil → monthly_electric_extra > 0, monthly_fuel_cost = 0."""
    seen_ev = False
    for i in range(50):
        c = pick_car(
            random.Random(i),
            city_key="stockholm",
            age=35,
            spend_profile="extravagant",
            student_id=i,
        )
        if c.has_car and c.fuel_type == "el":
            assert c.monthly_electric_extra > 0
            assert c.monthly_fuel_cost == 0
            seen_ev = True
            break
    assert seen_ev, "borde sett minst en el-bil bland 50 försök"


def test_pick_car_financing_thresholds():
    """< 80 000 kr → cash · 80-280k → loan eller cash · > 280k → leasing eller loan."""
    cash_count = loan_count = leasing_count = 0
    for i in range(60):
        c = pick_car(
            random.Random(i + 5000),
            city_key="stockholm",
            age=40,
            spend_profile="extravagant",
            student_id=i,
        )
        if not c.has_car:
            continue
        if c.financing == "cash":
            cash_count += 1
        elif c.financing == "loan":
            loan_count += 1
        elif c.financing == "leasing":
            leasing_count += 1
    # Extravagant + Stockholm → bilar > 280k vanliga → mest leasing/loan
    assert leasing_count + loan_count >= cash_count, (
        "extravagant ska oftare ha leasing/lån än kontant"
    )


# === Helpers ===


def test_city_tier_classification():
    assert _city_tier("stockholm") == "large"
    assert _city_tier("uppsala") == "medium"
    assert _city_tier("hjo") == "small"


def test_spend_profile_modifier():
    s = _spend_profile_modifier("sparsam")
    assert s["car_chance_delta"] < 0
    assert s["tier_bias"] == "budget"
    e = _spend_profile_modifier("extravagant")
    assert e["car_chance_delta"] > 0
    assert e["tier_bias"] == "premium"


def test_market_value_depreciation():
    """Linjär depreciation · 5 år gammal bil = ~50 % av nybilspris."""
    new_price = BUDGET_CARS[0]
    val_3y = _market_value(new_price, 3)
    val_8y = _market_value(new_price, 8)
    assert val_3y > val_8y
    assert val_8y >= int(new_price.base_price_new * 0.30)  # floor


def test_insurance_premium_scales_with_value():
    """Dyrare bil → dyrare premie."""
    cheap = _insurance_premium(80_000, 5, 35)
    expensive = _insurance_premium(450_000, 5, 35)
    assert expensive > cheap


def test_insurance_premium_young_driver_surcharge():
    """Förare under 25 → +100 kr."""
    young = _insurance_premium(150_000, 5, 22)
    older = _insurance_premium(150_000, 5, 30)
    assert young > older


# === seed_car_for_scope ===


def test_seed_car_for_scope_creates_insurance_policy(
    session, monkeypatch,
):
    """seed_car_for_scope ska skapa InsurancePolicy(bilforsakring)
    om StudentProfile har has_car=True."""
    # Mocka master_session att returnera en fake StudentProfile
    fake_profile_data = {
        "has_car": True,
        "car_brand": "Volvo",
        "car_model": "V60",
        "car_year": 2020,
        "car_license_plate": "ABC 123",
        "car_fuel_type": "bensin",
        "car_market_value_sek": 250_000,
        "car_insurance_provider": "Folksam",
        "car_insurance_premium_monthly": 650,
        "car_financing": "cash",
        "car_loan_principal": 0,
        "car_loan_monthly_payment": 0,
        "car_leasing_monthly": 0,
    }

    class FakeProf:
        def __init__(self, data):
            for k, v in data.items():
                setattr(self, k, v)

    class FakeQuery:
        def __init__(self, prof):
            self._prof = prof
        def filter(self, *a, **k):
            return self
        def first(self):
            return self._prof

    class FakeSession:
        def __init__(self, prof):
            self._prof = prof
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return None
        def query(self, *a, **k):
            return FakeQuery(self._prof)

    def fake_master_session():
        return FakeSession(FakeProf(fake_profile_data))

    monkeypatch.setattr(
        "hembudget.school.engines.master_session",
        fake_master_session,
    )

    from hembudget.game_engine.monthly_engine.car_seed import (
        seed_car_for_scope,
    )
    result = seed_car_for_scope(
        session, student_id=100, today_game=date(2026, 1, 1),
    )
    assert result["insurance"] is True
    assert result["welcome_mail"] is True

    pol = session.query(InsurancePolicy).filter(
        InsurancePolicy.kind == "bilforsakring",
    ).first()
    assert pol is not None
    assert pol.provider == "Folksam"
    assert pol.premium_monthly == Decimal("650")

    mail = session.query(MailItem).filter(
        MailItem.subject.like("Välkommen som kund%"),
    ).first()
    assert mail is not None


def test_seed_car_for_scope_creates_loan_when_financed(
    session, monkeypatch,
):
    """När financing='loan' skapas Loan-rad."""
    fake_data = {
        "has_car": True,
        "car_brand": "BMW",
        "car_model": "3-serie",
        "car_year": 2023,
        "car_license_plate": "XYZ 987",
        "car_fuel_type": "bensin",
        "car_market_value_sek": 450_000,
        "car_insurance_provider": "If",
        "car_insurance_premium_monthly": 950,
        "car_financing": "loan",
        "car_loan_principal": 380_000,
        "car_loan_monthly_payment": 7_350,
        "car_leasing_monthly": 0,
    }

    class FakeProf:
        def __init__(self, data):
            for k, v in data.items():
                setattr(self, k, v)

    class FakeQuery:
        def __init__(self, prof):
            self._prof = prof
        def filter(self, *a, **k):
            return self
        def first(self):
            return self._prof

    class FakeSession:
        def __init__(self, prof):
            self._prof = prof
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return None
        def query(self, *a, **k):
            return FakeQuery(self._prof)

    monkeypatch.setattr(
        "hembudget.school.engines.master_session",
        lambda: FakeSession(FakeProf(fake_data)),
    )
    from hembudget.game_engine.monthly_engine.car_seed import (
        seed_car_for_scope,
    )
    result = seed_car_for_scope(
        session, student_id=200, today_game=date(2026, 1, 1),
    )
    assert result["loan"] is True
    loan = session.query(Loan).filter(
        Loan.name.like("Billån%"),
    ).first()
    assert loan is not None
    assert loan.principal_amount == Decimal("380000")


def test_seed_car_for_scope_idempotent(session, monkeypatch):
    """Andra anrop ska INTE skapa duplicate försäkring."""
    fake_data = {
        "has_car": True,
        "car_brand": "Volvo",
        "car_model": "V60",
        "car_year": 2020,
        "car_license_plate": "DEF 456",
        "car_fuel_type": "bensin",
        "car_market_value_sek": 200_000,
        "car_insurance_provider": "Trygg-Hansa",
        "car_insurance_premium_monthly": 600,
        "car_financing": "cash",
        "car_loan_principal": 0,
        "car_loan_monthly_payment": 0,
        "car_leasing_monthly": 0,
    }

    class FakeProf:
        def __init__(self, data):
            for k, v in data.items():
                setattr(self, k, v)

    class FakeQuery:
        def __init__(self, prof):
            self._prof = prof
        def filter(self, *a, **k):
            return self
        def first(self):
            return self._prof

    class FakeSession:
        def __init__(self, prof):
            self._prof = prof
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return None
        def query(self, *a, **k):
            return FakeQuery(self._prof)

    monkeypatch.setattr(
        "hembudget.school.engines.master_session",
        lambda: FakeSession(FakeProf(fake_data)),
    )
    from hembudget.game_engine.monthly_engine.car_seed import (
        seed_car_for_scope,
    )
    seed_car_for_scope(session, student_id=300, today_game=date(2026, 1, 1))
    seed_car_for_scope(session, student_id=300, today_game=date(2026, 2, 1))

    pol_count = session.query(InsurancePolicy).filter(
        InsurancePolicy.kind == "bilforsakring",
    ).count()
    assert pol_count == 1


def test_seed_car_for_scope_no_car_returns_skipped(session, monkeypatch):
    fake_data = {"has_car": False}

    class FakeProf:
        def __init__(self, data):
            for k, v in data.items():
                setattr(self, k, v)

    class FakeQuery:
        def __init__(self, prof):
            self._prof = prof
        def filter(self, *a, **k):
            return self
        def first(self):
            return self._prof

    class FakeSession:
        def __init__(self, prof):
            self._prof = prof
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return None
        def query(self, *a, **k):
            return FakeQuery(self._prof)

    monkeypatch.setattr(
        "hembudget.school.engines.master_session",
        lambda: FakeSession(FakeProf(fake_data)),
    )
    from hembudget.game_engine.monthly_engine.car_seed import (
        seed_car_for_scope,
    )
    result = seed_car_for_scope(
        session, student_id=400, today_game=date(2026, 1, 1),
    )
    assert result == {"skipped": "no_car"}
