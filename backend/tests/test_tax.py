from datetime import date
from decimal import Decimal

from hembudget.tax.isk import ISKCalculator, ISKQuarterValue, ISKYearData
from hembudget.tax.k4 import K4Calculator, Trade


def test_isk_floor_applied():
    data = ISKYearData(
        year=2026,
        opening_balance=Decimal("100000"),
        deposits=Decimal("12000"),
        quarter_values=[
            ISKQuarterValue(1, Decimal("101000")),
            ISKQuarterValue(2, Decimal("104000")),
            ISKQuarterValue(3, Decimal("108000")),
            ISKQuarterValue(4, Decimal("112000")),
        ],
        statslaneranta_30_nov=Decimal("0.001"),  # mkt lågt → golv gäller
    )
    res = ISKCalculator().compute(data)
    assert res.schablonrate == Decimal("0.012500")
    # Underlag = (100k + 12k + 101k + 104k + 108k + 112k) / 4 = 134 250
    assert res.underlag == Decimal("134250.00")
    assert res.skatt == (res.schablonintakt * Decimal("0.30")).quantize(Decimal("0.01"))


def test_isk_normal_rate():
    data = ISKYearData(
        year=2026,
        opening_balance=Decimal("100000"),
        deposits=Decimal("0"),
        quarter_values=[ISKQuarterValue(i, Decimal("100000")) for i in range(1, 5)],
        statslaneranta_30_nov=Decimal("0.0262"),  # 2.62 %
    )
    res = ISKCalculator().compute(data)
    # Rate = 3.62 %; Underlag = 125 000
    assert res.schablonrate == Decimal("0.036200")
    assert res.underlag == Decimal("125000.00")
    assert res.schablonintakt == Decimal("4525.00")
    assert res.skatt == Decimal("1357.50")


def test_k4_simple_buy_sell():
    trades = [
        Trade(date(2024, 1, 10), "AAPL", Decimal("10"), Decimal("100"), Decimal("1")),
        Trade(date(2025, 2, 1), "AAPL", Decimal("10"), Decimal("120"), Decimal("1")),
        Trade(date(2026, 3, 1), "AAPL", Decimal("-10"), Decimal("150"), Decimal("2")),
    ]
    rep = K4Calculator().compute(trades, 2026)
    assert len(rep.lines) == 1
    line = rep.lines[0]
    # snittkostnad: (10*100+1 + 10*120+1)/20 = (1001+1201)/20 = 110.1
    # sålda 10 → cost = 1101
    # proceeds = 10*150 - 2 = 1498
    # gain = 397
    assert line.acquisition_cost == Decimal("1101.00")
    assert line.sale_proceeds == Decimal("1498.00")
    assert line.gain == Decimal("397.00")
    assert rep.net == Decimal("397.00")


def test_k4_loss():
    trades = [
        Trade(date(2026, 1, 1), "XYZ", Decimal("100"), Decimal("50"), Decimal("0")),
        Trade(date(2026, 6, 1), "XYZ", Decimal("-100"), Decimal("30"), Decimal("0")),
    ]
    rep = K4Calculator().compute(trades, 2026)
    assert rep.lines[0].gain == Decimal("-2000.00")
    assert rep.total_loss == Decimal("2000.00")
    assert rep.net == Decimal("-2000.00")
