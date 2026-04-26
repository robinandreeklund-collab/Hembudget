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

## 5. Eventsystemet — kärnan i upplevelsen

### 5.1 Vad är ett event?

Ett event är ett **förslag** som dyker upp på elevens dashboard.
Eleven har **5 sekunder till 7 dagar** att svara: acceptera, neka,
eller (för vissa) bjuda in en klasskompis.

Varje event har:
- **Titel** ("Middag med familjen i söndag")
- **Beskrivning** (1–2 meningar pedagogisk text — ev. AI-genererad)
- **Kategori** (social, kultur, sport, mat, lifestyle, opportunity, oförutsett)
- **Kostnad** (deterministisk per event, t.ex. 320 kr)
- **Wellbeing-impact** vid accept/neka per dimension
- **Deadline** (sista dag att svara)
- **Vem föreslog** (familj, kompis, klasskompis-elev, system)

### 5.2 Event-bibliotek (master-DB, delat)

Cirka **80 mallar** över alla kategorier — likt `STOCK_UNIVERSE` och
`module_seed.py`. Mallar har sektorer/varumärken på riktigt:

**Sociala (utebjudningar):**
- Bio Filmstaden — *Den senaste Marvel-filmen* — 180 kr — +3 sociala, +2 fritid
- Restaurang Vapiano — *Pasta med kollegorna* — 280 kr — +4 sociala, +1 mat
- Hemmamiddag hos släktingen — 0 kr (eleven bjuder bara) — +5 sociala
- Karaokebar Friday Bar — 350 kr — +5 sociala, +3 fritid
- AIK-Hammarby på Tele2 Arena — 450 kr — +5 sociala, +5 fritid
- Musikalen "Mamma Mia" på Cirkus — 800 kr — +4 sociala, +5 kultur
- Stockholm Marathon — 600 kr (anmälningsavgift) — +6 hälsa, +3 sociala
- Spelmuseum med kompisen — 150 kr — +3 fritid, +2 kultur

**Familjehändelser:**
- Mormors 80-årskalas — 500 kr (gåva) — +5 sociala, +2 trygghet
- Födelsedagspresent till syskon — 350 kr — +3 sociala
- Familjesemester en helg på Gotland — 1 200 kr — +6 sociala, +6 fritid

**Spontana möjligheter:**
- "Det är realisation på Volt-cykeln du tittat på" — 4 500 kr — varierande
- "Kompis säljer sin gamla soffa" — 800 kr — neutral
- "Marathon-anmälan stänger imorgon" — 600 kr — +6 hälsa, +3 sociala

**Oförutsedda kostnader (negativa events):**
- Tandläkare — akut visdomstand — 2 800 kr — −2 trygghet (ej val)
- Diskmaskinen går sönder — 4 500 kr — −3 trygghet (ej val)
- Cykeldäck-byte — 350 kr — −1 ekonomi (ej val)
- Förkylning, missade jobb 2 dagar — −800 kr lön — −2 trygghet
- Ringen tappad i avloppet — sökavgift 600 kr — −1 trygghet
- "Du blev av med jobbet, sista lönen kommer" — STORT — −10 ekonomi

### 5.3 Trigger-logik

När triggas ett event?

- **Tidsbaserat:** vissa events knyts till veckodagar (fredagsmiddag) eller
  månadsdagar (1:a-25:e för lön-relaterade impulsköp)
- **Slumpmässigt:** generatorn drar 0–3 events per simulerad vecka,
  seedat på `(student_id, year_month, week_n)` — deterministiskt
- **Reaktivt:** beroende på elevens *läge*:
  - Hög sparkonto → fler "spendera"-event
  - Hög stress (låg Wellbeing) → fler "lugna ner"-event (motion, naturen)
  - Många nej i rad → fler enklare social events ("kort fika")
- **Lärar-triggat:** läraren kan *manuellt* skicka ett specifikt event
  till en klass eller elev. Pedagogiskt verktyg: "kommande lektion ska
  vi prata om semesterbudgetering — jag triggar 'Familjesemester'".
- **Klasskompis-triggat:** se sektion 6.

### 5.4 Beslut-flödet

Notifikations-bubbla i header (rödprick) öppnar event-listan.
Klick på ett event → modal:

```
┌─────────────────────────────────────────┐
│ 🎬 Bio med kompisarna                   │
├─────────────────────────────────────────┤
│ Anna och Karim har bjudit dig på den    │
│ nya Marvel-filmen på Filmstaden         │
│ Söndergatan i fredag.                   │
│                                         │
│ Kostnad:           180 kr               │
│ Datum:             fredag 15 maj        │
│                                         │
│ Om du accepterar:                       │
│   Sociala band   +3                     │
│   Fritid         +2                     │
│                                         │
│ Om du nekar:                            │
│   Sociala band   −1                     │
│   (ingen ekonomisk påverkan)            │
│                                         │
│ [Acceptera]  [Neka]  [Bjud klasskompis] │
└─────────────────────────────────────────┘
```

Vid **Acceptera**: skapas en `Transaction` i kategorin nöje +
`StudentEvent` med result=accepted, Wellbeing-impact appliceras.

Vid **Neka**: `StudentEvent.result=declined`, neka-impact appliceras.

Vid **Bjud klasskompis** (sektion 6): event skickas till mottagaren.

### 5.5 "Alltid neka"-mekaniken

Spårar en `decline_streak` per elev. Om eleven nekar **3+ events i
rad utan ekonomiskt skäl** (dvs eleven *hade* råd):

- Ny notifikation: *"Du har nekat 4 förslag senaste veckan. Sociala
  band: 38/100. Inget krav att acceptera — men kanske värt att
  reflektera."*
- Wellbeing-impact: −2/event efter den 3:e
- AI-genererad pedagogisk fråga vid månadsslut: *"Hur kände du när du
  nekade dessa? Var det ekonomi, ork, eller något annat?"*

Vägar runt: om eleven *hade* råd men nekade pga prioriteringar (sparmål,
osv) kan eleven flagga "jag valde sparande över sociala" — då
applicerar vi **inte** decline-impacten. Det är ett medvetet val, inte
isolering.

---

## 6. Sociala mekanismer — klasskompisar

### 6.1 Bjuda en klasskompis

På varje "social"-typkategoriserat event ser eleven knappen **"Bjud
klasskompis"**:

1. Lista över klasskompisar (om läraren slagit på funktionen)
2. Eleven väljer 1–N personer
3. Mottagaren får eventet i sin inbox med markeringen *"Anna har
   bjudit dig till bion på fredag — ni delar kostnaden 50/50"*
4. Mottagaren kan acceptera, neka, eller motbjuda en alternativ tid

### 6.2 Kostnadsdelning

Tre modeller (lärare väljer per klass via super-admin):

**A) "Den som bjuder betalar"** — bjudaren tar hela kostnaden, andra
gratis. Pedagogik: generositet kostar.

**B) "Var och en betalar sig själv"** — alla som accepterar betalar
sin del.

**C) "Bjudaren betalar, men kostnaden delas"** (default) — bjudaren
betalar och syns på kontoutdraget. Mottagarna får automatiskt en
*"återbetala till Anna"*-rad i sin Upcoming-lista. Detta speglar
verkligheten — Swish-skuld syns i mobilen.

### 6.3 Begränsningar

- Max **3 bjudningar per elev per vecka** — annars blir det spam
- Endast event där `social_invite_allowed=True` på mall
- Mottagaren kan **stänga av inbjudningar** i sina inställningar
- Lärare kan slå av hela funktionen om klassdynamiken inte mår väl

### 6.4 Pedagogiken

- Lär sig att bjuda andra **kostar pengar men ger relationer**
- Lär sig att om man **alltid blir bjuden men aldrig bjuder själv** så
  faller relationen i obalans (mottagarens Wellbeing får ingen plus i
  Social-dimensionen efter 3+ events där bara hen accepterat utan
  att returnera)
- Lär sig om **Swish-skulder** — om någon ber dig betala och du inte
  betalar inom 14 dagar, hamnar det som "förfallet" och påverkar
  relationen

---

## 7. Klasslista och status (super-admin opt-in)

### 7.1 Standardläge: AV

Av integritetsskäl är klasslistan **avstängd som default**. Lärare
slår på den per klass via `/admin/landing/class-display`-toggle.

### 7.2 När den är på

På elev-dashboardens högerspalt visas en **anonymiserad rangordning**:

```
DIN KLASS — ÖVERSIKT (anonymt)
─────────────────────────────────
🥇 Wellbeing-toppen denna månad:
   #1 Anonym A — 87/100
   #2 Anonym B — 84/100
   #3 Du själv — 82/100  ← du
   ...

📊 Klassens genomsnitt:    74/100
   Du är:                  +8 över snitt
   
🤝 Mest sociala den här veckan:
   1. Anonym C — 14 events
   2. Anonym D — 11 events
   ...
```

Eleverna ser **bara sig själva** med namn — alla andra är
anonymiserade ("Anonym A"). Eleven kan välja att synas under sitt
namn (opt-in *per elev*).

### 7.3 Lärarens vy

Lärare har **alltid** full vy med namn (inte anonym). Tabellkolumner:
- Namn
- Wellbeing-totalt + trend (↗ ↘ →)
- Per-dimension som mini-radar
- Antal accepterade vs nekade events senaste 30 dagar
- Rödflagg om dimensionen sociala band <30 eller mat <50 (potentiella
  varningssignaler)

### 7.4 Klassgemensamma events (avancerat)

I avancerat läge (super-admin opt-in) kan läraren skapa **klass-events**
där hela klassen är inbjuden:

- "Klassresan till Berlin" — 4 500 kr per elev över 3 mån — påverkar
  alla elevers ekonomi
- "Klassmiddag i fredag" — 250 kr per elev som accepterar
- "Friluftsdagen" — 0 kr men +6 sociala för alla som accepterar

Pedagogik: eleverna känner att deras beslut är *del av en grupp*. Att
neka klassresan när 25 av 26 sa ja känns annorlunda än att neka en
random utebjudning.

### 7.5 Integritetsmodellen

Vi följer en **opt-in-stege**:

1. Super-admin: aktivera klasslista per skola
2. Lärare: aktivera per klass
3. Elev: visa-mig-med-namn (default anonym)

Backend lagrar allt på scope-nivå men exposerar bara aggregat till
elev-vyn.

---

*(Fortsätter i nästa commit: datamodell, endpoints, AI, faseplan.)*
