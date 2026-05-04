"""Monthly Engine · vecko-tick som genererar lön, fakturor och variabla
utgifter per spelmånad.

Spec: dev/game-motor/03-monthly-engine.md

Pipeline per (student, year_month):
  1. Säkerställ scope-DB-konton (lönekonto, sparkonto, ev. kreditkort)
  2. Fas A · Salary phase   — lönespec + lön-in-transaktion
  3. Fas B · Fixed expenses — staggered fakturor dag 1-10
  4. Fas C · Variable expenses — Konsumentverket × spend_profile
  5. Logga `WeekTickRun(student_id, year_month, ...)` i master-DB

Idempotent: re-tick av samma year_month är no-op (kollar WeekTickRun
innan något skapas).
"""
from .week_tick import (
    TickResult,
    TickSkipped,
    tick_month,
)
from .salary_phase import generate_salary_phase
from .fixed_expenses import generate_fixed_expenses
from .variable_expenses import generate_variable_expenses
from .scope_seed import ensure_scope_accounts

__all__ = [
    "TickResult",
    "TickSkipped",
    "tick_month",
    "generate_salary_phase",
    "generate_fixed_expenses",
    "generate_variable_expenses",
    "ensure_scope_accounts",
]
