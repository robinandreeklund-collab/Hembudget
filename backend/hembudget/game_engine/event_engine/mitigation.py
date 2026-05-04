"""E2 · Försäkrings-mildring.

Spec: dev/game-motor/04-event-engine.md (Försäkrings-mildring)

`apply_mitigation(template, policies, profile)` returnerar en
`MitigationResult` med:
- effective_cost · vad eleven faktiskt betalar
- pentagon_impact · vilken påverkan som ska appliceras
- mitigation_label · text till mailbody / audit-log
- policy_id · ev. försäkring som användes
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Optional

from .templates import EventTemplate, Mitigation, PentagonImpact


@dataclass
class MitigationResult:
    """Resultat av mitigation-räkning för ett event."""

    template_key: str
    base_cost: int                # rå slumpad kostnad innan mitigation
    effective_cost: int           # vad eleven betalar
    pentagon_impact: PentagonImpact
    mitigation_used: bool
    mitigation_label: Optional[str]
    policy_id: Optional[int]
    policy_kind: Optional[str]


def best_mitigation_for(
    template: EventTemplate,
    policies: Iterable,           # InsurancePolicy-likt (har .kind, .id, .status)
    *,
    savings_buffer: int = 0,
) -> tuple[Optional[Mitigation], Optional[int]]:
    """Hitta första matchande mitigation för (template, policies).

    Returnerar (mitigation, policy_id). Båda None om ingen mildring
    matchar.

    Reglerna:
    1. Ittererar template.mitigations i ordning (första vinner)
    2. För insurance_kind: kräver att en policy med .kind == kind är
       active. Ej-aktiva policys ignoreras.
    3. Om insurance_kind är None → är en "savings_buffer-mitigation" och
       kräver att eleven har minst `requires_savings_buffer_min` kr.
    """
    active_policies_by_kind: dict[str, int] = {}
    for p in policies:
        status = getattr(p, "status", None)
        if status not in (None, "active"):
            continue
        kind = getattr(p, "kind", None)
        pid = getattr(p, "id", None)
        if kind and pid is not None and kind not in active_policies_by_kind:
            active_policies_by_kind[kind] = pid

    for mit in template.mitigations:
        if mit.insurance_kind:
            pid = active_policies_by_kind.get(mit.insurance_kind)
            if pid is not None:
                return mit, pid
        else:
            if savings_buffer >= mit.requires_savings_buffer_min:
                return mit, None
    return None, None


def apply_mitigation(
    template: EventTemplate,
    base_cost: int,
    policies: Iterable,
    *,
    savings_buffer: int = 0,
) -> MitigationResult:
    """Applicera ev. mitigation och returnera färdigberäknat resultat."""
    mit, policy_id = best_mitigation_for(
        template, policies, savings_buffer=savings_buffer,
    )

    if mit is None:
        return MitigationResult(
            template_key=template.key,
            base_cost=base_cost,
            effective_cost=base_cost,
            pentagon_impact=template.pentagon_unmitigated,
            mitigation_used=False,
            mitigation_label=None,
            policy_id=None,
            policy_kind=None,
        )

    effective = int(round(base_cost * mit.cost_multiplier))
    impact = template.pentagon_mitigated or template.pentagon_unmitigated
    return MitigationResult(
        template_key=template.key,
        base_cost=base_cost,
        effective_cost=effective,
        pentagon_impact=impact,
        mitigation_used=True,
        mitigation_label=mit.label,
        policy_id=policy_id,
        policy_kind=mit.insurance_kind,
    )
