"""Katalog över alla AI-prompts som lärare får anpassa.

Designprincip: hellre färre välvalda prompts än alla. Tekniska
klassificerare (kategori-match, klasskompis-bjudningar) hålls
hårdkodade så pedagogiska poäng-system inte kan brytas.

Varje prompt har:
* `key`            — stabil sträng som lagras i DB (TeacherAiPrompt.prompt_key)
* `label`          — visningsnamn för läraren
* `category`       — gruppering i UI ("personas" / "biz_eval" / ...)
* `description`    — pedagogisk beskrivning av VAD prompten styr
* `default_text`   — den hårdkodade default-prompten (kopia)
* `variables`      — lista av f-string-variabler läraren får använda
* `used_at`        — frontend-route där prompten triggas (för spårning)
* `model`          — vilken Claude-modell ("haiku" / "sonnet")
* `preview_input`  — exempel-input till förhandsgranskning

Källan till sanning för default-texterna är `school/ai.py` resp.
`business/ai.py`. Vi importerar dem hit i stället för att kopiera
strängar — det garanterar att default som visas i lärar-UI:t alltid
matchar den som körs i produktion.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PromptCategory = Literal[
    "personas", "biz_eval", "teacher_grading", "content_gen",
]


@dataclass(frozen=True)
class PromptSpec:
    key: str
    label: str
    category: PromptCategory
    description: str
    default_text: str
    variables: list[str]
    used_at: str
    model: str
    preview_input: str

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "category": self.category,
            "description": self.description,
            "default_text": self.default_text,
            "variables": self.variables,
            "used_at": self.used_at,
            "model": self.model,
            "preview_input": self.preview_input,
        }


def _load_defaults() -> dict[str, str]:
    """Importera default-prompts från sannings-källorna. Görs lazily
    så att en cirkulär import inte kraschar app-starten."""
    from . import ai as _school_ai
    from ..business import ai as _biz_ai
    return {
        # Personas
        "negotiation_maria": _school_ai.NEGOTIATION_SYSTEM_TEMPLATE,
        "cover_letter_mats": _school_ai.COVER_LETTER_SYSTEM_PROMPT,
        "interview_mats": _school_ai.INTERVIEW_ANSWER_SYSTEM_PROMPT,
        "chat_coach": _school_ai.CHAT_SYSTEM_PROMPT,
        "qa_coach": _school_ai.QA_SYSTEM_PROMPT,
        # Biz-eval
        "biz_pitch": _biz_ai._PITCH_SYSTEM,
        "biz_marketing": _biz_ai._MARKETING_SYSTEM,
        "biz_job_desc": _biz_ai._JOB_DESC_SYSTEM,
        # Teacher grading
        "teacher_feedback": _school_ai.FEEDBACK_SYSTEM_PROMPT,
        "rubric_grading": _school_ai.RUBRIC_SYSTEM_PROMPT,
        "stock_trade_feedback": _school_ai.STOCK_TRADE_FEEDBACK_SYSTEM_PROMPT,
        "diversification": _school_ai.DIVERSIFICATION_SYSTEM_PROMPT,
        "wellbeing_monthly": _school_ai.WELLBEING_MONTHLY_SYSTEM_PROMPT,
        # Content-gen
        "module_gen": _school_ai.MODULE_GEN_SYSTEM_PROMPT,
        "stock_term_explain": _school_ai.STOCK_TERM_SYSTEM_PROMPT,
        "category_explain": _school_ai.CATEGORY_EXPLAIN_SYSTEM_PROMPT,
        "quiz_explain": _school_ai.QUIZ_EXPLAIN_SYSTEM_PROMPT,
        "student_summary": _school_ai.STUDENT_SUMMARY_SYSTEM_PROMPT,
    }


# Specs: en per controllable prompt. Default-text fylls i lazily via
# _load_defaults() och _SPECS-cachen byggs vid första GET-anropet.
_SPECS_META: list[dict] = [
    # === A · Personas eleven möter direkt ===
    {
        "key": "negotiation_maria",
        "label": "Maria HR · Lönesamtal",
        "category": "personas",
        "description": (
            "Maria är HR-chefen som förhandlar lön med eleven på "
            "/v2/arbetsgivaren. Prompten styr Marias ton och vilka "
            "argument hon använder mot elevens lönekrav."
        ),
        "variables": [
            "{employer}", "{profession}", "{gross_salary}", "{city}",
            "{performance}", "{tenure_months}", "{market_avg}",
        ],
        "used_at": "/v2/arbetsgivaren",
        "model": "sonnet",
        "preview_input": (
            "Eleven Tone, sjuksköterska, 28 år, har varit anställd 18 mån.\n"
            "Nuvarande lön: 32 000 kr · Marknadssnitt: 35 500 kr\n"
            "Eleven säger: 'Jag har arbetat hårt och vill upp till 38 000.'"
        ),
    },
    {
        "key": "cover_letter_mats",
        "label": "Mats Arbetsförmedlingen · Personligt brev",
        "category": "personas",
        "description": (
            "Mats är handläggaren på Arbetsförmedlingen som granskar "
            "elevens personliga brev innan en jobbansökan. Prompten "
            "styr hur strängt han bedömer + vilka aspekter han lyfter."
        ),
        "variables": ["{job_title}", "{employer}", "{archetype}"],
        "used_at": "/v2/arbetsformedlingen",
        "model": "sonnet",
        "preview_input": (
            "Jobb: Säljare på Elgiganten\n"
            "Eleven skrev: 'Hej! Jag heter Anna och vill jobba hos er. "
            "Jag är duktig på att prata med folk och tycker om elektronik.'"
        ),
    },
    {
        "key": "interview_mats",
        "label": "Mats Arbetsförmedlingen · Intervju-svar",
        "category": "personas",
        "description": (
            "Mats bedömer elevens intervju-svar (öppna frågor om "
            "motivation, styrkor, svagheter). Prompten styr feedback-"
            "tonen och vilka kriterier han väger."
        ),
        "variables": ["{question}", "{job_title}"],
        "used_at": "/v2/arbetsformedlingen",
        "model": "sonnet",
        "preview_input": (
            "Fråga: 'Vad är din största svaghet?'\n"
            "Elevens svar: 'Jag är lite för perfektionistisk ibland.'"
        ),
    },
    {
        "key": "chat_coach",
        "label": "Studiecoach · Echo-chat",
        "category": "personas",
        "description": (
            "Studiecoachen som svarar elevens frågor i Echo-drawern. "
            "Generell coach kring budget, lön, skatt, sparande."
        ),
        "variables": [],
        "used_at": "Echo-drawer · alla vyer",
        "model": "haiku",
        "preview_input": (
            "Eleven frågar: 'Hur mycket bör jag spara varje månad?'"
        ),
    },
    {
        "key": "qa_coach",
        "label": "Studiecoach · Specifika frågor",
        "category": "personas",
        "description": (
            "Variant av studiecoachen för korta Q&A-svar i specifika "
            "vyer (t.ex. quiz-svarstext, kategori-förklaring)."
        ),
        "variables": [],
        "used_at": "Quiz + kategoriförklaringar",
        "model": "haiku",
        "preview_input": "Eleven frågar: 'Vad är skillnaden på brutto och netto?'",
    },

    # === B · Företagsmotor — bedömningar ===
    {
        "key": "biz_pitch",
        "label": "Företag · Offert-pitch-bedömning",
        "category": "biz_eval",
        "description": (
            "Bedömer hur övertygande elevens pitch-text är i en offert. "
            "Resultat: score 0..1 som påverkar acceptance_model och "
            "kundens beslut. Justera om du tycker AI är för snäll/sträng."
        ),
        "variables": [],
        "used_at": "/v2/foretag/offerter",
        "model": "haiku",
        "preview_input": (
            "Jobb: 'Bygga altan 18 kvm'\n"
            "Pitch: 'Vi har lång erfarenhet och levererar med god kvalitet.'"
        ),
    },
    {
        "key": "biz_marketing",
        "label": "Företag · Marknadsföringskopia",
        "category": "biz_eval",
        "description": (
            "Bedömer kvaliteten på elevens marknadsföringskopia (annons-"
            "texter, kampanjer). Resultat: 0.5–1.5x multiplikator på "
            "pipeline-boost. Driver hur effektiva kampanjerna blir."
        ),
        "variables": [],
        "used_at": "/v2/foretag/marknad",
        "model": "haiku",
        "preview_input": (
            "Kampanjtext: 'Köp 10 % rabatt nu! Gratis hemleverans i Umeå.'"
        ),
    },
    {
        "key": "biz_job_desc",
        "label": "Företag · Generera jobb-beskrivningar",
        "category": "biz_eval",
        "description": (
            "Genererar varierade jobb-beskrivningar för nya offert-"
            "förfrågningar i företagsmotorn. Justera ton/språknivå för "
            "att matcha elevens nivå (åk 1 vs åk 3 t.ex.)."
        ),
        "variables": [],
        "used_at": "/v2/foretag/offerter (auto-tick)",
        "model": "haiku",
        "preview_input": (
            "Jobb: Måla rum · Bransch: snickare · Kund: Familjen Lindqvist"
        ),
    },

    # === C · Lärar-bedömnings-stöd ===
    {
        "key": "teacher_feedback",
        "label": "Reflektions-feedback · förslag åt läraren",
        "category": "teacher_grading",
        "description": (
            "Genererar förslag på pedagogisk feedback till elevens "
            "reflektion. Du som lärare kan kopiera/redigera innan du "
            "skickar — AI ersätter inte din bedömning, den förslår."
        ),
        "variables": [],
        "used_at": "/teacher/v2/reflektioner",
        "model": "sonnet",
        "preview_input": (
            "Reflektion från eleven: 'Jag lärde mig att budget är viktigt "
            "men det är svårt att hålla.'"
        ),
    },
    {
        "key": "rubric_grading",
        "label": "Rubric-bedömning · scorea elevreflektion",
        "category": "teacher_grading",
        "description": (
            "Bedömer en elevreflektion mot en rubric (kriterier + "
            "nivåer). Returnerar score per kriterium + motivering."
        ),
        "variables": ["{rubric_json}"],
        "used_at": "/teacher/v2/rubrics",
        "model": "sonnet",
        "preview_input": (
            "Rubric: Förklarar nyckeltal · Resonerar konsekvenser\n"
            "Elev-text: 'Sparkvoten är hur mycket man sparar av lönen.'"
        ),
    },
    {
        "key": "stock_trade_feedback",
        "label": "Aktie-feedback · efter elev-handel",
        "category": "teacher_grading",
        "description": (
            "Pedagogisk återkoppling efter att eleven gjort en köp/sälj "
            "i aktie-simulatorn. Bedömer beslut + ger insikt."
        ),
        "variables": [],
        "used_at": "/v2/aktier",
        "model": "haiku",
        "preview_input": (
            "Eleven köpte 10 H&M @ 165 kr efter 8% kursfall samma vecka."
        ),
    },
    {
        "key": "diversification",
        "label": "Diversifierings-bedömning av portfölj",
        "category": "teacher_grading",
        "description": (
            "Bedömer hur väl-diversifierad elevens aktieportfölj är. "
            "Resultat: score + förbättringsförslag."
        ),
        "variables": [],
        "used_at": "/v2/aktier",
        "model": "haiku",
        "preview_input": (
            "Portfölj: 70 % H&M, 30 % Volvo. Inga andra branscher."
        ),
    },
    {
        "key": "wellbeing_monthly",
        "label": "Wellbeing · Månadssammanfattning",
        "category": "teacher_grading",
        "description": (
            "Genererar en pedagogisk månadssammanfattning av elevens "
            "wellbeing-data (tärningskast, känslolägen, ekonomistress)."
        ),
        "variables": [],
        "used_at": "/v2/postladan månadssamm.",
        "model": "haiku",
        "preview_input": (
            "Senaste 4 v: 2 sjukveckor, 1 stress-event, sparkvot −5 %."
        ),
    },

    # === D · Innehållsgeneratorer ===
    {
        "key": "module_gen",
        "label": "Modulgenerering för lärare",
        "category": "content_gen",
        "description": (
            "AI-skiss av en hel modul (3-5 steg) baserat på lärarens "
            "ämnesförslag. Lärare kan justera tonen i AI-skisser här."
        ),
        "variables": [],
        "used_at": "/teacher/v2/moduler · skissa-knappen",
        "model": "sonnet",
        "preview_input": "Lärare frågar: 'Skissa en modul om sparande för åk 2.'",
    },
    {
        "key": "stock_term_explain",
        "label": "Aktieterm-förklaring (eleven klickar på en term)",
        "category": "content_gen",
        "description": (
            "Förklarar aktietermer på lättläst svenska. Justera "
            "språknivå för åldersgruppen i din klass."
        ),
        "variables": [],
        "used_at": "/v2/aktier",
        "model": "haiku",
        "preview_input": "Term att förklara: 'P/E-tal'",
    },
    {
        "key": "category_explain",
        "label": "Kategori-förklaring (varför hamnade transaktion här)",
        "category": "content_gen",
        "description": (
            "Förklarar varför en transaktion blev kategoriserad på "
            "ett visst sätt. Pedagogisk så eleven förstår systemet."
        ),
        "variables": [],
        "used_at": "/v2/banken",
        "model": "haiku",
        "preview_input": (
            "Transaktion: 'WILLYS STORMARK' kategoriserades som 'Mat'."
        ),
    },
    {
        "key": "quiz_explain",
        "label": "Quiz-svar-förklaring",
        "category": "content_gen",
        "description": (
            "Förklarar varför ett quiz-svar var rätt/fel. Driver "
            "feedback efter att eleven kört quiz i en modul."
        ),
        "variables": [],
        "used_at": "/v2/moduler · quiz",
        "model": "haiku",
        "preview_input": (
            "Fråga: Vad är sparkvot? · Eleven svarade: 'Hur mycket "
            "man tjänar per timme.'"
        ),
    },
    {
        "key": "student_summary",
        "label": "Elev-sammanfattning för lärare",
        "category": "content_gen",
        "description": (
            "Snabb sammanfattning av en elevs status (ekonomiska val, "
            "lärande-progress, händelser) för lärar-överblick."
        ),
        "variables": [],
        "used_at": "/teacher/v2/elev/{id}",
        "model": "sonnet",
        "preview_input": (
            "Elev: Anton · 4 veckor i spelet · 2 olästa fakturor · "
            "kompetens: nivå 3 i 'Sparande'."
        ),
    },
]


_specs_cache: list[PromptSpec] | None = None


def get_all_specs() -> list[PromptSpec]:
    """Bygg och cacha PromptSpec-lista. Cacha så att lazy default-
    importerna bara körs en gång."""
    global _specs_cache
    if _specs_cache is not None:
        return _specs_cache
    defaults = _load_defaults()
    out: list[PromptSpec] = []
    for meta in _SPECS_META:
        key = meta["key"]
        out.append(PromptSpec(
            key=key,
            label=meta["label"],
            category=meta["category"],
            description=meta["description"],
            default_text=defaults.get(key, ""),
            variables=meta["variables"],
            used_at=meta["used_at"],
            model=meta["model"],
            preview_input=meta["preview_input"],
        ))
    _specs_cache = out
    return out


def get_spec(key: str) -> PromptSpec | None:
    for s in get_all_specs():
        if s.key == key:
            return s
    return None
