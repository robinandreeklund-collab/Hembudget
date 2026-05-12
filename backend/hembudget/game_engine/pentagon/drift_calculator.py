"""M4 · Pentagon-drift (automatisk månadsvis justering).

Spec: dev/game-motor/07-pentagon-mekanik.md (Drift)

Driften är en pedagogisk konsekvens: "att inte göra något är också ett
val". Vid varje månads-tick beräknar vi en ±5-klampad delta per axel
baserat på elevens beteende den månaden:

  ECONOMY  · sparkvot, obetalda fakturor, aktivt sparmål
  HEALTH   · vårdfakturor, alkohol-relaterade köp
  SAFETY   · kompetens-progression, modul-steg, lönesamtal
  SOCIAL   · accepterade vs nekade social-förslag, engagemang
  LEISURE  · andel av månadens utgifter som går till nöje (sweet spot 10-20%)

Drift returneras som dict {"economy": int, ...} och passar in i
`apply_momentum` + `apply_pentagon_delta`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session


AXES = ("economy", "safety", "health", "social", "leisure")


@dataclass
class DriftResult:
    """Per-axel-drift + förklaring per axel (för Echo + lärar-vy)."""

    deltas: dict[str, int] = field(default_factory=lambda: {a: 0 for a in AXES})
    explanations: dict[str, list[str]] = field(
        default_factory=lambda: {a: [] for a in AXES},
    )

    def add(self, axis: str, delta: int, why: str) -> None:
        self.deltas[axis] += delta
        self.explanations[axis].append(
            f"{'+' if delta >= 0 else ''}{delta}: {why}",
        )

    def clamp_to_max(self, max_per_axis: int = 5) -> None:
        for a in AXES:
            self.deltas[a] = max(-max_per_axis, min(max_per_axis, self.deltas[a]))


def _ym_bounds(year_month: str) -> tuple[date, date]:
    y, m = map(int, year_month.split("-"))
    start = date(y, m, 1)
    if m == 12:
        end = date(y + 1, 1, 1)
    else:
        end = date(y, m + 1, 1)
    return start, end


def _sum_in_month(s: Session, year_month: str, *, sign: str) -> int:
    """Summa över Transaction.amount inom year_month, filtrerad efter
    sign (`positive` = inkomst, `negative` = utgift). Returnerar
    absoluta belopp som int.
    """
    from ...db.models import Transaction
    start, end = _ym_bounds(year_month)
    q = s.query(Transaction).filter(
        Transaction.date >= start, Transaction.date < end,
    )
    rows = q.all()
    if sign == "positive":
        return int(sum((t.amount for t in rows if t.amount and t.amount > 0), Decimal(0)))
    return int(abs(sum((t.amount for t in rows if t.amount and t.amount < 0), Decimal(0))))


def _category_spend_in_month(
    s: Session, year_month: str, category_keywords: tuple[str, ...],
) -> int:
    """Summa utgifter där kategorinamnet innehåller något av nyckelorden."""
    from ...db.models import Category, Transaction
    start, end = _ym_bounds(year_month)
    q = (
        s.query(Transaction)
        .join(Category, Transaction.category_id == Category.id, isouter=True)
        .filter(Transaction.date >= start, Transaction.date < end)
        .filter(Transaction.amount < 0)
    )
    total = 0
    for t in q.all():
        cat = t.category
        if cat is None:
            continue
        name = (cat.name or "").lower()
        if any(kw in name for kw in category_keywords):
            total += int(abs(t.amount or Decimal(0)))
    return total


def _unhandled_invoices_in_month(s: Session, year_month: str) -> int:
    from ...db.models import MailItem
    start, end = _ym_bounds(year_month)
    return (
        s.query(MailItem)
        .filter(
            MailItem.mail_type == "invoice",
            MailItem.due_date >= start,
            MailItem.due_date < end,
            MailItem.status.in_(("unhandled", "viewed")),
        )
        .count()
    )


def _student_event_decisions(s: Session, year_month: str) -> tuple[int, int]:
    """Returnerar (n_accepted, n_declined) för månaden."""
    from ...db.models import StudentEvent
    start, end = _ym_bounds(year_month)
    rows = (
        s.query(StudentEvent)
        .filter(
            StudentEvent.decided_at >= datetime.combine(start, datetime.min.time()),
            StudentEvent.decided_at < datetime.combine(end, datetime.min.time()),
            StudentEvent.status.in_(("accepted", "declined")),
        )
        .all()
    )
    n_accepted = sum(1 for r in rows if r.status == "accepted")
    n_declined = sum(1 for r in rows if r.status == "declined")
    return n_accepted, n_declined


def compute_monthly_drift(
    scope_session: Session,
    *,
    year_month: str,
    has_active_savings_goal: bool = False,
) -> DriftResult:
    """Räkna pentagon-drift för en spelmånad baserat på scope-DB-data.

    Tar `scope_session` redan-bunden till elevens scope. Varje fas har
    en pedagogisk förklaring som loggas i `DriftResult.explanations`.
    """
    result = DriftResult()

    income = _sum_in_month(scope_session, year_month, sign="positive")
    spend = _sum_in_month(scope_session, year_month, sign="negative")

    # === ECONOMY ===
    save = income - spend
    if income > 0:
        save_rate = save / income
        if save_rate >= 0.20:
            result.add("economy", +2, f"sparkvot {save_rate*100:.0f}% (>20%)")
        elif save_rate >= 0.10:
            result.add("economy", +1, f"sparkvot {save_rate*100:.0f}% (>10%)")
        elif save_rate < 0:
            result.add("economy", -3, "spenderade mer än du tjänade")

    unhandled = _unhandled_invoices_in_month(scope_session, year_month)
    if unhandled >= 3:
        result.add("economy", -2, f"{unhandled} obetalda fakturor")

    if has_active_savings_goal:
        result.add("economy", +1, "aktivt sparmål satt")

    # === HEALTH ===
    # Vård + hygien (apotek/tandläkare/1177)
    health_keywords = ("hälsa", "hygien", "vård", "tand", "1177", "apotek")
    health_spend = _category_spend_in_month(
        scope_session, year_month, health_keywords,
    )
    if health_spend >= 2000:
        result.add("health", +1, "investerat i hälsa/vård")

    # Motion · sport · träning · gym · idrott
    # Padelbana, gym, Stadium, simhall, spinning, löparbana, etc.
    sport_keywords = (
        "padel", "gym", "träning", "fitness", "stadium",
        "simhall", "spinning", "yoga", "klätter", "löpning",
        "sats", "friskis", "actic", "nordicwell", "12till12",
        "tennishall", "innebandy", "fotboll", "ishall", "skid",
    )
    sport_spend = _category_spend_in_month(
        scope_session, year_month, sport_keywords,
    )
    if sport_spend >= 200:
        result.add("health", +2, f"motion/sport ({int(sport_spend)} kr)")

    alcohol_kw = ("alkohol", "system", "krog", "bar")
    alcohol_spend = _category_spend_in_month(
        scope_session, year_month, alcohol_kw,
    )
    if alcohol_spend >= 1500:
        result.add("health", -2, f"hög alkoholrelaterad konsumtion ({alcohol_spend} kr)")

    # === SAFETY (karriär + boende) ===
    # Kompetens-progression och modul-steg läses från master-DB i M5-
    # integration; här visar vi bara den scope-baserade delen.
    #
    # Boende-tier-drift · safety påverkas av kvaliteten på elevens
    # boende. Hemlös (terminated/None) slår hårt; lyx-bostad lyfter
    # safety över tid. Skala matchar tier_monthly_safety_drift() i
    # housing_market/rentals.py.
    try:
        from ...db.models import ActiveHome as _ActiveHome
        active_home = (
            scope_session.query(_ActiveHome)
            .filter(_ActiveHome.status.in_(("active", "notice_given")))
            .order_by(_ActiveHome.id.desc())
            .first()
        )
        if active_home is None:
            # Ingen ActiveHome registrerad · betraktas som hemlös /
            # ej satt boende → safety-drift -8 / mån
            result.add(
                "safety", -8,
                "inget registrerat boende · högsta otrygghet",
            )
        else:
            # Härled tier från monthly_cost (storlek + hyra-bracket)
            rent = int(active_home.monthly_cost or 0)
            if rent <= 5000:
                tier = 1
            elif rent <= 9000:
                tier = 2
            elif rent <= 14000:
                tier = 3
            else:
                tier = 4
            drift_map = {1: -2, 2: 0, 3: +1, 4: +2}
            d = drift_map.get(tier, 0)
            if d != 0:
                label = {
                    1: "trångt korridor-/akutboende",
                    2: "litet boende",
                    3: "rymligt familjeboende",
                    4: "lyxbostad",
                }[tier]
                result.add("safety", d, label)
    except Exception:
        # Defensiv · drift får aldrig blockera pentagon-uppdatering
        pass

    # === SOCIAL ===
    n_accept, n_decline = _student_event_decisions(scope_session, year_month)
    total_decisions = n_accept + n_decline
    if total_decisions > 0:
        ratio = n_accept / total_decisions
        if ratio >= 0.6 and total_decisions >= 2:
            result.add("social", +2, f"accepterade {n_accept}/{total_decisions} förslag")
        elif ratio <= 0.2 and n_decline >= 3:
            result.add("social", -2, f"nekade {n_decline}/{total_decisions} förslag")

    # === LEISURE ===
    leisure_keywords = ("nöje", "fritid", "kultur", "sport", "streaming", "bio")
    leisure_spend = _category_spend_in_month(
        scope_session, year_month, leisure_keywords,
    )
    if spend > 0:
        leisure_pct = leisure_spend / spend
        if 0.10 <= leisure_pct <= 0.20:
            result.add("leisure", +1, f"sweet spot {leisure_pct*100:.0f}% nöje av utgifter")
        elif leisure_pct < 0.05:
            result.add("leisure", -2, "mindre än 5% nöje — risk för utbrändhet")
        elif leisure_pct > 0.30:
            result.add("leisure", -2, f"{leisure_pct*100:.0f}% nöje — risk för slöseri")

    result.clamp_to_max(5)
    return result
