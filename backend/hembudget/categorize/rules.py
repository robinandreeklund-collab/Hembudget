from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy.orm import Session

from ..db.models import Category, Rule


@dataclass
class RuleMatch:
    rule_id: int
    category_id: int
    priority: int


class RuleEngine:
    """Regex / substring-baserad regelmotor. Prioritet avgör vid flera matchningar."""

    def __init__(self, rules: Iterable[Rule]):
        self._rules: list[tuple[Rule, re.Pattern | None]] = []
        for r in rules:
            pat = None
            if r.is_regex:
                try:
                    pat = re.compile(r.pattern, re.IGNORECASE)
                except re.error:
                    pat = None
            self._rules.append((r, pat))
        self._rules.sort(key=lambda rp: -rp[0].priority)

    def match(self, description: str, amount: float | None = None) -> RuleMatch | None:
        desc_l = (description or "").lower()
        for rule, pat in self._rules:
            if pat is not None:
                if pat.search(description or ""):
                    if self._sign_ok(rule, amount):
                        return RuleMatch(rule.id, rule.category_id, rule.priority)
            else:
                if rule.pattern.lower() in desc_l and self._sign_ok(rule, amount):
                    return RuleMatch(rule.id, rule.category_id, rule.priority)
        return None

    def _sign_ok(self, rule: Rule, amount: float | None) -> bool:
        # "Swish in" only applies to positive amounts; "Lön" same.
        return True  # placeholder — can be extended per-category


def load_rules(session: Session) -> RuleEngine:
    rules = session.query(Rule).order_by(Rule.priority.desc()).all()
    return RuleEngine(rules)


def seed_categories_and_rules(session: Session) -> None:
    """Idempotent: insert default categories and seed rules if empty."""
    from .seed_rules import DEFAULT_CATEGORIES, SEED_RULES

    # Categories
    existing = {c.name: c for c in session.query(Category).all()}
    for name, parent_name, icon in DEFAULT_CATEGORIES:
        if name in existing:
            continue
        parent_id = existing[parent_name].id if parent_name and parent_name in existing else None
        cat = Category(name=name, parent_id=parent_id, icon=icon)
        session.add(cat)
        session.flush()
        existing[name] = cat

    # Seed rules
    if session.query(Rule).count() > 0:
        return
    for pattern, cat_name, priority in SEED_RULES:
        cat = existing.get(cat_name)
        if not cat:
            continue
        session.add(
            Rule(
                pattern=pattern,
                is_regex=False,
                category_id=cat.id,
                priority=priority,
                source="seed",
            )
        )


def create_rule_from_correction(
    session: Session, pattern: str, category_id: int, priority: int = 120
) -> Rule:
    """When a user corrects a transaction's category, persist a rule to learn."""
    existing = (
        session.query(Rule)
        .filter(Rule.pattern == pattern, Rule.category_id == category_id)
        .first()
    )
    if existing:
        existing.priority = max(existing.priority, priority)
        return existing
    rule = Rule(pattern=pattern, is_regex=False, category_id=category_id,
                priority=priority, source="user")
    session.add(rule)
    session.flush()
    return rule
