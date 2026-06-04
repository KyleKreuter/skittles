"""The action surface shared by every agent.

:class:`ToolContext` binds the exchange to a single agent for the duration of
one turn and exposes the operations an agent may perform. The LLM agent reaches
these through function calling (validated via :func:`dispatch`); the heuristic
agent calls the same methods directly. This keeps the rules in one place.
"""

from __future__ import annotations

from pydantic import BaseModel, ValidationError

from skittles.domain.colors import COLOR_ORDER, Color, all_market_pairs
from skittles.market.exchange import Exchange, OrderRejected
from skittles.market.order import Side


class PlaceOrderArgs(BaseModel):
    side: Side
    base: Color
    quote: Color
    quantity: int
    price: int


class CancelOrderArgs(BaseModel):
    order_id: int


class ViewMarketArgs(BaseModel):
    base: Color
    quote: Color


class ToolContext:
    """Per-turn handle for one agent onto the exchange."""

    def __init__(
        self,
        exchange: Exchange,
        agent_id: str,
        *,
        round_index: int,
        rounds_total: int,
        market_depth: int = 5,
    ) -> None:
        self.exchange = exchange
        self.agent_id = agent_id
        self.round_index = round_index
        self.rounds_total = rounds_total
        self.market_depth = market_depth
        self.calls = 0
        self.done = False

    # --- read operations -------------------------------------------------

    def get_state(self) -> dict:
        inv = self.exchange.inventories[self.agent_id]
        leading_color, leading_count = inv.max_color()
        return {
            "agent_id": self.agent_id,
            "round": self.round_index,
            "rounds_total": self.rounds_total,
            "rounds_remaining": self.rounds_total - self.round_index,
            "inventory": {
                c.value: {
                    "available": inv.available[c],
                    "reserved": inv.reserved[c],
                    "total": inv.total(c),
                }
                for c in COLOR_ORDER
            },
            "leading_color": leading_color.value,
            "leading_count": leading_count,
            "grand_total": inv.grand_total(),
            "fee_rate": self.exchange.fee_rate,
            "goal": "maximize the count of a single color (available skittles)",
            "color_ranking": [c.value for c in COLOR_ORDER],
        }

    def view_markets(self) -> dict:
        """All 10 markets with their order books (anonymous, top levels)."""
        books = []
        for base, quote in all_market_pairs():
            books.append(self.exchange.market_snapshot(base, quote, self.market_depth))
        return {
            "explanation": (
                "Each market is (base, quote) with base the lower-ranked color. "
                "BUY base = acquire base, pay quote. SELL base = give base, get quote. "
                "Price is quote-skittles per 1 base-skittle."
            ),
            "markets": books,
        }

    def view_market(self, base: Color, quote: Color) -> dict:
        return self.exchange.market_snapshot(base, quote, self.market_depth)

    def my_orders(self) -> dict:
        return {
            "open_orders": [
                o.to_dict(include_agent=False)
                for o in self.exchange.open_orders(self.agent_id)
            ]
        }

    # --- write operations ------------------------------------------------

    def place_order(
        self, side: Side, base: Color, quote: Color, quantity: int, price: int
    ) -> dict:
        result = self.exchange.place_order(
            self.agent_id, side, base, quote, quantity, price
        )
        return result.to_dict()

    def cancel_order(self, order_id: int) -> dict:
        self.exchange.cancel_order(self.agent_id, order_id)
        return {"ok": True, "order_id": order_id}

    def end_turn(self) -> dict:
        self.done = True
        return {"turn_ended": True}


# --- LLM tool wiring -----------------------------------------------------

_COLOR_ENUM = [c.value for c in COLOR_ORDER]


def tool_specs() -> list[dict]:
    """OpenAI/LiteLLM function-calling schema for the agent's tools."""
    return [
        {
            "type": "function",
            "function": {
                "name": "get_state",
                "description": "Your current round, inventory (available/reserved/total per color) and leading color.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "view_markets",
                "description": "Order books for all 10 color-pair markets (top price levels, anonymous).",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "my_orders",
                "description": "List your own resting (open / partially filled) orders with their ids.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "place_order",
                "description": (
                    "Place a limit order. Market is (base, quote) with base the lower-ranked "
                    "color. BUY base = acquire base and pay quote; SELL base = give base and "
                    "receive quote. Price = quote per base (positive integer). Offered skittles "
                    "are escrowed immediately."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "side": {"type": "string", "enum": ["BUY", "SELL"]},
                        "base": {"type": "string", "enum": _COLOR_ENUM},
                        "quote": {"type": "string", "enum": _COLOR_ENUM},
                        "quantity": {"type": "integer", "minimum": 1},
                        "price": {"type": "integer", "minimum": 1},
                    },
                    "required": ["side", "base", "quote", "quantity", "price"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "cancel_order",
                "description": "Cancel one of your resting orders by id and refund its escrow.",
                "parameters": {
                    "type": "object",
                    "properties": {"order_id": {"type": "integer"}},
                    "required": ["order_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "end_turn",
                "description": "End your turn for this round. Call this when you are done acting.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]


def dispatch(ctx: ToolContext, name: str, arguments: dict) -> dict:
    """Validate and execute a tool call, returning a JSON-serializable result.

    Any rejection (bad args, insufficient inventory, unknown order) is returned
    as ``{"error": ...}`` so the model can read it and correct course.
    """
    ctx.calls += 1
    try:
        if name == "get_state":
            return ctx.get_state()
        if name == "view_markets":
            return ctx.view_markets()
        if name == "my_orders":
            return ctx.my_orders()
        if name == "place_order":
            args = PlaceOrderArgs(**arguments)
            return ctx.place_order(args.side, args.base, args.quote, args.quantity, args.price)
        if name == "cancel_order":
            args = CancelOrderArgs(**arguments)
            return ctx.cancel_order(args.order_id)
        if name == "end_turn":
            return ctx.end_turn()
        return {"error": f"unknown tool {name!r}"}
    except ValidationError as exc:
        return {"error": f"invalid arguments for {name}: {exc.errors()}"}
    except OrderRejected as exc:
        return {"error": str(exc)}
    except Exception as exc:  # defensive: never crash a run on a bad tool call
        return {"error": f"{type(exc).__name__}: {exc}"}
