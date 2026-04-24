"""Tester för deterministisk detektering av fakturarader.

Mot riktiga PDFer i data_for_test/Jan så vi vet att det funkar mot
faktiska Hjo Energi, Hjo Kommun, Avfall Karaborg m.fl. som användaren
importerar månadsvis.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from hembudget.parsers.invoice_lines import (
    detect_multi_service_lines,
    enrich_parsed_with_detected_lines,
)
from hembudget.parsers.pdf_statements import extract_pdf_text_layout


REPO_ROOT = Path(__file__).resolve().parents[2]
JAN_DIR = REPO_ROOT / "data_for_test" / "Jan"
HJO_ENERGI_PDF = JAN_DIR / "efa_1776848229114.pdf"
HJO_KOMMUN_PDF = JAN_DIR / "efa_1776848216915.pdf"
AVFALL_PDF = JAN_DIR / "efa_1776848108443.pdf"


def _read_text(pdf: Path) -> str:
    return extract_pdf_text_layout(pdf.read_bytes())


@pytest.mark.skipif(not HJO_ENERGI_PDF.exists(), reason="Hjo Energi PDF saknas")
def test_hjo_energi_splits_into_el_vatten_internet():
    text = _read_text(HJO_ENERGI_PDF)
    lines = detect_multi_service_lines(text)

    # Tre rader: Elnät, Vatten, Internet/KabelTV
    assert len(lines) == 3
    descs = {ln["description"] for ln in lines}
    cats = {ln["category"] for ln in lines}
    assert "Elnät" in descs
    assert "Vatten" in descs
    assert "Internet" in descs
    # Tre olika kategorier
    assert cats == {"El", "Vatten/Avgift", "Internet"}

    # Belopp stämmer
    amts = {ln["description"]: ln["amount"] for ln in lines}
    assert amts["Elnät"] == pytest.approx(2019.23)
    assert amts["Vatten"] == pytest.approx(875.30)
    assert amts["Internet"] == pytest.approx(898.00)


@pytest.mark.skipif(not AVFALL_PDF.exists(), reason="Avfall Karaborg PDF saknas")
def test_avfall_karaborg_detects_two_rader_samma_kategori():
    """Avfall-fakturan har 2 rader (Grundavgift + Hämtning) båda under
    Vatten/Avgift. Detektorn ska returnera båda så man ser detaljerna
    även om de mappar till samma budget-kategori."""
    text = _read_text(AVFALL_PDF)
    lines = detect_multi_service_lines(text)

    # Minst 2 rader
    assert len(lines) >= 2
    # Alla under Vatten/Avgift
    for ln in lines:
        assert ln["category"] == "Vatten/Avgift"


def test_detector_returns_empty_for_single_service_invoice():
    """En A-kassa-faktura eller enkel räkning utan flera tjänster → tom."""
    text = """
    Faktura
    Medlemsavgift Januari 2026  149,00
    Att betala: 149,00
    """
    lines = detect_multi_service_lines(text)
    # Ingen match — inga kända tjänstemönster
    assert lines == []


def test_detector_skips_if_only_one_category():
    """Två Elnät-rader (t.ex. föregående + innevarande månad) → inte split
    (samma kategori, ingen budget-nytta). Men om båda har Elnät-beskrivning
    returnerar vi ändå båda så detaljerna syns."""
    text = """
    Elnät december 2025  1 000,00
    Elnät november 2025  980,00
    """
    lines = detect_multi_service_lines(text)
    # Båda hittas men returneras trots samma kategori — fallback i slutet
    # av detect_multi_service_lines returnerar >=2 rader även om
    # kategorierna är samma.
    assert len(lines) == 2


def test_enrich_respects_llm_when_it_already_has_lines():
    """Om LLM redan returnerade >=2 lines → detektorn rör inget."""
    parsed = {
        "name": "Hjo Energi",
        "amount": 3793.00,
        "lines": [
            {"description": "El", "amount": 2019.23, "category": "El"},
            {"description": "Vatten", "amount": 875.30, "category": "Vatten/Avgift"},
            {"description": "Bredband", "amount": 898.00, "category": "Internet"},
        ],
    }
    text = "Elnät  2 019,23\nVatten  875,30\nInternet/KabelTV  898,00\n"
    changed = enrich_parsed_with_detected_lines(parsed, text)
    assert changed is False
    assert len(parsed["lines"]) == 3


@pytest.mark.skipif(not HJO_ENERGI_PDF.exists(), reason="Hjo Energi PDF saknas")
def test_enrich_fills_in_when_llm_returned_no_lines():
    """LLM missar lines (returnerar []) — detektorn räddar dagen."""
    text = _read_text(HJO_ENERGI_PDF)
    parsed = {
        "name": "Hjo Energi",
        "amount": 3793.00,
        "expected_date": "2026-01-30",
        "lines": [],
    }
    changed = enrich_parsed_with_detected_lines(parsed, text)
    assert changed is True
    assert len(parsed["lines"]) == 3
    cats = {ln["category"] for ln in parsed["lines"]}
    assert cats == {"El", "Vatten/Avgift", "Internet"}


def test_enrich_rejects_detection_when_sum_differs_from_total():
    """Säkerhet: om upptäckta rader summerar till något helt annat än
    fakturabeloppet, lita inte på dem (sannolikt felaktig text-scan)."""
    parsed = {"name": "Test", "amount": 100.00, "lines": []}
    text = "Elnät  2 000,00\nVatten  1 000,00\nInternet  500,00\n"
    changed = enrich_parsed_with_detected_lines(parsed, text)
    assert changed is False
    assert parsed["lines"] == []


def test_enrich_tolerates_oresavrundning():
    """Summan av raderna kan skilja ±1-2 kr från totalbeloppet p.g.a.
    öresavrundning på svenska fakturor. Detektorn ska acceptera."""
    parsed = {"name": "Hjo Energi", "amount": 3793.00, "lines": []}
    # Summan 3792.53 (öresavrundning 0.47)
    text = "Elnät  2 019,23\nVatten  875,30\nInternet/KabelTV  898,00\n"
    changed = enrich_parsed_with_detected_lines(parsed, text)
    assert changed is True
    assert len(parsed["lines"]) == 3
