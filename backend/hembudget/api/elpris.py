"""HTTP-endpoints för svenska spotelpriser."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException

from ..elpris import VALID_ZONES, DayPrices, ElprisClient
from .deps import require_auth

router = APIRouter(
    prefix="/elpris",
    tags=["elpris"],
    dependencies=[Depends(require_auth)],
)


# Modul-lokal klient — delad cache över requests. Kan bytas ut i tester.
_CLIENT: Optional[ElprisClient] = None


def get_client() -> ElprisClient:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = ElprisClient()
    return _CLIENT


def set_client(client: ElprisClient) -> None:
    """Används av tester — ersätt singleton."""
    global _CLIENT
    _CLIENT = client


def _serialize(day: DayPrices) -> dict:
    return {
        "date": day.date.isoformat(),
        "zone": day.zone,
        "avg_sek_per_kwh_inc_vat": day.avg_inc_vat,
        "cheapest_hours": [
            {
                "start": h.time_start.isoformat(),
                "end": h.time_end.isoformat(),
                "sek_per_kwh_inc_vat": round(h.sek_inc_vat, 4),
            }
            for h in day.cheapest_hours(3)
        ],
        "hours": [
            {
                "start": h.time_start.isoformat(),
                "end": h.time_end.isoformat(),
                "sek_per_kwh": round(h.sek_per_kwh, 4),
                "sek_per_kwh_inc_vat": round(h.sek_inc_vat, 4),
            }
            for h in day.hours
        ],
    }


@router.get("/{day}")
def get_day(day: str, zone: str = "SE3") -> dict:
    """`day` = 'today', 'tomorrow' eller 'YYYY-MM-DD'."""
    if zone not in VALID_ZONES:
        raise HTTPException(400, f"zone must be one of {VALID_ZONES}")
    client = get_client()

    if day == "today":
        target = date.today()
    elif day == "tomorrow":
        target = date.today() + timedelta(days=1)
    else:
        try:
            target = date.fromisoformat(day)
        except ValueError as exc:
            raise HTTPException(400, "day must be 'today', 'tomorrow' or YYYY-MM-DD") from exc

    try:
        return _serialize(client.get(target, zone))
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(
                404,
                f"Inga priser tillgängliga för {target.isoformat()} ({zone}). "
                "Morgondagens priser publiceras typiskt runt 13:00 CET.",
            ) from exc
        raise HTTPException(502, f"Elprisetjustnu svarade: {exc}") from exc
    except httpx.RequestError as exc:
        raise HTTPException(503, f"Kunde inte nå elpris-API: {exc}") from exc
