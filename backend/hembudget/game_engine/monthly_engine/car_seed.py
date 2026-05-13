"""Bil-seed för scope-DB · auto-skapar InsurancePolicy, Loan och
välkomstmail när eleven har bil.

Anropas en gång vid första tick (efter ensure_scope_accounts).
Idempotent · skippar om InsurancePolicy(kind='bilforsakring') redan
finns för scope.

Pedagogisk poäng: eleven "ärver" bilförsäkring och ev. billån direkt
vid karaktärsskapande (matchar verkligheten — du säger inte upp
försäkringen på din befintliga bil). Bil-events och drivmedel
hanteras separat i tick-engine.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from ...db.models import (
    InsurancePolicy, Loan, MailItem,
)


log = logging.getLogger(__name__)


def seed_car_for_scope(
    s: Session,
    *,
    student_id: int,
    today_game: date,
) -> dict:
    """Säkerställ att en bilägare har InsurancePolicy + ev. CSN/lån +
    välkomstmail. Idempotent · skippar om policy redan finns.

    Returnerar en dict med vad som skapades för logging/tester.
    """
    # Hämta bil-data från StudentProfile (master DB)
    from ...school.engines import master_session
    from ...school.models import StudentProfile

    with master_session() as ms:
        prof = (
            ms.query(StudentProfile)
            .filter(StudentProfile.student_id == student_id)
            .first()
        )
        if prof is None:
            return {"skipped": "no_profile"}
        if not bool(getattr(prof, "has_car", False)):
            return {"skipped": "no_car"}

        # Snapshot fälten medan session är öppen
        car_data = {
            "brand": getattr(prof, "car_brand", None),
            "model": getattr(prof, "car_model", None),
            "year": getattr(prof, "car_year", None),
            "license_plate": getattr(prof, "car_license_plate", None),
            "fuel_type": getattr(prof, "car_fuel_type", None),
            "market_value": getattr(prof, "car_market_value_sek", None),
            "insurance_provider": getattr(
                prof, "car_insurance_provider", None,
            ),
            "insurance_premium": getattr(
                prof, "car_insurance_premium_monthly", None,
            ) or 0,
            "financing": getattr(prof, "car_financing", None),
            "loan_principal": getattr(prof, "car_loan_principal", None) or 0,
            "loan_monthly": getattr(
                prof, "car_loan_monthly_payment", None,
            ) or 0,
            "leasing_monthly": getattr(prof, "car_leasing_monthly", None) or 0,
        }

    created = {
        "insurance": False,
        "loan": False,
        "welcome_mail": False,
        "registration_mail": False,
    }

    label = f"{car_data['brand']} {car_data['model']} {car_data['year']}".strip()
    plate = car_data["license_plate"] or "—"

    # === 1. InsurancePolicy ===
    existing_pol = (
        s.query(InsurancePolicy)
        .filter(
            InsurancePolicy.kind == "bilforsakring",
            InsurancePolicy.status == "active",
        )
        .first()
    )
    if existing_pol is None and car_data["insurance_premium"] > 0:
        s.add(InsurancePolicy(
            provider=car_data["insurance_provider"] or "Folksam",
            name=f"Helförsäkring · {label}",
            kind="bilforsakring",
            premium_monthly=Decimal(str(car_data["insurance_premium"])),
            coverage_amount=(
                Decimal(str(car_data["market_value"]))
                if car_data["market_value"] else None
            ),
            deductible=Decimal("1500"),  # standard självrisk vid skada
            autogiro=True,
            status="active",
            started_on=today_game,
            notes=(
                f"Bil: {label} · regnr {plate} · "
                f"drivmedel {car_data['fuel_type']}"
            ),
        ))
        created["insurance"] = True

    # === 2. Lån (om finansierat med billån) ===
    if car_data["financing"] == "loan" and car_data["loan_principal"] > 0:
        # Skapa bara om det inte redan finns ett bil-lån.
        existing_loan = (
            s.query(Loan)
            .filter(Loan.name.like(f"Billån%{label}%"))
            .first()
        )
        if existing_loan is None:
            loan = Loan(
                name=f"Billån · {label}",
                lender="Spelbanken Bil",
                principal_amount=Decimal(str(car_data["loan_principal"])),
                start_date=today_game,
                interest_rate=0.06,
                binding_type="rörlig",
                amortization_monthly=Decimal(str(
                    int(car_data["loan_principal"] / 60)
                )),
                notes=(
                    f"Finansiering av {label}. 5 år · 6 % ränta · "
                    f"månadsbetalning ~{car_data['loan_monthly']} kr "
                    "(annuitet)"
                ),
                active=True,
                loan_kind="car",
            )
            s.add(loan)
            s.flush()
            # Skapa LoanScheduleEntry för hela löptiden (60 mån). Vid
            # varje månadstick genereras en autogiro-Transaction för
            # billån-avin (se fixed_expenses.py) som matchas mot dessa
            # schema-rader → LoanPayment skapas → outstanding_balance
            # sjunker. Utan schema skulle matcher bara matcha på text
            # och billån-saldot stannade konstant i huvudboken.
            from ...db.models import LoanScheduleEntry
            principal = Decimal(str(car_data["loan_principal"]))
            monthly_total = Decimal(str(car_data["loan_monthly"]))
            amort_per_month = Decimal(str(int(car_data["loan_principal"] / 60)))
            day_of_month = min(today_game.day, 28)
            for i in range(1, 61):  # 60 månader = 5 år
                total_months = today_game.month + i
                year_n = today_game.year + (total_months - 1) // 12
                month_n = (total_months - 1) % 12 + 1
                try:
                    due = date(year_n, month_n, day_of_month)
                except ValueError:
                    continue
                interest_amt = (monthly_total - amort_per_month).quantize(
                    Decimal("0.01"),
                )
                if interest_amt > 0:
                    s.add(LoanScheduleEntry(
                        loan_id=loan.id,
                        due_date=due,
                        amount=interest_amt,
                        payment_type="interest",
                    ))
                s.add(LoanScheduleEntry(
                    loan_id=loan.id,
                    due_date=due,
                    amount=amort_per_month,
                    payment_type="amortization",
                ))
            created["loan"] = True
            created["schedule_entries"] = 60

    # === 3. Välkomstmail från försäkringsbolaget ===
    welcome_subj = f"Välkommen som kund · {car_data['insurance_provider']}"
    existing_welcome = (
        s.query(MailItem)
        .filter(MailItem.subject == welcome_subj)
        .first()
    )
    if existing_welcome is None and car_data["insurance_premium"] > 0:
        s.add(MailItem(
            sender=f"{car_data['insurance_provider']}",
            sender_short=car_data['insurance_provider'][:3].upper(),
            sender_kind="financial",
            sender_meta=f"Bilförsäkring · {plate}",
            mail_type="info",
            subject=welcome_subj,
            body_meta=f"{label} · {car_data['insurance_premium']} kr/mån",
            body=(
                f"Hej! Vi har registrerat din helförsäkring för "
                f"{label} (regnr {plate}).\n\n"
                f"• Premie: {car_data['insurance_premium']} kr/mån (autogiro)\n"
                f"• Självrisk vid skada: 1 500 kr\n"
                f"• Försäkringsbelopp: {car_data['market_value']} kr "
                "(marknadsvärde)\n\n"
                "Tänk på att försäkringen INTE täcker vanligt slitage "
                "(däckbyten, service, oljebyten). Du får separata fakturor "
                "för dessa kostnader när de uppstår.\n\n"
                f"Vänliga hälsningar,\n"
                f"{car_data['insurance_provider']}"
            ),
            amount=None,
            due_date=None,
            status="unhandled",
            released_at=None,
        ))
        created["welcome_mail"] = True

    # === 4. Registrerings-/leasingmail om relevant ===
    if car_data["financing"] == "leasing":
        leas_subj = f"Leasingavtal · {label}"
        existing_leas = (
            s.query(MailItem).filter(MailItem.subject == leas_subj).first()
        )
        if existing_leas is None:
            s.add(MailItem(
                sender="Spelbanken Bil-leasing",
                sender_short="SBL",
                sender_kind="financial",
                sender_meta=f"Leasing · {plate}",
                mail_type="info",
                subject=leas_subj,
                body_meta=(
                    f"{car_data['leasing_monthly']} kr/mån · 36 mån"
                ),
                body=(
                    f"Ditt leasingavtal för {label} är aktivt.\n\n"
                    f"• Månadsavgift: {car_data['leasing_monthly']} kr\n"
                    f"• Bindningstid: 36 månader\n"
                    f"• Slutdatum: {today_game + timedelta(days=36*30)}\n\n"
                    "Leasing innebär att du INTE äger bilen — vid slutet "
                    "lämnar du tillbaka den. Service ingår, men du betalar "
                    "drivmedel, däck och försäkring själv.\n\n"
                    "Hälsningar,\nSpelbanken Bil-leasing"
                ),
                amount=None,
                due_date=None,
                status="unhandled",
                released_at=None,
            ))
            created["registration_mail"] = True

    s.flush()
    return created
