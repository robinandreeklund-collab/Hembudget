"""Frisktandvård-seed för scope-DB.

Skapar InsurancePolicy(kind='frisktandvard') + välkomstmail för
karaktärer som fått frisktandvård i sin StudentProfile. Idempotent.
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from ...db.models import InsurancePolicy, MailItem


log = logging.getLogger(__name__)


def seed_dental_for_scope(
    s: Session, *, student_id: int, today_game: date,
) -> dict:
    """Skapar frisktandvård-policy + välkomstmail om eleven har det
    i sin StudentProfile. Idempotent."""
    from ...school.engines import master_session
    from ...school.models import StudentProfile

    with master_session() as ms:
        prof = (
            ms.query(StudentProfile)
            .filter(StudentProfile.student_id == student_id)
            .first()
        )
        if prof is None:
            return {"skipped": "no_profile"}
        if not bool(getattr(prof, "has_frisktandvard", False)):
            return {"skipped": "no_dental"}
        tier = getattr(prof, "frisktandvard_tier", None) or 1
        cat = getattr(prof, "frisktandvard_age_category", None) or "normal"
        premium = getattr(
            prof, "frisktandvard_premium_monthly", None,
        ) or 65

    created = {"insurance": False, "welcome_mail": False}

    existing = (
        s.query(InsurancePolicy)
        .filter(
            InsurancePolicy.kind == "frisktandvard",
            InsurancePolicy.status == "active",
        )
        .first()
    )
    if existing is None:
        s.add(InsurancePolicy(
            provider="Folktandvården",
            name=f"Frisktandvård · grupp {tier}",
            kind="frisktandvard",
            premium_monthly=Decimal(str(premium)),
            coverage_amount=None,  # täcker tjänster, inte belopp
            deductible=None,
            autogiro=True,
            status="active",
            started_on=today_game,
            notes=(
                f"Prisgrupp {tier} ({cat}) · täcker karieskontroll, "
                "lagningar, tandstensborttagning, rotfyllning enl. "
                "Folktandvårdens avtal. Premie {premium} kr/mån "
                "(autogiro)."
            ).replace("{premium}", str(premium)),
        ))
        created["insurance"] = True

    welcome_subj = "Välkommen som frisktandvård-patient"
    existing_w = (
        s.query(MailItem).filter(MailItem.subject == welcome_subj).first()
    )
    if existing_w is None:
        cat_label = (
            "20-23 eller 67+ · ATB-rabatt aktiv"
            if cat == "atb"
            else "24-66 · normalpris"
        )
        s.add(MailItem(
            sender="Folktandvården",
            sender_short="FTV",
            sender_kind="agency",
            sender_meta=f"Frisktandvård · grupp {tier}",
            mail_type="info",
            subject=welcome_subj,
            body_meta=f"{premium} kr/mån · grupp {tier}",
            body=(
                "Hej och välkommen!\n\n"
                f"Du är inskriven på frisktandvård i prisgrupp {tier} "
                "baserat på din senaste tandkontroll. Avtalet täcker "
                "allt inom Folktandvårdens utbud i Sverige:\n\n"
                "• Regelbundna kontroller\n"
                "• Lagningar (karies)\n"
                "• Tandstensborttagning\n"
                "• Rotfyllningar\n"
                "• Akut tandvård (om plötslig värk eller skada)\n\n"
                f"Premie: {premium} kr/mån (autogiro)\n"
                f"Pristyp: {cat_label}\n\n"
                "Avtalet löper 3 år. Du kan säga upp via Mina sidor. "
                "Vid avtalsslut görs ny kontroll och du kan hamna i "
                "en högre/lägre prisgrupp.\n\n"
                "Vänliga hälsningar,\n"
                "Folktandvården"
            ),
            amount=None,
            due_date=None,
            status="unhandled",
            released_at=None,
        ))
        created["welcome_mail"] = True

    s.flush()
    return created
