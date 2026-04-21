from datetime import date, timedelta
from decimal import Decimal

from hembudget.subscriptions.detector import SubscriptionDetector


class _FakeTx:
    def __init__(self, d, amount, merchant, account_id=1, category_id=None):
        self.date = d
        self.amount = Decimal(str(amount))
        self.normalized_merchant = merchant
        self.account_id = account_id
        self.category_id = category_id


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    def query(self, _model):
        return _FakeQuery(self._rows)


def test_detects_monthly_subscription():
    rows = [
        _FakeTx(date(2026, 1, 5), -129, "SPOTIFY"),
        _FakeTx(date(2026, 2, 5), -129, "SPOTIFY"),
        _FakeTx(date(2026, 3, 5), -129, "SPOTIFY"),
        _FakeTx(date(2026, 4, 5), -129, "SPOTIFY"),
    ]
    det = SubscriptionDetector(_FakeSession(rows))
    cands = det.detect()
    assert len(cands) == 1
    c = cands[0]
    assert c.merchant == "SPOTIFY"
    assert c.interval_days in (30, 31)
    assert c.occurrences == 4
    assert c.next_expected_date > date(2026, 4, 5)


def test_ignores_non_recurring():
    rows = [
        _FakeTx(date(2026, 1, 5), -200, "ICA"),
        _FakeTx(date(2026, 1, 6), -50, "ICA"),
    ]
    det = SubscriptionDetector(_FakeSession(rows))
    assert det.detect() == []
