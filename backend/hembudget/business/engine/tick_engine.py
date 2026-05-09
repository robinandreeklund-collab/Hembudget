"""Business tick-engine · huvud-orkestrator.

Spec: deb/README.md avsnitt 12 ("Stega vecka framåt").

Kör en vecka i bolagets simulation. Anropas antingen:
- Direkt från elevens `POST /v2/foretag/tick` (manuell stega)
- Från `game_engine.monthly_engine.week_tick.run_private_week()` när
  privat-tick körs och eleven har biz_mode_enabled=True (synkad tick).

8 faser per tick (analog med privat-motorns A–H):
  A. Decide pending quotes — kunder svarar på elevens öppna offerter
  B. Auto-pay won jobs som blivit fakturerade och är förfallna (om
     kunden vill betala enligt payment_morality)
  C. Generate new opportunities — pipeline_generator → JobOpportunity
  D. Update reputation — drift mot snitt-kvalitet
  E. Roll random events (advanced mode)
  F. Charge subscriptions — månatliga kostnader (BusinessDecision.monthly_cost)
  G. Emit pentagon-deltas (privat-pentagon påverkas av biz-utfall)
  H. Persist BusinessTickJob audit-rad

Determinism: seed = (company_id * 100000) + week_no
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from ..models import (
    BusinessDecision,
    BusinessTickJob,
    Company,
    CompanyInvoice,
    CompanyTransaction,
    Job,
    JobOpportunity,
    MarketingCampaign,
    Quote,
    SupplierInvoice,
)
from .acceptance_model import AcceptanceInput, evaluate_quote
from .difficulty import get_biz_difficulty
from .events import roll_events
from .pipeline_generator import PipelineInput, calculate_n_opportunities
from .pricing import market_price_for
from .reputation import (
    update_reputation_from_complaint,
    update_reputation_from_delivery,
)
from .seed_data import industry_pool

log = logging.getLogger(__name__)


@dataclass
class TickSummary:
    week_no: int
    new_opportunities: int = 0
    quotes_decided: int = 0
    quotes_accepted: int = 0
    quotes_rejected: int = 0
    invoices_paid_now: int = 0
    events_triggered: int = 0
    total_supplier_cost: int = 0
    pentagon_deltas: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    reputation_after: int = 50


def _pick_customer_with_segment_mix(
    rng,
    customers,
    segment_mix: tuple[float, float, float] | None,
):
    """Välj en kund från `customers` med segment-vikter från branschen.

    `segment_mix` = (privat, foretag, kommun) som summerar till 1.0.
    Om None ges → uniform random.choice.

    Branschen styr KUND-typen mest — t.ex. snickare har 65 % privat-
    kunder (ROT-avdrag), IT-konsult 65 % företag, catering 55 % företag.
    """
    if segment_mix is None or not customers:
        return rng.choice(customers)

    # Gruppera kunder per segment
    grouped: dict[str, list] = {"privat": [], "foretag": [], "kommun": []}
    for c in customers:
        seg = getattr(c, "segment", "privat")
        grouped.setdefault(seg, []).append(c)

    # Sannolikhetsval mot bransch-mix
    p_priv, p_for, p_kom = segment_mix
    roll = rng.random()
    if roll < p_priv and grouped["privat"]:
        return rng.choice(grouped["privat"])
    if roll < p_priv + p_for and grouped["foretag"]:
        return rng.choice(grouped["foretag"])
    if grouped["kommun"]:
        return rng.choice(grouped["kommun"])

    # Fallback om bransch-mix-segment saknas i pool
    return rng.choice(customers)


def _tick_seed(company_id: int, week_no: int, suffix: int = 0) -> int:
    """Deterministisk seed för en (company, week, faslokal-suffix)."""
    return company_id * 100000 + week_no * 100 + suffix


def _sum_active_marketing_boost(
    s: Session, *, company_id: int, today: date,
) -> float:
    rows = (
        s.query(MarketingCampaign)
        .filter(
            MarketingCampaign.company_id == company_id,
            MarketingCampaign.active.is_(True),
            MarketingCampaign.started_on <= today,
            MarketingCampaign.ends_on >= today,
        )
        .all()
    )
    if not rows:
        return 0.0
    total = 0.0
    for c in rows:
        # AI-kvalitet (0.5..1.5) multiplicerar base_pipeline_boost
        ai_factor = (
            float(c.ai_quality_factor) if c.ai_quality_factor else 1.0
        )
        total += float(c.base_pipeline_boost) * ai_factor
    return min(3.0, total)


def _insured_kinds(s: Session, *, company_id: int, today: date) -> set[str]:
    rows = (
        s.query(BusinessDecision)
        .filter(
            BusinessDecision.company_id == company_id,
            BusinessDecision.kind == "insurance",
            BusinessDecision.active.is_(True),
            BusinessDecision.started_on <= today,
        )
        .all()
    )
    return {r.insurance_kind for r in rows if r.insurance_kind}


def _phase_a_decide_quotes(
    s: Session, *, company: Company, today: date, summary: TickSummary,
) -> None:
    """Fas A · kunderna svarar på elevens öppna offerter."""
    open_quotes = (
        s.query(Quote)
        .join(JobOpportunity, JobOpportunity.id == Quote.opportunity_id)
        .filter(
            Quote.company_id == company.id,
            Quote.accepted.is_(None),
            JobOpportunity.status == "quoted",
        )
        .all()
    )
    marketing_boost = _sum_active_marketing_boost(
        s, company_id=company.id, today=today,
    )
    norm_boost = min(1.0, marketing_boost / 1.5)  # normalisera till 0..1

    for i, q in enumerate(open_quotes):
        opp = q.opportunity
        inp = AcceptanceInput(
            market_price=opp.market_price,
            offered_price=q.offered_price,
            reputation=company.reputation,
            marketing_boost=norm_boost,
            pitch_quality=(
                float(q.pitch_quality) if q.pitch_quality is not None else None
            ),
            expected_delivery_days=opp.expected_delivery_days,
            offered_delivery_days=q.offered_delivery_days,
            customer_price_sensitivity=float(opp.price_sensitivity),
            customer_quality_sensitivity=float(opp.quality_sensitivity),
        )
        seed = _tick_seed(company.id, company.week_no, suffix=10 + i)
        result = evaluate_quote(inp, seed=seed)

        q.accept_probability = Decimal(str(round(result.probability, 3)))
        q.accepted = result.accepted
        q.decision_explanation = result.explanation
        q.decided_on = today

        if result.accepted:
            opp.status = "won"
            # Tids-kapacitet · uppskatta arbetstimmar från industri
            try:
                from ...api.foretag_capacity import estimate_job_hours
                est_h, per_w = estimate_job_hours(
                    opp.industry_tag or company.industry_key or "default",
                    q.offered_delivery_days,
                )
            except Exception:
                est_h, per_w = 0, 0
            deadline = today + timedelta(days=q.offered_delivery_days)
            # Skapa Job-rad
            job = Job(
                company_id=company.id,
                opportunity_id=opp.id,
                quote_id=q.id,
                title=opp.title,
                customer_name=opp.customer_name,
                agreed_price=q.offered_price,
                started_on=today,
                expected_complete_on=deadline,
                original_deadline=deadline,
                estimated_hours=est_h,
                hours_per_week=per_w,
                status="in_progress",
            )
            s.add(job)
            summary.quotes_accepted += 1
            summary.notes.append(
                f"Vunnit jobb: {opp.title} · {q.offered_price} kr"
            )
        else:
            opp.status = "lost"
            summary.quotes_rejected += 1
            summary.notes.append(f"Förlorat: {opp.title}")

        summary.quotes_decided += 1


def _phase_b_collect_payments(
    s: Session, *, company: Company, today: date, summary: TickSummary,
) -> None:
    """Fas B · kunder betalar förfallna fakturor enligt payment_morality."""
    overdue_invoices = (
        s.query(CompanyInvoice)
        .filter(
            CompanyInvoice.company_id == company.id,
            CompanyInvoice.status == "sent",
            CompanyInvoice.due_on <= today,
            CompanyInvoice.paid_on.is_(None),
        )
        .all()
    )
    if not overdue_invoices:
        return

    import random as _random
    rng = _random.Random(_tick_seed(company.id, company.week_no, suffix=20))
    for inv in overdue_invoices:
        # Hämta jobbets opportunity → payment_morality
        job = (
            s.query(Job)
            .filter(Job.invoice_id == inv.id)
            .first()
        )
        morality = 0.92  # default
        if job is not None:
            opp = (
                s.query(JobOpportunity)
                .filter(JobOpportunity.id == job.opportunity_id)
                .first()
            )
            if opp is not None:
                morality = float(opp.payment_morality)

        if rng.random() < morality:
            inv.status = "paid"
            inv.paid_on = today
            if job is not None:
                job.status = "paid"
            # Bokför income-transaktionen — annars syns inte fakturan i
            # kassan eller i Allabolags omsättning. Manuell mark-paid
            # (api/foretag.py) gör samma sak; auto-betalningen här
            # tappade tx tidigare → bolaget visade "0 kr omsättning"
            # trots att fakturan stod som betald.
            s.add(CompanyTransaction(
                company_id=inv.company_id,
                occurred_on=inv.paid_on,
                kind="income",
                category="Försäljning",
                description=f"Faktura {inv.invoice_number} betald",
                amount_excl_vat=inv.amount_excl_vat,
                vat_rate=inv.vat_rate,
                vat_amount=inv.vat_amount or Decimal(0),
            ))
            summary.invoices_paid_now += 1


def _phase_c_generate_opportunities(
    s: Session, *, company: Company, today: date, summary: TickSummary,
) -> None:
    """Fas C · pipeline_generator → nya JobOpportunity-rader.

    Spärrar generering om bolaget saknar bas-utrustning · eleven måste
    köpa innan kunderna börjar höra av sig (realistisk modell)."""
    if not company.has_base_equipment:
        summary.notes.append(
            "Inga nya förfrågningar · bas-utrustning saknas"
        )
        return

    profile = get_biz_difficulty(company.level)

    in_progress = (
        s.query(Job)
        .filter(
            Job.company_id == company.id,
            Job.status == "in_progress",
        )
        .count()
    )
    marketing_boost = _sum_active_marketing_boost(
        s, company_id=company.id, today=today,
    )

    inp = PipelineInput(
        week_no=company.week_no,
        reputation=company.reputation,
        avg_quality=company.avg_quality,
        open_complaints=company.open_complaints,
        active_marketing_boost=marketing_boost,
        delivery_capacity=company.delivery_capacity,
        in_progress_jobs=in_progress,
        base_per_week=profile.base_opportunities_per_week,
    )
    out = calculate_n_opportunities(
        inp, seed=_tick_seed(company.id, company.week_no, suffix=30),
    )
    summary.notes.append(out.explanation)

    # Använd industry_KEY (stabil) istället för industry_LABEL (display).
    # Tidigare bröt detta 7/10 industrier eftersom labels innehåller
    # mellanslag/snedstreck ("Snickare / hantverkare") medan seed_data
    # är keyed på key.
    customers, jobs = industry_pool(company.industry_key)

    # === Stad-multipliers · pris + pipeline-täthet ===
    # Stockholm-IT 1200 kr/h, Umeå-IT 850 kr/h. Storstad → fler offerter.
    city_price_mult = 1.0
    if company.city_key:
        try:
            from ...game_engine.pools.stadspool import STAD_BY_KEY
            stad = STAD_BY_KEY.get(company.city_key)
            if stad is not None:
                # Större stad = högre priser (cost_multiplier_housing
                # är en bra proxy för lokal-prissättning + lönenivå)
                city_price_mult = float(stad.cost_multiplier_housing)
        except Exception:
            pass

    # === Bransch-baseline · Industry.hourly_rate × Industry.time ===
    industry_rate_mid = None
    industry_segment_mix: tuple[float, float, float] | None = None
    if company.industry_key:
        try:
            from ..industries import get_industry as _get_ind
            ind = _get_ind(company.industry_key)
            industry_rate_mid = (
                ind.hourly_rate_min + ind.hourly_rate_max
            ) / 2.0
            industry_segment_mix = (
                ind.segment_mix_privat,
                ind.segment_mix_foretag,
                ind.segment_mix_kommun,
            )
        except Exception:
            pass

    import random as _random
    rng = _random.Random(_tick_seed(company.id, company.week_no, suffix=31))
    for k in range(out.n_opportunities):
        # Vikta kund-segment efter bransch om vi har mix-data
        cust = _pick_customer_with_segment_mix(
            rng, customers, industry_segment_mix,
        )
        tmpl = rng.choice(jobs)

        # Pris-baseline · försök bransch-baserat · annars fallback
        if industry_rate_mid is not None:
            est_hours = (tmpl.delivery_days or 1) * 6
            market_price = int(industry_rate_mid * est_hours)
        else:
            market_price = market_price_for(tmpl, cust)

        # Stad-multiplier
        market_price = int(market_price * city_price_mult)

        # Volatilitet ±X% av riktpriset
        vol = profile.market_price_volatility
        adj = 1.0 + rng.uniform(-vol, vol)
        market_price = max(500, int(round(market_price * adj / 100) * 100))

        deadline = today + timedelta(days=tmpl.delivery_days * 2)

        # AI-berikad jobbeskrivning · varierad text per offert i stället
        # för identiska template-strängar. Faller tillbaka till
        # tmpl.description om AI saknas/fail:ar (deterministisk fallback
        # per CLAUDE.md-policy). Vi gör bara AI-anropet för 1 av 3 nya
        # offerter för att inte spränga tokens när biz tickar autotick:t
        # varje timme — räcker för att eleven ska se variation.
        description = tmpl.description
        if rng.random() < 0.33:
            try:
                from ..ai import generate_job_description as _gen_desc
                from ...school.engines import master_session as _ms_ai
                from ...school.models import (
                    Student as _Stu_ai,
                )
                # Hitta lärare via tenant_id ("s_<id>" eller "f_<id>")
                teacher_id_for_ai: Optional[int] = None
                tenant = getattr(company, "tenant_id", None) or ""
                if tenant.startswith("s_"):
                    try:
                        sid_ai = int(tenant[2:])
                        with _ms_ai() as _msa:
                            stu_ai = _msa.get(_Stu_ai, sid_ai)
                            if stu_ai is not None:
                                teacher_id_for_ai = stu_ai.teacher_id
                    except (ValueError, Exception):
                        pass
                ai_desc = _gen_desc(
                    job_title=tmpl.title,
                    industry=company.industry_label or "Tjänst",
                    customer_name=cust.name,
                    teacher_id=teacher_id_for_ai,
                )
                if ai_desc:
                    description = ai_desc
            except Exception:
                pass

        # Kräver bil? Branscher med requires_car: alla privat-kund-jobb
        # och 50 % av företag-jobb (deterministiskt via rng).
        requires_car = False
        try:
            from ..industries import get_industry as _gi
            ind_meta = _gi(company.industry_key) if company.industry_key else None
            if ind_meta and ind_meta.requires_car:
                if cust.segment == "privat":
                    requires_car = True
                elif cust.segment == "foretag":
                    requires_car = rng.random() < 0.5
        except Exception:
            pass

        opp = JobOpportunity(
            company_id=company.id,
            customer_name=cust.name,
            customer_segment=cust.segment,
            price_sensitivity=Decimal(str(round(
                cust.price_sensitivity * profile.customer_price_pressure_mult, 3,
            ))),
            quality_sensitivity=Decimal(str(round(cust.quality_sensitivity, 3))),
            payment_morality=Decimal(str(round(cust.payment_morality, 3))),
            title=tmpl.title,
            description=description,
            industry_tag=tmpl.industry_tag,
            requires_car=requires_car,
            market_price=market_price,
            expected_delivery_days=tmpl.delivery_days,
            deadline_on=deadline,
            status="open",
            week_no=company.week_no,
            received_on=today,
        )
        s.add(opp)

    summary.new_opportunities = out.n_opportunities


def _phase_d_reputation_drift(
    s: Session, *, company: Company, summary: TickSummary,
) -> None:
    """Fas D · drift av reputation mot snitt-kvalitet (utan delivery)."""
    if company.avg_quality is None:
        return
    # Långsam drift (5 % av diff per vecka) — säkerställer att ett enskilt
    # bra/dåligt jobb inte förstör/raddar bygget
    target = company.avg_quality
    diff = target - company.reputation
    if abs(diff) >= 1:
        company.reputation = max(
            0, min(100, company.reputation + int(round(diff * 0.05))),
        )


def _phase_e_random_events(
    s: Session, *, company: Company, today: date, summary: TickSummary,
) -> list[dict]:
    """Fas E · slumpevents (bara advanced mode)."""
    profile = get_biz_difficulty(company.level)
    if profile.event_probability_per_week <= 0:
        return []

    insured = _insured_kinds(s, company_id=company.id, today=today)
    events = roll_events(
        seed=_tick_seed(company.id, company.week_no, suffix=40),
        n_max=profile.max_events_per_week,
        p_per_week=profile.event_probability_per_week,
        insured_kinds=insured,
    )
    out: list[dict] = []
    for ev in events:
        # Skapa en SupplierInvoice som källan av kostnaden
        s.add(SupplierInvoice(
            company_id=company.id,
            sender_name="Slumpevent",
            invoice_number=f"EV-{company.week_no}-{ev.template.kind[:5]}",
            issued_on=today,
            due_on=today + timedelta(days=14),
            description=ev.template.label,
            amount_excl_vat=ev.actual_cost,
            vat_rate=Decimal("0.25"),
            source="system",
            status="open",
            notes=ev.template.description + (
                "\n[Försäkring täckte 90 %.]" if ev.insurance_covered else ""
            ),
        ))
        if ev.template.creates_complaint:
            company.open_complaints += 1
            company.reputation = update_reputation_from_complaint(
                company.reputation, severity=1,
            )
        elif ev.template.reputation_impact != 0:
            company.reputation = max(
                0, min(100, company.reputation + ev.template.reputation_impact),
            )
        out.append({
            "kind": ev.template.kind,
            "label": ev.template.label,
            "cost": ev.actual_cost,
            "insurance_covered": ev.insurance_covered,
        })
    summary.events_triggered = len(events)
    return out


def _phase_f_charge_subscriptions(
    s: Session, *, company: Company, today: date, summary: TickSummary,
) -> None:
    """Fas F · debitera månatliga decisions (anställd, leasing, friskvård)."""
    # Vi kör veckovis charge: monthly_cost / 4 i veckan
    active_decisions = (
        s.query(BusinessDecision)
        .filter(
            BusinessDecision.company_id == company.id,
            BusinessDecision.active.is_(True),
            BusinessDecision.monthly_cost > 0,
            BusinessDecision.started_on <= today,
        )
        .all()
    )
    total_cost = 0
    for d in active_decisions:
        weekly = int(round(d.monthly_cost / 4))
        if weekly <= 0:
            continue
        s.add(CompanyTransaction(
            company_id=company.id,
            occurred_on=today,
            kind="expense",
            category=f"decision:{d.kind}",
            description=f"Veckokostnad · {d.title}",
            amount_excl_vat=Decimal(str(weekly)),
            vat_rate=Decimal("0.25"),
            vat_amount=Decimal(str(int(round(weekly * 0.25)))),
        ))
        total_cost += weekly

    # Lokal-hyra · 1/4 av månadshyra per biz-vecka
    try:
        from ..models import CompanyLocation
        loc = (
            s.query(CompanyLocation)
            .filter(
                CompanyLocation.company_id == company.id,
                CompanyLocation.is_active.is_(True),
            )
            .first()
        )
        if loc and loc.monthly_cost > 0:
            weekly_rent = int(round(loc.monthly_cost / 4))
            s.add(CompanyTransaction(
                company_id=company.id,
                occurred_on=today,
                kind="expense",
                category="Lokal · hyra",
                description=f"Veckohyra · {loc.location_kind}",
                amount_excl_vat=Decimal(str(weekly_rent)),
                vat_rate=Decimal("0.25"),
                vat_amount=Decimal(str(int(round(weekly_rent * 0.25)))),
            ))
            total_cost += weekly_rent
    except Exception:
        log.exception("phase_f: lokal-hyra-debitering misslyckades")

    # Lån-räntor · 1/4 av månadsbetalning per biz-vecka
    try:
        from ..models import CompanyLoan
        active_loans = (
            s.query(CompanyLoan)
            .filter(
                CompanyLoan.company_id == company.id,
                CompanyLoan.status == "active",
            )
            .all()
        )
        for ln in active_loans:
            weekly_pmt = int(round(ln.monthly_payment / 4))
            if weekly_pmt <= 0:
                continue
            # Ränta + amortering proportionellt
            monthly_rate = float(ln.interest_rate) / 12.0
            interest_weekly = int(round(ln.outstanding * monthly_rate / 4))
            amort_weekly = max(0, weekly_pmt - interest_weekly)
            if amort_weekly > ln.outstanding:
                amort_weekly = ln.outstanding
            s.add(CompanyTransaction(
                company_id=company.id,
                occurred_on=today,
                kind="expense",
                category="Lån · ränta",
                description=f"Veckoränta · {ln.lender}",
                amount_excl_vat=Decimal(str(interest_weekly)),
                vat_rate=Decimal("0.0"),
                vat_amount=Decimal(0),
            ))
            if amort_weekly > 0:
                s.add(CompanyTransaction(
                    company_id=company.id,
                    occurred_on=today,
                    kind="expense",
                    category="Lån · amortering",
                    description=f"Veckoamortering · {ln.lender}",
                    amount_excl_vat=Decimal(str(amort_weekly)),
                    vat_rate=Decimal("0.0"),
                    vat_amount=Decimal(0),
                ))
            ln.outstanding -= amort_weekly
            if ln.outstanding <= 0 or ln.months_left <= 0:
                ln.status = "repaid"
            ln.months_left = max(0, ln.months_left - 1)
            total_cost += interest_weekly + amort_weekly
    except Exception:
        log.exception("phase_f: lån-debitering misslyckades")

    # Avskrivningar · 1/4 av månadsavskrivning per biz-vecka
    # Linjär plan: cost_excl_vat / useful_life_months · 4 för veckokostnad
    try:
        from ..models import CompanyAsset
        active_assets = (
            s.query(CompanyAsset)
            .filter(
                CompanyAsset.company_id == company.id,
                CompanyAsset.status == "active",
            )
            .all()
        )
        for asset in active_assets:
            life = max(1, int(asset.useful_life_months or 60))
            monthly_dep = float(asset.cost_excl_vat or 0) / life
            weekly_dep = int(round(monthly_dep / 4))
            if weekly_dep <= 0:
                continue
            remaining = float(asset.cost_excl_vat or 0) - float(
                asset.accumulated_depreciation or 0
            )
            if remaining <= 0:
                asset.status = "fully_depreciated"
                continue
            booked = min(weekly_dep, int(remaining))
            cat = (
                "Avskrivning Inventarier"
                if asset.asset_kind == "equipment"
                else "Avskrivning Fordon"
            )
            s.add(CompanyTransaction(
                company_id=company.id,
                occurred_on=today,
                kind="expense",
                category=cat,
                description=f"Veckoavskrivning · {asset.label}",
                amount_excl_vat=Decimal(str(booked)),
                vat_rate=Decimal("0.0"),
                vat_amount=Decimal(0),
            ))
            asset.accumulated_depreciation = Decimal(
                str(float(asset.accumulated_depreciation or 0) + booked)
            )
            asset.last_depreciation_on = today
            if float(asset.accumulated_depreciation) >= float(
                asset.cost_excl_vat or 0
            ):
                asset.status = "fully_depreciated"
            total_cost += booked
    except Exception:
        log.exception("phase_f: avskrivnings-bokning misslyckades")

    summary.total_supplier_cost = total_cost


def kickstart_pipeline_only(
    s: Session, *, company: Company, weeks: int = 2,
) -> None:
    """Generera N veckors offertförfrågningar UTAN att boka veckoränta,
    amortering, avskrivning eller andra phase_f-kostnader.

    Används när vi vill fylla pipelinen direkt (t.ex. precis efter köp
    av bas-utrustning) men INTE dubbel-debitera kostnader. run_business_
    week kör ALLA phases inkl. _phase_f_charge_subscriptions, vilket
    blev veckokostnader x2 på samma datum när buy_startup_kit + list_
    opportunities båda försökte 'kickstarta'.

    Bara phase_c (pipeline-generering) körs här. company.week_no avancerar
    så pipeline_generator-statistiken känns korrekt, men inga transaktioner
    bokförs.
    """
    if not company.active:
        return
    # Använd spel-datum (synkat med privat-tid) i stället för real-tid
    # så genererade opps får rätt datum-stämpel.
    from ..game_clock import current_game_date
    today = current_game_date()
    for _ in range(weeks):
        try:
            company.week_no = (company.week_no or 0) + 1
            summary = TickSummary(week_no=company.week_no)
            _phase_c_generate_opportunities(
                s, company=company, today=today, summary=summary,
            )
        except Exception:
            log.exception(
                "kickstart_pipeline_only: phase_c misslyckades vecka %s",
                company.week_no,
            )
            break
    s.flush()


def _update_capacity_from_growth(
    s: Session, *, company: Company,
) -> None:
    """Synca delivery_capacity baserat på lokal × utrustning × MCP.

    Körs INNAN _phase_c_generate_opportunities så pipeline_generator
    har rätt cap-värde. Fail-soft: om CompanyLocation/Equipment saknas
    bibehålls existerande delivery_capacity."""
    try:
        from ..models import (
            CompanyEquipment, CompanyLocation, CompanyMcpRental,
        )
        loc = (
            s.query(CompanyLocation)
            .filter(
                CompanyLocation.company_id == company.id,
                CompanyLocation.is_active.is_(True),
            )
            .first()
        )
        eq = (
            s.query(CompanyEquipment)
            .filter(
                CompanyEquipment.company_id == company.id,
                CompanyEquipment.is_active.is_(True),
            )
            .first()
        )
        # SPEL-TID-FIX: tidigare _d.today() (real-tid) jämfördes mot
        # ends_on (spel-tid). En MCP som "startar idag och slutar
        # om 2 spel-veckor" hade ends_on = spel-2026-01-15. Real-today
        # = 2026-05-08 → filtret ends_on >= real-today blev False →
        # MCP räknades som inaktiv direkt vid skapande → eleven
        # förlorade kapaciteten utan att märka.
        from ..game_clock import current_game_date as _cgd_mcp
        active_mcp = (
            s.query(CompanyMcpRental)
            .filter(
                CompanyMcpRental.company_id == company.id,
                CompanyMcpRental.status == "active",
                CompanyMcpRental.ends_on >= _cgd_mcp(),
            )
            .count()
        )
        base = loc.max_concurrent_jobs if loc else 2
        speed = float(eq.speed_multiplier) if eq else 1.0
        new_cap = max(1, int(base * speed) + active_mcp)
        company.delivery_capacity = new_cap
    except Exception:
        log.exception("update_capacity_from_growth misslyckades")


def run_business_week(
    s: Session,
    *,
    company: Company,
    today: Optional[date] = None,
) -> TickSummary:
    """Kör en vecka i bolaget. Returnerar TickSummary för audit + UI.

    Detta är huvudingången. Kallas antingen från elevens manuella
    tick-endpoint eller från `monthly_engine.week_tick.run_private_week()`
    när scope har biz_mode_enabled och en aktiv Company.
    """
    if not company.active:
        raise ValueError("Cannot tick a closed company")

    if today is None:
        from ..game_clock import current_game_date
        today = current_game_date()
    company.week_no += 1
    summary = TickSummary(week_no=company.week_no)

    # Skapa audit-rad innan körning så vi kan logga error om något fail:ar
    tick_row = BusinessTickJob(
        company_id=company.id,
        week_no=company.week_no,
        status="running",
    )
    s.add(tick_row)
    s.flush()

    try:
        # Synca kapacitet från lokal/utrustning/MCP innan pipeline-gen
        _update_capacity_from_growth(s, company=company)
        _phase_a_decide_quotes(s, company=company, today=today, summary=summary)
        _phase_b_collect_payments(
            s, company=company, today=today, summary=summary,
        )
        _phase_c_generate_opportunities(
            s, company=company, today=today, summary=summary,
        )
        _phase_d_reputation_drift(s, company=company, summary=summary)
        events_log = _phase_e_random_events(
            s, company=company, today=today, summary=summary,
        )
        _phase_f_charge_subscriptions(
            s, company=company, today=today, summary=summary,
        )
        _phase_g_employment_decision_check(
            s, company=company, summary=summary,
        )
        _phase_vat_threshold_check(
            s, company=company, today=today, summary=summary,
        )
        _phase_h_milestone_mails(
            s, company=company, summary=summary,
        )
        _phase_i_overload_consequences(
            s, company=company, today=today, summary=summary,
        )

        s.flush()
        tick_row.status = "done"
        tick_row.completed_at = datetime.utcnow()
        tick_row.summary = {
            "notes": summary.notes,
            "events": events_log,
        }
        tick_row.n_new_opportunities = summary.new_opportunities
        tick_row.n_quotes_decided = summary.quotes_decided
        tick_row.n_jobs_delivered = 0  # leverans sker i deliver-endpoint, ej tick
        tick_row.n_invoices_paid = summary.invoices_paid_now
        tick_row.reputation_after = company.reputation

        summary.reputation_after = company.reputation
        s.flush()
    except Exception as exc:
        log.exception("biz tick failed for company %s week %s",
                      company.id, company.week_no)
        # VIKTIGT: tick_row är på samma session `s` som alla phases.
        # När exceptionen propageras → session_scope rollback:ar HELA
        # sessionen, inkl. tick_row. Resultatet: vi kan ALDRIG se vad
        # som failade. Persistera failure-raden i en SEPARAT session
        # innan re-raise, så att tick-status-endpoint kan visa felet.
        try:
            from ...db.base import session_scope as _ss_audit
            with _ss_audit() as _audit_s:
                _audit_row = BusinessTickJob(
                    company_id=company.id,
                    week_no=company.week_no,
                    status="failed",
                    error=str(exc)[:1000],
                    completed_at=datetime.utcnow(),
                )
                _audit_s.add(_audit_row)
        except Exception:
            log.exception(
                "kunde inte persistera tick-failure i separat session",
            )
        raise

    return summary


# ===== Auto-tick · spelmotorn drar fram veckor baserat på real-tid =====
#
# Tidigare krävdes att läraren tryckte "Stega vecka" eller att privat-
# tick rullade en månad framåt. Det gjorde biz-läget statiskt och döddt
# mellan elev-besök · ingen ny offert dök upp förrän eleven själv
# triggade. Nu körs run_business_week automatiskt när en biz-endpoint
# läses, baserat på real-tid · 1 biz-vecka per AUTO_TICK_INTERVAL_HOURS
# real-timme. Resultat: eleven loggar in och ser nya offertförfrågningar
# rulla in över dagen, kunder besluter sig om gamla offerter, etc.
#
# Lazy-eval-mönstret är samma som /v2/postladan-realtidsprojektion: vi
# slipper en konstant background-job men får ändå en levande spelvärld.

AUTO_TICK_INTERVAL_HOURS = 1.0  # 1 biz-vecka per real-timme · justerbart
AUTO_TICK_MAX_CATCHUP_WEEKS = 6  # tak per request så vi inte loopar

def auto_tick_if_due(s: Session, *, company: Company) -> int:
    """Kör så många run_business_week som behövs för att fånga upp
    real-tid sedan senaste auto-tick. Idempotent · säker att anropa
    från valfri biz-endpoint vid läsning. Returnerar antal körda
    veckor (0 = ingen tick behövdes)."""
    if not company.active:
        return 0
    now = datetime.utcnow()
    last = company.last_auto_tick_at
    if last is None:
        # Första läsningen efter create_company · sätt baseline utan
        # att tika (create_company gjorde redan 2 init-veckor).
        company.last_auto_tick_at = now
        return 0
    elapsed_hours = (now - last).total_seconds() / 3600.0
    n_due = int(elapsed_hours // AUTO_TICK_INTERVAL_HOURS)
    if n_due <= 0:
        return 0
    n = min(n_due, AUTO_TICK_MAX_CATCHUP_WEEKS)

    # Beräkna SPEL-datum för respektive tick · biz ska gå genom samma
    # kalender som privat (anchor 2026-01-01, 1 real-timme = 1 spel-
    # vecka). Annars hamnar biz-transaktioner med real-tid (maj 2026)
    # medan privat står på spel-tid (jan 2026).
    from ..game_clock import current_game_date
    game_today = current_game_date()

    n_done = 0
    for _ in range(n):
        try:
            run_business_week(s, company=company, today=game_today)
            n_done += 1
        except Exception:
            log.exception(
                "auto_tick: vecka %s misslyckades · stoppar",
                company.week_no + 1,
            )
            # VIKTIGT: vi kan INTE bara avancera last_auto_tick_at som om
            # ticken kördes — då hamnar offerter "i evig kö" eftersom
            # phase_a aldrig får chansen att besluta dem och vi inte
            # försöker igen vid nästa request. Lämna last_auto_tick_at
            # ofall för att försöka igen direkt på nästa endpoint-läsning.
            break
    # Avancera tidsstämpeln med antalet faktiska lyckade tickar (n_done),
    # inte n. Om allt failade lämnar vi last_auto_tick_at orörd så vi
    # fortsätter försöka tills underliggande bug är fixad.
    from datetime import timedelta as _td
    if n_done > 0:
        company.last_auto_tick_at = last + _td(
            hours=n_done * AUTO_TICK_INTERVAL_HOURS,
        )

    # Sync till Allabolag-cachen (master-DB) så klassens scoreboard
    # uppdateras. Fail-soft: om sync krashar fortsätter ändå auto-tick.
    if n_done > 0:
        try:
            from ...school.engines import (
                master_session as _ms,
                get_current_actor_student as _gcas,
            )
            from ...school.models import Student as _Stu
            from ...api.allabolag import sync_class_company_share
            sid = _gcas()
            if sid is not None:
                with _ms() as _msess:
                    stu = _msess.get(_Stu, sid)
                    if stu is not None:
                        sync_class_company_share(
                            s,
                            company=company,
                            teacher_id=stu.teacher_id,
                            student_id=sid,
                            class_label=stu.class_label,
                        )
        except Exception:
            log.exception(
                "auto_tick: Allabolag-sync misslyckades för company=%s",
                company.id,
            )
    return n_done


# ===== Cross-engine: tids-stress + Maria-prompt (Sprint 8) =====

def _phase_g_employment_decision_check(
    s: Session, *, company: Company, summary: TickSummary,
) -> None:
    """Spåra tids-stress · skicka Maria-mail vid 4+ veckor överbelastning.

    Logiken:
    1. Räkna totala timmar (anställd + biz active jobs)
    2. Om total > 50: öka consecutive_overload_weeks
    3. Om consecutive >= 4 OCH biz_h >= 25 OCH employed: skicka mail
    4. Annars · reset overload-counter om timmarna är OK

    Mail skickas en gång; vi triggar inte igen så länge eleven inte
    har valt eller om eleven valt 'keep_fulltime' (där vi resetar
    counter).
    """
    from ..cross_pentagon import compute_weekly_business_hours
    from ..employment_decision import (
        evaluate_employment_decision, maria_prompt_text,
    )
    from ...school.engines import (
        master_session, get_current_actor_student,
    )
    from ...school.models import StudentProfile, Student

    actor_id = get_current_actor_student()
    if actor_id is None:
        return

    # Räkna biz-timmar
    in_progress = (
        s.query(Job)
        .filter(Job.company_id == company.id, Job.status == "in_progress")
        .all()
    )
    biz_h = compute_weekly_business_hours(
        in_progress, industry_key=company.industry_key,
    )

    # Hämta + uppdatera StudentProfile
    student_first_name = "du"
    with master_session() as ms:
        prof = (
            ms.query(StudentProfile)
            .filter(StudentProfile.student_id == actor_id)
            .first()
        )
        stu = ms.get(Student, actor_id)
        if stu is not None and stu.display_name:
            student_first_name = stu.display_name.split(" ")[0]
        if prof is None:
            return
        emp_h = int(getattr(prof, "weekly_hours_employed", 40) or 40)
        emp_status = getattr(prof, "employment_status", "employed")
        overload = int(getattr(prof, "consecutive_overload_weeks", 0) or 0)
        total_h = emp_h + biz_h

        if total_h > 50:
            overload += 1
        else:
            overload = 0

        prof.consecutive_overload_weeks = overload
        ms.commit()

        trigger = evaluate_employment_decision(
            weekly_hours_business=biz_h,
            consecutive_overload_weeks=overload,
            employment_status=emp_status,
        )

    if not trigger.should_trigger:
        summary.notes.append(
            f"tidsstress · {biz_h}h biz · overload-veckor={overload}",
        )
        return

    # Kolla om vi redan skickat ett Maria-mail med samma trigger
    # (för att inte spamma varje vecka). Använd subject-prefix som idmark.
    from ...db.models import MailItem
    existing = (
        s.query(MailItem)
        .filter(
            MailItem.subject.like("Hej %· vi behöver prata om din arbetstid"),
            MailItem.status.in_({"unhandled", "viewed"}),
        )
        .first()
    )
    if existing is not None:
        summary.notes.append(
            "Maria-prompt redan skickad och oavslutad · skippar",
        )
        return

    subj, meta, body = maria_prompt_text(
        student_first_name=student_first_name,
        weekly_hours_business=biz_h,
        weeks=overload,
    )
    s.add(MailItem(
        sender="Maria · din chef",
        sender_short="MAR",
        sender_kind="work",
        sender_meta="tidskonflikt · 3 val att besvara",
        mail_type="info",
        subject=subj,
        body_meta=meta,
        body=body,
        amount=None,
        due_date=None,
        received_at=datetime.utcnow(),
        status="unhandled",
    ))
    summary.notes.append(
        f"Maria-säg-upp-prompt skickad ({biz_h}h biz · {overload}v "
        "överbelastning)",
    )


def _phase_vat_threshold_check(
    s: Session, *, company: Company, today: date, summary: TickSummary,
) -> None:
    """Pedagogisk auto-trigger av momsregistrering.

    Skattereglerna: bolag MÅSTE vara momsregistrerat när 12-månaders
    rullande omsättning passerar 80 000 kr. Innan tröskeln är det
    frivilligt (kan göras för att få ingående moms tillbaka).

    I simuleringen vill vi inte tvinga eleven ta ställning vid bolags-
    start (när oms är 0). I stället:
      * Vid 60 000 kr → varnings-mail från Skatteverket: 'närmar sig
        gränsen, börja förbered registrering'.
      * Vid 80 000 kr → mail + auto-flippar vat_registered=True.

    Idempotent: kollar mail med stable subject så vi inte spammar varje
    vecka när tröskeln redan passerats.
    """
    if company.vat_registered:
        return  # redan registrerat, inget att göra

    from ..models import CompanyTransaction as _Tx
    from ...db.models import MailItem

    cutoff_12m = today - timedelta(days=365)
    income_12m = (
        s.query(_Tx)
        .filter(
            _Tx.company_id == company.id,
            _Tx.kind == "income",
            _Tx.occurred_on >= cutoff_12m,
        )
        .all()
    )
    revenue_12m = sum(float(t.amount_excl_vat or 0) for t in income_12m)

    if revenue_12m >= 80000:
        # Auto-registrera + skicka mail
        existing = (
            s.query(MailItem)
            .filter(MailItem.subject == "Momsregistrering · automatisk")
            .first()
        )
        if existing is None:
            s.add(MailItem(
                sender="Skatteverket",
                sender_short="SKV",
                sender_kind="agency",
                sender_meta="Momsregistrering",
                mail_type="info",
                subject="Momsregistrering · automatisk",
                body_meta=f"12 mån omsättning: {int(revenue_12m):,} kr".replace(",", " "),
                body=(
                    "Hej. Ditt bolag har passerat 80 000 kr i rullande "
                    "12-månaders omsättning. Enligt momslagen är "
                    "registrering nu obligatoriskt — vi har lagt upp "
                    "momsnummer åt dig automatiskt.\n\n"
                    "Detta påverkar din verksamhet:\n"
                    "· Du ska lägga 25 % moms på fakturor till privat-"
                    "kunder och 6/12/25 % beroende på bransch på "
                    "andra kunder.\n"
                    "· Du får tillbaka ingående moms på dina kostnader "
                    "(t.ex. 25 % på utrustning) i din momsdeklaration.\n"
                    "· Momsperiod: kvartal (kan ändras).\n\n"
                    "Hälsningar / Skatteverket"
                ),
                amount=None,
                due_date=None,
                status="unhandled",
            ))
            company.vat_registered = True
            summary.notes.append(
                f"Auto-momsreg · 12-mån oms {int(revenue_12m)} kr ≥ 80 000 kr"
            )
    elif revenue_12m >= 60000:
        # Varnings-mail · obligatoriskt om 20k till
        existing = (
            s.query(MailItem)
            .filter(MailItem.subject == "Närmar sig moms-gränsen")
            .first()
        )
        if existing is None:
            s.add(MailItem(
                sender="Skatteverket",
                sender_short="SKV",
                sender_kind="agency",
                sender_meta="Information",
                mail_type="info",
                subject="Närmar sig moms-gränsen",
                body_meta=f"12 mån omsättning: {int(revenue_12m):,} kr".replace(",", " "),
                body=(
                    f"Ditt bolag har {int(revenue_12m):,} kr i rullande "
                    "12-månaders omsättning. Vid 80 000 kr blir moms-"
                    "registrering obligatoriskt — vi registrerar dig "
                    "automatiskt då.\n\n"
                    "Du kan registrera dig FRIVILLIGT redan nu om du vill "
                    "kunna dra av ingående moms på dina kostnader. "
                    "Hör av dig om du vill det.\n\n"
                    "Hälsningar / Skatteverket"
                ).replace(",", " "),
                amount=None,
                due_date=None,
                status="unhandled",
            ))
            summary.notes.append(
                f"Moms-varning · 12-mån oms {int(revenue_12m)} kr"
            )


def _phase_h_milestone_mails(
    s: Session, *, company: Company, summary: TickSummary,
) -> None:
    """Pedagogiska milstolpe-mail · skickas vid specifika veckor.

    v4 · 'Du har drivit företaget i 4 veckor — reflektera om
           prissättning och kund-mix.'
    v8 · 'Du har drivit företaget i 8 veckor — börjar du se mönster
           i vilka kund-typer som betalar bäst?'
    v12 · 'Vad har du lärt dig om kassaflöde under första kvartalet?'
    v24 · 'Halv-årsuppdatering — pentagon-jämförelse mot start.'

    Idempotent: kolla att mail med samma subject inte redan finns.
    Mailen signeras av elevens lärare (dynamisk) · läses från
    Teacher.name via current-actor-student-cookie.
    """
    from ...db.models import MailItem

    # Hämta läraren som äger eleven · signerar milstolpe-mailen
    teacher_name = "Klassansvarig lärare"
    name_initials = "LÄR"
    try:
        from ...school.engines import (
            master_session as _ms_t,
            get_current_actor_student as _gcas_t,
        )
        from ...school.models import Student as _Stu_t, Teacher as _T_t
        actor_id = _gcas_t()
        if actor_id is not None:
            with _ms_t() as _msdb_t:
                _stu = _msdb_t.get(_Stu_t, actor_id)
                if _stu is not None:
                    _t = _msdb_t.get(_T_t, _stu.teacher_id)
                    if _t is not None and _t.name:
                        teacher_name = _t.name
                        name_initials = "".join(
                            w[0] for w in teacher_name.split() if w
                        )[:4].upper() or "LÄR"
    except Exception:
        pass

    # Lärar-namn används i body-texten där det refereras
    teacher_first = teacher_name.split(" ")[0] if teacher_name else "läraren"

    milestones = {
        4:  ("Reflektera · 4 veckor i drift",
             "Vad har du lärt dig om prissättning?",
             "Du har drivit företaget i en månad. Innan du går vidare — "
             "stanna upp och fundera. Ligger dina priser i mitten av "
             "Konsumentverkets schablon? Är dina kunder främst privat, "
             "företag eller kommun? Vad ger bäst marginal? Skriv ner i "
             f"en reflektion för {teacher_first}."),
        8:  ("Reflektera · 8 veckor i drift",
             "Mönster i kunder och betalning?",
             "8 veckor in. Vilka kunder betalar i tid? Vilka släpar? "
             "Finns det en bransch-trend i din kund-mix? Marginalen "
             "skiljer sig ofta 20+ % mellan privat och företag — har "
             f"du sett det? Reflektion till {teacher_first}."),
        12: ("Reflektera · 12 veckor · första kvartalet",
             "Kassaflöde · vad lärde du dig?",
             "Första kvartalet klart. Hur har kassan rört sig? Var det "
             "en månad där du nästan inte kunde ta ut egen lön? Hur "
             "skiljer sig moms-due från det du faktiskt har på "
             "företagskontot? Skriv en lärande-reflektion."),
        24: ("Halv-årsuppdatering",
             "Pentagon-jämförelse mot start",
             "26 veckor i drift. Pentagon-axlarna har rört sig — vilken "
             "har stigit mest, vilken har dippat? Privat-pentagonen har "
             "också reagerat på företaget. Är det värt det?"),
    }

    if company.week_no not in milestones:
        return

    subject_short, meta, body = milestones[company.week_no]
    full_subject = f"v{company.week_no} · {subject_short}"

    # Idempotens · kolla om mail redan finns
    existing = (
        s.query(MailItem)
        .filter(MailItem.subject == full_subject)
        .first()
    )
    if existing is not None:
        return

    s.add(MailItem(
        sender=f"{teacher_name} · klassansvarig",
        sender_short=name_initials,
        sender_kind="other",
        sender_meta=f"milstolpe · v{company.week_no}",
        mail_type="info",
        subject=full_subject,
        body_meta=meta,
        body=body,
        amount=None,
        due_date=None,
        received_at=datetime.utcnow(),
        status="unhandled",
    ))
    summary.notes.append(
        f"Milstolpe-mail v{company.week_no} skickat",
    )


# ===== Leverera-jobb (separat funktion · kallas från endpoint) =====


def deliver_job(
    s: Session,
    *,
    company: Company,
    job: Job,
    quality_score: int,
    today: Optional[date] = None,
    create_invoice: bool = True,
) -> tuple[Job, Optional[CompanyInvoice]]:
    """Eleven levererar ett jobb.

    Sätter quality_score, skapar CompanyInvoice (om create_invoice=True),
    uppdaterar avg_quality och reputation.
    """
    if today is None:
        from ..game_clock import current_game_date
        today = current_game_date()
    if job.status not in ("in_progress",):
        raise ValueError("Job is not in_progress")

    job.quality_score = quality_score
    job.delivered_on = today
    job.status = "delivered"

    # Uppdatera bolagets historik
    from .reputation import update_avg_quality
    company.avg_quality = update_avg_quality(company.avg_quality, quality_score)
    company.reputation = update_reputation_from_delivery(
        company.reputation, quality_score,
    )
    company.jobs_delivered += 1

    invoice: Optional[CompanyInvoice] = None
    if create_invoice:
        # Skapa kund (om saknas) + faktura
        from ..models import CompanyCustomer
        cust = (
            s.query(CompanyCustomer)
            .filter(
                CompanyCustomer.company_id == company.id,
                CompanyCustomer.name == job.customer_name,
            )
            .first()
        )
        if cust is None:
            cust = CompanyCustomer(
                company_id=company.id,
                name=job.customer_name,
                is_private=True,
            )
            s.add(cust)
            s.flush()

        amt = Decimal(str(job.agreed_price))
        vat_rate = Decimal("0.25")
        vat_amt = (amt * vat_rate).quantize(Decimal("0.01"))
        invoice_no = f"F-{company.id:04d}-{company.jobs_delivered:04d}"
        invoice = CompanyInvoice(
            company_id=company.id,
            customer_id=cust.id,
            invoice_number=invoice_no,
            issued_on=today,
            due_on=today + timedelta(days=30),
            description=job.title,
            amount_excl_vat=amt,
            vat_rate=vat_rate,
            vat_amount=vat_amt,
            status="sent",
        )
        s.add(invoice)
        s.flush()
        job.invoice_id = invoice.id
        job.status = "invoiced"

    s.flush()
    return job, invoice


# ===== Fas K · överbelastning-konsekvenser =====

def _phase_i_overload_consequences(
    s: Session, *, company: Company, today: date, summary: TickSummary,
) -> None:
    """Räknar belastning, tillämpar tier-konsekvenser, slumpar förseningar.

    Spec: Fas K · dev/feature-allabolag.md (tids-kapacitet)

    Tier-trappa (per vecka):
      T0 ≤ 100%        ingen påföljd
      T1 101-130%      Hälsa-3, 5% delay-risk per jobb
      T2 131-180%      Hälsa-8 + Trygghet-2, 25% delay
      T3 >180%         Hälsa-15 + Trygghet-5, 50% delay
      T4 (T3 i 4+ v)   Krasch · capacity 0 i 1 v

    Återhämtning: ratio < 0.9 → consecutive_overload_weeks --1
    """
    import random
    from ...school.engines import (
        get_current_actor_student, master_session,
    )
    from ...school.models import StudentProfile, Student
    from ..models import CompanyMcpRental, Job

    sid = get_current_actor_student()
    if sid is None:
        return

    # Hämta tids-kapacitet
    try:
        from ...api.foretag_capacity import (
            compute_time_capacity, _classify_tier, TIER_INFO,
        )
        cap = compute_time_capacity(s, company=company, student_id=sid)
    except Exception:
        log.exception("overload: kunde inte räkna kapacitet")
        return

    ratio = cap["ratio"]
    weeks_over = cap["weeks_overloaded"]

    # Uppdatera räknaren
    with master_session() as ms:
        prof = (
            ms.query(StudentProfile)
            .filter(StudentProfile.student_id == sid)
            .first()
        )
        if prof is None:
            return
        if ratio > 1.0:
            current = int(getattr(prof, "consecutive_overload_weeks", 0) or 0)
            prof.consecutive_overload_weeks = current + 1
            weeks_over = current + 1
        elif ratio < 0.9:
            current = int(getattr(prof, "consecutive_overload_weeks", 0) or 0)
            prof.consecutive_overload_weeks = max(0, current - 1)
        ms.commit()

    tier = _classify_tier(ratio, weeks_over)
    if tier == 0:
        return

    info = TIER_INFO[tier]

    # Privat-pentagon · Hälsa + Trygghet
    try:
        from ...game_engine.pentagon import apply_pentagon_delta
        if info["health_per_week"] != 0:
            apply_pentagon_delta(
                sid, axis="health",
                requested_delta=info["health_per_week"],
                reason_kind="biz_overload",
                reason_id=company.id,
                reason_table="companies",
                explanation=(
                    f"Företaget är på {tier} ({info['label']}) · "
                    f"belastning {int(ratio * 100)} %"
                ),
            )
        if info["safety_per_week"] != 0:
            apply_pentagon_delta(
                sid, axis="safety",
                requested_delta=info["safety_per_week"],
                reason_kind="biz_overload",
                reason_id=company.id,
                reason_table="companies",
                explanation=(
                    f"Stress från företaget påverkar tryggheten ({info['label']})"
                ),
            )
    except Exception:
        log.exception("overload: kunde inte applicera pentagon-delta")

    # Tier 4 · krasch · capacity 0 i 1 vecka
    if tier == 4:
        company.delivery_capacity = 0
        # Generera mail
        try:
            from ...db.models import MailItem
            s.flush()
            # Mail till postlådan (privat-scope) görs via shared session_scope
            # som redan är aktiv via tenant_id
            from ...db.base import session_scope as _ps
            with _ps() as priv_s:
                priv_s.add(MailItem(
                    sender="Vårdcentralen",
                    sender_short="VC",
                    sender_kind="health",
                    mail_type="info",
                    subject="Sjukskrivning · 1 vecka",
                    body=(
                        "Du har varit kraftigt överbelastad i 4 veckor "
                        "rakt. Vi sjukskriver dig 1 vecka för återhämtning. "
                        "Företagets kapacitet är 0 under denna tid · alla "
                        "aktiva jobb pausas.\n\n"
                        "När du kommer tillbaka: ta bort uppdrag, anställ "
                        "någon eller säg upp privat-jobbet."
                    ),
                    amount=None,
                    due_date=None,
                    status="unhandled",
                ))
                priv_s.commit()
        except Exception:
            pass

    # Slumpa förseningar per aktivt jobb
    delay_prob = info["delay_risk_pct"] / 100.0
    if delay_prob <= 0:
        return

    rng = random.Random(_tick_seed(company.id, company.week_no, suffix=99))
    active_jobs = (
        s.query(Job)
        .filter(
            Job.company_id == company.id,
            Job.status == "in_progress",
        )
        .all()
    )
    for job in active_jobs:
        if rng.random() >= delay_prob:
            continue
        # Försening · 7 dagar
        from datetime import timedelta as _td
        job.expected_complete_on = job.expected_complete_on + _td(days=7)
        job.delays_count = int(job.delays_count or 0) + 1
        job.last_delayed_on = today

        # Kund klagar omedelbart
        company.open_complaints += 1
        company.reputation = max(0, company.reputation - 10)
        summary.notes.append(
            f"Försening: {job.title} · {job.delays_count}:e ggn"
        )

        # 3:e gången → kund avbryter
        if job.delays_count >= 3:
            job.status = "cancelled"
            company.reputation = max(0, company.reputation - 15)
            summary.notes.append(
                f"Kund avbröt: {job.title} (3+ förseningar)"
            )
            try:
                from ...db.models import MailItem
                from ...db.base import session_scope as _ps
                with _ps() as priv_s:
                    priv_s.add(MailItem(
                        sender=job.customer_name,
                        sender_short="KUND",
                        sender_kind="customer",
                        mail_type="info",
                        subject=f"Avbruten beställning · {job.title}",
                        body=(
                            f"Vi har tappat förtroendet efter 3 förseningar. "
                            f"Vi avbryter beställningen utan slutbetalning. "
                            f"Detta påverkar både företagets rykte och "
                            f"kreditvärdighet."
                        ),
                        amount=None,
                        due_date=None,
                        status="unhandled",
                    ))
                    priv_s.commit()
            except Exception:
                pass
        else:
            # Klagomål-mail
            try:
                from ...db.models import MailItem
                from ...db.base import session_scope as _ps
                with _ps() as priv_s:
                    priv_s.add(MailItem(
                        sender=job.customer_name,
                        sender_short="KUND",
                        sender_kind="customer",
                        mail_type="info",
                        subject=f"Klagomål · {job.title}",
                        body=(
                            f"Hej. Vi noterar att leveransen försenats. "
                            f"Detta är inte ok. Ny förväntad leverans: "
                            f"{job.expected_complete_on.isoformat()}."
                        ),
                        amount=None,
                        due_date=None,
                        status="unhandled",
                    ))
                    priv_s.commit()
            except Exception:
                pass
