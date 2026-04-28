"""Bygger en MonthScenario-vy från elevens FAKTISKA Transaction-ledger
för en månad. Det här är kärnan i "dynamiskt kontoutdrag":
``render_kontoutdrag(scenario)`` återanvänds som PDF-renderare, men
istället för fiktiva scenario-transaktioner matas faktiska bank-rader
från elevens scope-DB in.

Skillnaden mot tidigare arkitektur:
- TIDIGARE: kontoutdrag-PDF byggdes från scenario.transactions —
  alla återkommande fakturor visades som "redan dragna" innan eleven
  ens hunnit signera dem i banken.
- NU: kontoutdrag-PDF visar HISTORIK — bara det som faktiskt har
  hänt (elevens faktiska Transaction-ledger). Fakturor som eleven
  inte signerat finns kvar som UpcomingTransaction och dyker upp i
  /bank/upcoming-payments tills eleven signerar.

Det matchar verkligheten: en svensk bank skickar inte fakturor som
"redan dragna" i månadsutdraget. Den skickar utdraget med faktiska
händelser, plus separata fakturor att betala.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import and_
from sqlalchemy.orm import Session

from ..db.models import Account, Transaction
from .scenario import MonthScenario, TxEvent


__all__ = ["build_ledger_scenario"]


def build_ledger_scenario(
    s: Session,
    *,
    student_id: int,
    year_month: str,
    bank_account: Account | None = None,
    bank_name: str = "Ekonomilabbet Bank",
    card_name: str = "Ekonomilabbet Kort",
) -> MonthScenario:
    """Konstruera en MonthScenario från elevens faktiska Transaction-rader
    för ``year_month`` på ``bank_account``.

    Om ``bank_account`` inte ges försöker vi hitta första checking-kontot.
    Om inget finns returneras ett tomt scenario med opening_balance=0.

    Opening balance beräknas som account.opening_balance + summan av
    alla transaktioner FÖRE month_start. Ger korrekt löpande saldo i PDF:en.
    """
    year, month = map(int, year_month.split("-"))
    month_start = date(year, month, 1)
    last_day = monthrange(year, month)[1]
    month_end = date(year, month, last_day)

    if bank_account is None:
        bank_account = (
            s.query(Account)
            .filter(Account.type == "checking")
            .order_by(Account.id.asc())
            .first()
        )

    bank_account_no = (
        f"{1000 + (bank_account.id if bank_account else 0):04d}-{student_id:06d}"
    )
    card_account_no = (
        f"4500 1234 5678 {(student_id % 10000):04d}"
    )

    if bank_account is None:
        return MonthScenario(
            year_month=year_month,
            student_id=student_id,
            bank_account_no=bank_account_no,
            card_account_no=card_account_no,
            bank_name=bank_name,
            card_name=card_name,
            opening_balance=Decimal("0"),
        )

    # Opening balance = account.opening_balance + summan av alla TX före månadens start
    pre_month_txs = (
        s.query(Transaction)
        .filter(
            and_(
                Transaction.account_id == bank_account.id,
                Transaction.date < month_start,
            )
        )
        .all()
    )
    opening = Decimal(str(bank_account.opening_balance or 0))
    for t in pre_month_txs:
        opening += Decimal(str(t.amount))

    # Hämta alla TX inom month
    in_month = (
        s.query(Transaction)
        .filter(
            and_(
                Transaction.account_id == bank_account.id,
                Transaction.date >= month_start,
                Transaction.date <= month_end,
            )
        )
        .order_by(Transaction.date.asc(), Transaction.id.asc())
        .all()
    )

    tx_events: list[TxEvent] = []
    for t in in_month:
        tx_events.append(TxEvent(
            date=t.date if isinstance(t.date, date) else _coerce_date(t.date),
            description=t.raw_description or "",
            amount=Decimal(str(t.amount)),
            category_hint="",
        ))

    return MonthScenario(
        year_month=year_month,
        student_id=student_id,
        bank_account_no=bank_account_no,
        card_account_no=card_account_no,
        bank_name=bank_name,
        card_name=card_name,
        salary=None,  # lönen visas via lönespec-PDF separat
        transactions=tx_events,
        card_events=[],  # kortets transaktioner visas i kreditkortsfaktura
        loans=[],
        opening_balance=opening,
    )


def _coerce_date(v) -> date:
    if isinstance(v, date):
        return v
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str):
        return date.fromisoformat(v)
    raise ValueError(f"Cannot coerce {v!r} to date")
