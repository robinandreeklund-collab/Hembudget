"""PDF-renderare för Ekonomilabbets fyra dokumenttyper.

Format-strategi: vi äger formatet — alla PDF:er börjar med
"EKONOMILABBET <TYP>" så vår parser entydigt känner igen dem. Strukturen
är platt och tabell-baserad, inga columner som kan glida iväg.

Reportlab finns redan installerat (används av rapport-PDF:erna i appen).
"""
from __future__ import annotations

import io
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .scenario import (
    CardEvent,
    LoanEvent,
    MonthScenario,
    SalaryEvent,
    TxEvent,
)


# -- Gemensam styling --

STYLES = getSampleStyleSheet()
H_TITLE = ParagraphStyle(
    "Title", parent=STYLES["Title"], fontSize=18, spaceAfter=4,
    textColor=colors.HexColor("#0f172a"),
)
H_SUB = ParagraphStyle(
    "Sub", parent=STYLES["Normal"], fontSize=10,
    textColor=colors.HexColor("#475569"),
)
H_TAG = ParagraphStyle(
    "Tag", parent=STYLES["Normal"], fontSize=8,
    textColor=colors.HexColor("#94a3b8"),
)
H_LABEL = ParagraphStyle(
    "Label", parent=STYLES["Normal"], fontSize=9,
    textColor=colors.HexColor("#475569"),
)
H_BIG = ParagraphStyle(
    "Big", parent=STYLES["Normal"], fontSize=14, leading=18,
    textColor=colors.HexColor("#0f172a"),
)
H_BODY = ParagraphStyle(
    "Body", parent=STYLES["Normal"], fontSize=10, leading=14,
)


def _kr(amount) -> str:
    """Format SEK med tusentalsavgränsare och två decimaler."""
    if isinstance(amount, Decimal):
        amount = float(amount)
    sign = "-" if amount < 0 else ""
    abs_amount = abs(amount)
    s = f"{abs_amount:,.2f}".replace(",", " ").replace(".", ",")
    return f"{sign}{s} kr"


def _build_doc(buf, title_meta: str) -> SimpleDocTemplate:
    return SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
        title=title_meta, author="Ekonomilabbet",
    )


# ---------- Lönespec ----------

def render_lonespec(salary: SalaryEvent, scenario: MonthScenario) -> bytes:
    buf = io.BytesIO()
    doc = _build_doc(buf, f"Lönespec {scenario.year_month}")
    story = [
        Paragraph("EKONOMILABBET LÖNESPEC", H_TAG),
        Spacer(1, 4),
        Paragraph(f"Lönespecifikation – {salary.pay_date.strftime('%B %Y').capitalize()}", H_TITLE),
        Paragraph(f"Arbetsgivare: <b>{salary.employer}</b>", H_BODY),
        Paragraph(f"Befattning: {salary.profession}", H_BODY),
        Paragraph(f"Utbetalningsdag: {salary.pay_date.isoformat()}", H_BODY),
        Spacer(1, 12),
    ]
    rows = [
        ["Bruttolön (efter ev. sjukavdrag)", _kr(salary.gross)],
    ]
    if salary.sick_days > 0:
        rows.append([
            f"— Sjukavdrag ({salary.sick_days} dag{'ar' if salary.sick_days > 1 else ''})",
            "-" + _kr(salary.sick_deduction),
        ])
    rows.extend([
        ["– Grundavdrag", "-" + _kr(salary.grundavdrag)],
        ["= Beskattningsbar inkomst",
         _kr(salary.gross - salary.grundavdrag)],
        ["Kommunalskatt (32 %)", "-" + _kr(salary.kommunal_tax)],
    ])
    if salary.statlig_tax > 0:
        rows.append(["Statlig skatt (20 %)", "-" + _kr(salary.statlig_tax)])
    rows.append(["", ""])
    rows.append(["NETTOLÖN att utbetala", _kr(salary.net)])

    t = Table(rows, colWidths=[110 * mm, 50 * mm])
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LINEBELOW", (0, 2), (-1, 2), 0.4, colors.HexColor("#cbd5e1")),
        ("LINEABOVE", (0, -1), (-1, -1), 1.2, colors.HexColor("#0f172a")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f1f5f9")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t)
    if salary.note:
        story.append(Spacer(1, 10))
        story.append(Paragraph(
            f"<b>OBS:</b> {salary.note}", H_BODY,
        ))
    story.append(Spacer(1, 18))
    story.append(Paragraph(
        "Detta är en övningsspecifikation — värden är fiktiva och syftar "
        "till att eleven ska kunna räkna och planera sin ekonomi.",
        H_LABEL,
    ))
    doc.build(story)
    return buf.getvalue()


# ---------- Kontoutdrag ----------

def render_kontoutdrag(scenario: MonthScenario) -> bytes:
    buf = io.BytesIO()
    doc = _build_doc(buf, f"Kontoutdrag {scenario.year_month}")
    year, month = map(int, scenario.year_month.split("-"))

    # Beräkna ingående/utgående saldo
    opening = scenario.opening_balance
    txs_sorted = sorted(scenario.transactions, key=lambda t: (t.date, t.description))
    saldo = opening
    table_rows = [["Datum", "Text", "Belopp", "Saldo"]]
    for t in txs_sorted:
        saldo += t.amount
        table_rows.append([
            t.date.isoformat(),
            t.description,
            _kr(t.amount),
            _kr(saldo),
        ])

    story = [
        Paragraph("EKONOMILABBET KONTOUTDRAG", H_TAG),
        Spacer(1, 4),
        Paragraph(f"Kontoutdrag – {scenario.year_month}", H_TITLE),
        Paragraph(f"Bank: <b>{scenario.bank_name}</b>", H_BODY),
        Paragraph(f"Konto: {scenario.bank_account_no}", H_BODY),
        Paragraph(
            f"Period: {year}-{month:02d}-01 till "
            f"{txs_sorted[-1].date.isoformat() if txs_sorted else '—'}",
            H_BODY,
        ),
        Paragraph(f"Ingående saldo: {_kr(opening)}", H_BODY),
        Paragraph(f"Utgående saldo: <b>{_kr(saldo)}</b>", H_BODY),
        Spacer(1, 12),
    ]

    t = Table(
        table_rows,
        colWidths=[24 * mm, 80 * mm, 32 * mm, 32 * mm],
        repeatRows=1,
    )
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#f8fafc")]),
        ("ALIGN", (2, 1), (3, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#0f172a")),
    ]))
    story.append(t)
    doc.build(story)
    return buf.getvalue()


# ---------- Lånebesked ----------

def render_lanbesked(loan: LoanEvent, scenario: MonthScenario) -> bytes:
    buf = io.BytesIO()
    doc = _build_doc(buf, f"Lånebesked {loan.loan_name} {scenario.year_month}")

    story = [
        Paragraph("EKONOMILABBET LÅNEBESKED", H_TAG),
        Spacer(1, 4),
        Paragraph(f"Lånebesked – {loan.loan_name}", H_TITLE),
        Paragraph(f"Långivare: <b>{loan.lender}</b>", H_BODY),
        Paragraph(f"Period: {scenario.year_month}", H_BODY),
        Paragraph(f"Förfallodag: {loan.due_date.isoformat()}", H_BODY),
        Spacer(1, 12),
    ]

    rows = [
        ["Aktuell ränta", f"{loan.rate_pct:.2f} %"],
        ["Räntekostnad denna månad", _kr(loan.interest)],
        ["Amortering denna månad", _kr(loan.amortization)],
        ["", ""],
        ["TOTALT ATT BETALA",
         _kr(loan.interest + loan.amortization)],
        ["Återstående lån (efter amortering)", _kr(loan.remaining)],
    ]
    t = Table(rows, colWidths=[110 * mm, 50 * mm])
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LINEABOVE", (0, 4), (-1, 4), 1.2, colors.HexColor("#0f172a")),
        ("FONTNAME", (0, 4), (-1, 4), "Helvetica-Bold"),
        ("BACKGROUND", (0, 4), (-1, 4), colors.HexColor("#fef3c7")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t)
    story.append(Spacer(1, 18))
    story.append(Paragraph(
        "Räntan avser kostnad för att låna pengar. Amorteringen minskar "
        "ditt skuldsaldo. Tillsammans är detta din månadskostnad för lånet.",
        H_LABEL,
    ))
    doc.build(story)
    return buf.getvalue()


# ---------- Kreditkortsfaktura ----------

def render_kreditkort(
    card_events: list[CardEvent], scenario: MonthScenario,
) -> bytes:
    buf = io.BytesIO()
    doc = _build_doc(buf, f"Kreditkort {scenario.year_month}")
    year, month = map(int, scenario.year_month.split("-"))
    total = sum((e.amount for e in card_events), Decimal(0))

    story = [
        Paragraph("EKONOMILABBET KREDITKORT", H_TAG),
        Spacer(1, 4),
        Paragraph(f"Kreditkortsfaktura – {scenario.year_month}", H_TITLE),
        Paragraph(f"Kort: <b>{scenario.card_name}</b>", H_BODY),
        Paragraph(f"Kortnummer: {scenario.card_account_no}", H_BODY),
        Paragraph(
            f"Period: {year}-{month:02d}-01 till "
            f"{year}-{month:02d}-{card_events[-1].date.day if card_events else '01'}",
            H_BODY,
        ),
        Paragraph(f"Totalt att betala: <b>{_kr(total)}</b>", H_BIG),
        Spacer(1, 12),
    ]

    if not card_events:
        story.append(Paragraph(
            "Inga köp på kortet denna månad.", H_BODY,
        ))
    else:
        rows = [["Datum", "Köp", "Belopp"]]
        for e in card_events:
            rows.append([
                e.date.isoformat(),
                e.description,
                _kr(e.amount),
            ])
        rows.append(["", "Att betala", _kr(total)])
        t = Table(rows, colWidths=[24 * mm, 110 * mm, 36 * mm], repeatRows=1)
        t.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2),
             [colors.white, colors.HexColor("#f8fafc")]),
            ("ALIGN", (2, 0), (2, -1), "RIGHT"),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("LINEABOVE", (0, -1), (-1, -1), 1.0, colors.HexColor("#0f172a")),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#fef3c7")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t)

    story.append(Spacer(1, 18))
    story.append(Paragraph(
        "Kreditkortsfakturan visar alla köp du gjort på kortet under "
        "perioden. Hela summan ska betalas till bankkontot senast "
        "förfallodagen.",
        H_LABEL,
    ))
    doc.build(story)
    return buf.getvalue()
