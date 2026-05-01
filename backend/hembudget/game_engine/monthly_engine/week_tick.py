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


def _check_and_create_run(
    student_id: int,
    year_month: str,
    seed_used: Optional[int],
) -> tuple[bool, int]:
    """Atomiskt: om run finns med completed → return (True, id).
    Annars skapa en ny run i status='in_progress' och return (False, id)."""
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
            # in_progress eller failed — låt oss försöka igen
            existing.status = "in_progress"
            existing.started_at = datetime.utcnow()
            existing.error_message = None
            s.commit()
            return False, existing.id
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
) -> TickResult:
    """Kör Monthly Engine för en (student, year_month) idempotent.

    `student` måste vara ett detached/attached Student-objekt (vi läser
    bara id + display_name + family_id). `profile` är resultatet från
    Profile Generator.
    """
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
                )

                summary["fixed"] = generate_fixed_expenses(
                    s,
                    profile=profile,
                    year_month=year_month,
                    student_scope=scope_key,
                    rng=random.Random(rng_master.random()),
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
                )

                # Fas E · oväntade händelser (Sprint 3) — försäkrings-
                # mildring, MailItem, InsuranceClaim, pentagon-impact direkt
                events = roll_monthly_events(
                    s,
                    profile=profile,
                    year_month=year_month,
                    student_scope=scope_key,
                    rng=random.Random(rng_master.random()),
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

                s.commit()
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
