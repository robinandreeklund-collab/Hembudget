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

