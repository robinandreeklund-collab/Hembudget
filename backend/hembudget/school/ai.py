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

from ..school.models import Teacher
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


_client: Any = None
_client_loaded = False


def _get_client() -> Any:
    """Lazy-init Anthropic-klienten. Returnerar None om API-nyckel saknas
    eller om paketet inte är installerat."""
    global _client, _client_loaded
    if _client_loaded:
        return _client
    _client_loaded = True
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        log.info("ai: ANTHROPIC_API_KEY saknas — AI-funktioner inaktiva")
        return None
    try:
        from anthropic import Anthropic
        _client = Anthropic(api_key=api_key)
        log.info("ai: Anthropic-klient initierad")
    except Exception:
        log.exception("ai: kunde inte initiera Anthropic-klient")
        _client = None
    return _client


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

Svara ENDAST med giltig JSON i exakt det här formatet:

{
  "scores": [
    {"criterion_id": "<rubric.key>", "score": <level_index 0..levels.length-1>, "rationale": "<1–2 meningar på svenska>"}
  ],
  "overall_comment": "<2–3 meningar sammanfattande feedback på svenska>"
}

Regler:
- score = index i levels-arrayen (0 = lägsta nivå, levels.length-1 = högsta).
- criterion_id MÅSTE matcha rubric-objektets "key"-fält exakt.
- Bedöm BARA det eleven faktiskt skrivit, inte det du tror hen tänkte.
- Var generös men rättvis — om kriteriet inte adresseras alls = 0.
- "rationale" måste peka på konkret bevis i elevens text.
- Använd ALLA kriterier som finns i rubriken, inga extra.
- Inget annat än JSON. Ingen markdown, inga kodblock, ingen förklaring efter."""


def score_with_rubric(
    *,
    rubric_json: str,
    reflection_text: str,
    step_prompt: str,
    teacher_id: int | None = None,
) -> Optional[AIResult]:
    user = (
        f"Rubric:\n{rubric_json}\n\n"
        f"Frågan eleven svarade på:\n{step_prompt}\n\n"
        f"Elevens reflektion:\n{reflection_text}\n\n"
        "Ge din bedömning som JSON enligt instruktionen."
    )
    return _call_claude(
        model=MODEL_SONNET,
        system=RUBRIC_SYSTEM_PROMPT,
        user_prompt=user,
        max_tokens=MAX_TOKENS_RUBRIC,
        use_thinking=True,
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
Svara ENDAST med giltig JSON i exakt det här formatet:

{
  "title": "<kort titel, max 60 tecken>",
  "summary": "<1–2 meningars beskrivning för eleven, svenska>",
  "steps": [
    {
      "kind": "read" | "watch" | "reflect" | "task" | "quiz",
      "title": "<stegets titel>",
      "body": "<instruktionstext till eleven, 1–3 stycken, svenska>",
      "sort_order": <heltal>
    }
  ]
}

Regler:
- 4–7 steg totalt, stegvis ökande svårighetsgrad.
- Minst ETT "reflect"-steg med öppen fråga där eleven motiverar ett val.
- Minst ETT "task"-steg som ber eleven göra något konkret i plattformen (t.ex. "lägg in din lön", "gör en budget för 4 veckor").
- "read"-steg: body = 150–300 ord förklarande text på lättläst svenska.
- "watch"-steg: nämn att eleven hittar länken hos läraren (vi lägger ingen URL själva).
- "quiz"-steg: body = en fråga + 3–4 svarsalternativ (vi markerar inget rätt här, lärare gör det).
- Målgrupp: 16–19 år. Undvik ekonomjargong, eller förklara om du använder ett sånt ord.
- Svenska, ingen engelska.
- Bara JSON — inget annat, ingen markdown, inget kodblock."""


def generate_module_template(
    *,
    theme_prompt: str,
    teacher_id: int | None = None,
) -> Optional[AIResult]:
    user = (
        "Lärarens beskrivning av vad modulen ska handla om:\n"
        f"{theme_prompt}\n\n"
        "Skissa en modulmall som JSON enligt instruktionen."
    )
    return _call_claude(
        model=MODEL_SONNET,
        system=MODULE_GEN_SYSTEM_PROMPT,
        user_prompt=user,
        max_tokens=MAX_TOKENS_MODULE,
        use_thinking=True,
        teacher_id=teacher_id,
    )


# ---------- Feature 5: Semantisk kategori-bedömning ----------

CATEGORY_SYSTEM_PROMPT = """Du är ett pedagogiskt verktyg som jämför två kategorinamn på svenska hushållsutgifter.
Facit = den kategori som läraren tänkt att transaktionen ska hamna i.
Elev = den kategori eleven valt.

Avgör: är elevens val SEMANTISKT korrekt? "ICA Maxi 450 kr" som lagts på "Mat & livsmedel" ska räknas som rätt även om facit säger "Matvaror". "Burger King" på "Restaurang" är också rätt när facit säger "Uteätande".

Svara ENDAST med giltig JSON:

{
  "is_match": true | false,
  "confidence": <0.0 .. 1.0>,
  "explanation": "<1 mening på svenska — kort motivering>"
}

Regler:
- true när kategorierna betyder ungefär samma sak i vardaglig svenska.
- false när de helt skiljer sig (t.ex. "Mat" vs "Transport").
- confidence 0.9+ bara om det är uppenbart samma kategori.
- Bara JSON, inget annat."""


def check_category_semantic_match(
    *,
    merchant: str,
    amount: float,
    student_category: str,
    facit_category: str,
    teacher_id: int | None = None,
) -> Optional[AIResult]:
    user = (
        f"Transaktion: {merchant} ({amount:.0f} kr)\n"
        f"Facit-kategori: {facit_category}\n"
        f"Elev-val: {student_category}\n\n"
        "Är elevens val semantiskt korrekt?"
    )
    return _call_claude(
        model=MODEL_HAIKU,
        system=CATEGORY_SYSTEM_PROMPT,
        user_prompt=user,
        max_tokens=MAX_TOKENS_CATEGORY,
        use_thinking=False,
        teacher_id=teacher_id,
    )
