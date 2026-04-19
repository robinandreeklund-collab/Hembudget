"""ROT/RUT-taggning och summering.

ROT: max 50 000 kr/år (2025) men tillfälligt höjt till 75 000 kr 2024/2025.
Vi använder användarens nuvarande taxkonfig för att vara flexibla.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from ..db.models import TaxEvent, Transaction


@dataclass
class RotRutSummary:
    year: int
    rot_used: Decimal
    rut_used: Decimal
    rot_cap: Decimal
    rut_cap: Decimal
    rot_remaining: Decimal
    rut_remaining: Decimal
    notes: list[str] = field(default_factory=list)


class RotRutService:
    # Kan vara behov att uppdatera över tid; default 2026 siffror.
    DEFAULT_ROT_CAP = Decimal("75000")
    DEFAULT_RUT_CAP = Decimal("75000")

    def __init__(self, session: Session):
        self.session = session

    def tag_transaction(
        self,
        transaction_id: int,
        kind: str,   # "rot" | "rut"
        deduction_amount: Decimal,
    ) -> TaxEvent:
        assert kind in ("rot", "rut")
        tx = self.session.get(Transaction, transaction_id)
        if tx is None:
            raise ValueError(f"Transaction {transaction_id} not found")
        event = TaxEvent(
            type=kind,
            amount=deduction_amount,
            date=tx.date,
            transaction_id=tx.id,
            meta={"merchant": tx.normalized_merchant},
        )
        self.session.add(event)
        self.session.flush()
        return event

    def summary(
        self,
        year: int,
        rot_cap: Decimal | None = None,
        rut_cap: Decimal | None = None,
    ) -> RotRutSummary:
        rot_cap = rot_cap or self.DEFAULT_ROT_CAP
        rut_cap = rut_cap or self.DEFAULT_RUT_CAP

        rot_events = (
            self.session.query(TaxEvent)
            .filter(TaxEvent.type == "rot", TaxEvent.date >= date(year, 1, 1), TaxEvent.date < date(year + 1, 1, 1))
            .all()
        )
        rut_events = (
            self.session.query(TaxEvent)
            .filter(TaxEvent.type == "rut", TaxEvent.date >= date(year, 1, 1), TaxEvent.date < date(year + 1, 1, 1))
            .all()
        )
        rot_used = sum((e.amount for e in rot_events), Decimal("0"))
        rut_used = sum((e.amount for e in rut_events), Decimal("0"))

        notes: list[str] = []
        if rot_used > rot_cap:
            notes.append(f"ROT överskrider tak {rot_cap} kr")
        if rut_used > rut_cap:
            notes.append(f"RUT överskrider tak {rut_cap} kr")

        return RotRutSummary(
            year=year,
            rot_used=rot_used,
            rut_used=rut_used,
            rot_cap=rot_cap,
            rut_cap=rut_cap,
            rot_remaining=max(rot_cap - rot_used, Decimal("0")),
            rut_remaining=max(rut_cap - rut_used, Decimal("0")),
            notes=notes,
        )
