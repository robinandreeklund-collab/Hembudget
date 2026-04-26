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
