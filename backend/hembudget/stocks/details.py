"""Hämta fundamentala data per aktie från yfinance.

Pedagogiskt syfte: eleven ser P/E-tal, marknadsvärde, utdelning, 52v-
high/low och företagsbeskrivning. Varje metric kommer med en
'explainer'-text som UI:n visar som tooltip.

Cachas inte explicit — yfinance har sin egen ~5 min cache. Anropas
vid varje detail-pageview, vilket är OK eftersom data inte ändras
ofta.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

log = logging.getLogger(__name__)


# Pedagogiska förklaringar per metric — visas som tooltip i UI:n.
# Hålls korta och konkreta så eleven förstår direkt utan att tappa
# sin plats i analysen.
EXPLAINERS: dict[str, str] = {
    "market_cap":
        "Marknadsvärde = aktiekurs × antal aktier. Visar hur stort "
        "bolaget är. > 100 mdr = stort (Volvo, Apple), < 5 mdr = litet.",
    "pe_ratio":
        "P/E-talet = aktiekurs / vinst per aktie. Ett P/E på 15 betyder "
        "att du betalar 15 kr för varje krona i årlig vinst. Tillväxt-"
        "bolag har ofta P/E 25-40, mogna bolag 10-20.",
    "dividend_yield":
        "Utdelning i procent av aktiekursen. 4 % betyder att om du "
        "äger för 100 kr får du 4 kr/år i utdelning. Banker och fastig-"
        "hetsbolag har hög utdelning, tillväxtbolag har ofta 0 %.",
    "beta":
        "Hur mycket aktien rör sig i förhållande till hela marknaden. "
        "Beta 1.0 = rör sig som index. 1.5 = rör sig 50 % mer (mer risk). "
        "0.5 = rör sig hälften så mycket (mindre risk).",
    "fifty_two_week_high":
        "Högsta kursen senaste 12 månader. Om dagens kurs är nära high "
        "har aktien gått bra. Kan tyda på momentum eller övervärdering.",
    "fifty_two_week_low":
        "Lägsta kursen senaste 12 månader. Om dagens kurs är nära low "
        "har aktien fallit. Kan vara köpläge — eller varningssignal.",
    "earnings_growth":
        "Vinsttillväxt i procent jämfört med året innan. Positivt = "
        "bolaget tjänar mer pengar. Negativt = mindre.",
}


def fetch_stock_fundamentals(ticker: str) -> dict:
    """Hämta nyckelmetrik från yfinance. Returnerar dict med
    'value' + 'explainer' per fält. Ger tom dict vid fel.

    Format:
    {
      "market_cap": {"value": 1234567890, "explainer": "..."},
      "pe_ratio": {"value": 18.5, "explainer": "..."},
      ...
      "summary": "Volvo är ett svenskt verkstadsföretag...",
    }
    """
    try:
        import yfinance as yf  # type: ignore
    except ImportError:
        log.warning("yfinance saknas — kan inte hämta fundamenta")
        return {}

    try:
        t = yf.Ticker(ticker)
        # `info` är dyr att hämta (HTTP-anrop till Yahoo). Hämtas på
        # detail-pageview vilket är OK; inte på listvy.
        info = t.info or {}
    except Exception as exc:
        log.warning("yfinance fundamentals fetch failed for %s: %s", ticker, exc)
        return {}

    def _wrap(key: str, value: Any) -> Optional[dict]:
        if value is None:
            return None
        return {"value": value, "explainer": EXPLAINERS.get(key, "")}

    out: dict[str, Any] = {}

    # Market cap
    mc = info.get("marketCap")
    if mc:
        out["market_cap"] = _wrap("market_cap", float(mc))

    # P/E (forward eller trailing — föredra trailing)
    pe = info.get("trailingPE") or info.get("forwardPE")
    if pe:
        out["pe_ratio"] = _wrap("pe_ratio", float(pe))

    # Utdelning i procent
    div_yield = info.get("dividendYield")
    if div_yield is not None:
        # Yahoo returnerar antingen 0.04 (4%) eller 4.0 — normalisera till %
        v = float(div_yield)
        if v < 1:
            v = v * 100
        out["dividend_yield"] = _wrap("dividend_yield", round(v, 2))

    # Beta
    beta = info.get("beta")
    if beta is not None:
        out["beta"] = _wrap("beta", round(float(beta), 2))

    # 52w high/low
    hi = info.get("fiftyTwoWeekHigh")
    if hi:
        out["fifty_two_week_high"] = _wrap("fifty_two_week_high", float(hi))
    lo = info.get("fiftyTwoWeekLow")
    if lo:
        out["fifty_two_week_low"] = _wrap("fifty_two_week_low", float(lo))

    # Earnings growth (om available)
    eg = info.get("earningsQuarterlyGrowth")
    if eg is not None:
        v = float(eg) * 100  # 0.15 → 15%
        out["earnings_growth"] = _wrap("earnings_growth", round(v, 1))

    # Bolagsbeskrivning — korthet behövs så vi trimmar till första meningen
    # eller ~400 chars. På svenska om möjligt (Yahoo har normalt engelska).
    summary = info.get("longBusinessSummary") or info.get("description")
    if summary:
        # Plocka första 2 meningarna, max 400 chars
        text = str(summary).strip()
        if len(text) > 400:
            # Klipp vid sista mellanslag innan 400
            cut = text[:400].rsplit(" ", 1)[0] + "…"
            text = cut
        out["summary"] = text

    # Industri-info
    industry = info.get("industry")
    if industry:
        out["industry"] = industry
    full_name = info.get("longName")
    if full_name:
        out["full_name"] = full_name

    return out
