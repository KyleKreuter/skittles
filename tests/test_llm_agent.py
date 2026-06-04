"""LLM agent tool-loop, cost tracking and budget gate — no network calls."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from skittles.agents.cost import CostTracker
from skittles.agents.llm_agent import LLMAgent
from skittles.agents.tools import ToolContext
from skittles.domain.colors import Color
from skittles.sim.config import AgentConfig, ExperimentConfig

from .conftest import make_exchange


def _tool_call(cid: str, name: str, args: dict) -> SimpleNamespace:
    return SimpleNamespace(
        id=cid,
        function=SimpleNamespace(name=name, arguments=json.dumps(args)),
    )


def _response(content, tool_calls, cost=0.001) -> SimpleNamespace:
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message)],
        _hidden_params={"response_cost": cost},
    )


class _Script:
    """A fake litellm.completion that replays scripted responses in order."""

    def __init__(self, responses: list[SimpleNamespace]) -> None:
        self.responses = responses
        self.calls = 0

    def __call__(self, **kwargs) -> SimpleNamespace:
        resp = self.responses[self.calls]
        self.calls += 1
        return resp


def _config() -> tuple[AgentConfig, ExperimentConfig]:
    cfg = AgentConfig(id="llm", type="llm", provider="mistral", model="mistral-small-latest")
    exp = ExperimentConfig(
        rounds=5,
        agents=[cfg, AgentConfig(id="other", type="heuristic")],
    )
    return cfg, exp


def test_agent_places_order_then_ends_turn():
    ex = make_exchange({"llm": {Color.RED: 50, Color.BLUE: 50}, "other": {Color.RED: 50}})
    cfg, exp = _config()
    tracker = CostTracker(limit_usd=10.0)

    script = _Script([
        _response(
            "I will sell some RED for BLUE.",
            [_tool_call("c1", "place_order", {
                "side": "SELL", "base": "RED", "quote": "BLUE",
                "quantity": 5, "price": 2,
            })],
        ),
        _response("Done for now.", [_tool_call("c2", "end_turn", {})]),
    ])

    agent = LLMAgent(cfg, exp, tracker, completion_fn=script)
    ctx = ToolContext(ex, "llm", round_index=1, rounds_total=5)
    agent.act(ctx)

    assert script.calls == 2
    assert ctx.done is True
    assert ex.inventories["llm"].reserved[Color.RED] == 5  # escrowed by the SELL
    assert agent.cost_usd == pytest.approx(0.002)
    assert tracker.spent_usd == pytest.approx(0.002)
    assert any("sell some RED" in n for n in agent.notes)


def test_invalid_tool_args_are_reported_not_crashing():
    ex = make_exchange({"llm": {Color.RED: 50}, "other": {Color.RED: 50}})
    cfg, exp = _config()
    tracker = CostTracker(limit_usd=10.0)

    # First call: a non-canonical market (rejected). Second: end the turn.
    script = _Script([
        _response(None, [_tool_call("c1", "place_order", {
            "side": "SELL", "base": "BLUE", "quote": "RED", "quantity": 1, "price": 1,
        })]),
        _response(None, [_tool_call("c2", "end_turn", {})]),
    ])

    agent = LLMAgent(cfg, exp, tracker, completion_fn=script)
    ctx = ToolContext(ex, "llm", round_index=1, rounds_total=5)
    agent.act(ctx)  # must not raise

    assert ctx.done is True
    assert len(ex.open_orders("llm")) == 0  # nothing got placed


def test_memory_accumulates_and_is_replayed_next_turn():
    from skittles.agents.prompts import build_observation

    ex = make_exchange({"llm": {Color.RED: 50, Color.BLUE: 50}, "other": {Color.RED: 50}})
    cfg, exp = _config()
    tracker = CostTracker(limit_usd=10.0)

    # Round 1: agent reasons, then ends its turn.
    script = _Script([
        _response("Targeting BLUE this round.", [_tool_call("c1", "end_turn", {})]),
    ])
    agent = LLMAgent(cfg, exp, tracker, completion_fn=script)
    agent.act(ToolContext(ex, "llm", round_index=1, rounds_total=5))

    assert agent._memory == [(1, "Targeting BLUE this round.")]

    # Round 2: that memory must appear in the fresh observation.
    obs = build_observation(
        ToolContext(ex, "llm", round_index=2, rounds_total=5), memory=agent._memory
    )
    assert "your memory" in obs.lower()
    assert "Targeting BLUE this round." in obs


def test_budget_exhausted_skips_api_call():
    ex = make_exchange({"llm": {Color.RED: 50}, "other": {Color.RED: 50}})
    cfg, exp = _config()
    tracker = CostTracker(limit_usd=1.0)
    tracker.add(1.0)  # already at the ceiling

    def explode(**kwargs):
        raise AssertionError("completion must not be called when budget is exhausted")

    agent = LLMAgent(cfg, exp, tracker, completion_fn=explode)
    ctx = ToolContext(ex, "llm", round_index=1, rounds_total=5)
    agent.act(ctx)

    assert agent.cost_usd == 0.0
    assert any("budget exhausted" in n for n in agent.notes)
