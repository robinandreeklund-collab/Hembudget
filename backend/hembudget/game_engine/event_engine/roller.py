"""E4 · Event-roller och appliering per spelmånad.

Spec: dev/game-motor/04-event-engine.md (Daglig tick)

För Sprint 3 implementerar vi MÅNADS-tick (snarare än daglig). Logiken:

  1. För varje template: räkna chans = frequency_per_year / 12
  2. Slumpa om eventet ska triggas (rng.random() < chans)
  3. Filtrera bort templates där age_range / family_status_filter inte
     matchar profilen
  4. Klamp: max 3 events per månad så elev inte överbelastas
  5. Apply_mitigation per event → MailItem + ev. InsuranceClaim

Daglig tick (= specifika dagar i månaden) tas i Sprint 4 (M6 cron).
"""
from __future__ import annotations

import hashlib
import logging
import random
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from ...db.models import InsuranceClaim, InsurancePolicy, MailItem
from ..difficulty import DifficultyProfile, get_difficulty
from ..profile_generator.schema import GeneratedProfile
from ..release_schedule import release_at_for_day
from .mitigation import MitigationResult, apply_mitigation
from .templates import EVENT_BY_KEY, EVENT_TEMPLATES, EventTemplate

log = logging.getLogger(__name__)

MAX_EVENTS_PER_MONTH = 3


@dataclass
class EventOccurrence:
    """En triggad händelse + dess mitigation-resultat och DB-spår."""

    template_key: str
    template_display: str
    occurred_on: date
    mitigation: MitigationResult
    mail_id: int
    claim_id: Optional[int]


# === Filter ===


def _template_matches_profile(
    template: EventTemplate,
    profile: GeneratedProfile,
) -> bool:
    age = profile.facts.get("age", 30)
    if not (template.age_range[0] <= age <= template.age_range[1]):
        return False
    if template.family_status_filter:
        if profile.family.status not in template.family_status_filter:
            return False
    return True


def _eligible_templates(profile: GeneratedProfile) -> list[EventTemplate]:
    return [
        t for t in EVENT_TEMPLATES
        if t.active and _template_matches_profile(t, profile)
    ]


# === Roller ===


def _stable_hash(scope: str, year_month: str, key: str) -> str:
    raw = f"{scope}|{year_month}|event|{key}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _ym_to_date(year_month: str, day: int) -> date:
    y, m = map(int, year_month.split("-"))
    return date(y, m, min(day, 28))


def _build_mail(
    *,
    template: EventTemplate,
    mit: MitigationResult,
    occurred_on: date,
    year_month: str,
    released_at: Optional[datetime] = None,
) -> MailItem:
    """Bygger MailItem för ett triggat event.

    Beloppet är negativt = utgift; positivt = inkomst (ovanligt format
    sett från MailItem som annars bara tar negativa belopp). Vi följer
    konventionen i db.models.MailItem (`amount` signed)."""
    cost = mit.effective_cost
    is_income = cost < 0  # cost_range gav negativt belopp = bonus etc
    if is_income:
        amount = Decimal(-cost)  # Income = positivt mail-amount
        mail_type = "info"
    elif cost == 0:
        amount = None
        mail_type = "info"
    else:
        amount = Decimal(-cost)  # Expense = negativt mail-amount
        mail_type = "invoice"

    body_lines = [
        template.display,
        "",
        template.description,
        "",
    ]
    if mit.mitigation_used and mit.mitigation_label:
        body_lines.append(f"Försäkringsmildring: {mit.mitigation_label}")
        body_lines.append(
            f"Räknat på orginalbelopp {mit.base_cost:,} kr "
            f"→ du betalar {mit.effective_cost:,} kr".replace(",", " ")
        )
    elif cost > 0:
        body_lines.append(
            f"Belopp: {cost:,} kr".replace(",", " "),
        )
    if template.echo_trigger:
        body_lines.append("")
        body_lines.append(f"Echo: {template.echo_trigger}")

    # Svensk standard · faktura/bot kommer 3-7 dagar EFTER händelsen
    # och har 30 dagars betalningstid från fakturadatum. Tidigare hade
    # vi due_date == occurred_on == received_at, alltså 0 dagar
    # förfallotid (helt orimligt). Parkeringsbot 7 jan → bot kommer
    # ~10 jan, ska betalas senast ~10 feb.
    from datetime import datetime as _dt_ev, time as _time_ev, timedelta as _td_ev
    payment_terms_days = getattr(template, "payment_terms_days", None) or 30
    invoice_arrival_days = 3 if cost > 0 else 0  # bot kommer snabbt; info-mail same-day
    invoice_received_on = occurred_on + _td_ev(days=invoice_arrival_days)
    due_d = (
        invoice_received_on + _td_ev(days=payment_terms_days)
        if (cost or 0) > 0 else None
    )

    return MailItem(
        sender=template.sender,
        sender_short=template.sender_short,
        sender_kind=template.sender_kind,
        sender_meta=f"händelse · {occurred_on.isoformat()}",
        mail_type=mail_type,
        subject=template.display,
        body_meta=(
            f"Försäkring täckte" if mit.mitigation_used
            else (
                f"Inkomst {-cost:,} kr".replace(",", " ") if is_income
                else (
                    f"Belopp {cost:,} kr".replace(",", " ") if cost > 0
                    else "Information"
                )
            )
        ),
        body="\n".join(body_lines),
        amount=amount,
        due_date=due_d,
        status="unhandled",
        released_at=released_at,
        # received_at = SPEL-tid · annars stämplas alla event-mail med
        # real-tid (utcnow) vid seed-körning och eleven ser "7 maj"
        # i postlådan trots att händelsen är i januari.
        received_at=_dt_ev.combine(
            invoice_received_on,
            _time_ev(10, 0),
        ),
    )


def _maybe_insurance_claim(
    *,
    mit: MitigationResult,
    occurred_on: date,
    template: EventTemplate,
) -> Optional[InsuranceClaim]:
    """Om mitigation användes → skapa InsuranceClaim för audit-trail.
    Om INGEN policy fanns men eventet hade mitigations → no_policy claim
    så lärare kan visa "denne elev hade kunnat skydda sig"."""
    has_mitigations = bool(template.mitigations)
    if not has_mitigations or mit.base_cost <= 0:
        return None

    if mit.mitigation_used and mit.policy_id is not None:
        return InsuranceClaim(
            occurred_on=occurred_on,
            policy_id=mit.policy_id,
            kind=template.kind if template.kind in (
                "stold", "olycka", "skada", "vattenskada", "brand",
            ) else "skada",
            title=template.display,
            description=mit.mitigation_label,
            amount_claimed=Decimal(mit.base_cost),
            amount_paid=Decimal(mit.base_cost - mit.effective_cost),
            status="paid",
            paid_at=occurred_on,
            no_policy=False,
        )

    # Oskyddat — skapa info-claim
    return InsuranceClaim(
        occurred_on=occurred_on,
        policy_id=None,
        kind="skada",
        title=template.display,
        description="Hade ingen relevant försäkring vid händelsen.",
        amount_claimed=Decimal(mit.base_cost),
        amount_paid=Decimal(0),
        status="info",
        no_policy=True,
    )


def apply_event(
    s: Session,
    *,
    template: EventTemplate,
    profile: GeneratedProfile,
    year_month: str,
    student_scope: str,
    rng: random.Random,
    base_cost_override: Optional[int] = None,
    difficulty_level: int = 2,
    release_base: Optional[datetime] = None,
) -> EventOccurrence:
    """Applicera ETT event för en elev i en spelmånad.

    Används både av roller (slumpade events) och av lärar-injektionen
    (manuellt valda events). `base_cost_override` tillåter läraren att
    sätta exakt belopp.

    `difficulty_level` (1-3) skalar utgifts-events: nivå 3 = dyrare
    tandläkare/vattenskada. Inkomst-events oförändrade.
    """
    diff = get_difficulty(difficulty_level)

    # Slumpa kostnad
    if base_cost_override is not None:
        base_cost = base_cost_override
    elif template.cost_range[0] == template.cost_range[1] == 0:
        base_cost = 0
    else:
        lo, hi = template.cost_range
        # Säkerhetsklamp om någon definierar fel ordning
        if lo > hi:
            lo, hi = hi, lo
        base_cost = rng.randint(lo, hi)
        # Difficulty-skalning för utgifter (positiva belopp).
        # Inkomster (negativa) behålls oförändrade.
        if base_cost > 0 and diff.event_cost_mult != 1.0:
            base_cost = int(base_cost * diff.event_cost_mult)

    # Lookup elevens policys + buffer
    policies = s.query(InsurancePolicy).all()
    # För Sprint 3: vi har ingen direkt link till sparkontot här;
    # sätt savings_buffer = 0 (förbättras i Sprint 4 med kontosaldo).
    mit = apply_mitigation(template, base_cost, policies, savings_buffer=0)

    # Slumpa dag i månaden
    day = rng.randint(1, 28)
    occurred = _ym_to_date(year_month, day)

    released_at = (
        release_at_for_day(release_base, day)
        if release_base is not None
        else None
    )
    mail = _build_mail(
        template=template,
        mit=mit,
        occurred_on=occurred,
        year_month=year_month,
        released_at=released_at,
    )
    # Stable hash via OCR-ref för pseudo-dedup
    mail.ocr_reference = _stable_hash(
        student_scope, year_month, template.key,
    )[:18]
    s.add(mail)
    s.flush()

    claim = _maybe_insurance_claim(
        mit=mit, occurred_on=occurred, template=template,
    )
    claim_id: Optional[int] = None
    if claim is not None:
        s.add(claim)
        s.flush()
        claim_id = claim.id
        # Försäkringsutbetalning · skapa Transaction på elevens lönekonto
        # så pengarna faktiskt landar på saldot. Annars syns
        # utbetalningen bara i /v2/forsakringar utan att påverka kontot.
        if (
            claim.status == "paid"
            and claim.amount_paid is not None
            and claim.amount_paid > 0
        ):
            try:
                from ...db.models import Account, Transaction
                import hashlib as _hl_ins
                lonekonto = (
                    s.query(Account)
                    .filter(Account.type == "checking")
                    .order_by(Account.id.asc())
                    .first()
                )
                if lonekonto is not None:
                    desc = (
                        f"Försäkringsutbetalning · {template.display}"
                    )
                    tx_hash = _hl_ins.sha256(
                        f"claim|{student_scope}|{template.key}|"
                        f"{occurred.isoformat()}|{int(claim.amount_paid)}".encode()
                    ).hexdigest()[:32]
                    tx = Transaction(
                        account_id=lonekonto.id,
                        date=occurred,
                        amount=Decimal(claim.amount_paid),  # positivt
                        currency="SEK",
                        raw_description=desc,
                        normalized_merchant=(
                            "Folksam" if "folksam" in (
                                template.key or ""
                            ).lower() else "Försäkringsbolaget"
                        ),
                        hash=tx_hash,
                        is_transfer=False,
                        user_verified=True,
                    )
                    s.add(tx)
                    s.flush()
            except Exception:
                import logging
                logging.getLogger(__name__).exception(
                    "claim → Transaction misslyckades — sväljer",
                )

    return EventOccurrence(
        template_key=template.key,
        template_display=template.display,
        occurred_on=occurred,
        mitigation=mit,
        mail_id=mail.id,
        claim_id=claim_id,
    )


def roll_monthly_events(
    s: Session,
    *,
    profile: GeneratedProfile,
    year_month: str,
    student_scope: str,
    rng: Optional[random.Random] = None,
    max_events: Optional[int] = None,
    difficulty_level: int = 2,
    release_base: Optional[datetime] = None,
) -> list[EventOccurrence]:
    """Slumpa vilka events som triggas och applicera dem.

    Algoritm:
      1. Filtrera till profil-matchande templates
      2. Per template: trigger om rng.random() < (frequency/12 × diff-mult)
      3. Klamp totalt antal till max_events (sortera efter
         pentagon_unmitigated.economy abs så största händelser prioriteras)

    `difficulty_level` skalar både frekvens (event_frequency_mult) och
    cap (max_events_per_month). Default 2 = neutralt baseline.
    """
    rng = rng or random.Random(f"{student_scope}|{year_month}|events")
    diff = get_difficulty(difficulty_level)
    if max_events is None:
        max_events = diff.max_events_per_month
    eligible = _eligible_templates(profile)

    triggered: list[EventTemplate] = []
    for t in eligible:
        chance = (t.frequency_per_year / 12.0) * diff.event_frequency_mult
        if rng.random() < chance:
            triggered.append(t)

    if len(triggered) > max_events:
        triggered.sort(
            key=lambda x: abs(x.pentagon_unmitigated.economy)
            + abs(x.pentagon_unmitigated.safety),
            reverse=True,
        )
        triggered = triggered[:max_events]

    occurrences: list[EventOccurrence] = []
    for t in triggered:
        try:
            occ = apply_event(
                s,
                template=t,
                profile=profile,
                year_month=year_month,
                student_scope=student_scope,
                rng=rng,
                difficulty_level=difficulty_level,
                release_base=release_base,
            )
            occurrences.append(occ)
        except Exception:
            log.exception("event_engine: apply_event failed för %s", t.key)

    return occurrences
