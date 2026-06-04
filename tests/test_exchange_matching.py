"""Matching behaviour: crossing, maker-price execution, partial fills, priority."""

from __future__ import annotations

import pytest

from skittles.domain.colors import Color
from skittles.market.exchange import Exchange, OrderRejected
from skittles.market.order import OrderStatus, Side

from .conftest import make_exchange


def test_resting_sell_then_crossing_buy_executes_at_maker_price(two_agents: Exchange):
    ex = two_agents
    # Alice rests a SELL of 10 RED at 2 BLUE each.
    res_sell = ex.place_order("alice", Side.SELL, Color.RED, Color.BLUE, quantity=10, price=2)
    assert res_sell.status is OrderStatus.OPEN
    assert ex.inventories["alice"].reserved[Color.RED] == 10

    # Bob buys 10 RED at limit 3 -> executes at maker price 2, refunded the rest.
    res_buy = ex.place_order("bob", Side.BUY, Color.RED, Color.BLUE, quantity=10, price=3)
    assert res_buy.status is OrderStatus.FILLED
    assert res_buy.filled_quantity == 10
    assert res_buy.fills == [type(res_buy.fills[0])(price=2, quantity=10)]

    alice, bob = ex.inventories["alice"], ex.inventories["bob"]
    # Alice: 50-10 RED, 50 + 10*2 BLUE.
    assert alice.available[Color.RED] == 40
    assert alice.reserved[Color.RED] == 0
    assert alice.available[Color.BLUE] == 70
    # Bob: 50+10 RED, 50 - 10*2 BLUE (escrowed 30 at limit 3, refunded 10).
    assert bob.available[Color.RED] == 60
    assert bob.available[Color.BLUE] == 30
    assert bob.reserved[Color.BLUE] == 0


def test_partial_fill_leaves_remainder_resting(two_agents: Exchange):
    ex = two_agents
    ex.place_order("alice", Side.SELL, Color.RED, Color.BLUE, quantity=4, price=2)
    res = ex.place_order("bob", Side.BUY, Color.RED, Color.BLUE, quantity=10, price=2)

    assert res.status is OrderStatus.PARTIALLY_FILLED
    assert res.filled_quantity == 4
    assert res.resting_quantity == 6
    # Remaining 6 RED rest as a bid; Bob still escrows 6*2 BLUE for them.
    assert ex.inventories["bob"].reserved[Color.BLUE] == 12
    assert len(ex.open_orders("bob")) == 1


def test_non_crossing_orders_both_rest(two_agents: Exchange):
    ex = two_agents
    ex.place_order("alice", Side.SELL, Color.RED, Color.BLUE, quantity=5, price=4)
    res = ex.place_order("bob", Side.BUY, Color.RED, Color.BLUE, quantity=5, price=2)
    assert res.status is OrderStatus.OPEN
    assert res.filled_quantity == 0
    assert len(ex.trades) == 0


def test_price_time_priority_picks_best_then_oldest():
    ex = make_exchange(
        {
            "m1": {Color.RED: 10},
            "m2": {Color.RED: 10},
            "taker": {Color.BLUE: 100},
        }
    )
    # Two resting asks: m1 cheaper, m2 dearer. Taker buy should hit m1 first.
    ex.place_order("m1", Side.SELL, Color.RED, Color.BLUE, quantity=5, price=2)
    ex.place_order("m2", Side.SELL, Color.RED, Color.BLUE, quantity=5, price=3)

    res = ex.place_order("taker", Side.BUY, Color.RED, Color.BLUE, quantity=6, price=5)
    assert res.filled_quantity == 6
    # 5 @ 2 from m1, then 1 @ 3 from m2.
    assert [(f.price, f.quantity) for f in res.fills] == [(2, 5), (3, 1)]
    assert ex.inventories["m1"].available[Color.BLUE] == 10  # 5*2
    assert ex.inventories["m2"].available[Color.BLUE] == 3   # 1*3


def test_cancel_refunds_remaining_escrow(two_agents: Exchange):
    ex = two_agents
    res = ex.place_order("alice", Side.SELL, Color.RED, Color.BLUE, quantity=10, price=2)
    assert ex.inventories["alice"].reserved[Color.RED] == 10

    ex.cancel_order("alice", res.order_id)
    assert ex.inventories["alice"].reserved[Color.RED] == 0
    assert ex.inventories["alice"].available[Color.RED] == 50
    assert len(ex.open_orders("alice")) == 0


def test_rejects_non_canonical_market(two_agents: Exchange):
    ex = two_agents
    # BLUE outranks RED, so (BLUE, RED) is not canonical.
    with pytest.raises(OrderRejected, match="non-canonical"):
        ex.place_order("alice", Side.SELL, Color.BLUE, Color.RED, quantity=1, price=1)


def test_rejects_insufficient_inventory(two_agents: Exchange):
    ex = two_agents
    with pytest.raises(OrderRejected, match="insufficient"):
        ex.place_order("alice", Side.SELL, Color.RED, Color.BLUE, quantity=999, price=1)


def test_rejects_non_integer_or_nonpositive(two_agents: Exchange):
    ex = two_agents
    with pytest.raises(OrderRejected):
        ex.place_order("alice", Side.SELL, Color.RED, Color.BLUE, quantity=0, price=1)
    with pytest.raises(OrderRejected):
        ex.place_order("alice", Side.SELL, Color.RED, Color.BLUE, quantity=1, price=-2)
