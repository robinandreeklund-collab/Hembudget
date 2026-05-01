# 14 · Monte Carlo · validerings-resultat (Fas 8 V1)

> Initial Monte Carlo-körning · 300 simuleringar per (level × spend_profile)
> Genererad efter Sprint 1-6 + post-analys (sjuk + budget-fix)

## Resultat — initial körning

```
Nivå 1 sparsam     pos= 95.7% mar=  0.7% neg=  3.7% median= +125 662 kr
Nivå 1 balanserad  pos= 94.3% mar=  1.3% neg=  4.3% median= +110 420 kr
Nivå 1 slosa       pos= 89.7% mar=  3.7% neg=  6.7% median=  +91 345 kr
Nivå 2 sparsam     pos= 98.7% mar=  0.0% neg=  1.3% median= +147 051 kr
Nivå 2 balanserad  pos= 98.0% mar=  0.7% neg=  1.3% median= +134 678 kr
Nivå 2 slosa       pos= 95.3% mar=  2.3% neg=  2.3% median= +111 032 kr
Nivå 3 sparsam     pos= 99.0% mar=  0.3% neg=  0.7% median= +182 832 kr
Nivå 3 balanserad  pos= 99.0% mar=  0.0% neg=  1.0% median= +169 421 kr
Nivå 3 slosa       pos= 97.3% mar=  1.7% neg=  1.0% median= +145 894 kr
```

## Analys

**Klassificering:**
- `positive` = end-of-year-balans ≥ +5000 kr (sparat)
- `marginal` = -10000 ≤ balans < +5000 (jämnt)
- `negative` = balans < -10000 (skuldsatt)

### Vad fungerar bra

- **Nivå 1 sparsam (95.7 % positiv)** matchar designmål ~90-95%. Spelare
  som börjar och spenderar försiktigt klarar sig bra — pedagogiskt
  rimligt.
- **Slumpmässig variation syns**: nivå 1 sparsam median +125k vs slosa
  +91k → spend_profile-multipliern på 0.85/1.00/1.25 har realistisk
  effekt (~30% diff över året).
- **Nivå 1 slösa har 6.7 % negativ** — pedagogiskt värdefullt: cirka
  var 15:e elev hamnar i skuldfälla, vilket öppnar för läraren-coaching.

### Vad behöver kalibreras (V2 i fas-grupp)

**Nivå 2 och 3 är för "snälla"** jämfört med spec:
- Spec: nivå 2 balanserad = 60-70 % positiv → uppmätt 98 %
- Spec: nivå 3 slösa = 30-40 % positiv → uppmätt 97 %

Detta är förväntad upptäckt — vi har MEDVETET inte injicerat större
oväntade kostnader för nivå 2-3 ännu. Plan för V2 (Fas 8b):

1. **Difficulty-multiplikator på event_engine** — nivå 3 ska få fler
   "tunga" events (vattenskada, varsel, kvarskatt) per månad
2. **Difficulty-multiplikator på sjuk-frekvens** — nivå 3 har fler
   långa sjukperioder → större lönebortfall
3. **Difficulty-multiplikator på fasta utgifter** — nivå 3 har dyrare
   stadsplacering eller större boende
4. **Större event-cost-spread** — vattenskada cost_range kan höjas
   för nivå 3 (t.ex. 30k-80k istället för 15k-45k)

### Slutsats

Monte Carlo-verktyget fungerar och ger oss en kvantifierad bild av
spelmotorns balans. Vidare kalibrering är arbete för Fas 8b/9.

## Användning

```bash
# CLI · enskild körning
python -m hembudget.game_engine.monte_carlo --n 1000 --level 1 --spend sparsam

# CLI · grid över alla 3×3
python -m hembudget.game_engine.monte_carlo --n 500 --grid

# CLI · JSON-output för pipelineintegration
python -m hembudget.game_engine.monte_carlo --grid --json

# Endpoint (lärar-token krävs)
POST /v2/teacher/monte-carlo
{
  "n_simulations": 1000,
  "starting_level": 2,
  "spend_profile": "balanserad",
  "partner_model": "auto"
}
```

Performance: ~1500 simuleringar/sekund på en standard CPU. 10k sims =
~7 sekunder.

## Vad mäts (per simulering)

In-memory beräkning över 12 sim-månader (ingen DB-skrivning):

```
end_balance =
  + annual_net_salary
  - annual_housing_cost
  - annual_variable_cost (Konsumentverket × spend_profile)
  - annual_sick_loss (sampled från health_engine)
  - annual_event_cost (sampled från event_engine, max 3/mån)
  + annual_event_income (bonusar etc)
```

Initial pentagon-totalt sparas också för korrelations-analys mellan
"karaktär hade tufft start" vs "slutbalans".
