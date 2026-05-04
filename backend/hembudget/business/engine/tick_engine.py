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
            # Skapa Job-rad
            job = Job(
                company_id=company.id,
                opportunity_id=opp.id,
                quote_id=q.id,
                title=opp.title,
                customer_name=opp.customer_name,
                agreed_price=q.offered_price,
                started_on=today,
                expected_complete_on=today + timedelta(
                    days=q.offered_delivery_days,
                ),
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
            summary.invoices_paid_now += 1


def _phase_c_generate_opportunities(
    s: Session, *, company: Company, today: date, summary: TickSummary,
) -> None:
    """Fas C · pipeline_generator → nya JobOpportunity-rader."""
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

    customers, jobs = industry_pool(company.industry_label)

    import random as _random
    rng = _random.Random(_tick_seed(company.id, company.week_no, suffix=31))
    for k in range(out.n_opportunities):
        cust = rng.choice(customers)
        tmpl = rng.choice(jobs)
        market_price = market_price_for(tmpl, cust)
        # Volatilitet ±X% av riktpriset
        vol = profile.market_price_volatility
        adj = 1.0 + rng.uniform(-vol, vol)
        market_price = max(500, int(round(market_price * adj / 100) * 100))

        deadline = today + timedelta(days=tmpl.delivery_days * 2)
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
            description=tmpl.description,
            industry_tag=tmpl.industry_tag,
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
    summary.total_supplier_cost = total_cost


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

    today = today or date.today()
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
        tick_row.status = "failed"
        tick_row.error = str(exc)[:1000]
        tick_row.completed_at = datetime.utcnow()
        s.flush()
        raise

    return summary


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
    today = today or date.today()
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
