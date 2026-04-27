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
 M — POST /ai/student/ask          (icke-stream, bakåtkompat)
 M' — POST /ai/student/ask/stream  (SSE-stream)
 N — POST /ai/modules/generate
 O — POST /ai/category/check
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..school import is_enabled as school_enabled
from ..school import ai as ai_core
from ..school.engines import master_session
from ..school.models import (
    AskAiMessage, AskAiThread, Module, ModuleStep, Student,
    StudentStepProgress, Teacher,
)
from ..security.rate_limit import RULES_STUDENT_ASK, check_rate_limit
from .deps import TokenInfo, require_teacher, require_token

log = logging.getLogger(__name__)

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
    # Backwards-compat: `raw` behålls (JSON-serialiserad data) så
    # frontend som förr läste raw fortfarande fungerar.
    raw: str
    parsed: dict
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
    # tool_use garanterar att result.data följer RUBRIC_TOOL_SCHEMA —
    # inga manuella json.loads som kan krascha.
    return RubricSuggestionOut(
        raw=json.dumps(result.data, ensure_ascii=False),
        parsed=result.data,
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


def _resolve_ask_context(
    payload: AskIn,
) -> tuple[str, Optional[str], Optional[str]]:
    """Slå upp modul + steg-titel för prompt-kontext."""
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
    return module_title, module_summary, step_prompt


def _log_quick_ask(
    info: TokenInfo,
    payload: AskIn,
    module_title: str,
) -> Optional[int]:
    """Persistera elevens snabbfråga som AskAiMessage. Återanvänder en
    befintlig "Snabbfrågor: <modul>"-tråd per elev/modul så att lärar-
    vyn får en hanterbar lista istället för en tråd per fråga.

    Returnerar thread_id eller None om något gick snett. Vi sväljer fel
    avsiktligt — audit-loggning får ALDRIG blockera en AI-fråga som
    eleven betalar med tokens för.
    """
    if info.role != "student" or info.student_id is None:
        return None
    try:
        with master_session() as s:
            title = f"Snabbfrågor: {module_title}"
            existing = (
                s.query(AskAiThread)
                .filter(
                    AskAiThread.student_id == info.student_id,
                    AskAiThread.module_id == payload.module_id,
                    AskAiThread.title == title,
                )
                .order_by(AskAiThread.updated_at.desc())
                .first()
            )
            if existing:
                thread = existing
            else:
                thread = AskAiThread(
                    student_id=info.student_id,
                    teacher_id=None,
                    title=title,
                    module_id=payload.module_id,
                )
                s.add(thread)
                s.flush()
            s.add(AskAiMessage(
                thread_id=thread.id,
                role="user",
                content=payload.question,
            ))
            # Bumpa updated_at så lärar-vyn sorterar senaste högst
            thread.updated_at = datetime.utcnow()
            return thread.id
    except Exception:
        log.exception("kunde inte logga elev-snabbfråga (auditspår)")
        return None


def _log_quick_ask_answer(thread_id: Optional[int], answer: str) -> None:
    """Persistera Claudes svar i samma tråd som frågan. Tyst om fel."""
    if thread_id is None or not answer:
        return
    try:
        with master_session() as s:
            s.add(AskAiMessage(
                thread_id=thread_id,
                role="assistant",
                content=answer,
            ))
            t = s.get(AskAiThread, thread_id)
            if t:
                t.updated_at = datetime.utcnow()
    except Exception:
        log.exception("kunde inte logga AI-svar (auditspår)")


@router.post("/student/ask", response_model=AskOut)
def ask_student(
    payload: AskIn,
    request: Request,
    info: TokenInfo = Depends(require_token),
) -> AskOut:
    _require_school()
    # Rate-limit: varje elev/lärare får max 15 frågor/minut per IP så
    # ingen kan "kosta ihjäl" lärarens Anthropic-konto.
    check_rate_limit(request, "ai-ask", RULES_STUDENT_ASK)
    # Både elever och lärare får fråga — men läraren räknas på sitt
    # eget konto och eleven räknas på sin lärares.
    teacher_id = _teacher_id_for_info(info)
    _gate_ai(teacher_id)

    module_title, module_summary, step_prompt = _resolve_ask_context(payload)

    # Audit-logga elevens fråga FÖRE Claude-anropet — så lärare ser
    # frågan även om svaret skulle krascha.
    thread_id = _log_quick_ask(info, payload, module_title)

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
    _log_quick_ask_answer(thread_id, result.text)
    return AskOut(
        answer=result.text,
        model=ai_core.MODEL_SONNET,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )


# ---------- M': Streaming-variant av samma fråga ----------

@router.post("/student/ask/stream")
def ask_student_stream(
    payload: AskIn,
    request: Request,
    info: TokenInfo = Depends(require_token),
):
    """SSE-ström av Claudes svar. Klienten läser `text/event-stream` och
    uppdaterar UI:t token-för-token. Samma rate-limit + gating som den
    icke-strömmande varianten.

    Event-format:
      data: {"type": "delta", "text": "..."}
      data: {"type": "done", "input_tokens": N, "output_tokens": M}
      data: {"type": "error", "message": "..."}
    """
    _require_school()
    check_rate_limit(request, "ai-ask", RULES_STUDENT_ASK)
    teacher_id = _teacher_id_for_info(info)
    _gate_ai(teacher_id)

    module_title, module_summary, step_prompt = _resolve_ask_context(payload)

    context_parts = [f"Modul eleven jobbar med: {module_title}"]
    if module_summary:
        context_parts.append(f"Modulens syfte: {module_summary}")
    if step_prompt:
        context_parts.append(f"Aktuellt steg: {step_prompt}")
    user_prompt = "\n".join(context_parts) + f"\n\nElevens fråga:\n{payload.question}"

    # Audit-logga frågan direkt så lärare ser den även om eleven
    # avbryter strömmen mitt i.
    thread_id = _log_quick_ask(info, payload, module_title)

    def gen():
        text_parts: list[str] = []
        for chunk in ai_core.stream_claude(
            model=ai_core.MODEL_SONNET,
            system=ai_core.QA_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_tokens=ai_core.MAX_TOKENS_QA,
            use_thinking=False,  # streaming: snabb första token viktigast
            teacher_id=teacher_id,
        ):
            if chunk.get("type") == "delta":
                text_parts.append(chunk.get("text", ""))
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        # Persistera assistant-svaret när strömmen är klar
        _log_quick_ask_answer(thread_id, "".join(text_parts).strip())

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Cloud Run + Cloudflare buffrar gzip:ade SSE-strömmar; stäng
            # av det så token:arna kommer ut direkt.
            "X-Accel-Buffering": "no",
        },
    )


# ---------- M''': Streaming-förklaring av ett felaktigt quiz-svar ----------

class QuizExplainIn(BaseModel):
    step_id: int


@router.post("/student/quiz-explain/stream")
def quiz_explain_stream(
    payload: QuizExplainIn,
    request: Request,
    info: TokenInfo = Depends(require_token),
):
    """Strömmar en pedagogisk förklaring av varför elevens senaste svar
    på quiz-steget var fel. Anropet är idempotent — ingen DB-skrivning,
    ingen påverkan på mastery. Kräver att steget är slutfört och att
    data.correct är False."""
    _require_school()
    check_rate_limit(request, "ai-ask", RULES_STUDENT_ASK)
    teacher_id = _teacher_id_for_info(info)
    _gate_ai(teacher_id)

    with master_session() as s:
        step = s.get(ModuleStep, payload.step_id)
        if not step or step.kind != "quiz":
            raise HTTPException(400, "Steget är inte en quiz")
        prog = s.query(StudentStepProgress).filter(
            StudentStepProgress.student_id == info.student_id,
            StudentStepProgress.step_id == payload.step_id,
        ).first()
        if not prog or not prog.data:
            raise HTTPException(400, "Du har inte svarat på frågan än")
        data = prog.data if isinstance(prog.data, dict) else {}
        if data.get("correct") is not False:
            raise HTTPException(400, "Ditt svar var rätt")

        params = step.params or {}
        question = str(params.get("question") or step.content or step.title)
        options: list[str] = list(params.get("options") or [])

        multi = "correct_indices" in params
        if multi:
            chosen_idx: list[int] = list(data.get("answers") or [])
            correct_idx: list[int] = list(params.get("correct_indices") or [])
        else:
            chosen_single = data.get("answer")
            chosen_idx = [chosen_single] if isinstance(chosen_single, int) else []
            ci = params.get("correct_index")
            correct_idx = [ci] if isinstance(ci, int) else []

    def label(idxs: list[int]) -> str:
        if not idxs or not options:
            return "(okänt)"
        return " + ".join(
            options[i] for i in idxs if 0 <= i < len(options)
        ) or "(okänt)"

    user_prompt = (
        f"Fråga:\n{question}\n\n"
        f"Alla svarsalternativ:\n"
        + "\n".join(f"- {o}" for o in options)
        + f"\n\nElevens val: {label(chosen_idx)}\n"
        f"Rätt svar: {label(correct_idx)}\n\n"
        "Förklara pedagogiskt varför elevens val inte stämmer, utan att döma."
    )

    def gen():
        for chunk in ai_core.stream_claude(
            model=ai_core.MODEL_SONNET,
            system=ai_core.QUIZ_EXPLAIN_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_tokens=350,
            use_thinking=False,
            teacher_id=teacher_id,
        ):
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------- N: AI-modulgenerering ----------

class ModuleGenIn(BaseModel):
    prompt: str = Field(min_length=10, max_length=2000)
    """Lärarens beskrivning — t.ex. 'En modul om att göra sin första
    månadsbudget, med fokus på att skilja på behov och önskemål'."""


class ModuleGenOut(BaseModel):
    raw: str
    parsed: dict
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
    return ModuleGenOut(
        raw=json.dumps(result.data, ensure_ascii=False),
        parsed=result.data,
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
    # tool_use-schemat garanterar nycklarna — ingen defensiv parse-logik.
    is_match = bool(result.data["is_match"])
    confidence = float(result.data["confidence"])
    explanation = str(result.data["explanation"])
    return CategoryCheckOut(
        is_match=is_match,
        confidence=max(0.0, min(1.0, confidence)),
        explanation=explanation,
        raw=json.dumps(result.data, ensure_ascii=False),
        model=ai_core.MODEL_HAIKU,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )


# ---------- Kategori-förklaring (streamande follow-up) ----------

class CategoryExplainIn(BaseModel):
    merchant: str = Field(min_length=1, max_length=200)
    amount: float
    student_category: str = Field(min_length=1, max_length=80)
    facit_category: str = Field(min_length=1, max_length=80)


@router.post("/category/explain/stream")
def category_explain_stream(
    payload: CategoryExplainIn,
    request: Request,
    info: TokenInfo = Depends(require_token),
):
    """Streamar en pedagogisk förklaring av varför facit-kategorin
    skiljer sig från elevens val. Idempotent (ingen DB-skrivning)."""
    _require_school()
    check_rate_limit(request, "ai-ask", RULES_STUDENT_ASK)
    teacher_id = _teacher_id_for_info(info)
    _gate_ai(teacher_id)

    prompt = (
        f"Transaktion: {payload.merchant} ({payload.amount:.0f} kr)\n"
        f"Läraren tänkte: {payload.facit_category}\n"
        f"Elev-val: {payload.student_category}\n\n"
        "Förklara pedagogiskt skillnaden."
    )

    def gen():
        for chunk in ai_core.stream_claude(
            model=ai_core.MODEL_HAIKU,
            system=ai_core.CATEGORY_EXPLAIN_SYSTEM_PROMPT,
            user_prompt=prompt,
            max_tokens=350,
            use_thinking=False,
            teacher_id=teacher_id,
        ):
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------- AI-elevsammanfattning för lärare ----------

class StudentSummaryOut(BaseModel):
    student_id: int
    strengths: str
    gaps: str
    next_steps: str
    model: str
    input_tokens: int
    output_tokens: int


@router.post(
    "/teacher/students/{student_id}/summary",
    response_model=StudentSummaryOut,
)
def student_summary(
    student_id: int,
    info: TokenInfo = Depends(require_teacher),
) -> StudentSummaryOut:
    """AI-genererad lägesbild (styrkor/gap/nästa steg). Bygger context
    från mastery + senaste reflektioner + uppdragsstatus och skickar
    allt i en enda Sonnet-anrop med tool_use för strukturerad output."""
    _require_school()
    teacher_id = info.teacher_id or 0
    _gate_ai(teacher_id)

    with master_session() as s:
        stu = s.query(Student).filter(
            Student.id == student_id,
            Student.teacher_id == teacher_id,
        ).first()
        if not stu:
            raise HTTPException(404, "Elev finns inte eller tillhör inte dig")

        # Mastery
        from .modules import _compute_mastery_for_student
        from ..school.models import Competency, StudentStepProgress as _Prog, ModuleStep as _Step
        from ..school.models import Assignment as _A
        mastery = _compute_mastery_for_student(s, student_id)
        comps = {
            c.id: c for c in s.query(Competency).all()
        }
        mastery_lines = []
        for cid, (m, ev, _) in sorted(
            mastery.items(), key=lambda kv: -kv[1][0],
        ):
            c = comps.get(cid)
            if not c:
                continue
            mastery_lines.append(
                f"- {c.name} ({c.level}): {round(m*100)}% "
                f"[{ev} bevis]"
            )

        # Senaste reflektioner (upp till 5)
        reflect_rows = (
            s.query(_Prog, _Step)
            .join(_Step, _Prog.step_id == _Step.id)
            .filter(
                _Prog.student_id == student_id,
                _Step.kind == "reflect",
                _Prog.completed_at.isnot(None),
            )
            .order_by(_Prog.completed_at.desc())
            .limit(5)
            .all()
        )
        reflect_lines = []
        for p, st in reflect_rows:
            text = ""
            if isinstance(p.data, dict):
                text = str(p.data.get("reflection", ""))[:400]
            reflect_lines.append(f"* \"{st.title}\": {text}")

        # Uppdrag
        a_rows = (
            s.query(_A)
            .filter(_A.student_id == student_id)
            .order_by(_A.created_at.desc())
            .limit(10)
            .all()
        )
        a_lines = []
        for a in a_rows:
            state = "klart" if a.manually_completed_at else "öppet"
            a_lines.append(f"- {a.title} ({a.kind}, {state})")

        name = stu.display_name

    context_bundle = (
        f"Elev: {name} (id={student_id})\n\n"
        "Mastery (högst först):\n" + ("\n".join(mastery_lines) or "(ingen data)")
        + "\n\nSenaste reflektioner:\n"
        + ("\n".join(reflect_lines) or "(inga)")
        + "\n\nUppdrag:\n"
        + ("\n".join(a_lines) or "(inga)")
    )

    result = ai_core.generate_student_summary(
        context_bundle=context_bundle,
        teacher_id=teacher_id,
    )
    if result is None:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "AI-anropet misslyckades — försök igen senare.",
        )
    return StudentSummaryOut(
        student_id=student_id,
        strengths=str(result.data.get("strengths", "")),
        gaps=str(result.data.get("gaps", "")),
        next_steps=str(result.data.get("next_steps", "")),
        model=ai_core.MODEL_SONNET,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )


# ---------- Multi-turn AskAI-trådar ----------

class ThreadSummary(BaseModel):
    id: int
    title: Optional[str]
    module_id: Optional[int]
    created_at: str
    updated_at: str
    message_count: int


class ThreadMessage(BaseModel):
    id: int
    role: str
    content: str
    created_at: str


class ThreadDetail(ThreadSummary):
    messages: list[ThreadMessage]


def _owner_filter(info: TokenInfo):
    """(clause, write_context) — vem äger trådar för detta token?"""
    if info.role == "student":
        return AskAiThread.student_id == info.student_id, {
            "student_id": info.student_id,
        }
    if info.role == "teacher":
        # Lärares egna trådar (skilda från deras elevers)
        return (
            (AskAiThread.teacher_id == info.teacher_id)
            & (AskAiThread.student_id.is_(None))
        ), {"teacher_id": info.teacher_id}
    return None, None


@router.get(
    "/teacher/students/{student_id}/threads",
    response_model=list[ThreadSummary],
)
def teacher_list_student_threads(
    student_id: int,
    info: TokenInfo = Depends(require_teacher),
) -> list[ThreadSummary]:
    """Lärar-vy: alla AskAI-trådar (snabbfrågor + multi-turn) som
    eleven har öppnat. Läraren ser elevens AI-historik utan att behöva
    impersonera. Audit-spår för bedömning + missbruksskydd."""
    _require_school()
    with master_session() as s:
        stu = s.query(Student).filter(
            Student.id == student_id,
            Student.teacher_id == info.teacher_id,
        ).first()
        if not stu:
            raise HTTPException(404, "Student not found")
        threads = (
            s.query(AskAiThread)
            .filter(AskAiThread.student_id == student_id)
            .order_by(AskAiThread.updated_at.desc())
            .limit(50)
            .all()
        )
        out: list[ThreadSummary] = []
        for t in threads:
            n = (
                s.query(AskAiMessage)
                .filter(AskAiMessage.thread_id == t.id)
                .count()
            )
            out.append(ThreadSummary(
                id=t.id, title=t.title, module_id=t.module_id,
                created_at=t.created_at.isoformat(),
                updated_at=t.updated_at.isoformat(),
                message_count=n,
            ))
        return out


@router.get(
    "/teacher/students/{student_id}/threads/{thread_id}",
    response_model=ThreadDetail,
)
def teacher_get_student_thread(
    student_id: int,
    thread_id: int,
    info: TokenInfo = Depends(require_teacher),
) -> ThreadDetail:
    """Hämta en specifik AskAI-tråd för en av lärarens elever, med alla
    meddelanden. Används från StudentDetail-sidan."""
    _require_school()
    with master_session() as s:
        stu = s.query(Student).filter(
            Student.id == student_id,
            Student.teacher_id == info.teacher_id,
        ).first()
        if not stu:
            raise HTTPException(404, "Student not found")
        t = s.query(AskAiThread).filter(
            AskAiThread.id == thread_id,
            AskAiThread.student_id == student_id,
        ).first()
        if not t:
            raise HTTPException(404, "Tråd finns ej")
        msgs = (
            s.query(AskAiMessage)
            .filter(AskAiMessage.thread_id == thread_id)
            .order_by(AskAiMessage.created_at.asc())
            .all()
        )
        return ThreadDetail(
            id=t.id, title=t.title, module_id=t.module_id,
            created_at=t.created_at.isoformat(),
            updated_at=t.updated_at.isoformat(),
            message_count=len(msgs),
            messages=[
                ThreadMessage(
                    id=m.id, role=m.role, content=m.content,
                    created_at=m.created_at.isoformat(),
                ) for m in msgs
            ],
        )


@router.get("/student/threads", response_model=list[ThreadSummary])
def list_threads(
    info: TokenInfo = Depends(require_token),
) -> list[ThreadSummary]:
    _require_school()
    clause, _ = _owner_filter(info)
    if clause is None:
        raise HTTPException(403, "Okänd roll")
    with master_session() as s:
        threads = (
            s.query(AskAiThread)
            .filter(clause)
            .order_by(AskAiThread.updated_at.desc())
            .limit(50)
            .all()
        )
        out: list[ThreadSummary] = []
        for t in threads:
            n = (
                s.query(AskAiMessage)
                .filter(AskAiMessage.thread_id == t.id)
                .count()
            )
            out.append(ThreadSummary(
                id=t.id, title=t.title, module_id=t.module_id,
                created_at=t.created_at.isoformat(),
                updated_at=t.updated_at.isoformat(),
                message_count=n,
            ))
        return out


@router.get("/student/threads/{thread_id}", response_model=ThreadDetail)
def get_thread(
    thread_id: int,
    info: TokenInfo = Depends(require_token),
) -> ThreadDetail:
    _require_school()
    clause, _ = _owner_filter(info)
    if clause is None:
        raise HTTPException(403, "Okänd roll")
    with master_session() as s:
        t = s.query(AskAiThread).filter(
            AskAiThread.id == thread_id,
        ).filter(clause).first()
        if not t:
            raise HTTPException(404, "Tråd finns ej")
        msgs = (
            s.query(AskAiMessage)
            .filter(AskAiMessage.thread_id == thread_id)
            .order_by(AskAiMessage.created_at.asc())
            .all()
        )
        return ThreadDetail(
            id=t.id, title=t.title, module_id=t.module_id,
            created_at=t.created_at.isoformat(),
            updated_at=t.updated_at.isoformat(),
            message_count=len(msgs),
            messages=[
                ThreadMessage(
                    id=m.id, role=m.role, content=m.content,
                    created_at=m.created_at.isoformat(),
                ) for m in msgs
            ],
        )


@router.delete("/student/threads/{thread_id}")
def delete_thread(
    thread_id: int,
    info: TokenInfo = Depends(require_token),
) -> dict:
    _require_school()
    clause, _ = _owner_filter(info)
    if clause is None:
        raise HTTPException(403, "Okänd roll")
    with master_session() as s:
        t = s.query(AskAiThread).filter(
            AskAiThread.id == thread_id,
        ).filter(clause).first()
        if not t:
            raise HTTPException(404, "Tråd finns ej")
        s.delete(t)
    return {"ok": True}


class AskThreadIn(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    thread_id: Optional[int] = None
    module_id: Optional[int] = None
    step_id: Optional[int] = None


def _adaptive_system_prompt(teacher_id: int, student_id: Optional[int]) -> str:
    """Bygger systempromprompten. Om elev: lägger till mastery-summery
    så Sonnet kan anpassa språknivå (låg mastery → mer Socrates, högre
    mastery → direkt svar)."""
    base = ai_core.QA_SYSTEM_PROMPT
    if student_id is None:
        return base
    try:
        from .modules import _compute_mastery_for_student
        with master_session() as s:
            mastery = _compute_mastery_for_student(s, student_id)
            if not mastery:
                return base
            # 3 högst mastery-kompetenser + 3 lägst
            ranked = sorted(
                mastery.items(), key=lambda kv: -kv[1][0],
            )
            top = ranked[:3]
            bottom = [x for x in ranked if x[1][0] < 0.25][-3:]
            from ..school.models import Competency as _C
            comp_names = {
                c.id: c.name for c in s.query(_C).filter(
                    _C.id.in_([k for k, _ in ranked])
                ).all()
            }
            sections: list[str] = []
            if top:
                strong = ", ".join(
                    f"{comp_names.get(k, '?')} ({round(v[0]*100)}%)"
                    for k, v in top
                )
                sections.append(f"Elevens starka områden: {strong}.")
            if bottom:
                weak = ", ".join(
                    f"{comp_names.get(k, '?')}"
                    for k, v in bottom
                )
                sections.append(
                    f"Behöver mer grund i: {weak}. Ställ hellre en "
                    "följdfråga än ge komplett svar direkt på dessa."
                )
            if sections:
                return base + "\n\n" + "\n".join(sections)
    except Exception:
        pass
    return base


@router.post("/student/threads/message/stream")
def thread_message_stream(
    payload: AskThreadIn,
    request: Request,
    info: TokenInfo = Depends(require_token),
):
    """Skicka ett nytt user-meddelande till en tråd (eller skapa en ny
    tråd om thread_id saknas). Persisterar user-meddelandet direkt, och
    streamar Claudes svar. När strömmen stänger persisteras assistant-
    meddelandet också.

    Format: samma SSE som /ai/student/ask/stream, plus ett första event
    `{"type": "thread", "thread_id": N}` innan deltas börjar strömma.
    """
    _require_school()
    check_rate_limit(request, "ai-ask", RULES_STUDENT_ASK)
    teacher_id = _teacher_id_for_info(info)
    _gate_ai(teacher_id)

    # Hitta eller skapa tråd + persistera user-message, plocka ut historiken
    with master_session() as s:
        thread: Optional[AskAiThread] = None
        if payload.thread_id is not None:
            clause, _ = _owner_filter(info)
            thread = s.query(AskAiThread).filter(
                AskAiThread.id == payload.thread_id,
            ).filter(clause).first()
            if not thread:
                raise HTTPException(404, "Tråd finns ej")
        if thread is None:
            thread = AskAiThread(
                student_id=info.student_id if info.role == "student" else None,
                teacher_id=info.teacher_id if info.role == "teacher" else None,
                title=payload.question[:80],
                module_id=payload.module_id,
            )
            s.add(thread); s.flush()

        # Spara user-meddelande direkt
        s.add(AskAiMessage(
            thread_id=thread.id,
            role="user",
            content=payload.question,
        ))
        s.flush()
        thread_id = thread.id

        # Bygg full historik för Claude
        history = [
            {"role": m.role, "content": m.content}
            for m in s.query(AskAiMessage).filter(
                AskAiMessage.thread_id == thread_id,
            ).order_by(AskAiMessage.created_at.asc()).all()
        ]

    # Module/step-kontext blir första user-meddelandets kontext
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

    system_prompt = _adaptive_system_prompt(
        teacher_id,
        info.student_id if info.role == "student" else None,
    )
    # Prefixa sista user-meddelandet med kontext så Sonnet ser var
    # eleven är i kursplanen.
    if history and (module_title or step_prompt):
        ctx = [f"Modul eleven jobbar med: {module_title}"]
        if module_summary:
            ctx.append(f"Modulens syfte: {module_summary}")
        if step_prompt:
            ctx.append(f"Aktuellt steg: {step_prompt}")
        original_last = history[-1]["content"]
        history[-1] = {
            "role": "user",
            "content": "\n".join(ctx) + "\n\nFråga:\n" + original_last,
        }

    def gen():
        yield f"data: {json.dumps({'type': 'thread', 'thread_id': thread_id})}\n\n"
        text_parts: list[str] = []
        for chunk in ai_core.stream_claude(
            model=ai_core.MODEL_SONNET,
            system=system_prompt,
            messages=history,
            max_tokens=ai_core.MAX_TOKENS_QA,
            use_thinking=False,
            teacher_id=teacher_id,
        ):
            if chunk.get("type") == "delta":
                text_parts.append(chunk.get("text", ""))
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        # Persistera assistant-svar när strömmen är klar
        final = "".join(text_parts).strip()
        if final:
            with master_session() as s:
                s.add(AskAiMessage(
                    thread_id=thread_id, role="assistant", content=final,
                ))

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------- Aktie-features (D4) ----------

class StockTermIn(BaseModel):
    term: str


class StockTermOut(BaseModel):
    explanation: str
    model: str
    input_tokens: int
    output_tokens: int


@router.post("/stocks/explain-term", response_model=StockTermOut)
def stock_explain_term(
    payload: StockTermIn,
    request: Request,
    info: TokenInfo = Depends(require_token),
) -> StockTermOut:
    """Förklarar en aktieterm pedagogiskt på lättläst svenska."""
    _require_school()
    check_rate_limit(request, "ai-stock-term", RULES_STUDENT_ASK)
    teacher_id = _teacher_id_for_info(info)
    _gate_ai(teacher_id)
    result = ai_core.explain_stock_term(
        term=payload.term, teacher_id=teacher_id,
    )
    if result is None:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "AI-anropet misslyckades.",
        )
    return StockTermOut(
        explanation=result.text,
        model=ai_core.MODEL_HAIKU,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )


class TradeFeedbackIn(BaseModel):
    side: str
    ticker: str
    stock_name: str
    sector: str
    quantity: int
    price: float
    courtage: float
    total: float
    student_rationale: str | None = None


class TradeFeedbackOut(BaseModel):
    feedback: str
    model: str
    input_tokens: int
    output_tokens: int


@router.post("/stocks/trade-feedback", response_model=TradeFeedbackOut)
def stock_trade_feedback(
    payload: TradeFeedbackIn,
    request: Request,
    info: TokenInfo = Depends(require_token),
) -> TradeFeedbackOut:
    """Pedagogisk reflektion efter ett köp/sälj. Inga rekommendationer."""
    _require_school()
    check_rate_limit(request, "ai-stock-feedback", RULES_STUDENT_ASK)
    teacher_id = _teacher_id_for_info(info)
    _gate_ai(teacher_id)
    if payload.side not in ("buy", "sell"):
        raise HTTPException(400, "side måste vara 'buy' eller 'sell'")
    result = ai_core.feedback_on_trade(
        side=payload.side,
        ticker=payload.ticker,
        stock_name=payload.stock_name,
        sector=payload.sector,
        quantity=payload.quantity,
        price=payload.price,
        courtage=payload.courtage,
        total=payload.total,
        student_rationale=payload.student_rationale,
        teacher_id=teacher_id,
    )
    if result is None:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "AI-anropet misslyckades.",
        )
    return TradeFeedbackOut(
        feedback=result.text,
        model=ai_core.MODEL_HAIKU,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )


class DiversificationIn(BaseModel):
    sector_weights: dict[str, float]
    n_holdings: int


class DiversificationOut(BaseModel):
    feedback: str
    model: str
    input_tokens: int
    output_tokens: int


@router.post("/stocks/evaluate-diversification", response_model=DiversificationOut)
def stock_evaluate_diversification(
    payload: DiversificationIn,
    request: Request,
    info: TokenInfo = Depends(require_token),
) -> DiversificationOut:
    """Bedömer portföljens diversifiering pedagogiskt."""
    _require_school()
    check_rate_limit(request, "ai-stock-diversify", RULES_STUDENT_ASK)
    teacher_id = _teacher_id_for_info(info)
    _gate_ai(teacher_id)
    result = ai_core.evaluate_diversification(
        sector_weights=payload.sector_weights,
        n_holdings=payload.n_holdings,
        teacher_id=teacher_id,
    )
    if result is None:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "AI-anropet misslyckades.",
        )
    return DiversificationOut(
        feedback=result.text,
        model=ai_core.MODEL_HAIKU,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )


# ---------- Wellbeing AI-endpoints (Fas 6) ----------

class WellbeingMonthlyIn(BaseModel):
    year_month: str
    total_score: int
    economy: int
    health: int
    social: int
    leisure: int
    safety: int
    events_accepted: int
    events_declined: int
    budget_violations: int
    decline_streak: int


class WellbeingFeedbackOut(BaseModel):
    feedback: str
    model: str
    input_tokens: int
    output_tokens: int


@router.post("/wellbeing/monthly-feedback", response_model=WellbeingFeedbackOut)
def wellbeing_monthly_feedback(
    payload: WellbeingMonthlyIn,
    request: Request,
    info: TokenInfo = Depends(require_token),
) -> WellbeingFeedbackOut:
    """Pedagogisk månadsreflektion baserat på elevens Wellbeing."""
    _require_school()
    check_rate_limit(request, "ai-wellbeing-monthly", RULES_STUDENT_ASK)
    teacher_id = _teacher_id_for_info(info)
    _gate_ai(teacher_id)
    result = ai_core.monthly_wellbeing_feedback(
        year_month=payload.year_month,
        total_score=payload.total_score,
        economy=payload.economy,
        health=payload.health,
        social=payload.social,
        leisure=payload.leisure,
        safety=payload.safety,
        events_accepted=payload.events_accepted,
        events_declined=payload.events_declined,
        budget_violations=payload.budget_violations,
        decline_streak=payload.decline_streak,
        teacher_id=teacher_id,
    )
    if result is None:
        detail = "AI-anropet misslyckades."
        last = ai_core.get_last_error()
        if last:
            detail = f"AI-anropet misslyckades: {last}"
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail,
        )
    return WellbeingFeedbackOut(
        feedback=result.text,
        model=ai_core.MODEL_HAIKU,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )


class DeclineNudgeIn(BaseModel):
    streak_count: int
    recent_categories: list[str] = []


class DeclineNudgeOut(BaseModel):
    nudge: str
    model: str
    input_tokens: int
    output_tokens: int


@router.post("/wellbeing/decline-nudge", response_model=DeclineNudgeOut)
def wellbeing_decline_nudge(
    payload: DeclineNudgeIn,
    request: Request,
    info: TokenInfo = Depends(require_token),
) -> DeclineNudgeOut:
    """Sokratisk nudge när eleven nekat 3+ events i rad."""
    _require_school()
    check_rate_limit(request, "ai-decline-nudge", RULES_STUDENT_ASK)
    teacher_id = _teacher_id_for_info(info)
    _gate_ai(teacher_id)
    result = ai_core.decline_streak_nudge(
        streak_count=payload.streak_count,
        recent_categories=payload.recent_categories,
        teacher_id=teacher_id,
    )
    if result is None:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "AI-anropet misslyckades.")
    return DeclineNudgeOut(
        nudge=result.text,
        model=ai_core.MODEL_HAIKU,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )


class InviteMotivationIn(BaseModel):
    inviter_name: str
    event_title: str
    cost: float
    cost_split_model: str
    swish_amount: float
    student_balance: float
    student_savings: float


class InviteMotivationOut(BaseModel):
    note: str
    model: str
    input_tokens: int
    output_tokens: int


@router.post(
    "/wellbeing/invite-motivation", response_model=InviteMotivationOut,
)
def wellbeing_invite_motivation(
    payload: InviteMotivationIn,
    request: Request,
    info: TokenInfo = Depends(require_token),
) -> InviteMotivationOut:
    """Neutral kommentar när klasskompis bjuder. Hjälper se båda sidor."""
    _require_school()
    check_rate_limit(request, "ai-invite-motivation", RULES_STUDENT_ASK)
    teacher_id = _teacher_id_for_info(info)
    _gate_ai(teacher_id)
    result = ai_core.class_invite_motivation(
        inviter_name=payload.inviter_name,
        event_title=payload.event_title,
        cost=payload.cost,
        cost_split_model=payload.cost_split_model,
        swish_amount=payload.swish_amount,
        student_balance=payload.student_balance,
        student_savings=payload.student_savings,
        teacher_id=teacher_id,
    )
    if result is None:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "AI-anropet misslyckades.")
    return InviteMotivationOut(
        note=result.text,
        model=ai_core.MODEL_HAIKU,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )
