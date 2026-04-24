"""Svenska spotelpriser från elprisetjustnu.se.

API: https://www.elprisetjustnu.se/elpris-api
- Gratis, ingen autentisering.
- URL-mönster: /api/v1/prices/YYYY/MM-DD_ZONE.json
- Zone = SE1 (norr), SE2 (norra mellan), SE3 (södra mellan, t.ex. Stockholm/Hjo),
  SE4 (syd).
- Data publiceras omkring 13:00 CET för nästa dag.
- Retroaktiv data ändras aldrig → cache evigt säkert.

Returnerar per timme:
- SEK_per_kWh (exkl. moms och nätavgift)
- EUR_per_kWh
- EXR (växelkurs)
- time_start / time_end (ISO 8601 med tidszon)

Vi berikar med:
- SEK_inc_vat = SEK_per_kWh × 1.25 (25 % moms)
- är_billig/är_dyr-flaggor baserat på dagens snitt
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from statistics import mean
from typing import Callable

import httpx

log = logging.getLogger(__name__)

VALID_ZONES = ("SE1", "SE2", "SE3", "SE4")
VAT_MULTIPLIER = Decimal("1.25")
API_BASE = "https://www.elprisetjustnu.se/api/v1/prices"


@dataclass
class HourlyPrice:
    time_start: datetime
    time_end: datetime
    sek_per_kwh: float       # exkl. moms
    sek_inc_vat: float       # inkl. 25 % moms
    eur_per_kwh: float


@dataclass
class DayPrices:
    date: date
    zone: str
    hours: list[HourlyPrice]

    @property
    def avg_inc_vat(self) -> float:
        if not self.hours:
            return 0.0
        return round(mean(h.sek_inc_vat for h in self.hours), 4)

    @property
    def min_hour(self) -> HourlyPrice | None:
        return min(self.hours, key=lambda h: h.sek_inc_vat) if self.hours else None

    @property
    def max_hour(self) -> HourlyPrice | None:
        return max(self.hours, key=lambda h: h.sek_inc_vat) if self.hours else None

    def cheapest_hours(self, n: int = 3) -> list[HourlyPrice]:
        return sorted(self.hours, key=lambda h: h.sek_inc_vat)[:n]


# HTTP-klient som injiceras i klass för testning
FetchFn = Callable[[str], list[dict]]


def _default_fetch(url: str) -> list[dict]:
    with httpx.Client(timeout=10.0) as client:
        r = client.get(url)
        r.raise_for_status()
        return r.json()


class ElprisClient:
    """Cachad klient mot elprisetjustnu.se."""

    def __init__(
        self,
        fetch: FetchFn | None = None,
        zone: str = "SE3",
    ):
        if zone not in VALID_ZONES:
            raise ValueError(f"zone must be one of {VALID_ZONES}, got {zone!r}")
        self.fetch = fetch or _default_fetch
        self.default_zone = zone
        # (date, zone) → DayPrices. Data ändras aldrig → säker evig cache.
        self._cache: dict[tuple[date, str], DayPrices] = {}

    def _url(self, d: date, zone: str) -> str:
        return f"{API_BASE}/{d.year}/{d.month:02d}-{d.day:02d}_{zone}.json"

    def get(self, d: date, zone: str | None = None) -> DayPrices:
        """Hämta priser för ett specifikt datum. Kastar om API returnerar
        HTTP 404 (vanligt innan 13:00 för morgondagen)."""
        z = zone or self.default_zone
        if z not in VALID_ZONES:
            raise ValueError(f"zone must be one of {VALID_ZONES}, got {z!r}")
        key = (d, z)
        if key in self._cache:
            return self._cache[key]
        raw = self.fetch(self._url(d, z))
        hours: list[HourlyPrice] = []
        for row in raw:
            try:
                start = datetime.fromisoformat(row["time_start"])
                end = datetime.fromisoformat(row["time_end"])
                sek = float(row["SEK_per_kWh"])
                eur = float(row["EUR_per_kWh"])
            except (KeyError, ValueError) as exc:
                log.warning("ogiltig rad från elpris-API: %r (%s)", row, exc)
                continue
            hours.append(HourlyPrice(
                time_start=start,
                time_end=end,
                sek_per_kwh=sek,
                sek_inc_vat=round(sek * float(VAT_MULTIPLIER), 5),
                eur_per_kwh=eur,
            ))
        result = DayPrices(date=d, zone=z, hours=hours)
        self._cache[key] = result
        return result

    def today(self, zone: str | None = None) -> DayPrices:
        return self.get(date.today(), zone)

    def tomorrow(self, zone: str | None = None) -> DayPrices:
        return self.get(date.today() + timedelta(days=1), zone)
