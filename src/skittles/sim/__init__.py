"""Simulation layer: config, orchestration engine and scoring."""

from skittles.sim.config import AgentConfig, ExperimentConfig, load_config
from skittles.sim.engine import RunResult, SimulationEngine
from skittles.sim.scoring import AgentScore, ScoreBoard, score_run

__all__ = [
    "AgentConfig",
    "ExperimentConfig",
    "load_config",
    "SimulationEngine",
    "RunResult",
    "AgentScore",
    "ScoreBoard",
    "score_run",
]
