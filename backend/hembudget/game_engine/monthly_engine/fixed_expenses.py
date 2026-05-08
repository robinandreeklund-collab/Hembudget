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
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from ...db.models import InsurancePolicy, MailItem
from ..pools.stadspool import STAD_BY_KEY
from ..profile_generator.schema import GeneratedProfile
from ..release_schedule import release_at_for_day


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
    # Strukturerad fakturadata · matchar V2InvoiceData på frontend.
    # None = enkel faktura (genereras default-rader). Sätt explicit
    # för fakturor med specifika rader/moms/period.
    invoice_data: Optional[dict] = None


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


def _format_text_invoice(
    *, sender: str, subject: str, inv: dict, due: date,
) -> str:
    """Mänskligt-läsbar fakturatext byggd från invoice_data.

    Visas som fallback-body för text-only-rendering. Strukturerad
    rendering i frontend använder invoice_data direkt.
    """
    lines: list[str] = [
        f"FAKTURA · {sender}",
        f"Avser: {subject}",
        (
            f"Period: {inv.get('period_start','—')} – "
            f"{inv.get('period_end','—')}"
        ),
        f"Fakturanummer: {inv.get('invoice_number','—')}",
        "",
        f"  {'Beskrivning':<42} {'Belopp':>12}",
        f"  {'-' * 42} {'-' * 12}",
    ]
    for row in inv.get("rows", []):
        label = str(row.get("label", ""))
        if row.get("qty") is not None:
            qty = row.get("qty")
            unit = row.get("unit", "")
            up = row.get("unit_price")
            if up is not None:
                label = f"{label} ({qty} {unit} × {up:.2f} kr)"
            else:
                label = f"{label} ({qty} {unit})"
        amt = int(row.get("amount", 0))
        lines.append(
            f"  {label[:42]:<42} {amt:>10,} kr".replace(",", " ")
        )

    moms = int(inv.get("moms", 0))
    moms_rate = inv.get("moms_rate", 0)
    if moms > 0:
        lines.append(
            f"  {'Moms ' + str(moms_rate) + ' %':<42} "
            f"{moms:>10,} kr".replace(",", " ")
        )
    total = int(inv.get("total", 0))
    lines += [
        f"  {'-' * 42} {'-' * 12}",
        f"  {'TOTALT ATT BETALA':<42} {total:>10,} kr".replace(",", " "),
        "",
        f"Förfallodag: {due.isoformat()}",
        f"OCR-referens: {inv.get('ocr','—')}",
    ]
    bg = inv.get("bankgiro")
    if bg:
        lines.append(f"Bankgiro: {bg}")
    extra = inv.get("extra") or {}
    if extra.get("moms_note"):
        lines += ["", f"Moms-info: {extra['moms_note']}"]
    if extra.get("policy_notes"):
        lines += ["", f"Försäkringsvillkor: {extra['policy_notes']}"]
    if extra.get("tip"):
        lines += ["", f"Tips: {extra['tip']}"]
    lines += [
        "",
        "Vänligen betala via banken senast på förfallodagen.",
        "Försenad betalning kan medföra påminnelseavgift (60-95 kr).",
    ]
    return "\n".join(lines)


def _period_dates(year_month: str) -> tuple[date, date]:
    """Returnera (period_start, period_end) för en given year-month."""
    y, m = map(int, year_month.split("-"))
    start = date(y, m, 1)
    if m == 12:
        end = date(y + 1, 1, 1)
    else:
        end = date(y, m + 1, 1)
    from datetime import timedelta as _td
    return start, end - _td(days=1)


def _prev_year_month(year_month: str) -> str:
    """'2026-05' → '2026-04'. Wrappar januari→föregående år."""
    y, m = map(int, year_month.split("-"))
    if m == 1:
        return f"{y - 1:04d}-12"
    return f"{y:04d}-{m - 1:02d}"


def _prev_period_dates(year_month: str) -> tuple[date, date]:
    """Period för föregående månad — används av konsumtionsbaserade
    fakturor (el, bredband, mobil, bolåneränta) som fakturerar
    efterskotts. Eleven kan inte få faktura för maj-förbrukning den
    5:e maj eftersom månaden inte ens är slut.
    """
    return _period_dates(_prev_year_month(year_month))


def _build_bills(
    rng: random.Random,
    profile: GeneratedProfile,
    year_month: str,
) -> list[FixedBill]:
    """Bygg lista över fakturor för månaden — sorterade på dag.

    Varje faktura kan ha invoice_data med strukturerade rader, moms,
    OCR och period — som sedan renderas i MailDetailV2.InvoiceLayout.
    """
    city = STAD_BY_KEY.get(profile.city_key)
    bills: list[FixedBill] = []
    period_start, period_end = _period_dates(year_month)

    def _ocr(seed_extra: str) -> str:
        raw = f"{year_month}|{seed_extra}|{profile.seed}"
        import hashlib as _hl
        return _hl.sha256(raw.encode()).hexdigest()[:14].upper()

    # === DAG 1 · BOENDE ===
    if profile.housing.type == "hyresratt":
        amount = profile.housing.monthly_cost
        ocr = _ocr(f"hyra-{year_month}")
        # Hyra är momsfri. Rader: kallhyra + ev. el-i-hyran.
        bills.append(FixedBill(
            day=1,
            sender=f"{profile.city_display} Bostäder",
            sender_short="HYR",
            sender_kind="land",
            subject=f"Hyresavi {year_month}",
            body_meta=(
                f"{profile.housing.size_kvm} kvm · {profile.city_display}"
            ),
            amount=amount,
            bankgiro="5402-3961",
            invoice_data={
                "kind": "hyra",
                "invoice_number": f"HYR-{year_month}-{profile.seed % 9999:04d}",
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "rows": [
                    {
                        "label": (
                            f"Kallhyra {profile.housing.size_kvm} kvm · "
                            f"lgh {profile.seed % 999:03d}"
                        ),
                        "amount": amount,
                    },
                ],
                "subtotal": amount,
                "moms": 0,
                "moms_rate": 0,
                "total": amount,
                "ocr": ocr,
                "bankgiro": "5402-3961",
                "extra": {
                    "size_kvm": profile.housing.size_kvm,
                    "city": profile.city_display,
                    "contract_type": "Förstahandskontrakt",
                    "moms_note": "Hyra är momsfri (1 kap. 11 § ML)",
                },
            },
        ))
    else:
        # BR/villa: månadsavgift + bolån + drift som separata fakturor
        if profile.housing.monthly_avgift:
            avgift = profile.housing.monthly_avgift
            ocr = _ocr(f"brf-{year_month}")
            bills.append(FixedBill(
                day=1,
                sender=f"BRF {profile.city_display}",
                sender_short="BRF",
                sender_kind="land",
                subject=f"Månadsavgift {year_month}",
                body_meta=f"Avgift för {profile.housing.size_kvm} kvm",
                amount=avgift,
                bankgiro="6310-1842",
                invoice_data={
                    "kind": "brf_avgift",
                    "invoice_number": (
                        f"BRF-{year_month}-{profile.seed % 999:03d}"
                    ),
                    "period_start": period_start.isoformat(),
                    "period_end": period_end.isoformat(),
                    "rows": [
                        {
                            "label": "Månadsavgift",
                            "amount": int(avgift * 0.65),
                        },
                        {
                            "label": "Värme & varmvatten (uppskattat)",
                            "amount": int(avgift * 0.20),
                        },
                        {
                            "label": "Underhållsfond",
                            "amount": int(avgift * 0.10),
                        },
                        {
                            "label": "Förvaltning",
                            "amount": int(avgift * 0.05),
                        },
                    ],
                    "subtotal": avgift,
                    "moms": 0,
                    "moms_rate": 0,
                    "total": avgift,
                    "ocr": ocr,
                    "bankgiro": "6310-1842",
                    "extra": {
                        "size_kvm": profile.housing.size_kvm,
                        "moms_note": "Bostadsrättsavgift är momsfri",
                    },
                },
            ))
        if profile.housing.monthly_amortering or profile.housing.monthly_interest:
            # Efterskotts: ränta beräknas på saldot under den
            # passerade månaden — inte den vi går in i. Faktura i maj
            # → ränta för aprils saldo.
            bolan_period_ym = _prev_year_month(year_month)
            bolan_period_start, bolan_period_end = _prev_period_dates(year_month)
            ranta = int(profile.housing.monthly_interest or 0)
            amort = int(profile.housing.monthly_amortering or 0)
            loan_total = ranta + amort
            ocr = _ocr(f"bolan-{year_month}")
            bills.append(FixedBill(
                day=2,
                sender="Spelbanken Bolån",
                sender_short="BANK",
                sender_kind="bank",
                subject=f"Bolån · ränta + amortering {bolan_period_ym}",
                body_meta=(
                    f"Lån {profile.housing.loan_amount or 0:,} kr · "
                    "ränta 3,75 %"
                ).replace(",", " "),
                amount=loan_total,
                bankgiro="5503-2197",
                invoice_data={
                    "kind": "bolan",
                    "invoice_number": (
                        f"BL-{year_month}-{profile.seed % 9999:04d}"
                    ),
                    "period_start": bolan_period_start.isoformat(),
                    "period_end": bolan_period_end.isoformat(),
                    "rows": [
                        {
                            "label": "Ränta (3,75 % p.a.)",
                            "amount": ranta,
                        },
                        {
                            "label": "Amortering (rak, 50 år)",
                            "amount": amort,
                        },
                    ],
                    "subtotal": loan_total,
                    "moms": 0,
                    "moms_rate": 0,
                    "total": loan_total,
                    "ocr": ocr,
                    "bankgiro": "5503-2197",
                    "extra": {
                        "loan_amount": profile.housing.loan_amount or 0,
                        "interest_rate_pct": 3.75,
                        "ranta_avdragsgill_pct": 30,
                        "moms_note": (
                            "Bolåneränta är momsfri men 30 % av räntan "
                            "är avdragsgill i deklarationen."
                        ),
                    },
                },
            ))
        if profile.housing.monthly_drift:
            # Efterskotts: kommunala driftavgifter (sopor, snöröjning)
            # avser passerad månads förbrukning.
            drift_period_ym = _prev_year_month(year_month)
            drift_period_start, drift_period_end = _prev_period_dates(year_month)
            drift = profile.housing.monthly_drift
            sopor = int(drift * 0.30)
            forsakring = int(drift * 0.40)
            snorojning = drift - sopor - forsakring
            ocr = _ocr(f"drift-{year_month}")
            bills.append(FixedBill(
                day=4,
                sender=f"{profile.city_display} kommun",
                sender_short="VILLA",
                sender_kind="util",
                subject=f"Driftavi villa {drift_period_ym}",
                body_meta="Sopor + försäkring + snöröjning",
                amount=drift,
                bankgiro="7521-0814",
                invoice_data={
                    "kind": "drift_villa",
                    "invoice_number": (
                        f"DR-{year_month}-{profile.seed % 9999:04d}"
                    ),
                    "period_start": drift_period_start.isoformat(),
                    "period_end": drift_period_end.isoformat(),
                    "rows": [
                        {"label": "Sophämtning + återvinning",
                         "amount": sopor},
                        {"label": "Villaförsäkring (årspremie /12)",
                         "amount": forsakring},
                        {"label": "Snöröjning + sandning (säsong)",
                         "amount": snorojning},
                    ],
                    "subtotal": drift,
                    "moms": 0,
                    "moms_rate": 0,
                    "total": drift,
                    "ocr": ocr,
                    "bankgiro": "7521-0814",
                    "extra": {
                        "moms_note": "Kommunala avgifter är momsfria",
                    },
                },
            ))

    # === DAG 3 · EL (Tibber) · kWh × spot + nät, moms 25 % ===
    # Efterskotts: el-räkningen som inkommer i maj avser april-
    # förbrukningen. Förbrukningen mäts först — sedan faktureras.
    el_period_ym = _prev_year_month(year_month)
    el_period_start, el_period_end = _prev_period_dates(year_month)
    kwh, spot = _seasonal_electricity_kwh(
        rng, el_period_ym, profile.housing.size_kvm,
    )
    grid_fee = 250  # elnätsavgift fast/mån (genomsnitt 2026)
    spot_cost = int(kwh * spot)
    energy_skatt = int(kwh * 0.45)  # energiskatt 45 öre/kWh 2026
    net_subtotal = spot_cost + grid_fee + energy_skatt
    moms = int(net_subtotal * 0.25)
    el_amount = net_subtotal + moms
    if city:
        el_amount = int(el_amount * city.cost_multiplier_housing)
    ocr = _ocr(f"el-{year_month}")
    bills.append(FixedBill(
        day=3,
        sender="Tibber",
        sender_short="EL",
        sender_kind="util",
        subject=f"Elräkning {el_period_ym}",
        body_meta=f"{kwh} kWh · {profile.housing.size_kvm} kvm",
        amount=el_amount,
        bankgiro="5050-1144",
        invoice_data={
            "kind": "el",
            "invoice_number": f"TB-{year_month}-{profile.seed % 99999:05d}",
            "period_start": el_period_start.isoformat(),
            "period_end": el_period_end.isoformat(),
            "rows": [
                {
                    "label": "Förbrukning",
                    "qty": kwh,
                    "unit": "kWh",
                    "unit_price": float(spot),
                    "amount": spot_cost,
                },
                {
                    "label": "Energiskatt (45 öre/kWh)",
                    "qty": kwh,
                    "unit": "kWh",
                    "unit_price": 0.45,
                    "amount": energy_skatt,
                },
                {
                    "label": "Elnätsavgift (fast)",
                    "amount": grid_fee,
                },
            ],
            "subtotal": net_subtotal,
            "moms": moms,
            "moms_rate": 25,
            "total": el_amount,
            "ocr": ocr,
            "bankgiro": "5050-1144",
            "extra": {
                "kwh_total": kwh,
                "spot_price": float(spot),
                "size_kvm": profile.housing.size_kvm,
                "tip": (
                    "Pedagogiskt: vinter ger 3-5x högre el-räkning. "
                    "Fast-pris-avtal jämnar ut men kostar premie."
                ),
            },
        },
    ))

    # === DAG 5 · BREDBAND (Bahnhof) · 100/100 fiber, moms 25 % ===
    # Efterskotts: fakturan i maj täcker föregående månads abonnemang.
    bb_period_ym = _prev_year_month(year_month)
    bb_period_start, bb_period_end = _prev_period_dates(year_month)
    bb_net = 311  # 311 kr ex moms
    bb_moms = int(bb_net * 0.25)
    bb_total = bb_net + bb_moms
    ocr = _ocr(f"bredband-{year_month}")
    bills.append(FixedBill(
        day=5,
        sender="Bahnhof",
        sender_short="NET",
        sender_kind="util",
        subject=f"Bredband {bb_period_ym}",
        body_meta="100/100 Mbit/s fiber · obegränsat",
        amount=bb_total,
        bankgiro="5995-0312",
        invoice_data={
            "kind": "bredband",
            "invoice_number": f"BH-{year_month}-{profile.seed % 99999:05d}",
            "period_start": bb_period_start.isoformat(),
            "period_end": bb_period_end.isoformat(),
            "rows": [
                {"label": "Bahnhof Fiber 100/100 Mbit/s",
                 "amount": int(bb_net * 0.85)},
                {"label": "Statisk IP",
                 "amount": int(bb_net * 0.05)},
                {"label": "Routerhyra",
                 "amount": bb_net - int(bb_net * 0.85)
                          - int(bb_net * 0.05)},
            ],
            "subtotal": bb_net,
            "moms": bb_moms,
            "moms_rate": 25,
            "total": bb_total,
            "ocr": ocr,
            "bankgiro": "5995-0312",
            "extra": {
                "speed_down_mbit": 100,
                "speed_up_mbit": 100,
                "binding": "Tillsvidare",
            },
        },
    ))

    # === DAG 7 · MOBIL (Telia) · surfpaket + samtal, moms 25 % ===
    # Efterskotts: fakturan i maj täcker föregående månads samtal+surf.
    mob_period_ym = _prev_year_month(year_month)
    mob_period_start, mob_period_end = _prev_period_dates(year_month)
    mobile_subtotal = rng.choice([95, 119, 159, 199, 239, 319])
    mobile_data_gb = {95: 5, 119: 15, 159: 30, 199: 60, 239: 100, 319: 1000}
    surf_gb = mobile_data_gb.get(mobile_subtotal, 30)
    mobile_moms = int(mobile_subtotal * 0.25)
    mobile_total = mobile_subtotal + mobile_moms
    ocr = _ocr(f"mobil-{year_month}")
    bills.append(FixedBill(
        day=7,
        sender="Telia",
        sender_short="TEL",
        sender_kind="util",
        subject=f"Mobilabonnemang {mob_period_ym}",
        body_meta=f"{surf_gb} GB surf · obegränsade samtal",
        amount=mobile_total,
        bankgiro="5050-2299",
        invoice_data={
            "kind": "mobil",
            "invoice_number": f"TEL-{year_month}-{profile.seed % 99999:05d}",
            "period_start": mob_period_start.isoformat(),
            "period_end": mob_period_end.isoformat(),
            "rows": [
                {"label": f"Surfpaket {surf_gb} GB",
                 "amount": int(mobile_subtotal * 0.65)},
                {"label": "Obegränsade samtal & SMS",
                 "amount": int(mobile_subtotal * 0.30)},
                {"label": "Mobilförsäkring (basic)",
                 "amount": (
                     mobile_subtotal
                     - int(mobile_subtotal * 0.65)
                     - int(mobile_subtotal * 0.30)
                 )},
            ],
            "subtotal": mobile_subtotal,
            "moms": mobile_moms,
            "moms_rate": 25,
            "total": mobile_total,
            "ocr": ocr,
            "bankgiro": "5050-2299",
            "extra": {
                "data_gb": surf_gb,
                "binding": "12 mån",
            },
        },
    ))

    # Hemförsäkring + olycksfall + ev. bostadsrätts-/livförsäkring
    # läggs till från InsurancePolicy-tabellen i generate_fixed_expenses
    # nedan (efter att session öppnats).

    # === DAG 10 · LOKALTRAFIK · månadskort om städer med koll-trafik ===
    if city and city.job_density >= 1.0:
        sl_amount = 970 if city.key == "stockholm" else 850
        sl_provider = "SL"
        sl_bg = "5012-0145"
        if city.key == "goteborg":
            sl_amount = 815
            sl_provider = "Västtrafik"
            sl_bg = "5012-0212"
        elif city.key == "malmo":
            sl_amount = 850
            sl_provider = "Skånetrafiken"
            sl_bg = "5012-0301"
        elif city.key != "stockholm":
            sl_provider = "Lokaltrafik"
        # SL/koll-trafik · moms 6 % på persontransport
        sl_net = int(sl_amount / 1.06)
        sl_moms = sl_amount - sl_net
        ocr = _ocr(f"sl-{year_month}")
        bills.append(FixedBill(
            day=10,
            sender=sl_provider,
            sender_short="SL",
            sender_kind="util",
            subject=f"Periodbiljett {year_month} · 30 dgr",
            body_meta=f"Månadskort {sl_provider} · {profile.city_display}",
            amount=sl_amount,
            bankgiro=sl_bg,
            invoice_data={
                "kind": "lokaltrafik",
                "invoice_number": f"{sl_provider[:3].upper()}-{year_month}-{profile.seed % 99999:05d}",
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "rows": [
                    {
                        "label": f"30-dagarsbiljett · {sl_provider} ({profile.city_display})",
                        "amount": sl_net,
                    },
                ],
                "subtotal": sl_net,
                "moms": sl_moms,
                "moms_rate": 6,
                "total": sl_amount,
                "ocr": ocr,
                "bankgiro": sl_bg,
                "extra": {
                    "moms_note": "Persontransport har reducerad moms 6 %",
                },
            },
        ))

    return sorted(bills, key=lambda b: b.day)


def generate_fixed_expenses(
    s: Session,
    *,
    profile: GeneratedProfile,
    year_month: str,
    student_scope: str,
    rng: Optional[random.Random] = None,
    release_base: Optional[datetime] = None,
) -> dict:
    """Skapar staggered fakturor för spelmånaden. Returnerar summary.

    `release_base`: T0 för realtid-projektion. Om satt får varje
    MailItem ett `released_at = release_base + offset` baserat på
    bill.day (1-30) så fakturorna dyker upp gradvis i postlådan
    över 5 real-dagar. None = visa direkt.
    """
    rng = rng or random.Random(f"{student_scope}|{year_month}|fixed")

    bills = _build_bills(rng, profile, year_month)
    period_start, period_end = _period_dates(year_month)

    def _ocr(seed_extra: str) -> str:
        return _bill_hash(
            student_scope, year_month, seed_extra, 0,
        )[:14].upper()

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
        premium = int(policy.premium_monthly)
        sj = int(policy.deductible or 0)
        cov = int(policy.coverage_amount or 0)
        ocr_ins = _ocr(f"ins-{policy.id}-{year_month}")
        bills.append(FixedBill(
            day=8 + (ip_idx % 4),
            sender=policy.provider,
            sender_short=policy.provider[:3].upper(),
            sender_kind="ins",
            subject=f"{policy.name} · premie {year_month}",
            body_meta=(
                f"Premie {premium} kr/mån · självrisk {sj} kr"
            ),
            amount=premium,
            bankgiro=f"5000-{ip_idx + 1:04d}",
            invoice_data={
                "kind": "forsakring",
                "invoice_number": (
                    f"{policy.provider[:3].upper()}-"
                    f"{year_month}-{policy.id:04d}"
                ),
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "rows": [
                    {
                        "label": f"{policy.name} (månadspremie)",
                        "amount": premium,
                    },
                ],
                "subtotal": premium,
                "moms": 0,
                "moms_rate": 0,
                "total": premium,
                "ocr": ocr_ins,
                "bankgiro": f"5000-{ip_idx + 1:04d}",
                "extra": {
                    "policy_kind": policy.kind,
                    "coverage_amount": cov,
                    "deductible": sj,
                    "moms_note": "Försäkringspremier är momsfria (3 kap. 10 § ML)",
                    "policy_notes": policy.notes or "",
                },
            },
        ))

    bills = sorted(bills, key=lambda b: b.day)

    created_ids: list[int] = []
    total = 0

    for bill in bills:
        due = _ym_to_date(year_month, bill.day)

        # invoice_data är primär källa när bill har strukturerade rader.
        # Fallback för fakturor som ännu inte har invoice_data byggt:
        # generera enkel struktur här.
        if bill.invoice_data is not None:
            inv = bill.invoice_data
            ocr_val = inv.get("ocr") or _ocr(
                f"{bill.sender_short}-{bill.day}",
            )
            inv["ocr"] = ocr_val
        else:
            ocr_val = _ocr(f"{bill.sender_short}-{bill.day}")
            inv = {
                "kind": "annan",
                "invoice_number": (
                    f"{bill.sender_short}-{year_month}-{bill.day:02d}"
                ),
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "rows": [
                    {"label": bill.body_meta or bill.subject,
                     "amount": bill.amount},
                ],
                "subtotal": bill.amount,
                "moms": 0,
                "moms_rate": 0,
                "total": bill.amount,
                "ocr": ocr_val,
                "bankgiro": bill.bankgiro,
                "extra": {},
            }

        # Mänsklig text-body genereras från invoice_data så även
        # text-rendering visar samma poster som strukturerad rendering.
        body = _format_text_invoice(
            sender=bill.sender,
            subject=bill.subject,
            inv=inv,
            due=due,
        )

        # Releasa fakturan när den ANLÄNDER (~14 dgr innan due), inte
        # när den FÖRFALLER. Tidigare buggen: bill.day=3 (Tibber Jan 3)
        # gav release_at = release_base + 2 dgr → mailet syntes först
        # på Jan 3 (= förfallodagen) i spel-tid. Eleven hade ingen tid
        # att betala. Nu släpps på receive_day = max(1, due_day - 14)
        # så mail om Jan-3-faktura är synligt redan vid start (Jan 1).
        receive_day = max(1, bill.day - 14)
        released_at = (
            release_at_for_day(release_base, receive_day)
            if release_base is not None
            else None
        )
        # received_at = SPEL-datetime så postlådan visar "20 dec" inte
        # "7 maj" (real-tid när seed kördes). Använder due_date - 14d
        # som "fakturadatum" (svensk standard: kund får 14-30 dgr).
        from datetime import (
            datetime as _dt_fe, timedelta as _td_fe,
        )
        receive_d = due - _td_fe(days=14)
        receive_at_spel = _dt_fe.combine(
            receive_d, _dt_fe.min.time(),
        ).replace(hour=8)
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
            ocr_reference=ocr_val,
            invoice_data=inv,
            released_at=released_at,
            received_at=receive_at_spel,
        )
        s.add(mail)
        s.flush()
        created_ids.append(mail.id)
        total += bill.amount

        # Skapa motsvarande UtilityReading för el/bredband/mobil/vatten
        # så /v2/forbrukning kan visa historik. Annars syns bara
        # fakturan i postlådan men förbrukning-aktören är tom.
        if bill.invoice_data and bill.invoice_data.get("kind") in (
            "el", "bredband", "mobil", "vatten",
        ):
            try:
                from ...db.models import UtilityReading
                _kind_map = {
                    "el": ("electricity", "kWh", "energy"),
                    "bredband": ("internet", None, "energy"),
                    "mobil": ("mobile", None, "energy"),
                    "vatten": ("water", "m3", "energy"),
                }
                meter_type, default_unit, meter_role = _kind_map[
                    bill.invoice_data["kind"]
                ]
                extra = bill.invoice_data.get("extra") or {}
                period_start_str = bill.invoice_data.get("period_start")
                period_end_str = bill.invoice_data.get("period_end")
                if period_start_str and period_end_str:
                    consumption = None
                    consumption_unit = default_unit
                    if bill.invoice_data["kind"] == "el":
                        consumption = Decimal(
                            str(extra.get("kwh_total") or 0)
                        )
                        consumption_unit = "kWh"
                    s.add(UtilityReading(
                        supplier=bill.sender,
                        meter_type=meter_type,
                        meter_role=meter_role,
                        period_start=date.fromisoformat(period_start_str),
                        period_end=date.fromisoformat(period_end_str),
                        consumption=consumption,
                        consumption_unit=consumption_unit,
                        cost_kr=Decimal(str(bill.amount)),
                        source="seed",
                        notes=f"Auto-skapad från {bill.subject}",
                    ))
            except Exception:
                # UtilityReading är best-effort · ingen krasch
                # om modellen saknar kolumn / annan miljö-skillnad.
                pass

    return {
        "items_created": len(created_ids),
        "mail_ids": created_ids,
        "total_amount": total,
        "by_day": [
            {"day": b.day, "sender": b.sender, "amount": b.amount}
            for b in bills
        ],
    }
