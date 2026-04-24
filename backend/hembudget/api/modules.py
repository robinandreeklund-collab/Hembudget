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
    Competency, Module, ModuleStep, ModuleStepCompetency,
    PeerFeedback, Student, StudentModule, StudentProfile,
    StudentStepProgress,
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


@router.get("/library/modules", response_model=list[ModuleOut])
def library_modules() -> list[ModuleOut]:
    """Publika mallar — inga auth krav. Används både för
    lärarens bibliotek och landningssidan om vi vill visa exempel."""
    _require_school_mode()
    with master_session() as s:
        rows = (
            s.query(Module)
            .filter(Module.is_template.is_(True))
            .order_by(Module.title)
            .all()
        )
        return [_module_to_out(m) for m in rows]


@router.get("/library/modules/{module_id}", response_model=ModuleDetailOut)
def library_module_detail(module_id: int) -> ModuleDetailOut:
    _require_school_mode()
    with master_session() as s:
        m = s.query(Module).filter(
            Module.id == module_id,
            Module.is_template.is_(True),
        ).first()
        if not m:
            raise HTTPException(404, "Template not found")
        base = _module_to_out(m)
        return ModuleDetailOut(
            **base.model_dump(),
            steps=[_step_to_out(st) for st in m.steps],
        )


@router.post("/teacher/modules/{module_id}/clone", response_model=ModuleOut)
def clone_module(
    module_id: int,
    info: TokenInfo = Depends(require_teacher),
) -> ModuleOut:
    """Duplicera en befintlig modul (systemmall eller lärarens egen) till
    en ny modul som ägs av aktuell lärare. Steg kopieras inklusive params.
    Ny modul sätts som is_template=False."""
    _require_school_mode()
    from ..school.models import ModuleStepCompetency
    with master_session() as s:
        original = s.query(Module).filter(Module.id == module_id).first()
        if not original:
            raise HTTPException(404, "Module not found")
        # Tillåtet att klona: egen modul, eller template (system eller från
        # annan lärare)
        if (
            original.teacher_id not in (None, info.teacher_id)
            and not original.is_template
        ):
            raise HTTPException(403, "Kan inte klona denna modul")

        max_so = (
            s.query(Module.sort_order)
            .filter(Module.teacher_id == info.teacher_id)
            .order_by(Module.sort_order.desc())
            .first()
        )
        next_so = (max_so[0] + 10) if max_so else 0
        new_mod = Module(
            teacher_id=info.teacher_id,
            title=f"{original.title} (kopia)",
            summary=original.summary,
            is_template=False,
            sort_order=next_so,
        )
        s.add(new_mod)
        s.flush()
        # Kopiera steg
        for st in original.steps:
            new_step = ModuleStep(
                module_id=new_mod.id,
                sort_order=st.sort_order,
                kind=st.kind,
                title=st.title,
                content=st.content,
                params=dict(st.params) if st.params else None,
            )
            s.add(new_step)
            s.flush()
            # Kopiera competency-kopplingar
            for msc in s.query(ModuleStepCompetency).filter(
                ModuleStepCompetency.step_id == st.id
            ).all():
                s.add(ModuleStepCompetency(
                    step_id=new_step.id,
                    competency_id=msc.competency_id,
                    weight=msc.weight,
                ))
        return _module_to_out(new_mod)


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


# ---------- Kompetenser ----------

class CompetencyOut(BaseModel):
    id: int
    key: str
    name: str
    description: Optional[str]
    level: str
    is_system: bool


class CompetencyMasteryOut(BaseModel):
    competency: CompetencyOut
    mastery: float  # 0.0–1.0
    evidence_count: int
    latest_evidence_at: Optional[datetime] = None


@router.get("/school/competencies", response_model=list[CompetencyOut])
def list_competencies(
    info: TokenInfo = Depends(require_token),
) -> list[CompetencyOut]:
    """Lista tillgängliga kompetenser för aktuell användare."""
    _require_school_mode()
    with master_session() as s:
        q = s.query(Competency).filter(
            (Competency.is_system.is_(True)) |
            (
                Competency.teacher_id == (info.teacher_id or -1)
                if info.role == "teacher" else False
            )
        ).order_by(Competency.level, Competency.name)
        return [
            CompetencyOut(
                id=c.id, key=c.key, name=c.name,
                description=c.description, level=c.level,
                is_system=c.is_system,
            )
            for c in q.all()
        ]


@router.post("/teacher/modules/{module_id}/steps/{step_id}/competencies")
def link_step_competency(
    module_id: int, step_id: int,
    competency_id: int, weight: float = 1.0,
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
        existing = s.query(ModuleStepCompetency).filter(
            ModuleStepCompetency.step_id == step_id,
            ModuleStepCompetency.competency_id == competency_id,
        ).first()
        if existing:
            existing.weight = weight
        else:
            s.add(ModuleStepCompetency(
                step_id=step_id, competency_id=competency_id, weight=weight,
            ))
    return {"ok": True}


@router.delete("/teacher/modules/{module_id}/steps/{step_id}/competencies/{competency_id}")
def unlink_step_competency(
    module_id: int, step_id: int, competency_id: int,
    info: TokenInfo = Depends(require_teacher),
) -> dict:
    _require_school_mode()
    with master_session() as s:
        m = s.query(Module).filter(
            Module.id == module_id,
            Module.teacher_id == info.teacher_id,
        ).first()
        if not m:
            raise HTTPException(403, "Not your module")
        row = s.query(ModuleStepCompetency).filter(
            ModuleStepCompetency.step_id == step_id,
            ModuleStepCompetency.competency_id == competency_id,
        ).first()
        if row:
            s.delete(row)
    return {"ok": True}


@router.get(
    "/teacher/modules/{module_id}/steps/{step_id}/competencies",
    response_model=list[CompetencyOut],
)
def list_step_competencies(
    module_id: int, step_id: int,
    info: TokenInfo = Depends(require_teacher),
) -> list[CompetencyOut]:
    _require_school_mode()
    with master_session() as s:
        rows = (
            s.query(Competency)
            .join(ModuleStepCompetency,
                  Competency.id == ModuleStepCompetency.competency_id)
            .filter(ModuleStepCompetency.step_id == step_id)
            .all()
        )
        return [
            CompetencyOut(
                id=c.id, key=c.key, name=c.name,
                description=c.description, level=c.level,
                is_system=c.is_system,
            )
            for c in rows
        ]


def _compute_mastery_for_student(
    s, student_id: int,
) -> dict[int, tuple[float, int, Optional[datetime]]]:
    """Returnera mastery per kompetens-id för en elev.
    Mastery-formel per kompetens:
       mastery = sum(done_weights * success_factor) / sum(all_weights)
    där success_factor är 1.0 för read/task/reflect (om klar) och
    0.0/1.0 för quiz beroende på correct.
    """
    # Alla step-competency-kopplingar + step-kind
    rows = (
        s.query(ModuleStepCompetency, ModuleStep)
        .join(ModuleStep, ModuleStepCompetency.step_id == ModuleStep.id)
        .all()
    )
    # Elevens progress per step_id
    progs = {
        p.step_id: p for p in s.query(StudentStepProgress).filter(
            StudentStepProgress.student_id == student_id
        ).all()
    }
    by_comp: dict[int, dict] = {}
    for msc, step in rows:
        bucket = by_comp.setdefault(msc.competency_id, {
            "total_weight": 0.0,
            "earned_weight": 0.0,
            "count": 0,
            "latest": None,
        })
        bucket["total_weight"] += msc.weight
        prog = progs.get(step.id)
        if prog and prog.completed_at:
            success = 1.0
            if step.kind == "quiz":
                # Mastery baseras på första försöket så eleven inte kan
                # "trappa upp" sin mastery genom att svara om tills rätt.
                d = prog.data or {}
                success = 1.0 if d.get("first_correct", d.get("correct")) else 0.0
            bucket["earned_weight"] += msc.weight * success
            bucket["count"] += 1
            if not bucket["latest"] or prog.completed_at > bucket["latest"]:
                bucket["latest"] = prog.completed_at
    result: dict[int, tuple[float, int, Optional[datetime]]] = {}
    for cid, b in by_comp.items():
        mastery = (
            b["earned_weight"] / b["total_weight"]
            if b["total_weight"] > 0 else 0.0
        )
        result[cid] = (mastery, b["count"], b["latest"])
    return result


@router.get(
    "/student/mastery",
    response_model=list[CompetencyMasteryOut],
)
def student_mastery(
    info: TokenInfo = Depends(require_token),
) -> list[CompetencyMasteryOut]:
    _require_school_mode()
    if info.role != "student":
        raise HTTPException(403, "Not a student token")
    out: list[CompetencyMasteryOut] = []
    with master_session() as s:
        mastery_by_cid = _compute_mastery_for_student(s, info.student_id)
        comps = s.query(Competency).all()
        for c in comps:
            m = mastery_by_cid.get(c.id, (0.0, 0, None))
            out.append(CompetencyMasteryOut(
                competency=CompetencyOut(
                    id=c.id, key=c.key, name=c.name,
                    description=c.description, level=c.level,
                    is_system=c.is_system,
                ),
                mastery=round(m[0], 3),
                evidence_count=m[1],
                latest_evidence_at=m[2],
            ))
        # Sortera: mest bevisade först, sedan nivå
        out.sort(key=lambda r: (-r.evidence_count, r.competency.level, r.competency.name))
    return out


@router.get(
    "/teacher/students/{student_id}/mastery",
    response_model=list[CompetencyMasteryOut],
)
def teacher_student_mastery(
    student_id: int,
    info: TokenInfo = Depends(require_teacher),
) -> list[CompetencyMasteryOut]:
    """Samma som /student/mastery men för läraren som tittar."""
    _require_school_mode()
    with master_session() as s:
        stu = s.query(Student).filter(
            Student.id == student_id,
            Student.teacher_id == info.teacher_id,
        ).first()
        if not stu:
            raise HTTPException(404, "Student not found")
        mastery_by_cid = _compute_mastery_for_student(s, student_id)
        comps = s.query(Competency).all()
        out = [
            CompetencyMasteryOut(
                competency=CompetencyOut(
                    id=c.id, key=c.key, name=c.name,
                    description=c.description, level=c.level,
                    is_system=c.is_system,
                ),
                mastery=round(mastery_by_cid.get(c.id, (0.0, 0, None))[0], 3),
                evidence_count=mastery_by_cid.get(c.id, (0.0, 0, None))[1],
                latest_evidence_at=mastery_by_cid.get(c.id, (0.0, 0, None))[2],
            )
            for c in comps
        ]
        out.sort(key=lambda r: (-r.evidence_count, r.competency.level, r.competency.name))
        return out


# ---------- Lärarens reflektionsinbox ----------

class ReflectionOut(BaseModel):
    progress_id: int
    student_id: int
    student_name: str
    class_label: Optional[str]
    module_id: int
    module_title: str
    step_id: int
    step_title: str
    step_question: Optional[str]  # step.content
    reflection: str
    completed_at: Optional[datetime]
    teacher_feedback: Optional[str]
    feedback_at: Optional[datetime]
    # Ev. rubric-definition från step.params + elevens bedömning
    rubric: Optional[list[dict]] = None  # [{key, name, levels: [..]}]
    rubric_scores: Optional[dict] = None  # {key: level_index}


class FeedbackIn(BaseModel):
    feedback: str = Field(min_length=1, max_length=4000)
    # Valfri rubric-bedömning: {criterion_key: level_index}
    rubric_scores: Optional[dict] = None


@router.get("/teacher/reflections", response_model=list[ReflectionOut])
def list_reflections(
    needs_feedback: bool = False,
    info: TokenInfo = Depends(require_teacher),
) -> list[ReflectionOut]:
    """Alla reflektioner från mina elever.
    needs_feedback=true filtrerar till bara de utan feedback."""
    _require_school_mode()
    out: list[ReflectionOut] = []
    with master_session() as s:
        # Alla progress-rader för reflect-steg från mina elever
        rows = (
            s.query(StudentStepProgress, ModuleStep, Student)
            .join(ModuleStep, StudentStepProgress.step_id == ModuleStep.id)
            .join(Student, StudentStepProgress.student_id == Student.id)
            .filter(
                Student.teacher_id == info.teacher_id,
                ModuleStep.kind == "reflect",
                StudentStepProgress.completed_at.isnot(None),
            )
            .order_by(StudentStepProgress.completed_at.desc())
            .all()
        )
        for prog, step, stu in rows:
            if needs_feedback and prog.teacher_feedback:
                continue
            reflection = ""
            if prog.data and isinstance(prog.data, dict):
                reflection = str(prog.data.get("reflection", ""))
            module = s.query(Module).filter(Module.id == step.module_id).first()
            rubric = None
            if step.params and isinstance(step.params.get("rubric"), list):
                rubric = step.params["rubric"]
            out.append(ReflectionOut(
                progress_id=prog.id,
                student_id=stu.id, student_name=stu.display_name,
                class_label=stu.class_label,
                module_id=step.module_id,
                module_title=module.title if module else "—",
                step_id=step.id, step_title=step.title,
                step_question=step.content,
                reflection=reflection,
                completed_at=prog.completed_at,
                teacher_feedback=prog.teacher_feedback,
                feedback_at=prog.feedback_at,
                rubric=rubric,
                rubric_scores=prog.rubric_scores,
            ))
    return out


@router.post("/teacher/reflections/{progress_id}/feedback")
def give_feedback(
    progress_id: int,
    payload: FeedbackIn,
    info: TokenInfo = Depends(require_teacher),
) -> dict:
    _require_school_mode()
    with master_session() as s:
        prog = s.query(StudentStepProgress).filter(
            StudentStepProgress.id == progress_id
        ).first()
        if not prog:
            raise HTTPException(404, "Progress not found")
        # Säkerställ att det är lärarens elev
        stu = s.query(Student).filter(Student.id == prog.student_id).first()
        if not stu or stu.teacher_id != info.teacher_id:
            raise HTTPException(403, "Inte din elev")
        prog.teacher_feedback = payload.feedback.strip()
        prog.feedback_at = datetime.utcnow()
        if payload.rubric_scores is not None:
            prog.rubric_scores = payload.rubric_scores
    return {"ok": True}


@router.get("/teacher/reflections/unread-count")
def reflections_unread_count(
    info: TokenInfo = Depends(require_teacher),
) -> dict:
    _require_school_mode()
    with master_session() as s:
        n = (
            s.query(StudentStepProgress)
            .join(ModuleStep, StudentStepProgress.step_id == ModuleStep.id)
            .join(Student, StudentStepProgress.student_id == Student.id)
            .filter(
                Student.teacher_id == info.teacher_id,
                ModuleStep.kind == "reflect",
                StudentStepProgress.completed_at.isnot(None),
                StudentStepProgress.teacher_feedback.is_(None),
            )
            .count()
        )
    return {"unread": n}


# ---------- Adaptiva rekommendationer ----------

class RecommendationOut(BaseModel):
    module_id: int
    title: str
    summary: Optional[str]
    step_count: int
    reason: str  # mänskligt läsbar förklaring
    weak_competencies: list[str]  # kompetens-namn som modulen tränar
    score: float  # rangordning (högre = bättre rek)


def _recommend_modules_for_student(
    s, student_id: int, limit: int = 5,
) -> list[RecommendationOut]:
    """Ge rekommenderade moduler baserat på elevens mastery.

    Logik:
    1. Räkna mastery per kompetens. Identifiera "svaga" kompetenser —
       mastery < 0.5 (eller 0 bevis = helt outforskade).
    2. Hämta alla moduler som är:
       - Template (systemmall), ELLER ägda av elevens lärare
       - INTE redan tilldelade eleven
    3. Poängsätt varje modul: summan av svaga kompetensers bidrag.
       En modul får poäng om något av dess steg är kopplat till en
       svag kompetens.
    4. Returnera topp-N med förklaring.
    """
    me = s.query(Student).filter(Student.id == student_id).first()
    if not me:
        return []

    mastery_map = _compute_mastery_for_student(s, student_id)
    comps = {c.id: c for c in s.query(Competency).all()}

    # Svaga kompetenser: mastery < 0.5 (räknar också helt outforskade
    # som svaga men ger dem något lägre vikt)
    weakness: dict[int, float] = {}
    for cid, c in comps.items():
        m = mastery_map.get(cid)
        if m is None:
            # Ingen koppling än — mindre prioriterat
            weakness[cid] = 0.3
        elif m[0] < 0.5:
            # Ju lägre mastery desto högre prioritet
            weakness[cid] = 1.0 - m[0]
    if not weakness:
        return []

    # Redan tilldelade moduler
    assigned_module_ids = {
        sm.module_id for sm in s.query(StudentModule).filter(
            StudentModule.student_id == student_id
        ).all()
    }

    # Alla relevanta moduler
    candidate_modules = (
        s.query(Module)
        .filter(
            ((Module.teacher_id == me.teacher_id) | Module.is_template.is_(True)),
        )
        .all()
    )

    ranked: list[tuple[Module, float, set[int]]] = []
    for m in candidate_modules:
        if m.id in assigned_module_ids:
            continue
        if not m.steps:
            continue
        # Hämta alla kompetenser som denna moduls steg tränar
        step_ids = [st.id for st in m.steps]
        mscs = (
            s.query(ModuleStepCompetency).filter(
                ModuleStepCompetency.step_id.in_(step_ids)
            ).all()
        )
        comp_ids = {msc.competency_id for msc in mscs}
        if not comp_ids:
            continue
        # Poäng = summan av svaga kompetensers vikt bland modulens
        score = sum(weakness.get(cid, 0) for cid in comp_ids)
        if score <= 0:
            continue
        ranked.append((m, score, comp_ids))

    ranked.sort(key=lambda t: -t[1])

    out: list[RecommendationOut] = []
    for m, score, comp_ids in ranked[:limit]:
        weak_names = [
            comps[cid].name for cid in comp_ids
            if cid in weakness and cid in comps
        ][:3]
        if weak_names:
            reason = (
                "Tränar svaga områden: " + ", ".join(weak_names)
            )
        else:
            reason = "Passar din utvecklingsnivå"
        out.append(RecommendationOut(
            module_id=m.id, title=m.title, summary=m.summary,
            step_count=len(m.steps), reason=reason,
            weak_competencies=weak_names, score=round(score, 2),
        ))
    return out


@router.get(
    "/student/recommendations",
    response_model=list[RecommendationOut],
)
def student_recommendations(
    info: TokenInfo = Depends(require_token),
) -> list[RecommendationOut]:
    _require_school_mode()
    if info.role != "student":
        raise HTTPException(403, "Not a student token")
    with master_session() as s:
        return _recommend_modules_for_student(s, info.student_id)


@router.get(
    "/teacher/students/{student_id}/recommendations",
    response_model=list[RecommendationOut],
)
def teacher_student_recommendations(
    student_id: int,
    info: TokenInfo = Depends(require_teacher),
) -> list[RecommendationOut]:
    _require_school_mode()
    with master_session() as s:
        stu = s.query(Student).filter(
            Student.id == student_id,
            Student.teacher_id == info.teacher_id,
        ).first()
        if not stu:
            raise HTTPException(404, "Student not found")
        return _recommend_modules_for_student(s, student_id)


# ---------- Peer-review ----------

class PeerReviewTarget(BaseModel):
    progress_id: int
    module_title: str
    step_title: str
    step_question: Optional[str]
    reflection: str


class PeerFeedbackIn(BaseModel):
    progress_id: int
    body: str = Field(min_length=10, max_length=2000)


class PeerFeedbackReceived(BaseModel):
    id: int
    body: str
    created_at: datetime
    module_title: str
    step_title: str


@router.get("/student/peer-review/next",
            response_model=Optional[PeerReviewTarget])
def peer_review_next(
    info: TokenInfo = Depends(require_token),
) -> Optional[PeerReviewTarget]:
    """Hämta nästa reflektion att peer-review:a. Slumpas anonymt från
    samma modul, andra elever hos samma lärare, och endast för steg
    där läraren aktiverat peer_review=true i params."""
    _require_school_mode()
    if info.role != "student":
        raise HTTPException(403, "Not a student token")
    import random
    with master_session() as s:
        me = s.query(Student).filter(Student.id == info.student_id).first()
        if not me:
            raise HTTPException(404, "Student not found")
        # Hitta progress-rader från andra elever hos samma lärare, på
        # reflect-steg där peer_review är enabled och jag inte redan reviewat.
        candidates = (
            s.query(StudentStepProgress, ModuleStep)
            .join(ModuleStep, StudentStepProgress.step_id == ModuleStep.id)
            .join(Student, StudentStepProgress.student_id == Student.id)
            .filter(
                Student.teacher_id == me.teacher_id,
                Student.id != me.id,
                ModuleStep.kind == "reflect",
                StudentStepProgress.completed_at.isnot(None),
            )
            .all()
        )
        # Filtrera på peer_review + redan reviewade
        already = {
            pf.target_progress_id
            for pf in s.query(PeerFeedback).filter(
                PeerFeedback.reviewer_student_id == me.id
            ).all()
        }
        pool: list = []
        for prog, step in candidates:
            if prog.id in already:
                continue
            if not (step.params or {}).get("peer_review"):
                continue
            pool.append((prog, step))
        if not pool:
            return None
        prog, step = random.choice(pool)
        module = s.query(Module).filter(Module.id == step.module_id).first()
        return PeerReviewTarget(
            progress_id=prog.id,
            module_title=module.title if module else "—",
            step_title=step.title,
            step_question=step.content,
            reflection=(prog.data or {}).get("reflection", ""),
        )


@router.post("/student/peer-review")
def peer_review_submit(
    payload: PeerFeedbackIn,
    info: TokenInfo = Depends(require_token),
) -> dict:
    _require_school_mode()
    if info.role != "student":
        raise HTTPException(403, "Not a student token")
    with master_session() as s:
        target = s.query(StudentStepProgress).filter(
            StudentStepProgress.id == payload.progress_id
        ).first()
        if not target:
            raise HTTPException(404, "Inte hittat")
        if target.student_id == info.student_id:
            raise HTTPException(400, "Du kan inte review:a din egen reflektion")
        # Samma lärare?
        me = s.query(Student).filter(Student.id == info.student_id).first()
        target_stu = s.query(Student).filter(Student.id == target.student_id).first()
        if not me or not target_stu or me.teacher_id != target_stu.teacher_id:
            raise HTTPException(403, "Ej samma klass")
        existing = s.query(PeerFeedback).filter(
            PeerFeedback.reviewer_student_id == info.student_id,
            PeerFeedback.target_progress_id == payload.progress_id,
        ).first()
        if existing:
            raise HTTPException(400, "Du har redan gett feedback")
        s.add(PeerFeedback(
            reviewer_student_id=info.student_id,
            target_progress_id=payload.progress_id,
            body=payload.body.strip(),
        ))
    return {"ok": True}


@router.get(
    "/student/peer-review/received",
    response_model=list[PeerFeedbackReceived],
)
def peer_review_received(
    info: TokenInfo = Depends(require_token),
) -> list[PeerFeedbackReceived]:
    """Peer-feedback jag fått från andra elever — anonymt (inget
    reviewer-namn visas)."""
    _require_school_mode()
    if info.role != "student":
        raise HTTPException(403, "Not a student token")
    out: list[PeerFeedbackReceived] = []
    with master_session() as s:
        rows = (
            s.query(PeerFeedback, StudentStepProgress, ModuleStep)
            .join(
                StudentStepProgress,
                PeerFeedback.target_progress_id == StudentStepProgress.id,
            )
            .join(ModuleStep, StudentStepProgress.step_id == ModuleStep.id)
            .filter(StudentStepProgress.student_id == info.student_id)
            .order_by(PeerFeedback.created_at.desc())
            .all()
        )
        for pf, prog, step in rows:
            mod = s.query(Module).filter(Module.id == step.module_id).first()
            out.append(PeerFeedbackReceived(
                id=pf.id, body=pf.body, created_at=pf.created_at,
                module_title=mod.title if mod else "—",
                step_title=step.title,
            ))
    return out


# ---------- Portfolio PDF ----------

def _collect_portfolio(s, student_id: int) -> dict:
    """Samla ihop all data som behövs för portfolio-PDF:en."""
    student = s.query(Student).filter(Student.id == student_id).first()
    if not student:
        return {}
    profile = s.query(StudentProfile).filter(
        StudentProfile.student_id == student_id
    ).first()

    # Mastery (bara de med evidens)
    from .modules import _compute_mastery_for_student
    mastery_map = _compute_mastery_for_student(s, student_id)
    comps = s.query(Competency).all()
    mastery_rows = []
    for c in comps:
        m = mastery_map.get(c.id)
        if not m or m[1] == 0:
            continue
        mastery_rows.append({
            "competency": {"name": c.name, "level": c.level},
            "mastery": m[0],
            "evidence_count": m[1],
        })
    mastery_rows.sort(key=lambda r: -r["mastery"])

    # Reflektioner
    refs_raw = (
        s.query(StudentStepProgress, ModuleStep)
        .join(ModuleStep, StudentStepProgress.step_id == ModuleStep.id)
        .filter(
            StudentStepProgress.student_id == student_id,
            ModuleStep.kind == "reflect",
            StudentStepProgress.completed_at.isnot(None),
        )
        .order_by(StudentStepProgress.completed_at)
        .all()
    )
    reflections: list[dict] = []
    for prog, step in refs_raw:
        mod = s.query(Module).filter(Module.id == step.module_id).first()
        rubric = None
        if step.params and isinstance(step.params.get("rubric"), list):
            rubric = step.params["rubric"]
        reflections.append({
            "module_title": mod.title if mod else "—",
            "step_title": step.title,
            "step_question": step.content,
            "reflection": (prog.data or {}).get("reflection", ""),
            "teacher_feedback": prog.teacher_feedback,
            "rubric": rubric,
            "rubric_scores": prog.rubric_scores,
            "completed_at": (
                prog.completed_at.strftime("%Y-%m-%d %H:%M")
                if prog.completed_at else ""
            ),
        })

    # Modul-progress
    modules_progress: list[dict] = []
    for sm in (
        s.query(StudentModule)
        .filter(StudentModule.student_id == student_id)
        .order_by(StudentModule.sort_order)
        .all()
    ):
        mod = s.query(Module).filter(Module.id == sm.module_id).first()
        if not mod:
            continue
        step_ids = [st.id for st in mod.steps]
        completed = 0
        if step_ids:
            completed = s.query(StudentStepProgress).filter(
                StudentStepProgress.student_id == student_id,
                StudentStepProgress.step_id.in_(step_ids),
                StudentStepProgress.completed_at.isnot(None),
            ).count()
        modules_progress.append({
            "title": mod.title,
            "completed": completed,
            "total": len(step_ids),
        })

    return {
        "student": student,
        "profile": profile,
        "mastery_rows": mastery_rows,
        "reflections": reflections,
        "modules_progress": modules_progress,
    }


@router.get("/student/portfolio.pdf")
def student_portfolio_pdf(info: TokenInfo = Depends(require_token)):
    from fastapi.responses import Response
    from ..teacher.portfolio_pdf import build_portfolio_pdf
    _require_school_mode()
    if info.role != "student":
        raise HTTPException(403, "Not a student token")
    with master_session() as s:
        data = _collect_portfolio(s, info.student_id)
    if not data or not data.get("profile"):
        raise HTTPException(404, "Elev eller profil saknas")
    pdf = build_portfolio_pdf(**data)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition":
                f'attachment; filename="portfolio_{data["student"].id}.pdf"',
        },
    )


@router.get("/teacher/students/{student_id}/portfolio.pdf")
def teacher_portfolio_pdf(
    student_id: int,
    info: TokenInfo = Depends(require_teacher),
):
    from fastapi.responses import Response
    from ..teacher.portfolio_pdf import build_portfolio_pdf
    _require_school_mode()
    with master_session() as s:
        stu = s.query(Student).filter(
            Student.id == student_id,
            Student.teacher_id == info.teacher_id,
        ).first()
        if not stu:
            raise HTTPException(404, "Student not found")
        data = _collect_portfolio(s, student_id)
    if not data or not data.get("profile"):
        raise HTTPException(404, "Profil saknas")
    pdf = build_portfolio_pdf(**data)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition":
                f'attachment; filename="portfolio_{student_id}.pdf"',
        },
    )


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
            # Två format stöds:
            # - Enkel: params.correct_index (int), data.answer (int)
            # - Multi: params.correct_indices (list[int]), data.answers (list[int])
            params = st.params or {}
            multi = "correct_indices" in params
            if multi:
                answers = data.get("answers")
                if not isinstance(answers, list):
                    raise HTTPException(400, "Saknar 'answers' (lista)")
                correct = set(params.get("correct_indices") or [])
                chosen = set(a for a in answers if isinstance(a, int))
                data["correct"] = (chosen == correct)
                data["correct_indices"] = list(correct)
            else:
                answer = data.get("answer")
                if not isinstance(answer, int):
                    raise HTTPException(400, "Saknar 'answer' (int)")
                correct_index = params.get("correct_index")
                data["correct"] = (answer == correct_index)
                data["correct_index"] = correct_index
            # Bevara första svaret för mastery-räkning: mastery räknar
            # första försöket, oavsett om eleven svarar rätt senare.
            prev = s.query(StudentStepProgress).filter(
                StudentStepProgress.student_id == info.student_id,
                StudentStepProgress.step_id == step_id,
            ).first()
            if prev and prev.data and "first_correct" in prev.data:
                data["first_correct"] = prev.data["first_correct"]
                data["attempts"] = (prev.data.get("attempts") or 1) + 1
            else:
                data["first_correct"] = data["correct"]
                data["attempts"] = 1

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
