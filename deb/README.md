# Fullständig analys: Modulen "Mitt företag"

Entreprenörskaps- och företagsekonomi-simulator för Ekonomilabbet.

Nedan är en komplett designanalys för att lyfta pappersmaterialet till en
fullt integrerad modul i Ekonomilabbet, med egen undersida, eget datalager
och full koppling till befintlig modul-, AI- och lärarinfrastruktur.
Inga kodändringar — bara arkitektur, pedagogik, mekanik och konkreta
integrationspunkter.

---

## 1. Konceptet i en mening

En **dynamisk företagssimulator** där eleven driver ett självvalt enskilt
företag över 8–16 simulerade veckor: får offerter från en AI-driven
kundpool, fakturerar, bokför, stämmer av bank, tar strategiska beslut
(marknadsföring, anställning, friskvård), och får läraren som
"myndighet/leverantör" som matar in skatter, leverantörsfakturor och
granskning. Allt finns på en egen undersida `/business` (elev) och
`/teacher/business` (lärare), men kompetensmål, AI-feedback,
rubric-bedömning och progress-spårning återanvänder den befintliga
modul-infrastrukturen från `school/models.py`.

---

## 2. Hur det passar i befintlig arkitektur

Det stora värdet är att **ingenting ska byggas från noll** — ni har redan
alla byggstenar:

| Behov i nya modulen | Befintlig komponent som återanvänds |
|---|---|
| Stegbaserad genomgång (intro, teori, kvitto, reflektion) | `Module` + `ModuleStep` (`school/models.py:472-524`) med kinds `read/watch/reflect/task/quiz` |
| Per-elev-progress, heartbeat, tid på uppgift | `StudentModule`, `StudentStepProgress`, `StudentStepHeartbeat` |
| Kompetensmål per delmoment | `Competency` + `ModuleStepCompetency` (`competency_seed.py`) — bara nya kompetenser läggs till |
| Lärar-feedback på reflektion + AI-rubric | `ai.py::generate_feedback_suggestion` och `score_with_rubric` |
| Eleven frågar AI om regler/skatt/bokföring | `ai.py::answer_student_question` (`/ai/student/ask` + stream) |
| Multi-tenant isolering av företaget per elev | `StudentScopeMiddleware` + `TenantMixin` — nya tabeller ärver bara mixin |
| Fakturor som PDF | `teacher/pdfs.py` (reportlab) — samma motor som lönespec/kontoutdrag |
| Lärar-genererade artefakter (leverantörsfaktura, skattebesked) | `ScenarioBatch` + `BatchArtifact` (`school/models.py:260-332`) — utöka enbart med nya `kind`-värden |
| Bokförda transaktioner och kontoplan | `Account`, `Transaction`, `Category` (i scope-DB) — utökas med dimensionerna `debit_account`/`credit_account` |
| Token-räkning per lärare för all AI | `ai.py::_record_usage` |

**Slutsats:** modulen blir ett *nytt domänlager ovanpå* dagens motor, inte
en parallell stack. Ny kod behöver i princip bara: nya scope-tabeller
(företag, offerter, kunder, jobb), en ny seed-mall i `module_seed.py`, ett
par nya `Assignment.kind`, fyra–fem nya AI-funktioner i `ai.py`, en ny
router (`api/business.py`) och en ny frontend-sektion `pages/business/`.

---

## 3. Två svårighetsnivåer i en och samma simulator

Materialet ska serva **Företagsekonomi 1 / Entreprenörskap** (grund) **och
Företagsekonomi 2** (fördjupning). Lös detta med ett *läge* på
företagsnivån istället för två moduler:

- **Grundläge** (`level: "basics"`)
  - Manuell resultaträkning som steg (eleven fyller i belopp i ett
    formulär; systemet visar facit)
  - Förenklad bokföring: bara intäkter/kostnader/resultat — inga T-konton
  - Marknadsföring och beslut är "knappval", inte fri text
  - Avstämning sker veckovis automatiskt
  - Inga nyckeltal, ingen revision

- **Fördjupningsläge** (`level: "advanced"`)
  - Riktig dubbel bokföring (debet/kredit) mot en pedagogiskt förenklad
    BAS-kontoplan (~30 konton)
  - Bankavstämning: läraren genererar kontoutdrag (befintlig
    `render_kontoutdrag`!) som eleven matchar mot egna bokförda poster
  - Nyckeltal: bruttomarginal, soliditet, likviditet,
    omsättningshastighet — räknas och redovisas
  - **Peer-revision**: en elev tilldelas en kamrats bokföring, går igenom
    checklist, lämnar revisionsrapport (rubric-bedömd av AI)

Spara läget på själva företagsentiteten så att samma lärare kan ge en
åttonde-klass enklare läge och en gymnasieelev avancerat — utan att
klona modulen.

---

## 4. Kärndomänmodell (nya tabeller, scope-isolerade)

Allt ärver `TenantMixin` så att `StudentScopeMiddleware` automatiskt
isolerar per elev. Inga kolumner anges här (det är design, inte schema),
bara entiteterna och varför de finns.

1. **Business** — själva företaget. Affärsidé (fritext från eleven,
   AI-modererad), bransch (vald från enum: hantverk, IT-tjänster, café,
   hundpassning, e-handel, konsult, kreativ tjänst …), startdatum, läge
   (basics/advanced), simuleringstakt (1 vecka i spelet = X minuter
   realtid eller "stega manuellt"), nuvarande "rykte" (0–100, drivs av
   kvalitet på leveranser).
2. **Customer** — kundpool genererad av systemet. Har segment
   (privat/företag/kommun), priskänslighet, kvalitetskänslighet,
   betalningsmoral.
3. **JobOpportunity** — en offertförfrågan. Beskrivning, marknadsmässigt
   riktpris, deadline, status (open/quoted/won/lost/done/cancelled).
4. **Quote** — elevens offert på en JobOpportunity. Pris, leveranstid,
   beskrivning, ev. fritextpitch.
5. **Job** — vunnen offert som blir uppdrag. Status
   (in_progress/delivered/disputed), kvalitetspoäng vid leverans (sätts
   av eleven själv eller ett "kvalitetsbeslut"-steg).
6. **CustomerInvoice** — kundfaktura kopplad till Job. Förfallodatum,
   status (sent/paid/overdue), bokföringsförslag.
7. **SupplierInvoice** — leverantörsfaktura inkommande. Källa: antingen
   genererad av systemet (hyra, abonnemang) eller skapad manuellt av
   läraren (för pedagogiska oväntade händelser: "du har fått en
   miljöskatt", "datorn gick sönder").
8. **MarketingCampaign** — typ (sociala medier, flygblad,
   Google-annonser, sponsring), kostnad, varaktighet, kvalitet (eleven
   får välja innehåll, AI-bedömer).
9. **BusinessDecision** — generisk "stora beslut": anställa timanställd,
   friskvårdsbidrag, byta lokal, leasingbil, försäkring. Param-driven
   (samma mönster som `Assignment.params`).
10. **LedgerEntry** — bokföringspost i avancerat läge: datum,
    verifikationsnummer, debet-konto, kredit-konto, belopp, motpart. Två
    rader per affärshändelse.
11. **ChartOfAccount** — pedagogisk kontoplan (bara avancerat läge),
    seedad globalt.
12. **ReconciliationSession** — bankavstämning: lista över bokförda
    poster + lista över bankposter + matchningar.
13. **AuditAssignment** — peer-revision: en elev får en kamrats
    bokföringspaket att granska.

Det viktiga: **alla "händelser" mynnar ut i en eller flera
`Transaction`+`LedgerEntry`** så att resultaträkningen byggs på samma
motor ni redan har. Kundfaktura → en transaktion på "Försäljning";
faktura betald → överföring till bankkontot. Det här är direkt analogt
med hur ert nuvarande system kategoriserar privata transaktioner.

---

## 5. Spelmekanik: "Programmet avgör"

Det här är hjärtat i materialet och behöver vara *transparent men inte
för enkelt*. Två separata mekanismer:

### 5.1 Tar kunden offerten?

En **acceptansmodell** med viktade faktorer, beräknad deterministiskt
(inte LLM — du vill att läraren ska kunna förklara varför):

```
P(accept) = sigmoid(
    w1 * (riktpris - elevpris) / riktpris        # priskänslighet per kund
  + w2 * företagets_rykte                         # 0–100
  + w3 * marknadsföringseffekt_just_nu            # avtagande över tid
  + w4 * matchning_pitch_mot_behov                # AI-bedömt 0–1
  - w5 * leveranstid_avvikelse                    # för långsam = nej
)
```

Slumptal jämförs mot P(accept). Eleven får alltid se en kort motivering
("Kunden tyckte priset var rimligt men du lovade leverans 3 veckor —
för långsamt"). Det här uppfyller "programmet avgör om kunden accepterar
offerten".

### 5.2 Får eleven fler liknande jobb?

En **pipeline-genererare** som körs när simuleringen stegar fram en
vecka:

```
antal_nya_jobb_denna_vecka = base
  + bonus(rykte)
  + bonus(aktiva_marknadsföringskampanjer)
  + bonus(senaste_levererade_kvalitet)
  - penalty(öppna_klagomål)
```

Branschmix viktas av elevens historiska affärsidé och eventuellt nya
kompetenser (köpte de en kurs i webbutveckling? Då dyker fler IT-jobb
upp). Det är "programmet avgör om eleven får fler liknande jobb".

**Varför inte LLM här?** För att läraren behöver kunna säga "därför
fick du tre jobb istället för ett" och eleven måste kunna räkna ut
samband — annars går pedagogiken förlorad. LLM används bara för
*innehåll* (kundtext, jobbeskrivning, pitch-bedömning), inte för
*beslut* (acceptans, antal jobb). Det är en viktig arkitekturprincip.
