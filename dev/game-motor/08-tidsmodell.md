# 08 · Tidsmodell

> 1 spelmånad = 1 realvecka. Komprimerad tid med kvar-realism.

## Grundprincipen

Eleven ska uppleva **ett helt år av vuxen-ekonomi på ~10 veckor** av
klassrumstid. Det är så vi balanserar:

- Pedagogiskt djup (ett år = säsong, skattedeklaration, semester)
- Klassrumstempo (8–10 veckor är en normal modul-period)
- Engagemang (varje vecka händer något konkret)

## Mappning

| Realtid | Speltid |
|---|---|
| 1 dag | ~3,3 spel-dagar |
| 1 vecka | 1 spelmånad |
| 1 termin (~17 v) | ~17 spelmånader (1 år + 5 mån) |
| 1 läsår (~36 v) | 3 spelår |

## Per dag (realtid)

Varje realtidsdag är **3–4 speldagar**. Det betyder:

- En reflektion eleven skriver på fredag motsvarar ungefär en
  veckas eftertanke i spelet
- En lektion på 60 min = ~3 speldagar av "tid att fundera"
- En helg (fre-mån) = ~10 speldagar (tid att låta beslut sjunka in)

## Per vecka (realtid) = 1 spelmånad

```
Måndag      Klassrumstid · läraren introducerar veckans utmaning
Tis-Tor     Eleven gör val, läser, reflekterar (i sin egen takt)
Fredag      Echo påminnande · "vad har du gjort denna spelmånad?"
Lör-Sön     System tickar nästa månad nattetid söndag
                → lönen kommer, fakturor landar, månads-drift räknas
```

## Snabbspola

Lärare kan välja att **snabbspola** för:
- Hela klassen (alla elever en månad framåt)
- En specifik elev (för demonstration)
- Specifik datumintervall (sommarlov)

Snabbspola tickar Monthly Engine + Event Engine men **klampat**:
- Max 3 spelmånader per snabbspola-anrop (förhindra oavsiktlig spam)
- Loggas i klass-historiken
- Notis till eleven nästa gång hen loggar in: "3 månader passerade
  medan du var borta — här är din sammanfattning"

## Pausad tid

Klassens tid kan pausas:
- Sommarlov (ca 9 v) — automatiskt eller manuellt
- Sportlov / Höstlov / Påsklov
- Lärarens skönsbedömning (sjukdom, prov-period etc)

När pausad:
- Inga events triggas
- Inga lönespecar genereras
- Eleven kan logga in och se sin status, men ingenting förändras
- Pentagon-värden frysta

Tekniskt: `ClassCalendar.paused_until` sätts. Allt cron-arbete
checkar detta först.

## Säsongsevent (kvartalsvis)

Var **3:e spelmånad** triggar ett "kvartal":

| Q | Spelmånader | Triggade events |
|---|---|---|
| Q1 | jan, feb, mar | Skattedeklaration · vinter-eltoppar |
| Q2 | apr, maj, jun | Sommarsemester-planering · OB-bonus |
| Q3 | jul, aug, sep | Pensionsbesked · försäkrings-omför |
| Q4 | okt, nov, dec | Julbonus / 13:e mån · julhandelns ekonomi |

Säsongseventen är **garanterade** (inte slumpas bort), men **kan
fördröjas** om eleven inte hunnit. T.ex. Skattedeklarationen kan
vänta på Skatteverket-modul-completion.

## What-if-läge (parallell scenario)

Lärare kan starta en **parallell timeline** för en elev:

```
Original tidslinje:
  jan -> feb -> mar -> apr (eleven valde köpa BR)
  
What-if-grenen:
  jan -> feb -> mar -> apr (vad hade hänt om eleven valt hyra?)
```

Tekniskt: snapshot av elevens scope-DB + master-state vid grenpunkten.
Den nya grenen körs i en sandlåda (read-only på original-data, write
på snapshot-kopia).

Pedagogiskt värde: eleven (och läraren) ser direkt utfallet av två
val över tid.

Begränsningar:
- Max 1 aktiv what-if per elev åt gången
- Max 6 spelmånader framåt i grenen
- Grenen raderas automatiskt efter 14 dagar realtid

## Timezone & helger

All cron körs på **Europe/Stockholm**. Helgdagar respekteras:

- Julafton, Juldagen, Annandag jul → fakturor flyttas till nästa
  vardag
- Nyår → "Gott nytt år"-notis i Postlådan med året-summering
- Påsk, Midsommar → fakturor inte exakt på dagen
- Valborg, 1 maj, Pingst → helg-event (mer fritid-utgifter slumpas)

## Hastighetsval

Lärare kan justera per klass:

```yaml
weeks_per_sim_month:
  fast: 1     # Default · 1 vecka = 1 spelmånad
  normal: 2   # 2 veckor = 1 spelmånad (mer realistisk takt)
  slow: 4     # 1 månad real = 1 spelmånad (verklighetstrogen)
```

Vid `fast`: 1 termin = 17 spelmånader. Vid `slow`: 1 termin = 4
spelmånader. Olika klasser kan ha olika hastigheter.

## Lärar-paus per elev

Förutom klass-paus kan läraren **frysa en specifik elev**:
- "Filip Ö. var sjuk i 2 veckor, frys hans tid"
- Han får ingen catch-up-stress när han kommer tillbaka

Tekniskt: `Student.paused_until` sätts. Per-elev-pause overrides
klass-tick.

## Återställning

Lärare kan **rewind** en elev till tidigare spelmånad:

```python
POST /v2/teacher/students/{id}/rewind
{ "to_year_month": "2026-03" }
```

Effekt:
- Alla MailItems efter mars raderas
- Alla Transactions efter mars raderas
- Pentagon återställs till mars-värdet
- Notis till eleven: "Din lärare återställde till mars · ny start"

Används för demonstration eller om eleven gjorde något förfärligt
(släppte hela bufferten på en dag).

## Implementation

```
backend/hembudget/game_engine/
  calendar/
    __init__.py
    class_calendar.py      # ClassCalendar-modell
    advance.py             # advance_class_one_month()
    snabbspola.py          # snabbspola_klass + snabbspola_elev
    rewind.py              # Rollback till tidigare ym
    what_if.py             # Parallell-grens-snapshot
    pause.py               # Pause-utility
    season.py              # Season-event-trigger
```

## Endpoints

| Metod | URL | Syfte |
|---|---|---|
| GET | `/v2/teacher/calendar` | Aktuell klass-kalender |
| POST | `/v2/teacher/calendar/advance` | Tickar nästa månad nu |
| POST | `/v2/teacher/calendar/pause` | Pausa klassen |
| POST | `/v2/teacher/calendar/resume` | Återuppta |
| PATCH | `/v2/teacher/calendar/speed` | Ändra weeks_per_month |
| POST | `/v2/teacher/students/{id}/rewind` | Rewind elev |
| POST | `/v2/teacher/students/{id}/pause` | Pausa elev |
| POST | `/v2/teacher/students/{id}/what-if` | Skapa what-if-gren |

## Frontend

I lärar-hub:
- Aktuellt datum + spelmånad (ex "Realtid: 14 maj · Spel: jul 2026")
- "Snabbspola" / "Pausa" / "Återuppta"-knappar
- Hastighet-väljare (fast/normal/slow)

Per elev:
- "Rewind" / "Pausa elev" / "What-if-scenario"-knappar i action-bar
