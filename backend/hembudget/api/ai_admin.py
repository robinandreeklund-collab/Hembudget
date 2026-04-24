"""Super-admin-endpoints för att styra AI-åtkomst per lärare.

Endast lärare med `is_super_admin = True` får anropa dessa. Första
bootstrap-läraren blir auto super-admin. Övriga lärare får AI som
default = False — inga AI-anrop går igenom förrän super-admin toggar
på det.

Endpoints:
- GET  /admin/ai/status             — är AI-klienten över huvud taget uppe?
- GET  /admin/ai/teachers           — lista lärare + deras ai_enabled-flagga
- POST /admin/ai/teachers/{id}/ai   — toggla ai_enabled för en lärare
- POST /admin/ai/teachers/{id}/super — toggla is_super_admin för en lärare
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..school import is_enabled as school_enabled
from ..school.ai import is_available as ai_available
from ..school.engines import master_session
from ..school.models import Teacher
from .deps import TokenInfo, require_teacher

router = APIRouter(prefix="/admin/ai", tags=["admin-ai"])


def _require_super_admin(info: TokenInfo = Depends(require_teacher)) -> TokenInfo:
    if not school_enabled():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "School mode inaktivt")
    with master_session() as s:
        t = s.get(Teacher, info.teacher_id)
        if not t or not t.is_super_admin:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Super-admin krävs",
            )
    return info


class AIStatusOut(BaseModel):
    client_available: bool
    """Om ANTHROPIC_API_KEY är satt + anthropic-paketet kunde laddas."""


class TeacherAIRow(BaseModel):
    id: int
    email: str
    name: str
    active: bool
    is_super_admin: bool
    is_demo: bool
    ai_enabled: bool
    ai_requests_count: int
    ai_input_tokens: int
    ai_output_tokens: int


class ToggleIn(BaseModel):
    enabled: bool


@router.get("/status", response_model=AIStatusOut)
def ai_status(_: TokenInfo = Depends(_require_super_admin)) -> AIStatusOut:
    return AIStatusOut(client_available=ai_available())


@router.get("/teachers", response_model=list[TeacherAIRow])
def list_teachers(
    _: TokenInfo = Depends(_require_super_admin),
) -> list[TeacherAIRow]:
    with master_session() as s:
        teachers = s.query(Teacher).order_by(Teacher.id.asc()).all()
        return [
            TeacherAIRow(
                id=t.id,
                email=t.email,
                name=t.name,
                active=t.active,
                is_super_admin=t.is_super_admin,
                is_demo=t.is_demo,
                ai_enabled=t.ai_enabled,
                ai_requests_count=t.ai_requests_count,
                ai_input_tokens=t.ai_input_tokens,
                ai_output_tokens=t.ai_output_tokens,
            )
            for t in teachers
        ]


@router.post("/teachers/{teacher_id}/ai", response_model=TeacherAIRow)
def toggle_ai(
    teacher_id: int,
    payload: ToggleIn,
    _: TokenInfo = Depends(_require_super_admin),
) -> TeacherAIRow:
    with master_session() as s:
        t = s.get(Teacher, teacher_id)
        if not t:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Lärare finns ej")
        t.ai_enabled = payload.enabled
        s.flush()
        return TeacherAIRow(
            id=t.id,
            email=t.email,
            name=t.name,
            active=t.active,
            is_super_admin=t.is_super_admin,
            is_demo=t.is_demo,
            ai_enabled=t.ai_enabled,
            ai_requests_count=t.ai_requests_count,
            ai_input_tokens=t.ai_input_tokens,
            ai_output_tokens=t.ai_output_tokens,
        )


@router.post("/teachers/{teacher_id}/super", response_model=TeacherAIRow)
def toggle_super(
    teacher_id: int,
    payload: ToggleIn,
    info: TokenInfo = Depends(_require_super_admin),
) -> TeacherAIRow:
    if teacher_id == info.teacher_id and not payload.enabled:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Du kan inte ta bort din egen super-admin-status",
        )
    with master_session() as s:
        t = s.get(Teacher, teacher_id)
        if not t:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Lärare finns ej")
        t.is_super_admin = payload.enabled
        s.flush()
        return TeacherAIRow(
            id=t.id,
            email=t.email,
            name=t.name,
            active=t.active,
            is_super_admin=t.is_super_admin,
            is_demo=t.is_demo,
            ai_enabled=t.ai_enabled,
            ai_requests_count=t.ai_requests_count,
            ai_input_tokens=t.ai_input_tokens,
            ai_output_tokens=t.ai_output_tokens,
        )


@router.get("/me")
def ai_me(info: TokenInfo = Depends(require_teacher)) -> dict:
    """Används av frontend för att veta om den inloggade läraren har AI
    aktiverat OCH är super-admin (visar i så fall admin-länken)."""
    with master_session() as s:
        t = s.get(Teacher, info.teacher_id)
        if not t:
            return {
                "ai_enabled": False,
                "is_super_admin": False,
                "ai_available": False,
            }
        return {
            "ai_enabled": bool(t.ai_enabled),
            "is_super_admin": bool(t.is_super_admin),
            "ai_available": ai_available(),
        }
