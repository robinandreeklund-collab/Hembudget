"""AI-funktioner för företagsläget.

Spec: deb/README.md avsnitt 9 ("AI-integration — var och varför").

LLM ska göra det den är bra på (språk, bedömning) — inte det den är
dålig på (deterministiska siffror). Konkret 4 funktioner:

1. evaluate_quote_pitch     · Bedömer pitchens kvalitet 0..1 (Haiku)
   Används av acceptansmodellen som en av 5 viktade faktorer.
2. evaluate_marketing_copy  · Kvalitetsfaktor 0.5..1.5 + feedback (Haiku)
   Multipliceras på base_pipeline_boost.
3. generate_job_description · Skapar varierande jobbeskrivningar (Haiku)
   Används av tick_engine när vi seedar JobOpportunity.
4. review_business_idea     · Modereringsspår (Haiku) — krav, inte finess.
   Olagligt/oetiskt → returnerar reject med pedagogisk motivering.

ALLA funktioner har **deterministisk fallback** så simulatorn fungerar
utan API-nyckel. Detta är policy från CLAUDE.md ("avsaknad av nyckel
= tyst av, inte 500"). Fallbacken är medvetet konservativ — neutral
0.5 / 1.0-faktor — så att eleven inte straffas för att läraren inte
satt upp AI.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

log = logging.getLogger(__name__)


# === Kvalitetsbedömning av pitch i offert ===


_PITCH_SYSTEM = """Du är en pedagogisk bedömare som hjälper en gymnasieelev
träna offertskrivande. Du läser elevens pitch på en offert till en kund och
bedömer hur övertygande och konkret den är.

Returnera ENDAST JSON i formatet:
{"score": 0.X, "reason": "kort förklaring på svenska"}

score: ett tal mellan 0.0 och 1.0
- 0.0–0.3 = svag pitch (vag, ofokuserad, säljer inte värde)
- 0.4–0.6 = ok men inte stark
- 0.7–1.0 = stark (konkret, visar förståelse för kundens behov,
  professionell ton)

Var ärlig men inte hård — eleven ska få konstruktiv feedback. Du
bedömer SPRÅKLIG kvalitet, inte priset. Pris hanteras separat."""


def evaluate_quote_pitch(
    *,
    pitch: str,
    job_title: str,
    job_description: str,
    teacher_id: Optional[int] = None,
) -> Optional[float]:
    """Returnera pitch-kvalitet 0..1, eller None om AI är otillgänglig.

    Tystas till None vid fel — anroparen skriver in None i Quote.pitch_quality
    vilket tolkas som 0.5 (neutral) av acceptansmodellen.
    """
    if not pitch or not pitch.strip():
        return None
    try:
        from ..school.ai import (
            MODEL_HAIKU, _call_claude, is_available,
        )
        if not is_available():
            return _deterministic_pitch_score(pitch)

        user = (
            f"Jobbet: {job_title}\n"
            f"Beskrivning: {job_description}\n\n"
            f"Elevens pitch:\n{pitch.strip()}\n\n"
            f"Bedöm pitchens kvalitet (returnera bara JSON)."
        )
        from ..school.ai import resolve_prompt as _resolve
        result = _call_claude(
            model=MODEL_HAIKU,
            system=_resolve(
                "biz_pitch", teacher_id=teacher_id, default=_PITCH_SYSTEM,
            ),
            user_prompt=user,
            max_tokens=150,
            teacher_id=teacher_id,
        )
        if result is None:
            return _deterministic_pitch_score(pitch)
        score = _extract_json_score(result.text, key="score")
        if score is None:
            return _deterministic_pitch_score(pitch)
        return max(0.0, min(1.0, score))
    except Exception:
        log.exception("evaluate_quote_pitch failed")
        return _deterministic_pitch_score(pitch)


def _deterministic_pitch_score(pitch: str) -> float:
    """Fallback när AI saknas. Heuristisk poäng från textens längd +
    förekomst av nyckelord. Aldrig perfekt, men bättre än None."""
    words = len(pitch.split())
    score = 0.4  # baseline
    if words >= 30:
        score += 0.15
    if words >= 60:
        score += 0.10
    keywords = (
        "kund", "snabb", "kvalitet", "erfarenhet", "garanti",
        "leverans", "uppfölj", "tids", "expert", "anpassad",
        "personlig", "referens",
    )
    hits = sum(1 for k in keywords if k in pitch.lower())
    score += min(0.20, hits * 0.05)
    return max(0.2, min(0.85, score))


# === Marknadsföringscopy ===


_MARKETING_SYSTEM = """Du är en pedagogisk marknadsförare som bedömer
en gymnasieelevs reklam-text för en marknadsföringskampanj.

Returnera ENDAST JSON i formatet:
{"factor": 1.X, "feedback": "kort förklaring på svenska"}

factor: en multiplikator mellan 0.5 och 1.5
- 0.5–0.8 = svag (luddig, inget tydligt värdeerbjudande, dåligt språk)
- 0.9–1.1 = ok (begripligt men inte spännande)
- 1.2–1.5 = stark (konkret målgrupp, tydlig CTA, känsla)

feedback: ge eleven 1-2 konkreta förbättringsförslag, max 200 tecken."""


def evaluate_marketing_copy(
    *,
    copy_text: str,
    kind: str,
    teacher_id: Optional[int] = None,
) -> Optional[dict]:
    """Returnera dict med 'factor' (0.5..1.5) + 'feedback' (text).

    None om AI är ej tillgänglig.
    """
    if not copy_text or not copy_text.strip():
        return None
    try:
        from ..school.ai import (
            MODEL_HAIKU, _call_claude, is_available,
        )
        if not is_available():
            return _deterministic_marketing(copy_text)

        user = (
            f"Kampanjtyp: {kind}\n\n"
            f"Elevens copy:\n{copy_text.strip()}\n\n"
            f"Bedöm copy:n (returnera bara JSON)."
        )
        from ..school.ai import resolve_prompt as _resolve
        result = _call_claude(
            model=MODEL_HAIKU,
            system=_resolve(
                "biz_marketing",
                teacher_id=teacher_id,
                default=_MARKETING_SYSTEM,
            ),
            user_prompt=user,
            max_tokens=300,
            teacher_id=teacher_id,
        )
        if result is None:
            return _deterministic_marketing(copy_text)
        factor = _extract_json_score(result.text, key="factor")
        feedback = _extract_json_string(result.text, key="feedback")
        if factor is None:
            return _deterministic_marketing(copy_text)
        return {
            "factor": max(0.5, min(1.5, factor)),
            "feedback": feedback or "Bra jobbat!",
        }
    except Exception:
        log.exception("evaluate_marketing_copy failed")
        return _deterministic_marketing(copy_text)


def _deterministic_marketing(copy_text: str) -> dict:
    """Fallback för marknadsföringscopy."""
    words = len(copy_text.split())
    factor = 0.85
    if words >= 20:
        factor += 0.1
    if words >= 50:
        factor += 0.1
    cta = any(
        p in copy_text.lower()
        for p in ("ring", "boka", "klicka", "besök", "anmäl", "köp", "rabatt")
    )
    if cta:
        factor += 0.1
    return {
        "factor": max(0.5, min(1.5, factor)),
        "feedback": (
            "Bra grund. Tänk på en tydligare CTA om det saknas."
            if not cta
            else "Bra med tydlig uppmaning! Var konkret om vad kunden får."
        ),
    }


# === Affärsidé-moderering (modereringsspår) ===

_BUSINESS_IDEA_SYSTEM = """Du är pedagogisk granskare som modererar
elevers affärsidéer i en skol-simulator. Din uppgift: stoppa olagliga
eller uppenbart oetiska idéer (drogförsäljning, vapen, ocker, bedrägeri),
men släppa igenom allt som är legalt — även 'roliga' idéer som
tomtfärger eller drönarfilm.

Returnera ENDAST JSON i formatet:
{"verdict": "approved|rejected", "reason": "förklaring på svenska"}

approved: idén är OK (det är default — bara stoppa det som är klart fel)
rejected: idén är olaglig eller uppenbart oetisk
reason: kort motivering, max 200 tecken. Vid rejected: var pedagogisk
        och föreslå en justering."""


def review_business_idea(
    *,
    idea_text: str,
    teacher_id: Optional[int] = None,
) -> dict:
    """Returnera {'verdict': 'approved'|'rejected', 'reason': str}.

    Vid AI-fel: defaultar till approved (vi vill inte blockera elever
    bara för att API:et är nere). Tappade granskningar kan läraren
    städa manuellt via klassöversikt.
    """
    if not idea_text or not idea_text.strip():
        return {"verdict": "rejected", "reason": "Ingen idé skriven."}

    # Hård-regel-screen FÖRE AI · vissa keywords avvisas direkt
    blocked = (
        "narkotika", "droger", "kokain", "heroin",
        "vapen", "ammunition", "sprängmedel",
        "barnpornografi",
    )
    lower = idea_text.lower()
    for kw in blocked:
        if kw in lower:
            return {
                "verdict": "rejected",
                "reason": (
                    f"Idén innehåller ord som tyder på olaglig "
                    f"verksamhet ('{kw}'). Välj en lagligt produkt eller "
                    f"tjänst."
                ),
            }

    try:
        from ..school.ai import (
            MODEL_HAIKU, _call_claude, is_available,
        )
        if not is_available():
            return {"verdict": "approved", "reason": ""}

        user = f"Affärsidé:\n{idea_text.strip()}\n\nBedöm (returnera JSON)."
        result = _call_claude(
            model=MODEL_HAIKU,
            system=_BUSINESS_IDEA_SYSTEM,
            user_prompt=user,
            max_tokens=200,
            teacher_id=teacher_id,
        )
        if result is None:
            return {"verdict": "approved", "reason": ""}
        verdict = _extract_json_string(result.text, key="verdict") or "approved"
        reason = _extract_json_string(result.text, key="reason") or ""
        if verdict not in ("approved", "rejected"):
            verdict = "approved"
        return {"verdict": verdict, "reason": reason}
    except Exception:
        log.exception("review_business_idea failed")
        return {"verdict": "approved", "reason": ""}


# === Generera jobbeskrivningar ===
#
# Notera: vi använder denna SPARSAMT eftersom det är dyrt (en per
# nyskapad opportunity per elev per vecka). Default i tick_engine är
# att seed_data.JobTemplate.description används direkt utan AI. Denna
# funktion finns för att läraren EXPLICIT kan trigga "variera
# beskrivningar" på klassen via en knapp i lärar-vyn.

_JOB_DESC_SYSTEM = """Du genererar realistiska jobbeskrivningar för en
företagssimulator. Texten ska vara på svenska, 2–4 meningar, beskriva
exakt vad kunden vill ha utfört, ev. praktiska detaljer (storlek,
materialval, deadline-press), och hålla en naturlig kund-ton.

Returnera ENDAST själva beskrivningstexten — ingen rubrik, ingen JSON."""


def generate_job_description(
    *,
    job_title: str,
    industry: str,
    customer_name: str,
    teacher_id: Optional[int] = None,
) -> Optional[str]:
    """Returnera 2–4-meningars text. None om AI ej tillgänglig."""
    try:
        from ..school.ai import (
            MODEL_HAIKU, _call_claude, is_available,
        )
        if not is_available():
            return None
        user = (
            f"Jobb: {job_title}\n"
            f"Bransch: {industry}\n"
            f"Kund: {customer_name}\n\n"
            f"Skriv jobbeskrivningen som om kunden förklarar vad hen vill ha gjort."
        )
        from ..school.ai import resolve_prompt as _resolve
        result = _call_claude(
            model=MODEL_HAIKU,
            system=_resolve(
                "biz_job_desc",
                teacher_id=teacher_id,
                default=_JOB_DESC_SYSTEM,
            ),
            user_prompt=user,
            max_tokens=200,
            teacher_id=teacher_id,
        )
        return result.text.strip() if result else None
    except Exception:
        log.exception("generate_job_description failed")
        return None


# === JSON-helpers ===


def _extract_json_score(text: str, *, key: str) -> Optional[float]:
    try:
        m = re.search(r"\{.*?\}", text, re.DOTALL)
        if not m:
            return None
        obj = json.loads(m.group(0))
        v = obj.get(key)
        return float(v) if v is not None else None
    except Exception:
        return None


def _extract_json_string(text: str, *, key: str) -> Optional[str]:
    try:
        m = re.search(r"\{.*?\}", text, re.DOTALL)
        if not m:
            return None
        obj = json.loads(m.group(0))
        v = obj.get(key)
        return str(v).strip() if v is not None else None
    except Exception:
        return None


# === Bolagsverket · AI granskar elevens årsredovisning (Fas B) ===

_BOLAGSVERKET_SYSTEM = """Du är AI-handläggare på Bolagsverket. En elev
har skickat in årsredovisning för sitt simulerade bolag och du ska
granska den pedagogiskt — både realistiskt och hjälpsamt.

Kontrollera:
1. Är resultaträkningen aritmetiskt korrekt? (intäkter − kostnader −
   skatt = vinst-efter-skatt)
2. Är bolagsskatten rimlig? (~20.6% av vinst-före-skatt vid +;
   0 vid förlust)
3. Är eget kapital rimligt? (start-aktiekapital + ackumulerad vinst)
4. Finns några varningstecken? (massa obetalda fakturor, väldigt liten
   omsättning vs antal månader, etc.)

Returnera ENDAST JSON i formatet:
{
  "decision": "approved" | "rejected",
  "feedback_md": "pedagogisk markdown-text till eleven (max 600 tecken)",
  "issues": [{"category": "<kategori>", "explanation": "<förklaring>"}]
}

Vid `approved`: feedback_md är beröm + ev. förbättrings-tips för nästa år.
Vid `rejected`: feedback_md förklarar tydligt VAD som behöver rättas
och issues[]-arrayen har konkreta items.

Var pedagogisk men inte för snäll — eleven lär sig av tydlig kritik.
Rejekta automatiskt om resultatet inte stämmer aritmetiskt."""


def review_annual_report(
    *,
    fiscal_year: int,
    revenue_total: int,
    expense_total: int,
    salary_total: int,
    profit_before_tax: int,
    corporate_tax: int,
    profit_after_tax: int,
    equity_end: int,
    n_invoices_paid: int,
    n_invoices_unpaid: int,
    student_note: Optional[str] = None,
    teacher_id: Optional[int] = None,
) -> Optional[dict]:
    """Returnera dict med {'decision', 'feedback_md', 'issues'}.

    None om AI är otillgänglig — anroparen skapar då en deterministisk
    fallback (auto-approve om aritmetiken stämmer).
    """
    try:
        from ..school.ai import (
            MODEL_SONNET, _call_claude, is_available, resolve_prompt,
        )
        if not is_available():
            return None

        user = (
            f"## Årsredovisning {fiscal_year}\n"
            f"Intäkter (omsättning): {revenue_total} kr\n"
            f"Kostnader (rörliga + fasta): {expense_total} kr\n"
            f"Lön (egen): {salary_total} kr\n"
            f"Vinst före skatt: {profit_before_tax} kr\n"
            f"Bolagsskatt 20.6%: {corporate_tax} kr\n"
            f"Vinst efter skatt: {profit_after_tax} kr\n"
            f"Eget kapital, utgående: {equity_end} kr\n"
            f"Fakturor betalda: {n_invoices_paid}\n"
            f"Fakturor obetalda: {n_invoices_unpaid}\n"
        )
        if student_note:
            user += f"\n## Elevens kommentar\n{student_note}\n"
        user += "\nGranska och returnera JSON enligt formatet."

        result = _call_claude(
            model=MODEL_SONNET,
            system=resolve_prompt(
                "bolagsverket_review",
                teacher_id=teacher_id,
                default=_BOLAGSVERKET_SYSTEM,
            ),
            user_prompt=user,
            max_tokens=900,
            teacher_id=teacher_id,
        )
        if result is None:
            return None

        # Försök parsa JSON
        try:
            m = re.search(r"\{.*\}", result.text, re.DOTALL)
            if not m:
                return None
            obj = json.loads(m.group(0))
            decision = obj.get("decision", "approved")
            if decision not in ("approved", "rejected"):
                decision = "approved"
            return {
                "decision": decision,
                "feedback_md": str(obj.get("feedback_md", ""))[:1500],
                "issues": obj.get("issues", []) if isinstance(
                    obj.get("issues"), list,
                ) else [],
            }
        except Exception:
            log.exception("review_annual_report: kunde inte parsa AI-svar")
            return None
    except Exception:
        log.exception("review_annual_report failed")
        return None
