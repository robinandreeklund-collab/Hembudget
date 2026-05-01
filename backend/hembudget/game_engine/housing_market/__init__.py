"""Housing Market · per-stad bostadsmarknad med listings + valuation.

Spec: dev/game-motor/06-boendemarknaden.md

Komponenter:
  B1 · market_data.py   — månadsdrift av snittpris per stad
  B2 · listings.py      — deterministisk pool av tillgängliga bostäder
  B3 · transaction.py   — köp-flöde (skapar Loan + uppdaterar boende)
  B5 · valuation.py     — värdera elevens nuvarande boende

Listings är inte persisterade i scope-DB — de genereras on-demand
baserat på (city, year_month) som seed. Det matchar verkligheten:
"varje månad är det andra bostäder ute".
"""
from .market_data import (
    PRICE_DRIFT_TRENDS,
    market_price_for,
)
from .listings import (
    HousingListing,
    listings_for_city,
)
from .transaction import (
    PurchaseResult,
    SellResult,
    buy_listing,
    sell_current_home,
)
from .valuation import (
    HomeValuation,
    valuate_current_home,
)

__all__ = [
    "PRICE_DRIFT_TRENDS",
    "market_price_for",
    "HousingListing",
    "listings_for_city",
    "PurchaseResult",
    "SellResult",
    "buy_listing",
    "sell_current_home",
    "HomeValuation",
    "valuate_current_home",
]
