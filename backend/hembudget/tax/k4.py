"""K4 — kapitalvinst/förlust för marknadsnoterade värdepapper.

Beräknas med genomsnittsmetoden: snittanskaffningskurs uppdateras vid köp.
Vid försäljning: vinst = (försäljningspris - snittkostnad × antal sålda) - courtage.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from datetime import date
from typing import Iterable


@dataclass
class Trade:
    date: date
    symbol: str
    qty: Decimal            # positiv = köp, negativ = sälj
    price: Decimal          # pris per enhet
    fee: Decimal = Decimal("0")
    currency: str = "SEK"


@dataclass
class K4Line:
    symbol: str
    total_sold_qty: Decimal
    sale_proceeds: Decimal        # summa försäljningssumma
    acquisition_cost: Decimal     # summa snittkostnad för sålda
    gain: Decimal                 # sale_proceeds - acquisition_cost


@dataclass
class K4Report:
    year: int
    lines: list[K4Line] = field(default_factory=list)
    total_gain: Decimal = Decimal("0")
    total_loss: Decimal = Decimal("0")
    net: Decimal = Decimal("0")


class K4Calculator:
    def compute(self, trades: Iterable[Trade], year: int) -> K4Report:
        holdings: dict[str, tuple[Decimal, Decimal]] = {}  # symbol -> (qty, avg_cost)
        lines_by_symbol: dict[str, K4Line] = {}

        for t in sorted(trades, key=lambda x: x.date):
            qty, avg = holdings.get(t.symbol, (Decimal("0"), Decimal("0")))
            if t.qty > 0:  # buy
                new_qty = qty + t.qty
                total_cost = avg * qty + t.price * t.qty + t.fee
                avg = total_cost / new_qty if new_qty > 0 else Decimal("0")
                holdings[t.symbol] = (new_qty, avg)
            else:  # sell
                sold = -t.qty
                if t.date.year != year:
                    # Still update holdings for history
                    holdings[t.symbol] = (qty - sold, avg)
                    continue
                proceeds = t.price * sold - t.fee
                cost = avg * sold
                line = lines_by_symbol.setdefault(
                    t.symbol,
                    K4Line(
                        symbol=t.symbol,
                        total_sold_qty=Decimal("0"),
                        sale_proceeds=Decimal("0"),
                        acquisition_cost=Decimal("0"),
                        gain=Decimal("0"),
                    ),
                )
                line.total_sold_qty += sold
                line.sale_proceeds += proceeds
                line.acquisition_cost += cost
                line.gain = line.sale_proceeds - line.acquisition_cost
                holdings[t.symbol] = (qty - sold, avg)

        report = K4Report(year=year, lines=list(lines_by_symbol.values()))
        for l in report.lines:
            if l.gain >= 0:
                report.total_gain += l.gain
            else:
                report.total_loss += -l.gain
        report.net = report.total_gain - report.total_loss

        q = Decimal("0.01")
        for l in report.lines:
            l.total_sold_qty = l.total_sold_qty.quantize(Decimal("0.0001"))
            l.sale_proceeds = l.sale_proceeds.quantize(q)
            l.acquisition_cost = l.acquisition_cost.quantize(q)
            l.gain = l.gain.quantize(q)
        report.total_gain = report.total_gain.quantize(q)
        report.total_loss = report.total_loss.quantize(q)
        report.net = report.net.quantize(q)
        return report
