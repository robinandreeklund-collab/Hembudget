from __future__ import annotations

import json
import logging
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..budget.forecast import CashflowForecaster
from ..budget.monthly import MonthlyBudgetService
from ..db.models import Category, ChatMessage, Subscription, Transaction
from ..llm.client import LLMUnavailable, LMStudioClient
from ..llm.prompts import CHAT_SYSTEM
from ..scenarios.engine import ScenarioEngine
from ..subscriptions.detector import SubscriptionDetector

log = logging.getLogger(__name__)


TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_month_summary",
            "description": "Hämta månadens budget vs utfall per kategori.",
            "parameters": {
                "type": "object",
                "properties": {"month": {"type": "string", "description": "YYYY-MM"}},
                "required": ["month"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_transactions",
            "description": "Sök transaktioner på kategori, datumintervall eller merchant.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "merchant": {"type": "string"},
                    "from_date": {"type": "string"},
                    "to_date": {"type": "string"},
                    "min_amount": {"type": "number"},
                    "max_amount": {"type": "number"},
                    "limit": {"type": "integer", "default": 50},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "top_categories",
            "description": "Lista topp N kategorier (per utgiftsbelopp) under ett intervall.",
            "parameters": {
                "type": "object",
                "properties": {
                    "from_date": {"type": "string"},
                    "to_date": {"type": "string"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["from_date", "to_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_subscriptions",
            "description": "Hitta återkommande dragningar (prenumerationer).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "forecast_cashflow",
            "description": "Projicera kassaflöde framåt baserat på historiskt snitt.",
            "parameters": {
                "type": "object",
                "properties": {"months": {"type": "integer", "default": 6}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_scenario",
            "description": "Beräkna bolåne-, sparmåls- eller flyttscenario.",
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["mortgage", "savings_goal", "move"]},
                    "params": {"type": "object"},
                },
                "required": ["kind", "params"],
            },
        },
    },
]


def _d(x) -> float:
    try:
        return float(x)
    except Exception:
        return 0.0


class ChatAgent:
    """Tool-using agent som läser ur DB och räknar deterministiskt via backend."""

    def __init__(self, session: Session, llm: LMStudioClient, max_tool_iters: int = 5):
        self.session = session
        self.llm = llm
        self.max_tool_iters = max_tool_iters

    # --- Tool implementations ---

    def _tool_get_month_summary(self, month: str) -> dict:
        s = MonthlyBudgetService(self.session).summary(month)
        return {
            "month": s.month,
            "income": _d(s.income),
            "expenses": _d(s.expenses),
            "savings": _d(s.savings),
            "savings_rate": s.savings_rate,
            "lines": [
                {"category": l.category, "planned": _d(l.planned), "actual": _d(l.actual), "diff": _d(l.diff)}
                for l in s.lines
            ],
        }

    def _tool_query_transactions(self, **kw) -> dict:
        q = self.session.query(Transaction)
        if kw.get("category"):
            q = q.join(Category, Category.id == Transaction.category_id).filter(
                Category.name == kw["category"]
            )
        if kw.get("merchant"):
            q = q.filter(Transaction.normalized_merchant.ilike(f"%{kw['merchant'].upper()}%"))
        if kw.get("from_date"):
            q = q.filter(Transaction.date >= date.fromisoformat(kw["from_date"]))
        if kw.get("to_date"):
            q = q.filter(Transaction.date <= date.fromisoformat(kw["to_date"]))
        if kw.get("min_amount") is not None:
            q = q.filter(Transaction.amount >= Decimal(str(kw["min_amount"])))
        if kw.get("max_amount") is not None:
            q = q.filter(Transaction.amount <= Decimal(str(kw["max_amount"])))
        rows = q.order_by(Transaction.date.desc()).limit(int(kw.get("limit", 50))).all()
        return {
            "transactions": [
                {
                    "date": t.date.isoformat(),
                    "amount": _d(t.amount),
                    "description": t.raw_description,
                    "merchant": t.normalized_merchant,
                    "category": t.category.name if t.category else None,
                }
                for t in rows
            ]
        }

    def _tool_top_categories(self, from_date: str, to_date: str, limit: int = 10) -> dict:
        rows = self.session.execute(
            select(Category.name, func.sum(Transaction.amount).label("total"))
            .join(Category, Category.id == Transaction.category_id, isouter=True)
            .where(
                Transaction.date >= date.fromisoformat(from_date),
                Transaction.date <= date.fromisoformat(to_date),
                Transaction.amount < 0,
            )
            .group_by(Category.name)
            .order_by(func.sum(Transaction.amount).asc())
            .limit(limit)
        ).all()
        return {"top": [{"category": n or "Okategoriserat", "total": _d(t)} for n, t in rows]}

    def _tool_find_subscriptions(self) -> dict:
        # First return already-persisted, fall back to live detection
        subs = self.session.query(Subscription).filter(Subscription.active.is_(True)).all()
        if not subs:
            subs_live = SubscriptionDetector(self.session).detect()
            return {
                "subscriptions": [
                    {
                        "merchant": s.merchant,
                        "amount": _d(s.amount),
                        "interval_days": s.interval_days,
                        "next_expected_date": s.next_expected_date.isoformat(),
                    }
                    for s in subs_live
                ]
            }
        return {
            "subscriptions": [
                {
                    "merchant": s.merchant,
                    "amount": _d(s.amount),
                    "interval_days": s.interval_days,
                    "next_expected_date": s.next_expected_date.isoformat() if s.next_expected_date else None,
                }
                for s in subs
            ]
        }

    def _tool_forecast_cashflow(self, months: int = 6) -> dict:
        f = CashflowForecaster(self.session).project(horizon_months=months)
        return {
            "forecast": [
                {
                    "month": m.month,
                    "income": _d(m.projected_income),
                    "expenses": _d(m.projected_expenses),
                    "net": _d(m.projected_net),
                }
                for m in f
            ]
        }

    def _tool_calculate_scenario(self, kind: str, params: dict) -> dict:
        return ScenarioEngine().run(kind, params)

    def _dispatch(self, name: str, args: dict) -> dict:
        fn = {
            "get_month_summary": self._tool_get_month_summary,
            "query_transactions": self._tool_query_transactions,
            "top_categories": self._tool_top_categories,
            "find_subscriptions": self._tool_find_subscriptions,
            "forecast_cashflow": self._tool_forecast_cashflow,
            "calculate_scenario": self._tool_calculate_scenario,
        }.get(name)
        if fn is None:
            return {"error": f"unknown_tool:{name}"}
        try:
            return fn(**args)
        except Exception as exc:
            log.exception("tool %s failed", name)
            return {"error": str(exc)}

    # --- Main loop ---

    def ask(self, session_id: str, user_message: str) -> str:
        history_rows = (
            self.session.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.id.asc())
            .all()
        )
        messages: list[dict[str, Any]] = [{"role": "system", "content": CHAT_SYSTEM}]
        for m in history_rows:
            entry: dict[str, Any] = {"role": m.role, "content": m.content}
            if m.tool_calls:
                entry["tool_calls"] = m.tool_calls.get("tool_calls") if isinstance(m.tool_calls, dict) else None
            messages.append(entry)
        messages.append({"role": "user", "content": user_message})

        self.session.add(ChatMessage(session_id=session_id, role="user", content=user_message))
        self.session.flush()

        final_text: str = ""
        for _ in range(self.max_tool_iters):
            try:
                resp = self.llm.tool_call(messages, tools=TOOLS, temperature=0.1)
            except LLMUnavailable as exc:
                final_text = f"LM Studio är inte tillgänglig: {exc}"
                break
            choice = resp.choices[0].message
            tool_calls = getattr(choice, "tool_calls", None)
            if tool_calls:
                messages.append(
                    {
                        "role": "assistant",
                        "content": choice.content or "",
                        "tool_calls": [tc.model_dump() for tc in tool_calls],
                    }
                )
                for tc in tool_calls:
                    name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    result = self._dispatch(name, args)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(result, ensure_ascii=False, default=str),
                        }
                    )
                continue
            final_text = choice.content or ""
            break

        self.session.add(
            ChatMessage(session_id=session_id, role="assistant", content=final_text)
        )
        self.session.flush()
        return final_text
