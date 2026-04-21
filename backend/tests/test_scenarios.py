from decimal import Decimal

from hembudget.scenarios.engine import (
    MortgageParams,
    MoveParams,
    SavingsGoalParams,
    ScenarioEngine,
)


def test_mortgage_basic_ltv_80():
    eng = ScenarioEngine()
    res = eng.mortgage(
        MortgageParams(
            price=Decimal("5000000"),
            cash_down=Decimal("1000000"),  # 20 % kontant = LTV 80 %
            interest_rate=0.04,
            household_income_yearly=Decimal("800000"),
            monthly_fee=Decimal("4500"),
        )
    )
    assert res.loan_amount == Decimal("4000000.00")
    assert 0.79 < res.ltv < 0.81
    # LTV 80 % → 2 % amortering; skuldkvot 5x → +1 %
    assert abs(res.amortization_rate_annual - 0.03) < 1e-9
    # 4 000 000 × 3 %/12 = 10 000 kr/mån
    assert res.monthly_amortization == Decimal("10000.00")
    # Ränta brutto: 4 000 000 × 4%/12 = 13 333.33
    assert abs(float(res.monthly_interest_gross) - 13333.33) < 0.01
    assert "Ränteavdrag" in " ".join(res.assumptions)


def test_mortgage_no_amortization_under_50_ltv():
    res = ScenarioEngine().mortgage(
        MortgageParams(
            price=Decimal("4000000"),
            cash_down=Decimal("2200000"),   # LTV 45 %
            interest_rate=0.04,
            household_income_yearly=Decimal("900000"),
        )
    )
    assert res.amortization_rate_annual == 0.0
    assert res.monthly_amortization == Decimal("0.00")


def test_savings_goal_reaches_target():
    res = ScenarioEngine().savings_goal(
        SavingsGoalParams(
            target_amount=Decimal("500000"),
            horizon_months=120,
            monthly_contribution=Decimal("3000"),
            expected_annual_return=0.07,
        )
    )
    # Ska vara nära eller över 500k
    assert res.projected_balance > Decimal("490000")
    assert res.shortfall >= Decimal("0")


def test_savings_goal_shortfall():
    res = ScenarioEngine().savings_goal(
        SavingsGoalParams(
            target_amount=Decimal("1000000"),
            horizon_months=60,
            monthly_contribution=Decimal("5000"),
            expected_annual_return=0.05,
        )
    )
    assert res.shortfall > Decimal("0")
    assert res.required_monthly_to_hit > Decimal("5000")


def test_move_breakeven():
    res = ScenarioEngine().move(
        MoveParams(
            current_monthly_cost=Decimal("20000"),
            new_monthly_cost=Decimal("15000"),
            moving_cost=Decimal("30000"),
            horizon_months=60,
        )
    )
    assert res.monthly_delta == Decimal("-5000.00")
    assert res.breakeven_months == 6.0
    # 60 × -5000 + 30000 = -270 000
    assert res.total_over_horizon == Decimal("-270000.00")
