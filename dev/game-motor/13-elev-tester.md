# 13 · Elev-tester · veckotest med karaktärs-baserade frågor

> Hur vi vet att eleven faktiskt **lär sig** (inte bara navigerar
> appen). Lärar-utskickade tester med frågor genererade från
> elevens unika karaktär — svåra att fuska med AI eller Google.

## Varför

Idag har vi:
- Wellbeing-pentagonen som speglar val (men inte kunskap)
- Modul-quiz-steg (men begränsade till modulinnehåll)
- Reflektioner (subjektiva, inte testbara fakta)
- Lärar-bedömning (manuellt, inte skalbart)

**Det vi saknar:** Systematisk validering att eleven förstår
ekonomin **i sin egen karaktärs kontext**. Just det är det centrala
pedagogiska målet.

## Tre-pelare-strategi

```
            ┌─────────────────────────┐
            │  Veckans test (15 min)  │
            └──────────┬──────────────┘
                       │
       ┌───────────────┼───────────────┐
       ▼               ▼               ▼
  ┌─────────┐    ┌─────────┐    ┌─────────┐
  │ Uppdrag │    │ Moduler │    │ Karaktär│
  │ -frågor │    │ -frågor │    │ -frågor │
  └─────────┘    └─────────┘    └─────────┘
   (5 poäng)     (5 poäng)      (10 poäng)
```

Karaktärs-frågorna har högst vikt eftersom de **kan inte besvaras
med AI eller sökning** — de kräver kunskap om elevens eget yrke,
egen lön, egen budget, egen karaktärsprofil.

## Test-struktur

### A · Uppdrags-baserade frågor (5 p)

Hämtas från uppdrag eleven fått senaste 1–2 spelmånader.

Exempel om uppdraget var "Räkna KALP för 2,4 Mkr-bolån":
- "Vad var KALP-resultatet du räknade fram för bolånet?"
- "Vilken månadskostnad gav du för räntor + amortering?"
- "Skulle du rekommendera bunden eller rörlig ränta i ditt
  scenario? Varför?"

Validering:
- Numeriska svar matchas mot KALP-modellens exakta beräkning för
  ELEVENS scope-DB
- Open-text-svar bedöms av lärare manuellt (eller AI-bedömt om
  kvalitet är acceptabel)

### B · Modul-baserade frågor (5 p)

Hämtas från moduler eleven har genomfört. Befintliga `quiz`-steg
återanvänds, men randomiseras.

Exempel om eleven gjort "ISK-modulen":
- "Vid 50 000 kr på ISK och 0,89 % schablonskatt — vad blir
  årets skatt?"
- "Vilket av följande är BÄST för långsiktigt sparande?"
  (flerval)

Validering: Quiz-svaren har rätt-svar i modul-data → auto-rättas.

### C · Karaktärs-baserade frågor (10 p) ⭐

**Det här är kärnan — anti-fusk genom personalisering.**

Frågorna genereras från elevens **konkreta karaktärsdata**:

```python
def generate_character_questions(student: Student) -> list[Question]:
    profile = get_student_profile(student.id)
    scope = get_scope_state(student.id)
    
    questions = []
    
    # FRÅGA 1: Lön + skatt
    questions.append({
        "kind": "numeric",
        "text": (
            f"Du tjänar {profile.gross_salary_monthly:,} kr brutto per "
            f"månad som {profile.profession}. Hur mycket netto får du "
            f"ut, ungefär? (svara i tusental, ex 24 för 24 000 kr)"
        ),
        "answer_min": int(profile.net_salary_monthly / 1000) - 2,
        "answer_max": int(profile.net_salary_monthly / 1000) + 2,
        "explanation": (
            f"Din nettolön är {profile.net_salary_monthly:,} kr. "
            f"Skatten är {profile.tax_rate_effective:.0%} effektivt."
        ),
    })
    
    # FRÅGA 2: Boende-procent
    housing_pct = profile.housing_monthly / profile.net_salary_monthly * 100
    questions.append({
        "kind": "numeric",
        "text": (
            f"Du bor i en {profile.housing_type} på {profile.housing_kvm} "
            f"kvm i {profile.city}. Boendekostnaden är "
            f"{profile.housing_monthly:,} kr/mån. Hur många procent av "
            f"din nettolön går till boendet?"
        ),
        "answer_min": int(housing_pct) - 3,
        "answer_max": int(housing_pct) + 3,
    })
    
    # FRÅGA 3: Pentagon-koppling
    weakest_axis = min(scope.pentagon, key=lambda k: scope.pentagon[k])
    questions.append({
        "kind": "multi_choice",
        "text": (
            f"Just nu är din svagaste pentagon-axel {weakest_axis} "
            f"med värdet {scope.pentagon[weakest_axis]}/100. Vilket av "
            f"följande val skulle ÖKA den axeln mest?"
        ),
        "options": _generate_axis_specific_options(weakest_axis),
        "correct_idx": _correct_axis_choice(weakest_axis),
    })
    
    # FRÅGA 4: Faktiska transaktioner
    last_month_top_category = get_top_spending_category(scope, last_month)
    questions.append({
        "kind": "multi_choice",
        "text": (
            f"Förra spelmånaden spenderade du mest pengar på en "
            f"kategori. Vilken?"
        ),
        "options": ["Mat", "Restaurang", "Kläder", "Boende", "Transport"],
        "correct_idx": _category_index(last_month_top_category),
    })
    
    # FRÅGA 5: Budget vs utfall
    over_budget_cat = find_over_budget_category(scope, last_month)
    if over_budget_cat:
        questions.append({
            "kind": "open_short",
            "text": (
                f"Du gick över budget i kategorin '{over_budget_cat.name}' "
                f"med {over_budget_cat.over_amount} kr förra månaden. "
                f"Beskriv kort EN åtgärd du kan göra för att hålla "
                f"budgeten nästa månad."
            ),
            "validation": "ai_or_teacher",
        })
    
    return questions
```

**Varför är detta svår-fuskat?**
- Frågan refererar till elevens UNIKA siffror (lön, boende, kvm, stad)
- Svaret är räknebart men kräver att man **vet sin egen karaktär**
- AI/Google kan inte gissa elevens exakta nettolön, boendekostnad,
  eller månadens högst-utgift-kategori
- En klasskompis som hjälper måste ha tillgång till exakt samma data
  → enklare att se om de bara blivit tillsagda svaret

## Test-flöde

```
1. Lärare bygger test-mall i v2-modulbiblioteket:
   - Väljer "Veckans test" eller "Stort prov"
   - Anger antal frågor per pelare (ex 3+3+5)
   - Sätter deadline + tidsgräns (t.ex. 20 min)
   
2. Lärare skickar ut testet:
   - Per elev (individuell) eller hela klassen
   - Backend genererar UNIKA frågor per elev från ovanstående logik
   - MailItem skapas i postlådan med kind="test"
   
3. Eleven öppnar testet:
   - Stilren UI · timer + progress
   - En fråga åt gången · ingen "tillbaka"-knapp
   - Aktivitet loggas (klickbeteende, tid per fråga)
   
4. Vid inlämning:
   - Auto-rättning av numeric + multi_choice
   - Open-text → kö för lärar-bedömning
   - Direkt feedback på rättade frågor (rätt/fel + förklaring)
   
5. Lärare ser:
   - Per elev: poäng, tid, fel-fördelning
   - Per fråga: hur stor andel av klassen klarade
   - Identifierar luckor: "60 % missade lön/skatt-frågan → vi behöver
     mer fokus på det"
```

## Datamodeller

### `master::TestTemplate`

```python
class TestTemplate:
    id: int (PK)
    teacher_id: int
    title: str                       # "Veckans test v 18"
    description: str
    questions_per_pillar: dict       # {"uppdrag": 3, "modul": 3, "karaktar": 5}
    pillar_weights: dict             # {"uppdrag": 5, "modul": 5, "karaktar": 10}
    time_limit_minutes: int
    randomize_order: bool
    allow_review_after: bool         # Får eleven se rätta svar efter?
    created_at: datetime
```

### `master::StudentTest`

```python
class StudentTest:
    id: int (PK)
    template_id: int (FK)
    student_id: int (FK)
    issued_at: datetime              # När läraren skickade
    deadline: datetime
    started_at: datetime | None
    submitted_at: datetime | None
    status: str                      # "issued" | "started" | "submitted" | "expired"
    auto_score: float                # Auto-bedömt
    teacher_score: float | None      # Lärarens manuella poäng
    final_score: float | None        # Sammanlagt
    questions_seed: int              # Determinism för regeneration
```

### `master::StudentTestQuestion`

```python
class StudentTestQuestion:
    id: int (PK)
    test_id: int (FK)
    question_idx: int                # 1, 2, 3...
    pillar: str                      # "uppdrag" | "modul" | "karaktar"
    kind: str                        # "numeric" | "multi_choice" | "open_short"
    text: str                        # Frågan (genererad från karaktärsdata)
    options: list[str] | None        # för multi_choice
    correct_answer: dict             # {"min": 23, "max": 27} eller {"idx": 2}
    explanation: str                 # Visas efter
    student_answer: str | None
    is_correct: bool | None
    points_awarded: float | None
    teacher_comment: str | None
```

## Anti-fusk-strategier

| Strategi | Hur det funkar |
|---|---|
| **Personaliserad data** | Frågor baseras på elevens unika karaktärsdata |
| **Tidsbegränsning** | 20 min hindrar att eleven hinner Googla allt |
| **Slumpad ordning** | Två elever ser inte samma frågor i samma ordning |
| **Engångs-snapshot** | Frågor genereras vid utskick, inte vid öppning (kan inte refresha för nya) |
| **Aktivitets-logg** | Tid per fråga + klick-beteende (klassrums-lärare ser om någon "fastnade" på Google) |
| **Variation över tid** | Varje vecka annan slumpad subset av karaktärs-frågorna |

## AI-genererade frågor (Fas 2)

För `open_short`-bedömning:
- Lärare granskar manuellt eller AI-bedömt
- AI-promten innehåller: korrekt svar (ledtråd), elevens svar,
  kontext om karaktären
- Returnerar: poäng + motivation
- Lärare kan override AI-bedömningen

För `multi_choice`-options:
- AI kan generera distraktorer (felaktiga men plausibla
  alternativ) baserat på elevens karaktär
- Säkerställer att rätt svar inte alltid är "Det realistiska"

## Pentagon-konsekvenser

| Resultat | Pentagon-effekt |
|---|---|
| Test 90 %+ | +3 safety |
| Test 70-89 % | +1 safety |
| Test < 50 % | -2 safety, -1 social (eleven vet att hen kämpar) |
| Test missat (deadline passerade) | -3 safety |
| Test inlämnat 5 min innan deadline | -1 leisure (stress) |

## Lärar-vyer

### `/teacher/v2/tester` (ny vy)

- Lista alla skapade test-mallar
- Per mall: skicka till klass / specifik elev
- Per utskickat test: status per elev (gjord / pågår / missad)
- Klick → detalj-vy med alla elevers svar

### `/teacher/v2/elev/:id/tester` (utökning av elev-detalj)

- Per-elev test-historik
- Genomsnittlig poäng senaste 3 mån
- Trend-pil (förbättras / försämras)

## Elev-vyer

### `/v2/test/:test_id` (ny vy)

- Welcome-skärm: "Test från [lärare] · 11 frågor · 20 min"
- Per fråga: text + svarsfält + "nästa →"
- Progress bar
- Timer
- Submit → resultat-skärm

### `/v2/postladan` får nu test-typer

Befintlig MailItem-modellen utökas med `mail_type="test"` (eller ny
domän — kanske TestNotification).

## Implementation-fas

Detta byggs som **Fas 9 · Elev-tester** efter Monte Carlo (Fas 8):

| Sub-fas | Innehåll |
|---|---|
| 9.1 | Datamodeller (TestTemplate, StudentTest, StudentTestQuestion) |
| 9.2 | Frågegenerator-motor (pillarna ovan) |
| 9.3 | Lärar-vy: skapa mall + skicka |
| 9.4 | Elev-vy: ta testet |
| 9.5 | Auto-rättning + lärar-rättning av open-text |
| 9.6 | Pentagon-koppling vid resultat |
| 9.7 | Integrationen i postlådan |
| 9.8 | Anti-fusk-mätningar (tid per fråga, etc) |

## Pedagogiska forskningsfrågor

- Är 11 frågor per vecka för mycket / för lite?
- Vilken vikt-fördelning lär bäst (3+3+5 eller 2+2+7)?
- Hur värdefullt är det att eleven får se sina rätta svar efter?
- Bör testet vara tvingande eller frivilligt?

Dessa testas under pilot-perioden med lärar-feedback.

## Referenser till befintliga system

| Befintligt | Roll |
|---|---|
| `Module` + `ModuleStep` (kind="quiz") | Källa för B-pelare |
| `Assignment` | Källa för A-pelare |
| `StudentProfile` | Källa för C-pelare (karaktärsdata) |
| `MailItem` | Bärare av test-notifikationen |
| `WellbeingEvent` | Mottagare av test-resultats-effekter |
| `StudentActivity` | Audit av test-aktivitet |
