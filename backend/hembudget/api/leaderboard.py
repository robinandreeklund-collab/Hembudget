"""Multi-leaderboard + entreprenörspoäng + badges.

Spec: Fas H · dev/feature-allabolag.md

12 kategorier · alla baseras på ClassCompanyShare-cache + master-DB-aggregat.
Per-vecka-vinnare → ClassWeeklyAward → driver social-motivation.
Per-elev-poäng + badges → StudentEntrepreneurScore.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel


from .deps import TokenInfo, require_token


log = logging.getLogger(__name__)

router = APIRouter(prefix="/v2/leaderboard", tags=["leaderboard"])


# === Kategorier ===

CATEGORIES = [
    {
        "key": "best_overall",
        "label": "Bäst i klassen",
        "emoji": "🏆",
        "metric": "total_points",
        "higher_is_better": True,
        "desc": "Total entreprenörspoäng · summan av alla mätningar",
    },
    {
        "key": "growth_rocket",
        "label": "Årets raket",
        "emoji": "📈",
        "metric": "growth_rate_4w",
        "higher_is_better": True,
        "desc": "Procentuell tillväxt 4 veckor",
    },
    {
        "key": "margin_king",
        "label": "Marginalkungen",
        "emoji": "💰",
        "metric": "margin_pct",
        "higher_is_better": True,
        "desc": "Högst vinstmarginal",
    },
    {
        "key": "customer_favorite",
        "label": "Kundernas favorit",
        "emoji": "🎯",
        "metric": "won_quotes_4w",
        "higher_is_better": True,
        "desc": "Flest vunna offerter senaste 4 v",
    },
    {
        "key": "stable",
        "label": "Stabilast",
        "emoji": "⚖️",
        "metric": "kassa",
        "higher_is_better": True,
        "desc": "Bäst likviditet · högst kassa",
    },
    {
        "key": "best_employer",
        "label": "Bästa arbetsgivare",
        "emoji": "🤝",
        "metric": "n_employees",
        "higher_is_better": True,
        "desc": "Flest anställda",
    },
    {
        "key": "delivery_pro",
        "label": "Leveransproffs",
        "emoji": "⚡",
        "metric": "reputation",
        "higher_is_better": True,
        "desc": "Högst rykte · proxy för leveranssäkerhet",
    },
    {
        "key": "credit_master",
        "label": "Kreditvärdig",
        "emoji": "🛡",
        "metric": "uc_score",
        "higher_is_better": True,
        "desc": "Bäst företags-UC",
    },
    {
        "key": "comeback",
        "label": "Comeback-kid",
        "emoji": "🌱",
        "metric": "comeback_score",
        "higher_is_better": True,
        "desc": "Bottennapp till framgång · största förbättringen",
    },
    {
        "key": "mentor",
        "label": "Mentor",
        "emoji": "🎓",
        "metric": "mentor_helps",
        "higher_is_better": True,
        "desc": "Hjälpt andra elev-bolag mest",
    },
    {
        "key": "innovator",
        "label": "Innovatör",
        "emoji": "💡",
        "metric": "pivot_success",
        "higher_is_better": True,
        "desc": "Pivotat smart · ökad oms efter pivot",
    },
    {
        "key": "level",
        "label": "Klättraren",
        "emoji": "🚀",
        "metric": "company_level_rank",
        "higher_is_better": True,
        "desc": "Högst företagsnivå (Marknadsledare = 4)",
    },
]


# === Score-helper ===

LEVEL_RANK = {"startup": 1, "vaxande": 2, "etablerat": 3, "marknadsledare": 4}


def _row_metric(row, metric: str) -> float:
    """Hämta metric-värde från ClassCompanyShare-rad."""
    if metric == "total_points":
        return _entrepreneur_points(row)
    if metric == "growth_rate_4w":
        return float(row.revenue_4w)  # förenklat utan historik
    if metric == "margin_pct":
        return float(row.margin_pct)
    if metric == "won_quotes_4w":
        return 0.0  # placeholder · kräver Quote-historik (fas senare)
    if metric == "kassa":
        return float(row.kassa)
    if metric == "n_employees":
        return float(row.n_employees)
    if metric == "reputation":
        return float(row.reputation)
    if metric == "uc_score":
        return float(row.uc_score)
    if metric == "comeback_score":
        return 0.0  # placeholder
    if metric == "mentor_helps":
        return 0.0  # placeholder · Fas I
    if metric == "pivot_success":
        return 0.0  # placeholder
    if metric == "company_level_rank":
        return float(LEVEL_RANK.get(row.company_level, 1))
    return 0.0


def _entrepreneur_points(row) -> float:
    """Sammansatt entreprenörspoäng."""
    return (
        row.profit_4w * 0.4
        + row.kassa * 0.2
        + row.reputation * 200
        + row.uc_score * 100
        + row.n_employees * 5000
        + LEVEL_RANK.get(row.company_level, 1) * 10000
    )


# === Schemas ===

class LeaderRowOut(BaseModel):
    rank: int
    student_id: int
    student_display: str
    company_name: str
    company_level: str
    metric_value: float
    is_mine: bool


class LeaderboardCategoryOut(BaseModel):
    key: str
    label: str
    emoji: str
    desc: str
    rows: list[LeaderRowOut]


# === Endpoints ===

@router.get("/categories", response_model=list[LeaderboardCategoryOut])
def get_all_categories(info: TokenInfo = Depends(require_token)):
    """Lista topp-3 per kategori. Ger dataset till frontend för
    multi-leaderboard."""
    from ..school.engines import master_session
    from ..school.models import ClassCompanyShare, Student

    if info.role == "teacher" and info.teacher_id:
        teacher_id = info.teacher_id
        my_sid: Optional[int] = None
    elif info.role == "student" and info.student_id:
        with master_session() as s:
            stu = s.get(Student, info.student_id)
            if stu is None:
                raise HTTPException(404, "Elev saknas")
            teacher_id = stu.teacher_id
            my_sid = info.student_id
    else:
        raise HTTPException(403, "Endast lärare/elev")

    with master_session() as s:
        # Privacy-fix: opublicerade bolag dyker INTE upp i leaderboard.
        # Allabolag-flikens scoreboard filtrerade is_published=True för
        # elever men leaderboard saknade samma filter → en elev kunde
        # togglat "Dölj" i Allabolag och ändå hamna i topplistorna med
        # namn + ägare exponerade. Lärare ser ALLA (även dolda) eftersom
        # is_mine inte gäller här.
        q = s.query(ClassCompanyShare).filter(
            ClassCompanyShare.teacher_id == teacher_id,
        )
        if info.role == "student":
            # Eleven ser sig själv + andras publicerade
            q = q.filter(
                (ClassCompanyShare.owner_student_id == my_sid)
                | (ClassCompanyShare.is_published.is_(True))
            )
        rows = q.all()
        if not rows:
            return []
        sids = list({r.owner_student_id for r in rows})
        students = (
            s.query(Student).filter(Student.id.in_(sids)).all()
        )
        names = {st.id: st.display_name for st in students}

    out: list[LeaderboardCategoryOut] = []
    for cat in CATEGORIES:
        # Score varje rad
        ranked = sorted(
            rows,
            key=lambda r: _row_metric(r, cat["metric"]),
            reverse=cat["higher_is_better"],
        )
        topn = ranked[:5]
        leader_rows = []
        for i, r in enumerate(topn):
            leader_rows.append(LeaderRowOut(
                rank=i + 1,
                student_id=r.owner_student_id,
                student_display=names.get(r.owner_student_id, "?"),
                company_name=r.company_name,
                company_level=r.company_level,
                metric_value=_row_metric(r, cat["metric"]),
                is_mine=(r.owner_student_id == my_sid),
            ))
        out.append(LeaderboardCategoryOut(
            key=cat["key"],
            label=cat["label"],
            emoji=cat["emoji"],
            desc=cat["desc"],
            rows=leader_rows,
        ))
    return out


# === Badges ===

BADGES: dict[str, dict] = {
    "first_company": {
        "emoji": "🚀",
        "label": "Första bolaget",
        "desc": "Du startade ditt första företag.",
    },
    "first_employee": {
        "emoji": "🤝",
        "label": "Första anställning",
        "desc": "Du anställde din första klasskompis.",
    },
    "first_won_offer": {
        "emoji": "🎯",
        "label": "Första vunna offerten",
        "desc": "Kunden valde dig.",
    },
    "first_loss": {
        "emoji": "📚",
        "label": "Första lärdomen",
        "desc": "Du förlorade en offert · viktigt att lära sig.",
    },
    "level_vaxande": {
        "emoji": "🌱",
        "label": "Växande företag",
        "desc": "Du nådde nivå Växande.",
    },
    "level_etablerat": {
        "emoji": "🏛",
        "label": "Etablerat företag",
        "desc": "Du nådde nivå Etablerat.",
    },
    "level_marknadsledare": {
        "emoji": "👑",
        "label": "Marknadsledare",
        "desc": "Du blev marknadsledare i klassen.",
    },
    "uc_aaa": {
        "emoji": "🛡",
        "label": "AAA-kreditvärdighet",
        "desc": "Ditt bolag har högsta UC-rating.",
    },
    "annual_report_approved": {
        "emoji": "📋",
        "label": "Bolagsverket godkänd",
        "desc": "AI Bolagsverket godkände din årsredovisning.",
    },
    "first_loan": {
        "emoji": "💳",
        "label": "Första lånet",
        "desc": "Du tog ditt första företagslån.",
    },
    "loan_repaid": {
        "emoji": "✅",
        "label": "Lån återbetalt",
        "desc": "Du betalade av ett lån i tid.",
    },
    "five_employees": {
        "emoji": "👥",
        "label": "Lagledare",
        "desc": "5 anställda på lönelistan.",
    },
}


def _detect_badges(row) -> dict[str, str]:
    """Identifiera vilka badges en rad uppfyller. Returnerar
    {badge_key: earned_at_iso} för nyligen vunna."""
    now = datetime.utcnow().isoformat() + "Z"
    earned: dict[str, str] = {}

    # Always-on förstaföretag
    earned["first_company"] = now
    if row.company_level == "vaxande":
        earned["level_vaxande"] = now
    elif row.company_level == "etablerat":
        earned["level_vaxande"] = now
        earned["level_etablerat"] = now
    elif row.company_level == "marknadsledare":
        earned["level_vaxande"] = now
        earned["level_etablerat"] = now
        earned["level_marknadsledare"] = now
    if row.uc_rating == "AAA":
        earned["uc_aaa"] = now
    if row.annual_report_status == "approved":
        earned["annual_report_approved"] = now
    if row.n_employees >= 1:
        earned["first_employee"] = now
    if row.n_employees >= 5:
        earned["five_employees"] = now
    return earned


class BadgeOut(BaseModel):
    key: str
    emoji: str
    label: str
    desc: str
    earned_at: Optional[str]
    is_earned: bool


class StudentScoreOut(BaseModel):
    student_id: int
    total_points: int
    badges: list[BadgeOut]
    n_earned: int
    n_total: int


@router.get("/me", response_model=StudentScoreOut)
def my_score(info: TokenInfo = Depends(require_token)):
    if info.role != "student" or info.student_id is None:
        raise HTTPException(403, "Endast elever")
    student_id = info.student_id

    from ..school.engines import master_session
    from ..school.models import (
        ClassCompanyShare, StudentEntrepreneurScore,
    )
    with master_session() as s:
        share = (
            s.query(ClassCompanyShare)
            .filter(ClassCompanyShare.owner_student_id == student_id)
            .first()
        )
        if share is None:
            return StudentScoreOut(
                student_id=student_id,
                total_points=0,
                badges=[
                    BadgeOut(
                        key=k, emoji=b["emoji"], label=b["label"],
                        desc=b["desc"], earned_at=None, is_earned=False,
                    )
                    for k, b in BADGES.items()
                ],
                n_earned=0,
                n_total=len(BADGES),
            )
        points = int(_entrepreneur_points(share))
        earned = _detect_badges(share)

        # Persist
        score = s.get(StudentEntrepreneurScore, student_id)
        if score is None:
            score = StudentEntrepreneurScore(
                student_id=student_id,
                total_points=points,
                badges=earned,
            )
            s.add(score)
        else:
            score.total_points = points
            score.badges = earned
            score.last_recomputed_at = datetime.utcnow()
        s.commit()

        out_badges: list[BadgeOut] = []
        for k, b in BADGES.items():
            out_badges.append(BadgeOut(
                key=k,
                emoji=b["emoji"],
                label=b["label"],
                desc=b["desc"],
                earned_at=earned.get(k),
                is_earned=k in earned,
            ))
        return StudentScoreOut(
            student_id=student_id,
            total_points=points,
            badges=out_badges,
            n_earned=len(earned),
            n_total=len(BADGES),
        )
