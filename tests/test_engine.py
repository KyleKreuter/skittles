"""Engine-level: early-stop on dry rounds, end-to-end conservation (no API)."""

from __future__ import annotations

from skittles.sim.config import AgentConfig, ExperimentConfig
from skittles.sim.engine import SimulationEngine


def _heuristic_config(tmp_path, **overrides) -> ExperimentConfig:
    base = dict(
        rounds=30,
        seed=42,
        output_dir=str(tmp_path),
        agents=[AgentConfig(id=f"h{i}", type="heuristic") for i in range(3)],
    )
    base.update(overrides)
    return ExperimentConfig(**base)


def test_stops_early_when_market_goes_dry(tmp_path):
    # Heuristic agents converge after round 1, so trading dries up quickly.
    cfg = _heuristic_config(tmp_path, rounds=30, stop_after_dry_rounds=3)
    result = SimulationEngine(cfg).run()
    assert result.report["rounds_completed"] < 30  # aborted early


def test_runs_all_rounds_without_dry_stop(tmp_path):
    cfg = _heuristic_config(tmp_path, rounds=5, stop_after_dry_rounds=None)
    result = SimulationEngine(cfg).run()
    assert result.report["rounds_completed"] == 5


def test_end_to_end_conservation(tmp_path):
    cfg = _heuristic_config(tmp_path, rounds=10, stop_after_dry_rounds=None)
    result = SimulationEngine(cfg).run()
    # After settlement, agents' totals plus the fee vault equal the start supply.
    agents_total = sum(a["grand_total"] for a in result.report["agents"])
    assert agents_total + result.report["fees_collected_total"] == 3 * cfg.initial_skittles
