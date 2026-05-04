# 04 · Event & Decision Engine

> Det som gör simuleringen levande. 1–3 oväntade händelser per
> spelmånad, försäkrings-koppling, beslut-portar och Echo-triggers.

## Översikt

Event Engine kompletterar Monthly Engine. Medan Monthly Engine sköter
det **förutsägbara** (lön kommer 25:e, hyra kommer 1:a) sköter Event
Engine det **överraskande** (tandläkaren ringer, cykeln stjäls,
arbetsförmedlingen tipsar).

Existerande `events::engine.py` + `school::EventTemplate` är grunden.
Vi utökar med:
- Försäkrings-mildring
- Konsekvens-kedjor (försenad → påminnelse → inkasso)
- Echo-triggers (proaktiv coaching)
- Lärar-injektion (TeacherMailbox-bulk)

## Event-typer

### A · Slumpade liv-händelser

Drivs av `EventTemplate`-poolen. Varje template har:
- `trigger_conditions` (when) — månads-frekvens, ålder, familjestatus
- `cost_range` — ekonomisk effekt
- `pentagon_impact` — påverkan per axel om eleven gör NO_ACTION
- `mitigations` — vad eleven kan göra (har försäkring, snabbt agerar)
- `actor_route` — vilken aktör eleven hänvisas till

**Exempel-templates:**

```yaml
- key: tandlakar_ring
  display: "Folktandvården ringde · karieskontroll"
  frequency_per_year: 0.5  # 50% chans/år
  age_range: [16, 99]
  cost_range: [3000, 6500]
  mitigations:
    - { has_policy: "tandvård_premium", multiplier: 0.10, label: "Egenavgift 500 kr" }
    - { has_policy: "tandvård_basic", multiplier: 0.50, label: "Halverad" }
    - { has_savings_buffer: 5000, multiplier: 1.0, mood: "lugn" }
  pentagon_impact_unmitigated:
    economy: -8
    health: -4   # smärta + osäkerhet
  pentagon_impact_mitigated:
    economy: -2
    health: +1   # blev åtgärdat tidigt
  echo_trigger:
    when_received: "Är det här en bra påminnelse om varför försäkring finns?"

- key: cykel_stulen
  display: "Cykeln stulen utanför arbetet"
  frequency_per_year: 0.15
  cost_range: [4000, 12000]
  mitigations:
    - { has_policy: "hemforsakring_med_drulle", multiplier: 0.15, label: "Självrisk 1500" }
  pentagon_impact_unmitigated:
    economy: -6
    leisure: -3   # ingen pendling-cykel
  
- key: bonus_julgava
  display: "Företagsbonus · ovanlig"
  frequency_per_year: 0.05
  cost_range: [-15000, -5000]  # negativ kostnad = inkomst
  pentagon_impact_unmitigated:
    economy: +5
    safety: +2

- key: arbetsloshet_varslad
  display: "Varsel · 3 mån uppsägningstid"
  frequency_per_year: 0.03
  age_range: [22, 65]
  pentagon_impact_unmitigated:
    economy: -10
    safety: -15
    health: -8   # stress
  mitigations:
    - { has_policy: "inkomstforsakring", multiplier: 0.5 }
    - { has_savings_min_3_months: true, multiplier: 0.7 }
  follow_up_chain:
    - after_days: 30
      template: "arbetsloshet_a_kassa"
    - after_days: 90
      template: "arbetsloshet_aktiv_jobbsokning"

- key: studietips_arbetsformedlingen
  display: "Arbetsförmedlingen tipsar om jobb"
  frequency_per_year: 1.5
  pentagon_impact_unmitigated: {}
  echo_trigger: "Verkar passa dig — vill du läsa mer?"
  actor_route: "/v2/arbetsformedlingen"
```

### B · Konsekvens-kedjor

Varje händelse kan starta en kedja som följer eleven över tid:

**Exempel: obetald faktura**
```
Dag 0   Faktura mottagen (postlåda)
Dag 14  Påminnelse (om ej betald) · -1 economy
Dag 30  Inkasso-varning · -3 economy, -2 social
Dag 45  Inkasso skickas (PaymentMark skapas) · -5 economy, -4 safety
Dag 90  Kronofogden · -10 economy, -8 safety, betalningsanmärkning
```

Befintlig `db::PaymentMark`-modellen används för inkasso-spårning.

**Exempel: arbetslöshet**
```
Dag 0   Varsel
Dag 30  Slutet på uppsägningstid → ingen lön
Dag 31  A-kassa-ansökan triggas (notif)
Dag 60  A-kassa-utbetalning (lägre)
Dag 90  Aktivt jobbsökande → Arbetsförmedlingen
```

### C · Försäkrings-mildring

Vid varje event-trigger körs:

```python
def apply_event(student, template, rng):
    # Kontrollera försäkringar
    relevant_policies = [
        p for p in student.insurance_policies
        if p.kind in template.relevant_kinds
        and p.active
    ]
    
    mitigation = best_mitigation(template, relevant_policies, student)
    
    cost = rng.uniform(*template.cost_range) * mitigation.multiplier
    pentagon = mitigation.pentagon_impact
    
    create_mail_item(student, template, cost, pentagon)
    if mitigation.label:
        log_to_audit(student, f"Försäkring mildrade: {mitigation.label}")
```

### D · Lärar-injektion

Existerande `/v2/teacher/mailboxes/bulk-inject` (Fas 2U) kompletteras
med möjlighet att skicka **event** istället för bara mail:

```python
POST /v2/teacher/mailboxes/bulk-inject
{
  "mode": "event",                    # ← nytt
  "template_key": "tandlakar_ring",
  "target_student_ids": [12, 17],
  "amount_override": 4200,            # valfri
  "notes": "Lektionspoäng om akut likviditet"
}
```

Det skapar event via samma motor som spontana, men med fixt belopp.

### E · Echo-triggers

Echo blir mer reaktiv. När event händer registrerar engine en
"echo_topic":

```python
class EchoTopic(MasterBase):
    student_id: int
    topic_key: str         # "post_tandlakare_pension"
    body: str              # Frågan Echo ställer
    expires_at: datetime   # Echo glömmer efter X dagar
    answered: bool
```

När eleven öppnar Echo nästa gång (eller efter 24 h) kan Echo:
- "Tandläkar-räkningen kom igår — vill du prata om hur du kunde
  ha haft tandförsäkring?"
- "Du har inte sett över din pension på 3 månader — kolla orange
  kuvertet?"

## Säsongsevent (kvartalsvis)

Var 3:e spelmånad triggas en "kvartalsrapport" — en större händelse
som påverkar flera dimensioner:

| Kvartal | Möjliga events |
|---|---|
| Q1 | Skattedeklaration · vinterns el-toppar · semester-planering |
| Q2 | Bonus / sommar-OB · semesterresa-frestelse |
| Q3 | Pensionsbesked · försäkrings-omförhandling |
| Q4 | Julbonus / 13:e månad · julhandelns kostnader |

Säsongseventen är "garanterade" — de slumpas inte bort. Men eleven
har möjlighet att förbereda sig.

## Daglig tick

Förutom månads-fasen körs en daglig tick som:
- Avgör om dagens schemalagda events ska skickas (event_template har
  `target_date` när skapad)
- Triggar konsekvens-kedjor (påminnelse på dag 14 osv)
- Uppdaterar Echo-topics (de äldsta försvinner)

## Lärar-vy: vad jag ser

I klass-hub action-bar + per elev:
- Pågående konsekvens-kedjor (varför har Filip Ö. inkasso?)
- Aktiva försäkringar (täcker eleven sina risker?)
- Senaste 30 dagars events (vad har hänt i klassen?)

I event-feed (ny vy):
- Tidslinje av alla events i klassen
- Filter: per kind, per elev, per datumintervall
- "Inject event"-knapp (använd template-poolen direkt)

## Implementation

```
backend/hembudget/game_engine/
  event_engine/
    __init__.py
    templates.py           # EventTemplate-pool definition
    trigger.py             # When ska eventet trigga?
    mitigation.py          # Försäkrings-räkning
    consequence_chain.py   # Påminnelse → inkasso etc
    echo_topics.py         # Reaktiv coaching
    daily_tick.py          # Schemalagda dagliga events
    teacher_inject.py      # Lärar-överrid

backend/hembudget/school/
  event_models.py
    EventTemplate           # befintlig, utökas
    EventInstance           # ny: konkret instans per elev
    EchoTopic               # ny
```

## Existerande integration

| Befintligt | Roll |
|---|---|
| `events::engine.tick_for_student` | Behåll, anropa från daily_tick |
| `school::EventTemplate` | Mall-poolen (utökas med försäkrings-fält) |
| `db::MailItem` | Bärare av events till elev |
| `db::PaymentMark` | Inkasso-spårning för konsekvens-kedjor |
| `insurance::*` | Försäkringsdomänen |
| `wellbeing::calculator` | Pentagon-effekt vid varje event |
