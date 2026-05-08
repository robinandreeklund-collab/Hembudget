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
from typing import Optional

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


def seed_default_insurance_policies(
    s: Session,
    *,
    housing_type: Optional[str] = None,
    has_partner: bool = False,
) -> int:
    """Seedа default-katalogen i en scope-DB.

    `housing_type` styr vilka som aktiveras vid seed:
    - hyresratt → hem + olycksfall = active
    - bostadsratt → hem + olycksfall + bostadsrättsforsakring = active
    - villa/radhus → hem + olycksfall + villa-försäkring = active
    - None / okänt → ALLA "considered" (lärare seedar manuellt utan
      bostads-kontext, eller test → vi vågar inte gissa vilka som
      passar utan att veta hur eleven bor)

    Övriga (livförsäkring, sjukvård) lämnas "considered" så eleven
    medvetet kan välja att aktivera.

    Idempotent: hoppar över policys som redan finns (matchar på
    provider + kind + name) men UPPDATERAR status om policy redan finns
    men borde vara aktiv. Returnerar antal nya rader skapade.
    """
    # Utan känd bostadstyp aktiverar vi inget — eleven bestämmer.
    active_kinds: set[str] = set()
    if housing_type in ("hyresratt", "bostadsratt", "villa", "radhus"):
        active_kinds.update({"hem", "olycksfall"})
    if housing_type == "bostadsratt":
        active_kinds.add("bostadsrattsforsakring")
    elif housing_type in ("villa", "radhus"):
        active_kinds.add("villa")  # om det finns villa-typ i katalogen
    if has_partner:
        active_kinds.add("liv")

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
        target_status = (
            "active" if spec["kind"] in active_kinds else "considered"
        )
        if existing is not None:
            # Befintlig policy · uppdatera status om eleven inte ändrat den
            if existing.status == "considered" and target_status == "active":
                existing.status = "active"
            continue
        spec_with_status = {**spec, "status": target_status}
        s.add(InsurancePolicy(**spec_with_status))
        created += 1
    if created:
        s.flush()
    return created
