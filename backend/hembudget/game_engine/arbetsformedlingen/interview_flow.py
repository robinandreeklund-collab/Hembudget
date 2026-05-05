"""A4 · Intervju-flöde state-machine.

Spec: dev/game-motor/05-arbetsformedlingen.md (5-rond intervjuflöde)

5 ronder med pedagogiska val + Mats-feedback + pentagon-effekter.

Varje round-funktion tar ett input-objekt och returnerar (RoundResult,
updated_application). Status-machine sköts av `submit_round_response`
som dispatcherar till rätt funktion baserat på application.current_round.
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Optional

from sqlalchemy.orm import Session

from ...db.models import JobApplication
from ..pentagon import apply_pentagon_delta
from ..pools.yrkespool import YRKE_BY_KEY
from .matching import JobOpening

log = logging.getLogger(__name__)


# === Input-objekt per rond ===

@dataclass
class Round1Input:
    """Sprint 7 · personligt brev (ersätter cover_letter_hours-slider).
    Eleven skriver brevet, Sonnet bedömer kvalitet och ger feedback."""
    cover_letter_text: str = ""


@dataclass
class Round2Input:
    tone: Literal["saker", "reflekterande", "ansprakvol", "arlig"] = "reflekterande"
    answers: list[str] = field(default_factory=list)


@dataclass
class Round3Input:
    """Sprint 7 · case-uppgift med riktig text. AI-bedömer svaret 0-15."""
    case_answer_text: str = ""


@dataclass
class Round4Input:
    """Sprint 7 · slutintervju med klädsel + research-svar.
    research_text bedöms av AI för språkkvalitet + företagskännedom."""
    dress: Literal["vardag", "business_casual", "formell"] = "business_casual"
    research_text: str = ""


@dataclass
class Round5Decision:
    decision: Literal["accept", "decline", "negotiate"] = "accept"
    counter_offer_kr: Optional[int] = None


@dataclass
class RoundResult:
    """Resultat av en avslutad rond."""
    round_n: int
    score_delta: int                # -10 till +10 per rond
    feedback_md: str
    pentagon_delta: dict[str, int]
    advanced_to: int                # Nästa round_n eller 0 om klart
    final_status: Optional[str] = None


# === Apply ===


def apply_to_job(
    s: Session,
    *,
    student_id: int,
    opening: JobOpening,
    today: date,
) -> JobApplication:
    """Skapa ny JobApplication, status round_1, current_round=1."""
    # Lagra full annons-data så lärar-vy + AI-kontext kan visa
    # exakt vad eleven såg när hen sökte (annonser regenereras
    # varje månad, så utan denna snapshot går historiken förlorad).
    job_ad_snapshot = {
        "listing_id": opening.listing_id,
        "description": opening.description,
        "company_blurb": opening.company_blurb,
        "job_description": opening.job_description,
        "requirements": opening.requirements,
        "meriter": opening.meriter,
        "benefits": opening.benefits,
        "employment_type": opening.employment_type,
        "application_deadline": opening.application_deadline,
        "work_hours": opening.work_hours,
        "start_date": opening.start_date,
    }
    app = JobApplication(
        yrke_key=opening.yrke_key,
        yrke_display=opening.yrke_display,
        employer_name=opening.employer_name,
        city_key=opening.city_key,
        city_display=opening.city_display,
        monthly_gross_offered=None,
        match_score=opening.match_score,
        status="round_1",
        current_round=1,
        rounds_data={"opening": {
            "listing_id": opening.listing_id,
            "ssyk": opening.yrke_ssyk,
            "median_salary": opening.monthly_gross_median,
            "match_score": opening.match_score,
        }},
        started_on=today,
    )
    if hasattr(app, "job_ad_data"):
        app.job_ad_data = job_ad_snapshot
    s.add(app)
    s.flush()

    # Pentagon: +1 safety (har sökt = aktiv karriär)
    try:
        apply_pentagon_delta(
            student_id, axis="safety", requested_delta=+1,
            reason_kind="decision", reason_id=app.id,
            reason_table="job_applications",
            explanation=f"sökt jobb · {opening.yrke_display}",
        )
    except Exception:
        log.exception("pentagon delta failed for apply_to_job")
    return app


# === Round logic ===


def _round1(
    s: Session, *, app: JobApplication, student_id: int,
    inp: Round1Input,
) -> RoundResult:
    """Rond 1 · CV + personligt brev. Sonnet bedömer brev-kvalitet 0-25
    poäng. Score_delta -10..+10 baserat på AI-score / 1.6.
    """
    text = (inp.cover_letter_text or "").strip()
    word_count = len([w for w in text.split() if w])

    # Hämta annons-data för AI-kontexten (om sparad)
    job_ad = (app.job_ad_data or {}) if hasattr(app, "job_ad_data") else {}

    # AI-bedömning · faller back till heuristik om AI saknas
    ai_score = None
    ai_feedback = None
    ai_highlights: list[str] = []
    if word_count >= 30:
        try:
            from ...school.ai import evaluate_cover_letter
            from ...school.engines import master_session as _ms_dun
            from ...school.models import Student as _Stu_dun
            with _ms_dun() as ms:
                stu = ms.get(_Stu_dun, student_id)
                teacher_id = stu.teacher_id if stu else None
            res = evaluate_cover_letter(
                cover_letter_text=text,
                job_title=app.yrke_display,
                employer=app.employer_name,
                job_description=job_ad.get("description")
                    or app.yrke_display,
                requirements=job_ad.get("requirements") or [],
                teacher_id=teacher_id,
            )
            if res is not None:
                ai_score = int(res.data.get("score", 12))
                ai_feedback = res.data.get("feedback_md", "")
                ai_highlights = res.data.get("highlights", []) or []
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "round1: AI-bedömning misslyckades — fallback till heuristik",
            )

    # Heuristik-fallback: bedöm baserat på längd
    if ai_score is None:
        if word_count < 50:
            ai_score = 6
            ai_feedback = (
                "Brevet är för kort. Skriv 200-400 ord där du förklarar "
                "varför just detta jobbet och ge konkreta exempel."
            )
        elif word_count < 150:
            ai_score = 12
            ai_feedback = (
                "Skapligt utgångsläge men kunde vara mer detaljerat. "
                "Lägg till ett konkret exempel från din erfarenhet."
            )
        elif word_count > 600:
            ai_score = 14
            ai_feedback = (
                "För långt. Få brev läses helt om de är över 400 ord. "
                "Kortare, tydligare = bättre."
            )
        else:
            ai_score = 17
            ai_feedback = "Lagom längd. Bra struktur."

    # Mappa 0-25 → -10..+10
    score_delta = max(-10, min(10, int(ai_score / 1.25 - 10)))

    # Pentagon: alltid lite stress (-2 hälsa). Bra brev → +2 carrier.
    # Dåligt brev → -1 self-confidence (safety).
    pentagon: dict[str, int] = {"halsa": -2}
    if ai_score >= 18:
        pentagon["karriar"] = +2
        pentagon["safety"] = +1
    elif ai_score < 10:
        pentagon["safety"] = -2

    feedback = (
        f"**Rond 1 · Personligt brev**\n\n"
        f"AI-bedömning: **{ai_score}/25** poäng.\n\n"
        f"{ai_feedback or ''}\n"
    )
    if ai_highlights:
        feedback += "\n**Det här gjorde du bra:**\n"
        for h in ai_highlights:
            feedback += f"- {h}\n"

    rd = app.rounds_data or {}
    rd["round_1"] = {
        "cover_letter_text": text,
        "word_count": word_count,
        "ai_score": ai_score,
        "ai_feedback": ai_feedback,
        "score_delta": score_delta,
    }
    app.rounds_data = rd
    if hasattr(app, "cover_letter_text"):
        app.cover_letter_text = text
    if hasattr(app, "ai_feedback_md"):
        existing = app.ai_feedback_md or ""
        app.ai_feedback_md = (existing + "\n\n" + feedback).strip() if existing else feedback
    app.status = "round_2"
    app.current_round = 2
    return RoundResult(
        round_n=1, score_delta=score_delta, feedback_md=feedback,
        pentagon_delta=pentagon, advanced_to=2,
    )


_TONE_EFFECTS = {
    "saker": (+2, {"safety": +1}),
    "reflekterande": (+1, {}),
    "ansprakvol": (-1, {"safety": -1}),
    "arlig": (+1, {"social": +1}),
}


_INTERVIEW_QUESTIONS = [
    "Berätta kort om dig själv och varför du söker just det här jobbet.",
    "Vad är din största styrka och kan du ge ett konkret exempel?",
    "Vad är din lägsta lönenivå du kan acceptera?",
    "Vilka tider passar för en personlig intervju?",
]


def _round2(
    s: Session, *, app: JobApplication, student_id: int,
    inp: Round2Input,
) -> RoundResult:
    """Rond 2 · Telefonintervju. AI-bedömer kvaliteten på elevens svar
    samt språket. Score_delta = (tone_delta) + (AI_score / 3)."""
    delta, extra = _TONE_EFFECTS.get(inp.tone, (+0, {}))
    answers = [a for a in inp.answers if a and len(a.strip()) > 5]
    n_answers = len(answers)
    if n_answers >= 4:
        delta += 1

    # AI-bedömning av textsvaren (om eleven faktiskt skrev något)
    ai_score = None
    ai_lang_score = None
    ai_feedback = None
    if n_answers >= 2:
        try:
            from ...school.ai import evaluate_interview_answers
            from ...school.engines import master_session as _ms_2
            from ...school.models import Student as _Stu_2
            with _ms_2() as ms:
                stu = ms.get(_Stu_2, student_id)
                teacher_id = stu.teacher_id if stu else None
            qa = []
            for i, a in enumerate(answers):
                qa.append({
                    "question": _INTERVIEW_QUESTIONS[i] if i < len(_INTERVIEW_QUESTIONS)
                                else f"Fråga {i+1}",
                    "answer": a,
                })
            res = evaluate_interview_answers(
                job_title=app.yrke_display,
                employer=app.employer_name,
                questions_and_answers=qa,
                teacher_id=teacher_id,
            )
            if res is not None:
                ai_score = int(res.data.get("score", 8))
                ai_lang_score = int(res.data.get("language_score", 3))
                ai_feedback = res.data.get("feedback_md", "")
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "round2: AI-bedömning misslyckades",
            )

    # Mappa AI-score till score_delta. Tona-bonus läggs ovanpå.
    if ai_score is not None:
        delta += int(ai_score / 5 - 1.5)  # 0..15 → -1..+1.5

    score_delta = max(-10, min(10, delta))
    pentagon: dict[str, int] = {"halsa": -2}
    pentagon.update({k: v for k, v in extra.items()})
    if ai_lang_score is not None:
        if ai_lang_score >= 4:
            pentagon["karriar"] = pentagon.get("karriar", 0) + 1
        elif ai_lang_score <= 1:
            pentagon["safety"] = pentagon.get("safety", 0) - 1

    feedback = (
        f"**Rond 2 · Telefonintervju**\n\n"
        f"Du valde tonen **{inp.tone}** och svarade på {n_answers} "
        f"frågor.\n\n"
    )
    if ai_score is not None:
        feedback += f"AI-bedömning: **{ai_score}/15** poäng på svarskvalitet"
        if ai_lang_score is not None:
            feedback += f" (varav språk {ai_lang_score}/5)"
        feedback += ".\n\n"
        if ai_feedback:
            feedback += ai_feedback + "\n\n"
    if inp.tone == "ansprakvol":
        feedback += (
            "_Säker inställning är bra — men för tidigt anspråksfull "
            "kan rekryteraren tolka som arrogant._\n"
        )
    elif inp.tone == "arlig":
        feedback += (
            "_Ärlig är vinnande för relation, men kan vara för naivt om "
            "du visar svaga sidor utan kontext._\n"
        )

    rd = app.rounds_data or {}
    rd["round_2"] = {
        "tone": inp.tone,
        "n_answers": n_answers,
        "answers": answers,
        "ai_score": ai_score,
        "ai_lang_score": ai_lang_score,
        "ai_feedback": ai_feedback,
        "score_delta": score_delta,
    }
    app.rounds_data = rd
    if hasattr(app, "ai_feedback_md"):
        existing = app.ai_feedback_md or ""
        app.ai_feedback_md = (existing + "\n\n" + feedback).strip() if existing else feedback
    app.status = "round_3"
    app.current_round = 3
    return RoundResult(
        round_n=2, score_delta=score_delta, feedback_md=feedback,
        pentagon_delta=pentagon, advanced_to=3,
    )


def _round3(
    s: Session, *, app: JobApplication, student_id: int,
    inp: Round3Input,
) -> RoundResult:
    """Rond 3 · Kompetenstest / case-uppgift. Eleven skriver lösning,
    Sonnet bedömer kvalitet 0-15. Score_delta = (ai_score - 7) / 2."""
    text = (inp.case_answer_text or "").strip()
    word_count = len([w for w in text.split() if w])

    yrke = YRKE_BY_KEY.get(app.yrke_key)
    role = yrke.display if yrke else app.yrke_display

    # AI-bedömning av case-svaret
    ai_score = None
    ai_lang_score = None
    ai_feedback = None
    if word_count >= 30:
        try:
            from ...school.ai import evaluate_interview_answers
            from ...school.engines import master_session as _ms_3
            from ...school.models import Student as _Stu_3
            with _ms_3() as ms:
                stu = ms.get(_Stu_3, student_id)
                teacher_id = stu.teacher_id if stu else None
            res = evaluate_interview_answers(
                job_title=app.yrke_display,
                employer=app.employer_name,
                questions_and_answers=[{
                    "question": (
                        f"Case-uppgift för rollen som {role}: beskriv hur "
                        "du skulle hantera en konkret arbetssituation."
                    ),
                    "answer": text,
                }],
                teacher_id=teacher_id,
            )
            if res is not None:
                ai_score = int(res.data.get("score", 8))
                ai_lang_score = int(res.data.get("language_score", 3))
                ai_feedback = res.data.get("feedback_md", "")
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "round3: AI-bedömning misslyckades — fallback heuristik",
            )

    # Heuristik-fallback baserat på längd
    if ai_score is None:
        if word_count < 30:
            ai_score = 4
            ai_feedback = "För kort case-svar. Skriv minst 80 ord med ett konkret resonemang."
        elif word_count < 80:
            ai_score = 7
            ai_feedback = "OK svar men kunde vara djupare. Visa hur du tänker steg-för-steg."
        elif word_count > 400:
            ai_score = 9
            ai_feedback = "Lite för långt. Var koncis — visa att du kan summera."
        else:
            ai_score = 11
            ai_feedback = "Lagom djup. Bra struktur."

    # Mappa 0-15 → -4..+4
    score_delta = max(-4, min(4, int(ai_score / 2 - 4)))

    pentagon: dict[str, int] = {"halsa": -1}
    if ai_score >= 12:
        pentagon["karriar"] = +2
    elif ai_score < 6:
        pentagon["safety"] = -1
    if ai_lang_score is not None and ai_lang_score >= 4:
        pentagon["karriar"] = pentagon.get("karriar", 0) + 1

    feedback = (
        f"**Rond 3 · Kompetenstest · case-uppgift**\n\n"
        f"AI-bedömning: **{ai_score}/15** poäng på case-svaret"
    )
    if ai_lang_score is not None:
        feedback += f" (varav språk {ai_lang_score}/5)"
    feedback += ".\n\n"
    if ai_feedback:
        feedback += ai_feedback + "\n"

    rd = app.rounds_data or {}
    rd["round_3"] = {
        "case_answer_text": text,
        "word_count": word_count,
        "ai_score": ai_score,
        "ai_lang_score": ai_lang_score,
        "ai_feedback": ai_feedback,
        "score_delta": score_delta,
    }
    app.rounds_data = rd
    if hasattr(app, "case_answer_text"):
        app.case_answer_text = text
    if hasattr(app, "ai_feedback_md"):
        existing = app.ai_feedback_md or ""
        app.ai_feedback_md = (existing + "\n\n" + feedback).strip() if existing else feedback
    app.status = "round_4"
    app.current_round = 4
    return RoundResult(
        round_n=3, score_delta=score_delta, feedback_md=feedback,
        pentagon_delta=pentagon, advanced_to=4,
    )


def _round4(
    s: Session, *, app: JobApplication, student_id: int,
    inp: Round4Input,
) -> RoundResult:
    """Rond 4 · Slutintervju på plats. Klädsel + research-svar.
    Research-svaret AI-bedöms för språk + företagskännedom."""
    dress_score = {"vardag": -1, "business_casual": +2, "formell": +1}.get(inp.dress, 0)
    research_text = (inp.research_text or "").strip()
    research_words = len([w for w in research_text.split() if w])

    # AI-bedömning av research-svaret
    ai_score = None
    ai_lang_score = None
    ai_feedback = None
    if research_words >= 20:
        try:
            from ...school.ai import evaluate_interview_answers
            from ...school.engines import master_session as _ms_4
            from ...school.models import Student as _Stu_4
            with _ms_4() as ms:
                stu = ms.get(_Stu_4, student_id)
                teacher_id = stu.teacher_id if stu else None
            res = evaluate_interview_answers(
                job_title=app.yrke_display,
                employer=app.employer_name,
                questions_and_answers=[{
                    "question": (
                        f"Vad vet du om {app.employer_name}? "
                        f"Varför vill du jobba just där?"
                    ),
                    "answer": research_text,
                }],
                teacher_id=teacher_id,
            )
            if res is not None:
                ai_score = int(res.data.get("score", 8))
                ai_lang_score = int(res.data.get("language_score", 3))
                ai_feedback = res.data.get("feedback_md", "")
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "round4: AI-bedömning misslyckades",
            )

    if ai_score is None:
        if research_words < 30:
            ai_score = 5
            ai_feedback = "Du visste inte tillräckligt om företaget. Läs deras hemsida och nyhetsrum."
        elif research_words > 250:
            ai_score = 10
            ai_feedback = "Bra detaljnivå men håll dig till relevanta saker för rollen."
        else:
            ai_score = 9
            ai_feedback = "Lagom research. Visar att du tagit dig tid."

    research_delta = int(ai_score / 4 - 2)  # 0..15 → -2..+1.75
    score_delta = dress_score + research_delta
    pentagon: dict[str, int] = {"halsa": -3}
    if research_words >= 100:
        pentagon["leisure"] = -1
    if ai_score >= 12:
        pentagon["karriar"] = +2
    if ai_lang_score is not None and ai_lang_score >= 4:
        pentagon["karriar"] = pentagon.get("karriar", 0) + 1

    feedback = (
        f"**Rond 4 · Intervju på plats**\n\n"
        f"Klädsel: **{inp.dress}** (rekryteraren noterar). "
    )
    if research_words >= 20:
        feedback += (
            f"Research-svar bedömt **{ai_score}/15** poäng"
        )
        if ai_lang_score is not None:
            feedback += f" (språk {ai_lang_score}/5)"
        feedback += ".\n\n"
        if ai_feedback:
            feedback += ai_feedback + "\n"
    else:
        feedback += "Du sa inte mycket om företaget — det märktes.\n"

    rd = app.rounds_data or {}
    rd["round_4"] = {
        "dress": inp.dress,
        "research_text": research_text,
        "research_words": research_words,
        "ai_score": ai_score,
        "ai_lang_score": ai_lang_score,
        "ai_feedback": ai_feedback,
        "score_delta": score_delta,
    }
    app.rounds_data = rd
    if hasattr(app, "ai_feedback_md"):
        existing = app.ai_feedback_md or ""
        app.ai_feedback_md = (existing + "\n\n" + feedback).strip() if existing else feedback
    app.status = "round_5"
    app.current_round = 5
    return RoundResult(
        round_n=4, score_delta=score_delta, feedback_md=feedback,
        pentagon_delta=pentagon, advanced_to=5,
    )


def _compute_final_score(app: JobApplication) -> int:
    """Summera alla ronders score_delta + match_score-bias."""
    rd = app.rounds_data or {}
    total = app.match_score
    for k in ("round_1", "round_2", "round_3", "round_4"):
        if k in rd:
            total += int(rd[k].get("score_delta", 0)) * 2
    return max(0, min(100, total))


def _round5_offer_or_reject(
    s: Session, *, app: JobApplication, student_id: int,
) -> RoundResult:
    """Avgör om eleven får erbjudande eller avslag baserat på final_score.

    Sannolikheter:
      score >= 80: 95% offer
      score 60-79: 70% offer
      score 40-59: 40% offer
      score < 40:  10% offer
    """
    score = _compute_final_score(app)
    app.final_score = score
    rng = random.Random(f"offer|{app.id}|{score}")

    if score >= 80:
        p = 0.95
    elif score >= 60:
        p = 0.70
    elif score >= 40:
        p = 0.40
    else:
        p = 0.10

    if rng.random() < p:
        # Erbjudande
        yrke = YRKE_BY_KEY.get(app.yrke_key)
        if yrke is None:
            base = 30000
        else:
            # Lön baserad på final_score: median ± 30%
            base = yrke.monthly_gross_median
            offset_pct = (score - 50) / 100 * 0.3
            base = int(base * (1 + offset_pct))
            base = max(yrke.monthly_gross_min, min(yrke.monthly_gross_max, base))
        app.monthly_gross_offered = base
        app.status = "offer_pending"
        feedback = (
            f"**Rond 5 · Erbjudande från {app.employer_name}**\n\n"
            f"Mats: \"Bra jobbat! De erbjuder dig **{base:,} kr/mån** "
            f"brutto.\"\n\n".replace(",", " ")
            + f"Final score: **{score}/100**.\n"
            + "Du kan acceptera, motbjuda med högre lön, eller tacka nej."
        )
        return RoundResult(
            round_n=5, score_delta=0, feedback_md=feedback,
            pentagon_delta={}, advanced_to=0,
            final_status="offer_pending",
        )

    # Avslag · pedagogisk feedback baserat på vad som gick fel + tydlig
    # wellbeing-impact (avslag KÄNNS — eleven ska känna det också).
    app.status = "rejected"
    app.completed_on = date.today()
    feedback = (
        f"**Rond 5 · Avslag från {app.employer_name}**\n\n"
        f"Tyvärr fick du inte jobbet den här gången. "
        f"Final score blev **{score}/100**.\n\n"
        f"### Det här hade du kunnat göra annorlunda:\n\n"
    )
    rd = app.rounds_data or {}
    learnings = []
    r1 = rd.get("round_1", {})
    if r1.get("ai_score", 25) < 14:
        learnings.append(
            "**Personligt brev** behövde vara mer specifikt mot företaget. "
            "Generiska brev sticker inte ut."
        )
    r2 = rd.get("round_2", {})
    if r2.get("ai_score", 15) < 9:
        learnings.append(
            "**Telefonintervjun** kunde ha varit djupare. Konkreta "
            "exempel slår alltid generella floskler."
        )
    if r2.get("tone") == "ansprakvol":
        learnings.append(
            "Mjukare ton i tidiga intervjuer kan ge bättre resultat — "
            "anspråksfullhet tolkas ofta som arrogans."
        )
    r3 = rd.get("round_3", {})
    if r3.get("ai_score", 15) < 9:
        learnings.append(
            "**Case-uppgiften** behövde mer struktur. Visa hur du tänker "
            "steg-för-steg, inte bara slutsatsen."
        )
    r4 = rd.get("round_4", {})
    if r4.get("ai_score", 15) < 9 or r4.get("research_words", 0) < 50:
        learnings.append(
            "**Research om företaget** var för tunn. Läs deras hemsida, "
            "senaste nyheter och konkurrenter inför slutintervjun."
        )
    if not learnings:
        learnings.append(
            "Allt såg bra ut. Det här jobbet hade mycket konkurrens — "
            "du var nära. Sök fler liknande jobb."
        )
    for it in learnings:
        feedback += f"- {it}\n"

    feedback += (
        f"\n### Effekt på din wellbeing\n\n"
        f"Avslag känns. Trygghet och självkänsla sänks. "
        f"Du kan söka nya jobb direkt — eller fundera ett par dagar."
    )

    # Tydlig wellbeing-impact vid avslag (verkligheten)
    pentagon = {
        "safety": -3,    # trygghet/självkänsla
        "halsa": -2,     # avslag är stress
        "relation": -1,  # man behöver berätta för någon
        "ekonomi": -1,   # om man räknat med jobbet
    }
    return RoundResult(
        round_n=5, score_delta=0, feedback_md=feedback,
        pentagon_delta=pentagon, advanced_to=0,
        final_status="rejected",
    )


# === Dispatcher ===


def submit_round_response(
    s: Session,
    *,
    student_id: int,
    application_id: int,
    payload: dict,
) -> RoundResult:
    """Dispatcha till rätt rond-handler baserat på app.current_round."""
    app = s.get(JobApplication, application_id)
    if app is None:
        raise ValueError(f"Application {application_id} hittades inte")
    if app.status not in ("round_1", "round_2", "round_3", "round_4"):
        raise ValueError(
            f"Application {application_id} är inte i en aktiv rond "
            f"(status={app.status})"
        )

    handlers = {
        1: lambda: _round1(s, app=app, student_id=student_id,
                           inp=Round1Input(**payload)),
        2: lambda: _round2(s, app=app, student_id=student_id,
                           inp=Round2Input(**payload)),
        3: lambda: _round3(s, app=app, student_id=student_id,
                           inp=Round3Input(**payload)),
        4: lambda: _round4(s, app=app, student_id=student_id,
                           inp=Round4Input(**payload)),
    }
    handler = handlers.get(app.current_round)
    if handler is None:
        raise ValueError(f"Okänd rond {app.current_round}")

    result = handler()

    # Applicera pentagon
    for axis, delta in result.pentagon_delta.items():
        try:
            apply_pentagon_delta(
                student_id, axis=axis, requested_delta=delta,
                reason_kind="decision", reason_id=app.id,
                reason_table="job_applications",
                explanation=f"intervju rond {result.round_n} · {app.employer_name}",
            )
        except Exception:
            log.exception("pentagon delta failed for round %d", result.round_n)

    # Om vi nådde rond 5 → kör direkt
    if result.advanced_to == 5:
        offer_result = _round5_offer_or_reject(s, app=app, student_id=student_id)
        for axis, delta in offer_result.pentagon_delta.items():
            try:
                apply_pentagon_delta(
                    student_id, axis=axis, requested_delta=delta,
                    reason_kind="decision", reason_id=app.id,
                    reason_table="job_applications",
                    explanation=f"intervju rond 5 · {app.employer_name}",
                )
            except Exception:
                log.exception("pentagon delta failed for round 5")
        s.flush()
        return offer_result

    s.flush()
    return result


def accept_offer(
    s: Session,
    *,
    student_id: int,
    application_id: int,
) -> JobApplication:
    """Eleven tar jobbet. Uppdaterar StudentProfile.profession + lön
    + pentagon-delta baserat på lön-skillnad mot tidigare."""
    app = s.get(JobApplication, application_id)
    if app is None or app.status != "offer_pending":
        raise ValueError("Inget pending erbjudande att acceptera.")
    app.status = "accepted"
    app.completed_on = date.today()
    s.flush()

    # === Uppdatera StudentProfile · KRITISKT ===
    # Innan denna fanns triggades pentagon-delta men profile.gross_salary
    # uppdaterades aldrig. Resultat: tick_month nästa månad använde
    # gammal lön och eleven såg "accepted" utan löneökning.
    salary_delta_pct = 0.0
    try:
        from ...school.engines import master_session as _ms
        from ...school.models import StudentProfile as _SP
        from ...school.tax import compute_net_salary as _net
        with _ms() as mdb:
            sp = (
                mdb.query(_SP)
                .filter(_SP.student_id == student_id)
                .first()
            )
            if sp is not None and app.monthly_gross_offered:
                old_gross = int(sp.gross_salary_monthly or 0)
                new_gross = int(app.monthly_gross_offered)
                if old_gross > 0:
                    salary_delta_pct = (
                        (new_gross - old_gross) / old_gross * 100.0
                    )
                sp.profession = app.yrke_display
                if hasattr(sp, "profession_key"):
                    sp.profession_key = app.yrke_key
                sp.gross_salary_monthly = new_gross
                tax = _net(new_gross)
                sp.net_salary_monthly = tax.net_monthly
                sp.tax_rate_effective = tax.effective_rate
                sp.employer = app.employer_name
                mdb.commit()
    except Exception:
        log.exception(
            "accept_offer: StudentProfile sync failed för %s", student_id,
        )

    # Pentagon: +3 safety (säkrad inkomst). Economy-delta proportionerlig
    # mot löneökning (max +5 vid stor höjning, min -2 vid sänkning).
    deltas = {"safety": +3}
    if salary_delta_pct >= 15:
        deltas["economy"] = +5
    elif salary_delta_pct >= 5:
        deltas["economy"] = +3
    elif salary_delta_pct >= 0:
        deltas["economy"] = +1
    elif salary_delta_pct >= -10:
        deltas["economy"] = -1
    else:
        deltas["economy"] = -2
    explain_extra = (
        f" · lön {salary_delta_pct:+.0f} %"
        if salary_delta_pct != 0 else ""
    )
    for axis, delta in deltas.items():
        try:
            apply_pentagon_delta(
                student_id, axis=axis, requested_delta=delta,
                reason_kind="decision", reason_id=app.id,
                reason_table="job_applications",
                explanation=(
                    f"accepterade jobb · {app.employer_name}"
                    f"{explain_extra}"
                ),
            )
        except Exception:
            log.exception("pentagon delta failed for accept_offer")
    return app


def decline_offer(
    s: Session,
    *,
    student_id: int,
    application_id: int,
) -> JobApplication:
    """Eleven tackar nej. Pentagon: ingen större effekt."""
    app = s.get(JobApplication, application_id)
    if app is None or app.status != "offer_pending":
        raise ValueError("Inget pending erbjudande att neka.")
    app.status = "declined"
    app.completed_on = date.today()
    s.flush()
    return app


def abandon_application(
    s: Session,
    *,
    student_id: int,
    application_id: int,
) -> JobApplication:
    """Eleven avbryter mitt i flödet. Pentagon: -1 safety, -1 health."""
    app = s.get(JobApplication, application_id)
    if app is None:
        raise ValueError("Application saknas.")
    if app.status not in ("round_1", "round_2", "round_3", "round_4", "round_5"):
        raise ValueError("Application är redan avslutad.")
    app.status = "abandoned"
    app.completed_on = date.today()
    s.flush()

    for axis, delta in (("safety", -1), ("health", -1)):
        try:
            apply_pentagon_delta(
                student_id, axis=axis, requested_delta=delta,
                reason_kind="decision", reason_id=app.id,
                reason_table="job_applications",
                explanation=f"avbröt ansökan · {app.employer_name}",
            )
        except Exception:
            log.exception("pentagon delta failed for abandon")
    return app
