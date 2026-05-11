"""Skatteverkets tidsfönster · 3-fas-modell per inkomstår.

Spelet är ankrat på 2026-01-01 (1 real-timme = 1 spel-vecka). Skatteverket
hanterar inkomstår Y under FÖLJANDE år (Y+1) enligt riktiga kalendern:

    Jan-1 mars (Y+1)    · OFF-SEASON      · aktören låst
    2-16 mars (Y+1)     · GRANSKA         · läs-läge, inte lämna in
    17 mars-4 maj (Y+1) · INLÄMNA         · submit aktiverad
    5 maj (Y+1) framåt  · STÄNGD          · efter deadline · förseningsavgift

Plus 3 utbetalnings-/inbetalnings-händelser som inte ändrar fönstret:
    12 mars (Y+1)       · Kvarskatt-deadline från slutskattebesked (Y-1)
    7-10 april (Y+1)    · Återbäringsvåg 1 (för submit ≤ 31 mars)
    9-12 juni (Y+1)     · Återbäringsvåg 2 (för submit 1 apr-4 maj)

Pedagogisk poäng: Skatteverket är inte en evigt öppen aktör som eleven
kan klicka på när som helst. Den har ETT fönster per år, och den
fasta deadlinen blir kännbar genom att aktör-knappen i hubben rentav
är låst innan 2 mars.

Implementation: alla `/v2/skatten/*`-endpoints kallar `gate_for_phase()`
som sätter rätt HTTPStatus + felmeddelande. Frontend hämtar `GET
/v2/skatten/window` för att rendera locked-view eller granska-banner.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal, Optional


Phase = Literal[
    "off_season",   # jan-1 mars Y+1 · låst
    "granska",      # 2-16 mars Y+1 · läs-läge
    "inlamna",      # 17 mars-4 maj Y+1 · submit aktiverad
    "stangd",       # 5 maj framåt · efter deadline
]


@dataclass
class WindowState:
    """Tillstånd för Skatteverkets fönster vid en specifik spel-tids-punkt.

    `tax_year` = vilket inkomstår eleven kan deklarera för just nu
    (Y-1 där Y är spel-året). Under off-season (jan-mars) av Y+1 är
    tax_year fortfarande Y-1 men `phase = off_season` → låst.

    `submit_open` är true bara under inlamna-fasen.
    `can_read` är true under granska + inlamna (eleven får titta).
    """
    phase: Phase
    tax_year: int                 # år som ska deklareras (Y - 1)
    can_read: bool                # får eleven titta?
    submit_open: bool             # får eleven trycka lämna in?
    opens_on: Optional[date]      # nästa fas-byte (None om sista fas)
    closes_on: Optional[date]     # när nuvarande fas slutar
    today_game: date              # for debug/UI
    description: str              # pedagogisk klartext


# Hårda datum för SKV-fönstret per inkomstår Y (deklaration sker i Y+1)
SKV_GRANSKA_OPEN_MONTH_DAY = (3, 2)    # 2 mars
SKV_INLAMNA_OPEN_MONTH_DAY = (3, 17)   # 17 mars
SKV_DIGITAL_DEADLINE = (3, 31)         # 31 mars · våg 1
SKV_INLAMNA_CLOSE_MONTH_DAY = (5, 4)   # 4 maj
SKV_KVARSKATT_DUE = (3, 12)            # 12 mars
SKV_REFUND_WAVE_1 = (4, 7)             # 7 april
SKV_REFUND_WAVE_2 = (6, 9)             # 9 juni
SKV_LATE_FEE_KR = 1_250                # 1 250 kr första gången


def compute_window(today_game: date) -> WindowState:
    """Avgör fas + nästa fas-datum från ett spel-datum.

    Eleven kan deklarera FÖREGÅENDE års inkomst under jan-maj av
    INNEVARANDE år. T.ex. 2027-03-17 → deklaration för 2026.

    Algoritm:
      - tax_year = today_game.year - 1
      - om today_game.year < ANCHOR_YEAR + 1: ingen deklaration än
        (off_season för Y=ANCHOR_YEAR, men eleven har inte hunnit fylla
        ett helt skatteår än så vi visar 'inväntar')
      - inom innevarande år: jämför mot mm/dd för faserna
    """
    y = today_game.year
    tax_year = y - 1

    def _d(mm: int, dd: int) -> date:
        return date(y, mm, dd)

    granska_open = _d(*SKV_GRANSKA_OPEN_MONTH_DAY)
    inlamna_open = _d(*SKV_INLAMNA_OPEN_MONTH_DAY)
    inlamna_close = _d(*SKV_INLAMNA_CLOSE_MONTH_DAY)

    if today_game < granska_open:
        # Off-season tills 2 mars
        return WindowState(
            phase="off_season",
            tax_year=tax_year,
            can_read=False,
            submit_open=False,
            opens_on=granska_open,
            closes_on=granska_open,
            today_game=today_game,
            description=(
                f"Skatteverket öppnar 2 mars för deklaration av {tax_year}. "
                "Använd tiden till att samla lönespecs, ROT-/RUT-kvitton "
                "och ev. reseräkningar."
            ),
        )
    if today_game < inlamna_open:
        # 2-16 mars · granska-läge
        return WindowState(
            phase="granska",
            tax_year=tax_year,
            can_read=True,
            submit_open=False,
            opens_on=inlamna_open,
            closes_on=inlamna_open,
            today_game=today_game,
            description=(
                f"Deklarationen för {tax_year} ligger i digital brevlåda. "
                "Granska förtryckta uppgifter, lägg till avdrag — själva "
                "inlämningen öppnar 17 mars."
            ),
        )
    if today_game <= inlamna_close:
        # 17 mars - 4 maj · inlämnings-fönster
        return WindowState(
            phase="inlamna",
            tax_year=tax_year,
            can_read=True,
            submit_open=True,
            opens_on=None,
            closes_on=inlamna_close,
            today_game=today_game,
            description=(
                f"Inlämning öppen till 4 maj. Skicka in före 31 mars för "
                f"återbäring i april (våg 1), annars våg 2 (9-12 juni)."
            ),
        )
    # Efter 4 maj · stängd
    # Nästa öppning = 2 mars nästa år
    next_granska = date(y + 1, *SKV_GRANSKA_OPEN_MONTH_DAY)
    return WindowState(
        phase="stangd",
        tax_year=tax_year,
        can_read=True,  # eleven får läsa gamla deklarationer
        submit_open=False,
        opens_on=next_granska,
        closes_on=None,
        today_game=today_game,
        description=(
            f"Deadline 4 maj har passerats. Eventuell inlämning för "
            f"{tax_year} ger förseningsavgift {SKV_LATE_FEE_KR} kr. "
            f"Skatteverket öppnar igen 2 mars {y + 1} för deklaration "
            f"av {y}."
        ),
    )


def current_window_for_student(student_id: int) -> WindowState:
    """Hjälpare som slår upp current_game_date för eleven och delegerar."""
    from ..business.game_clock import current_game_date_for_student
    return compute_window(current_game_date_for_student(student_id))
