"""Shared test helpers."""

from __future__ import annotations

import pytest

from skittles.domain.colors import COLOR_ORDER, Color
from skittles.domain.inventory import Inventory
from skittles.market.exchange import Exchange


def make_exchange(
    holdings: dict[str, dict[Color, int]], fee_rate: float = 0.0
) -> Exchange:
    """Build an exchange with explicit per-agent available holdings."""
    inventories = {
        agent_id: Inventory(available=dict(colors))
        for agent_id, colors in holdings.items()
    }
    return Exchange(inventories, fee_rate=fee_rate)


def total_per_color(exchange: Exchange) -> dict[Color, int]:
    """Sum skittles per color across all agents *and the fee vault*.

    With a fee, agents' circulating supply shrinks but the global total
    (agents + house) is still conserved.
    """
    totals = {c: 0 for c in COLOR_ORDER}
    for inv in exchange.inventories.values():
        for c in COLOR_ORDER:
            totals[c] += inv.total(c)
    for c in COLOR_ORDER:
        totals[c] += exchange.fees_collected[c]
    return totals


@pytest.fixture
def two_agents() -> Exchange:
    """Alice and Bob each hold 50 RED and 50 BLUE."""
    return make_exchange(
        {
            "alice": {Color.RED: 50, Color.BLUE: 50},
            "bob": {Color.RED: 50, Color.BLUE: 50},
        }
    )
