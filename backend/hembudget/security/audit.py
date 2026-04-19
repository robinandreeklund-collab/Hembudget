from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..db.models import AuditLog


def log_action(
    session: Session,
    action: str,
    *,
    user_id: int | None = None,
    meta: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(action=action, user_id=user_id, meta=meta)
    session.add(entry)
    session.flush()
    return entry
