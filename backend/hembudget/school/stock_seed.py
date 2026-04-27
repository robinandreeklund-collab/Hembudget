"""Idempotent seed för aktiekurs-infrastrukturen.

- 30 OMXS30-aktier som tillgängliga i simulatorn (välkända svenska
  large-caps över 8 sektorer för rimlig diversifiering)
- Marknadskalender för innevarande + nästa år (svenska helgdagar)

Körs vid uppstart från main.py::lifespan eller manuellt via CLI.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable

from sqlalchemy.orm import Session

from .stock_models import MarketCalendar, StockMaster


# 30 svenska aktier från OMXS30 (april 2026). Sektorer förenklade till
# 8 grupper för att underlätta diversifieringsövningar.
STOCK_UNIVERSE: list[dict] = [
    # Industri
    {"ticker": "VOLV-B.ST",  "name": "Volvo B",            "sector": "Industri"},
    {"ticker": "ATCO-A.ST",  "name": "Atlas Copco A",      "sector": "Industri"},
    {"ticker": "ATCO-B.ST",  "name": "Atlas Copco B",      "sector": "Industri"},
    {"ticker": "SAND.ST",    "name": "Sandvik",            "sector": "Industri"},
    {"ticker": "ABB.ST",     "name": "ABB",                "sector": "Industri"},
    {"ticker": "ALFA.ST",    "name": "Alfa Laval",         "sector": "Industri"},
    {"ticker": "SKF-B.ST",   "name": "SKF B",              "sector": "Industri"},
    # Bank/Finans
    {"ticker": "SEB-A.ST",   "name": "SEB A",              "sector": "Bank"},
    {"ticker": "SHB-A.ST",   "name": "Svenska Handelsbanken A", "sector": "Bank"},
    {"ticker": "SWED-A.ST",  "name": "Swedbank A",         "sector": "Bank"},
    {"ticker": "NDA-SE.ST",  "name": "Nordea Bank",        "sector": "Bank"},
    {"ticker": "INVE-B.ST",  "name": "Investor B",         "sector": "Bank"},
    # Telecom
    {"ticker": "TELIA.ST",   "name": "Telia Company",      "sector": "Telecom"},
    {"ticker": "TEL2-B.ST",  "name": "Tele2 B",            "sector": "Telecom"},
    {"ticker": "ERIC-B.ST",  "name": "Ericsson B",         "sector": "Telecom"},
    # Konsument
    {"ticker": "HM-B.ST",    "name": "Hennes & Mauritz B", "sector": "Konsument"},
    {"ticker": "ESSITY-B.ST", "name": "Essity B",          "sector": "Konsument"},
    {"ticker": "AZN.ST",     "name": "AstraZeneca",        "sector": "Hälsa"},
    {"ticker": "GETI-B.ST",  "name": "Getinge B",          "sector": "Hälsa"},
    {"ticker": "SOBI.ST",    "name": "Swedish Orphan Biovitrum", "sector": "Hälsa"},
    # IT
    {"ticker": "EVO.ST",     "name": "Evolution",          "sector": "IT"},
    {"ticker": "SINCH.ST",   "name": "Sinch",              "sector": "IT"},
    # Råvaror
    {"ticker": "BOL.ST",     "name": "Boliden",            "sector": "Råvaror"},
    {"ticker": "SCA-B.ST",   "name": "SCA B",              "sector": "Råvaror"},
    {"ticker": "SSAB-A.ST",  "name": "SSAB A",             "sector": "Råvaror"},
    # Fastighet
    {"ticker": "SBB-B.ST",   "name": "Samhällsbyggnadsbolaget B", "sector": "Fastighet"},
    {"ticker": "BALD-B.ST",  "name": "Balder B",           "sector": "Fastighet"},
    {"ticker": "CAST.ST",    "name": "Castellum",          "sector": "Fastighet"},
    # Energi/Övrigt
    {"ticker": "EQT.ST",     "name": "EQT",                "sector": "Bank"},
    {"ticker": "ELUX-B.ST",  "name": "Electrolux B",       "sector": "Konsument"},
]


# 30 amerikanska aktier (NYSE/NASDAQ) — tillåter elever att jämföra
# svenska och amerikanska bolag, lära sig om utlandshandel och
# valutaväxlingsrisk. Yfinance täcker dem utan extra konfig.
US_STOCK_UNIVERSE: list[dict] = [
    # Tech (mega-cap)
    {"ticker": "AAPL",  "name": "Apple",          "sector": "IT-USA"},
    {"ticker": "MSFT",  "name": "Microsoft",      "sector": "IT-USA"},
    {"ticker": "GOOGL", "name": "Alphabet A",     "sector": "IT-USA"},
    {"ticker": "META",  "name": "Meta Platforms", "sector": "IT-USA"},
    {"ticker": "NVDA",  "name": "Nvidia",         "sector": "IT-USA"},
    {"ticker": "AMZN",  "name": "Amazon",         "sector": "IT-USA"},
    {"ticker": "TSLA",  "name": "Tesla",          "sector": "IT-USA"},
    {"ticker": "NFLX",  "name": "Netflix",        "sector": "IT-USA"},
    # Finans
    {"ticker": "JPM",   "name": "JPMorgan Chase", "sector": "Bank-USA"},
    {"ticker": "BAC",   "name": "Bank of America", "sector": "Bank-USA"},
    {"ticker": "V",     "name": "Visa",           "sector": "Bank-USA"},
    {"ticker": "MA",    "name": "Mastercard",     "sector": "Bank-USA"},
    {"ticker": "BRK-B", "name": "Berkshire Hathaway B", "sector": "Bank-USA"},
    # Konsument
    {"ticker": "KO",    "name": "Coca-Cola",      "sector": "Konsument-USA"},
    {"ticker": "PEP",   "name": "PepsiCo",        "sector": "Konsument-USA"},
    {"ticker": "MCD",   "name": "McDonald's",     "sector": "Konsument-USA"},
    {"ticker": "NKE",   "name": "Nike",           "sector": "Konsument-USA"},
    {"ticker": "DIS",   "name": "Walt Disney",    "sector": "Konsument-USA"},
    {"ticker": "WMT",   "name": "Walmart",        "sector": "Konsument-USA"},
    # Hälsa/läkemedel
    {"ticker": "JNJ",   "name": "Johnson & Johnson", "sector": "Hälsa-USA"},
    {"ticker": "PFE",   "name": "Pfizer",         "sector": "Hälsa-USA"},
    {"ticker": "UNH",   "name": "UnitedHealth",   "sector": "Hälsa-USA"},
    # Industri/energi
    {"ticker": "XOM",   "name": "Exxon Mobil",    "sector": "Energi-USA"},
    {"ticker": "CVX",   "name": "Chevron",        "sector": "Energi-USA"},
    {"ticker": "BA",    "name": "Boeing",         "sector": "Industri-USA"},
    {"ticker": "CAT",   "name": "Caterpillar",    "sector": "Industri-USA"},
    {"ticker": "GE",    "name": "General Electric", "sector": "Industri-USA"},
    # Övriga välkända
    {"ticker": "SBUX",  "name": "Starbucks",      "sector": "Konsument-USA"},
    {"ticker": "PYPL",  "name": "PayPal",         "sector": "IT-USA"},
    {"ticker": "INTC",  "name": "Intel",          "sector": "IT-USA"},
]


def seed_stock_universe(session: Session) -> int:
    """Idempotent seed av StockMaster — bara tillägg, aldrig delete.

    Returnerar antal tillagda rader. Innehåller både svenska
    OMXS30-aktier (XSTO, SEK) och amerikanska large-caps
    (NYSE/NASDAQ, USD) — eleven kan handla båda och lära sig
    skillnaden i kostnader (utlandscourtage, valutaväxlingsavgift)."""
    existing = {s.ticker for s in session.query(StockMaster).all()}
    added = 0
    for entry in STOCK_UNIVERSE:
        if entry["ticker"] in existing:
            continue
        session.add(StockMaster(
            ticker=entry["ticker"],
            name=entry["name"],
            name_sv=entry.get("name_sv"),
            sector=entry["sector"],
            currency="SEK",
            exchange="XSTO",
            active=1,
        ))
        added += 1
    for entry in US_STOCK_UNIVERSE:
        if entry["ticker"] in existing:
            continue
        session.add(StockMaster(
            ticker=entry["ticker"],
            name=entry["name"],
            name_sv=entry.get("name_sv"),
            sector=entry["sector"],
            currency="USD",
            exchange="XNAS",  # generisk USA — yfinance bryr sig inte
            active=1,
        ))
        added += 1
    if added:
        session.flush()
    return added


# --- Marknadskalender ---

def _swedish_holidays(year: int) -> set[date]:
    """Returnera svenska helgdagar då börsen är stängd. Inkluderar fasta
    helgdagar + påskberoende. Midsommarafton är sedan 2021 stängd hela
    dagen (innan halvdag), julafton/nyårsafton är också stängda hela
    dagen (innan halvdag)."""
    from datetime import date as D

    # Beräkna påskdagen — Anonymous Gregorian algoritm
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    L = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * L) // 451
    month = (h + L - 7 * m + 114) // 31
    day = ((h + L - 7 * m + 114) % 31) + 1
    easter_sunday = D(year, month, day)
    good_friday = easter_sunday - timedelta(days=2)
    easter_monday = easter_sunday + timedelta(days=1)
    ascension = easter_sunday + timedelta(days=39)

    # Midsommarafton = fredagen mellan 19 och 25 juni
    midsommarafton = next(
        D(year, 6, d) for d in range(19, 26)
        if D(year, 6, d).weekday() == 4
    )

    return {
        D(year, 1, 1),   # Nyårsdagen
        D(year, 1, 6),   # Trettondag jul
        good_friday,
        easter_monday,
        D(year, 5, 1),   # Första maj
        ascension,
        D(year, 6, 6),   # Nationaldagen (handelsdag i praktiken men ofta stängt)
        midsommarafton,
        D(year, 12, 24),  # Julafton
        D(year, 12, 25),  # Juldagen
        D(year, 12, 26),  # Annandag jul
        D(year, 12, 31),  # Nyårsafton
    }


def seed_market_calendar(session: Session, *, years_ahead: int = 1) -> int:
    """Seeda börstidskalendern för current_year + years_ahead år framåt.

    Idempotent: bara dagar som inte redan finns läggs till.
    Returnerar antal tillagda rader."""
    today = date.today()
    end_year = today.year + years_ahead

    existing = {
        (r.calendar_date, r.exchange)
        for r in session.query(MarketCalendar).all()
    }

    added = 0
    for year in range(today.year, end_year + 1):
        holidays = _swedish_holidays(year)
        d = date(year, 1, 1)
        last = date(year, 12, 31)
        while d <= last:
            key = (d, "XSTO")
            if key in existing:
                d += timedelta(days=1)
                continue
            is_weekend = d.weekday() >= 5
            is_holiday = d in holidays
            if is_weekend or is_holiday:
                status = "closed"
                note = "Helg" if is_weekend else "Helgdag"
                open_time = None
                close_time = None
            else:
                status = "open"
                note = None
                open_time = "09:00"
                close_time = "17:30"
            session.add(MarketCalendar(
                calendar_date=d,
                exchange="XSTO",
                status=status,
                open_time=open_time,
                close_time=close_time,
                note=note,
            ))
            added += 1
            d += timedelta(days=1)
    if added:
        session.flush()
    return added


def seed_all(session: Session) -> dict:
    """Seeda allt aktie-relaterat. Idempotent."""
    return {
        "stocks_added": seed_stock_universe(session),
        "calendar_days_added": seed_market_calendar(session),
    }
