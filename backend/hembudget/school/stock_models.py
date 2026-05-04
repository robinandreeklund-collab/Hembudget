"""Master-DB-modeller för aktiekurs-infrastrukturen.

Globalt delade tabeller (samma kurs för alla elever):
- StockMaster — metadata om de 30 tillgängliga aktierna
- StockQuote — append-only historik av kurser (var 5:e min under börstid)
- LatestStockQuote — denormaliserad senaste-pris-tabell för snabb lookup
- MarketCalendar — börstidskalender (öppet/stängt/halvdag) för svenska
  helgdagar

Per-elev-data (StockHolding, StockTransaction, StockWatchlist) ligger
i scope-DB:n i db/models.py.

Importeras från school/models.py så att MasterBase.metadata.create_all()
hittar tabellerna.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .models import MasterBase


class StockMaster(MasterBase):
    """Metadata om en aktie. Seedad en gång (30 OMXS30-aktier).

    Ticker använder Yahoo-format (`VOLV-B.ST`) så data-providern kan
    slå upp direkt. Sektor används i diversifierings-uppdrag.
    """
    __tablename__ = "stock_master"
    __table_args__ = (
        UniqueConstraint("ticker", name="uq_stock_master_ticker"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    name_sv: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    sector: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    isin: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="SEK", nullable=False)
    exchange: Mapped[str] = mapped_column(String(10), default="XSTO", nullable=False)
    active: Mapped[bool] = mapped_column(Integer, default=1, nullable=False)


class StockQuote(MasterBase):
    """Append-only historik av kurser. En rad per polltick (var 5:e min).

    Används för grafer (1d/1w/1m/1y) — tidiga rader downsampleas i
    bakgrund efter 90 dagar för att hålla DB-storleken nere. Lagrar
    `quote_id` på varje StockTransaction så vi kan visa exakt vilken
    kurs som gällde vid affären (revisionsspårbarhet).
    """
    __tablename__ = "stock_quotes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    last: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    bid: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    ask: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    # BigInteger eftersom dagsvolym kan vara > 2^31 (AAPL etc.)
    volume: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    change_pct: Mapped[Optional[float]] = mapped_column(nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="yfinance", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )


class LatestStockQuote(MasterBase):
    """Denormaliserad senaste-pris-tabell. En rad per ticker.

    Uppdateras vid varje polltick. Används för portföljvärdering och
    aktielista-vyn — gör att vi slipper subquery mot stock_quotes."""
    __tablename__ = "latest_stock_quotes"
    __table_args__ = (
        UniqueConstraint("ticker", name="uq_latest_quote_ticker"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    last: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    bid: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    ask: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 4), nullable=True)
    change_pct: Mapped[Optional[float]] = mapped_column(nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    quote_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(),
    )


class MarketCalendar(MasterBase):
    """Börstidskalender. Seedad för innevarande + nästa år.

    status:
      "open"     — vanlig handelsdag
      "closed"   — helgdag eller helg
      "half_day" — kort dag (sällsynt; används inte för svenska börsen
                   i V1 men finns för framtida bruk)
    """
    __tablename__ = "market_calendar"
    __table_args__ = (
        UniqueConstraint("calendar_date", "exchange", name="uq_market_cal_date_ex"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    calendar_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    exchange: Mapped[str] = mapped_column(String(10), default="XSTO", nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    open_time: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    close_time: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)


class FxRate(MasterBase):
    """Append-only valutakurshistorik. Append vid varje stock-poll.

    rate = SEK per 1 enhet av base. T.ex. base='USD' → rate=10.50
    betyder 1 USD = 10.50 SEK. Vi kör USD/SEK i V1; CAD/EUR/GBP kan
    läggas till senare.
    """
    __tablename__ = "fx_rates"
    __table_args__ = (
        UniqueConstraint("base", "ts", name="uq_fx_base_ts"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    base: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    quote: Mapped[str] = mapped_column(
        String(8), default="SEK", nullable=False,
    )
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    rate: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    source: Mapped[str] = mapped_column(
        String(20), default="yfinance", nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(),
    )


class LatestFxRate(MasterBase):
    """Denormaliserad senaste kurs per valutapar — undviker subquery."""
    __tablename__ = "latest_fx_rates"
    __table_args__ = (
        UniqueConstraint("base", "quote", name="uq_latest_fx_pair"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    base: Mapped[str] = mapped_column(String(8), nullable=False)
    quote: Mapped[str] = mapped_column(
        String(8), default="SEK", nullable=False,
    )
    rate: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(),
    )
