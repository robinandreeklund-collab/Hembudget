from __future__ import annotations

import json
import logging
from typing import Any, Iterable

from openai import APIConnectionError, APITimeoutError, OpenAI

from ..config import settings

log = logging.getLogger(__name__)


class LLMUnavailable(RuntimeError):
    pass


class LMStudioClient:
    """Thin wrapper over the OpenAI SDK pointed at LM Studio."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None,
                 model: str | None = None, timeout: float | None = None):
        self.base_url = base_url or settings.lm_studio_base_url
        self.model = model or settings.lm_studio_model
        self.timeout = timeout or settings.llm_timeout_seconds
        self._client = OpenAI(
            base_url=self.base_url,
            api_key=api_key or settings.lm_studio_api_key,
            timeout=self.timeout,
        )

    def is_alive(self) -> bool:
        try:
            self._client.models.list()
            return True
        except Exception as exc:
            log.debug("LM Studio not reachable: %s", exc)
            return False

    def complete(self, messages: list[dict[str, Any]], **kwargs) -> str:
        try:
            resp = self._client.chat.completions.create(
                model=self.model, messages=messages, **kwargs
            )
        except (APIConnectionError, APITimeoutError) as exc:
            raise LLMUnavailable(str(exc)) from exc
        return resp.choices[0].message.content or ""

    def complete_json(self, messages: list[dict[str, Any]], schema: dict | None = None, **kwargs) -> Any:
        extra: dict[str, Any] = {}
        if schema is not None:
            extra["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "response", "schema": schema, "strict": True},
            }
        else:
            extra["response_format"] = {"type": "json_object"}
        raw = self.complete(messages, **{**kwargs, **extra})
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Fallback: try to locate first JSON object
            start = raw.find("{")
            end = raw.rfind("}")
            if start >= 0 and end > start:
                return json.loads(raw[start : end + 1])
            raise

    def tool_call(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        **kwargs,
    ):
        try:
            return self._client.chat.completions.create(
                model=self.model, messages=messages, tools=tools, tool_choice="auto", **kwargs
            )
        except (APIConnectionError, APITimeoutError) as exc:
            raise LLMUnavailable(str(exc)) from exc

    def batch_complete_json(
        self, system: str, user_batches: Iterable[str], schema: dict | None = None
    ) -> list[Any]:
        results = []
        for user in user_batches:
            results.append(
                self.complete_json(
                    [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    schema=schema,
                    temperature=0.0,
                )
            )
        return results
