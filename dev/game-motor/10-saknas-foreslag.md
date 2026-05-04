# 10 · Saknas i ursprungsförslaget

> Spec-författarens utökningar. Saker som krävs för en komplett
> spelmotor men inte explicit nämndes i originalförslaget.

## A · AI-tokenbudget per motor

Echo, Maria, Mats, AI-anrop i Profile Generator (om vi använder LLM
för flavor-text) — alla konsumerar Anthropic API-tokens. Vi behöver
**budget per motor** och **lärar-budget per klass**.

```yaml
ai_budget:
  monthly_max_tokens_per_class: 5_000_000
  weighting:
    echo: 0.50          # Eleven använder mest
    maria: 0.20         # 5-rond per förhandling
    mats: 0.20          # 5-rond per intervju
    profile_flavor: 0.05
    teacher_chat: 0.05
```

Implementation:
- Befintligt `_token_count` i Maria utökas till alla AI-anrop
- Daglig kvarvarande visas i lärar-hub
- Vid 80 % → varning, vid 100 % → fallback (canned responses)

## B · Reverse-engineering pedagogik (audit trail)

Lärare måste kunna förstå **exakt** varför pentagonen ändrades.
Befintlig `WellbeingFactor` är start, men vi behöver utöka med:

- Tidsstämpel per ändring
- Källa-länk (klickbar till MailItem, Module, etc)
- Lärar-kommentar (frivillig anteckning)

Ny vy: `/teacher/v2/elev/:id/wellbeing-trail` med komplett
spårning per axel.

## C · Karaktärs-kontinuitet över semester

När klassen pausar (sommarlov):
- Karaktärens "interna liv" pausas (inga events)
- Men eleven ska kunna logga in och **planera** för hösten
- Echo kan vara aktiv i "planeringsläge" utan att tid passerar

När klassen återupptar:
- "Sammanfattning av sommaren"-notis (vad hade hänt om tid passerat)
- Pedagogisk reflektion-uppgift om sommarens val

## D · Sociala faktorer utöver sambo

Originalförslaget har sambo + barn. Vi behöver också:

- **Vänner**: nätverk-events ("Vän bjöd på middag" = -300 kr leisure)
- **Föräldrar**: åldrande föräldrar kan trigga events ("Mamma sjuk")
- **Kollegor**: arbets-relationer påverkar safety
- **Klasskompisar**: peer-review-system finns men kan utökas

## E · Skola/utbildning-spår

För elever som spelar gymnasie-yngre karaktärer:
- Kan eleven söka högre utbildning?
- CSN-flöde (befintligt) integrerat
- Effekt: paus i jobbet, lägre lön under utbildning, högre lön efter

## F · Hälso-svängningar

Originalförslaget nämner tandläkare. Vi behöver också:
- Akut sjukdom (förkylning · -2 hälsa, +1 leisure tvångs-vila)
- Kroniska tillstånd (slumpas vid Profile Generator)
- Mental hälsa (stress-ackumulering → utbrott)
- Träning (modul-baserat: yoga, löpning ger +hälsa)

## G · Arbets-relaterade problem

- Mobbning på jobbet (- safety, - hälsa)
- Bossy chef (- safety) — utlöser jobbsökande från Arbetsförmedlingen
- Befordran (intern, parallell till jobbyte)
- Sjukskrivning (- ekonomi om ingen försäkring)

## H · Bostadsbyte vid jobbyte

Om eleven byter jobb i annan stad:
- Auto-trigger boendemarknads-flöde
- 3 mån överlapp där eleven betalar båda boenden
- Pendlings-alternativ (om realistiskt)

## I · Skuldfälla-eskalering

Befintlig `PaymentMark` + `CreditCheck` + `is_high_cost_credit` finns.
Spelmotorn aktiverar dem:
- Obetald faktura → påminnelse → inkasso → KFM
- SMS-lån-frestelse i events ("Du har 500 kr kvar och behöver mat")
- Konsekvens-kedjor över 3–6 spelmånader

## J · Statliga ändringar

Halv-årligt slumpas:
- Ränte-höjning från Riksbanken (påverkar bolån)
- Skatte-justering (kommunal)
- Försäkrings-premier (pris-höjning)
- Inflation-event (Konsumentverket-tabell justeras)

## K · Ekonomiska kris-event (säsongsbundna)

Vid Q3-Q4 år 2 finns chans (~10 %) för:
- Lokal kris (företaget varslar)
- Global kris (lågkonjunktur, bostadspris-fall)
- Energi-chock (el-räkningen dubblas)

Pedagogiskt värde: visa hur buffert + diversifiering räddar.

## L · Arvskifte / arv

Slumpas mycket sällan (~1 % per år):
- Mor-/farförälder dör → arv på 30 000 – 200 000 kr
- Pedagogisk reflektion: vad gör du med pengarna?
- Försäkrings-event: livförsäkring kan trigga om partner dör

## M · Stora livsförändringar

Befintlig partner-modell stödjer:
- Sambo → gift (events)
- Sambo-separation (events)
- Barn (om både flickor)

Behöver också:
- Dödsfall i familjen
- Adoption
- Föräldraledighet → -ekonomi, +relation, +hälsa

## N · Pension-väljare

PPM/premiepension-val (befintlig PensionAssumption):
- Eleven kan välja fonder själv
- Echo coachar mot indexfond
- Långsiktig pedagogisk effekt: 30 års val visar i pensions-prognosen

## O · Försäkrings-paket-nivåer

Per försäkringskategori finns 2–4 nivåer:
- Hemförsäkring: bas / standard / premium
- Tandförsäkring: ingen / privat / tilläggs-tand
- Bilförsäkring: trafik / halv / hel

Eleven väljer balans pris vs skydd.

## P · Privatlån / SMS-lån-fälla

Pedagogiskt **kritiskt** att eleven förstår dessa. Events:
- Frestelse-mail från SMS-företag ("Klicka för 5000 kr nu")
- Konsekvens om eleven tar ut: -ränta-anmärkning, KFM, blockerade
  bolån

## Q · Datasekretess och GDPR

Allt eleven gör loggas. Lärare har full insyn (Fas 2Y aktivitets-
historik). Vi behöver:
- Tydlig policy: vad sparas, hur länge, vem ser
- Elev-rätt att exportera egen data (CSV)
- Vid läsårs-slut: anonymisera eller radera

## R · Lärar-konfiguration per klass

Olika klasser olika fokus:
- Bygg-program: fokus på snickeri-yrket + bil-ekonomi
- Sjuksköterske-program: fokus på vård-yrket + arbetstid
- Ekonomi-program: fokus på ISK, aktier, skatt

Lärare väljer **modul-paket** som låser/öppnar viss ekonomi-domän.

## S · Multiplayer-effekter

När klasskompisar interagerar:
- Peer-review-system (befintligt)
- Klasskompis-paring (Modell C)
- Klass-mål (gemensam wellbeing-utmaning)
- "Fråga klassen"-funktion (anonymt)

## T · Time-zone & helger

Beskrivet i `08-tidsmodell.md`. Sammanfattat:
- Europe/Stockholm
- Helgdagar respekteras
- Lov pausas

## U · Validering & balanstest

Beskrivet i `09-difficulty-levels.md`. Sammanfattat:
- Monte Carlo per nivå (10 000 körningar)
- Mål-kvantilavstånd
- Iteration på SEVERITY_BY_LEVEL

## V · Migrering av befintliga elever

V1-elever har data men inget StudentProfile. När vi rullar ut spelmotorn:
- Auto-detection: om scope-DB har transaktioner → behåll dem
- Profile Generator körs för alla v1-elever som inte har profil
- Lärar-kontroll: "Migrera klass" eller "Behåll v1"

## W · Performance

- 28 elever × 4 ticks/månad = 112 ticks/månad/klass
- 100 klasser → 11 200 ticks/månad
- Per tick: ~50 ms (Monthly Engine)
- Total: ~9 minuter cron-tid/månad
- Skalbart till tusentals klasser med async + worker-pool

## X · Failure modes

Vad händer om eleven misslyckas totalt?
- Inkasso-stack → KFM-anmärkning → blockerat bolån
- Ingen "game over" — eleven kan alltid fortsätta
- Lärare kan rewind eller hjälpa (säkerhetsnät)

## Y · Återställning

Lärare kan rewind till tidigare ym (befintlig idé). Tillägg:
- Auto-snapshot var 3:e månad (för säker rewind)
- Snapshot-storage: GCS-fuse på Cloud Run

## Z · Internationell utflyttning (avancerat)

Pedagogiskt: vad händer om karaktären flyttar utomlands?
- Skatte-effekter (avskrivning från Sverige)
- Pension-effekter
- Försäkring (paus / nytt avtal)

Endast på nivå 3 + via specifik modul.

## ÅÄÖ · Övriga

- **Side quests** från lärare (frivilliga utmaningar utöver assignments)
- **Karaktärs-arc** (kapitel-system: månad 1=etablering, 6=kris, 12=utvärdering)
- **Notification scheduling** (vilka events ska vänta över helgen?)
- **Audit trail** (varje wellbeing-ändring spårbar)
