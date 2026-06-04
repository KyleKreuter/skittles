"""System prompt and per-turn observation for the LLM agent."""

from __future__ import annotations

from skittles.agents.tools import ToolContext
from skittles.domain.colors import COLOR_ORDER

SYSTEM_PROMPT = """\
You are an autonomous trader in a multi-round Skittles market experiment.

GOAL
Maximize the number of skittles you hold of a SINGLE color. Only your highest
single-color count at the END of the final round decides your score — the color
itself does not matter, just pick one and accumulate it. Every player started
with {initial} skittles randomly split across the five colors.

COLORS (ranked, low to high): {ranking}

MARKETS (a continuous double-auction order book per color pair)
- A market is written (base, quote) where `base` is the lower-ranked color.
- BUY base  = acquire `base`, paying `quote`.
- SELL base = give away `base`, receiving `quote`.
- Price is an integer: how many `quote` skittles buy ONE `base` skittle.
- To convert color X into color Y, place the order on the (X,Y) or (Y,X) market
  on whichever side moves you toward Y. Any color-for-color swap is possible.
- When you place an order the offered skittles are escrowed (locked) immediately:
  a SELL locks `quantity` base; a BUY locks `quantity * price` quote. Cancelling
  refunds the lock. Trades execute at the resting (maker) order's price, so
  crossing with a generous limit can fill you at a better price.
- The exchange charges a FEE on every trade: a fraction of what you *receive*
  is kept by the house (floored to whole skittles) and removed from play. So
  each trade shrinks the total supply a little — trade with intent, not churn.

HOW PLAY WORKS
- The game runs for a fixed number of rounds. You get one turn per round.
- Other traders act too. Orders you leave in the book rest across rounds until
  they fill or you cancel them.
- Each turn: inspect your state and the markets, then place and/or cancel orders,
  and finally call `end_turn`. You have a limited number of tool calls per turn,
  so be decisive. Briefly state your reasoning in plain text alongside your calls.

Think strategically: consolidating toward one color usually means selling your
minority colors and buying your chosen color at acceptable rates."""

FORUM_BLOCK = """

FORUM
There is a shared public forum. With `broadcast` you post a message that carries
your name and is seen by ALL agents; `view_forum` re-reads recent posts. Use it
to negotiate trades, signal intent, propose coordination or mislead rivals. It is
cheap talk: nobody is bound by what they say, and others may bluff. Trades only
happen through the order book — the forum just lets you talk about them."""


def system_prompt(initial_skittles: int, forum_enabled: bool = True) -> str:
    text = SYSTEM_PROMPT.format(
        initial=initial_skittles,
        ranking=" < ".join(c.value for c in COLOR_ORDER),
    )
    if forum_enabled:
        text += FORUM_BLOCK
    return text


def build_observation(ctx: ToolContext) -> str:
    """Compact per-turn observation: own state plus a market digest."""
    state = ctx.get_state()
    inv = state["inventory"]
    holdings = ", ".join(
        f"{c.value}={inv[c.value]['available']}"
        + (f"(+{inv[c.value]['reserved']} locked)" if inv[c.value]["reserved"] else "")
        for c in COLOR_ORDER
    )

    lines = [
        f"Round {state['round']} of {state['rounds_total']} "
        f"({state['rounds_remaining']} remaining).",
        f"Your holdings: {holdings}.",
        f"Currently leading: {state['leading_count']} × {state['leading_color']}.",
        f"Exchange fee: {state['fee_rate'] * 100:.0f}% of what you receive per trade.",
    ]

    open_orders = ctx.my_orders()["open_orders"]
    if open_orders:
        oo = "; ".join(
            f"#{o['order_id']} {o['side']} {o['remaining']} {o['base']}"
            f"/{o['quote']} @ {o['price']}"
            for o in open_orders
        )
        lines.append(f"Your resting orders: {oo}.")

    markets = [m for m in ctx.view_markets()["markets"] if m["bids"] or m["asks"]]
    if markets:
        lines.append("Active markets (bids = buyers of base, asks = sellers of base):")
        for m in markets:
            bids = " ".join(f"{b['quantity']}@{b['price']}" for b in m["bids"]) or "-"
            asks = " ".join(f"{a['quantity']}@{a['price']}" for a in m["asks"]) or "-"
            lines.append(f"  {m['base']}/{m['quote']}: bids[{bids}] asks[{asks}]")
    else:
        lines.append("No resting orders in any market yet.")

    if ctx.forum is not None:
        posts = ctx.view_forum()["posts"]
        if posts:
            lines.append("Recent forum messages (all agents see these):")
            for p in posts:
                lines.append(f"  [r{p['round']}] {p['name']}: {p['message']}")
        else:
            lines.append("Forum is empty so far. You may broadcast a message.")

    lines.append("Act now: place/cancel orders, optionally broadcast, then call end_turn.")
    return "\n".join(lines)
