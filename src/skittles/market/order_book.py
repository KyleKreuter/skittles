"""A single-market limit order book with price-time priority.

Resting orders are kept in two lists sorted best-first:

* ``bids`` (BUY): highest price first, oldest (lowest ``sequence``) first on ties.
* ``asks`` (SELL): lowest price first, oldest first on ties.

The agent count and order volume in this experiment are small, so we keep the
lists fully sorted on insert for clarity rather than using heaps.
"""

from __future__ import annotations

from collections import defaultdict

from skittles.domain.colors import Color
from skittles.market.order import Order, Side


class OrderBook:
    def __init__(self, base: Color, quote: Color) -> None:
        self.base = base
        self.quote = quote
        self.bids: list[Order] = []  # best (highest price, oldest) first
        self.asks: list[Order] = []  # best (lowest price, oldest) first

    # --- best quotes -----------------------------------------------------

    def best_bid(self) -> Order | None:
        return self.bids[0] if self.bids else None

    def best_ask(self) -> Order | None:
        return self.asks[0] if self.asks else None

    # --- mutations -------------------------------------------------------

    def add(self, order: Order) -> None:
        """Insert a resting order, keeping the relevant side sorted best-first."""
        if order.side is Side.BUY:
            self.bids.append(order)
            self.bids.sort(key=lambda o: (-o.price, o.sequence))
        else:
            self.asks.append(order)
            self.asks.sort(key=lambda o: (o.price, o.sequence))

    def remove(self, order: Order) -> None:
        side = self.bids if order.side is Side.BUY else self.asks
        side.remove(order)

    # --- views -----------------------------------------------------------

    def resting_orders(self) -> list[Order]:
        return [*self.bids, *self.asks]

    def snapshot(self, depth: int = 5) -> dict:
        """Aggregate the top ``depth`` price levels per side (anonymous)."""
        return {
            "base": self.base.value,
            "quote": self.quote.value,
            "bids": _aggregate(self.bids, depth, reverse=True),
            "asks": _aggregate(self.asks, depth, reverse=False),
        }

    def is_empty(self) -> bool:
        return not self.bids and not self.asks


def _aggregate(orders: list[Order], depth: int, *, reverse: bool) -> list[dict]:
    """Sum remaining quantity per price level, return up to ``depth`` levels."""
    levels: dict[int, int] = defaultdict(int)
    for o in orders:
        levels[o.price] += o.remaining
    ordered = sorted(levels.items(), key=lambda kv: kv[0], reverse=reverse)
    return [{"price": price, "quantity": qty} for price, qty in ordered[:depth]]
