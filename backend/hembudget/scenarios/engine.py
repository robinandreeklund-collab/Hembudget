"""Deterministiska scenariomotorer för svenska bolån, sparmål och flytt.

LLM:en föreslår parametrar; dessa funktioner räknar alltid siffrorna.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from decimal import Decimal


# -------- Bolån --------

@dataclass
class MortgageParams:
    price: Decimal                # slutpris
    cash_down: Decimal            # kontantinsats
    interest_rate: float          # nominell årsränta, t.ex. 0.045
    term_years: int = 50          # typisk svensk bolånetid
    household_income_yearly: Decimal = Decimal("0")   # bruttoinkomst
    property_tax_yearly: Decimal = Decimal("9525")    # kommunal fastighetsavgift 2026 schablon
    monthly_fee: Decimal = Decimal("0")               # BRF-avgift eller driftskostnad
    include_interest_deduction: bool = True


@dataclass
class MortgageResult:
    loan_amount: Decimal
    ltv: float                           # belåningsgrad 0..1
    amortization_rate_annual: float      # enligt FI:s regler
    monthly_interest_gross: Decimal
    monthly_interest_net: Decimal        # efter ränteavdrag
    monthly_amortization: Decimal
    monthly_property_tax: Decimal
    monthly_fee: Decimal
    monthly_total_net: Decimal
    kvar_att_leva_pa_ratio: float | None # andel av brutto/månad (informativt)
    assumptions: list[str] = field(default_factory=list)


def _amortization_rate(ltv: float, income_multiple: float | None) -> float:
    """FI:s amorteringskrav (2016/2018 i kraft 2026):
    - LTV > 70 %: 2 % amortering
    - 50 % < LTV <= 70 %: 1 % amortering
    - LTV <= 50 %: 0 %
    - Skuldkvot > 4.5 × årsinkomst: +1 % extra
    """
    rate = 0.0
    if ltv > 0.7:
        rate += 0.02
    elif ltv > 0.5:
        rate += 0.01
    if income_multiple is not None and income_multiple > 4.5:
        rate += 0.01
    return rate


# -------- Sparmål --------

@dataclass
class SavingsGoalParams:
    target_amount: Decimal
    horizon_months: int
    monthly_contribution: Decimal = Decimal("0")
    expected_annual_return: float = 0.05
    start_balance: Decimal = Decimal("0")


@dataclass
class SavingsGoalResult:
    projected_balance: Decimal
    target_amount: Decimal
    shortfall: Decimal                    # positive = saknas
    required_monthly_to_hit: Decimal      # om shortfall
    path: list[tuple[int, Decimal]] = field(default_factory=list)  # (månad, saldo)


# -------- Flytt --------

@dataclass
class MoveParams:
    current_monthly_cost: Decimal
    new_monthly_cost: Decimal
    moving_cost: Decimal = Decimal("0")
    horizon_months: int = 60


@dataclass
class MoveResult:
    monthly_delta: Decimal
    breakeven_months: float | None
    total_over_horizon: Decimal


class ScenarioEngine:
    """Deterministic calculation of common financial scenarios."""

    def mortgage(self, p: MortgageParams) -> MortgageResult:
        assumptions: list[str] = []
        loan = p.price - p.cash_down
        if loan < 0:
            loan = Decimal("0")
        ltv = float(loan / p.price) if p.price > 0 else 0.0

        income_mult = None
        if p.household_income_yearly > 0:
            income_mult = float(loan / p.household_income_yearly)

        amort_rate = _amortization_rate(ltv, income_mult)
        monthly_amort = (loan * Decimal(str(amort_rate))) / Decimal("12")

        monthly_int_gross = (loan * Decimal(str(p.interest_rate))) / Decimal("12")
        if p.include_interest_deduction:
            # 30 % avdrag upp till 100 000 kr/år, 21 % därutöver
            yearly_int = monthly_int_gross * Decimal("12")
            if yearly_int <= Decimal("100000"):
                deduction = yearly_int * Decimal("0.30")
            else:
                deduction = Decimal("100000") * Decimal("0.30") + (
                    yearly_int - Decimal("100000")
                ) * Decimal("0.21")
            monthly_int_net = monthly_int_gross - deduction / Decimal("12")
            assumptions.append("Ränteavdrag 30 %/21 % applicerat")
        else:
            monthly_int_net = monthly_int_gross

        monthly_tax = p.property_tax_yearly / Decimal("12")
        total_net = monthly_int_net + monthly_amort + monthly_tax + p.monthly_fee

        kvar_ratio = None
        if p.household_income_yearly > 0:
            kvar_ratio = float(total_net / (p.household_income_yearly / Decimal("12")))

        if amort_rate > 0:
            assumptions.append(f"Amortering {amort_rate*100:.1f} %/år enligt FI:s krav")
        else:
            assumptions.append("Ingen amortering krävs (LTV ≤ 50 %)")
        if income_mult is not None and income_mult > 4.5:
            assumptions.append(f"Skuldkvot {income_mult:.1f}× → +1 % skärpning")

        q = Decimal("0.01")
        return MortgageResult(
            loan_amount=loan.quantize(q),
            ltv=round(ltv, 4),
            amortization_rate_annual=amort_rate,
            monthly_interest_gross=monthly_int_gross.quantize(q),
            monthly_interest_net=monthly_int_net.quantize(q),
            monthly_amortization=monthly_amort.quantize(q),
            monthly_property_tax=monthly_tax.quantize(q),
            monthly_fee=p.monthly_fee.quantize(q),
            monthly_total_net=total_net.quantize(q),
            kvar_att_leva_pa_ratio=round(kvar_ratio, 4) if kvar_ratio is not None else None,
            assumptions=assumptions,
        )

    def savings_goal(self, p: SavingsGoalParams) -> SavingsGoalResult:
        r_monthly = (1 + p.expected_annual_return) ** (1 / 12) - 1
        balance = p.start_balance
        path: list[tuple[int, Decimal]] = [(0, balance.quantize(Decimal("0.01")))]
        r_dec = Decimal(str(r_monthly))
        for m in range(1, p.horizon_months + 1):
            balance = balance * (Decimal("1") + r_dec) + p.monthly_contribution
            path.append((m, balance.quantize(Decimal("0.01"))))

        projected = balance.quantize(Decimal("0.01"))
        shortfall = (p.target_amount - projected).quantize(Decimal("0.01"))

        # PMT for remaining shortfall: FV = PMT * ((1+r)^n - 1)/r
        required = Decimal("0")
        if shortfall > 0 and p.horizon_months > 0:
            if r_monthly == 0:
                required = (p.target_amount - p.start_balance) / Decimal(p.horizon_months)
            else:
                fv = p.target_amount - p.start_balance * (Decimal("1") + r_dec) ** p.horizon_months
                factor = ((Decimal("1") + r_dec) ** p.horizon_months - Decimal("1")) / r_dec
                required = fv / factor

        return SavingsGoalResult(
            projected_balance=projected,
            target_amount=p.target_amount.quantize(Decimal("0.01")),
            shortfall=max(shortfall, Decimal("0")),
            required_monthly_to_hit=max(required, Decimal("0")).quantize(Decimal("0.01")),
            path=path,
        )

    def move(self, p: MoveParams) -> MoveResult:
        delta = p.new_monthly_cost - p.current_monthly_cost
        breakeven = None
        if delta < 0 and p.moving_cost > 0:
            breakeven = float(p.moving_cost / -delta)
        total = delta * Decimal(p.horizon_months) + p.moving_cost
        q = Decimal("0.01")
        return MoveResult(
            monthly_delta=delta.quantize(q),
            breakeven_months=round(breakeven, 1) if breakeven is not None else None,
            total_over_horizon=total.quantize(q),
        )

    def run(self, kind: str, params: dict) -> dict:
        """Dispatch from generic JSON payloads (used by API + LLM tool use)."""
        if kind == "mortgage":
            p = MortgageParams(
                price=Decimal(str(params["price"])),
                cash_down=Decimal(str(params.get("cash_down", 0))),
                interest_rate=float(params["interest_rate"]),
                term_years=int(params.get("term_years", 50)),
                household_income_yearly=Decimal(str(params.get("household_income_yearly", 0))),
                property_tax_yearly=Decimal(str(params.get("property_tax_yearly", 9525))),
                monthly_fee=Decimal(str(params.get("monthly_fee", 0))),
                include_interest_deduction=bool(params.get("include_interest_deduction", True)),
            )
            return asdict(self.mortgage(p))
        if kind == "savings_goal":
            p = SavingsGoalParams(
                target_amount=Decimal(str(params["target_amount"])),
                horizon_months=int(params["horizon_months"]),
                monthly_contribution=Decimal(str(params.get("monthly_contribution", 0))),
                expected_annual_return=float(params.get("expected_annual_return", 0.05)),
                start_balance=Decimal(str(params.get("start_balance", 0))),
            )
            return asdict(self.savings_goal(p))
        if kind == "move":
            p = MoveParams(
                current_monthly_cost=Decimal(str(params["current_monthly_cost"])),
                new_monthly_cost=Decimal(str(params["new_monthly_cost"])),
                moving_cost=Decimal(str(params.get("moving_cost", 0))),
                horizon_months=int(params.get("horizon_months", 60)),
            )
            return asdict(self.move(p))
        raise ValueError(f"Unknown scenario kind: {kind}")
