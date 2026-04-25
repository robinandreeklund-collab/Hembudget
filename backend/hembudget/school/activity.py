"""Audit-spår för elev-handlingar i scope-DB.

Endpoints i transactions/budget/loans/imports/transfers anropar
`log_activity(kind, summary, payload=None)` direkt efter en lyckad
ändring. Helper:n läser aktiv elev-id från ContextVar:n som sätts av
StudentScopeMiddleware och skriver en rad till `student_activities`-
tabellen i master-DB.

Designprinciper:
- **Fail-safe.** Om master-DB:n är nere eller ContextVar:n inte är
  satt (t.ex. demo-läge) ska inga undantag bubbla upp och blockera
  själva användarhandlingen. Vi loggar istället till applikations-
  loggen och fortsätter.
- **Inga PII-värden i payload.** Kontonummer, mottagar-namn osv. får
  inte sparas — håll det till siffror, månader och rubriker.
- **School-mode-only.** I desktop-läge finns ingen master-DB; helpern
  blir då en no-op.
"""
from __future__ import annotations

import logging
from typing import Optional

from . import is_enabled as school_enabled
from .engines import get_current_actor_student, master_session
from .models import StudentActivity

log = logging.getLogger(__name__)


def log_activity(
    kind: str,
    summary: str,
    payload: Optional[dict] = None,
    student_id: Optional[int] = None,
) -> None:
    """Skriv en rad i student_activities. Tyst om något går fel.

    `student_id` får anges explicit för fall där middleware:n inte
    körs (tester, batch-jobb). Annars hämtas det från ContextVar.
    """
    if not school_enabled():
        return
    sid = student_id if student_id is not None else get_current_actor_student()
    if sid is None:
        return
    try:
        with master_session() as s:
            s.add(StudentActivity(
                student_id=sid,
                kind=kind,
                summary=summary[:240],
                payload=payload,
            ))
    except Exception:
        log.exception(
            "kunde inte logga StudentActivity (%s) — sväljer fel", kind,
        )
