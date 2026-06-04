"""A deterministic, rule-based baseline agent (no API calls).

Strategy: greedily converge on the color it already leads with.

Each turn it:
1. cancels its own resting orders to free escrow,
2. picks ``target`` = the color it currently has the most of,
3. tries to convert every other color it holds into ``target``: if a resting
   order on the opposite side is favorable it crosses (takes liquidity),
   otherwise it posts a passive 1:1 order (provides liquidity).

It is intentionally simple — a comparison baseline and a way to exercise the
full simulation without spending API budget, not an optimal trader.
"""

from __future__ import annotations

import random

from skittles.agents.base import Agent
from skittles.agents.tools import ToolContext
from skittles.domain.colors import COLOR_ORDER, Color, canonical_pair, color_rank
from skittles.market.exchange import OrderRejected
from skittles.market.order import Side

MAX_CONVERT_PRICE = 5  # willing to pay up to this many skittles per target


class HeuristicAgent(Agent):
    def __init__(self, agent_id: str, rng: random.Random) -> None:
        super().__init__(agent_id)
        self._rng = rng
        self._notes: list[str] = []

    @property
    def notes(self) -> list[str]:
        return self._notes

    def act(self, ctx: ToolContext) -> None:
        # 1. Free escrow from previous rounds.
        for order in ctx.exchange.open_orders(self.agent_id):
            try:
                ctx.cancel_order(order.order_id)
            except OrderRejected:
                pass

        inv = ctx.exchange.inventories[self.agent_id]
        target, _ = inv.max_color()

        others = [c for c in COLOR_ORDER if c != target and inv.available[c] > 0]
        self._rng.shuffle(others)

        for give in others:
            self._convert(ctx, give=give, target=target)

        self._notes.append(f"round {ctx.round_index}: consolidating on {target.value}")
        ctx.end_turn()

    def _convert(self, ctx: ToolContext, *, give: Color, target: Color) -> None:
        """Place an order moving ``give`` -> ``target`` for this agent."""
        inv = ctx.exchange.inventories[self.agent_id]
        base, quote = canonical_pair(target, give)
        book = ctx.exchange.books.get((base, quote))

        if color_rank(target) < color_rank(give):
            # target is base -> we BUY base, paying `give` (quote).
            best_ask = book.best_ask() if book else None
            if best_ask and best_ask.price <= MAX_CONVERT_PRICE:
                qty = min(inv.available[give] // best_ask.price, best_ask.remaining)
                if qty >= 1:
                    self._try(ctx, Side.BUY, base, quote, qty, best_ask.price)
                    return
            # Otherwise post a cheap resting bid (1 quote per base).
            qty = inv.available[give]
            if qty >= 1:
                self._try(ctx, Side.BUY, base, quote, qty, 1)
        else:
            # target is quote -> we SELL base (`give`), receiving target.
            best_bid = book.best_bid() if book else None
            if best_bid:
                qty = min(inv.available[give], best_bid.remaining)
                if qty >= 1:
                    self._try(ctx, Side.SELL, base, quote, qty, best_bid.price)
                    return
            qty = inv.available[give]
            if qty >= 1:
                self._try(ctx, Side.SELL, base, quote, qty, 1)

    @staticmethod
    def _try(ctx: ToolContext, side: Side, base: Color, quote: Color, qty: int, price: int) -> None:
        try:
            ctx.place_order(side, base, quote, qty, price)
        except OrderRejected:
            pass
