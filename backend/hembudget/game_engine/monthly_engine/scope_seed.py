"""Säkerställ att elevens scope-DB har de konton + kategorier som
Monthly Engine behöver innan första ticken.

Idempotent: kollar om kontona redan finns och skapar bara saknade.
Default-kategorierna seedas av `_seed_tenant_if_needed` redan, så vi
behöver bara säkerställa konton här.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy.orm import Session

from ...db.models import Account, Category
from ..profile_generator.schema import GeneratedProfile

log = logging.getLogger(__name__)


# Konton vi alltid säkerställer för en spelare i Monthly Engine
DEFAULT_ACCOUNTS = [
    {
        "name": "Lönekonto",
        "bank": "Spelbanken",
        "type": "checking",
        "account_number": "1234 56 78901",
    },
    {
        "name": "Sparkonto",
        "bank": "Spelbanken",
        "type": "savings",
        "account_number": "9876 54 32109",
    },
    {
        "name": "ISK",
        "bank": "Spelbanken",
        "type": "isk",
        "account_number": "1111 22 33344",
    },
]


def ensure_scope_accounts(
    s: Session,
    profile: GeneratedProfile,
) -> dict[str, Account]:
    """Säkerställ att lönekonto, sparkonto och ISK finns i scope-DB:n.

    Returnerar en dict {"lonekonto": Account, "sparkonto": Account, ...}
    så att caller kan referera till rätt konto vid Transaction-skapelse.

    Lönekontots opening_balance sätts till en månadsvärd buffer så
    eleven inte hamnar i minus omedelbart vid första utgift dag 1.
    """
    by_type: dict[str, Account] = {}

    for spec in DEFAULT_ACCOUNTS:
        existing = (
            s.query(Account)
            .filter(Account.type == spec["type"])
            .first()
        )
        if existing is not None:
            by_type[spec["type"]] = existing
            continue

        opening = Decimal("0")
        if spec["type"] == "checking":
            # Lönekonto-buffer = ~2 hushålls-månadsnetto. Tidigare
            # baserades det på main.monthly_net vilket gjorde att
            # sambo-karaktärer med låg main-lön (t.ex. Gymnasie-elev
            # deltid 4 446 kr) startade på minus i 1:a månaden trots
            # att partnern drog in 21 000 kr. Använder nu
            # household_net_monthly som speglar verkligt cashflow.
            household_net = (
                profile.household_net_monthly
                if profile.household_net_monthly
                else profile.monthly_net
            )
            opening = Decimal(household_net * 2)
        elif spec["type"] == "savings":
            household_net = (
                profile.household_net_monthly
                if profile.household_net_monthly
                else profile.monthly_net
            )
            opening = Decimal(household_net)

        acc = Account(
            name=spec["name"],
            bank=spec["bank"],
            type=spec["type"],
            account_number=spec["account_number"],
            opening_balance=opening,
        )
        s.add(acc)
        s.flush()
        by_type[spec["type"]] = acc

    return {
        "lonekonto": by_type["checking"],
        "sparkonto": by_type["savings"],
        "isk": by_type["isk"],
    }


def get_or_create_category(s: Session, name: str) -> Category:
    """Hämta default-kategori eller skapa ad hoc om den inte finns.

    Default-kategorier seedas vid första scope-init, men nya behov
    (t.ex. nya konsumentverket-kategorier) kan dyka upp över tid.
    """
    cat = s.query(Category).filter(Category.name == name).first()
    if cat is not None:
        return cat
    cat = Category(name=name)
    s.add(cat)
    s.flush()
    return cat
