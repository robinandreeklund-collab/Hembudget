"""Systemmall-moduler som lärare kan klona och anpassa."""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


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
    for tpl in [FIRST_MONTH_TEMPLATE]:
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
