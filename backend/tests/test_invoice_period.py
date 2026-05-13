"""Tester för efterskotts-period på konsumtionsbaserade fakturor.

Användsfall: Tibber el, Bahnhof bredband, Telia mobil, bolåneränta
och driftavi villa fakturerar passerad månad — fakturan i maj avser
april-förbrukning. Tidigare visade alla fakturor "2026-05-01 – 2026-
05-31" även på 5:e maj, vilket är pedagogiskt missvisande (du KAN
inte få faktura för förbrukning som ännu inte har skett).
"""
from __future__ import annotations

from datetime import date

from hembudget.game_engine.monthly_engine.fixed_expenses import (
    _period_dates,
    _prev_period_dates,
    _prev_year_month,
)


def test_prev_year_month_basic():
    assert _prev_year_month("2026-05") == "2026-04"
    assert _prev_year_month("2026-12") == "2026-11"


def test_prev_year_month_january_wraps():
    assert _prev_year_month("2026-01") == "2025-12"


def test_prev_period_dates_returns_april_for_may():
    start, end = _prev_period_dates("2026-05")
    assert start == date(2026, 4, 1)
    assert end == date(2026, 4, 30)


def test_prev_period_dates_february_handles_leap_year():
    start, end = _prev_period_dates("2024-03")
    assert start == date(2024, 2, 1)
    assert end == date(2024, 2, 29)  # 2024 är skottår


def test_period_vs_prev_period_differ():
    cur_s, cur_e = _period_dates("2026-05")
    prev_s, prev_e = _prev_period_dates("2026-05")
    assert cur_s != prev_s
    assert cur_e != prev_e
