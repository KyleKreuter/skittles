"""Skittle colors and the canonical market-pair convention.

Every unordered pair of colors maps to exactly one market ``(base, quote)``.
We fix a total order over the colors and define ``base`` as the lower-ranked
color and ``quote`` as the higher-ranked one. With 5 colors this yields
C(5, 2) = 10 markets.
"""

from __future__ import annotations

from enum import Enum
from itertools import combinations


class Color(str, Enum):
    """The five Skittle colors. ``str`` mixin makes them JSON/CLI friendly."""

    RED = "RED"
    GREEN = "GREEN"
    BLUE = "BLUE"
    ORANGE = "ORANGE"
    YELLOW = "YELLOW"

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return self.value


# Canonical total order used to derive market pairs deterministically.
COLOR_ORDER: tuple[Color, ...] = (
    Color.RED,
    Color.GREEN,
    Color.BLUE,
    Color.ORANGE,
    Color.YELLOW,
)

_RANK: dict[Color, int] = {color: i for i, color in enumerate(COLOR_ORDER)}


def color_rank(color: Color) -> int:
    """Return the canonical rank of ``color`` (lower = earlier)."""
    return _RANK[color]


def canonical_pair(a: Color, b: Color) -> tuple[Color, Color]:
    """Map two distinct colors to the canonical ``(base, quote)`` market pair.

    ``base`` is the lower-ranked color, ``quote`` the higher-ranked one.

    Raises:
        ValueError: if ``a`` and ``b`` are the same color.
    """
    if a == b:
        raise ValueError(f"a market needs two distinct colors, got {a} twice")
    return (a, b) if _RANK[a] < _RANK[b] else (b, a)


def all_market_pairs() -> list[tuple[Color, Color]]:
    """Return all 10 canonical ``(base, quote)`` market pairs."""
    return [canonical_pair(a, b) for a, b in combinations(COLOR_ORDER, 2)]
