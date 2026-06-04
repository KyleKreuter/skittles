"""Per-agent Skittle inventory with an escrow (``reserved``) compartment.

Every color has two integer buckets:

* ``available`` — freely usable skittles.
* ``reserved``  — skittles locked behind an open order (escrow). They still
  belong to the agent (counted as owned) but cannot back another order until
  the order fills or is cancelled.

State transitions used by the exchange:

* place SELL  -> :meth:`reserve` base out of available
* place BUY   -> :meth:`reserve` quote out of available
* cancel/refund -> :meth:`release` reserved back to available
* trade settles -> :meth:`settle_out` (reserved leaves the agent for good)
* trade receives -> :meth:`add` incoming color into available
"""

from __future__ import annotations

import random

from skittles.domain.colors import COLOR_ORDER, Color


class Inventory:
    """Mutable holdings for a single agent. All quantities are non-negative ints."""

    __slots__ = ("available", "reserved")

    def __init__(
        self,
        available: dict[Color, int] | None = None,
        reserved: dict[Color, int] | None = None,
    ) -> None:
        self.available: dict[Color, int] = {c: 0 for c in COLOR_ORDER}
        self.reserved: dict[Color, int] = {c: 0 for c in COLOR_ORDER}
        if available:
            for color, qty in available.items():
                self.available[color] = qty
        if reserved:
            for color, qty in reserved.items():
                self.reserved[color] = qty

    # --- queries ---------------------------------------------------------

    def total(self, color: Color) -> int:
        """Owned skittles of ``color`` (available + reserved)."""
        return self.available[color] + self.reserved[color]

    def grand_total(self) -> int:
        """Total skittles owned across all colors."""
        return sum(self.total(c) for c in COLOR_ORDER)

    def max_color(self) -> tuple[Color, int]:
        """Return the color with the highest *available* count and that count.

        Used for end-of-run scoring (after all orders are cancelled, so
        ``reserved`` is empty). Ties resolve by canonical color order.
        """
        best = max(COLOR_ORDER, key=lambda c: (self.available[c], -COLOR_ORDER.index(c)))
        return best, self.available[best]

    # --- mutations -------------------------------------------------------

    def reserve(self, color: Color, qty: int) -> None:
        """Move ``qty`` of ``color`` from available into escrow."""
        _check_positive(qty)
        if self.available[color] < qty:
            raise InsufficientInventory(
                f"need {qty} {color} available, have {self.available[color]}"
            )
        self.available[color] -= qty
        self.reserved[color] += qty

    def release(self, color: Color, qty: int) -> None:
        """Move ``qty`` of ``color`` from escrow back to available (refund/cancel)."""
        _check_positive(qty)
        if self.reserved[color] < qty:
            raise InsufficientInventory(
                f"need {qty} {color} reserved, have {self.reserved[color]}"
            )
        self.reserved[color] -= qty
        self.available[color] += qty

    def settle_out(self, color: Color, qty: int) -> None:
        """Remove ``qty`` of escrowed ``color`` permanently (handed to counterparty)."""
        _check_positive(qty)
        if self.reserved[color] < qty:
            raise InsufficientInventory(
                f"need {qty} {color} reserved to settle, have {self.reserved[color]}"
            )
        self.reserved[color] -= qty

    def add(self, color: Color, qty: int) -> None:
        """Add ``qty`` of ``color`` to available (received from a trade)."""
        _check_positive(qty)
        self.available[color] += qty

    # --- serialization ---------------------------------------------------

    def snapshot(self) -> dict[str, dict[str, int]]:
        """Return a plain-dict snapshot for logging."""
        return {
            "available": {c.value: self.available[c] for c in COLOR_ORDER},
            "reserved": {c.value: self.reserved[c] for c in COLOR_ORDER},
        }

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        avail = ", ".join(f"{c.value}={self.available[c]}" for c in COLOR_ORDER)
        return f"Inventory(available[{avail}], total={self.grand_total()})"

    # --- factory ---------------------------------------------------------

    @classmethod
    def random(cls, total: int, rng: random.Random) -> "Inventory":
        """Distribute ``total`` skittles uniformly at random over the colors.

        Each skittle is independently assigned to a uniformly chosen color,
        i.e. a multinomial draw. Deterministic given ``rng``.
        """
        available: dict[Color, int] = {c: 0 for c in COLOR_ORDER}
        for _ in range(total):
            available[rng.choice(COLOR_ORDER)] += 1
        return cls(available=available)


class InsufficientInventory(Exception):
    """Raised when an inventory mutation would go negative."""


def _check_positive(qty: int) -> None:
    if not isinstance(qty, int) or qty <= 0:
        raise ValueError(f"quantity must be a positive integer, got {qty!r}")
