"""Conservation: skittles are never created or destroyed, only moved/escrowed."""

from __future__ import annotations

import random

from skittles.domain.colors import COLOR_ORDER, Color, canonical_pair
from skittles.market.exchange import Exchange, OrderRejected
from skittles.market.order import Side

from .conftest import make_exchange, total_per_color


def test_conservation_holds_for_simple_trade(two_agents: Exchange):
    ex = two_agents
    before = total_per_color(ex)
    ex.place_order("alice", Side.SELL, Color.RED, Color.BLUE, quantity=10, price=2)
    ex.place_order("bob", Side.BUY, Color.RED, Color.BLUE, quantity=10, price=3)
    assert total_per_color(ex) == before


def test_conservation_under_random_order_stream():
    """Fuzz: random valid orders/cancels must preserve every color's total."""
    rng = random.Random(1234)
    agents = ["a", "b", "c", "d"]
    holdings = {
        a: {c: rng.randint(5, 40) for c in COLOR_ORDER} for a in agents
    }
    ex = make_exchange(holdings)
    expected = total_per_color(ex)

    placed_order_ids: list[tuple[str, int]] = []

    for _ in range(2000):
        agent = rng.choice(agents)
        action = rng.random()

        if action < 0.8:  # place an order
            c1, c2 = rng.sample(list(COLOR_ORDER), 2)
            base, quote = canonical_pair(c1, c2)
            side = rng.choice([Side.BUY, Side.SELL])
            qty = rng.randint(1, 8)
            price = rng.randint(1, 4)
            try:
                res = ex.place_order(agent, side, base, quote, qty, price)
                placed_order_ids.append((agent, res.order_id))
            except OrderRejected:
                pass  # insufficient funds etc. — expected and fine
        elif placed_order_ids:  # cancel a previously placed order
            owner, oid = rng.choice(placed_order_ids)
            try:
                ex.cancel_order(owner, oid)
            except OrderRejected:
                pass  # already filled/cancelled — expected

        # Invariant must hold after every single step.
        assert total_per_color(ex) == expected

    # No inventory bucket ever went negative.
    for inv in ex.inventories.values():
        for c in COLOR_ORDER:
            assert inv.available[c] >= 0
            assert inv.reserved[c] >= 0


def test_cancel_all_clears_escrow_back_to_available():
    ex = make_exchange({"solo": {Color.RED: 30, Color.BLUE: 30}})
    ex.place_order("solo", Side.SELL, Color.RED, Color.BLUE, quantity=10, price=2)

    n = ex.cancel_all("solo")
    assert n == 1
    inv = ex.inventories["solo"]
    assert inv.reserved[Color.RED] == 0
    assert inv.available[Color.RED] == 30
