"""JSONL event and per-round snapshot logging for a single run."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class EventLogger:
    """Appends events to ``events.jsonl`` and round snapshots to ``snapshots.jsonl``."""

    def __init__(self, run_dir: str | Path) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._events = (self.run_dir / "events.jsonl").open("w", encoding="utf-8")
        self._snapshots = (self.run_dir / "snapshots.jsonl").open("w", encoding="utf-8")
        self.current_round = 0

    # --- writers ---------------------------------------------------------

    def exchange_sink(self, kind: str, payload: dict) -> None:
        """Sink passed to :class:`~skittles.market.exchange.Exchange`."""
        self._write(self._events, {"type": kind, "round": self.current_round, **payload})

    def log(self, event_type: str, data: dict[str, Any]) -> None:
        self._write(self._events, {"type": event_type, "round": self.current_round, **data})

    def snapshot(self, data: dict[str, Any]) -> None:
        self._write(self._snapshots, data)

    # --- lifecycle -------------------------------------------------------

    def close(self) -> None:
        self._events.close()
        self._snapshots.close()

    def __enter__(self) -> "EventLogger":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @staticmethod
    def _write(handle: Any, obj: dict) -> None:
        handle.write(json.dumps(obj, ensure_ascii=False) + "\n")
        handle.flush()
