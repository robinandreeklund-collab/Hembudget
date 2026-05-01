"""B1 · Marknadsdata + månadsdrift per stad.

Spec: dev/game-motor/06-boendemarknaden.md (Marknads-data · Bostadsrätt-priser)

Bas-priset per kvm är hämtat från `stadspoolen.avg_brf_price_per_kvm`.
Månadsdrift modelleras som lognormal-fördelning med stadens trend +
volatilitet. För deterministisk testbarhet används seed (year_month +
city.key) som rng-källa.

Trenderna (yearly_trend) appliceras varje månad som ~yearly/12. Den
förväntade prisändringen per månad blir då ≈ trend/12 ± volatilitet.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Optional

from ..pools.stadspool import STAD_BY_KEY


@dataclass(frozen=True)
class CityPriceTrend:
    """Per-stad pris-utvecklings-parametrar."""

    yearly_trend: float        # Förväntad årlig prisutveckling (0.05 = +5%/år)
    monthly_volatility: float  # Std för månads-drift (0.008 = ±0.8 %/månad)


# Realistiska 2026-trender per stad (källa: Mäklarstatistik prognoser
# uppjusterade för stadens efterfrågan och inflation)
PRICE_DRIFT_TRENDS: dict[str, CityPriceTrend] = {
    "stockholm":  CityPriceTrend(yearly_trend=0.050, monthly_volatility=0.008),
    "goteborg":   CityPriceTrend(yearly_trend=0.040, monthly_volatility=0.007),
    "malmo":      CityPriceTrend(yearly_trend=0.035, monthly_volatility=0.007),
    "uppsala":    CityPriceTrend(yearly_trend=0.045, monthly_volatility=0.008),
    "linkoping":  CityPriceTrend(yearly_trend=0.035, monthly_volatility=0.006),
    "orebro":     CityPriceTrend(yearly_trend=0.030, monthly_volatility=0.006),
    "vasteras":   CityPriceTrend(yearly_trend=0.030, monthly_volatility=0.006),
    "norrkoping": CityPriceTrend(yearly_trend=0.025, monthly_volatility=0.006),
    "gavle":      CityPriceTrend(yearly_trend=0.025, monthly_volatility=0.005),
    "sundsvall":  CityPriceTrend(yearly_trend=0.020, monthly_volatility=0.005),
    "umea":       CityPriceTrend(yearly_trend=0.040, monthly_volatility=0.007),
    "lulea":      CityPriceTrend(yearly_trend=0.025, monthly_volatility=0.005),
    "medelstad":  CityPriceTrend(yearly_trend=0.030, monthly_volatility=0.005),
    "smaort":     CityPriceTrend(yearly_trend=0.020, monthly_volatility=0.003),
}


def _ym_to_months_since(year_month: str, baseline_ym: str = "2026-01") -> int:
    """Antal månader mellan baseline_ym och year_month."""
    y1, m1 = map(int, baseline_ym.split("-"))
    y2, m2 = map(int, year_month.split("-"))
    return (y2 - y1) * 12 + (m2 - m1)


def market_price_for(
    city_key: str,
    year_month: str,
    *,
    baseline_ym: str = "2026-01",
    seed_extra: int = 0,
) -> int:
    """Returnerar snittpris kr/kvm för bostadsrätt i staden vid year_month.

    Beräknas som baspris × (1 + yearly_trend/12)^N × slumpmässig
    volatilitets-faktor. Deterministisk: samma (city, year_month)
    ger samma pris.
    """
    city = STAD_BY_KEY.get(city_key)
    if city is None:
        return 0
    trend = PRICE_DRIFT_TRENDS.get(
        city_key,
        CityPriceTrend(yearly_trend=0.025, monthly_volatility=0.005),
    )

    months = _ym_to_months_since(year_month, baseline_ym)
    base = city.avg_brf_price_per_kvm
    monthly_growth = trend.yearly_trend / 12.0

    # Deterministisk volatilitet: rng seedad på (city, year_month)
    rng = random.Random(f"market|{city_key}|{year_month}|{seed_extra}")
    # Lognormal kring 0 med given std
    shock = rng.gauss(0.0, trend.monthly_volatility)
    # Trend-komponenten ger månads-multiplikator (1 + monthly_growth)
    factor = (1.0 + monthly_growth) ** months * math.exp(shock)
    return max(5_000, int(base * factor))
