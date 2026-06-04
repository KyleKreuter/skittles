"""Experiment configuration (YAML -> validated pydantic models)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator


class AgentConfig(BaseModel):
    """One participant in the experiment."""

    id: str
    type: Literal["llm", "heuristic"] = "llm"

    # LLM-only fields (ignored for heuristic agents).
    provider: str | None = None          # e.g. "mistral", "openai", "anthropic"
    model: str | None = None             # e.g. "mistral-large-latest"
    temperature: float = 0.7
    reasoning_effort: str | None = None  # "minimal"/"low"/"medium"/"high" (GPT-5.x)
    persona: str | None = None           # optional extra system-prompt flavor

    @model_validator(mode="after")
    def _check_llm_fields(self) -> "AgentConfig":
        if self.type == "llm" and not self.model:
            raise ValueError(f"agent {self.id!r}: llm agents require a 'model'")
        return self

    @property
    def litellm_model(self) -> str:
        """The model string LiteLLM expects, e.g. ``mistral/mistral-large-latest``.

        If ``model`` already contains a ``provider/`` prefix it is used as-is.
        """
        if self.model and "/" in self.model:
            return self.model
        if self.provider:
            return f"{self.provider}/{self.model}"
        return self.model or ""


class ExperimentConfig(BaseModel):
    rounds: int = Field(default=50, ge=1)
    seed: int = 42
    initial_skittles: int = Field(default=100, ge=1)
    fee_rate: float = Field(default=0.1, ge=0.0, lt=1.0)  # house cut per trade
    max_tool_calls_per_turn: int = Field(default=12, ge=1)
    max_cost_usd: float | None = 5.0
    market_depth: int = Field(default=5, ge=1)
    forum_enabled: bool = True                       # shared broadcast chat
    forum_feed_size: int = Field(default=15, ge=1)   # recent posts shown per turn
    stop_after_dry_rounds: int | None = None         # abort if N rounds in a row trade nothing
    output_dir: str = "runs"
    agents: list[AgentConfig] = Field(min_length=2)

    @model_validator(mode="after")
    def _unique_ids(self) -> "ExperimentConfig":
        ids = [a.id for a in self.agents]
        if len(ids) != len(set(ids)):
            raise ValueError("agent ids must be unique")
        return self


def load_config(path: str | Path) -> ExperimentConfig:
    """Load and validate an experiment config from a YAML file."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return ExperimentConfig.model_validate(raw)
