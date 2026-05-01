# 05 · Arbetsförmedlingen + AI Mats

> Den **10:e aktören**. Realistisk svensk jobbmatchning med 5-rond
> intervju mot AI-rekryteraren Mats.

## Roll i ekosystemet

Arbetsförmedlingen kompletterar Maria (lönesamtal med befintlig
arbetsgivare) med **byte av jobb**. Två olika AI-personer för två
olika scenarier:

| Aktör | AI | Domän |
|---|---|---|
| Arbetsgivaren | Maria | Löneförhandling med nuvarande arbetsgivare |
| Arbetsförmedlingen | Mats | Söka och få nytt jobb |

## Jobbpoolen

Samma `yrkespool.py` som Profile Generator använder. Pool av ~150
jobb, varje med:

```yaml
- key: it_konsult_junior
  display: "IT-konsult, junior"
  ssyk: "2512"
  monthly_gross_min: 35000
  monthly_gross_median: 41000
  monthly_gross_max: 49000
  education_level: "yh"  # eller "hogskola"
  experience_years_required: 0-2
  competency_match: ["safety", "economy"]
  city_density:
    stockholm: 1.5
    göteborg: 1.2
    småort: 0.3
  match_score_keywords:
    - { skill: "javascript", weight: 0.8 }
    - { skill: "react", weight: 0.5 }
    - { skill: "teamwork", weight: 0.4 }
  collective_agreement: "almega_it"
  difficulty_at_level:
    1: 0.7   # 70% chans att lyckas
    2: 0.5
    3: 0.35
```

## Frekvens (slumpas i Event Engine)

| Hur eleven får jobbtips | Frekvens |
|---|---|
| **Auto från Arbetsförmedlingen** (via Event Engine) | 1.5/år (ca 1 gång på 8 mån) |
| **Aktivt sökande** (eleven öppnar) | När som helst, max 2 ansökningar/spelmånad |
| **Vid arbetslöshet** | 3–5 tips/månad |

## 5-rond intervjuflöde

### Rond 1 · CV + personligt brev

**Tid:** 1–2 dagar i spelet

**Vad eleven gör:**
- Granskar CV (auto-genererat från StudentProfile)
- Kan välja att lägga tid på personligt brev (slider: 30 min – 4 h)
- Mer tid → starkare intryck, men kostar fritid + relation-tid

**AI Mats sparar:**
- Bedömning av CV-matchning (auto-räknat)
- Kvalitet på personligt brev (baserat på elevens val)

**Pentagon-effekt:**
- Karriär +1 (har sökt något)
- Relation -1 om eleven valde > 2 h på brev
- Fritid -1 om eleven valde > 1 h

### Rond 2 · Telefonintervju

**Tid:** 1 dag i spelet · 4–5 frågor

**Frågor (slumpas från pool):**
- "Berätta om en gång du hanterat en konflikt"
- "Vad är dina svaga sidor?"
- "Varför vill du byta jobb just nu?"
- "Vad förväntar du dig för lön?"

**Eleven väljer ton (multi-choice):**
- Säker (+ karriär, kan tippa cocky)
- Reflekterande (balans)
- Anspråksfull (- karriär om för tidigt)
- Ärlig (+ social, kan vara naivt)

**Pentagon-effekt:**
- Hälsa -2 (stress innan + under)
- Karriär +1–3 beroende på prestation

### Rond 3 · Kompetenstest / case

**Tid:** 2 dagar

**Vad eleven får:**
- Mini-case som matchar yrket
  - IT-konsult: koda en algoritm-skiss
  - Sjuksköterska: prioritera 4 patienter
  - Säljare: pitch produkten i 60 ord
- Eller budget/beslut-test (för andra yrken)

**Bedöms av:**
- Mats AI går igenom svaret + ger feedback
- Score 1–10 syns för eleven (transparens)

**Pentagon-effekt:**
- Karriär +1–4 vid bra
- Karriär -2 + ekonomi -1 om eleven gav upp halvvägs

### Rond 4 · Intervju på plats / video

**Tid:** 1–2 dagar

**Förberedelse-val:**
- Klädsel: vardags / business casual / formell
- Förstudera företaget: 0 / 30 min / 2 h
- Resa till plats (kostnad om Stockholm-Småland t.ex.)

**Intervju:** AI Mats ställer 3–4 djupare frågor:
- "Var ser du dig själv om 5 år?"
- "Hur bidrar du till vår kultur?"
- "Vad gör du om en kollega inte gör sin del?"

**Pentagon-effekt:**
- Hälsa -2 till -4 (stress-topp)
- Relation -2 (energi-tom efter)
- Karriär +2–5 vid bra
- Eventuell resekostnad → ekonomi -50 till -1500

### Rond 5 · Erbjudande + löneförhandling

**Tid:** 1 dag

Två utfall:
- **AVSLAG**: Mats förklarar varför (transparent feedback) + tipsar om
  förbättringar för nästa gång
- **ERBJUDANDE**: Mats ger startbud → läsaren förhandlar (kopplas till
  befintlig Maria-motor men med Mats istället)

Vid erbjudande:
- 1–3 förhandlings-rundor (kortare än Maria, inte 5)
- Eleven kan acceptera, motbjuda eller avslå
- Förhandling inom yrkespool-spannet (kan inte be om dubbel median)

## Match-poäng (success rate)

Eleven får ett `match_score` 0–100 baserat på:

```python
def calculate_match_score(student, job):
    score = 0
    
    # Yrkes-kompetens
    student_competencies = compute_mastery_for_student(student.id)
    for skill, weight in job.match_score_keywords:
        cid = competency_lookup(skill)
        score += student_competencies.get(cid, 0) * weight * 30
    
    # Erfarenhet (proxy via tid på plattformen)
    weeks_active = (now - student.created_at).days / 7
    if job.experience_years_required[0] <= (weeks_active / 12):
        score += 20
    
    # Stad-match
    if student.city in job.preferred_cities:
        score += 15
    
    # Utbildningsnivå (placeholder, baseras på age + level)
    score += 15
    
    # Tidigare prestationer (om bytt jobb tidigare med bra utfall)
    score += previous_job_history_bonus(student) * 10
    
    return min(100, score)
```

`match_score` påverkar:
- Sannolikhet att eleven får erbjudande (rond 5)
- Lönen i erbjudandet (median ± offset baserat på score)

## Difficulty-skillnader

| Nivå | Effekt på Arbetsförmedlingen |
|---|---|
| 1 | Färre frågor, mildare bedömning, +30 % success rate |
| 2 | Normal |
| 3 | Tuffare frågor, hårdare bedömning, -25 % success rate |

Difficulty påverkar **inte** vilka jobb som finns i pool — bara hur
svårt det är att få dem.

## Begränsningar

- **Max 2 aktiva ansökningar** per spelmånad (cooldown)
- **24 h cooldown** mellan ronderna (i spel-tid, inte realtid)
- Eleven kan **avbryta** när som helst → kostar bara tid + lite
  wellbeing (relation/hälsa)

## Pentagon-konsekvenser av jobbyte

Vid byte (rond 5 = accepterat):

| Förändring | Pentagon |
|---|---|
| Ny lön högre än gammal | +5 ekonomi, +3 karriär |
| Ny lön lägre (medvetet val) | -2 ekonomi, +2 leisure (mindre stress) |
| Pendling längre | -3 leisure, -2 health |
| Pendling kortare | +2 leisure, +1 health |
| Flytta till annan stad | -8 social (initialt), +3 karriär |
| Trial-period (probation) 6 mån | -2 safety i 6 mån |

## Lärar-vy

I klass-hub:
- "Aktiva jobbintervjuer" — vilka elever är mitt i en runda
- "Avslutade senaste 30 dgr" — vem fick jobb, vem fick avslag

I `/teacher/v2/elev/:id`:
- Komplett intervju-historik per elev
- Vilka val eleven gjorde i varje rond
- Pedagogisk reflektion (vad lärde sig eleven?)

## Existerande system att återanvända

| Befintligt | Roll |
|---|---|
| `school::SalaryNegotiation` | Ärv strukturen för att lagra Mats-rundor |
| `school::NegotiationRound` | Per-rond data |
| `school::CollectiveAgreement` | Tillgängliga avtal kopplade till yrke |
| `school::ProfessionAgreement` | Yrket → avtal |
| `school::MarketSalaryRange` | Lönespann (utökas till alla yrken) |

## Implementation

```
backend/hembudget/game_engine/
  arbetsformedlingen/
    __init__.py
    pool.py                  # Yrkespool (delas med Profile Generator)
    matching.py              # match_score-beräkning
    interview_flow.py        # 5-rond state-machine
    mats_ai.py               # AI-prompts för Mats
    api.py                   # /v2/arbetsformedlingen/* endpoints
```

## Endpoints

| Metod | URL | Syfte |
|---|---|---|
| GET | `/v2/arbetsformedlingen/jobs` | Lista relevanta jobb för eleven |
| GET | `/v2/arbetsformedlingen/jobs/{key}` | Detalj-vy av jobb |
| POST | `/v2/arbetsformedlingen/apply/{key}` | Starta ansökan |
| GET | `/v2/arbetsformedlingen/applications` | Mina pågående ansökningar |
| POST | `/v2/arbetsformedlingen/applications/{id}/round` | Skicka rond-svar |
| POST | `/v2/arbetsformedlingen/applications/{id}/abandon` | Avbryt |

## Frontend-vy

Ny aktör i hub-kompassen: "**Arbetsförmedlingen**" med ikonen 🏢.

Sidan har:
- Jobblista (3–6 relevanta + sökfält för fler)
- Per jobb: yrke, lön, stad, match_score, "Sök →"
- Intervju-vy: state-machine UI med progress bar (1/5, 2/5...)
- Avslutade ansökningar (utfall, lärdomar)
