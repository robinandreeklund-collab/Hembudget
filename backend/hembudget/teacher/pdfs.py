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

def _employer_org_no(employer: str) -> str:
    """Deterministisk fake-orgnr per arbetsgivare så samma företag alltid
    har samma nummer i UI:n."""
    h = abs(hash(employer)) % 9999999
    return f"556{h % 1000:03d}-{h % 10000:04d}"


def render_lonespec(
    salary: SalaryEvent,
    scenario: MonthScenario,
    *,
    student_name: str = "Eleven",
    teacher_email: str = "lärare@ekonomilabbet.org",
) -> bytes:
    """Lönespec i Skatteverket-/typisk arbetsgivar-stil:
    Header med arbetsgivare + org-nr, anställd-block, tabell med kolumner
    (Avdrag/Tillägg, Antal, A-pris, Belopp), semester-info, info-fot.

    student_name: visas i 'Anställd:'-fältet.
    teacher_email: visas i footer ('Frågor om din lön: …') så eleven
    vet vart hen ska vända sig (= läraren, inte en påhittad arbetsgivare).
    """
    buf = io.BytesIO()
    doc = _build_doc(buf, f"Lönespec {scenario.year_month}")
    org_no = _employer_org_no(salary.employer)
    period_label = salary.pay_date.strftime("%B %Y").capitalize()
    period_start = salary.pay_date.replace(day=1)

    # Magic header (parser kollar första 200 chars). Hålls minimal.
    story = [
        Paragraph("EKONOMILABBET LÖNESPEC", H_TAG),
        Spacer(1, 6),
    ]

    # Header-block: arbetsgivare vs anställd, två kolumner
    header_rows = [
        [
            Paragraph(f"<b>{salary.employer}</b>", H_BODY),
            Paragraph("<b>LÖNESPECIFIKATION</b>", H_BODY),
        ],
        [
            Paragraph(f"Org.nr: {org_no}<br/>Sverige", H_LABEL),
            Paragraph(
                f"Avlönad: {period_start.isoformat()} – "
                f"{salary.pay_date.isoformat()}<br/>"
                f"Period: {period_label}",
                H_LABEL,
            ),
        ],
    ]
    h_table = Table(header_rows, colWidths=[90 * mm, 84 * mm])
    h_table.setStyle(TableStyle([
        ("LINEBELOW", (0, 1), (-1, 1), 1.0, colors.HexColor("#0f172a")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(h_table)
    story.append(Spacer(1, 10))

    # Anställd-info (parser-anchors: 'Arbetsgivare:', 'Utbetalningsdag:')
    employee_rows = [
        ["Arbetsgivare:", salary.employer, "Utbetalningsdag:", salary.pay_date.isoformat()],
        ["Befattning:", salary.profession, "Skattetabell:", "33"],
        ["Anställd:", student_name, "Anställningsnr:", "ANS-1042"],
    ]
    e_table = Table(employee_rows, colWidths=[28 * mm, 56 * mm, 38 * mm, 50 * mm])
    e_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#475569")),
        ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor("#475569")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(e_table)
    story.append(Spacer(1, 12))

    # Avdrag/Tillägg-tabell — fyrkolumns Skatteverket-stil
    rows = [
        ["Avdrag / Tillägg", "Antal", "A-pris", "Belopp"],
        ["Månadslön", "1", _kr(salary.gross), _kr(salary.gross)],
    ]
    if salary.sick_days > 0:
        rows.append([
            "Sjukavdrag",
            f"{salary.sick_days} dag{'ar' if salary.sick_days > 1 else ''}",
            _kr(-salary.sick_deduction / max(salary.sick_days, 1)),
            "-" + _kr(salary.sick_deduction),
        ])
    rows.append([
        "Bruttolön", "", "", _kr(salary.gross),
    ])
    rows.append([
        "Grundavdrag", "", "",
        "-" + _kr(salary.grundavdrag),
    ])
    rows.append([
        "Beskattningsbar inkomst", "", "",
        _kr(salary.gross - salary.grundavdrag),
    ])
    rows.append([
        "Kommunalskatt (32 %)", "", "",
        "-" + _kr(salary.kommunal_tax),
    ])
    if salary.statlig_tax > 0:
        rows.append([
            "Statlig skatt (20 %)", "", "",
            "-" + _kr(salary.statlig_tax),
        ])
    rows.append(["", "", "", ""])
    rows.append(["NETTOLÖN att utbetala", "", "", _kr(salary.net)])

    t = Table(rows, colWidths=[78 * mm, 22 * mm, 32 * mm, 42 * mm], repeatRows=1)
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        # Header
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        # Alignment
        ("ALIGN", (1, 1), (3, -1), "RIGHT"),
        # Subtotal-linjer
        ("ROWBACKGROUNDS", (0, 1), (-1, -2),
         [colors.white, colors.HexColor("#f8fafc")]),
        ("LINEABOVE", (0, -1), (-1, -1), 1.5, colors.HexColor("#0f172a")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, -1), (-1, -1), 11),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#fef3c7")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t)
    story.append(Spacer(1, 12))

    # Semester-info (vanlig på svenska lönespecar)
    sem_rows = [
        ["Semester", "Intjänade dagar", "Uttagna dagar", "Sparade dagar"],
        ["Innevarande år", "25", "0", "5"],
    ]
    sem_t = Table(sem_rows, colWidths=[40 * mm, 40 * mm, 40 * mm, 40 * mm])
    sem_t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("BOX", (0, 0), (-1, -1), 0.3, colors.HexColor("#94a3b8")),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(sem_t)

    if salary.note:
        story.append(Spacer(1, 10))
        story.append(Paragraph(
            f"<b>OBS:</b> {salary.note}", H_BODY,
        ))
    story.append(Spacer(1, 14))
    story.append(Paragraph(
        f"<b>{salary.employer}</b> &nbsp;&nbsp; Org.nr {org_no} &nbsp;&nbsp; "
        f"Frågor om din lön: <b>{teacher_email}</b>",
        H_LABEL,
    ))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "Övningsdokument från Ekonomilabbet — fiktiva värden för "
        "pedagogiskt syfte. Detta är inte en riktig lönespecifikation.",
        H_TAG,
    ))
    doc.build(story)
    return buf.getvalue()


# ---------- Kontoutdrag ----------

def _iban_from_account_no(account_no: str) -> str:
    """Generera ett deterministiskt IBAN-liknande nummer från kontonr."""
    digits = "".join(c for c in account_no if c.isdigit())
    digits = (digits + "00000000")[:20]
    return f"SE45 8000 {digits[0:4]} {digits[4:8]} {digits[8:12]}"


def render_kontoutdrag(
    scenario: MonthScenario,
    *,
    student_name: str = "Eleven",
) -> bytes:
    """Kontoutdrag i Nordea/SEB-stil:
    Bank-header, kund-block med IBAN/BIC, period-info, saldo-summering,
    detaljerad transaktionstabell med bokföringsdag + beskrivning + belopp +
    löpande saldo.
    """
    buf = io.BytesIO()
    doc = _build_doc(buf, f"Kontoutdrag {scenario.year_month}")
    year, month = map(int, scenario.year_month.split("-"))

    opening = scenario.opening_balance
    txs_sorted = sorted(
        scenario.transactions, key=lambda t: (t.date, t.description),
    )
    saldo = opening
    income_sum = Decimal(0)
    expense_sum = Decimal(0)
    table_rows = [["Datum", "Beskrivning", "Belopp", "Saldo"]]
    for t in txs_sorted:
        saldo += t.amount
        if t.amount > 0:
            income_sum += t.amount
        else:
            expense_sum += -t.amount
        table_rows.append([
            t.date.isoformat(),
            t.description,
            _kr(t.amount),
            _kr(saldo),
        ])

    iban = _iban_from_account_no(scenario.bank_account_no)
    period_end = (
        txs_sorted[-1].date.isoformat() if txs_sorted else f"{year}-{month:02d}-01"
    )

    # Magic-header (parser kollar första 200 chars)
    story = [
        Paragraph("EKONOMILABBET KONTOUTDRAG", H_TAG),
        Spacer(1, 6),
    ]

    # Bank-header
    bank_header = [
        [
            Paragraph(f"<b>{scenario.bank_name.upper()}</b>", H_BODY),
            Paragraph("<b>KONTOUTDRAG</b>", H_BODY),
        ],
        [
            Paragraph(
                "Privatkonto<br/>"
                "Tel kundtjänst: 0771-22 44 88",
                H_LABEL,
            ),
            Paragraph(
                f"Period: {year}-{month:02d}-01 till {period_end}<br/>"
                f"Utskriftsdatum: {period_end}",
                H_LABEL,
            ),
        ],
    ]
    bh_t = Table(bank_header, colWidths=[90 * mm, 84 * mm])
    bh_t.setStyle(TableStyle([
        ("LINEBELOW", (0, 1), (-1, 1), 1.0, colors.HexColor("#0f172a")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(bh_t)
    story.append(Spacer(1, 8))

    # Konto-block
    acct_rows = [
        ["Kontoinnehavare:", student_name],
        ["Kontonummer:", scenario.bank_account_no],
        ["IBAN:", iban],
        ["BIC:", "NDEASESS"],
    ]
    acct_t = Table(acct_rows, colWidths=[34 * mm, 140 * mm])
    acct_t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#475569")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(acct_t)
    story.append(Spacer(1, 10))

    # Saldo-summering box
    sum_rows = [
        ["Ingående saldo", "Insättningar", "Uttag", "Utgående saldo"],
        [
            _kr(opening), "+" + _kr(income_sum),
            "-" + _kr(expense_sum), _kr(saldo),
        ],
    ]
    sum_t = Table(sum_rows, colWidths=[43.5 * mm] * 4)
    sum_t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("FONTSIZE", (0, 1), (-1, 1), 11),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#f1f5f9")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#0f172a")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TEXTCOLOR", (1, 1), (1, 1), colors.HexColor("#059669")),
        ("TEXTCOLOR", (2, 1), (2, 1), colors.HexColor("#dc2626")),
    ]))
    story.append(sum_t)
    story.append(Spacer(1, 12))

    # Transaktionstabell
    t = Table(
        table_rows,
        colWidths=[24 * mm, 86 * mm, 30 * mm, 30 * mm],
        repeatRows=1,
    )
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#f8fafc")]),
        ("ALIGN", (2, 1), (3, -1), "RIGHT"),
        ("FONTNAME", (2, 1), (3, -1), "Courier"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#0f172a")),
    ]))
    story.append(t)

    story.append(Spacer(1, 10))
    story.append(Paragraph(
        f"<b>{scenario.bank_name}</b> · Org.nr 516406-0120 · "
        "Smålandsgatan 17, 105 71 Stockholm",
        H_LABEL,
    ))
    story.append(Paragraph(
        "Övningsdokument från Ekonomilabbet — fiktiva värden för "
        "pedagogiskt syfte.",
        H_TAG,
    ))
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
    *,
    student_name: str = "Eleven",
) -> bytes:
    """Kreditkortsfaktura i SEB Kort/Eurocard-stil:
    Header med kortutgivare, sammanställning-box (föregående saldo,
    inbetalt, köp, ränta, ny saldo), inbetalningsinfo (OCR + bankgiro +
    förfallodag), detaljerad köp-tabell.
    """
    import calendar as _cal
    buf = io.BytesIO()
    doc = _build_doc(buf, f"Kreditkort {scenario.year_month}")
    year, month = map(int, scenario.year_month.split("-"))
    total = sum((e.amount for e in card_events), Decimal(0))
    last_day = _cal.monthrange(year, month)[1]
    period_end = f"{year}-{month:02d}-{last_day:02d}"
    # Förfallodag: ~28:e nästa månad
    if month < 12:
        due_y, due_m = year, month + 1
    else:
        due_y, due_m = year + 1, 1
    due_last = _cal.monthrange(due_y, due_m)[1]
    due_day = min(28, due_last)
    due_date = f"{due_y}-{due_m:02d}-{due_day:02d}"
    min_payment = max(Decimal(int(total * Decimal("0.05"))), Decimal(150)) if total > 0 else Decimal(0)
    ocr = f"{abs(hash(scenario.card_account_no)) % 10**9:09d}"

    # Magic-header (parser läser första 200 chars)
    story = [
        Paragraph("EKONOMILABBET KREDITKORT", H_TAG),
        Spacer(1, 6),
    ]

    # Header
    head_rows = [
        [
            Paragraph(f"<b>{scenario.card_name.upper()}</b>", H_BODY),
            Paragraph("<b>RÄKNING</b>", H_BODY),
        ],
        [
            Paragraph(
                "Kreditkortsleverantör<br/>"
                "Kundtjänst: 0771-44 33 22",
                H_LABEL,
            ),
            Paragraph(
                f"Period: {year}-{month:02d}-01 till {period_end}<br/>"
                f"Förfallodag: <b>{due_date}</b>",
                H_LABEL,
            ),
        ],
    ]
    h_t = Table(head_rows, colWidths=[90 * mm, 84 * mm])
    h_t.setStyle(TableStyle([
        ("LINEBELOW", (0, 1), (-1, 1), 1.0, colors.HexColor("#0f172a")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(h_t)
    story.append(Spacer(1, 8))

    # Kortinnehavare
    holder_rows = [
        ["Kortinnehavare:", student_name],
        ["Kortnummer:", scenario.card_account_no],
        ["Kreditgräns:", "40 000,00 kr"],
    ]
    holder_t = Table(holder_rows, colWidths=[34 * mm, 140 * mm])
    holder_t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#475569")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(holder_t)
    story.append(Spacer(1, 10))

    # Sammanställning-box (typisk för SEB Kort/Eurocard)
    summary_rows = [
        ["Föregående saldo", "Inbetalt", "Nya köp", "Räntekostnad", "Att betala"],
        [
            _kr(0), "+" + _kr(0), "-" + _kr(total),
            _kr(0), _kr(total),
        ],
    ]
    sum_t = Table(summary_rows, colWidths=[34.5 * mm] * 5)
    sum_t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, 0), 7.5),
        ("FONTSIZE", (0, 1), (-1, 1), 10),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BACKGROUND", (-1, 1), (-1, 1), colors.HexColor("#fef3c7")),
        ("BACKGROUND", (0, 1), (-2, 1), colors.HexColor("#f1f5f9")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#0f172a")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(sum_t)
    story.append(Spacer(1, 10))

    # Inbetalningsinfo
    pay_rows = [
        [
            Paragraph(f"<b>Förfallodag</b><br/>{due_date}", H_BODY),
            Paragraph(f"<b>Att betala</b><br/>{_kr(total)}", H_BIG),
            Paragraph(f"<b>Lägsta belopp</b><br/>{_kr(min_payment)}", H_BODY),
        ],
        [
            Paragraph(f"<b>Bankgiro</b><br/>5050-1234", H_LABEL),
            Paragraph(f"<b>OCR-nummer</b><br/>{ocr}", H_LABEL),
            Paragraph("<b>Mottagare</b><br/>SEB Kort AB", H_LABEL),
        ],
    ]
    pay_t = Table(pay_rows, colWidths=[58 * mm] * 3)
    pay_t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#94a3b8")),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(pay_t)
    story.append(Spacer(1, 12))

    # Köp-tabell (parser kräver "Datum" + "Köp" rubriken samt slutrad
    # "Att betala")
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
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2),
             [colors.white, colors.HexColor("#f8fafc")]),
            ("ALIGN", (2, 0), (2, -1), "RIGHT"),
            ("FONTNAME", (2, 1), (2, -1), "Courier"),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("LINEABOVE", (0, -1), (-1, -1), 1.0, colors.HexColor("#0f172a")),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#fef3c7")),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(t)

    story.append(Spacer(1, 12))
    story.append(Paragraph(
        "<b>Effektiv ränta</b> 17,9 % efter förfallodagen. "
        "Betala hela beloppet före förfallodagen för att undvika ränta. "
        "Lägsta belopp tillåts men kostar dyrt över tid.",
        H_LABEL,
    ))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "Övningsdokument från Ekonomilabbet — fiktiva värden för "
        "pedagogiskt syfte.",
        H_TAG,
    ))
    doc.build(story)
    return buf.getvalue()
