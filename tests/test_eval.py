"""Log-score evaluation: baseline as ground zero, [0,1] range."""

from __future__ import annotations

import pytest

from skittles.sim.eval import evaluate, log_score


def test_floor_scores_zero_ceiling_scores_one():
    assert log_score(40, floor=40, ceiling=100) == 0.0
    assert log_score(100, floor=40, ceiling=100) == 1.0


def test_below_floor_is_zero_above_ceiling_is_one():
    assert log_score(30, floor=40, ceiling=100) == 0.0
    assert log_score(120, floor=40, ceiling=100) == 1.0


def test_monotonic_and_in_range_between_floor_and_ceiling():
    prev = -1.0
    for v in range(40, 101, 5):
        s = log_score(v, floor=40, ceiling=100)
        assert 0.0 <= s <= 1.0
        assert s >= prev  # non-decreasing
        prev = s


def test_log_curve_is_concave():
    # Equal-size steps yield smaller gains as we approach the ceiling.
    gain_low = log_score(60, 40, 100) - log_score(40, 40, 100)
    gain_high = log_score(100, 40, 100) - log_score(80, 40, 100)
    assert gain_low > gain_high


def test_degenerate_floor_is_safe():
    assert log_score(50, floor=0, ceiling=100) == 0.0
    assert log_score(50, floor=100, ceiling=100) in (0.0, 1.0)  # no crash/NaN


def test_evaluate_uses_baseline_as_floor():
    agents = [
        {"agent_id": "llm1", "type": "llm", "model": "m", "leading_count": 90},
        {"agent_id": "base", "type": "heuristic", "model": None, "leading_count": 45},
        {"agent_id": "llm2", "type": "llm", "model": "m", "leading_count": 45},
        {"agent_id": "llm3", "type": "llm", "model": "m", "leading_count": 30},
    ]
    result = evaluate(agents, initial_skittles=100)
    assert result["baseline_id"] == "base"
    assert result["floor"] == 45
    by_id = {s["agent_id"]: s["log_score"] for s in result["scores"]}
    assert by_id["base"] == 0.0          # ground zero
    assert by_id["llm2"] == 0.0          # equals baseline
    assert by_id["llm3"] == 0.0          # below baseline
    assert 0.0 < by_id["llm1"] <= 1.0    # clearly above baseline
    assert result["scores"][0]["agent_id"] == "llm1"  # sorted desc
