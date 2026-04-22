"""Deterministisk detektering av fakturarader för svenska multi-tjänst-fakturor.

Hjo Energi, Vattenfall, E.ON, kommuner m.fl. skickar ofta kombinerade
fakturor där el, vatten, bredband, avfall, fjärrvärme listas som
separata rader med eget belopp. LLM:n missar ibland att extrahera dessa
även när texten är tydlig. Denna modul kompletterar LLM:n genom att
scanna PDF-texten efter kända tjänstemönster.

Används via `detect_multi_service_lines(text)` som returnerar en lista
av {"description", "amount", "category"}-dicts kompatibla med
build_lines_from_vision().
"""
from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)


# (regex, beskrivning, kategori-namn) — mer specifika mönster FÖRE mer generella
# (eftersom vi bryter vid första träffen per rad).
_SERVICE_PATTERNS: list[tuple[str, str, str]] = [
    # Elnät / elhandel (separata poster är vanliga)
    (r"^elnät(?:savgift)?\b", "Elnät", "El"),
    (r"^elhandel\b", "Elhandel", "El"),
    (r"^elförbrukning\b", "Elförbrukning", "El"),
    (r"^fast\s+avgift\s+el\b", "Fast avgift el", "El"),
    (r"^elenergi\b", "Elenergi", "El"),
    (r"^rörlig\s+elhandel\b", "Rörlig elhandel", "El"),
    # Vatten & avlopp
    (r"^vatten\s+och\s+avlopp\b", "Vatten och avlopp", "Vatten/Avgift"),
    (r"^vatten\b", "Vatten", "Vatten/Avgift"),
    (r"^va-?avgift\b", "VA-avgift", "Vatten/Avgift"),
    # Avfall / renhållning
    (r"^renhållning\b", "Renhållning", "Vatten/Avgift"),
    (r"^sophämtning\b", "Sophämtning", "Vatten/Avgift"),
    (r"^hämtning\s+(restavfall|matavfall|hushållsavfall)\b", "Hämtning avfall", "Vatten/Avgift"),
    (r"^avfallsavgift\b", "Avfallsavgift", "Vatten/Avgift"),
    (r"^grundavgift\s+småhus\b", "Grundavgift renhållning", "Vatten/Avgift"),
    # Bredband / internet / TV
    (r"^internet(?:/\s*kabel-?tv)?\b", "Internet", "Internet"),
    (r"^kabel[-\s]?tv\b", "KabelTV", "Internet"),
    (r"^bredband\b", "Bredband", "Internet"),
    (r"^fiber(?:\s*bredband)?\b", "Fiber", "Internet"),
    (r"^stadsnät\b", "Stadsnät", "Internet"),
    # Värme
    (r"^fjärrvärme\b", "Fjärrvärme", "El"),
    # Barnomsorg (ofta 2+ rader per faktura)
    (r"^förskole?avgift\b", "Förskoleavgift", "Förskola/Skola"),
    (r"^avg(?:ift)?\s+skolbarnsomsorg\b", "Skolbarnsomsorg", "Förskola/Skola"),
    (r"^barnomsorg(?:s?avgift)?\b", "Barnomsorg", "Förskola/Skola"),
    # Försäkring (If listar varje försäkring som egen rad)
    (r"^barnförsäkring\b", "Barnförsäkring", "Försäkring"),
    (r"^livförsäkring\b", "Livförsäkring", "Livförsäkring"),
    (r"^bilförsäkring\b", "Bilförsäkring", "Bilförsäkring"),
    (r"^helförsäkring\b", "Helförsäkring", "Bilförsäkring"),
    (r"^hemförsäkring\b", "Hemförsäkring", "Hemförsäkring"),
    (r"^villa(?:hem)?försäkring\b", "Villaförsäkring", "Hemförsäkring"),
    (r"^olycksfalls(?:försäkring)?\b", "Olycksfall", "Försäkring"),
]

# Belopp i svensk format: "2 019,23" eller "302,47" eller "1 200,00"
# Tillåter tusental-separator (mellanslag) och alltid två decimaler.
_AMOUNT_RE = re.compile(
    r"(-?\d{1,3}(?:[\s ]\d{3})*,\d{2})(?:\s*(?:kr|sek))?\s*$",
    re.IGNORECASE,
)


def _parse_sv_amount(s: str) -> float | None:
    """Konvertera '2 019,23' → 2019.23."""
    cleaned = s.replace(" ", "").replace(" ", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


# Sektionsrubriker som signalerar att det som kommer efter är en
# DETALJERAD specifikation — belopp som redan är summerade ovanför.
# Matchas endast när de står på egen rad (eller inledningsvis på raden)
# så "Se fakturaspecifikationen på nästa sida" INTE triggar snittet.
_SPEC_SECTION_RE = re.compile(
    r"^\s*(FAKTURASPECIFIKATION|Specifikation|Förbrukningsstatistik)\s*$",
    re.MULTILINE,
)


def _truncate_before_specification(text: str) -> str:
    """Returnera bara texten FÖRE första specifikations-sektionsrubriken.

    Observera: "Se fakturaspecifikationen på nästa sida" är INGEN
    sektionsrubrik — det är en hänvisning, och scanningen fortsätter
    förbi den. Riktiga sektioner kommer på egen rad (Hjo Energi:
    'FAKTURASPECIFIKATION'; If: 'Specifikation')."""
    m = _SPEC_SECTION_RE.search(text)
    return text[: m.start()] if m else text


def detect_multi_service_lines(text: str) -> list[dict]:
    """Scanna fakturatext efter kända tjänstemönster.

    Returnerar lista av {"description", "amount", "category"}.
    Tom lista om texten inte matchar något mönster — dvs. fakturan är
    sannolikt en enskild tjänst, så ingen split-uppdelning behövs.

    Scanner bara sammanfattningen av fakturan (före "FAKTURASPECIFIKATION"
    eller liknande markörer) för att undvika att plocka delposter från
    detalj-sektionen.

    Defensiv: kräver minst 2 rader för att returnera något. En faktura
    med bara en rad behöver ingen split.
    """
    if not text:
        return []

    summary = _truncate_before_specification(text)
    hits: list[dict] = []
    seen_sigs: set[tuple[str, float]] = set()

    for raw_line in summary.split("\n"):
        line = raw_line.strip()
        if not line or len(line) > 200:
            continue

        amount_match = _AMOUNT_RE.search(line)
        if not amount_match:
            continue
        amount = _parse_sv_amount(amount_match.group(1))
        if amount is None or amount <= 0:
            continue

        # Delen FÖRE beloppet är beskrivningen
        head = line[: amount_match.start()].strip()
        if not head:
            continue
        head_low = head.lower()

        for pattern, desc, cat in _SERVICE_PATTERNS:
            if re.match(pattern, head_low):
                sig = (desc, round(amount, 2))
                if sig in seen_sigs:
                    break
                seen_sigs.add(sig)
                hits.append({
                    "description": desc,
                    "amount": amount,
                    "category": cat,
                })
                break

    # Kräv minst 2 rader — samma kategori OK (t.ex. två barnomsorgs-rader)
    if len(hits) < 2:
        return []
    return hits


def enrich_parsed_with_detected_lines(
    parsed: dict,
    text: str,
    amount_tolerance_kr: float = 3.0,
) -> bool:
    """Om LLM returnerade <=1 lines, komplettera från detektorn.

    Returnerar True om komplettering skedde, False annars.
    `parsed` muteras på plats.

    Säkerhetskontroll: detektor-lines summa måste vara nära
    fakturabeloppet (inom `amount_tolerance_kr` efter öresavrundning).
    """
    existing = parsed.get("lines") or []
    if len(existing) >= 2:
        return False

    detected = detect_multi_service_lines(text)
    if len(detected) < 2:
        return False

    total = float(parsed.get("amount") or 0)
    if total <= 0:
        return False

    det_sum = sum(d["amount"] for d in detected)
    if abs(det_sum - total) > amount_tolerance_kr:
        log.info(
            "Detected lines sum (%.2f) differs from invoice total (%.2f) by %.2f — skipping enrichment",
            det_sum, total, abs(det_sum - total),
        )
        return False

    parsed["lines"] = detected
    parsed.setdefault("_detector_used", True)
    return True
