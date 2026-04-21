from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db.models import Scenario
from ..scenarios.engine import ScenarioEngine
from .deps import db, require_auth
from .schemas import ScenarioIn, ScenarioOut

router = APIRouter(prefix="/scenarios", tags=["scenarios"], dependencies=[Depends(require_auth)])


@router.post("/calculate")
def calculate(payload: ScenarioIn) -> dict:
    try:
        return ScenarioEngine().run(payload.kind, payload.params)
    except (KeyError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/", response_model=ScenarioOut)
def save_scenario(payload: ScenarioIn, session: Session = Depends(db)) -> Scenario:
    result = ScenarioEngine().run(payload.kind, payload.params)
    s = Scenario(name=payload.name, kind=payload.kind, params=payload.params, result=result)
    session.add(s)
    session.flush()
    return s


@router.get("/", response_model=list[ScenarioOut])
def list_scenarios(session: Session = Depends(db)) -> list[Scenario]:
    return session.query(Scenario).order_by(Scenario.id.desc()).all()


@router.delete("/{scenario_id}")
def delete_scenario(scenario_id: int, session: Session = Depends(db)) -> dict:
    s = session.get(Scenario, scenario_id)
    if s is None:
        raise HTTPException(404, "Scenario not found")
    session.delete(s)
    return {"deleted": scenario_id}
