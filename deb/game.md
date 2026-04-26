# Gamification: Liv, beslut och välmående

Komplett designanalys för att lyfta Ekonomilabbet från en pedagogisk
huvudbok till en **levande simulator** där eleven lär sig att ekonomi
är ett *medel*, inte ett *mål*. Inga kodändringar — bara
arkitektur, mekanik, datamodell och faseplan.

---

## 1. Problemet och visionen

### 1.1 Vad som saknas idag

Plattformen är logiskt korrekt men *känslomässigt platt*. Eleven kan:
- Sätta en budget på 200 kr/mån för mat utan att något händer
- Säga nej till alla utgifter utan konsekvens
- Aldrig hamna i situationen "kompisarna ringer — fixa något kul"
- Inte mäta sig mot klassen, ingen social dimension

Verkligheten är full av dessa val. Att lära sig hantera dem är minst
lika viktigt som att räkna ränta.

### 1.2 Visionen

En **livssimulator** byggd ovanpå dagens ekonomimotor där eleven:

1. **Får oförberedda förslag och kostnader** ("middag med familjen i
   morgon — 320 kr, accepterar du?")
2. **Bedöms inte bara på kontosaldo** utan på en sammansatt
   **Wellbeing Score** som mäter ekonomi + relationer + balans
3. **Lär sig att alltid säga nej är fel** — isolering har en kostnad
4. **Lär sig att alltid säga ja är fel** — överkonsumtion har en kostnad
5. **Kan bjuda klasskompisar** — sociala kostnader och vinster delas
6. **Ser sig själv mot klassen** (om läraren slår på den vyn) — utan
   namnskuldram, bara anonyma badges och jämförelser

### 1.3 Pedagogiska lärmål

| Lärmål | Hur det övas |
|---|---|
| Ekonomi är medel, inte mål | Wellbeing visar att noll utgifter ≠ bästa liv |
| Budget måste ha minimum | Konsumentverket-tröskel som triggar varning + impact |
| Alla val har två kostnader | Pengar **OCH** Wellbeing-dimensioner |
| Sociala band är värdefulla | Relationships-dimensionen sjunker vid isolering |
| Långsiktigt vinner över impuls | Ackumulerad Wellbeing över terminen mäts |

---

## 2. Designprinciper (icke-förhandlingsbara)

1. **Pedagogiskt fokus, inte spelmässigt.** Inga "liv", inga "achievement-
   pop-ups med konfetti", inga gamla-metro-bell-belöningar. Varje
   feedback är en lärande-händelse.
2. **Determinism för rättvisa.** Två elever med samma val ska få
   samma utfall. Slumpgenerator seedad på `(student_id, year_month,
   event_seed)` så samma månad → samma erbjudanden.
3. **Konsekvenserna kvarstår.** Tar du nej till alla event i april,
   är det april-Wellbeing som påverkas. Maj återställer inte —
   minnet bärs över terminen i en `WellbeingTrend`-graf.
4. **Aldrig fördömande.** AI:n och systemet säger aldrig "du gjorde
   fel". Det säger "din relationsdimension har sjunkit 8 poäng. Det
   är OK — men varför?".
5. **Frivillig social del.** Klassrumssjukdomen "min kompis vet vad jag
   spenderar pengar på" är reell. Allt social är **opt-in** per elev,
   och hela funktionen är opt-in per lärare via super-admin-toggle.
6. **Personlighet matters.** En elev som självidentifierar som introvert
   ska inte straffas lika hårt för att neka kalas. `Personality`-typen
   påverkar tröskelvärdena.

---

## 3. Wellbeing Score — kärnmekaniken

En sammansatt poäng **0–100** beräknad per månad och visualiserad som
en pentagonradar med fem dimensioner:

### 3.1 Fem dimensioner

| Dimension | Mätare | Vad ökar | Vad sänker |
|---|---|---|---|
| **Ekonomi** | budget vs verklighet, sparande, skuld | Hålla budget, sparande > 10 %, låg skuldkvot | Negativt saldo, högkostnadskredit |
| **Mat & hälsa** | matbudget vs minimum, "tandläkare"-events | Budget ≥ Konsumentverket | Budget < 80 % av minimum |
| **Sociala band** | accepterade sociala events, bjudningar | Acceptera middag/bio/match | Neka 3+ i rad utan budget-skäl |
| **Fritid & balans** | nöje, kultur, sport-events | Variation över kategorier | Ingen aktivitet på 30 dagar |
| **Trygghet** | buffert, försäkring, oförutsedda hanterade | 2+ månadslöner i buffert | SMS-lån, sparkonto < 5 000 |

Total Wellbeing = viktat snitt (alla dimensioner samma vikt i V1; kan
nyanseras per personlighet).

### 3.2 Räkning

Sker vid **månadsslut** (eller "stega vecka framåt" om eleven använder
veckotick). Lagras i `WellbeingScore`-tabellen som tidsserie. Eleven ser
trenden över hela terminen.

### 3.3 Visualisering

- **Pentagon-radar** på Dashboard (fem hörn, ifyllt område)
- **Trendpil** per dimension: "Sociala band: ↓ 8 p sedan förra månaden"
- **Pedagogisk text under**, t.ex: *"Du nekade alla 4 sociala
  inbjudningar i april. Sociala band är på 42/100 — lägsta i din
  klass. Inget krav att acceptera, men reflektera över vad det säger
  om ditt val."*

### 3.4 Inte en betygsskala

Wellbeing är **inte** ett betyg. Det är en signal. Läraren ser den i
sin elev-vy, men den ska aldrig bli ett poängjakts-mål — då tappas
poängen.

---

## 4. Konsumentverket-minimum + budget-realism

### 4.1 Minimibelopp 2026 (ensamboende vuxen, från Konsumentverket)

| Kategori | Minimibelopp/mån |
|---|---|
| Mat | 2 600 kr |
| Hygien & kläder | 1 300 kr |
| Fritid & nöje | 700 kr |
| Hemförsäkring | 200 kr |
| Telefon & data | 250 kr |
| Hushållsel (lägenhet) | 200 kr |
| Bredband | 300 kr |
| **Totalt minimum** | **~5 550 kr/mån** |

(Boendekostnad räknas separat — det varierar mycket.)

Dessa siffror finns redan i `school/konsumentverket.py`. Bra
återanvändning.

### 4.2 Validering vid budget-sättning

När eleven sätter en budget under minimibeloppet **för en kategori**:

- **Ej hård blockering.** Eleven får sätta vad hen vill.
- **Banner i UI:** "Konsumentverket räknar med 2 600 kr/mån för mat.
  Du har satt 1 200 kr — det går teoretiskt, men du kommer märka det.
  Wellbeing→Mat & hälsa drabbas."
- **Generatorn anpassar sig:** transaktioner i den kategorin kommer
  in i mängd som speglar budgeten — inte som tidigare där allt var
  konstant.
- **Wellbeing-impact:** budget < 80 % av minimum sänker dimensionen
  med 2 p/månad. Budget < 50 % sänker med 5 p/månad.

### 4.3 Generatorn anpassar sig (förändring av befintlig kod)

Idag genererar `MonthlyDataGenerator._generate_transactions` ungefär
samma utgifter oavsett budget. **Ny logik:**

```
för varje budgeterad kategori:
  ratio = budget / konsumentverk_minimum
  if ratio < 0.5:
    # Sub-existens: generera bara absolut nödvändiga rader
    transactions = baseline * 0.5
  elif ratio < 0.8:
    # Snålt liv: generera färre och billigare
    transactions = baseline * 0.7
  elif ratio < 1.5:
    # Standard
    transactions = baseline * 1.0
  else:
    # Generös: lägg till impuls-rader och mer variation
    transactions = baseline * 1.2 + impulse_extras
```

Detta får eleven att **känna** sin budget i kontoutdraget. Sätter du
1 200 kr/mån för mat ser du verkligen färre ICA-rader och mer
"Pasta + ost" och mindre "Sushi Yama".

---

*(Fortsätter i nästa commit: eventsystemet, sociala mekanismer, klasslista.)*
