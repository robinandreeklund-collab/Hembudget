"""Rik månadsrapport som PDF.

Sektioner:
1. Titel + period + genererad datum
2. KPI-ruta (Inkomst / Utgifter / Sparat / Sparkvot) med färg per cell
3. Pie: Utgifter per kategori (top 8 + Övrigt)
4. Pie: Inkomst per person
5. Tabell: Överföringsförslag (hur mycket vardera person bör föra över
   till gemensamt — baserat på lika delning + income-proportionell delning)
6. Bar chart: Budget vs utfall per kategori
7. Bar chart: Top 10 förändringar mot föregående månad
8. Grupperad kategoritabell med budget/utfall/diff + färg

Layout: A4, 15mm marginaler. Platypus används för flödande layout så
sektionerna paginerar naturligt.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
    Spacer, Table, TableStyle,
)
from sqlalchemy.orm import Session

from ..budget.monthly import MonthlyBudgetService, MonthSummary
from ..chat import tools as chat_tools
from ..db.models import User
from . import charts


SWEDISH_MONTHS = [
    "januari", "februari", "mars", "april", "maj", "juni",
    "juli", "augusti", "september", "oktober", "november", "december",
]


def _format_month_label(month: str) -> str:
    y, m = month.split("-")
    return f"{SWEDISH_MONTHS[int(m) - 1]} {y}"


def _format_sek(amount: float | Decimal) -> str:
    """1 234 567 kr — svensk tusenseparator med space."""
    n = float(amount)
    neg = n < 0
    s = f"{abs(n):,.0f}".replace(",", " ")
    return f"-{s} kr" if neg else f"{s} kr"


def _prev_month(month: str) -> str:
    y, m = map(int, month.split("-"))
    if m == 1:
        return f"{y - 1}-12"
    return f"{y}-{m - 1:02d}"


@dataclass
class TransferSuggestion:
    """Förslag på hur vardera person ska bidra till gemensamma utgifter.
    Presenterar två modeller parallellt så familjen kan välja."""
    person_name: str
    income: float
    income_share_pct: float  # andel av total hushållsinkomst
    fair_equal: float  # 50/50 split
    fair_prorata: float  # proportionellt mot inkomst
    already_paid: float  # utgifter som personens konto redan tagit i mån


@dataclass
class MonthlyReportData:
    """All data som behövs för att rendera PDF:en. Samlad här så vi kan
    testa siffrorna utan att rendera."""
    month: str
    generated_at: datetime
    summary: MonthSummary
    prev_summary: MonthSummary | None
    by_owner: dict  # raw från get_family_breakdown
    transfers: list[TransferSuggestion] = field(default_factory=list)
    # Top-N utgiftskategorier för pie chart (efter utfall)
    expense_slices: list[tuple[str, float]] = field(default_factory=list)
    # Inkomst per person
    income_slices: list[tuple[str, float]] = field(default_factory=list)
    # Största förändringar (abs) mellan denna + föregående månad, (cat, diff)
    deltas: list[tuple[str, float]] = field(default_factory=list)


def build_report_data(session: Session, month: str) -> MonthlyReportData:
    svc = MonthlyBudgetService(session)
    summary = svc.summary(month)

    # Föregående månad — kan vara tom om ingen data finns, men MonthSummary
    # returneras alltid (bara med 0:or).
    try:
        prev_summary = svc.summary(_prev_month(month))
    except Exception:
        prev_summary = None

    family = chat_tools.get_family_breakdown(session, month)
    by_owner: dict = family.get("by_owner", {})

    # Utgifter per kategori — abs(actual) för endast expense-raderna
    expense_slices: list[tuple[str, float]] = []
    for l in summary.lines:
        if l.kind != "income":
            v = abs(float(l.actual))
            if v > 0:
                expense_slices.append((l.category, v))
    expense_slices.sort(key=lambda p: -p[1])

    # Inkomst per person — använd user-ID-mapping när möjligt
    users_by_id = {u.id: u.name for u in session.query(User).all()}
    income_slices: list[tuple[str, float]] = []
    for key, bucket in by_owner.items():
        income = float(bucket.get("income") or 0)
        if income <= 0:
            continue
        label = _pretty_owner_key(key, users_by_id)
        income_slices.append((label, income))
    income_slices.sort(key=lambda p: -p[1])

    # Transfer-förslag: fokusera på "gemensamt"-kostnaden (shared expenses)
    transfers = _compute_transfer_suggestions(by_owner, users_by_id)

    # Förändring mot förra månaden
    deltas: list[tuple[str, float]] = []
    if prev_summary is not None:
        prev_by_cat = {
            l.category_id: (l.category, abs(float(l.actual)))
            for l in prev_summary.lines
            if l.kind != "income"
        }
        cur_by_cat = {
            l.category_id: (l.category, abs(float(l.actual)))
            for l in summary.lines
            if l.kind != "income"
        }
        all_ids = set(prev_by_cat.keys()) | set(cur_by_cat.keys())
        for cid in all_ids:
            name, cur_v = cur_by_cat.get(cid, (None, 0.0))
            if name is None:
                name, _ = prev_by_cat.get(cid, ("?", 0.0))
            prev_v = prev_by_cat.get(cid, (name, 0.0))[1]
            d = cur_v - prev_v
            if abs(d) < 50:  # brus-filter
                continue
            deltas.append((name, d))
        deltas.sort(key=lambda p: -abs(p[1]))

    return MonthlyReportData(
        month=month,
        generated_at=datetime.now(),
        summary=summary,
        prev_summary=prev_summary,
        by_owner=by_owner,
        transfers=transfers,
        expense_slices=expense_slices,
        income_slices=income_slices,
        deltas=deltas,
    )


def _pretty_owner_key(key: str, users_by_id: dict[int, str]) -> str:
    """by_owner-keys ser ut som 'gemensamt' eller 'user_3'. Gör om till
    ett läsbart namn."""
    if key == "gemensamt":
        return "Gemensamt"
    if key.startswith("user_"):
        try:
            uid = int(key.split("_", 1)[1])
        except (ValueError, IndexError):
            return key
        return users_by_id.get(uid, f"Person {uid}")
    return key


def _compute_transfer_suggestions(
    by_owner: dict, users_by_id: dict[int, str],
) -> list[TransferSuggestion]:
    """Räkna fram fair-share-förslag. Vi kollar:
    - Summa gemensamma utgifter (by_owner['gemensamt']['expenses'])
    - Per-person inkomst (by_owner['user_X']['income'])
    - Per-person redan-betalda utgifter (by_owner['user_X']['expenses'])

    Två modeller:
    - 50/50: delar gemensamma utgifter lika
    - Prorata: proportionellt mot inkomst
    """
    gemensamt = by_owner.get("gemensamt", {})
    shared_expenses = float(gemensamt.get("expenses") or 0)

    # Samla personer (inte 'gemensamt')
    person_keys = [k for k in by_owner.keys() if k != "gemensamt"]
    if not person_keys:
        return []
    total_income = sum(
        float(by_owner[k].get("income") or 0) for k in person_keys
    )
    n = len(person_keys)
    out: list[TransferSuggestion] = []
    for key in person_keys:
        bucket = by_owner[key]
        income = float(bucket.get("income") or 0)
        already = float(bucket.get("expenses") or 0)
        share = (income / total_income) if total_income > 0 else (1 / n)
        out.append(
            TransferSuggestion(
                person_name=_pretty_owner_key(key, users_by_id),
                income=income,
                income_share_pct=round(share * 100, 1),
                fair_equal=round(shared_expenses / n, 0) if n > 0 else 0.0,
                fair_prorata=round(shared_expenses * share, 0),
                already_paid=already,
            )
        )
    out.sort(key=lambda t: -t.income)
    return out


# ---------- Rendering ----------


def render_pdf(data: MonthlyReportData) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=f"Hembudget — {data.month}",
        author="Hembudget",
    )
    styles = getSampleStyleSheet()
    h_title = ParagraphStyle(
        "HTitle",
        parent=styles["Title"],
        fontSize=22,
        leading=26,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=2,
        alignment=TA_LEFT,
    )
    h_sub = ParagraphStyle(
        "HSub",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#64748b"),
        alignment=TA_LEFT,
    )
    h_section = ParagraphStyle(
        "HSection",
        parent=styles["Heading2"],
        fontSize=13,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=8,
        spaceAfter=4,
    )
    body = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontSize=9.5,
        textColor=colors.HexColor("#334155"),
        leading=12,
    )
    hint = ParagraphStyle(
        "Hint",
        parent=styles["Normal"],
        fontSize=8.5,
        textColor=colors.HexColor("#64748b"),
        leading=11,
    )

    story: list = []

    # 1. Header
    story.append(
        Paragraph(
            f"Månadsrapport — {_format_month_label(data.month)}",
            h_title,
        )
    )
    story.append(
        Paragraph(
            f"Genererad {data.generated_at.strftime('%Y-%m-%d %H:%M')} · Hembudget",
            h_sub,
        )
    )
    story.append(Spacer(1, 8))

    # 2. KPI-ruta
    story.append(_kpi_box(data.summary))
    story.append(Spacer(1, 14))

    # 3+4. Två piecharts sida vid sida (2-col table)
    exp_labels = [p[0] for p in data.expense_slices]
    exp_values = [p[1] for p in data.expense_slices]
    inc_labels = [p[0] for p in data.income_slices]
    inc_values = [p[1] for p in data.income_slices]

    pie_exp = charts.pie_chart(
        exp_labels, exp_values,
        title="Utgifter per kategori",
        palette=charts.DEFAULT_PALETTE,
    )
    pie_inc = charts.pie_chart(
        inc_labels, inc_values,
        title="Inkomst per person",
        palette=charts.PERSON_PALETTE,
    )
    img_exp = Image(io.BytesIO(pie_exp), width=87 * mm, height=62 * mm)
    img_inc = Image(io.BytesIO(pie_inc), width=87 * mm, height=62 * mm)
    pie_tbl = Table(
        [[img_exp, img_inc]],
        colWidths=[90 * mm, 90 * mm],
    )
    pie_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(pie_tbl)
    story.append(Spacer(1, 12))

    # 5. Transfer-förslag
    if data.transfers:
        story.append(Paragraph("Överföring till gemensamt konto", h_section))
        story.append(
            Paragraph(
                "Två modeller för hur ni kan dela månadens gemensamma "
                "utgifter. <b>50/50</b> delar lika. <b>Prorata</b> delar "
                "proportionellt mot inkomst — den som tjänar mer bidrar mer.",
                hint,
            )
        )
        story.append(Spacer(1, 4))
        story.append(_transfers_table(data.transfers))
        story.append(Spacer(1, 12))

    # 6. Budget vs utfall — chart
    budget_rows = [
        l for l in data.summary.lines
        if l.kind != "income" and (l.planned != 0 or abs(float(l.actual)) >= 200)
    ]
    budget_rows.sort(key=lambda l: -abs(float(l.actual)))
    budget_rows = budget_rows[:12]
    if budget_rows:
        bar = charts.bar_chart_budget_vs_actual(
            [l.category for l in budget_rows],
            [abs(float(l.planned)) for l in budget_rows],
            [abs(float(l.actual)) for l in budget_rows],
            title="Budget vs utfall per kategori",
        )
        story.append(Image(io.BytesIO(bar), width=180 * mm, height=None))
        story.append(Spacer(1, 10))

    # 7. Prev-month-deltas — chart
    if data.deltas:
        delta_chart = charts.diff_chart_prev_month(
            [d[0] for d in data.deltas[:10]],
            [d[1] for d in data.deltas[:10]],
            title=f"Största förändringar mot {_format_month_label(_prev_month(data.month))}",
        )
        story.append(Image(io.BytesIO(delta_chart), width=180 * mm, height=None))
        story.append(Spacer(1, 10))

    # 8. Detaljerad kategoritabell
    story.append(PageBreak())
    story.append(Paragraph("Detaljerad budget", h_section))
    story.append(_detail_table(data.summary))

    # Fot
    story.append(Spacer(1, 12))
    story.append(
        Paragraph(
            "Genererad av Hembudget. Rapporten baseras på bokförda "
            "transaktioner per genereringsdagen. Belopp är avrundade till "
            "hela kronor.",
            hint,
        )
    )

    doc.build(story)
    return buf.getvalue()


def _kpi_box(summary: MonthSummary) -> Table:
    """4 färgade celler med stora siffror. Använder Table med egen style."""
    income = float(summary.income)
    expenses = float(summary.expenses)
    savings = float(summary.savings)
    rate = summary.savings_rate

    header_style = ParagraphStyle(
        "KpiLabel", fontSize=8, textColor=colors.HexColor("#475569"),
        alignment=TA_CENTER, leading=10, spaceAfter=2,
        fontName="Helvetica",
    )
    value_style_pos = ParagraphStyle(
        "KpiPos", fontSize=16, textColor=colors.HexColor("#047857"),
        alignment=TA_CENTER, leading=20, fontName="Helvetica-Bold",
    )
    value_style_neg = ParagraphStyle(
        "KpiNeg", fontSize=16, textColor=colors.HexColor("#b91c1c"),
        alignment=TA_CENTER, leading=20, fontName="Helvetica-Bold",
    )
    value_style_dark = ParagraphStyle(
        "KpiDark", fontSize=16, textColor=colors.HexColor("#0f172a"),
        alignment=TA_CENTER, leading=20, fontName="Helvetica-Bold",
    )

    cells = [
        [
            Paragraph("INKOMST", header_style),
            Paragraph(_format_sek(income), value_style_pos),
        ],
        [
            Paragraph("UTGIFTER", header_style),
            Paragraph(_format_sek(-expenses), value_style_neg),
        ],
        [
            Paragraph("SPARAT", header_style),
            Paragraph(
                _format_sek(savings),
                value_style_pos if savings >= 0 else value_style_neg,
            ),
        ],
        [
            Paragraph("SPARKVOT", header_style),
            Paragraph(
                f"{rate * 100:.1f} %",
                value_style_dark if rate >= 0 else value_style_neg,
            ),
        ],
    ]
    # Flytta till 1 rad × 4 kolumner där varje kolumn har två rader
    tbl = Table(
        [[c[0] for c in cells], [c[1] for c in cells]],
        colWidths=[45 * mm] * 4,
        rowHeights=[8 * mm, 14 * mm],
    )
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("BOX", (0, 0), (0, -1), 0.75, colors.HexColor("#e2e8f0")),
        ("BOX", (1, 0), (1, -1), 0.75, colors.HexColor("#e2e8f0")),
        ("BOX", (2, 0), (2, -1), 0.75, colors.HexColor("#e2e8f0")),
        ("BOX", (3, 0), (3, -1), 0.75, colors.HexColor("#e2e8f0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return tbl


def _transfers_table(transfers: list[TransferSuggestion]) -> Table:
    header = ["Person", "Inkomst", "Andel", "50/50-split", "Prorata", "Redan betalt"]
    rows: list[list] = [header]
    for t in transfers:
        rows.append([
            t.person_name,
            _format_sek(t.income),
            f"{t.income_share_pct:.0f} %",
            _format_sek(t.fair_equal),
            _format_sek(t.fair_prorata),
            _format_sek(t.already_paid),
        ])
    tbl = Table(rows, colWidths=[40*mm, 28*mm, 16*mm, 30*mm, 30*mm, 28*mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
            colors.white, colors.HexColor("#f8fafc"),
        ]),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return tbl


def _detail_table(summary: MonthSummary) -> Table:
    """Alla kategori-rader, grupperade per huvudgrupp. Diff-kolumnen får
    färg: röd om utgift > budget, grön om under."""
    # Gruppera via samma logik som frontend
    lines_by_group: dict[str, list] = {}
    for l in summary.lines:
        key = "Inkomster" if l.kind == "income" else (l.group or "Övrigt")
        lines_by_group.setdefault(key, []).append(l)

    # Sortering: inkomster sist, annars efter grupp-namn
    def _group_order(g: str) -> tuple[int, str]:
        return (1 if g == "Inkomster" else 0, g)

    rows: list[list] = [["Kategori", "Budget", "Utfall", "Diff", "Progress"]]
    style_cmds: list[tuple] = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]

    row_idx = 1
    for group in sorted(lines_by_group.keys(), key=_group_order):
        group_lines = lines_by_group[group]
        # Grupp-rubrik
        planned_sum = sum(float(l.planned) for l in group_lines)
        actual_sum = sum(float(l.actual) for l in group_lines)
        diff_sum = sum(float(l.diff) for l in group_lines)
        rows.append([
            group.upper(),
            _format_sek(planned_sum),
            _format_sek(actual_sum),
            _format_sek(diff_sum),
            "",
        ])
        style_cmds.append(("BACKGROUND", (0, row_idx), (-1, row_idx),
                           colors.HexColor("#e2e8f0")))
        style_cmds.append(("FONTNAME", (0, row_idx), (-1, row_idx),
                           "Helvetica-Bold"))
        row_idx += 1

        for l in group_lines:
            planned = float(l.planned)
            actual = float(l.actual)
            diff = float(l.diff)
            progress = (l.progress_pct or 0) if l.planned != 0 else 0
            rows.append([
                f"   {l.category}",
                _format_sek(planned) if planned != 0 else "—",
                _format_sek(actual),
                _format_sek(diff) if planned != 0 else "—",
                f"{progress:.0f} %" if planned != 0 else "",
            ])
            # Färga diff röd om negativ, grön om positiv (ur budget-perspektivet)
            if planned != 0:
                diff_color = (
                    colors.HexColor("#047857") if diff >= 0
                    else colors.HexColor("#b91c1c")
                )
                style_cmds.append(
                    ("TEXTCOLOR", (3, row_idx), (3, row_idx), diff_color)
                )
            # Progress-färg
            if planned != 0:
                if progress > 100:
                    pct_color = colors.HexColor("#b91c1c")
                elif progress > 80:
                    pct_color = colors.HexColor("#b45309")
                else:
                    pct_color = colors.HexColor("#047857")
                style_cmds.append(
                    ("TEXTCOLOR", (4, row_idx), (4, row_idx), pct_color)
                )
            row_idx += 1

    tbl = Table(rows, colWidths=[58*mm, 28*mm, 28*mm, 28*mm, 22*mm])
    tbl.setStyle(TableStyle(style_cmds))
    return tbl
