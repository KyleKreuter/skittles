"""A shared broadcast forum.

Unlike the anonymous order book, the forum is **named**: every post carries the
author's agent id and a free-text message, and all agents see recent posts in
their per-turn observation (plus a ``view_forum`` tool to re-read). This gives
agents a channel to negotiate, signal, coordinate — or bluff.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Callable

EventSink = Callable[[str, dict], None]
MAX_MESSAGE_LENGTH = 500


@dataclass
class Post:
    sequence: int
    agent_id: str
    message: str
    round: int

    def to_dict(self) -> dict:
        return {
            "sequence": self.sequence,
            "agent_id": self.agent_id,
            "message": self.message,
            "round": self.round,
        }


class Forum:
    def __init__(
        self,
        event_sink: EventSink | None = None,
        max_message_length: int = MAX_MESSAGE_LENGTH,
    ) -> None:
        self.posts: list[Post] = []
        self.max_message_length = max_message_length
        self._event_sink = event_sink
        self._next_seq = 1

    def post(self, agent_id: str, message: str, round_index: int) -> Post:
        """Append a broadcast from ``agent_id``. Messages are trimmed/capped."""
        text = message.strip()[: self.max_message_length]
        post = Post(
            sequence=self._next_seq,
            agent_id=agent_id,
            message=text,
            round=round_index,
        )
        self._next_seq += 1
        self.posts.append(post)
        if self._event_sink is not None:
            self._event_sink("broadcast", post.to_dict())
        return post

    def recent(self, n: int) -> list[Post]:
        """The ``n`` most recent posts, oldest-first."""
        if n <= 0:
            return []
        return self.posts[-n:]

    def count_by_agent(self) -> dict[str, int]:
        return dict(Counter(p.agent_id for p in self.posts))
