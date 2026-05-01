"""Pydantic-schemas för en genererad profil.

Hålls separata från ORM-modeller (StudentProfile) eftersom profilen
först måste granskas + ev. reroll:as innan den persisteras.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


HousingType = Literal["hyresratt", "bostadsratt", "villa", "radhus"]
FamilyStatus = Literal["ensam", "sambo", "familj_med_barn"]
PartnerModel = Literal["solo", "ai", "klasskompis", "auto"]


class HousingChoice(BaseModel):
    """Boendet eleven hamnar i — typ + storlek + månadskostnad."""

    type: HousingType
    size_kvm: int = Field(ge=15, le=200)
    monthly_cost: int = Field(
        description="Hyra (hyresratt) eller avgift+ränta+amortering (BR/villa)."
    )
    purchase_price: Optional[int] = Field(
        default=None,
        description="Köpeskilling om bostadsrätt/villa/radhus.",
    )
    loan_amount: Optional[int] = Field(
        default=None,
        description="Bostadslån (köpeskilling × LTV).",
    )
    monthly_amortering: Optional[int] = None
    monthly_interest: Optional[int] = None
    monthly_avgift: Optional[int] = None
    monthly_drift: Optional[int] = None


class FamilyChoice(BaseModel):
    """Familjekonfiguration för profilen."""

    status: FamilyStatus
    partner_model: PartnerModel = "solo"
    partner_yrke_key: Optional[str] = None
    partner_gross_monthly: Optional[int] = None
    children_count: int = 0
    children_ages: list[int] = Field(default_factory=list)


class PentagonInit(BaseModel):
    """Startvärden för pentagonen (alla axlar 45-80)."""

    economy: int = Field(ge=0, le=100)
    safety: int = Field(ge=0, le=100)
    health: int = Field(ge=0, le=100)
    social: int = Field(ge=0, le=100)
    leisure: int = Field(ge=0, le=100)
    explanations: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Per-axel lista över vilka modifierare som applicerades.",
    )


class GeneratedProfile(BaseModel):
    """Komplett resultat från Profile Generator."""

    # Identitet
    seed: int = Field(description="Slumpfröet som gav exakt denna profil.")
    name: str

    # Yrke + ekonomi
    yrke_key: str
    yrke_display: str
    yrke_ssyk: str
    monthly_gross: int = Field(description="Bruttolön kr/mån för individ.")
    monthly_net: int = Field(description="Nettolön efter förenklad svensk skatt.")

    # Stad
    city_key: str
    city_display: str
    region: str

    # Boende
    housing: HousingChoice

    # Familj
    family: FamilyChoice
    household_gross_monthly: int = Field(
        description="Individ + ev. partner. Driver budget-procentregler.",
    )
    household_net_monthly: int

    # Pentagon
    pentagon: PentagonInit

    # Profil-fakta som drev pentagon-beräkningen (visas i UI för spårbarhet)
    facts: dict = Field(
        default_factory=dict,
        description=(
            "Härledda fakta: housing_pct, age, has_chronic_condition, "
            "commute_minutes, has_health_insurance, etc."
        ),
    )
