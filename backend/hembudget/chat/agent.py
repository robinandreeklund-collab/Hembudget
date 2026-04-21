"""Chat-agent som orkestrerar LM Studio med tool-use.

Verktygsimplementationerna ligger i chat/tools.py — den här modulen
binder bara ihop dem med LLM:en och chat-historiken i DB."""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from ..db.models import ChatMessage
from ..llm.client import LLMUnavailable, LMStudioClient
from ..llm.prompts import CHAT_SYSTEM
from . import tools

log = logging.getLogger(__name__)


# JSON-schema-definitioner för varje verktyg. LM Studio får hela listan
# och får själva välja vilka att anropa.
TOOLS: list[dict[str, Any]] = [
    # -- Befintliga --
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
            "description": (
                "Sök transaktioner efter kategori, datumintervall, merchant, belopp "
                "eller konto. Returnerar även splits per transaktion."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "merchant": {"type": "string"},
                    "from_date": {"type": "string"},
                    "to_date": {"type": "string"},
                    "min_amount": {"type": "number"},
                    "max_amount": {"type": "number"},
                    "account_id": {"type": "integer"},
                    "limit": {"type": "integer", "default": 50},
                    "include_transfers": {"type": "boolean", "default": False},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "top_categories",
            "description": (
                "Topp N utgiftskategorier över ett intervall. Honorerar "
                "transaktionsuppdelningar så en faktura splittad på el/vatten/bredband "
                "syns som separata rader."
            ),
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
            "description": "Projicera kassaflöde N månader framåt från historiskt snitt.",
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
            "description": (
                "Beräkna bolåne-, sparmåls- eller flyttscenario. "
                "kind ∈ {mortgage, savings_goal, move}."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["mortgage", "savings_goal", "move"],
                    },
                    "params": {"type": "object"},
                },
                "required": ["kind", "params"],
            },
        },
    },
    # -- Nya: kontostatus & balansgrafer --
    {
        "type": "function",
        "function": {
            "name": "get_accounts",
            "description": "Lista alla konton med typ, bank och nuvarande saldo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "as_of": {
                        "type": "string",
                        "description": "YYYY-MM-DD; default idag",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_account_balance",
            "description": "Saldo på ett specifikt konto vid en tidpunkt.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account_id": {"type": "integer"},
                    "as_of": {"type": "string"},
                },
                "required": ["account_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_balance_history",
            "description": "Månadsvisa slutsaldon för ett eller alla konton.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account_id": {"type": "integer"},
                    "months": {"type": "integer", "default": 6},
                },
            },
        },
    },
    # -- Nya: planerade poster --
    {
        "type": "function",
        "function": {
            "name": "get_upcoming",
            "description": (
                "Lista planerade fakturor (bill) eller löner (income) med eventuella "
                "fakturarader (el/vatten/bredband-splits)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["bill", "income"]},
                    "from_date": {"type": "string"},
                    "to_date": {"type": "string"},
                    "only_unmatched": {"type": "boolean", "default": True},
                    "owner": {"type": "string"},
                },
            },
        },
    },
    # -- Nya: lån --
    {
        "type": "function",
        "function": {
            "name": "get_loans",
            "description": (
                "Lista lån med aktuellt saldo, betalad amortering, ränta totalt, "
                "LTV (om bostadsvärde finns) och antal betalningar."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "active_only": {"type": "boolean", "default": True}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_loan_schedule",
            "description": "Kommande schemalagda lånebetalningar (ränta + amortering).",
            "parameters": {
                "type": "object",
                "properties": {
                    "loan_id": {"type": "integer"},
                    "months": {"type": "integer", "default": 12},
                },
            },
        },
    },
    # -- Nya: sparande, scenarion, skatt --
    {
        "type": "function",
        "function": {
            "name": "get_goals",
            "description": "Sparmål med progress (current/target + progress_ratio).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_scenarios",
            "description": "Sparade scenarion (bolån/sparmål/flytt) med deras input och resultat.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_tax_events",
            "description": (
                "Skatterelaterade händelser (ISK-insättning, K4-vinst, ROT, RUT, "
                "bolåneräntor). Summerar per typ."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {"type": "integer"},
                    "type": {
                        "type": "string",
                        "enum": ["isk_deposit", "k4_sale", "rot", "rut", "interest"],
                    },
                },
            },
        },
    },
    # -- Nya: kategorier & regler --
    {
        "type": "function",
        "function": {
            "name": "get_categories",
            "description": "Alla kategorier med månadsbudget (om satt).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_rules",
            "description": "Kategoriseringsregler — valfritt filtrerat på kategorinamn.",
            "parameters": {
                "type": "object",
                "properties": {"category": {"type": "string"}},
            },
        },
    },
    # -- Nya: trender & jämförelser --
    {
        "type": "function",
        "function": {
            "name": "get_budget_history",
            "description": "Budget + utfall över flera månader för trendanalys.",
            "parameters": {
                "type": "object",
                "properties": {
                    "from_month": {"type": "string", "description": "YYYY-MM"},
                    "to_month": {"type": "string", "description": "YYYY-MM"},
                },
                "required": ["from_month", "to_month"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_months",
            "description": (
                "Jämför två månader: total inkomst/utgift/sparande + per-kategori-diff, "
                "sorterat på absolutvärde."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "month_a": {"type": "string"},
                    "month_b": {"type": "string"},
                },
                "required": ["month_a", "month_b"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_anomalies",
            "description": (
                "Statistiska avvikelser denna månad jämfört mot historiskt snitt "
                "(z-score över 6 månaders lookback)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "month": {"type": "string"},
                    "threshold_sigma": {"type": "number", "default": 2.0},
                },
                "required": ["month"],
            },
        },
    },
    # -- Nya: familj --
    {
        "type": "function",
        "function": {
            "name": "subscription_health",
            "description": (
                "Hälsokoll för prenumerationer: hitta de som inte dragits "
                "senaste `stale_days` dagarna. Summerar stale årskostnad — "
                "bra för att föreslå uppsägningar."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "stale_days": {"type": "integer", "default": 60}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_family_breakdown",
            "description": (
                "Vem-betalade-vad per kontoägare (owner_id) och per konto under "
                "en månad. Inkomst och utgift separat."
            ),
            "parameters": {
                "type": "object",
                "properties": {"month": {"type": "string"}},
                "required": ["month"],
            },
        },
    },
]


# Dispatcher: namn → implementation. Hålls i sync med TOOLS ovan.
_DISPATCH = {
    "get_month_summary": tools.get_month_summary,
    "query_transactions": tools.query_transactions,
    "top_categories": tools.top_categories,
    "find_subscriptions": tools.find_subscriptions,
    "forecast_cashflow": tools.forecast_cashflow,
    "calculate_scenario": tools.calculate_scenario,
    "get_accounts": tools.get_accounts,
    "get_account_balance": tools.get_account_balance,
    "get_balance_history": tools.get_balance_history,
    "get_upcoming": tools.get_upcoming,
    "get_loans": tools.get_loans,
    "get_loan_schedule": tools.get_loan_schedule,
    "get_goals": tools.get_goals,
    "get_scenarios": tools.get_scenarios,
    "get_tax_events": tools.get_tax_events,
    "get_categories": tools.get_categories,
    "get_rules": tools.get_rules,
    "get_budget_history": tools.get_budget_history,
    "compare_months": tools.compare_months,
    "detect_anomalies": tools.detect_anomalies,
    "get_family_breakdown": tools.get_family_breakdown,
    "subscription_health": tools.subscription_health,
}


class ChatAgent:
    """Tool-using agent som läser ur DB och räknar deterministiskt via backend."""

    def __init__(
        self,
        session: Session,
        llm: LMStudioClient,
        max_tool_iters: int = 8,
    ):
        self.session = session
        self.llm = llm
        self.max_tool_iters = max_tool_iters

    def _dispatch(self, name: str, args: dict) -> dict:
        fn = _DISPATCH.get(name)
        if fn is None:
            return {"error": f"unknown_tool:{name}"}
        try:
            return fn(self.session, **args)
        except TypeError as exc:
            # Argumentnamn som inte finns i funktionen → hjälpsamt fel
            log.warning("tool %s got bad args %s: %s", name, args, exc)
            return {"error": f"bad_arguments:{exc}"}
        except Exception as exc:
            log.exception("tool %s failed", name)
            return {"error": str(exc)}

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
                entry["tool_calls"] = (
                    m.tool_calls.get("tool_calls")
                    if isinstance(m.tool_calls, dict)
                    else None
                )
            messages.append(entry)
        messages.append({"role": "user", "content": user_message})

        self.session.add(
            ChatMessage(session_id=session_id, role="user", content=user_message)
        )
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
                serialized_calls = [tc.model_dump() for tc in tool_calls]
                messages.append(
                    {
                        "role": "assistant",
                        "content": choice.content or "",
                        "tool_calls": serialized_calls,
                    }
                )
                # Spara assistant-steget med tool_calls i DB så frontend kan
                # rendera "anropade verktyg X"-chips i chat-historiken.
                self.session.add(
                    ChatMessage(
                        session_id=session_id,
                        role="assistant",
                        content=choice.content or "",
                        tool_calls={"tool_calls": serialized_calls},
                    )
                )
                for tc in tool_calls:
                    name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    result = self._dispatch(name, args)
                    result_json = json.dumps(
                        result, ensure_ascii=False, default=str
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result_json,
                        }
                    )
                    # Spara även tool-svaret med vilket verktyg som anropades.
                    self.session.add(
                        ChatMessage(
                            session_id=session_id,
                            role="tool",
                            content=result_json,
                            tool_calls={
                                "name": name,
                                "arguments": args,
                                "tool_call_id": tc.id,
                            },
                        )
                    )
                self.session.flush()
                continue
            final_text = choice.content or ""
            break

        self.session.add(
            ChatMessage(session_id=session_id, role="assistant", content=final_text)
        )
        self.session.flush()
        return final_text
