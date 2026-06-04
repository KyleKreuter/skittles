"""Exchange fee: skimmed from receipts, conserved into the house vault."""

from __future__ import annotations

import random

from skittles.domain.colors import COLOR_ORDER, Color, canonical_pair
from skittles.market.exchange import OrderRejected
from skittles.market.order import Side

from .conftest import make_exchange, total_per_color


def test_fee_skimmed_from_both_received_legs():
    # 10% fee, trade of 10 RED @ 2 BLUE -> quote volume 20.
    ex = make_exchange(
        {"alice": {Color.RED: 50, Color.BLUE: 50}, "bob": {Color.RED: 50, Color.BLUE: 50}},
        fee_rate=0.1,
    )
    ex.place_order("alice", Side.SELL, Color.RED, Color.BLUE, quantity=10, price=2)
    ex.place_order("bob", Side.BUY, Color.RED, Color.BLUE, quantity=10, price=2)

    alice, bob = ex.inventories["alice"], ex.inventories["bob"]
    # Seller receives 20 BLUE minus floor(20*0.1)=2 -> 18 -> 50+18 = 68.
    assert alice.available[Color.BLUE] == 68
    assert alice.available[Color.RED] == 40
    # Buyer receives 10 RED minus floor(10*0.1)=1 -> 9 -> 50+9 = 59.
    assert bob.available[Color.RED] == 59
    assert bob.available[Color.BLUE] == 30  # paid 20 BLUE in full

    # House kept the fees.
    assert ex.fees_collected[Color.BLUE] == 2
    assert ex.fees_collected[Color.RED] == 1


def test_global_total_conserved_including_house():
    ex = make_exchange(
        {"alice": {Color.RED: 50, Color.BLUE: 50}, "bob": {Color.RED: 50, Color.BLUE: 50}},
        fee_rate=0.1,
    )
    before = total_per_color(ex)
    ex.place_order("alice", Side.SELL, Color.RED, Color.BLUE, quantity=10, price=2)
    ex.place_order("bob", Side.BUY, Color.RED, Color.BLUE, quantity=10, price=2)
    after = total_per_color(ex)
    assert after == before  # agents + house unchanged per color


def test_small_trade_pays_no_fee_due_to_floor():
    ex = make_exchange(
        {"a": {Color.RED: 5}, "b": {Color.BLUE: 5}},
        fee_rate=0.1,
    )
    # quote volume 1, base qty 1 -> floor(0.1) = 0 fee on both legs.
    ex.place_order("a", Side.SELL, Color.RED, Color.BLUE, quantity=1, price=1)
    ex.place_order("b", Side.BUY, Color.RED, Color.BLUE, quantity=1, price=1)
    assert sum(ex.fees_collected.values()) == 0
    assert ex.inventories["a"].available[Color.BLUE] == 1
    assert ex.inventories["b"].available[Color.RED] == 1


def test_conservation_under_random_stream_with_fee():
    rng = random.Random(99)
    agents = ["a", "b", "c"]
    holdings = {a: {c: rng.randint(10, 40) for c in COLOR_ORDER} for a in agents}
    ex = make_exchange(holdings, fee_rate=0.1)
    expected = total_per_color(ex)

    for _ in range(1500):
        agent = rng.choice(agents)
        c1, c2 = rng.sample(list(COLOR_ORDER), 2)
        base, quote = canonical_pair(c1, c2)
        try:
            ex.place_order(agent, rng.choice([Side.BUY, Side.SELL]),
                           base, quote, rng.randint(1, 8), rng.randint(1, 4))
        except OrderRejected:
            pass
        assert total_per_color(ex) == expected
