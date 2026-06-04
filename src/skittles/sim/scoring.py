"""End-of-run scoring: who holds the most of a single color?"""

from __future__ import annotations

from dataclasses import dataclass

from skittles.domain.colors import Color
from skittles.market.exchange import Exchange


@dataclass
class AgentScore:
    agent_id: str
    leading_color: Color
    leading_count: int      # the score that decides the winner
    grand_total: int        # total skittles owned (first tie-break)

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "leading_color": self.leading_color.value,
            "leading_count": self.leading_count,
            "grand_total": self.grand_total,
        }


@dataclass
class ScoreBoard:
    ranking: list[AgentScore]

    @property
    def winner(self) -> AgentScore:
        return self.ranking[0]

    def to_dict(self) -> dict:
        return {
            "winner": self.winner.agent_id,
            "ranking": [s.to_dict() for s in self.ranking],
        }


def score_run(exchange: Exchange) -> ScoreBoard:
    """Score after all open orders have been cancelled (escrow drained).

    Winner = highest single-color count. Tie-break: most total skittles, then
    agent id (stable / reproducible).
    """
    scores: list[AgentScore] = []
    for agent_id, inv in exchange.inventories.items():
        color, count = inv.max_color()
        scores.append(
            AgentScore(
                agent_id=agent_id,
                leading_color=color,
                leading_count=count,
                grand_total=inv.grand_total(),
            )
        )
    scores.sort(key=lambda s: (-s.leading_count, -s.grand_total, s.agent_id))
    return ScoreBoard(ranking=scores)
