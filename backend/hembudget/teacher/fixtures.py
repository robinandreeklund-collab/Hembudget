"""Pooler av handlare, fakturor och lån som datagenerator slumpar från.

Varje elev får distinkt data genom att seeden (student_id, year_month)
väljer olika kombinationer. Inte samma handlare, inte samma belopp,
inte samma fakturaleverantörer.
"""
from __future__ import annotations

# Kategori → lista av (handelsnamn, prisspann min-max)
MERCHANTS: dict[str, list[tuple[str, int, int]]] = {
    "Mat": [
        ("ICA Maxi Borås", 180, 1850),
        ("Willys Torpa", 150, 1400),
        ("Coop Forum", 200, 1600),
        ("Lidl Centralen", 100, 950),
        ("Hemköp", 80, 600),
        ("ICA Kvantum", 220, 2100),
        ("Willys Hemma", 60, 400),
    ],
    "Transport": [
        ("SL Access", 930, 970),
        ("Västtrafik Periodkort", 795, 825),
        ("Preem Bensin", 400, 1200),
        ("Circle K", 350, 1100),
        ("OKQ8", 380, 1050),
        ("SJ Biljett", 199, 1499),
    ],
    "Nöje": [
        ("Spotify Premium", 109, 139),
        ("Netflix", 99, 229),
        ("HBO Max", 99, 149),
        ("Viaplay", 139, 229),
        ("SF Bio", 129, 189),
        ("Systembolaget", 150, 850),
        ("Steam Games", 99, 599),
    ],
    "Hälsa": [
        ("Apoteket Hjärtat", 89, 499),
        ("Kronans Apotek", 79, 399),
        ("Apotek Hjärtat", 120, 650),
        ("Folktandvården", 350, 2400),
    ],
    "Shopping": [
        ("H&M", 199, 999),
        ("Zara", 299, 1499),
        ("Clas Ohlson", 89, 799),
        ("Jula", 79, 699),
        ("IKEA", 99, 2499),
        ("Elgiganten", 299, 4999),
        ("Biltema", 59, 599),
    ],
    "Restaurang": [
        ("Max Hamburgare", 89, 229),
        ("McDonald's", 75, 195),
        ("Sushi Yama", 139, 389),
        ("O'Learys", 189, 549),
        ("Espresso House", 45, 135),
        ("Pizza Hut", 129, 329),
    ],
    "Sport": [
        ("Stadium", 199, 1899),
        ("XXL Sport", 249, 2499),
        ("SATS Gym", 449, 649),
        ("Nordic Wellness", 299, 549),
    ],
}

# Fakturor med varierade intervall (UpcomingTransaction)
INVOICE_TEMPLATES: list[dict] = [
    {"name": "Hjo Energi", "category": "Hushåll", "min": 450, "max": 1850,
     "kind": "utility", "meter": "electricity"},
    {"name": "Vattenfall Elnät", "category": "Hushåll", "min": 280, "max": 950,
     "kind": "utility", "meter": "electricity"},
    {"name": "Fortum El", "category": "Hushåll", "min": 520, "max": 2100,
     "kind": "utility", "meter": "electricity"},
    {"name": "Telia Bredband", "category": "Hushåll", "min": 299, "max": 599,
     "kind": "invoice"},
    {"name": "Tele2 Bredband", "category": "Hushåll", "min": 279, "max": 549,
     "kind": "invoice"},
    {"name": "Com Hem", "category": "Hushåll", "min": 399, "max": 649,
     "kind": "invoice"},
    {"name": "Telenor Mobil", "category": "Hushåll", "min": 199, "max": 499,
     "kind": "invoice"},
    {"name": "Hyra Brf Solgården", "category": "Boende", "min": 4500, "max": 8500,
     "kind": "invoice"},
    {"name": "If Hemförsäkring", "category": "Försäkring", "min": 165, "max": 395,
     "kind": "invoice"},
    {"name": "Trygg Hansa Bil", "category": "Försäkring", "min": 450, "max": 850,
     "kind": "invoice"},
    {"name": "Radiotjänst", "category": "Hushåll", "min": 113, "max": 125,
     "kind": "invoice"},
]

# Lån-mallar
LOAN_TEMPLATES: list[dict] = [
    {"name": "Bolån Villa", "lender": "SBAB",
     "principal_range": (1_800_000, 3_500_000),
     "rate_range": (0.038, 0.046),
     "amort_pct_range": (0.01, 0.02),
     "binding": "rörlig", "category": "Huslån"},
    {"name": "Bolån Bostadsrätt", "lender": "SEB",
     "principal_range": (1_200_000, 2_800_000),
     "rate_range": (0.040, 0.048),
     "amort_pct_range": (0.01, 0.02),
     "binding": "3mån", "category": "Huslån"},
    {"name": "Billån", "lender": "Santander",
     "principal_range": (85_000, 280_000),
     "rate_range": (0.055, 0.085),
     "amort_pct_range": (0.025, 0.045),
     "binding": "rörlig", "category": "Billån"},
    {"name": "Studielån CSN", "lender": "CSN",
     "principal_range": (120_000, 450_000),
     "rate_range": (0.022, 0.031),
     "amort_pct_range": (0.005, 0.012),
     "binding": "rörlig", "category": "Studielån"},
    {"name": "Renoveringslån", "lender": "Länsförsäkringar",
     "principal_range": (50_000, 250_000),
     "rate_range": (0.065, 0.095),
     "amort_pct_range": (0.02, 0.05),
     "binding": "rörlig", "category": "Lån"},
]

# Arbetsgivare för löner
EMPLOYERS: list[tuple[str, int, int]] = [
    ("Ericsson AB", 28_000, 48_000),
    ("Volvo Cars", 26_000, 42_000),
    ("Spotify Sverige", 32_000, 58_000),
    ("IKEA Retail", 22_000, 38_000),
    ("H&M Group", 24_000, 40_000),
    ("Stockholms Stad", 25_000, 39_000),
    ("Region Västra Götaland", 26_000, 41_000),
    ("Scania CV", 27_000, 45_000),
]

# Startkonton som alla elever får
DEFAULT_ACCOUNTS = [
    {"name": "Lönekonto", "bank": "nordea", "type": "checking"},
    {"name": "Sparkonto", "bank": "nordea", "type": "savings"},
    {"name": "Kreditkort", "bank": "seb_kort", "type": "credit",
     "credit_limit": 40_000},
]
