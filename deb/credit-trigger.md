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

*(Fortsätter i nästa commit: privatlån-flödet, SMS-lån, datamodell.)*
