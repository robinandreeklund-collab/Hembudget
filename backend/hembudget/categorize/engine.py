from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from sqlalchemy.orm import Session

from ..db.models import Category, Transaction
from ..llm.client import LLMUnavailable, LMStudioClient
from ..llm.prompts import CATEGORIZATION_SYSTEM
from ..config import settings
from .rules import RuleEngine, load_rules

log = logging.getLogger(__name__)


@dataclass
class CategorizationResult:
    index: int
    category_id: int | None
    merchant: str | None
    confidence: float
    source: str  # "rule" | "history" | "llm" | "uncategorized"
    reason: str = ""


def normalize_merchant(description: str) -> str:
    """Remove city suffixes, card numbers, reference codes to get a stable merchant name."""
    s = description or ""
    s = re.sub(r"\*\s*\d+", "", s)               # *1234 references (handle first)
    s = re.sub(r"\b\d{4,}\b", "", s)             # long numbers
    s = re.sub(r"\[[^\]]+\]", "", s)             # [city]
    s = re.sub(r"\s{2,}", " ", s).strip(" -.,;|*")
    return s.upper()[:120]


class CategorizationEngine:
    def __init__(self, session: Session, llm: LMStudioClient | None = None):
        self.session = session
        self.llm = llm
        self._rule_engine: RuleEngine | None = None
        self._category_by_name: dict[str, int] = {}
        self._category_names: list[str] = []

    def _rules(self) -> RuleEngine:
        if self._rule_engine is None:
            self._rule_engine = load_rules(self.session)
        return self._rule_engine

    def _categories(self) -> dict[str, int]:
        if not self._category_by_name:
            for c in self.session.query(Category).all():
                self._category_by_name[c.name] = c.id
                self._category_names.append(c.name)
        return self._category_by_name

    def _history_match(self, normalized: str) -> int | None:
        if not normalized:
            return None
        row = (
            self.session.query(Transaction)
            .filter(
                Transaction.normalized_merchant == normalized,
                Transaction.user_verified.is_(True),
                Transaction.category_id.is_not(None),
            )
            .order_by(Transaction.id.desc())
            .first()
        )
        return row.category_id if row else None

    def categorize_batch(self, transactions: list[Transaction]) -> list[CategorizationResult]:
        cats = self._categories()
        rules = self._rules()
        results: list[CategorizationResult] = []
        unknown: list[tuple[int, Transaction]] = []

        for i, tx in enumerate(transactions):
            normalized = normalize_merchant(tx.raw_description)
            tx.normalized_merchant = normalized

            # 1. rules
            m = rules.match(tx.raw_description, float(tx.amount))
            if m:
                results.append(
                    CategorizationResult(i, m.category_id, normalized, 1.0, "rule", "regelmotor")
                )
                continue

            # 2. history
            hist = self._history_match(normalized)
            if hist is not None:
                results.append(
                    CategorizationResult(i, hist, normalized, 0.9, "history", "tidigare rättat")
                )
                continue

            # 3. LLM fallback
            results.append(
                CategorizationResult(i, None, normalized, 0.0, "uncategorized", "")
            )
            unknown.append((i, tx))

        if unknown and self.llm is not None and self.llm.is_alive():
            llm_results = self._llm_categorize(unknown)
            for i, llm_res in llm_results.items():
                results[i] = llm_res

        return results

    def _llm_categorize(
        self, unknown: list[tuple[int, Transaction]]
    ) -> dict[int, CategorizationResult]:
        cats = self._categories()
        out: dict[int, CategorizationResult] = {}
        batch_size = settings.categorization_batch_size
        system = CATEGORIZATION_SYSTEM.replace("{categories}", ", ".join(sorted(cats.keys())))

        schema = {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "index": {"type": "integer"},
                            "category": {"type": "string"},
                            "merchant": {"type": "string"},
                            "confidence": {"type": "number"},
                            "reason": {"type": "string"},
                        },
                        "required": ["index", "category", "confidence"],
                    },
                }
            },
            "required": ["items"],
        }

        for start in range(0, len(unknown), batch_size):
            chunk = unknown[start : start + batch_size]
            lines = [
                json.dumps(
                    {
                        "index": global_i,
                        "date": tx.date.isoformat(),
                        "amount": float(tx.amount),
                        "description": tx.raw_description,
                    },
                    ensure_ascii=False,
                )
                for (global_i, tx) in chunk
            ]
            user = "Kategorisera följande:\n" + "\n".join(lines)
            try:
                resp = self.llm.complete_json(
                    [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    schema=schema,
                    temperature=0.0,
                )
            except LLMUnavailable as exc:
                log.warning("LLM categorize batch failed: %s", exc)
                continue

            for item in resp.get("items", []):
                idx = item.get("index")
                cat_name = item.get("category")
                cat_id = cats.get(cat_name)
                if cat_id is None or idx is None:
                    continue
                out[idx] = CategorizationResult(
                    index=idx,
                    category_id=cat_id,
                    merchant=item.get("merchant") or None,
                    confidence=float(item.get("confidence", 0.5)),
                    source="llm",
                    reason=item.get("reason", ""),
                )
        return out

    def apply_results(
        self, transactions: list[Transaction], results: list[CategorizationResult]
    ) -> None:
        for tx, r in zip(transactions, results):
            if r.category_id is not None:
                tx.category_id = r.category_id
                tx.ai_confidence = r.confidence
            if r.merchant:
                tx.normalized_merchant = r.merchant
