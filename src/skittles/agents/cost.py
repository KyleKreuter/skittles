"""Shared API cost budget across all LLM agents in a run."""

from __future__ import annotations


class CostTracker:
    """Accumulates spend and enforces an optional hard ceiling (USD)."""

    def __init__(self, limit_usd: float | None) -> None:
        self.limit_usd = limit_usd
        self.spent_usd = 0.0

    def add(self, amount: float) -> None:
        self.spent_usd += max(0.0, amount)

    def exhausted(self) -> bool:
        if self.limit_usd is None:
            return False
        return self.spent_usd >= self.limit_usd

    @property
    def remaining(self) -> float:
        if self.limit_usd is None:
            return float("inf")
        return max(0.0, self.limit_usd - self.spent_usd)
