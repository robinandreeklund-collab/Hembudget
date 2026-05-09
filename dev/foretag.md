# Företagsläget · djupanalys

> Skriven 2026-05-09 efter genomläsning av hela `/v2/foretag*`-,
> `/v2/allabolag`- och `/v2/arbetsformedlingen`-domänen
> (~ 18 000 rader backend + tillhörande frontend).
>
> Syftet är dels att dokumentera mekaniken så nästa Claude-pass slipper
> återupptäcka samma saker, dels att lista konkreta buggar och
> svagheter med fil:rad-referenser så de kan plockas upp som tickets.

---

## 1 · Översikt

**Företagsläget** är delen av Ekonomilabbet där eleven driver ett
fiktivt svenskt bolag (AB · enskild firma · handelsbolag-stub) i
samma simulerade kalender som privat-läget (1 real-timme = 1 spel-vecka,
anchor 2026-01-01). Branschen väljs ur 10 fasta `Industry`-objekt
(`backend/hembudget/business/industries.py`) och staden ärvs från
karaktärens `StudentProfile.city` — branscher som `frisor`, `catering`
eller `personal_trainer` kräver minst medel-stad
(`industry_available_in_city`).

Pedagogisk grundpremiss:

* Eleven ska se en *levande* spelvärld utan att vara tvungen att
  klicka "Stega vecka". `auto_tick_if_due()` (tick_engine.py:912)
  räknar fram så många biz-veckor som passerat sedan senaste
  endpoint-läsning.
* Eleven ska *jämföras* mot klassen via Allabolag (scoreboard) och
  klass-företag-jobbannonser (Arbetsförmedlingen → "Klass-jobb").
* Privat-pentagon ska påverkas av biz-utfall — men *asymmetriskt*
  (negativa biz-händelser slår hårdare än positiva, se
  `business/cross_pentagon.py`).

Två svårighetsnivåer ligger på `Company.level`:

| Nivå | Bas-pipeline/v | Volatilitet | Random events | Acceptance-shift |
|---|---|---|---|---|
| `basics` | 2 | ±5 % | 0 % | +0.5 logits (mildare) |
| `advanced` | 3 | ±15 % | 40 %/v | -0.3 logits (svårare) |

Källa: `business/engine/difficulty.py:50-71`.

Företagsdomänen är aktiverad bara om läraren har togglat
`Student.business_mode_enabled = True`. Modellen lever per scope
(elev/familj) — `Company`, `CompanyTransaction`, `JobOpportunity` etc.
— medan klass-aggregatet `ClassCompanyShare` ligger i master-DB.

---

## 2 · Spelmotorn · tick-flödet

`run_business_week()` (tick_engine.py:793-893) är huvudloopen och
kör **9 faser** per vecka i denna ordning:

1. `_update_capacity_from_growth` — Synca `delivery_capacity`
   = `lokal.max_concurrent_jobs * eq.speed_multiplier + active_mcp`.
   Görs FÖRE pipeline_generator så bolaget får rätt cap.
2. **Fas A · `_phase_a_decide_quotes`** — Kunderna besluter om alla
   öppna offerter via `acceptance_model.evaluate_quote()`. Vid YES
   skapas en `Job`-rad direkt med `estimated_hours`/`hours_per_week`
   skattat från `industries.time_per_job_hours_min/max`.
3. **Fas B · `_phase_b_collect_payments`** — Kunder betalar förfallna
   `CompanyInvoice` enligt `JobOpportunity.payment_morality`
   (default 0.92). När betald → status=`paid`, `paid_on=today`,
   och en `CompanyTransaction(kind="income")` bokförs (denna
   bokföring saknades ursprungligen, kommentar i koden bekräftar
   det var en bug · tick_engine.py:281-291).
4. **Fas C · `_phase_c_generate_opportunities`** — Spärr om
   `has_base_equipment=False`. Annars: `pipeline_generator`
   räknar antal nya förfrågningar (rep + marketing + quality −
   complaints, kapacitets-faktor). För varje genererad opp:
   väljer kund med segment-mix (privat/företag/kommun från
   industri), pris-baseline = `industry.hourly_rate_mid * delivery_days * 6`,
   stad-multiplier (`STAD_BY_KEY[city_key].cost_multiplier_housing`),
   volatilitet ±5/15 %. AI berikar beskrivningen för 1 av 3
   (token-sparare) via `business.ai.generate_job_description`.
   `requires_car` flaggas för bransch+privat-kund (deterministisk
   rng).
5. **Fas D · `_phase_d_reputation_drift`** — Långsam drift av
   `reputation` 5 % mot `avg_quality` om diff > 1.
6. **Fas E · `_phase_e_random_events`** — Bara advanced. Slumpar
   0..2 events från `EVENT_TEMPLATES` (datorn_gick_sonder,
   kund_klagade, miljoskatt, leverantor_hojde_pris,
   vattenskada_lokalen, stold_av_verktyg). Försäkring täcker 90 %
   för `egendom`-kinds. Skapar `SupplierInvoice` + ev. höjer
   `open_complaints`/sänker `reputation`.
7. **Fas F · `_phase_f_charge_subscriptions`** — Veckovis 1/4 av
   månadskostnad för (a) aktiva `BusinessDecision.monthly_cost > 0`,
   (b) lokal-hyra `CompanyLocation`, (c) lån-ränta + amortering
   `CompanyLoan`, (d) avskrivningar `CompanyAsset`. Allt bokförs
   som `CompanyTransaction(kind="expense")` med kategori-prefix.
8. **Fas G · `_phase_g_employment_decision_check`** — Räknar biz-h/v
   via `cross_pentagon.compute_weekly_business_hours`, jämför mot
   `StudentProfile.weekly_hours_employed`. Om total > 50 ökar
   `consecutive_overload_weeks`, om eleven pressat 4+ veckor och
   ≥ 25 h/v biz → Maria-prompten (mail).
9. **Fas momsregistrering · `_phase_vat_threshold_check`** — Räknar
   12 mån rullande omsättning. ≥ 60k → varnings-mail. ≥ 80k →
   auto-flippar `vat_registered=True` + skickar mail. Idempotent
   via subject-match.
10. **Fas H · `_phase_h_milestone_mails`** — Skickar reflektionsmail
    v4/v8/v12/v24, signerade av elevens lärare.
11. **Fas I · `_phase_i_overload_consequences`** — Räknar tier
    (T0..T4) via `compute_time_capacity` + classify_tier. Tier
    >= 1 ger pentagon-deltas på health/safety. Tier 4 → kraschen,
    capacity = 0 i 1 vecka, sjukskrivning-mail. Tier-baserad
    delay_risk slumpar förseningar på aktiva jobb (3 förseningar →
    kund avbryter).

Alla seedade slumpval använder `_tick_seed(company.id, week_no, suffix)`
för determinism — läraren kan teoretiskt re-spela en vecka.

Auditering: `BusinessTickJob` skapas vid start (status=`running`),
markeras `done` eller `failed` vid slut. Vid exception: en
**separat** session öppnas (tick_engine.py:876-890) för att skriva
failure-raden, eftersom huvudsessionen rollback:as.

`auto_tick_if_due()` är idempotent — `last_auto_tick_at` flyttas
fram med `n_done * AUTO_TICK_INTERVAL_HOURS` (1.0 h), och om en
tick fail:ar lämnas tidsstämpeln orörd så nästa request försöker
igen. Tak: `AUTO_TICK_MAX_CATCHUP_WEEKS = 6` veckor per request.

---

## 3 · Datamodell

### Scope-DB (per elev)

| Modell | Roll |
|---|---|
| `Company` | Bolags-rooten · 1 aktiv per scope. Innehåller status, week_no, reputation, avg_quality, has_base_equipment, has_car, last_auto_tick_at, recent_quiz_question_ids (JSON). |
| `CompanyTransaction` | Alla pengar in/ut. `kind` ∈ {income, expense, salary, vat_payment, tax_payment, asset_purchase}. Kanonisk källa till kassan. |
| `CompanyCustomer` | Kund-stamfil (skapas vid `deliver_job`). |
| `CompanyInvoice` | Fakturor till kunder. `invoice_number` String(40) — **ej unique-constraint** (se buggar). |
| `CompanyVatPeriod` | Momsperiod-rapporter (kvartal/år). |
| `CompanyOwnerSalary` | Lön till AB-ägare (lön + AGI 31.42 % + prel-skatt 30 % förenklat). |
| `JobOpportunity` | Offertförfrågningar från simulerade kunder. |
| `Quote` | Elevens offert · `unique=True` på `opportunity_id`. |
| `Job` | Vunnet uppdrag · `unique=True` på `opportunity_id`. Har `estimated_hours`/`hours_per_week`/`delays_count`. |
| `MarketingCampaign` | Aktiva kampanjer. `base_pipeline_boost` läses i tick_engine fas C. |
| `BusinessDecision` | Anställning/försäkring/leasing/friskvård. `monthly_cost`/`one_time_cost`/`capacity_delta`/`reputation_delta`. |
| `SupplierInvoice` | Leverantörsfaktura · genererade av events, lärar-mass-skick eller manuella. |
| `BusinessTickJob` | Audit-rad per körd tick (status, n_*, error). |
| `CompanyAnnualReport` | Årsbokslut + AI-Bolagsverket-granskning. |
| `CompanyLoan` | Bolagets lån. `outstanding`/`monthly_payment`/`is_personal_guarantee`. |
| `CompanyLocation` | Aktiv lokal · `max_employees`, `max_concurrent_jobs`. |
| `CompanyEquipment` | `speed_multiplier` på 1.00..1.50. |
| `CompanyAsset` | Aktiverat anläggningstillgång (>5 000 kr) · 60-mån avskrivning för equipment, 120 för vehicle. |
| `CompanyMcpRental` | Inhyrd frilansare en vecka. |

### Master-DB (per lärare)

| Modell | Roll |
|---|---|
| `ClassCompanyShare` | Cache-rad per (student, company). Aggregat: revenue_4w, profit_4w, kassa, n_employees, reputation, uc_score/uc_rating, company_level, annual_report_status. |
| `CompanyJobAd` | Klass-jobbannons. |
| `CompanyJobApplication` | Ansökan från klasskompis. |
| `CompanyEmployment` | Realt anställd elev → ägar-bolag. |
| `CompanyMentorship` | Mentor-kid-relation. |
| `ClassSeasonEvent` | Lärar-aktiverade events (Black Friday etc.). |
| `StudentEntrepreneurScore` | Total points + JSON badges. |

---

## 4 · Ekonomi-modellen

### Kassan

`backend/hembudget/business/cash.py:compute_company_cash` är **enda
sanningen**. Definition:

```
kassa = Σ(income.amount_excl_vat) − Σ((expense|salary|vat_payment|
                                        tax_payment|asset_purchase).amount_excl_vat)
```

`share_capital` på `Company` är **legal status** — den faktiska
insättningen speglas alltid som en `CompanyTransaction(kind="income",
category="Aktiekapital · insättning")` (vid cash-funded AB) eller
som en `kind="income", category="Lån · startkapital"` (vid
business_loan_pg). Filen `cash.py` har en utmärkt kommentar om
detta (`cash.py:18-25`) — tidigare hade systemet 4-5 olika
kassa-formler som gav olika svar mellan vyer.

### Omsättning · vinst · marginal

Per `compute_business_pentagon` (service.py:353):

* `income_4w` = `Σ(amount_excl_vat WHERE kind="income" AND occurred_on ≥ today−28d)`
* `expense_4w` = `Σ(amount_excl_vat WHERE kind IN ("expense", "salary"))`
* `profit_4w` = income − expense
* `margin_4w_pct` = profit/income · 100 (bara om income > 0)

OBS: `vat_payment`, `tax_payment` och `asset_purchase` räknas inte
som expense här (de är skuldreglering eller balansräkningspost,
INTE periodens kostnad). Det är pedagogiskt korrekt eftersom
avskrivningar bokförs separat med kategori "Avskrivning Inventarier".

### Moms

`compute_period_vat` (service.py:259) räknar `output_vat` =
Σ(vat_amount WHERE income), `input_vat` = Σ(vat_amount WHERE expense),
`net_vat` = output − input. `file_vat_period` skapar `CompanyVatPeriod`
+ `CompanyTransaction(kind="vat_payment")` om netto > 0.

Tröskel: 80k 12-mån rullande omsättning → auto-momsregistrering
(`_phase_vat_threshold_check`).

### Lön + AGI (AB)

`compute_owner_salary` (service.py:33):
* AGI 31.42 % default · 19.49 % för 18-24-åringar
* Prel-skatt 30 % på brutto
* `total_cost_to_company` = brutto + AGI
* `net_to_owner` = brutto − prel-skatt

`book_owner_salary` skapar bolags-tx `kind="salary"` (kostnad =
total_cost) och en privat-tx på elevens checking-konto (= netto).

Eget uttag (enskild firma): `book_owner_withdrawal` bokför
`kind="expense", category="Eget uttag"` på bolaget och
positiv tx på privatkontot. Ingen AGI, ingen prel-skatt — eleven
deklarerar privatskatten på årets vinst.

### Bolagsskatt

20.6 % (2026) · `estimate_corporate_tax_for_year` (service.py:543).

---

## 5 · Pipeline-generering & matchning

### `pipeline_generator.calculate_n_opportunities`

```
n = base_per_week (2 basics / 3 advanced)
  + rep_bonus (+2 om rep≥80, +1 om ≥60, -1 om ≤30)
  + marketing_bonus (clamp(2, round(boost * 0.7)))
  + quality_bonus (+1 om avg_q≥80, -1 om ≤40)
  - complaint_penalty (clamp(2, open_complaints))
  · capacity_factor (free_slots: 0→0.4 · 1→0.7 · 2+→1.0)
  ± slump (-1/0/0/+1 deterministisk)
```

Källa: `pipeline_generator.py:42-110`.

### `acceptance_model.evaluate_quote`

Logistic regression med 5 termer, sigmoid:

* `W_PRICE = 4.5` · `price_diff_ratio * (0.5 + customer_price_sensitivity)`
* `W_REPUTATION = 0.025` · `(reputation - 50)`
* `W_MARKETING = 0.5` · `marketing_boost (0..1)`
* `W_PITCH = 1.5` · `(pitch_q - 0.5) * (0.5 + customer_quality_sensitivity)`
* `W_DELAY = 1.2` · `-max(0, delay_ratio)` (bara straff)

Kalibrerat så offert exakt på riktpris ger ~50 %, 30 % billigare
~85 %, 30 % dyrare ~15 %. Outputtar `probability`, `accepted`,
`explanation` (pedagogisk klartext).

### Pris-baseline

Två lager:
1. `industries.hourly_rate_min/max` mid-värde × `delivery_days * 6`
   (timmar antagna per dag)
2. Stad-multiplier (`STAD_BY_KEY[city].cost_multiplier_housing` —
   används som pris-proxy, se buggsektion).
3. `pricing.SEGMENT_PRICE_FACTOR` används bara som *fallback* när
   industri-data saknas (privat 1.0, företag 1.2, kommun 1.4).
4. Volatilitet ±5 % (basics) eller ±15 % (advanced).
5. Avrundning till hela hundratal.

### Segment-mix

`industries.segment_mix_privat/foretag/kommun` summerar till 1.0
och driver `_pick_customer_with_segment_mix` (tick_engine.py:74).
T.ex. snickare 65/30/5 (ROT-tunga), IT-konsult 15/65/20,
catering 30/55/15 (B2B-luncher).

---

## 6 · Leverans + kvalitet

### Flöde

```
JobOpportunity (open)
   ↓ submit_quote (POST /opportunities/{id}/quote)
JobOpportunity (quoted) + Quote (accepted=None)
   ↓ tick_engine fas A · evaluate_quote
JobOpportunity (won/lost) + Quote (accepted=True/False)
   ↓ Job (in_progress, agreed_price, est_hours)
   ↓ submit_delivery_quiz (3-fråge-quiz)
Job (delivered) → deliver_job()
   ↓ create CompanyInvoice (status=sent)
Job (invoiced)
   ↓ tick_engine fas B (kund betalar enligt morality)
Job (paid) + Invoice (paid)
```

### Quiz

`backend/hembudget/business/delivery_quiz.py` ersatte slidern
(eleven valde själv 0-100 → triv-fusk). 3 frågor per leverans,
3 alternativ vardera. Mappning:

* `option_good` → 100p
* `option_mid` → 60p
* `option_bad` → 20p

`score_answers(answers)` (delivery_quiz.py:1654) returnerar
`mean ± random(7)` clampat till 0-100. Quiz-ID:n sparas i
`Company.recent_quiz_question_ids` (JSON, max 10) för
anti-repetition.

Anti-fusk: GET-endpointen seedar shuffle på `(question_id * 1000 + job_id)`
så a/b/c-ordningen är stabil mellan reload men "good" inte alltid är "a".

### Reputation

* `update_reputation_from_delivery(current, quality, weight=0.15)`
  → asymptotisk drift mot quality, ~5-6 leveranser för full effekt.
* `update_reputation_from_complaint(current, severity)` → -5/-10/-15
  direkt.
* `update_reputation_from_marketing(current, ai_factor)` → ±3
  (ai_factor 0.5..1.5 → -3..+3).
* `update_avg_quality(current, new, weight=0.3)` → exponentiell
  utjämning.

---

## 7 · Tillväxt & beslut

### Lokal (`CompanyLocation`)

5 nivåer i `LOCATION_CATALOG` (foretag_growth.py:55):

| kind | hyra/mån | max_emp | max_jobs |
|---|---|---|---|
| home | 0 | 0 | 1 |
| rented_1r | 4 000 | 1 | 4 |
| rented_2r | 9 000 | 3 | 8 |
| office_50 | 18 000 | 5 | 14 |
| office_120 | 38 000 | 10 | 28 |

`office_50` och `office_120` kan köpas (480k / 1.2M) i stället för
hyras.

### Utrustning (`CompanyEquipment`)

| kind | pris | speed | breakdown |
|---|---|---|---|
| standard | 0 | 1.00 | 0.000 |
| second_hand | 12 000 | 1.10 | 0.050 |
| premium | 45 000 | 1.30 | 0.000 |
| specialist | 120 000 | 1.50 | 0.000 |

`breakdown_risk` används inte i koden idag — bara satt på modellen.

### Lån (`CompanyLoan`)

`LOAN_TERMS` (foretag_growth.py:128):

| purpose | min/max | utan PG | med PG | mån |
|---|---|---|---|---|
| startup_capital | 25k-50k | 12 % | 7 % | 60 |
| growth | 10k-500k | 9.5 % | 6 % | 60 |
| buffer | 5k-100k | 14 % | 9 % | 24 |

UC-rating på `ClassCompanyShare` justerar räntan ±5 p.e. UC=D
utan personlig borgen → automatisk avslag (foretag_growth.py:764).

### Anställning

**Två separata system samtidigt — viktig pedagogisk + teknisk
distinktion:**

1. **Fiktiva anställda** via `BusinessDecision(kind="hire_full_time")`
   med `capacity_delta=+1`. Inkrementerar `Company.delivery_capacity`
   direkt. Bokför `monthly_cost` i fas F. Ingen riktig elev.
2. **Riktiga klass-anställda** via `CompanyJobAd` →
   `CompanyJobApplication` → `CompanyEmployment` (master-DB).
   Inkrementerar inte `Company.delivery_capacity`, men räknas
   in i `compute_time_capacity` (foretag_capacity.py:160-202)
   med 40 h/v.

`compute_time_capacity` slår ihop båda källorna (kommentar:
"Tidigare bug · capacity läste BARA källa #1").

### Marknadsföring

10-tier paketkatalog `MARKETING_PACKAGES` (foretag_engine.py:941):
lokaltidning (3.5k, +5 % pipeline) → TV-reklam (750k, +80 %).
`reputation_bump` 1-12 direkt vid köp. Aktiva kampanjer summas
i tick fas C (`_sum_active_marketing_boost`, max 3.0).

### MCP-frilans

`POST /v2/foretag/growth/mcp/rent` med 1-4 v. Kostar 48 000 kr/v.
Ger +1 capacity och +40 h/v i tids-modellen. Sätter `CompanyMcpRental`
med `ends_on`-datum.

### Bas-utrustning + bil

`StartupKitInfoOut` läser `industry.equipment_cost_init` och
`car_cost`. Köp aktiverar `CompanyAsset` (60 mån för equipment,
120 för fordon) + flagga `Company.has_base_equipment`/`has_car`.
Innan bas-utrustning är köpt: pipeline_generator returnerar 0
opportunities (tick_engine.py:302).

### Tids-kapacitet

5-tier-modell i `foretag_capacity.py`:

| Tier | Ratio | Hälsa/v | Trygghet/v | Delay-risk |
|---|---|---|---|---|
| T0 | ≤ 100 % | 0 | 0 | 0 % |
| T1 | 101-130 % | -3 | 0 | 5 % |
| T2 | 131-180 % | -8 | -2 | 25 % |
| T3 | > 180 % | -15 | -5 | 50 % |
| T4 | T3 i 4 v | -20 | -8 | 100 % (krasch) |

Tillgängliga timmar = 84 (ägaren · inkl kvällar/helger) − privat-jobb-h
+ 40 × n_employees + 40 × n_active_mcp.

---

## 8 · Allabolag

### `sync_class_company_share`

Cachen i master-DB uppdateras vid:

* Varje `auto_tick_if_due` (tick_engine.py:967)
* `create_company` (efter init-tick · foretag.py:702)
* `list_class_companies` self-heal (allabolag.py:336) om eleven
  saknar share-rad

Räknar:
* `revenue_4w`, `profit_4w`, `margin_pct` på 30-dagars-fönster
  i **spel-tid** (`current_game_date_for_student`).
* `kassa` = `compute_company_cash` (kanonisk).
* `n_invoices_open` (status=sent), `n_invoices_overdue`
  (status=sent AND due_on < today_g).
* `uc_score` + `uc_rating` (likviditet 30 % · marginal 25 % ·
  fakturor 20 % · rykte 15 % · ålder 10 %).
* `company_level`: startup → vaxande (≥50k oms + 1 anställd) →
  etablerat (≥200k + 3 anställda + 50k kassa) → marknadsledare
  (≥500k + 5 anställda + rep≥85).

### Detail-vy

`/v2/allabolag/{company_id}/detail` öppnar ägarens scope-DB via
`scope_context()` och bygger en allabolag.se-stil-profil med
syntetisk address (`_synth_address`) baserad på `company.id` +
`city_key`. Visar 5-perioders staplar (4-veckors-bucket),
nyckeltal kassalikviditet/vinstmarginal/soliditet med direction-
pilar (jämfört mot föregående period).

### Privacy

`ClassCompanyShare.is_published` (default True). Eleven kan
toggla via `POST /v2/allabolag/publish`. Lärare ser alltid alla.
Andra elever ser bara publicerade + sitt eget.

---

## 9 · Klass-interaktioner

### Klass-jobbannonser (`company_jobs.py`)

* Ägaren skapar `CompanyJobAd` (POST `/v2/foretag/job-ads`).
  Spärrar mot `loc.max_employees − active_employments − open_ads ≥ 0`.
* Andra elever söker via `POST /v2/arbetsformedlingen/klass-jobb/{id}/apply`
  med cover_letter (≥ 20 chars).
* Ägaren beslutar via `POST /{ad_id}/applications/{app_id}/decide`
  → vid accept: `CompanyEmployment` + alla andra ansökningar
  rejected.
* Säga upp: `POST /employments/{empl_id}/terminate` med LAS-baserad
  uppsägningstid (1-6 mån beroende på anställningstid).

### Mentor

`POST /v2/foretag/mentor/apply` — bara om eleven är på nivå
`etablerat` eller `marknadsledare`. Mentee måste ha `profit_4w < 0`
ELLER `uc_score < 40`. Ger mentee +5 rykte (cache direkt).

### Säsong-events

Lärare aktiverar via `POST /v2/teacher/season-events`:
* `black_friday` — 7 dgr · shared-opp × 3
* `recruitment_crisis` — 14 dgr · MCP × 1.5
* `sustainability` — 30 dgr · specialist-utrustning +10 % rykte
* `bankruptcy_chain` — 7 dgr · ofakturerade < 30 d får 50 %

OBS: Eventens påverkan på tick_engine är **inte implementerad** —
helper `is_event_active()` finns men inget `_phase_*` läser den.
Säsong-events är just nu bara visuell statussignal.

### Leaderboards

12 kategorier i `CATEGORIES` (leaderboard.py:29). Sorterar
`ClassCompanyShare`-rader på olika metrics. Flera kategorier
(`won_quotes_4w`, `comeback_score`, `mentor_helps`, `pivot_success`)
har **placeholder = 0.0** (leaderboard.py:143-157) — de är inte
implementerade men visas som tom topplista.

---

## 10 · Privat ↔ biz-koppling

### Cross-pentagon

`biz_to_private_factors(biz_axes)` (cross_pentagon.py:38)
mappar de 5 biz-axlarna till privat-pentagon:

| Biz-axel | < tröskel | > tröskel | Privat-axel |
|---|---|---|---|
| likviditet | -8 (<20) / -5 (<30) | +3 (≥80, asymmetri) | economy |
| vinst | -5 / -2 | +1 | health |
| tidsatgang | +30 → -3, +85 → -7 leisure −5 social | — | leisure/social |
| kundbas | -3 (<25) | +3 (≥80) | safety |
| omsattning | — | +2 (≥85+vinst≥60) | economy |

Asymmetri: stora positiva = små privat-bonus (man kan inte ta
ut allt direkt). Stora negativa = stora privat-penalties
(stress drabbar verkliga personen).

### `compute_weekly_business_hours`

(cross_pentagon.py:265) summerar förväntade timmar/v från
`in_progress_jobs`. Bransch-baseline `(min+max)/2` delat på
`weeks_left`. **Använder `_d.today()` (real-time)** vilket
är en bugg — se buggsektion.

### Maria-säg-upp

Triggas i tick fas G när `consecutive_overload_weeks ≥ 4` AND
`weekly_hours_business ≥ 25` AND status=`employed`. Tre val:

* `keep_fulltime` → resetar overload-counter, fortsätter pressa
* `go_parttime` → 20 h/v, halverad lön, resetar counter
* `resign` → status=freelance_only, lön 0 från månad +3

### Tids-kapacitet (private 40 h-jobb äter 84 h)

Modell: ägaren har 84 produktiva h/v (inkl kvällar/helger).
Privat-jobb äter `weekly_hours_employed` (default 40). Resterande
44 h är "self_biz_hours". Plus +40 per anställd, +40 per active
MCP.

### Ägarens lön landar på privat-konto

`book_owner_salary` skapar `Transaction` på elevens checking-konto
med netto-belopp (service.py:170). Hash baseras på
`(company_name, paid_on, kind, net_amount)` för idempotens.

---

## 11 · Brister & buggar

### KRITISK · `n_employees` skrivs alltid till 0 i Allabolag-cachen

`backend/hembudget/api/allabolag.py:219`

```python
# Anställda — Fas D · CompanyEmployment-räknare. Fas A: 0.
n_employees = 0
...
row.n_employees = n_employees
```

`sync_class_company_share` skriver alltid `0` även om eleven
har CompanyEmployment-rader. `decide_application`
(`company_jobs.py:632`) sätter `share.n_employees = (count active)`
direkt vid accept, men nästa `auto_tick_if_due` kör
`sync_class_company_share` och **överskriver tillbaka till 0**.

**Konsekvens:**
* Ingen elev kan progrediera från `startup` → `vaxande` via
  scoreboard (`_compute_level` kräver `n_employees ≥ 1`).
* `BadgeOut("first_employee", "five_employees")` aldrig
  triggade.
* Leaderboard-kategori `best_employer` (n_employees) alltid 0.
* Detail-vyn visar "0 anställda" trots att eleven har 3.

**Fix:** Räkna från `CompanyEmployment` i `sync_class_company_share`:

```python
from ..school.models import ClassCompanyShare, CompanyEmployment
n_employees = (
    ms.query(CompanyEmployment)
    .filter(CompanyEmployment.company_share_id == row.id,
            CompanyEmployment.status == "active")
    .count()
) if row.id is not None else 0
```

— men row är inte committed än vid första syncen, så räkna
istället via `owner_student_id` → finns då CompanyEmployment-
raderna pekar på `share.id` så de finns även vid omsync.

Lägg också med `Company.delivery_capacity − 1` (fiktiva
anställda från BusinessDecision-flödet) som
`compute_time_capacity` redan gör (foretag_capacity.py:196).

---

### KRITISK · `BusinessDecision` accepterar klient-supplerad capacity_delta + reputation_delta

`backend/hembudget/api/foretag_engine.py:1186-1203`

```python
class DecisionIn(BaseModel):
    kind: str = ...
    capacity_delta: int = Field(default=0)
    reputation_delta: int = Field(default=0)
    ...
```

Klienten skickar `capacity_delta` och `reputation_delta` direkt.
`create_decision` (1292) gör:

```python
if body.capacity_delta:
    co.delivery_capacity = max(1, co.delivery_capacity + body.capacity_delta)
if body.reputation_delta:
    co.reputation = max(0, min(100, co.reputation + body.reputation_delta))
```

**Konsekvens:**
Elev gör `POST /v2/foretag/decisions` med
`{"kind":"wellness", "capacity_delta": 999, "reputation_delta": 50,
 "monthly_cost": 0, "one_time_cost": 0}` och får direkt unlimited
delivery_capacity + max-rep. Spelet är trasigt.

**Fix:** Hårdkoda capacity/reputation-deltas i en server-side
`DECISION_CATALOG` (analog med MARKETING_PACKAGES). Klienten
skickar bara `kind` (eller paket-key); servern slår upp värdena.
Ingen reputation_delta utan en konkret pedagogisk källa
(t.ex. genomförd välkomstsession för anställd → +1 rep).

---

### KRITISK · `score_answers` är icke-deterministisk

`backend/hembudget/business/delivery_quiz.py:1677`

```python
def score_answers(answers: list[str]) -> int:
    ...
    base = sum(points) / 3
    jitter = random.randint(-7, 7)   # ← inte seedat
    return max(0, min(100, int(round(base + jitter))))
```

`random.randint` använder global modul-RNG. Två anrop med samma
input ger olika svar. Ingen `_tick_seed`-determinism.

**Konsekvens:**
Om quiz-endpointen anropas två gånger (frontend retry, double-
click, race condition) får eleven olika quality_score. Cron-
audit kan inte re-spela ett jobb. För eleven märks det vanligtvis
inte (svaret committas på första anropet), men det bryter
designprincipen "läraren ska kunna re-spela en vecka".

**Fix:** `submit_delivery_quiz` har redan `(job_id, company_id)`-
seed för pick_questions. Skicka samma seed in i score_answers:

```python
def score_answers(answers, *, seed: int) -> int:
    rng = random.Random(seed)
    ...
    jitter = rng.randint(-7, 7)
```

---

### VIKTIG · Real-tid läckor i biz-kod

Trots att `business/game_clock.current_game_date()` finns och
används flitigt, finns kvarvarande real-tid-användningar som
jämförs med spel-data:

1. **`business/cross_pentagon.py:294`** ·
   `compute_weekly_business_hours` använder `_d.today()` för att
   räkna `weeks_left = (job.expected_complete_on - today).days // 7`.
   När jobbet har `expected_complete_on=2026-02-15` (spel) och
   real-today är 2026-05-09 blir `weeks_left` negativt. Anropas
   från tick_engine fas G — Maria-prompten räknar fel biz-h/v.

2. **`api/arbetsformedlingen.py:265`** ·
   `cutoff = _d_diff.today() - _td_diff(days=30)` används för
   "3+ avslag de senaste 30 dagarna → -10 match-score".
   Eftersom `JobApplication.completed_on` lagras i spel-tid blir
   match-score-justeringen alltid 0 (cutoff = real-maj 2026,
   completed_on = spel-januari 2026 → ingen träff). Pedagogiska
   konsekvensen "var aktiv men inte spammig" försvinner.

3. **`api/arbetsformedlingen.py:322`** ·
   `apply_to_job(s, ..., today=_date.today())` — detta sätter
   `JobApplication.started_on` till real-tid medan resten av
   spelet använder spel-tid.

4. **`api/company_jobs.py:329, 415`** ·
   `today = datetime.utcnow().date()` används både för
   `list_my_employments` (auto-sweep notice_period → terminated)
   och i `terminate_employment` för LAS-uppsägningstid-räkning
   (`years_employed = (today - empl.started_at).days / 365.25`).
   `empl.started_at` är `datetime.utcnow()` (sätts av default i
   modellen) men anropas i ett spel där tiden går 168x snabbare.
   Notice-perioden (1-6 mån) blir alltid 1 mån eftersom
   anställningstiden mätts i real-tid.

5. **`business/engine/tick_engine.py:782`** ·
   `_update_capacity_from_growth` använder `_d.today()` för att
   filtrera aktiva MCP-rentals. När MCP started_on/ends_on satts
   med `current_game_date()` blir filtret fel: en MCP som
   "startas idag och slutar om 2 spel-veckor" ser ut att redan
   vara avslutad (real-today >> spel-today + 14 dagar).

6. **`business/engine/tick_engine.py:855, 884, 1105, 1320`** ·
   `datetime.utcnow()` för `tick_row.completed_at`,
   `MailItem.received_at`. Dessa är audit-tidsstämplar — diskutabelt
   om de SKA vara real-tid eller spel-tid. Om elev kommer tillbaka
   och ser "Maria-mail mottaget 2026-05-09" medan resten av postlådan
   står på 2026-02 blir det förvirrande.

**Fix:** Centralisera till `current_game_date()` i alla biz-flöden.
Lägg till `current_game_datetime()`-helper för audit-rader så vi
har en enda källa.

---

### VIKTIG · `invoice_number` har ingen unique-constraint + två numreringssystem

`backend/hembudget/business/models.py:236` ·
`invoice_number` är `String(40), nullable=False` men **inte
unique=True**. Detta i kombination med två olika genereringsvägar:

* **Via deliver_job** (`tick_engine.py:1387`):
  `f"F-{company.id:04d}-{company.jobs_delivered:04d}"`
* **Via add_invoice** (`foretag.py:972`):
  `f"{current_game_date().year}-{n_existing + 1:04d}"`

`n_existing` räknar samtliga fakturor (även de tickskapade), men
prefix är "2026-0001" istället för "F-0001-0003". Två fakturor
kan rivalisera: nya `add_invoice` kan generera "2026-0001" medan
det redan finns en deliver_job-skapad "F-0001-0001"; fungerar
men inkonsistent. Värre: två samtidiga `add_invoice` (race
condition · läraren impersonerar samtidigt som eleven klickar)
räknar `n_existing` separat i två sessions och båda får samma
nummer.

För `SupplierInvoice` (models.py:621) är det värre: tick-genererade
events får `f"EV-{week_no}-{kind[:5]}"`. Två events i samma vecka
av samma kind → identiska invoice_number, ingen unique constraint.

**Fix:**
1. Lägg `UniqueConstraint("company_id", "invoice_number")` på
   `CompanyInvoice` och `SupplierInvoice`.
2. Centralisera nummergenerering i en helper som tar company-låst
   counter (eller använder `Sequence` i Postgres-mode).
3. För events: använd `f"EV-{week_no}-{kind}-{seq}"` med seq
   från en lokal counter.

---

### VIKTIG · "Faktura-betald" boxas in 2 gånger när tick + manuell mark-paid kollideras

`tick_engine.py:282-291` (fas B) · skapar income-tx för automatiskt
betalda fakturor.
`foretag.py:1043-1052` (mark_invoice_paid) · skapar income-tx för
manuellt markerade fakturor.

Båda kollar bara `inv.status` innan tx-skapas. Om eleven manuellt
markerar status=paid i sek X, och tick fas B sedan kör i sek X+1
**innan** sessionen flushats... är scenariot låst tack vare
session_scope auto-commit. **MEN:** om frontend gör retry på
mark-paid-endpointen (network-error), eller om frontend gör
duplicate-call (React StrictMode dev-läge): andra anropet kommer
in på `inv.status="paid"` och returnerar tidigt utan att skapa
duplicat-tx. **Bra.**

**Däremot:** om någon kör `s.add(CompanyTransaction(...))` direkt
i en data-fix-skript och glömmer transactional check → riskerar
dubbel-bokföring. Ingen DB-constraint hindrar.

**Fix:** Lägg en partial unique på `(company_id, kind="income",
description LIKE 'Faktura % betald')` i Postgres. Eller skapa
en `paid_via_invoice_id`-kolumn på `CompanyTransaction` med
unique-constraint.

---

### VIKTIG · `_phase_h_milestone_mails` använder fel idempotens-key

`tick_engine.py:1300-1306`:

```python
existing = (
    s.query(MailItem)
    .filter(MailItem.subject == full_subject)
    .first()
)
```

Subjects: `"v4 · Reflektera · 4 veckor i drift"`. Om eleven har
två bolag (stänger ett, öppnar nytt) hittar denna check att v4-
mailet redan skickats för det första bolaget och hoppar över för
det andra. Pedagogiskt fel.

**Fix:** Inkludera `company.id` i subject eller body_meta.

---

### VIKTIG · `_phase_g_employment_decision_check` matchar fel mail

`tick_engine.py:1077-1082`:

```python
existing = (
    s.query(MailItem)
    .filter(
        MailItem.subject.like("Hej %· vi behöver prata om din arbetstid"),
        ...
    )
)
```

Pattern matches alla "Hej STUDENT · vi behöver prata om din arbetstid"
oavsett vem · oavsett vilket bolag. Om eleven har bolag i två
scopes (t.ex. familj-scope + solo-scope) krockar de. Mindre allvarligt
än ovan.

---

### VIKTIG · Race condition: två sessions skriver till samma scope

Flera endpoints öppnar **två separata `session_scope()` block i
samma request**:

* `apply_loan` (foretag_growth.py:689 + 776) — först läser company,
  sedan i nytt block skapar lånet. Mellan blocken kan auto_tick
  ha ändrat company.
* `buy_startup_kit` (foretag_growth.py:1093) — privat-session +
  bolags-session i sandwich, med `raise HTTPException(402)` mitt i
  som inte rollback:ar privat-mail-tx (`private_s.commit()` kallas
  innan raise).
* `decide_application` öppnar `session_scope` för scope-DB inifrån
  ett `master_session`-block (company_jobs.py:555). Om scope-sessionen
  fail:ar är master-sessionen redan committad upp till `body.decision`
  — orphaned.

**Fix:** Ett globalt request-scope (t.ex. via FastAPI dep
`Depends(scope_session)`) som gör all-or-nothing. Eller åtminstone
explicit try/finally med rollback på private_s om HTTPException
kastas mellan flushes.

---

### VIKTIG · `apply_loan` `is_personal_guarantee=False` accepteras vid UC < D men ger fortfarande godkänt

`foretag_growth.py:707-712`:

```python
if share.uc_rating == "C":
    rate += 0.02
elif share.uc_rating == "D":
    rate += 0.05
rate = max(0.03, rate)
```

UC=C ger bara +2 % ränta utan personlig borgen. Spec säger:
"UC D/E avslår om inte personlig borgen". Men UC=C→D border-
case är avgörande: en elev med UC=C får sin ansökan godkänd även
utan personlig borgen → eleven förstår inte varför hens kompis
fick avslag.

Pedagogisk yttre cut-off vid C/D är fin men inget syns för
användaren — borde finnas en visualisering "din UC ligger i 'C'-
zonen, lånet beviljas men räntan är högre".

---

### VIKTIG · "Påminnelse" bokförs som intäkt men kunden har aldrig betalat den

`foretag.py:1173-1182` (`send_invoice_reminder`):

```python
s.add(CompanyTransaction(
    company_id=c.id,
    occurred_on=today_g,
    kind="income",
    category="Påminnelseavgift",
    description=f"{label} · faktura {inv.invoice_number}",
    amount_excl_vat=amount,
    ...
))
```

Avgiften 60/60/180 kr **bokförs direkt som intäkt**. Men
påminnelseavgift är inte intäkt förrän kunden betalat den —
i verkligheten: påminnelseavgiften läggs till skulden (utökar
fordran), och bokförs först som intäkt när kund betalat.

Pedagogisk konsekvens: eleven ser sin omsättning öka 60 kr
per påminnelse, även om hen aldrig får pengarna. Värre: det
ökar moms-output och i förlängningen bolagsskatt.

**Fix:** Höja `inv.amount_excl_vat` med avgiften i stället, och
låt fas B's auto-pay bokföra HELA inkluderat tillägget när kund
betalar. Eller skapa en separat tabell för påminnelse-avgifter
som följer fakturan.

---

### MINDRE · Avskrivningar har avrundningsfel som ackumulerar

`tick_engine.py:667-670`:

```python
life = max(1, int(asset.useful_life_months or 60))
monthly_dep = float(asset.cost_excl_vat or 0) / life
weekly_dep = int(round(monthly_dep / 4))
```

För en `cost_excl_vat=15_000` / 60 mån = 250 kr/mån / 4 = 62.5
→ rundas till 63 kr/v. Över 240 veckor (5 år) blir det 15 120 kr —
120 kr över originalvärdet. Koden klippar mot
`accumulated_depreciation < cost_excl_vat` (rad 698-700) men
sista veckans bokning blir då något fel.

Större issue: `weekly_dep` är `int`, men `accumulated_depreciation`
är `Numeric(14, 2)`. Konversionen via `Decimal(str(...))` på rad
694 är OK, men "weekly_dep / 4" varierar 0/1 kr över 4 veckor
→ ojämn redovisning.

**Fix:** Räkna `monthly_dep` exakt och fördela rest till sista
veckan via Decimal-aritmetik.

---

### MINDRE · `Company.delivery_capacity` reverteras inte korrekt vid `end_decision`

`foretag_engine.py:1345-1348`:

```python
if d.capacity_delta:
    co.delivery_capacity = max(1, co.delivery_capacity - d.capacity_delta)
```

Men `compute_capacity` (foretag_growth.py:243) räknar om från
`base_max * speed_multiplier + active_mcp` — som *inte* tar
hänsyn till BusinessDecision. Däremot `_update_capacity_from_growth`
(tick_engine.py:747) sätter `delivery_capacity = base * speed + mcp`
varje tick — så förändringen i `end_decision` skrivs över direkt
vid nästa auto_tick.

**Konsekvens:** Att säga upp en anställd har INGEN effekt på
delivery_capacity i praktiken. Pipeline-genereringen påverkas
inte. Men `compute_time_capacity` läser
`Company.delivery_capacity − 1` som "fiktiva anställda" och fortsätter
ge dem 40 h/v även efter end_decision.

**Fix:** Ta bort `_update_capacity_from_growth`-överskrivningen
(eller flytta capacity_delta till en separat persistent kolumn
`Company.fictional_employees_count`).

---

### MINDRE · Pris-baseline använder `cost_multiplier_housing` som proxy

`tick_engine.py:351`:

```python
city_price_mult = float(stad.cost_multiplier_housing)
```

Bostadskostnaden i Stockholm är ~1.4x medel-stad. Men IT-konsult-
priser i Stockholm är ~1.6x medel-stad, snickeri ~1.2x. En proxy
fungerar OK för pedagogik men introducerar systematiska fel:

* Catering i en stor stad blir för billig (ska vara ~1.3-1.4x,
  blir ~1.2x).
* Frisör i en mindre stad blir för dyr.

**Fix:** Lägg till `Industry.city_price_multipliers` per nivå
(small/medium/large) eller använd en separat
`STAD_BY_KEY[city].business_price_multiplier`.

---

### MINDRE · `_compute_uc` använder approximation `income_4w * 0.6` som baseline-månadskostnad

`allabolag.py:99`:

```python
base_monthly = max(1, income_4w * 0.6)
```

Företag som inte tjänar pengar (income=0) får `base_monthly=1`
→ liquidity_score = 100/1 * 50 = 5000 → clamp till 100.
Resultat: ett bolag utan inkomst men med kassa får UC=AAA.

För ett bolag med 100k 4-veckors-omsättning:
`base_monthly = 60_000`. Kassa 20_000 → 20k/60k * 50 = 16.6 →
liquidity_score = 16. Bolaget har 1.3 mån buffert (verkligheten:
"OK liquiditet"), men UC-formeln ger låg score.

**Fix:** Räkna baseline-månadskostnad från faktiska expense-tx:
`expense_4w / 4 * 4` (= månadskostnad). Eller låt eleven se
"X månader buffert" som rå nyckeltal.

---

### MINDRE · `tick_engine.py:262` morality default 0.92, men nya opps satta till 0.9 default

`models.py:382` har `payment_morality = Decimal("0.9")` som column-default.
`tick_engine.py:262` har `morality = 0.92` som fallback om Job/opp saknas.
Skillnaden 2 % gör att deterministiska re-plays blir avvikande beroende
på om Job-raden finns.

---

### MINDRE · AuthZ-läcka: `mentor_router.candidates` filtrerar inte på publish

`biz_class_actions.py:96-104`:

```python
candidates = (
    s.query(ClassCompanyShare)
    .filter(
        ClassCompanyShare.teacher_id == stu.teacher_id,
        ClassCompanyShare.id != my_share.id,
        ClassCompanyShare.is_published.is_(True),
    )
    .all()
)
```

Den DOES filtrera på `is_published`. Men sedan väljer
`if c.profit_4w < 0` — alltså bara bolag som har sagt "publicera".
Bra.

`/v2/leaderboard/categories` filtrerar däremot **INTE** på
`is_published` (leaderboard.py:218-222). Eleven som togglat
opublicerat dyker ändå upp i topplistan med både namn och
ägare. Designval, men strider mot Allabolag-privacy.

**Fix:** Lägg `ClassCompanyShare.is_published.is_(True)` i
leaderboard-queryn. För opublicerade: visa "?" eller skip.

---

### MINDRE · Inkonsekvent moms-beräkning

`tick_engine.py:573, 919, 1172` (m.fl.) bokför subscription-/lokal-/
marknadsförings-kostnader med `vat_rate=0.25` och `vat_amount=int(round(weekly * 0.25))`.

**Decimal vs float-blandning:** `Decimal(str(int(round(weekly * 0.25))))`.
Om weekly = 7 kr (mycket små decisions) → 7*0.25 = 1.75 → round(1.75) = 2
istället för 1.75. Tappar 0.75 kr i ingående moms. Inte stort men
ackumulerar över hundratals decisions.

**Riktigare:** `Decimal(str(weekly)) * Decimal("0.25")`.

---

### MINDRE · Pengar i `int` istället för `Decimal` på flera modeller

`Company.share_capital: Mapped[int]`,
`CompanyLoan.principal/outstanding/monthly_payment: int`,
`MarketingCampaign.cost: int`,
`CompanyMcpRental.cost_total: int`,
`Job.agreed_price: int`.

Pedagogiskt kan int gå (allt avrundat till hela kr), men:
* Int-arithmetic + Decimal-arithmetic blandas i samma uttryck
  (`amt = Decimal(str(job.agreed_price))` i deliver_job rad 1384).
* Avrundningsfel ackumulerar när bolaget delar 250 kr/mån i
  weekly chunks (250/4 = 62.5 → 63).

**Fix:** Migrera till `Numeric(14, 2)` för pengar. Backåtkompat
via SQLAlchemy custom type.

---

### MINDRE · Frontend kan dölja `is_overdue` genom att räkna mot real-tid

Frontend läser `inv.due_on` och kan visa "förfallen sedan X dgr"
mot `new Date()` (browser-tid). Backend skickar redan
`is_overdue`/`days_overdue` i `InvoiceOut` (foretag.py:181-183),
beräknat mot spel-tid (`current_game_date`). Men om någon
React-komponent gör eget `Date.now()`-jämförelse blir det fel.

**Fix:** Sök i `frontend/src/v2/biz/` efter `due_on` och
verifiera att alla overdue-renderingar använder backend-fältet.

---

### MINDRE · Felmeddelanden 500 i stället för 4xx

`/v2/foretag/jobs/{id}/quality-quiz` kastar `HTTPException(500)`
om quiz-bibliotekets pool är < 3 frågor (foretag_engine.py:711).
Det är ett konfigurations-/seed-problem, inte ett serverfel —
bör vara 503 eller 422.

`api/foretag_engine.py:1779` returnerar success även när allt
faller (`n_skipped_no_company` ökas vid generic Exception). Lärar-
upplevelsen: 200 OK med "0 fakturor skickade", inget felmeddelande.

---

### MINDRE · `delivery_capacity` på `Company` läses inte från `_update_capacity_from_growth` vid create

`Company.delivery_capacity` default = 1 i modellen. Vid create
genereras 2 init-tickar i `create_company` (foretag.py:687).
`run_business_week` kör `_update_capacity_from_growth` FÖRE fas A
men vid första ticken finns ingen aktiv `CompanyLocation` → den
faller till `base = 2` (kommentar säger annat: "loc is None →
base = 2"). Eftersom `_ensure_default_location_and_equipment` bara
körs i `growth_overview`-endpoints kan `Company.delivery_capacity`
ha värde 1 trots att hemmakontor borde ge ... 1 (`max_concurrent_jobs=1`).
OK, samma värde av tillfällighet, men koden är skör.

**Fix:** Anropa `_ensure_default_location_and_equipment` i
`create_company` så vi alltid har lokal-rad innan första ticken.

---

### MINDRE · Tester saknas för kritiska kodvägar

Det finns ETT test för biz-mode: `test_e2e_biz_mode.py`. Saknas:

* `acceptance_model.evaluate_quote` med extrema värden (rep=0,
  rep=100, price 50 % under, 200 % över).
* `pipeline_generator` med 0 cap, full cap, många klagomål.
* `compute_company_cash` med olika tx-mix.
* `sync_class_company_share` med skiftande employment.
* `kickstart_pipeline_only` vs `run_business_week` (för att
  fånga dubbel-debiteringen som koden själv refererar till).
* `score_answers` (deterministisk-test som kan triggar
  random-buggen ovan).
* Race condition: två samtidiga `create_company` i samma scope.

---

### MINDRE · Idempotens-luckor i `kickstart_pipeline_only`

`tick_engine.py:709-744` kör `_phase_c_generate_opportunities` 2
gånger vid bas-utrustning-köp. Varje körning ökar `company.week_no
+= 1`. Om eleven köper bas-utrustning, sedan auto_tick triggas en
timme senare → week_no har redan ökats med 2 utan att fas-A/B/F
körts för dem. Konsekvenser:

* `BusinessTickJob`-rader saknas för v1 och v2 → audit-hål.
* `_phase_h_milestone_mails` triggas på `week_no==4` baserat på
  ökad räknare, inte på faktisk simulerad tid.

**Fix:** Lägg till en separat counter `Company.pipeline_kickstart_weeks`
som inte räknas som riktiga tick-veckor. Eller seed pipeline en
gång utan att ändra week_no (samma seed för båda → identiska
opportunities, vilket också är dåligt).

---

### MINDRE · `apply_loan` skapar privat-mail tjuvtittar mellan privat- och biz-scope

`foretag_growth.py:716-762` skickar mail till `MailItem` (privat-
scope) inom samma `with session_scope()` som biz-data. Men `MailItem`
ligger i `db.models` (privat-scope) — så det är teknisk korrekt
att den lever i scope-DB:n. **Men** koden gör `with _ps_check() as
private_s:` på rad 484 ovan, vilket är samma scope. Det blir
förvirrande att läsa eftersom kommentar säger "privat-scope" men
det är samma scope som biz för en student-elev.

För en familj-elev där biz är på familj-scope men privat på solo-
scope blir det däremot fel — vilket kan vara en latent bugg om
familjeläge någonsin används med biz.

---

## 12 · Optimeringar & förbättringar

### Performance

* **N+1 i `list_jobs`** (foretag_engine.py:519) · varje Job
  kallar `_to_job_out` som anropar `current_game_date()` som
  öppnar master_session för varje rad. Cacha en gång per request.
* **N+1 i `class_overview`** (foretag_engine.py:1581) · för varje
  elev öppnas separat `scope_context` + `session_scope`. Vid
  klass på 30 elever = 30 scope-byten. Om Postgres är aktivt
  (cloud SQL) går det OK; vid SQLite-fallback blir det ~30 file-
  open. Lös genom att läsa `ClassCompanyShare`-cachen i stället
  (den finns redan).
* **`sync_class_company_share`** kör på varje tick med 3-5 queries.
  Kan batchas via en single SQL `SELECT SUM(...) GROUP BY kind`.
* **Saknad cache** för `industry_pool` (seed_data.py) — den
  byggs varje phase_c. Beräknad listdata kan singleton:as.

### UX

* "Förlorad" offert visas i röd pill, men `decision_explanation`
  (skapad i evaluate_quote) är inte alltid enkel-läsbar. Fundera på
  en "varför?" tooltip-knapp.
* TickStatusOut visar "nästa tick om HH:MM" men inte vad ticken
  ska göra. Visa en preview "1 ny offert förväntas, 2 kunder ska
  besluta".
* Allabolag-detail har syntetisk address — gör det tydligt att
  det är fiktivt (vattenstämpel?). Annars kan eleven tro att
  det är en riktig adress.

### Pedagogik

* `_compute_level` har för höga trösklar (500k oms + 5 anställda
  för marknadsledare). Klassen kommer aldrig nå det. Sänk eller
  inför per-klass-relativa nivåer.
* Bolagsskatt 20.6 % räknas ut men `paid_on` finns inte. Eleven
  ser ingen "skatt 5 mars 2027"-händelse.
* Random events i advanced är binär (insurance täcker 90 % eller
  inte). Verkligheten har självrisk-stege. Lägg till mer nyans.
* Pris-baseline blandar "kr/h × delivery_days × 6" med "base_price
  × segment_factor". Två modeller, oklar för läraren vilken som
  gäller.
* Ingen synkronisering mellan biz-events och nyhetsbrev/postlådan
  ger eleven en "vad hände den här veckan"-summary.

### Schema-design

* `Company.delivery_capacity` är en cache av andra modeller
  (location × equipment + decisions + mcp). Gör det till en
  `@property` istället för persistent kolumn. Annars måste alla
  4 källor synkas perfekt.
* `Company.recent_quiz_question_ids` är JSON i SQLite. Postgres
  har `ARRAY` som är typsäker. Migrera när vi rör schemat.
* `JobOpportunity.industry_tag` är en string som inte är FK till
  industries.IndustryKey. Risk för typo om koden refactoras.

### Test coverage

Se buggsektion ovan. Lägg särskilt till regressionstest för:
* Maria-mail dedup när elev har 2 bolag.
* `n_employees`-sync efter accept/terminate.
* `payment_morality` distribution över 100 ticks.
* Pris-baseline för alla 10 branscher × 5 städer.

### Felhantering

* `auto_tick_if_due` swallowar exception och fortsätter — bra.
  Men loggning vid prod-fel hamnar i Cloud Logging utan tagg.
  Lägg `extra={"company_id": co.id, "week": co.week_no}`.
* `apply_loan` UC-läs:ningen är `try/except: pass` (rad 713) —
  om Master-DB är nere får eleven det bästa villkoret. Bör vara
  503 i stället.

### Skalning

* `auto_tick_if_due` körs vid varje GET. För klass på 30 elever
  som alla loggar in samtidigt på en lektion → 30 samtidiga
  pipeline_generator + AI-anrop. AI-anropet (rad 408 · 33 %
  chans per offert) kan trigga rate-limits på Anthropic. Lägg
  per-teacher-throttle.
* `ClassCompanyShare`-cachen är konsistens-kritisk. Om en elev
  loggar in samtidigt på två devices kan båda trigga
  sync_class_company_share parallellt → race på samma row.
  Lägg `with_for_update(skip_locked=True)` i Postgres-mode.

### Monitoring

Saknade prod-loggar för:
* Hur många `auto_tick_if_due` som kör per timme (sentinell för
  trafiknivå).
* Failure-rate på `BusinessTickJob.status="failed"`.
* AI-anrop per teacher_id (för att fånga overshoot mot
  ANTHROPIC_API_KEY-quota).
* `mark_invoice_paid`-double-clicks (idempotens-tester).

---

## 13 · Roadmap

Prioriterad lista, högst först.

| # | Vad | Var | Prio |
|---|---|---|---|
| 1 | Fix `n_employees=0`-skrivningen i `sync_class_company_share` | allabolag.py:219 | **kritisk** |
| 2 | Server-side `DECISION_CATALOG` så klient inte sätter `capacity_delta`/`reputation_delta` | foretag_engine.py:1186 | **kritisk** |
| 3 | Seedad `score_answers` (deterministiskt) | delivery_quiz.py:1654 | **kritisk** |
| 4 | Migrera ALLA `_d.today()`/`utcnow().date()` i biz till `current_game_date()` (cross_pentagon, arbetsformedlingen, company_jobs, tick_engine MCP-filter) | flera | **viktig** |
| 5 | `UniqueConstraint(company_id, invoice_number)` på CompanyInvoice + SupplierInvoice + central nummergenerator | models.py:236 | **viktig** |
| 6 | Påminnelseavgift bokförs vid betalning, inte vid utskick | foretag.py:1173 | **viktig** |
| 7 | `_phase_h_milestone_mails` idempotenskey ska inkludera `company_id` | tick_engine.py:1300 | viktig |
| 8 | Lägg `ClassCompanyShare.is_published` filter i leaderboard-queryn | leaderboard.py:218 | viktig |
| 9 | Skapa testsuite för engine (acceptance, pipeline, cash, sync) | tests/ | viktig |
| 10 | Implementera säsong-events i tick_engine (de är just nu visuell endast) | biz_class_actions, tick_engine | nice-to-have |
| 11 | Pris-baseline: separat `business_price_multiplier` per stad istället för housing-proxy | tick_engine.py:351 | nice-to-have |
| 12 | Migrera int-pengar till `Numeric(14, 2)` på `Company.share_capital`, `CompanyLoan.*`, `Job.agreed_price`, `MarketingCampaign.cost` | models.py | nice-to-have |
| 13 | UC-baseline-månadskostnad räknas från faktiska expenses, inte 60 % av income | allabolag.py:99 | nice-to-have |
| 14 | Detail-vyns adress-vattenstämpel "Fiktiv adress" | AllabolagDetailV2.tsx | nice-to-have |
| 15 | `delivery_capacity` blir `@property` istället för persistent | models.py:128 | nice-to-have |
