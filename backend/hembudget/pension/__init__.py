"""Default-seed + beräknings-helpers för Aktör 09 · Pensionsmyndigheten.

Skapar en singleton PensionAssumption per scope med 2026-defaults:
- Riktålder 67 år (höjs gradvis till 69 år 2030)
- Real avkastning 2 %
- IBB 2026 = 80 600 kr/år (7,5 IBB-tak ≈ 604 500 kr/år)
- Delningstal 17 (vid 67 år)
- ITP1 4,5 % under 7,5 IBB · 30 % över

Beräkningarna gör 4 pelare:
1a. Inkomstpension — 16 % av lön upp till 7,5 IBB, ackumulerat med real
    avkastning över återstående år, omvandlat via delningstal.
1b. Premiepension — 2,5 % av lön, samma logik (men med högre antagen
    avkastning eftersom AP7 Såfa har högre aktieandel).
2.  Tjänstepension ITP1 — 4,5 % under tak, 30 % över. Hämtar lön +
    arbetsgivare från StudentProfile (master-DB).
3.  Privat (Avanza ISK) — månadssparande × 12 × år × ränta-på-ränta.
    Tar nuvarande FundHolding + StockHolding-värde som startvärde.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from ..db.models import (
    Account,
    FundHolding,
    PensionAssumption,
    StockHolding,
)


def seed_default_pension(s: Session) -> int:
    """Skapa singleton PensionAssumption om saknas. Idempotent.

    Returnerar 1 om ny rad skapades, 0 om redan fanns.
    """
    existing = s.query(PensionAssumption).first()
    if existing is not None:
        return 0
    s.add(PensionAssumption())
    s.flush()
    return 1


def get_or_create_assumptions(s: Session) -> PensionAssumption:
    """Hämta scope-singleton, skapa om saknas."""
    a = s.query(PensionAssumption).first()
    if a is None:
        a = PensionAssumption()
        s.add(a)
        s.flush()
    return a


def isk_balance(s: Session) -> Decimal:
    """Beräkna nuvarande ISK-värde — fonder + aktier på alla ISK-konton.

    Returnerar 0 om inget ISK-konto finns.
    """
    isk_accounts = (
        s.query(Account).filter(Account.type == "isk").all()
    )
    if not isk_accounts:
        return Decimal("0")

    ids = [a.id for a in isk_accounts]
    fund_total = sum(
        (
            Decimal(str(h.market_value or 0))
            for h in s.query(FundHolding)
            .filter(FundHolding.account_id.in_(ids))
            .all()
        ),
        Decimal("0"),
    )
    stock_holdings = (
        s.query(StockHolding)
        .filter(StockHolding.account_id.in_(ids))
        .all()
    )
    stock_total = Decimal("0")
    if stock_holdings:
        # Hämta senaste kurs per ticker från master.latest_stock_quotes
        from ..school.engines import master_session as _ms
        from ..school.stock_models import LatestStockQuote
        tickers = list({h.ticker for h in stock_holdings})
        with _ms() as msdb:
            quotes = (
                msdb.query(LatestStockQuote)
                .filter(LatestStockQuote.ticker.in_(tickers))
                .all()
            )
            price_by_ticker = {
                q.ticker: Decimal(str(q.last)) for q in quotes
            }
        for h in stock_holdings:
            price = price_by_ticker.get(
                h.ticker, Decimal(str(h.avg_cost)),
            )
            stock_total += Decimal(str(h.quantity)) * price

    return fund_total + stock_total


def project_pelare(
    monthly_pension_kr_today: float,
    real_return_pct: float,
    years_to_retire: int,
) -> float:
    """Hjälp: räkna upp ett dagens månadsbelopp med real avkastning.

    Returnerar belopp i dagens penningvärde (real, ej nominal). Eftersom
    real_return redan är inflationsjusterad multiplicerar vi enbart med
    (1 + r)^år för accumulering på pensionskapital, inte på utbetalning.
    Detta är förenklat — verklig pensionsberäkning är delningstal-baserad
    men funkar pedagogiskt.
    """
    if years_to_retire <= 0:
        return monthly_pension_kr_today
    growth = (1.0 + real_return_pct / 100.0) ** years_to_retire
    return monthly_pension_kr_today * growth


def _annual_to_monthly_via_delningstal(
    annual_capital_kr: float,
    delningstal: float,
) -> float:
    """Omvandla pensionskapital till månadsutbetalning via delningstal.

    delningstal ≈ 17 vid 67 år (livslängdsfaktor). Månadsbeloppet
    = capital / (delningstal * 12).
    """
    if delningstal <= 0:
        return 0.0
    return annual_capital_kr / (delningstal * 12.0)


def compute_pension_forecast(
    s: Session,
    *,
    age: Optional[int],
    gross_salary_monthly: Optional[float],
    has_collective_agreement: bool,
) -> dict:
    """Returnerar dict med 4 pelare + total + scenario-prognoser.

    Beräkning baserad på StudentProfile (lön + ålder) + ev. ITP1
    (kollektivavtal i Fas 2C) + ISK-värde (FundHolding + StockHolding).
    Pengar i dagens penningvärde (real avkastning).
    """
    a = get_or_create_assumptions(s)
    retire_age = int(a.retire_age)
    real_return = float(a.real_return_pct)
    delningstal = float(a.delningstal)
    ibb = float(a.ibb_yearly)
    ibb_cap_75 = ibb * 7.5  # 7.5 IBB tak — ~604 500 kr 2026
    itp_low = float(a.itp1_low_pct)
    itp_high = float(a.itp1_high_pct)
    custom_isk = float(a.custom_isk_monthly)

    if age is None or gross_salary_monthly is None:
        # Tomt scenario — eleven har inte fyllt i profil
        return {
            "retire_age": retire_age,
            "real_return_pct": real_return,
            "ibb_yearly": ibb,
            "delningstal": delningstal,
            "years_to_retire": 0,
            "pillars": [],
            "total_monthly_at_retire": 0.0,
            "scenarios": {},
            "isk_current_value": float(isk_balance(s)),
            "custom_isk_monthly": custom_isk,
        }

    years_to_retire = max(0, retire_age - age)
    annual_salary = gross_salary_monthly * 12.0
    capped_annual = min(annual_salary, ibb_cap_75)
    over_cap_annual = max(0.0, annual_salary - ibb_cap_75)

    # 1a · Inkomstpension: 16 % av lön under tak, ackumulerat
    income_pct = 16.0
    annual_contribution = capped_annual * income_pct / 100.0
    # Approximativt: total pensionsrätt om månads-inbetalningen ackumulerar
    # över years_to_retire med real_return → geometric sum
    if years_to_retire > 0 and real_return > 0:
        r = real_return / 100.0
        capital_inkomst = annual_contribution * (
            ((1 + r) ** years_to_retire - 1) / r
        )
    else:
        capital_inkomst = annual_contribution * years_to_retire
    inkomst_monthly = _annual_to_monthly_via_delningstal(
        capital_inkomst, delningstal,
    )

    # 1b · Premiepension: 2.5 % — högre antagen avkastning (AP7 Såfa, +1pp)
    premie_pct = 2.5
    annual_premie = capped_annual * premie_pct / 100.0
    r_pp = (real_return + 1.0) / 100.0
    if years_to_retire > 0:
        capital_premie = annual_premie * (
            ((1 + r_pp) ** years_to_retire - 1) / r_pp
        )
    else:
        capital_premie = annual_premie * years_to_retire
    premie_monthly = _annual_to_monthly_via_delningstal(
        capital_premie, delningstal,
    )

    # 2 · ITP1 tjänstepension
    if has_collective_agreement and gross_salary_monthly > 0:
        annual_itp = (
            capped_annual * itp_low / 100.0
            + over_cap_annual * itp_high / 100.0
        )
        if years_to_retire > 0 and real_return > 0:
            r2 = real_return / 100.0
            capital_itp = annual_itp * (
                ((1 + r2) ** years_to_retire - 1) / r2
            )
        else:
            capital_itp = annual_itp * years_to_retire
        itp_monthly = _annual_to_monthly_via_delningstal(
            capital_itp, delningstal,
        )
    else:
        itp_monthly = 0.0

    # 3 · Privat (ISK) — startvärde + månadssparande × år × ränta-på-ränta
    isk_now = float(isk_balance(s))
    monthly_save = custom_isk
    r3 = real_return / 100.0
    if years_to_retire > 0 and r3 > 0:
        # Future value: startvärde * (1+r)^år + månads * geometric sum
        fv_start = isk_now * ((1 + r3) ** years_to_retire)
        fv_monthly = (
            monthly_save * 12.0 * ((1 + r3) ** years_to_retire - 1) / r3
        )
        capital_private = fv_start + fv_monthly
    else:
        capital_private = isk_now + monthly_save * 12.0 * years_to_retire
    # Privat tas ut över ~25 år (egen plan), inte delningstal
    private_monthly = (
        capital_private / (25 * 12.0) if capital_private > 0 else 0.0
    )

    pillars = [
        {
            "label": "Pelare 1",
            "name": "Inkomstpension",
            "detail": "Statlig · 16 % av lön upp till 7,5 IBB",
            "monthly_at_retire": round(inkomst_monthly, 0),
            "source": "auto",
        },
        {
            "label": "Pelare 1",
            "name": "Premiepension",
            "detail": "2,5 % · AP7 Såfa (default)",
            "monthly_at_retire": round(premie_monthly, 0),
            "source": "auto",
        },
        {
            "label": "Pelare 2",
            "name": "Tjänstepension ITP1",
            "detail": (
                f"{itp_low:.1f} % under tak · {itp_high:.0f} % över · "
                "kollektivavtal" if has_collective_agreement
                else "Inget kollektivavtal · 0 kr/mån"
            ),
            "monthly_at_retire": round(itp_monthly, 0),
            "source": "agreement" if has_collective_agreement else "missing",
        },
        {
            "label": "Pelare 3",
            "name": "Privat (Avanza ISK)",
            "detail": (
                f"{int(monthly_save)} kr/mån sparat · ISK-värde "
                f"{int(isk_now):,} kr".replace(",", " ")
            ),
            "monthly_at_retire": round(private_monthly, 0),
            "source": "isk",
        },
    ]

    total = sum(p["monthly_at_retire"] for p in pillars)

    # Scenarier · tidigt (-4 % per år före 67), sent (+8 % per år)
    early = total * (1.0 - 0.04 * 2)  # 65 år
    late = total * (1.0 + 0.08 * 3)   # 70 år

    return {
        "retire_age": retire_age,
        "real_return_pct": real_return,
        "ibb_yearly": ibb,
        "delningstal": delningstal,
        "years_to_retire": years_to_retire,
        "pillars": pillars,
        "total_monthly_at_retire": round(total, 0),
        "scenarios": {
            "age_65_early": round(early, 0),
            "age_67_target": round(total, 0),
            "age_70_late": round(late, 0),
        },
        "isk_current_value": round(isk_now, 0),
        "custom_isk_monthly": round(custom_isk, 0),
        "annual_salary": annual_salary,
        "ibb_cap_75": ibb_cap_75,
    }
