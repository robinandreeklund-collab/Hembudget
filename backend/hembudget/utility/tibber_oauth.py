"""Tibber OAuth 2.0-klient för Data API (data-api.tibber.com/v1/gql).

Tibbers nya Data API kräver OAuth 2.0 authorization code flow, till
skillnad från gamla v1-beta som tog en statisk bearer-token. Fördelen:
användaren kan nå data även utan eget elavtal — en registrerad
developer-klient får access till homes + energy systems via scopes
som 'data-api-homes-read', 'data-api-energy-systems-read'.

Flödet (från användarens perspektiv):
1. Frontend anropar GET /utility/tibber/oauth/start → får tillbaka
   en authorization-URL.
2. Browser öppnar URL:en → Tibber login + consent.
3. Tibber redirectar till /Callback?code=...&state=... (vi använder
   http://localhost:1420/Callback som Tauri/dev-frontend är på).
4. Frontend skickar code + state till POST /utility/tibber/oauth/callback
   → backend byter code mot access_token + refresh_token, lagrar
   krypterat i AppSetting, returnerar profil-info.
5. Följande API-anrop använder TibberOAuthClient.authorized_session()
   som auto-refresh:ar tokens när de går ut.

Tokens lagras i AppSetting med key='tibber_oauth' som JSON:
    {
      "access_token": "...",
      "refresh_token": "...",
      "expires_at": "2026-05-01T12:00:00",
      "scope": "data-api-homes-read ...",
      "client_id": "..."
    }

client_id + client_secret lagras separat i 'tibber_oauth_config' så
de kan bytas utan att slå ut en aktiv session.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx


# Tibbers OAuth endpoints. Dessa är dokumenterade på
# https://developer.tibber.com/docs/guides/calling-api
TIBBER_AUTHORIZE_URL = "https://thewall.tibber.com/connect/authorize"
TIBBER_TOKEN_URL = "https://thewall.tibber.com/connect/token"
# Nya Data API:et — GraphQL-endpoint för homes/energy-data med OAuth
TIBBER_DATA_API_URL = "https://app.tibber.com/v4/gql"

# Minsta scope-set vi behöver för utility-sidan. Extra scopes skadar
# inte och kan krävas av Tibber för viss data.
DEFAULT_SCOPES = [
    "openid",
    "profile",
    "offline_access",  # Måste ingå för att få refresh_token
    "data-api-user-read",
    "data-api-homes-read",
    "data-api-energy-systems-read",
]

DEFAULT_TIMEOUT = 20.0


class TibberOAuthError(RuntimeError):
    """Höjs vid OAuth-flödesfel (ogiltig code, expired refresh, etc).
    Meddelandet är användarriktat och säkert att visa i UI."""


@dataclass
class TibberTokenSet:
    """Allt backend lagrar efter ett lyckat token-utbyte. `expires_at`
    är UTC-timestamp när access_token går ut."""
    access_token: str
    refresh_token: str | None
    expires_at: datetime
    scope: str
    client_id: str

    def to_dict(self) -> dict:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at.isoformat(),
            "scope": self.scope,
            "client_id": self.client_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TibberTokenSet":
        exp = d.get("expires_at")
        if isinstance(exp, str):
            exp_dt = datetime.fromisoformat(exp)
        else:
            exp_dt = datetime.now(timezone.utc)
        return cls(
            access_token=d["access_token"],
            refresh_token=d.get("refresh_token"),
            expires_at=exp_dt,
            scope=d.get("scope", ""),
            client_id=d.get("client_id", ""),
        )

    def is_expired(self, skew_seconds: int = 60) -> bool:
        """Sant om access_token går ut inom `skew_seconds`."""
        now = datetime.now(timezone.utc)
        # Hantera naiva datetime som lagrade utan tz (äldre data)
        exp = self.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return exp - now < timedelta(seconds=skew_seconds)


def build_authorization_url(
    client_id: str,
    redirect_uri: str,
    scopes: list[str] | None = None,
    state: str | None = None,
) -> tuple[str, str]:
    """Returnerar (authorize_url, state). State måste sparas i klienten
    och verifieras i callback — skyddar mot CSRF.

    `redirect_uri` måste matcha EXAKT det som är registrerat på Tibber-
    developer-sidan (se skärmdump: http://localhost:1420/Callback)."""
    scopes = scopes or DEFAULT_SCOPES
    state = state or secrets.token_urlsafe(24)
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "state": state,
    }
    return f"{TIBBER_AUTHORIZE_URL}?{urlencode(params)}", state


def exchange_code_for_token(
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    timeout: float = DEFAULT_TIMEOUT,
) -> TibberTokenSet:
    """Byt authorization-code mot access_token + refresh_token."""
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    return _post_token_request(data, timeout=timeout, client_id=client_id)


def refresh_access_token(
    client_id: str,
    client_secret: str,
    refresh_token: str,
    timeout: float = DEFAULT_TIMEOUT,
) -> TibberTokenSet:
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    return _post_token_request(data, timeout=timeout, client_id=client_id)


def _post_token_request(
    data: dict, timeout: float, client_id: str,
) -> TibberTokenSet:
    try:
        resp = httpx.post(
            TIBBER_TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        raise TibberOAuthError(f"Nätverksfel mot Tibber: {exc}") from exc
    if resp.status_code == 400:
        try:
            body = resp.json()
        except Exception:
            body = {}
        err = body.get("error", "invalid_request")
        desc = body.get("error_description", "")
        raise TibberOAuthError(
            f"Tibber avvisade token-förfrågan ({err}). {desc}"
        )
    if resp.status_code >= 400:
        raise TibberOAuthError(
            f"Tibber svarade {resp.status_code}: {resp.text[:200]}"
        )
    body = resp.json()
    expires_in = int(body.get("expires_in", 3600))
    return TibberTokenSet(
        access_token=body["access_token"],
        refresh_token=body.get("refresh_token"),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
        scope=body.get("scope", ""),
        client_id=client_id,
    )


class TibberOAuthClient:
    """GraphQL-klient mot Tibber Data API med OAuth-tokens.

    Konstruktorn tar en TibberTokenSet. Om access_token behöver refresh
    under en request görs det transparent — använd `tokens_after` för
    att spara tillbaka uppdaterade tokens i DB.
    """

    def __init__(
        self,
        tokens: TibberTokenSet,
        client_secret: str,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.tokens = tokens
        self.client_secret = client_secret
        self.timeout = timeout
        self._tokens_updated = False

    @property
    def tokens_after(self) -> TibberTokenSet | None:
        """Returnerar nya tokens om refresh inträffade under klientens
        livstid, annars None. Backend ska spara dessa i DB."""
        return self.tokens if self._tokens_updated else None

    def _ensure_fresh(self) -> None:
        if not self.tokens.is_expired():
            return
        if not self.tokens.refresh_token:
            raise TibberOAuthError(
                "Access-token har gått ut och refresh_token saknas — "
                "användaren måste auktorisera på nytt."
            )
        self.tokens = refresh_access_token(
            self.tokens.client_id,
            self.client_secret,
            self.tokens.refresh_token,
            timeout=self.timeout,
        )
        self._tokens_updated = True

    def _post(self, query: str, variables: dict | None = None) -> dict:
        self._ensure_fresh()
        headers = {
            "Authorization": f"Bearer {self.tokens.access_token}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables
        try:
            resp = httpx.post(
                TIBBER_DATA_API_URL,
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise TibberOAuthError(f"Nätverksfel: {exc}") from exc
        if resp.status_code == 401:
            raise TibberOAuthError(
                "Tibber nekar access (401). Token kan ha återkallats — "
                "auktorisera på nytt."
            )
        if resp.status_code >= 400:
            raise TibberOAuthError(
                f"Tibber API svarade {resp.status_code}: {resp.text[:200]}"
            )
        body = resp.json()
        if "errors" in body and body["errors"]:
            errs = "; ".join(
                e.get("message", "?") for e in body["errors"]
            )
            raise TibberOAuthError(f"GraphQL-fel: {errs}")
        return body.get("data") or {}

    # ----- Queries -----

    def viewer_profile(self) -> dict:
        """Användarens namn + kontaktinfo. Användbart för att bekräfta
        att OAuth-flödet lyckades efter auktoriseringen."""
        q = """
        query { viewer { name login userId } }
        """
        data = self._post(q)
        return data.get("viewer") or {}

    def list_homes(self) -> list[dict]:
        """Alla hem användaren har tillgång till i Data API:et.
        Returnerar råa dicts så kallande kod kan plocka det den behöver
        utan att schemat måste flyga genom en dataklass-migration."""
        q = """
        query {
          viewer {
            homes {
              id
              address { address1 postalCode city country }
              size
              mainFuseSize
              features { realTimeConsumptionEnabled }
              meteringPointData { consumptionEan }
            }
          }
        }
        """
        data = self._post(q)
        viewer = data.get("viewer") or {}
        return viewer.get("homes") or []

    def home_consumption(
        self,
        home_id: str,
        resolution: str = "HOURLY",
        last: int = 24,
    ) -> list[dict]:
        """Historisk förbrukning per hem. resolution: HOURLY | DAILY |
        WEEKLY | MONTHLY | ANNUAL."""
        q = """
        query Consumption($homeId: ID!, $res: EnergyResolution!, $last: Int!) {
          viewer {
            home(id: $homeId) {
              consumption(resolution: $res, last: $last) {
                nodes { from to cost unitPrice consumption consumptionUnit }
              }
            }
          }
        }
        """
        data = self._post(q, {
            "homeId": home_id, "res": resolution, "last": last,
        })
        viewer = data.get("viewer") or {}
        home = viewer.get("home") or {}
        cons = home.get("consumption") or {}
        return cons.get("nodes") or []

    def current_measurement(self, home_id: str) -> dict | None:
        """Pulse realtime snapshot. Returnerar None om Pulse saknas."""
        q = """
        query Current($homeId: ID!) {
          viewer {
            home(id: $homeId) {
              features { realTimeConsumptionEnabled }
              currentSubscription {
                priceInfo { current { total energy tax startsAt level currency } }
              }
              daily: consumption(resolution: DAILY, last: 1) {
                nodes { from to consumption cost }
              }
            }
          }
        }
        """
        data = self._post(q, {"homeId": home_id})
        viewer = data.get("viewer") or {}
        home = viewer.get("home") or {}
        features = home.get("features") or {}
        if not features.get("realTimeConsumptionEnabled"):
            return None
        daily = home.get("daily") or {}
        nodes = daily.get("nodes") or []
        sub = home.get("currentSubscription") or {}
        price_info = sub.get("priceInfo") or {}
        current_p = price_info.get("current") or {}
        return {
            "price_current": current_p,
            "daily_latest": nodes[0] if nodes else None,
        }
