from __future__ import annotations

import io

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..budget.monthly import MonthlyBudgetService
from .deps import db, require_auth

router = APIRouter(prefix="/reports", tags=["reports"], dependencies=[Depends(require_auth)])


@router.get("/month/{month}/excel")
def excel_report(month: str, session: Session = Depends(db)) -> Response:
    try:
        from openpyxl import Workbook
    except ImportError:
        return Response(status_code=501, content="openpyxl ej installerat")

    summary = MonthlyBudgetService(session).summary(month)
    wb = Workbook()
    ws = wb.active
    ws.title = f"Budget {month}"
    ws.append(["Kategori", "Budgeterat", "Faktiskt", "Diff"])
    for l in summary.lines:
        ws.append([l.category, float(l.planned), float(l.actual), float(l.diff)])
    ws.append([])
    ws.append(["Inkomst", "", float(summary.income), ""])
    ws.append(["Utgifter", "", float(summary.expenses), ""])
    ws.append(["Sparande", "", float(summary.savings), ""])
    ws.append(["Sparkvot", "", summary.savings_rate, ""])

    buf = io.BytesIO()
    wb.save(buf)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="hembudget-{month}.xlsx"'},
    )


@router.get("/month/{month}/pdf")
def pdf_report(month: str, session: Session = Depends(db)) -> Response:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib import colors
    except ImportError:
        return Response(status_code=501, content="reportlab ej installerat")

    summary = MonthlyBudgetService(session).summary(month)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    styles = getSampleStyleSheet()
    story = [
        Paragraph(f"Hembudget — {month}", styles["Title"]),
        Spacer(1, 12),
        Paragraph(
            f"Inkomst: {float(summary.income):,.0f} kr | Utgifter: {float(summary.expenses):,.0f} kr"
            f" | Sparande: {float(summary.savings):,.0f} kr ({summary.savings_rate*100:.1f} %)",
            styles["Normal"],
        ),
        Spacer(1, 12),
    ]
    data = [["Kategori", "Budget", "Faktiskt", "Diff"]]
    for l in summary.lines:
        data.append([l.category, f"{float(l.planned):,.0f}", f"{float(l.actual):,.0f}",
                     f"{float(l.diff):,.0f}"])
    t = Table(data, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
    ]))
    story.append(t)
    doc.build(story)
    return Response(
        content=buf.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="hembudget-{month}.pdf"'},
    )
