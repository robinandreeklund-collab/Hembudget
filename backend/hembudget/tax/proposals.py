"""Skatteverket-logik: auto-generering av förslag + skatte-beräkning.

- auto_generate_proposals(s, year) — letar efter avdragsgilla räntor i
  Loan/Transaction-tabellerna och skapar TaxProposal-rader om de saknas.
  Idempotent: skapar inte dubbletter för samma (year, kind, source).

- compute_tax_summary(s, year, profile) — räknar slutlig skatt givet
  alla godkända TaxDeduction-rader plus ev. ISK-schablonskatt.
  Returnerar dict med gross_income, prelim_tax, deductions_total,
  isk_tax, final_tax, diff.

- approve_proposal(s, proposal_id) → skapar matchande TaxDeduction
- reject_proposal(s, proposal_id) → markerar status=rejected

INGEN MOCKUP: alla siffror räknas från faktisk data (Loan.interest_rate
× outstanding_balance × tid, FundHolding.market_value × 0,89 %).
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from ..db.models import (
    FundHolding,
    Loan,
    TaxDeduction,
    TaxProposal,
    TaxYearReturn,
    Transaction,
)
from ..loans.matcher import LoanMatcher


def auto_generate_proposals(s: Session, year: int) -> int:
    """Skapa TaxProposal-rader baserat på faktiska räntor i scope-DB.

    För varje aktivt lån med ränta > 0:
    - Räkna årlig räntekostnad (förenklat: outstanding_balance × rate)
    - Skapa TaxProposal "Ränteavdrag på lån X" med suggested_amount
      = ränta × 0,30 (30 % skatteeffekt)

    Idempotent: hoppar över om TaxProposal redan finns för samma
    (year, kind, name, source).
    """
    created = 0
    matcher = LoanMatcher(s)
    active_loans = s.query(Loan).filter(Loan.active.is_(True)).all()

    for loan in active_loans:
        if loan.interest_rate is None or loan.interest_rate <= 0:
            continue
        balance = matcher.outstanding_balance(loan)
        if balance <= 0:
            continue

        rate = Decimal(str(loan.interest_rate))
        # SQLAlchemy rate kan ligga som 0.017 eller 1.7 — normalisera
        if rate > 1:
            rate = rate / 100

        # Schabloniserad årsränta för förslag = balance × rate.
        # Detta är en uppskattning Skatteverket gör tills KU25 kommer.
        annual_interest = (balance * rate).quantize(Decimal("0.01"))
        if annual_interest <= 0:
            continue

        # Avdrag = ränta × 30 % (kapital-avdrag)
        deduction_amount = (annual_interest * Decimal("0.30")).quantize(
            Decimal("0.01"),
        )

        # Avdragstyp baserat på lånets art
        if "csn" in (loan.lender or "").lower() or loan.name and "csn" in loan.name.lower():
            kind = "csn-ranta"
            label_kind = "CSN-lån"
        elif "bolån" in (loan.name or "").lower() or "bostads" in (loan.name or "").lower():
            kind = "bolane-ranta"
            label_kind = "bolån"
        else:
            kind = "ovrig"
            label_kind = loan.name

        proposal_source = f"auto-loan:{loan.id}"

        existing = (
            s.query(TaxProposal)
            .filter(
                TaxProposal.year == year,
                TaxProposal.source == proposal_source,
            )
            .first()
        )
        if existing is not None:
            continue

        s.add(TaxProposal(
            year=year,
            kind=kind,
            name=f"Ränteavdrag på {label_kind}",
            description=(
                f"Ränta {int(annual_interest)} kr betalad på "
                f"{loan.name or loan.lender} under {year} · 30 % avdrag"
            ),
            suggested_amount=deduction_amount,
            status="pending",
            source=proposal_source,
        ))
        created += 1

    if created:
        s.flush()
    return created


def approve_proposal(
    s: Session, proposal_id: int,
) -> Optional[TaxProposal]:
    """Godkänn ett förslag → skapa motsvarande TaxDeduction.

    Idempotent: re-approve gör inget om redan approved.
    """
    proposal = s.get(TaxProposal, proposal_id)
    if proposal is None:
        return None
    if proposal.status == "approved":
        return proposal

    deduction = TaxDeduction(
        year=proposal.year,
        kind=proposal.kind,
        name=proposal.name,
        description=proposal.description,
        amount=proposal.suggested_amount,
        source=f"from-proposal:{proposal.id}",
    )
    s.add(deduction)
    s.flush()

    proposal.status = "approved"
    proposal.decided_at = datetime.utcnow()
    proposal.deduction_id = deduction.id
    s.flush()
    return proposal


def reject_proposal(
    s: Session, proposal_id: int,
) -> Optional[TaxProposal]:
    """Avvisa ett förslag (status=rejected, ingen TaxDeduction skapas)."""
    proposal = s.get(TaxProposal, proposal_id)
    if proposal is None:
        return None
    if proposal.status == "rejected":
        return proposal

    # Om redan godkänd: ta bort kopplad deduction
    if proposal.status == "approved" and proposal.deduction_id:
        ded = s.get(TaxDeduction, proposal.deduction_id)
        if ded:
            s.delete(ded)
        proposal.deduction_id = None

    proposal.status = "rejected"
    proposal.decided_at = datetime.utcnow()
    s.flush()
    return proposal


def isk_schablon_tax(s: Session) -> Decimal:
    """Schablonskatt på ISK = market_value × 0,89 % (förenklad).

    Riktiga regeln är komplexare (4 mätpunkter under året + insättningar),
    men 0,89 % på senaste värdet är en god approximation för pedagogiken.
    """
    from sqlalchemy import func as _f
    total = s.query(_f.coalesce(_f.sum(FundHolding.market_value), 0)).scalar()
    underlying = Decimal(str(total or 0))
    return (underlying * Decimal("0.0089")).quantize(Decimal("0.01"))


def compute_tax_summary(
    s: Session,
    year: int,
    profile_gross_monthly: Optional[Decimal] = None,
    profile_tax_rate: Optional[Decimal] = None,
) -> dict:
    """Räkna ihop skatte-summary för året.

    Källor:
    - Bruttoinkomst = profile.gross_salary_monthly × 12 (om finns) ELLER
      summa positiva lön-transactions för året
    - Förskottsinbetald skatt = brutto × tax_rate (från profile)
      ELLER om vi har lönespec-data, summera faktisk skatt
    - Avdrag = sum(TaxDeduction.amount × 0,30) för året (30 % effekt)
    - ISK-schablonskatt = FundHolding × 0,89 %
    - Slutlig skatt = preliminär + ISK-schablon − avdrag-effekt
    - Diff = preliminär − slutlig
    """
    if profile_gross_monthly and profile_gross_monthly > 0:
        gross_annual = profile_gross_monthly * 12
    else:
        # Räkna från lönespec-transaktioner i året
        from sqlalchemy import func as _f
        from datetime import date as _d
        q = (
            s.query(_f.coalesce(_f.sum(Transaction.amount), 0))
            .filter(Transaction.amount > 0)
            .filter(Transaction.date >= _d(year, 1, 1))
            .filter(Transaction.date < _d(year + 1, 1, 1))
            .filter(_f.lower(Transaction.raw_description).like("%lön%"))
        )
        net_year = Decimal(str(q.scalar() or 0))
        if profile_tax_rate and profile_tax_rate > 0:
            gross_annual = (
                net_year / (Decimal("1") - profile_tax_rate)
            ).quantize(Decimal("0.01"))
        else:
            gross_annual = net_year

    rate = profile_tax_rate or Decimal("0.30")
    prelim_tax = (gross_annual * rate).quantize(Decimal("0.01"))

    deductions = (
        s.query(TaxDeduction)
        .filter(TaxDeduction.year == year)
        .all()
    )
    deductions_total = sum(
        (Decimal(str(d.amount)) for d in deductions), Decimal("0"),
    )
    # 30 % skatteffekt på avdrag (kapital + tjänst i bottenskatt)
    deduction_effect = (deductions_total * Decimal("0.30")).quantize(
        Decimal("0.01"),
    )

    isk_tax = isk_schablon_tax(s)
    final_tax = (prelim_tax + isk_tax - deduction_effect).quantize(
        Decimal("0.01"),
    )
    diff = prelim_tax - final_tax

    return {
        "year": year,
        "gross_income": float(gross_annual),
        "prelim_tax_paid": float(prelim_tax),
        "deductions_total": float(deductions_total),
        "deduction_effect": float(deduction_effect),
        "isk_schablon_tax": float(isk_tax),
        "final_tax": float(final_tax),
        "diff": float(diff),  # positiv = återbäring
    }


def submit_tax_year(
    s: Session,
    year: int,
    profile_gross_monthly: Optional[Decimal],
    profile_tax_rate: Optional[Decimal],
) -> TaxYearReturn:
    """Lås in deklarationen för året (skapa TaxYearReturn).

    Om eleven redan lämnat in: uppdatera siffrorna och behåll locked=True.
    Eleven kan öppna igen via reopen_tax_year() (ej implementerat ännu).
    """
    summary = compute_tax_summary(
        s, year, profile_gross_monthly, profile_tax_rate,
    )

    existing = (
        s.query(TaxYearReturn)
        .filter(TaxYearReturn.year == year)
        .first()
    )
    if existing is None:
        existing = TaxYearReturn(year=year, gross_income=Decimal("0"),
                                  prelim_tax_paid=Decimal("0"),
                                  final_tax=Decimal("0"),
                                  diff=Decimal("0"))
        s.add(existing)

    existing.submitted_at = datetime.utcnow()
    existing.locked = True
    existing.gross_income = Decimal(str(summary["gross_income"]))
    existing.prelim_tax_paid = Decimal(str(summary["prelim_tax_paid"]))
    existing.deductions_total = Decimal(str(summary["deductions_total"]))
    existing.final_tax = Decimal(str(summary["final_tax"]))
    existing.diff = Decimal(str(summary["diff"]))
    s.flush()
    return existing


def latest_tax_year_return(
    s: Session, year: int,
) -> Optional[TaxYearReturn]:
    return (
        s.query(TaxYearReturn)
        .filter(TaxYearReturn.year == year)
        .order_by(TaxYearReturn.id.desc())
        .first()
    )
