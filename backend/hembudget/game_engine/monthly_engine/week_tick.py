"""M5 · Vecko-tick orchestrator.

Spec: dev/game-motor/03-monthly-engine.md (Idempotens + Lärar-kontroll).

Huvudentry: `tick_month(student, profile, year_month)` som:
  1. Slår upp `WeekTickRun(student_id, year_month)` i master-DB
  2. Om finns och status="completed" → return TickSkipped
  3. Annars: scope_seed → salary_phase → fixed_expenses →
     variable_expenses → markera WeekTickRun.status="completed"
  4. Felfall sätts som status="failed" + error_message så lärare ser

Varje fas gör sitt arbete inuti `scope_context(scope_for_student(...))`
så att tenant_id auto-fylls och rätt SQLite-fil används.
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ...events.engine import tick_for_student as legacy_event_tick
from ...school.engines import (
    get_scope_session,
    master_session,
    scope_context,
    scope_for_student,
)
from ...school.game_engine_models import WeekTickRun
from ...school.models import Student
from ..event_engine import roll_monthly_events
from ..health_engine import roll_monthly_health_events
from ..pentagon import (
    apply_pentagon_delta,
    compute_monthly_drift,
)
from ..profile_generator.schema import GeneratedProfile
from .fixed_expenses import generate_fixed_expenses
from .salary_phase import generate_salary_phase
from .scope_seed import ensure_scope_accounts
from .variable_expenses import generate_variable_expenses

log = logging.getLogger(__name__)


@dataclass
class TickResult:
    student_id: int
    year_month: str
    skipped: bool
    summary: dict


class TickSkipped(Exception):
    """Raises (intern) när year_month redan tickats — fångas av tick_month."""


def _ym_first_day(year_month: str) -> "date":
    """Första dagen i year_month som date — används som sim-datum för
    legacy event tick.
    """
    from datetime import date as _date
    y, m = map(int, year_month.split("-"))
    return _date(y, m, 1)


def _run_pension_transfer(
    s,
    *,
    student,
    lonekonto,
    isk_account,
    year_month: str,
    student_scope: str,
    release_base: Optional[datetime] = None,
) -> dict:
    """Skapar månatlig pension-transfer från lönekonto till ISK om
    eleven har satt custom_isk_monthly i pension-vyn.

    Två transfers skapas (par via transfer_pair_id) på pay-day (25:e):
    - Lönekonto: -X kr (is_transfer=True)
    - ISK: +X kr (is_transfer=True)

    Idempotent via hash. Cash-saldot räknas live i bank-vyn.
    """
    if isk_account is None or lonekonto is None:
        return {"skipped": "no_isk_or_loneconto"}
    from decimal import Decimal as _D
    from ...db.models import Transaction as _Tx, PensionAssumption as _PA
    pa = s.query(_PA).first()
    if pa is None or not pa.custom_isk_monthly:
        return {"skipped": "no_assumption"}
    monthly = int(pa.custom_isk_monthly)
    if monthly <= 0:
        return {"skipped": "zero_amount"}

    from datetime import date as _date_t
    y, m = map(int, year_month.split("-"))
    # Transfer på 25:e (samma dag som lön)
    pay_day = _date_t(y, m, min(25, 28))

    base = (
        f"v2-pension-transfer-{student.id}-{year_month}-{monthly}"
    )
    out_hash = f"transfer-{base}-out"
    in_hash = f"transfer-{base}-in"

    existing = (
        s.query(_Tx).filter(_Tx.hash == out_hash).first()
    )
    if existing is not None:
        return {
            "already_done": True, "amount": monthly,
            "tx_out": existing.id,
        }

    from ..release_schedule import release_at_for_day as _rad
    released_at = (
        _rad(release_base, 25) if release_base is not None else None
    )

    amount = _D(str(monthly))
    out_tx = _Tx(
        account_id=lonekonto.id,
        date=pay_day,
        amount=-amount,
        currency="SEK",
        raw_description=f"Pension-spar till ISK · {monthly} kr/mån",
        normalized_merchant="Avanza ISK",
        is_transfer=True,
        user_verified=True,
        hash=out_hash,
        released_at=released_at,
    )
    in_tx = _Tx(
        account_id=isk_account.id,
        date=pay_day,
        amount=amount,
        currency="SEK",
        raw_description=f"Pension-spar från lönekonto · {monthly} kr/mån",
        normalized_merchant="Lönekonto",
        is_transfer=True,
        user_verified=True,
        hash=in_hash,
        released_at=released_at,
    )
    s.add_all([out_tx, in_tx])
    s.flush()
    out_tx.transfer_pair_id = in_tx.id
    in_tx.transfer_pair_id = out_tx.id
    s.flush()

    return {
        "amount": monthly,
        "tx_out": out_tx.id,
        "tx_in": in_tx.id,
        "pay_day": pay_day.isoformat(),
    }


def _run_legacy_event_tick(
    scope_session,
    *,
    profile: GeneratedProfile,
    year_month: str,
) -> dict:
    """Anropar existerande events.engine.tick_for_student inom samma
    scope-session så social-förslag (StudentEvent) skapas som driver
    wellbeing.calculator (impact_economy/health/social/leisure/safety).

    Felfall fångas och loggas — vi vill inte att en felande social-tick
    ska bryta hela Monthly Engine.
    """
    try:
        with master_session() as ms:
            sim_today = _ym_first_day(year_month)
            result = legacy_event_tick(
                scope_session=scope_session,
                master_session=ms,
                student_seed=profile.seed,
                today=sim_today,
                max_events_per_tick=3,
            )
        return {
            "events_created": result.events_created,
            "candidates_evaluated": result.candidates_evaluated,
            "skipped_reason_counts": result.skipped_reason_counts,
            "tick_date": sim_today.isoformat(),
        }
    except Exception as exc:
        log.exception(
            "monthly_engine: legacy event tick failed för ym=%s", year_month,
        )
        return {
            "events_created": 0,
            "error": str(exc),
        }


def _apply_pentagon_phase(
    scope_session,
    *,
    student_id: int,
    year_month: str,
    event_pentagon_delta: dict[str, int],
) -> dict:
    """Beräkna drift + applicera tröghet + skriv WellbeingEvent-rader.

    Två källor till delta i denna fas:
      1. Oväntade händelser (Fas E) — `event_pentagon_delta`-summa
      2. Månadsdrift (Fas G) — beräknad från beteende

    Båda går genom `apply_pentagon_delta` som klampar med tröghet och
    loggar i master::wellbeing_events.
    """
    drift = compute_monthly_drift(scope_session, year_month=year_month)

    new_values: dict[str, int] = {}
    applied_per_axis: dict[str, dict[str, int]] = {}

    for axis in ("economy", "safety", "health", "social", "leisure"):
        # Event-delta (från Fas E, oväntade händelser)
        ev_delta = int(event_pentagon_delta.get(axis, 0))
        applied_event_delta = 0
        new_value = None
        if ev_delta != 0:
            applied_event_delta, new_value = apply_pentagon_delta(
                student_id,
                axis=axis,
                requested_delta=ev_delta,
                reason_kind="event",
                year_month=year_month,
                explanation="aggregerade händelser denna månad",
            )

        # Drift-delta (från beteende denna månad)
        drift_delta = int(drift.deltas.get(axis, 0))
        applied_drift_delta = 0
        if drift_delta != 0:
            applied_drift_delta, new_value = apply_pentagon_delta(
                student_id,
                axis=axis,
                requested_delta=drift_delta,
                reason_kind="drift",
                year_month=year_month,
                explanation="; ".join(drift.explanations.get(axis, [])) or None,
            )

        applied_per_axis[axis] = {
            "event_requested": ev_delta,
            "event_applied": applied_event_delta,
            "drift_requested": drift_delta,
            "drift_applied": applied_drift_delta,
            "drift_reasons": drift.explanations.get(axis, []),
            "new_value": new_value,
        }
        if new_value is not None:
            new_values[axis] = new_value

    return {
        "by_axis": applied_per_axis,
        "new_values": new_values,
    }


def _check_and_create_run(
    student_id: int,
    year_month: str,
    seed_used: Optional[int],
) -> tuple[bool, int]:
    """Atomiskt: om run finns med completed → return (True, id).
    Annars skapa en ny run i status='in_progress' och return (False, id).

    När en gammal run var failed/in_progress finns delvis-skapade
    transaktioner kvar i scope-DB:n. Vi rensar dem innan retry så att
    samma deterministiska hash inte konfliktar (UNIQUE constraint på
    transactions.tenant_id+hash).
    """
    with master_session() as s:
        existing = (
            s.query(WeekTickRun)
            .filter(
                WeekTickRun.student_id == student_id,
                WeekTickRun.year_month == year_month,
            )
            .one_or_none()
        )
        if existing is not None and existing.status == "completed":
            return True, existing.id
        if existing is not None:
            # Anti-race · om en annan tråd just nu kör samma tick
            # (in_progress, startad inom 5 min) ska vi INTE purge:a
            # och retrya. Då skulle vi rensa partiella data medan
            # andra tråden skapar dem → race + dubbletter.
            if existing.status == "in_progress":
                age_sec = (
                    datetime.utcnow() - existing.started_at
                ).total_seconds() if existing.started_at else 1e9
                if age_sec < 300:
                    # Skipped: en annan tråd håller på, skippa
                    # tyst (returnera 'skipped'-flagga)
                    return True, existing.id
            # in_progress > 5 min eller failed — rensa partiell state
            existing.status = "in_progress"
            existing.started_at = datetime.utcnow()
            existing.error_message = None
            s.commit()
            run_id = existing.id
            # Rensa scope-DB-data från det failade/avbrutna försöket
            from ...school.engines import master_session as _ms
            with _ms() as ms:
                stu = ms.get(Student, student_id)
                if stu is not None:
                    _purge_partial_tick_data(stu, year_month)
            return False, run_id
        run = WeekTickRun(
            student_id=student_id,
            year_month=year_month,
            status="in_progress",
            seed_used=seed_used,
        )
        s.add(run)
        s.commit()
        s.refresh(run)
        return False, run.id


def _purge_partial_tick_data(student: Student, year_month: str) -> None:
    """Rensa transaktioner + mail + events skapade av ett FAILED tick-run
    så vi kan köra om idempotent. year_month = "YYYY-MM".

    Filtrerar på Transaction.date och MailItem.due_date eftersom de
    motsvarar SPEL-månaden. received_at = real-tid när tick körde,
    INTE relevant för att hitta mails från en historisk spel-månad
    (kan ha skapats real-tid 2026-05 men ha due_date 2025-10).
    """
    from datetime import date as _d
    from ...db.models import (
        Account as _Acc, MailItem as _Mail, Transaction as _Tx,
    )
    from ...school.engines import (
        get_scope_session, scope_context, scope_for_student,
    )

    try:
        year = int(year_month[:4])
        month = int(year_month[5:7])
    except (ValueError, IndexError):
        return
    start = _d(year, month, 1)
    end_year = year + (1 if month == 12 else 0)
    end_month = 1 if month == 12 else month + 1
    end = _d(end_year, end_month, 1)

    scope_key = scope_for_student(student)
    maker = get_scope_session(scope_key)
    try:
        with scope_context(scope_key):
            with maker() as s:
                s.query(_Tx).filter(
                    _Tx.date >= start, _Tx.date < end,
                ).delete(synchronize_session=False)
                # Mail · använd due_date för fakturor/lönespec så vi
                # fångar mails från spel-månaden oavsett när de blev
                # 'levererade' i real-tid. Mails utan due_date (info-
                # brev, sociala events) rensas bara om received_at
                # inom real-period (gamla beteendet).
                s.query(_Mail).filter(
                    _Mail.due_date.isnot(None),
                    _Mail.due_date >= start,
                    _Mail.due_date < end,
                ).delete(synchronize_session=False)
                s.query(_Mail).filter(
                    _Mail.due_date.is_(None),
                    _Mail.received_at >= datetime.combine(
                        start, datetime.min.time(),
                    ),
                    _Mail.received_at < datetime.combine(
                        end, datetime.min.time(),
                    ),
                ).delete(synchronize_session=False)
                s.commit()
    except Exception:
        log.exception(
            "_purge_partial_tick_data: rensning misslyckades för "
            "student=%s ym=%s", student.id, year_month,
        )


def _finalize_run(run_id: int, summary: dict, status: str = "completed",
                  error_message: Optional[str] = None) -> None:
    with master_session() as s:
        run = s.get(WeekTickRun, run_id)
        if run is None:
            return
        run.status = status
        run.phase_summary = summary
        run.completed_at = datetime.utcnow()
        if error_message:
            run.error_message = error_message
        s.commit()


def tick_month(
    student: Student,
    profile: GeneratedProfile,
    year_month: str,
    *,
    spend_profile: str = "balanserad",
    starting_level: int = 1,
    release_base: Optional[datetime] = None,
) -> TickResult:
    """Kör Monthly Engine för en (student, year_month) idempotent.

    `student` måste vara ett detached/attached Student-objekt (vi läser
    bara id + display_name + family_id). `profile` är resultatet från
    Profile Generator.

    `release_base`: T0 för realtid-projektion. När satt får varje
    seedat MailItem/Transaction ett `released_at` baserat på spel-dagen
    (1-30) så händelserna dyker upp gradvis i postlådan/banken över
    5 real-dagar (en skolvecka).

    När `release_base` INTE skickas auto-detekterar vi:
    - Historisk year_month (innan innevarande månad) → None, allt
      synligt direkt (förra månaden HAR redan hänt ur elevens
      perspektiv).
    - Innevarande eller framtida year_month → utcnow(), realtid-
      projektion gäller (eleven ska se eventen rulla in över veckan).
    """
    if release_base is None:
        try:
            from datetime import date as _d_now
            today = _d_now.today()
            current_ym = f"{today.year:04d}-{today.month:02d}"
            # Lexikografisk jämförelse fungerar för "YYYY-MM"
            if year_month >= current_ym:
                release_base = datetime.utcnow()
        except Exception:
            pass
    skipped, run_id = _check_and_create_run(
        student.id, year_month, profile.seed,
    )
    if skipped:
        log.info(
            "monthly_engine: tick redan körd för student=%s ym=%s — skippar",
            student.id, year_month,
        )
        return TickResult(
            student_id=student.id,
            year_month=year_month,
            skipped=True,
            summary={"skipped": True, "run_id": run_id},
        )

    scope_key = scope_for_student(student)
    rng_master = random.Random(f"{scope_key}|{year_month}|monthly_engine")

    summary: dict = {"student_id": student.id, "year_month": year_month}

    try:
        # Säkerställ scope-DB-engine + categories existerar (besökt
        # via get_scope_session); sen kör allt i en transaktion.
        maker = get_scope_session(scope_key)
        with scope_context(scope_key):
            with maker() as s:
                accounts = ensure_scope_accounts(s, profile)
                lonekonto = accounts["lonekonto"]

                summary["salary"] = generate_salary_phase(
                    s,
                    profile=profile,
                    year_month=year_month,
                    salary_account=lonekonto,
                    student_scope=scope_key,
                    student_name=student.display_name,
                    release_base=release_base,
                )

                summary["fixed"] = generate_fixed_expenses(
                    s,
                    profile=profile,
                    year_month=year_month,
                    student_scope=scope_key,
                    rng=random.Random(rng_master.random()),
                    release_base=release_base,
                )

                summary["variable"] = generate_variable_expenses(
                    s,
                    profile=profile,
                    year_month=year_month,
                    salary_account=lonekonto,
                    student_scope=scope_key,
                    spend_profile=spend_profile,
                    starting_level=starting_level,
                    rng=random.Random(rng_master.random()),
                    release_base=release_base,
                )

                # Fas D · automatisk pension-transfer från lönekonto
                # till ISK om eleven satt custom_isk_monthly i pension-
                # vyn. Tidigare var custom_isk_monthly bara aspiration —
                # pengar flyttades aldrig faktiskt.
                summary["pension_transfer"] = _run_pension_transfer(
                    s,
                    student=student,
                    lonekonto=lonekonto,
                    isk_account=accounts.get("isk"),
                    year_month=year_month,
                    student_scope=scope_key,
                    release_base=release_base,
                )

                # Fas E · oväntade händelser (Sprint 3) — försäkrings-
                # mildring, MailItem, InsuranceClaim, pentagon-impact direkt
                events = roll_monthly_events(
                    s,
                    profile=profile,
                    year_month=year_month,
                    student_scope=scope_key,
                    rng=random.Random(rng_master.random()),
                    difficulty_level=starting_level,
                    release_base=release_base,
                )
                pentagon_total = {
                    k: 0 for k in ("economy", "safety", "health", "social", "leisure")
                }
                for occ in events:
                    for axis, delta in occ.mitigation.pentagon_impact.as_dict().items():
                        pentagon_total[axis] += delta
                summary["events"] = {
                    "triggered": len(events),
                    "total_cost": sum(
                        max(0, occ.mitigation.effective_cost) for occ in events
                    ),
                    "total_income": sum(
                        max(0, -occ.mitigation.effective_cost)
                        for occ in events
                    ),
                    "mitigated": sum(
                        1 for occ in events if occ.mitigation.mitigation_used
                    ),
                    "pentagon_delta": pentagon_total,
                    "by_template": [
                        {
                            "key": occ.template_key,
                            "display": occ.template_display,
                            "occurred_on": occ.occurred_on.isoformat(),
                            "effective_cost": occ.mitigation.effective_cost,
                            "mitigation": occ.mitigation.mitigation_label,
                            "mail_id": occ.mail_id,
                            "claim_id": occ.claim_id,
                        }
                        for occ in events
                    ],
                }

                # Fas F · social-förslag (existerande events/-modul,
                # Sprint 3 integration). Skapar StudentEvent-rader som
                # eleven kan acceptera/neka — wellbeing.calculator läser
                # accepted+declined per spelmånad och summerar impact_*.
                summary["social_proposals"] = _run_legacy_event_tick(
                    s, profile=profile, year_month=year_month,
                )

                # Fas H · sjukdom + VAB (post-analys steg 1)
                # Slumpa sjukperioder/VAB baserat på Försäkringskassans +
                # Arbetsgivarverkets statistik. Skapar MailItem +
                # löneavdrags-Transaction + pentagon-delta + EmployerSat-event.
                health_events = roll_monthly_health_events(
                    s,
                    student_id=student.id,
                    student_scope=scope_key,
                    profile=profile,
                    year_month=year_month,
                    rng=random.Random(rng_master.random()),
                    salary_account=lonekonto,
                    difficulty_level=starting_level,
                    release_base=release_base,
                )
                summary["health"] = {
                    "episodes": len(health_events),
                    "total_gross_loss": sum(o.gross_loss for o in health_events),
                    "by_episode": [
                        {
                            "key": o.template.key,
                            "display": o.template.display,
                            "kind": o.template.kind,
                            "n_days": o.n_days,
                            "occurred_on": o.occurred_on.isoformat(),
                            "gross_loss": o.gross_loss,
                            "mail_id": o.mail_id,
                            "tx_id": o.tx_id,
                        }
                        for o in health_events
                    ],
                }

                # Fas G · drift + WellbeingEvent-logg (Sprint 4 · M4+P1+P2)
                # Räkna månadsdrift baserat på beteende den månaden +
                # applicera tröghet (max ±5/event, ±12/30d). Pentagon-
                # delta från Fas E (oväntade händelser) och drift loggas
                # i master::wellbeing_events.
                summary["pentagon"] = _apply_pentagon_phase(
                    s,
                    student_id=student.id,
                    year_month=year_month,
                    event_pentagon_delta=pentagon_total,
                )

                # Fas I · biz-tick · OM eleven har företagsläget på OCH
                # ett aktivt bolag finns. Vi kör 4 biz-veckor per privat-
                # månads-tick (eftersom privat tickar en månad åt gången
                # och biz är vecko-baserad). Misslyckas tyst — skall inte
                # ta ner privat-ticken om biz har en bug.
                try:
                    from ...school.engines import master_session as _ms
                    from ...school.models import Student as _Stu
                    with _ms() as ms:
                        stu = ms.get(_Stu, student.id)
                        biz_on = bool(
                            stu and getattr(stu, "business_mode_enabled", False)
                        )
                    if biz_on:
                        from ...business.engine import run_business_week
                        from ...business.models import Company as _Co
                        active_co = (
                            s.query(_Co)
                            .filter(_Co.active.is_(True))
                            .first()
                        )
                        if active_co is not None:
                            biz_summaries = []
                            for _w in range(4):
                                tsum = run_business_week(s, company=active_co)
                                biz_summaries.append({
                                    "week_no": tsum.week_no,
                                    "new_opps": tsum.new_opportunities,
                                    "decided": tsum.quotes_decided,
                                    "accepted": tsum.quotes_accepted,
                                    "rejected": tsum.quotes_rejected,
                                    "paid": tsum.invoices_paid_now,
                                    "events": tsum.events_triggered,
                                    "reputation": tsum.reputation_after,
                                })
                            summary["business"] = {
                                "company_id": active_co.id,
                                "weeks": biz_summaries,
                            }
                except Exception as _biz_exc:
                    log.exception(
                        "biz-tick failed within monthly_engine — privat-tick "
                        "fortsätter ändå (student=%s ym=%s): %s",
                        student.id, year_month, _biz_exc,
                    )
                    summary["business"] = {"error": str(_biz_exc)[:300]}

                s.commit()

                # Persistera wellbeing-snapshot direkt så lärar-vyer
                # kan läsa den i en batched query istället för att
                # räkna om från scratch (20+ queries per elev × N elever
                # i klass-overview blev 1-3 s; med snapshot blir det
                # < 100 ms eftersom alla läses i ETT IN-query).
                try:
                    from ...wellbeing.calculator import (
                        calculate_wellbeing as _calc_wb,
                        persist_wellbeing as _persist_wb,
                    )
                    wb_result = _calc_wb(s, year_month)
                    _persist_wb(s, wb_result)
                    s.commit()
                    summary["wellbeing"] = {
                        "year_month": year_month,
                        "total_score": wb_result.total_score,
                        "persisted": True,
                    }
                except Exception:
                    log.exception(
                        "tick_month: wellbeing-persist failed — "
                        "klass-overview faller tillbaka på live-beräkning",
                    )
                    summary["wellbeing"] = {"persisted": False}
    except Exception as exc:
        log.exception(
            "monthly_engine: tick FAILED för student=%s ym=%s",
            student.id, year_month,
        )
        _finalize_run(run_id, summary, status="failed", error_message=str(exc))
        raise

    _finalize_run(run_id, summary, status="completed")

    return TickResult(
        student_id=student.id,
        year_month=year_month,
        skipped=False,
        summary=summary,
    )
