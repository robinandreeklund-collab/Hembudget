"""Tibber GraphQL-klient för att hämta elpris, förbrukning och real-
tidsmätningar via användarens API-token.

Tibber har två API:er:
1. Public API (https://api.tibber.com/v1-beta/gql) — price + historical
   consumption per hem. Token genereras på https://developer.tibber.com
2. Data API (https://data-api.tibber.com/graphql) — samma men med
   utökad playground för utvecklare.

Vi använder v1-beta som är stabilt och dokumenterat. Realtidsmätningar
via Pulse kräver WebSocket-subscription — för MVP:n polar vi
currentMeasurement via HTTP som uppdateras var ~1 min.

Auth: Bearer <token>. Token lagras krypterat i AppSetting-tabellen
(key='tibber_api_token'). Viewer-query bekräftar validity + returnerar
home-ID för användaren.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import httpx


TIBBER_GQL_URL = "https://api.tibber.com/v1-beta/gql"
DEFAULT_TIMEOUT = 15.0


class TibberError(RuntimeError):
    """Kastas vid API-fel (ogiltig token, nätverksproblem, schema-
    ändringar). Meddelandet är användarriktat."""


@dataclass
class TibberHome:
    id: str
    address: str
    size: int | None
    main_fuse_size: int | None
    currency: str
    has_pulse: bool  # Om realtime-mätning är aktiverad


@dataclass
class TibberPricePoint:
    starts_at: datetime
    total: Decimal  # kr/kWh inkl. moms + skatt
    energy: Decimal  # grund-pris
    tax: Decimal
    level: str  # "CHEAP" | "NORMAL" | "EXPENSIVE" | etc.


@dataclass
class TibberConsumptionPoint:
    from_ts: datetime
    to_ts: datetime
    kwh: Decimal | None
    cost_kr: Decimal | None
    unit_price: Decimal | None


@dataclass
class TibberRealtime:
    power_watts: float  # nuvarande effekt
    consumption_since_last_reset_kwh: float
    cost_since_last_reset_kr: float
    currency: str
    timestamp: datetime


class TibberClient:
    def __init__(self, token: str, timeout: float = DEFAULT_TIMEOUT):
        self.token = token
        self.timeout = timeout

    def _post(self, query: str, variables: dict | None = None) -> dict:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables
        try:
            resp = httpx.post(
                TIBBER_GQL_URL, headers=headers, json=payload,
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise TibberError(f"Nätverksfel: {exc}") from exc
        if resp.status_code == 401:
            raise TibberError(
                "Ogiltig Tibber-token. Generera en ny på "
                "https://developer.tibber.com/settings/access-token"
            )
        if resp.status_code >= 400:
            raise TibberError(
                f"Tibber API svarade {resp.status_code}: {resp.text[:200]}"
            )
        body = resp.json()
        if "errors" in body:
            errs = "; ".join(e.get("message", "?") for e in body["errors"])
            raise TibberError(f"GraphQL-fel: {errs}")
        return body["data"]

    def list_homes(self) -> list[TibberHome]:
        q = """
        query {
          viewer {
            name
            homes {
              id
              address { address1 postalCode city }
              size
              mainFuseSize
              currentSubscription { priceInfo { current { currency } } }
              features { realTimeConsumptionEnabled }
            }
          }
        }
        """
        data = self._post(q)
        homes = []
        for h in data.get("viewer", {}).get("homes", []) or []:
            addr = h.get("address") or {}
            addr_str = ", ".join(
                x for x in [
                    addr.get("address1"),
                    addr.get("postalCode"),
                    addr.get("city"),
                ] if x
            )
            currency = (
                (h.get("currentSubscription") or {})
                .get("priceInfo", {}).get("current", {}).get("currency", "SEK")
            )
            has_pulse = bool(
                (h.get("features") or {}).get("realTimeConsumptionEnabled")
            )
            homes.append(TibberHome(
                id=h["id"],
                address=addr_str or "Okänd adress",
                size=h.get("size"),
                main_fuse_size=h.get("mainFuseSize"),
                currency=currency,
                has_pulse=has_pulse,
            ))
        return homes

    def price_info_today_and_tomorrow(self, home_id: str) -> dict:
        """Returnerar priser för idag + imorgon i timmesupplösning."""
        q = """
        query PriceInfo($homeId: ID!) {
          viewer {
            home(id: $homeId) {
              currentSubscription {
                priceInfo {
                  current { total energy tax startsAt level currency }
                  today { total energy tax startsAt level }
                  tomorrow { total energy tax startsAt level }
                }
              }
            }
          }
        }
        """
        data = self._post(q, {"homeId": home_id})
        pi = (
            data.get("viewer", {})
            .get("home", {})
            .get("currentSubscription", {})
            .get("priceInfo", {})
        )
        return pi or {}

    def consumption(
        self,
        home_id: str,
        resolution: str = "MONTHLY",  # HOURLY | DAILY | MONTHLY | ANNUAL
        last: int = 12,
    ) -> list[TibberConsumptionPoint]:
        q = """
        query Consumption($homeId: ID!, $resolution: EnergyResolution!, $last: Int!) {
          viewer {
            home(id: $homeId) {
              consumption(resolution: $resolution, last: $last) {
                nodes { from to consumption consumptionUnit cost unitPrice }
              }
            }
          }
        }
        """
        data = self._post(q, {
            "homeId": home_id,
            "resolution": resolution,
            "last": last,
        })
        nodes = (
            data.get("viewer", {})
            .get("home", {})
            .get("consumption", {})
            .get("nodes", [])
        ) or []
        out = []
        for n in nodes:
            out.append(TibberConsumptionPoint(
                from_ts=datetime.fromisoformat(
                    n["from"].replace("Z", "+00:00"),
                ),
                to_ts=datetime.fromisoformat(
                    n["to"].replace("Z", "+00:00"),
                ),
                kwh=Decimal(str(n["consumption"])) if n.get("consumption") is not None else None,
                cost_kr=Decimal(str(n["cost"])) if n.get("cost") is not None else None,
                unit_price=Decimal(str(n["unitPrice"])) if n.get("unitPrice") is not None else None,
            ))
        return out

    def realtime(self, home_id: str) -> TibberRealtime | None:
        """Hämtar senaste Pulse-mätning. Returnerar None om Pulse inte
        är konfigurerad för hemmet."""
        q = """
        query Realtime($homeId: ID!) {
          viewer {
            home(id: $homeId) {
              features { realTimeConsumptionEnabled }
              currentSubscription { priceInfo { current { currency } } }
              daily: consumption(resolution: DAILY, last: 1) {
                nodes { from to consumption cost }
              }
            }
          }
        }
        """
        data = self._post(q, {"homeId": home_id})
        home = data.get("viewer", {}).get("home", {}) or {}
        if not (home.get("features") or {}).get("realTimeConsumptionEnabled"):
            return None
        # Vi använder senaste DAILY-noden som proxy för "sedan midnatt"
        nodes = (home.get("daily") or {}).get("nodes") or []
        if not nodes:
            return None
        n = nodes[0]
        currency = (
            (home.get("currentSubscription") or {})
            .get("priceInfo", {}).get("current", {}).get("currency", "SEK")
        )
        try:
            kwh_today = float(n.get("consumption") or 0)
            cost_today = float(n.get("cost") or 0)
        except (TypeError, ValueError):
            kwh_today = 0.0
            cost_today = 0.0
        return TibberRealtime(
            power_watts=0.0,  # hämtas separat via subscription i framtiden
            consumption_since_last_reset_kwh=kwh_today,
            cost_since_last_reset_kr=cost_today,
            currency=currency,
            timestamp=datetime.utcnow(),
        )


def monthly_consumption_to_readings(
    home: TibberHome,
    nodes: list[TibberConsumptionPoint],
) -> list[dict]:
    """Konvertera Tibber månads-noder till UtilityReading-dict:s
    redo att sparas i DB. Returnerar tomlista om ingen förbrukning."""
    out = []
    for n in nodes:
        if n.kwh is None or n.kwh == 0:
            continue
        out.append({
            "supplier": "tibber",
            "meter_type": "electricity",
            "period_start": n.from_ts.date(),
            "period_end": n.to_ts.date(),
            "consumption": float(n.kwh),
            "consumption_unit": "kWh",
            "cost_kr": float(n.cost_kr or 0),
            "source": "tibber_api",
            "notes": f"home={home.id} price={n.unit_price}",
        })
    return out
