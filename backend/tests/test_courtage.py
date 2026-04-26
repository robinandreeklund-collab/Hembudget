"""Tester för courtage-beräkningen (Avanza Mini m.fl.)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from hembudget.stocks.courtage import compute_courtage


def test_mini_under_min_returns_minimum():
    """Mycket små affärer landar på 1 kr minimi."""
    # 100 kr * 0,25 % = 0,25 kr → minimi vinner
    assert compute_courtage(Decimal("100"), "mini") == Decimal("1.00")
    # 400 kr * 0,25 % = 1,00 kr → exakt på gränsen
    assert compute_courtage(Decimal("400"), "mini") == Decimal("1.00")


def test_mini_above_min_uses_percent():
    """Stora affärer ger procentuellt courtage."""
    # 4000 kr * 0,25 % = 10 kr
    assert compute_courtage(Decimal("4000"), "mini") == Decimal("10.00")
    # 10 000 kr * 0,25 % = 25 kr
    assert compute_courtage(Decimal("10000"), "mini") == Decimal("25.00")


def test_mini_rounds_to_ore():
    """0,25 % på 4567 kr = 11,4175 → 11,42 (HALF_UP)."""
    result = compute_courtage(Decimal("4567"), "mini")
    assert result == Decimal("11.42")


def test_start_is_fixed_39():
    assert compute_courtage(Decimal("1000"), "start") == Decimal("39.00")
    assert compute_courtage(Decimal("100000"), "start") == Decimal("39.00")


def test_none_is_zero():
    assert compute_courtage(Decimal("5000"), "none") == Decimal("0.00")


def test_zero_or_negative_returns_zero():
    assert compute_courtage(Decimal("0")) == Decimal("0.00")
    assert compute_courtage(Decimal("-100")) == Decimal("0.00")


def test_default_uses_env_var(monkeypatch):
    monkeypatch.setenv("HEMBUDGET_COURTAGE_MODEL", "start")
    assert compute_courtage(Decimal("1000")) == Decimal("39.00")
    monkeypatch.setenv("HEMBUDGET_COURTAGE_MODEL", "none")
    assert compute_courtage(Decimal("1000")) == Decimal("0.00")


def test_default_when_env_unset_is_mini(monkeypatch):
    monkeypatch.delenv("HEMBUDGET_COURTAGE_MODEL", raising=False)
    # 4000 * 0,25 % = 10
    assert compute_courtage(Decimal("4000")) == Decimal("10.00")


def test_unknown_model_falls_back_to_mini():
    """Okänd modell → mini-default."""
    assert compute_courtage(Decimal("4000"), "okand") == Decimal("10.00")
