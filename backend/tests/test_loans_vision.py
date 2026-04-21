"""Test av hjälpfunktioner för vision-baserad låneparsning."""
from hembudget.api.loans import _derive_interest_rate


def test_derive_rate_from_interest_only_schedule():
    """Nordea-exemplet: balans 800 000, ränta ca 1 900 kr/mån → ~2.85 %."""
    schedule = [
        {"due_date": "2026-04-27", "total_amount": 1902, "amortization_amount": 0},
        {"due_date": "2026-05-27", "total_amount": 1841, "amortization_amount": 0},
        {"due_date": "2026-06-27", "total_amount": 1902, "amortization_amount": 0},
        {"due_date": "2026-07-27", "total_amount": 1841, "amortization_amount": 0},
        {"due_date": "2026-08-27", "total_amount": 1902, "amortization_amount": 0},
    ]
    rate = _derive_interest_rate(schedule, current_balance=800000)
    assert rate is not None
    # Förväntar oss ~0.028 (2.8 %)
    assert 0.027 < rate < 0.029


def test_derive_rate_with_amortization():
    """Om amortering syns ska vi bara räkna räntedelen."""
    schedule = [
        {"due_date": "2026-04-01", "total_amount": 5000, "amortization_amount": 3000},
        {"due_date": "2026-05-01", "total_amount": 5000, "amortization_amount": 3000},
    ]
    # ränta = 2000 kr/mån, balance 600k → 2000*12/600000 = 4 %
    rate = _derive_interest_rate(schedule, current_balance=600000)
    assert abs(rate - 0.04) < 0.001


def test_derive_rate_none_for_empty_schedule():
    assert _derive_interest_rate([], 500000) is None


def test_derive_rate_none_for_zero_balance():
    schedule = [{"due_date": "2026-04-01", "total_amount": 1000}]
    assert _derive_interest_rate(schedule, current_balance=0) is None
