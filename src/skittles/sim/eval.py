"""Evaluation metric: a log score in [0, 1] with the baseline as ground zero.

The heuristic baseline is the reference floor (score 0): matching the dumb
mechanical player earns no credit. A configurable ``ceiling`` (default the
starting hoard, ``initial_skittles``) maps to 1 — converting everything into a
single color is "perfect". The mapping is logarithmic, so clearly beating the
baseline is rewarded while the last stretch toward perfection flattens out.

    log_score = clamp( ln(value / floor) / ln(ceiling / floor), 0, 1 )
"""

from __future__ import annotations

import math


def log_score(value: float, floor: float, ceiling: float) -> float:
    """Map ``value`` to [0, 1]: ``floor`` -> 0, ``ceiling`` -> 1, log-scaled.

    Values at or below the floor score 0; at or above the ceiling score 1.
    """
    if floor <= 0 or value <= 0:
        return 0.0
    ceiling = max(ceiling, floor + 1)  # keep the denominator strictly positive
    if value <= floor:
        return 0.0
    return min(1.0, math.log(value / floor) / math.log(ceiling / floor))


def evaluate(
    agents: list[dict], *, initial_skittles: int, ceiling: int | None = None
) -> dict:
    """Score every agent against the heuristic baseline (ground zero).

    Args:
        agents: dicts with at least ``agent_id``, ``type`` and ``leading_count``.
        initial_skittles: default ceiling (the perfect single-color hoard).
        ceiling: optional explicit ceiling overriding ``initial_skittles``.

    Returns a dict with the chosen ``floor``/``ceiling``, the baseline id, and
    a ``scores`` list sorted by ``log_score`` descending. If no heuristic agent
    is present, the lowest ``leading_count`` in the field becomes the floor.
    """
    baseline = next((a for a in agents if a.get("type") == "heuristic"), None)
    if baseline is not None:
        floor = baseline["leading_count"]
    else:
        floor = min((a["leading_count"] for a in agents), default=0)
    if ceiling is None:
        ceiling = initial_skittles

    scores = [
        {
            "agent_id": a["agent_id"],
            "type": a.get("type"),
            "model": a.get("model"),
            "leading_count": a["leading_count"],
            "log_score": round(log_score(a["leading_count"], floor, ceiling), 4),
        }
        for a in agents
    ]
    scores.sort(key=lambda s: -s["log_score"])
    return {
        "baseline_id": baseline["agent_id"] if baseline else None,
        "floor": floor,
        "ceiling": ceiling,
        "scores": scores,
    }
