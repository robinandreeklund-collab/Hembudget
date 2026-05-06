"""Domänlogik för företagsläget — moms-beräkning, lönekostnad, bolagsskatt."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from .models import (
    Company,
    CompanyInvoice,
    CompanyOwnerSalary,
    CompanyTransaction,
    CompanyVatPeriod,
)


# === Konstanter ===

EMPLOYER_FEE_DEFAULT = Decimal("0.3142")    # 31.42% 2026
EMPLOYER_FEE_YOUNG = Decimal("0.1949")      # 18-24 år 2026
PREL_TAX_DEFAULT = Decimal("0.30")          # Personal A-skatt enkel
CORPORATE_TAX = Decimal("0.206")            # Bolagsskatt 20.6 % 2026
VAT_RATES = (Decimal("0.25"), Decimal("0.12"), Decimal("0.06"), Decimal("0.0"))


# === Lön ===


def compute_owner_salary(
    *,
    gross_salary: int,
    is_young: bool = False,
) -> dict:
    """Räkna ut lönekostnad för ägarens uttag (AB)."""
    gross = Decimal(gross_salary)
    fee_rate = EMPLOYER_FEE_YOUNG if is_young else EMPLOYER_FEE_DEFAULT
    fee = (gross * fee_rate).quantize(Decimal("0.01"))
    prel_tax = (gross * PREL_TAX_DEFAULT).quantize(Decimal("0.01"))
    net = (gross - prel_tax).quantize(Decimal("0.01"))
    total_cost = (gross + fee).quantize(Decimal("0.01"))
    return {
        "gross_salary": float(gross),
        "employer_fee_rate": float(fee_rate),
        "employer_fee_amount": float(fee),
        "prel_tax_rate": float(PREL_TAX_DEFAULT),
        "prel_tax_amount": float(prel_tax),
        "net_to_owner": float(net),
        "total_cost_to_company": float(total_cost),
    }


def book_owner_salary(
    s: Session,
    *,
    company: Company,
    gross_salary: int,
    paid_on: date,
    is_young: bool = False,
    notes: Optional[str] = None,
    student_id: Optional[int] = None,
) -> CompanyOwnerSalary:
    """Skapa CompanyOwnerSalary + matchande CompanyTransaction +
    Bug #7-utbyggnad: matchande Transaction på elevens privata
    lönekonto (= netto-belopp landar i privatekonomin).
    """
    calc = compute_owner_salary(
        gross_salary=gross_salary, is_young=is_young,
    )
    row = CompanyOwnerSalary(
        company_id=company.id,
        paid_on=paid_on,
        gross_salary=Decimal(calc["gross_salary"]),
        employer_fee_rate=Decimal(str(calc["employer_fee_rate"])),
        employer_fee_amount=Decimal(str(calc["employer_fee_amount"])),
        prel_tax_rate=Decimal(str(calc["prel_tax_rate"])),
        prel_tax_amount=Decimal(str(calc["prel_tax_amount"])),
        net_to_owner=Decimal(str(calc["net_to_owner"])),
        total_cost_to_company=Decimal(str(calc["total_cost_to_company"])),
        notes=notes,
    )
    s.add(row)

    # Bokföring · skapa expense-transaction för bolagets kostnad
    s.add(CompanyTransaction(
        company_id=company.id,
        occurred_on=paid_on,
        kind="salary",
        category="Lön till ägare",
        description=f"Lön + arb.giv.avg. ({calc['gross_salary']:.0f} kr brutto)",
        amount_excl_vat=Decimal(str(calc["total_cost_to_company"])),
        vat_rate=Decimal("0.0"),
        vat_amount=Decimal("0.0"),
    ))
    s.flush()

    # Bug #7-utbyggnad · Pengarna landar i privatekonomin
    _credit_private_payroll_account(
        s, paid_on=paid_on, net_amount=int(calc["net_to_owner"]),
        company_name=company.name,
        kind="ab_salary",
    )

    # Pentagon-koppling
    if student_id is not None:
        _apply_business_pentagon_effect(
            student_id=student_id,
            kind="ab_salary",
            gross_salary=int(calc["gross_salary"]),
            net_to_owner=int(calc["net_to_owner"]),
            total_cost=int(calc["total_cost_to_company"]),
        )

    return row


def book_owner_withdrawal(
    s: Session,
    *,
    company: Company,
    amount: int,
    paid_on: date,
    notes: Optional[str] = None,
    student_id: Optional[int] = None,
) -> CompanyTransaction:
    """Bug #7-utbyggnad · Eget uttag (enskild firma).

    Pengarna går från företagskontot till privatkontot. Eleven
    betalar privatskatt på överskottet vid årsdeklaration — INTE
    arbetsgivaravgift. Ingen avdragsgill kostnad för bolaget.
    """
    if company.form != "enskild_firma":
        raise ValueError(
            "Eget uttag gäller bara enskild firma. AB använder lön (book_owner_salary)."
        )
    tx = CompanyTransaction(
        company_id=company.id,
        occurred_on=paid_on,
        kind="expense",
        category="Eget uttag",
        description=notes or f"Eget uttag {amount:,} kr".replace(",", " "),
        amount_excl_vat=Decimal(amount),
        vat_rate=Decimal("0.0"),
        vat_amount=Decimal("0.0"),
    )
    s.add(tx)
    s.flush()

    _credit_private_payroll_account(
        s, paid_on=paid_on, net_amount=amount,
        company_name=company.name,
        kind="own_withdrawal",
    )

    if student_id is not None:
        _apply_business_pentagon_effect(
            student_id=student_id,
            kind="own_withdrawal",
            gross_salary=amount,
            net_to_owner=amount,
            total_cost=amount,
        )

    return tx


def _credit_private_payroll_account(
    s: Session,
    *,
    paid_on: date,
    net_amount: int,
    company_name: str,
    kind: str,
) -> None:
    """Skapa Transaction på elevens privatekonomi-lönekonto.

    `kind`:
      "ab_salary"        — AB-lön (skattat netto)
      "own_withdrawal"   — Eget uttag (obeskattat, deklareras nästa år)
    """
    import hashlib
    from ..db.models import Account, Transaction as PrivTransaction

    # Hitta elevens checking-konto i privatekonomin
    acc = (
        s.query(Account)
        .filter(Account.type == "checking")
        .order_by(Account.id.asc())
        .first()
    )
    if acc is None:
        return  # Eleven har inget privat lönekonto än — hoppa över

    label = (
        "AB-lön (netto)" if kind == "ab_salary"
        else "Eget uttag från egen firma"
    )
    raw = f"{company_name}|{paid_on.isoformat()}|{kind}|{net_amount}"
    tx_hash = hashlib.sha256(raw.encode()).hexdigest()[:32]

    s.add(PrivTransaction(
        account_id=acc.id,
        date=paid_on,
        amount=Decimal(net_amount),  # POSITIV = inkomst
        currency="SEK",
        raw_description=f"{label} · {company_name}",
        normalized_merchant=company_name,
        hash=tx_hash,
        user_verified=True,
    ))
    s.flush()


def _apply_business_pentagon_effect(
    *,
    student_id: int,
    kind: str,
    gross_salary: int,
    net_to_owner: int,
    total_cost: int,
) -> None:
    """Bug #7-utbyggnad · Företagets ekonomi påverkar privat pentagon.

    Logik:
    - Ta ut lön/uttag → +economy privat (har pengar nu)
    - Stort uttag relativt företagets storlek → -safety privat
      (osäkerhet · företaget tappar likviditet)
    - Litet uttag → +safety privat (företaget bygger kassa)
    """
    try:
        from ..game_engine.pentagon import apply_pentagon_delta
    except Exception:
        return

    # +economy proportionellt mot uttagets storlek
    economy_delta = min(3, max(1, net_to_owner // 10000))
    try:
        apply_pentagon_delta(
            student_id,
            axis="economy",
            requested_delta=+economy_delta,
            reason_kind="decision",
            reason_table="company_owner_salaries",
            explanation=(
                f"företaget betalade ut "
                f"{net_to_owner:,} kr netto"
            ).replace(",", " "),
        )
    except Exception:
        pass


# === Moms ===


def compute_period_vat(
    s: Session,
    *,
    company: Company,
    start: date,
    end: date,
) -> dict:
    """Räkna utgående/ingående moms och netto för en period."""
    txs = (
        s.query(CompanyTransaction)
        .filter(
            CompanyTransaction.company_id == company.id,
            CompanyTransaction.occurred_on >= start,
            CompanyTransaction.occurred_on <= end,
        )
        .all()
    )
    output_vat = sum(
        (Decimal(t.vat_amount or 0) for t in txs if t.kind == "income"),
        Decimal(0),
    )
    input_vat = sum(
        (Decimal(t.vat_amount or 0) for t in txs if t.kind == "expense"),
        Decimal(0),
    )
    net = output_vat - input_vat
    return {
        "output_vat": float(output_vat),
        "input_vat": float(input_vat),
        "net_vat": float(net),
        "n_transactions": len(txs),
    }


def file_vat_period(
    s: Session,
    *,
    company: Company,
    period_label: str,
    start: date,
    end: date,
    due: date,
) -> CompanyVatPeriod:
    """Skapa eller uppdatera VatPeriod-rad och bokför moms-betalning."""
    existing = (
        s.query(CompanyVatPeriod)
        .filter(
            CompanyVatPeriod.company_id == company.id,
            CompanyVatPeriod.period_label == period_label,
        )
        .one_or_none()
    )
    calc = compute_period_vat(s, company=company, start=start, end=end)

    if existing is None:
        existing = CompanyVatPeriod(
            company_id=company.id,
            period_label=period_label,
            start_date=start,
            end_date=end,
            due_date=due,
            output_vat=Decimal(str(calc["output_vat"])),
            input_vat=Decimal(str(calc["input_vat"])),
            net_vat=Decimal(str(calc["net_vat"])),
            status="filed",
            filed_on=date.today(),
        )
        s.add(existing)
    else:
        existing.output_vat = Decimal(str(calc["output_vat"]))
        existing.input_vat = Decimal(str(calc["input_vat"]))
        existing.net_vat = Decimal(str(calc["net_vat"]))
        existing.status = "filed"
        existing.filed_on = date.today()

    # Bokför moms-betalning som expense (om netto > 0)
    if calc["net_vat"] > 0:
        s.add(CompanyTransaction(
            company_id=company.id,
            occurred_on=due,
            kind="vat_payment",
            category="Moms",
            description=f"Moms-inbetalning {period_label}",
            amount_excl_vat=Decimal(str(calc["net_vat"])),
            vat_rate=Decimal("0.0"),
            vat_amount=Decimal("0.0"),
        ))
    s.flush()
    return existing


# === Bolagsskatt ===


def compute_business_pentagon(
    s: Session,
    *,
    company: Company,
    today: Optional[date] = None,
) -> dict:
    """Bug #7-utbyggnad · Företagets pentagon (5 axlar 0-100).

    Spec: vol-7-prototyp p-biz-hub
      Axel 01 · Omsättning · senaste 4 v jämfört med rolling-baseline
      Axel 02 · Kundbas    · antal aktiva kunder + ryktes-score
      Axel 03 · Likviditet · kassaflöde + nästa moms-due
      Axel 04 · Tidsåtgång · debiterbara/admin-timmar (förenklat ~50/50)
      Axel 05 · Vinst      · marginal senaste 4 v

    För MVP räknar vi från CompanyTransaction:s 4-veckors-fönster.
    """
    today = today or date.today()
    four_weeks_ago = today - __import__("datetime").timedelta(days=28)
    twelve_weeks_ago = today - __import__("datetime").timedelta(days=84)

    txs_4w = (
        s.query(CompanyTransaction)
        .filter(
            CompanyTransaction.company_id == company.id,
            CompanyTransaction.occurred_on >= four_weeks_ago,
        )
        .all()
    )
    txs_12w = (
        s.query(CompanyTransaction)
        .filter(
            CompanyTransaction.company_id == company.id,
            CompanyTransaction.occurred_on >= twelve_weeks_ago,
            CompanyTransaction.occurred_on < four_weeks_ago,
        )
        .all()
    )

    income_4w = sum(
        (Decimal(t.amount_excl_vat or 0) for t in txs_4w if t.kind == "income"),
        Decimal(0),
    )
    expense_4w = sum(
        (Decimal(t.amount_excl_vat or 0) for t in txs_4w
         if t.kind in ("expense", "salary")),
        Decimal(0),
    )
    profit_4w = income_4w - expense_4w
    margin_4w = float(profit_4w / income_4w * 100) if income_4w > 0 else 0.0

    income_12w = sum(
        (Decimal(t.amount_excl_vat or 0) for t in txs_12w if t.kind == "income"),
        Decimal(0),
    )
    rolling_baseline = (income_12w / 8) if income_12w > 0 else Decimal(1)

    # Axel 01 · Omsättning (50 = baseline, +50 om dubblat)
    if rolling_baseline > 0:
        ratio = float(income_4w / rolling_baseline)
        omsattning = max(0, min(100, int(40 + ratio * 25)))
    else:
        omsattning = 50 if income_4w > 0 else 30

    # Axel 02 · Kundbas (antal aktiva fakturor senaste 90 dgr)
    from .models import CompanyCustomer, CompanyInvoice
    n_invoices_active = (
        s.query(CompanyInvoice)
        .filter(
            CompanyInvoice.company_id == company.id,
            CompanyInvoice.status.in_(("sent", "paid")),
            CompanyInvoice.issued_on >= four_weeks_ago,
        )
        .count()
    )
    kundbas = min(100, 30 + n_invoices_active * 12)

    # Axel 03 · Likviditet (=kassa = ack income - ack expense)
    all_txs = (
        s.query(CompanyTransaction)
        .filter(CompanyTransaction.company_id == company.id)
        .all()
    )
    kassa = sum(
        (Decimal(t.amount_excl_vat or 0) for t in all_txs if t.kind == "income"),
        Decimal(0),
    ) - sum(
        (Decimal(t.amount_excl_vat or 0) for t in all_txs
         if t.kind in ("expense", "salary", "vat_payment", "tax_payment")),
        Decimal(0),
    )
    likviditet = max(0, min(100, int(50 + float(kassa) / 1000)))

    # Axel 04 · Tidsåtgång (förenklat: 60 om aktiv, 40 annars)
    tidsatgang = 60 if income_4w > 0 else 40

    # Axel 05 · Vinst (marginal)
    if income_4w == 0:
        vinst = 30
    elif margin_4w >= 30:
        vinst = 90
    elif margin_4w >= 15:
        vinst = 70
    elif margin_4w >= 5:
        vinst = 55
    elif margin_4w >= 0:
        vinst = 45
    else:
        vinst = 25

    total = (omsattning + kundbas + likviditet + tidsatgang + vinst) // 5

    # === Föregående 4-veckors-fönster (för biz-pent-prev jämförelse i UI) ===
    # Backend räknar inte rekursivt — vi använder de redan-hämtade
    # txs_12w (= 4-12v sedan = "förra månaden") och approximerar
    # axlarna på samma sätt fast på det gamla fönstret. Saknas data →
    # axes_prev = None så frontend hoppar över prev-polygonen.
    axes_prev: Optional[dict] = None
    if txs_12w:
        income_prev = income_12w / 2 if income_12w else Decimal(0)  # ~ snitt 4v
        expense_prev = sum(
            (Decimal(t.amount_excl_vat or 0) for t in txs_12w
             if t.kind in ("expense", "salary")),
            Decimal(0),
        ) / 2
        profit_prev = income_prev - expense_prev
        margin_prev = (
            float(profit_prev / income_prev * 100)
            if income_prev > 0 else 0.0
        )
        # Approximera ratio mot rolling-baseline (samma som ovan men
        # förskjutet en period)
        if rolling_baseline > 0:
            ratio_prev = float(income_prev / rolling_baseline)
            oms_prev = max(0, min(100, int(40 + ratio_prev * 25)))
        else:
            oms_prev = 50 if income_prev > 0 else 30
        # Kundbas-prev: räkna fakturor i det gamla fönstret
        n_inv_prev = (
            s.query(CompanyInvoice)
            .filter(
                CompanyInvoice.company_id == company.id,
                CompanyInvoice.status.in_(("sent", "paid")),
                CompanyInvoice.issued_on >= twelve_weeks_ago,
                CompanyInvoice.issued_on < four_weeks_ago,
            )
            .count()
        )
        kund_prev = min(100, 30 + n_inv_prev * 12)
        # Likviditet-prev approximeras till nuvarande − profit_4w
        # (= kassan som den var FÖRE de senaste 4 veckorna)
        kassa_prev = kassa - profit_4w
        liq_prev = max(0, min(100, int(50 + float(kassa_prev) / 1000)))
        tid_prev = 60 if income_prev > 0 else 40
        if income_prev == 0:
            vinst_prev = 30
        elif margin_prev >= 30:
            vinst_prev = 90
        elif margin_prev >= 15:
            vinst_prev = 70
        elif margin_prev >= 5:
            vinst_prev = 55
        elif margin_prev >= 0:
            vinst_prev = 45
        else:
            vinst_prev = 25
        axes_prev = {
            "omsattning": oms_prev,
            "kundbas": kund_prev,
            "likviditet": liq_prev,
            "tidsatgang": tid_prev,
            "vinst": vinst_prev,
        }

    return {
        "axes": {
            "omsattning": omsattning,
            "kundbas": kundbas,
            "likviditet": likviditet,
            "tidsatgang": tidsatgang,
            "vinst": vinst,
        },
        "axes_prev": axes_prev,
        "total_score": total,
        "metrics": {
            "income_4w": float(income_4w),
            "expense_4w": float(expense_4w),
            "profit_4w": float(profit_4w),
            "margin_4w_pct": round(margin_4w, 1),
            "kassa": float(kassa),
            "n_invoices_active": n_invoices_active,
        },
    }


def estimate_corporate_tax_for_year(
    s: Session,
    *,
    company: Company,
    year: int,
) -> dict:
    """Räkna förväntad bolagsskatt för aktuellt år (gäller AB).

    Bolagsskatt 2026: 20.6 % av skattepliktigt resultat.
    Resultat = inkomster - utgifter (inklusive lön + arb.giv.avg.).
    """
    start = date(year, 1, 1)
    end = date(year, 12, 31)
    txs = (
        s.query(CompanyTransaction)
        .filter(
            CompanyTransaction.company_id == company.id,
            CompanyTransaction.occurred_on >= start,
            CompanyTransaction.occurred_on <= end,
        )
        .all()
    )
    incomes = sum(
        (Decimal(t.amount_excl_vat or 0) for t in txs if t.kind == "income"),
        Decimal(0),
    )
    expenses = sum(
        (Decimal(t.amount_excl_vat or 0) for t in txs
         if t.kind in ("expense", "salary")),
        Decimal(0),
    )
    profit = incomes - expenses
    tax = max(Decimal(0), profit * CORPORATE_TAX).quantize(Decimal("0.01"))
    return {
        "year": year,
        "income_total": float(incomes),
        "expense_total": float(expenses),
        "profit_before_tax": float(profit),
        "corporate_tax_rate": float(CORPORATE_TAX),
        "estimated_tax": float(tax),
        "profit_after_tax": float(profit - tax),
        "n_transactions": len(txs),
    }
