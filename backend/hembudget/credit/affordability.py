"""Affordability-check för planerade transaktioner.

Pedagogiskt syfte: när eleven står i en kassa och ska handla, eller
just klickar 'Skicka in' på en faktura, kan vi ge en tydlig signal
*innan* transaktionen skapas:
  - 'OK, du har råd'
  - 'Saldot räcker inte. Du saknar 8 453 kr — så här kan du lösa det…'

Triggar kreditflödet (privatlån/SMS-lån) först om eleven explicit
väljer det. Vi rekommenderar inget — eleven beslutar.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from ..db.models import Account, Transaction


# Konton där lånet INTE ska triggas (uttag tillåts ej via systemet
# alls — handhas i transfers.py med NEVER_NEGATIVE_KINDS).
NEVER_NEGATIVE_KINDS = {"savings", "isk", "pension"}

# Konton där affordability-check är meningsfull. Lönekontot är det
# centrala. Kreditkortet hanteras separat (credit_limit).
AFFORDABILITY_KINDS = {"checking"}


@dataclass
class AffordabilityResult:
    ok: bool
    current_balance: Decimal
    threshold: Decimal
    shortfall: Decimal     # 0 om ok=True
    explanation: str       # Pedagogisk text på svenska
    account_kind: str


def _balance_for(session: Session, account_id: int) -> Decimal:
    acc = session.get(Account, account_id)
    if acc is None:
        return Decimal("0")
    base = acc.opening_balance or Decimal("0")
    q = session.query(
        sa_func.coalesce(sa_func.sum(Transaction.amount), 0),
    ).filter(Transaction.account_id == account_id)
    if acc.opening_balance_date is not None:
        q = q.filter(Transaction.date >= acc.opening_balance_date)
    total = q.scalar() or Decimal("0")
    if not isinstance(total, Decimal):
        total = Decimal(str(total))
    return base + total


def check_affordability(
    session: Session,
    *,
    account_id: int,
    amount: Decimal,
    threshold: Decimal = Decimal("0"),
) -> AffordabilityResult:
    """Kollar om en planerad utgift på `amount` ryms i kontosaldot.

    `threshold` är en buffert — om kvar-saldo skulle gå under denna
    behandlas det som otillräckligt även om det matematiskt är >0.
    Default 0 kr (matematisk tröskel). Lärare kan höja per elev via
    StudentProfile.credit_buffer_threshold.

    Returnerar pedagogisk explanation även när ok=True (eleven får
    veta hur mycket marginal som finns).
    """
    acc = session.get(Account, account_id)
    if acc is None:
        return AffordabilityResult(
            ok=False, current_balance=Decimal("0"),
            threshold=threshold, shortfall=amount,
            explanation="Kontot saknas.",
            account_kind="unknown",
        )

    balance = _balance_for(session, account_id)
    after = balance - amount

    if acc.type in NEVER_NEGATIVE_KINDS:
        # Sparkonton blockas separat i transfers.py — vi returnerar
        # bara info här.
        if after < 0:
            return AffordabilityResult(
                ok=False, current_balance=balance,
                threshold=Decimal("0"), shortfall=-after,
                explanation=(
                    f"{acc.name} är ett sparkonto och kan inte gå minus. "
                    f"Du har {balance:.0f} kr — du försöker ta ut {amount:.0f} kr."
                ),
                account_kind=acc.type,
            )
        return AffordabilityResult(
            ok=True, current_balance=balance, threshold=Decimal("0"),
            shortfall=Decimal("0"),
            explanation=f"OK. Efter uttaget har du {after:.0f} kr kvar.",
            account_kind=acc.type,
        )

    if acc.type == "credit":
        # Kreditkort har egen logik via credit_limit
        limit = acc.credit_limit or Decimal("0")
        # Hur mycket av krediten är redan utnyttjad?
        # Saldot är negativt vid utnyttjad kredit (vi följer bankkonvention).
        used = max(Decimal("0"), -balance)
        available = limit - used
        if amount > available:
            return AffordabilityResult(
                ok=False, current_balance=balance,
                threshold=Decimal("0"), shortfall=amount - available,
                explanation=(
                    f"Kreditgränsen på {acc.name} är {limit:.0f} kr. "
                    f"Du har redan utnyttjat {used:.0f} kr så bara "
                    f"{available:.0f} kr finns kvar att handla för."
                ),
                account_kind=acc.type,
            )
        return AffordabilityResult(
            ok=True, current_balance=balance, threshold=Decimal("0"),
            shortfall=Decimal("0"),
            explanation=(
                f"OK. {amount:.0f} kr ryms i kreditgränsen "
                f"({available - amount:.0f} kr kvar efter köpet)."
            ),
            account_kind=acc.type,
        )

    # checking och övriga: tillämpa threshold
    if after < threshold:
        shortfall = threshold - after
        if threshold > 0:
            why = (
                f"Du har {balance:.0f} kr på {acc.name}. "
                f"Tar du ut {amount:.0f} kr blir det {after:.0f} kr kvar — "
                f"under din buffert på {threshold:.0f} kr. "
                f"Du saknar alltså {shortfall:.0f} kr för att hålla bufferten."
            )
        else:
            why = (
                f"Du har {balance:.0f} kr på {acc.name}, "
                f"men försöker ta ut {amount:.0f} kr. "
                f"Det går inte ihop — du saknar {shortfall:.0f} kr."
            )
        return AffordabilityResult(
            ok=False, current_balance=balance, threshold=threshold,
            shortfall=shortfall, explanation=why,
            account_kind=acc.type,
        )

    return AffordabilityResult(
        ok=True, current_balance=balance, threshold=threshold,
        shortfall=Decimal("0"),
        explanation=f"OK. Efter uttaget har du {after:.0f} kr kvar.",
        account_kind=acc.type,
    )
