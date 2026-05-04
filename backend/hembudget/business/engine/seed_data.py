"""Seed-data för spelmotorn: branscher, kunder, jobbmallar.

Spec: deb/README.md avsnitt 4 (Customer/JobOpportunity) + avsnitt 14
("hand-skrivna kunder ger pedagogisk kontroll").

Hybrid-modell: vi har 3-5 grundkunder + 4-6 jobbmallar per bransch.
Pipeline_generator drar ur dessa mallar deterministiskt baserat på
(company_id, week_no).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CustomerSeed:
    name: str
    segment: str            # privat | foretag | kommun
    price_sensitivity: float  # 0..1 (1 = väldigt priskänslig)
    quality_sensitivity: float  # 0..1
    payment_morality: float  # 0..1 (1 = betalar i tid)


@dataclass
class JobTemplate:
    title: str
    description: str
    base_price: int          # SEK exkl moms · justeras av pricing-modul
    delivery_days: int
    industry_tag: str


# === Branschpooler ===
#
# Varje bransch har sin kundpool + jobbmall-pool. Eleven seedar
# "industry_label" på Company → vi vet vilken bransch att dra ur.
# "default" används som fallback om industrin inte är mappad.


HANTVERK_CUSTOMERS = [
    CustomerSeed("Familjen Lindqvist", "privat", 0.55, 0.6, 0.95),
    CustomerSeed("BRF Solrosen", "foretag", 0.7, 0.5, 0.9),
    CustomerSeed("Petra Hansson", "privat", 0.45, 0.7, 0.95),
    CustomerSeed("Företaget Bygg & Bo AB", "foretag", 0.6, 0.55, 0.85),
    CustomerSeed("Kommunens fastighetsförvaltning", "kommun", 0.8, 0.4, 0.99),
]

HANTVERK_JOBS = [
    JobTemplate("Måla ett rum", "Vardagsrum 18 kvm, två fönster.", 8000, 5, "hantverk"),
    JobTemplate("Lägga klinker i badrum", "Helkaklat badrum 6 kvm.", 22000, 12, "hantverk"),
    JobTemplate("Bygga altan 12 kvm", "Trä, två trappsteg.", 35000, 21, "hantverk"),
    JobTemplate("Reparera trasigt staket", "20 m längd, byta 6 stolpar.", 6500, 4, "hantverk"),
    JobTemplate("Tapetsera hall + trappa", "Halv-stor villa, ca 30 kvm väggyta.", 12000, 7, "hantverk"),
    JobTemplate("Plåtarbete på garage", "30 kvm tak, ny taklist.", 28000, 14, "hantverk"),
]

IT_CUSTOMERS = [
    CustomerSeed("Helena Sjöberg", "privat", 0.4, 0.8, 0.92),
    CustomerSeed("Café Sol & Måne", "foretag", 0.65, 0.6, 0.88),
    CustomerSeed("Tandläkarmottagningen Vita Leendet", "foretag", 0.5, 0.75, 0.95),
    CustomerSeed("Anders Karlsson", "privat", 0.35, 0.85, 0.93),
    CustomerSeed("Föreningen Fritidsbåtar Östermalm", "foretag", 0.55, 0.65, 0.9),
]

IT_JOBS = [
    JobTemplate("Bygga enkel webbplats", "5-sidor, kontaktformulär, mobilanpassad.", 12000, 7, "it"),
    JobTemplate("WordPress-installation + tema", "Installera + 3 anpassningar + utbildning 1 h.", 6500, 3, "it"),
    JobTemplate("Sätta upp e-handelsbutik", "Shopify-baserad, 20 produkter, betalning + frakt.", 25000, 14, "it"),
    JobTemplate("Felsökning slö dator", "Hembesök, rensa virus + uppdatera, backup.", 1500, 1, "it"),
    JobTemplate("Konfigurera nytt kontor-nätverk", "5 datorer, WiFi, skrivare, säkerhet.", 9000, 5, "it"),
    JobTemplate("Digitalisera bokföring + integration", "Visma/Fortnox + bank, 3 månaders historik.", 18000, 12, "it"),
]

CAFE_CUSTOMERS = [
    CustomerSeed("Walk-in-kund", "privat", 0.7, 0.5, 1.0),
    CustomerSeed("Företaget Konsult & Co", "foretag", 0.55, 0.6, 0.92),
    CustomerSeed("Skolan Norra", "kommun", 0.85, 0.4, 0.99),
    CustomerSeed("Föreningen Friluftsliv", "foretag", 0.65, 0.55, 0.88),
]

CAFE_JOBS = [
    JobTemplate("Catering till möte", "20 personer, smörgåstårta + dryck + kaffe.", 4200, 3, "cafe"),
    JobTemplate("Veckomeny för lunchgäster", "5 dagars meny, 80 portioner/dag.", 14000, 5, "cafe"),
    JobTemplate("Födelsedagstårta beställning", "12 personer, dekoration anpassad.", 850, 2, "cafe"),
    JobTemplate("Frukostarrangemang för konferens", "30 pers, frallor, kaffe, juice.", 2400, 1, "cafe"),
    JobTemplate("Specialbeställning bröllopstårta", "60 personer, 3-vånings.", 6500, 7, "cafe"),
]

KONSULT_CUSTOMERS = [
    CustomerSeed("Familjen Forss", "privat", 0.45, 0.7, 0.93),
    CustomerSeed("Studio Kreativa AB", "foretag", 0.6, 0.65, 0.88),
    CustomerSeed("Region Mellan", "kommun", 0.75, 0.5, 0.99),
    CustomerSeed("Startup Foodie", "foretag", 0.55, 0.7, 0.85),
]

KONSULT_JOBS = [
    JobTemplate("Strategisession halvdag", "4 h workshop, dokumenterad.", 9500, 2, "konsult"),
    JobTemplate("Marknadsanalys ny produkt", "Konkurrensbild, SWOT, 8-sidig rapport.", 18000, 14, "konsult"),
    JobTemplate("Coaching-pakat 5 sessioner", "1 h/v, fokus karriärbyte.", 7500, 35, "konsult"),
    JobTemplate("Föredragshållning konferens", "45 min föredrag + Q&A, anpassat innehåll.", 12000, 7, "konsult"),
    JobTemplate("Säljträning för team", "2 dagar, 8 säljare, övningsinslag.", 24000, 10, "konsult"),
]

KREATIV_CUSTOMERS = [
    CustomerSeed("Erika Linder", "privat", 0.5, 0.75, 0.92),
    CustomerSeed("Galleri Norrlandet", "foretag", 0.7, 0.6, 0.88),
    CustomerSeed("Förlaget BokKraft", "foretag", 0.55, 0.7, 0.92),
    CustomerSeed("Familjen Berg", "privat", 0.6, 0.65, 0.93),
]

KREATIV_JOBS = [
    JobTemplate("Logotypdesign", "3 förslag + 2 revideringar.", 5500, 7, "kreativ"),
    JobTemplate("Bröllopsfotografering", "6 timmar, 200 redigerade bilder.", 18000, 14, "kreativ"),
    JobTemplate("Bildillustration för bok", "10 färgbilder, A5, full upphovsrätt.", 22000, 21, "kreativ"),
    JobTemplate("Filmproduktion intervju", "1 dags inspelning + redigering 5 min.", 14000, 10, "kreativ"),
]

EHANDEL_CUSTOMERS = [
    CustomerSeed("Direktkund online", "privat", 0.7, 0.55, 0.97),
    CustomerSeed("Återförsäljare Norden", "foretag", 0.6, 0.7, 0.9),
    CustomerSeed("Föreningen Trail Run", "foretag", 0.6, 0.6, 0.88),
]

EHANDEL_JOBS = [
    JobTemplate("Bulkorder hoodies med tryck", "50 st, custom design.", 18000, 14, "ehandel"),
    JobTemplate("Order specialprodukt", "Premium-version, custom färg.", 1850, 5, "ehandel"),
    JobTemplate("Sponsringsorder klubb", "30 st rea-produkter med klubblogo.", 9500, 10, "ehandel"),
]

DEFAULT_CUSTOMERS = [
    CustomerSeed("Anna Persson", "privat", 0.5, 0.6, 0.93),
    CustomerSeed("Företaget X AB", "foretag", 0.65, 0.55, 0.88),
    CustomerSeed("Lokala kommunen", "kommun", 0.8, 0.45, 0.99),
]

DEFAULT_JOBS = [
    JobTemplate("Standarduppdrag", "Generiskt jobb, ingen branschmappning.", 6000, 7, "default"),
    JobTemplate("Större projekt", "Generiskt projekt, längre leveranstid.", 18000, 14, "default"),
]


# === Mappningstabell · industry_label → (customers, jobs) ===

INDUSTRY_POOLS: dict[str, tuple[list[CustomerSeed], list[JobTemplate]]] = {
    "hantverk": (HANTVERK_CUSTOMERS, HANTVERK_JOBS),
    "it": (IT_CUSTOMERS, IT_JOBS),
    "it-tjanster": (IT_CUSTOMERS, IT_JOBS),
    "cafe": (CAFE_CUSTOMERS, CAFE_JOBS),
    "konsult": (KONSULT_CUSTOMERS, KONSULT_JOBS),
    "kreativ": (KREATIV_CUSTOMERS, KREATIV_JOBS),
    "kreativ-tjanst": (KREATIV_CUSTOMERS, KREATIV_JOBS),
    "ehandel": (EHANDEL_CUSTOMERS, EHANDEL_JOBS),
    "e-handel": (EHANDEL_CUSTOMERS, EHANDEL_JOBS),
}


def industry_pool(
    industry_label: str | None,
) -> tuple[list[CustomerSeed], list[JobTemplate]]:
    """Hämta (customers, jobs) för en bransch. Default om ej hittad.

    Vi normaliserar (lowercase + ersätt mellanslag/streck) innan lookup
    så att 'IT-tjänster', 'IT tjänster' och 'it' alla matchar samma pool.
    """
    if industry_label is None:
        return DEFAULT_CUSTOMERS, DEFAULT_JOBS
    key = industry_label.lower().replace(" ", "-").replace("ä", "a").replace("ö", "o").replace("å", "a")
    if key in INDUSTRY_POOLS:
        return INDUSTRY_POOLS[key]
    # Fallback · matcha på första segment (t.ex. 'it-konsult' → 'it')
    head = key.split("-")[0]
    if head in INDUSTRY_POOLS:
        return INDUSTRY_POOLS[head]
    return DEFAULT_CUSTOMERS, DEFAULT_JOBS
