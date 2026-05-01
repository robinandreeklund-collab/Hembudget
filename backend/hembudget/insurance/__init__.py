"""Default-katalog för svenska försäkringar (Fas 2D).

Innehåller 6 vanliga försäkringspaket som speglar svenska 2026-marknaden.
Lärare kan seedа dessa per scope eller anpassa via /v2/teacher/students/
{id}/insurance-policies.

Källor (faktagranskat 2026-04):
- Folksam Hem (lägenhet 50 m²): ~189 kr/mån, 1 500 självrisk
- Folksam Olycksfall: ~131 kr/mån, vård 100 000, invalid 600 000
- Folksam Hem + Olycksfall bundling: ~290 kr/mån (rabatt -30 kr)
- Trygg-Hansa Liv (200 000 utbet): ~50 kr/mån (ung vuxen)
- If Bostadsrättsförsäkring: ~95 kr/mån (krävs vid bolån)
- LF Bil halvförsäkring: ~250 kr/mån (genomsnitt)
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from ..db.models import InsurancePolicy


# Standardpaket. status="considered" som default — eleven aktiverar
# eller läraren togglar till "active". Premium är genomsnitt 2026.
DEFAULT_INSURANCE_POLICIES = [
    {
        "provider": "Folksam",
        "name": "Hemförsäkring",
        "kind": "hem",
        "premium_monthly": Decimal("189"),
        "coverage_amount": Decimal("200000"),
        "deductible": Decimal("1500"),
        "autogiro": True,
        "status": "considered",
        "notes": (
            "Lösegendom max 200 000 kr · ansvar 5 Mkr · rättskydd · "
            "reseskydd 60 dagar"
        ),
    },
    {
        "provider": "Folksam",
        "name": "Olycksfallsförsäkring",
        "kind": "olycksfall",
        "premium_monthly": Decimal("131"),
        "coverage_amount": Decimal("600000"),
        "deductible": None,
        "autogiro": True,
        "status": "considered",
        "notes": (
            "Invaliditetsersättning 600 000 · vårdkostnader 100 000 · "
            "smärt-/lytesersättning"
        ),
    },
    {
        "provider": "Trygg-Hansa",
        "name": "Livförsäkring",
        "kind": "liv",
        "premium_monthly": Decimal("50"),
        "coverage_amount": Decimal("200000"),
        "deductible": None,
        "autogiro": True,
        "status": "considered",
        "notes": (
            "Engångsbelopp 200 000 till efterlevande vid dödsfall. "
            "Värd det om sambo/barn finns."
        ),
    },
    {
        "provider": "If",
        "name": "Bostadsrättsförsäkring",
        "kind": "bostadsrattsforsakring",
        "premium_monthly": Decimal("95"),
        "coverage_amount": Decimal("500000"),
        "deductible": Decimal("3000"),
        "autogiro": True,
        "status": "considered",
        "notes": (
            "Krävs av banken vid bolån · skydd för bostadens "
            "egen del (skadat parkett, läckande rör i din lgh)"
        ),
    },
    {
        "provider": "Länsförsäkringar",
        "name": "Bilförsäkring (halv)",
        "kind": "bilforsakring",
        "premium_monthly": Decimal("250"),
        "coverage_amount": Decimal("100000"),
        "deductible": Decimal("3000"),
        "autogiro": True,
        "status": "considered",
        "notes": (
            "Halvförsäkring · trafik + brand/stöld + glas + "
            "rättsskydd · ej vagn-/kollisionsskydd"
        ),
    },
    {
        "provider": "Folksam",
        "name": "Barnförsäkring",
        "kind": "barnforsakring",
        "premium_monthly": Decimal("125"),
        "coverage_amount": Decimal("1000000"),
        "deductible": None,
        "autogiro": True,
        "status": "considered",
        "notes": (
            "Sjuk- och olycksfallsförsäkring för barn · invalid "
            "1 Mkr · diagnoskapital vid allvarlig sjukdom"
        ),
    },
]


def seed_default_insurance_policies(s: Session) -> int:
    """Seedа default-katalogen i en scope-DB.

    Idempotent: hoppar över policys som redan finns (matchar på
    provider + kind + name). Returnerar antal nya rader.
    """
    created = 0
    for spec in DEFAULT_INSURANCE_POLICIES:
        existing = (
            s.query(InsurancePolicy)
            .filter(
                InsurancePolicy.provider == spec["provider"],
                InsurancePolicy.kind == spec["kind"],
                InsurancePolicy.name == spec["name"],
            )
            .first()
        )
        if existing is not None:
            continue
        s.add(InsurancePolicy(**spec))
        created += 1
    if created:
        s.flush()
    return created
