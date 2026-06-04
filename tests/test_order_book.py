"""Order book priority and aggregation."""

from __future__ import annotations

from skittles.domain.colors import Color
from skittles.market.order import Order, Side
from skittles.market.order_book import OrderBook


def _order(oid: int, side: Side, price: int, qty: int, seq: int) -> Order:
    return Order(
        order_id=oid,
        agent_id=f"a{oid}",
        side=side,
        base=Color.RED,
        quote=Color.BLUE,
        price=price,
        quantity=qty,
        sequence=seq,
    )


def test_bids_sorted_highest_price_then_oldest_first():
    book = OrderBook(Color.RED, Color.BLUE)
    book.add(_order(1, Side.BUY, price=2, qty=1, seq=10))
    book.add(_order(2, Side.BUY, price=3, qty=1, seq=11))
    book.add(_order(3, Side.BUY, price=3, qty=1, seq=9))  # same price, older

    assert book.best_bid().order_id == 3  # price 3, oldest
    assert [o.order_id for o in book.bids] == [3, 2, 1]


def test_asks_sorted_lowest_price_then_oldest_first():
    book = OrderBook(Color.RED, Color.BLUE)
    book.add(_order(1, Side.SELL, price=5, qty=1, seq=10))
    book.add(_order(2, Side.SELL, price=4, qty=1, seq=11))
    book.add(_order(3, Side.SELL, price=4, qty=1, seq=9))

    assert book.best_ask().order_id == 3  # price 4, oldest
    assert [o.order_id for o in book.asks] == [3, 2, 1]


def test_snapshot_aggregates_by_price_level():
    book = OrderBook(Color.RED, Color.BLUE)
    book.add(_order(1, Side.BUY, price=3, qty=2, seq=1))
    book.add(_order(2, Side.BUY, price=3, qty=5, seq=2))
    book.add(_order(3, Side.BUY, price=2, qty=1, seq=3))

    snap = book.snapshot(depth=5)
    assert snap["bids"] == [
        {"price": 3, "quantity": 7},
        {"price": 2, "quantity": 1},
    ]
    assert snap["asks"] == []
