"""Wellbeing-API: aktuell + historik + omräkning.

Wellbeing är en pedagogisk mätare — inte ett betyg. Endpointarna
returnerar både råpoäng och pedagogisk förklaring så frontend kan
visa varför scoren blev som den blev.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db.models import PersonalityProfile, WellbeingScore
from ..wellbeing.calculator import (
    WellbeingFactor,
    calculate_wellbeing,
    persist_wellbeing,
)
from ..wellbeing.portfolio_impact import compute_portfolio_impact_summary
from ..wellbeing.stock_hindsight import compute_stock_hindsight
from .deps import db, require_auth


router = APIRouter(
    prefix="/wellbeing",
    tags=["wellbeing"],
    dependencies=[Depends(require_auth)],
)


class FactorOut(BaseModel):
    dimension: str
    points: int
    explanation: str


class WellbeingOut(BaseModel):
    year_month: str
    total_score: int
    economy: int
    health: int
    social: int
    leisure: int
    safety: int
    factors: list[FactorOut]
    explanation: str
    events_accepted: int
    events_declined: int
    budget_violations: int


def _result_to_out(r) -> WellbeingOut:
    return WellbeingOut(
        year_month=r.year_month,
        total_score=r.total_score,
        economy=r.economy,
        health=r.health,
        social=r.social,
        leisure=r.leisure,
        safety=r.safety,
        factors=[
            FactorOut(dimension=f.dimension, points=f.points, explanation=f.explanation)
            for f in r.factors
        ],
        explanation=r.explanation,
        events_accepted=r.events_accepted,
        events_declined=r.events_declined,
        budget_violations=r.budget_violations,
    )


def _current_year_month() -> str:
    today = date.today()
    return f"{today.year:04d}-{today.month:02d}"


@router.get("/current", response_model=WellbeingOut)
def current_wellbeing(
    year_month: Optional[str] = Query(default=None),
    session: Session = Depends(db),
) -> WellbeingOut:
    """Beräkna Wellbeing för aktuell månad (eller specifik via param).

    Räknar live från scope-DB:n — ingen persistans här. Använd
    /recompute för att spara."""
    ym = year_month or _current_year_month()
    result = calculate_wellbeing(session, ym)
    return _result_to_out(result)


class HistoryRow(BaseModel):
    year_month: str
    total_score: int
    economy: int
    health: int
    social: int
    leisure: int
    safety: int


@router.get("/history")
def wellbeing_history(
    months: int = Query(default=12, ge=1, le=36),
    session: Session = Depends(db),
) -> dict:
    """Returnera senaste N månadernas WellbeingScore (sparade rader).

    Frontend ritar tidsserie på Dashboard. Tomma månader hoppas över."""
    rows = (
        session.query(WellbeingScore)
        .order_by(WellbeingScore.year_month.desc())
        .limit(months)
        .all()
    )
    return {
        "history": [
            HistoryRow(
                year_month=r.year_month,
                total_score=r.total_score,
                economy=r.economy,
                health=r.health,
                social=r.social,
                leisure=r.leisure,
                safety=r.safety,
            ).model_dump()
            for r in reversed(rows)  # äldst först för tidsserie
        ],
        "count": len(rows),
    }


@router.post("/recompute")
def recompute_wellbeing(
    year_month: Optional[str] = None,
    session: Session = Depends(db),
) -> dict:
    """Räkna om Wellbeing för en månad och spara/uppsert WellbeingScore-rad.

    Anropas vid månadsskifte eller manuellt vid större händelse
    (lärare har generated ny batch, elev har gjort flera transaktioner)."""
    ym = year_month or _current_year_month()
    result = calculate_wellbeing(session, ym)
    row = persist_wellbeing(session, result)
    return {
        "ok": True,
        "year_month": row.year_month,
        "total_score": row.total_score,
        "saved_id": row.id,
    }


@router.get("/portfolio-impact")
def portfolio_impact(session: Session = Depends(db)) -> dict:
    """Live aktieportfölj-påverkan på Trygghet.

    Räknar loss aversion (λ=2.0) + concentration-penalty och returnerar
    detaljerad data så frontend kan visa ett pedagogiskt kort på
    /investments. Eleven ska SE varför Trygghet rör sig — inte bara
    upptäcka att den gjort det."""
    return compute_portfolio_impact_summary(session)


@router.get("/stock-hindsight")
def stock_hindsight(
    year_month: Optional[str] = Query(default=None),
    session: Session = Depends(db),
) -> dict:
    """Aktie-eftertanke: 60-dagars hindsight på elevens sälj.

    För varje sälj senaste 30 dagarna (eller specificerad månad) räknar
    vi ut "vad hade hänt om du väntat 60 dagar". Plus best/worst-beslut
    och loss-aversion-kvot. Pedagogisk konfrontation, inte moralisering."""
    return compute_stock_hindsight(session, year_month)


# ---------- Personlighet (V2 från start) ----------

class PersonalityIn(BaseModel):
    introvert_score: int = 50
    thrill_seeker_score: int = 50
    family_oriented_score: int = 50


class PersonalityOut(BaseModel):
    introvert_score: int
    thrill_seeker_score: int
    family_oriented_score: int
    onboarded: bool


@router.get("/personality", response_model=PersonalityOut)
def get_personality(session: Session = Depends(db)) -> PersonalityOut:
    """Hämta elevens personlighet (default 50/50/50 om ej onboardad)."""
    row = session.query(PersonalityProfile).first()
    if row is None:
        return PersonalityOut(
            introvert_score=50, thrill_seeker_score=50,
            family_oriented_score=50, onboarded=False,
        )
    return PersonalityOut(
        introvert_score=row.introvert_score,
        thrill_seeker_score=row.thrill_seeker_score,
        family_oriented_score=row.family_oriented_score,
        onboarded=row.onboarded_at is not None,
    )


@router.post("/personality", response_model=PersonalityOut)
def save_personality(
    payload: PersonalityIn, session: Session = Depends(db),
) -> PersonalityOut:
    """Spara personlighetsval från onboarding-quiz. Idempotent — kan
    köras flera gånger om eleven vill ändra."""
    from datetime import datetime as _dt
    row = session.query(PersonalityProfile).first()
    if row is None:
        row = PersonalityProfile(
            introvert_score=max(0, min(100, payload.introvert_score)),
            thrill_seeker_score=max(0, min(100, payload.thrill_seeker_score)),
            family_oriented_score=max(0, min(100, payload.family_oriented_score)),
            onboarded_at=_dt.utcnow(),
        )
        session.add(row)
    else:
        row.introvert_score = max(0, min(100, payload.introvert_score))
        row.thrill_seeker_score = max(0, min(100, payload.thrill_seeker_score))
        row.family_oriented_score = max(0, min(100, payload.family_oriented_score))
        if row.onboarded_at is None:
            row.onboarded_at = _dt.utcnow()
    session.flush()
    return PersonalityOut(
        introvert_score=row.introvert_score,
        thrill_seeker_score=row.thrill_seeker_score,
        family_oriented_score=row.family_oriented_score,
        onboarded=True,
    )
