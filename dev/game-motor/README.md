# Spelmotorn · Den simulerade verkligheten

> **Den simulerade spelmotorn** är hjärtat i Ekonomilabbet — den knyter
> ihop alla aktörer, verktyg och val till en levande, automatisk
> simulering av en svensk vuxen-vardag.

Denna mapp innehåller den kompletta arkitekturen och implementations-
specen för spelmotorn. Den är skriven som ett levande designdokument:
varje kapitel motsvarar en motor-del eller en designprincip.

## Tre motorer som samverkar

| Motor | Ansvar | Frekvens | Tekniskt mönster |
|---|---|---|---|
| **Profile Generator** | Skapar hel karaktär vid ny elev | 1 gång (vid skapelse) | Seed-baserad deterministisk |
| **Monthly Engine** | Lön, fakturor, drift, värdering | Varje spelmånad (= 1 realvecka) | Kalender-driven cron |
| **Event & Decision Engine** | Oväntade händelser, beslut, Echo, försäkringar | Realtid + dagligen | Trigger-baserad |

Allt rullar **automatiskt efter att läraren skapat eleven** — läraren
ska aldrig behöva generera data manuellt.

## Läs i ordning

1. [`01-vision-och-arkitektur.md`](./01-vision-och-arkitektur.md) — Vision, principer, tre-motors-arkitektur
2. [`02-profile-generator.md`](./02-profile-generator.md) — Karaktärs-skapelse (yrke, stad, boende, familj)
3. [`03-monthly-engine.md`](./03-monthly-engine.md) — Månadsmotorn (lön, fakturor, drift)
4. [`04-event-engine.md`](./04-event-engine.md) — Oväntade händelser + försäkringskoppling
5. [`05-arbetsformedlingen.md`](./05-arbetsformedlingen.md) — Jobbpool + 5-rond intervju med AI Mats
6. [`06-boendemarknaden.md`](./06-boendemarknaden.md) — Köp/sälj/flytt + bolån
7. [`07-pentagon-mekanik.md`](./07-pentagon-mekanik.md) — Wellbeing-formel, tröghet, drift, mål
8. [`08-tidsmodell.md`](./08-tidsmodell.md) — 1 spelmånad = 1 realvecka, snabbspola, säsong
9. [`09-difficulty-levels.md`](./09-difficulty-levels.md) — Nivå 1–3 utan att röra ekonomin
10. [`10-saknas-foreslag.md`](./10-saknas-foreslag.md) — Vad som saknas i ursprungsförslaget
11. [`11-implementations-plan.md`](./11-implementations-plan.md) — Faser, prioritet, integration med v2
12. [`12-data-modeller.md`](./12-data-modeller.md) — Befintliga + nya tabeller (master + scope)

## Status (2026-05-01)

**Existerar redan:**
- StudentProfile (master-DB) · Profile Generator-fundamentet
- WellbeingCalculator · 5-axel-pentagon med faktorer
- ScenarioBatch + ScenarioArtifact · månadsdriven artefakt-generering
- 9 aktörer + Postlådan + 6 verktyg
- 14 systemkompetenser
- Lärar-modulbibliotek + assignments
- BankIDSession · friktionsbaserad signering
- Maria-AI lönesamtal (5 rundor)
- Echo-AI (sokratisk coach)

**Designat men ej implementerat (denna spec):**
- Centraliserad Monthly Engine som tickar varje vecka
- Yrkespool (~150 svenska yrken med SCB-data)
- Stadspool med kostnadsmultiplikatorer
- Arbetsförmedlingen-aktör (10:e aktören) + AI Mats 5-rond
- Boendemarknad (köp/sälj/flytt + bolåneflöden)
- Initial pentagon-variation per karaktär
- Snabbspola + säsongsevent + What-if-läge
- Difficulty-levels med konsekvent ekonomi
- Klass-genomsnitt-tävling
- Echo-minne över 3–4 spelmånader

## Princip: realism × spelbarhet × pedagogik

Alla beslut i spelmotorn vägs mot tre kriterier:

1. **Realism** — siffror från SCB, Konsumentverket, Hyresgästföreningen,
   Skatteverket. Bolåneräntor uppdaterade. Ingen pedagogisk fiktion.
2. **Spelbarhet** — komprimerad tid, klar feedback-loop, eleven kan
   påverka tempo. Ingen monoton drift utan friktion eller belöning.
3. **Pedagogik** — varje val ska ge spårbar effekt på pentagonen,
   varje siffra ska kunna förklaras. Echo coachar utan att lösa.

När principerna kommer i konflikt vinner pedagogiken — det är därför
vi finns.

## Dokumentations-konventioner

- **Datatabeller** anges som `master::TableName` eller `scope::TableName`
  beroende på vilken DB de bor i.
- **Endpoints** anges relativt v2-routern: `/v2/...`.
- **Konstanter** (lönespann, hyror, multiplikatorer) anges som svenska
  2026-värden där det finns data; placeholder annars.
- **Faser** anges som `Fas N · namn`. Fas-numrering är icke-kronologisk
  utan strukturerad efter beroenden.
