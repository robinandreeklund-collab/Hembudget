# 07 · Pentagon-mekaniken

> Wellbeing-pentagonen är plattformens **starkaste USP** — och den
> mest känsliga att balansera. Här är formeln, trögheten, driften och
> målen.

## Befintligt

`backend/hembudget/wellbeing/calculator.py` räknar redan pentagonen
med 5 axlar och `WellbeingFactor`-poster. Spelmotorn utökar med:
- Tröghet (max-rörelse per månad)
- Drift (automatisk månadsvis justering)
- Mål (eleven sätter egna mål per axel)
- Klass-aggregering (snitt + tävling)

## Total wellbeing-formel

```python
def total_wellbeing(p):
    # Inte ett rakt snitt — ekonomi viktas något högre eftersom
    # det ÄR Ekonomilabbet. Men inte så mycket att andra axlar blir
    # irrelevanta.
    weights = {
        "economy": 0.25,
        "health": 0.20,
        "social": 0.20,
        "leisure": 0.20,
        "safety": 0.15,   # karriär
    }
    return round(
        sum(p[k] * w for k, w in weights.items())
    )
```

Exempel:
- Eleven på (60, 60, 60, 60, 60) → 60
- Eleven på (80, 50, 50, 50, 50) → 57 (ekonomi drar upp)
- Eleven på (50, 70, 70, 70, 70) → 64 (övriga balanserar)

## Tröghet (momentum)

Pentagonen kan **inte ändras hur mycket som helst per spelmånad**.
Detta hindrar:
- Yo-yo-effekter (ena dagen +20, andra dagen -20)
- "Spel-aktig" känsla
- Pedagogiskt nonsens (du kan inte ångra ett dåligt val på en månad)

```python
class AxisMomentum:
    max_change_per_event: int = 5      # Stort enskilt event
    max_change_per_day: int = 8        # Summerat över alla events
    max_change_per_month: int = 12     # Total drift + events
    
def apply_change(axis, requested_delta, current_state):
    # Klampa per event
    delta = max(-5, min(5, requested_delta))
    
    # Räkna ackumulerad förändring senaste 24 h
    accumulated_24h = sum_changes_last_24h(axis, current_state.events)
    if abs(accumulated_24h + delta) > 8:
        delta = sign(delta) * (8 - abs(accumulated_24h))
    
    # Räkna ackumulerad förändring senaste 30 dagar
    accumulated_30d = sum_changes_last_30d(axis, current_state.events)
    if abs(accumulated_30d + delta) > 12:
        delta = sign(delta) * (12 - abs(accumulated_30d))
    
    return current_state.value + delta
```

## Drift (automatisk månadsvis justering)

Vid varje månads-tick läggs en automatisk drift på, baserad på
elevens **balans**:

```python
def monthly_drift(student, year_month):
    """
    Drift är resultatet av val ELLER icke-val.
    Att inte göra något är också ett val.
    """
    drift = {axis: 0 for axis in AXES}
    
    # ECONOMY-drift
    save_rate = month_savings(student, year_month) / month_income
    if save_rate >= 0.20: drift["economy"] += 2
    elif save_rate >= 0.10: drift["economy"] += 1
    elif save_rate < 0: drift["economy"] -= 3
    
    if has_unpaid_bills(student): drift["economy"] -= 2
    if has_active_savings_goal(student): drift["economy"] += 1
    
    # HEALTH-drift
    if had_dentist_within_year(student): drift["health"] += 1
    if has_unpaid_health_bills(student): drift["health"] -= 2
    if month_alcohol_categorizations > 8: drift["health"] -= 2
    
    # SAFETY-drift (karriär)
    if month_competency_progressions >= 1: drift["safety"] += 2
    if month_module_steps_done >= 3: drift["safety"] += 1
    if has_active_negotiation(student): drift["safety"] += 1
    elif months_since_active_negotiation > 12: drift["safety"] -= 2
    
    # SOCIAL-drift
    if unread_teacher_feedback >= 5: drift["social"] -= 2
    if engaged_dialog_count >= 3: drift["social"] += 2
    if peer_review_given(student, year_month): drift["social"] += 1
    
    # LEISURE-drift (balans!)
    leisure_pct = leisure_spend / total_spend
    if 0.10 <= leisure_pct <= 0.20: drift["leisure"] += 1   # Sweet spot
    elif leisure_pct < 0.05: drift["leisure"] -= 2          # Allt jobb
    elif leisure_pct > 0.30: drift["leisure"] -= 2          # Slöseri
    
    # Klampa drift max ±5 per axel per månad
    return {k: max(-5, min(5, v)) for k, v in drift.items()}
```

## Initial pentagon-variation

Beskriven i [`02-profile-generator.md`](./02-profile-generator.md). 
Sammanfattning:
- Baslinje 60 per axel
- Modifierare baserat på profil-fakta (singel, sambo, dyrt boende osv)
- Klamp 45–80 per axel
- Total wellbeing 52–68 vid start för 95 % av karaktärer

## Mål-system

Eleven kan sätta egna mål per axel:

```python
class WellbeingGoal(MasterBase):
    student_id: int
    axis: str           # "economy" | "health" | ...
    target_value: int   # 0-100
    deadline: date
    set_at: datetime
    achieved: bool      # auto när axis_value >= target i 14 dgr
    motivation: str | None
```

Echo coachar mot målen:
- "Du har 5 dagar kvar tills ditt mål 'Hälsa över 70'. Aktuell: 67."
- "Du nådde ditt mål — bra jobbat! Vill du sätta ett nytt?"

Lärar-vyn ser elevens mål och kan tilldela "klass-mål" (alla elever
ska nå hälsa 70 till v 12).

## Klass-aggregering

`/v2/teacher/klass-overview` aggregerar redan klass-pentagon (snitt
över alla elever). Utökas med:

- **Klass-tävling**: två klasser kan jämföras (skole-nivå)
- **Trend-pilar**: senaste månadens utveckling per axel
- **Outliers**: elever som drar upp/ner snittet (Fas 2AH redan)

## Wellbeing-event-loggen

Varje pentagon-förändring loggas:

```python
class WellbeingEvent(MasterBase):
    student_id: int
    occurred_at: datetime
    axis: str
    delta: int
    reason_kind: str    # "event" | "drift" | "decision" | "goal_achieved"
    reason_id: int      # Referens till MailItem, Module, etc
    explanation: str    # Människo-läsbar
```

Detta är spårbarheten — varför gick "Hälsa" ner från 65 till 58?
Svaret syns på `/v2/pentagon/axis/health` med klick.

## Echo-minne (3–4 spelmånader)

Echo behöver komma ihåg vad som har hänt:

```python
class EchoMemory(MasterBase):
    student_id: int
    memory_kind: str      # "wellbeing_trend" | "decision" | "missed_opportunity"
    summary: str          # "Bytt jobb 2 ggr på 6 mån"
    importance: int       # 1-10
    relevant_axis: str | None
    expires_at: datetime  # 4 spelmånader = ~28 d realtid
    referenced_count: int # Hur ofta Echo har refererat
```

Vid Echo-konversation: ladda relevanta minnen → väv in i prompten.

Exempel: Eleven byter jobb 2:a gången på 6 mån. Echo kommer ihåg
första bytet och säger:
> "Du bytte också för 4 spelmånader sen. Vad hindrar dig från att
> stanna? Är det rätta jobbet du söker, eller flyr du något?"

## Lärar-bedömning av wellbeing

Lärare kan **inte** direkt ändra wellbeing-värden — det skulle bryta
spårbarheten. Men de kan:
- Höja kompetenser manuellt (Fas 2AG) → indirekt effekt på safety
- Skicka uppdrag som ger pedagogisk effekt
- Se hela event-loggen och förklara
- Lägga till anteckningar (för bedömning, inte mekanik)

## Implementation

```
backend/hembudget/game_engine/
  pentagon/
    __init__.py
    formula.py             # total_wellbeing + per-axis weights
    momentum.py            # Tröghet/clamping
    drift.py               # Månatlig drift-beräkning
    goals.py               # WellbeingGoal CRUD
    echo_memory.py         # EchoMemory CRUD
    wellbeing_event.py     # Logg per förändring
```

## Frontend-utökningar

Vy `/v2/pentagon/axis/{axis}` (Fas 2Z) utökas med:
- "Mina mål för denna axel" (eleven kan sätta nya)
- "Echo har minne av X relevanta händelser"
- Tröghets-info: "Senaste månadens rörelse: -3 (max -12)"
