"""Heuristisk parser för svenska energi-, bredbands- och VA-fakturor.

Stöd:
- **Hjo Energi** — el + vatten + internet på samma faktura. Vi extraherar
  el-delen (kWh + el-summa) separat från vatten/bredband. Bonus: tabellen
  'Förbrukningsstatistik' har 12+ månaders kWh-historik som vi kan spara.
- **Telinet** — rörligt elavtal (inte bredband — tidigare version gissade
  fel baserat på företagsnamnet).
- **Tibber** — PDF-faktura backup (Tibber API föredras).
- **Vattenfall / E.ON / Fortum** — el, generisk parser.
- **Hjo Kommun** — separat VA-faktura, vatten i m³.

Extraherar:
- supplier + meter_type
- period_start / period_end
- consumption + enhet (kWh / GB / m³)
- cost_kr (totalbelopp inkl. moms för den valda mätartypen)
- Bonus för Hjo Energi: history-tabell med kWh per månad

Filosofi: hellre supplier-specifik logik än en generisk gissning. Varje
faktura från samma bolag har konsistent layout — kör en dedikerad parser
som kan den exakt, och låt generisk fallback hantera okända format.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional

import pypdfium2 as pdfium


@dataclass
class UtilityPdfResult:
    supplier: str = "unknown"
    meter_type: str = "electricity"
    # 'grid' (nätleverantör — Hjo Elnät, Vattenfall Elnät)
    # 'energy' (elhandel — Telinet, Tibber, E.ON, Fortum)
    # 'total' (en kombinerad faktura, ingen separat nätdel, eller okänt)
    meter_role: str = "total"

    period_start: Optional[date] = None
    period_end: Optional[date] = None

    consumption: Optional[Decimal] = None
    consumption_unit: Optional[str] = None

    cost_kr: Optional[Decimal] = None

    raw_text: str = ""
    parse_errors: list[str] = field(default_factory=list)
    # Bonus: extra månadsvis förbrukningshistorik (t.ex. Hjo Energi ger
    # 12 mån kWh per faktura). Används för att fylla på gamla månader.
    history: list["HistoryPoint"] = field(default_factory=list)


@dataclass
class HistoryPoint:
    """En rad i en leverantörs månadsstatistik-tabell — bara kWh, inget
    kr-belopp (det saknas i de flesta utskrivna tabeller)."""
    year: int
    month: int
    kwh: Decimal


SWEDISH_MONTHS = {
    "januari": 1, "februari": 2, "mars": 3, "april": 4,
    "maj": 5, "juni": 6, "juli": 7, "augusti": 8,
    "september": 9, "oktober": 10, "november": 11, "december": 12,
    # kortformer som Hjo Energi använder i historik-tabellen
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "maj_": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "okt": 10, "nov": 11, "dec": 12,
}
# "maj" kan inte ha två värden i dict — hanteras separat


def _to_decimal(s: str) -> Optional[Decimal]:
    s = s.strip().replace(" ", "").replace(" ", "")
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def _to_date(s: str) -> Optional[date]:
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", s.strip())
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.match(r"(\d{4})-(\d{1,2})$", s.strip())
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), 1)
        except ValueError:
            return None
    return None


def _last_day_of_month(year: int, month: int) -> int:
    from calendar import monthrange
    return monthrange(year, month)[1]


def extract_text(pdf_bytes: bytes) -> str:
    pdf = pdfium.PdfDocument(pdf_bytes)
    return "\n".join(p.get_textpage().get_text_range() for p in pdf)


def detect_supplier_and_type(text: str) -> tuple[str, str]:
    """Returnera (supplier, meter_type).

    Prioritetsordning: mer specifik leverantör först så att t.ex. en
    Hjo Energi-faktura som även nämner 'Hjo Kommun AB' för VA-delen
    inte klassas som kommunal-VA.
    """
    lower = text.lower()
    # Specifika bolag först. OBS: ordning är viktig — Telinet-fakturor
    # nämner "Nätleverantör: Hjo Elnät AB" i anläggningsuppgifterna, så
    # Telinet-checken måste komma FÖRE Hjo Elnät-matchningen. Hjo Energi
    # har 'hjoenergi.se'/'Hjo Elnät AB' i brevhuvudet men skriver aldrig
    # 'telinet', så den ordningen löser båda fallen.
    if "telinet" in lower:
        return ("telinet", "electricity")
    if "hjoenergi" in lower or "hjo energi" in lower or "hjo elnät" in lower:
        return ("hjo_energi", "electricity")
    if "tibber" in lower:
        return ("tibber", "electricity")
    if "vattenfall" in lower:
        if "vatten och avlopp" in lower or "va-avgift" in lower:
            return ("vattenfall", "water")
        return ("vattenfall", "electricity")
    if "fortum" in lower:
        return ("fortum", "electricity")
    if "e.on" in lower or re.search(r"\beon\b", lower):
        return ("eon", "electricity")
    if "fjärrvärme" in lower:
        return ("fjärrvärme", "heating")
    if "hjo kommun" in lower and (
        "vatten" in lower or "avlopp" in lower or "va " in lower
    ):
        return ("hjo_kommun", "water")
    return ("unknown", "electricity")


# ---------- Telinet-specifik parser ----------

def _parse_telinet(text: str, res: UtilityPdfResult) -> UtilityPdfResult:
    """Telinet rörligt-el-faktura. Karaktäristiska nyckelord:

    - 'Faktura <sv månad> - <sv månad> <år>' som periodrad
    - 'Under perioden har du förbrukat: NNN kWh'
    - 'Totalbelopp att betala: N NNN kr'
    """
    res.meter_type = "electricity"
    res.meter_role = "energy"  # Telinet säljer bara elhandelsdelen

    # Period: "Faktura 1 februari - 28 februari 2026" eller
    # "Faktura 1 februari - 29 februari 2028"
    m = re.search(
        r"Faktura\s+(\d{1,2})\s+(januari|februari|mars|april|maj|juni|juli|augusti|september|oktober|november|december)"
        r"\s*[-–—]\s*"
        r"(\d{1,2})\s+(januari|februari|mars|april|maj|juni|juli|augusti|september|oktober|november|december)"
        r"\s+(\d{4})",
        text,
        re.IGNORECASE,
    )
    if m:
        d1, mon1, d2, mon2, yr = m.groups()
        m1 = SWEDISH_MONTHS[mon1.lower()]
        m2 = SWEDISH_MONTHS[mon2.lower()]
        year = int(yr)
        try:
            # Om månaderna korsar årsskifte (dec-jan): första datumet får
            # föregående år. Telinet-fakturor är dock oftast inom en månad.
            year1 = year - 1 if m1 == 12 and m2 == 1 else year
            res.period_start = date(year1, m1, int(d1))
            res.period_end = date(year, m2, int(d2))
        except ValueError:
            res.parse_errors.append(f"Ogiltig period: {m.group(0)}")

    # Förbrukning: "Under perioden har du förbrukat: 2 285 kWh"
    m = re.search(
        r"Under\s+perioden\s+har\s+du\s+förbrukat[:\s]*([\d\s.,]+?)\s*kWh",
        text,
        re.IGNORECASE,
    )
    if m:
        v = _to_decimal(m.group(1))
        if v and v > 0:
            res.consumption = v
            res.consumption_unit = "kWh"

    # Totalbelopp — Telinet skriver det som "Totalbelopp att betala: 3 665 kr"
    # (ett ord 'Totalbelopp' — gamla regexet krävde whitespace efter).
    m = re.search(
        r"Totalbelopp\s+att\s+betala[:\s]*([\d\s.,]+?)\s*kr",
        text,
        re.IGNORECASE,
    )
    if m:
        v = _to_decimal(m.group(1))
        if v and v > 0:
            res.cost_kr = v
    # Fallback: bara "Totalbelopp: N kr" (på specifikationssidan)
    if res.cost_kr is None:
        m = re.search(
            r"Totalbelopp[:\s]*([\d\s.,]+?)\s*kr",
            text,
            re.IGNORECASE,
        )
        if m:
            v = _to_decimal(m.group(1))
            if v and v > 0:
                res.cost_kr = v
    return res


# ---------- Hjo Energi-specifik parser ----------

def _parse_hjo_energi(text: str, res: UtilityPdfResult) -> UtilityPdfResult:
    """Hjo Energi slår ihop el + vatten + internet på samma faktura. Vi
    extraherar el-delen (kWh + el-summa) primärt eftersom det är den
    meter_type användaren främst spårar. Totalkostnaden för el-delen
    hittas efter 'Elöverföring' och 'Summa'-raden innan Vatten-sektionen.

    PDF-layout (kort):
        Abonnemang NNNNNN-NNNNNN  31 dagar  ...  XXX.XX
        Elöverföring (avläst) NNNNNN-NNNNNN  N NNN  kWh  ...  YYY.YY
        Energiskatt N NNN  kWh ... ZZZ.ZZ
        Årlig ...
        Moms 25% på ...
        Summa  N NNN.NN             <-- el-summa
        Vatten
        ...
    """
    res.meter_type = "electricity"
    # Hjo Energi fakturerar elnätsavgiften (plus vatten + internet på
    # samma faktura) — inte energin själv. Kostnaden (elnätsdelen) och
    # förbrukningen (kWh) ska räknas som 'grid' så den inte dubbelräknas
    # mot Telinets energifaktura för samma månad.
    res.meter_role = "grid"

    # Period: "YYMMDD-YYMMDD" (Hjo skriver det kompakt utan århundrade)
    # Vi letar på Elöverföring-raden för att inte få VA-period.
    m = re.search(
        r"Elöverföring[^\n]*?(\d{2})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})",
        text,
    )
    if m:
        y1, mo1, d1, y2, mo2, d2 = m.groups()
        try:
            res.period_start = date(2000 + int(y1), int(mo1), int(d1))
            res.period_end = date(2000 + int(y2), int(mo2), int(d2))
        except ValueError:
            res.parse_errors.append(f"Ogiltig el-period: {m.group(0)}")
    # Backup: om Elöverföring-raden saknar datum, ta första YYMMDD-YYMMDD
    # som står efter 'Abonnemang'.
    if res.period_start is None:
        m = re.search(
            r"Abonnemang[^\n]*?(\d{2})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})",
            text,
        )
        if m:
            y1, mo1, d1, y2, mo2, d2 = m.groups()
            try:
                res.period_start = date(2000 + int(y1), int(mo1), int(d1))
                res.period_end = date(2000 + int(y2), int(mo2), int(d2))
            except ValueError:
                pass

    # Förbrukning: "Elöverföring (avläst) NNNNNN-NNNNNN <NEWLINE> 1 531 <NEWLINE> kWh"
    # pdfium splitar tabellceller på olika rader, så talet står ensamt
    # på egen rad strax före en 'kWh'-rad. Vi letar efter ett tal
    # (ev. tusenseparator med mellanslag) direkt följt av 'kWh' på
    # efterföljande rad — periodnumret '260331' ligger på samma rad
    # som 'Elöverföring' och matchar inte detta mönster.
    eo_idx = text.lower().find("elöverföring")
    if eo_idx >= 0:
        window = text[eo_idx : eo_idx + 400]
        m = re.search(
            r"^\s*(\d[\d\s]*?\d|\d)\s*$[\r\n]+\s*kWh\b",
            window,
            re.MULTILINE,
        )
        if m:
            v = _to_decimal(m.group(1))
            if v and v > 0:
                res.consumption = v
                res.consumption_unit = "kWh"

    # El-delsumma: efter Elöverföring finns 'Summa' strax innan 'Vatten'.
    # Layout: ... Moms 25% på 1 378,70 \n 344,68 \n Summa \n 1 723,38 \n Vatten
    # Vi tar texten mellan 'Elöverföring' och nästa 'Vatten'/'Internet'-sektion
    # och hittar 'Summa' där.
    if eo_idx >= 0:
        vatten_idx = text.lower().find("vatten", eo_idx + 1)
        internet_idx = text.lower().find("internet/kabeltv", eo_idx + 1)
        end_markers = [i for i in (vatten_idx, internet_idx) if i > 0]
        end_idx = min(end_markers) if end_markers else eo_idx + 2000
        el_section = text[eo_idx:end_idx]
        m = re.search(
            r"Summa\s*\n?\s*([\d\s.,]+?)(?:\s*\n|\s{2,}|$)",
            el_section,
        )
        if m:
            v = _to_decimal(m.group(1))
            if v and v > 0:
                res.cost_kr = v

    # Om el-summan saknas, fallback till totalbeloppet 'Att betala'
    if res.cost_kr is None:
        m = re.search(
            r"Att\s+betala[\s\n]*([\d\s.,]+?)\s*(?:SEK|kr|\n)",
            text,
            re.IGNORECASE,
        )
        # Försök också utan unit (Hjo skriver 'SEK' före, inte efter talet)
        if not m:
            m = re.search(
                r"(?:Öresutjämning[^\n]*\n[^\n]*\n)?"
                r"(\d{4}-\d{2}-\d{2})\s*\n?\s*([\d\s]+?[,.][\d]{2})\s*SEK",
                text,
                re.IGNORECASE,
            )
            if m:
                v = _to_decimal(m.group(2))
                if v and v > 0:
                    res.cost_kr = v
        else:
            v = _to_decimal(m.group(1))
            if v and v > 0:
                res.cost_kr = v

    # Historik-tabell: 'mar-25 1 587 10%' per månad. Vi extraherar alla.
    history_start = text.lower().find("förbrukningsstatistik")
    if history_start >= 0:
        # Läs de följande 1200 tecknen; månadsnamn-mönster med kort form
        hist_section = text[history_start : history_start + 1500]
        short_months = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "maj": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "okt": 10, "nov": 11, "dec": 12,
        }
        # Layout: 'mar-25 1 587 10% apr-25 1 124 7% ...'
        # Greedy-match på kWh-talet (ev. med tusenseparator-space), följt
        # av obligatorisk '<procenttal>%' så vi vet var talet slutar.
        for m in re.finditer(
            r"(jan|feb|mar|apr|maj|jun|jul|aug|sep|okt|nov|dec)-(\d{2})"
            r"\s+(\d(?:[\d\s]*\d)?)\s+\d+\s*%",
            hist_section,
            re.IGNORECASE,
        ):
            mon_str, yr_str, kwh_str = m.groups()
            mon = short_months.get(mon_str.lower())
            if mon is None:
                continue
            kwh = _to_decimal(kwh_str)
            if kwh is None or kwh <= 0:
                continue
            res.history.append(
                HistoryPoint(
                    year=2000 + int(yr_str),
                    month=mon,
                    kwh=kwh,
                )
            )

    return res


# ---------- Generisk parser (fallback för övriga leverantörer) ----------

def _parse_generic(text: str, res: UtilityPdfResult) -> UtilityPdfResult:
    """Fallback med de gamla regexarna för leverantörer vi inte har
    dedikerad logik för (Vattenfall, E.ON, Fortum etc)."""
    res.period_start, res.period_end = _extract_period(text)
    res.cost_kr = _extract_total_cost(text)

    if res.meter_type in ("electricity", "heating"):
        res.consumption = _extract_kwh(text)
        res.consumption_unit = "kWh" if res.consumption else None
    elif res.meter_type == "broadband":
        res.consumption = _extract_gb(text)
        res.consumption_unit = "GB" if res.consumption else None
    elif res.meter_type == "water":
        m = re.search(r"(\d{1,3}(?:[,\.]\d+)?)\s*m[³3]", text)
        if m:
            res.consumption = _to_decimal(m.group(1))
            res.consumption_unit = "m³"
    return res


def _extract_period(text: str) -> tuple[Optional[date], Optional[date]]:
    m = re.search(
        r"[Pp]eriod[:\s]*(\d{4}-\d{1,2}-\d{1,2})\s*[-–—]\s*(\d{4}-\d{1,2}-\d{1,2})",
        text,
    )
    if m:
        return _to_date(m.group(1)), _to_date(m.group(2))
    m = re.search(
        r"[Ff]örbrukningsperiod[:\s]*(\d{4}-\d{1,2}-\d{1,2})\s*(?:till|[-–—])\s*(\d{4}-\d{1,2}-\d{1,2})",
        text,
    )
    if m:
        return _to_date(m.group(1)), _to_date(m.group(2))
    m = re.search(
        r"\b(\d{4}-\d{1,2}-\d{1,2})\s*[-–—]\s*(\d{4}-\d{1,2}-\d{1,2})\b",
        text,
    )
    if m:
        return _to_date(m.group(1)), _to_date(m.group(2))
    m = re.search(
        r"\b(januari|februari|mars|april|maj|juni|juli|augusti|september|oktober|november|december)\s+(\d{4})\b",
        text,
        re.IGNORECASE,
    )
    if m:
        mon = SWEDISH_MONTHS[m.group(1).lower()]
        year = int(m.group(2))
        return date(year, mon, 1), date(year, mon, _last_day_of_month(year, mon))
    return None, None


def _extract_kwh(text: str) -> Optional[Decimal]:
    matches = re.findall(
        r"(\d{1,3}(?:[ \. ]\d{3})*(?:[,\.]\d+)?)\s*kWh",
        text,
    )
    if not matches:
        return None
    vals = [_to_decimal(m) for m in matches]
    vals = [v for v in vals if v is not None and v > 0]
    if not vals:
        return None
    return max(vals)


def _extract_gb(text: str) -> Optional[Decimal]:
    matches = re.findall(r"(\d{1,3}(?:[,\.]\d+)?)\s*GB", text)
    if not matches:
        return None
    vals = [_to_decimal(m) for m in matches]
    vals = [v for v in vals if v is not None and v > 0]
    if not vals:
        return None
    return max(vals)


def _extract_total_cost(text: str) -> Optional[Decimal]:
    patterns = [
        r"[Tt]otalbelopp\s+att\s+betala[:\s]*([\d\s,.]+?)\s*kr",
        r"[Tt]otalbelopp[:\s]*([\d\s,.]+?)\s*kr",
        r"[Aa]tt\s+betala[:\s]*([\d\s,.]+?)\s*kr",
        r"[Ss]umma\s+att\s+betala[:\s]*([\d\s,.]+?)\s*kr",
        r"[Ss]lutsumma[:\s]*([\d\s,.]+?)\s*kr",
        r"[Bb]elopp[:\s]*([\d\s,.]+?)\s*SEK",
        # Hjo-style: 'Att betala\n2026-04-30\n2 709,46 677,37 0,17 SEK 3 387,00'
        r"SEK\s+([\d\s]+?[,.][\d]{2})\b",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            val = _to_decimal(m.group(1))
            if val and val > 0:
                return val
    return None


# ---------- Public entrypoint ----------

def parse_utility_pdf(pdf_bytes: bytes) -> UtilityPdfResult:
    """Parse en energifaktura → strukturerad data.

    Tolerant mot olika layouter. Om något fält inte hittas returneras
    det som None och användaren kan fylla i manuellt i UI:t.

    Stöd-matrisen finns i modul-docstringen.
    """
    res = UtilityPdfResult()
    try:
        text = extract_text(pdf_bytes)
    except Exception as exc:
        res.parse_errors.append(f"PDF-läsning misslyckades: {exc}")
        return res
    res.raw_text = text
    res.supplier, res.meter_type = detect_supplier_and_type(text)

    # Supplier-specifika parsers tar precedens
    if res.supplier == "telinet":
        _parse_telinet(text, res)
    elif res.supplier == "hjo_energi":
        _parse_hjo_energi(text, res)
    else:
        _parse_generic(text, res)

    # Sanity check
    if res.period_start is None and res.cost_kr is None:
        res.parse_errors.append(
            "Varken period eller totalbelopp hittat — troligen ej en faktura."
        )
    return res
