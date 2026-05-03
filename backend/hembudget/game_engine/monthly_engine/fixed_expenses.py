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

from ...db.models import InsurancePolicy, MailItem
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


def _seasonal_electricity_kwh(
    rng: random.Random, year_month: str, size_kvm: int,
) -> tuple[int, float]:
    """Realistisk el-förbrukning baserad på storlek + säsong.

    Returnerar (kWh, spotpris_per_kwh).

    Schablon SCB 2026 för svensk hyresrätt/lägenhet:
    - ~30 kWh/kvm/år för hushållsel (utan uppvärmning) i hyresrätt
    - + ~80-120 kWh/kvm/år för uppvärmning i bostadsrätt/villa
    - + ~3-5 kWh/kvm/år extra för varmvatten

    Spotpris (snitt 2026):
    - Vinter (dec/jan/feb): 1,40-2,20 kr/kWh
    - Vår/höst (mar/apr/okt/nov): 0,80-1,30 kr/kWh
    - Sommar (maj-sep): 0,40-0,80 kr/kWh
    + elnätsavgift fast (~250 kr/mån) som läggs på i _build_bills.
    """
    month = int(year_month.split("-")[1])
    # Bas-förbrukning per kvm + säsong
    if month in (12, 1, 2):
        kwh_per_kvm_month = rng.uniform(7.0, 9.5)  # vinter, hög uppv.
        spot = rng.uniform(1.40, 2.20)
    elif month in (3, 11):
        kwh_per_kvm_month = rng.uniform(5.0, 7.0)
        spot = rng.uniform(0.80, 1.30)
    elif month in (4, 10):
        kwh_per_kvm_month = rng.uniform(3.5, 5.0)
        spot = rng.uniform(0.60, 1.00)
    else:  # maj-sep · sommar
        kwh_per_kvm_month = rng.uniform(2.0, 3.5)
        spot = rng.uniform(0.40, 0.80)

    kwh = int(kwh_per_kvm_month * max(20, size_kvm))
    return kwh, round(spot, 2)


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

    # Dag 3 · El · realistisk kWh × spotpris + elnätsavgift
    kwh, spot = _seasonal_electricity_kwh(
        rng, year_month, profile.housing.size_kvm,
    )
    grid_fee = 250  # elnätsavgift fast/mån (genomsnitt 2026)
    spot_cost = int(kwh * spot)
    el_amount = spot_cost + grid_fee
    if city:
        el_amount = int(el_amount * city.cost_multiplier_housing)
    bills.append(FixedBill(
        day=3,
        sender="Tibber",
        sender_short="EL",
        sender_kind="util",
        subject=f"Elräkning {year_month}",
        body_meta=(
            f"{kwh} kWh × {spot:.2f} kr ({spot_cost} kr) + "
            f"{grid_fee} kr nät · {profile.housing.size_kvm} kvm"
        ),
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

    # Hemförsäkring + olycksfall + ev. bostadsrätts-/livförsäkring
    # läggs till från InsurancePolicy-tabellen i generate_fixed_expenses
    # nedan (efter att session öppnats). Då blir fakturorna konsistenta
    # med försäkringar som syns i /v2/forsakringar (samma provider och
    # premium som lärar-katalogen) — istället för en hårdkodad "If
    # Skadeförsäkring" som inte fanns någonstans annars.

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

    # Lägg till försäkrings-fakturor BARA för aktiva InsurancePolicy
    # i scope:n. Då matchar fakturorna policies som syns i
    # /v2/forsakringar (1 system, ingen inkonsistens).
    active_policies = (
        s.query(InsurancePolicy)
        .filter(InsurancePolicy.status == "active")
        .all()
    )
    for ip_idx, policy in enumerate(active_policies):
        if policy.premium_monthly is None or policy.premium_monthly <= 0:
            continue
        bills.append(FixedBill(
            day=8 + (ip_idx % 4),  # staggera dag 8-11 om flera försäkringar
            sender=policy.provider,
            sender_short=policy.provider[:3].upper(),
            sender_kind="ins",
            subject=f"{policy.name} {year_month}",
            body_meta=(
                f"Premie {int(policy.premium_monthly)} kr/mån · "
                f"självrisk {int(policy.deductible or 0)} kr"
            ),
            amount=int(policy.premium_monthly),
        ))

    bills = sorted(bills, key=lambda b: b.day)

    created_ids: list[int] = []
    total = 0

    for bill in bills:
        due = _ym_to_date(year_month, bill.day)
        ocr = _bill_hash(
            student_scope, year_month, bill.sender_short, bill.day,
        )[:14].upper()
        # Bygg en riktig faktura-body med rader, moms-uppdelning,
        # förfallodag, OCR och bankgiro — istället för en lös rad.
        # Moms 25 % är default; för bostadsrelaterat (hyra/avgift) 0 %.
        is_housing = bill.sender_kind == "land"
        is_insurance = bill.sender_kind == "ins"
        # Hyra och försäkring momsfritt
        moms_rate = 0.0 if (is_housing or is_insurance) else 0.25
        net = (
            int(round(bill.amount / (1 + moms_rate)))
            if moms_rate > 0
            else bill.amount
        )
        moms = bill.amount - net

        body_lines: list[str] = [
            f"FAKTURA · {bill.sender}",
            f"Avser: {bill.subject}",
            "",
            f"  {'Beskrivning':<40} {'Belopp':>12}",
            f"  {'-' * 40} {'-' * 12}",
            f"  {bill.body_meta or bill.subject:<40} "
            f"{net:>10,} kr".replace(",", " "),
        ]
        if moms > 0:
            body_lines.append(
                f"  {'Moms 25 %':<40} {moms:>10,} kr".replace(",", " ")
            )
        body_lines += [
            f"  {'-' * 40} {'-' * 12}",
            f"  {'TOTALT ATT BETALA':<40} "
            f"{bill.amount:>10,} kr".replace(",", " "),
            "",
            f"Förfallodag: {due.isoformat()}",
            f"OCR-referens: {ocr}",
        ]
        if bill.bankgiro:
            body_lines.append(f"Bankgiro: {bill.bankgiro}")
        body_lines += [
            "",
            "Vänligen betala via banken senast på förfallodagen.",
            "Försenad betalning kan medföra påminnelseavgift.",
        ]
        body = "\n".join(body_lines)

        mail = MailItem(
            sender=bill.sender,
            sender_short=bill.sender_short,
            sender_kind=bill.sender_kind,
            sender_meta=f"faktura · förfaller {due.isoformat()}",
            mail_type="invoice",
            subject=bill.subject,
            body_meta=bill.body_meta,
            body=body,
            amount=Decimal(-bill.amount),  # Negativt = utgift
            due_date=due,
            status="unhandled",
            is_recurring=True,
            bankgiro=bill.bankgiro,
            ocr_reference=ocr,
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
