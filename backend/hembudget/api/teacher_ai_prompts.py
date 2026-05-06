"""Lärar-API för att anpassa AI-systempromptar.

Endpoints:
* GET    /v2/teacher/ai-prompts/registry           — lista alla controllable prompts
* GET    /v2/teacher/ai-prompts                    — lärarens overrides
* PUT    /v2/teacher/ai-prompts/{key}              — spara override
* DELETE /v2/teacher/ai-prompts/{key}              — ta bort override (fall tillbaka default)
* POST   /v2/teacher/ai-prompts/{key}/preview      — kör prompten med exempel-input

Spec: dev/teacher-ai-prompts.md (fas 1-4)
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from .deps import TokenInfo, require_token
from ..school.ai_prompt_registry import (
    PromptCategory,
    get_all_specs,
    get_spec,
)


log = logging.getLogger(__name__)

router = APIRouter(prefix="/v2/teacher/ai-prompts", tags=["teacher-ai"])


def _require_teacher(info: TokenInfo) -> int:
    if info.role != "teacher" or info.teacher_id is None:
        raise HTTPException(403, "Endast lärare")
    return info.teacher_id


# === Schemas ===

class PromptSpecOut(BaseModel):
    key: str
    label: str
    category: str
    description: str
    default_text: str
    variables: list[str]
    used_at: str
    model: str
    preview_input: str


class PromptOverrideOut(BaseModel):
    key: str
    custom_text: str
    is_active: bool
    updated_at: Optional[str] = None


class PromptUpdateIn(BaseModel):
    custom_text: str = Field(..., max_length=8000)
    is_active: bool = True


class PromptPreviewIn(BaseModel):
    """Förhandsgranska — skicka custom_text som inte (nödvändigtvis)
    är sparad än, plus ev. extra preview-input. Returnerar AI-svaret."""
    custom_text: Optional[str] = Field(default=None, max_length=8000)
    preview_input: Optional[str] = Field(default=None, max_length=4000)


class PromptPreviewOut(BaseModel):
    output_text: str
    input_tokens: int
    output_tokens: int
    model: str


# === Endpoints ===

@router.get("/registry", response_model=list[PromptSpecOut])
def list_registry(info: TokenInfo = Depends(require_token)):
    """Lista alla AI-prompts läraren får anpassa.

    Innehåller default-text + metadata (kategori, vilka variabler
    som finns, vilken modell, var prompten triggas). UI:n bygger
    sin lista från detta · ingen klient-side hardcoding."""
    _require_teacher(info)
    return [PromptSpecOut(**s.to_dict()) for s in get_all_specs()]


@router.get("", response_model=list[PromptOverrideOut])
def list_overrides(info: TokenInfo = Depends(require_token)):
    """Hämta lärarens befintliga overrides. Bara nycklar som faktiskt
    har en rad returneras · UI:n läser detta + registry:n och slår
    samman."""
    teacher_id = _require_teacher(info)
    from ..school.engines import master_session
    from ..school.models import TeacherAiPrompt
    with master_session() as s:
        rows = (
            s.query(TeacherAiPrompt)
            .filter(TeacherAiPrompt.teacher_id == teacher_id)
            .all()
        )
        return [
            PromptOverrideOut(
                key=r.prompt_key,
                custom_text=r.custom_text or "",
                is_active=r.is_active,
                updated_at=r.updated_at.isoformat() if r.updated_at else None,
            )
            for r in rows
        ]


@router.put("/{key}", response_model=PromptOverrideOut)
def upsert_override(
    key: str,
    body: PromptUpdateIn,
    info: TokenInfo = Depends(require_token),
):
    """Spara lärarens custom-text för en prompt. Validerar att alla
    obligatoriska {variabler} finns kvar i texten.

    Skapar ny rad om ingen finns, uppdaterar annars. is_active=False
    gör att default används · custom_text bevaras så läraren kan
    slå på/av utan att radera sin variant."""
    teacher_id = _require_teacher(info)
    spec = get_spec(key)
    if spec is None:
        raise HTTPException(404, f"Okänd prompt-key: {key}")

    custom_text = (body.custom_text or "").strip()

    # Validera att alla obligatoriska variabler finns kvar (om någon)
    if custom_text and spec.variables:
        missing = [v for v in spec.variables if v not in custom_text]
        if missing:
            raise HTTPException(
                400,
                "Custom-text saknar obligatoriska variabler: "
                + ", ".join(missing)
                + ". Använd dem för att Maria/Mats ska få elev-data.",
            )

    from ..school.engines import master_session
    from ..school.models import TeacherAiPrompt
    with master_session() as s:
        row = (
            s.query(TeacherAiPrompt)
            .filter(
                TeacherAiPrompt.teacher_id == teacher_id,
                TeacherAiPrompt.prompt_key == key,
            )
            .first()
        )
        if row is None:
            row = TeacherAiPrompt(
                teacher_id=teacher_id,
                prompt_key=key,
                custom_text=custom_text,
                is_active=body.is_active,
            )
            s.add(row)
        else:
            row.custom_text = custom_text
            row.is_active = body.is_active
        s.commit()
        s.refresh(row)
        return PromptOverrideOut(
            key=row.prompt_key,
            custom_text=row.custom_text or "",
            is_active=row.is_active,
            updated_at=row.updated_at.isoformat() if row.updated_at else None,
        )


@router.delete("/{key}", status_code=204)
def delete_override(
    key: str,
    info: TokenInfo = Depends(require_token),
):
    """Ta bort lärarens override · default-prompten används från och
    med nästa AI-anrop. Idempotent — 204 även om ingen rad fanns."""
    teacher_id = _require_teacher(info)
    from ..school.engines import master_session
    from ..school.models import TeacherAiPrompt
    with master_session() as s:
        row = (
            s.query(TeacherAiPrompt)
            .filter(
                TeacherAiPrompt.teacher_id == teacher_id,
                TeacherAiPrompt.prompt_key == key,
            )
            .first()
        )
        if row is not None:
            s.delete(row)
            s.commit()


@router.post("/{key}/preview", response_model=PromptPreviewOut)
def preview_prompt(
    key: str,
    body: PromptPreviewIn,
    info: TokenInfo = Depends(require_token),
):
    """Förhandsgranska en prompt mot ett exempel-input. Använder
    EJ-sparad custom_text om sådan skickats, annars befintlig
    override eller default. AI-svaret räknas mot lärarens token-
    konto precis som vanliga elev-anrop."""
    teacher_id = _require_teacher(info)
    spec = get_spec(key)
    if spec is None:
        raise HTTPException(404, f"Okänd prompt-key: {key}")

    from ..school import ai as _ai
    if not _ai.is_available():
        raise HTTPException(
            503, "AI är inte konfigurerad (ANTHROPIC_API_KEY saknas)",
        )
    if not _ai.is_enabled_for_teacher(teacher_id):
        raise HTTPException(
            503, "AI är avstängd för ditt konto · kontakta super-admin",
        )

    # System-text att använda · prio: explicit body.custom_text > sparad
    # override > default. Variabel-substitution sker bara om template
    # innehåller {employer} etc · annars används texten som den är.
    system_text = body.custom_text
    if system_text is None or not system_text.strip():
        system_text = _ai.resolve_prompt(
            key, teacher_id=teacher_id, default=spec.default_text,
        )

    # Substituera ev. variabler med dummy-värden så preview funkar
    # även för Maria/Mats-promptarna (som annars kraschar på
    # KeyError vid {employer}).
    if spec.variables:
        dummy_vars = _make_dummy_vars(spec.variables)
        try:
            system_text = system_text.format(**dummy_vars)
        except (KeyError, IndexError) as exc:
            raise HTTPException(
                400,
                f"Custom-text saknar variabel: {exc}. Lägg till alla "
                "obligatoriska variabler innan du sparar.",
            )

    user_text = body.preview_input or spec.preview_input

    # Modell-val · haiku/sonnet baserat på spec
    model = _ai.MODEL_HAIKU if spec.model == "haiku" else _ai.MODEL_SONNET

    try:
        result = _ai._call_claude(
            model=model,
            system=system_text,
            user_prompt=user_text,
            max_tokens=600,
            teacher_id=teacher_id,
        )
        if result is None:
            raise HTTPException(503, "AI-anrop misslyckades")
        return PromptPreviewOut(
            output_text=result.text,
            input_tokens=result.usage_input_tokens,
            output_tokens=result.usage_output_tokens,
            model=spec.model,
        )
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("preview_prompt failed för key=%s", key)
        raise HTTPException(500, f"AI-fel: {exc}")


def _make_dummy_vars(variables: list[str]) -> dict[str, object]:
    """Bygg en dict med exempel-värden för alla deklarerade variabler.
    Används vid preview så template.format() inte kraschar."""
    out: dict[str, object] = {}
    for v in variables:
        # v är "{name}" · plocka bort {} för dict-key
        name = v.strip("{}").strip()
        if not name:
            continue
        # Numeriska defaultar
        if name in (
            "salary", "gross_salary", "years", "tenure_months",
            "round_no", "max_rounds", "score", "market_avg",
        ):
            out[name] = 30000 if "salary" in name or "market" in name else 1
        elif name in ("pct",):
            out[name] = 2.5
        elif name == "trend":
            out[name] = "stabil"
        elif name == "events_summary":
            out[name] = "inga"
        elif name == "performance":
            out[name] = "bra"
        elif name == "rubric_json":
            out[name] = '{"criteria":[]}'
        elif name == "archetype":
            out[name] = "vard_underskoterska"
        elif name == "agreement_name":
            out[name] = "Vårdförbundet"
        elif name == "city":
            out[name] = "Umeå"
        elif name == "employer":
            out[name] = "Region Mellan"
        elif name == "profession":
            out[name] = "Sjuksköterska"
        elif name == "student_name":
            out[name] = "Tone"
        elif name in ("job_title",):
            out[name] = "Säljare"
        elif name == "question":
            out[name] = "Vad är din största styrka?"
        else:
            out[name] = f"<{name}>"
    return out
