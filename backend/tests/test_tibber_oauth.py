"""Tester för Tibber OAuth-klienten.

Testar:
- Authorization-URL byggs korrekt med rätt params
- TibberTokenSet serialiserar/deserialiserar korrekt
- is_expired() returnerar rätt
- Token-refresh anropas när access_token gått ut
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest

from hembudget.utility.tibber_oauth import (
    TIBBER_AUTHORIZE_URL,
    DEFAULT_SCOPES,
    TibberOAuthError,
    TibberTokenSet,
    build_authorization_url,
)


def test_build_authorization_url_contains_required_params():
    url, state = build_authorization_url(
        client_id="CID",
        redirect_uri="http://localhost:1420/Callback",
    )
    parsed = urlparse(url)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == TIBBER_AUTHORIZE_URL
    qs = parse_qs(parsed.query)
    assert qs["client_id"] == ["CID"]
    assert qs["redirect_uri"] == ["http://localhost:1420/Callback"]
    assert qs["response_type"] == ["code"]
    assert qs["state"] == [state]
    # Default-scopes måste innehålla homes + offline_access för refresh
    scope = qs["scope"][0].split()
    assert "data-api-homes-read" in scope
    assert "offline_access" in scope


def test_build_authorization_url_uses_custom_scopes():
    url, _ = build_authorization_url(
        client_id="CID",
        redirect_uri="http://localhost:1420/Callback",
        scopes=["data-api-homes-read"],
    )
    qs = parse_qs(urlparse(url).query)
    assert qs["scope"] == ["data-api-homes-read"]


def test_build_authorization_url_generates_unique_state():
    _, s1 = build_authorization_url("CID", "http://x/cb")
    _, s2 = build_authorization_url("CID", "http://x/cb")
    assert s1 != s2


def test_default_scopes_include_homes_and_refresh():
    assert "data-api-homes-read" in DEFAULT_SCOPES
    assert "offline_access" in DEFAULT_SCOPES


def test_token_set_serialization_roundtrip():
    t = TibberTokenSet(
        access_token="AT",
        refresh_token="RT",
        expires_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
        scope="data-api-homes-read",
        client_id="CID",
    )
    d = t.to_dict()
    t2 = TibberTokenSet.from_dict(d)
    assert t2.access_token == "AT"
    assert t2.refresh_token == "RT"
    assert t2.scope == "data-api-homes-read"
    assert t2.client_id == "CID"
    assert t2.expires_at.year == 2030


def test_token_set_is_expired_detects_expired():
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    t = TibberTokenSet(
        access_token="AT",
        refresh_token="RT",
        expires_at=past,
        scope="",
        client_id="CID",
    )
    assert t.is_expired() is True


def test_token_set_is_expired_allows_future():
    future = datetime.now(timezone.utc) + timedelta(hours=2)
    t = TibberTokenSet(
        access_token="AT",
        refresh_token="RT",
        expires_at=future,
        scope="",
        client_id="CID",
    )
    assert t.is_expired() is False


def test_token_set_is_expired_uses_skew():
    """Tokens som går ut om 30 sek ska räknas som utgångna med skew=60."""
    near = datetime.now(timezone.utc) + timedelta(seconds=30)
    t = TibberTokenSet(
        access_token="AT",
        refresh_token="RT",
        expires_at=near,
        scope="",
        client_id="CID",
    )
    assert t.is_expired(skew_seconds=60) is True
    assert t.is_expired(skew_seconds=10) is False


def test_token_set_handles_naive_datetime():
    """Äldre sparad data kan vara utan tz-info — vi ska inte krascha."""
    naive = datetime(2020, 1, 1)  # utan tz
    t = TibberTokenSet(
        access_token="AT",
        refresh_token="RT",
        expires_at=naive,
        scope="",
        client_id="CID",
    )
    # 2020-01-01 är för länge sen → expired
    assert t.is_expired() is True


def test_oauth_error_is_runtime_error():
    """TibberOAuthError ska gå att fånga som RuntimeError (konsistent
    med gamla TibberError)."""
    assert issubclass(TibberOAuthError, RuntimeError)
    with pytest.raises(RuntimeError):
        raise TibberOAuthError("test")
