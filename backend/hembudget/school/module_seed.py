"""Systemmall-moduler som lärare kan klona och anpassa."""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


# Mall: "Kontoutdraget — vart tog pengarna vägen?"
ACCOUNT_STATEMENT_TEMPLATE = {
    "title": "Kontoutdraget — vart tog pengarna vägen?",
    "summary": "Importera ditt månadens kontoutdrag, sortera utgifterna i kategorier och se var pengarna faktiskt går.",
    "steps": [
        {
            "kind": "read",
            "title": "Bankens dagbok över dig",
            "content": (
                "Kontoutdraget är bankens lista över allt som hänt på ditt "
                "konto under en månad — varje insättning, varje köp, varje "
                "räkning. Det är facit. Många unga vuxna har aldrig läst ett "
                "i sin helhet.\n\n"
                "I Ekonomilabbet får du ett realistiskt PDF-utdrag varje "
                "månad. Den första uppgiften är att importera det och "
                "kategorisera varje rad så du faktiskt SER vart pengarna "
                "går — inte bara att de är slut."
            ),
        },
        {
            "kind": "task",
            "title": "Importera månadens kontoutdrag",
            "content": (
                "Gå till 'Dina dokument' i menyn. Där ligger ditt PDF-"
                "utdrag för den senaste månaden. Klicka 'Importera' så "
                "läser systemet in transaktionerna och visar dem på "
                "Transaktioner-sidan."
            ),
            "params": {"assignment_kind": "import_batch"},
        },
        {
            "kind": "read",
            "title": "Vad är en kategori?",
            "content": (
                "En kategori är en etikett som beskriver VAD pengarna gick "
                "till: 'Mat', 'Boende', 'Transport', 'Nöje' osv.\n\n"
                "När varje köp har en kategori kan du svara på frågor som:\n"
                "• Hur mycket går till mat per månad?\n"
                "• Är jag över- eller underbudget på nöje?\n"
                "• Vad är mina tre största utgifter?\n\n"
                "Utan kategorier syns bara att kontot är tomt i slutet."
            ),
        },
        {
            "kind": "task",
            "title": "Kategorisera alla transaktioner",
            "content": (
                "Gå till 'Transaktioner' och tilldela en kategori till varje "
                "rad som saknar. Använd dropdown-menyn. Är du osäker — "
                "tänk: vad SKULLE jag kalla detta köp om jag berättade för "
                "min förälder? Det räcker oftast."
            ),
            "params": {"assignment_kind": "categorize_all"},
        },
        {
            "kind": "quiz",
            "title": "Vart hör det här hemma?",
            "content": None,
            "params": {
                "question": "ICA Maxi 487 kr — vilken kategori passar bäst?",
                "options": [
                    "Boende",
                    "Mat & livsmedel",
                    "Transport",
                    "Nöje",
                ],
                "correct_index": 1,
                "explanation": (
                    "ICA är en livsmedelsbutik så det mesta du köper där "
                    "är mat. Ibland säljer de andra saker (kläder, "
                    "elektronik) men då hade beloppet sett annorlunda ut "
                    "och kunden får dela upp köpet manuellt."
                ),
            },
        },
        {
            "kind": "reflect",
            "title": "Vart gick mest pengar?",
            "content": (
                "Titta på dashboarden och se vilka kategorier som åt mest. "
                "Var det som du förväntade dig? Om inte — vad var skillnaden "
                "mot vad du trodde? Skriv 3-4 meningar."
            ),
            "params": {
                "rubric": [
                    {
                        "key": "specifik",
                        "name": "Specifik",
                        "levels": [
                            "Generellt",
                            "Refererar till en kategori",
                            "Refererar till specifika belopp",
                        ],
                    },
                    {
                        "key": "insikt",
                        "name": "Insikt",
                        "levels": [
                            "Beskriver",
                            "Drar slutsats",
                            "Föreslår förändring",
                        ],
                    },
                ],
            },
        },
    ],
}


# Mall: "Buffert — när livet smäller till"
BUFFER_TEMPLATE = {
    "title": "Buffert — när livet smäller till",
    "summary": "Bygg upp en sparbuffert som klarar ett oväntat slag — tandläkare, trasig mobil, sjukdagar.",
    "steps": [
        {
            "kind": "read",
            "title": "Vad är en buffert?",
            "content": (
                "En buffert är pengar du har sparat undan för det "
                "OVÄNTADE — inte för en semester eller en ny telefon, utan "
                "för när tandläkaren säger 4 200 kr eller diskmaskinen säger "
                "upp sig en tisdag i februari.\n\n"
                "Tumregeln: 2-3 månadslöner i buffert är ett bra mål för "
                "en vuxen. För dig som elev kan ett mindre mål (5-10 000 kr) "
                "räcka för att täcka det vanligaste oväntade."
            ),
        },
        {
            "kind": "quiz",
            "title": "Vad räknas som 'oväntat'?",
            "content": None,
            "params": {
                "question": "Vilka av dessa borde bufferten täcka?",
                "options": [
                    "Trasig laptop som du måste ha för skolan",
                    "Konsertbiljett du köper på ett impuls",
                    "Tandläkare-räkning på 3 800 kr",
                    "Resa du planerat i ett halvår",
                ],
                "correct_indices": [0, 2],
                "explanation": (
                    "Buffert = pengar för OVÄNTAT som du måste fixa NU. "
                    "Konserter och planerade resor är 'roligt' och borde "
                    "ha eget sparmål. Trasig dator + tandläkare är "
                    "klassisk buffert-användning."
                ),
            },
        },
        {
            "kind": "read",
            "title": "Räkna ut ditt eget buffert-mål",
            "content": (
                "Ett bra första buffert-mål är ungefär två månaders "
                "fasta utgifter (hyra, abonnemang, mat). \n\n"
                "Exempel: hyra 5 200 + mat 3 500 + abonnemang 700 = "
                "9 400 kr/månad. Två månader = 18 800 kr som mål.\n\n"
                "Vid 1 500 kr sparat per månad tar det ~13 månader. "
                "Vid 750 kr/månad → 25 månader. Bygg vad du kan, varje "
                "månad räknas."
            ),
        },
        {
            "kind": "task",
            "title": "Sätt ett konkret sparmål",
            "content": (
                "Räkna ut två månaders fasta utgifter och be din lärare "
                "skapa ett 'Spara X kr'-uppdrag åt dig med det beloppet. "
                "Om du redan har det — försök spara minst 10 % av "
                "nettolönen denna månad."
            ),
            "params": {"assignment_kind": "save_amount"},
        },
        {
            "kind": "reflect",
            "title": "Vad skulle gå sönder först hos dig?",
            "content": (
                "Tänk dig att du fick en oväntad räkning på 5 000 kr "
                "imorgon. Vad skulle den vara på? Hur skulle du betala "
                "den utan buffert? Vad skulle du behöva ge upp för att "
                "fixa den?"
            ),
            "params": {
                "rubric": [
                    {
                        "key": "konkret",
                        "name": "Konkret",
                        "levels": [
                            "Allmänt",
                            "Specifikt scenario",
                            "Specifikt scenario + plan",
                        ],
                    },
                    {
                        "key": "ärlighet",
                        "name": "Ärlighet",
                        "levels": ["Generellt", "Personligt"],
                    },
                ],
            },
        },
        {
            "kind": "read",
            "title": "Var ska bufferten ligga?",
            "content": (
                "Bufferten ska INTE ligga på lönekontot — då försvinner "
                "den. Och inte i fonder/aktier — där kan värdet vara nere "
                "när du behöver pengarna.\n\n"
                "Bästa platsen: ett separat sparkonto med fri uttag och "
                "minst lite ränta. Många banker har 'flexibelt sparkonto' "
                "med 1-3 % ränta. Inte mycket, men bättre än lönekontots "
                "0 %."
            ),
        },
    ],
}


# Mall: "Första bolånet — rörlig vs bunden"
MORTGAGE_TEMPLATE = {
    "title": "Första bolånet — rörlig vs bunden",
    "summary": "Förstå räntor, amortering och det stora valet rörlig vs bunden ränta — med riktiga historiska räntor.",
    "steps": [
        {
            "kind": "read",
            "title": "Vad är ett bolån?",
            "content": (
                "Ett bolån är pengar du lånar för att köpa en bostad. "
                "Banken tar pant i bostaden — kan du inte betala får de "
                "ta över den. I gengäld får du en låg ränta jämfört med "
                "andra lån (~3-5 % istället för 8-15 %).\n\n"
                "Två kostnader varje månad:\n"
                "• RÄNTA — det banken tar betalt för att låna ut pengar\n"
                "• AMORTERING — själva avbetalningen av lånet\n\n"
                "Bara amorteringen krymper skulden. Räntan är 'priset' du "
                "betalar för att ha lånet."
            ),
        },
        {
            "kind": "quiz",
            "title": "Vad gör amorteringen?",
            "content": None,
            "params": {
                "question": "Du har ett bolån på 2 000 000 kr. Räntan är "
                "4 % och amorteringen är 2 %. Hur mycket KRYMPER skulden "
                "första året?",
                "options": [
                    "120 000 kr (räntan + amorteringen)",
                    "80 000 kr (bara räntan)",
                    "40 000 kr (bara amorteringen)",
                    "Skulden krymper inte alls",
                ],
                "correct_index": 2,
                "explanation": (
                    "Bara amorteringen krymper själva skulden. 2 % av 2 mkr "
                    "= 40 000 kr. Räntan (80 000 kr/år) är priset för att HA "
                    "lånet — den minskar inte skulden. Många blandar ihop "
                    "detta första gången de tittar på en bolåneberäkning."
                ),
            },
        },
        {
            "kind": "read",
            "title": "Rörlig vs bunden ränta",
            "content": (
                "RÖRLIG ränta följer marknaden. Ändras typiskt var tredje "
                "månad. Kan gå upp eller ner snabbt. Lägre i snitt över "
                "lång tid.\n\n"
                "BUNDEN ränta låses fast i 1, 3 eller 5 år. Du vet exakt "
                "vad det kostar. Lite dyrare i utbyte mot förutsägbarhet.\n\n"
                "I lugna räntelägen (Riksbankens styrränta nära noll) är "
                "rörlig nästan alltid billigare. När räntan stiger snabbt "
                "(som 2022-2023) skyddar bunden mot chocken.\n\n"
                "Det är ett risk-vs-trygghet-val. Inget rätt svar — beror "
                "på din egen situation."
            ),
        },
        {
            "kind": "watch",
            "title": "Hur sätter Riksbanken styrräntan?",
            "content": (
                "Be din lärare om en 5-min-video från Riksbanken eller SVT "
                "som förklarar reporäntan och dess effekter på bolånen. "
                "(Lärare: lägg in en YouTube-länk i steg-params om du vill.)"
            ),
            "params": {"video_url": ""},
        },
        {
            "kind": "task",
            "title": "Gör ditt bolåne-val",
            "content": (
                "Be din lärare skapa ett 'Bolåne-beslut'-uppdrag åt dig. "
                "Du får då välja en historisk beslutsmånad (t.ex. juni 2022) "
                "och en horisont (typiskt 24-36 månader). Välj rörlig eller "
                "bunden. Systemet räknar sedan facit mot Riksbankens "
                "verkliga räntor och visar vilket val som blev billigast."
            ),
            "params": {"assignment_kind": "mortgage_decision"},
        },
        {
            "kind": "reflect",
            "title": "Hur tänkte du?",
            "content": (
                "Skriv 4-5 meningar om ditt val. Vad var det som vägde "
                "tyngst — kostnad, trygghet, magkänsla? Hur skulle du "
                "tänka om det var dina riktiga 2 miljoner?"
            ),
            "params": {
                "rubric": [
                    {
                        "key": "argumentation",
                        "name": "Argumentation",
                        "levels": [
                            "Refererar inte till valet",
                            "Argumenterar utifrån data",
                            "Argumenterar utifrån data + egen risk",
                        ],
                    },
                    {
                        "key": "perspektiv",
                        "name": "Perspektiv",
                        "levels": [
                            "Bara en tidshorisont",
                            "Funderar på flera scenarier",
                        ],
                    },
                ],
            },
        },
    ],
}


# Mall: "Kreditkort utan att gå under"
CREDITCARD_TEMPLATE = {
    "title": "Kreditkort utan att gå under",
    "summary": "Förstå hur kreditkort fungerar — och varför 'minimibetalning' är en fälla.",
    "steps": [
        {
            "kind": "read",
            "title": "Bra verktyg, dålig vana",
            "content": (
                "Ett kreditkort låter dig 'köpa nu, betala senare'. Du får "
                "en månadsfaktura som du betalar ~30 dagar efter köpet.\n\n"
                "Om du betalar HELA fakturan i tid är kreditkortet GRATIS. "
                "Du får dessutom kortförsäkring, ångerrätt och i vissa "
                "fall bonuspoäng.\n\n"
                "Om du betalar bara MINIMI-beloppet (oftast 3-5 % av "
                "skulden) börjar räntan gnaga. Och bolåneräntan (4 %) ser "
                "ut som en gratis-överraskning jämfört med kreditkort:s "
                "18-25 %."
            ),
        },
        {
            "kind": "quiz",
            "title": "Vad kostar minimi-betalningen?",
            "content": None,
            "params": {
                "question": "Du har 6 000 kr på ditt kreditkort. Räntan är "
                "20 % per år. Du betalar bara minimi (300 kr/månad). Hur "
                "lång tid tar det att betala av — och hur mycket har du "
                "betalat totalt?",
                "options": [
                    "20 månader, 6 000 kr (ingen ränta)",
                    "24 månader, 7 200 kr",
                    "28 månader, ~8 350 kr",
                    "Det betalas aldrig av om man bara betalar minimi",
                ],
                "correct_index": 2,
                "explanation": (
                    "Räntan på 100 kr/månad (20%/12 av 6 000) äter upp en "
                    "stor del av minibetalningen. Det tar ~28 månader att "
                    "bli skuldfri och du har då betalat ~8 350 kr för en "
                    "skuld på 6 000 kr. Effektiv kostnad: 2 350 kr i ränta."
                ),
            },
        },
        {
            "kind": "read",
            "title": "Effektiv ränta vs nominell ränta",
            "content": (
                "Den NOMINELLA räntan är den 'ren' procentsiffran banken "
                "marknadsför ('19,9 %'). Den EFFEKTIVA räntan inkluderar "
                "alla avgifter (uppläggning, faktura, autogiro) och säger "
                "vad lånet egentligen kostar.\n\n"
                "Lagstadgat ska den effektiva räntan ALLTID anges för "
                "konsumentkrediter. Titta efter den siffran — inte den "
                "stora marknadsförda."
            ),
        },
        {
            "kind": "task",
            "title": "Granska din kortfaktura",
            "content": (
                "Importera månadens kreditkortsfaktura via 'Dina dokument' "
                "om du inte redan gjort det. Titta på 'Saldo att betala' "
                "och 'Minimum att betala'. Räkna ut hur lång tid det skulle "
                "ta att betala av om du bara betalar minimi varje månad."
            ),
            "params": {"assignment_kind": "import_batch"},
        },
        {
            "kind": "quiz",
            "title": "Vilken kortvana är säkrast?",
            "content": None,
            "params": {
                "question": "Vilken vana skyddar dig från att gräva ner dig "
                "i kortskuld?",
                "options": [
                    "Använd kortet bara för stora köp",
                    "Sätt autogiro på HELA fakturan varje månad",
                    "Betala minimi varje månad — det räcker",
                    "Använd flera kort så fakturorna blir mindre var och en",
                ],
                "correct_index": 1,
                "explanation": (
                    "Autogiro på hela fakturan = du kan ALDRIG glömma "
                    "betala, ALDRIG råka ut för ränta, men får ändå "
                    "fördelarna (försäkring, ångerrätt). Tröskeln blir "
                    "'kan jag betala av detta nästa lön?' — inte "
                    "'minimi räcker'."
                ),
            },
        },
        {
            "kind": "reflect",
            "title": "Skulle du vilja ha kreditkort?",
            "content": (
                "Skulle du skaffa ett kreditkort när du är 18? Varför / "
                "varför inte? Om ja — vilka regler skulle du sätta för "
                "dig själv?"
            ),
            "params": {
                "rubric": [
                    {
                        "key": "argument",
                        "name": "Argument",
                        "levels": [
                            "Bara åsikt",
                            "Argument med skäl",
                            "Argument med konsekvensanalys",
                        ],
                    },
                ],
            },
        },
    ],
}


# Mall: "Att börja spara på riktigt"
SAVING_TEMPLATE = {
    "title": "Att börja spara på riktigt",
    "summary": "Från sparkonto till indexfond — och varför ränta-på-ränta är världens viktigaste insikt.",
    "steps": [
        {
            "kind": "read",
            "title": "Tre nivåer av sparande",
            "content": (
                "Inte allt sparande är samma sak. Tre nivåer:\n\n"
                "1. SPARKONTO (kort sikt) — bufferten. Pengar du måste "
                "kunna ta ut imorgon. ~1-3 % ränta. Säkert.\n\n"
                "2. INDEXFOND (lång sikt, 5+ år) — pengar du inte behöver "
                "på flera år. ~7 % årlig avkastning historiskt. Volatilt "
                "år för år men stabilt över tid.\n\n"
                "3. ENSKILDA AKTIER (lång sikt, hög risk) — bara med "
                "pengar du har råd att förlora. Kan ge 30 % på ett år, "
                "kan tappa 50 %.\n\n"
                "Bygg från botten: först bufferten, sedan fondsparande, "
                "sist (om någonsin) enskilda aktier."
            ),
        },
        {
            "kind": "read",
            "title": "Ränta-på-ränta — världens viktigaste insikt",
            "content": (
                "Ränta-på-ränta = du tjänar ränta INTE BARA på dina "
                "insatta pengar, utan också på den ränta som tidigare "
                "år gett dig.\n\n"
                "Exempel: 1 000 kr/mån i 30 år vid 7 % årlig avkastning "
                "blir ~1,17 MILJONER kr. Bara 360 000 är dina insatta "
                "pengar. Resten — 810 000 — är ränta på ränta.\n\n"
                "Samma tusenlapp/månad i bara 10 år (= 120 000 insatt) "
                "blir bara ~173 000. Tiden är allt. Börja tidigt även om "
                "beloppet är litet."
            ),
        },
        {
            "kind": "quiz",
            "title": "Vilket exempel ger mest pengar?",
            "content": None,
            "params": {
                "question": "Tre personer sparar 500 kr/mån vid 7 % "
                "avkastning. Vem har MEST pengar vid 65?",
                "options": [
                    "Anna börjar vid 20, sparar 10 år, slutar (60 000 insatt)",
                    "Bahar börjar vid 30, sparar i 35 år (210 000 insatt)",
                    "Carl börjar vid 40, sparar i 25 år (150 000 insatt)",
                ],
                "correct_index": 0,
                "explanation": (
                    "Trick-fråga! Anna slutar vid 30 men låter pengarna "
                    "växa i 35 år vid 7 % → ~700 000 kr. Bahar har 210 000 "
                    "insatta i 35 år → ~860 000 kr. Carl har bara 25 år "
                    "→ ~410 000. Anna SLÅR Carl trots att hon satt in "
                    "MINDRE. Tid > belopp för långsiktigt sparande."
                ),
            },
        },
        {
            "kind": "read",
            "title": "Indexfond vs aktivt förvaltad fond",
            "content": (
                "INDEXFOND följer marknaden mekaniskt (köper allt). Avgift "
                "0,2-0,4 %/år. Slår nästan alltid aktiva fonder över 10+ år.\n\n"
                "AKTIV FOND har en förvaltare som väljer aktier. Avgift "
                "1-2 %/år. 80-90 % av aktiva fonder presterar SÄMRE än "
                "index över lång tid (efter avgifter).\n\n"
                "1 % skillnad i avgift låter inte mycket. På 30 år är det "
                "~30 % MINDRE pengar i din ficka. Indexfond är default-"
                "valet för 99 % av sparare."
            ),
        },
        {
            "kind": "task",
            "title": "Sätt ett långsiktigt sparmål",
            "content": (
                "Be din lärare skapa ett 'Spara X kr/mån'-uppdrag åt dig. "
                "Den här gången: tänk pension, inte semester. Hur mycket "
                "kan du tänka dig att spara om DU FICK välja, inte vad "
                "Konsumentverket säger?"
            ),
            "params": {"assignment_kind": "save_amount"},
        },
        {
            "kind": "reflect",
            "title": "Vilket är din 30-års-jag tacksam för?",
            "content": (
                "Tänk dig att du är 50 år. Vad skulle du önska att din "
                "20-åriga jag hade gjort med pengarna? Vad tror du att "
                "DU kommer ångra? Skriv ärligt."
            ),
            "params": {
                "rubric": [
                    {
                        "key": "tidshorisont",
                        "name": "Tidshorisont",
                        "levels": [
                            "Bara nuet",
                            "Refererar till framtiden",
                            "Kopplar nuet till framtid + handling",
                        ],
                    },
                ],
            },
        },
    ],
}


# Mall: "Familjeekonomi — när två delar"
FAMILY_TEMPLATE = {
    "title": "Familjeekonomi — när två delar",
    "summary": "Sambo eller gift? Egen ekonomi eller gemensam? Hur fördelar man räkningarna när inkomsterna är olika?",
    "steps": [
        {
            "kind": "read",
            "title": "Tre modeller för parens ekonomi",
            "content": (
                "Det finns ingen 'rätt' modell — bara olika kompromisser:\n\n"
                "1. ALLT GEMENSAMT — ett konto, en pott. Enklast om "
                "inkomsterna är lika och förtroendet stort.\n\n"
                "2. PROPORTIONELLT — tjänar du 60 % av hushållet, betalar "
                "du 60 % av räkningarna. Egna konton för 'eget'.\n\n"
                "3. ALLT SEPARAT, BARA NÅGRA GEMENSAMMA — eget allt, men "
                "ett gemensamt 'hyrkonto' för fasta utgifter.\n\n"
                "Modell 2 är vanligast i Sverige och brukar upplevas som "
                "rättvis även när inkomsterna är olika."
            ),
        },
        {
            "kind": "read",
            "title": "Vad räknas som 'gemensamt'?",
            "content": (
                "Klassiska gemensamma utgifter:\n"
                "• Hyra/bolån\n"
                "• El, vatten, bredband\n"
                "• Mat (oftast)\n"
                "• Hemförsäkring\n"
                "• Underhåll, möbler\n\n"
                "Klassiska personliga utgifter:\n"
                "• Kläder, hygien\n"
                "• Egna prenumerationer (Spotify, gym)\n"
                "• Hobbyer\n"
                "• Restauranger med vänner\n\n"
                "Mat är ofta gränsfall — vissa par delar 50/50, andra "
                "räknar mat som gemensam-pott. Båda funkar."
            ),
        },
        {
            "kind": "quiz",
            "title": "Räkneexempel — proportionell modell",
            "content": None,
            "params": {
                "question": "Anna tjänar 30 000 kr/mån, Bahar 20 000. "
                "Hyran är 12 000. I proportionell modell — hur mycket ska "
                "Anna respektive Bahar betala?",
                "options": [
                    "6 000 kr var (50/50)",
                    "Anna 7 200, Bahar 4 800",
                    "Anna 8 000, Bahar 4 000",
                    "Anna 10 000, Bahar 2 000",
                ],
                "correct_index": 1,
                "explanation": (
                    "Proportionellt: Anna har 30/(30+20) = 60 % av "
                    "hushållets inkomst. 60 % av 12 000 = 7 200. "
                    "Bahar betalar resten (4 800). Båda lägger SAMMA "
                    "andel av sin egen lön på hyran (24 % av sin lön)."
                ),
            },
        },
        {
            "kind": "task",
            "title": "Bygg en gemensam budget",
            "content": (
                "Be din lärare placera dig i en familj med en kompis. Då "
                "delar ni en simulerad ekonomi — gemensamt konto, "
                "gemensam budget, gemensamma räkningar. Diskutera och "
                "kom överens om hur ni vill fördela kostnaderna."
            ),
            "params": {"assignment_kind": "set_budget"},
        },
        {
            "kind": "reflect",
            "title": "Vad är viktigast — rättvist eller enkelt?",
            "content": (
                "I parets ekonomi finns ofta en spänning mellan att vara "
                "RÄTTVIS (proportionellt) och att vara ENKEL (50/50 eller "
                "allt gemensamt). Vad värderar du högst? Skulle du vilja "
                "att alla regler var skrivna i förväg, eller fungerar "
                "magkänsla?"
            ),
            "params": {
                "rubric": [
                    {
                        "key": "egen-ståndpunkt",
                        "name": "Egen ståndpunkt",
                        "levels": [
                            "Refererar bara",
                            "Egen åsikt",
                            "Egen åsikt med skäl",
                        ],
                    },
                    {
                        "key": "perspektiv",
                        "name": "Perspektiv",
                        "levels": [
                            "En sida",
                            "Båda sidor",
                            "Båda sidor + kompromiss",
                        ],
                    },
                ],
            },
        },
        {
            "kind": "read",
            "title": "Vad händer om man separerar?",
            "content": (
                "Sambolagen: gemensamt köpt bostad och inbo (möbler, "
                "hushållsmaskiner) delas 50/50 vid separation, även om en "
                "betalat mer. Allt ANNAT (sparande, bil, kläder) är ditt "
                "om du köpt själv.\n\n"
                "Vill man ha annat — skriv samboavtal. Banalt? Ja. "
                "Pinsamt? Ja. Smart? Ja, om en av er köpt bostaden själv "
                "innan ni flyttade ihop.\n\n"
                "Gift: äktenskapsförord fungerar likadant — utan det blir "
                "allt giftorättsgods och delas vid skilsmässa."
            ),
        },
    ],
}


# Mall: "Din första månad"
FIRST_MONTH_TEMPLATE = {
    "title": "Din första månad",
    "summary": "En introduktion till Ekonomilabbet — lön, skatt, budget och första dokumenten.",
    "steps": [
        {
            "kind": "read",
            "title": "Välkommen!",
            "content": (
                "I Ekonomilabbet får du öva på att hantera ekonomi precis som "
                "när du flyttat hemifrån. Du har ett simulerat yrke, en lön, "
                "en bostad och räkningar att betala. Allt är fiktivt, men "
                "siffrorna är realistiska (baserade på svensk lönestatistik "
                "och Konsumentverkets 2026-siffror).\n\n"
                "Denna modul tar dig igenom grunderna: vad är en lönespec, "
                "hur fungerar skatten, och hur sätter du en budget som "
                "fungerar för just din situation."
            ),
        },
        {
            "kind": "reflect",
            "title": "Vad tänker du om pengar?",
            "content": (
                "Innan vi börjar — skriv några meningar om hur du ser på "
                "pengar idag. Är det stressande? Roligt? Något du inte "
                "tänker på? Det finns inget rätt eller fel."
            ),
            "params": {
                "rubric": [
                    {
                        "key": "depth",
                        "name": "Djup",
                        "levels": [
                            "Kort och ytligt",
                            "Utvecklat resonemang",
                            "Nyanserat och personligt",
                        ],
                    },
                ],
            },
        },
        {
            "kind": "quiz",
            "title": "Snabbkoll: vad är bruttolön?",
            "content": None,
            "params": {
                "question": "Vilket påstående stämmer?",
                "options": [
                    "Bruttolön är det du får i handen efter skatt",
                    "Bruttolön är det arbetsgivaren betalar innan skatt dras",
                    "Bruttolön är samma som nettolön",
                ],
                "correct_index": 1,
                "explanation": (
                    "Bruttolön = lön innan skatt. Skatten dras av direkt av "
                    "arbetsgivaren och skickas till Skatteverket. "
                    "Det som landar på ditt konto är nettolönen."
                ),
            },
        },
        {
            "kind": "quiz",
            "title": "Vilka syften har skatten?",
            "content": None,
            "params": {
                "question": "Vad används skattepengarna till? (flera rätt)",
                "options": [
                    "Skola och sjukvård",
                    "Dina privata semestrar",
                    "Vägar, polis och försvar",
                    "Pension och sjukersättning",
                ],
                "correct_indices": [0, 2, 3],
                "explanation": (
                    "Skatt finansierar gemensam välfärd — skola, vård, "
                    "pensioner, infrastruktur, rättsväsen. Den går INTE "
                    "till privat konsumtion."
                ),
            },
        },
        {
            "kind": "read",
            "title": "Så fungerar en budget",
            "content": (
                "En budget är en plan för månaden: vad du tjänar, vad du "
                "måste betala (hyra, el, mat), och vad som blir kvar till "
                "sparande och nöjen.\n\n"
                "Viktiga regler:\n"
                "• Utgifter får inte vara större än inkomsten\n"
                "• Fasta kostnader (hyra, försäkringar) ska räknas först\n"
                "• Sparande borde behandlas som en 'räkning' till dig själv\n"
                "• Ha alltid en buffert — oväntade saker händer"
            ),
        },
        {
            "kind": "task",
            "title": "Sätt din månadsbudget",
            "content": (
                "Gå till 'Budget' och fyll i dina kategorier. Du kan använda "
                "Konsumentverkets förslag som utgångspunkt och sedan justera."
            ),
        },
        {
            "kind": "reflect",
            "title": "Avslutande reflektion",
            "content": (
                "Nu har du sett din lön, förstått skatten och satt en "
                "budget. Vad förvånade dig mest? Vad känns svårast att "
                "planera för?"
            ),
            "params": {
                "rubric": [
                    {
                        "key": "insight",
                        "name": "Insikt",
                        "levels": [
                            "Beskriver fakta",
                            "Visar eftertanke",
                            "Kopplar till eget liv",
                        ],
                    },
                    {
                        "key": "honesty",
                        "name": "Ärlighet",
                        "levels": [
                            "Generellt",
                            "Personligt",
                        ],
                    },
                ],
            },
        },
    ],
}


SYSTEM_TOUR_TEMPLATE = {
    "title": "Lär känna systemet",
    "summary": (
        "Praktisk genomgång: använd Överföringar och Kommande räkningar "
        "för att få full kontroll på pengaflödet. Spårning sker live mot "
        "din huvudbok."
    ),
    "steps": [
        {
            "kind": "read",
            "title": "Vad är en överföring?",
            "content": (
                "En överföring är när du flyttar pengar mellan dina egna "
                "konton — t.ex. från lönekontot till sparkontot. Det är "
                "INTE en utgift eller en inkomst, det är bara att pengarna "
                "rör sig.\n\n"
                "Om en överföring råkar bokas som en vanlig transaktion "
                "kommer den dyka upp dubbelt i statistiken: först som en "
                "'utgift' från det ena kontot, sen som en 'inkomst' till "
                "det andra. Lösningen är att länka ihop de två raderna."
            ),
        },
        {
            "kind": "quiz",
            "title": "Snabbkoll: överföringar",
            "content": None,
            "params": {
                "question": (
                    "Du flyttar 2 000 kr från lönekonto till sparkonto. "
                    "Hur ska det räknas i din månadsbudget?"
                ),
                "options": [
                    "Som en utgift på 2 000 kr",
                    "Som en överföring (varken utgift eller inkomst)",
                    "Som ett sparande på 2 000 kr i kategorin 'Mat'",
                ],
                "correct_index": 1,
                "explanation": (
                    "Pengarna lämnar inte din ekonomi — de bara byter "
                    "konto. Markera det som överföring så det inte stör "
                    "kategori-statistiken."
                ),
            },
        },
        {
            "kind": "task",
            "title": "Länka två överföringar",
            "content": (
                "Gå till sidan 'Överföringar' i menyn. Hitta två "
                "transaktioner som hör ihop (samma belopp, motsatta "
                "tecken, nära i tid) och länka dem som en överföring. "
                "Steget markeras automatiskt som klart när du har minst "
                "två länkade överföringar i din huvudbok."
            ),
            "params": {
                "assignment_kind": "link_transfer",
                "target_count": 2,
            },
        },
        {
            "kind": "read",
            "title": "Vad är 'kommande räkningar'?",
            "content": (
                "Räkningar du vet kommer men ännu inte har betalats — "
                "elen, hyran, försäkringen. Att lägga in dem som "
                "'kommande' låter dig se cashflow:n in i framtiden så "
                "du inte blir överraskad.\n\n"
                "Du hittar funktionen under 'Kommande' i menyn. Bra "
                "vana: lägg in alla återkommande räkningar en gång, "
                "markera 'Återkommande månad', så fylls de på "
                "automatiskt."
            ),
        },
        {
            "kind": "task",
            "title": "Lägg till tre kommande räkningar",
            "content": (
                "Tänk igenom vilka återkommande räkningar du har. "
                "Lägg till minst tre i 'Kommande' — t.ex. hyra, "
                "telefon, streamingtjänst. Steget markeras klart "
                "automatiskt när du har tre eller fler i huvudboken."
            ),
            "params": {
                "assignment_kind": "add_upcoming",
                "target_count": 3,
            },
        },
        {
            "kind": "reflect",
            "title": "Vad upptäckte du?",
            "content": (
                "När du gick igenom dina kommande räkningar — dök det "
                "upp några du glömt eller inte tänkt på? Vad lärde det "
                "dig om dina månadskostnader?"
            ),
            "params": {
                "rubric": [
                    {
                        "key": "insight",
                        "name": "Insikt",
                        "levels": [
                            "Beskriver fakta",
                            "Identifierar mönster",
                            "Kopplar till framtida planering",
                        ],
                    },
                ],
            },
        },
    ],
}


STOCKS_TEMPLATE = {
    "title": "Aktier — komma igång",
    "summary": (
        "Från första ISK-kontot till en diversifierad portfölj. Steg-för-"
        "steg-modul som lär dig riskspridning, courtage och hur "
        "aktiehandel fungerar i praktiken."
    ),
    "steps": [
        {
            "kind": "read",
            "title": "Vad är en aktie?",
            "content": (
                "En aktie är en del av ett företag. När du köper en aktie "
                "blir du delägare i företaget — om de går bra ökar värdet, "
                "om de går dåligt minskar det. Värdet på en aktie bestäms "
                "av utbud och efterfrågan på börsen.\n\n"
                "Tänk på det så här: Volvo har ungefär 2 miljarder aktier. "
                "Om du köper 10 stycken äger du 0,000 000 5 % av Volvo. "
                "Du har också rätt till en del av vinsten — det kallas "
                "utdelning."
            ),
        },
        {
            "kind": "task",
            "title": "Skapa ditt första aktiekonto (ISK)",
            "content": (
                "Gå till 'Konton' i menyn och skapa ett nytt konto med "
                "typen 'ISK'. Det är ett särskilt konto för aktier och "
                "fonder där skatten är schablonmässig — du betalar en "
                "liten procent på värdet varje år istället för "
                "kapitalvinstskatt på varje sälj."
            ),
            "params": {
                "assignment_kind": "stock_open_account",
                "target_count": 1,
            },
        },
        {
            "kind": "task",
            "title": "Flytta 10 000 kr till ditt aktiekonto",
            "content": (
                "Gå till 'Överföringar' och klicka 'Ny överföring'. "
                "Flytta 10 000 kr från ditt sparkonto till ditt nya "
                "ISK. Det kallas att 'fonda kontot' — pengarna behöver "
                "ligga där för att du ska kunna handla."
            ),
            "params": {
                "assignment_kind": "make_transfer",
                "target_count": 1,
                "min_amount": 1000,
                "to_account_kind": "isk",
            },
        },
        {
            "kind": "read",
            "title": "Riskspridning — varför du inte ska lägga alla ägg i en korg",
            "content": (
                "Om du satsar alla pengar på en aktie och företaget går "
                "i konkurs — då är allt borta. Lösningen är "
                "diversifiering: sprid pengarna mellan flera olika "
                "företag i flera olika branscher.\n\n"
                "På Stockholmsbörsen finns t.ex. Industri (Volvo, "
                "Atlas Copco), Bank (SEB, Swedbank), Telecom (Telia, "
                "Ericsson), Hälsa (AstraZeneca), Konsument (H&M), "
                "och fler. När en bransch går dåligt går oftast en "
                "annan bra — det jämnar ut svängningarna."
            ),
        },
        {
            "kind": "task",
            "title": "Köp 5 aktier från minst 3 olika sektorer",
            "content": (
                "Gå till 'Aktier' i menyn → fliken 'Marknad'. Välj 5 "
                "aktier som passar dig — men minst 3 olika sektorer. "
                "Lägg max ~2 000 kr per aktie så du hinner sprida "
                "innan likviden tar slut. Skriv en kort motivering "
                "för varje köp."
            ),
            "params": {
                "assignment_kind": "stock_diversify",
                "min_holdings": 5,
                "min_sectors": 3,
            },
        },
        {
            "kind": "read",
            "title": "Courtage — den dolda kostnaden",
            "content": (
                "Varje gång du köper eller säljer aktier tar mäklaren ut "
                "en avgift. Vi använder Avanza Mini-courtage: minst 1 kr "
                "per affär, eller 0,25 % av beloppet — det som är högst.\n\n"
                "Räkneexempel: köper du för 100 kr betalar du 1 kr "
                "(minimi). Köper du för 4 000 kr betalar du 10 kr "
                "(0,25 %). Vid 100 köp om året på 1 000 kr blir det "
                "100 kr i avgifter — pengar som äter upp vinsten. "
                "Stora och få affärer är billigare än många små."
            ),
        },
        {
            "kind": "quiz",
            "title": "Snabbkoll på det du lärt dig",
            "content": None,
            "params": {
                "question": (
                    "Du köper 20 Volvo-aktier för 200 kr/styck. Hur "
                    "mycket courtage betalar du (Mini-modell)?"
                ),
                "options": [
                    "1 kr",
                    "10 kr",
                    "20 kr",
                    "100 kr",
                ],
                "correct_index": 1,
                "explanation": (
                    "20 × 200 = 4 000 kr × 0,25 % = 10 kr. Det är "
                    "över minimumet på 1 kr, så procenten gäller."
                ),
            },
        },
        {
            "kind": "reflect",
            "title": "Var det svårt att välja?",
            "content": (
                "När du valde dina 5 aktier — vad styrde dig? Var det "
                "namn du kände igen, sektorer du tror på, eller "
                "siffrorna i dagens kurs? Vad lärde du dig om "
                "diversifiering?"
            ),
            "params": {
                "rubric": [
                    {
                        "key": "risk_understanding",
                        "name": "Förståelse för risk",
                        "levels": [
                            "Nämner inte risk",
                            "Pratar om en risk",
                            "Förklarar varför spridning minskar risken",
                        ],
                    },
                    {
                        "key": "courtage_understanding",
                        "name": "Förståelse för courtage",
                        "levels": [
                            "Nämner inte avgifter",
                            "Vet att courtage finns",
                            "Räknar med courtage i sina beslut",
                        ],
                    },
                    {
                        "key": "own_reflection",
                        "name": "Egen reflektion",
                        "levels": [
                            "Återger fakta",
                            "Bedömer sina egna val",
                            "Drar pedagogiska slutsatser",
                        ],
                    },
                ],
            },
        },
    ],
}


def seed_system_modules(master_session) -> int:
    """Lägg in systemmoduler (teacher_id=NULL + is_template=True) om saknas.
    Identifieras via unikt title+teacher_id=NULL — enklare än ett key-fält.
    """
    from .models import Module, ModuleStep
    existing = {
        m.title for m in master_session.query(Module).filter(
            Module.teacher_id.is_(None),
            Module.is_template.is_(True),
        ).all()
    }
    n = 0
    for tpl in [
        FIRST_MONTH_TEMPLATE,
        ACCOUNT_STATEMENT_TEMPLATE,
        BUFFER_TEMPLATE,
        MORTGAGE_TEMPLATE,
        CREDITCARD_TEMPLATE,
        SAVING_TEMPLATE,
        FAMILY_TEMPLATE,
        SYSTEM_TOUR_TEMPLATE,
        STOCKS_TEMPLATE,
    ]:
        if tpl["title"] in existing:
            continue
        m = Module(
            teacher_id=None,
            title=tpl["title"],
            summary=tpl.get("summary"),
            is_template=True,
            sort_order=0,
        )
        master_session.add(m)
        master_session.flush()
        for i, st in enumerate(tpl["steps"]):
            master_session.add(ModuleStep(
                module_id=m.id,
                sort_order=(i + 1) * 10,
                kind=st["kind"],
                title=st["title"],
                content=st.get("content"),
                params=st.get("params"),
            ))
        n += 1
    return n
