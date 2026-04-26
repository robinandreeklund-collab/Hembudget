"""Claude API-integration för skolmodulen.

Funktioner som använder Claude:
 1. AI-feedback-förslag på elevreflektion (Haiku 4.5, lättvikt)
 2. AI-rubric-bedömning som stöd vid läraromdöme (Sonnet 4.6, nyanserat)
 3. Elev-Q&A — "förklara det här igen" (Sonnet 4.6, nyanserat)
 4. AI-modulgenerering — lärare beskriver tema → färdig modulmall (Sonnet 4.6)
 5. Semantisk kategori-bedömning — facit vs elevens val (Haiku 4.5, lättvikt)

Design:
- Klienten initieras lazy — om ANTHROPIC_API_KEY saknas går allt i no-op
  (features returnerar None och endpoints svarar 503).
- Prompt-caching via `cache_control: {type: "ephemeral"}` läggs på stabila
  systemprompt-prefix. Render-ordningen är `tools → system → messages`, så
  vi håller systemprompten deterministisk.
- Varje anrop bokförs mot lärarens konto (ai_requests_count + tokens).
- Adaptive thinking (`thinking: {type: "adaptive"}`) används på Sonnet 4.6
  för nyanserade uppgifter — aldrig för Haiku.

OBS: Den här filen gör själva IO-anropen. Endpoint-wrappers ligger i
api/ai.py och ropar `generate_feedback_suggestion`, `score_with_rubric` osv.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

from ..school.models import AppConfig, Teacher
from ..school.engines import master_session

log = logging.getLogger(__name__)


# Modell-val enligt skill-guide:
# - Haiku 4.5: snabbt + billigt för lättvikt-uppgifter
# - Sonnet 4.6: nyanserat för pedagogisk bedömning / textgenerering
MODEL_HAIKU = "claude-haiku-4-5"
MODEL_SONNET = "claude-sonnet-4-6"


# Maximal respons-längd per feature — håller kostnadskontroll.
MAX_TOKENS_FEEDBACK = 400
MAX_TOKENS_RUBRIC = 600
MAX_TOKENS_QA = 800
MAX_TOKENS_MODULE = 2500
MAX_TOKENS_CATEGORY = 200
MAX_TOKENS_STOCK_TERM = 200
MAX_TOKENS_STOCK_FEEDBACK = 300
MAX_TOKENS_DIVERSIFICATION = 400

# app_config-nyckel där DB-nyckeln lagras. Super-admin kan sätta,
# uppdatera och rensa den via UI. Fallback är ANTHROPIC_API_KEY-env-
# varen för befintliga deployer som redan satt den där.
AI_KEY_CONFIG_KEY = "ai_api_key"


_client: Any = None
_client_signature: str = ""


def _read_api_key() -> str:
    """Läser API-nyckel. DB-värdet (satt via /admin/ai/api-key) vinner
    över env-varen, så super-admin kan byta nyckel utan att redeploya."""
    try:
        with master_session() as s:
            cfg = s.get(AppConfig, AI_KEY_CONFIG_KEY)
            if cfg and cfg.value and isinstance(cfg.value, dict):
                key = str(cfg.value.get("key", "")).strip()
                if key:
                    return key
    except Exception:
        # DB kan vara oläsbar under startup eller migration — falla
        # tillbaka till env tyst.
        log.exception("ai: kunde inte läsa API-nyckel från DB")
    return os.environ.get("ANTHROPIC_API_KEY", "").strip()


def _get_client() -> Any:
    """Lazy-init + revalidering av Anthropic-klienten. Vi sparar en
    'signature' (nyckelns hash-prefix) så att om super-admin byter
    nyckel via UI plockar vi upp den nya vid nästa anrop utan att
    tjänsten behöver startas om."""
    global _client, _client_signature
    api_key = _read_api_key()
    signature = api_key[:12] if api_key else ""
    if _client is not None and signature == _client_signature:
        return _client
    # Nyckeln har ändrats eller klient saknas — rebuilda.
    _client = None
    _client_signature = signature
    if not api_key:
        return None
    try:
        from anthropic import Anthropic
        _client = Anthropic(api_key=api_key)
        log.info("ai: Anthropic-klient initierad")
    except Exception:
        log.exception("ai: kunde inte initiera Anthropic-klient")
        _client = None
    return _client


def invalidate_client() -> None:
    """Rensa klient-cachen så nästa anrop återskapar med ny nyckel."""
    global _client, _client_signature
    _client = None
    _client_signature = ""


def has_key_configured() -> bool:
    """True om det finns en nyckel (i DB eller env)."""
    return bool(_read_api_key())


def key_source() -> str:
    """"db" om super-admin satt en via UI, "env" om bara env-varen
    finns, "" om ingen alls. Används av admin-UI för att visa källan."""
    try:
        with master_session() as s:
            cfg = s.get(AppConfig, AI_KEY_CONFIG_KEY)
            if cfg and cfg.value and isinstance(cfg.value, dict):
                key = str(cfg.value.get("key", "")).strip()
                if key:
                    return "db"
    except Exception:
        pass
    if os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return "env"
    return ""


def key_preview() -> str:
    """Visar bara sista 4 tecknen av aktiv nyckel för admin-UI."""
    k = _read_api_key()
    if not k:
        return ""
    return f"…{k[-4:]}" if len(k) >= 4 else ""


def is_available() -> bool:
    """True om API-nyckel finns och paketet kunde laddas. Används för att
    avgöra om AI-endpoints ska svara 503 eller försöka."""
    return _get_client() is not None


def is_enabled_for_teacher(teacher_id: int) -> bool:
    """Kombinerar klient-tillgänglighet + per-lärarkonfig."""
    if not is_available():
        return False
    with master_session() as s:
        t = s.get(Teacher, teacher_id)
        return bool(t and t.ai_enabled)


@dataclass
class AIResult:
    """Resultat från ett AI-anrop. text = sammanslagen modelltext,
    input_tokens/output_tokens bokförs för kostnadskontroll."""
    text: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0


@dataclass
class AIStructuredResult:
    """Resultat från ett tool_use-anrop. data är det tolkade tool-input:et
    (garanterat giltigt enligt schemat av Anthropic API)."""
    data: dict
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0


def _record_usage(
    teacher_id: int | None,
    input_tokens: int,
    output_tokens: int,
) -> None:
    """Öka räkneverken på lärarkontot. Tystar exceptions — bokföring
    får aldrig hindra UX."""
    if teacher_id is None:
        return
    try:
        with master_session() as s:
            t = s.get(Teacher, teacher_id)
            if t:
                t.ai_requests_count += 1
                t.ai_input_tokens += input_tokens
                t.ai_output_tokens += output_tokens
    except Exception:
        log.exception("ai: kunde inte bokföra usage för teacher_id=%s", teacher_id)


def _call_claude(
    *,
    model: str,
    system: str,
    user_prompt: str,
    max_tokens: int,
    use_thinking: bool = False,
    teacher_id: int | None = None,
) -> Optional[AIResult]:
    """Kör ett Claude-anrop. Systemprompten cache:as (ephemeral) så
    återkommande fasta instruktioner inte räknas som input-tokens varje
    gång.

    thinking:
      - Haiku stöder inte adaptive thinking — lämna False där.
      - Sonnet 4.6 kör `thinking: {type: "adaptive"}` — modellen
        avgör själv hur mycket den tänker.
    """
    client = _get_client()
    if client is None:
        return None
    try:
        params: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                },
            ],
            "messages": [
                {"role": "user", "content": user_prompt},
            ],
        }
        if use_thinking:
            params["thinking"] = {"type": "adaptive"}

        resp = client.messages.create(**params)

        text_parts: list[str] = []
        for block in resp.content:
            if getattr(block, "type", None) == "text":
                text_parts.append(block.text)
        text = "\n".join(text_parts).strip()

        usage = getattr(resp, "usage", None)
        in_tok = getattr(usage, "input_tokens", 0) if usage else 0
        out_tok = getattr(usage, "output_tokens", 0) if usage else 0
        cr = getattr(usage, "cache_read_input_tokens", 0) if usage else 0
        cc = getattr(usage, "cache_creation_input_tokens", 0) if usage else 0

        _record_usage(teacher_id, in_tok + cr + cc, out_tok)
        return AIResult(
            text=text,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cache_read_tokens=cr,
            cache_creation_tokens=cc,
        )
    except Exception:
        log.exception("ai: Claude-anrop misslyckades (model=%s)", model)
        return None


def _call_claude_structured(
    *,
    model: str,
    system: str,
    user_prompt: str,
    max_tokens: int,
    tool_name: str,
    tool_description: str,
    tool_schema: dict,
    use_thinking: bool = False,
    teacher_id: int | None = None,
) -> Optional[AIStructuredResult]:
    """Tvinga Claude att returnera data enligt ett JSON-schema via
    tool_use. Anthropic-API:et garanterar att tool-input-objektet är
    strukturellt giltigt enligt schemat — inga manuella json.loads
    som kan krascha på trunkerade svar.

    Thinking + tools kräver att `thinking` sätts om man vill ha det
    och modell stöder det (Sonnet 4.6 gör). Vi lämnar det valfritt.
    """
    client = _get_client()
    if client is None:
        return None
    try:
        tools = [
            {
                "name": tool_name,
                "description": tool_description,
                "input_schema": tool_schema,
            },
        ]
        params: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                },
            ],
            "messages": [
                {"role": "user", "content": user_prompt},
            ],
            "tools": tools,
            "tool_choice": {"type": "tool", "name": tool_name},
        }
        if use_thinking:
            # tool_choice med "tool" + adaptive thinking är inte
            # kompatibelt i alla Sonnet-versioner. Lämna thinking av
            # för att garantera att tool_use faktiskt används.
            pass

        resp = client.messages.create(**params)

        data: Optional[dict] = None
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use":
                raw = getattr(block, "input", None)
                if isinstance(raw, dict):
                    data = raw
                    break

        if data is None:
            log.warning(
                "ai: tool_use-svar saknade %s-block (model=%s)",
                tool_name, model,
            )
            return None

        usage = getattr(resp, "usage", None)
        in_tok = getattr(usage, "input_tokens", 0) if usage else 0
        out_tok = getattr(usage, "output_tokens", 0) if usage else 0
        cr = getattr(usage, "cache_read_input_tokens", 0) if usage else 0
        cc = getattr(usage, "cache_creation_input_tokens", 0) if usage else 0

        _record_usage(teacher_id, in_tok + cr + cc, out_tok)
        return AIStructuredResult(
            data=data,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cache_read_tokens=cr,
            cache_creation_tokens=cc,
        )
    except Exception:
        log.exception(
            "ai: Claude tool_use-anrop misslyckades (model=%s, tool=%s)",
            model, tool_name,
        )
        return None


def stream_claude(
    *,
    model: str,
    system: str,
    user_prompt: str | None = None,
    messages: list[dict] | None = None,
    max_tokens: int,
    use_thinking: bool = False,
    teacher_id: int | None = None,
):
    """Generator som strömmar text-deltas från Claude. yieldar
    `{"type": "delta", "text": "..."}` för varje token, och sist
    `{"type": "done", "input_tokens": N, "output_tokens": M}`.
    Vid fel: `{"type": "error", "message": "..."}`.

    Antingen `user_prompt` (enkel enradig fråga) eller `messages`
    (fullt meddelandelista för multi-turn) krävs — båda samtidigt
    kombineras inte.

    Sätt use_thinking=False för rena UI-chattar — thinking fördröjer
    första token:en med flera sekunder.
    """
    client = _get_client()
    if client is None:
        yield {"type": "error", "message": "AI-klient saknas"}
        return

    if messages is None:
        if user_prompt is None:
            yield {"type": "error", "message": "stream_claude saknar input"}
            return
        messages = [{"role": "user", "content": user_prompt}]

    in_tok = out_tok = cr = cc = 0
    try:
        params: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                },
            ],
            "messages": messages,
        }
        if use_thinking:
            params["thinking"] = {"type": "adaptive"}

        with client.messages.stream(**params) as stream:
            for delta in stream.text_stream:
                if delta:
                    yield {"type": "delta", "text": delta}
            final = stream.get_final_message()
            usage = getattr(final, "usage", None)
            in_tok = getattr(usage, "input_tokens", 0) if usage else 0
            out_tok = getattr(usage, "output_tokens", 0) if usage else 0
            cr = getattr(usage, "cache_read_input_tokens", 0) if usage else 0
            cc = getattr(usage, "cache_creation_input_tokens", 0) if usage else 0
    except Exception as e:
        log.exception("ai: stream-anrop misslyckades (model=%s)", model)
        yield {"type": "error", "message": str(e)}
        return

    _record_usage(teacher_id, in_tok + cr + cc, out_tok)
    yield {
        "type": "done",
        "input_tokens": in_tok,
        "output_tokens": out_tok,
    }


# ---------- Feature 1: AI-feedback-förslag på reflektion ----------

FEEDBACK_SYSTEM_PROMPT = """Du är ett pedagogiskt stöd för en svensk gymnasielärare i samhällsekonomi/personlig ekonomi.
Ditt enda jobb är att föreslå KONSTRUKTIV återkoppling på en elevs reflektion — läraren bestämmer sen om hen vill använda förslaget rakt av, redigera det eller förkasta det.

Riktlinjer:
- Svara på svenska, warmt men professionellt.
- 2–4 meningar, max 60 ord.
- Börja med något eleven gjorde bra.
- Avsluta med EN konkret fråga eller nästa steg som utmanar tanken vidare.
- Dumpa ALDRIG fakta — syftet är att stötta reflektion, inte rätta sakfel.
- Använd inte emojis. Använd inte listformat. Ingen rubrik."""


def generate_feedback_suggestion(
    *,
    reflection_text: str,
    module_title: str,
    step_prompt: str,
    teacher_id: int | None = None,
) -> Optional[AIResult]:
    user = (
        f"Modul: {module_title}\n"
        f"Frågan eleven svarade på:\n{step_prompt}\n\n"
        f"Elevens reflektion:\n{reflection_text}\n\n"
        "Ge ett konkret förslag på återkoppling läraren kan skicka."
    )
    return _call_claude(
        model=MODEL_HAIKU,
        system=FEEDBACK_SYSTEM_PROMPT,
        user_prompt=user,
        max_tokens=MAX_TOKENS_FEEDBACK,
        use_thinking=False,
        teacher_id=teacher_id,
    )


# ---------- Feature 2: AI-rubric-bedömning ----------

RUBRIC_SYSTEM_PROMPT = """Du hjälper en svensk gymnasielärare bedöma en elevreflektion mot en rubric.
Du är ett STÖD — läraren sätter slutbetyget. Din uppgift är att föreslå nivå + motivera kort.

Rubricen är en JSON-array med objekt: {"key": "<nyckel>", "name": "<kriterienamn>", "levels": ["<nivå 1-text>", "<nivå 2-text>", ...]}.

Regler:
- score = index i levels-arrayen (0 = lägsta nivå, levels.length-1 = högsta).
- criterion_id MÅSTE matcha rubric-objektets "key"-fält exakt.
- Bedöm BARA det eleven faktiskt skrivit, inte det du tror hen tänkte.
- Var generös men rättvis — om kriteriet inte adresseras alls = 0.
- "rationale" måste peka på konkret bevis i elevens text.
- Använd ALLA kriterier som finns i rubriken, inga extra.

Du bedömer via `submit_rubric_assessment`-verktyget — strukturen är given där."""


RUBRIC_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "scores": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "criterion_id": {
                        "type": "string",
                        "description": "Rubric-kriteriets 'key'-fält.",
                    },
                    "score": {
                        "type": "integer",
                        "minimum": 0,
                        "description": "Index in levels-arrayen, 0 = lägsta.",
                    },
                    "rationale": {
                        "type": "string",
                        "description": "1–2 meningar på svenska med bevis från elevens text.",
                    },
                },
                "required": ["criterion_id", "score", "rationale"],
            },
        },
        "overall_comment": {
            "type": "string",
            "description": "2–3 meningar sammanfattande feedback på svenska.",
        },
    },
    "required": ["scores", "overall_comment"],
}


def score_with_rubric(
    *,
    rubric_json: str,
    reflection_text: str,
    step_prompt: str,
    teacher_id: int | None = None,
) -> Optional[AIStructuredResult]:
    user = (
        f"Rubric:\n{rubric_json}\n\n"
        f"Frågan eleven svarade på:\n{step_prompt}\n\n"
        f"Elevens reflektion:\n{reflection_text}\n\n"
        "Kör `submit_rubric_assessment` med din bedömning."
    )
    return _call_claude_structured(
        model=MODEL_SONNET,
        system=RUBRIC_SYSTEM_PROMPT,
        user_prompt=user,
        max_tokens=MAX_TOKENS_RUBRIC,
        tool_name="submit_rubric_assessment",
        tool_description=(
            "Lämna in en rubric-bedömning med per-kriterium-nivåer och "
            "en samlad kommentar."
        ),
        tool_schema=RUBRIC_TOOL_SCHEMA,
        teacher_id=teacher_id,
    )


# ---------- Feature 3: Elev-Q&A — "förklara igen" ----------

QA_SYSTEM_PROMPT = """Du är en vänlig studiecoach för svenska gymnasielever inom personlig ekonomi.
Eleven jobbar just nu med en specifik modul och har frågat om ett begrepp hen inte förstår.

Riktlinjer:
- Svara på svenska, MYCKET lätt språk, 16-åring som målgrupp.
- Max 150 ord.
- Använd konkret vardagsexempel som en 16-åring känner igen (SL-kort, Spotify, lön från extrajobb, Swish).
- Svara ALDRIG med något som bryter mot sanningen i svensk ekonomi/skatt/konsumentlagstiftning.
- Ge INTE personlig finansiell rådgivning. Om eleven frågar "ska jag köpa X" → svara "så här kan du tänka när du resonerar kring det" istället.
- Inga emojis. Max en punktlista om det verkligen hjälper."""


QUIZ_EXPLAIN_SYSTEM_PROMPT = """Du är en vänlig studiecoach för svenska gymnasielever.
Eleven har svarat fel på en quiz-fråga och vill förstå sitt eget fel.

Din uppgift i tre steg (i den ordningen, men väv ihop dem):
1. Erkänn snabbt vad eleven valde och visa förståelse för varför det KAN verka rimligt.
2. Förklara vad som egentligen är rätt och varför — lugnt och utan att döma.
3. Avsluta med EN konkret tumregel eller ett exempel som hjälper minnas nästa gång.

Riktlinjer:
- Svenska, 16-åring som målgrupp, max 130 ord.
- Säg aldrig "ditt svar var dumt" eller liknande.
- Använd konkreta vardagsexempel (Swish, Spotify, lön från sommarjobb).
- Inga emojis, ingen rubrikmarkdown, ingen punktlista om det inte gör det tydligare.
- Säg aldrig vilket numrerat alternativ som var rätt — förklara konceptet istället, eleven ser ändå facit i UI:t."""


def answer_student_question(
    *,
    question: str,
    module_title: str,
    module_summary: str | None,
    step_prompt: str | None,
    teacher_id: int | None = None,
) -> Optional[AIResult]:
    context_parts = [f"Modul eleven jobbar med: {module_title}"]
    if module_summary:
        context_parts.append(f"Modulens syfte: {module_summary}")
    if step_prompt:
        context_parts.append(f"Aktuellt steg: {step_prompt}")
    context = "\n".join(context_parts)

    user = f"{context}\n\nElevens fråga:\n{question}"
    return _call_claude(
        model=MODEL_SONNET,
        system=QA_SYSTEM_PROMPT,
        user_prompt=user,
        max_tokens=MAX_TOKENS_QA,
        use_thinking=True,
        teacher_id=teacher_id,
    )


# ---------- Feature 4: AI-modulgenerering ----------

MODULE_GEN_SYSTEM_PROMPT = """Du är en kursdesigner för svensk gymnasieekonomi. En lärare ber dig skissa en modulmall.

Regler:
- 4–7 steg totalt, stegvis ökande svårighetsgrad.
- Minst ETT "reflect"-steg med öppen fråga där eleven motiverar ett val.
- Minst ETT "task"-steg som ber eleven göra något konkret i plattformen (t.ex. "lägg in din lön", "gör en budget för 4 veckor").
- "read"-steg: body = 150–300 ord förklarande text på lättläst svenska.
- "watch"-steg: nämn att eleven hittar länken hos läraren (vi lägger ingen URL själva).
- "quiz"-steg: body = en fråga + 3–4 svarsalternativ (vi markerar inget rätt här, lärare gör det).
- Målgrupp: 16–19 år. Undvik ekonomjargong, eller förklara om du använder ett sånt ord.
- Svenska, ingen engelska.

Du svarar genom att kalla `submit_module_template`-verktyget — strukturen är given där."""


MODULE_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "description": "Kort titel, max 60 tecken.",
            "maxLength": 60,
        },
        "summary": {
            "type": "string",
            "description": "1–2 meningars beskrivning för eleven, svenska.",
        },
        "steps": {
            "type": "array",
            "minItems": 4,
            "maxItems": 7,
            "items": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["read", "watch", "reflect", "task", "quiz"],
                    },
                    "title": {"type": "string"},
                    "body": {
                        "type": "string",
                        "description": "Instruktionstext till eleven, 1–3 stycken svenska.",
                    },
                    "sort_order": {"type": "integer", "minimum": 0},
                },
                "required": ["kind", "title", "body", "sort_order"],
            },
        },
    },
    "required": ["title", "summary", "steps"],
}


def generate_module_template(
    *,
    theme_prompt: str,
    teacher_id: int | None = None,
) -> Optional[AIStructuredResult]:
    user = (
        "Lärarens beskrivning av vad modulen ska handla om:\n"
        f"{theme_prompt}\n\n"
        "Kör `submit_module_template` med en modulmall."
    )
    return _call_claude_structured(
        model=MODEL_SONNET,
        system=MODULE_GEN_SYSTEM_PROMPT,
        user_prompt=user,
        max_tokens=MAX_TOKENS_MODULE,
        tool_name="submit_module_template",
        tool_description=(
            "Lämna en komplett modulmall: titel, syfte och 4–7 steg "
            "av blandade typer."
        ),
        tool_schema=MODULE_TOOL_SCHEMA,
        teacher_id=teacher_id,
    )


# ---------- Feature 6: AI-elevsammanfattning för lärare ----------

STUDENT_SUMMARY_SYSTEM_PROMPT = """Du hjälper en svensk gymnasielärare få en snabb
överblick över var en elev står i sin pedagogiska resa inom personlig ekonomi.

Du får elevens profil, senaste reflektioner (de sista ca 5), mastery-
översikt och uppdragsstatus. Skriv en koncis lägesbild i tre sektioner:

1. Styrkor — vad eleven tydligt klarar, baserat på bevis (mastery,
   reflektionskvalitet, klarade uppdrag).
2. Gap — vilka kompetenser eller begrepp eleven verkar sakna grund i.
   Var KONKRET: säg "bolåneränta vs amortering" istället för "lån".
3. Nästa steg — 1–3 konkreta förslag läraren kan ge (modul att prioritera,
   övning, samtalsämne).

Riktlinjer:
- Svenska, 4–6 meningar per sektion, 200–300 ord totalt.
- Bygg på konkreta bevis från datan — citera inte men referera.
- Var kollegial: eleven är fortfarande en tonåring som lär sig.
- Ingen smink — om eleven har hunnit lite säg det, om hen har hunnit
  mycket säg det också.
- Inga emojis. Rubriker får vara "**Styrkor**" osv i markdown-fetstil.

Svara i vanlig prosa — verktyget vi använder strukturerar de tre
sektionerna."""


STUDENT_SUMMARY_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "strengths": {"type": "string"},
        "gaps": {"type": "string"},
        "next_steps": {"type": "string"},
    },
    "required": ["strengths", "gaps", "next_steps"],
}


def generate_student_summary(
    *,
    context_bundle: str,
    teacher_id: int | None = None,
) -> Optional[AIStructuredResult]:
    return _call_claude_structured(
        model=MODEL_SONNET,
        system=STUDENT_SUMMARY_SYSTEM_PROMPT,
        user_prompt=context_bundle + "\n\nKör `submit_student_summary`.",
        max_tokens=1200,
        tool_name="submit_student_summary",
        tool_description=(
            "Lämna en pedagogisk lägesbild i tre sektioner: styrkor, "
            "gap och nästa steg."
        ),
        tool_schema=STUDENT_SUMMARY_TOOL_SCHEMA,
        teacher_id=teacher_id,
    )


# ---------- Feature 5: Semantisk kategori-bedömning ----------

CATEGORY_EXPLAIN_SYSTEM_PROMPT = """Du är en vänlig studiecoach för svenska gymnasielever.
Eleven har kategoriserat en transaktion "fel" jämfört med facit. Din
uppgift är att på lätt svenska förklara varför läraren tänkt annorlunda
— utan att döma.

Struktur:
1. Acceptera elevens tanke (varför den egna gissningen var rimlig).
2. Förklara skillnaden mellan kategorierna i vardagliga termer.
3. Ge en minnesregel eller ett exempel så eleven hittar rätt nästa gång.

Riktlinjer:
- Svenska, 16-åring som målgrupp, max 130 ord.
- Inga emojis, ingen punktlista om det inte hjälper.
- Säg aldrig "din kategorisering är dum" eller liknande."""


CATEGORY_SYSTEM_PROMPT = """Du är ett pedagogiskt verktyg som jämför två kategorinamn på svenska hushållsutgifter.
Facit = den kategori som läraren tänkt att transaktionen ska hamna i.
Elev = den kategori eleven valt.

Avgör: är elevens val SEMANTISKT korrekt? "ICA Maxi 450 kr" som lagts på "Mat & livsmedel" ska räknas som rätt även om facit säger "Matvaror". "Burger King" på "Restaurang" är också rätt när facit säger "Uteätande".

Regler:
- is_match=true när kategorierna betyder ungefär samma sak i vardaglig svenska.
- is_match=false när de helt skiljer sig (t.ex. "Mat" vs "Transport").
- confidence 0.9+ bara om det är uppenbart samma kategori.

Du rapporterar via `submit_category_match`-verktyget."""


CATEGORY_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "is_match": {"type": "boolean"},
        "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
        },
        "explanation": {
            "type": "string",
            "description": "1 mening på svenska med kort motivering.",
        },
    },
    "required": ["is_match", "confidence", "explanation"],
}


def check_category_semantic_match(
    *,
    merchant: str,
    amount: float,
    student_category: str,
    facit_category: str,
    teacher_id: int | None = None,
) -> Optional[AIStructuredResult]:
    user = (
        f"Transaktion: {merchant} ({amount:.0f} kr)\n"
        f"Facit-kategori: {facit_category}\n"
        f"Elev-val: {student_category}\n\n"
        "Kör `submit_category_match` med din bedömning."
    )
    return _call_claude_structured(
        model=MODEL_HAIKU,
        system=CATEGORY_SYSTEM_PROMPT,
        user_prompt=user,
        max_tokens=MAX_TOKENS_CATEGORY,
        tool_name="submit_category_match",
        tool_description=(
            "Rapportera om elevens val är semantiskt korrekt mot facit."
        ),
        tool_schema=CATEGORY_TOOL_SCHEMA,
        teacher_id=teacher_id,
    )


# ---------- Aktie-features (D4) ----------
#
# AI får ALDRIG ge köp/sälj-rekommendationer för enskilda aktier. Endast
# förklaringar, observationer och pedagogiska frågor. Detta är både
# juridiskt skyddande (simulator i skola, inte rådgivning) och
# pedagogiskt rätt — eleven ska tänka själv.

STOCK_TERM_SYSTEM_PROMPT = """Du är en pedagogisk förklarare av aktietermer på lättläst svenska för svenska gymnasieelever (16–18 år).

Regler:
- Förklara termen i 1–2 meningar, max 60 ord.
- Använd ett vardagligt exempel om möjligt.
- Ge ALDRIG köp- eller säljrekommendationer.
- Säg aldrig "du borde", "jag rekommenderar", "satsa på".
- Om termen handlar om risk eller skatt: var saklig, inte skrämmande.
- Skriv på svenska."""


def explain_stock_term(
    *,
    term: str,
    teacher_id: int | None = None,
) -> Optional[AIResult]:
    """Förklarar en aktieterm pedagogiskt. Anropas när eleven hovrar
    eller klickar på 'Vad är X?' i UI:t."""
    user = f"Förklara termen: '{term}'"
    return _call_claude(
        model=MODEL_HAIKU,
        system=STOCK_TERM_SYSTEM_PROMPT,
        user_prompt=user,
        max_tokens=MAX_TOKENS_STOCK_TERM,
        use_thinking=False,
        teacher_id=teacher_id,
    )


STOCK_TRADE_FEEDBACK_SYSTEM_PROMPT = """Du ger pedagogisk återkoppling till en svensk gymnasieelev som just gjort en aktieaffär i en skol-simulator.

Regler:
- Reflektera över KARAKTÄREN av affären (sektor, storlek, timing) — INTE om den var "bra eller dålig".
- Ge ALDRIG köp- eller säljrekommendationer.
- Nämn ev. courtage som procentandel av affären om det är högt (>1 %).
- Om eleven skrev en motivering, kommentera den kort men ärligt.
- 2–4 meningar, max 80 ord, lättläst svenska.
- Ingen "du borde", inga åsikter om aktiens framtida värde."""


def feedback_on_trade(
    *,
    side: str,  # "buy" | "sell"
    ticker: str,
    stock_name: str,
    sector: str,
    quantity: int,
    price: float,
    courtage: float,
    total: float,
    student_rationale: str | None,
    teacher_id: int | None = None,
) -> Optional[AIResult]:
    """Kort kommentar efter köp/sälj. Aktiveras bara när lärarens
    ai_enabled=True. Tom kommentar = simulatorn fungerar utan."""
    courtage_pct = (courtage / total * 100) if total > 0 else 0
    rationale = student_rationale or "(ingen motivering angiven)"
    user = (
        f"Affär: {side} {quantity} st {stock_name} ({ticker}, {sector}).\n"
        f"Kurs {price:.2f} kr/styck, courtage {courtage:.2f} kr "
        f"({courtage_pct:.2f} % av affären), totalt {total:.2f} kr.\n"
        f"Elevens motivering: {rationale}\n\n"
        "Ge en kort pedagogisk reflektion på svenska."
    )
    return _call_claude(
        model=MODEL_HAIKU,
        system=STOCK_TRADE_FEEDBACK_SYSTEM_PROMPT,
        user_prompt=user,
        max_tokens=MAX_TOKENS_STOCK_FEEDBACK,
        use_thinking=False,
        teacher_id=teacher_id,
    )


DIVERSIFICATION_SYSTEM_PROMPT = """Du bedömer hur diversifierad en svensk gymnasieelevs aktieportfölj är.

Regler:
- Bedöm spridning över sektorer + viktning (är en sektor extremt dominerande?).
- Säg ALDRIG vilka aktier eleven ska köpa eller sälja.
- Om spridningen är god, säg det och förklara varför kort.
- Om en sektor dominerar (>50 %), nämn det som observation utan att skriva "byt ut".
- 2–4 meningar, max 80 ord, lättläst svenska."""


def evaluate_diversification(
    *,
    sector_weights: dict,  # sector -> percent
    n_holdings: int,
    teacher_id: int | None = None,
) -> Optional[AIResult]:
    """Bedömer portföljens diversifiering pedagogiskt."""
    sector_lines = "\n".join(
        f"- {sector}: {weight:.1f} %"
        for sector, weight in sorted(
            sector_weights.items(), key=lambda kv: -kv[1],
        )
    )
    user = (
        f"Antal innehav: {n_holdings}\n"
        f"Sektorvikter:\n{sector_lines}\n\n"
        "Bedöm diversifieringen pedagogiskt på svenska."
    )
    return _call_claude(
        model=MODEL_HAIKU,
        system=DIVERSIFICATION_SYSTEM_PROMPT,
        user_prompt=user,
        max_tokens=MAX_TOKENS_DIVERSIFICATION,
        use_thinking=False,
        teacher_id=teacher_id,
    )
