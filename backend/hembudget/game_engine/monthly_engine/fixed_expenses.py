"""Fas B · Fasta utgifter.

Spec: dev/game-motor/03-monthly-engine.md (Fas B).

Skapar 5-7 `MailItem` (kind="invoice") på olika dagar 1-10 i spelmånaden.
Staggered så att alla fakturor inte krockar med hyran dag 1 — eleven
ska kunna lära sig prioritera och planera likviditet över månaden.

Belopp matchas mot profilens stad + boendeval. SL-kort triggas bara
i städer med kollektivtrafik (jobbtäthet ≥ 1.0).
"""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from ...db.models import MailItem
from ..pools.stadspool import STAD_BY_KEY
from ..profile_generator.schema import GeneratedProfile


@dataclass(frozen=True)
class FixedBill:
    day: int
    sender: str
    sender_short: str
    sender_kind: str
    subject: str
    body_meta: str
    amount: int
    bankgiro: Optional[str] = None


def _ym_to_date(year_month: str, day: int) -> date:
    y, m = map(int, year_month.split("-"))
    # Klamp så att vi aldrig overflowar februari
    safe_day = min(day, 28)
    return date(y, m, safe_day)


def _bill_hash(student_scope: str, year_month: str, kind: str, day: int) -> str:
    raw = f"{student_scope}|{year_month}|fixed|{kind}|{day}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _seasonal_electricity(rng: random.Random, year_month: str) -> int:
    """Vinter-månader = dyrare el. Ljusare april-sept = billigare."""
    month = int(year_month.split("-")[1])
    if month in (12, 1, 2):
        return rng.randint(1100, 1800)
    if month in (3, 11):
        return rng.randint(800, 1300)
    if month in (4, 10):
        return rng.randint(600, 900)
    return rng.randint(400, 700)  # Sommar


def _build_bills(
    rng: random.Random,
    profile: GeneratedProfile,
    year_month: str,
) -> list[FixedBill]:
    """Bygg lista över fakturor för månaden — sorterade på dag."""
    city = STAD_BY_KEY.get(profile.city_key)
    bills: list[FixedBill] = []

    # Dag 1 · Boende (hyra eller bolåne+avgift)
    if profile.housing.type == "hyresratt":
        bills.append(FixedBill(
            day=1,
            sender="Hyresvärden",
            sender_short="HYR",
            sender_kind="land",
            subject=f"Hyresavi {year_month}",
            body_meta=(
                f"Hyresrätt {profile.housing.size_kvm} kvm · "
                f"{profile.city_display}"
            ),
            amount=profile.housing.monthly_cost,
            bankgiro="123-4567",
        ))
    else:
        # BR/villa: månadskostnad delas i två fakturor (avgift + bolån)
        if profile.housing.monthly_avgift:
            bills.append(FixedBill(
                day=1,
                sender="Bostadsrättsföreningen",
                sender_short="BRF",
                sender_kind="land",
                subject=f"Månadsavgift {year_month}",
                body_meta=f"Avgift för {profile.housing.size_kvm} kvm",
                amount=profile.housing.monthly_avgift,
                bankgiro="234-5678",
            ))
        if profile.housing.monthly_amortering or profile.housing.monthly_interest:
            loan_total = (
                (profile.housing.monthly_amortering or 0)
                + (profile.housing.monthly_interest or 0)
            )
            bills.append(FixedBill(
                day=2,
                sender="Spelbanken Bolån",
                sender_short="BANK",
                sender_kind="bank",
                subject=f"Bolån {year_month}",
                body_meta=(
                    f"Ränta + amortering · lån "
                    f"{profile.housing.loan_amount or 0:,} kr"
                ).replace(",", " "),
                amount=loan_total,
                bankgiro="345-6789",
            ))
        if profile.housing.monthly_drift:
            bills.append(FixedBill(
                day=4,
                sender="Driftkostnader villa",
                sender_short="VILLA",
                sender_kind="util",
                subject=f"Driftavi {year_month}",
                body_meta="Sopor, försäkring, snöröjning",
                amount=profile.housing.monthly_drift,
            ))

    # Dag 3 · El
    el_amount = _seasonal_electricity(rng, year_month)
    if city:
        el_amount = int(el_amount * city.cost_multiplier_housing)
    bills.append(FixedBill(
        day=3,
        sender="Tibber",
        sender_short="EL",
        sender_kind="util",
        subject=f"Elräkning {year_month}",
        body_meta="Spotpris + elnätsavgift",
        amount=el_amount,
    ))

    # Dag 5 · Bredband
    bills.append(FixedBill(
        day=5,
        sender="Bahnhof",
        sender_short="NET",
        sender_kind="util",
        subject=f"Bredband {year_month}",
        body_meta="100/100 Mbit/s fiber",
        amount=389,
    ))

    # Dag 7 · Mobil
    mobile_amount = rng.choice([119, 149, 199, 249, 299, 399])
    bills.append(FixedBill(
        day=7,
        sender="Telia",
        sender_short="TEL",
        sender_kind="util",
        subject=f"Mobilabonnemang {year_month}",
        body_meta=f"Surf-paket {mobile_amount} kr/mån",
        amount=mobile_amount,
    ))

    # Dag 8 · Hemförsäkring (bara om profil bor i egen lägenhet)
    if profile.housing.type in ("hyresratt", "bostadsratt", "villa", "radhus"):
        hf_amount = rng.randint(120, 220)
        if profile.housing.type == "villa":
            hf_amount = rng.randint(280, 480)  # villaförsäkring dyrare
        bills.append(FixedBill(
            day=8,
            sender="If Skadeförsäkring",
            sender_short="INS",
            sender_kind="ins",
            subject=f"Hemförsäkring {year_month}",
            body_meta=f"Premie för {profile.housing.size_kvm} kvm",
            amount=hf_amount,
        ))

    # Dag 10 · SL-kort / pendlartrans (om städer med kollektivtrafik)
    if city and city.job_density >= 1.0:
        sl_amount = 970 if city.key == "stockholm" else 850
        if city.key == "goteborg":
            sl_amount = 815  # Västtrafik 2026
        bills.append(FixedBill(
            day=10,
            sender=(
                "SL"
                if city.key == "stockholm" else
                "Västtrafik" if city.key == "goteborg" else "Lokaltrafik"
            ),
            sender_short="SL",
            sender_kind="util",
            subject=f"Periodbiljett {year_month}",
            body_meta="Månadskort kollektivtrafik",
            amount=sl_amount,
        ))

    return sorted(bills, key=lambda b: b.day)


def generate_fixed_expenses(
    s: Session,
    *,
    profile: GeneratedProfile,
    year_month: str,
    student_scope: str,
    rng: Optional[random.Random] = None,
) -> dict:
    """Skapar staggered fakturor för spelmånaden. Returnerar summary."""
    rng = rng or random.Random(f"{student_scope}|{year_month}|fixed")

    bills = _build_bills(rng, profile, year_month)
    created_ids: list[int] = []
    total = 0

    for bill in bills:
        due = _ym_to_date(year_month, bill.day)
        mail = MailItem(
            sender=bill.sender,
            sender_short=bill.sender_short,
            sender_kind=bill.sender_kind,
            sender_meta=f"faktura · förfaller {due.isoformat()}",
            mail_type="invoice",
            subject=bill.subject,
            body_meta=bill.body_meta,
            body=(
                f"{bill.subject}\n\n"
                f"Belopp: {bill.amount:,} kr\n".replace(",", " ")
                + f"Förfallodag: {due.isoformat()}\n"
                + (f"Bankgiro: {bill.bankgiro}\n" if bill.bankgiro else "")
            ),
            amount=Decimal(-bill.amount),  # Negativt = utgift
            due_date=due,
            status="unhandled",
            is_recurring=True,
            bankgiro=bill.bankgiro,
            ocr_reference=_bill_hash(
                student_scope, year_month, bill.sender_short, bill.day,
            )[:18],
        )
        s.add(mail)
        s.flush()
        created_ids.append(mail.id)
        total += bill.amount

    return {
        "items_created": len(created_ids),
        "mail_ids": created_ids,
        "total_amount": total,
        "by_day": [
            {"day": b.day, "sender": b.sender, "amount": b.amount}
            for b in bills
        ],
    }
