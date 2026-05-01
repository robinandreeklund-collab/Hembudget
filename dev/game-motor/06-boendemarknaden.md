# 06 · Boendemarknaden

> Köp / sälj / flytta. Realistisk svensk bostadsmarknad med bolån,
> amortering och pentagon-konsekvenser.

## Befintligt fundament

Vi har redan:
- `db::Loan` · bolån med ränta + amortering
- `db::RentalContract` · hyresavtal
- `loans::matcher` + `scenarios::engine::MortgageEngine` · KALP-räknaren
- `loans::credit::compute_kalp` · funktion som körs vid bolåneval
- `MortgageDecision` · spårning av elevens val (från modul-uppdrag)

Spelmotorn knyter ihop dessa till en **levande marknad**.

## Marknads-data

### Bostadsrätt-priser (kr/m²)

Per stad, uppdaterad månadsvis i Monthly Engine:

```yaml
stockholm:
  initial_price_per_kvm: 78000
  monthly_drift_pct: { mean: 0.4, std: 0.8 }   # +/- volatilitet
  yearly_trend: 0.05  # 5%/år 2026 (lokal prognos)

göteborg:
  initial_price_per_kvm: 56000
  monthly_drift_pct: { mean: 0.3, std: 0.7 }
  yearly_trend: 0.04

malmö:
  initial_price_per_kvm: 42000
  monthly_drift_pct: { mean: 0.3, std: 0.7 }
  yearly_trend: 0.035

medelstad:
  initial_price_per_kvm: 32000
  monthly_drift_pct: { mean: 0.2, std: 0.5 }
  yearly_trend: 0.03

småort:
  initial_price_per_kvm: 18000
  monthly_drift_pct: { mean: 0.1, std: 0.3 }
  yearly_trend: 0.02
```

Värdering uppdateras månadsvis så elevens egen bostad har en levande
"värd just nu"-summa.

### Hyresrätter

- Hyresrätter har inget köp/säljvärde
- Hyran är fast (kontrakt) men förhandlas via Hyresgästföreningen +1.5–2 %/år
- Förstahandskontrakt är guld (slumpas vid skapelse, kan inte få nytt
  utan kö-tid)
- Andrahandskontrakt kan slumpas via events ("Erbjudande från vän")

### Villor

- Per stad finns en pool av villor med drift + tomtstorlek
- Villor har högre drift (uppvärmning, underhåll)
- Vid köp: större kontantinsats krävs (bolån max 75 % av värdet
  förstagångs-köpare 2026)

## Köp-flödet

När eleven vill flytta från hyresrätt → bostadsrätt eller uppgradera:

```
1. Eleven öppnar /v2/hyresvarden ELLER /v2/lan
2. Klickar "Köp ny bostad" (ny knapp)
3. UI visar:
   - Föreslagna bostäder i staden (3–5 från pool)
   - Filter: storlek, max pris, område
4. Eleven väljer en bostad
5. KALP-räknare körs (befintlig logic)
6. UPPDRAG från lärare alt. self-driven:
   - Räkna ränta-bunden vs rörlig
   - Räkna amorteringsplan
   - Eleven gör val
7. Bolån skapas (db::Loan)
8. Befintligt boende:
   - Hyresrätt → uppsägning + 3 mån uppsägningstid
   - Bostadsrätt → säljs på "marknaden" (3–6 mån i spel)
9. Pentagon-effekter
```

## Sälj-flödet

```
1. Eleven kan när som helst klicka "Sälj min bostad"
2. UI visar nuvarande marknadsvärde + estimerad försäljning
3. Försäljningen tar 2–6 spelmånader (slumpas)
4. Under tiden: visningar ger mindre wellbeing-effekter
5. Vid genomslag: kapital-tillskott (efter mäklarkostnad + reavinstskatt)
6. Bolånet löses
7. Eventuell uppskovsräntor (om eleven köper nytt)
```

## Flytt-flödet (samma stad)

Lättare än köp/sälj. Bara byter bostad inom samma typ:
- Hyresrätt → ny hyresrätt (kö eller andrahand)
- Bostadsrätt → bostadsrätt (köp + sälj-process)

## Stadsbyte

Triggas vid:
- Jobbyte i annan stad (Arbetsförmedlingen)
- Privat val (Echo kan föreslå "har du tänkt på Göteborg?")
- Familje-event (sambo flyttar dit, etc)

Konsekvenser:
- Allt boende säljs/sägs upp + nytt köps/hyrs
- Pentagon: -8 social (initialt), +3 karriär (om jobbet är skälet)
- Återhämtning över 3–6 spelmånader

## Pentagon-konsekvenser

| Action | Pentagon-effekt |
|---|---|
| Köp första bostadsrätt | +5 safety, -10 economy (kontantinsats) |
| Uppgradera bostadsrätt (större) | +3 safety, +2 leisure, -5 economy |
| Nedgradera (sälj och hyr) | -2 safety, +5 economy |
| Sälja vid prisuppgång (vinst) | +8 economy |
| Sälja vid prisnedgång (förlust) | -8 economy, -2 safety |
| Flytta inom stad | +2 leisure (om uppgradering) |
| Flytta annan stad | -8 social, +3 karriär (om jobb-skäl) |
| Köpa villa (singel + ung) | +2 safety, -15 economy, -3 leisure (drift) |

## Räntor (uppdaterade månadsvis)

Befintlig `school::InterestRateSeries` har redan strukturen. Spelmotorn
fyller den med 2026-data:

```yaml
interest_rate_history:
  - { year_month: "2026-01", policy: 2.50, bolan_rorlig: 4.20, bolan_3ar: 3.85 }
  - { year_month: "2026-02", policy: 2.50, bolan_rorlig: 4.15, bolan_3ar: 3.80 }
  - { year_month: "2026-03", policy: 2.25, bolan_rorlig: 4.00, bolan_3ar: 3.70 }
  ...
```

Vid varje månadstick:
- Rörlig ränta uppdateras (kan ändra elevens månadskostnad)
- Bunden ränta uppdateras för pris-inspiration
- Echo varnar vid stora rörelser ("Räntan steg 0,5 % — är du orolig?")

## Sambo + bostads-delning

Om partnermodell = "ai" eller "klasskompis":
- Sambon kan stå för del av boendekostnad (fördelning enligt
  fairness_choice från onboarding)
- Vid uppgradering: båda måste "godkänna" (eller eleven gör det själv om
  ai-partner)
- Vid separation (slumpas vid problem-event): bodelning, sälj, etc

## Implementation

```
backend/hembudget/game_engine/
  housing_market/
    __init__.py
    market.py              # Per-stad marknadsdata + drift
    listings.py            # Pool av tillgängliga bostäder per stad
    transaction.py         # Köp + sälj-processer
    valuation.py           # Månatlig värdering av elevens boende
    api.py                 # /v2/boendemarknad/* endpoints
```

## Endpoints

| Metod | URL | Syfte |
|---|---|---|
| GET | `/v2/boendemarknad/listings` | Tillgängliga bostäder i elevens stad |
| GET | `/v2/boendemarknad/my-home/valuation` | Aktuellt värde på min bostad |
| POST | `/v2/boendemarknad/buy/{listing_id}` | Starta köpprocess |
| POST | `/v2/boendemarknad/sell` | Lägg ut för försäljning |
| GET | `/v2/boendemarknad/active-transactions` | Pågående köp/sälj |
| POST | `/v2/boendemarknad/move-city/{city_key}` | Initiera stadsbyte |

## Frontend

Befintliga vyer utökas:
- `/v2/lan` (Lånegivaren) → ny knapp "Bolåne-kalkylator + sök bostad"
- `/v2/hyresvarden` (Hyresvärden) → ny knapp "Köp egen bostad"
- Ny vy: `/v2/boendemarknad` med listings + min bostad

## Echo-coaching

Echo har starka triggers i bostadsdomänen eftersom det är livets
största ekonomiska beslut:

- Innan köp: "Har du KALP-räknat? Vad händer vid +2 % ränta?"
- Vid stor ränte-rörelse: "Räntan ökar — är din bunden eller rörlig?"
- Vid uppgradering: "Behöver du verkligen mer plats? Räcker det
  inte med renovering?"
- Vid säljbeslut: "Vinster är skattepliktiga — har du räknat?"

## Lärar-konfiguration

Lärare kan välja per klass:
- "Aktiv bostadsmarknad" (på/av) — om av: hyresrätt-bara, ingen sälj
- "Värderings-volatilitet" (låg/normal/hög) — för olika scenarion
- "Förbjud Stockholm" (för pedagogisk fokus på medelstad)
