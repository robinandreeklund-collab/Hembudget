"""Modul-endpoints: kursplan, steg-progression, tilldelning.

Används av både lärare (skapa/redigera moduler, tilldela till elever)
och elever (gå igenom moduler steg för steg).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..school import is_enabled as school_enabled
from ..school.engines import master_session
from ..school.models import (
    Module, ModuleStep, Student, StudentModule, StudentStepProgress,
)
from .deps import TokenInfo, require_teacher, require_token

router = APIRouter(tags=["modules"])


def _require_school_mode() -> None:
    if not school_enabled():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "School mode disabled")


# ---------- Schemas ----------

class ModuleStepIn(BaseModel):
    kind: str = Field(pattern=r"^(read|watch|reflect|task|quiz)$")
    title: str
    content: Optional[str] = None
    params: Optional[dict] = None
    sort_order: int = 0


class ModuleStepOut(BaseModel):
    id: int
    module_id: int
    sort_order: int
    kind: str
    title: str
    content: Optional[str]
    params: Optional[dict]


class ModuleIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    summary: Optional[str] = None
    is_template: bool = False


class ModuleOut(BaseModel):
    id: int
    teacher_id: Optional[int]
    title: str
    summary: Optional[str]
    is_template: bool
    sort_order: int
    created_at: datetime
    step_count: int


class ModuleDetailOut(ModuleOut):
    steps: list[ModuleStepOut]


class StudentModuleOut(BaseModel):
    id: int
    module_id: int
    module_title: str
    module_summary: Optional[str]
    sort_order: int
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    step_count: int
    completed_step_count: int


class StudentStepOut(BaseModel):
    step: ModuleStepOut
    completed_at: Optional[datetime]
    data: Optional[dict]
    teacher_feedback: Optional[str]


class AssignStudentsIn(BaseModel):
    student_ids: list[int]


class StepCompleteIn(BaseModel):
    data: Optional[dict] = None


def _module_to_out(m: Module) -> ModuleOut:
    return ModuleOut(
        id=m.id, teacher_id=m.teacher_id,
        title=m.title, summary=m.summary,
        is_template=m.is_template, sort_order=m.sort_order,
        created_at=m.created_at,
        step_count=len(m.steps),
    )


def _step_to_out(s: ModuleStep) -> ModuleStepOut:
    return ModuleStepOut(
        id=s.id, module_id=s.module_id, sort_order=s.sort_order,
        kind=s.kind, title=s.title, content=s.content, params=s.params,
    )


# ---------- Lärarens modul-hantering ----------

@router.get("/teacher/modules", response_model=list[ModuleOut])
def list_teacher_modules(
    info: TokenInfo = Depends(require_teacher),
) -> list[ModuleOut]:
    """Alla moduler som läraren äger + alla systemmallar."""
    _require_school_mode()
    with master_session() as s:
        mods = (
            s.query(Module)
            .filter(
                (Module.teacher_id == info.teacher_id) |
                (Module.teacher_id.is_(None) & Module.is_template.is_(True))
            )
            .order_by(Module.sort_order, Module.title)
            .all()
        )
        return [_module_to_out(m) for m in mods]


@router.post("/teacher/modules", response_model=ModuleDetailOut)
def create_module(
    payload: ModuleIn,
    info: TokenInfo = Depends(require_teacher),
) -> ModuleDetailOut:
    _require_school_mode()
    with master_session() as s:
        # Hitta högsta sort_order, lägg efter
        max_so = (
            s.query(Module.sort_order)
            .filter(Module.teacher_id == info.teacher_id)
            .order_by(Module.sort_order.desc())
            .first()
        )
        next_so = (max_so[0] + 10) if max_so else 0
        m = Module(
            teacher_id=info.teacher_id,
            title=payload.title, summary=payload.summary,
            is_template=payload.is_template,
            sort_order=next_so,
        )
        s.add(m)
        s.flush()
        base = _module_to_out(m)
        return ModuleDetailOut(**base.model_dump(), steps=[])


@router.get("/teacher/modules/{module_id}", response_model=ModuleDetailOut)
def get_module(
    module_id: int,
    info: TokenInfo = Depends(require_teacher),
) -> ModuleDetailOut:
    _require_school_mode()
    with master_session() as s:
        m = s.query(Module).filter(Module.id == module_id).first()
        if not m:
            raise HTTPException(404, "Module not found")
        if m.teacher_id not in (None, info.teacher_id):
            raise HTTPException(403, "Not your module")
        base = _module_to_out(m)
        return ModuleDetailOut(
            **base.model_dump(),
            steps=[_step_to_out(st) for st in m.steps],
        )


@router.patch("/teacher/modules/{module_id}", response_model=ModuleOut)
def update_module(
    module_id: int,
    payload: ModuleIn,
    info: TokenInfo = Depends(require_teacher),
) -> ModuleOut:
    _require_school_mode()
    with master_session() as s:
        m = s.query(Module).filter(
            Module.id == module_id,
            Module.teacher_id == info.teacher_id,
        ).first()
        if not m:
            raise HTTPException(404, "Module not found")
        m.title = payload.title
        m.summary = payload.summary
        m.is_template = payload.is_template
        s.flush()
        return _module_to_out(m)


@router.delete("/teacher/modules/{module_id}")
def delete_module(
    module_id: int,
    info: TokenInfo = Depends(require_teacher),
) -> dict:
    _require_school_mode()
    with master_session() as s:
        m = s.query(Module).filter(
            Module.id == module_id,
            Module.teacher_id == info.teacher_id,
        ).first()
        if not m:
            raise HTTPException(404, "Module not found")
        s.delete(m)
    return {"ok": True}


@router.post("/teacher/modules/{module_id}/steps", response_model=ModuleStepOut)
def create_step(
    module_id: int,
    payload: ModuleStepIn,
    info: TokenInfo = Depends(require_teacher),
) -> ModuleStepOut:
    _require_school_mode()
    with master_session() as s:
        m = s.query(Module).filter(
            Module.id == module_id,
            Module.teacher_id == info.teacher_id,
        ).first()
        if not m:
            raise HTTPException(404, "Module not found")
        # Om sort_order inte angett: lägg sist
        if payload.sort_order == 0 and m.steps:
            sort_order = max(st.sort_order for st in m.steps) + 10
        else:
            sort_order = payload.sort_order
        st = ModuleStep(
            module_id=m.id,
            sort_order=sort_order,
            kind=payload.kind,
            title=payload.title,
            content=payload.content,
            params=payload.params,
        )
        s.add(st)
        s.flush()
        return _step_to_out(st)


@router.patch(
    "/teacher/modules/{module_id}/steps/{step_id}",
    response_model=ModuleStepOut,
)
def update_step(
    module_id: int, step_id: int,
    payload: ModuleStepIn,
    info: TokenInfo = Depends(require_teacher),
) -> ModuleStepOut:
    _require_school_mode()
    with master_session() as s:
        st = s.query(ModuleStep).filter(ModuleStep.id == step_id).first()
        if not st or st.module_id != module_id:
            raise HTTPException(404, "Step not found")
        m = s.query(Module).filter(
            Module.id == module_id,
            Module.teacher_id == info.teacher_id,
        ).first()
        if not m:
            raise HTTPException(403, "Not your module")
        st.kind = payload.kind
        st.title = payload.title
        st.content = payload.content
        st.params = payload.params
        if payload.sort_order:
            st.sort_order = payload.sort_order
        s.flush()
        return _step_to_out(st)


@router.delete("/teacher/modules/{module_id}/steps/{step_id}")
def delete_step(
    module_id: int, step_id: int,
    info: TokenInfo = Depends(require_teacher),
) -> dict:
    _require_school_mode()
    with master_session() as s:
        st = s.query(ModuleStep).filter(ModuleStep.id == step_id).first()
        if not st or st.module_id != module_id:
            raise HTTPException(404, "Step not found")
        m = s.query(Module).filter(
            Module.id == module_id,
            Module.teacher_id == info.teacher_id,
        ).first()
        if not m:
            raise HTTPException(403, "Not your module")
        s.delete(st)
    return {"ok": True}


@router.post("/teacher/modules/{module_id}/assign")
def assign_module(
    module_id: int,
    payload: AssignStudentsIn,
    info: TokenInfo = Depends(require_teacher),
) -> dict:
    """Tilldela en modul till en eller flera elever."""
    _require_school_mode()
    assigned = 0
    with master_session() as s:
        m = s.query(Module).filter(Module.id == module_id).first()
        if not m:
            raise HTTPException(404, "Module not found")
        if m.teacher_id not in (None, info.teacher_id):
            raise HTTPException(403, "Not your module")
        for sid in payload.student_ids:
            stu = s.query(Student).filter(
                Student.id == sid,
                Student.teacher_id == info.teacher_id,
            ).first()
            if not stu:
                continue
            existing = s.query(StudentModule).filter(
                StudentModule.student_id == sid,
                StudentModule.module_id == module_id,
            ).first()
            if existing:
                continue
            # Sort_order: sist i elevens lista
            max_so = (
                s.query(StudentModule.sort_order)
                .filter(StudentModule.student_id == sid)
                .order_by(StudentModule.sort_order.desc())
                .first()
            )
            next_so = (max_so[0] + 10) if max_so else 0
            s.add(StudentModule(
                student_id=sid, module_id=module_id, sort_order=next_so,
            ))
            assigned += 1
    return {"assigned": assigned}


@router.post("/teacher/modules/{module_id}/unassign")
def unassign_module(
    module_id: int,
    payload: AssignStudentsIn,
    info: TokenInfo = Depends(require_teacher),
) -> dict:
    _require_school_mode()
    removed = 0
    with master_session() as s:
        for sid in payload.student_ids:
            stu = s.query(Student).filter(
                Student.id == sid,
                Student.teacher_id == info.teacher_id,
            ).first()
            if not stu:
                continue
            sm = s.query(StudentModule).filter(
                StudentModule.student_id == sid,
                StudentModule.module_id == module_id,
            ).first()
            if sm:
                s.delete(sm)
                removed += 1
    return {"removed": removed}


# ---------- Elevens kursplan ----------

@router.get("/student/modules", response_model=list[StudentModuleOut])
def student_modules(
    info: TokenInfo = Depends(require_token),
) -> list[StudentModuleOut]:
    _require_school_mode()
    if info.role != "student":
        raise HTTPException(403, "Not a student token")
    out: list[StudentModuleOut] = []
    with master_session() as s:
        rows = (
            s.query(StudentModule)
            .filter(StudentModule.student_id == info.student_id)
            .order_by(StudentModule.sort_order)
            .all()
        )
        for sm in rows:
            m = s.query(Module).filter(Module.id == sm.module_id).first()
            if not m:
                continue
            step_ids = [st.id for st in m.steps]
            completed = (
                s.query(StudentStepProgress)
                .filter(
                    StudentStepProgress.student_id == info.student_id,
                    StudentStepProgress.step_id.in_(step_ids),
                    StudentStepProgress.completed_at.isnot(None),
                )
                .count()
            ) if step_ids else 0
            out.append(StudentModuleOut(
                id=sm.id, module_id=m.id,
                module_title=m.title, module_summary=m.summary,
                sort_order=sm.sort_order,
                started_at=sm.started_at, completed_at=sm.completed_at,
                step_count=len(step_ids),
                completed_step_count=completed,
            ))
    return out


@router.get("/student/modules/{module_id}", response_model=ModuleDetailOut)
def student_module_detail(
    module_id: int,
    info: TokenInfo = Depends(require_token),
) -> ModuleDetailOut:
    _require_school_mode()
    if info.role != "student":
        raise HTTPException(403, "Not a student token")
    with master_session() as s:
        sm = s.query(StudentModule).filter(
            StudentModule.student_id == info.student_id,
            StudentModule.module_id == module_id,
        ).first()
        if not sm:
            raise HTTPException(404, "Modulen är inte tilldelad dig")
        m = s.query(Module).filter(Module.id == module_id).first()
        if not m:
            raise HTTPException(404, "Module not found")
        # Markera modulen som startad om första gången
        if not sm.started_at:
            sm.started_at = datetime.utcnow()
        base = _module_to_out(m)
        return ModuleDetailOut(
            **base.model_dump(),
            steps=[_step_to_out(st) for st in m.steps],
        )


@router.get("/student/steps/{step_id}/progress", response_model=StudentStepOut)
def student_step_progress(
    step_id: int,
    info: TokenInfo = Depends(require_token),
) -> StudentStepOut:
    _require_school_mode()
    if info.role != "student":
        raise HTTPException(403, "Not a student token")
    with master_session() as s:
        st = s.query(ModuleStep).filter(ModuleStep.id == step_id).first()
        if not st:
            raise HTTPException(404, "Step not found")
        # Säkerställ att eleven är tilldelad modulen
        sm = s.query(StudentModule).filter(
            StudentModule.student_id == info.student_id,
            StudentModule.module_id == st.module_id,
        ).first()
        if not sm:
            raise HTTPException(403, "Modulen är inte tilldelad dig")
        prog = s.query(StudentStepProgress).filter(
            StudentStepProgress.student_id == info.student_id,
            StudentStepProgress.step_id == step_id,
        ).first()
        return StudentStepOut(
            step=_step_to_out(st),
            completed_at=prog.completed_at if prog else None,
            data=prog.data if prog else None,
            teacher_feedback=prog.teacher_feedback if prog else None,
        )


@router.post("/student/steps/{step_id}/complete")
def student_complete_step(
    step_id: int,
    payload: StepCompleteIn,
    info: TokenInfo = Depends(require_token),
) -> dict:
    """Markera ett steg som klart + lagra ev. svar/reflektion i data.
    För quiz: data={"answer": index}, server räknar ut om rätt.
    För reflect: data={"reflection": "..."} — kräver minst 10 tecken.
    För read/watch: data tas emot men krävs inte.
    """
    _require_school_mode()
    if info.role != "student":
        raise HTTPException(403, "Not a student token")
    with master_session() as s:
        st = s.query(ModuleStep).filter(ModuleStep.id == step_id).first()
        if not st:
            raise HTTPException(404, "Step not found")
        sm = s.query(StudentModule).filter(
            StudentModule.student_id == info.student_id,
            StudentModule.module_id == st.module_id,
        ).first()
        if not sm:
            raise HTTPException(403, "Modulen är inte tilldelad dig")

        data = dict(payload.data or {})

        # Typ-specifik validering
        if st.kind == "reflect":
            text = (data.get("reflection") or "").strip()
            if len(text) < 10:
                raise HTTPException(
                    400,
                    "Skriv en reflektion på minst 10 tecken",
                )
            data["reflection"] = text
        elif st.kind == "quiz":
            answer = data.get("answer")
            if not isinstance(answer, int):
                raise HTTPException(400, "Saknar 'answer' (int)")
            correct_index = (st.params or {}).get("correct_index")
            data["correct"] = (answer == correct_index)
            data["correct_index"] = correct_index

        prog = s.query(StudentStepProgress).filter(
            StudentStepProgress.student_id == info.student_id,
            StudentStepProgress.step_id == step_id,
        ).first()
        if not prog:
            prog = StudentStepProgress(
                student_id=info.student_id,
                step_id=step_id,
                completed_at=datetime.utcnow(),
                data=data,
            )
            s.add(prog)
        else:
            prog.completed_at = datetime.utcnow()
            prog.data = data
        s.flush()

        # Om alla steg klara → markera modulen som klar
        total_steps = s.query(ModuleStep).filter(
            ModuleStep.module_id == st.module_id
        ).count()
        completed = s.query(StudentStepProgress).filter(
            StudentStepProgress.student_id == info.student_id,
            StudentStepProgress.step_id.in_(
                s.query(ModuleStep.id).filter(
                    ModuleStep.module_id == st.module_id
                )
            ),
            StudentStepProgress.completed_at.isnot(None),
        ).count()
        sm_done = total_steps > 0 and completed >= total_steps
        if sm_done and not sm.completed_at:
            sm.completed_at = datetime.utcnow()
        return {
            "ok": True,
            "step_done": True,
            "module_done": sm_done,
            "progress": f"{completed}/{total_steps}",
            "data": data,
        }
