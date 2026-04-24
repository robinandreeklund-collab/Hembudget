"""Bygger ett "månadsscenario" från en elevprofil — alla händelser som
ska bli till PDF-artefakter (lönespec, kontoutdrag, lån, kreditkort).

Logiken här är PERSONLIGHETSDRIVEN:
- sparsam: lägre konsumtion, hög sparkvot, sällan kreditkort
- blandad: balanserat, måttligt sparande
- slosaktig: hög konsumtion (restaurang, shopping, nöje), låg sparkvot,
  ofta kreditkort + ev. överskridit budget

Varje månad kan ge olika exakta värden (slumpas på (student_id, year_month))
men profilens grunddrag bevaras.
"""
from __future__ import annotations

import calendar
import random
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass
class TxEvent:
    """En enskild bankhändelse på lönekontot."""
    date: date
    description: str
    amount: Decimal  # negativt = utgift, positivt = inkomst
    category_hint: str = ""


@dataclass
class CardEvent:
    """Ett kortköp på kreditkortet (samlas till faktura)."""
    date: date
    description: str
    amount: Decimal  # alltid positiv (köpbelopp)
    category_hint: str = ""


@dataclass
class LoanEvent:
    """En låneavi för månaden."""
    loan_name: str
    lender: str
    interest: Decimal
    amortization: Decimal
    remaining: Decimal
    rate_pct: float
    due_date: date


@dataclass
class SalaryEvent:
    """En lönespec för månaden."""
    employer: str
    profession: str
    gross: Decimal
    grundavdrag: Decimal
    kommunal_tax: Decimal
    statlig_tax: Decimal
    net: Decimal
    pay_date: date


@dataclass
class MonthScenario:
    year_month: str
    student_id: int
    bank_account_no: str
    card_account_no: str
    bank_name: str = "Ekonomilabbet Bank"
    card_name: str = "Ekonomilabbet Kort"
    salary: SalaryEvent | None = None
    transactions: list[TxEvent] = field(default_factory=list)
    card_events: list[CardEvent] = field(default_factory=list)
    loans: list[LoanEvent] = field(default_factory=list)
    opening_balance: Decimal = Decimal("0")


# --- Konsumtions-mallar per personlighet ---

CONSUMPTION_PROFILES: dict[str, dict] = {
    "sparsam": {
        "groceries_per_week": (700, 1100),
        "restaurant_per_month": (0, 2),
        "entertainment_per_month": (0, 1),
        "shopping_per_month": (0, 1),
        "transport_per_month": (700, 1200),
        "savings_pct_of_net": (0.20, 0.35),
        "card_usage": 0.10,  # % av utgifter på kort
    },
    "blandad": {
        "groceries_per_week": (900, 1500),
        "restaurant_per_month": (2, 5),
        "entertainment_per_month": (1, 3),
        "shopping_per_month": (1, 3),
        "transport_per_month": (800, 1400),
        "savings_pct_of_net": (0.05, 0.15),
        "card_usage": 0.30,
    },
    "slosaktig": {
        "groceries_per_week": (1100, 1900),
        "restaurant_per_month": (5, 12),
        "entertainment_per_month": (3, 8),
        "shopping_per_month": (3, 7),
        "transport_per_month": (900, 1600),
        "savings_pct_of_net": (0.0, 0.05),
        "card_usage": 0.55,
    },
}


# --- Handlare per kategori (deterministiska val per profil) ---

MERCHANTS_GROCERY = [
    "ICA Maxi", "ICA Kvantum", "Coop Konsum", "Willys", "Hemköp", "Lidl",
]
MERCHANTS_RESTAURANT = [
    "Max Hamburgare", "McDonald's", "Sushi Yama", "O'Learys",
    "Espresso House", "Pizza Hut", "Burger King", "Wayne's Coffee",
]
MERCHANTS_ENT = [
    "Spotify Premium", "Netflix", "HBO Max", "Viaplay", "SF Bio",
    "Steam Games", "Systembolaget",
]
MERCHANTS_SHOP = [
    "H&M", "Zara", "Clas Ohlson", "Jula", "IKEA", "Elgiganten",
    "Biltema", "Lindex", "Stadium",
]
MERCHANTS_TRANSPORT = [
    "SL Access", "Västtrafik Periodkort", "Preem Bensin",
    "Circle K", "OKQ8",
]


def build_scenario(
    *,
    student_id: int,
    year_month: str,
    profile,  # StudentProfile (master-DB)
    seed: int | None = None,
) -> MonthScenario:
    """Slumpa fram ett komplett månadsscenario."""
    s = seed if seed is not None else (
        abs(hash((student_id, year_month, "scenario"))) & 0xFFFFFFFF
    )
    rng = random.Random(s)
    year, month = map(int, year_month.split("-"))
    last_day = calendar.monthrange(year, month)[1]
    first_day = date(year, month, 1)

    # Konton (deterministiska per elev — samma över månader)
    id_rng = random.Random(abs(hash(("acc_id", student_id))) & 0xFFFFFFFF)
    bank_no = (
        f"{id_rng.randint(1000,9999)} {id_rng.randint(10,99)} "
        f"{id_rng.randint(10000,99999)}"
    )
    card_no = f"4571 **** **** {id_rng.randint(1000,9999)}"

    scenario = MonthScenario(
        year_month=year_month,
        student_id=student_id,
        bank_account_no=bank_no,
        card_account_no=card_no,
    )

    # ---------- Lön ----------
    pay_day = id_rng.choice([25, 26, 27])
    pay_date = date(year, month, min(pay_day, last_day))
    scenario.salary = SalaryEvent(
        employer=profile.employer,
        profession=profile.profession,
        gross=Decimal(profile.gross_salary_monthly),
        grundavdrag=Decimal(1_250),
        kommunal_tax=Decimal(round((profile.gross_salary_monthly - 1250) * 0.32)),
        statlig_tax=Decimal(0),  # redan inräknat i tax_rate ifall över brytpunkt
        net=Decimal(profile.net_salary_monthly),
        pay_date=pay_date,
    )
    scenario.transactions.append(TxEvent(
        date=pay_date,
        description=f"LÖN {profile.employer.upper()}",
        amount=Decimal(profile.net_salary_monthly),
        category_hint="Lön",
    ))

    # ---------- Återkommande utgifter (alltid bankgiro/autogiro) ----------
    # Hyra/avgift på 27:e (eller liknande)
    rent_day = id_rng.choice([27, 28, 30])
    rent_date = date(year, month, min(rent_day, last_day))
    rent_label = {
        "hyresratt": "HYRA",
        "bostadsratt": "BRF AVGIFT",
        "villa": "DRIFT VILLA",
    }[profile.housing_type]
    scenario.transactions.append(TxEvent(
        date=rent_date,
        description=f"{rent_label} {profile.city.upper()}",
        amount=-Decimal(profile.housing_monthly),
        category_hint="Boende",
    ))

    # El (varierar per månad, högre vintern)
    el_base = 600 if month in (12, 1, 2) else 350
    el_amount = rng.randint(el_base, el_base + 800)
    scenario.transactions.append(TxEvent(
        date=date(year, month, min(15, last_day)),
        description=id_rng.choice([
            "VATTENFALL ELNAT", "FORTUM EL", "ELLEVIO ELNÄT",
            "TIBBER ENERGI",
        ]),
        amount=-Decimal(el_amount),
        category_hint="El",
    ))

    # Bredband
    scenario.transactions.append(TxEvent(
        date=date(year, month, min(20, last_day)),
        description=id_rng.choice([
            "TELIA BREDBAND", "BAHNHOF", "COM HEM", "TELE2",
        ]),
        amount=-Decimal(id_rng.randint(379, 549)),
        category_hint="Bredband",
    ))

    # Mobil
    scenario.transactions.append(TxEvent(
        date=date(year, month, min(20, last_day)),
        description=id_rng.choice([
            "TELENOR ABONNEMANG", "TELIA MOBIL", "TRE",
        ]),
        amount=-Decimal(id_rng.randint(199, 449)),
        category_hint="Mobil",
    ))

    # Försäkring
    if rng.random() < 0.7:
        scenario.transactions.append(TxEvent(
            date=date(year, month, min(5, last_day)),
            description=id_rng.choice([
                "IF FORSAKRING", "TRYGG HANSA", "FOLKSAM HEM",
                "LANSFORSAKRINGAR HEM",
            ]),
            amount=-Decimal(id_rng.randint(180, 480)),
            category_hint="Försäkring",
        ))

    # ---------- Lån ----------
    if profile.has_mortgage:
        loan_amount = id_rng.randint(1_500_000, 3_500_000)
        rate = round(id_rng.uniform(0.038, 0.048), 4)
        # Förenklat: ~10 år in i amorteringen
        remaining = Decimal(int(loan_amount * 0.78))
        amort = Decimal(round(loan_amount * 0.013 / 12))
        interest = Decimal(round(float(remaining) * rate / 12))
        loan_due = date(year, month, min(28, last_day))
        scenario.loans.append(LoanEvent(
            loan_name="Bolån",
            lender=id_rng.choice(["SBAB", "SEB", "Swedbank", "Handelsbanken"]),
            interest=interest,
            amortization=amort,
            remaining=remaining - amort,
            rate_pct=rate * 100,
            due_date=loan_due,
        ))
        scenario.transactions.append(TxEvent(
            date=loan_due,
            description=f"BOLÅN AUTOGIRO",
            amount=-(interest + amort),
            category_hint="Huslån",
        ))
    if profile.has_car_loan:
        car_loan = id_rng.randint(80_000, 220_000)
        rate = round(id_rng.uniform(0.055, 0.085), 4)
        remaining = Decimal(int(car_loan * 0.65))
        amort = Decimal(round(car_loan * 0.04 / 12))
        interest = Decimal(round(float(remaining) * rate / 12))
        due = date(year, month, min(15, last_day))
        scenario.loans.append(LoanEvent(
            loan_name="Billån",
            lender=id_rng.choice(["Santander", "Resurs Bank", "Volvofinans"]),
            interest=interest,
            amortization=amort,
            remaining=remaining - amort,
            rate_pct=rate * 100,
            due_date=due,
        ))
        scenario.transactions.append(TxEvent(
            date=due,
            description="BILLÅN AUTOGIRO",
            amount=-(interest + amort),
            category_hint="Billån",
        ))
    if profile.has_student_loan:
        # CSN är ett aggregat — visa bara ett mindre belopp/månad
        amount = id_rng.randint(950, 2200)
        scenario.transactions.append(TxEvent(
            date=date(year, month, min(28, last_day)),
            description="CSN AUTOGIRO",
            amount=-Decimal(amount),
            category_hint="Studielån",
        ))

    # ---------- Konsumtion (personlighetsdriven) ----------
    cp = CONSUMPTION_PROFILES[profile.personality]

    # Mat — varje vecka
    for week in range(4):
        day = rng.randint(1, last_day)
        amount = rng.randint(*cp["groceries_per_week"])
        merchant = rng.choice(MERCHANTS_GROCERY)
        on_card = rng.random() < cp["card_usage"]
        ev = (CardEvent if on_card else TxEvent)(
            date=date(year, month, day),
            description=f"{merchant}",
            amount=Decimal(amount) if on_card else -Decimal(amount),
            category_hint="Mat",
        )
        if on_card:
            scenario.card_events.append(ev)
        else:
            scenario.transactions.append(ev)

    # Restaurang
    n_rest = rng.randint(*cp["restaurant_per_month"])
    for _ in range(n_rest):
        day = rng.randint(1, last_day)
        amount = rng.randint(95, 450)
        merchant = rng.choice(MERCHANTS_RESTAURANT)
        on_card = rng.random() < cp["card_usage"] + 0.1
        ev = (CardEvent if on_card else TxEvent)(
            date=date(year, month, day),
            description=f"{merchant}",
            amount=Decimal(amount) if on_card else -Decimal(amount),
            category_hint="Restaurang",
        )
        (scenario.card_events if on_card else scenario.transactions).append(ev)

    # Nöje
    n_ent = rng.randint(*cp["entertainment_per_month"])
    for _ in range(n_ent):
        day = rng.randint(1, last_day)
        merchant = rng.choice(MERCHANTS_ENT)
        # Streaming = fast pris
        if "Premium" in merchant or merchant in ("Netflix", "HBO Max", "Viaplay"):
            amount = id_rng.randint(99, 229)
        else:
            amount = rng.randint(99, 590)
        on_card = rng.random() < cp["card_usage"]
        ev = (CardEvent if on_card else TxEvent)(
            date=date(year, month, day),
            description=f"{merchant}",
            amount=Decimal(amount) if on_card else -Decimal(amount),
            category_hint="Nöje",
        )
        (scenario.card_events if on_card else scenario.transactions).append(ev)

    # Shopping
    n_shop = rng.randint(*cp["shopping_per_month"])
    for _ in range(n_shop):
        day = rng.randint(1, last_day)
        merchant = rng.choice(MERCHANTS_SHOP)
        amount = rng.randint(199, 2900)
        on_card = rng.random() < cp["card_usage"] + 0.15
        ev = (CardEvent if on_card else TxEvent)(
            date=date(year, month, day),
            description=f"{merchant}",
            amount=Decimal(amount) if on_card else -Decimal(amount),
            category_hint="Shopping",
        )
        (scenario.card_events if on_card else scenario.transactions).append(ev)

    # Transport (bensin/SL)
    transport = rng.randint(*cp["transport_per_month"])
    scenario.transactions.append(TxEvent(
        date=date(year, month, rng.randint(1, last_day)),
        description=rng.choice(MERCHANTS_TRANSPORT),
        amount=-Decimal(transport),
        category_hint="Transport",
    ))

    # Sparande (sparsam → större överföring i månadens slut)
    savings_pct = rng.uniform(*cp["savings_pct_of_net"])
    savings = round(profile.net_salary_monthly * savings_pct, -2)
    if savings > 100:
        scenario.transactions.append(TxEvent(
            date=date(year, month, last_day),
            description="ÖVERFÖRING SPARKONTO",
            amount=-Decimal(int(savings)),
            category_hint="Sparande",
        ))

    # Sortera tx kronologiskt
    scenario.transactions.sort(key=lambda t: (t.date, t.description))
    scenario.card_events.sort(key=lambda t: (t.date, t.description))

    return scenario
