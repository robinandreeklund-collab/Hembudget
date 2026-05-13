"""Cache-adapter · Redis i prod, in-memory fallback för dev/test.

Backend för 30s-aggregat-cache av /v2/hub och liknande heavy endpoints.
Utan cache: varje hub-request → 5-10 master_session-anrop + pentagon-
beräkning + wellbeing-snapshot. Med 30s-cache räcker en tung beräkning
per elev per 30:e sek — resten är O(serialize/deserialize).

Designval:
- Klar fallback till in-memory om HEMBUDGET_REDIS_URL saknas eller
  Redis är otillgängligt. App-funktionalitet ska aldrig blockas av
  cache-utfall · cache är prestanda-optimering, inte kritisk path.
- Bytes som value-type · serialize:as i caller (typiskt JSON eller
  pickle). Cache:en är agnostisk om format.
- Pattern-baserad invalidering via clear_pattern() så vi kan slänga
  alla hub-cachar för en elev: clear_pattern(f"hub:s{student_id}:*").
- TTL-baserad expiry · ingen explicit purge-thread. Redis hanterar
  det själv · in-memory: lazy-cleanup vid get/set.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Optional


log = logging.getLogger(__name__)


class Cache:
    """Abstrakt cache-interface."""

    def get(self, key: str) -> Optional[bytes]:
        raise NotImplementedError

    def set(self, key: str, value: bytes, ttl: int) -> None:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError

    def clear_pattern(self, pattern: str) -> int:
        """Radera alla nycklar som matchar pattern (* som glob)."""
        raise NotImplementedError


class InMemoryCache(Cache):
    """Process-lokal cache · per Cloud Run-instans, EJ delad mellan
    instanser. Räcker för dev + 1-instans-deploys. För prod-multi-
    instans → använd Redis (varje instans har egen kopia annars).

    Trådsäker via lock. Lazy-cleanup: slänger expired entries vid
    get(). Bra nog för ~10K nycklar.
    """

    def __init__(self) -> None:
        self._data: dict[str, tuple[bytes, float]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[bytes]:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if time.time() >= expires_at:
                del self._data[key]
                return None
            return value

    def set(self, key: str, value: bytes, ttl: int) -> None:
        with self._lock:
            self._data[key] = (value, time.time() + ttl)

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def clear_pattern(self, pattern: str) -> int:
        # Enkel glob: "*" matchar allt suffixet, prefix måste matcha
        with self._lock:
            if "*" not in pattern:
                if pattern in self._data:
                    del self._data[pattern]
                    return 1
                return 0
            prefix = pattern.split("*", 1)[0]
            keys = [k for k in self._data if k.startswith(prefix)]
            for k in keys:
                del self._data[k]
            return len(keys)


class RedisCache(Cache):
    """Redis-klient via redis-py. Tål connection-fel · loggar och
    returnerar None vid felet (caller faller tillbaka till källan).
    """

    def __init__(self, url: str) -> None:
        import redis  # lazy import så in-memory-only-deploys funkar utan dep
        self._client = redis.from_url(
            url,
            socket_timeout=2.0,           # fail-fast vid Redis-down
            socket_connect_timeout=2.0,
            decode_responses=False,        # bytes-mode
            health_check_interval=30,
            retry_on_timeout=True,
        )

    def get(self, key: str) -> Optional[bytes]:
        try:
            return self._client.get(key)
        except Exception:
            log.warning("RedisCache.get failed för %s · fallback None", key)
            return None

    def set(self, key: str, value: bytes, ttl: int) -> None:
        try:
            self._client.set(key, value, ex=ttl)
        except Exception:
            log.warning("RedisCache.set failed för %s · skippar", key)

    def delete(self, key: str) -> None:
        try:
            self._client.delete(key)
        except Exception:
            log.warning("RedisCache.delete failed för %s · skippar", key)

    def clear_pattern(self, pattern: str) -> int:
        # SCAN + DEL · undviker att blocka Redis med KEYS på stor DB
        try:
            count = 0
            for k in self._client.scan_iter(match=pattern, count=200):
                self._client.delete(k)
                count += 1
            return count
        except Exception:
            log.warning(
                "RedisCache.clear_pattern failed för %s · skippar", pattern,
            )
            return 0


_cache_singleton: Optional[Cache] = None
_cache_lock = threading.Lock()


def get_cache() -> Cache:
    """Returnera singleton-cache. Initierar Redis om HEMBUDGET_REDIS_URL
    finns, annars in-memory."""
    global _cache_singleton
    if _cache_singleton is not None:
        return _cache_singleton
    with _cache_lock:
        if _cache_singleton is not None:
            return _cache_singleton
        url = os.environ.get("HEMBUDGET_REDIS_URL", "").strip()
        if url:
            try:
                _cache_singleton = RedisCache(url)
                # Test-pinga · misslyckas direkt om URL fel/Redis nere
                _cache_singleton.set("hb:cache:_init", b"ok", ttl=5)
                log.info("cache: Redis aktiv via %s",
                         url.split("@")[-1])  # dölj password
            except Exception:
                log.exception(
                    "cache: Redis-init failed · faller tillbaka till "
                    "in-memory (multi-instans-deploy får DELAD cache "
                    "per instans → mindre effektiv men funktionellt OK)",
                )
                _cache_singleton = InMemoryCache()
        else:
            log.info(
                "cache: HEMBUDGET_REDIS_URL ej satt · använder "
                "in-memory (per Cloud Run-instans · för dev/små deploys)",
            )
            _cache_singleton = InMemoryCache()
    return _cache_singleton


def reset_cache_for_testing() -> None:
    """Töm singleton · för pytest-fixtures som vill rena state."""
    global _cache_singleton
    with _cache_lock:
        _cache_singleton = None
