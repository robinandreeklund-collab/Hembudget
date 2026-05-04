"""V2 · PDF-rendering av strukturerade fakturor.

Bygger på reportlab-stilen från teacher/pdfs.py men tar in vår
V2InvoiceData JSON-struktur. Generic — fungerar för alla fakturatyper
(el, mobil, bredband, hyra, BRF-avgift, bolån, drift, försäkring,
lokaltrafik).

Användning:
    pdf_bytes = render_v2_invoice_pdf(
        invoice_data, sender, subject, due_date, student_name,
    )

Returnerar bytes som streamas via /v2/postladan/{id}/pdf.
"""
from __future__ import annotations

import io
from datetime import date as _date
from decimal import Decimal
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


_STYLES = getSampleStyleSheet()
_H_TITLE = ParagraphStyle(
    "Title", parent=_STYLES["Title"], fontSize=20, spaceAfter=4,
    textColor=colors.HexColor("#0f172a"),
)
_H_SUB = ParagraphStyle(
    "Sub", parent=_STYLES["Normal"], fontSize=10,
    textColor=colors.HexColor("#475569"),
)
_H_TAG = ParagraphStyle(
    "Tag", parent=_STYLES["Normal"], fontSize=8,
    textColor=colors.HexColor("#94a3b8"),
)
_H_LABEL = ParagraphStyle(
    "Label", parent=_STYLES["Normal"], fontSize=9,
    textColor=colors.HexColor("#475569"),
)
_H_BIG = ParagraphStyle(
    "Big", parent=_STYLES["Normal"], fontSize=14, leading=18,
    textColor=colors.HexColor("#0f172a"),
)
_H_TOTAL = ParagraphStyle(
    "Total", parent=_STYLES["Normal"], fontSize=14, leading=18,
    textColor=colors.HexColor("#dc4c2b"),
)
_H_BODY = ParagraphStyle(
    "Body", parent=_STYLES["Normal"], fontSize=10, leading=14,
)
_H_FOOTER = ParagraphStyle(
    "Footer", parent=_STYLES["Normal"], fontSize=8, leading=11,
    textColor=colors.HexColor("#94a3b8"),
)


def _kr(amount) -> str:
    if isinstance(amount, Decimal):
        amount = float(amount)
    sign = "-" if amount < 0 else ""
    abs_amount = abs(amount)
    s = f"{abs_amount:,.2f}".replace(",", " ").replace(".", ",")
    return f"{sign}{s} kr"


# Mappa kind → svensk titel + företags-org-nr
_KIND_TITLE: dict[str, str] = {
    "el": "Elräkning",
    "mobil": "Mobilräkning",
    "bredband": "Bredbandsräkning",
    "hyra": "Hyresavi",
    "brf_avgift": "Månadsavgift bostadsrätt",
    "bolan": "Bolåneavi · ränta + amortering",
    "drift_villa": "Driftavi villa",
    "forsakring": "Försäkringspremie",
    "lokaltrafik": "Periodbiljett",
    "annan": "Faktura",
}


def _org_no(sender: str) -> str:
    """Stabil-mock org-nr per leverantör."""
    import hashlib as _hl
    h = _hl.sha256(sender.encode()).hexdigest()
    a = int(h[:6], 16) % 1000000
    b = int(h[6:10], 16) % 10000
    return f"{a:06d}-{b:04d}"


def render_v2_invoice_pdf(
    invoice: dict,
    *,
    sender: str,
    subject: str,
    due_date: Optional[_date],
    student_name: str = "Eleven",
    student_address: Optional[str] = None,
) -> bytes:
    """Rendera en strukturerad faktura som PDF.

    `invoice` matchar invoice_data-JSON:en på MailItem (kind, rows,
    subtotal, moms, total, ocr, bankgiro, period, extra-dict).
    Returnerar PDF-bytes som kan streamas direkt via FastAPI Response.
    """
    buf = io.BytesIO()
    kind = str(invoice.get("kind", "annan"))
    title_meta = _KIND_TITLE.get(kind, "Faktura")
    invoice_no = str(invoice.get("invoice_number", "—"))

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
        title=f"{title_meta} · {invoice_no}",
        author=sender,
    )

    story: list = []

    # === HEADER · avsändare + faktura-meta ===
    sender_block = [
        Paragraph(f"<b>{sender}</b>", _H_BIG),
        Paragraph(f"Org.nr {_org_no(sender)}", _H_TAG),
        Spacer(1, 4),
        Paragraph(title_meta, _H_SUB),
    ]
    period_start = invoice.get("period_start")
    period_end = invoice.get("period_end")
    period_str = "—"
    if period_start and period_end:
        period_str = f"{period_start} – {period_end}"

    meta_block = [
        Paragraph(f"<b>Fakturanummer</b>: {invoice_no}", _H_BODY),
        Paragraph(
            f"<b>Förfallodag</b>: "
            f"{due_date.isoformat() if due_date else '—'}",
            _H_BODY,
        ),
        Paragraph(f"<b>Period</b>: {period_str}", _H_BODY),
    ]
    ocr = invoice.get("ocr")
    bg = invoice.get("bankgiro")
    if ocr:
        meta_block.append(Paragraph(f"<b>OCR</b>: {ocr}", _H_BODY))
    if bg:
        meta_block.append(Paragraph(f"<b>Bankgiro</b>: {bg}", _H_BODY))

    header_table = Table(
        [[sender_block, meta_block]],
        colWidths=[90 * mm, 84 * mm],
    )
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 12))

    # === Mottagare ===
    addr = student_address or "Adress saknas"
    story.append(Paragraph(
        f"<b>Mottagare</b>: {student_name}", _H_BODY,
    ))
    story.append(Paragraph(addr, _H_LABEL))
    story.append(Spacer(1, 14))

    # === RADER ===
    story.append(Paragraph(f"<b>Specifikation</b>", _H_BIG))
    story.append(Spacer(1, 6))

    rows_table_data: list[list] = [
        ["Beskrivning", "Antal", "À-pris", "Belopp"],
    ]
    for r in invoice.get("rows", []):
        label = str(r.get("label", ""))
        qty = r.get("qty")
        unit = r.get("unit") or ""
        unit_price = r.get("unit_price")
        amount = float(r.get("amount", 0))
        qty_str = ""
        ap_str = ""
        if qty is not None:
            qty_str = f"{qty} {unit}".strip()
            if unit_price is not None:
                ap_str = _kr(unit_price)
        rows_table_data.append([label, qty_str, ap_str, _kr(amount)])

    # Subtotal · moms · total
    subtotal = float(invoice.get("subtotal", 0))
    moms = float(invoice.get("moms", 0))
    moms_rate = float(invoice.get("moms_rate", 0))
    total = float(invoice.get("total", 0))

    rows_table_data.append(["", "", "Summa exkl moms", _kr(subtotal)])
    if moms > 0:
        rows_table_data.append(
            ["", "", f"Moms {moms_rate:g} %", _kr(moms)],
        )
    rows_table_data.append(["", "", "TOTALT", _kr(total)])

    rows_table = Table(
        rows_table_data,
        colWidths=[80 * mm, 28 * mm, 28 * mm, 38 * mm],
        hAlign="LEFT",
    )
    rows_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#cbd5e1")),
        ("LINEABOVE", (0, -1), (-1, -1), 1.2, colors.HexColor("#dc4c2b")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, -1), (-1, -1), colors.HexColor("#dc4c2b")),
        ("FONTSIZE", (0, -1), (-1, -1), 12),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [
            colors.white, colors.HexColor("#fafafa"),
        ]),
    ]))
    story.append(rows_table)
    story.append(Spacer(1, 16))

    # === Pedagogisk info-ruta ===
    extra = invoice.get("extra") or {}
    info_lines: list[str] = []
    if extra.get("moms_note"):
        info_lines.append(f"<b>Moms-info</b>: {extra['moms_note']}")
    if extra.get("policy_notes"):
        info_lines.append(
            f"<b>Försäkringsvillkor</b>: {extra['policy_notes']}",
        )
    if extra.get("tip"):
        info_lines.append(f"<b>Tips</b>: {extra['tip']}")
    if info_lines:
        info_box = Table(
            [[Paragraph("<br/>".join(info_lines), _H_BODY)]],
            colWidths=[174 * mm],
        )
        info_box.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fff7ed")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#fdba74")),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(info_box)
        story.append(Spacer(1, 14))

    # === Betalningsinfo ===
    pay_lines = [
        Paragraph("<b>Betalning</b>", _H_BODY),
    ]
    if bg:
        pay_lines.append(Paragraph(
            f"Betala via banken till bankgiro <b>{bg}</b>.", _H_LABEL,
        ))
    if ocr:
        pay_lines.append(Paragraph(
            f"Använd OCR-referens <b>{ocr}</b>.", _H_LABEL,
        ))
    pay_lines.append(Paragraph(
        f"Senast på förfallodagen <b>"
        f"{due_date.isoformat() if due_date else '—'}</b>.",
        _H_LABEL,
    ))
    pay_lines.append(Paragraph(
        "Vid försenad betalning: påminnelseavgift 60-95 kr + ränta "
        "enl. räntelagen.",
        _H_FOOTER,
    ))
    story.extend(pay_lines)
    story.append(Spacer(1, 18))

    # === Footer ===
    story.append(Paragraph(
        "Detta är en pedagogiskt simulerad faktura · "
        "Ekonomilabbet sandbox · ingen riktig betalning krävs.",
        _H_FOOTER,
    ))

    doc.build(story)
    return buf.getvalue()
