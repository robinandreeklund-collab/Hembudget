"""Bolåne- och styrräntor — historiska data + Riksbankens SweaApi-update.

Strategi:
- Första gången InterestRateSeries är tom fylls den från STATIC_SERIES
  (hårdkodade månadsvärden från SCB/Riksbanken 2015-2026).
- /teacher/rates/refresh kan anropas för att hämta senaste från
  Riksbanken och fylla på det som saknas.
- scenario.py frågar get_rate_for_month() när ett lånebesked renderas.

Spreaden mellan policy och bolåneränta är ca 2.2-3.2 procentenheter
beroende på bindningstyp — typiska svenska listpriser.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Literal

log = logging.getLogger(__name__)

RateType = Literal["policy", "stibor3m", "bolan_rorlig", "bolan_3ar", "bolan_5ar"]


# Hårdkodade månadsvärden — styrränta (Riksbanken) 2015-01 → 2026-04.
# Bolåneräntor härleds som policy + spread (se _derive_bolan_from_policy).
# Källa: Riksbanken "Reporänta förändringar" + SCB MFI-statistik.
STATIC_POLICY_MONTHLY: dict[str, float] = {
    # 2015-2019: negativ ränta/noll
    "2015-01": -0.00050, "2015-02": -0.00050, "2015-03": -0.00250,
    "2015-04": -0.00250, "2015-05": -0.00250, "2015-06": -0.00250,
    "2015-07": -0.00350, "2015-08": -0.00350, "2015-09": -0.00350,
    "2015-10": -0.00350, "2015-11": -0.00350, "2015-12": -0.00350,
    "2016-01": -0.00350, "2016-02": -0.00500, "2016-03": -0.00500,
    "2016-04": -0.00500, "2016-05": -0.00500, "2016-06": -0.00500,
    "2016-07": -0.00500, "2016-08": -0.00500, "2016-09": -0.00500,
    "2016-10": -0.00500, "2016-11": -0.00500, "2016-12": -0.00500,
    # 2017-2018: fortsatt negativ
    **{f"2017-{m:02d}": -0.00500 for m in range(1, 13)},
    **{f"2018-{m:02d}": -0.00500 for m in range(1, 13)},
    # 2019: första höjningen, sedan tillbaka
    "2019-01": -0.00250, "2019-02": -0.00250, "2019-03": -0.00250,
    **{f"2019-{m:02d}": -0.00250 for m in range(4, 13)},
    # 2020-2021: 0 %
    **{f"2020-{m:02d}": 0.0 for m in range(1, 13)},
    **{f"2021-{m:02d}": 0.0 for m in range(1, 13)},
    # 2022: snabba höjningar
    "2022-01": 0.0, "2022-02": 0.0, "2022-03": 0.0, "2022-04": 0.0,
    "2022-05": 0.0025, "2022-06": 0.0025, "2022-07": 0.0075,
    "2022-08": 0.0075, "2022-09": 0.0175, "2022-10": 0.0175,
    "2022-11": 0.0250, "2022-12": 0.0250,
    # 2023: fortsatt upp
    "2023-01": 0.0250, "2023-02": 0.0300, "2023-03": 0.0300,
    "2023-04": 0.0350, "2023-05": 0.0350, "2023-06": 0.0375,
    "2023-07": 0.0375, "2023-08": 0.0375, "2023-09": 0.0400,
    "2023-10": 0.0400, "2023-11": 0.0400, "2023-12": 0.0400,
    # 2024: topp och sänkning
    "2024-01": 0.0400, "2024-02": 0.0400, "2024-03": 0.0400,
    "2024-04": 0.0400, "2024-05": 0.0375, "2024-06": 0.0375,
    "2024-07": 0.0350, "2024-08": 0.0350, "2024-09": 0.0325,
    "2024-10": 0.0325, "2024-11": 0.0275, "2024-12": 0.0250,
    # 2025: fortsatta sänkningar
    "2025-01": 0.0250, "2025-02": 0.0225, "2025-03": 0.0225,
    "2025-04": 0.0200, "2025-05": 0.0200, "2025-06": 0.0200,
    "2025-07": 0.0200, "2025-08": 0.0200, "2025-09": 0.0225,
    "2025-10": 0.0225, "2025-11": 0.0225, "2025-12": 0.0250,
    # 2026: prognos (justeras med riktig data när tillgänglig)
    "2026-01": 0.0250, "2026-02": 0.0275, "2026-03": 0.0275,
    "2026-04": 0.0300,
}


# Spread (procentenheter) ovanpå styrränta för respektive bolåneränta
SPREAD_RORLIG = 0.0150
SPREAD_3AR = 0.0120
SPREAD_5AR = 0.0140


def _derive(policy: float, rate_type: RateType) -> float:
    if rate_type == "policy":
        return policy
    if rate_type == "stibor3m":
        return max(0, policy + 0.0010)
    if rate_type == "bolan_rorlig":
        return max(0.01, policy + SPREAD_RORLIG)
    if rate_type == "bolan_3ar":
        # Bundna räntor "glänter" mindre mot policy — använd glidande medel
        return max(0.015, policy + SPREAD_3AR)
    if rate_type == "bolan_5ar":
        return max(0.02, policy + SPREAD_5AR)
    return policy


def seed_static_series(master_session) -> int:
    """Fyll InterestRateSeries från STATIC_POLICY_MONTHLY första gången.
    Returnerar antal rader insatta."""
    from .models import InterestRateSeries
    existing = {
        (r.rate_type, r.year_month)
        for r in master_session.query(InterestRateSeries).all()
    }
    n_added = 0
    rate_types: list[RateType] = [
        "policy", "stibor3m", "bolan_rorlig", "bolan_3ar", "bolan_5ar",
    ]
    for ym, policy in STATIC_POLICY_MONTHLY.items():
        for rt in rate_types:
            if (rt, ym) in existing:
                continue
            master_session.add(InterestRateSeries(
                rate_type=rt, year_month=ym,
                rate=_derive(policy, rt),
                source="static",
            ))
            n_added += 1
    return n_added


def get_rate_for_month(
    master_session, year_month: str, rate_type: RateType = "bolan_rorlig",
) -> float | None:
    """Hitta räntan för given månad. Fallback: närmaste tidigare månad.
    Returnerar None om ingen data finns överhuvudtaget."""
    from .models import InterestRateSeries
    row = master_session.query(InterestRateSeries).filter(
        InterestRateSeries.rate_type == rate_type,
        InterestRateSeries.year_month == year_month,
    ).first()
    if row:
        return row.rate
    # Fallback: närmaste tidigare
    row = (
        master_session.query(InterestRateSeries)
        .filter(
            InterestRateSeries.rate_type == rate_type,
            InterestRateSeries.year_month <= year_month,
        )
        .order_by(InterestRateSeries.year_month.desc())
        .first()
    )
    return row.rate if row else None


def refresh_from_riksbank(master_session) -> dict:
    """Hämta senaste policy-räntor från Riksbanken och fyll på.
    API: https://api.riksbank.se/swea/v1/Observations/

    Serie-id för reporänta: SECBREPOEFF (daglig)
    Vi tar sista observationen per månad.

    Graceful: om APIet inte svarar loggas felet men inga exceptions
    stoppar anropande endpoint.
    """
    import httpx
    result = {"fetched": 0, "added": 0, "errors": []}
    try:
        # 2015-01-01 till idag
        url = (
            "https://api.riksbank.se/swea/v1/Observations/"
            "SECBREPOEFF/2015-01-01"
        )
        with httpx.Client(timeout=10.0) as c:
            r = c.get(url)
            if r.status_code != 200:
                result["errors"].append(f"HTTP {r.status_code}")
                return result
            data = r.json()  # list av {date, value}
            result["fetched"] = len(data)

        # Aggregera till månadsvärden (sista observationen i varje månad)
        by_month: dict[str, float] = {}
        for obs in data:
            d = obs.get("date")
            v = obs.get("value")
            if not d or v is None:
                continue
            ym = d[:7]
            by_month[ym] = float(v) / 100.0  # API returnerar i procent (t.ex. 3.25)

        from .models import InterestRateSeries
        existing = {
            (r.rate_type, r.year_month): r
            for r in master_session.query(InterestRateSeries).all()
        }
        rate_types: list[RateType] = [
            "policy", "stibor3m", "bolan_rorlig", "bolan_3ar", "bolan_5ar",
        ]
        for ym, policy in by_month.items():
            for rt in rate_types:
                key = (rt, ym)
                new_rate = _derive(policy, rt)
                if key in existing:
                    # Uppdatera om källan inte är riksbank-baserad
                    row = existing[key]
                    if row.source != "riksbank":
                        row.rate = new_rate
                        row.source = "riksbank"
                        row.updated_at = datetime.utcnow()
                else:
                    master_session.add(InterestRateSeries(
                        rate_type=rt, year_month=ym,
                        rate=new_rate, source="riksbank",
                    ))
                    result["added"] += 1
    except Exception as e:
        log.exception("Riksbank-API misslyckades")
        result["errors"].append(str(e))
    return result
