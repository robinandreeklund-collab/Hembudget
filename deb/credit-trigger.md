# Negativt saldo → kreditflöde

Designanalys för en pedagogisk kreditmotor som triggas när elevens
ekonomi inte går ihop. Inga kodändringar i denna fil — bara
arkitektur, datamodell, UX och faseplan.

---

## 1. Problemet

Idag tillåter systemet att lönekontot går djupt minus utan att eleven
märker det. Skärmdumpar visar saldon på −12 254 kr efter att bolån,
hyra och en överföring till sparkonto dragits — utan att något
händer i UI:t.

Pedagogiskt är detta **fel signal**. Verkligheten är:

- Banken tillåter inte övertrassering på vanliga lönekonton (eller tar
  ut hög straffränta)
- När pengarna inte räcker tvingas människor välja: skjuta upp en
  räkning, ta lån, eller låta något gå till inkasso
- Sämsta valet (SMS-lån) är ofta det första man tar — för att man inte
  hann tänka eller söka annat

Vi vill **simulera dessa konsekvenser** i en trygg sandlåda så eleven
övar att hantera situationen innan den uppstår på riktigt.

Användaren vill också blockera **överföringar till sparkonto** när
pengar saknas på avsändarkontot — ett sparkonto ska inte kunna fyllas
med fiktiva pengar.

---

## 2. Designprinciper

1. **Block, varna, eller trigga — välj per situation.**
   - Sparkonto-överföring som skulle ge negativt avsändarsaldo →
     **block** (returnera 400, frontend visar "saldot räcker inte")
   - Räkning/transaktion som skulle ge negativt lönekontosaldo → 
     **triggar kreditflödet** (eleven får välja: ta lån, hoppa över)
2. **Eleven beslutar — systemet rekommenderar inte.** AI får
   förklara skillnader, men aldrig "ta detta lån".
3. **Verkligheten i sandlåda.** Privatlån-villkor från riktiga
   bankers prislistor (SEB, SBAB, Avanza). SMS-lånvillkor från Klarna,
   Bynk, GF Money — alla offentliga.
4. **Konsekvenserna kvarstår.** Tar eleven SMS-lån denna månad ligger
   skulden + räntan kvar nästa månad. Lånet blir en `Loan`-rad med
   amorterings-schemat, exakt som ett bolån.
5. **Audit-spår.** Varje kreditbeslut loggas (ansökan, godkännande,
   avslag, val) så läraren kan se elevens beslutsgång.

---

## 3. Triggern: när systemet ingriper

Två separata triggrar baserat på *avsändarkontots typ*:

### 3.1 Sparkonto — strikt blockering

Vi har redan denna i fas A1 (`api/transfers.py::create_transfer`):

```
if src.type == "savings":
    balance = _balance_for(session, src.id)
    if balance - amount < 0:
        raise HTTPException(400, "Sparkontot skulle gå minus…")
```

Den fungerar för proaktiva överföringar, men **inte för importerade
banktransaktioner** (där kommer raden in via parser och hamnar i DB
oavsett saldo). Räcker för pedagogiken — eleven kan inte själv
övertrassera sparkontot.

**Utvidgning V1:** generaliserade till alla kontotyper utom `checking`
och `credit`. Det betyder: ISK, depå, sparkonto, pensionskonto kan
aldrig gå minus via *manuella elev-aktioner*.

### 3.2 Lönekonto — soft trigger

Här är kärnan. När en ny transaktion eller överföring skulle göra
lönekontot **negativt eller under en buffert-tröskel** (t.ex. 500 kr,
konfigurerbart per elev) händer detta:

1. **Operationen pausas** — inte rejected
2. Eleven får en **modal: "Din ekonomi går inte ihop"**
3. Modalen visar:
   - Aktuellt saldo
   - Beloppet som ska dras
   - Hur mycket eleven saknar
   - 3 alternativ:
     - **Ta privatlån** (rekommenderad knapp)
     - **Ta SMS-lån** (varningsknapp — visas grå-markerad)
     - **Avbryt transaktionen** (skjut upp räkningen — påverkar
       betalningsanmärkning senare)

Tröskeln är konfigurerbar:
- 0 kr för nybörjare (rent matematiskt — när saldot blir negativt)
- 500 kr eller 1 000 kr i en mer realistisk variant (vill inte att
  kontot står på 50 kr om en autogirobetalning är på väg)

### 3.3 Vad triggar tekniskt

Två platser i koden:

**a)** `api/transfers.py::create_transfer` — eleven gör en proaktiv
överföring som skulle ge minus.

**b)** En ny endpoint **`POST /transactions/check-affordability`** som
varje "skapa transaktion"-flöde kallar innan det faktiskt skapar
raden. Returnerar:

```
{ "ok": true } eller
{ "ok": false, "shortfall": 8453, "credit_options_url": "/credit/options?need=8453" }
```

Frontend kan då pausa, visa modalen, låta eleven välja, och *därefter*
skicka transaktionen.

**c)** Vid import av batch-PDF:er — om eleven importerar ett
kontoutdrag som *redan* visar minus (klassens generator skapade en
hård månad), triggar vi en **post-import-check**: när importen är
klar, kolla saldon. Om något konto är negativt → modal direkt med
samma flöde.

---

## 4. Privatlån-flödet (förstaval)

När eleven klickar **"Ta privatlån"**:

### 4.1 Ansökningsformulär

Modal som visar:
- **Belopp** (förvalt = shortfall + buffer 5 000 kr, slider 5 000 –
  100 000 kr)
- **Återbetalningstid** (12 / 24 / 36 / 60 / 84 mån)
- **Ändamål** (dropdown: oförutsedda utgifter / boende / annat)
- **Sammanfattning live:**
  - Månadskostnad
  - Total ränta över löptiden
  - Effektiv ränta
  - Total kostnad

### 4.2 Simulerad kreditupplysning

Eleven klickar **"Ansök"**. Servern kör en deterministisk
kreditbedömning baserat på:

| Faktor | Vikt | Källa |
|---|---|---|
| Inkomst (lön senaste 3 mån, snitt) | +++ | `Transaction` med kategori "Lön" |
| Befintliga lån (skuldkvot) | −−− | `Loan`-tabellen, summa principal_amount |
| Sparkonto-saldo (buffert) | + | live-saldo savings-konton |
| Antal nyligen tagna lån (senaste 6 mån) | −− | `Loan.start_date` |
| Betalningsanmärkningar (om vi simulerar) | −−− | nytt fält `Loan.is_default` |
| Ålder (om sätts på elev) | + | StudentProfile |

Algoritm:
```
score = 600   # mid
score += min(income_avg / 1000, 30)              # max +30
score -= min(total_debt / 10000, 50)             # max −50
score += min(savings / 5000, 20)                 # max +20
score -= recent_loans_count * 15                 # −15 per nyligt lån
score -= defaults_count * 100                    # hård straff
score -= (requested_amount / income_avg) * 10    # för stor ansökan = nej
# Slumpfaktor (deterministisk på elev+månad+belopp): ±20 poäng

approval_threshold = 550
```

Resultat: **godkänd / avslag** med kort förklaring i klartext.

### 4.3 Vid godkännande

Modal byter vy:
- "Banken har godkänt din ansökan!"
- Räntan beräknas: `nominell = 4–9 %` baserat på score (bättre score
  → lägre ränta — exakt formel: `9 - (score-550)/50 %`)
- **Villkorstext** att läsa: 4–6 punkter på lättläst svenska
- **Två knappar:** "Acceptera och få pengarna" / "Tacka nej"

Vid acceptera:
1. Skapa **`Loan`**-rad: name="Privatlån", lender=valt bank-namn,
   principal_amount, start_date, interest_rate, binding_type="rörlig",
   amortization_monthly = beräknad rakamortering
2. Skapa **`LoanScheduleEntry`**-rader för varje månad i löptiden
3. Skapa **`Transaction`** på lönekontot: `+lånebelopp`, kategori
   "Privatlån utbetalning", is_transfer=False
4. Returnera till transaktions-flödet — den ursprungliga utgiften går
   nu igenom (saldot räcker)

### 4.4 Vid avslag

- "Banken har tackat nej. Skäl: din skuldkvot är för hög."
- **Två knappar:** "Försök en annan bank" (1–2 fler simulerade
  bankförsök med liknande villkor) / "Prova SMS-lån som sista utväg"
  / "Avbryt transaktionen"

---

## 5. SMS-lån-flödet (sista utväg)

Eleven klickar **"Prova SMS-lån"**. Distinkt UX som signalerar att
detta är *fel* val:

### 5.1 Visuell varning

- Röd toppbar: **"Detta är dyr kredit. Läs noga."**
- Tre snabba fakta i mono:
  - Effektiv ränta: **89 % – 200 %**
  - Avgifter utöver räntan
  - Risk att hamna i skuldspiral

### 5.2 Förenklad ansökan

- Belopp: 1 000 – 30 000 kr
- Löptid: 30 / 60 / 90 dagar (kort!)
- Ingen kreditupplysning (eller en pro forma som *alltid* godkänns
  så länge eleven har lön — det är poängen med SMS-lån)
- Snabbgodkännande (modal byter vy direkt)

### 5.3 Villkor är hårda

- Effektiv ränta enligt formel: `nominell ~30 % + uppläggningsavgift
  500 kr + aviavgift 50 kr/månad`
- Räknat över löptiden ger detta **89 % – 150 %** effektiv ränta
- Visa eleven **innan** acceptans:
  - "Du lånar 5 000 kr. Du betalar tillbaka 5 950 kr om 30 dagar."
  - "Effektiv ränta: 117 %"

### 5.4 Vid acceptans

Samma som privatlån men:
- `Loan.lender` = "Bynk" / "Klarna" / "Cashbuddy" (slumpat per elev)
- Räntan högre, löptiden kortare
- Tag `is_high_cost_credit=True` på Loan så lärar-UI:t kan
  färgmärka det rött

### 5.5 Pedagogisk follow-up

- Efter accepterat SMS-lån: skapa automatiskt en **reflektionsfråga**
  i `StudentStepProgress`: "Hur hamnade du här? Vad kunde du gjort
  annorlunda?"
- AI:n (om aktiverad) skickar en pedagogisk kommentar — inte
  fördömande utan analytisk: "SMS-lånet kostar 1 200 kr på 90 dagar.
  Det motsvarar X dagars sparande. Hur hade du kunnat undvika det?"

---

## 6. Sparkonto strikt — utvidgning

**V1-fix (snabb):** Generalisera blocket i `create_transfer` till att
gälla alla *uttagsbara* kontotyper som inte ska kunna gå minus:

```
NEVER_NEGATIVE = {"savings", "isk", "pension"}
if src.type in NEVER_NEGATIVE:
    if balance - amount < 0:
        raise HTTPException(400, f"{src.name} skulle gå minus...")
```

Lönekonto (`checking`) och Kreditkort (`credit`) får fortfarande gå
minus — men checking triggar kreditflödet, credit-kort använder
kreditgränsen som vanligt.

**V2 (senare):** Validera även på **transaktions-skapandet**, inte
bara överföringar. När en POST `/transactions` skulle ge negativt
saldo på ett `NEVER_NEGATIVE`-konto → 400. Detta blir relevant först
om vi tillåter eleven att skapa egna manuella transaktioner direkt
(idag importeras de från PDF).

---

*(Fortsätter i nästa commit: datamodell, backend-endpoints, UX-flöde,
faseplan.)*
