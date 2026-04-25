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
