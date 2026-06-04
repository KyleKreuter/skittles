"""The exchange: holds one order book per color pair and runs the matching.

Mechanics (continuous double auction, price-time priority):

* Orders must use the **canonical** market orientation: ``base`` is the
  lower-ranked color, ``quote`` the higher-ranked one (see
  :func:`skittles.domain.colors.canonical_pair`). To acquire ``base`` place a
  BUY (you pay ``quote``); to give ``base`` away for ``quote`` place a SELL.
  Every color-for-color swap is expressible this way, so non-canonical
  orientations are rejected to keep integer pricing exact.
* On submission the offered skittles are escrowed immediately: a SELL locks
  ``quantity`` base, a BUY locks ``quantity * price`` quote.
* A new order matches against resting orders on the opposite side that cross
  its limit, best price first then oldest first. **Trades execute at the
  resting (maker) order's price.** A taker buyer that escrowed at a higher
  limit is refunded the difference.
* The exchange is a clearing house that keeps a **fee** on every trade: a
  fraction (``fee_rate``) of what each side *receives*, floored to whole
  skittles, is moved into the house vault (``fees_collected``) and thus leaves
  the agents' circulating supply.

Conservation invariant: every skittle that leaves one inventory enters another,
escrow, or the fee vault, so the per-color total over *(all agents + the fee
vault)* is constant. Tests assert this directly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

from skittles.domain.colors import COLOR_ORDER, Color, color_rank
from skittles.domain.inventory import Inventory
from skittles.market.order import Order, OrderStatus, Side, Trade
from skittles.market.order_book import OrderBook

EventSink = Callable[[str, dict], None]


class OrderRejected(Exception):
    """Raised when an order cannot be accepted (validation or insufficient funds)."""


@dataclass
class Fill:
    """One execution from the taker's perspective (anonymous price/qty)."""

    price: int
    quantity: int
    base_fee: int = 0
    quote_fee: int = 0

    def to_dict(self) -> dict:
        return {
            "price": self.price,
            "quantity": self.quantity,
            "base_fee": self.base_fee,
            "quote_fee": self.quote_fee,
        }


@dataclass
class PlaceResult:
    """Outcome of a :meth:`Exchange.place_order` call, returned to the agent."""

    order_id: int
    status: OrderStatus
    side: Side
    base: Color
    quote: Color
    price: int
    requested_quantity: int
    filled_quantity: int
    fills: list[Fill] = field(default_factory=list)

    @property
    def resting_quantity(self) -> int:
        return self.requested_quantity - self.filled_quantity

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "status": self.status.value,
            "side": self.side.value,
            "base": self.base.value,
            "quote": self.quote.value,
            "limit_price": self.price,
            "requested_quantity": self.requested_quantity,
            "filled_quantity": self.filled_quantity,
            "resting_quantity": self.resting_quantity,
            "fills": [f.to_dict() for f in self.fills],
        }


class Exchange:
    def __init__(
        self,
        inventories: dict[str, Inventory],
        event_sink: EventSink | None = None,
        fee_rate: float = 0.0,
    ) -> None:
        if not 0.0 <= fee_rate < 1.0:
            raise ValueError(f"fee_rate must be in [0, 1), got {fee_rate}")
        self.inventories = inventories
        self.fee_rate = fee_rate
        self.fees_collected: dict[Color, int] = {c: 0 for c in COLOR_ORDER}
        self.books: dict[tuple[Color, Color], OrderBook] = {}
        self.orders: dict[int, Order] = {}
        self.trades: list[Trade] = []
        self._event_sink = event_sink
        self._next_order_id = 1
        self._next_seq = 1

    # --- public API ------------------------------------------------------

    def place_order(
        self,
        agent_id: str,
        side: Side,
        base: Color,
        quote: Color,
        quantity: int,
        price: int,
    ) -> PlaceResult:
        """Validate, escrow, match and (if anything remains) rest a new order."""
        self._validate(agent_id, base, quote, quantity, price)
        inv = self.inventories[agent_id]

        # Escrow the offered skittles before the order can interact with the book.
        if side is Side.SELL:
            self._require(inv.available[base] >= quantity,
                          f"insufficient {base.value}: need {quantity}, "
                          f"have {inv.available[base]} available")
            inv.reserve(base, quantity)
        else:  # BUY
            cost = quantity * price
            self._require(inv.available[quote] >= cost,
                          f"insufficient {quote.value}: need {cost}, "
                          f"have {inv.available[quote]} available")
            inv.reserve(quote, cost)

        order = Order(
            order_id=self._next_order_id,
            agent_id=agent_id,
            side=side,
            base=base,
            quote=quote,
            price=price,
            quantity=quantity,
            sequence=self._next_seq,
        )
        self._next_order_id += 1
        self._next_seq += 1
        self.orders[order.order_id] = order
        self._emit("order_placed", order.to_dict())

        fills = self._match(order)

        if order.remaining > 0:
            order.status = (
                OrderStatus.PARTIALLY_FILLED if order.filled else OrderStatus.OPEN
            )
            self._book(base, quote).add(order)
        else:
            order.status = OrderStatus.FILLED

        return PlaceResult(
            order_id=order.order_id,
            status=order.status,
            side=side,
            base=base,
            quote=quote,
            price=price,
            requested_quantity=quantity,
            filled_quantity=order.filled,
            fills=fills,
        )

    def cancel_order(self, agent_id: str, order_id: int) -> None:
        """Cancel a resting order and refund its remaining escrow."""
        order = self.orders.get(order_id)
        if order is None:
            raise OrderRejected(f"unknown order {order_id}")
        if order.agent_id != agent_id:
            raise OrderRejected(f"order {order_id} does not belong to {agent_id}")
        if not order.is_resting():
            raise OrderRejected(f"order {order_id} is {order.status.value}, cannot cancel")

        inv = self.inventories[agent_id]
        remaining = order.remaining
        if order.side is Side.SELL:
            inv.release(order.base, remaining)
        else:
            inv.release(order.quote, remaining * order.price)

        self._book(order.base, order.quote).remove(order)
        order.status = OrderStatus.CANCELLED
        self._emit("order_cancelled", order.to_dict())

    def cancel_all(self, agent_id: str) -> int:
        """Cancel every resting order of ``agent_id`` (used at end of run)."""
        resting = [
            o for o in self.orders.values()
            if o.agent_id == agent_id and o.is_resting()
        ]
        for order in resting:
            self.cancel_order(agent_id, order.order_id)
        return len(resting)

    def open_orders(self, agent_id: str) -> list[Order]:
        return [
            o for o in self.orders.values()
            if o.agent_id == agent_id and o.is_resting()
        ]

    def market_snapshot(self, base: Color, quote: Color, depth: int = 5) -> dict:
        return self._book(base, quote).snapshot(depth)

    def all_snapshots(self, depth: int = 5) -> list[dict]:
        """Snapshots of every non-empty market (keeps observations compact)."""
        return [
            book.snapshot(depth)
            for book in self.books.values()
            if not book.is_empty()
        ]

    # --- internals -------------------------------------------------------

    def _match(self, taker: Order) -> list[Fill]:
        """Match ``taker`` against the opposite book side; settle each fill."""
        book = self._book(taker.base, taker.quote)
        fills: list[Fill] = []

        while taker.remaining > 0:
            maker = book.best_bid() if taker.side is Side.SELL else book.best_ask()
            if maker is None:
                break
            if not _crosses(taker, maker):
                break

            exec_qty = min(taker.remaining, maker.remaining)
            exec_price = maker.price  # execute at the resting order's price

            if taker.side is Side.SELL:
                buyer, seller = maker, taker
            else:
                buyer, seller = taker, maker
            base_fee, quote_fee = self._settle(
                base=taker.base,
                quote=taker.quote,
                qty=exec_qty,
                exec_price=exec_price,
                buyer=buyer,
                seller=seller,
            )

            taker.filled += exec_qty
            maker.filled += exec_qty
            fills.append(Fill(price=exec_price, quantity=exec_qty,
                              base_fee=base_fee, quote_fee=quote_fee))

            trade = Trade(
                base=taker.base,
                quote=taker.quote,
                price=exec_price,
                quantity=exec_qty,
                maker_order_id=maker.order_id,
                taker_order_id=taker.order_id,
                maker_agent=maker.agent_id,
                taker_agent=taker.agent_id,
                taker_side=taker.side,
                base_fee=base_fee,
                quote_fee=quote_fee,
                sequence=self._next_seq,
            )
            self._next_seq += 1
            self.trades.append(trade)
            self._emit("trade", trade.to_dict())

            if maker.remaining == 0:
                maker.status = OrderStatus.FILLED
                book.remove(maker)
            else:
                maker.status = OrderStatus.PARTIALLY_FILLED

        return fills

    def _settle(
        self,
        *,
        base: Color,
        quote: Color,
        qty: int,
        exec_price: int,
        buyer: Order,
        seller: Order,
    ) -> tuple[int, int]:
        """Transfer skittles for one fill and skim the house fee.

        Escrow already covers what each side *pays*; the fee is taken from what
        each side *receives* (quote for the seller, base for the buyer) so no
        extra escrow is needed. Returns ``(base_fee, quote_fee)``.
        """
        seller_inv = self.inventories[seller.agent_id]
        buyer_inv = self.inventories[buyer.agent_id]
        quote_paid = qty * exec_price

        # Seller: hand over escrowed base, receive quote minus the fee.
        seller_inv.settle_out(base, qty)
        quote_fee = self._fee(quote_paid)
        if quote_paid - quote_fee > 0:
            seller_inv.add(quote, quote_paid - quote_fee)

        # Buyer: pay quote from escrow (locked at the buyer's own limit price),
        # receive base minus the fee. Refund the difference if the buyer was the
        # taker and crossed at a better (lower) maker price.
        buyer_inv.settle_out(quote, quote_paid)
        overpay = qty * (buyer.price - exec_price)
        if overpay > 0:
            buyer_inv.release(quote, overpay)
        base_fee = self._fee(qty)
        if qty - base_fee > 0:
            buyer_inv.add(base, qty - base_fee)

        self.fees_collected[quote] += quote_fee
        self.fees_collected[base] += base_fee
        return base_fee, quote_fee

    def _fee(self, volume: int) -> int:
        """House fee on a received ``volume``, floored to whole skittles."""
        if self.fee_rate <= 0.0:
            return 0
        return math.floor(volume * self.fee_rate + 1e-9)

    def _validate(
        self, agent_id: str, base: Color, quote: Color, quantity: int, price: int
    ) -> None:
        if agent_id not in self.inventories:
            raise OrderRejected(f"unknown agent {agent_id!r}")
        if base == quote:
            raise OrderRejected("base and quote must be different colors")
        if color_rank(base) >= color_rank(quote):
            raise OrderRejected(
                f"non-canonical market: use base={_lower(base, quote)}, "
                f"quote={_higher(base, quote)} (base must be the lower-ranked color)"
            )
        if not isinstance(quantity, int) or quantity <= 0:
            raise OrderRejected(f"quantity must be a positive integer, got {quantity!r}")
        if not isinstance(price, int) or price <= 0:
            raise OrderRejected(f"price must be a positive integer, got {price!r}")

    def _book(self, base: Color, quote: Color) -> OrderBook:
        key = (base, quote)
        book = self.books.get(key)
        if book is None:
            book = OrderBook(base, quote)
            self.books[key] = book
        return book

    @staticmethod
    def _require(condition: bool, message: str) -> None:
        if not condition:
            raise OrderRejected(message)

    def _emit(self, kind: str, payload: dict) -> None:
        if self._event_sink is not None:
            self._event_sink(kind, payload)


def _crosses(taker: Order, maker: Order) -> bool:
    """True if a taker order can trade against the resting maker order."""
    if taker.side is Side.SELL:  # selling base: need a bid >= our ask
        return maker.price >= taker.price
    return maker.price <= taker.price  # buying base: need an ask <= our bid


def _lower(a: Color, b: Color) -> Color:
    return a if color_rank(a) < color_rank(b) else b


def _higher(a: Color, b: Color) -> Color:
    return a if color_rank(a) > color_rank(b) else b
