"""Tester för cache-adaptern (Redis + in-memory-fallback).

Verifierar:
- In-memory: get/set/delete/expiry/clear_pattern
- Singleton-beteende
- Fallback när HEMBUDGET_REDIS_URL saknas
"""
from __future__ import annotations

import os
import time

import pytest


@pytest.fixture(autouse=True)
def _reset_cache_singleton():
    """Töm singleton mellan tester så env-var-changes plockas upp."""
    from hembudget.cache import reset_cache_for_testing
    reset_cache_for_testing()
    yield
    reset_cache_for_testing()


def test_inmemory_set_get():
    from hembudget.cache import InMemoryCache
    c = InMemoryCache()
    c.set("foo", b"bar", ttl=10)
    assert c.get("foo") == b"bar"


def test_inmemory_miss_returns_none():
    from hembudget.cache import InMemoryCache
    c = InMemoryCache()
    assert c.get("nope") is None


def test_inmemory_ttl_expiry():
    from hembudget.cache import InMemoryCache
    c = InMemoryCache()
    c.set("k", b"v", ttl=0)  # TTL=0 → utgår omedelbart
    time.sleep(0.05)
    assert c.get("k") is None


def test_inmemory_delete():
    from hembudget.cache import InMemoryCache
    c = InMemoryCache()
    c.set("k", b"v", ttl=10)
    c.delete("k")
    assert c.get("k") is None


def test_inmemory_clear_pattern_glob():
    from hembudget.cache import InMemoryCache
    c = InMemoryCache()
    c.set("hub:s_1:v1", b"a", ttl=60)
    c.set("hub:s_2:v1", b"b", ttl=60)
    c.set("other:k", b"c", ttl=60)
    n = c.clear_pattern("hub:*")
    assert n == 2
    assert c.get("hub:s_1:v1") is None
    assert c.get("hub:s_2:v1") is None
    assert c.get("other:k") == b"c"


def test_inmemory_clear_pattern_exact():
    from hembudget.cache import InMemoryCache
    c = InMemoryCache()
    c.set("hub:s_1:v1", b"a", ttl=60)
    n = c.clear_pattern("hub:s_1:v1")
    assert n == 1
    assert c.get("hub:s_1:v1") is None


def test_get_cache_returns_inmemory_when_no_redis_url(monkeypatch):
    monkeypatch.delenv("HEMBUDGET_REDIS_URL", raising=False)
    from hembudget.cache import get_cache, InMemoryCache
    c = get_cache()
    assert isinstance(c, InMemoryCache)


def test_get_cache_singleton(monkeypatch):
    monkeypatch.delenv("HEMBUDGET_REDIS_URL", raising=False)
    from hembudget.cache import get_cache
    c1 = get_cache()
    c2 = get_cache()
    assert c1 is c2  # singleton


def test_get_cache_falls_back_when_redis_unreachable(monkeypatch):
    """Om HEMBUDGET_REDIS_URL pekar på en obefintlig host SKA appen
    falla tillbaka till in-memory utan att krascha."""
    monkeypatch.setenv(
        "HEMBUDGET_REDIS_URL",
        "redis://localhost:1/0",  # port 1 är reserverad/oanvänd
    )
    from hembudget.cache import get_cache, InMemoryCache
    c = get_cache()
    # Förväntat: RedisCache-init failar i ping → fallback in-memory
    assert isinstance(c, InMemoryCache)


def test_invalidate_hub_cache_busts_entry():
    """invalidate_hub_cache ska radera entry så nästa get returnerar None."""
    from hembudget.api.v2 import invalidate_hub_cache
    from hembudget.cache import get_cache
    c = get_cache()
    c.set("hub:s_42:v1", b"cached", ttl=60)
    assert c.get("hub:s_42:v1") == b"cached"
    invalidate_hub_cache(42)
    assert c.get("hub:s_42:v1") is None


def test_invalidate_hub_cache_none_is_noop():
    from hembudget.api.v2 import invalidate_hub_cache
    # Inget exception · accept None tyst
    invalidate_hub_cache(None)
