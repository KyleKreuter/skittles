"""Agent interface. Every agent acts on a per-turn :class:`ToolContext`."""

from __future__ import annotations

from abc import ABC, abstractmethod

from skittles.agents.tools import ToolContext


class Agent(ABC):
    """Base class for all trading agents."""

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id

    @abstractmethod
    def act(self, ctx: ToolContext) -> None:
        """Take this agent's turn by calling operations on ``ctx``."""

    # Hooks the engine can read after a run (LLM agents override).
    @property
    def cost_usd(self) -> float:
        return 0.0

    @property
    def notes(self) -> list[str]:
        """Short per-turn reasoning notes captured for the research report."""
        return []
