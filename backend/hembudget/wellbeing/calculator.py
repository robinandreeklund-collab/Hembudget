"""Wellbeing-beräkningsmotor.

Beräknar 5-dimensionell Wellbeing-Score (0-100) baserat på elevens
ekonomi i scope-DB:n. I fas 1 räknar vi BARA på ekonomiska faktorer:
- budget vs Konsumentverket-minimum (Mat & hälsa-dimensionen)
- saldo + skuld + sparande (Ekonomi + Trygghet)
- buffert (Trygghet)

Sociala/Fritid-dimensionerna ligger på neutral 50 i fas 1 — fylls i
av events i fas 3 (StudentEvent).

Pedagogiskt: ALLA bidrag är transparenta. Det ska gå att räkna efter
poängen själv genom att läsa explanation-texten.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from ..db.models import Account, Budget, Loan, Transaction, WellbeingScore
from .minimums import check_against_minimum


@dataclass
class WellbeingFactor:
    """En enskild bidragspost — pedagogiskt transparent."""
    dimension: str       # "economy" | "health" | "social" | "leisure" | "safety"
    points: int          # Bidrag till dimensionen (kan vara negativt)
    explanation: str     # Pedagogisk text


@dataclass
class WellbeingResult:
    year_month: str
    total_score: int = 50
    economy: int = 50
    health: int = 50
    social: int = 50
    leisure: int = 50
    safety: int = 50
    factors: list[WellbeingFactor] = field(default_factory=list)
    events_accepted: int = 0
    events_declined: int = 0
    budget_violations: int = 0

    @property
    def explanation(self) -> str:
        """Sammanfattande text för UI:t — listar de viktigaste
        bidragen i klartext."""
        if not self.factors:
            return "Ingen aktivitet att bedöma än."
        # Sortera mest påverkande först
        ranked = sorted(self.factors, key=lambda f: -abs(f.points))[:5]
        lines = [
            f"Wellbeing: {self.total_score}/100 — viktigaste bidragen:"
        ]
        for f in ranked:
            sign = "+" if f.points >= 0 else ""
            lines.append(f"• {f.dimension} ({sign}{f.points} p): {f.explanation}")
        return "\n".join(lines)


def _saldo_for(session: Session, account_id: int) -> Decimal:
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


def _checking_balance(session: Session) -> Decimal:
    """Total saldo över alla checking-konton."""
    accs = session.query(Account).filter(Account.type == "checking").all()
    return sum((_saldo_for(session, a.id) for a in accs), Decimal("0"))


def _savings_balance(session: Session) -> Decimal:
    """Total saldo över alla sparkonton + ISK."""
    accs = (
        session.query(Account)
        .filter(Account.type.in_({"savings", "isk"}))
        .all()
    )
    return sum((_saldo_for(session, a.id) for a in accs), Decimal("0"))


def _total_active_debt(session: Session) -> Decimal:
    total = (
        session.query(sa_func.coalesce(sa_func.sum(Loan.principal_amount), 0))
        .filter(Loan.active.is_(True))
        .scalar() or Decimal("0")
    )
    return Decimal(str(total)) if not isinstance(total, Decimal) else total


def _high_cost_credit_count(session: Session) -> int:
    # Skydda mot prod-Postgres som ännu saknar kolumnen (migration ej körd).
    # Wellbeing-räkning får inte krascha — då tar den ner hela dashboarden.
    from ..school.engines import scope_has_column
    if not scope_has_column("loans", "is_high_cost_credit"):
        return 0
    try:
        return (
            session.query(Loan)
            .filter(Loan.active.is_(True), Loan.is_high_cost_credit.is_(True))
            .count()
        )
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "_high_cost_credit_count: SELECT misslyckades — returnerar 0",
        )
        try:
            session.rollback()
        except Exception:
            pass
        return 0


def _budget_violations(session: Session, year_month: str) -> tuple[int, list[str]]:
    """Kollar elevens budget för denna månad mot Konsumentverket. Returnerar
    (antal_violations, lista_av_categorinamn) — kategorinamn behövs i UI."""
    from ..db.models import Category
    rows = (
        session.query(Budget, Category.name)
        .join(Category, Category.id == Budget.category_id)
        .filter(Budget.month == year_month)
        .all()
    )
    violations: list[str] = []
    for b, cat_name in rows:
        check = check_against_minimum(cat_name, int(b.planned_amount))
        if check.is_violation:
            violations.append(cat_name)
    return len(violations), violations


def calculate_wellbeing(session: Session, year_month: str) -> WellbeingResult:
    """Beräkna Wellbeing för en given månad.

    Fas 1: bara ekonomiska faktorer. Fas 3 lägger till events.
    """
    result = WellbeingResult(year_month=year_month)
    factors: list[WellbeingFactor] = []

    # --- EKONOMI-DIMENSION ---
    has_checking = (
        session.query(Account).filter(Account.type == "checking").count() > 0
    )
    checking = _checking_balance(session) if has_checking else None
    debt = _total_active_debt(session)
    high_cost = _high_cost_credit_count(session)

    economy = 50
    if checking is not None:
        if checking < 0:
            delta = -25
            economy += delta
            factors.append(WellbeingFactor(
                "economy", delta,
                f"Lönekontot ligger på {int(checking):,} kr — minus räknas hårt.".replace(",", " "),
            ))
        elif checking < 1_000:
            delta = -10
            economy += delta
            factors.append(WellbeingFactor(
                "economy", delta,
                f"Lönekonto under 1 000 kr — väldigt liten marginal.",
            ))
        elif checking >= 10_000:
            delta = 10
            economy += delta
            factors.append(WellbeingFactor(
                "economy", delta,
                f"Lönekonto på {int(checking):,} kr — bra marginal.".replace(",", " "),
            ))

    if high_cost > 0:
        delta = -20 * high_cost
        economy += delta
        factors.append(WellbeingFactor(
            "economy", delta,
            f"Du har {high_cost} aktivt SMS-/snabblån — högkostnadskredit "
            "äter upp ekonomin.",
        ))

    # --- TRYGGHET-DIMENSION ---
    has_savings = (
        session.query(Account)
        .filter(Account.type.in_({"savings", "isk"}))
        .count() > 0
    )
    savings = _savings_balance(session) if has_savings else Decimal("0")
    safety = 50
    if not has_savings:
        # Inga sparkonton — vi vet inte, lämna neutral
        pass
    elif savings >= 50_000:
        delta = 25
        safety += delta
        factors.append(WellbeingFactor(
            "safety", delta,
            f"Buffert på {int(savings):,} kr — välbalansat — räcker långt vid kris.".replace(",", " "),
        ))
    elif savings >= 25_000:
        delta = 15
        safety += delta
        factors.append(WellbeingFactor(
            "safety", delta,
            f"Buffert på {int(savings):,} kr — räcker en månads inkomst, ok start.".replace(",", " "),
        ))
    elif savings >= 10_000:
        delta = 5
        safety += delta
        factors.append(WellbeingFactor(
            "safety", delta,
            f"Buffert på {int(savings):,} kr — något att gripa om vid akut kostnad.".replace(",", " "),
        ))
    elif savings < 5_000:
        delta = -15
        safety += delta
        factors.append(WellbeingFactor(
            "safety", delta,
            f"Buffert bara {int(savings):,} kr — en oväntad räkning slår hårt.".replace(",", " "),
        ))

    if debt > 0:
        # Skuldkvot mot ungefärlig årsinkomst — använd checking som proxy
        # i fas 1 (vi har inte salaries-rapport här).
        # Hård gräns vid 100 000 kr i skuld utan motsvarande sparande.
        if debt > savings + 100_000:
            delta = -10
            safety += delta
            factors.append(WellbeingFactor(
                "safety", delta,
                f"Skuld {int(debt):,} kr utan motsvarande buffert — sårbar position.".replace(",", " "),
            ))

    # --- HÄLSA-DIMENSION (budget vs minimum) ---
    health = 50
    n_violations, violation_cats = _budget_violations(session, year_month)
    if n_violations > 0:
        delta = -5 * n_violations
        health += delta
        cat_str = ", ".join(violation_cats[:3])
        factors.append(WellbeingFactor(
            "health", delta,
            f"{n_violations} budget(ar) under Konsumentverket-minimum "
            f"({cat_str}). −5 p per kategori.",
        ))
    elif rows_total := (
        session.query(Budget).filter(Budget.month == year_month).count()
    ):
        # Om budget är satt och allt är ok → liten positiv signal
        delta = 5
        health += delta
        factors.append(WellbeingFactor(
            "health", delta,
            f"Du har en realistisk budget i nivå med Konsumentverket — bra grund.",
        ))

    # --- SOCIAL + FRITID (V2: events räknas in från fas 3) ---
    from ..db.models import StudentEvent
    # Hämta events beslutade denna månad (accepted+declined räknas)
    from datetime import datetime as _dt
    y, m = year_month.split("-")
    month_start = date(int(y), int(m), 1)
    if int(m) == 12:
        month_end = date(int(y) + 1, 1, 1)
    else:
        month_end = date(int(y), int(m) + 1, 1)

    decided_events = (
        session.query(StudentEvent)
        .filter(
            StudentEvent.decided_at >= _dt.combine(month_start, _dt.min.time()),
            StudentEvent.decided_at < _dt.combine(month_end, _dt.min.time()),
            StudentEvent.status.in_({"accepted", "declined"}),
        )
        .all()
    )
    n_accepted = sum(1 for e in decided_events if e.status == "accepted")
    n_declined = sum(1 for e in decided_events if e.status == "declined")

    social = 50
    leisure = 50
    for e in decided_events:
        impact = e.impact_applied or {}
        social += int(impact.get("social", 0))
        leisure += int(impact.get("leisure", 0))

    if n_accepted + n_declined > 0:
        ratio_accept = n_accepted / max(1, n_accepted + n_declined)
        if ratio_accept >= 0.6:
            factors.append(WellbeingFactor(
                "social",
                +5,
                f"Du accepterade {n_accepted} av {n_accepted + n_declined} "
                "förslag denna månad — engagerad social aktivitet.",
            ))
            social += 5
        elif ratio_accept <= 0.2 and n_declined >= 3:
            factors.append(WellbeingFactor(
                "social",
                -5,
                f"Du nekade {n_declined} av {n_accepted + n_declined} "
                "förslag — isolering har en kostnad.",
            ))
            social -= 5

    # --- KLAMP + TOTAL ---
    economy = max(0, min(100, economy))
    health = max(0, min(100, health))
    social = max(0, min(100, social))
    leisure = max(0, min(100, leisure))
    safety = max(0, min(100, safety))
    total = (economy + health + social + leisure + safety) // 5

    result.economy = economy
    result.health = health
    result.social = social
    result.leisure = leisure
    result.safety = safety
    result.total_score = total
    result.factors = factors
    result.budget_violations = n_violations
    result.events_accepted = n_accepted
    result.events_declined = n_declined
    return result


def persist_wellbeing(session: Session, result: WellbeingResult) -> WellbeingScore:
    """Spara/uppsert WellbeingScore-rad för en månad. Idempotent."""
    existing = (
        session.query(WellbeingScore)
        .filter(WellbeingScore.year_month == result.year_month)
        .first()
    )
    if existing is None:
        row = WellbeingScore(
            year_month=result.year_month,
            total_score=result.total_score,
            economy=result.economy,
            health=result.health,
            social=result.social,
            leisure=result.leisure,
            safety=result.safety,
            events_accepted=result.events_accepted,
            events_declined=result.events_declined,
            budget_violations=result.budget_violations,
            explanation=result.explanation,
        )
        session.add(row)
    else:
        existing.total_score = result.total_score
        existing.economy = result.economy
        existing.health = result.health
        existing.social = result.social
        existing.leisure = result.leisure
        existing.safety = result.safety
        existing.events_accepted = result.events_accepted
        existing.events_declined = result.events_declined
        existing.budget_violations = result.budget_violations
        existing.explanation = result.explanation
        row = existing
    session.flush()
    return row
