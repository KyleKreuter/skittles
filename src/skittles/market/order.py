"""Order and trade value types.

Prices are integers: ``price`` quote-skittles buy 1 base-skittle. Quantities
are integers (base-skittles). Keeping both integral guarantees settlement never
produces fractional skittles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from skittles.domain.colors import Color


class Side(str, Enum):
    """Order side, always expressed relative to the market's ``base`` color."""

    BUY = "BUY"   # acquire base, pay quote
    SELL = "SELL"  # give base, receive quote


class OrderStatus(str, Enum):
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"


@dataclass
class Order:
    """A limit order resting in, or passing through, a single market book."""

    order_id: int
    agent_id: str
    side: Side
    base: Color
    quote: Color
    price: int           # quote per 1 base
    quantity: int        # original base quantity
    sequence: int        # global monotonic counter -> time priority
    filled: int = 0
    status: OrderStatus = OrderStatus.OPEN

    @property
    def remaining(self) -> int:
        return self.quantity - self.filled

    def is_resting(self) -> bool:
        return self.status in (OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED)

    def to_dict(self, *, include_agent: bool = True) -> dict:
        data = {
            "order_id": self.order_id,
            "side": self.side.value,
            "base": self.base.value,
            "quote": self.quote.value,
            "price": self.price,
            "quantity": self.quantity,
            "filled": self.filled,
            "remaining": self.remaining,
            "status": self.status.value,
        }
        if include_agent:
            data["agent_id"] = self.agent_id
        return data


@dataclass
class Trade:
    """A single executed match between a maker and a taker order."""

    base: Color
    quote: Color
    price: int            # execution price = resting (maker) order price
    quantity: int         # base traded
    maker_order_id: int
    taker_order_id: int
    maker_agent: str
    taker_agent: str
    taker_side: Side
    base_fee: int = 0
    quote_fee: int = 0
    sequence: int = field(default=0)

    def to_dict(self) -> dict:
        return {
            "base": self.base.value,
            "quote": self.quote.value,
            "price": self.price,
            "quantity": self.quantity,
            "quote_volume": self.price * self.quantity,
            "base_fee": self.base_fee,
            "quote_fee": self.quote_fee,
            "maker_order_id": self.maker_order_id,
            "taker_order_id": self.taker_order_id,
            "maker_agent": self.maker_agent,
            "taker_agent": self.taker_agent,
            "taker_side": self.taker_side.value,
            "sequence": self.sequence,
        }
