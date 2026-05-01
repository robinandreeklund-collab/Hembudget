# 09 · Difficulty Levels

> Tre nivåer (Sparsam · Balanserad · Slösa) som **inte rör ekonomin**
> men ändrar tempo och svårighetsgrad.

## Princip

Karaktären är **identisk ekonomiskt** från start på alla tre nivåer.
Samma yrke, samma lön, samma boende, samma försäkringskostnader.

Det som skiljer är **vad som händer efter starten**:

| Parameter | Nivå 1 (Sparsam) | Nivå 2 (Balanserad) | Nivå 3 (Slösa) |
|---|---|---|---|
| Startlön & boende | Identiskt | Identiskt | Identiskt |
| Försäkringskostnader | Identiska | Identiska | Identiska |
| Antal events/månad | 0–1 | 1–2 | 2–3 |
| Event-svårighet | Mest milda/positiva | Blandat | Fler stora negativa |
| Faktura-variation | ±5 % | ±12 % | ±20 % |
| Jobbintervju success | +30 % chans | Normal | -25 % chans |
| Wellbeing-tröghet | Snabb återhämtning | Normal | Långsam återhämtning |
| Echo-hjälp | Mer direkt vägledning | Normalt | Minimalt stöd |
| Antal stora beslut | Färre | Normalt | Fler |

## Varför inte rör ekonomin?

Att höja eller sänka startlön baserat på nivå skulle:
- Förvirra lärare (varför har Sara A. nivå 1 25k men Hassan nivå 3 50k?)
- Bryta jämförbarhet mellan klasser
- Bli pedagogiskt orättvist (svaga elever får sämre lön → mindre att räkna med)

Istället är logiken: **alla får en realistisk vuxen-lön**, men hur
turbulent vardagen är runt den lönen varierar.

## Visualisering för läraren

I `/teacher/v2/skapa` (befintligt) väljer läraren:
- ▰▱▱ Nivå 1 · Sparsam (default · alla börjar här)
- ▰▰▱ Nivå 2 · Balanserad (om elev har lite mer erfarenhet)
- ▰▰▰ Nivå 3 · Slösa (specialfall · för avancerade scenarion)

I aktivera-nivå-modalen (Fas 2AG):
> "Vid aktivering: Sara behåller karaktären (samma yrke, lön, bostad)
> men får svårare ekonomi. Spendprofilen byts till Balanserad. Fler
> oväntade brev. Restaurang-budget överskrids oftare. Sambo-utgifter
> delas annorlunda."

## Spendprofilens roll

Varje nivå mappas till en spendprofil:
- Nivå 1 → "sparsam" (multiplikator 0.85 på variabla utgifter)
- Nivå 2 → "balanserad" (1.00)
- Nivå 3 → "slosa" (1.25)

Spendprofilen kan dock manuellt ändras (Fas 2AG-modalen tillåter
"new_spend_profile"-override). Det betyder att man kan ha
"Nivå 3 + sparsam" — eleven utmanas av många events men spenderar
fortfarande lite.

## Event-svårighet

Vid `event_engine.tick()` används nivåns `severity_filter`:

```python
SEVERITY_BY_LEVEL = {
    1: { "mild_positive": 0.4, "mild_neutral": 0.4, "moderate": 0.15, "severe": 0.05 },
    2: { "mild_positive": 0.20, "mild_neutral": 0.30, "moderate": 0.35, "severe": 0.15 },
    3: { "mild_positive": 0.10, "mild_neutral": 0.20, "moderate": 0.40, "severe": 0.30 },
}
```

Per template anges severity. T.ex. "tandlakar_ring" är moderate,
"arbetsloshet_varslad" är severe, "bonus_julgava" är mild_positive.

## Wellbeing-tröghet (återhämtning)

```python
RECOVERY_DECAY_PER_MONTH = {
    1: 1.5,   # Negativa effekter återställs snabbt
    2: 1.0,   # Normal
    3: 0.6,   # Långsam återhämtning
}
```

Vid varje månads-drift räknas:
```python
for axis, value in pentagon.items():
    deviation_from_baseline = value - 60
    recovery = -deviation_from_baseline * 0.05 * RECOVERY_DECAY_PER_MONTH[level]
    drift[axis] += recovery
```

Resultat:
- Eleven på nivå 1 med hälsa 50 → återhämtar +0.75 / mån snabbt
- Eleven på nivå 3 med hälsa 50 → återhämtar +0.30 / mån (sittande
  effekter sitter längre)

## Echo-hjälpgrad

Echo-promptens **system_message** justeras per nivå:

```python
ECHO_GUIDANCE = {
    1: "Du är en STRUKTUR-coach. Ge konkreta råd och alternativ. Eleven är ny.",
    2: "Du är en SOKRATISK coach. Ställ frågor, peka mot resurser, undvik direkta råd.",
    3: "Du är en MINIMAL coach. Bekräfta bara att du finns. Be eleven läsa själv.",
}
```

Nivå 1: "Här är 3 alternativ för buffert: 1) Sparkonto, 2) ISK, 3) Bunden..."
Nivå 2: "Vad tänker du om buffert? Vart skulle du parkera den?"
Nivå 3: "Du har gjort din research?"

## Jobbintervju success-rate

I Arbetsförmedlingen-flödet (`05-arbetsformedlingen.md`) modifierar
nivån `match_score`:

```python
def adjusted_match(base_match, level):
    if level == 1: return min(100, base_match * 1.30)
    if level == 2: return base_match
    if level == 3: return base_match * 0.75
```

## Nivå-promotion (Fas 2AG redan klar)

Eleven kan **inte själv** flytta upp i nivå. Lärare aktiverar via
`/teacher/v2/elev/:id` → "▰▰▱ Aktivera Nivå 2"-knappen.

Krav (heuristik från befintlig PromotionCard):
- Pent-balans ≥ 65
- Aktiv senaste 14 d
- ≥ 1 G-eller-F-kompetens
- ≥ 1 modul klar

Vid promotion:
- `student.v2_level` bumpas
- `student.v2_spend_profile` byts (auto eller manuellt)
- StudentActivity-event loggas (kind="level.promoted")
- Eleven får notis: "Du klarade Nivå 1 — välkommen till Nivå 2"
- Echo-prompten byts (nästa konversation märker skillnaden)

## Validering: alla nivåer ska gå att klara

Vi kör Monte Carlo (10 000 simulerade elever per nivå) och kollar:

| Mål | Nivå 1 | Nivå 2 | Nivå 3 |
|---|---|---|---|
| Total wellbeing > 65 efter 12 spelmånader | ≥ 90 % | ≥ 75 % | ≥ 60 % |
| Total wellbeing > 55 efter 12 spelmånader | ≥ 95 % | ≥ 85 % | ≥ 70 % |
| Inkasso-fall | ≤ 5 % | ≤ 15 % | ≤ 30 % |
| Konkurs (saldo < -5000 i 60 d) | 0 % | ≤ 2 % | ≤ 8 % |

Om Monte Carlo visar för svårt eller för enkelt → justera
SEVERITY_BY_LEVEL eller RECOVERY_DECAY_PER_MONTH.

## Implementation

```
backend/hembudget/game_engine/
  difficulty/
    __init__.py
    levels.py              # SEVERITY_BY_LEVEL, RECOVERY_DECAY etc
    monte_carlo.py         # Validerings-skript
    promotion.py           # Befintlig från Fas 2AG, integreras
```

## Lärar-vy: nivå-info

På `/teacher/v2/elev/:id` finns redan:
- Pill med "Nivå 1 · Sparsam" (Fas 2S)
- "▰▰▱ Aktivera Nivå 2"-knapp (Fas 2AG)
- PromoteLevelModal med varning

Tillägg:
- Visa Monte Carlo-konfidens: "Givet din profil och nivå 1, har 92 %
  av simulerade elever wellbeing > 65 efter 12 mån"
