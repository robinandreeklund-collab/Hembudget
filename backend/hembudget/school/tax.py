"""Förenklad svensk inkomstskatt-kalkyl för pedagogiskt bruk.

Inte exakt — Skatteverkets riktiga tabeller har fler steg, men för
övningssyfte ger vi en realistisk approximation:

- Kommunalskatt: ~32% (genomsnitt)
- Statlig skatt: 20% på inkomst över brytpunkt 2026 (~625 800 kr/år)
- Grundavdrag: ~15 000 kr/år (förenklat)

Returnerar bruttolön → nettolön + förklaringssträng som visas i
elevens onboarding.
"""
from __future__ import annotations

from dataclasses import dataclass


# Approximerade siffror för 2026 (förenklat — pedagogiskt syfte)
KOMMUNALSKATT = 0.32
STATLIG_SKATT = 0.20
BRYTPUNKT_MANATLIG = 52_150  # ungefär 625 800 / 12
GRUNDAVDRAG_MANATLIG = 1_250  # ungefär 15 000 / 12


@dataclass
class TaxResult:
    gross_monthly: int
    grundavdrag: int
    taxable: int
    kommunal_tax: int
    statlig_tax: int
    total_tax: int
    net_monthly: int
    effective_rate: float
    explanation: str


def compute_net_salary(gross_monthly: int) -> TaxResult:
    """Räkna nettolön + skatt enligt förenklad svensk modell."""
    grundavdrag = min(GRUNDAVDRAG_MANATLIG, gross_monthly)
    taxable = max(0, gross_monthly - grundavdrag)

    # Kommunalskatt på hela beskattningsbara inkomsten
    kommunal = round(taxable * KOMMUNALSKATT)

    # Statlig skatt på den del som överstiger brytpunkten
    over_brytpunkt = max(0, taxable - BRYTPUNKT_MANATLIG)
    statlig = round(over_brytpunkt * STATLIG_SKATT)

    total_tax = kommunal + statlig
    net = gross_monthly - total_tax
    effective_rate = total_tax / gross_monthly if gross_monthly else 0.0

    explanation = _build_explanation(
        gross_monthly, grundavdrag, taxable, kommunal,
        over_brytpunkt, statlig, total_tax, net, effective_rate,
    )

    return TaxResult(
        gross_monthly=gross_monthly,
        grundavdrag=grundavdrag,
        taxable=taxable,
        kommunal_tax=kommunal,
        statlig_tax=statlig,
        total_tax=total_tax,
        net_monthly=net,
        effective_rate=effective_rate,
        explanation=explanation,
    )


def _build_explanation(
    gross: int, grundavdrag: int, taxable: int, kommunal: int,
    over_brytpunkt: int, statlig: int, total_tax: int, net: int,
    eff_rate: float,
) -> str:
    parts = [
        f"Din bruttolön är {gross:,} kr/månad.".replace(",", " "),
        f"Av det får du dra av ett grundavdrag på {grundavdrag:,} kr."
            .replace(",", " "),
        f"Resten ({taxable:,} kr) är skattepliktig.".replace(",", " "),
        f"Kommunalskatten är {KOMMUNALSKATT*100:.0f}% av detta = "
        f"{kommunal:,} kr.".replace(",", " "),
    ]
    if over_brytpunkt > 0:
        parts.append(
            f"Du tjänar mer än brytpunkten ({BRYTPUNKT_MANATLIG:,} kr/mån), "
            f"så på de extra {over_brytpunkt:,} kr betalar du också "
            f"{STATLIG_SKATT*100:.0f}% statlig skatt = {statlig:,} kr."
                .replace(",", " ")
        )
    parts.extend([
        f"Total skatt: {total_tax:,} kr (≈ {eff_rate*100:.1f}% av lönen)."
            .replace(",", " "),
        f"Det betyder att {net:,} kr landar på ditt konto varje månad."
            .replace(",", " "),
    ])
    return " ".join(parts)
