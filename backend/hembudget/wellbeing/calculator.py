"""Wellbeing-beräkningsmotor.

Beräknar 5-dimensionell Wellbeing-Score (0-100) baserat på elevens
ekonomi i scope-DB:n. I fas 1 räknar vi BARA på ekonomiska faktorer:
- budget vs Konsumentverket-minimum (Mat & hälsa-dimensionen)
- saldo + skuld + sparande (Ekonomi + Trygghet)
- buffert (Trygghet)

Sociala/Fritid-dimensionerna ligger på neutral 50 i fas 1 — fylls i
av events i fas 3 (StudentEvent).

Pedagogiskt: ALLA bidrag är transparenta. Det ska gå att räkna efter
poängen själv genom att läsa explanation-texten.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from ..db.models import Account, Budget, Loan, Transaction, WellbeingScore
from .minimums import check_against_minimum


@dataclass
class WellbeingFactor:
    """En enskild bidragspost — pedagogiskt transparent."""
    dimension: str       # "economy" | "health" | "social" | "leisure" | "safety"
    points: int          # Bidrag till dimensionen (kan vara negativt)
    explanation: str     # Pedagogisk text


@dataclass
class WellbeingResult:
    year_month: str
    total_score: int = 50
    economy: int = 50
    health: int = 50
    social: int = 50
    leisure: int = 50
    safety: int = 50
    factors: list[WellbeingFactor] = field(default_factory=list)
    events_accepted: int = 0
    events_declined: int = 0
    budget_violations: int = 0

    @property
    def explanation(self) -> str:
        """Sammanfattande text för UI:t — listar de viktigaste
        bidragen i klartext."""
        if not self.factors:
            return "Ingen aktivitet att bedöma än."
        # Sortera mest påverkande först
        ranked = sorted(self.factors, key=lambda f: -abs(f.points))[:5]
        lines = [
            f"Wellbeing: {self.total_score}/100 — viktigaste bidragen:"
        ]
        for f in ranked:
            sign = "+" if f.points >= 0 else ""
            lines.append(f"• {f.dimension} ({sign}{f.points} p): {f.explanation}")
        return "\n".join(lines)


def _saldo_for(session: Session, account_id: int) -> Decimal:
    acc = session.get(Account, account_id)
    if acc is None:
        return Decimal("0")
    base = acc.opening_balance or Decimal("0")
    q = session.query(
        sa_func.coalesce(sa_func.sum(Transaction.amount), 0),
    ).filter(Transaction.account_id == account_id)
    if acc.opening_balance_date is not None:
        q = q.filter(Transaction.date >= acc.opening_balance_date)
    total = q.scalar() or Decimal("0")
    if not isinstance(total, Decimal):
        total = Decimal(str(total))
    return base + total


def _checking_balance(session: Session) -> Decimal:
    """Total saldo över alla checking-konton."""
    accs = session.query(Account).filter(Account.type == "checking").all()
    return sum((_saldo_for(session, a.id) for a in accs), Decimal("0"))


def _savings_balance(session: Session) -> Decimal:
    """Total saldo över alla sparkonton + ISK."""
    accs = (
        session.query(Account)
        .filter(Account.type.in_({"savings", "isk"}))
        .all()
    )
    return sum((_saldo_for(session, a.id) for a in accs), Decimal("0"))


def _total_active_debt(session: Session) -> Decimal:
    total = (
        session.query(sa_func.coalesce(sa_func.sum(Loan.principal_amount), 0))
        .filter(Loan.active.is_(True))
        .scalar() or Decimal("0")
    )
    return Decimal(str(total)) if not isinstance(total, Decimal) else total


def _high_cost_credit_count(session: Session) -> int:
    # Skydda mot prod-Postgres som ännu saknar kolumnen (migration ej körd).
    # Wellbeing-räkning får inte krascha — då tar den ner hela dashboarden.
    from ..school.engines import scope_has_column
    if not scope_has_column("loans", "is_high_cost_credit"):
        return 0
    try:
        return (
            session.query(Loan)
            .filter(Loan.active.is_(True), Loan.is_high_cost_credit.is_(True))
            .count()
        )
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "_high_cost_credit_count: SELECT misslyckades — returnerar 0",
        )
        try:
            session.rollback()
        except Exception:
            pass
        return 0


def _budget_violations(session: Session, year_month: str) -> tuple[int, list[str]]:
    """Kollar elevens budget för denna månad mot Konsumentverket. Returnerar
    (antal_violations, lista_av_categorinamn) — kategorinamn behövs i UI."""
    from ..db.models import Category
    rows = (
        session.query(Budget, Category.name)
        .join(Category, Category.id == Budget.category_id)
        .filter(Budget.month == year_month)
        .all()
    )
    violations: list[str] = []
    for b, cat_name in rows:
        check = check_against_minimum(cat_name, int(b.planned_amount))
        if check.is_violation:
            violations.append(cat_name)
    return len(violations), violations


def calculate_wellbeing(session: Session, year_month: str) -> WellbeingResult:
    """Beräkna Wellbeing för en given månad.

    Fas 1: bara ekonomiska faktorer. Fas 3 lägger till events.
    """
    result = WellbeingResult(year_month=year_month)
    factors: list[WellbeingFactor] = []

    # --- EKONOMI-DIMENSION ---
    has_checking = (
        session.query(Account).filter(Account.type == "checking").count() > 0
    )
    checking = _checking_balance(session) if has_checking else None
    debt = _total_active_debt(session)
    high_cost = _high_cost_credit_count(session)

    economy = 50
    if checking is not None:
        if checking < 0:
            delta = -25
            economy += delta
            factors.append(WellbeingFactor(
                "economy", delta,
                f"Lönekontot ligger på {int(checking):,} kr — minus räknas hårt.".replace(",", " "),
            ))
        elif checking < 1_000:
            delta = -10
            economy += delta
            factors.append(WellbeingFactor(
                "economy", delta,
                f"Lönekonto under 1 000 kr — väldigt liten marginal.",
            ))
        elif checking >= 10_000:
            delta = 10
            economy += delta
            factors.append(WellbeingFactor(
                "economy", delta,
                f"Lönekonto på {int(checking):,} kr — bra marginal.".replace(",", " "),
            ))

    if high_cost > 0:
        delta = -20 * high_cost
        economy += delta
        factors.append(WellbeingFactor(
            "economy", delta,
            f"Du har {high_cost} aktivt SMS-/snabblån — högkostnadskredit "
            "äter upp ekonomin.",
        ))

    # --- TRYGGHET-DIMENSION ---
    has_savings = (
        session.query(Account)
        .filter(Account.type.in_({"savings", "isk"}))
        .count() > 0
    )
    savings = _savings_balance(session) if has_savings else Decimal("0")
    safety = 50
    if not has_savings:
        # Inga sparkonton — vi vet inte, lämna neutral
        pass
    elif savings >= 50_000:
        delta = 25
        safety += delta
        factors.append(WellbeingFactor(
            "safety", delta,
            f"Buffert på {int(savings):,} kr — välbalansat — räcker långt vid kris.".replace(",", " "),
        ))
    elif savings >= 25_000:
        delta = 15
        safety += delta
        factors.append(WellbeingFactor(
            "safety", delta,
            f"Buffert på {int(savings):,} kr — räcker en månads inkomst, ok start.".replace(",", " "),
        ))
    elif savings >= 10_000:
        delta = 5
        safety += delta
        factors.append(WellbeingFactor(
            "safety", delta,
            f"Buffert på {int(savings):,} kr — något att gripa om vid akut kostnad.".replace(",", " "),
        ))
    elif savings < 5_000:
        delta = -15
        safety += delta
        factors.append(WellbeingFactor(
            "safety", delta,
            f"Buffert bara {int(savings):,} kr — en oväntad räkning slår hårt.".replace(",", " "),
        ))

    if debt > 0:
        # Skuldkvot mot ungefärlig årsinkomst — använd checking som proxy
        # i fas 1 (vi har inte salaries-rapport här).
        # Hård gräns vid 100 000 kr i skuld utan motsvarande sparande.
        if debt > savings + 100_000:
            delta = -10
            safety += delta
            factors.append(WellbeingFactor(
                "safety", delta,
                f"Skuld {int(debt):,} kr utan motsvarande buffert — sårbar position.".replace(",", " "),
            ))

    # Betalningsanmärkningar (PaymentMark) — drar trygghet & ekonomi.
    # Pedagogiskt: anmärkningar är synliga i 3 år och stänger ut eleven
    # från låg-räntelån. Mycket konkret konsekvens.
    try:
        from ..db.models import PaymentMark as _PaymentMark
        from datetime import date as _d
        today_d = _d.today()
        active_marks = (
            session.query(_PaymentMark)
            .filter(
                (_PaymentMark.expires_at.is_(None)) |
                (_PaymentMark.expires_at >= today_d)
            )
            .count()
        )
        if active_marks > 0:
            delta = min(15, 5 * active_marks)
            safety -= delta
            factors.append(WellbeingFactor(
                "safety", -delta,
                f"{active_marks} betalningsanmärkning"
                f"{'ar' if active_marks > 1 else ''} aktiv"
                f"{'a' if active_marks > 1 else ''} — kreditstämpel "
                "som stänger ute från låg-räntelån i 3 år.",
            ))
            economy_delta = min(10, 3 * active_marks)
            economy -= economy_delta
            factors.append(WellbeingFactor(
                "economy", -economy_delta,
                "Anmärkning gör att framtida lån blir dyrare eller "
                "blockeras helt — direkt ekonomisk kostnad.",
            ))
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "calculate_wellbeing: payment_marks-factor misslyckades",
        )

    # Deklaration inlämnad (TaxYearReturn) — pedagogiskt: att hantera
    # skattekontot är ett tecken på ekonomisk mognad. Stora kvarskatter
    # som inte är planerade slår mot ekonomin direkt.
    try:
        from ..db.models import TaxYearReturn as _TYR
        from datetime import date as _date_t
        current_year = _date_t.today().year
        # Senaste året som lämnats in
        latest_return = (
            session.query(_TYR)
            .order_by(_TYR.year.desc())
            .first()
        )
        if latest_return is not None:
            # Bonus: deklaration lämnad i tid (gäller fjolåret)
            if latest_return.year == current_year - 1:
                economy += 3
                factors.append(WellbeingFactor(
                    "economy", 3,
                    f"Deklaration {latest_return.year} inlämnad — "
                    "skattekontot reglerat i tid.",
                ))
            diff = float(latest_return.diff)
            # Stor kvarskatt → economy-penalty (måste betalas in)
            if diff < -5000:
                penalty = min(15, int(abs(diff) // 1000))
                economy -= penalty
                factors.append(WellbeingFactor(
                    "economy", -penalty,
                    f"Kvarskatt {int(abs(diff)):,} kr — ".replace(",", " ")
                    + "måste betalas in. Likviditeten pressad.",
                ))
            # Stor återbäring → safety-bonus (oväntat tillskott)
            elif diff > 3000:
                bonus = min(8, int(diff // 1000))
                safety += bonus
                factors.append(WellbeingFactor(
                    "safety", bonus,
                    f"Återbäring {int(diff):,} kr — ".replace(",", " ")
                    + "oväntat tillskott till bufferten.",
                ))
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "calculate_wellbeing: tax_year_return-factor misslyckades",
        )

    # Lönesamtal (SalaryNegotiation) — påverkar wellbeing pedagogiskt:
    # - aktivt lönesamtal: +2 economy ("du tar tag i din lön")
    # - completed med löneökning: +5 economy ("hen lyckades")
    # - abandoned: -3 economy ("gav upp innan resultat")
    # OBS: SalaryNegotiation ligger i master-DB men är scope:ad per
    # student_id. För wellbeing räknas eleven via current_actor_student.
    try:
        from ..school.employer_models import (
            SalaryNegotiation as _SN,
        )
        from ..school.engines import (
            master_session as _ms_w, get_current_actor_student,
        )
        actor_id = get_current_actor_student()
        if actor_id is not None:
            with _ms_w() as msw:
                latest_neg = (
                    msw.query(_SN)
                    .filter(_SN.student_id == actor_id)
                    .order_by(_SN.started_at.desc())
                    .first()
                )
                if latest_neg is not None:
                    if latest_neg.status == "active":
                        economy += 2
                        factors.append(WellbeingFactor(
                            "economy", 2,
                            f"Pågående lönesamtal · runda startad — du "
                            f"tar tag i din lön.",
                        ))
                    elif latest_neg.status == "completed":
                        if latest_neg.final_pct and latest_neg.final_pct > 0:
                            bonus = min(
                                8, int(float(latest_neg.final_pct) * 2),
                            )
                            economy += bonus
                            factors.append(WellbeingFactor(
                                "economy", bonus,
                                f"Lönesamtal klart · "
                                f"{float(latest_neg.final_pct):.1f} % "
                                "höjning sänker lönedipp och bygger upp "
                                "ekonomin.",
                            ))
                    elif latest_neg.status == "abandoned":
                        economy -= 3
                        factors.append(WellbeingFactor(
                            "economy", -3,
                            f"Avbrutet lönesamtal — gav upp innan "
                            "resultat. Kostar både i nuvarande lön och "
                            "framtida förhandlingsläge.",
                        ))
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "calculate_wellbeing: salary_negotiation-factor misslyckades",
        )

    # Försäkringar (InsurancePolicy + InsuranceClaim) — påverkar
    # safety-axeln pedagogiskt:
    # - aktiva basförsäkringar (hem) → +safety
    # - oskyddad händelse (no_policy=True) → -safety
    # - utbetalad skada (status=paid) → +safety (försäkring fungerade)
    # - höga premier över 600 kr/mån → -economy lite (kostar i nuet)
    try:
        from ..db.models import (
            InsurancePolicy as _IP,
            InsuranceClaim as _IC,
        )
        from datetime import date as _d_ins
        active_policies = (
            session.query(_IP)
            .filter(_IP.status == "active")
            .all()
        )
        active_count = len(active_policies)
        has_hem = any(p.kind == "hem" for p in active_policies)
        total_premium = sum(
            (Decimal(str(p.premium_monthly or 0))
             for p in active_policies),
            Decimal("0"),
        )

        if has_hem:
            safety += 5
            factors.append(WellbeingFactor(
                "safety", 5,
                "Hemförsäkring aktiv — bohag och ansvar täckta. "
                "Grundtrygghet på plats.",
            ))
        if active_count >= 3:
            safety += 3
            factors.append(WellbeingFactor(
                "safety", 3,
                f"{active_count} aktiva försäkringar — heltäckande "
                "skydd för olika risker.",
            ))

        # Premie-belastning: höga totala premier kostar i nuet
        if total_premium > 700:
            penalty = min(8, int((float(total_premium) - 700) / 100))
            economy -= penalty
            factors.append(WellbeingFactor(
                "economy", -penalty,
                f"Försäkrings-premier {int(total_premium):,} kr/mån — ".replace(",", " ")
                + "över snitt för ung vuxen, optimera bundling?",
            ))

        # Skadehändelser senaste 12 månader
        from datetime import timedelta as _td_ins
        cutoff = _d_ins.today() - _td_ins(days=365)
        recent_claims = (
            session.query(_IC)
            .filter(_IC.occurred_on >= cutoff)
            .all()
        )

        paid_count = sum(
            1 for c in recent_claims if c.status == "paid"
            and c.amount_paid and c.amount_paid > 0
        )
        unprotected_count = sum(
            1 for c in recent_claims if c.no_policy
        )

        if paid_count > 0:
            bonus = min(8, paid_count * 3)
            safety += bonus
            factors.append(WellbeingFactor(
                "safety", bonus,
                f"{paid_count} skadehändelse"
                f"{'r' if paid_count > 1 else ''} ersatt"
                f"{'a' if paid_count > 1 else ''} senaste året — "
                "försäkringen fungerar konkret.",
            ))
        if unprotected_count > 0:
            penalty = min(15, unprotected_count * 8)
            safety -= penalty
            factors.append(WellbeingFactor(
                "safety", -penalty,
                f"{unprotected_count} oskyddad händelse"
                f"{'r' if unprotected_count > 1 else ''} senaste året — "
                "konsekvenser bars helt själv.",
            ))
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "calculate_wellbeing: insurance-factor misslyckades",
        )

    # Förbruknings-portfölj (UtilitySubscription) — påverkar safety
    # och economy:
    # - 3+ aktiva förbruknings-abonnemang → +3 safety (organiserat)
    # - El med spotpris (Tibber) → +1 economy (smart leverantörsval)
    # - Total månadskostnad > 1500 kr/mån → -economy (max -6)
    # - Bindningstid utgår < 30 dagar utan åtgärd → varning (ingen impact)
    try:
        from ..db.models import UtilitySubscription as _US
        from datetime import date as _d_us, timedelta as _td_us
        active_subs = (
            session.query(_US)
            .filter(_US.status == "active")
            .all()
        )
        active_subs_count = len(active_subs)
        total_monthly = sum(
            (
                Decimal(str(u.monthly_cost or 0))
                + Decimal(str(u.grid_fee_monthly or 0))
                for u in active_subs
                if not u.included_in_rent
            ),
            Decimal("0"),
        )
        has_spot = any(u.spot_pricing for u in active_subs)

        if active_subs_count >= 3:
            safety += 3
            factors.append(WellbeingFactor(
                "safety", 3,
                f"{active_subs_count} aktiva abonnemang — el, värme, "
                "internet och mobil organiserade.",
            ))
        if has_spot:
            economy += 1
            factors.append(WellbeingFactor(
                "economy", 1,
                "Spotpris-el (Tibber/likn) — du betalar marknadspris "
                "och kan styra till natten för 30 % rabatt.",
            ))
        if total_monthly > 1500:
            penalty = min(6, int((float(total_monthly) - 1500) / 200))
            if penalty > 0:
                economy -= penalty
                factors.append(WellbeingFactor(
                    "economy", -penalty,
                    f"Förbrukning {int(total_monthly):,} kr/mån — ".replace(",", " ")
                    + "över rimlig nivå, omförhandla bindningar?",
                ))

        # Bindningstid utgår snart (informativ - ingen wellbeing-impact,
        # men loggas så lärare kan följa upp)
        soon = _d_us.today() + _td_us(days=30)
        expiring = [
            u for u in active_subs
            if u.binding_end is not None and u.binding_end <= soon
        ]
        if expiring:
            factors.append(WellbeingFactor(
                "growth", 0,
                f"{len(expiring)} bindning"
                f"{'ar' if len(expiring) > 1 else ''} utgår inom 30 "
                "dagar — chans att omförhandla.",
            ))
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "calculate_wellbeing: utility-factor misslyckades",
        )

    # Hyresvärden (RentalContract + RentalNotice) — påverkar safety + economy
    try:
        from ..db.models import (
            RentalContract as _RC,
            RentalNotice as _RN,
        )
        from ..school.models import StudentProfile as _SP_rent
        from datetime import date as _d_rent, timedelta as _td_rent
        active_rentals = (
            session.query(_RC)
            .filter(_RC.status == "active")
            .all()
        )
        if active_rentals:
            primary = active_rentals[0]
            ctype = primary.contract_type
            duration = primary.duration_type
            rent = float(primary.monthly_rent or 0)

            if ctype == "forsta_hand":
                safety += 5
                factors.append(WellbeingFactor(
                    "safety", 5,
                    "Förstahandskontrakt — stabil bostad, "
                    "besittningsskydd, ingen risk för uppsägning.",
                ))
            elif ctype == "andra_hand":
                safety -= 3
                factors.append(WellbeingFactor(
                    "safety", -3,
                    "Andrahandskontrakt — tidsbegränsat, "
                    "begränsat skydd, värd kan säga upp.",
                ))
            elif ctype == "inneboende":
                safety -= 2
                factors.append(WellbeingFactor(
                    "safety", -2,
                    "Inneboende — minst skydd, inget eget kontrakt.",
                ))

            if duration == "tillsvidare" and ctype != "inneboende":
                safety += 3
                factors.append(WellbeingFactor(
                    "safety", 3,
                    "Tillsvidareavtal — ingen tidsbegränsning, "
                    "långsiktigt boende.",
                ))

            # Hyresandel av netto — slå mot StudentProfile.net_salary_monthly
            # OBS: StudentProfile bor i master-DB (MasterBase), inte i
            # scope-DB. session-parametern här är en scope-DB-session
            # → vi måste öppna master_session separat. Lazy import för
            # att undvika circular.
            try:
                from ..school.engines import master_session as _ms_rent
                with _ms_rent() as _msdb:
                    profile = (
                        _msdb.query(_SP_rent)
                        .order_by(_SP_rent.student_id.desc())
                        .first()
                    )
                    # Detacha så vi kan använda fältet utanför sessionen
                    _net_salary = (
                        float(profile.net_salary_monthly)
                        if profile and profile.net_salary_monthly
                        else None
                    )
            except Exception:
                _net_salary = None
            profile = _net_salary  # rebrand för enkelhet nedan
            if profile is not None:
                net = profile  # vi rebrand-ade till net_salary ovan
                if net > 0 and rent > 0:
                    share = rent / net
                    if share > 0.40:
                        penalty = min(
                            8, int((share - 0.40) * 100 / 5),
                        )
                        if penalty > 0:
                            economy -= penalty
                            factors.append(WellbeingFactor(
                                "economy", -penalty,
                                f"Hyran är {int(share * 100)} % av "
                                "nettoinkomsten — över 40 %-tröskeln, "
                                "lite att leva av efter fasta utgifter.",
                            ))
                    elif share < 0.25:
                        economy += 2
                        factors.append(WellbeingFactor(
                            "economy", 2,
                            f"Hyran är bara {int(share * 100)} % av "
                            "nettoinkomsten — bra utrymme för sparande.",
                        ))

            # Senaste 12 mån hyresnotiser med höjning > 4 %
            cutoff_rent = _d_rent.today() - _td_rent(days=365)
            big_hikes = (
                session.query(_RN)
                .filter(
                    _RN.occurred_on >= cutoff_rent,
                    _RN.notice_type == "hyreshojning",
                    _RN.change_pct.isnot(None),
                    _RN.change_pct > Decimal("4"),
                )
                .count()
            )
            if big_hikes > 0:
                economy -= 2
                factors.append(WellbeingFactor(
                    "economy", -2,
                    f"{big_hikes} hyreshöjning"
                    f"{'ar' if big_hikes > 1 else ''} > 4 % senaste "
                    "året — kostnaden ökar snabbare än lön.",
                ))
        else:
            # Ingen aktiv bostad alls — registrerat boende saknas
            factors.append(WellbeingFactor(
                "safety", -2,
                "Inget registrerat hyreskontrakt eller bostadsrätt — "
                "boendet är odefinierat.",
            ))
            safety -= 2
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "calculate_wellbeing: rental-factor misslyckades",
        )

    # Senaste kreditprövning (CreditCheck) — låg UC-score (D/E) drar
    # trygghet eftersom eleven inte kan låna sig ur en kris.
    try:
        from ..db.models import CreditCheck as _CreditCheck
        latest = (
            session.query(_CreditCheck)
            .order_by(_CreditCheck.computed_at.desc())
            .first()
        )
        if latest is not None:
            cls = latest.uc_score_class
            if cls == "E":
                safety -= 10
                factors.append(WellbeingFactor(
                    "safety", -10,
                    f"Kreditklass E — ingen vill låna ut. "
                    f"Måste klara dig själv ur alla kriser.",
                ))
            elif cls == "D":
                safety -= 5
                factors.append(WellbeingFactor(
                    "safety", -5,
                    f"Kreditklass D — endast dyra lån är möjliga.",
                ))
            elif cls == "A":
                safety += 3
                factors.append(WellbeingFactor(
                    "safety", 3,
                    f"Kreditklass A — full tillgång till billig kredit "
                    "om något oförutsett skulle hända.",
                ))
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "calculate_wellbeing: credit_check-factor misslyckades",
        )

    # Aktieportfölj-rörelse — pedagogisk kärnpunkt: eleven ska känna
    # loss aversion på riktigt. Påverkar Trygghet i realtid.
    try:
        from .portfolio_impact import compute_portfolio_impact
        portfolio_factors = compute_portfolio_impact(session)
        for pf in portfolio_factors:
            safety += pf.points
            factors.append(pf)
    except Exception:
        # Får aldrig krascha hela wellbeing-räkningen — log och fortsätt.
        import logging
        logging.getLogger(__name__).exception(
            "calculate_wellbeing: portfolio_impact misslyckades — hoppar över",
        )

    # --- HÄLSA-DIMENSION (budget vs minimum) ---
    health = 50
    n_violations, violation_cats = _budget_violations(session, year_month)
    if n_violations > 0:
        delta = -5 * n_violations
        health += delta
        cat_str = ", ".join(violation_cats[:3])
        factors.append(WellbeingFactor(
            "health", delta,
            f"{n_violations} budget(ar) under Konsumentverket-minimum "
            f"({cat_str}). −5 p per kategori.",
        ))
    elif rows_total := (
        session.query(Budget).filter(Budget.month == year_month).count()
    ):
        # Om budget är satt och allt är ok → liten positiv signal
        delta = 5
        health += delta
        factors.append(WellbeingFactor(
            "health", delta,
            f"Du har en realistisk budget i nivå med Konsumentverket — bra grund.",
        ))

    # --- SOCIAL + FRITID (V2: events räknas in från fas 3) ---
    from ..db.models import StudentEvent
    # Hämta events beslutade denna månad (accepted+declined räknas)
    from datetime import datetime as _dt
    y, m = year_month.split("-")
    month_start = date(int(y), int(m), 1)
    if int(m) == 12:
        month_end = date(int(y) + 1, 1, 1)
    else:
        month_end = date(int(y), int(m) + 1, 1)

    decided_events = (
        session.query(StudentEvent)
        .filter(
            StudentEvent.decided_at >= _dt.combine(month_start, _dt.min.time()),
            StudentEvent.decided_at < _dt.combine(month_end, _dt.min.time()),
            StudentEvent.status.in_({"accepted", "declined"}),
        )
        .all()
    )
    n_accepted = sum(1 for e in decided_events if e.status == "accepted")
    n_declined = sum(1 for e in decided_events if e.status == "declined")

    social = 50
    leisure = 50
    for e in decided_events:
        impact = e.impact_applied or {}
        social += int(impact.get("social", 0))
        leisure += int(impact.get("leisure", 0))

    if n_accepted + n_declined > 0:
        ratio_accept = n_accepted / max(1, n_accepted + n_declined)
        if ratio_accept >= 0.6:
            factors.append(WellbeingFactor(
                "social",
                +5,
                f"Du accepterade {n_accepted} av {n_accepted + n_declined} "
                "förslag denna månad — engagerad social aktivitet.",
            ))
            social += 5
        elif ratio_accept <= 0.2 and n_declined >= 3:
            factors.append(WellbeingFactor(
                "social",
                -5,
                f"Du nekade {n_declined} av {n_accepted + n_declined} "
                "förslag — isolering har en kostnad.",
            ))
            social -= 5

    # --- KLAMP + TOTAL ---
    economy = max(0, min(100, economy))
    health = max(0, min(100, health))
    social = max(0, min(100, social))
    leisure = max(0, min(100, leisure))
    safety = max(0, min(100, safety))
    total = (economy + health + social + leisure + safety) // 5

    result.economy = economy
    result.health = health
    result.social = social
    result.leisure = leisure
    result.safety = safety
    result.total_score = total
    result.factors = factors
    result.budget_violations = n_violations
    result.events_accepted = n_accepted
    result.events_declined = n_declined
    return result


def persist_wellbeing(session: Session, result: WellbeingResult) -> WellbeingScore:
    """Spara/uppsert WellbeingScore-rad för en månad. Idempotent."""
    existing = (
        session.query(WellbeingScore)
        .filter(WellbeingScore.year_month == result.year_month)
        .first()
    )
    if existing is None:
        row = WellbeingScore(
            year_month=result.year_month,
            total_score=result.total_score,
            economy=result.economy,
            health=result.health,
            social=result.social,
            leisure=result.leisure,
            safety=result.safety,
            events_accepted=result.events_accepted,
            events_declined=result.events_declined,
            budget_violations=result.budget_violations,
            explanation=result.explanation,
        )
        session.add(row)
    else:
        existing.total_score = result.total_score
        existing.economy = result.economy
        existing.health = result.health
        existing.social = result.social
        existing.leisure = result.leisure
        existing.safety = result.safety
        existing.events_accepted = result.events_accepted
        existing.events_declined = result.events_declined
        existing.budget_violations = result.budget_violations
        existing.explanation = result.explanation
        row = existing
    session.flush()
    return row
