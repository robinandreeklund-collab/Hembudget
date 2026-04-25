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
    for tpl in [FIRST_MONTH_TEMPLATE, ACCOUNT_STATEMENT_TEMPLATE]:
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
