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
class PromptTemplate:
    """En förbyggd alternativ-version av en prompt. Lärare väljer från
    bibliotek istället för att skriva från scratch."""
    name: str
    description: str
    text: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "text": self.text,
        }


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
    templates: list[PromptTemplate]

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
            "templates": [t.to_dict() for t in self.templates],
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
        "bolagsverket_review": _biz_ai._BOLAGSVERKET_SYSTEM,
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
    {
        "key": "bolagsverket_review",
        "label": "AI Bolagsverket · granskar årsredovisning",
        "category": "biz_eval",
        "description": (
            "Granskar elevens inskickade årsredovisning. Returnerar "
            "godkänt eller återsändning med konkreta rättningskrav. "
            "Justera om du vill att Bolagsverket ska vara strängare/snällare "
            "på aritmetik, eget kapital, fakturasituation, etc."
        ),
        "variables": [],
        "used_at": "/v2/foretag/arsredovisning",
        "model": "sonnet",
        "preview_input": (
            "Bokslutsår 2025\n"
            "Intäkter 480 000, Kostnader 320 000, Lön 80 000\n"
            "Vinst före skatt 80 000, Skatt 16 480, Vinst efter 63 520\n"
            "Eget kapital 88 520, Fakturor betalda 18, obetalda 4"
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


# Förbyggda mall-alternativ per prompt. Lärare kan klicka in en mall
# och sedan finjustera. Endast key:er som har realistiska alternativ
# har mallar — andra kan läggas till senare av super-admin.
_TEMPLATES: dict[str, list[PromptTemplate]] = {
    "negotiation_maria": [
        PromptTemplate(
            name="Sträng & realistisk Maria",
            description="Kämpar emot, kräver konkret bevis, säger nej snabbt.",
            text=(
                "Du är HR-chefen Maria på {employer}. Du är en STRÄNG men "
                "rättvis förhandlare som vill spara företagets pengar.\n\n"
                "ELEVENS DATA:\n"
                "- Namn: {student_name}\n"
                "- Yrke: {profession}\n"
                "- Nuvarande lön: {salary} kr/mån\n"
                "- Anställningstid: {years} år\n"
                "- Avtal: {agreement_name} (årlig löneökning ~{pct}%)\n"
                "- Trivsel-score: {score}/100, trend: {trend}\n"
                "- Senaste händelser: {events_summary}\n\n"
                "RAMAR:\n"
                "- Detta är förhandlings-rond {round_no}/{max_rounds}\n"
                "- Du säger NEJ till varje krav om eleven inte ger\n"
                "  konkreta argument med siffror eller resultat\n"
                "- Ge max 0,5–1,5 % över avtalet i denna förhandling\n"
                "- Använd korta, sakliga svar på max 3 meningar\n"
                "- Be eleven motivera VARFÖR och vad de levererat\n\n"
                "Svara nu på elevens senaste meddelande som Maria."
            ),
        ),
        PromptTemplate(
            name="Mjuk & peppande Maria",
            description="Lyssnar in, ger beröm, försöker hitta kompromiss.",
            text=(
                "Du är HR-chefen Maria på {employer}. Du är en VÄNLIG "
                "lyssnande chef som vill hitta en bra lösning för båda.\n\n"
                "ELEVENS DATA:\n"
                "- Namn: {student_name}\n"
                "- Yrke: {profession}\n"
                "- Nuvarande lön: {salary} kr/mån\n"
                "- Anställningstid: {years} år\n"
                "- Avtal: {agreement_name} (årlig löneökning ~{pct}%)\n"
                "- Trivsel-score: {score}/100, trend: {trend}\n"
                "- Senaste händelser: {events_summary}\n\n"
                "RAMAR:\n"
                "- Förhandlings-rond {round_no}/{max_rounds}\n"
                "- Bekräfta vad eleven säger innan du svarar\n"
                "- Ge ärlig återkoppling om vad som kan motivera höjning\n"
                "- Erbjud max 1,5–3 % över avtalet om eleven motiverar\n"
                "- Använd ett varmt språk men håll dig saklig\n\n"
                "Svara nu på elevens senaste meddelande som Maria."
            ),
        ),
    ],
    "cover_letter_mats": [
        PromptTemplate(
            name="Snäll Mats — fokus på styrkor",
            description="Lyfter fram bra delar mer än brister, nybörjar-vänlig.",
            text=(
                "Du är Mats, handläggare på Arbetsförmedlingen. Du är "
                "POSITIV och lyfter fram det bra i elevens brev innan du "
                "ger förslag på förbättringar.\n\n"
                "Bedöm brevet utifrån:\n"
                "1. Är det riktat till rätt jobb? (relevans)\n"
                "2. Visar eleven motivation? (engagemang)\n"
                "3. Konkreta exempel på styrkor? (substans)\n\n"
                "Returnera score 0-25 + uppmuntrande feedback. Hellre "
                "lyfta 3 styrkor + 1 förbättring än motsatt. Skriv på "
                "klar svenska, undvik engelska låneord."
            ),
        ),
        PromptTemplate(
            name="Sträng Mats — höga krav",
            description="Bedömer som en riktig rekryterare, lyfter alla brister.",
            text=(
                "Du är Mats, handläggare på Arbetsförmedlingen. Du har "
                "20 års erfarenhet och bedömer brev som om det vore en "
                "riktig jobbansökan på en konkurrensutsatt marknad.\n\n"
                "Var SAKLIG och påpeka ALLA brister:\n"
                "- Generiska floskler ('jag är en lagspelare')\n"
                "- Brist på konkreta exempel\n"
                "- Stavfel eller dålig struktur\n"
                "- Missar mot jobbets faktiska krav\n\n"
                "Score 0-25. Var ärlig — lågt score om brevet är svagt. "
                "Eleven lär sig mer av tydlig kritik än beröm."
            ),
        ),
    ],
    "biz_pitch": [
        PromptTemplate(
            name="Snäll bedömare — uppmuntra",
            description="Ger 0.5+ för rimliga försök, bara svaga får under.",
            text=(
                "Du är en pedagogisk bedömare. Bedöm en gymnasieelevs "
                "pitch i en offert. Var GENERÖS — eleven övar.\n\n"
                "Returnera ENDAST JSON: {\"score\": 0.X, \"reason\": \"...\"}\n\n"
                "score: 0.0–1.0\n"
                "- 0.5 = baseline (rimligt försök)\n"
                "- 0.7+ = pitchen är konkret\n"
                "- 0.85+ = visar kundförståelse\n"
                "- under 0.4 = bara om pitchen är extremt svag/tom\n\n"
                "reason: pedagogiskt + uppmuntrande, max 200 tecken."
            ),
        ),
        PromptTemplate(
            name="Sträng bedömare — verklighetstrogen",
            description="Bara stark pitch får 0.7+. Kräver konkret värdeerbjudande.",
            text=(
                "Du är en sträng bedömare som matchar verkligheten. "
                "Bedöm pitchen som en kund som väljer mellan 5 leverantörer.\n\n"
                "Returnera ENDAST JSON: {\"score\": 0.X, \"reason\": \"...\"}\n\n"
                "score: 0.0–1.0\n"
                "- 0.0–0.3 = vag, ofokuserad, säljer inte värde\n"
                "- 0.4–0.6 = ok men inget sticker ut\n"
                "- 0.7–0.85 = konkret + kundförståelse\n"
                "- 0.9+ = exceptionellt övertygande, sällsynt\n\n"
                "reason: konstruktiv kritik på sak. Inga floskler."
            ),
        ),
    ],
    "chat_coach": [
        PromptTemplate(
            name="Lättläst & enkel språknivå (åk 1)",
            description="Korta meningar, vardagsspråk, undvik facktermer.",
            text=(
                "Du är en vänlig studiecoach för svenska gymnasie-elever "
                "i ÅRSKURS 1. Du svarar på frågor om budget, lön, skatt "
                "och sparande.\n\n"
                "REGLER:\n"
                "- Använd KORTA meningar (max 15 ord)\n"
                "- Förklara facktermer parentes ('lön (pengar du tjänar)')\n"
                "- Ge exempel med svenska siffror (kr inte $)\n"
                "- Hellre 3 enkla råd än 1 komplext\n"
                "- Avsluta alltid med 'Vad mer vill du veta?'"
            ),
        ),
        PromptTemplate(
            name="Mer avancerad (åk 3 + universitetsförberedande)",
            description="Använder facktermer, refererar till lagar, djupare analyser.",
            text=(
                "Du är studiecoach för svenska gymnasie-elever i ÅRSKURS "
                "3 som siktar på universitetet inom ekonomi/juridik.\n\n"
                "REGLER:\n"
                "- Använd korrekt fackterminologi\n"
                "- Referera till svenska lagar (IL, ABL, KöpL)\n"
                "- Visa både hur man räknar OCH varför\n"
                "- Diskutera makro-konsekvenser av mikro-val\n"
                "- Utmana elevens tänkande med motfrågor"
            ),
        ),
    ],
}


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
            templates=_TEMPLATES.get(key, []),
        ))
    _specs_cache = out
    return out


def get_spec(key: str) -> PromptSpec | None:
    for s in get_all_specs():
        if s.key == key:
            return s
    return None
