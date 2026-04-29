# Nya funktioner: Överföringar och Aktiehandel

Designanalys för två sammanhängande funktioner:

1. **Överföringar mellan elevens egna konton** (proaktivt flöde — eleven
   skapar överföringen själv, saldot uppdateras direkt).
2. **Aktiehandel** med 30 svenska large-caps, realtidskurser var 5:e
   minut, Avanza-courtage, full lärarspårning och egen modul.

Ingen kod — bara arkitektur, datamodell, integrationspunkter, pedagogik
och en faseplan. Förankrad i befintlig kodbas.

---

# DEL 1 — Överföringar mellan egna konton

## 1. Bakgrund: vad finns redan

Ni har **redan** en överföringsmotor — men den är *detection-driven*
för importerade banktransaktioner:

- `Transaction.is_transfer` + `Transaction.transfer_pair_id`
  (`backend/hembudget/db/models.py:114-117`) — flagga + FK till motpart
- `backend/hembudget/api/transfers.py` — endpoints för att lista parade,
  oparade, föreslagna, samt manuell länkning
- `backend/hembudget/transfers/detector.py` — auto-detektion av
  kreditkortsbetalningar, "ISK insättning", kontonummermönster m.m.
- `frontend/src/pages/Transfers.tsx` — tre kolumner (parade / oparade /
  förslag), bulk-länkning
- Saldot räknas **live** från transaktioner i `api/balances.py:18-100`,
  inte cachat på kontot

**Det som saknas:** ett aktivt flöde där eleven själv klickar "flytta
500 kr från lönekonto till sparkonto" och saldot uppdateras direkt.
Detta är fundamentalt eftersom skoleleverna oftast inte har importerade
bankdata — kontona är genererade.

## 2. Designprincip: två länkade transaktioner, ingen ny modell

Den enklaste och mest robusta lösningen är att en överföring = **två
`Transaction`-rader skapade i samma DB-transaktion**, parade via
`transfer_pair_id`. Då fortsätter `balances.py` fungera utan ändringar
— minus-raden minskar avsändarsaldo, plus-raden ökar mottagarsaldo,
och `is_transfer=True` gör att de filtreras bort från utgifts-/intäkts-
summor i ledger-rapporter (vilket redan görs i `api/ledger.py`).

Ingen ny tabell, ingen ny modell. Bara en ny endpoint och en ny
frontend-modal.

## 3. Ny endpoint `POST /transfers/create`

Inputs:
- `from_account_id`, `to_account_id`
- `amount` (positivt heltal i öre eller decimal — håll samma format som
  resten av Transaction)
- `date` (default idag, accepterar framtida datum för "planerad")
- `description` (frivillig, default "Överföring till {tokonto-namn}")

Validering (alla 4xx, inte 5xx):
- båda kontona finns och tillhör elevens scope (auto via
  `StudentScopeMiddleware`)
- konton är olika
- belopp > 0
- avsändarkontot tål uttaget (varning men *tillåt* om kontotyp är
  `checking`/`credit`; blockera om `savings` skulle bli negativ —
  pedagogiskt: man ska inte kunna "övertrassera sparkontot")

Utförande (allt i samma SQLAlchemy-session, atomic):
1. Skapa avsändar-Transaction: `amount = -X`, `is_transfer=True`,
   `category` = "Överföring ut"
2. Skapa mottagar-Transaction: `amount = +X`, `is_transfer=True`,
   `category` = "Överföring in"
3. Sätt `transfer_pair_id` korsvis på båda
4. Commit
5. Returnera båda raderna + nya saldon för båda kontona

## 4. Frontend — `TransferModal`

Knapp "Ny överföring" på tre ställen:
- Översta raden i `/accounts` (kontoöversikt)
- I `Transactions.tsx` (åtgärdsmeny)
- I företagsmodulens dashboard (när den finns) — flytta från
  privatekonomi till företagskassa

Modal:
- Från-konto: dropdown med saldo i parentes ("Lönekonto — 12 450 kr")
- Till-konto: dropdown, exkluderar valt från-konto
- Belopp: numfält med live-preview "Nytt saldo lönekonto: 11 950 kr,
  nytt saldo sparkonto: 5 500 kr"
- Datum + beskrivning
- "Genomför" → POST → optimistic update av saldoindikatorer

Pedagogiska detaljer som höjer kvaliteten:
- Visa procent av sparmål som uppnås om till-kontot har ett `Goal`
- Vid stora överföringar (>50 % av avsändarens saldo): mjuk varning
  "Är du säker? Detta är mer än hälften av kontots saldo"

## 5. Lärarspårning

Lägg till ett event i `StudentActivity`-loggen (om den finns; annars i
`StudentStepHeartbeat`-stilen — nytt event-typ): `transfer_created`
med metadata `{from, to, amount, balance_after}`. Visas i
`/teacher/students/:id` som tidslinje "Flyttade 1 500 kr från Lön
till Spar — kl 14:32". Detta är *guld* för läraren när hen vill se om
eleven förstår koppling mellan inkomst, sparande och utgifter.

## 6. Modul-koppling

Befintliga "Din första månad" och "Buffert"-modulerna har redan
`task`-steg av kind `link_transfer` och liknande. Lägg till en ny
`assignment_kind`: `make_transfer` med params `{min_amount,
to_account_kind, max_age_days}`. Stegtypen kan då auto-markeras klar
när eleven gör en överföring som matchar.

## 7. Risker och fallgropar

- **Race condition vid samtidiga överföringar:** Två klick på samma
  knapp inom 200 ms kan ge dubbel överföring. Lösning: idempotency-key
  i requesten (UUID från frontend) + UNIQUE-index på `(scope_id,
  idempotency_key)` på Transaction.
- **Negativa saldon i ledger-vyer:** Om ni tillåter checking att gå
  minus, måste rapporterna visa det rött, inte krasha. Kontrollera
  `api/ledger.py`.
- **Framtida datum:** Behandlas idag som vanlig transaktion — saldot
  påverkas direkt även om datumet är i morgon. Antingen acceptera det
  (enkelt, lätt att förklara) eller införa "pending"-status (komplicerat
  — kräver ny kolumn). **Rekommendation: acceptera direkt-effekt i V1,
  spara "planerade överföringar" som separat feature i V2.**
- **Företags-modulens kassa vs privatkonton:** När båda finns i samma
  scope kan eleven flytta pengar mellan privat och företag. Det är
  *önskvärt* (kapitaltillskott, eget uttag) men måste bokföras
  pedagogiskt rätt — inte bara som "Överföring ut". Lägg till en
  speciell kategori "Eget uttag / Kapitaltillskott" som triggas när
  ena kontot är `business`-typen.

---

# DEL 2 — Aktiehandel

## 8. Konceptet i en mening

Eleven öppnar ett aktiekonto (ISK), flyttar pengar dit via överförings-
funktionen från del 1, väljer från en lista på **30 svenska
large-caps** (förslagsvis OMXS30), köper och säljer fritt under
börsens öppettider, betalar **Avanza Mini-courtage**, och får en
realtidsvy över portföljen. Allt köp/sälj loggas i en **immutable
ledger** som läraren kan granska beslut för beslut.

## 9. Vad finns redan att bygga vidare på

| Behov | Befintlig komponent |
|---|---|
| ISK som kontotyp | `accountTypes.ts` har `isk` |
| Aggregerade innehav per ISK | `FundHolding` + `FundHoldingSnapshot` (`db/models.py:427-487`) — *liknande mönster* återanvänds men för aktier |
| ISK-schablonbeskattning | `ISKCalculator` i `api/tax.py` — utökas så att aktievärden räknas in i underlaget |
| Vision-AI för bankskärmbilder | `api/funds.py::parse_image` — kan återanvändas senare för att importera Avanza-portfölj |
| Saldoberäkning från transaktioner | `api/balances.py` — likviden räknas live, inget cachat |
| Lärarens tilldelning av uppgifter | `Assignment`-modellen — ny `kind: stock_buy/stock_sell/diversify` |
| Modulinfrastruktur | `Module/ModuleStep/StudentModule` — ny systemmodul "Aktier — komma igång" |
| AI-Q&A | `ai.py::answer_student_question` — utökad kontext för aktietermer |

**Det helt nya:** datakälla för kurser, en globalt delad
`StockMaster`/`StockQuote`-tabell, en ordermotor (även om den i V1
bara tar marknadsorder), och börstidskalender.

## 10. Datakälla för kurser — den största designbeslutet

Kursdata kostar pengar eller har gränser. Tre realistiska alternativ:

| Källa | Kostnad | Realtid? | Risk |
|---|---|---|---|
| **yfinance** (Yahoo, inofficiell) | Gratis | Ja, ~15 min försening | Kan brytas, ingen SLA |
| **Finnhub** | Gratis 60 anrop/min | Ja | Kräver API-nyckel; rate limit räcker (30 aktier/5 min = 6/min) |
| **Alpha Vantage** | Gratis 25/dag, $50/mån för premium | Ja på premium | Gratis nivå räcker inte för 30 aktier |
| **Nasdaq Stockholm direkt** | Dyrt (4-siffrig $/mån) | Ja, äkta realtid | Inte värt det för skolbruk |
| **EOD Historical Data** | $20/mån | 15-min försenat | Bra om budget finns |

**Rekommendation:** Bygg en `QuoteProvider`-abstraktion (interface) med
två implementationer från start — `YFinanceProvider` (default,
fallback) och `FinnhubProvider` (primär om `FINNHUB_API_KEY` är satt
i env). Då kan ni:
- starta gratis med yfinance
- skala upp till Finnhub om Yahoo bryts
- byta källa utan att röra resten av koden

Lägg in en envvar `HEMBUDGET_QUOTE_PROVIDER` (default `yfinance`) och
`FINNHUB_API_KEY` (frivillig).

**Pedagogisk märkning:** kursvyn ska *alltid* visa "Försening: ~15
min" tydligt, så elever förstår att de inte tradeear på äkta realtid.
Det är pedagogiskt korrekt och rättsligt skyddande.

## 11. Datamodell

### Globalt (ej scope-isolerat — delas mellan alla elever)

- **`StockMaster`** — Ticker (`VOLV-B.ST`), namn (`Volvo B`), namn på
  svenska, ISIN, sektor (`Industri`), valuta (`SEK`), börs (`XSTO`),
  marknadsplats-ID. ~30 rader, seedade en gång.
- **`StockQuote`** — append-only historik. `ticker, ts, last, bid,
  ask, volume, change_pct`. En rad per polltick (var 5:e min). Används
  för grafer (1d/1w/1m/1y).
- **`LatestStockQuote`** — denormaliserad senaste-pris-tabell, en rad
  per ticker. Uppdateras vid varje polltick. Gör att portföljvärdering
  blir en `JOIN` istället för subquery.
- **`MarketCalendar`** — datum + status (`open`/`closed`/`half_day`)
  + öppningstid + stängningstid. Seedad för innevarande + nästa år
  med svenska helgdagar och midsommarafton (kort dag).

### Scope-isolerat (ärver `TenantMixin`)

- **`StockHolding`** — `account_id` (måste vara `isk` eller ny `depa`),
  `ticker`, `quantity` (antal aktier), `avg_cost` (snittinköpspris
  efter courtage). Aggregat — uppdateras efter varje
  StockTransaction. Antal kan inte vara fraktion i V1 (förenklar).
- **`StockTransaction`** — `account_id, ticker, side` (`buy`/`sell`),
  `quantity`, `price` (kurs vid execution), `courtage`,
  `total_amount` (= quantity * price + courtage vid köp; quantity *
  price - courtage vid sälj), `executed_at`, `quote_id` (FK till
  exakt vilken `StockQuote`-rad som användes — pedagogiskt och
  audit-bart). **Append-only — aldrig delete eller update.** Detta
  är "ledgern" som läraren granskar.
- **`StockOrder`** *(valfritt i V1)* — om limit-orders ska stödjas.
  Annars: bara marknadsorder utförs synkront mot `LatestStockQuote`
  och `StockOrder`-tabellen behövs ej.

### Vad gör den valda modellen pedagogiskt rätt

`StockTransaction` lagrar `quote_id` istället för bara `price`. Det
betyder att om läraren senare frågar "varför fick eleven det priset?"
kan systemet visa **exakt** vilken polltick som gällde — vilken minut
data hämtades och från vilken källa. Det här är revisionsspårbarhet
på riktigt och passar perfekt ihop med Företagsekonomi 2:s kapitel
om revision.

## 12. Kursprispipeline (bakgrundsjobb)

### Schemaläggning

Lägg en `APScheduler`-baserad bakgrundsjobb i `main.py::lifespan`
(byt från `on_event("startup")` samtidigt — CLAUDE.md noterar att den
är deprecated):

```
schedule:
  - var 5:e minut, måndag–fredag, 09:00–17:30 CET
  - skip om MarketCalendar säger closed eller half_day-stängt
  - hoppa över första 60 sek efter öppning (volatilitet, dåliga quoter)
```

### Pipeline-steg

1. Hämta de 30 tickers från `StockMaster`
2. Anropa `QuoteProvider.fetch_quotes(tickers)` — batchat
3. Skriv en rad per ticker till `StockQuote` (history)
4. Upsert till `LatestStockQuote`
5. Logga eventuella fetch-fel utan att krasha jobbet
6. Notifiera frontend via SSE/WebSocket *(V2)* — i V1 räcker att
   frontend pollar var 30:e sek

### Cloud Run-fallgropen

Med `--max-instances=1` är detta enkelt — bakgrundsjobbet körs i
samma process som webben. Men: om instansen sover ner (Cloud Run
suspend efter inaktivitet), missar man pollar. Lösning:
- sätt `--min-instances=1` på prod (lite dyrare, kanske $10/mån)
- eller: använd Cloud Scheduler som pingar ett internt endpoint
  `/internal/poll-quotes` var 5:e min — då vaknar instansen

**Rekommendation:** Cloud Scheduler-varianten. Kostar inget extra
(Cloud Scheduler är gratis upp till 3 jobb), och håller arkitekturen
identisk med dagens.

### Historik-storlek

30 aktier × 12 ticks/timme × 9 timmar × 252 börsdagar/år = **~815
000 rader/år**. Trivialt för Postgres, fungerar i SQLite men gör att
DB-filen växer. Lägg en städnings-jobb som downsampleear quoter äldre
än 90 dagar till 1 quote/dag (close).

## 13. Handelsflöde — köp och sälj

### Aktiekonto

V1 använder befintlig `isk`-kontotyp. Eleven kan ha flera ISK-konton
(t.ex. ett "ISK Aktier" + befintligt "ISK Fonder"). Backend-validering:
en `StockHolding` får bara höra till ett konto med
`account.kind == 'isk'`.

V2-möjlighet: ny kontotyp `depa` (vanlig depå med kapitalvinstskatt
på K4-blankett) — knyts till befintlig `TaxEvent.kind = "k4_sale"`.
Pedagogiskt värdefullt för Företagsekonomi 2 men inte nödvändigt
först.

### Köp-flödet (marknadsorder, V1)

1. Eleven öppnar aktiens detaljsida → klickar "Köp"
2. Modal: antal aktier (eller belopp i SEK med auto-konvertering),
   visar:
   - Aktuell kurs (från `LatestStockQuote`) + tidsstämpel
   - Beräknat courtage
   - Total kostnad
   - Likvid efter köp
   - Disclaimer: "Pris kan variera tills order utförs"
3. Eleven klickar "Bekräfta köp"
4. Backend:
   - Validerar: börsen öppen (kolla `MarketCalendar`), saldo räcker,
     antal > 0
   - Hämtar **senaste** `LatestStockQuote` (inte den eleven såg —
     ärligare)
   - Beräknar courtage (se nedan)
   - Skapar `StockTransaction` (append)
   - Uppdaterar `StockHolding` (insert eller update + ny snittkurs)
   - Skapar en `Transaction` på ISK-kontot: `amount = -total`,
     `category = "Aktieköp"`, `is_investment = True` (ny flagga eller
     använd `metadata`-fältet)
   - Returnerar uppdaterat innehav + ny likvid + executed_at + quote_id
5. Frontend visar bekräftelse: "Köpte 10 Volvo B för 245,50 kr/st.
   Courtage 6,14 kr. Totalt 2 461,14 kr."

### Sälj-flödet

Samma som köp, fast omvänt:
- Validera att eleven har minst `quantity` aktier i `StockHolding`
- Beräkna realiserad vinst/förlust (`realized_pnl = (sell_price -
  avg_cost) * quantity - courtage`)
- Sätt eventuellt `TaxEvent.kind = "k4_sale"` om kontot är `depa`
  (V2)
- Uppdatera `StockHolding.quantity` (radera raden om kvantitet = 0)

### Snittkurs-beräkning (avg_cost)

Standard "viktat genomsnitt":
```
ny_avg_cost = (gammal_quantity * gammal_avg_cost
             + ny_quantity * ny_pris
             + nytt_courtage) / (gammal_quantity + ny_quantity)
```

Ändras inte vid sälj — säljpriset jämförs mot snittkursen för att
beräkna realiserad vinst/förlust.

## 14. Courtage — Avanza Mini

Ni vill matcha Avanza. Avanza har flera klasser; **Mini Courtage** är
default för småsparare och rimligast för pedagogik:

```
courtage = max(1.00, 0.0025 * affärsbelopp)
        # 1 kr minimum, annars 0,25 % av belopp
```

(Avanzas riktiga "Mini" är just 1 kr min, 0,25 %, ingen takgräns för
mini. Andra klasser som Start/Småspar har högre minimi men lägre
procent. Håll det enkelt: en formel, en klass.)

Lagra courtage *som ett separat fält* på `StockTransaction` —
**inte** baka in i `total_amount`. Det är kritiskt för att eleven
ska kunna se "jag betalade X kr i avgifter under året" — pedagogiskt
bra och stöder läraruppdrag som "Räkna ut din total-courtage".

Lägg också en envvar `HEMBUDGET_COURTAGE_MODEL` (default `mini`) så
att läraren kan byta till `start` (39 kr fast) eller `none` (för
övningsklass) — alla tre formler implementeras i en `compute_courtage`
helper.

## 15. Börstider och kalendar

Stockholmsbörsen (Nasdaq Stockholm Main Market):
- Mån–fre 09:00–17:30 CET/CEST
- Stängd: nyårsdag, trettondag, långfredag, annandag påsk, första
  maj, Kristi himmelsfärd, midsommarafton (faktiskt **stängd hela
  dagen** sedan 2021), julafton, juldagen, annandag jul, nyårsafton
- Vissa dagar med tidigare stängning (sällsynt)

Implementation:
- `MarketCalendar`-tabell seedad för 2 år framåt
- En helper `is_market_open(at: datetime) -> bool` används både i
  bakgrundsjobbet (skip polling när stängt) och i orderväg (avvisa
  order när stängt)
- Frontend visar tydligt: badge **"Börsen öppen — stänger 17:30"**
  eller **"Börsen stängd — öppnar måndag 09:00"**

Pedagogisk vinst: elever lär sig att börsen inte är öppen 24/7. Det
är en reell insikt som många unga saknar.

## 16. Köp utanför börstid?

Två val:
- **Strikt:** Avvisa orderförsöket helt. Pedagogiskt rent. Visar
  konsekvenser av börstid.
- **Mjukt:** Acceptera order, märk som `pending`, utför vid nästa
  öppning till då gällande pris. Realistiskt mot Avanza.

**Rekommendation V1:** Strikt. Det förenklar kraftigt (ingen
order-kö-motor) och är pedagogiskt tydligare. V2 kan lägga till
pending-orders.

## 17. Pedagogisk märkning av varje köp/sälj

Varje `StockTransaction` får ett valfritt fält `student_rationale`
(text) — eleven kan skriva "Köper för att Q4-rapporten såg bra ut"
**innan** köpet bekräftas. Inte påtvingat, men:
- Lärare kan tilldela uppdrag "Skriv motivering för varje köp"
- AI kan analysera mönster över tid
- Vid revision kan eleven själv se sina tidigare resonemang

Det här är vad som gör skillnad mellan "spel" och "lärande".

## 18. Lärarintegration

### Klassöversikt `/teacher/investments`

Tabell över alla elever som handlar:
- Företag / namn
- Antal innehav
- Total likvid
- Totalt portföljvärde (likvid + marknadsvärde)
- Realiserad vinst/förlust YTD
- Orealiserad vinst/förlust just nu
- Total courtage spenderad
- Antal trades senaste 7 dagarna
- Senaste trade-tidpunkt

Sortbar och filtrerbar. Klick på elev → drilldown med **hela ledgern**
(varje köp/sälj med tidsstämpel, ticker, antal, pris, courtage,
motivering, quote_id-länk till exakt källdata).

### Lärar-uppdrag (`Assignment.kind`)

Nya kinds som passar in i den befintliga `Assignment`-modellen:

| Kind | Beskrivning | Params |
|---|---|---|
| `stock_open_account` | Öppna ett aktiekonto | `{account_kind: "isk"}` |
| `stock_fund_account` | Flytta likvid till aktiekonto | `{min_amount, target_account_kind}` |
| `stock_buy_specific` | Köp en specifik aktie | `{ticker, min_quantity}` |
| `stock_buy_amount` | Köp för minst X kr i fritt vald aktie | `{min_amount}` |
| `stock_diversify` | Sprid över N olika sektorer | `{min_sectors, min_holdings}` |
| `stock_sell_all` | Sälj alla innehav (lik vidationsövning) | `{}` |
| `stock_calculate_pnl` | Räkna ut vinst/förlust manuellt | `{ticker}` |
| `stock_courtage_total` | Räkna ut total courtage senaste månaden | `{}` |
| `stock_write_motivation` | Skriv motivering för varje köp i vecka | `{}` |

Varje uppdrag har `due_date` och `manually_completed_at` precis som
befintliga Assignments. Lärarens vy "Pågående uppdrag" får automatiskt
de nya kinds — ingen ny UI-kod krävs för listning, bara nya
ikoner/labels.

### Lärarens "skicka marknadshändelse" (V2-möjlighet)

Tänk att läraren ska kunna trycka på en knapp och säga "Telia släpper
Q3-rapport, kursen rasar 8 %". Det skulle påverka den globala
`StockMaster`-poolen — vilket är **fel** eftersom alla elever delar
den. Bättre: introducera en **scope-overlay**: `StockEvent` per
scope (sällsynt) som modifierar pristrenden. Komplext — håll utanför
V1.

## 19. Modulen "Aktier — komma igång"

Ny systemmodul i `module_seed.py`. 8 steg, idempotent seedad. Läraren
tilldelar den med ett klick.

1. **`read`** — *Vad är en aktie?* (200 ord, lättläst svenska)
   Aktie = del av ett företag. Pris bestäms av utbud/efterfrågan.
   Värdet kan både öka och minska.

2. **`task: stock_open_account`** — *Skapa ditt första aktiekonto*
   Eleven klickar på `/accounts` → "Nytt konto" → väljer ISK → namnger
   det. Steg auto-markeras klart vid skapande.

3. **`task: stock_fund_account`** — *Flytta 10 000 kr till ditt
   aktiekonto* (testar **direkt** överföringsfunktionen från del 1!).
   Använder `make_transfer`-uppdragstypen från sektion 6.

4. **`read`** — *Riskspridning — varför du inte ska lägga alla ägg
   i en korg* Förklarar sektorbegreppet, kopplar till de 30
   tillgängliga aktierna grupperade per sektor (Industri, Bank,
   Telecom, Hälsa, Konsument, IT, Råvaror, Fastighet).

5. **`task: stock_diversify`** — *Köp 5 aktier från minst 3 olika
   sektorer, max 2 000 kr per aktie*. Auto-markeras klart när
   `StockHolding` har minst 5 olika tickers från minst 3 olika
   `StockMaster.sektor`-värden.

6. **`read`** — *Courtage, spread och varför din avkastning är
   mindre än kursen visar* Visar elevens **egna** courtage-data:
   "Du har spenderat 23,40 kr i courtage hittills. Det är 0,7 % av
   ditt portföljvärde."

7. **`quiz`** — Kontrollfrågor:
   - Vad händer med ett aktiebolags värde om alla vill sälja?
   - Vad är skillnaden mellan ISK och en vanlig depå?
   - Räkna ut courtage för ett köp på 4 500 kr (= max(1, 11,25) =
     11,25 kr)
   - Vad är en sektor? Ge tre exempel.

8. **`reflect`** — *Var det svårt att välja? Vad lärde du dig?*
   Rubric-bedömt via befintlig `score_with_rubric`. Kriterier:
   "Förståelse för risk", "Förståelse för courtage", "Egna
   reflektioner".

Kompetenser (nya rader i `competency_seed.py`):
`stock_basics`, `risk_diversification`, `courtage_understanding`,
`portfolio_thinking`.

## 20. AI-integration

| Funktion | Modell | Var | Pedagogiskt syfte |
|---|---|---|---|
| `explain_stock_term` | Haiku | ny i `ai.py` | Eleven hovrar ord som "P/E-tal", "spread", "utdelning" och får 1-mening-förklaring |
| `evaluate_diversification` | Haiku, tool_use | ny | Bedömer portföljens spridning (sektorvikter, antal innehav) och returnerar kommentar |
| `feedback_on_trade` | Haiku | ny | Efter varje köp/sälj — kort kommentar "Du köpte Volvo. Industri-sektorn är cyklisk — bra om du tror på konjunkturuppgång." |
| `answer_student_question` | Sonnet, **befintlig** | utvidga prompt-kontext | Aktieterminologi och svensk skatt |
| `score_with_rubric` | Sonnet, **befintlig** | — | Rubric-bedömning av reflektionssteg 8 |

**Strikt regel som måste respekteras i prompten:** AI får aldrig ge
finansiell **rådgivning** (köp/sälj-rekommendationer för enskilda
aktier). Endast **förklaringar** och **observationer** av elevens
egna val. Lägg detta som ett hårt direktiv i systemprompten och
testa med adversarial prompts. Det här är både juridiskt skyddande
(simulator i skola, inte rådgivning) och pedagogiskt rätt — eleven
ska tänka själv.

Token-räkning: alla anrop går genom `_record_usage` (befintlig).
Sätt en **soft cap per elev per vecka** för aktie-AI specifikt
(`Teacher.ai_stock_weekly_cap`) — annars kan en elev som hovrar
över 50 ord trigga onödiga kostnader.

## 21. Frontend-undersida `/investments`

### Elev-vyn

Toppnivå i sidofältet, ikon "trending_up". Sektioner:

- **Översikt** — totalt portföljvärde, dagens förändring, total
  realiserad/orealiserad vinst, sektorvikter (donut chart)
- **Mina aktier** — lista av `StockHolding` med live-värdering
- **Marknad** — alla 30 tillgängliga aktier sorterbara per kurs,
  förändring %, sektor; klick → detaljvy med graf + köp/sälj
- **Order-historik (Ledger)** — hela `StockTransaction`-loggen,
  filtreringsbar per ticker/datum/typ
- **Watchlist** — favoriter eleven flaggat (ny scope-tabell
  `StockWatchlist`)

### Lärarens drilldown `/teacher/investments/:student_id`

- Aggregerade siffror i kortrad
- **Ledger-vy** — exakt samma data som eleven ser, men med extra
  kolumn "Quote source" som visar `quote_id` → exakt
  polldata-tidsstämpel + källa
- "Lägg till uppdrag" — snabbt ge eleven en av kinds från
  sektion 18

### Pedagogisk widget — "Vad om?"

På varje innehavskort: knapp "Vad om jag inte hade köpt detta?".
Räknar `quantity * (current_price - alternative_baseline)` där
baseline = OMXS30-index från samma datum. Visar "Du har gjort 230 kr
*sämre* än om du hade köpt en indexfond". Smärtsam men sann
pedagogik om aktiv förvaltning vs index.

## 22. ISK-skatt — koppla in befintlig motor

`ISKCalculator` i `api/tax.py` beräknar idag schablonskatt på
kvartalsvärden. Det den behöver är **portföljens samlade värde** —
inte bara fonder. Lös genom att utöka `_quarterly_value()` (eller
motsvarande metod) så att den inkluderar:

```
quarterly_value = likvid_på_isk_konto
                + sum(StockHolding.quantity * StockQuote_close_at_quarter)
                + sum(FundHolding.market_value)
```

Det enda som ändras är *underlaget* — formeln (statslåneränta + 1 %,
schablon på underlaget) är samma. **Inga schemaändringar**.

För Företagsekonomi 2 är det här en pedagogisk poäng: schablonskatten
straffar inte vinst, den straffar *värde*. Eleven kan göra förlust
och ändå betala skatt.

---

# DEL 3 — Optimeringar och risker (gemensamt för båda)

## 23. Prestanda och skalning

- **Saldoberäkning vid många transaktioner:** Idag räknas saldot
  live från alla transaktioner. När en aktiv elev har 200+ trades +
  privatekonomi-transaktioner blir det tungt. Lösning *när det
  behövs*, inte nu: snapshot-tabell `AccountBalanceSnapshot` som
  uppdateras vid varje transaktion (cache-invalideringen är
  kontrollerad eftersom alla muteringar sker via era endpoints).
- **Kursgrafer:** Frontend-komponenten ska aldrig ladda 815 000
  rader. Servern aggregerar baserat på vald period (1d → råa quoter
  senaste dygnet, 1w → 30-min bars, 1y → dagsclose). Lägg detta i
  `GET /stocks/:ticker/history?period=1d|1w|1m|1y`.
- **Frontend-bundle:** En ny route med charting (recharts) +
  drag-and-drop + tabeller adderar storlek. Lazy-load
  `/investments`-rutten med `React.lazy`. Recharts redan i
  beroendena — ingen ny dep.
- **Polling vs WebSocket:** V1 frontend-polling var 30:e sek räcker
  gott för 30 elever × 10 öppna flikar = 600 anrop/min mot
  `LatestStockQuote`-endpoint. Det är trivialt. SSE/WebSocket först
  vid behov.

## 24. Kostnadskontroll

- **Datakälla:** Finnhub gratis 60/min räcker för 30 aktier var 5:e
  min (= 6/min). Yfinance gratis utan limit men opålitlig.
  Värsta-fall budget: $50/mån för Alpha Vantage premium om båda
  fallar.
- **AI-tokens:** `feedback_on_trade` triggas vid varje köp/sälj.
  Aktiv elev gör kanske 10 trades/vecka × 30 elever = 300 anrop/v.
  Med Haiku ~$0,25/mån/lärare. Trivial om man har caching på
  systemprompten.
- **Cloud Run:** `--min-instances=1` för att hålla bakgrundsjobbet
  vaket = ca $10–15/mån. Alternativ Cloud Scheduler är gratis.
- **DB-storlek:** 815k quote-rader/år ~= 80 MB SQLite. Postgres-
  fallback ändå rekommenderad innan ni har >200 elever.

## 25. Säkerhet och dataskydd

- **API-nycklar för kursdata:** Lagra som Cloud Run-secret, aldrig
  i kod eller frontend. `FINNHUB_API_KEY` exponeras *aldrig* till
  klient — alla quoter går via er backend.
- **Rate limiting:** Befintlig sliding window i `security/rate_limit.py`
  räcker. Lägg en strikt limit på `/stocks/:ticker/buy` och
  `/stocks/:ticker/sell` (t.ex. 60 trades/timme/elev) för att hindra
  spam-trading-bots eller frustrerade elever som klickar 100 ggr.
- **Audit-trail:** Alla `StockTransaction` är append-only. Lägg en
  databas-trigger eller en CI-test som verifierar att inga
  DELETE/UPDATE körs mot tabellen. Det är revisorns garanti.
- **PII:** Inget extra — eleven loggas redan via scope-systemet,
  ingen ny känslig data.

## 26. Pedagogiska fallgropar

- **Spel-känsla:** Risk att modulen blir "Robinhood för barn" och
  uppmuntrar daytrading. Motverka:
  - Visa courtage-summan tydligt på dashboard ("Du har spenderat
    56 kr i avgifter denna vecka — det är X % av dina vinster")
  - "Vad om?"-widgeten (sektion 21) som jämför mot indexfond
  - Modulens `read`-steg betonar långsiktigt sparande
  - Reflektionssteg som tvingar eleven att motivera sina val
- **Fiktiva pengar respekteras inte:** Risk att eleven tar absurda
  risker eftersom det "inte är riktiga pengar". Motverka genom att
  låta läraren ge "klassens portföljmästare"-utmärkelse efter ett
  läsår — ger social vikt.
- **Marknadsförståelse vs lyckokast:** En elev kan tjäna mycket på
  ren tur (en aktie råkar gå upp 30 %). Pedagogen behöver kunna säga
  "Bra resultat — men kan du förklara *varför*?". Det är därför
  `student_rationale` och reflektionssteget är viktiga.

## 27. Konflikter med befintlig kod

- `Account.kind` är `varchar(20)` — `isk` finns redan, ingen
  schemaändring krävs för kontotyp.
- `Transaction` får ny *implicit* användning ("Aktieköp"-kategori)
  — ingen ny kolumn behövs om ni använder `metadata`/`tags`-fält.
  Verifiera att `metadata` finns; annars lägg till `is_investment`-
  bool eller bara använd specifika kategori-namn.
- `MasterBase`-tabeller `StockMaster`, `StockQuote`,
  `LatestStockQuote`, `MarketCalendar` läggs till i
  `school/engines.py::_run_master_migrations` med ALTER TABLE-checks
  per CLAUDE.md.
- Per-scope-tabeller (`StockHolding`, `StockTransaction`,
  `StockWatchlist`) hanteras av `db/migrate.py::run_migrations`.

## 28. Implementationsplan i faser

**Fas A — Överföringar (3–5 dagar):**
- Ny endpoint `POST /transfers/create` med validering
- `TransferModal` på Accounts-sidan
- Idempotency-key + UNIQUE-constraint
- Lägg till `make_transfer`-uppdragstyp
- Tester: happy path, samma konto blockeras, negativt blockeras,
  insufficient funds blockeras
- → Använd som onboarding-byggsten för aktiemodulen

**Fas B — Aktiekursinfrastruktur (1 vecka):**
- `StockMaster` seedat med 30 OMXS30
- `MarketCalendar` seedat 2 år
- `QuoteProvider`-interface + `YFinanceProvider`
- Bakgrundsjobb i `lifespan` + Cloud Scheduler-pinger
- `StockQuote`/`LatestStockQuote`-tabeller
- `GET /stocks/:ticker`, `GET /stocks/:ticker/history`
- Frontend: `/investments` placeholder med statisk lista
- → Verifiera att kurser uppdateras live, ingen handel än

**Fas C — Handel (1 vecka):**
- `StockHolding`, `StockTransaction` (append-only)
- `POST /stocks/:ticker/buy`, `POST /stocks/:ticker/sell`
- Avanza Mini-courtage-formel + envvar
- `compute_courtage` helper
- Köp/sälj-modal i frontend
- Order-historik-vy
- Tester: börstid-blockering, saldo-validering, snittkurs-beräkning,
  realiserad pnl-beräkning
- → End-to-end fungerande för en elev

**Fas D — Modul + lärare (1 vecka):**
- Seed "Aktier — komma igång" i `module_seed.py`
- Nya kompetenser i `competency_seed.py`
- 9 nya `Assignment.kind` + UI för lärare att tilldela
- `/teacher/investments` klassöversikt + drilldown med ledger
- AI-funktioner: `explain_stock_term`, `evaluate_diversification`,
  `feedback_on_trade`
- → Klassrums-redo

**Fas E — Polish och pedagogik (3–5 dagar):**
- "Vad om?"-widget (jämför mot OMXS30-index)
- ISK-skatte-koppling i `_quarterly_value`
- Watchlist
- Sektorvikter-donut chart
- Token-cap per elev/vecka
- Klassens topplista (anonym, opt-in per lärare)

**Total tid:** ~4–5 veckor för full leverans, men Fas A ensam ger
omedelbart värde och kan lanseras separat.

## 29. Vad ni ska besluta före kod

1. **Datakälla för kurser:** yfinance gratis (risk för avbrott)
   eller Finnhub-nyckel (kräver registrering, gratis nivå räcker)?
   Min rekommendation: börja med `QuoteProvider`-interface och båda
   som plug-ins, default yfinance.
2. **`min-instances=1` eller Cloud Scheduler för polling?** Min
   rekommendation: Cloud Scheduler (gratis, lättare att förklara).
3. **Strikt vs mjuk hantering utanför börstid?** Min rekommendation:
   strikt i V1.
4. **Fraktionella aktier?** Min rekommendation: nej i V1 (heltal
   bara), spegla Avanza Mini-erfarenhet.
5. **Limit-orders i V1?** Min rekommendation: nej, bara marknadsorder.
6. **Aktielista — strikt OMXS30 eller bredare 30 stycken?** Min
   rekommendation: OMXS30 (välkänt, pedagogiskt, regelbundet
   uppdaterat). Komplettera ev. med 1–2 utanför (Tesla?) för
   internationell exponering — men då måste valutaomräkning lösas.
   Håll SEK-only i V1.
7. **Företags-modulens kassa kopplas till aktiekonto?** Får
   företagskassan investera i aktier? Realistiskt
   (likviditetsförvaltning) men komplicerar. Min rekommendation:
   nej i V1 — håll privat och företag separata.
8. **Watchlist på Stock-nivå eller Account-nivå?** Min
   rekommendation: per scope (en watchlist per elev) — enklast.

---

# Sammanfattning

**Del 1 — Överföringar:** Liten tilläggsfunktion ovanpå redan
existerande infrastruktur. Ingen ny modell, en ny endpoint, en ny
modal. Levererbar på en vecka och blir omedelbart byggsten för Del 2.

**Del 2 — Aktiehandel:** Större men välavgränsad funktion. Kräver:
- Ny global tabell-trio (`StockMaster`, `StockQuote`,
  `LatestStockQuote`) + `MarketCalendar`
- Två nya scope-tabeller (`StockHolding`, `StockTransaction`)
- Ett bakgrundsjobb (kursprispolling)
- Tre nya AI-funktioner (alla pedagogiska, ej rådgivning)
- En ny systemmodul + 9 nya Assignment-kinds
- En ny lärarsektion `/teacher/investments` med fullständig
  ledger-drilldown
- Återanvänder befintlig ISK-skatteberäkning, befintlig
  Module/Step-infrastruktur, befintlig AI-token-mätning

**Total leveranstid:** 4–5 veckor med tydlig faseplan där varje fas
är livefärdig.

**Största risken:** datakällans tillförlitlighet. Mitigering:
abstrakt provider-interface med fallback. Allt övrigt är hantverk
ovanpå er befintliga arkitektur.

**Pedagogisk vinst:** Eleven får en sömlös resa från privatekonomi
→ överföring till aktiekonto → riskspridning → faktisk handel →
reflektion, allt i ett verktyg läraren kan följa beslut för beslut.

