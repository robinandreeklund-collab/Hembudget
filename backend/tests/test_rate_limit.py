"""Tester för rate-limit + Turnstile-hjälparna."""
from __future__ import annotations

import time

import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers
from starlette.requests import Request

from hembudget.security.rate_limit import (
    Rule,
    check_rate_limit,
    reset_all_for_testing,
    verify_turnstile,
)


def _fake_request(ip: str = "1.2.3.4") -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/test",
        "headers": Headers({"cf-connecting-ip": ip}).raw,
        "client": (ip, 0),
    }
    return Request(scope)


def setup_function(_fn) -> None:
    reset_all_for_testing()


def test_rate_limit_allows_under_threshold() -> None:
    rule = Rule(limit=3, window_sec=60)
    req = _fake_request()
    for _ in range(3):
        check_rate_limit(req, "bucket-a", [rule])


def test_rate_limit_blocks_over_threshold() -> None:
    rule = Rule(limit=2, window_sec=60)
    req = _fake_request()
    check_rate_limit(req, "bucket-b", [rule])
    check_rate_limit(req, "bucket-b", [rule])
    with pytest.raises(HTTPException) as exc:
        check_rate_limit(req, "bucket-b", [rule])
    assert exc.value.status_code == 429


def test_rate_limit_is_per_ip() -> None:
    rule = Rule(limit=1, window_sec=60)
    req_a = _fake_request("10.0.0.1")
    req_b = _fake_request("10.0.0.2")
    check_rate_limit(req_a, "bucket-c", [rule])
    # Samma bucket men annan IP ska inte blockeras
    check_rate_limit(req_b, "bucket-c", [rule])


def test_turnstile_skipped_without_secret(monkeypatch) -> None:
    monkeypatch.delenv("TURNSTILE_SECRET", raising=False)
    req = _fake_request()
    # Ska inte kasta trots att ingen token finns
    verify_turnstile(req, required=True)


def test_turnstile_required_blocks_when_missing(monkeypatch) -> None:
    monkeypatch.setenv("TURNSTILE_SECRET", "dummysecret")
    req = _fake_request()
    with pytest.raises(HTTPException) as exc:
        verify_turnstile(req, required=True)
    assert exc.value.status_code == 403


def test_turnstile_optional_skips_when_missing(monkeypatch) -> None:
    monkeypatch.setenv("TURNSTILE_SECRET", "dummysecret")
    req = _fake_request()
    # required=False + ingen token → ska inte kasta
    verify_turnstile(req, required=False)
