# 02 · Profile Generator

> Skapas en gång, vid skapelse. Resultatet är en deterministisk men
> realistisk svensk vuxen med yrke, lön, stad, boende, familj och
> initial pentagon.

## Steg 1 · Bas-input

| Input | Källa | Syfte |
|---|---|---|
| `teacher_id` | Inloggad lärare | Ägarskap |
| `seed` | Hash av (teacher_id, login_code) eller manuellt val | Determinism |
| `archetype` | Lärarens val eller "random" | Yrke-pool-filter |
| `partner_model` | "solo" / "ai" / "klasskompis" / "auto" | Familjestatus |
| `starting_level` | 1 / 2 / 3 (default 1) | Difficulty (ej ekonomi) |
| `name` | Lärarens fritext | display_name |

## Steg 2 · Slumpa yrke (från svenska 2026-pool)

**Yrkespool:** ~150 svenska yrken, byggd från SCB SSYK-2012 + Arbets-
förmedlingens 2026-prognos.

Per yrke:
```yaml
- key: undersköterska_vård
  ssyk: "5321"
  display: "Undersköterska, hemsjukvård"
  monthly_gross_min: 26500
  monthly_gross_median: 28800
  monthly_gross_max: 32200
  education_level: "gymnasium"  # gymnasium | yh | hogskola | doktor
  competency_match: ["health", "safety"]  # vilka kompetenser yrket bygger
  city_preference: ["stockholm", "göteborg", "medelstad", "småort"]
  weight_per_level: { 1: 1.0, 2: 0.8, 3: 0.5 }  # vanligare på nivå 1
  collective_agreement: "kommunal_vard"
  description: "Vårdar äldre eller sjuka i hemmet eller på boende."
  realistic_career_paths: ["specialistundersköterska", "sjuksköterska"]
```

**Slumpfunktion:**
1. Filtrera pool på `archetype` (om explicit) ELLER `starting_level` weight
2. Vikta efter regional-fördelning (60 % storstad, 30 % medelstad, 10 % småort)
3. Pick deterministisk via seed

## Steg 3 · Slumpa stad

**Stadspool:** Stockholm, Göteborg, Malmö, Uppsala, Linköping, Örebro,
Västerås, Norrköping, Gävle, Sundsvall, Umeå, Luleå + ~10 mindre orter.

Per stad:
```yaml
- key: stockholm
  display: "Stockholm"
  population: 990_000
  cost_multiplier_housing: 1.30   # 30% dyrare boende
  cost_multiplier_food: 1.05      # 5% dyrare mat
  cost_multiplier_transport: 1.15 # SL-kort etc
  job_density: 1.5                # fler jobb-tillgångar
  bostad_pct_brf: 0.55            # mest BRF
  bostad_pct_villa: 0.05          # få villor
  bostad_pct_hyresratt: 0.40
  avg_brf_price_2026: 78000       # kr/m² genomsnitt
  region: "Stockholm"
```

Stadsval drivs av:
- Yrkets `city_preference`
- Profilens "tycker om storstad / mindre" (slump)
- Lite spridning så inte alla hamnar i Stockholm

## Steg 4 · Slumpa boende (matchat mot lön)

**Regelverk (svenska normer 2026):**
- Boendekostnad max 30–35 % av nettolön (singel)
- Max 25 % vid familj med barn
- Max 40 % om eleven INTE har bil (avgör vid yrke som kräver bil)

**Boende-typer:**
```yaml
hyresratt:
  weight_per_income: { low: 0.7, mid: 0.5, high: 0.3 }
  monthly_cost_per_kvm: 100-180
  size_kvm_per_person: 30-45
  no_loan: true

bostadsratt:
  weight_per_income: { low: 0.2, mid: 0.4, high: 0.55 }
  buy_price_per_kvm: city_specific  # från cost_multiplier
  monthly_avgift: 30-90 / kvm / år (delas med 12)
  loan_required: true
  ltv_max: 0.85  # 15% kontantinsats
  amortering_rules: svenska 2025/2026

villa:
  weight_per_income: { low: 0.05, mid: 0.15, high: 0.30 }
  buy_price: city_specific
  driftkostnad: 4000-9000 kr/mån
  loan_required: true
  
radhus:
  weight_per_income: { low: 0.05, mid: 0.10, high: 0.20 }
```

**Algoritm:**
1. Räkna nettolön (via existerande `tax/_compute_net_salary`)
2. Beräkna max-boendekostnad (= 30 % × nettolön, eller 25 % om familj)
3. Filtrera boendetyper inom budget
4. Slumpa typ enligt vikter
5. Slumpa storlek + lägesfaktor inom typen
6. Beräkna månadskostnad + ev. lån

## Steg 5 · Slumpa familj

| Status | Sannolikhet | Effekt |
|---|---|---|
| Singel | 70 % | — |
| Sambo | 20 % | + partnerinkomst, delade utgifter |
| Familj med barn | 10 % | + barnbidrag, + barnomsorg, + matkostnad |

Vid sambo:
- Partner slumpas själv från yrkespoolen
- Partner-inkomst läggs till hushållsinkomst
- Partnermodell: AI (default), solo (sambo finns men ej spelbar), klasskompis

Vid barn:
- Antal barn 1–3 (vikt 60-30-10)
- Åldrar 0–18 år (slumpa)
- Konsumentverkets matkostnad-tabell per åldersgrupp
- Barnbidrag 1 250 kr/barn (2026)

## Steg 6 · Initial pentagon (variation per karaktär)

Baslinje för alla axlar = **60**.

Modifierare baserat på profil-fakta:

```python
def initial_pentagon(profile: StudentProfile) -> dict[str, int]:
    p = {"economy": 60, "safety": 60, "health": 60, "social": 60, "leisure": 60}
    
    # ECONOMY
    housing_pct = profile.housing_monthly / profile.net_salary
    if housing_pct > 0.35: p["economy"] -= 5
    if housing_pct > 0.40: p["economy"] -= 3
    if profile.has_student_loan: p["economy"] -= 3
    if profile.has_credit_card and profile.has_high_cost_credit: p["economy"] -= 5
    
    # SAFETY (karriär)
    if profile.competency_match_with_yrke: p["safety"] += 5
    if profile.collective_agreement: p["safety"] += 3
    if profile.is_temporary_employment: p["safety"] -= 5
    
    # HEALTH
    if profile.has_chronic_condition: p["health"] -= 3  # slumpas 10 %
    if profile.commute_minutes > 60: p["health"] -= 2
    if profile.has_health_insurance: p["health"] += 2
    
    # SOCIAL (relationer)
    if profile.family_status == "sambo": p["social"] += 5
    if profile.family_status == "familj_med_barn": p["social"] += 8
    if profile.family_status == "ensam" and profile.age > 30: p["social"] -= 3
    
    # LEISURE (fritid)
    if profile.commute_minutes > 60: p["leisure"] -= 4
    if profile.has_children: p["leisure"] -= 3
    if profile.budget_for_leisure < 1500: p["leisure"] -= 2
    
    # Klampa: ingen axel under 45 eller över 80 vid start
    return {k: max(45, min(80, v)) for k, v in p.items()}
```

**Slutresultat:** Total wellbeing 52–68 för 95 % av karaktärer. Ingen
startar i ett "omöjligt" läge.

## Steg 7 · Seeda scope-DB

När profilen är klar seedas elevens scope-DB med:

| Tabell | Rader | Källa |
|---|---|---|
| `Account` | Lönekonto + sparkonto + ISK + kreditkort | Standard |
| `Loan` | Bostadslån (om bostadsrätt/villa) + ev. CSN | Profil |
| `RentalContract` | Hyresavtal (om hyresrätt) | Profil |
| `Category` | Default-kategorier (Mat, Hyra, Restaurang...) | Standard |
| `MailItem` | Första månadens fakturor | Monthly Engine seed |
| `InsurancePolicy` | Eventuell hemförsäkring (om profil har den) | Profil |
| `UtilitySubscription` | El, mobil, bredband | Stad-default |

## Steg 8 · Lärarvy efter skapelse

Läraren ser:
- Bekräftelsekort (redan implementerat) med login-kod + QR
- Direktlänk till `/teacher/v2/elev/:id` där hela karaktären visas
- "Förhandsgranska" — impersonera direkt för att se elevens vy

## Avancerade lägen

### A. Klassrums-paritet
Lärare kan välja "**Jämn start**": alla elever får +/- 0 på pentagonen
oavsett profil-modifierare. Pedagogiskt val för rättvist start-läge.

### B. Manuell override
Lärare kan ändra `seed`, `archetype`, `partner_model` innan creation
för att få kontrollerade scenarion (t.ex. "skapa 5 IT-konsulter med
samma startvillkor för komparativ studie").

### C. Reroll
Innan eleven loggat in kan läraren "reroll:a" karaktären — ny seed,
samma display_name. Efter första login är karaktären låst (för
pedagogisk integritet).

### D. Twin-mode (forskning)
Två elever skapas med identisk seed → identisk karaktär. Lärare
jämför val över tid (perfekt för debattövningar).

## Implementation

```
backend/hembudget/game_engine/
  profile_generator/
    __init__.py
    yrkespool.py          # Pool med ~150 yrken (YAML eller Python-konstant)
    stadspool.py          # ~22 städer
    matcher.py            # Matchar lön/boende/stad
    pentagon_init.py      # Initial pentagon-beräkning
    seeder.py             # Skapar scope-DB-rader
    api.py                # Endpoint /v2/teacher/students/profile-preview
```

## Integration med existerande v2-create-endpoint

`POST /v2/teacher/students/create` (Fas 2X) utökas så att den
**efter Student-skapelse** anropar `profile_generator.generate(...)`
istället för dagens enkla `_create_profile_for_student`. Det betyder
att vi kan reroll:a och förhandsvisa innan vi commitar.

Ny endpoint: `POST /v2/teacher/students/profile-preview` som tar
samma input som `/create` men returnerar BARA den genererade profilen
(utan att skapa elev). Frontend kan visa förhandsvisning innan lärare
trycker "Skapa".
