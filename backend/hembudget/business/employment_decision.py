"""Maria-säg-upp-prompt · trigger när företaget tar för många timmar.

Pedagogisk princip: när elevens företag växer (≥ 25 h/v under 4 v
i rad) blir det tydligt att hen inte längre kan klara båda. Maria
(chefen) skickar ett mail med 3 val:

1. Behåll heltid · fritid-axel −10 (kan inte hänga med på allt)
2. Gå ner till 50% (20 h/v) · lön /2 men 20 h ledigt för biz
3. Säg upp helt · lön = 0 från månad +3, fokus 100% biz

Konsekvens:
- Säger upp och biz krasar inom 3 mån → privat-pentagon-ekonomi rasar
- Behåller heltid och biz växer → konstant burnout-stress
- Deltid är safe-middle, men halvering av lön slår hårt på fast utgifter

Pedagogiken: eleven måste väga risk mot kapital — verklighetsnära.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


EmploymentChoice = Literal[
    "keep_fulltime",      # behåll 40h
    "go_parttime",        # 20h, lön /2
    "resign",             # 0h, ingen lön efter månad +3
]


@dataclass
class EmploymentDecisionTrigger:
    should_trigger: bool
    weekly_hours_business: int
    consecutive_overload_weeks: int
    reason: str
    options: list[str]


def evaluate_employment_decision(
    *,
    weekly_hours_business: int,
    consecutive_overload_weeks: int,
    employment_status: str,
) -> EmploymentDecisionTrigger:
    """Avgör om Maria ska skicka säg-upp-prompten denna vecka.

    Trigger-villkor:
    - employment_status == "employed" (annars redan beslutat)
    - weekly_hours_business >= 25 i 4 veckor i rad

    Resterande logik (mail-skick, mode-toggle) ligger i route-koden.
    """
    if employment_status != "employed":
        return EmploymentDecisionTrigger(
            should_trigger=False,
            weekly_hours_business=weekly_hours_business,
            consecutive_overload_weeks=consecutive_overload_weeks,
            reason="Redan beslutat (deltid eller uppsagd).",
            options=[],
        )

    if weekly_hours_business < 25:
        return EmploymentDecisionTrigger(
            should_trigger=False,
            weekly_hours_business=weekly_hours_business,
            consecutive_overload_weeks=consecutive_overload_weeks,
            reason=(
                f"Företaget tar bara {weekly_hours_business} h/v · "
                "OK att behålla heltid."
            ),
            options=[],
        )

    if consecutive_overload_weeks < 4:
        return EmploymentDecisionTrigger(
            should_trigger=False,
            weekly_hours_business=weekly_hours_business,
            consecutive_overload_weeks=consecutive_overload_weeks,
            reason=(
                f"{consecutive_overload_weeks} v överbelastad · vänta "
                "till 4+ innan Maria skickar prompt."
            ),
            options=[],
        )

    return EmploymentDecisionTrigger(
        should_trigger=True,
        weekly_hours_business=weekly_hours_business,
        consecutive_overload_weeks=consecutive_overload_weeks,
        reason=(
            f"{weekly_hours_business} h/v företag i {consecutive_overload_weeks} "
            "veckor · Maria märker att leveranserna sjunker."
        ),
        options=["keep_fulltime", "go_parttime", "resign"],
    )


def maria_prompt_text(
    *,
    student_first_name: str,
    weekly_hours_business: int,
    weeks: int,
) -> tuple[str, str, str]:
    """Bygg subject + body_meta + body till Maria-mailet.

    Returnerar (subject, body_meta, body) som matchar MailItem-fälten.
    """
    subject = f"Hej {student_first_name} · vi behöver prata om din arbetstid"
    body_meta = (
        f"Du jobbar ~{weekly_hours_business} h/v utöver heltidstjänsten i "
        f"{weeks} veckor i rad. Maria föreslår tre val."
    )
    body = (
        f"Hej {student_first_name},\n\n"
        f"Jag har märkt att du har varit … upptagen … på senaste tid. "
        f"Faktum är att jag förstår att du driver något eget vid sidan av — "
        f"och baserat på dina veckodata pratar vi om ungefär {weekly_hours_business} "
        f"timmar i veckan i {weeks} veckor i rad utöver din ordinarie tjänst hos oss.\n\n"
        f"Det är inte hållbart i längden. Du har levererat på halvfart de "
        f"senaste sprintarna. Innan det här blir ett HR-ärende vill jag att "
        f"vi pratar igenom vad du vill göra:\n\n"
        f"=== DINA VAL ===\n\n"
        f"1. BEHÅLL HELTID (40 h/v hos oss)\n"
        f"   · Lön oförändrad\n"
        f"   · Du fortsätter pressa båda spåren\n"
        f"   · Pentagon · fritid och hälsa drabbas (−5 till −10)\n\n"
        f"2. GÅ NER TILL 50% (20 h/v hos oss)\n"
        f"   · Lön halveras\n"
        f"   · 20 h ledigt för företaget\n"
        f"   · Riskerat: räcker biz för fasta utgifter?\n\n"
        f"3. SÄG UPP\n"
        f"   · Du blir egenföretagare på heltid\n"
        f"   · Lön slutar månad +3 (uppsägningstid)\n"
        f"   · Pentagon · safety-axeln rasar tills biz kompenserar\n"
        f"   · Pedagogiskt: testa kassaflöde-förmågan på riktigt\n\n"
        f"Det finns inget rätt svar. Det beror på hur stabilt företaget "
        f"är just nu och hur risk-mottaglig du är. Tänk över det och svara "
        f"i appen via Hubben → 'Beslut'.\n\n"
        f"Hälsningar,\n"
        f"Maria · din chef"
    )
    return subject, body_meta, body


def apply_employment_decision(
    profile,
    choice: EmploymentChoice,
) -> dict:
    """Applicera elevens val på StudentProfile.

    Returnerar en summary-dict som UI kan rendera ('Du valde X. Det
    betyder Y.').
    """
    if choice == "keep_fulltime":
        profile.weekly_hours_employed = 40
        profile.employment_status = "employed"
        # Reset overload-counter så Maria inte triggas igen direkt
        profile.consecutive_overload_weeks = 0
        return {
            "choice": "keep_fulltime",
            "summary": (
                "Du behåller heltid. Lön oförändrad. Räkna med att "
                "fritid- och hälsa-axlarna pressas så länge du driver "
                "biz parallellt."
            ),
            "weekly_hours_employed": 40,
            "salary_change_pct": 0,
        }

    if choice == "go_parttime":
        profile.weekly_hours_employed = 20
        profile.employment_status = "employed"
        profile.consecutive_overload_weeks = 0
        # Halvera bruttolönen
        profile.gross_salary_monthly = int(profile.gross_salary_monthly * 0.5)
        profile.net_salary_monthly = int(profile.net_salary_monthly * 0.5)
        return {
            "choice": "go_parttime",
            "summary": (
                "Du går ner till 50%. Lönen halveras från och med "
                "nästa månadsspec. 20 h/v ledigt för företaget."
            ),
            "weekly_hours_employed": 20,
            "salary_change_pct": -50,
        }

    if choice == "resign":
        # Lön kvar i 3 månader (uppsägningstid)
        profile.employment_status = "freelance_only"
        # Vi nollar inte hours direkt — generation-flödet använder
        # employment_status==freelance_only för att stoppa lönespec
        # från månad +3.
        profile.consecutive_overload_weeks = 0
        return {
            "choice": "resign",
            "summary": (
                "Du säger upp dig. Lön kommer i 3 månader till "
                "(uppsägningstid), sedan 0. Företaget måste klara "
                "alla privata kostnader därefter."
            ),
            "weekly_hours_employed": 40,    # under uppsägningstid
            "salary_change_pct": 0,
            "salary_ends_in_months": 3,
        }

    raise ValueError(f"Okänt val: {choice}")
