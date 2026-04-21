"""Test för elprisetjustnu-klienten (utan riktig HTTP)."""
from __future__ import annotations

from datetime import date, datetime

import pytest

from hembudget.elpris import ElprisClient, VALID_ZONES


SAMPLE_HOURS = [
    {
        "SEK_per_kWh": 0.10,
        "EUR_per_kWh": 0.009,
        "EXR": 11.1,
        "time_start": "2026-04-21T00:00:00+02:00",
        "time_end": "2026-04-21T01:00:00+02:00",
    },
    {
        "SEK_per_kWh": 0.20,
        "EUR_per_kWh": 0.018,
        "EXR": 11.1,
        "time_start": "2026-04-21T01:00:00+02:00",
        "time_end": "2026-04-21T02:00:00+02:00",
    },
    {
        "SEK_per_kWh": 0.50,
        "EUR_per_kWh": 0.045,
        "EXR": 11.1,
        "time_start": "2026-04-21T18:00:00+02:00",
        "time_end": "2026-04-21T19:00:00+02:00",
    },
]


def _fake_fetch(url: str) -> list[dict]:
    return list(SAMPLE_HOURS)


def test_invalid_zone_raises():
    with pytest.raises(ValueError):
        ElprisClient(zone="SE9")


def test_url_format():
    client = ElprisClient(fetch=_fake_fetch, zone="SE3")
    url = client._url(date(2026, 4, 21), "SE3")
    assert url == "https://www.elprisetjustnu.se/api/v1/prices/2026/04-21_SE3.json"


def test_parses_hours_and_adds_vat():
    client = ElprisClient(fetch=_fake_fetch, zone="SE3")
    day = client.get(date(2026, 4, 21))
    assert len(day.hours) == 3
    h = day.hours[0]
    assert h.sek_per_kwh == 0.10
    # 0.10 × 1.25 = 0.125
    assert h.sek_inc_vat == 0.125


def test_min_max_and_avg():
    client = ElprisClient(fetch=_fake_fetch, zone="SE3")
    day = client.get(date(2026, 4, 21))
    assert day.min_hour.sek_per_kwh == 0.10
    assert day.max_hour.sek_per_kwh == 0.50
    # Snitt inkl moms: (0.125 + 0.25 + 0.625) / 3 = 0.333...
    assert round(day.avg_inc_vat, 3) == 0.333


def test_cheapest_hours_sorted():
    client = ElprisClient(fetch=_fake_fetch, zone="SE3")
    day = client.get(date(2026, 4, 21))
    top2 = day.cheapest_hours(2)
    assert [h.sek_per_kwh for h in top2] == [0.10, 0.20]


def test_cache_avoids_refetch():
    calls: list[str] = []

    def counting_fetch(url: str) -> list[dict]:
        calls.append(url)
        return list(SAMPLE_HOURS)

    client = ElprisClient(fetch=counting_fetch, zone="SE3")
    client.get(date(2026, 4, 21))
    client.get(date(2026, 4, 21))
    client.get(date(2026, 4, 21), zone="SE1")
    assert len(calls) == 2  # samma datum, olika zone → två anrop


def test_skips_malformed_rows():
    def bad_fetch(url):
        return [
            SAMPLE_HOURS[0],
            {"SEK_per_kWh": "not-a-number"},  # bryter typning
            SAMPLE_HOURS[1],
        ]

    client = ElprisClient(fetch=bad_fetch, zone="SE3")
    day = client.get(date(2026, 4, 21))
    assert len(day.hours) == 2


def test_all_zones_valid():
    for z in VALID_ZONES:
        client = ElprisClient(fetch=_fake_fetch, zone=z)
        day = client.get(date(2026, 4, 21))
        assert day.zone == z
