"""Klass-pool-offertförfrågningar · alla elever med samma bransch
ser samma förfrågan och tävlar.

Spec: dev/feature-allabolag.md (Fas C)

Flöde:
1. emit_shared_opportunities_if_due() — schemaläggs varje real-tim
   per teacher+industry. Skapar SharedOpportunity om det är dags.
   Triggas lazy från GET /v2/foretag/opportunities/shared.
2. Eleven ser sin pool-vy + lämnar EN SharedQuote per opp.
3. Vid deadline_at: lazy-eval → AI väljer vinnare → en Job skapas
   i vinnarens scope-DB, förlorarna får pedagogisk förklaring.

Lazy-mönstret matchar auto_tick_if_due (1 emit per timme per
teacher+industry) — slipper background scheduler."""
from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as SASession

from .deps import TokenInfo, require_token
from ..business.models import (
    Company, Job, JobOpportunity, Quote,
)
from ..db.base import session_scope


log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v2/foretag/opportunities/shared", tags=["allabolag"],
)


def _require_student(info: TokenInfo) -> int:
    if info.role != "student" or info.student_id is None:
        raise HTTPException(403, "Endast elever")
    return info.student_id


# Konfig · 1 ny shared opp per (teacher, industry) per X timmar
# Satt lågt så elever ser tävling regelbundet
SHARED_EMIT_INTERVAL_HOURS = 6.0
# Deadline · eleverna har X timmar att lämna in offert
SHARED_DEADLINE_HOURS = 24.0


# === Schemas ===

class SharedOpportunityOut(BaseModel):
    id: int
    customer_name: str
    customer_segment: str
    title: str
    description: str
    market_price: int
    expected_delivery_days: int
    industry_key: str
    deadline_at: str
    hours_until_deadline: float
    status: str
    n_competitors: int
    has_my_quote: bool
    is_winner: Optional[bool]
    decision_explanation: Optional[str]


class SharedQuoteIn(BaseModel):
    offered_price: int = Field(ge=1)
    offered_delivery_days: int = Field(ge=1, le=120)
    pitch_text: Optional[str] = Field(default=None, max_length=2000)


class SharedQuoteRowOut(BaseModel):
    student_display: str
    offered_price: int
    offered_delivery_days: int
    pitch_text: Optional[str]
    pitch_quality: Optional[float]
    is_winner: bool
    is_mine: bool


# === Emit shared opportunities ===

def _emit_shared_opportunities_if_due(
    teacher_id: int, industry_key: str, class_label: Optional[str],
) -> int:
    """Skapa nya shared opps om sista emission är > intervall.

    Använder template från seed_data per industry för konsekvent
    pris-baseline. Idempotent · returnerar antal skapade."""
    from ..school.engines import master_session
    from ..school.models import SharedOpportunity
    from ..business.engine.seed_data import industry_pool

    customers, jobs = industry_pool(industry_key)
    if not jobs:
        return 0

    now = datetime.utcnow()
    cutoff = now - timedelta(hours=SHARED_EMIT_INTERVAL_HOURS)

    with master_session() as s:
        # Senaste emit för denna kombo
        last = (
            s.query(SharedOpportunity)
            .filter(
                SharedOpportunity.teacher_id == teacher_id,
                SharedOpportunity.industry_key == industry_key,
            )
            .order_by(SharedOpportunity.created_at.desc())
            .first()
        )
        if last is not None and last.created_at > cutoff:
            return 0

        # Emitta 1 ny opp · plocka kund + jobb-template deterministiskt
        # baserat på teacher_id + industry_key + timestamp så det ej
        # är samma jobb varje gång.
        rng = random.Random(
            teacher_id * 1000
            + hash(industry_key) % 997
            + int(now.timestamp() // 3600),
        )
        cust = rng.choice(customers)
        tmpl = rng.choice(jobs)
        # Pris-volatilitet ±10 % runt baspriset
        price = int(round(tmpl.base_price * (1.0 + rng.uniform(-0.1, 0.1)) / 100) * 100)
        deadline = now + timedelta(hours=SHARED_DEADLINE_HOURS)
        opp = SharedOpportunity(
            teacher_id=teacher_id,
            class_label=class_label,
            industry_key=industry_key,
            customer_name=cust.name,
            customer_segment=cust.segment,
            title=tmpl.title,
            description=tmpl.description,
            market_price=price,
            expected_delivery_days=tmpl.delivery_days,
            deadline_at=deadline,
            status="open",
        )
        s.add(opp)
        s.commit()
        return 1


def _decide_expired_opportunities(teacher_id: int) -> int:
    """Lazy-eval: hitta open-opps med passerad deadline · AI väljer
    vinnare. Returnerar antal beslutade."""
    from ..school.engines import master_session
    from ..school.models import (
        SharedOpportunity, SharedQuote, Student,
    )

    now = datetime.utcnow()
    decided = 0
    with master_session() as s:
        expired = (
            s.query(SharedOpportunity)
            .filter(
                SharedOpportunity.teacher_id == teacher_id,
                SharedOpportunity.status == "open",
                SharedOpportunity.deadline_at <= now,
            )
            .all()
        )
        for opp in expired:
            quotes = (
                s.query(SharedQuote)
                .filter(SharedQuote.shared_opportunity_id == opp.id)
                .all()
            )
            if not quotes:
                # Ingen lämnade in · markera expired
                opp.status = "expired"
                opp.decided_at = now
                opp.decision_explanation = (
                    "Ingen i klassen lämnade offert innan deadline. "
                    "Kunden valde någon annan."
                )
                decided += 1
                continue

            # Använd existerande acceptance_model + AI-pitch-bedömning
            # AI-poolens vinnare = den med högst sammansatt score.
            # Sätt pitch_quality först om den saknas.
            from ..business.ai import evaluate_quote_pitch
            for q in quotes:
                if q.pitch_quality is None and q.pitch_text and q.pitch_text.strip():
                    try:
                        teacher_id_for_ai = teacher_id
                        score = evaluate_quote_pitch(
                            pitch=q.pitch_text,
                            job_title=opp.title,
                            job_description=opp.description,
                            teacher_id=teacher_id_for_ai,
                        )
                        if score is not None:
                            q.pitch_quality = float(score)
                    except Exception:
                        log.exception(
                            "shared_opp pitch eval failed",
                        )

            # Score = (rabatt-vs-marknad) * 50 + pitch * 30 + leverans-snabbhet * 20
            def _score(q: SharedQuote) -> float:
                price_score = max(
                    0.0,
                    1.0 - max(0, q.offered_price - opp.market_price * 0.5)
                    / max(1, opp.market_price),
                )
                pitch_score = float(q.pitch_quality) if q.pitch_quality else 0.5
                delivery_score = max(
                    0.0,
                    1.0 - max(0, q.offered_delivery_days - opp.expected_delivery_days)
                    / max(1, opp.expected_delivery_days),
                )
                return price_score * 50 + pitch_score * 30 + delivery_score * 20

            ranked = sorted(quotes, key=_score, reverse=True)
            winner = ranked[0]
            winner.is_winner = True
            opp.winner_student_id = winner.student_id
            opp.status = "decided"
            opp.decided_at = now

            # Bygg pedagogisk förklaring
            winner_score = _score(winner)
            second = ranked[1] if len(ranked) > 1 else None
            opp.decision_explanation = (
                f"Vinnare: {winner.company_name} · pris {winner.offered_price} kr, "
                f"leverans {winner.offered_delivery_days} dagar, "
                f"pitch-kvalitet {int((winner.pitch_quality or 0.5) * 100)}%. "
                + (
                    f"Andra-platsen: {second.company_name} ({second.offered_price} kr). "
                    if second else ""
                )
                + "Kunden valde mest helhet · pris + pitch + leveranstid."
            )

            # Skapa Job i vinnarens scope-DB
            try:
                stu = s.get(Student, winner.student_id)
                if stu is not None:
                    from ..school.engines import (
                        scope_for_student, scope_context, get_scope_session,
                    )
                    sk = scope_for_student(stu)
                    with scope_context(sk):
                        with get_scope_session(sk)() as scope_s:
                            co = (
                                scope_s.query(Company)
                                .filter(Company.active.is_(True))
                                .first()
                            )
                            if co is not None:
                                # Skapa lokal opportunity + quote +
                                # job så vinnaren ser det i sin
                                # vanliga jobb-lista
                                local_opp = JobOpportunity(
                                    company_id=co.id,
                                    customer_name=opp.customer_name,
                                    customer_segment=opp.customer_segment,
                                    title=opp.title,
                                    description=opp.description,
                                    industry_tag=opp.industry_key,
                                    market_price=opp.market_price,
                                    expected_delivery_days=opp.expected_delivery_days,
                                    deadline_on=opp.deadline_at.date(),
                                    status="won",
                                    week_no=int(co.week_no or 0),
                                    received_on=opp.created_at.date(),
                                )
                                scope_s.add(local_opp)
                                scope_s.flush()
                                local_quote = Quote(
                                    opportunity_id=local_opp.id,
                                    company_id=co.id,
                                    offered_price=winner.offered_price,
                                    offered_delivery_days=winner.offered_delivery_days,
                                    pitch_text=winner.pitch_text,
                                    accepted=True,
                                    accept_probability=0.99,
                                    decision_explanation=opp.decision_explanation,
                                    submitted_on=winner.submitted_at.date(),
                                    decided_on=now.date(),
                                )
                                scope_s.add(local_quote)
                                scope_s.flush()
                                local_job = Job(
                                    company_id=co.id,
                                    opportunity_id=local_opp.id,
                                    quote_id=local_quote.id,
                                    title=opp.title,
                                    customer_name=opp.customer_name,
                                    agreed_price=winner.offered_price,
                                    started_on=now.date(),
                                    expected_complete_on=(
                                        now + timedelta(days=winner.offered_delivery_days)
                                    ).date(),
                                    status="in_progress",
                                )
                                scope_s.add(local_job)
                                scope_s.commit()
            except Exception:
                log.exception(
                    "shared_opp: kunde inte skapa lokalt Job hos vinnaren"
                )

            decided += 1

        if decided > 0:
            s.commit()
    return decided


# === Endpoints ===

@router.get("", response_model=list[SharedOpportunityOut])
def list_shared_opportunities(info: TokenInfo = Depends(require_token)):
    """Lista alla pågående/beslutade klass-pool-opps för elevens
    bransch. Triggar emit + decide om det är dags."""
    student_id = _require_student(info)
    from ..school.engines import master_session
    from ..school.models import (
        SharedOpportunity, SharedQuote, Student,
    )

    with session_scope() as scope_s:
        co = (
            scope_s.query(Company)
            .filter(Company.active.is_(True))
            .first()
        )
        if co is None or not co.industry_key:
            return []
        industry = co.industry_key
        company_name = co.name

    with master_session() as ms:
        stu = ms.get(Student, student_id)
        if stu is None:
            raise HTTPException(404, "Elev saknas")
        teacher_id = stu.teacher_id
        class_label = stu.class_label

    # Trigga emit + decide lazily (idempotent)
    try:
        _emit_shared_opportunities_if_due(teacher_id, industry, class_label)
        _decide_expired_opportunities(teacher_id)
    except Exception:
        log.exception("shared_opp: lazy-emit/decide misslyckades")

    now = datetime.utcnow()
    with master_session() as s:
        opps = (
            s.query(SharedOpportunity)
            .filter(
                SharedOpportunity.teacher_id == teacher_id,
                SharedOpportunity.industry_key == industry,
            )
            .order_by(SharedOpportunity.deadline_at.desc())
            .limit(20)
            .all()
        )
        out: list[SharedOpportunityOut] = []
        for opp in opps:
            quotes = (
                s.query(SharedQuote)
                .filter(SharedQuote.shared_opportunity_id == opp.id)
                .all()
            )
            my_quote = next(
                (q for q in quotes if q.student_id == student_id), None,
            )
            out.append(SharedOpportunityOut(
                id=opp.id,
                customer_name=opp.customer_name,
                customer_segment=opp.customer_segment,
                title=opp.title,
                description=opp.description,
                market_price=opp.market_price,
                expected_delivery_days=opp.expected_delivery_days,
                industry_key=opp.industry_key,
                deadline_at=opp.deadline_at.isoformat(),
                hours_until_deadline=max(
                    0.0,
                    (opp.deadline_at - now).total_seconds() / 3600.0,
                ),
                status=opp.status,
                n_competitors=len(quotes),
                has_my_quote=my_quote is not None,
                is_winner=(
                    my_quote is not None and my_quote.is_winner
                    if my_quote else None
                ),
                decision_explanation=opp.decision_explanation,
            ))
    return out


@router.post("/{opp_id}/quote", response_model=dict)
def submit_shared_quote(
    opp_id: int,
    body: SharedQuoteIn,
    info: TokenInfo = Depends(require_token),
):
    """Lämna ETT bud på en SharedOpportunity. Max 1 per elev/opp."""
    student_id = _require_student(info)
    from ..school.engines import master_session
    from ..school.models import (
        SharedOpportunity, SharedQuote, Student,
    )

    # Hämta elevens företag-namn för cache i SharedQuote
    with session_scope() as scope_s:
        co = (
            scope_s.query(Company)
            .filter(Company.active.is_(True))
            .first()
        )
        if co is None:
            raise HTTPException(400, "Du har inget aktivt företag")
        company_name = co.name

    with master_session() as ms:
        stu = ms.get(Student, student_id)
        if stu is None:
            raise HTTPException(404, "Elev saknas")
        teacher_id = stu.teacher_id

    with master_session() as s:
        opp = s.get(SharedOpportunity, opp_id)
        if opp is None or opp.teacher_id != teacher_id:
            raise HTTPException(404, "Förfrågan saknas")
        if opp.status != "open":
            raise HTTPException(409, "Deadline har passerat")
        if opp.deadline_at <= datetime.utcnow():
            raise HTTPException(409, "Deadline har passerat")

        # Existing kvoter?
        existing = (
            s.query(SharedQuote)
            .filter(
                SharedQuote.shared_opportunity_id == opp_id,
                SharedQuote.student_id == student_id,
            )
            .first()
        )
        if existing is not None:
            raise HTTPException(
                409, "Du har redan lämnat offert på denna förfrågan",
            )

        q = SharedQuote(
            shared_opportunity_id=opp_id,
            student_id=student_id,
            company_name=company_name,
            offered_price=body.offered_price,
            offered_delivery_days=body.offered_delivery_days,
            pitch_text=body.pitch_text,
        )
        s.add(q)
        s.commit()
        return {"ok": True, "quote_id": q.id}


@router.get("/{opp_id}/competitors", response_model=list[SharedQuoteRowOut])
def list_competitors(
    opp_id: int,
    info: TokenInfo = Depends(require_token),
):
    """Visa konkurrentbudgivning för en BESLUTAD opp.

    Pedagogiskt: när opp:en är decided får eleven se ALLA bud +
    AI:s motivering. Lärorikt att jämföra sin egen mot vinnarens.
    Bud döljs medan opp är open så elever inte kopierar varandra."""
    student_id = _require_student(info)
    from ..school.engines import master_session
    from ..school.models import (
        SharedOpportunity, SharedQuote, Student,
    )

    with master_session() as s:
        opp = s.get(SharedOpportunity, opp_id)
        if opp is None:
            raise HTTPException(404, "Förfrågan saknas")
        if opp.status not in ("decided", "expired"):
            return []  # döljs medan deadline är öppen

        quotes = (
            s.query(SharedQuote)
            .filter(SharedQuote.shared_opportunity_id == opp_id)
            .all()
        )
        student_ids = list({q.student_id for q in quotes})
        students = (
            s.query(Student).filter(Student.id.in_(student_ids)).all()
        )
        name_map = {st.id: st.display_name for st in students}
        out = []
        for q in quotes:
            out.append(SharedQuoteRowOut(
                student_display=name_map.get(q.student_id, "Anonym")
                + " · " + q.company_name,
                offered_price=q.offered_price,
                offered_delivery_days=q.offered_delivery_days,
                pitch_text=q.pitch_text,
                pitch_quality=q.pitch_quality,
                is_winner=q.is_winner,
                is_mine=(q.student_id == student_id),
            ))
        # Vinnaren först, övriga sorterade på pris
        out.sort(key=lambda r: (not r.is_winner, r.offered_price))
        return out
