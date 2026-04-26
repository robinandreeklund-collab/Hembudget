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
