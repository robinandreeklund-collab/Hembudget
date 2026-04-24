"""Generera portfolio-PDF för en elev:
- Elevens profil
- Mastery per kompetens
- Alla reflektioner med fråga, svar, lärarens feedback, rubric-betyg
"""
from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)


STYLES = getSampleStyleSheet()
H1 = ParagraphStyle(
    "H1", parent=STYLES["Title"], fontSize=22, spaceAfter=6,
    textColor=colors.HexColor("#0f172a"),
)
H2 = ParagraphStyle(
    "H2", parent=STYLES["Heading2"], fontSize=14, spaceBefore=18,
    spaceAfter=6, textColor=colors.HexColor("#0ea5e9"),
)
H3 = ParagraphStyle(
    "H3", parent=STYLES["Heading3"], fontSize=12, spaceBefore=10,
    spaceAfter=4, textColor=colors.HexColor("#0f172a"),
)
BODY = ParagraphStyle(
    "Body", parent=STYLES["BodyText"], fontSize=10, leading=14,
)
META = ParagraphStyle(
    "Meta", parent=STYLES["Normal"], fontSize=9,
    textColor=colors.HexColor("#64748b"),
)


def build_portfolio_pdf(
    *,
    student,  # Student-objekt från master-DB
    profile,  # StudentProfile
    mastery_rows: list[dict],  # [{competency:{name,level}, mastery, evidence_count}]
    reflections: list[dict],  # [{module_title, step_title, step_question, reflection, teacher_feedback, rubric, rubric_scores, completed_at}]
    modules_progress: list[dict],  # [{title, completed, total}]
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=f"Portfolio {student.display_name}",
        author="Ekonomilabbet",
    )
    story: list = []

    # Header
    story.append(Paragraph("Portfolio – Ekonomilabbet", H1))
    story.append(Paragraph(
        f"<b>{student.display_name}</b>"
        + (f" · {student.class_label}" if student.class_label else ""),
        BODY,
    ))
    story.append(Paragraph(
        f"Genererad {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}", META,
    ))

    # Profil-box
    story.append(Spacer(1, 8))
    profile_data = [
        ["Yrke", profile.profession],
        ["Arbetsgivare", profile.employer],
        ["Bruttolön", f"{profile.gross_salary_monthly:,} kr/mån".replace(",", " ")],
        ["Nettolön", f"{profile.net_salary_monthly:,} kr/mån".replace(",", " ")],
        ["Personlighet", profile.personality],
        ["Stad", profile.city],
        ["Boende", f"{profile.housing_type} ({profile.housing_monthly:,} kr)".replace(",", " ")],
    ]
    if profile.children_ages:
        profile_data.append([
            "Familj",
            f"Sambo + {len(profile.children_ages)} barn ({', '.join(str(a) for a in profile.children_ages)} år)",
        ])
    tbl = Table(profile_data, colWidths=[40 * mm, 120 * mm])
    tbl.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#64748b")),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
    ]))
    story.append(tbl)

    # Modulgenomgångar
    if modules_progress:
        story.append(Paragraph("Kursplan", H2))
        rows = [["Modul", "Klara steg", "Status"]]
        for m in modules_progress:
            status = (
                "✓ Klar" if m["completed"] >= m["total"] and m["total"] > 0
                else (f"{m['completed']}/{m['total']}" if m["total"] > 0 else "—")
            )
            rows.append([m["title"], f"{m['completed']}/{m['total']}", status])
        tbl = Table(rows, colWidths=[100 * mm, 30 * mm, 30 * mm])
        tbl.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
        ]))
        story.append(tbl)

    # Mastery-diagram
    if mastery_rows:
        story.append(Paragraph("Färdigheter", H2))
        for row in mastery_rows:
            name = row["competency"]["name"]
            pct = int(row["mastery"] * 100)
            evidence = row["evidence_count"]
            # Fake-bar med en tabell-row
            bar_filled = "█" * max(1, int(pct / 5))
            bar_empty = "░" * max(0, 20 - int(pct / 5))
            story.append(Paragraph(
                f"<b>{name}</b> — {pct}% ({evidence} bevis)<br/>"
                f"<font face='Courier' size='9'>{bar_filled}{bar_empty}</font>",
                BODY,
            ))

    # Reflektioner
    if reflections:
        story.append(Paragraph("Reflektioner", H2))
        for r in reflections:
            story.append(Paragraph(
                f"<b>{r.get('module_title', '—')}</b> · {r.get('step_title', '—')}",
                H3,
            ))
            if r.get("completed_at"):
                story.append(Paragraph(
                    f"Skrivet: {r['completed_at']}", META,
                ))
            if r.get("step_question"):
                story.append(Paragraph(
                    f"<i>Frågan:</i> {_escape(r['step_question'])}",
                    BODY,
                ))
            story.append(Paragraph(
                f"<i>Ditt svar:</i><br/>{_escape(r.get('reflection', ''))}",
                BODY,
            ))
            if r.get("teacher_feedback"):
                story.append(Paragraph(
                    f"<i>Lärarens feedback:</i><br/>"
                    f"<font color='#0ea5e9'>{_escape(r['teacher_feedback'])}</font>",
                    BODY,
                ))
            if r.get("rubric") and r.get("rubric_scores"):
                parts = []
                for crit in r["rubric"]:
                    idx = r["rubric_scores"].get(crit["key"])
                    if idx is not None and idx < len(crit["levels"]):
                        parts.append(f"<b>{crit['name']}:</b> {crit['levels'][idx]}")
                if parts:
                    story.append(Paragraph(
                        "<i>Bedömning:</i> " + " · ".join(parts),
                        BODY,
                    ))
            story.append(Spacer(1, 4))

    doc.build(story)
    return buf.getvalue()


def _escape(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
    )
