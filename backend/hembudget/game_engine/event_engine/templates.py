"""Event Template-pool 1.0 · ~30 svenska liv-händelser med realistiska
kostnader och försäkrings-koppling.

Spec: dev/game-motor/04-event-engine.md (Event-typer A-D)

Varje template har:
- `frequency_per_year` · genomsnitt antal/år för en typisk vuxen
- `cost_range` · (min, max) kr (negativt = inkomst, t.ex. bonus)
- `pentagon_unmitigated/mitigated` · per-axel-effekt
- `mitigations` · lista av (insurance_kind, multiplier, label)
- `actor_route` · ev. djuplänk till relevant aktör (Arbetsförmedlingen,
  Skatteverket osv.)
- `echo_trigger` · valfri Echo-fråga som triggas när eleven öppnar mailet

Källor: SCB försäkringsdata 2024, Svensk Försäkring brancschstatistik,
Konsumentverket-räkningar.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional


EventKind = Literal[
    "unexpected", "opportunity", "income", "lifecycle", "career",
]

# Insurance-kinds matchar `db.models.InsurancePolicy.kind`
InsuranceKind = Literal[
    "hem", "olycksfall", "liv", "barnforsakring",
    "bostadsrattsforsakring", "bilforsakring", "djur",
    "tandvard", "inkomstforsakring", "ovrig",
]


@dataclass(frozen=True)
class PentagonImpact:
    """Per-axel-effekt på pentagonen (kan vara negativ eller positiv)."""

    economy: int = 0
    safety: int = 0
    health: int = 0
    social: int = 0
    leisure: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "economy": self.economy,
            "safety": self.safety,
            "health": self.health,
            "social": self.social,
            "leisure": self.leisure,
        }


@dataclass(frozen=True)
class Mitigation:
    """En försäkring (eller annan situation) som mildrar event-effekten.

    `cost_multiplier` appliceras på event-kostnaden (1.0 = ingen mildring,
    0.0 = helt täckt). `label` visas i mail-bodyn så eleven förstår vad
    som hände.
    """

    insurance_kind: Optional[InsuranceKind]
    cost_multiplier: float
    label: str
    # Om mitigation kräver mer än bara policy-existens (t.ex. "buffer ≥ 5000
    # kr"), kan vi i framtiden lägga till en check-funktion. För nu räcker
    # insurance_kind eller None (= "savings_buffer"-fallback hanterad i
    # mitigation.py).
    requires_savings_buffer_min: int = 0


@dataclass(frozen=True)
class EventTemplate:
    """En oväntad händelse som kan trigga för en elev under en spelmånad."""

    key: str
    display: str
    description: str
    kind: EventKind

    # Trigger-logik
    frequency_per_year: float          # Förväntat antal/år
    age_range: tuple[int, int] = (16, 99)
    family_status_filter: tuple[str, ...] = ()  # Tomt = alla statusar

    # Ekonomisk effekt
    cost_range: tuple[int, int] = (0, 0)  # SEK (negativ = inkomst)

    # Pentagon-effekt
    pentagon_unmitigated: PentagonImpact = field(
        default_factory=PentagonImpact,
    )
    pentagon_mitigated: Optional[PentagonImpact] = None

    # Försäkrings-mildring (första matchning vinner)
    mitigations: tuple[Mitigation, ...] = ()

    # UI / coaching
    actor_route: Optional[str] = None
    echo_trigger: Optional[str] = None
    sender: str = "Postlådan"
    sender_short: str = "EVT"
    sender_kind: str = "other"

    # Aktiv = får triggas av roller. False = endast manuell injektion.
    active: bool = True


# === POOL · 30 svenska 2026-händelser ===

EVENT_TEMPLATES: list[EventTemplate] = [
    # --- HÄLSA & TANDVÅRD ---
    EventTemplate(
        key="tandlakar_kontroll",
        display="Folktandvården · karieskontroll",
        description=(
            "Folktandvården kallade till halvårskontroll. Snabb "
            "undersökning med röntgen vid behov."
        ),
        kind="unexpected",
        frequency_per_year=0.5,
        # Realistisk prislista 2026 · enbart kontroll (inte lagning).
        # Tidigare 3000-6500 var orealistiskt högt — det var närmare
        # 'kontroll + 2 lagningar' men eventet säger bara 'kontroll'.
        # Hänvisar nu till lagning som SEPARAT event (tandlakar_karies
        # nedan).
        cost_range=(700, 1100),
        pentagon_unmitigated=PentagonImpact(economy=-2, health=-1),
        pentagon_mitigated=PentagonImpact(economy=0, health=+1),
        mitigations=(
            # Frisktandvård täcker 100 % (egenavgift 0 kr)
            Mitigation("frisktandvard", 0.0, "Frisktandvård · ingen kostnad"),
            # Äldre 'tandvard'-kind kvar för bakåtkompat
            Mitigation("tandvard", 0.10, "Tandvårdsförsäkring · egenavgift"),
        ),
        sender="Folktandvården",
        sender_short="FTV",
        sender_kind="other",
        echo_trigger="Hade frisktandvård gjort detta gratis?",
    ),
    EventTemplate(
        key="tandlakar_karies",
        display="Folktandvården · karies-lagning",
        description=(
            "Vid kontrollen hittades ett hål som behöver lagas. "
            "Lagning med komposit · 1 besök."
        ),
        kind="unexpected",
        frequency_per_year=0.20,
        cost_range=(1800, 3200),
        pentagon_unmitigated=PentagonImpact(economy=-4, health=-1),
        pentagon_mitigated=PentagonImpact(economy=0, health=+1),
        mitigations=(
            Mitigation("frisktandvard", 0.0, "Frisktandvård · ingen kostnad"),
            Mitigation("tandvard", 0.20, "Tandvårdsförsäkring · egenavgift"),
        ),
        sender="Folktandvården",
        sender_short="FTV",
        sender_kind="other",
        echo_trigger="Hade frisktandvård gjort detta gratis?",
    ),
    EventTemplate(
        key="vardcentral_besok",
        display="Vårdcentralen · läkarbesök",
        description="Akut hälsoärende — receptkostnad och patientavgift.",
        kind="unexpected",
        frequency_per_year=1.2,
        cost_range=(250, 1300),
        pentagon_unmitigated=PentagonImpact(economy=-2, health=-2),
        sender="1177 Vårdguiden",
        sender_short="1177",
    ),
    EventTemplate(
        key="glasogon_byte",
        display="Optiker · nya glasögon",
        description="Synen har försämrats — bågar + glas behövs.",
        kind="lifecycle",
        frequency_per_year=0.25,
        age_range=(25, 99),
        cost_range=(2200, 5800),
        pentagon_unmitigated=PentagonImpact(economy=-5),
        pentagon_mitigated=PentagonImpact(economy=-1),
        mitigations=(
            Mitigation("ovrig", 0.30, "Friskvårdsbidrag täcker delar"),
        ),
        sender="Synsam",
        sender_short="OPT",
    ),

    # --- BOENDE & HEMMET ---
    EventTemplate(
        key="diskmaskin_havererad",
        display="Diskmaskinen havererade",
        description=(
            "Diskmaskinen läcker och behöver bytas ut. Nytt kök-vit "
            "kostar runt 6 500 kr inkl. installation."
        ),
        kind="unexpected",
        frequency_per_year=0.20,
        family_status_filter=("ensam", "sambo", "familj_med_barn"),
        cost_range=(5500, 9000),
        pentagon_unmitigated=PentagonImpact(economy=-7, health=-1),
        pentagon_mitigated=PentagonImpact(economy=-2),
        mitigations=(
            Mitigation("hem", 0.20, "Hemförsäkring · självrisk 1 500 kr"),
        ),
        sender="Elgiganten",
        sender_short="ELG",
    ),
    EventTemplate(
        key="vattenskada_badrum",
        display="Vattenskada i badrummet",
        description="Läcka från grannlägenheten. Reparation + utredning krävs.",
        kind="unexpected",
        frequency_per_year=0.05,
        cost_range=(15000, 45000),
        pentagon_unmitigated=PentagonImpact(economy=-15, safety=-8, health=-5),
        pentagon_mitigated=PentagonImpact(economy=-3, safety=-1),
        mitigations=(
            Mitigation("hem", 0.10, "Hemförsäkring täcker · självrisk 3 000 kr"),
            Mitigation("bostadsrattsforsakring", 0.05, "BR-tillägg täcker fullt"),
        ),
        sender="Bostadsrättsföreningen",
        sender_short="BRF",
        sender_kind="land",
        echo_trigger="Tänk på att hemförsäkringens belopp ofta är låga vid vattenskada — tilläggs-skydd kan vara värt det.",
    ),
    EventTemplate(
        key="parboende_inflyttning",
        display="Sambon flyttar in · möbel-investering",
        description="Ni behöver dela på inköp för att starta gemensamt boende.",
        kind="lifecycle",
        frequency_per_year=0.15,
        family_status_filter=("sambo",),
        cost_range=(4000, 12000),
        pentagon_unmitigated=PentagonImpact(economy=-5, social=+3),
        sender="IKEA",
        sender_short="IKEA",
    ),

    # --- TRANSPORT ---
    EventTemplate(
        key="cykel_stulen",
        display="Cykeln stulen utanför arbetet",
        description="Cykeln stals trots att du låste den. Polisanmälan inlämnad.",
        kind="unexpected",
        frequency_per_year=0.15,
        cost_range=(4000, 12000),
        pentagon_unmitigated=PentagonImpact(economy=-6, leisure=-3),
        pentagon_mitigated=PentagonImpact(economy=-1, leisure=-2),
        mitigations=(
            Mitigation("hem", 0.15, "Hemförsäkring drulle · självrisk 1 500"),
        ),
        sender="Polisen",
        sender_short="POL",
        sender_kind="other",
    ),
    EventTemplate(
        key="bilreparation",
        display="Bilen behöver reparation",
        description="Verkstaden upptäckte slitage på bromsar och kamrem.",
        kind="unexpected",
        frequency_per_year=0.30,
        cost_range=(3500, 14000),
        pentagon_unmitigated=PentagonImpact(economy=-6),
        pentagon_mitigated=PentagonImpact(economy=-2),
        mitigations=(
            Mitigation("bilforsakring", 0.40, "Maskinskadeförsäkring täcker delvis"),
        ),
        sender="Volkswagen Service",
        sender_short="BIL",
    ),
    EventTemplate(
        key="parkeringsbot",
        display="Parkeringsbot · 700 kr",
        description="Glömde att flytta bilen vid sopning.",
        kind="unexpected",
        frequency_per_year=0.40,
        cost_range=(700, 1400),
        pentagon_unmitigated=PentagonImpact(economy=-2),
        sender="Stockholm Parkering",
        sender_short="PARK",
        sender_kind="other",
    ),

    # --- ARBETE & KARRIÄR ---
    EventTemplate(
        key="bonus_julgava",
        display="Företagsbonus · ovanlig",
        description="Företaget delar ut en oväntad bonus i samband med årsskifte.",
        kind="income",
        frequency_per_year=0.15,
        cost_range=(-15000, -3000),  # Negativ = inkomst
        pentagon_unmitigated=PentagonImpact(economy=+5, safety=+2),
        sender="Arbetsgivaren",
        sender_short="WORK",
        sender_kind="work",
    ),
    EventTemplate(
        key="overtidsersattning",
        display="Övertidsersättning · projektslut",
        description="Extra utbetalning för intensiva veckor.",
        kind="income",
        frequency_per_year=0.40,
        cost_range=(-8000, -1500),
        pentagon_unmitigated=PentagonImpact(economy=+3, leisure=-2),
        sender="Arbetsgivaren",
        sender_short="WORK",
        sender_kind="work",
    ),
    EventTemplate(
        key="arbetsloshet_varslad",
        display="Varsel · 3 mån uppsägningstid",
        description=(
            "Företaget varslar om personalneddragning. Du har 3 månaders "
            "uppsägningstid kvar."
        ),
        kind="career",
        frequency_per_year=0.04,
        age_range=(22, 65),
        cost_range=(0, 0),
        pentagon_unmitigated=PentagonImpact(
            economy=-10, safety=-15, health=-8,
        ),
        pentagon_mitigated=PentagonImpact(economy=-3, safety=-5, health=-3),
        mitigations=(
            Mitigation("inkomstforsakring", 0.50, "Inkomstförsäkring täcker 80% i 200 dagar"),
        ),
        actor_route="/v2/arbetsformedlingen",
        sender="HR-avdelningen",
        sender_short="HR",
        sender_kind="work",
        echo_trigger="Hur ser din ekonomiska buffert ut just nu?",
    ),
    EventTemplate(
        key="loneforhojning_arlig",
        display="Lönerevision · ny månadslön",
        description="Lönerevisionen gav 3 % löneförhöjning.",
        kind="income",
        frequency_per_year=0.95,  # ~1 ggr/år
        cost_range=(0, 0),  # Lön ändras separat (ej engångsbelopp)
        pentagon_unmitigated=PentagonImpact(economy=+2, safety=+2),
        sender="HR-avdelningen",
        sender_short="HR",
        sender_kind="work",
    ),
    EventTemplate(
        key="kompetensutveckling_kurs",
        display="Erbjudande om kompetenskurs",
        description="Företaget bjuder in dig till en YH-kort kurs i nätverk.",
        kind="opportunity",
        frequency_per_year=0.35,
        cost_range=(0, 0),
        pentagon_unmitigated=PentagonImpact(safety=+4, leisure=-2),
        sender="HR-avdelningen",
        sender_short="HR",
        sender_kind="work",
    ),

    # --- FAMILJ & SOCIAL ---
    EventTemplate(
        key="kalas_inbjudan",
        display="Inbjudan till barnkalas",
        description="Klasskompisens kalas — en present förväntas.",
        kind="opportunity",
        frequency_per_year=2.5,
        family_status_filter=("familj_med_barn",),
        cost_range=(150, 500),
        pentagon_unmitigated=PentagonImpact(economy=-1, social=+2),
        sender="Förskolan",
        sender_short="SKL",
    ),
    EventTemplate(
        key="present_brollop",
        display="Bröllopspresent från kompis",
        description="Bröllopsinbjudan — present + gåva.",
        kind="lifecycle",
        frequency_per_year=0.30,
        age_range=(20, 50),
        cost_range=(800, 3000),
        pentagon_unmitigated=PentagonImpact(economy=-3, social=+4),
        sender="Tradera",
        sender_short="GIFT",
    ),
    EventTemplate(
        key="familj_semester_planering",
        display="Familjen vill åka på sommarsemester",
        description="Diskussion om sommarsemester — Norge eller Spanien?",
        kind="lifecycle",
        frequency_per_year=1.0,
        # Förutsätter "familjen"/"vi" — solo-elever ska inte få
        # mail om familjesemester när de bor ensamma.
        family_status_filter=("sambo", "familj_med_barn"),
        cost_range=(8000, 35000),
        pentagon_unmitigated=PentagonImpact(economy=-10, social=+5, leisure=+5),
        sender="Resekonsulten",
        sender_short="RES",
    ),

    # --- MYNDIGHET ---
    EventTemplate(
        key="skatteaterbaring",
        display="Skatteåterbäring · slutskattebesked",
        description="Skatteverket drog för mycket i preliminärskatt.",
        kind="income",
        frequency_per_year=0.25,
        cost_range=(-9000, -1000),
        pentagon_unmitigated=PentagonImpact(economy=+3),
        sender="Skatteverket",
        sender_short="SKV",
        sender_kind="skv",
    ),
    EventTemplate(
        key="kvarskatt",
        display="Kvarskatt · slutskattebesked",
        description="Skatteverket vill ha in kvarskatt.",
        kind="unexpected",
        frequency_per_year=0.20,
        cost_range=(2500, 12000),
        pentagon_unmitigated=PentagonImpact(economy=-5),
        sender="Skatteverket",
        sender_short="SKV",
        sender_kind="skv",
        echo_trigger="Var det en överraskning eller hade du kunnat förbereda dig?",
    ),
    EventTemplate(
        key="csn_aterbetalning_andring",
        display="CSN · ny avbetalningsplan",
        description="CSN justerar din avbetalningsplan baserat på inkomst.",
        kind="lifecycle",
        frequency_per_year=0.15,
        age_range=(22, 50),
        cost_range=(0, 0),
        pentagon_unmitigated=PentagonImpact(economy=-1, safety=+1),
        sender="CSN",
        sender_short="CSN",
        sender_kind="skv",
    ),

    # --- TJÄNSTER & PRENUMERATIONER ---
    EventTemplate(
        key="streaming_prishojning",
        display="Netflix prishöjning",
        description="Månadsavgiften höjs med 30 kr.",
        kind="lifecycle",
        frequency_per_year=0.30,
        cost_range=(0, 0),  # Återkommande, ingen engångsutgift
        pentagon_unmitigated=PentagonImpact(economy=-1),
        sender="Netflix",
        sender_short="NFX",
        sender_kind="util",
    ),
    EventTemplate(
        key="gym_arsavtal",
        display="Erbjudande · gym-årsavtal",
        description="SATS sänker årspriset med 20 % om du betalar nu.",
        kind="opportunity",
        frequency_per_year=0.20,
        cost_range=(4500, 7000),
        pentagon_unmitigated=PentagonImpact(economy=-3, health=+5, leisure=+3),
        sender="SATS",
        sender_short="GYM",
    ),

    # --- OLYCKA & SKADA ---
    EventTemplate(
        key="mobil_tappad",
        display="Mobilen tappad i golvet",
        description="Skärmen krossad. Reparation eller ny mobil?",
        kind="unexpected",
        frequency_per_year=0.20,
        cost_range=(2200, 9000),
        pentagon_unmitigated=PentagonImpact(economy=-4),
        pentagon_mitigated=PentagonImpact(economy=-1),
        mitigations=(
            Mitigation("hem", 0.20, "Hemförsäkring drulle · självrisk 1 500"),
        ),
        sender="iPlace Service",
        sender_short="MOB",
    ),
    EventTemplate(
        key="hund_veterinar",
        display="Hunden behöver veterinärvård",
        description="Magbesvär — behov av provtagning + medicin.",
        kind="unexpected",
        frequency_per_year=0.40,
        cost_range=(1500, 8000),
        pentagon_unmitigated=PentagonImpact(economy=-4, health=-1),
        pentagon_mitigated=PentagonImpact(economy=-1),
        mitigations=(
            Mitigation("djur", 0.20, "Djurförsäkring täcker 80 %"),
        ),
        sender="Evidensia",
        sender_short="VET",
    ),

    # --- POSITIVA HÄNDELSER ---
    EventTemplate(
        key="lottovinst_liten",
        display="Liten lottovinst",
        description="Du vann 500 kr på Lotto.",
        kind="opportunity",
        frequency_per_year=0.10,
        cost_range=(-2000, -100),
        pentagon_unmitigated=PentagonImpact(economy=+1, leisure=+2),
        sender="Svenska Spel",
        sender_short="SPL",
    ),
    EventTemplate(
        key="present_morfar",
        display="Mormor/morfar gav present",
        description="En oväntad gåva från släkten.",
        kind="opportunity",
        frequency_per_year=0.50,
        cost_range=(-5000, -500),
        pentagon_unmitigated=PentagonImpact(economy=+2, social=+3),
        sender="Familj",
        sender_short="FAM",
    ),
    EventTemplate(
        key="vinst_returnera_vara",
        display="Returnerade en vara · pengar tillbaka",
        description="Den där tröjan du köpte i förra veckan: passar inte.",
        kind="income",
        frequency_per_year=0.60,
        cost_range=(-1500, -200),
        pentagon_unmitigated=PentagonImpact(economy=+1),
        sender="Returavdelningen",
        sender_short="RTN",
    ),

    # --- ARBETSFÖRMEDLINGEN ---
    EventTemplate(
        key="arbetsformedlingen_tipsar",
        display="Arbetsförmedlingen tipsar om jobb",
        description=(
            "Vi tror att den här rollen passar dig — vill du läsa mer "
            "och eventuellt söka?"
        ),
        kind="opportunity",
        frequency_per_year=1.5,
        age_range=(18, 65),
        cost_range=(0, 0),
        pentagon_unmitigated=PentagonImpact(safety=+1),
        actor_route="/v2/arbetsformedlingen",
        sender="Arbetsförmedlingen",
        sender_short="AF",
        sender_kind="other",
        echo_trigger="Verkar passa dig — vill du läsa mer?",
    ),

    # --- LIVSCYKEL-HÄNDELSER ---
    EventTemplate(
        key="resa_vanner",
        display="Vänner vill åka helg-resa",
        description="Krogtur till Köpenhamn — vill du följa med?",
        kind="opportunity",
        frequency_per_year=0.50,
        age_range=(20, 55),
        cost_range=(2500, 7000),
        pentagon_unmitigated=PentagonImpact(economy=-5, social=+5, leisure=+4),
        sender="Vänner",
        sender_short="SOC",
    ),
    EventTemplate(
        key="hyresavi_indexerad",
        display="Hyresvärden · hyreshöjning",
        description="Indexering av hyra med 2 % från nästa månad.",
        kind="lifecycle",
        frequency_per_year=0.40,
        cost_range=(0, 0),
        pentagon_unmitigated=PentagonImpact(economy=-2, safety=-1),
        sender="Hyresvärden",
        sender_short="HYR",
        sender_kind="land",
    ),
]


# === LOOKUP-INDEX ===

EVENT_BY_KEY: dict[str, EventTemplate] = {e.key: e for e in EVENT_TEMPLATES}


def list_active_templates() -> list[EventTemplate]:
    return [e for e in EVENT_TEMPLATES if e.active]
