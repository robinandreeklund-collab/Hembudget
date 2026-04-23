"""Överföringsplan — framåtriktad månadsrapport för utskick.

Skillnad mot monthly_pdf.py:
- Monthly = bakåtblick på passerad månad (vad blev av pengarna)
- Upcoming = framåtblick på nästa månad (hur mycket behöver vi, vem betalar vad)

Designad för att skickas till partnern så hon ser:
1. Förväntad inkomst (per person)
2. Kända kommande fakturor (gemensamma)
3. Lån (ränta + amortering)
4. Hennes föreslagna överföring — både 50/50 och prorata

Vi återanvänder /upcoming/forecast-datan (samma siffror som
/upcoming-sidan visar) så inget räknas två gånger.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image, PageBreak, Paragraph, SimpleDocTemplate,
    Spacer, Table, TableStyle,
)
from sqlalchemy.orm import Session

from . import charts


SWEDISH_MONTHS = [
    "januari", "februari", "mars", "april", "maj", "juni",
    "juli", "augusti", "september", "oktober", "november", "december",
]


def _format_month_label(month: str) -> str:
    y, m = map(int, month.split("-"))
    return f"{SWEDISH_MONTHS[m - 1]} {y}"


def _format_sek(amount: float | Decimal | int) -> str:
    n = float(amount)
    s = f"{abs(n):,.0f}".replace(",", " ")
    return f"{'-' if n < 0 else ''}{s} kr"


@dataclass
class PersonShare:
    """En persons del av månadens gemensamma kostnader."""
    name: str
    income: float
    income_share_pct: float
    fair_equal: float  # 50/50-delad
    fair_prorata: float  # proportionell mot inkomst


@dataclass
class UpcomingReportData:
    month: str
    generated_at: datetime
    period_start: date | None
    period_end: date | None
    salary_cycle_start_day: int

    # Prognos-totaler (från /upcoming/forecast)
    expected_income: float
    upcoming_bills: float
    loan_scheduled: float
    avg_fixed_expenses: float
    after_known: float  # Lön - fakturor - lån (ignorerar variabla)

    # Per-person
    shares: list[PersonShare] = field(default_factory=list)

    # Bill-lista för bilaga
    bills: list[dict] = field(default_factory=list)
    incomes: list[dict] = field(default_factory=list)


def build_upcoming_data(
    session: Session, month: str,
) -> UpcomingReportData:
    """Beräkna all data för rapporten genom att återanvända
    /upcoming/forecast-logiken — då stämmer siffrorna med UI:n."""
    from ..api.upcoming import monthly_forecast
    forecast = monthly_forecast(month=month, split_ratio=0.5, session=session)

    totals = forecast["totals"]
    income_by_owner = forecast["income_by_owner"]

    shares = _compute_shares(
        income_by_owner=income_by_owner,
        shared_cost=totals["upcoming_bills"] + totals["loan_scheduled"],
    )

    return UpcomingReportData(
        month=month,
        generated_at=datetime.now(),
        period_start=(
            date.fromisoformat(forecast["period_start"])
            if forecast.get("period_start") else None
        ),
        period_end=(
            date.fromisoformat(forecast["period_end"])
            if forecast.get("period_end") else None
        ),
        salary_cycle_start_day=forecast.get("salary_cycle_start_day", 1),
        expected_income=totals["expected_income"],
        upcoming_bills=totals["upcoming_bills"],
        loan_scheduled=totals["loan_scheduled"],
        avg_fixed_expenses=totals["avg_fixed_expenses"],
        after_known=totals["after_known_bills"],
        shares=shares,
        bills=forecast["upcoming_bills"],
        incomes=forecast["upcoming_incomes"],
    )


def _compute_shares(
    income_by_owner: dict[str, float],
    shared_cost: float,
) -> list[PersonShare]:
    """Dela upp shared_cost per person enligt 50/50 + prorata-modellerna."""
    if not income_by_owner:
        return []
    people = [
        (name, amt) for name, amt in income_by_owner.items()
        if name and name.lower() != "okänd"
    ]
    if not people:
        # Fallback: visa även Okänd om det är enda vi har
        people = list(income_by_owner.items())
    total_income = sum(amt for _, amt in people) or 0.0
    n = len(people)
    out: list[PersonShare] = []
    for name, amt in people:
        share = (amt / total_income) if total_income > 0 else (1 / n)
        out.append(PersonShare(
            name=name,
            income=amt,
            income_share_pct=round(share * 100, 1),
            fair_equal=round(shared_cost / n, 0) if n > 0 else 0.0,
            fair_prorata=round(shared_cost * share, 0),
        ))
    out.sort(key=lambda p: -p.income)
    return out


# ---------- Rendering ----------

def render_upcoming_pdf(data: UpcomingReportData) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
        title=f"Överföringsplan {data.month}",
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle(
        "h1", parent=styles["Title"], fontSize=22, alignment=TA_LEFT,
        textColor=colors.HexColor("#0f172a"), spaceAfter=4,
    )
    h_section = ParagraphStyle(
        "h2", parent=styles["Heading2"], fontSize=13,
        textColor=colors.HexColor("#0f172a"), spaceAfter=6,
    )
    meta = ParagraphStyle(
        "meta", parent=styles["Normal"], fontSize=9,
        textColor=colors.HexColor("#64748b"),
    )
    hint = ParagraphStyle(
        "hint", parent=styles["Normal"], fontSize=9,
        textColor=colors.HexColor("#475569"), spaceAfter=4,
    )
    body = ParagraphStyle(
        "body", parent=styles["Normal"], fontSize=10,
        textColor=colors.HexColor("#0f172a"), spaceAfter=4,
    )

    story: list = []

    # 1. Titel
    story.append(
        Paragraph(f"Överföringsplan — {_format_month_label(data.month)}", h1),
    )
    period_label = ""
    if data.period_start and data.period_end:
        period_label = (
            f" · Period {data.period_start.isoformat()} till "
            f"{(data.period_end).isoformat()}"
        )
    story.append(
        Paragraph(
            f"Genererad {data.generated_at.strftime('%Y-%m-%d %H:%M')}"
            f"{period_label}",
            meta,
        ),
    )
    story.append(Spacer(1, 10))

    # 2. Vänlig introduktion för partnern
    story.append(
        Paragraph(
            "Det här är en sammanställning av kommande månad — "
            "förväntad lön, kända fakturor och lån, samt hur mycket du "
            "behöver flytta över till det gemensamma kontot.",
            body,
        ),
    )
    story.append(Spacer(1, 10))

    # 3. KPI-ruta
    story.append(_kpi_box(data))
    story.append(Spacer(1, 12))

    # 4. Inkomst-donut
    if charts.HAS_MATPLOTLIB and data.shares:
        pie = charts.pie_chart(
            [s.name for s in data.shares],
            [s.income for s in data.shares],
            title=f"Förväntad lön — {_format_sek(data.expected_income)}",
            palette=charts.PERSON_PALETTE,
        )
        if pie is not None:
            story.append(_scaled_image(pie, max_width_mm=130))
            story.append(Spacer(1, 10))

    # 5. Din andel-tabellen
    story.append(Paragraph("Din andel att föra över", h_section))
    story.append(
        Paragraph(
            "Två modeller — välj den som passar er bäst. "
            "<b>50/50</b>: ni delar lika på gemensamma kostnader. "
            "<b>Prorata</b>: den som tjänar mer bidrar mer, proportionellt.",
            hint,
        ),
    )
    story.append(Spacer(1, 4))
    story.append(_share_table(data))
    story.append(Spacer(1, 8))
    story.append(
        Paragraph(
            f"<b>Flytta senast den dag lönen kommer</b> (dag "
            f"{data.salary_cycle_start_day} i månaden).",
            body,
        )
    )
    story.append(Spacer(1, 14))

    # 6. Vad omfattar det?
    story.append(
        Paragraph("Vad ska pengarna täcka?", h_section),
    )
    story.append(_cost_breakdown_table(data))
    story.append(Spacer(1, 14))

    # 7. Bilaga: fakturalista
    if data.bills:
        story.append(PageBreak())
        story.append(Paragraph("Bilaga: Kommande fakturor", h_section))
        story.append(
            Paragraph(
                f"{len(data.bills)} fakturor "
                f"till en total summa av {_format_sek(data.upcoming_bills)}.",
                meta,
            ),
        )
        story.append(Spacer(1, 6))
        story.append(_bills_table(data.bills))

    doc.build(story)
    return buf.getvalue()


def _scaled_image(png_bytes: bytes, max_width_mm: float) -> Image:
    """Samma metod som monthly_pdf._scaled_image — proportionell skalning
    med aspect ratio via PIL, undviker LayoutError."""
    buf = io.BytesIO(png_bytes)
    try:
        from PIL import Image as PILImage
        buf.seek(0)
        pil = PILImage.open(buf)
        w_px, h_px = pil.size
        buf.seek(0)
    except Exception:
        w_px, h_px = 1280, 720
    target_w = max_width_mm * mm
    target_h = target_w * (h_px / w_px)
    return Image(buf, width=target_w, height=target_h)


def _kpi_box(data: UpcomingReportData) -> Table:
    shared_cost = data.upcoming_bills + data.loan_scheduled
    headers = [
        Paragraph("<b>FÖRVÄNTAD LÖN</b>", _kpi_label()),
        Paragraph("<b>GEMENSAMT ATT BETALA</b>", _kpi_label()),
        Paragraph("<b>LÅN (RÄNTA + AMORT.)</b>", _kpi_label()),
        Paragraph("<b>KVAR EFTER KÄNDA</b>", _kpi_label()),
    ]
    values = [
        Paragraph(_format_sek(data.expected_income), _kpi_value("#059669")),
        Paragraph(_format_sek(shared_cost), _kpi_value("#dc2626")),
        Paragraph(_format_sek(data.loan_scheduled), _kpi_value("#dc2626")),
        Paragraph(
            _format_sek(data.after_known),
            _kpi_value("#059669" if data.after_known >= 0 else "#dc2626"),
        ),
    ]
    tbl = Table([headers, values], colWidths=[45 * mm] * 4)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("TOPPADDING", (0, 1), (-1, 1), 10),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 10),
    ]))
    return tbl


def _kpi_label() -> ParagraphStyle:
    return ParagraphStyle(
        "kpi-label",
        fontName="Helvetica-Bold",
        fontSize=8,
        textColor=colors.HexColor("#64748b"),
        alignment=1,
    )


def _kpi_value(color_hex: str) -> ParagraphStyle:
    return ParagraphStyle(
        "kpi-value",
        fontName="Helvetica-Bold",
        fontSize=16,
        textColor=colors.HexColor(color_hex),
        alignment=1,
    )


def _share_table(data: UpcomingReportData) -> Table:
    header = ["Person", "Inkomst", "Andel", "50/50-del", "Prorata-del"]
    rows: list[list] = [header]
    for s in data.shares:
        rows.append([
            s.name,
            _format_sek(s.income),
            f"{s.income_share_pct:.0f} %",
            _format_sek(s.fair_equal),
            _format_sek(s.fair_prorata),
        ])
    tbl = Table(
        rows,
        colWidths=[45 * mm, 35 * mm, 20 * mm, 35 * mm, 35 * mm],
    )
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
            colors.white, colors.HexColor("#f8fafc"),
        ]),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return tbl


def _cost_breakdown_table(data: UpcomingReportData) -> Table:
    rows: list[list] = [
        ["Kategori", "Belopp", "Kommentar"],
        [
            "Kommande fakturor",
            _format_sek(data.upcoming_bills),
            f"{len(data.bills)} st — se bilaga",
        ],
        [
            "Lån (ränta + amortering)",
            _format_sek(data.loan_scheduled),
            "Enligt lånescheman",
        ],
    ]
    total = data.upcoming_bills + data.loan_scheduled
    rows.append([
        "TOTALT att dela",
        _format_sek(total),
        "",
    ])
    tbl = Table(rows, colWidths=[60 * mm, 40 * mm, 70 * mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#fef3c7")),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ALIGN", (2, 0), (2, -1), "LEFT"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return tbl


def _bills_table(bills: list[dict]) -> Table:
    bills_sorted = sorted(bills, key=lambda b: b["expected_date"])
    rows: list[list] = [["Datum", "Faktura", "Belopp"]]
    for b in bills_sorted:
        rows.append([
            b.get("expected_date", "—"),
            b.get("name") or "—",
            _format_sek(b.get("amount") or 0),
        ])
    tbl = Table(rows, colWidths=[25 * mm, 115 * mm, 35 * mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (2, 0), (2, -1), "RIGHT"),
        ("ALIGN", (0, 0), (1, -1), "LEFT"),
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
