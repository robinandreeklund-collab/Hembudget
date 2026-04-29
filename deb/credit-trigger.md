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

## 7. Datamodellsändringar

Ingen helt ny tabell behövs. **Loan**-modellen täcker det mesta. Vi
lägger till några fält:

### 7.1 Befintlig `Loan` utökas

```
is_high_cost_credit: bool   # SMS-lån / snabblån — färgmärks rött
loan_kind: str              # "mortgage" | "private" | "sms" | "car" | "student"
applied_at: datetime        # När ansökan gjordes (separerar från start_date)
score_at_application: int   # Kreditscore då — för retro-analys
declined_attempts: JSON     # Lista av {bank, score, reason} innan godkänt
```

### 7.2 Ny tabell `CreditApplication`

För att kunna logga ansökningar som *inte* ledde till lån (avslag,
elev tackade nej):

```
CreditApplication (TenantMixin):
  id, kind ("private"|"sms"), requested_amount, requested_months,
  result ("approved"|"declined"|"abandoned"|"accepted"|"rejected_by_student"),
  score_value, simulated_lender, offered_rate,
  triggered_by_tx_id (FK Transaction, nullable — vad utlöste behovet),
  created_at, decided_at
```

Detta är **revisionsspår**: läraren kan se *alla* kreditförsök, inte
bara de som blev verkliga lån. Pedagogiskt värdefullt.

### 7.3 Ny `StudentProfile`-utökning (master-DB)

Läraren ska kunna konfigurera per elev:

```
credit_buffer_threshold: int    # Default 0, kan höjas till 500/1000
allow_credit_flow: bool         # Lärare kan slå av hela flödet om
                                # klassen inte är där pedagogiskt än
sms_loan_enabled: bool          # Separat — SMS-lån är medvetet svårt
                                # och vissa lärare vill inte använda
```

---

## 8. Backend-endpoints (nya)

| Metod | Path | Funktion |
|---|---|---|
| `POST` | `/credit/check-affordability` | Kollar om en planerad transaktion ryms i lönekontosaldot. Returnerar `ok` eller `shortfall + options` |
| `POST` | `/credit/private/apply` | Skickar in ansökan, kör scoring, returnerar `approved/declined + offer` |
| `POST` | `/credit/private/accept` | Eleven accepterar offerten — skapar Loan, LoanScheduleEntry, Transaction |
| `POST` | `/credit/private/decline` | Eleven tackar nej — uppdaterar CreditApplication.result |
| `POST` | `/credit/sms/apply` | Som privat men auto-godkänt om grundkrav möts |
| `POST` | `/credit/sms/accept` | Skapar high-cost Loan |
| `GET` | `/credit/applications` | Elev/lärare listar ansökningar (audit) |
| `GET` | `/teacher/students/:id/credit-history` | Lärar-vy: alla ansökningar för en elev |

Alla under `api/credit.py` — ny router. Återanvänder
`StudentScopeMiddleware` så scope-isoleringen sker automatiskt.

---

## 9. Frontend-flöde (UX)

### 9.1 Ny komponent `CreditModal`

Tre vyer i en modal med fade-mellan:

1. **Översikt-vyn** — "Din ekonomi går inte ihop"
   - Visar saldo, shortfall, alternativ
2. **Ansök-vyn** — formulär per lånetyp
3. **Resultat-vyn** — godkänd/avslag + acceptans-knappar

### 9.2 Var triggas modalen

- I `NewTransferModal` när eleven skulle ge lönekonto < tröskel
- I `Transactions`-sidan vid manuell transaktion (om vi får den
  funktionen)
- Som **automatisk popup** när eleven öppnar `/dashboard` och något
  konto är negativt (post-import-trigger)

### 9.3 Lärar-vy

Ny flik `/teacher/students/:id/credit` med:
- Tabell över alla ansökningar (datum, typ, belopp, resultat, ränta)
- Lista över aktiva lån + total skuld
- Total räntekostnad senaste året
- Knapp "Slå av kreditflöde för denna elev" (om läraren inte vill)

---

## 10. Pedagogiken (vad eleven ska lära sig)

Tre lärmål som matrix:

| Lärmål | Hur det övas |
|---|---|
| Skuldkvot påverkar ränta | Score-tabellen visar exakt hur mycket befintliga lån sänker score |
| Ränta-på-ränta är dyrt | Privatlån-formuläret visar `total_kostnad` live när eleven drar i löptids-slidern |
| SMS-lån är *en* lösning men ofta fel | Modal-färg + reflektion + AI-feedback gör skillnaden tydlig |
| Buffert förhindrar kreditbehov | "Om du haft 5 000 kr extra på sparkontot hade detta inte triggats" — visa i modalen |

Koppla till **kompetens-systemet** (`competency_seed.py`):
- Ny kompetens: `credit_decision_skill`
- Ny modul: "Kreditmånaden — när pengarna inte räcker" med 6 steg

---

## 11. Faseplan

**Fas 1 — Sparkonto-strikt (1 timme):** Generalisera blocket i
`create_transfer` till `NEVER_NEGATIVE`-set. Inga nya tabeller.
Snabb fix för det första symptomet.

**Fas 2 — Affordability-check (3–5 dagar):** Ny endpoint
`/credit/check-affordability`. `NewTransferModal` kallar den innan
submit. Visa enkel "ditt saldo räcker inte" — *utan* kreditflöde
ännu, bara avbryta-knapp. Triggrar ger oss data om hur ofta det
händer i klassrummet utan att ändra UX för mycket.

**Fas 3 — Privatlåne-flödet (1 vecka):**
- DB-migrationer: nya `Loan`-fält + `CreditApplication`-tabell
- `api/credit.py`-router med privat-endpoints
- `CreditModal` med ansök + scoring + acceptans
- Skapar verkliga Loan-rader vid accept

**Fas 4 — SMS-låneflödet (3–5 dagar):**
- SMS-specifikt UI med varningar
- Auto-godkänt med hård ränta
- Reflektionsfråga + AI-kommentar (om ai_enabled)
- `is_high_cost_credit`-färgmärkning i lärar-UI

**Fas 5 — Lärarintegration (1 vecka):**
- `/teacher/students/:id/credit`-flik
- StudentProfile-konfiguration (buffer, av/på)
- Klassöversikt av kreditansökningar

**Fas 6 — Polish (2–3 dagar):**
- Modulen "Kreditmånaden" i `module_seed.py`
- Ny kompetens
- Post-import-trigger på Dashboard
- AI-funktion för pedagogisk kommentar efter SMS-lån

---

## 12. Beslutspunkter innan kod

1. **Tröskelvärde för trigger.** 0 kr (matematiskt) eller 500–1 000 kr
   (realistiskt buffert)? Min rekommendation: 0 kr som default,
   konfigurerbart per elev. Lärare som vill ha tightare buffert kan
   höja.
2. **Hur många bankförsök?** En enda bank som säger nej, eller
   3 banker (SEB → SBAB → Avanza) med olika scoring-trösklar? Min
   rekommendation: 1 bank i V1, 3 banker i V2 — gör avslags-känslan
   mer realistisk.
3. **Slumpmässigt resultat eller deterministiskt?** Deterministiskt
   ger rättvisa mellan elever (samma ekonomi → samma utfall) men kan
   kännas spelat. Min rekommendation: deterministiskt seed:at på
   `(student_id, year_month, requested_amount)` — samma val ger samma
   resultat, men olika belopp ger olika utfall.
4. **Får eleven "spara" undanlagda räkningar?** Om eleven trycker
   "avbryt transaktionen" — vad händer med den? Min rekommendation:
   räkningen läggs som `UpcomingTransaction` med varning "förfallen,
   risk för betalningsanmärkning" och triggar igen nästa månad om
   inte betald.
5. **Inkasso-flöde i V2?** Realistiskt men komplicerat. Min
   rekommendation: skippa V1, lägg som "kommande modul" i Variant
   C-roadmappen.
6. **AI-kommentar — med eller utan?** Kostar tokens. Min
   rekommendation: opt-in via `Teacher.ai_enabled` som vi redan har.
   Utan AI fungerar reflektionsfrågan, men utan AI-svar.

---

## Sammanfattning

Tre buggar adresseras med ett samlat designsvar:

1. **Sparkonto kan gå minus** → generalisera befintligt block till
   `NEVER_NEGATIVE`-set (1 timme, ingen ny modell)
2. **Lönekonto går djupt minus utan signal** → soft trigger på
   `check-affordability`-endpoint (3–5 dagar)
3. **Inget pedagogiskt flöde när pengarna tar slut** → Privatlån-
   flöde med simulerad kreditupplysning (1 vecka), SMS-lån som sista
   utväg (3–5 dagar), realistiska Loan-rader skapas så hela
   ekonomimotorn tar över därifrån

**Total leveranstid:** ~3 veckor uppdelat i 6 faser, varje fas
livefärdig och testbar.

**Största pedagogiska vinsten:** eleven övar att **välja under press**
— det enskilt vanligaste momentet där unga går fel ekonomiskt. Att
göra det i sandlåda med konsekvenser kvarstår över månader är något
ingen klassisk lärobok kan erbjuda.
