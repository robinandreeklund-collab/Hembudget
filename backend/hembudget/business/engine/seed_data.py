"""Seed-data för spelmotorn: kunder + jobbmallar per bransch.

Spec: deb/README.md avsnitt 4 (Customer/JobOpportunity) + avsnitt 14
("hand-skrivna kunder ger pedagogisk kontroll").

10 fasta branscher (matchar business/industries.py). VARJE bransch
har 4-6 kundtyper + 6-10 jobbmallar med konkreta, pedagogiskt
användbara beskrivningar — eleven ska kunna förstå exakt VAD jobbet
gäller och kunna skriva en meningsfull pitch utan att gissa.

Pipeline_generator drar mallar deterministiskt baserat på (company_id,
week_no). AI (generate_job_description) berikar slumpvis 100% av
nya opps med varierade beskrivningar — fallback här är medvetet
DETALJERAD så även AI-fri-läget håller pedagogisk kvalitet.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CustomerSeed:
    name: str
    segment: str            # privat | foretag | kommun
    price_sensitivity: float  # 0..1 (1 = väldigt priskänslig)
    quality_sensitivity: float  # 0..1
    payment_morality: float  # 0..1 (1 = betalar i tid)


@dataclass
class JobTemplate:
    title: str
    description: str
    base_price: int          # SEK exkl moms · justeras av pricing-modul
    delivery_days: int
    industry_tag: str


# === 1. IT-konsult ===

IT_KONSULT_CUSTOMERS = [
    CustomerSeed("Helena Sjöberg", "privat", 0.40, 0.80, 0.92),
    CustomerSeed("Café Sol & Måne", "foretag", 0.65, 0.60, 0.88),
    CustomerSeed("Tandläkarmottagningen Vita Leendet", "foretag", 0.50, 0.75, 0.95),
    CustomerSeed("Anders Karlsson Konsult AB", "foretag", 0.55, 0.70, 0.90),
    CustomerSeed("Föreningen Fritidsbåtar", "foretag", 0.55, 0.65, 0.88),
    CustomerSeed("Kommunens IT-avdelning", "kommun", 0.80, 0.55, 0.99),
]

IT_KONSULT_JOBS = [
    JobTemplate(
        "Migrera mailservern till Microsoft 365",
        "12 anställda, behöver flytta från egen server till Microsoft 365 inkl. delade kalendrar och delade mappar. Vill ha 30 min utbildning per anställd. Ingen befintlig dokumentation — du får börja från noll.",
        18000, 7, "it_konsult",
    ),
    JobTemplate(
        "Sätta upp säker VPN till hemmakontor",
        "5 personer arbetar hemifrån, behöver krypterad uppkoppling till företagsservern. Vill ha 2-faktorautentisering och dokumenterad rutin för förlorade enheter.",
        9500, 4, "it_konsult",
    ),
    JobTemplate(
        "Felsökning återkommande WiFi-problem",
        "Kontoret har 25 personer, WiFi droppar 3-4 gånger per dag. Mätning, rådgivning kring nya accesspunkter, samt installation om nödvändigt. Hembesök ingår.",
        4800, 2, "it_konsult",
    ),
    JobTemplate(
        "Backuplösning + disaster recovery-plan",
        "Bokföringsbyrå med 8 anställda. Vill ha automatisk backup till krypterad molntjänst + dokumenterad återställningsrutin som de kan testa själva varje kvartal.",
        14000, 5, "it_konsult",
    ),
    JobTemplate(
        "GDPR-genomgång + åtgärdsplan",
        "Liten konsultfirma som aldrig gjort en GDPR-inventering. Vill veta vad de lagrar, var, och vad som behöver ändras. Leverans: rapport + 1 h workshop.",
        12500, 7, "it_konsult",
    ),
    JobTemplate(
        "Uppgradera 12 datorer från Win 10 till Win 11",
        "Hårdvaran funkar men användarna är osäkra. Du gör uppgraderingen + 15 min snabb-utbildning per dator. Måste ske utanför kontorstid.",
        16500, 5, "it_konsult",
    ),
    JobTemplate(
        "IT-policy för nyanställda",
        "Företag växer från 6 till 15 anställda. Behöver onboarding-checklista för IT (konton, lösenord, säkerhet, BYOD). 4-5 sidor.",
        7800, 4, "it_konsult",
    ),
]


# === 2. Webb- & grafisk designer ===

WEBBDESIGNER_CUSTOMERS = [
    CustomerSeed("Mona Lindqvist Yoga", "foretag", 0.65, 0.75, 0.90),
    CustomerSeed("Restaurang Lilla Stället", "foretag", 0.70, 0.65, 0.88),
    CustomerSeed("Snickeri Berg & Söner", "foretag", 0.55, 0.55, 0.92),
    CustomerSeed("Författaren Per Eriksson", "privat", 0.45, 0.80, 0.93),
    CustomerSeed("Idrottsföreningen IFK Norra", "foretag", 0.75, 0.55, 0.85),
]

WEBBDESIGNER_JOBS = [
    JobTemplate(
        "Designa ny hemsida — 5 sidor",
        "Yoga-studio som vill flytta från Wix till en egen WordPress-sida. Behöver schema-bokning, prislista, lärar-presentationer. Vill ha lugn naturpalett, sans-serif.",
        14500, 10, "webbdesigner",
    ),
    JobTemplate(
        "Logotyp + grafisk profil",
        "Restaurang som öppnar nästa månad. Behöver logotyp i 3 versioner (full, ikonisk, mono), färgpalett, typsnittsval. Du får 3 förslag, 2 revideringar.",
        9500, 7, "webbdesigner",
    ),
    JobTemplate(
        "Webbshop för småföretag — 30 produkter",
        "Snickeri vill sälja brädor och möbler online. Shopify-baserad, betalning via Klarna/Swish. 30 produkter med foto + beskrivning, frakt-uppsättning.",
        24500, 14, "webbdesigner",
    ),
    JobTemplate(
        "Bokomslag + tryckdesign",
        "Författare ska självpublicera bok. Behöver omslag (front, baksida, rygg) i tryck-kvalitet. Du läser första kapitlet för att fånga stämningen.",
        7200, 7, "webbdesigner",
    ),
    JobTemplate(
        "Logo-redesign + profilmaterial",
        "Idrottsförening fyller 50 år. Vill modernisera men behålla färgerna. Logo + matchprogram-mall + Instagram-template.",
        11500, 10, "webbdesigner",
    ),
    JobTemplate(
        "Landningssida för produktlansering",
        "En-sidas landningssida med formulär för intresseanmälningar, integration mot Mailchimp, Google Analytics. Klar inom en vecka, lansering hård deadline.",
        8500, 5, "webbdesigner",
    ),
    JobTemplate(
        "Banners + sociala medier-kit",
        "Företag har ny produkt. Behöver 12 banners i olika format för Facebook, Instagram, LinkedIn + Google Ads. Tema: rörig storstad blir lugn.",
        6800, 5, "webbdesigner",
    ),
]


# === 3. Snickare / hantverkare ===

SNICKARE_CUSTOMERS = [
    CustomerSeed("Familjen Lindqvist", "privat", 0.55, 0.60, 0.95),
    CustomerSeed("BRF Solrosen", "foretag", 0.70, 0.50, 0.90),
    CustomerSeed("Petra Hansson", "privat", 0.45, 0.70, 0.95),
    CustomerSeed("Bygg & Bo AB", "foretag", 0.60, 0.55, 0.85),
    CustomerSeed("Kommunens fastighetsförvaltning", "kommun", 0.80, 0.40, 0.99),
]

SNICKARE_JOBS = [
    JobTemplate(
        "Bygga altan 18 kvm",
        "Villaträdgård, sluttande mark. Tryckimpregnerat virke, två trappsteg, räcke ena sidan. Kunden köper materialet själv. ROT-avdrag förväntas.",
        38000, 21, "snickare",
    ),
    JobTemplate(
        "Köksluckor + bänkskiva renovering",
        "30-tals villa, kök 8 kvm. Slipa befintliga luckor + måla, ny laminerad bänkskiva (3 m), nya handtag. Kund vill ha klassisk vit.",
        24500, 14, "snickare",
    ),
    JobTemplate(
        "Bygga garderober i hallen",
        "Inbyggda från golv till tak, 2,4 m bred, 60 cm djup. Skjutdörrar med spegel. Inredning: 4 hyllor + skorack.",
        22000, 12, "snickare",
    ),
    JobTemplate(
        "Reparera trasigt staket — 20 m",
        "Hagforsstaket, 6 stolpar har ruttnat och ska bytas. Räfflad gran. Kund vill också ha ny grind 90 cm bred.",
        7500, 4, "snickare",
    ),
    JobTemplate(
        "Tapetsera hall + trappa",
        "Halv-stor villa, ca 30 kvm väggyta, två tapettyper (mörk hall, ljus trappa). Existerande tapet ska tas bort först.",
        12500, 8, "snickare",
    ),
    JobTemplate(
        "Lägga klinker i badrum 6 kvm",
        "Helkaklat 6 kvm badrum från 80-talet. Riv ut befintligt, fixa underlag, lägg nytt klinker (kund har valt). Tätskikt enligt branschnorm.",
        29500, 14, "snickare",
    ),
    JobTemplate(
        "Bygga uthus / förråd 6 kvm",
        "Trädgårdsförråd 3×2 m, plåttak, en dörr, ett fönster. Kund vill ha det rödfärgat. Bygglovsanmälan klar.",
        32000, 18, "snickare",
    ),
    JobTemplate(
        "Slipa och olja trägolv 35 kvm",
        "Vardagsrum + matsal, gammalt furugolv, slitet med fläckar. Slipning, dammbindning, 3 lager hård-olja.",
        18500, 7, "snickare",
    ),
]


# === 4. Rörmokare / VVS ===

RORMOKARE_CUSTOMERS = [
    CustomerSeed("Familjen Andersson", "privat", 0.45, 0.70, 0.95),
    CustomerSeed("BRF Hagaparken", "foretag", 0.65, 0.55, 0.92),
    CustomerSeed("Restaurang Kvarnen", "foretag", 0.60, 0.65, 0.90),
    CustomerSeed("Nya Skolan AB", "foretag", 0.70, 0.60, 0.93),
    CustomerSeed("Kommunens lokalförvaltning", "kommun", 0.75, 0.50, 0.99),
]

RORMOKARE_JOBS = [
    JobTemplate(
        "Byta blandare i kök + diskmaskin-anslutning",
        "60-tals köksö som behöver helt ny blandare och anslutning för ny diskmaskin. Vatten avstängt 2 timmar. Akut, läcker idag.",
        4500, 1, "rormokare",
    ),
    JobTemplate(
        "Renovera badrum — vattenledningar",
        "Helrenovering, 6 kvm. Du gör vattenrör + avlopp + dolda förgreningar. Plattsättning sker av annan firma. Tätskikt och våtrumsintyg ingår.",
        38000, 14, "rormokare",
    ),
    JobTemplate(
        "Byta värmepanna",
        "Villa, gammal oljepanna 15 år, ska bytas till luft-vatten värmepump. Borrning + installation + driftsättning. ROT-avdrag och energirådgivning ingår.",
        72000, 10, "rormokare",
    ),
    JobTemplate(
        "Reparera trasigt avlopp",
        "BRF, 2:a vån, översvämning från tvättstugan. Akut! Behöver komma fram dagen efter, lokalisera och åtgärda. Försäkring täcker delvis.",
        8500, 1, "rormokare",
    ),
    JobTemplate(
        "Installera vattensparventiler — 12 lägenheter",
        "BRF vill spara på varmvatten. 12 lägenheter, byta blandare i kök + dusch. Schemalagt, 3 dagar.",
        24000, 7, "rormokare",
    ),
    JobTemplate(
        "Byta toalettstol + vatten-anslutning",
        "Standard toalett behöver bytas (sprucken). Inkl. vatten-anslutning, golvbrunn-koll, bortforsling av gammal.",
        4200, 1, "rormokare",
    ),
    JobTemplate(
        "Installera ny diskbänk + vattenledning",
        "Restaurang vill ha extra industri-diskbänk i köket. Drar fram både kall- och varmvatten + nytt avlopp under befintligt skåp.",
        9500, 3, "rormokare",
    ),
]


# === 5. Elektriker ===

ELEKTRIKER_CUSTOMERS = [
    CustomerSeed("Familjen Wallin", "privat", 0.50, 0.70, 0.95),
    CustomerSeed("Kontorsfastigheten Vasa 12", "foretag", 0.65, 0.60, 0.92),
    CustomerSeed("Café Mocca", "foretag", 0.65, 0.60, 0.88),
    CustomerSeed("BRF Lärkträdet", "foretag", 0.70, 0.55, 0.92),
    CustomerSeed("Kommunens skolor", "kommun", 0.80, 0.55, 0.99),
]

ELEKTRIKER_JOBS = [
    JobTemplate(
        "Byta proppskåp + säkringar",
        "Villa från 70-talet, behöver modern jordfelsbrytare och nya automater. Inkl. besiktning av installationen + dokumentation.",
        14500, 3, "elektriker",
    ),
    JobTemplate(
        "Installera laddbox för elbil",
        "Garage, befintlig 16A trefas finns. Du installerar 11 kW laddbox, parkopplar med app, anmäler till nätägare. Bidrag finns.",
        18000, 2, "elektriker",
    ),
    JobTemplate(
        "Dra ny el i renoverat badrum",
        "Helrenovering, 6 kvm. Behöver belysning (3 punkter) + jordat uttag + golvvärme-styrning. Våtrumsintyg.",
        9500, 3, "elektriker",
    ),
    JobTemplate(
        "Felsöka jordfelsbrytare som löser ut",
        "Café, jordfelsbrytaren slår ifrån varje dag i lunchrusningen. Du måste hitta vilken apparat som läcker. Får inte stänga restaurangen.",
        3800, 1, "elektriker",
    ),
    JobTemplate(
        "Belysning i kontorslokal — 250 kvm",
        "Kontor flyttar in, behöver LED-armaturer i 250 kvm öppet kontor + 6 mötesrum. Energieffektivt, dimbart, anpassningsbart.",
        45000, 14, "elektriker",
    ),
    JobTemplate(
        "Installera spis + ugn",
        "Lägenhet får ny köksinredning. Du drar fram trefas till spisen, jordat uttag bakom + besiktning före driftsättning.",
        4200, 1, "elektriker",
    ),
    JobTemplate(
        "Dra fram el till uthus + belysning",
        "Trädgård 30 m till nytt uthus. Du gräver kabeldike + drar markkabel + installerar 3 uttag och tak-belysning. ROT-avdrag.",
        16500, 5, "elektriker",
    ),
]


# === 6. Frisör / barberare ===

FRISOR_CUSTOMERS = [
    CustomerSeed("Walk-in-kund", "privat", 0.65, 0.55, 1.00),
    CustomerSeed("Stamkund med abonnemang", "privat", 0.40, 0.85, 0.99),
    CustomerSeed("Bröllopsföljet (5 personer)", "privat", 0.30, 0.90, 0.95),
    CustomerSeed("Konferensgrupp - klipp + frukost", "foretag", 0.60, 0.65, 0.90),
    CustomerSeed("Föreningen Tonårsgruppen", "foretag", 0.75, 0.50, 0.92),
]

FRISOR_JOBS = [
    JobTemplate(
        "Klippning + styling damer",
        "Nya kund, axellångt hår, vill ha bob med slingor. Tvätt, klippning, slingor (full kalott), färginlägg, föna. Konsultation 10 min innan.",
        1450, 1, "frisor",
    ),
    JobTemplate(
        "Bröllopsfrisyr inkl. provning",
        "Brud, axellångt hår, vill ha low-bun med blommor. Provning 1 vecka innan + själva bröllopsdagen. Hemma hos kund för bröllopet.",
        4200, 7, "frisor",
    ),
    JobTemplate(
        "Klippning herrar — abonnemang",
        "Stamkund, vill teckna 4-månaders abonnemang (klippning var 4:e vecka). Skägg-trim ingår. Lojalitetspris.",
        2800, 1, "frisor",
    ),
    JobTemplate(
        "Färgning helt — från brunett till blond",
        "Stor färgförändring. Två sittningar (urblekning + tonande), dvs. flera timmar. Kund vill ha detaljerat förklaring av processen + skadekontroll.",
        4800, 2, "frisor",
    ),
    JobTemplate(
        "Styling + klippning för fotograf-jobb",
        "Modell behöver klassisk styling för katalog-fotografering. Måste matcha specifik look (referensbild). Kund kommer på morgonen och åker direkt till studio.",
        1850, 1, "frisor",
    ),
    JobTemplate(
        "Klippning gruppbokning — 5 tonåringar",
        "Föreningens 5 tonårspojkar inför sommarlov. Snabb-klipp, fade-style, alla bokade samtidigt en lördag. Pris per person.",
        2500, 1, "frisor",
    ),
    JobTemplate(
        "Hårförlängning",
        "Kunden vill gå från axellångt till midjelångt. Tape-extensions, ca 100 g hår. Konsultation, mätning, montering 3-4 timmar. Inkl. instruktion + skötselråd.",
        7500, 1, "frisor",
    ),
]


# === 7. Coach / livsstilsexpert ===

COACH_CUSTOMERS = [
    CustomerSeed("Familjen Forss", "privat", 0.45, 0.70, 0.93),
    CustomerSeed("Studio Kreativa AB", "foretag", 0.60, 0.65, 0.88),
    CustomerSeed("Region Mellan", "kommun", 0.75, 0.50, 0.99),
    CustomerSeed("Startup Foodie", "foretag", 0.55, 0.70, 0.85),
    CustomerSeed("HR-avdelning Stora bolaget", "foretag", 0.55, 0.75, 0.95),
]

COACH_JOBS = [
    JobTemplate(
        "Karriärcoaching — 5-pakets-session",
        "Privatperson 38 år vill byta yrke. 5 sessioner à 1 h, 1 gång per vecka. Inkl. tester, hemuppgifter och CV-genomgång.",
        9500, 35, "coach",
    ),
    JobTemplate(
        "Workshop ledarskap — halvdag",
        "Företag med 8 mellanchefer. 4 timmar workshop om feedback-kultur + coaching-stil. Inkl. dokumentation och 1 h uppföljning per chef.",
        18500, 14, "coach",
    ),
    JobTemplate(
        "Stresshantering föreläsning",
        "Stort företag bjuder in alla 60 anställda till 60-minuters föreläsning + Q&A. Inkl. handout och länksamling.",
        12500, 7, "coach",
    ),
    JobTemplate(
        "1:1-coaching VD",
        "Startup-VD som behöver klargöra strategiska val. 6 sessioner à 1,5 h över 3 månader. Konfidentiellt, eget verktyg för uppgifter mellan sessioner.",
        22000, 90, "coach",
    ),
    JobTemplate(
        "Föräldra-workshop sömn + skärm-tid",
        "Förskola bjuder in föräldrar. 2 timmar interaktiv workshop med konkreta tips. Du tar med material och övningar.",
        8500, 7, "coach",
    ),
    JobTemplate(
        "Konfliktlösning-möte arbetsgrupp",
        "5 personer i en arbetsgrupp som kommer dåligt överens. Halv dag medling + 1 h uppföljning efter 2 veckor.",
        14500, 14, "coach",
    ),
    JobTemplate(
        "Onboarding-program nya chefer",
        "Region anställer 8 nya enhetschefer. Du tar fram 4-veckors onboarding-program (självstudier + möten) + handleder själva onboardingen.",
        38000, 21, "coach",
    ),
]


# === 8. Personal Trainer / friskvård ===

PERSONAL_TRAINER_CUSTOMERS = [
    CustomerSeed("Privatkund — vill gå ner i vikt", "privat", 0.60, 0.65, 0.95),
    CustomerSeed("Stamkund — abonnemang 6 mån", "privat", 0.40, 0.85, 0.99),
    CustomerSeed("Företag AB — friskvård", "foretag", 0.55, 0.70, 0.95),
    CustomerSeed("Förskolan Kotten — personalvård", "foretag", 0.70, 0.55, 0.92),
    CustomerSeed("Idrottsföreningen Springpojkarna", "foretag", 0.75, 0.55, 0.85),
]

PERSONAL_TRAINER_JOBS = [
    JobTemplate(
        "PT-paket 10 sessioner — viktnedgång",
        "Privatperson 35 år, mål: gå ner 15 kg på 6 månader. 10 sessioner à 1 h med kostrådgivning + uppföljning av kroppsmätningar.",
        9500, 60, "personal_trainer",
    ),
    JobTemplate(
        "Företagsfriskvård — månadsabonnemang",
        "10 anställda får 1 PT-session per månad i 6 månader. Schemaläggning via kalender, lokalen tillhandahålls av kund.",
        24000, 30, "personal_trainer",
    ),
    JobTemplate(
        "Löpträning inför maratonsen",
        "Stamkund, klar med halvmaratonen, ska springa Stockholm Marathon. 16 veckors program, 2 PT-sessioner/v + skriftligt program de andra dagarna.",
        18500, 112, "personal_trainer",
    ),
    JobTemplate(
        "Rehab-träning efter knäoperation",
        "55 år, ny korsbandsplastik, klar med fysio. 8 sessioner specialträning för att komma tillbaka till tennis. Fysioterapeut-rapport bifogad.",
        7800, 56, "personal_trainer",
    ),
    JobTemplate(
        "Workshop ergonomi för personal",
        "Förskola, 12 personer. 2 timmar interaktiv workshop om lyft-teknik + stress-stretching. Lokal: deras eget pausrum.",
        7500, 7, "personal_trainer",
    ),
    JobTemplate(
        "Träningsläger weekend — idrottsförening",
        "12 ungdomar 14-16 år, 2 dagar intensiv förberedelseträning. Inkl. matnings-rådgivning och lekar för gruppdynamik.",
        14500, 21, "personal_trainer",
    ),
    JobTemplate(
        "Online-coaching med video-feedback",
        "Distanskund, 4 månader, du skickar program via app + ger feedback på inskickade träningsvideos varje vecka.",
        6800, 120, "personal_trainer",
    ),
]


# === 9. Fotograf ===

FOTOGRAF_CUSTOMERS = [
    CustomerSeed("Familjen Berg", "privat", 0.55, 0.75, 0.93),
    CustomerSeed("Galleri Norrlandet", "foretag", 0.70, 0.60, 0.88),
    CustomerSeed("Förlaget BokKraft", "foretag", 0.55, 0.70, 0.92),
    CustomerSeed("Brudpar Söderlind", "privat", 0.30, 0.90, 0.95),
    CustomerSeed("Restaurang Lindesbergs", "foretag", 0.60, 0.70, 0.90),
    CustomerSeed("Kommunens kommunikationsenhet", "kommun", 0.75, 0.55, 0.99),
]

FOTOGRAF_JOBS = [
    JobTemplate(
        "Bröllopsfotografering hel dag",
        "Bröllopspar, 80 gäster, fotografering kl 12-22. Förlovning + ceremoni + middag + dans. Leverans: 250 redigerade bilder + foto-bok 30 sidor.",
        24500, 21, "fotograf",
    ),
    JobTemplate(
        "Familjefotografering utomhus",
        "Familj 4 personer, höstskogen, 1,5 timmar. Leverans: 30 redigerade bilder digitalt + 5 utskrifter A4. Egna kläder, du föreslår posing.",
        4200, 7, "fotograf",
    ),
    JobTemplate(
        "Produktfotografering webshop — 25 produkter",
        "Smyckesbutik, 25 produkter. Vit bakgrund + lifestyle på modell. Leverans: 4 bilder per produkt (front, sida, detalj, lifestyle), retuscherade.",
        12500, 10, "fotograf",
    ),
    JobTemplate(
        "Konferens-dokumentation 1 dag",
        "Heldagskonferens 200 deltagare. Du dokumenterar talare, breakout-sessions, mingel. Leverans: 100 redigerade bilder inom 48 h.",
        8500, 3, "fotograf",
    ),
    JobTemplate(
        "Restaurang-meny fotografering",
        "Restaurang öppnar i augusti. 18 rätter ska fotograferas. Du ansvarar för styling tillsammans med kock. Halv dag.",
        9500, 7, "fotograf",
    ),
    JobTemplate(
        "Personalfoton kontor",
        "12 anställda, individuella headshots + grupp. Studio-look mot grå/svart bakgrund. Färdiga inom en vecka.",
        7800, 5, "fotograf",
    ),
    JobTemplate(
        "Bok-illustrationer + omslag",
        "Författare ska självpublicera novellsamling. 8 svartvita illustrationer + omslag (front + baksida). Leverans tryck-färdig.",
        18500, 28, "fotograf",
    ),
    JobTemplate(
        "Hemförsäljning fastighet",
        "Mäklare beställer foto av 4 lägenheter på rad, varje 3-rummare. Du fotograferar inomhus + balkong. 25 bilder per lägenhet.",
        14500, 3, "fotograf",
    ),
]


# === 10. Catering / kokerska ===

CATERING_CUSTOMERS = [
    CustomerSeed("Bröllopspar Sandberg", "privat", 0.30, 0.90, 0.95),
    CustomerSeed("Företaget Konsult & Co", "foretag", 0.55, 0.65, 0.92),
    CustomerSeed("Skolan Norra", "kommun", 0.85, 0.50, 0.99),
    CustomerSeed("Föreningen Friluftsliv", "foretag", 0.65, 0.55, 0.88),
    CustomerSeed("Församlingen Sankta Klara", "foretag", 0.70, 0.60, 0.95),
]

CATERING_JOBS = [
    JobTemplate(
        "Bröllopscatering 80 personer",
        "3-rätters middag, kallt-bord vid mingel, dessertbuffé. Vegetariskt + glutenfritt-alternativ. Levereras till bygdegård kl 16.",
        45000, 21, "catering",
    ),
    JobTemplate(
        "Företagslunch — varje fredag i 3 månader",
        "Kontor 25 personer, du levererar varm lunch varje fredag i 12 veckor. Veckomeny som kund godkänner i förväg. Inkl. servering på plats.",
        38000, 90, "catering",
    ),
    JobTemplate(
        "Födelsedagsfest 30 personer",
        "Hemma hos kund, 50-årskalas. Buffé med 6 huvudrätter + 3 efterrätter. Du serverar och plockar undan, kunden vill umgås.",
        9500, 7, "catering",
    ),
    JobTemplate(
        "Skolavslutning - tårta + saft 120 elever",
        "Skola beställer enkla tårtor (sockerkaka m. krädig) + saft + frukt för 120 elever. Levereras 8.30 på avslutningsdagen.",
        4500, 5, "catering",
    ),
    JobTemplate(
        "Picknickkorgar för utflyktsföretag",
        "Friluftsföretag säljer dagsutflykter + picknick. 20 picknickkorgar/v under sommaren. Kallrätter + dryck + dessert. Engångsförpackningar.",
        18500, 14, "catering",
    ),
    JobTemplate(
        "Begravning - smörgåstårta 40 personer",
        "Församling beställer minnesstund. Smörgåstårta (lax + skinka), kaffe + tårta. Levereras 13.00 till församlingshemmet.",
        5800, 3, "catering",
    ),
    JobTemplate(
        "Konferens-frukost varje morgon i 3 dagar",
        "120 deltagare, 3 dagar. Du levererar frukostbuffé varje morgon kl 7.30, packar ihop kl 9.30. Inkl. specialkost (vegan, lakto-fri).",
        21500, 14, "catering",
    ),
]


# === Default-fallback (används om industry_key inte mappas) ===
#
# OBS: alla 10 fasta industrier ÄR mappade nedan. Default används bara
# för bakåtkompatibilitet med eventuella legacy-bolag utan industry_key.
# Beskrivningarna är ändå konkreta så även det här fallet håller
# pedagogisk kvalitet.

DEFAULT_CUSTOMERS = [
    CustomerSeed("Anna Persson", "privat", 0.50, 0.60, 0.93),
    CustomerSeed("Företaget X AB", "foretag", 0.65, 0.55, 0.88),
    CustomerSeed("Lokala kommunen", "kommun", 0.80, 0.45, 0.99),
]

DEFAULT_JOBS = [
    JobTemplate(
        "Tjänsteuppdrag mot mindre företag",
        "Lokalt företag behöver din tjänst, ungefär 1 veckas arbete. Tydlig leverans, rimlig deadline, ROT/RUT om relevant.",
        9500, 7, "default",
    ),
    JobTemplate(
        "Större projekt över 2 veckor",
        "Företag eller kommun beställer ett mer omfattande projekt. Förstudie, leverans, dokumentation, uppföljning.",
        24500, 14, "default",
    ),
]


# === Mappning · industry_key (från industries.py) → (customers, jobs) ===
#
# OBS: dict-nyckeln är `Industry.key`-värdet (samma som vi sparar på
# Company.industry_key), INTE display-label. Tidigare normaliserade
# vi `industry_label` vilket bröt 7 av 10 industrier eftersom labels
# är kosmetiska ("Snickare / hantverkare") medan keys är stabila
# ("snickare").

INDUSTRY_POOLS: dict[str, tuple[list[CustomerSeed], list[JobTemplate]]] = {
    "it_konsult": (IT_KONSULT_CUSTOMERS, IT_KONSULT_JOBS),
    "webbdesigner": (WEBBDESIGNER_CUSTOMERS, WEBBDESIGNER_JOBS),
    "snickare": (SNICKARE_CUSTOMERS, SNICKARE_JOBS),
    "rormokare": (RORMOKARE_CUSTOMERS, RORMOKARE_JOBS),
    "elektriker": (ELEKTRIKER_CUSTOMERS, ELEKTRIKER_JOBS),
    "frisor": (FRISOR_CUSTOMERS, FRISOR_JOBS),
    "coach": (COACH_CUSTOMERS, COACH_JOBS),
    "personal_trainer": (PERSONAL_TRAINER_CUSTOMERS, PERSONAL_TRAINER_JOBS),
    "fotograf": (FOTOGRAF_CUSTOMERS, FOTOGRAF_JOBS),
    "catering": (CATERING_CUSTOMERS, CATERING_JOBS),
}


# Legacy-aliasing · äldre kod (Monte Carlo, fixtures) använder breda
# kategori-strängar som "hantverk", "konsult", "it". De mappas till en
# rimlig industry-key från de 10 fasta industrierna så simuleringar
# fortsätter ge realistiska siffror.
_LEGACY_ALIAS: dict[str, str] = {
    "hantverk": "snickare",
    "it": "it_konsult",
    "it-tjanster": "it_konsult",
    "it-tjänster": "it_konsult",
    "konsult": "coach",
    "kreativ": "fotograf",
    "kreativ-tjanst": "fotograf",
    "kreativ-tjänst": "fotograf",
    "cafe": "catering",
    "café": "catering",
    "ehandel": "webbdesigner",
    "e-handel": "webbdesigner",
}


def industry_pool(
    industry_key: str | None,
) -> tuple[list[CustomerSeed], list[JobTemplate]]:
    """Hämta (customers, jobs) för en bransch baserat på industry_key.

    Tidigare lookup använde industry_label (display-namn) → 7/10
    industrier saknade mappning och föll till generiska "Standarduppdrag".
    Nu använder vi den stabila industry_key från industries.py + ett
    fåtal legacy-alias så Monte Carlo och äldre fixtures fortsätter
    fungera.
    """
    if not industry_key:
        return DEFAULT_CUSTOMERS, DEFAULT_JOBS
    key = industry_key.lower().strip().replace(" ", "-")
    if key in INDUSTRY_POOLS:
        return INDUSTRY_POOLS[key]
    if key in _LEGACY_ALIAS:
        return INDUSTRY_POOLS[_LEGACY_ALIAS[key]]
    # Fallback · matcha första segment (t.ex. 'it-konsult' → 'it')
    head = key.split("-")[0]
    if head in INDUSTRY_POOLS:
        return INDUSTRY_POOLS[head]
    if head in _LEGACY_ALIAS:
        return INDUSTRY_POOLS[_LEGACY_ALIAS[head]]
    return DEFAULT_CUSTOMERS, DEFAULT_JOBS
