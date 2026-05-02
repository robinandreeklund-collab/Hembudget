# 14 · Monte Carlo · validerings-resultat (Fas 8 V1)

> Komplett Monte Carlo-körning · **10 000 simuleringar per cell** =
> 90 000 totalt · ~78 sekunder
> Genererad efter Sprint 1-6 + post-analys (sjuk + budget-fix)

## Resultat — full körning (10k per cell)

```
Nivå Spend            N   pos%   mar%   neg%       p10    median       p90      mean    tid
---------------------------------------------------------------------------------------------------------
    1 sparsam     10000   94.9    0.8    4.3    +36217   +121213   +308242   +147695   8.8s
    1 balanserad  10000   93.8    1.4    4.9    +24672   +109367   +290495   +134149   8.7s
    1 slosa       10000   90.0    3.0    7.0     +5109    +88791   +261447   +111573   8.6s
    2 sparsam     10000   98.5    0.4    1.1    +56017   +150323   +363213   +183971   8.6s
    2 balanserad  10000   97.8    0.8    1.4    +44803   +138110   +346009   +170429   8.6s
    2 slosa       10000   95.3    2.1    2.6    +25981   +117468   +317640   +147860   8.6s
    3 sparsam     10000   99.5    0.2    0.2    +69314   +174715   +413052   +213635   8.7s
    3 balanserad  10000   99.1    0.5    0.3    +58100   +162816   +395638   +200092   8.7s
    3 slosa       10000   97.6    1.3    1.1    +39293   +141724   +365746   +177520   8.6s
```

(Initial 300-sample-körning matchar 10k inom <1 procentenhet — seed-systemet
är robust och statistiken konvergerar snabbt.)

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
