"""Huvudbok-endpoint — en komplett avstämning av all ekonomisk data.

Syftet: användaren ska snabbt kunna se ATT allt balanserar. Består av
fyra huvuddelar:

1. Balansrapport per konto (opening + flöden + closing)
2. Resultaträkning per kategori (inkomst/utgift)
3. Kontroller (transfers summerar till 0, credit = köp, etc.)
4. Verifikat — hela transaktionslistan för perioden, sorterad

Används av Rapporter-sidans 'Huvudbok'-vy så användaren snabbt ser om
siffrorna hänger ihop eller om något verkar skevt.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db.models import (
    Account,
    Category,
    Loan,
    LoanPayment,
    Transaction,
    UpcomingPayment,
    UpcomingTransaction,
)
from ..loans.matcher import LoanMatcher
from .deps import db, require_auth

router = APIRouter(
    prefix="/ledger", tags=["ledger"], dependencies=[Depends(require_auth)],
)


def _parse_period(year: int | None, month: str | None) -> tuple[date, date, str]:
    """Returnera (start, end, label). end är EXKLUSIV (nästa dag/månad/år)."""
    if month:
        y, m = map(int, month.split("-"))
        start = date(y, m, 1)
        end = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
        return start, end, month
    y = year or date.today().year
    return date(y, 1, 1), date(y + 1, 1, 1), str(y)


def _d(x) -> float:
    return float(x or 0)


@router.get("/")
def huvudbok(
    year: Optional[int] = None,
    month: Optional[str] = None,
    session: Session = Depends(db),
) -> dict:
    """Huvudbok för en period (månad eller helt år).

    - `month=YYYY-MM` → en kalendermånad
    - `year=YYYY` → hela året (default: innevarande år)
    """
    period_start, period_end, period_label = _parse_period(year, month)

    # En tx som användaren manuellt matchat mot en kommande faktura räknas
    # INTE som transfer här, även om is_transfer=True råkar stå kvar från
    # import. Intentionen vid matchning är "detta är en bill-betalning",
    # inte "flytt mellan mina konton" — så vi vill att den syns som utgift
    # i resultaträkningen och inte flaggas som orphan-transfer.
    #
    # VIKTIGT: om matchad-tx ingår i ett transfer_pair måste vi exkludera
    # BÅDA sidor, annars räknas ena sidan som inkomst/utgift och andra
    # som transfer → obalans = tx:ens belopp. Annars får man en stor
    # "Interna överföringar balanserar"-summa utan några synliga orphans.
    upcoming_matched_ids: set[int] = {
        tid for (tid,) in session.query(UpcomingPayment.transaction_id).all()
    }
    reclassified_transfer_ids: set[int] = set(upcoming_matched_ids)
    if upcoming_matched_ids:
        partner_rows = (
            session.query(Transaction.transfer_pair_id)
            .filter(Transaction.id.in_(upcoming_matched_ids))
            .filter(Transaction.transfer_pair_id.is_not(None))
            .all()
        )
        reclassified_transfer_ids.update(pid for (pid,) in partner_rows if pid)

    # ---------- Balansrapport per konto ----------
    accounts = session.query(Account).order_by(Account.id).all()
    account_rows = []
    total_assets = 0.0
    total_liabilities = 0.0

    for acc in accounts:
        # Opening = opening_balance + rörelse FÖRE period_start
        ob = acc.opening_balance or Decimal("0")
        ob_date = acc.opening_balance_date
        is_incognito = bool(getattr(acc, "incognito", False))

        pre_q = session.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
            Transaction.account_id == acc.id,
            Transaction.date < period_start,
        )
        if ob_date is not None:
            pre_q = pre_q.filter(Transaction.date > ob_date)
        pre_sum = Decimal(str(pre_q.scalar() or 0))
        opening_at_period = ob + pre_sum

        # Rörelse UNDER perioden, uppdelat
        tx_in_period = session.query(Transaction).filter(
            Transaction.account_id == acc.id,
            Transaction.date >= period_start,
            Transaction.date < period_end,
        ).all()

        def _is_transfer(t: Transaction) -> bool:
            # Upcoming-matchade tx OCH deras pair-partner räknas som vanliga
            # utgifter/inkomster, inte transfers — även om is_transfer-flaggan
            # råkar stå kvar. Symmetri behövs annars får vi en obalans lika
            # stor som den matchade delen.
            return bool(t.is_transfer) and t.id not in reclassified_transfer_ids

        income_in = sum(
            (t.amount for t in tx_in_period if t.amount > 0 and not _is_transfer(t)),
            Decimal("0"),
        )
        expenses_in = sum(
            (-t.amount for t in tx_in_period if t.amount < 0 and not _is_transfer(t)),
            Decimal("0"),
        )
        transfer_in = sum(
            (t.amount for t in tx_in_period if t.amount > 0 and _is_transfer(t)),
            Decimal("0"),
        )
        transfer_out = sum(
            (-t.amount for t in tx_in_period if t.amount < 0 and _is_transfer(t)),
            Decimal("0"),
        )

        closing = (
            opening_at_period + income_in - expenses_in + transfer_in - transfer_out
        )

        # Inkognito-konton: saldo och privata utgifter räknas inte med i
        # familjens totalekonomi. Bara lön (income) + överföringar får
        # effekt — och bidrar till familjens helhet via mottagarkontots
        # transfer_in/inkomst.
        if is_incognito:
            assets_contribution = 0.0
            liabilities_contribution = 0.0
        else:
            assets_contribution = (
                float(closing) if acc.type not in ("credit",) else 0.0
            )
            liabilities_contribution = (
                -float(closing) if acc.type == "credit" and closing < 0 else 0.0
            )
        total_assets += assets_contribution
        total_liabilities += liabilities_contribution

        account_rows.append({
            "id": acc.id,
            "name": acc.name,
            "bank": acc.bank,
            "type": acc.type,
            "owner_id": acc.owner_id,
            "incognito": is_incognito,
            "opening_balance": float(opening_at_period),
            "income": float(income_in),
            "expenses": float(expenses_in),
            "transfer_in": float(transfer_in),
            "transfer_out": float(transfer_out),
            "closing_balance": float(closing),
            "transaction_count": len(tx_in_period),
        })

    # ---------- Resultaträkning per kategori ----------
    # Hämtar alla transaktioner + join:ar Category + Account (för incognito-
    # filter). Inkognito-kontons PRIVATA UTGIFTER exkluderas helt (vi vet
    # inte vad de går till), men deras inkomster räknas i familj/YTD.
    # is_transfer=False ELLER upcoming-matchad. Se kommentar kring
    # upcoming_matched_ids ovan — matchade tx räknas som utgifter.
    tx_q = (
        session.query(Transaction, Category, Account)
        .outerjoin(Category, Category.id == Transaction.category_id)
        .join(Account, Account.id == Transaction.account_id)
        .filter(
            Transaction.date >= period_start,
            Transaction.date < period_end,
        )
    )
    if reclassified_transfer_ids:
        tx_q = tx_q.filter(
            (Transaction.is_transfer.is_(False))
            | (Transaction.id.in_(reclassified_transfer_ids))
        )
    else:
        tx_q = tx_q.filter(Transaction.is_transfer.is_(False))
    all_tx = tx_q.all()
    cat_agg: dict[tuple[int | None, str], dict] = {}
    income_total = Decimal("0")
    expense_total = Decimal("0")
    uncategorized_count = 0
    for tx, cat, acc in all_tx:
        is_incognito = bool(getattr(acc, "incognito", False))
        # Skippa privata utgifter på inkognito-konton helt
        if is_incognito and tx.amount < 0:
            continue
        cat_id = cat.id if cat else None
        cat_name = cat.name if cat else "Okategoriserat"
        if cat_id is None:
            uncategorized_count += 1
        key = (cat_id, cat_name)
        bucket = cat_agg.setdefault(
            key,
            {
                "category_id": cat_id, "category": cat_name,
                "income": Decimal("0"), "expenses": Decimal("0"), "count": 0,
            },
        )
        if tx.amount > 0:
            bucket["income"] += tx.amount
            income_total += tx.amount
        else:
            bucket["expenses"] += -tx.amount
            expense_total += -tx.amount
        bucket["count"] += 1

    cat_out = []
    for b in cat_agg.values():
        cat_out.append({
            "category_id": b["category_id"],
            "category": b["category"],
            "income": float(b["income"]),
            "expenses": float(b["expenses"]),
            "net": float(b["income"] - b["expenses"]),
            "count": b["count"],
        })
    cat_out.sort(key=lambda r: -(abs(r["income"]) + abs(r["expenses"])))

    # ---------- Kontroller / avstämningar ----------
    checks: list[dict] = []

    # 1. Interna överföringar ska summera till 0 (lika mycket in som ut
    #    när båda sidor är inom perioden)
    transfer_sum = sum(
        (float(r["transfer_in"] - r["transfer_out"]) for r in account_rows),
        0.0,
    )
    # Tolerans: upp till 2 kr öresavrundning över hela perioden är OK.
    # Svenska banker avrundar olika för -tx och +tx, så par kan ha
    # 0.01-0.50 kr diff var. 2 kr räcker för en hel familjs månad.
    transfer_passed = abs(transfer_sum) <= 2.0
    checks.append({
        "name": "Interna överföringar balanserar",
        "passed": transfer_passed,
        "value": round(transfer_sum, 2),
        "detail": (
            "Summan av alla transfer_in minus transfer_out ska vara 0 — "
            "om inte så finns orphan-överföringar (bara en sida av paret) "
            "eller parade överföringar med olika belopp (öresavrundning)"
        ),
        "check_type": "transfers_imbalance" if not transfer_passed else None,
    })

    # 2. Kredit-konto: closing balance ≤ 0 (skuld-konto)
    for r in account_rows:
        if r["type"] == "credit" and r["closing_balance"] > 100:
            checks.append({
                "name": f"Kreditkort '{r['name']}' har positivt saldo",
                "passed": False,
                "value": r["closing_balance"],
                "detail": (
                    "Kreditkortskonton ska normalt ha 0 eller negativt "
                    "saldo (0 = inget att betala, negativt = skuld). "
                    "Positivt saldo tyder på att inbetalningar saknar "
                    "matchning mot en faktura."
                ),
            })

    # 3. Okategoriserade transaktioner
    checks.append({
        "name": "Alla transaktioner är kategoriserade",
        "passed": uncategorized_count == 0,
        "value": uncategorized_count,
        "detail": (
            f"{uncategorized_count} transaktioner saknar kategori — "
            "påverkar budget och rapporter"
        ),
        "check_type": "uncategorized" if uncategorized_count > 0 else None,
    })

    # 4. Lån: outstanding_balance stämmer med principal/current - amort
    loans = session.query(Loan).filter(Loan.active.is_(True)).all()
    matcher = LoanMatcher(session)
    total_loan_debt = 0.0
    loan_rows: list[dict] = []
    for loan in loans:
        balance = float(matcher.outstanding_balance(loan))
        total_loan_debt += balance
        total_paid = float(
            session.query(func.coalesce(func.sum(LoanPayment.amount), 0))
            .filter(
                LoanPayment.loan_id == loan.id,
                LoanPayment.date >= period_start,
                LoanPayment.date < period_end,
            ).scalar() or 0
        )
        loan_rows.append({
            "id": loan.id,
            "name": loan.name,
            "lender": loan.lender,
            "principal_amount": float(loan.principal_amount),
            "current_balance_at_creation": (
                float(loan.current_balance_at_creation)
                if loan.current_balance_at_creation is not None else None
            ),
            "outstanding_balance": balance,
            "interest_rate": loan.interest_rate,
            "payments_in_period": total_paid,
        })
    total_liabilities += total_loan_debt

    # 5. Kommande fakturor vs matchade transaktioner
    # OBS: "matchad" = fullt betald (payment_status == "paid"), INTE bara
    # att matched_transaction_id är satt. En delbetald faktura har en
    # primär match men är inte klar — den ska räknas som unmatched med
    # RESTERANDE belopp (inte ursprungsbelopp).
    from ..upcoming_match.payments import paid_amount as _paid_amount
    _PAID_TOLERANCE = Decimal("2.00")
    ups = (
        session.query(UpcomingTransaction)
        .filter(
            UpcomingTransaction.expected_date >= period_start,
            UpcomingTransaction.expected_date < period_end,
        )
        .all()
    )
    matched_ups: list[UpcomingTransaction] = []
    unmatched_ups: list[UpcomingTransaction] = []
    unmatched_sum_remaining = Decimal("0")
    matched_sum_amount = Decimal("0")
    for u in ups:
        # variance_accepted = användaren har godkänt avvikelse, räknas som matched
        if getattr(u, "variance_accepted", False):
            matched_ups.append(u)
            matched_sum_amount += u.amount
            continue
        paid = _paid_amount(session, u)
        remaining = u.amount - paid
        if abs(remaining) <= _PAID_TOLERANCE:
            matched_ups.append(u)
            matched_sum_amount += u.amount
        else:
            unmatched_ups.append(u)
            # Partiellt betalda räknas med bara återstående del
            unmatched_sum_remaining += remaining if remaining > 0 else Decimal("0")
    unmatched_past = [
        u for u in unmatched_ups if u.expected_date < date.today()
    ]
    checks.append({
        "name": "Passerade kommande-rader är matchade",
        "passed": len(unmatched_past) == 0,
        "value": len(unmatched_past),
        "detail": (
            f"{len(unmatched_past)} kommande-rader med passerat datum "
            "saknar matchning mot en Transaction — antingen ska de "
            "raderas eller matcha en bankrad"
        ),
        "check_type": (
            "unmatched_past_upcomings" if len(unmatched_past) > 0 else None
        ),
    })

    upcoming_summary = {
        "total": len(ups),
        "matched": len(matched_ups),
        "unmatched": len(unmatched_ups),
        "unmatched_past": len(unmatched_past),
        "matched_sum": float(matched_sum_amount),
        "unmatched_sum": float(unmatched_sum_remaining),
    }

    net_worth = total_assets - total_liabilities

    return {
        "period": {
            "label": period_label,
            "start": period_start.isoformat(),
            "end": period_end.isoformat(),
        },
        "accounts": account_rows,
        "categories": cat_out,
        "loans": loan_rows,
        "upcoming_summary": upcoming_summary,
        "checks": checks,
        "totals": {
            "income": float(income_total),
            "expenses": float(expense_total),
            "net_result": float(income_total - expense_total),
            "assets": round(total_assets, 2),
            "liabilities": round(total_liabilities, 2),
            "net_worth": round(net_worth, 2),
            "uncategorized_count": uncategorized_count,
        },
    }


@router.get("/check/{check_type}")
def check_details(
    check_type: str,
    year: Optional[int] = None,
    month: Optional[str] = None,
    session: Session = Depends(db),
) -> dict:
    """Returnerar underliggande rader för en huvudbok-kontroll.

    check_type = 'transfers_imbalance' | 'uncategorized' |
                  'unmatched_past_upcomings'

    Används av huvudbok-UI:t för att expandera varje avstämningsrad och
    visa vilka poster som orsakar problemet, med snabb-åtgärdsknappar.
    """
    period_start, period_end, _label = _parse_period(year, month)

    # Ladda konton en gång så vi kan berika transaction-svar
    accounts = {a.id: a for a in session.query(Account).all()}

    # Upcoming-matchade tx räknas inte som transfers — exkludera dem
    # både från orphan-listan och paired-mismatch-walken. Plus deras
    # pair-partner (symmetri — annars kvarstår obalansen).
    upcoming_matched_ids: set[int] = {
        tid for (tid,) in session.query(UpcomingPayment.transaction_id).all()
    }
    reclassified_transfer_ids: set[int] = set(upcoming_matched_ids)
    if upcoming_matched_ids:
        partner_rows = (
            session.query(Transaction.transfer_pair_id)
            .filter(Transaction.id.in_(upcoming_matched_ids))
            .filter(Transaction.transfer_pair_id.is_not(None))
            .all()
        )
        reclassified_transfer_ids.update(pid for (pid,) in partner_rows if pid)

    def _tx_out(tx: Transaction) -> dict:
        acc = accounts.get(tx.account_id)
        return {
            "id": tx.id,
            "date": tx.date.isoformat(),
            "amount": float(tx.amount),
            "description": tx.raw_description,
            "account_id": tx.account_id,
            "account_name": acc.name if acc else None,
            "category_id": tx.category_id,
            "is_transfer": tx.is_transfer,
            "transfer_pair_id": tx.transfer_pair_id,
        }

    if check_type == "transfers_imbalance":
        # Orphan-transfers: is_transfer=True men ingen motpart.
        # Upcoming-matchade exkluderas — användaren har redan redovisat
        # dem som bill-betalningar.
        orphans_q = (
            session.query(Transaction)
            .filter(
                Transaction.date >= period_start,
                Transaction.date < period_end,
                Transaction.is_transfer.is_(True),
                Transaction.transfer_pair_id.is_(None),
            )
        )
        if reclassified_transfer_ids:
            orphans_q = orphans_q.filter(
                ~Transaction.id.in_(reclassified_transfer_ids)
            )
        orphans = orphans_q.order_by(Transaction.date.desc()).all()
        orphan_net = sum((float(t.amount) for t in orphans), 0.0)

        # Parade men med beloppsskillnad (öresavrundning eller större fel).
        # Walkar pairs och summerar source+destination — balanserat par
        # ska summera till 0. Pair där en sida är upcoming-matchad är
        # redan reklassificerad till expense/income och ska inte räknas.
        paired_q = (
            session.query(Transaction)
            .filter(
                Transaction.date >= period_start,
                Transaction.date < period_end,
                Transaction.is_transfer.is_(True),
                Transaction.transfer_pair_id.is_not(None),
            )
        )
        if reclassified_transfer_ids:
            paired_q = paired_q.filter(
                ~Transaction.id.in_(reclassified_transfer_ids)
            )
        paired = paired_q.all()
        # Gruppera i par: lägsta id i paret är "source"
        seen_pair_ids: set[int] = set()
        mismatched: list[dict] = []
        by_id = {t.id: t for t in paired}
        # Plocka även eventuella partners som ligger utanför perioden
        missing_partner_ids = {
            t.transfer_pair_id for t in paired
            if t.transfer_pair_id and t.transfer_pair_id not in by_id
        }
        if missing_partner_ids:
            extra = session.query(Transaction).filter(
                Transaction.id.in_(missing_partner_ids),
            ).all()
            for t in extra:
                by_id[t.id] = t
        for t in paired:
            if t.id in seen_pair_ids:
                continue
            pid = t.transfer_pair_id
            if pid is None or pid not in by_id:
                continue
            partner = by_id[pid]
            seen_pair_ids.add(t.id)
            seen_pair_ids.add(partner.id)
            # Balanserat par: source+dest = 0. Diff > 0.01 = mismatch
            pair_sum = float(t.amount) + float(partner.amount)
            if abs(pair_sum) > 0.01:
                mismatched.append({
                    "source": _tx_out(t),
                    "destination": _tx_out(partner),
                    "pair_sum": round(pair_sum, 2),
                })

        mismatched_net = sum(p["pair_sum"] for p in mismatched)
        return {
            "check_type": check_type,
            "count": len(orphans),
            "mismatched_pairs_count": len(mismatched),
            "net_diff": round(orphan_net + mismatched_net, 2),
            "orphan_net": round(orphan_net, 2),
            "mismatched_net": round(mismatched_net, 2),
            "transactions": [_tx_out(t) for t in orphans],
            "mismatched_pairs": mismatched,
        }

    if check_type == "uncategorized":
        # Inkludera upcoming-matchade (som räknas som expense, inte transfer)
        # så uncategorized-listan stämmer med resultaträkningens
        # "Okategoriserat"-rad. Annars kan user:n se "8 transactions" i
        # resultaträkningen men bara 1 rad i åtgärda-vyn.
        uncat_q = (
            session.query(Transaction)
            .filter(
                Transaction.date >= period_start,
                Transaction.date < period_end,
                Transaction.category_id.is_(None),
            )
        )
        if reclassified_transfer_ids:
            uncat_q = uncat_q.filter(
                (Transaction.is_transfer.is_(False))
                | (Transaction.id.in_(reclassified_transfer_ids))
            )
        else:
            uncat_q = uncat_q.filter(Transaction.is_transfer.is_(False))
        rows = uncat_q.order_by(Transaction.date.desc()).all()
        return {
            "check_type": check_type,
            "count": len(rows),
            "transactions": [_tx_out(t) for t in rows],
        }

    if check_type == "unmatched_past_upcomings":
        # "Omatchad" = inte fullt betald. Delbetalda fakturor räknas
        # fortfarande som unmatched eftersom användaren fortfarande
        # måste åtgärda resten.
        from ..upcoming_match.payments import paid_amount as _paid_amount
        from decimal import Decimal as _D
        today = date.today()
        candidates = (
            session.query(UpcomingTransaction)
            .filter(
                UpcomingTransaction.expected_date >= period_start,
                UpcomingTransaction.expected_date < period_end,
                UpcomingTransaction.expected_date < today,
            )
            .order_by(UpcomingTransaction.expected_date.desc())
            .all()
        )
        PAID_TOL = _D("2.00")
        ups = []
        for u in candidates:
            remaining = u.amount - _paid_amount(session, u)
            if abs(remaining) > PAID_TOL:
                ups.append((u, remaining))
        return {
            "check_type": check_type,
            "count": len(ups),
            "upcomings": [
                {
                    "id": u.id,
                    "kind": u.kind,
                    "name": u.name,
                    "amount": float(u.amount),
                    "remaining_amount": float(remaining),
                    "expected_date": u.expected_date.isoformat(),
                    "owner": u.owner,
                    "debit_account_id": u.debit_account_id,
                    "source": u.source,
                }
                for u, remaining in ups
            ],
        }

    raise HTTPException(400, f"Unknown check_type: {check_type}")


@router.get("/export.yaml")
def export_yaml(
    year: Optional[int] = None,
    month: Optional[str] = None,
    session: Session = Depends(db),
) -> Response:
    """Huvudboken som YAML-fil — praktiskt för att klistra in i en
    felsökning eller diffa mellan två perioder."""
    import yaml
    data = huvudbok(year=year, month=month, session=session)
    # Safe-dump (inga Python-objekt, bara primitiver från JSON-dict)
    body = yaml.safe_dump(
        data, allow_unicode=True, sort_keys=False, default_flow_style=False,
    )
    label = data["period"]["label"].replace("/", "-")
    return Response(
        content=body,
        media_type="application/x-yaml",
        headers={
            "Content-Disposition": f'attachment; filename="huvudbok_{label}.yaml"',
        },
    )


@router.get("/export.pdf")
def export_pdf(
    year: Optional[int] = None,
    month: Optional[str] = None,
    session: Session = Depends(db),
) -> Response:
    """Huvudboken som en snygg PDF — för arkiv eller utskrift."""
    from io import BytesIO
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
    )

    data = huvudbok(year=year, month=month, session=session)

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=15 * mm, bottomMargin=15 * mm,
        leftMargin=15 * mm, rightMargin=15 * mm,
        title=f"Huvudbok {data['period']['label']}",
    )
    styles = getSampleStyleSheet()
    h1 = styles["Heading1"]
    h2 = styles["Heading2"]
    body = styles["BodyText"]
    small = ParagraphStyle(
        "Small", parent=body, fontSize=8, textColor=colors.HexColor("#475569"),
    )

    def fmt_kr(n: float) -> str:
        return f"{n:,.0f} kr".replace(",", " ")

    elements = [
        Paragraph(f"Huvudbok — {data['period']['label']}", h1),
        Paragraph(
            f"Period: {data['period']['start']} – {data['period']['end']}",
            small,
        ),
        Spacer(1, 8),
    ]

    # Totals box
    t = data["totals"]
    totals_tbl = Table(
        [
            ["Inkomster", "Utgifter", "Netto", "Nettoförmögenhet"],
            [fmt_kr(t["income"]), fmt_kr(t["expenses"]),
             fmt_kr(t["net_result"]), fmt_kr(t["net_worth"])],
        ],
        hAlign="LEFT",
    )
    totals_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(totals_tbl)
    elements.append(Spacer(1, 12))

    # Checks
    elements.append(Paragraph("Avstämning", h2))
    check_rows = [["✓/✗", "Kontroll", "Värde"]]
    for ch in data["checks"]:
        mark = "✓" if ch["passed"] else "✗"
        check_rows.append([mark, ch["name"], str(ch["value"])])
    if len(check_rows) > 1:
        t = Table(check_rows, colWidths=[15 * mm, 110 * mm, 35 * mm], hAlign="LEFT")
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ]))
        # Färgrad för misslyckade checkar
        for idx, ch in enumerate(data["checks"], start=1):
            if not ch["passed"]:
                t.setStyle(TableStyle([
                    ("BACKGROUND", (0, idx), (-1, idx), colors.HexColor("#fef3c7")),
                ]))
        elements.append(t)
    elements.append(Spacer(1, 12))

    # Balansrapport per konto
    elements.append(Paragraph("Balansrapport per konto", h2))
    acc_rows = [["Konto", "Ingående", "In", "Ut", "TrIn", "TrUt", "Utgående", "#"]]
    for a in data["accounts"]:
        acc_rows.append([
            f"{a['name']}\n{a['bank']} · {a['type']}",
            fmt_kr(a["opening_balance"]),
            fmt_kr(a["income"]),
            fmt_kr(a["expenses"]),
            fmt_kr(a["transfer_in"]) if a["transfer_in"] else "—",
            fmt_kr(a["transfer_out"]) if a["transfer_out"] else "—",
            fmt_kr(a["closing_balance"]),
            str(a["transaction_count"]),
        ])
    if len(acc_rows) > 1:
        t = Table(
            acc_rows,
            colWidths=[45 * mm, 22 * mm, 20 * mm, 20 * mm, 18 * mm, 18 * mm, 22 * mm, 10 * mm],
            hAlign="LEFT",
        )
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        elements.append(t)
    elements.append(Spacer(1, 12))

    # Resultaträkning per kategori
    elements.append(PageBreak())
    elements.append(Paragraph("Resultaträkning per kategori", h2))
    cat_rows = [["Kategori", "Inkomst", "Utgift", "Netto", "#"]]
    for c in data["categories"]:
        cat_rows.append([
            c["category"],
            fmt_kr(c["income"]) if c["income"] > 0 else "—",
            fmt_kr(c["expenses"]) if c["expenses"] > 0 else "—",
            fmt_kr(c["net"]),
            str(c["count"]),
        ])
    if len(cat_rows) > 1:
        t = Table(
            cat_rows,
            colWidths=[70 * mm, 28 * mm, 28 * mm, 28 * mm, 15 * mm],
            hAlign="LEFT",
        )
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ]))
        # Okategoriserade i gult
        for idx, c in enumerate(data["categories"], start=1):
            if c["category"] == "Okategoriserat":
                t.setStyle(TableStyle([
                    ("BACKGROUND", (0, idx), (-1, idx), colors.HexColor("#fef3c7")),
                ]))
        elements.append(t)

    # Lån
    if data["loans"]:
        elements.append(Spacer(1, 12))
        elements.append(Paragraph("Lån", h2))
        loan_rows = [["Lån", "Långivare", "Ursprung", "Kvar", "Ränta", "Betalt"]]
        for l in data["loans"]:
            loan_rows.append([
                l["name"], l["lender"],
                fmt_kr(l["principal_amount"]),
                fmt_kr(l["outstanding_balance"]),
                f"{l['interest_rate']*100:.2f}%",
                fmt_kr(l["payments_in_period"]),
            ])
        t = Table(loan_rows, hAlign="LEFT")
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
        ]))
        elements.append(t)

    doc.build(elements)
    pdf_bytes = buf.getvalue()
    label = data["period"]["label"].replace("/", "-")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="huvudbok_{label}.pdf"',
        },
    )
