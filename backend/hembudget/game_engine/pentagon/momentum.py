"""P1 · Tröghet (momentum).

Spec: dev/game-motor/07-pentagon-mekanik.md (Tröghet/momentum)

Förhindrar yo-yo-effekter:
- Max ±5 per enskilt event (`MAX_PER_EVENT`)
- Max ±8 ackumulerat per 24 h (`MAX_PER_DAY`)
- Max ±12 ackumulerat per 30 dagar (`MAX_PER_MONTH`)

`apply_momentum(axis, requested_delta, history)` returnerar den faktiska
delta som ska appliceras efter klampning. `history` är en iterable av
WellbeingEvent-rader (eller objekt med .occurred_at, .axis, .delta).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable


MAX_PER_EVENT = 5
MAX_PER_DAY = 8
MAX_PER_MONTH = 12


def _clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(upper, value))


def _accumulated(
    history: Iterable,
    *,
    axis: str,
    since: datetime,
) -> int:
    """Summa av delta på `axis` med occurred_at >= since."""
    total = 0
    for h in history:
        if getattr(h, "axis", None) != axis:
            continue
        occurred = getattr(h, "occurred_at", None)
        if occurred is None or occurred < since:
            continue
        total += int(getattr(h, "delta", 0) or 0)
    return total


def apply_momentum(
    axis: str,
    requested_delta: int,
    history: Iterable,
    *,
    now: datetime | None = None,
) -> int:
    """Klampa `requested_delta` enligt tre-stegs tröghets-regler.

    Returnerar den faktiska delta som ska appliceras (kan vara 0 om
    elevens 30-dagars-kvot är uttömd).
    """
    now = now or datetime.utcnow()

    # 1. Per-event-klamp
    delta = _clamp(requested_delta, -MAX_PER_EVENT, MAX_PER_EVENT)

    # 2. Per-24h-klamp
    acc_24h = _accumulated(history, axis=axis, since=now - timedelta(hours=24))
    if abs(acc_24h + delta) > MAX_PER_DAY:
        if delta >= 0:
            delta = max(0, MAX_PER_DAY - acc_24h)
        else:
            delta = min(0, -MAX_PER_DAY - acc_24h)

    # 3. Per-30d-klamp
    acc_30d = _accumulated(history, axis=axis, since=now - timedelta(days=30))
    if abs(acc_30d + delta) > MAX_PER_MONTH:
        if delta >= 0:
            delta = max(0, MAX_PER_MONTH - acc_30d)
        else:
            delta = min(0, -MAX_PER_MONTH - acc_30d)

    return delta
