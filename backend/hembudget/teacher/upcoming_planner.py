"""Planerar UpcomingTransactions för en framtida månad baserat på
elevens profil. Detta är kärnan i Rolling N+1-arkitekturen:

När ``create_batch_for_student(student, "2026-11")`` körs vill vi att
elevens bank ska visa fakturor som FÖRFALLER under DECEMBER —
HYRA 1 dec, EL 1 dec, TRE 7 dec osv. Eleven har då en hel månad
att signera dem i banken med EkonomilabbetID.

Tidigare skapades upcomings för CURRENT month (samma som batchen
genererades för), vilket gjorde att kontoutdraget redan visade dem
som "dragna" — eleven hade ingen agency över när/om de ska betalas.
Det var fel mot verkligheten där bankens kontoutdrag visar HISTORIK,
inte framtid.

Modulen är data-driven från ``StudentProfile``: housing_type,
housing_monthly, has_mortgage, has_car_loan, has_student_loan etc.
Slumptalen seedas deterministiskt på (student_id, year_month) så
samma elev + samma månad alltid ger samma fakturor.
"""
from __future__ import annotations

import random
from calendar import monthrange
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from ..db.models import Account, UpcomingTransaction
from ..school.models import Student, StudentProfile

__all__ = ["plan_upcomings_for_month", "next_year_month"]


def next_year_month(year_month: str) -> str:
    """Returnera year_month + 1 månad. '2026-11' → '2026-12'."""
    year, month = map(int, year_month.split("-"))
    if month == 12:
        return f"{year + 1:04d}-01"
    return f"{year:04d}-{month + 1:02d}"


def plan_upcomings_for_month(
    s: Session,
    student: Student,
    profile: StudentProfile,
    year_month: str,
    debit_account: Account,
    owner: str,
    *,
    seed_suffix: str = "rolling_v1",
) -> int:
    """Skapa UpcomingTransactions för fakturor som ska FÖRFALLA under
    ``year_month`` (typiskt nästa månad relativt batchen som genererar
    dem). Idempotent — skapar inga duplikat om upcomings redan finns
    för månaden.

    Returnerar antal nya upcomings som skapades.

    Logiken speglar :func:`scenario._build_recurring_bills` men vi
    läser från profilen direkt istället för att bygga via scenario,
    eftersom upcomings är PROSPEKTIVA — de behöver inte matcha en
    specifik scenario-månad.
    """
    year, month = map(int, year_month.split("-"))
    last_day = monthrange(year, month)[1]
    seed = abs(hash((student.id, year_month, seed_suffix))) & 0xFFFFFFFF
    rng = random.Random(seed)
    # id_rng styr deterministiska "varumärken" (Vattenfall vs Fortum osv)
    id_rng = random.Random(
        abs(hash((student.id, "vendor_lock"))) & 0xFFFFFFFF,
    )

    created = 0

    def _add_if_missing(
        kind: str,
        name: str,
        amount: Decimal,
        expected: date,
        autogiro: bool = True,
    ) -> bool:
        # Idempotens — finns det redan en upcoming med samma (name,
        # expected_date, amount) skippa.
        existing = (
            s.query(UpcomingTransaction)
            .filter(
                UpcomingTransaction.name == name,
                UpcomingTransaction.expected_date == expected,
                UpcomingTransaction.amount == amount,
            )
            .first()
        )
        if existing is not None:
            return False
        s.add(UpcomingTransaction(
            kind=kind,
            name=name,
            amount=amount,
            expected_date=expected,
            recurring_monthly=True,
            source="scenario",
            debit_account_id=debit_account.id,
            debit_date=expected,
            autogiro=autogiro,
            owner=owner,
        ))
        return True

    # ─── Boende ────────────────────────────────────────────────────
    rent_day = id_rng.choice([27, 28, 30])
    rent_date = date(year, month, min(rent_day, last_day))
    rent_label = {
        "hyresratt": "HYRA",
        "bostadsratt": "BRF AVGIFT",
        "villa": "DRIFT VILLA",
    }.get(profile.housing_type, "HYRA")
    if _add_if_missing(
        "bill",
        f"{rent_label} {profile.city.upper()}",
        Decimal(profile.housing_monthly),
        rent_date,
    ):
        created += 1

    # ─── El ─────────────────────────────────────────────────────────
    el_base = 600 if month in (12, 1, 2) else 350
    el_amount = rng.randint(el_base, el_base + 800)
    el_vendor = id_rng.choice([
        "VATTENFALL ELNAT", "FORTUM EL", "ELLEVIO ELNÄT", "TIBBER ENERGI",
    ])
    if _add_if_missing(
        "bill",
        el_vendor,
        Decimal(el_amount),
        date(year, month, min(15, last_day)),
    ):
        created += 1

    # ─── Bredband ──────────────────────────────────────────────────
    bredband_vendor = id_rng.choice([
        "TELIA BREDBAND", "BAHNHOF", "COM HEM", "TELE2",
    ])
    if _add_if_missing(
        "bill",
        bredband_vendor,
        Decimal(id_rng.randint(379, 549)),
        date(year, month, min(20, last_day)),
    ):
        created += 1

    # ─── Mobil ─────────────────────────────────────────────────────
    mobil_vendor = id_rng.choice([
        "TELENOR ABONNEMANG", "TELIA MOBIL", "TRE",
    ])
    if _add_if_missing(
        "bill",
        mobil_vendor,
        Decimal(id_rng.randint(199, 449)),
        date(year, month, min(20, last_day)),
    ):
        created += 1

    # ─── Hemförsäkring ─────────────────────────────────────────────
    forsakring_vendor = id_rng.choice([
        "IF FORSAKRING", "TRYGG HANSA", "FOLKSAM", "LANSFORSAKRINGAR",
    ])
    if _add_if_missing(
        "bill",
        forsakring_vendor,
        Decimal(id_rng.randint(120, 280)),
        date(year, month, min(5, last_day)),
    ):
        created += 1

    # ─── Studielån (CSN) ──────────────────────────────────────────
    if profile.has_student_loan:
        if _add_if_missing(
            "bill",
            "CSN",
            Decimal(id_rng.randint(900, 1900)),
            date(year, month, min(25, last_day)),
        ):
            created += 1

    # ─── Bilån ──────────────────────────────────────────────────────
    if profile.has_car_loan:
        if _add_if_missing(
            "bill",
            "BILLÅN",
            Decimal(id_rng.randint(2200, 3800)),
            date(year, month, min(28, last_day)),
        ):
            created += 1

    # ─── Bolån (amortering + ränta — räknas på profilens housing) ──
    if profile.has_mortgage:
        # Approximation: bolåneränta runt 30-50% av housing_monthly för
        # bostadsrätt med större lån. Studenter på pilot-stadiet har sällan
        # bolån, men fältet stödjer det.
        if _add_if_missing(
            "bill",
            "BOLÅN AMORTERING",
            Decimal(id_rng.randint(1500, 4500)),
            date(year, month, min(28, last_day)),
        ):
            created += 1

    # ─── Lön (income — dyker upp som "kommande lön") ─────────────
    # Vanligtvis 25:e i månaden. Skapas så elevens dashboard kan
    # visa "lön är på väg".
    if profile.net_salary_monthly:
        pay_day = min(25, last_day)
        pay_date = date(year, month, pay_day)
        existing = (
            s.query(UpcomingTransaction)
            .filter(
                UpcomingTransaction.kind == "income",
                UpcomingTransaction.expected_date == pay_date,
                UpcomingTransaction.amount == profile.net_salary_monthly,
            )
            .first()
        )
        if existing is None:
            s.add(UpcomingTransaction(
                kind="income",
                name=f"Lön {profile.employer}",
                amount=Decimal(profile.net_salary_monthly),
                expected_date=pay_date,
                recurring_monthly=True,
                source="scenario",
                debit_account_id=debit_account.id,
                debit_date=pay_date,
                owner=owner,
            ))
            created += 1

    s.flush()
    return created
