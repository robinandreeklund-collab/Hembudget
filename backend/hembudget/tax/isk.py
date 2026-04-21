"""ISK-schablonbeskattning.

Skatteunderlag = (IB + insättningar + värdet vid varje kvartals ingång) / 4 × schablonränta
Schablonränta = statslåneränta 30 nov föregående år + 1 procentenhet, minst 1,25 %.
Skatt = underlag × 30 %.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Iterable

MIN_SCHABLON_RATE = Decimal("0.0125")
SCHABLON_ADDON = Decimal("0.01")   # + 1 procentenhet
CAPITAL_TAX_RATE = Decimal("0.30")


@dataclass
class ISKQuarterValue:
    quarter: int     # 1..4 (start of quarter)
    value: Decimal   # kapital på kontots värde vid kvartalets ingång


@dataclass
class ISKYearData:
    year: int
    opening_balance: Decimal
    deposits: Decimal                 # summa insättningar under året
    quarter_values: list[ISKQuarterValue]
    statslaneranta_30_nov: Decimal    # föregående år per 30/11


@dataclass
class ISKResult:
    year: int
    underlag: Decimal
    schablonrate: Decimal
    schablonintakt: Decimal
    skatt: Decimal
    notes: list[str] = field(default_factory=list)


class ISKCalculator:
    def compute(self, data: ISKYearData) -> ISKResult:
        notes: list[str] = []
        rate = data.statslaneranta_30_nov + SCHABLON_ADDON
        if rate < MIN_SCHABLON_RATE:
            rate = MIN_SCHABLON_RATE
            notes.append("Golv 1,25 % tillämpat")
        # Kapitalunderlag = (IB + insättningar + Q1 + Q2 + Q3 + Q4) / 4
        quarter_sum = sum((q.value for q in data.quarter_values), Decimal("0"))
        underlag = (data.opening_balance + data.deposits + quarter_sum) / Decimal("4")
        schablonintakt = underlag * rate
        skatt = schablonintakt * CAPITAL_TAX_RATE
        q = Decimal("0.01")
        return ISKResult(
            year=data.year,
            underlag=underlag.quantize(q),
            schablonrate=rate.quantize(Decimal("0.000001")),
            schablonintakt=schablonintakt.quantize(q),
            skatt=skatt.quantize(q),
            notes=notes,
        )

    @staticmethod
    def from_transactions(
        year: int,
        opening_balance: Decimal,
        isk_transactions: Iterable,
        quarter_values: Iterable[ISKQuarterValue],
        statslaneranta_30_nov: Decimal,
    ) -> ISKYearData:
        deposits = sum(
            (Decimal(str(t.amount)) for t in isk_transactions if Decimal(str(t.amount)) > 0),
            Decimal("0"),
        )
        return ISKYearData(
            year=year,
            opening_balance=opening_balance,
            deposits=deposits,
            quarter_values=list(quarter_values),
            statslaneranta_30_nov=statslaneranta_30_nov,
        )
