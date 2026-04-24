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
    # Antal sjukdagar denna månad (karensdag + 80% ersättning på de
    # första 14 dagarna, enligt Försäkringskassan). 0 = ingen sjukdom.
    sick_days: int = 0
    sick_deduction: Decimal = Decimal("0")
    note: str = ""


def _lookup_mortgage_rate(year_month: str) -> float | None:
    """Hämta bolån-rörlig-räntan för given månad från master-DB. Returnerar
    None om ingen data finns (t.ex. vid test utan master-DB)."""
    try:
        from ..school.engines import master_session
        from ..school.rates import get_rate_for_month
        with master_session() as s:
            return get_rate_for_month(s, year_month, "bolan_rorlig")
    except Exception:
        return None


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

# --- Säsongsmultiplikatorer per kategori × månad ---
# Värde 1.0 = normal, 1.5 = 50% mer, 0.8 = 20% mindre
SEASONAL_MULT: dict[str, list[float]] = {
    # Index 0 = januari, 11 = december
    "groceries":     [1.05, 0.95, 1.00, 1.00, 1.00, 1.05, 1.10, 1.10, 1.00, 1.00, 1.05, 1.30],
    "restaurant":    [0.9,  1.0,  1.0,  1.1,  1.15, 1.2,  1.3,  1.2,  1.0,  1.0,  1.0,  1.4],
    "entertainment": [0.85, 1.0,  1.0,  1.0,  1.15, 1.1,  1.15, 1.1,  1.0,  1.0,  1.0,  1.35],
    "shopping":      [0.7,  0.9,  1.0,  1.1,  1.0,  1.1,  1.2,  1.1,  0.9,  0.95, 1.1,  1.8],
    "transport":     [1.1,  1.0,  1.0,  1.0,  1.0,  1.15, 1.3,  1.15, 1.0,  1.0,  1.0,  1.1],
    "gift":          [0.5,  1.0,  1.0,  0.8,  1.5,  1.0,  1.0,  0.8,  1.0,  1.0,  1.0,  3.0],
    # El skalas redan separat i scenario-logiken
}


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

    # ---------- Månadsspecifika "händelser" (overshoot-logik) ----------
    # Varje månad slumpas det fram 0-2 händelser som gör att eleven får
    # se att olika saker påverkar budgeten. Pedagogiskt syfte.
    # Exempel: tandläkarbesök, vinterel, semester, bilreparation.
    # Tupel: (facit-kategori, (beskrivning, min, max))
    # Facit-kategorin MÅSTE vara en riktig app-kategori som eleven kan välja
    EVENTS = [
        ("Hälsa",       ("HÄLSA TANDLÄKARE", 1500, 4500)),
        ("Transport",   ("BILVERKSTAD VOLVO", 2500, 8000)),
        ("El",          ("ELRÄKNING EXTRA HÖG", 1200, 2800)),
        ("Presenter",   ("PRESENTSHOP", 400, 1500)),
        ("Shopping",    ("IKEA", 2200, 6500)),
        ("Shopping",    ("H&M STORHANDEL", 800, 2400)),
        ("Hälsa",       ("APOTEKET HJÄRTAT", 350, 1200)),
        ("Restaurang",  ("RESTAURANG OPERAKÄLLAREN", 850, 2200)),
        ("Försäkring",  ("IF FÖRSÄKRING ÅRSAVI", 1200, 3500)),
        ("Resor",       ("SJ RESA TILL STOCKHOLM", 700, 2900)),
        # Hushåll som går sönder — trasiga vitvaror, elektronik
        ("Hemelektronik", ("ELGIGANTEN NY DISKMASKIN", 6500, 14_000)),
        ("Hemelektronik", ("MEDIAMARKT NY TV", 4500, 18_000)),
        ("Hemelektronik", ("ELEKTROSKANDIA NY KYL", 8500, 18_000)),
        ("Hemelektronik", ("NETONNET NY TVÄTTMASKIN", 5500, 12_000)),
        ("Hem & Hushåll", ("JULA NYA MÖBLER", 1200, 4500)),
        ("Presenter",   ("BOKUS JULKLAPPAR", 800, 3500)),  # dec
    ]
    # Personlighet styr sannolikhet
    n_events = {
        "sparsam": rng.choices([0, 1, 2], weights=[0.5, 0.4, 0.1])[0],
        "blandad": rng.choices([0, 1, 2], weights=[0.3, 0.5, 0.2])[0],
        "slosaktig": rng.choices([1, 2, 3], weights=[0.3, 0.5, 0.2])[0],
    }[profile.personality]
    selected_events = rng.sample(EVENTS, min(n_events, len(EVENTS)))
    overshoot_events: list[tuple[str, str, int]] = []
    for ev_kind, (desc, lo, hi) in selected_events:
        amount = rng.randint(lo, hi)
        day = rng.randint(1, last_day)
        ev_date = date(year, month, day)
        # ~50% chans att hamna på kort, annars konto
        on_card = rng.random() < 0.4 and profile.has_credit_card
        ev = (CardEvent if on_card else TxEvent)(
            date=ev_date,
            description=desc,
            amount=Decimal(amount) if on_card else -Decimal(amount),
            category_hint=ev_kind,
        )
        if on_card:
            scenario.card_events.append(ev)
        else:
            scenario.transactions.append(ev)
        overshoot_events.append((ev_kind, desc, amount))

    # ---------- Lön ----------
    pay_day = id_rng.choice([25, 26, 27])
    pay_date = date(year, month, min(pay_day, last_day))
    gross_monthly = profile.gross_salary_monthly
    net_monthly = profile.net_salary_monthly
    sick_days = 0
    sick_deduction = Decimal(0)
    sick_note = ""

    # 10% chans per månad för kort sjukdom (1-5 dagar)
    # Första dagen är karens (0% ersättning), resten 80%.
    if rng.random() < 0.10:
        sick_days = rng.randint(1, 5)
        # Grovt: daglig lön = gross/22 arbetsdagar
        daily_gross = gross_monthly / 22
        # Dag 1 = 100% avdrag, dag 2-5 = 20% avdrag (80% sjuklön)
        deduction = daily_gross  # karensdag
        if sick_days > 1:
            deduction += (sick_days - 1) * daily_gross * 0.20
        sick_deduction = Decimal(round(deduction))
        gross_monthly = max(0, gross_monthly - int(sick_deduction))
        net_monthly = max(0, net_monthly - int(float(sick_deduction) * 0.68))  # ca 32% skatteåtgång
        sick_note = (
            f"Du var sjukskriven {sick_days} dag{'ar' if sick_days > 1 else ''}. "
            f"Sjukavdrag: {sick_deduction} kr. Lönen denna månad är lägre än vanligt."
        )

    scenario.salary = SalaryEvent(
        employer=profile.employer,
        profession=profile.profession,
        gross=Decimal(gross_monthly),
        grundavdrag=Decimal(1_250),
        kommunal_tax=Decimal(round((gross_monthly - 1250) * 0.32)),
        statlig_tax=Decimal(0),
        net=Decimal(net_monthly),
        pay_date=pay_date,
        sick_days=sick_days,
        sick_deduction=sick_deduction,
        note=sick_note,
    )
    scenario.transactions.append(TxEvent(
        date=pay_date,
        description=f"LÖN {profile.employer.upper()}",
        amount=Decimal(net_monthly),
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

    # ---------- Barn (om profilen har barn) ----------
    children_ages = list(getattr(profile, "children_ages", None) or [])
    for c_age in children_ages:
        if 1 <= c_age <= 5:
            # Förskola
            scenario.transactions.append(TxEvent(
                date=date(year, month, min(5, last_day)),
                description=f"FÖRSKOLEAVGIFT KOMMUN",
                amount=-Decimal(rng.randint(950, 1700)),
                category_hint="Barn",
            ))
        elif 6 <= c_age <= 12:
            # Fritids
            scenario.transactions.append(TxEvent(
                date=date(year, month, min(5, last_day)),
                description=f"FRITIDSAVGIFT KOMMUN",
                amount=-Decimal(rng.randint(450, 1100)),
                category_hint="Barn",
            ))
        if c_age >= 6 and rng.random() < 0.5:
            # Aktivitet (fotboll, dans osv)
            scenario.transactions.append(TxEvent(
                date=date(year, month, min(rng.randint(1, last_day), last_day)),
                description=id_rng.choice([
                    "FOTBOLLSKLUBB MEDLEMSAVG", "DANSSKOLA AVGIFT",
                    "MUSIKSKOLA AVGIFT", "SCOUT KÅR AVGIFT",
                ]),
                amount=-Decimal(rng.randint(250, 1200)),
                category_hint="Barn",
            ))
        if c_age <= 1 and rng.random() < 0.4:
            # Blöjor / barnutrustning
            scenario.transactions.append(TxEvent(
                date=date(year, month, rng.randint(1, last_day)),
                description="BARN APOTEKET HJÄRTAT",
                amount=-Decimal(rng.randint(450, 1200)),
                category_hint="Barn",
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
        # Använd aktuell månadsränta från InterestRateSeries när tillgängligt,
        # annars fall tillbaka till profilen-baserat slumpat värde
        rate = _lookup_mortgage_rate(year_month) or round(
            id_rng.uniform(0.038, 0.048), 4
        )
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

    # Mat — varje vecka. Skala upp för fler personer i hushållet enligt
    # Konsumentverkets siffror (ungefär +800 kr/månad per extra person).
    # Plus säsongsvariation (jul +30%, semester-sommar +10% osv).
    persons = (
        1 + (1 if getattr(profile, "partner_age", None) else 0)
        + len(children_ages)
    )
    m_idx = month - 1  # 0-11
    grocery_low, grocery_high = cp["groceries_per_week"]
    person_factor = 1.0 + (persons - 1) * 0.45
    season = SEASONAL_MULT["groceries"][m_idx]
    grocery_low = int(grocery_low * person_factor * season)
    grocery_high = int(grocery_high * person_factor * season)
    for week in range(4):
        day = rng.randint(1, last_day)
        amount = rng.randint(grocery_low, grocery_high)
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

    # Restaurang — säsongsmultiplikator (jul/sommar ökar)
    season_rest = SEASONAL_MULT["restaurant"][m_idx]
    n_rest_base = rng.randint(*cp["restaurant_per_month"])
    n_rest = int(round(n_rest_base * season_rest))
    for _ in range(n_rest):
        day = rng.randint(1, last_day)
        amount = int(rng.randint(95, 450) * season_rest)
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

    # Shopping — julshopping (dec +80%, nov +10%), sommar-utförsäljning
    season_shop = SEASONAL_MULT["shopping"][m_idx]
    n_shop_base = rng.randint(*cp["shopping_per_month"])
    n_shop = int(round(n_shop_base * season_shop))
    for _ in range(n_shop):
        day = rng.randint(1, last_day)
        merchant = rng.choice(MERCHANTS_SHOP)
        amount = int(rng.randint(199, 2900) * season_shop)
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
