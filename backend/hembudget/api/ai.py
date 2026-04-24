"""AI-feature-endpoints (Claude API).

Alla endpoints här kräver:
 1. school-mode aktivt
 2. att den autentiserade läraren har `ai_enabled=True` (styrs via
    /admin/ai) — elever räknar mot sin lärares konto
 3. att ANTHROPIC_API_KEY är satt på servern

Om något av detta saknas → 503 Service Unavailable med tydligt meddelande
så frontend kan visa "AI-funktioner avstängda" istället för att dö.

Feature-endpoints:
 K — POST /ai/reflection/{progress_id}/feedback-suggestion
 L — POST /ai/reflection/{progress_id}/rubric-suggestion
 M — POST /ai/student/ask
 N — POST /ai/modules/generate
 O — POST /ai/category/check
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..school import is_enabled as school_enabled
from ..school import ai as ai_core
from ..school.engines import master_session
from ..school.models import (
    Module, ModuleStep, Student, StudentStepProgress, Teacher,
)
from .deps import TokenInfo, require_teacher, require_token

router = APIRouter(prefix="/ai", tags=["ai"])


def _require_school() -> None:
    if not school_enabled():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "School mode inaktivt")


def _teacher_id_for_info(info: TokenInfo) -> int:
    """Ger teacher_id oavsett om det är en lärare eller en elev — eleven
    räknar mot sin lärares konto."""
    if info.role == "teacher" and info.teacher_id:
        return info.teacher_id
    if info.role == "student" and info.student_id:
        with master_session() as s:
            stu = s.get(Student, info.student_id)
            if stu:
                return stu.teacher_id
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Okänd roll")


def _gate_ai(teacher_id: int) -> None:
    """Gate: lärarens ai_enabled måste vara True OCH klienten måste
    vara tillgänglig. Kastar 503 annars."""
    with master_session() as s:
        t = s.get(Teacher, teacher_id)
        if not t or not t.ai_enabled:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "AI-funktioner är inte aktiverade för detta konto. "
                "Be super-admin att slå på dem.",
            )
    if not ai_core.is_available():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AI-klient är inte konfigurerad på servern.",
        )


# ---------- K: AI-feedback-förslag på reflektion ----------

class FeedbackSuggestionOut(BaseModel):
    suggestion: str
    model: str
    input_tokens: int
    output_tokens: int


@router.post(
    "/reflection/{progress_id}/feedback-suggestion",
    response_model=FeedbackSuggestionOut,
)
def feedback_suggestion(
    progress_id: int,
    info: TokenInfo = Depends(require_teacher),
) -> FeedbackSuggestionOut:
    _require_school()
    teacher_id = info.teacher_id or 0
    _gate_ai(teacher_id)

    with master_session() as s:
        prog = s.get(StudentStepProgress, progress_id)
        if not prog:
            raise HTTPException(404, "Progress finns ej")
        stu = s.get(Student, prog.student_id)
        if not stu or stu.teacher_id != teacher_id:
            raise HTTPException(403, "Inte din elev")
        step = s.get(ModuleStep, prog.step_id)
        if not step or step.kind != "reflect":
            raise HTTPException(400, "Det här steget är inte en reflektion")
        module = s.query(Module).filter(Module.id == step.module_id).first()

        reflection = ""
        if prog.data and isinstance(prog.data, dict):
            reflection = str(prog.data.get("reflection", ""))
        if not reflection.strip():
            raise HTTPException(400, "Eleven har ingen reflektionstext")

        module_title = module.title if module else "—"
        step_prompt = step.content or step.title

    result = ai_core.generate_feedback_suggestion(
        reflection_text=reflection,
        module_title=module_title,
        step_prompt=step_prompt,
        teacher_id=teacher_id,
    )
    if result is None:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "AI-anropet misslyckades — försök igen senare.",
        )
    return FeedbackSuggestionOut(
        suggestion=result.text,
        model=ai_core.MODEL_HAIKU,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )


# ---------- L: AI-rubric-bedömning ----------

class RubricSuggestionOut(BaseModel):
    raw: str
    parsed: Optional[dict] = None
    model: str
    input_tokens: int
    output_tokens: int


@router.post(
    "/reflection/{progress_id}/rubric-suggestion",
    response_model=RubricSuggestionOut,
)
def rubric_suggestion(
    progress_id: int,
    info: TokenInfo = Depends(require_teacher),
) -> RubricSuggestionOut:
    _require_school()
    teacher_id = info.teacher_id or 0
    _gate_ai(teacher_id)

    with master_session() as s:
        prog = s.get(StudentStepProgress, progress_id)
        if not prog:
            raise HTTPException(404, "Progress finns ej")
        stu = s.get(Student, prog.student_id)
        if not stu or stu.teacher_id != teacher_id:
            raise HTTPException(403, "Inte din elev")
        step = s.get(ModuleStep, prog.step_id)
        if not step or step.kind != "reflect":
            raise HTTPException(400, "Steget är inte en reflektion")

        rubric = None
        if step.params and isinstance(step.params.get("rubric"), list):
            rubric = step.params["rubric"]
        if not rubric:
            raise HTTPException(400, "Inget rubric-definition på steget")

        reflection = ""
        if prog.data and isinstance(prog.data, dict):
            reflection = str(prog.data.get("reflection", ""))
        if not reflection.strip():
            raise HTTPException(400, "Eleven har ingen reflektionstext")

        step_prompt = step.content or step.title

    result = ai_core.score_with_rubric(
        rubric_json=json.dumps(rubric, ensure_ascii=False),
        reflection_text=reflection,
        step_prompt=step_prompt,
        teacher_id=teacher_id,
    )
    if result is None:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "AI-anropet misslyckades — försök igen senare.",
        )
    parsed: Optional[dict] = None
    try:
        parsed = json.loads(result.text)
    except Exception:
        parsed = None
    return RubricSuggestionOut(
        raw=result.text,
        parsed=parsed,
        model=ai_core.MODEL_SONNET,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )


# ---------- M: Elev-Q&A-chatt ----------

class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    module_id: Optional[int] = None
    step_id: Optional[int] = None


class AskOut(BaseModel):
    answer: str
    model: str
    input_tokens: int
    output_tokens: int


@router.post("/student/ask", response_model=AskOut)
def ask_student(
    payload: AskIn,
    info: TokenInfo = Depends(require_token),
) -> AskOut:
    _require_school()
    # Både elever och lärare får fråga — men läraren räknas på sitt
    # eget konto och eleven räknas på sin lärares.
    teacher_id = _teacher_id_for_info(info)
    _gate_ai(teacher_id)

    module_title = "Allmän ekonomi"
    module_summary: Optional[str] = None
    step_prompt: Optional[str] = None
    with master_session() as s:
        if payload.module_id:
            m = s.get(Module, payload.module_id)
            if m:
                module_title = m.title
                module_summary = m.summary
        if payload.step_id:
            st = s.get(ModuleStep, payload.step_id)
            if st:
                step_prompt = st.content or st.title

    result = ai_core.answer_student_question(
        question=payload.question,
        module_title=module_title,
        module_summary=module_summary,
        step_prompt=step_prompt,
        teacher_id=teacher_id,
    )
    if result is None:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "AI-anropet misslyckades — försök igen senare.",
        )
    return AskOut(
        answer=result.text,
        model=ai_core.MODEL_SONNET,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )


# ---------- N: AI-modulgenerering ----------

class ModuleGenIn(BaseModel):
    prompt: str = Field(min_length=10, max_length=2000)
    """Lärarens beskrivning — t.ex. 'En modul om att göra sin första
    månadsbudget, med fokus på att skilja på behov och önskemål'."""


class ModuleGenOut(BaseModel):
    raw: str
    parsed: Optional[dict] = None
    model: str
    input_tokens: int
    output_tokens: int


@router.post("/modules/generate", response_model=ModuleGenOut)
def generate_module(
    payload: ModuleGenIn,
    info: TokenInfo = Depends(require_teacher),
) -> ModuleGenOut:
    _require_school()
    teacher_id = info.teacher_id or 0
    _gate_ai(teacher_id)

    result = ai_core.generate_module_template(
        theme_prompt=payload.prompt,
        teacher_id=teacher_id,
    )
    if result is None:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "AI-anropet misslyckades — försök igen senare.",
        )
    parsed: Optional[dict] = None
    try:
        parsed = json.loads(result.text)
    except Exception:
        parsed = None
    return ModuleGenOut(
        raw=result.text,
        parsed=parsed,
        model=ai_core.MODEL_SONNET,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )


# ---------- O: Semantisk kategori-bedömning ----------

class CategoryCheckIn(BaseModel):
    merchant: str = Field(min_length=1, max_length=200)
    amount: float
    student_category: str = Field(min_length=1, max_length=80)
    facit_category: str = Field(min_length=1, max_length=80)


class CategoryCheckOut(BaseModel):
    is_match: bool
    confidence: float
    explanation: str
    raw: str
    model: str
    input_tokens: int
    output_tokens: int


@router.post("/category/check", response_model=CategoryCheckOut)
def check_category(
    payload: CategoryCheckIn,
    info: TokenInfo = Depends(require_token),
) -> CategoryCheckOut:
    _require_school()
    teacher_id = _teacher_id_for_info(info)
    _gate_ai(teacher_id)

    result = ai_core.check_category_semantic_match(
        merchant=payload.merchant,
        amount=payload.amount,
        student_category=payload.student_category,
        facit_category=payload.facit_category,
        teacher_id=teacher_id,
    )
    if result is None:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "AI-anropet misslyckades — försök igen senare.",
        )
    # Default: icke-matchande om JSON-parse failar — säkrast.
    is_match = False
    confidence = 0.0
    explanation = ""
    try:
        parsed = json.loads(result.text)
        is_match = bool(parsed.get("is_match"))
        confidence = float(parsed.get("confidence", 0.0))
        explanation = str(parsed.get("explanation", ""))
    except Exception:
        explanation = "Kunde inte tolka AI-svaret"
    return CategoryCheckOut(
        is_match=is_match,
        confidence=max(0.0, min(1.0, confidence)),
        explanation=explanation,
        raw=result.text,
        model=ai_core.MODEL_HAIKU,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )
