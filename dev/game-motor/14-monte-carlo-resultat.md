# 14 · Monte Carlo · validerings-resultat (Fas 8 + Fas 8b)

> **Status:** Kalibrerad mot designmål · 9/9 cells inom mål
> **Validering:** 90 000 simuleringar (10k × 9 cells), ~80 sekunder
> **Iteration:** 12 MC-rundor av kalibrering

## Slutresultat — perfekt kalibrering

```
Niv Spend          pos%   neg%       mål      diff      p10    median       p90
----------------------------------------------------------------------------------------------
  1 sparsam        92.1    6.1    90-95%        ✓    +16503   +108614   +293040
  1 balanserad     88.9    8.2    80-90%        ✓      -107    +91685   +269642
  1 slosa          79.5   14.8    75-85%        ✓    -27639    +63084   +232236
  2 sparsam        80.7   14.7    80-90%        ✓    -30727    +87069   +302219
  2 balanserad     68.7   25.9    60-70%        ✓    -63286    +51822   +255388
  2 slosa          45.6   48.9    45-55%        ✓   -119223     -7218   +176769
  3 sparsam        61.4   33.7    55-65%        ✓   -104355    +42037   +278202
  3 balanserad     49.1   46.0    40-50%        ✓   -140308     +1963   +222417
  3 slosa          29.4   66.8    25-35%        ✓   -203816    -66011   +134041
```

**Pedagogisk distribution per nivå (pos / neg):**
- Nivå 1: 79-92% positiva, 6-15% negativa → "lärande-zon"
- Nivå 2: 46-81% positiva, 15-49% negativa → "realistisk vuxenpress"
- Nivå 3: 29-61% positiva, 34-67% negativa → "ekonomisk verklighet biter"

## Klassificering

- `positive` = end-of-year-balans ≥ +5 000 kr
- `marginal` = -10 000 ≤ balans < +5 000 kr
- `negative` = balans < -10 000 kr

## Kalibrerings-mekanik

Sju multiplikatorer per nivå styr svårighetsgraden utan att bryta realism:

| Multiplikator | Nivå 1 | Nivå 2 | Nivå 3 |
|---|---|---|---|
| `event_frequency_mult` | 1.25 | 1.85 | 2.4 |
| `event_cost_mult` | 1.18 | 1.55 | 1.85 |
| `max_events_per_month` | 2 | 4 | 5 |
| `sick_probability_mult` | 0.9 | 1.4 | 1.85 |
| `long_sick_probability_mult` | 0.6 | 2.2 | 3.2 |
| `vab_probability_mult` | 0.9 | 1.1 | 1.3 |
| `variable_spend_extra_mult` | 1.07 | 1.13 | 1.18 |
| `spend_profile_amplifier` | 1.3 | 2.5 | 2.7 |
| `initial_savings_buffer_mult` | 1.2 | 1.0 | 0.7 |

### Vad varje multiplikator gör

- **event_frequency_mult**: Skalar `frequency_per_year` på alla event-templates.
  Nivå 3 = 2.4x oftare vattenskador, varsel, kvarskatt.
- **event_cost_mult**: Skalar UTGIFTS-events 1.85x på nivå 3 (vattenskada
  kan gå från 15-45k till 28-83k). Inkomst-events oförändrade.
- **max_events_per_month**: Cap efter slumpning. Nivå 3 = upp till 5/månad
  i värsta fall.
- **sick_probability_mult**: Skalar baseline-sannolikheten för sjuk per månad.
- **long_sick_probability_mult**: Inom en sjukperiod, sannolikheten att den
  blir lång (>14 dagar = utbrändhet/rygg). Nivå 3 = 3.2x oftare.
- **variable_spend_extra_mult**: Allmänt påslag på Konsumentverket-baseline
  pga oförutsedda småköp eleven inte planerar för.
- **spend_profile_amplifier**: Förstärker spreaden mellan sparsam (0.85),
  balanserad (1.00) och slosa (1.25). Nivå 3 amp 2.7 → sparsam=0.595,
  slosa=1.675. Sparsam-elever skyddas, slosa-elever straffas mer.

## Kalibrerings-resa (12 iterationer)

| Iter | Träff | Anteckningar |
|---|---|---|
| 0 (pre-Fas 8b) | 1/9 | Alla nivå-3 slogs >97% positiv (mål 25-35%) |
| 1 | 2/9 | Initial profilering, nivå 3 nästan rätt direkt |
| 2 | 1/9 | Nivå 2 balanserad ✓, sparsam för hård |
| 3 | 3/9 | Sparsam-cells började träffa |
| 4 | 3/9 | spend_profile_amplifier introducerad |
| 5 | 5/9 | Slosa började bli rimlig |
| 6 | 3/9 | Konflikt mellan sparsam vs balanserad/slosa |
| 7 | 6/9 | Bra utveckling, små justeringar kvar |
| 8 | 4/9 | Sparsam åter för hård efter event-höjning |
| 9 | 7/9 | Större amp-höjning, nästan i mål |
| 10 | 7/9 | Liknande, justering åt andra hållet |
| 11 | 4/9 | För mycket — sänkte events för hårt |
| **12** | **9/9** ✅ | **Slutkalibrering — alla cells inom mål** |

## CLI-användning

```bash
# Enskild körning
python -m hembudget.game_engine.monte_carlo --n 1000 --level 1 --spend sparsam

# Grid över alla 3×3
python -m hembudget.game_engine.monte_carlo --n 5000 --grid

# JSON för pipeline-integration
python -m hembudget.game_engine.monte_carlo --grid --json
```

## Endpoint

```
POST /v2/teacher/monte-carlo
{
  "n_simulations": 1000,
  "starting_level": 2,
  "spend_profile": "balanserad",
  "partner_model": "auto"
}
```

Lärar-token krävs. Max 10k sims per anrop.

## Performance

- ~1 100 sims/sekund (något långsammare än innan pga difficulty-arithmetik)
- 90 000 sims = ~80 sekunder
- 10k sims per cell ger ±1.5 procentenheter konvergens

## Pedagogisk slutsats

Spelmotorn ger nu **realistisk pedagogisk progression**:

- **Nivå 1** belönar försiktighet (sparsam = 92%) men accepterar
  experiment (slosa = 80%, ingen katastrof).
- **Nivå 2** kräver eftertanke — slosa hamnar nästan 50/50, balanserad
  träffar realistisk svensk medel-elev.
- **Nivå 3** speglar tuff vuxen-vardag — slösare hamnar i skuld med
  67% sannolikhet, även sparsamma elever har 34% risk att gå minus.

Detta matchar designmålen i 09-difficulty-levels.md exakt.

## Källor (svenska 2026-data)

- SCB Strukturlönestatistik 2024 (uppjusterad 3 % för 2026)
- Konsumentverket hushållskostnader 2026
- Försäkringskassan VAB-statistik 2023
- Arbetsgivarverket "Staten i siffror — sjukfrånvaro" 2023
- Hyresgästföreningen Bostadsbarometern 2024
- Svensk Mäklarstatistik / Booli BRF-snitt 2024
