"""Slumpevents · oväntade händelser i advanced mode.

Spec: deb/README.md avsnitt 6 ("Försäkring: skyddar mot slumpmässiga
händelser i RandomEventEngine") + avsnitt 8 ("läraren matar in
oväntade händelser").

Vi har två kanaler:
1. **Engine-events** — denna fil. Slumpas vid varje tick i advanced
   mode. Pedagogiskt syfte: visa att verkligheten är osäker, att
   försäkring + buffert har värde.
2. **Lärar-events** — leverantörsfaktura-mass-skick i lärar-vyn.
   Manuella, inte slump.

Försäkring (BusinessDecision.kind = 'insurance') skyddar mot
specifika kinds. Vi kollar `BusinessDecision.insurance_kind` mot
event_kind innan vi sätter ekonomisk skada.

Determinism: seedat på (company_id, week_no, event_index).
"""
from __future__ import annotations

import random
from dataclasses import dataclass


EVENT_KINDS = [
    "datorn_gick_sonder",
    "kund_klagade",
    "miljoskatt",
    "leverantor_hojde_pris",
    "vattenskada_lokalen",
    "stold_av_verktyg",
]


@dataclass
class BizEventTemplate:
    kind: str
    label: str
    description: str
    cost: int                      # SEK utgift som triggas
    insurance_covered_by: str | None  # Försäkringskind som skyddar
    reputation_impact: int          # delta på reputation
    creates_complaint: bool


EVENT_TEMPLATES: dict[str, BizEventTemplate] = {
    "datorn_gick_sonder": BizEventTemplate(
        kind="datorn_gick_sonder",
        label="Datorn gick sönder",
        description=(
            "Din arbetsdator slutade fungera. Reparation eller ny dator."
        ),
        cost=12000,
        insurance_covered_by="egendom",
        reputation_impact=0,
        creates_complaint=False,
    ),
    "kund_klagade": BizEventTemplate(
        kind="kund_klagade",
        label="Kund klagade på leverans",
        description=(
            "En tidigare kund hörde av sig och var missnöjd. "
            "Ni får göra om eller ge prisavdrag."
        ),
        cost=2500,
        insurance_covered_by=None,
        reputation_impact=-5,
        creates_complaint=True,
    ),
    "miljoskatt": BizEventTemplate(
        kind="miljoskatt",
        label="Oväntad miljöskatt",
        description=(
            "Skatteverket kräver in en miljöskatt för förra perioden."
        ),
        cost=4500,
        insurance_covered_by=None,
        reputation_impact=0,
        creates_complaint=False,
    ),
    "leverantor_hojde_pris": BizEventTemplate(
        kind="leverantor_hojde_pris",
        label="Leverantören höjde priserna",
        description=(
            "Era inköpskostnader steg med 8 % från idag. "
            "Era marginaler påverkas."
        ),
        cost=1500,
        insurance_covered_by=None,
        reputation_impact=0,
        creates_complaint=False,
    ),
    "vattenskada_lokalen": BizEventTemplate(
        kind="vattenskada_lokalen",
        label="Vattenskada i lokalen",
        description=(
            "Ledning brustit. Saneringsarbete och utrustning förstörd."
        ),
        cost=18000,
        insurance_covered_by="egendom",
        reputation_impact=0,
        creates_complaint=False,
    ),
    "stold_av_verktyg": BizEventTemplate(
        kind="stold_av_verktyg",
        label="Verktygsstöld",
        description=(
            "Inbrott i bilen. Stulna verktyg måste ersättas."
        ),
        cost=8500,
        insurance_covered_by="egendom",
        reputation_impact=0,
        creates_complaint=False,
    ),
}


@dataclass
class TriggeredBizEvent:
    template: BizEventTemplate
    actual_cost: int               # Efter försäkrings-reduktion
    insurance_covered: bool


def roll_events(
    *, seed: int, n_max: int, p_per_week: float,
    insured_kinds: set[str],
) -> list[TriggeredBizEvent]:
    """Slå tärning för veckans events.

    Returnerar lista av faktiskt triggade events (kan vara tom).
    """
    rng = random.Random(seed)
    triggered: list[TriggeredBizEvent] = []
    for _ in range(n_max):
        if rng.random() < p_per_week:
            kind = rng.choice(EVENT_KINDS)
            tmpl = EVENT_TEMPLATES[kind]
            insured = (
                tmpl.insurance_covered_by is not None
                and tmpl.insurance_covered_by in insured_kinds
            )
            actual_cost = (
                int(tmpl.cost * 0.1) if insured else tmpl.cost
            )  # Försäkring täcker 90 %, self-risk 10 %
            triggered.append(TriggeredBizEvent(
                template=tmpl,
                actual_cost=actual_cost,
                insurance_covered=insured,
            ))
    return triggered
