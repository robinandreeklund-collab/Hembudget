"""School-mode: lärare + elever som egna DB:er.

När HEMBUDGET_SCHOOL_MODE=1 aktiveras:
- En separat "master"-DB håller teacher/student/generation-runs.
- Varje elev har en egen SQLite-fil på disk (school/students/{id}.db).
- Lärare loggar in med e-post + lösen; elever med kort kod.
- Befintliga /transactions, /budget, /ledger osv. fungerar oförändrat —
  men en request-scoped ContextVar styr vilken DB som session_scope()
  öppnar.
"""
from __future__ import annotations

import os


def is_enabled() -> bool:
    return os.environ.get("HEMBUDGET_SCHOOL_MODE", "").lower() in (
        "1", "true", "yes",
    )
